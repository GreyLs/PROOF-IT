"""An outbound HTTPS connector for this checkout. No inbound firewall changes."""
from pathlib import Path
import hashlib,json,re,subprocess,time,urllib.request
import psutil
from scripts.private_runtime import private_dir, private_file
ROOT=Path(__file__).resolve().parents[1]
VERSION='2026.10.0'
SHA256='86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c'

def main():
 runtime=private_dir()
 exe=ROOT/'.tools'/('cloudflared-'+VERSION+'.exe');exe.parent.mkdir(exist_ok=True)
 if not exe.exists():
  urllib.request.urlretrieve('https://github.com/cloudflare/cloudflared/releases/download/'+VERSION+'/cloudflared-windows-amd64.exe',exe)
 if hashlib.sha256(exe.read_bytes()).hexdigest()!=SHA256:raise SystemExit('Connector integrity mismatch')
 pidfile=runtime/'public-tunnel.pid';record=runtime/'public-link.json'
 if pidfile.exists() and record.exists():
  try:
   process=psutil.Process(int(pidfile.read_text()))
   if Path(process.exe()).resolve()==exe.resolve():
    print(json.loads(record.read_text())['url']);return
  except (psutil.Error,ValueError):pass
 log=runtime/'public-tunnel.log'
 with log.open('wb') as f:
  process=subprocess.Popen([str(exe),'tunnel','--no-autoupdate','--protocol','http2','--url','http://127.0.0.1:1717'],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=f,stderr=f,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 pidfile.write_text(str(process.pid))
 for _ in range(120):
  if process.poll() is not None:raise SystemExit('Connector stopped; inspect private ingress log')
  match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',log.read_text(encoding='utf-8',errors='replace'))
  if match:break
  time.sleep(.25)
 else:raise SystemExit('No public origin received; inspect private ingress log')
 origin=match.group(0)
 record.write_text(json.dumps({'origin':origin,'url':origin+'/proofit','temporary':True,'requires_running_computer_and_connector':True,'connector_version':VERSION,'connector_sha256':SHA256},indent=2),encoding='utf-8')
 (runtime/'public-settings.json').write_text(json.dumps({'BASE_URL':origin,'BIND_ADDR':'127.0.0.1:1717','FSP_OIDC_ISSUER':origin+'/identity/realms/proofit','TRUST_CLOUDFLARE_LOCAL_TUNNEL':'true'},indent=2),encoding='utf-8')
 from dotenv import dotenv_values
 envfile=runtime/'keycloak.env';cfg=dotenv_values(envfile)
 cfg['PROOFIT_PUBLIC_ORIGIN']=origin
 envfile.write_text('\n'.join(k+'='+v for k,v in cfg.items())+'\n',encoding='utf-8')
 print('HTTPS interface:',origin+'/proofit')
 print('Next: recreate Keycloak with private ingress keycloak.env; configure_keycloak_origin; start_local --cpu-only')
if __name__=='__main__':main()
