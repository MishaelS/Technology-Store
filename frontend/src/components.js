// Pieces used on several pages.
import { api } from "./api.js";
import { preload } from "./images.js";
import { t } from "./i18n.js";
import { headerChanged } from "./router.js";
import { isLoggedIn, session } from "./session.js";
import { attempt, date, flash, h, icon, image, isImageUrl, money, navigate } from "./ui.js";

export function goToLogin() {
  navigate(`/login?next=${encodeURIComponent(location.hash.slice(1) || "/")}`);
}

export async function addToCart(productId, quantity = 1) {
  if (!isLoggedIn()) return goToLogin();
  const cart = await attempt(() => api("/api/cart", { method: "POST", body: { product_id: productId, quantity } }));
  if (cart) {
    session.cartCount = cart.count;
    headerChanged();
    flash(t("product.added"));
  }
  return Boolean(cart);
}

/** All photos of a product: the main one first, then the extra ones; only links image() accepts. */
export function productPictures(product) {
  return [product.image_url, ...(product.images || [])].filter(isImageUrl);
}

const FLIP_MS = 650; // how long each photo stays while the mouse rests on a card

/** Picture of a product, or its category icon while there is no photo. With several photos
 *  they flip one after another while the mouse rests on the picture, and go back to the first when it leaves. */
export function productThumb(product, href) {
  const pictures = productPictures(product);
  const content = image(pictures[0], product.name) || icon(`categories/${product.category}`);
  const thumb = h("a", { href: `#${href}`, class: "thumb", "aria-hidden": "true", tabindex: -1 }, content);
  if (pictures.length < 2) return thumb;

  const dots = h("span", { class: "thumb-dots" }, pictures.map(() => h("i")));
  thumb.append(dots);
  let layers = null; // the extra photos, laid over the first one; made on the first hover
  let index = 0;
  let timer = null;
  const show = (i) => {
    index = i;
    layers.forEach((layer, k) => layer.classList.toggle("shown", k + 1 === i));
    thumb.classList.toggle("on-layer", i > 0); // the first photo hides under the shown one (see-through cards too)
    [...dots.children].forEach((dot, k) => dot.classList.toggle("on", k === i));
  };
  const start = () => {
    if (!layers) {
      layers = pictures.slice(1).map((url) => {
        const layer = image(url, "");
        layer.classList.add("flip");
        thumb.insertBefore(layer, dots);
        return layer;
      });
    }
    clearInterval(timer);
    show(0);
    timer = setInterval(() => show((index + 1) % pictures.length), FLIP_MS);
  };
  const stop = () => {
    clearInterval(timer);
    if (layers) show(0);
  };
  thumb.addEventListener("pointerenter", start);
  thumb.addEventListener("pointerleave", stop);
  // in a card the link of the title covers the whole card: the card passes its hover on (productCard)
  thumb.flip = { start, stop };
  return thumb;
}

const ZOOM_DELAY = 1200; // ms the mouse has to rest on the photo before the lens opens
const ZOOM = 2.4;

/** Photos on the product page: the big one with thumbnails under it. Resting the mouse on the big photo
 *  for a moment turns on a lens: the photo grows and follows the mouse, like a magnifying glass. */
export function productGallery(product) {
  const pictures = productPictures(product);
  const fallback = h("div", { class: "card product-card" }, productThumb(product, `/product/${product.id}`));
  if (!pictures.length) return fallback;

  const big = image(pictures[0], product.name, "full");
  const hint = h("span", { class: "zoom-hint" }, icon("actions/search"), t("product.zoom_hint"));
  const frame = h("div", { class: "zoom-frame" }, big, hint, h("span", { class: "zoom-progress" }));
  let timer = null;
  const place = (event) => {
    const box = frame.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * 100;
    const y = ((event.clientY - box.top) / box.height) * 100;
    big.style.transformOrigin = `${Math.max(0, Math.min(100, x))}% ${Math.max(0, Math.min(100, y))}%`;
  };
  frame.style.setProperty("--zoom-delay", `${ZOOM_DELAY}ms`);
  frame.style.setProperty("--zoom", ZOOM);
  frame.addEventListener("pointerenter", (event) => {
    if (event.pointerType === "touch") return;
    place(event);
    frame.classList.add("arming"); // the bar under the photo fills while we wait
    timer = setTimeout(() => {
      frame.classList.remove("arming");
      frame.classList.add("zoomed");
    }, ZOOM_DELAY);
  });
  frame.addEventListener("pointermove", place);
  frame.addEventListener("pointerleave", () => {
    clearTimeout(timer);
    frame.classList.remove("arming", "zoomed");
  });

  const thumbs = pictures.length > 1
    ? h("div", { class: "gallery-thumbs" }, pictures.map((url, i) => h("button", {
        type: "button",
        class: i === 0 ? "gallery-thumb on" : "gallery-thumb",
        "aria-label": t("product.photo_n", { n: i + 1 }),
        onclick: (event) => select(event.currentTarget, url),
        onpointerenter: (event) => select(event.currentTarget, url),
        onfocus: () => preload(url, 1),
      }, image(url, ""))))
    : null;
  function select(button, url) {
    // the big photo through the loader: already preloaded when the mouse came onto the thumbnail
    preload(url, 0).then(() => (big.src = url), () => {});
    thumbs.querySelectorAll(".gallery-thumb").forEach((b) => b.classList.toggle("on", b === button));
  }
  return h("div", { class: "card product-gallery" }, frame, thumbs);
}

