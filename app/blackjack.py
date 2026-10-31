"""Force the player's opening King + Ace at the native blackjack deal point.

The original generator still rejects duplicate cards, applies face-down bits,
and updates its own hand counts. Scoring, dealer AI and script rewards remain
native. No polling writes to transient card pointers or global RNG changes.
"""
import hashlib
import struct
from live_drop import Code

ID = 'atlas-blackjack'
HOOK = 0x40361c
ORIGINAL = bytes.fromhex('8b5d0085db7507')
MANAGER = 0x48d7f0
WINDOW_FLAG = 0x48ce6c
ALLOCATION = 4096
RECORD = dict(id=ID, parent='2193', kind='toggle',
              label='Her elde Blackjack · K + A',
              description='Always Blackjack (King + Ace)', minimumTrainerVersion=2)
VERIFIED = (
    (0x403560, 0x40, '45fdff11364912b610dc846768ea3e2e800298bd1b404b0a1b82794c395e71af'),
    (0x4035a0, 0x130, '54ef77d34116df0d8ed240723b460bd3f8885525e8fe70270b0eba771f7d4bf9'),
    (0x4036d0, 0x147, 'e63fba678b8de1223c2639b0a83a3140da027b32bb562c69c6a8f6ac06553499'),
    (0x4343b0, 0x8c, '48c4942a06002c0d60514e1d34a75b28eeeba53db1201bf692e00eb114649557'),
)


def verify(game):
    for address, length, expected in VERIFIED:
        if hashlib.sha256(game.read(address, length)).hexdigest() != expected:
            raise RuntimeError(f'Blackjack kodu tanınmadı: {address:08x}. Yama uygulanmadı.')


def make_stub(base):
    c = Code(base)
    # The generator has repurposed argument 1 to the selected count pointer.
    # At this point ESP is unchanged from its original seven-instruction frame.
    c.emit('81 fd').u32(MANAGER).branch('0f 85', 'native')
    c.emit('39 6c 24 20').branch('0f 85', 'native')  # dealer count pointer differs
    c.emit('83 7d 00 01').branch('0f 87', 'native')  # only player cards 0 and 1
    # Optional joker draws produce suit 4 / rank 0. A forced K/A needs a real
    # suit; keep the native duplicate retry, which draws a fresh random suit.
    c.emit('83 ff 04').branch('0f 85', 'rank').emit('31 ff')
    c.mark('rank').emit('83 7d 00 00').branch('0f 85', 'ace')
    c.emit('ba').u32(13).branch('e9', 'native')
    c.mark('ace').emit('ba').u32(1)
    c.mark('native').emit('8b 5d 00 85 db').branch('0f 85', 0x40362a)
    c.branch('e9', 0x403623)
    raw = c.finish()
    assert len(raw) < ALLOCATION
    return raw


def detour(base):
    return b'\xe9' + struct.pack('<i', base-HOOK-5) + b'\x90'*(len(ORIGINAL)-5)


def snapshot(game):
    if game is None: return None
    try:
        values = struct.unpack('<42I', game.read(MANAGER, 0xa8))
        player_count, dealer_count = values[0], values[17]
        if player_count > 16 or dealer_count > 16: return None
        def card(value):
            rank = value & 0xffff
            return dict(rank=rank, label={0:'Joker',1:'A',11:'J',12:'Q',13:'K'}.get(rank,str(rank)),
                        suit=(value>>16)&15, faceDown=bool(value&0x80000000))
        return dict(windowOpen=game.words(WINDOW_FLAG)[0]==1,
                    playerCards=[card(v) for v in values[1:1+player_count]],
                    dealerCount=dealer_count, result=values[37])
    except (OSError, ValueError, struct.error):
        return None
