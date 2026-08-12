#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run all three regression legs and say, in one line, whether anything moved.

    cd cad2bim/tests
    python3 run_regressions.py                 # check against the baselines
    python3 run_regressions.py --bless         # re-record them

This is the command to run before shipping a release. The unit suite
(`python3 -m unittest discover -s . -p "test_*.py"`) stays under a second and is
the inner loop; these three take about three minutes between them and are the
gate. Keeping them apart is deliberate -- a gate nobody runs because it makes
the inner loop slow is a gate that does not exist, which is how the last set
ended up in a scratchpad and got lost.

Exit code 0 when every leg matches its baseline, 1 when anything moved or a leg
could not run.
"""

import os
import sys
import time
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

LEGS = (
    ("slab fingerprints  (29 archived exports)", "regression_slab_fingerprints"),
    ("DXF sweep          (17 fixture drawings)", "regression_dxf_sweep"),
    ("storey replay      (4 storey stacks)", "regression_storeys"),
)


def main(argv):
    if "--bless" in argv:
        os.environ["CAD2BIM_BLESS"] = "1"
        print("RE-RECORDING baselines (CAD2BIM_BLESS=1)\n")

    loader = unittest.TestLoader()
    failed = []
    written = []
    for title, module in LEGS:
        started = time.time()
        suite = loader.loadTestsFromName(module)
        with open(os.devnull, "w") as quiet:
            result = unittest.TextTestRunner(verbosity=0, stream=quiet).run(suite)
        elapsed = time.time() - started
        if result.wasSuccessful() and not result.skipped:
            print("  ok       {0}   {1:.0f}s".format(title, elapsed))
        elif result.wasSuccessful():
            written.append(title)
            print("  written  {0}   {1:.0f}s".format(title, elapsed))
            for _test, reason in result.skipped:
                print("           {0}".format(reason))
        else:
            failed.append(title)
            print("  MOVED    {0}   {1:.0f}s".format(title, elapsed))
            for _test, trace in result.failures + result.errors:
                print("           " + trace.strip().splitlines()[-1][:200])

    print()
    if failed:
        print("{0} of {1} legs moved. Read the diff above, decide whether the "
              "change was intended, then --bless if it was."
              .format(len(failed), len(LEGS)))
        return 1
    if written:
        # A leg that WROTE its baseline checked nothing. Saying "all legs match"
        # here would be the exact failure this harness exists to prevent: a
        # green line that means "not measured".
        print("{0} of {1} legs wrote a baseline and checked nothing. Run again "
              "with no flags to check against them."
              .format(len(written), len(LEGS)))
        return 0
    print("all {0} legs match their baselines.".format(len(LEGS)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
