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
from six.moves import cPickle as pickle
import json
import re
from itertools import groupby
import threading

from kobo.shortcuts import force_list, relative_path

import pungi.wrappers.kojiwrapper
from pungi.wrappers.comps import CompsWrapper
import pungi.phases.pkgset.pkgsets
from pungi.arch import get_valid_arches, getBaseArch
from pungi.util import is_arch_multilib, retry, find_old_compose
from pungi import Modulemd

from pungi.phases.pkgset.common import (create_arch_repos,
                                        populate_arch_pkgsets,
                                        get_create_global_repo_cmd,
                                        run_create_global_repo)
from pungi.phases.gather import get_packages_to_gather

import pungi.phases.pkgset.source


def variant_dict_from_str(compose, module_str):
    """
    Method which parses module NVR string, defined in a variants file and returns
    a module info dictionary instead.

    For more information about format of module_str, read:
    https://pagure.io/modularity/blob/master/f/source/development/
    building-modules/naming-policy.rst

    Pungi supports N:S, N:S:V and N:S:V:C.

    Attributes:
        compose: compose for which the variant_dict is generated
        module_str: string, the NV(R) of module defined in a variants file.
    """

    # The new format can be distinguished by colon in module_str, because
    # there is not module in Fedora with colon in a name or stream and it is
    # now disallowed to create one. So if colon is there, it must be new
    # naming policy format.
    if module_str.find(":") != -1:
        module_info = {}

        nsv = module_str.split(":")
        if len(nsv) > 4:
            raise ValueError(
                "Module string \"%s\" is not recognized. "
                "Only NAME:STREAM[:VERSION[:CONTEXT]] is allowed.")
        if len(nsv) > 3:
            module_info["context"] = nsv[3]
        if len(nsv) > 2:
            module_info["version"] = nsv[2]
        if len(nsv) > 1:
            module_info["stream"] = nsv[1]
        module_info["name"] = nsv[0]
        return module_info
    else:
        # Fallback to previous old format with '-' delimiter.
        compose.log_warning(
            "Variant file uses old format of module definition with '-'"
            "delimiter, please switch to official format defined by "
            "Modules Naming Policy.")

        module_info = {}
        # The regex is matching a string which should represent the release number
        # of a module. The release number is in format: "%Y%m%d%H%M%S"
        release_regex = re.compile("^(\d){14}$")

        section_start = module_str.rfind('-')
        module_str_first_part = module_str[section_start+1:]
        if release_regex.match(module_str_first_part):
            module_info['version'] = module_str_first_part
            module_str = module_str[:section_start]
            section_start = module_str.rfind('-')
            module_info['stream'] = module_str[section_start+1:]
        else:
            module_info['stream'] = module_str_first_part
        module_info['name'] = module_str[:section_start]

        return module_info


@retry(wait_on=IOError)
def get_koji_modules(compose, koji_wrapper, event, module_info_str):
    """
    :param koji_wrapper: koji wrapper instance
    :param event: event at which to perform the query
    :param module_info_str: str, mmd or module dict

    :return final list of module_info which pass repoclosure
    """
    koji_proxy = koji_wrapper.koji_proxy

    module_info = variant_dict_from_str(compose, module_info_str)

    # We need to format the query string to koji reguirements. The
    # transformation to NVR for use in Koji has to match what MBS is doing when
    # importing the build.
    query_str = "%s-%s-%s.%s" % (
        module_info["name"],
        module_info["stream"].replace("-", "_"),
        module_info.get("version", "*"),
        module_info.get("context", "*"),
    )
    query_str = query_str.replace('*.*', '*')

    koji_builds = koji_proxy.search(query_str, "build", "glob")

    modules = []
    for build in koji_builds:
        md = koji_proxy.getBuild(build["id"])

        if md["completion_ts"] > event["ts"]:
            # The build finished after the event at which we are limited to,
            # ignore it.
            compose.log_debug(
                "Module build %s is too new, ignoring it." % build["name"]
            )
            continue

        if not md["extra"]:
            continue

        try:
            md["modulemd"] = md["extra"]["typeinfo"]["module"]["modulemd_str"]
            md["tag"] = md["extra"]["typeinfo"]["module"]["content_koji_tag"]
            # Get the NSVC from module metadata, because the original Koji build
            # has '-' replaced with "_".
            md["name"] = md["extra"]["typeinfo"]["module"]["name"]
            md["stream"] = md["extra"]["typeinfo"]["module"]["stream"]
            md["version"] = md["extra"]["typeinfo"]["module"]["version"]
            md["context"] = md["extra"]["typeinfo"]["module"]["context"]
        except KeyError:
            continue

        modules.append(md)

    if not modules:
        raise ValueError(
            "No module build found for %r (queried for %r)"
            % (module_info_str, query_str)
        )

    # If there is version provided, then all modules with that version will go
    # in. In case version is missing, we will find the latest version and
    # include all modules with that version.
    if not module_info.get('version'):
        # select all found modules with latest version
        sorted_modules = sorted(modules, key=lambda item: int(item['version']), reverse=True)
        latest_version = int(sorted_modules[0]['version'])
        modules = [module for module in modules if latest_version == int(module['version'])]

    return modules


