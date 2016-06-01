#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import mock
import os
import sys
import unittest
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.phases.pkgset.sources import source_koji
from tests import helpers

EVENT_INFO = {'id': 15681980, 'ts': 1460956382.81936}
TAG_INFO = {
    "maven_support": False,
    "locked": False,
    "name": "f25",
    "extra": {
        "mock.package_manager": "dnf"
    },
    "perm": None,
    "id": 335,
    "arches": None,
    "maven_include_all": None,
    "perm_id": None
}


class TestGetKojiEvent(helpers.PungiTestCase):

    def setUp(self):
        super(TestGetKojiEvent, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})

        self.event_file = self.topdir + '/work/global/koji-event'

    def test_use_preconfigured_event(self):
        koji_wrapper = mock.Mock()
        self.compose.koji_event = 123456
        self.compose.DEBUG = False

        koji_wrapper.koji_proxy.getEvent.return_value = EVENT_INFO

        event = source_koji.get_koji_event_info(self.compose, koji_wrapper)

        self.assertEqual(event, EVENT_INFO)
        self.assertItemsEqual(
            koji_wrapper.mock_calls,
            [mock.call.koji_proxy.getEvent(123456)])
        with open(self.event_file) as f:
            self.assertEqual(json.load(f), EVENT_INFO)

    def test_gets_last_event(self):
        self.compose.DEBUG = False
        self.compose.koji_event = None
        koji_wrapper = mock.Mock()

        koji_wrapper.koji_proxy.getLastEvent.return_value = EVENT_INFO

        event = source_koji.get_koji_event_info(self.compose, koji_wrapper)

        self.assertEqual(event, EVENT_INFO)
        self.assertItemsEqual(
            koji_wrapper.mock_calls,
            [mock.call.koji_proxy.getLastEvent()])
        with open(self.event_file) as f:
            self.assertEqual(json.load(f), EVENT_INFO)

    def test_gets_last_event_in_debug_mode(self):
        self.compose.DEBUG = True
        self.compose.koji_event = None
        koji_wrapper = mock.Mock()
        helpers.touch(self.event_file, json.dumps(EVENT_INFO))

        event = source_koji.get_koji_event_info(self.compose, koji_wrapper)

        self.assertEqual(event, EVENT_INFO)
        self.assertItemsEqual(koji_wrapper.mock_calls, [])
        with open(self.event_file) as f:
            self.assertEqual(json.load(f), EVENT_INFO)


class TestGetKojiTagInfo(helpers.PungiTestCase):
    def setUp(self):
        super(TestGetKojiTagInfo, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {
            'pkgset_koji_tag': 'f25'
        })
        self.compose.DEBUG = False
        self.tag_file = os.path.join(self.topdir, 'work', 'global', 'koji-tag')
        self.koji_wrapper = mock.Mock()

    def test_get_tag_info(self):
        self.koji_wrapper.koji_proxy.getTag.return_value = TAG_INFO

        tag_info = source_koji.get_koji_tag_info(self.compose, self.koji_wrapper)

        self.assertEqual(tag_info, TAG_INFO)
        self.assertItemsEqual(
            self.koji_wrapper.mock_calls,
            [mock.call.koji_proxy.getTag('f25')]
        )
        with open(self.tag_file) as f:
            self.assertEqual(json.load(f), TAG_INFO)

    def test_bad_tag_name(self):
        self.koji_wrapper.koji_proxy.getTag.return_value = None

        with self.assertRaises(ValueError) as ctx:
            source_koji.get_koji_tag_info(self.compose, self.koji_wrapper)

        self.assertIn('Unknown', str(ctx.exception))

    def test_get_tag_info_in_debug_mode(self):
        self.compose.DEBUG = True
        helpers.touch(self.tag_file, json.dumps(TAG_INFO))

        tag_info = source_koji.get_koji_tag_info(self.compose, self.koji_wrapper)

        self.assertEqual(tag_info, TAG_INFO)
        self.assertItemsEqual(self.koji_wrapper.mock_calls, [])
        with open(self.tag_file) as f:
            self.assertEqual(json.load(f), TAG_INFO)


