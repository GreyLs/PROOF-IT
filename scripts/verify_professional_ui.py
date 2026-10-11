"""Live candidate/employer/browser and actual Qwen draft flow, no load test."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from intelligence import professional as cat
from scripts.workbench_test_fixture import Fixture
from scripts.check_proofit_ui import LAYOUT_CHECK,settle

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current'

def main():
    f=Fixture();report={'checks':[],'browser_errors':[],'capacity_test_run':False,'started_at':time.strftime('%Y-%m-%dT%H:%M:%S%z')};shots=OUT/'ui';shots.mkdir(parents=True,exist_ok=True)
    try:
        c,cu=f.register('candidate');e,eu=f.register('employer');reviewer,ru=f.register('employer')
        started=time.perf_counter();r=e.post('/intelligence/assessment/drafts/generate',json={'specialization':'backend_python','topic':'Транзакционная идемпотентность API'});r.raise_for_status();jobid=r.json()['job_id']
        for _ in range(360):
            job=e.get('/intelligence/jobs/'+jobid).json()
            if job['status'] in ('done','failed'):break
            time.sleep(1)
        assert job['status']=='done',job
        report['qwen_draft']={'model':job['result']['execution']['model'],'seconds':round(time.perf_counter()-started,3),'passed':True,'automatic_activation':False}
        with sync_playwright() as p:
            browser=p.chromium.launch()
            for width,height in ((1440,1000),(390,844)):
                for role,client,route in [('candidate',c,'professional-assessment'),('employer',reviewer,'assessment-lab')]:
                    ctx=browser.new_context(viewport={'width':width,'height':height})
                    ctx.add_cookies([{'name':'fsp_session','value':client.headers['Authorization'][7:],'url':f.cfg['BASE_URL']+'/','httpOnly':True,'sameSite':'Strict'}])
                    page=ctx.new_page();page.on('pageerror',lambda err:report['browser_errors'].append(str(err)))
                    def callback_response(response):
                        if '/oidc/callback' in response.url:report['callback_http_status']=response.status
                    page.on('response',callback_response)
                    page.goto(f.cfg['BASE_URL']+'/#'+route);settle(page)
                    if role=='candidate':
                        if width==1440:
                            page.get_by_role('button',name='Начать оценку',exact=True).click()
                            expect(page.get_by_role('radiogroup')).to_be_visible()
                            layout=page.evaluate(LAYOUT_CHECK);assert not layout['horizontal_overflow'],layout
                            page.screenshot(path=str(shots/f'assessment-question-{width}.png'))
                            for _ in range(8):
                                row=f.db.execute("SELECT id,contract FROM intelligence.professional_attempts WHERE user_id=%s AND status='active'",(cu['id'],)).fetchone();q=cat.next_item(row[1]);page.get_by_role('radio').nth(q['correct']).check();page.get_by_role('button',name='Ответить',exact=True).click()
                                if _<7:expect(page.get_by_text(f'Вопрос {_+2} ·',exact=False)).to_be_visible()
                            expect(page.get_by_role('heading',name='Ваш профиль:',exact=False)).to_be_visible()
                        else:
                            page.locator('.cat-history button').first.click();expect(page.locator('.cat-result')).to_be_visible()
                    else:
                        page.get_by_label('Кого ищете',exact=True).fill('Нужен Аналитика данных. Middle, SQL, Python, Pandas. 180–250 тыс руб. Удалённо.')
                        page.get_by_role('button',name='Разобрать потребность',exact=True).click();expect(page.locator('.cat-preview h3')).to_have_text('Аналитика данных')
                        if width==1440:
                            page.locator('.cat-editor summary').first.click()
                            page.get_by_label('Заключение эксперта',exact=True).first.fill('Однозначность и соответствие профессиональной теме проверены. Допуск к пилоту.')
                            page.get_by_role('button',name='Сохранить проверку и принять в пилот',exact=True).first.click();expect(page.locator('.cat-drafts').get_by_text('Пилот',exact=True)).to_be_visible()
                    settle(page);layout=page.evaluate(LAYOUT_CHECK);layout.update(name=f'{role}-{route}-{width}',passed=not layout['horizontal_overflow'] and not page.locator('.error-box:visible').count());report['checks'].append(layout);page.screenshot(path=str(shots/(layout['name']+'.png')));assert layout['passed'],layout
                    if role=='candidate' and width==1440:
                        page.get_by_role('button',name='Привязать ФСП ID',exact=True).click();expect(page.get_by_role('heading',name='Привязка ФСП ID')).to_be_visible();page.get_by_role('link',name='Продолжить локальную проверку').click();page.wait_for_url('**/#professional-assessment');expect(page.get_by_role('button',name='Обновить привязку',exact=True)).to_be_visible();report['oidc_browser_redirect']=True
                    ctx.close()
            # Guest login exercises actual session cookies, not fixture tokens.
            ctx=browser.new_context(viewport={'width':390,'height':844});page=ctx.new_page();page.goto(f.cfg['BASE_URL']);settle(page)
            page.get_by_role('button',name='Попробовать экспресс-оценку',exact=True).click();expect(page.get_by_role('radiogroup')).to_be_visible(timeout=20000)
            guest=page.request.get(f.cfg['BASE_URL']+'/api/auth/me').json()['user'];f.users.append(guest)
            page.get_by_role('button',name='Удалить гостевой профиль',exact=True).click();expect(page.get_by_role('button',name='Попробовать экспресс-оценку',exact=True)).to_be_visible();report['guest_entry_and_deletion']=True
            ctx.close();browser.close()
        report['passed']=all(x['passed'] for x in report['checks']) and not report['browser_errors']
    except Exception as error:
        from urllib.parse import urlsplit
        if 'page' in locals():
            report['last_browser_path']=urlsplit(page.url).path+'#'+urlsplit(page.url).fragment
            try:report['visible_error']=page.locator('body').inner_text()[:300] if '/oidc/callback' in page.url else None
            except Exception:pass
        report['passed']=False;report['error']=type(error).__name__+': '+str(error)[:1200];raise
    finally:
        f.db.execute('DELETE FROM intelligence.item_drafts WHERE author_id=ANY(%s) OR reviewer_id=ANY(%s)',([u['id'] for u in f.users],[u['id'] for u in f.users]));f.close();(OUT/'professional-browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k not in ('checks','browser_errors')}),flush=True)

if __name__=='__main__':main()
