"""Rule-aware BPM tax reads and idempotent scripted fiscal reforms for TE."""
from inspect_mod_overlap import TOKEN

LAWS={
 'law_consumption_based_taxation':'consumption_based',
 'law_land_based_taxation':'land_based',
 'law_per_capita_based_taxation':'per_capita',
 'law_proportional_taxation':'proportional',
 'law_graduated_taxation':'graduated',
}
READS={'has_law':'has','has_law_or_variant':'has_or_variant'}


def rewrite(text):
    """Edit literal scalar assignments only; strings and comments are opaque."""
    tokens=[m for m in TOKEN.finditer(text) if not m.group().startswith('#')]
    changes=[];counts={'reads':0,'activations':0}
    for i in range(len(tokens)-2):
        key,op,value=[m.group() for m in tokens[i:i+3]]
        if op!='=' or not value.startswith('law_type:'):continue
        law=value.removeprefix('law_type:')
        if law not in LAWS:continue
        if key in READS:
            replacement=f'tbcp_tax_{READS[key]}_{LAWS[law]} = yes';counts['reads']+=1
        elif key=='activate_law':
            replacement=f'tbcp_tax_activate_{LAWS[law]} = yes';counts['activations']+=1
        else:continue
        changes.append((tokens[i].start(),tokens[i+2].end(),replacement))
    for start,end,replacement in reversed(changes):text=text[:start]+replacement+text[end:]
    return text,counts


def helpers(rows):
    triggers=[];effects=[]
    for law,short in LAWS.items():
        for original,read in READS.items():
            triggers.append(f'''tbcp_tax_{read}_{short} = {{
    trigger_if = {{
        limit = {{ te_tax_code_in_force = yes has_law = law_type:law_te_tax_code }}
        te_tax_code_equivalent_{short} = yes
    }}
    trigger_else = {{ {original} = law_type:{law} }}
}}
''')
        branches=[]
        for index,(row_law,level,rates) in enumerate(row for row in rows if row[0]==law):
            unchanged=' '.join(f'has_variable = te_tax_en_{key} var:te_tax_en_{key} = {value} '
                               f'has_variable = te_tax_en_{key}_exp var:te_tax_en_{key}_exp = -1 '
                               f'has_variable = te_tax_en_{key}_succ var:te_tax_en_{key}_succ = -1'
                               for key,value in rates.items())
            writes='\n'.join(f'set_variable = {{ name = te_tax_en_{key} value = {value} }}' for key,value in rates.items())
            branches.append(f'''{'if' if index==0 else 'else_if'} = {{
            limit = {{ tax_level = {level} }}
            if = {{
                limit = {{ NAND = {{ {unchanged} }} }}
                {writes}
                # External reform: invalidate stale fiscal baselines without
                # touching goods, relief, customs, bills or obligations.
                te_tax_gen_migrate_provisions = yes
                change_variable = {{ name = te_tax_code_version add = 1 }}
                tbcp_tax_queue_sync = yes
            }}
        }}''')
        assert len(branches)==5
        effects.append(f'''tbcp_tax_activate_{short} = {{
    if = {{
        limit = {{ te_tax_code_in_force = yes has_law = law_type:law_te_tax_code }}
        {chr(10).join(branches)}
    }}
    else = {{ activate_law = law_type:{law} }}
}}
''')
    effects.append('''# One deferred collection event per country per day. No new pulse.
tbcp_tax_queue_sync = {
    if = {
        limit = {
            OR = {
                NOT = { has_variable = tbcp_tax_reform_sync_day }
                NOT = { var:tbcp_tax_reform_sync_day = te_tax_today }
            }
        }
        set_variable = { name = tbcp_tax_reform_sync_day value = te_tax_today }
        trigger_event = { id = te_tax.4 days = 1 }
    }
}
''')
    return {'common/scripted_triggers/zzzzzz_tbcp_tax_legacy_triggers.txt':'\n'.join(triggers),
            'common/scripted_effects/zzzzzz_tbcp_tax_legacy_effects.txt':'\n'.join(effects)}


def integrate(research,load,parse,generated,rows):
    """Keep full-file replacement only for categories without existing adapters."""
    outputs=dict(generated);evidence=[];additional_ideologies=[]
    protected={n['key'] for rel,text in generated.items() if rel.startswith('common/ideologies/') for n in parse(text)}
    for rel in sorted(research['sources']['bpm']['files']):
        if not (rel.startswith(('common/','events/')) and rel.endswith('.txt')):continue
        original=load('bpm',rel)
        changed,counts=rewrite(original)
        if changed==original:continue
        if rel.startswith('common/journal_entries/'):
            # Two shared historical entries already use the author's broader
            # counts-as success criteria and retain BPM's disabled branch.
            assert rel in {'common/journal_entries/zz_bpm_00_imperialism_of_promise.txt',
                           'common/journal_entries/zz_bpm_06_portugal_politics.txt'}
            policy='handled by composed historical entries'
        elif rel.startswith('common/parties/'):
            policy='rewrite composed parties below'
        elif rel.startswith('common/ideologies/'):
            for node in parse(original):
                adapted,c=rewrite(node['body'])
                if adapted!=node['body'] and node['key'] not in protected:
                    additional_ideologies.append(f'REPLACE:{node["key"]} = {{{adapted}}}\n')
            policy='rewrite composed ideologies; replace only additional affected IDs'
        else:
            assert rel not in outputs,'Existing adapter requires explicit composition: '+rel
            outputs[rel]=changed;policy='same-path BPM file override'
        evidence.append({'source':rel,**counts,'policy':policy})
    for rel in list(generated):
        if rel.startswith(('common/parties/','common/ideologies/')):
            outputs[rel],counts=rewrite(outputs[rel])
    if additional_ideologies:
        outputs['common/ideologies/zzzzzz_tbcp_tax_ideologies.txt']='\n'.join(additional_ideologies)
    outputs.update(helpers(rows))
    return outputs,{'source_adapters':evidence,'additional_ideologies':len(additional_ideologies),
                    'legacy_activation_policy':'idempotent external rate reform, deferred sync; native before migration/light/off',
                    'rate_rows':rows,'new_pulses':0}
