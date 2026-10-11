"""Fresh untuned generator holdout and honest counterfactual effect measurements."""
import json,random,statistics
from pathlib import Path
from catboost import CatBoostRegressor
from ml_time_forecasting.train import vacancy_rows,candidate_rows,VACANCY_FEATURES,CANDIDATE_FEATURES,r2_score,rmse
from ml_time_forecasting.service import load_models,vacancy_response,candidate_response

ROOT=Path(__file__).resolve().parents[1]
def main():
    load_models(); report={'seed':20261009,'rows_per_task':3000,'method':'Independent generator holdout; frozen model, no retuning on this holdout','tasks':{}}
    for task,generator,features,response in [('vacancy_fill',vacancy_rows,VACANCY_FEATURES,vacancy_response),('candidate_job_search',candidate_rows,CANDIDATE_FEATURES,candidate_response)]:
        rows=generator(random.Random(20261009),3000);m=CatBoostRegressor();m.load_model(str(ROOT/'ml_time_forecasting/artifacts'/f'{task}.cbm'))
        target=[r['target_days'] for r in rows];pred=list(m.predict([[r[f] for f in features] for r in rows]))
        effects=[response(r) for r in rows[:100]]
        report['tasks'][task]={'r2':round(r2_score(target,pred),6),'rmse_days':round(rmse(target,pred),4),'mae_days':round(statistics.mean(abs(a-b)for a,b in zip(target,pred)),4),'counterfactual_cases':100,'mean_reduction_days':round(statistics.mean(e['forecast_days']-e['recommended_days'] for e in effects),2),'target_achieved_cases':sum(e['recommended_days']<=e['target_days'] for e in effects),'worsening_cases':sum(e['recommended_days']>e['forecast_days']for e in effects)}
    report['passed']=all(t['r2']>.92 and t['worsening_cases']==0 for t in report['tasks'].values())
    out=ROOT/'validation/reports/current';out.mkdir(parents=True,exist_ok=True);(out/'forecast-holdout.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
    assert report['passed'], 'Holdout quality or nonworsening recommendation requirement failed'
if __name__=='__main__':main()
