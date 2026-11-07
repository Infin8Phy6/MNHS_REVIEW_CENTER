/* Grade -> Section cascading selects.
 *
 * A page marks its two picks with data-grade-pick and data-section-pick (the
 * section names the grade select through data-from) and carries the class list
 * in a JSON script tag, so the section box refills the moment the grade changes
 * instead of waiting for a submit.
 */
(function () {
  function boot() {
    var node = document.getElementById('rh-classes');
    if (!node) return;
    var map;
    try {
      map = JSON.parse(node.textContent || '{}');
    } catch (problem) {
      return;
    }

    Array.prototype.forEach.call(
      document.querySelectorAll('select[data-section-pick]'), function (section) {
        var grade = document.getElementById(section.getAttribute('data-from'));
        if (!grade) return;
        var blank = section.querySelector('option[value=""]');
        var blankText = blank ? blank.textContent : '-- Choose Section --';

        function fill(keep, first) {
          var names = map[grade.value] || [];
          section.disabled = !grade.value;
          section.innerHTML = '';
          var head = document.createElement('option');
          head.value = '';
          head.textContent = names.length ? blankText : 'no section for this grade';
          section.appendChild(head);
          names.forEach(function (name) {
            section.appendChild(new Option(name, name));
          });
          // A record can still hold a class nobody has on the list any more.
          // On the first build it stays selectable so the page is not edited by
          // accident; once the grade is touched it goes, because it belongs to
          // the grade that was just picked.
          if (keep && first && names.indexOf(keep) < 0) {
            section.appendChild(new Option(keep + ' (not on the Classes page)', keep));
          } else if (keep && names.indexOf(keep) < 0) {
            keep = '';
          }
          section.value = keep || '';
        }

        // The server already chose the right pair, so start from its section.
        fill(section.getAttribute('data-current') || section.value, true);
        grade.addEventListener('change', function () { fill(''); });
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
