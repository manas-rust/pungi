# -*- coding: utf-8 -*-


"""
This script creates unified ISOs for a specified compose.
Unified ISOs are created per architecture and
contain all variant packages and repos.


TODO:
* jigdo
"""


from __future__ import print_function

import copy
import errno
import glob
import json
import os
import shutil
import sys
import tempfile

import productmd
import productmd.compose
import productmd.images
import productmd.treeinfo
from kobo.shortcuts import run, compute_file_checksums

import pungi.linker
import pungi.wrappers.createrepo
from pungi.util import makedirs
from pungi.compose_metadata.discinfo import write_discinfo as create_discinfo
from pungi.wrappers import iso
from pungi.phases.image_checksum import dump_checksums, get_images, make_checksums


def ti_merge(one, two):
    assert one.tree.arch == two.tree.arch
    for variant in two.variants.get_variants(recursive=False):
        if variant.uid in one.variants:
            continue
        var = productmd.treeinfo.Variant(one)
        var.id = variant.id
        var.uid = variant.uid
        var.name = variant.name
        var.type = variant.type
        for i in ("debug_packages", "debug_repository", "packages", "repository",
                  "source_packages", "source_repository"):
            setattr(var, i, getattr(variant, i, None))
        one.variants.add(var)


DEFAULT_CHECKSUMS = ['md5', 'sha1', 'sha256']


