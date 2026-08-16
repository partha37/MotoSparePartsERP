/*
 * Wires the chart/table toggle used on every report page (see the
 * .report-section markup convention). Table is the default view — the
 * Chart.js instance for a section is built lazily on first "Chart" click,
 * not on page load: a canvas measured by Chart.js while its container is
 * display:none gets sized zero-width and never recovers without an
 * explicit resize(), and most sections are never switched to chart view at
 * all, so building eagerly would also be wasted work on every page load.
 */
(function () {
  function wire(section, buildChart) {
    if (!section) return;
    const chartPane = section.querySelector(".view-chart");
    const tablePane = section.querySelector(".view-table");
    const chartBtn = section.querySelector('.view-toggle [data-view="chart"]');
    const tableBtn = section.querySelector('.view-toggle [data-view="table"]');
    let chart = null;

    function show(view) {
      if (chartPane) chartPane.style.display = view === "chart" ? "" : "none";
      if (tablePane) tablePane.style.display = view === "table" ? "" : "none";
      if (chartBtn) chartBtn.classList.toggle("active", view === "chart");
      if (tableBtn) tableBtn.classList.toggle("active", view === "table");
    }

    if (chartBtn) {
      chartBtn.addEventListener("click", function () {
        if (!chart) chart = buildChart();
        show("chart");
      });
    }
    if (tableBtn) {
      tableBtn.addEventListener("click", function () {
        show("table");
      });
    }

    show("table");
  }

  window.ReportToggle = { wire: wire };
})();
