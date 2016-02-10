# -*- coding: utf-8 -*-

import copy
import os
import time
from kobo import shortcuts

from pungi.util import get_variant_data, resolve_git_url, makedirs
from pungi.phases.base import PhaseBase
from pungi.linker import Linker
from pungi.paths import translate_path
from pungi.wrappers.kojiwrapper import KojiWrapper
from kobo.threads import ThreadPool, WorkerThread
from productmd.images import Image


class ImageBuildPhase(PhaseBase):
    """class for wrapping up koji image-build"""
    name = "image_build"

    def __init__(self, compose):
        PhaseBase.__init__(self, compose)
        self.pool = ThreadPool(logger=self.compose._logger)

    def skip(self):
        if PhaseBase.skip(self):
            return True
        if not self.compose.conf.get(self.name):
            self.compose.log_info("Config section '%s' was not found. Skipping" % self.name)
            return True
        return False

    def _get_install_tree(self, image_conf, variant):
        """
        Get a path to os tree for a variant specified in `install_tree_from` or
        current variant. If the config is set, it will be removed from the
        dict.
        """
        install_tree_from = image_conf.pop('install_tree_from', variant.uid)
        install_tree_source = self.compose.variants.get(install_tree_from)
        if not install_tree_source:
            raise RuntimeError(
                'There is no variant %s to get install tree from when building image for %s.'
                % (install_tree_from, variant.uid))
        return translate_path(
            self.compose,
            self.compose.paths.compose.os_tree('$arch', install_tree_source, create_dir=False)
        )

    def _get_repo(self, image_conf, variant):
        """
        Get a comma separated list of repos. First included are those
        explicitly listed in config, followed by repos from other variants,
        finally followed by repo for current variant.

        The `repo_from` key is removed from the dict (if present).
        """
        repo = shortcuts.force_list(image_conf.get('repo', []))

        extras = shortcuts.force_list(image_conf.pop('repo_from', []))
        extras.append(variant.uid)

        for extra in extras:
            v = self.compose.variants.get(extra)
            if not v:
                raise RuntimeError(
                    'There is no variant %s to get repo from when building image for %s.'
                    % (extra, variant.uid))
            repo.append(translate_path(
                self.compose,
                self.compose.paths.compose.os_tree('$arch', v, create_dir=False)))

        return ",".join(repo)

    def _get_arches(self, image_conf, arches):
        if 'arches' in image_conf['image-build']:
            arches = set(image_conf['image-build'].get('arches', [])) & arches
        return ','.join(sorted(arches))

    def _set_release(self, image_conf):
        """If release is set explicitly to None, replace it with date and respin."""
        if 'release' in image_conf and image_conf['release'] is None:
            image_conf['release'] = '%s.%s' % (self.compose.compose_date, self.compose.compose_respin)

    def run(self):
        for variant in self.compose.get_variants():
            arches = set([x for x in variant.arches if x != 'src'])

            for image_conf in get_variant_data(self.compose.conf, self.name, variant):
                # We will modify the data, so we need to make a copy to
                # prevent problems in next iteration where the original
                # value is needed.
                image_conf = copy.deepcopy(image_conf)

                # image_conf is passed to get_image_build_cmd as dict

                image_conf["image-build"]['arches'] = self._get_arches(image_conf, arches)
                if not image_conf["image-build"]['arches']:
                    continue

                # Replace possible ambiguous ref name with explicit hash.
                if 'ksurl' in image_conf:
                    image_conf["image-build"]['ksurl'] = resolve_git_url(image_conf["image-build"]['ksurl'])

                image_conf["image-build"]["variant"] = variant

                image_conf["image-build"]["install_tree"] = self._get_install_tree(image_conf, variant)

                self._set_release(image_conf)

                # transform format into right 'format' for image-build
                # e.g. 'docker,qcow2'
                format = image_conf["image-build"]["format"]
                image_conf["image-build"]["format"] = ",".join([x[0] for x in image_conf["image-build"]["format"]])
                image_conf["image-build"]['repo'] = self._get_repo(image_conf, variant)

                cmd = {
                    "format": format,
                    "image_conf": image_conf,
                    "conf_file": self.compose.paths.work.image_build_conf(
                        image_conf["image-build"]['variant'],
                        image_name=image_conf["image-build"]['name'],
                        image_type=image_conf["image-build"]['format'].replace(",", "-")
                    ),
                    "image_dir": self.compose.paths.compose.image_dir(variant),
                    "relative_image_dir": self.compose.paths.compose.image_dir(
                        variant, relative=True
                    ),
                    "link_type": self.compose.conf.get("link_type", "hardlink-or-copy"),
                    "scratch": image_conf.pop('scratch', False),
                }
                self.pool.add(CreateImageBuildThread(self.pool))
                self.pool.queue_put((self.compose, cmd))

        self.pool.start()


