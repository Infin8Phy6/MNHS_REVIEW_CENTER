/* The finished attempt as one A4 page, drawn on this device so a phone or a
   school tablet can hand the teacher a PNG with no internet and no libraries. */
(function () {
  var box = document.getElementById("sheetData");
  var button = document.getElementById("dl");
  var note = document.getElementById("note");
  if (!box || !button) return;

  var sheet = {};
  try { sheet = JSON.parse(box.textContent) || {}; } catch (e) { return; }

  var A4_W = 794, A4_H = 1123, SCALE = 2, MARGIN = 54;
  var CONTENT = A4_W - MARGIN * 2;
  var FONT = "'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
  var NAVY = "#14213d", INK = "#222222", SOFT = "#667085", LINE = "#d9dee6";
  var GOOD = "#1e7e34", TINT = "#eef3f8";

  function neat(text) {
    return String(text == null ? "" : text).replace(/\s+/g, " ").trim();
  }

  function draw() {
    var canvas = document.createElement("canvas");
    canvas.width = A4_W * SCALE;
    canvas.height = A4_H * SCALE;
    var ctx = canvas.getContext("2d");
    ctx.scale(SCALE, SCALE);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, A4_W, A4_H);

    var y = MARGIN;
    ctx.textBaseline = "alphabetic";
    ctx.font = "700 20px " + FONT;
    ctx.fillStyle = NAVY;
    ctx.fillText(neat(sheet.title).slice(0, 60) || "Crosswords", MARGIN, y);
    y += 22;
    ctx.font = "12px " + FONT;
    ctx.fillStyle = SOFT;
    var who = [neat(sheet.name), [neat(sheet.grade), neat(sheet.section)].filter(Boolean).join(" "),
               neat(sheet.date)].filter(Boolean).join("  ·  ");
    ctx.fillText(who, MARGIN, y);
    y += 26;

    // the score badge
    ctx.font = "700 18px " + FONT;
    ctx.fillStyle = GOOD;
    ctx.fillText(sheet.score + " / " + sheet.max + " points", MARGIN, y);
    y += 18;

    var cols = sheet.cols || 1, rows = sheet.rows || 1;
    var cell = Math.min(CONTENT / cols, 430 / rows, 34);
    var gw = cell * cols, x0 = (A4_W - gw) / 2;
    var numAt = {};
    (sheet.clues || []).forEach(function (c) {
      if (c.at) numAt[c.at[0] + "," + c.at[1]] = c.n;
    });
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(x0, y, gw, cell * rows);
    ctx.strokeStyle = NAVY;
    ctx.lineWidth = 1;
    for (var r = 0; r <= rows; r++) {
      ctx.beginPath(); ctx.moveTo(x0, y + r * cell); ctx.lineTo(x0 + gw, y + r * cell); ctx.stroke();
    }
    for (var c = 0; c <= cols; c++) {
      ctx.beginPath(); ctx.moveTo(x0 + c * cell, y); ctx.lineTo(x0 + c * cell, y + cell * rows); ctx.stroke();
    }
    for (r = 0; r < rows; r++) {
      for (c = 0; c < cols; c++) {
        var x = x0 + c * cell, cy = y + r * cell;
        var n = numAt[r + "," + c];
        if (n) {
          ctx.font = "8px " + FONT;
          ctx.fillStyle = SOFT;
          ctx.fillText(String(n), x + 2, cy + 9);
        }
        var letter = (sheet.grid && sheet.grid[r] && sheet.grid[r][c]) || "";
        if (letter) {
          ctx.font = "600 " + Math.floor(cell * 0.5) + "px " + FONT;
          ctx.fillStyle = INK;
          ctx.fillText(letter, x + cell / 2 - ctx.measureText(letter).width / 2,
                       cy + cell * 0.72);
        }
      }
    }
    y += cell * rows + 24;

    // the clue list, with the answers under every solved word
    var items = (sheet.clues || []).slice().sort(function (a, b) { return a.n - b.n; });
    ctx.font = "10.5px " + FONT;
    items.forEach(function (cl) {
      if (y > A4_H - MARGIN - 14) return;   // one page; ten short clues always fit
      var text = cl.n + ". " + (cl.dir === "H" ? "Across" : "Down") + " — " +
                 neat(cl.clue);
      ctx.fillStyle = SOFT;
      ctx.fillText(clip(ctx, text, CONTENT - 120), MARGIN, y);
      ctx.fillStyle = cl.solved ? GOOD : "#c82333";
      ctx.font = "700 10.5px " + FONT;
      var ans = (cl.word || "?") + (cl.solved ? " (+3)" : " (0)");
      ctx.fillText(ans, A4_W - MARGIN - ctx.measureText(ans).width, y);
      ctx.font = "10.5px " + FONT;
      y += 16;
    });

    ctx.fillStyle = SOFT;
    ctx.font = "10px " + FONT;
    ctx.fillText("MNHS Review Center · Crosswords" +
      (sheet.reason === "timeout" ? " · clock ran out" :
       sheet.reason === "closed" ? " · puzzle closed by the teacher" : ""),
      MARGIN, A4_H - MARGIN / 2);
    return canvas;
  }

  function clip(ctx, text, width) {
    while (ctx.measureText(text).width > width && text.length > 3) {
      text = text.slice(0, -4);
    }
    return text;
  }

  function fileBase() {
    var name = neat(sheet.name).replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);
    return "Crossword_" + (name || "Result") + "_" + (sheet.score || 0) + "of" + sheet.max + ".png";
  }

  button.addEventListener("click", function () {
    button.disabled = true;
    note.textContent = "Drawing the page…";
    setTimeout(function () {
      try {
        var canvas = draw();
        canvas.toBlob(function (blob) {
          button.disabled = false;
          if (!blob) { note.textContent = "This browser would not make the picture. Try again."; return; }
          var url = URL.createObjectURL(blob);
          var link = document.createElement("a");
          link.href = url;
          link.download = fileBase();
          document.body.appendChild(link);
          link.click();
          link.remove();
          setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
          note.textContent = "Saved as " + fileBase();
        }, "image/png");
      } catch (err) {
        button.disabled = false;
        note.textContent = "The page could not be drawn on this device.";
      }
    }, 30);
  });
})();
