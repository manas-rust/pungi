#!/usr/bin/env python2
# -*- coding: utf-8 -*-


import unittest
import mock

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.phases.image_build import ImageBuildPhase, CreateImageBuildThread
from tests.helpers import _DummyCompose, PungiTestCase


class TestImageBuildPhase(PungiTestCase):

    @mock.patch('pungi.phases.image_build.ThreadPool')
    def test_image_build(self, ThreadPool):
        compose = _DummyCompose(self.topdir, {
            'image_build': {
                '^Client|Server$': [
                    {
                        'image-build': {
                            'format': [('docker', 'tar.xz')],
                            'name': 'Fedora-Docker-Base',
                            'target': 'f24',
                            'version': 'Rawhide',
                            'ksurl': 'git://git.fedorahosted.org/git/spin-kickstarts.git',
                            'kickstart': "fedora-docker-base.ks",
                            'distro': 'Fedora-20',
                            'disk_size': 3
                        }
                    }
                ]
            },
            'koji_profile': 'koji',
        })

        phase = ImageBuildPhase(compose)

        phase.run()
        self.maxDiff = None

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)
        client_args = {
            "format": [('docker', 'tar.xz')],
            "image_conf": {
                'image-build': {
                    'install_tree': self.topdir + '/compose/Client/$arch/os',
                    'kickstart': 'fedora-docker-base.ks',
                    'format': 'docker',
                    'repo': self.topdir + '/compose/Client/$arch/os',
                    'variant': compose.variants['Client'],
                    'target': 'f24',
                    'disk_size': 3,
                    'name': 'Fedora-Docker-Base',
                    'arches': 'amd64',
                    'version': 'Rawhide',
                    'ksurl': 'git://git.fedorahosted.org/git/spin-kickstarts.git',
                    'distro': 'Fedora-20',
                }
            },
            "conf_file": self.topdir + '/work/image-build/Client/docker_Fedora-Docker-Base.cfg',
            "image_dir": self.topdir + '/compose/Client/%(arch)s/images',
            "relative_image_dir": 'Client/%(arch)s/images',
            "link_type": 'hardlink-or-copy',
            "scratch": False,
        }
        server_args = {
            "format": [('docker', 'tar.xz')],
            "image_conf": {
                'image-build': {
                    'install_tree': self.topdir + '/compose/Server/$arch/os',
                    'kickstart': 'fedora-docker-base.ks',
                    'format': 'docker',
                    'repo': self.topdir + '/compose/Server/$arch/os',
                    'variant': compose.variants['Server'],
                    'target': 'f24',
                    'disk_size': 3,
                    'name': 'Fedora-Docker-Base',
                    'arches': 'amd64,x86_64',
                    'version': 'Rawhide',
                    'ksurl': 'git://git.fedorahosted.org/git/spin-kickstarts.git',
                    'distro': 'Fedora-20',
                }
            },
            "conf_file": self.topdir + '/work/image-build/Server/docker_Fedora-Docker-Base.cfg',
            "image_dir": self.topdir + '/compose/Server/%(arch)s/images',
            "relative_image_dir": 'Server/%(arch)s/images',
            "link_type": 'hardlink-or-copy',
            "scratch": False,
        }
        self.maxDiff = None
        self.assertItemsEqual(phase.pool.queue_put.mock_calls,
                              [mock.call((compose, client_args)),
                               mock.call((compose, server_args))])

    @mock.patch('pungi.phases.image_build.ThreadPool')
    def test_image_build_filter_all_variants(self, ThreadPool):
        compose = _DummyCompose(self.topdir, {
            'image_build': {
                '^Client|Server$': [
                    {
                        'image-build': {
                            'format': [('docker', 'tar.xz')],
                            'name': 'Fedora-Docker-Base',
                            'target': 'f24',
                            'version': 'Rawhide',
                            'ksurl': 'git://git.fedorahosted.org/git/spin-kickstarts.git',
                            'kickstart': "fedora-docker-base.ks",
                            'distro': 'Fedora-20',
                            'disk_size': 3,
                            'arches': ['non-existing'],
                        }
                    }
                ]
            },
            'koji_profile': 'koji',
        })

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertFalse(phase.pool.add.called)
        self.assertFalse(phase.pool.queue_put.called)

    @mock.patch('pungi.phases.image_build.ThreadPool')
    def test_image_build_set_install_tree(self, ThreadPool):
        compose = _DummyCompose(self.topdir, {
            'image_build': {
                '^Server$': [
                    {
                        'image-build': {
                            'format': [('docker', 'tar.xz')],
                            'name': 'Fedora-Docker-Base',
                            'target': 'f24',
                            'version': 'Rawhide',
                            'ksurl': 'git://git.fedorahosted.org/git/spin-kickstarts.git',
                            'kickstart': "fedora-docker-base.ks",
                            'distro': 'Fedora-20',
                            'disk_size': 3,
                            'arches': ['x86_64'],
                            'install_tree_from': 'Everything',
                        }
                    }
                ]
            },
            'koji_profile': 'koji',
        })

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)

        self.assertTrue(phase.pool.queue_put.called_once)
        args, kwargs = phase.pool.queue_put.call_args
        self.assertEqual(args[0][0], compose)
        self.maxDiff = None
        self.assertDictEqual(args[0][1], {
            "format": [('docker', 'tar.xz')],
            "image_conf": {
                'image-build': {
                    'install_tree': self.topdir + '/compose/Everything/$arch/os',
                    'kickstart': 'fedora-docker-base.ks',
                    'format': 'docker',
                    'repo': self.topdir + '/compose/Server/$arch/os',
                    'variant': compose.variants['Server'],
                    'target': 'f24',
                    'disk_size': 3,
                    'name': 'Fedora-Docker-Base',
                    'arches': 'x86_64',
                    'version': 'Rawhide',
                    'ksurl': 'git://git.fedorahosted.org/git/spin-kickstarts.git',
                    'distro': 'Fedora-20',
                }
            },
            "conf_file": self.topdir + '/work/image-build/Server/docker_Fedora-Docker-Base.cfg',
            "image_dir": self.topdir + '/compose/Server/%(arch)s/images',
            "relative_image_dir": 'Server/%(arch)s/images',
            "link_type": 'hardlink-or-copy',
            "scratch": False,
        })

    @mock.patch('pungi.phases.image_build.ThreadPool')
    def test_image_build_set_extra_repos(self, ThreadPool):
        compose = _DummyCompose(self.topdir, {
            'image_build': {
                '^Server$': [
                    {
                        'image-build': {
                            'format': [('docker', 'tar.xz')],
                            'name': 'Fedora-Docker-Base',
                            'target': 'f24',
                            'version': 'Rawhide',
                            'ksurl': 'git://git.fedorahosted.org/git/spin-kickstarts.git',
                            'kickstart': "fedora-docker-base.ks",
                            'distro': 'Fedora-20',
                            'disk_size': 3,
                            'arches': ['x86_64'],
                            'repo_from': 'Everything',
                        }
                    }
                ]
            },
            'koji_profile': 'koji',
        })

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)

        self.assertTrue(phase.pool.queue_put.called_once)
        args, kwargs = phase.pool.queue_put.call_args
        self.assertEqual(args[0][0], compose)
        self.maxDiff = None
        self.assertDictEqual(args[0][1], {
            "format": [('docker', 'tar.xz')],
            "image_conf": {
                'image-build': {
                    'install_tree': self.topdir + '/compose/Server/$arch/os',
                    'kickstart': 'fedora-docker-base.ks',
                    'format': 'docker',
                    'repo': ','.join([self.topdir + '/compose/Everything/$arch/os',
                                      self.topdir + '/compose/Server/$arch/os']),
                    'variant': compose.variants['Server'],
                    'target': 'f24',
                    'disk_size': 3,
                    'name': 'Fedora-Docker-Base',
                    'arches': 'x86_64',
                    'version': 'Rawhide',
                    'ksurl': 'git://git.fedorahosted.org/git/spin-kickstarts.git',
                    'distro': 'Fedora-20',
                }
            },
            "conf_file": self.topdir + '/work/image-build/Server/docker_Fedora-Docker-Base.cfg',
            "image_dir": self.topdir + '/compose/Server/%(arch)s/images',
            "relative_image_dir": 'Server/%(arch)s/images',
            "link_type": 'hardlink-or-copy',
            "scratch": False,
        })

    @mock.patch('pungi.phases.image_build.ThreadPool')
    def test_image_build_create_release(self, ThreadPool):
        compose = _DummyCompose(self.topdir, {
            'image_build': {
                '^Server$': [
                    {
                        'image-build': {
                            'format': [('docker', 'tar.xz')],
                            'name': 'Fedora-Docker-Base',
                            'target': 'f24',
                            'version': 'Rawhide',
                            'ksurl': 'git://git.fedorahosted.org/git/spin-kickstarts.git',
                            'kickstart': "fedora-docker-base.ks",
                            'distro': 'Fedora-20',
                            'disk_size': 3,
                            'arches': ['x86_64'],
                            'release': None,
                        }
                    }
                ]
            },
            'koji_profile': 'koji',
        })

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)

        self.assertTrue(phase.pool.queue_put.called_once)
        args, kwargs = phase.pool.queue_put.call_args
        self.assertEqual(args[0][1].get('image_conf', {}).get('image-build', {}).get('release'),
                         '20151203.0')

    @mock.patch('pungi.phases.image_build.ThreadPool')
    def test_image_build_scratch_build(self, ThreadPool):
        compose = _DummyCompose(self.topdir, {
            'image_build': {
                '^Server$': [
                    {
                        'image-build': {
                            'format': [('docker', 'tar.xz')],
                            'name': 'Fedora-Docker-Base',
                            'target': 'f24',
                            'version': 'Rawhide',
                            'ksurl': 'git://git.fedorahosted.org/git/spin-kickstarts.git',
                            'kickstart': "fedora-docker-base.ks",
                            'distro': 'Fedora-20',
                            'disk_size': 3,
                            'arches': ['x86_64'],
                            'scratch': True,
                        }
                    }
                ]
            },
            'koji_profile': 'koji',
        })

        phase = ImageBuildPhase(compose)

        phase.run()

        # assert at least one thread was started
        self.assertTrue(phase.pool.add.called)

        self.assertTrue(phase.pool.queue_put.called_once)
        args, kwargs = phase.pool.queue_put.call_args
        self.assertTrue(args[0][1].get('scratch'))


