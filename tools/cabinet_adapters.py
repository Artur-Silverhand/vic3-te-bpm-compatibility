"""Bound candidate generation and calculate BPM consensus in one linear scan."""
from law_merge import fields
from remaining_merge import recursive_blocks


FIX_POOL='''
# Scratch state is local to this rebuild, never a history of former candidates.
clear_variable_list = bpm_CAB_temp_pool
every_in_list = {
    variable = bpm_CAB_char_select_pool
    if = {
        limit = { is_character_alive = yes owner = prev }
        owner = {
            if = {
                limit = { NOT = { is_target_in_variable_list = { name = bpm_CAB_temp_pool target = prev } } }
                add_to_variable_list = { name = bpm_CAB_temp_pool target = prev }
            }
        }
    }
}
clear_variable_list = bpm_CAB_char_select_pool
every_in_list = {
    variable = bpm_CAB_temp_pool
    owner = { add_to_variable_list = { name = bpm_CAB_char_select_pool target = prev } }
}
clear_variable_list = bpm_CAB_temp_pool
'''

SYNERGY='''
set_variable = { name = bpm_temp_synergy_calculation value = 0 }
set_local_variable = { name = tbcp_synergy_law_count value = 0 }
every_law = {
    save_scope_as = bpm_law_to_check
    change_local_variable = { name = tbcp_synergy_law_count add = 1 }
    owner = {
        set_local_variable = { name = tbcp_synergy_seen value = 0 }
        set_local_variable = { name = tbcp_synergy_min value = 0 }
        set_local_variable = { name = tbcp_synergy_max value = 0 }
        every_in_list = {
            variable = bpm_synergy_calculation_charset
            set_local_variable = { name = tbcp_synergy_opinion value = bpm_character_law_stance_as_number_abs }
            if = {
                limit = { local_var:tbcp_synergy_seen = 0 }
                set_local_variable = { name = tbcp_synergy_min value = local_var:tbcp_synergy_opinion }
                set_local_variable = { name = tbcp_synergy_max value = local_var:tbcp_synergy_opinion }
                set_local_variable = { name = tbcp_synergy_seen value = 1 }
            }
            else = {
                if = {
                    limit = { local_var:tbcp_synergy_opinion < local_var:tbcp_synergy_min }
                    set_local_variable = { name = tbcp_synergy_min value = local_var:tbcp_synergy_opinion }
                }
                if = {
                    limit = { local_var:tbcp_synergy_opinion > local_var:tbcp_synergy_max }
                    set_local_variable = { name = tbcp_synergy_max value = local_var:tbcp_synergy_opinion }
                }
            }
        }
        if = {
            limit = { local_var:tbcp_synergy_seen = 1 }
            change_variable = {
                name = bpm_temp_synergy_calculation
                add = { value = local_var:tbcp_synergy_max subtract = local_var:tbcp_synergy_min divide = 4 }
            }
        }
    }
}
change_variable = { name = bpm_temp_synergy_calculation divide = { value = local_var:tbcp_synergy_law_count min = 1 } }
'''


def integrate(research,load,parse,generated):
    outputs=dict(generated)
    relative='common/scripted_effects/BPM_CAB_effects.txt'
    assert relative not in outputs
    source=load('bpm',relative);nodes={n['key']:n for n in parse(source)}
    edits=[]
    def replace(key,body):
        node=nodes[key];edits.append((node['start'],node['end'],key+' = {\n'+body+'\n}\n'))
    replace('bpm_fix_cabinet_pool',FIX_POOL)
    replace('bpm_clear_cabinet_pool',nodes['bpm_clear_cabinet_pool']['body']+'\nclear_variable_list = bpm_CAB_temp_pool\n')

    # Preserve the author's random/weighted IG choice and character creation.
    # Only actual valid insertions set the per-pick progress marker.
    pick=nodes['bpm_pick_cabinet_minister']['body'];insertions=[]
    for node in recursive_blocks(pick,parse):
        if node['key']!='add_to_variable_list':continue
        data={f['key']:f['value'] for f in fields(node['body'])}
        if data.get('name')!='bpm_CAB_char_select_pool':continue
        target=data['target'];assert target in {'scope:ranig.leader','scope:ranchar'},target
        helper='tbcp_cabinet_try_add_leader' if target.endswith('.leader') else 'tbcp_cabinet_try_add_created'
        insertions.append((node['start'],node['end'],helper+' = yes'))
    assert len(insertions)==3
    for start,end,value in sorted(insertions,reverse=True):pick=pick[:start]+value+pick[end:]
    replace('bpm_pick_cabinet_minister','set_local_variable = { name = tbcp_cabinet_pick_added value = 0 }\n'+pick)

    original=nodes['bpm_fill_cabinet_pool']['body']
    loop=next(v for v in recursive_blocks(original,parse) if v['key']=='while')
    condition=next(v['body'] for v in parse(loop['body']) if v['key']=='limit')
    # The original target is 10 or 16. At most 16 successful additions are
    # needed after cleanup; failed progress exits immediately. Never truncate
    # an already larger live/protected pool.
    body='''
if = {
    limit = { is_player = yes }
    bpm_fix_cabinet_pool = yes
    set_local_variable = { name = tbcp_cabinet_attempts value = 0 }
    set_local_variable = { name = tbcp_cabinet_progress value = 1 }
    while = {
        limit = {
            local_var:tbcp_cabinet_attempts < 16
            local_var:tbcp_cabinet_progress = 1
'''+condition+'''
        }
        bpm_pick_cabinet_minister = yes
        bpm_fix_cabinet_pool = yes
        change_local_variable = { name = tbcp_cabinet_attempts add = 1 }
        set_local_variable = { name = tbcp_cabinet_progress value = local_var:tbcp_cabinet_pick_added }
    }
}
'''
    replace('bpm_fill_cabinet_pool',body)
    for start,end,value in sorted(edits,reverse=True):source=source[:start]+value+source[end:]
    outputs[relative]=source
    helpers=[]
    for name,target in [('leader','scope:ranig.leader'),('created','scope:ranchar')]:
        helpers.append(f'''tbcp_cabinet_try_add_{name} = {{
    if = {{
        limit = {{ exists = {target} }}
        if = {{
            limit = {{
                {target} = {{ is_character_alive = yes owner = prev }}
                NOT = {{ is_target_in_variable_list = {{ name = bpm_CAB_char_select_pool target = {target} }} }}
            }}
            add_to_variable_list = {{ name = bpm_CAB_char_select_pool target = {target} }}
            set_local_variable = {{ name = tbcp_cabinet_pick_added value = 1 }}
        }}
    }}
}}
''')
    outputs['common/scripted_effects/zzzzzz_tbcp_cabinet_helpers.txt']='\n'.join(helpers)
    relative='common/scripted_effects/BPM_CAB_SYNERGY_effects.txt'
    assert relative not in outputs
    source=load('bpm',relative)
    node=next(v for v in parse(source) if v['key']=='bpm_calculate_synergy')
    outputs[relative]=source[:node['start']]+'bpm_calculate_synergy = {\n'+SYNERGY+'\n}\n'+source[node['end']:]
    return outputs,{'changed_effects':['bpm_fix_cabinet_pool','bpm_clear_cabinet_pool','bpm_pick_cabinet_minister',
                                      'bpm_fill_cabinet_pool','bpm_calculate_synergy'],
                    'max_candidate_attempts':16,'targets':[10,16],
                    'scratch_policy':'clear before and after repair; retain unique living owned characters',
                    'consensus_policy':'same all-law denominator and same stance function; one min/max scan; empty set gives zero',
                    'persistent_cache_added':False,'new_pulses':0}
