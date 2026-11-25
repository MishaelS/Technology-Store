// Entry point: header, routing (#/path?query) and page rendering.
import { LANGUAGES } from "./config.js";
import { api } from "./api.js";
import { watchSelects } from "./dropdown.js";
import { installRipple, revealOnScroll } from "./effects.js";
import { hexWave, installHexBackground } from "./hex-background.js";
import { currentTheme, toggleTheme, watchSystemTheme } from "./theme.js";
import { watchNumbers } from "./number-field.js";
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
import { avatar, flash, h, icon, link, loading, navigate } from "./ui.js";

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
let lastCartCount = null; // to see when the cart grew

/** Marks the current section in the header menu without redrawing the header. */
function markCurrentSection() {
  const section = (location.hash.slice(1) || "/").split(/[/?]/)[1] || "";
  for (const a of document.querySelectorAll("#header .main-nav a, #header .tab-bar a")) {
    const own = a.getAttribute("href").slice(2);
    if (own === section) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

/** Draws the header only when something in it changed (user, cart, language), otherwise it would blink. */
function renderHeader() {
  const user = session.user;
  const key = JSON.stringify([user?.id, user?.name, user?.role, user?.avatar_url, session.cartCount, getLanguage(), currentTheme()]);
  if (key === headerKey) {
    markCurrentSection();
    return;
  }
  headerKey = key;
  const previousCount = lastCartCount;
  lastCartCount = session.cartCount;
  // the first drawing of the header is not "the cart grew"
  const shownCartCount = previousCount ?? session.cartCount;
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
      h("a", { href: "#/", class: "brand", "aria-label": t("app.name") },
        h("img", { src: "/resources/icons/logo.svg", alt: "", width: 28, height: 28 }), h("span", { class: "brand-name" }, t("app.name"))),
      h(
        "nav",
        { class: "main-nav", "aria-label": t("nav.home") },
        navLink("/catalog", t("nav.catalog")),
        navLink("/builder", t("nav.builder")),
        navLink("/news", t("nav.news")),
        can("admin.access") ? navLink("/admin", t("nav.admin")) : null,
      ),
      searchForm,
      // phones: the sections are a bar at the bottom of the screen, always under the thumb
      h(
        "nav",
        { class: "tab-bar", "aria-label": t("nav.home") },
        [["/", "navigation/home", t("nav.home")], ["/catalog", "navigation/catalog", t("nav.catalog")],
          ["/builder", "navigation/builder", t("nav.builder")], ["/news", "navigation/news", t("nav.news")],
          can("admin.access") ? ["/admin", "navigation/admin", t("nav.admin")] : null]
          .filter(Boolean)
          .map(([path, iconName, text]) => h("a", { href: `#${path}` }, icon(iconName), h("span", {}, text))),
      ),
      h(
        "div",
        { class: "header-actions" },
        // light / dark: the icon shows the theme you get by clicking
        h("button", {
          type: "button",
          class: "theme-toggle",
          title: currentTheme() === "dark" ? t("nav.theme_light") : t("nav.theme_dark"),
          "aria-label": currentTheme() === "dark" ? t("nav.theme_light") : t("nav.theme_dark"),
          onclick: (event) => {
            const box = event.currentTarget.getBoundingClientRect();
            toggleTheme(box.left + box.width / 2, box.top + box.height / 2);
          },
        }, icon(currentTheme() === "dark" ? "navigation/theme-light" : "navigation/theme-dark")),
        languageSelect,
        user
          ? [
              h("a", { href: "#/cart", class: "cart-link", "aria-label": t("nav.cart") }, icon("navigation/cart"),
                h("span", { class: "label" }, t("nav.cart")), session.cartCount
                ? h("span", { class: session.cartCount > shownCartCount ? "count bump" : "count" }, session.cartCount) // grew: the number jumps
                : null),
              // own photo or initials; logging out is in the account
              h("a", { href: "#/account", class: "avatar-link", title: user.name, "aria-label": t("account.title") },
                avatar(user)),
            ]
          : [
              h("a", { href: "#/login", class: "login-link", "aria-label": t("nav.login") }, icon("navigation/login"), h("span", { class: "label" }, t("nav.login"))),
              h("a", { href: "#/register", class: "btn primary register-link", "aria-label": t("nav.register") },
                icon("navigation/register"), h("span", { class: "label" }, t("nav.register"))),
            ],
      ),
    ),
  );
  renderFooter();
  markCurrentSection();
}

let footerCategories = null; // loaded once: the footer lists the catalog sections

