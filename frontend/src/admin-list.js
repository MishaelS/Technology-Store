// Admin lists: a search bar on top and a table (or cards) that loads more rows while scrolling,
// the same infinite list as in the catalog. No page buttons.
//
// Admin API lists are page-based ({items, total, page, pages}); pagedSource() turns them into
// chunks for infiniteList, so the backend stays as it is.
import { api, query as toQuery } from "./api.js";
import { t } from "./i18n.js";
import { infiniteList } from "./infinite.js";
import { onLeave } from "./router.js";
import { h, icon, select } from "./ui.js";

/** fetchPage for infiniteList over a page-based API: the "cursor" is the next page number. */
export function pagedSource(url, params, pageSize = 20) {
  return async (cursor) => {
    const page = cursor || 1;
    const data = await api(`${url}${toQuery({ ...params, page, page_size: pageSize })}`);
    return { items: data.items, total: data.total, next_cursor: page < data.pages ? page + 1 : null };
  };
}

/** Grey rows in a table while the next rows load. */
function skeletonRows(columns, count = 3) {
  return Array.from({ length: count }, () =>
    h("tr", { class: "skeleton-row" }, Array.from({ length: columns }, () => h("td", {}, h("span", { class: "bone" })))));
}

/** Text in a table cell: the main line and smaller grey lines under it. */
export function cell(main, ...lines) {
  return h("div", { class: "cell" }, h("span", { class: "cell-main" }, main),
    lines.filter((x) => x !== null && x !== undefined && x !== "").map((x) => h("span", { class: "cell-sub" }, x)));
}

/** Small square button with an icon; the text is the tooltip and what screen readers say. */
export function iconButton(iconName, text, props = {}) {
  const tag = props.href ? "a" : "button";
  const cls = tag === "a" ? "btn small icon-action" : "small icon-action";
  return h(tag, { type: tag === "button" ? "button" : null, ...props, class: `${cls} ${props.class || ""}`.trim(), title: text, "aria-label": text }, icon(iconName));
}

/**
 * section     admin section name, for the address bar
 * source      (params) => fetchPage: where the rows come from
 * params      filter values from the address
 * search      placeholder of the search box, or null for no search
 * filters     [{name, options: [[value, text]]}] → selects, or [{name, label, type: "checkbox"}]
 * head        column titles → a table; without head the items are cards in a column
 * render      (item, update) => Node; update(newItem) redraws this item in place after a change
 * actions     extra nodes on the right of the search bar (e.g. "New product")
 * emptyText   text when nothing is found
 */
export function adminList({ section, source, params, search, filters = [], head, render, actions = null, emptyText = t("common.nothing_found"), skeleton }) {
  params = { ...params };
  const found = h("span", { class: "muted found" });
  const listBox = h("div", { class: "admin-list-body" });
  let list = null;

  // an item can redraw itself after a change without reloading the whole list
  const renderItem = (item) => {
    const node = render(item, (next) => node.replaceWith(renderItem(next)));
    return node;
  };

  function load() {
    list?.destroy();
    const container = head
      ? h("table", { class: "admin-table" }, h("thead", {}, h("tr", {}, head.map((x) => h("th", {}, x)))))
      : h("div", { class: "admin-cards" });
    listBox.replaceChildren(container);
    found.textContent = "";
    list = infiniteList({
      container,
      fetchPage: source(params),
      renderItem,
      endText: t("admin.list_end"),
      emptyText,
      skeleton: skeleton || (head ? () => skeletonRows(head.length) : null),
      onTotal: (total) => (found.textContent = t("catalog.found", { count: total })),
    });
  }

  // filters change the list right away; the address keeps them, so a reload or a link opens the same list
  let timer = null;
  function change(name, value) {
    params[name] = value;
    history.replaceState(null, "", `#/admin${toQuery({ section, ...params })}`);
    load();
  }

  const controls = filters.map((filter) => {
    if (filter.type === "checkbox") {
      return h("label", { class: "toolbar-check" },
        h("input", { type: "checkbox", checked: params[filter.name] === "true", onchange: (e) => change(filter.name, e.target.checked ? "true" : "") }),
        filter.label);
    }
    const node = select(filter.name, filter.options, params[filter.name]);
    node.addEventListener("change", () => change(filter.name, node.value));
    return node;
  });
  const searchBox = search === null || search === undefined
    ? null
    : h(
        "label",
        { class: "toolbar-search" },
        icon("actions/search"),
        h("input", {
          type: "search",
          value: params.search || "",
          placeholder: search,
          "aria-label": search,
          // the list follows the typing with a short pause, no button needed
          oninput: (e) => {
            clearTimeout(timer);
            timer = setTimeout(() => change("search", e.target.value.trim()), 300);
          },
          onkeydown: (e) => e.key === "Enter" && e.preventDefault(),
        }),
      );

  onLeave(() => {
    clearTimeout(timer);
    list?.destroy();
  });
  load();
  return h(
    "div",
    { class: "admin-list" },
    h("div", { class: "toolbar" }, searchBox, controls, h("div", { class: "toolbar-end" }, found, actions)),
    listBox,
  );
}
