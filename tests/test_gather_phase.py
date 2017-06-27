# -*- coding: utf-8 -*-

import copy
import mock
import os
import sys

try:
    import unittest2 as unittest
except ImportError:
    import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pungi.phases import gather
from pungi.phases.gather import _mk_pkg_map
from tests import helpers


class MockPackageSet(dict):
    def __init__(self, *args):
        for pkg in args:
            self[pkg.path] = pkg


class MockPkg(object):
    def __init__(self, path, is_system_release=False):
        self.path = path
        self.is_system_release = is_system_release
        filename = os.path.basename(path)
        self.nvr, self.arch, _ = filename.rsplit('.', 2)
        self.name, self.version, self.release = self.nvr.rsplit('-', 2)

    def __repr__(self):
        return self.nvr


def _join(a, *rest):
    res = copy.deepcopy(a)
    for b in rest:
        for key in res:
            res[key].extend(b[key])
    return res


class TestGatherWrapper(helpers.PungiTestCase):

    def setUp(self):
        super(TestGatherWrapper, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})
        self.package_set = mock.Mock()
        self.variant = helpers.MockVariant(
            uid='Server', arches=['x86_64'], type='variant')
        self.optional = helpers.MockVariant(
            uid='Server-optional', arches=['x86_64'], type='optional', parent=self.variant)
        self.addon = helpers.MockVariant(
            uid='Server-HA', arches=['x86_64'], type='addon', parent=self.variant)
        self.lp = helpers.MockVariant(
            uid='Server-LP', arches=['x86_64'], type='layered-product', parent=self.variant)
        self.server_packages = {
            "rpm": [{'path': '/build/foo-1.0-1.x86_64.rpm', 'flags': ['input']}],
            "srpm": [{'path': '/build/foo-1.0-1.src.rpm', 'flags': []}],
            "debuginfo": [{'path': '/build/foo-debuginfo-1.0-1.x86_64.rpm', 'flags': []}],
        }
        self.maxDiff = None

    def _dummy_gather(self, compose, arch, variant, package_sets, **kwargs):
        self.assertEqual(
            package_sets, self.package_set,
            'Called gather_packages on %s.%s with bad package sets' % (variant.uid, arch))
        if variant.uid == 'Server':
            return self.server_packages
        if variant.uid == 'Server-optional':
            return self.optional_packages
        if variant.uid == 'Server-HA':
            return self.addon_packages
        if variant.uid == 'Server-LP':
            return self.lp_packages
        self.assertFalse('This should not be reached - variant %s' % variant.uid)

    @mock.patch('pungi.phases.gather.write_packages')
    @mock.patch('pungi.phases.gather.gather_packages')
    def test_single_variant(self, gather_packages, write_packages):
        # There is only one variant: exactly the packages returned by gather
        # method should be returned without modifications.
        self.compose.all_variants = {'Server': self.variant}

        expected_server_packages = copy.deepcopy(self.server_packages)

        gather_packages.side_effect = self._dummy_gather

        result = gather.gather_wrapper(self.compose, self.package_set, '/build')

        self.assertEqual(result, {'x86_64': {'Server': expected_server_packages}})
        self.assertEqual(
            write_packages.call_args_list,
            [mock.call(self.compose, 'x86_64', self.variant,
                       expected_server_packages, path_prefix='/build')])

    @mock.patch('pungi.phases.gather.write_packages')
    @mock.patch('pungi.phases.gather.gather_packages')
    def test_addon(self, gather_packages, write_packages):
        # Addon has all packages that parent has, plus one extra input package
        # and one fulltree-exclude package. Only the input one should remain in
        # addon, and the fulltree one should move to parent.
        self.compose.all_variants = {'Server': self.variant, 'Server-HA': self.addon}

        move_to_parent = {'path': '/build/foo-common-1.0-1.x86_64.rpm', 'flags': ['fulltree-exclude']}
        keep_in_addon = {'path': '/build/bar-1.0-1.x86_64.rpm', 'flags': ['input']}
        expected_server_packages = _join(self.server_packages, _mk_pkg_map([move_to_parent]))
        self.addon_packages = _join(self.server_packages, _mk_pkg_map([keep_in_addon, move_to_parent]))
        expected_addon_packages = _mk_pkg_map(
            [{'path': '/build/bar-1.0-1.x86_64.rpm', 'flags': ['input']}])

        gather_packages.side_effect = self._dummy_gather

        result = gather.gather_wrapper(self.compose, self.package_set, '/build')

        self.assertEqual(result, {'x86_64': {'Server': expected_server_packages,
                                             'Server-HA': expected_addon_packages}})
        self.assertItemsEqual(
            write_packages.call_args_list,
            [mock.call(self.compose, 'x86_64', self.variant,
                       expected_server_packages, path_prefix='/build'),
             mock.call(self.compose, 'x86_64', self.addon,
                       expected_addon_packages, path_prefix='/build')])

    @mock.patch('pungi.phases.gather.write_packages')
    @mock.patch('pungi.phases.gather.gather_packages')
    def test_layered_product(self, gather_packages, write_packages):
        # This test is pretty much identical to the one for addon.
        self.compose.all_variants = {'Server': self.variant, 'Server-LP': self.lp}

        move_to_parent = {'path': '/build/foo-common-1.0-1.x86_64.rpm', 'flags': ['fulltree-exclude']}
        keep_in_lp = {'path': '/build/bar-1.0-1.x86_64.rpm', 'flags': ['input']}
        expected_server_packages = copy.deepcopy(self.server_packages)
        expected_server_packages['rpm'].append(move_to_parent)
        self.lp_packages = _join(self.server_packages, _mk_pkg_map([keep_in_lp, move_to_parent]))
        expected_lp_packages = _mk_pkg_map(
            [{'path': '/build/bar-1.0-1.x86_64.rpm', 'flags': ['input']}])

        gather_packages.side_effect = self._dummy_gather

        result = gather.gather_wrapper(self.compose, self.package_set, '/build')

        self.assertEqual(result, {'x86_64': {'Server': expected_server_packages,
                                             'Server-LP': expected_lp_packages}})
        self.assertItemsEqual(
            write_packages.call_args_list,
            [mock.call(self.compose, 'x86_64', self.variant,
                       expected_server_packages, path_prefix='/build'),
             mock.call(self.compose, 'x86_64', self.lp,
                       expected_lp_packages, path_prefix='/build')])

    @mock.patch('pungi.phases.gather.write_packages')
    @mock.patch('pungi.phases.gather.gather_packages')
    def test_optional(self, gather_packages, write_packages):
        # All packages in optional that are present in parent should be removed
        # from optional. There is no move to parent here.
        self.compose.all_variants = {'Server': self.variant, 'Server-optional': self.optional}

        expected_server_packages = copy.deepcopy(self.server_packages)
        self.optional_packages = _join(self.server_packages, _mk_pkg_map(
            [{'path': '/build/bar-1.0-1.x86_64.rpm', 'flags': ['input']},
             {'path': '/build/foo-common-1.0-1.x86_64.rpm', 'flags': ['fulltree-exclude']}]))
        expected_optional_packages = _mk_pkg_map(
            [{'path': '/build/bar-1.0-1.x86_64.rpm', 'flags': ['input']}])

        gather_packages.side_effect = self._dummy_gather

        result = gather.gather_wrapper(self.compose, self.package_set, '/build')

        self.assertEqual(result, {'x86_64': {'Server': expected_server_packages,
                                             'Server-optional': expected_optional_packages}})
        self.assertItemsEqual(
            write_packages.call_args_list,
            [mock.call(self.compose, 'x86_64', self.variant,
                       expected_server_packages, path_prefix='/build'),
             mock.call(self.compose, 'x86_64', self.optional,
                       expected_optional_packages, path_prefix='/build')])

    @mock.patch('pungi.phases.gather.write_packages')
    @mock.patch('pungi.phases.gather.gather_packages')
    def test_all(self, gather_packages, write_packages):
        # Addon contains an extra package compared to parent. Layered product
        # contains an extra package compared to addon. Optional has one extra
        # package on it's own compared to addon. Only the one extra package
        # should remain in all non-parent variants.
        #
        # There are also two packages that should move to parent variant. Addon
        # has one of them, layered product has both.
        self.compose.all_variants = {'Server': self.variant, 'Server-optional': self.optional,
                                     'Server-HA': self.addon, 'Server-LP': self.lp}

        addon_extra_package = {'path': '/build/foo-addon-1.0.1-1.noarch.rpm', 'flags': []}
        lp_extra_package = {'path': '/build/foo-layer-1.0.1-1.noarch.rpm', 'flags': []}
        optional_extra_package = {'path': '/build/foo-optional-1.0.1-1.noarch.rpm', 'flags': []}
        move_from_addon = {'path': '/build/foo-addon-contrib-1.0-1.noarch.rpm', 'flags': ['fulltree-exclude']}
        move_from_lp = {'path': '/build/foo-layer-contrib-1.0-1.noarch.rpm', 'flags': ['fulltree-exclude']}

        self.addon_packages = _join(self.server_packages, _mk_pkg_map(
            [addon_extra_package, move_from_addon]))
        self.lp_packages = _join(self.addon_packages, _mk_pkg_map(
            [lp_extra_package, move_from_lp]))
        self.optional_packages = _join(self.lp_packages, _mk_pkg_map(
            [optional_extra_package]))

        expected_server_packages = _join(self.server_packages, _mk_pkg_map(
            [move_from_addon, move_from_lp]))
        expected_addon_packages = _mk_pkg_map([addon_extra_package])
        expected_lp_packages = _mk_pkg_map([lp_extra_package])
        expected_optional_packages = _mk_pkg_map([optional_extra_package])

        gather_packages.side_effect = self._dummy_gather

        result = gather.gather_wrapper(self.compose, self.package_set, '/build')

        self.assertEqual(result, {'x86_64': {'Server': expected_server_packages,
                                             'Server-optional': expected_optional_packages,
                                             'Server-HA': expected_addon_packages,
                                             'Server-LP': expected_lp_packages}})
        self.assertItemsEqual(
            write_packages.call_args_list,
            [mock.call(self.compose, 'x86_64', self.compose.all_variants['Server'],
                       expected_server_packages, path_prefix='/build'),
             mock.call(self.compose, 'x86_64', self.compose.all_variants['Server-optional'],
                       expected_optional_packages, path_prefix='/build'),
             mock.call(self.compose, 'x86_64', self.compose.all_variants['Server-HA'],
                       expected_addon_packages, path_prefix='/build'),
             mock.call(self.compose, 'x86_64', self.compose.all_variants['Server-LP'],
                       expected_lp_packages, path_prefix='/build')])

    @mock.patch('pungi.phases.gather.write_packages')
    @mock.patch('pungi.phases.gather.gather_packages')
    def test_keep_srpm_in_lp(self, gather_packages, write_packages):
        # There is one binary and source package in addon and lp but not in
        # parent. Addon should remain unchanged and the binary package should
        # disappear from lp.
        # This seems peculiar and may not be correct.
        self.compose.all_variants = {'Server': self.variant,
                                     'Server-HA': self.addon,
                                     'Server-LP': self.lp}

        addon_extra_package = {'path': '/build/foo-addon-1.0.1-1.noarch.rpm', 'flags': []}
        addon_extra_source = {'path': '/build/foo-addon-1.0.1-1.src.rpm', 'flags': []}

        self.addon_packages = _join(self.server_packages, _mk_pkg_map(
            [addon_extra_package], [addon_extra_source]))
        self.lp_packages = _join(self.addon_packages)

        expected_server_packages = _join(self.server_packages)
        expected_addon_packages = _mk_pkg_map([addon_extra_package], [addon_extra_source])
        expected_lp_packages = _mk_pkg_map([], [addon_extra_source])

        gather_packages.side_effect = self._dummy_gather

        result = gather.gather_wrapper(self.compose, self.package_set, '/build')

        self.assertEqual(result, {'x86_64': {'Server': expected_server_packages,
                                             'Server-HA': expected_addon_packages,
                                             'Server-LP': expected_lp_packages}})
        self.assertItemsEqual(
            write_packages.call_args_list,
            [mock.call(self.compose, 'x86_64', self.compose.all_variants['Server'],
                       expected_server_packages, path_prefix='/build'),
             mock.call(self.compose, 'x86_64', self.compose.all_variants['Server-HA'],
                       expected_addon_packages, path_prefix='/build'),
             mock.call(self.compose, 'x86_64', self.compose.all_variants['Server-LP'],
                       expected_lp_packages, path_prefix='/build')])


