"""Local-only CT parsing and bounded, reversible code generation."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'app'))
from ct_table import parse,empty_table
from ct_asm import assemble,patch_span


def table(entry):return ('<CheatTable><CheatEntries>'+entry+'</CheatEntries></CheatTable>').encode()


class CTTests(unittest.TestCase):
    def test_no_bundled_table(self):
        self.assertEqual(empty_table()['records'],[])
        self.assertFalse((ROOT/'app/trainer-plan.json').exists())
        self.assertEqual(list((ROOT/'app').glob('*.ct')),[])

    def test_value_hierarchy_and_arithmetic_offsets(self):
        xml=table('<CheatEntry><ID>1</ID><Description>Example</Description><CheatEntries><CheatEntry><ID>2</ID><Description>Value</Description><VariableType>4 Bytes</VariableType><Address>fallbackPtr</Address><Offsets><Offset>E8+68</Offset></Offsets></CheatEntry></CheatEntries></CheatEntry>')
        result=parse(xml,'unused.exe');group,value=result['records']
        self.assertEqual(value['parent'],group['id']);self.assertEqual(value['offsets'],[0x150])
        self.assertEqual(value['kind'],'value')

    def test_pointer_action_is_data_not_executed_script(self):
        xml=table('<CheatEntry><ID>1</ID><Description>Example action</Description><AssemblerScript>[ENABLE]\n[fallbackPtr]+38:\ndb 03\n[DISABLE]</AssemblerScript></CheatEntry>')
        result=parse(xml,'unused.exe')
        self.assertEqual(result['actions']['ct:1'],[dict(root='fallbackPtr',offset=0x38,data='03')])

    def test_unsupported_script_is_not_an_executable_patch(self):
        xml=table('<CheatEntry><ID>1</ID><Description>Unsupported</Description><AssemblerScript>[ENABLE]\n{$lua}\nos.execute("never")\n[DISABLE]</AssemblerScript></CheatEntry>')
        result=parse(xml,'unused.exe')
        self.assertEqual(result['records'][0]['kind'],'unsupported')
        self.assertEqual(result['patches'],{});self.assertEqual(result['actions'],{})

    def test_entities_and_unsupported_value_addresses_are_rejected(self):
        with self.assertRaises(ValueError):parse(b'<!DOCTYPE x><CheatTable/>','unused.exe')
        xml=table('<CheatEntry><ID>1</ID><VariableType>4 Bytes</VariableType><Address>kernel32.dll+10</Address></CheatEntry>')
        result=parse(xml,'unused.exe');self.assertEqual(result['records'][0]['kind'],'unsupported')

    def test_imported_code_is_padded_to_a_whole_original_instruction(self):
        xml=table('<CheatEntry><ID>1</ID><Description>Example branch</Description><AssemblerScript>[ENABLE]\nShadowFlare.exe+1000:\njmp ShadowFlare.exe+1010\nnop\n[DISABLE]</AssemblerScript></CheatEntry>')
        original=bytes.fromhex('7f 26 8b 46 40')+b'\x90'*123
        with patch('ct_table.image_bytes',return_value=original):result=parse(xml,'unused.exe')
        row=result['patches']['ct:1'][0]
        self.assertEqual(row['before'],'7f268b4640');self.assertEqual(len(bytes.fromhex(row['after'])),5)
        self.assertEqual(row['after'],'eb0e909090')

    def test_assembler_relocates_local_allocation_at_actual_base(self):
        source='[ENABLE]\nalloc(buffer,32)\nbuffer:\nmov eax,1\njmp resume\nShadowFlare.exe+1000:\njmp buffer\nresume:\n[DISABLE]'
        for base in (0x2000000,0x3100000):
            writes,allocated=assemble(source,base)
            self.assertEqual(writes[0]['address'],0x401000)
            self.assertEqual(0x401005+struct.unpack_from('<i',writes[0]['after'],1)[0],base)
            self.assertEqual(base+10+struct.unpack_from('<i',allocated,6)[0],0x401005)

    def test_native_boundary_decoder_rejects_unknown_or_truncated_instructions(self):
        self.assertEqual(patch_span(bytes.fromhex('7f 26 8b 46 40'),3),5)
        with self.assertRaises(ValueError):patch_span(bytes.fromhex('d9 ee'),1)
        with self.assertRaises(ValueError):patch_span(bytes.fromhex('8b 86'),2)


if __name__=='__main__':unittest.main()
