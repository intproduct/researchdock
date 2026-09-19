"""Manual T02 acceptance helper; fixture state stays under runtime/.
Use only with the isolated stack described in docs/handoff/T02-manual-test.zh-CN.md.
This tool writes synthetic API records; it never scans or changes local repositories.
"""
import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['seed', 'verify'])
    p.add_argument('--base', required=True)
    p.add_argument('--env-file', required=True)
    p.add_argument('--state', required=True)
    a = p.parse_args()
    origin = urllib.parse.urlsplit(a.base)
    if origin.scheme != 'http' or origin.hostname not in ('127.0.0.1', 'localhost'):
        p.error('Use the isolated loopback HTTP endpoint only')
    state = (ROOT / a.state).resolve()
    if not state.is_relative_to(ROOT / 'runtime'):
        p.error('state must be inside project runtime/')
    config = (ROOT / a.env_file).resolve()
    if not config.is_relative_to(ROOT / 'runtime'):
        p.error('env-file must be the isolated generated file inside runtime/')
    env = dict(line.split('=', 1) for line in config.read_text(encoding='utf-8-sig').splitlines() if '=' in line and not line.startswith('#'))
    base = a.base.rstrip('/') + '/api/v1'
    def request(path, body=None, token=None, method=None, expected=200, form=False):
        headers = {}
        if token: headers['Authorization'] = 'Bearer ' + token
        data = None
        if body is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
            data = (urllib.parse.urlencode(body) if form else json.dumps(body)).encode()
        req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                code, payload = response.status, response.read()
        except urllib.error.HTTPError as error:
            code, payload = error.code, error.read()
        if code != expected:
            raise RuntimeError(f'{method or ("POST" if body is not None else "GET")} {path}: expected {expected}, got {code}')
        return json.loads(payload) if payload else None
    token = request('/login/access-token', {'username':env['FIRST_SUPERUSER'], 'password':env['FIRST_SUPERUSER_PASSWORD']}, form=True)['access_token']
    if a.mode == 'seed':
        if state.exists(): p.error('Refusing to overwrite existing fixture state')
        project = request('/projects', {'name':'T02 manual acceptance', 'stage':'active', 'status_note':'initial'}, token, expected=201)
        for note in ['first save', 'second save']:
            body = {k:project[k] for k in ['name','description','stage','status_note','next_step','revision']}
            body['status_note'] = note
            project = request('/projects/' + project['id'], body, token, 'PUT')
        device = request('/devices', {'name':'T02 disposable device','platform':'audit'}, token, expected=201)
        device_token = device['token']
        copy = request('/agent/copies', {'project_id':project['id'],'local_path':'/t02-audit-metadata-only'}, device_token)
        for seq in [5, 2, 5]:
            request('/agent/copies/' + copy['id'] + '/observations', {'sequence':seq,'observed_at':datetime.now(UTC).isoformat(),'comparison':'unknown','reason':'T02 fixture'}, device_token)
        request('/devices/' + device['device']['id'] + '/revoke', {}, token)
        copies = request('/projects/' + project['id'] + '/copies', token=token)
        assert copies[0]['sequence'] == 5
        record = {'project':project, 'history':request('/projects/'+project['id']+'/history',token=token), 'copies':copies, 'device_id':device['device']['id'], 'device_token':device_token}
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(json.dumps(record), encoding='utf-8')
        try: os.chmod(state, 0o600)
        except OSError: pass
        print('PASS seed: project revision 3, history, device, copy sequence 5, revoked credential')
    else:
        record = json.loads(state.read_text(encoding='utf-8'))
        project = record['project']
        actual = next(x for x in request('/projects',token=token) if x['id']==project['id'])
        assert actual == project, 'project differs'
        assert request('/projects/'+project['id']+'/history',token=token)==record['history'], 'history differs'
        assert request('/projects/'+project['id']+'/copies',token=token)==record['copies'], 'copies/sequence differ'
        device = next(x for x in request('/devices',token=token) if x['id']==record['device_id'])
        assert device['revoked'], 'revocation lost'
        print('PASS project/history/copy IDs, contents, revision, sequence, revocation preserved')
    record = json.loads(state.read_text(encoding='utf-8'))
    project = record['project']
    body = {k:project[k] for k in ['name','description','stage','status_note','next_step','revision']}
    body['revision'] -= 1
    request('/projects/'+project['id'],body,token,'PUT',expected=409)
    request('/agent/projects',token=record['device_token'],expected=401)
    print('PASS stale revision rejected (409), revoked device rejected (401)')

if __name__ == '__main__':
    main()