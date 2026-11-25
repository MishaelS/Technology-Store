import { api } from "../api.js";
import { factCard, newsCard, productCard } from "../components.js";
import { t } from "../i18n.js";
import { h, icon, image, moreLink } from "../ui.js";

const AUTOPLAY_MS = 6000;

function section(title, content, more = null) {
  return h("section", { class: "section" }, h("div", { class: "section-head" }, h("h2", {}, title), more), content);
}

/** Slide with one promotion: badge, title, text, "more" button and a picture (or a big icon). */
function promoSlide(promo) {
  return h(
    "div",
    { class: "promo-slide" },
    h(
      "div",
      { class: "copy" },
      h("span", { class: "news-badge" }, icon("content/promo"), t("news_types.promo")),
      h("h2", {}, promo.title),
      h("p", {}, promo.text),
      h("div", { class: "row" },
        h("a", { href: "#/news?type=promo", class: "btn primary big" }, t("home.promo_more"), icon("navigation/arrow-right"))),
    ),
    h("div", { class: "promo-art", "aria-hidden": "true" }, image(promo.image_url) || icon("content/promo")),
  );
}

/**
 * Slider over the first screen: the "build a PC" slide first, then promotions.
 * Slides scroll natively (swipe on phones, scroll-snap), arrows and dots move them,
 * and they change by themselves every few seconds unless the user is looking at one
 * (mouse over it, focus inside it, tab in the background, reduced motion).
 */
function promoSlider(slides) {
  const track = h("div", { class: "slider-track", tabindex: "-1" },
    slides.map((slide, i) =>
      h("div", { class: "slide", role: "group", "aria-roledescription": "slide", "aria-label": t("home.slide_of", { n: i + 1, total: slides.length }) }, slide)));
  if (slides.length < 2) return h("section", { class: "promo-slider single" }, track);

  let current = 0;
  let target = null; // slide an arrow/dot/autoplay is scrolling to: slides passed on the way don't count
  const go = (i) => {
    current = target = (i + slides.length) % slides.length;
    markDot();
    if (track.scrollLeft === current * track.clientWidth) target = null; // already there: no scroll will come
    track.scrollTo({ left: current * track.clientWidth, behavior: "smooth" });
  };
  const dots = slides.map((_, i) =>
    h("button", { type: "button", class: "slider-dot", "aria-label": t("home.slide_of", { n: i + 1, total: slides.length }), onclick: () => go(i) }));
  const arrow = (step, name, label) =>
    h("button", { type: "button", class: `slider-arrow ${step < 0 ? "prev" : "next"}`, "aria-label": label, onclick: () => go(current + step) }, icon(name));

  // arrows and dots in one bar under the slide: they never cover the slide's picture or text
  const dotsBox = h("div", { class: "slider-dots" }, dots);
  const box = h(
    "section",
    { class: "promo-slider", "aria-roledescription": "carousel", "aria-label": t("home.slider_label") },
    track,
    h("div", { class: "slider-bar" },
      arrow(-1, "navigation/chevron-left", t("home.slide_prev")),
      dotsBox,
      arrow(1, "navigation/chevron-right", t("home.slide_next"))),
  );

  const markDot = () => dots.forEach((dot, i) => dot.setAttribute("aria-current", i === current ? "true" : "false"));
  // the slide nearest to the track's left edge is the current one: works for arrows, dots and a finger swipe alike
  track.addEventListener(
    "scroll",
    () => {
      const index = Math.round(track.scrollLeft / track.clientWidth);
      if (target !== null) {
        if (index === target) target = null;
        return;
      }
      if (index !== current && index >= 0 && index < slides.length) {
        current = index;
        markDot();
      }
    },
    { passive: true },
  );
  // a finger or a wheel takes over from a scroll that is still running
  for (const name of ["pointerdown", "wheel", "touchstart"]) track.addEventListener(name, () => (target = null), { passive: true });
  markDot();

  // Autoplay. The bar filling the active dot is a CSS animation, and the slide changes exactly when it
  // ends (animationend): the bar and the change can't drift apart, and everything that stops the bar
  // (mouse over the slider, keyboard focus inside it, a background tab) stops the change too.
  const keyboardFocus = () => box.contains(document.activeElement) && document.activeElement.matches(":focus-visible");
  const setPaused = (value) => box.classList.toggle("paused", value);
  box.addEventListener("pointerenter", () => setPaused(true));
  // a click leaves the focus on the dot or arrow: that alone must not keep the slider paused
  box.addEventListener("pointerleave", () => setPaused(keyboardFocus()));
  box.addEventListener("focusin", () => setPaused(keyboardFocus() || box.matches(":hover")));
  box.addEventListener("focusout", (event) =>
    setPaused((box.contains(event.relatedTarget) && event.relatedTarget.matches(":focus-visible")) || box.matches(":hover")));
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    box.classList.add("autoplay");
    box.style.setProperty("--autoplay", `${AUTOPLAY_MS}ms`);
    dotsBox.addEventListener("animationend", (event) => {
      if (event.animationName === "dot-fill") go(current + 1);
    });
  }
  return box;
}

