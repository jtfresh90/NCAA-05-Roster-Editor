# NCAA 05 GameCube — Model Swap Verification Test

**Goal:** Answer "does a swapped model actually render correctly in-game?" with a
5-minute Dolphin experiment. This is the one test the swap machinery needs before
model swapping can be called working end-to-end.

## Background (verified headless, Oct 7 2026)

- `PLADATA.DAT` (147MB, 2,672 TERF entries) is the player/equipment model archive.
- Whole-entry blob swapping (trey31's Madden 08 PC method, adapted for GameCube)
  produces a byte-valid TERF — swapping entries 2117↔2118 round-trips byte-identical.
- The ISO rebuild chain (TERF rebuild → append DAT → FST update) is the same chain
  the texture editor already uses.
- Size clustering suggests: 931 entries at 100–200KB (player bodies), 885 at 1–5KB
  (pads/accessories), and a tight group of 16 entries at exactly 1607 bytes
  (indices 2117–2134 — candidates for helmets or small equipment pieces).

**Not yet proven:** that entry 2117 is a helmet, or that swapped geometry renders
correctly (or doesn't crash the game). Dolphin is the only available oracle —
this environment cannot run it (no GPU libraries).

## The 5-minute test

### 1. Build a swapped ISO

On the repo (needs the ISO + `model_swap.py`, `texture_parser.py`):

```bash
# From the ncaa05-github directory:
# Step A: swap two candidate helmet slots in PLADATA.DAT
python3 model_swap.py /path/to/PLADATA.DAT --swap 2117 2118 -o PLADATA_SWAPPED.DAT

# Step B: rebuild a patched ISO with the swapped DAT.
# Use the same ISO-rebuild path as the PWA texture editor:
# load ISO -> slice PLADATA.DAT via FST offset -> replace with PLADATA_SWAPPED.DAT
# -> append to ISO end -> update FST entry. The PWA (mobile/texture.html) does
# this in-browser; model_swap support for PLADATA is in the Model Swap page.
```

Simplest path: open the PWA model-swap page
(https://jtfresh90.github.io/NCAA-05-Roster-Editor/mobile/), load the ISO,
select PLADATA.DAT, pick entries 2117 and 2118, swap, download the patched ISO.

### 2. Boot it in Dolphin

1. Dolphin → open the patched ISO.
2. Start a quick game (any two teams) and look at the helmets during the
   opening camera pan / kickoff.
3. Also check the pre-game team-select screen if helmets are visible there.

### 3. Read the result

| What you see | Verdict |
|---|---|
| Two teams' helmets visibly swapped (or mismatched vs. stock) | ✅ Swap works end-to-end. Entry 2117–2134 are swappable model slots. |
| Helmets look normal everywhere | ⚠️ Entries 2117/2118 aren't helmet slots (or are unused). Try the 1–5KB group (pads) next — a swapped shoulder pad is visible in close-ups. |
| Game freezes/crashes on load or at kickoff | ❌ The engine validates or couples these entries. Report which screen it died on — that tells us where the check lives. |
| Players' bodies look wrong/distorted | ⚠️ Slot coupling: entries may need to swap in pairs (e.g., model + its texture). Next step: swap a whole size-cluster group together. |

### 4. Report back

The useful facts for the next step: which entries you swapped, which screen you
were on, and what changed visually (or where it crashed). A 10-second screen
recording beats a paragraph.

## If the test passes

The fast next wins, in payoff order:

1. **Swap helmets for real** — swap a team's full helmet group with another
   school's (all 16 of the 2117–2134 group), full-team visual overhaul.
2. **Pad/accessory swaps** — the 885 entries at 1–5KB are quick wins.
3. **Stadium models** — STADIUMS.DAT (287MB) via the same blob-swap machinery.
4. **Animation swaps** — ANIMDATA.DAT (1,151 entries): same method, unproven in
   practice; treat as experimental.

## If the test fails

- Crash on load → likely a checksum/hash the rebuild doesn't update. Next: diff
  a Dolphin save/load cycle of the stock ISO to find integrity fields.
- Nothing visible → the size cluster is the wrong group. Next: swap two entries
  from the 100–200KB body group (e.g., indices from `--list --min 100000`) and
  watch the players' bodies.