/** Dark footer with columns of links: the store, the catalog sections, for buyers, service. */
function renderFooter() {
  const column = (title, links) => h("nav", { class: "footer-col", "aria-label": title },
    h("h3", {}, title), h("ul", {}, links.map(([path, text]) => h("li", {}, h("a", { href: `#${path}` }, text)))));
  const shop = h("div", { class: "footer-shop" });
  const drawShop = () => shop.replaceChildren(column(t("footer.shop"), [["/catalog", t("catalog.all_categories")],
    ...(footerCategories || []).map((c) => [`/catalog?category=${c.slug}`, c.name])]));
  drawShop();
  if (!footerCategories) {
    api("/api/categories").then((list) => {
      footerCategories = list;
      drawShop();
    }).catch(() => {});
  }
  document.getElementById("footer").replaceChildren(
    h("div", { class: "footer-inner" },
      h("div", { class: "footer-grid" },
        h("div", { class: "footer-brand" },
          h("a", { href: "#/", class: "brand" }, h("img", { src: "/resources/icons/logo.svg", alt: "", width: 28, height: 28 }), t("app.name")),
          h("p", {}, `© 2026 ${t("app.name")}`),
          h("p", { class: "footer-note" }, t("app.footer_note"))),
        shop,
        column(t("footer.buyers"), [["/catalog", t("nav.catalog")], ["/builder", t("nav.builder")], ["/news", t("nav.news")], ["/cart", t("nav.cart")]]),
        column(t("footer.service"), [["/account?tab=orders", t("footer.orders")], ["/account?tab=builds", t("footer.builds")],
          ["/account?tab=repairs", t("footer.repairs")], ["/account?tab=bonus", t("footer.bonus")]])),
      h("div", { class: "footer-bottom" }, h("span", {}, t("app.tagline")), h("a", { href: "#/" }, t("app.name")))),
  );
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
/** Where a wave starts: a click a moment ago (link, arrow, filter), otherwise the middle of the screen ("Back"). */
function wavePoint() {
  const fresh = Date.now() - lastClick.time < 3000;
  return fresh ? { x: lastClick.x, y: lastClick.y } : { x: window.innerWidth / 2, y: window.innerHeight / 3 };
}

function pageTransition(main, swap) {
  const { x, y } = wavePoint();
  hexWave(x, y); // the hex bytes in the background run as a wave from the same point
  if (!document.startViewTransition || reducedMotion.matches) return swap();
  const root = document.documentElement.style;
  // the swap must happen exactly once: by the transition, or by the safety timer below
  let swapped = false;
  const swapOnce = () => {
    if (swapped) return false;
    swapped = true;
    swap();
    return true;
  };
  const transition = document.startViewTransition(() => {
    if (!swapOnce()) return;
    // the circle is drawn in #main's own box, so move the point into it
    const box = main.getBoundingClientRect();
    const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
    root.setProperty("--wave-x", `${x - box.left}px`);
    root.setProperty("--wave-y", `${y - box.top}px`);
    root.setProperty("--wave-r", `${Math.ceil(radius)}px`);
  });
  // the browser waits for a frame to start the transition; if no frame comes (a page that is not
  // painted), the new page must still appear
  setTimeout(() => {
    if (swapped) return;
    transition.skipTransition();
    swapOnce();
  }, 1000);
}

let lastPath = null;
let lastQuery = ""; // filters of the shown page: a change of them is a new page too

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
    const queryText = query.toString();
    // same section, other filters (catalog, news): the page also changes, with the same wave;
    // a reload of the same page (after cancelling an order and so on) changes nothing visible
    const newFilters = !newSection && queryText !== lastQuery;
    const swap = () => {
      if (current !== renderCounter) return; // a newer page came while the transition was starting
      runLeave(); // stop the old page (observers, timers) right before swapping it
      main.replaceChildren(node);
      if (newSection) window.scrollTo(0, 0); // new section: start at the top; same section (filters): stay
      lastPath = path;
      lastQuery = queryText;
      runAfter();
      revealOnScroll(main);
    };
    // another section or other filters: the new page spreads like a wave from the place of the click
    if ((newSection || newFilters) && lastPath !== null) pageTransition(main, swap);
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


async function start() {
  watchSelects(document.body); // every <select> becomes the site's own dropdown
  watchNumbers(document.body); // every number field gets the site's own up/down arrows
  installRipple(); // click wave in buttons
  installHexBackground(); // hex digits behind the page, a wave runs over them on page change
  watchSystemTheme(); // light/dark follows the system until the user picks one
  window.addEventListener("theme:change", () => renderHeader());
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
