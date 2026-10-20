/*
 * Progressive enhancement for read-only data tables: adds a
 * whole-table search box, click-to-sort column headers, and a per-column
 * filter row — entirely client-side (all rows are already server-rendered;
 * a single shop's record counts are small enough that no server round trip
 * is needed). Tables inside forms must opt in with `data-table` so
 * line-item editors are left alone.
 *
 * Columns whose header cell is empty (the usual Edit/Delete actions column)
 * are automatically skipped for both sorting and filtering. Rows that are
 * really an empty-state placeholder (a single <td colspan> — the Jinja
 * "{% else %}No X yet.{% endfor %}" row every list template uses) are
 * detected the same way and left alone rather than sorted/hidden.
 * Column filters infer date pickers and small categorical dropdowns from
 * their values; `data-filter-type="text|select|date"` and
 * `data-total="sum|none"` on a header cell can override that inference.
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

  function parseDate(text) {
    const value = text.trim();
    let match = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (match) return match[1] + "-" + match[2] + "-" + match[3];
    match = value.match(/^(\d{1,2})-(\d{1,2})-(\d{4})/);
    if (match) return match[3] + "-" + match[2].padStart(2, "0") + "-" + match[1].padStart(2, "0");
    return "";
  }

  function cleanHeader(th) {
    const clone = th.cloneNode(true);
    clone.querySelectorAll(".data-table-sort-indicator").forEach(function (el) {
      el.remove();
    });
    return clone.textContent.trim();
  }

  function shouldSum(th) {
    const setting = th.dataset.total;
    if (setting === "none") return false;
    if (setting === "sum") return true;
    const label = cleanHeader(th).toLowerCase();
    return /\b(qty|quantity|stock|remaining|total|balance|paid|revenue|profit|discount|charges|amount|due|count|items|value)\b/.test(label) &&
      !/\b(percent|percentage|margin|rate|average|avg)\b/.test(label);
  }

  function isMoneyColumn(th, rows, colIndex) {
    const label = cleanHeader(th);
    if (/\b(price|mrp|cost price|percent|percentage|margin|rate)\b/i.test(label)) {
      return /\b(total|amount|value)\b/i.test(label);
    }
    return rows.some(function (tr) {
      const cell = tr.children[colIndex];
      return cell && cell.textContent.includes("₹");
    });
  }

  function formatTotal(value, isMoney) {
    if (isMoney) return "₹" + value.toFixed(2);
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
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
          const cellText = cell ? cell.textContent.trim() : "";
          const value = input.value.trim();
          let matches;
          if (input.dataset.filterType === "select") {
            matches = cellText.toLowerCase() === value.toLowerCase();
          } else if (input.dataset.filterType === "date") {
            matches = parseDate(cellText) === value;
          } else {
            matches = cellText.toLowerCase().includes(value.toLowerCase());
          }
          if (!matches) {
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
    updateSummary(state);
  }

  function visibleRows(state) {
    return dataRows(state.tbody).filter(function (tr) {
      return !tr.classList.contains("d-none");
    });
  }

  function updateSummary(state) {
    const rows = visibleRows(state);
    state.summary.textContent = "";
    const count = document.createElement("span");
    count.className = "text-muted";
    count.textContent = rows.length + (rows.length === 1 ? " row" : " rows");
    state.summary.appendChild(count);

    state.headerCells.forEach(function (th, colIndex) {
      if (!shouldSum(th)) return;
      let total = 0;
      let countValues = 0;
      rows.forEach(function (tr) {
        const cell = tr.children[colIndex];
        const value = cell ? parseNumeric(cell.textContent) : null;
        if (value === null) return;
        total += value;
        countValues++;
      });
      if (!countValues) return;

      const item = document.createElement("span");
      item.className = "data-table-summary-total";
      item.textContent = cleanHeader(th) + ": " +
        formatTotal(total, isMoneyColumn(th, rows, colIndex));
      state.summary.appendChild(item);
    });
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

  function buildSummary(table) {
    const summary = document.createElement("div");
    summary.className = "data-table-summary mb-2";
    summary.setAttribute("aria-live", "polite");
    table.parentNode.insertBefore(summary, table);
    return summary;
  }

  function inferFilterType(th, rows, colIndex) {
    const configured = th.dataset.filterType;
    if (configured === "text" || configured === "select" || configured === "date") {
      return configured;
    }
    const nonEmpty = rows.map(function (tr) {
      const cell = tr.children[colIndex];
      return cell ? cell.textContent.trim() : "";
    }).filter(Boolean);
    if (/\b(date|created|last edited)\b/i.test(cleanHeader(th))) return "date";
    if (!nonEmpty.length) return "text";

    const dateCount = nonEmpty.filter(function (value) {
      return !!parseDate(value);
    }).length;
    if (dateCount >= nonEmpty.length * 0.8) {
      return "date";
    }
    const unique = new Set(nonEmpty.map(function (value) { return value.toLowerCase(); }));
    if (!columnIsNumeric(rows, colIndex) && unique.size > 1 && unique.size <= 12 &&
        unique.size <= nonEmpty.length * 0.6) {
      return "select";
    }
    return "text";
  }

  function buildFilterRow(table, headerRow, eligible, idPrefix, rows) {
    const filterRow = document.createElement("tr");
    filterRow.className = "data-table-filter-row";
    const inputs = [];
    Array.from(headerRow.children).forEach(function (th, i) {
      const cell = document.createElement("th");
      if (eligible[i]) {
        const type = inferFilterType(th, rows, i);
        let input;
        if (type === "select") {
          input = document.createElement("select");
          input.className = "form-select form-select-sm";
          const allOption = document.createElement("option");
          allOption.value = "";
          allOption.textContent = "All";
          input.appendChild(allOption);
          const values = Array.from(new Set(rows.map(function (tr) {
            const dataCell = tr.children[i];
            return dataCell ? dataCell.textContent.trim() : "";
          }).filter(Boolean))).sort(function (a, b) { return a.localeCompare(b); });
          values.forEach(function (value) {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = value;
            input.appendChild(option);
          });
        } else {
          input = document.createElement("input");
          input.type = type === "date" ? "date" : "search";
          input.className = "form-control form-control-sm";
          input.placeholder = type === "date" ? "" : "Filter…";
        }
        input.dataset.filterType = type;
        input.id = idPrefix + "-filter-" + i;
        input.name = idPrefix + "-filter-" + i;
        input.setAttribute("aria-label", "Filter by " + cleanHeader(th));
        cell.appendChild(input);
        if (type === "select" && window.SearchableSelect) {
          window.SearchableSelect.enhance(input);
        }
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
    if (!headerRow || !tbody || table.hasAttribute("data-plain-table")) return;
    if (table.closest("form") && !table.classList.contains("data-table")) return;
    if (Array.from(headerRow.cells).some(function (th) { return th.colSpan > 1; })) return;

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
    state.summary = buildSummary(table);
    state.searchInput.addEventListener("input", function () {
      applyFilters(state);
    });

    const initialRows = dataRows(tbody);
    state.filterInputs = buildFilterRow(table, headerRow, eligible, idPrefix, initialRows);
    state.filterInputs.forEach(function (input) {
      if (!input) return;
      input.addEventListener(input.tagName === "SELECT" ? "change" : "input", function () {
        applyFilters(state);
      });
    });

    state.noMatchRow = buildNoMatchRow(tbody, headerCells.length);
    applyFilters(state);

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
    (root || document).querySelectorAll("table.data-table, table:not([data-plain-table])").forEach(enhance);
  }

  document.addEventListener("DOMContentLoaded", function () {
    enhanceAll(document);
  });

  window.DataTable = { enhance: enhance, enhanceAll: enhanceAll };
})();
