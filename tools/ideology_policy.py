"""Explicit, reviewable correspondences for BPM axes and TE law positions.

Only TE-added laws are imported into existing groups. Original BPM positions
never change. New groups are owned by one BPM axis to avoid competing priority
1000 positions. Missing TE opinions remain absent, not invented.
"""
from law_merge import fields, emit

OWNERS = {
 'eco':'antitrust financial_regulation genetic_rights inheritance intellectual_property monetary_policy national_bank ministry_of_commerce',
 'cit':'minority_rights language_policy',
 'dop':'electoral_finance',
 'fem':'LGBTQ_rights bodily_autonomy family_reproductive_policy human_augmentation',
 'mil':'rules_of_war ministry_of_war ministry_of_foreign_affairs',
 'rel':'ministry_of_religion',
 'sta':'criminal_justice judiciary state_power privacy_rights internet_governance ministry_of_culture ministry_of_propaganda ministry_of_science ministry_of_thought_control ministry_of_intelligence_and_security frontier_ai_control right_to_information',
 'wel':'automation_policy ministry_of_the_environment resource_transition ministry_of_labor ministry_of_refugee_affairs ministry_of_consumer_protection ministry_of_urban_planning ministry_of_international_aid',
}

# Every row is deliberate. This is data, not a keyword classifier.
# TE's existing profile supplies values only for the lawgroups owned by this
# axis, plus TE-only laws in groups where this BPM ideology already has views.
ROWS = {
 'eco': {
  'market_liberal':'laissez_faire artisan',
  'liberal':'interventionist modern_interventionist american_system',
  'agrarian':'traditional_agrarian modern_agrarian conservative_agrarian distributist_economy',
  'state_socialist':'agrarian_socialist socialist_mixed_economy',
  'patriotic':'autarky agrarian_autarky',
  'communist_leader':'socialist_autarky centralized_economy',
  'proletarian':'proletarian_economy',
  'paternalistic':'serf_economy debt_serf_economy slave_economy antebellum_economy',
  'traditionalist':'trad_isolationist',
  'technocratic':'modernizer',
  'colonialist':'colonialist slave_colonialist colonial_slavery_supporter',
 },
 'cit': {
  'humanitarian':'internationalist closed_internationalist',
  'liberal':'immigrant_nationalist liberal_nationalist multiethnic_nationalist',
  'patriotic':'nationalist',
  'reactionary':'segregationist ethnonationalist',
  'colonialist':'colonial_segregationist',
  'traditionalist':'traditional_culture samurai',
  'pious':'christian_internationalist',
 },
 'dop': {
  'communist_leader':'party_socialist party_state',
  'anarchist':'anarchist anarcho_syndicalist',
  'radical':'radical_democrat dissent syndical_unionist syndicalist',
  'liberal':'moderate_democrat',
  'paternalistic':'authoritarian_democrat autocrat traditional_power',
  'oligarchic':'oligarch',
  'technocratic':'technocrat',
  'authoritarian':'state_power state_unionist anti_unionist organic_power',
  'meritocratic':'meritocratic_autocrat',
  'proletarian':'unionist',
  'patriotic':'metropole_loyalist',
  'moralist':'divine_democrat',
  'reformer':'christian_democrat',
  'traditionalist':'conservative_democrat organic_democrat',
 },
 'fem': {'feminist':'gender_egalitarian','liberal':'benevolent_sexism',
         'patriarchal':'moderate_patriarchal patriarchal'},
 'gov': {'liberal':'liberal_republican','radical':'radical_republican',
         'state_socialist':'moderate_proletarian','communist_leader':'radical_proletarian',
         'royalist':'moderate_monarchist radical_monarchist','theocrat':'theocrat',
         'reactionary':'anti_proletarian'},
 'mil': {'jingoist':'ultramilitarist emergency frontier_expansion',
         'patriotic':'patriotic patriotic_liberal mass_army institutional_militarist',
         'pacifist':'defensive_patriot antimilitarist',
         'proletarian':'popular_army','paternalistic':'aristocratic_militarist',
         'plutocratic':'plutocratic_militarist'},
 'rel': {'anti_clerical':'atheist radical_secularist','liberal':'secularist',
         'moralist':'moralist radical_moralist','pious':'pragmatic_moralist modern_moralist'},
 'sta': {'anarchist':'minimal_state','particularist':'decentralized_state devolved_state federated_state regionalized_state',
         'liberal':'weak_state','authoritarian':'powerful_state security_state subjugated_security_state',
         'radical':'progressive_state','paternalistic':'subjugated_state organic_state',
         'meritocratic':'effective_state institutional_state'},
 'wel': {'state_socialist':'expanded_public_welfare public_welfare social_market_welfare',
         'paternalistic':'paternalistic_welfare reactionary_paternalistic',
         'market_liberal':'market_welfare no_welfare secular_anti_welfare',
         'moralist':'religious_welfare','agrarian':'distributist_welfare'},
}