class TestGetSystemRelease(unittest.TestCase):
    def setUp(self):
        self.compose = mock.Mock()
        self.variant = helpers.MockVariant(uid='Server', arches=['x86_64'],
                                           type='variant')
        self.addon = helpers.MockVariant(uid='Server-HA', arches=['x86_64'],
                                         type='addon', parent=self.variant)

    def test_no_package_set(self):
        self.assertEqual(
            gather.get_system_release_packages(self.compose, 'x86_64',
                                               self.variant, None),
            (set(), set())
        )

    def test_no_arch_in_package_set(self):
        self.assertEqual(
            gather.get_system_release_packages(self.compose, 'x86_64',
                                               self.variant, {}),
            (set(), set())
        )

    def test_no_system_release_package(self):
        pkgset = MockPackageSet(MockPkg('/build/bash-1.0.0-1.x86_64.rpm'))
        packages, filter_packages = gather.get_system_release_packages(
            self.compose, 'x86_64', self.variant, {'x86_64': pkgset})

        self.assertItemsEqual(packages, [])
        self.assertItemsEqual(filter_packages, [])

    def test_picks_single(self):
        pkgset = MockPackageSet(
            MockPkg('/build/dummy-1.0.0-1.x86_64.rpm', is_system_release=True),
        )
        packages, filter_packages = gather.get_system_release_packages(
            self.compose, 'x86_64', self.variant, {'x86_64': pkgset})

        self.assertItemsEqual(packages, [('dummy', None)])
        self.assertItemsEqual(filter_packages, [])

    def test_prefers_variant(self):
        pkgset = MockPackageSet(
            MockPkg('/build/system-release-1.0.0-1.x86_64.rpm', is_system_release=True),
            MockPkg('/build/system-release-server-1.0.0-1.x86_64.rpm', is_system_release=True),
        )
        packages, filter_packages = gather.get_system_release_packages(
            self.compose, 'x86_64', self.variant, {'x86_64': pkgset})

        self.assertItemsEqual(packages, [('system-release-server', None)])
        self.assertItemsEqual(filter_packages, [('system-release', None)])

    def test_no_best_match(self):
        pkgset = MockPackageSet(
            MockPkg('/build/system-release-foo-1.0.0-1.x86_64.rpm', is_system_release=True),
            MockPkg('/build/system-release-bar-1.0.0-1.x86_64.rpm', is_system_release=True),
        )
        packages, filter_packages = gather.get_system_release_packages(
            self.compose, 'x86_64', self.variant, {'x86_64': pkgset})

        # In this case a random package is picked, so let's check that both
        # list contain one package and that they are different.
        self.assertEqual(len(packages), 1)
        self.assertEqual(len(filter_packages), 1)
        self.assertNotEqual(packages, filter_packages)

    def test_optional_picks_parent(self):
        pkgset = MockPackageSet(
            MockPkg('/build/system-release-1.0.0-1.x86_64.rpm', is_system_release=True),
            MockPkg('/build/system-release-server-1.0.0-1.x86_64.rpm', is_system_release=True),
            MockPkg('/build/system-release-client-1.0.0-1.x86_64.rpm', is_system_release=True),
        )
        packages, filter_packages = gather.get_system_release_packages(
            self.compose, 'x86_64', self.addon, {'x86_64': pkgset})

        self.assertItemsEqual(packages, [('system-release-server', None)])
        self.assertItemsEqual(filter_packages,
                              [('system-release-client', None),
                               ('system-release', None)])


