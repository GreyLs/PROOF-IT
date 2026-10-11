"""Rebuild and restart only the APIs owned by the current service checkout."""
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.start_local import DOMAINS,api_process,managed,old_single_api

def main():
    old_single_api()
    for role in ['gateway']+[r for r,_ in DOMAINS]:
        managed('api-'+role,api_process(role),time.time()+1)
    try:
        subprocess.run(['cargo','build','--release','--locked'],cwd=ROOT,check=True)
    finally:
        # If compilation fails, the previously valid binary remains available.
        subprocess.run([sys.executable,str(ROOT/'scripts/start_local.py')],cwd=ROOT,check=True)

if __name__=='__main__':main()
