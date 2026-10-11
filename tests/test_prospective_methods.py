"""Controlled algorithm/security checks; no real-user pilot, no LLM."""
import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
import httpx
import numpy as np
import pytest
from intelligence import prospective as pv, economic_sources as es, experiments as ex

def protocol(kind='parallel_forms'):
 return pv.protocol({'kind':kind,'role':'backend_python','grade':'middle',
  'model_version':'role-parameter-forms-v1' if kind=='parallel_forms' else 'bilateral-market-1.0.0',
  'start_at':'2030-01-01T00:00:00Z','end_at':'2030-12-31T00:00:00Z'},_created_at='2026-10-10T00:00:00Z')

def forecast_row(**changes):
 row={'vacancy_id':'v1','candidate_id':'c1','stage':'vacancy','model_version':'bilateral-market-1.0.0',
  'created_at':'2026-02-01T00:00:00Z','synthetic':False,
  'candidate_accepts':True,'employer_accepts':False,
  'candidate_decided_at':'2026-02-02T00:00:00Z','employer_decided_at':'2026-02-03T00:00:00Z',
  'prediction':{'candidate_acceptance':{'mean':.8},'employer_acceptance':{'mean':.3},'joint_point_estimate':None}}
 row.update(changes);return row

def paired_rows(count=200):
 rows=[]
 for i in range(count):
  identity='controlled-'+str(i);assigned=ex.assign({'identity':identity,'scope':'backend_python:middle','version':'role-parameter-forms-v1'})
  rows.append({'participant_id':identity,'role':'backend_python','grade':'middle','model_version':'role-parameter-forms-v1',
   'synthetic':False,'complete':True,'review_required':False,
   'assigned_at':'2030-02-01T00:00:00Z','first_at':'2030-02-02T00:00:00Z','second_at':'2030-02-05T00:00:00Z',
   'order':'AB' if assigned['variant']=='A' else 'BA','theta_a':i%3/2,'theta_b':i%3/2+.01,
   'anchor_a':.2,'anchor_b':.2,'form_a_sha256':'a'*64,'form_b_sha256':'b'*64,'source_sha256':'c'*64})
 return rows

def test_empty_real_cohort_has_no_manufactured_metrics():
 r=pv.forecast_report({'records':[]});assert r['status']=='awaiting_real_observations'
 assert r['complete_pairs']==0 and r['stages']['offer']['candidate'] is None
 assert not r['production_calibration_authorized'] and not r['real_employment_validated']

def test_protocol_creation_cannot_backdate_enrollment_or_trust_caller_clock():
 p=protocol();p['created_at']='1900-01-01T00:00:00Z';p['start_at']='2000-01-01T00:00:00Z'
 with pytest.raises(ValueError):pv.protocol(p)

def test_calibration_roles_are_stratified_not_relabelled():
 rows=[forecast_row(candidate_id='c1'),forecast_row(candidate_id='c2')]
 rows[0]['prediction']['context']={'role':'backend_python','grade':'middle'}
 rows[1]['prediction']['context']={'role':'data_science','grade':'senior'}
 r=pv.forecast_report({'records':rows})
 assert set(r['role_blocks']['vacancy'])=={'backend_python:middle','data_science:senior'}
 assert all(x['candidate']['n']==1 for x in r['role_blocks']['vacancy'].values())

def test_proper_scoring_and_stage_scope():
 r=pv.forecast_report({'records':[forecast_row()]})
 assert r['stages']['vacancy']['candidate']['brier']==pytest.approx(.04)
 assert r['stages']['vacancy']['employer']['brier']==pytest.approx(.09)
 assert r['stages']['vacancy']['candidate']['log_loss']==pytest.approx(-np.log(.8))
 assert r['stages']['vacancy']['candidate']['auc'] is None
 assert r['stages']['vacancy']['joint'] is None and r['stages']['offer']['candidate'] is None

@pytest.mark.parametrize('key,value',[('candidate_decided_at','2026-01-31T00:00:00Z'),
 ('employer_decided_at','2026-02-01T00:00:00Z'),('candidate_accepts',1),('stage','hire'),('model_version','unknown')])
def test_invalid_outcomes_rejected(key,value):
 with pytest.raises(ValueError):pv.forecast_report({'records':[forecast_row(**{key:value})]})

