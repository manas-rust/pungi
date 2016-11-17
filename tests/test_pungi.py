# -*- coding: utf-8 -*-

try:
    import unittest2 as unittest
except ImportError:
    import unittest


import os
import tempfile
import shutil
import sys
import logging

HERE = os.path.dirname(__file__)
BINDIR = (os.path.join(HERE, '..', 'bin'))
sys.path.insert(0, os.path.join(HERE, '..'))
os.environ['PATH'] = '%s:%s' % (BINDIR, os.environ['PATH'])

from pungi.wrappers.pungi import PungiWrapper


def convert_pkg_map(data):
    """
    Go through the mapping, extract only paths and convert them to just
    basenames.
    """
    result = {}
    for pkg_type in data:
        result[pkg_type] = sorted(set([os.path.basename(pkg['path'])
                                       for pkg in data[pkg_type]]))
    return result


class TestPungi(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="test_compose_")
        self.repo = os.path.join(os.path.dirname(__file__), "fixtures/repos/repo")
        self.lookaside = os.path.join(os.path.dirname(__file__),
                                      "fixtures/repos/repo-krb5-lookaside")
        self.ks = os.path.join(self.tmp_dir, "ks")
        self.out = os.path.join(self.tmp_dir, "out")
        logger = logging.getLogger('Pungi')
        if not logger.handlers:
            formatter = logging.Formatter('%(name)s:%(levelname)s: %(message)s')
            console = logging.StreamHandler(sys.stdout)
            console.setFormatter(formatter)
            console.setLevel(logging.INFO)
            logger.addHandler(console)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def go(self, packages, groups, repo=None, lookaside=None, prepopulate=None,
           multilib_whitelist=None, **kwargs):
        """
        Write a kickstart with given packages and groups, then run the
        depsolving and parse the output.
        """
        p = PungiWrapper()
        repos = {"repo": repo or self.repo}
        if lookaside:
            repos['lookaside'] = lookaside
        p.write_kickstart(self.ks, repos, groups, packages, prepopulate=prepopulate,
                          multilib_whitelist=multilib_whitelist)
        kwargs.setdefault('cache_dir', self.tmp_dir)
        # Unless the test specifies an arch, we need to default to x86_64.
        # Otherwise the arch of current machine will be used, which will cause
        # failure most of the time.
        kwargs.setdefault('arch', 'x86_64')

        p.run_pungi(self.ks, self.tmp_dir, 'DP', **kwargs)
        with open(self.out, "r") as f:
            pkg_map = p.get_packages(f.read())
        return convert_pkg_map(pkg_map)

    def test_kernel(self):
        packages = [
            "dummy-kernel",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("dummy-kernel-3.1.0-1.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-kernel-3.1.0-1.x86_64.rpm",  # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-kernel-3.1.0-1.src.rpm"
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_kernel_fulltree(self):
        packages = [
            "dummy-kernel",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertNotIn("dummy-kernel-3.1.0-1.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-kernel-3.1.0-1.x86_64.rpm",          # Important
            "dummy-kernel-headers-3.1.0-1.x86_64.rpm",
            "dummy-kernel-doc-3.1.0-1.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-kernel-3.1.0-1.src.rpm"
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_kernel_doc_fulltree(self):
        packages = [
            "dummy-kernel-doc",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertNotIn("dummy-kernel-3.1.0-1.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-kernel-3.1.0-1.x86_64.rpm",          # Important
            "dummy-kernel-headers-3.1.0-1.x86_64.rpm",
            "dummy-kernel-doc-3.1.0-1.noarch.rpm",      # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-kernel-3.1.0-1.src.rpm"
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_bash_noarch_pulls_64bit(self):
        packages = [
            "dummy-glibc.+",
            "dummy-bash-doc",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=False, arch="ppc64")

        self.assertNotIn("dummy-bash-4.2.37-6.ppc.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.ppc64.rpm",            # Important
            "dummy-bash-doc-4.2.37-6.noarch.rpm",       # Important
            "dummy-filesystem-4.2.37-6.ppc64.rpm",
            "dummy-glibc-2.14-5.ppc.rpm",
            "dummy-glibc-2.14-5.ppc64.rpm",
            "dummy-glibc-common-2.14-5.ppc64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.ppc64.rpm",
            "dummy-glibc-debuginfo-2.14-5.ppc.rpm",
            "dummy-glibc-debuginfo-2.14-5.ppc64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.ppc.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.ppc64.rpm",
        ])

    def test_foo32_doc_fulltree(self):
        packages = [
            "dummy-foo32-doc",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-foo32-1-1.i686.rpm",                 # Important
            "dummy-foo32-doc-1-1.noarch.rpm",           # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-foo32-1-1.src.rpm"
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_bash(self):
        packages = [
            "dummy-bash",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("dummy-bash-4.2.37-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-5.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.x86_64.rpm",           # Important
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_s390x(self):
        packages = [
            "dummy-bash",
        ]
        pkg_map = self.go(packages, None, greedy="none", arch="s390x")

        self.assertNotIn("dummy-bash-4.2.37-5.s390.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-5.s390x.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.s390.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.s390x.rpm",            # Important
            "dummy-filesystem-4.2.37-6.s390x.rpm",
            "dummy-glibc-2.14-5.s390x.rpm",
            "dummy-glibc-common-2.14-5.s390x.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.s390x.rpm",
            "dummy-glibc-debuginfo-2.14-5.s390x.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.s390x.rpm",
        ])

    def test_bash_greedy(self):
        # we want only the latest package version
        packages = [
            "dummy-bash",
        ]
        pkg_map = self.go(packages, None, greedy="all")

        self.assertNotIn("dummy-bash-4.2.37-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-5.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",             # Important
            "dummy-bash-4.2.37-6.x86_64.rpm",           # Important
            "dummy-filesystem-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.i686.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.i686.rpm",
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_older(self):
        packages = [
            "dummy-bash-4.2.37-5",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("dummy-bash-4.2.37-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-5.x86_64.rpm",           # Important
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-5.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-5.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_system_release(self):
        packages = [
            "dummy-filesystem",
            "system-release",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("dummy-release-client-workstation-1.0.0-1.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-release-client-workstation-1.0.0-1.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-release-client-1.0.0-1.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-release-client-1.0.0-1.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-release-server-1.0.0-1.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-release-server-1.0.0-1.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-release-notes-1.2-1.noarch.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-filesystem-4.2.37-6.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_system_release_greedy(self):
        packages = [
            "system-release",
        ]
        pkg_map = self.go(packages, None, greedy="all")

        self.assertNotIn("dummy-release-notes-1.2-1.noarch.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-release-client-1.0.0-1.i686.rpm",                # Important
            "dummy-release-client-1.0.0-1.x86_64.rpm",              # Important
            "dummy-release-client-workstation-1.0.0-1.i686.rpm",    # Important
            "dummy-release-client-workstation-1.0.0-1.x86_64.rpm",  # Important
            "dummy-release-server-1.0.0-1.i686.rpm",                # Important
            "dummy-release-server-1.0.0-1.x86_64.rpm",              # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-release-client-1.0.0-1.src.rpm",
            "dummy-release-client-workstation-1.0.0-1.src.rpm",
            "dummy-release-server-1.0.0-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_smtpdaemon(self):
        packages = [
            "dummy-vacation",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("dummy-postfix-2.9.2-2.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-sendmail-8.14.5-12.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-sendmail-8.14.5-12.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-postfix-2.9.2-2.x86_64.rpm",             # Important
            "dummy-vacation-1.2.7.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-postfix-2.9.2-2.src.rpm",
            "dummy-vacation-1.2.7.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-postfix-debuginfo-2.9.2-2.x86_64.rpm",
            "dummy-vacation-debuginfo-1.2.7.1-1.x86_64.rpm",
        ])

    def test_smtpdaemon_sendmail(self):
        packages = [
            "dummy-vacation",
            "dummy-sendmail",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("dummy-postfix-2.9.2-2.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-postfix-2.9.2-2.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-sendmail-8.14.5-12.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-sendmail-8.14.5-12.x86_64.rpm",          # Important
            "dummy-vacation-1.2.7.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-sendmail-8.14.5-12.src.rpm",
            "dummy-vacation-1.2.7.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-sendmail-debuginfo-8.14.5-12.x86_64.rpm",
            "dummy-vacation-debuginfo-1.2.7.1-1.x86_64.rpm",
        ])

    def test_smtpdaemon_greedy(self):
        packages = [
            "dummy-vacation",
        ]
        pkg_map = self.go(packages, None, greedy="all")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.i686.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-postfix-2.9.2-2.i686.rpm",               # Important
            "dummy-postfix-2.9.2-2.x86_64.rpm",             # Important
            "dummy-sendmail-8.14.5-12.i686.rpm",            # Important
            "dummy-sendmail-8.14.5-12.x86_64.rpm",          # Important
            "dummy-vacation-1.2.7.1-1.i686.rpm",
            "dummy-vacation-1.2.7.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-postfix-2.9.2-2.src.rpm",
            "dummy-sendmail-8.14.5-12.src.rpm",
            "dummy-vacation-1.2.7.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-postfix-debuginfo-2.9.2-2.i686.rpm",
            "dummy-postfix-debuginfo-2.9.2-2.x86_64.rpm",
            "dummy-sendmail-debuginfo-8.14.5-12.i686.rpm",
            "dummy-sendmail-debuginfo-8.14.5-12.x86_64.rpm",
            "dummy-vacation-debuginfo-1.2.7.1-1.i686.rpm",
            "dummy-vacation-debuginfo-1.2.7.1-1.x86_64.rpm",
        ])

    def test_firefox(self):
        packages = [
            "Dummy-firefox",
        ]
        pkg_map = self.go(packages, None, greedy="none")

        self.assertNotIn("Dummy-firefox-16.0.1-1.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-devel-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-devel-1.10-5.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-16.0.1-1.x86_64.rpm",            # Important
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-16.0.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "Dummy-firefox-16.0.1-1.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "Dummy-xulrunner-16.0.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "Dummy-firefox-debuginfo-16.0.1-1.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-debuginfo-16.0.1-1.x86_64.rpm",
        ])

    def test_firefox_selfhosting(self):
        packages = [
            "Dummy-firefox",
        ]
        pkg_map = self.go(packages, None, greedy="none", selfhosting=True)

        self.assertNotIn("Dummy-firefox-16.0.1-2.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-devel-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-bash-4.2.37-6.x86_64.rpm",
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-16.0.1-1.x86_64.rpm",            # Important
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-krb5-1.10-5.x86_64.rpm",
            "dummy-krb5-devel-1.10-5.x86_64.rpm",           # Important
            "dummy-krb5-libs-1.10-5.x86_64.rpm",
            "Dummy-xulrunner-16.0.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "Dummy-firefox-16.0.1-1.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-krb5-1.10-5.src.rpm",
            "Dummy-xulrunner-16.0.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-debuginfo-16.0.1-1.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",          # Important
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",   # Important
            "dummy-krb5-debuginfo-1.10-5.x86_64.rpm",
            "Dummy-xulrunner-debuginfo-16.0.1-1.x86_64.rpm",
        ])

    def test_firefox_selfhosting_with_krb5_lookaside(self):
        packages = [
            "Dummy-firefox",
        ]
        pkg_map = self.go(packages, None, lookaside=self.lookaside,
                          greedy="none", selfhosting=True,
                          lookaside_repos=["lookaside"])

        self.assertNotIn("Dummy-firefox-16.0.1-2.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-1.10-5.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-debuginfo-1.10-5.x86_64.rpm", pkg_map["debuginfo"])
        self.assertNotIn("dummy-krb5-1.10-5.src.rpm", pkg_map["srpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-bash-4.2.37-6.x86_64.rpm",
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-16.0.1-1.x86_64.rpm",            # Important
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-16.0.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "Dummy-firefox-16.0.1-1.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "Dummy-xulrunner-16.0.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-debuginfo-16.0.1-1.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-debuginfo-16.0.1-1.x86_64.rpm",
        ])

    def test_firefox_fulltree(self):
        packages = [
            "Dummy-firefox",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertNotIn("Dummy-firefox-16.0.1-2.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-devel-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-devel-1.10-5.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-16.0.1-1.x86_64.rpm",            # Important
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-nscd-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-16.0.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "Dummy-firefox-16.0.1-1.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "Dummy-xulrunner-16.0.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "Dummy-firefox-debuginfo-16.0.1-1.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-debuginfo-16.0.1-1.x86_64.rpm",
        ])

    def test_firefox_selfhosting_fulltree(self):
        packages = [
            "Dummy-firefox",
        ]
        pkg_map = self.go(packages, None, greedy="none", selfhosting=True, fulltree=True)

        self.assertNotIn("Dummy-firefox-16.0.1-2.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-devel-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-bash-4.2.37-6.x86_64.rpm",
            "dummy-bash-doc-4.2.37-6.noarch.rpm",
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-16.0.1-1.x86_64.rpm",            # Important
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-krb5-1.10-5.x86_64.rpm",
            "dummy-krb5-devel-1.10-5.x86_64.rpm",           # Important
            "dummy-krb5-libs-1.10-5.x86_64.rpm",
            "dummy-krb5-workstation-1.10-5.x86_64.rpm",     # Important
            "dummy-nscd-2.14-5.x86_64.rpm",
            "Dummy-xulrunner-16.0.1-1.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "Dummy-firefox-16.0.1-1.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-krb5-1.10-5.src.rpm",
            "Dummy-xulrunner-16.0.1-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "Dummy-firefox-debuginfo-16.0.1-1.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-krb5-debuginfo-1.10-5.x86_64.rpm",
            "Dummy-xulrunner-debuginfo-16.0.1-1.x86_64.rpm",
        ])

    def test_krb5_fulltree(self):
        packages = [
            "dummy-krb5",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertNotIn("dummy-krb5-devel-1.10-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-krb5-workstation-1.10-5.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-krb5-1.10-5.x86_64.rpm",
            "dummy-krb5-devel-1.10-5.x86_64.rpm",           # Important
            "dummy-krb5-libs-1.10-5.x86_64.rpm",
            "dummy-krb5-workstation-1.10-5.x86_64.rpm",     # Important
            "dummy-nscd-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-krb5-1.10-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-krb5-debuginfo-1.10-5.x86_64.rpm",
        ])

    def test_bash_multilib(self):
        packages = [
            "dummy-bash.+",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        # 'dummy-bash' req already satisfied by bash.i686
        self.assertNotIn("dummy-bash-4.2.37-6.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",             # Important
            "dummy-bash-doc-4.2.37-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-nscd-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_multilib_exclude(self):
        # test if excluding a package really works
        # NOTE: dummy-bash-doc would pull x86_64 bash in (we want noarch pulling 64bit deps in composes)
        packages = [
            "dummy-bash.+",
            "-dummy-bash-doc",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertNotIn("dummy-bash-4.2.37-6.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-doc-4.2.37-6.noarch.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",             # Important
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-nscd-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_multilib_greedy(self):
        packages = [
            "dummy-bash.+",
        ]
        pkg_map = self.go(packages, None, greedy="all", fulltree=True)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",             # Important
            "dummy-bash-4.2.37-6.x86_64.rpm",           # Important
            "dummy-bash-doc-4.2.37-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.i686.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-nscd-2.14-5.i686.rpm",
            "dummy-nscd-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.i686.rpm",
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    @unittest.skip('This test is broken')
    def test_bash_multilib_nogreedy(self):
        packages = [
            "dummy-bash.+",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertNotIn("dummy-bash-4.2.37-6.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",             # Important
            "dummy-bash-doc-4.2.37-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            # "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            # "dummy-glibc-common-2.14-5.i686.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.i686.rpm",
            # "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            # "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_multilib_filter_greedy(self):
        packages = [
            "dummy-bash",
            "-dummy-bash.+",
        ]
        pkg_map = self.go(packages, None, greedy="all", fulltree=True)

        self.assertNotIn("dummy-bash-4.2.37-6.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.x86_64.rpm",           # Important
            "dummy-bash-doc-4.2.37-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.i686.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-nscd-2.14-5.i686.rpm",
            "dummy-nscd-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_bash_filter_greedy(self):
        packages = [
            "dummy-filesystem",
            "dummy-bash.+",
            "-dummy-bash",
        ]
        pkg_map = self.go(packages, None, greedy="all", fulltree=True)

        self.assertNotIn("dummy-bash-4.2.37-6.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.x86_64.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-filesystem-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-filesystem-4.2.37-6.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_ipw3945_kmod(self):
        # every package name is different
        packages = [
            "dummy-kmod-ipw3945",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=True)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-kmod-ipw3945-1.2.0-4.20.x86_64.rpm",         # Important
            "dummy-kmod-ipw3945-xen-1.2.0-4.20.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-ipw3945-kmod-1.2.0-4.20.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-ipw3945-kmod-debuginfo-1.2.0-4.20.x86_64.rpm",
        ])

    def test_multilib_method_devel(self):
        packages = [
            "dummy-lvm2-devel",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=False,
                          multilib_methods=["devel"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-lvm2-2.02.84-4.x86_64.rpm",
            "dummy-lvm2-devel-2.02.84-4.i686.rpm",          # Important
            "dummy-lvm2-devel-2.02.84-4.x86_64.rpm",        # Important
            "dummy-lvm2-libs-2.02.84-4.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-lvm2-2.02.84-4.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-lvm2-debuginfo-2.02.84-4.i686.rpm",
            "dummy-lvm2-debuginfo-2.02.84-4.x86_64.rpm",
        ])

    def test_selinux_policy_base(self):
        packages = [
            "dummy-freeipa-server",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=False, arch="ppc64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-freeipa-server-2.2.0-1.ppc64.rpm",           # Important
            "dummy-selinux-policy-mls-3.10.0-121.noarch.rpm",   # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-freeipa-2.2.0-1.src.rpm",
            "dummy-selinux-policy-3.10.0-121.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_selinux_policy_base_greedy_build(self):
        packages = [
            "dummy-freeipa-server",
        ]
        pkg_map = self.go(packages, None, greedy="build", fulltree=False, arch="ppc64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-freeipa-server-2.2.0-1.ppc64.rpm",               # Important
            "dummy-selinux-policy-minimal-3.10.0-121.noarch.rpm",
            "dummy-selinux-policy-mls-3.10.0-121.noarch.rpm",       # Important
            "dummy-selinux-policy-targeted-3.10.0-121.noarch.rpm"
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-freeipa-2.2.0-1.src.rpm",
            "dummy-selinux-policy-3.10.0-121.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_selinux_policy_base_existing_provides(self):
        packages = [
            "dummy-selinux-policy-targeted",
            "dummy-freeipa-server",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=False, arch="ppc64")

        self.assertNotIn("dummy-selinux-policy-mls-3.10.0-121.noarch.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-freeipa-server-2.2.0-1.ppc64.rpm",               # Important
            "dummy-selinux-policy-targeted-3.10.0-121.noarch.rpm",  # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-freeipa-2.2.0-1.src.rpm",
            "dummy-selinux-policy-3.10.0-121.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_selinux_policy_doc_fulltree(self):
        packages = [
            "dummy-selinux-policy-doc"
        ]
        pkg_map = self.go(packages, None, fulltree=True)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-selinux-policy-doc-3.10.0-121.noarch.rpm",
            "dummy-selinux-policy-minimal-3.10.0-121.noarch.rpm",
            "dummy-selinux-policy-mls-3.10.0-121.noarch.rpm",
            "dummy-selinux-policy-targeted-3.10.0-121.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-selinux-policy-3.10.0-121.src.rpm"
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_AdobeReader_enu_nosrc(self):
        packages = [
            "dummy-AdobeReader_enu",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=False, arch="x86_64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-AdobeReader_enu-9.5.1-1.i486.rpm",       # Important
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-AdobeReader_enu-9.5.1-1.nosrc.rpm",
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_imsettings(self):
        packages = [
            "dummy-imsettings",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=False, arch="x86_64")

        self.assertNotIn("dummy-imsettings-gnome-1.2.9-1.x86_64.rpm", pkg_map["rpm"])
        # prefers qt over gnome (shorter name)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-imsettings-1.2.9-1.x86_64.rpm",          # Important
            "dummy-imsettings-qt-1.2.9-1.x86_64.rpm",       # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-imsettings-1.2.9-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_imsettings_basic_desktop(self):
        packages = [
            "dummy-imsettings",
        ]
        groups = [
            "basic-desktop"
        ]
        pkg_map = self.go(packages, groups, greedy="none", fulltree=False, arch="x86_64")

        self.assertNotIn("dummy-imsettings-qt-1.2.9-1.x86_64.rpm", pkg_map["rpm"])
        # prefers gnome over qt (condrequires in @basic-desktop)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-imsettings-1.2.9-1.x86_64.rpm",          # Important
            "dummy-imsettings-gnome-1.2.9-1.x86_64.rpm",    # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-imsettings-1.2.9-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_imsettings_basic_desktop_nodeps(self):
        packages = [
            "dummy-imsettings",
        ]
        groups = [
            "basic-desktop"
        ]
        pkg_map = self.go(packages, groups, greedy="none", fulltree=False, nodeps=True,
                          arch="x86_64")

        self.assertNotIn("dummy-imsettings-gnome-1.2.9-1.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-imsettings-qt-1.2.9-1.x86_64.rpm", pkg_map["rpm"])
        # prefers gnome over qt (condrequires in @basic-desktop)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-imsettings-1.2.9-1.x86_64.rpm",          # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-imsettings-1.2.9-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_imsettings_basic_desktop_and_qt(self):
        packages = [
            "dummy-imsettings",
            "dummy-imsettings-qt",
        ]
        groups = [
            "basic-desktop"
        ]
        pkg_map = self.go(packages, groups, greedy="none", fulltree=False, arch="x86_64")

        # prefers gnome over qt (condrequires in @basic-desktop)
        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-imsettings-1.2.9-1.x86_64.rpm",          # Important
            "dummy-imsettings-gnome-1.2.9-1.x86_64.rpm",    # Important
            "dummy-imsettings-qt-1.2.9-1.x86_64.rpm",       # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-imsettings-1.2.9-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_bash_nodeps(self):
        packages = [
            "dummy-bash",
        ]
        pkg_map = self.go(packages, None, greedy="none", nodeps=True)

        self.assertNotIn("dummy-bash-4.2.37-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-5.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-bash-4.2.37-6.x86_64.rpm",           # Important
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-bash-4.2.37-6.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
        ])

    def test_bash_fulltree_nodeps(self):
        packages = [
            "dummy-bash",
        ]
        pkg_map = self.go(packages, None, greedy="none", nodeps=True, fulltree=True)

        self.assertNotIn("dummy-bash-4.2.37-5.i686.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-5.x86_64.rpm", pkg_map["rpm"])
        self.assertNotIn("dummy-bash-4.2.37-6.i686.rpm", pkg_map["rpm"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-bash-4.2.37-6.x86_64.rpm",           # Important
            "dummy-bash-doc-4.2.37-6.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-bash-4.2.37-6.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.x86_64.rpm",
        ])

    def test_lookaside_empty(self):
        # if the input repo and lookaside repo are the same, output must be empty
        packages = [
            "*",
        ]
        pkg_map = self.go(packages, None, lookaside=self.repo,
                          greedy="none", nodeps=True, fulltree=True,
                          lookaside_repos=["lookaside"])

        self.assertItemsEqual(pkg_map["rpm"], [])
        self.assertItemsEqual(pkg_map["srpm"], [])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_exclude_wildcards(self):
        packages = [
            "dummy-bash",
            "-dummy-bas*",
            "dummy-glibc",
        ]
        pkg_map = self.go(packages, None, lookaside=self.repo,
                          greedy="none", nodeps=True, fulltree=True)

        # neither dummy-bash or dummy-basesystem is pulled in
        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-nscd-2.14-5.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-glibc-2.14-5.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_atlas_greedy_none(self):
        packages = [
            "dummy-atlas-devel",
        ]
        pkg_map = self.go(packages, None, greedy="none", fulltree=False, arch="x86_64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-atlas-3.8.4-7.x86_64.rpm",
            "dummy-atlas-devel-3.8.4-7.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-atlas-3.8.4-7.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_atlas_greedy_build(self):
        packages = [
            "dummy-atlas",
            "dummy-atlas-devel",
        ]
        pkg_map = self.go(packages, None, greedy="build", fulltree=False, arch="x86_64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-atlas-3.8.4-7.x86_64.rpm",
            "dummy-atlas-devel-3.8.4-7.x86_64.rpm",
            "dummy-atlas-sse3-3.8.4-7.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-atlas-3.8.4-7.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_atlas_greedy_build_multilib_devel(self):
        packages = [
            "dummy-atlas-devel",
        ]
        pkg_map = self.go(packages, None, greedy="build", multilib_methods=["devel"],
                          fulltree=False, arch="x86_64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-atlas-3.8.4-7.x86_64.rpm",
            "dummy-atlas-devel-3.8.4-7.i686.rpm",
            "dummy-atlas-devel-3.8.4-7.x86_64.rpm",
            "dummy-atlas-sse3-3.8.4-7.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-atlas-3.8.4-7.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_atlas_greedy_build_multilib_devel_32bit(self):
        packages = [
            "dummy-atlas-devel.+",
        ]
        pkg_map = self.go(packages, None, greedy="build", multilib_methods=["devel"],
                          fulltree=False, arch="x86_64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-atlas-3.8.4-7.x86_64.rpm",
            "dummy-atlas-devel-3.8.4-7.i686.rpm",
            "dummy-atlas-sse3-3.8.4-7.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-atlas-3.8.4-7.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_atlas_greedy_all(self):
        packages = [
            "dummy-atlas-devel",
        ]
        pkg_map = self.go(packages, None, greedy="all", fulltree=False, arch="x86_64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-atlas-3.8.4-7.i686.rpm",
            "dummy-atlas-3dnow-3.8.4-7.i686.rpm",
            "dummy-atlas-devel-3.8.4-7.i686.rpm",
            "dummy-atlas-sse-3.8.4-7.i686.rpm",
            "dummy-atlas-sse2-3.8.4-7.i686.rpm",
            "dummy-atlas-sse3-3.8.4-7.i686.rpm",

            "dummy-atlas-3.8.4-7.x86_64.rpm",
            "dummy-atlas-devel-3.8.4-7.x86_64.rpm",
            "dummy-atlas-sse3-3.8.4-7.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-atlas-3.8.4-7.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_skype(self):
        packages = [
            "dummy-skype",
        ]
        pkg_map = self.go(packages, None, greedy="build", fulltree=False, arch="x86_64")

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-skype-4.2.0.13-1.i586.rpm",
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
        ])
        # no SRPM for skype
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
        ])

    def test_prepopulate(self):
        packages = [
            "dummy-glibc",
        ]
        prepopulate = [
            "dummy-bash.i686",
            "dummy-lvm2.x86_64",
        ]

        pkg_map = self.go(packages, None, prepopulate=prepopulate)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-basesystem-10.0-6.noarch.rpm",
            "dummy-bash-4.2.37-6.i686.rpm",
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-lvm2-2.02.84-4.x86_64.rpm",
            "dummy-lvm2-libs-2.02.84-4.x86_64.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-bash-4.2.37-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
            "dummy-lvm2-2.02.84-4.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-bash-debuginfo-4.2.37-6.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
            "dummy-lvm2-debuginfo-2.02.84-4.x86_64.rpm",
        ])

    def test_langpacks(self):
        packages = [
            "dummy-release-notes",
        ]
        pkg_map = self.go(packages, None)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-release-notes-1.2-1.noarch.rpm",
            "dummy-release-notes-cs-CZ-1.2-1.noarch.rpm",
            "dummy-release-notes-en-US-1.2-1.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-release-notes-1.2-1.src.rpm",
            "dummy-release-notes-cs-CZ-1.2-1.src.rpm",
            "dummy-release-notes-en-US-1.2-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [])

    def test_multilib_whitelist(self):
        # whitelist must work regardless if multilib_method is specified or not
        packages = [
            "dummy-glibc",
        ]

        pkg_map = self.go(packages, None, multilib_whitelist=["dummy-glibc"])

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-filesystem-4.2.37-6.x86_64.rpm",
            "dummy-glibc-common-2.14-5.x86_64.rpm",
            "dummy-glibc-2.14-5.i686.rpm",
            "dummy-glibc-2.14-5.x86_64.rpm",
            "dummy-basesystem-10.0-6.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-basesystem-10.0-6.src.rpm",
            "dummy-glibc-2.14-5.src.rpm",
            "dummy-filesystem-4.2.37-6.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-glibc-debuginfo-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-2.14-5.x86_64.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.i686.rpm",
            "dummy-glibc-debuginfo-common-2.14-5.x86_64.rpm",
        ])

    def test_noarch_debuginfo(self):
        packages = [
            "dummy-mingw32-qt5-qtbase",
        ]
        pkg_map = self.go(packages, None)

        self.assertItemsEqual(pkg_map["rpm"], [
            "dummy-mingw32-qt5-qtbase-5.6.0-1.noarch.rpm",
        ])
        self.assertItemsEqual(pkg_map["srpm"], [
            "dummy-mingw-qt5-qtbase-5.6.0-1.src.rpm",
        ])
        self.assertItemsEqual(pkg_map["debuginfo"], [
            "dummy-mingw32-qt5-qtbase-debuginfo-5.6.0-1.noarch.rpm",
        ])


if __name__ == "__main__":
    unittest.main()