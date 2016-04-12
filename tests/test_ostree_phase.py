#!/usr/bin/env python
# -*- coding: utf-8 -*-


import unittest
import mock

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tests import helpers
from pungi.phases import ostree


class OSTreePhaseTest(helpers.PungiTestCase):

    def test_validate(self):
        compose = helpers.DummyCompose(self.topdir, {
            'ostree': [
                ("^Atomic$", {
                    "x86_64": {
                        "treefile": "fedora-atomic-docker-host.json",
                        "config_url": "https://git.fedorahosted.org/git/fedora-atomic.git",
                        "source_repo_from": "Everything",
                        "ostree_repo": "/mnt/koji/compose/atomic/Rawhide/"
                    }
                })
            ]
        })

        phase = ostree.OSTreePhase(compose)
        try:
            phase.validate()
        except:
            self.fail('Correct config must validate')

    def test_validate_bad_conf(self):
        compose = helpers.DummyCompose(self.topdir, {
            'ostree': 'yes please'
        })

        phase = ostree.OSTreePhase(compose)
        with self.assertRaises(ValueError):
            phase.validate()

    @mock.patch('pungi.phases.ostree.ThreadPool')
    def test_run(self, ThreadPool):
        cfg = mock.Mock()
        compose = helpers.DummyCompose(self.topdir, {
            'ostree': [
                ('^Everything$', {'x86_64': cfg})
            ]
        })

        pool = ThreadPool.return_value

        phase = ostree.OSTreePhase(compose)
        phase.run()

        self.assertEqual(len(pool.add.call_args_list), 1)
        self.assertEqual(pool.queue_put.call_args_list,
                         [mock.call((compose, compose.variants['Everything'], 'x86_64', cfg))])

    @mock.patch('pungi.phases.ostree.ThreadPool')
    def test_skip_without_config(self, ThreadPool):
        compose = helpers.DummyCompose(self.topdir, {})
        compose.just_phases = None
        compose.skip_phases = []
        phase = ostree.OSTreePhase(compose)
        self.assertTrue(phase.skip())


class OSTreeThreadTest(helpers.PungiTestCase):

    def _dummy_config_repo(self, scm_dict, target, logger=None):
        helpers.touch(os.path.join(target, 'fedora-atomic-docker-host.json'))
        helpers.touch(os.path.join(target, 'fedora-rawhide.repo'),
                      'mirrorlist=mirror-mirror-on-the-wall')

    @mock.patch('pungi.wrappers.scm.get_dir_from_scm')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    def test_run(self, KojiWrapper, get_dir_from_scm):
        get_dir_from_scm.side_effect = self._dummy_config_repo

        compose = helpers.DummyCompose(self.topdir, {
            'koji_profile': 'koji',
            'runroot_tag': 'rrt',
            'translate_paths': [
                (self.topdir + '/compose', 'http://example.com')
            ]
        })
        pool = mock.Mock()
        cfg = {
            'source_repo_from': 'Everything',
            'config_url': 'https://git.fedorahosted.org/git/fedora-atomic.git',
            'config_branch': 'f24',
            'treefile': 'fedora-atomic-docker-host.json',
            'ostree_repo': '/other/place/for/atomic'
        }
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.return_value = {
            'task_id': 1234,
            'retcode': 0,
            'output': 'Foo bar\n',
        }

        t = ostree.OSTreeThread(pool)

        t.process((compose, compose.variants['Everything'], 'x86_64', cfg), 1)

        self.assertEqual(get_dir_from_scm.call_args_list,
                         [mock.call({'scm': 'git', 'repo': 'https://git.fedorahosted.org/git/fedora-atomic.git',
                                     'branch': 'f24', 'dir': '.'},
                                    self.topdir + '/work/ostree/config_repo', logger=pool._logger)])
        self.assertEqual(koji.get_runroot_cmd.call_args_list,
                         [mock.call('rrt', 'x86_64',
                                    ['pungi-make-ostree',
                                     '--log-dir={}/logs/x86_64/ostree'.format(self.topdir),
                                     '--treefile={}/fedora-atomic-docker-host.json'.format(
                                         self.topdir + '/work/ostree/config_repo'),
                                     '/other/place/for/atomic'],
                                    channel=None, mounts=[self.topdir, '/other/place/for/atomic'],
                                    packages=['pungi', 'ostree', 'rpm-ostree'],
                                    task_id=True, use_shell=True)])
        self.assertEqual(koji.run_runroot_cmd.call_args_list,
                         [mock.call(koji.get_runroot_cmd.return_value,
                                    log_file=self.topdir + '/logs/x86_64/ostree/runroot.log')])

        with open(self.topdir + '/work/ostree/config_repo/fedora-rawhide.repo') as f:
            self.assertIn('baseurl=http://example.com/Everything/x86_64/os'.format(self.topdir),
                          f.read())

    @mock.patch('pungi.wrappers.scm.get_dir_from_scm')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    def test_run_fail(self, KojiWrapper, get_dir_from_scm):
        get_dir_from_scm.side_effect = self._dummy_config_repo

        compose = helpers.DummyCompose(self.topdir, {
            'koji_profile': 'koji',
            'runroot_tag': 'rrt',
            'failable_deliverables': [
                ('^.*$', {'*': ['ostree']})
            ]
        })
        pool = mock.Mock()
        cfg = {
            'source_repo_from': 'Everything',
            'config_url': 'https://git.fedorahosted.org/git/fedora-atomic.git',
            'config_branch': 'f24',
            'treefile': 'fedora-atomic-docker-host.json',
            'ostree_repo': '/other/place/for/atomic'
        }
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.return_value = {
            'task_id': 1234,
            'retcode': 1,
            'output': 'Foo bar\n',
        }

        t = ostree.OSTreeThread(pool)

        t.process((compose, compose.variants['Everything'], 'x86_64', cfg), 1)

        compose.log_info.assert_has_calls([
            mock.call('[FAIL] Ostree (variant Everything, arch x86_64) failed, but going on anyway.'),
            mock.call('Runroot task failed: 1234. See {} for more details.'.format(
                self.topdir + '/logs/x86_64/ostree/runroot.log'))
        ])

    @mock.patch('pungi.wrappers.scm.get_dir_from_scm')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    def test_run_handle_exception(self, KojiWrapper, get_dir_from_scm):
        get_dir_from_scm.side_effect = self._dummy_config_repo

        compose = helpers.DummyCompose(self.topdir, {
            'koji_profile': 'koji',
            'runroot_tag': 'rrt',
            'failable_deliverables': [
                ('^.*$', {'*': ['ostree']})
            ]
        })
        pool = mock.Mock()
        cfg = {
            'source_repo_from': 'Everything',
            'config_url': 'https://git.fedorahosted.org/git/fedora-atomic.git',
            'config_branch': 'f24',
            'treefile': 'fedora-atomic-docker-host.json',
            'ostree_repo': '/other/place/for/atomic'
        }
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.side_effect = helpers.boom

        t = ostree.OSTreeThread(pool)

        t.process((compose, compose.variants['Everything'], 'x86_64', cfg), 1)

        compose.log_info.assert_has_calls([
            mock.call('[FAIL] Ostree (variant Everything, arch x86_64) failed, but going on anyway.'),
            mock.call('BOOM')
        ])


if __name__ == '__main__':
    unittest.main()