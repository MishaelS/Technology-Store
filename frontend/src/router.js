// Page lifecycle hooks used by pages: cleanup on leave and actions after the page is shown.
let leaveHandlers = [];
let afterHandlers = [];

/** Run fn when the user leaves the current page (stop observers, save scroll...). */
export function onLeave(fn) {
  leaveHandlers.push(fn);
}

/** Run fn right after the page is put on the screen (e.g. restore scroll position). */
export function afterRender(fn) {
  afterHandlers.push(fn);
}

export function runLeave() {
  const handlers = leaveHandlers;
  leaveHandlers = [];
  afterHandlers = [];
  handlers.forEach((fn) => fn());
}

export function runAfter() {
  const handlers = afterHandlers;
  afterHandlers = [];
  handlers.forEach((fn) => fn());
}

/** Draw the current page again (after a change on the server). */
export function reload() {
  window.dispatchEvent(new Event("page:reload"));
}

/** Ask the header to redraw (cart count, user name). */
export function headerChanged() {
  window.dispatchEvent(new Event("header:update"));
}
