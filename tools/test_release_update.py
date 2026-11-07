"""A release name cannot silently acquire different bytes after an update."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import package_patch
from source_state import ROOT,sha


class ReleaseUpdateContracts(unittest.TestCase):
    def test_existing_release_is_immutable_even_with_fresh_pass(self):
        parent=ROOT/'runtime/release-tests';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as name:
            root=Path(name).resolve();self.assertTrue(root.is_relative_to(parent.resolve()))
            output=root/'patch';output.mkdir();(output/'.metadata').mkdir();(root/'tools').mkdir()
            reports=root/'docs/validation';reports.mkdir(parents=True)
            (root/'project.json').write_text(json.dumps({'patch_version':'9.0.0-dev','supported_game_version':'1.15.0'}))
            (output/'.metadata/metadata.json').write_text(json.dumps({'version':'9.0.0-dev'}))
            data=output/'data.txt';data.write_text('first version')
            build={'version':'9.0.0-dev','source_commits':{},'status':'candidate','open':[]}
            (reports/'build-manifest.json').write_text(json.dumps(build))
            def fresh_reports():
                hashes={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}
                (reports/'offline-audit.json').write_text(json.dumps({'unresolved_typed_references':[],
                    'unknown_replacements':[],'duplicate_generated_entities':[],'patch_sha256':hashes}))
                (reports/'synthetic-gate.json').write_text(json.dumps({'version':'9.0.0-dev','status':'PASS',
                    'patch_sha256':hashes,'tools_sha256':{}}))
            fresh_reports()
            with patch.object(package_patch,'ROOT',root),patch.object(package_patch,'OUTPUT',output),\
                 patch.object(package_patch,'VERSION','9.0.0-dev'),patch.object(package_patch,'require_fresh_inputs'):
                original=package_patch.package();archive=root/original['archive'];before=sha(archive)
                self.assertEqual(package_patch.package()['sha256'],before)
                # Preserve an existing archive's exact bytes even if another
                # compressor/tool would encode the same members differently.
                with zipfile.ZipFile(archive) as package:members={name:package.read(name) for name in package.namelist()}
                with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED) as package:
                    for name,content in members.items():package.writestr(name,content)
                before=sha(archive)
                self.assertEqual(package_patch.package()['sha256'],before)
                data.write_text('different version');fresh_reports()
                with self.assertRaisesRegex(AssertionError,'Immutable release'):package_patch.package()
                self.assertEqual(sha(archive),before)


if __name__=='__main__':unittest.main(verbosity=2)
