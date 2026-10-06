export function createModelMarkerLayer({
  element,
  camera,
}) {
  // The splat viewer renders its Gaussian pass after the Three.js scene.
  // Project real world anchors into a DOM layer so opaque splats cannot cover
  // the markers and camera zoom cannot shrink their screen size.
  const layer = document.createElement("div");
  layer.className = "pointer-events-none absolute inset-0 z-10 overflow-hidden";
  layer.setAttribute("aria-hidden", "true");
  layer.dataset.modelMarkers = "";
  element.appendChild(layer);
  let markers = [];

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
      markers = anchors.map(({ anchor, number, selected }) => {
        const node = document.createElement("div");
        node.className = "pointer-events-none absolute size-20 -translate-x-1/2 -translate-y-1/2";
        node.dataset.modelPoint = String(number);
        node.dataset.selected = String(selected);
        const accent = selected ? "#34d399" : "#ffffff";
        const badgeX = (number - 1) % 4 < 2 ? 24 : -24;
        const badgeY = number % 2 ? -24 : 24;
        const ringRadius = selected ? 9 : 7;
        // The crosshair centre is the exact anchor. Offset numbering leaves
        // the underlying bud/leaf tip visible; dark outlines contrast with
        // both bright foliage and the black enclosure.
        node.innerHTML = `<svg width="80" height="80" viewBox="-40 -40 80 80" fill="none">
          <path d="M0 0 L${badgeX} ${badgeY}" stroke="#06100c" stroke-width="4"/>
          <path d="M0 0 L${badgeX} ${badgeY}" stroke="${accent}" stroke-width="1.5"/>
          <circle r="${ringRadius}" stroke="#06100c" stroke-width="6"/>
          <circle r="${ringRadius}" stroke="${accent}" stroke-width="2"/>
          <path d="M-14 0 H-10 M10 0 H14 M0 -14 V-10 M0 10 V14" stroke="#06100c" stroke-width="5"/>
          <path d="M-14 0 H-10 M10 0 H14 M0 -14 V-10 M0 10 V14" stroke="${accent}" stroke-width="2"/>
          <circle r="2" fill="${accent}" stroke="#06100c" stroke-width="1"/>
          <circle cx="${badgeX}" cy="${badgeY}" r="14" fill="${selected ? "#34d399" : "#07130f"}" stroke="#06100c" stroke-width="6"/>
          <circle cx="${badgeX}" cy="${badgeY}" r="14" stroke="#ffffff" stroke-width="2"/>
          <text x="${badgeX}" y="${badgeY + 1}" fill="${selected ? "#052e16" : "#ffffff"}" font-size="16" font-weight="800" font-family="sans-serif" text-anchor="middle" dominant-baseline="central">${number}</text>
        </svg>`;
        return { node, anchor };
      });
      layer.replaceChildren(...markers.map(({ node }) => node));
      update();
    },
    dispose() {
      markers = [];
      layer.remove();
    },
  };
}
