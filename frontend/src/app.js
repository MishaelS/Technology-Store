// Entry point: header, routing (#/path?query) and page rendering.
import { LANGUAGES } from "./config.js";
import { watchSelects } from "./dropdown.js";
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
import { productEditorPage } from "./pages/product-editor.js";
import { runAfter, runLeave } from "./router.js";
import { can, isLoggedIn, loadUser, logout, refreshCartCount, session } from "./session.js";
import { flash, h, icon, link, loading, navigate } from "./ui.js";

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
  ["/admin/products/new", productEditorPage, { permission: "products.manage" }],
  ["/admin/products/:id", productEditorPage, { permission: "products.manage" }],
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

let headerKey = "";

/** Marks the current section in the header menu without redrawing the header. */
function markCurrentSection() {
  const section = (location.hash.slice(1) || "/").split(/[/?]/)[1] || "";
  for (const a of document.querySelectorAll("#header .main-nav a")) {
    const own = a.getAttribute("href").slice(2);
    if (own === section) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

/** Draws the header only when something in it changed (user, cart, language), otherwise it would blink. */
function renderHeader() {
  const user = session.user;
  const key = JSON.stringify([user?.id, user?.name, user?.role, session.cartCount, getLanguage()]);
  if (key === headerKey) {
    markCurrentSection();
    return;
  }
  headerKey = key;
  const languageSelect = h(
    "select",
    { "aria-label": t("nav.language"), onchange: (e) => changeLanguage(e.target.value) },
    LANGUAGES.map((code) => h("option", { value: code, selected: code === getLanguage() }, code.toUpperCase())),
  );
  const section = (location.hash.slice(1) || "/").split(/[/?]/)[1] || "";
  const navLink = (path, text) => h("a", { href: `#${path}`, "aria-current": section === path.slice(1) ? "page" : null }, text);
  const search = h("input", { type: "search", name: "search", placeholder: t("nav.search_placeholder"), "aria-label": t("common.search") });
  const searchForm = h(
    "form",
    {
      class: "header-search",
      role: "search",
      onsubmit: (event) => {
        event.preventDefault();
        navigate(`/catalog${search.value.trim() ? `?search=${encodeURIComponent(search.value.trim())}` : ""}`);
      },
    },
    icon("actions/search"),
    search,
  );
  document.getElementById("header").replaceChildren(
    h(
      "div",
      { class: "header-inner" },
      h("a", { href: "#/", class: "brand" }, h("img", { src: "/resources/icons/logo.svg", alt: "", width: 28, height: 28 }), t("app.name")),
      h(
        "nav",
        { class: "main-nav", "aria-label": t("nav.home") },
        navLink("/catalog", t("nav.catalog")),
        navLink("/builder", t("nav.builder")),
        navLink("/news", t("nav.news")),
        can("admin.access") ? navLink("/admin", t("nav.admin")) : null,
      ),
      searchForm,
      h(
        "div",
        { class: "header-actions" },
        languageSelect,
        user
          ? [
              h("a", { href: "#/cart" }, icon("navigation/cart"), t("nav.cart"), session.cartCount ? h("span", { class: "count" }, session.cartCount) : null),
              h("a", { href: "#/account", title: t(`roles.${user.role}`) }, icon("navigation/account"), user.name),
              h("button", { type: "button", onclick: onLogout }, t("nav.logout")),
            ]
          : [
              h("a", { href: "#/login" }, icon("navigation/login"), t("nav.login")),
              h("a", { href: "#/register", class: "btn primary" }, t("nav.register")),
            ],
      ),
    ),
  );
  document.getElementById("footer").replaceChildren(h("div", { class: "footer-inner" }, t("app.footer_note")));
  markCurrentSection();
}

let renderCounter = 0;

// Where the user clicked last: the page transition wave starts there.
let lastClick = { x: 0, y: 0, time: 0 };
document.addEventListener("pointerdown", (event) => {
  lastClick = { x: event.clientX, y: event.clientY, time: Date.now() };
});
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

/** Swaps the page with a View Transition: the old page fades away, the new one opens as a growing circle.
 *  Browsers without View Transitions (or with reduced motion) just swap. */
function pageTransition(main, swap) {
  if (!document.startViewTransition || reducedMotion.matches) return swap();
  // a click a moment ago (link, arrow): start from it; "Back" button and others: from the middle of the screen
  const fresh = Date.now() - lastClick.time < 3000;
  const x = fresh ? lastClick.x : window.innerWidth / 2;
  const y = fresh ? lastClick.y : window.innerHeight / 3;
  const root = document.documentElement.style;
  document.startViewTransition(() => {
    swap();
    // the circle is drawn in #main's own box, so move the point into it
    const box = main.getBoundingClientRect();
    const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
    root.setProperty("--wave-x", `${x - box.left}px`);
    root.setProperty("--wave-y", `${y - box.top}px`);
    root.setProperty("--wave-r", `${Math.ceil(radius)}px`);
  });
}

let lastPath = null;

/** Thin loading bar at the top, only when the next page takes a noticeable time. */
function showLoading(current) {
  const timer = setTimeout(() => {
    if (current === renderCounter) document.body.classList.add("is-loading");
  }, 200);
  return () => {
    clearTimeout(timer);
    if (current === renderCounter) document.body.classList.remove("is-loading");
  };
}

async function render() {
  renderHeader();
  const main = document.getElementById("main");
  const { parts, query } = parseHash();
  const path = parts.join("/");
  const found = match(parts);
  const current = ++renderCounter;

  if (!found) {
    runLeave();
    main.replaceChildren(h("h1", {}, "404"), link("/", t("nav.home")));
    return;
  }
  if ((found.rules.login || found.rules.permission) && !isLoggedIn()) {
    navigate(`/login?next=${encodeURIComponent(location.hash.slice(1))}`);
    return;
  }
  if (found.rules.permission && !can(found.rules.permission)) {
    runLeave();
    main.replaceChildren(h("p", { class: "error" }, t("errors.forbidden")));
    return;
  }

  // The current page stays on screen until the next one is ready, so nothing blinks.
  // Only the very first page (nothing to keep yet) shows "Loading…".
  if (!main.childElementCount) main.replaceChildren(loading());
  const done = showLoading(current);
  try {
    const node = await found.page({ params: found.params, query });
    if (current !== renderCounter) return; // the user already went to another page
    const newSection = path !== lastPath;
    const swap = () => {
      runLeave(); // stop the old page (observers, timers) right before swapping it
      main.replaceChildren(node);
      if (newSection) window.scrollTo(0, 0); // new section: start at the top; same section (filters): stay
      lastPath = path;
      runAfter();
    };
    // another section: the new page spreads like a wave from the place of the click
    if (newSection && lastPath !== null) pageTransition(main, swap);
    else swap();
  } catch (error) {
    if (current === renderCounter) {
      runLeave();
      main.replaceChildren(h("p", { class: "error" }, error.message));
    }
  } finally {
    done();
  }
}

async function changeLanguage(code) {
  await loadLanguage(code);
  if (isLoggedIn()) await loadUser(); // role names etc.
  headerKey = ""; // texts changed: redraw the header
  render();
}

function onLogout() {
  logout();
  navigate("/");
  render();
}

async function start() {
  watchSelects(document.body); // every <select> becomes the site's own dropdown
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
