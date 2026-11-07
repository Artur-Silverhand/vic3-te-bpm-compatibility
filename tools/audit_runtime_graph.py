"""Conservative offline call/registration/cost audit of the composed script VFS.

No engine execution. Conditional cycles and dynamic macro calls are reported,
never silently treated as proof of safety. Positive-delay edges are excluded
only from the same-tick graph, not from the full feedback graph.
"""
from collections import defaultdict,Counter
from dataclasses import dataclass
from bisect import bisect_left
import json
from pathlib import Path
import re
import sys

from build_patch import ROOT,OUTPUT,REPORT,digest
from script_syntax import parse,Field,scalars,walk

DATABASES={'common/scripted_effects':'effect','common/scripted_triggers':'trigger',
           'common/script_values':'value','common/on_actions':'hook',
           'common/journal_entries':'journal','common/scripted_guis':'sgui',
           'common/decisions':'decision','common/laws':'law','common/amendments':'amendment',
           'common/technology/technologies':'technology','common/character_interactions':'interaction'}
CONDITIONAL={'if','else_if','else','trigger_if','trigger_else_if','trigger_else','limit',
             'random','random_list','switch','trigger','potential','option'}
VALUE_ARGUMENTS={'value','add','subtract','multiply','divide','min','max','modulo','factor','weight',
                 'multiplier','chance','days','months','years','level','amount','count','threshold'}
# These two domains are established by the pinned callers/schema, not by
# excluding self-edges: a party type is *_party (or one_party_independents),
# and the relief command's KEY is agrel/regrel. Without them a wildcard would
# incorrectly resolve to bpm_is_party_banned and te_tax_dr_relief_touch itself.
MACRO_DOMAINS={'bpm_is_$PARTY$_banned':{'PARTY':r'(?:\w+_party|one_party_independents)'},
               'te_tax_dr_$KEY$_touch':{'KEY':r'(?:agrel|regrel)'}}


def event_id(key):
    match=re.fullmatch(r'(.+)\.(\d+)',key)
    return match[1]+'.'+str(int(match[2])) if match else key
LOOPS={'every_country','every_decentralized_country','every_state','every_scope_state','every_scope_pop',
       'every_pop','every_interest_group','every_scope_interest_group','every_scope_building','every_scope_party'}


def strongly_connected(nodes,edges):
    """Iterative Kosaraju: audit large script graphs without Python recursion."""
    graph={n:set() for n in nodes};reverse={n:set() for n in nodes}
    for a,b in edges:
        if a in graph and b in graph:graph[a].add(b);reverse[b].add(a)
    seen=set();order=[]
    for root in graph:
        if root in seen:continue
        stack=[(root,False)]
        while stack:
            node,done=stack.pop()
            if done:order.append(node);continue
            if node in seen:continue
            seen.add(node);stack.append((node,True))
            stack.extend((n,False) for n in graph[node] if n not in seen)
    seen=set();components=[]
    for root in reversed(order):
        if root in seen:continue
        stack=[root];group=[];seen.add(root)
        while stack:
            node=stack.pop();group.append(node)
            for n in reverse[node]:
                if n not in seen:seen.add(n);stack.append(n)
        if len(group)>1 or root in graph[root]:components.append(sorted(group))
    return sorted(components)


def reviewed_iteration_optimization(row):
    # Exact, tested substitution: two ordered cabinet-list selections become
    # one plain pass. It may not add a world/pop loop or deepen nesting.
    return (row['id']=='effect:bpm_calculate_synergy'
            and row['before']['loops']=={'every_law':1,'ordered_in_list':2}
            and row['after']['loops']=={'every_law':1,'every_in_list':1}
            and row['before']['max_loop_depth']==row['after']['max_loop_depth']==2)


def load_vfs(research,cache):
    files={}
    for label in ['game','timeline','bpm']:
        root=Path(research['sources'][label]['root'])
        for rel,record in research['sources'][label]['files'].items():
            category='events' if rel.startswith('events/') else str(Path(rel).parent).replace('\\','/')
            if not(rel.endswith('.txt') and (category in DATABASES or category=='events')):continue
            path=root/rel
            assert digest(path)==record['sha256'],'Source drift: '+str(path)
            text=path.read_text(encoding='utf-8-sig')
            files[rel]=(label,text)
    return files


