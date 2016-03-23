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
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.


import os

from kobo.shortcuts import force_list
from ..util import process_args


class LoraxWrapper(object):
    def get_lorax_cmd(self, product, version, release, repo_baseurl, output_dir,
                      variant=None, bugurl=None, nomacboot=False, noupgrade=False,
                      is_final=False, buildarch=None, volid=None, buildinstallpackages=None,
                      add_template=None, add_arch_template=None,
                      add_template_var=None, add_arch_template_var=None):
        cmd = ["lorax"]
        cmd.append("--product=%s" % product)
        cmd.append("--version=%s" % version)
        cmd.append("--release=%s" % release)

        for i in force_list(repo_baseurl):
            if "://" not in i:
                i = "file://%s" % os.path.abspath(i)
            cmd.append("--source=%s" % i)

        if variant is not None:
            cmd.append("--variant=%s" % variant)

        if bugurl is not None:
            cmd.append("--bugurl=%s" % bugurl)

        if nomacboot:
            cmd.append("--nomacboot")

        if noupgrade:
            cmd.append("--noupgrade")

        if is_final:
            cmd.append("--isfinal")

        if buildarch:
            cmd.append("--buildarch=%s" % buildarch)

        if volid:
            cmd.append("--volid=%s" % volid)

        cmd.extend(process_args('--installpkgs={}', buildinstallpackages))
        cmd.extend(process_args('--add-template={}', add_template))
        cmd.extend(process_args('--add-arch-template={}', add_arch_template))
        cmd.extend(process_args('--add-template-var={}', add_template_var))
        cmd.extend(process_args('--add-arch-template-var={}', add_arch_template_var))

        output_dir = os.path.abspath(output_dir)
        cmd.append(output_dir)

        # TODO: workdir

        return cmd

    def get_buildinstall_cmd(self, product, version, release, repo_baseurl, output_dir, variant=None, bugurl=None, nomacboot=False, noupgrade=False, is_final=False, buildarch=None, volid=None, brand=None):
        # RHEL 6 compatibility
        # Usage: buildinstall [--debug] --version <version> --brand <brand> --product <product> --release <comment> --final [--output outputdir] [--discs <discstring>] <root>

        brand = brand or "redhat"
        # HACK: ignore provided release
        release = "%s %s" % (brand, version)
        bugurl = bugurl or "https://bugzilla.redhat.com"

        cmd = ["/usr/lib/anaconda-runtime/buildinstall"]

        cmd.append("--debug")

        cmd.extend(["--version", version])
        cmd.extend(["--brand", brand])
        cmd.extend(["--product", product])
        cmd.extend(["--release", release])

        if is_final:
            cmd.append("--final")

        if buildarch:
            cmd.extend(["--buildarch", buildarch])

        if bugurl:
            cmd.extend(["--bugurl", bugurl])

        output_dir = os.path.abspath(output_dir)
        cmd.extend(["--output", output_dir])

        for i in force_list(repo_baseurl):
            if "://" not in i:
                i = "file://%s" % os.path.abspath(i)
            cmd.append(i)

        return cmd
