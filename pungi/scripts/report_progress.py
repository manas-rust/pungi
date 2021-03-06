from __future__ import print_function

import argparse
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd")
    opts = parser.parse_args()

    data = json.load(sys.stdin)
    compose = data["location"]

    dest = os.environ["_PUNGI_ORCHESTRATOR_PROGRESS_MONITOR"]

    with open(dest, "a") as f:
        if opts.cmd == "phase-start":
            print("%s: phase %s started" % (compose, data["phase_name"]), file=f)
        elif opts.cmd == "phase-stop":
            print("%s: phase %s finished" % (compose, data["phase_name"]), file=f)