class TestTrimPackages(unittest.TestCase):
    def setUp(self):
        self.compose = mock.Mock()
        self.variant = helpers.MockVariant(uid='Server', arches=['x86_64'],
                                           type='variant')
        self.addon = helpers.MockVariant(uid='Server-HA', arches=['x86_64'],
                                         type='addon', parent=self.variant)

    def test_trim_toplevel(self):
        self.assertIsNone(gather.trim_packages(self.compose, 'x86_64', self.variant, {}))

    def test_remove_package_explicitly(self):
        to_remove = {'path': '/build/required-1.0.0-1.x86_64.rpm', 'flags': ['input']}
        to_keep = {'path': '/build/empty-1.0.0-1.x86_64.rpm', 'flags': []}
        pkg_map = _mk_pkg_map([to_remove, to_keep])
        addon_pkgs, moved_to_parent, removed_pkgs = gather.trim_packages(
            self.compose, 'x86_64', self.addon, pkg_map, remove_pkgs={'rpm': ['required']})

        self.assertEqual(removed_pkgs, _mk_pkg_map([to_remove]))
        self.assertEqual(addon_pkgs, _mk_pkg_map(set(['empty']), iterable_class=set))
        self.assertEqual(moved_to_parent, _mk_pkg_map())
        self.assertEqual(pkg_map, _mk_pkg_map([to_keep]))

    def test_remove_package_present_in_parent(self):
        # packages present in parent will be removed from addon
        parent_pkgs = {
            'rpm': [
                ('wanted', 'x86_64'),
            ]
        }
        to_remove = {'path': '/build/wanted-1.0.0-1.x86_64.rpm', 'flags': []}
        pkg_map = _mk_pkg_map([to_remove])
        addon_pkgs, moved_to_parent, removed_pkgs = gather.trim_packages(
            self.compose, 'x86_64', self.addon, pkg_map, parent_pkgs=parent_pkgs)

        self.assertEqual(removed_pkgs, _mk_pkg_map([to_remove]))
        self.assertEqual(addon_pkgs, _mk_pkg_map(iterable_class=set))
        self.assertEqual(moved_to_parent, _mk_pkg_map())
        self.assertEqual(pkg_map, _mk_pkg_map())

    def test_move_package_to_parent(self):
        # fulltree-exclude packages in addon only will move to parent
        to_move = {'path': '/build/wanted-1.0.0-1.x86_64.rpm', 'flags': ['fulltree-exclude']}
        pkg_map = _mk_pkg_map([to_move])
        addon_pkgs, moved_to_parent, removed_pkgs = gather.trim_packages(
            self.compose, 'x86_64', self.addon, pkg_map, parent_pkgs={'rpm': []})

        self.assertEqual(removed_pkgs, _mk_pkg_map())
        self.assertEqual(addon_pkgs, _mk_pkg_map(iterable_class=set))
        self.assertEqual(moved_to_parent, _mk_pkg_map([to_move]))
        self.assertEqual(pkg_map, _mk_pkg_map())

    def test_keep_explicit_input_in_addon(self):
        # fulltree-exclude packages explictly in addon will be kept in addon
        parent_pkgs = {'rpm': []}
        pkg = {'path': '/build/wanted-1.0.0-1.x86_64.rpm', 'flags': ['fulltree-exclude', 'input']}
        pkg_map = _mk_pkg_map([pkg])
        addon_pkgs, moved_to_parent, removed_pkgs = gather.trim_packages(
            self.compose, 'x86_64', self.addon, pkg_map, parent_pkgs=parent_pkgs)

        self.assertEqual(removed_pkgs, _mk_pkg_map())
        self.assertEqual(addon_pkgs, _mk_pkg_map(set(['wanted']), iterable_class=set))
        self.assertEqual(moved_to_parent, _mk_pkg_map())
        self.assertEqual(pkg_map, _mk_pkg_map([pkg]))


