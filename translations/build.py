"""Build separate Russian packs with explicit human/draft provenance and token QA."""
from collections import Counter,defaultdict
from pathlib import Path
import argparse
import hashlib
import json
import re
import uuid

from loclib import ROOT,profile,plain,translatable,mask,restore,validate,CONCEPT,normalize_bracket,tokens,digest,json_write,write_localization,numeric_profile

DATA=ROOT/'translations/data'
WORK=ROOT/'runtime/translations'
ALLOWED_LATIN={'Better Politics Mod','Quanta cura','Immortale dei','Rerum novarum','Graves de communi re',
               'Qui Pro Domina Justitia Sequitur','BP','II','III','IV','V','VI','VII','VIII','IX','X',
               'IBM','AMD','Intel','NVIDIA','Apple','Microsoft','Google','SpaceX','NASA','ESA','CERN',
               'Boeing','Airbus','Toyota','Tesla','Samsung','Sony','Nokia','Ericsson','NATO','GATT',
               'UNESCO','UNICEF','OpenAI','Wi-Fi','Bluetooth','USB','HTTP','HTTPS','TCP/IP','IP','DNA','RNA',
               'NASDAQ','NYSE','ISO','IEC','Linux','Unix','Android','iOS','Windows','macOS'}
UI={'Yes':'Да','No':'Нет','Go':'Перейти','On':'Включено','Off':'Отключено','Cancel':'Отмена','Back':'Назад',
    'Close':'Закрыть','Open':'Открыть','Next':'Далее','Previous':'Назад','Confirm':'Подтвердить','Add':'Добавить',
    'Remove':'Удалить','Save':'Сохранить','Load':'Загрузить','Enable':'Включить','Disable':'Отключить',
    'UN':'ООН','GDP':'ВВП','AI':'ИИ','Research':'Исследования','Construction':'Строительство',
    'Intelligence Capacity':'Разведывательные возможности','Human Augmentation':'Усовершенствование человека'}
SOURCE_REPAIRS={
    'concept_bpm_ig_is_state_institutional_desc':lambda s:s.replace("GetLawType(law_theocracy')","GetLawType('law_theocracy')").replace("GetLawType(law_corporatized_unions')","GetLawType('law_corporatized_unions')"),
    'concept_bpm_ig_is_proletarian_desc':lambda s:s.replace("GetLawType(law_corporatized_unions')","GetLawType('law_corporatized_unions')"),
    'concept_bpm_ig_is_radical_socialist_desc':lambda s:re.sub(r"(?<!\[)Concept\('concept_bpm_ig_is_anarchist'", "[Concept('concept_bpm_ig_is_anarchist'",s),
    'bpm_law_effect_tt_repeatable_different_in_collectivized_agriculture':lambda s:s+'#!',
    'tooltip_bpm_ig_is_proletarian_socialist':lambda s:s.replace('tooltip_bpm_ig_is_proletarian_socialist', 'concept_bpm_ig_is_proletarian_socialist'),
}


def source_for_validation(key,value):
    if key in SOURCE_REPAIRS:value=SOURCE_REPAIRS[key](value)
    # Source has an unquoted concept label; the repair retains its target.
    if key in {'RIGIDITY','BPM_CABINET_SYNERGY_FROM_RIGIDITY','country_synergy_from_rigidity_add','country_synergy_from_rigidity_add_desc'}:
        value=value.replace("Concept('concept_bpm_political_stability', concept_bpm_political_stability)",
                            "Concept('concept_bpm_political_stability', 'Political Stability')")
    return value


def load_cache():
    result={};path=WORK/'offline-cache.jsonl'
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            try:item=json.loads(line)
            except json.JSONDecodeError:continue
            result[item['id']]=item
    return result


def overrides(prefix):
    result={};origins={}
    paths=set(DATA.glob(prefix+'*_overrides.json'))
    direct=DATA/(prefix+'overrides.json')
    if direct.exists():paths.add(direct)
    for path in sorted(paths):
        values=json.loads(path.read_text(encoding='utf-8'))
        for key,value in values.items():result[key]=value;origins[key]=path.name
    return result,origins


def latin_only(value):
    text=plain(value)+' '+' '.join(plain(match['label']) for match in CONCEPT.finditer(value))
    return bool(re.search('[A-Za-z]{2}',text) and not re.search('[А-Яа-яЁё]',text))


def numeric_exceptions():
    result={}
    for path in sorted(DATA.glob('*numeric_allowlist.json')):
        for pack,rows in json.loads(path.read_text(encoding='utf-8')).items():
            result.setdefault(pack,{}).update(rows)
    return result


