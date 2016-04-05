# -*- coding: utf-8 -*-

"""
This module contains functions required by pungi-make-ostree.
It is expected to be runnable in Koji runroot.
"""

import argparse
import os
from kobo import shortcuts
import re
import errno

from .wrappers import scm


def ensure_dir(path):
    try:
        os.makedirs(path)
    except OSError as err:
        if err.errno != errno.EEXIST:
            raise
    return path


def make_log_file(log_dir, filename):
    """Return path to log file with given name, if log_dir is set."""
    if not log_dir:
        return None
    ensure_dir(log_dir)
    return os.path.join(log_dir, '{}.log'.format(filename))


def init_ostree_repo(repo, log_dir=None):
    """If the ostree repo does not exist, initialize it."""
    log_file = make_log_file(log_dir, 'init-ostree-repo')
    if not os.path.isdir(repo):
        ensure_dir(repo)
        shortcuts.run(['ostree', 'init', '--repo={}'.format(repo), '--mode=archive-z2'],
                      show_cmd=True, logfile=log_file)


def make_ostree_repo(repo, config, log_dir=None):
    log_file = make_log_file(log_dir, 'create-ostree-repo')
    shortcuts.run(['rpm-ostree', 'compose', 'tree', '--repo={}'.format(repo), config],
                  show_cmd=True, logfile=log_file)


def clone_repo(repodir, url, branch):
    scm.get_dir_from_scm(
        {'scm': 'git', 'repo': url, 'branch': branch, 'dir': '.'}, repodir)


def tweak_mirrorlist(repodir, source_repo):
    for file in os.listdir(repodir):
        if file.endswith('.repo'):
            tweak_file(os.path.join(repodir, file), source_repo)


def tweak_file(path, source_repo):
    """Replace mirrorlist line in repo file with baseurl pointing to source_repo."""
    with open(path, 'r') as f:
        contents = f.read()
    replacement = 'baseurl={}'.format(source_repo)
    contents = re.sub(r'^mirrorlist=.*$', replacement, contents, flags=re.MULTILINE)
    with open(path, 'w') as f:
        f.write(contents)


def prepare_config(workdir, config_url, config_branch, source_repo):
    repodir = os.path.join(workdir, 'config_repo')
    clone_repo(repodir, config_url, config_branch)
    tweak_mirrorlist(repodir, source_repo)
    return repodir


def run(opts):
    workdir = ensure_dir(opts.work_dir)
    repodir = prepare_config(workdir, opts.config_url, opts.config_branch,
                             opts.source_repo)
    ensure_dir(repodir)
    init_ostree_repo(opts.ostree_repo, log_dir=opts.log_dir)
    treefile = os.path.join(repodir, opts.treefile)
    make_ostree_repo(opts.ostree_repo, treefile, log_dir=opts.log_dir)


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--log-dir',
                        help='where to log output')
    parser.add_argument('--work-dir', required=True,
                        help='where to put temporary files')

    parser.add_argument('ostree_repo', metavar='OSTREE_REPO',
                        help='where to put the ostree repo')
    parser.add_argument('--treefile', required=True,
                        help='treefile for rpm-ostree')
    parser.add_argument('--config-url', required=True,
                        help='git repository with the treefile')
    parser.add_argument('--config-branch', default='master',
                        help='git branch to be used')
    parser.add_argument('--source-repo', required=True,
                        help='yum repo used as source for')

    opts = parser.parse_args(args)

    run(opts)
