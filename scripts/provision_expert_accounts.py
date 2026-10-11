"""Provision the two public, local-demo accounts used by hackathon reviewers.

This utility deliberately refuses a non-demo server: these credentials are for the
local review stand only and must never be provisioned on a production installation.
"""
import httpx


ORIGIN = "http://localhost:8080"
API = f"{ORIGIN}/api"
ACCOUNTS = (
    {
        "role": "candidate",
        "email": "expert.candidate@fsp.test",
        "password": "Fsp!Candidate2026",
        "name": "Эксперт Кандидат",
    },
    {
        "role": "employer",
        "email": "expert.employer@fsp.test",
        "password": "Fsp!Employer2026",
        "name": "Эксперт Работодатель",
    },
)


def login(client: httpx.Client, account: dict) -> httpx.Response:
    return client.post(
        "/auth/login",
        json={"identifier": account["email"], "password": account["password"]},
    )


def main() -> None:
    with httpx.Client(base_url=API, headers={"Origin": ORIGIN}, timeout=30) as client:
        meta = client.get("/meta")
        assert meta.status_code == 200 and meta.json().get("demo"), (
            "Expert accounts can only be provisioned on the local demo stand."
        )
        completed = []
        for account in ACCOUNTS:
            response = login(client, account)
            if response.status_code == 200:
                assert response.json()["user"]["role"] == account["role"]
                assert client.post("/auth/logout").status_code == 200
                completed.append(f"{account['role']}: existing")
                continue
            assert response.status_code == 401, response.text
            registration = client.post(
                "/auth/register",
                json={**account, "consent_processing": True},
            )
            assert registration.status_code == 200, registration.text
            token = registration.json().get("development_mail", {}).get("token")
            assert token, "The review stand did not return a confirmation token."
            verified = client.post("/auth/verify", json={"token": token})
            assert verified.status_code == 200, verified.text
            assert verified.json()["user"]["role"] == account["role"]
            assert client.post("/auth/logout").status_code == 200
            completed.append(f"{account['role']}: created")
        for account in ACCOUNTS:
            for identifier in (account["email"], account["name"]):
                response = client.post(
                    "/auth/login",
                    json={"identifier": identifier, "password": account["password"]},
                )
                assert response.status_code == 200, response.text
                assert response.json()["user"]["role"] == account["role"]
                assert client.post("/auth/logout").status_code == 200
    print("Expert review accounts: " + "; ".join(completed))


if __name__ == "__main__":
    main()
