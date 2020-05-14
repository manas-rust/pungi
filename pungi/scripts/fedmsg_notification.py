# -*- coding: utf-8 -*-

import argparse
import fedmsg
import fedmsg.config
import json
import sys


def send(cmd, data):
    topic = "compose.%s" % cmd.replace("-", ".").lower()
    fedmsg.publish(topic=topic, modname="pungi", msg=data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd")
    opts = parser.parse_args()

    config = fedmsg.config.load_config()
    config["active"] = True  # Connect out to a fedmsg-relay instance
    config["cert_prefix"] = "releng"  # Use this cert.
    fedmsg.init(**config)

    data = json.load(sys.stdin)
    send(opts.cmd, data)