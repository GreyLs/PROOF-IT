from pathlib import Path
import json
import re
ROOT=Path(__file__).resolve().parents[1]
S={'type':'string'};I={'type':'integer'};B={'type':'boolean'};A={'type':'array','items':S}
def obj(properties,required=None):return {'type':'object','properties':properties,'required':required if required is not None else list(properties)}
def enum(*values):return {'type':'string','enum':list(values)}
def ref(name):return {'$ref':f'#/components/schemas/{name}'}
def array(name):return {'type':'array','items':ref(name)}
schemas={
'Error':obj({'error':obj({'code':I,'message':S})}),
'User':obj({'id':S,'email':S,'role':enum('candidate','employer'),'subject_id':S,'synthetic':B}),
'Candidate':obj({'id':S,'display_name':S,'specialization':S,'confirmed_grade':{'type':['string','null']},'experience_years':{'type':'number'},'skills':A,'expected_salary':I,'work_format':S,'test_score':I,'test_valid_until':{'type':['string','null'],'format':'date-time'},'fsp_status':enum('not_linked','pending','mock_verified','verified'),'fsp_score':I,'achievements':{'type':'array','items':{'type':'object'}},'synthetic':B,'profile_updated_at':{'type':'string','format':'date-time'},'relevance':{'type':'integer','minimum':0,'maximum':3},'matched_skills':A,'missing_skills':A,'reasons':A,'salary_compatible':{'type':['boolean','null']}},['id','display_name','specialization','confirmed_grade','skills','test_score']),
'ProfileInput':obj({'full_name':S,'email':S,'phone':S,'specialization':S,'declared_grade':enum('junior','middle','senior'),'industry':S,'experience_years':{'type':'number','minimum':0,'maximum':80},'skills':A,'soft_skills':A,'about':S,'expected_salary':{'type':'integer','minimum':0},'work_format':S,'visibility':enum('private','employer_searchable'),'consent_processing':B,'consent_publication':B,'fsp_id':{'type':['string','null']},'version':I}),
'Company':obj({'name':S,'description':S,'industry':S,'contact':S}),
'VacancyInput':obj({'title':S,'description':S,'specialization':S,'grade':enum('junior','middle','senior'),'skills':A,'salary_from':{'type':'integer','minimum':1},'salary_to':{'type':'integer','minimum':1},'work_format':S,'status':enum('draft','published','closed')}),
'Vacancy':{'allOf':[ref('VacancyInput'),obj({'id':S,'company_id':S,'company_name':S,'currency':enum('RUB'),'origin':S,'source_ref':S,'synthetic':B,'created_at':S,'updated_at':S})]},
'OfferInput':obj({'candidate_id':S,'vacancy_id':{'type':['string','null']},'title':S,'description':S,'salary_from':{'type':'integer','minimum':1},'salary_to':{'type':'integer','minimum':1},'idempotency_key':{'type':'string','maxLength':100}}),
'Invitation':{'allOf':[ref('OfferInput'),obj({'id':S,'company_id':S,'company_name':S,'contact':S,'currency':enum('RUB'),'status':enum('sent','viewed','accepted','declined'),'created_at':S,'responded_at':{'type':['string','null']}})]},
'AssessmentItem':obj({'id':S,'competency':S,'prompt':S,'options':A,'points':I,'anchor':B}),
'AssessmentStart':obj({'specialization':S,'grade':enum('junior','middle','senior'),'industry':S}),
'AssessmentAttempt':obj({'id':S,'items':array('AssessmentItem'),'expires_at':S,'grade':S,'specialization':S},['id','items','expires_at','grade','specialization']),
'AssessmentResult':obj({'id':S,'passed':B,'score':I,'threshold':I,'parameter_score':I,'specialization':S,'declared_grade':S,'confirmed_grade':{'type':['string','null']},'items':{'type':'array','items':obj({'id':S,'competency':S,'correct':B,'earned':I,'max':I,'feedback':S})},'message':S,'suggest_higher':B,'cooldown_days':I}),
'Document':obj({'id':S,'user_id':S,'kind':enum('resume','vacancy','profile_export'),'filename':S,'sha256':S,'bytes':I,'status':enum('queued','processing','review','completed','failed'),'progress':I,'result':{'type':['object','null'],'description':'fields, reviewed_fields, provenance[field]={page,quote,method}, pages[], warnings[], engine; profile_export output_key'},'error':{'type':['string','null']},'attempts':I,'created_at':S,'updated_at':S},['id','kind','filename','status','progress']),
'Application':obj({'id':S,'vacancy_id':S,'candidate_id':S,'status':enum('sent','viewed','interview','rejected','withdrawn'),'message':S,'created_at':S}),
'TaskInput':obj({'candidate_id':S,'title':S,'prompt':S}),
'Task':{'allOf':[ref('TaskInput'),obj({'id':S,'company_id':S,'response':{'type':['string','null']},'feedback':{'type':['string','null']},'score':{'type':['integer','null']},'status':enum('pending','submitted','reviewed'),'created_at':S,'submitted_at':{'type':['string','null']},'reviewed_at':{'type':['string','null']}})]},
'SavedSearch':obj({'id':S,'name':S,'query':{'type':'object'},'candidate_ids':A,'created_at':S}),
'TalantixConnect':obj({'access_token':{'type':'string','minLength':20,'maxLength':4096},'refresh_token':{'type':['string','null'],'minLength':20,'maxLength':4096},'expires_in':{'type':'integer','minimum':60,'maximum':172800},'refresh_token_expires_in':{'type':'integer','minimum':60,'maximum':31536000}},['access_token']),
'TalantixSource':obj({'source_id':{'type':'integer','minimum':1}}),
'TalantixVacancyMapping':obj({'external_vacancy_id':{'type':'integer','minimum':1}}),
}
paths={}
def route(method,path,summary,body=None,response=None,public=False,queries=None,description=''):
    op={'summary':summary,'description':description or summary,'operationId':method+'_'+path.strip('/').replace('/','_').replace('{','').replace('}','').replace('-','_').replace('.','_'),'tags':[path.split('/')[1]],'security':[] if public else [{'sessionCookie':[]},{'bearerSession':[]}],
      'responses':{'200':{'description':'Успешный результат','content':{'application/json':{'schema':response or {'type':'object'}}}}}}
    for code,desc in [('400','Ошибка входных данных'),('401','Нет действующей подтверждённой сессии'),('403','Недостаточно прав или origin не совпадает'),('404','Объект не найден в доступной пользователю области'),('409','Конфликт состояния, version, уникальности или cooldown'),('429','Ограничение параллельных запросов или очереди'),('500','Внутренняя ошибка'),('503','Временная недоступность зависимости')]:op['responses'][code]={'description':desc,'content':{'application/json':{'schema':ref('Error')}}}
    op['responses']['422']={'description':'Ошибка десериализации тела (Axum): текстовая диагностика','content':{'text/plain':{'schema':S}}}
    params=[]
    for name in re.findall(r'\{([^}]+)\}',path):params.append({'name':name,'in':'path','required':True,'schema':S})
    for name,schema in (queries or {}).items():params.append({'name':name,'in':'query','required':False,'schema':schema})
    if params:op['parameters']=params
    if body:op['requestBody']={'required':True,'content':{'application/json':{'schema':ref(body) if isinstance(body,str) else body}}}
    paths[path]=paths.get(path,{})|{method:op}
