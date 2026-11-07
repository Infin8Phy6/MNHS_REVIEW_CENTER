// The staff profile alarm: three minutes before a class meets, the page
// flashes a banner, highlights that cell on the weekly table, beeps and -
// when the browser allows it - sends a system notification. Meetings come
// from the JSON block the profile prints; the tab only has to be open.
(function () {
  var LEAD_MINUTES = 3;
  var DAY_NAMES = { 0: 'Sun', 1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri', 6: 'Sat' };

  var box = document.getElementById('sched-meetings');
  if (!box) return;
  var meetings;
  try {
    meetings = JSON.parse(box.textContent);
  } catch (e) {
    return;
  }

  var fired = {};

  function toMinutes(text) {
    var parts = String(text || '').split(':');
    if (parts.length !== 2) return null;
    var h = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10);
    if (isNaN(h) || isNaN(m)) return null;
    return h * 60 + m;
  }

  function beep() {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      var ctx = new Ctx();
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.type = 'square';
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.12, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.6);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.6);
      osc.onended = function () { ctx.close(); };
    } catch (e) { /* a locked-down browser simply stays quiet */ }
  }

  function flash(meeting) {
    var what = meeting.section + ' - ' +
      (meeting.subjects && meeting.subjects.length
        ? meeting.subjects.join(', ')
        : 'every subject') +
      ' (' + meeting.grade + ')' +
      (meeting.room ? ' in ' + meeting.room : '');
    var banner = document.getElementById('sched-alarm');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'sched-alarm';
      banner.className = 'sched-alarm';
      banner.setAttribute('role', 'alert');
      var text = document.createElement('div');
      text.className = 'sched-alarm-text';
      banner.appendChild(text);
      var close = document.createElement('button');
      close.type = 'button';
      close.className = 'sched-alarm-close';
      close.setAttribute('aria-label', 'Dismiss the class alarm');
      close.innerHTML = '&#215;';
      close.addEventListener('click', function () { banner.remove(); });
      banner.appendChild(close);
      document.body.appendChild(banner);
    }
    banner.querySelector('.sched-alarm-text').textContent =
      'Class in 3 minutes: ' + what + ' starts at ' + meeting.start + '.';
    var cell = document.querySelector(
      '.sched-block[data-day="' + meeting.day +
      '"][data-section="' + meeting.section +
      '"][data-start="' + meeting.start + '"]');
    if (cell) cell.classList.add('sched-soon');
    beep();
    if (window.Notification) {
      if (Notification.permission === 'granted') {
        new Notification('Class in 3 minutes', {
          body: what + ' starts at ' + meeting.start + '.',
        });
      } else if (Notification.permission !== 'denied') {
        Notification.requestPermission();
      }
    }
  }

  function tick() {
    var now = new Date();
    var day = DAY_NAMES[now.getDay()];
    var nowMinutes = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
    meetings.forEach(function (meeting) {
      if (meeting.day !== day || !meeting.start) return;
      var start = toMinutes(meeting.start);
      if (start === null) return;
      var key = day + '|' + meeting.section + '|' + meeting.start;
      if (fired[key]) return;
      var delta = start - nowMinutes;
      if (delta > 0 && delta <= LEAD_MINUTES) {
        fired[key] = true;
        flash(meeting);
      }
    });
  }

  // Ask for notification permission once the teacher first clicks the page,
  // so browsers that require a gesture still allow the alarm outside the tab.
  if (window.Notification && Notification.permission === 'default') {
    document.addEventListener('click', function once() {
      document.removeEventListener('click', once);
      Notification.requestPermission();
    });
  }

  tick();
  setInterval(tick, 15000);
})();
