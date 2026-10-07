#!/usr/bin/env bash
set -uo pipefail
VENV=${PHASE0_VENV:-/tmp/phase0-dbos-venv}
PYTHON="$VENV/bin/python"
"$PYTHON" - <<'PY'
import os, psycopg
url=os.environ.get('PHASE0_DB_URL','postgresql://postgres:phase0fixture@127.0.0.1:55432/phase0')
with psycopg.connect(url) as conn:
    conn.execute('DROP SCHEMA IF EXISTS dbos CASCADE')
    conn.execute('DROP SCHEMA IF EXISTS fixture CASCADE')
PY
run() {
  echo "$(date -u +%FT%TZ) $1"
  "$PYTHON" experiments/dbos/probe.py "$1"
  code=$?
  echo "exit=$code"
  if [[ "$code" != "$2" ]]; then exit 1; fi
}
run start-recovery 41
run finish-recovery 0
run dedupe 0
run start-effect 42
run finish-effect 0
run guard 0
run cancel 0
run schedule-before 43
sleep 3
run schedule-after 0
run start-version 44
PHASE0_APP_VERSION=2 run inspect-version 0
run finish-version 0
"$PYTHON" - <<'PY'
import os, psycopg
url=os.environ.get('PHASE0_DB_URL','postgresql://postgres:phase0fixture@127.0.0.1:55432/phase0')
with psycopg.connect(url) as conn:
    for table in ('events','effects','control'):
        print(table,conn.execute(f'SELECT count(*) FROM fixture.{table}').fetchone()[0])
    unique,total=conn.execute("SELECT count(DISTINCT key),count(*) FROM fixture.events WHERE kind='schedule'").fetchone()
    print('schedule_unique',(unique,total))
    counts=dict(conn.execute('SELECT kind,count(*) FROM fixture.events GROUP BY kind').fetchall())
    assert counts['model']==1 and counts['after_signal']==1
    assert counts['run']==1 and counts['attempt']==2 and counts.get('effect',0)==0
    assert counts['version_start']==1 and counts['version_finish']==1
    assert conn.execute('SELECT count(*) FROM fixture.effects').fetchone()[0]==1
    assert unique==total and total>=2
    print('assertions=passed')
PY
