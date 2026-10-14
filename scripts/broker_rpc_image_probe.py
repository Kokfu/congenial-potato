"""Synthetic RPC probe for a UID 10001, network-none backend container.

Feed this file to python via stdin; no PostgreSQL or product service is used.
The authorizer is a trusted fixture stub, not database authorization evidence.
"""
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import os,secrets,socket,tempfile,sys
from threading import Thread
from uuid import uuid4
from workforce.network_policy import PinnedHTTPConnection
from workforce.read_broker_contract import BrokerReadTicket,BrokerOutcomeUnknown,sign_ticket
from workforce.read_broker_result import verify_broker_reply
from workforce.read_broker_rpc import make_broker_server,broker_exchange
assert os.getuid()==10001
assert 'APP_DATABASE_URL' not in os.environ and 'workforce.db' not in sys.modules
seen=[]
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        seen.append(self.path)
        body=b'IMAGE_RPC_SYNTHETIC_CLAIM'
        self.send_response(200)
        self.send_header('Content-Type','text/plain')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self,*args): pass
origin=ThreadingHTTPServer(('127.0.0.1',0),Handler)
origin_thread=Thread(target=origin.serve_forever,daemon=True)
origin_thread.start()
def resolve(host,port,*,type):
    assert (host,port)==('example.test',443)
    return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',port))]
def factory(host,port,ip,*,timeout):
    assert (host,port,ip)==('example.test',443,'8.8.8.8')
    return PinnedHTTPConnection(host,origin.server_port,'127.0.0.1',timeout=timeout)
key=secrets.token_bytes(32)
journal=Path(tempfile.mkdtemp(prefix='rpc-journal-'))
broker=make_broker_server(('127.0.0.1',0),key=key,journal=journal,resolver=resolve,
    connection_factory=factory,experiment_enabled=True)
thread=Thread(target=broker.serve_forever,kwargs={'poll_interval':.02},daemon=True)
thread.start()
at=datetime.now(timezone.utc)
ticket=BrokerReadTicket(attempt_id=uuid4(),approval_id=uuid4(),project_id=uuid4(),
    agent_id=uuid4(),root_id=uuid4(),payload_hash='a'*64,policy_hash='b'*64,schema_hash='c'*64,
    grant_id=uuid4(),grant_revision=1,grant_expires_at=at+timedelta(hours=1),issued_at=at,
    expires_at=at+timedelta(seconds=30),url='https://example.test/source',max_bytes=64,
    timeout_seconds=1.,addresses=('8.8.8.8',))
envelope=sign_ticket(ticket,key=key)
def authorize(value):
    assert value==envelope and seen==[] and len(list(journal.iterdir()))==1
try:
    signed=broker_exchange(broker.server_address,envelope,key=key,authorize=authorize,
                           experiment_enabled=True)
    assert verify_broker_reply(signed,envelope,key=key).text=='IMAGE_RPC_SYNTHETIC_CLAIM'
    try:
        broker_exchange(broker.server_address,envelope,key=key,authorize=authorize,experiment_enabled=True)
        raise AssertionError('replayed request')
    except BrokerOutcomeUnknown: pass
    assert seen==['/source']
    print('uid=10001; network=none; rpc_roundtrip=passed; durable_fence=passed; replay=denied')
finally:
    broker.shutdown(); broker.server_close(); thread.join(timeout=3)
    origin.shutdown(); origin.server_close(); origin_thread.join(timeout=3)
