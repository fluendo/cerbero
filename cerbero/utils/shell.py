# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Andoni Morales Alastruey <ylatuya@gmail.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import logging
import subprocess
import asyncio
import shlex
import sys
import os
import re
import tarfile
import zipfile
import tempfile
import time
import glob
import shutil
import hashlib
import urllib.request
import urllib.error
import urllib.parse
import collections
from ftplib import FTP
from pathlib import Path, PurePath
from distutils.version import StrictVersion
from typing import Iterable

from cerbero.enums import Platform
from cerbero.utils import _, system_info, to_unixpath
from cerbero.utils import messages as m
from cerbero.errors import FatalError


PATCH = 'patch'
TAR = 'tar'
TARBALL_SUFFIXES = ('tar.gz', 'tgz', 'tar.bz2', 'tbz2', 'tar.xz')


PLATFORM = system_info()[0]
DRY_RUN = False

CALL_ENV = None


def console_is_interactive():
    if not os.isatty(sys.stdout.fileno()):
        return False
    if os.environ.get('TERM') == 'dumb':
        return False
    return True


def log(msg, logfile):
    if logfile is None:
        logging.info(msg)
    else:
        logfile.write(msg + '\n')


def _fix_mingw_cmd(path):
    reserved = ['/', ' ', '\\', ')', '(', '"']
    l_path = list(path)
    for i in range(len(path)):
        if path[i] == '\\':
            if i + 1 == len(path) or path[i + 1] not in reserved:
                l_path[i] = '/'
    return ''.join(l_path)


def _cmd_string_to_array(cmd):
    if not isinstance(cmd, str):
        return cmd
    if PLATFORM == Platform.WINDOWS:
        # fix paths with backslashes
        cmd = _fix_mingw_cmd(cmd)
    # If we've been given a string, run it through sh to get scripts working on
    # Windows and shell syntax such as && and env var setting working on all
    # platforms.
    return ['sh', '-c', cmd]


def set_call_env(env):
    global CALL_ENV
    CALL_ENV = env


def restore_call_env():
    global CALL_ENV
    CALL_ENV = None


def call(cmd, cmd_dir='.', fail=True, verbose=False, logfile=None, env=None):
    '''
    Run a shell command
    DEPRECATED: Use new_call and a cmd array wherever possible

    @param cmd: the command to run
    @type cmd: str
    @param cmd_dir: directory where the command will be run
    @param cmd_dir: str
    @param fail: whether or not to raise an exception if the command fails
    @type fail: bool
    '''
    global CALL_ENV
    try:
        if logfile is None:
            if verbose:
                m.message("Running command '%s'" % cmd)
            stream = None
        else:
            logfile.write("Running command '%s'\n" % cmd)
            logfile.flush()
            stream = logfile
        shell = True
        if PLATFORM == Platform.WINDOWS:
            # windows do not understand ./
            if cmd.startswith('./'):
                cmd = cmd[2:]
            # run all processes through sh.exe to get scripts working
            cmd = '%s "%s"' % ('sh -c', cmd)
            # fix paths with backslashes
            cmd = _fix_mingw_cmd(cmd)
            # Disable shell which uses cmd.exe
            shell = False
        if DRY_RUN:
            # write to sdterr so it's filtered more easilly
            m.error("cd %s && %s && cd %s" % (cmd_dir, cmd, os.getcwd()))
            ret = 0
        else:
            if CALL_ENV is not None:
                env = CALL_ENV.copy()
            elif env is not None:
                env = env.copy()
            else:
                env = os.environ.copy()

            # Force python scripts to print their output on newlines instead
            # of on exit. Ensures that we get continuous output in log files.
            env['PYTHONUNBUFFERED'] = '1'
            ret = subprocess.check_call(cmd, cwd=cmd_dir, bufsize=1,
                                        stderr=subprocess.STDOUT, stdout=stream,
                                        universal_newlines=True,
                                        env=env, shell=shell)
    except subprocess.CalledProcessError:
        if fail:
            raise FatalError(_("Error running command: %s") % cmd)
        else:
            ret = 0
    return ret


