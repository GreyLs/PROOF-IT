"""Static Helm/YAML validation only. Never contacts a Kubernetes cluster."""
import json
import subprocess
from pathlib import Path

import yaml

ROOT=Path(__file__).resolve().parents[1]


def main():
    helm=ROOT/".tools/helm-v3.19.0/windows-amd64/helm.exe"
    lint=subprocess.run([str(helm),"lint","deploy/horizon"],cwd=ROOT,text=True,encoding="utf-8",capture_output=True,check=True)
    rendered=subprocess.run([str(helm),"template","proofit","deploy/horizon"],cwd=ROOT,text=True,encoding="utf-8",capture_output=True,check=True)
    objects=[o for o in yaml.safe_load_all(rendered.stdout) if o]
    values=yaml.safe_load((ROOT/"deploy/horizon/values.yaml").read_text(encoding="utf-8"))
    assert values["api"]["replicas"]>=2
    assert values["pgbouncer"]["mode"]=="session"
    assert "pool_mode = session" in (ROOT/"deploy/horizon/pgbouncer.ini").read_text(encoding="utf-8")
    deployments={o["metadata"]["name"]:o for o in objects if o["kind"]=="Deployment"}
    autoscalers={o["metadata"]["name"]:o for o in objects if o["kind"]=="HorizontalPodAutoscaler"}
    for name in values["domains"]:
        assert "proofit-"+name in deployments and "proofit-"+name in autoscalers
    assert "proofit-intelligence-engine" in deployments
    engine=deployments["proofit-intelligence-engine"]["spec"]["template"]["spec"]["containers"][0]
    assert not any(e["name"]=="DATABASE_URL" for e in engine["env"])
    for o in autoscalers.values():
        assert o["spec"]["maxReplicas"]>=o["spec"]["minReplicas"]>=2
    report={"passed":True,"lint_exit_code":lint.returncode,"render_exit_code":rendered.returncode,"resources":len(objects),"deployments":len(deployments),"autoscalers":len(autoscalers),"capacity_test_run":False,"cluster_deployment_run":False,"schema_validation":"Helm lint + YAML + configuration invariants; no API-server admission"}
    (ROOT/"validation/reports/current/deployment.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    (ROOT/"validation/reports/current/chart-rendered.yaml").write_text(rendered.stdout,encoding="utf-8")
    print(json.dumps(report))


if __name__=="__main__":main()
