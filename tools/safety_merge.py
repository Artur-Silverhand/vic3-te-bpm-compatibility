"""Remove ambiguous shadow definitions; select explicit mod-over-game bodies."""
from collections import defaultdict
from pathlib import Path
from script_syntax import top_spans
from law_merge import fields,emit


def integrate(research,load,parse,generated):
    outputs=dict(generated);vfs={}
    for label in ['game','timeline','bpm']:
        for rel in sorted(research['sources'][label]['files']):
            if rel.startswith(('events/','common/script_values/')) and rel.endswith('.txt'):
                vfs[rel]=(label,load(label,rel))
    for rel,text in outputs.items():
        if rel.startswith(('events/','common/script_values/')) and rel.endswith('.txt'):vfs[rel]=('patch',text)
    by_key=defaultdict(list)
    for rel,(label,text) in vfs.items():
        for entity in top_spans(text):
            if entity['operation']!='DEFINE':continue
            if rel.startswith('events/') and (not entity['block'] or '.' not in entity['key']):continue
            category='events' if rel.startswith('events/') else 'script_values'
            by_key[(category,entity['key'])].append((label,rel,entity))
    changes=defaultdict(list);decisions=[]
    priority={'game':0,'timeline':1,'bpm':2,'patch':3}
    for (category,key),records in sorted(by_key.items()):
        if len(records)<2:continue
        ordered=sorted(records,key=lambda r:priority[r[0]],reverse=True)
        assert priority[ordered[0][0]]>priority[ordered[1][0]],'Same-source duplicate needs explicit decision: '+str(records)
        winner=ordered[0]
        for label,rel,node in ordered[1:]:
            changes[rel].append((node['start'],node['end'],f'# TBCP: {key} supplied by {winner[1]}.'))
        decisions.append({'category':category,'key':key,'winner_owner':winner[0],'winner_path':winner[1],
                          'suppressed_paths':[rel for _,rel,_ in ordered[1:]]})
    for rel,edits in changes.items():
        text=vfs[rel][1]
        for start,end,value in sorted(edits,reverse=True):text=text[:start]+value+text[end:]
        outputs[rel]=text
    # Vanilla and BPM both register an effect for this hook. BPM replaces the
    # entire legislative phase procedure, including AI fallback. Retaining
    # vanilla's unconditional phase increment would bypass BPM's voting/veto.
    relative='common/on_actions/00_code_on_actions.txt'
    assert relative not in outputs,'Checkpoint adapter requires composition'
    original=load('game',relative)
    node=next(n for n in parse(original) if n['key']=='on_law_checkpoint_success')
    outputs[relative]=original[:node['start']]+'# TBCP: on_law_checkpoint_success is provided by BPM.\n'+original[node['end']:]
    # Future TE parties need BPM's active-IG and single-party/party-ban gates.
    # Explicit political-family policy; keep every original TE eligibility and
    # weight field, and delegate to existing country-scope ban predicates.
    future={'green_party':'radical_party','populist_party':'reactionary_party','technocratic_party':'liberal_party'}
    parties=[];ban_helpers=[]
    for party,counterpart in future.items():
        relative='common/parties/'+party+'.txt'
        source=next(n for n in parse(load('timeline',relative)) if n['key']==party)
        items=fields(source['body']);gate=next(v for v in items if v['key']=='available_for_interest_group')
        gate['value']+='\nbpm_interest_group_is_activated = yes\nNOT = { bpm_is_party_banned = { PARTY = '+party+' } }\n'
        parties.append('REPLACE:'+party+' = {\n'+emit(items)+'}\n')
        ban_helpers.append(f'bpm_is_{party}_banned = {{ bpm_is_{counterpart}_banned = yes }}\n')
    outputs['common/parties/zzzzzz_tbcp_future_parties.txt']='\n'.join(parties)
    outputs['common/scripted_triggers/zzzzzz_tbcp_future_party_bans.txt']='\n'.join(ban_helpers)
    # BPM's same-path Iberian coup file retains .1-.4 but omits 1.15's .11,
    # still called by the game's foreign-coup diplomatic action. Restore only
    # this referenced new event; do not bring back the replaced domestic chain.
    relative='events/iberia_events/ip4_coup_events.txt'
    original=load('game',relative)
    foreign=next(n for n in parse(original) if n['key']=='ip4_coup.11')
    assert 'ip4_coup.11' not in {n['key'] for n in parse(load('bpm',relative))}
    outputs['events/tbcp_foreign_coup_events.txt']='namespace = ip4_coup\n\n'+foreign['raw']+'\n'
    relative='common/journal_entries/BPM_je_america.txt'
    assert relative not in outputs
    original=load('bpm',relative)
    assert original.count('id = bpm_acw_events.0001')==1
    outputs[relative]=original.replace('id = bpm_acw_events.0001','id = bpm_acw_events.1')
    return outputs,{'shadow_definitions_resolved':decisions,'files_masked':sorted(changes),
                    'future_party_ban_families':future,
                    'restored_referenced_game_events':['ip4_coup.11'],
                    'checkpoint_success':'sole BPM effect; vanilla phase increment removed at original path'}
