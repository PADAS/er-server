"use strict";

// ── Name → Value auto-populate ─────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function () {
  var nameField = document.querySelector('[name="name"]');
  var valueField = document.querySelector('[name="value"]');

  if (!nameField) return;

  var autoPopulated = false;

  if (valueField) {
    valueField.addEventListener("input", function () {
      autoPopulated = false;
    });
  }

  nameField.addEventListener("blur", function () {
    var name = nameField.value;
    setTimeout(function () {
      if (valueField && (valueField.value === "" || autoPopulated)) {
        valueField.value = name.trim().toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
        autoPopulated = true;
      }
    }, 0);
  });
});

// ── Up/down reordering for chosen event-types ──────────────────────────────
// Poll for #id_event_types_to because SelectFilter2.js creates it on
// window.load and our script may execute before that.
function initCommunityInputReorder() {
  var toBox = document.getElementById("id_event_types_to");

  if (!toBox) {
    setTimeout(initCommunityInputReorder, 100);
    return;
  }

  if (toBox.dataset.reorderInit) return;
  toBox.dataset.reorderInit = "1";

  var cacheId = "id_event_types_to";

  // Reorder both the SelectBox cache and the DOM to match a given list of PKs.
  // SelectBox.redisplay() rebuilds the DOM from the cache, so both must be kept
  // in sync — DOM-only changes are wiped whenever redisplay() is called.
  function applyOrder(orderedPks) {
    var cache = window.SelectBox && window.SelectBox.cache[cacheId];
    if (!cache) return;

    // Build a map for O(1) lookup, then rebuild cache array in the desired order.
    var byValue = {};
    cache.forEach(function (item) { byValue[item.value] = item; });

    var reordered = [];
    orderedPks.forEach(function (pk) {
      if (byValue[pk]) reordered.push(byValue[pk]);
    });
    // Append any items not mentioned in orderedPks (e.g. newly added ones).
    cache.forEach(function (item) {
      if (!orderedPks.includes(item.value)) reordered.push(item);
    });

    window.SelectBox.cache[cacheId] = reordered;
    window.SelectBox.redisplay(cacheId);
  }

  // Restore saved order on page load. SelectFilter2 renames the original
  // <select id="id_event_types"> to id="id_event_types_from", so look there.
  var fromSelect = document.getElementById("id_event_types_from");
  var savedOrder = fromSelect && fromSelect.dataset.savedOrder;
  if (savedOrder) {
    applyOrder(savedOrder.split(",").filter(Boolean));
  }

  function moveSelected(direction) {
    var currentOrder = Array.from(toBox.options).map(function (o) { return o.value; });
    var selectedSet = new Set(
      Array.from(toBox.options).filter(function (o) { return o.selected; }).map(function (o) { return o.value; })
    );

    if (direction === "up") {
      for (var i = 1; i < currentOrder.length; i++) {
        if (selectedSet.has(currentOrder[i]) && !selectedSet.has(currentOrder[i - 1])) {
          var tmp = currentOrder[i - 1];
          currentOrder[i - 1] = currentOrder[i];
          currentOrder[i] = tmp;
        }
      }
    } else {
      for (var i = currentOrder.length - 2; i >= 0; i--) {
        if (selectedSet.has(currentOrder[i]) && !selectedSet.has(currentOrder[i + 1])) {
          var tmp = currentOrder[i + 1];
          currentOrder[i + 1] = currentOrder[i];
          currentOrder[i] = tmp;
        }
      }
    }

    applyOrder(currentOrder);

    // Re-select the same items after redisplay rebuilds the DOM.
    Array.from(toBox.options).forEach(function (o) {
      o.selected = selectedSet.has(o.value);
    });
  }

  function makeBtn(label, title) {
    var btn = document.createElement("a");
    btn.href = "#";
    btn.textContent = label;
    btn.title = title;
    btn.style.cssText = "display:block; text-align:center; padding:2px 6px; margin:2px 0; text-decoration:none; font-size:16px;";
    return btn;
  }

  var btnUp = makeBtn("▲", "Move up");
  var btnDown = makeBtn("▼", "Move down");

  btnUp.addEventListener("click", function (e) { e.preventDefault(); moveSelected("up"); });
  btnDown.addEventListener("click", function (e) { e.preventDefault(); moveSelected("down"); });

  var btnContainer = document.createElement("div");
  btnContainer.style.cssText = "display:flex; flex-direction:column; justify-content:flex-start; margin-left:6px;";
  btnContainer.appendChild(btnUp);
  btnContainer.appendChild(btnDown);

  // Wrap the entire .selector widget + buttons in a flex row so the buttons
  // sit to the right of the whole widget without disturbing its internal layout.
  var selectorDiv = toBox.closest(".selector");
  var wrapper = document.createElement("div");
  wrapper.style.cssText = "display:inline-flex; align-items:flex-start;";
  selectorDiv.parentNode.insertBefore(wrapper, selectorDiv);
  wrapper.appendChild(selectorDiv);
  wrapper.appendChild(btnContainer);

  // Push the button container down so it aligns with the select box, not the h2 header.
  btnContainer.style.marginTop = (toBox.offsetTop - selectorDiv.offsetTop) + "px";

  // On submit, inject hidden inputs carrying the chosen values in their current
  // order, then disable the _to select so SelectFilter2's select_all() has no
  // visible effect.  Both handlers run synchronously in the same JS tick, so
  // the browser never renders the "all selected" state between them.
  var form = toBox.closest("form");
  if (form) {
    form.addEventListener("submit", function () {
      var pks = Array.from(toBox.options).map(function (o) { return o.value; });

      pks.forEach(function (pk) {
        var input = document.createElement("input");
        input.type = "hidden";
        input.name = "event_types";
        input.value = pk;
        form.appendChild(input);
      });

      // Disable the select so its values aren't double-submitted.
      toBox.disabled = true;
    });
  }
}

