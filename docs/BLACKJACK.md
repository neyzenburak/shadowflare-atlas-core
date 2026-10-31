# Blackjack every hand: K + A

Toggle **Control Desk > Trainer > Atlas > Blackjack every hand**. You can also
search the trainer for `blackjack`. After enabling it, **start a new hand**:
the player's first two cards are **King, then Ace**. Disabling restores normal
dealing.

The blackjack conversations on tower floors 17 and 22 use the same dealer,
so the option works in both. Betting, continuing, winning streaks and item or
storage rewards follow the game's normal flow. Two natural blackjacks still
produce a draw. Cards already dealt in an existing hand are not changed.

## Implementation

- `blackjack.py` places a temporary detour over the seven-byte instruction
  boundary at `40361C`. No game EXE or scenario file is modified.
- Only the first two draws in the **player's** hand of blackjack object
  `48D7F0` are changed. The dealer, later draws and other objects use the
  original path.
- The candidate card's suit is kept. The original duplicate-card check can
  draw another suit if necessary. Joker candidates become valid K/A cards.
- Face-down flags, card counts, Ace's 1/11 scoring and result comparison remain
  in the original code. The general random number generator is not patched.
- SHA-256 values for dealing, reset, score/result and script entry points are
  checked before activation. Unrecognized code is not overwritten.
- The existing trainer backup, operation lock, patching and restoration paths
  are used. Resetting the trainer or normally closing the companion restores
  the original code.

This Atlas-authored entry is separate in `trainer-extras.js`; imported Cheat
Engine records are not modified. Core requires Trainer API version 3 or newer
for this control.

## Verification

`tests/test_blackjack.py` runs the original EXE's actual x86 dealing, scoring
and result functions in Unicorn. It checks 128 initial hands, card uniqueness,
redrawing a conflicting suit, Jokers, face-down flags, later draws, other
objects, draws, disabling and trainer reset.

`tests/test_trainer_blackjack.cjs` checks visibility, search, compatibility with
older companions and toggle requests in a DOM environment; it requires `jsdom`.
New hands with K + A were also verified in a running game.

```powershell
python -m unittest discover -s tests -p test_blackjack.py -v
node tests/test_trainer_blackjack.cjs
```
