"""Execute the adapter's restricted script subset against synthetic fiscal state.

Native TE calls are explicit model boundaries. This verifies our state/branch
contracts, not engine scheduling, caches, scopes or modifier implementation.
"""
from copy import deepcopy
from script_syntax import parse,Field,scalars


class FiscalModel:
    def __init__(self,effects,triggers,rows,state):
        self.effects={v.key:v.value for v in parse(effects) if isinstance(v,Field)}
        self.triggers={v.key:v.value for v in parse(triggers) if isinstance(v,Field)}
        self.rows=rows;self.state=deepcopy(state);self.events=[];self.native_laws=[]
        self.locals={};self.accepted=[]
        self.steps=0;self.depth=0

    def value(self,value):
        if value.startswith('local_var:'):return self.locals.get(value[10:],0)
        if value.startswith('var:'):return self.state['vars'].get(value[4:],0)
        if value.startswith('te_tax_ai_clout_'):
            data=self.state['ai'][value.removeprefix('te_tax_ai_clout_')]
            return data['clout'] if data['eligible'] else -1
        if value=='te_tax_today':return self.state['day']
        try:return float(value)
        except ValueError:return value

    def check(self,items,mode='AND'):
        result=[];chain=False
        for item in items:
            assert isinstance(item,Field),item
            key=item.key;v=item.value
            if key=='trigger_if':
                limit=next(f.value for f in v if isinstance(f,Field) and f.key=='limit')
                chain=self.check(limit)
                if chain:result.append(self.check([f for f in v if f.key!='limit']))
            elif key=='trigger_else_if':
                if not chain:
                    limit=next(f.value for f in v if f.key=='limit');chain=self.check(limit)
                    if chain:result.append(self.check([f for f in v if f.key!='limit']))
            elif key=='trigger_else':
                if not chain:result.append(self.check(v))
            elif key in {'AND','OR','NOT','NOR','NAND'}:result.append(self.check(v,key))
            elif key=='has_variable':result.append(v in self.state['vars'])
            elif key.startswith(('var:','local_var:')):
                a=self.value(key);b=self.value(v)
                result.append({'=':a==b,'==':a==b,'!=':a!=b,'<':a<b,'>':a>b,'<=':a<=b,'>=':a>=b}[item.op])
            elif key=='has_law' or key=='has_law_or_variant':result.append(self.state['law']==v.removeprefix('law_type:'))
            elif key=='tax_level':result.append(self.state['level']==v)
            elif key=='te_tax_code_in_force':result.append(self.state['full'] and self.state['vars'].get('te_tax_migrated',0)>=1)
            elif key in {'te_tax_ai_offer_acceptable','te_tax_ai_persuadable'}:
                group=scalars(v)['IG'];column='acceptable' if key=='te_tax_ai_offer_acceptable' else 'persuadable'
                result.append(self.state['ai'][group][column])
            elif key.startswith('te_tax_code_equivalent_'):
                variables=self.state['vars'];w=variables.get('te_tax_en_wage',0);d=variables.get('te_tax_en_div',0)
                if w>=4 and d>=w:short='graduated'
                elif w>=4 and d>=1:short='proportional'
                elif variables.get('te_tax_en_head',0)>=1 and w>=1:short='per_capita'
                elif variables.get('te_tax_en_land',0)>=1:short='land_based'
                else:short='consumption_based'
                result.append(key=='te_tax_code_equivalent_'+short)
            elif key in self.triggers:result.append(self.check(self.triggers[key]))
            else:raise ValueError('Unmodelled trigger '+key)
        if mode=='AND':return all(result)
        if mode=='OR':return any(result)
        if mode in {'NOT','NOR'}:return not any(result)
        if mode=='NAND':return not all(result)
        raise ValueError(mode)

    def execute(self,key):
        self.depth+=1
        if self.depth>16:raise RuntimeError('Adapter recursion: '+key)
        try:self.run(self.effects[key])
        finally:self.depth-=1

    def run(self,items):
        chain=False
        for item in items:
            self.steps+=1
            if self.steps>20000:raise RuntimeError('Unbounded synthetic execution')
            assert isinstance(item,Field),item
            key=item.key;v=item.value
            if key in {'if','else_if'}:
                if key=='if':chain=False
                if not chain:
                    limit=next(f.value for f in v if isinstance(f,Field) and f.key=='limit')
                    chain=self.check(limit)
                    if chain:self.run([f for f in v if f.key!='limit'])
            elif key=='else':
                if not chain:self.run(v)
            elif key in self.effects:self.execute(key)
            elif key=='set_variable':
                data=scalars(v);self.state['vars'][data['name']]=self.value(data['value'])
            elif key=='set_local_variable':
                data=scalars(v);self.locals[data['name']]=self.value(data['value'])
            elif key=='change_variable':
                data=scalars(v);self.state['vars'][data['name']]=self.state['vars'].get(data['name'],0)+self.value(data['add'])
            elif key=='te_tax_gen_migrate_provisions':
                for rate in ['wage','div','land','head','cons']:
                    variables=self.state['vars'];prefix='te_tax_en_'+rate
                    variables[prefix+'_since']=self.state['month'] if variables[prefix]>0 else -1
                    variables[prefix+'_exp']=-1;variables[prefix+'_succ']=-1
                    xver='te_tax_xver_'+rate;variables[xver]=variables.get(xver,0)+1
            elif key=='trigger_event':self.events.append(scalars(v))
            elif key=='activate_law':
                self.state['law']=v.removeprefix('law_type:');self.native_laws.append(self.state['law'])
            elif key=='te_tax_ai_accept_offer':self.accepted.append(scalars(v)['IG'])
            elif key=='debug_log':pass
            else:raise ValueError('Unmodelled effect '+key)
