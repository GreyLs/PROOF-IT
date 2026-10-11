"""Offline preparation of product-copy assets; not an evaluation or runtime service."""
import argparse,hashlib,json,re,time
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];FOLDER=ROOT/'web/src/locales'
DECISION_COPY=json.loads((ROOT/'scripts/decision_ui_translations.json').read_text(encoding='utf-8'))if (ROOT/'scripts/decision_ui_translations.json').exists()else{}
FINALIZATION_COPY=json.loads((ROOT/'scripts/finalization_ui_translations.json').read_text(encoding='utf-8'))if (ROOT/'scripts/finalization_ui_translations.json').exists()else{}
AGENT_REVIEWED={}
review_file=FOLDER/'agent-reviews.json'
if review_file.exists():
 review_metadata=json.loads(review_file.read_text(encoding='utf-8'))
 current_source=json.loads((FOLDER/'ru.json').read_text(encoding='utf-8'))
 source_digest=hashlib.sha256(json.dumps(current_source,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
 for reviewed_language,review in review_metadata.get('languages',{}).items():
  candidate_path=FOLDER/(reviewed_language+'.json')
  if candidate_path.exists():
   candidate_copy=json.loads(candidate_path.read_text(encoding='utf-8'))
   catalog_digest=hashlib.sha256(json.dumps(candidate_copy,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
   if review.get('source_sha256')==source_digest and review.get('catalog_sha256')==catalog_digest and review.get('scope')=='full_static_catalog' and review.get('independent_human_review') is False:
    AGENT_REVIEWED[reviewed_language]=candidate_copy
GLOSSARY={
 'en':'English: грейд=grade, отклик=application, резюме=resume, evidence=proof source, цифровой двойник=digital twin, стандартная ошибка=standard error, подтвержденный=verified, зарплатная вилка=salary range (never fork), срок=time/duration, стр.=page, решение проверяющего=reviewer decision, направление=field, предпосылка=assumption.',
 'kk':'Kazakh Cyrillic: кандидат=үміткер, работодатель=жұмыс беруші, резюме=түйіндеме, вакансия=бос орын, отклик=өтінім, навык=дағды, доказательство=дәлел, цифровой двойник=цифрлық егіз, стандартная ошибка=стандартты қате, top-5=үздік 5, подтвержденный=расталған, войти=кіру, выйти=шығу, грейд=деңгей.',
 'uz':'Uzbek Latin: кандидат=nomzod, работодатель=ish beruvchi, резюме=rezyume, вакансия=vakansiya, отклик=ariza, навык=ko‘nikma, доказательство=dalil, цифровой двойник=raqamli egizak, стандартная ошибка=standart xatolik, войти=kirish, выйти=chiqish, грейд=daraja.',
 'az':'Azerbaijani Latin: кандидат=namizəd, работодатель=işəgötürən, резюме=CV, вакансия=vakansiya, отклик=müraciət, навык=bacarıq, доказательство=sübut, цифровой двойник=rəqəmsal əkiz, стандартная ошибка=standart xəta, войти=daxil ol, выйти=çıx, грейд=səviyyə.',
 'be':'Belarusian Cyrillic: кандидат=кандыдат, работодатель=працадаўца, резюме=рэзюмэ, вакансия=вакансія, отклик=адгук, доказательство=доказ, цифровой двойник=лічбавы двайнік, стандартная ошибка=стандартная памылка, грейд=узровень, войти=увайсці, выйти=выйсці. Correct Belarusian spelling: і/ў/дз/ц, not Russian и/щ/ъ.'}
NAMES={'en':'English','kk':'Kazakh','uz':'Uzbek','az':'Azerbaijani','be':'Belarusian'}
PROTECTED_TERMS=('API','ATS','JSON','PDF','PNG','JPEG','GitHub','OAuth','MOEX','ISS',
 'Talantix','DreamJob','ProofLab','CodeArena','Ed25519','Python','FastAPI','PostgreSQL',
 'CAT','GraphSAGE','GAT','SFIA','O*NET','e-CF','Recall','NDCG',
 'СТД-СФР','СТД-ПФР','СТД-Р')
CYRILLIC_IDENTIFIERS=('ФСП','ВК','СТД-СФР','СТД-ПФР','СТД-Р')
WRITTEN_NUMBERS={
 'en':{3:r'three',7:r'seven',8:r'eight'},
 'kk':{3:r'үш(?:ке|тен|тің|ті)?',7:r'жеті(?:ге|ден|нің|ні)?',8:r'сегіз(?:ге|ден|дің|ді)?'},
 'uz':{3:r'uch(?:ta|tagacha)?',7:r'yetti(?:ta|tagacha)?',8:r'sakkiz(?:ta|tagacha)?'},
 'az':{3:r'üç(?:ədək|ə|dən|ün)?',7:r'yeddi(?:yədək|yə|dən|nin)?',8:r'səkkiz(?:ədək|ə|dən|in)?'},
 'be':{3:r'тры|трох|трыма|тром',7:r'сем|сямі',8:r'восем|васьмі'},
}

# Agent-reviewed core UI wording. Never replace these with generated drafts.
# Columns: Russian key | English | Kazakh | Uzbek | Azerbaijani | Belarusian.
CORE_COPY='''
Добавьте резюме или выполните задачу в ProofLab.|Add a resume or complete a task in ProofLab.|Түйіндеме қосыңыз немесе ProofLab-та тапсырма орындаңыз.|Rezyume qo‘shing yoki ProofLab’da topshiriq bajaring.|CV əlavə edin və ya ProofLab-da tapşırıq yerinə yetirin.|Дадайце рэзюмэ або выканайце задачу ў ProofLab.
Можно добровольно загрузить выписку СТД-СФР, СТД-ПФР или СТД-Р. Отсутствие файла не снижает видимость.|You may voluntarily upload a СТД-СФР, СТД-ПФР or СТД-Р employment record extract. Not uploading a file does not reduce visibility.|СТД-СФР, СТД-ПФР немесе СТД-Р еңбек қызметі туралы үзіндіні ерікті түрде жүктеуге болады. Файлдың болмауы көрінуді төмендетпейді.|СТД-СФР, СТД-ПФР yoki СТД-Р mehnat faoliyati ko‘chirmasini ixtiyoriy yuklash mumkin. Fayl yo‘qligi ko‘rinishni kamaytirmaydi.|СТД-СФР, СТД-ПФР və ya СТД-Р əmək fəaliyyəti çıxarışını könüllü yükləyə bilərsiniz. Faylın olmaması görünməni azaltmır.|Можна добраахвотна загрузіць выпіску СТД-СФР, СТД-ПФР або СТД-Р. Адсутнасць файла не зніжае бачнасць.
Отсутствие данных не является негативной оценкой. Контрольные точки измеряют участие в проверке результата, а не удовлетворённость работой.|Missing data is not a negative assessment. Checkpoints measure participation in verifying the outcome, not job satisfaction.|Деректердің болмауы теріс бағалау болып саналмайды. Бақылау нүктелері жұмысқа қанағаттануды емес, нәтижені тексеруге қатысуды өлшейді.|Ma’lumot yo‘qligi salbiy baho emas. Nazorat nuqtalari ishdan qoniqishni emas, natijani tekshirishdagi ishtirokni o‘lchaydi.|Məlumatın olmaması mənfi qiymətləndirmə deyil. Nəzarət nöqtələri işdən məmnunluğu deyil, nəticənin yoxlanmasında iştirakı ölçür.|Адсутнасць даных не з’яўляецца негатыўнай ацэнкай. Кантрольныя пункты вымяраюць удзел у праверцы выніку, а не задаволенасць працай.
GitHub · проверяемый личный вклад|GitHub · verifiable individual contribution|GitHub · тексеруге болатын жеке үлес|GitHub · tekshiriladigan shaxsiy hissa|GitHub · yoxlanıla bilən şəxsi töhfə|GitHub · асабісты ўнёсак, які можна праверыць
Вакансии связаны. Согласованные отклики будут передаваться в Talantix.|Jobs linked. Applications with consent will be transferred to Talantix.|Бос орындар байланыстырылды. Келісім берілген өтінімдер Talantix-ке жіберіледі.|Vakansiyalar bog‘landi. Rozilik berilgan arizalar Talantix’ga uzatiladi.|Vakansiyalar əlaqələndirilib. Razılıq verilmiş müraciətlər Talantix-ə ötürüləcək.|Вакансіі звязаныя. Адгукі, на перадачу якіх дадзена згода, будуць перадавацца ў Talantix.
Ваши контакты не раскрыты.|Your contact details have not been disclosed.|Байланыс деректеріңіз ашылған жоқ.|Kontakt ma’lumotlaringiz oshkor qilinmagan.|Əlaqə məlumatlarınız açıqlanmayıb.|Вашы кантакты не раскрытыя.
Для подбора также нужен действующий подтверждённый грейд. Контакты останутся закрытыми.|Matching also requires a valid verified grade. Your contact details will remain hidden.|Іріктеу үшін жарамды расталған деңгей де қажет. Байланыс деректері жабық қалады.|Saralash uchun amaldagi tasdiqlangan daraja ham kerak. Kontakt ma’lumotlari yopiq qoladi.|Uyğunlaşdırma üçün qüvvədə olan təsdiqlənmiş səviyyə də lazımdır. Əlaqə məlumatları bağlı qalacaq.|Для падбору таксама патрэбны дзейны пацверджаны ўзровень. Кантакты застануцца закрытымі.
Закрыты до согласия|Hidden until consent|Келісім берілгенше жабық|Rozilik berilguncha yopiq|Razılıq verilənədək bağlıdır|Закрытыя да згоды
Кандидат закрыл прямые контакты. Используйте этот закрытый чат; контактные данные недоступны.|The candidate has hidden their direct contact details. Use this private chat; contact details are unavailable.|Үміткер тікелей байланыс деректерін жапты. Осы жабық чатты пайдаланыңыз; байланыс деректері қолжетімсіз.|Nomzod bevosita kontakt ma’lumotlarini yopdi. Ushbu yopiq chatdan foydalaning; kontakt ma’lumotlari mavjud emas.|Namizəd birbaşa əlaqə məlumatlarını bağlayıb. Bu qapalı çatdan istifadə edin; əlaqə məlumatları əlçatan deyil.|Кандыдат закрыў прамыя кантакты. Выкарыстоўвайце гэты закрыты чат; кантактныя даныя недаступныя.
Консультация учитывает ваши целевые резюме. Для беседы достаточно профессионального опыта; контакты и ФИО не нужны.|The consultation considers your targeted resumes. Professional experience is enough for the conversation; contact details and your full name are not needed.|Кеңес мақсатты түйіндемелеріңізді ескереді. Әңгімеге кәсіби тәжірибе жеткілікті; байланыс деректері мен толық аты-жөніңіз қажет емес.|Maslahat maqsadli rezyumelaringizni hisobga oladi. Suhbat uchun kasbiy tajriba yetarli; kontakt ma’lumotlari va to‘liq ism-sharif kerak emas.|Məsləhət hədəf CV-lərinizi nəzərə alır. Söhbət üçün peşə təcrübəsi kifayətdir; əlaqə məlumatları və tam adınız lazım deyil.|Кансультацыя ўлічвае вашы мэтавыя рэзюмэ. Для размовы дастаткова прафесійнага досведу; кантакты і поўнае імя не патрэбныя.
Контактный email|Contact email|Байланыс электрондық поштасы|Aloqa uchun email|Əlaqə e-poçtu|Кантактны email
Контакты демонстрационные|Demo contact details|Демонстрациялық байланыс деректері|Namoyish uchun kontakt ma’lumotlari|Nümayiş üçün əlaqə məlumatları|Дэманстрацыйныя кантакты
Контакты ждут согласия|Contact access awaits consent|Байланыс деректеріне қолжетімділік келісімді күтуде|Kontaktlarga kirish uchun rozilik kutilmoqda|Əlaqə məlumatlarına giriş üçün razılıq gözlənilir|Доступ да кантактаў чакае згоды
Контакты кандидата|Candidate contact details|Үміткердің байланыс деректері|Nomzodning kontakt ma’lumotlari|Namizədin əlaqə məlumatları|Кантакты кандыдата
Контакты открыты вам|Contact details shared with you|Байланыс деректері сізге ашылды|Kontakt ma’lumotlari sizga ochiq|Əlaqə məlumatları sizə açıqdır|Кантакты адкрытыя вам
ЛИЧНЫЙ КАНАЛ СВЯЗИ|PRIVATE COMMUNICATION CHANNEL|ЖЕКЕ БАЙЛАНЫС АРНАСЫ|SHAXSIY ALOQA KANALI|ŞƏXSİ ƏLAQƏ KANALI|АСАБІСТЫ КАНАЛ СУВЯЗІ
ЛИЧНЫЙ ПРОФИЛЬ|PERSONAL PROFILE|ЖЕКЕ ПРОФИЛЬ|SHAXSIY PROFIL|ŞƏXSİ PROFİL|АСАБІСТЫ ПРОФІЛЬ
Личные данные|Personal data|Жеке деректер|Shaxsiy ma’lumotlar|Şəxsi məlumatlar|Асабістыя даныя
Надёжность шкалы на реальных специалистах и фактическая ёмкость инфраструктуры требуют отдельной приёмки. Контактные данные не входят в публичные отчёты.|Scale reliability on real professionals and actual infrastructure capacity require separate acceptance checks. Contact details are excluded from public reports.|Нақты мамандар бойынша шкаланың сенімділігі мен инфрақұрылымның нақты сыйымдылығы бөлек қабылдау тексеруін қажет етеді. Байланыс деректері жария есептерге кірмейді.|Shkalaning haqiqiy mutaxassislardagi ishonchliligi va infratuzilmaning amaldagi sig‘imi alohida qabul tekshiruvini talab qiladi. Kontakt ma’lumotlari ochiq hisobotlarga kiritilmaydi.|Şkalanın real mütəxəssislər üzrə etibarlılığı və infrastrukturun faktiki tutumu ayrıca qəbul yoxlaması tələb edir. Əlaqə məlumatları ictimai hesabatlara daxil edilmir.|Надзейнасць шкалы на рэальных спецыялістах і фактычная ёмістасць інфраструктуры патрабуюць асобнай прыёмкі. Кантактныя даныя не ўваходзяць у публічныя справаздачы.
Не согласен с результатом|I disagree with the result|Нәтижемен келіспеймін|Natijaga rozi emasman|Nəticə ilə razı deyiləm|Не згодны з вынікам
Отслеживайте предложения и открывайте контакты после согласия.|Track offers and share contact details after consent.|Ұсыныстарды бақылап, келісім бергеннен кейін байланыс деректерін ашыңыз.|Takliflarni kuzating va rozilik bergandan keyin kontakt ma’lumotlarini oching.|Təklifləri izləyin və razılıq verdikdən sonra əlaqə məlumatlarını açın.|Сачыце за прапановамі і адкрывайце кантакты пасля згоды.
Принять и открыть контакты|Accept and share contact details|Қабылдау және байланыс деректерін ашу|Qabul qilish va kontakt ma’lumotlarini ochish|Qəbul et və əlaqə məlumatlarını aç|Прыняць і адкрыць кантакты
Прямые контакты закрыты. Внутренний чат остаётся приватным и доступен только этой компании.|Direct contact details are hidden. The internal chat remains private and accessible only to this company.|Тікелей байланыс деректері жабық. Ішкі чат құпия болып қалады және тек осы компанияға қолжетімді.|Bevosita kontakt ma’lumotlari yopiq. Ichki chat maxfiy bo‘lib qoladi va faqat ushbu kompaniyaga ochiq.|Birbaşa əlaqə məlumatları bağlıdır. Daxili çat məxfi qalır və yalnız bu şirkət üçün əlçatandır.|Прамыя кантакты закрытыя. Унутраны чат застаецца прыватным і даступным толькі гэтай кампаніі.
Публичный артефакт → вопросы по изменениям → независимая ролевая оценка.|Public artifact → questions about changes → independent role-specific assessment.|Жария артефакт → өзгерістер туралы сұрақтар → рөл бойынша тәуелсіз бағалау.|Ochiq artefakt → o‘zgarishlar haqidagi savollar → rol bo‘yicha mustaqil baholash.|İctimai artefakt → dəyişikliklərlə bağlı suallar → rol üzrə müstəqil qiymətləndirmə.|Публічны артэфакт → пытанні пра змены → незалежная ацэнка па ролі.
Согласие на вакансию|Consent to the job|Бос орынға келісім|Vakansiyaga rozilik|Vakansiyaya razılıq|Згода на вакансію
Согласие на обработку данных для работы сервиса|Consent to data processing for service operation|Сервис жұмысы үшін деректерді өңдеуге келісім|Xizmat ishlashi uchun ma’lumotlarni qayta ishlashga rozilik|Xidmətin fəaliyyəti üçün məlumatların emalına razılıq|Згода на апрацоўку даных для працы сэрвісу
Согласие на оффер|Consent to the offer|Ұсынысқа келісім|Ish taklifiga rozilik|İş təklifinə razılıq|Згода на прапанову
Согласие на публикацию обезличенного профессионального профиля|Consent to publication of an anonymized professional profile|Иесіздендірілген кәсіби профильді жариялауға келісім|Shaxssizlantirilgan kasbiy profilni e’lon qilishga rozilik|Şəxsiyyətsizləşdirilmiş peşə profilinin dərcinə razılıq|Згода на публікацыю абязлічанага прафесійнага профілю
Согласованные условия, подтверждённые навыки и оптимальный портфель найма.|Agreed terms, verified skills and an optimal hiring portfolio.|Келісілген шарттар, расталған дағдылар және оңтайлы жұмысқа қабылдау портфелі.|Kelishilgan shartlar, tasdiqlangan ko‘nikmalar va maqbul ishga olish portfeli.|Razılaşdırılmış şərtlər, təsdiqlənmiş bacarıqlar və optimal işə qəbul portfeli.|Узгодненыя ўмовы, пацверджаныя навыкі і аптымальны партфель найму.
Согласовано записей:|Approved records:|Келісілген жазба:|Kelishilgan yozuvlar:|Razılaşdırılmış qeydlər:|Узгоднена запісаў:
Содержание согласуется|Content is consistent|Мазмұны сәйкес келеді|Mazmun mos keladi|Məzmun uyğundur|Змест узгадняецца
Ссылка действует 30 минут. После смены пароля прежние сессии будут закрыты.|The link is valid for 30 minutes. Changing your password will end previous sessions.|Сілтеме 30 минут жарамды. Құпиясөз өзгергеннен кейін алдыңғы сессиялар аяқталады.|Havola 30 daqiqa amal qiladi. Parol almashtirilgandan keyin avvalgi seanslar tugaydi.|Keçid 30 dəqiqə qüvvədədir. Şifrə dəyişdirildikdən sonra əvvəlki sessiyalar bağlanacaq.|Спасылка дзейнічае 30 хвілін. Пасля змены пароля папярэднія сесіі будуць закрытыя.
· Оспаривается|· Disputed|· Даулы|· Nizolashilmoqda|· Mübahisələndirilir|· Аспрэчваецца
· ваш выбор|· your choice|· сіздің таңдауыңыз|· sizning tanlovingiz|· seçiminiz|· ваш выбар
· доказательность|· evidence strength|· дәлел деңгейі|· dalillar kuchi|· sübut gücü|· доказнасць
· ожидание выше бюджета|· expectations exceed budget|· күтілетін ақы бюджеттен жоғары|· kutilayotgan haq budjetdan yuqori|· gözlənilən əməkhaqqı büdcəni aşır|· чаканні вышэйшыя за бюджэт
· оценка компании:|· company rating:|· компания бағасы:|· kompaniya bahosi:|· şirkətin reytinqi:|· ацэнка кампаніі:
· правильный вариант|· correct option|· дұрыс нұсқа|· to‘g‘ri variant|· düzgün variant|· правільны варыянт
· правильный ответ|· correct answer|· дұрыс жауап|· to‘g‘ri javob|· düzgün cavab|· правільны адказ
· руководящая роль|· leadership role|· басшылық рөл|· rahbarlik roli|· rəhbərlik rolu|· кіроўная роля
· совпадение ожиданий:|· expectations match:|· күтілімдердің сәйкестігі:|· kutilmalarning mosligi:|· gözləntilərin uyğunluğu:|· супадзенне чаканняў:
· сокращение|· reduction|· қысқару|· qisqarish|· azalma|· скарачэнне
· удовлетворяют всем ограничениям:|· meet all constraints:|· барлық шектеуге сай:|· barcha cheklovlarga mos:|· bütün məhdudiyyətlərə uyğundur:|· адпавядаюць усім абмежаванням:
Ваш грейд не понижается|Your grade is not lowered|Деңгейіңіз төмендетілмейді|Darajangiz pasaytirilmaydi|Səviyyəniz aşağı salınmır|Ваш узровень не зніжаецца
ВАШИ ДАННЫЕ ПОД ВАШИМ КОНТРОЛЕМ|YOUR DATA UNDER YOUR CONTROL|ДЕРЕКТЕРІҢІЗ ӨЗ БАҚЫЛАУЫҢЫЗДА|MA’LUMOTLARINGIZ O‘Z NAZORATINGIZDA|MƏLUMATLARINIZ ÖZ NƏZARƏTİNİZDƏDİR|ВАШЫЯ ДАНЫЯ ПАД ВАШЫМ КАНТРОЛЕМ
Автор и проверяющий — разные эксперты. Пилотные вопросы не меняют результат оценки. Активация требует данных калибровки и решения проверяющего.|The author and reviewer are different experts. Pilot questions do not affect assessment results. Activation requires calibration data and a reviewer decision.|Автор мен тексеруші — әртүрлі сарапшылар. Пилоттық сұрақтар бағалау нәтижесін өзгертпейді. Іске қосу үшін калибрлеу деректері мен тексерушінің шешімі қажет.|Muallif va tekshiruvchi — turli ekspertlar. Sinov savollari baholash natijasini o‘zgartirmaydi. Faollashtirish uchun kalibrlash ma’lumotlari va tekshiruvchining qarori kerak.|Müəllif və yoxlayan şəxs müxtəlif ekspertlərdir. Pilot suallar qiymətləndirmə nəticəsini dəyişmir. Aktivləşdirmə üçün kalibrləmə məlumatları və yoxlayanın qərarı tələb olunur.|Аўтар і правяральнік — розныя эксперты. Пілотныя пытанні не змяняюць вынік ацэнкі. Актывацыя патрабуе даных каліброўкі і рашэння правяральніка.
В каждом кейсе — до 800 символов. Расскажите порядок действий, как проверите качество и на чём сосредоточитесь. Уровень подтверждается после обоих этапов; критерии — логика, качество и приоритеты.|Up to 800 characters per case. Describe your steps, how you will check quality and what you will focus on. The level is verified after both stages; criteria are logic, quality and priorities.|Әр кейсте — 800 таңбаға дейін. Әрекеттердің ретін, сапаны қалай тексеретініңізді және неге назар аударатыныңызды сипаттаңыз. Деңгей екі кезеңнен кейін расталады; критерийлер — логика, сапа және басымдықтар.|Har bir amaliy holat uchun 800 tagacha belgi. Harakatlar tartibi, sifatni qanday tekshirishingiz va nimaga e’tibor qaratishingizni ayting. Daraja ikkala bosqichdan keyin tasdiqlanadi; mezonlar — mantiq, sifat va ustuvorliklar.|Hər praktiki hal üçün 800 simvoladək. Addımlarınızı, keyfiyyəti necə yoxlayacağınızı və nəyə diqqət yetirəcəyinizi təsvir edin. Səviyyə hər iki mərhələdən sonra təsdiqlənir; meyarlar məntiq, keyfiyyət və prioritetlərdir.|У кожным кейсе — да 800 сімвалаў. Апішыце парадак дзеянняў, як праверыце якасць і на чым засяродзіцеся. Узровень пацвярджаецца пасля абодвух этапаў; крытэрыі — логіка, якасць і прыярытэты.
Бюджет до, ₽ / месяц|Maximum budget, ₽ / month|Ең жоғары бюджет, ₽ / ай|Eng ko‘p budjet, ₽ / oy|Maksimum büdcə, ₽ / ay|Максімальны бюджэт, ₽ / месяц
Вам предлагают работу|You have a job offer|Сізге жұмыс ұсынылды|Sizga ish taklif qilinmoqda|Sizə iş təklif olunur|Вам прапануюць працу
Варианты ответа|Answer options|Жауап нұсқалары|Javob variantlari|Cavab variantları|Варыянты адказу
Без сети · изолированный запуск|No network · isolated execution|Желісіз · оқшауланған іске қосу|Tarmoqsiz · ajratilgan muhitda ishga tushirish|Şəbəkəsiz · təcrid olunmuş icra|Без сеткі · ізаляваны запуск
Будет плюсом:|Nice to have:|Қосымша артықшылық:|Qo‘shimcha afzallik:|Əlavə üstünlük:|Будзе перавагай:
Дисциплина|Discipline|Тәртіп|Intizom|İntizam|Дысцыпліна
Диапазон сроков|Duration range|Мерзім аралығы|Muddat oralig‘i|Müddət aralığı|Дыяпазон тэрмінаў
Ролевая проверка знаний|Role-specific knowledge assessment|Рөл бойынша білімді тексеру|Rol bo‘yicha bilimlarni tekshirish|Rol üzrə biliklərin yoxlanması|Праверка ведаў па ролі
Знания роли подтверждены|Role knowledge verified|Рөл бойынша білім расталды|Rol bo‘yicha bilimlar tasdiqlandi|Rol üzrə biliklər təsdiqlənib|Веды па ролі пацверджаныя
Фиксируются только события смены вкладки и копирования. Содержимое буфера, изображение экрана и личные данные не собираются. Сигналы требуют проверки человеком.|Only tab changes and copy events are recorded. Clipboard contents, screen images and personal data are not collected. Signals require human review.|Тек қойындыны ауыстыру және көшіру оқиғалары тіркеледі. Алмасу буферінің мазмұны, экран суреті және жеке деректер жиналмайды. Сигналдарды адам тексеруі тиіс.|Faqat ichki oynani almashtirish va nusxa olish hodisalari qayd etiladi. Bufer tarkibi, ekran tasviri va shaxsiy ma’lumotlar yig‘ilmaydi. Signallarni inson tekshirishi kerak.|Yalnız vərəqin dəyişdirilməsi və kopyalama hadisələri qeydə alınır. Mübadilə buferinin məzmunu, ekran görüntüsü və şəxsi məlumatlar toplanmır. Siqnallar insan tərəfindən yoxlanmalıdır.|Фіксуюцца толькі падзеі змены ўкладкі і капіявання. Змесціва буфера, выява экрана і асабістыя даныя не збіраюцца. Сігналы патрабуюць праверкі чалавекам.
Только явно заданные рабочие предпочтения; без психологических выводов.|Only explicitly stated work preferences; no psychological inferences.|Тек нақты көрсетілген жұмыс қалаулары; психологиялық қорытындыларсыз.|Faqat aniq ko‘rsatilgan ish afzalliklari; psixologik xulosalarsiz.|Yalnız açıq şəkildə göstərilən iş seçimləri; psixoloji nəticələr çıxarılmır.|Толькі яўна зададзеныя працоўныя перавагі; без псіхалагічных высноў.
Удалить гостевой профиль|Delete guest profile|Қонақ профилін жою|Mehmon profilini o‘chirish|Qonaq profilini sil|Выдаліць гасцявы профіль
Удалить документ|Delete document|Құжатты жою|Hujjatni o‘chirish|Sənədi sil|Выдаліць дакумент
Удалить документ и результаты его распознавания?|Delete the document and its recognition results?|Құжатты және оны тану нәтижелерін жою керек пе?|Hujjat va uni tanib olish natijalari o‘chirilsinmi?|Sənədi və onun tanınma nəticələrini silmək istəyirsiniz?|Выдаліць дакумент і вынікі яго распазнавання?
Управляйте сессиями, доступом к контактам и своими данными.|Manage sessions, access to contact details and your data.|Сессияларды, байланыс деректеріне қолжетімділікті және өз деректеріңізді басқарыңыз.|Seanslar, kontakt ma’lumotlariga kirish va o‘z ma’lumotlaringizni boshqaring.|Sessiyaları, əlaqə məlumatlarına girişi və öz məlumatlarınızı idarə edin.|Кіруйце сесіямі, доступам да кантактаў і сваімі данымі.
Управляйте видимостью профиля|Manage profile visibility|Профильдің көрінуін басқару|Profil ko‘rinishini boshqarish|Profilin görünməsini idarə edin|Кіруйце бачнасцю профілю
Тест подтверждает знания, а не всю профессию. Практические критерии и независимая защита вклада оцениваются отдельно в разделе GitHub.|The test verifies knowledge, not the whole profession. Practical criteria and independent contribution defense are assessed separately in the GitHub section.|Тест бүкіл кәсіпті емес, білімді растайды. Практикалық критерийлер мен үлесті тәуелсіз қорғау GitHub бөлімінде бөлек бағаланады.|Test bilimlarni tasdiqlaydi, butun kasbni emas. Amaliy mezonlar va hissani mustaqil himoya qilish GitHub bo‘limida alohida baholanadi.|Test bütün peşəni deyil, bilikləri təsdiqləyir. Praktiki meyarlar və töhfənin müstəqil müdafiəsi GitHub bölməsində ayrıca qiymətləndirilir.|Тэст пацвярджае веды, а не ўсю прафесію. Практычныя крытэрыі і незалежная абарона ўнёску ацэньваюцца асобна ў раздзеле GitHub.
Обзор|Overview|Шолу|Umumiy ko‘rinish|Ümumi baxış|Агляд
Мой кабинет|My dashboard|Жеке кабинетім|Shaxsiy kabinetim|Şəxsi kabinetim|Мой кабінет
Мой профиль|My profile|Менің профилім|Mening profilim|Profilim|Мой профіль
Работодатель|Employer|Жұмыс беруші|Ish beruvchi|İşəgötürən|Працадаўца
Кандидат|Candidate|Үміткер|Nomzod|Namizəd|Кандыдат
Войти|Sign in|Кіру|Kirish|Daxil ol|Увайсці
Войти в кабинет|Sign in|Кабинетке кіру|Kabinetga kirish|Kabinetə daxil ol|Увайсці ў кабінет
Выйти|Sign out|Шығу|Chiqish|Çıx|Выйсці
Регистрация|Registration|Тіркелу|Ro‘yxatdan o‘tish|Qeydiyyat|Рэгістрацыя
Создать аккаунт|Create account|Тіркелгі жасау|Hisob yaratish|Hesab yarat|Стварыць акаўнт
Пароль|Password|Құпиясөз|Parol|Şifrə|Пароль
Новый пароль|New password|Жаңа құпиясөз|Yangi parol|Yeni şifrə|Новы пароль
Сохранить новый пароль|Save new password|Жаңа құпиясөзді сақтау|Yangi parolni saqlash|Yeni şifrəni saxla|Захаваць новы пароль
Забыли пароль?|Forgot password?|Құпиясөзді ұмыттыңыз ба?|Parolni unutdingizmi?|Şifrəni unutmusunuz?|Забылі пароль?
Вернуться ко входу|Back to sign in|Кіру бетіне оралу|Kirishga qaytish|Girişə qayıt|Вярнуцца да ўваходу
Отправить ссылку|Send link|Сілтемені жіберу|Havolani yuborish|Keçid göndər|Адправіць спасылку
Email или имя|Email or name|Электрондық пошта немесе аты|Email yoki ism|E-poçt və ya ad|Электронная пошта або імя
Электронная почта|Email|Электрондық пошта|Elektron pochta|E-poçt|Электронная пошта
Адрес электронной почты|Email address|Электрондық пошта мекенжайы|Elektron pochta manzili|E-poçt ünvanı|Адрас электроннай пошты
Ваше имя|Your name|Атыңыз|Ismingiz|Adınız|Ваша імя
Название компании|Company name|Компания атауы|Kompaniya nomi|Şirkətin adı|Назва кампаніі
Не менее 10 символов|At least 10 characters|Кемінде 10 таңба|Kamida 10 ta belgi|Ən azı 10 simvol|Не менш за 10 сімвалаў
От 10 до 256 символов|10 to 256 characters|10–256 таңба|10 dan 256 tagacha belgi|10-dan 256-dək simvol|Ад 10 да 256 сімвалаў
Ещё нет аккаунта?|No account yet?|Тіркелгіңіз жоқ па?|Hali hisobingiz yo‘qmi?|Hələ hesabınız yoxdur?|Яшчэ няма акаўнта?
Уже зарегистрированы?|Already registered?|Тіркелгенсіз бе?|Ro‘yxatdan o‘tganmisiz?|Artıq qeydiyyatdan keçmisiniz?|Ужо зарэгістраваныя?
Подождите…|Please wait…|Күте тұрыңыз…|Kuting…|Gözləyin…|Пачакайце…
Вакансии|Jobs|Бос орындар|Vakansiyalar|Vakansiyalar|Вакансіі
Активные вакансии|Active jobs|Белсенді бос орындар|Faol vakansiyalar|Aktiv vakansiyalar|Актыўныя вакансіі
Отклики|Applications|Өтінімдер|Arizalar|Müraciətlər|Адгукі
Мои отклики|My applications|Менің өтінімдерім|Mening arizalarim|Müraciətlərim|Мае адгукі
Приглашения|Invitations|Шақырулар|Taklifnomalar|Dəvətlər|Запрашэнні
Предложения|Offers|Ұсыныстар|Takliflar|Təkliflər|Прапановы
Документы|Documents|Құжаттар|Hujjatlar|Sənədlər|Дакументы
Компания|Company|Компания|Kompaniya|Şirkət|Кампанія
Сообщения|Messages|Хабарламалар|Xabarlar|Mesajlar|Паведамленні
Банк талантов|Talent pool|Таланттар қоры|Iste’dodlar bazasi|İstedad bazası|Банк талентаў
Стратегия найма|Hiring strategy|Жұмысқа қабылдау стратегиясы|Ishga olish strategiyasi|İşə qəbul strategiyası|Стратэгія найму
Двойник команды|Team twin|Команданың цифрлық егізі|Jamoaning raqamli egizagi|Komandanın rəqəmsal əkizi|Двайнік каманды
Лаборатория оценок|Assessment lab|Бағалау зертханасы|Baholash laboratoriyasi|Qiymətləndirmə laboratoriyası|Лабараторыя ацэнак
Короткие задания|Short tasks|Қысқа тапсырмалар|Qisqa topshiriqlar|Qısa tapşırıqlar|Кароткія заданні
Доступ и данные|Access and data|Қолжетімділік және деректер|Kirish huquqi va ma’lumotlar|Giriş və məlumatlar|Доступ і даныя
Граф навыков|Skills graph|Дағдылар графы|Ko‘nikmalar grafi|Bacarıqlar qrafı|Граф навыкаў
Доказательства и возможности|Evidence and opportunities|Дәлелдер мен мүмкіндіктер|Dalillar va imkoniyatlar|Sübutlar və imkanlar|Доказы і магчымасці
Карьерный маршрут|Career path|Мансап жолы|Karyera yo‘li|Karyera yolu|Кар’ерны маршрут
Тренировка CAT|CAT practice|CAT жаттығуы|CAT mashqi|CAT məşqi|Трэніроўка CAT
Резюме и тесты|Resumes and tests|Түйіндемелер мен тесттер|Rezyumelar va testlar|CV-lər və testlər|Рэзюмэ і тэсты
Проекты и интервью|Projects and interviews|Жобалар мен сұхбаттар|Loyihalar va suhbatlar|Layihələr və müsahibələr|Праекты і інтэрв’ю
Horizon · мой поиск|Horizon · my search|Horizon · менің іздеуім|Horizon · mening qidiruvim|Horizon · axtarışım|Horizon · мой пошук
Horizon · сценарии|Horizon · scenarios|Horizon · сценарийлер|Horizon · ssenariylar|Horizon · ssenarilər|Horizon · сцэнарыі
hr-консультант|HR adviser|HR кеңесшісі|HR maslahatchisi|HR məsləhətçisi|HR-кансультант
Открыть меню|Open menu|Мәзірді ашу|Menyuni ochish|Menyunu aç|Адкрыць меню
Закрыть меню|Close menu|Мәзірді жабу|Menyuni yopish|Menyunu bağla|Закрыць меню
Сохранить|Save|Сақтау|Saqlash|Saxla|Захаваць
Отмена|Cancel|Бас тарту|Bekor qilish|Ləğv et|Скасаваць
Назад|Back|Артқа|Orqaga|Geri|Назад
Продолжить|Continue|Жалғастыру|Davom etish|Davam et|Працягнуць
Закрыть|Close|Жабу|Yopish|Bağla|Закрыць
Поиск|Search|Іздеу|Qidirish|Axtarış|Пошук
Контакты под вашим контролем|You control your contact details|Байланыс деректері сіздің бақылауыңызда|Kontakt ma’lumotlaringiz nazoratingizda|Əlaqə məlumatlarınız nəzarətinizdədir|Кантакты пад вашым кантролем
% предпосылок подтверждено|% of assumptions verified|% алғышарт расталды|% shartlar tasdiqlandi|% ilkin şərt təsdiqlənib|% перадумоў пацверджана
, стандартная ошибка|, standard error|, стандартты қате|, standart xatolik|, standart xəta|, стандартная памылка
. Грейд не изменён.|. Grade unchanged.|. Деңгей өзгермеді.|. Daraja o‘zgarmadi.|. Səviyyə dəyişməyib.|. Узровень не зменены.
. Минимум:|. Minimum:|. Ең аз:|. Eng kam:|. Minimum:|. Мінімум:
. Полное совпадение top-5:|. Exact top-5 match:|. top-5 толық сәйкестігі:|. top-5 to‘liq mosligi:|. top-5 tam uyğunluğu:|. Поўнае супадзенне top-5:
. Разбор предыдущей попытки доступен ниже.|. The previous attempt review is available below.|. Алдыңғы әрекеттің талдауы төменде берілген.|. Oldingi urinish tahlili quyida mavjud.|. Əvvəlki cəhdin təhlili aşağıda verilib.|. Разбор папярэдняй спробы даступны ніжэй.
. Средняя абсолютная ошибка срока:|. Mean absolute error in duration:|. Мерзімнің орташа абсолютті қатесі:|. Muddatning o‘rtacha mutlaq xatoligi:|. Müddətin orta mütləq xətası:|. Сярэдняя абсалютная памылка тэрміну:
. Указание в резюме не является подтверждением.|. A resume claim is not verification.|. Түйіндемеде көрсету растау болып саналмайды.|. Rezyumeda ko‘rsatish tasdiqlash hisoblanmaydi.|. CV-də qeyd olunması təsdiq sayılmır.|. Згадка ў рэзюмэ не з’яўляецца пацвярджэннем.
. Условия можно повысить; снижение не предлагается.|. Terms can be improved; reductions are not offered.|. Шарттарды жақсартуға болады; төмендету ұсынылмайды.|. Shartlarni yaxshilash mumkin; pasaytirish taklif qilinmaydi.|. Şərtləri yaxşılaşdırmaq olar; azaldılma təklif edilmir.|. Умовы можна палепшыць; зніжэнне не прапануецца.
. Эквивалентные названия должностей и точность записи дат учтены.|. Equivalent job titles and date precision are accounted for.|. Баламалы лауазым атаулары мен күндерді жазу дәлдігі ескерілді.|. Teng ma’noli lavozim nomlari va sanalar aniqligi hisobga olindi.|. Ekvivalent vəzifə adları və tarixlərin dəqiqliyi nəzərə alınıb.|. Улічаны раўназначныя назвы пасад і дакладнасць запісу дат.
/ 100 · обратная связь|/ 100 · feedback|/ 100 · кері байланыс|/ 100 · fikr-mulohaza|/ 100 · rəy|/ 100 · зваротная сувязь
/ до|/ up to|/ дейін|/ gacha|/ qədər|/ да
/450 · Короткий конкретный ответ повышает точность оценки|/450 · A short, specific answer improves assessment accuracy|/450 · Қысқа әрі нақты жауап бағалау дәлдігін арттырады|/450 · Qisqa va aniq javob baholash aniqligini oshiradi|/450 · Qısa və konkret cavab qiymətləndirmənin dəqiqliyini artırır|/450 · Кароткі канкрэтны адказ павышае дакладнасць ацэнкі
/800 символов · без кода|/800 characters · no code|/800 таңба · кодсыз|/800 belgi · kodsiz|/800 simvol · kodsuz|/800 сімвалаў · без кода
17 НАПРАВЛЕНИЙ|17 FIELDS|17 БАҒЫТ|17 YO‘NALISH|17 İSTİQAMƏT|17 КІРУНКАЎ
180 дней|180 days|180 күн|180 kun|180 gün|180 дзён
3 кейса · без написания кода|3 cases · no coding|3 кейс · код жазусыз|3 amaliy holat · kod yozmasdan|3 praktiki hal · kod yazmadan|3 кейсы · без напісання кода
30 дней|30 days|30 күн|30 kun|30 gün|30 дзён
60 дней|60 days|60 күн|60 kun|60 gün|60 дзён
90 дней|90 days|90 күн|90 kun|90 gün|90 дзён
95-й процентиль|95th percentile|95-процентиль|95-persentil|95-ci persentil|95-ы працэнтыль
; ошибок:|; errors:|; қателер:|; xatolar:|; xətalar:|; памылак:
% правильных ответов. Откройте разбор, чтобы увидеть свой выбор и ключ по каждому вопросу.|% correct answers. Open the review to see your choice and the answer key for each question.|% дұрыс жауап. Әр сұрақтағы таңдауыңыз бен дұрыс жауабын көру үшін талдауды ашыңыз.|% to‘g‘ri javob. Har bir savoldagi tanlovingiz va to‘g‘ri javobni ko‘rish uchun tahlilni oching.|% düzgün cavab. Hər sual üzrə seçiminizi və düzgün cavabı görmək üçün təhlili açın.|% правільных адказаў. Адкрыйце разбор, каб убачыць свой выбар і правільны адказ на кожнае пытанне.
20–30 минут на практическую задачу. Перед отправкой условие и эталон проходят проверку запуска.|20–30 minutes for a practical task. Before submission, the task specification and reference solution undergo an execution check.|Практикалық тапсырмаға 20–30 минут. Жіберу алдында тапсырма шарты мен эталондық шешімнің орындалуы тексеріледі.|Amaliy topshiriq uchun 20–30 daqiqa. Yuborishdan oldin topshiriq sharti va namunaviy yechimning ishga tushishi tekshiriladi.|Praktiki tapşırıq üçün 20–30 dəqiqə. Göndərilməzdən əvvəl tapşırığın şərti və etalon həllin icrası yoxlanılır.|20–30 хвілін на практычную задачу. Перад адпраўкай умова і эталоннае рашэнне праходзяць праверку запуску.
Backend-разработчик в продуктовую команду|Backend developer for a product team|Өнім командасына backend әзірлеушісі|Mahsulot jamoasiga backend dasturchi|Məhsul komandası üçün backend proqramçısı|Backend-распрацоўшчык у прадуктовую каманду
Email не заполнен|Email is required|Электрондық пошта толтырылмаған|Email kiritilmagan|E-poçt daxil edilməyib|Электронная пошта не запоўнена
Horizon учитывает конкретную цель и текущий рынок платформы.|Horizon takes your specific goal and the platform’s current job market into account.|Horizon нақты мақсат пен платформаның ағымдағы еңбек нарығын ескереді.|Horizon aniq maqsad va platformaning joriy mehnat bozorini hisobga oladi.|Horizon konkret məqsədi və platformanın cari əmək bazarını nəzərə alır.|Horizon улічвае канкрэтную мэту і бягучы рынак платформы.
ID кандидата|Candidate ID|Үміткер ID-і|Nomzod ID-si|Namizəd ID-si|ID кандыдата
ID компании на DreamJob|Company ID on DreamJob|DreamJob-тағы компания ID-і|DreamJob’dagi kompaniya ID-si|DreamJob-da şirkət ID-si|ID кампаніі на DreamJob
ID участника ФСП|ФСП participant ID|ФСП қатысушысының ID-і|ФСП ishtirokchisi ID-si|ФСП iştirakçısının ID-si|ID удзельніка ФСП
JSON с вакансиями|Job listings in JSON|Бос орындар бар JSON|Vakansiyalar bilan JSON|Vakansiyalar olan JSON|JSON з вакансіямі
Middle Python-разработчик, FastAPI и PostgreSQL, удалённо, 180–250 тысяч рублей. Разрабатывать API и улучшать надёжность.|Mid-level Python developer, FastAPI and PostgreSQL, remote, 180–250 thousand rubles. Develop APIs and improve reliability.|Middle деңгейіндегі Python әзірлеушісі, FastAPI және PostgreSQL, қашықтан, 180–250 мың рубль. API әзірлеу және сенімділікті арттыру.|Middle darajadagi Python dasturchi, FastAPI va PostgreSQL, masofadan, 180–250 ming rubl. API yaratish va ishonchlilikni yaxshilash.|Middle səviyyəli Python proqramçısı, FastAPI və PostgreSQL, məsafədən, 180–250 min rubl. API hazırlamaq və etibarlılığı artırmaq.|Python-распрацоўшчык узроўню Middle, FastAPI і PostgreSQL, дыстанцыйна, 180–250 тысяч рублёў. Распрацоўваць API і павышаць надзейнасць.
PDF с текстом, сканы и изображения. Извлечём сведения и покажем их источник.|Text PDFs, scans and images. We will extract the information and show its source.|Мәтіні бар PDF, скандар мен суреттер. Ақпаратты шығарып, дереккөзін көрсетеміз.|Matnli PDF, skanlar va rasmlar. Ma’lumotlarni ajratib olib, manbasini ko‘rsatamiz.|Mətnli PDF, skanlar və şəkillər. Məlumatları çıxarıb mənbəyini göstərəcəyik.|PDF з тэкстам, сканы і выявы. Вылучым звесткі і пакажам іх крыніцу.
PDF, PNG, JPEG · до 20 МБ · до 40 страниц · до 5 файлов в очереди|PDF, PNG, JPEG · up to 20 MB · up to 40 pages · up to 5 queued files|PDF, PNG, JPEG · 20 МБ дейін · 40 бетке дейін · кезекте 5 файлға дейін|PDF, PNG, JPEG · 20 MB gacha · 40 sahifagacha · navbatda 5 tagacha fayl|PDF, PNG, JPEG · 20 MB-dək · 40 səhifəyədək · növbədə 5 fayladək|PDF, PNG, JPEG · да 20 МБ · да 40 старонак · да 5 файлаў у чарзе
PDF-профиль|PDF profile|PDF профилі|PDF profil|PDF profil|PDF-профіль
Talantix подключён. Загрузите каталог и выберите источник кандидатов.|Talantix connected. Load the catalog and choose a candidate source.|Talantix қосылды. Каталогты жүктеп, үміткерлер дереккөзін таңдаңыз.|Talantix ulandi. Katalogni yuklang va nomzodlar manbasini tanlang.|Talantix qoşulub. Kataloqu yükləyin və namizəd mənbəyini seçin.|Talantix падключаны. Загрузіце каталог і выберыце крыніцу кандыдатаў.
you@company.ru или имя при регистрации|you@company.ru or the name used when registering|you@company.ru немесе тіркелген кездегі атыңыз|you@company.ru yoki ro‘yxatdan o‘tishdagi ism|you@company.ru və ya qeydiyyat zamanı istifadə etdiyiniz ad|you@company.ru або імя пры рэгістрацыі
Согласен на обработку данных профиля для работы сервиса. Публикацию профиля выберу отдельно в настройках.|I agree to processing my profile data to operate the service. I will choose whether to publish my profile separately in settings.|Сервистің жұмысы үшін профиль деректерімді өңдеуге келісемін. Профильді жариялау туралы шешімді баптауларда бөлек таңдаймын.|Servis ishlashi uchun profil ma’lumotlarim qayta ishlanishiga roziman. Profilni e’lon qilishni sozlamalarda alohida tanlayman.|Xidmətin fəaliyyəti üçün profil məlumatlarımın işlənməsinə razıyam. Profilin dərc olunmasını parametrlərdə ayrıca seçəcəyəm.|Згодны на апрацоўку даных профілю для працы сэрвісу. Публікацыю профілю выберу асобна ў наладах.
Открыть письмо и подтвердить|Open email and verify|Хатты ашып, растау|Xatni ochish va tasdiqlash|Məktubu aç və təsdiqlə|Адкрыць ліст і пацвердзіць
Сохранить профиль|Save profile|Профильді сақтау|Profilni saqlash|Profili saxla|Захаваць профіль
Опубликовать вакансию|Publish job|Бос орынды жариялау|Vakansiyani e’lon qilish|Vakansiyanı dərc et|Апублікаваць вакансію
Опубликовать работодателям|Publish for employers|Жұмыс берушілерге жариялау|Ish beruvchilar uchun e’lon qilish|İşəgötürənlər üçün dərc et|Апублікаваць для працадаўцаў
Создать вакансию / потребность|Create job / hiring need|Бос орын / қажеттілік жасау|Vakansiya / ehtiyoj yaratish|Vakansiya / ehtiyac yarat|Стварыць вакансію / патрэбу
· изменение вилки: +|· salary range change: +|· жалақы ауқымының өзгеруі: +|· ish haqi oralig‘i o‘zgarishi: +|· maaş aralığının dəyişməsi: +|· змяненне дыяпазону зарплаты: +
· стр.|· page|· бет|· sahifa|· səhifə|· стар.
Кандидат увидит зарплату и решит, открыть ли вам контакты.|The candidate will see the salary and decide whether to share their contact details with you.|Үміткер жалақыны көріп, сізге байланыс деректерін ашу туралы шешім қабылдайды.|Nomzod ish haqini ko‘rib, sizga kontakt ma’lumotlarini ochish haqida qaror qiladi.|Namizəd maaşı görüb əlaqə məlumatlarını sizinlə paylaşmağa qərar verəcək.|Кандыдат убачыць зарплату і вырашыць, ці адкрываць вам свае кантакты.
Отправляя отклик, вы открываете этой компании контакты из своего профиля.|Submitting an application shares the contact details from your profile with this company.|Өтінім жібергенде осы компанияға профиліңіздегі байланыс деректерін ашасыз.|Ariza yuborish orqali bu kompaniyaga profilingizdagi kontakt ma’lumotlarini ochasiz.|Müraciət göndərməklə profilinizdəki əlaqə məlumatlarını bu şirkətlə paylaşırsınız.|Адпраўляючы адгук, вы адкрываеце гэтай кампаніі кантакты са свайго профілю.
Контакты откроются только после согласия кандидата на ваше предложение.|Contact details are shared only after the candidate accepts your offer.|Байланыс деректері үміткер ұсынысыңызға келісім бергеннен кейін ғана ашылады.|Kontakt ma’lumotlari nomzod taklifingizga rozilik berganidan keyingina ochiladi.|Əlaqə məlumatları yalnız namizəd təklifinizi qəbul etdikdən sonra paylaşılacaq.|Кантакты адкрыюцца толькі пасля згоды кандыдата на вашу прапанову.
Отклик отправлен. Контакты открыты этой компании.|Application sent. Your contact details have been shared with this company.|Өтінім жіберілді. Байланыс деректеріңіз осы компанияға ашылды.|Ariza yuborildi. Kontakt ma’lumotlaringiz bu kompaniyaga ochildi.|Müraciət göndərildi. Əlaqə məlumatlarınız bu şirkətlə paylaşılıb.|Адгук адпраўлены. Вашы кантакты адкрытыя гэтай кампаніі.
Приглашение принято. Контакты открыты этой компании.|Invitation accepted. Your contact details have been shared with this company.|Шақыру қабылданды. Байланыс деректеріңіз осы компанияға ашылды.|Taklifnoma qabul qilindi. Kontakt ma’lumotlaringiz bu kompaniyaga ochildi.|Dəvət qəbul edildi. Əlaqə məlumatlarınız bu şirkətlə paylaşılıb.|Запрашэнне прынятае. Вашы кантакты адкрытыя гэтай кампаніі.
Если работодатель подключил Talantix, разрешаю передать туда мой отклик, резюме и контакты для этой вакансии.|If the employer has connected Talantix, I allow my application, resume and contact details for this job to be transferred to Talantix.|Жұмыс беруші Talantix-ті қосқан болса, осы бос орынға өтінімімді, түйіндемемді және байланыс деректерімді оған беруге келісемін.|Ish beruvchi Talantix’ni ulagan bo‘lsa, bu vakansiya uchun arizam, rezyume va kontakt ma’lumotlarimni unga uzatishga roziman.|İşəgötürən Talantix-i qoşubsa, bu vakansiya üçün müraciətimin, CV-min və əlaqə məlumatlarımın oraya ötürülməsinə icazə verirəm.|Калі працадаўца падключыў Talantix, дазваляю перадаць туды мой адгук, рэзюмэ і кантакты для гэтай вакансіі.
Если у компании подключён Talantix, разрешаю передать туда мой отклик и контакты для этой вакансии.|If the company has connected Talantix, I allow my application and contact details for this job to be transferred to Talantix.|Компания Talantix-ті қосқан болса, осы бос орынға өтінімім мен байланыс деректерімді оған беруге келісемін.|Kompaniya Talantix’ni ulagan bo‘lsa, bu vakansiya uchun arizam va kontakt ma’lumotlarimni unga uzatishga roziman.|Şirkət Talantix-i qoşubsa, bu vakansiya üçün müraciətimin və əlaqə məlumatlarımın oraya ötürülməsinə icazə verirəm.|Калі ў кампаніі падключаны Talantix, дазваляю перадаць туды мой адгук і кантакты для гэтай вакансіі.
Русский|Russian|Орысша|Ruscha|Rusca|Руская
Беларуская|Belarusian|Беларусь тілі|Belaruscha|Belarusca|Беларуская
Қазақша|Kazakh|Қазақша|Qozoqcha|Qazaxca|Казахская
Вклад в GitHub|GitHub contribution|GitHub-тағы үлес|GitHub’dagi hissa|GitHub töhfəsi|Унёсак у GitHub
Радар найма|Hiring radar|Жұмысқа қабылдау радары|Ishga olish radari|İşə qəbul radarı|Радар найму
Аккаунт GitHub|GitHub account|GitHub тіркелгісі|GitHub hisobi|GitHub hesabı|Акаўнт GitHub
Аккаунт привязан:|Linked account:|Тіркелгі байланыстырылды:|Hisob bog‘landi:|Hesab əlaqələndirilib:|Акаўнт прывязаны:
Подтверждение владения аккаунтом|Account ownership verification|Тіркелгі иелігін растау|Hisobga egalikni tasdiqlash|Hesab sahibliyinin təsdiqi|Пацвярджэнне валодання акаўнтам
Получить одноразовый код|Get a one-time code|Бір реттік код алу|Bir martalik kod olish|Birdəfəlik kod al|Атрымаць аднаразовы код
ID публичного gist|Public gist ID|Жария gist ID-і|Ochiq gist ID-si|İctimai gist ID-si|ID публічнага gist
Проверить привязку|Verify account link|Тіркелгі байланысын тексеру|Hisob bog‘lanishini tekshirish|Hesab əlaqəsini yoxla|Праверыць прывязку
Посмотреть репозитории|View repositories|Репозиторийлерді көру|Repozitoriylarni ko‘rish|Repozitoriylərə bax|Паглядзець рэпазіторыі
Публичные репозитории|Public repositories|Жария репозиторийлер|Ochiq repozitoriylar|İctimai repozitoriylər|Публічныя рэпазіторыі
Ссылка на публичный PR|Public PR link|Жария PR сілтемесі|Ochiq PR havolasi|İctimai PR keçidi|Спасылка на публічны PR
Отправить защиту|Submit contribution defense|Үлесті қорғауды жіберу|Hissa himoyasini yuborish|Töhfə müdafiəsini göndər|Адправіць абарону ўнёску
Использовать этот публичный артефакт для проверки моего вклада|Use this public artifact to verify my contribution|Үлесімді тексеру үшін осы жария артефактіні пайдалану|Hissamni tekshirish uchun ushbu ochiq artefaktdan foydalanish|Töhfəmi yoxlamaq üçün bu ictimai artefaktdan istifadə et|Выкарыстаць гэты публічны артэфакт для праверкі майго ўнёску
Привязка подтверждает контроль аккаунта, но не авторство каждого изменения.|Linking verifies control of the account, but not authorship of every change.|Байланыстыру тіркелгіні басқаруды растайды, бірақ әр өзгерістің авторлығын растамайды.|Bog‘lash hisobni boshqarishni tasdiqlaydi, ammo har bir o‘zgarish muallifligini tasdiqlamaydi.|Əlaqələndirmə hesaba nəzarəti təsdiqləyir, lakin hər dəyişikliyin müəllifliyini təsdiqləmir.|Прывязка пацвярджае кантроль акаўнта, але не аўтарства кожнай змены.
Срок действия — 10 минут. После проверки публичный gist можно удалить.|Valid for 10 minutes. You may delete the public gist after verification.|Жарамдылық мерзімі — 10 минут. Тексеруден кейін жария gist-ті жоюға болады.|Amal qilish muddati — 10 daqiqa. Tekshiruvdan keyin ochiq gist’ni o‘chirish mumkin.|10 dəqiqə qüvvədədir. Yoxlamadan sonra ictimai gist-i silmək olar.|Тэрмін дзеяння — 10 хвілін. Пасля праверкі публічны gist можна выдаліць.
GitHub используется только для выбранных вами публичных доказательств. Код не запускается, контактная база не собирается.|GitHub is used only for public evidence you select. Code is not executed and no contact database is collected.|GitHub тек сіз таңдаған жария дәлелдер үшін қолданылады. Код іске қосылмайды, байланыс деректерінің базасы жиналмайды.|GitHub faqat siz tanlagan ochiq dalillar uchun ishlatiladi. Kod ishga tushirilmaydi, kontaktlar bazasi yig‘ilmaydi.|GitHub yalnız seçdiyiniz ictimai sübutlar üçün istifadə olunur. Kod icra edilmir və əlaqə bazası toplanmır.|GitHub выкарыстоўваецца толькі для выбраных вамі публічных доказаў. Код не запускаецца, база кантактаў не збіраецца.
Грейд профессии не присваивается по общей CAT-проверке или наличию PR. Результат включает область проверки и отдельно оценённые навыки.|A professional grade is not awarded based on a general CAT assessment or the existence of a PR. The result states the assessment scope and the skills assessed separately.|Кәсіби деңгей жалпы CAT тексеруі немесе PR бар болуы бойынша берілмейді. Нәтижеде тексеру аясы мен бөлек бағаланған дағдылар көрсетіледі.|Kasbiy daraja umumiy CAT tekshiruvi yoki PR mavjudligi asosida berilmaydi. Natijada tekshiruv doirasi va alohida baholangan ko‘nikmalar ko‘rsatiladi.|Peşə səviyyəsi ümumi CAT yoxlaması və ya PR-nin mövcudluğu əsasında verilmir. Nəticədə yoxlamanın əhatəsi və ayrıca qiymətləndirilmiş bacarıqlar göstərilir.|Прафесійны ўзровень не прысвойваецца на падставе агульнай CAT-праверкі ці наяўнасці PR. Вынік уключае вобласць праверкі і асобна ацэненыя навыкі.
Прогноз не принимает кадровое решение автоматически и не использует чувствительные признаки.|The forecast does not make hiring decisions automatically and does not use sensitive attributes.|Болжам кадрлық шешімді автоматты түрде қабылдамайды және сезімтал белгілерді қолданбайды.|Prognoz kadrlar bo‘yicha qarorni avtomatik qabul qilmaydi va sezgir belgilarni ishlatmaydi.|Proqnoz işə qəbul qərarını avtomatik vermir və həssas əlamətlərdən istifadə etmir.|Прагноз не прымае кадравае рашэнне аўтаматычна і не выкарыстоўвае адчувальныя прыкметы.
Для этой роли практика GitHub не является подходящим способом подтверждения.|GitHub practice is not an appropriate verification method for this role.|Осы рөл үшін GitHub практикасы растаудың қолайлы тәсілі емес.|Bu rol uchun GitHub amaliyoti mos tasdiqlash usuli emas.|Bu rol üçün GitHub təcrübəsi uyğun təsdiqləmə üsulu deyil.|Для гэтай ролі практыка GitHub не з’яўляецца прыдатным спосабам пацвярджэння.
Исследовательский сигнал для модели. Не заменяет отклик, приглашение или принятие предложения.|A research signal for the model. It does not replace an application, invitation or offer acceptance.|Модельге арналған зерттеу сигналы. Өтінімді, шақыруды немесе ұсынысты қабылдауды алмастырмайды.|Model uchun tadqiqot signali. Ariza, taklifnoma yoki taklifni qabul qilish o‘rnini bosmaydi.|Model üçün tədqiqat siqnalı. Müraciəti, dəvəti və ya təklifin qəbulunu əvəz etmir.|Даследчы сігнал для мадэлі. Не замяняе адгук, запрашэнне ці прыняцце прапановы.
Учётная запись|Account|Тіркелгі|Hisob|Hesab|Уліковы запіс
Доступ и безопасность.|Access and security.|Қолжетімділік және қауіпсіздік.|Kirish va xavfsizlik.|Giriş və təhlükəsizlik.|Доступ і бяспека.
Копия ваших данных|A copy of your data|Деректеріңіздің көшірмесі|Ma’lumotlaringiz nusxasi|Məlumatlarınızın surəti|Копія вашых даных
Скачать мои данные|Download my data|Деректерімді жүктеп алу|Ma’lumotlarimni yuklab olish|Məlumatlarımı endir|Спампаваць мае даныя
Выйти на всех устройствах|Sign out on all devices|Барлық құрылғыда жүйеден шығу|Barcha qurilmalardan chiqish|Bütün cihazlardan çıx|Выйсці на ўсіх прыладах
Удаление аккаунта|Account deletion|Тіркелгіні жою|Hisobni o‘chirish|Hesabın silinməsi|Выдаленне акаўнта
Удалить мой аккаунт|Delete my account|Тіркелгімді жою|Hisobimni o‘chirish|Hesabımı sil|Выдаліць мой акаўнт
Подтвердите текущий пароль|Confirm your current password|Ағымдағы құпиясөзді растаңыз|Joriy parolni tasdiqlang|Cari şifrənizi təsdiqləyin|Пацвердзіце бягучы пароль
Удалить аккаунт и его данные? Это действие нельзя отменить в кабинете.|Delete the account and its data? This action cannot be undone in your dashboard.|Тіркелгі мен оның деректерін жою керек пе? Бұл әрекетті кабинетте кері қайтару мүмкін емес.|Hisob va uning ma’lumotlari o‘chirilsinmi? Bu amalni kabinetda bekor qilib bo‘lmaydi.|Hesabı və onun məlumatlarını silmək istəyirsiniz? Bu əməliyyatı kabinetdə geri qaytarmaq olmaz.|Выдаліць акаўнт і яго даныя? Гэта дзеянне нельга адмяніць у кабінеце.
Кому доступны контакты|Who can access your contact details|Байланыс деректері кімге қолжетімді|Kontakt ma’lumotlari kimga ochiq|Əlaqə məlumatları kimə açıqdır|Каму даступныя кантакты
Доступ разрешён вами|Access granted by you|Қолжетімділікті сіз бердіңіз|Kirish huquqini siz berdingiz|Girişə siz icazə vermisiniz|Доступ дазволены вамі
Контакты закрыты|Contact details hidden|Байланыс деректері жабық|Kontakt ma’lumotlari yopiq|Əlaqə məlumatları bağlıdır|Кантакты закрытыя
Открыть снова|Restore access|Қолжетімділікті қайта ашу|Kirish huquqini tiklash|Girişi bərpa et|Аднавіць доступ
Закрыть контакты|Revoke contact access|Байланыс деректеріне қолжетімділікті жабу|Kontakt ma’lumotlariga kirishni yopish|Əlaqə məlumatlarına girişi bağla|Закрыць доступ да кантактаў
Открыть контакты|Share contact details|Байланыс деректерін ашу|Kontakt ma’lumotlarini ochish|Əlaqə məlumatlarını paylaş|Адкрыць кантакты
Профиль, документы и рабочие связи будут удалены, все сессии завершатся. События безопасности без содержимого профиля и резервные копии хранятся по политике оператора.|Your profile, documents and work connections will be deleted, and all sessions will end. Security events without profile contents and backups are retained according to the operator’s policy.|Профиль, құжаттар мен жұмыс байланыстары жойылып, барлық сессия аяқталады. Профиль мазмұны жоқ қауіпсіздік оқиғалары мен резервтік көшірмелер оператор саясатына сәйкес сақталады.|Profil, hujjatlar va ish aloqalari o‘chiriladi, barcha seanslar tugaydi. Profil mazmunisiz xavfsizlik hodisalari va zaxira nusxalar operator siyosatiga muvofiq saqlanadi.|Profil, sənədlər və iş əlaqələri silinəcək, bütün sessiyalar bitəcək. Profil məzmunu olmayan təhlükəsizlik hadisələri və ehtiyat nüsxələr operatorun siyasətinə uyğun saxlanılır.|Профіль, дакументы і працоўныя сувязі будуць выдаленыя, усе сесіі завершацца. Падзеі бяспекі без змесціва профілю і рэзервовыя копіі захоўваюцца паводле палітыкі аператара.
'''

LANGUAGE_REVIEWED={
 'en':{
  'Автор и проверяющий — разные эксперты. Пилотные вопросы не меняют результат оценки. Активация требует данных калибровки и решения проверяющего.':'The author and reviewer are different experts. Pilot questions do not affect assessment results. Activation requires calibration data and a reviewer decision.',
  '· диапазонов уровня:':'· grade ranges:',
  'Кандидат увидит зарплату и решит, открыть ли вам контакты.':'The candidate will see the salary and decide whether to share their contact details with you.',
  'Кандидат разрешил вашей компании связаться с ним.':'The candidate has allowed your company to contact them.',
  'Категория подтверждена на 90 дней. Для предложений включите публикацию профиля.':'Category verified for 90 days. Enable profile publication to receive offers.',
  'КАБИНЕТ КАНДИДАТА':'CANDIDATE DASHBOARD',
  'КАБИНЕТ РАБОТОДАТЕЛЯ':'EMPLOYER DASHBOARD',
  'Источник рядом':'Source attached',
  'Отклик отправлен. Контакты открыты этой компании.':'Application sent. Your contact details have been shared with this company.',
  'Приглашение принято. Контакты открыты этой компании.':'Invitation accepted. Your contact details have been shared with this company.',
  'Отправляя отклик, вы открываете этой компании контакты из своего профиля.':'Submitting an application shares the contact details from your profile with this company.',
  'Если работодатель подключил Talantix, разрешаю передать туда мой отклик, резюме и контакты для этой вакансии.':'If the employer has connected Talantix, I allow my application, resume and contact details for this job to be transferred to Talantix.',
  'Если у компании подключён Talantix, разрешаю передать туда мой отклик и контакты для этой вакансии.':'If the company has connected Talantix, I allow my application and contact details for this job to be transferred to Talantix.',
  'Вы можете закрыть доступ компании независимо от статуса предложения. Уже полученную компанией копию контактов сервис отозвать не может.':'You can revoke a company’s access regardless of the offer status. The service cannot recall a copy of your contact details that the company has already received.',
  'Контрольная разметка не читается рабочим API':'The production API does not read the evaluation ground truth',
  'Измерена фактическая выдача API по фиксированной контрольной разметке. Это не измеренный процент успешных наймов.':'Actual API results were measured against fixed evaluation labels. This is not a measured successful hiring rate.',
  'Не удалось завершить сессию. Попробуйте снова.':'Could not sign out. Please try again.',
  'Описывайте реальные проекты. Можно не называть заказчика и закрытые цифры. Если опыта нет, сообщите об этом.':'Describe real projects. You may omit client names and confidential figures. If you have no experience, say so.',
  'Подпись Ed25519. Без имени, телефона и email. Действие прекращается при отзыве паспорта или доказательства.':'Ed25519 signature. No name, phone or email. Validity ends if the passport or evidence is revoked.',
  'Профиль, сведения о документах и события безопасности в JSON. Оригиналы файлов и результаты распознавания доступны в разделе «Документы».':'Your profile, document information and security events in JSON. Original files and extracted text are available under Documents.',
  'Профиль, стек и ожидания':'Profile, technology stack and expectations',
  'Прочитаем документ':'We will read the document',
  'Прочитано':'Read',
  'Прямые контакты закрыты. Внутренний чат остаётся приватным и доступен только этой компании.':'Direct contact details are hidden. The internal chat remains private and is available only to this company.',
  'Проверить подпись и отзыв':'Check signature and revocation',
  'Фиксируются только события смены вкладки и копирования. Содержимое буфера, изображение экрана и личные данные не собираются. Сигналы требуют проверки человеком.':'Only tab changes and copy events are recorded. Clipboard contents, screen images and personal data are not collected. Signals require human review.',
  'Сверяется содержание. Подлинность документа и электронная подпись не удостоверяются. Выписка доступна только вам.':'The contents are compared. Document authenticity and electronic signatures are not authenticated. The statement is accessible only to you.',
  'Копия ваших данных':'A copy of your data',
  'Выпустить подписанный паспорт':'Issue a signed passport',
  'Грейд профессии не присваивается по общей CAT-проверке или наличию PR. Результат включает область проверки и отдельно оценённые навыки.':'A professional grade is not awarded based on a general CAT assessment or the existence of a PR. The result states the assessment scope and the skills assessed separately.',
  'Для этой роли практика GitHub не является подходящим способом подтверждения.':'GitHub practice is not an appropriate verification method for this role.',
  'Защита pull request':'Pull request contribution defense',
  'Защиты пока не подготовлены.':'No contribution defenses have been prepared yet.',
  'Мои защиты вклада':'My contribution defenses',
  'Практика, знания и авторская привязка подтверждены':'Practice, knowledge and authorship linkage verified',
  'Область оценки зафиксирована; полное подтверждение роли пока не выдано':'Assessment scope recorded; full role verification has not yet been issued',
  'Прогноз не принимает кадровое решение автоматически и не использует чувствительные признаки.':'The forecast does not make hiring decisions automatically and does not use sensitive attributes.',
  'Неответившие исключены из бинарных решений и показаны как цензурированные наблюдения.':'Non-responders are excluded from binary decisions and shown as censored observations.',
  'Внутренний инвентарь, не национальная статистика. Синтетические вакансии:':'Internal inventory, not national statistics. Synthetic job listings:',
 },
 'kk':{
  'Гибрид':'Аралас',
  'Грейд':'Деңгей',
  'ДЕМО-ПРОФИЛЬ':'ДЕМО-ПРОФИЛЬ',
  'ДИАЛОГ НАЧИНАЕТСЯ С ПРОЗРАЧНОСТИ':'ӘҢГІМЕ АШЫҚТЫҚТАН БАСТАЛАДЫ',
  'Двустороннее решение':'Екіжақты шешім',
  'Демо-команда':'Демо команда',
  'Дисциплина':'Тәртіп',
  'К':'К',
  'Кейс':'Кейс',
  'Меню':'Мәзір',
  'Оригинал':'Түпнұсқа',
  'ПРУФ-ИТ':'ПРУФ-ИТ',
  'ПРУФ-ИТ · ФСП':'ПРУФ-ИТ · ФСП',
  'Пилот':'Пилот',
  'План':'Жоспар',
  'Повторить':'Қайталау',
  'Подготавливаем…':'Дайындап жатырмыз…',
  'Подробнее':'Толығырақ',
  'Подтверждено':'Расталды',
  'Подтверждено:':'Расталды:',
  'Показывать':'Көрсету',
  'Полная':'Толық',
  'Почему?':'Неліктен?',
  'Приватность':'Құпиялылық',
  'Пригласить':'Шақыру',
  'Принято':'Қабылданды',
  'Приняты':'Қабылданды',
  'Принять':'Қабылдау',
  'Принять в пилот':'Пилотқа қабылдау',
  'Проверено':'Тексерілді',
  'Проверено:':'Тексерілді:',
  'Проверить':'Тексеру',
  'Проверить:':'Тексеру:',
  'Проверьте поля':'Өрістерді тексеріңіз',
  'Проверьте:':'Тексеріңіз:',
  'Прогресс оценки':'Бағалау барысы',
  'Просмотрен':'Қаралды',
  'Просмотрено':'Қаралды',
  'Просмотрены':'Қаралды',
  'Профиль':'Профиль',
  'Профиль скрыт':'Профиль жасырылған',
  'Прочитано':'Оқылды',
  'Работодатель:':'Жұмыс беруші:',
  'Работодателю':'Жұмыс берушіге',
  'Разбор проекта':'Жобаны талдау',
  'Разбор проекта:':'Жобаны талдау:',
  'Размеченных пар':'Белгіленген жұптар',
  'Распознавание':'Тану',
  'Распределено':'Бөлінді',
  'Рассчитываем…':'Есептеп жатырмыз…',
  'Расчёт сохранён':'Есептеу сақталды',
  'Ревью практики':'Практиканы сараптау',
  'Резерв':'Резерв',
  'Результат':'Нәтиже',
  'Резюме':'Түйіндеме',
  'Резюме ·':'Түйіндеме ·',
  'Резюме в файле':'Файлдағы түйіндеме',
  'Резюме:':'Түйіндеме:',
  'Роль:':'Рөл:',
  'Рост':'Өсу',
  'С возвращением.':'Қайта оралуыңызбен.',
  'Сбросить':'Қалпына келтіру',
  'Сдвиг':'Ығысу',
  'Скрытые тесты:':'Жасырын тесттер:',
  'Скрыть резюме':'Түйіндемені жасыру',
  'Следующий шаг':'Келесі қадам',
  'Совместимость':'Үйлесімділік',
  'Сообщение':'Хабарлама',
  'Состояние:':'Күйі:',
  'Сохраняем…':'Сақтап жатырмыз…',
  'Сохранённые':'Сақталған',
  'Специализация':'Мамандану',
  'Сравнить':'Салыстыру',
  'Средние 50%:':'Ортаңғы 50%:',
  'Стаж':'Еңбек өтілі',
  'Статус':'Мәртебе',
  'Статус отклика':'Өтінім мәртебесі',
  'Стек':'Стек',
  'Стек из резюме':'Түйіндемедегі стек',
  'Страница':'Бет',
  'Телефон':'Телефон',
  'Темп':'Қарқын',
  'Тест':'Тест',
  'Только мне':'Тек маған',
  'УСЛОВИЕ':'ШАРТ',
  'Уведомления':'Хабарландырулар',
  'Узкие места':'Тар орындар',
  'Уровень роли':'Рөл деңгейі',
  'Условие':'Шарт',
  'ФИО':'Т.А.Ә.',
  'ФСП':'ФСП',
  'ФСП ID':'ФСП ID',
  'ФСП · демо':'ФСП · демо',
  'Файлы:':'Файлдар:',
  'Формат':'Формат',
  'Формат оценки':'Бағалау форматы',
  'Формат работы':'Жұмыс форматы',
  'Целевая позиция':'Мақсатты лауазым',
  'Целевое резюме':'Мақсатты түйіндеме',
  'Целевой грейд':'Мақсатты деңгей',
  'Цель −':'Мақсат −',
  'Часов в неделю':'Аптасына сағат',
  'Черновик':'Жоба нұсқасы',
  'Числовой ответ':'Сандық жауап',
  'Что важно вам':'Сізге не маңызды',
  'Что улучшить':'Нені жақсарту керек',
  'Экспресс':'Экспресс',
  'Маршрут 14 / 30 / 90':'Жоспар 14 / 30 / 90',
  'Портфель найма':'Жұмысқа қабылдау портфелі',
  'Участие в мероприятиях ФСП':'ФСП іс-шараларына қатысу',
  'Участник текущего процесса':'Ағымдағы процестің қатысушысы',
  'ФЕДЕРАЦИЯ СПОРТИВНОГО':'СПОРТТЫҚ ФЕДЕРАЦИЯ',
  'ФСП · ждёт проверки':'ФСП · тексеруді күтуде',
  'ФСП подтверждено':'ФСП расталды',
  'Файл должен быть меньше 1 МБ':'Файл көлемі 1 МБ-тан аз болуы тиіс',
  'Фактический результат и наблюдения':'Нақты нәтиже және бақылаулар',
  'Фактический срок записан':'Нақты мерзім жазылды',
  'Федерация спортивного программирования':'Спорттық бағдарламалау федерациясы',
  'Фильтры сохраняются вместе с составом первой страницы.':'Сүзгілер бірінші беттің құрамымен бірге сақталады.',
  'Формат не указан':'Формат көрсетілмеген',
  'Хорошие предложения начинаются с профиля':'Жақсы ұсыныстар профильден басталады',
  'Хочу расти горизонтально: какие смежные роли мне подходят?':'Көлденең дамығым келеді: маған қандай іргелес рөлдер сәйкес келеді?',
  'Хочу сменить позицию. Какие навыки из моего опыта можно перенести?':'Лауазымымды ауыстырғым келеді. Тәжірибемдегі қандай дағдыларды жаңа рөлге қолдануға болады?',
  'ЦЕЛЕВЫЕ РЕЗЮМЕ · РОЛЬ-СПЕЦИФИЧНАЯ ОЦЕНКА':'МАҚСАТТЫ ТҮЙІНДЕМЕЛЕР · РӨЛГЕ САЙ БАҒАЛАУ',
  'Целевое направление':'Мақсатты бағыт',
  'Цель −10% пока не достигается доступными изменениями.':'Қолжетімді өзгерістер арқылы −10% мақсатына әзірге жету мүмкін емес.',
  'Чат появится автоматически после вашего отклика на вакансию или приглашения от компании.':'Бос орынға өтінім жібергеннен немесе компаниядан шақыру алғаннан кейін чат автоматты түрде пайда болады.',
  'Чем занимается команда и какие задачи предстоят':'Команда немен айналысады және алда қандай міндеттер бар',
  'Черновик готов. Проверьте корректность условий и вариантов.':'Жоба нұсқасы дайын. Шарттар мен нұсқалардың дұрыстығын тексеріңіз.',
  'Черновик перенесён в ваш профиль. Проверьте настройки публикации.':'Жоба нұсқасы профиліңізге көшірілді. Жариялау параметрлерін тексеріңіз.',
  'Что в результате требует проверки? Не менее 10 символов.':'Нәтижеде нені тексеру керек? Кемінде 10 таңба.',
  'Что вам интересно? Какой опыт хотите использовать по-новому?':'Сізге не қызық? Қандай тәжірибені жаңаша қолданғыңыз келеді?',
  'Что видит работодатель':'Жұмыс беруші не көреді',
  'Что стоит уточнить':'Нені нақтылау керек',
  'Экспертная глубина':'Сарапшылық тереңдік',
  'Экспертная оценка сохранена':'Сарапшы бағасы сақталды',
  'Экспертная проверка вопросов, контролируемый пилот и наблюдение за решаемостью.':'Сұрақтарды сарапшы тексеруі, бақыланатын пилот және сұрақтардың шешілуін бақылау.',
  'Экспресс · 8 вопросов':'Экспресс · 8 сұрақ',
  'Экспресс-вопросы':'Экспресс сұрақтар',
  'Эталон прошёл':'Эталон тексеруден өтті',
  'Эти сведения увидит кандидат в вашем приглашении.':'Үміткер осы мәліметтерді шақыруыңызда көреді.',
  'Это разбор запроса. Вакансия не создана и не опубликована.':'Бұл — сұраныстың талдауы. Бос орын жасалмады және жарияланбады.',
  'Это результат сверки на момент обработки документа. Текущий статус показан в профиле.':'Бұл — құжат өңделген сәттегі салыстырып тексеру нәтижесі. Ағымдағы мәртебе профильде көрсетілген.',
  'Этот документ уже загружен. Открыт существующий результат.':'Бұл құжат бұрын жүктелген. Бар нәтиже ашылды.',
  'Эффект зависит от выполнения плана и доступного рынка':'Әсер жоспардың орындалуына және қолжетімді нарыққа байланысты',
  'Я начинаю карьеру. Помоги выбрать направление и план первых шагов.':'Мансабымды енді бастаймын. Бағыт пен алғашқы қадамдар жоспарын таңдауға көмектес.',
  'Явно оценённые навыки через запятую':'Нақты бағаланған дағдыларды үтірмен бөліңіз',
  'автотестов':'автотест',
  'в месяц':'айына',
  'в месяц ·':'айына ·',
  'вакансий готовы к проверке и загрузке':'бос орын тексеруге және жүктеуге дайын',
  'вакансий требуют проверки · ориентир':'бос орын тексеруді қажет етеді · бағдар',
  'видимыми.':'көрінетін.',
  'возможностей с единственным пробелом ·':'тек бір олқылығы бар мүмкіндік ·',
  'вознаграждение':'сыйақы',
  'гибрид':'аралас',
  'грейд подтверждён':'деңгей расталды',
  'демонстрационные записи':'демонстрациялық жазбалар',
  'дн.':'күн',
  'дней':'күн',
  'должность':'лауазым',
  'за пределами рынка':'нарық шегінен тыс',
  'завершённых наблюдений · нижняя граница':'аяқталған бақылау · төменгі шек',
  'заданий':'тапсырма',
  'из':'ішінен',
  'из 100':'100 ішінен',
  'из 3':'3 ішінен',
  'или выберите файлы на устройстве':'немесе құрылғыдан файлдарды таңдаңыз',
  'кандидатов в поиске':'іздеудегі үміткер',
  'кандидатов в снимке ·':'деректер кесіндісіндегі үміткер ·',
  'кандидатов для сравнения':'салыстыруға арналған үміткер',
  'квалификацию целевой роли':'мақсатты рөлдің біліктілігін',
  'комментариев':'пікір',
  'которая ищет вас':'сізді іздеп жүрген',
  'лет · от':'жыл · бастап',
  'лет опыта':'жыл тәжірибе',
  'медиана':'медиана',
  'медиана ожиданий':'күтілімдер медианасы',
  'минут':'минут',
  'мс':'мс',
  'мс.':'мс.',
  'назначений · незаполнено мест:':'тағайындау · толтырылмаған орын:',
  'направление':'бағыт',
  'начало работы':'жұмыстың басталуы',
  'не прикреплено':'тіркелмеген',
  'не указаны':'көрсетілмеген',
  'недели':'апта',
  'нет пробелов по стеку':'стек бойынша олқылық жоқ',
  'нужно подтверждение грейда':'деңгейді растау қажет',
  'обучаемых параметров':'үйретілетін параметр',
  'объяснимое соответствие':'түсіндірілетін сәйкестік',
  'ограниченная выборка':'шектеулі іріктеме',
  'ожидается':'күтілуде',
  'ожидание в месяц':'айлық күтілім',
  'окончание работы':'жұмыстың аяқталуы',
  'опыт раскрыт по критериям роли':'тәжірибе рөл критерийлері бойынша сипатталды',
  'остались пробелы или противоречия':'олқылықтар немесе қайшылықтар қалды',
  'от':'бастап',
  'ответил':'жауап берді',
  'отзывов · источник обновлён':'пікір · дереккөз жаңартылды',
  'откликов':'өтінім',
  'отмечен отдельно. Каждый вопрос имеет один правильный ответ.':'бөлек белгіленген. Әр сұрақтың бір дұрыс жауабы бар.',
  'офис':'кеңсе',
  'по настоящее время':'қазіргі уақытқа дейін',
  'подтвердили навыки тестом':'дағдыларын тест арқылы растады',
  'подходящих специалистов с открытой зарплатой.':'жалақысы көрсетілген сәйкес маман.',
  'пока нет актуальных доказательств отдельных навыков':'жекелеген дағдылардың өзекті дәлелдері әзірге жоқ',
  'полный ограниченный снимок':'толық шектеулі деректер кесіндісі',
  'после окончания календарного месяца':'күнтізбелік ай аяқталғаннан кейін',
  'результат проверки':'тексеру нәтижесі',
  'решённых вопросов':'шешілген сұрақ',
  'с каждым фактом.':'әрбір фактпен бірге.',
  'синтетические записи':'синтетикалық жазбалар',
  'снимков.':'деректер кесіндісі.',
  'специалистов':'маман',
  'точечный прогноз не идентифицирован':'нүктелік болжам анықталмаған',
  'тыс.':'мың',
  'увольнение не указано':'жұмыстан шығу көрсетілмеген',
  'удал':'қашықтан',
  'удалённо':'қашықтан',
  'уровень':'деңгей',
  'формат работы':'жұмыс форматы',
  'экспертного диалога':'сарапшылық диалогтың',
  '● Ваш сценарий':'● Сіздің сценарийіңіз',
  '● Текущие условия':'● Ағымдағы шарттар',
  '🟩 Правильный вариант ·':'🟩 Дұрыс нұсқа ·',
  'Этапы интервью':'Сұхбат кезеңдері',
  'Эффект действий':'Әрекеттер әсері',
  'Автономия':'Дербестік',
  'Архив':'Мұрағат',
  '· демо':'· демо',
  '· Оспаривается':'· Даулы',
  '· доказательность':'· дәлелділік',
  '· диапазонов уровня:':'· деңгей аралықтары:',
  '· не более':'· ең көбі',
  '· ожидание выше бюджета':'· күтілетін жалақы бюджеттен жоғары',
  '· отклик на «':'· өтінім: «',
  'Проверить подпись и отзыв':'Қолтаңба мен кері қайтарылуын тексеру',
  'Ваш грейд не понижается':'Деңгейіңіз төмендетілмейді',
  'Ваше имя и контакты откроются только выбранной компании после согласия или отклика.':'Атыңыз бен байланыс деректеріңіз келісім бергеннен немесе өтінім жібергеннен кейін тек таңдалған компанияға ашылады.',
  'Ваши предыдущие диалоги':'Алдыңғы диалогтарыңыз',
  'Ваши приглашения':'Шақыруларыңыз',
  'Верификация компании не выполнена':'Компанияны растау орындалмаған',
  'Вернуть на доработку':'Қайта өңдеуге қайтару',
  'Версия:':'Нұсқа:',
  'Взаимодействие':'Өзара әрекеттесу',
  'Вознаграждение:':'Сыйақы:',
  'Вопросы готовятся и проходят отдельную проверку. Можно продолжать работу в кабинете.':'Сұрақтар дайындалып, бөлек тексеріледі. Кабинетте жұмысты жалғастыра беруге болады.',
  'Восстановим доступ.':'Қолжетімділікті қалпына келтіреміз.',
  'Все вакансии проверяются до сохранения. Если в строке ошибка, пакет не будет загружен частично.':'Барлық бос орын сақтау алдында тексеріледі. Жолда қате болса, пакет ішінара жүктелмейді.',
  'Вставка отмечена в журнале. Сигнал рассматривается вместе с решением и пояснениями.':'Қою әрекеті журналда белгіленді. Сигнал шешіммен және түсініктемелермен бірге қарастырылады.',
  'Всё начинается с документа':'Барлығы құжаттан басталады',
  'Вы ещё не открывали контакты компаниям.':'Сіз әлі компанияларға байланыс деректеріңізді ашқан жоқсыз.',
  'Вы можете закрыть доступ компании независимо от статуса предложения. Уже полученную компанией копию контактов сервис отозвать не может.':'Ұсыныстың мәртебесіне қарамастан компанияға берілген қолжетімділікті жаба аласыз. Компания алған байланыс деректерінің көшірмесін сервис кері қайтара алмайды.',
  'Вы открыли контакты этой компании. Можно продолжить общение.':'Осы компанияға байланыс деректеріңізді аштыңыз. Әңгімені жалғастыруға болады.',
  'Выберите вакансию Talantix для каждой вакансии платформы.':'Платформаның әр бос орнына сәйкес Talantix бос орнын таңдаңыз.',
  'Выберите вакансию и отправьте задачу заинтересованным кандидатам.':'Бос орынды таңдап, қызығушылық білдірген үміткерлерге тапсырма жіберіңіз.',
  'Выберите источник':'Дереккөзді таңдаңыз',
  'Выберите направление':'Бағытты таңдаңыз',
  'Выберите направление и начните с восьми вопросов.':'Бағытты таңдап, сегіз сұрақтан бастаңыз.',
  'Выберите одно резюме: его поля, источники и исправления сохраняются отдельно.':'Бір түйіндемені таңдаңыз: оның өрістері, дереккөздері мен түзетулері бөлек сақталады.',
  'Выберите предложение':'Ұсынысты таңдаңыз',
  'Выбрать документы':'Құжаттарды таңдау',
  'Выйти на всех устройствах':'Барлық құрылғыда жүйеден шығу',
  'Выписка из трудовой':'Еңбек кітапшасынан үзінді',
  'Выписка не распознана':'Үзінді танылмады',
  'Выписка:':'Үзінді:',
  'Выполнение остановлено:':'Орындау тоқтатылды:',
  'Выполняем…':'Орындап жатырмыз…',
  'Ваши вакансии и потребности':'Бос орындарыңыз бен қажеттіліктеріңіз',
  'Ваша карьера. Ваш ход.':'Сіздің мансабыңыз. Сіздің қадамыңыз.',
  'Для этого ранее созданного профиля действует историческая оценка. Загрузите отдельное резюме или создайте новую цель, чтобы получить роль-специфичный тест.':'Бұрын жасалған осы профильге тарихи бағалау қолданылады. Рөлге арналған тест алу үшін бөлек түйіндеме жүктеңіз немесе жаңа мақсат жасаңыз.',
 },
 'uz':{
  '· не более':'· ko‘pi bilan',
  'Выберите направление и начните с восьми вопросов.':'Yo‘nalishni tanlang va sakkizta savoldan boshlang.',
  'Выпустить подписанный паспорт':'Imzolangan pasportni chiqarish',
  'Действие доступно и без опубликованной вакансии.':'Bu amal vakansiya e’lon qilinmagan bo‘lsa ham mavjud.',
  'До трёх направлений карьеры. Для каждого — свой тест и своя выдача вакансий.':'Uchtagacha karyera yo‘nalishi. Har biri uchun alohida test va vakansiyalar ro‘yxati.',
  'ИНТЕГРАЦИИ':'INTEGRATSIYALAR',
  'ИТ / финтех / образование':'IT / fintex / ta’lim',
 },
 'az':{
  'Выберите направление и начните с восьми вопросов.':'İstiqaməti seçin və səkkiz sualdan başlayın.',
  'Дисциплина':'İntizam',
  'До трёх направлений карьеры. Для каждого — свой тест и своя выдача вакансий.':'Üçədək karyera istiqaməti. Hər biri üçün ayrıca test və vakansiya siyahısı.',
  'ИНТЕГРАЦИИ':'İNTEQRASİYALAR',
 },
 'be':{
  'Зарплата от, ₽ / месяц':'Зарплата ад, ₽ / месяц',
  'Загрузите каталог: будут прочитаны источники кандидатов и вакансии Talantix, без изменения данных в ATS.':'Загрузіце каталог: будуць прачытаныя крыніцы кандыдатаў і вакансіі Talantix без змены даных у ATS.',
  'Доступ разрешён вами':'Доступ дазволены вамі',
  'Доступен в подборе':'Даступны ў падборы',
  'Для подбора также нужен действующий подтверждённый грейд. Контакты останутся закрытыми.':'Для падбору таксама патрэбны дзейны пацверджаны ўзровень. Кантакты застануцца закрытымі.',
  'Если вы участник ФСП':'Калі вы ўдзельнік ФСП',
  'Добровольная сверка должностей и дат с сохранённым резюме. При выявленном расхождении показы приостанавливаются до исправления. Можно загрузить PDF или читаемый скан.':'Добраахвотная зверка пасад і дат з захаваным рэзюмэ. Пры выяўленым разыходжанні паказы прыпыняюцца да выпраўлення. Можна загрузіць PDF або чытэльны скан.',
  '· ваш выбор':'· ваш выбар',
  '· демо':'· дэма',
  '· день':'· дзень',
  '· диапазонов уровня:':'· дыяпазонаў узроўню:',
  'ВАША КОМАНДА НАЧИНАЕТСЯ С ТАЛАНТА':'ВАША КАМАНДА ПАЧЫНАЕЦЦА З ТАЛЕНТУ',
  'Вакансии связаны. Согласованные отклики будут передаваться в Talantix.':'Вакансіі звязаныя. Узгодненыя адгукі будуць перадавацца ў Talantix.',
  'Ваш ФСП ID':'Ваш ФСП ID',
  'Ваш разбор':'Ваш разбор',
  'Ваши отклики':'Вашы адгукі',
  'Время для новой задачи':'Час для новай задачы',
  'Время истекло':'Час скончыўся',
  'Время ответа API':'Час адказу API',
  'Все':'Усе',
  'Все вакансии':'Усе вакансіі',
  'Вы':'Вы',
  'Выберите вакансию Talantix для каждой вакансии платформы.':'Выберыце вакансію Talantix для кожнай вакансіі платформы.',
  'Выберите вакансию и отправьте задачу заинтересованным кандидатам.':'Выберыце вакансію і адпраўце задачу зацікаўленым кандыдатам.',
  'Выписка из трудовой':'Выпіска з працоўнай кніжкі',
  'Выписка не распознана':'Выпіска не распазнаная',
  'Выписка:':'Выпіска:',
  'Выполнение остановлено:':'Выкананне спынена:',
  'Выполняем…':'Выконваем…',
  'Выпустить подписанный паспорт':'Выдаць падпісаны пашпарт',
  'Гибрид':'Гібрыд',
  'Горизонт поиска':'Гарызонт пошуку',
  'Гостевая сессия действует 30 минут. Профиль приватен.':'Гасцявая сесія дзейнічае 30 хвілін. Профіль прыватны.',
  'Готов к прохождению':'Гатовы да праходжання',
  'Готовим вопросы':'Рыхтуем пытанні',
  'Готовим и проверяем…':'Рыхтуем і правяраем…',
  'Готовим черновик для экспертной проверки…':'Рыхтуем чарнавік для экспертнай праверкі…',
  'Грейд':'Узровень',
  'ДЕМО-ПРОФИЛЬ':'ДЭМА-ПРОФІЛЬ',
  'ДИАЛОГ НАЧИНАЕТСЯ С ПРОЗРАЧНОСТИ':'ДЫЯЛОГ ПАЧЫНАЕЦЦА З ПРАЗРЫСТАСЦІ',
  'Дата':'Дата',
  'Диагностика и восстановление':'Дыягностыка і аднаўленне',
  'Для исправления измените резюме либо загрузите актуальную выписку. Удаление файла само по себе не снимает выявленное расхождение.':'Для выпраўлення змяніце рэзюмэ або загрузіце актуальную выпіску. Выдаленне файла само па сабе не ліквідуе выяўленае разыходжанне.',
  'Добавить вакансию':'Дадаць вакансію',
  'Есть PDF вакансии?':'Ёсць PDF вакансіі?',
  'Есть несоответствие':'Ёсць неадпаведнасць',
  'Есть различия в требованиях':'Ёсць адрозненні ў патрабаваннях',
  'Есть различия с потребностью':'Ёсць адрозненні з патрэбай',
  'Есть расхождения':'Ёсць разыходжанні',
  'Есть структурное сходство с другим решением. Это сигнал для обсуждения авторства, не обвинение и не автоматическое снижение оценки.':'Ёсць структурнае падабенства з іншым рашэннем. Гэта сігнал для абмеркавання аўтарства, а не абвінавачанне ці аўтаматычнае зніжэнне ацэнкі.',
  'Ещё не опубликован в подборе':'Яшчэ не апублікаваны ў падборы',
  'Загружаем…':'Загружаем…',
  'Загрузить или проверить выписку':'Загрузіць або праверыць выпіску',
  'Закрыта':'Закрыта',
  'Зарплата известна до первого сообщения.':'Зарплата вядомая да першага паведамлення.',
  'Засчитано':'Залічана',
  'Защита авторства и AI-assisted engineering':'Абарона аўтарства і AI-assisted engineering',
  'Здесь появятся сообщения по опубликованным вакансиям.':'Тут з’явяцца паведамленні па апублікаваных вакансіях.',
  'ИНТЕГРАЦИИ':'ІНТЭГРАЦЫІ',
  'ИТ / финтех / образование':'ІТ / фінтэх / адукацыя',
 },
}


def core_catalog(language, source):
 column=list(NAMES).index(language)+1
 result={parts[0]:parts[column] for line in CORE_COPY.strip().splitlines()
         if (parts:=line.split('|'))[0] in source}
 result.update({key:value for key,value in LANGUAGE_REVIEWED.get(language,{}).items()if key in source})
 result.update({key:values[language] for key,values in DECISION_COPY.items()if key in source and language in values})
 result.update({key:values[language] for key,values in FINALIZATION_COPY.items()if key in source and language in values})
 result.update({key:value for key,value in AGENT_REVIEWED.get(language,{}).items()if key in source})
 return result


def problems(source, value, language):
 """Conservative structural checks, not certification of semantic quality."""
 errors=[]
 if not isinstance(value,str) or not value.strip():return ['empty/non-string']
 alphabet_source=source;alphabet_value=value
 for identifier in CYRILLIC_IDENTIFIERS:
  alphabet_source=alphabet_source.replace(identifier,'')
  alphabet_value=alphabet_value.replace(identifier,'')
 # A source copy can be legitimate only for text containing no Cyrillic.
 reviewed=core_catalog(language,{source:source})
 if value==source and re.search('[А-Яа-яЁё]',alphabet_source) and reviewed.get(source)!=value:
  errors.append('untranslated source')
 if Counter(re.findall(r'\d+(?:[.,]\d+)?',source))!=Counter(re.findall(r'\d+(?:[.,]\d+)?',value)):
  errors.append('numbers changed')
 pattern=r'\$\{[^}]+\}|\{\{[^}]+\}\}|\{[A-Za-z_][\w.]*\}|%[sd]'
 if Counter(re.findall(pattern,source))!=Counter(re.findall(pattern,value)):errors.append('placeholders changed')
 for term in PROTECTED_TERMS:
  if term in source and term not in value:errors.append('technical term missing: '+term)
 operators=r'[≤≥<>=%₽]|→|\+\s*(?=\d|$)'
 if Counter(re.findall(operators,source))!=Counter(re.findall(operators,value)):
  errors.append('operators/currency symbols changed')
 if re.search(r'[\u3400-\u9fff]',value):errors.append('unexpected CJK text')
 if language in ('kk','be')and re.search(r'[А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІіЎў]+[A-Za-z]+|[A-Za-z]+[А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІіЎў]+',value):
  errors.append('mixed alphabets within a word')
 for number,ru_pattern in {3:r'три|трёх|трех',7:r'семь|семи',8:r'восемь|восьми'}.items():
  if re.search(r'\b('+ru_pattern+r')\b',source,re.I)and not re.search(r'\b('+WRITTEN_NUMBERS[language][number]+r'|'+str(number)+r')\b',value,re.I):
   errors.append('written numeral changed: '+str(number))
 if language in ('en','uz','az') and re.search('[А-Яа-яЁё]',alphabet_value):
  errors.append('unexpected Cyrillic')
 if language=='be' and re.search('[иИщЩъЪ]',value.replace('ФСП','')):errors.append('Russian-only letters')
 if language=='kk' and re.search('[А-Яа-яЁё]',alphabet_source) and not re.search('[А-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІі]',alphabet_value):
  errors.append('Kazakh Cyrillic required')
 return errors


def write_qa_status(source, language, catalog):
 """An explicit distinction between reviewed copy and machine-generated drafts."""
 path=FOLDER/'qa-status.json'
 status=json.loads(path.read_text(encoding='utf-8'))if path.exists()else{'schema_version':1,'languages':{}}
 reviewed=core_catalog(language,source)
 checked=[key for key,value in reviewed.items()if catalog.get(key)==value]
 invalid=[key for key,value in catalog.items()if key in source and problems(source[key],value,language)]
 status['languages'][language]={
  'source_sha256':hashlib.sha256(json.dumps(source,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest(),
  'catalog_sha256':hashlib.sha256(json.dumps(catalog,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest(),
  'source_key_count':len(source),'catalog_key_count':len(catalog),
  'missing_key_count':len(set(source)-set(catalog)),
  'exact_keyset':set(catalog)==set(source),
  'structural_invalid_keys':invalid,
  'semantically_reviewed_keys':checked,
  'critical_expected_keys':list(reviewed),
  'critical_ready':set(checked)==set(reviewed)and set(catalog)==set(source)and not invalid,
  'machine_translated_key_count':len([key for key in catalog if key in source and key not in checked]),
  'semantic_ready':set(checked)==set(source)and not invalid,
  'translation_status':'agent_reviewed_static_catalog' if set(checked)==set(source)and not invalid else 'machine_assisted_draft',
  'independent_human_review':False,
  'review_scope':'Listed keys have been reviewed by the agent; independent human linguistic review is not claimed.',
  'updated_at':datetime.now(timezone.utc).isoformat(),
 }
 path.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def synchronize_keys(source,language,catalog):
 # Removed UI keys are archived, preserving translations from earlier drafts.
 extra={key:value for key,value in catalog.items()if key not in source}
 if extra:
  path=FOLDER/'qa-status.json'
  status=json.loads(path.read_text(encoding='utf-8'))if path.exists()else{'schema_version':1,'languages':{}}
  status.setdefault('retired_translations',{}).setdefault(language,{}).update(extra)
  path.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 return {key:value for key,value in catalog.items()if key in source}

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--limit-batches',type=int,default=0)
 parser.add_argument('--languages',nargs='+',choices=list(NAMES),default=['en','kk'])
 parser.add_argument('--model',default='qwen3:8b')
 parser.add_argument('--batch-size',type=int,default=12)
 parser.add_argument('--core-only',action='store_true')
 parser.add_argument('--validate-only',action='store_true')
 args=parser.parse_args()
 if args.batch_size<1:parser.error('--batch-size must be positive')
 source=json.loads((FOLDER/'ru.json').read_text(encoding='utf-8'));batches_done=0
 with httpx.Client(timeout=120)as client:
  for lang in args.languages:
   glossary=GLOSSARY[lang]
   path=FOLDER/(lang+'.json');catalog=json.loads(path.read_text(encoding='utf-8'))if path.exists()else{}
   if args.validate_only:
    invalid={k:problems(source[k],v,lang)for k,v in catalog.items()if k in source and problems(source[k],v,lang)}
    print(json.dumps({'language':lang,'keys':len(catalog),'total':len(source),'missing':len(set(source)-set(catalog)),
                     'extra':len(set(catalog)-set(source)),'invalid':invalid},ensure_ascii=False),flush=True)
    continue
   catalog=synchronize_keys(source,lang,catalog)
   reviewed=core_catalog(lang,source)
   catalog.update(reviewed)
   path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   write_qa_status(source,lang,catalog)
   if args.core_only:
    print(json.dumps({'language':lang,'reviewed_core':len(reviewed),'keys':len(catalog),'total':len(source)}),flush=True)
    continue
   missing=[k for k in source if k not in reviewed and problems(source[k],catalog.get(k),lang)]
   for start in range(0,len(missing),args.batch_size):
    keys=missing[start:start+args.batch_size];ids=[str(i)for i in range(len(keys))]
    phrases={id:source[key]for id,key in zip(ids,keys)}
    schema={'type':'object','properties':{id:{'type':'string'}for id in ids},'required':ids,'additionalProperties':False}
    prompt='Translate FROM RUSSIAN INTO '+NAMES[lang].upper()+'. Every output string MUST be written in '+NAMES[lang]+', not Russian. Return a JSON object with exactly the same numeric IDs as the input. Each ID must contain the translation of its own source text; never shift or combine entries. Preserve numbers, operators, placeholders and proper names. Do not abbreviate, explain, invent or change technical facts. Use concise natural UI wording. '+glossary
    prompt+=' Preserve fragment punctuation and exact numeric values, currency and proper names. Never convert RUB/rubles to local currency. Technical abbreviations stay unchanged. Kazakh output uses Cyrillic; Uzbek and Azerbaijani use Latin. Do not transliterate Russian words instead of translating.'
    request={'model':args.model,'stream':False,'think':False,'format':schema,'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps(phrases,ensure_ascii=False)+'\n/no_think'}],'options':{'temperature':0,'num_ctx':8192,'num_predict':1536},'keep_alive':'10m'}
    accepted={};active_ids=ids.copy()
    for attempt in range(3):
     began=time.monotonic();data={}
     try:
      r=client.post('http://127.0.0.1:11434/api/chat',json=request);r.raise_for_status();data=r.json()
      output=json.loads(data['message']['content'])
      assert isinstance(output,dict)and set(output)==set(active_ids),'Missing or unexpected translation IDs'
      invalid=[]
      for id in active_ids:
       errors=problems(source[keys[int(id)]],output[id],lang)
       if errors:invalid.append((id,errors))
       else:accepted[id]=output[id]
      assert not invalid, json.dumps(invalid)
      break
     except (ValueError,AssertionError,httpx.HTTPError)as error:
      print(json.dumps({'language':lang,'batch_start':start,'attempt':attempt+1,'rejected':str(error)}),flush=True)
      if attempt==2:break
      active_ids=[id for id in ids if id not in accepted]
      request['format']={'type':'object','properties':{id:{'type':'string'}for id in active_ids},'required':active_ids,'additionalProperties':False}
      request['messages'][1]['content']=json.dumps({id:phrases[id]for id in active_ids},ensure_ascii=False)+'\n/no_think'
      request['messages'][0]['content']=prompt+' Previous output failed validation: '+str(error)+'. Correct these issues.'
    # Only validated keyed results are retained; gaps never receive Russian fallback.
    values=[accepted.get(id)for id in ids]
    catalog.update((k,v)for k,v in zip(keys,values)if v is not None)
    catalog.update(reviewed)
    path.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write_qa_status(source,lang,catalog)
    batches_done+=1;print(json.dumps({'language':lang,'keys':len(catalog),'total':len(source),'structurally_valid':sum(not problems(source[k],catalog.get(k),lang)for k in source),'seconds':round(time.monotonic()-began,2),'output_tokens':data.get('eval_count')}),flush=True)
    if args.limit_batches and batches_done>=args.limit_batches:return
if __name__=='__main__':main()
