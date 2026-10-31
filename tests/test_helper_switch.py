"""Switching checkouts stops only the old companion, never the game."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import live_server as server


class HelperSwitchTests(unittest.TestCase):
    def helper(self,**changes):
        return dict(bridge='ShadowFlare Atlas Live Drop 1',protocol=19,installationId=server.INSTALLATION_ID,token='test-only',helperPid=123,**changes)

    def test_same_checkout_is_reused_without_requests(self):
        old=self.helper()
        with patch.object(server,'urlopen')as request:
            self.assertIs(server.select_existing_helper(old,'http://127.0.0.1:8770/'),old)
        request.assert_not_called()

    def test_other_checkout_uses_authenticated_stop_instead_of_old_source_restart(self):
        old=self.helper();old['installationId']='another-installation'
        with patch.object(server,'urlopen',side_effect=[io.BytesIO(b'{"state":"stopping"}'),OSError('closed')])as request,patch.object(server.time,'sleep'):
            self.assertEqual(server.select_existing_helper(old,'http://127.0.0.1:8770/'),{})
        stop=request.call_args_list[0].args[0]
        self.assertTrue(stop.full_url.endswith('/api/live/stop'))
        self.assertEqual(stop.get_header('X-atlas-token'),'test-only')
        self.assertEqual(stop.get_header('Origin'),'http://127.0.0.1:8770')

    def test_previous_protocol_is_switched_even_without_installation_identity(self):
        old=self.helper();old['protocol']=18;old.pop('installationId')
        with patch.object(server,'urlopen',side_effect=[io.BytesIO(b'{}'),OSError('closed')]),patch.object(server.time,'sleep'):
            self.assertEqual(server.select_existing_helper(old,'http://127.0.0.1:8770/'),{})

    def test_unknown_local_server_is_not_stopped(self):
        old={'bridge':'another app'}
        with patch.object(server,'urlopen')as request:self.assertIs(server.select_existing_helper(old,'http://127.0.0.1:8770/'),old)
        request.assert_not_called()


if __name__=='__main__':unittest.main()
