"""Preserve BPM membership and generation; append TE-only gender-law/tech branches."""
from law_merge import fields, emit, norm
from inspect_mod_overlap import TOKEN

COUNTERPARTS={
 'ig_agrarian_populists':'ig_rural_folk',
 'ig_anarchists':'ig_trade_unions',
 'ig_christian_democrats':'ig_devout',
 'ig_conservatives':'ig_petty_bourgeoisie',
 'ig_fascists':'ig_petty_bourgeoisie',
 'ig_liberals':'ig_intelligentsia',
 'ig_market_liberals':'ig_industrialists',
 'ig_national_liberals':'ig_petty_bourgeoisie',
 'ig_radicals':'ig_intelligentsia',
 'ig_reactionaries':'ig_landowners',
 'ig_reformist_socialists':'ig_trade_unions',
 'ig_revolutionist_socialists':'ig_trade_unions',
 'ig_socialists':'ig_trade_unions',
}


def build_characters(research,load,parse):
    te_nodes={n['key']:n for n in parse(load('timeline','common/interest_groups/zz_te_ig_female_chance.txt'))}
    game_ids=set();mod_ids=set()
    for label,dest in [('game',game_ids),('timeline',mod_ids)]:
        for rel in research['sources'][label]['files']:
            if (rel.startswith('common/laws/') or rel.startswith('common/technology/technologies/')) and rel.endswith('.txt'):
                dest.update(n['key'] for n in parse(load(label,rel)))
    new_ids=mod_ids-game_ids
    out=[];audit=[]
    for rel in sorted(research['sources']['bpm']['files']):
        if not (rel.startswith('common/interest_groups/') and rel.endswith('.txt')):continue
        for entity in parse(load('bpm',rel)):
            counterpart=COUNTERPARTS.get(entity['key'],entity['key'])
            assert counterpart in te_nodes,entity['key']
            te_fields={n['key']:n for n in parse(te_nodes[counterpart]['body'])}
            target=fields(entity['body']); index={v['key']:i for i,v in enumerate(target)}
            changes=[]
            for key in ['female_commander_chance','female_politician_chance','female_agitator_chance']:
                assert key in index and target[index[key]]['block'],(entity['key'],key)
                source=te_fields[key]
                added=[]
                for branch in parse(source['body']):
                    names={m.group().split(':')[-1] for m in TOKEN.finditer(branch['body']) if not m.group().startswith('#')}
                    if names & new_ids:
                        assert branch['key']=='if','Dependent TE branch requires manual merge'
                        if norm(branch['raw']) not in norm(target[index[key]]['value']):added.append(branch['raw'])
                target[index[key]]['value']+='\n'+'\n'.join(added)
                changes.append({'field':key,'branches_added':len(added)})
            out.append('REPLACE:'+entity['key']+' = {\n'+emit(target)+'}\n')
            audit.append({'ig':entity['key'],'te_counterpart':counterpart,'source':rel,'fields':changes})
    return '\n'.join(out),audit