class CreateImageBuildThread(WorkerThread):
    def fail(self, compose, cmd):
        compose.log_error("CreateImageBuild failed.")

    def process(self, item, num):
        compose, cmd = item
        try:
            self.worker(num, compose, cmd)
        except Exception as exc:
            if not compose.can_fail(cmd["image_conf"]["image-build"]['variant'], '*', 'image-build'):
                raise
            else:
                msg = ('[FAIL] image-build for variant %s failed, but going on anyway.\n%s'
                       % (cmd['image_conf']['image-build']['variant'], exc))
                self.pool.log_info(msg)

    def worker(self, num, compose, cmd):
        arches = cmd["image_conf"]["image-build"]['arches'].split(',')
        log_file = compose.paths.log.log_file(
            cmd["image_conf"]["image-build"]["arches"],
            "imagebuild-%s-%s-%s" % ('-'.join(arches),
                                     cmd["image_conf"]["image-build"]["variant"],
                                     cmd["image_conf"]["image-build"]['format'].replace(",", "-"))
        )
        msg = "Creating %s image (arches: %s, variant: %s)" % (cmd["image_conf"]["image-build"]["format"].replace(",", "-"),
                                                               '-'.join(arches),
                                                               cmd["image_conf"]["image-build"]["variant"])
        self.pool.log_info("[BEGIN] %s" % msg)

        koji_wrapper = KojiWrapper(compose.conf["koji_profile"])

        # writes conf file for koji image-build
        self.pool.log_info("Writing image-build config for %s.%s into %s" % (
            cmd["image_conf"]["image-build"]["variant"], '-'.join(arches), cmd["conf_file"]))
        koji_cmd = koji_wrapper.get_image_build_cmd(cmd["image_conf"],
                                                    conf_file_dest=cmd["conf_file"],
                                                    scratch=cmd['scratch'])

        # avoid race conditions?
        # Kerberos authentication failed: Permission denied in replay cache code (-1765328215)
        time.sleep(num * 3)
        output = koji_wrapper.run_blocking_cmd(koji_cmd, log_file=log_file)
        self.pool.log_debug("build-image outputs: %s" % (output))
        if output["retcode"] != 0:
            self.fail(compose, cmd)
            raise RuntimeError("ImageBuild task failed: %s. See %s for more details." % (output["task_id"], log_file))

        # copy image to images/
        image_infos = []

        paths = koji_wrapper.get_image_paths(output["task_id"])

        for arch, paths in paths.iteritems():
            for path in paths:
                # format is list of tuples [('qcow2', '.qcow2'), ('raw-xz', 'raw.xz'),]
                for format, suffix in cmd['format']:
                    if path.endswith(suffix):
                        image_infos.append({'path': path, 'suffix': suffix, 'type': format, 'arch': arch})
                        break

        if len(image_infos) != len(cmd['format']) * len(arches):
            self.pool.log_error(
                "Error in koji task %s. Expected to find same amount of images "
                "as in suffixes attr in image-build (%s) for each arch (%s). Got '%s'." %
                (output["task_id"], len(cmd['format']),
                 len(arches), len(image_infos)))
            self.fail(compose, cmd)

        # The usecase here is that you can run koji image-build with multiple --format
        # It's ok to do it serialized since we're talking about max 2 images per single
        # image_build record
        linker = Linker(logger=compose._logger)
        for image_info in image_infos:
            image_dir = cmd["image_dir"] % {"arch": image_info['arch']}
            makedirs(image_dir)
            relative_image_dir = cmd["relative_image_dir"] % {"arch": image_info['arch']}

            # let's not change filename of koji outputs
            image_dest = os.path.join(image_dir, os.path.basename(image_info['path']))
            linker.link(image_info['path'], image_dest, link_type=cmd["link_type"])

            # Update image manifest
            img = Image(compose.im)
            img.type = image_info['type']
            img.format = image_info['suffix']
            img.path = os.path.join(relative_image_dir, os.path.basename(image_dest))
            img.mtime = int(os.stat(image_dest).st_mtime)
            img.size = os.path.getsize(image_dest)
            img.arch = image_info['arch']
            img.disc_number = 1     # We don't expect multiple disks
            img.disc_count = 1
            img.bootable = False
            compose.im.add(variant=cmd["image_conf"]["image-build"]["variant"].uid,
                           arch=image_info['arch'],
                           image=img)

        self.pool.log_info("[DONE ] %s" % msg)
