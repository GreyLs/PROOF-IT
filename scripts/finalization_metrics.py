"""Numerical oracle/latency evidence, not empirical hiring effectiveness."""
import json,time,math,hashlib
import numpy as np
from pathlib import Path
from intelligence import prospective as pv
from tests.test_prospective_methods import protocol,paired_rows,macro_rows,forecast_row
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current'
def main():
 rng=np.random.default_rng(3917);probabilities=rng.uniform(.001,.999,2000);labels=rng.integers(0,2,2000)
 scored=pv._scores(probabilities,labels)
 oracle_brier=math.fsum((float(p)-int(y))**2 for p,y in zip(probabilities,labels))/len(labels)
 oracle_logloss=-math.fsum(math.log(float(p))if y else math.log1p(-float(p))for p,y in zip(probabilities,labels))/len(labels)
 small_p=np.round(probabilities[:200],1);small_y=labels[:200];small=pv._scores(small_p,small_y)
 comparisons=[(float(a)>float(b))+.5*(float(a)==float(b))for a in small_p[small_y==1]for b in small_p[small_y==0]]
 auc_error=abs(small['auc']-math.fsum(comparisons)/len(comparisons))
 errors=[];rows=[forecast_row(candidate_id='control-'+str(i),candidate_accepts=bool(i%2),employer_accepts=bool(i%3))for i in range(120)]
 for _ in range(5):pv.forecast_report({'records':rows})
 durations=[]
 for _ in range(40):
  start=time.perf_counter();pv.forecast_report({'records':rows});durations.append((time.perf_counter()-start)*1000)
 for i in range(120):
  row=forecast_row(candidate_id=str(i),candidate_decided_at='2025-01-01T00:00:00Z')
  try:pv.forecast_report({'records':[row]});errors.append(i)
  except ValueError:pass
 paired=pv.parallel_report({'protocol':protocol(),'records':paired_rows()})
 shifted=paired_rows()
 for row in shifted:row['theta_b']=row['theta_a']+.5
 negative=pv.parallel_report({'protocol':protocol(),'records':shifted})
 ablation=pv.macro_ablation({'protocol':protocol('forecast'),'records':macro_rows()})
 qa=json.loads((ROOT/'web/src/locales/qa-status.json').read_text(encoding='utf-8'))
 report={'passed':not errors and abs(scored['brier']-oracle_brier)<1e-12 and abs(scored['log_loss']-oracle_logloss)<1e-12 and auc_error<1e-12,
  'generated_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'seed':3917,'llm_calls':0,'real_human_pilot':False,
  'proper_score_oracle_cases':2000,'brier_oracle_absolute_error':abs(scored['brier']-oracle_brier),
  'log_loss_oracle_absolute_error':abs(scored['log_loss']-oracle_logloss),
  'auc_ties_pairwise_oracle_cases':len(comparisons),'auc_ties_oracle_absolute_error':auc_error,
  'future_label_leakage_controls':120,'future_label_leakage_rejections':120-len(errors),
  'cohort_report_cpu':{'records':120,'measured_runs':40,'warmup_runs':5,'p50_ms':float(np.median(durations)),
                     'p95_ms':float(np.quantile(durations,.95)),'max_ms':max(durations)},
  'paired_equivalence_positive_control':paired['statistical_gate_passed'],
  'shifted_form_negative_control_rejected':not negative['statistical_gate_passed'],
  'macro_paired_loss_oracle_absolute_error':abs(ablation['mean_delta']+.16),
  'static_catalogs':{lang:{'keys':row['catalog_key_count'],'source':row['source_key_count'],'structural_errors':len(row['structural_invalid_keys']),'critical_ready':row['critical_ready']}for lang,row in qa['languages'].items()},
  'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()for name in ('intelligence/prospective.py','intelligence/economic_sources.py','intelligence/professional.py','intelligence/experiments.py')},
  'scope':'controlled independent scalar/pairwise numeric oracles and warm local CPU timing; no network, no load extrapolation, no hiring accuracy claim'}
 assert report['passed'];(OUT/'finalization-metrics.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
