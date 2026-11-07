"""Execute cabinet adapters' script subset with explicit native-game boundaries.

Character selection/creation and stance getters are supplied inputs. Lists,
scopes, arithmetic, loops and the emitted guards are executed from their AST.
"""
from copy import deepcopy
from fractions import Fraction
from script_syntax import Field,scalars


class CabinetModel:
    def __init__(self,effects,characters=None,pool=None,player=True,variety=False,laws=None,charset=None,picker=None):
        self.effects=effects;self.characters=deepcopy(characters or {})
        self.lists={'C':{'bpm_CAB_char_select_pool':list(pool or []),
                          'bpm_CAB_temp_pool':[],'bpm_synergy_calculation_charset':list(charset or [])},'F':{}}
        self.vars={'C':{},'F':{}};self.locals={};self.scopes={};self.stack=[('country','C')]
        self.laws=list(laws or []);self.player=player;self.variety=variety;self.picker=picker
        self.attempts=0;self.steps=0;self.stance_reads=0;self.law_visits=0

    def resolve(self,name):
        if name.lower()=='prev':return self.stack[-2] if len(self.stack)>1 else None
        if name.lower() in {'this','root'}:return self.stack[-1] if name.lower()=='this' else self.stack[0]
        if name.startswith('scope:'):return self.scopes.get(name[6:])
        raise ValueError('Unknown scope '+name)

    def owner(self):
        kind,key=self.stack[-1]
        if kind=='law':return ('country','C')
        if kind=='character':return ('country',self.characters[key]['owner'])
        raise ValueError('Country owner not defined in model')

    def country(self):
        assert self.stack[-1][0]=='country',self.stack
        return self.stack[-1][1]

    def lists_here(self):return self.lists[self.country()]

    def push(self,scope,action):
        assert scope is not None
        self.stack.append(scope)
        try:return action()
        finally:self.stack.pop()

    def value(self,value):
        if isinstance(value,list):return self.expression(value)
        if value.startswith('local_var:'):return self.locals.get(value[10:],Fraction(0))
        if value.startswith('scope:'):
            scope=self.resolve(value);assert scope and scope[0]=='value',value
            return scope[1]
        if value in {'bpm_character_law_stance_as_number','bpm_character_law_stance_as_number_abs',
                     'bpm_character_law_stance_as_number_negative'}:
            self.stance_reads+=1;assert self.stack[-1][0]=='character'
            law=self.scopes['bpm_law_to_check'][1]
            stance=Fraction(self.characters[self.stack[-1][1]]['stances'][law])
            return stance+2 if value.endswith('_abs') else -stance if value.endswith('_negative') else stance
        if value=='bpm_synergy_of_charset_divisor':
            self.law_visits+=len(self.laws)
            return Fraction(max(1,len(self.laws)))
        return Fraction(value)

    def expression(self,items,start=Fraction(0)):
        result=start;chain=False
        for f in items:
            if f.key in {'if','else_if'}:
                if f.key=='if':chain=False
                if not chain:
                    chain=self.check(next(x.value for x in f.value if x.key=='limit'))
                    if chain:result=self.expression([x for x in f.value if x.key!='limit'],result)
                continue
            v=self.value(f.value)
            if f.key=='value':result=v
            elif f.key=='add':result+=v
            elif f.key=='subtract':result-=v
            elif f.key=='multiply':result*=v
            elif f.key=='divide':result/=v
            elif f.key=='min':result=max(result,v) # Paradox 'min' is the lower bound
            else:raise ValueError('Unknown expression '+f.key)
        return result

    def check(self,items,mode='AND'):
        results=[];chain=False
        for f in items:
            key=f.key;v=f.value
            if key in {'trigger_if','trigger_else_if'}:
                if key=='trigger_if':chain=False
                if not chain:
                    chain=self.check(next(x.value for x in v if x.key=='limit'))
                    if chain:results.append(self.check([x for x in v if x.key!='limit']))
            elif key=='trigger_else':
                if not chain:results.append(self.check(v))
            elif key in {'AND','OR','NOT','NOR','NAND'}:results.append(self.check(v,key))
            elif key.startswith(('local_var:','scope:')) and not isinstance(v,list):
                a=self.value(key);b=self.value(v)
                results.append({'=':a==b,'<':a<b,'>':a>b,'<=':a<=b,'>=':a>=b}[f.op])
            elif key=='always':results.append(v=='yes')
            elif key=='is_player':results.append(self.player==(v=='yes'))
            elif key=='modifier:country_bpm_cabinet_variety':results.append(self.variety==(v=='yes'))
            elif key=='is_character_alive':results.append(self.characters[self.stack[-1][1]]['alive']==(v=='yes'))
            elif key=='owner':results.append(self.owner()==self.resolve(v))
            elif key=='exists':results.append(self.resolve(v) is not None)
            elif key=='has_variable_list':results.append(bool(self.lists_here().get(v,[])))
            elif key=='variable_list_size':
                data=scalars(v);condition=next(x for x in v if x.key=='value')
                size=len(self.lists_here().get(data['name'],[]));limit=int(condition.value)
                results.append({'<=':size<=limit,'<':size<limit,'>':size>limit,'=':size==limit}[condition.op])
            elif key=='is_target_in_variable_list':
                data=scalars(v);target=self.resolve(data['target'])
                results.append(target is not None and target[1] in self.lists_here().get(data['name'],[]))
            elif key.startswith('scope:') and isinstance(v,list):results.append(self.push(self.resolve(key),lambda:self.check(v)))
            else:raise ValueError('Unknown trigger '+key)
        if mode=='AND':return all(results)
        if mode=='OR':return any(results)
        if mode in {'NOT','NOR'}:return not any(results)
        if mode=='NAND':return not all(results)
        raise ValueError(mode)

    def execute(self,key):
        if key=='bpm_pick_cabinet_minister':
            # Native weighted choice and creation are unchanged by the patch.
            # Execute the emitted reset, then its emitted insertion guard.
            self.run(self.effects[key][:1]);self.attempts+=1
            choice=self.picker(self) if self.picker else None
            if choice:
                kind,character=choice
                self.scopes['ranig.leader' if kind=='leader' else 'ranchar']=('character',character) if character else None
                self.execute('tbcp_cabinet_try_add_'+kind)
            return
        self.run(self.effects[key])

    def run(self,items):
        chain=False
        for f in items:
            self.steps+=1
            if self.steps>2000000:raise RuntimeError('Synthetic step budget exceeded')
            key=f.key;v=f.value
            if key in {'if','else_if'}:
                if key=='if':chain=False
                if not chain:
                    chain=self.check(next(x.value for x in v if x.key=='limit'))
                    if chain:self.run([x for x in v if x.key!='limit'])
            elif key=='else':
                if not chain:self.run(v)
            elif key=='while':
                limit=next(x.value for x in v if x.key=='limit');count=0
                while self.check(limit):
                    count+=1
                    if count>100:raise RuntimeError('Nonterminating synthetic while')
                    self.run([x for x in v if x.key!='limit'])
            elif key in {'set_local_variable','change_local_variable','set_variable','change_variable'}:
                data=scalars(v);name=data['name']
                store=self.locals if 'local' in key else self.vars[self.country()]
                expression=[x for x in v if x.key!='name']
                store[name]=self.expression(expression,Fraction(0) if key.startswith('set_') else store.get(name,Fraction(0)))
            elif key=='clear_variable_list':self.lists_here()[v]=[]
            elif key=='add_to_variable_list':
                data=scalars(v);target=self.resolve(data['target']);assert target
                # Use append semantics, a stricter stress model than automatic
                # engine deduplication. The emitted guards must prevent duplicates.
                self.lists_here().setdefault(data['name'],[]).append(target[1])
            elif key=='every_in_list':
                data=scalars(v);characters=list(self.lists_here().get(data['variable'],[]))
                for character in characters:
                    if character in self.characters:self.push(('character',character),lambda:self.run([x for x in v if x.key!='variable']))
            elif key=='ordered_in_list':
                data=scalars(v);characters=list(self.lists_here().get(data['variable'],[]))
                scores=[(self.push(('character',c),lambda:self.value(data['order_by'])),i,c) for i,c in enumerate(characters)]
                if scores:
                    chosen=max(scores,key=lambda item:(item[0],-item[1]))[2]
                    self.push(('character',chosen),lambda:self.run([x for x in v if x.key not in {'variable','order_by','position'}]))
            elif key=='every_law':
                for law in self.laws:
                    self.law_visits+=1;self.push(('law',law),lambda:self.run(v))
            elif key=='owner':self.push(self.owner(),lambda:self.run(v))
            elif key=='save_scope_as':self.scopes[v]=self.stack[-1]
            elif key=='save_scope_value_as':
                data=scalars(v);self.scopes[data['name']]=('value',self.value(data['value']))
            elif key in self.effects:self.execute(key)
            else:raise ValueError('Unknown effect '+key)
