"""Explicit law-field composition for pinned TE/BPM inputs, not generic deep merge."""
from decimal import Decimal, InvalidOperation
from inspect_mod_overlap import TOKEN

LISTS = {'unlocking_laws', 'disallowing_laws', 'unlocking_technologies', 'requires_law_or'}
EFFECTS = {'on_activate', 'on_deactivate', 'on_enact'}
TRIGGERS = {'can_enact', 'is_visible', 'can_impose'}
MODIFIERS = {'modifier', 'institution_modifier', 'acceptance_modifier'}


def fields(text):
    tokens = [m for m in TOKEN.finditer(text) if not m.group().startswith('#')]
    result=[]; i=0
    while i < len(tokens):
        start=i
        if i+2>=len(tokens) or tokens[i+1].group()!='=':
            raise ValueError('Expected assignment near '+tokens[i].group())
        key=tokens[i].group(); i+=2
        opening=i
        if tokens[i].group()=='{':
            depth=1; i+=1
            while i<len(tokens) and depth:
                depth += (tokens[i].group()=='{')-(tokens[i].group()=='}'); i+=1
            if depth: raise ValueError('Unclosed field '+key)
            value=text[tokens[opening].end():tokens[i-1].start()]
            block=True
        else:
            value=tokens[i].group(); i+=1; block=False
            if value in {'hsv','hsv360','rgb','hex'} and i<len(tokens) and tokens[i].group()=='{':
                depth=1;i+=1
                while i<len(tokens) and depth:
                    depth+=(tokens[i].group()=='{')-(tokens[i].group()=='}');i+=1
                if depth:raise ValueError('Unclosed typed literal '+key)
                value=text[tokens[opening].start():tokens[i-1].end()]
        result.append({'key':key,'block':block,'value':value})
    return result


def norm(value):
    return ' '.join(m.group() for m in TOKEN.finditer(value) if not m.group().startswith('#'))


def emit(items):
    return '\n'.join('\t'+v['key']+' = '+('{\n'+v['value'].strip()+'\n\t}' if v['block'] else v['value']) for v in items)+'\n'


def modifier_sum(old, extra, conversion_policy=None):
    out=fields(old); index={v['key']:i for i,v in enumerate(out)}
    if len(index)!=len(out): raise ValueError('Repeated modifier in base')
    for item in fields(extra):
        if item['key'] not in index:
            index[item['key']]=len(out);out.append(item);continue
        previous=out[index[item['key']]]
        if previous['block'] or item['block']:raise ValueError('Symbolic modifier '+item['key'])
        try:
            value=Decimal(previous['value'])+Decimal(item['value'])
            previous['value']=format(value,'f')
        except InvalidOperation:
            if previous['value']!=item['value']:
                if item['key'].startswith('country_allow_conversion_') and item['key'].endswith('_bool') and conversion_policy:
                    if conversion_policy=='incoming':previous['value']=item['value']
                else:raise ValueError('Conflicting modifier '+item['key'])
    return emit(out)


def inject(body, addition, overrides=(), conversion_policy=None):
    out=fields(body); index={v['key']:i for i,v in enumerate(out)}
    if len(index)!=len(out):raise ValueError('Repeated law field needs manual resolution')
    for item in fields(addition):
        key=item['key']
        if key not in index:index[key]=len(out);out.append(item);continue
        previous=out[index[key]]
        if previous['block']!=item['block']:raise ValueError('Different field shape '+key)
        if key in MODIFIERS:
            previous['value']=modifier_sum(previous['value'],item['value'],conversion_policy)
        elif key in LISTS:
            words=norm(previous['value']).split(); more=norm(item['value']).split()
            if any(x in '{}=' for x in words+more):raise ValueError('Non-list '+key)
            previous['value']='\n'.join(dict.fromkeys(words+more))
        elif key in EFFECTS or key in TRIGGERS:
            # Effects execute in source order; triggers are an implicit AND.
            previous['value']+='\n'+item['value']
        elif key in overrides:
            previous['value']=item['value']
        elif norm(previous['value'])!=norm(item['value']):
            raise ValueError('Unreviewed conflicting law field '+key)
    return emit(out)
