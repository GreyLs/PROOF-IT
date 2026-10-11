from pathlib import Path
from xml.sax.saxutils import escape
import datetime
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
ROOT=Path(__file__).resolve().parents[1]
def export_profile(profile:dict,path:Path):
    for face,filename in [('FSP','JetBrainsMono-Regular.ttf'),('FSPBold','JetBrainsMono-Bold.ttf')]:
        pdfmetrics.registerFont(TTFont(face,str(ROOT/'web/public/brand'/filename)))
    normal=ParagraphStyle('body',fontName='FSP',fontSize=9,leading=15,textColor=colors.HexColor('#1B1C21'))
    h1=ParagraphStyle('title',parent=normal,fontName='FSPBold',fontSize=23,leading=30,spaceAfter=18)
    h2=ParagraphStyle('sub',parent=normal,fontName='FSPBold',fontSize=13,leading=20,textColor=colors.HexColor('#402FFF'),spaceBefore=16,spaceAfter=8)
    flow=[Paragraph('ФСП / ТРАЕКТОРИЯ',h2),Paragraph(escape(profile.get('full_name') or profile['display_name']),h1)]
    def section(title,text):flow.extend([Paragraph(title,h2),Paragraph(escape(str(text)).replace('\n','<br/>'),normal)])
    method = 'разбор проекта и три индивидуальных кейса без кода' if str(profile.get('assessment_method','')).startswith('project-cases') else 'экспертный диалог по рассказу кандидата' if str(profile.get('assessment_method','')).startswith('expert-dialogue') else 'сценарные демонстрационные данные' if profile.get('synthetic') else 'историческая оценка профиля'
    section('Профессиональный профиль',f"Специализация: {profile.get('specialization') or 'Не указана'}\nПодтверждённый грейд: {profile.get('confirmed_grade') or 'Не подтверждён'}\nЗаявленный грейд: {profile.get('declared_grade','—')}\nОпыт: {profile.get('experience_years',0)} лет\nОценка опыта: {profile.get('test_score',0)} / 100\nОснование: {method}")
    section('Стек',', '.join(profile.get('skills',[])) or 'Не указан')
    section('Условия',f"Ожидаемая зарплата: {profile.get('expected_salary',0):,} ₽\nФормат работы: {profile.get('work_format','—')}")
    section('О себе',profile.get('about') or 'Не заполнено')
    if profile.get('soft_skills'):section('Заявленные софт-скиллы',', '.join(profile['soft_skills']))
    section('Контакты',f"Email: {profile.get('email') or 'Не указан'}\nТелефон: {profile.get('phone') or 'Не указан'}")
    section('История ФСП',{'not_linked':'История ФСП не связана. Отсутствие истории не препятствует подбору.','pending':'FSP ID указан пользователем и ожидает проверки.','mock_verified':'Демонстрационные синтетические достижения. Не реальная выгрузка ФСП.','verified':'Достижения подтверждены источником.'}.get(profile.get('fsp_status'),'История не указана'))
    flow.extend([Spacer(1,22),Paragraph('Профиль создан владельцем. При передаче PDF получатель увидит указанные контакты. Данные резюме не заменяют результаты экспертного диалога.',normal)])
    if profile.get('synthetic'):flow.append(Paragraph('ДЕМОНСТРАЦИОННЫЙ СИНТЕТИЧЕСКИЙ ПРОФИЛЬ',h2))
    def footer(c,doc):
        c.setFont('FSP',8);c.setFillColor(colors.HexColor('#777777'));c.drawString(42,25,f'ФСП · Траектория / {datetime.date.today().isoformat()}');c.drawRightString(550,25,str(doc.page))
    SimpleDocTemplate(str(path),pagesize=(595,842),rightMargin=45,leftMargin=45,topMargin=35,bottomMargin=45).build(flow,onFirstPage=footer,onLaterPages=footer)
