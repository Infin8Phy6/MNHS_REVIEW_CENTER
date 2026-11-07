/* Quantum Architect board.
 *
 * The rules live in Python (quantum/chemistry.py) and the wording + scoring come
 * from /api/engine, so this file only mirrors the decision logic. If a message or
 * a number changes, it changes server-side first.
 */
(function () {
  'use strict';

  // qa_play.html injects this so the board keeps working when the Review Center
  // mounts this game under /games/quantum-architect instead of at the site root.
  const BASE = window.QA_BASE || '/';
  const el = (id) => document.getElementById(id);
  const boardEl = el('board');
  const ladderEl = el('ladder');
  const poolEl = el('pool-tokens');
  const feedbackEl = el('feedback');

  const UP = '\u2191';
  const DOWN = '\u2193';
  const CAPACITY = { s: 2, p: 6, d: 10, f: 14 };
  const ORBITALS = { s: 1, p: 3, d: 5, f: 7 };

  let SHARED = null;
  let DATA = null;
  let want = {};
  let madelungWant = {};
  let exceptionSublevels = new Set();
  let valSubs = new Set();
  let valShells = new Set();
  let shown = [];
  let S = null;
  let ticking = null;

  // ---------------------------------------------------------------- utilities
  const subType = (name) => name.slice(-1);
  const shellOf = (name) => Number(name.charAt(0));
  const capOf = (name) => CAPACITY[subType(name)];
  const boxesOf = (name) => ORBITALS[subType(name)];

  function madelungTargets(z) {
    const out = {};
    let left = z;
    for (const name of SHARED.fillOrder) {
      if (left <= 0) break;
      const take = Math.min(left, capOf(name));
      if (take > 0) out[name] = take;
      left -= take;
    }
    return out;
  }

  function occupancy(sub) {
    return (S.boxes[sub] || []).reduce((sum, state) => sum + state, 0);
  }

  function totalPlaced() {
    return Object.keys(S.boxes).reduce((sum, sub) => sum + occupancy(sub), 0);
  }

  function firstEmptyBox(sub) {
    const list = S.boxes[sub] || [];
    const m = boxesOf(sub);
    for (let i = 0; i < m; i += 1) if (list[i] === 0) return i;
    for (let i = 0; i < m; i += 1) if (list[i] === 1) return i;
    return null;
  }

  function nextNeeded() {
    for (const sub of SHARED.fillOrder) {
      const target = want[sub] || 0;
      if (target > 0 && occupancy(sub) < target) return sub;
    }
    return null;
  }

  function nextNeededMadelung() {
    for (const sub of SHARED.fillOrder) {
      const target = madelungWant[sub] || 0;
      if (target > 0 && occupancy(sub) < target) return sub;
    }
    return null;
  }

  // ------------------------------------------------------------- validation
  function checkPlacement(sub, box, spin) {
    const msg = SHARED.messages;
    const placed = totalPlaced();
    if (placed >= DATA.z) {
      return { code: 'count_over', rule: 'COUNT', severity: 'block',
               message: msg.count_over.replace('{symbol}', DATA.symbol)
                       .replace('{z}', DATA.z).replace('{have}', placed + 1) };
    }
    if (occupancy(sub) >= capOf(sub)) {
      return { code: 'capacity', rule: 'CAPACITY', severity: 'block',
               message: msg.capacity.replace('{type}', subType(sub)).replace('{max}', capOf(sub)) };
    }
    const needed = nextNeeded();
    if (needed && sub !== needed) {
      if (DATA.isException && sub === nextNeededMadelung()) {
        return { code: 'aufbau_exception', rule: 'EXCEPTION', severity: 'gold',
                 message: msg.aufbau_exception.replace('{symbol}', DATA.symbol)
                         .replace('{actual}', DATA.fillOrder)
                         .replace('{reason}', DATA.exceptionReason),
                 correct: needed };
      }
      return { code: 'aufbau', rule: 'AUFBAU', severity: 'bounce',
               message: msg.aufbau.replace('{target}', sub).replace('{next}', needed),
               correct: needed, correctBox: firstEmptyBox(needed) };
    }
    const state = (S.boxes[sub] || [])[box];
    const m = boxesOf(sub);
    const filled = occupancy(sub);
    const empty = filled < m ? filled : null;

    if (state === 2) {
      return { code: 'pauli_third', rule: 'PAULI', severity: 'block',
               message: msg.pauli_third, correct: sub, correctBox: empty };
    }
    if (state === 1 && empty !== null) {
      return { code: 'hund', rule: 'HUND', severity: 'bounce',
               message: msg.hund.replace('{type}', subType(sub)), correct: sub, correctBox: empty };
    }
    if (state === 1 && spin === UP) {
      return { code: 'pauli_spin', rule: 'PAULI', severity: 'warn', autoSpin: DOWN,
               message: msg.pauli_spin, correct: sub, correctBox: box };
    }
    if (state === 0 && spin === DOWN) {
      return { code: 'hund_spin', rule: 'HUND', severity: 'warn', autoSpin: UP,
               message: msg.hund_spin, correct: sub, correctBox: box };
    }
    return null;
  }

  // ------------------------------------------------------------- rendering
  function buildRows() {
    const needed = DATA.sublevels.map((s) => s.name);
    const extra = SHARED.fillOrder.filter((n) => !needed.includes(n)).slice(0, 2);
    shown = needed.concat(extra);
    S.boxes = {};
    shown.concat(SHARED.fillOrder).forEach((name) => {
      if (!S.boxes[name]) S.boxes[name] = new Array(boxesOf(name)).fill(0);
    });
    ladderEl.innerHTML = '';
    shown.forEach((name) => ladderEl.appendChild(rowFor(name)));
    S.closed = new Set();
    S.swept = new Set();
  }

  function rowFor(name) {
    const isPart = (want[name] || 0) > 0;
    const row = document.createElement('div');
    row.className = 'level' + (isPart ? '' : ' is-locked') + (valSubs.has(name) ? ' is-valence' : '');
    row.dataset.sub = name;

    const label = document.createElement('div');
    label.className = 'level-name';
    label.innerHTML = '<b>' + name + '</b><span class="level-tag">n=' + shellOf(name) +
      ' · ' + boxesOf(name) + ' box' + (boxesOf(name) > 1 ? 'es' : '') +
      ' · ' + (isPart ? want[name] + ' e⁻' : 'not in ' + DATA.symbol) +
      (valSubs.has(name) ? ' · <span class="valence-flag">valence</span>' : '') + '</span>';
    row.appendChild(label);

    const wrap = document.createElement('div');
    wrap.className = 'boxes';
    for (let i = 0; i < boxesOf(name); i += 1) {
      wrap.appendChild(boxButton(name, i));
    }
    row.appendChild(wrap);
    return row;
  }

  function boxButton(name, index) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'orb';
    button.dataset.sub = name;
    button.dataset.box = String(index);
    button.setAttribute('aria-label', describeBox(name, index));
    const arrows = document.createElement('span');
    arrows.className = 'arrows';
    button.appendChild(arrows);
    return button;
  }

  function describeBox(name, index) {
    const state = (S.boxes[name] || [])[index] || 0;
    const reading = state === 2 ? 'paired, up and down' : state === 1 ? 'one electron, up' : 'empty';
    return name + ' orbital ' + (index + 1) + ' of ' + boxesOf(name) + ', ' + reading;
  }

  function paintBoxes() {
    ladderEl.querySelectorAll('.orb').forEach((button) => {
      const name = button.dataset.sub;
      const index = Number(button.dataset.box);
      const state = (S.boxes[name] || [])[index] || 0;
      button.firstChild.textContent = state === 2 ? UP + DOWN : state === 1 ? UP : '';
      button.setAttribute('aria-label', describeBox(name, index));
    });
    ladderEl.querySelectorAll('.level').forEach((row) => {
      const name = row.dataset.sub;
      const target = want[name] || 0;
      row.classList.toggle('is-closed', target > 0 && occupancy(name) === target);
      row.classList.toggle('is-active', nextNeeded() === name);
    });
  }

  function renderPool() {
    const left = DATA.z - totalPlaced();
    const placingValence = valSubs.has(nextNeeded());
    poolEl.innerHTML = '';
    const show = Math.min(left, 24);
    for (let i = 0; i < show; i += 1) {
      const token = document.createElement('button');
      token.type = 'button';
      token.className = 'token' + (S.selected && i === 0 ? ' is-selected' : '') +
        (placingValence ? ' is-valence' : '');
      token.textContent = S.spin;
      token.setAttribute('aria-label', 'electron ' + (i + 1) + ' of ' + left + ', spin ' +
        (S.spin === UP ? 'up' : 'down') + (placingValence ? ', valence electron' : ''));
      token.draggable = true;
      token.addEventListener('click', () => { S.selected = true; renderPool(); });
      token.addEventListener('dragstart', (event) => {
        S.selected = true;
        event.dataTransfer.setData('text/plain', 'electron');
        event.dataTransfer.effectAllowed = 'copy';
      });
      poolEl.appendChild(token);
    }
    if (left > show) {
      const more = document.createElement('span');
      more.className = 'level-tag';
      more.textContent = '+' + (left - show) + ' more';
      poolEl.appendChild(more);
    }
    el('remaining').textContent = String(left);
  }

  function renderNotation() {
    const groups = {};
    Object.keys(S.boxes).forEach((name) => {
      const count = occupancy(name);
      if (count > 0) groups[name] = count;
    });
    const names = SHARED.fillOrder.filter((n) => groups[n]);
    const energy = notationItems(names);
    const byShell = notationItems(names.slice().sort((a, b) =>
      (shellOf(a) - shellOf(b)) || (typeRank(a) - typeRank(b))));
    notationLine(el('notation-fill'), 'energy order:', energy, ' ');
    notationLine(el('notation-full'), '', byShell, ' ');
    el('notation-shorthand').textContent = 'target shorthand: ' + DATA.shorthand;
    notationLine(el('notation-shells'), '', shellItems(groups), ', ');
    el('remaining').textContent = String(DATA.z - totalPlaced());
  }

  function notationItems(names) {
    return names.map((name) => ({
      text: name + sup(occupancy(name)), valence: valSubs.has(name),
    }));
  }

  const SUP = '⁰¹²³⁴⁵⁶⁷⁸⁹';
  function sup(n) {
    return String(n).split('').map((d) => SUP[Number(d)]).join('');
  }
  function typeRank(name) {
    return { s: 0, p: 1, d: 2, f: 3 }[subType(name)];
  }
  function shellItems(groups) {
    const totals = {};
    Object.keys(groups).forEach((name) => {
      const n = shellOf(name);
      totals[n] = (totals[n] || 0) + groups[name];
    });
    return Object.keys(totals).sort((a, b) => a - b).map((n) =>
      ({ text: String(totals[n]), valence: valShells.has(Number(n)) }));
  }

  // Notation is built from nodes, not a string, so valence terms can be coloured.
  function notationLine(node, prefix, items, joiner) {
    node.textContent = '';
    if (prefix) node.appendChild(document.createTextNode(prefix + ' '));
    if (!items.length) {
      node.appendChild(document.createTextNode('—'));
      return;
    }
    items.forEach((item, index) => {
      if (index) node.appendChild(document.createTextNode(joiner));
      const span = document.createElement('span');
      span.textContent = item.text;
      if (item.valence) span.className = 'val';
      node.appendChild(span);
    });
  }

  function flash(message, kind, target) {
    const item = document.createElement('li');
    item.className = 'v-' + kind;
    item.textContent = message;
    feedbackEl.prepend(item);
    while (feedbackEl.children.length > 6) feedbackEl.lastChild.remove();
    if (target) {
      target.classList.remove('is-wrong', 'is-good', 'is-exception');
      void target.offsetWidth;
      target.classList.add(kind === 'bounce' || kind === 'block' ? 'is-wrong'
        : kind === 'gold' ? 'is-exception' : 'is-good');
    }
    if (kind === 'bounce' || kind === 'block') {
      boardEl.classList.remove('shaking');
      void boardEl.offsetWidth;
      boardEl.classList.add('shaking');
    }
  }

  function highlightCorrect(sub, box) {
    ladderEl.querySelectorAll('.is-target').forEach((n) => n.classList.remove('is-target'));
    if (!sub) return;
    const selector = '.orb[data-sub="' + sub + '"]' + (box === null || box === undefined ? '' : '[data-box="' + box + '"]');
    const match = ladderEl.querySelector(selector) ||
      ladderEl.querySelector('.orb[data-sub="' + sub + '"]');
    if (match) match.classList.add('is-target');
  }

  // ------------------------------------------------------------ scoring
  function scorePar() {
    const block = SHARED.scoring.blockFactor[DATA.block] || 1;
    let par = 100 * DATA.z + 1000 * block;
    DATA.sublevels.forEach((s) => {
      par += SHARED.scoring.closure[s.type];
      if (s.orbitals > 1) par += SHARED.scoring.hundSweep;
    });
    return par;
  }

  function adjustStability(delta) {
    if (S.practice) return;
    const bounds = SHARED.scoring.stability;
    S.stability = Math.max(0, Math.min(bounds.start, S.stability + delta));
    if (S.stability >= 0 && delta > 0) S.streakForRecovery += 1;
    if (delta < 0) S.streakForRecovery = 0;
    if (!S.recovered && S.stability <= 30 && S.streakForRecovery >= 4) {
      S.stability = Math.min(bounds.start, S.stability + bounds.recovery);
      S.recovered = true;
      flash('Stability cell recovered +' + bounds.recovery, 'good');
    }
    paintStability();
    if (S.stability <= 0) decay('Stability reached zero — the atom fell apart.');
  }

  function paintStability() {
    const bar = el('stability');
    bar.style.width = S.stability + '%';
    bar.setAttribute('aria-valuenow', String(Math.round(S.stability)));
    el('stability-value').textContent = String(Math.round(S.stability));
    bar.classList.toggle('is-warn', S.stability <= 69 && S.stability > 39);
    bar.classList.toggle('is-critical', S.stability <= 39);
  }

  function addScore(points) {
    if (S.practice) return;
    S.score = Math.max(0, S.score + Math.round(points));
    el('score').textContent = S.score.toLocaleString();
  }

  function bumpMultiplier(correct) {
    const limits = SHARED.scoring.multiplier;
    if (correct) {
      S.multiplier = Math.min(limits.max, S.multiplier + limits.step);
    } else {
      S.multiplier = 1;
    }
    S.maxMultiplier = Math.max(S.maxMultiplier, S.multiplier);
    el('multiplier').textContent = '×' + S.multiplier.toFixed(2);
  }

  // ------------------------------------------------------------ placement
  function attemptPlace(sub, box, sourceButton) {
    if (S.done) return;
    if (DATA.z - totalPlaced() <= 0) return;
    const violation = checkPlacement(sub, box, S.spin);
    if (violation) {
      handleViolation(violation, sub, box, sourceButton);
      return;
    }
    commit(sub, box, S.spin, sourceButton);
  }

  function handleViolation(violation, sub, box, sourceButton) {
    const penalties = SHARED.scoring.penalty;
    const stability = SHARED.scoring.stability;
    if (violation.severity === 'gold') {
      flash(violation.message, 'gold', sourceButton);
      highlightCorrect(violation.correct, violation.correctBox);
      if (violation.correct) focusRow(violation.correct);
      bumpMultiplier(false);
      return;
    }
    if (violation.severity === 'warn') {
      flash(violation.message, 'warn', sourceButton);
      S.errors[violation.rule] = (S.errors[violation.rule] || 0) + 1;
      addScore(penalties.warn);
      adjustStability(stability.warn);
      commit(sub, box, violation.autoSpin, sourceButton, true);
      return;
    }
    flash(violation.message, violation.severity === 'block' ? 'block' : 'bounce', sourceButton);
    S.errors[violation.rule] = (S.errors[violation.rule] || 0) + 1;
    addScore(violation.severity === 'block' ? penalties.block : penalties.bounce);
    adjustStability(violation.severity === 'block' ? stability.block : stability.bounce);
    bumpMultiplier(false);
    if (violation.correct) {
      highlightCorrect(violation.correct, violation.correctBox);
      focusRow(violation.correct);
    }
  }

  function focusRow(sub) {
    const row = ladderEl.querySelector('.level[data-sub="' + sub + '"]');
    if (row) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function commit(sub, box, spin, sourceButton, autocorrected) {
    S.boxes[sub][box] = spin === DOWN ? 2 : 1;
    S.order.push({ sub: sub, box: box });
    paintBoxes();
    renderPool();
    renderNotation();
    drawBohr();
    drawOrbitalCloud();
    bumpMultiplier(true);

    if (!autocorrected) {
      addScore(SHARED.scoring.place * S.multiplier);
      adjustStability(SHARED.scoring.stability.place);
      flash('Placed in ' + sub + ' box ' + (box + 1) + ' (spin ' + (spin === UP ? 'up' : 'down') + ')', 'good', sourceButton);
    }

    if (exceptionSublevels.has(sub) && occupancy(sub) === (want[sub] || 0) && !S.exceptionAwarded) {
      S.exceptionAwarded = true;
      addScore(SHARED.scoring.exceptionInsight);
      flash('Exception insight +' + SHARED.scoring.exceptionInsight + ' — ' + DATA.exceptionReason, 'gold');
    }

    const target = want[sub] || 0;
    if (target > 0 && occupancy(sub) === target && !S.closed.has(sub)) {
      S.closed.add(sub);
      const bonus = SHARED.scoring.closure[subType(sub)];
      addScore(bonus);
      flash(sub + ' closed +' + bonus, 'good');
    }
    if (boxesOf(sub) > 1 && occupancy(sub) === boxesOf(sub) && !S.swept.has(sub)) {
      S.swept.add(sub);
      addScore(SHARED.scoring.hundSweep);
      flash("Hund sweep in " + sub + ' +' + SHARED.scoring.hundSweep, 'good');
    }

    const needed = nextNeeded();
    highlightCorrect(needed, needed ? firstEmptyBox(needed) : null);

    if (totalPlaced() === DATA.z) finish();
  }

  // ------------------------------------------------------------ element flow
  function loadElement(z) {
    fetch(BASE + 'api/element/' + z)
      .then((response) => response.json())
      .then((payload) => {
        DATA = payload;
        startElement();
        history.replaceState(null, '', BASE + 'play/' + z);
      })
      .catch(() => flash('Could not load element ' + z + '.', 'block'));
  }

  function freshState(attempts) {
    const timerSeconds = Math.max(60, SHARED.scoring.timerBaseSeconds +
      SHARED.scoring.timerPerElectron * DATA.z);
    return {
      boxes: {}, order: [], score: 0, multiplier: 1, maxMultiplier: 1,
      stability: SHARED.scoring.stability.start, recovered: false, streakForRecovery: 0,
      errors: {}, hints: 0, spin: UP, selected: false,
      practice: el('practice').checked, secondsLeft: timerSeconds, done: false,
      attempts: attempts, closed: new Set(), swept: new Set(), exceptionAwarded: false,
      lock: SHARED.scoring.lockBase * (SHARED.scoring.blockFactor[DATA.block] || 1),
    };
  }

  function startElement(keepAttempts) {
    want = {};
    DATA.sublevels.forEach((s) => { want[s.name] = s.count; });
    madelungWant = madelungTargets(DATA.z);
    valSubs = new Set(DATA.valenceSublevels || []);
    valShells = new Set([...valSubs].map(shellOf));
    exceptionSublevels = new Set(SHARED.fillOrder.filter(
      (name) => (madelungWant[name] || 0) !== (want[name] || 0)));

    S = freshState(keepAttempts && S ? S.attempts : 0);
    HOVER = null;
    if (CLOUD_NOTE_DEFAULT) el('cloud-note').textContent = CLOUD_NOTE_DEFAULT;

    el('hud-symbol').textContent = DATA.symbol;
    el('hud-name').textContent = DATA.name;
    el('hud-z').textContent = String(DATA.z);
    el('hud-block').textContent = DATA.block;
    el('hud-period').textContent = String(DATA.period);
    if (el('hud-group')) el('hud-group').textContent = DATA.group === null ? 'f-block' : String(DATA.group);
    el('z-input').value = String(DATA.z);
    el('score').textContent = '0';
    el('multiplier').textContent = '×1.00';
    document.querySelectorAll('.pt-cell').forEach((cell) =>
      cell.classList.toggle('is-current', Number(cell.dataset.z) === DATA.z));
    feedbackEl.innerHTML = '';
    el('result').hidden = true;
    el('spin-label').textContent = S.spin;

    buildRows();
    renderPool();
    renderNotation();
    paintBoxes();
    paintStability();
    drawBohr();
    drawOrbitalCloud();
    startTimer();

    const opening = DATA.isException
      ? DATA.name + ' (Z=' + DATA.z + ') is a stability exception. Aufbau alone predicts ' + DATA.expected + '.'
      : DATA.name + ' — ' + DATA.z + ' electrons. The ladder starts at 1s on top: fill downward, lowest energy first.';
    flash(opening, 'good');
    const needed = nextNeeded();
    highlightCorrect(needed, needed ? firstEmptyBox(needed) : null);
  }

  function startTimer() {
    clearInterval(ticking);
    paintTimer();
    if (S.practice) return;
    ticking = setInterval(() => {
      if (S.done) return;
      S.secondsLeft -= 1;
      paintTimer();
      if (S.secondsLeft % 8 === 0) adjustStability(SHARED.scoring.stability.bounce / 4);
      if (S.secondsLeft <= 0) {
        clearInterval(ticking);
        decay('Time ran out with ' + (DATA.z - totalPlaced()) + ' electrons still unplaced.');
      }
    }, 1000);
  }

  function paintTimer() {
    const minutes = Math.floor(S.secondsLeft / 60);
    const seconds = S.secondsLeft % 60;
    el('timer').textContent = minutes + ':' + String(seconds).padStart(2, '0');
  }

  function decay(reason) {
    if (S.done) return;
    const seconds = Math.max(30, S.secondsLeft);
    S.attempts += 1;
    const attempt = S.attempts;
    startElement(true);
    S.secondsLeft = seconds;
    paintTimer();
    flash(reason + ' Board reset — attempt ' + (attempt + 1) + '.', 'block');
  }

  function finish() {
    S.done = true;
    clearInterval(ticking);
    const perfect = Object.keys(S.errors).length === 0;
    const timeBonus = S.practice ? 0 : Math.min(Math.round(scorePar() * 0.5), S.secondsLeft * 2);
    let total = S.score + Math.round(S.lock) + timeBonus;
    if (perfect) total = Math.round(total * SHARED.scoring.perfectMultiplier);
    S.score = total;
    el('score').textContent = total.toLocaleString();
    showResult(perfect, timeBonus);
  }

  function showResult(perfect, timeBonus) {
    const par = scorePar();
    const ratio = Math.max(0, S.score / par);
    const stars = ratio >= SHARED.scoring.starThresholds[2] && errorCount() <= 1 ? 3
      : ratio >= SHARED.scoring.starThresholds[1] && errorCount() <= 3 ? 2
      : ratio >= SHARED.scoring.starThresholds[0] ? 1 : 0;
    const errorTotal = errorCount();

    el('result-title').textContent = DATA.name + ' is stable' + (perfect ? ' — flawless build' : '');
    el('result-stars').textContent = '★'.repeat(stars) + '☆'.repeat(3 - stars);
    el('r-full').textContent = DATA.full;
    el('r-fill').textContent = DATA.fillOrder;
    el('r-shorthand').textContent = DATA.shorthand;
    el('r-shells').textContent = DATA.shells;
    el('r-valence').textContent = DATA.valenceSublevels.join('  ') +
      '  ·  ' + DATA.valenceCount + ' valence electrons';
    el('r-score').textContent = S.score.toLocaleString() + (perfect ? ' (×1.5 flawless)' : '') +
      ' · stability bonus ' + timeBonus;
    el('r-par').textContent = Math.round(ratio * 100) + '% of par ' + par.toLocaleString() +
      ' · rule breaks ' + errorTotal + (S.attempts ? ' · resets ' + S.attempts : '');
    el('r-mult').textContent = '×' + S.maxMultiplier.toFixed(2);
    el('r-time').textContent = S.practice ? 'practice mode, no timer' : S.secondsLeft + ' s left';

    const body = el('r-report');
    body.innerHTML = '';
    const coaching = {
      AUFBAU: 'Read the ladder from the top: the first empty slot is always the legal one.',
      PAULI: 'One orbital holds two, and only as a matched pair.',
      HUND: 'Fill every box in a sublevel with one electron before pairing any of them, and draw every lone electron ↑.',
      COUNT: 'The electron count must equal the atomic number for a neutral atom.',
      CAPACITY: 'Check the sublevel capacity: s 2, p 6, d 10, f 14.',
    };
    ['AUFBAU', 'PAULI', 'HUND', 'CAPACITY', 'COUNT'].forEach((rule) => {
      const count = S.errors[rule] || 0;
      const row = document.createElement('tr');
      row.innerHTML = '<td>' + rule + '</td><td>' + count + '</td><td>' +
        (count ? coaching[rule] : 'clean') + '</td>';
      body.appendChild(row);
    });

    el('r-note').textContent = DATA.isException
      ? DATA.name + ' breaks the expected order: ' + DATA.exceptionReason
      : 'Shorthand for the note book: ' + DATA.shorthand + '. Notation order here groups by shell (n).';
    el('result').hidden = false;
    el('r-next').focus();
  }

  function errorCount() {
    return Object.keys(S.errors).reduce((sum, rule) => sum + (S.errors[rule] || 0), 0);
  }

  // ------------------------------------------------------------ Bohr model
  const SHELL_LETTERS = ['K', 'L', 'M', 'N', 'O', 'P', 'Q'];

  function drawBohr() {
    const canvas = el('bohr');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const groups = {};
    Object.keys(S.boxes).forEach((name) => {
      const count = occupancy(name);
      if (count > 0) groups[shellOf(name)] = (groups[shellOf(name)] || 0) + count;
    });
    const shells = Object.keys(groups).map(Number).sort((a, b) => a - b);
    const maxR = Math.min(width, height) / 2 - 10;
    const cx = width / 2;
    const cy = height / 2;

    ctx.strokeStyle = '#1e2b4d';
    ctx.beginPath();
    ctx.arc(cx, cy, 7, 0, Math.PI * 2);
    ctx.fillStyle = '#e879f9';
    ctx.fill();
    ctx.fillStyle = '#7d8db5';
    ctx.font = '10px Consolas, monospace';
    ctx.fillText(DATA.symbol, cx + 10, cy - 8);

    shells.forEach((n, index) => {
      const radius = maxR * ((index + 1) / Math.max(1, shells.length));
      const isValence = valShells.has(n);
      ctx.beginPath();
      ctx.strokeStyle = isValence ? 'rgba(255, 92, 92, .55)' : 'rgba(120, 160, 220, .35)';
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.stroke();
      const count = groups[n];
      for (let i = 0; i < count; i += 1) {
        const angle = (Math.PI * 2 * i) / count - Math.PI / 2;
        const x = cx + radius * Math.cos(angle);
        const y = cy + radius * Math.sin(angle);
        ctx.beginPath();
        ctx.fillStyle = isValence ? 'rgba(255, 92, 92, .9)' : 'rgba(34, 211, 238, .85)';
        ctx.arc(x, y, 3.2, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = isValence ? '#ff5c5c' : '#7d8db5';
      ctx.font = '9px Consolas, monospace';
      const letter = SHELL_LETTERS[n - 1] || ('n=' + n);
      ctx.fillText(letter + ' · ' + count + (isValence ? ' valence' : ''),
                   cx - 22, cy - radius - 3);
    });
  }

  // ------------------------------------------------------------ real cloud model
  // Each occupied orbital is drawn as the shape of its sublevel (s sphere,
  // p dumbbell, d cloverleaf, f multi-lobed) and turned to the axis its mℓ
  // selects. For Z 1-20 only s and p appear, which is the point of the view.
  const TYPE_L = { s: 0, p: 1, d: 2, f: 3 };
  const TYPE_COLOR = { s: '34,211,238', p: '56,189,248', d: '167,139,250', f: '251,191,36' };
  let HOVER = null;
  let CLOUD_NOTE_DEFAULT = '';

  function drawOrbitalCloud() {
    const canvas = el('cloud');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    const cx = width / 2;
    const cy = height / 2 + 4;

    const occupied = [];
    Object.keys(S.boxes).forEach((name) => {
      const type = subType(name);
      const l = TYPE_L[type];
      const n = shellOf(name);
      S.boxes[name].forEach((state, index) => {
        if (!state) return;
        occupied.push({ name: name, type: type, n: n, box: index, ml: -l + index,
                        paired: state === 2, valence: valSubs.has(name) });
      });
    });

    if (!occupied.length) {
      ctx.fillStyle = '#7d8db5';
      ctx.font = '11px Consolas, monospace';
      ctx.textAlign = 'center';
      ctx.fillText('Place an electron to grow its cloud', cx, cy);
      ctx.textAlign = 'start';
      return;
    }

    // Outer shells first, then the compact inner ones; within one shell the
    // spherical s cloud sits behind its p lobes.
    occupied.sort((a, b) => (b.n - a.n) || (typeRank(a.type) - typeRank(b.type)) ||
      (a.box - b.box));
    occupied.forEach((orbital) => drawOrbital(ctx, orbital, cx, cy));

    ctx.beginPath();
    ctx.fillStyle = '#e879f9';
    ctx.arc(cx, cy, 4.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#dbe6ff';
    ctx.font = '700 10px Consolas, monospace';
    ctx.fillText(DATA.symbol, cx + 8, cy - 6);

    ctx.fillStyle = '#5b6b93';
    ctx.font = '9px Consolas, monospace';
    ctx.fillText('bright = paired  ·  red = valence', 10, height - 10);
  }

  function drawOrbital(ctx, orbital, cx, cy) {
    const color = orbital.valence ? '255,92,92' : TYPE_COLOR[orbital.type];
    const hot = HOVER && HOVER.sub === orbital.name && HOVER.box === orbital.box;
    const base = 26 + 24 * (orbital.n - 1);
    ctx.save();
    ctx.lineJoin = 'round';
    if (hot) {
      ctx.shadowColor = 'rgba(' + color + ',.95)';
      ctx.shadowBlur = 16;
    }
    if (orbital.type === 's') {
      drawSphere(ctx, cx, cy, base * 0.92, color, orbital.paired, hot);
    } else if (orbital.type === 'p') {
      if (orbital.ml > 0) ctx.setLineDash([5, 3]);
      drawDumbbell(ctx, cx, cy, pAngle(orbital.ml), base * 0.95, base * 0.30,
                   color, orbital.paired, hot);
    } else if (orbital.type === 'd') {
      if (orbital.ml > 0) ctx.setLineDash([5, 3]);
      drawD(ctx, cx, cy, orbital.ml, base, color, orbital.paired, hot);
    } else {
      if (orbital.ml > 0) ctx.setLineDash([4, 3]);
      drawF(ctx, cx, cy, orbital.ml, base, color, orbital.paired, hot);
    }
    ctx.restore();
  }

  function pAngle(ml) {
    if (ml === -1) return 0;                 // across the page
    if (ml === 0) return -Math.PI / 2;       // upright
    return -Math.PI / 4;                     // diagonal, into the page
  }

  function drawSphere(ctx, cx, cy, r, color, paired, hot) {
    const grad = ctx.createRadialGradient(cx, cy, r * 0.05, cx, cy, r);
    grad.addColorStop(0, 'rgba(' + color + ',' + (paired ? 0.55 : 0.32) + ')');
    grad.addColorStop(0.55, 'rgba(' + color + ',' + (paired ? 0.20 : 0.12) + ')');
    grad.addColorStop(1, 'rgba(' + color + ',0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = 'rgba(' + color + ',' + (paired ? 0.92 : 0.62) + ')';
    ctx.lineWidth = hot ? 2.4 : 1.1;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();
  }

  function drawDumbbell(ctx, cx, cy, angle, length, width, color, paired, hot) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    ctx.fillStyle = 'rgba(' + color + ',' + (paired ? 0.26 : 0.15) + ')';
    ctx.strokeStyle = 'rgba(' + color + ',' + (paired ? 0.92 : 0.66) + ')';
    ctx.lineWidth = hot ? 2.2 : 1.1;
    [1, -1].forEach((side) => {
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.bezierCurveTo(side * length * 0.16, -width, side * length * 0.72, -width,
                        side * length, 0);
      ctx.bezierCurveTo(side * length * 0.72, width, side * length * 0.16, width, 0, 0);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    });
    ctx.restore();
  }

  function drawD(ctx, cx, cy, ml, base, color, paired, hot) {
    const length = base * 0.62;
    const width = base * 0.20;
    if (ml === 0) {
      drawDumbbell(ctx, cx, cy, 0, length * 1.12, width, color, paired, hot);
      ctx.strokeStyle = 'rgba(' + color + ',' + (paired ? 0.8 : 0.55) + ')';
      ctx.fillStyle = 'rgba(' + color + ',' + (paired ? 0.16 : 0.09) + ')';
      ctx.lineWidth = hot ? 2 : 1;
      ctx.beginPath();
      ctx.ellipse(cx, cy, length * 0.52, length * 0.22, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      return;
    }
    const diagonal = Math.abs(ml) === 1;
    const angles = diagonal ? [Math.PI / 4, -Math.PI / 4] : [0, Math.PI / 2];
    angles.forEach((angle) => drawDumbbell(ctx, cx, cy, angle, length, width,
                                           color, paired, hot));
  }

  function drawF(ctx, cx, cy, ml, base, color, paired, hot) {
    const length = base * 0.55;
    const width = base * 0.15;
    const offset = ((ml + 3) * Math.PI) / 24;
    for (let i = 0; i < 4; i += 1) {
      drawDumbbell(ctx, cx, cy, offset + (i * Math.PI) / 4, length, width,
                   color, paired, hot);
    }
  }

  // ------------------------------------------------------------ interaction
  function bind() {
    ladderEl.addEventListener('click', (event) => {
      const button = event.target.closest('.orb');
      if (button) { S.selected = false; attemptPlace(button.dataset.sub, Number(button.dataset.box), button); }
    });
    ladderEl.addEventListener('mouseover', (event) => {
      const button = event.target.closest('.orb');
      if (!button) return;
      const sub = button.dataset.sub;
      const box = Number(button.dataset.box);
      HOVER = { sub: sub, box: box };
      el('cloud-note').textContent = describeOrbital(sub, box);
      drawOrbitalCloud();
    });
    ladderEl.addEventListener('mouseleave', () => {
      if (!HOVER) return;
      HOVER = null;
      el('cloud-note').textContent = CLOUD_NOTE_DEFAULT;
      drawOrbitalCloud();
    });
    ladderEl.addEventListener('dragover', (event) => {
      if (event.target.closest('.orb')) { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; }
    });
    ladderEl.addEventListener('drop', (event) => {
      const button = event.target.closest('.orb');
      if (!button) return;
      event.preventDefault();
      S.selected = false;
      attemptPlace(button.dataset.sub, Number(button.dataset.box), button);
      renderPool();
    });

    el('z-input').addEventListener('change', () => loadElement(Number(el('z-input').value || 1)));
    el('z-prev').addEventListener('click', () => loadElement(Math.max(1, DATA.z - 1)));
    el('z-next').addEventListener('click', () => loadElement(Math.min(118, DATA.z + 1)));
    el('z-random').addEventListener('click', () => loadElement(1 + Math.floor(Math.random() * 56)));
    el('z-reset').addEventListener('click', () => startElement());
    el('practice').addEventListener('change', () => startElement());
    el('spin-toggle').addEventListener('click', flipSpin);
    el('r-close').addEventListener('click', () => { el('result').hidden = true; });
    el('r-retry').addEventListener('click', () => startElement());
    el('r-next').addEventListener('click', () => loadElement(Math.min(118, DATA.z + 1)));

    document.querySelectorAll('.pt-cell').forEach((cell) =>
      cell.addEventListener('click', () => loadElement(Number(cell.dataset.z))));

    document.addEventListener('keydown', (event) => {
      if (event.target.matches('input, textarea, select')) return;
      const key = event.key.toLowerCase();
      if (key === 's') { event.preventDefault(); flipSpin(); }
      else if (key === 'u') { event.preventDefault(); undo(); }
      else if (key === 'r') { event.preventDefault(); startElement(); }
      else if (key === 'h') { event.preventDefault(); hint(); }
      else if (key === 'escape') { el('result').hidden = true; }
      else if (/^[1-7]$/.test(key)) {
        event.preventDefault();
        jumpToShell(Number(key));
      }
    });
  }

  function shapeFor(type) {
    return { s: 'spherical', p: 'dumbbell (two lobes)', d: 'four-lobed / dz²', f: 'multi-lobed' }[type];
  }

  const P_AXIS = { '-1': 'across the page', '0': 'upright', '1': 'diagonal, into the page' };

  function describeOrbital(sub, box) {
    const type = subType(sub);
    const ml = -TYPE_L[type] + box;
    const axis = type === 'p' ? ' · ' + P_AXIS[String(ml)] : '';
    return sub + ' · mℓ = ' + String(ml).replace('-', '−') + ' · ' + shapeFor(type) + axis;
  }

  function flipSpin() {
    S.spin = S.spin === UP ? DOWN : UP;
    el('spin-label').textContent = S.spin;
    renderPool();
    flash('Spin set to ' + (S.spin === UP ? 'up' : 'down') +
      '. A lone electron is always drawn ↑; ↓ only goes in to pair an orbital that already holds one.', 'warn');
  }

  function undo() {
    const last = S.order.pop();
    if (!last) return;
    S.boxes[last.sub][last.box] = 0;
    if (!S.practice) addScore(SHARED.scoring.penalty.undo);
    S.closed.delete(last.sub);
    S.swept.delete(last.sub);
    if (totalPlaced() === DATA.z - 1) S.done = false;
    paintBoxes();
    renderPool();
    renderNotation();
    drawBohr();
    drawOrbitalCloud();
    flash('Removed the electron from ' + last.sub + ' box ' + (last.box + 1) + '.', 'warn');
  }

  function hint() {
    const needed = nextNeeded();
    if (!needed) return;
    if (!S.practice) addScore(SHARED.scoring.penalty.hint);
    S.hints += 1;
    highlightCorrect(needed, firstEmptyBox(needed));
    focusRow(needed);
    flash('Next legal slot: ' + needed + ', box ' + (firstEmptyBox(needed) + 1) +
      (S.practice ? '' : ' (a hint costs ' + Math.abs(SHARED.scoring.penalty.hint) + ' points).'), 'good');
  }

  function jumpToShell(n) {
    const match = SHARED.fillOrder.find((name) => shellOf(name) === n && (want[name] || 0) > 0 && occupancy(name) < want[name])
      || SHARED.fillOrder.find((name) => shellOf(name) === n && (want[name] || 0) > 0);
    if (!match) return;
    const button = ladderEl.querySelector('.orb[data-sub="' + match + '"]');
    if (button) { button.focus(); focusRow(match); }
  }

  // ------------------------------------------------------------ boot
  function boot() {
    fetch(BASE + 'api/engine')
      .then((response) => response.json())
      .then((shared) => {
        SHARED = shared;
        SHARED.scoring.starThresholds = SHARED.scoring.starThresholds || [0.55, 0.75, 0.9];
        DATA = JSON.parse(el('element-data').textContent);
        CLOUD_NOTE_DEFAULT = el('cloud-note').textContent;
        bind();
        startElement();
      })
      .catch(() => {
        feedbackEl.innerHTML = '<li class="v-block">The rule table failed to load. Reload the page.</li>';
      });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
