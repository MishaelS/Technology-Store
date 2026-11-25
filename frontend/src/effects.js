// Small visual effects shared by all pages. Everything is off when the user asks for reduced motion.
//  - ripple: a wave spreads from the click point inside buttons;
//  - reveal: blocks fade in and slide up when they scroll into view;
//  - countTo: a number counts up/down to its new value.

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

/** Wave from the click point inside buttons. One listener for the whole page. */
export function installRipple() {
  document.addEventListener(
    "pointerdown",
    (event) => {
      if (reducedMotion.matches || event.button !== 0) return;
      const target = event.target.closest("button, .btn, .more-link");
      if (!target || target.disabled) return;
      const box = target.getBoundingClientRect();
      const size = Math.hypot(box.width, box.height) * 2;
      const wave = document.createElement("span");
      wave.className = "ripple";
      wave.style.cssText = `left: ${event.clientX - box.left}px; top: ${event.clientY - box.top}px; width: ${size}px; height: ${size}px`;
      target.append(wave);
      setTimeout(() => wave.remove(), 600); // a timer, not animationend: it also fires in a background tab
    },
    { passive: true },
  );
}

// blocks of a page that appear while scrolling
const REVEAL = ".home-content > .section, .product-page > *, .build-summary";
let revealObserver = null;

/** Blocks below the screen start hidden and appear when they scroll into view. */
export function revealOnScroll(root) {
  revealObserver?.disconnect();
  if (reducedMotion.matches || !("IntersectionObserver" in window)) return;
  revealObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        entry.target.classList.add("revealed");
        revealObserver.unobserve(entry.target);
      }
    },
    { rootMargin: "0px 0px -8% 0px" },
  );
  for (const block of root.querySelectorAll(REVEAL)) {
    // what is already on screen is shown at once: no blank first screen
    if (block.getBoundingClientRect().top < window.innerHeight) continue;
    block.classList.add("reveal");
    revealObserver.observe(block);
  }
}

/** Counts the number in `node` from `from` to `to`; `format` turns a number into text. */
export function countTo(node, from, to, format = String, duration = 600) {
  if (reducedMotion.matches || from === to) {
    node.textContent = format(to);
    return;
  }
  const start = performance.now();
  const step = (now) => {
    const k = Math.min(1, (now - start) / duration);
    const eased = 1 - (1 - k) ** 3; // fast start, soft stop
    node.textContent = format(Math.round(from + (to - from) * eased));
    if (k < 1 && node.isConnected) requestAnimationFrame(step);
  };
  node.textContent = format(from);
  requestAnimationFrame(step);
}