@pytest.mark.parametrize('probability',[-.1,1.1,float('inf'),float('nan'),True,'0.5'])
def test_invalid_probability_rejected(probability):
 row=forecast_row();row['prediction']['candidate_acceptance']['mean']=probability
 with pytest.raises(ValueError):pv.forecast_report({'records':[row]})

def test_synthetic_censoring_duplicates():
 r=pv.forecast_report({'records':[forecast_row(synthetic=True),forecast_row(candidate_id='c2',candidate_accepts=None)]})
 assert r['excluded']=={'synthetic':1,'censored':1}and r['complete_pairs']==0
 with pytest.raises(ValueError):pv.forecast_report({'records':[forecast_row(),forecast_row()]})

@pytest.mark.parametrize('key,value',[('margin',.8),('planned_looks',10),('minimum_complete_pairs',2),('ece_bins',2)])
def test_preregistered_protocol_cannot_be_loosened(key,value):
 p=protocol();p[key]=value
 with pytest.raises(ValueError):pv.check_protocol(p,'parallel_forms')
 p['protocol_sha256']=pv.digest({k:v for k,v in p.items()if k!='protocol_sha256'})
 with pytest.raises(ValueError):pv.check_protocol(p,'parallel_forms')

def test_controlled_paired_tost_pass_is_not_certificate_permission():
 r=pv.parallel_report({'protocol':protocol(),'records':paired_rows()})
 assert r['statistical_gate_passed'] and r['theta']['mean_difference']==pytest.approx(-.01)
 assert not r['production_activation_allowed'] and not r['generalizes_to_other_roles']

@pytest.mark.parametrize('key,value',[('role','data_science'),('grade','senior'),('model_version','different'),
 ('order','wrong'),('second_at','2030-02-02T10:00:00Z'),('source_sha256','x'*64),('theta_a',float('nan')),
 ('form_b_sha256','a'*64),('assigned_at','2030-03-01T00:00:00Z')])
def test_invalid_parallel_cohort_rejected(key,value):
 rows=paired_rows(2);rows[0][key]=value
 with pytest.raises(ValueError):pv.parallel_report({'protocol':protocol(),'records':rows})

def test_shifted_form_fails_equivalence():
 rows=paired_rows()
 for r in rows:r['theta_b']=r['theta_a']+.5
 r=pv.parallel_report({'protocol':protocol(),'records':rows})
 assert not r['theta']['equivalent']and not r['statistical_gate_passed']

def test_parallel_exclusions_and_duplicates():
 rows=paired_rows(3);rows[0]['synthetic']=True;rows[1]['complete']=False;rows[2]['review_required']=True
 r=pv.parallel_report({'protocol':protocol(),'records':rows})
 assert r['n']==0 and r['excluded']=={'synthetic':1,'incomplete':1,'flagged_for_review':1}
 with pytest.raises(ValueError):pv.parallel_report({'protocol':protocol(),'records':paired_rows(2)*2})

@pytest.mark.parametrize('role',['backend_python','frontend_development','data_science','data_engineering','ml_engineering'])
def test_actual_parallel_task_parameters_and_identical_anchors(role):
 p=protocol();p['role']=role;p=pv.protocol(p,_created_at=p['created_at'])
 banks=ex.study_banks({'protocol':p});a,b=(banks['contracts'][v]for v in ('A','B'))
 assert banks['contract_sha256']['A']!=banks['contract_sha256']['B']
 anchors=set(a['parallel_form']['anchor_families']);different=0
 for x,y in zip(a['bank'],b['bank']):
  assert x['id']==y['id']and x['options'][x['correct']]==str(x['answer_value'])and y['options'][y['correct']]==str(y['answer_value'])
  if x['family']in anchors:assert x==y
  else:different+=x['prompt']!=y['prompt']
 assert different>0 and not banks['production_activation_allowed']

def macro_rows():
 return [{'id':str(i),'role':'backend_python','grade':'middle','model_version':'bilateral-market-1.0.0',
  'synthetic':False,'stage':'offer','trained_until':'2029-12-01T00:00:00Z',
  'prediction_at':(datetime(2030,2,1,tzinfo=timezone.utc)+timedelta(days=i%40)).isoformat(),
  'outcome_at':'2030-05-01T00:00:00Z','macro_published_at':'2030-01-01T00:00:00Z',
  'outcome':i%2==0,'baseline':.5,'with_macro':.7 if i%2==0 else .3}for i in range(160)]

