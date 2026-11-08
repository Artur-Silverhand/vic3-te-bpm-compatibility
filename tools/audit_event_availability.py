"""Inventory disabled vanilla events separately from syntax/reference checks.

An inert upstream override can be deliberate. This report diagnoses availability;
it does not automatically restore political chains replaced by BPM.
"""
from collections import Counter,defaultdict
import json
from pathlib import Path
import re
from source_state import ROOT,load_lock
from script_syntax import parse,Field,scalars


def event_id(key):
    match=re.fullmatch(r'(.+)\.(\d+)',key)
    return match[1]+'.'+str(int(match[2])) if match else key


def events(root):
    result={};by_path={}
    for path in sorted((Path(root)/'events').rglob('*.txt')):
        relative=path.relative_to(root).as_posix();by_path[relative]={}
        for node in parse(path.read_text(encoding='utf-8-sig')):
            if not isinstance(node,Field) or not isinstance(node.value,list) or not re.fullmatch(r'.+\.\d+',node.key):continue
            key=event_id(node.key);item={'key':key,'path':relative,'body':node.value,'fields':scalars(node.value)}
            item['inert_hidden_stub']=item['fields'].get('hidden')=='yes' and all(
                isinstance(row,Field) and row.key in {'type','placement','hidden'} and isinstance(row.value,str)
                for row in node.value)
            result.setdefault(key,[]).append(item);by_path[relative][key]=item
    return result,by_path


def explicitly_false(body):
    """Only prove an unconditional false conjunct, never infer from nested OR."""
    return any(isinstance(item,Field) and (
        item.key=='always' and item.value=='no' or
        item.key in {'AND','hidden_trigger'} and isinstance(item.value,list) and explicitly_false(item.value)
    ) for item in body)


def blocked_gates(root,category,gates):
    rows=[]
    for path in sorted((Path(root)/category).rglob('*.txt')):
        for node in parse(path.read_text(encoding='utf-8-sig')):
            if not isinstance(node,Field) or not isinstance(node.value,list):continue
            for gate in node.value:
                if isinstance(gate,Field) and gate.key in gates and isinstance(gate.value,list) and explicitly_false(gate.value):
                    rows.append({'key':node.key,'path':path.relative_to(root).as_posix(),'blocked_gate':gate.key})
    return rows


def audit():
    lock=load_lock(ROOT);roots={'game':Path(lock['game']['root'])/'game',
                              'timeline':Path(lock['mods']['timeline']['mod_root']),
                              'bpm':Path(lock['mods']['bpm']['mod_root']),'patch':ROOT/'patch'}
    inventories={label:events(root) for label,root in roots.items()}
    game,game_paths=inventories['game'];rows=[];hidden={};omitted={}
    for label in ('timeline','bpm'):
        source,paths=inventories[label];stubs=[];removed=[]
        for key,definitions in source.items():
            if key in game:
                for node in definitions:
                    if node['inert_hidden_stub']:
                        stubs.append({'event':key,'mod_path':node['path'],'game_paths':[v['path'] for v in game[key]]})
        for relative,current in paths.items():
            if relative in game_paths:
                for key in game_paths[relative].keys()-current.keys():
                    removed.append({'event':key,'masked_game_path':relative,
                                    'defined_elsewhere_in_mod':key in source})
        hidden[label]=stubs;omitted[label]=removed
    # The patch's explicit duplicate policy decides which definitions survive.
    active_paths={}
    for label in ('game','timeline','bpm','patch'):
        for relative,definitions in inventories[label][1].items():active_paths[relative]=(label,definitions)
    active=defaultdict(list)
    for relative,(label,definitions) in active_paths.items():
        for key,node in definitions.items():active[key].append({'owner':label,'path':relative,'inert_hidden_stub':node['inert_hidden_stub']})
    rlit=sorted(key for key in game if key.startswith('rlit.'))
    blocked={label:{'events':blocked_gates(roots[label],'events',{'trigger'}),
                    'journals':blocked_gates(roots[label],'common/journal_entries',{'possible','is_shown_when_inactive'})}
             for label in ('timeline','bpm')}
    summary={'source_event_ids':{label:len(value[0]) for label,value in inventories.items()},
             'vanilla_inert_hidden_overrides':{label:len(value) for label,value in hidden.items()},
             'same_path_omissions':{label:len(value) for label,value in omitted.items()},
             'rlit_vanilla_events':len(rlit),
             'explicit_false_gates':{label:{kind:len(rows) for kind,rows in groups.items()} for label,groups in blocked.items()},
             'rlit_starters':{key:active.get(event_id(key),[]) for key in ('rlit.001','rlit.052')},
             'interpretation':'Inventory only: deliberate disabling is distinct from a missing reference or engine failure.',
             'game_launched':False}
    report={'summary':summary,'inert_hidden_overrides':hidden,'same_path_omissions':omitted,'rlit_events':rlit,
            'explicit_false_gates':blocked,
            'limitations':['False inactive/possible gates can be bypassed by explicit add_journal_entry.',
                           'This does not evaluate dynamic scopes, DLC ownership, dates, random chances or engine execution.']}
    destination=ROOT/'docs/research/event-availability.json';destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2));return report


if __name__=='__main__':audit()
