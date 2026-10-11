"""Real browser flow: offer -> consent -> contacts; PDF queue -> review -> draft.
Uses demo identities and removes only the newly created business records.
Keeps clearly synthetic reviewed PDFs in the demo cabinet for demonstration.
"""
from pathlib import Path
import os,json,time,uuid
import psycopg
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];load_dotenv(ROOT/'.env')
OUT=ROOT/'validation/reports/current/screenshots';OUT.mkdir(exist_ok=True)
run=uuid.uuid4().hex[:8];title=f'Проверка браузера {run}';errors=[];checks=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://localhost:8080',wait_until='networkidle')
    page.get_by_role('button',name='Я работодатель',exact=True).click()
    page.get_by_role('button',name='Банк талантов',exact=True).click()
    page.get_by_role('textbox',name='Поиск по навыку или ID').fill('PC00057')
    expect(page.locator('.candidate-card')).to_have_count(1)
    page.get_by_role('button',name='Профиль',exact=True).click()
    expect(page.get_by_role('dialog')).to_contain_text('Контакты откроются')
    page.get_by_role('button',name='Закрыть',exact=True).click();checks.append('contacts hidden before consent')
    page.get_by_role('button',name='Пригласить',exact=True).click()
    page.get_by_label('Название предложения').fill(title)
    page.get_by_label('Команда, задачи и условия').fill('Разработка сервиса на Python. Синтетическое предложение для проверки полного сценария.')
    page.get_by_role('button',name='Отправить приглашение',exact=True).click()
    expect(page.get_by_role('dialog')).to_have_count(0)
    page.get_by_role('button',name='Кабинет кандидата',exact=True).click()
    page.get_by_role('button',name='Приглашения',exact=True).click()
    card=page.locator('.offer-card').filter(has_text=title)
    card.get_by_role('button',name='Принять и открыть контакты').click()
    expect(card).to_contain_text('Вы открыли контакты этой компании')
    page.screenshot(path=str(OUT/'08-candidate-consent.png'),full_page=True)
    page.get_by_role('button',name='Кабинет работодателя',exact=True).click()
    page.get_by_role('button',name='Приглашения',exact=True).click()
    page.locator('.offer-card').filter(has_text=title).get_by_role('button',name='Открыть контакты').click()
    expect(page.get_by_role('dialog')).to_contain_text('candidate@demo.example')
    page.screenshot(path=str(OUT/'09-consented-contacts.png'),full_page=True)
    page.get_by_role('button',name='Закрыть',exact=True).click();checks.append('offer accepted in UI; employer sees contacts')
    page.get_by_role('button',name='Документы',exact=True).click()
    page.locator('input[type=file]').set_input_files(str(ROOT/'tests/fixtures/vacancy-text.pdf'))
    card=page.locator('.document-item').filter(has_text='vacancy-text.pdf')
    expect(card.get_by_role('button',name='Проверить')).to_be_visible(timeout=240000)
    card.get_by_role('button',name='Проверить').click()
    expect(page.get_by_label('Зарплата от, ₽',exact=True)).to_have_value('220000')
    expect(page.get_by_label('Зарплата до, ₽',exact=True)).to_have_value('300000')
    assert 'Python' in page.get_by_label('Стек, через запятую',exact=True).input_value()
    page.screenshot(path=str(OUT/'10-document-review.png'),full_page=True)
    page.get_by_role('button',name='Создать вакансию / потребность',exact=True).click()
    expect(page.get_by_role('dialog')).to_have_count(1)
    page.get_by_label('Название роли или потребности').fill(title)
    page.get_by_role('button',name='Сформировать подборку',exact=True).click()
    expect(page.get_by_role('dialog')).to_have_count(0)
    checks.append('PDF queue completed; cited salary correct; reviewed need created')
    page.get_by_role('button',name='Кабинет кандидата',exact=True).click()
    page.get_by_role('button',name='Мой профиль',exact=True).click()
    page.get_by_role('button',name='PDF-профиль',exact=True).click()
    page.get_by_role('button',name='Документы',exact=True).click()
    export=page.locator('.document-item').filter(has_text='Ваш PDF-профиль')
    expect(export.get_by_role('link',name='Открыть PDF').first).to_be_visible(timeout=60000)
    url=export.get_by_role('link',name='Открыть PDF').first.get_attribute('href')
    result=page.request.get('http://localhost:8080'+url)
    assert result.ok and result.body().startswith(b'%PDF-');checks.append('profile PDF exported through real worker queue')
    browser.close()
with psycopg.connect(os.environ['DATABASE_URL']) as db:
    ids=[r[0] for r in db.execute('SELECT id FROM invitations WHERE company_id=%s AND title=%s',('EMP0001',title))]
    db.execute('DELETE FROM audit_events WHERE entity_id=ANY(%s)',(ids,))
    db.execute('DELETE FROM invitations WHERE id=ANY(%s)',(ids,))
    db.execute('DELETE FROM vacancies WHERE company_id=%s AND title=%s',('EMP0001',title))
report={'checks':checks,'javascript_errors':errors,'passed':not errors}
(ROOT/'validation/reports/current/browser-flow-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2));assert not errors
