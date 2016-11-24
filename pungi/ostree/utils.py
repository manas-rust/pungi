# -*- coding: utf-8 -*-


# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <https://gnu.org/licenses/>.


import datetime
import json
import os

from pungi.util import makedirs


def make_log_file(log_dir, filename):
    """Return path to log file with given name, if log_dir is set."""
    if not log_dir:
        return None
    makedirs(log_dir)
    return os.path.join(log_dir, '%s.log' % filename)


def get_ref_from_treefile(treefile):
    """Return ref name by parsing the tree config file"""
    ref = None
    if os.path.isfile(treefile):
        with open(treefile, 'r') as f:
            try:
                parsed = json.loads(f.read())
                ref = parsed['ref']
            except Exception:
                pass
    return ref


def get_commitid_from_commitid_file(commitid_file):
    """Return commit id which is read from the commitid file"""
    commitid = None
    if os.path.isfile(commitid_file):
        with open(commitid_file, 'r') as f:
            commitid = f.read().replace('\n', '')
    return commitid


def tweak_treeconf(treeconf, source_repos=None, keep_original_sources=False):
    """
    Update tree config file by adding new repos, and remove existing repos
    from the tree config file if 'keep_original_sources' is not enabled.
    """
    # add this timestamp to repo name to get unique repo filename and repo name
    # should be safe enough
    time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

    treeconf_dir = os.path.dirname(treeconf)
    with open(treeconf, 'r') as f:
        treeconf_content = json.load(f)

    # backup the old tree config
    os.rename(treeconf, '%s.%s.bak' % (treeconf, time))

    repos = []
    if source_repos:
        for repo in source_repos:
            name = "%s-%s" % (repo['name'], time)
            with open("%s/%s.repo" % (treeconf_dir, name), 'w') as f:
                f.write("[%s]\n" % name)
                f.write("name=%s\n" % name)
                f.write("baseurl=%s\n" % repo['baseurl'])
                exclude = repo.get('exclude', None)
                if exclude:
                    f.write("exclude=%s\n" % exclude)
                gpgcheck = '1' if repo.get('gpgcheck', False) else '0'
                f.write("gpgcheck=%s\n" % gpgcheck)
            repos.append(name)

    original_repos = treeconf_content.get('repos', [])
    if keep_original_sources:
        treeconf_content['repos'] = original_repos + repos
    else:
        treeconf_content['repos'] = repos

    # update tree config to add new repos
    with open(treeconf, 'w') as f:
        json.dump(treeconf_content, f, indent=4)