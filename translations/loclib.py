"""Paradox localization parsing, protected tokens, and Russian pack validation."""
from collections import Counter
from dataclasses import dataclass,asdict
import hashlib
import json
from pathlib import Path
import re
from decimal import Decimal

ROOT=Path(__file__).resolve().parents[1]
ROW=re.compile(r'^\s*([^\s:#][^\s:]*)\s*:\s*\d*\s*"')
HEADER=re.compile(r'^\s*l_([a-z_]+)\s*:')
MACRO=re.compile(r'\$[A-Za-z0-9_.|+=%:\-]+\$')
ICON=re.compile(r'@[A-Za-z0-9_]+!')
FORMAT=re.compile(r'#!|#[A-Za-z_]+')
CONCEPT=re.compile(r"Concept\(\s*'(?P<key>concept_[^']+)'\s*,\s*'(?P<label>(?:\\.|[^'])*)'\s*\)")

@dataclass(frozen=True)
class Entry:
    key:str
    value:str
    file:str
    line:int


def parse_line(line,recover=False):
    match=ROW.match(line)
    if not match:return None
    start=match.end();i=start;quotes=[]
    while i<len(line):
        if line[i]=='\\':i+=2;continue
        if line[i]=='"':quotes.append(i)
        i+=1
    if not quotes:return None
    first=quotes[0];tail=line[first+1:].strip();recovered=False
    if tail and not tail.startswith('#'):
        if not recover:raise ValueError('Unescaped quotes or trailing text')
        valid=[v for v in quotes if not line[v+1:].strip() or line[v+1:].lstrip().startswith('#')]
        if not valid:
            if match[1]=='bpm_je_guilty_four_civil_war' and 'The crimes of this guilty land' in line:
                return match[1],line[start:].rstrip(),True
            raise ValueError('Unclosed localization value')
        first=valid[-1];recovered=True
    return match[1],line[start:first],recovered


def load(directory,language,canonical_folder=False):
    directory=Path(directory)
    if canonical_folder:paths=list((directory/language).rglob('*.yml'))+list(directory.glob('*_l_'+language+'.yml'))
    else:paths=list(directory.rglob('*.yml'))
    paths.sort(key=lambda p:('replace' in p.relative_to(directory).parts,p.relative_to(directory).as_posix()))
    result={};issues=[];duplicates=[];files=[]
    for path in paths:
        raw=path.read_bytes()
        try:text=raw.decode('utf-8-sig')
        except UnicodeError:issues.append({'file':path.name,'issue':'encoding'});continue
        relative=path.relative_to(directory).as_posix()
        header=next((HEADER.match(v) for v in text.splitlines() if HEADER.match(v)),None)
        if not header or header[1]!=language:continue
        files.append(relative)
        if not raw.startswith(b'\xef\xbb\xbf'):issues.append({'file':relative,'issue':'missing_utf8_bom'})
        for number,line in enumerate(text.splitlines(),1):
            if not ROW.match(line):continue
            try:parsed=parse_line(line,recover=True)
            except ValueError as error:issues.append({'file':relative,'line':number,'issue':str(error)});continue
            if parsed is None:issues.append({'file':relative,'line':number,'issue':'unclosed'});continue
            key,value,recovered=parsed
            if recovered:issues.append({'file':relative,'line':number,'key':key,'issue':'unescaped_inner_quotes_recovered'})
            if key in result and result[key].value!=value:
                duplicates.append({'key':key,'first_file':result[key].file,'last_file':relative})
            result[key]=Entry(key,value,relative,number)
    return result,{'files':files,'issues':issues,'conflicting_duplicates':duplicates}


def tokens(value):
    """Return non-overlapping protected islands; retain full nested script calls."""
    result=[];i=0
    while i<len(value):
        char=value[i]
        if char=='[':
            depth=1;j=i+1
            while j<len(value) and depth:
                depth+=(value[j]=='[')-(value[j]==']');j+=1
            if not depth:result.append(('bracket',i,j,value[i:j]));i=j;continue
        match=MACRO.match(value,i) or ICON.match(value,i) or FORMAT.match(value,i)
        if match:
            raw=match.group();kind='macro' if raw.startswith('$') else 'icon' if raw.startswith('@') else 'format'
            if kind=='format' and raw!='#!' and match.end()<len(value) and value[match.end()]==';':
                end=match.end();depth=0
                while end<len(value):
                    char=value[end]
                    if char.isspace() and depth==0:break
                    depth+=(char=='[')-(char==']');end+=1
                result.append((kind,i,end,value[i:end]));i=end;continue
            result.append((kind,i,match.end(),raw));i=match.end();continue
        if char=='\\' and i+1<len(value) and value[i+1] in 'nrt':
            result.append(('escape',i,i+2,value[i:i+2]));i+=2;continue
        if char=='\\' and i+1<len(value) and value[i+1] in '[]\\':i+=2;continue
        i+=1
    return result