def test_paired_macro_ablation_control_and_no_automatic_activation():
 r=pv.macro_ablation({'protocol':protocol('forecast'),'records':macro_rows()})
 assert r['mean_delta']==pytest.approx(-.16)and r['date_clusters']==40
 assert r['incremental_accuracy_gate_passed']and not r['forecast_activation_allowed']
 assert r['ranking_effect']==0

@pytest.mark.parametrize('key,value',[('macro_published_at','2030-06-01T00:00:00Z'),('trained_until','2030-02-01T00:00:00Z'),
 ('synthetic',True),('grade','senior'),('outcome',1),('with_macro',1.5)])
def test_macro_temporal_leakage_and_scope_rejected(key,value):
 rows=macro_rows();rows[0][key]=value
 with pytest.raises(ValueError):pv.macro_ablation({'protocol':protocol('forecast'),'records':rows})

def test_unlicensed_adapter_makes_no_network_request(monkeypatch):
 monkeypatch.delenv('MOEX_RIGHTS_MANIFEST_FILE',raising=False)
 monkeypatch.setattr(es.httpx,'AsyncClient',lambda *a,**k:pytest.fail('Network must not be opened'))
 r=asyncio.run(es.fetch({'index':'IMOEX','from':'2026-01-01','till':'2026-01-02'}))
 assert r['status']=='licensing_required'and r['forecast_effect']==r['ranking_effect']==0

def test_rights_manifest_fail_closed(monkeypatch,tmp_path):
 path=tmp_path/'rights.json';monkeypatch.setenv('MOEX_RIGHTS_MANIFEST_FILE',str(path))
 for invalid in ({},[],{'provider':'MOEX ISS','approved_by_operator':False},'bad'):
  path.write_text(json.dumps(invalid),encoding='utf-8');assert es.authorization()is None

def history(close=3400.,secid='IMOEX',day='2026-10-01'):
 return {'history':{'columns':['SECID','TRADEDATE','CLOSE'],'data':[[secid,day,close]]}}

def test_iss_schema_missing_is_not_zero():
 assert es.parse_history(history(None),'IMOEX','2026-10-10T00:00:00Z')==[]
 assert es.parse_history(history(),'IMOEX','2026-10-10T00:00:00Z')[0]['close']==3400

@pytest.mark.parametrize('close,secid,day',[(True,'IMOEX','2026-10-01'),(-1,'IMOEX','2026-10-01'),
 (float('inf'),'IMOEX','2026-10-01'),(100,'EVIL','2026-10-01'),(100,'IMOEX','2027-10-01')])
def test_iss_invalid_rows_rejected(close,secid,day):
 with pytest.raises(ValueError):es.parse_history(history(close,secid,day),'IMOEX','2026-10-10T00:00:00Z')

def test_authorized_adapter_is_bounded_and_still_not_predictive(monkeypatch,tmp_path):
 class ControlledClock(datetime):
  @classmethod
  def now(cls,tz=None):return datetime(2026,10,10,12,tzinfo=timezone.utc)
 monkeypatch.setattr(es,'datetime',ControlledClock)
 path=tmp_path/'rights.json';path.write_text(json.dumps({'provider':'MOEX ISS','approved_by_operator':True,
  'third_party_product_use':True,'contract_reference':'controlled-not-real-license','valid_from':'2020-01-01',
  'valid_until':'2099-01-01','permitted_indexes':['IMOEX']}),encoding='utf-8')
 monkeypatch.setenv('MOEX_RIGHTS_MANIFEST_FILE',str(path));calls=[];real_client=httpx.AsyncClient
 def respond(request):
  calls.append(request);assert request.url.host=='iss.moex.com'
  return httpx.Response(200,json=history(day='2026-10-09'))
 def client(**kwargs):
  assert kwargs['trust_env']is False and kwargs['follow_redirects']is False
  return real_client(**kwargs,transport=httpx.MockTransport(respond))
 monkeypatch.setattr(es.httpx,'AsyncClient',client)
 r=asyncio.run(es.fetch({'index':'IMOEX','from':'2026-10-01','till':'2026-10-10'}))
 assert len(calls)==1 and r['status']=='source_snapshot'and r['limited_to_one_page']
 assert r['ranking_effect']==r['forecast_effect']==0 and len(r['body_sha256'])==64
 with pytest.raises(ValueError):asyncio.run(es.fetch({'index':'MOEXFN','from':'2026-10-01','till':'2026-10-10'}))
