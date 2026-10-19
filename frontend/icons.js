// Local line icons shared by navigation and guided pages. No network dependency.
export function icon(name, size = 20) {
  const paths = {
    home: "m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z",
    plus: "M12 5v14M5 12h14", arrow: "M5 12h14m-5-5 5 5-5 5",
    in: "M7 5v14m-4-4 4 4 4-4M14 7h7m-7 5h5",
    out: "M7 19V5m-4 4 4-4 4 4M14 12h7m-7 5h5",
    chat: "M20 11a8 8 0 0 1-8 8H5l-3 3V11a9 9 0 0 1 18 0ZM7 10h8m-8 4h5",
    book: "M4 3h14a2 2 0 0 1 2 2v16H5a2 2 0 0 1-2-2V5a2 2 0 0 1 1-2ZM7 3v18m4-12h5m-5 4h5",
    people: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.87M12 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Zm4-3a4 4 0 0 1 0 8",
    more: "M5 12h.01M12 12h.01M19 12h.01",
    bell: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-8 12h4",
    calendar: "M4 5h16v16H4ZM8 3v4m8-4v4M4 11h16",
    check: "m5 12 4 4L19 6", bill: "M6 3h12v18l-3-2-3 2-3-2-3 2ZM9 8h6m-6 4h6",
    sun: "M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
    moon: "M20.5 13a8.5 8.5 0 0 1-9.5-9.5A8.5 8.5 0 1 0 20.5 13Z",
  };
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [k, val] of Object.entries({ viewBox: "0 0 24 24", width: size, height: size, fill: "none", stroke: "currentColor", "stroke-width": name === "more" ? 4 : 1.7, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", focusable: "false" })) svg.setAttribute(k, val);
  const path = document.createElementNS(svg.namespaceURI, "path"); path.setAttribute("d", paths[name] || paths.book); svg.appendChild(path);
  return svg;
}