class PkgsetSourceKoji(pungi.phases.pkgset.source.PkgsetSourceBase):
    enabled = True

    def __call__(self):
        compose = self.compose
        koji_profile = compose.conf["koji_profile"]
        self.koji_wrapper = pungi.wrappers.kojiwrapper.KojiWrapper(koji_profile)
        # path prefix must contain trailing '/'
        path_prefix = self.koji_wrapper.koji_module.config.topdir.rstrip("/") + "/"
        package_sets = get_pkgset_from_koji(self.compose, self.koji_wrapper, path_prefix)
        return (package_sets, path_prefix)


def get_pkgset_from_koji(compose, koji_wrapper, path_prefix):
    event_info = get_koji_event_info(compose, koji_wrapper)
    pkgset_global = populate_global_pkgset(compose, koji_wrapper, path_prefix, event_info)

    cmd = get_create_global_repo_cmd(compose, path_prefix)
    t = threading.Thread(target=run_create_global_repo, args=(compose, cmd))
    t.start()

    package_sets = populate_arch_pkgsets(compose, path_prefix, pkgset_global)
    package_sets["global"] = pkgset_global

    t.join()

    for arch in compose.get_arches():
        # TODO: threads? runroot?
        create_arch_repos(compose, arch, path_prefix)

    return package_sets


def _add_module_to_variant(koji_wrapper, variant, build, add_to_variant_modules=False):
    """
    Adds module defined by Koji build info to variant.

    :param Variant variant: Variant to add the module to.
    :param int: build id
    :param bool add_to_variant_modules: Adds the modules also to
        variant.modules.
    """
    mmds = {}
    archives = koji_wrapper.koji_proxy.listArchives(build["id"])
    for archive in archives:
        if archive["btype"] != "module":
            # Skip non module archives
            continue
        typedir = koji_wrapper.koji_module.pathinfo.typedir(build, archive["btype"])
        filename = archive["filename"]
        file_path = os.path.join(typedir, filename)
        try:
            # If there are two dots, the arch is in the middle. MBS uploads
            # files with actual architecture in the filename, but Pungi deals
            # in basearch. This assumes that each arch in the build maps to a
            # unique basearch.
            _, arch, _ = filename.split(".")
            filename = "modulemd.%s.txt" % getBaseArch(arch)
        except ValueError:
            pass
        mmds[filename] = Modulemd.Module.new_from_file(file_path)

    source_mmd = mmds["modulemd.txt"]
    nsvc = source_mmd.dup_nsvc()

    variant.mmds.append(source_mmd)
    for arch in variant.arches:
        variant.arch_mmds.setdefault(arch, {})[nsvc] = mmds["modulemd.%s.txt" % arch]

    if add_to_variant_modules:
        variant.modules.append(nsvc)

    return source_mmd


