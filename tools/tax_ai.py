"""Linear offer selection preserving TE's persuasion/clout/tie ordering."""
from script_syntax import parse as ast_parse,walk


def optimize(text,igs,parse):
    node=next(n for n in parse(text) if n['key']=='te_tax_gen_ai_accept_offer')
    pieces=['''
# Same ordering as TE: persuadable first; clout descending; fixed IGS tie order.
# Pick before executing any offer, so support cannot change during selection.
set_local_variable = { name = tbcp_tax_best_group value = 0 }
set_local_variable = { name = tbcp_tax_best_tier value = -1 }
set_local_variable = { name = tbcp_tax_best_clout value = -1 }
''']
    for index,ig in enumerate(igs,start=1):
        pieces.append(f'''
set_local_variable = {{ name = tbcp_tax_candidate_clout value = te_tax_ai_clout_{ig} }}
if = {{
    limit = {{ local_var:tbcp_tax_candidate_clout >= 0 te_tax_ai_offer_acceptable = {{ IG = {ig} }} }}
    set_local_variable = {{ name = tbcp_tax_candidate_tier value = 0 }}
    if = {{
        limit = {{ te_tax_ai_persuadable = {{ IG = {ig} }} }}
        set_local_variable = {{ name = tbcp_tax_candidate_tier value = 1 }}
    }}
    if = {{
        limit = {{
            OR = {{
                local_var:tbcp_tax_best_group = 0
                local_var:tbcp_tax_candidate_tier > local_var:tbcp_tax_best_tier
                AND = {{
                    local_var:tbcp_tax_candidate_tier = local_var:tbcp_tax_best_tier
                    local_var:tbcp_tax_candidate_clout > local_var:tbcp_tax_best_clout
                }}
            }}
        }}
        set_local_variable = {{ name = tbcp_tax_best_group value = {index} }}
        set_local_variable = {{ name = tbcp_tax_best_tier value = local_var:tbcp_tax_candidate_tier }}
        set_local_variable = {{ name = tbcp_tax_best_clout value = local_var:tbcp_tax_candidate_clout }}
    }}
}}
''')
    for index,ig in enumerate(igs,start=1):
        pieces.append(f'''{'if' if index==1 else 'else_if'} = {{
    limit = {{ local_var:tbcp_tax_best_group = {index} }}
    te_tax_ai_accept_offer = {{ IG = {ig} }}
}}
''')
    body='\n'.join(pieces)
    old=sum(1 for _ in walk(ast_parse(node['body'])))
    new=sum(1 for _ in walk(ast_parse(body)))
    assert new<old
    result=text[:node['start']]+'te_tax_gen_ai_accept_offer = {\n'+body+'}\n'+text[node['end']:]
    return result,{'function':'te_tax_gen_ai_accept_offer','old_ast_fields':old,'new_ast_fields':new,
                  'algorithm':'one clout/eligibility scan plus one dispatch; linear in IG count',
                  'tie_policy':'earlier IGS wins equal clout within same persuasion tier'}
