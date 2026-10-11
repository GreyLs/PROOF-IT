"""Provision independent local secrets; never print their values."""
from pathlib import Path
from scripts.private_runtime import private_file
import argparse, secrets
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--origin',default='http://localhost:1717');args=parser.parse_args()
    from urllib.parse import urlsplit
    url=urlsplit(args.origin)
    if url.scheme not in ('http','https') or not url.hostname or url.path not in ('','/') or url.username:raise SystemExit('Provide an origin without path or credentials')
    root=Path(__file__).resolve().parents[1];runtime=root/'runtime';runtime.mkdir(exist_ok=True)
    path=private_file('keycloak.env')
    if not path.exists():
        path.write_text('\n'.join(['PROOFIT_KC_DB_PASSWORD='+secrets.token_urlsafe(48),'PROOFIT_KC_ADMIN_PASSWORD='+secrets.token_urlsafe(32),'PROOFIT_OIDC_CLIENT_SECRET='+secrets.token_urlsafe(48),'PROOFIT_PUBLIC_ORIGIN='+args.origin])+'\n',encoding='utf-8')
    key=runtime/'passport-ed25519.pem'
    from dotenv import dotenv_values
    client=runtime/'keycloak-client.secret'
    if not client.exists():client.write_text(dotenv_values(path)['PROOFIT_OIDC_CLIENT_SECRET'],encoding='ascii')
    if not key.exists():key.write_bytes(Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    print('Independent secrets provisioned in ignored runtime files. Existing secrets preserved.')
if __name__=='__main__':main()