def _get_modules_from_koji(
    compose, koji_wrapper, event, variant, variant_tags, module_tag_rpm_filter
):
    """
    Loads modules for given `variant` from koji `session`, adds them to
    the `variant` and also to `variant_tags` dict.

    :param Compose compose: Compose for which the modules are found.
    :param koji_wrapper: We will obtain koji session from the wrapper.
    :param Variant variant: Variant with modules to find.
    :param dict variant_tags: Dict populated by this method. Key is `variant`
        and value is list of Koji tags to get the RPMs from.
    """

    # Find out all modules in every variant and add their Koji tags
    # to variant and variant_tags list.
    for module in variant.get_modules():
        koji_modules = get_koji_modules(compose, koji_wrapper, event, module["name"])
        for koji_module in koji_modules:
            mmd = _add_module_to_variant(koji_wrapper, variant, koji_module)

            tag = koji_module["tag"]
            uid = ':'.join([koji_module['name'], koji_module['stream'],
                            koji_module['version'], koji_module['context']])
            variant_tags[variant].append(tag)

            # Store mapping module-uid --> koji_tag into variant.
            # This is needed in createrepo phase where metadata is exposed by producmd
            variant.module_uid_to_koji_tag[uid] = tag

            module_tag_rpm_filter[tag] = set(mmd.get_rpm_filter().get())

            module_msg = (
                "Module '{uid}' in variant '{variant}' will use Koji tag '{tag}' "
                "(as a result of querying module '{module}')"
            ).format(uid=uid, variant=variant, tag=tag, module=module["name"])
            compose.log_info("%s" % module_msg)


def filter_inherited(koji_proxy, event, module_builds, top_tag):
    """Look at the tag inheritance and keep builds only from the topmost tag.

    Using latest=True for listTagged() call would automatically do this, but it
    does not understand streams, so we have to reimplement it here.
    """
    inheritance = [
        tag["name"] for tag in koji_proxy.getFullInheritance(top_tag, event=event["id"])
    ]

    def keyfunc(mb):
        return (mb["name"], mb["version"])

    result = []

    # Group modules by Name-Stream
    for _, builds in groupby(sorted(module_builds, key=keyfunc), keyfunc):
        builds = list(builds)
        # For each N-S combination find out which tags it's in
        available_in = set(build["tag_name"] for build in builds)

        # And find out which is the topmost tag
        for tag in [top_tag] + inheritance:
            if tag in available_in:
                break

        # And keep only builds from that topmost tag
        result.extend(build for build in builds if build["tag_name"] == tag)

    return result


def filter_by_whitelist(compose, module_builds, input_modules):
    """
    Exclude modules from the list that do not match any pattern specified in
    input_modules. Order may not be preserved.
    """
    specs = set()
    nvr_prefixes = set()
    for spec in input_modules:
        # Do not do any filtering in case variant wants all the modules.
        if spec["name"] == "*":
            return module_builds

        info = variant_dict_from_str(compose, spec["name"])
        prefix = ("%s-%s-%s.%s" % (
            info["name"],
            info["stream"].replace("-", "_"),
            info.get("version", ""),
            info.get("context", ""),
        )).rstrip("-.")
        nvr_prefixes.add((prefix, spec["name"]))
        specs.add(spec["name"])

    modules_to_keep = []
    used = set()

    for mb in module_builds:
        for (prefix, spec) in nvr_prefixes:
            if mb["nvr"].startswith(prefix):
                modules_to_keep.append(mb)
                used.add(spec)
                break

    if used != specs:
        raise RuntimeError(
            "Configuration specified patterns (%s) that don't match any modules in the configured tags."
            % ", ".join(specs - used)
        )

    return modules_to_keep


