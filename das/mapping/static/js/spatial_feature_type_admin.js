(function () {
  "use strict";

  function field(name) { return document.getElementById("id_" + name); }

  function strVal(name, fallback) {
    const el = field(name);
    if (!el) return fallback;
    return el.value.trim() || el.defaultValue.trim() || fallback;
  }

  function numVal(name, fallback) {
    const el = field(name);
    if (!el || el.value === "") return fallback;
    const v = parseFloat(el.value);
    return isNaN(v) ? fallback : v;
  }

  function findFieldset(heading) {
    for (const fs of document.querySelectorAll("fieldset.module")) {
      if (fs.querySelector("h2")?.textContent.trim() === heading) return fs;
    }
    return null;
  }

  function svgEl(tag) {
    return document.createElementNS("http://www.w3.org/2000/svg", tag);
  }

  // Wrap all .form-row children in a flex layout with the preview on the right.
  function insertPreviewBeside(fs, svg) {
    const rows = [...fs.querySelectorAll(":scope > .form-row")];
    const h2 = fs.querySelector("h2");

    const wrapper = document.createElement("div");
    wrapper.className = "format-preview-layout";

    const fieldsCol = document.createElement("div");
    fieldsCol.className = "format-preview-fields";
    rows.forEach(row => fieldsCol.appendChild(row));

    const previewCol = document.createElement("div");
    previewCol.className = "format-preview-col";
    svg.classList.add("format-preview");
    previewCol.appendChild(svg);

    wrapper.appendChild(fieldsCol);
    wrapper.appendChild(previewCol);

    h2 ? h2.insertAdjacentElement("afterend", wrapper) : fs.appendChild(wrapper);
  }

  // Paint the filled portion of the track via a linear-gradient so it reaches
  // the thumb's right edge at max. Firefox uses ::-moz-range-progress (CSS-only),
  // but WebKit/Chromium need this JS-driven background.
  function paintRangeFill(el) {
    const min = parseFloat(el.min) || 0;
    const max = parseFloat(el.max) || 1;
    const parsed = parseFloat(el.value);
    const val = Number.isNaN(parsed) ? min : parsed;
    const pct = max === min ? 100 : ((val - min) / (max - min)) * 100;
    el.style.background =
      `linear-gradient(to right, #2563eb 0 ${pct}%, #d1d5db ${pct}% 100%)`;
  }

  // Show current value next to a range slider and keep it in sync.
  function addSliderOutput(name) {
    const el = field(name);
    if (!el || el.type !== "range") return;
    el.classList.add("opacity-slider");
    const out = document.createElement("output");
    out.className = "slider-output";
    if (el.id) out.setAttribute("for", el.id);
    out.setAttribute("aria-live", "polite");
    out.textContent = parseFloat(el.value).toFixed(2);
    el.insertAdjacentElement("afterend", out);
    paintRangeFill(el);
    el.addEventListener("input", () => {
      out.textContent = parseFloat(el.value).toFixed(2);
      paintRangeFill(el);
    });
  }

  function watchFields(names, callback) {
    for (const name of names) {
      field(name)?.addEventListener("input", callback);
      field(name)?.addEventListener("change", callback);
    }
  }

  // ---- Sync presentation JSON textarea from formatting controls ----
  const FORM_FIELD_TO_JSON_KEY = {
    stroke:            "stroke",
    stroke_width:      "stroke-width",
    stroke_opacity:    "stroke-opacity",
    point_image:       "image",
    point_width:       "width",
    point_height:      "height",
    fill_opacity:      "fill-opacity",
    fill_outline_color:"fill-outline-color",
    fill_color:        "fill",
  };
  const INTEGER_FIELDS = new Set(["stroke_width"]);
  const FLOAT_FIELDS   = new Set(["stroke_opacity", "point_width", "point_height", "fill_opacity"]);

  function syncPresentationJson() {
    const el = field("presentation");
    if (!el) return;

    // Start with the existing JSON so unknown keys are preserved.
    let base = {};
    try {
      const parsed = JSON.parse(el.value || "{}");
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        base = parsed;
      }
    } catch {}

    const updated = { ...base };
    for (const [fieldName, jsonKey] of Object.entries(FORM_FIELD_TO_JSON_KEY)) {
      const inputEl = field(fieldName);
      if (!inputEl) continue;
      const raw = inputEl.value.trim();
      if (!raw) {
        delete updated[jsonKey];
        continue;
      }
      if (INTEGER_FIELDS.has(fieldName)) {
        const n = parseInt(raw, 10);
        if (!isNaN(n)) updated[jsonKey] = n;
      } else if (FLOAT_FIELDS.has(fieldName)) {
        const n = parseFloat(raw);
        if (!isNaN(n)) updated[jsonKey] = n;
      } else {
        updated[jsonKey] = raw;
      }
    }
    el.value = JSON.stringify(updated, null, 2);
  }

  // ---- Line Formatting preview ----
  function buildLinePreview() {
    const fs = findFieldset("Line Formatting");
    if (!fs) return;

    const svg = svgEl("svg");
    svg.setAttribute("viewBox", "0 0 350 120");
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

    const line = svgEl("line");
    line.setAttribute("x1", "16");
    line.setAttribute("y1", "60");
    line.setAttribute("x2", "334");
    line.setAttribute("y2", "60");
    svg.appendChild(line);
    insertPreviewBeside(fs, svg);

    function update() {
      line.setAttribute("stroke", strVal("stroke", "#FF6600"));
      line.setAttribute("stroke-width", numVal("stroke_width", 2));
      line.setAttribute("stroke-opacity", numVal("stroke_opacity", 1));
    }
    watchFields(["stroke", "stroke_width", "stroke_opacity"], update);
    update();
  }

  // ---- Point Formatting preview ----
  function buildPointPreview() {
    const fs = findFieldset("Point Formatting");
    if (!fs) return;

    const container = document.createElement("div");
    container.style.display = "flex";
    container.style.alignItems = "center";
    container.style.justifyContent = "center";

    const img = document.createElement("img");
    img.alt = "";
    container.appendChild(img);
    insertPreviewBeside(fs, container);
    container.classList.add("format-preview--plain");

    function update() {
      const src = strVal("point_image", "");
      const w = numVal("point_width", 20);
      const h = numVal("point_height", 20);
      img.style.width = w + "px";
      img.style.height = h + "px";
      if (src) {
        img.src = src;
        img.style.display = "block";
      } else {
        img.src = "";
        img.style.display = "none";
      }
    }
    watchFields(["point_image", "point_width", "point_height"], update);
    update();
  }

  // ---- Polygon Formatting preview ----
  function buildPolygonPreview() {
    const fs = findFieldset("Polygon Formatting");
    if (!fs) return;

    const svg = svgEl("svg");
    svg.setAttribute("viewBox", "0 0 350 120");
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

    const rect = svgEl("rect");
    rect.setAttribute("x", "20");
    rect.setAttribute("y", "10");
    rect.setAttribute("width", "310");
    rect.setAttribute("height", "100");
    rect.setAttribute("rx", "4");
    svg.appendChild(rect);
    insertPreviewBeside(fs, svg);

    function update() {
      rect.setAttribute("fill", strVal("fill_color", "#FF6600"));
      rect.setAttribute("fill-opacity", numVal("fill_opacity", 0.25));
      const borderStroke = strVal("border_color", "") || strVal("fill_outline_color", "#FF6600");
      rect.setAttribute("stroke", borderStroke);
      rect.setAttribute("stroke-width", "2");
    }
    watchFields(["fill_color", "fill_opacity", "fill_outline_color", "border_color"], update);
    update();
  }

  function setupPresentationValidation() {
    const el = field("presentation");
    if (!el) return;

    // Pretty-print on load.
    const raw = el.value.trim();
    if (raw && raw !== "null") {
      try { el.value = JSON.stringify(JSON.parse(raw), null, 2); } catch {}
    }

    el.addEventListener("input", function () {
      el.setCustomValidity("");
    });

    el.closest("form")?.addEventListener("submit", function (e) {
      const raw = el.value.trim();
      if (!raw || raw === "null") {
        el.setCustomValidity("");
        return;
      }
      try {
        const parsed = JSON.parse(raw);
        el.value = JSON.stringify(parsed, null, 2);
        el.setCustomValidity("");
      } catch {
        el.setCustomValidity("Invalid JSON — please fix before saving.");
        el.reportValidity();
        e.preventDefault();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    addSliderOutput("stroke_opacity");
    addSliderOutput("fill_opacity");
    buildLinePreview();
    buildPointPreview();
    buildPolygonPreview();
    watchFields(Object.keys(FORM_FIELD_TO_JSON_KEY), syncPresentationJson);
    setupPresentationValidation();
  });
})();
