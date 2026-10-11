//! Explicit ranking policy. Benchmark labels are never loaded by the service.
//! Professional relevance precedes assessment score; FSP evidence is only a tie-breaker.
use crate::{
    AppState,
    auth::{Actor, new_id},
    error::{AppError, Result},
};
use axum::{
    Json,
    extract::{Path, Query, State},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sqlx::{Arguments, FromRow, postgres::PgArguments};

#[derive(Clone, Serialize, Deserialize)]
pub struct Specialization {
    pub id: String,
    pub label: String,
    pub family: String,
    pub skills: Vec<String>,
    #[serde(default)]
    pub allowed_grades: Vec<String>,
    #[serde(default)]
    pub leadership_level: Option<String>,
}
pub fn taxonomy() -> &'static [Specialization] {
    static DATA: std::sync::OnceLock<Vec<Specialization>> = std::sync::OnceLock::new();
    DATA.get_or_init(|| {
        serde_json::from_str(include_str!("../data/taxonomy.json")).expect("validated taxonomy")
    })
}
pub fn valid_spec(s: &str) -> bool {
    taxonomy().iter().any(|x| x.id == s)
}
pub fn valid_grade(s: &str) -> bool {
    matches!(s, "junior" | "middle" | "senior")
}
pub fn valid_role_grade(spec: &str, grade: &str) -> bool {
    valid_grade(grade)
        && !(spec == "software_architecture" && grade == "junior")
        && taxonomy().iter().find(|t| t.id == spec).is_none_or(|t| {
            t.allowed_grades.is_empty() || t.allowed_grades.iter().any(|g| g == grade)
        })
}
pub fn is_leadership_spec(spec: &str) -> bool {
    taxonomy()
        .iter()
        .find(|item| item.id == spec)
        .is_some_and(|item| item.leadership_level.is_some())
}
pub fn valid_vacancy_grade(spec: &str, grade: &str) -> bool {
    if is_leadership_spec(spec) {
        grade.is_empty()
    } else {
        valid_role_grade(spec, grade)
    }
}
pub fn grade_rank(s: &str) -> i32 {
    match s {
        "junior" => 0,
        "middle" => 1,
        "senior" => 2,
        _ => -10,
    }
}

