// Elemental Table Game - typing, checking and the landscape sheet.
window.ETABLE = (function () {
  var cfg = null;
  var last = null;   // the marks and score from the newest check, for the download

  function inputs() {
    return Array.prototype.slice.call(document.querySelectorAll('#etg input'));
  }

  function cells() {
    var out = {};
    inputs().forEach(function (box) {
      out[box.getAttribute('data-r') + ':' + box.getAttribute('data-col')] = box.value;
    });
    return out;
  }

  function clearMarks() {
    document.querySelectorAll('#etg td.blank').forEach(function (td) {
      td.classList.remove('is-ok', 'is-no');
      var fix = td.querySelector('.fix');
      if (fix) fix.remove();
    });
  }

  function paint(marks) {
    clearMarks();
    marks.forEach(function (mark) {
      var td = document.querySelector('#etg td[data-cell="' + mark.r + ':' + mark.col + '"]');
      if (!td) return;
      td.classList.add(mark.ok ? 'is-ok' : 'is-no');
      if (!mark.ok) {
        var note = document.createElement('span');
        note.className = 'fix';
        note.textContent = mark.truth;
        td.appendChild(note);
      }
    });
  }

  function showScore(score, total, marks) {
    var byRow = {};
    marks.forEach(function (m) { byRow[m.r] = (byRow[m.r] || 0) + (m.ok ? 1 : 0); });
    var rows = Object.keys(byRow).sort(function (a, b) { return a - b; })
      .map(function (r) { return 'row ' + (Number(r) + 1) + ': ' + byRow[r] + '/' + cfg.table[r].blanks.length; });
    var box = document.getElementById('score');
    box.innerHTML = '<b>' + score + ' / ' + total + '</b> &nbsp;' +
      (score === total ? 'Every cell right - the whole table is yours.' :
        (score >= 20 ? 'Strong. Fix the misses below and deal another for a cleaner sheet.' :
          'Read the clues in the row again: protons = electrons, mass = protons + neutrons, ' +
          'and the group gives the valence count.')) +
      '<div class="key">' + rows.join(' &middot; ') + '</div>';
    box.hidden = false;
  }

  function setDownloadReady() {
    document.getElementById('downloadPng').disabled = false;
    document.getElementById('downloadPdf').disabled = false;
  }

  function check() {
    var button = document.getElementById('check');
    button.disabled = true;
    fetch(cfg.checkUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cells: cells() })
    }).then(function (res) {
      if (!res.ok) throw new Error('check failed');
      return res.json();
    }).then(function (data) {
      last = data;
      paint(data.marks);
      showScore(data.score, data.total, data.marks);
      setDownloadReady();
    }).catch(function () {
      var box = document.getElementById('score');
      box.textContent = 'The check did not go through. Keep the page open and try again.';
      box.hidden = false;
    }).finally(function () {
      button.disabled = false;
    });
  }

  function payload() {
    return {
      student: cfg.student,
      heads: cfg.heads,
      columns: cfg.columns,
      table: last.table,
      marks: last.marks,
      score: last.score,
      total: last.total,
      typed: cells()
    };
  }

  function downloadPng() {
    if (!last) return;
    window.ETABLE_EXPORT.save(payload());
  }

  function downloadPdf() {
    if (!last) return;
    window.ETABLE_EXPORT.savePdf(payload());
  }

  function restore() {
    if (!cfg.checked || !cfg.saved || !cfg.saved.length) return;
    cfg.saved.forEach(function (mark) {
      var box = document.querySelector('#etg input[data-r="' + mark.r + '"][data-col="' + mark.col + '"]');
      if (box) box.value = mark.given;
    });
    paint(cfg.saved);
    showScore(cfg.savedScore, cfg.maxPoints, cfg.saved);
    last = { score: cfg.savedScore, total: cfg.maxPoints, marks: cfg.saved, table: cfg.table };
    setDownloadReady();
  }

  return {
    start: function (config) {
      cfg = config;
      document.getElementById('check').addEventListener('click', check);
      document.getElementById('downloadPng').addEventListener('click', downloadPng);
      document.getElementById('downloadPdf').addEventListener('click', downloadPdf);
      inputs().forEach(function (box, i) {
        box.addEventListener('keydown', function (event) {
          if (event.key === 'Enter') {
            event.preventDefault();
            var next = inputs()[i + 1];
            if (next) next.focus(); else check();
          }
        });
      });
      var first = inputs()[0];
      if (first) first.focus();
      restore();
    }
  };
})();
