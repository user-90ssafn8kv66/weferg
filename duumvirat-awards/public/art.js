// Original faceted-crystal artwork, built from polygons that share the
// gradients defined once in index.html (#g-light … #g-deep).
const SHADE = ['url(#g-light)', 'url(#g-mid)', 'url(#g-dark)', 'url(#g-deep)'];
const INK = '#030a24';

const pts = (points) => points.map(([x, y]) => `${x},${y}`).join(' ');
const poly = (points, fill, extra = '') => `<polygon points="${pts(points)}" fill="${fill}" ${extra}/>`;

// A shard standing on (x, y), growing upward by h, rotated around its base.
function crystal(x, y, w, h, rot = 0) {
  const r = w * 0.12;
  const s = -h * 0.72;
  return `<g transform="translate(${x} ${y}) rotate(${rot})">${
    poly([[-0.28 * w, 0], [-0.5 * w, s], [r, -h * 0.66], [r * 0.6, 0]], SHADE[1]) +
    poly([[r * 0.6, 0], [r, -h * 0.66], [0.5 * w, s], [0.28 * w, 0]], SHADE[3]) +
    poly([[-0.5 * w, s], [0, -h], [r, -h * 0.66]], SHADE[0]) +
    poly([[r, -h * 0.66], [0, -h], [0.5 * w, s]], SHADE[2]) +
    poly([[-0.5 * w, s], [-0.4 * w, s * 0.96], [-0.22 * w, 0], [-0.28 * w, 0]], '#fff', 'opacity="0.45"')
  }</g>`;
}

// Triangles from a centre point to each edge of an outline.
function fan(cx, cy, outline, shades) {
  return outline
    .map((point, i) => poly([[cx, cy], point, outline[(i + 1) % outline.length]], SHADE[shades[i % shades.length]]))
    .join('');
}

function bar(x1, x2, y, h) {
  const m = y + h * 0.45;
  return (
    poly([[x1, y], [x2, y], [x2 - 5, m], [x1 + 5, m]], SHADE[0]) +
    poly([[x1 + 5, m], [x2 - 5, m], [x2 - 12, y + h], [x1 + 12, y + h]], SHADE[2])
  );
}

const diamond = (x, y, rx, ry, fill) => poly([[x, y - ry], [x + rx, y], [x, y + ry], [x - rx, y]], fill);

const ICONS = {
  crown: () =>
    crystal(-52, -18, 26, 80, -40) + crystal(52, -18, 26, 80, 40) +
    crystal(-26, -20, 30, 100, -20) + crystal(26, -20, 30, 100, 20) +
    crystal(0, -22, 34, 118) +
    bar(-76, -5, -16, 22) + bar(5, 76, -16, 22),

  tiara: () =>
    crystal(-66, -8, 18, 46, -28) + crystal(66, -8, 18, 46, 28) +
    crystal(-36, -14, 24, 74, -14) + crystal(36, -14, 24, 74, 14) +
    crystal(0, -18, 34, 122) +
    poly([[-90, 2], [-4, -22], [-4, -12], [-86, 9]], SHADE[0]) +
    poly([[-86, 9], [-4, -12], [-4, -4], [-80, 16]], SHADE[2]) +
    poly([[90, 2], [4, -22], [4, -12], [86, 9]], SHADE[1]) +
    poly([[86, 9], [4, -12], [4, -4], [80, 16]], SHADE[3]) +
    diamond(0, -2, 11, 14, SHADE[0]),

  heart: () =>
    fan(0, -64, [
      [0, 4], [-56, -52], [-64, -84], [-48, -110], [-22, -114], [0, -94],
      [22, -114], [48, -110], [64, -84], [56, -52],
    ], [1, 0, 0, 1, 2, 1, 2, 3, 3, 2]),

  bolt: () =>
    fan(2, -68, [
      [10, -138], [38, -138], [14, -82], [46, -82], [-24, 6], [-6, -56], [-42, -56],
    ], [0, 2, 1, 3, 1, 2, 0]),

  crosshair: () =>
    '<circle cx="0" cy="-68" r="36" fill="none" stroke="url(#g-mid)" stroke-width="9"/>' +
    '<circle cx="0" cy="-68" r="39" fill="none" stroke="#fff" stroke-width="1.2" opacity="0.4"/>' +
    crystal(0, -142, 24, 52, 180) + crystal(0, 6, 24, 52) +
    crystal(-74, -68, 24, 52, 90) + crystal(74, -68, 24, 52, -90) +
    diamond(0, -68, 7, 7, SHADE[0]),

  sword: () =>
    crystal(0, -36, 32, 112) +
    poly([[-46, -42], [46, -42], [36, -34], [-36, -34]], SHADE[0]) +
    poly([[-36, -34], [36, -34], [28, -26], [-28, -26]], SHADE[2]) +
    poly([[-6, -26], [6, -26], [5, -4], [-5, -4]], SHADE[3]) +
    diamond(0, 4, 11, 11, SHADE[0]),

  mask: () =>
    fan(0, -68, [[0, -128], [52, -98], [52, -38], [0, -8], [-52, -38], [-52, -98]], [1, 2, 3, 2, 1, 0]) +
    diamond(-20, -84, 8, 12, INK) + diamond(20, -84, 8, 12, INK) +
    poly([[-30, -56], [30, -56], [15, -34], [-15, -34]], INK),

  star: () =>
    fan(0, -68, [
      [0, -140], [15, -83], [64, -68], [15, -53], [0, 4], [-15, -53], [-64, -68], [-15, -83],
    ], [1, 2, 3, 2, 1, 0, 0, 1]) +
    fan(62, -122, [[62, -138], [66, -126], [78, -122], [66, -118], [62, -106], [58, -118], [46, -122], [58, -126]], [0]) +
    fan(-56, -22, [[-56, -34], [-53, -25], [-44, -22], [-53, -19], [-56, -10], [-59, -19], [-68, -22], [-59, -25]], [0]),

  gem: () => crystal(-24, -4, 28, 84, -16) + crystal(24, -4, 28, 90, 16) + crystal(0, 0, 36, 128),
};

export function icon(name) {
  const draw = ICONS[name] || ICONS.gem;
  return `<svg viewBox="-115 -150 230 175" aria-hidden="true" focusable="false">${draw()}</svg>`;
}

export function heroCrystals() {
  return (
    crystal(-190, 10, 70, 210, -42) + crystal(190, 10, 70, 220, 41) +
    crystal(-120, 14, 84, 300, -24) + crystal(124, 14, 84, 310, 23) +
    crystal(0, 0, 100, 540) +
    crystal(-58, 20, 70, 250, -9) + crystal(62, 20, 72, 270, 10)
  );
}
