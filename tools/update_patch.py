"""Triage updates and stage isolated candidates. Never installs or launches a game."""
import argparse
from collections import defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from inspect_mod_overlap import TOKEN
from script_syntax import top_spans
from source_state import ROOT,BASE_SCOPE,load_lock,load_research,project,game_identity,sha,read_json,pending_update_review

ADAPTERS={
    'laws/ideologies':['common/laws/*','common/law_groups/*','common/ideologies/*'],
    'parties/elections':['common/parties/*','common/amendments/*','common/*/*fptp*'],
    'characters/IG':['common/interest_groups/*','common/character*/*'],
    'cabinet':['common/scripted_effects/BPM_CAB*','common/script_values/*CAB*'],
    'tax/economy':['common/*/*tax*','common/*/*tax*/*','gui/*tax*','scripts/generators/gen_tax_code.py',
                   'common/goods/*','common/pop_needs/*','common/*/*construction*'],
    'events/hooks':['events/*','common/on_actions/*','common/scripted_effects/*','common/scripted_triggers/*'],
    'UI':['gui/*'],
    'production/institutions':['common/production_methods/*','common/institutions/*','common/technology/*'],
    'engine/API':['common/defines/*','common/modifier*/*','common/scripted_rules/*','common/power_bloc_principles/*'],
}
HELPERS=('scripts/generators/gen_tax_code.py','paradox_file_parser.py','organize_loc.py',
         'path_constants.py','scripts/_path_detect.py','vanilla_parsed/common/pop_needs.json',
         'vanilla_parsed/common/goods.json')


def semantic(text):
    return hashlib.sha256(' '.join(m.group() for m in TOKEN.finditer(text) if not m.group().startswith('#')).encode()).hexdigest()


def symbols(text):
    """Keep duplicate selectors as ordered entries; never collapse them silently."""
    result=defaultdict(list)
    for node in top_spans(text):result[node['key']].append((node['operation'],semantic(node['raw'])))
    return dict(result)


def compare_file(before,after,relative):
    if before==after:return {'kind':'unchanged','changed_symbols':[]}
    if before.replace(b'\r\n',b'\n')==after.replace(b'\r\n',b'\n'):
        return {'kind':'line_endings','changed_symbols':[]}
    if relative.endswith(('.txt','.gui')) and relative.startswith(('common/','events/','gui/')):
        try:
            a=before.decode('utf-8-sig');b=after.decode('utf-8-sig')
            if semantic(a)==semantic(b):return {'kind':'formatting','changed_symbols':[]}
            left,right=symbols(a),symbols(b)
            changed=sorted(k for k in set(left)|set(right) if left.get(k)!=right.get(k))
            return {'kind':'script','changed_symbols':changed}
        except (ValueError,UnicodeError,IndexError):
            return {'kind':'unparsed_script','changed_symbols':[]}
    return {'kind':'content','changed_symbols':[]}


def impacts(relative,overrides):
    result=sorted(name for name,patterns in ADAPTERS.items() if any(fnmatch.fnmatchcase(relative,pattern) for pattern in patterns))
    if relative in overrides:result.insert(0,'same-path override')
    return result or ['unclassified: review required']


