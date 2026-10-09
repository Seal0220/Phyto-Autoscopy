import test from "node:test";
import assert from "node:assert/strict";
import { PerspectiveCamera, Vector3 } from "three";
import { createModelMarkerLayer, createTipMarkerLayer } from "../src/features/AnalysisRun/lib/analysisModelMarkers.js";

class Element extends EventTarget {
  style = {};
  dataset = {};
  attributes = {};
  children = [];
  captures = new Set();
  clientWidth = 800;
  clientHeight = 600;
  setAttribute(name, value) { this.attributes[name] = value; }
  appendChild(node) { this.children.push(node); node.parentNode = this; }
  replaceChildren(...nodes) { this.children = nodes; for (const node of nodes) node.parentNode = this; }
  focus() {}
  getBoundingClientRect() { return { left: 0, top: 0 }; }
  setPointerCapture(id) { this.captures.add(id); }
  hasPointerCapture(id) { return this.captures.has(id); }
  releasePointerCapture(id) { this.captures.delete(id); }
  remove() {
    if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((node) => node !== this);
    this.parentNode = null;
  }
}

test("tip markers project the measured position and distinguish confirmed tips from candidates", (t) => {
  const previous = globalThis.document;
  globalThis.document = { createElement: () => new Element() };
  t.after(() => { globalThis.document = previous; });
  const element = new Element();
  const camera = new PerspectiveCamera(40, 4 / 3, .01, 100);
  camera.position.set(0, 0, 10);
  const marker = createTipMarkerLayer({ element, camera });
  const node = element.children[0].children[0];
  marker.setTip({ x_mm: 0, y_mm: 0, z_mm: 0, valid: true });
  assert.equal(node.hidden, false);
  assert.equal(node.style.left, "400px");
  assert.equal(node.style.top, "300px");
  assert.equal(node.dataset.tipStatus, "confirmed");
  assert.match(node.innerHTML, /尖端（已確認）/);
  const graphic = node.innerHTML;
  camera.fov = 20;
  camera.updateProjectionMatrix();
  marker.update();
  assert.equal(node.innerHTML, graphic, "zoom must preserve the marker's screen size");
  marker.setTip({ x_mm: 1, y_mm: 0, z_mm: 0, valid: false });
  assert.equal(node.dataset.tipStatus, "candidate");
  assert.match(node.attributes["aria-label"], /待補正/);
  assert.ok(parseFloat(node.style.left) > 400);
  marker.setTip({ x_mm: null, y_mm: 0, z_mm: 0, valid: false });
  assert.equal(node.hidden, true, "missing coordinates must not create a tip at the origin");
  marker.setTip({ x_mm: 0, y_mm: 0, z_mm: 11, valid: true });
  assert.equal(node.hidden, true, "a point behind the camera must be hidden");
  marker.dispose();
  assert.equal(element.children.length, 0);
});

function event(node, type, values = {}) {
  const input = new Event(type, { cancelable: true });
  Object.assign(input, { button: 0, isPrimary: true, pointerId: 1, clientX: 400, clientY: 300, ...values });
  node.dispatchEvent(input);
  return input;
}

function fixture(t) {
  const previous = globalThis.document;
  globalThis.document = { createElement: () => new Element() };
  t.after(() => { globalThis.document = previous; });
  const element = new Element();
  const camera = new PerspectiveCamera(40, 4 / 3, .01, 100);
  camera.position.set(0, 0, 10);
  const calls = { select: [], move: [], remove: [], drag: [], notice: [] };
  let hit = { pointId: 110, anchor: new Vector3(1, 0, 0) };
  let accepted = true;
  const layer = createModelMarkerLayer({
    element, camera,
    pickPoint: () => hit,
    onSelect: (id) => calls.select.push(id),
    onMove: (...ids) => { calls.move.push(ids); return accepted; },
    onRemove: (id) => calls.remove.push(id),
    onDragState: (active) => calls.drag.push(active),
    onNotice: (notice) => calls.notice.push(notice),
  });
  const anchors = [100, 101].map((pointId, index) => ({ pointId, anchor: new Vector3(index, 0, 0), number: index + 1, selected: !index }));
  layer.setMarkers(anchors);
  t.after(() => layer.dispose());
  return {
    element, layer, anchors, calls, nodes: element.children[0].children,
    hit: (value) => { hit = value; }, reject: () => { accepted = false; },
  };
}

