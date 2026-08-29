// Column resize + hide/show for every real data table in the app. Auto-enhances
// any <table> that has a <thead><tr><th>...</th></tr> — opt out of a specific
// table with the `data-plain-table` attribute (e.g. small key-value tables that
// aren't really a "data grid"). Per-table state (which columns are hidden, and
// any custom widths) is remembered in localStorage, keyed by the page's first
// path segment + a signature built from the header labels — so e.g. every
// invoice's item table (same headers, different sale id) shares one saved
// layout, while the Sales list and a Sales invoice table (different headers)
// are tracked separately.
(function () {
  "use strict";

  var STORAGE_PREFIX = "tableTools:";
  var MIN_COL_WIDTH = 40;

  function headerRow(table) {
    var thead = table.tHead;
    if (!thead || !thead.rows.length) return null;
    return Array.prototype.slice.call(thead.rows[0].cells);
  }

  // A <th>'s visible text may include a sort-direction indicator
  // (".data-table-sort-indicator", from data-table.js / server_table.html)
  // that changes with the current sort state — strip it so the column label
  // and the localStorage key signature stay stable regardless of sort order.
  function cleanLabel(th) {
    var clone = th.cloneNode(true);
    clone.querySelectorAll(".data-table-sort-indicator, .tt-resize-handle").forEach(function (el) {
      el.remove();
    });
    return clone.textContent.trim();
  }

  function storageKey(table, headers) {
    var sig = headers.map(cleanLabel).join("|");
    var pathPrefix = location.pathname.split("/").slice(0, 2).join("/") || "/";
    return STORAGE_PREFIX + pathPrefix + "::" + sig;
  }

  function loadState(key) {
    try {
      var raw = localStorage.getItem(key);
      if (!raw) return { widths: {}, hidden: [] };
      var parsed = JSON.parse(raw);
      return { widths: parsed.widths || {}, hidden: parsed.hidden || [] };
    } catch (e) {
      return { widths: {}, hidden: [] };
    }
  }

  function saveState(key, state) {
    try {
      localStorage.setItem(key, JSON.stringify(state));
    } catch (e) { /* storage full/unavailable — resize/hide just won't persist */ }
  }

  function ensureColgroup(table, colCount) {
    var colgroup = table.querySelector(":scope > colgroup");
    if (colgroup && colgroup.children.length === colCount) return colgroup;
    if (colgroup) colgroup.remove();
    colgroup = document.createElement("colgroup");
    for (var i = 0; i < colCount; i++) colgroup.appendChild(document.createElement("col"));
    table.insertBefore(colgroup, table.firstChild);
    return colgroup;
  }

  function enhance(table) {
    if (table.dataset.ttEnhanced === "1" || table.hasAttribute("data-plain-table")) return;
    var headers = headerRow(table);
    if (!headers || headers.length < 2) return;
    for (var h = 0; h < headers.length; h++) {
      if (headers[h].colSpan && headers[h].colSpan > 1) return; // ambiguous width/hide math — skip
    }
    table.dataset.ttEnhanced = "1";

    var key = storageKey(table, headers);
    var state = loadState(key);
    var colgroup = ensureColgroup(table, headers.length);
    var cols = Array.prototype.slice.call(colgroup.children);

    var wrap = document.createElement("div");
    wrap.className = "tt-wrap";
    table.parentNode.insertBefore(wrap, table);

    var toolbar = document.createElement("div");
    toolbar.className = "tt-toolbar no-print";
    var toggleBtn = document.createElement("button");
    toggleBtn.type = "button";
    toggleBtn.className = "tt-toggle-btn";
    var iconTemplate = document.getElementById("tt-columns-icon");
    if (iconTemplate) toggleBtn.appendChild(iconTemplate.content.cloneNode(true));
    var badge = document.createElement("span");
    badge.className = "tt-hidden-badge";
    toggleBtn.appendChild(badge);
    toolbar.appendChild(toggleBtn);
    wrap.appendChild(toolbar);
    wrap.appendChild(table);

    var menu = document.createElement("div");
    menu.className = "tt-menu";
    document.body.appendChild(menu);

    function updateBadge() {
      var n = state.hidden.length;
      badge.textContent = n > 0 ? String(n) : "";
      badge.classList.toggle("show", n > 0);
      toggleBtn.classList.toggle("has-hidden", n > 0);
      toggleBtn.title = n > 0
        ? n + " column" + (n > 1 ? "s" : "") + " hidden — click to show"
        : "Show/hide columns";
      toggleBtn.setAttribute("aria-label", toggleBtn.title);
    }

    function applyHidden() {
      // display:none on a <col> is a no-op in every browser — <col> boxes
      // don't generate a visible box themselves, so visibility:collapse
      // (the CSS2 table-column mechanism) is what removes the column's
      // cells from rendering while the rest of the table reflows around it.
      cols.forEach(function (col, i) {
        col.style.visibility = state.hidden.indexOf(i) !== -1 ? "collapse" : "";
      });
      // A collapsed header <th> correctly gets width:0, but its sort-indicator
      // span (added by data-table.js) is plain static inline content — with
      // the cell's default overflow:visible, that content still paints past
      // the zero-width box instead of disappearing. For any column that isn't
      // the last one, the next cell's opaque background happens to paint over
      // that leftover sliver, hiding the bug — but the *last* column has
      // nothing after it to cover it, leaving its sort arrow floating with no
      // header text under it. overflow:hidden on just the header cell clips
      // it without touching `display` (unlike display:none, which would
      // remove the cell from the row entirely and shift every later cell's
      // column-index alignment against the colgroup).
      headers.forEach(function (th, i) {
        th.style.overflow = state.hidden.indexOf(i) !== -1 ? "hidden" : "";
      });
      updateBadge();
    }

    function applyWidths() {
      if (Object.keys(state.widths).length === 0) return;
      table.style.tableLayout = "fixed";
      cols.forEach(function (col, i) {
        if (state.widths[i]) col.style.width = state.widths[i] + "px";
      });
    }

    function wireResize(th, index) {
      var handle = document.createElement("span");
      handle.className = "tt-resize-handle";
      th.style.position = th.style.position || "relative";
      th.appendChild(handle);

      handle.addEventListener("mousedown", function (e) {
        e.preventDefault();
        e.stopPropagation();
        var startX = e.clientX;
        var startWidths = headers.map(function (hh) { return hh.getBoundingClientRect().width; });
        table.style.tableLayout = "fixed";
        cols.forEach(function (col, i) { col.style.width = startWidths[i] + "px"; });

        function onMove(ev) {
          var delta = ev.clientX - startX;
          cols[index].style.width = Math.max(MIN_COL_WIDTH, startWidths[index] + delta) + "px";
        }
        function onUp() {
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
          cols.forEach(function (col, i) {
            var px = parseFloat(col.style.width);
            if (px) state.widths[i] = Math.round(px);
          });
          saveState(key, state);
        }
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
    }

    headers.forEach(function (th, i) {
      var label = cleanLabel(th);
      if (!label) return; // unlabeled columns (row actions, checkboxes) stay fixed/visible

      var item = document.createElement("label");
      item.className = "tt-menu-item";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = state.hidden.indexOf(i) === -1;
      cb.addEventListener("change", function () {
        var idx = state.hidden.indexOf(i);
        if (cb.checked && idx !== -1) state.hidden.splice(idx, 1);
        if (!cb.checked && idx === -1) state.hidden.push(i);
        applyHidden();
        saveState(key, state);
      });
      item.appendChild(cb);
      item.appendChild(document.createTextNode(" " + label));
      menu.appendChild(item);

      wireResize(th, i);
    });

    var resetBtn = document.createElement("button");
    resetBtn.type = "button";
    resetBtn.className = "tt-menu-reset";
    resetBtn.textContent = "Reset columns";
    resetBtn.addEventListener("click", function () {
      state.hidden = [];
      state.widths = {};
      cols.forEach(function (col) { col.style.width = ""; });
      table.style.tableLayout = "";
      applyHidden();
      saveState(key, state);
      menu.querySelectorAll("input[type=checkbox]").forEach(function (cb) { cb.checked = true; });
    });
    menu.appendChild(resetBtn);

    function positionMenu() {
      var rect = toggleBtn.getBoundingClientRect();
      menu.style.top = rect.bottom + 4 + "px";
      menu.style.left = Math.max(4, rect.right - menu.offsetWidth) + "px";
    }

    toggleBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      var willOpen = !menu.classList.contains("open");
      document.querySelectorAll(".tt-menu.open").forEach(function (m) { m.classList.remove("open"); });
      if (willOpen) {
        menu.classList.add("open");
        positionMenu();
      }
    });
    document.addEventListener("click", function (e) {
      if (!menu.contains(e.target) && e.target !== toggleBtn) menu.classList.remove("open");
    });
    window.addEventListener("resize", function () {
      if (menu.classList.contains("open")) positionMenu();
    });

    applyHidden();
    applyWidths();
  }

  window.TableTools = { enhance: enhance };

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("table").forEach(function (t) {
      try { enhance(t); } catch (e) { /* a table-tools bug should never break the page */ }
    });
  });
})();