def check(root=ROOT,profile='workshop',roots=None):
    root=Path(root);lock=load_lock(root);baseline=load_research(root,lock);roots=dict(roots or {})
    for label in ('timeline','bpm'):
        roots.setdefault(label,Path(lock['mods'][label]['workshop_root'] if profile=='workshop' else lock['mods'][label]['mod_root']))
    roots.setdefault('game',Path(lock['game']['root'])/'game')
    current=game_identity(Path(roots['game']).parent)
    overrides={p.relative_to(root/'patch').as_posix() for p in (root/'patch').rglob('*') if p.is_file()}
    report={'schema_version':1,'checked_utc':datetime.now(timezone.utc).isoformat(),
            'profile':profile,'status':'UNCHANGED','changes':[],'sources':{},'blockers':[],
            'game_launched':False,'installed_files_changed':False,
            'scope':'recorded runtime files plus TE generator helpers; new overlaps need full candidate audit'}
    for label,selected in roots.items():
        selected=Path(selected).resolve()
        if not selected.is_dir():raise ValueError('Missing source directory: '+label)
        old=baseline['sources'][label];reference=Path(old['root'])
        # Old inventories did not include TE/BPM map_data; do not invent a baseline.
        scope=tuple(v for v in BASE_SCOPE if v!='map_data' or any(r.startswith('map_data/') for r in old['files']))
        expected={rel:record for rel,record in old['files'].items() if rel.split('/')[0] in scope}
        actual={p.relative_to(selected).as_posix():p for top in scope for p in (selected/top).rglob('*') if p.is_file()
                and (top=='.metadata' or not any(v.startswith('.') for v in p.relative_to(selected).parts))}
        helper_bytes={}
        if label=='timeline':
            for rel in HELPERS:
                try:
                    helper_bytes[rel]=subprocess.check_output(['git','-C',lock['mods']['timeline']['checkout'],
                        'show',lock['mods']['timeline']['commit']+':'+rel],stderr=subprocess.DEVNULL)
                    reference_file=reference/rel
                    if reference_file.exists() and reference_file.read_bytes().replace(b'\r\n',b'\n')==helper_bytes[rel].replace(b'\r\n',b'\n'):
                        helper_bytes[rel]=reference_file.read_bytes()
                    data=helper_bytes[rel]
                    expected[rel]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
                except subprocess.CalledProcessError:
                    # Missing pinned toolchain is an explicit unknown, never a green result.
                    report['blockers'].append('timeline: pinned helper unavailable: '+rel)
                if (selected/rel).exists():actual[rel]=selected/rel
                elif profile=='workshop':expected.pop(rel,None)  # Workshop does not ship the authoring toolchain.
        for relative in sorted(set(expected)|set(actual)):
            before=expected.get(relative);path=actual.get(relative)
            if path is not None and (path.is_symlink() or not path.resolve().is_relative_to(selected)):
                raise ValueError('Source link escapes source directory: '+label)
            digest=sha(path) if path else None
            if before and path and before.get('sha256')==digest:continue
            if before and path and 'sha256' not in before:
                info={'kind':'unhashed_baseline','changed_symbols':[]}
            elif not before:info={'kind':'added','changed_symbols':[]}
            elif not path:info={'kind':'removed','changed_symbols':[]}
            else:
                original=reference/relative
                if relative in helper_bytes:
                    info=compare_file(helper_bytes[relative],path.read_bytes(),relative)
                elif original.exists() and sha(original)==before.get('sha256'):
                    info=compare_file(original.read_bytes(),path.read_bytes(),relative)
                else:info={'kind':'changed_baseline_unavailable','changed_symbols':[]}
            row={'source':label,'path':relative,**info,'adapters':impacts(relative,overrides),
                 'baseline_sha256':before.get('sha256') if before else None,'candidate_sha256':digest}
            report['changes'].append(row)
        metadata=read_json(selected/'.metadata/metadata.json') if (selected/'.metadata/metadata.json').exists() else {}
        report['sources'][label]={'version':metadata.get('version'),'changed_files':sum(v['source']==label for v in report['changes']),
                                  'scope':list(scope)}
        if label!='game':
            supported=metadata.get('supported_game_version')
            if supported and not fnmatch.fnmatchcase(current['version'],supported):
                report['blockers'].append(label+': declares another supported game version')
    report['game']={'baseline_version':lock['game']['version'],'candidate':current}
    for field in ('version','steam_build_id','launcher_settings_sha256'):
        if field in lock['game'] and current.get(field)!=lock['game'][field]:report['blockers'].append('game identity changed: '+field)
    report['substantive_changes']=sum(row['kind'] not in {'line_endings','formatting'} for row in report['changes'])
    if report['substantive_changes'] or report['blockers']:report['status']='REVIEW_REQUIRED'
    elif report['changes']:report['status']='RESTAGE_REQUIRED'
    return report


