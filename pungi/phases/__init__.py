# -*- coding: utf-8 -*-


# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <https://gnu.org/licenses/>.


# phases in runtime order
from .init import InitPhase  # noqa
from .pkgset import PkgsetPhase  # noqa
from .gather import GatherPhase  # noqa
from .createrepo import CreaterepoPhase  # noqa
from .product_img import ProductimgPhase  # noqa
from .buildinstall import BuildinstallPhase  # noqa
from .extra_files import ExtraFilesPhase  # noqa
from .createiso import CreateisoPhase  # noqa
from .live_images import LiveImagesPhase  # noqa
from .image_build import ImageBuildPhase  # noqa
from .test import TestPhase  # noqa
from .image_checksum import ImageChecksumPhase    # noqa
from .livemedia_phase import LiveMediaPhase  # noqa
from .ostree import OSTreePhase  # noqa
from .ostree_installer import OstreeInstallerPhase  # noqa
from .osbs import OSBSPhase  # noqa


def run_all(phases):
    """Start and stop all given phases and make them run in parallel.

    This function makes sure that even if one of the phases fails and raises an
    exception, all the phases will still be correctly stopped.

    If multiple phases fail, a exception from one of them will be raised, but
    there are no guarantees which one it will be.
    """
    if not phases:
        return
    phases[0].start()
    try:
        run_all(phases[1:])
    finally:
        phases[0].stop()
