# -*- coding: utf-8 -*-

"""
Messaging hook to block compose progress until an ostree commit is signed.

The signing is implemented by robosignatory, which listens on the message bus
and reacts to messages about new commits. It will create a signature and then
update the ref in the repo to point to the new commit.

This script should not be used if Pungi is updating the reference on its own
(since that does not leave time for the signature).
"""

from __future__ import print_function

import argparse
import datetime
import fedmsg.config
import json
import os
import sys
import time


def is_ref_updated(ref_file, commit):
    """The ref is updated when the file points to the correct commit."""
    try:
        with open(ref_file) as f:
            return f.read().strip() == commit
    except IOError:
        # Failed to open the file, probably it does not exist, so let's just
        # wait more.
        return False


def ts_log(msg):
    print("%s: %s" % (datetime.datetime.utcnow(), msg))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd")
    opts = parser.parse_args()

    if opts.cmd != "ostree":
        # Not an announcement of new ostree commit, nothing to do.
        sys.exit()

    try:
        data = json.load(sys.stdin)
    except ValueError:
        print("Failed to decode data", file=sys.stderr)
        sys.exit(1)

    repo = data["local_repo_path"]
    commit = data["commitid"]
    if not commit:
        print("No new commit was created, nothing will get signed.")
        sys.exit(0)

    path = "%s/objects/%s/%s.commitmeta" % (repo, commit[:2], commit[2:])

    config = fedmsg.config.load_config()
    config["active"] = True  # Connect out to a fedmsg-relay instance
    config["cert_prefix"] = "releng"  # Use this cert.
    fedmsg.init(**config)
    topic = "compose.%s" % opts.cmd.replace("-", ".").lower()

    count = 0
    while not os.path.exists(path):
        ts_log("Commit not signed yet, waiting...")
        count += 1
        if count >= 60:  # Repeat every 5 minutes
            print("Repeating notification")
            fedmsg.publish(topic=topic, modname="pungi", msg=data)
            count = 0
        time.sleep(5)

    print("Found signature, waiting for ref to be updated.")

    ref_file = os.path.join(repo, "refs/heads", data["ref"])
    while not is_ref_updated(ref_file, commit):
        ts_log("Ref is not yet up-to-date, waiting...")
        time.sleep(5)

    print("Ref is up-to-date. All done!")
