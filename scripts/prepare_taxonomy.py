from pathlib import Path
import csv,json
root=Path(__file__).resolve().parents[1]
labels={
'backend_python':('Python / Backend','backend'),'backend_java':('Java / Backend','backend'),'backend_csharp':('.NET / C#','backend'),'backend_cpp':('C++ разработка','backend'),
'qa_engineering':('Тестирование / QA','quality'),'devops':('DevOps','infrastructure'),'data_analytics':('Аналитика данных','data'),'one_c':('Разработка 1С','enterprise'),'system_administration':('Системное администрирование','infrastructure'),
'ml_data_science':('ML / Data Science','data'),'mlops':('MLOps','infrastructure'),'software_architecture':('Архитектура ПО','architecture'),'data_engineering':('Data Engineering','data'),'system_analysis':('Системный анализ','analysis'),'frontend_development':('Frontend','frontend'),'mobile_development':('Мобильная разработка','mobile'),'cybersecurity':('Информационная безопасность','security')}
with (root/'data/vacancies.csv').open(encoding='utf-8-sig') as f: vacancies=list(csv.DictReader(f))
roles={}
for row in vacancies:
 key=row['specialization']
 label,family=labels.get(key,(key,'other'))
 roles[key]={'id':key,'label':label,'family':family,'skills':row['matching_requirement_profile'].split('; ')}
(root/'data/taxonomy.json').write_text(json.dumps(list(roles.values()),ensure_ascii=False,indent=2),encoding='utf-8')
print([(x['id'],x['label']) for x in roles.values()])
