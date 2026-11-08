"""Restore Russian literature and bind cultural renaissance lifecycles to homelands."""
from copy import deepcopy
from script_syntax import parse,Field,walk

RENAISSANCES={'ukraine':('ukrainian',range(1,6)),'belarus':('byelorussian',range(6,11))}


def emit(items,level=0):
    lines=[];indent='\t'*level
    for item in items:
        if isinstance(item,Field):
            if isinstance(item.value,list):
                lines.extend([indent+item.key+' '+item.op+' {',emit(item.value,level+1),indent+'}'])
            elif isinstance(item.value,tuple):
                lines.extend([indent+item.key+' '+item.op+' '+item.value[0]+' {',emit(item.value[1],level+1),indent+'}'])
            else:lines.append(indent+item.key+' '+item.op+' '+item.value)
        elif isinstance(item,list):lines.extend([indent+'{',emit(item,level+1),indent+'}'])
        else:lines.append(indent+item)
    return '\n'.join(lines)


def body(text):return parse(text)
def field(items,key):return next(v for v in items if isinstance(v,Field) and v.key==key)
def prepend(items,key,text):field(items,key).value[:0]=body(text)
def wrap(items,condition):return [Field('if','=',[Field('limit','=',body(condition)),*items])]


def regional_gates(items,culture):
    """A named historical location must still be a homeland, not just owned."""
    for index,item in enumerate(list(items)):
        if not isinstance(item,Field):continue
        if item.key=='has_state_in_state_region' and isinstance(item.value,str):
            items[index]=Field('AND','=',[item,*body('s:'+item.value+' = { is_homeland = cu:'+culture+' }')])
        elif isinstance(item.value,list):regional_gates(item.value,culture)


def literature(text):
    nodes=parse(text)
    for event in nodes:
        if not isinstance(event,Field) or not isinstance(event.value,list):continue
        if event.key=='rlit.001':
            event.value.append(Field('trigger','=',body('has_dlc_feature = ip5_content c:RUS ?= this NOT = { has_variable = rlit_001_fired } NOT = { has_variable = rlit_arc_abandoned }')))
        elif event.key=='rlit.052':prepend(event.value,'trigger','has_dlc_feature = ip5_content')
        elif event.key in {'rlit.015','rlit.036'}:
            prefix=event.key
            for option in [v for v in event.value if isinstance(v,Field) and v.key=='option']:
                name=field(option.value,'name').value
                route={prefix+'.a':'official',prefix+'.b':'republican',prefix+'.c':'spiritual',prefix+'.opt_d':'universal'}.get(name)
                if route is None:continue
                # Preserve choice, visibility, weights and country modifier;
                # replace only vanilla IG mutations, which use incompatible axes.
                option.value=[v for v in option.value if not (isinstance(v,Field) and v.key in {'ig:ig_intelligentsia','if','else_if'})]
                option.value.extend(body('ig:ig_intelligentsia ?= { tbcp_rlit_'+route+'_effect = yes }'))
            # The event's own once flag prevents re-firing; the helper is also
            # idempotent per chapter in case an option is applied twice.
            for option in [v for v in event.value if isinstance(v,Field) and v.key=='option']:
                keep=[v for v in option.value if isinstance(v,Field) and v.key in {'name','trigger','ai_chance','default_option'}]
                effects=[v for v in option.value if v not in keep]
                marker='tbcp_rlit_'+prefix.split('.')[1]+'_applied'
                option.value=keep+wrap([*body('set_variable = '+marker),*effects],'NOT = { has_variable = '+marker+' }')
    return emit(nodes)+'\n'


POLITICS='''
# IG scope. Each transition replaces only its relevant BPM axis.
tbcp_rlit_official_effect = {
    if = {
        limit = { has_ideology = ideology:ideology_gov_moderate_monarchist }
        bpm_set_ideology = { type = gov name = radical_monarchist }
    }
    else_if = {
        limit = { OR = { has_ideology = ideology:ideology_gov_anti_proletarian has_ideology = ideology:ideology_gov_liberal_republican has_ideology = ideology:ideology_gov_radical_republican } }
        bpm_set_ideology = { type = gov name = moderate_monarchist }
    }
    if = {
        limit = { has_ideology = ideology:ideology_dop_authoritarian_democrat }
        bpm_set_ideology = { type = dop name = autocrat }
    }
    else_if = {
        limit = { OR = { has_ideology = ideology:ideology_dop_moderate_democrat has_ideology = ideology:ideology_dop_radical_democrat } }
        bpm_set_ideology = { type = dop name = authoritarian_democrat }
    }
}
tbcp_rlit_republican_effect = {
    if = {
        limit = { OR = { has_ideology = ideology:ideology_gov_anti_proletarian has_ideology = ideology:ideology_gov_moderate_monarchist has_ideology = ideology:ideology_gov_radical_monarchist } }
        bpm_set_ideology = { type = gov name = liberal_republican }
    }
    if = {
        limit = { OR = { has_ideology = ideology:ideology_dop_autocrat has_ideology = ideology:ideology_dop_authoritarian_democrat } }
        bpm_set_ideology = { type = dop name = moderate_democrat }
    }
}
tbcp_rlit_spiritual_effect = {
    remove_ideology = ideology_anti_clerical
    bpm_set_ideology = { type = rel name = modern_moralist }
}
tbcp_rlit_universal_effect = {
    bpm_set_ideology = { type = cit name = liberal_nationalist }
}
'''


