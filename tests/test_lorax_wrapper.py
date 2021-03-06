# -*- coding: utf-8 -*-

try:
    import unittest2 as unittest
except ImportError:
    import unittest

import six

from pungi.wrappers.lorax import LoraxWrapper


class LoraxWrapperTest(unittest.TestCase):
    def setUp(self):
        self.lorax = LoraxWrapper()

    def test_get_command_with_minimal_arguments(self):
        cmd = self.lorax.get_lorax_cmd(
            "product", "version", "release", "/mnt/repo_baseurl", "/mnt/output_dir"
        )

        self.assertEqual(cmd[0], "lorax")
        six.assertCountEqual(
            self,
            cmd[1:],
            [
                "--product=product",
                "--version=version",
                "--release=release",
                "--source=file:///mnt/repo_baseurl",
                "/mnt/output_dir",
            ],
        )

    def test_get_command_with_all_arguments(self):
        cmd = self.lorax.get_lorax_cmd(
            "product",
            "version",
            "release",
            "/mnt/repo_baseurl",
            "/mnt/output_dir",
            variant="Server",
            bugurl="http://example.com/",
            nomacboot=True,
            noupgrade=True,
            is_final=True,
            buildarch="x86_64",
            volid="VOLUME_ID",
            buildinstallpackages=["bash", "vim"],
            add_template=["t1", "t2"],
            add_arch_template=["ta1", "ta2"],
            add_template_var=["v1", "v2"],
            add_arch_template_var=["va1", "va2"],
            log_dir="/tmp",
            dracut_args=["--foo", "bar"],
            squashfs_only=True,
            configuration_file="/storage/RHEL-7.8-20200731.n.0/"
            + "logs/x86_64/buildinstall-Server-logs/lorax.conf",
        )

        self.assertEqual(cmd[0], "lorax")
        six.assertCountEqual(
            self,
            cmd[1:],
            [
                "--product=product",
                "--version=version",
                "--release=release",
                "--variant=Server",
                "--source=file:///mnt/repo_baseurl",
                "--bugurl=http://example.com/",
                "--buildarch=x86_64",
                "--volid=VOLUME_ID",
                "--nomacboot",
                "--noupgrade",
                "--isfinal",
                "--installpkgs=bash",
                "--installpkgs=vim",
                "--add-template=t1",
                "--add-template=t2",
                "--add-arch-template=ta1",
                "--add-arch-template=ta2",
                "--add-template-var=v1",
                "--add-template-var=v2",
                "--add-arch-template-var=va1",
                "--add-arch-template-var=va2",
                "--logfile=/tmp/lorax.log",
                "--dracut-arg=--foo",
                "--dracut-arg=bar",
                "--squashfs-only",
                "--config",
                "/storage/RHEL-7.8-20200731.n.0/"
                + "logs/x86_64/buildinstall-Server-logs/lorax.conf",
                "/mnt/output_dir",
            ],
        )
