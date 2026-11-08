"""Source-bound Russian strings owned by the compatibility patch itself."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from translations.loclib import parse_line,ROW,digest,validate,numeric_profile,escape_value

RELATIVE='localization/russian/zz_tbcp_bridge_l_russian.yml'
INPUTS=('translations/loclib.py','translations/memory/bridge.json')


def entries(generated,language):
    result={}
    for relative,text in generated.items():
        if not relative.startswith('localization/') or not relative.endswith('_l_'+language+'.yml'):
            continue
        if relative==RELATIVE:continue
        for line in text.splitlines():
            if not ROW.match(line):continue
            key,value,_=parse_line(line)
            if key in result:raise ValueError('Duplicate patch localization: '+key)
            result[key]=value
    return result


def render(english,native,memory):
    if set(memory)!=set(english):
        raise ValueError('Russian bridge keys changed; review translation source bindings')
    if set(native)-set(english):raise ValueError('Russian patch keys have no English source')
    output={}
    for key,en in english.items():
        row=memory[key];ru=row['ru']
        if row['en_sha256']!=digest(en):raise ValueError('Russian bridge English changed: '+key)
        if validate(en,ru) or numeric_profile(en)!=numeric_profile(ru):
            raise ValueError('Russian bridge structure or numbers changed: '+key)
        if key in native:
            if native[key]!=escape_value(ru):raise ValueError('Native Russian bridge disagrees: '+key)
        else:output[key]=ru
    text='l_russian:\n'+''.join(f' {key}:0 "{escape_value(ru)}"\n' for key,ru in sorted(output.items()))
    for line in text.splitlines()[1:]:parse_line(line)
    return text,{'source_keys':len(english),'native_keys':len(native),'translated_keys':len(output),
                 'source_bound':True,'standalone_translation_packs_required':False}


def integrate(root,generated):
    memory=json.loads((Path(root)/INPUTS[1]).read_text(encoding='utf-8'))
    text,report=render(entries(generated,'english'),entries(generated,'russian'),memory)
    generated[RELATIVE]=text
    return generated,report
