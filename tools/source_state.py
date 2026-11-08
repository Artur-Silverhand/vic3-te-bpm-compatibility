"""Resolve local paths and bind a synthetic PASS to its exact input state."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE_SCOPE=('.metadata','common','events','gui','map_data')
INPUT_SCOPE=BASE_SCOPE+('localization',)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def resolve(root,value):
    path=Path(value)
    return path.resolve() if path.is_absolute() else (Path(root)/path).resolve()


def project(root=ROOT):
    data=read_json(Path(root)/'project.json')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?',data['patch_version']):
        raise ValueError('Invalid patch version')
    if '..' in data['patch_version']:raise ValueError('Invalid patch version')
    return data


def load_lock(root=ROOT):
    root=Path(root);data=read_json(root/'sources.lock.json')
    local=read_json(root/'paths.local.json') if (root/'paths.local.json').exists() else {}
    for label,config in data['mods'].items():
        checkout=resolve(root,local.get(label,config['checkout']))
        # Relocated checkouts use the conventional relative source layout.
        conventional=root/'sources/upstream'/('Vic3TimelineExtended' if label=='timeline' else 'Better-Politics-Mod-Vic-3')
        if label not in local and not checkout.exists() and conventional.exists():checkout=conventional.resolve()
        config['checkout']=str(checkout)
        config['mod_root']=str((checkout/config['mod_subdirectory']).resolve())
    data['game']['root']=str(resolve(root,local.get('game',data['game']['root'])))
    return data


def research_path(root=ROOT,lock=None):
    root=Path(root);lock=lock or load_lock(root)
    value=lock['research_reports']['github']['path']
    path=resolve(root,value)
    if not path.exists():
        relative=root/'docs/research'/Path(value).name
        if relative.exists():path=relative.resolve()
    return path


def load_research(root=ROOT,lock=None):
    lock=lock or load_lock(root);path=research_path(root,lock)
    if sha(path)!=lock['research_reports']['github']['sha256']:raise ValueError('Research report changed')
    report=read_json(path)
    for label in ('timeline','bpm'):report['sources'][label]['root']=lock['mods'][label]['mod_root']
    report['sources']['game']['root']=str(Path(lock['game']['root'])/'game')
    return report


def scoped_files(root,scope=INPUT_SCOPE):
    root=Path(root).resolve();result={}
    for directory in scope:
        for path in sorted((root/directory).rglob('*')):
            if not path.is_file():continue
            relative=path.relative_to(root)
            if any(part.startswith('.') for part in relative.parts) and relative.parts[0]!='.metadata':continue
            if path.is_symlink() or not path.resolve().is_relative_to(root):raise ValueError('Input link escapes source tree')
            result[relative.as_posix()]=sha(path)
    return result


def game_identity(root):
    root=Path(root);settings=root/'launcher/launcher-settings.json'
    data=read_json(settings)
    result={'version':data['rawVersion'],'launcher_settings_sha256':sha(settings)}
    steam=root.parent.parent/'appmanifest_529340.acf'
    if steam.exists():
        match=re.search(r'"buildid"\s+"([^"]+)"',steam.read_text(encoding='utf-8-sig'))
        if not match:raise ValueError('Missing Steam build identity')
        result['steam_build_id']=match[1]
    return result


def source_state(root=ROOT):
    """Fail on input drift, including additions/deletions, before issuing a PASS."""
    root=Path(root);lock=load_lock(root);report=load_research(root,lock);policy=project(root)
    game=game_identity(lock['game']['root'])
    if game['version']!=lock['game']['version']:raise ValueError('Game version changed; stage a new candidate')
    if game['version']!=policy['supported_game_version']:raise ValueError('Game API review required in project.json')
    for key in ('launcher_settings_sha256','steam_build_id'):
        if key in lock['game'] and game.get(key)!=lock['game'][key]:raise ValueError('Game build changed or unavailable: '+key)
    result={'schema_version':1,'scope':list(INPUT_SCOPE),'lock_sha256':sha(root/'sources.lock.json'),
            'research_sha256':sha(research_path(root,lock)),'project_sha256':sha(root/'project.json'),
            'update_review_sha256':sha(root/'update-review.json') if (root/'update-review.json').exists() else None,
            'game':game,'sources':{}}
    pending_update_review(root)
    if (root/'backports').exists():
        result['backports']={p.relative_to(root).as_posix():sha(p) for p in sorted((root/'backports').rglob('*')) if p.is_file()}
    if (root/'docs/decisions/iteration-reviews.json').exists():
        result['iteration_reviews_sha256']=sha(root/'docs/decisions/iteration-reviews.json')
    for label in ('timeline','bpm','game'):
        config=report['sources'][label];actual=scoped_files(config['root'])
        baseline_scope=tuple(name for name in BASE_SCOPE if name!='map_data' or any(rel.startswith('map_data/') for rel in config['files']))
        expected_paths={rel for rel in config['files'] if rel.split('/')[0] in baseline_scope}
        expected={rel:record['sha256'] for rel,record in config['files'].items()
                  if rel in expected_paths and 'sha256' in record}
        base={rel:value for rel,value in actual.items() if rel.split('/')[0] in baseline_scope}
        changed=sorted(set(base)^expected_paths|{rel for rel in set(base)&set(expected) if base[rel]!=expected[rel]})
        if changed:
            raise ValueError(label+' inputs changed; run update_patch.py check: '+', '.join(changed[:8]))
        item={'files':len(actual),'baseline_scope':list(baseline_scope),'baseline_hashed_files':len(expected),
              'sha256':hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest()}
        if label!='game':
            mod=lock['mods'][label]
            current=subprocess.check_output(['git','-C',mod['checkout'],'rev-parse','HEAD'],text=True).strip()
            if current!=mod['commit']:raise ValueError(label+' commit changed')
            dirty=subprocess.check_output(['git','-C',mod['checkout'],'status','--porcelain','--untracked-files=no'],text=True)
            if dirty.strip():raise ValueError(label+' tracked source files were edited')
            item['commit']=current
            # These tracked helpers are executed by the TE generator/parser.
            if label=='timeline':
                helpers=['scripts/generators/gen_tax_code.py','paradox_file_parser.py','organize_loc.py',
                         'path_constants.py','scripts/_path_detect.py','vanilla_parsed/common/pop_needs.json',
                         'vanilla_parsed/common/goods.json']
                item['helpers']={rel:sha(Path(mod['checkout'])/rel) for rel in helpers}
        result['sources'][label]=item
    return result


def pending_update_review(root=ROOT):
    root=Path(root);path=root/'update-review.json'
    if not path.exists():return []
    data=read_json(path);lock=load_lock(root)
    expected={'lock_sha256':sha(root/'sources.lock.json'),'research_sha256':sha(research_path(root,lock))}
    if data['input_context']!=expected:raise ValueError('Update review belongs to different inputs')
    required=data['required'];reviewed=data.get('reviewed',{})
    if len(required)!=len(set(required)):raise ValueError('Duplicate update review ID')
    if any(key not in required or not isinstance(note,str) or len(note.strip())<8 for key,note in reviewed.items()):
        raise ValueError('Each reviewed change needs a concrete explanation')
    return sorted(set(required)-set(reviewed))


def require_fresh_inputs(gate,root=ROOT):
    if 'source_state' not in gate:raise ValueError('Gate predates input tracking; rerun verify_patch.py')
    if gate['source_state']!=source_state(root):raise ValueError('Inputs changed since PASS; rerun verify_patch.py')
    pending=pending_update_review(root)
    if pending:raise ValueError('Upstream changes need review before shipping: '+', '.join(pending[:6]))
