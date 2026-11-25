// All requests to the backend go through api(): token, language and errors in one place.
import { API_URL } from "./config.js";
import { getLanguage, t } from "./i18n.js";

export class ApiError extends Error {
  constructor(status, message, fields = []) {
    super(message);
    this.status = status;
    this.fields = fields; // [{field, message}] for 422
  }
}

export async function api(path, { method = "GET", body } = {}) {
  const headers = { "Accept-Language": getLanguage() };
  const token = localStorage.getItem("token");
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(API_URL + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, t("common.error"));
  }

  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && token) window.dispatchEvent(new Event("auth:expired"));
    let message = data?.detail;
    if (Array.isArray(message)) message = message.map((d) => d.msg).join("; "); // old FastAPI format
    throw new ApiError(response.status, message || t("common.error"), data?.fields || []);
  }
  return data;
}

/** Sends a file as the request body (POST /api/admin/uploads). Returns the JSON answer. */
export async function uploadFile(path, file) {
  const headers = { "Accept-Language": getLanguage(), "Content-Type": file.type || "application/octet-stream" };
  const token = localStorage.getItem("token");
  if (token) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(API_URL + path, { method: "POST", headers, body: file });
  } catch {
    throw new ApiError(0, t("common.error"));
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, data?.detail || t("common.error"));
  return data;
}

/** Build "?a=1&b=2" from an object, skipping empty values. */
export function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "" && value !== false) search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
