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


import subprocess
import os
import shutil
import string
import sys
import hashlib
import errno
import pipes
import re
import urlparse
import contextlib
import traceback
import tempfile
import time

from kobo.shortcuts import run, force_list
from productmd.common import get_major_version

from .wrappers import kojiwrapper


def _doRunCommand(command, logger, rundir='/tmp', output=subprocess.PIPE, error=subprocess.PIPE, env=None):
    """Run a command and log the output.  Error out if we get something on stderr"""

    logger.info("Running %s" % subprocess.list2cmdline(command))

    p1 = subprocess.Popen(command, cwd=rundir, stdout=output, stderr=error, universal_newlines=True, env=env,
                          close_fds=True)
    (out, err) = p1.communicate()

    if out:
        logger.debug(out)

    if p1.returncode != 0:
        logger.error("Got an error from %s" % command[0])
        logger.error(err)
        raise OSError("Got an error (%d) from %s: %s" % (p1.returncode, command[0], err))


def _link(local, target, logger, force=False):
    """Simple function to link or copy a package, removing target optionally."""

    if os.path.exists(target) and force:
        os.remove(target)

    # check for broken links
    if force and os.path.islink(target):
        if not os.path.exists(os.readlink(target)):
            os.remove(target)

    try:
        os.link(local, target)
    except OSError, e:
        if e.errno != 18:  # EXDEV
            logger.error('Got an error linking from cache: %s' % e)
            raise OSError(e)

        # Can't hardlink cross file systems
        shutil.copy2(local, target)


def _ensuredir(target, logger, force=False, clean=False):
    """Ensure that a directory exists, if it already exists, only continue
    if force is set."""

    # We have to check existance of a logger, as setting the logger could
    # itself cause an issue.
    def whoops(func, path, exc_info):
        message = 'Could not remove %s' % path
        if logger:
            logger.error(message)
        else:
            sys.stderr(message)
        sys.exit(1)

    if os.path.exists(target) and not os.path.isdir(target):
        message = '%s exists but is not a directory.' % target
        if logger:
            logger.error(message)
        else:
            sys.stderr(message)
        sys.exit(1)

    if not os.path.isdir(target):
        os.makedirs(target)
    elif force and clean:
        shutil.rmtree(target, onerror=whoops)
        os.makedirs(target)
    elif force:
        return
    else:
        message = 'Directory %s already exists.  Use --force to overwrite.' % target
        if logger:
            logger.error(message)
        else:
            sys.stderr(message)
        sys.exit(1)


def _doCheckSum(path, hash, logger):
    """Generate a checksum hash from a provided path.
    Return a string of type:hash"""

    # Try to figure out what hash we want to do
    try:
        sum = hashlib.new(hash)
    except ValueError:
        logger.error("Invalid hash type: %s" % hash)
        return False

    # Try to open the file, using binary flag.
    try:
        myfile = open(path, 'rb')
    except IOError, e:
        logger.error("Could not open file %s: %s" % (path, e))
        return False

    # Loop through the file reading chunks at a time as to not
    # put the entire file in memory.  That would suck for DVDs
    while True:
        chunk = myfile.read(8192)  # magic number!  Taking suggestions for better blocksize
        if not chunk:
            break  # we're done with the file
        sum.update(chunk)
    myfile.close()

    return '%s:%s' % (hash, sum.hexdigest())


def makedirs(path, mode=0o775):
    try:
        os.makedirs(path, mode=mode)
    except OSError as ex:
        if ex.errno != errno.EEXIST:
            raise


def rmtree(path, ignore_errors=False, onerror=None):
    """shutil.rmtree ENOENT (ignoring no such file or directory) errors"""
    try:
        shutil.rmtree(path, ignore_errors, onerror)
    except OSError as ex:
        if ex.errno != errno.ENOENT:
            raise


def explode_rpm_package(pkg_path, target_dir):
    """Explode a rpm package into target_dir."""
    pkg_path = os.path.abspath(pkg_path)
    makedirs(target_dir)
    run("rpm2cpio %s | cpio -iuvmd && chmod -R a+rX ." % pipes.quote(pkg_path), workdir=target_dir)


def pkg_is_rpm(pkg_obj):
    if pkg_is_srpm(pkg_obj):
        return False
    if pkg_is_debug(pkg_obj):
        return False
    return True


def pkg_is_srpm(pkg_obj):
    if isinstance(pkg_obj, str):
        # string, probably N.A, N-V-R.A, N-V-R.A.rpm
        for i in (".src", ".nosrc", ".src.rpm", ".nosrc.rpm"):
            if pkg_obj.endswith(i):
                return True
    else:
        # package object
        if pkg_obj.arch in ("src", "nosrc"):
            return True
    return False