document.addEventListener("DOMContentLoaded", initCommunityInputReorder);

// ── QR code panel ───────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function () {
  var valueField = document.getElementById("id_value");
  if (!valueField) return;

  // Build the panel
  var panel = document.createElement("div");
  panel.style.cssText = "margin-left:24px; min-width:180px; display:flex; flex-direction:column; align-items:center;";

  var qrContainer = document.createElement("div");
  qrContainer.id = "community-input-qr";
  panel.appendChild(qrContainer);

  var downloadBtn = document.createElement("button");
  downloadBtn.type = "button";
  downloadBtn.textContent = "Download PNG";
  downloadBtn.style.cssText = "margin-top:8px; width:100%;";
  panel.appendChild(downloadBtn);

  var urlRow = document.createElement("div");
  urlRow.style.cssText = "display:flex; align-items:center; margin-top:8px; gap:6px; width:100%;";

  var urlText = document.createElement("span");
  urlText.style.cssText = "font-size:11px; word-break:break-all; flex:1;";
  urlRow.appendChild(urlText);

  var copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.textContent = "Copy";
  copyBtn.style.cssText = "white-space:nowrap; flex-shrink:0;";
  urlRow.appendChild(copyBtn);
  panel.appendChild(urlRow);

  // Insert panel to the right of the first fieldset
  var firstFieldset = document.querySelector("fieldset.module");
  if (!firstFieldset) return;

  var wrapper = document.createElement("div");
  wrapper.style.cssText = "display:flex; align-items:flex-start;";
  firstFieldset.parentNode.insertBefore(wrapper, firstFieldset);
  wrapper.appendChild(firstFieldset);
  wrapper.appendChild(panel);

  function getBaseUrl(value) {
    return window.location.protocol + "//" + window.location.host + "/community/" + encodeURIComponent(value);
  }

  function render(value) {
    var base = getBaseUrl(value);
    var qrUrl = base + "?referer=qr_code";
    urlText.textContent = base;

    qrContainer.innerHTML = "";
    new QRCode(qrContainer, {
      text: qrUrl,
      width: 160,
      height: 160,
      correctLevel: QRCode.CorrectLevel.M,
    });

    panel.style.display = "flex";
  }

  function update() {
    var value = valueField.value.trim();
    if (value) {
      render(value);
    } else {
      panel.style.display = "none";
    }
  }

  downloadBtn.addEventListener("click", function () {
    var canvas = qrContainer.querySelector("canvas");
    if (!canvas) return;
    var a = document.createElement("a");
    a.download = "qr-" + (valueField.value.trim() || "community") + ".png";
    a.href = canvas.toDataURL("image/png");
    a.click();
  });

  copyBtn.addEventListener("click", function () {
    navigator.clipboard.writeText(urlText.textContent).then(function () {
      var orig = copyBtn.textContent;
      copyBtn.textContent = "Copied!";
      setTimeout(function () { copyBtn.textContent = orig; }, 1500);
    });
  });

  valueField.addEventListener("input", update);
  update();
});
