// Entry point: header, routing (#/path?query) and page rendering.
import { LANGUAGES } from "./config.js";
import { getLanguage, loadLanguage, t } from "./i18n.js";
import { accountPage } from "./pages/account.js";
import { adminPage } from "./pages/admin.js";
import { loginPage, registerPage } from "./pages/auth.js";
import { builderPage } from "./pages/builder.js";
import { cartPage } from "./pages/cart.js";
import { catalogPage } from "./pages/catalog.js";
import { homePage } from "./pages/home.js";
import { newsPage } from "./pages/news.js";
import { productPage } from "./pages/product.js";
import { runAfter, runLeave } from "./router.js";
import { can, isLoggedIn, loadUser, logout, refreshCartCount, session } from "./session.js";
import { flash, h, link, loading, navigate } from "./ui.js";

// [path pattern, page, access rule]
const ROUTES = [
  ["/", homePage],
  ["/catalog", catalogPage],
  ["/product/:id", productPage],
  ["/news", newsPage],
  ["/builder", builderPage],
  ["/login", loginPage],
  ["/register", registerPage],
  ["/cart", cartPage, { login: true }],
  ["/account", accountPage, { login: true }],
  ["/admin", adminPage, { permission: "admin.access" }],
];

function parseHash() {
  const [path, search = ""] = (location.hash.slice(1) || "/").split("?");
  return { parts: path.split("/").filter(Boolean), query: new URLSearchParams(search) };
}

function match(parts) {
  for (const [pattern, page, rules = {}] of ROUTES) {
    const expected = pattern.split("/").filter(Boolean);
    if (expected.length !== parts.length) continue;
    const params = {};
    const ok = expected.every((part, i) => {
      if (part.startsWith(":")) {
        params[part.slice(1)] = decodeURIComponent(parts[i]);
        return true;
      }
      return part === parts[i];
    });
    if (ok) return { page, params, rules };
  }
  return null;
}

function renderHeader() {
  const user = session.user;
  const languageSelect = h(
    "select",
    { "aria-label": t("nav.language"), onchange: (e) => changeLanguage(e.target.value) },
    LANGUAGES.map((code) => h("option", { value: code, selected: code === getLanguage() }, code.toUpperCase())),
  );
  document.getElementById("header").replaceChildren(
    h(
      "nav",
      {},
      link("/", h("b", {}, t("app.name"))),
      link("/catalog", t("nav.catalog")),
      link("/builder", t("nav.builder")),
      link("/news", t("nav.news")),
      user ? link("/cart", `${t("nav.cart")} (${session.cartCount})`) : null,
      user ? link("/account", t("nav.account")) : null,
      can("admin.access") ? link("/admin", t("nav.admin")) : null,
      h("span", { class: "spacer" }),
      languageSelect,
      user
        ? [h("span", { class: "muted" }, `${user.name} (${t(`roles.${user.role}`)})`),
           h("button", { onclick: onLogout }, t("nav.logout"))]
        : [link("/login", t("nav.login")), link("/register", t("nav.register"))],
    ),
  );
  document.getElementById("footer").textContent = t("app.footer_note");
}

let renderCounter = 0;

async function render() {
  runLeave();
  renderHeader();
  const main = document.getElementById("main");
  const { parts, query } = parseHash();
  const found = match(parts);
  const current = ++renderCounter;

  if (!found) {
    main.replaceChildren(h("h1", {}, "404"), link("/", t("nav.home")));
    return;
  }
  if ((found.rules.login || found.rules.permission) && !isLoggedIn()) {
    navigate(`/login?next=${encodeURIComponent(location.hash.slice(1))}`);
    return;
  }
  if (found.rules.permission && !can(found.rules.permission)) {
    main.replaceChildren(h("p", { class: "error" }, t("errors.forbidden")));
    return;
  }

  main.replaceChildren(loading());
  try {
    const node = await found.page({ params: found.params, query });
    if (current !== renderCounter) return; // the user already went to another page
    main.replaceChildren(node);
    runAfter();
  } catch (error) {
    if (current === renderCounter) main.replaceChildren(h("p", { class: "error" }, error.message));
  }
}

async function changeLanguage(code) {
  await loadLanguage(code);
  if (isLoggedIn()) await loadUser(); // role names etc.
  render();
}

function onLogout() {
  logout();
  navigate("/");
  render();
}

async function start() {
  try {
    await loadLanguage();
  } catch {
    document.getElementById("main").replaceChildren(
      h("p", { class: "error" }, "API is not available. Start the project: ./run.sh start"),
    );
    return;
  }
  await loadUser();
  await refreshCartCount().catch(() => {});

  window.addEventListener("hashchange", render);
  window.addEventListener("header:update", renderHeader);
  window.addEventListener("page:reload", render);
  window.addEventListener("auth:expired", () => {
    logout();
    flash(t("errors.auth_required"), "error");
    render();
  });
  render();
}

start();
