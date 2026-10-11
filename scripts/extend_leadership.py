"""Idempotent authored leadership scenarios. Never label designed salaries as market observations."""
from pathlib import Path
import csv, json, hashlib, shutil, gzip, heapq
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path.home()/'Desktop/ФСП 2026/Тестовые данные ФСП/production_dataset'
ROLES=[
 ('lead_engineering','Тимлид / руководитель группы разработки','team_lead',6,10,5,9,260000,420000,['Python','PostgreSQL','Architecture','Code review','Delivery','Mentoring'], 'платёжного API', 'идемпотентность, транзакционные границы и контролируемый релиз'),
 ('lead_data','Тимлид / руководитель группы данных','team_lead',5,9,5,9,280000,450000,['SQL','Python','Airflow','Data quality','Delivery','Mentoring'], 'платформы данных', 'контракты данных, lineage и качество пайплайнов'),
 ('head_platform','Руководитель направления платформы','direction_head',15,28,8,13,350000,550000,['Platform engineering','SLO','Kubernetes','FinOps','Roadmap','People management'], 'облачной платформы', 'SLO, стоимость сервиса и приоритеты внутренних команд'),
 ('head_data','Руководитель направления Data / AI','direction_head',14,26,8,13,370000,580000,['Data strategy','ML lifecycle','Data governance','Experiment design','Roadmap','People management'], 'Data / AI продукта', 'качество данных, вывод моделей и окупаемость внедрения'),
 ('director_engineering','Руководитель отдела разработки','department_head',30,60,10,16,400000,650000,['Engineering management','Architecture','Hiring','Budgeting','Delivery','Risk management'], 'B2B SaaS продукта', 'портфель релизов, найм руководителей групп и технологический долг'),
 ('director_security','Руководитель отдела ИБ','department_head',15,35,9,15,400000,650000,['AppSec','Threat modeling','Incident response','Security governance','Budgeting','People management'], 'безопасности ИТ-продукта', 'модель угроз, процесс реагирования и приоритизация рисков'),
 ('executive_cto','CTO / технический директор ИТ-компании','c_level',65,140,12,20,550000,950000,['Technology strategy','Architecture','P&L','Portfolio management','Org design','Risk management'], 'технологической стратегии SaaS-компании', 'build-versus-buy, инвестиционный портфель и организационная модель'),
 ('executive_ciso','CISO / директор по информационной безопасности','c_level',30,70,12,20,500000,850000,['Security strategy','Enterprise risk','Business continuity','Board reporting','Budgeting','Org design'], 'стратегии ИБ облачной ИТ-компании', 'риск-аппетит, непрерывность бизнеса и защита продуктовой разработки'),
]

def read(name):
 with (SOURCE/'data'/f'{name}.csv').open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
