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

import os
import shutil
import sys
try:
    import sysconfig
except:
    from distutils import sysconfig
try:
    import xml.etree.cElementTree as etree
except ImportError:
    from lxml import etree
import gettext
import platform as pplatform
import re

from cerbero.enums import Platform, Architecture, Distro, DistroVersion
from cerbero.errors import FatalError
from cerbero.utils import messages as m

_ = gettext.gettext
N_ = lambda x: x


class ArgparseArgument(object):

    def __init__(self, *name, **kwargs):
        self.name = name
        self.args = kwargs

    def add_to_parser(self, parser):
        parser.add_argument(*self.name, **self.args)


def user_is_root():
        ''' Check if the user running the process is root '''
        return hasattr(os, 'getuid') and os.getuid() == 0


def determine_num_of_cpus():
    ''' Number of virtual or physical CPUs on this system '''

    # Python 2.6+
    try:
        import multiprocessing
        return multiprocessing.cpu_count()
    except (ImportError, NotImplementedError):
        return 1


def to_winpath(path):
    if path.startswith('/'):
        path = '%s:%s' % (path[1], path[2:])
    return path.replace('/', '\\')


def to_unixpath(path):
    if path[1] == ':':
        path = '/%s%s' % (path[0], path[2:])
    return path


def to_odd_cased_unixpath(path):
    if path[1] == ':':
        # from winpath
        drive_letter = path[0]
        if drive_letter.isupper():
            drive_letter = drive_letter.lower()
        else:
            drive_letter = drive_letter.upper()
        path = drive_letter + path[1:]
        path = to_unixpath(path)
    elif path[0] == '/':
        # from unixpath
        drive_letter = path[1]
        if drive_letter.isupper():
            drive_letter = drive_letter.lower()
        else:
            drive_letter = drive_letter.upper()
        path = path[0] + drive_letter + path[2:]
    return path


def to_winepath(path):
        path = path.replace('/', '\\\\')
        # wine maps the filesystem root '/' to 'z:\'
        path = 'z:\\%s' % path
        return path


def fix_winpath(path):
    return path.replace('\\', '/')


