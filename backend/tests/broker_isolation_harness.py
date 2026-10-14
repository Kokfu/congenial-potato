"""Opt-in Docker acceptance fixture. Own/remove only unique fixture resources."""
from contextlib import contextmanager
import json
import select
import subprocess
import time
from uuid import uuid4


def docker(*args,check=True):
    return subprocess.run(['docker',*args],check=check,capture_output=True,text=True,timeout=45)


def details(name):
    return json.loads(docker('inspect',name).stdout)[0]


def service(name):
    ids=docker('compose','ps','--all','-q',name).stdout.strip().splitlines()
    assert len(ids)==1
    return ids[0]


def line(process,timeout=15):
    assert select.select([process.stdout],[],[],timeout)[0], 'fixture process did not respond'
    value=process.stdout.readline()
    assert value, 'fixture process closed without a response'
    return value.strip()


def send(process,value):
    process.stdin.write(json.dumps(value)+'\n')
    process.stdin.flush()


ORIGIN='''
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,os,ssl,sys,time
from pathlib import Path
assert os.getuid()==10001
cfg=json.loads(sys.stdin.readline())
cert,key=Path('/tmp/cert.pem'),Path('/tmp/key.pem')
cert.write_text(cfg['cert']); key.write_text(cfg['key']); key.chmod(0o600)
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(cert,key)
context.set_servername_callback(lambda _sock,host,_ctx: print('origin_sni='+str(host),flush=True))
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        print('origin_get='+self.path,flush=True)
        if cfg['pause']:
            deadline=time.monotonic()+4
            while not Path('/tmp/release').exists():
                if time.monotonic()>=deadline: return
                time.sleep(.01)
        if self.path=='/redirect':
            self.send_response(302); self.send_header('Location','https://example.test/followed')
            self.send_header('Content-Length','0'); self.end_headers(); return
        body=cfg['body'].encode('utf-8')
        self.send_response(200); self.send_header('Content-Type','text/plain')
        self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*args): pass
class Server(ThreadingHTTPServer):
    def handle_error(self,*args): pass
server=Server(('0.0.0.0',8443),Handler)
server.socket=context.wrap_socket(server.socket,server_side=True)
print('origin_ready',flush=True)
server.serve_forever()
'''

BROKER='''
import json,os,socket,ssl,sys
from pathlib import Path
from workforce.network_policy import PinnedHTTPSConnection
from workforce.read_broker_rpc import make_broker_server
assert os.getuid()==10001
assert 'APP_DATABASE_URL' not in os.environ and 'DB_PASSWORD_FILE' not in os.environ
assert 'INITIAL_ADMIN_PASSWORD_FILE' not in os.environ and 'workforce.db' not in sys.modules
assert not Path('/run/secrets/db_password').exists()
cfg=json.loads(sys.stdin.readline())
context=ssl.create_default_context(cadata=cfg['cert'])
def resolve(host,port,*,type):
    assert (host,port)==('example.test',443)
    return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(cfg['dns'],port))]
def factory(host,port,ip,*,timeout):
    assert (host,port,ip)==('example.test',443,'8.8.8.8')
    return PinnedHTTPSConnection(host,8443,cfg['origin'],timeout=timeout,context=context)
server=make_broker_server((cfg['bind'],8091),key=bytes.fromhex(cfg['key']),journal=Path('/journal'),
    resolver=resolve,connection_factory=factory,experiment_enabled=True,
    after_fetch=(lambda:os._exit(73)) if cfg['crash'] else None)
print('broker_ready',flush=True)
server.serve_forever()
'''

CLIENT='''
import json,os,sys
from workforce.read_broker_contract import BrokerOutcomeUnknown
from workforce.local_read_experiment import ReadDenied
from workforce.read_broker_rpc import broker_exchange
assert os.getuid()==10001
cfg=json.loads(sys.stdin.readline())
def authorize(envelope):
    print(json.dumps({'authorize':True}),flush=True)
    decision=sys.stdin.readline().strip()
    if decision=='unknown': raise BrokerOutcomeUnknown('fixture admission already consumed')
    if decision!='allow': raise ReadDenied('fixture mediator refused')
try:
    signed=broker_exchange((cfg['broker'],8091),cfg['ticket'],key=bytes.fromhex(cfg['key']),
        authorize=authorize,experiment_enabled=True)
    print(json.dumps({'signed':signed}),flush=True)
except BrokerOutcomeUnknown:
    print(json.dumps({'state':'unknown'}),flush=True)
except ReadDenied:
    print(json.dumps({'state':'denied'}),flush=True)
'''