def check_call(cmd, cmd_dir=None, shell=False, split=True, fail=False, env=None):
    '''
    DEPRECATED: Use check_output and a cmd array wherever possible
    '''
    if env is None and CALL_ENV is not None:
        env = CALL_ENV.copy()
    if split and isinstance(cmd, str):
        cmd = shlex.split(cmd)
    try:
        process = subprocess.Popen(cmd, cwd=cmd_dir, env=env,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, shell=shell)
        output, unused_err = process.communicate()
        if process.poll() and fail:
            raise Exception()
    except Exception:
        raise FatalError(_("Error running command: %s") % cmd)

    if sys.stdout.encoding:
        output = output.decode(sys.stdout.encoding, errors='replace')

    return output


def check_output(cmd, cmd_dir=None, logfile=None, env=None):
    cmd = _cmd_string_to_array(cmd)
    try:
        o = subprocess.check_output(cmd, cwd=cmd_dir, env=env, stderr=logfile)
    except (OSError, subprocess.CalledProcessError) as e:
        raise FatalError('Running command: {!r}\n{}'.format(cmd, str(e)))

    if sys.stdout.encoding:
        o = o.decode(sys.stdout.encoding, errors='replace')
    return o


def new_call(cmd, cmd_dir=None, logfile=None, env=None):
    cmd = _cmd_string_to_array(cmd)
    if logfile:
        logfile.write('Running command {!r}\n'.format(cmd))
        logfile.flush()
    try:
        subprocess.check_call(cmd, cwd=cmd_dir, env=env,
                              stdout=logfile, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        raise FatalError('Running command: {!r}\n{}'.format(cmd, str(e)))


async def async_call(cmd, cmd_dir='.', fail=True, logfile=None, env=None):
    '''
    Run a shell command

    @param cmd: the command to run
    @type cmd: str
    @param cmd_dir: directory where the command will be run
    @param cmd_dir: str
    '''
    cmd = _cmd_string_to_array(cmd)

    if logfile is None:
        stream = None
    else:
        logfile.write("Running command '%s'\n" % ' '.join([shlex.quote(c) for c in cmd]))
        logfile.flush()
        stream = logfile

    if DRY_RUN:
        # write to sdterr so it's filtered more easilly
        m.error("cd %s && %s && cd %s" % (cmd_dir, cmd, os.getcwd()))
        return

    global CALL_ENV
    if CALL_ENV is not None:
        env = CALL_ENV.copy()
    elif env is None:
        env = os.environ.copy()

    # Force python scripts to print their output on newlines instead
    # of on exit. Ensures that we get continuous output in log files.
    env['PYTHONUNBUFFERED'] = '1'

    proc = await asyncio.create_subprocess_exec(*cmd, cwd=cmd_dir,
                                                stderr=subprocess.STDOUT, stdout=stream,
                                                env=env)
    await proc.wait()
    if proc.returncode != 0 and fail:
        raise FatalError('Running {!r}, returncode {}'.format(cmd, proc.returncode))

    return proc.returncode

async def async_check_output(cmd, cmd_dir=None, logfile=None, env=None):
    '''
    Run a shell command and get the output

    @param cmd: the command to run
    @type cmd: str
    @param cmd_dir: directory where the command will be run
    @param cmd_dir: str
    '''
    cmd = _cmd_string_to_array(cmd)

    if PLATFORM == Platform.WINDOWS:
        import cerbero.hacks
        # On Windows, create_subprocess_exec with a PIPE fails while creating
        # a named pipe using tempfile.mktemp because we override os.path.join
        # to use / on Windows. Override the tempfile module's reference to the
        # original implementation, then change it back later so it doesn't leak.
        # XXX: Get rid of this once we move to Path.as_posix() everywhere
        tempfile._os.path.join = cerbero.hacks.oldjoin
        # The tempdir is derived from TMP and TEMP which use / as the path
        # separator, which fails for the same reason as above. Ensure that \ is
        # used instead.
        tempfile.tempdir = str(PurePath(tempfile.gettempdir()))

    global CALL_ENV
    if CALL_ENV is not None:
        env = CALL_ENV.copy()
    elif env is None:
        env = os.environ.copy()

    proc = await asyncio.create_subprocess_exec(*cmd, cwd=cmd_dir,
                                                stdout=subprocess.PIPE, stderr=logfile, env=env)
    (output, unused_err) = await proc.communicate()

    if PLATFORM == Platform.WINDOWS:
        os.path.join = cerbero.hacks.join

    if sys.stdout.encoding:
        output = output.decode(sys.stdout.encoding, errors='replace')

    if proc.returncode != 0:
        raise FatalError('Running {!r}, returncode {}:\n{}'.format(cmd, proc.returncode, output))

    return output


def apply_patch(patch, directory, strip=1, logfile=None):
    '''
    Apply a patch

    @param patch: path of the patch file
    @type patch: str
    @param directory: directory to apply the apply
    @type: directory: str
    @param strip: strip
    @type strip: int
    '''
    log("Applying patch {}".format(patch), logfile)
    call('%s -p%s -f -i %s' % (PATCH, strip, patch), directory)


async def unpack(filepath, output_dir, logfile=None):
    '''
    Extracts a tarball

    @param filepath: path of the tarball
    @type filepath: str
    @param output_dir: output directory
    @type output_dir: str
    '''
    log('Unpacking {} in {}'.format(filepath, output_dir), logfile)

    # Recent versions of tar are much faster than the tarfile module, but we
    # can't use tar on Windows because MSYS tar is ancient and buggy.
    if filepath.endswith(TARBALL_SUFFIXES):
        if PLATFORM != Platform.WINDOWS:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            await async_call(['tar', '-C', output_dir, '-xf', filepath, '--no-same-owner'])
        else:
            cmode = 'bz2' if filepath.endswith('bz2') else filepath[-2:]
            tf = tarfile.open(filepath, mode='r:' + cmode)
            tf.extractall(path=output_dir)
    elif filepath.endswith('.zip'):
        zf = zipfile.ZipFile(filepath, "r")
        zf.extractall(path=output_dir)
    else:
        raise FatalError("Unknown tarball format %s" % filepath)


async def download_wget(url, destination=None, check_cert=True, overwrite=False, logfile=None, user=None, password=None):
    '''
    Downloads a file with wget

    @param url: url to download
    @type: str
    @param destination: destination where the file will be saved
    @type destination: str
    '''
    cmd = "wget %s " % url
    path = None
    if destination is not None:
        cmd += "-O %s " % destination

    if not check_cert:
        cmd += " --no-check-certificate"

    if user:
        cmd += " --user %s" % user
        if password:
            cmd += " --password \"%s\"" % password

    cmd += " --tries=2"
    cmd += " --timeout=10.0"
    cmd += " --progress=dot:giga"

    try:
        await async_call(cmd, path, logfile=logfile)
    except FatalError as e:
        if os.path.exists(destination):
            os.remove(destination)
        raise e


async def download_urllib2(url, destination=None, check_cert=True, overwrite=False, logfile=None, user=None, password=None):
    '''
    Download a file with urllib2, which does not rely on external programs

    @param url: url to download
    @type: str
    @param destination: destination where the file will be saved
    @type destination: str
    '''
    ctx = None
    if not check_cert:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    # This is roughly what wget and curl do
    if not destination:
        destination = os.path.basename(url)

    try:
        logging.info(destination)
        with open(destination, 'wb') as d:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'cerbero')
            f = urllib.request.urlopen(req, context=ctx)
            d.write(f.read())
    except urllib.error.HTTPError as e:
        if os.path.exists(destination):
            os.remove(destination)
        raise e