def system_info():
    '''
    Get the sysem information.
    Return a tuple with the platform type, the architecture and the
    distribution
    '''

    # Get the platform info
    platform = sys.platform
    if platform.startswith('win'):
        platform = Platform.WINDOWS
    elif platform.startswith('darwin'):
        platform = Platform.DARWIN
    elif platform.startswith('linux'):
        platform = Platform.LINUX
    else:
        raise FatalError(_("Platform %s not supported") % platform)

    # Get the architecture info
    if platform == Platform.WINDOWS:
        platform_str = sysconfig.get_platform()
        if platform_str in ['win-amd64', 'win-ia64']:
            arch = Architecture.X86_64
        else:
            arch = Architecture.X86
    else:
        uname = os.uname()
        arch = uname[4]
        if arch == 'x86_64':
            arch = Architecture.X86_64
        elif arch.endswith('86'):
            arch = Architecture.X86
        elif arch == "Power Macintosh":
            arch = Architecture.PPC
        else:
            raise FatalError(_("Architecture %s not supported") % arch)

    # Get the distro info
    if platform == Platform.LINUX:
        d = pplatform.linux_distribution()
        if d[0] in ['Ubuntu', 'debian']:
            distro = Distro.DEBIAN
            if d[2] == 'maverick':
                distro_version = DistroVersion.UBUNTU_MAVERICK
            elif d[2] == 'hardy':
                distro_version = DistroVersion.UBUNTU_HARDY
            elif d[2] == 'lucid':
                distro_version = DistroVersion.UBUNTU_LUCID
            elif d[2] == 'natty':
                distro_version = DistroVersion.UBUNTU_NATTY
            elif d[2] == 'oneiric':
                distro_version = DistroVersion.UBUNTU_ONEIRIC
            elif d[2] == 'precise':
                distro_version = DistroVersion.UBUNTU_PRECISE
            elif d[2] == 'quantal':
                distro_version = DistroVersion.UBUNTU_QUANTAL
            elif d[2] == 'raring':
                distro_version = DistroVersion.UBUNTU_RARING
            elif d[2] == 'saucy':
                distro_version = DistroVersion.UBUNTU_SAUCY
            elif d[2] == 'trusty':
                distro_version = DistroVersion.UBUNTU_TRUSTY
            elif d[2] == 'utopic':
                distro_version = DistroVersion.UBUNTU_UTOPIC
            elif d[2] == 'vivid':
                distro_version = DistroVersion.UBUNTU_VIVID
            elif d[2] == 'wily':
                distro_version = DistroVersion.UBUNTU_WILY
            elif d[2] == 'xenial':
                distro_version = DistroVersion.UBUNTU_XENIAL
            elif d[1].startswith('6.'):
                distro_version = DistroVersion.DEBIAN_SQUEEZE
            elif d[1].startswith('7.') or d[1].startswith('wheezy'):
                distro_version = DistroVersion.DEBIAN_WHEEZY
            elif d[1].startswith('jessie'):
                distro_version = DistroVersion.DEBIAN_JESSIE
            elif d[1].startswith('9.'):
                distro_version = DistroVersion.DEBIAN_STRETCH
            else:
                raise FatalError("Distribution '%s' not supported" % str(d))
        elif d[0] in ['RedHat', 'Fedora', 'CentOS']:
            distro = Distro.REDHAT
            if d[1] == '16':
                distro_version = DistroVersion.FEDORA_16
            elif d[1] == '17':
                distro_version = DistroVersion.FEDORA_17
            elif d[1] == '18':
                distro_version = DistroVersion.FEDORA_18
            elif d[1] == '19':
                distro_version = DistroVersion.FEDORA_19
            elif d[1] == '20':
                distro_version = DistroVersion.FEDORA_20
            elif d[1].startswith('6.'):
                distro_version = DistroVersion.REDHAT_6
            else:
                # FIXME Fill this
                raise FatalError("Distribution '%s' not supported" % str(d))
        elif d[0].strip() in ['openSUSE']:
            distro = Distro.SUSE
            if d[1] == '12.1':
                distro_version = DistroVersion.OPENSUSE_12_1
            elif d[1] == '12.2':
                distro_version = DistroVersion.OPENSUSE_12_2
            elif d[1] == '12.3':
                distro_version = DistroVersion.OPENSUSE_12_3
            else:
                # FIXME Fill this
                raise FatalError("Distribution OpenSuse '%s' "
                                 "not supported" % str(d))
        else:
            raise FatalError("Distribution '%s' not supported" % str(d))
    elif platform == Platform.WINDOWS:
        distro = Distro.WINDOWS
        win32_ver = pplatform.win32_ver()[0].lower()
        dmap = {'xp': DistroVersion.WINDOWS_XP,
                'vista': DistroVersion.WINDOWS_VISTA,
                '7': DistroVersion.WINDOWS_7,
                '8': DistroVersion.WINDOWS_8,
                '8.1': DistroVersion.WINDOWS_8,
                '10': DistroVersion.WINDOWS_10,
                'post2008Server': DistroVersion.WINDOWS_8}
        if win32_ver in dmap:
            distro_version = dmap[win32_ver]
        else:
            raise FatalError("Windows version '%s' not supported" % win32_ver)
    elif platform == Platform.DARWIN:
        distro = Distro.OS_X
        ver = pplatform.mac_ver()[0]
        if ver.startswith('10.13'):
            distro_version = DistroVersion.OS_X_HIGH_SIERRA
        elif ver.startswith('10.12'):
            distro_version = DistroVersion.OS_X_SIERRA
        elif ver.startswith('10.11'):
            distro_version = DistroVersion.OS_X_EL_CAPITAN
        elif ver.startswith('10.10'):
            distro_version = DistroVersion.OS_X_YOSEMITE
        elif ver.startswith('10.9'):
            distro_version = DistroVersion.OS_X_MAVERICKS
        elif ver.startswith('10.8'):
            distro_version = DistroVersion.OS_X_MOUNTAIN_LION
        elif ver.startswith('10.7'):
            distro_version = DistroVersion.OS_X_LION
        elif ver.startswith('10.6'):
            distro_version = DistroVersion.OS_X_SNOW_LEOPARD
        elif ver.startswith('10.5'):
            distro_version = DistroVersion.OS_X_LEOPARD
        else:
            raise FatalError("Mac version %s not supported" % ver)

    num_of_cpus = determine_num_of_cpus()

    return platform, arch, distro, distro_version, num_of_cpus