def _get_modules_from_koji_tags(
        compose, koji_wrapper, event_id, variant, variant_tags, module_tag_rpm_filter):
    """
    Loads modules for given `variant` from Koji, adds them to
    the `variant` and also to `variant_tags` dict.

    :param Compose compose: Compose for which the modules are found.
    :param KojiWrapper koji_wrapper: Koji wrapper.
    :param dict event_id: Koji event ID.
    :param Variant variant: Variant with modules to find.
    :param dict variant_tags: Dict populated by this method. Key is `variant`
        and value is list of Koji tags to get the RPMs from.
    """
    # Compose tags from configuration
    compose_tags = [
        {"name": tag} for tag in force_list(compose.conf["pkgset_koji_module_tag"])
    ]
    # Find out all modules in every variant and add their Koji tags
    # to variant and variant_tags list.
    koji_proxy = koji_wrapper.koji_proxy
    for modular_koji_tag in variant.get_modular_koji_tags() + compose_tags:
        tag = modular_koji_tag["name"]

        # List all the modular builds in the modular Koji tag.
        # We cannot use latest=True here, because we need to get all the
        # available streams of all modules. The stream is represented as
        # "release" in Koji build and with latest=True, Koji would return
        # only builds with highest release.
        module_builds = koji_proxy.listTagged(
            tag, event=event_id["id"], inherit=True, type="module")

        # Filter out builds inherited from non-top tag
        module_builds = filter_inherited(koji_proxy, event_id, module_builds, tag)

        # Apply whitelist of modules if specified.
        variant_modules = variant.get_modules()
        if variant_modules:
            module_builds = filter_by_whitelist(compose, module_builds, variant_modules)

        # Find the latest builds of all modules. This does following:
        # - Sorts the module_builds descending by Koji NVR (which maps to NSV
        #   for modules).
        # - Groups the sorted module_builds by NV (NS in modular world).
        #   In each resulting `ns_group`, the first item is actually build
        #   with the latest version (because the list is still sorted by NVR).
        # - Groups the `ns_group` again by "release" ("version" in modular
        #   world) to just get all the "contexts" of the given NSV. This is
        #   stored in `nsv_builds`.
        # - The `nsv_builds` contains the builds representing all the contexts
        #   of the latest version for give name-stream, so add them to
        #   `latest_builds`.
        latest_builds = []
        module_builds = sorted(
            module_builds, key=lambda build: build['nvr'], reverse=True)
        for ns, ns_builds in groupby(
                module_builds, key=lambda x: ":".join([x["name"], x["version"]])):
            for nsv, nsv_builds in groupby(
                    ns_builds, key=lambda x: x["release"].split(".")[0]):
                latest_builds += list(nsv_builds)
                break

        # For each latest modular Koji build, add it to variant and
        # variant_tags.
        for build in latest_builds:
            # Get the Build from Koji to get modulemd and module_tag.
            build = koji_proxy.getBuild(build["build_id"])
            module_tag = build.get("extra", {}).get("typeinfo", {}).get(
                "module", {}).get("content_koji_tag", "")

            variant_tags[variant].append(module_tag)

            mmd = _add_module_to_variant(koji_wrapper, variant, build, True)

            # Store mapping module-uid --> koji_tag into variant.
            # This is needed in createrepo phase where metadata is exposed by producmd
            module_data = build.get("extra", {}).get("typeinfo", {}).get("module", {})
            try:
                uid = "{name}:{stream}".format(**module_data)
            except KeyError as e:
                raise KeyError("Unable to create uid in format name:stream %s" % e)
            if module_data.get("version"):
                uid += ":{version}".format(**module_data)
                if module_data.get("context"):
                    uid += ":{context}".format(**module_data)
            variant.module_uid_to_koji_tag[uid] = module_tag

            module_tag_rpm_filter[module_tag] = set(mmd.get_rpm_filter().get())

            module_msg = "Module {module} in variant {variant} will use Koji tag {tag}.".format(
                variant=variant, tag=module_tag, module=build["nvr"])
            compose.log_info("%s" % module_msg)


def _find_old_file_cache_path(compose):
    """
    Finds the old compose with "pkgset_file_cache.pickled" and returns
    the path to it. If no compose is found, returns None.
    """
    old_compose_path = find_old_compose(
        compose.old_composes,
        compose.ci_base.release.short,
        compose.ci_base.release.version,
        compose.ci_base.release.type_suffix,
        compose.ci_base.base_product.short if compose.ci_base.release.is_layered else None,
        compose.ci_base.base_product.version if compose.ci_base.release.is_layered else None,
    )
    if not old_compose_path:
        return None

    old_file_cache_dir = compose.paths.work.pkgset_file_cache()
    rel_dir = relative_path(old_file_cache_dir, compose.topdir.rstrip('/') + '/')
    old_file_cache_path = os.path.join(old_compose_path, rel_dir)
    if not os.path.exists(old_file_cache_path):
        return None
    return old_file_cache_path


