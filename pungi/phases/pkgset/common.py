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


import os

from kobo.shortcuts import run, relative_path

import pungi.phases.pkgset.pkgsets
from pungi.arch import get_valid_arches
from pungi.wrappers.createrepo import CreaterepoWrapper
from pungi.util import is_arch_multilib, find_old_compose


# TODO: per arch?
def populate_arch_pkgsets(compose, path_prefix, global_pkgset):
    result = {}
    for arch in compose.get_arches():
        compose.log_info("Populating package set for arch: %s" % arch)
        is_multilib = is_arch_multilib(compose.conf, arch)
        arches = get_valid_arches(arch, is_multilib, add_src=True)
        pkgset = pungi.phases.pkgset.pkgsets.PackageSetBase(compose.conf["sigkeys"], logger=compose._logger, arches=arches)
        pkgset.merge(global_pkgset, arch, arches)
        pkgset.save_file_list(compose.paths.work.package_list(arch=arch), remove_path_prefix=path_prefix)
        result[arch] = pkgset
    return result


def create_global_repo(compose, path_prefix):
    createrepo_c = compose.conf["createrepo_c"]
    createrepo_checksum = compose.conf["createrepo_checksum"]
    repo = CreaterepoWrapper(createrepo_c=createrepo_c)
    repo_dir_global = compose.paths.work.arch_repo(arch="global")
    msg = "Running createrepo for the global package set"

    if compose.DEBUG and os.path.isdir(os.path.join(repo_dir_global, "repodata")):
        compose.log_warning("[SKIP ] %s" % msg)
        return

    compose.log_info("[BEGIN] %s" % msg)

    # find an old compose suitable for repodata reuse
    old_compose_path = None
    update_md_path = None
    if compose.old_composes:
        old_compose_path = find_old_compose(compose.old_composes, compose.conf["release_short"], compose.conf["release_version"], compose.conf.get("base_product_short"), compose.conf.get("base_product_version"))
        if old_compose_path is None:
            compose.log_info("No suitable old compose found in: %s" % compose.old_composes)
        else:
            repo_dir = compose.paths.work.arch_repo(arch="global")
            rel_path = relative_path(repo_dir, os.path.abspath(compose.topdir).rstrip("/") + "/")
            old_repo_dir = os.path.join(old_compose_path, rel_path)
            if os.path.isdir(old_repo_dir):
                compose.log_info("Using old repodata from: %s" % old_repo_dir)
                update_md_path = old_repo_dir

    # IMPORTANT: must not use --skip-stat here -- to make sure that correctly signed files are pulled in
    cmd = repo.get_createrepo_cmd(path_prefix, update=True, database=True, skip_stat=False, pkglist=compose.paths.work.package_list(arch="global"), outputdir=repo_dir_global, baseurl="file://%s" % path_prefix, workers=5, update_md_path=update_md_path, checksum=createrepo_checksum)
    run(cmd, logfile=compose.paths.log.log_file("global", "arch_repo"), show_cmd=True)
    compose.log_info("[DONE ] %s" % msg)


def create_arch_repos(compose, arch, path_prefix):
    createrepo_c = compose.conf["createrepo_c"]
    createrepo_checksum = compose.conf["createrepo_checksum"]
    repo = CreaterepoWrapper(createrepo_c=createrepo_c)
    repo_dir_global = compose.paths.work.arch_repo(arch="global")
    repo_dir = compose.paths.work.arch_repo(arch=arch)
    msg = "Running createrepo for arch '%s'" % arch

    if compose.DEBUG and os.path.isdir(os.path.join(repo_dir, "repodata")):
        compose.log_warning("[SKIP ] %s" % msg)
        return

    compose.log_info("[BEGIN] %s" % msg)
    comps_path = None
    if compose.has_comps:
        comps_path = compose.paths.work.comps(arch=arch)
    cmd = repo.get_createrepo_cmd(path_prefix, update=True, database=True, skip_stat=True, pkglist=compose.paths.work.package_list(arch=arch), outputdir=repo_dir, baseurl="file://%s" % path_prefix, workers=5, groupfile=comps_path, update_md_path=repo_dir_global, checksum=createrepo_checksum)
    run(cmd, logfile=compose.paths.log.log_file(arch, "arch_repo"), show_cmd=True)
    compose.log_info("[DONE ] %s" % msg)