async def download_curl(url, destination=None, check_cert=True, overwrite=False, logfile=None, user=None, password=None):
    '''
    Downloads a file with cURL

    @param url: url to download
    @type: str
    @param destination: destination where the file will be saved
    @type destination: str
    '''
    path = None
    cmd = "curl -L --fail "
    if user:
        cmd += "--user %s" % user
        if password:
            cmd += ":\"%s\" " % password
        else:
            cmd += " "
    if not check_cert:
        cmd += " -k "
    if destination is not None:
        cmd += "%s -o %s " % (url, destination)
    else:
        cmd += "-O %s " % url
    try:
        await async_call(cmd, path, logfile=logfile)
    except FatalError as e:
        if os.path.exists(destination):
            os.remove(destination)
        raise e


async def download(url, destination=None, check_cert=True, overwrite=False, logfile=None, mirrors=None, user=None, password=None):
    '''
    Downloads a file

    @param url: url to download
    @type: str
    @param destination: destination where the file will be saved
    @type destination: str
    @param check_cert: whether to check certificates or not
    @type check_cert: bool
    @param overwrite: whether to overwrite the destination or not
    @type check_cert: bool
    @param logfile: path to the file to log instead of stdout
    @type logfile: str
    @param mirrors: list of mirrors to use as fallback
    @type logfile: list
    '''
    if not overwrite and os.path.exists(destination):
        if logfile is None:
            logging.info("File %s already downloaded." % destination)
        return
    else:
        if not os.path.exists(os.path.dirname(destination)):
            os.makedirs(os.path.dirname(destination))
        log("Downloading {}".format(url), logfile)

    urls = [url]
    if mirrors is not None:
        filename = os.path.basename(url)
        # Add a traling '/' the url so that urljoin joins correctly urls
        # in case users provided it without the trailing '/'
        urls += [urllib.parse.urljoin(u + '/', filename) for u in mirrors]

    # wget shipped with msys fails with an SSL error on github URLs
    # https://githubengineering.com/crypto-removal-notice/
    # curl on Windows (if provided externally) is often badly-configured and fails
    # to download over https, so just always use urllib2 on Windows.
    if sys.platform.startswith('win'):
        download_func = download_urllib2
    elif which('wget'):
        download_func = download_wget
    elif which('curl'):
        download_func = download_curl
    else:
        # Fallback. TODO: make this the default and remove curl/wget dependency
        download_func = download_urllib2

    errors = []
    for murl in urls:
        tries = 2
        while tries > 0:
            try:
                return await download_func(murl, destination, check_cert, overwrite, logfile)
            except Exception as ex:
                tries -= 1
                if tries == 0:
                    errors.append(ex)
    raise Exception(errors)


