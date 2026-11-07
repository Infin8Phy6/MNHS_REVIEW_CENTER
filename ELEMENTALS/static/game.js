/* The game: ask for a symbol, let the server mark it, then show the finished tile. */
(function () {
  "use strict";

  var TOKEN = window.EL_TOKEN;
  // "/" when ELEMENTALS runs on its own, "/game/" inside the Review Center.
  var BASE = window.EL_BASE || "/";
  var $ = function (id) { return document.getElementById(id); };
  var state = null, busy = false, tick = null, started = Date.now();

  function screen(which) {
    var on = which === "scr-end" ? ["scr-end", "scr-sheet"] : [which];
    ["scr-play", "scr-end", "scr-sheet"].forEach(function (n) {
      $(n).classList.toggle("on", on.indexOf(n) >= 0);
    });
  }

  function get(url) {
    return fetch(url).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || r.status); return j; });
    });
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || r.status); return j; });
    });
  }

  function load() {
    return get(BASE + "api/state/" + TOKEN).then(function (j) {
      state = j;
      $("who").textContent = j.student;
      if (j.grade || j.section) {
        $("who").textContent = j.student + " \u00b7 " + [j.grade, j.section].filter(Boolean).join(" ");
      }
      if (j.finished) { screen("scr-end"); render_end(j.summary); }
      else { screen("scr-play"); draw(j); }
    }).catch(function (e) {
      $("fb").className = "fb no";
      $("fb").textContent = "Cannot reach the game on this computer: " + e.message;
    });
  }

  function draw(j) {
    var hard = j.level === "hard";
    $("ctr").setAttribute("data-base", "Item " + j.idx + " of " + j.total);
    $("ctr").textContent = "Item " + j.idx + " of " + j.total;
    $("sc").textContent = "Score " + j.score;
    $("pk").style.width = ((j.idx - 1) / j.total * 100) + "%";
    $("lvl").textContent = hard ? "Hard level" : "With choices";
    $("mtile").innerHTML = EL.tileHTML(j.tile, { size: "big", hide: true });
    $("ename").textContent = j.tile.name;
    $("place").textContent = hard
      ? "Type the symbol exactly as the periodic table writes it - capital first letter, small second one."
      : "Give the chemical symbol for this element.";
    $("clues").innerHTML = j.clues.map(function (c) { return "<li>" + EL.esc(c) + "</li>"; }).join("");
    $("choicebox").hidden = hard;
    $("playbox").classList.toggle("hard", hard);
    $("ans").placeholder = "Symbol";
    $("letters").hidden = !hard;
    if (hard) {
      $("letters").textContent = j.letters === 1 ? "1 letter" : j.letters + " letters";
    }
    $("opts").innerHTML = hard ? "" : j.choices.map(function (c) {
      return '<button type="button" data-sym="' + EL.esc(c.symbol) + '">' + EL.esc(c.symbol) + "</button>";
    }).join("");
    Array.prototype.forEach.call($("opts").children, function (b) {
      b.addEventListener("click", function () { answer(b.getAttribute("data-sym")); });
    });
    var ans = $("ans");
    ans.value = ""; ans.disabled = false; ans.classList.remove("oops");
    $("chk").disabled = false;
    $("fb").className = "fb"; $("fb").textContent = "";
    $("reveal").hidden = true;
    $("nxt").hidden = true;
    if (window.matchMedia("(min-width: 820px)").matches) { ans.focus(); }
  }

  function answer(sym) {
    if (busy || !state || state.finished) { return; }
    var given = String(sym || "").trim();
    if (!given) { $("ans").classList.add("oops"); $("ans").focus(); return; }
    busy = true;
    $("ans").disabled = true; $("chk").disabled = true;
    post(BASE + "api/answer/" + TOKEN, { symbol: given }).then(function (r) {
      var t = r.correct;
      var klass = t.class && t.class !== t.family_label ? " \u2014 " + t.class : "";
      var fact = t.where + klass + " \u00b7 " + t.state.toLowerCase() +
        " at room temperature" + (t.symbol_origin ? " \u00b7 symbol from " + t.symbol_origin : "");
      $("fb").className = "fb " + (r.ok ? "ok" : "no");
      $("fb").innerHTML = (r.ok ? "Correct \u2014 " :
        r.near ? "Right letters, wrong capitalisation \u2014 the symbol is " :
                 "Not quite \u2014 the symbol is ") +
        "<b>" + EL.esc(t.symbol) + "</b> (" + EL.esc(t.name) + ")" +
        '<span class="fact">' + EL.esc(fact) + "</span>";
      $("reveal").hidden = false;
      $("reveal").innerHTML = EL.tileHTML(t, { size: "side" }) +
        '<dl class="facts">' +
        pair("Atomic number", t.z) + pair("Chemical symbol", t.symbol) +
        pair("Element name", t.name) + pair("Atomic mass", t.mass_text + " u") +
        pair("Electron configuration", t.config_pretty) +
        pair("Oxidation states", t.oxidation_pretty) +
        pair("State / class", t.state + " \u00b7 " + t.class) +
        pair("Position", t.where) + "</dl>";
      Array.prototype.forEach.call($("opts").children, function (b) {
        var s = b.getAttribute("data-sym");
        if (s.toUpperCase() === t.symbol.toUpperCase()) { b.className = "pick"; }
        else if (s.toUpperCase() === given.toUpperCase()) { b.className = "miss"; }
        else { b.className = "dim"; }
        b.disabled = true;
      });
      if (!r.ok) { $("ans").classList.add("oops"); }
      $("sc").textContent = "Score " + r.score;
      $("pk").style.width = ((state.total - r.remaining) / state.total * 100) + "%";
      $("nxt").textContent = r.remaining ? "Next item \u2192" : "See my score \u2192";
      $("nxt").hidden = false;
      $("nxt").focus();
      state.score = r.score;
    }).catch(function (e) {
      $("fb").className = "fb no"; $("fb").textContent = e.message;
      $("ans").disabled = false; $("chk").disabled = false;
    }).then(function () { busy = false; });
  }

  function pair(k, v) {
    return "<dt>" + EL.esc(k) + "</dt><dd>" + EL.esc(v) + "</dd>";
  }

  function render_end(s) {
    clearInterval(tick);
    var hard = s.level === "hard";
    var pct = s.total ? Math.round(s.score / s.total * 100) : 0;
    $("fin").innerHTML = s.score + "<small> / " + s.total + "</small>";
    $("fpct").textContent = pct + "% \u00b7 " + EL.mmss(s.seconds || Math.round((Date.now() - started) / 1000));
    $("flvl").hidden = !hard;
    $("flvl").textContent = s.level_label || "";
    $("fmsg").textContent = pct === 100 ? (hard ? "Perfect. Every symbol spelled and capitalised correctly."
                                                : "Perfect. Every symbol from the clues.") :
      pct >= 70 ? "Strong work - a few clues left to master." :
      pct >= 40 ? "Halfway there. Check the tiles you missed and try again." :
      "Keep the periodic table close and study the tiles below.";
    $("rows").innerHTML = s.items.map(function (i) {
      return "<tr><td>" + i.idx + "</td>" +
        '<td><span class="sw" style="background:var(--f-' + i.tile.family + ')"></span>' +
        EL.esc(i.tile.name) + " \u00b7 " + i.tile.z + "</td>" +
        "<td><b>" + EL.esc(i.given || "-") + "</b></td>" +
        "<td><b>" + EL.esc(i.tile.symbol) + "</b></td>" +
        '<td class="c"><span class="mk ' + (i.ok ? "ok" : "no") + '">' + (i.ok ? "\u2713" : "\u2717") + "</span></td></tr>";
    }).join("");
    sheet(s);
  }

  /* ---------- the printable result sheet ---------- */
  function C(w, h) { var c = document.getElementById("sheet"); c.width = w; c.height = h; return c.getContext("2d"); }

  function sheet(s) {
    var W = 1000, rowH = 52, head = 250, foot = 130;
    var H = head + 70 + s.items.length * rowH + foot;
    var g = C(W, H);
    var ink = "#14213d", line = "#d9e0ea", mut = "#41506b";
    g.fillStyle = "#fff"; g.fillRect(0, 0, W, H);

    g.fillStyle = ink; g.fillRect(0, 0, W, 108);
    g.fillStyle = "#fca311"; g.fillRect(0, 108, W, 8);
    g.fillStyle = ink; g.fillRect(28, 26, 56, 56);
    g.fillStyle = "#fca311"; g.fillRect(34, 32, 44, 44);
    g.fillStyle = ink; g.font = "bold 22px Arial"; g.textAlign = "center";
    g.fillText("El", 56, 62);
    g.fillStyle = "#fff"; g.textAlign = "left"; g.font = "bold 30px Arial";
    g.fillText("ELEMENTALS \u2014 Periodic Table Symbol Sprint", 100, 52);
    g.font = "16px Arial"; g.fillStyle = "#c8d6ee";
    g.fillText("Activity result sheet", 100, 80);

    var pct = s.total ? Math.round(s.score / s.total * 100) : 0;
    g.fillStyle = ink; g.font = "bold 17px Arial";
    g.fillText("Student:", 30, 150);
    g.font = "bold 22px Arial";
    g.save(); g.beginPath(); g.rect(110, 128, W - 430, 32); g.clip();
    g.fillText(s.student, 112, 152); g.restore();
    g.font = "15px Arial"; g.fillStyle = mut;
    var cls = [s.grade, s.section].filter(Boolean).join(" \u00b7 ");
    var lvl = s.level === "hard" ? "  \u00b7  Hard: capitalisation counts" : "";
    g.save(); g.beginPath(); g.rect(112, 160, W - 420, 22); g.clip();
    g.fillText((cls ? cls + "  \u00b7  " : "") + s.date + "  \u00b7  " + EL.mmss(s.seconds || 0) + " spent" + lvl, 112, 174);
    g.restore();

    g.fillStyle = pct >= 70 ? "#2a9d8f" : pct >= 40 ? "#e2932b" : "#e76f51";
    round(g, W - 300, 128, 270, 74, 12); g.fill();
    g.fillStyle = "#fff"; g.textAlign = "center"; g.font = "bold 30px Arial";
    g.fillText("Score " + s.score + " / " + s.total, W - 165, 160);
    g.font = "bold 15px Arial";
    g.fillText(pct + "%", W - 165, 186);

    var top = 232;
    g.fillStyle = ink; g.fillRect(30, top, W - 60, 40);
    g.fillStyle = "#fff"; g.font = "bold 13px Arial"; g.textAlign = "left";
    var cols = [[30, "#"], [80, "Element from the clues"], [400, "Answer given"], [610, "Correct symbol"], [810, "Result"]];
    cols.forEach(function (c) { g.fillText(c[1], c[0] + 14, top + 26); });

    s.items.forEach(function (i, n) {
      var y = top + 40 + n * rowH;
      g.fillStyle = n % 2 ? "#f6f9fc" : "#fff";
      g.fillRect(30, y, W - 60, rowH);
      g.strokeStyle = line; g.lineWidth = 1; g.strokeRect(30.5, y + .5, W - 61, rowH - 1);
      g.fillStyle = ink; g.font = "bold 16px Arial";
      g.fillText(String(i.idx), 44, y + 33);
      g.fillStyle = fam(i.tile.family); g.fillRect(94, y + 14, 16, 24);
      g.fillStyle = ink; g.font = "17px Arial";
      g.fillText(i.tile.name + "  (" + i.tile.z + ")", 120, y + 32);
      g.font = "bold 17px Arial";
      g.fillStyle = i.ok ? ink : "#a8442f";
      g.fillText(i.given || "\u2014", 414, y + 32);
      g.fillStyle = ink; g.fillText(i.tile.symbol, 624, y + 32);
      g.fillStyle = i.ok ? "#2a9d8f" : "#e76f51";
      g.font = "bold 24px Arial"; g.textAlign = "center";
      g.fillText(i.ok ? "\u2713" : "\u2717", 862, y + 35);
      g.textAlign = "left";
    });

    var foot_y = top + 40 + s.items.length * rowH + 44;
    g.strokeStyle = "#9aa5b1"; g.lineWidth = 1.4;
    g.beginPath(); g.moveTo(30, foot_y); g.lineTo(430, foot_y); g.stroke();
    g.beginPath(); g.moveTo(560, foot_y); g.lineTo(970, foot_y); g.stroke();
    g.fillStyle = mut; g.font = "13px Arial";
    g.fillText("Student signature", 30, foot_y + 22);
    g.fillText("Teacher checked", 560, foot_y + 22);
    g.font = "12px Arial";
    g.fillText("Symbols and clues are drawn from the periodic table stored in the app database.", 30, H - 26);
  }

  var FAM = { alkali: "#fbdcd2", alkaline: "#fbe6c8", transition: "#d9e4fb", post: "#d7ebe6",
    metalloid: "#cfe8dd", nonmetal: "#dbf0d8", halogen: "#eadcf7", noble: "#d2f0f7",
    lanthanide: "#fbd9ea", actinide: "#f7dcc4", unknown: "#e4e8ee" };
  function fam(k) { return FAM[k] || "#e4e8ee"; }

  function round(g, x, y, w, h, r) {
    g.beginPath(); g.moveTo(x + r, y); g.lineTo(x + w - r, y); g.quadraticCurveTo(x + w, y, x + w, y + r);
    g.lineTo(x + w, y + h - r); g.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    g.lineTo(x + r, y + h); g.quadraticCurveTo(x, y + h, x, y + h - r);
    g.lineTo(x, y + r); g.quadraticCurveTo(x, y, x + r, y); g.closePath();
  }

  function pngName(s) {
    return "ELEMENTALS_" + String(s ? s.student : "draft").replace(/[^\w]+/g, "_").slice(0, 40) +
      "_" + new Date().toISOString().slice(0, 10) + ".png";
  }

  function save(href) {
    var a = document.createElement("a");
    if (!("download" in a)) { window.open(href, "_blank", "noopener"); return; }
    a.href = href; a.download = pngName(state && state.summary); a.rel = "noopener";
    document.body.appendChild(a); a.click(); a.remove();
  }

  function download() {
    var c = $("sheet"), btn = $("dl"), old = btn.textContent;
    var tell = function (msg) { btn.textContent = msg; setTimeout(function () { btn.textContent = old; }, 3000); };
    var give = function (url) { save(url); tell("Saved \u2713"); };
    if (!c.toBlob) { give(c.toDataURL("image/png")); return; }
    c.toBlob(function (blob) {
      if (!blob) { give(c.toDataURL("image/png")); return; }
      var url = URL.createObjectURL(blob);
      // Save the copy on this computer first: starting a download can cancel a
      // request that is still running.
      fetch(BASE + "api/sheet/" + TOKEN, { method: "POST", headers: { "Content-Type": "image/png" }, body: blob })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (j.file) {
            $("dlnote").innerHTML = "A copy is kept on this computer: <b>" + EL.esc(j.folder) + "</b> \u00b7 <a href=\"" + EL.esc(j.file) + "\">open it</a>";
          }
          give(url);
        })
        .catch(function () { $("dlnote").textContent = "The download worked; this computer could not keep a copy."; give(url); });
      setTimeout(function () { URL.revokeObjectURL(url); }, 20000);
    }, "image/png");
  }

  /* ---------- wiring ---------- */
  $("chk").addEventListener("click", function () { answer($("ans").value); });
  $("ans").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); answer($("ans").value); }
  });
  $("nxt").addEventListener("click", function () { $("nxt").hidden = true; load(); });
  $("dl").addEventListener("click", download);

  tick = setInterval(function () {
    var el = $("ctr"), base = el && el.getAttribute("data-base");
    if (base && state && !state.finished) {
      el.textContent = base + "  \u00b7  " + EL.mmss(Math.round((Date.now() - started) / 1000));
    }
  }, 1000);

  load();
})();
