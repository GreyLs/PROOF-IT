from scripts.private_runtime import private_file
"""Start the local compatibility-first microservice topology.

The public address is configured by BASE_URL and BIND_ADDR. The gateway forwards the
unchanged API contract to private loopback services; no browser route or
business handler changes as part of this topology change.
"""
from pathlib import Path
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
RUNTIME.mkdir(exist_ok=True)
API_BINARY = (ROOT / "target" / "release" / "fsp-trajectory.exe").resolve()
DOMAINS = (
    ("identity", 8082),
    ("talent", 8083),
    ("recruitment", 8084),
    ("documents", 8085),
    ("integrations", 8086),
    ("platform", 8087),
    ("intelligence", 8088),
)


def alive(url, host=None):
    try:
        request = urllib.request.Request(url, headers={"Host": host} if host else {})
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.HTTPError):
        return False


def request_json(url, payload=None, timeout=10):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def start(name, args, env=None):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    with (RUNTIME / (name + ".log")).open("ab") as log:
        process = subprocess.Popen(
            [str(value) for value in args], cwd=ROOT, stdout=log, stderr=log,
            stdin=subprocess.DEVNULL, creationflags=flags, env=env,
        )
    (RUNTIME / (name + ".pid")).write_text(str(process.pid), encoding="ascii")
    print(name, "PID", process.pid)


def stop_process(process):
    import psutil
    children = process.children(recursive=True)
    for child in children:
        child.terminate()
    process.terminate()
    _, remaining = psutil.wait_procs([process, *children], timeout=8)
    for item in remaining:
        item.kill()
    psutil.wait_procs(remaining, timeout=5)


def managed(name, predicate, freshness=0):
    """Return whether a recorded, current process belongs to this checkout."""
    import psutil
    pidfile = RUNTIME / (name + ".pid")
    try:
        process = psutil.Process(int(pidfile.read_text(encoding="ascii")))
    except (FileNotFoundError, ValueError, psutil.NoSuchProcess):
        return False
    if not predicate(process):
        # Windows can recycle a PID after a service exits. Discard only this
        # stale bookkeeping file; never touch the unrelated live process.
        pidfile.unlink(missing_ok=True)
        return False
    if process.create_time() >= freshness:
        return True
    stop_process(process)
    pidfile.unlink(missing_ok=True)
    print(name, "restarted after code/configuration change")
    return False


def api_process(role):
    def check(process):
        try:
            return (
                Path(process.exe()).resolve() == API_BINARY
                and Path(process.cwd()).resolve() == ROOT
                and process.environ().get("FSP_SERVICE") == role
            )
        except OSError:
            return False
    return check


def fresh_api(name, role, bind, configuration):
    public_config=private_file("public-settings.json")
    newest = max(API_BINARY.stat().st_mtime, (ROOT / ".env").stat().st_mtime, Path(__file__).stat().st_mtime, public_config.stat().st_mtime if public_config.exists()else 0)
    if managed(name, api_process(role), newest):
        return
    if alive(f"http://{bind}/api/health", urlsplit(configuration["BASE_URL"]).netloc):
        raise RuntimeError(f"Address {bind} belongs to a process outside the managed {role} service")
    environment = {**os.environ}
    environment.update({key: configuration[key] for key in (
        "OLLAMA_URL", "OLLAMA_MODEL", "FSP_REQUIRE_GPU", "FSP_GPU_MIN_OFFLOAD_PERCENT",
        "FSP_OLLAMA_KEEP_ALIVE", "FSP_FORECAST_URL", "DATABASE_PARALLEL_WORKERS",
    ) if configuration.get(key)})
    for key in ('FSP_OIDC_ISSUER','FSP_REGISTRY_URL','DREAMJOB_PARTNER_URL','FSP_KEYCLOAK_URL','TRUST_CLOUDFLARE_LOCAL_TUNNEL'):
        if configuration.get(key):environment[key]=configuration[key]
    environment.update(
        FSP_SERVICE=role, BIND_ADDR=bind, BASE_URL=configuration["BASE_URL"], DATABASE_MAX_CONNECTIONS="4",
    )
    if role != "gateway":
        environment["TRUSTED_PROXY_IPS"] = "127.0.0.1"
    start(name, [API_BINARY], env=environment)


