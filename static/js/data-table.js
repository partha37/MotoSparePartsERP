/*
 * Progressive enhancement for <table class="data-table">: adds a
 * whole-table search box, click-to-sort column headers, and a per-column
 * filter row — entirely client-side (all rows are already server-rendered;
 * a single shop's record counts are small enough that no server round trip
 * is needed). Auto-runs on every table carrying the class, so enabling it
 * on a page is just adding the class — no per-page JS wiring required.
 *
 * Columns whose header cell is empty (the usual Edit/Delete actions column)
 * are automatically skipped for both sorting and filtering. Rows that are
 * really an empty-state placeholder (a single <td colspan> — the Jinja
 * "{% else %}No X yet.{% endfor %}" row every list template uses) are
 * detected the same way and left alone rather than sorted/hidden.
 */
(function () {
  const SEARCH_ICON =
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" class="bi bi-search" viewBox="0 0 16 16">' +
    '<path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001q.044.06.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1 1 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0"/></svg>';

  function isPlaceholderRow(tr) {
    const cells = tr.children;
    return cells.length === 1 && cells[0].hasAttribute("colspan");
  }

  function dataRows(tbody) {
    return Array.from(tbody.rows).filter(function (tr) {
      return !isPlaceholderRow(tr) && !tr.classList.contains("data-table-no-match");
    });
  }

  function parseNumeric(text) {
    const m = text.trim().match(/-?[\d,]+(\.\d+)?/);
    if (!m) return null;
    const num = parseFloat(m[0].replace(/,/g, ""));
    return isNaN(num) ? null : num;
  }

  function columnIsNumeric(rows, colIndex) {
    let seen = 0;
    let numeric = 0;
    rows.forEach(function (tr) {
      const cell = tr.children[colIndex];
      const text = cell ? cell.textContent.trim() : "";
      if (!text) return;
      seen++;
      if (parseNumeric(text) !== null) numeric++;
    });
    return seen > 0 && numeric >= seen * 0.5;
  }

  function applyFilters(state) {
    const rows = dataRows(state.tbody);
    const searchQ = state.searchInput ? state.searchInput.value.trim().toLowerCase() : "";
    let anyVisible = false;

    rows.forEach(function (tr) {
      let visible = !searchQ || tr.textContent.toLowerCase().includes(searchQ);
      if (visible) {
        for (let i = 0; i < state.filterInputs.length; i++) {
          const input = state.filterInputs[i];
          if (!input || !input.value.trim()) continue;
          const cell = tr.children[i];
          const cellText = cell ? cell.textContent.toLowerCase() : "";
          if (!cellText.includes(input.value.trim().toLowerCase())) {
            visible = false;
            break;
          }
        }
      }
      tr.classList.toggle("d-none", !visible);
      if (visible) anyVisible = true;
    });

    if (state.noMatchRow) {
      state.noMatchRow.classList.toggle("d-none", anyVisible || rows.length === 0);
    }
  }

  function sortByColumn(state, colIndex) {
    const rows = dataRows(state.tbody);
    const numeric = columnIsNumeric(rows, colIndex);
    const dir = state.sortCol === colIndex && state.sortDir === "asc" ? "desc" : "asc";
    state.sortCol = colIndex;
    state.sortDir = dir;

    const decorated = rows.map(function (tr, i) {
      const cell = tr.children[colIndex];
      const text = cell ? cell.textContent.trim() : "";
      return { tr: tr, i: i, text: text, num: parseNumeric(text) };
    });

    decorated.sort(function (a, b) {
      let cmp;
      if (numeric) {
        const an = a.num === null ? -Infinity : a.num;
        const bn = b.num === null ? -Infinity : b.num;
        cmp = an - bn;
      } else {
        cmp = a.text.toLowerCase().localeCompare(b.text.toLowerCase());
      }
      if (cmp === 0) cmp = a.i - b.i;
      return dir === "desc" ? -cmp : cmp;
    });

    decorated.forEach(function (d) {
      state.tbody.appendChild(d.tr);
    });
    if (state.noMatchRow) state.tbody.appendChild(state.noMatchRow);

    state.headerCells.forEach(function (th, i) {
      const indicator = th.querySelector(".data-table-sort-indicator");
      if (!indicator) return;
      indicator.textContent = i === colIndex ? (dir === "asc" ? "▲" : "▼") : "↕";
    });
  }

  function buildToolbar(table, idPrefix) {
    const toolbar = document.createElement("div");
    toolbar.className = "data-table-toolbar mb-2";
    const group = document.createElement("div");
    group.className = "input-group input-group-sm";
    group.style.maxWidth = "320px";
    group.innerHTML =
      '<span class="input-group-text">' + SEARCH_ICON + "</span>" +
      '<input type="search" class="form-control" id="' + idPrefix + '-search" name="' + idPrefix +
      '-search" placeholder="Search this table…" aria-label="Search this table">';
    toolbar.appendChild(group);
    table.parentNode.insertBefore(toolbar, table);
    return group.querySelector("input");
  }

  function buildFilterRow(table, headerRow, eligible, idPrefix) {
    const filterRow = document.createElement("tr");
    filterRow.className = "data-table-filter-row";
    const inputs = [];
    Array.from(headerRow.children).forEach(function (th, i) {
      const cell = document.createElement("th");
      if (eligible[i]) {
        const input = document.createElement("input");
        input.type = "search";
        input.className = "form-control form-control-sm";
        input.placeholder = "Filter…";
        input.id = idPrefix + "-filter-" + i;
        input.name = idPrefix + "-filter-" + i;
        input.setAttribute("aria-label", "Filter by " + th.textContent.trim());
        cell.appendChild(input);
        inputs.push(input);
      } else {
        inputs.push(null);
      }
      filterRow.appendChild(cell);
    });
    headerRow.parentNode.insertBefore(filterRow, headerRow.nextSibling);
    return inputs;
  }

  function buildNoMatchRow(tbody, colCount) {
    const tr = document.createElement("tr");
    tr.className = "data-table-no-match d-none";
    const td = document.createElement("td");
    td.colSpan = colCount;
    td.className = "text-center text-muted";
    td.textContent = "No rows match your search/filter.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return tr;
  }

  let tableCounter = 0;

  function enhance(table) {
    if (table.dataset.dataTableEnhanced) return;
    table.dataset.dataTableEnhanced = "1";

    const headerRow = table.tHead && table.tHead.rows[0];
    const tbody = table.tBodies[0];
    if (!headerRow || !tbody) return;

    const idPrefix = "data-table-" + (++tableCounter);
    const headerCells = Array.from(headerRow.children);
    const eligible = headerCells.map(function (th) {
      return th.textContent.trim().length > 0;
    });

    const state = {
      tbody: tbody,
      headerCells: headerCells,
      sortCol: -1,
      sortDir: "asc",
    };

    state.searchInput = buildToolbar(table, idPrefix);
    state.searchInput.addEventListener("input", function () {
      applyFilters(state);
    });

    state.filterInputs = buildFilterRow(table, headerRow, eligible, idPrefix);
    state.filterInputs.forEach(function (input) {
      if (input) input.addEventListener("input", function () {
        applyFilters(state);
      });
    });

    state.noMatchRow = buildNoMatchRow(tbody, headerCells.length);

    headerCells.forEach(function (th, i) {
      if (!eligible[i]) return;
      th.classList.add("data-table-sortable");
      th.tabIndex = 0;
      th.setAttribute("role", "button");
      const indicator = document.createElement("span");
      indicator.className = "data-table-sort-indicator";
      indicator.textContent = "↕";
      th.appendChild(indicator);
      th.addEventListener("click", function () {
        sortByColumn(state, i);
      });
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          sortByColumn(state, i);
        }
      });
    });
  }

  function enhanceAll(root) {
    (root || document).querySelectorAll("table.data-table").forEach(enhance);
  }

  document.addEventListener("DOMContentLoaded", function () {
    enhanceAll(document);
  });

  window.DataTable = { enhance: enhance, enhanceAll: enhanceAll };
})();