# Narrow additional correspondences where the primary TE profile has no view.
# Genetic rights are assigned to the economic/property axis (licensing,
# inheritance and ownership), while bodily autonomy remains on the rights axis.
SECONDARY = {
 'ideology_eco_laissez_faire':{'lawgroup_ministry_of_commerce':'ideology_corporate'},
 'ideology_eco_artisan':{'lawgroup_ministry_of_commerce':'ideology_custom_religion_free_market_economy'},
 'ideology_eco_interventionist':{'lawgroup_ministry_of_commerce':'ideology_custom_religion_social_democratic_economy'},
 'ideology_eco_modern_interventionist':{'lawgroup_ministry_of_commerce':'ideology_custom_religion_social_democratic_economy'},
 'ideology_wel_religious_welfare':{'lawgroup_ministry_of_international_aid':'ideology_pious'},
}


def make_policy(research, load, parse):
    expected=set(research['timeline_new_lawgroups'])
    ownership={'lawgroup_'+group:axis for axis,groups in OWNERS.items() for group in groups.split()}
    assert set(ownership)==expected, 'New or removed TE group needs policy review'
    te={}
    for rel in sorted(research['sources']['timeline']['files']):
        if rel.startswith('common/ideologies/') and rel.endswith('.txt'):
            for node in parse(load('timeline',rel)):te[node['key']]=node
    game_laws=set(); te_laws=set()
    for label,dest in [('game',game_laws),('timeline',te_laws)]:
        for rel in research['sources'][label]['files']:
            if rel.startswith('common/laws/') and rel.endswith('.txt'):
                for node in parse(load(label,rel)):dest.add(node['key'])
    new_laws=te_laws-game_laws
    mapping={}
    for axis,rows in ROWS.items():
        for profile,variants in rows.items():
            source='ideology_'+profile
            assert source in te,source
            for variant in variants.split():
                target=f'ideology_{axis}_{variant}'
                assert target not in mapping,target
                mapping[target]=(axis,source)
    mapping['ideology_jingoist']=('mil','ideology_jingoist')
    evidence=[];group_coverage=set();changed={};seen=set()
    for rel in sorted(research['sources']['bpm']['files']):
        if not (rel.startswith('common/ideologies/bpm_') and rel.endswith('_ig_ideologies.txt')):continue
        for node in parse(load('bpm',rel)):
            if node['key'] not in mapping:continue
            seen.add(node['key'])
            axis,profile=mapping[node['key']]
            source_groups={v['key']:v for v in fields(te[profile]['body']) if v['block'] and v['key'].startswith('lawgroup_')}
            group_profiles={key:profile for key in source_groups}
            for group,other_profile in SECONDARY.get(node['key'],{}).items():
                assert group not in source_groups, 'Primary TE profile acquired an opinion: review secondary mapping'
                other=next(v for v in fields(te[other_profile]['body']) if v['key']==group)
                source_groups[group]=other;group_profiles[group]=other_profile
            target=fields(node['body']);index={v['key']:i for i,v in enumerate(target)}
            additions=0
            for group,stance_block in source_groups.items():
                if group in expected and ownership[group]!=axis:continue
                if group not in expected and group not in index:continue
                old=fields(target[index[group]]['value']) if group in index else []
                old_names={v['key'] for v in old}
                entries=[v for v in fields(stance_block['value']) if v['key'] not in old_names and (group in expected or v['key'] in new_laws)]
                if not entries:continue
                if group in index:target[index[group]]['value']=emit(old+entries)
                else:index[group]=len(target);target.append({'key':group,'block':True,'value':emit(entries)})
                additions+=len(entries)
                if group in expected:group_coverage.add(group)
                for entry in entries:
                    evidence.append({'target':node['key'],'axis':axis,'source_profile':group_profiles[group],
                                     'group':group,'law':entry['key'],'stance':entry['value']})
            if additions:changed[node['key']]=emit(target)
    assert set(mapping)<=seen, 'Unknown BPM mapping targets: '+str(sorted(set(mapping)-seen))
    return changed,{'correspondences':mapping,'stances':evidence,'covered_new_groups':sorted(group_coverage),
                    'uncovered_new_groups':sorted(expected-group_coverage),
                    'changed_ideologies':len(changed),'added_stances':len(evidence)}
