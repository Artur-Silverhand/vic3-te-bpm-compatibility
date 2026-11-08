"""Execute the adapters' lifecycle/axis contracts, with native engine boundaries.

This is not an engine simulation: joins' original movement/AI setup, character
creation and modifiers are explicit boundaries; our guards and clocks execute.
"""
from copy import deepcopy
import json
import operator
from pathlib import Path
import unittest
from script_syntax import parse,Field,walk,scalars
from build_patch import ROOT,OUTPUT,blocks,normalized
from test_support import built_patch
from te_backports import apply_unified,load as load_backports
from audit_runtime_graph import reviewed_bounded_iteration
from source_state import load_lock


def definitions(relative):
    return {item.key:item.value for item in parse((OUTPUT/relative).read_text(encoding='utf-8-sig')) if isinstance(item,Field)}


class World:
    def __init__(self,key='ukraine'):
        self.key=key;self.culture='ukrainian' if key=='ukraine' else 'byelorussian'
        self.a={'kind':'country','name':'A','tag':'RUS','vars':{},'ideologies':set(),'characters':[]}
        self.b={'kind':'country','name':'B','tag':'AUS','vars':{},'ideologies':set(),'characters':[]}
        self.states=[{'kind':'state','name':'STATE_EAST_GALICIA','owner':self.a,'homes':{self.culture}},
                     {'kind':'state','name':'STATE_BREST','owner':self.a,'homes':{self.culture}}]
        self.je={'kind':'journal','members':[self.a]};self.globals={};self.day=0;self.dlc=True;self.progress=0
        self.exiles=[];self.used=set();self.scopes={'journal_entry':self.je};self.temporary={};self.awards={};self.modifiers=[]
        self.effects=definitions('common/scripted_effects/zzzzzz_tbcp_culture.txt')
        self.triggers=definitions('common/scripted_triggers/zzzzzz_tbcp_culture.txt')
        self.values=definitions('common/script_values/zzzzzz_tbcp_culture.txt');self.steps=0

    def number(self,value):
        if value=='game_date':return self.day
        if value.startswith('global_var:'):return self.globals[value[11:]]
        if value in self.values:
            result=0
            for item in self.values[value]:
                amount=self.number(item.value)
                if item.key=='value':result=amount
                elif item.key=='subtract':result-=amount
                elif item.key=='min':result=max(result,amount)
                elif item.key=='max':result=min(result,amount)
                else:raise ValueError(item.key)
            return result
        try:return float(value)
        except ValueError:return value

    def check(self,items,current=None,previous=None,mode='AND'):
        current=current or self.je;answers=[]
        for item in items:
            assert isinstance(item,Field),item
            k,v=item.key,item.value
            if k in {'AND','OR','NOT','NOR'}:answer=self.check(v,current,previous,k)
            elif k in self.triggers:answer=self.check(self.triggers[k],current,previous)
            elif k=='always':answer=v=='yes'
            elif k=='has_dlc_feature':answer=self.dlc
            elif k=='c:RUS':answer=current.get('tag')=='RUS'
            elif k=='has_variable':answer=v in current.get('vars',{})
            elif k=='has_global_variable':answer=v in self.globals
            elif k=='has_ideology':answer=v.removeprefix('ideology:') in current['ideologies']
            elif k.startswith('global_var:') or k=='game_date':answer={'=':operator.eq,'>=':operator.ge,'<':operator.lt}[item.op](self.number(k),self.number(v))
            elif k=='exists':answer=v.removeprefix('scope:') in self.scopes
            elif k=='has_template':answer=current.get('template')==v
            elif k=='is_template_used':answer=v in self.used
            elif k=='has_journal_entry':answer=v in current.get('journals',set())
            elif k=='is_involved_in_journal_entry':answer=current in self.je['members']
            elif k=='is_in_list':answer=current['name'] in self.temporary.get(v,set())
            elif k=='is_homeland':answer=v.removeprefix('cu:') in current['homes']
            elif k=='state_region':answer=self.check(v,current,previous)
            elif k.startswith('s:'):answer=any(self.check(v,s,current) for s in self.states if s['name']==k[2:])
            elif k=='has_state_in_state_region':answer=any(s['owner'] is current and s['name']==v for s in self.states)
            elif k=='any_scope_state':answer=any(self.check(v,s,current) for s in self.states if s['owner'] is current)
            elif k=='any_scope_character':answer=any(self.check(v,c,current) for c in current['characters'])
            elif k.startswith('cu:'):answer=self.check(v,{'kind':'culture','name':k[3:]},current)
            elif k=='any_scope_homeland_state':answer=any(self.check(v,s,current) for s in self.states if current['name'] in s['homes'])
            else:raise ValueError('Unmodelled condition '+k)
            answers.append(answer)
        return any(answers) if mode=='OR' else not any(answers) if mode in {'NOT','NOR'} else all(answers)

    def run(self,items,current=None,previous=None):
        current=current or self.je;chain=False
        for item in items:
            self.steps+=1
            if self.steps>5000:raise RuntimeError('Unbounded adapter execution')
            k,v=item.key,item.value
            if k in {'if','else_if','else'}:
                if k=='if':chain=False
                if not chain:
                    condition=next((row.value for row in v if isinstance(row,Field) and row.key=='limit'),[])
                    chain=self.check(condition,current,previous)
                    if chain:self.run([row for row in v if row.key!='limit'],current,previous)
            elif k in self.effects:
                if k.endswith('_join'):
                    # Original movement/AI initialization is a native boundary;
                    # execute the actual enclosing once guard and marker first.
                    clause=self.effects[k][0];guard=clause.value[0]
                    if self.check(guard.value,current,previous):
                        self.run([clause.value[1]],current,previous)
                        self.awards[current['name']]=self.awards.get(current['name'],0)+1
                else:self.run(self.effects[k],current,previous)
            elif k in {'scope:journal_entry','ig:ig_intelligentsia'}:self.run(v,self.je if k=='scope:journal_entry' else current,current)
            elif k.startswith('scope:'):self.run(v,self.scopes[k[6:]],current)
            elif k.startswith('cu:'):self.run(v,{'kind':'culture','name':k[3:]},current)
            elif k=='owner':self.run(v,current['owner'],current)
            elif k in {'every_scope_je_involved','every_scope_homeland_state'}:
                candidates=list(self.je['members']) if k=='every_scope_je_involved' else [s for s in self.states if current['name'] in s['homes']]
                limit=next((row.value for row in v if row.key=='limit'),[])
                for target in candidates:
                    if self.check(limit,target,current):self.run([row for row in v if row.key!='limit'],target,current)
            elif k=='remove_involved_country':self.je['members'].remove(previous)
            elif k=='add_involved_country':
                if previous not in self.je['members']:
                    self.je['members'].append(previous);self.run(parse('tbcp_cr_'+self.key+'_join = yes'),previous,current)
            elif k=='add_to_temporary_list':self.temporary.setdefault(v,set()).add(current['name'])
            elif k in {'set_global_variable','change_global_variable'}:
                data=scalars(v);self.globals[data['name']]=self.number(data['value']) if k=='set_global_variable' else self.globals[data['name']]+self.number(data['add'])
            elif k=='set_variable':
                if isinstance(v,str):current['vars'][v]=True
                else:current['vars'][scalars(v)['name']]=scalars(v)['value']
            elif k=='bpm_set_ideology':
                data=scalars(v);prefix='ideology_'+data['type']+'_'
                current['ideologies']={x for x in current['ideologies'] if not x.startswith(prefix)}|{prefix+data['name']}
            elif k=='remove_ideology':current['ideologies'].discard(v)
            elif k=='add_modifier':self.modifiers.append(scalars(v)['name'])
            elif k in {'random_scope_character','random_character_in_exile_pool'}:
                candidates=current['characters'] if k=='random_scope_character' else self.exiles
                limit=next(row.value for row in v if row.key=='limit')
                target=next((c for c in candidates if self.check(limit,c,current)),None)
                if target:self.run([row for row in v if row.key!='limit'],target,current)
            elif k=='save_scope_as':self.scopes[v]=current
            elif k=='create_character':
                data=scalars(v);character={'kind':'character','template':data['template']}
                current['characters'].append(character);self.used.add(data['template']);self.scopes[data['save_scope_as']]=character
            elif k=='add_journal_entry':current.setdefault('journals',set()).add(scalars(v)['type'])
            elif k=='set_temporary_event_immortality':pass # native lifetime boundary
            else:raise ValueError('Unmodelled effect '+k)

    def reconcile(self):
        self.temporary={};self.run(self.effects['tbcp_cr_'+self.key+'_reconcile'])


class CulturalContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.manifest=built_patch()

    def test_new_russia_starts_once_and_requires_dlc(self):
        event=definitions('events/rlit_cluster1_golden_age.txt')['rlit.001'];trigger=next(x.value for x in event if x.key=='trigger');immediate=next(x.value for x in event if x.key=='immediate')
        w=World();w.dlc=False;self.assertFalse(w.check(trigger,w.a));w.dlc=True
        self.assertTrue(w.check(trigger,w.a));self.assertFalse(w.check(trigger,w.b))
        w.run(immediate,w.a)
        self.assertIn('je_rlit_golden_age',w.a['journals']);self.assertIn('rlit_001_fired',w.a['vars'])
        self.assertEqual(sum(c['template']=='RUS_alexander_pushkin' for c in w.a['characters']),1)
        self.assertFalse(w.check(trigger,w.a))

    def test_duel_needs_start_and_date_and_does_not_resurrect_used_dead_template(self):
        event=definitions('events/rlit_cluster1_golden_age.txt')['rlit.002'];trigger=next(x.value for x in event if x.key=='trigger')
        # Replace only the engine date literal with a day ordinal for this model.
        text=deepcopy(trigger)
        for f in walk(text):
            if f.key=='game_date':f.value='397'
        w=World();w.a['journals']={'je_rlit_golden_age'};w.a['vars']['rlit_001_fired']=True
        self.assertFalse(w.check(text,w.a));w.day=397;self.assertTrue(w.check(text,w.a))
        w.used.add('RUS_alexander_pushkin');self.assertFalse(w.check(text,w.a))
        w.a['characters'].append({'kind':'character','template':'RUS_alexander_pushkin'});self.assertTrue(w.check(text,w.a))

    def test_finales_are_idempotent_and_keep_unrelated_bpm_axes(self):
        for chapter in ('015','036'):
            event=definitions('events/rlit_cluster'+('1_golden_age' if chapter=='015' else '2_crossroads')+'.txt')['rlit.'+chapter]
            option=next(x.value for x in event if x.key=='option' and scalars(x.value)['name']=='rlit.'+chapter+'.a')
            effect=[x for x in option if x.key not in {'name','trigger','ai_chance','default_option'}]
            w=World();w.a['ideologies']={'ideology_gov_anti_proletarian','ideology_dop_moderate_democrat','ideology_eco_laissez_faire'}
            w.run(effect,w.a);first=deepcopy(w.a);w.run(effect,w.a)
            self.assertEqual(w.a,first);self.assertEqual(len(w.modifiers),1)
            self.assertIn('ideology_eco_laissez_faire',w.a['ideologies'])
            self.assertIn('ideology_gov_moderate_monarchist',w.a['ideologies'])
            self.assertEqual(sum(x.startswith('ideology_gov_') for x in w.a['ideologies']),1)

    def test_zero_world_homelands_pause_clock_and_keep_join_awards_once(self):
        for key in ('ukraine','belarus'):
            w=World(key);w.globals={'tbcp_cr_'+key+'_active_days':100,'tbcp_cr_'+key+'_last_day':0}
            w.run(parse('tbcp_cr_'+key+'_join = yes'),w.a)
            for s in w.states:s['homes'].clear()
            w.day=30;w.reconcile();self.assertEqual(w.globals['tbcp_cr_'+key+'_active_days'],100);self.assertEqual(w.je['members'],[])
            w.states[0]['homes'].add(w.culture);w.day=60;w.reconcile()
            self.assertEqual(w.globals['tbcp_cr_'+key+'_active_days'],130);self.assertEqual(w.je['members'],[w.a]);self.assertEqual(w.awards['A'],1)

    def test_foreign_homelands_keep_global_story_but_move_country_involvement(self):
        w=World();w.globals={'tbcp_cr_ukraine_active_days':0,'tbcp_cr_ukraine_last_day':0}
        for s in w.states:s['owner']=w.b
        w.day=30;w.reconcile()
        self.assertEqual(w.je['members'],[w.b]);self.assertEqual(w.awards,{'B':1});self.assertEqual(w.globals['tbcp_cr_ukraine_active_days'],30)
        w.day=60;w.reconcile();self.assertEqual(w.awards,{'B':1})

    def test_paused_entry_cannot_finish_even_when_bar_was_full(self):
        entries=definitions('common/journal_entries/08_cultural_renaissances.txt')
        bars=definitions('common/scripted_progress_bars/00_ip5_cultural_renaissance_bars.txt')
        for key in ('ukraine','belarus'):
            entry=entries['je_'+key+'_cultural_renaissance'];w=World(key)
            for s in w.states:s['homes'].clear()
            self.assertFalse(w.check([next(x for x in entry if x.key=='possible').value[0]]))
            for outcome in [x.value for x in entry if x.key=='outcome']:
                trigger=next(x.value for x in outcome if x.key=='trigger')
                # The first actual conjunct is the global homeland gate.
                self.assertFalse(w.check([trigger[0]]))
            bar=bars['je_cultural_renaissance_'+key+'_progress_bar'];monthly=next(x.value for x in bar if x.key=='monthly_progress')
            self.assertFalse(w.check(monthly[0].value[0].value))
            self.assertNotIn('timeout',{x.key for x in entry})

    def test_regional_events_require_the_named_region_to_remain_homeland(self):
        event=definitions('events/russia_events/cultural_renaissances_events.txt')['cultural_renaissances_events.1']
        trigger=next(x.value for x in event if x.key=='trigger');w=World()
        # Remove the unrelated UKR identity check; retain actual adapter gates.
        trigger=[x for x in trigger if x.key!='NOT']
        self.assertTrue(w.check(trigger,w.a));w.states[0]['homes'].clear();self.assertFalse(w.check(trigger,w.a))

    def test_queued_event_option_has_no_effect_after_country_loses_homelands(self):
        event=definitions('events/russia_events/cultural_renaissances_events.txt')['cultural_renaissances_events.1']
        option=next(x.value for x in event if x.key=='option')
        effects=[x for x in option if x.key not in {'name','trigger','ai_chance','default_option'}]
        w=World();[s['homes'].clear() for s in w.states]
        before=deepcopy(w.globals);w.run(effects,w.a);self.assertEqual(w.globals,before);self.assertEqual(w.modifiers,[])

    def test_timeout_keeps_7300_active_days_and_bounds_elapsed_delta(self):
        w=World();w.globals={'tbcp_cr_ukraine_last_day':0};w.day=1000
        self.assertEqual(w.number('tbcp_cr_ukraine_elapsed'),31)
        entry=definitions('common/journal_entries/08_cultural_renaissances.txt')['je_ukraine_cultural_renaissance']
        outcomes=[x for x in entry if x.key=='outcome'];last=next(x.value for x in outcomes[-1].value if x.key=='trigger')
        w.globals['tbcp_cr_ukraine_active_days']=7299;self.assertFalse(w.check(last));w.globals['tbcp_cr_ukraine_active_days']=7300;self.assertTrue(w.check(last))


class BackportContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):built_patch()

    def test_patches_reject_drift_and_truncated_hunks(self):
        patch='@@ -1,2 +1,2 @@\n a\n-b\n+c'
        self.assertEqual(apply_unified('a\nb\n',patch),'a\nc\n')
        with self.assertRaises(ValueError):apply_unified('a\nx\n',patch)
        with self.assertRaises(ValueError):apply_unified('a\nb\n',patch.rsplit('\n',1)[0])

    def test_pool_add_is_once_outside_cycle_running_gate(self):
        banking=definitions('common/journal_entries/je_banking.txt')['je_banking_cycle'];weekly=next(x.value for x in banking if x.key=='on_weekly_pulse');effect=next(x.value for x in weekly if x.key=='effect')
        self.assertEqual(sum(x.key=='banking_weekly_investment_pool_add' for x in effect),1)
        effects=definitions('common/scripted_effects/banking_cycle_effects.txt')
        self.assertFalse(any(x.key=='add_investment_pool' for x in walk(effects['banking_cycle_weekly_effects'])))
        self.assertEqual(scalars(effects['banking_weekly_investment_pool_add'])['add_investment_pool'],'investment_pool_banking_cycle_add')

    def test_nuclear_loop_has_explicit_weekly_and_ai_bounds(self):
        effect=definitions('common/scripted_effects/nuclear_weapon_effects.txt')['nuclear_program_weekly_progress']
        loop=next(x.value for x in effect if x.key=='while');limit=next(x.value for x in loop if x.key=='limit')
        self.assertTrue(any(x.key=='local_var:nd_built_this_week' and x.op=='<' and x.value=='nuclear_weapon_program_max_per_week' for x in limit))
        self.assertTrue(any(x.key=='NOT' and scalars(x.value).get('nuclear_program_ai_at_stockpile_cap')=='yes' for x in limit))
        constants=definitions('common/script_values/extra_script_values.txt')
        self.assertEqual(constants['nuclear_weapon_program_max_per_week'],'3')

    def test_milestone_loop_doubles_a_positive_threshold_and_terminates(self):
        effect=definitions('common/scripted_effects/nuclear_weapon_effects.txt')['nd_log_arsenal_watch']
        assignments=[scalars(f.value) for f in walk(effect) if f.key=='set_variable' and isinstance(f.value,list)]
        starts=[float(v['value']) for v in assignments if v.get('name')=='nd_log_next_milestone']
        self.assertTrue(starts);self.assertTrue(all(v==50 for v in starts))
        loop=next(f.value for f in walk(effect) if f.key=='while')
        increment=next(scalars(f.value) for f in loop if f.key=='change_variable')
        self.assertEqual(increment,{'name':'nd_log_next_milestone','multiply':'2'})
        for arsenal in (0,49,50,1200,10**12):
            threshold=starts[0];steps=0
            while arsenal>=threshold:
                threshold*=float(increment['multiply']);steps+=1
                self.assertLess(steps,40)

    def test_bounded_iteration_review_rejects_same_metrics_with_changed_body(self):
        reviews=json.loads((ROOT/'docs/decisions/iteration-reviews.json').read_text(encoding='utf-8'))
        node={'body':definitions('common/scripted_effects/zzzzzz_tbcp_culture.txt')['tbcp_cr_ukraine_reconcile']}
        row={'id':'effect:tbcp_cr_ukraine_reconcile','before':{'loops':{}},'after':{'loops':{'every_scope_je_involved':1,'every_scope_homeland_state':1},'max_loop_depth':1}}
        self.assertTrue(reviewed_bounded_iteration(row,node,reviews))
        node['body']=node['body']+[Field('unexpected_effect','=','yes')]
        self.assertFalse(reviewed_bounded_iteration(row,node,reviews))

    def test_all_backports_bound_to_pinned_parent_and_production_composed_once(self):
        values,report=load_backports(ROOT,load_lock(ROOT)['mods']['timeline']['mod_root'])
        self.assertEqual(report['files'],18)
        text=(OUTPUT/'common/production_methods/extra_pms.txt').read_text(encoding='utf-8-sig')
        composed=blocks((OUTPUT/'common/production_methods/zzzzzz_tbcp_production.txt').read_text(encoding='utf-8-sig'))
        self.assertFalse({n['key'] for n in blocks(text)}&{n['key'] for n in composed})


if __name__=='__main__':unittest.main(verbosity=2)