test("drag selects the actual marker and preserves pointer capture across selection renders", (t) => {
  const f = fixture(t), node = f.nodes[1];
  const start = node.style.left;
  event(node, "pointerdown");
  f.layer.setMarkers(f.anchors.map((anchor) => ({ ...anchor, selected: anchor.pointId === 101 })));
  assert.equal(f.element.children[0].children[1], node);
  assert.equal(node.hasPointerCapture(1), true);
  f.hit({ pointId: 120, anchor: new Vector3(2, 0, 0) });
  event(node, "pointermove", { clientX: 420 });
  assert.notEqual(node.style.left, start);
  event(node, "pointerup", { clientX: 420 });
  assert.deepEqual(f.calls.select, [101]);
  assert.deepEqual(f.calls.move, [[101, 120]]);
  assert.deepEqual(f.calls.drag, [true, false]);
  assert.equal(node.hasPointerCapture(1), false);
  event(node, "click", { detail: 1 });
  assert.deepEqual(f.calls.select, [101], "a drag must not add the old anchor back on click");
});

test("click and jitter select without changing a model anchor", (t) => {
  const f = fixture(t), node = f.nodes[0];
  event(node, "pointerdown");
  event(node, "pointermove", { clientX: 403 });
  event(node, "pointerup", { clientX: 403 });
  assert.deepEqual(f.calls.move, []);
  assert.deepEqual(f.calls.select, [100]);
});

test("empty-space drops and rejected duplicate anchors restore the original marker", (t) => {
  const f = fixture(t), node = f.nodes[0], start = node.style.left;
  event(node, "pointerdown");
  event(node, "pointermove", { clientX: 420 });
  f.hit(null);
  event(node, "pointerup", { clientX: 900 });
  assert.equal(node.style.left, start);
  assert.deepEqual(f.calls.move, []);
  assert.equal(f.calls.notice.length, 1);
  f.hit({ pointId: 101, anchor: new Vector3(1, 0, 0) });
  f.reject();
  event(node, "pointerdown");
  event(node, "pointermove", { clientX: 420 });
  event(node, "pointerup", { clientX: 420 });
  assert.equal(node.style.left, start);
  assert.deepEqual(f.calls.move, [[100, 101]]);
});

test("cancellation, Escape and locking release the camera without committing a drag", (t) => {
  const f = fixture(t), node = f.nodes[0], start = node.style.left;
  for (const stop of ["pointercancel", "lostpointercapture", "Escape", "lock"]) {
    event(node, "pointerdown");
    event(node, "pointermove", { clientX: 420 });
    if (stop === "lock") f.layer.setDisabled(true);
    else if (stop === "Escape") event(node, "keydown", { key: "Escape" });
    else event(node, stop);
    assert.equal(node.style.left, start);
    assert.equal(node.hasPointerCapture(1), false);
  }
  assert.deepEqual(f.calls.move, []);
  assert.deepEqual(f.calls.drag, [true, false, true, false, true, false, true, false]);
  event(node, "pointerdown");
  event(node, "contextmenu");
  event(node, "keydown", { key: "Delete" });
  assert.deepEqual(f.calls.remove, []);
  assert.equal(node.disabled, true);
});

test("right-click and keyboard delete address that marker rather than the selected group", (t) => {
  const f = fixture(t), node = f.nodes[1];
  assert.equal(event(node, "contextmenu").defaultPrevented, true);
  event(node, "keydown", { key: "Delete" });
  event(node, "click", { detail: 0 });
  assert.deepEqual(f.calls.remove, [101, 101]);
  assert.deepEqual(f.calls.select, [101]);
  assert.match(node.attributes["aria-label"], /第 2 組/);
  assert.equal(node.attributes["aria-pressed"], "false");
});

test("removal and disposal clean up a captured drag and all marker listeners", (t) => {
  const f = fixture(t), node = f.nodes[0];
  event(node, "pointerdown");
  f.layer.setMarkers([f.anchors[1]]);
  assert.equal(node.hasPointerCapture(1), false);
  event(node, "contextmenu");
  assert.deepEqual(f.calls.remove, []);
  const remaining = f.element.children[0].children[0];
  event(remaining, "pointerdown");
  f.layer.dispose();
  assert.equal(f.element.children.length, 0);
  assert.deepEqual(f.calls.drag, [true, false, true, false]);
  event(remaining, "contextmenu");
  assert.deepEqual(f.calls.remove, []);
});
