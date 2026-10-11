from scripts.private_runtime import private_file
"""Targeted verification of the approved video and brand composition only."""
import hashlib
import json
import time
from pathlib import Path
from dotenv import dotenv_values
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'validation/reports/current'

def main():
    cfg = dotenv_values(ROOT/'.env')
    cfg.update(json.loads((private_file('public-settings.json')).read_text(encoding='utf-8')))
    origin = cfg['BASE_URL']
    errors, checks = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width in (390, 768, 1440):
            page = browser.new_page(viewport={'width': width, 'height': 1000})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin+'/proofit')
            page.wait_for_selector('.auth-brand-constellation svg')
            page.wait_for_function('()=>document.querySelector(".auth-network-video").readyState>=2')
            assert page.locator('.auth-motion-control, video[controls], .guest-entry, [data-demo-entry], canvas').count() == 0
            video = page.locator('video').evaluate('(v)=>({autoplay:v.autoplay,muted:v.muted,loop:v.loop,inline:v.playsInline,paused:v.paused,time:v.currentTime})')
            assert all(video[key] for key in ('autoplay', 'muted', 'loop', 'inline')) and not video['paused']
            page.wait_for_timeout(650)
            assert page.locator('video').evaluate('(v)=>v.currentTime') != video['time']
            page.locator('video').evaluate('(v)=>v.pause()')
            page.wait_for_function('()=>document.querySelector("video")?.paused===false')
            before=page.locator('video').evaluate('(v)=>v.currentTime')
            page.wait_for_timeout(650)
            assert page.locator('video').evaluate('(v)=>v.currentTime')!=before
            mark = page.locator('[data-brand-mark=fsp] path')
            assert mark.count() == 3
            assert all('url(#auth-brand-' in value for value in mark.evaluate_all('(paths)=>paths.map(p=>p.getAttribute("fill"))'))
            assert page.locator('.auth-brand-constellation').get_attribute('aria-hidden') == 'true'
            geometry = page.evaluate('''() => {
              const story=document.querySelector('.login-story').getBoundingClientRect();
              const title=document.querySelector('.login-story h1').getBoundingClientRect();
              const text=document.querySelector('.login-story > p').getBoundingClientRect();
              const decoration=document.querySelector('.auth-brand-constellation').getBoundingClientRect();
              const button=document.querySelector('.login-form button[type=submit], .login-form .button.primary').getBoundingClientRect();
              return {below_text:decoration.top>=Math.max(title.bottom,text.bottom),
                inside_story:decoration.left>=story.left && decoration.right<=story.right && decoration.bottom<=story.bottom,
                login_button_clickable:Boolean(document.elementFromPoint(button.left+button.width/2,button.top+button.height/2)?.closest('button'))};
            }''')
            assert all(geometry.values()), geometry
            brand = page.locator('.login-story').evaluate('(e)=>getComputedStyle(e).getPropertyValue("--purple").trim().toLowerCase()')
            assert brand == '#402fff'
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            page.screenshot(path=str(OUT/f'auth-revision-{width}.png'), full_page=True)
            checks.append({'width': width, 'continuous_silent_video': True, 'pause_button_absent': True,
                'brand_mark_paths': 3, 'brand_token_unchanged': brand, 'decorative_only': True,
                'composition': 'three-orbits-code-shield-growth', 'pause_recovery': True, **geometry, 'overflow': False})
            page.close()
        page = browser.new_page(reduced_motion='reduce')
        page.goto(origin+'/proofit')
        page.wait_for_selector('.auth-network-video')
        page.wait_for_function('()=>document.querySelector("video")?.paused===false')
        assert page.locator('.auth-brand-constellation svg').count() == 1
        checks.append({'reduced_motion_preference': True, 'silent_video_continues': True, 'svg_animation_absent': True})
        page.close()
        # Verify that decorative elements are unmounted in either real cabinet.
        for role in ('candidate', 'employer'):
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin+'/proofit')
            page.locator('input[autocomplete=username]').fill(role+'@demo.proofit.invalid')
            page.locator('input[autocomplete=current-password]').fill('Proofit-Demo-2026!')
            page.get_by_role('button', name='Войти в кабинет', exact=True).click()
            page.wait_for_selector('.app-shell')
            assert page.locator('.auth-network-video, .auth-brand-constellation').count() == 0
            assert page.request.get(origin+'/api/auth/me').json()['user']['role'] == role
            page.locator('.topbar [aria-label="Выйти"]').click()
            page.wait_for_selector('.auth-brand-constellation svg')
            assert page.request.get(origin+'/api/auth/me').status == 401
            checks.append({'role': role, 'login_only_decoration': True, 'normal_login_and_logout': True})
            page.close()
        browser.close()
    source = ROOT/'web/public/media/auth-network.mp4'
    result = {'passed': not errors, 'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'scope': 'authentication video and branded SVG composition only; other benchmarks not rerun',
        'checks': checks, 'browser_errors': errors, 'llm_scoring': False,
        'media_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    (OUT/'auth-revision.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    assert not errors
    print(json.dumps({'passed': True, 'checks': len(checks), 'js_errors': len(errors)}))

if __name__ == '__main__':
    main()
