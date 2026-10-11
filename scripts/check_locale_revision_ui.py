"""Exact catalog gates and browser language persistence; not full human QA."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from scripts.workbench_test_fixture import Fixture
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current'
def main():
    qa=json.loads((ROOT/'web/src/locales/qa-status.json').read_text(encoding='utf-8'));source=json.loads((ROOT/'web/src/locales/ru.json').read_text(encoding='utf-8'));checks=[];errors=[]
    ready=['ru']
    for lang in ('en','kk','uz','az','be'):
        catalog=json.loads((ROOT/f'web/src/locales/{lang}.json').read_text(encoding='utf-8'));status=qa['languages'][lang]
        exact=set(catalog)==set(source)
        if exact and status.get('critical_ready') and not status['structural_invalid_keys']:ready.append(lang)
        assert status['catalog_key_count']==len(catalog) and status['source_key_count']==len(source)
    f=Fixture()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f.cfg['BASE_URL']+'/proofit');page.wait_for_selector('.login-page')
            for lang in ready:
                page.locator('input[autocomplete=username]').fill('unchanged-user@example.test')
                page.locator('input[autocomplete=current-password]').fill('local-test-value-no-login')
                page.locator('.language-trigger').click()
                assert page.locator('[data-language]').count()==len(ready)
                page.locator('[data-language='+lang+']').click()
                assert page.locator('html').get_attribute('lang')==lang
                expected=source['Войти в кабинет'] if lang=='ru' else json.loads((ROOT/f'web/src/locales/{lang}.json').read_text(encoding='utf-8'))['Войти в кабинет']
                expect(page.get_by_role('button',name=expected,exact=True)).to_be_visible()
                assert page.locator('input[autocomplete=username]').input_value()=='unchanged-user@example.test'
                assert page.locator('input[autocomplete=current-password]').input_value()=='local-test-value-no-login'
                page.reload();page.wait_for_selector('.login-page');assert page.locator('html').get_attribute('lang')==lang
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
                checks.append({'language':lang,'persisted':True,'critical_login_copy':True,'input_unchanged':True})
            browser.close()
        report={'passed':not errors,'generated_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'ready_languages':ready,'disabled_drafts':[k for k in ('uz','az','be') if k not in ready],'checks':checks,'browser_errors':errors,'scope':'static UI catalog structure + selected auth strings + browser switching/persistence, not independent full semantic review','independent_human_review':False}
        (OUT/'locale-ui.json').write_text(json.dumps(report,indent=2),encoding='utf-8');assert not errors;print(json.dumps(report))
    finally:f.close()
if __name__=='__main__':main()