class UnifiedISO(object):
    def __init__(self, compose_path, output_path=None):
        self.compose_path = os.path.abspath(compose_path)
        compose_subdir = os.path.join(self.compose_path, "compose")
        if os.path.exists(compose_subdir):
            self.compose_path = compose_subdir

        self.compose = productmd.compose.Compose(compose_path)
        self.ci = self.compose.info

        self.linker = pungi.linker.Linker()

        temp_topdir = os.path.abspath(os.path.join(self.compose_path, "..", "work"))
        makedirs(temp_topdir)
        self.temp_dir = tempfile.mkdtemp(prefix="unified_isos_", dir=temp_topdir)

        self.treeinfo = {}      # {arch/src: TreeInfo}
        self.repos = {}         # {arch/src: {variant: new_path}
        self.comps = {}         # {arch/src: {variant: old_path}
        self.productid = {}     # {arch/stc: {variant: old_path}
        self.images = {}        # {arch/src: [*.iso, *.iso.{md5,sha1,sha256}sum]}
        self.conf = self.read_config()

    def create(self, delete_temp=True):
        print("Creating unified ISOs for: {0}".format(self.compose_path))
        try:
            self.link_to_temp()
            self.createrepo()
            self.discinfo()
            self.createiso()
            self.link_to_compose()
            self.update_checksums()
        finally:
            if delete_temp:
                shutil.rmtree(self.temp_dir)

    def _link_tree(self, dir, variant, arch):
        blacklist_files = [".treeinfo", ".discinfo", "boot.iso", "media.repo", "extra_files.json"]
        blacklist_dirs = ["repodata"]

        for root, dirs, files in os.walk(dir):
            for i in blacklist_dirs:
                if i in dirs:
                    dirs.remove(i)

            for fn in files:
                if fn in blacklist_files:
                    continue

                old_path = os.path.join(root, fn)
                if fn.endswith(".rpm"):
                    new_path = os.path.join(self.temp_dir, "trees", arch, variant.uid, fn)
                    self.repos.setdefault(arch, {})[variant.uid] = os.path.dirname(new_path)
                else:
                    old_relpath = os.path.relpath(old_path, dir)
                    new_path = os.path.join(self.temp_dir, "trees", arch, old_relpath)

                makedirs(os.path.dirname(new_path))
                try:
                    self.linker.link(old_path, new_path)
                except OSError as exc:
                    print("Failed to link %s to %s: %s" % (old_path, new_path, exc.strerror),
                          file=sys.stderr)
                    raise

    def link_to_temp(self):
        # copy files to new location; change RPM location to $variant_uid
        for variant in self.ci.get_variants(recursive=False):
            for arch in variant.arches:
                print("Processing: {0}.{1}".format(variant.uid, arch))
                tree_dir = os.path.join(self.compose_path, variant.paths.os_tree[arch])

                ti = productmd.treeinfo.TreeInfo()
                try:
                    ti.load(os.path.join(tree_dir, ".treeinfo"))
                except IOError as exc:
                    if exc.errno != errno.ENOENT:
                        raise
                    print('Tree %s.%s has no .treeinfo, skipping...'
                          % (variant.uid, arch),
                          file=sys.stderr)
                    continue

                arch_ti = self.treeinfo.get(arch)
                if arch_ti is None:
                    arch_ti = ti
                    self.treeinfo[arch] = arch_ti
                else:
                    ti_merge(arch_ti, ti)

                if arch_ti.tree.arch != arch:
                    raise RuntimeError('Treeinfo arch mismatch')

                # override paths
                arch_ti[variant.uid].repository = variant.uid
                arch_ti[variant.uid].packages = variant.uid

                comps_path = glob.glob(os.path.join(self.compose_path,
                                                    variant.paths.repository[arch],
                                                    "repodata", "*comps*.xml"))
                if comps_path:
                    self.comps.setdefault(arch, {})[variant.uid] = comps_path[0]

                productid_path = os.path.join(self.compose_path, variant.paths.repository[arch],
                                              "repodata", "productid")
                self.productid.setdefault(arch, {})[variant.uid] = productid_path

                self._link_tree(tree_dir, variant, arch)

                # sources
                print("Processing: {0}.{1}".format(variant.uid, "src"))
                tree_dir = os.path.join(self.compose_path, variant.paths.source_tree[arch])
                ti = productmd.treeinfo.TreeInfo()
                ti.load(os.path.join(tree_dir, ".treeinfo"))

                arch_ti = self.treeinfo.get("src")
                if arch_ti is None:
                    arch_ti = ti
                    self.treeinfo["src"] = arch_ti
                else:
                    ti_merge(arch_ti, ti)

                if arch_ti.tree.arch != "src":
                    raise RuntimeError('Treeinfo arch mismatch')

                # override paths
                arch_ti[variant.uid].repository = variant.uid
                arch_ti[variant.uid].packages = variant.uid
                # set to None, replace with source_*; requires productmd changes or upstream version
                # arch_ti[variant.uid].source_repository = variant.uid
                # arch_ti[variant.uid].source_packages = variant.uid

                self._link_tree(tree_dir, variant, 'src')

                # Debuginfo
                print("Processing: {0}.{1} debuginfo".format(variant.uid, arch))
                tree_dir = os.path.join(self.compose_path, variant.paths.debug_tree[arch])

                debug_arch = 'debug-%s' % arch

                # We don't have a .treeinfo for debuginfo trees. Let's just
                # copy the one from binary tree.
                self.treeinfo.setdefault(debug_arch, copy.deepcopy(self.treeinfo[arch]))

                self._link_tree(tree_dir, variant, debug_arch)

    def createrepo(self):
        # remove old repomd.xml checksums from treeinfo
        for arch, ti in self.treeinfo.iteritems():
            print("Removing old repomd.xml checksums from treeinfo: {0}".format(arch))
            for i in ti.checksums.checksums.keys():
                if "repomd.xml" in i:
                    del ti.checksums.checksums[i]

        # write new per-variant repodata
        cr = pungi.wrappers.createrepo.CreaterepoWrapper(createrepo_c=True)
        for arch in self.repos:
            ti = self.treeinfo[arch]
            for variant in self.repos[arch]:
                print("Creating repodata: {0}.{1}".format(variant, arch))
                tree_dir = os.path.join(self.temp_dir, "trees", arch)
                repo_path = self.repos[arch][variant]
                comps_path = self.comps.get(arch, {}).get(variant, None)
                cmd = cr.get_createrepo_cmd(repo_path, groupfile=comps_path, update=True)
                run(cmd, show_cmd=True)

                productid_path = self.productid.get(arch, {}).get(variant, None)
                if productid_path:
                    print("Adding productid to repodata: {0}.{1}".format(variant, arch))
                    repo_dir = os.path.join(self.repos[arch][variant], "repodata")
                    new_path = os.path.join(repo_dir, os.path.basename(productid_path))

                    if os.path.exists(productid_path):
                        shutil.copy2(productid_path, new_path)
                        cmd = cr.get_modifyrepo_cmd(repo_dir, new_path, compress_type="gz")
                        run(cmd)
                    else:
                        print("WARNING: productid not found in {0}.{1}".format(variant, arch))

                print("Inserting new repomd.xml checksum to treeinfo: {0}.{1}".format(variant, arch))
                # insert new repomd.xml checksum to treeinfo
                repomd_path = os.path.join(repo_path, "repodata", "repomd.xml")
                ti.checksums.add(os.path.relpath(repomd_path, tree_dir), 'sha256', root_dir=tree_dir)

        # write treeinfo
        for arch, ti in self.treeinfo.iteritems():
            print("Writing treeinfo: {0}".format(arch))
            ti_path = os.path.join(self.temp_dir, "trees", arch, ".treeinfo")
            ti.dump(ti_path)

    def discinfo(self):
        # write discinfo and media repo
        for arch, ti in self.treeinfo.iteritems():
            di_path = os.path.join(self.temp_dir, "trees", arch, ".discinfo")
            description = "%s %s" % (ti.release.name, ti.release.version)
            if ti.release.is_layered:
                description += " for %s %s" % (ti.base_product.name, ti.base_product.version)
            create_discinfo(di_path, description, arch.split('-', 1)[-1])

    def read_config(self):
        try:
            conf_dump = glob.glob(os.path.join(self.compose_path,
                                               '../logs/global/config-dump*.global.log'))[0]
        except IndexError:
            print('Config dump not found, can not adhere to previous settings. '
                  'Expect weird naming and checksums.',
                  file=sys.stderr)
            return {}
        with open(conf_dump) as f:
            return json.load(f)

    def createiso(self):
        # create ISOs
        im = self.compose.images

        for typed_arch, ti in self.treeinfo.items():
            source_dir = os.path.join(self.temp_dir, "trees", typed_arch)
            arch = typed_arch.split('-', 1)[-1]
            debuginfo = typed_arch.startswith('debug-')

            # XXX: HARDCODED
            disc_type = "dvd"

            iso_arch = arch
            if arch == "src":
                iso_arch = "source"
            elif debuginfo:
                iso_arch = arch + '-debuginfo'

            iso_name = "%s-%s-%s.iso" % (self.ci.compose.id, iso_arch, disc_type)
            iso_dir = os.path.join(self.temp_dir, "iso", iso_arch)
            iso_path = os.path.join(iso_dir, iso_name)

            print("Creating ISO for {0}: {1}".format(arch, iso_name))

            makedirs(iso_dir)
            volid = "%s %s %s" % (ti.release.short, ti.release.version, arch)
            if debuginfo:
                volid += " debuginfo"

            # create ISO
            run(iso.get_mkisofs_cmd(iso_path, [source_dir], volid=volid, exclude=["./lost+found"]))

            # implant MD5
            supported = True
            run(iso.get_implantisomd5_cmd(iso_path, supported))

            checksums = compute_file_checksums(
                iso_path, self.conf.get('media_checksums', DEFAULT_CHECKSUMS))

            # write manifest file
            run(iso.get_manifest_cmd(iso_path))

            img = productmd.images.Image(im)
            # temporary path, just a file name; to be replaced with variant specific path
            img.path = os.path.basename(iso_path)
            img.mtime = int(os.stat(iso_path).st_mtime)
            img.size = os.path.getsize(iso_path)
            img.arch = arch

            # XXX: HARDCODED
            img.type = "dvd"
            img.format = "iso"
            img.disc_number = 1
            img.disc_count = 1
            img.bootable = False
            img.unified = True

            self.images.setdefault(typed_arch, set()).add(iso_path)
            self.images.setdefault(typed_arch, set()).add(iso_path + ".manifest")

            for checksum_type, checksum in checksums.iteritems():
                if not self.conf.get('media_checksum_one_file', False):
                    checksum_path = dump_checksums(iso_dir, checksum_type,
                                                   {iso_name: checksum},
                                                   '%s.%sSUM' % (iso_name, checksum_type.upper()))
                    self.images.setdefault(typed_arch, set()).add(checksum_path)

                img.add_checksum(self.compose_path, checksum_type=checksum_type, checksum_value=checksum)

            img.implant_md5 = iso.get_implanted_md5(iso_path)
            try:
                img.volume_id = iso.get_volume_id(iso_path)
            except RuntimeError:
                pass

            if arch == "src":
                all_arches = [i for i in self.treeinfo if i != "src"]
            else:
                all_arches = [arch]

            for tree_arch in all_arches:
                if tree_arch.startswith('debug-'):
                    continue
                ti = self.treeinfo[tree_arch]
                for variant_uid in ti.variants:
                    variant = ti.variants[variant_uid]
                    # We don't want to copy the manifest.
                    img.parent = None
                    variant_img = copy.deepcopy(img)
                    variant_img.parent = im
                    variant_img.subvariant = variant.id
                    paths_attr = 'isos' if arch != 'src' else 'source_isos'
                    paths = getattr(self.ci.variants[variant.uid].paths, paths_attr)
                    variant_img.path = os.path.join(
                        paths.get(tree_arch, os.path.join(variant.uid, tree_arch, "iso")),
                        os.path.basename(img.path)
                    )
                    im.add(variant.uid, tree_arch, variant_img)

        im.dump(os.path.join(self.compose_path, 'metadata', 'images.json'))

    def link_to_compose(self):
        for variant in self.ci.get_variants(recursive=False):
            for arch in variant.arches | set(['debug-' + a for a in variant.arches]) | set(['src']):
                bare_arch = arch.split('-', 1)[-1]
                if arch == 'src':
                    dir = 'source'
                elif arch.startswith('debug-'):
                    dir = bare_arch + '/debug'
                else:
                    dir = bare_arch
                default_path = os.path.join(variant.uid, dir, "iso")
                isos = os.path.join(self.compose_path, default_path)
                makedirs(isos)
                for image in self.images.get(arch, []):
                    dst = os.path.join(isos, os.path.basename(image))
                    print("Linking {0} -> {1}".format(image, dst))
                    self.linker.link(image, dst)

    def _get_base_filename(self, variant, arch):
        substs = {
            'compose_id': self.compose.info.compose.id,
            'release_short': self.compose.info.release.short,
            'version': self.compose.info.release.version,
            'date': self.compose.info.compose.date,
            'respin': self.compose.info.compose.respin,
            'type': self.compose.info.compose.type,
            'type_suffix': self.compose.info.compose.type_suffix,
            'label': self.compose.info.compose.label,
            'label_major_version': self.compose.info.compose.label_major_version,
            'variant': variant,
            'arch': arch,
        }
        base_name = self.conf.get('media_checksum_base_filename', '')
        if base_name:
            base_name = (base_name % substs).format(**substs)
            base_name += '-'
        return base_name

    def update_checksums(self):
        for (variant, arch, path), images in get_images(self.compose_path, self.compose.images).iteritems():
            base_checksum_name = self._get_base_filename(variant, arch)
            make_checksums(variant, arch, path, images,
                           self.conf.get('media_checksums', DEFAULT_CHECKSUMS),
                           base_checksum_name,
                           self.conf.get('media_checksum_one_file', False))