route('get','/health','Проверка API и подключения к БД',public=True,response=obj({'status':S,'version':S,'uptime_seconds':I}))
route('get','/meta','Настройки интерфейса и справочник специализаций',public=True)
route('get','/dashboard','Агрегаты своего кабинета и категорий')
route('post','/auth/register','Регистрация и письмо подтверждения',obj({'email':{'type':'string','format':'email'},'password':{'type':'string','minLength':10,'maxLength':256},'role':enum('candidate','employer'),'name':S,'consent_processing':B}),public=True,description='В demo-mode возвращается development_mail для локальной песочницы. Иначе письмо отправляется по SMTP; токен не возвращается. Контакты не публикуются автоматически.')
route('post','/auth/verify','Однократное подтверждение email',obj({'token':S}),obj({'user':ref('User')}),public=True,description='TTL 30 минут. Устанавливает HttpOnly cookie fsp_session; для HTTPS используется __Host-fsp_session с Secure.')
route('post','/auth/login','Вход по email и паролю',obj({'email':S,'password':S}),obj({'user':ref('User')}),public=True)
route('get','/auth/me','Текущая сессия',response=obj({'user':ref('User')}))
route('post','/auth/logout','Завершение текущей сессии',response=obj({'ok':B}),public=True)
route('get','/profile','Собственный профиль кандидата или компании',response=obj({'profile':{'type':'object'}}))
route('put','/profile','Изменение своего профиля кандидатом','ProfileInput',obj({'profile':{'type':'object'}}),description='Только candidate. version предотвращает потерю изменений. Изменение специализации снимает прежнюю категорию, но не cooldown. Ввод FSP ID не подтверждает достижения.')
route('put','/company','Изменение своей компании работодателем','Company',obj({'profile':{'type':'object'}}))
route('get','/candidates','Объяснимая подборка и фильтрация',response=obj({'items':array('Candidate'),'total':I,'offset':I,'limit':I,'need':{'type':'object'},'ranking_version':S,'policy':S}),queries={'vacancy_id':S,'specialization':S,'grade':enum('junior','middle','senior'),'skills':{'type':'string','description':'Обязательные навыки через запятую'},'salary_to':I,'fsp':enum('verified','with_history','without_history'),'q':S,'limit':{'type':'integer','minimum':1,'maximum':100},'offset':{'type':'integer','minimum':0}},description='Только employer. Контактов нет в схеме результата. categories допускаются только по пройденному неистёкшему тесту и двум согласиям.')
route('get','/candidates/{id}','Профиль кандидата с условным раскрытием контактов',response=obj({'candidate':ref('Candidate'),'contacts_released':B,'contacts':{'type':['object','null'],'properties':{'full_name':S,'email':S,'phone':S}}}),description='Только employer. Контакты выдаются именно этой компании при accepted-приглашении или её действующем отклике. Чужое согласие не подходит.')
route('get','/saved-searches','Сохранённые подборки своей компании',response=obj({'items':array('SavedSearch')}))
route('post','/saved-searches','Сохранить фильтры и снимок подборки',obj({'name':S,'query':{'type':'object'},'candidate_ids':A}),obj({'id':S}))
route('get','/invitations','Свои входящие или исходящие приглашения',response=obj({'items':array('Invitation')}))
route('post','/invitations','Предложение кандидату с зарплатой','OfferInput',obj({'invitation':ref('Invitation')}),description='Только employer. Привязка к вакансии необязательна; если есть — вакансия должна принадлежать компании. salary_from>0, salary_to>=salary_from. Идемпотентность по company_id/idempotency_key.')
route('put','/invitations/{id}','Ответ кандидата на своё приглашение',obj({'status':enum('viewed','accepted','declined')}),obj({'invitation':ref('Invitation'),'contacts_released':B}),description='Только candidate-владелец. Терминальные accepted/declined нельзя менять. Повтор того же состояния допустим.')
route('get','/vacancies','Список опубликованных вакансий или своих потребностей',response=obj({'items':array('Vacancy')}),queries={'specialization':S,'grade':S,'mine':B,'company_id':S,'q':S,'limit':{'type':'integer','maximum':500},'offset':I})
route('post','/vacancies','Создать вакансию или непубличную потребность','VacancyInput',obj({'vacancy':ref('Vacancy')}))
route('put','/vacancies/{id}','Изменить свою вакансию','VacancyInput',obj({'vacancy':ref('Vacancy')}))
route('post','/vacancies/{id}/apply','Самостоятельный отклик кандидата',obj({'message':S}),obj({'application':ref('Application')}),description='Отклик открывает контакты владельцу вакансии. Повтор не создаёт дубликат.')
route('get','/applications','Свои отклики или отклики на вакансии компании',response=obj({'items':array('Application')}))
route('put','/applications/{id}','Изменить статус отклика',obj({'status':enum('viewed','interview','rejected','withdrawn')}),obj({'application':ref('Application')}),description='Candidate может только отозвать свой отклик. Employer меняет только отклики на свои вакансии; withdrawn нельзя вернуть в обработку.')
route('get','/tasks','Свои короткие задания',response=obj({'items':array('Task')}))
route('post','/tasks','Предложить кандидату короткое задание','TaskInput',obj({'task':ref('Task')}),description='Не чаще одного задания в неделю на пару компания/кандидат.')
route('put','/tasks/{id}','Решение кандидата или обратная связь работодателя',obj({'response':S,'score':{'type':'integer','minimum':0,'maximum':100},'feedback':S},[]),obj({'task':ref('Task')}),description='Candidate передаёт response. Employer передаёт score/feedback. Проверка не меняет подтверждённый грейд.')
route('get','/assessments','Исторические оценки профиля')
route('post','/assessments','Удалённый сценарий тестов: 410 Gone',description='Тесты заменены экспертным диалогом.')
route('post','/assessments/{id}/submit','Удалённый сценарий тестов: 410 Gone')
route('get','/dialogues','История собственных экспертных диалогов',response=obj({'items':{'type':'array','items':{'type':'object'}}}))
route('post','/dialogues','Начать или возобновить разбор реального проекта',obj({'mode':enum('profile','vacancy'),'vacancy_id':{'type':['string','null']}},['mode']),description='Candidate; согласие; заполненный профиль; опубликованная вакансия. До трёх уточнений опыта. Для profile далее обязательны три индивидуальных кейса без кода. 409 при cooldown, 429 модель занята, 503 модель недоступна. Автоматического понижения нет.')
route('get','/dialogues/{id}','Собственный диалог с цитатами и результатом',description='404 для чужого ID; внутренний снимок не раскрывается.')
route('post','/dialogues/{id}/messages','Ответить о профессиональном опыте',obj({'text':{'type':'string','minLength':1,'maxLength':3500},'revision':I}),description='Проверка темы; неподходящий ответ возвращает redirect и не расходует вопрос. 409 для изменённого профиля/вакансии, завершённого диалога или устаревшей revision. Только profile может присвоить грейд. 503 не засчитывает ответ.')
route('post','/dialogues/{id}/cases','Подготовить три индивидуальных кейса',description='Только владелец profile-сессии в phase=cases после разбора проекта. Генерация и отдельная LLM-проверка; каждый текст до 800 символов. Повтор возвращает сохранённый набор. Оценки кейсов скрыты до завершения всех трёх. Финальный грейд требует прохождения проекта и кейсов.')

