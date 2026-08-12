# cad2bim tests

Two tiers, on purpose.

## Inner loop — the unit suite

```
cd AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/tests
python3 -m unittest discover -s . -p "test_*.py"
```

452 tests, about a second. Run it on every edit. It proves the pieces: geometry
primitives, label parsing, naming templates, the dialog wiring, type-name
matching. It cannot prove that a change to a geometry pass left the rest of the
corpus alone — nothing that runs in a second can.

## Release gate — the three regression legs

```
python3 run_regressions.py            # check against the stored baselines
python3 run_regressions.py --bless    # re-record them, deliberately
```

About three minutes. Run before shipping.

| Leg | Corpus | What only it can see |
|-----|--------|----------------------|
| `regression_slab_fingerprints` | 29 archived Revit exports, newest per drawing | Real Revit-link geometry. Five drawings (test14, test15, test18, test19, test20) have no surviving DXF — this is the only thing still watching them. |
| `regression_dxf_sweep` | the 17 fixture DXFs | The full slab chain including note recovery and labels. An export drops the raw text, so only a DXF can drive `apply_slab_labels` / `loops_for_unclaimed_notes`. |
| `regression_storeys` | 4 multi-storey exports (test9 ×11, test10 ×10, test12 ×5, test13 ×5) | Per-storey numbers. test10's roof carries no A-FLOR layer at all; a single-storey fingerprint cannot see a roof that built nothing while every floor below looked perfect. |

Each leg writes its baseline on first run and checks against it afterwards.
Baselines live in `baselines/*.json`, sorted and indented so a pull request diff
shows the one number that moved.

**A moved number is not automatically a bug.** The legs say *what* changed, never
whether it was allowed. Read the diff, decide, then `--bless` if it was intended
— and say so in the commit.

### Why they are `regression_*.py` and not `test_*.py`

So `discover -p "test_*.py"` stays under a second. A gate that makes the inner
loop slow is a gate people stop running, which is how the previous set of
harnesses came to live in an uncommitted scratchpad and get lost with it.

### Provenance of the baselines

The numbers were measured at **v0.68.1**, the release confirmed against Revit.
They are *not* the lost v0.67.3 baselines — `scratchpad/slabbase.py`,
`base_after.json`, `sweep67.py`, `t10_full.py` and `t10_cols.py` were never
committed and cannot be reproduced. What these defend is drift from v0.68.1 on.

One independent check that the sweep reproduces the real pipeline: `findings.md`
recorded "test10 +6 noted bays" at the old v0.67.3 baseline, and
`regression_dxf_sweep` measures `slab_loops_recovered_from_notes = 6` on test10.

## Environment

`pip install ezdxf` is required for the DXF leg and for `test_beam_stress`. The
bundled `lib/py3` copy is a Windows build — importing its `numpy` calls
`os.add_dll_directory`, which does not exist on Linux, so the bundled `ezdxf`
will not load. The DXF leg skips with that message rather than failing when
`ezdxf` is missing.

## Non-test harnesses

`replay_beams.py` and `demo_slabs.py` are diagnostic scripts, not gates: point
them at one export to inspect a single drawing by hand.
