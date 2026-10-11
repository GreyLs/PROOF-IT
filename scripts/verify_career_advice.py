"""Three real Qwen career cases: actionable advice, privacy, read-only profile."""
import hashlib,json,re,time,uuid
from pathlib import Path
from scripts.workbench_test_fixture import Fixture
ROOT=Path(__file__).resolve().parents[1]
CASES=[('beginner','Я начинаю карьеру: знаю основы Python, люблю данные. Предложи два направления, разницу между ними и практический план первых 14 дней.'),('transition','Работаю четыре года Python backend-разработчиком, хочу перейти в data engineering. Какие навыки перенести, чего не хватает и что сделать в ближайшие 14 дней? Не придумывай мой опыт.'),('horizontal','Хочу горизонтально развиваться из Python-разработки в смежную роль без управленческой карьеры. Сравни два пути и предложи маленький проект на 14 дней. Мой контакт: privacy@example.test +7 (999) 111-22-33 — не используй его.')]
def main():
    f=Fixture();items=[]
    try:
        for name,text in CASES:
            c,u=f.register('candidate');rid='CA'+uuid.uuid4().hex
            f.db.execute("INSERT INTO resume_profiles(id,candidate_id,target_position,specialization,declared_grade,experience_years,skills,about,expected_salary,visibility,status) VALUES(%s,%s,'Python Backend','backend_python','middle',4,ARRAY['Python','PostgreSQL'],'Разработка API и обработка данных, автоматические тесты и ревью.',200000,'private','draft')",(rid,u['subject_id']))
            before=f.db.execute('SELECT to_jsonb(r) FROM resume_profiles r WHERE id=%s',(rid,)).fetchone()[0];start=time.perf_counter();r=c.post('/career-consultant',json={'text':text});r.raise_for_status();reply=r.json()['reply'];after=f.db.execute('SELECT to_jsonb(r) FROM resume_profiles r WHERE id=%s',(rid,)).fetchone()[0]
            criteria={'substantial':len(reply)>300,'uses_professional_context':bool(re.search(r'Python|SQL|данн|разработ',reply,re.I)),'actionable_plan':bool(re.search(r'план|шаг|день|дни|недел|проект|14',reply,re.I)),'no_contact_leak':'example.test'not in reply and '999'not in reply,'profile_unchanged':before==after}
            items.append({'case':name,'latency_ms':round((time.perf_counter()-start)*1000,2),'criteria':criteria,'reply':reply,'passed':all(criteria.values())});print(name,items[-1]['passed'],flush=True)
            assert items[-1]['passed']
    finally:
        f.close();report={'model':'qwen3:8b','cases':items,'completed':len(items)==len(CASES),'passed':len(items)==len(CASES) and all(x['passed']for x in items),'method':'Real requests; explicit content/privacy/immutability checks, not independent human ratings.'};(ROOT/'validation/reports/current/career-advice.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