export async function homePage() {
  const [data, categories] = await Promise.all([api("/api/home"), api("/api/categories")]);

  const hero = h(
    "section",
    { class: "hero" },
    h(
      "div",
      { class: "copy" },
      h("h1", {}, t("app.tagline")),
      h("p", {}, t("home.build_cta_text")),
      h(
        "div",
        { class: "row" },
        h("a", { href: "#/builder", class: "btn primary big" }, icon("navigation/builder"), t("nav.builder")),
        h("a", { href: "#/catalog", class: "btn big" }, t("nav.catalog")),
      ),
    ),
    h(
      "div",
      { class: "hero-card" },
      h("strong", {}, t("builder.title")),
      h("span", { class: "muted" }, t("home.build_steps")),
      h("ul", { class: "checks" },
        ["socket", "ram", "psu"].map((key) => h("li", {}, icon("feedback/success"), h("span", {}, t(`home.build_check_${key}`))))),
    ),
  );

  // Categories in a sticky panel on the left, like in the catalog. The list can be collapsed;
  // the choice is kept in the browser.
  let closed = false;
  try {
    closed = localStorage.getItem("homeCategoriesClosed") === "1";
  } catch {
    /* storage blocked: the list just starts open */
  }
  const categoryList = h(
    "details",
    { class: "filter-section", open: !closed },
    h("summary", {}, icon("navigation/catalog"), h("span", {}, t("home.categories"))),
    h(
      "nav",
      { class: "filter-body scroll-row", "aria-label": t("home.categories") },
      h("a", { href: "#/catalog", class: "filter-option" }, icon("navigation/catalog"), h("span", { class: "filter-text" }, t("catalog.all_categories"))),
      categories.map((c) =>
        h("a", { href: `#/catalog?category=${c.slug}`, class: "filter-option" }, icon(`categories/${c.slug}`), h("span", { class: "filter-text" }, c.name))),
    ),
  );
  categoryList.addEventListener("toggle", () => {
    try {
      localStorage.setItem("homeCategoriesClosed", categoryList.open ? "0" : "1");
    } catch {
      /* not remembered, still works */
    }
  });
  const sidebar = h("aside", { class: "filters-panel" }, categoryList);

  const slider = promoSlider([hero, ...data.promos.map(promoSlide)]);
  const news = data.promos.concat(data.news);
  return h(
    "div",
    { class: "catalog-layout" },
    sidebar,
    h(
    "div",
    { class: "section home-content" },
    slider,
    data.discounts.length
      ? section(t("home.discounts"), h("div", { class: "grid" }, data.discounts.slice(0, 4).map(productCard)),
          moreLink("/catalog?discount=true", t("catalog.discount")))
      : null,
    section(t("home.hits"), h("div", { class: "grid" }, data.hits.slice(0, 4).map(productCard)), moreLink("/catalog", t("nav.catalog"))),
    // news at the bottom: a row of tiles, the fact of the day is the last tile
    section(
      t("home.news"),
      h("div", { class: "news-grid" }, news.slice(0, data.fact ? 5 : 6).map(newsCard), data.fact ? factCard(data.fact) : null),
      moreLink("/news", t("home.all_news")),
    ),
    ),
  );
}