BYPASS='''
import http.client,socket,sys,urllib.request
from pathlib import Path
origin,broker=sys.argv[1:]
assert all(r.split()[1]!='00000000' for r in Path('/proc/net/route').read_text().splitlines()[1:])
def denied(call):
    try: call()
    except (OSError,urllib.error.URLError): return
    raise AssertionError('origin bypass succeeded')
denied(lambda:socket.create_connection((origin,8443),timeout=.4))
def direct_http():
    c=http.client.HTTPConnection(origin,8443,timeout=.4)
    try: c.request('GET','/bypass'); c.getresponse().read()
    finally: c.close()
denied(direct_http)
opener=urllib.request.build_opener(urllib.request.ProxyHandler({'http':'http://'+origin+':8443'}))
denied(lambda:opener.open('http://fixture.invalid/proxy',timeout=.4))
with socket.create_connection((broker,8091),timeout=2) as c:
    c.sendall(b'CONNECT example.test:443 HTTP/1.1\\r\\n\\r\\n')
    try: assert c.recv(1)==b''
    except ConnectionResetError: pass
print('direct=denied; http=denied; proxy=denied; connect=denied')
'''


class Isolation:
    def __init__(self,image,cert,key,*,pause=False,dns='8.8.8.8',crash=False,body='ISOLATED_SYNTHETIC_CLAIM'):
        self.image,self.cert,self.key=image,cert,key
        self.pause,self.dns,self.crash=pause,dns,crash
        self.body=body
        self.prefix='workforce-broker-gate-'+uuid4().hex[:12]
        self.link,self.source,self.volume=(self.prefix+s for s in ('-link','-origin-net','-journal'))
        self.origin,self.broker=self.prefix+'-origin',self.prefix+'-broker'
        self.created_networks=[]; self.containers=[]; self.attached=[]; self.processes=[]
        self.volumes=[]
        self.services={name:service(name) for name in ('api','worker','db')}
        self.before={name:set(details(cid)['NetworkSettings']['Networks']) for name,cid in self.services.items()}
        assert len(self.before['api'])==len(self.before['worker'])==1
        self.control=next(iter(self.before['api']))
        assert self.before['db']==self.before['worker']==self.before['api']

    def _start(self,name,program,config):
        process=subprocess.Popen(['docker','start','-ai',name],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        self.processes.append(process)
        deadline=time.monotonic()+10
        while not details(name)['State']['Running']:
            assert process.poll() is None and time.monotonic()<deadline, 'fixture container did not start'
            time.sleep(.03)
        if name==self.broker:
            self.broker_ip=details(name)['NetworkSettings']['Networks'][self.link]['IPAddress']
            assert self.broker_ip
            config['bind']=self.broker_ip
        send(process,config)
        expected='origin_ready' if name==self.origin else 'broker_ready'
        assert line(process)==expected
        return process

    def _create(self,name,network,program,*,volume=False):
        args=['create','-i','--name',name,'--network',network,'--user','10001:10001',
              '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
              '--pids-limit','64','--memory','192m','--cpus','1',
              '--tmpfs','/tmp:rw,mode=1777','--entrypoint','python']
        if volume: args+=['--mount',f'type=volume,source={self.volume},target=/journal']
        docker(*args,self.image,'-u','-c',program)
        self.containers.append(name)

    def setup(self):
        assert int(docker('version','--format','{{.Server.Version}}').stdout.split('.')[0])>=28
        for name in (self.link,self.source):
            docker('network','create','--internal','--opt','com.docker.network.bridge.gateway_mode_ipv4=isolated',name)
            self.created_networks.append(name)
        self.initialize_journal(self.volume)
        self._create(self.origin,self.source,ORIGIN)
        self._start(self.origin,ORIGIN,{'cert':self.cert,'key':self.key,'pause':self.pause,'body':self.body})
        self.origin_ip=details(self.origin)['NetworkSettings']['Networks'][self.source]['IPAddress']
        assert self.origin_ip
        for name in ('api','worker'):
            docker('network','connect',self.link,self.services[name])
            self.attached.append(name)
        self.start_broker()
        self.check_networks()

    def initialize_journal(self,volume):
        docker('volume','create',volume)
        self.volumes.append(volume)
        docker('run','--rm','--network','none','--mount',f'type=volume,source={volume},target=/journal',
            '--entrypoint','python',self.image,'-c',
            "import os; os.chown('/journal',10001,10001); os.chmod('/journal',0o700)")

    def start_broker(self):
        self._create(self.broker,self.link,BROKER,volume=True)
        docker('network','connect',self.source,self.broker)
        self.broker_process=self._start(self.broker,BROKER,{'cert':self.cert,'key':self.signing_key.hex(),
            'origin':self.origin_ip,'dns':self.dns,'crash':self.crash})

    def restart_broker(self,*,replace_journal=False):
        docker('rm','-f',self.broker)
        self.containers.remove(self.broker)
        self.broker_process.communicate(timeout=5)
        self.crash=False
        if replace_journal:
            self.volume=self.prefix+'-replacement-journal'
            self.initialize_journal(self.volume)
        self.start_broker()
        self.check_networks()

    def check_networks(self):
        for name in ('api','worker'):
            info=details(self.services[name])
            assert set(info['NetworkSettings']['Networks'])==self.before[name]|{self.link}
            assert not any(n.get('Gateway') for n in info['NetworkSettings']['Networks'].values())
        info=details(self.broker)
        assert set(info['NetworkSettings']['Networks'])=={self.link,self.source}
        assert not any(n.get('Gateway') for n in info['NetworkSettings']['Networks'].values())
        assert info['Config']['User']=='10001:10001' and info['HostConfig']['ReadonlyRootfs']
        assert {v.removeprefix('CAP_') for v in info['HostConfig']['CapDrop']}=={'ALL'}
        assert {m['Destination'] for m in info['Mounts']} <= {'/journal','/tmp'}
        assert any(m['Destination']=='/journal' and m['Type']=='volume' and m['Name']==self.volume
                   for m in info['Mounts'])
        assert set(details(self.origin)['NetworkSettings']['Networks'])=={self.source}
        db_ip=details(self.services['db'])['NetworkSettings']['Networks'][self.control]['IPAddress']
        check='''
import socket,sys
from pathlib import Path
assert all(r.split()[1]!='00000000' for r in Path('/proc/net/route').read_text().splitlines()[1:])
try: socket.create_connection((sys.argv[1],5432),timeout=.4)
except OSError: print('broker_db=denied')
else: raise AssertionError('broker reached database network')
'''
        assert docker('exec','--user','10001:10001',self.broker,'python','-c',check,db_ip).stdout.strip()=='broker_db=denied'

    def assert_marker(self,invocation_id):
        code='''
from pathlib import Path
import os,stat,sys
from uuid import UUID
paths=list(Path('/journal').iterdir())
assert len(paths)==1 and paths[0].name==UUID(sys.argv[1]).hex+'.attempt'
assert paths[0].stat().st_uid==10001 and stat.S_IMODE(paths[0].stat().st_mode)==0o600
body=paths[0].read_bytes()
assert len(body)==65 and body[-1:]==b'\\n' and all(c in b'0123456789abcdef' for c in body[:-1])
print('private_digest_fence=passed')
'''
        assert docker('exec','--user','10001:10001',self.broker,'python','-c',code,
                      invocation_id).stdout.strip()=='private_digest_fence=passed'

    def bypass_checks(self):
        for name in ('api','worker'):
            result=docker('exec','--user','10001:10001',self.services[name],'python','-c',BYPASS,
                          self.origin_ip,self.broker_ip).stdout.strip()
            assert result=='direct=denied; http=denied; proxy=denied; connect=denied'

    def client(self,name,envelope):
        process=subprocess.Popen(['docker','exec','-i','--user','10001:10001',self.services[name],
            'python','-u','-c',CLIENT],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,text=True,bufsize=1)
        self.processes.append(process)
        send(process,{'broker':self.broker_ip,'ticket':envelope,'key':self.signing_key.hex()})
        return process

    def logs(self):
        return docker('logs',self.origin).stdout.splitlines()

    def wait_for_fetch(self):
        deadline=time.monotonic()+3
        while not any(v.startswith('origin_get=') for v in self.logs()):
            assert time.monotonic()<deadline, 'origin did not receive fixture request'
            time.sleep(.03)

    def release(self):
        docker('exec','--user','10001:10001',self.origin,'python','-c',
               "from pathlib import Path; Path('/tmp/release').touch()")

    def cleanup(self):
        for name in self.containers[::-1]: docker('rm','-f',name,check=False)
        for process in self.processes:
            if process.poll() is None: process.terminate()
            process.communicate(timeout=5)
        for name in self.attached[::-1]:
            docker('network','disconnect','-f',self.link,self.services[name],check=False)
        for name in self.created_networks[::-1]: docker('network','rm',name,check=False)
        for volume in self.volumes[::-1]: docker('volume','rm',volume,check=False)
        for name,cid in self.services.items():
            assert set(details(cid)['NetworkSettings']['Networks'])==self.before[name], 'topology not restored'


@contextmanager
def isolated(image,cert,key,signing_key,**kwargs):
    fixture=Isolation(image,cert,key,**kwargs)
    fixture.signing_key=signing_key
    try:
        fixture.setup()
        yield fixture
    finally:
        fixture.cleanup()
