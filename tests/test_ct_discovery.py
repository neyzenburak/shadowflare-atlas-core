"""Game-folder CT discovery is local, non-executing and respects removal."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import trainer
from ct_discovery import discover,read_local_file
from ct_table import empty_table,MAX_BYTES


def table(label='Example value'):
    return ('<CheatTable><CheatEntries><CheatEntry><ID>1</ID><Description>'+label+
            '</Description><VariableType>4 Bytes</VariableType><Address>fallbackPtr</Address>'
            '<Offsets><Offset>150</Offset></Offsets></CheatEntry></CheatEntries></CheatTable>').encode()


class CTDiscoveryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='atlas-ct-discovery-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.game=self.root/'game';self.game.mkdir();self.local=self.root/'local'
        patches=patch.multiple(trainer,LOCAL=self.local,PLAN=empty_table(),RECORDS={trainer.blackjack.ID:trainer.blackjack.RECORD})
        patches.start();self.addCleanup(patches.stop)
        locator=patch('game_paths.locate',return_value=self.game);self.locate=locator.start();self.addCleanup(locator.stop)
        native=patch.object(trainer,'Game');self.native=native.start();self.addCleanup(native.stop)
        self.control=trainer.Trainer(start_worker=False)

    def test_single_table_is_imported_without_opening_or_modifying_the_game(self):
        path=self.game/'My table.CT';path.write_bytes(table())
        self.control.discover_table()
        self.assertEqual(self.control.table()['source'],path.name)
        self.assertEqual(self.control.table()['records'][0]['label'],'Example value')
        self.assertTrue((self.local/'table.json').is_file())
        self.assertEqual(self.control.info()['active'],[])
        self.assertEqual(self.control.info()['frozen'],[])
        self.assertEqual(path.read_bytes(),table())
        self.native.assert_not_called()

    def test_only_top_level_files_are_considered(self):
        nested=self.game/'other';nested.mkdir();(nested/'nested.ct').write_bytes(table())
        (self.game/'directory.ct').mkdir();(self.game/'notes.txt').write_bytes(table())
        self.assertEqual(discover(self.game),[])
        self.control.discover_table();self.assertFalse(self.control.table()['sha256'])
        self.assertFalse(self.local.exists())

    def test_multiple_tables_require_selection_then_recover_when_unambiguous(self):
        first=self.game/'one.ct';first.write_bytes(table('First'))
        second=self.game/'two.ct';second.write_bytes(table('Second'))
        self.control.discover_table()
        self.assertFalse(self.control.table()['sha256'])
        self.assertIn('CT dosyas',self.control.info()['table']['discoveryMessage'])
        second.unlink();self.control.discover_table()
        self.assertEqual(self.control.table()['records'][0]['label'],'First')

    def test_existing_manual_import_is_not_replaced(self):
        self.control.import_table(table('Chosen manually'),'chosen.ct')
        (self.game/'other.ct').write_bytes(table('Discovered'))
        self.locate.reset_mock();self.control.discover_table()
        self.assertEqual(self.control.table()['source'],'chosen.ct')
        self.assertEqual(self.control.table()['records'][0]['label'],'Chosen manually')
        self.locate.assert_not_called();self.native.assert_not_called()

    def test_invalid_file_is_reported_and_can_be_repaired(self):
        path=self.game/'table.ct';path.write_bytes(b'not XML')
        self.control.discover_table()
        self.assertFalse(self.control.table()['sha256'])
        self.assertTrue(self.control.info()['table']['discoveryMessage'])
        self.assertIn(trainer.blackjack.ID,trainer.RECORDS)
        path.write_bytes(table());self.control.discover_table()
        self.assertTrue(self.control.table()['sha256'])
        self.assertEqual(self.control.info()['table']['discoveryMessage'],'')

    def test_oversized_file_is_not_read_and_growth_is_bounded(self):
        path=self.game/'large.ct'
        with path.open('wb') as stream:stream.truncate(MAX_BYTES+1)
        with patch.object(Path,'open',side_effect=AssertionError('Must check size before opening')):
            with self.assertRaises(ValueError):read_local_file(path)
        self.control.discover_table();self.assertFalse(self.control.table()['sha256'])
        path.write_bytes(b'')
        with self.assertRaises(ValueError):read_local_file(path)
        path.write_bytes(b'x'*(MAX_BYTES+1))
        from types import SimpleNamespace
        with patch.object(Path,'stat',return_value=SimpleNamespace(st_size=1)):
            with self.assertRaises(ValueError):read_local_file(path)

    def test_removal_stays_removed_across_restart_until_manual_import(self):
        (self.game/'table.ct').write_bytes(table())
        self.control.discover_table();self.control.remove_table()
        self.assertFalse((self.local/'table.json').exists())
        restarted=trainer.Trainer(start_worker=False);restarted.discover_table()
        self.assertFalse(restarted.table()['sha256'])
        self.assertTrue(restarted.info()['table']['autoImportBlocked'])
        restarted.import_table(table('Selected again'),'table.ct')
        self.assertFalse(restarted.info()['table']['autoImportBlocked'])
        self.assertFalse((self.local/'auto-import-disabled').exists())
        self.assertTrue(restarted.table()['sha256'])

    def test_discovery_waits_for_a_game_selection_and_does_not_execute_lua(self):
        self.locate.return_value=None;self.control.discover_table()
        self.assertFalse(self.local.exists())
        self.locate.return_value=self.game
        raw=b'<CheatTable><LuaScript>os.execute("never")</LuaScript><CheatEntries><CheatEntry><ID>1</ID><AssemblerScript>[ENABLE]\n{$lua}\nos.execute("never")\n[DISABLE]</AssemblerScript></CheatEntry></CheatEntries></CheatTable>'
        (self.game/'script.ct').write_bytes(raw);self.control.discover_table()
        self.assertEqual(self.control.table()['records'][0]['kind'],'unsupported')
        self.assertEqual(trainer.PLAN['patches'],{})
        self.assertEqual(self.control.info()['active'],[])
        self.native.assert_not_called()


if __name__=='__main__':unittest.main()
