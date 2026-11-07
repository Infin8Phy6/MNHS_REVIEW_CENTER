"""Put the rows from the last committed quiz_app.db back into the live one.

Nothing here runs by itself -- start the app, read the two counts printed, and
only then pass --go. The live file is copied to quiz_app.db.bak-restore-<stamp>
before a single row is written, and a row whose email / client_uuid / date +
name already exists in the live database is skipped, so running it twice cannot
duplicate anything.

    venv\\Scripts\\python.exe _restore_from_head.py          # read-only preview
    venv\\Scripts\\python.exe _restore_from_head.py --go      # actually write
"""
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.join(HERE, 'quiz_app.db')
SNAP = os.path.join(HERE, '_quiz_app_from_head.db')

TABLES = [
    # (table, the columns worth carrying, the column that proves the row is already here)
    ('user', ['first_name', 'middle_name', 'last_name', 'suffix', 'school',
              'grade', 'section', 'email', 'password_hash', 'created_at'], 'email'),
    ('quiz_attempt', ['user_id', 'client_uuid', 'subject', 'topic', 'quiz_set_info',
                      'score', 'total', 'date_taken'], 'client_uuid'),
    ('ungraded', ['client_uuid', 'user_id', 'name', 'school', 'grade', 'section',
                  'subject', 'topic', 'quiz_set_info', 'score', 'total',
                  'date_taken'], 'client_uuid'),
]


def snapshot():
    """git show HEAD:quiz_app.db -> a temp file, so we read the committed copy."""
    data = subprocess.run(['git', 'show', 'HEAD:quiz_app.db'], cwd=HERE,
                          check=True, capture_output=True).stdout
    with open(SNAP, 'wb') as f:
        f.write(data)
    return SNAP


def rows(conn, table, cols):
    cur = conn.execute('select %s from %s' % (', '.join(cols), table))
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main():
    go = '--go' in sys.argv
    src = sqlite3.connect(snapshot())
    dst = sqlite3.connect(LIVE)

    print('live rows now   :', {t: dst.execute('select count(*) from %s' % t).fetchone()[0]
                                for t, _, _ in TABLES})
    print('snapshot rows   :', {t: src.execute('select count(*) from %s' % t).fetchone()[0]
                                for t, _, _ in TABLES})

    plan, stamp = [], datetime.now().strftime('%Y%m%d-%H%M%S')
    for table, cols, key in TABLES:
        have = {r[key] for r in rows(dst, table, [key])}
        missing = [r for r in rows(src, table, cols) if r[key] not in have]
        plan.append((table, cols, missing))
        print('%s: %d row(s) to bring back' % (table, len(missing)))
        for r in missing:
            print('   ', {c: r[c] for c in (['email'] if table == 'user' else [key, 'date_taken'])})

    if not go:
        print('\nPreview only. Re-run with --go to write.')
        return

    backup = LIVE + '.bak-restore-' + stamp
    shutil.copy2(LIVE, backup)
    print('copied the live file to', os.path.basename(backup))

    written = 0
    for table, cols, missing in plan:
        for r in missing:
            ph = ', '.join(['?'] * len(cols))
            dst.execute('insert into %s (%s) values (%s)' % (table, ', '.join(cols), ph),
                        [r[c] for c in cols])
            written += 1
    dst.commit()
    print('wrote %d row(s); live is now' % written,
          {t: dst.execute('select count(*) from %s' % t).fetchone()[0] for t, _, _ in TABLES})


if __name__ == '__main__':
    main()
