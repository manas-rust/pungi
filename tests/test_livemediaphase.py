#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import unittest
import mock

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.phases.livemedia_phase import LiveMediaPhase, LiveMediaThread
from tests.helpers import _DummyCompose, PungiTestCase


class TestLiveMediaPhase(PungiTestCase):
    @mock.patch('pungi.phases.livemedia_phase.ThreadPool')
    def test_live_media_minimal(self, ThreadPool):
        compose = _DummyCompose(self.topdir, {
            'live_media': {
                '^Server$': [
                    {
                        'target': 'f24',
                        'kickstart': 'file.ks',
                        'ksurl': 'git://example.com/repo.git',
                        'name': 'Fedora Server Live',
                        'version': 'Rawhide',
                    }
                ]
            },
            'koji_profile': 'koji',
        })

        phase = LiveMediaPhase(compose)

        phase.run()
        self.assertTrue(phase.pool.add.called)
        self.assertEqual(phase.pool.queue_put.call_args_list,
                         [mock.call((compose,
                                     compose.variants['Server'],
                                     {
                                         'arches': ['amd64', 'x86_64'],
                                         'ksfile': 'file.ks',
                                         'ksurl': 'git://example.com/repo.git',
                                         'ksversion': None,
                                         'name': 'Fedora Server Live',
                                         'release': None,
                                         'repo': [self.topdir + '/compose/Server/$basearch/os'],
                                         'scratch': False,
                                         'skip_tag': None,
                                         'target': 'f24',
                                         'title': None,
                                         'install_tree': self.topdir + '/compose/Server/$basearch/os',
                                         'version': 'Rawhide',
                                     }))])

    @mock.patch('pungi.phases.livemedia_phase.ThreadPool')
    def test_live_media_non_existing_install_tree(self, ThreadPool):
        compose = _DummyCompose(self.topdir, {
            'live_media': {
                '^Server$': [
                    {
                        'target': 'f24',
                        'kickstart': 'file.ks',
                        'ksurl': 'git://example.com/repo.git',
                        'name': 'Fedora Server Live',
                        'version': 'Rawhide',
                        'install_tree_from': 'Missing',
                    }
                ]
            },
            'koji_profile': 'koji',
        })

        phase = LiveMediaPhase(compose)

        with self.assertRaisesRegexp(RuntimeError, r'no.+Missing.+when building.+Server'):
            phase.run()

    @mock.patch('pungi.phases.livemedia_phase.ThreadPool')
    def test_live_media_non_existing_repo(self, ThreadPool):
        compose = _DummyCompose(self.topdir, {
            'live_media': {
                '^Server$': [
                    {
                        'target': 'f24',
                        'kickstart': 'file.ks',
                        'ksurl': 'git://example.com/repo.git',
                        'name': 'Fedora Server Live',
                        'version': 'Rawhide',
                        'repo_from': 'Missing',
                    }
                ]
            },
            'koji_profile': 'koji',
        })

        phase = LiveMediaPhase(compose)

        with self.assertRaisesRegexp(RuntimeError, r'no.+Missing.+when building.+Server'):
            phase.run()

    @mock.patch('pungi.phases.livemedia_phase.resolve_git_url')
    @mock.patch('pungi.phases.livemedia_phase.ThreadPool')
    def test_live_media_full(self, ThreadPool, resolve_git_url):
        compose = _DummyCompose(self.topdir, {
            'live_media': {
                '^Server$': [
                    {
                        'target': 'f24',
                        'kickstart': 'file.ks',
                        'ksurl': 'git://example.com/repo.git#HEAD',
                        'name': 'Fedora Server Live',
                        'scratch': True,
                        'skip_tag': True,
                        'title': 'Custom Title',
                        'repo_from': ['Everything'],
                        'repo': ['http://example.com/extra_repo'],
                        'arches': ['x86_64'],
                        'ksversion': '24',
                        'release': None,
                        'version': 'Rawhide',
                        'install_tree_from': 'Everything',
                    }
                ]
            }
        })

        resolve_git_url.return_value = 'resolved'

        phase = LiveMediaPhase(compose)

        phase.run()
        self.assertTrue(phase.pool.add.called)
        self.assertEqual(phase.pool.queue_put.call_args_list,
                         [mock.call((compose,
                                     compose.variants['Server'],
                                     {
                                         'arches': ['x86_64'],
                                         'ksfile': 'file.ks',
                                         'ksurl': 'resolved',
                                         'ksversion': '24',
                                         'name': 'Fedora Server Live',
                                         'release': '20151203.0',
                                         'repo': ['http://example.com/extra_repo',
                                                  self.topdir + '/compose/Everything/$basearch/os',
                                                  self.topdir + '/compose/Server/$basearch/os'],
                                         'scratch': True,
                                         'skip_tag': True,
                                         'target': 'f24',
                                         'title': 'Custom Title',
                                         'install_tree': self.topdir + '/compose/Everything/$basearch/os',
                                         'version': 'Rawhide',
                                     }))])


