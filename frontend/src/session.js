// Logged-in user and what they are allowed to see.
// Permissions come from the API (user.permissions): the frontend only HIDES things,
// the backend still checks every request.
import { api } from "./api.js";

export const session = { user: null, cartCount: 0 };

export function can(permission) {
  return Boolean(session.user?.permissions?.includes(permission));
}

export function isLoggedIn() {
  return session.user !== null;
}

export function saveLogin({ token, user }) {
  localStorage.setItem("token", token);
  session.user = user;
}

export function logout() {
  localStorage.removeItem("token");
  session.user = null;
  session.cartCount = 0;
}

export async function loadUser() {
  if (!localStorage.getItem("token")) return logout();
  try {
    session.user = await api("/api/auth/me");
  } catch {
    logout();
  }
}

export async function refreshCartCount() {
  session.cartCount = isLoggedIn() ? (await api("/api/cart")).count : 0;
}
