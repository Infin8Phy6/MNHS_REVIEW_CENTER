"""Run ONCE on this computer to let the app email a reset code.

1. Make a Gmail App Password: https://myaccount.google.com/apppasswords
   (needs 2-Step Verification turned on; it is NOT your normal Gmail password)
2. python mail_authorize.py   -> it asks for that App Password.
3. It saves it to  ~/.mnhs/mail.json  - outside this project folder, so the
   password is never copied, zipped or pushed with the app.

To change it later, run this again. To stop the app sending mail, delete that file.
"""
import getpass
import json
import os
import ssl
import smtplib
import sys

SERVER = 'smtp.gmail.com'
PORT = 587


def destination():
    return os.path.expanduser(
        os.environ.get('MNHS_MAIL_CREDENTIALS')
        or os.path.join(os.path.expanduser('~'), '.mnhs', 'mail.json'))


def main():
    username = input('Mailbox address [%s]: ' % 'angelesedgardo17@gmail.com').strip() \
        or 'angelesedgardo17@gmail.com'
    password = getpass.getpass('Gmail App Password (hidden as you type): ').strip()
    if not password:
        print('No App Password given, so nothing was saved.')
        return 1

    print('Testing %s over port %d...' % (SERVER, PORT))
    try:
        with smtplib.SMTP(SERVER, PORT, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(username, password.replace(' ', ''))
    except Exception as exc:
        print('Gmail refused that App Password: %s' % exc)
        print('Make sure it is an App Password from myaccount.google.com/apppasswords,')
        print('not your ordinary Gmail password.')
        return 1

    path = destination()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'mail_username': username,
                   'mail_password': password,
                   'mail_server': SERVER,
                   'mail_port': str(PORT)}, f, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # Windows keeps its own rules for files in the user profile
    print('Saved. The app can now send a reset code from %s.' % username)
    print('Credentials are in %s - keep that outside any copy of the app.' % path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