def display_labels(value,labels,concepts):
    def replace(match):
        text=labels.get(match['label']) or concepts.get(match['key'])
        if not text:return match.group()
        return "Concept('"+match['key']+"', '"+text.replace("'",'’')+"')"
    return CONCEPT.sub(replace,value)


def build(draft=False):
    data=json.loads((WORK/'canonical.json').read_text(encoding='utf-8'));cache=load_cache()
    terms=json.loads((DATA/'ru_terms.json').read_text(encoding='utf-8'))
    allow=json.loads((DATA/'latin_allowlist.json').read_text(encoding='utf-8')) if (DATA/'latin_allowlist.json').exists() else {}
    numeric_allow=numeric_exceptions()
    frozen={pack:json.loads((ROOT/('translations/memory/'+pack+'.json')).read_text(encoding='utf-8'))
            if (ROOT/('translations/memory/'+pack+'.json')).exists() else {} for pack in ('bpm','te')}
    te_human,te_origins=overrides('te_');bpm_human,bpm_origins=overrides('bpm_')
    labels={}
    for en,ru in terms.items():labels[en]=ru
    # A vanilla place name can share an English word with a UI caption; do not
    # reuse arbitrary same-text translations across unrelated keys.
    for entry in data['te_en'].values():
        for match in CONCEPT.finditer(entry['value']):
            cached=cache.get(digest(match['label']))
            if cached and cached['status'] in {'draft','segmented_draft'}:labels.setdefault(match['label'],cached['ru'])
    result={};quality={};issues=[];remaining=[]
    for pack in ('bpm','te'):
        source=data[pack+'_en'];human=bpm_human if pack=='bpm' else te_human;origins=bpm_origins if pack=='bpm' else te_origins
        russian={};provenance={};reused=set()
        for key,entry in source.items():
            en=entry['value'];value=None;basis=None
            previous=frozen[pack].get(key)
            if key in human and previous and previous.get('en_sha256')!=digest(en):
                remaining.append({'pack':pack,'key':key,'en':en,'reason':'human translation bound to changed English'});continue
            if key in human:value=human[key];basis='human:'+origins[key]
            elif previous and previous.get('en_sha256')==digest(en):
                value=previous['ru'];basis=previous['basis'];reused.add(key)
            elif pack=='bpm' and frozen[pack]:
                remaining.append({'pack':pack,'key':key,'en':en,'reason':'new/changed BPM text needs review'});continue
            elif pack=='bpm' and key in data['bpm_workshop_ru']:value=data['bpm_workshop_ru'][key]['value'];basis='Dictator_life'
            elif pack=='bpm' and key in data['bpm_base_ru']:value=data['bpm_base_ru'][key]['value'];basis='BPM bundled Russian'
            elif not translatable(en):value=en;basis='nonlinguistic'
            elif en in UI:value=UI[en];basis='curated UI'
            elif en in terms:value=terms[en];basis='curated glossary'
            elif key in data['game_en'] and key in data['game_ru'] and data['game_en'][key]['value']==en:
                value=data['game_ru'][key]['value'];basis='vanilla same key/source'
            else:
                template,protected=mask(en);cached=cache.get(digest(template))
                if cached and cached['status'] in {'draft','segmented_draft'}:
                    value=restore(cached['ru'],protected);basis='offline '+cached['status']
            if value is None:remaining.append({'pack':pack,'key':key,'en':en});continue
            expected=source_for_validation(key,en)
            russian[key]=value;provenance[key]={'basis':basis,'en_sha256':digest(en)}
        if pack=='bpm':
            for key in ('LAW_ENACTMENT_SETBACKS_LABEL','ENACTING_TO_LAW'):
                if key in data['bpm_workshop_ru']:
                    russian[key]=data['bpm_workshop_ru'][key]['value'];provenance[key]={'basis':'Dictator_life interface repair'}
        concepts={key:ru for key,ru in russian.items() if key.startswith('concept_') and not key.endswith('_desc') and not tokens(ru)}
        for key,value in list(russian.items()):
            if key not in reused and (provenance[key]['basis'].startswith('offline') or provenance[key]['basis']=='nonlinguistic'):
                russian[key]=display_labels(value,labels,concepts)
            if key in source:
                en=source[key]['value']
                problems=validate(source_for_validation(key,en),russian[key])
                if numeric_profile(en)!=numeric_profile(russian[key]):
                    accepted=numeric_allow.get(pack,{}).get(key,{})
                    if accepted.get('en_sha256')!=digest(en) or accepted.get('ru_sha256')!=digest(russian[key]) or not accepted.get('reason'):
                        problems.append('numbers_changed')
                if problems:issues.append({'pack':pack,'key':key,'issues':problems,'en':en,'ru':russian[key],'basis':provenance[key]['basis']})
        result[pack]=russian;quality[pack]=provenance
    # Reuse reviewed tax templates for the compatibility patch's additional IGs.
    template_memory={}
    for key,en in data['te_en'].items():
        if key not in result['te']:continue
        value=result['te'][key];template,protected=mask(en['value'])
        if profile(en['value'])!=profile(value):continue
        original=tokens(en['value']);translated=tokens(value)
        pool=defaultdict(list)
        for number,(kind,_,_,raw) in enumerate(original):pool[(kind,normalize_bracket(raw) if kind=='bracket' else raw)].append(number)
        out=[];last=0;used=defaultdict(int)
        for kind,start,end,raw in translated:
            identity=(kind,normalize_bracket(raw) if kind=='bracket' else raw);index=used[identity];used[identity]+=1
            out.extend([value[last:start],'__PH'+str(pool[identity][index])+'__']);last=end
        out.append(value[last:]);template_memory[template]=''.join(out)
    bridge={}
    bridge_path=ROOT/'translations/memory/bridge.json'
    frozen_bridge=json.loads(bridge_path.read_text(encoding='utf-8')) if bridge_path.exists() else {}
    for key,entry in data['bridge_en'].items():
        en=entry['value'];value=data.get('bridge_ru',{}).get(key,{}).get('value')
        previous=frozen_bridge.get(key);reused_bridge=False
        if value is None and previous:
            if previous['en_sha256']!=digest(en):
                remaining.append({'pack':'bridge','key':key,'en':en,'reason':'changed bridge text needs review'});continue
            value=previous['ru'];reused_bridge=True
        if value is None:value=result['te'].get(key) if key in data['te_en'] and data['te_en'][key]['value']==en else None
        if value is None:
            template,protected=mask(en)
            translated=template_memory.get(template)
            cached=cache.get(digest(template))
            if translated is None and cached and cached['status'] in {'draft','segmented_draft'}:translated=cached['ru']
            if translated is not None:value=restore(translated,protected)
        if value is None:remaining.append({'pack':'bridge','key':key,'en':en});continue
        if not reused_bridge:value=display_labels(value,labels,result['bpm'])
        problems=validate(en,value)
        if numeric_profile(en)!=numeric_profile(value):problems.append('numbers_changed')
        if problems:issues.append({'pack':'bridge','key':key,'issues':problems,'en':en,'ru':value})
        bridge[key]={'en_sha256':digest(en),'ru':value}
    out=ROOT/'runtime/translations/build';out.mkdir(parents=True,exist_ok=True)
    json_write(out/'remaining.json',remaining);json_write(out/'issues.json',issues)
    untranslated=[]
    for pack,values in result.items():
        for key,value in values.items():
            permission=allow.get(pack,{}).get(key,{})
            if latin_only(value) and (permission.get('value_sha256')!=digest(value) or not permission.get('reason')):
                untranslated.append({'pack':pack,'key':key,'value':value,'en':data[pack+'_en'].get(key,{}).get('value')})
    json_write(out/'latin-only.json',untranslated)
    json_write(out/'bridge.json',bridge)
    for pack,values in result.items():
        json_write(out/(pack+'-values.json'),values);json_write(out/(pack+'-quality.json'),quality[pack])
    summary={'status':'DRAFT' if draft or issues or remaining or untranslated else 'STRUCTURAL_PASS',
             'source_keys':{pack:len(data[pack+'_en']) for pack in result},
             'built_keys':{pack:len(values) for pack,values in result.items()},'bridge_keys':len(bridge),
             'structural_issues':len(issues),'remaining':len(remaining),'latin_only_for_review':len(untranslated),
             'quality':{pack:dict(Counter(v['basis'].split(':')[0] for v in quality[pack].values())) for pack in result},
             'engine_verified':False,'all_prose_human_reviewed':False}
    summary['input_sha256']={str(path.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [WORK/'canonical.json',*sorted(DATA.glob('*.json'))]}
    json_write(out/'summary.json',summary);print(json.dumps(summary,indent=2))
    if not draft and summary['status']!='STRUCTURAL_PASS':raise SystemExit(2)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--draft',action='store_true');args=parser.parse_args();build(args.draft)
