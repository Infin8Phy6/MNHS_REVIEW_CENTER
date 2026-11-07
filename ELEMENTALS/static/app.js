/* Shared helpers: the periodic-table tile and a few small utilities. */
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  /* opts: size ("big"|"side"|""), hide (mask symbol, number and mass) */
  function tileHTML(t, opts) {
    var o = opts || {};
    var mask = o.hide;
    return '<div class="tile f-' + esc(t.family) + (o.size ? " " + o.size : "") + (mask ? " masked" : "") + '">' +
      '<div class="tn">' + (mask ? "?" : esc(t.z)) + "</div>" +
      '<div class="tsym">' + (mask ? "?" : esc(t.symbol)) + "</div>" +
      '<div class="tnm">' + (o.noName ? "&nbsp;" : esc(t.name)) + "</div>" +
      '<div class="tm">' + (mask ? "?" : esc(t.mass_text)) + "</div>" +
      "</div>";
  }

  function mmss(sec) {
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  window.EL = { esc: esc, tileHTML: tileHTML, mmss: mmss };
})();
