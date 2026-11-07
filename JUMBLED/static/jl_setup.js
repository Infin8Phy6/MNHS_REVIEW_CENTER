/* Grade -> Subject -> Quarter -> Topic, filled from the same tree the quiz form uses. */
(function () {
  var box = document.getElementById("specTree");
  if (!box) return;
  var tree = {};
  try { tree = JSON.parse(box.textContent) || {}; } catch (e) { return; }

  var grade = document.getElementById("grade");
  var subject = document.getElementById("subject");
  var quarter = document.getElementById("quarter");
  var topic = document.getElementById("topic");

  function fill(sel, items, keep) {
    var wanted = keep ? sel.value : "";
    sel.innerHTML = "";
    items.forEach(function (text) {
      var o = document.createElement("option");
      o.value = text;
      o.textContent = text;
      sel.appendChild(o);
    });
    if (wanted && items.indexOf(wanted) >= 0) sel.value = wanted;
    sel.disabled = !items.length;
  }

  var order = ["Grade 7", "Grade 8", "Grade 9", "Grade 10"];
  var levels = Object.keys(tree).sort(function (a, b) {
    var d = order.indexOf(a) - order.indexOf(b);
    return d === 0 ? (a < b ? -1 : 1) : (d < 0 ? -1 : 1);
  });
  fill(grade, levels);

  function subjects() { fill(subject, Object.keys(tree[grade.value] || {}).sort(), true); }
  function quarters() {
    var node = (tree[grade.value] || {})[subject.value] || {};
    fill(quarter, Object.keys(node).sort(function (a, b) {
      return parseInt(a.replace(/\D/g, ""), 10) - parseInt(b.replace(/\D/g, ""), 10);
    }), true);
  }
  function topics() {
    var node = (tree[grade.value] || {})[subject.value] || {};
    fill(topic, (node[quarter.value] || []).slice(), true);
  }

  grade.addEventListener("change", function () { subjects(); quarters(); topics(); });
  subject.addEventListener("change", function () { quarters(); topics(); });
  quarter.addEventListener("change", topics);

  subjects(); quarters(); topics();
})();

/* Single player or a multiplayer room — one form, the mode is just a flag. */
(function () {
  var solo = document.getElementById("modeSolo");
  var room = document.getElementById("modeRoom");
  var field = document.getElementById("soloField");
  var go = document.getElementById("goBtn");
  if (!solo || !room || !field || !go) return;

  var note = document.getElementById("modeNote");
  var roomNote = document.getElementById("roomNote");

  function use(multi) {
    field.value = multi ? "" : "1";
    go.textContent = multi ? "Create the room" : "Play alone";
    solo.classList.toggle("on", !multi);
    room.classList.toggle("on", multi);
    solo.setAttribute("aria-selected", String(!multi));
    room.setAttribute("aria-selected", String(multi));
    note.classList.toggle("hide", multi);
    roomNote.classList.toggle("hide", !multi);
  }

  solo.addEventListener("click", function () { use(false); });
  room.addEventListener("click", function () { use(true); });
})();
