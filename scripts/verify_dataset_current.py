"""Read-only audit of repository dataset, compressed gold and privacy markers."""
import collections
import csv
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def rows(name):
    path = ROOT / "data" / name
    with (path.open(encoding="utf-8-sig", newline="") if path.exists() else gzip.open(str(path)+".gz", "rt", encoding="utf-8-sig", newline="")) as file:
        yield from csv.DictReader(file)

def main():
    candidates = list(rows("candidates.csv")); vacancies = list(rows("vacancies.csv"))
    cids = {r["candidate_id"] for r in candidates}; vids = {r["vacancy_id"] for r in vacancies}
    assert len(cids) == len(candidates) == 4040
    assert len(vids) == len(vacancies) == 494
    assert all(not r["email"] and not r["phone"] for r in candidates)
    assert all(r["identity_kind"].startswith("synthetic") for r in candidates)
    assert all(0 < int(r["salary_from_rub"]) <= int(r["salary_to_rub"]) for r in vacancies)
    counts = collections.Counter(); total = 0
    for row in rows("relevance_labels.csv"):
        assert row["candidate_id"] in cids and row["vacancy_id"] in vids
        assert int(row["expected_relevance"]) in range(4)
        counts[row["expected_relevance"]] += 1; total += 1
    assert total == len(candidates)*len(vacancies)
    top = list(rows("expected_top5.csv"))
    assert len(top) == len(vacancies)*5
    assert all(r["candidate_id"] in cids and r["vacancy_id"] in vids for r in top)
    report = {"passed":True,"candidates":len(candidates),"vacancies":len(vacancies),"specializations":len({r["specialization"]for r in candidates}),"private_candidates":sum(r["profile_visibility"]=="private"for r in candidates),"gold_pairs":total,"label_distribution":dict(counts),"top5_rows":len(top),"method":"Read-only source audit: unique source IDs, empty contact fields, synthetic markers, salary bounds, all gold pair foreign keys and gains, top-5 references. Gold is not supplied to runtime APIs.","sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in(ROOT/"data").glob("*")if p.is_file()}}
    (ROOT/"validation/reports/current/data-audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items()if k!='sha256'}))

if __name__ == "__main__": main()
