"""Create private production secrets without printing or overwriting existing values."""
from pathlib import Path
import os
import secrets

root=Path(__file__).resolve().parent/'secrets'
root.mkdir(mode=0o700,exist_ok=True)
for name in ['db_admin_password','db_migrator_password','db_api_password','db_worker_password','processor_token','mail_encryption_key','integration_encryption_key']:
    path=root/name
    if not path.exists():path.write_text(secrets.token_hex(32),encoding='ascii');path.chmod(0o600)
for role in ['migrator','api','worker']:
    path=root/f'database_{role}_url'
    if not path.exists():
        password=(root/f'db_{role}_password').read_text(encoding='ascii').strip()
        path.write_text(f'postgresql://fsp_{role}:{password}@postgres:5432/fsp_trajectory',encoding='ascii');path.chmod(0o600)
smtp=root/'smtp_password'
if not smtp.exists():smtp.write_text('',encoding='ascii');smtp.chmod(0o600)
print('Private secrets prepared. Set deploy/secrets/smtp_password and deploy/production.env before deployment. No secrets printed.')
