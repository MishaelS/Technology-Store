// The first slide of the home page: an assembled PC that turns around by itself and keeps changing its parts —
// every few seconds one part flies out and another one of the same kind flies in. Every build shown is compatible
// (the same rules as the builder check), made of products in stock. Uses the 3D case of the builder (pc-case.js).
import { api } from "./api.js";

const SLOTS = ["case", "motherboard", "cpu", "cooler", "ram", "gpu", "psu", "storage"];
const SWAP_MS = 2600; // one part changes this often
const CHANGEABLE = ["gpu", "cooler", "ram", "case", "psu", "storage", "cpu", "gpu", "cooler", "ram"]; // GPUs, coolers, RAM more often

const pick = (list) => list[Math.floor(Math.random() * list.length)];
const shuffled = (list) => [...list].sort(() => Math.random() - 0.5);

/** Does the whole build fit together? (services/compatibility.py, the same rules) */
function fits(b) {
  const cpu = b.cpu.specs, mb = b.motherboard.specs, box = b.case.specs, cooler = b.cooler.specs;
  const ram = b.ram.specs, gpu = b.gpu?.specs, psu = b.psu.specs;
  if (cpu.socket !== mb.socket) return false;
  if (!cooler.sockets?.includes(cpu.socket) || cooler.tdp < cpu.tdp) return false;
  if (ram.ram_type !== mb.ram_type || ram.sticks > mb.ram_slots) return false;
  if (!box.form_factors?.includes(mb.form_factor)) return false;
  if (gpu && gpu.length_mm > box.max_gpu_mm) return false;
  if (cooler.type === "СЖО") {
    if (box.max_radiator_mm && cooler.radiator_mm > box.max_radiator_mm) return false;
  } else if (box.max_cooler_mm && cooler.height_mm && cooler.height_mm > box.max_cooler_mm) return false;
  const need = Math.ceil(((cpu.tdp + (gpu?.tdp || 0) + 100) * 1.2) / 50) * 50;
  return psu.wattage >= need;
}

/** A random compatible build from the products in stock; null when the catalog can't make one. */
function randomBuild(bySlot) {
  for (let attempt = 0; attempt < 400; attempt++) {
    const cpu = pick(bySlot.cpu);
    const boards = bySlot.motherboard.filter((m) => m.specs.socket === cpu.specs.socket);
    if (!boards.length) continue;
    const build = {
      cpu,
      motherboard: pick(boards),
      cooler: pick(bySlot.cooler),
      ram: pick(bySlot.ram),
      gpu: pick(bySlot.gpu),
      psu: pick(bySlot.psu),
      case: pick(bySlot.case),
      storage: pick(bySlot.storage),
    };
    if (fits(build)) return build;
  }
  return null;
}

/** The same build with one part changed to another compatible one (or the build as it was). */
function swapOne(build, bySlot) {
  for (const slot of shuffled(CHANGEABLE)) {
    for (const product of shuffled(bySlot[slot])) {
      if (product.id === build[slot].id) continue;
      const next = { ...build, [slot]: product };
      if (slot === "cpu" && next.motherboard.specs.socket !== product.specs.socket) {
        // a CPU of another socket brings a board for it
        const board = shuffled(bySlot.motherboard).find((m) => m.specs.socket === product.specs.socket && fits({ ...next, motherboard: m }));
        if (!board) continue;
        next.motherboard = board;
      }
      if (fits(next)) return next;
    }
  }
  return build;
}

/** What pc-case.js update() takes. */
function forView(build, node) {
  if (node) node.dataset.build = SLOTS.map((slot) => build[slot]?.id).join(","); // what is shown, for checks
  return {
    case: build.case, motherboard: build.motherboard, cpu: build.cpu, cooler: build.cooler, gpu: build.gpu, psu: build.psu,
    ram: [build.ram], storage: [build.storage], powered: true, problems: new Set(),
  };
}

/**
 * Starts the turning, changing PC in `box`; `fallback` (the picture of the parts) stays until the 3D is there,
 * and for good when there is no WebGL or the model doesn't load.
 */
export async function startHeroBuild(box, fallback) {
  const [{ createCaseView }, ...lists] = await Promise.all([
    import("./pc-case.js"),
    ...SLOTS.map((slot) => api(`/api/products?category=${slot}&limit=100`)),
  ]);
  const bySlot = Object.fromEntries(SLOTS.map((slot, i) => [slot, lists[i].items.filter((p) => p.stock > 0)]));
  let build = randomBuild(bySlot);
  if (!build || !box.isConnected) return;

  // the mouse over the whole first slide turns the view
  const view = createCaseView({ showcase: true, lookArea: box.closest(".hero-slide") || box });
  view.node.classList.add("hero-3d");
  box.append(view.node);
  view.update(forView(build, view.node));
  // the picture goes away once the 3D model is drawn
  const ready = setInterval(() => {
    if (!view.node.isConnected) return clearInterval(ready);
    if (view.node.classList.contains("ready")) {
      clearInterval(ready);
      fallback?.classList.add("hero-fallback-gone");
    }
    if (view.node.classList.contains("failed")) {
      clearInterval(ready);
      view.node.remove();
    }
  }, 200);

  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return; // one build, no changes
  let visible = true;
  new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; }).observe(view.node);
  const timer = setInterval(() => {
    if (!view.node.isConnected) return clearInterval(timer);
    if (!visible || document.hidden) return; // nobody looks: no changes, no work
    build = swapOne(build, bySlot);
    view.update(forView(build, view.node));
  }, SWAP_MS);
}
