"""Prepare canonical translation sources and reusable protected templates."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
from collections import defaultdict,Counter
from loclib import ROOT,load,plain,translatable,mask,digest,json_write

sys.path.insert(0,str(ROOT/'tools'))
from source_state import load_lock


def prepare():
    lock=load_lock(ROOT)
    paths={'te_en':(Path(lock['mods']['timeline']['mod_root'])/'localization','english',True),
           'bpm_en':(Path(lock['mods']['bpm']['mod_root'])/'localization','english',True),
           'bpm_base_ru':(Path(lock['mods']['bpm']['mod_root'])/'localization','russian',True),
           'bpm_workshop_ru':(Path(lock['mods']['bpm']['workshop_root']).parent/'3487720283/localization','russian',False),
           'bridge_en':(ROOT/'patch/localization','english',True),
           'bridge_ru':(ROOT/'patch/localization','russian',True),
           'game_en':(Path(lock['game']['root'])/'game/localization','english',True),
           'game_ru':(Path(lock['game']['root'])/'game/localization','russian',True)}
    data={};stats={}
    for name,(path,language,canonical) in paths.items():
        entries,stats[name]=load(path,language,canonical)
        if name=='bridge_ru':entries={key:entry for key,entry in entries.items() if not entry.file.endswith('zz_tbcp_bridge_l_russian.yml')}
        data[name]={k:asdict(v) for k,v in entries.items()}
    output=ROOT/'runtime/translations';output.mkdir(parents=True,exist_ok=True)
    json_write(output/'canonical.json',data);json_write(output/'source-audit.json',stats)
    source=data['te_en'];templates={};by_key={};snippets={}
    for key,entry in source.items():
        template,protected=mask(entry['value']);identifier=digest(template)
        if translatable(entry['value']):
            templates.setdefault(identifier,{'en':template,'keys':[]})['keys'].append(key)
            by_key[key]={'template':identifier,'protected':protected}
    for key,entry in data['bridge_en'].items():
        if key in source and entry['value']==source[key]['value']:continue
        template,protected=mask(entry['value']);identifier=digest(template)
        if translatable(entry['value']):
            templates.setdefault(identifier,{'en':template,'keys':[]})['keys'].append('bridge:'+key)
            by_key['bridge:'+key]={'template':identifier,'protected':protected}
    # Concept display words live in script islands; translate them independently.
    from loclib import CONCEPT
    for entry in list(source.values())+list(data['bridge_en'].values()):
        for match in CONCEPT.finditer(entry['value']):
            label=match['label']
            if translatable(label):snippets[label]=digest(label)
    json_write(output/'te-templates.json',templates)
    json_write(output/'te-key-templates.json',by_key)
    json_write(output/'concept-labels.json',snippets)
    summary={'te_keys':len(source),'bpm_keys':len(data['bpm_en']),'bpm_workshop_keys':len(data['bpm_workshop_ru']),
             'te_templates':len(templates),'concept_labels':len(snippets),
             'bpm_missing_keys':len(data['bpm_en'].keys()-data['bpm_workshop_ru'].keys()),
             'te_words':sum(len(plain(v['value']).split()) for v in source.values())}
    json_write(output/'prepare-summary.json',summary);print(json.dumps(summary,indent=2))


if __name__=='__main__':prepare()
