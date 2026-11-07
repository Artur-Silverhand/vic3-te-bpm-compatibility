"""Offline input/reference/syntax audit. Never starts Victoria 3 or its launcher."""
from collections import defaultdict
import json
from pathlib import Path
import re
import sys
import contextlib
import io

from build_patch import ROOT, OUTPUT, REPORT, blocks, digest, normalized
from inspect_mod_overlap import TOKEN
from script_syntax import parse as structured_parse,top_spans
from source_state import load_research


def audit():
    research=load_research(ROOT)
    catalog=defaultdict(set); hooks=defaultdict(list)
    for label,source in research['sources'].items():
        root=Path(source['root'])
        for rel,record in source['files'].items():
            if not(rel.startswith('common/') and rel.endswith('.txt')):continue
            # Reuse the scanner's known DNA limitation; no generated DNA exists.
            if rel.startswith('common/dna_data/'):continue
            path=root/rel
            if not path.exists():raise ValueError('Missing input '+str(path))
            if digest(path)!=record['sha256']:raise ValueError('Input drift '+str(path))
            for node in blocks(path.read_text(encoding='utf-8-sig')):
                category=Path(rel).parent.as_posix()
                catalog[category].add(node['key'])
                if category=='common/on_actions':hooks[node['key']].append((label,rel,node))

    namespaces={
        'law_type':'common/laws', 'law_group':'common/law_groups',
        'ideology':'common/ideologies', 'amendment_type':'common/amendments',
        'institution_type':'common/institutions', 'interest_group_type':'common/interest_groups',
        'production_method_type':'common/production_methods',
    }
    definitions=[]; unresolved=[]; unknown_replacements=[]; counts=defaultdict(int)
    checked_scripts=sorted((OUTPUT/'common').rglob('*.txt'))+sorted((OUTPUT/'events').rglob('*.txt'))
    for path in checked_scripts:
        relative=path.relative_to(OUTPUT).as_posix(); category=path.parent.relative_to(OUTPUT).as_posix()
        text=path.read_text(encoding='utf-8-sig')
        for node in blocks(text):
            # History sections are executable containers repeated per file,
            # not unique database entity IDs (COUNTRIES, GLOBAL, STATES).
            if not category.startswith('common/history') and category!='common/on_actions':definitions.append((category,node['key']))
            if node['operation']=='REPLACE' and node['key'] not in catalog[category]:
                unknown_replacements.append({'file':relative,'key':node['key']})
        for prefix,key in re.findall(r'\b([a-z_]+):([\w]+)',normalized(text)):
            if prefix not in namespaces:continue
            counts[prefix]+=1
            if key not in catalog[namespaces[prefix]]:
                unresolved.append({'file':relative,'namespace':prefix,'key':key})
    duplicates=sorted({str(key) for key in definitions if definitions.count(key)>1})

    # Official installed _on_actions.md permits multi-file declarations of
    # lists, but disallows competing trigger/effect blocks. All 22 cross-mod
    # hooks use lists exclusively. Do not register those lists a second time.
    shared=[e for e in research['comparisons']['timeline_bpm']['shared_entities']
            if e['category']=='common/on_actions']
    hook_report=[]
    for entry in shared:
        members=[record for label,rel,node in hooks[entry['key']] if label in {'timeline','bpm'}
                 for record in blocks(node['body'])]
        keys={m['key'] for m in members}
        assert keys <= {'on_actions','events','random_events'},(entry['key'],keys)
        missing=[];calls=[]
        for member in members:
            if member['key']!='on_actions':continue
            for name in normalized(member['body']).split():
                assert name not in '{}=',member
                calls.append(name)
                if name not in hooks:missing.append(name)
        if missing:raise ValueError('Missing callbacks: '+str(missing))
        hook_report.append({'hook':entry['key'],'fields':sorted(keys),'callbacks':calls,
                            'policy':'retain additive source registrations; no extra registration'})

    # A second parser implementation checks common files with directives kept
    # literal. Its AST is not an engine simulation and GUI is outside its API.
    sys.path.insert(0,research['sources']['timeline']['root'])
    from paradox_file_parser import ParadoxFileParser
    independent=[];independent_events=[];parser_limitations=[]
    for path in checked_scripts:
        parser=ParadoxFileParser()
        text=path.read_text(encoding='utf-8-sig')
        structured_parse(text)
        try:
            with contextlib.redirect_stdout(io.StringIO()):parser.parse_file(str(path),apply_directives=False)
            definition_count=len(parser.data)
        except ValueError:
            # The independent parser cannot read vanilla's mixed delayed
            # callback lists. Never ignore modified unsupported syntax: each
            # rejected top-level block must match a pinned inherited block.
            relative=path.relative_to(OUTPUT).as_posix();originals=set()
            for label in ['game','timeline','bpm']:
                record=research['sources'][label]['files'].get(relative)
                if record:
                    source=Path(research['sources'][label]['root'])/relative
                    assert digest(source)==record['sha256']
                    originals.update(normalized(v['raw']) for v in top_spans(source.read_text(encoding='utf-8-sig')))
            entries=top_spans(text);definition_count=len(entries)
            for entry in entries:
                check=ParadoxFileParser()
                try:check.parse_object(check.tokenize('{'+entry['raw']+'}'))
                except ValueError as error:
                    assert normalized(entry['raw']) in originals,'Modified unsupported syntax: '+relative+'/'+entry['key']
                    parser_limitations.append({'file':relative,'key':entry['key'],'error':str(error),
                                               'proof':'normalized block identical to hash-verified inherited source; structured parser passed'})
        target=independent_events if path.is_relative_to(OUTPUT/'events') else independent
        target.append({'file':path.relative_to(ROOT).as_posix(),'definitions':definition_count})
    gui=[]
    for path in sorted((OUTPUT/'gui').rglob('*.gui')):
        depth=0
        for token in TOKEN.finditer(path.read_text(encoding='utf-8-sig')):
            value=token.group()
            depth+=(value=='{')-(value=='}')
            if depth<0:raise ValueError('Excess closing GUI brace '+str(path))
        if depth:raise ValueError('Unclosed GUI brace '+str(path))
        gui.append(path.relative_to(OUTPUT).as_posix())
    result={'method':'offline structural and selected typed-reference audit; not engine execution',
            'unknown_replacements':unknown_replacements,'unresolved_typed_references':unresolved,
            'typed_reference_occurrences':dict(counts),'duplicate_generated_entities':duplicates,
            'shared_on_actions':hook_report,'independent_common_parser':independent,
            'independent_event_parser':independent_events,
            'independent_parser_inherited_limitations':parser_limitations,
            'balanced_gui_files':gui,'engine_verified':False,'render_verified':False,
            'patch_sha256':{p.relative_to(OUTPUT).as_posix():digest(p) for p in sorted(OUTPUT.rglob('*')) if p.is_file()}}
    destination=ROOT/'docs/validation/offline-audit.json'
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'docs/validation/independent-parser.json').write_text(json.dumps(independent,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'common_files':len(independent),'event_files':len(independent_events),'gui_files':len(gui),'shared_hooks':len(shared),
                      'independent_parser_inherited_limitations':parser_limitations,
                      'typed_references':sum(counts.values()),'unresolved':unresolved,
                      'unknown_replacements':unknown_replacements,'duplicate_definitions':duplicates},indent=2))
    if unresolved or unknown_replacements or duplicates:raise SystemExit(1)
    return result


if __name__=='__main__':audit()
