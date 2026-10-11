"""Package current, non-ignored repository files; never include runtime secrets."""
from pathlib import Path
import hashlib,json,subprocess
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1]
def main():
 from scripts.check_publication_privacy import check
 check()
 names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
 files=sorted({n for n in names if n and (ROOT/n).is_file() and not n.startswith(('runtime/','.env','target/','.tools/'))})
 output=ROOT/'runtime/proofit-source.zip';output.parent.mkdir(exist_ok=True)
 manifest={}
 with ZipFile(output,'w',ZIP_DEFLATED,compresslevel=6) as archive:
  for name in files:
   path=(ROOT/name).resolve();assert path.is_relative_to(ROOT.resolve());manifest[name]=hashlib.sha256(path.read_bytes()).hexdigest();archive.write(path,'proofit/'+name)
  archive.writestr('proofit/source-manifest.json',json.dumps(manifest,indent=2))
 print('Current source archive:',output,'files:',len(files))
if __name__=='__main__':main()
