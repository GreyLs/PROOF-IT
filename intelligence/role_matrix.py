"""Authored role rubrics mapped to attributed O*NET occupational references.

Not an O*NET certificate and not a reproduction of licensed SFIA descriptions.
Knowledge measurement and observed engineering responsibility remain separate.
"""
VERSION = 'role-matrix-1.0.0'
SOURCES = {
    'software': 'https://www.onetonline.org/link/summary/15-1252.00',
    'science': 'https://www.onetonline.org/link/summary/15-2051.00',
    'data': 'https://www.onetonline.org/link/summary/15-1243.01',
}
GROUPS = {
    'software': [('correctness','Корректность и инварианты','Проверяемый контракт, граничные случаи и обработка ошибок'),
                 ('testing','Проверка и регрессии','Исполнимые тесты, отрицательные случаи и регрессионная защита'),
                 ('design','Проектирование','Обоснованные интерфейсы, альтернативы, сложность и ограничения'),
                 ('delivery','Эксплуатация и безопасность','Безопасный выпуск, наблюдаемость и обработка отказов')],
    'science': [('statistics','Статистика и постановка','Целевая величина, выборка, неопределённость и проверяемая гипотеза'),
                ('evaluation','Валидация модели','Независимый holdout, отсутствие leakage, калибровка и срезы'),
                ('reproducibility','Воспроизводимость','Версии данных, seed, окружение и исполнимый эксперимент'),
                ('deployment','Практическая применимость','Ошибки, дрейф, стоимость и связь с решаемой задачей')],
    'data': [('semantics','Семантика данных','Гранулярность, ключи, качество и схема источника'),
             ('pipeline','Надёжность потока','Идемпотентность, late data, backfill и восстановление'),
             ('query','SQL и вычисления','Корректность преобразований, план запроса и ресурсные границы'),
             ('governance','Контроль и lineage','Происхождение, доступ, контракт и наблюдаемость')],
    'ml': [('evaluation','Качество модели','Раздельная проверка модели, leakage и калибровка'),
           ('serving','Инженерия inference','Latency, batching, ресурсы и безопасный fallback'),
           ('lifecycle','Жизненный цикл','Версии, мониторинг дрейфа, rollback и воспроизводимость'),
           ('testing','Исполнимая проверка','Тесты данных, модели, сервиса и отказов')],
}
LEVELS = {
    'junior': 'Выполняет ограниченную задачу по заданному контракту и объясняет собственные изменения.',
    'middle': 'Самостоятельно выбирает решение, тестирует альтернативы и отвечает за результат в рабочем контексте.',
    'senior': 'Обосновывает системные компромиссы, управляет риском и демонстрирует проверяемый результат на значимом масштабе.',
}
CODING = {'backend_python','backend_java','backend_csharp','backend_cpp','frontend_development',
          'mobile_development','one_c','qa_engineering','devops','software_architecture',
          'ml_data_science','data_engineering','mlops','data_analytics','cybersecurity',
          'lead_engineering','lead_data','head_platform','head_data'}

def family(spec):
    if spec in ('mlops',): return 'ml'
    if spec in ('ml_data_science','data_analytics'): return 'science'
    if spec in ('data_engineering','lead_data','head_data'): return 'data'
    if spec in CODING: return 'software'
    return None

def matrix(payload):
    spec = payload['specialization']
    group = family(spec)
    if not group:
        return {'version':VERSION,'specialization':spec,'supported':False,
                'knowledge_test_is_professional_certification':False,'criteria':[]}
    source_group = 'science' if group=='ml' else group
    return {'version':VERSION,'specialization':spec,'supported':True,'family':group,
            'knowledge_test_is_professional_certification':False,
            'criteria':[{'id':key,'name':name,'observable':observable,'required':True,
                         'minimum_by_grade':{'junior':1,'middle':2,'senior':3}}
                        for key,name,observable in GROUPS[group]],
            'scale':{'0':'Не продемонстрировано','1':'Выполнение по заданному контракту',
                     '2':'Самостоятельное решение с проверкой','3':'Системное обоснование и ответственность',
                     '4':'Независимо проверенный системный результат'},
            'grade_behaviors':LEVELS,'sources':[SOURCES[source_group]],
            'source_attribution':'O*NET OnLine / USDOL; custom rubric and mapping, no endorsement',
            'license':'https://www.onetcenter.org/license_db.html',
            'required_evidence':['role-specific knowledge','artifact-bound practical defense','independent expert review'],
            'leadership_requires_separate_evidence':spec.startswith(('lead_','head_','director_'))}

def attestation(payload):
    rubric = matrix(payload)
    grade = payload['grade']
    if grade not in LEVELS: raise ValueError('grade')
    scores = payload.get('scores',{})
    if not isinstance(scores,dict): raise ValueError('scores')
    required = [criterion['id'] for criterion in rubric['criteria']]
    if set(scores)!=set(required) or any(isinstance(v,bool) or not isinstance(v,int) or not 0<=v<=4 for v in scores.values()):
        raise ValueError('rubric_scores')
    threshold = {'junior':1,'middle':2,'senior':3}[grade]
    practical = bool(required) and all(scores[key]>=threshold for key in required)
    conditions = {'role_supported':rubric['supported'],'practical_criteria_met':practical,
                  'identity_bound':payload.get('identity_bound') is True,
                  'artifact_intact':payload.get('artifact_intact') is True,
                  'independent_review':payload.get('independent_review') is True,
                  'knowledge_scope_verified':payload.get('knowledge_scope_verified') is True,
                  'leadership_evidence':not rubric.get('leadership_requires_separate_evidence') or payload.get('leadership_verified') is True}
    return {'version':VERSION,'specialization':payload['specialization'],'target_grade':grade,
            'criteria_scores':scores,'conditions':conditions,'role_confirmation_eligible':all(conditions.values()),
            'grade_auto_promoted':False,'missing_conditions':[key for key,value in conditions.items() if not value]}
