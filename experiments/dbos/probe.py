"""Disposable DBOS recovery probe. No model or external service is used."""
import os
import sys
import time
from datetime import datetime, timezone

import psycopg
from dbos import DBOS, SetWorkflowID

URL = os.environ.get('PHASE0_DB_URL', 'postgresql://postgres:phase0fixture@127.0.0.1:55432/phase0')
MODE = sys.argv[1]


def sql(query, args=()):
    with psycopg.connect(URL) as conn:
        with conn.cursor() as cur:
            cur.execute(query, args)
            if cur.description:
                return cur.fetchall()


def setup():
    sql('CREATE SCHEMA IF NOT EXISTS fixture')
    sql('CREATE TABLE IF NOT EXISTS fixture.events (kind text NOT NULL, key text NOT NULL, at timestamptz DEFAULT now())')
    sql('CREATE TABLE IF NOT EXISTS fixture.effects (key text PRIMARY KEY, payload text NOT NULL)')
    sql('CREATE TABLE IF NOT EXISTS fixture.control (key text PRIMARY KEY, cancelled boolean NOT NULL)')


def record(kind, key):
    sql('INSERT INTO fixture.events(kind,key) VALUES (%s,%s)', (kind,key))


def count(kind, key):
    return sql('SELECT count(*) FROM fixture.events WHERE kind=%s AND key=%s', (kind,key))[0][0]


@DBOS.step()
def model():
    record('model', 'd01')
    return 'fake-model-result'


@DBOS.step()
def after_signal():
    record('after_signal', 'd02')


@DBOS.workflow()
def recovery():
    value = model()
    response = DBOS.recv('approval', timeout_seconds=120)
    if response != {'request':'approval-1','decision':'approve'}:
        return 'wrong-signal'
    after_signal()
    return value


@DBOS.workflow()
def dedupe():
    record('run','d03')
    return 'done'


@DBOS.step()
def unsafe_effect():
    record('attempt','d04')
    sql('INSERT INTO fixture.effects(key,payload) VALUES (%s,%s) ON CONFLICT DO NOTHING', ('d04','synthetic'))
    if count('attempt','d04') == 1:
        os._exit(42)
    return 'reconciled'


@DBOS.workflow()
def effect_workflow():
    return unsafe_effect()


@DBOS.step()
def guarded_effect():
    record('effect','d05')


@DBOS.workflow()
def cancellable():
    DBOS.recv('gate', timeout_seconds=120)
    if sql('SELECT cancelled FROM fixture.control WHERE key=%s', ('d05',))[0][0]:
        return 'stopped'
    guarded_effect()


@DBOS.step()
def version_start():
    record('version_start','d07')


@DBOS.step()
def version_finish():
    record('version_finish','d07')


@DBOS.workflow()
def versioned():
    version_start()
    DBOS.recv('version-signal', timeout_seconds=120)
    version_finish()
    return 'finished'


@DBOS.workflow()
def scheduled(scheduled_time, context):
    record('schedule', scheduled_time.isoformat())


def wait_for(predicate, seconds=12):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate(): return True
        time.sleep(.1)
    return False


def status():
    return {k: sql('SELECT count(*) FROM fixture.events WHERE kind=%s',(k,))[0][0] for k in ['model','after_signal','run','attempt','effect','schedule']}


setup()
DBOS(config={'name':'phase0-dbos','system_database_url':URL,'executor_id':'phase0', 'application_version':os.environ.get('PHASE0_APP_VERSION','1'), 'scheduler_polling_interval_sec':1, 'log_level':'WARNING'})
DBOS.launch()
if MODE == 'start-version':
    with SetWorkflowID('phase0-version'):
        DBOS.start_workflow(versioned)
    assert wait_for(lambda: count('version_start','d07') == 1)
    print('version before crash',DBOS.get_workflow_status('phase0-version').status,flush=True)
    os._exit(44)
elif MODE == 'inspect-version':
    print('version on v2',DBOS.get_workflow_status('phase0-version').status,'finished',count('version_finish','d07'),flush=True)
elif MODE == 'finish-version':
    DBOS.send('phase0-version','go','version-signal')
    print('version back on v1',DBOS.retrieve_workflow('phase0-version').get_result(),'finished',count('version_finish','d07'),flush=True)
elif MODE == 'start-recovery':
    with SetWorkflowID('phase0-recovery'):
        DBOS.start_workflow(recovery)
    assert wait_for(lambda: count('model','d01') == 1)
    print('before crash', status(), flush=True)
    os._exit(41)
elif MODE == 'finish-recovery':
    DBOS.send('phase0-recovery', {'request':'approval-1','decision':'approve'}, 'approval')
    result=DBOS.retrieve_workflow('phase0-recovery').get_result()
    print('after restart', result, status(), flush=True)
elif MODE == 'dedupe':
    with SetWorkflowID('phase0-dedupe'):
        a=DBOS.start_workflow(dedupe)
    with SetWorkflowID('phase0-dedupe'):
        b=DBOS.start_workflow(dedupe)
    print('dedupe',a.get_result(), b.get_result(), status(), flush=True)
elif MODE == 'start-effect':
    with SetWorkflowID('phase0-effect'):
        DBOS.start_workflow(effect_workflow)
    time.sleep(10)
elif MODE == 'finish-effect':
    print('effect result',DBOS.retrieve_workflow('phase0-effect').get_result(),status(), 'ledger',sql('SELECT count(*) FROM fixture.effects WHERE key=%s',('d04',)),flush=True)
elif MODE == 'guard':
    sql('INSERT INTO fixture.control(key,cancelled) VALUES (%s,true) ON CONFLICT(key) DO UPDATE SET cancelled=false', ('d05',))
    with SetWorkflowID('phase0-guard'):
        DBOS.start_workflow(cancellable)
    time.sleep(.5)
    sql('UPDATE fixture.control SET cancelled=true WHERE key=%s', ('d05',))
    DBOS.send('phase0-guard','go','gate')
    print('guard',DBOS.retrieve_workflow('phase0-guard').get_result(),status(),flush=True)
elif MODE == 'cancel':
    sql('INSERT INTO fixture.control(key,cancelled) VALUES (%s,false) ON CONFLICT(key) DO UPDATE SET cancelled=false', ('d05',))
    with SetWorkflowID('phase0-cancel'):
        DBOS.start_workflow(cancellable)
    time.sleep(.5)
    DBOS.cancel_workflow('phase0-cancel')
    DBOS.send('phase0-cancel','go','gate')
    time.sleep(1)
    print('cancel',DBOS.get_workflow_status('phase0-cancel').status,status(),flush=True)
elif MODE == 'schedule-before':
    DBOS.create_schedule(schedule_name='phase0-every-second',workflow_fn=scheduled,schedule='* * * * * *',automatic_backfill=False)
    time.sleep(2.5)
    print('schedule before',status(),sql('SELECT key FROM fixture.events WHERE kind=%s ORDER BY key',('schedule',)),flush=True)
    os._exit(43)
elif MODE == 'schedule-after':
    time.sleep(2.5)
    print('schedule after',status(),sql('SELECT key FROM fixture.events WHERE kind=%s ORDER BY key',('schedule',)),flush=True)
else:
    raise ValueError(MODE)
DBOS.destroy()
