// Our own image loader: every picture of the site goes through it (image() in ui.js).
//
//  - Size for the place: cards, the cart, the builder and thumbnails get the small copy (NN-sm.webp,
//    480x360, ~9 KB), the product page the big photo. No small copy: the big one; nothing loads: a placeholder.
//  - Starts early: a picture starts loading when it is still 800 px away from the screen.
//  - A queue with priority: at most MAX_PARALLEL pictures load at once, the ones nearest to the screen first,
//    so pictures far below don't take the network from the ones you are looking at.
//  - Decoded before shown: the picture appears with a short fade, without a jerk in the scroll.
//    While it loads, its frame shows a light shimmer (style.css, .img-pending).
//  - Remembers: a picture loaded once shows at once next time (no fade, no waiting).
//  - preload(): pictures you are about to need (the other photos of a card under the mouse,
//    the big photo of the product page before the click).

const MAX_PARALLEL = 6;
const AHEAD = "800px"; // how far before the screen a picture starts loading
const PLACEHOLDER = "/resources/demo/placeholder.svg"; // nothing could be loaded

const ready = new Set(); // urls already loaded and decoded
const inflight = new Map(); // url -> Promise of loading
const queue = []; // {url, priority, start}
let running = 0;

/** The small copy of a picture, if the site makes one for it; otherwise the picture itself. */
export function smallUrl(url) {
  if (!url) return url;
  // prepared product photos (scripts/prepare_product_photos.py) and uploads (routers/uploads.py)
  if (/^\/resources\/photos\/web\/(.+\/\d+|hero-build)\.webp$/.test(url) || /^\/uploads\/(avatars\/)?[0-9a-f]+\.(png|jpe?g|webp|gif)$/.test(url)) {
    return url.replace(/\.(png|jpe?g|webp|gif)$/, "-sm.webp");
  }
  return url;
}

function pump() {
  while (running < MAX_PARALLEL && queue.length) {
    queue.sort((a, b) => a.priority - b.priority); // the smallest number: the nearest to the screen
    const job = queue.shift();
    running++;
    job.start().finally(() => {
      running--;
      pump();
    });
  }
}

/** Loads and decodes a picture once; priority 0 = needed right now, bigger = can wait. */
export function preload(url, priority = 5) {
  if (!url || ready.has(url)) return Promise.resolve(url);
  if (inflight.has(url)) {
    const waiting = queue.find((job) => job.url === url);
    if (waiting) waiting.priority = Math.min(waiting.priority, priority); // now needed sooner
    return inflight.get(url);
  }
  const promise = new Promise((resolve, reject) => {
    queue.push({
      url,
      priority,
      start: () => {
        const img = new Image();
        img.decoding = "async";
        img.src = url;
        return img.decode().then(
          () => {
            ready.add(url);
            resolve(url);
          },
          (error) => reject(error),
        );
      },
    });
    pump();
  });
  inflight.set(url, promise);
  promise.catch(() => {}).finally(() => inflight.delete(url));
  return promise;
}

// one observer for all pictures: starts loading what comes near the screen, nearest first
const observer = "IntersectionObserver" in window
  ? new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        observer.unobserve(entry.target);
        const distance = Math.max(0, entry.boundingClientRect.top - window.innerHeight);
        show(entry.target, Math.round(distance / 200)); // on screen: 0, a screen below: ~4
      }
    }, { rootMargin: `${AHEAD} 0px` })
  : null;

/** Loads the picture of an <img> made by picture() and shows it; tries the fallbacks on errors. */
function show(img, priority) {
  const tries = JSON.parse(img.dataset.tries);
  const next = () => {
    const url = tries.shift();
    if (!url) {
      img.remove(); // nothing to show
      return;
    }
    preload(url, priority).then(
      () => {
        img.src = url;
        img.classList.remove("img-pending");
      },
      next, // this one failed: the next one (big photo, then the placeholder)
    );
  };
  next();
}

/**
 * <img> that the loader fills. size: "small" (cards, lists) or "full" (product page).
 * Already loaded pictures are set at once; the others wait for their turn.
 */
export function picture(url, alt = "", size = "small", { placeholder = true } = {}) {
  const first = size === "small" ? smallUrl(url) : url;
  // placeholder: false — nothing loaded means no picture at all (what's under it stays visible)
  const tries = [...new Set([first, url, ...(placeholder ? [PLACEHOLDER] : [])])];
  const img = document.createElement("img");
  img.alt = alt;
  img.decoding = "async";
  img.draggable = false;
  if (ready.has(first)) {
    img.src = first;
    return img;
  }
  img.classList.add("img-pending");
  img.dataset.tries = JSON.stringify(tries);
  if (observer) observer.observe(img);
  else show(img, 0);
  return img;
}
