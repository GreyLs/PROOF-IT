from scripts.private_runtime import private_file
"""Provision a local demonstration identity through the real Keycloak Admin API."""
from pathlib import Path
import secrets
import httpx
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]
def main():
 cfg=dotenv_values(private_file('keycloak.env'));base='http://127.0.0.1:9091/identity'
 with httpx.Client(trust_env=False,timeout=30) as c:
  r=c.post(base+'/realms/master/protocol/openid-connect/token',data={'client_id':'admin-cli','grant_type':'password','username':'proofit-operator','password':cfg['PROOFIT_KC_ADMIN_PASSWORD']});r.raise_for_status();c.headers['Authorization']='Bearer '+r.json()['access_token']
  path=ROOT/'runtime/keycloak-demo.secret';password=path.read_text() if path.exists() else secrets.token_urlsafe(28)+'Aa1'
  users=c.get(base+'/admin/realms/proofit/users',params={'username':'proofit-demo','exact':'true'});users.raise_for_status()
  if not users.json():
   r=c.post(base+'/admin/realms/proofit/users',json={'username':'proofit-demo','enabled':True,'email':'proofit-demo@example.invalid','emailVerified':True,'firstName':'Proofit','lastName':'Demo'});r.raise_for_status()
   users=c.get(base+'/admin/realms/proofit/users',params={'username':'proofit-demo','exact':'true'});users.raise_for_status()
  uid=users.json()[0]['id'];r=c.put(base+'/admin/realms/proofit/users/'+uid+'/reset-password',json={'type':'password','value':password,'temporary':False});r.raise_for_status();path.write_text(password,encoding='ascii')
  print('Keycloak demonstration identity provisioned. Username: proofit-demo. Password retained only in ignored runtime/keycloak-demo.secret.')
if __name__=='__main__':main()