def populate_global_pkgset(compose, koji_wrapper, path_prefix, event):
    all_arches = set(["src"])
    for arch in compose.get_arches():
        is_multilib = is_arch_multilib(compose.conf, arch)
        arches = get_valid_arches(arch, is_multilib)
        all_arches.update(arches)

    # List of compose tags from which we create this compose
    compose_tags = []

    # List of compose_tags per variant
    variant_tags = {}

    # In case we use "nodeps" gather_method, we might know the final list of
    # packages which will end up in the compose even now, so instead of reading
    # all the packages from Koji tag, we can just cherry-pick the ones which
    # are really needed to do the compose and safe lot of time and resources
    # here. This only works if we are not creating bootable images. Those could
    # include packages that are not in the compose.
    packages_to_gather, groups = get_packages_to_gather(
        compose, include_arch=False, include_prepopulated=True)
    if groups:
        comps = CompsWrapper(compose.paths.work.comps())
        for group in groups:
            packages_to_gather += comps.get_packages(group)
    if compose.conf["gather_method"] == "nodeps" and not compose.conf.get('bootable'):
        populate_only_packages_to_gather = True
    else:
        populate_only_packages_to_gather = False

    # In case we use "deps" gather_method, there might be some packages in
    # the Koji tag which are not signed with proper sigkey. However, these
    # packages might never end up in a compose depending on which packages
    # from the Koji tag are requested how the deps are resolved in the end.
    # In this case, we allow even packages with invalid sigkeys to be returned
    # by PKGSET phase and later, the gather phase checks its results and if
    # there are some packages with invalid sigkeys, it raises an exception.
    allow_invalid_sigkeys = compose.conf["gather_method"] == "deps"

    # Mapping from koji tags to sets of package names that should be filtered
    # out. This is basically a workaround for tagging working on build level,
    # not rpm level. A module tag may build a package but not want it included.
    # This should exclude it from the package set to avoid pulling it in as a
    # dependency.
    module_tag_rpm_filter = {}

    for variant in compose.all_variants.values():
        # pkgset storing the packages belonging to this particular variant.
        variant.pkgset = pungi.phases.pkgset.pkgsets.KojiPackageSet(
            koji_wrapper, compose.conf["sigkeys"], logger=compose._logger,
            arches=all_arches)
        variant_tags[variant] = []

        # Get the modules from Koji tag or from PDC, depending on
        # configuration.
        modular_koji_tags = variant.get_modular_koji_tags()
        if (variant.modules or modular_koji_tags) and not Modulemd:
            raise ValueError(
                "pygobject module or libmodulemd library is not installed, "
                "support for modules is disabled, but compose contains "
                "modules.")

        if modular_koji_tags or (compose.conf["pkgset_koji_module_tag"] and variant.modules):
            included_modules_file = os.path.join(
                compose.paths.work.topdir(arch="global"),
                "koji-tag-module-%s.yaml" % variant.uid)
            _get_modules_from_koji_tags(
                compose,
                koji_wrapper,
                event,
                variant,
                variant_tags,
                module_tag_rpm_filter,
            )
        elif variant.modules:
            included_modules_file = os.path.join(
                compose.paths.work.topdir(arch="global"),
                "koji-module-%s.yaml" % variant.uid)
            _get_modules_from_koji(
                compose,
                koji_wrapper,
                event,
                variant,
                variant_tags,
                module_tag_rpm_filter,
            )

        # Ensure that every tag added to `variant_tags` is added also to
        # `compose_tags`.
        for variant_tag in variant_tags[variant]:
            if variant_tag not in compose_tags:
                compose_tags.append(variant_tag)

        if variant.mmds:
            Modulemd.Module.dump_all(variant.mmds, included_modules_file)
        if not variant_tags[variant] and variant.modules is None:
            variant_tags[variant].extend(force_list(compose.conf["pkgset_koji_tag"]))

    # Add global tag(s) if supplied.
    pkgset_koji_tags = []
    if 'pkgset_koji_tag' in compose.conf:
        if compose.conf["pkgset_koji_tag"] == "not-used":
            # The magic value is used for modular composes to avoid errors
            # about missing option. It should be removed in next version.
            compose.log_warning('pkgset_koji_tag is set to "not-used", but the '
                                'option is no longer required. Remove it from '
                                'the configuration.')
        else:
            pkgset_koji_tags = force_list(compose.conf["pkgset_koji_tag"])
            compose_tags.extend(pkgset_koji_tags)

    inherit = compose.conf["pkgset_koji_inherit"]
    inherit_modules = compose.conf["pkgset_koji_inherit_modules"]
    global_pkgset_path = os.path.join(
        compose.paths.work.topdir(arch="global"), "pkgset_global.pickle")
    if compose.DEBUG and os.path.isfile(global_pkgset_path):
        msg = "Populating the global package set from tag '%s'" % compose_tags
        compose.log_warning("[SKIP ] %s" % msg)
        with open(global_pkgset_path, "rb") as f:
            global_pkgset = pickle.load(f)
    else:
        global_pkgset = pungi.phases.pkgset.pkgsets.KojiPackageSet(
            koji_wrapper, compose.conf["sigkeys"], logger=compose._logger,
            arches=all_arches)

        old_file_cache_path = _find_old_file_cache_path(compose)
        old_file_cache = None
        if old_file_cache_path:
            compose.log_info("Reusing old PKGSET file cache from %s" % old_file_cache_path)
            old_file_cache = pungi.phases.pkgset.pkgsets.KojiPackageSet.load_old_file_cache(
                old_file_cache_path
            )
            global_pkgset.set_old_file_cache(old_file_cache)

        # Get package set for each compose tag and merge it to global package
        # list. Also prepare per-variant pkgset, because we do not have list
        # of binary RPMs in module definition - there is just list of SRPMs.
        for compose_tag in compose_tags:
            compose.log_info("Populating the global package set from tag "
                             "'%s'" % compose_tag)
            if compose_tag in pkgset_koji_tags:
                extra_builds = force_list(compose.conf.get("pkgset_koji_builds", []))
            else:
                extra_builds = []
            pkgset = pungi.phases.pkgset.pkgsets.KojiPackageSet(
                koji_wrapper, compose.conf["sigkeys"], logger=compose._logger,
                arches=all_arches, packages=packages_to_gather,
                allow_invalid_sigkeys=allow_invalid_sigkeys,
                populate_only_packages=populate_only_packages_to_gather,
                cache_region=compose.cache_region,
                extra_builds=extra_builds)
            if old_file_cache:
                pkgset.set_old_file_cache(old_file_cache)
            # Create a filename for log with package-to-tag mapping. The tag
            # name is included in filename, so any slashes in it are replaced
            # with underscores just to be safe.
            logfile = compose.paths.log.log_file(
                None, 'packages_from_%s' % compose_tag.replace('/', '_'))
            is_traditional = compose_tag in compose.conf.get('pkgset_koji_tag', [])
            should_inherit = inherit if is_traditional else inherit_modules
            pkgset.populate(
                compose_tag,
                event,
                inherit=should_inherit,
                logfile=logfile,
                exclude_packages=module_tag_rpm_filter.get(compose_tag),
            )
            for variant in compose.all_variants.values():
                if compose_tag in variant_tags[variant]:

                    # If it's a modular tag, store the package set for the module.
                    for nsvc, koji_tag in variant.module_uid_to_koji_tag.items():
                        if compose_tag == koji_tag:
                            variant.nsvc_to_pkgset[nsvc] = pkgset

                    # Optimization for case where we have just single compose
                    # tag - we do not have to merge in this case...
                    if len(variant_tags[variant]) == 1:
                        variant.pkgset = pkgset
                    else:
                        variant.pkgset.fast_merge(pkgset)
            # Optimization for case where we have just single compose
            # tag - we do not have to merge in this case...
            if len(compose_tags) == 1:
                global_pkgset = pkgset
            else:
                global_pkgset.fast_merge(pkgset)
        with open(global_pkgset_path, 'wb') as f:
            data = pickle.dumps(global_pkgset)
            f.write(data)

    # write global package list
    global_pkgset.save_file_list(
        compose.paths.work.package_list(arch="global"),
        remove_path_prefix=path_prefix)
    global_pkgset.save_file_cache(compose.paths.work.pkgset_file_cache())
    return global_pkgset


def get_koji_event_info(compose, koji_wrapper):
    event_file = os.path.join(compose.paths.work.topdir(arch="global"), "koji-event")

    msg = "Getting koji event"
    if compose.DEBUG and os.path.exists(event_file):
        compose.log_warning("[SKIP ] %s" % msg)
        result = json.load(open(event_file, "r"))
    else:
        result = get_koji_event_raw(koji_wrapper, compose.koji_event, event_file)
        if compose.koji_event:
            compose.log_info("Setting koji event to a custom value: %s" % compose.koji_event)
        else:
            compose.log_info(msg)
            compose.log_info("Koji event: %s" % result["id"])

    return result


def get_koji_event_raw(koji_wrapper, event_id, event_file):
    if event_id:
        koji_event = koji_wrapper.koji_proxy.getEvent(event_id)
    else:
        koji_event = koji_wrapper.koji_proxy.getLastEvent()

    with open(event_file, "w") as f:
        json.dump(koji_event, f)

    return koji_event