def pkg_is_debug(pkg_obj):
    if pkg_is_srpm(pkg_obj):
        return False
    if isinstance(pkg_obj, str):
        # string
        if "-debuginfo" in pkg_obj:
            return True
    else:
        # package object
        if "-debuginfo" in pkg_obj.name:
            return True
    return False


# fomat: [(variant_uid_regex, {arch|*: [data]})]
def get_arch_variant_data(conf, var_name, arch, variant):
    result = []
    for conf_variant, conf_data in conf.get(var_name, []):
        if variant is not None and not re.match(conf_variant, variant.uid):
            continue
        for conf_arch in conf_data:
            if conf_arch != "*" and conf_arch != arch:
                continue
            if conf_arch == "*" and arch == "src":
                # src is excluded from '*' and needs to be explicitly added to the mapping
                continue
            if isinstance(conf_data[conf_arch], list):
                result.extend(conf_data[conf_arch])
            else:
                result.append(conf_data[conf_arch])
    return result


def is_arch_multilib(conf, arch):
    """Check if at least one variant has multilib enabled on this variant."""
    return bool(get_arch_variant_data(conf, 'multilib', arch, None))


def _get_git_ref(fragment):
    if fragment == 'HEAD':
        return fragment
    if fragment.startswith('origin/'):
        branch = fragment.split('/', 1)[1]
        return 'refs/heads/' + branch
    return None


def resolve_git_url(url):
    """Given a url to a Git repo specifying HEAD or origin/<branch> as a ref,
    replace that specifier with actual SHA1 of the commit.

    Otherwise, the original URL will be returned.

    Raises RuntimeError if there was an error. Most likely cause is failure to
    run git command.
    """
    r = urlparse.urlsplit(url)
    ref = _get_git_ref(r.fragment)
    if not ref:
        return url

    # Remove git+ prefix from scheme if present. This is for resolving only,
    # the final result must use original scheme.
    scheme = r.scheme.replace('git+', '')

    baseurl = urlparse.urlunsplit((scheme, r.netloc, r.path, '', ''))
    _, output = run(['git', 'ls-remote', baseurl, ref])

    lines = [line for line in output.split('\n') if line]
    if len(lines) != 1:
        # This should never happen. HEAD can not match multiple commits in a
        # single repo, and there can not be a repo without a HEAD.
        raise RuntimeError('Failed to resolve %s', url)

    fragment = lines[0].split()[0]
    result = urlparse.urlunsplit((r.scheme, r.netloc, r.path, r.query, fragment))
    if '?#' in url:
        # The urlparse library drops empty query string. This hack puts it back in.
        result = result.replace('#', '?#')
    return result


# fomat: {arch|*: [data]}
def get_arch_data(conf, var_name, arch):
    result = []
    for conf_arch, conf_data in conf.get(var_name, {}).items():
        if conf_arch != "*" and conf_arch != arch:
            continue
        if conf_arch == "*" and arch == "src":
            # src is excluded from '*' and needs to be explicitly added to the mapping
            continue
        if isinstance(conf_data, list):
            result.extend(conf_data)
        else:
            result.append(conf_data)
    return result


def get_variant_data(conf, var_name, variant):
    """Get configuration for variant.

    Expected config format is a mapping from variant_uid regexes to lists of
    values.

    :param var_name: name of configuration key with which to work
    :param variant: Variant object for which to get configuration
    :rtype: a list of values
    """
    result = []
    for conf_variant, conf_data in conf.get(var_name, {}).iteritems():
        if not re.match(conf_variant, variant.uid):
            continue
        if isinstance(conf_data, list):
            result.extend(conf_data)
        else:
            result.append(conf_data)
    return result


def get_buildroot_rpms(compose, task_id):
    """Get build root RPMs - either from runroot or local"""
    result = []
    if task_id:
        # runroot
        koji = kojiwrapper.KojiWrapper(compose.conf['koji_profile'])
        buildroot_infos = koji.koji_proxy.listBuildroots(taskID=task_id)
        buildroot_info = buildroot_infos[-1]
        data = koji.koji_proxy.listRPMs(componentBuildrootID=buildroot_info["id"])
        for rpm_info in data:
            fmt = "%(nvr)s.%(arch)s"
            result.append(fmt % rpm_info)
    else:
        # local
        retcode, output = run("rpm -qa --qf='%{name}-%{version}-%{release}.%{arch}\n'")
        for i in output.splitlines():
            if not i:
                continue
            result.append(i)
    result.sort()
    return result


