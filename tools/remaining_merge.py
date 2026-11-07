"""Reviewed adapters for the remaining shared databases in the pinned inputs."""
import re
from law_merge import fields, emit, modifier_sum, norm


def build_remaining(research, load, parse):
    common = research['comparisons']['timeline_bpm']['shared_entities']
    outputs = {}; report = {}

    def body(label, record):
        nodes = [v for v in parse(load(label, record['path']))
                 if v['key'] == record['key'] and v['operation'] == record['operation']]
        assert len(nodes) == 1, record
        return nodes[0]['body']

    # Technologies and principles use complete definitions so an upstream
    # REPLACE cannot discard a separately loaded injection.
    for category, target in [
        ('common/technology/technologies', 'common/technology/technologies/zzzzzz_tbcp_technologies.txt'),
        ('common/power_bloc_principles', 'common/power_bloc_principles/zzzzzz_tbcp_principles.txt')]:
        entries = [e for e in common if e['category'] == category]
        vanilla = {v['key']:v['body'] for rel in sorted(research['sources']['game']['files'])
                   if rel.startswith(category + '/') and rel.endswith('.txt')
                   for v in parse(load('game',rel))}
        generated = []
        for entry in entries:
            replacements = [(label,r) for side,label in [('left','timeline'),('right','bpm')]
                            for r in entry[side] if r['operation'] == 'REPLACE']
            assert len(replacements) <= 1
            values = fields(body(*replacements[0]) if replacements else vanilla[entry['key']])
            index = {v['key']:v for v in values}
            for side,label in [('left','timeline'),('right','bpm')]:
                for record in entry[side]:
                    if record['operation'] != 'INJECT':continue
                    for item in fields(body(label,record)):
                        assert item['key'] in {'modifier','member_modifier','possible'}, item
                        if item['key'] not in index:
                            values.append(item);index[item['key']]=item
                        elif item['key'] == 'possible':
                            index[item['key']]['value'] += '\n'+item['value']
                        else:
                            previous=index[item['key']]
                            previous['value']=modifier_sum(previous['value'],item['value'])
            generated.append('REPLACE:'+entry['key']+' = {\n'+emit(values)+'}\n')
        outputs[target]='\n'.join(generated)
        report[category] = [e['key'] for e in entries]

    # BPM controls presentation; TE contributes AI metadata. Neither side's
    # scalar values are added as if they were gameplay modifiers.
    generated=[]
    for entry in common:
        if entry['category'] != 'common/modifier_type_definitions':continue
        values=fields(body('bpm',entry['right'][0]))
        names={v['key'] for v in values}
        extra=[v for v in fields(body('timeline',entry['left'][0])) if v['key'] not in names]
        assert all(v['key']=='game_data' for v in extra)
        generated.append('REPLACE:'+entry['key']+' = {\n'+emit(values+extra)+'}\n')
    outputs['common/modifier_type_definitions/zzzzzz_tbcp_modifier_types.txt']='\n'.join(generated)

    # Preserve BPM's historical political changes. Only the success condition
    # for taxation receives TE's rule-aware equivalent. The disabled branch
    # is the exact BPM tax condition, including its original has_law operator.
    generated=[]
    for entry in common:
        if entry['category'] != 'common/journal_entries':continue
        original=body('bpm',entry['right'][0]);te=body('timeline',entry['left'][0])
        markers=re.findall(r'### MOD: Tax Code[^\n]*\n(.*?)### END MOD ###',te,re.S)
        assert len(markers)==1,entry['key']
        conditional=next(v for v in parse(markers[0]) if v['key']=='trigger_if')['raw']
        matches=[v for v in recursive_blocks(original,parse)
                 if v['key']=='OR' and 'law_type:law_proportional_taxation' in v['body']
                 and all('taxation' in f['value'] for f in fields(v['body']))]
        assert len(matches)==1,entry['key']
        old=matches[0]
        change=conditional+'\ntrigger_else = {\n'+old['raw']+'\n}'
        result=original[:old['start']]+change+original[old['end']:]
        generated.append('REPLACE:'+entry['key']+' = {'+result+'}\n')
    outputs['common/journal_entries/zzzzzz_tbcp_tax_journals.txt']='\n'.join(generated)

    # Use the existing same-path override precedent for scripted_rules.
    # Suppress BPM's prefixed rule at its own path and insert the body into
    # TE's complete 1.15 rules file, preserving every other TE rule verbatim.
    relative='common/scripted_rules/00_scripted_rules.txt'
    original=load('timeline',relative)
    rule=next(v for v in parse(original) if v['key']=='has_voting_franchise')
    bpm_relative='common/scripted_rules/zzz_bpm_scripted_rules.txt'
    bpm_rule=parse(load('bpm',bpm_relative))
    assert len(bpm_rule)==1 and bpm_rule[0]['key']=='has_voting_franchise'
    outputs[relative]=(original[:rule['start']]+'has_voting_franchise = {'+
                       bpm_rule[0]['body']+'}'+original[rule['end']:])
    outputs[bpm_relative]='# has_voting_franchise is composed in 00_scripted_rules.txt.\n'
    report['journals']=['je_imperialism_of_promise','je_portugal_regeneration']
    report['modifier_type_policy']='BPM presentation, TE game_data'
    report['franchise_policy']='BPM elections trigger; TE other rules unchanged'
    return outputs,report


def recursive_blocks(text,parse,offset=0):
    """Return nested block spans in coordinates of the original string."""
    for node in parse(text):
        yield dict(node,start=node['start']+offset,end=node['end']+offset)
        # Locate the actual opening brace, not a brace in a preceding comment.
        opening=node['raw'].index('{')+node['start']+1
        yield from recursive_blocks(node['body'],parse,offset+opening)
