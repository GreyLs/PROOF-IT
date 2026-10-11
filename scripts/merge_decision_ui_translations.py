"""Merge reviewed bilingual UI assets without calling a generative service."""
import json
from pathlib import Path
from scripts.prepare_ui_translations import FOLDER,problems,write_qa_status

def main():
    additions=json.loads((Path(__file__).parent/'decision_ui_translations.json').read_text(encoding='utf-8'))
    source=json.loads((FOLDER/'ru.json').read_text(encoding='utf-8'))
    for key in additions:source[key]=key
    (FOLDER/'ru.json').write_text(json.dumps(source,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    results={}
    for language in ('en','kk','uz','az','be'):
        path=FOLDER/(language+'.json');catalog=json.loads(path.read_text(encoding='utf-8'))
        if language in ('en','kk'):
            for key,values in additions.items():
                assert not problems(key,values[language],language),(key,problems(key,values[language],language))
                catalog[key]=values[language]
            path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        write_qa_status(source,language,catalog)
        results[language]={'translated_keys':len(catalog),'source_keys':len(source)}
    print(json.dumps({'merged_pairs':len(additions),'languages':results}))

if __name__=='__main__':main()
