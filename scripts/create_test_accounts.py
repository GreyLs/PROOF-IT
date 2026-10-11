"""Create two local test accounts through the normal registration and login API.

Passwords are generated once and stored only in ignored runtime/test-accounts.json.
This deliberately requires the local mail sandbox and cannot provision production.
"""
from pathlib import Path
import json
import os
import secrets

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'runtime/test-accounts.json'
ORIGIN = (os.environ.get('FSP_TEST_BASE_URL') or dotenv_values(ROOT / '.env').get('BASE_URL') or 'http://localhost:1414').rstrip('/')


def main():
    accounts = json.loads(DESTINATION.read_text(encoding='utf-8')) if DESTINATION.exists() else {}
    with httpx.Client(base_url=ORIGIN + '/api', headers={'Origin': ORIGIN}, timeout=30, trust_env=False) as client:
        metadata = client.get('/meta')
        metadata.raise_for_status()
        if metadata.json().get('demo') is not True:
            raise SystemExit('Test provisioning requires the local mail sandbox')
        for role, name in [('employer', 'Тестовая ИТ-компания'), ('candidate', 'Тестовый кандидат')]:
            account = accounts.get(role)
            if account is None:
                account = {'email': f'{role}@fsp.test', 'password': secrets.token_urlsafe(18)}
                response = client.post('/auth/register', json={**account, 'role': role, 'name': name, 'consent_processing': True})
                response.raise_for_status()
                token = response.json().get('development_mail', {}).get('token')
                if not token:
                    raise SystemExit(f'Account {role} already exists without a local credential file; refusing to replace its password')
                response = client.post('/auth/verify', json={'token': token})
                response.raise_for_status()
                account['user'] = response.json()['user']
                accounts[role] = account
                DESTINATION.parent.mkdir(exist_ok=True)
                DESTINATION.write_text(json.dumps(accounts, ensure_ascii=False, indent=2), encoding='utf-8')
                DESTINATION.chmod(0o600)
                client.post('/auth/logout').raise_for_status()
            response = client.post('/auth/login', json={key: account[key] for key in ('email', 'password')})
            response.raise_for_status()
            assert response.json()['user']['role'] == role
            client.post('/auth/logout').raise_for_status()
            print(f'{role}: registration and password login verified')
    print('Credentials: runtime/test-accounts.json (not in Git)')


if __name__ == '__main__':
    main()
