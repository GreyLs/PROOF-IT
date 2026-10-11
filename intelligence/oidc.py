"""Allowlisted OIDC Authorization Code + PKCE connector; no email auto-linking."""
import base64
import hashlib
import os
from urllib.parse import urlencode,urlsplit

import httpx
import jwt
from worker.config import secret


def configuration(demo=False):
    issuer=os.getenv("FSP_OIDC_ISSUER","").rstrip("/")
    if not issuer:raise ValueError("oidc_not_configured")
    parsed=urlsplit(issuer)
    if parsed.scheme!="https" and not (demo and parsed.scheme=="http" and parsed.hostname in ("127.0.0.1","localhost")):raise ValueError("issuer_https")
    return issuer,os.getenv("FSP_OIDC_CLIENT_ID","proofit"),secret("FSP_OIDC_CLIENT_SECRET","")


async def metadata(client,issuer):
    response=await client.get(issuer+"/.well-known/openid-configuration");response.raise_for_status()
    data=response.json()
    if data["issuer"]!=issuer:raise ValueError("issuer_mismatch")
    origin=urlsplit(issuer)
    for name in ("authorization_endpoint","token_endpoint","jwks_uri"):
        parsed=urlsplit(data[name])
        if (parsed.scheme,parsed.netloc)!=(origin.scheme,origin.netloc):raise ValueError("endpoint_origin")
    return data


async def start(payload):
    issuer,client_id,_=configuration(payload.get("demo",False))
    async with httpx.AsyncClient(trust_env=False,timeout=10,follow_redirects=False) as client:
        endpoints=await metadata(client,issuer)
    verifier=payload["verifier"]
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params={"response_type":"code","client_id":client_id,"redirect_uri":payload["redirect_uri"],"scope":"openid","state":payload["state"],"nonce":payload["nonce"],"code_challenge":challenge,"code_challenge_method":"S256"}
    return {"authorization_url":endpoints["authorization_endpoint"]+"?"+urlencode(params),"issuer":issuer,"local_demo":False}


def verify(token,jwks,issuer,client_id,nonce):
    if len(token)>24000:raise ValueError("token_limit")
    header=jwt.get_unverified_header(token)
    if header.get("alg")!="RS256":raise ValueError("algorithm")
    keys=[k for k in jwks["keys"] if k.get("kid")==header.get("kid") and k.get("kty")=="RSA" and k.get("use","sig")=="sig" and k.get("alg","RS256")=="RS256"]
    if len(keys)!=1:raise ValueError("key_id")
    claims=jwt.decode(token,jwt.PyJWK(keys[0]).key,algorithms=["RS256"],audience=client_id,issuer=issuer,options={"require":["iss","sub","aud","exp","iat","nonce"]},leeway=15)
    if claims.get("nonce")!=nonce or not isinstance(claims["sub"],str) or not 1<=len(claims["sub"])<=300:raise ValueError("nonce_or_subject")
    if (isinstance(claims["aud"],list) and len(claims["aud"])>1 or claims.get("azp")) and claims.get("azp")!=client_id:raise ValueError("authorized_party")
    return {"issuer":issuer,"subject":claims["sub"]}


async def finish(payload):
    issuer,client_id,secret=configuration(payload.get("demo",False))
    async with httpx.AsyncClient(trust_env=False,timeout=15,follow_redirects=False) as client:
        endpoints=await metadata(client,issuer)
        body={"grant_type":"authorization_code","client_id":client_id,"code":payload["code"],"redirect_uri":payload["redirect_uri"],"code_verifier":payload["verifier"]}
        if secret:body["client_secret"]=secret
        response=await client.post(endpoints["token_endpoint"],data=body);response.raise_for_status()
        token=response.json()["id_token"]
        response=await client.get(endpoints["jwks_uri"]);response.raise_for_status()
        result=verify(token,response.json(),issuer,client_id,payload["nonce"])
    result["local_demo"]=False
    return result
