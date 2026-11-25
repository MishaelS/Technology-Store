import { api } from "../api.js";
import { priceRow, productCard } from "../components.js";
import { countTo } from "../effects.js";
import { getLanguage, t } from "../i18n.js";
import { onLeave } from "../router.js";
import { h, icon, image, moreLink } from "../ui.js";

const AUTOPLAY_MS = 6000;

function section(title, content, more = null) {
  return h("section", { class: "section" }, h("div", { class: "section-head" }, h("h2", {}, title), more), content);
}

/**
 * One slide of the first screen: on the left a small grey line, a big colored title, a text and buttons;
 * on the right a big picture over two colored circles.
 */
function heroSlide({ kicker, title, text, extra = null, actions, picture, tone = "" }) {
  return h(
    "div",
    { class: `hero-slide${tone ? ` tone-${tone}` : ""}` },
    h("div", { class: "hero-copy" },
      h("span", { class: "hero-kicker" }, kicker),
      h("h2", { class: "hero-title" }, title),
      text ? h("p", { class: "hero-text" }, text) : null,
      extra,
      h("div", { class: "row" }, actions)),
    h("div", { class: "hero-art", "aria-hidden": "true" },
      h("span", { class: "circle big" }), h("span", { class: "circle small" }),
      h("span", { class: "hero-pic" }, picture)),
  );
}

const short = (text, max = 140) => (text.length > max ? `${text.slice(0, max).replace(/\s+\S*$/, "")}…` : text);

function buildSlide() {
  return heroSlide({
    kicker: t("app.tagline"),
    title: t("home.hero_build_title"),
    text: t("home.build_cta_text"),
    actions: [
      h("a", { href: "#/builder", class: "btn primary big" }, icon("navigation/builder"), t("nav.builder")),
      h("a", { href: "#/catalog", class: "btn big" }, t("nav.catalog")),
    ],
    picture: icon("navigation/builder"),
  });
}

function productSlide(product) {
  return heroSlide({
    kicker: `${product.category_name} · ${product.brand}`,
    title: product.name,
    text: short(product.description || ""),
    extra: h("div", { class: "hero-price" }, priceRow(product)),
    actions: [h("a", { href: `#/product/${product.id}`, class: "btn primary big" }, t("home.promo_more"), icon("navigation/arrow-right"))],
    picture: image(product.image_url, product.name) || icon(`categories/${product.category}`),
    tone: "product",
  });
}

function promoSlide(promo) {
  return heroSlide({
    kicker: t("news_types.promo"),
    title: promo.title,
    text: promo.text,
    actions: [h("a", { href: "#/news?type=promo", class: "btn primary big" }, t("home.promo_more"), icon("navigation/arrow-right"))],
    picture: icon("content/promo"),
    tone: "promo",
  });
}

/**
 * Slider over the first screen: "build a PC", products on sale, then promotions.
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

/** News in three columns under a thick line: date and title, like a newspaper. */
function newsColumn(item) {
  return h("a", { href: `#/news${item.type === "news" ? "" : `?type=${item.type}`}`, class: "news-column" },
    h("time", { datetime: item.created_at }, new Date(item.created_at).toLocaleDateString(getLanguage(), { day: "numeric", month: "long", year: "numeric" })),
    h("strong", {}, item.title),
    h("span", { class: "muted" }, short(item.text, 110)));
}

/** A band of big numbers about the store; they count up when the band comes into view. */
function statsBand(stats) {
  const format = (n) => n.toLocaleString(getLanguage());
  const numbers = stats.map(([value, label]) => {
    // the real number from the start: without the animation (no frames, reduced motion) it's still right
    const node = h("strong", { class: "stat-number" }, format(value));
    node.dataset.value = value;
    return h("div", { class: "stat" }, node, h("span", {}, label));
  });
  const band = h("section", { class: "band stats-band" }, h("div", { class: "band-inner stats-row" }, numbers));
  const observer = new IntersectionObserver((entries) => {
    if (!entries.some((e) => e.isIntersecting)) return;
    observer.disconnect();
    band.querySelectorAll(".stat-number").forEach((node) => countTo(node, 0, Number(node.dataset.value), format, 1100));
  }, { threshold: 0.4 });
  observer.observe(band);
  onLeave(() => observer.disconnect());
  return band;
}

export async function homePage() {
  const [data, categories, brands, catalog] = await Promise.all([
    api("/api/home"), api("/api/categories"), api("/api/products/brands"), api("/api/products?limit=1"),
  ]);

  const slides = [buildSlide(), ...data.discounts.slice(0, 3).map(productSlide), ...data.promos.slice(0, 2).map(promoSlide)];
  const slider = promoSlider(slides);

  const categoryTiles = h("nav", { class: "category-tiles", "aria-label": t("home.categories") },
    categories.map((c) => h("a", { href: `#/catalog?category=${c.slug}`, class: "category-tile" },
      h("span", { class: "category-icon" }, icon(`categories/${c.slug}`)), h("span", {}, c.name))));

  const latest = [...data.news, ...data.promos].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 3);

  return h(
    "div",
    { class: "home" },
    h("section", { class: "band hero-band" }, h("div", { class: "band-inner" }, slider)),
    h("section", { class: "section" }, h("div", { class: "section-head" }, h("h2", {}, t("home.categories")),
      moreLink("/catalog", t("catalog.all_categories"))), categoryTiles),
    data.discounts.length
      ? section(t("home.discounts"), h("div", { class: "grid" }, data.discounts.slice(0, 4).map(productCard)),
          moreLink("/catalog?discount=true", t("catalog.discount")))
      : null,
    section(t("home.news"), h("div", { class: "news-columns" }, latest.map(newsColumn)), moreLink("/news", t("home.all_news"))),
    statsBand([
      [catalog.total, t("home.stat_products")],
      [brands.length, t("home.stat_brands")],
      [categories.length, t("home.stat_categories")],
    ]),
    h("section", { class: "band about-band" },
      h("div", { class: "about-picture", "aria-hidden": "true" }),
      h("div", { class: "band-inner" },
        h("div", { class: "about-card" },
          h("h2", {}, t("home.about_title")),
          h("p", {}, t("home.about_text")),
          data.fact ? h("p", { class: "about-fact" }, icon("content/fact"), h("span", {}, data.fact.text)) : null,
          h("div", { class: "row" },
            h("a", { href: "#/builder", class: "btn primary" }, icon("navigation/builder"), t("nav.builder")),
            h("a", { href: "#/catalog", class: "btn" }, t("nav.catalog")))))),
    section(t("home.hits"), h("div", { class: "grid" }, data.hits.slice(0, 4).map(productCard)), moreLink("/catalog", t("nav.catalog"))),
    h("section", { class: "band ask-band" }, h("div", { class: "band-inner" },
      h("p", {}, t("home.ask"), " ", h("a", { href: "#/builder" }, t("home.ask_link"))))),
  );
}
