/* The Who's Who board. The server holds the round, so every player in a room is
   looking at the same person, and the 10 second count after the third clue runs
   even in a tab that Chrome has slowed down. */
(function () {
  var board = document.getElementById("board");
  if (!board) return;

  function attr(name) { return board.getAttribute(name); }
  var token = attr("data-token");
  var urls = {state: attr("data-state"), reveal: attr("data-reveal"),
              answer: attr("data-answer"), next: attr("data-next"),
              reserve: attr("data-reserve"), start: attr("data-start")};

  function id(name) { return document.getElementById(name); }
  var ui = {title: id("title"), counter: id("counter"), code: id("code"),
            joinUrl: id("joinUrl"), lobby: id("lobby"), live: id("live"),
            closed: id("closed"), podium: id("podium"), photo: id("photo"),
            noPhoto: id("noPhoto"),
            tiles: id("tiles"), clues: [id("c1"), id("c2"), id("c3")],
            reveals: [id("r1"), id("r2"), id("r3")], worth: id("worth"),
            tickNote: id("tickNote"), form: id("answerForm"), given: id("given"),
            feedback: id("feedback"), scores: id("scores"), playersNote: id("playersNote"),
            giveUp: id("giveUp"), nextBtn: id("nextBtn"), startBtn: id("startBtn"),
            hostNote: id("hostNote"), closedNote: id("closedNote"), invite: id("invite"),
            past: id("past"), revealCard: id("revealCard"), shuffle: id("shuffle")};

  var lastTurn = "", lastJumble = "", tick = null, clueText = [], solo = false,
      live = false, praise = 0, shuffler = null;

  function show(node, on) { node.classList.toggle("hide", !on); }

  function tiles(word) {
    ui.tiles.innerHTML = "";
    String(word || "").split("").forEach(function (ch) {
      var t = document.createElement("span");
      t.textContent = ch;
      ui.tiles.appendChild(t);
    });
  }

  function deal(letters) {
    for (var i = letters.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var keep = letters[i]; letters[i] = letters[j]; letters[j] = keep;
    }
    return letters.join("");
  }

  function shuffle() {
    /* Re-deal the same letters - a fresh look, never a new clue. */
    var letters = String(lastJumble || "").split("");
    if (letters.length < 3) return;
    var shown = ui.tiles.textContent, text = shown;
    for (var n = 0; n < 12 && text === shown; n++) text = deal(letters.slice(0));
    tiles(text);
  }

  function paint_clues(person) {
    clueText = (person && person.clues) || [];
    ui.clues.forEach(function (node, i) {
      var text = clueText[i] || "";
      node.querySelector("p").textContent = text || "Not written for this person.";
      var open = !!(person && person.reveals > i);
      show(node, open);
      node.classList.toggle("on", open);
    });
  }

  function scores(list) {
    ui.scores.innerHTML = "";
    list.forEach(function (row, i) {
      var li = document.createElement("li");
      li.className = "row" + (row.you ? " you" : "");
      li.innerHTML = '<b class="place"></b><span class="who"></span><b class="pts"></b>';
      li.querySelector(".place").textContent = i + 1;
      li.querySelector(".who").textContent = row.name + (row.you ? " (you)" : "");
      li.querySelector(".pts").textContent = row.score;
      ui.scores.appendChild(li);
    });
  }

  function podium(list) {
    [["first", "p1", "s1", 0], ["second", "p2", "s2", 1], ["third", "p3", "s3", 2]]
      .forEach(function (spot) {
        var node = document.querySelector(".pod." + spot[0]);
        var row = list[spot[3]];
        show(node, !!row);
        if (!row) return;
        id(spot[1]).textContent = row.name;
        id(spot[2]).textContent = row.score + (row.score === 1 ? " pt" : " pts");
      });
    show(ui.podium, list.length > 0);
  }

  function past(list) {
    ui.past.innerHTML = "";
    list.forEach(function (row) {
      var li = document.createElement("li");
      var pic = document.createElement("b");
      if (row.photo) {
        var img = document.createElement("img");
        img.alt = "";
        img.src = row.photo_url;
        li.appendChild(img);
      } else {
        pic.textContent = "?";
        li.appendChild(pic);
      }
      var name = document.createElement("b");
      name.textContent = row.name;
      li.appendChild(name);
      ui.past.appendChild(li);
    });
    show(ui.revealCard, list.length > 0);
  }

  function paint(state) {
    solo = !!state.solo;
    live = state.status === "playing";
    ui.title.textContent = state.title || "Who's Who";
    ui.code.textContent = state.code;
    if (ui.joinUrl.value !== state.join_url) ui.joinUrl.value = state.join_url;
    ui.counter.textContent = (state.index + 1) + " of " + state.total + " people";
    ui.playersNote.textContent = solo
      ? "Playing alone · your score " + state.me.score
      : state.players.length + " player" + (state.players.length === 1 ? "" : "s") +
        " in this room · you are " + state.me.name + " · your score " + state.me.score;
    scores(state.scores || []);

    var lobby = state.status === "lobby";
    show(ui.lobby, lobby);
    show(ui.live, state.status === "playing");
    show(ui.closed, state.status === "done");
    show(ui.invite, !solo && state.status !== "done");

    if (lobby) {
      show(ui.startBtn, state.host);
      ui.hostNote.style.display = state.host ? "none" : "block";
      return;
    }

    if (state.status === "done") {
      if (solo) {
        show(ui.podium, false);
        var mine = (state.scores || [])[0];
        ui.closedNote.textContent = "You scored " + (mine ? mine.score : state.me.score) +
          " points over " + state.total + " people.";
      } else {
        podium(state.scores || []);
        ui.closedNote.textContent = "Champion, First Place and Second Place are decided by total points.";
      }
      past(state.past || []);
      return;
    }

    var person = state.person;
    if (!person) return;
    /* The board is re-read every second, but the letters are a clue, not a
       slot machine. Tiles, picture and the answer box are dealt once per
       person, so a half-typed name survives the polling. */
    var turn = [state.status, state.slug, state.index].join("-");
    if (turn !== lastTurn) {
      lastTurn = turn;
      lastJumble = person.jumble;
      tiles(person.jumble);
      ui.given.value = "";
      /* A correct name moves a solo round straight on, so the next poll would
         wipe the Bravo line before anyone reads it. Hold it a moment. */
      if (Date.now() >= praise) {
        ui.feedback.textContent = "";
        ui.feedback.className = "fb";
      }
      /* The picture is the first clue, so it leads the board. A person saved
         without one gets a clear note instead of the game logo. */
      ui.photo.src = person.photo_url;
      show(ui.photo, !!person.photo);
      show(ui.noPhoto, !person.photo);
      paint_clues(person);
      start_clock();
    }
    if (person.reveals !== undefined) {
      paint_clues(person);
      ui.reveals.forEach(function (btn, i) { btn.disabled = person.reveals > i || person.locked; });
    }
    ui.worth.textContent = person.points_next;
    ui.given.disabled = !!person.locked;
    ui.giveUp.disabled = !!person.locked;
    show(ui.nextBtn, !solo && state.host && state.status === "playing");
    /* The count only runs after the third clue, exactly as the game is scored. */
    tick = (person.reveals >= 3 && !person.locked) ? state.me.seconds_left : null;
    countdown();
  }

  function countdown() {
    if (tick === null) { ui.tickNote.textContent = ""; return; }
    ui.tickNote.textContent = tick > 0
      ? "Time left for this person: " + tick + "s."
      : "That person is closed.";
  }

  function post(url, fields, done) {
    var body = "p=" + encodeURIComponent(token);
    Object.keys(fields || {}).forEach(function (k) {
      body += "&" + encodeURIComponent(k) + "=" + encodeURIComponent(fields[k]);
    });
    fetch(url, {method: "POST", credentials: "same-origin",
                headers: {"Content-Type": "application/x-www-form-urlencoded"}, body: body})
      .then(function (r) { return r.json(); }).then(done).catch(function () {
        ui.feedback.textContent = "Send it again.";
        ui.feedback.className = "fb no";
      });
  }

  ui.reveals.forEach(function (btn) {
    btn.addEventListener("click", function () {
      post(urls.reveal, {level: btn.getAttribute("data-level")}, function (out) {
        if (out.error) return;
        var level = out.reveals;
        ui.clues.forEach(function (node, i) {
          node.classList.toggle("on", level > i);
          show(node, level > i);
        });
        ui.reveals.forEach(function (other, i) { other.disabled = level > i; });
        ui.worth.textContent = out.points_next;
        if (level === 3) { tick = out.seconds_left; }
        ui.feedback.textContent = level === 3
          ? "Last clue shown — " + out.seconds_left + " seconds left."
          : "Clue " + level + " revealed. This person is now worth " + out.points_next + " points.";
        ui.feedback.className = "fb";
        poll();
      });
    });
  });

  ui.form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var text = ui.given.value.trim();
    if (!text) return;
    post(urls.answer, {given: text}, function (out) {
      if (out.kind === "hit") {
        ui.feedback.textContent = "Bravo! " + out.answer + " — " + out.points + " points.";
        ui.feedback.className = "fb ok";
        praise = Date.now() + 3500;
        setTimeout(function () {
          if (Date.now() >= praise) {
            ui.feedback.textContent = "";
            ui.feedback.className = "fb";
          }
        }, 3700);
        ui.given.value = "";
        ui.given.disabled = true;
      } else {
        ui.feedback.textContent = out.reason || "Not this time.";
        ui.feedback.className = "fb no";
      }
      poll();
    });
  });

  ui.giveUp.addEventListener("click", function () {
    post(urls.reserve, {}, function () { poll(); });
  });
  ui.nextBtn.addEventListener("click", function () { post(urls.next, {}, poll); });
  ui.startBtn.addEventListener("click", function () { post(urls.start, {}, poll); });
  ui.shuffle.addEventListener("click", function () { shuffle(); start_clock(); });

  id("copyLink").addEventListener("click", function () {
    ui.joinUrl.removeAttribute("readonly");
    ui.joinUrl.select();
    try { document.execCommand("copy"); } catch (e) {}
    ui.joinUrl.setAttribute("readonly", "readonly");
    id("copyLink").textContent = "Copied";
    setTimeout(function () { id("copyLink").textContent = "Copy"; }, 1600);
  });

  function poll() {
    fetch(urls.state + "?p=" + encodeURIComponent(token), {credentials: "same-origin"})
      .then(function (r) {
        if (r.status === 401 || r.status === 404) {
          window.location.href = urls.state.replace("/api/state/", "/join/") +
            "?p=" + encodeURIComponent(token);
          return null;
        }
        return r.json();
      })
      .then(function (state) { if (state && !state.error) paint(state); })
      .catch(function () { /* the board keeps its last picture until the next poll */ });
  }

  setInterval(function () {
    if (tick === null) return;
    tick = Math.max(0, tick - 1);
    countdown();
  }, 1000);
  /* The letters keep moving every ten seconds while a person is open. Only the
     tiles move - the name being typed is never touched. */
  function start_clock() {
    clearInterval(shuffler);
    shuffler = setInterval(function () { if (live && !ui.given.disabled) shuffle(); }, 10000);
  }
  start_clock();
  setInterval(poll, 1500);
  poll();
})();