class TestCreateImageBuildThread(PungiTestCase):

    @mock.patch('pungi.phases.livemedia_phase.get_mtime')
    @mock.patch('pungi.phases.livemedia_phase.get_file_size')
    @mock.patch('pungi.phases.livemedia_phase.KojiWrapper')
    @mock.patch('pungi.phases.livemedia_phase.Linker')
    def test_process(self, Linker, KojiWrapper, get_file_size, get_mtime):
        compose = _DummyCompose(self.topdir, {
            'koji_profile': 'koji'
        })
        config = {
            'arches': ['amd64', 'x86_64'],
            'ksfile': 'file.ks',
            'ksurl': 'git://example.com/repo.git',
            'ksversion': None,
            'name': 'Fedora Server Live',
            'release': None,
            'repo': ['/repo/$basearch/Server'],
            'scratch': False,
            'skip_tag': None,
            'target': 'f24',
            'title': None,
            'version': 'Rawhide',
        }
        pool = mock.Mock()

        get_live_media_cmd = KojiWrapper.return_value.get_live_media_cmd
        get_live_media_cmd.return_value = 'koji-spin-livemedia'

        run_blocking_cmd = KojiWrapper.return_value.run_blocking_cmd
        run_blocking_cmd.return_value = {
            'task_id': 1234,
            'retcode': 0,
            'output': None,
        }

        get_image_paths = KojiWrapper.return_value.get_image_paths
        get_image_paths.return_value = {
            'x86_64': [
                '/koji/task/1235/tdl-amd64.xml',
                '/koji/task/1235/Live-20160103.x86_64.iso',
                '/koji/task/1235/Live-20160103.x86_64.tar.xz'
            ],
            'amd64': [
                '/koji/task/1235/tdl-amd64.xml',
                '/koji/task/1235/Live-20160103.amd64.iso',
                '/koji/task/1235/Live-20160103.amd64.tar.xz'
            ]
        }

        t = LiveMediaThread(pool)
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579
        with mock.patch('time.sleep'):
            t.process((compose, compose.variants['Server'], config), 1)

        self.assertEqual(
            run_blocking_cmd.mock_calls,
            [mock.call('koji-spin-livemedia',
                       log_file=self.topdir + '/logs/amd64-x86_64/livemedia-Server.amd64-x86_64.log')])
        self.assertEqual(get_live_media_cmd.mock_calls,
                         [mock.call({'arch': 'amd64,x86_64',
                                     'ksfile': 'file.ks',
                                     'ksurl': 'git://example.com/repo.git',
                                     'ksversion': None,
                                     'name': 'Fedora Server Live',
                                     'release': None,
                                     'repo': ['/repo/$basearch/Server'],
                                     'scratch': False,
                                     'skip_tag': None,
                                     'target': 'f24',
                                     'title': None,
                                     'version': 'Rawhide'})])
        self.assertEqual(get_image_paths.mock_calls,
                         [mock.call(1234)])
        self.assertTrue(os.path.isdir(self.topdir + '/compose/Server/x86_64/iso'))
        self.assertTrue(os.path.isdir(self.topdir + '/compose/Server/amd64/iso'))
        link = Linker.return_value.link
        self.assertItemsEqual(link.mock_calls,
                              [mock.call('/koji/task/1235/Live-20160103.amd64.iso',
                                         self.topdir + '/compose/Server/amd64/iso/Live-20160103.amd64.iso',
                                         link_type='hardlink-or-copy'),
                               mock.call('/koji/task/1235/Live-20160103.x86_64.iso',
                                         self.topdir + '/compose/Server/x86_64/iso/Live-20160103.x86_64.iso',
                                         link_type='hardlink-or-copy')])

        image_relative_paths = [
            'Server/amd64/iso/Live-20160103.amd64.iso',
            'Server/x86_64/iso/Live-20160103.x86_64.iso'
        ]

        self.assertEqual(len(compose.im.add.call_args_list), 2)
        for call in compose.im.add.call_args_list:
            _, kwargs = call
            image = kwargs['image']
            self.assertEqual(kwargs['variant'], 'Server')
            self.assertIn(kwargs['arch'], ('amd64', 'x86_64'))
            self.assertEqual(kwargs['arch'], image.arch)
            self.assertIn(image.path, image_relative_paths)
            self.assertEqual('iso', image.format)
            self.assertEqual('live', image.type)

    @mock.patch('pungi.phases.livemedia_phase.KojiWrapper')
    def test_handle_koji_fail(self, KojiWrapper):
        compose = _DummyCompose(self.topdir, {
            'koji_profile': 'koji',
            'failable_deliverables': [
                ('^.+$', {'*': ['live-media']})
            ]
        })
        config = {
            'arches': ['amd64', 'x86_64'],
            'ksfile': 'file.ks',
            'ksurl': 'git://example.com/repo.git',
            'ksversion': None,
            'name': 'Fedora Server Live',
            'release': None,
            'repo': ['/repo/$basearch/Server'],
            'scratch': False,
            'skip_tag': None,
            'target': 'f24',
            'title': None,
            'version': 'Rawhide',
        }
        pool = mock.Mock()

        run_blocking_cmd = KojiWrapper.return_value.run_blocking_cmd
        run_blocking_cmd.return_value = {
            'task_id': 1234,
            'retcode': 1,
            'output': None,
        }

        t = LiveMediaThread(pool)
        with mock.patch('os.stat') as stat:
            with mock.patch('os.path.getsize') as getsize:
                with mock.patch('time.sleep'):
                    getsize.return_value = 1024
                    stat.return_value.st_mtime = 13579
                    t.process((compose, compose.variants['Server'], config), 1)

    @mock.patch('pungi.phases.livemedia_phase.KojiWrapper')
    def test_handle_exception(self, KojiWrapper):
        compose = _DummyCompose(self.topdir, {
            'koji_profile': 'koji',
            'failable_deliverables': [
                ('^.+$', {'*': ['live-media']})
            ]
        })
        config = {
            'arches': ['amd64', 'x86_64'],
            'ksfile': 'file.ks',
            'ksurl': 'git://example.com/repo.git',
            'ksversion': None,
            'name': 'Fedora Server Live',
            'release': None,
            'repo': ['/repo/$basearch/Server'],
            'scratch': False,
            'skip_tag': None,
            'target': 'f24',
            'title': None,
            'version': 'Rawhide',
        }
        pool = mock.Mock()

        def boom(*args, **kwargs):
            raise Exception('BOOM')

        run_blocking_cmd = KojiWrapper.return_value.run_blocking_cmd
        run_blocking_cmd.side_effect = boom

        t = LiveMediaThread(pool)
        with mock.patch('os.stat') as stat:
            with mock.patch('os.path.getsize') as getsize:
                with mock.patch('time.sleep'):
                    getsize.return_value = 1024
                    stat.return_value.st_mtime = 13579
                    t.process((compose, compose.variants['Server'], config), 1)


if __name__ == "__main__":
    unittest.main()
