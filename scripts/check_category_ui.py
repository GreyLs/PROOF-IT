"""Chromium: persisted eligibility, reused translations and responsive cards."""
import json,time,uuid
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from scripts.workbench_test_fixture import Fixture

ROOT=Path(__file__).resolve().parents[1]

def main():
    f=Fixture(local_transport=True);checks=[];errors=[]
    try:
        client,user=f.register('candidate')
        f.db.execute('UPDATE candidates SET consent_publication=true WHERE id=%s',(user['subject_id'],))
        response=client.post('/resumes',json=dict(target_position='Eligibility boundary profile',specialization='backend_python',declared_grade='middle',
            experience_years=4,skills=['Python','SQL'],about='Python API and SQL queries.',expected_salary=180000,work_format='удалённо',visibility='employer_searchable'))
        response.raise_for_status();rid=response.json()['resume']['id'];cert='CU'+uuid.uuid4().hex
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            for state in ('pending','valid','revoked'):
                if state=='valid':
                    f.db.execute("INSERT INTO qualification_certificates(id,candidate_id,resume_id,specialization,grade,skills,assessment_version,attempt) VALUES(%s,%s,%s,'backend_python','middle','[\"Python\"]','ui-boundary-fixture','{\"score\":90}')",(cert,user['subject_id'],rid))
                if state=='revoked':
                    f.db.execute('UPDATE qualification_certificates SET revoked_at=now() WHERE id=%s',(cert,))
                for language in ('ru','en','kk','uz','az','be'):
                    catalog=json.loads((ROOT/f'web/src/locales/{language}.json').read_text(encoding='utf-8'))
                    for width in (390,1440):
                        context=browser.new_context(viewport={'width':width,'height':1000},extra_http_headers={'Authorization':client.headers['Authorization']})
                        context.add_init_script('localStorage.setItem("proofit.language",'+json.dumps(language)+')')
                        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                        page.goto(f.cfg['BASE_URL']+'/#resumes')
                        card=page.locator('.resume-card').filter(has_text='Eligibility boundary profile')
                        expect(card).to_be_visible(timeout=30000)
                        badge=card.locator('.section-heading .badge').first
                        expect(badge).to_have_text(catalog['Опубликовано' if state=='valid' else 'Ожидает подтверждения'])
                        assert page.locator('html').get_attribute('lang')==language
                        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
                        if language=='ru' and width==1440:
                            page.screenshot(path=str(ROOT/f'validation/reports/current/category-{state}-ui.png'),full_page=True)
                        checks.append(dict(state=state,language=language,width=width,expected_badge=badge.inner_text(),overflow=False))
                        context.close()
            browser.close()
        report=dict(passed=not errors,checks=checks,browser_errors=errors,llm_calls=0,
                    generated_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),scope='Persisted discovery readiness and translated status badge; not a new human translation audit')
        (ROOT/'validation/reports/current/category-revision-ui.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        assert not errors
        print('Eligibility cards: '+str(len(checks))+' browser scenarios passed.')
    finally:f.close()

if __name__=='__main__':main()
