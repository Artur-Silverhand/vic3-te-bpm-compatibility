"""Seal reviewed builds, rebuild without a model, and audit upstream text changes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from loclib import ROOT,digest,json_write,load,write_localization,validate,escape_value,numeric_profile
from build import source_for_validation,latin_only,numeric_exceptions

WORK=ROOT/'runtime/translations'
MEMORY=ROOT/'translations/memory'
OUTPUT=ROOT/'translations/output'
PACKS={
    'bpm':{'slug':'better-politics-mod-russian','name':'Better Politics Mod — Русский перевод (продолжение)',
           'id':'ea3bb3af-d9bd-4b6f-9c21-b0d3c3b39943','version':'0.1.1','readme':'README-BPM.md'},
    'te':{'slug':'vic3-timeline-extended-russian','name':'Timeline Extended — Русский перевод',
          'id':'76cf15a1-ac88-43b3-b0c3-557266dc5b70','version':'0.1.1-preview','readme':'README-TE.md'},
}


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def check_binding(memory,source):
    """An unchanged identifier does not make an old translation current."""
    current=set(source);old={key for key,row in memory.items() if row.get('en_sha256')}
    return {'added':sorted(current-old),'removed':sorted(old-current),
            'changed':sorted(key for key in old&current if digest(source[key]['value'])!=memory[key]['en_sha256'])}


def audit_sources(data,memories):
    return {pack:check_binding(memories[pack],data[pack+'_en']) for pack in PACKS}


def seal():
    summary=read(WORK/'build/summary.json')
    from prepare import prepare
    prepare()
    if summary['structural_issues'] or summary['remaining'] or summary['latin_only_for_review']:
        raise ValueError('Unresolved build findings; inspect runtime/translations/build')
    for relative,expected in summary['input_sha256'].items():
        if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()!=expected:
            raise ValueError('Build input changed: '+relative)
    data=read(WORK/'canonical.json')
    # Never silently accept new English while sealing an existing translation.
    if all((MEMORY/(pack+'.json')).exists() for pack in PACKS):
        changes=audit_sources(data,{pack:read(MEMORY/(pack+'.json')) for pack in PACKS})
        if any(any(rows.values()) for rows in changes.values()):
            json_write(WORK/'update-report.json',changes)
            raise ValueError('English source changed. Review changed/new keys before explicitly updating memory.')
    for pack in PACKS:
        values=read(WORK/('build/'+pack+'-values.json'));quality=read(WORK/('build/'+pack+'-quality.json'))
        memory={key:{'ru':value,**quality[key]} for key,value in values.items()}
        json_write(MEMORY/(pack+'.json'),memory)
    json_write(MEMORY/'bridge.json',read(WORK/'build/bridge.json'))
    sys.path.insert(0,str(ROOT/'tools'))
    from source_state import load_lock,game_identity
    lock=load_lock(ROOT)
    identity={'game':game_identity(lock['game']['root']),
              'mods':{name:{'commit':row['commit'],'version':row['metadata']['version']} for name,row in lock['mods'].items()},
              'translation_sources':{'bpm_workshop':'https://steamcommunity.com/sharedfiles/filedetails/?id=3487720283',
                                     'bpm_original_author':'Dictator_life'},
              'model':{'name':'Argos English-Russian 1.9 / CTranslate2','local_only':True,
                       'archive_sha256':'591d743ae103752b88ffc38785c50421320f4eff93c8967e0d3d2e14d4e27811'},
              'engine_verified':False,'all_prose_human_reviewed':False}
    json_write(MEMORY/'source-lock.json',identity)
    json_write(MEMORY/'quality.json',{key:value for key,value in summary.items() if key!='input_sha256'})


def audit(args):
    from prepare import prepare
    prepare();data=read(WORK/'canonical.json')
    for pack in PACKS:
        custom=getattr(args,pack+'_localization',None)
        if custom:
            entries,diagnostics=load(custom,'english',True)
            if not entries:raise ValueError('No English localization in supplied directory')
            data[pack+'_en']={key:{'value':row.value} for key,row in entries.items()}
    report=audit_sources(data,{pack:read(MEMORY/(pack+'.json')) for pack in PACKS})
    report['bridge']=check_binding(read(MEMORY/'bridge.json'),data['bridge_en'])
    sys.path.insert(0,str(ROOT/'tools'))
    from source_state import load_lock,game_identity
    actual=game_identity(load_lock(ROOT)['game']['root']);expected=read(MEMORY/'source-lock.json')['game']
    report['game_changed']=actual!=expected
    json_write(WORK/'update-report.json',report)
    print(json.dumps({key:({name:len(rows) for name,rows in item.items()} if isinstance(item,dict) else item)
                      for key,item in report.items()},indent=2))
    return not report['game_changed'] and not any(any(report[pack].values()) for pack in (*PACKS,'bridge'))


def package():
    if not audit(argparse.Namespace(te_localization=None,bpm_localization=None)):
        raise ValueError('Sources changed; review the update report before packaging')
    data=read(WORK/'canonical.json');memories={pack:read(MEMORY/(pack+'.json')) for pack in PACKS}
    changes=audit_sources(data,memories)
    bridge=read(MEMORY/'bridge.json')
    changes['bridge']=check_binding(bridge,data['bridge_en'])
    if any(any(rows.values()) for rows in changes.values()):raise ValueError('Stale source bindings; run audit')
    allow=read(ROOT/'translations/data/latin_allowlist.json')
    numeric_allow=numeric_exceptions()
    reports={}
    for pack,config in PACKS.items():
        target=OUTPUT/config['slug'];values={key:row['ru'] for key,row in memories[pack].items()}
        expected=data[pack+'_en']
        problems=[]
        for key,entry in expected.items():
            if key not in values:problems.append((key,'missing'));continue
            errors=validate(source_for_validation(key,entry['value']),values[key])
            if numeric_profile(entry['value'])!=numeric_profile(values[key]):
                accepted=numeric_allow.get(pack,{}).get(key,{})
                if accepted.get('en_sha256')!=digest(entry['value']) or accepted.get('ru_sha256')!=digest(values[key]) or not accepted.get('reason'):
                    errors.append('numbers_changed')
            if errors:problems.append((key,errors))
            if latin_only(values[key]):
                permission=allow.get(pack,{}).get(key,{})
                if permission.get('value_sha256')!=digest(values[key]) or not permission.get('reason'):
                    problems.append((key,'unreviewed_latin_only'))
        if problems:
            json_write(WORK/(pack+'-package-errors.json'),problems)
            raise ValueError(pack+' package failed; inspect runtime/translations/'+pack+'-package-errors.json')
        relative='localization/russian/replace/zzzz_'+pack+'_russian_l_russian.yml'
        write_localization(target/relative,values)
        emitted,diagnostics=load(target/'localization','russian',True)
        if diagnostics['issues'] or diagnostics['conflicting_duplicates'] or set(emitted)!=set(values):
            raise ValueError('Emitted localization failed syntax/coverage/duplicate checks')
        for key,value in values.items():
            if emitted[key].value!=escape_value(value):raise ValueError('Emitted value changed: '+key)
        metadata={'name':config['name'],'id':config['id'],'version':config['version'],
                  'supported_game_version':'1.15.0','short_description':'Русский перевод. Требует оригинальный мод.',
                  'tags':['Translation'],'relationships':[],
                  'game_custom_data':{'multiplayer_synchronized':False}}
        json_write(target/'.metadata/metadata.json',metadata)
        (target/'README.md').write_text((ROOT/'translations/docs'/config['readme']).read_text(encoding='utf-8'),encoding='utf-8',newline='\n')
        bindings={key:{name:value for name,value in row.items() if name!='ru'} for key,row in memories[pack].items()}
        json_write(target/'maintenance/source-bindings.json',bindings)
        json_write(target/'maintenance/source-lock.json',read(MEMORY/'source-lock.json'))
        json_write(target/'maintenance/quality.json',read(MEMORY/'quality.json'))
        archive=ROOT/'dist'/(config['slug']+'-'+config['version']+'.zip');archive.parent.mkdir(exist_ok=True)
        files=[target/name for name in (relative,'.metadata/metadata.json','README.md',
               'maintenance/source-bindings.json','maintenance/source-lock.json','maintenance/quality.json')]
        # Existing versions are immutable: a new translation needs a new version.
        if archive.exists():
            with zipfile.ZipFile(archive) as saved:
                current={path.relative_to(target).as_posix():path.read_bytes() for path in files}
                if set(current)!=set(saved.namelist()) or any(saved.read(key)!=value for key,value in current.items()):
                    raise ValueError('Version already packaged with different bytes; increment version')
        else:
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as output:
                for path in files:output.write(path,path.relative_to(target).as_posix())
        reports[pack]={'keys':len(values),'source_keys':len(data[pack+'_en']),'duplicate_keys':0,
                       'archive':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                       'engine_verified':False}
    json_write(OUTPUT/'package-report.json',reports);print(json.dumps(reports,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['seal','package','audit'])
    parser.add_argument('--te-localization',type=Path);parser.add_argument('--bpm-localization',type=Path)
    args=parser.parse_args()
    if args.command=='seal':seal()
    elif args.command=='package':package()
    elif not audit(args):raise SystemExit(2)