class TestWritePackages(helpers.PungiTestCase):
    def test_write_packages(self):
        self.compose = helpers.DummyCompose(self.topdir, {})
        pkg_map = {
            'rpm': [
                {'path': '/build/foo-1.0-1.x86_64.rpm', 'flags': []},
                {'path': '/build/foo-common-1.0-1.x86_64.rpm', 'flags': []},
                {'path': '/alt/build/bar-1.0-1.noarch.rpm', 'flags': []},
            ],
            'srpm': [
                {'path': '/build/foo-1.0-1.src.rpm', 'flags': []},
                {'path': '/alt/build/bar-1.0-1.src.rpm', 'flags': []},
            ],
            'debuginfo': [
                {'path': '/build/foo-debuginfo-1.0-1.x86_64.rpm', 'flags': []},
            ],
        }
        gather.write_packages(self.compose, 'x86_64', self.compose.variants['Server'], pkg_map, '/alt')

        with open(os.path.join(self.topdir, 'work', 'x86_64', 'package_list',
                               'Server.x86_64.rpm.conf')) as f:
            self.assertItemsEqual(f.read().strip().split('\n'),
                                  ['/build/foo-1.0-1.x86_64.rpm',
                                   '/build/foo-common-1.0-1.x86_64.rpm',
                                   '/build/bar-1.0-1.noarch.rpm'])

        with open(os.path.join(self.topdir, 'work', 'x86_64', 'package_list',
                               'Server.x86_64.srpm.conf')) as f:
            self.assertItemsEqual(f.read().strip().split('\n'),
                                  ['/build/foo-1.0-1.src.rpm',
                                   '/build/bar-1.0-1.src.rpm'])

        with open(os.path.join(self.topdir, 'work', 'x86_64', 'package_list',
                               'Server.x86_64.debuginfo.conf')) as f:
            self.assertItemsEqual(f.read().strip().split('\n'),
                                  ['/build/foo-debuginfo-1.0-1.x86_64.rpm'])