class Ftp:
    def __init__(self, remote_url, user=None, password=None):
        remote = urllib.parse.urlparse(remote_url)
        self.ftp = FTP()
        self.ftp.connect(remote.hostname, remote.port or 0)
        self.ftp.login(user, password)

    def close(self):
        self.ftp.quit()

    def file_exists(self, remote_url):
        remote = urllib.parse.urlparse(remote_url)
        try:
            self.ftp.cwd(os.path.dirname(remote.path))
            files = self.ftp.nlst()
            return os.path.basename(remote.path) in files
        except Exception:
            return False

    def download(self, remote_url, local_filename):
        if not self.file_exists(remote_url):
            raise Exception('Remote file {} does not exist'.format(remote_url))
        remote = urllib.parse.urlparse(remote_url)
        self.ftp.cwd(os.path.dirname(remote.path))
        with open(local_filename, 'wb') as f:
            self.ftp.retrbinary('RETR ' + os.path.basename(remote.path), f.write)

    def upload(self, local_filename, remote_url):
        remote = urllib.parse.urlparse(remote_url)
        try:
            self.ftp.mkd(os.path.dirname(remote.path))
        except Exception:
            pass
        self.ftp.cwd(os.path.dirname(remote.path))
        with open(local_filename, 'rb') as f:
            self.ftp.storbinary('STOR ' + os.path.basename(remote.path), f)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _splitter(string, base_url):
    lines = string.split('\n')
    for line in lines:
        try:
            yield "%s/%s" % (base_url, line.split(' ')[2])
        except:
            continue