/** Random delay for the pop-in animation of a card: they appear one by one, in a random order. */
function popDelay() {
  return `--delay: ${Math.round(Math.random() * 140)}ms`; // short: cards must not keep you waiting
}

export function productCard(product) {
  const href = `/product/${product.id}`;
  const out = product.stock <= 0;
  const few = !out && product.stock <= 3;
  const thumb = productThumb(product, href);
  if (product.discount_percent > 0) {
    thumb.append(h("span", { class: "card-badge" }, t("product.discount_badge", { percent: product.discount_percent })));
  }
  if (out) thumb.append(h("span", { class: "card-badge out" }, t("product.out_of_stock")));

  const label = h("span", {}, t("product.add_to_cart"));
  const buy = h(
    "button",
    {
      type: "button",
      class: "primary buy",
      disabled: out,
      "aria-label": `${t("product.add_to_cart")}: ${product.name}`,
      onclick: async () => {
        buy.disabled = true;
        const added = await addToCart(product.id);
        buy.disabled = false;
        if (!added) return;
        // short "added" state with a check mark
        buy.classList.add("added");
        label.textContent = t("product.added_short");
        setTimeout(() => {
          buy.classList.remove("added");
          label.textContent = t("product.add_to_cart");
        }, 1500);
      },
    },
    h("span", { class: "buy-icons" }, icon("actions/add-to-cart"), icon("actions/check")),
    label,
  );

  return h(
    "article",
    {
      class: `card product-card${out ? " is-out" : ""}`,
      style: popDelay(),
      onpointerenter: () => {
        thumb.flip?.start();
        // the click will probably follow: the big photo of the product page loads meanwhile
        const main = productPictures(product)[0];
        if (main) preload(main, 8).catch(() => {});
      },
      onpointerleave: () => thumb.flip?.stop(),
    },
    thumb,
    h("span", { class: "card-category" }, icon(`categories/${product.category}`), product.category_name),
    h("a", { href: `#${href}`, class: "title" }, product.name),
    h("span", { class: `stock${out ? " out" : few ? " few" : ""}` }, stockText(product)),
    h(
      "div",
      { class: "foot" },
      priceRow(product, false),
      buy,
    ),
  );
}

export function priceRow(product, withBadge = true) {
  return h(
    "div",
    { class: "row price-row" },
    h("span", { class: "price" }, money(product.price)),
    product.old_price ? h("span", { class: "old-price" }, money(product.old_price)) : null,
    withBadge && product.discount_percent > 0 ? h("span", { class: "discount" }, t("product.discount_badge", { percent: product.discount_percent })) : null,
  );
}

export function stockText(product) {
  return product.stock > 0 ? t("product.in_stock", { count: product.stock }) : t("product.out_of_stock");
}

// news type -> icon of its badge
export const NEWS_ICONS = { news: "navigation/news", promo: "content/promo", game: "content/game" };

/** A news tile: colored badge with the type, date, title and text. */
export function newsCard(news) {
  return h(
    "article",
    { class: `news-tile news-${news.type}`, style: popDelay() },
    image(news.image_url, news.title),
    h(
      "div",
      { class: "news-meta" },
      h("span", { class: "news-badge" }, icon(NEWS_ICONS[news.type] || "navigation/news"), t(`news_types.${news.type}`)),
      h("time", { datetime: news.created_at }, date(news.created_at)),
    ),
    h("h3", {}, news.title),
    h("p", {}, news.text),
  );
}

/** "Interesting fact" tile. */
export function factCard(fact) {
  return h(
    "aside",
    { class: "news-tile fact-tile", style: popDelay() },
    h("div", { class: "news-meta" }, h("span", { class: "news-badge" }, icon("content/fact"), t("home.fact"))),
    h("p", {}, fact.text),
  );
}

export function specValue(value) {
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? t("common.yes") : t("common.no");
  return String(value);
}

export function specsTable(specs) {
  return h(
    "table",
    {},
    Object.entries(specs).map(([key, value]) => h("tr", {}, h("th", {}, t(`specs.${key}`)), h("td", {}, specValue(value)))),
  );
}

export function statusName(status) {
  return t(`orders.status.${status}`);
}

/** Colored status label. `text` defaults to the order status name. */
export function statusPill(status, text = statusName(status)) {
  return h("span", { class: `pill s-${status}` }, text);
}

/** List of the build checks with status icons. */
export function checksList(checks) {
  const icons = { ok: "feedback/success", error: "feedback/error", warning: "feedback/warning", skip: "feedback/skip" };
  return h(
    "ul",
    { class: "checks" },
    checks.map((c) => h(
      "li",
      { class: c.status === "skip" ? "muted" : c.status },
      icon(icons[c.status], t(`builder.check_status.${c.status}`)),
      h("span", {}, c.message),
    )),
  );
}
