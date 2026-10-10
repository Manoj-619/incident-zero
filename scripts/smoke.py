"""HTTP smoke test against an already-running instance (direct backend or nginx)."""
import json
import sys
import time
import uuid
import urllib.error
import urllib.request

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5173'
capability = uuid.uuid4().hex + uuid.uuid4().hex


def call(path, payload=None, token=capability):
    headers = {'Content-Type': 'application/json', 'X-Session-Token': token}
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(base + path, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


assert call('/api/health')['simulation_only']
identifier = call('/api/missions', {'scenario': 'crossing'})['id']
path = '/api/missions/' + identifier
try:
    call(path, token=uuid.uuid4().hex)
    raise AssertionError('Owner isolation failed')
except urllib.error.HTTPError as error:
    assert error.code == 404
for _ in range(120):
    run = call(path)
    if run['status'] != 'running':
        break
    time.sleep(.5)
assert run['status'] == 'approval_pending', run.get('error')
assert run['result']['verification']['passed']
assert call(path + '/approve', {})['already_approved'] is False
assert call(path + '/approve', {})['already_approved'] is True
assert call(path + '/report')['status'] == 'approved'
print('PASS: health, computation, owner isolation, independent verification, atomic approval, report')
