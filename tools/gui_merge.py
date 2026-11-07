"""Resolve observed TE/BPM GUI names by same-path overrides; no desktop access."""
import re
from inspect_mod_overlap import TOKEN


def declarations(text):
    tokens=[m for m in TOKEN.finditer(text) if not m.group().startswith('#')]
    out=[]
    for i,tok in enumerate(tokens):
        if tok.group()!='type' or i+4>=len(tokens):continue
        if tokens[i+2].group()!='=' or tokens[i+4].group()!='{':continue
        opening=i+4;j=opening+1;depth=1
        while j<len(tokens) and depth:
            depth+=(tokens[j].group()=='{')-(tokens[j].group()=='}');j+=1
        if depth:raise ValueError('Unclosed GUI type '+tokens[i+1].group())
        out.append({'key':tokens[i+1].group(),'start':tok.start(),'end':tokens[j-1].end(),
                    'opening':tokens[opening].end(),'closing':tokens[j-1].start(),
                    'body':text[tokens[opening].end():tokens[j-1].start()]})
    return out


def edit(text,changes):
    for start,end,value in sorted(changes,reverse=True):text=text[:start]+value+text[end:]
    return text


def build_gui(research,load,parse):
    indexed={}
    for label in ['timeline','bpm']:
        indexed[label]={}
        for rel in sorted(research['sources'][label]['files']):
            if not(rel.startswith('gui/') and rel.endswith('.gui')):continue
            text=load(label,rel)
            for node in declarations(text):
                indexed[label].setdefault(node['key'],[]).append((rel,node))
    shared=indexed['timeline'].keys() & indexed['bpm'].keys()
    assert len(shared)==8,'GUI registry changed: review collisions'
    outputs={};removed={}
    for key in sorted(shared):
        assert len(indexed['timeline'][key])==len(indexed['bpm'][key])==1,key
        rel,node=indexed['timeline'][key][0]
        removed.setdefault(rel,[]).append((node['start'],node['end'],f'# {key}: provided by BPM via compatibility policy.'))
    for rel,changes in removed.items():
        text=edit(load('timeline',rel),changes)
        outputs[rel]=text

    # Preserve TE's Nation navigation without replacing BPM's country layout.
    rel='gui/00_te_country_panel_information.gui'
    te=load('timeline',rel)
    start=te.index('### MOD: Nation tab:')
    end=te.index('### END MOD ###',start)
    fragment=te[start:end]
    navigation=next(v['raw'] for v in parse(fragment) if v['key']=='flowcontainer')
    bpm_rel='gui/BPM_country_panel.gui'
    text=load('bpm',bpm_rel)
    country=next(v for v in declarations(text) if v['key']=='country_panel_information_content')
    outputs[bpm_rel]=text[:country['closing']]+'\n# TE Nation navigation\n'+navigation+'\n'+text[country['closing']:]

    # Preserve TE's lazy tax effect rows in BPM's legislative interface. Hide
    # BPM's ordinary effect/preview rows for tax laws to avoid duplicate output.
    te_rel='gui/00_te_law_effects.gui'
    source=load('timeline',te_rel)
    panel=next(v for v in declarations(source) if v['key']=='selected_or_enacting_law_content')
    marker=panel['body'].index("### MOD: Tax law effects: a taxation law shows the toggle")
    start=panel['body'].index('hbox = {',marker)
    end=panel['body'].index('### law lore',start)
    tax_fragment=panel['body'][start:end]
    assert 'te_law_tax_effects' in tax_fragment and 'te_law_tax_delta_effects' in tax_fragment
    bpm_rel='gui/BPM_politics_panel_change_law.gui'
    text=load('bpm',bpm_rel)
    node=next(v for v in declarations(text) if v['key']=='selected_or_enacting_law_content')
    body=node['body']
    count=0
    def gate(match):
        nonlocal count
        expression=match.group(1)
        if 'GetEffectDesc(' not in expression and 'GetDeltaEffectDesc(' not in expression:return match.group()
        count+=1
        return 'visible = "[And(Not(EqualTo_string(Law.GetGroup.GetKey, \'lawgroup_taxation\')), '+expression+')]"'
    body=re.sub(r'visible\s*=\s*"\[([^\n]*?)\]"',gate,body)
    assert count==5,'BPM effect layout changed'
    body+='\n# TE lazy tax effects\n'+tax_fragment+'\n'
    outputs[bpm_rel]=text[:node['opening']]+body+text[node['closing']:]
    return outputs,{'resolved_type_names':sorted(shared),'removed_from_te':{k:len(v) for k,v in removed.items()},
                    'nation_navigation_preserved':True,'tax_effect_rows_preserved':True,
                    'bpm_effect_rows_gated':count,'render_verified':False}
