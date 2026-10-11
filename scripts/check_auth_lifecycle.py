"""Fast acceptance check for registration, logout and login by email or displayed name."""
from pathlib import Path
import json
import uuid

import httpx
from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:8080"
API = f"{ORIGIN}/api"
PASSWORD = "Lifecycle-Only-2026"


def payload(role: str, name: str, email: str) -> dict:
    return {
        "email": email,
        "password": PASSWORD,
        "role": role,
        "name": name,
        "consent_processing": True,
    }


def check_api_role(role: str) -> str:
    suffix = uuid.uuid4().hex
    name = f"Проверка {'кандидат' if role == 'candidate' else 'работодатель'} {suffix}"
    email = f"auth-lifecycle-{suffix}@example.test"
    with httpx.Client(base_url=API, headers={"Origin": ORIGIN}, timeout=30) as client:
        registered = client.post("/auth/register", json=payload(role, name, email))
        assert registered.status_code == 200, registered.text
        token = registered.json()["development_mail"]["token"]
        assert client.post("/auth/login", json={"identifier": email, "password": PASSWORD}).status_code == 403
        assert client.post("/auth/verify", json={"token": token}).status_code == 200
        assert client.post("/auth/logout").status_code == 200
        by_email = client.post("/auth/login", json={"identifier": email, "password": PASSWORD})
        assert by_email.status_code == 200, by_email.text
        assert by_email.json()["user"]["role"] == role
        assert client.post("/auth/logout").status_code == 200
        by_name = client.post("/auth/login", json={"identifier": name, "password": PASSWORD})
        assert by_name.status_code == 200, by_name.text
        assert by_name.json()["user"]["role"] == role
        assert client.post("/auth/logout").status_code == 200
        assert client.get("/auth/me").status_code == 401
        assert client.post("/auth/login", json={"identifier": name, "password": PASSWORD}).status_code == 200
        deleted = client.request("DELETE", "/account", json={"password": PASSWORD})
        assert deleted.status_code == 200, deleted.text
        assert client.post("/auth/login", json={"identifier": email, "password": PASSWORD}).status_code == 401
    return role


def check_browser_candidate() -> None:
    suffix = uuid.uuid4().hex
    name = f"Проверка интерфейса {suffix}"
    email = f"ui-auth-lifecycle-{suffix}@example.test"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(ORIGIN, wait_until="networkidle")
        page.get_by_role("button", name="Регистрация", exact=True).click()
        page.get_by_role("button", name="Кандидат", exact=True).click()
        page.get_by_label("Ваше имя", exact=True).fill(name)
        page.get_by_label("Электронная почта", exact=True).fill(email)
        page.get_by_label("Пароль", exact=False).fill(PASSWORD)
        page.get_by_role("checkbox").check()
        page.get_by_role("button", name="Создать аккаунт", exact=True).click()
        page.get_by_role("button", name="Открыть письмо и подтвердить", exact=False).click()
        expect(page.locator(".workspace-label")).to_have_text("КАБИНЕТ КАНДИДАТА")
        page.get_by_role("button", name="Выйти", exact=True).click()
        page.get_by_label("Email или имя", exact=True).fill(name)
        page.get_by_label("Пароль", exact=True).fill(PASSWORD)
        page.get_by_role("button", name="Войти в кабинет", exact=True).click()
        expect(page.locator(".workspace-label")).to_have_text("КАБИНЕТ КАНДИДАТА")
        deleted = page.request.delete(
            f"{API}/account", data={"password": PASSWORD}, headers={"Origin": ORIGIN}
        )
        assert deleted.ok, deleted.status
        browser.close()


def main() -> None:
    roles = [check_api_role("candidate"), check_api_role("employer")]
    check_browser_candidate()
    report = {
        "passed": True,
        "checks": [
            f"API registration, verification, logout and login by email/name: {', '.join(roles)}",
            "Browser registration, confirmation, logout and login by displayed name: candidate",
        ],
    }
    (ROOT / "docs" / "auth-lifecycle-check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