class TestGetVariantPackages(helpers.PungiTestCase):
    def test_no_variant(self):
        compose = helpers.DummyCompose(self.topdir, {})
        packages, groups, filter_packages = gather.get_variant_packages(
            compose, 'x86_64', None)
        self.assertItemsEqual(packages, [])
        self.assertItemsEqual(groups, [])
        self.assertItemsEqual(filter_packages, [])

    @mock.patch('pungi.phases.gather.get_gather_source')
    def test_just_source(self, get_gather_source):
        get_gather_source.return_value = mock.Mock(
            return_value=mock.Mock(return_value=(set(['foo']), set(['core'])))
        )
        compose = helpers.DummyCompose(self.topdir, {})

        packages, groups, filter_packages = gather.get_variant_packages(
            compose, 'x86_64', compose.variants['Server'])
        self.assertItemsEqual(packages, ['foo'])
        self.assertItemsEqual(groups, ['core'])
        self.assertItemsEqual(filter_packages, [])

    @mock.patch('pungi.phases.gather.get_gather_source')
    def test_filter_system_release(self, get_gather_source):
        get_gather_source.return_value = mock.Mock(
            return_value=mock.Mock(return_value=(set(), set()))
        )
        compose = helpers.DummyCompose(self.topdir, {})
        pkgset = MockPackageSet(
            MockPkg('/build/system-release-1.0.0-1.x86_64.rpm', is_system_release=True),
            MockPkg('/build/system-release-server-1.0.0-1.x86_64.rpm', is_system_release=True),
        )

        packages, groups, filter_packages = gather.get_variant_packages(
            compose, 'x86_64', compose.variants['Server'], package_sets={'x86_64': pkgset})
        self.assertItemsEqual(packages, [('system-release-server', None)])
        self.assertItemsEqual(groups, [])
        self.assertItemsEqual(filter_packages, [('system-release', None)])

    @mock.patch('pungi.phases.gather.get_gather_source')
    def test_disable_filter_system_release(self, get_gather_source):
        get_gather_source.return_value = mock.Mock(
            return_value=mock.Mock(return_value=(set([]), set([])))
        )
        compose = helpers.DummyCompose(self.topdir, {
            'filter_system_release_packages': False
        })
        pkgset = MockPackageSet(
            MockPkg('/build/system-release-1.0.0-1.x86_64.rpm', is_system_release=True),
            MockPkg('/build/system-release-server-1.0.0-1.x86_64.rpm', is_system_release=True),
        )

        packages, groups, filter_packages = gather.get_variant_packages(
            compose, 'x86_64', compose.variants['Server'], package_sets={'x86_64': pkgset})
        self.assertItemsEqual(packages, [])
        self.assertItemsEqual(groups, [])
        self.assertItemsEqual(filter_packages, [])

    @mock.patch('pungi.phases.gather.get_gather_source')
    def test_optional_gets_parent_and_addon(self, get_gather_source):
        compose = helpers.DummyCompose(self.topdir, {})
        compose.setup_optional()
        compose.setup_addon()

        def dummy_source(arch, variant):
            if variant.uid == 'Server':
                return (set(['server-pkg']), set(['server-group']))
            if variant.uid == 'Server-HA':
                return (set(['addon-pkg']), set(['addon-group']))
            if variant.uid == 'Server-optional':
                return (set(['opt-pkg']), set(['opt-group']))
            self.assertFalse('This should not be reached')

        get_gather_source.return_value = mock.Mock(
            return_value=mock.Mock(side_effect=dummy_source)
        )

        packages, groups, filter_packages = gather.get_variant_packages(
            compose, 'x86_64', compose.all_variants['Server-optional'])
        self.assertItemsEqual(packages, ['server-pkg', 'addon-pkg', 'opt-pkg'])
        self.assertItemsEqual(groups, ['server-group', 'addon-group', 'opt-group'])
        self.assertItemsEqual(filter_packages, [])

    @mock.patch('pungi.phases.gather.get_gather_source')
    def test_optional_does_not_inherit_filters(self, get_gather_source):
        compose = helpers.DummyCompose(self.topdir, {
            'filter_packages': [
                ('^Server(-HA)?$', {'*': ['filter-me']}),
            ]
        })
        compose.setup_optional()
        compose.setup_addon()

        get_gather_source.return_value = mock.Mock(
            return_value=mock.Mock(return_value=(set(), set()))
        )

        packages, groups, filter_packages = gather.get_variant_packages(
            compose, 'x86_64', compose.all_variants['Server-optional'])
        self.assertItemsEqual(packages, [])
        self.assertItemsEqual(groups, [])
        self.assertItemsEqual(filter_packages, [])

    @mock.patch('pungi.phases.gather.get_gather_source')
    def test_additional_packages(self, get_gather_source):
        compose = helpers.DummyCompose(self.topdir, {
            'additional_packages': [
                ('.*', {'*': ['pkg', 'foo.x86_64']}),
            ]
        })

        get_gather_source.return_value = mock.Mock(
            return_value=mock.Mock(return_value=(set(), set()))
        )

        packages, groups, filter_packages = gather.get_variant_packages(
            compose, 'x86_64', compose.all_variants['Server'])
        self.assertItemsEqual(packages, [('pkg', None), ('foo', 'x86_64')])
        self.assertItemsEqual(groups, [])
        self.assertItemsEqual(filter_packages, [])

    @mock.patch('pungi.phases.gather.get_gather_source')
    def test_additional_packages_incompatible_arch(self, get_gather_source):
        compose = helpers.DummyCompose(self.topdir, {
            'additional_packages': [
                ('.*', {'*': ['foo.ppc64']}),
            ]
        })

        get_gather_source.return_value = mock.Mock(
            return_value=mock.Mock(return_value=(set(), set()))
        )

        with self.assertRaises(ValueError) as ctx:
            packages, groups, filter_packages = gather.get_variant_packages(
                compose, 'x86_64', compose.all_variants['Server'])

        self.assertIn('Incompatible package arch', str(ctx.exception))


