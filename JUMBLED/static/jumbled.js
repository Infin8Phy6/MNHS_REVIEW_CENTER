/* The live board. Everything on screen comes from the server, so all players in
   a room see the same word and the same countdown. */
(function () {
  var board = document.getElementById("board");
  if (!board) return;

  var token = board.getAttribute("data-token");
  var stateUrl = board.getAttribute("data-state");
  var answerUrl = board.getAttribute("data-answer");
  var startUrl = board.getAttribute("data-start");
  var resultUrl = board.getAttribute("data-result");

  function id(name) { return document.getElementById(name); }
  var ui = {
    topic: id("topic"), path: id("path"), code: id("code"), joinUrl: id("joinUrl"),
    lobby: id("lobby"), live: id("live"), closed: id("closed"), podium: id("podium"),
    counter: id("counter"), bar: id("bar"), clock: id("clock"), jumble: id("jumble"),
    hint: id("hint"), form: id("answerForm"), given: id("given"), feedback: id("feedback"),
    scores: id("scores"), playersNote: id("playersNote"), words: id("words"),
    answersCard: id("answersCard"), startBtn: id("startBtn"), hostNote: id("hostNote"),
    closedNote: id("closedNote"), invite: id("invite"), need: id("needNote"),
    dlWrap: id("dlWrap"), dlResult: id("dlResult")
  };

  var wordSeconds = 90, shownWord = "", lastSeen = "", tick = null;

  function toggle(node, on) { node.classList.toggle("hide", !on); }

  function tiles(word) {
    ui.jumble.innerHTML = "";
    String(word || "").split("").forEach(function (ch) {
      var t = document.createElement("span");
      t.textContent = ch;
      ui.jumble.appendChild(t);
    });
  }

  function scores(list) {
    ui.scores.innerHTML = "";
    list.forEach(function (row, i) {
      var li = document.createElement("li");
      li.className = "row" + (row.you ? " you" : "");
      li.innerHTML = '<b class="place">' + (i + 1) + '</b><span class="who"></span>' +
                     '<b class="pts"></b>';
      li.querySelector(".who").textContent = row.name + (row.you ? " (you)" : "");
      li.querySelector(".pts").textContent = row.score;
      ui.scores.appendChild(li);
    });
  }

  function podium(list) {
    [["first", id("p1"), id("s1"), 0], ["second", id("p2"), id("s2"), 1],
     ["third", id("p3"), id("s3"), 2]].forEach(function (spot) {
      var node = document.querySelector(".pod." + spot[0]);
      var row = list[spot[3]];
      toggle(node, !!row);
      if (!row) return;
      spot[1].textContent = row.name;
      spot[2].textContent = row.score + (row.score === 1 ? " pt" : " pts");
    });
    toggle(ui.podium, list.length > 0);
  }

  function wordList(rows, clincher) {
    ui.words.innerHTML = "";
    rows.forEach(function (row) {
      var li = document.createElement("li");
      li.innerHTML = '<b class="n"></b><b class="w"></b><span class="f"></span>';
      li.querySelector(".n").textContent = row.index;
      li.querySelector(".w").textContent = row.word;
      li.querySelector(".f").textContent = row.cleared
        ? "cleared by " + (row.first || "a player") + " (topic word + 2 real words)"
        : row.first ? "first solved by " + row.first : "nobody solved it";
      ui.words.appendChild(li);
    });
    if (clincher && clincher.word) {
      var extra = document.createElement("li");
      extra.innerHTML = '<b class="n"></b><b class="w"></b><span class="f"></span>';
      extra.querySelector(".n").textContent = rows.length + 1;
      extra.querySelector(".w").textContent = clincher.word + " (clincher)";
      extra.querySelector(".f").textContent = "tie-break word";
      ui.words.appendChild(extra);
    }
    toggle(ui.answersCard, rows.length > 0);
  }

  function needLine(progress) {
    if (!ui.need) return;
    if (!progress) { ui.need.textContent = ""; return; }
    var left = Math.max(0, progress.need - progress.bonus);
    ui.need.textContent = !progress.solved
      ? "The topic word first, then " + progress.need + " more real words to move the board on."
      : left > 0
        ? "Topic word in — " + left + " more real word" + (left === 1 ? " clears" : "s clear") +
          " this jumble."
        : "Cleared — next jumble on the board.";
  }

  function paint(state) {
    needLine(null);
    ui.topic.textContent = state.topic || "Jumbled Letters";
    ui.path.textContent = [state.grade, state.subject, state.quarter].filter(Boolean).join(" · ");
    ui.code.textContent = state.code;
    if (ui.joinUrl.value !== state.join_url) ui.joinUrl.value = state.join_url;
    ui.playersNote.textContent = state.solo
      ? "Playing alone · your score " + state.me.score
      : state.players.length + " player" + (state.players.length === 1 ? "" : "s") +
        " in this room · you are " + state.me.name + " · your score " + state.me.score;

    wordSeconds = state.word_seconds || wordSeconds;
    scores(state.scores || []);

    var lobby = state.status === "lobby";
    toggle(ui.lobby, lobby);
    toggle(ui.live, state.status === "playing" || state.status === "clincher");
    toggle(ui.closed, state.status === "done");
    toggle(ui.invite, lobby && !state.solo);

    if (lobby) {
      toggle(ui.startBtn, !!state.host);
      ui.hostNote.style.display = state.host ? "none" : "block";
      return;
    }

    if (state.status === "done") {
      if (state.solo) {
        toggle(ui.podium, false);
        var mine = (state.scores || [])[0];
        ui.closedNote.textContent = "You scored " + (mine ? mine.score : state.me.score) +
          " point" + (mine && mine.score === 1 ? "" : "s") + " out of a possible " +
          (state.total * 5) + ".";
        if (ui.dlWrap && resultUrl) {
          ui.dlResult.href = resultUrl + "?p=" + encodeURIComponent(token);
          toggle(ui.dlWrap, true);
        }
      } else {
        podium(state.scores || []);
        ui.closedNote.textContent = state.tied && state.tied.length
          ? "A clincher word settled the tie."
          : "Champion, First Place and Second Place are decided by total points.";
        toggle(ui.dlWrap, false);
      }
      wordList(state.words || [], state.clincher_word);
      return;
    }

    var word = state.word;
    if (!word) return;
    needLine(state.progress);
    if (state.revealed && (state.code + state.status + word.jumble) !== lastSeen) {
      var won = state.revealed.first ? " by " + state.revealed.first : "";
      ui.hint.textContent = "Last word: " + state.revealed.word +
        (state.revealed.cleared ? " — cleared" + won + " (topic word and 2 real words)"
          : state.revealed.first ? " — first solved by " + state.revealed.first
            : " — nobody solved it");
    }
    if (word.jumble !== shownWord) {
      shownWord = word.jumble;
      tiles(word.jumble);
      ui.counter.querySelector("span").textContent = word.clincher
        ? "Clincher" : "Word " + (word.number || 1) + " of " + state.total;
      ui.given.value = "";
      ui.feedback.textContent = "";
      ui.feedback.className = "fb";
    }
    ui.given.disabled = !word.may_answer;
    if (!word.may_answer) {
      ui.hint.textContent = "This clincher is only for the tied players — watch the board.";
    }
    lastSeen = state.code + state.status + word.jumble;
    tick = state.seconds_left;
  }

  function countdown() {
    if (tick === null) return;
    tick = Math.max(0, tick - 1);
    ui.clock.textContent = tick + "s";
    ui.bar.style.width = Math.max(0, Math.min(100, (tick / wordSeconds) * 100)) + "%";
  }

  function poll() {
    fetch(stateUrl + "?p=" + encodeURIComponent(token), {credentials: "same-origin"})
      .then(function (r) {
        if (r.status === 401 || r.status === 404) {
          window.location.href = stateUrl.replace("/api/state/", "/join/") +
            "?p=" + encodeURIComponent(token);
          return null;
        }
        return r.json();
      })
      .then(function (state) { if (state && !state.error) paint(state); })
      .catch(function () { /* the room keeps its last picture until the next poll */ });
  }

  ui.form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var text = ui.given.value.trim();
    if (!text) return;
    var body = "p=" + encodeURIComponent(token) + "&given=" + encodeURIComponent(text);
    fetch(answerUrl, {
      method: "POST", credentials: "same-origin",
      headers: {"Content-Type": "application/x-www-form-urlencoded"}, body: body
    }).then(function (r) { return r.json(); }).then(function (out) {
      ui.feedback.textContent = out.passed ? "Cleared — the next jumble is up."
        : (out.reason || (out.points ? "+" + out.points : "No points."));
      ui.feedback.className = "fb " + (out.points ? "ok" : "no");
      ui.given.value = "";
      ui.given.focus();
      poll();
    }).catch(function () { ui.feedback.textContent = "Send it again."; });
  });

  ui.startBtn.addEventListener("click", function () {
    ui.startBtn.disabled = true;
    fetch(startUrl, {
      method: "POST", credentials: "same-origin",
      headers: {"Content-Type": "application/x-www-form-urlencoded"},
      body: "p=" + encodeURIComponent(token)
    }).then(function () { ui.startBtn.disabled = false; poll(); });
  });

  id("copyLink").addEventListener("click", function () {
    ui.joinUrl.removeAttribute("readonly");
    ui.joinUrl.select();
    try { document.execCommand("copy"); } catch (e) {}
    ui.joinUrl.setAttribute("readonly", "readonly");
    id("copyLink").textContent = "Copied";
    setTimeout(function () { id("copyLink").textContent = "Copy"; }, 1600);
  });

  setInterval(countdown, 1000);
  setInterval(poll, 1500);
  poll();
})();
