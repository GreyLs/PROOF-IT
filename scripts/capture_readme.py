"""Capture the real interface using disposable, explicitly synthetic identities.

Run against a prepared demonstration installation, never against production.
The qualification run follows the API and uses server-side test keys/timing only
for these disposable fixtures. It is not evidence of human certification.
No response interception, DOM substitutions or existing images are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from psycopg.rows import dict_row

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=REPO)
    args = parser.parse_args()
    source = args.runtime_root.resolve()
    sys.path.insert(0, str(source))
    from scripts.workbench_test_fixture import Fixture
    from intelligence import professional

    fixture = Fixture()
    fixture.db.row_factory = dict_row
    origin = fixture.cfg["BASE_URL"].rstrip("/")
    output = REPO / "docs/assets/screenshots"
    output.mkdir(parents=True, exist_ok=True)
    rows, errors, failed_requests = [], [], []
    secret_values = [origin]

    def safe(value):
        result = str(value)
        for secret in secret_values:
            result = result.replace(secret, "[private]")
        return result

    def api(client, method, path, body=None):
        response = client.request(method, path, json=body)
        if response.status_code >= 400:
            raise RuntimeError(f"{method} {path}: {response.status_code}: {safe(response.text[:400])}")
        return response.json()

    def ready(page):
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(650)
        expect(page.locator(".error-box:visible")).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")

    def capture(page, name, role, route, state, full_page=False):
        ready(page)
        path = output / name
        page.screenshot(path=str(path), full_page=full_page)
        rows.append({"file": str(path.relative_to(REPO)).replace("\\", "/"),
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "role": role, "route": "/proofit" + ("#" + route if route else ""),
                     "state": state, "viewport": page.viewport_size,
                     "full_page": full_page, "synthetic_fixture": role != "anonymous",
                     "browser_errors": len(errors), "visible_error_boxes": 0,
                     "horizontal_overflow": False})
        print(json.dumps({"captured": name, "role": role}), flush=True)

    try:
        candidate, cu = fixture.register("candidate")
        employer, eu = fixture.register("employer")
        secret_values.extend([candidate.headers["Authorization"], employer.headers["Authorization"]])
        fixture.db.execute("UPDATE candidates SET display_name=%s,full_name=%s,consent_publication=true WHERE id=%s",
                           ("Демонстрационный кандидат", "Демонстрационный кандидат", cu["subject_id"]))
        fixture.db.execute("UPDATE companies SET name=%s,contact=%s,description=%s WHERE id=%s",
                           ("PROOF-IT · Демо-команда", "Демонстрационная связь",
                            "Учебная команда для проверки сценария обратного найма.", eu["subject_id"]))
        resume = api(candidate, "POST", "/resumes", {
            "target_position": "Python Backend Developer", "specialization": "backend_python",
            "declared_grade": "middle", "experience_years": 4,
            "skills": ["Python", "SQL", "PostgreSQL"],
            "about": "Проектирование REST API, оптимизация SQL и тестирование сервисов. Демонстрационные данные.",
            "expected_salary": 180000, "work_format": "удалённо", "visibility": "employer_searchable"
        })["resume"]
        rid = resume["id"]
        vacancy = api(employer, "POST", "/vacancies", {
            "title": "Python Backend Developer", "description": "Разработка API и сервисов: Python, PostgreSQL, тесты и командная работа. Демонстрационная вакансия.",
            "specialization": "backend_python", "grade": "middle", "skills": ["Python", "SQL", "PostgreSQL"],
            "salary_from": 180000, "salary_to": 240000, "work_format": "удалённо", "status": "published"
        })["vacancy"]
        deadline = time.monotonic() + 180
        while True:
            test = api(candidate, "GET", f"/resumes/{rid}/test")
            if test["status"] == "ready":
                break
            if test.get("generation_status") == "failed" or time.monotonic() > deadline:
                raise RuntimeError("Qualification preparation did not reach ready state")
            time.sleep(2)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)

            def context(client=None, mobile=False):
                ctx = browser.new_context(
                    viewport={"width": 390 if mobile else 1440, "height": 1000 if mobile else 1050},
                    device_scale_factor=1, locale="ru-RU", timezone_id="Europe/Moscow",
                    extra_http_headers={"Authorization": client.headers["Authorization"]} if client else {})
                page = ctx.new_page()
                page.on("pageerror", lambda error: errors.append(safe(error)))
                page.on("requestfailed", lambda request: failed_requests.append({
                    "path": request.url.replace(origin, ""), "failure": safe(request.failure)}))
                return ctx, page

            anonymous_ctx, login = context()
            login.goto(origin + "/proofit", wait_until="networkidle")
            expect(login.locator(".login-story h1")).to_contain_text("Те самые люди")
            login.wait_for_function('()=>document.querySelector("video")?.readyState>=2')
            capture(login, "01-login.png", "anonymous", "", "Current login heading and real animated background")
            anonymous_ctx.close()

            candidate_ctx, page = context(candidate)
            page.goto(origin + "/proofit#resumes", wait_until="networkidle")
            expect(page.locator(".qualification-card")).to_contain_text("Готов к прохождению")
            capture(page, "02-resume.png", "candidate", "resumes", "Published-intent resume before knowledge validation; pending admission")
            page.get_by_role("button", name="Начать тест", exact=True).click()
            expect(page.locator(".qualification-question")).to_be_visible()
            page.locator(".qualification-card").evaluate("e=>window.scrollTo(0,Math.max(0,e.getBoundingClientRect().top+scrollY-400))")
            capture(page, "03-assessment.png", "candidate", "resumes", "One real adaptive knowledge question; no answer key exposed")

            state = api(candidate, "GET", f"/resumes/{rid}/test")
            while state["status"] == "in_progress":
                row = fixture.db.execute("SELECT contract FROM qualification_tests WHERE resume_id=%s", (rid,)).fetchone()
                question = professional.next_item(row["contract"])
                assert state["question_id"] == question["id"] and len(state["questions"]) == 1
                index = len(row["contract"]["answers"])
                elapsed_ms = 10000 + 1700 * (index % 5) + 2300 * (index % 3)
                fixture.db.execute("UPDATE qualification_tests SET item_started_at=now()-(%s*interval '1 millisecond') WHERE resume_id=%s", (elapsed_ms, rid))
                state = api(candidate, "POST", f"/resumes/{rid}/test/submit", {
                    "question_id": question["id"], "revision": state["revision"], "answers": [[question["correct"]]]})
            assert state["passed"] and state["score"] == 100
            qualification = {"scope": "synthetic API exercise of role-knowledge issuance, not human certification",
                             "questions": len(state["review"]["questions"]), "score": state["score"],
                             "controlled_server_timing": True, "server_side_test_keys": True}

            page.goto(origin + "/proofit#proof-graph", wait_until="networkidle")
            expect(page.locator(".graph-explorer")).to_be_visible()
            page.get_by_label("Найти навык в графе", exact=True).fill("python")
            expect(page.locator(".graph-source-card").first).to_be_visible()
            page.evaluate("window.scrollTo(0,0)")
            capture(page, "04-proof-graph.png", "candidate", "proof-graph", "Python path linked to the certificate from the synthetic API exercise", full_page=True)

            page.goto(origin + "/proofit#horizon", wait_until="networkidle")
            expect(page.locator(".twin-overview")).to_be_visible()
            page.get_by_role("slider", name="Ответ в течение", exact=True).fill("1")
            page.get_by_role("slider", name="Этапы интервью", exact=True).fill("2")
            page.get_by_role("button", name="Рассчитать сценарий", exact=True).click()
            expect(page.locator(".twin-comparison")).to_be_visible(timeout=60000)
            assert page.locator(".twin-compare-grid article").count() == 2
            page.locator(".horizon-layout").evaluate("e=>window.scrollTo(0,Math.max(0,e.getBoundingClientRect().top+scrollY-85))")
            capture(page, "05-digital-twin.png", "candidate", "horizon", "Actual CPU scenario job: response in 1 day and 2 interview stages versus baseline; distributions are not calibrated hiring probabilities")

            employer_ctx, search = context(employer)
            search.goto(origin + "/proofit#search", wait_until="networkidle")
            search.get_by_role("combobox", name="Вакансия или потребность", exact=True).select_option(vacancy["id"])
            search.get_by_label("Поиск по навыку или ID", exact=True).fill(cu["subject_id"])
            expect(search.locator(".candidate-card")).to_have_count(1, timeout=30000)
            capture(search, "06-employer-search.png", "employer", "search", "Own vacancy and synthetic candidate only; actual eligibility and matching filters")
            search.get_by_role("button", name="Пригласить", exact=True).click()
            expect(search.get_by_role("heading", name="Начните диалог с предложения", exact=True)).to_be_visible()
            search.get_by_label("Название предложения", exact=True).fill("Python Backend Developer · Middle")
            search.get_by_label("Команда, задачи и условия", exact=True).fill(
                "Разработка API на Python, работа с PostgreSQL и тестами. Удалённый формат, команда из пяти разработчиков. Демонстрационное предложение.")
            search.get_by_label("Зарплата от, ₽ / месяц", exact=True).fill("180000")
            search.get_by_label("Зарплата до, ₽ / месяц", exact=True).fill("240000")
            capture(search, "07-employer-offer.png", "employer", "search", "Salary range and conditions before sending an internal synthetic invitation")
            search.get_by_role("button", name="Отправить приглашение", exact=True).click()
            expect(search.get_by_role("heading", name="Начните диалог с предложения", exact=True)).to_have_count(0)
            invitations = api(candidate, "GET", "/invitations")["items"]
            assert len(invitations) == 1

            mobile_ctx, mobile = context(candidate, mobile=True)
            mobile.goto(origin + "/proofit#invitations", wait_until="networkidle")
            expect(mobile.locator("main")).to_contain_text("Python Backend Developer")
            capture(mobile, "08-candidate-offer-mobile.png", "candidate", "invitations", "Received synthetic invitation on mobile; candidate retains the accept/decline decision", full_page=True)
            mobile_ctx.close()
            employer_ctx.close()
            candidate_ctx.close()
            version = browser.version
            browser.close()
        assert not errors, errors
        assert not failed_requests, failed_requests
        source_hash = hashlib.sha256()
        for file in sorted((source / "web/src").rglob("*")):
            if file.is_file():
                source_hash.update(file.relative_to(source).as_posix().encode())
                source_hash.update(file.read_bytes())
        report = {"generated_at": datetime.now(timezone.utc).isoformat(), "browser": "Chromium " + version,
                  "method": "New browser captures of real live routes; no screenshots reused, no mocked network or edited DOM",
                  "origin": "Private demonstration installation; address intentionally omitted",
                  "web_source_sha256": source_hash.hexdigest(), "qualification_fixture": qualification,
                  "synthetic_users": True, "screenshots": rows, "browser_errors": errors,
                  "failed_requests": failed_requests, "passed": True,
                  "cleanup": "Exact-ID fixture identities, data and sessions removed after capture"}
    finally:
        fixture.close()
    (output / "capture.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "screenshots": len(rows), "browser_errors": len(errors), "cleanup": True}))


if __name__ == "__main__":
    main()
