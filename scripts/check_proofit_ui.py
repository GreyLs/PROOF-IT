"""Read-only browser coverage for the PROOFIT desktop and mobile interface.

Uses only existing ignored test credentials. It never creates accounts or changes
domain data. Login/logout are the only allowed non-GET requests. Screenshots and
the machine-readable report are written under ignored runtime/ by default.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
VIEWPORTS = [(1440, 900), (1024, 768), (768, 1024), (390, 844), (360, 740)]
ROUTES = {
    "employer": ["overview", "search", "invitations", "vacancies", "applications",
                 "tasks", "documents", "company", "security", "messages", "validation"],
    "candidate": ["overview", "profile", "resumes", "assessment", "invitations",
                  "vacancies", "applications", "tasks", "documents", "security",
                  "career", "messages", "validation"],
}
TABLET_ROUTES = {"employer": {"overview", "search", "company", "messages"},
                 "candidate": {"overview", "profile", "resumes", "assessment", "messages"}}
FULL_PAGE_ROUTES = {"overview", "profile", "company", "search", "documents", "assessment", "vacancies"}

LAYOUT_CHECK = r"""() => {
  const width = window.innerWidth;
  const tolerance = 2;
  const findings = [];
  const descriptor = el => el.tagName.toLowerCase() +
    (typeof el.className === 'string' && el.className.trim()
      ? '.' + el.className.trim().split(/\s+/).slice(0, 4).join('.') : '');
  const excluded = el => {
    const sidebar = el.closest('.sidebar');
    if (sidebar && !sidebar.classList.contains('open') &&
        sidebar.getBoundingClientRect().right <= tolerance) return true;
    for (let ancestor = el.parentElement; ancestor; ancestor = ancestor.parentElement) {
      const css = getComputedStyle(ancestor);
      const box = ancestor.getBoundingClientRect();
      if (['auto', 'scroll', 'hidden', 'clip'].includes(css.overflowX) &&
          box.left >= -tolerance && box.right <= width + tolerance &&
          ancestor !== document.body && ancestor !== document.documentElement) return true;
    }
    return false;
  };
  for (const el of document.body.querySelectorAll('*')) {
    const css = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    if (css.display === 'none' || css.visibility === 'hidden' ||
        Number(css.opacity) === 0 || box.width === 0 || box.height === 0 || excluded(el)) continue;
    const outside = box.left < -tolerance || box.right > width + tolerance;
    const internal = el.clientWidth > 0 && el.scrollWidth > el.clientWidth + tolerance &&
      css.overflowX === 'visible' && css.display !== 'inline' &&
      // This upload illustration intentionally lets its corner badge extend by
      // six pixels. Its actual viewport bounds are still checked above.
      !el.matches('.upload-symbol') &&
      !['BODY', 'HTML', 'SVG'].includes(el.tagName) && !el.closest('svg');
    if ((outside || internal) && findings.length < 40) findings.push({
      element: descriptor(el), kind: outside ? 'outside_viewport' : 'unclipped_content',
      left: Math.round(box.left), right: Math.round(box.right),
      client_width: el.clientWidth, scroll_width: el.scrollWidth
    });
  }
  const logos = [...document.querySelectorAll('.brand img, .login-fsp')].map(img => {
    const box = img.getBoundingClientRect();
    const ratio = Math.min(box.width / img.naturalWidth, box.height / img.naturalHeight);
    return {source: new URL(img.src).pathname, loaded: img.complete && img.naturalWidth > 0,
      width: Math.round(box.width), height: Math.round(box.height),
      painted_width: Math.round(img.naturalWidth * ratio),
      painted_height: Math.round(img.naturalHeight * ratio)};
  });
  return {viewport_width: width, document_width: document.documentElement.scrollWidth,
    document_overflow: document.documentElement.scrollWidth > width + tolerance,
    horizontal_overflow: findings.length > 0, offenders: findings, logos,
    font_status: document.fonts.status, body_font: getComputedStyle(document.body).fontFamily,
    heading_font: document.querySelector('h1')
      ? getComputedStyle(document.querySelector('h1')).fontFamily : null};
}"""


def load_accounts() -> dict:
    path = ROOT / "runtime/test-accounts.json"
    if not path.exists():
        raise RuntimeError("Existing runtime/test-accounts.json is missing; no accounts were created")
    accounts = json.loads(path.read_text(encoding="utf-8"))
    for role in ROUTES:
        account = accounts.get(role, {})
        if not account.get("email") or not account.get("password"):
            raise RuntimeError(f"Existing credentials for {role} are incomplete; no accounts were created")
    return accounts


def sanitizer(accounts: dict):
    secrets = [str(account.get(key, "")) for account in accounts.values()
               for key in ("email", "password") if account.get(key)]

    def clean(value) -> str:
        text = str(value)
        for secret in secrets:
            text = text.replace(secret, "[redacted]")
        text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[redacted-email]", text)
        text = re.sub(r"([?&](?:token|verify|reset|password|email)=)[^\s&#]+",
                      r"\1[redacted]", text, flags=re.IGNORECASE)
        return text[:2000]

    return clean


def instrument(context, clean):
    events = []
    blocked = []
    marker = {"page": "bootstrap"}

    def allow_read_only(route):
        request = route.request
        path = urlsplit(request.url).path
        if request.method not in {"GET", "HEAD", "OPTIONS"} and path not in {
            "/api/auth/login", "/api/auth/logout"
        }:
            blocked.append({"page": marker["page"], "method": request.method, "path": path})
            route.abort("blockedbyclient")
        else:
            route.continue_()

    context.route("**/*", allow_read_only)
    page = context.new_page()
    page.on("pageerror", lambda error: events.append({"page": marker["page"],
             "kind": "pageerror", "message": clean(error)}))

    def console(message):
        if message.type != "error":
            return
        text = message.text
        # Anonymous bootstrap deliberately asks /auth/me and receives 401.
        location = message.location.get("url", "")
        if "/api/auth/me" in location and "401" in text:
            return
        events.append({"page": marker["page"], "kind": "console", "message": clean(text)})

    def response(response):
        path = urlsplit(response.url).path
        if response.status >= 400 and not (path == "/api/auth/me" and response.status == 401):
            events.append({"page": marker["page"], "kind": "http", "status": response.status,
                           "path": clean(path)})

    page.on("console", console)
    page.on("response", response)
    return page, events, blocked, marker


def settle(page):
    page.wait_for_load_state("networkidle", timeout=30000)
    page.evaluate("() => document.fonts.ready")
    page.wait_for_timeout(250)
    page.locator(".loading").wait_for(state="hidden", timeout=30000)


def capture(page, output: Path, name: str) -> dict:
    settle(page)
    result = page.evaluate(LAYOUT_CHECK)
    result["page"] = name
    result["screenshot"] = name + ".png"
    result["error_boxes"] = page.locator(".error-box:visible").count()
    result["brand_present"] = page.locator(".brand, .login-product").filter(has_text="ПРУФ-ИТ").count() > 0
    result["passed"] = (not result["horizontal_overflow"] and not result["error_boxes"]
                        and result["brand_present"] and all(logo["loaded"] for logo in result["logos"]))
    page.screenshot(path=str(output / result["screenshot"]), full_page=False)
    if name.split("-")[1] in FULL_PAGE_ROUTES:
        result["full_screenshot"] = name + "-full.png"
        page.screenshot(path=str(output / result["full_screenshot"]), full_page=True)
    return result


def menu_close_check(page) -> dict:
    toggle = page.locator(".mobile-menu").first
    expect(toggle).to_be_visible()
    toggle.click()
    expect(page.locator(".sidebar.open")).to_be_visible()
    close = page.get_by_role("button", name=re.compile(r"Закрыть.*меню", re.IGNORECASE))
    if close.count():
        if close.first.get_attribute("class") == "sidebar-backdrop":
            # The backdrop covers the viewport, but its center can be behind the
            # drawer. Click its exposed right-hand edge as a real user would.
            close.first.click(position={"x": page.viewport_size["width"] - 16, "y": 100})
            method = "backdrop_edge"
        else:
            close.first.click()
            method = "close_button"
    else:
        toggle.click()
        method = "toggle"
    expect(page.locator(".sidebar")).not_to_have_class(re.compile(r"\bopen\b"))
    return {"opened": True, "closed": True, "method": method}


def navigate(page, role: str, route: str, mobile: bool):
    if mobile:
        page.locator(".mobile-menu").first.click()
        expect(page.locator(".sidebar.open")).to_be_visible()
    sidebar = page.locator(".sidebar")
    if route == "messages":
        button = sidebar.locator(".message-nav")
    elif route == "validation":
        button = sidebar.locator(".quality-link")
    else:
        button = sidebar.locator("nav > button").nth(ROUTES[role].index(route))
    button.click()
    expect(page).to_have_url(re.compile(r"#" + re.escape(route) + r"$"))
    if mobile:
        expect(sidebar).not_to_have_class(re.compile(r"\bopen\b"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("PROOFIT_URL", "http://127.0.0.1"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--viewports", help="Comma-separated widths to restrict the default matrix")
    parser.add_argument("--roles", default="employer,candidate")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    output = args.output or ROOT / "runtime" / ("proofit-ui-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    output.mkdir(parents=True, exist_ok=True)
    accounts = load_accounts()
    clean = sanitizer(accounts)
    widths = {int(width) for width in args.viewports.split(",")} if args.viewports else None
    viewports = [(w, h) for w, h in VIEWPORTS if widths is None or w in widths]
    roles = args.roles.split(",")
    if not viewports or any(role not in ROUTES for role in roles):
        parser.error("Select existing viewport widths and candidate/employer roles")
    report = {"base_url": base, "read_only_domain_data": True,
              "started_at": datetime.now().isoformat(timespec="seconds"),
              "checks": [], "browser_errors": [], "blocked_mutations": [], "failures": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        for width, height in viewports:
            context = browser.new_context(viewport={"width": width, "height": height},
                                          device_scale_factor=1)
            page, events, blocked, marker = instrument(context, clean)
            name = f"login-{width}x{height}"
            marker["page"] = name
            try:
                page.goto(base, wait_until="networkidle")
                expect(page.get_by_role("button", name="Войти в кабинет", exact=True)).to_be_visible()
                report["checks"].append(capture(page, output, name))
            except Exception as error:
                report["failures"].append({"page": name, "error": clean(error)})
            report["browser_errors"].extend(events)
            report["blocked_mutations"].extend(blocked)
            context.close()
        for role in roles:
            context = browser.new_context(viewport={"width": 1440, "height": 900},
                                          device_scale_factor=1)
            page, events, blocked, marker = instrument(context, clean)
            marker["page"] = role + "-login"
            try:
                page.goto(base, wait_until="networkidle")
                page.get_by_label("Email или имя", exact=True).fill(accounts[role]["email"])
                page.get_by_label("Пароль", exact=True).fill(accounts[role]["password"])
                page.get_by_role("button", name="Войти в кабинет", exact=True).click()
                expect(page.locator(".workspace-label")).to_have_text(
                    "КАБИНЕТ КАНДИДАТА" if role == "candidate" else "КАБИНЕТ РАБОТОДАТЕЛЯ")
                for width, height in viewports:
                    page.set_viewport_size({"width": width, "height": height})
                    settle(page)
                    mobile = width <= 700
                    if mobile:
                        marker["page"] = f"{role}-menu-{width}x{height}"
                        try:
                            menu = menu_close_check(page)
                            menu["page"] = marker["page"]
                            menu["passed"] = True
                            report["checks"].append(menu)
                        except Exception as error:
                            report["failures"].append({"page": marker["page"], "error": clean(error)})
                            # Recover the presentation state using the existing UI toggle.
                            if page.locator(".sidebar.open").count():
                                page.locator(".mobile-menu").first.click(force=True)
                    for route in ROUTES[role]:
                        if width == 768 and route not in TABLET_ROUTES[role]:
                            continue
                        name = f"{role}-{route}-{width}x{height}"
                        marker["page"] = name
                        try:
                            navigate(page, role, route, mobile)
                            check = capture(page, output, name)
                            if mobile:
                                check["navigation_closed_menu"] = not page.locator(".sidebar.open").count()
                            report["checks"].append(check)
                        except Exception as error:
                            report["failures"].append({"page": name, "error": clean(error)})
            except Exception as error:
                report["failures"].append({"page": role + "-login", "error": clean(error)})
            finally:
                try:
                    # Removes only the session established by this browser run.
                    page.request.post(base + "/api/auth/logout", headers={"Origin": base})
                except Exception:
                    pass
                report["browser_errors"].extend(events)
                report["blocked_mutations"].extend(blocked)
                context.close()
        browser.close()
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    report["passed"] = (not report["failures"] and not report["browser_errors"]
                        and not report["blocked_mutations"]
                        and all(check["passed"] for check in report["checks"]))
    report["summary"] = {"checks": len(report["checks"]),
                         "layout_failures": sum(not check["passed"] for check in report["checks"]),
                         "browser_errors": len(report["browser_errors"]),
                         "blocked_mutations": len(report["blocked_mutations"]),
                         "execution_failures": len(report["failures"])}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "summary": report["summary"],
                      "report": str(output / "report.json")}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