def normalize_bracket(value):
    value=CONCEPT.sub(lambda m:'Concept('+m['key']+')',value)
    plain=re.fullmatch(r'\[(concept_[A-Za-z0-9_]+)(?:\|[lUuE]+)?\]',value)
    if plain:return 'concept:'+plain[1]
    call=re.fullmatch(r'\[Concept\((concept_[A-Za-z0-9_]+)\)(?:\|[lUuE]+)?\]',value)
    if call:return 'concept:'+call[1]
    return value


def profile(value):
    return Counter((kind,normalize_bracket(raw) if kind=='bracket' else raw) for kind,_,_,raw in tokens(value))


def plain(value):
    items=tokens(value);out=[];last=0
    for _,start,end,_ in items:out.append(value[last:start]);last=end
    out.append(value[last:])
    return ''.join(out).strip()


def visible(value):
    return plain(value)+' '+' '.join(plain(match['label']) for match in CONCEPT.finditer(value))


def numeric_profile(value):
    text=visible(value)
    # English comma thousands and Russian space thousands denote the same value.
    text=re.sub(r'(?<!\d)[1-9]\d{0,2}(?:[, \u00a0\u202f]\d{3})+(?!\d)',
                lambda match:re.sub(r'[, \u00a0\u202f]','',match[0]),text)
    result=Counter()
    for match in re.finditer(r'(?<![A-Za-zА-Яа-я_])(?P<sign>[+＋−–—-]\s*)?(?P<number>\d+(?:[.,]\d+)?)',text):
        value=Decimal(match['number'].replace(',','.'))
        sign=(match['sign'] or '').strip()
        # A mathematical minus is unambiguous. Hyphens/en dashes can instead
        # separate range endpoints; a spaced prose dash is not a minus sign.
        preceding=text[:match.start()];before=preceding.rstrip()
        is_range=bool(preceding and (preceding[-1].isdigit() or preceding[-1]=='%'))
        attached=bool(match['sign'] and not match['sign'][-1].isspace())
        spaced_minus_context=not before or before[-1] in '(:=,;'
        if sign=='−' or (sign in {'–','—','-'} and not is_range and (attached or spaced_minus_context)):
            value=-value
        result[str(value.normalize())]+=1
    return result


def translatable(value):return bool(re.search(r'[A-Za-z]{2}',plain(value)))


def mask(value):
    items=tokens(value);out=[];last=0
    for number,(_,start,end,_) in enumerate(items):out.extend([value[last:start],f'__PH{number}__']);last=end
    out.append(value[last:])
    return ''.join(out),[raw for _,_,_,raw in items]


def marker_ids(value):return Counter(int(v) for v in re.findall(r'__PH(\d+)__',value))


def restore(template,protected):
    expected=Counter(range(len(protected)))
    if marker_ids(template)!=expected:raise ValueError('Translation changed placeholders')
    return re.sub(r'__PH(\d+)__',lambda m:protected[int(m[1])],template)


def validate(en,ru):
    if not ru.strip() and en.strip():return ['empty_translation']
    problems=[]
    a,b=profile(en),profile(ru)
    if a!=b:problems.append('protected_tokens_changed')
    if re.search(r'__PH\d+__',ru):problems.append('unresolved_placeholder')
    if '\ufffd' in ru:problems.append('unicode_replacement_character')
    if len(en)>120 and len(visible(en))>60 and len(visible(ru))<len(visible(en))*.25:problems.append('suspicious_truncation')
    return problems


def escape_value(value):
    value=value.replace('\r\n','\\n').replace('\n','\\n').replace('\r','')
    out=[];slashes=0
    for char in value:
        if char=='"' and slashes%2==0:out.append('\\')
        out.append(char);slashes=slashes+1 if char=='\\' else 0
    if slashes%2:out.append('\\')
    return ''.join(out)


def write_localization(path,entries):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    text='l_russian:\n'+'\n'.join(f' {key}:0 "{escape_value(value)}"' for key,value in sorted(entries.items()))+'\n'
    path.write_text(text,encoding='utf-8-sig',newline='\n')
    # Test the exact emitted bytes, not only the in-memory dictionary.
    raw=path.read_bytes();assert raw.startswith(b'\xef\xbb\xbf')
    for line in text.splitlines()[1:]:parse_line(line)


def digest(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()


def json_write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
