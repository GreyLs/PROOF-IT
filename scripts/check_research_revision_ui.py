"""Live Chromium scenarios with disposable authenticated data; no LLM scoring."""
import json,time,uuid
from pathlib import Path
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row
from playwright.sync_api import sync_playwright,expect
from scripts.workbench_test_fixture import Fixture
from tests.test_resume_qualification import create_resume
from tests.test_workbench import VACANCY
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current'

def main():
    f=Fixture();checks=[];errors=[]
    try:
        f.db.row_factory=dict_row;c,cu=f.register('candidate');e,eu=f.register('employer')
        resume=create_resume(c,1).json()['resume'];v=e.post('/vacancies',json=VACANCY);v.raise_for_status();vacancy=v.json()['vacancy']
        c.post('/vacancies/'+vacancy['id']+'/apply',json={'resume_id':resume['id'],'message':'Контрольный отклик синтетической fixture, без контактов.'}).raise_for_status()
        id='GUI'+uuid.uuid4().hex
        questions=[{'id':str(i),'criterion':k,'file':'api.py','hunk':'@@ -1 +1 @@','code_excerpt':'return checked','prompt':'Объясните конкретные изменения и проверку результата.'} for i,k in enumerate(('correctness','testing','design','delivery'))]
        snapshot={'url':'https://github.com/psf/requests/pull/519','author_login':'fixture','coverage':{'files_received':1,'files_total':1,'commits_received':1,'commits_total':1,'discussions_complete':True}}
        f.db.execute("INSERT INTO intelligence.github_defenses(id,user_id,resume_id,specialization,target_grade,repository,pr_number,head_sha,artifact_digest,snapshot,questions) VALUES(%s,%s,%s,'backend_python','middle','psf/requests',519,%s,%s,%s,%s)",(id,cu['id'],resume['id'],'a'*40,'b'*64,Jsonb(snapshot),Jsonb(questions)))
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            for width in (390,1440):
                for role,client in (('candidate',c),('employer',e)):
                    ctx=browser.new_context(viewport={'width':width,'height':1000},extra_http_headers={'Authorization':client.headers['Authorization']})
                    page=ctx.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f.cfg['BASE_URL']+'/proofit#research-lab');expect(page.locator('main h1')).to_be_visible(timeout=30000)
                    if role=='candidate':
                        expect(page.get_by_text('Защита pull request',exact=True)).to_be_visible()
                        if width==1440:
                            for criterion in ('correctness','testing','design','delivery'):page.get_by_label(criterion,exact=True).fill('Самостоятельное пояснение для контрольной fixture; проверены инварианты, тесты, альтернативы и ограничения.')
                            page.get_by_role('button',name='Отправить защиту',exact=True).click();expect(page.get_by_text('submitted',exact=True)).to_be_visible(timeout=30000)
                    else:
                        page.get_by_role('button',name='Обновить радар и двойника',exact=True).click();expect(page.get_by_text('Ролевой рынок платформы',exact=True)).to_be_visible(timeout=30000)
                        expect(page.get_by_text('Консервативный индекс:',exact=False)).to_be_visible()
                    assert not page.locator('.error-box:visible').count()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    page.screenshot(path=str(OUT/f'research-{role}-{width}.png'),full_page=True)
                    checks.append({'role':role,'width':width,'layout':True,'cabinet_guard':True});ctx.close()
            browser.close()
        assert f.db.execute('SELECT status FROM intelligence.github_defenses WHERE id=%s',(id,)).fetchone()['status']=='submitted'
        report={'passed':not errors,'generated_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'checks':checks,'browser_errors':errors,'scope':'real Rust UI with isolated synthetic artifact fixture; public GitHub transport measured separately','llm_calls':0}
        (OUT/'research-ui.json').write_text(json.dumps(report,indent=2),encoding='utf-8');assert not errors;print(json.dumps({'passed':True,'checks':len(checks),'js_errors':len(errors)}))
    finally:f.close()

if __name__=='__main__':main()
