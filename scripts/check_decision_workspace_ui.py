"""Authenticated decision-workspace browser checks with exact-ID fixture cleanup."""
import json,time,uuid
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from psycopg.types.json import Jsonb
from scripts.workbench_test_fixture import Fixture
from tests.test_resume_qualification import create_resume
from tests.test_workbench import VACANCY

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current'

def main():
    f=Fixture();checks=[];errors=[]
    try:
        c,cu=f.register('candidate');e,eu=f.register('employer')
        response=create_resume(c,1);response.raise_for_status();resume=response.json()['resume']
        vacancy=e.post('/vacancies',json=VACANCY);vacancy.raise_for_status()
        cert='GUI_CERT'+uuid.uuid4().hex
        f.db.execute("UPDATE candidates SET consent_publication=true WHERE id=%s",(cu['subject_id'],))
        f.db.execute("UPDATE resume_profiles SET status='published',visibility='employer_searchable' WHERE id=%s",(resume['id'],))
        f.db.execute("INSERT INTO qualification_certificates(id,candidate_id,resume_id,specialization,grade,skills,assessment_version,attempt,scope) VALUES(%s,%s,%s,'backend_python','middle',%s,'ui-fixture',%s,'role-knowledge')",(cert,cu['subject_id'],resume['id'],Jsonb(['Python']),Jsonb({'scope':'synthetic UI provenance fixture, not a professional certification'})))
        e.put('/intelligence/evidence-lab/company-twin',json={'collaboration':'independent','pace':'dynamic','growth':'leadership','response_days':4,'interview_stages':2}).raise_for_status()
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            for width,height in ((1440,900),(1280,768),(1024,600),(390,844)):
                for role,client in (('candidate',c),('employer',e)):
                    ctx=browser.new_context(viewport={'width':width,'height':height},extra_http_headers={'Authorization':client.headers['Authorization']})
                    page=ctx.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f.cfg['BASE_URL']+'/proofit#horizon')
                    expect(page.locator('.twin-overview')).to_be_visible(timeout=30000)
                    assert page.locator('.sidebar [data-nav-group]').count()==7
                    if width<700:page.get_by_role('button',name='Меню',exact=True).click()
                    geometry=page.locator('.sidebar').evaluate('(e)=>({height:e.clientHeight,scroll:e.scrollHeight,last:e.querySelector(\"[data-nav-group=settings]\").getBoundingClientRect().bottom})')
                    assert geometry['scroll']<=geometry['height']+1,geometry
                    assert geometry['last']<=height,geometry
                    if width<700:page.locator('.sidebar-backdrop').click(position={'x':width-10,'y':30})
                    expect(page.locator('.section-tabs button[aria-current=page]')).to_have_text('Сценарии и сроки')
                    if width in (1440,390):
                        page.get_by_role('button',name='Рассчитать сценарий',exact=True).click()
                        expect(page.locator('.twin-comparison')).to_be_visible(timeout=60000)
                        assert page.locator('.twin-comparison .twin-compare-grid article').count()==2
                        page.get_by_text('Допущения, происхождение и границы результата',exact=True).click()
                        expect(page.get_by_text('Базовый процесс модели:',exact=False)).to_be_visible()
                    page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(120)
                    page.screenshot(path=str(OUT/f'decision-twin-{role}-{width}.png'),full_page=True)
                    if role=='candidate':
                        page.locator('.section-tabs').get_by_role('button',name='Граф доказательств',exact=True).click()
                        expect(page.locator('.graph-explorer')).to_be_visible(timeout=30000)
                        assert page.locator('.sidebar [data-nav-group=twin][aria-current=page]').count()==1
                        page.get_by_label('Найти навык в графе',exact=True).fill('python')
                        expect(page.locator('.graph-source-card').filter(has_text=cert)).to_be_visible()
                        page.get_by_label('Найти навык в графе',exact=True).fill('sql')
                        expect(page.locator('.graph-path-title>.gap')).to_be_visible()
                        page.get_by_label('Найти навык в графе',exact=True).fill('')
                        page.evaluate('window.scrollTo(0,0)');page.wait_for_timeout(120)
                        page.screenshot(path=str(OUT/f'decision-graph-{width}.png'),full_page=True)
                        if width==1440:
                            source=page.locator('.proof-evidence').filter(has_text='cert:'+cert)
                            # The management panel has a human title; select its checkbox by source title.
                            source=page.locator('.proof-evidence').filter(has_text='Квалификация: backend_python')
                            source.get_by_label('Показывать',exact=True).click()
                            expect(page.get_by_text('Скрыто · не участвует в графе',exact=True)).to_be_visible(timeout=30000)
                            public=e.get('/intelligence/graph/candidate/'+cu['subject_id']);public.raise_for_status()
                            assert not any(item['id']=='cert:'+cert for item in public.json().get('evidence_inventory',[]))
                            source=page.locator('.proof-evidence').filter(has_text='Квалификация: backend_python')
                            source.get_by_label('Показывать',exact=True).click()
                            expect(page.get_by_text('Скрыто · не участвует в графе',exact=True)).to_have_count(0)
                    else:
                        page.locator('.section-tabs').get_by_role('button',name='Команда и доказательства',exact=True).click()
                        expect(page.locator('.twin-purpose')).to_be_visible(timeout=30000)
                        expect(page.get_by_role('combobox',name='Взаимодействие',exact=True)).to_have_value('independent')
                        expect(page.get_by_role('combobox',name='Темп',exact=True)).to_have_value('dynamic')
                    assert not page.locator('.error-box:visible').count()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    checks.append({'role':role,'width':width,'height':height,'sidebar_groups':7,'sidebar_no_scroll':True,'scoped_tabs':True,'explained_workspace':True,'page_overflow':False})
                    if width==1440:
                        page.set_viewport_size({'width':1280,'height':600})
                        for language in ('en','kk'):
                            page.goto(f.cfg['BASE_URL']+'/proofit#horizon')
                            expect(page.locator('.twin-overview')).to_be_visible()
                            page.locator('.language-trigger').click();page.locator('[data-language='+language+']').click()
                            translations=json.loads((ROOT/f'web/src/locales/{language}.json').read_text(encoding='utf-8'))
                            key='Проверьте решение до изменения условий найма' if role=='employer' else 'Проверьте карьерный шаг до изменения своих условий'
                            expect(page.locator('.twin-overview h2')).to_have_text(translations[key])
                            assert page.locator('.sidebar').evaluate('(e)=>e.scrollHeight<=e.clientHeight+1')
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                            assert page.locator('.sidebar [data-nav-group]').count()==7
                            checks.append({'role':role,'language':language,'width':1280,'height':600,'translated_new_heading':True,'sidebar_no_scroll':True})
                    ctx.close()
            browser.close()
        report={'passed':not errors,'generated_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'checks':checks,'browser_errors':errors,'llm_calls':0,'scope':'auth fixtures + real scenario jobs, graph provenance, hide/restore/public filtering, saved employer context and responsive navigation; no load or general ranking rerun'}
        (OUT/'decision-workspace-ui.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({'passed':report['passed'],'checks':len(checks),'browser_errors':len(errors)}));assert not errors
    finally:f.close()

if __name__=='__main__':main()
