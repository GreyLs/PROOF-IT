"""Stop only this workspace's collector/stack; preserve volumes and secrets."""
import argparse
from pathlib import Path
import shutil
import subprocess
import psutil

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--collector-only', action='store_true')
    args = parser.parse_args()
    pidfile = ROOT / 'runtime/monitoring/exporter.pid'
    if pidfile.exists():
        try:
            process = psutil.Process(int(pidfile.read_text().strip()))
            command = process.cmdline()
            if 'scripts.monitoring_exporter' not in command or Path(process.cwd()).resolve() != ROOT:
                raise RuntimeError('Refusing to stop an unrelated/reused PID')
            process.terminate()
            process.wait(timeout=10)
        except psutil.NoSuchProcess:
            pass
    if not args.collector_only:
        docker = shutil.which('docker') or 'C:/Program Files/Docker/Docker/resources/bin/docker.exe'
        subprocess.run([docker, 'compose', '-f', 'deploy/monitoring/compose.yml', 'stop'], cwd=ROOT, check=True)
    print('Monitoring stopped; data volumes, database role and private secrets preserved.')

if __name__ == '__main__':
    main()
