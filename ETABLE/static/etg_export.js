// Elemental Table Game - the answered table, drawn on one landscape A4 sheet.
// A4 landscape at 96 dpi is 1123 x 794 px; it is painted at 2x and downloaded as a PNG.
window.ETABLE_EXPORT = (function () {
  var PAGE_W = 1123;
  var PAGE_H = 794;
  var SCALE = 2;
  var MARGIN = 46;
  var NAVY = '#14213d';
  var AMBER = '#fca311';
  var GREY = '#666666';
  var LINE = '#cfd6e0';
  var OK = '#1e7e34';
  var NO = '#c82333';
  var FONT = "'Segoe UI', Roboto, Helvetica, Arial, sans-serif";

  function slug(text) {
    return String(text || 'guest').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'guest';
  }

  function marksByCell(marks) {
    var map = {};
    (marks || []).forEach(function (m) { map[m.r + ':' + m.col] = m; });
    return map;
  }

  function columnXs(count) {
    // A narrow number column, then the nine data columns sharing the rest of the sheet.
    var first = 34;
    var each = (PAGE_W - MARGIN * 2 - first) / count;
    var xs = [MARGIN, MARGIN + first];
    for (var i = 0; i < count; i++) xs.push(xs[xs.length - 1] + each);
    return xs;
  }

  function centre(ctx, text, x, width, y) {
    ctx.fillText(String(text), x + width / 2, y);
  }

  function draw(data) {
    var columns = data.columns;
    var canvas = document.createElement('canvas');
    canvas.width = PAGE_W * SCALE;
    canvas.height = PAGE_H * SCALE;
    var ctx = canvas.getContext('2d');
    ctx.scale(SCALE, SCALE);
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';

    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, PAGE_W, PAGE_H);
    ctx.fillStyle = NAVY;
    ctx.fillRect(0, 0, PAGE_W, 8);

    var xs = columnXs(columns.length);
    var width = PAGE_W - MARGIN * 2;

    ctx.fillStyle = NAVY;
    ctx.font = '700 27px ' + FONT;
    ctx.fillText('MNHSRC \u2014 Elemental Table Game', MARGIN, 54);

    ctx.font = '14px ' + FONT;
    ctx.fillStyle = GREY;
    var day = new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
    ctx.fillText('Student: ' + (data.student || 'Guest') + '     \u00b7     ' + day +
      '     \u00b7     Five elements, five cells emptied in each row', MARGIN, 78);

    // the score, printed on the sheet so a paper copy carries the mark too
    ctx.font = '700 20px ' + FONT;
    ctx.textAlign = 'right';
    ctx.fillStyle = NAVY;
    ctx.fillText(data.score + ' / ' + data.total, PAGE_W - MARGIN, 60);
    ctx.textAlign = 'right';
    ctx.font = '12.5px ' + FONT;
    ctx.fillStyle = GREY;
    ctx.fillText('SCORE', PAGE_W - MARGIN, 78);
    ctx.textAlign = 'left';

    var top = 96;
    var headH = 46;
    var rowH = 92;

    // header row
    ctx.fillStyle = NAVY;
    ctx.fillRect(MARGIN, top, width, headH);
    ctx.strokeStyle = '#ffffff';
    for (var h = 0; h < columns.length; h++) {
      var x = xs[h + 1];
      ctx.textAlign = 'center';
      ctx.fillStyle = '#ffffff';
      ctx.font = '600 13.5px ' + FONT;
      var words = String(data.heads[columns[h]]).split(' ');
      if (words.length > 1) {
        ctx.fillText(words[0], x + (xs[h + 2] - x) / 2, top + 19);
        ctx.fillText(words.slice(1).join(' '), x + (xs[h + 2] - x) / 2, top + 36);
      } else {
        ctx.fillText(words[0], x + (xs[h + 2] - x) / 2, top + 29);
      }
    }
    ctx.textAlign = 'center';
    ctx.fillStyle = '#ffffff';
    ctx.font = '600 13.5px ' + FONT;
    ctx.fillText('#', MARGIN + 17, top + 29);
    ctx.textAlign = 'left';

    var marks = marksByCell(data.marks);

    // the five rows: every column, given cells and answered cells alike
    data.table.forEach(function (row, r) {
      var y = top + headH + r * rowH;
      ctx.fillStyle = '#eef1f7';
      ctx.fillRect(MARGIN, y, 34, rowH);
      ctx.strokeStyle = LINE;
      ctx.lineWidth = 1;
      ctx.strokeRect(MARGIN + 0.5, y + 0.5, width - 1, rowH - 1);
      ctx.fillStyle = NAVY;
      ctx.font = '600 14px ' + FONT;
      ctx.textAlign = 'center';
      ctx.fillText(String(r + 1), MARGIN + 17, y + rowH / 2 + 5);
      ctx.textAlign = 'left';

      columns.forEach(function (column, index) {
        var x = xs[index + 1];
        var cellW = xs[index + 2] - x;
        ctx.strokeStyle = LINE;
        ctx.strokeRect(x + 0.5, y + 0.5, cellW - 1, rowH - 1);

        var blank = row.blanks.indexOf(column) !== -1;
        var mark = marks[r + ':' + column];
        var value = row.truth[column];

        if (!blank) {
          ctx.fillStyle = '#f7f9fc';
          ctx.fillRect(x + 1, y + 1, cellW - 2, rowH - 2);
          ctx.fillStyle = NAVY;
          ctx.font = '700 19px ' + FONT;
          centre(ctx, value, x, cellW, y + rowH / 2 + 6);
          ctx.font = '11px ' + FONT;
          ctx.fillStyle = GREY;
          centre(ctx, 'clue', x, cellW, y + 20);
          return;
        }

        ctx.fillStyle = '#fffdf5';
        ctx.fillRect(x + 1, y + 1, cellW - 2, rowH - 2);

        var typed = (data.typed || {})[r + ':' + column] || '';
        var right = mark && mark.ok;
        ctx.fillStyle = right ? OK : NO;
        ctx.font = '700 15px ' + FONT;
        centre(ctx, typed || (right ? value : '(blank)'), x, cellW, y + rowH / 2 - 2);
        ctx.font = '700 20px ' + FONT;
        centre(ctx, right ? '\u2713' : '\u2717', x, cellW, y + rowH / 2 + 26);
        if (mark && !mark.ok) {
          ctx.font = '12px ' + FONT;
          ctx.fillStyle = GREY;
          centre(ctx, 'is ' + mark.truth, x, cellW, y + rowH - 12);
        }
      });
    });

    var foot = top + headH + data.table.length * rowH + 26;
    ctx.strokeStyle = AMBER;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(MARGIN, foot);
    ctx.lineTo(PAGE_W - MARGIN, foot);
    ctx.stroke();

    ctx.fillStyle = GREY;
    ctx.font = '12.5px ' + FONT;
    ctx.fillText('Laws behind every answer: protons = electrons in a neutral atom \u00b7 ' +
      'mass number = protons + neutrons \u00b7 group gives the valence electrons (1, 2, then 3-8) \u00b7 ' +
      'period is the shell those electrons sit in.', MARGIN, foot + 22);
    ctx.fillText('One point for each of the ' + data.total + ' emptied cells. ' +
      'Main-group elements (groups 1, 2, 13-18) of periods 1-4.', MARGIN, foot + 42);

    return canvas;
  }

  function save(data) {
    var link = document.createElement('a');
    link.href = draw(data).toDataURL('image/png');
    link.download = 'elemental-table-' + slug(data.student) + '-' + data.score + 'of' + data.total + '.png';
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  // The PDF is written by hand: one landscape A4 page holding the sheet as a
  // JPEG, so the app needs no internet and no library.
  function bytesOf(text) {
    var b = new Uint8Array(text.length);
    for (var i = 0; i < text.length; i++) b[i] = text.charCodeAt(i) & 0xff;
    return b;
  }

  function buildPdf(bytes, width, height) {
    var PT_W = 841.89;
    var PT_H = 595.28;
    var objects = [];
    objects[1] = '<< /Type /Catalog /Pages 2 0 R >>';
    objects[2] = '<< /Type /Pages /Count 1 /Kids [4 0 R] >>';
    objects[3] = {
      header: '<< /Type /XObject /Subtype /Image /Width ' + width + ' /Height ' + height +
        ' /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ' +
        bytes.length + ' >>',
      stream: bytes
    };
    objects[4] = '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ' + PT_W + ' ' + PT_H + '] ' +
      '/Resources << /XObject << /Im0 3 0 R >> >> /Contents 5 0 R >>';
    var commands = bytesOf('q ' + PT_W + ' 0 0 ' + PT_H + ' 0 0 cm /Im0 Do Q');
    objects[5] = { header: '<< /Length ' + commands.length + ' >>', stream: commands };

    var chunks = [];
    var offset = 0;
    function push(dataIn) {
      var b = typeof dataIn === 'string' ? bytesOf(dataIn) : dataIn;
      chunks.push(b);
      offset += b.length;
    }
    push('%PDF-1.4\n');
    push('%\u00E2\u00E3\u00CF\u00D3\n');
    var offsets = [];
    for (var n = 1; n < objects.length; n++) {
      offsets[n] = offset;
      var obj = objects[n];
      if (obj && typeof obj === 'object') {
        push(n + ' 0 obj\n' + obj.header + '\nstream\n');
        push(obj.stream);
        push('\nendstream\nendobj\n');
      } else {
        push(n + ' 0 obj\n' + obj + '\nendobj\n');
      }
    }
    var xrefAt = offset;
    var xref = 'xref\n0 ' + objects.length + '\n0000000000 65535 f \n';
    for (var i = 1; i < objects.length; i++) {
      xref += String(offsets[i] || 0).padStart(10, '0') + ' 00000 n \n';
    }
    push(xref);
    push('trailer\n<< /Size ' + objects.length + ' /Root 1 0 R >>\nstartxref\n' + xrefAt + '\n%%EOF\n');

    var pdf = new Uint8Array(offset);
    var at = 0;
    chunks.forEach(function (c) { pdf.set(c, at); at += c.length; });
    return pdf;
  }

  function savePdf(data) {
    var canvas = draw(data);
    canvas.toBlob(function (blob) {
      if (!blob) return;
      blob.arrayBuffer().then(function (buffer) {
        var pdf = buildPdf(new Uint8Array(buffer), canvas.width, canvas.height);
        var url = URL.createObjectURL(new Blob([pdf], { type: 'application/pdf' }));
        var link = document.createElement('a');
        link.href = url;
        link.download = 'elemental-table-' + slug(data.student) + '-' + data.score + 'of' + data.total + '.pdf';
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
      });
    }, 'image/jpeg', 0.92);
  }

  return { save: save, savePdf: savePdf, draw: draw };
})();
