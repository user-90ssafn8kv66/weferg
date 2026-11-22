import { createServer } from 'node:http';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { randomUUID, timingSafeEqual } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = path.join(ROOT, 'public');
const STORAGE_DIR = process.env.STORAGE_DIR || path.join(ROOT, 'storage');
const VOTES_FILE = path.join(STORAGE_DIR, 'votes.json');
const PORT = Number(process.env.PORT) || 3000;
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || '';
// Only believe X-Forwarded-* when the app really sits behind a proxy.
const TRUST_PROXY = process.env.TRUST_PROXY === '1';
const RATE_LIMIT = Number(process.env.RATE_LIMIT) || 60;
const RATE_WINDOW_MS = 10 * 60 * 1000;
const COOKIE = 'dv_voter';
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

const categories = JSON.parse(await readFile(path.join(ROOT, 'categories.json'), 'utf8'));
const candidateIds = new Map(
  categories.map((category) => [category.id, new Set(category.candidates.map((c) => c.id))]),
);

// votes: { [voterId]: { [categoryId]: candidateId } }
let votes = {};
try {
  votes = JSON.parse(await readFile(VOTES_FILE, 'utf8'));
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}

let saving = Promise.resolve();
function persist() {
  const snapshot = JSON.stringify(votes);
  saving = saving.catch(() => {}).then(async () => {
    await mkdir(STORAGE_DIR, { recursive: true });
    const tmp = `${VOTES_FILE}.tmp`;
    await writeFile(tmp, snapshot);
    await rename(tmp, VOTES_FILE);
  });
  return saving;
}

const hits = new Map();
function rateLimited(ip) {
  const now = Date.now();
  const entry = hits.get(ip);
  if (!entry || entry.resetAt <= now) {
    hits.set(ip, { count: 1, resetAt: now + RATE_WINDOW_MS });
    return false;
  }
  entry.count += 1;
  return entry.count > RATE_LIMIT;
}
setInterval(() => {
  const now = Date.now();
  for (const [ip, entry] of hits) if (entry.resetAt <= now) hits.delete(ip);
}, RATE_WINDOW_MS).unref();

function clientIp(req) {
  if (TRUST_PROXY) {
    const forwarded = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim();
    if (forwarded) return forwarded;
  }
  return req.socket.remoteAddress || 'unknown';
}

function voterId(req) {
  const match = String(req.headers.cookie || '').match(new RegExp(`(?:^|;\\s*)${COOKIE}=([^;]+)`));
  return match && UUID_RE.test(match[1]) ? match[1] : null;
}

function json(res, status, body, headers = {}) {
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    ...headers,
  });
  res.end(JSON.stringify(body));
}

async function readJson(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 2048) throw new Error('too large');
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

function sameOrigin(req) {
  const origin = req.headers.origin;
  if (!origin) return true;
  try {
    return new URL(origin).host === req.headers.host;
  } catch {
    return false;
  }
}

function getBallot(req, res) {
  let id = voterId(req);
  const headers = {};
  if (!id) {
    id = randomUUID();
    const secure = TRUST_PROXY && req.headers['x-forwarded-proto'] === 'https' ? '; Secure' : '';
    headers['Set-Cookie'] =
      `${COOKIE}=${id}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax${secure}`;
  }
  json(res, 200, { categories, voted: votes[id] || {} }, headers);
}

async function postVote(req, res) {
  if (!sameOrigin(req) || !String(req.headers['content-type'] || '').startsWith('application/json')) {
    return json(res, 403, { error: 'forbidden' });
  }
  if (rateLimited(clientIp(req))) return json(res, 429, { error: 'rate_limited' });

  const id = voterId(req);
  if (!id) return json(res, 400, { error: 'no_ballot' });

  let body;
  try {
    body = await readJson(req);
  } catch {
    return json(res, 400, { error: 'bad_request' });
  }
  const { categoryId, candidateId } = body || {};
  if (!candidateIds.get(categoryId)?.has(candidateId)) {
    return json(res, 400, { error: 'unknown_candidate' });
  }

  const mine = (votes[id] ||= {});
  if (mine[categoryId]) {
    return json(res, 409, { error: 'already_voted', candidateId: mine[categoryId] });
  }
  mine[categoryId] = candidateId;
  try {
    await persist();
  } catch (error) {
    delete mine[categoryId];
    console.error('Failed to save vote:', error);
    return json(res, 500, { error: 'save_failed' });
  }
  json(res, 201, { candidateId });
}

// Results stay hidden unless ADMIN_TOKEN is set and supplied.
function getResults(req, res) {
  const given = Buffer.from(String(req.headers.authorization || '').replace(/^Bearer\s+/i, ''));
  const expected = Buffer.from(ADMIN_TOKEN);
  if (!ADMIN_TOKEN || given.length !== expected.length || !timingSafeEqual(given, expected)) {
    return json(res, 404, { error: 'not_found' });
  }
  const results = categories.map((category) => ({
    id: category.id,
    title: category.title,
    candidates: category.candidates
      .map((candidate) => ({
        name: candidate.name,
        votes: Object.values(votes).filter((v) => v[category.id] === candidate.id).length,
      }))
      .sort((a, b) => b.votes - a.votes),
  }));
  json(res, 200, { voters: Object.keys(votes).length, results });
}

async function serveStatic(req, res, pathname) {
  let relative;
  try {
    relative = pathname === '/' ? 'index.html' : decodeURIComponent(pathname).replace(/^\/+/, '');
  } catch {
    return json(res, 404, { error: 'not_found' });
  }
  const file = path.join(PUBLIC_DIR, relative);
  if (!file.startsWith(PUBLIC_DIR + path.sep)) return json(res, 404, { error: 'not_found' });
  try {
    const content = await readFile(file);
    res.writeHead(200, {
      'Content-Type': MIME[path.extname(file)] || 'application/octet-stream',
      'Cache-Control': 'no-cache',
      'X-Content-Type-Options': 'nosniff',
    });
    res.end(req.method === 'HEAD' ? undefined : content);
  } catch {
    json(res, 404, { error: 'not_found' });
  }
}

const server = createServer(async (req, res) => {
  try {
    const { pathname } = new URL(req.url, 'http://localhost');
    if (pathname === '/api/ballot' && req.method === 'GET') return getBallot(req, res);
    if (pathname === '/api/vote' && req.method === 'POST') return await postVote(req, res);
    if (pathname === '/api/results' && req.method === 'GET') return getResults(req, res);
    if (pathname.startsWith('/api/')) return json(res, 404, { error: 'not_found' });
    if (req.method !== 'GET' && req.method !== 'HEAD') return json(res, 405, { error: 'method_not_allowed' });
    await serveStatic(req, res, pathname);
  } catch (error) {
    console.error(error);
    if (!res.headersSent) json(res, 500, { error: 'server_error' });
    else res.end();
  }
});

server.listen(PORT, () => console.log(`Duumvirat Awards 2026: http://localhost:${PORT}`));
