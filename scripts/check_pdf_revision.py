"""Validate generated PDF geometry, searchable text, links and manifest bindings."""
import hashlib,json,time
from pathlib import Path
import pymupdf

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'validation/reports/current'

def main():
    report=json.loads((OUT/'pdf-documentation.json').read_text(encoding='utf-8'))
    source=json.loads((OUT/'source-manifest.json').read_text(encoding='utf-8'))
    checks=[];problems=[];preview=None
    assert report['source_fingerprint']==source['source_fingerprint']
    for item in report['documents']:
        path=ROOT/item['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
        with pymupdf.open(path) as pdf:
            characters=0;spans=0;links=0
            for number,page in enumerate(pdf):
                text=page.get_text();characters+=len(text)
                for block in page.get_text('dict')['blocks']:
                    for line in block.get('lines',[]):
                        for span in line['spans']:
                            if not span['text'].strip():continue
                            spans+=1;x0,y0,x1,y1=span['bbox']
                            if x0 < -1 or y0 < -1 or x1 > page.rect.width+1 or y1 > page.rect.height+1:
                                problems.append({'document':item['file'],'page':number+1,'bbox':span['bbox'],'text':span['text'][:100]})
                for link in page.get_links():
                    uri=link.get('uri')
                    if uri:
                        links+=1
                        assert uri.startswith('https://'),(item['file'],number+1,uri)
                if path.name.startswith('12_') and preview is None and number>0:
                    preview=OUT/'pdf-research-layout.png';page.get_pixmap(matrix=pymupdf.Matrix(1.4,1.4)).save(preview)
                for filename,heading in [('pdf-architecture-layout.png','КОМПОНЕНТЫ И ГРАНИЦЫ ДОВЕРИЯ'),('pdf-runtime-layout.png','ОЧЕРЕДИ, СЕКРЕТЫ И ВЫЧИСЛИТЕЛЬНАЯ ИЗОЛЯЦИЯ'),('pdf-interaction-layout.png','ЗАЩИТА ПУБЛИЧНОГО PR: ВЗАИМОДЕЙСТВИЯ'),('pdf-twin-layout.png','ЦИКЛ ЦИФРОВОГО ДВОЙНИКА: ОТ ФАКТА К ДЕЙСТВИЮ')]:
                    if not path.name.startswith('00_') and heading in text:
                        page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(OUT/filename)
            assert characters>4000 and len(pdf)==item['pages']
            checks.append({'document':item['file'],'pages':len(pdf),'text_spans':spans,'https_links':links,'hash_verified':True})
    result={'passed':not problems,'generated_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'source_fingerprint':source['source_fingerprint'],'documents':checks,'out_of_page_text':problems,'scope':'PDF page geometry, searchable text, HTTPS link format and exact generated-file digests; not a new empirical model validation'}
    (OUT/'pdf-layout.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'documents':len(checks),'pages':sum(item['pages'] for item in checks),'out_of_page_text':len(problems)}))
    assert not problems

if __name__=='__main__':main()
