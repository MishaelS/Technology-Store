// Custom up/down arrows for every <input type="number"> on the page, in the site's style.
//
// The input itself stays as it is: forms read its value, pages listen to its "input"/"change"
// events, the keyboard arrows keep working. Only the browser's own spinner is hidden (style.css)
// and two small buttons are put inside the field instead.
// Holding a button repeats the step; "change" fires once, when the button is released,
// so pages that save on "change" (the cart) send one request, not one per step.

const DELAY = 400; // ms before holding starts to repeat
const REPEAT = 70; // ms between repeated steps

export function watchNumbers(root = document.body) {
  enhanceAll(root);
  new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) continue;
        if (node.matches('input[type="number"]')) enhance(node);
        else enhanceAll(node);
      }
    }
  }).observe(root, { childList: true, subtree: true });
}

function enhanceAll(root) {
  root.querySelectorAll('input[type="number"]:not([data-stepper])').forEach(enhance);
}

function enhance(input) {
  if (input.dataset.stepper) return;
  input.dataset.stepper = "on";

  const wrap = document.createElement("span");
  wrap.className = "number-field";
  // a width given to the input belongs to the whole field now
  if (input.getAttribute("style")) {
    wrap.setAttribute("style", input.getAttribute("style"));
    input.removeAttribute("style");
  }
  const up = arrow("up");
  const down = arrow("down");
  const arrows = document.createElement("span");
  arrows.className = "number-arrows";
  arrows.setAttribute("aria-hidden", "true"); // the keyboard has its own arrows, screen readers too
  arrows.append(up, down);
  input.replaceWith(wrap);
  wrap.append(input, arrows);

  const limit = (name) => (input[name] === "" ? null : Number(input[name]));
  function sync() {
    const value = input.value === "" ? null : Number(input.value);
    const off = input.disabled || input.readOnly;
    up.disabled = off || (value !== null && limit("max") !== null && value >= limit("max"));
    down.disabled = off || (value !== null && limit("min") !== null && value <= limit("min"));
  }

  function step(direction) {
    if (input.disabled || input.readOnly) return false;
    const before = input.value;
    try {
      if (direction > 0) input.stepUp();
      else input.stepDown();
    } catch {
      // step="any" can't use stepUp/stepDown: move by 1 and keep inside min/max
      let next = (Number(input.value) || 0) + direction;
      if (limit("min") !== null) next = Math.max(limit("min"), next);
      if (limit("max") !== null) next = Math.min(limit("max"), next);
      input.value = String(next);
    }
    if (input.value === before) return false;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    sync();
    return true;
  }

  let timer = null;
  let changed = false;
  function stop() {
    if (timer === null) return;
    clearTimeout(timer);
    clearInterval(timer);
    timer = null;
    if (changed) input.dispatchEvent(new Event("change", { bubbles: true }));
    changed = false;
  }
  for (const [button, direction] of [[up, 1], [down, -1]]) {
    button.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || button.disabled) return;
      event.preventDefault(); // keep the focus where it is (no blinking caret jump)
      button.setPointerCapture?.(event.pointerId);
      changed = step(direction);
      timer = setTimeout(() => {
        timer = setInterval(() => {
          if (step(direction)) changed = true;
          else stop(); // reached min/max
        }, REPEAT);
      }, DELAY);
    });
    button.addEventListener("pointerup", stop);
    button.addEventListener("pointercancel", stop);
    button.addEventListener("lostpointercapture", stop);
  }

  input.addEventListener("input", sync);
  input.addEventListener("change", sync);
  // pages also set value/disabled from code: check again when the field is touched
  wrap.addEventListener("pointerenter", sync);
  input.addEventListener("focus", sync);
  sync();
}

function arrow(direction) {
  const button = document.createElement("button");
  button.type = "button";
  button.tabIndex = -1;
  button.className = `number-arrow ${direction}`;
  const icon = document.createElement("span");
  icon.className = "icon";
  icon.style.setProperty("--m", "url(/resources/icons/navigation/chevron-down.svg)");
  button.append(icon);
  return button;
}