def integrate(research,load,parse_blocks,generated):
    outputs=dict(generated);triggers=[];effects=[POLITICS];values=[]
    # Mask BPM's two no-op starters at their original path, and restore the
    # actual vanilla files before duplicate resolution runs.
    outputs['events/_rlit_events.txt']='namespace = rlit\n# TBCP: full literature events restored at their vanilla paths.\n'
    for relative in ('events/rlit_cluster1_golden_age.txt','events/rlit_cluster2_crossroads.txt'):
        outputs[relative]=literature(load('game',relative))
    relative='common/journal_entries/08_cultural_renaissances.txt'
    entries=parse(load('game',relative));bars=parse(load('game','common/scripted_progress_bars/00_ip5_cultural_renaissance_bars.txt'))
    events=parse(load('game','events/russia_events/cultural_renaissances_events.txt'))
    for key,(culture,ids) in RENAISSANCES.items():
        entry=field(entries,'je_'+key+'_cultural_renaissance');world='tbcp_cr_'+key+'_has_homelands';country='tbcp_cr_'+key+'_country_has_homeland'
        triggers.extend(body(world+' = { cu:'+culture+' = { any_scope_homeland_state = { always = yes } } } '+country+' = { any_scope_state = { state_region = { is_homeland = cu:'+culture+' } } }'))
        timeout=field(entry.value,'timeout').value;assert timeout=='7300'
        entry.value.remove(field(entry.value,'timeout'))
        for gate in ('possible','is_shown_when_inactive'):prepend(entry.value,gate,world+' = yes')
        init='set_global_variable = { name = tbcp_cr_'+key+'_active_days value = 0 } set_global_variable = { name = tbcp_cr_'+key+'_last_day value = game_date }'
        field(entry.value,'immediate').value.extend(body(init))
        initial=deepcopy(field(entry.value,'immediate_all_involved').value)
        join='tbcp_cr_'+key+'_join';joined='tbcp_cr_'+key+'_joined'
        effects.append(emit([Field(join,'=',wrap([*body('set_variable = '+joined),*initial],'NOT = { has_variable = '+joined+' }'))]))
        field(entry.value,'immediate_all_involved').value=body(join+' = yes')
        entry.value.append(Field('on_become_involved_after_activation','=',body(join+' = yes')))
        elapsed='tbcp_cr_'+key+'_elapsed'
        values.append(elapsed+' = { value = game_date subtract = global_var:tbcp_cr_'+key+'_last_day min = 0 max = 31 }')
        display='tbcp_cr_'+key+'_active_days_display'
        values.append(display+' = { value = 0 if = { limit = { has_global_variable = tbcp_cr_'+key+'_active_days } add = global_var:tbcp_cr_'+key+'_active_days } }')
        assert not any(v.key=='progress_desc' for v in entry.value if isinstance(v,Field))
        entry.value.extend(body('progress_desc = { first_valid = { triggered_desc = { trigger = { NOT = { '+world+' = yes } } desc = tbcp_cr_paused } triggered_desc = { trigger = { always = yes } desc = tbcp_cr_'+key+'_clock } } }'))
        clock='''
if = { limit = { NOT = { has_global_variable = tbcp_cr_KEY_active_days } } set_global_variable = { name = tbcp_cr_KEY_active_days value = 0 } }
if = { limit = { has_global_variable = tbcp_cr_KEY_last_day WORLD = yes } change_global_variable = { name = tbcp_cr_KEY_active_days add = ELAPSED } }
set_global_variable = { name = tbcp_cr_KEY_last_day value = game_date }
scope:journal_entry = {
    every_scope_je_involved = {
        limit = { NOT = { COUNTRY = yes } }
        scope:journal_entry = { remove_involved_country = prev }
    }
}
cu:CULTURE = {
    every_scope_homeland_state = {
        owner ?= {
            if = {
                limit = { NOT = { is_in_list = tbcp_cr_KEY_seen } NOT = { is_involved_in_journal_entry = ENTRY } }
                add_to_temporary_list = tbcp_cr_KEY_seen
                scope:journal_entry = { add_involved_country = prev }
            }
        }
    }
}
'''.replace('KEY',key).replace('WORLD',world).replace('COUNTRY',country).replace('CULTURE',culture).replace('ENTRY',entry.key).replace('ELAPSED',elapsed)
        reconcile='tbcp_cr_'+key+'_reconcile'
        effects.append(reconcile+' = {\n'+clock+'\n}')
        pulse=field(field(entry.value,'on_monthly_pulse').value,'effect')
        pulse.value=[*body(reconcile+' = yes'),*wrap(pulse.value,world+' = yes')]
        # Old involved countries are guarded at every use, not only after the
        # next reconciliation. This includes already queued event options.
        for item in walk(entry.value):
            if item.key=='every_scope_je_involved' and isinstance(item.value,list):
                existing=next((v for v in item.value if isinstance(v,Field) and v.key=='limit'),None)
                if existing:existing.value[:0]=body(country+' = yes')
                else:item.value.insert(0,Field('limit','=',body(country+' = yes')))
            if item.key=='random_country' and isinstance(item.value,list):prepend(item.value,'limit',country+' = yes')
        for outcome in [v for v in entry.value if isinstance(v,Field) and v.key=='outcome']:
            flags=next((v for v in outcome.value if isinstance(v,Field) and v.key=='flags'),None)
            if flags and 'timeout' in flags.value:
                outcome.value.remove(flags)
                outcome.value.append(Field('trigger','=',body(world+' = yes global_var:tbcp_cr_'+key+'_active_days >= '+timeout)))
            else:prepend(outcome.value,'trigger',world+' = yes')
            for effect in [v for v in outcome.value if isinstance(v,Field) and v.key=='effect_all_involved']:
                effect.value=wrap(effect.value,country+' = yes')
        bar=field(bars,'je_cultural_renaissance_'+key+'_progress_bar')
        monthly=field(bar.value,'monthly_progress');monthly.value=wrap(monthly.value,world+' = yes')
        for number in ids:
            event=field(events,'cultural_renaissances_events.'+str(number))
            prepend(event.value,'trigger',country+' = yes')
            for option in [v for v in event.value if isinstance(v,Field) and v.key=='option']:
                keep=[v for v in option.value if isinstance(v,Field) and v.key in {'name','trigger','ai_chance','default_option'}]
                option.value=keep+wrap([v for v in option.value if v not in keep],country+' = yes')
            regional_gates(event.value,culture)
        regional_gates(entry.value,culture)
    outputs[relative]=emit(entries)+'\n'
    outputs['common/scripted_progress_bars/00_ip5_cultural_renaissance_bars.txt']=emit(bars)+'\n'
    outputs['events/russia_events/cultural_renaissances_events.txt']=emit(events)+'\n'
    outputs['common/scripted_triggers/zzzzzz_tbcp_culture.txt']=emit(triggers)+'\n'
    outputs['common/scripted_effects/zzzzzz_tbcp_culture.txt']='\n'.join(effects)+'\n'
    outputs['common/script_values/zzzzzz_tbcp_culture.txt']='\n'.join(values)+'\n'
    english={'tbcp_cr_paused':'Paused: this culture has no homeland states. Progress and the active-time limit resume when homelands return.'}
    russian={'tbcp_cr_paused':'Приостановлено: у культуры не осталось родных земель. Прогресс и отсчёт срока возобновятся после их возвращения.'}
    for key in RENAISSANCES:
        value="[SCOPE.ScriptValue('tbcp_cr_"+key+"_active_days_display')|0]"
        english['tbcp_cr_'+key+'_clock']='Active time: '+value+' / 7300 days. Time without homelands does not count.'
        russian['tbcp_cr_'+key+'_clock']='Активное время: '+value+' / 7300 дней. Время без родных земель не учитывается.'
    for language,strings in [('english',english),('russian',russian)]:
        outputs['localization/'+language+'/zz_tbcp_culture_l_'+language+'.yml']='l_'+language+':\n'+''.join(' '+k+':0 "'+v+'"\n' for k,v in strings.items())
    return outputs,{'literature_starters_restored':['rlit.001','rlit.052'],'political_finales':['rlit.015','rlit.036'],
                    'renaissances':list(RENAISSANCES),'timeout_active_days':7300,'clock_resolution':'monthly, delta capped at 31 days',
                    'world_scans_added':0,'new_campaign_required_for_full_timeout_accounting':True,'engine_verified':False}
