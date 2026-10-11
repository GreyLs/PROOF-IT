"""Fast auditable need parsing with explicit uncertainty and no external API."""
import json
import re
from functools import lru_cache
from pathlib import Path

ALIASES={"PostgreSQL":["postgres","postgresql","постгрес"],"JavaScript":["javascript","js"],"TypeScript":["typescript","ts"],"Node.js":["node.js","nodejs","node"],"C++":["c++","cpp"],"C#":["c#","csharp"],"Kubernetes":["kubernetes","k8s"],"Python":["python","питон"],"SQL":["sql"],"Go":["golang","go"],"React":["react","react.js"],"Machine learning":["machine learning","машинное обучение"],"CI/CD":["ci/cd","ci cd"],".NET":[".net","dotnet"]}

@lru_cache(1)
def taxonomy():return json.loads((Path(__file__).resolve().parents[1]/"data/taxonomy.json").read_text(encoding="utf-8"))

def skill_mentions(text):
    skills=sorted({s for role in taxonomy() for s in role["skills"]})
    found=[]
    for skill in skills:
        values=ALIASES.get(skill,[skill])
        if any(re.search(r"(?<![\w])"+re.escape(v)+r"(?![\w])",text,re.I) for v in values):found.append(skill)
    return found

def private_text(text):
    """Retain trusted public role labels while removing user-provided PII."""
    from worker.workbench import redact
    labels={f"__ROLE_{i}__":role['label'] for i,role in enumerate(taxonomy())}
    for token,label in sorted(labels.items(),key=lambda pair:-len(pair[1])):
        text=re.sub(re.escape(label),lambda match:token,text,flags=re.I)
    text=redact(text)
    for token,label in labels.items():text=text.replace(token,label)
    return text

def parse(payload):
    text=payload["text"]
    if not isinstance(text,str) or not 3<=len(text)<=4000:raise ValueError("text")
    text=private_text(text)
    skills=skill_mentions(text)
    parts=re.split(r"желательно|будет плюсом|nice to have|optional",text,maxsplit=1,flags=re.I)
    required=skill_mentions(parts[0]);optional=skill_mentions(parts[1]) if len(parts)>1 else []
    scored=[]
    for role in taxonomy():
        overlap=len(set(skills)&set(role["skills"]))
        tokens=[p for p in role["id"].split("_") if p not in ("backend","lead","head")]
        explicit=role["label"].casefold() in text.casefold() or role["id"] in text.casefold()
        primary=sum(bool(re.search(r"(?<!\w)"+re.escape(token)+r"(?!\w)",text,re.I)) for token in tokens if len(token)>1)
        score=overlap+2*primary+6*explicit
        # Leadership is a separate goal and never inferred from a long stack.
        if role.get("leadership_level") and not explicit and not re.search(r"lead|head|руковод|директор|начальник|cto",text,re.I):score=0
        scored.append((score,role))
    scored.sort(key=lambda x:(-x[0],x[1]["id"]))
    top=scored[0] if scored else (0,None)
    resolved=top[0]>=2 and (len(scored)<2 or top[0]>scored[1][0])
    grade="senior" if re.search(r"\bsenior\b|сеньор|старш",text,re.I) else "junior" if re.search(r"\bjunior\b|джун|начинающ",text,re.I) else "middle" if re.search(r"\bmiddle\b|мидл",text,re.I) else None
    amount=r"(?:\d{2,3}(?:[ \u00a0]\d{3})+|\d{2,6})"
    salary=re.search(r"(?<!\d)("+amount+r")\s*(?:[-–—]|до|to)?\s*("+amount+r")?\s*(тыс\.?|k|к)?\s*(?:₽|руб|rub)",text,re.I)
    low=high=None
    if salary:
        unit=1000 if salary.group(3) else 1;low=int(re.sub(r"\s","",salary.group(1)))*unit;high=int(re.sub(r"\s","",salary.group(2) or salary.group(1)))*unit
        if low<=0 or high<low:raise ValueError("salary_range")
    format="удалённо" if re.search(r"удал|remote",text,re.I) else "гибрид" if re.search(r"гибрид|hybrid",text,re.I) else "офис" if re.search(r"офис|office",text,re.I) else None
    missing=[name for name,v in (("specialization",resolved),("grade",grade),("salary",low),("work_format",format)) if not v]
    city=next((v for v in ("Москва","Санкт-Петербург","Казань","Новосибирск","Екатеринбург") if v.casefold() in text.casefold()),None)
    return {"specialization":top[1]["id"] if resolved else None,"alternatives":[{"id":r["id"],"label":r["label"]} for score,r in scored[:3] if score>0],"skills":skills,"required_skills":required,"optional_skills":optional,"grade":grade,"salary_from":low,"salary_to":high,"work_format":format,"city":city,"currency":"RUB" if low else None,"needs_confirmation":missing,"created_vacancy":False,"version":"needs-1.0.0"}
