"""Construction allocation and TE tax-code adapters for BPM's extra groups."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess

from character_merge import COUNTERPARTS
from law_merge import fields, emit
from tax_ai import optimize as optimize_tax_ai


def build_economy(research,load,parse):
    outputs={}
    # TE removes its allocation modifier before evaluating this multiplier.
    # In FMC mode cancel the remaining BPM law/institution contribution, so
    # the resulting share is exactly TE's purchase ratio. In direct mode keep
    # it: the result is TE's restored base plus BPM's delta and institution.
    relative='common/scripted_effects/te_construction_market_update_effects.txt'
    source=load('timeline',relative)
    node=next(n for n in parse(source) if n['key']=='te_construction_market_country_update_private_share')
    assert node['body'].count('multiplier = te_construction_market_private_share_target')==1
    body=node['body'].replace('multiplier = te_construction_market_private_share_target',
                              'multiplier = tbcp_construction_private_share')
    outputs[relative]=source[:node['start']]+'te_construction_market_country_update_private_share = {'+body+'}'+source[node['end']:]
    outputs['common/script_values/zzzzzz_tbcp_construction_values.txt']='''
# Country scope. Evaluated after the previous TE share modifier is removed.
tbcp_construction_private_share = {
    value = te_construction_market_private_share_target
    if = {
        limit = { te_free_market_construction_on = yes }
        subtract = {
            value = modifier:country_private_construction_allocation_mult
            multiply = 100
        }
    }
}
'''

    # Extend the author's generator in memory. It already generates the whole
    # support/offer/promise/AI/civil-war/GUI lifecycle from a single IG tuple.
    # Never call its writer or change the upstream checkout.
    root=Path(research['sources']['timeline']['root'])
    tree=subprocess.check_output(['git','-C',str(root),'ls-tree','-r','HEAD'],text=True,encoding='utf-8')
    tracked={line.split('\t',1)[1]:line.split()[2] for line in tree.splitlines()}
    verified={}
    def checked(relative):
        data=(root/relative).read_bytes()
        expected=tracked[relative]
        def blob(value):return hashlib.sha1(b'blob '+str(len(value)).encode()+b'\0'+value).hexdigest()
        assert expected in {blob(data),blob(data.replace(b'\r\n',b'\n'))},'Generator input drift: '+relative
        verified[relative]=hashlib.sha256(data).hexdigest()
        return data
    code='scripts/generators/gen_tax_code.py'
    for relative in [code,'paradox_file_parser.py','organize_loc.py','path_constants.py','scripts/_path_detect.py',
                     'vanilla_parsed/common/pop_needs.json','vanilla_parsed/common/goods.json']:
        checked(relative)
    for relative in research['sources']['timeline']['files']:
        if relative.startswith(('common/goods/','common/pop_needs/')) and relative.endswith('.txt'):
            load('timeline',relative)
    spec=importlib.util.spec_from_file_location('tbcp_pinned_te_tax_generator',root/code)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    baseline=module.render_all()
    for relative,data in baseline.items():
        source=checked(relative)
        assert source.replace(b'\r\n',b'\n')==data.replace(b'\r\n',b'\n'),'Upstream generator drift: '+relative
    extra={ig.removeprefix('ig_'):source.removeprefix('ig_') for ig,source in COUNTERPARTS.items()}
    old_igs=module.IGS
    assert len(old_igs)==8 and len(extra)==13 and not(set(old_igs)&set(extra))
    module.IGS=old_igs+tuple(sorted(extra))
    module.AI_RANK_LAST=len(module.IGS)
    for ig,source in extra.items():
        module.EXPOSURE[ig]=module.EXPOSURE[source]
        for table in [module.AGREL_POINTS,module.REGREL_POINTS_CONCERN]:
            if source in table:table[ig]=table[source]
    module.PROMISE_OFFERS=tuple((name,kind,arg,target,groups+tuple(ig for ig,source in sorted(extra.items()) if source in groups))
                               for name,kind,arg,target,groups in module.PROMISE_OFFERS)
    adapted=module.render_all()
    changed=[]
    for relative,data in adapted.items():
        if data==baseline[relative]:continue
        assert relative not in outputs,relative
        outputs[relative]=data.decode('utf-8-sig')
        changed.append(relative)
    # Cards use AccessAllInterestGroups, but their Accept action has a manual
    # type dispatch outside the generator. Extend both validity and execution;
    # otherwise new groups would display an offer that could never be accepted.
    relative='common/scripted_guis/te_tax_sguis.txt'
    source=load('timeline',relative)
    node=next(v for v in parse(source) if v['key']=='te_tax_cmd_accept_offer_sgui')
    items=fields(node['body'])
    for item in items:
        if item['key'] not in {'is_valid','effect'}:continue
        condition=item['key']=='is_valid'
        branch_name='trigger_else_if' if condition else 'else_if'
        command='te_tax_can_accept_offer' if condition else 'te_tax_cmd_accept_offer'
        additions='\n'.join(f'''{branch_name} = {{
            limit = {{ exists = scope:te_tax_ig scope:te_tax_ig = {{ is_interest_group_type = ig_{ig} }} }}
            {command} = {{ IG = {ig} }}
        }}''' for ig in sorted(extra))
        if condition:
            fallback='trigger_else = { always = no }'
            assert item['value'].count(fallback)==1
            item['value']=item['value'].replace(fallback,additions+'\n'+fallback)
        else:item['value']+='\n'+additions
    outputs[relative]=source[:node['start']]+'te_tax_cmd_accept_offer_sgui = {\n'+emit(items)+'}'+source[node['end']:]
    changed.append(relative)
    relative='common/scripted_effects/te_tax_generated_effects.txt'
    outputs[relative],ai_report=optimize_tax_ai(outputs[relative],module.IGS,parse)
    report={'construction':'FMC absolute target after cancelling BPM residual; direct mode preserves BPM delta',
            'tax_interest_groups':list(module.IGS),'tax_material_counterparts':extra,
            'tax_files_regenerated':changed,'tax_generator_inputs':verified,
            'original_tax_ig_ids_preserved':list(old_igs),'engine_verified':False,
            'tax_migration_rows':module.migration_indices(),
            'ai_offer_optimization':ai_report,
            'balance_policy':'explicit TE material-exposure exemplars; actual BPM IG law_stance supplies fiscal ideology'}
    return outputs,report
