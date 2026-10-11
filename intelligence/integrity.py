"""Task-scoped structural evidence for human review, with template subtraction."""
from __future__ import annotations
import hashlib,io,keyword,re,tokenize
VERSION='integrity-3.0.0'
KEYWORDS=set(keyword.kwlist)|set('function return if else for while const let var new of in true false null undefined SELECT FROM WHERE GROUP BY ORDER JOIN LEFT ON AS WITH SUM COUNT COALESCE PARTITION ROW_NUMBER OVER solve map filter reduce sorted range len int str list dict set print'.split())

def _tokens(code,language):
    if language=='python':
        try:
            raw=[(t.type,t.string) for t in tokenize.generate_tokens(io.StringIO(code).readline) if t.type not in (tokenize.COMMENT,tokenize.NL,tokenize.NEWLINE,tokenize.ENDMARKER,tokenize.ENCODING)]
        except (tokenize.TokenError,IndentationError):raw=[]
        out=[]
        for kind,value in raw:
            if kind==tokenize.NAME:out.append(value if value in KEYWORDS else 'ID')
            elif kind==tokenize.NUMBER:out.append('NUM')
            elif kind==tokenize.STRING:out.append('STR')
            elif kind==tokenize.INDENT:out.append('{')
            elif kind==tokenize.DEDENT:out.append('}')
            else:out.append(value)
        return out
    # Consume literals before comment patterns; comment-looking text in a string
    # must not erase the following SQL or TypeScript program.
    pattern=r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\x60(?:\\.|[^\x60\\])*\x60|/\*[\s\S]*?\*/|//[^\n]*|--[^\n]*|[A-Za-z_$][\w$]*|\d+(?:\.\d+)?|===|!==|=>|<=|>=|!=|==|&&|\|\||[^\s]"""
    out=[]
    for value in re.findall(pattern,code):
        if value.startswith(('/*','//','--')):continue
        if value[0] in ('"', "'", chr(96)):out.append('STR')
        elif value[0].isdigit():out.append('NUM')
        elif re.match(r'[A-Za-z_$]',value):out.append(value.upper() if value in KEYWORDS or value.upper() in KEYWORDS else 'ID')
        else:out.append(value)
    return out

def _hashes(tokens):
    grams=[int(hashlib.sha256(' '.join(tokens[i:i+5]).encode()).hexdigest()[:24],16) for i in range(max(0,len(tokens)-4))]
    picked=set()
    for i in range(max(1,len(grams)-3)):
        window=grams[i:i+4]
        if window:picked.add(format(min(window),'024x'))
    return picked

def fingerprint(payload):
    code=payload['code'];language=payload.get('language','python')
    if not isinstance(code,str) or len(code)>20000 or language not in ('python','sql','typescript','text'):raise ValueError('code')
    tokens=re.findall(r'[\w]+',code.casefold()) if language=='text' else _tokens(code,language)
    hashes=_hashes(tokens)
    base=_hashes(_tokens(payload.get('template',''),language)) if payload.get('template') and language!='text' else set()
    hashes-=base
    return {'version':VERSION,'language':language,'units':len(tokens),'hashes':{v:1 for v in sorted(hashes)},'template_units_removed':len(base),'fingerprints':len(hashes)}

def compare(payload):
    candidate=payload['fingerprint'];references=payload.get('references',[])[:500]
    a=set(candidate['hashes']);matches=[]
    for index,ref in enumerate(references):
        reference=ref.get('fingerprint',ref)
        if reference.get('version')!=VERSION or candidate['language']!=reference['language']:continue
        b=set(reference['hashes']);common=a&b
        containment=len(common)/max(1,min(len(a),len(b)))
        jaccard=len(common)/max(1,len(a|b))
        enough=min(candidate['units'],reference['units'])>=35 and min(len(a),len(b))>=6
        matches.append((containment,jaccard,len(common),enough,index))
    best=max(matches,default=(0,0,0,False,-1))
    recommended=best[3] and best[0]>=.85
    return {'version':VERSION,'references':len(matches),'similarity':round(best[0],5),'jaccard':round(best[1],5),'shared_fingerprints':best[2],
            'review_recommended':recommended,'automatic_penalty':False,'minimum_units':35,'measured_units':candidate['units'],
            'method':'normalized-token-winnowing-containment','template_subtracted':bool(candidate.get('template_units_removed')),
            'decision':'review' if recommended else 'no_structural_alert'}
