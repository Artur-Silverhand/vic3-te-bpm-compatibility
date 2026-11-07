"""One offline gate: contracts, synthetic execution, references and runtime graph."""
import json
import unittest
from build_patch import ROOT,VERSION,digest
from audit_patch import audit as audit_files
from audit_runtime_graph import audit as audit_graph


def verify():
    destination=ROOT/'docs/validation/synthetic-gate.json'
    destination.write_text(json.dumps({'version':VERSION,'status':'RUNNING'})+'\n',encoding='utf-8')
    tool_hashes={p.relative_to(ROOT).as_posix():digest(p) for p in sorted((ROOT/'tools').glob('*')) if p.suffix in {'.py','.ps1'}}
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tools'),pattern='test_*.py')
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        destination.write_text(json.dumps({'version':VERSION,'status':'FAIL','tests_run':result.testsRun,
                                           'failures':len(result.failures),'errors':len(result.errors)})+'\n',encoding='utf-8')
        raise SystemExit(1)
    try:files=audit_files();graph=audit_graph()
    except Exception as error:
        destination.write_text(json.dumps({'version':VERSION,'status':'FAIL','audit_error':str(error)})+'\n',encoding='utf-8')
        raise
    assert tool_hashes=={p.relative_to(ROOT).as_posix():digest(p) for p in sorted((ROOT/'tools').glob('*')) if p.suffix in {'.py','.ps1'}},'Tools changed during gate'
    record={'version':VERSION,'status':'PASS' if not graph['gate_failures'] else 'FAIL',
            'tests_run':result.testsRun,'tests_passed':True,
            'graph_failures':graph['gate_failures'],'graph_nodes':graph['patched_nodes'],
            'graph_edges':graph['patched_edges'],'patch_sha256':files['patch_sha256'],
            'tools_sha256':tool_hashes,
            'game_launched':False,'engine_or_performance_verified':False,
            'scope':'structural regression, ambiguity, call-cycle, reference and synthetic state contracts'}
    destination.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    if record['status']!='PASS':raise SystemExit(1)
    print(json.dumps({k:v for k,v in record.items() if k not in {'patch_sha256','tools_sha256'}},indent=2))
    return record


if __name__=='__main__':verify()
