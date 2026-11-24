// Interface texts come from the backend: GET /api/i18n/<lang> (files in resources/locales).
import { API_URL, DEFAULT_LANGUAGE, LANGUAGES } from "./config.js";

let texts = {};
let current = DEFAULT_LANGUAGE;

function guessLanguage() {
  const saved = localStorage.getItem("lang");
  if (LANGUAGES.includes(saved)) return saved;
  const browser = (navigator.language || "").slice(0, 2).toLowerCase();
  return LANGUAGES.includes(browser) ? browser : DEFAULT_LANGUAGE;
}

export async function loadLanguage(code = guessLanguage()) {
  const response = await fetch(`${API_URL}/api/i18n/${code}`);
  if (!response.ok) throw new Error(`Cannot load language ${code}`);
  texts = await response.json();
  current = code;
  localStorage.setItem("lang", code);
  document.documentElement.lang = code;
}

export function getLanguage() {
  return current;
}

/** t("cart.items_count", {count: 3}) -> "Товаров: 3". Unknown key -> the key itself. */
export function t(key, params = {}) {
  const value = key.split(".").reduce((node, part) => (node && typeof node === "object" ? node[part] : undefined), texts);
  if (typeof value !== "string") return key;
  return value.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}