route('get','/documents','Документы текущего пользователя',response=obj({'items':array('Document')}))
route('post','/documents','Загрузить PDF/PNG/JPEG',response=obj({'document':ref('Document'),'duplicate':B}),queries={'kind':enum('resume','vacancy','employment')},description='Максимум 20 МБ и 40 страниц; до 5 активных документов пользователя. Тип по magic bytes. Идемпотентность по user_id/sha256/kind; OCR асинхронный. Candidate: resume/employment; employer: resume/vacancy. Employment требует согласия, автоматически сверяется с сохранённым резюме и не допускает ручного изменения извлечённых полей.')
paths['/documents']['post']['requestBody']={'required':True,'content':{'multipart/form-data':{'schema':obj({'file':{'type':'string','format':'binary'}})}}}
paths['/documents']['post']['responses']['413']={'description':'Файл или тело запроса превышает 20 МБ'}
route('get','/documents/{id}','Состояние и черновик своего документа',response=obj({'document':ref('Document')}))
route('put','/documents/{id}','Подтвердить исправленные поля черновика',obj({'fields':{'type':'object'},'profile_index':{'type':'integer','minimum':0}},['fields']),obj({'document':ref('Document')}),description='Для PDF с несколькими резюме profile_index обязателен: правки сохраняются отдельно в profiles[index].reviewed_fields. Сохранение черновика не публикует кандидата и не присваивает грейд. Перенос в профиль/вакансию использует отдельный доменный endpoint.')
route('post','/documents/{id}/retry','Повторить failed-задание',response=obj({'document':ref('Document')}))
route('post','/documents/export-profile','Создать PDF своего профиля через очередь',response=obj({'document':ref('Document')}))
route('get','/documents/{id}/file','Оригинал документа или готовый PDF-профиль',description='Только владелец. Ответ private, no-store. Контакты в PDF предназначены для сознательной передачи владельцем.')
paths['/documents/{id}/file']['get']['responses']['200']={'description':'Файл','content':{x:{'schema':{'type':'string','format':'binary'}} for x in ['application/pdf','image/png','image/jpeg']}}
route('get','/validation','Результаты аудита, benchmark и нагрузки')
route('get','/openapi.json','Эта спецификация OpenAPI',public=True)
route('get','/health/live','Проверка процесса без зависимости от БД',response=obj({'status':S}),public=True)
route('get','/integrations/talantix','Состояние подключения Talantix ATS',response=obj({'connection':{'type':'object'}}),description='Только employer. Токены никогда не возвращаются.')
route('put','/integrations/talantix','Проверить и подключить Talantix ATS','TalantixConnect',obj({'connection':{'type':'object'}}),description='Только employer. Access token сначала проходит GET /auth_check; секреты хранятся зашифрованными.')
route('delete','/integrations/talantix','Отключить Talantix ATS',response=obj({'connection':{'type':'object'}}),description='Только employer. Удаляет зашифрованные токены и отменяет ожидающие передачи.')
route('get','/integrations/talantix/catalogue','Загрузить источники и вакансии Talantix',response=obj({'sources':{'type':'array','items':{'type':'object'}},'vacancies':{'type':'array','items':{'type':'object'}},'mappings':{'type':'array','items':{'type':'object'}}}),description='Только employer. Read-only запрос к Talantix; применяет refresh token при необходимости.')
route('put','/integrations/talantix/source','Выбрать источник кандидатов Talantix','TalantixSource',obj({'connection':{'type':'object'}}))
route('put','/vacancies/{id}/integrations/talantix','Связать вакансию с Talantix','TalantixVacancyMapping',obj({'mapping':{'type':'object'}}),description='Только владелец вакансии. Нужны активное подключение и выбранный источник.')
schemas['DialogueEvidence']=obj({'criterion':I,'label':S,'status':enum('missing','partial','supported','contradicted'),'quote':S,'facts':obj({'a':S,'b':S}),'reason':S,'source_kind':enum('candidate_statement')})
schemas['Dialogue']=obj({'id':S,'mode':enum('profile','vacancy'),'vacancy_id':{'type':['string','null']},'specialization':S,'grade':S,'messages':{'type':'array','items':obj({'role':enum('user','assistant'),'content':S,'question_number':I},['role','content'])},'evidence':array('DialogueEvidence'),'result':{'type':['object','null'],'properties':{'decision':enum('supported','not_supported','insufficient_evidence'),'score':I,'message':S,'evidence_basis':S,'grade_changed':B}},'question_count':{'type':'integer','minimum':0,'maximum':3},'max_questions':{'const':3},'status':enum('active','completed','expired'),'revision':I,'created_at':S,'method':S,'model':S,'redirect':S},['id','mode','messages','evidence','question_count','status','revision'])
schemas['ResumeInput']=obj({'target_position':S,'specialization':S,'declared_grade':enum('junior','middle','senior'),'experience_years':{'type':'number','minimum':0},'skills':A,'about':S,'expected_salary':I,'work_format':S,'visibility':enum('private','employer_searchable')})
schemas['QualificationSubmit']=obj({'question_id':S,'revision':I,'answers':{'type':'array','minItems':1,'maxItems':1,'items':{'type':'array','items':I,'minItems':1,'maxItems':1}}})
schemas['ConversationMessageInput']=obj({'body':{'type':'string','minLength':1,'maxLength':4000}})
schemas['Conversation']=obj({'id':S,'candidate_id':S,'company_id':S,'vacancy_id':{'type':['string','null']},'resume_id':{'type':['string','null']},'origin':enum('invitation','application'),'vacancy_title':S,'resume_title':S,'other_name':S,'other_kind':enum('candidate','company'),'contact_revoked':B,'unread_count':I,'last_message_at':{'type':['string','null'],'format':'date-time'}})
schemas['ConversationMessage']=obj({'id':S,'conversation_id':S,'sender_user_id':S,'body':S,'created_at':{'type':'string','format':'date-time'},'read_at':{'type':['string','null'],'format':'date-time'}})
route('get','/resumes','До трёх целевых резюме кандидата',response=obj({'max_resumes':I,'items':{'type':'array','items':{'type':'object'}}}))
route('post','/resumes','Создать целевое резюме и поставить генерацию теста в очередь','ResumeInput',obj({'resume':{'type':'object'}}))
route('put','/resumes/{id}','Изменить целевое резюме и обновить неиспользованный тест','ResumeInput',obj({'resume':{'type':'object'}}))
route('delete','/resumes/{id}','Скрыть целевое резюме',response=obj({'archived':B}))
route('get','/resumes/{id}/test','Статус и вопросы теста без ключей',response={'type':'object'})
route('post','/resumes/{id}/test/start','Начать единственную попытку',response={'type':'object'})
route('post','/resumes/{id}/test/submit','Ответить на одно задание; CAS, серверное время, адаптивный следующий вопрос','QualificationSubmit',response={'type':'object'})
route('get','/fsp/participations','Сведения кандидата об участии в мероприятиях ФСП',response=obj({'items':{'type':'array','items':{'type':'object'}}}))
route('post','/fsp/participations','Заявить участие; статус становится declared до сверки',obj({'event_name':S,'discipline':S,'event_date':{'type':['string','null'],'format':'date'},'result':S,'source_url':S}),response={'type':'object'})
route('get','/vacancies/recommended','Вакансии, ранжированные для конкретного резюме',response=obj({'items':{'type':'array','items':{'type':'object'}}}),queries={'resume_id':S,'limit':I})
route('get','/conversations','Private one-to-one conversations',response=obj({'items':array('Conversation')}),description='Created only by an invitation or application. List is scoped to the candidate--company relationship; contact fields are not returned.')
route('get','/conversations/{id}','Private conversation history',response=obj({'conversation':ref('Conversation'),'messages':array('ConversationMessage')}),queries={'before':S},description='History and read states are available only to the candidate and company bound to the conversation.')
route('post','/conversations/{id}/messages','Send a private conversation message','ConversationMessageInput',obj({'message':ref('ConversationMessage')}),description='Server checks the participant on every send; 1--4000 characters and 80 messages per account per 15 minutes.')
route('post','/conversations/{id}/read','Mark incoming messages as read',response=obj({'marked':I}),description='Changes only incoming messages for the current participant in an authorised conversation.')
schemas['Dialogue']['properties'].update({'phase':enum('project','cases','finished'),'case_index':{'type':'integer','minimum':0,'maximum':3},'project_result':{'type':['object','null']},'cases':{'type':'array','maxItems':3,'items':obj({'number':I,'axis':S,'prompt':{'type':'string','maxLength':800},'reviewed':B,'evaluation':{'type':['object','null']}})}})
for path,method in [('/dialogues','post'),('/dialogues/{id}','get'),('/dialogues/{id}/messages','post'),('/dialogues/{id}/cases','post')]:
    paths[path][method]['responses']['200']['content']['application/json']['schema']=ref('Dialogue')
