import { Vector3 } from "three";

export function createTipMarkerLayer({ element, camera }) {
  const layer = document.createElement("div");
  layer.className = "pointer-events-none absolute inset-0 z-20 overflow-hidden";
  layer.dataset.tipMarkers = "";
  const node = document.createElement("div");
  node.className = "absolute -translate-x-1/2 -translate-y-1/2";
  node.setAttribute("role", "img");
  node.hidden = true;
  layer.appendChild(node);
  element.appendChild(layer);
  let anchor = null;

  const update = () => {
    if (!anchor) { node.hidden = true; return; }
    camera.updateMatrixWorld();
    const position = anchor.clone().project(camera);
    const visible = element.clientWidth > 0 && element.clientHeight > 0
      && [position.x, position.y, position.z].every(Number.isFinite)
      && Math.abs(position.x) <= 1 && Math.abs(position.y) <= 1 && Math.abs(position.z) <= 1;
    node.hidden = !visible;
    if (visible) {
      node.style.left = `${(position.x + 1) * element.clientWidth / 2}px`;
      node.style.top = `${(1 - position.y) * element.clientHeight / 2}px`;
    }
  };
  return {
    update,
    setTip(landmark) {
      const xyz = [landmark?.x_mm, landmark?.y_mm, landmark?.z_mm];
      anchor = xyz.every((value) => typeof value === "number" && Number.isFinite(value))
        ? new Vector3(...xyz) : null;
      const confirmed = landmark?.valid === true;
      const label = confirmed ? "尖端（已確認）" : "尖端候選（待補正）";
      const accent = confirmed ? "#34d399" : "#fbbf24";
      node.setAttribute("aria-label", label);
      node.dataset.tipStatus = confirmed ? "confirmed" : "candidate";
      // The crosshair stays on the measured position; the offset label leaves
      // the plant visible. DOM projection keeps it above opaque Gaussian splats.
      node.innerHTML = `<svg width="220" height="90" viewBox="-22 -45 220 90" fill="none" aria-hidden="true" style="position:absolute;left:0;top:0;transform:translate(-22px,-45px)">
        <circle r="9" stroke="#06100c" stroke-width="7"/>
        <circle r="9" stroke="${accent}" stroke-width="3"/>
        <path d="M-18 0 H-12 M12 0 H18 M0 -18 V-12 M0 12 V18 M9 -9 L28 -28 H182" stroke="#06100c" stroke-width="6"/>
        <path d="M-18 0 H-12 M12 0 H18 M0 -18 V-12 M0 12 V18 M9 -9 L28 -28 H182" stroke="${accent}" stroke-width="2"/>
        <circle r="2" fill="${accent}"/>
        <rect x="27" y="-44" width="156" height="26" rx="6" fill="#06100c" stroke="${accent}"/>
        <text x="105" y="-26" text-anchor="middle" fill="${accent}" font-size="14" font-weight="700" font-family="sans-serif">${label}</text>
      </svg>`;
      update();
    },
    dispose() { anchor = null; layer.remove(); },
  };
}

