# -*- coding: utf-8 -*-

try:
    import unittest2 as unittest
except ImportError:
    import unittest

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.wrappers import repoclosure as rc


class RepoclosureWrapperTestCase(unittest.TestCase):
    def test_minimal_command(self):
        self.assertEqual(rc.get_repoclosure_cmd(),
                         ['/usr/bin/repoclosure'])

    def test_minimal_dnf_command(self):
        self.assertEqual(rc.get_repoclosure_cmd(backend='dnf'),
                         ['dnf', 'repoclosure'])

    def test_unknown_backend(self):
        with self.assertRaises(RuntimeError) as ctx:
            rc.get_repoclosure_cmd(backend='rpm')

        self.assertEqual(str(ctx.exception), 'Unknown repoclosure backend: rpm')

    def test_multiple_arches(self):
        self.assertEqual(rc.get_repoclosure_cmd(arch=['x86_64', 'ppc64']),
                         ['/usr/bin/repoclosure', '--arch=x86_64', '--arch=ppc64'])

    def test_full_command(self):
        repos = {'my-repo': '/mnt/koji/repo'}
        lookaside = {'fedora': 'http://kojipkgs.fp.o/repo'}

        cmd = rc.get_repoclosure_cmd(arch='x86_64', builddeps=True,
                                     repos=repos, lookaside=lookaside)
        self.assertEqual(cmd[0], '/usr/bin/repoclosure')
        self.assertItemsEqual(
            cmd[1:],
            ['--arch=x86_64',
             '--builddeps',
             '--repofrompath=my-repo,file:///mnt/koji/repo',
             '--repofrompath=fedora,http://kojipkgs.fp.o/repo',
             '--repoid=my-repo',
             '--lookaside=fedora'])

    def test_full_dnf_command(self):
        repos = {'my-repo': '/mnt/koji/repo'}
        lookaside = {'fedora': 'http://kojipkgs.fp.o/repo'}

        cmd = rc.get_repoclosure_cmd(backend='dnf', arch='x86_64',
                                     repos=repos, lookaside=lookaside)
        self.assertEqual(cmd[:2], ['dnf', 'repoclosure'])
        self.assertItemsEqual(
            cmd[2:],
            ['--arch=x86_64',
             '--repofrompath=my-repo,file:///mnt/koji/repo',
             '--repofrompath=fedora,http://kojipkgs.fp.o/repo',
             '--repo=my-repo',
             '--check=my-repo',
             '--repo=fedora'])

    def test_expand_repo(self):
        repos = {
            'local': '/mnt/koji/repo',
            'remote': 'http://kojipkgs.fp.o/repo',
        }
        cmd = rc.get_repoclosure_cmd(repos=repos)
        self.assertEqual(cmd[0], '/usr/bin/repoclosure')
        self.assertItemsEqual(
            cmd[1:],
            ['--repofrompath=local,file:///mnt/koji/repo',
             '--repofrompath=remote,http://kojipkgs.fp.o/repo',
             '--repoid=local',
             '--repoid=remote'])

    def test_expand_lookaside(self):
        repos = {
            'local': '/mnt/koji/repo',
            'remote': 'http://kojipkgs.fp.o/repo',
        }
        cmd = rc.get_repoclosure_cmd(lookaside=repos)
        self.assertEqual(cmd[0], '/usr/bin/repoclosure')
        self.assertItemsEqual(
            cmd[1:],
            ['--repofrompath=local,file:///mnt/koji/repo',
             '--repofrompath=remote,http://kojipkgs.fp.o/repo',
             '--lookaside=local',
             '--lookaside=remote'])
