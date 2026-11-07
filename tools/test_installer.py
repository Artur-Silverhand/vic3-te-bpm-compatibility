import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from update_installed_patch import update
from build_patch import ROOT


class PatchInstallerContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_root=ROOT/'runtime/installer-tests'
        cls.temp_root.mkdir(parents=True,exist_ok=True)

    def fixture(self,root):
        assert root.resolve().is_relative_to(self.temp_root.resolve())
        baseline=root/'baseline';source=root/'source';target=root/'installed'
        identity='44a453ae-01a4-49e4-991c-4f1eaa2ae614'
        for folder,version in [(baseline,'0.4.0-dev'),(source,'0.5.0-dev')]:
            (folder/'.metadata').mkdir(parents=True)
            (folder/'.metadata/metadata.json').write_text(json.dumps({'id':identity,'version':version,'name':version}),encoding='utf-8')
            (folder/'example.txt').write_text(version,encoding='utf-8')
        (source/'new.txt').write_text('new',encoding='utf-8')
        shutil.copytree(baseline,target)
        return target,baseline,source,root/'backup'

    def test_owned_update_verifies_backup_and_never_touches_baseline(self):
        with tempfile.TemporaryDirectory(dir=self.temp_root) as temporary:
            args=self.fixture(Path(temporary));result=update(*args)
            target,baseline,source,backup=args
            self.assertEqual((backup/'example.txt').read_text(),'0.4.0-dev')
            self.assertEqual((baseline/'example.txt').read_text(),'0.4.0-dev')
            self.assertEqual((target/'example.txt').read_text(),'0.5.0-dev')
            self.assertEqual((target/'new.txt').read_text(),'new')
            self.assertFalse(result['game_launched']);self.assertFalse(result['playset_changed'])

    def test_user_edits_stop_before_backup_or_overwrite(self):
        with tempfile.TemporaryDirectory(dir=self.temp_root) as temporary:
            args=self.fixture(Path(temporary));target,_,_,backup=args
            (target/'example.txt').write_text('user edit',encoding='utf-8')
            with self.assertRaisesRegex(AssertionError,'was edited'):update(*args)
            self.assertEqual((target/'example.txt').read_text(),'user edit')
            self.assertFalse(backup.exists())

    def test_partial_write_failure_restores_owned_files(self):
        with tempfile.TemporaryDirectory(dir=self.temp_root) as temporary:
            args=self.fixture(Path(temporary));target,_,_,_=args
            real=Path.replace;counter=0
            def fail_once(path,destination):
                nonlocal counter
                counter+=1
                if counter==2:raise OSError('synthetic write failure')
                return real(path,destination)
            with patch.object(Path,'replace',fail_once):
                with self.assertRaisesRegex(OSError,'synthetic write failure'):update(*args)
            self.assertEqual((target/'example.txt').read_text(),'0.4.0-dev')
            self.assertFalse((target/'new.txt').exists())
            self.assertEqual(json.loads((target/'.metadata/metadata.json').read_text())['version'],'0.4.0-dev')


if __name__=='__main__':unittest.main(verbosity=2)
