#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import mock
import unittest

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.wrappers.kojiwrapper import KojiWrapper


class KojiWrapperTest(unittest.TestCase):

    def setUp(self):
        self.koji_profile = mock.Mock()
        with mock.patch('pungi.wrappers.kojiwrapper.koji') as koji:
            koji.get_profile_module = mock.Mock(
                return_value=mock.Mock(
                    pathinfo=mock.Mock(
                        work=mock.Mock(return_value='/koji'),
                        taskrelpath=mock.Mock(side_effect=lambda id: 'task/' + str(id)),
                        imagebuild=mock.Mock(side_effect=lambda id: '/koji/imagebuild/' + str(id)),
                    )
                )
            )
            self.koji_profile = koji.get_profile_module.return_value
            self.koji = KojiWrapper('koji')

    @mock.patch('pungi.wrappers.kojiwrapper.open')
    def test_get_image_build_cmd_without_required_data(self, mock_open):
        with self.assertRaises(AssertionError):
            self.koji.get_image_build_cmd(
                {
                    'name': 'test-name',
                },
                '/tmp/file'
            )

    @mock.patch('pungi.wrappers.kojiwrapper.open')
    def test_get_image_build_cmd_correct(self, mock_open):
        cmd = self.koji.get_image_build_cmd(
            {
                'name': 'test-name',
                'version': '1',
                'target': 'test-target',
                'install_tree': '/tmp/test/install_tree',
                'arches': 'x86_64',
                'format': 'docker,qcow2',
                'kickstart': 'test-kickstart',
                'ksurl': 'git://example.com/ks.git',
                'distro': 'test-distro',
            },
            '/tmp/file'
        )

        self.assertEqual(cmd[0], 'koji')
        self.assertEqual(cmd[1], 'image-build')
        self.assertItemsEqual(cmd[2:],
                              ['--config=/tmp/file', '--wait'])

        output = mock_open.return_value
        self.assertEqual(mock.call('[image-build]\n'), output.write.mock_calls[0])
        self.assertItemsEqual(output.write.mock_calls[1:],
                              [mock.call('name = test-name\n'),
                               mock.call('version = 1\n'),
                               mock.call('target = test-target\n'),
                               mock.call('install_tree = /tmp/test/install_tree\n'),
                               mock.call('arches = x86_64\n'),
                               mock.call('format = docker,qcow2\n'),
                               mock.call('kickstart = test-kickstart\n'),
                               mock.call('ksurl = git://example.com/ks.git\n'),
                               mock.call('distro = test-distro\n'),
                               mock.call('\n')])

    def test_get_image_build_paths(self):

        # The data for this tests is obtained from the actual Koji build. It
        # includes lots of fields that are not used, but for the sake of
        # completeness is fully preserved.

        getTaskChildren_data = {
            12387273: [
                {
                    'arch': 'i386',
                    'awaited': False,
                    'channel_id': 12,
                    'completion_time': '2016-01-03 05:34:08.374262',
                    'completion_ts': 1451799248.37426,
                    'create_time': '2016-01-03 05:15:20.311599',
                    'create_ts': 1451798120.3116,
                    'host_id': 158,
                    'id': 12387276,
                    'label': 'i386',
                    'method': 'createImage',
                    'owner': 131,
                    'parent': 12387273,
                    'priority': 19,
                    'request': [
                        'Fedora-Cloud-Base',
                        '23',
                        '20160103',
                        'i386',
                        {
                            'build_tag': 299,
                            'build_tag_name': 'f23-build',
                            'dest_tag': 294,
                            'dest_tag_name': 'f23-updates-candidate',
                            'id': 144,
                            'name': 'f23-candidate'
                        },
                        299,
                        {
                            'create_event': 14011966,
                            'create_ts': 1451761803.33528,
                            'creation_time': '2016-01-02 19:10:03.335283',
                            'id': 563977,
                            'state': 1
                        },
                        'http://infrastructure.fedoraproject.org/pub/alt/releases/23/Cloud/i386/os/',
                        {
                            'disk_size': '3',
                            'distro': 'Fedora-20',
                            'format': ['qcow2', 'raw-xz'],
                            'kickstart': 'work/cli-image/1451798116.800155.wYJWTVHw/fedora-cloud-base-2878aa0.ks',
                            'release': '20160103',
                            'repo': ['http://infrastructure.fedoraproject.org/pub/alt/releases/23/Cloud/$arch/os/',
                                     'http://infrastructure.fedoraproject.org/pub/fedora/linux/updates/23/$arch/'],
                            'scratch': True
                        }
                    ],
                    'start_time': '2016-01-03 05:15:29.828081',
                    'start_ts': 1451798129.82808,
                    'state': 2,
                    'waiting': None,
                    'weight': 2.0
                }, {
                    'arch': 'x86_64',
                    'awaited': False,
                    'channel_id': 12,
                    'completion_time': '2016-01-03 05:33:20.066366',
                    'completion_ts': 1451799200.06637,
                    'create_time': '2016-01-03 05:15:20.754201',
                    'create_ts': 1451798120.7542,
                    'host_id': 156,
                    'id': 12387277,
                    'label': 'x86_64',
                    'method': 'createImage',
                    'owner': 131,
                    'parent': 12387273,
                    'priority': 19,
                    'request': [
                        'Fedora-Cloud-Base',
                        '23',
                        '20160103',
                        'x86_64',
                        {
                            'build_tag': 299,
                            'build_tag_name': 'f23-build',
                            'dest_tag': 294,
                            'dest_tag_name': 'f23-updates-candidate',
                            'id': 144,
                            'name': 'f23-candidate'
                        },
                        299,
                        {
                            'create_event': 14011966,
                            'create_ts': 1451761803.33528,
                            'creation_time': '2016-01-02 19:10:03.335283',
                            'id': 563977,
                            'state': 1
                        },
                        'http://infrastructure.fedoraproject.org/pub/alt/releases/23/Cloud/x86_64/os/',
                        {
                            'disk_size': '3',
                            'distro': 'Fedora-20',
                            'format': ['qcow2', 'raw-xz'],
                            'kickstart': 'work/cli-image/1451798116.800155.wYJWTVHw/fedora-cloud-base-2878aa0.ks',
                            'release': '20160103',
                            'repo': ['http://infrastructure.fedoraproject.org/pub/alt/releases/23/Cloud/$arch/os/',
                                     'http://infrastructure.fedoraproject.org/pub/fedora/linux/updates/23/$arch/'],
                            'scratch': True
                        }
                    ],
                    'start_time': '2016-01-03 05:15:35.196043',
                    'start_ts': 1451798135.19604,
                    'state': 2,
                    'waiting': None,
                    'weight': 2.0
                }
            ]
        }

        getTaskResult_data = {
            12387276: {
                'arch': 'i386',
                'files': ['tdl-i386.xml',
                          'fedora-cloud-base-2878aa0.ks',
                          'koji-f23-build-12387276-base.ks',
                          'libvirt-qcow2-i386.xml',
                          'Fedora-Cloud-Base-23-20160103.i386.qcow2',
                          'libvirt-raw-xz-i386.xml',
                          'Fedora-Cloud-Base-23-20160103.i386.raw.xz'],
                'logs': ['oz-i386.log'],
                'name': 'Fedora-Cloud-Base',
                'release': '20160103',
                'rpmlist': [],
                'task_id': 12387276,
                'version': '23'
            },
            12387277: {
                'arch': 'x86_64',
                'files': ['tdl-x86_64.xml',
                          'fedora-cloud-base-2878aa0.ks',
                          'koji-f23-build-12387277-base.ks',
                          'libvirt-qcow2-x86_64.xml',
                          'Fedora-Cloud-Base-23-20160103.x86_64.qcow2',
                          'libvirt-raw-xz-x86_64.xml',
                          'Fedora-Cloud-Base-23-20160103.x86_64.raw.xz'],
                'logs': ['oz-x86_64.log'],
                'name': 'Fedora-Cloud-Base',
                'release': '20160103',
                'rpmlist': [],
                'task_id': 12387277,
                'version': '23'
            }

        }

        self.koji.koji_proxy = mock.Mock(
            getTaskChildren=mock.Mock(side_effect=lambda task_id, request: getTaskChildren_data.get(task_id)),
            getTaskResult=mock.Mock(side_effect=lambda task_id: getTaskResult_data.get(task_id))
        )
        result = self.koji.get_image_build_paths(12387273)
        self.assertItemsEqual(result.keys(), ['i386', 'x86_64'])
        self.maxDiff = None
        self.assertItemsEqual(result['i386'],
                              ['/koji/task/12387276/tdl-i386.xml',
                               '/koji/task/12387276/fedora-cloud-base-2878aa0.ks',
                               '/koji/task/12387276/koji-f23-build-12387276-base.ks',
                               '/koji/task/12387276/libvirt-qcow2-i386.xml',
                               '/koji/task/12387276/Fedora-Cloud-Base-23-20160103.i386.qcow2',
                               '/koji/task/12387276/libvirt-raw-xz-i386.xml',
                               '/koji/task/12387276/Fedora-Cloud-Base-23-20160103.i386.raw.xz'])
        self.assertItemsEqual(result['x86_64'],
                              ['/koji/task/12387277/tdl-x86_64.xml',
                               '/koji/task/12387277/fedora-cloud-base-2878aa0.ks',
                               '/koji/task/12387277/koji-f23-build-12387277-base.ks',
                               '/koji/task/12387277/libvirt-qcow2-x86_64.xml',
                               '/koji/task/12387277/Fedora-Cloud-Base-23-20160103.x86_64.qcow2',
                               '/koji/task/12387277/libvirt-raw-xz-x86_64.xml',
                               '/koji/task/12387277/Fedora-Cloud-Base-23-20160103.x86_64.raw.xz'])


if __name__ == "__main__":
    unittest.main()