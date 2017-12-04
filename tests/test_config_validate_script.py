# -*- coding: utf-8 -*-


import mock
import os
import subprocess
import sys

import six


HERE = os.path.abspath(os.path.dirname(__file__))
BINDIR = os.path.join(HERE, '../bin')
PUNGI_CONFIG_VALIDATE = os.path.join(BINDIR, 'pungi-config-validate')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tests import helpers


class ConfigValidateScriptTest(helpers.PungiTestCase):

    @mock.patch('kobo.shortcuts.run')
    def test_validate_dummy_config(self, run):
        DUMMY_CONFIG = os.path.join(HERE, 'data/dummy-pungi.conf')
        interp = 'python2' if six.PY2 else 'python3'
        p = subprocess.Popen([interp, PUNGI_CONFIG_VALIDATE, DUMMY_CONFIG],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        (stdout, stderr) = p.communicate()
        self.assertEqual(b'', stdout)
        self.assertEqual(b'', stderr)
        self.assertEqual(0, p.returncode)
