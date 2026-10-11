"""Targeted real-browser checks of password-only access; no benchmark reruns."""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from scripts.workbench_test_fixture import Fixture

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'validation/reports/current'

def main():
    fixture = Fixture()
    checks, errors = [], []
    origin = fixture.cfg['BASE_URL']
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            for width in (390, 768, 1440):
                page.set_viewport_size({'width': width, 'height': 1000})
                page.goto(origin+'/proofit')
                page.wait_for_selector('.login-page input[autocomplete=username]')
                assert page.locator('.guest-entry, [data-demo-entry], .demo-help, .demo-credentials').count() == 0
                assert 'Проверить платформу в демо-режиме' not in page.locator('body').inner_text()
                assert page.get_by_role('button', name='Регистрация', exact=True).count() == 1
                assert page.get_by_role('button', name='Забыли пароль?', exact=True).count() == 1
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                page.screenshot(path=str(OUT/f'auth-access-{width}.png'), full_page=True)
                checks.append(f'password_only_login_page_{width}px')
            for role in ('candidate', 'employer'):
                page.locator('input[autocomplete=username]').fill(role+'@demo.proofit.invalid')
                page.locator('input[autocomplete=current-password]').fill('Proofit-Demo-2026!')
                page.get_by_role('button', name='Войти в кабинет', exact=True).click()
                page.wait_for_selector('.app-shell')
                user = page.request.get(origin+'/api/auth/me').json()['user']
                assert user['role'] == role and user['synthetic']
                assert page.locator('.demo-scenario-bar, [data-demo-role]').count() == 0
                if role == 'candidate':
                    page.locator('.sidebar [data-nav-group=assessment]').click()
                    page.locator('.section-tabs').get_by_role('button', name='Резюме и знания', exact=True).click()
                    page.wait_for_selector('.resume-card')
                    assert page.locator('.resume-card').count() >= 2
                else:
                    workspace = page.request.get(origin+'/api/auth/demo-context').json()['workspace']
                    vacancies = page.request.get(origin+'/api/vacancies?mine=true').json()['items']
                    assert len(vacancies) >= 2 and all(item['company_id'] == workspace['company_id'] for item in vacancies)
                page.locator('.topbar [aria-label="Выйти"]').click()
                page.wait_for_selector('.login-page')
                assert page.request.get(origin+'/api/auth/me').status == 401
                checks.append(f'{role}_form_login_correct_cabinet_logout_revoked')
            page.screenshot(path=str(OUT/'demo-revision-logout.png'), full_page=True)
            browser.close()
        report = {'passed': not errors, 'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'scope': 'removed guest UI, ordinary password login for both roles, seeded data and logout only',
            'checks': checks, 'browser_errors': errors, 'llm_scoring': False}
        (OUT/'demo-revision-ui.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        assert not errors
        print(json.dumps({'passed': True, 'checks': len(checks), 'js_errors': len(errors)}))
    finally:
        fixture.close()

if __name__ == '__main__':
    main()