def old_single_api():
    """Release the old monolith listener before starting the gateway."""
    import psutil
    pidfile = RUNTIME / "api.pid"
    try:
        process = psutil.Process(int(pidfile.read_text(encoding="ascii")))
    except (FileNotFoundError, ValueError, psutil.NoSuchProcess):
        return
    try:
        owned = Path(process.exe()).resolve() == API_BINARY and Path(process.cwd()).resolve() == ROOT
    except OSError:
        owned = False
    if not owned:
        raise RuntimeError("api: PID no longer belongs to this project")
    stop_process(process)
    pidfile.unlink(missing_ok=True)
    print("api replaced by api-gateway and domain services")


def fresh_python(name, module, token):
    import psutil
    newest = max(path.stat().st_mtime for path in (ROOT / "worker").glob("*.py"))
    def check(process):
        try:
            environment = process.environ()
            current = environment.get("PROCESSOR_TOKEN", "")
            if environment.get("PROCESSOR_TOKEN_FILE"):
                current = Path(environment["PROCESSOR_TOKEN_FILE"]).read_text(encoding="utf-8").strip()
            return (
                module in process.cmdline() and Path(process.cwd()).resolve() == ROOT
                and secrets.compare_digest(current, token)
            )
        except (OSError, psutil.Error):
            return False
    return managed(name, check, newest)


def fresh_forecast(configuration):
    import psutil
    source = ROOT / "ml_time_forecasting"
    artifacts = source / "artifacts"
    required = (artifacts / "model_manifest.json", artifacts / "vacancy_fill.cbm", artifacts / "candidate_job_search.cbm")
    if not all(path.exists() for path in required):
        raise RuntimeError("Forecast models are missing; run: .\\.venv\\Scripts\\python.exe -m ml_time_forecasting.train")
    newest = max(path.stat().st_mtime for path in [*source.glob("*.py"), *required])
    def check(process):
        try:
            return "ml_time_forecasting.service" in process.cmdline() and Path(process.cwd()).resolve() == ROOT
        except (OSError, psutil.Error):
            return False
    if managed("forecast", check, newest):
        return
    endpoint = configuration["FSP_FORECAST_URL"].rstrip("/")
    bind = endpoint.removeprefix("http://").removeprefix("https://")
    if alive(endpoint + "/health"):
        raise RuntimeError("Forecast port belongs to a process outside this project")
    start("forecast", [sys.executable, "-m", "ml_time_forecasting.service"], env={**os.environ, "FORECAST_BIND_ADDR": bind, "PYTHONUTF8": "1"})
    for _ in range(40):
        if alive(endpoint + "/health"):
            return
        time.sleep(0.25)
    raise RuntimeError("Forecast service did not become ready")


def ensure_ollama(configuration):
    endpoint = configuration.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    model = configuration.get("OLLAMA_MODEL", "qwen3:8b")
    if not alive(endpoint + "/api/tags"):
        executable = shutil.which("ollama")
        if not executable:
            raise RuntimeError("Ollama is required but was not found on PATH")
        def ollama_process(process):
            try:
                return Path(process.exe()).resolve() == Path(executable).resolve() and "serve" in process.cmdline()
            except OSError:
                return False
        if not managed("ollama", ollama_process):
            environment = {**os.environ, "OLLAMA_KEEP_ALIVE": "-1m"}
            start("ollama", [executable, "serve"], env=environment)
        for _ in range(80):
            if alive(endpoint + "/api/tags"):
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("Ollama did not become ready")
    tags = request_json(endpoint + "/api/tags")
    names = {str(item.get("name", "")) for item in tags.get("models", [])}
    if model not in names:
        raise RuntimeError(f"Required local model {model} is not installed; run: ollama pull {model}")
    # An ASCII, one-token probe warms the actual model without terminal encoding
    # being able to affect the readiness assertion.
    request_json(endpoint + "/api/chat", {
        "model": model, "messages": [{"role": "user", "content": "READY"}], "stream": False, "think": False,
        "keep_alive": "-1m", "options": {"num_gpu": 999, "temperature": 0, "seed": 42, "num_predict": 1},
    }, timeout=180)
    active = request_json(endpoint + "/api/ps").get("models", [])
    placement = next((item for item in active if item.get("name") == model or item.get("model") == model), None)
    total = int((placement or {}).get("size", 0))
    vram = int((placement or {}).get("size_vram", 0))
    threshold = int(configuration.get("FSP_GPU_MIN_OFFLOAD_PERCENT", "100"))
    if not placement or not total or not vram or vram * 100 < total * threshold:
        raise RuntimeError(f"{model} is not fully offloaded to GPU (vram={vram}, total={total})")
    print(f"Qwen ready: {model}; GPU offload {vram * 100 // total}%")


