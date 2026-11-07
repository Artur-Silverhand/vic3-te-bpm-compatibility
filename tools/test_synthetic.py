"""Negative and positive controls for the structural runtime auditor."""
import unittest
from audit_runtime_graph import analyze,strongly_connected,reviewed_iteration_optimization


class GraphContracts(unittest.TestCase):
    def scan(self,effects='',values='',hooks=None,events=None,triggers=''):
        files={}
        for relative,text in [('common/scripted_effects/test.txt',effects),('common/script_values/test.txt',values),
                              ('common/scripted_triggers/test.txt',triggers)]:
            if text:files[relative]=('patch',text)
        for relative,text in (hooks or {}).items():files['common/on_actions/'+relative]=('patch',text)
        for relative,text in (events or {}).items():files['events/'+relative]=('patch',text)
        return analyze(files,{})

    def test_detects_unconditional_two_function_recursion(self):
        result=self.scan('a = { b = yes } b = { a = yes }')
        self.assertEqual(result['unguarded_cycles'],[['effect:a','effect:b']])

    def test_conditional_cycle_is_reported_without_calling_it_unconditional(self):
        result=self.scan('a = { if = { limit = { always = no } b = yes } } b = { a = yes }')
        self.assertFalse(result['unguarded_cycles'])
        self.assertEqual(result['same_tick_cycles'],[['effect:a','effect:b']])

    def test_positive_delay_breaks_same_tick_cycle_but_feedback_is_retained(self):
        result=self.scan(events={'a.txt':'namespace = test\ntest.1 = { immediate = { trigger_event = { id = test.1 days = 1 } } }'})
        self.assertFalse(result['same_tick_cycles'])
        self.assertEqual(result['all_cycles'],[['event:test.1']])

    def test_zero_or_unknown_delay_does_not_hide_recursion(self):
        for delay in ['0','unknown_delay']:
            result=self.scan(events={'a.txt':f'test.1 = {{ immediate = {{ trigger_event = {{ id = test.1 days = {delay} }} }} }}'})
            self.assertEqual(result['same_tick_cycles'],[['event:test.1']])

    def test_detects_duplicate_effect_registration_and_callback(self):
        result=self.scan(hooks={'a.txt':'hook = { effect = { a = yes } on_actions = { cb } } cb = { }',
                               'b.txt':'hook = { effect = { b = yes } on_actions = { cb } }'})
        self.assertEqual(result['hook_field_conflicts'][0]['count'],2)
        self.assertEqual(result['duplicate_registrations'],[{'hook':'hook:hook','callback':'cb','count':2}])

    def test_variable_names_and_descriptions_do_not_become_value_calls(self):
        result=self.scan(values='cached = { if = { limit = { has_variable = cached } value = var:cached } }')
        self.assertFalse(result['edges'])
        self.assertFalse(result['same_tick_cycles'])

    def test_cached_ast_is_not_mutated_between_baseline_and_patch(self):
        files={'common/script_values/a.txt':('game','x = { value = 1 }'),
               'common/script_values/b.txt':('timeline','x = { value = 2 }')}
        cache={};first=analyze(files,cache);second=analyze(files,cache)
        self.assertEqual(first['metrics'],second['metrics'])
        self.assertEqual(first['edges'],second['edges'])

    def test_literal_macro_resolution_includes_new_ig_targets(self):
        result=self.scan(effects='go = { add = te_tax_light_rc_$KEY$_liberals }',
                         values='te_tax_light_rc_wage_liberals = 1 te_tax_light_rc_div_liberals = 2')
        self.assertEqual({e['to'] for e in result['edges']},
                         {'value:te_tax_light_rc_wage_liberals','value:te_tax_light_rc_div_liberals'})
        self.assertFalse(result['unknown_calls'])

    def test_reviewed_relief_domain_cannot_invent_self_recursion(self):
        result=self.scan('te_tax_dr_relief_touch = { te_tax_dr_$KEY$_touch = yes } '
                         'te_tax_dr_agrel_touch = { } te_tax_dr_regrel_touch = { }')
        self.assertFalse(result['same_tick_cycles'])
        self.assertEqual(len(result['edges']),2)

    def test_event_numeric_alias_resolves_to_declared_event(self):
        result=self.scan(effects='go = { trigger_event = { id = test.0001 days = 1 } }',
                         events={'a.txt':'namespace = test\ntest.1 = { }'})
        self.assertFalse(result['unknown_calls'])
        self.assertEqual(result['edges'][0]['to'],'event:test.1')

    def test_event_option_fallback_boolean_is_not_an_on_action_target(self):
        result=self.scan(events={'a.txt':'test.1 = { option = { name = test.1.a fallback = yes } }'})
        self.assertFalse(result['unknown_calls'])

    def test_cabinet_optimization_review_cannot_authorize_world_loops_or_deeper_nesting(self):
        from copy import deepcopy
        row={'id':'effect:bpm_calculate_synergy',
             'before':{'loops':{'every_law':1,'ordered_in_list':2},'max_loop_depth':2},
             'after':{'loops':{'every_law':1,'every_in_list':1},'max_loop_depth':2}}
        self.assertTrue(reviewed_iteration_optimization(row))
        world=deepcopy(row);world['after']['loops']['every_country']=1
        self.assertFalse(reviewed_iteration_optimization(world))
        nested=deepcopy(row);nested['after']['max_loop_depth']=3
        self.assertFalse(reviewed_iteration_optimization(nested))
        unrelated=deepcopy(row);unrelated['id']='effect:another_function'
        self.assertFalse(reviewed_iteration_optimization(unrelated))


if __name__=='__main__':unittest.main(verbosity=2)