class TestGetParentPkgs(unittest.TestCase):
    def setUp(self):
        self.variant = helpers.MockVariant(uid='Server', arches=['x86_64'],
                                           type='variant')
        self.addon = helpers.MockVariant(uid='Server-HA', arches=['x86_64'],
                                         type='addon', parent=self.variant)

    def test_returns_empty_for_toplevel(self):
        pkg_map = mock.Mock()
        result = gather.get_parent_pkgs('x86_64', self.variant, pkg_map)
        self.assertEqual(result, _mk_pkg_map(iterable_class=set))

    def test_on_addon(self):
        pkg_map = {
            'x86_64': {
                'Server': {
                    'rpm': [
                        {'path': '/build/foo-1.0-1.x86_64.rpm', 'flags': []},
                    ],
                    'srpm': [
                        {'path': '/build/foo-1.0-1.src.rpm', 'flags': []},
                    ],
                    'debuginfo': [
                        {'path': '/build/foo-debuginfo-1.0-1.x86_64.rpm', 'flags': []},
                    ],
                }
            }
        }
        result = gather.get_parent_pkgs('x86_64', self.addon, pkg_map)
        self.assertEqual(result,
                         {'rpm': set([('foo', 'x86_64')]),
                          'srpm': set([('foo', 'src')]),
                          'debuginfo': set([('foo-debuginfo', 'x86_64')])})