route('post','/auth/logout-all','Завершить все сессии текущего аккаунта')
route('post','/auth/reset-request','Запросить письмо сброса пароля',obj({'email':S}),public=True,description='Ответ не раскрывает существование адреса. В локальном demo письма доступны в песочнице.')
route('post','/auth/reset-confirm','Установить новый пароль по одноразовому токену',obj({'token':S,'password':{'type':'string','minLength':10,'maxLength':256}}),public=True,description='Погашает токен и отзывает прежние сессии.')
route('get','/account/export','Экспорт собственных данных, документов, диалогов и событий')
route('delete','/account','Удалить свой аккаунт с подтверждением паролем',obj({'password':S}),description='Удаление связанных личных данных; файлы ставятся в очередь удаления. Демонстрационные служебные аккаунты защищены от удаления.')
route('get','/account/contact-access','Компании с доступом к контактам кандидата')
route('post','/account/contact-access','Отозвать или восстановить ранее предоставленный доступ',obj({'company_id':S,'restore':B},['company_id']),description='Только кандидат; нельзя создать новый доступ компании без существовавшего согласия.')
for path in ['/assessments','/assessments/{id}/submit']:
    paths[path]['post']['responses']={'410':{'description':'Сценарий удалён; используйте /dialogues','content':{'application/json':{'schema':ref('Error')}}},'401':paths[path]['post']['responses']['401'],'403':paths[path]['post']['responses']['403']}
