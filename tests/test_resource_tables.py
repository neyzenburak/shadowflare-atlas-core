"""Native table reads work without a game-language patch module."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from resource_tables import lz_decode,tbd_data,table_records


class ResourceTableTests(unittest.TestCase):
    def payload(self):
        numeric=struct.pack('<5i',41,1,2,123,-456)
        cells=[b'alpha',b'beta']
        return struct.pack('<i',1)+numeric+b''.join(
            struct.pack('<i',len(cell))+bytes(x^255 for x in cell) for cell in cells)

    def test_uncompressed_table_retains_numeric_data_and_cells(self):
        payload=self.payload()
        data=b'TABLE DATA V000\x1a'+struct.pack('<ii',0,len(payload))+payload
        self.assertEqual(tbd_data(data),payload)
        table,=table_records(tbd_data(data))
        self.assertEqual((table['number'],table['rows'],table['cols']),(41,1,2))
        self.assertEqual(table['cells'],[b'alpha',b'beta'])
        self.assertEqual(table['numeric'],struct.pack('<5i',41,1,2,123,-456))

    def test_compressed_table_literal_stream(self):
        payload=self.payload()
        packed=b''.join(b'\0'+payload[i:i+8] for i in range(0,len(payload),8))
        stream=b'RCLIB-L\x1a'+struct.pack('<II',len(payload),len(packed))+packed
        self.assertEqual(lz_decode(stream),payload)
        data=b'TABLE DATA V000\x1a'+struct.pack('<i',1)+stream
        self.assertEqual(tbd_data(data),payload)

    def test_rejects_invalid_headers_sizes_and_trailing_data(self):
        for data in (b'invalid',b'TABLE DATA V000\x1a'+struct.pack('<i',2),
                     b'TABLE DATA V000\x1a'+struct.pack('<ii',0,20)+b'short'):
            with self.assertRaises(ValueError):tbd_data(data)
        with self.assertRaises(ValueError):table_records(self.payload()+b'x')


if __name__=='__main__':unittest.main()
