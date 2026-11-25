// Backend address. By default the site's own address: nginx passes /api/ on to the backend (nginx.conf),
// so the site also works through a tunnel or a forwarded port where only the site's port is open.
// Can be overridden for testing: localStorage.setItem("apiUrl", "http://localhost:8000")
export const API_URL = localStorage.getItem("apiUrl") || "";

export const LANGUAGES = ["ru", "en"];
export const DEFAULT_LANGUAGE = "ru";