schemas['Task']['allOf'][1]['properties']['status']=enum('pending','accepted','declined','reviewing','submitted','reviewed')
route('get','/career-consultant','Личная история HR-консультации; только кандидат')
route('post','/career-consultant','Совет по старту карьеры и переходу в смежную роль',obj({'text':{'type':'string','minLength':3,'maxLength':2000}}),description='Только кандидат. Контекст — его профессиональные резюме и история. Контакты редактируются, грейд и отклики не меняются.')
route('get','/notifications','Уведомления текущего пользователя')
route('post','/notifications/{id}/read','Отметить своё уведомление прочитанным')
route('post','/vacancies/generate','Черновик вакансии по короткому запросу',obj({'text':{'type':'string','minLength':10,'maxLength':2000}}),description='Только подтверждённый работодатель. Qwen2.5:3b; создание вакансии требует отдельного сохранения проверенного черновика.')
route('post','/vacancies/bulk','Атомарная загрузка 1–50 вакансий',obj({'items':{'type':'array','minItems':1,'maxItems':50,'items':ref('VacancyInput')}}),description='Не более 50 активных вакансий компании, включая черновики. Проверка всего пакета до вставки, лимит под блокировкой компании; тело до 1 МБ.')
route('get','/vacancies/{id}/market','Рыночная аналитика собственной вакансии',description='Только владелец. Медиана/квартили/гистограмма ожиданий при выборке от 5; кандидатские идентификаторы и контакты не возвращаются. Вознаграждение никогда не рекомендуется снижать.')
route('get','/vacancies/{id}/task-recipients','Заинтересованные кандидаты по своей вакансии')
route('post','/tasks/generate','Подготовить и проверить эталон задания под вакансию',obj({'vacancy_id':S,'instruction':{'type':'string','maxLength':1500}},['vacancy_id']),description='Qwen3:8b; эталон выполняется в Docker на открытых и скрытых тестах до сохранения черновика. Эталон и скрытые случаи не возвращаются.')
route('post','/tasks/dispatch','Направить проверенный черновик заинтересованным кандидатам',obj({'draft_id':S,'candidate_ids':{'type':'array','minItems':1,'maxItems':50,'items':S}}))
route('put','/tasks/{id}/decision','Принять или отклонить своё тестовое',obj({'status':enum('accepted','declined')}))
route('post','/tasks/{id}/run','Запустить открытые автотесты в изолированной песочнице',obj({'code':{'type':'string','maxLength':20000}}),description='Python 3.12, без сети/секретов/монтирований, non-root, CPU/RAM/PID/output/time limits. Только принявший задание кандидат.')
route('post','/tasks/{id}/submit','Открытые/скрытые автотесты, GPT-OSS ревью, доставка работодателю',obj({'code':{'type':'string','maxLength':20000}}),description='Статус accepted → reviewing → reviewed. При сбое возвращается accepted. Балл: 70% автотесты + 30% ревью, максимум 69 при неполном прохождении тестов. Категория не меняется.')
route('get','/forecasts/vacancy/{id}','Прогноз закрытия своей вакансии и контрфактуальная рекомендация')
route('get','/forecasts/job-search/{id}','Прогноз поиска работы по собственному резюме')
route('post','/intelligence/horizon','Поставить собственный сценарий Horizon в долговечную очередь',obj({'entity_id':S,'changes':{'type':'object'},'idempotency_key':{'type':'string','maxLength':100}},['entity_id']),description='Кандидат — своё резюме, компания — свою вакансию. Ответ job_id; status/result получают через jobs/{id}. Target capacity не является измерением нагрузки.')
route('get','/intelligence/jobs','Последние собственные расчёты')
route('get','/intelligence/jobs/{id}','Статус и результат собственного расчёта')
route('get','/intelligence/preferences','Приватные добровольные рабочие предпочтения кандидата')
route('put','/intelligence/preferences','Сохранить добровольные предпочтения',obj({'target_role':S,'weekly_hours':{'type':'number','minimum':2,'maximum':20},'collaboration':enum('','team','independent'),'pace':enum('','stable','dynamic'),'growth':enum('','expert','leadership','explore')},[]),description='Психологический тип не выводится; предпочтения не влияют на ранжирование и не доступны работодателю.')
route('get','/intelligence/graph','Собственный граф профессиональных доказательств')
route('get','/intelligence/graph/candidate/{id}','Публичный граф согласованного кандидата',description='Только проверенный работодатель; private/hidden/disputed артефакты исключаются. Без контактов и карьерных предпочтений.')
route('put','/intelligence/evidence/{id}','Управление публикацией и спором собственного артефакта',obj({'hidden':B,'disputed':B,'reason':{'type':'string','maxLength':1000}},[]))
route('post','/intelligence/career-route','Создать приватный маршрут 14/30/90 дней',description='Кандидат. Ответ job_id; учитываются граф навыков и добровольные предпочтения.')
route('post','/intelligence/strategy','Стратегия портфеля до 50 своих активных вакансий',obj({'extra_budget':{'type':'number','minimum':0,'maximum':100000000}},[]))
route('post','/intelligence/match','Объяснение совместимости обеих сторон',obj({'resume_id':S,'vacancy_id':S}),description='Оба объекта должны быть доступны пользователю. Контакты не раскрываются.')
route('get','/intelligence/decisions','Приватный версионированный журнал решений')
route('post','/intelligence/decisions/{id}/dispute','Оспорить своё решение',obj({'reason':{'type':'string','minLength':10,'maxLength':1000}}))
route('get','/intelligence/quality','Собственные показатели споров/фактических исходов',description='Без исходов MAE/RMSE остаются null, вероятности не выдаются за эмпирически откалиброванные.')
route('post','/intelligence/outcomes','Записать фактический срок для своего прогноза',obj({'decision_id':S,'actual_days':{'type':'number','exclusiveMinimum':0,'maximum':3650}}))
route('get','/intelligence/arena','История собственной практики без скрытых контрактов')
route('post','/intelligence/arena','Создать практику и проверить эталон',obj({'kind':enum('python','sql','typescript','incident','design','review','adaptive')}))
route('post','/intelligence/arena/{id}/run','Выполнить открытые случаи в изолированном Docker',obj({'code':{'type':'string','maxLength':20000}}))
route('post','/intelligence/arena/{id}/submit','Очередь автопроверки и реального ревью',obj({'code':{'type':'string','minLength':10,'maxLength':20000}}),description='Coding: открытые/скрытые тесты и GPT-OSS; инженерный текст: Qwen. Грейд не изменяется. Ответ job_id.')
route('post','/intelligence/arena/{id}/answer','Ответ на текущий адаптивный вопрос с CAS/revision',obj({'question_id':S,'answer':{'type':'number'},'revision':I}),description='Одинаковый вопрос/ревизия не принимаются повторно; банк/правильные ответы не публикуются.')
spec={'openapi':'3.1.0','info':{'title':'ПРУФ-ИТ API','version':'0.1.0','description':'Rust API платформы обратного найма. Ролевое разграничение и подтверждённые категории. Зарплаты — диапазоны RUB в месяц.'},'servers':[{'url':'/api'}],'paths':paths,'components':{'securitySchemes':{'sessionCookie':{'type':'apiKey','in':'cookie','name':'fsp_session'},'bearerSession':{'type':'http','scheme':'bearer','description':'Тот же opaque session token, не JWT.'}},'schemas':schemas}}
route('get','/auth/demo-context','Собственная связанная демо-пара',description='Возвращает только пару, которой принадлежит текущий user ID; для обычного аккаунта workspace=null.')
route('get','/intelligence/assessment/catalog','Размеры и версии профессионального банка')
route('get','/intelligence/assessment/attempts','Собственные попытки; ключи и банк скрыты')
route('post','/intelligence/assessment/attempts','Начать или продолжить персональную оценку',obj({'specialization':S,'mode':enum('express','full'),'extra_time':B},['specialization','mode']))
route('post','/intelligence/assessment/attempts/{id}/answer','Серверный таймер, ownership и CAS ответа',obj({'question_id':S,'answer':I,'revision':I}))
route('post','/intelligence/assessment/attempts/{id}/signals','Минимальная телеметрия без содержимого буфера/экрана',obj({'kind':enum('copy','paste','visibility_hidden','print_screen','fullscreen_exit'),'count':I},['kind']))
route('post','/intelligence/assessment/attempts/{id}/abandon','Закрыть собственную практику')
route('get','/intelligence/assessment/bank','Агрегированная экспозиция, решаемость и drift; экспертный доступ')
route('get','/intelligence/assessment/drafts','Экспертные черновики')
route('post','/intelligence/assessment/drafts','Создать проверяемый черновик',obj({'specialization':S,'content':{'type':'object'}}))
route('post','/intelligence/assessment/drafts/generate','Подготовить черновик в очереди',obj({'specialization':S,'topic':S}))
route('post','/intelligence/assessment/drafts/{id}/review','Проверка другим экспертом; пилот или отказ',obj({'decision':enum('pilot','rejected'),'note':S,'content':{'type':'object'}},['decision','note']))
route('post','/intelligence/assessment/drafts/{id}/calibrate','Оценка параметров по пилотным ответам')
route('post','/intelligence/assessment/drafts/{id}/activate','Активация проверяющим после калибровки')
route('get','/intelligence/assessment/oidc','Состояние привязки ФСП ID')
route('post','/intelligence/assessment/oidc','Начать OIDC code + PKCE; авторизованный владелец')
route('get','/intelligence/assessment/oidc/callback','Одноразовый state + браузерная привязка, nonce, RS256, issuer и audience',public=True,queries={'state':S,'code':S},description='Нужна отдельная HttpOnly SameSite=Lax cookie proofit_oidc (__Host-proofit_oidc в HTTPS). Основная сессия остаётся Strict; привязка не выполняет вход и не подтверждает достижения. Ответ 303, неверный state/browser — 400.')
paths['/intelligence/assessment/oidc/callback']['get']['responses']['303']={'description':'Вернуться в собственный кабинет; browser-binding cookie удаляется.'}
route('post','/intelligence/assessment/integrity/code','Индикатор сходства собственной завершённой практики',obj({'artifact_id':S}))
route('post','/intelligence/assessment/need-preview','Быстрый разбор потребности с уточнениями',obj({'text':S}))
for method,path,summary in [
 ('get','/intelligence/evidence-lab/workspace','Доказательства, следующие проверки и маршруты переноса'),
 ('get','/intelligence/evidence-lab/company-twin','Свой версионированный двойник команды'),
 ('put','/intelligence/evidence-lab/company-twin','Сохранить явно заданные рабочие параметры'),
 ('post','/intelligence/evidence-lab/allocation','Оптимальное распределение с жёсткими ограничениями'),
 ('post','/intelligence/evidence-lab/diagnosis/{id}','Диагностика ограничений своей вакансии'),
 ('get','/intelligence/evidence-lab/compatibility/{resume}/{vacancy}','Двусторонняя совместимость по доступным объектам'),
 ('get','/intelligence/evidence-lab/passport','Собственные паспорта без секретов'),
 ('post','/intelligence/evidence-lab/passport','Выпустить подписанный паспорт действующих доказательств'),
 ('get','/intelligence/evidence-lab/passport/public-key','Публичный ключ Ed25519'),
 ('post','/intelligence/evidence-lab/passport/verify','Проверить подпись, срок и отзыв'),
 ('post','/intelligence/evidence-lab/passport/{id}/revoke','Отозвать свой паспорт'),
 ('post','/intelligence/evidence-lab/authorship/{id}','Контекстная защита своего кода; самостоятельный и assisted режимы'),
 ('get','/intelligence/evidence-lab/reviews','Собственные сигналы; экспертная очередь по разрешению'),
 ('post','/intelligence/evidence-lab/reviews/{id}/challenge','Оспорить собственный сигнал'),
 ('post','/intelligence/evidence-lab/reviews/{id}/resolve','Независимое экспертное решение'),
 ('get','/intelligence/evidence-lab/followups','Контрольные точки 30/60/90 дней'),
 ('post','/intelligence/evidence-lab/followups','Явно запланировать начало сотрудничества'),
 ('put','/intelligence/evidence-lab/followups/{id}','Подтвердить фактический результат своей стороны'),
 ('get','/intelligence/evidence-lab/weekly-campaigns','Свои кампании адресных заданий'),
 ('post','/intelligence/evidence-lab/weekly-campaigns','Включить или остановить недельную кампанию'),
 ('get','/intelligence/providers/status','Состояние подготовленных партнёрских адаптеров'),
 ('put','/intelligence/providers/dreamjob','Привязать официальную страницу компании'),
 ('get','/intelligence/providers/dreamjob/{id}','Источник отзывов и подтверждённый снимок при наличии'),
 ('post','/intelligence/providers/sync/{provider}','Синхронизировать доступные собственные партнёрские сведения')]:
 body=None
 if method=='put' and path.endswith('/company-twin'):
  body=obj({'collaboration':enum('','team','independent'),'pace':enum('','stable','dynamic'),'growth':enum('','expert','leadership','explore'),'response_days':{'type':'number','minimum':0.25,'maximum':14},'interview_stages':{'type':'number','minimum':1,'maximum':7}},[]);body['additionalProperties']=False
 elif path.endswith('/passport/verify'):body=obj({'token':{'type':'string','maxLength':20000}})
 elif '/authorship/'in path:body=obj({'ai_assisted':B},[])
 elif path.endswith('/challenge'):body=obj({'reason':S})
 elif path.endswith('/resolve'):body=obj({'status':enum('confirmed','dismissed'),'reason':S})
 elif method=='post' and path.endswith('/followups'):body=obj({'invitation_id':S,'started_at':{'type':'string','format':'date-time'}})
 elif method=='put' and '/followups/'in path:body=obj({'result':{'type':'object'}})
 elif method=='post' and path.endswith('/weekly-campaigns'):body=obj({'vacancy_id':S,'enabled':B})
 elif method=='put' and path.endswith('/providers/dreamjob'):body=obj({'employer_id':{'type':'string','pattern':'^[0-9]{1,20}$'}})
 public=path.endswith('/passport/public-key')or path.endswith('/passport/verify')
 route(method,path,summary,body=body,public=public,description='Роль и владение проверяются сервером; публичная проверка паспорта не раскрывает прямые ПДн. Отсутствующие сведения не подменяются подтверждением.')
