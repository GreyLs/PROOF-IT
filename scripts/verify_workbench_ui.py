"""Real browser interactions for new workbench screens on desktop and mobile.

Disposable fixtures; actual ownership checks, notifications, task acceptance,
Docker execution and atomic import use the running API. LLM inference is covered
separately by verify_workbench_scenarios (no fake LLM route in this browser test).
"""
import json, time, uuid
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from psycopg.types.json import Jsonb
from scripts.workbench_test_fixture import Fixture
from scripts.check_proofit_ui import LAYOUT_CHECK, settle
from tests.test_workbench import VACANCY
ROOT=Path(__file__).resolve().parents[1]

def main():
    fixture=Fixture();out=ROOT/'validation/reports/current/ui';out.mkdir(parents=True,exist_ok=True)
    report={'checks':[],'browser_errors':[],'completed':False,'started_at':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    try:
        c,cu=fixture.register('candidate');e,eu=fixture.register('employer');v=e.post('/vacancies',json=VACANCY);v.raise_for_status();vid=v.json()['vacancy']['id']
        contract={'title':'Агрегация событий','prompt':'Вход: массив целых чисел. Верните сумму; пустой массив даёт ноль.','starter_code':'def solve(data):\n    pass','reference_solution':'def solve(data): return sum(data)','public_tests':[{'input':[1,2],'expected':3},{'input':[],'expected':0}],'hidden_tests':[{'input':[-1,2],'expected':1},{'input':[1,1],'expected':2},{'input':[9],'expected':9}]}
        fixture.db.execute("INSERT INTO career_messages(candidate_id,role,content) VALUES(%s,'user','Хочу перейти из разработки в аналитику'),(%s,'assistant',%s)",(cu['subject_id'],cu['subject_id'],'**План перехода**\n\n1. Начните с аудита переносимых навыков: Python, SQL и работа с данными.\n2. Выберите небольшой аналитический проект и подготовьте портфолио.'))
        with sync_playwright()as p:
            browser=p.chromium.launch()
            for width,height in [(1440,900),(390,844)]:
                tid='UT'+uuid.uuid4().hex
                fixture.db.execute('INSERT INTO micro_tasks(id,company_id,candidate_id,vacancy_id,title,prompt,contract) VALUES(%s,%s,%s,%s,%s,%s,%s)',(tid,eu['subject_id'],cu['subject_id'],vid,contract['title'],contract['prompt'],Jsonb(contract)))
                nid='UN'+uuid.uuid4().hex;fixture.db.execute("INSERT INTO notifications(id,user_id,kind,title,entity_id,vacancy_id) VALUES(%s,%s,'task.received','Новое тестовое по вакансии Python',%s,%s)",(nid,cu['id'],tid,vid))
                for role,client in [('candidate',c),('employer',e)]:
                    context=browser.new_context(viewport={'width':width,'height':height},extra_http_headers={'Authorization':client.headers['Authorization']});page=context.new_page()
                    page.on('pageerror',lambda error:report['browser_errors'].append(str(error)))
                    def capture(name):
                        settle(page);expect(page.locator('main h1').first).to_be_visible();r=page.evaluate(LAYOUT_CHECK);r.update(name=f'{role}-{name}-{width}',passed=not r['horizontal_overflow'] and not page.locator('.error-box:visible').count());report['checks'].append(r);page.screenshot(path=str(out/(r['name']+'.png')),full_page=False);assert r['passed'],r
                    page.goto(fixture.cfg['BASE_URL']+'/#overview');settle(page)
                    if role=='candidate':
                        page.goto(fixture.cfg['BASE_URL']+'/#career');expect(page.get_by_role('heading',name='Персональный hr-консультант')).to_be_visible();expect(page.locator('.career-advice strong')).to_have_text('План перехода');expect(page.locator('.career-advice li')).to_have_count(2);capture('career')
                        page.get_by_role('button',name='Уведомления',exact=True).click();expect(page.get_by_text('Новое тестовое по вакансии Python',exact=True).first).to_be_visible();capture('notification');page.get_by_text('Новое тестовое по вакансии Python',exact=True).first.click();settle(page)
                        page.locator('.practical-task').filter(has=page.get_by_role('button',name='Принять',exact=True)).last.get_by_role('button',name='Принять',exact=True).click();expect(page.get_by_label('Код решения')).to_be_visible();page.get_by_label('Код решения').fill('def solve(data):\n    return sum(data)');capture('sandbox')
                        page.get_by_role('button',name='Запустить автотесты',exact=True).click();expect(page.get_by_text('Автотесты: 2 из 2',exact=True)).to_be_visible(timeout=20000);capture('sandbox-run');page.get_by_role('button',name='Закрыть',exact=True).click()
                    else:
                        page.goto(fixture.cfg['BASE_URL']+'/#vacancies');settle(page);page.locator('.vacancy-card').first.get_by_role('button',name='Подробнее').click();expect(page.get_by_text('Потенциал найма',exact=True)).to_be_visible();capture('market-and-forecast');page.get_by_role('button',name='Закрыть',exact=True).click()
                        page.get_by_role('button',name='Создать по запросу',exact=True).click();capture('vacancy-generator');page.get_by_role('button',name='Закрыть',exact=True).click()
                        page.get_by_role('button',name='Загрузить до 50',exact=True).click();page.locator('input[type=file]').set_input_files(str(ROOT/'web/public/vacancy-import-example.json'));expect(page.get_by_text('1 вакансий готовы к проверке и загрузке',exact=True)).to_be_visible();capture('bulk-import');page.get_by_role('button',name='Проверить и загрузить',exact=True).click();expect(page.get_by_role('heading',name='Пакет вакансий')).not_to_be_visible(timeout=15000)
                    context.close()
            browser.close()
        report['completed']=True
    except Exception as exc:
        report['failure_type']=type(exc).__name__;raise
    finally:
        fixture.close();report['passed']=report['completed'] and not report['browser_errors'] and all(x['passed']for x in report['checks']);(ROOT/'validation/reports/current/workbench-ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'passed':report['passed'],'checks':len(report['checks']),'browser_errors':len(report['browser_errors'])}))
if __name__=='__main__':main()
