// Backend address. By default: the same host as the site, port 8000.
// Can be overridden for testing: localStorage.setItem("apiUrl", "http://...")
export const API_URL = localStorage.getItem("apiUrl") || `${location.protocol}//${location.hostname}:8000`;

export const LANGUAGES = ["ru", "en"];
export const DEFAULT_LANGUAGE = "ru";
