"""Build the isolated, experimental first integration module of SPEC-002.

This deliberately does not claim complete compatibility. Unknown political
and GUI merges stay open rather than being guessed by a generic deep merge.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess

from inspect_mod_overlap import TOKEN
from law_merge import inject as inject_law
from party_merge import build_parties
from ideology_policy import make_policy
from character_merge import build_characters
from gui_merge import build_gui
from remaining_merge import build_remaining
from economic_adapters import build_economy
from legacy_tax import integrate as integrate_legacy_tax
from safety_merge import integrate as integrate_safety
from cabinet_adapters import integrate as integrate_cabinet

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "patch"
REPORT = ROOT / "docs/research/2026-11-07-github-overlap.json"
VERSION = '0.6.0-dev'


def blocks(text: str) -> list[dict]:
    """Lossless first-level block spans; quoted braces and comments are opaque.

    Scalar and typed literals are preserved in the containing body. Nothing
    here resolves engine injection semantics or collapses duplicate keys.
    """
    tokens = [m for m in TOKEN.finditer(text) if not m.group().startswith('#')]
    result = []
    i = 0
    while i + 2 < len(tokens):
        if tokens[i+1].group() != '=' or tokens[i+2].group() != '{':
            i += 1
            continue
        start, opening = i, i+2
        depth, i = 1, i+3
        while i < len(tokens) and depth:
            if tokens[i].group() == '{': depth += 1
            if tokens[i].group() == '}': depth -= 1
            i += 1
        if depth:
            raise ValueError('Unclosed block: ' + tokens[start].group())
        name = tokens[start].group()
        operation, key = name.split(':', 1) if ':' in name else ('DEFINE', name)
        result.append(dict(key=key, operation=operation, start=tokens[start].start(),
                           end=tokens[i-1].end(), body=text[tokens[opening].end():tokens[i-1].start()],
                           raw=text[tokens[start].start():tokens[i-1].end()]))
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(body: str) -> str:
    return ' '.join(m.group() for m in TOKEN.finditer(body) if not m.group().startswith('#'))


def write(relative: str, text: str) -> None:
    path = OUTPUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8-sig', newline='\n')


def generate() -> dict:
    lock = json.loads((ROOT/'sources.lock.json').read_text(encoding='utf-8'))
    assert digest(REPORT) == lock['research_reports']['github']['sha256'], 'Research report changed'
    research = json.loads(REPORT.read_text(encoding='utf-8'))
    for name in ('timeline', 'bpm'):
        config = lock['mods'][name]
        current = subprocess.check_output(['git', '-C', config['checkout'], 'rev-parse', 'HEAD'], text=True).strip()
        assert current == config['commit'], f'{name}: wrong commit'
    cache = {}

    def definition(source: str, record: dict) -> dict:
        relative = record['path']
        cache_key = source, relative
        if cache_key not in cache:
            path = Path(research['sources'][source]['root']) / relative
            expected = research['sources'][source]['files'][relative]['sha256']
            assert digest(path) == expected, f'Input drift: {path}'
            cache[cache_key] = blocks(path.read_text(encoding='utf-8-sig'))
        candidates = [v for v in cache[cache_key] if v['key'] == record['key'] and v['operation'] == record['operation']]
        assert candidates and len({normalized(v['body']) for v in candidates}) == 1, f'Ambiguous input: {source}/{relative}/{record["key"]}'
        return candidates[0]

    common = research['comparisons']['timeline_bpm']['shared_entities']
    def source_text(label,relative):
        path=Path(research['sources'][label]['root'])/relative
        assert digest(path)==research['sources'][label]['files'][relative]['sha256'],f'Input drift: {path}'
        return path.read_text(encoding='utf-8-sig')
    axis_bodies,axis_report=make_policy(research,source_text,blocks)
    provenance = []
    pm_output = []
    for entry in common:
        if entry['category'] != 'common/production_methods': continue
        replacements = [r for r in entry['left'] if r['operation'] == 'REPLACE']
        if not replacements: continue
        assert len(replacements) == 1 and len(entry['left']) == 1, 'Needs explicit TE injection composition'
        body = definition('timeline', replacements[0])['body']
        fields = {field['key'] for field in blocks(body)}
        additions = []
        for record in entry['right']:
            assert record['operation'] == 'INJECT'
            for field in blocks(definition('bpm', record)['body']):
                assert field['key'] == 'disallowing_amendments', 'Unreviewed production field'
                assert field['key'] not in fields, 'Existing restriction needs manual list merge'
                fields.add(field['key'])
                additions.append(field['raw'])
        assert additions
        merged = body.rstrip() + '\n\t' + '\n\t'.join(additions) + '\n'
        pm_output.append(f'REPLACE:{entry["key"]} = {{{merged}}}\n')
        provenance.append(dict(requirements=['FR-09'], conflict='CON-007', key=entry['key'],
                               category=entry['category'], decision='TE recipe unchanged; append BPM amendment exclusion',
                               inputs=entry['left'] + entry['right']))
    assert len(pm_output) == 6

    ideology_output = []
    added_groups = 0
    leader_count = 0
    new_groups = set(research['timeline_new_lawgroups'])
    for entry in common:
        if entry['category'] != 'common/ideologies': continue
        assert len(entry['left']) == 1
        assert len({normalized(definition('bpm', r)['body']) for r in entry['right']}) == 1
        bpm = definition('bpm', entry['right'][0])
        bpm = dict(bpm,body=axis_bodies.get(entry['key'],bpm['body']))
        te = definition('timeline', entry['left'][0])
        existing = {v['key'] for v in blocks(bpm['body'])}
        # The same named character ideology is an explicit correspondence.
        # Empty vanilla IG placeholders must remain empty in BPM.
        character = bool(re.search(r'\bcharacter_ideology\s*=\s*yes\b', normalized(bpm['body'])))
        additions = [v for v in blocks(te['body']) if character and v['key'] in new_groups and v['key'] not in existing]
        body = bpm['body'].rstrip()
        if additions:
            body += '\n\t' + '\n\t'.join(v['raw'] for v in additions)
            leader_count += 1
            added_groups += len(additions)
        ideology_output.append(f'REPLACE:{entry["key"]} = {{{body}\n}}\n')
        provenance.append(dict(requirements=['FR-04', 'FR-05'], conflict='CON-001', key=entry['key'],
                               category=entry['category'], decision='BPM intact; identical character ideology receives only TE-only lawgroups',
                               added_lawgroups=[v['key'] for v in additions], inputs=entry['left'] + entry['right']))
    assert len(ideology_output) == 103

    # Laws: choose the existing complete replacement, then explicitly compose
    # additive modifiers, trigger conjunctions, effect sequences and list unions.
    # This does not add the old vanilla body over a BPM replacement.
    vanilla={}
    for path in sorted((Path(research['sources']['game']['root'])/'common/laws').glob('*.txt')):
        relative=path.relative_to(Path(research['sources']['game']['root'])).as_posix()
        assert digest(path)==research['sources']['game']['files'][relative]['sha256'],f'Game drift: {relative}'
        for entity in blocks(path.read_text(encoding='utf-8-sig')):vanilla[entity['key']]=entity['body']
    laws=[]
    approved_overrides={'law_agrarianism':{'ai_enact_weight_modifier'},
                        'law_interventionism':{'progressiveness','ai_enact_weight_modifier'},
                        'law_laissez_faire':{'progressiveness','ai_enact_weight_modifier'},
                        'law_militarized_police':{'progressiveness','ai_enact_weight_modifier'}}
    for entry in common:
        if entry['category']!='common/laws':continue
        replacements=[(label,r) for label,side in [('timeline','left'),('bpm','right')]
                      for r in entry[side] if r['operation']=='REPLACE']
        assert len(replacements)<=1, 'Two full law replacements require an explicit decision'
        body=definition(*replacements[0])['body'] if replacements else vanilla[entry['key']]
        for label,side in [('timeline','left'),('bpm','right')]:
            for record in entry[side]:
                if record['operation']=='INJECT':
                    try:
                        body=inject_law(body,definition(label,record)['body'],
                                        approved_overrides.get(entry['key'],()) if label=='bpm' else (),
                                        'incoming' if label=='bpm' else 'existing')
                    except ValueError as error:
                        raise ValueError(f'{entry["key"]}, {label}, {record["path"]}: {error}') from error
        laws.append(f'REPLACE:{entry["key"]} = {{\n{body}\n}}\n')
        provenance.append(dict(requirements=['FR-06','FR-09','FR-15'],conflict='CON-002',
                               category=entry['category'],key=entry['key'],
                               decision='explicit law composition; BPM political gates, TE economic/social modifiers',
                               inputs=entry['left']+entry['right']))
    assert len(laws)==70

    party_files,party_report=build_parties(research,source_text,blocks)
    character_body,character_report=build_characters(research,source_text,blocks)
    gui_files,gui_report=build_gui(research,source_text,blocks)
    remaining_files,remaining_report=build_remaining(research,source_text,blocks)
    economic_files,economic_report=build_economy(research,source_text,blocks)

    header = '# Generated by tools/build_patch.py. Development candidate; engine acceptance pending.\n'
    generated={}
    generated['common/production_methods/zzzzzz_tbcp_production.txt']=header + '\n'.join(pm_output)
    generated['common/ideologies/zzzzzz_tbcp_ideologies.txt']=header + '\n'.join(ideology_output)
    protected={entry['key'] for entry in common if entry['category']=='common/ideologies'}
    generated['common/ideologies/zzzzzz_tbcp_axes.txt']=header+'\n'.join(
        f'REPLACE:{key} = {{\n{body}\n}}\n' for key,body in sorted(axis_bodies.items()) if key not in protected)
    generated['common/laws/zzzzzz_tbcp_laws.txt']=header + '\n'.join(laws)
    for relative,body in party_files.items():generated[relative]=header+body
    generated['common/interest_groups/zzzzzz_tbcp_characters.txt']=header+character_body
    for relative,body in gui_files.items():generated[relative]=header+body
    for relative,body in remaining_files.items():generated[relative]=header+body
    generated.update(economic_files)
    generated['common/defines/zzzzzz_tbcp_defines.txt']=header + 'NPolitics = {\n\tMAX_INSTITUTION_INVESTMENT = 9\n\tINCOHERENCE_FACTOR = 1\n}\n'
    generated,legacy_report=integrate_legacy_tax(research,source_text,blocks,generated,economic_report['tax_migration_rows'])
    generated,safety_report=integrate_safety(research,source_text,blocks,generated)
    generated,cabinet_report=integrate_cabinet(research,source_text,blocks,generated)
    owned_roots={'common','events','gui','localization','map_data','gfx'}
    existing={p.relative_to(OUTPUT).as_posix() for p in OUTPUT.rglob('*') if p.is_file()
              and p.relative_to(OUTPUT).parts[0] in owned_roots}
    assert not existing-generated.keys(),'Stale or unowned runtime files require review: '+str(sorted(existing-generated.keys()))
    for relative,body in generated.items():write(relative,body)
    metadata = {'name': 'Timeline Extended + BPM — Compatibility (Development)',
                'id': '44a453ae-01a4-49e4-991c-4f1eaa2ae614', 'version': VERSION,
                'supported_game_version': '1.15.0',
                'short_description': 'Development compatibility candidate. Requires pinned TE and full BPM. Runtime acceptance pending; read README.',
                'tags': ['Gameplay', 'Interest Groups'], 'relationships': [],
                'game_custom_data': {'multiplayer_synchronized': True}}
    (OUTPUT/'.metadata').mkdir(parents=True, exist_ok=True)
    (OUTPUT/'.metadata/metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    result = {'version': VERSION, 'status': 'development_candidate_runtime_unverified',
              'source_commits': {n: lock['mods'][n]['commit'] for n in ('timeline','bpm')},
              'production_definitions': len(pm_output), 'protected_bpm_ideologies': len(ideology_output),
              'character_ideologies_extended': leader_count, 'new_lawgroup_blocks': added_groups,
              'composed_laws':len(laws),
              'parties':party_report,
              'axis_integration':{key:value for key,value in axis_report.items() if key not in {'stances','correspondences'}},
              'character_integration':character_report,
              'gui_integration':gui_report,
              'remaining_integration':remaining_report,
              'economic_integration':economic_report,
              'legacy_tax_integration':legacy_report,
              'cabinet_optimization':cabinet_report,
              'safety_integration':{'shadow_definitions_resolved':len(safety_report['shadow_definitions_resolved']),
                                    'files_masked':safety_report['files_masked'],'checkpoint_success':safety_report['checkpoint_success']},
              'engine_load_order_verified': False, 'game_runs_performed': False,
              'open': ['manual Steam load/order and GUI acceptance', 'laws, amendments, cabinet, IG splits and FPTP: runtime acceptance',
                       'tax full/customs: rule-aware legacy reads and idempotent scripted reforms need runtime acceptance',
                       'tax material-exposure correspondences: balance acceptance',
                       'country transitions, demographic and construction profiles: runtime acceptance',
                       'independent full S1-S3 research and feature-retention audit incomplete',
                       'AI, saved-game continuation, late progression and performance acceptance'],
              'provenance': provenance}
    report_dir = ROOT/'docs/validation'
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir/'build-manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (ROOT/'docs/decisions/ideology-correspondences.json').write_text(json.dumps(axis_report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    decisions={
        'common/amendments':'BPM tradition with TE allowed-law extensions; ADR-003',
        'common/defines':'only conflicting political scalars explicitly resolved; other fields retained in sources; ADR-001',
        'common/history':'distinct additive GLOBAL history files retained; order-sensitive state requires manual acceptance',
        'common/ideologies':'BPM bodies with explicit TE character/axis positions; ADR-001/004',
        'common/interest_groups':'BPM groups with TE-only female-generation branches; ADR-005',
        'common/journal_entries':'BPM historical entry plus rule-aware TE tax success; ADR-007',
        'common/laws':'full field-aware composition; ADR-002',
        'common/modifier_type_definitions':'BPM presentation and TE AI game_data; ADR-007',
        'common/on_actions':'source list registrations retained, no duplicate adapter; installed _on_actions.md; ADR-007',
        'common/parties':'BPM weights with TE FPTP lifecycle; ADR-003',
        'common/power_bloc_principles':'BPM political modifier and TE slot/override conditions; ADR-007',
        'common/production_methods':'TE full recipes plus BPM restrictions; disjoint injections retained; ADR-001',
        'common/scripted_rules':'BPM franchise in same-path TE rule file; ADR-007',
        'common/static_modifiers':'disjoint base_values injections retained without registering twice; ADR-007',
        'common/technology/technologies':'BPM research logic and TE modifiers; ADR-007',
    }
    registry=[{'id':f'OVL-{i:03d}','category':e['category'],'key':e['key'],
               'source_records':{'timeline':e['left'],'bpm':e['right']},
               'decision':decisions[e['category']],'status':'static_decision_runtime_unverified'}
              for i,e in enumerate(common,start=1)]
    conflict_dir=ROOT/'docs/conflicts';conflict_dir.mkdir(exist_ok=True)
    (conflict_dir/'overlap-decisions.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (conflict_dir/'shadow-definitions.json').write_text(json.dumps(safety_report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


if __name__ == '__main__':
    value = generate()
    print(json.dumps({k: v for k,v in value.items() if k not in ('provenance',)}, ensure_ascii=True, indent=2))
