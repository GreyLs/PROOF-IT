from scripts.private_runtime import private_file
"""Update exact OIDC redirect URLs through the real local Keycloak Admin API."""
from pathlib import Path
import httpx,json,time
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
def main():
 cfg=dotenv_values(private_file('keycloak.env'));origin=cfg['PROOFIT_PUBLIC_ORIGIN'];base='http://127.0.0.1:9091/identity'
 with httpx.Client(trust_env=False,timeout=15) as c:
  for _ in range(90):
   try:
    r=c.post(base+'/realms/master/protocol/openid-connect/token',data={'client_id':'admin-cli','grant_type':'password','username':'proofit-operator','password':cfg['PROOFIT_KC_ADMIN_PASSWORD']});r.raise_for_status();break
   except (httpx.HTTPError):time.sleep(.5)
  else:raise SystemExit('Keycloak is not ready')
  c.headers['Authorization']='Bearer '+r.json()['access_token']
  r=c.get(base+'/admin/realms/proofit/clients',params={'clientId':'proofit'});r.raise_for_status();client=r.json()[0]
  client.update(redirectUris=[origin+'/api/intelligence/assessment/oidc/callback'],webOrigins=[origin],rootUrl=origin,baseUrl=origin)
  c.put(base+'/admin/realms/proofit/clients/'+client['id'],json=client).raise_for_status()
  c.put(base+'/admin/realms/proofit',json={'sslRequired':'external' if origin.startswith('https://') else 'none'}).raise_for_status()
 print('Real Keycloak origin and exact OIDC redirects configured:',origin)
if __name__=='__main__':main()
