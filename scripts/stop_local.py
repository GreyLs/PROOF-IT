"""Stop only processes proven to have been started by this checkout."""
from pathlib import Path
import psutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
API_BINARY = (ROOT / "target" / "release" / "fsp-trajectory.exe").resolve()


def owns(name, process):
    try:
        if name.startswith("api"):
            return Path(process.exe()).resolve() == API_BINARY and Path(process.cwd()).resolve() == ROOT
        if name in ("ollama", "ollama-review"):
            return "serve" in process.cmdline() and Path(process.cwd()).resolve() == ROOT
        module = "intelligence.service" if name == "intelligence-engine" else "worker.workbench" if name == "workbench" else "worker.processor_service" if name == "processor" else "ml_time_forecasting.service" if name == "forecast" else "worker.main"
        return module in process.cmdline() and Path(process.cwd()).resolve() == ROOT
    except (OSError, psutil.Error):
        return False


for name in ["api-gateway", "api-intelligence", "api-platform", "api-integrations", "api-documents", "api-recruitment", "api-talent", "api-identity", "api", "worker", "processor", "forecast", "intelligence-engine", "workbench", "ollama", "ollama-review"]:
    pidfile = ROOT / "runtime" / f"{name}.pid"
    if not pidfile.exists():
        continue
    try:
        process = psutil.Process(int(pidfile.read_text(encoding="ascii")))
        if not owns(name, process):
            raise RuntimeError(f"{name}: PID no longer belongs to this project")
        children = process.children(recursive=True)
        for child in children:
            child.terminate()
        process.terminate()
        _, remaining = psutil.wait_procs([process, *children], timeout=10)
        for item in remaining:
            item.kill()
        psutil.wait_procs(remaining, timeout=5)
        print(name, "stopped")
    except psutil.NoSuchProcess:
        pass
    pidfile.unlink(missing_ok=True)

cluster = (ROOT / "runtime" / "postgres").resolve()
assert cluster.is_relative_to(ROOT / "runtime")
if (cluster / "postmaster.pid").exists():
    subprocess.run([str(ROOT / ".tools" / "postgres17" / "pgsql" / "bin" / "pg_ctl.exe"), "-D", str(cluster), "stop", "-m", "fast"], check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
