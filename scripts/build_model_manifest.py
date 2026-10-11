"""Runtime model contract without historical experimental metrics."""
from pathlib import Path
import hashlib,json
from ml_time_forecasting.train import VACANCY_FEATURES,CANDIDATE_FEATURES
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'ml_time_forecasting/artifacts'
def main():
 tasks={}
 for task,features in [('vacancy_fill',VACANCY_FEATURES),('candidate_job_search',CANDIDATE_FEATURES)]:
  path=OUT/(task+'.cbm');tasks[task]={'model':path.name,'features':list(features),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'training_scope':'synthetic-scenario-simulator','model_policy':'frozen; outcomes do not automatically retrain'}
 (OUT/'model_manifest.json').write_text(json.dumps({'schema':'forecast-model-contract-1','tasks':tasks},indent=2),encoding='utf-8')
 print('Frozen model manifests regenerated; current quality is recorded separately.')
if __name__=='__main__':main()
