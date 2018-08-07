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
import shlex
import sys
import os
import tarfile
import zipfile
import tempfile
import time
import glob
import shutil
import hashlib

from cerbero.enums import Platform
from cerbero.utils import _, system_info, to_unixpath
from cerbero.utils import messages as m
from cerbero.errors import FatalError


PATCH = 'patch'
TAR = 'tar'


PLATFORM = system_info()[0]
LOGFILE = None  # open('/tmp/cerbero.log', 'w+')
DRY_RUN = False


class StdOut:

    def __init__(self, stream=sys.stdout):
        self.stream = stream

    def write(self, data):
        self.stream.write(data)
        self.stream.flush()

    def __getattr__(self, attr):
        return getattr(self.stream, attr)


def _fix_mingw_cmd(path):
    reserved = ['/', ' ', '\\', ')', '(', '"']
    l_path = list(path)
    for i in range(len(path)):
        if path[i] == '\\':
            if i + 1 == len(path) or path[i + 1] not in reserved:
                l_path[i] = '/'
    return ''.join(l_path)


def call(cmd, cmd_dir='.', fail=True):
    '''
    Run a shell command

    @param cmd: the command to run
    @type cmd: str
    @param cmd_dir: directory where the command will be run
    @param cmd_dir: str
    @param fail: wheter to raise an exception if the command failed or not
    @type fail: bool
    '''
    try:
        m.message("Running command '%s' in path '%s'" % (cmd, cmd_dir))
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
        stream = LOGFILE or sys.stdout
        if DRY_RUN:
            # write to sdterr so it's filtered more easilly
            m.error ("cd %s && %s && cd %s" % (cmd_dir, cmd, os.getcwd()))
            ret = 0
        else:
            ret = subprocess.check_call(cmd, cwd=cmd_dir,
                                       stderr=subprocess.STDOUT,
                                       stdout=StdOut(stream),
                                       env=os.environ.copy(), shell=shell)
    except subprocess.CalledProcessError:
        if fail:
            raise FatalError(_("Error running command: %s") % cmd)
        else:
            ret = 0
    return ret


def check_call(cmd, cmd_dir=None, shell=False, split=True, fail=False):
    try:
        if split:
            cmd = shlex.split(cmd)
        process = subprocess.Popen(cmd, cwd=cmd_dir,
                                   stdout=subprocess.PIPE,
                                   stderr=open(os.devnull), shell=shell)
        output, unused_err = process.communicate()
        if process.poll() and fail:
            raise Exception()
    except Exception:
        raise FatalError(_("Error running command: %s") % cmd)
    return output


def apply_patch(patch, directory, strip=1):
    '''
    Apply a patch

    @param patch: path of the patch file
    @type patch: str
    @param directory: directory to apply the apply
    @type: directory: str
    @param strip: strip
    @type strip: int
    '''

    logging.info("Applying patch %s" % (patch))
    call('%s -p%s -f -i %s' % (PATCH, strip, patch), directory)


def unpack(filepath, output_dir):
    '''
    Extracts a tarball

    @param filepath: path of the tarball
    @type filepath: str
    @param output_dir: output directory
    @type output_dir: str
    '''
    logging.info("Unpacking %s in %s" % (filepath, output_dir))
    if filepath.endswith('tar.gz') or filepath.endswith('tar.bz2') or filepath.endswith('tgz'):
        tf = tarfile.open(filepath, mode='r:*')
        tf.extractall(path=output_dir)
    if filepath.endswith('tar.xz'):
        call("%s -Jxf %s" % (TAR, to_unixpath(filepath)), output_dir)
    if filepath.endswith('.zip'):
        zf = zipfile.ZipFile(filepath, "r")
        zf.extractall(path=output_dir)


def _get_download_cache_url(url, cache_url, filename = None):
    '''
    Get the cache url if available

    @param url: original url to download
    @type url: str
    @param cache_url: base cache url to use
    @type cache_url: str
    @param filename: custom filename to use
    @type filename: str
    '''
    if cache_url is None:
      return url
    if filename is None:
      dl_cache_url = cache_url + os.path.basename(url)
    else:
      dl_cache_url = cache_url + filename
    logging.info('Using the cache url: %s instead of %s' % (dl_cache_url, url))
    return dl_cache_url


def download(url, destination=None, recursive=False, check_cert=True, user=None, password=None, cache_url=None, filename = None):
    '''
    Downloads a file with wget

    @param url: url to download
    @type: str
    @param destination: destination where the file will be saved
    @type destination: str
    @param user: the username to use when connecting
    @type user: str
    @param password: the password to use when connecting
    @type password: str
    @param cache_url: cache url to try first
    @type cache_url: str
    @param filename: custom filename to use by the cache url
    @type filename: str
    '''
    original_url = None
    cache_url = _get_download_cache_url(url, cache_url, filename)
    if cache_url != url:
      original_url = url
      url = cache_url
    cmd = "wget %s " % url
    path = None
    if recursive:
        cmd += "-r "
        path = destination
    else:
        if destination is not None:
            cmd += "-O %s " % destination

    if not check_cert:
        cmd += " --no-check-certificate"

    if user:
        cmd += " --user=%s" % user
    if password:
        cmd += " --password=%s" % password

    if not recursive and os.path.exists(destination):
        logging.info("File %s already downloaded." % destination)
    else:
        logging.info("Downloading %s", url)
        try:
            call(cmd, path)
        except FatalError, e:
            os.remove(destination)
            if original_url is not None:
              try:
                cmd = cmd.replace(cache_url, original_url)
                call(cmd, path)
              except FatalError, e:
                os.remove(destination)
                raise e
            else:
              raise e


