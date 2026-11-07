"""Sends the password-reset code by email using only the standard library.

The mailbox password is never kept inside this project. It is read from
MNHS_MAIL_PASSWORD, or from the file named by MNHS_MAIL_CREDENTIALS
(~/.mnhs/mail.json by default), which sits outside the folder that gets copied,
zipped or pushed. Everything else has school defaults so the app works with
nothing set up at all, apart from the password.
"""
import json
import os
import smtplib
import ssl
from email.message import EmailMessage

_last_error = ""

DEFAULTS = {
    'MAIL_SERVER': 'smtp.gmail.com',
    'MAIL_PORT': '587',
    'MAIL_USE_TLS': 'True',
    'MAIL_USERNAME': 'angelesedgardo17@gmail.com',
    'MAIL_DEFAULT_SENDER': '',
}


def credentials_path():
    return os.path.expanduser(
        os.environ.get('MNHS_MAIL_CREDENTIALS')
        or os.path.join(os.path.expanduser('~'), '.mnhs', 'mail.json'))


def _from_file():
    path = credentials_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _pick(key, file_keys):
    """Environment first, then the credential file, then the school default."""
    for name in [key] + list(file_keys):
        value = os.environ.get('MNHS_' + name)
        if value:
            return value
    file_raw = _from_file()
    for name in file_keys:
        if file_raw.get(name):
            return file_raw[name]
    return DEFAULTS.get(key, '')


def settings():
    user = str(_pick('MAIL_USERNAME', ['mail_username', 'username']))
    # Gmail shows an App Password in four groups of four. The spaces are only
    # for reading, so login has to be tried without them.
    password = str(_pick('MAIL_PASSWORD', ['mail_password', 'password'])).replace(' ', '')
    sender = str(_pick('MAIL_DEFAULT_SENDER', ['mail_sender', 'sender'])) or user
    port = str(_pick('MAIL_PORT', ['mail_port', 'port']) or '587')
    try:
        port = int(port)
    except ValueError:
        port = 587
    use_tls = str(_pick('MAIL_USE_TLS', ['mail_tls', 'tls'])).strip().lower() not in ('0', 'false', 'no')
    return {
        'server': str(_pick('MAIL_SERVER', ['mail_server', 'server']) or 'smtp.gmail.com'),
        'port': port,
        'tls': use_tls,
        'username': user,
        'password': password,
        'sender': sender,
    }


def configured():
    s = settings()
    return bool(s['username'] and s['password'])


def error():
    return _last_error


def send(to, subject, body):
    """Hand one message to Gmail. Returns True, or False with error() set."""
    global _last_error
    s = settings()
    if not (s['username'] and s['password']):
        _last_error = ('Email is not set up on this computer. Put the mailbox password in '
                       '%s ({"mail_password": "..."}) or set MNHS_MAIL_PASSWORD.'
                       % credentials_path())
        return False

    msg = EmailMessage()
    msg['From'] = s['sender']
    msg['To'] = to
    msg['Subject'] = subject
    msg.set_content(body)

    try:
        if s['tls']:
            with smtplib.SMTP(s['server'], s['port'], timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                smtp.login(s['username'], s['password'])
                smtp.sendmail(s['sender'], [to], msg.as_string())
        else:
            with smtplib.SMTP_SSL(s['server'], s['port'], timeout=20) as smtp:
                smtp.login(s['username'], s['password'])
                smtp.sendmail(s['sender'], [to], msg.as_string())
    except Exception as exc:
        _last_error = 'The mail could not be sent: %s' % exc
        return False

    _last_error = ''
    return True