class TestGatherPackages(helpers.PungiTestCase):
    @mock.patch('pungi.phases.gather.get_variant_packages')
    @mock.patch('pungi.phases.gather.get_gather_method')
    def test_no_extra_options(self, get_gather_method, get_variant_packages):
        packages, groups, filters = mock.Mock(), mock.Mock(), mock.Mock()
        get_variant_packages.return_value = (packages, groups, filters)
        compose = helpers.DummyCompose(self.topdir, {})
        pkg_set = mock.Mock()
        self.assertEqual(
            gather.gather_packages(compose, 'x86_64', compose.variants['Server'], pkg_set),
            get_gather_method.return_value.return_value.return_value
        )
        self.assertEqual(get_gather_method.call_args_list,
                         [mock.call(compose.conf['gather_method'])])
        self.assertEqual(get_variant_packages.call_args_list,
                         [mock.call(compose, 'x86_64', compose.variants['Server'], pkg_set)])
        self.assertEqual(
            get_gather_method.return_value.return_value.call_args_list,
            [mock.call('x86_64', compose.variants['Server'], packages, groups,
                       filters, set(), set(), pkg_set, fulltree_excludes=set(),
                       prepopulate=set())]
        )

    @mock.patch('pungi.phases.gather.get_variant_packages')
    def test_empty_variant(self, get_variant_packages):
        packages, groups, filters = mock.Mock(), mock.Mock(), mock.Mock()
        get_variant_packages.return_value = (packages, groups, filters)
        compose = helpers.DummyCompose(self.topdir, {})
        compose.variants['Server'].is_empty = True
        pkg_set = mock.Mock()
        self.assertEqual(
            gather.gather_packages(compose, 'x86_64', compose.variants['Server'], pkg_set),
            _mk_pkg_map()
        )
        self.assertEqual(get_variant_packages.call_args_list, [])

    @mock.patch('pungi.phases.gather.get_variant_packages')
    @mock.patch('pungi.phases.gather.get_gather_method')
    def test_multilib_white_black_list(self, get_gather_method, get_variant_packages):
        packages, groups, filters = mock.Mock(), mock.Mock(), mock.Mock()
        get_variant_packages.return_value = (packages, groups, filters)
        compose = helpers.DummyCompose(self.topdir, {
            'multilib_whitelist': {'*': ['white']},
            'multilib_blacklist': {'*': ['black']},
        })
        pkg_set = mock.Mock()
        self.assertEqual(
            gather.gather_packages(compose, 'x86_64', compose.variants['Server'], pkg_set),
            get_gather_method.return_value.return_value.return_value
        )
        self.assertEqual(get_gather_method.call_args_list,
                         [mock.call(compose.conf['gather_method'])])
        self.assertEqual(get_variant_packages.call_args_list,
                         [mock.call(compose, 'x86_64', compose.variants['Server'], pkg_set)])
        self.assertEqual(
            get_gather_method.return_value.return_value.call_args_list,
            [mock.call('x86_64', compose.variants['Server'], packages, groups,
                       filters, set(['white']), set(['black']), pkg_set,
                       fulltree_excludes=set(), prepopulate=set())]
        )


