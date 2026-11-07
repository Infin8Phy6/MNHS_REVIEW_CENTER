/* The single-player result as one A4 page, drawn on this device so a phone or a
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
  var GOOD = "#1e7e34", BAD = "#c82333", TINT = "#eef3f8";

  function label(ctx, text, x, y, size, weight, color, spacing) {
    ctx.font = weight + " " + size + "px " + FONT;
    ctx.fillStyle = color;
    if (!spacing) { ctx.fillText(text, x, y); return; }
    // Canvas has no letter-spacing, so a spaced heading is drawn one letter at a time.
    var run = x;
    String(text).split("").forEach(function (ch) {
      ctx.fillText(ch, run, y);
      run += ctx.measureText(ch).width + spacing;
    });
  }

  function wrap(ctx, text, maxWidth) {
    var words = String(text == null ? "" : text).split(/\s+/).filter(Boolean);
    if (!words.length) return [""];
    var lines = [], line = "";
    words.forEach(function (word) {
      var next = line ? line + " " + word : word;
      if (ctx.measureText(next).width > maxWidth && line) { lines.push(line); line = word; }
      else { line = next; }
    });
    if (line) lines.push(line);
    return lines;
  }

  function neat(text) {
    // Canvas draws text, it never parses it, so a name keeps its apostrophes.
    return String(text == null ? '' : text).replace(/\s+/g, ' ').trim();
  }

  function stamp(value, fallback) {
    var text = neat(value);
    return text ? text.slice(0, 10) : (fallback || "");
  }

  function draw() {
    var canvas = document.createElement("canvas");
    canvas.width = A4_W * SCALE;
    canvas.height = A4_H * SCALE;
    var ctx = canvas.getContext("2d");
    ctx.scale(SCALE, SCALE);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, A4_W, A4_H);
    ctx.textBaseline = "alphabetic";

    var y = MARGIN;
    label(ctx, "JUMBLED LETTERS", MARGIN, y + 14, 15, "700", NAVY, 3);
    label(ctx, "Single Player Result", MARGIN, y + 40, 24, "700", INK);
    y += 58;

    ctx.strokeStyle = NAVY;
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(MARGIN, y); ctx.lineTo(A4_W - MARGIN, y); ctx.stroke();
    y += 34;

    label(ctx, "STUDENT", MARGIN, y, 11, "700", SOFT, 1.4);
    label(ctx, neat(sheet.name) || "—", MARGIN, y + 30, 26, "700", NAVY);
    y += 48;

    var path = (sheet.path || []).filter(Boolean).map(neat).join("  ·  ");
    var meta = [
      path ? "Topic  " + path : "",
      "Room  " + neat(sheet.room),
      "Finished  " + stamp(sheet.finished, stamp(sheet.started, "—"))
    ].filter(Boolean);
    ctx.font = "13px " + FONT;
    ctx.fillStyle = SOFT;
    meta.forEach(function (line) {
      ctx.fillText(line, MARGIN, y + 4);
      y += 20;
    });
    y += 14;

    // The score box is what a teacher reads first, so it keeps its own block.
    var boxH = 84;
    ctx.fillStyle = TINT;
    ctx.fillRect(MARGIN, y, CONTENT, boxH);
    ctx.strokeStyle = LINE;
    ctx.lineWidth = 1;
    ctx.strokeRect(MARGIN, y, CONTENT, boxH);
    label(ctx, "SCORE", MARGIN + 20, y + 26, 11, "700", SOFT, 1.4);
    label(ctx, String(sheet.score == null ? 0 : sheet.score), MARGIN + 20, y + 60, 30, "700", NAVY);
    var solved = (sheet.solved || 0) + " of " + (sheet.total || 0) + " topic words solved";
    var bonus = (sheet.bonus || 0) + " bonus word" + (sheet.bonus === 1 ? "" : "s") + " counted";
    label(ctx, solved, MARGIN + 120, y + 38, 15, "600", INK);
    label(ctx, bonus, MARGIN + 120, y + 60, 15, "400", SOFT);
    y += boxH + 30;

    var cols = [MARGIN, MARGIN + 42, MARGIN + 212, MARGIN + 352];
    label(ctx, "#", cols[0], y, 11, "700", SOFT, 1.4);
    label(ctx, "JUMBLE", cols[1], y, 11, "700", SOFT, 1.4);
    label(ctx, "WORD", cols[2], y, 11, "700", SOFT, 1.4);
    label(ctx, "WHAT YOU SENT", cols[3], y, 11, "700", SOFT, 1.4);
    y += 10;
    ctx.strokeStyle = LINE;
    ctx.beginPath(); ctx.moveTo(MARGIN, y); ctx.lineTo(A4_W - MARGIN, y); ctx.stroke();

    (sheet.words || []).forEach(function (line) {
      y += 30;
      var sent = line.solved ? "Solved the topic word" : "Not solved";
      var bonus = (line.bonus || []).map(neat).filter(Boolean);
      ctx.font = "13px " + FONT;
      var lines = [];
      lines.push({ text: sent, color: line.solved ? GOOD : BAD, bold: true });
      bonus.forEach(function (word, i) {
        lines.push({ text: (i + 1) + ". " + word.toUpperCase(), color: SOFT, bold: false });
      });
      label(ctx, String(line.number || ""), cols[0], y, 14, "400", SOFT);
      label(ctx, (neat(line.jumble) || "").toUpperCase(), cols[1], y, 15, "700", INK, 1.5);
      label(ctx, (neat(line.word) || "").toUpperCase(), cols[2], y, 15, "700", NAVY, 1);
      lines.forEach(function (part) {
        label(ctx, part.text, cols[3], y, 13, part.bold ? "600" : "400", part.color);
        y += part.bold ? 0 : 18;
      });
      y += 14;
      ctx.strokeStyle = LINE;
      ctx.beginPath(); ctx.moveTo(MARGIN, y); ctx.lineTo(A4_W - MARGIN, y); ctx.stroke();
      if (y > A4_H - 130) return;
    });

    var foot = A4_H - 70;
    ctx.strokeStyle = LINE;
    ctx.beginPath(); ctx.moveTo(MARGIN, foot - 16); ctx.lineTo(A4_W - MARGIN, foot - 16); ctx.stroke();
    label(ctx, "Jumbled Letters practice score. It never enters the Review Center quiz results.",
          MARGIN, foot + 4, 12, "400", SOFT);
    label(ctx, "Points: a topic word is worth " + (sheet.target_points || 5) +
          ", any other real word " + (sheet.valid_points || 1) + ".",
          MARGIN, foot + 22, 12, "400", SOFT);
    return canvas;
  }

  function fileBase() {
    var name = neat(sheet.name).replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);
    return "Jumbled_Letters_" + (name || "Result") + ".png";
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