def write(name,rows):
 fields=list(dict.fromkeys(k for r in rows for k in r))
 with (SOURCE/'data'/f'{name}.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def main():
 backup=ROOT/'runtime/backups/stage-2026-10-06'
 backup.mkdir(parents=True,exist_ok=True)
 if not (backup/'dataset').exists():shutil.copytree(SOURCE,backup/'dataset')
 taxonomy=json.loads((ROOT/'data/taxonomy.json').read_text(encoding='utf-8'))
 taxonomy=[x for x in taxonomy if x['id'] not in {r[0] for r in ROLES}]
 candidates=[r for r in read('candidates') if not r['candidate_id'].startswith('LC')]
 vacancies=[r for r in read('vacancies') if not r['vacancy_id'].startswith('LV')]
 employers=[r for r in read('employers') if not r['company_id'].startswith('LE')]
 attempts=[r for r in read('assessment_attempts') if not r['candidate_id'].startswith('LC')]
 blueprints=[r for r in read('assessment_blueprints') if r['specialization'] not in {x[0] for x in ROLES}]
 cases=[]
 for n,(spec,label,level,tmin,tmax,ymin,ymax,low,high,skills,project,depth) in enumerate(ROLES,1):
  taxonomy.append({'id':spec,'label':label,'family':spec,'skills':skills,'leadership_level':level,'allowed_grades':['middle','senior']})
  for j in range(80):
   cid=f'LC{n:02}{j+1:03}'; team=tmin+j%(tmax-tmin+1);years=round(ymin+(j%11)/10*(ymax-ymin),1)
   score=64+j%36;grade='middle' if j%4==0 else 'senior'; salary=low+(j%9)*((high-low)//10//10000)*10000
   management=round(min(years-3,2+j%7 if level=='team_lead' else 4+j%8),1)
   case=['strong','partial','missing','contradiction'][j%4]
   about=f'Синтетическое резюме {cid}. {label}. Общий опыт {years} лет, управление {management} лет. ИТ-компания «Контур продукта {n}» (вымышленная).'
   if case=='strong':about+=f' Руководил командой из {team} человек в разработке {project}. Лично отвечал за {depth}. За 12 месяцев сократил цикл поставки с {24+j%5} до {12+j%3} дней: ввёл лимиты незавершённой работы, разделил релизы и согласовал критерии отката. Сравнивал месячные медианы до и после; отслеживал долю неуспешных изменений, чтобы ускорение не ухудшало надёжность.'
   elif case=='partial':about+=f' В команде было {team} человек. Участвовал в планировании и развитии {project}; командный результат положительный, личная зона ответственности и способ измерения не описаны.'
   elif case=='missing':about+=f' Работал над {project}. Обязанности, размер команды и метрики в резюме не указаны; требуется уточнение без автоматического отрицательного вывода.'
   else:about+=' В последние три года работал индивидуальным специалистом. Прямых подчинённых не было; решения по бюджету, найму и приоритетам принимал мой руководитель. Хочу перейти на управленческую роль.'
   candidates.append({'candidate_id':cid,'display_name':f'Кандидат {cid}','identity_kind':'synthetic pseudonym; no real person','email':'','phone':'','specialization':spec,'current_grade':grade,'experience_years':str(years),'skills':'; '.join(skills[:4+j%3]),'expected_salary_from_rub':str(salary),'work_format':['удалённо','гибрид','офис'][j%3],'profile_visibility':'private' if j%13==0 else 'employer_searchable','contacts_visible_to_employer':'false','test_score_pct':str(score),'profile_freshness_days':str(j%70),'has_fsp_history':'false','fsp_evidence_score':'0','profile_data_origin':'synthetic authored leadership scenario; not validated real experience','leadership_level':level,'management_years':str(management),'team_size':str(team if case in ('strong','partial') else 0),'resume_text':about,'dialogue_case':case})
   attempts.append({'attempt_id':f'PA-{cid}','candidate_id':cid,'variant_id':f'DIA-{cid}','blueprint_id':f'BP-{spec.upper()}-{grade.upper()}','specialization':spec,'declared_grade':grade,'result_grade':grade,'score_pct':str(score),'anchor_form_id':f'RUBRIC-{spec.upper()}','unique_parameter_seed':hashlib.sha256(cid.encode()).hexdigest()[:16],'attempt_status':'completed','valid_until':'2027-01-03','is_synthetic':'true'})
  for grade in ['middle','senior']:
   blueprints.append({'blueprint_id':f'BP-{spec.upper()}-{grade.upper()}','specialization':spec,'grade':grade,'assessment_format':'expert dialogue; historical scores are synthetic, not model results','anchor_competencies':'; '.join(skills),'anchor_items':'0','parameterized_items':'0','max_score':'100','pass_threshold':str(83 if grade=='middle' else 100),'grade_change_cooldown_days':'90','equating_method':'fixed evidence rubric; at most 3 targeted questions; independent calibration pending','is_synthetic':'true'})
  for j in range(8):
   vid=f'LV{n:02}{j+1:02}';eid=f'LE{n:02}{j+1:02}';grade='middle' if j%4==0 else 'senior';team=tmin+j%max(1,tmax-tmin)
   desc=f'Синтетическая ИТ-компания разрабатывает {project}. Роль: {label}. В зоне ответственности {team} специалистов'+(' в нескольких группах с тимлидами.' if level!='team_lead' else '.')
   desc+=f' Требуется личный опыт управления, {depth}. Цель на год: надёжная поставка продукта при согласованном бюджете. Обязательны примеры самостоятельных решений, объяснение компромиссов и измеримый результат. Стаж от {ymin} лет, управление от {2 if level=="team_lead" else 4} лет. Зарплата до вычета налогов, без бонусов. Сценарий не является реальным предложением работы.'
   vacancies.append({'vacancy_id':vid,'company_id':eid,'company_name':f'ИТ-компания «Контур продукта {n}.{j+1}» (синтетическая)','company_data_origin':'synthetic IT company','title':label,'specialization':spec,'target_grade':grade,'salary_from_rub':str(low+j%3*20000),'salary_to_rub':str(high+j%3*20000),'currency':'RUB','experience_required_years':str(ymin),'publication_date':'2026-10-06','observed_skill_terms':'; '.join(skills),'matching_requirement_profile':'; '.join(skills),'profile_origin':'team-authored leadership requirements','source_ref':f'AUTHORED-LEADERSHIP-{vid}','is_synthetic':'true','salary_basis':'designed gross monthly scenario, not a market estimate','leadership_level':level,'team_size':str(team),'description':desc})
   employers.append({'company_id':eid,'company_name':vacancies[-1]['company_name'],'industry':'Разработка ИТ-продуктов / SaaS','company_description':desc.split(' Требуется')[0],'contact_channel':'demo-contact-not-real','profile_origin':'synthetic IT company, not a real employer'})
   cases.append({'vacancy_id':vid,'candidate_id':f'LC{n:02}{j+1:03}','case':['strong','partial','missing','contradiction'][j%4],'expected_question_limit':'3','expected_behavior':'clarify missing evidence; no automatic downgrade; no external fact verification'})
 write('candidates',candidates);write('vacancies',vacancies);write('employers',employers);write('assessment_attempts',attempts);write('assessment_blueprints',blueprints);write('dialogue_cases',cases)
 (ROOT/'data/taxonomy.json').write_text(json.dumps(taxonomy,ensure_ascii=False,indent=2),encoding='utf-8')
 rubric={}
 for t in taxonomy:
  management='leadership_level' in t
  domain=', '.join(t['skills'][:3])
  rubric[t['id']]=[
   {'label':'Решения и профессиональная глубина','requirement':f'Личное решение в области {domain}, его механизм, альтернативы и ограничения','question':f'В вашем последнем проекте в области {domain} какой компромисс определил лично принятое вами решение?'},
   {'label':'Масштаб и личная ответственность','requirement':('Масштаб управления, прямые и косвенные подчинённые, делегирование и границы полномочий' if management else 'Самостоятельность, личный вклад и границы ответственности в конкретном проекте'),'question':('Какое решение о работе вашей команды вы принимали лично и где проходила граница ваших полномочий?' if management else 'За какую часть описанного проекта вы отвечали лично и как проверили результат своей работы?')},
   {'label':'Результат и контроль рисков','requirement':'Наблюдаемый результат относительно исходного состояния, способ измерения и контроль побочного риска','question':'Как вы установили, что результат вашего решения улучшился относительно исходного состояния без ухудшения смежных показателей?'}]
 (ROOT/'data/interview_rubrics.json').write_text(json.dumps(rubric,ensure_ascii=False,indent=2),encoding='utf-8')
 write('coverage_by_specialization',[{'specialization':t['id'],'valid_current_source_vacancies':sum(v['specialization']==t['id'] and v['is_synthetic']=='false' for v in vacancies),'market_calibrated_scenarios':sum(v['specialization']==t['id'] and v['is_synthetic']=='true' for v in vacancies),'synthetic_candidate_profiles':sum(c['specialization']==t['id'] for c in candidates)} for t in taxonomy])
 # Independently regenerate the complete matrix from the documented deterministic rule.
 tax={t['id']:t for t in taxonomy};g={'junior':1,'middle':2,'senior':3};top=[]
 with (SOURCE/'data/relevance_labels.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['vacancy_id','candidate_id','expected_relevance','rationale','label_origin'])
  for v in vacancies:
   ranked=[];skills=set(v['matching_requirement_profile'].split('; '))
   for c in candidates:
    exact=v['specialization']==c['specialization'];gap=g[c['current_grade']]-g[v['target_grade']];salary=int(c['expected_salary_from_rub'])<=int(v['salary_to_rub']);common=len(skills&set(c['skills'].split('; ')));family=tax[c['specialization']]['family']==tax[v['specialization']]['family']
    rel=3 if exact and gap==0 and salary and common>=4 else 2 if exact and ((gap>=0 and salary) or gap==0) else 1 if exact or (family and common>=3 and gap>=0) else 0
    w.writerow([v['vacancy_id'],c['candidate_id'],rel,'fixed_role_grade_salary_skills_rule','controlled team-authored oracle; not independent human judgement'])
    if c['profile_visibility']=='employer_searchable':ranked.append((rel,int(c['test_score_pct']),int(c['fsp_evidence_score']),c['candidate_id']))
   for pos,x in enumerate(heapq.nlargest(5,ranked),1):top.append({'vacancy_id':v['vacancy_id'],'expected_rank':pos,'candidate_id':x[3],'selection_rule':'relevance > scenario score > FSP evidence > candidate ID'})
 write('expected_top5',top)
 for p in (SOURCE/'data').glob('*.csv'):shutil.copy2(p,ROOT/'data'/p.name)
 with (ROOT/'data/relevance_labels.csv').open('rb') as src,gzip.open(ROOT/'data/relevance_labels.csv.gz','wb') as dst:shutil.copyfileobj(src,dst)
 report={'candidates':len(candidates),'vacancies':len(vacancies),'specializations':len(taxonomy),'leadership_candidates':640,'leadership_vacancies':64,'leadership_levels':Counter(c['leadership_level'] for c in candidates if c.get('leadership_level')),'pairs':len(candidates)*len(vacancies),'dialogue_cases':len(cases),'salary_provenance':'Leadership salaries are authored scenario budgets, not measured market statistics.'}
 (ROOT/'validation/reports/current/leadership-data-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
