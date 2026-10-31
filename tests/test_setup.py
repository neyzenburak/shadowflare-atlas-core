"""Portable setup: paths, privacy, and ZIP imports must not overwrite code."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import unittest
import types
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tools')]
import game_paths as G
from import_assets import import_assets
from build_assets import CRITICAL,is_ready,trainer,read_js,build_lock,publish


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='atlas-setup-test-')
        self.base=Path(self.temp.name).resolve()
        assert self.base.parent==Path(tempfile.gettempdir()).resolve()
        self.game=self.base/'Oyun \u00e7\u0131\u011f\u00f6\u015f\u00fc'
        for name in ('ShadowFlare.exe','System/Game/Parameter/Item.Ibn','System/Game/Parameter/Table.Tbd',
                     'System/Game/Pattern/Item0000.njp','System/Common/Pattern/Font00.njp'):
            p=self.game/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'test fixture')
        for name in ('Scenario','Map','Character/ENEMY'):(self.game/name).mkdir(parents=True)
        self.sha=patch.object(G,'EXE_SHA256',hashlib.sha256(b'test fixture').hexdigest());self.sha.start()
        self.settings=self.base/'settings.json'

    def tearDown(self):
        self.sha.stop();self.temp.cleanup()

    def test_executable_or_folder_and_unicode(self):
        self.assertEqual(G.validate(self.game),self.game)
        self.assertEqual(G.validate(self.game/'ShadowFlare.exe'),self.game)

    def test_remember_preserves_other_settings(self):
        self.settings.write_text('{"keep":42}','utf8')
        G.remember(self.game,self.settings)
        self.assertEqual(G.load_settings(self.settings)['keep'],42)
        with patch.dict(os.environ,{},clear=True):self.assertEqual(G.locate(settings=self.settings),self.game)

    def test_wrong_build_rejected_without_writes(self):
        (self.game/'ShadowFlare.exe').write_bytes(b'unsupported')
        with self.assertRaisesRegex(ValueError,'Unsupported'):G.remember(self.game,self.settings)
        self.assertFalse(self.settings.exists())

    def test_multiple_installations_require_selection(self):
        other=self.base/'second';other.mkdir()
        with patch.dict(os.environ,{},clear=True),patch.object(G,'running_games',return_value=[self.game,other]),patch.object(G,'validate',side_effect=lambda p:Path(p)):
            self.assertIsNone(G.locate(settings=self.settings))

    def test_bad_configuration_is_ignored(self):
        for text in ('not json','[]','null'):
            self.settings.write_text(text,'utf8');self.assertEqual(G.load_settings(self.settings),{})

    def test_import_keeps_controllers(self):
        archive=self.base/'assets.zip';app=self.base/'app';app.mkdir();(app/'maps.js').write_text('current controller','utf8')
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('app/maps.js','obsolete controller');z.writestr('app/data.js','catalogue');z.writestr('app/assets/example.png',b'pixels')
        self.assertEqual(import_assets(archive,app),2)
        self.assertEqual((app/'maps.js').read_text('utf8'),'current controller')

    def test_zip_traversal_rejected(self):
        archive=self.base/'bad.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape','bad')
        with self.assertRaises(ValueError):import_assets(archive,self.base/'app')
        self.assertFalse((self.base.parent/'escape').exists())

    def test_import_skips_language_resources_from_full_edition_zip(self):
        archive=self.base/'full-edition.zip';app=self.base/'imported'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('app/data.js','catalogue')
            z.writestr('app/assets/turkish/Font00.njp',b'language patch')
        self.assertEqual(import_assets(archive,app),1)
        self.assertFalse((app/'assets/turkish').exists())

    def test_publish_skips_language_resources_from_old_build_output(self):
        output=self.base/'old-output';app=self.base/'published'
        (output/'assets/turkish').mkdir(parents=True)
        (output/'assets/turkish/Font00.njp').write_bytes(b'language patch')
        (output/'data.js').write_text('catalogue','utf8')
        publish(output,app,{},'test')
        self.assertEqual((app/'data.js').read_text('utf8'),'catalogue')
        self.assertFalse((app/'assets/turkish').exists())
        manifest=json.loads((app/'assets/setup-manifest.json').read_text('utf8'))
        self.assertEqual([f['path'] for f in manifest['files']],['data.js'])

    def test_readiness_requires_all_entrypoints(self):
        app=self.base/'generated'
        for name in CRITICAL:
            self.assertFalse(is_ready(app));p=app/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'x')
        self.assertTrue(is_ready(app))

    def test_optional_guide_images_are_not_broken_references(self):
        world=json.loads((ROOT/'tools/asset_build/reference/world-guide.json').read_text('utf8'))
        self.assertTrue(all(not s.get('src')for s in world['sources'].values()))
        self.assertTrue(all(not s.get('src')for s in world['questRequirements']))

    def test_setup_ships_no_external_trainer_records(self):
        out=self.base/'trainer';out.mkdir()
        with patch.dict(sys.modules,{'paths':types.SimpleNamespace(GAME=self.base/'no-game-files',OUTPUT=out)}):trainer()
        data=read_js(out/'trainer-data.js')
        self.assertEqual(data['records'],[])
        self.assertEqual(data['structures'],[])
        self.assertEqual(data['patches'],{})

    def test_overlapping_build_is_rejected(self):
        with patch('build_assets.ROOT',self.base):
            with build_lock():
                with self.assertRaisesRegex(RuntimeError,'already running'):
                    with build_lock():self.fail('Two overlapping builders acquired the lock')
            with build_lock():pass

    def test_malformed_optional_ct_does_not_block_setup(self):
        out=self.base/'trainer';out.mkdir()
        (out/'ShadowFlare v2-004 by Starcraster.ct').write_text('broken optional XML','utf8')
        with patch.dict(sys.modules,{'paths':types.SimpleNamespace(GAME=out,OUTPUT=out)}):trainer()
        self.assertEqual(read_js(out/'trainer-data.js')['records'],[])


if __name__=='__main__':unittest.main()
