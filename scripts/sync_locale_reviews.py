"""Record completed agent authoring/review, preserving corrected translations.

Explicit languages only. This is not a translation or native-human review tool;
catalog/source hashes invalidate the review when any asset changes.
"""
import argparse
import hashlib
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'web/src/locales'

def digest(value):
 return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--reviewed-languages',nargs='+',choices=['uz','az','be'],required=True)
 args=parser.parse_args()
 source=json.loads((FOLDER/'ru.json').read_text(encoding='utf-8'))
 path=FOLDER/'agent-reviews.json'
 metadata=json.loads(path.read_text(encoding='utf-8'))if path.exists()else{'schema_version':1,'languages':{}}
 for lang in args.reviewed_languages:
  catalog=json.loads((FOLDER/(lang+'.json')).read_text(encoding='utf-8'))
  assert set(catalog)==set(source)and all(isinstance(v,str)and v.strip()for v in catalog.values())
  metadata['languages'][lang]={'source_sha256':digest(source),'catalog_sha256':digest(catalog),
   'scope':'full_static_catalog','reviewer_kind':'agent','independent_human_review':False,
   'reviewed_at':datetime.now(timezone.utc).isoformat()}
 path.write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
 from scripts import prepare_ui_translations as preparation
 importlib.reload(preparation)
 for lang in preparation.NAMES:
  catalog=json.loads((FOLDER/(lang+'.json')).read_text(encoding='utf-8'))
  preparation.write_qa_status(source,lang,catalog)
  invalid={k:preparation.problems(source[k],v,lang)for k,v in catalog.items()if preparation.problems(source[k],v,lang)}
  assert not invalid,invalid
 status=json.loads((FOLDER/'qa-status.json').read_text(encoding='utf-8'))
 print(json.dumps({lang:{key:row[key]for key in ('catalog_key_count','missing_key_count','critical_ready','semantic_ready','independent_human_review')}for lang,row in status['languages'].items()}))

if __name__=='__main__':main()