def write_report(report,directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Update impact report','',f"Status: {report['status']}",'',
           'No game launch, installation change or automatic compatibility approval.','']
    lines.extend('- '+value for value in report['blockers'])
    cosmetic=sum(v['kind'] in {'line_endings','formatting'} for v in report['changes'])
    lines+=['',f"Substantive changes: {report['substantive_changes']}. Formatting/line endings: {cosmetic} (full list in report.json).",'',
            '| Source | File | Change | Adapters | Symbols |','|---|---|---|---|---|']
    for row in report['changes']:
        if row['kind'] in {'line_endings','formatting'}:continue
        names=', '.join(row['changed_symbols'][:12]).replace('|','\\|')
        lines.append(f"| {row['source']} | {row['path']} | {row['kind']} | {', '.join(row['adapters'])} | {names} |")
    (directory/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def git(checkout,*args):
    return subprocess.check_output(['git','-C',str(checkout),*args],text=True,encoding='utf-8').strip()


def candidate_path(root,name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',name) or '..' in name:raise ValueError('Invalid candidate name')
    parent=(Path(root)/'runtime/updates').resolve();target=(parent/name).resolve()
    if target.parent!=parent:raise ValueError('Candidate path escapes update directory')
    if target.exists():raise FileExistsError('Existing candidate left untouched')
    return target


def upstream(fetch=False,root=ROOT):
    """Inspect cached remote defaults; fetching never checks out or merges them."""
    lock=load_lock(root);result={}
    for label in ('timeline','bpm'):
        config=lock['mods'][label];checkout=config['checkout']
        if fetch:subprocess.run(['git','-C',checkout,'fetch','origin'],check=True)
        ref=git(checkout,'symbolic-ref','--short','refs/remotes/origin/HEAD')
        commit=git(checkout,'rev-parse',ref+'^{commit}')
        result[label]={'pinned':config['commit'],'remote_ref':ref,'available':commit,
                       'update_available':commit!=config['commit']}
    return {'schema_version':1,'fetched':fetch,'sources':result,'checked_out_or_installed':False}


def stage(name,version,timeline_ref='HEAD',bpm_ref='HEAD',game=None,fetch=False,verify=False,root=ROOT):
    root=Path(root);destination=candidate_path(root,name);old_lock=load_lock(root);policy=project(root)
    if version==policy['patch_version']:raise ValueError('A candidate requires a new patch version')
    test_policy={**policy,'patch_version':version}
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?',version) or '..' in version:raise ValueError('Invalid patch version')
    refs={'timeline':timeline_ref,'bpm':bpm_ref};commits={}
    for label,ref in refs.items():
        if not ref or ref.startswith('-'):raise ValueError('Invalid Git reference')
        checkout=old_lock['mods'][label]['checkout']
        if fetch:subprocess.run(['git','-C',checkout,'fetch','origin'],check=True)
        commits[label]=git(checkout,'rev-parse','--verify','--end-of-options',ref+'^{commit}')
    game=Path(game or old_lock['game']['root']).resolve();identity=game_identity(game)
    destination.mkdir(parents=True);worker=destination/'project'
    state={'schema_version':1,'status':'PREPARING','version':version,'commits':commits,
           'game':identity,'game_launched':False,'installed_files_changed':False,
           'engine_verified':False,'game_review_required':identity['version']!=policy['supported_game_version']}
    state_path=destination/'candidate.json'
    def save():state_path.write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        worker.mkdir()
        for directory in ('tools','patch','release'):
            shutil.copytree(root/directory,worker/directory,ignore=shutil.ignore_patterns('__pycache__','workshop-content','*.vdf','workshop-upload-result.json'))
        if (root/'backports').exists():shutil.copytree(root/'backports',worker/'backports')
        from translation_bridge import INPUTS as translation_inputs
        for relative in translation_inputs:
            target=worker/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(root/relative,target)
        shutil.copytree(root/'docs/decisions',worker/'docs/decisions')
        for relative in ('docs/validation','docs/conflicts','docs/research'):(worker/relative).mkdir(parents=True,exist_ok=True)
        for name in ('SPEC.md','STATUS.md','README.md','THIRD_PARTY_NOTICES.md'):
            (worker/name).write_bytes((root/name).read_bytes())
        for name in ('patch/README.md','patch/TESTING.md'):
            path=worker/name;path.write_text(path.read_text(encoding='utf-8').replace(policy['patch_version'],version),encoding='utf-8')
        (worker/'project.json').write_text(json.dumps(test_policy,indent=2)+'\n',encoding='utf-8')
        lock=deepcopy(old_lock);selected={}
        for label in ('timeline','bpm'):
            folder='Vic3TimelineExtended' if label=='timeline' else 'Better-Politics-Mod-Vic-3'
            checkout=worker/'sources/upstream'/folder;checkout.parent.mkdir(parents=True,exist_ok=True)
            subprocess.run(['git','clone','--no-hardlinks','--no-checkout',old_lock['mods'][label]['checkout'],str(checkout)],check=True,capture_output=True)
            subprocess.run(['git','-C',str(checkout),'config','core.autocrlf','false'],check=True)
            subprocess.run(['git','-C',str(checkout),'checkout','--detach',commits[label]],check=True,capture_output=True)
            config=lock['mods'][label];mod=checkout/config['mod_subdirectory'];selected[label]=mod
            metadata=read_json(mod/'.metadata/metadata.json')
            config.update({'checkout':checkout.relative_to(worker).as_posix(),
                           'mod_root':mod.relative_to(worker).as_posix(),'commit':commits[label],
                           'tree':git(checkout,'rev-parse','HEAD^{tree}'),'commit_time':git(checkout,'show','-s','--format=%cI','HEAD'),
                           'metadata':metadata,'metadata_sha256':sha(mod/'.metadata/metadata.json'),'sparse_checkout':False})
        selected['game']=game/'game'
        impact=check(root,profile='github-candidate',roots=selected)
        write_report(impact,destination)
        research=worker/'docs/research/candidate-overlap.json'
        command=[sys.executable,str(worker/'tools/inspect_mod_overlap.py'),'--output',str(research),
                 '--timeline-root',str(selected['timeline']),'--bpm-root',str(selected['bpm']),'--game-root',str(selected['game'])]
        with (destination/'inventory.log').open('w',encoding='utf-8') as log:
            subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
        lock['game'].update(identity);lock['game']['root']=str(game)
        lock['research_reports']={'github':{'path':'docs/research/candidate-overlap.json','sha256':sha(research)}}
        lock['recorded_utc']=datetime.now(timezone.utc).isoformat()
        (worker/'sources.lock.json').write_text(json.dumps(lock,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        old_report=load_research(root);new_report=read_json(research)
        def overlap_keys(report):
            return {(v['category'],v['key']) for v in report['comparisons']['timeline_bpm']['shared_entities']}
        new_overlaps=sorted(overlap_keys(new_report)-overlap_keys(old_report))
        required=[v['source']+':'+v['path'] for v in impact['changes'] if v['kind'] not in {'line_endings','formatting'}]
        required+=['overlap:'+category+':'+key for category,key in new_overlaps]
        required+=impact['blockers']
        review={'schema_version':1,'input_context':{'lock_sha256':sha(worker/'sources.lock.json'),
                  'research_sha256':sha(research)},'required':sorted(set(required)),'reviewed':{}}
        (worker/'update-review.json').write_text(json.dumps(review,indent=2)+'\n',encoding='utf-8')
        state['pending_reviews']=len(review['required']);state['new_overlaps']=len(new_overlaps)
        state['status']='GAME_REVIEW_REQUIRED' if state['game_review_required'] else 'PREPARED'
        save()
        if verify:
            with (destination/'verification.log').open('w',encoding='utf-8') as log:
                result=subprocess.run([sys.executable,str(worker/'tools/verify_patch.py')],cwd=worker,stdout=log,stderr=subprocess.STDOUT)
            state['verification_exit_code']=result.returncode
            state['status']=('SYNTHETIC_PASS_REVIEW_REQUIRED' if pending_update_review(worker) else 'SYNTHETIC_PASS') if result.returncode==0 else 'VERIFICATION_FAILED'
            save()
    except Exception as error:
        state['status']='PREPARATION_FAILED';state['error_type']=type(error).__name__;save()
        raise
    return state


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    audit=commands.add_parser('check');audit.add_argument('--profile',choices=['workshop','pinned'],default='workshop')
    for label in ('timeline','bpm','game'):audit.add_argument('--'+label+'-root',type=Path)
    audit.add_argument('--name',default='check')
    prepare=commands.add_parser('stage');prepare.add_argument('--name',required=True);prepare.add_argument('--patch-version',required=True)
    prepare.add_argument('--timeline-ref',default='HEAD');prepare.add_argument('--bpm-ref',default='HEAD')
    prepare.add_argument('--game-root',type=Path);prepare.add_argument('--fetch',action='store_true');prepare.add_argument('--verify',action='store_true')
    remote=commands.add_parser('upstream');remote.add_argument('--fetch',action='store_true')
    args=parser.parse_args()
    if args.command=='upstream':
        print(json.dumps(upstream(args.fetch),indent=2));return 0
    if args.command=='check':
        # Repeated checks replace reports only; candidate folders remain immutable.
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.name):raise ValueError('Invalid report name')
        output=ROOT/'runtime/updates'/('report-'+args.name)
        roots={label:(getattr(args,label+'_root')/ 'game' if label=='game' else getattr(args,label+'_root'))
               for label in ('timeline','bpm','game') if getattr(args,label+'_root') is not None}
        result=check(profile=args.profile,roots=roots);write_report(result,output)
        print(json.dumps({'status':result['status'],'changed_files':len(result['changes']),
                          'substantive_changes':result['substantive_changes'],'blockers':result['blockers'],
                          'report':output.relative_to(ROOT).as_posix()+'/report.md'},indent=2))
        return 0 if result['status']=='UNCHANGED' else 2
    result=stage(args.name,args.patch_version,args.timeline_ref,args.bpm_ref,args.game_root,args.fetch,args.verify)
    print(json.dumps(result,indent=2));return 0 if result['status'] in {'PREPARED','SYNTHETIC_PASS'} else 2


if __name__=='__main__':raise SystemExit(main())