def _apply_substitutions(compose, volid):
    for k, v in compose.conf['volume_id_substitutions'].iteritems():
        volid = volid.replace(k, v)
    return volid


def get_volid(compose, arch, variant=None, escape_spaces=False, disc_type=False):
    """Get ISO volume ID for arch and variant"""
    if variant and variant.type == "addon":
        # addons are part of parent variant media
        return None

    if variant and variant.type == "layered-product":
        release_short = variant.release_short
        release_version = variant.release_version
        release_is_layered = True
        base_product_short = compose.conf["release_short"]
        base_product_version = get_major_version(compose.conf["release_version"])
        variant_uid = variant.parent.uid
    else:
        release_short = compose.conf["release_short"]
        release_version = compose.conf["release_version"]
        release_is_layered = compose.conf["release_is_layered"]
        base_product_short = compose.conf.get("base_product_short", "")
        base_product_version = compose.conf.get("base_product_version", "")
        variant_uid = variant and variant.uid or None

    products = compose.conf['image_volid_formats']
    layered_products = compose.conf['image_volid_layered_product_formats']

    volid = None
    if release_is_layered:
        all_products = layered_products + products
    else:
        all_products = products

    for i in all_products:
        if not variant_uid and "%(variant)s" in i:
            continue
        try:
            args = get_format_substs(compose,
                                     variant=variant_uid,
                                     release_short=release_short,
                                     version=release_version,
                                     arch=arch,
                                     disc_type=disc_type or '',
                                     base_product_short=base_product_short,
                                     base_product_version=base_product_version)
            volid = (i % args).format(**args)
        except KeyError as err:
            raise RuntimeError('Failed to create volume id: unknown format element: %s' % err.message)
        volid = _apply_substitutions(compose, volid)
        if len(volid) <= 32:
            break

    if volid and len(volid) > 32:
        raise ValueError("Could not create volume ID <= 32 characters")

    if volid and escape_spaces:
        volid = volid.replace(" ", r"\x20")
    return volid


def get_mtime(path):
    return int(os.stat(path).st_mtime)


def get_file_size(path):
    return os.path.getsize(path)


def find_old_compose(old_compose_dirs, release_short, release_version,
                     base_product_short=None, base_product_version=None):
    composes = []

    for compose_dir in force_list(old_compose_dirs):
        if not os.path.isdir(compose_dir):
            continue

        # get all finished composes
        for i in os.listdir(compose_dir):
            # TODO: read .composeinfo

            pattern = "%s-%s" % (release_short, release_version)
            if base_product_short:
                pattern += "-%s" % base_product_short
            if base_product_version:
                pattern += "-%s" % base_product_version

            if not i.startswith(pattern):
                continue

            path = os.path.join(compose_dir, i)
            if not os.path.isdir(path):
                continue

            if os.path.islink(path):
                continue

            status_path = os.path.join(path, "STATUS")
            if not os.path.isfile(status_path):
                continue

            try:
                with open(status_path, 'r') as f:
                    if f.read().strip() in ("FINISHED", "FINISHED_INCOMPLETE", "DOOMED"):
                        composes.append((i, os.path.abspath(path)))
            except:
                continue

    if not composes:
        return None

    return sorted(composes)[-1][1]


def process_args(fmt, args):
    """Given a list of arguments, format each value with the format string.

    >>> process_args('--opt=%s', ['foo', 'bar'])
    ['--opt=foo', '--opt=bar']
    """
    return [fmt % val for val in force_list(args or [])]


@contextlib.contextmanager
def failable(compose, can_fail, variant, arch, deliverable, subvariant=None, logger=None):
    """If a deliverable can fail, log a message and go on as if it succeeded."""
    if not logger:
        logger = compose._logger
    msg = deliverable.replace('-', ' ').capitalize()
    if can_fail:
        compose.attempt_deliverable(variant, arch, deliverable, subvariant)
    else:
        compose.require_deliverable(variant, arch, deliverable, subvariant)
    try:
        yield
    except Exception as exc:
        if not can_fail:
            raise
        else:
            compose.fail_deliverable(variant, arch, deliverable, subvariant)
            ident = 'variant %s, arch %s' % (variant.uid if variant else 'None', arch)
            if subvariant:
                ident += ', subvariant %s' % subvariant
            logger.info('[FAIL] %s (%s) failed, but going on anyway.'
                        % (msg, ident))
            logger.info(str(exc))
            tb = traceback.format_exc()
            logger.debug(tb)