lab='/intelligence/research-lab'
route('post',lab+'/bilateral/{id}/freeze','Неизменяемый прогноз до первого намерения каждой стороны',obj({'candidate_id':S,'stage':enum('vacancy','offer')}),description='Только владелец вакансии и существующий участник процесса. Прогноз вычисляется сервером, не принимается от клиента. Advisory-lock сериализует фиксацию и запись намерений; повтор или уже выраженное намерение — 409. Синтетический контекст маркируется и исключается из реальной валидации.')
for suffix,summary in [('forecast','Проспективные метрики собственных прогнозов'),('export','Собственные снимки и первые завершённые парные исходы')]:
 route('get',lab+'/validation/'+suffix,summary,queries={'vacancy_id':S,'stage':enum('vacancy','offer')},description='Только авторизованный работодатель-владелец. Первый завершённый парный исход сохраняется неизменяемым; последующая смена намерения не переписывает его. Online: максимум 500 снимков; export: 5000, без тихого усечения. Brier, LogLoss, ECE и AUC разделены по стадиям; нет фиктивных метрик при отсутствии реальных наблюдений. Намерения не являются фактом трудоустройства.')
for method,path,summary,body in [
 ('get','/workspace','Собственные защиты вклада; очередь независимого эксперта по разрешению',None),
 ('post','/github/profile','Ограниченное чтение публичных репозиториев',obj({'login':S})),
 ('post','/github/repository','Публичные коммиты, PR и отдельные Repository Discussions',obj({'repository':S})),
 ('post','/github/challenge','Одноразовый proofit-claim.txt, срок 600 секунд',obj({'login':S})),
 ('post','/github/verify','Атомарно привязать публичный gist к аккаунту',obj({'gist_id':S})),
 ('post','/github/pr','Снимок публичного PR и вопросы, связанные с SHA и артефактом',obj({'url':S,'resume_id':S,'consent_public_evidence':B})),
 ('put','/github/pr/{id}/answers','Отправить собственные ответы с CAS revision',obj({'revision':I,'answers':{'type':'object','additionalProperties':S}})),
 ('post','/github/pr/{id}/review','Независимая экспертная ролевая оценка; не для обычной роли работодателя',obj({'revision':I,'scores':{'type':'object','additionalProperties':{'type':'integer','minimum':0,'maximum':4}},'skills':A,'reason':S})),
 ('get','/matrix/{specialization}','Практическая матрица профессии с атрибуцией O*NET',None),
 ('post','/forms/{resume}','Стабильное распределение A/B в блоке целевой роли',None),
 ('get','/forms/report/{specialization}','Диагностика эквивалентности форм; одобренный эксперт',None),
 ('get','/bilateral/{id}','Отдельные интервальные оценки парных намерений vacancy/offer',None),
 ('post','/bilateral/{id}/decision','Намерение собственной стороны; не заменяет отклик или принятие оффера',obj({'stage':enum('vacancy','offer'),'accepts':B,'candidate_id':S},['stage','accepts'])),
 ('get','/bilateral/{id}/participants','Участники процесса только своей вакансии',None),
 ('get','/reliability/{id}','Раздельные наблюдения надёжности; неизвестность не негатив',None),
 ('get','/market/{id}','Радар собственной вакансии: роль, грейд, отрасль, synthetic scope',None),
]:route(method,lab+path,summary,body=body,response={'type':'object'},description='Штатная авторизация и серверная проверка ownership. Общий CAT не является полной аттестацией профессии; scope знаний и независимой практики разделены.')
(ROOT/'data/contracts').mkdir(parents=True,exist_ok=True)
(ROOT/'data/contracts/openapi.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
print('OpenAPI endpoints:',sum(len(x) for x in paths.values()))