def ls_files(files, prefix):
    if not files:
        return []
    sfiles = set()
    prefix = Path(prefix)
    for f in ' '.join(files).split():
        sfiles.update([i.relative_to(prefix).as_posix() for i in prefix.glob(f)])
    return list(tuple(sfiles))


def ls_dir(dirpath, prefix):
    files = []
    for root, dirnames, filenames in os.walk(dirpath):
        _root = root.split(prefix)[1]
        if _root[0] == '/':
            _root = _root[1:]
        files.extend([os.path.join(_root, x) for x in filenames])
    return files


def find_newer_files(prefix, compfile, include_link=False):
    '''
    Returns all files that have a change (metadata of file, e.g. permissions)
    or modification time (file content modified) which is newer than the one
    from compfile.
    '''
    include_links = include_link and '-L' or ''
    cmd = 'find %s * \( -type f -o -type l \) \( -cnewer %s -o -newer %s \)' % \
        (include_links, compfile, compfile)
    sfiles = check_output(cmd, prefix).split('\n')
    sfiles.remove('')
    return sfiles


def replace(filepath, replacements):
    ''' Replaces keys in the 'replacements' dict with their values in file '''
    with open(filepath, 'r') as f:
        content = f.read()
    for k, v in replacements.items():
        content = content.replace(k, v)
    with open(filepath, 'w+') as f:
        f.write(content)


def find_files(pattern, prefix):
    return glob.glob(os.path.join(prefix, pattern))


def prompt(message, options=[]):
    ''' Prompts the user for input with the message and options '''
    if len(options) != 0:
        message = "%s [%s] " % (message, '/'.join(options))
    res = input(message)
    while res not in [str(x) for x in options]:
        res = input(message)
    return res


def prompt_multiple(message, options):
    ''' Prompts the user for input with using a list of string options'''
    output = message + '\n'
    for i in range(len(options)):
        output += "[%s] %s\n" % (i, options[i])
    res = input(output)
    while res not in [str(x) for x in range(len(options))]:
        res = input(output)
    return options[int(res)]


def copy_dir(src, dest, exclude_dirs=[]):
    if not os.path.exists(src):
        return
    for path in os.listdir(src):
        if path in exclude_dirs:
            continue
        s = os.path.join(src, path)
        d = os.path.join(dest, path)
        if not os.path.exists(os.path.dirname(d)):
            os.makedirs(os.path.dirname(d))
        if os.path.isfile(s):
            shutil.copy(s, d)
        elif os.path.isdir(s):
            copy_dir(s, d, exclude_dirs)


def touch(path, create_if_not_exists=False, offset=0):
    if not os.path.exists(path):
        if create_if_not_exists:
            open(path, 'w').close()
        else:
            return
    t = time.time() + offset
    os.utime(path, (t, t))


def file_sha256(path):
    '''
    Get the file SHA256 hash
    '''
    return hashlib.sha256(open(path, 'rb').read()).digest()


