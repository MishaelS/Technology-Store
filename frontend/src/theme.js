// Light or dark theme of the site.
// The choice is kept in the browser; until the user picks one, the site follows the system theme.
// The theme is the data-theme attribute of <html>: style.css has a second set of color variables for it.
// index.html sets it before the page is drawn, so a dark page never flashes white.

const KEY = "theme";
const system = window.matchMedia("(prefers-color-scheme: dark)");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

export function currentTheme() {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function saved() {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function apply(theme) {
  document.documentElement.dataset.theme = theme;
  window.dispatchEvent(new Event("theme:change")); // the header icon and the hex background follow
}

/** Follow the system theme while the user hasn't chosen one. Call once at start. */
export function watchSystemTheme() {
  system.addEventListener("change", () => {
    if (!saved()) apply(system.matches ? "dark" : "light");
  });
}

/** Switches the theme; the new one opens as a circle from the point (x, y), e.g. the switch button. */
export function toggleTheme(x = window.innerWidth, y = 0) {
  const next = currentTheme() === "dark" ? "light" : "dark";
  try {
    localStorage.setItem(KEY, next);
  } catch {
    /* not remembered, still switches */
  }
  if (!document.startViewTransition || reducedMotion.matches) return apply(next);
  const root = document.documentElement;
  root.style.setProperty("--theme-x", `${x}px`);
  root.style.setProperty("--theme-y", `${y}px`);
  root.style.setProperty("--theme-r", `${Math.ceil(Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y)))}px`);
  root.classList.add("theme-switching");
  let applied = false;
  const applyOnce = () => {
    if (applied) return;
    applied = true;
    apply(next);
  };
  const transition = document.startViewTransition(applyOnce);
  transition.finished.finally(() => root.classList.remove("theme-switching"));
  // the browser waits for a frame to start; a page that isn't drawn (a background tab) must still switch
  setTimeout(() => {
    if (applied) return;
    transition.skipTransition();
    applyOnce();
  }, 1000);
}
