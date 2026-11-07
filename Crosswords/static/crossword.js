/* The play board: click successive tiles in a straight line, press Check.
   Letters all come from /api/state; the server alone decides points. */
(function () {
  var board = document.querySelector(".board");
  if (!board) return;
  var URLS = {state: board.dataset.state, check: board.dataset.check,
              finish: board.dataset.finish, result: board.dataset.result};
  var gridBox = document.getElementById("grid");
  var clock = document.getElementById("clock");
  var scoreEl = document.getElementById("score");
  var say = document.getElementById("say");

  var state = null;
  var selection = [];          // [[r,c], ...] straight and contiguous
  var target = null;           // clue number the solver is answering, or null
  var tick = null;

  function sameCell(a, b) { return a[0] === b[0] && a[1] === b[1]; }

  function adjacentEnd(cell) {
    // extend the run only along its own row or column, touching an end tile
    var head = selection[0], tail = selection[selection.length - 1];
    if (selection.length === 1) {
      if ((cell[0] === head[0] && Math.abs(cell[1] - head[1]) === 1) ||
          (cell[1] === head[1] && Math.abs(cell[0] - head[0]) === 1)) return "grow";
      return "reset";
    }
    var dr = tail[0] - head[0], dc = tail[1] - head[1];
    var stepR = dr ? dr / Math.abs(dr) : 0, stepC = dc ? dc / Math.abs(dc) : 0;
    if ((cell[0] === tail[0] + stepR && cell[1] === tail[1] + stepC) ||
        (cell[0] === head[0] - stepR && cell[1] === head[1] - stepC)) return "grow";
    return "reset";
  }

  function paint() {
    // The layout lives on the element itself, too: a tablet still holding an
    // old cached stylesheet must never stack the tiles into a one-letter list.
    gridBox.style.display = "grid";
    gridBox.style.gap = "2px";
    gridBox.style.gridTemplateColumns = "repeat(" + state.cols + ", minmax(0, 1fr))";
    gridBox.innerHTML = "";
    for (var r = 0; r < state.rows; r++) {
      for (var c = 0; c < state.cols; c++) {
        var cell = document.createElement("div");
        cell.className = "cell";
        if (selection.some(function (s) { return s[0] === r && s[1] === c; })) {
          cell.classList.add("sel");
        }
        cell.textContent = state.grid[r][c];
        cell.dataset.r = r; cell.dataset.c = c;
        gridBox.appendChild(cell);
      }
    }
    ["across", "down"].forEach(function (id) {
      var box = document.getElementById(id);
      box.innerHTML = "";
      state.clues
        .filter(function (cl) { return cl.dir === (id === "across" ? "H" : "V"); })
        .sort(function (a, b) { return a.n - b.n; })
        .forEach(function (cl) {
          var li = document.createElement("li");
          li.innerHTML = "<b>" + cl.n + ".</b> " + escapeText(cl.clue ||
            "(" + cl.length + " letters)");
          if (cl.solved) { li.className = "solved"; li.innerHTML = "<b>" + cl.n +
            ".</b> <s>" + escapeText(cl.clue || "") + "</s> " + cl.word; }
          if (target === cl.n && !cl.solved) li.className = "target";
          li.onclick = function () {
            if (!cl.solved) { target = (target === cl.n ? null : cl.n); paint(); }
          };
          box.appendChild(li);
        });
    });
    scoreEl.textContent = state.score;
    drawClock();
  }

  function escapeText(t) {
    var d = document.createElement("span");
    d.textContent = t;
    return d.innerHTML;
  }

  function drawClock() {
    var s = state.seconds_left;
    clock.textContent = Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2);
    clock.classList.toggle("low", s <= 30 && s > 0);
  }

  gridBox.addEventListener("click", function (ev) {
    var cell = ev.target.closest(".cell");
    if (!cell || state.finished) return;
    var r = +cell.dataset.r, c = +cell.dataset.c;
    var here = [r, c];
    if (selection.length && sameCell(here, selection[selection.length - 1])) {
      selection.pop();                       // second tap on the last tile undoes it
    } else if (!selection.length) {
      selection = [here];
    } else {
      var move = adjacentEnd(here);
      if (move === "grow") selection.push(here);
      else selection = [here];
    }
    paint();
  });

  document.getElementById("clear").onclick = function () {
    selection = []; target = null; paint();
  };

  document.getElementById("check").onclick = function () {
    if (state.finished || selection.length < 2) {
      tell("Click the tiles that spell the answer first.", "bad");
      return;
    }
    post(URLS.check, {n: target, cells: selection}, function (res) {
      if (res.reason === "finished" || res.reason === "timeout" ||
          res.reason === "closed") { window.location = URLS.result; return; }
      if (res.matched && res.already) tell("Number " + res.n + " is already banked.", "");
      else if (res.matched) { tell(res.points + " points for " + res.n + "!", "good");
                              selection = []; target = null; }
      else tell("That run is not the word. Keep looking.", "bad");
      refresh();
    });
  };

  document.getElementById("done").onclick = function () {
    post(URLS.finish, {}, function () { window.location = URLS.result; });
  };

  function tell(msg, kind) {
    say.textContent = msg;
    say.className = "say " + (kind || "");
  }

  function post(url, body, done) {
    fetch(url, {method: "POST", headers: {"Content-Type": "application/json"},
                body: JSON.stringify(body)})
      .then(function (r) { return r.json(); }).then(done)
      .catch(function () { tell("The review center could not be reached.", "bad"); });
  }

  function refresh() {
    fetch(URLS.state).then(function (r) { return r.json(); }).then(function (s) {
      if (s.finished) { window.location = URLS.result; return; }
      state = s;   // the solver's half-built selection stays on screen
      paint();
    }).catch(function () {});
  }

  tick = setInterval(function () {
    if (!state || state.finished) return;
    state.seconds_left = Math.max(0, state.seconds_left - 1);
    drawClock();
    if (state.seconds_left % 2 === 0) refresh();
  }, 1000);

  refresh();
})();