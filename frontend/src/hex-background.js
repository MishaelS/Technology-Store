// Background of the site: rows of hex bytes behind the page, like a memory dump (10 AA 2A D2 EC 00 ...).
//
// The bytes themselves stay as they are; only a wave changes them. At rest Perlin noise (always the same
// seed, so the picture is the same on every visit) sets the size and brightness of every byte: where the
// noise is higher, the byte is bigger and brighter. The noise slowly drifts from the top left corner to
// the bottom right one, so soft "clouds" of bigger bytes float over the screen.
// On every page change a wave runs from the click point: the bytes it passes light up and get new values,
// which they keep after the wave.
//
// Speed: one <canvas> fixed behind everything, drawn at a low resolution (RES) and stretched by the
// browser: that gives the soft, slightly blurred look for free (a CSS blur over the whole screen is
// expensive, on phones especially) and ~10x fewer pixels to fill. At rest it's redrawn only a few times
// a second and not at all while the page scrolls, so scrolling gets the whole frame; during a wave every frame. All 256 bytes are drawn once into a 16x16 sprite and copied with drawImage,
// much cheaper than fillText for thousands of cells. A hidden tab draws nothing (requestAnimationFrame
// stops). Reduced motion: one still picture, no drift and no waves.

const CELL_W = 30; // px per byte: two digits and the space after them
const CELL_H = 22; // px per line
const FONT_SIZE = 13;
const DIM = 0.04; // how visible a byte is where the noise is lowest
const BRIGHT = 0.15; // ... and where it is highest
const SMALL = 0.55; // size of a byte where the noise is lowest (1 = normal)
const BIG = 1.35; // ... and where it is highest
const PEAK = 0.55; // brightness added on the crest of the wave
const SPEED = 1.6; // px per ms the wave front moves
const BAND = 220; // px, width of the lit band
const COLOR = "59, 91, 219"; // --accent

const SEED = 20260515; // one seed forever: the same clouds every time
const SCALE = 260; // px per noise unit: bigger = larger clouds
const DRIFT = 14; // px per second the noise moves (to the bottom right)
const IDLE_FPS = 10; // redraws per second at rest: the drift is slow, more is wasted work
const IDLE_FPS_PHONE = 6; // phones: weaker, and the drift is hardly seen on a small screen
const RES = 0.6; // canvas pixels per CSS pixel, whatever the screen density
const SCROLL_PAUSE = 250; // ms after the last scroll before the rest-state drift goes on

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let canvas, ctx, sprite, ratio, cols, rows, bytes, alpha, size;
let wave = null; // {x, y, start, far} while a wave runs
let lastDraw = 0;
let scrollPause = 0; // until when the drift waits (the page is scrolling)
const phone = window.matchMedia("(max-width: 640px)");

// ---------- Perlin noise (2D, "improved" Perlin) ----------

/** Small seeded random generator (mulberry32): the same seed gives the same numbers. */
function seeded(seed) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let x = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

// permutation of 0..255 shuffled with the fixed seed, doubled to skip "& 255" on lookups
const PERM = (() => {
  const random = seeded(SEED);
  const p = Array.from({ length: 256 }, (_, i) => i);
  for (let i = 255; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [p[i], p[j]] = [p[j], p[i]];
  }
  return Uint8Array.from([...p, ...p]);
})();

const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10);
const lerp = (a, b, t) => a + (b - a) * t;
function grad(hash, x, y) {
  // 8 directions
  switch (hash & 7) {
    case 0: return x + y;
    case 1: return -x + y;
    case 2: return x - y;
    case 3: return -x - y;
    case 4: return x;
    case 5: return -x;
    case 6: return y;
    default: return -y;
  }
}

/** Perlin noise at (x, y), roughly -1..1. */
function perlin(x, y) {
  const xi = Math.floor(x), yi = Math.floor(y);
  const X = xi & 255, Y = yi & 255;
  const xf = x - xi, yf = y - yi;
  const u = fade(xf), v = fade(yf);
  const aa = PERM[PERM[X] + Y], ab = PERM[PERM[X] + Y + 1];
  const ba = PERM[PERM[X + 1] + Y], bb = PERM[PERM[X + 1] + Y + 1];
  return lerp(
    lerp(grad(aa, xf, yf), grad(ba, xf - 1, yf), u),
    lerp(grad(ab, xf, yf - 1), grad(bb, xf - 1, yf - 1), u),
    v,
  );
}

/** Noise as 0..1: two octaves, big clouds with some detail; contrast pushed a bit. */
function noise01(x, y) {
  const n = perlin(x, y) * 0.75 + perlin(x * 2.3 + 17.1, y * 2.3 + 5.7) * 0.25;
  return Math.min(1, Math.max(0, n * 1.25 + 0.5));
}

// ---------- canvas ----------

