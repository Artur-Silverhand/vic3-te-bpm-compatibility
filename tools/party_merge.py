"""Keep BPM party weights and add TE's FPTP terms without vanilla size caps."""
import re
from law_merge import norm


def build_parties(research, load, parse):
    outputs={}; parties=[]; audit=[]
    te_weights={v['key']:v for v in parse(load('timeline','common/parties/zz_te_party_join_weights.txt'))}
    template=next(v for v in parse(te_weights['agrarian_party']['body']) if v['key']=='join_weight')
    def terms(party):
        nodes=parse(template['body'])
        selected=[v['raw'] for v in nodes if '"te_fptp_major_party_join"' in v['body'] or '"te_fptp_minor_party_join"' in v['body']]
        assert len(selected)==2
        return '\n'.join(selected).replace('te_fptp_major_agrarian_party','te_fptp_major_'+party)
    records=[x for x in research['comparisons']['timeline_bpm']['shared_entities'] if x['category']=='common/parties']
    for entry in records:
        record=entry['right'][0]
        entity=next(v for v in parse(load('bpm',record['path'])) if v['key']==entry['key'])
        weight=next(v for v in parse(entity['body']) if v['key']=='join_weight')
        assert 'scope:number' not in weight['body'], 'BPM changed size rules: review FPTP composition'
        body=entity['body'][:weight['start']]+f'join_weight = {{{weight["body"]}\n{terms(entry["key"])}\n}}'+entity['body'][weight['end']:]
        parties.append(f'REPLACE:{entry["key"]} = {{{body}}}\n')
        audit.append({'key':entry['key'],'bpm_file':record['path'],'decision':'BPM weight steps intact; TE major/minor adjustments appended'})
    relative='common/parties/zzzz_reactionary_party.txt'
    entity=next(v for v in parse(load('bpm',relative)) if v['key']=='reactionary_party')
    weight=next(v for v in parse(entity['body']) if v['key']=='join_weight')
    assert 'scope:number' not in weight['body']
    body=entity['body'][:weight['start']]+f'join_weight = {{{weight["body"]}\n{terms("reactionary_party")}\n}}'+entity['body'][weight['end']:]
    parties.append(f'REPLACE:reactionary_party = {{{body}}}\n')
    outputs['common/parties/zzzzzz_tbcp_parties.txt']='\n'.join(parties)

    # Scripted effects/triggers use same-path replacement of the whole upstream
    # file: do not assume REPLACE directives are supported in these databases.
    effect_rel='common/scripted_effects/te_fptp_effects.txt'
    effects=load('timeline',effect_rel); edits=[]
    for node in parse(effects):
        body=node['body']
        if node['key']=='te_fptp_mark_major_party':
            body+='\nelse_if = { limit = { is_party_type = reactionary_party } scope:te_fptp_country = { set_variable = te_fptp_major_reactionary_party } }\n'
        elif node['key']=='te_fptp_clear_major_marks':
            body+='\nremove_variable = te_fptp_major_reactionary_party\n'
        else:continue
        edits.append((node['start'],node['end'],node['key']+' = {'+body+'}'))
    assert len(edits)==2
    for start,end,value in sorted(edits,reverse=True):effects=effects[:start]+value+effects[end:]
    def exclude_independents(text):
        # Independents are a single-party-state opposition container, not an
        # electoral party that should occupy either FPTP major-party slot.
        return re.sub(r'NOT\s*=\s*\{\s*is_party_type\s*=\s*revolutionary_party\s*\}',
                      'NOR = { is_party_type = revolutionary_party is_party_type = one_party_independents }',text)
    outputs[effect_rel]=exclude_independents(effects)
    value_rel='common/script_values/te_fptp_values.txt'
    outputs[value_rel]=exclude_independents(load('timeline',value_rel))
    trigger_rel='common/scripted_triggers/te_fptp_triggers.txt'
    triggers=load('timeline',trigger_rel)
    node=next(v for v in parse(triggers) if v['key']=='te_fptp_party_is_major')
    or_node=next(v for v in parse(node['body']) if v['key']=='OR')
    addition='\nAND = { is_party_type = reactionary_party scope:te_fptp_country = { has_variable = te_fptp_major_reactionary_party } }\n'
    body=node['body'][:or_node['start']]+'OR = {'+or_node['body']+addition+'}'+node['body'][or_node['end']:]
    outputs[trigger_rel]=triggers[:node['start']]+node['key']+' = {'+body+'}'+triggers[node['end']:]

    # Both sources replace Free Elections. Preserve BPM's rigidity reward and
    # political repeal/sponsor conditions, union TE's eligible electoral laws,
    # and remove the anarchy penalty TE explicitly retired.
    a_rel='common/amendments/bpm_amendments_historical_04.txt'
    base=next(v for v in parse(load('bpm',a_rel)) if v['key']=='amendment_tradition_of_free_elections')
    te=next(v for v in parse(load('timeline','common/amendments/te_tradition_of_free_elections.txt')) if v['key']==base['key'])
    old=next(v for v in parse(base['body']) if v['key']=='allowed_laws')
    more=next(v for v in parse(te['body']) if v['key']=='allowed_laws')
    words=re.findall(r'\blaw_[a-z_]+\b',norm(old['body']+'\n'+more['body']))
    # 1.15 Labour Suffrage is an electoral law and TE's FPTP trigger already
    # includes it; keep the historical tradition eligible on the same path.
    words.append('law_labour_suffrage')
    body=base['body'][:old['start']]+'allowed_laws = { '+' '.join(dict.fromkeys(words))+' }'+base['body'][old['end']:]
    body=re.sub(r'(?m)^[ \t]*country_enactment_success_chance_law_anarchy_add\s*=\s*[-.0-9]+[^\n]*','',body)
    outputs['common/amendments/zzzzzz_tbcp_elections.txt']='REPLACE:'+base['key']+' = {'+body+'}\n'
    return outputs,{'shared_parties':len(records),'bpm_added_parties':1,'party_decisions':audit,
                    'free_elections':'BPM reward/repeal; TE eligible laws; no anarchy penalty',
                    'independents':'excluded from TE FPTP ranking'}
