"""Run the Review Center for the review-center WiFi.

Start this with start_local.bat. Students join the modem's WiFi and open
http://<this laptop's address>:5000. Nothing here contacts PythonAnywhere:
the Sync button on /admin/sync is what sends results to the live server.
"""
import os

os.environ.setdefault('MNHS_LOCAL', '1')  # no reminder loop from a laptop copy

from app import app  # noqa: E402  (needs the flag above)

HOST = '0.0.0.0'
PORT = int(os.environ.get('MNHS_PORT') or 5000)


def main():
    try:
        from waitress import serve
    except ImportError:
        print('waitress is not installed; using the Flask server instead.')
        print('For a smoother run:  venv\\Scripts\\pip install waitress')
        app.run(host=HOST, port=PORT, threaded=True)
    else:
        print('Listening on all network cards; students use http://<laptop-ip>:%s' % PORT)
        serve(app, host=HOST, port=PORT, threads=16)


if __name__ == '__main__':
    main()