def validate_packager(packager):
    # match packager in the form 'Name <email>'
    expr = r'(.*\s)*[<]([a-zA-Z0-9+_\-\.]+@'\
        '[0-9a-zA-Z][.-0-9a-zA-Z]*.[a-zA-Z]+)[>]$'
    return bool(re.match(expr, packager))


def copy_files(origdir, destdir, files, extensions, target_platform):
    for f in files:
        f = f % extensions
        install_dir = os.path.dirname(os.path.join(destdir, f))
        if not os.path.exists(install_dir):
            os.makedirs(install_dir)
        if destdir[1] == ':':
            # windows path
            relprefix = to_unixpath(destdir)[2:]
        else:
            relprefix = destdir[1:]
        orig = os.path.join(origdir, relprefix, f)
        dest = os.path.join(destdir, f)
        m.action("copying %s to %s" % (orig, dest))
        try:
            shutil.copy(orig, dest)
        except IOError:
            m.warning("Could not copy %s to %s" % (orig, dest))


def remove_list_duplicates(seq):
    ''' Remove list duplicates maintaining the order '''
    seen = set()
    seen_add = seen.add
    return [x for x in seq if x not in seen and not seen_add(x)]


def parse_file(filename, dict):
    if '__file__' not in dict:
        dict['__file__'] = filename
    try:
        execfile(filename, dict)
    except Exception, ex:
        import traceback
        traceback.print_exc()
        raise ex


def escape_path(path):
    path = path.replace('\\', '/')
    path = path.replace('(', '\\\(').replace(')', '\\\)')
    path = path.replace(' ', '\\\\ ')
    return path


def get_wix_prefix():
    if 'WIX' in os.environ:
        wix_prefix = os.path.join(os.environ['WIX'],'bin')
    else:
        wix_prefix = 'C:/Program Files%s/WiX Toolset v3.6/bin'
        if not os.path.exists(wix_prefix):
            wix_prefix = wix_prefix % ' (x86)'
    if not os.path.exists(wix_prefix):
        raise FatalError("The required packaging tool 'WiX' was not found")
    return escape_path(to_unixpath(wix_prefix))


def replace_prefix_infile(prefix, file, replacement='{PREFIX}'):
    '''
    Replace all possible ways of writing the prefix.
    This function replaces in a file.

    @cvar prefix: prefix to be replaced
    @rtype: str
    @cvar file: file name to be replaced
    @rtype: str
    @cvar replacement: the placeholder to put instead of the prefix
    @rtype: str
    '''
    shell.replace(file, {
        prefix: replacement,
        to_unixpath(prefix): replacement,
        to_winpath(prefix): replacement,
        to_winepath(prefix): replacement,
        to_odd_cased_unixpath(prefix): replacement,
        os.path.normpath(prefix): replacement,
    })


def replace_prefix(prefix, string, replacement='{PREFIX}'):
    '''
    Replace all possible ways of writing the prefix.
    This function replaces in a string.

    @return: replaced string
    @rtype: str

    @cvar prefix: prefix to be replaced
    @rtype: str
    @cvar string: the original string
    @rtype: str
    @cvar replacement: the placeholder to put instead of the prefix
    @rtype: str
    '''
    for p in [prefix, to_unixpath(prefix), to_winpath(prefix),
              to_winepath(prefix), to_odd_cased_unixpath(prefix),
              os.path.normpath(prefix)]:
        string = string.replace(p, replacement)
    return string


def is_text_file(filename):
    '''
    Check if a file is text or binary.
    This uses the same logic as file(1).
    Adapted from https://stackoverflow.com/a/7392391/1324984.
    '''
    textchars = bytearray(set([7,8,9,10,12,13,27]) | set(range(0x20, 0x100)) - set([0x7f]))
    with open(filename, 'rb') as f:
        return f.read(1024).translate(None, textchars) == ''

#taken from https://stackoverflow.com/a/17548459
def file_string_replace(filename, old_string, new_string):
        # Safely read the input filename using 'with'
        with open(filename) as f:
            s = f.read()
            if old_string not in s:
                print '"{old_string}" not found in {filename}.'.format(**locals())
                return

        # Safely write the changed content, if found in the file
        with open(filename, 'w') as f:
            print 'Changing "{old_string}" to "{new_string}" in {filename}'.format(**locals())
            s = s.replace(old_string, new_string)
            f.write(s)
