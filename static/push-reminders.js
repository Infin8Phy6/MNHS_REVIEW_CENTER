// Class reminders: a one-time card asks this device to accept class
// notifications. The answer ("turned on" or "not now") is saved by the server
// in reminder_choice.json, per account, so no page asks again - the choice
// stays as saved until the person changes it on the Profile page.
(function () {
    var card = document.querySelector('[data-reminder-card]');

    if (!window.RH_LOGGED_IN ||
        !('serviceWorker' in navigator) ||
        !('PushManager' in window) ||
        !('Notification' in window)) {
        if (card) {
            card.querySelector('[data-reminder-status]').textContent =
                'Not available on this browser';
            card.querySelector('[data-reminder-note]').textContent =
                'This browser cannot show class reminders. Try Chrome, Edge or Firefox on this device.';
            var unavailable = card.querySelector('[data-reminder-toggle]');
            unavailable.textContent = 'Not available';
            unavailable.disabled = true;
        }
        return;
    }

    var BELL = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">' +
        '<path fill="currentColor" d="M12 22a2.5 2.5 0 0 0 2.45-2h-4.9A2.5 2.5 0 0 0 12 22Zm7-5.5-1.3-1.9V9a5.7 5.7 0 0 0-4.4-5.6V2.8a1.3 1.3 0 0 0-2.6 0v.6A5.7 5.7 0 0 0 6.3 9v5.6L5 16.5a1 1 0 0 0 .8 1.6h12.4a1 1 0 0 0 .8-1.6Z"/></svg>';

    function urlBase64ToUint8Array(base64) {
        var padding = '='.repeat((4 - base64.length % 4) % 4);
        var b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
        var raw = atob(b64);
        var out = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
        return out;
    }

    function b64(buffer) {
        var bytes = new Uint8Array(buffer), str = '';
        for (var i = 0; i < bytes.length; i++) str += String.fromCharCode(bytes[i]);
        return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    }

    function subscriptionBody(sub) {
        var p256dh = sub.getKey('p256dh');
        var auth = sub.getKey('auth');
        return {
            endpoint: sub.endpoint,
            keys: { p256dh: p256dh ? b64(p256dh) : '', auth: auth ? b64(auth) : '' }
        };
    }

    function post(path, body) {
        return fetch(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(function (response) { return response.ok; })
          .catch(function () { return false; });
    }

    function saveChoice(choice) {
        return post('/push/choice', { choice: choice });
    }

    function readChoice() {
        return fetch('/push/choice', { headers: { 'Accept': 'application/json' } })
            .then(function (response) {
                return response.ok ? response.json() : null;
            })
            .then(function (data) { return data && data.choice; })
            .catch(function () { return null; });
    }

    // Returns 'on', 'blocked' (the browser said no) or 'failed' (anything else).
    function turnOn(registration) {
        return Notification.requestPermission().then(function (permission) {
            if (permission !== 'granted') return 'blocked';
            return fetch('/push/vapid')
                .then(function (response) {
                    if (!response.ok) throw new Error('no key');
                    return response.json();
                })
                .then(function (info) {
                    return registration.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: urlBase64ToUint8Array(info.publicKey)
                    });
                })
                .then(function (sub) {
                    return post('/push/subscribe', subscriptionBody(sub));
                })
                .then(function (saved) { return saved ? 'on' : 'failed'; });
        }).catch(function () { return 'failed'; });
    }

    function reminderBar(registration) {
        var el = document.getElementById('rh-push-bar');
        if (el) return el;
        el = document.createElement('section');
        el.id = 'rh-push-bar';
        el.setAttribute('role', 'dialog');
        el.setAttribute('aria-labelledby', 'rh-push-title');
        el.innerHTML =
            '<div class="rh-push-head">' +
                '<span class="rh-push-bell">' + BELL + '</span>' +
                '<div class="rh-push-copy">' +
                    '<p class="rh-push-title" id="rh-push-title">Class reminders</p>' +
                    '<p class="rh-push-text">Turn them on and this device tells you when a class starts.</p>' +
                '</div>' +
                '<button type="button" class="rh-push-close" aria-label="Not now">&times;</button>' +
            '</div>' +
            '<div class="rh-push-actions">' +
                '<button type="button" class="rh-push-notnow">Not now</button>' +
                '<button type="button" class="rh-push-enable">Turn on</button>' +
            '</div>';
        document.body.appendChild(el);

        var closeBtn = el.querySelector('.rh-push-close');
        var notNow = el.querySelector('.rh-push-notnow');
        var enable = el.querySelector('.rh-push-enable');

        function hide() {
            el.classList.add('rh-push-gone');
            window.setTimeout(function () { el.remove(); }, 160);
        }

        function notNowClicked() {
            saveChoice('dismissed');
            hide();
        }

        closeBtn.addEventListener('click', notNowClicked);
        notNow.addEventListener('click', notNowClicked);

        enable.addEventListener('click', function () {
            enable.disabled = true;
            notNow.disabled = true;
            enable.textContent = 'Turning on...';
            turnOn(registration).then(function (result) {
                if (result === 'on') {
                    saveChoice('enabled');
                    hide();
                    return;
                }
                if (result === 'blocked') {
                    // The browser is blocking this site; keep the saved answer
                    // so another device can still be asked.
                    hide();
                    return;
                }
                enable.disabled = false;
                notNow.disabled = false;
                enable.textContent = 'Try again';
            });
        });
        return el;
    }

    function wireProfileCard(card, registration) {
        var status = card.querySelector('[data-reminder-status]');
        var note = card.querySelector('[data-reminder-note]');
        var toggle = card.querySelector('[data-reminder-toggle]');

        function paint(subscribed, choice) {
            card.classList.toggle('is-on', !!subscribed);
            toggle.disabled = false;
            if (subscribed) {
                status.textContent = 'On for this device';
                toggle.textContent = 'Turn off on this device';
                note.textContent = 'Class-start alerts arrive on this device. Turn them off any time.';
                return;
            }
            status.textContent = 'Off for this device';
            toggle.textContent = 'Turn on this device';
            if (Notification.permission === 'denied') {
                note.textContent = 'Your browser is blocking notifications for this site. ' +
                    'Allow them in the browser settings, then try again.';
            } else if (choice === 'dismissed') {
                note.textContent = 'You chose not now. The one-time bar will not come back; ' +
                    'turn reminders on here whenever you want.';
            } else {
                note.textContent = 'The one-time bar is already saved for your account. ' +
                    'This switch is the place to change it.';
            }
        }

        function refresh() {
            Promise.all([
                registration.pushManager.getSubscription(),
                readChoice()
            ]).then(function (values) {
                paint(values[0], values[1]);
            }).catch(function () {
                status.textContent = 'Could not check this device';
                toggle.disabled = true;
            });
        }

        toggle.addEventListener('click', function () {
            toggle.disabled = true;
            registration.pushManager.getSubscription().then(function (sub) {
                if (sub) {
                    return sub.unsubscribe().then(function () {
                        return post('/push/unsubscribe', { endpoint: sub.endpoint });
                    }).then(function () {
                        return saveChoice('dismissed');
                    }).then(refresh);
                }
                return turnOn(registration).then(function (result) {
                    if (result === 'on') {
                        return saveChoice('enabled').then(refresh);
                    }
                    paint(null, result === 'blocked' ? 'dismissed' : null);
                    if (result === 'failed') {
                        note.textContent = 'Could not turn reminders on. Try again in a moment.';
                    }
                });
            }).catch(function () {
                toggle.disabled = false;
                note.textContent = 'Could not check this device. Try again in a moment.';
            });
        });

        refresh();
    }

    navigator.serviceWorker.ready.then(function (registration) {
        if (card) wireProfileCard(card, registration);

        registration.pushManager.getSubscription().then(function (existing) {
            if (existing) {
                // Keep the server's copy fresh - the person may have signed in
                // as somebody else since this device subscribed.
                post('/push/subscribe', subscriptionBody(existing));
                var old = document.getElementById('rh-push-bar');
                if (old) old.remove();
                return;
            }
            if (Notification.permission === 'denied') return;
            readChoice().then(function (choice) {
                if (choice !== 'ask') return;
                reminderBar(registration);
                // "shown" is written after the first answer wins, so a click
                // during this moment is never replaced by "shown".
                saveChoice('shown');
            });
        });
    }).catch(function () {
        /* push not available on this browser */
        if (card) {
            card.querySelector('[data-reminder-status]').textContent =
                'Reminders are not ready on this device';
            card.querySelector('[data-reminder-note]').textContent =
                'The offline worker could not start. Reload the page and try again.';
            var stuck = card.querySelector('[data-reminder-toggle]');
            stuck.textContent = 'Try again later';
            stuck.disabled = true;
        }
    });
})();
