"""Read-only checks of installed TE without BPM or the compatibility patch."""
import argparse
from dataclasses import asdict
import importlib
import json
from pathlib import Path
import sys
import time

from source_state import ROOT,load_lock
from script_syntax import parse


def audit(target=None):
    sys.dont_write_bytecode=True
    lock=load_lock(ROOT);upstream=Path(lock['mods']['timeline']['mod_root'])
    target=Path(target or lock['mods']['timeline']['workshop_root'])
    destination=ROOT/'runtime/te-standalone';destination.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(upstream))
    started=time.monotonic();report={'scope':'TE only; installed scripts; no game launch','checks':{}}
    def save():
        (destination/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    errors=[];count=0
    for directory in ('common','events','map_data'):
        for path in sorted((target/directory).rglob('*.txt')):
            # These are engine documentation, not database scripts.
            if path.name.endswith('_types.txt') and path.parent.name=='common':continue
            try:parse(path.read_text(encoding='utf-8-sig'))
            except (ValueError,UnicodeError) as error:errors.append({'file':path.relative_to(target).as_posix(),'error':str(error)})
            count+=1
    report['checks']['script_syntax']={'files':count,'errors':errors};save()
    print('script_syntax',count,'files',len(errors),'errors',flush=True)
    for name in ('orphaned_event_audit','duplicate_key_audit','effect_trigger_validity_audit','event_context_audit'):
        try:
            module=importlib.import_module(name)
            kwargs={'mod_path':str(target)}
            if name=='effect_trigger_validity_audit':
                kwargs.update(valid_keys=module.load_catalog(str(upstream)),context_keys=module.load_context_catalog(str(upstream)))
            result=module.audit(**kwargs)
            flags=[asdict(row) for row in result.flags]
            def relative(value):
                if isinstance(value,dict):return {key:relative(item) for key,item in value.items()}
                if isinstance(value,list):return [relative(item) for item in value]
                if isinstance(value,str):return value.replace(str(target),'TE').replace(str(upstream),'TE toolchain')
                return value
            unreviewed=sum(not row.get('exemption') for row in flags)
            item={'flags':relative(flags),'unreviewed':unreviewed}
            for field in ('coverage','stale_tags','unknown_tags'):
                value=getattr(result,field,None)
                if value is not None:item[field]=relative([asdict(row) for row in value] if isinstance(value,list) else value)
            report['checks'][name]=item
            print(name,'unreviewed',unreviewed,flush=True)
        except Exception as error:
            report['checks'][name]={'tool_error':str(error)};print(name,type(error).__name__,str(error),flush=True)
        save()
    report['seconds']=round(time.monotonic()-started,1);save()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--mod-root',type=Path)
    audit(parser.parse_args().mod_root)
