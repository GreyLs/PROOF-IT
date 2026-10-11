"""Mobile entry after layout settles; complements the full browser journey."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright,expect
from check_expert_dialogues import register,cleanup,ORIGIN
ROOT=Path(__file__).resolve().parents[1]
client,user=register()
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  page=browser.new_page(viewport={'width':390,'height':844})
  page.goto(ORIGIN,wait_until='networkidle')
  page.get_by_label('Email или имя',exact=True).fill(user['email'])
  page.get_by_label('Пароль',exact=True).fill('DialogueOnly-2026-Synthetic')
  page.get_by_role('button',name='Войти в кабинет',exact=True).click()
  expect(page.locator('.sidebar')).to_have_count(1)
  page.goto(ORIGIN+'/#assessment',wait_until='networkidle')
  page.reload(wait_until='networkidle')
  expect(page.locator('.sidebar')).not_to_be_in_viewport()
  expect(page.get_by_role('button',name='Начать экспертный диалог',exact=True)).to_be_visible()
  assert page.evaluate('() => document.documentElement.scrollWidth <= window.innerWidth + 1')
  page.screenshot(path=str(ROOT/'validation/reports/current/screenshots/stage/05-mobile-assistant.png'),full_page=True)
  browser.close()
 report={'passed':True,'width':390,'horizontal_overflow':False,'closed_sidebar_outside_viewport':True}
 (ROOT/'validation/reports/current/browser-mobile-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report))
finally:
 client.close();cleanup(user)
