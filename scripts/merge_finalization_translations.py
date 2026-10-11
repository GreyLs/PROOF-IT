"""Mechanical merge of explicitly authored UI phrases. No translation service."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 phrases=json.loads((ROOT/'scripts/finalization_ui_translations.json').read_text(encoding='utf-8'))
 for language in ('ru','en','kk','uz','az','be'):
  path=ROOT/'web/src/locales'/(language+'.json')
  catalog=json.loads(path.read_text(encoding='utf-8'))
  catalog.update({source:source if language=='ru' else values[language]for source,values in phrases.items()})
  path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'authored_additional_keys':len(phrases),'languages':6}))
if __name__=='__main__':main()