def can_arch_fail(failable_arches, arch):
    """Check if `arch` is in `failable_arches` or `*` can fail."""
    return '*' in failable_arches or arch in failable_arches


def get_format_substs(compose, **kwargs):
    """Return a dict of basic format substitutions.

    Any kwargs will be added as well.
    """
    substs = {
        'compose_id': compose.compose_id,
        'release_short': compose.ci_base.release.short,
        'version': compose.ci_base.release.version,
        'date': compose.compose_date,
        'respin': compose.compose_respin,
        'type': compose.compose_type,
        'type_suffix': compose.compose_type_suffix,
        'label': compose.compose_label,
        'label_major_version': compose.compose_label_major_version,
    }
    substs.update(kwargs)
    return substs


def copy_all(src, dest):
    """
    Copy all files and directories within ``src`` to the ``dest`` directory.

    This is equivalent to running ``cp -r src/* dest``.

    :param src:
        Source directory to copy from.

    :param dest:
        Destination directory to copy to.

    :return:
        A list of relative paths to the files copied.

    Example:
        >>> _copy_all('/tmp/src/', '/tmp/dest/')
        ['file1', 'dir1/file2', 'dir1/subdir/file3']
    """
    contents = os.listdir(src)
    if not contents:
        raise RuntimeError('Source directory %s is empty.' % src)
    makedirs(dest)
    for item in contents:
        source = os.path.join(src, item)
        destination = os.path.join(dest, item)
        if os.path.isdir(source):
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)

    return recursive_file_list(src)


def recursive_file_list(directory):
    """Return a list of files contained in ``directory``.

    The files are paths relative to ``directory``

    :param directory:
        Path to the directory to list.

    Example:
        >>> recursive_file_list('/some/dir')
        ['file1', 'subdir/file2']
    """
    file_list = []
    for root, dirs, files in os.walk(directory):
        file_list += [os.path.relpath(os.path.join(root, f), directory) for f in files]
    return file_list