class TestCreateImageBuildThread(PungiTestCase):

    @mock.patch('pungi.phases.image_build.get_mtime')
    @mock.patch('pungi.phases.image_build.get_file_size')
    @mock.patch('pungi.phases.image_build.KojiWrapper')
    @mock.patch('pungi.phases.image_build.Linker')
    def test_process(self, Linker, KojiWrapper, get_file_size, get_mtime):
        compose = _DummyCompose(self.topdir, {
            'koji_profile': 'koji'
        })
        pool = mock.Mock()
        cmd = {
            "format": [('docker', 'tar.xz'), ('qcow2', 'qcow2')],
            "image_conf": {
                'image-build': {
                    'install_tree': '/ostree/$arch/Client',
                    'kickstart': 'fedora-docker-base.ks',
                    'format': 'docker',
                    'repo': '/ostree/$arch/Client',
                    'variant': compose.variants['Client'],
                    'target': 'f24',
                    'disk_size': 3,
                    'name': 'Fedora-Docker-Base',
                    'arches': 'amd64,x86_64',
                    'version': 'Rawhide',
                    'ksurl': 'git://git.fedorahosted.org/git/spin-kickstarts.git',
                    'distro': 'Fedora-20',
                }
            },
            "conf_file": 'amd64,x86_64-Client-Fedora-Docker-Base-docker',
            "image_dir": self.topdir + '/compose/Client/%(arch)s/images',
            "relative_image_dir": 'image_dir/Client/%(arch)s',
            "link_type": 'hardlink-or-copy',
            "scratch": False,
        }
        koji_wrapper = KojiWrapper.return_value
        koji_wrapper.run_blocking_cmd.return_value = {
            "retcode": 0,
            "output": None,
            "task_id": 1234,
        }
        koji_wrapper.get_image_paths.return_value = {
            'amd64': [
                '/koji/task/1235/tdl-amd64.xml',
                '/koji/task/1235/Fedora-Docker-Base-20160103.amd64.qcow2',
                '/koji/task/1235/Fedora-Docker-Base-20160103.amd64.tar.xz'
            ],
            'x86_64': [
                '/koji/task/1235/tdl-x86_64.xml',
                '/koji/task/1235/Fedora-Docker-Base-20160103.x86_64.qcow2',
                '/koji/task/1235/Fedora-Docker-Base-20160103.x86_64.tar.xz'
            ]
        }

        linker = Linker.return_value
        get_file_size.return_value = 1024
        get_mtime.return_value = 13579

        t = CreateImageBuildThread(pool)
        with mock.patch('time.sleep'):
            t.process((compose, cmd), 1)

        self.assertItemsEqual(
            linker.mock_calls,
            [mock.call('/koji/task/1235/Fedora-Docker-Base-20160103.amd64.qcow2',
                       self.topdir + '/compose/Client/amd64/images/Fedora-Docker-Base-20160103.amd64.qcow2',
                       link_type='hardlink-or-copy'),
             mock.call('/koji/task/1235/Fedora-Docker-Base-20160103.amd64.tar.xz',
                       self.topdir + '/compose/Client/amd64/images/Fedora-Docker-Base-20160103.amd64.tar.xz',
                       link_type='hardlink-or-copy'),
             mock.call('/koji/task/1235/Fedora-Docker-Base-20160103.x86_64.qcow2',
                       self.topdir + '/compose/Client/x86_64/images/Fedora-Docker-Base-20160103.x86_64.qcow2',
                       link_type='hardlink-or-copy'),
             mock.call('/koji/task/1235/Fedora-Docker-Base-20160103.x86_64.tar.xz',
                       self.topdir + '/compose/Client/x86_64/images/Fedora-Docker-Base-20160103.x86_64.tar.xz',
                       link_type='hardlink-or-copy')])

        image_relative_paths = {
            'image_dir/Client/amd64/Fedora-Docker-Base-20160103.amd64.qcow2': {
                'format': 'qcow2',
                'type': 'qcow2',
                'arch': 'amd64',
            },
            'image_dir/Client/amd64/Fedora-Docker-Base-20160103.amd64.tar.xz': {
                'format': 'tar.xz',
                'type': 'docker',
                'arch': 'amd64',
            },
            'image_dir/Client/x86_64/Fedora-Docker-Base-20160103.x86_64.qcow2': {
                'format': 'qcow2',
                'type': 'qcow2',
                'arch': 'x86_64',
            },
            'image_dir/Client/x86_64/Fedora-Docker-Base-20160103.x86_64.tar.xz': {
                'format': 'tar.xz',
                'type': 'docker',
                'arch': 'x86_64',
            },
        }

        # Assert there are 4 images added to manifest and the arguments are sane
        self.assertEqual(len(compose.im.add.call_args_list), 4)
        for call in compose.im.add.call_args_list:
            _, kwargs = call
            image = kwargs['image']
            self.assertEqual(kwargs['variant'], 'Client')
            self.assertIn(kwargs['arch'], ('amd64', 'x86_64'))
            self.assertEqual(kwargs['arch'], image.arch)
            self.assertIn(image.path, image_relative_paths)
            data = image_relative_paths.pop(image.path)
            self.assertEqual(data['format'], image.format)
            self.assertEqual(data['type'], image.type)

        self.assertTrue(os.path.isdir(self.topdir + '/compose/Client/amd64/images'))
        self.assertTrue(os.path.isdir(self.topdir + '/compose/Client/x86_64/images'))

    @mock.patch('pungi.phases.image_build.KojiWrapper')
    @mock.patch('pungi.phases.image_build.Linker')
    def test_process_handle_fail(self, Linker, KojiWrapper):
        compose = _DummyCompose(self.topdir, {
            'koji_profile': 'koji',
            'failable_deliverables': [
                ('^.*$', {
                    '*': ['image-build']
                })
            ]
        })
        pool = mock.Mock()
        cmd = {
            "format": [('docker', 'tar.xz'), ('qcow2', 'qcow2')],
            "image_conf": {
                'image-build': {
                    'install_tree': '/ostree/$arch/Client',
                    'kickstart': 'fedora-docker-base.ks',
                    'format': 'docker',
                    'repo': '/ostree/$arch/Client',
                    'variant': compose.variants['Client'],
                    'target': 'f24',
                    'disk_size': 3,
                    'name': 'Fedora-Docker-Base',
                    'arches': 'amd64,x86_64',
                    'version': 'Rawhide',
                    'ksurl': 'git://git.fedorahosted.org/git/spin-kickstarts.git',
                    'distro': 'Fedora-20',
                }
            },
            "conf_file": 'amd64,x86_64-Client-Fedora-Docker-Base-docker',
            "image_dir": '/image_dir/Client/%(arch)s',
            "relative_image_dir": 'image_dir/Client/%(arch)s',
            "link_type": 'hardlink-or-copy',
            'scratch': False,
        }
        koji_wrapper = KojiWrapper.return_value
        koji_wrapper.run_blocking_cmd.return_value = {
            "retcode": 1,
            "output": None,
            "task_id": 1234,
        }

        t = CreateImageBuildThread(pool)
        with mock.patch('os.stat') as stat:
            with mock.patch('os.path.getsize') as getsize:
                with mock.patch('time.sleep'):
                    getsize.return_value = 1024
                    stat.return_value.st_mtime = 13579
                    t.process((compose, cmd), 1)

    @mock.patch('pungi.phases.image_build.KojiWrapper')
    @mock.patch('pungi.phases.image_build.Linker')
    def test_process_handle_exception(self, Linker, KojiWrapper):
        compose = _DummyCompose(self.topdir, {
            'koji_profile': 'koji',
            'failable_deliverables': [
                ('^.*$', {
                    '*': ['image-build']
                })
            ]
        })
        pool = mock.Mock()
        cmd = {
            "format": [('docker', 'tar.xz'), ('qcow2', 'qcow2')],
            "image_conf": {
                'image-build': {
                    'install_tree': '/ostree/$arch/Client',
                    'kickstart': 'fedora-docker-base.ks',
                    'format': 'docker',
                    'repo': '/ostree/$arch/Client',
                    'variant': compose.variants['Client'],
                    'target': 'f24',
                    'disk_size': 3,
                    'name': 'Fedora-Docker-Base',
                    'arches': 'amd64,x86_64',
                    'version': 'Rawhide',
                    'ksurl': 'git://git.fedorahosted.org/git/spin-kickstarts.git',
                    'distro': 'Fedora-20',
                }
            },
            "conf_file": 'amd64,x86_64-Client-Fedora-Docker-Base-docker',
            "image_dir": '/image_dir/Client/%(arch)s',
            "relative_image_dir": 'image_dir/Client/%(arch)s',
            "link_type": 'hardlink-or-copy',
            'scratch': False,
        }

        def boom(*args, **kwargs):
            raise RuntimeError('BOOM')

        koji_wrapper = KojiWrapper.return_value
        koji_wrapper.run_blocking_cmd.side_effect = boom

        t = CreateImageBuildThread(pool)
        with mock.patch('os.stat') as stat:
            with mock.patch('os.path.getsize') as getsize:
                with mock.patch('time.sleep'):
                    getsize.return_value = 1024
                    stat.return_value.st_mtime = 13579
                    t.process((compose, cmd), 1)


if __name__ == "__main__":
    unittest.main()
