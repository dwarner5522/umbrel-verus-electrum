'''Runs ElectrumX for Verus and serves a status page, its JSON API and an Umbrel widget.

Standard library only. ElectrumX itself runs as a child process from /opt/electrumx.
'''
import collections
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlsplit

HTTP_PORT = int(os.environ.get('PORT', '3000'))
ELECTRUMX_DIR = os.environ.get('ELECTRUMX_DIR', '/opt/electrumx')
DB_DIRECTORY = os.environ.get('DB_DIRECTORY', '/data/db')
ELECTRUM_PORT = int(os.environ.get('ELECTRUM_PORT', '17485'))
# ElectrumX's own admin RPC. It has no authentication, so it only ever listens on loopback.
ADMIN_RPC_PORT = int(os.environ.get('ADMIN_RPC_PORT', '8000'))
DAEMON_HOST = os.environ.get('DAEMON_HOST', '')
DAEMON_RPC_PORT = os.environ.get('DAEMON_RPC_PORT', '27486')
DAEMON_RPC_USER = os.environ.get('DAEMON_RPC_USER', '')
DAEMON_RPC_PASS = os.environ.get('DAEMON_RPC_PASS', '')
DEVICE_DOMAIN_NAME = os.environ.get('DEVICE_DOMAIN_NAME', '')
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'public')

RESTART_DELAY = 15
POLL_INTERVAL = 5

MIME = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.svg': 'image/svg+xml',
}

state = {
    # starting -> syncing -> ready
    'phase': 'starting',
    'message': 'Starting ElectrumX…',
    'error': None,
    'dbHeight': None,
    'daemonHeight': None,
    'progress': 0,
    'sessions': 0,
    'uptime': None,
    'version': None,
    'updatedAt': None,
}
log_lines = collections.deque(maxlen=200)
child = None
serving = False
shutting_down = threading.Event()


def log(message):
    print('{} supervisor: {}'.format(time.strftime('%Y-%m-%dT%H:%M:%S'), message), flush=True)


# ---------------------------------------------------------------------------
# ElectrumX process

def electrumx_env():
    env = dict(os.environ)
    env.update({
        'COIN': 'Verus',
        'NET': 'mainnet',
        'DB_DIRECTORY': DB_DIRECTORY,
        'DAEMON_URL': 'http://{}:{}@{}:{}/'.format(
            quote(DAEMON_RPC_USER, safe=''), quote(DAEMON_RPC_PASS, safe=''), DAEMON_HOST, DAEMON_RPC_PORT),
        'HOST': '0.0.0.0',
        'TCP_PORT': str(ELECTRUM_PORT),
        'RPC_HOST': '127.0.0.1',
        'RPC_PORT': str(ADMIN_RPC_PORT),
        # A personal server: don't look for or announce to public Electrum peers.
        'PEER_DISCOVERY': 'off',
        'PEER_ANNOUNCE': '',
        'PYTHONUNBUFFERED': '1',
    })
    env.setdefault('CACHE_MB', '800')
    # The default per-session bandwidth limit (2 MB an hour) throttles wallets with many addresses.
    env.setdefault('BANDWIDTH_LIMIT', '100000000')
    return env


def pump_output(stream):
    for raw in iter(stream.readline, b''):
        line = raw.decode('utf-8', 'replace').rstrip()
        log_lines.append(line)
        print(line, flush=True)


