// Custom dropdown in the site's style for every <select> on the page.
//
// The native <select> stays in the page, hidden: forms still read its value and pages keep
// listening to its "change" event, so page code doesn't need to know about this component.
// Keyboard: arrows, Home/End, Enter/Space to pick, Esc to close, a letter jumps to an option.

let openDropdown = null; // the one dropdown that is open right now
let counter = 0;

export function watchSelects(root = document.body) {
  enhanceAll(root);
  new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) continue;
        if (node.matches("select")) enhance(node);
        else enhanceAll(node);
      }
    }
  }).observe(root, { childList: true, subtree: true });

  document.addEventListener("pointerdown", (event) => {
    if (openDropdown && !openDropdown.wrap.contains(event.target)) openDropdown.close(false);
  });
}

function enhanceAll(root) {
  root.querySelectorAll("select:not([data-dropdown])").forEach(enhance);
}

/** Name for screen readers: aria-label, or the text of the <label> around/for the select. */
function accessibleName(select) {
  if (select.getAttribute("aria-label")) return select.getAttribute("aria-label");
  const label = select.labels?.[0];
  if (!label) return select.name || "";
  const copy = label.cloneNode(true);
  copy.querySelectorAll("select, .dropdown").forEach((el) => el.remove());
  return copy.textContent.trim();
}

function el(tag, className, attrs = {}) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

function enhance(select) {
  if (select.dataset.dropdown || select.multiple) return;
  select.dataset.dropdown = "on";

  const id = `dropdown-${++counter}`;
  const wrap = el("span", "dropdown");
  if (select.getAttribute("style")) wrap.setAttribute("style", select.getAttribute("style"));
  const button = el("button", "dropdown-button", { type: "button", "aria-haspopup": "listbox", "aria-expanded": "false", "aria-controls": id });
  const label = el("span", "dropdown-label");
  const chevron = el("span", "icon dropdown-chevron", { "aria-hidden": "true" });
  chevron.style.setProperty("--m", "url(/resources/icons/navigation/chevron-down.svg)");
  button.append(label, chevron);
  const list = el("ul", "dropdown-list", { id, role: "listbox", tabindex: "-1" });
  list.hidden = true;

  select.replaceWith(wrap);
  select.classList.add("dropdown-native");
  select.tabIndex = -1;
  select.setAttribute("aria-hidden", "true");
  wrap.append(select, button, list);

  let active = -1; // highlighted option while the list is open
  let closeTimer = null;
  let typed = "";
  let typedTimer = null;

  function options() {
    return Array.from(select.options);
  }

  function sync() {
    const current = select.options[select.selectedIndex];
    label.textContent = current ? current.textContent : "";
    button.disabled = select.disabled;
    const name = accessibleName(select);
    button.setAttribute("aria-label", name ? `${name}: ${label.textContent}` : label.textContent);
  }

  function render() {
    list.replaceChildren(...options().map((option, index) => {
      const item = el("li", "", {
        id: `${id}-${index}`,
        role: "option",
        "aria-selected": String(index === select.selectedIndex),
      });
      if (option.disabled) item.setAttribute("aria-disabled", "true");
      item.textContent = option.textContent;
      item.addEventListener("pointerenter", () => highlight(index, false));
      item.addEventListener("click", () => choose(index));
      return item;
    }));
  }

  function highlight(index, scroll = true) {
    const items = list.children;
    if (!items.length) return;
    active = Math.max(0, Math.min(index, items.length - 1));
    for (const [i, item] of Array.from(items).entries()) item.classList.toggle("active", i === active);
    list.setAttribute("aria-activedescendant", `${id}-${active}`);
    if (scroll) items[active].scrollIntoView({ block: "nearest" });
  }

  function step(from, direction) {
    const all = options();
    for (let i = from + direction; i >= 0 && i < all.length; i += direction) {
      if (!all[i].disabled) return i;
    }
    return from;
  }

  function open() {
    if (select.disabled) return;
    if (openDropdown && openDropdown !== api) openDropdown.close(false);
    clearTimeout(closeTimer);
    sync();
    render();
    list.hidden = false;
    // next frame, so the slide-in transition runs from the closed state
    requestAnimationFrame(() => wrap.classList.add("open"));
    button.setAttribute("aria-expanded", "true");
    openDropdown = api;
    highlight(select.selectedIndex >= 0 ? select.selectedIndex : 0);
    list.focus({ preventScroll: true });
  }

  function close(focusButton = true) {
    wrap.classList.remove("open");
    button.setAttribute("aria-expanded", "false");
    list.removeAttribute("aria-activedescendant");
    closeTimer = setTimeout(() => (list.hidden = true), 160);
    if (openDropdown === api) openDropdown = null;
    if (focusButton) button.focus({ preventScroll: true });
  }

  function choose(index) {
    const option = select.options[index];
    if (!option || option.disabled) return;
    const changed = select.selectedIndex !== index;
    select.selectedIndex = index;
    sync();
    close();
    if (changed) {
      select.dispatchEvent(new Event("input", { bubbles: true }));
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }

  function typeAhead(char) {
    clearTimeout(typedTimer);
    typed += char.toLowerCase();
    typedTimer = setTimeout(() => (typed = ""), 600);
    const found = options().findIndex((o) => !o.disabled && o.textContent.trim().toLowerCase().startsWith(typed));
    if (found >= 0) highlight(found);
  }

  button.addEventListener("click", () => (wrap.classList.contains("open") ? close() : open()));
  button.addEventListener("keydown", (event) => {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
      event.preventDefault();
      open();
    }
  });

  list.addEventListener("keydown", (event) => {
    const keys = {
      ArrowDown: () => highlight(step(active, 1)),
      ArrowUp: () => highlight(step(active, -1)),
      Home: () => highlight(step(-1, 1)),
      End: () => highlight(step(select.options.length, -1)),
      Enter: () => choose(active),
      " ": () => choose(active),
      Escape: () => close(),
      Tab: () => close(false),
    };
    if (keys[event.key]) {
      if (event.key !== "Tab") event.preventDefault();
      keys[event.key]();
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
      typeAhead(event.key);
    }
  });

  // options or "disabled" changed by page code, or a change made without our component
  new MutationObserver(sync).observe(select, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"] });
  select.addEventListener("change", sync);

  const api = { wrap, close };
  sync();
}
