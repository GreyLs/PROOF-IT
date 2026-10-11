"""Browser acceptance: password-only entry, independent roles and the supplied PDF."""
from pathlib import Path
import json
import uuid

from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
ORIGIN='http://localhost:8080'


def main():
    accounts=json.loads((ROOT/'runtime/test-accounts.json').read_text(encoding='utf-8'))
    checked=json.loads((ROOT/'runtime/resume-samples-check.json').read_text(encoding='utf-8'))
    errors=[]
    checks=[]
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(ORIGIN+'/#documents',wait_until='networkidle')
        expect(page.get_by_role('button',name='Войти в кабинет',exact=True)).to_be_visible()
        expect(page.locator('.sidebar')).to_have_count(0)
        expect(page.locator('.demo-buttons')).to_have_count(0)
        response=page.evaluate("""async () => {
            const data=new FormData();data.append('file',new Blob(['%PDF-'],{type:'application/pdf'}),'empty.pdf');
            const response=await fetch('/api/documents?kind=resume',{method:'POST',body:data});
            return response.status;
        }""")
        assert response==401,response
        checks.append('Direct cabinet URL and browser upload require authentication')

        def login(role):
            account=accounts[role]
            page.get_by_label('Email или имя',exact=True).fill(account['email'])
            page.get_by_label('Пароль',exact=True).fill(account['password'])
            page.get_by_role('button',name='Войти в кабинет',exact=True).click()
            expect(page.locator('.workspace-label')).to_have_text('КАБИНЕТ КАНДИДАТА' if role=='candidate' else 'КАБИНЕТ РАБОТОДАТЕЛЯ')
            expect(page.locator('.role-switch')).to_have_count(0)

        login('candidate')
        page.reload(wait_until='networkidle')
        expect(page.locator('.workspace-label')).to_have_text('КАБИНЕТ КАНДИДАТА')
        page.get_by_role('button',name='Документы',exact=True).click()
        card=page.locator('.document-item').filter(has_text='resume_samples.pdf')
        expect(card.get_by_role('button',name='Проверить',exact=True)).to_be_visible()
        card.get_by_role('button',name='Проверить',exact=True).click()
        selector=page.get_by_label('Резюме в файле',exact=False)
        expect(selector.locator('option')).to_have_count(4)
        expect(page.get_by_role('button',name='Перенести в мой профиль',exact=True)).to_be_disabled()
        detail=page.request.get(ORIGIN+'/api/documents/'+checked['document_id']).json()['document']
        for index,profile in enumerate(detail['result']['profiles']):
            selector.select_option(str(index))
            expect(page.get_by_label('ФИО',exact=True)).to_have_value(profile['fields']['full_name'])
            expect(page.get_by_label('Телефон',exact=True)).to_have_value(str(profile['fields']['phone']))
            page.get_by_role('button',name='Исходный текст',exact=True).click()
            expect(page.locator('.source-pages section')).to_have_count(1)
            expect(page.locator('.source-pages .badge')).to_have_text('Страница '+str(index+1))
            page.get_by_role('button',name='Поля и источники',exact=True).click()
        page.screenshot(path=str(ROOT/'runtime/resume-bundle-review.png'),full_page=True)
        page.get_by_role('button',name='Закрыть',exact=True).click()
        checks.append('Three resumes in supplied PDF have separate fields, contacts and page citations')
        page.get_by_role('button',name='Выйти',exact=True).click()
        expect(page.get_by_role('button',name='Войти в кабинет',exact=True)).to_be_visible()
        login('employer')
        expect(page.get_by_role('button',name='Банк талантов',exact=True)).to_be_visible()
        response=page.request.get(ORIGIN+'/api/documents/'+checked['document_id'])
        assert response.status==404
        checks.append('Separate employer login cannot access the candidate document')
        page.get_by_role('button',name='Выйти',exact=True).click()
        expect(page.get_by_role('button',name='Войти в кабинет',exact=True)).to_be_visible()
        page.screenshot(path=str(ROOT/'runtime/password-only-login.png'),full_page=True)

        # A new user can register in the UI, verify in the local mailbox, then log in again.
        email=f'ui-registration-{uuid.uuid4().hex}@example.test'
        password='UiOnly-'+uuid.uuid4().hex
        display_name='Тест регистрации интерфейса'
        page.get_by_role('button',name='Регистрация',exact=True).click()
        page.get_by_role('button',name='Кандидат',exact=True).click()
        page.get_by_label('Ваше имя',exact=True).fill(display_name)
        page.get_by_label('Email или имя',exact=True).fill(email)
        page.get_by_label('Пароль',exact=False).fill(password)
        page.get_by_role('checkbox').check()
        page.get_by_role('button',name='Создать аккаунт',exact=True).click()
        page.get_by_role('button',name='Открыть письмо и подтвердить',exact=False).click()
        expect(page.locator('.workspace-label')).to_have_text('КАБИНЕТ КАНДИДАТА')
        page.get_by_role('button',name='Выйти',exact=True).click()
        page.get_by_label('Электронная почта',exact=True).fill(email)
        page.get_by_label('Пароль',exact=True).fill(password)
        page.get_by_role('button',name='Войти в кабинет',exact=True).click()
        expect(page.locator('.workspace-label')).to_have_text('КАБИНЕТ КАНДИДАТА')
        page.get_by_role('button',name='Выйти',exact=True).click()
        page.get_by_label('Email или имя',exact=True).fill(display_name)
        page.get_by_label('Пароль',exact=True).fill(password)
        page.get_by_role('button',name='Войти в кабинет',exact=True).click()
        expect(page.locator('.workspace-label')).to_have_text('КАБИНЕТ КАНДИДАТА')
        response=page.request.delete(ORIGIN+'/api/account',data={'password':password},headers={'Origin':ORIGIN})
        assert response.ok,response.status
        checks.append('New UI registration, confirmation, logout and login by email and displayed name succeed')
        browser.close()
    assert not errors,errors
    report={'passed':True,'checks':checks,'javascript_errors':errors}
    (ROOT/'validation/reports/current/registered-access-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
