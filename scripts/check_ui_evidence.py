"""Real Chromium responsive checks and video semantics; no generative calls."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
from scripts.workbench_test_fixture import Fixture
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current';OUT.mkdir(parents=True,exist_ok=True)
def main():
 f=Fixture();errors=[];checks=[]
 try:
  with sync_playwright() as pw:
   browser=pw.chromium.launch(headless=True)
   for width in [390,768,1440]:
    page=browser.new_page(viewport={'width':width,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(f.cfg['BASE_URL']);page.wait_for_selector('.login-page');page.locator('.auth-network-video').evaluate('(v)=>v.load()');page.wait_for_timeout(1000)
    video=page.locator('.auth-network-video').evaluate('(v)=>({muted:v.muted,loop:v.loop,inline:v.playsInline,ready:v.readyState,inside:!!v.closest(".login-story")})');assert video['muted'] and video['loop'] and video['inline'] and video['inside']
    overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth');assert not overflow
    page.screenshot(path=str(OUT/f'login-{width}.png'),full_page=True);checks.append({'page':'login','width':width,'overflow':overflow,'video':video})
    assert page.locator('.auth-motion-control').count()==0
    before=page.locator('.auth-network-video').evaluate('(v)=>v.currentTime')
    page.wait_for_timeout(700)
    assert page.locator('.auth-network-video').evaluate('(v)=>!v.paused&&v.currentTime')!=before
    page.close()
   for role in ['candidate','employer']:
    c,u=f.register(role);token=c.headers['Authorization'].removeprefix('Bearer ')
    for width in [390,1440]:
     secure=f.cfg['BASE_URL'].startswith('https://');context=browser.new_context(viewport={'width':width,'height':1000});context.add_cookies([{'name':'__Host-fsp_session' if secure else 'fsp_session','value':token,'url':f.cfg['BASE_URL'],'secure':secure,'httpOnly':True,'sameSite':'Strict'}]);page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(f.cfg['BASE_URL']+'/#evidence');page.wait_for_selector('.app-shell');page.wait_for_selector('h1');page.wait_for_timeout(700)
     assert page.locator('.auth-network-video').count()==0
     assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
     page.screenshot(path=str(OUT/f'{role}-evidence-{width}.png'),full_page=True);checks.append({'page':role+'-evidence','width':width,'overflow':False,'auth_video_absent':True});context.close()
   page=browser.new_page(reduced_motion='reduce');page.goto(f.cfg['BASE_URL']);page.wait_for_selector('.auth-network-video');page.wait_for_function('()=>document.querySelector(".auth-network-video").readyState>=2');assert not page.locator('.auth-network-video').evaluate('(v)=>v.paused');checks.append({'page':'reduced-motion','paused':False});page.close();browser.close()
  report={'checks':checks,'browser_errors':errors,'llm_calls':0,'passed':not errors};(OUT/'browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');assert not errors
  print('Chromium responsive/video/accessibility checks passed:',len(checks))
 finally:f.close()
if __name__=='__main__':main()
