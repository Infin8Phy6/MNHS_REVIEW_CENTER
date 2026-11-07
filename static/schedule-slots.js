// A class may meet for a double period, so one schedule can hold several
// time slots. Rows are cloned and renamed by index before posting; the
// server reads days_N, start_N, end_N plus slot_count.
(function () {
  var LIMIT = 8;

  function rowsIn(box) {
    return box.querySelectorAll('.cs-slot');
  }

  function reindex(box) {
    var slots = box.querySelector('.cs-slots');
    var count = box.querySelector('input[name="slot_count"]');
    if (!slots || !count) return;
    var rows = rowsIn(slots);
    Array.prototype.forEach.call(rows, function (row, index) {
      Array.prototype.forEach.call(row.querySelectorAll('input[type="checkbox"]'), function (input) {
        input.name = 'days_' + index;
      });
      Array.prototype.forEach.call(row.querySelectorAll('input[type="time"]'), function (input) {
        input.name = input.getAttribute('data-kind') + '_' + index;
      });
      // One row alone is the whole schedule, so nothing to remove yet.
      var del = row.querySelector('.cs-del-slot');
      if (del) del.hidden = rows.length < 2;
    });
    count.value = rows.length;
    var add = box.querySelector('.cs-add-slot');
    if (add) add.disabled = rows.length >= LIMIT;
  }

  document.addEventListener('click', function (event) {
    var add = event.target.closest('.cs-add-slot');
    if (add) {
      var box = add.closest('[data-slots]');
      var slots = box.querySelector('.cs-slots');
      if (rowsIn(slots).length >= LIMIT) return;
      // Clone the first row for its markup, then clear its ticks and times.
      var row = rowsIn(slots)[0].cloneNode(true);
      Array.prototype.forEach.call(row.querySelectorAll('input'), function (input) {
        if (input.type === 'checkbox') input.checked = false;
        else input.value = '';
      });
      slots.appendChild(row);
      reindex(box);
      row.querySelector('input[type="time"]').focus();
      return;
    }
    var del = event.target.closest('.cs-del-slot');
    if (del) {
      var box2 = del.closest('[data-slots]');
      if (rowsIn(box2.querySelector('.cs-slots')).length < 2) return;
      del.closest('.cs-slot').remove();
      reindex(box2);
    }
  });

  Array.prototype.forEach.call(document.querySelectorAll('[data-slots]'), reindex);
})();