/** Puts the canvas behind the page. Call once at start. */
export function installHexBackground() {
  canvas = document.createElement("canvas");
  canvas.id = "hex-bg";
  canvas.setAttribute("aria-hidden", "true");
  document.body.prepend(canvas);
  ctx = canvas.getContext("2d");
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(setup, 150);
  });
  setup();
  if (reducedMotion.matches) return;
  window.addEventListener("scroll", () => (scrollPause = performance.now() + SCROLL_PAUSE), { passive: true });
  hexWave(window.innerWidth / 2, 0); // a first wave from the top when the site opens
  requestAnimationFrame(loop);
}

function setup() {
  ratio = RES;
  canvas.width = Math.ceil(window.innerWidth * ratio);
  canvas.height = Math.ceil(window.innerHeight * ratio);
  cols = Math.ceil(window.innerWidth / CELL_W) + 1;
  rows = Math.ceil(window.innerHeight / CELL_H) + 1;
  // the starting bytes come from the same seed too; after that only waves change them
  const random = seeded(SEED + 1);
  bytes = Uint8Array.from({ length: cols * rows }, () => (random() * 256) | 0);
  alpha = new Float32Array(cols * rows);
  size = new Float32Array(cols * rows);
  makeSprite();
  update(performance.now());
  draw();
}

/** All bytes 00..FF in a 16x16 grid, in the accent color. Drawn as big as the biggest byte,
 *  so enlarged bytes stay sharp. */
function makeSprite() {
  const w = CELL_W * ratio * BIG, h = CELL_H * ratio * BIG;
  sprite = document.createElement("canvas");
  sprite.width = w * 16;
  sprite.height = h * 16;
  const s = sprite.getContext("2d");
  s.font = `600 ${FONT_SIZE * ratio * BIG}px "JetBrains Mono", ui-monospace, Menlo, monospace`;
  s.textAlign = "center";
  s.textBaseline = "middle";
  s.fillStyle = `rgb(${COLOR})`;
  for (let b = 0; b < 256; b++) {
    s.fillText(b.toString(16).toUpperCase().padStart(2, "0"), (b % 16) * w + w / 2, Math.floor(b / 16) * h + h / 2);
  }
}

/** Size and brightness of every byte at the moment `now` from the noise; new bytes under the wave. */
function update(now) {
  // the field moves to the bottom right, so we look at it from a point moving to the top left
  const shift = reducedMotion.matches ? 0 : (now / 1000) * DRIFT;
  const front = wave ? (now - wave.start) * SPEED : 0;
  for (let r = 0; r < rows; r++) {
    const cy = r * CELL_H + CELL_H / 2;
    for (let c = 0; c < cols; c++) {
      const i = r * cols + c;
      const cx = c * CELL_W + CELL_W / 2;
      const n = noise01((cx - shift) / SCALE, (cy - shift) / SCALE);
      let lit = 0;
      if (wave) {
        const behind = front - Math.hypot(cx - wave.x, cy - wave.y); // px behind the front
        if (behind > 0 && behind < BAND) lit = Math.sin((Math.PI * behind) / BAND);
      }
      // only the crest of the wave changes the bytes; they keep the new values after it
      if (lit > 0.5 && Math.random() < 0.35) bytes[i] = (Math.random() * 256) | 0;
      size[i] = SMALL + (BIG - SMALL) * n + 0.25 * lit; // the wave also swells them a little
      alpha[i] = DIM + (BRIGHT - DIM) * n * n + PEAK * lit; // n² keeps the low parts really quiet
    }
  }
  if (wave && front > wave.far) wave = null;
}

function draw() {
  const w = CELL_W * ratio, h = CELL_H * ratio; // a cell on the screen
  const sw = w * BIG, sh = h * BIG; // a byte in the sprite
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const i = r * cols + c;
      const b = bytes[i];
      const dw = w * size[i], dh = h * size[i]; // grows or shrinks around the middle of its cell
      ctx.globalAlpha = Math.min(1, alpha[i]);
      ctx.drawImage(sprite, (b % 16) * sw, Math.floor(b / 16) * sh, sw, sh,
        c * w + (w - dw) / 2, r * h + (h - dh) / 2, dw, dh);
    }
  }
  ctx.globalAlpha = 1;
}

function loop(now) {
  // at rest a few frames a second are enough for the slow drift, and none while the page scrolls;
  // a wave gets every frame
  const idleStep = 1000 / (phone.matches ? IDLE_FPS_PHONE : IDLE_FPS);
  if (wave || (now >= scrollPause && now - lastDraw >= idleStep)) {
    lastDraw = now;
    update(now);
    draw();
  }
  requestAnimationFrame(loop);
}

/** A wave over the bytes from the point (x, y) of the screen. */
export function hexWave(x, y) {
  if (!canvas || reducedMotion.matches || document.hidden) return;
  const far = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y)) + BAND;
  wave = { x, y, start: performance.now(), far };
}