def enter_build_environment(platform, arch, sourcedir=None):
    '''
    Enters to a new shell with the build environment
    '''
    BASHRC = '''
if [ -e ~/.bashrc ]; then
source ~/.bashrc
fi
%s
PS1='\[\033[01;32m\][cerbero-%s-%s]\[\033[00m\]%s '
'''
    MSYSBAT = '''
start bash.exe --rcfile %s
'''
    if sourcedir:
        sourcedirsh = 'cd ' + sourcedir
    else:
        sourcedirsh = ''

    ps1 = os.environ.get('PS1', '')

    if PLATFORM == Platform.WINDOWS:
        msysbatdir = tempfile.mkdtemp()
        msysbat = os.path.join(msysbatdir, "msys.bat")
        bashrc = os.path.join(msysbatdir, "bash.rc")
        with open(msysbat, 'w+') as f:
            f.write(MSYSBAT % bashrc)
        with open(bashrc, 'w+') as f:
            f.write(BASHRC % (sourcedirsh, platform, arch, ps1))
        subprocess.check_call(msysbat, shell=True)
        # We should remove the temporary directory
        # but there is a race with the bash process
    else:
        bashrc = tempfile.NamedTemporaryFile()
        bashrc.write((BASHRC % (sourcedirsh, platform, arch, ps1)).encode())
        bashrc.flush()
        shell = os.environ.get('SHELL', '/bin/bash')
        if os.system("%s --rcfile %s -c echo 'test' > /dev/null 2>&1" % (shell, bashrc.name)) == 0:
            os.execlp(shell, shell, '--rcfile', bashrc.name)
        else:
            os.environ["CERBERO_ENV"] = "[cerbero-%s-%s]" % (platform, arch)
            os.execlp(shell, shell)
        bashrc.close()


def which(pgm, path=None):
    if path is None:
        path = os.getenv('PATH')
    for p in path.split(os.path.pathsep):
        p = os.path.join(p, pgm)
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
        if PLATFORM == Platform.WINDOWS:
            for ext in os.getenv('PATHEXT').split(';'):
                pext = p + ext
                if os.path.exists(pext):
                    return pext


def check_tool_version(tool_name, needed, env):
    found = False
    newer = False
    if env is None:
        env = os.environ.copy()
    tool = which(tool_name, env['PATH'])
    if not tool:
        return None, False, False
    try:
        out = check_output([tool, '--version'], env=env)
    except FatalError:
        return None, False, False
    m = re.search('([0-9]+\.[0-9]+(\.[0-9]+)?)', out)
    if m:
        found = m.groups()[0]
        newer = StrictVersion(found) >= StrictVersion(needed)

    return tool, found, newer


def check_perl_version(needed, env):
    perl = which('perl', env['PATH'])
    try:
        out = check_output([perl, '--version'], env=env)
    except FatalError:
        return None, None, None
    m = re.search('v[0-9]+\.[0-9]+(\.[0-9]+)?', out)
    if not m:
        raise FatalError('Could not detect perl version')
    found = m.group()[1:]
    newer = StrictVersion(found) >= StrictVersion(needed)
    return perl, found, newer


def windows_proof_rename(from_name, to_name):
    '''
    On Windows, if you try to rename a file or a directory that you've newly
    created, an anti-virus may be holding a lock on it, and renaming it will
    yield a PermissionError. In this case, the only thing we can do is try and
    try again.
    '''
    delays = [0.1, 0.1, 0.2, 0.2, 0.2, 0.5, 0.5, 1, 1, 1, 1, 2]
    if PLATFORM == Platform.WINDOWS:
        for d in delays:
            try:
                os.rename(from_name, to_name)
                return
            except PermissionError:
                time.sleep(d)
                continue
    # Try one last time and throw an error if it fails again
    os.rename(from_name, to_name)


class BuildStatusPrinter:
    def __init__(self):
        self.step_to_recipe = collections.defaultdict(list)
        self.recipe_to_step = {}
        self.total = 0
        self.count = 0

    def _get_completion_percent(self, step, all_steps):
        one_recipe = 100. / float(self.total)
        one_step = one_recipe / len(all_steps)
        completed = 100. * float(self.count - 1) / float(self.total)
        for i, s in enumerate(all_steps):
            if step == s[1]:
                completed += i * one_step
        return int(completed)

    def update_recipe_step(self, count, recipe, step):
        recipe_name = recipe.name
        self.count = count
        m.build_step(count, self.total, self._get_completion_percent(step, recipe.steps), recipe_name, step)
