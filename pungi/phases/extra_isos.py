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

from kobo.shortcuts import force_list
from kobo.threads import ThreadPool, WorkerThread

from pungi import createiso
from pungi.phases.base import ConfigGuardedPhase, PhaseBase, PhaseLoggerMixin
from pungi.phases.createiso import (add_iso_to_metadata, copy_boot_images,
                                    run_createiso_command)
from pungi.util import failable, get_format_substs, get_variant_data, get_volid
from pungi.wrappers import iso
from pungi.wrappers.scm import get_dir_from_scm, get_file_from_scm


class ExtraIsosPhase(PhaseLoggerMixin, ConfigGuardedPhase, PhaseBase):
    name = "extra_isos"

    def __init__(self, compose):
        super(ExtraIsosPhase, self).__init__(compose)
        self.pool = ThreadPool(logger=self.logger)

    def validate(self):
        for variant in self.compose.get_variants(types=['variant']):
            for config in get_variant_data(self.compose.conf, self.name, variant):
                extra_arches = set(config.get('arches', [])) - set(variant.arches)
                if extra_arches:
                    self.compose.log_warning(
                        'Extra iso config for %s mentions non-existing arches: %s'
                        % (variant, ', '.join(sorted(extra_arches))))

    def run(self):
        commands = []

        for variant in self.compose.get_variants(types=['variant']):
            for config in get_variant_data(self.compose.conf, self.name, variant):
                arches = set(variant.arches)
                if config.get('arches'):
                    arches &= set(config['arches'])
                if not config['skip_src']:
                    arches.add('src')
                for arch in sorted(arches):
                    commands.append((config, variant, arch))

        for (config, variant, arch) in commands:
            self.pool.add(ExtraIsosThread(self.pool))
            self.pool.queue_put((self.compose, config, variant, arch))

        self.pool.start()


class ExtraIsosThread(WorkerThread):
    def process(self, item, num):
        self.num = num
        compose, config, variant, arch = item
        can_fail = arch in config.get('failable_arches', [])
        with failable(compose, can_fail, variant, arch, 'extra_iso', logger=self.pool._logger):
            self.worker(compose, config, variant, arch)

    def worker(self, compose, config, variant, arch):
        filename = get_filename(compose, variant, arch, config.get('filename'))
        volid = get_volume_id(compose, variant, arch, config.get('volid', []))
        iso_dir = compose.paths.compose.iso_dir(arch, variant)
        iso_path = os.path.join(iso_dir, filename)

        msg = "Creating ISO (arch: %s, variant: %s): %s" % (arch, variant, filename)
        self.pool.log_info("[BEGIN] %s" % msg)

        get_extra_files(compose, variant, arch, config.get('extra_files', []))

        bootable = arch != "src" and compose.conf['bootable']

        graft_points = get_iso_contents(compose, variant, arch,
                                        config['include_variants'],
                                        filename, bootable)

        opts = createiso.CreateIsoOpts(
            output_dir=iso_dir,
            iso_name=filename,
            volid=volid,
            graft_points=graft_points,
            arch=arch,
            supported=compose.supported,
        )

        if bootable:
            opts = opts._replace(buildinstall_method=compose.conf['buildinstall_method'])

        script_file = os.path.join(compose.paths.work.tmp_dir(arch, variant),
                                   'extraiso-%s.sh' % filename)
        with open(script_file, 'w') as f:
            createiso.write_script(opts, f)

        run_createiso_command(compose.conf["runroot"], self.num, compose, bootable, arch,
                              ['bash', script_file], [compose.topdir],
                              log_file=compose.paths.log.log_file(
                                  arch, "extraiso-%s" % os.path.basename(iso_path)),
                              with_jigdo=False)

        add_iso_to_metadata(compose, variant, arch, iso_path, bootable, 1, 1)

        self.pool.log_info("[DONE ] %s" % msg)


def get_extra_files(compose, variant, arch, extra_files):
    """Clone the configured files into a directory from where they can be
    included in the ISO.
    """
    extra_files_dir = compose.paths.work.extra_iso_extra_files_dir(arch, variant)
    for scm_dict in extra_files:
        getter = get_file_from_scm if 'file' in scm_dict else get_dir_from_scm
        target_path = os.path.join(extra_files_dir, scm_dict.get('target', '').lstrip('/'))
        getter(scm_dict, target_path, logger=compose._logger)


def get_iso_contents(compose, variant, arch, include_variants, filename, bootable):
    """Find all files that should be on the ISO. For bootable image we start
    with the boot configuration. Then for each variant we add packages,
    repodata and extra files. Finally we add top-level extra files.
    """
    iso_dir = compose.paths.work.iso_dir(arch, filename)

    files = {}
    if bootable:
        buildinstall_dir = compose.paths.work.buildinstall_dir(arch, create_dir=False)
        if compose.conf['buildinstall_method'] == 'lorax':
            buildinstall_dir = os.path.join(buildinstall_dir, variant.uid)

        copy_boot_images(buildinstall_dir, iso_dir)
        files = iso.get_graft_points([buildinstall_dir, iso_dir])

    variants = [variant.uid] + include_variants
    for variant_uid in variants:
        var = compose.all_variants[variant_uid]

        # Get packages...
        package_dir = compose.paths.compose.packages(arch, var)
        for k, v in iso.get_graft_points([package_dir]).items():
            files[os.path.join(var.uid, 'Packages', k)] = v

        # Get repodata...
        tree_dir = compose.paths.compose.repository(arch, var)
        repo_dir = os.path.join(tree_dir, 'repodata')
        for k, v in iso.get_graft_points([repo_dir]).items():
            files[os.path.join(var.uid, 'repodata', k)] = v

        # Get extra files...
        extra_files_dir = compose.paths.work.extra_files_dir(arch, var)
        for k, v in iso.get_graft_points([extra_files_dir]).items():
            files[os.path.join(var.uid, k)] = v

    # Add extra files specific for the ISO
    extra_files_dir = compose.paths.work.extra_iso_extra_files_dir(arch, variant)
    files.update(iso.get_graft_points([extra_files_dir]))

    gp = "%s-graft-points" % iso_dir
    iso.write_graft_points(gp, files, exclude=["*/lost+found", "*/boot.iso"])
    return gp


def get_filename(compose, variant, arch, format):
    disc_type = compose.conf['disc_types'].get('dvd', 'dvd')
    base_filename = compose.get_image_name(
        arch, variant, disc_type=disc_type, disc_num=1)
    if not format:
        return base_filename
    kwargs = {
        'arch': arch,
        'disc_type': disc_type,
        'disc_num': 1,
        'suffix': '.iso',
        'filename': base_filename,
        'variant': variant,
    }
    args = get_format_substs(compose, **kwargs)
    try:
        return (format % args).format(**args)
    except KeyError as err:
        raise RuntimeError('Failed to create image name: unknown format element: %s' % err)


def get_volume_id(compose, variant, arch, formats):
    disc_type = compose.conf['disc_types'].get('dvd', 'dvd')
    # Get volume ID for regular ISO so that we can substitute it in.
    volid = get_volid(compose, arch, variant, disc_type=disc_type)
    return get_volid(compose, arch, variant, disc_type=disc_type,
                     formats=force_list(formats), volid=volid)