"""Prepare reproducible qualification contracts without an inference dependency."""
from intelligence.certification import prepare
VERSION='certification-3.0.0'

def generate(payload):
    return prepare(payload)

def controlled_questions(resume):
    from intelligence import professional as cat
    contract=prepare({'resume':resume,'seed':42})['contract']
    questions=[]
    while len(questions)<10 and (q:=cat.next_item(contract)) is not None:
        questions.append({'prompt':q['prompt'],'options':q['options'],'correct':[q['correct']]})
        contract=cat.step({'contract':contract,'question_id':q['id'],'answer':q['correct'],'elapsed_ms':5000})['contract']
    return questions

def valid(question):
    return bool(question.get('prompt')) and len(question.get('options',[]))==4 and len(question.get('correct',[]))==1
