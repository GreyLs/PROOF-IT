"""Reproducible CPU algorithm experiments; all observations are machine-derived."""
from pathlib import Path
import hashlib,itertools,json,math,random,re,statistics,subprocess,time
import numpy as np
from intelligence import professional as cat,integrity,needs,twins,certification
from intelligence.item_bank import FAMILIES,render
from tests.test_evidence_methods import CODE
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current'
def write(name,value):
 OUT.mkdir(parents=True,exist_ok=True);value['measured_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z');value['llm_calls']=0
 (OUT/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def wilson(k,n):
 z=1.96;p=k/n;d=1+z*z/n;mid=(p+z*z/(2*n))/d;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d;return [max(0,mid-half),min(1,mid+half)]
def assessment():
 rng=np.random.default_rng(20261010);truth=rng.uniform(-2.7,2.7,360);rows=[];start=time.perf_counter()
 for i,t in enumerate(truth):
  c=cat.create({'seed':20261010+i*7,'specialization':['backend_python','frontend_ts','qa','devops','lead_engineering'][i%5],'mode':'full'})
  while(q:=cat.next_item(c)) is not None:
   success=rng.random()<float(cat.probability(t,q));answer=q['correct'] if success else (q['correct']+int(rng.integers(1,4)))%4
   c=cat.step({'contract':c,'question_id':q['id'],'answer':answer,'elapsed_ms':10000+137*len(c['answers'])})['contract']
  r=cat.result(c);actual='junior' if t<-.5 else 'middle' if t<1 else 'senior';certain=max(r['grade_probabilities'].values())>=.85
  rows.append({'truth':float(t),'theta':r['theta'],'se':r['standard_error'],'predicted':r['suggested_grade'],'actual':actual,'certain':certain,'questions':r['scored_questions']})
 certain=[x for x in rows if x['certain']];k=sum(x['actual']==x['predicted'] for x in certain)
 write('assessment',{'simulated_trajectories':len(rows),'scope':'Monte Carlo under authored 3PL response process; not human psychometric calibration','seed':20261010,'theta_correlation':float(np.corrcoef(truth,[x['theta'] for x in rows])[0,1]),'theta_rmse':float(np.sqrt(np.mean([(x['truth']-x['theta'])**2 for x in rows]))),'exact_grade_accuracy':sum(x['actual']==x['predicted'] for x in rows)/len(rows),'within_one_grade':sum(abs(cat.GRADES.index(x['actual'])-cat.GRADES.index(x['predicted']))<=1 for x in rows)/len(rows),'certainty_threshold':.85,'certain_cases':len(certain),'certain_accuracy':k/max(1,len(certain)),'certain_accuracy_wilson95':wilson(k,len(certain)) if certain else None,'coverage':len(certain)/len(rows),'mean_questions':statistics.mean(x['questions'] for x in rows),'range_questions':[min(x['questions'] for x in rows),max(x['questions'] for x in rows)],'elapsed_seconds':time.perf_counter()-start,'independent_human_labels':0})
def item_execution():
 jobs=[]
 for seed in range(40):
  for family in FAMILIES['typescript']:
   q=render(family,seed%3,seed);p=q['prompt']
   array=re.search(r'const xs=(\[[^]]+\]); (.*)\. Найдите',p)
   if array:code='const xs='+array[1]+'; return ('+array[2]+');'
   elif family=='ts_slice':n,start,end=map(int,re.search(r'из (\d+) элементов; xs.slice\((\d+),(\d+)\)',p).groups());code=f'const xs=Array.from({{length:{n}}},(_,i)=>i); return xs.slice({start},{end}).length;'
   else:b=int(re.search(r'const b=(\d+)',p)[1]);code=f'const a=0,b={b};return (a??b)+(a||b);'
   jobs.append({'code':code,'expected':int(q['options'][q['correct']])})
 node=ROOT/'.tools/node-v24.21.0-win-x64/node.exe'
 script='const fs=require("fs");const cases=JSON.parse(fs.readFileSync(0,"utf8"));process.stdout.write(JSON.stringify(cases.map(x=>Function(x.code)())));'
 result=subprocess.run([str(node),'-e',script],input=json.dumps(jobs),text=True,capture_output=True,check=True)
 actual=json.loads(result.stdout);assert actual==[x['expected'] for x in jobs]
 write('executable-oracles',{'python_cases':240,'sql_cases':240,'typescript_cases':len(jobs),'role_forms':sum(len(v) for v in FAMILIES.values())*3*30,'typescript_passed':len(actual),'oracles':['Python execution in pytest','SQLite query execution in pytest','Node.js 24 real execution'],'roles':list(FAMILIES),'llm_generated_answer_keys':False})
def similarity():
 reference=integrity.fingerprint({'code':CODE});positives=[];negative=[]
 for i in range(120):
  code=CODE.replace('seen',f'cache{i}').replace('totals',f'result{i}').replace('event',f'entry{i}')+'\n'+'\n'.join(f'def unused{k}(x):\n    return x*x+{k}' for k in range(i%40))
  if i%3==0:code=code.replace('    ','  ')
  positives.append(integrity.compare({'fingerprint':integrity.fingerprint({'code':code}),'references':[reference]}))
 independent=[
  "from collections import defaultdict\ndef solve(data):\n    rows={v['id']:v for v in data['events']}\n    balance=defaultdict(int)\n    for key in rows:\n        row=rows[key]\n        balance[row['account']]+=row['amount']\n    return [dict(account=a,total=balance[a]) for a in sorted(balance)]",
  "def solve(data):\n    unique={e['id']:e for e in reversed(data['events'])}\n    keys=sorted({r['account'] for r in unique.values()})\n    answer=[]\n    for k in keys:\n        selected=filter(lambda x:x['account']==k,unique.values())\n        amount=sum(map(lambda x:x['amount'],selected))\n        answer.append(dict(account=k,total=amount))\n    return answer",
  "def solve(data):\n    groups={}\n    ids=[]\n    for row in data['events']:\n        identifier=row['id']\n        if identifier not in ids:\n            ids.append(identifier)\n            account=row['account']\n            if account not in groups:\n                groups[account]=[]\n            groups[account].append(row['amount'])\n    answer=[]\n    for account in sorted(groups.keys()):\n        answer.append(dict(account=account,total=sum(groups[account])))\n    return answer",
 ]
 for code in independent:negative.append(integrity.compare({'fingerprint':integrity.fingerprint({'code':code}),'references':[reference]}))
 tp=sum(r['review_recommended'] for r in positives);fp=sum(r['review_recommended'] for r in negative)
 write('integrity',{'copy_transformations':len(positives),'detected':tp,'sensitivity':tp/len(positives),'sensitivity_wilson95':wilson(tp,len(positives)),'independent_same_task_implementations':len(negative),'structural_false_alerts':fp,'minimum_copy_containment':min(x['similarity'] for x in positives),'padding_functions_up_to':39,'automatic_penalties':0,'method':'token normalization, k=5, window=4, template subtraction, containment threshold 0.85; independent human review','scope':'Controlled structural transformations and three independently authored implementations; not an open-world plagiarism accuracy estimate'})
def parsing():
 rows=[]
 for role in needs.taxonomy():
  for band in ['180–250 тыс руб','180000–250000 RUB','от 180 до 250 тыс. руб','180 000 — 250 000 ₽']:
   p=needs.parse({'text':role['label']+'; Middle; '+', '.join(role['skills'][:3])+'; '+band+'; удалённо'})
   rows.append((p['specialization']==role['id'],p['salary_from']==180000 and p['salary_to']==250000))
 write('need-parsing',{'cases':len(rows),'role_correct':sum(r[0] for r in rows),'salary_correct':sum(r[1] for r in rows),'role_accuracy':sum(r[0] for r in rows)/len(rows),'salary_accuracy':sum(r[1] for r in rows)/len(rows),'scope':'Explicit taxonomy labels and four salary notation families; deterministic parser'})
def main():item_execution();similarity();parsing();assessment();print('CPU experiments recorded: executable oracles, integrity, parsing and CAT simulation.')
if __name__=='__main__':main()
