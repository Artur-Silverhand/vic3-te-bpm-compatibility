"""Source-preservation checks for the experimental integration module."""
import json
from pathlib import Path
import sys
import unittest

from build_patch import ROOT, OUTPUT, blocks, normalized, generate
from law_merge import fields, inject, modifier_sum
from gui_merge import declarations
from remaining_merge import recursive_blocks
from legacy_tax import rewrite as rewrite_tax,LAWS
from synthetic_tax import FiscalModel
from script_syntax import top_spans,walk,parse as ast_parse
from test_support import built_patch


class PatchContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = built_patch()
        cls.lock = json.loads((ROOT/'sources.lock.json').read_text(encoding='utf-8'))

    def test_quoted_braces_and_comments_do_not_change_scope(self):
        sample = 'x = { desc = "literal } # still quoted" if = { a = yes } } # }\ny = { a = no }'
        parsed = blocks(sample)
        self.assertEqual([v['key'] for v in parsed], ['x', 'y'])
        self.assertEqual([v['key'] for v in blocks(parsed[0]['body'])], ['if'])

    def test_incomplete_input_fails_closed(self):
        with self.assertRaises(ValueError):
            blocks('x = { if = { a = yes }')

    def test_production_recipe_unchanged_and_bpm_restriction_resolves(self):
        source = Path(self.lock['mods']['timeline']['mod_root'])/'common/production_methods/extra_pms.txt'
        before = {v['key']: v for v in blocks(source.read_text(encoding='utf-8-sig'))}
        after = blocks((OUTPUT/'common/production_methods/zzzzzz_tbcp_production.txt').read_text(encoding='utf-8-sig'))
        self.assertEqual(len(after), 6)
        bpm = Path(self.lock['mods']['bpm']['mod_root'])
        amendment_keys = {v['key'] for p in (bpm/'common/amendments').glob('*.txt')
                          for v in blocks(p.read_text(encoding='utf-8-sig'))}
        for entity in after:
            source_body = normalized(before[entity['key']]['body'])
            self.assertTrue(normalized(entity['body']).startswith(source_body), entity['key'])
            fields = [v for v in blocks(entity['body']) if v['key']=='disallowing_amendments']
            self.assertEqual(len(fields), 1)
            self.assertEqual(fields[0]['body'].split(), ['bpm_amendment_artisanal_economy'])
            self.assertIn(fields[0]['body'].strip(), amendment_keys)

    def test_every_original_bpm_ideology_field_survives(self):
        bpm = Path(self.lock['mods']['bpm']['mod_root'])
        original = {}
        for p in (bpm/'common/ideologies').glob('*.txt'):
            for entity in blocks(p.read_text(encoding='utf-8-sig')):
                original[entity['key']] = entity
        emitted = blocks((OUTPUT/'common/ideologies/zzzzzz_tbcp_ideologies.txt').read_text(encoding='utf-8-sig'))
        self.assertEqual(len(emitted), 103)
        self.assertEqual(len({v['key'] for v in emitted}), 103)
        allowed = set(json.loads((ROOT/'docs/research/2026-11-07-github-overlap.json').read_text(encoding='utf-8'))['timeline_new_lawgroups'])
        policy=json.loads((ROOT/'docs/decisions/ideology-correspondences.json').read_text(encoding='utf-8'))
        for entity in emitted:
            base = rewrite_tax(original[entity['key']]['body'])[0]
            if entity['key'] in policy['correspondences']:
                before={v['key']:v for v in fields(base)}
                after={v['key']:v for v in fields(entity['body'])}
                for key,value in before.items():
                    self.assertIn(key,after)
                    if key.startswith('lawgroup_'):
                        actual={v['key']:v['value'] for v in fields(after[key]['value'])}
                        for stance in fields(value['value']):self.assertEqual(actual[stance['key']],stance['value'])
                    else:self.assertEqual(normalized(value['value']),normalized(after[key]['value']))
            else:self.assertTrue(normalized(entity['body']).startswith(normalized(base)), entity['key'])
            if 'character_ideology = yes' not in normalized(base) and entity['key'] not in policy['correspondences']:
                self.assertEqual(normalized(entity['body']), normalized(base), entity['key'])
            old_fields = {v['key'] for v in blocks(base)}
            for v in blocks(entity['body']):
                self.assertTrue(v['key'] in old_fields or v['key'] in allowed)

    def test_all_new_groups_have_traceable_axis_positions(self):
        policy=json.loads((ROOT/'docs/decisions/ideology-correspondences.json').read_text(encoding='utf-8'))
        self.assertEqual(len(policy['covered_new_groups']),39)
        self.assertFalse(policy['uncovered_new_groups'])
        te=Path(self.lock['mods']['timeline']['mod_root'])
        source={v['key']:v for p in (te/'common/ideologies').glob('*.txt') for v in blocks(p.read_text(encoding='utf-8-sig'))}
        for row in policy['stances']:
            body=source[row['source_profile']]['body']
            group=next(v for v in fields(body) if v['key']==row['group'])
            view=next(v for v in fields(group['value']) if v['key']==row['law'])
            self.assertEqual(view['value'],row['stance'])

    def test_axis_output_preserves_existing_bpm_views_and_priority(self):
        bpm=Path(self.lock['mods']['bpm']['mod_root'])
        original={v['key']:v for p in (bpm/'common/ideologies').glob('*.txt') for v in blocks(p.read_text(encoding='utf-8-sig'))}
        all_keys=[]
        for p in (OUTPUT/'common/ideologies').glob('*.txt'):
            for entity in blocks(p.read_text(encoding='utf-8-sig')):
                all_keys.append(entity['key'])
                if p.name!='zzzzzz_tbcp_axes.txt':continue
                before={v['key']:v for v in fields(original[entity['key']]['body'])}
                after={v['key']:v for v in fields(entity['body'])}
                for key,value in before.items():
                    if key.startswith('lawgroup_'):
                        actual={v['key']:v['value'] for v in fields(after[key]['value'])}
                        for old in fields(value['value']):self.assertEqual(old['value'],actual[old['key']])
                    else:self.assertEqual(normalized(value['value']),normalized(after[key]['value']))
        self.assertEqual(len(all_keys),len(set(all_keys)))

    def test_defines_and_experimental_status(self):
        text = (OUTPUT/'common/defines/zzzzzz_tbcp_defines.txt').read_text(encoding='utf-8-sig')
        self.assertIn('MAX_INSTITUTION_INVESTMENT = 9', text)
        self.assertIn('INCOHERENCE_FACTOR = 1', text)
        self.assertFalse(self.manifest['game_runs_performed'])
        self.assertFalse(self.manifest['engine_load_order_verified'])
        self.assertTrue(self.manifest['open'])

    def test_law_modifier_cancellation_is_exact(self):
        result={v['key']:v['value'] for v in fields(modifier_sum(
            'allocation = 0.50 emission = -0.15', 'allocation = -0.50 emission = 0.10'))}
        self.assertEqual(result,{'allocation':'0.00','emission':'-0.05'})

    def test_unknown_law_scalar_conflict_requires_decision(self):
        with self.assertRaisesRegex(ValueError,'progressiveness'):
            inject('progressiveness = 25','progressiveness = 50')

    def test_law_lists_and_effects_preserve_both_sources(self):
        result=fields(inject('unlocking_laws = { a b } on_enact = { first = yes }',
                             'unlocking_laws = { b c } on_enact = { second = yes }'))
        result={v['key']:v['value'] for v in result}
        self.assertEqual(result['unlocking_laws'].split(),['a','b','c'])
        self.assertEqual(normalized(result['on_enact']),'first = yes second = yes')

    def test_all_shared_laws_keep_integration_hooks(self):
        data=json.loads((ROOT/'docs/research/2026-11-07-github-overlap.json').read_text(encoding='utf-8'))
        emitted={v['key']:v for v in blocks((OUTPUT/'common/laws/zzzzzz_tbcp_laws.txt').read_text(encoding='utf-8-sig'))}
        self.assertEqual(len(emitted),70)
        for entry in data['comparisons']['timeline_bpm']['shared_entities']:
            if entry['category']!='common/laws':continue
            result={v['key']:v for v in fields(emitted[entry['key']]['body'])}
            self.assertIn('group',result,entry['key'])
            for label,side in [('timeline','left'),('bpm','right')]:
                for record in entry[side]:
                    p=Path(data['sources'][label]['root'])/record['path']
                    node=next(v for v in blocks(p.read_text(encoding='utf-8-sig')) if v['key']==entry['key'] and v['operation']==record['operation'])
                    original={v['key']:v for v in fields(node['body'])}
                    for key,value in original.items():
                        self.assertIn(key,result,entry['key']+'/'+key)
                        if key in {'modifier','institution_modifier','acceptance_modifier'}:
                            actual={v['key'] for v in fields(result[key]['value'])}
                            self.assertTrue({v['key'] for v in fields(value['value'])}<=actual)

    def test_party_weights_keep_bpm_steps_and_add_fptp_once(self):
        bpm=Path(self.lock['mods']['bpm']['mod_root'])
        originals={n['key']:n for p in (bpm/'common/parties').glob('*.txt') for n in blocks(p.read_text(encoding='utf-8-sig'))}
        emitted=blocks((OUTPUT/'common/parties/zzzzzz_tbcp_parties.txt').read_text(encoding='utf-8-sig'))
        self.assertEqual(len(emitted),12)
        for entity in emitted:
            before=next(v for v in blocks(originals[entity['key']]['body']) if v['key']=='join_weight')
            after=next(v for v in blocks(entity['body']) if v['key']=='join_weight')
            self.assertTrue(normalized(after['body']).startswith(normalized(rewrite_tax(before['body'])[0])))
            self.assertEqual(after['body'].count('"te_fptp_major_party_join"'),1)
            self.assertEqual(after['body'].count('"te_fptp_minor_party_join"'),1)
            self.assertIn('te_fptp_major_'+entity['key'],after['body'])

    def test_fptp_extra_party_has_complete_lifecycle(self):
        effects=(OUTPUT/'common/scripted_effects/te_fptp_effects.txt').read_text(encoding='utf-8-sig')
        triggers=(OUTPUT/'common/scripted_triggers/te_fptp_triggers.txt').read_text(encoding='utf-8-sig')
        self.assertIn('set_variable = te_fptp_major_reactionary_party',effects)
        self.assertIn('remove_variable = te_fptp_major_reactionary_party',effects)
        self.assertIn('has_variable = te_fptp_major_reactionary_party',triggers)
        self.assertIn('is_party_type = one_party_independents',effects)

    def test_electoral_tradition_preserves_bpm_and_te_extensions(self):
        body=blocks((OUTPUT/'common/amendments/zzzzzz_tbcp_elections.txt').read_text(encoding='utf-8-sig'))[0]['body']
        data={v['key']:v for v in fields(body)}
        self.assertIn('law_organic_democracy',data['allowed_laws']['value'])
        self.assertIn('law_anarchy',data['allowed_laws']['value'])
        self.assertIn('law_labour_suffrage',data['allowed_laws']['value'])
        self.assertIn('country_rigidity_baseline_add',data['modifier']['value'])
        self.assertNotIn('country_enactment_success_chance_law_anarchy_add',data['modifier']['value'])

    def test_file_overrides_preserve_unmodified_te_helpers(self):
        te=Path(self.lock['mods']['timeline']['mod_root'])
        relative='common/scripted_effects/te_fptp_effects.txt'
        before={n['key']:n for n in blocks((te/relative).read_text(encoding='utf-8-sig'))}
        after={n['key']:n for n in blocks((OUTPUT/relative).read_text(encoding='utf-8-sig'))}
        self.assertEqual(before.keys(),after.keys())
        for key in before:
            if key in {'te_fptp_mark_major_party','te_fptp_clear_major_marks','te_fptp_refresh_major_parties'}:continue
            expected=normalized(before[key]['body']).replace(
                'NOT = { is_party_type = revolutionary_party }',
                'NOR = { is_party_type = revolutionary_party is_party_type = one_party_independents }')
            self.assertEqual(expected,normalized(after[key]['body']),key)

    def test_character_integration_keeps_bpm_membership_and_chance_base(self):
        bpm=Path(self.lock['mods']['bpm']['mod_root'])
        original={v['key']:v for p in (bpm/'common/interest_groups').glob('*.txt')
                  for v in blocks(p.read_text(encoding='utf-8-sig'))}
        output=blocks((OUTPUT/'common/interest_groups/zzzzzz_tbcp_characters.txt').read_text(encoding='utf-8-sig'))
        self.assertEqual({v['key'] for v in output},original.keys())
        for entity in output:
            before={v['key']:v for v in fields(original[entity['key']]['body'])}
            after={v['key']:v for v in fields(entity['body'])}
            self.assertEqual(before.keys(),after.keys())
            for key,old in before.items():
                if key in {'female_commander_chance','female_politician_chance','female_agitator_chance'}:
                    self.assertTrue(normalized(after[key]['value']).startswith(normalized(old['value'])))
                    self.assertIn('law_type:law_full_equality_and_protection',after[key]['value'])
                else:self.assertEqual(normalized(old['value']),normalized(after[key]['value']),entity['key']+'/'+key)

    def test_gui_collisions_removed_and_bpm_features_kept(self):
        te=Path(self.lock['mods']['timeline']['mod_root'])
        bpm=Path(self.lock['mods']['bpm']['mod_root'])
        shared=set(self.manifest['gui_integration']['resolved_type_names'])
        remaining=[]
        for source in (te,bpm):
            for path in (source/'gui').glob('**/*.gui'):
                relative=path.relative_to(source)
                selected=OUTPUT/relative if (OUTPUT/relative).exists() else path
                old=declarations(path.read_text(encoding='utf-8-sig'))
                new=declarations(selected.read_text(encoding='utf-8-sig'))
                self.assertEqual({v['key'] for v in old}-shared,{v['key'] for v in new}-shared)
                remaining.extend(v['key'] for v in new if v['key'] in shared)
        for key in shared:self.assertEqual(remaining.count(key),1,key)
        # Every BPM callback survives the country/law panel transformations.
        for relative in ['gui/BPM_country_panel.gui','gui/BPM_politics_panel_change_law.gui']:
            import re
            before=(bpm/relative).read_text(encoding='utf-8-sig')
            after=(OUTPUT/relative).read_text(encoding='utf-8-sig')
            callbacks=re.findall(r'onclick\s*=\s*"[^"\n]*"',before)
            for callback in callbacks:self.assertIn(callback,after)
        country=(OUTPUT/'gui/BPM_country_panel.gui').read_text(encoding='utf-8-sig')
        self.assertIn('te_nation_panel_line',country)
        law=(OUTPUT/'gui/BPM_politics_panel_change_law.gui').read_text(encoding='utf-8-sig')
        self.assertIn('te_law_tax_delta_effects',law)

    def test_journals_keep_bpm_except_rule_aware_tax_success(self):
        bpm=Path(self.lock['mods']['bpm']['mod_root'])
        original={v['key']:v for p in (bpm/'common/journal_entries').glob('*.txt')
                  for v in blocks(p.read_text(encoding='utf-8-sig'))}
        output=blocks((OUTPUT/'common/journal_entries/zzzzzz_tbcp_tax_journals.txt').read_text(encoding='utf-8-sig'))
        self.assertEqual(len(output),2)
        for entity in output:
            body=entity['body']
            conditional=next(v for v in recursive_blocks(body,blocks)
                             if v['key']=='trigger_if' and 'te_tax_code_full = yes' in normalized(v['body']))
            following=next(v for v in recursive_blocks(body,blocks)
                           if v['key']=='trigger_else' and v['start']>conditional['end'])
            restored=body[:conditional['start']]+following['body']+body[following['end']:]
            self.assertEqual(normalized(restored),normalized(original[entity['key']]['body']))

    def test_technology_and_principle_modifiers_keep_both_models(self):
        tech={v['key']:{f['key']:f for f in fields(v['body'])}
              for v in blocks((OUTPUT/'common/technology/technologies/zzzzzz_tbcp_technologies.txt').read_text(encoding='utf-8-sig'))}
        self.assertIn('feminism_researched',tech['feminism']['on_researched']['value'])
        self.assertIn('state_contraception_add',tech['feminism']['modifier']['value'])
        self.assertIn('country_institution_culture_max_investment_add',tech['mass_propaganda']['modifier']['value'])
        self.assertIn('country_sol_expectations_target_add',tech['mass_propaganda']['modifier']['value'])
        principles=blocks((OUTPUT/'common/power_bloc_principles/zzzzzz_tbcp_principles.txt').read_text(encoding='utf-8-sig'))
        creative=next(v for v in principles if v['key']=='principle_creative_legislature_3')['body']
        self.assertIn('country_bpm_ruler_complete_veto_enabled = no',creative)
        self.assertIn('country_legislative_override_capacity_add = 2',creative)
        self.assertIn('te_pb_principle_slot_free',creative)

    def test_franchise_override_preserves_te_power_bloc_rules(self):
        relative='common/scripted_rules/00_scripted_rules.txt'
        te=Path(self.lock['mods']['timeline']['mod_root'])
        before={v['key']:v['body'] for v in blocks((te/relative).read_text(encoding='utf-8-sig'))}
        after={v['key']:v['body'] for v in blocks((OUTPUT/relative).read_text(encoding='utf-8-sig'))}
        self.assertEqual(before.keys(),after.keys())
        for key,value in before.items():
            if key=='has_voting_franchise':self.assertEqual(normalized(after[key]),'bpm_country_has_elections = yes')
            else:self.assertEqual(normalized(value),normalized(after[key]),key)
        self.assertFalse(blocks((OUTPUT/'common/scripted_rules/zzz_bpm_scripted_rules.txt').read_text(encoding='utf-8-sig')))

    def test_tax_support_offers_and_civil_war_cover_all_bpm_groups(self):
        bpm=Path(self.lock['mods']['bpm']['mod_root'])
        groups={v['key'].removeprefix('ig_') for p in (bpm/'common/interest_groups').glob('*.txt')
                for v in blocks(p.read_text(encoding='utf-8-sig'))}
        report=self.manifest['economic_integration']
        self.assertEqual(groups,set(report['tax_interest_groups']))
        self.assertEqual(len(groups),21)
        values=(OUTPUT/'common/script_values/te_tax_generated_values.txt').read_text(encoding='utf-8-sig')
        support=(OUTPUT/'common/script_values/te_tax_generated_support_values.txt').read_text(encoding='utf-8-sig')
        effects=(OUTPUT/'common/scripted_effects/te_tax_generated_bill_effects.txt').read_text(encoding='utf-8-sig')
        triggers=(OUTPUT/'common/scripted_triggers/te_tax_generated_triggers.txt').read_text(encoding='utf-8-sig')
        sguis=(OUTPUT/'common/scripted_guis/te_tax_sguis.txt').read_text(encoding='utf-8-sig')
        # Existing obligation/history IDs retain their meaning. New groups
        # are appended and get the entire support/commitment/repair lifecycle.
        for idx,ig in enumerate(report['tax_interest_groups'],start=1):
            self.assertIn(f'te_tax_ig_id_{ig} = {idx}',values)
            self.assertIn(f'te_tax_ig_band_{ig} =',support)
            self.assertIn(f'law_stance = {{ law = law_type:law_graduated_taxation',support)
            self.assertIn(f'te_tax_com_{ig}',effects)
            self.assertIn(f'var:te_tax_o$N$_ig = {idx} exists = ig:ig_{ig}',triggers)
        for ig in report['tax_material_counterparts']:
            self.assertIn(f'te_tax_sup_{ig}',effects)
            self.assertIn(f'te_tax_can_accept_offer = {{ IG = {ig} }}',sguis)
            self.assertIn(f'te_tax_cmd_accept_offer = {{ IG = {ig} }}',sguis)
        # Support totals include actual clout, not the exemplar's clout.
        self.assertTrue('ig:ig_liberals.ig_clout' in support,'Liberal clout absent from tax support')

    def test_construction_compensation_applies_after_removal_and_only_for_market(self):
        relative='common/scripted_effects/te_construction_market_update_effects.txt'
        text=(OUTPUT/relative).read_text(encoding='utf-8-sig')
        body=next(v['body'] for v in blocks(text) if v['key']=='te_construction_market_country_update_private_share')
        self.assertLess(body.index('remove_modifier'),body.index('multiplier = tbcp_construction_private_share'))
        value=(OUTPUT/'common/script_values/zzzzzz_tbcp_construction_values.txt').read_text(encoding='utf-8-sig')
        self.assertIn('limit = { te_free_market_construction_on = yes }',value)
        self.assertIn('value = modifier:country_private_construction_allocation_mult',value)
        te=Path(self.lock['mods']['timeline']['mod_root'])
        original=(te/relative).read_text(encoding='utf-8-sig')
        self.assertEqual(normalized(text.replace('tbcp_construction_private_share','te_construction_market_private_share_target')),
                         normalized(original))

    def fiscal_model(self,full=True,migrated=True,law='law_te_tax_code',level='medium'):
        effects=(OUTPUT/'common/scripted_effects/zzzzzz_tbcp_tax_legacy_effects.txt').read_text(encoding='utf-8-sig')
        triggers=(OUTPUT/'common/scripted_triggers/zzzzzz_tbcp_tax_legacy_triggers.txt').read_text(encoding='utf-8-sig')
        variables={f'te_tax_en_{key}':0 for key in ['wage','div','land','head','cons']}
        variables.update(te_tax_migrated=int(migrated),te_tax_code_version=0,
                         te_tax_pa_on=1,te_tax_o1_on=1,te_tax_en_agrel=2,te_tax_en_regrel=1,
                         te_tax_en_g_grain=1,te_tax_en_imp_grain=3,te_tax_bl_on=1)
        for key in ['wage','div','land','head','cons']:
            variables[f'te_tax_en_{key}_exp']=-1;variables[f'te_tax_en_{key}_succ']=-1
        state={'vars':variables,'full':full,'law':law,'level':level,'day':100,'month':50}
        return FiscalModel(effects,triggers,self.manifest['legacy_tax_integration']['rate_rows'],state)

    def test_all_25_scripted_tax_reforms_match_author_rate_table_and_are_idempotent(self):
        for law,level,rates in self.manifest['legacy_tax_integration']['rate_rows']:
            model=self.fiscal_model(level=level)
            preserved={k:v for k,v in model.state['vars'].items() if not k.startswith('te_tax_en_wage')
                       and k in {'te_tax_pa_on','te_tax_o1_on','te_tax_en_agrel','te_tax_en_regrel',
                                 'te_tax_en_g_grain','te_tax_en_imp_grain','te_tax_bl_on'}}
            command='tbcp_tax_activate_'+LAWS[law]
            model.execute(command)
            for key,value in rates.items():self.assertEqual(model.state['vars']['te_tax_en_'+key],value,(law,level,key))
            self.assertEqual(model.state['law'],'law_te_tax_code')
            self.assertFalse(model.native_laws)
            self.assertEqual(model.events,[{'id':'te_tax.4','days':'1'}])
            for key,value in preserved.items():self.assertEqual(model.state['vars'][key],value)
            from copy import deepcopy
            snapshot=deepcopy(model.state)
            for _ in range(20):model.execute(command)
            self.assertEqual(model.state,snapshot)
            self.assertEqual(len(model.events),1)

    def test_full_tax_reads_have_exactly_one_equivalent_for_all_25_migrations(self):
        for law,level,rates in self.manifest['legacy_tax_integration']['rate_rows']:
            model=self.fiscal_model(level=level)
            for key,value in rates.items():model.state['vars']['te_tax_en_'+key]=value
            for kind in ['has','has_or_variant']:
                actual=[candidate for candidate,short in LAWS.items()
                        if model.check(model.triggers[f'tbcp_tax_{kind}_{short}'])]
                self.assertEqual(actual,[law],(law,level))

    def test_disabled_light_and_unmigrated_tax_modes_keep_native_activation(self):
        for full,migrated in [(False,False),(False,True),(True,False)]:
            for law,short in LAWS.items():
                model=self.fiscal_model(full,migrated,'law_land_based_taxation')
                from copy import deepcopy
                variables=deepcopy(model.state['vars'])
                model.execute('tbcp_tax_activate_'+short)
                self.assertEqual(model.state['law'],law)
                self.assertEqual(model.state['vars'],variables)
                self.assertFalse(model.events)
                for candidate,cshort in LAWS.items():
                    self.assertEqual(model.check(model.triggers['tbcp_tax_has_'+cshort]),candidate==law)

    def test_multiple_same_day_reforms_coalesce_sync_and_next_day_can_schedule(self):
        model=self.fiscal_model()
        for short in ['per_capita','graduated','land_based']:model.execute('tbcp_tax_activate_'+short)
        self.assertEqual(len(model.events),1)
        self.assertEqual(model.state['vars']['te_tax_code_version'],3)
        model.state['day']+=1
        model.execute('tbcp_tax_activate_proportional')
        self.assertEqual(len(model.events),2)

    def test_tax_rewriter_leaves_comments_strings_and_other_operators_opaque(self):
        text='# has_law = law_type:law_graduated_taxation\nx = "activate_law = law_type:law_land_based_taxation"\n'
        self.assertEqual(rewrite_tax(text)[0],text)
        text+='has_law_or_variant = law_type:law_proportional_taxation\nis_enacting_law = law_type:law_graduated_taxation'
        changed,counts=rewrite_tax(text)
        self.assertIn('tbcp_tax_has_or_variant_proportional = yes',changed)
        self.assertIn('is_enacting_law = law_type:law_graduated_taxation',changed)
        self.assertEqual(counts,{'reads':1,'activations':0})

    def test_shadow_masks_keep_every_retained_definition_verbatim(self):
        report=json.loads((ROOT/'docs/conflicts/shadow-definitions.json').read_text(encoding='utf-8'))
        research=json.loads((ROOT/'docs/research/2026-11-07-github-overlap.json').read_text(encoding='utf-8'))
        game=Path(research['sources']['game']['root'])
        removed={}
        for entry in report['shadow_definitions_resolved']:
            for relative in entry['suppressed_paths']:removed.setdefault(relative,set()).add(entry['key'])
        self.assertGreaterEqual(len(report['shadow_definitions_resolved']),500)
        for relative in report['files_masked']:
            before={v['key']:v for v in top_spans((game/relative).read_text(encoding='utf-8-sig'))}
            after={v['key']:v for v in top_spans((OUTPUT/relative).read_text(encoding='utf-8-sig'))}
            self.assertEqual(before.keys()-removed[relative],after.keys(),relative)
            for key,node in after.items():self.assertEqual(normalized(node['raw']),normalized(before[key]['raw']),relative+'/'+key)

    def test_checkpoint_uses_one_bpm_effect_without_vanilla_phase_increment(self):
        relative='common/on_actions/00_code_on_actions.txt'
        self.assertNotIn('on_law_checkpoint_success',{v['key'] for v in blocks((OUTPUT/relative).read_text(encoding='utf-8-sig'))})
        bpm=Path(self.lock['mods']['bpm']['mod_root'])
        source=(bpm/'common/on_actions/BPM_law_enactment_on_actions.txt').read_text(encoding='utf-8-sig')
        self.assertEqual(len([v for v in blocks(source) if v['key']=='on_law_checkpoint_success']),1)

    def test_future_parties_preserve_weights_and_obey_bpm_activation_and_bans(self):
        te=Path(self.lock['mods']['timeline']['mod_root'])
        emitted=blocks((OUTPUT/'common/parties/zzzzzz_tbcp_future_parties.txt').read_text(encoding='utf-8-sig'))
        self.assertEqual({v['key'] for v in emitted},{'green_party','populist_party','technocratic_party'})
        helpers=(OUTPUT/'common/scripted_triggers/zzzzzz_tbcp_future_party_bans.txt').read_text(encoding='utf-8-sig')
        for node in emitted:
            original=blocks((te/'common/parties'/f'{node["key"]}.txt').read_text(encoding='utf-8-sig'))[0]
            before={v['key']:v for v in fields(original['body'])};after={v['key']:v for v in fields(node['body'])}
            self.assertEqual(before.keys(),after.keys())
            for key in before:
                if key=='available_for_interest_group':
                    self.assertTrue(normalized(after[key]['value']).startswith(normalized(before[key]['value'])))
                    self.assertIn('bpm_interest_group_is_activated = yes',after[key]['value'])
                    self.assertIn('PARTY = '+node['key'],after[key]['value'])
                else:self.assertEqual(normalized(before[key]['value']),normalized(after[key]['value']))
            self.assertIn('bpm_is_'+node['key']+'_banned',helpers)

    def test_linear_tax_ai_matches_original_order_in_1500_synthetic_states(self):
        import random
        rng=random.Random(20261107)
        igs=self.manifest['economic_integration']['tax_interest_groups']
        text=(OUTPUT/'common/scripted_effects/te_tax_generated_effects.txt').read_text(encoding='utf-8-sig')
        function=next(n['raw'] for n in blocks(text) if n['key']=='te_tax_gen_ai_accept_offer')
        model=FiscalModel(function,'',[],{'vars':{},'ai':{}})
        maximum_steps=0
        for case in range(1500):
            data={ig:{'clout':rng.choice([0,0.01,0.05,0.15,0.3,0.6]),
                       'eligible':rng.random()>0.2,'acceptable':rng.random()>0.4,
                       'persuadable':rng.random()>0.5} for ig in igs}
            if case==0:
                for row in data.values():row.update(eligible=True,acceptable=True,persuadable=True,clout=0.05)
            if case==1:
                for row in data.values():row['acceptable']=False
            expected=sorted(((not row['persuadable'],-row['clout'],index,ig)
                             for index,(ig,row) in enumerate(data.items()) if row['eligible'] and row['acceptable']))
            model.state={'vars':{},'ai':data};model.locals={};model.accepted=[];model.steps=0
            model.execute('te_tax_gen_ai_accept_offer')
            self.assertEqual(model.accepted,[expected[0][3]] if expected else [],case)
            maximum_steps=max(maximum_steps,model.steps)
        self.assertLessEqual(maximum_steps,21*20+32,'Linear-selection synthetic instruction budget exceeded')
        report=self.manifest['economic_integration']['ai_offer_optimization']
        self.assertLess(report['new_ast_fields'],report['old_ast_fields']//4)
        self.assertNotIn('te_tax_ai_clout_rank_',function)

    def test_generated_triggers_and_values_have_no_persistent_side_effects(self):
        forbidden={'set_variable','change_variable','remove_variable','add_modifier','remove_modifier',
                   'trigger_event','activate_law','create_country','create_character','add_journal_entry'}
        for category in ['common/scripted_triggers','common/script_values']:
            for path in (OUTPUT/category).glob('*.txt'):
                keys={f.key for f in walk(ast_parse(path.read_text(encoding='utf-8-sig')))}
                self.assertFalse(keys & forbidden,(path.name,keys & forbidden))

    def test_tax_sync_burst_drains_instead_of_building_an_event_recursion(self):
        te=Path(self.lock['mods']['timeline']['mod_root'])
        source=(te/'common/scripted_effects/te_tax_collection_effects.txt').read_text(encoding='utf-8-sig')
        defer=next(v['raw'] for v in blocks(source) if v['key']=='te_tax_defer_sync')
        model=self.fiscal_model()
        from script_syntax import parse as parse_ast,Field
        model.effects.update({v.key:v.value for v in parse_ast(defer) if isinstance(v,Field)})
        # Multiple native/compatibility entry points on the same day. The
        # adapter schedules once; TE's native daily guard may defer once.
        for _ in range(50):model.execute('tbcp_tax_queue_sync')
        self.assertEqual(len(model.events),1)
        queue={100:50,101:1};model.events=[];syncs=0;processed=0
        for day in range(100,104):
            model.state['day']=day
            for _ in range(queue.pop(day,0)):
                processed+=1
                if model.state['vars'].get('te_tax_sync_day',-1)>=day:
                    model.execute('te_tax_defer_sync')
                else:model.state['vars']['te_tax_sync_day']=day;syncs+=1
                for event in model.events:
                    self.assertEqual(event,{'id':'te_tax.4','days':'1'})
                    queue[day+1]=queue.get(day+1,0)+1
                model.events=[]
        self.assertFalse(queue)
        self.assertEqual(syncs,3)
        self.assertEqual(processed,53)

    def test_foreign_coup_event_and_acw_target_are_present_without_restoring_domestic_coups(self):
        te_game=Path(json.loads((ROOT/'docs/research/2026-11-07-github-overlap.json').read_text(encoding='utf-8'))['sources']['game']['root'])
        original=next(n['raw'] for n in blocks((te_game/'events/iberia_events/ip4_coup_events.txt').read_text(encoding='utf-8-sig'))
                      if n['key']=='ip4_coup.11')
        restored=blocks((OUTPUT/'events/tbcp_foreign_coup_events.txt').read_text(encoding='utf-8-sig'))
        self.assertEqual([v['key'] for v in restored],['ip4_coup.11'])
        self.assertEqual(normalized(restored[0]['raw']),normalized(original))
        relative='common/journal_entries/BPM_je_america.txt'
        bpm=Path(self.lock['mods']['bpm']['mod_root'])
        after=(OUTPUT/relative).read_text(encoding='utf-8-sig')
        before=(bpm/relative).read_text(encoding='utf-8-sig')
        self.assertEqual(after,before.replace('id = bpm_acw_events.0001','id = bpm_acw_events.1'))

    def test_unowned_runtime_file_stops_build_instead_of_silently_shipping_it(self):
        path=OUTPUT/'common/scripted_effects/tbcp_synthetic_stale_file.txt'
        self.assertFalse(path.exists())
        self.assertTrue(path.resolve().is_relative_to(OUTPUT.resolve()))
        try:
            path.write_text('stale_effect = { }',encoding='utf-8')
            with self.assertRaisesRegex(AssertionError,'Stale or unowned runtime files'):generate()
        finally:path.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
