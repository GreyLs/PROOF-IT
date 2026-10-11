"""Actual browser journey with separate authenticated roles and a live expert dialogue."""
from pathlib import Path
import json,time,uuid,os
import httpx,psycopg
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright,expect
from check_expert_dialogues import STRONG_BACKEND, register
from check_project_cases import respondent
ROOT=Path(__file__).resolve().parents[1];load_dotenv(ROOT/'.env');OUT=ROOT/'validation/reports/current/screenshots/project-cases';OUT.mkdir(parents=True,exist_ok=True)
errors=[];checks=[];created=[]
def main():
 c,cu=register();e,eu=register('employer');created.extend([cu,eu]);title='Предложение UI '+uuid.uuid4().hex[:6]
 try:
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True)
   cp=browser.new_page(viewport={'width':1440,'height':1050});ep=browser.new_page(viewport={'width':1440,'height':1050})
   for page,u in [(cp,cu),(ep,eu)]:
    page.on('pageerror',lambda x:errors.append(str(x)));page.goto('http://localhost:8080',wait_until='networkidle')
    page.get_by_label('Email или имя',exact=True).fill(u['email']);page.get_by_label('Пароль',exact=True).fill('DialogueOnly-2026-Synthetic');page.get_by_role('button',name='Войти в кабинет',exact=True).click();expect(page.locator('.sidebar')).to_be_visible()
   checks.append('Separate password login in both browser contexts')
   cp.get_by_role('button',name='Мой профиль',exact=True).click()
   cp.get_by_label('ФИО',exact=True).fill('Синтетический кандидат для проверки интерфейса')
   cp.get_by_label('Телефон',exact=True).fill('+7 000 000-00-00')
   cp.get_by_label('Специализация',exact=False).select_option('backend_python')
   cp.get_by_label('Предполагаемый грейд',exact=False).select_option('middle')
   cp.get_by_label('Опыт, лет',exact=True).fill('4')
   cp.get_by_label('Стек и профессиональные навыки',exact=False).fill('Python, FastAPI, PostgreSQL, Docker')
   cp.get_by_label('О себе и своей роли в команде',exact=True).fill('Разрабатывал сервис платежей на Python и PostgreSQL. В резюме не указаны мои решения, ответственность и наблюдаемый результат.')
   with cp.expect_response(lambda r:r.url.endswith('/api/profile') and r.request.method=='PUT'):
    cp.get_by_role('button',name='Сохранить профиль',exact=True).click()
   cp.get_by_role('button',name='Подтвердить уровень',exact=True).click()
   cp.screenshot(path=str(OUT/'01-profile-assistant.png'),full_page=True)
   cp.get_by_role('button',name='Начать экспертный диалог',exact=True).click()
   expect(cp.locator('.expert-compose textarea')).to_be_visible(timeout=180000)
   cp.locator('.expert-compose textarea').fill('Напиши рецепт борща');cp.get_by_role('button',name='Отправить ответ',exact=True).click()
   expect(cp.locator('.expert-messages .notice')).to_contain_text('только ваш профессиональный опыт',timeout=180000)
   expect(cp.locator('.expert-toolbar')).to_contain_text('Уточнения опыта: 1')
   checks.append('UI redirects recipe request without consuming a question')
   for _ in range(3):
    cp.locator('.expert-compose textarea').fill(STRONG_BACKEND);cp.get_by_role('button',name='Отправить ответ',exact=True).click()
    expect(cp.locator('.expert-messages')).to_have_attribute('aria-busy','false',timeout=180000)
    if cp.get_by_role('button',name='Подготовить три кейса',exact=True).count():break
   assert c.get('/profile').json()['profile']['confirmed_grade'] is None
   with cp.expect_response(lambda r:r.url.endswith('/cases') and r.request.method=='POST',timeout=330000) as prepared:
    cp.get_by_role('button',name='Подготовить три кейса',exact=True).click()
   d=prepared.value.json();assert len(d['cases'])==1
   for i in range(3):
    prompt=d['cases'][i]['prompt'];assert len(prompt)<=800
    answer=respondent(prompt,'backend_python','middle','strong')
    expect(cp.locator('.expert-compose textarea')).to_be_enabled(timeout=330000)
    cp.locator('.expert-compose textarea').fill(answer)
    with cp.expect_response(lambda r:r.url.endswith('/messages') and r.request.method=='POST',timeout=330000) as answered:
     cp.get_by_role('button',name='Отправить ответ',exact=True).click()
    assert answered.value.ok,answered.value.text();d=answered.value.json()
    print('browser: case',i+1,'completed',flush=True)
    if i<2:assert c.get('/profile').json()['profile']['confirmed_grade'] is None
   assert d['result']['decision']=='supported',d['result']
   expect(cp.locator('.expert-result')).to_contain_text('Категория подтверждена',timeout=330000)
   checks.append('Three separately reviewed no-code cases and delayed grade via browser')
   cp.screenshot(path=str(OUT/'02-evidence-result.png'),full_page=True);checks.append('Live Qwen dialogue assigns category via UI')
   cp.get_by_role('button',name='Мой профиль',exact=True).click()
   # Visibility is an explicit candidate action in the UI, after confirmation.
   checks_boxes=cp.locator('input[type=checkbox]');checks_boxes.nth(0).check();checks_boxes.nth(1).check()
   cp.get_by_label('Видимость работодателям',exact=False).select_option('employer_searchable')
   with cp.expect_response(lambda r:r.url.endswith('/api/profile') and r.request.method=='PUT'):
    cp.get_by_role('button',name='Сохранить профиль',exact=True).click()
   ep.get_by_role('button',name='Банк талантов',exact=True).click();ep.get_by_label('Поиск по навыку или ID',exact=True).fill(cu['subject_id']);expect(ep.locator('.candidate-card')).to_have_count(1)
   ep.get_by_role('button',name='Профиль',exact=True).click();expect(ep.get_by_role('dialog')).to_contain_text('Контакты откроются');ep.get_by_role('button',name='Закрыть',exact=True).click()
   ep.get_by_role('button',name='Пригласить',exact=True).click();ep.get_by_label('Название предложения').fill(title);ep.get_by_label('Команда, задачи и условия').fill('Разработка платёжного сервиса на Python. Синтетическое предложение для сквозной проверки.')
   ep.get_by_label('Зарплата от, ₽ / месяц',exact=True).fill('220000');ep.get_by_label('Зарплата до, ₽ / месяц',exact=True).fill('300000')
   ep.get_by_role('button',name='Отправить приглашение',exact=True).click();expect(ep.get_by_role('dialog')).to_have_count(0)
   cp.get_by_role('button',name='Предложения',exact=True).click();card=cp.locator('.offer-card').filter(has_text=title);expect(card).to_be_visible();card.get_by_role('button',name='Принять и открыть контакты',exact=True).click();expect(card).to_contain_text('Вы открыли контакты этой компании')
   ep.get_by_role('button',name='Приглашения',exact=True).click();ep.locator('.offer-card').filter(has_text=title).get_by_role('button',name='Открыть контакты',exact=True).click();expect(ep.get_by_role('dialog')).to_contain_text(cu['email']);ep.screenshot(path=str(OUT/'03-employer-consented-contact.png'),full_page=True)
   checks.append('Employer search -> salary offer -> candidate consent -> scoped contacts')
   cp.get_by_role('button',name='Мой профиль',exact=True).click();cp.get_by_role('button',name='PDF-профиль',exact=True).click();cp.get_by_role('button',name='Документы',exact=True).click();export=cp.locator('.document-item').filter(has_text='Ваш PDF-профиль');expect(export.get_by_role('link',name='Открыть PDF').first).to_be_visible(timeout=90000)
   url=export.get_by_role('link',name='Открыть PDF').first.get_attribute('href');pdf=cp.request.get('http://localhost:8080'+url);assert pdf.ok and pdf.body().startswith(b'%PDF');checks.append('Actual profile PDF export')
   cp.get_by_role('button',name='Вакансии',exact=True).click();cp.get_by_label('Специализация вакансий').select_option('executive_cto');expect(cp.locator('.vacancy-card')).to_have_count(8)
   cp.locator('.vacancy-card').first.get_by_role('button',name='Посмотреть и откликнуться',exact=True).click();expect(cp.get_by_role('dialog')).to_contain_text('Насколько эта роль соответствует вашему опыту?');cp.screenshot(path=str(OUT/'04-vacancy-assistant.png'),full_page=True);cp.get_by_role('button',name='Закрыть',exact=True).click()
   cp.set_viewport_size({'width':390,'height':844});cp.goto('http://localhost:8080/#assessment',wait_until='networkidle');cp.reload(wait_until='networkidle');expect(cp.locator('.sidebar')).not_to_be_in_viewport();assert cp.evaluate('document.documentElement.scrollWidth <= window.innerWidth+1');cp.screenshot(path=str(OUT/'05-mobile-assistant.png'),full_page=True);checks.append('Leadership vacancy chat entry and 390px mobile layout')
   browser.close()
  assert not errors,errors
 finally:
  c.close();e.close()
  # Remove only synthetic subjects created by this script, including own child records.
  ids=[u['id'] for u in created];subjects=[u['subject_id'] for u in created]
  with psycopg.connect(os.environ['DATABASE_URL']) as db:
   db.execute("INSERT INTO file_deletions(storage_key) SELECT storage_key FROM documents WHERE user_id=ANY(%s) UNION SELECT result->>'output_key' FROM documents WHERE user_id=ANY(%s) AND result->>'output_key' IS NOT NULL ON CONFLICT DO NOTHING",(ids,ids))
   for query in ['DELETE FROM audit_events WHERE actor_id=ANY(%s)','DELETE FROM documents WHERE user_id=ANY(%s)','DELETE FROM users WHERE id=ANY(%s)']:db.execute(query,(ids,))
   db.execute('DELETE FROM invitations WHERE candidate_id=ANY(%s) OR company_id=ANY(%s)',(subjects,subjects));db.execute('DELETE FROM assessments WHERE candidate_id=ANY(%s)',(subjects,));db.execute('DELETE FROM candidates WHERE id=ANY(%s)',(subjects,));db.execute('DELETE FROM companies WHERE id=ANY(%s)',(subjects,))
  report={'checks':checks,'javascript_errors':errors,'passed':not errors and len(checks)==7};(ROOT/'validation/reports/current/browser-project-cases-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