export function createModelMarkerLayer({
  element,
  camera,
  pickPoint,
  onSelect,
  onMove,
  onRemove,
  onDragState,
  onNotice,
  tipPicking = false,
}) {
  // The splat viewer renders its Gaussian pass after the Three.js scene.
  // Project real world anchors into a DOM layer so opaque splats cannot cover
  // the markers and camera zoom cannot shrink their screen size.
  const layer = document.createElement("div");
  layer.className = "pointer-events-none absolute inset-0 z-10 overflow-hidden";
  layer.dataset.modelMarkers = "";
  element.appendChild(layer);
  let markers = [];
  let disabled = false;
  let drag = null;

  const finishDrag = () => {
    if (!drag) return null;
    const previous = drag;
    drag = null;
    previous.marker.anchor = previous.anchor;
    if (previous.marker.node.hasPointerCapture(previous.pointerId)) {
      previous.marker.node.releasePointerCapture(previous.pointerId);
    }
    onDragState(false);
    return previous;
  };

  const cancelDrag = () => {
    finishDrag();
    update();
  };

  const createMarker = (pointId) => {
    const node = document.createElement("button");
    node.type = "button";
    node.className = "pointer-events-auto absolute size-9 -translate-x-1/2 -translate-y-1/2 rounded-full cursor-grab active:cursor-grabbing focus-visible:outline-2 focus-visible:outline-emerald-300 disabled:cursor-default";
    node.style.touchAction = "none";
    const marker = { node, pointId };
    const listeners = {
      pointerdown(event) {
        if (disabled || event.button !== 0 || !event.isPrimary || drag) return;
        event.preventDefault();
        event.stopPropagation();
        node.focus({ preventScroll: true });
        const bounds = element.getBoundingClientRect();
        drag = {
          marker, pointerId: event.pointerId, x: event.clientX, y: event.clientY,
          offsetX: event.clientX - bounds.left - parseFloat(node.style.left),
          offsetY: event.clientY - bounds.top - parseFloat(node.style.top),
          anchor: marker.anchor.clone(), moved: false,
        };
        node.setPointerCapture(event.pointerId);
        onDragState(true);
        onSelect(pointId);
      },
      pointermove(event) {
        if (!drag || drag.marker !== marker || drag.pointerId !== event.pointerId) return;
        event.preventDefault();
        event.stopPropagation();
        if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 5) drag.moved = true;
        if (!drag.moved) return;
        const hit = pickPoint(event.clientX - drag.offsetX, event.clientY - drag.offsetY);
        marker.anchor = hit?.anchor ?? drag.anchor;
        update();
      },
      pointerup(event) {
        if (!drag || drag.marker !== marker || drag.pointerId !== event.pointerId) return;
        event.preventDefault();
        event.stopPropagation();
        const previous = finishDrag();
        if (previous.moved) {
          const hit = pickPoint(event.clientX - previous.offsetX, event.clientY - previous.offsetY);
          if (hit) {
            if (onMove(pointId, hit.pointId) !== false) {
              marker.anchor = hit.anchor;
              onNotice("");
            }
          } else onNotice("請拖到清楚的模型位置，原標記已保留。");
        }
        update();
      },
      pointercancel(event) {
        if (drag?.marker === marker && drag.pointerId === event.pointerId) cancelDrag();
      },
      lostpointercapture(event) {
        if (drag?.marker === marker && drag.pointerId === event.pointerId) cancelDrag();
      },
      contextmenu(event) {
        event.preventDefault();
        event.stopPropagation();
        if (disabled) return;
        cancelDrag();
        onRemove(pointId);
      },
      keydown(event) {
        if (disabled) return;
        if (event.key === "Escape" && drag) {
          event.preventDefault();
          event.stopPropagation();
          cancelDrag();
        } else if (["Delete", "Backspace"].includes(event.key)) {
          event.preventDefault();
          event.stopPropagation();
          cancelDrag();
          onRemove(pointId);
        }
      },
      click(event) {
        event.stopPropagation();
        // Pointer selection happens on press; only keyboard activation selects here.
        if (!disabled && event.detail === 0) onSelect(pointId);
      },
    };
    for (const [name, listener] of Object.entries(listeners)) node.addEventListener(name, listener);
    marker.dispose = () => {
      for (const [name, listener] of Object.entries(listeners)) node.removeEventListener(name, listener);
      node.remove();
    };
    return marker;
  };

  const update = () => {
    const width = element.clientWidth;
    const height = element.clientHeight;
    camera.updateMatrixWorld();
    for (const { node, anchor } of markers) {
      const position = anchor.clone().project(camera);
      const visible = width > 0 && height > 0
        && Number.isFinite(position.x) && Number.isFinite(position.y) && Number.isFinite(position.z)
        && Math.abs(position.x) <= 1 && Math.abs(position.y) <= 1 && Math.abs(position.z) <= 1;
      node.hidden = !visible;
      if (visible) {
        node.style.left = `${(position.x + 1) * width / 2}px`;
        node.style.top = `${(1 - position.y) * height / 2}px`;
      }
    }
  };

  return {
    update,
    setMarkers(anchors) {
      const previous = new Map(markers.map((marker) => [marker.pointId, marker]));
      const ids = new Set(anchors.map(({ pointId }) => pointId));
      if (drag && !ids.has(drag.marker.pointId)) cancelDrag();
      markers = anchors.map(({ anchor, pointId, number, selected }) => {
        const marker = previous.get(pointId) ?? createMarker(pointId);
        const { node } = marker;
        if (drag?.marker !== marker) marker.anchor = anchor;
        node.disabled = disabled;
        node.setAttribute("aria-label", tipPicking ? "尖端標記，拖動調整，右鍵或 Delete 刪除尖端" : `第 ${number} 組模型參照點，拖動調整，右鍵或 Delete 刪除此組`);
        node.setAttribute("aria-pressed", String(selected));
        node.dataset.modelPoint = String(number);
        node.dataset.pointId = String(pointId);
        node.dataset.selected = String(selected);
        const accent = selected ? "#34d399" : "#ffffff";
        const badgeX = (number - 1) % 4 < 2 ? 24 : -24;
        const badgeY = number % 2 ? -24 : 24;
        const ringRadius = selected ? 9 : 7;
        // The crosshair centre is the exact anchor. Offset numbering leaves
        // the underlying bud/leaf tip visible; dark outlines contrast with
        // both bright foliage and the black enclosure.
        node.innerHTML = `<svg width="80" height="80" viewBox="-40 -40 80 80" fill="none" aria-hidden="true" style="pointer-events:none;position:absolute;left:50%;top:50%;transform:translate(-50%,-50%)">
          <path d="M0 0 L${badgeX} ${badgeY}" stroke="#06100c" stroke-width="4"/>
          <path d="M0 0 L${badgeX} ${badgeY}" stroke="${accent}" stroke-width="1.5"/>
          <circle r="${ringRadius}" stroke="#06100c" stroke-width="6"/>
          <circle r="${ringRadius}" stroke="${accent}" stroke-width="2"/>
          <path d="M-14 0 H-10 M10 0 H14 M0 -14 V-10 M0 10 V14" stroke="#06100c" stroke-width="5"/>
          <path d="M-14 0 H-10 M10 0 H14 M0 -14 V-10 M0 10 V14" stroke="${accent}" stroke-width="2"/>
          <circle r="2" fill="${accent}" stroke="#06100c" stroke-width="1"/>
          <circle cx="${badgeX}" cy="${badgeY}" r="14" fill="${selected ? "#34d399" : "#07130f"}" stroke="#06100c" stroke-width="6"/>
          <circle cx="${badgeX}" cy="${badgeY}" r="14" stroke="#ffffff" stroke-width="2"/>
          <text x="${badgeX}" y="${badgeY + 1}" fill="${selected ? "#052e16" : "#ffffff"}" font-size="16" font-weight="800" font-family="sans-serif" text-anchor="middle" dominant-baseline="central">${tipPicking ? "尖" : number}</text>
          <circle cx="${badgeX}" cy="${badgeY}" r="16" fill="transparent" style="pointer-events:all"/>
        </svg>`;
        if (!node.parentNode) layer.appendChild(node);
        return marker;
      });
      for (const [id, marker] of previous) if (!ids.has(id)) marker.dispose();
      // Keep keyboard traversal in pair order, without detaching a captured pointer.
      if (!drag && markers.some(({ node }, index) => layer.children[index] !== node)) {
        layer.replaceChildren(...markers.map(({ node }) => node));
      }
      update();
    },
    setDisabled(locked) {
      disabled = locked;
      if (disabled) cancelDrag();
      for (const { node } of markers) node.disabled = disabled;
    },
    dispose() {
      finishDrag();
      for (const marker of markers) marker.dispose();
      markers = [];
      layer.remove();
    },
  };
}