def download_curl(url, destination=None, recursive=False, check_cert=True, user=None, password=None, overwrite=False, cache_url=None, filename = None):
    '''
    Downloads a file with cURL

    @param url: url to download
    @type: str
    @param destination: destination where the file will be saved
    @type destination: str
    @param user: the username to use when connecting
    @type user: str
    @param password: the password to use when connecting
    @type password: str
    @param overwrite: in case the file exists overwrite it
    @type overwrite: bool
    @param cache_url: cache url to try first
    @type cache_url: str
    @param filename: custom filename to use by the cache url
    @type filename: str
    '''
    path = None
    if recursive:
        raise FatalError(_("cURL doesn't support recursive downloads"))

    original_url = None
    cache_url = _get_download_cache_url(url, cache_url, filename)
    if cache_url != url:
      original_url = url
      url = cache_url

    cmd = "curl -L "
    if user:
        cmd += "--user %s" % user
        if password:
            cmd += ":%s " % password
        else:
            cmd += " "
    if not check_cert:
        cmd += "-k "
    if destination is not None:
        cmd += "%s -o %s " % (url, destination)
    else:
        cmd += "-O %s " % url

    if not overwrite and os.path.exists(destination):
        logging.info("File %s already downloaded." % destination)
    else:
        logging.info("Downloading %s", url)
        try:
            call(cmd, path)
        except FatalError, e:
            if os.path.exists(destination):
              os.remove(destination)
            if original_url is not None:
              try:
                cmd = cmd.replace(cache_url, original_url)
                call(cmd, path)
              except FatalError, e:
                os.remove(destination)
                raise e
            else:
              raise e


def upload_curl(source, url, user=None, password=None):
    if not os.path.exists(source):
        raise FatalError(_("File %s does not exist.") % source)

    path = None
    cmd = "curl -T "
    cmd += "%s %s" % (source, url)
    if user:
        cmd += " --user %s" % user
        if password:
            cmd += ":%s " % password
        else:
            cmd += " "

    cmd += " --ftp-create-dirs "
    logging.info("Uploading %s to %s", source, url)
    call(cmd, path)

def _splitter(string, base_url):
    lines = string.split('\n')
    for line in lines:
        try:
            yield "%s/%s" % (base_url, line.split(' ')[2])
        except:
            continue


def recursive_download(url, destination):
    '''
    Recursive download for servers that don't return a list a url's but only
    the index.html file
    '''
    raw_list = check_call('curl %s' % url)

    with tempfile.NamedTemporaryFile() as f:
        for path in _splitter(raw_list, url):
            f.file.write(path + '\n')
        if not os.path.exists(destination):
            os.makedirs(destination)
        call("wget -i %s %s" % (f.name, url), destination)


def ls_files(files, prefix):
    if files == []:
        return files
    sfiles = check_call('ls %s' % ' '.join(files),
                        prefix, True, False, False).split('\n')
    sfiles.remove('')
    return list(set(sfiles))


def ls_dir(dirpath, prefix):
    files = []
    for root, dirnames, filenames in os.walk(dirpath):
        _root = root.split(prefix)[1]
        if _root[0] == '/':
            _root = _root[1:]
        files.extend([os.path.join(_root, x) for x in filenames])
    return files


def find_newer_files(prefix, compfile, include_link=False):
    include_links = include_link and '-L' or ''
    cmd = 'find %s * -type f -cnewer %s' % (include_links, compfile)
    sfiles = check_call(cmd, prefix, True, False, False).split('\n')
    sfiles.remove('')
    return sfiles


def replace(filepath, replacements):
    ''' Replaces keys in the 'replacements' dict with their values in file '''
    with open(filepath, 'r') as f:
        content = f.read()
    for k, v in replacements.iteritems():
        content = content.replace(k, v)
    with open(filepath, 'w+') as f:
        f.write(content)


def find_files(pattern, prefix):
    return glob.glob(os.path.join(prefix, pattern))


def prompt(message, options=[]):
    ''' Prompts the user for input with the message and options '''
    if len(options) != 0:
        message = "%s [%s] " % (message, '/'.join(options))
    res = raw_input(message)
    while res not in [str(x) for x in options]:
        res = raw_input(message)
    return res


def copy_dir(src, dest, exclude_dirs = []):
    if not os.path.exists(src):
        return
    for path in os.listdir(src):
        if path in exclude_dirs :
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


def file_hash(path):
    '''
    Get the file md5 hash
    '''
    try:
        return hashlib.md5(open(path, 'rb').read()).digest()
    except:
        return None


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