class TestPopulateGlobalPkgset(helpers.PungiTestCase):
    def setUp(self):
        super(TestPopulateGlobalPkgset, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {
            'pkgset_koji_tag': 'f25',
            'sigkeys': mock.Mock(),
        })
        self.compose.DEBUG = False
        self.koji_wrapper = mock.Mock()
        self.pkgset_path = os.path.join(self.topdir, 'work', 'global', 'pkgset_global.pickle')

    @mock.patch('cPickle.dumps')
    @mock.patch('pungi.phases.pkgset.pkgsets.KojiPackageSet')
    def test_populate(self, KojiPackageSet, pickle_dumps):

        pickle_dumps.return_value = 'DATA'

        orig_pkgset = KojiPackageSet.return_value

        pkgset = source_koji.populate_global_pkgset(
            self.compose, self.koji_wrapper, '/prefix', 'f25', 123456)

        self.assertIs(pkgset, orig_pkgset)
        self.assertEqual(
            pkgset.mock_calls,
            [mock.call.populate('f25', 123456, inherit=True),
             mock.call.save_file_list(self.topdir + '/work/global/package_list/global.conf',
                                      remove_path_prefix='/prefix')])
        self.assertItemsEqual(pickle_dumps.call_args_list,
                              [mock.call(orig_pkgset)])
        with open(self.pkgset_path) as f:
            self.assertEqual(f.read(), 'DATA')

    @mock.patch('cPickle.load')
    def test_populate_in_debug_mode(self, pickle_load):
        helpers.touch(self.pkgset_path, 'DATA')
        self.compose.DEBUG = True

        pickle_load.return_value

        with mock.patch('pungi.phases.pkgset.sources.source_koji.open',
                        mock.mock_open(), create=True) as m:
            pkgset = source_koji.populate_global_pkgset(
                self.compose, self.koji_wrapper, '/prefix', 'f25', 123456)

        self.assertEqual(pickle_load.call_args_list,
                         [mock.call(m.return_value)])
        self.assertIs(pkgset, pickle_load.return_value)
        self.assertEqual(
            pkgset.mock_calls,
            [mock.call.save_file_list(self.topdir + '/work/global/package_list/global.conf',
                                      remove_path_prefix='/prefix')])


class TestGetPackageSetFromKoji(helpers.PungiTestCase):
    def setUp(self):
        super(TestGetPackageSetFromKoji, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {
            'pkgset_koji_tag': 'f25',
        })
        self.compose.koji_event = None
        self.compose.DEBUG = False
        self.koji_wrapper = mock.Mock()
        self.koji_wrapper.koji_proxy.getLastEvent.return_value = EVENT_INFO
        self.koji_wrapper.koji_proxy.getTag.return_value = TAG_INFO

    @mock.patch('pungi.phases.pkgset.sources.source_koji.create_arch_repos')
    @mock.patch('pungi.phases.pkgset.sources.source_koji.create_global_repo')
    @mock.patch('pungi.phases.pkgset.sources.source_koji.populate_arch_pkgsets')
    @mock.patch('pungi.phases.pkgset.sources.source_koji.populate_global_pkgset')
    def test_get_package_sets(self, pgp, pap, cgr, car):
        expected = {'x86_64': mock.Mock()}
        pap.return_value = expected
        expected['global'] = pgp.return_value

        pkgsets = source_koji.get_pkgset_from_koji(self.compose, self.koji_wrapper, '/prefix')

        self.assertItemsEqual(
            self.koji_wrapper.koji_proxy.mock_calls,
            [mock.call.getLastEvent(),
             mock.call.getTag('f25')]
        )
        self.assertEqual(pgp.call_args_list,
                         [mock.call(self.compose, self.koji_wrapper, '/prefix',
                                    TAG_INFO, EVENT_INFO)])
        self.assertEqual(pap.call_args_list,
                         [mock.call(self.compose, '/prefix', pgp.return_value)])
        self.assertEqual(cgr.call_args_list,
                         [mock.call(self.compose, '/prefix')])
        self.assertItemsEqual(car.call_args_list,
                              [mock.call(self.compose, 'x86_64', '/prefix'),
                               mock.call(self.compose, 'amd64', '/prefix')])

        self.assertEqual(pkgsets, expected)


class TestSourceKoji(helpers.PungiTestCase):

    @mock.patch('pungi.phases.pkgset.sources.source_koji.get_pkgset_from_koji')
    @mock.patch('pungi.wrappers.kojiwrapper.KojiWrapper')
    def test_run(self, KojiWrapper, gpfk):
        compose = helpers.DummyCompose(self.topdir, {
            'koji_profile': 'koji'
        })
        KojiWrapper.return_value.koji_module.config.topdir = '/prefix'

        phase = source_koji.PkgsetSourceKoji(compose)
        pkgsets, path_prefix = phase()

        self.assertEqual(pkgsets, gpfk.return_value)
        self.assertEqual(path_prefix, '/prefix/')
        self.assertItemsEqual(KojiWrapper.mock_calls,
                              [mock.call('koji')])


if __name__ == "__main__":
    unittest.main()