def run_electrumx():
    '''Keep ElectrumX running until we are asked to shut down.'''
    global child, serving
    os.makedirs(DB_DIRECTORY, exist_ok=True)
    while not shutting_down.is_set():
        log('starting ElectrumX')
        serving = False
        state.update(phase='starting', message='Starting ElectrumX…', dbHeight=None, daemonHeight=None, sessions=0)
        child = subprocess.Popen(
            [sys.executable, os.path.join(ELECTRUMX_DIR, 'electrumx_server')],
            cwd=ELECTRUMX_DIR, env=electrumx_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        pump_output(child.stdout)
        code = child.wait()
        child = None
        log('ElectrumX exited with code {}'.format(code))
        if shutting_down.is_set():
            return
        state.update(phase='stopped', message='ElectrumX stopped. Restarting…')
        if code != 0:
            state['error'] = 'ElectrumX exited unexpectedly (code {}). See the log below.'.format(code)
        shutting_down.wait(RESTART_DELAY)


def admin_rpc(method):
    '''One newline-delimited JSON-RPC call to ElectrumX's local admin port.'''
    with socket.create_connection(('127.0.0.1', ADMIN_RPC_PORT), timeout=10) as sock:
        sock.sendall(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': []}).encode() + b'\n')
        reply = json.loads(sock.makefile('rb').readline())
    if reply.get('error'):
        raise RuntimeError(reply['error'])
    return reply['result']


def electrum_port_open():
    try:
        socket.create_connection(('127.0.0.1', ELECTRUM_PORT), timeout=3).close()
        return True
    except OSError:
        return False


def poll():
    global serving
    while not shutting_down.wait(POLL_INTERVAL):
        if child is None:
            continue
        try:
            info = admin_rpc('getinfo')
        except (OSError, ValueError, RuntimeError):
            # Not listening yet: ElectrumX is opening its database or waiting for the Verus node.
            if state['phase'] not in ('starting', 'stopped'):
                state.update(phase='starting', message='Waiting for ElectrumX…')
            elif any('daemon' in line.lower() and ('error' in line.lower() or 'connect' in line.lower())
                     for line in list(log_lines)[-5:]):
                state['message'] = 'Waiting for the Verus node…'
            continue

        db_height = info.get('db_height') or 0
        daemon_height = info.get('daemon_height') or 0
        # ElectrumX only opens the Electrum port once it has caught up with the node.
        # Stop probing after that, so the probe doesn't show up as a wallet connection.
        serving = serving or electrum_port_open()
        ready = serving
        state.update(
            phase='ready' if ready else 'syncing',
            message='Ready for wallets' if ready else 'Indexing the blockchain',
            error=None,
            dbHeight=db_height,
            daemonHeight=daemon_height,
            progress=1 if ready else (min(db_height / daemon_height, 1) if daemon_height > 0 else 0),
            # one of the sessions is this admin RPC connection
            sessions=max(info.get('sessions', 0) - 1, 0),
            uptime=info.get('uptime'),
            version=info.get('version'),
            updatedAt=int(time.time() * 1000),
        )


# ---------------------------------------------------------------------------
# HTTP

def widget_sync():
    ready = state['phase'] == 'ready'
    known = state['dbHeight'] is not None
    # Don't round up to 100% until wallets can actually connect.
    percent = 100 if ready else min(int(state['progress'] * 1000) / 10, 99.9)
    return {
        'type': 'text-with-progress',
        'refresh': '5s',
        'link': '',
        'title': 'Electrum server',
        'text': '{:g}%'.format(percent) if known else '-',
        'progressLabel': 'Ready' if ready else ('Indexing' if known else 'Starting'),
        'progress': state['progress'] if known else 0,
    }


def connect_details():
    return {'host': DEVICE_DOMAIN_NAME, 'port': ELECTRUM_PORT, 'protocol': 'tcp'}


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send(status, json.dumps(payload).encode(), 'application/json')

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/status':
            return self.send_json(200, dict(state, connect=connect_details()))
        if path == '/api/logs':
            return self.send_json(200, {'lines': list(log_lines)})
        if path == '/api/widget/sync':
            return self.send_json(200, widget_sync())
        if path.startswith('/api/'):
            return self.send_json(404, {'error': 'Not found'})

        relative = 'index.html' if path == '/' else path.lstrip('/')
        file = os.path.realpath(os.path.join(PUBLIC_DIR, relative))
        extension = os.path.splitext(file)[1]
        if not file.startswith(PUBLIC_DIR + os.sep) or extension not in MIME or not os.path.isfile(file):
            return self.send_json(404, {'error': 'Not found'})
        with open(file, 'rb') as handle:
            self.send(200, handle.read(), MIME[extension])


# ---------------------------------------------------------------------------
# Lifecycle

def shutdown(signum, _frame):
    if shutting_down.is_set():
        return
    log('signal {} received, stopping ElectrumX'.format(signum))
    shutting_down.set()
    state.update(phase='stopping', message='Shutting down…')
    if child is not None:
        # ElectrumX flushes its database on SIGTERM
        child.terminate()


def main():
    if not (DAEMON_HOST and DAEMON_RPC_USER and DAEMON_RPC_PASS):
        sys.exit('DAEMON_HOST, DAEMON_RPC_USER and DAEMON_RPC_PASS are required')

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    server = ThreadingHTTPServer(('0.0.0.0', HTTP_PORT), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=poll, daemon=True).start()
    log('status page listening on :{}'.format(HTTP_PORT))

    run_electrumx()
    server.shutdown()


if __name__ == '__main__':
    main()
