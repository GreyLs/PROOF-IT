"""Feature/browser verification at 1440/390 px; no load testing."""
import json
import time
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from scripts.workbench_test_fixture import Fixture
from scripts.check_proofit_ui import LAYOUT_CHECK, settle
from tests.test_workbench import VACANCY

ROOT=Path(__file__).resolve().parents[1]


def main():
    fixture=Fixture();report={"checks":[],"browser_errors":[],"capacity_test_run":False,"started_at":time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    out=ROOT/"validation/reports/current/horizon-ui";out.mkdir(parents=True,exist_ok=True)
    try:
        c,cu=fixture.register("candidate");e,eu=fixture.register("employer")
        rid="HR"+uuid.uuid4().hex
        fixture.db.execute("INSERT INTO resume_profiles(id,candidate_id,target_position,specialization,declared_grade,experience_years,skills,about,expected_salary,work_format,visibility,status) VALUES(%s,%s,'Python Backend Developer','backend_python','middle',3,ARRAY['Python','SQL','PostgreSQL'],'Разработка API и транзакционных сервисов с тестами.',180000,'удалённо','private','draft')",(rid,cu["subject_id"]))
        v=e.post("/vacancies",json=VACANCY);v.raise_for_status()
        with sync_playwright() as p:
            browser=p.chromium.launch()
            for width,height in ((1440,1000),(390,844)):
                for role,client in (("candidate",c),("employer",e)):
                    ctx=browser.new_context(viewport={"width":width,"height":height},extra_http_headers={"Authorization":client.headers["Authorization"]})
                    page=ctx.new_page();page.on("pageerror",lambda error:report["browser_errors"].append(str(error)))
                    def capture(name):
                        settle(page)
                        expect(page.locator("main h1").first).to_be_visible()
                        layout=page.evaluate(LAYOUT_CHECK)
                        layout.update(name=f"{role}-{name}-{width}",passed=not layout["horizontal_overflow"] and not page.locator(".error-box:visible").count())
                        report["checks"].append(layout)
                        page.screenshot(path=str(out/(layout["name"]+".png")),full_page=False)
                        assert layout["passed"],layout
                    page.goto(fixture.cfg["BASE_URL"]+"/#horizon");settle(page)
                    expect(page.get_by_label("Расширение формата работы",exact=True)).to_have_value("1")
                    page.get_by_role("button",name="Рассчитать сценарий",exact=True).click()
                    expect(page.locator(".horizon-curve")).to_be_visible(timeout=30000);capture("horizon")
                    if role=="candidate":
                        page.goto(fixture.cfg["BASE_URL"]+"/#proof-graph");expect(page.locator(".proof-graph")).to_be_visible();capture("proof-graph")
                        page.goto(fixture.cfg["BASE_URL"]+"/#career-route");page.get_by_role("button",name="Создать мой маршрут",exact=True).click()
                        expect(page.locator(".career-timeline")).to_be_visible(timeout=30000);capture("career-route")
                        page.goto(fixture.cfg["BASE_URL"]+"/#arena");page.get_by_role("button",name="SQL Запросы и крайние случаи").click()
                        expect(page.locator("#arena-code")).to_be_visible(timeout=30000)
                        page.locator("#arena-code").fill("WITH f AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY event_key ORDER BY id) rn FROM events) SELECT a.name,COALESCE(SUM(e.value),0) FROM accounts a LEFT JOIN f e ON e.account_id=a.id AND e.rn=1 GROUP BY a.id,a.name ORDER BY a.name")
                        page.get_by_role("button",name="Запустить",exact=True).click()
                        expect(page.get_by_role("heading",name="Открытые тесты: 2/2",exact=True)).to_be_visible(timeout=30000);capture("sql-arena")
                    else:
                        page.goto(fixture.cfg["BASE_URL"]+"/#strategy");page.get_by_label("Дополнительный бюджет",exact=True).fill("30000")
                        page.get_by_role("button",name="Построить план найма",exact=True).click()
                        expect(page.locator(".strategy-table tbody tr")).to_have_count(1,timeout=30000);capture("strategy")
                    ctx.close()
            browser.close()
        report["passed"]=all(x["passed"]for x in report["checks"]) and not report["browser_errors"]
    except Exception as error:
        report["passed"]=False;report["error_type"]=type(error).__name__;raise
    finally:
        fixture.close();(ROOT/"validation/reports/current/horizon-browser.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"passed":report.get("passed"),"checks":len(report["checks"]),"browser_errors":len(report["browser_errors"])}))

if __name__=="__main__":main()
