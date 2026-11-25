// Infinite scroll: loads the next chunk when the end of the list comes into view.
// Works with API lists that return {items, next_cursor, total}.
import { t } from "./i18n.js";
import { h, icon } from "./ui.js";

/**
 * @param container   element to append items to
 * @param fetchPage   async (cursor) => {items, next_cursor, total}
 * @param renderItem  (item) => Node
 * @param state       optional saved state {items, cursor, done, total} to continue from
 * @param onTotal     called with the total count
 * @param endText     text under a finished list (default: about products)
 * @param skeleton    () => Node[]: placeholders shown in the list while the next chunk loads
 * @returns {{state, destroy}}
 */
export function infiniteList({ container, fetchPage, renderItem, state, onTotal, endText = t("catalog.end_of_list"), skeleton }) {
  state = state || { items: [], cursor: null, done: false, total: null };
  const status = h("p", { class: "muted" });
  const sentinel = h("div", { style: "height: 1px" });
  container.after(status, sentinel);

  let busy = false;
  let destroyed = false;

  for (const item of state.items) container.append(renderItem(item));
  if (state.total !== null) onTotal?.(state.total);

  async function loadMore() {
    if (busy || state.done || destroyed) return;
    busy = true;
    // placeholder cards where the next ones will appear; the text stays for screen readers only
    const placeholders = skeleton?.() || [];
    for (const node of placeholders) node.setAttribute("aria-hidden", "true");
    container.append(...placeholders);
    container.setAttribute("aria-busy", "true");
    status.textContent = placeholders.length ? "" : t("common.loading");
    try {
      const page = await fetchPage(state.cursor);
      if (destroyed) return;
      for (const item of page.items) {
        state.items.push(item);
        container.append(renderItem(item));
      }
      state.cursor = page.next_cursor;
      state.done = page.next_cursor === null;
      if (page.total !== undefined && page.total !== null) {
        state.total = page.total;
        onTotal?.(page.total);
      }
      status.textContent = state.done ? (state.items.length ? endText : t("catalog.empty")) : "";
    } catch (error) {
      status.replaceChildren(h("span", { class: "error" }, error.message), " ",
        h("button", { onclick: () => loadMore() }, t("common.retry")));
    } finally {
      busy = false;
      for (const node of placeholders) node.remove();
      container.removeAttribute("aria-busy");
    }
    // the screen may still not be full: keep loading
    if (nearEnd()) loadMore();
  }

  function nearEnd() {
    return !state.done && sentinel.isConnected && sentinel.getBoundingClientRect().top < window.innerHeight + 300;
  }

  const observer = new IntersectionObserver((entries) => entries[0].isIntersecting && loadMore(), {
    rootMargin: "300px",
  });
  observer.observe(sentinel);
  // backup for browsers/tabs where IntersectionObserver doesn't fire (e.g. a hidden tab)
  // checked at most once per frame: getBoundingClientRect on every scroll event makes scrolling stutter
  let queued = false;
  const onScroll = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      if (nearEnd()) loadMore();
    });
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  if (!state.items.length) loadMore();
  else status.textContent = state.done ? endText : "";

  return {
    state,
    destroy() {
      destroyed = true;
      observer.disconnect();
      window.removeEventListener("scroll", onScroll);
    },
  };
}

/** "Back to top" button, shown after scrolling two screens down. Returns a cleanup function. */
export function toTopButton() {
  const button = h("button", { id: "to-top", type: "button", onclick: () => window.scrollTo({ top: 0, behavior: "smooth" }) },
    icon("navigation/arrow-up"), t("common.to_top"));
  document.body.append(button);
  let shown = false;
  let queued = false;
  const onScroll = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      const show = window.scrollY > window.innerHeight * 2;
      if (show !== shown) button.classList.toggle("show", (shown = show)); // touch the DOM only on change
    });
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  return () => {
    window.removeEventListener("scroll", onScroll);
    button.remove();
  };
}