def main():
    configuration = dotenv_values(ROOT / ".env")
    overrides = private_file("public-settings.json")
    if overrides.exists():
        values=json.loads(overrides.read_text(encoding="utf-8"))
        allowed={'BASE_URL','BIND_ADDR','FSP_OIDC_ISSUER','TRUST_CLOUDFLARE_LOCAL_TUNNEL'}
        if set(values)-allowed:raise RuntimeError('Unexpected public runtime setting')
        configuration.update(values)
    public_bind = configuration.get("BIND_ADDR") or "127.0.0.1:80"
    public_url = (configuration.get("BASE_URL") or "http://127.0.0.1").rstrip("/")
    configuration["BASE_URL"] = public_url
    configuration["FSP_FORECAST_URL"] = (configuration.get("FSP_FORECAST_URL") or "http://127.0.0.1:8090").rstrip("/")
    public_host = urlsplit(public_url).netloc
    public_health = f"http://{public_bind}/api/health"
    cpu_only = "--cpu-only" in sys.argv
    if not cpu_only: ensure_ollama(configuration)
    fresh_forecast(configuration)
    if not cpu_only:
        review_endpoint = configuration.get("CODE_REVIEW_OLLAMA_URL", "http://127.0.0.1:11435")
        if not alive(review_endpoint + "/api/tags"):
            review_binary = ROOT / ".tools/ollama-review/ollama.exe"
            if review_binary.exists():
                review_env = {**os.environ,"OLLAMA_HOST":urlsplit(review_endpoint).netloc,"OLLAMA_MAX_LOADED_MODELS":"1"}
                start("ollama-review",[review_binary,"serve"],env=review_env)
            for _ in range(40):
                if alive(review_endpoint + "/api/tags"):
                    break
                time.sleep(0.25)
        review_model = configuration.get("CODE_REVIEW_MODEL", "gpt-oss:20b")
        review_names = {item.get("name") for item in request_json(review_endpoint + "/api/tags").get("models",[])}
        if review_model not in review_names:
            raise RuntimeError(f"Required code review model {review_model} is missing")
        small_model = configuration.get("VACANCY_MODEL", "qwen2.5:3b")
        small_names = {item.get("name") for item in request_json(configuration.get("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/tags").get("models",[])}
        if small_model not in small_names:
            raise RuntimeError(f"Required vacancy model is missing; run: ollama pull {small_model}")
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Docker Desktop is required for the isolated code sandbox")
    flags = getattr(subprocess,"CREATE_NO_WINDOW",0)
    if subprocess.run([docker,"info","--format","{{.ServerVersion}}"],capture_output=True,timeout=15,creationflags=flags).returncode:
        raise RuntimeError("Start Docker Desktop: isolated sandbox engine is not ready")
    if subprocess.run([docker,"image","inspect","python:3.12-alpine"],capture_output=True,timeout=15,creationflags=flags).returncode:
        raise RuntimeError("Sandbox image is missing; run: docker pull python:3.12-alpine")
    if subprocess.run([docker,"image","inspect","node:24-alpine"],capture_output=True,timeout=15,creationflags=flags).returncode:
        raise RuntimeError("TypeScript sandbox image is missing; run: docker pull node:24-alpine")
    workbench_file = RUNTIME / "workbench.secret"
    if not workbench_file.exists():
        workbench_file.write_text(secrets.token_hex(32), encoding="ascii")
    workbench_allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "COMSPEC", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG"}
    workbench_env = {key:value for key,value in os.environ.items() if key.upper() in workbench_allowed}
    workbench_env.update(WORKBENCH_TOKEN_FILE=str(workbench_file), PYTHONUTF8="1")
    for key in ("OLLAMA_URL", "OLLAMA_MODEL", "VACANCY_MODEL", "CODE_REVIEW_MODEL", "CODE_REVIEW_OLLAMA_URL"):
        if configuration.get(key):
            workbench_env[key] = configuration[key]
    def workbench_owned(process):
        return "worker.workbench" in process.cmdline() and Path(process.cwd()).resolve() == ROOT
    newest_workbench = max(p.stat().st_mtime for p in (ROOT/"worker/workbench.py",ROOT/".env",Path(__file__)))
    if not managed("workbench", workbench_owned, newest_workbench):
        start("workbench", [sys.executable, "-m", "worker.workbench"], env=workbench_env)
    token_file = RUNTIME / "processor.secret"
    if not token_file.exists():
        token_file.write_text(secrets.token_hex(32), encoding="ascii")
    token = token_file.read_text(encoding="ascii").strip()
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL"}
    processor_env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    processor_env.update({key: configuration[key] for key in (
        "OLLAMA_URL", "OLLAMA_MODEL", "FSP_REQUIRE_GPU", "FSP_GPU_MIN_OFFLOAD_PERCENT",
        "FSP_OLLAMA_KEEP_ALIVE", "TESSERACT_CMD",
    ) if configuration.get(key)})
    processor_env.update(PROCESSOR_TOKEN_FILE=str(token_file), PYTHONUTF8="1", OMP_THREAD_LIMIT="2")
    if not fresh_python("processor", "worker.processor_service", token):
        if alive("http://127.0.0.1:8081/health"):
            raise RuntimeError("Port 8081 belongs to a process outside the managed processor")
        start("processor", [sys.executable, "-m", "worker.processor_service"], env=processor_env)
    old_single_api()
    intelligence_file = RUNTIME / "intelligence.secret"
    if not intelligence_file.exists():
        intelligence_file.write_text(secrets.token_hex(32), encoding="ascii")
    intelligence_env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    intelligence_env.update(INTELLIGENCE_TOKEN_FILE=str(intelligence_file), PYTHONUTF8="1")
    for key in ("FSP_OIDC_ISSUER","FSP_OIDC_CLIENT_ID","FSP_OIDC_CLIENT_SECRET","FSP_OIDC_CLIENT_SECRET_FILE","FSP_REGISTRY_URL","FSP_REGISTRY_TOKEN_FILE","DREAMJOB_PARTNER_URL","DREAMJOB_PARTNER_TOKEN_FILE","PASSPORT_KEY_FILE","GITHUB_PUBLIC_TOKEN_FILE","MOEX_RIGHTS_MANIFEST_FILE"):
        if configuration.get(key):intelligence_env[key]=configuration[key]
    if configuration.get("REDIS_URL"):
        intelligence_env["REDIS_URL"] = configuration["REDIS_URL"]
    def intelligence_owned(process):
        return "intelligence.service" in process.cmdline() and Path(process.cwd()).resolve() == ROOT
    newest_intelligence = max([p.stat().st_mtime for p in (ROOT / "intelligence").glob("*.py")]+[Path(__file__).stat().st_mtime,(ROOT/'.env').stat().st_mtime,overrides.stat().st_mtime if overrides.exists()else 0])
    if not managed("intelligence-engine", intelligence_owned, newest_intelligence):
        start("intelligence-engine", [sys.executable, "-m", "intelligence.service"], env=intelligence_env)
    for _ in range(40):
        if alive("http://127.0.0.1:8092/health"):
            break
        time.sleep(.25)
    else:
        raise RuntimeError("Intelligence engine did not become ready")
    for role, port in DOMAINS:
        fresh_api("api-" + role, role, f"127.0.0.1:{port}", configuration)
    for role, port in DOMAINS:
        for _ in range(40):
            if alive(f"http://127.0.0.1:{port}/api/health"):
                break
            time.sleep(0.25)
        else:
            raise RuntimeError(f"{role} did not become ready")
    fresh_api("api-gateway", "gateway", public_bind, configuration)
    worker_env = {**os.environ, "PROCESSOR_TOKEN_FILE": str(token_file), "PROCESSOR_URL": "http://127.0.0.1:8081"}
    worker_env.update({key: configuration[key] for key in (
        "OLLAMA_URL", "OLLAMA_MODEL", "FSP_REQUIRE_GPU", "FSP_GPU_MIN_OFFLOAD_PERCENT", "FSP_OLLAMA_KEEP_ALIVE", "FSP_FORECAST_URL",
    ) if configuration.get(key)})
    if not fresh_python("worker", "worker.main", token):
        start("worker", [sys.executable, "-m", "worker.main"], env=worker_env)
    for _ in range(40):
        if alive(public_health, public_host):
            break
        time.sleep(0.25)
    print("Health:", alive(public_health, public_host))
    print("Interface:", public_url)


if __name__ == "__main__":
    main()
