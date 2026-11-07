"""Small lossless-enough AST for structural audits, not a Victoria interpreter."""
from dataclasses import dataclass
from inspect_mod_overlap import TOKEN


@dataclass
class Field:
    key:str
    op:str
    value:object


def parse(text):
    tokens=[m.group() for m in TOKEN.finditer(text) if not m.group().startswith('#')]
    def scope(i,closing=False):
        result=[]
        while i<len(tokens):
            if tokens[i]=='}':
                if not closing:raise ValueError('Unexpected }')
                return result,i+1
            if tokens[i]=='{':
                value,i=scope(i+1,True);result.append(value);continue
            key=tokens[i];i+=1
            if i<len(tokens) and tokens[i] in {'=','?=','!=','==','<','>','<=','>='}:
                op=tokens[i];i+=1
                if i>=len(tokens):raise ValueError('Missing value: '+key)
                if tokens[i]=='{':value,i=scope(i+1,True)
                else:
                    value=tokens[i];i+=1
                    if value in {'rgb','hsv','hsv360','hex'} and i<len(tokens) and tokens[i]=='{':
                        literal,i=scope(i+1,True);value=(value,literal)
                result.append(Field(key,op,value))
            else:result.append(key)
        if closing:raise ValueError('Unclosed scope')
        return result,i
    return scope(0)[0]


def walk(items):
    for item in items:
        if isinstance(item,list):yield from walk(item)
        if isinstance(item,Field):
            yield item
            if isinstance(item.value,list):yield from walk(item.value)


def scalars(items):
    return {v.key:v.value for v in items if isinstance(v,Field) and isinstance(v.value,str)}


def top_spans(text):
    """Top-level scalar/block spans, retaining directives and source offsets."""
    tokens=[m for m in TOKEN.finditer(text) if not m.group().startswith('#')]
    out=[];i=0
    while i<len(tokens):
        if i+2>=len(tokens) or tokens[i+1].group()!='=':raise ValueError('Expected top-level assignment: '+tokens[i].group())
        start=i;raw_key=tokens[i].group();i+=2;block=tokens[i].group()=='{'
        if block:
            depth=1;i+=1
            while i<len(tokens) and depth:
                depth+=(tokens[i].group()=='{')-(tokens[i].group()=='}');i+=1
            if depth:raise ValueError('Unclosed definition '+raw_key)
        else:i+=1
        operation,key=raw_key.split(':',1) if ':' in raw_key else ('DEFINE',raw_key)
        out.append({'key':key,'operation':operation,'block':block,'start':tokens[start].start(),
                    'end':tokens[i-1].end(),'raw':text[tokens[start].start():tokens[i-1].end()]})
    return out