class TestWritePrepopulate(helpers.PungiTestCase):
    def test_without_config(self):
        compose = helpers.DummyCompose(self.topdir, {})
        gather.write_prepopulate_file(compose)
        self.assertFalse(os.path.isfile(os.path.join(self.topdir, 'work', 'global', 'prepopulate.json')))

    def test_copy_by_filename(self):
        compose = helpers.DummyCompose(self.topdir, {
            'gather_prepopulate': 'input-prepopulate.json',
        })
        compose.DEBUG = False
        compose.config_dir = self.topdir
        helpers.copy_fixture('prepopulate.json', os.path.join(self.topdir, 'input-prepopulate.json'))

        gather.write_prepopulate_file(compose)
        self.assertTrue(os.path.isfile(os.path.join(self.topdir, 'work', 'global', 'prepopulate.json')))

    def test_copy_local_by_scm_dict(self):
        compose = helpers.DummyCompose(self.topdir, {
            'gather_prepopulate': {
                'file': 'input-prepopulate.json',
                'scm': 'file',
                'repo': None,
            }
        })
        compose.DEBUG = False
        compose.config_dir = self.topdir
        helpers.copy_fixture('prepopulate.json', os.path.join(self.topdir, 'input-prepopulate.json'))

        gather.write_prepopulate_file(compose)
        self.assertTrue(os.path.isfile(os.path.join(self.topdir, 'work', 'global', 'prepopulate.json')))


class TestGetPrepopulate(helpers.PungiTestCase):
    def setUp(self):
        super(TestGetPrepopulate, self).setUp()
        self.compose = helpers.DummyCompose(self.topdir, {})

    def test_no_file(self):
        self.assertEqual(
            gather.get_prepopulate_packages(self.compose, 'x86_64', self.compose.variants['Server']),
            set()
        )

    def test_for_one_variant(self):
        helpers.copy_fixture('prepopulate.json',
                             os.path.join(self.topdir, 'work', 'global', 'prepopulate.json'))
        self.assertItemsEqual(
            gather.get_prepopulate_packages(self.compose, 'x86_64', self.compose.variants['Server']),
            ["foo-common.noarch",
             "foo.i686",
             "foo.x86_64"]
        )

    def test_for_all_variants(self):
        helpers.copy_fixture('prepopulate.json',
                             os.path.join(self.topdir, 'work', 'global', 'prepopulate.json'))
        self.assertItemsEqual(
            gather.get_prepopulate_packages(self.compose, 'x86_64', None),
            ["foo-common.noarch",
             "foo.i686",
             "foo.x86_64",
             "bar.x86_64"]
        )


class TestGatherPhase(helpers.PungiTestCase):
    @mock.patch('pungi.phases.gather.link_files')
    @mock.patch('pungi.phases.gather.gather_wrapper')
    def test_run(self, gather_wrapper, link_files):
        pkgset_phase = mock.Mock()
        compose = helpers.DummyCompose(self.topdir, {})
        compose.notifier = mock.Mock()
        compose.all_variants['Client'].is_empty = True
        pkg_map = gather_wrapper.return_value

        def _mk_link_call(arch, variant):
            return mock.call(compose, arch, compose.all_variants[variant],
                             pkg_map[arch][variant],
                             pkgset_phase.package_sets, manifest=phase.manifest)

        phase = gather.GatherPhase(compose, pkgset_phase)
        phase.run()
        phase.stop()

        self.assertEqual(gather_wrapper.call_args_list,
                         [mock.call(compose, pkgset_phase.package_sets, pkgset_phase.path_prefix)])
        self.assertItemsEqual(
            link_files.call_args_list,
            [_mk_link_call('x86_64', 'Server'),
             _mk_link_call('amd64', 'Server'),
             _mk_link_call('amd64', 'Everything'),
             _mk_link_call('x86_64', 'Everything')])
        self.assertTrue(os.path.isfile(os.path.join(self.topdir, 'compose', 'metadata', 'rpms.json')))

    @mock.patch('pungi.phases.gather.link_files')
    @mock.patch('pungi.phases.gather.gather_wrapper')
    def test_writes_manifest_when_skipped(self, gather_wrapper, link_files):
        pkgset_phase = mock.Mock()
        compose = helpers.DummyCompose(self.topdir, {})
        compose.notifier = mock.Mock()

        phase = gather.GatherPhase(compose, pkgset_phase)
        phase.stop()

        self.assertEqual(gather_wrapper.call_args_list, [])
        self.assertTrue(os.path.isfile(os.path.join(self.topdir, 'compose', 'metadata', 'rpms.json')))