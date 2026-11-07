"""Maintenance failures must block shipping; candidates must stay isolated."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from source_state import ROOT,source_state,require_fresh_inputs,load_lock,load_research,sha,scoped_files,pending_update_review
from update_patch import compare_file,symbols,impacts,candidate_path,check,HELPERS,stage,upstream


class UpdateContracts(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'runtime/update-tests';parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent)
        self.root=Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(parent.resolve()))
        self.addCleanup(self.temp.cleanup)
        self.te=self.root/'sources/upstream/TE';self.bpm=self.root/'sources/upstream/BPM'
        self.game=self.root/'steamapps/common/Victoria 3'
        for folder in (self.te,self.bpm,self.game/'game'):
            (folder/'common/scripted_effects').mkdir(parents=True)
            (folder/'common/scripted_effects/base.txt').write_text('base = { value = 1 }\n')
        for folder in (self.te,self.bpm):
            (folder/'.metadata').mkdir()
            (folder/'.metadata/metadata.json').write_text(json.dumps({'version':'1','supported_game_version':'1.15.*'}))
        for rel in HELPERS:
            path=self.te/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'helper\n')
        (self.game/'launcher').mkdir()
        (self.game/'launcher/launcher-settings.json').write_text(json.dumps({'rawVersion':'1.15.0'}))
        (self.game.parent.parent/'appmanifest_529340.acf').write_text('"buildid" "123"')
        self.policy={'patch_version':'0.6.0-dev','supported_game_version':'1.15.0'}
        self.write('project.json',self.policy)
        data={'sources':{label:{'root':'unused','files':{rel:{'sha256':value} for rel,value in scoped_files(folder).items()}}
                         for label,folder in [('timeline',self.te),('bpm',self.bpm),('game',self.game/'game')]}}
        self.write('docs/research/base.json',data)
        self.lock={'mods':{label:{'checkout':folder.relative_to(self.root).as_posix(),'mod_subdirectory':'.',
                                 'commit':('a' if label=='timeline' else 'b')*40,'workshop_root':str(folder)}
                           for label,folder in [('timeline',self.te),('bpm',self.bpm)]},
                   'game':{'root':str(self.game),'version':'1.15.0','steam_build_id':'123',
                           'launcher_settings_sha256':sha(self.game/'launcher/launcher-settings.json')},
                   'research_reports':{'github':{'path':'docs/research/base.json','sha256':sha(self.root/'docs/research/base.json')}}}
        self.write('sources.lock.json',self.lock)
        def fake_git(command,**kwargs):
            if 'show' in command:return b'helper\n'
            if 'status' in command:return ''
            return ('a' if command[2]==str(self.te) else 'b')*40+'\n'
        self.mock=patch('subprocess.check_output',side_effect=fake_git)
        self.mock.start();self.addCleanup(self.mock.stop)

    def write(self,relative,value):
        path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value),encoding='utf-8')

    def test_noop_and_relocated_report_roots_use_local_lock(self):
        self.assertEqual(load_research(self.root)['sources']['timeline']['root'],str(self.te))
        result=check(self.root,profile='pinned')
        self.assertEqual(result['status'],'UNCHANGED')
        self.assertEqual(source_state(self.root)['game']['steam_build_id'],'123')

    def test_new_runtime_file_blocks_previous_pass(self):
        gate={'source_state':source_state(self.root)}
        (self.te/'common/scripted_effects/new.txt').write_text('extra = {}')
        with self.assertRaisesRegex(ValueError,'inputs changed'):require_fresh_inputs(gate,self.root)

    def test_deleted_runtime_file_blocks_previous_pass(self):
        gate={'source_state':source_state(self.root)}
        (self.bpm/'common/scripted_effects/base.txt').unlink()
        with self.assertRaisesRegex(ValueError,'inputs changed'):require_fresh_inputs(gate,self.root)

    def test_edited_runtime_file_blocks_previous_pass(self):
        gate={'source_state':source_state(self.root)}
        (self.te/'common/scripted_effects/base.txt').write_text('base = { value = 2 }')
        with self.assertRaisesRegex(ValueError,'inputs changed'):require_fresh_inputs(gate,self.root)

    def test_localization_and_generator_changes_invalidate_gate(self):
        gate={'source_state':source_state(self.root)}
        path=self.te/'localization/english/test.yml';path.parent.mkdir(parents=True);path.write_text('l_english:')
        with self.assertRaisesRegex(ValueError,'since PASS'):require_fresh_inputs(gate,self.root)
        path.unlink()
        (self.te/HELPERS[0]).write_text('changed helper')
        with self.assertRaisesRegex(ValueError,'since PASS'):require_fresh_inputs(gate,self.root)

    def test_game_build_update_with_same_version_requires_review(self):
        (self.game.parent.parent/'appmanifest_529340.acf').write_text('"buildid" "124"')
        with self.assertRaisesRegex(ValueError,'Game build changed'):source_state(self.root)

    def test_new_game_version_cannot_be_declared_supported_by_lock_edit(self):
        self.lock['game']['version']='1.16.0';self.write('sources.lock.json',self.lock)
        (self.game/'launcher/launcher-settings.json').write_text(json.dumps({'rawVersion':'1.16.0'}))
        with self.assertRaisesRegex(ValueError,'Game API review'):source_state(self.root)

    def test_missing_input_binding_and_project_version_change_block_shipping(self):
        with self.assertRaisesRegex(ValueError,'predates'):require_fresh_inputs({},self.root)
        gate={'source_state':source_state(self.root)}
        self.policy['patch_version']='0.7.0-dev';self.write('project.json',self.policy)
        with self.assertRaisesRegex(ValueError,'since PASS'):require_fresh_inputs(gate,self.root)

    def test_profile_paths_are_local_overrides_without_changing_research_hash(self):
        self.write('paths.local.json',{'timeline':self.te.relative_to(self.root).as_posix()})
        self.assertEqual(load_lock(self.root)['mods']['timeline']['mod_root'],str(self.te))
        source_state(self.root)

    def test_hidden_operating_system_files_do_not_create_false_drift(self):
        before=source_state(self.root)
        (self.te/'common/.DS_Store').write_bytes(b'ignored')
        self.assertEqual(source_state(self.root),before)
        self.assertEqual(check(self.root,profile='pinned')['status'],'UNCHANGED')

    def test_triage_identifies_changed_symbol_and_override(self):
        path=self.bpm/'common/scripted_effects/base.txt'
        (self.root/'patch/common/scripted_effects').mkdir(parents=True)
        (self.root/'patch/common/scripted_effects/base.txt').write_text('patched = {}')
        path.write_text('base = { value = 2 }\nnew = { }')
        report=check(self.root,profile='pinned')
        self.assertEqual(report['status'],'REVIEW_REQUIRED')
        row=report['changes'][0]
        self.assertIn('same-path override',row['adapters'])
        # The baseline file was edited in place: do not pretend its old body is available.
        self.assertEqual(row['kind'],'changed_baseline_unavailable')

    def test_semantic_comparison_preserves_strings_and_duplicate_selectors(self):
        a=b'x = { v = "hello world" }\nINJECT:x = { a = 1 }\nINJECT:x = { b = 2 }'
        self.assertEqual(compare_file(a,a.replace(b'\n',b'\r\n'),'common/laws/a.txt')['kind'],'line_endings')
        self.assertEqual(compare_file(a,b'# comment\n'+a,'common/laws/a.txt')['kind'],'formatting')
        changed=compare_file(a,a.replace(b'hello world',b'hello  world'),'common/laws/a.txt')
        self.assertEqual(changed['changed_symbols'],['x'])
        self.assertEqual(len(symbols(a.decode())['x']),3)

    def test_candidate_path_escape_reuse_and_same_version_are_rejected(self):
        for name in ('../bad','a/b','..','-bad'):
            with self.assertRaises(ValueError):candidate_path(self.root,name)
        path=candidate_path(self.root,'safe');path.mkdir(parents=True)
        with self.assertRaises(FileExistsError):candidate_path(self.root,'safe')
        with self.assertRaisesRegex(ValueError,'new patch version'):stage('new','0.6.0-dev',root=self.root)
        self.assertFalse((self.root/'runtime/updates/new').exists())

    def test_unknown_changes_are_not_silently_auto_approved(self):
        (self.te/'common/unfamiliar').mkdir()
        (self.te/'common/unfamiliar/new.txt').write_text('surprise = { }')
        report=check(self.root,profile='pinned')
        self.assertEqual(report['status'],'REVIEW_REQUIRED')
        self.assertIn('unclassified: review required',report['changes'][0]['adapters'])

    def test_remote_update_check_only_fetches_and_never_checks_out(self):
        with patch('update_patch.subprocess.run') as run:
            result=upstream(fetch=True,root=self.root)
        self.assertEqual(run.call_count,2)
        self.assertTrue(all(call.args[0][-2:]==['fetch','origin'] for call in run.call_args_list))
        self.assertFalse(result['checked_out_or_installed'])

    def test_passing_synthetics_cannot_ship_unreviewed_upstream_changes(self):
        review={'input_context':{'lock_sha256':sha(self.root/'sources.lock.json'),
                 'research_sha256':sha(self.root/'docs/research/base.json')},
                'required':['overlap:new_category:new_entity'],'reviewed':{}}
        self.write('update-review.json',review)
        gate={'source_state':source_state(self.root)}
        with self.assertRaisesRegex(ValueError,'need review'):require_fresh_inputs(gate,self.root)
        review['reviewed']={review['required'][0]:'New definition merged in the adapter and contract verified'}
        self.write('update-review.json',review)
        with self.assertRaisesRegex(ValueError,'since PASS'):require_fresh_inputs(gate,self.root)
        require_fresh_inputs({'source_state':source_state(self.root)},self.root)

    def test_review_must_match_input_context_and_explain_decision(self):
        review={'input_context':{'lock_sha256':'wrong','research_sha256':'wrong'},'required':['change'],'reviewed':{}}
        self.write('update-review.json',review)
        with self.assertRaisesRegex(ValueError,'different inputs'):source_state(self.root)
        review['input_context']={'lock_sha256':sha(self.root/'sources.lock.json'),
                                 'research_sha256':sha(self.root/'docs/research/base.json')}
        review['reviewed']={'change':''};self.write('update-review.json',review)
        with self.assertRaisesRegex(ValueError,'explanation'):pending_update_review(self.root)


if __name__=='__main__':unittest.main(verbosity=2)
