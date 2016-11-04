#!/usr/bin/env python
# -*- coding: utf-8 -*-


import json
import unittest
import mock

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tests import helpers
from pungi.phases import ostree


class OSTreePhaseTest(helpers.PungiTestCase):

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

    def setUp(self):
        super(OSTreeThreadTest, self).setUp()
        self.repo = os.path.join(self.topdir, 'place/for/atomic')
        os.makedirs(os.path.join(self.repo, 'refs', 'heads'))
        self.cfg = {
            'source_repo_from': 'Everything',
            'config_url': 'https://git.fedorahosted.org/git/fedora-atomic.git',
            'config_branch': 'f24',
            'treefile': 'fedora-atomic-docker-host.json',
            'ostree_repo': self.repo
        }
        self.compose = helpers.DummyCompose(self.topdir, {
            'koji_profile': 'koji',
            'runroot_tag': 'rrt',
            'translate_paths': [
                (self.topdir + '/compose', 'http://example.com')
            ]
        })
        self.pool = mock.Mock()

    def _dummy_config_repo(self, scm_dict, target, logger=None):
        os.makedirs(target)
        helpers.touch(os.path.join(target, 'fedora-atomic-docker-host.json'),
                      json.dumps({'ref': 'fedora-atomic/25/x86_64'}))
        helpers.touch(os.path.join(target, 'fedora-rawhide.repo'),
                      'mirrorlist=mirror-mirror-on-the-wall')
        helpers.touch(os.path.join(target, 'fedora-24.repo'),
                      'metalink=who-is-the-fairest-of-them-all')
        helpers.touch(os.path.join(target, 'fedora-23.repo'),
                      'baseurl=why-not-zoidberg?')

    def _mock_runroot(self, retcode, writefiles=None):
        """Pretend to run a task in runroot, creating a log file with given line

        Also allows for writing other files of requested"""
        def fake_runroot(self, log_file, **kwargs):
            if writefiles:
                logdir = os.path.dirname(log_file)
                for filename in writefiles:
                    helpers.touch(os.path.join(logdir, filename),
                                  '\n'.join(writefiles[filename]))
            return {'task_id': 1234, 'retcode': retcode, 'output': 'Foo bar\n'}
        return fake_runroot

    @mock.patch('pungi.wrappers.scm.get_dir_from_scm')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    def test_run(self, KojiWrapper, get_dir_from_scm):
        get_dir_from_scm.side_effect = self._dummy_config_repo

        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.side_effect = self._mock_runroot(0)

        t = ostree.OSTreeThread(self.pool)

        t.process((self.compose, self.compose.variants['Everything'], 'x86_64', self.cfg), 1)

        self.assertEqual(get_dir_from_scm.call_args_list,
                         [mock.call({'scm': 'git', 'repo': 'https://git.fedorahosted.org/git/fedora-atomic.git',
                                     'branch': 'f24', 'dir': '.'},
                                    self.topdir + '/work/ostree-1/config_repo', logger=self.pool._logger)])
        self.assertEqual(koji.get_runroot_cmd.call_args_list,
                         [mock.call('rrt', 'x86_64',
                                    ['pungi-make-ostree',
                                     '--log-dir=%s/logs/x86_64/Everything/ostree-1' % self.topdir,
                                     '--treefile=%s/fedora-atomic-docker-host.json' % (
                                         self.topdir + '/work/ostree-1/config_repo'),
                                     self.repo],
                                    channel=None, mounts=[self.topdir, self.repo],
                                    packages=['pungi', 'ostree', 'rpm-ostree'],
                                    task_id=True, use_shell=True, new_chroot=True)])
        self.assertEqual(koji.run_runroot_cmd.call_args_list,
                         [mock.call(koji.get_runroot_cmd.return_value,
                                    log_file=self.topdir + '/logs/x86_64/Everything/ostree-1/runroot.log')])

        for fp in ['fedora-rawhide.repo', 'fedora-24.repo', 'fedora-24.repo']:
            with open(os.path.join(self.topdir, 'work/ostree-1/config_repo', fp)) as f:
                self.assertIn('baseurl=http://example.com/Everything/$basearch/os',
                              f.read())
        self.assertTrue(os.path.isdir(self.repo))

    @mock.patch('pungi.wrappers.scm.get_dir_from_scm')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    def test_run_fail(self, KojiWrapper, get_dir_from_scm):
        get_dir_from_scm.side_effect = self._dummy_config_repo

        self.cfg['failable'] = ['*']
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.side_effect = self._mock_runroot(1)

        t = ostree.OSTreeThread(self.pool)

        t.process((self.compose, self.compose.variants['Everything'], 'x86_64', self.cfg), 1)

        self.compose.log_info.assert_has_calls([
            mock.call('[FAIL] Ostree (variant Everything, arch x86_64) failed, but going on anyway.'),
            mock.call('Runroot task failed: 1234. See %s for more details.'
                      % (self.topdir + '/logs/x86_64/Everything/ostree-1/runroot.log'))
        ])

    @mock.patch('pungi.wrappers.scm.get_dir_from_scm')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    def test_run_handle_exception(self, KojiWrapper, get_dir_from_scm):
        get_dir_from_scm.side_effect = self._dummy_config_repo

        self.cfg['failable'] = ['*']
        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.side_effect = helpers.boom

        t = ostree.OSTreeThread(self.pool)

        t.process((self.compose, self.compose.variants['Everything'], 'x86_64', self.cfg), 1)

        self.compose.log_info.assert_has_calls([
            mock.call('[FAIL] Ostree (variant Everything, arch x86_64) failed, but going on anyway.'),
            mock.call('BOOM')
        ])

    @mock.patch('pungi.wrappers.scm.get_dir_from_scm')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    def test_run_send_message(self, KojiWrapper, get_dir_from_scm):
        get_dir_from_scm.side_effect = self._dummy_config_repo

        self.compose.notifier = mock.Mock()

        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.side_effect = self._mock_runroot(
            0,
            {'commitid': 'fca3465861a',
             'create-ostree-repo.log':
                ['Doing work', 'fedora-atomic/25/x86_64 -> fca3465861a']})
        t = ostree.OSTreeThread(self.pool)

        t.process((self.compose, self.compose.variants['Everything'], 'x86_64', self.cfg), 1)

        self.assertEqual(self.compose.notifier.send.mock_calls,
                         [mock.call('ostree',
                                    variant='Everything',
                                    arch='x86_64',
                                    ref='fedora-atomic/25/x86_64',
                                    commitid='fca3465861a')])

    @mock.patch('pungi.wrappers.scm.get_dir_from_scm')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    def test_run_send_message_without_commit_id(self, KojiWrapper, get_dir_from_scm):
        get_dir_from_scm.side_effect = self._dummy_config_repo

        self.compose.notifier = mock.Mock()

        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.side_effect = self._mock_runroot(
            0,
            {'create-ostree-repo.log': ['Doing work', 'Weird output']})
        t = ostree.OSTreeThread(self.pool)

        t.process((self.compose, self.compose.variants['Everything'], 'x86_64', self.cfg), 1)

        self.assertEqual(self.compose.notifier.send.mock_calls,
                         [mock.call('ostree',
                                    variant='Everything',
                                    arch='x86_64',
                                    ref=None,
                                    commitid=None)])

    @mock.patch('pungi.wrappers.scm.get_dir_from_scm')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    def test_run_send_no_message_on_failure(self, KojiWrapper, get_dir_from_scm):
        get_dir_from_scm.side_effect = self._dummy_config_repo

        self.compose.notifier = mock.Mock()

        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.side_effect = self._mock_runroot(1)
        t = ostree.OSTreeThread(self.pool)

        self.assertRaises(RuntimeError, t.process,
                          (self.compose, self.compose.variants['Everything'], 'x86_64', self.cfg),
                          1)
        self.assertEqual(self.compose.notifier.send.mock_calls, [])

    @mock.patch('pungi.wrappers.scm.get_dir_from_scm')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    def test_run_with_update_summary(self, KojiWrapper, get_dir_from_scm):
        self.cfg['update_summary'] = True

        get_dir_from_scm.side_effect = self._dummy_config_repo

        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.side_effect = self._mock_runroot(0)

        t = ostree.OSTreeThread(self.pool)

        t.process((self.compose, self.compose.variants['Everything'], 'x86_64', self.cfg), 1)

        self.assertEqual(get_dir_from_scm.call_args_list,
                         [mock.call({'scm': 'git', 'repo': 'https://git.fedorahosted.org/git/fedora-atomic.git',
                                     'branch': 'f24', 'dir': '.'},
                                    self.topdir + '/work/ostree-1/config_repo', logger=self.pool._logger)])
        self.assertEqual(koji.get_runroot_cmd.call_args_list,
                         [mock.call('rrt', 'x86_64',
                                    ['pungi-make-ostree',
                                     '--log-dir=%s/logs/x86_64/Everything/ostree-1' % self.topdir,
                                     '--treefile=%s/fedora-atomic-docker-host.json' % (
                                         self.topdir + '/work/ostree-1/config_repo'),
                                     '--update-summary', self.repo],
                                    channel=None, mounts=[self.topdir, self.repo],
                                    packages=['pungi', 'ostree', 'rpm-ostree'],
                                    task_id=True, use_shell=True, new_chroot=True)])
        self.assertEqual(koji.run_runroot_cmd.call_args_list,
                         [mock.call(koji.get_runroot_cmd.return_value,
                                    log_file=self.topdir + '/logs/x86_64/Everything/ostree-1/runroot.log')])

        for fp in ['fedora-rawhide.repo', 'fedora-24.repo', 'fedora-24.repo']:
            with open(os.path.join(self.topdir, 'work/ostree-1/config_repo', fp)) as f:
                self.assertIn('baseurl=http://example.com/Everything/$basearch/os',
                              f.read())
        self.assertTrue(os.path.isdir(self.repo))

    @mock.patch('pungi.wrappers.scm.get_dir_from_scm')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    def test_run_with_versioning_metadata(self, KojiWrapper, get_dir_from_scm):
        self.cfg['version'] = '24'

        get_dir_from_scm.side_effect = self._dummy_config_repo

        koji = KojiWrapper.return_value
        koji.run_runroot_cmd.side_effect = self._mock_runroot(0)

        t = ostree.OSTreeThread(self.pool)

        t.process((self.compose, self.compose.variants['Everything'], 'x86_64', self.cfg), 1)

        self.assertEqual(get_dir_from_scm.call_args_list,
                         [mock.call({'scm': 'git', 'repo': 'https://git.fedorahosted.org/git/fedora-atomic.git',
                                     'branch': 'f24', 'dir': '.'},
                                    self.topdir + '/work/ostree-1/config_repo', logger=self.pool._logger)])
        self.assertEqual(koji.get_runroot_cmd.call_args_list,
                         [mock.call('rrt', 'x86_64',
                                    ['pungi-make-ostree',
                                     '--log-dir=%s/logs/x86_64/Everything/ostree-1' % self.topdir,
                                     '--treefile=%s/fedora-atomic-docker-host.json' % (
                                         self.topdir + '/work/ostree-1/config_repo'),
                                     '--version=24', self.repo],
                                    channel=None, mounts=[self.topdir, self.repo],
                                    packages=['pungi', 'ostree', 'rpm-ostree'],
                                    task_id=True, use_shell=True, new_chroot=True)])
        self.assertEqual(koji.run_runroot_cmd.call_args_list,
                         [mock.call(koji.get_runroot_cmd.return_value,
                                    log_file=self.topdir + '/logs/x86_64/Everything/ostree-1/runroot.log')])

if __name__ == '__main__':
    unittest.main()
