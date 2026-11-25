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

/**
 * Field with its name inside: grey text in the empty field that moves up and shrinks
 * when the user types or picks something (a "floating label"), so no line of text above every field.
 * `input` can be the control itself or a wrapper with it (and a hint under it).
 */
export function field(label, input) {
  const control = input.matches?.("input, textarea, select") ? input : input.querySelector?.("input, textarea, select");
  if (!control || ["checkbox", "radio"].includes(control.type)) return h("label", {}, label, input);
  // :placeholder-shown tells CSS the field is empty; a real placeholder only shows once the field is focused
  if (control.tagName !== "SELECT" && !control.placeholder) control.placeholder = " ";
  const kind = control.tagName === "SELECT" ? " is-select" : control.tagName === "TEXTAREA" ? " is-textarea" : "";
  return h("label", { class: `float-field${kind}` }, input, h("span", { class: "float-label" }, label));
}

export function select(name, options, value) {
  return h(
    "select",
    { name },
    options.map(([optionValue, text]) => h("option", { value: optionValue, selected: String(optionValue) === String(value ?? "") }, text)),
  );
}

/** First letters of the first two words of the name: "Пётр Покупатель" -> "ПП". */
export function initials(name) {
  const words = String(name || "").trim().split(/\s+/).filter(Boolean);
  return (words.slice(0, 2).map((w) => w[0]).join("") || "?").toUpperCase();
}

// soft colors for circles with initials; a user always gets the same one (by id)
const AVATAR_COLORS = ["#3B5BDB", "#0C8599", "#7048E8", "#E8590C", "#2B8A3E", "#C2255C", "#1971C2", "#E67700"];

/** Round avatar: the user's photo, or the initials on a color. `size` is "" (header) or "big". */
export function avatar(user, size = "") {
  const cls = `avatar${size ? ` ${size}` : ""}`;
  const photo = image(user.avatar_url, "");
  if (photo) return h("span", { class: cls }, photo);
  return h("span", { class: `${cls} initials`, style: `--avatar-color: ${AVATAR_COLORS[(user.id || 0) % AVATAR_COLORS.length]}` }, initials(user.name));
}

/** "Nothing here yet" block: an icon, a line of text and an optional button (path, text). */
export function emptyState(iconName, text, action = null) {
  return h(
    "div",
    { class: "empty-state" },
    h("span", { class: "empty-icon" }, icon(iconName)),
    h("p", {}, text),
    action ? h("a", { href: `#${action[0]}`, class: "btn primary" }, action[1], icon("navigation/arrow-right")) : null,
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
