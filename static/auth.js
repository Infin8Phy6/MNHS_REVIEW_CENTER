// Adds a small eye icon inside every password box so people can check what
// they typed without a big worded button crowding the field. Works on any
// page that loads this script - no markup changes needed inside the forms.
(function () {
    var EYE = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" ' +
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
        'aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>' +
        '<circle cx="12" cy="12" r="3"/></svg>';
    var EYE_OFF = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" ' +
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
        'aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8' +
        'a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8' +
        'a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>' +
        '<line x1="1" y1="1" x2="23" y2="23"/></svg>';

    function enhance(input) {
        if (input.dataset.pwToggle) return;
        input.dataset.pwToggle = '1';

        var wrap = document.createElement('span');
        wrap.className = 'pw-wrap';
        input.parentNode.insertBefore(wrap, input);
        wrap.appendChild(input);

        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'pw-toggle';
        button.innerHTML = EYE;
        button.setAttribute('aria-label', 'Show password');
        button.addEventListener('click', function () {
            var showing = input.type === 'password';
            input.type = showing ? 'text' : 'password';
            button.innerHTML = showing ? EYE_OFF : EYE;
            button.setAttribute('aria-label', showing ? 'Hide password' : 'Show password');
            input.focus();
        });
        wrap.appendChild(button);

        // Put the mask back when the form goes out, so saved logins and
        // password managers still treat the box as a password field.
        if (input.form) {
            input.form.addEventListener('submit', function () {
                if (input.type === 'text') {
                    input.type = 'password';
                    button.innerHTML = EYE;
                    button.setAttribute('aria-label', 'Show password');
                }
            });
        }
    }

    function apply() {
        document.querySelectorAll('input[type="password"]').forEach(enhance);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', apply);
    } else {
        apply();
    }
})();
