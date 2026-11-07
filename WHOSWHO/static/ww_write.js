/* The admin form: one block per person, added as many times as the teacher likes.

   Every field keeps the same name, so the server reads matching lists by index.
   Only the file inputs need an index of their own, because a blank file input
   still posts a part. */
(function () {
  var form = document.getElementById("actForm");
  var box = document.getElementById("people");
  var seed = document.getElementById("seed");
  var tpl = document.getElementById("personRow");
  if (!form || !box || !tpl) return;

  var rows = [];
  try { rows = JSON.parse(seed.textContent) || []; } catch (e) { rows = []; }

  function make(data) {
    var node = tpl.content.cloneNode(true).querySelector(".person");
    var d = data || {};
    node.querySelector("[name=person_id]").value = d.id || "";
    node.querySelector("[name=name]").value = d.name || "";
    var clues = d.clues || ["", "", "",];
    [1, 2, 3].forEach(function (n) {
      node.querySelector("[name=clue" + n + "]").value = (clues[n - 1] || "").trim();
    });

    var photo = d.photo || {};
    var have = photo.file || photo.drive_id;
    if (have) {
      var img = node.querySelector(".thumb");
      img.src = d.preview || "";
      img.classList.remove("hide");
      node.querySelector(".keep").classList.remove("hide");
      node.querySelector(".current").textContent =
        photo.drive_id ? "Saved in Google Drive" : "Saved on this computer";
    }
    node.querySelector(".drop").addEventListener("click", function () {
      node.remove();
      renumber();   // otherwise the survivors keep freed photo<i> numbers
    });
    node.dataset.hasPhoto = have ? "1" : "";
    box.appendChild(node);
    return node;
  }

  rows.forEach(make);
  if (!rows.length) make();

  document.getElementById("addPerson").addEventListener("click", function () {
    make();
    renumber();
    box.lastElementChild.querySelector("[name=name]").focus();
  });

  function renumber() {
    Array.prototype.forEach.call(box.children, function (node, i) {
      node.querySelector(".n").textContent = i + 1;
      node.querySelector(".file").name = "photo" + i;
      var keep = node.querySelector(".keepBox");
      keep.name = "keep_photo" + i;   // indexed, or an unchecked box shifts every row
      keep.value = "1";
      keep.checked = !!node.dataset.hasPhoto;
      /* A file input with nothing chosen still posts an empty part, which the
         server would read as "replace the picture". Off with it. */
      node.querySelector(".file").disabled = !node.querySelector(".file").files.length &&
        !!node.dataset.hasPhoto;
    });
  }

  box.addEventListener("change", function (ev) {
    if (ev.target.classList.contains("file")) {
      var node = ev.target.closest(".person");
      if (ev.target.files.length) {
        node.dataset.hasPhoto = "";
        node.querySelector(".keep").classList.add("hide");
        node.querySelector(".current").textContent = "New file: " + ev.target.files[0].name;
      }
    }
    renumber();
  });

  box.addEventListener("click", function (ev) {
    if (ev.target.classList.contains("keepBox")) {
      var node = ev.target.closest(".person");
      node.querySelector(".file").disabled = ev.target.checked;
    }
  });

  box.lastElementChild && renumber();

  /* A person without a picture cannot be guessed, so stop the save here and
     point at the block that needs one. The server checks it again. */
  form.addEventListener("submit", function (ev) {
    renumber();
    var notice = document.getElementById("photoNotice");
    var bad = [];
    Array.prototype.forEach.call(box.children, function (node, i) {
      var file = node.querySelector(".file");
      var keep = node.querySelector(".keepBox");
      var named = node.querySelector("[name=name]").value.trim();
      var has = (file.files && file.files.length > 0) ||
                (node.dataset.hasPhoto === "1" && keep.checked);
      node.classList.toggle("bad", !!named && !has);
      if (named && !has) bad.push(i + 1);
    });
    if (!bad.length) {
      if (notice) { notice.classList.add("hide"); }
      return;
    }
    ev.preventDefault();
    if (notice) {
      notice.textContent = "Add a picture for person " + bad.join(", ") +
        " before saving this activity.";
      notice.classList.remove("hide");
      notice.scrollIntoView({block: "center"});
    }
    var first = box.querySelectorAll(".person.bad")[0];
    if (first) { first.scrollIntoView({block: "center"}); }
  });
})();
