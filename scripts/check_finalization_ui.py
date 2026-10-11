"""Six-language authenticated cab/market flow, no LLM or external market reads."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from scripts.workbench_test_fixture import Fixture
from tests.test_resume_qualification import create_resume
from tests.test_workbench import VACANCY
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current'

def main():
 f=Fixture();checks=[];errors=[]
 try:
  c,cu=f.register('candidate');e,eu=f.register('employer')
  resume=create_resume(c,1).json()['resume'];v=e.post('/vacancies',json=VACANCY);v.raise_for_status();vacancy=v.json()['vacancy']
  c.post('/vacancies/'+vacancy['id']+'/apply',json={'resume_id':resume['id'],'message':'Синтетический UI-контроль фиксации прогноза.'}).raise_for_status()
  source=json.loads((ROOT/'web/src/locales/ru.json').read_text(encoding='utf-8'))
  with sync_playwright()as p:
   browser=p.chromium.launch(headless=True)
   for language in ('ru','en','kk','uz','az','be'):
    catalog=source if language=='ru' else json.loads((ROOT/f'web/src/locales/{language}.json').read_text(encoding='utf-8'))
    for role,client in (('candidate',c),('employer',e)):
     ctx=browser.new_context(viewport={'width':390 if language=='be' else 1280,'height':768},extra_http_headers={'Authorization':client.headers['Authorization']})
     ctx.add_init_script("localStorage.setItem('proofit.language',"+json.dumps(language)+")")
     page=ctx.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
     page.goto(f.cfg['BASE_URL']+'/proofit#research-lab');expect(page.locator('main h1')).to_be_visible(timeout=30000)
     assert page.locator('html').get_attribute('lang')==language
     if role=='employer':
      expect(page.get_by_role('heading',name=catalog['Проспективная проверка прогноза'],exact=True)).to_be_visible()
      assert not page.locator('.error-box:visible').count()
      if language=='ru':
       page.get_by_role('button',name='Обновить радар и двойника',exact=True).click()
       page.locator('label.field').filter(has=page.get_by_text('Участник текущего процесса',exact=True)).locator('select').select_option(cu['subject_id'])
       page.get_by_role('button',name='Зафиксировать прогноз до решения',exact=True).click()
       expect(page.get_by_text('Прогноз сохранён без возможности редактирования',exact=True)).to_be_visible(timeout=30000)
       page.get_by_role('button',name='Обновить отчёт проверки',exact=True).click()
       expect(page.get_by_text('Исключено синтетических записей: 1',exact=True)).to_be_visible(timeout=30000)
       assert not page.locator('.error-box:visible').count()
     else:
      expect(page.get_by_role('heading',name=catalog['Защита pull request'],exact=True)).to_be_visible()
     geometry=page.evaluate('''()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('main *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,8).map(e=>({tag:e.tagName,css:e.className,text:e.textContent.slice(0,150),right:e.getBoundingClientRect().right}))})''')
     if geometry['scroll']>geometry['width']+1:
      page.screenshot(path=str(OUT/f'finalization-overflow-{role}-{language}.png'),full_page=True)
      print(json.dumps({'language':language,'role':role,'geometry':geometry},ensure_ascii=False),flush=True)
     assert geometry['scroll']<=geometry['width']+1,geometry
     if language in ('ru','be'):page.screenshot(path=str(OUT/f'finalization-{role}-{language}.png'),full_page=True)
     checks.append({'language':language,'role':role,'no_overflow':True,'immutable_prediction_ui':role=='employer'and language=='ru'})
     ctx.close()
   browser.close()
  report={'passed':not errors,'generated_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'checks':checks,'browser_errors':errors,
   'llm_calls':0,'scope':'six-language role workspaces and one live synthetic forecast-freeze workflow; not human semantic QA or a real pilot'}
  (OUT/'finalization-ui.json').write_text(json.dumps(report,indent=2),encoding='utf-8');assert not errors
  print(json.dumps({'passed':True,'checks':len(checks),'js_errors':len(errors)}))
 finally:f.close()
if __name__=='__main__':main()