def analyze(files,cache):
    nodes={};duplicates=[];registration=[]
    for rel,(owner,text) in sorted(files.items()):
        category='events' if rel.startswith('events/') else Path(rel).parent.as_posix()
        kind=DATABASES.get(category,'event')
        if kind=='event' and not rel.startswith('events/'):continue
        if text not in cache:
            try:cache[text]=parse(text)
            except ValueError as error:raise ValueError(f'{owner}/{rel}: {error}') from error
        for entity in cache[text]:
            if not isinstance(entity,Field):continue
            if kind=='event' and ('.' not in entity.key or not isinstance(entity.value,list)):continue
            operation,key=entity.key.split(':',1) if ':' in entity.key else ('DEFINE',entity.key)
            if kind=='event':key=event_id(key)
            identity=kind+':'+key
            body=list(entity.value) if isinstance(entity.value,list) else [Field('value','=',entity.value)]
            record={'id':identity,'key':key,'kind':kind,'body':body,'owner':owner,'path':rel}
            if kind=='hook' and identity in nodes:
                nodes[identity]['body']=nodes[identity]['body']+body
                nodes[identity]['sources'].append((owner,rel))
            elif operation in {'INJECT','TRY_INJECT','INJECT_OR_CREATE'} and identity in nodes:
                nodes[identity]['body']=nodes[identity]['body']+body
            elif identity in nodes and operation=='DEFINE':
                # Unknown duplicate precedence: retain both possible edges.
                if nodes[identity]['body']!=body:
                    duplicates.append({'id':identity,'paths':[nodes[identity]['path'],rel]})
                    nodes[identity]['body']+=body
            else:
                nodes[identity]=record;record['sources']=[(owner,rel)]
    names=defaultdict(list)
    for identity,node in nodes.items():names[node['key']].append(identity)
    edges=[];unknown=[];metrics={};hook_errors=[];macro_cache={}
    ordered_names=sorted(names)
    def add(src,key,kinds,guarded,loops,delay=0,mechanism='call'):
        if 'event' in kinds:key=event_id(key)
        found=[identity for identity in names.get(key,[]) if nodes[identity]['kind'] in kinds]
        if not found and '$' in key:
            cache_key=(key,tuple(sorted(kinds)))
            if cache_key not in macro_cache:
                prefix=key.split('$',1)[0]
                expression=re.escape(key)
                for variable in re.findall(r'\$(\w+)\$',key):
                    domain=MACRO_DOMAINS.get(key,{}).get(variable,r'[^:$\s{}]+')
                    expression=expression.replace(re.escape('$'+variable+'$'),domain)
                expression='^'+expression+'$'
                pattern=re.compile(expression)
                candidates=[];position=bisect_left(ordered_names,prefix)
                while position<len(ordered_names) and ordered_names[position].startswith(prefix):
                    name=ordered_names[position];position+=1
                    if '$' not in name and pattern.fullmatch(name):
                        candidates.extend(identity for identity in names[name] if nodes[identity]['kind'] in kinds)
                    if len(candidates)>128:
                        candidates=[];break # broad unknown parameter, not 37k speculative edges
                macro_cache[cache_key]=candidates
            found=macro_cache[cache_key]
        for target in found:edges.append({'from':src,'to':target,'guarded':guarded,'loops':list(loops),
                                          'delay':delay,'mechanism':mechanism})
        if not found and '$' in key:
            unknown.append({'from':src,'target':key,'kind':'parameterized call'})
        return bool(found)
    def visit(items,src,guarded=False,loops=()):
        for item in items:
            if isinstance(item,list):
                visit(item,src,guarded,loops);continue
            if not isinstance(item,Field):continue
            key=item.key;value=item.value
            child_guard=guarded or key in CONDITIONAL or item.op=='?='
            is_loop=key in LOOPS or key.startswith(('every_','ordered_')) or key=='while'
            child_loops=loops+(key,) if is_loop else loops
            if is_loop:
                metrics[src]['loops'][key]+=1
                metrics[src]['max_loop_depth']=max(metrics[src]['max_loop_depth'],len(child_loops))
            if isinstance(value,str):
                if key in names:add(src,key,{'effect','trigger','value'},guarded,loops)
                elif '$' in key and not key.startswith(('var:','scope:')):add(src,key,{'effect','trigger','value'},guarded,loops)
                # Script values can be bare or scope-qualified; variables and
                # type references never become calls just by sharing a name.
                if ':' not in value and (key in VALUE_ARGUMENTS or item.op in {'<','>','<=','>='}):
                    target=value.split('.')[-1]
                    add(src,target,{'value'},guarded,loops,mechanism='value')
                if key=='fallback' and nodes[src]['kind']=='hook':
                    if not add(src,value,{'hook'},guarded,loops,mechanism='fallback'):
                        unknown.append({'from':src,'target':value,'kind':'missing fallback'})
            else:
                if not isinstance(value,list):continue
                if key in names:add(src,key,{'effect','trigger','value'},guarded,loops)
                elif '$' in key:add(src,key,{'effect','trigger','value'},guarded,loops)
                if key=='trigger_event':
                    values=scalars(value);target=values.get('id',values.get('on_action'))
                    delay=0
                    for unit in ['days','months','years']:
                        if unit in values:
                            try:delay=max(delay,float(values[unit]))
                            except ValueError:delay=-1
                    if target:
                        if not add(src,target,{'event','hook'},guarded,loops,delay,'trigger_event'):
                            unknown.append({'from':src,'target':target,'kind':'dynamic event' if '$' in target else 'missing event'})
                elif key in {'on_actions','events','first_valid','first_valid_on_action','random_events','random_on_actions'}:
                    kind='hook' if key in {'on_actions','first_valid_on_action','random_on_actions'} else 'event'
                    delay=0
                    for child in value:
                        if isinstance(child,Field) and child.key=='delay':
                            delay=1 # positive literal/range audited separately below
                        elif isinstance(child,str):
                            if child!='0' and not add(src,child,{kind},guarded or key.startswith(('random','first_valid')),loops,delay,'registration'):
                                unknown.append({'from':src,'target':child,'kind':'missing registration' if '$' not in child else 'parameterized registration'})
                        elif child.key.isdigit() and isinstance(child.value,str) and child.value!='0':
                            if not add(src,child.value,{kind},True,loops,delay,'random_registration'):
                                unknown.append({'from':src,'target':child.value,'kind':'missing registration' if '$' not in child.value else 'parameterized registration'})
                visit(value,src,child_guard,child_loops)
    for identity,node in nodes.items():
        metrics[identity]={'loops':Counter(),'fields':sum(1 for _ in walk(node['body'])),'max_loop_depth':0}
        if node['kind']=='hook':
            by_key=Counter(f.key for f in node['body'] if isinstance(f,Field))
            for key in ['effect','trigger']:
                if by_key[key]>1:hook_errors.append({'hook':identity,'field':key,'count':by_key[key],'sources':node['sources']})
            for member in node['body']:
                if isinstance(member,Field) and member.key=='on_actions' and isinstance(member.value,list):
                    registration.extend((identity,child) for child in member.value if isinstance(child,str))
        visit(node['body'],identity)
    repeats=[{'hook':key[0],'callback':key[1],'count':count} for key,count in Counter(registration).items() if count>1]
    direct=[(e['from'],e['to']) for e in edges if e['delay']<=0]
    unguarded=[(e['from'],e['to']) for e in edges if e['delay']<=0 and not e['guarded']]
    return {'nodes':nodes,'edges':edges,'same_tick_cycles':strongly_connected(nodes,direct),
            'unguarded_cycles':strongly_connected(nodes,unguarded),'all_cycles':strongly_connected(nodes,[(e['from'],e['to']) for e in edges]),
            'duplicate_registrations':repeats,'hook_field_conflicts':hook_errors,'duplicate_definitions':duplicates,
            'unknown_calls':unknown,'metrics':metrics,
            'macro_resolutions':[{'pattern':key[0],'kinds':list(key[1]),'candidates':value} for key,value in macro_cache.items()]}


