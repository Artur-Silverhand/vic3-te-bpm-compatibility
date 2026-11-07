import json
from fractions import Fraction
from pathlib import Path
import random
import unittest

from build_patch import ROOT,OUTPUT,blocks,normalized
from script_syntax import parse,Field,walk,scalars
from synthetic_cabinet import CabinetModel
from test_support import built_patch


class CabinetContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=built_patch()
        lock=json.loads((ROOT/'sources.lock.json').read_text(encoding='utf-8'))
        cls.bpm=Path(lock['mods']['bpm']['mod_root'])
        cls.effects={}
        for relative in ['common/scripted_effects/BPM_CAB_effects.txt',
                         'common/scripted_effects/BPM_CAB_SYNERGY_effects.txt',
                         'common/scripted_effects/zzzzzz_tbcp_cabinet_helpers.txt']:
            cls.effects.update({f.key:f.value for f in parse((OUTPUT/relative).read_text(encoding='utf-8-sig')) if isinstance(f,Field)})
        original=(cls.bpm/'common/scripted_effects/BPM_CAB_SYNERGY_effects.txt').read_text(encoding='utf-8-sig')
        cls.old_effects={f.key:f.value for f in parse(original) if isinstance(f,Field)}

    def test_consensus_matches_original_script_in_400_states(self):
        rng=random.Random(20261108)
        for case in range(400):
            laws=[str(i) for i in range(rng.choice([0,1,26,45,84,120]))]
            characters={str(i):{'alive':True,'owner':'C','stances':{law:rng.randint(-2,2) for law in laws}}
                        for i in range(rng.choice([1,2,6,12,16]))}
            old=CabinetModel(self.old_effects,characters,laws=laws,charset=list(characters))
            new=CabinetModel(self.effects,characters,laws=laws,charset=list(characters))
            old.execute('bpm_calculate_synergy');new.execute('bpm_calculate_synergy')
            expected=sum((Fraction(max(c['stances'][law] for c in characters.values())-
                                   min(c['stances'][law] for c in characters.values()),4) for law in laws),Fraction(0))/max(len(laws),1)
            self.assertEqual(new.vars['C']['bpm_temp_synergy_calculation'],old.vars['C']['bpm_temp_synergy_calculation'],case)
            self.assertEqual(new.vars['C']['bpm_temp_synergy_calculation'],expected,case)
            self.assertEqual(new.stance_reads,len(laws)*len(characters))
            self.assertEqual(new.law_visits,len(laws))
            if laws:self.assertLess(new.stance_reads,old.stance_reads)

    def test_empty_charset_cannot_reuse_old_opinions(self):
        chars={'a':{'alive':True,'owner':'C','stances':{'x':-2}},'b':{'alive':True,'owner':'C','stances':{'x':2}}}
        model=CabinetModel(self.effects,chars,laws=['x'],charset=['a','b'])
        model.execute('bpm_calculate_synergy')
        self.assertEqual(model.vars['C']['bpm_temp_synergy_calculation'],1)
        model.lists['C']['bpm_synergy_calculation_charset']=[]
        model.scopes['highest_opinion']=('value',Fraction(4));model.scopes['lowest_opinion']=('value',Fraction(0))
        model.execute('bpm_calculate_synergy')
        self.assertEqual(model.vars['C']['bpm_temp_synergy_calculation'],0)

    def test_consensus_updates_immediately_when_inputs_change(self):
        chars={'a':{'alive':True,'owner':'C','stances':{'x':-2,'y':0}},'b':{'alive':True,'owner':'C','stances':{'x':2,'y':0}}}
        model=CabinetModel(self.effects,chars,laws=['x'],charset=['a','b'])
        model.execute('bpm_calculate_synergy');self.assertEqual(model.vars['C']['bpm_temp_synergy_calculation'],1)
        model.laws.append('y');model.execute('bpm_calculate_synergy')
        self.assertEqual(model.vars['C']['bpm_temp_synergy_calculation'],Fraction(1,2))
        model.characters['b']['stances']['x']=-2;model.execute('bpm_calculate_synergy')
        self.assertEqual(model.vars['C']['bpm_temp_synergy_calculation'],0)
        model.lists['C']['bpm_synergy_calculation_charset']=['b'];model.execute('bpm_calculate_synergy')
        self.assertEqual(model.vars['C']['bpm_temp_synergy_calculation'],0)

    def test_repair_is_idempotent_and_discards_dead_foreign_and_duplicate_refs(self):
        chars={'live':{'alive':True,'owner':'C','minister':True},'dead':{'alive':False,'owner':'C'},
               'foreign':{'alive':True,'owner':'F'}}
        model=CabinetModel(self.effects,chars,pool=['live','dead','live','foreign'])
        model.lists['C']['bpm_CAB_temp_pool']=['dead','foreign']
        model.lists['F']['bpm_CAB_temp_pool']=['unrelated']
        for _ in range(100):model.execute('bpm_fix_cabinet_pool')
        self.assertEqual(model.lists['C']['bpm_CAB_char_select_pool'],['live'])
        self.assertEqual(model.lists['C']['bpm_CAB_temp_pool'],[])
        self.assertEqual(model.lists['F']['bpm_CAB_temp_pool'],['unrelated'])
        self.assertTrue(model.characters['live']['minister'])

    def test_no_eligible_candidate_exits_after_one_attempt(self):
        for variety in [False,True]:
            model=CabinetModel(self.effects,variety=variety)
            model.execute('bpm_fill_cabinet_pool')
            self.assertEqual(model.attempts,1)
            self.assertEqual(model.lists['C']['bpm_CAB_char_select_pool'],[])

    def test_attempt_cap_terminates_even_if_native_progress_reporting_is_wrong(self):
        class BrokenNative(CabinetModel):
            def execute(self,key):
                if key=='bpm_pick_cabinet_minister':
                    self.attempts+=1;self.locals['tbcp_cabinet_pick_added']=1
                else:super().execute(key)
        model=BrokenNative(self.effects,variety=True)
        model.execute('bpm_fill_cabinet_pool')
        self.assertEqual(model.attempts,16)
        self.assertEqual(model.lists['C']['bpm_CAB_char_select_pool'],[])

    def test_normal_fill_reaches_10_or_16_without_growth_when_full(self):
        def create(model):
            key='c'+str(model.attempts)
            model.characters[key]={'alive':True,'owner':'C'}
            return 'created',key
        for variety,target in [(False,10),(True,16)]:
            model=CabinetModel(self.effects,variety=variety,picker=create)
            model.execute('bpm_fill_cabinet_pool')
            self.assertEqual(model.attempts,target)
            self.assertEqual(len(model.lists['C']['bpm_CAB_char_select_pool']),target)
            for _ in range(100):model.execute('bpm_fill_cabinet_pool')
            self.assertEqual(model.attempts,target)
            self.assertEqual(len(model.lists['C']['bpm_CAB_char_select_pool']),target)

    def test_duplicate_missing_dead_and_foreign_insertions_cannot_keep_loop_running(self):
        chars={'a':{'alive':True,'owner':'C'},'dead':{'alive':False,'owner':'C'},'foreign':{'alive':True,'owner':'F'}}
        for target in ['a','dead','foreign',None]:
            for kind in ['leader','created']:
                model=CabinetModel(self.effects,chars,pool=['a'],picker=lambda model,k=kind,t=target:(k,t))
                model.execute('bpm_fill_cabinet_pool')
                self.assertEqual(model.attempts,1)
                self.assertEqual(model.lists['C']['bpm_CAB_char_select_pool'],['a'])

    def test_oversized_live_protected_pool_is_preserved_and_ai_does_not_generate_pool(self):
        chars={str(i):{'alive':True,'owner':'C','minister':True} for i in range(30)}
        for player in [True,False]:
            model=CabinetModel(self.effects,chars,pool=list(chars),player=player)
            model.execute('bpm_fill_cabinet_pool')
            self.assertEqual(model.attempts,0)
            self.assertEqual(model.lists['C']['bpm_CAB_char_select_pool'],list(chars))

    def test_5000_turnover_cycles_do_not_accumulate_temporary_state(self):
        serial=0
        def create(model):
            nonlocal serial
            serial+=1;key=str(serial);model.characters[key]={'alive':True,'owner':'C'}
            return 'created',key
        model=CabinetModel(self.effects,picker=create)
        model.execute('bpm_fill_cabinet_pool')
        for cycle in range(5000):
            model.steps=0
            pool=model.lists['C']['bpm_CAB_char_select_pool']
            model.characters[pool[0]]['alive']=False
            model.lists['C']['bpm_CAB_temp_pool'].append('obsolete')
            model.execute('bpm_fill_cabinet_pool')
            pool=model.lists['C']['bpm_CAB_char_select_pool']
            self.assertEqual(len(pool),10)
            self.assertEqual(len(set(pool)),10)
            self.assertTrue(all(model.characters[c]['alive'] for c in pool))
            self.assertFalse(model.lists['C']['bpm_CAB_temp_pool'])

    def test_unrelated_bpm_effects_and_weighted_native_picker_are_preserved(self):
        relative='common/scripted_effects/BPM_CAB_effects.txt'
        before={v['key']:v for v in blocks((self.bpm/relative).read_text(encoding='utf-8-sig'))}
        after={v['key']:v for v in blocks((OUTPUT/relative).read_text(encoding='utf-8-sig'))}
        self.assertEqual(before.keys(),after.keys())
        changed={'bpm_fix_cabinet_pool','bpm_clear_cabinet_pool','bpm_fill_cabinet_pool','bpm_pick_cabinet_minister'}
        for key in before:
            if key not in changed:self.assertEqual(normalized(before[key]['body']),normalized(after[key]['body']),key)
        picker=normalized(after['bpm_pick_cabinet_minister']['body'])
        prefix='set_local_variable = { name = tbcp_cabinet_pick_added value = 0 } '
        self.assertTrue(picker.startswith(prefix))
        picker=picker[len(prefix):].replace('tbcp_cabinet_try_add_leader = yes',
            'add_to_variable_list = { name = bpm_CAB_char_select_pool target = scope:ranig.leader }').replace(
            'tbcp_cabinet_try_add_created = yes','add_to_variable_list = { name = bpm_CAB_char_select_pool target = scope:ranchar }')
        self.assertEqual(picker,normalized(before['bpm_pick_cabinet_minister']['body']))
        relative='common/scripted_effects/BPM_CAB_SYNERGY_effects.txt'
        original={v['key']:v for v in blocks((self.bpm/relative).read_text(encoding='utf-8-sig'))}
        output={v['key']:v for v in blocks((OUTPUT/relative).read_text(encoding='utf-8-sig'))}
        self.assertEqual(original.keys(),output.keys())
        for key in original:
            if key!='bpm_calculate_synergy':self.assertEqual(normalized(original[key]['body']),normalized(output[key]['body']))


if __name__=='__main__':unittest.main(verbosity=2)