def levenshtein(a, b):
    """Compute Levenshtein edit distance between two strings."""
    mat = [[0 for _ in xrange(len(a) + 1)] for _ in xrange(len(b) + 1)]

    for i in xrange(len(a) + 1):
        mat[0][i] = i

    for j in xrange(len(b) + 1):
        mat[j][0] = j

    for j in xrange(1, len(b) + 1):
        for i in xrange(1, len(a) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            mat[j][i] = min(mat[j - 1][i] + 1,
                            mat[j][i - 1] + 1,
                            mat[j - 1][i - 1] + cost)

    return mat[len(b)][len(a)]


@contextlib.contextmanager
def temp_dir(log=None, *args, **kwargs):
    """Create a temporary directory and ensure it's deleted."""
    if kwargs.get('dir'):
        # If we are supposed to create the temp dir in a particular location,
        # ensure the location already exists.
        makedirs(kwargs['dir'])
    dir = tempfile.mkdtemp(*args, **kwargs)
    try:
        yield dir
    finally:
        try:
            shutil.rmtree(dir)
        except OSError as exc:
            # Okay, we failed to delete temporary dir.
            if log:
                log.warning('Error removing %s: %s', dir, exc.strerror)


def fusermount(path, **kwargs):
    """Run fusermount -u on a given path."""
    run_unmount_cmd(['fusermount', '-u', path], path=path, **kwargs)


def run_unmount_cmd(cmd, max_retries=10, path=None, logger=None):
    """Attempt to run the command to unmount an image.

    If the command fails and stderr complains about device being busy, try
    again. We will do up to ``max_retries`` attemps with increasing pauses.

    If both path and logger are specified, more debugging information will be
    printed in case of failure.
    """
    for i in xrange(max_retries):
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate()
        if proc.returncode == 0:
            # We were successful
            return
        if 'Device or resource busy' not in err:
            raise RuntimeError('Unhandled error when running %r: %r' % (cmd, err))
        time.sleep(i)
    # Still busy, there's something wrong.
    if path and logger:
        commands = [
            ['ls', '-lA', path],
            ['fuser', '-vm', path],
            ['lsof', '+D', path],
        ]
        for c in commands:
            try:
                proc = subprocess.Popen(c, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                out, _ = proc.communicate()
                logger.debug('`%s` exited with %s and following output:\n%s',
                             ' '.join(c), proc.returncode, out)
            except OSError:
                logger.debug('`%s` command not available for debugging',
                             ' '.join(c))
    raise RuntimeError('Failed to run %r: Device or resource busy.' % cmd)


def translate_path(compose, path):
    """
    @param compose - required for access to config
    @param path
    """
    normpath = os.path.normpath(path)
    mapping = compose.conf["translate_paths"]

    for prefix, newvalue in mapping:
        prefix = os.path.normpath(prefix)
        # Strip trailing slashes: the prefix has them stripped by `normpath`.
        newvalue = newvalue.rstrip('/')
        if normpath.startswith(prefix):
            # We can't call os.path.normpath on result since it is not actually
            # a path - http:// would get changed to  http:/ and so on.
            # Only the first occurance should be replaced.
            return normpath.replace(prefix, newvalue, 1)

    return normpath


def get_repo_url(compose, repo, arch='$basearch'):
    """
    Convert repo to repo URL.

    @param compose - required for access to variants
    @param repo - string or a dict which at least contains 'baseurl' key
    @param arch - string to be used as arch in repo url
    """
    if isinstance(repo, dict):
        try:
            repo = repo['baseurl']
        except KeyError:
            raise RuntimeError('Baseurl is required in repo dict %s' % str(repo))
    if '://' not in repo:
        # this is a variant name
        v = compose.all_variants.get(repo)
        if not v:
            raise RuntimeError('There is no variant %s to get repo from.' % repo)
        repo = translate_path(compose, compose.paths.compose.repository(arch, v, create_dir=False))
    return repo


def get_repo_urls(compose, repos, arch='$basearch'):
    """
    Convert repos to a list of repo URLs.

    @param compose - required for access to variants
    @param repos - list of string or dict, if item is a dict, key 'baseurl' is required
    @param arch - string to be used as arch in repo url
    """
    urls = []
    for repo in repos:
        repo = get_repo_url(compose, repo, arch=arch)
        urls.append(repo)
    return urls


def _translate_url_to_repo_id(url):
    """
    Translate url to valid repo id by replacing any invalid char to '_'.
    """
    _REPOID_CHARS = string.ascii_letters + string.digits + '-_.:'
    return ''.join([s if s in list(_REPOID_CHARS) else '_' for s in url])


def get_repo_dict(compose, repo, arch='$basearch'):
    """
    Convert repo to a dict of repo options.

    If repo is a string, translate it to repo url if necessary (when it's
    not a url), and set it as 'baseurl' in result dict, also generate
    a repo id/name as 'name' key in result dict.
    If repo is a dict, translate value of 'baseurl' key to url if necessary,
    if 'name' key is missing in the dict, generate one for it.

    @param compose - required for access to variants
    @param repo - A string or dict, if it is a dict, key 'baseurl' is required
    @param arch - string to be used as arch in repo url
    """
    repo_dict = {}
    if isinstance(repo, dict):
        url = repo['baseurl']
        name = repo.get('name', None)
        if '://' in url:
            if name is None:
                name = _translate_url_to_repo_id(url)
        else:
            # url is variant uid
            if name is None:
                name = '%s-%s' % (compose.compose_id, url)
            url = get_repo_url(compose, url, arch=arch)
        repo['name'] = name
        repo['baseurl'] = url
        return repo
    else:
        # repo is normal url or variant uid
        repo_dict = {}
        if '://' in repo:
            repo_dict['name'] = _translate_url_to_repo_id(repo)
            repo_dict['baseurl'] = repo
        else:
            repo_dict['name'] = '%s-%s' % (compose.compose_id, repo)
            repo_dict['baseurl'] = get_repo_url(compose, repo)

    return repo_dict


def get_repo_dicts(compose, repos, arch='$basearch'):
    """
    Convert repos to a list of repo dicts.

    @param compose - required for access to variants
    @param repo - A list of string or dict, if item is a dict, key 'baseurl' is required
    @param arch - string to be used as arch in repo url
    """
    repo_dicts = []
    for repo in repos:
        repo_dict = get_repo_dict(compose, repo, arch=arch)
        repo_dicts.append(repo_dict)
    return repo_dicts


def version_generator(compose, gen):
    """If ``gen`` is a known generator, create a value. Otherwise return
       the argument value unchanged.
    """
    if gen == '!OSTREE_VERSION_FROM_LABEL_DATE_TYPE_RESPIN':
        return '%s.%s' % (compose.image_version, compose.image_release)
    if gen == '!RELEASE_FROM_LABEL_DATE_TYPE_RESPIN':
        return compose.image_release
    if gen and gen[0] == '!':
        raise RuntimeError("Unknown version generator '%s'" % gen)
    return gen
