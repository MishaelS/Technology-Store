// Small helpers to build the page. Text is always inserted as text (never as HTML),
// so data from the API can't inject scripts.
import { getLanguage, t } from "./i18n.js";

/** h("a", {href: "#/", class: "x", onclick: fn}, "text", otherNode) */
export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on")) element.addEventListener(key.slice(2), value);
    else if (key === "class") element.className = value;
    else if (key in element && key !== "list") element[key] = value;
    else element.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return element;
}

export function link(path, ...children) {
  return h("a", { href: `#${path}` }, ...children);
}

/** "Show all" link with an arrow, for the right side of a section title. */
export function moreLink(path, text) {
  return h("a", { href: `#${path}`, class: "more-link" }, text, icon("navigation/arrow-right"));
}

export function money(amount) {
  return t("common.price", { amount: Number(amount).toLocaleString(getLanguage()) });
}

export function date(iso) {
  return new Date(iso).toLocaleString(getLanguage(), { dateStyle: "short", timeStyle: "short" });
}

/** Only http(s) links or paths on the site (the backend checks this too). */
export function image(url, alt = "") {
  if (!url || !(/^https?:\/\//.test(url) || url.startsWith("/"))) return null;
  return h("img", { src: url, alt, loading: "lazy", decoding: "async" });
}

/** Icon from resources/icons: icon("navigation/cart").
 *  Drawn as a mask, so it takes the text color (`color: ...`) like the design wants.
 *  Without a label it is hidden from screen readers. */
export function icon(name, label = "") {
  return h("span", {
    class: "icon",
    style: `--m: url(/resources/icons/${name}.svg)`,
    role: label ? "img" : null,
    "aria-label": label || null,
    "aria-hidden": label ? null : "true",
  });
}

export function navigate(path) {
  location.hash = path;
}

let flashTimer;
/** Short message at the top of the page. */
export function flash(message, kind = "") {
  const box = document.getElementById("flash");
  box.className = kind;
  box.textContent = message;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => (box.textContent = ""), 5000);
}

/** Error from api() inside a form: text + list of bad fields. */
export function errorBox(error) {
  return h(
    "div",
    { class: "error" },
    error.message,
    error.fields?.length ? h("ul", {}, error.fields.map((f) => h("li", {}, `${f.field}: ${f.message}`))) : null,
  );
}

/** Run an async action, show its error next to `place` (or in flash). */
export async function attempt(action, place) {
  try {
    return await action();
  } catch (error) {
    if (place) place.replaceChildren(errorBox(error));
    else flash(error.message, "error");
    return undefined;
  }
}

export function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

export function field(label, input) {
  return h("label", {}, label, input);
}

export function select(name, options, value) {
  return h(
    "select",
    { name },
    options.map(([optionValue, text]) => h("option", { value: optionValue, selected: String(optionValue) === String(value ?? "") }, text)),
  );
}

/** Grey placeholders in the shape of cards, shown while the real cards load. kind: "product" | "news". */
export function skeletons(kind, count) {
  const bone = (extra = "") => h("span", { class: `bone ${extra}` });
  const card = () =>
    kind === "news"
      ? h("div", { class: "skeleton news-skeleton" }, bone("short"), bone("title"), bone(), bone(), bone("half"))
      : h("div", { class: "skeleton product-skeleton" }, bone("thumb"), bone("short"), bone("title"), bone("half"),
          h("div", { class: "skeleton-foot" }, bone("price"), bone("button")));
  return Array.from({ length: count }, card);
}

/** First page of the site while it loads: a title bar and a few cards. Screen readers hear "Loading…". */
export function loading() {
  return h(
    "div",
    { class: "page-skeleton", role: "status", "aria-label": t("common.loading") },
    h("span", { class: "bone heading" }),
    h("div", { class: "grid", "aria-hidden": "true" }, skeletons("product", 4)),
  );
}