#[derive(Clone, Serialize, Deserialize, FromRow, Debug)]
pub struct Candidate {
    pub id: String,
    pub resume_id: String,
    pub target_position: String,
    pub display_name: String,
    pub specialization: String,
    pub confirmed_grade: Option<String>,
    pub grade_evidence: String,
    pub category_scope: Option<String>,
    pub category_proof_id: Option<String>,
    pub experience_years: f64,
    pub skills: Vec<String>,
    pub expected_salary: i32,
    pub work_format: String,
    pub test_score: i32,
    pub assessment_method: String,
    pub test_valid_until: Option<chrono::DateTime<chrono::Utc>>,
    pub fsp_status: String,
    pub fsp_score: i32,
    pub achievements: Value,
    pub employment_confirmed: bool,
    pub qualification_passed: bool,
    pub fsp_event_verified: bool,
    pub synthetic: bool,
    pub profile_updated_at: chrono::DateTime<chrono::Utc>,
    pub verified_skills: Vec<String>,
    pub graph_score: f64,
}
pub const PUBLIC_FIELDS: &str = "id,resume_id,target_position,display_name,specialization,confirmed_grade,grade_evidence,category_scope,category_proof_id,experience_years,skills,expected_salary,work_format,test_score,assessment_method,test_valid_until,fsp_status,fsp_score,achievements,employment_confirmed,qualification_passed,fsp_event_verified,synthetic,profile_updated_at,verified_skills,graph_score";
#[derive(Clone, Serialize, Deserialize, Default, Debug)]
pub struct Need {
    #[serde(default)]
    pub specialization: String,
    #[serde(default)]
    pub grade: String,
    #[serde(default)]
    pub skills: Vec<String>,
    #[serde(default)]
    pub salary_to: i32,
    #[serde(default)]
    pub description: String,
}
#[derive(Serialize, Debug)]
pub struct MatchResult {
    #[serde(flatten)]
    pub candidate: Candidate,
    pub relevance: i32,
    pub matched_skills: Vec<String>,
    pub missing_skills: Vec<String>,
    pub reasons: Vec<String>,
    pub salary_compatible: Option<bool>,
}
pub fn rank(candidate: Candidate, need: &Need) -> MatchResult {
    let needed: std::collections::HashSet<String> =
        need.skills.iter().map(|s| s.to_lowercase()).collect();
    let mut seen = std::collections::HashSet::new();
    let common: Vec<String> = candidate
        .skills
        .iter()
        .filter(|s| needed.contains(&s.to_lowercase()) && seen.insert(s.to_lowercase()))
        .cloned()
        .collect();
    let missing = need
        .skills
        .iter()
        .filter(|s| {
            !candidate
                .skills
                .iter()
                .any(|n| n.to_lowercase() == s.to_lowercase())
        })
        .cloned()
        .collect();
    let role_match =
        need.specialization.is_empty() || candidate.specialization == need.specialization;
    let gap = if need.grade.is_empty() {
        0
    } else {
        grade_rank(candidate.confirmed_grade.as_deref().unwrap_or("")) - grade_rank(&need.grade)
    };
    let salary_ok = need.salary_to <= 0 || candidate.expected_salary <= need.salary_to;
    let enough_skills = needed.is_empty() || common.len() >= needed.len().min(4);
    let specs = taxonomy();
    let related = specs
        .iter()
        .find(|s| s.id == need.specialization)
        .zip(specs.iter().find(|s| s.id == candidate.specialization))
        .is_some_and(|(a, b)| a.family == b.family);
    let relevance = if candidate.confirmed_grade.is_none() {
        0
    } else if role_match && gap == 0 && salary_ok && enough_skills {
        3
    } else if role_match && ((gap >= 0 && salary_ok) || gap == 0) {
        2
    } else if role_match || (related && common.len() >= 3 && gap >= 0) {
        1
    } else {
        0
    };
    let mut reasons = vec![];
    if role_match {
        reasons.push("Специализация соответствует потребности".into());
    } else if related {
        reasons.push("Смежное направление: потребуется проверка переносимых навыков".into());
    }
    if gap == 0 && candidate.grade_evidence == "qualification_test" {
        reasons.push(format!(
            "Грейд {} подтверждён тестом по этому резюме",
            candidate.confirmed_grade.as_deref().unwrap_or("—")
        ));
    } else if gap == 0 && candidate.grade_evidence == "expert_dialogue" {
        reasons.push(format!(
            "Грейд {} подтверждён экспертным диалогом",
            candidate.confirmed_grade.as_deref().unwrap_or("—")
        ));
    } else if gap == 0 {
        reasons.push(format!(
            "Грейд {} заявлен в опубликованном резюме; подтверждение ещё не получено",
            candidate.confirmed_grade.as_deref().unwrap_or("—")
        ));
    } else {
        reasons.push("Подтверждённый грейд отличается от целевого".into());
    }
    if !need.skills.is_empty() {
        reasons.push(format!(
            "Совпали {} из {} навыков профиля; резюме не подтверждает владение каждым навыком",
            common.len(),
            need.skills.len()
        ));
    }
    if need.salary_to > 0 {
        reasons.push(
            if salary_ok {
                "Ожидание по зарплате укладывается в бюджет"
            } else {
                "Ожидание выше бюджета — условия нужно согласовать"
            }
            .into(),
        );
    }
    reasons.push(format!("Оценка по роли: {} из 100", candidate.test_score));
    if candidate.employment_confirmed {
        reasons.push(
            "Сроки и должность согласуются с загруженной электронной трудовой выпиской".into(),
        );
    }
    if candidate.qualification_passed {
        reasons.push("Тест по этому резюме успешно пройден".into());
    }
    if candidate.fsp_event_verified {
        reasons.push("Есть подтверждённое участие в мероприятии ФСП".into());
    }
    reasons.push(if candidate.synthetic {
        "Синтетический профиль и сценарная оценка".into()
    } else if candidate.assessment_method.starts_with("expert-dialogue") {
        "Оценка по экспертному диалогу; факты работы независимо не проверены".into()
    } else {
        "Историческая оценка профиля".into()
    });
    if candidate.fsp_status == "verified" {
        reasons.push(
            "Подтверждённые достижения ФСП учитываются при равенстве основных показателей".into(),
        );
    } else if candidate.fsp_status == "mock_verified" {
        reasons.push("Демонстрационная история ФСП: синтетические записи, не реестр".into());
    } else {
        reasons.push("История ФСП отсутствует; участие в подборе доступно".into());
    }
    MatchResult {
        candidate,
        relevance,
        matched_skills: common,
        missing_skills: missing,
        reasons,
        salary_compatible: if need.salary_to > 0 {
            Some(salary_ok)
        } else {
            None
        },
    }
}
#[cfg(test)]
pub fn sort_results(results: &mut [MatchResult]) {
    results.sort_by(|a, b| {
        b.relevance
            .cmp(&a.relevance)
            .then(b.candidate.graph_score.total_cmp(&a.candidate.graph_score))
            .then(
                b.candidate
                    .employment_confirmed
                    .cmp(&a.candidate.employment_confirmed),
            )
            .then(
                b.candidate
                    .qualification_passed
                    .cmp(&a.candidate.qualification_passed),
            )
            .then(
                b.candidate
                    .fsp_event_verified
                    .cmp(&a.candidate.fsp_event_verified),
            )
            .then(b.candidate.test_score.cmp(&a.candidate.test_score))
            .then(b.candidate.fsp_score.cmp(&a.candidate.fsp_score))
            .then(b.candidate.id.cmp(&a.candidate.id))
            .then(b.candidate.resume_id.cmp(&a.candidate.resume_id))
    });
}
#[derive(Deserialize, Default)]
pub struct Search {
    pub vacancy_id: Option<String>,
    pub specialization: Option<String>,
    pub grade: Option<String>,
    pub skills: Option<String>,
    pub salary_to: Option<i32>,
    pub fsp: Option<String>,
    pub q: Option<String>,
    pub limit: Option<usize>,
    pub offset: Option<usize>,
}
pub async fn search(
    State(s): State<AppState>,
    actor: Actor,
    Query(q): Query<Search>,
) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    let mut need = Need::default();
    if let Some(id) = q.vacancy_id.as_ref() {
        let row:Option<(String,String,Vec<String>,i32,String)>=sqlx::query_as("SELECT specialization,grade,skills,salary_to,description FROM vacancies WHERE id=$1 AND (company_id=$2 OR status='published')").bind(id).bind(&actor.subject_id).fetch_optional(&s.db).await?;
        let Some((specialization, grade, skills, salary_to, description)) = row else {
            return Err(AppError::missing());
        };
        need = Need {
            specialization,
            grade,
            skills,
            salary_to,
            description,
        };
    }
    if let Some(v) = q.specialization.as_ref() {
        if !v.is_empty() && !valid_spec(v) {
            return Err(AppError::bad("Неизвестная специализация"));
        }
        need.specialization = v.clone();
    }
    if let Some(v) = q.grade.as_ref() {
        if !v.is_empty() && !valid_grade(v) {
            return Err(AppError::bad("Неизвестный грейд"));
        }
        need.grade = v.clone();
    }
    if let Some(v) = q.skills.as_ref() {
        need.skills = v
            .split(',')
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .take(30)
            .map(str::to_owned)
            .collect();
    }
    if let Some(v) = q.salary_to {
        need.salary_to = v;
    }
    let mut unique = std::collections::HashSet::new();
    need.skills.retain(|s| unique.insert(s.to_lowercase()));
    // Push filtering and top-k to PostgreSQL. Only a bounded page crosses the API process;
    // no full candidate bank is materialized in Rust on every request.
    // Flatten the equivalent resume union before filtering. A per-candidate
    // LATERAL scan visited the whole bank even for a selective role query.
    // The legacy branch remains gated by absence of ANY resume, including
    // archived/private ones: visibility and ranking semantics are unchanged.
    let base = r#"WITH eligible AS (
      SELECT c.id,r.id AS resume_id,r.target_position,c.display_name,r.specialization,
        r.confirmed_grade,r.grade_evidence,r.category_scope,r.category_proof_id,
        r.experience_years,r.skills,r.expected_salary,r.work_format,
        r.test_score,r.assessment_method,r.test_valid_until,c.fsp_status,c.fsp_score,c.achievements,
        (c.employment_check->>'status'='aligned') AS employment_confirmed,
        r.qualification_passed,
        EXISTS(SELECT 1 FROM fsp_participations fp WHERE fp.candidate_id=c.id AND fp.status IN ('verified','mock_verified')) AS fsp_event_verified,
        c.synthetic,c.profile_updated_at,
        ARRAY(SELECT ss.skill FROM intelligence.skill_support ss WHERE ss.candidate_id=c.id AND ss.strength>=0.5) AS verified_skills,
        coalesce((SELECT sum(ss.strength)/greatest(1,CASE WHEN cardinality($3::text[])=0 THEN count(*)::integer ELSE cardinality($3::text[]) END) FROM intelligence.skill_support ss WHERE ss.candidate_id=c.id AND (cardinality($3::text[])=0 OR ss.skill=ANY($3::text[]))),0)::float8 AS graph_score,
        CASE WHEN $9<0 THEN 0 ELSE (CASE r.confirmed_grade WHEN 'junior' THEN 0 WHEN 'middle' THEN 1 ELSE 2 END)-$9 END AS grade_gap,
        ($4<=0 OR r.expected_salary<=$4) AS salary_ok,
        (SELECT count(DISTINCT fsp_fold(skill)) FROM unnest(r.skills) skill WHERE fsp_fold(skill)=ANY($3::text[])) AS common_skills
      FROM intelligence.resume_category_evidence r JOIN candidates c ON c.id=r.candidate_id
      WHERE r.employer_eligible
      AND ($1='' OR r.specialization=$1) AND ($2='' OR r.confirmed_grade=$2)
      AND ($5='' OR ($5='verified' AND (c.fsp_status='verified' OR EXISTS(SELECT 1 FROM fsp_participations fp WHERE fp.candidate_id=c.id AND fp.status='verified'))) OR ($5='with_history' AND (c.fsp_status IN ('verified','mock_verified') OR EXISTS(SELECT 1 FROM fsp_participations fp WHERE fp.candidate_id=c.id AND fp.status IN ('verified','mock_verified')))) OR ($5='without_history' AND c.fsp_status NOT IN ('verified','mock_verified') AND NOT EXISTS(SELECT 1 FROM fsp_participations fp WHERE fp.candidate_id=c.id AND fp.status IN ('verified','mock_verified'))))
      AND ($6='' OR position($6 in fsp_fold(c.display_name))>0 OR position($6 in fsp_fold(c.id))>0 OR position($6 in fsp_fold(array_to_string(r.skills,' ')))>0 OR position($6 in fsp_fold(r.target_position))>0)
      AND (NOT $7 OR ARRAY(SELECT fsp_fold(x) FROM unnest(r.skills) x) @> $3::text[])
      AND ($8<=0 OR r.expected_salary<=$8)
    ),scored AS (
      SELECT *,CASE WHEN grade_gap=0 AND salary_ok AND (cardinality($3::text[])=0 OR common_skills>=least(4,cardinality($3::text[]))) THEN 3
      WHEN (grade_gap>=0 AND salary_ok) OR grade_gap=0 THEN 2 ELSE 1 END AS match_tier FROM eligible
    )"#;
    let query = q.q.as_deref().unwrap_or("");
    if query.len() > 200 {
        return Err(AppError::bad("Поисковый запрос слишком длинный"));
    }
    let mut args = PgArguments::default();
    args.add(&need.specialization).unwrap();
    args.add(q.grade.as_deref().unwrap_or("")).unwrap();
    args.add(
        need.skills
            .iter()
            .map(|s| s.to_lowercase())
            .collect::<Vec<_>>(),
    )
    .unwrap();
    args.add(need.salary_to).unwrap();
    args.add(q.fsp.as_deref().unwrap_or("")).unwrap();
    args.add(query.to_lowercase()).unwrap();
    args.add(q.skills.is_some()).unwrap();
    args.add(q.salary_to.unwrap_or(0)).unwrap();
    args.add(if need.grade.is_empty() {
        -1
    } else {
        grade_rank(&need.grade)
    })
    .unwrap();
    let total: i64 =
        sqlx::query_scalar_with(&format!("{base} SELECT count(*) FROM scored"), args.clone())
            .fetch_one(&s.db)
            .await?;
    let offset = q.offset.unwrap_or(0).min(total as usize);
    let limit = q.limit.unwrap_or(20).clamp(1, 100);
    args.add(limit as i64).unwrap();
    args.add(offset as i64).unwrap();
    let candidates=sqlx::query_as_with::<_,Candidate,_>(&format!("{base} SELECT {PUBLIC_FIELDS} FROM scored ORDER BY match_tier DESC,graph_score DESC,employment_confirmed DESC,qualification_passed DESC,fsp_event_verified DESC,test_score DESC,fsp_score DESC,id DESC,resume_id DESC LIMIT $10 OFFSET $11"),args).fetch_all(&s.db).await?;
    let results: Vec<_> = candidates.into_iter().map(|c| rank(c, &need)).collect();
    Ok(Json(
        json!({"items":results,"total":total,"offset":offset,"limit":limit,"need":need,"ranking_version":"evidence-graph-3.1","eligibility_version":"verified-category-1.0","policy":"Действующее подтверждение категории → релевантность → граф доказательств → квалификация → подтверждённые события → ID"}),
    ))
}
pub async fn detail(
    State(s): State<AppState>,
    actor: Actor,
    Path(id): Path<String>,
) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    let candidate=sqlx::query_as::<_,Candidate>(r#"
      SELECT c.id,r.id AS resume_id,r.target_position,c.display_name,r.specialization,
        r.confirmed_grade,coalesce(r.grade_evidence,'unconfirmed') AS grade_evidence,
        r.category_scope,r.category_proof_id,r.experience_years,r.skills,r.expected_salary,
        r.work_format,r.test_score,coalesce(r.assessment_method,'unconfirmed') AS assessment_method,
        r.test_valid_until,c.fsp_status,c.fsp_score,c.achievements,
        (c.employment_check->>'status'='aligned') AS employment_confirmed,r.qualification_passed,
        EXISTS(SELECT 1 FROM fsp_participations fp WHERE fp.candidate_id=c.id AND fp.status IN ('verified','mock_verified')) AS fsp_event_verified,
        c.synthetic,c.profile_updated_at,
        ARRAY(SELECT ss.skill FROM intelligence.skill_support ss WHERE ss.candidate_id=c.id AND ss.strength>=0.5) AS verified_skills,
        coalesce((SELECT avg(ss.strength) FROM intelligence.skill_support ss WHERE ss.candidate_id=c.id),0)::float8 AS graph_score
      FROM intelligence.resume_category_evidence r JOIN candidates c ON c.id=r.candidate_id
      WHERE c.id=$1 AND NOT c.employment_blocked AND c.consent_processing
        AND r.status<>'archived' AND (r.employer_eligible
          OR EXISTS(SELECT 1 FROM invitations i WHERE i.candidate_id=c.id AND i.company_id=$2
            AND i.status='accepted' AND (i.resume_id=r.id OR (i.resume_id IS NULL
              AND r.visibility='employer_searchable' AND r.status='published' AND c.consent_publication)))
          OR EXISTS(SELECT 1 FROM applications ap JOIN vacancies v ON v.id=ap.vacancy_id
            WHERE ap.candidate_id=c.id AND v.company_id=$2 AND ap.status<>'withdrawn'
            AND (ap.resume_id=r.id OR (ap.resume_id IS NULL
              AND r.visibility='employer_searchable' AND r.status='published' AND c.consent_publication))))
      ORDER BY r.employer_eligible DESC,r.qualification_passed DESC,r.id LIMIT 1"#)
        .bind(&id).bind(&actor.subject_id).fetch_optional(&s.db).await?.ok_or_else(AppError::missing)?;
    let contacts: Option<Value> = sqlx::query_scalar("SELECT jsonb_build_object('full_name',full_name,'email',email,'phone',phone) FROM candidates c WHERE c.id=$1 AND c.consent_processing AND NOT EXISTS(SELECT 1 FROM contact_revocations r WHERE r.candidate_id=c.id AND r.company_id=$2) AND (EXISTS(SELECT 1 FROM invitations WHERE candidate_id=c.id AND company_id=$2 AND status='accepted') OR EXISTS(SELECT 1 FROM applications a JOIN vacancies v ON v.id=a.vacancy_id WHERE a.candidate_id=c.id AND v.company_id=$2 AND a.status<>'withdrawn'))").bind(&id).bind(&actor.subject_id).fetch_optional(&s.db).await?;
    let granted = contacts.is_some();
    if granted {
        crate::db::audit(
            &s,
            &actor.id,
            "contacts.viewed",
            &id,
            json!({"company_id":actor.subject_id}),
        )
        .await?;
    }
    Ok(Json(
        json!({"candidate":candidate,"contacts_released":granted,"contacts":contacts}),
    ))
}
#[derive(Deserialize)]
pub struct SaveSearch {
    pub name: String,
    pub query: Value,
    pub candidate_ids: Vec<String>,
}
pub async fn save(
    State(s): State<AppState>,
    actor: Actor,
    Json(input): Json<SaveSearch>,
) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    if input.name.trim().is_empty()
        || input.name.len() > 150
        || input.candidate_ids.len() > 100
        || input.query.to_string().len() > 10000
    {
        return Err(AppError::bad("Некорректная подборка"));
    }
    let id = new_id("S");
    sqlx::query(
        "INSERT INTO saved_searches(id,company_id,name,query,candidate_ids) VALUES($1,$2,$3,$4,$5)",
    )
    .bind(&id)
    .bind(&actor.subject_id)
    .bind(input.name)
    .bind(input.query)
    .bind(input.candidate_ids)
    .execute(&s.db)
    .await?;
    Ok(Json(json!({"id":id})))
}
pub async fn saved(State(s): State<AppState>, actor: Actor) -> Result<Json<Value>> {
    actor.verified_employer(&s).await?;
    let items:Vec<Value>=sqlx::query_scalar("SELECT to_jsonb(s) FROM saved_searches s WHERE company_id=$1 ORDER BY created_at DESC LIMIT 100").bind(&actor.subject_id).fetch_all(&s.db).await?;
    Ok(Json(json!({"items":items})))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn c() -> Candidate {
        Candidate {
            id: "C1".into(),
            resume_id: "R1".into(),
            target_position: "Backend developer".into(),
            display_name: "Тест".into(),
            specialization: "backend_python".into(),
            confirmed_grade: Some("middle".into()),
            grade_evidence: "qualification_test".into(),
            category_scope: Some("role-knowledge".into()),
            category_proof_id: Some("CERT-test".into()),
            experience_years: 3.,
            skills: vec!["Python".into(), "SQL".into()],
            expected_salary: 200000,
            work_format: "удалённо".into(),
            test_score: 85,
            assessment_method: "synthetic_scenario".into(),
            test_valid_until: None,
            fsp_status: "not_linked".into(),
            fsp_score: 0,
            achievements: json!([]),
            employment_confirmed: false,
            qualification_passed: false,
            fsp_event_verified: false,
            synthetic: true,
            profile_updated_at: chrono::Utc::now(),
            verified_skills: vec![],
            graph_score: 0.0,
        }
    }
    #[test]
    fn fsp_never_overrides_professional_relevance() {
        let need = Need {
            specialization: "backend_python".into(),
            grade: "middle".into(),
            skills: vec!["Python".into()],
            salary_to: 300000,
            ..Default::default()
        };
        let a = c();
        let mut b = c();
        b.specialization = "devops".into();
        b.test_score = 100;
        b.fsp_score = 100;
        let mut results = vec![rank(b, &need), rank(a, &need)];
        sort_results(&mut results);
        assert_eq!(results[0].candidate.specialization, "backend_python");
    }
    #[test]
    fn salary_gap_is_explained() {
        let n = Need {
            salary_to: 100000,
            ..Default::default()
        };
        let r = rank(c(), &n);
        assert_eq!(r.salary_compatible, Some(false));
        assert_eq!(r.relevance, 2);
    }
    #[test]
    fn unconfirmed_profile_cannot_acquire_relevance_from_an_empty_need() {
        let mut candidate = c();
        candidate.confirmed_grade = None;
        assert_eq!(rank(candidate, &Need::default()).relevance, 0);
    }
    #[test]
    fn in_memory_order_matches_sql_graph_and_resume_tie_breaks() {
        let need = Need::default();
        let mut stronger = c();
        stronger.graph_score = 0.8;
        let mut weaker = c();
        weaker.graph_score = 0.2;
        weaker.employment_confirmed = true;
        let mut tied = stronger.clone();
        tied.resume_id = "R2".into();
        let mut result = vec![rank(weaker, &need), rank(stronger, &need), rank(tied, &need)];
        sort_results(&mut result);
        assert_eq!(result[0].candidate.resume_id, "R2");
        assert_eq!(result[1].candidate.graph_score, 0.8);
    }
}
