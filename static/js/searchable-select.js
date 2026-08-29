/*
 * Turns a plain <select> into a type-to-filter combobox without touching its
 * name/value/options — the original <select> stays in the DOM (hidden) and
 * keeps submitting normally; a text input + dropdown list sit in front of it
 * as a UI proxy. Existing code that reads/sets `select.value`/`selectedIndex`
 * or listens for its 'change' event keeps working unmodified, because every
 * commit here sets the real select's value and dispatches a real 'change'.
 *
 * Options whose visible text starts with "--" (e.g. "-- Select Product --")
 * are treated as placeholder/prompt text rather than a real committed value.
 *
 * If other code changes select.value/selectedIndex programmatically (e.g.
 * auto-picking the oldest stock batch), call `select.refreshSearchable()`
 * afterwards so the visible text stays in sync.
 */
(function () {
  function labelFor(opt) {
    return (opt.textContent || "").trim();
  }

  function isPlaceholder(opt) {
    return /^--/.test(labelFor(opt));
  }

  function enhance(select) {
    if (!select || select.dataset.searchableEnhanced) return select;
    select.dataset.searchableEnhanced = "1";

    const wrapper = document.createElement("div");
    wrapper.className = "searchable-select position-relative";

    const input = document.createElement("input");
    input.type = "text";
    input.className = "form-control searchable-select-input";
    input.setAttribute("autocomplete", "off");
    const ariaLabel = select.getAttribute("aria-label");
    if (ariaLabel) input.setAttribute("aria-label", ariaLabel);
    if (select.hasAttribute("required")) input.setAttribute("required", "");
    if (select.disabled) input.disabled = true;

    // position: fixed (not Bootstrap's position-absolute) so the menu is
    // positioned straight off the input's viewport coordinates and can never
    // get clipped by an ancestor with overflow:auto/hidden — e.g. a
    // line-item table wrapped for horizontal scroll (table-tools.js's
    // .tt-wrap) would otherwise cut the dropdown off after a couple of rows.
    const menu = document.createElement("ul");
    menu.className = "list-group searchable-select-menu d-none";

    select.classList.add("d-none");
    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(input);
    wrapper.appendChild(select);
    wrapper.appendChild(menu);

    // Keep "click label to focus" working even though the label's `for`
    // still points at the now-hidden select.
    if (select.id) {
      const label = document.querySelector('label[for="' + select.id + '"]');
      if (label) {
        label.addEventListener("mousedown", function (e) {
          e.preventDefault();
          input.focus();
        });
      }
    }

    let filtered = [];
    let activeIdx = -1;

    function sync() {
      const opt = select.options[select.selectedIndex];
      if (!opt || isPlaceholder(opt)) {
        input.value = "";
        input.placeholder = opt ? labelFor(opt) : "";
      } else {
        input.value = labelFor(opt);
        input.placeholder = "";
      }
    }

    function closeMenu() {
      menu.classList.add("d-none");
      menu.innerHTML = "";
      activeIdx = -1;
      setNoMatch(false);
    }

    // menu is position:fixed, so its coordinates are plain viewport pixels
    // off the input — not relative to any positioned ancestor.
    function positionMenu() {
      const rect = input.getBoundingClientRect();
      menu.style.top = rect.bottom + "px";
      menu.style.left = rect.left + "px";
      menu.style.width = rect.width + "px";
    }

    // Fires a bubbling custom event only on actual state change, so a sibling
    // control (e.g. a "not in the list? add it" button next to this select)
    // can show/hide itself in response instead of always being visible.
    function setNoMatch(noMatch) {
      if (select.dataset.noMatch === String(noMatch)) return;
      select.dataset.noMatch = String(noMatch);
      select.dispatchEvent(new CustomEvent("searchable:nomatch", { bubbles: true, detail: { noMatch: noMatch } }));
    }

    function highlight() {
      Array.from(menu.children).forEach(function (li, i) {
        li.classList.toggle("active", i === activeIdx);
      });
      const el = menu.children[activeIdx];
      if (el) el.scrollIntoView({ block: "nearest" });
    }

    function render(query) {
      const q = query.trim().toLowerCase();
      filtered = Array.from(select.options).filter(function (o) {
        return labelFor(o).toLowerCase().includes(q);
      });
      menu.innerHTML = "";
      if (!filtered.length) {
        const li = document.createElement("li");
        li.className = "list-group-item text-muted small";
        li.textContent = "No matches";
        menu.appendChild(li);
        activeIdx = -1;
      } else {
        const currentOpt = select.options[select.selectedIndex];
        activeIdx = currentOpt ? Math.max(filtered.indexOf(currentOpt), 0) : 0;
        filtered.forEach(function (opt) {
          const li = document.createElement("li");
          li.className = "list-group-item list-group-item-action searchable-select-item";
          li.textContent = labelFor(opt);
          li.addEventListener("mousedown", function (e) {
            e.preventDefault(); // fires before the input's blur, so reconcile() can't race it
            commit(opt);
          });
          menu.appendChild(li);
        });
        highlight();
      }
      positionMenu();
      menu.classList.remove("d-none");
      setNoMatch(!filtered.length && q !== "");
    }

    function commit(opt) {
      // Set by index, not `select.value = opt.value` — two options can
      // legitimately share the same value (e.g. a "-- None --" placeholder
      // and a real "Walk-in" option both submitting ""), and assigning by
      // value always snaps to the *first* option with that value, silently
      // discarding which one the user actually clicked.
      const idx = Array.prototype.indexOf.call(select.options, opt);
      if (idx !== -1) select.selectedIndex = idx;
      delete select.dataset.searchQuery;
      sync();
      closeMenu();
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function reconcile() {
      sync();
      closeMenu();
    }

    input.addEventListener("focus", function () {
      render("");
      input.select();
    });

    input.addEventListener("input", function () {
      // Stashed on the real <select> (not just kept in the input) so other
      // code — e.g. a "not in the list? add it" trigger sitting next to this
      // select — can read what the user actually typed after the proxy
      // input's own value gets reset back to blank/placeholder on blur.
      select.dataset.searchQuery = input.value;
      render(input.value);
    });

    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (menu.classList.contains("d-none")) {
          render(input.value);
          return;
        }
        if (filtered.length) {
          activeIdx = Math.min(activeIdx + 1, filtered.length - 1);
          highlight();
        }
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (!menu.classList.contains("d-none") && filtered.length) {
          activeIdx = Math.max(activeIdx - 1, 0);
          highlight();
        }
      } else if (e.key === "Enter") {
        if (!menu.classList.contains("d-none") && filtered.length && activeIdx >= 0) {
          e.preventDefault();
          commit(filtered[activeIdx]);
        }
      } else if (e.key === "Escape") {
        reconcile();
      }
    });

    input.addEventListener("blur", reconcile);

    // Scroll events don't bubble, so a nested scrollable ancestor (e.g. a
    // wide line-item table's horizontal-scroll wrapper) needs the capture
    // phase to be seen here at all. Closing on scroll/resize is simpler and
    // safer than repositioning the fixed menu, and no worse an experience —
    // this is what most native comboboxes do too.
    document.addEventListener("scroll", function () {
      if (!menu.classList.contains("d-none")) closeMenu();
    }, true);
    window.addEventListener("resize", function () {
      if (!menu.classList.contains("d-none")) closeMenu();
    });

    document.addEventListener("mousedown", function (e) {
      if (!wrapper.contains(e.target) && !menu.classList.contains("d-none")) closeMenu();
    });

    select.refreshSearchable = sync;
    sync();
    return select;
  }

  // Undoes enhance() inside a cloned subtree (used before re-wiring a
  // cloned line-item row) so the select can be enhanced fresh — cloneNode
  // copies markup and dataset flags but not event listeners, so a clone
  // must never be left half-enhanced.
  function reset(root) {
    (root || document).querySelectorAll(".searchable-select").forEach(function (wrapper) {
      const select = wrapper.querySelector("select");
      if (!select) return;
      select.classList.remove("d-none");
      delete select.dataset.searchableEnhanced;
      delete select.refreshSearchable;
      wrapper.parentNode.insertBefore(select, wrapper);
      wrapper.remove();
    });
  }

  // Toggling `select.required` after enhance() doesn't affect the visible
  // proxy input (its `required` was only copied once, at enhance time), so
  // native validation would silently check the hidden select instead. This
  // keeps both in sync whenever required-ness needs to change dynamically
  // (e.g. line-item rows where only the first row is mandatory).
  function setRequired(select, val) {
    select.required = val;
    const wrapper = select.closest(".searchable-select");
    const proxy = wrapper ? wrapper.querySelector(".searchable-select-input") : null;
    if (proxy) proxy.required = val;
  }

  // Same reasoning as setRequired: `select.disabled` alone doesn't affect the
  // visible proxy input (its `disabled` was only copied once, at enhance
  // time, from the pre-enhance state) — anything that disables a select
  // *after* enhancement (e.g. two mutually-exclusive selects where picking
  // one locks the other) must go through this instead of setting
  // `select.disabled` directly, or the proxy stays clickable/typeable while
  // the real select silently ignores it.
  function setDisabled(select, val) {
    select.disabled = val;
    const wrapper = select.closest(".searchable-select");
    const proxy = wrapper ? wrapper.querySelector(".searchable-select-input") : null;
    if (proxy) proxy.disabled = val;
  }

  window.SearchableSelect = { enhance: enhance, reset: reset, setRequired: setRequired, setDisabled: setDisabled };
})();
