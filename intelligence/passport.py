"""Portable, revocable, non-identifying Ed25519 proof credentials."""
import hashlib, os, time
from pathlib import Path
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ISSUER='proofit:proof-passport:v1'
def key():
    path=Path(os.getenv('PASSPORT_KEY_FILE','runtime/passport-ed25519.pem'))
    if not path.exists():raise ValueError('passport_key_not_provisioned')
    return serialization.load_pem_private_key(path.read_bytes(),password=None)
def public(_):
    return {'algorithm':'EdDSA','issuer':ISSUER,'public_key':key().public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()}
def issue(p):
    now=int(time.time());claims=p['claims']
    token=jwt.encode({'iss':ISSUER,'aud':'proofit:proof-verifier','iat':now,'exp':now+86400*30,'jti':p['id'],'proof':claims},key(),algorithm='EdDSA',headers={'typ':'proofit+jwt'})
    return {'token':token,'digest':hashlib.sha256(token.encode()).hexdigest(),'expires_at':now+86400*30,'algorithm':'Ed25519','public_key':public({})['public_key']}
def verify(p):
    token=p.get('token','')
    if not isinstance(token,str) or not 20<=len(token)<=20000:raise ValueError('token')
    try:
        value=jwt.decode(token,key().public_key(),algorithms=['EdDSA'],issuer=ISSUER,audience='proofit:proof-verifier',options={'require':['iss','aud','iat','exp','jti','proof']})
        return {'signature_valid':True,'id':value['jti'],'proof':value['proof'],'expires_at':value['exp'],'digest':hashlib.sha256(token.encode()).hexdigest()}
    except jwt.PyJWTError:return {'signature_valid':False}
