"""Opt-in saves must reach the real operation entry points without disk writes by default."""
import sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from operation_save import optional_save,save_choice
import map_travel
import ground_loot


class OptionalSaveTests(unittest.TestCase):
    def test_only_explicit_true_invokes_native_save(self):
        with patch('native_save.save_current',return_value={'backup':'test-backup'}) as save:
            self.assertIsNone(optional_save());self.assertIsNone(optional_save(False));save.assert_not_called()
            self.assertEqual(optional_save(True,60),{'backup':'test-backup'});save.assert_called_once_with(60)
    def test_non_booleans_never_become_an_accidental_save(self):
        with patch('native_save.save_current') as save:
            for value in (None,0,1,'false','true',[],{}):
                with self.assertRaises(ValueError):save_choice(value)
                with self.assertRaises(ValueError):optional_save(value)
            save.assert_not_called()
    def test_map_travel_default_false_and_true_choose_save_before_request_lock(self):
        for options,expected in (({},False),({'save_before':False},False),({'save_before':True},True)):
            game=Mock();lock=Mock();lock.acquire.return_value=False
            with patch.object(map_travel,'Game',return_value=game),patch.object(map_travel,'identity',return_value={'binding':'character'}),patch.object(map_travel,'verify'),patch.object(map_travel,'validate_destination'),patch.object(map_travel,'LOCK',lock),patch('native_save.save_current',return_value={'backup':'saved'}) as save:
                with self.assertRaises(RuntimeError):map_travel.travel('00000000','character',**options)
                if expected:save.assert_called_once_with(30)
                else:save.assert_not_called()
                game.close.assert_called_once()
    def test_ground_sale_noop_reports_the_actual_save_choice(self):
        state=dict(pid=1,player=2,map=3)
        for options,expected in (({},False),({'save_before':False},False),({'save_before':True},True)):
            game=Mock();game.state.return_value=state;game.words.return_value=(0,)
            lock=Mock();lock.acquire.return_value=True
            with patch.object(ground_loot,'Game',return_value=game),patch.object(ground_loot,'VERIFIED',()),patch.object(ground_loot,'ground_equipment',return_value=[]),patch.object(ground_loot,'LOCK',lock),patch('native_save.save_current',return_value={'backup':'saved'}) as save:
                result=ground_loot.sell_ground('1:2:3',None,lambda:None,**options)
                self.assertIs(result['saved'],expected);self.assertEqual(result['backup'],'saved' if expected else None)
                if expected:save.assert_called_once_with(60)
                else:save.assert_not_called()
                lock.release.assert_called_once()
    def test_read_only_quote_never_saves_even_with_save_option(self):
        game=Mock();game.state.return_value=dict(pid=1,player=2,map=3)
        lock=Mock();lock.acquire.return_value=False
        with patch.object(ground_loot,'Game',return_value=game),patch.object(ground_loot,'LOCK',lock),patch('native_save.save_current') as save:
            with self.assertRaises(RuntimeError):ground_loot.sell_ground('1:2:3',None,lambda:None,dry_run=True,save_before=True)
            save.assert_not_called()
    def test_bad_choice_is_rejected_before_opening_game(self):
        for module,function,args in ((map_travel,map_travel.travel,('00000000','character')),(ground_loot,ground_loot.sell_ground,('1:2:3',None,lambda:None))):
            with patch.object(module,'Game') as game:
                with self.assertRaises(ValueError):function(*args,save_before='false')
                game.assert_not_called()

if __name__=='__main__':unittest.main()
