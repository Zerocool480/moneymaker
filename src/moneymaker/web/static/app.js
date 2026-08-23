/* Money Maker Engine — broadcast interaction layer (vanilla, ~150 lines). */
(function () {
  "use strict";
  var reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---- theme toggle (t) ---- */
  function setTheme(t) {
    var h = document.documentElement;
    if (t === "light") h.setAttribute("data-theme", "light");
    else h.removeAttribute("data-theme");
    localStorage.setItem("mm-theme", t);
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.setAttribute("aria-pressed", t === "light" ? "true" : "false");
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("#theme-toggle")) {
      var light = document.documentElement.getAttribute("data-theme") === "light";
      setTheme(light ? "dark" : "light");
    }
  });

  /* ---- keyboard: 1-6 nav, j/k rows, t theme, d density, Esc ---- */
  document.addEventListener("keydown", function (e) {
    if (e.target.matches("input, select, textarea")) return;
    if (e.key >= "1" && e.key <= "6") {
      var a = document.querySelector('.nav-link[data-key="' + e.key + '"]');
      if (a) a.click();
    } else if (e.key === "t") {
      var light = document.documentElement.getAttribute("data-theme") === "light";
      setTheme(light ? "dark" : "light");
    } else if (e.key === "d") {
      document.body.classList.toggle("dense");
    } else if (e.key === "j" || e.key === "k") {
      var rows = Array.prototype.slice.call(
        document.querySelectorAll("tr.pick-row, tr.clickable"));
      if (!rows.length) return;
      var cur = rows.indexOf(document.activeElement.closest("tr"));
      var nxt = e.key === "j" ? Math.min(cur + 1, rows.length - 1)
                              : Math.max(cur - 1, 0);
      rows[nxt].focus();
      e.preventDefault();
    } else if (e.key === "Escape") {
      var p = document.getElementById("why-panel");
      if (p) p.querySelectorAll(":scope > *:not(.ghost-cap)").length;
    }
  });

  /* ---- busy buttons: morph label while HTMX request runs ---- */
  document.addEventListener("htmx:beforeRequest", function (e) {
    var btn = e.detail.elt.querySelector ?
      (e.detail.elt.matches("button[data-busy]") ? e.detail.elt
        : e.detail.elt.querySelector("button[data-busy]")) : null;
    if (btn) {
      btn.dataset.label = btn.textContent;
      btn.textContent = btn.dataset.busy;
      btn.classList.add("busy");
    }
  });
  document.addEventListener("htmx:afterRequest", function (e) {
    document.querySelectorAll("button.busy").forEach(function (btn) {
      btn.textContent = btn.dataset.label || btn.textContent;
      btn.classList.remove("busy");
    });
  });

  /* ---- count-up on landed sim numbers ---- */
  document.addEventListener("htmx:afterSwap", function (e) {
    wireTips(e.detail.target || document);
    wireCompare();
    markSelection();
    if (reduced) return;
    (e.detail.target || document).querySelectorAll(".count-up").forEach(function (el) {
      var txt = el.childNodes[0] && el.childNodes[0].nodeValue;
      if (!txt) return;
      var m = txt.match(/([\d.,]+)/);
      if (!m) return;
      var target = parseFloat(m[1].replace(/,/g, ""));
      if (!isFinite(target)) return;
      var t0 = performance.now();
      function tick(t) {
        var k = Math.min((t - t0) / 450, 1);
        k = 1 - Math.pow(1 - k, 3);
        var v = target * k;
        var s = m[1].indexOf(".") >= 0 ? v.toFixed(1) : Math.round(v).toLocaleString();
        el.childNodes[0].nodeValue = txt.replace(m[1], s);
        if (k < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    });
  });

  /* ---- shared tooltip for SVG hits (money strip, sweat markers) ---- */
  function wireTips(root) {
    root.querySelectorAll("svg .hit[data-tip]").forEach(function (r) {
      r.addEventListener("pointerenter", function (ev) {
        var tip = r.closest("section, .card").querySelector(".tooltip");
        if (!tip) return;
        tip.textContent = r.dataset.tip;
        tip.hidden = false;
        var host = tip.parentElement.getBoundingClientRect();
        tip.style.left = Math.min(ev.clientX - host.left + 8,
                                  host.width - 240) + "px";
      });
      r.addEventListener("pointerleave", function () {
        var tip = r.closest("section, .card").querySelector(".tooltip");
        if (tip) tip.hidden = true;
      });
    });
    root.querySelectorAll(".pass-marker").forEach(function (g) {
      var svg = g.closest("svg");
      g.addEventListener("pointerenter", function (ev) {
        var f = +g.dataset.finish;
        svg.classList.add("sweating");
        svg.querySelectorAll(".col").forEach(function (c) {
          c.classList.toggle("hl", +c.dataset.finish <= f);
        });
        var tip = svg.closest("section, .card").querySelector(".tooltip");
        if (tip) {
          tip.textContent = "pass " + g.dataset.rival + " with " +
            g.dataset.finish + "th or better · " + g.dataset.pays +
            " · " + g.dataset.p;
          tip.hidden = false;
          var host = tip.parentElement.getBoundingClientRect();
          tip.style.left = Math.min(ev.clientX - host.left + 8,
                                    host.width - 280) + "px";
        }
      });
      g.addEventListener("pointerleave", function () {
        svg.classList.remove("sweating");
        svg.querySelectorAll(".col.hl").forEach(function (c) {
          c.classList.remove("hl");
        });
        var tip = svg.closest("section, .card").querySelector(".tooltip");
        if (tip) tip.hidden = true;
      });
    });
  }

  /* ---- compare tray ---- */
  function wireCompare() {
    var tray = document.getElementById("compare-tray");
    if (!tray) return;
    var boxes = document.querySelectorAll("input.cmp");
    function sync() {
      var on = Array.prototype.filter.call(boxes, function (b) { return b.checked; });
      if (on.length > 3) { on[0].checked = false; return sync(); }
      document.getElementById("cmp-keys").value =
        on.map(function (b) { return b.value; }).join("|");
      document.getElementById("cmp-count").textContent =
        on.length ? on.length + " candidate" + (on.length > 1 ? "s" : "") : "";
      tray.hidden = on.length < 1;
    }
    boxes.forEach(function (b) { b.addEventListener("change", sync); });
  }

  /* ---- board row selection state ---- */
  function markSelection() {
    document.querySelectorAll("tr.pick-row").forEach(function (r) {
      r.addEventListener("click", function () {
        document.querySelectorAll("tr.pick-row[aria-selected]").forEach(function (o) {
          o.removeAttribute("aria-selected");
        });
        r.setAttribute("aria-selected", "true");
      });
    });
  }

  /* ---- upload radio shows file input ---- */
  document.addEventListener("change", function (e) {
    if (e.target.name === "source") {
      var f = document.getElementById("pos-file");
      if (f) f.classList.toggle("file-hidden", e.target.value !== "upload");
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    wireTips(document);
    wireCompare();
    markSelection();
    var light = document.documentElement.getAttribute("data-theme") === "light";
    var btn = document.getElementById("theme-toggle");
    if (btn) btn.setAttribute("aria-pressed", light ? "true" : "false");
  });
})();