def audit():
    research=json.loads(REPORT.read_text(encoding='utf-8'));cache={}
    baseline_files=load_vfs(research,cache)
    baseline=analyze(baseline_files,cache)
    combined=dict(baseline_files)
    for path in OUTPUT.rglob('*.txt'):
        rel=path.relative_to(OUTPUT).as_posix();category='events' if rel.startswith('events/') else path.parent.relative_to(OUTPUT).as_posix()
        if category in DATABASES or category=='events':combined[rel]=('patch',path.read_text(encoding='utf-8-sig'))
    patched=analyze(combined,cache)
    # Compare edge sets, not SCC equality: an old guarded SCC can become unsafe
    # through a new unguarded edge without changing its list of nodes.
    def new_records(key):
        old={json.dumps(v,sort_keys=True) for v in baseline[key]}
        return [v for v in patched[key] if json.dumps(v,sort_keys=True) not in old]
    old_edges={(e['from'],e['to'],e['guarded'],e['delay']) for e in baseline['edges']}
    added_edges=[e for e in patched['edges'] if (e['from'],e['to'],e['guarded'],e['delay']) not in old_edges]
    cyclic_added=[]
    for component in patched['same_tick_cycles']:
        members=set(component)
        internal=[e for e in added_edges if e['from'] in members and e['to'] in members and e['delay']<=0]
        if internal:cyclic_added.append({'nodes':component,'new_edges':internal})
    changed_metrics=[]
    for key,value in patched['metrics'].items():
        old=baseline['metrics'].get(key,{'fields':0,'loops':{},'max_loop_depth':0})
        if value!=old:changed_metrics.append({'id':key,'before':old,'after':value})
    result={'method':'conservative composed-VFS graph; no engine execution or runtime timing',
            'baseline_nodes':len(baseline['nodes']),'patched_nodes':len(patched['nodes']),
            'baseline_edges':len(baseline['edges']),'patched_edges':len(patched['edges']),
            'new_unguarded_cycles':new_records('unguarded_cycles'),
            'cycles_with_new_same_tick_edges':cyclic_added,
            'new_duplicate_registrations':new_records('duplicate_registrations'),
            'new_hook_field_conflicts':new_records('hook_field_conflicts'),
            'new_ambiguous_definitions':new_records('duplicate_definitions'),
            'new_unknown_calls':new_records('unknown_calls'),
            'patched_unknown_calls':patched['unknown_calls'],
            'literal_missing_targets':[row for row in patched['unknown_calls'] if '$' not in row['target']],
            'baseline_same_tick_cycles':baseline['same_tick_cycles'],
            'patched_same_tick_cycles':patched['same_tick_cycles'],
            'baseline_unguarded_cycles':baseline['unguarded_cycles'],
            'baseline_duplicate_registrations':baseline['duplicate_registrations'],
            'baseline_hook_field_conflicts':baseline['hook_field_conflicts'],
            'baseline_ambiguous_definitions':baseline['duplicate_definitions'],
            'patched_ambiguous_definitions':patched['duplicate_definitions'],
            'patched_duplicate_registrations':patched['duplicate_registrations'],
            'patched_hook_field_conflicts':patched['hook_field_conflicts'],
            'patched_unguarded_cycles':patched['unguarded_cycles'],
            'all_feedback_cycles':patched['all_cycles'],
            'macro_resolutions':patched['macro_resolutions'],
            'reviewed_macro_domains':MACRO_DOMAINS,
            'changed_structural_costs':changed_metrics,
            'added_edges':added_edges,
            'new_iteration_costs':[row for row in changed_metrics
                                   if (row['after']['max_loop_depth']>row['before']['max_loop_depth']
                                   or any(v>row['before']['loops'].get(k,0) for k,v in row['after']['loops'].items()))
                                   and not reviewed_iteration_optimization(row)],
            'reviewed_iteration_optimizations':[row for row in changed_metrics if reviewed_iteration_optimization(row)],
            'limitations':['conditional feasibility and engine callbacks are not executed',
                           'parameterized targets conservatively include every matching declared literal target',
                           'unknown event delay is not certified positive',
                           'AST field counts are structural proxies, not milliseconds or complexity proofs']}
    result['gate_failures']=gate_failures(result)
    result['status']='PASS' if not result['gate_failures'] else 'FAIL'
    result['patch_sha256']={p.relative_to(OUTPUT).as_posix():digest(p) for p in sorted(OUTPUT.rglob('*')) if p.is_file()}
    (ROOT/'docs/validation/runtime-graph.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['status','baseline_nodes','patched_nodes','baseline_edges','patched_edges',
                     'new_unguarded_cycles','cycles_with_new_same_tick_edges','new_duplicate_registrations',
                     'new_hook_field_conflicts','new_ambiguous_definitions','new_unknown_calls','new_iteration_costs','gate_failures']},ensure_ascii=True,indent=2))
    return result


def gate_failures(result):
    checks=['patched_unguarded_cycles','cycles_with_new_same_tick_edges','patched_duplicate_registrations',
            'patched_hook_field_conflicts','patched_ambiguous_definitions','new_unknown_calls','new_iteration_costs',
            'literal_missing_targets']
    return [key for key in checks if result[key]]


if __name__=='__main__':
    result=audit()
    if result['gate_failures']:raise SystemExit(1)
