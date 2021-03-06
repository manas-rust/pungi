# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import print_function

import argparse
import json
import os
import shutil
import sys

from six.moves import configparser

import kobo.conf
import pungi.checks
import pungi.util

from pungi_utils import config_utils


def load_file(source, conf):
    try:
        with open(source) as f:
            conf.load_from_dict(json.load(f))
    except ValueError:
        conf.load_from_file(source)


def load_source(source, conf):
    if os.path.isfile(source):
        load_file(source, conf)
    elif os.path.isdir(source):
        load_file(os.path.join(source, "logs/global/config-dump.global.log"), conf)
    else:
        raise RuntimeError("Source %s is neither file nor directory." % source)


def dump_multi_config(conf_file, dest, **kwargs):
    """Given a multi compose config, clone it and all referenced files to a
    given directory.
    """
    parser = configparser.RawConfigParser()
    parser.read(conf_file)

    pungi.util.makedirs(dest)
    basedir = os.path.dirname(conf_file)

    def copy_local_files(config):
        """Helper function called on all loaded Pungi configs that copies local
        variants or comps files (unless specified by absolute path).
        """
        for opt in "comps_file", "variants_file":
            val = config.get(opt)
            if isinstance(val, str) and val[0] != "/":
                shutil.copy2(os.path.join(basedir, val), dest)

    for section in parser.sections():
        if section == "general":
            continue
        file_path = parser.get(section, "config")
        dest_file = os.path.splitext(os.path.join(dest, file_path))[0] + ".json"
        with open(dest_file, "w") as fh:
            if not process_file(
                [os.path.join(basedir, file_path)],
                out=fh,
                callback=copy_local_files,
                **kwargs
            ):
                return False
        parser.set(section, "config", os.path.basename(dest_file))

    with open(os.path.join(dest, os.path.basename(conf_file)), "w") as fh:
        parser.write(fh)

    return True


def process_file(
    sources,
    out=sys.stdout,
    callback=None,
    defines=None,
    just_dump=False,
    event=None,
    offline=False,
):
    """Load Pungi config file, validate it, optionally resolve Git references,
    and dump created JSON to a given stream.

    :param callable callback: a callable to call with parsed config
    :param dict defines: mapping of values to define before parsing the config
    :param bool just_dump: skip validation and adding default values
    :param int event: Koji event to hardcode into the config
    :param bool offline: skip resolving Git references
    :returns: False if validation failed, True otherwise
    """
    conf = kobo.conf.PyConfigParser()

    # Make sure variables are ready before processing config template
    conf.load_from_dict(defines or {})

    for source in sources:
        load_source(source, conf)

    # Load again to overwrite exsting config with the value provided in command line
    conf.load_from_dict(defines or {})

    if not just_dump:
        errors, _ = pungi.checks.validate(conf, offline=offline)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return False

    if event:
        conf["koji_event"] = event

    # Clean up defines from the final final config. We don't want to keep them
    # as they would cause warnings during validation.
    config_utils.remove_unknown(conf, defines)

    if callback:
        callback(conf)

    json.dump(conf, out, sort_keys=True, indent=4)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "sources",
        metavar="SOURCE",
        nargs="+",
        help=(
            "Source for the configuration; either a compose "
            "or arbitrary number of config files."
        ),
    )
    parser.add_argument(
        "--freeze-event",
        metavar="ID",
        type=pungi.util.parse_koji_event,
        help=(
            "Include this koji event in the created config; "
            "takes either event ID or path to a compose"
        ),
    )
    parser.add_argument(
        "-e",
        "--define",
        action="append",
        default=[],
        metavar="VAR=VALUE",
        type=config_utils.validate_definition,
        help=(
            "Define missing or overwrite existing config item in the config file, "
            "or assign value to template variable. "
            "Can be used multiple times."
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--just-dump",
        action="store_true",
        help=(
            "Do not transform the config in any way. Default values are not "
            "added, git references are not resolved."
        ),
    )
    group.add_argument(
        "--offline", action="store_true", help="Do not resolve git references."
    )
    parser.add_argument(
        "--multi",
        metavar="DIR",
        help=(
            "Treat source as config for pungi-orchestrate and store dump into "
            "given directory."
        ),
    )

    args = parser.parse_args()

    defines = config_utils.extract_defines(args.define)

    if args.multi:
        if len(args.sources) > 1:
            parser.error("Only one multi config can be specified.")

        return dump_multi_config(
            args.sources[0],
            dest=args.multi,
            defines=defines,
            just_dump=args.just_dump,
            event=args.freeze_event,
            offline=args.offline,
        )

    return process_file(
        args.sources,
        defines=defines,
        just_dump=args.just_dump,
        event=args.freeze_event,
        offline=args.offline,
    )


def cli_main():
    try:
        if not main():
            sys.exit(1)
    except RuntimeError as exc:
        print("Error", str(exc), file=sys.stderr)
        sys.exit(2)
