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

import logging

from pungi import util


class PhaseBase(object):

    def __init__(self, compose):
        self.compose = compose
        self.msg = "---------- PHASE: %s ----------" % self.name.upper()
        self.finished = False
        self._skipped = False

    def validate(self):
        pass

    def conf_assert_str(self, name):
        missing = []
        invalid = []
        if name not in self.compose.conf:
            missing.append(name)
        elif not isinstance(self.compose.conf[name], str):
            invalid.append(name, type(self.compose.conf[name]), str)
        return missing, invalid

    def skip(self):
        if self._skipped:
            return True
        if self.compose.just_phases and self.name not in self.compose.just_phases:
            return True
        if self.name in self.compose.skip_phases:
            return True
        if self.name in self.compose.conf["skip_phases"]:
            return True
        return False

    def start(self):
        self._skipped = self.skip()
        if self._skipped:
            self.compose.log_warning("[SKIP ] %s" % self.msg)
            self.finished = True
            return
        self.compose.log_info("[BEGIN] %s" % self.msg)
        self.compose.notifier.send('phase-start', phase_name=self.name)
        self.run()

    def stop(self):
        if self.finished:
            return
        if hasattr(self, "pool"):
            self.pool.stop()
        self.finished = True
        self.compose.log_info("[DONE ] %s" % self.msg)
        self.compose.notifier.send('phase-stop', phase_name=self.name)

    def run(self):
        raise NotImplementedError


class ConfigGuardedPhase(PhaseBase):
    """A phase that is skipped unless config option is set."""

    def skip(self):
        if super(ConfigGuardedPhase, self).skip():
            return True
        if not self.compose.conf.get(self.name):
            self.compose.log_info("Config section '%s' was not found. Skipping." % self.name)
            return True
        return False


class ImageConfigMixin(object):
    """
    A mixin for phase that needs to access image related settings: ksurl,
    version, target and release.

    First, it checks config object given as argument, then it checks
    phase-level configuration and finally falls back to global configuration.
    """

    def __init__(self, *args, **kwargs):
        super(ImageConfigMixin, self).__init__(*args, **kwargs)
        self._phase_ksurl = None

    def get_config(self, cfg, opt):
        return cfg.get(
            opt, self.compose.conf.get(
                '%s_%s' % (self.name, opt), self.compose.conf.get(
                    'global_%s' % opt)))

    def get_version(self, cfg):
        """
        Get version from configuration hierarchy or fall back to release
        version.
        """
        return self.get_config(cfg, 'version') or self.compose.image_version

    def get_release(self, cfg):
        """
        If release is set to a magic string (or explicitly to None -
        deprecated), replace it with a generated value. Uses configuration
        passed as argument, phase specific settings and global settings.
        """
        for key, conf in [('release', cfg),
                          ('%s_release' % self.name, self.compose.conf),
                          ('global_release', self.compose.conf)]:
            if key in conf:
                return util.version_generator(self.compose, conf[key]) or self.compose.image_release
        return None

    def get_ksurl(self, cfg):
        """
        Get ksurl from `cfg`. If not present, fall back to phase defined one or
        global one.
        """
        if 'ksurl' in cfg:
            return util.resolve_git_url(cfg['ksurl'])
        if '%s_ksurl' % self.name in self.compose.conf:
            return self.phase_ksurl
        if 'global_ksurl' in self.compose.conf:
            return self.global_ksurl
        return None

    @property
    def phase_ksurl(self):
        """Get phase level ksurl, making sure to resolve it only once."""
        # The phase-level setting is cached as instance attribute of the phase.
        if not self._phase_ksurl:
            ksurl = self.compose.conf.get('%s_ksurl' % self.name)
            self._phase_ksurl = util.resolve_git_url(ksurl)
        return self._phase_ksurl

    @property
    def global_ksurl(self):
        """Get global ksurl setting, making sure to resolve it only once."""
        # The global setting is cached in the configuration object.
        if 'private_global_ksurl' not in self.compose.conf:
            ksurl = self.compose.conf.get('global_ksurl')
            self.compose.conf['private_global_ksurl'] = util.resolve_git_url(ksurl)
        return self.compose.conf['private_global_ksurl']


class PhaseLoggerMixin(object):
    """
    A mixin that can extend a phase with a new logging logger that copy
    handlers from compose, but with different formatter that includes phase name.
    """
    def __init__(self, *args, **kwargs):
        super(PhaseLoggerMixin, self).__init__(*args, **kwargs)
        self.logger = None
        if self.compose._logger and self.compose._logger.handlers:
            self.logger = logging.getLogger(self.name.upper())
            self.logger.setLevel(logging.DEBUG)
            format = "%(asctime)s [%(name)-16s] [%(levelname)-8s] %(message)s"
            import copy
            for handler in self.compose._logger.handlers:
                hl = copy.copy(handler)
                hl.setFormatter(logging.Formatter(format, datefmt="%Y-%m-%d %H:%M:%S"))
                hl.setLevel(logging.DEBUG)
                self.logger.addHandler(hl)
