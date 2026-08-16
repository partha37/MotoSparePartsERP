/*
 * Applies this app's dark/light theme (see base.html's data-bs-theme toggle)
 * to Chart.js's global defaults, since Chart.js's own default text/gridline
 * colors (mid-gray, tuned for a white background) read poorly on this app's
 * near-black dark theme. Must load after chart.umd.min.js and before any
 * page-specific `new Chart(...)` calls, since Chart.defaults are read once
 * at chart-construction time, not live — a theme change after that requires
 * a page reload to take effect, same as every other themed element here.
 */
(function () {
  if (typeof Chart === "undefined") return;
  const isDark = document.documentElement.getAttribute("data-bs-theme") === "dark";
  Chart.defaults.color = isDark ? "#adb5bd" : "#495057";
  Chart.defaults.borderColor = isDark ? "rgba(255, 255, 255, 0.15)" : "rgba(0, 0, 0, 0.1)";
})();
