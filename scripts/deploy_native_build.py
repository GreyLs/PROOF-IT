"""Replace only managed native APIs; preserve ingress and all data services."""
from pathlib import Path
import argparse,json,shutil,time,psutil
from urllib.parse import urlsplit
from dotenv import dotenv_values
from scripts.private_runtime import private_file
from scripts import start_local as runtime


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--from-build',required=True)
    args=parser.parse_args()
    source=(runtime.ROOT/args.from_build).resolve()
    target_root=(runtime.ROOT/'target').resolve()
    if not source.is_relative_to(target_root) or not source.is_file() or source.name!='fsp-trajectory.exe':
        raise RuntimeError('Expected a completed native build inside this checkout target directory')
    configuration=dict(dotenv_values(runtime.ROOT/'.env'))
    private_settings=private_file('public-settings.json')
    if private_settings.exists():
        values=json.loads(private_settings.read_text(encoding='utf-8'))
        if set(values)-{'BASE_URL','BIND_ADDR','FSP_OIDC_ISSUER','TRUST_CLOUDFLARE_LOCAL_TUNNEL'}:
            raise RuntimeError('Unexpected private runtime setting')
        configuration.update(values)
    names=[('api-'+role,role,f'127.0.0.1:{port}') for role,port in runtime.DOMAINS]
    names.append(('api-gateway','gateway',configuration['BIND_ADDR']))
    # Preserve the previous executable before touching any running process.
    backup=runtime.RUNTIME/'api-before-category-revision.exe'
    if runtime.API_BINARY.exists():shutil.copy2(runtime.API_BINARY,backup)
    for name,role,_ in names:
        runtime.managed(name,runtime.api_process(role),freshness=float('inf'))
    # Recover same-checkout listeners whose bookkeeping PID file was lost.
    # Matching a process name alone is insufficient ownership evidence.
    roles={role for _,role,_ in names}
    for process in psutil.process_iter():
        try:
            owned=(Path(process.exe()).resolve()==runtime.API_BINARY
                   and Path(process.cwd()).resolve()==runtime.ROOT
                   and len(process.cmdline())==1
                   and process.environ().get('FSP_SERVICE') in roles)
            if owned:
                role=process.environ()['FSP_SERVICE']
                runtime.stop_process(process)
                print('Recovered same-checkout '+role+' listener without a PID record')
        except (psutil.NoSuchProcess,psutil.AccessDenied,OSError):
            continue
    shutil.copy2(source,runtime.API_BINARY)
    for name,role,bind in names:
        runtime.fresh_api(name,role,bind,configuration)
        for _ in range(80):
            if runtime.alive('http://'+bind+'/api/health',urlsplit(configuration['BASE_URL']).netloc):break
            time.sleep(.25)
        else:raise RuntimeError('Native service did not become ready: '+role)
    print('Native APIs healthy; ingress connector and database were not restarted.')

if __name__=='__main__':main()
