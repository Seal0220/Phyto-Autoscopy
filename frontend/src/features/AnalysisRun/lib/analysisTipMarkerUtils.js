export function tipMarkerSvg({
  confirmed = true,
  interactive = false,
  label = "尖端",
} = {}) {
  const accent = confirmed ? "#34d399" : "#fbbf24";
  const title = label.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
  return `<svg width="80" height="80" viewBox="-40 -40 80 80" fill="none" aria-hidden="true" style="pointer-events:none;position:absolute;left:50%;top:50%;transform:translate(-50%,-50%)">
    <title>${title}</title>
    <path d="M6.36 -6.36 L24 -24" stroke="#06100c" stroke-width="4"/>
    <path d="M6.36 -6.36 L24 -24" stroke="${accent}" stroke-width="1.5"/>
    <circle r="9" stroke="#06100c" stroke-width="6"/>
    <circle r="9" stroke="${accent}" stroke-width="2"/>
    <path d="M-14 0 H-10 M10 0 H14 M0 -14 V-10 M0 10 V14" stroke="#06100c" stroke-width="5"/>
    <path d="M-14 0 H-10 M10 0 H14 M0 -14 V-10 M0 10 V14" stroke="${accent}" stroke-width="2"/>
    <circle cx="24" cy="-24" r="14" fill="${accent}" stroke="#06100c" stroke-width="6"/>
    <circle cx="24" cy="-24" r="14" stroke="#ffffff" stroke-width="2"/>
    <text x="24" y="-23" fill="#052e16" font-size="16" font-weight="800" font-family="sans-serif" text-anchor="middle" dominant-baseline="central">尖</text>
    ${interactive ? '<circle cx="24" cy="-24" r="16" fill="transparent" style="pointer-events:all"/>' : ""}
  </svg>`;
}
