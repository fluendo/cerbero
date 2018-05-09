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

from cerbero.bootstrap import BootstraperBase
from cerbero.bootstrap.bootstraper import register_bootstraper
from cerbero.config import Platform, Architecture, Distro, DistroVersion
from cerbero.utils import shell, os


class UnixBootstraper (BootstraperBase):
    tool = ''
    packages = []
    distro_packages = {}
    winetricks_tool = ''
    msxml3_path = ''

    def _download_winetricks(self):
        if self.config.distro_version in [DistroVersion.DEBIAN_STRETCH]:
            self.winetricks_tool = os.path.join(self.config.build_tools_prefix, 'winetricks')
            WINETRICKS_URL = 'https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks'
            if not os.path.isfile(self.winetricks_tool):
                shell.download(WINETRICKS_URL, self.winetricks_tool)
            shell.call ('chmod +x %s' % self.winetricks_tool)
        else:
            self.winetricks_tool = 'winetricks'
            shell.call(self.tool % ' winetricks')
    # This method aims to download missing package manually helping winetricks. This method became useless
    # with dotnot40 but helps dotnet45 installation on ubuntu 16.04.
    def _download_wine_package(self, path_name, package_name):
        package_path = os.path.expanduser('~/.cache/winetricks/%s/' % path_name)
        url = 'ftp://fluendosys:fluendo\ sys@officestorage1.fluendo.lan/data/fluendo/tech/private/cerbero/custom_packages/wine/%s' % package_name
        if not os.path.exists (package_path):
            os.makedirs (package_path)
            package_path = os.path.expanduser('~/.cache/winetricks/%s/%s' % (path_name, package_name))
            shell.download(url, package_path)

    def _download_missing_wine_deps(self):
        self._download_winetricks()

    def _install_dotnet_for_wine(self):
        self._download_missing_wine_deps()
        os.environ['WINE'] = "wineconsole"
        shell.call('%s -q dotnet40 corefonts' % self.winetricks_tool)

    def start(self):
        packages = self.packages
        if self.config.distro_version in self.distro_packages:
            packages += self.distro_packages[self.config.distro_version]
        if 'wine' in self.packages:
          if self.config.distro_version in [DistroVersion.DEBIAN_STRETCH]:
            ["wine32" if x=="wine" else x for x in a]
          shell.call('echo ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true | sudo debconf-set-selections')
        shell.call(self.tool % ' '.join(self.packages))
        if 'wine' in self.packages:
            shell.call(self.tool % ' cabextract')
            self._install_dotnet_for_wine()

class DebianBootstraper (UnixBootstraper):

    packages = ['autotools-dev', 'automake', 'autoconf', 'libtool', 'g++',
                'autopoint', 'make', 'cmake', 'bison', 'flex', 'yasm',
                'pkg-config', 'gtk-doc-tools', 'libxv-dev', 'libx11-dev',
                'libpulse-dev', 'python-dev', 'texinfo', 'gettext',
                'build-essential', 'doxygen', 'curl',
                'libxext-dev', 'libxi-dev', 'x11proto-record-dev',
                'libxrender-dev', 'libgl1-mesa-dev', 'libxfixes-dev',
                'libxdamage-dev', 'libxcomposite-dev', 'libasound2-dev',
                'libxml-simple-perl', 'dpkg-dev', 'debhelper',
                'devscripts', 'fakeroot', 'transfig',
                'gperf', 'libdbus-glib-1-dev', 'wget', 'glib-networking',
                'intltool', 'git']
    distro_packages = {
        DistroVersion.DEBIAN_SQUEEZE: ['libgtk2.0-dev'],
        DistroVersion.UBUNTU_MAVERICK: ['libgtk2.0-dev'],
        DistroVersion.UBUNTU_LUCID: ['libgtk2.0-dev'],
        DistroVersion.UBUNTU_NATTY: ['libgtk2.0-dev'],
        DistroVersion.DEBIAN_WHEEZY: ['libgdk-pixbuf2.0-dev'],
        DistroVersion.DEBIAN_JESSIE: ['libgdk-pixbuf2.0-dev'],
        DistroVersion.DEBIAN_STRETCH: ['libgdk-pixbuf2.0-dev'],
        DistroVersion.UBUNTU_ONEIRIC: ['libgdk-pixbuf2.0-dev'],
        DistroVersion.UBUNTU_PRECISE: ['libgdk-pixbuf2.0-dev'],
    }

    def __init__(self, config, assume_yes, non_interactive):
        UnixBootstraper.__init__(self, config, assume_yes, non_interactive)
        if self.config.target_platform == Platform.WINDOWS:
            if self.config.arch == Architecture.X86_64:
                if self.config.distro_version in [DistroVersion.UBUNTU_MAVERICK,
                    DistroVersion.UBUNTU_HARDY, DistroVersion.UBUNTU_LUCID,
                    DistroVersion.UBUNTU_NATTY, DistroVersion.UBUNTU_PRECISE]:
                  self.packages.append('ia32-libs')
                elif self.config.distro_version in [DistroVersion.UBUNTU_XENIAL]:
                  self.packages.append('libc6:i386 libncurses5:i386 libstdc++6:i386')
        if self.config.distro_version in [DistroVersion.DEBIAN_SQUEEZE,
                DistroVersion.UBUNTU_MAVERICK, DistroVersion.UBUNTU_LUCID]:
            self.packages.remove('glib-networking')
        if self.config.distro_version in [DistroVersion.UBUNTU_LUCID]:
            self.packages.remove('autopoint')
        plat_packages = self.config.extra_bootstrap_packages.get(
                self.config.platform, None)
        if plat_packages:
            self.packages += plat_packages.get(self.config.distro, [])

        tool = 'sudo apt-get'
        if self.assume_yes or self.non_interactive:
            tool += ' -y'
        tool += ' install %s'
        if self.non_interactive:
            tool = 'DEBIAN_FRONTEND=noninteractive ' + tool
        self.tool = tool


class RedHatBootstraper (UnixBootstraper):

    tool = 'su -c "yum install %s"'
    packages = ['gcc', 'gcc-c++', 'automake', 'autoconf', 'libtool',
                'gettext-devel', 'make', 'cmake', 'bison', 'flex', 'yasm',
                'pkgconfig', 'gtk-doc', 'curl', 'doxygen', 'texinfo',
                'texinfo-tex', 'texlive-dvips', 'docbook-style-xsl',
                'transfig', 'intltool', 'rpm-build', 'redhat-rpm-config',
                'python-devel', 'libXrender-devel', 'pulseaudio-libs-devel',
                'libXv-devel', 'mesa-libGL-devel', 'libXcomposite-devel',
                'alsa-lib-devel', 'perl-ExtUtils-MakeMaker', 'libXi-devel',
                'perl-XML-Simple', 'gperf', 'gdk-pixbuf2-devel', 'wget',
                'docbook-utils-pdf', 'glib-networking']


class OpenSuseBootstraper (UnixBootstraper):

    tool = 'sudo zypper install %s'
    packages = ['gcc', 'automake', 'autoconf', 'gcc-c++', 'libtool',
            'gettext-tools', 'make', 'cmake', 'bison', 'flex', 'yasm',
            'gtk-doc', 'curl', 'doxygen', 'texinfo',
            'texlive', 'docbook-xsl-stylesheets',
            'transfig', 'intltool', 'patterns-openSUSE-devel_rpm_build',
            'python-devel', 'xorg-x11-libXrender-devel', 'libpulse-devel',
            'xorg-x11-libXv-devel', 'Mesa-libGL-devel', 'libXcomposite-devel',
            'alsa-devel', 'libXi-devel', 'Mesa-devel',
            'perl-XML-Simple', 'gperf', 'gdk-pixbuf-devel', 'wget',
            'docbook-utils', 'glib-networking']


def register_all():
    register_bootstraper(Distro.DEBIAN, DebianBootstraper)
    register_bootstraper(Distro.REDHAT, RedHatBootstraper)
    register_bootstraper(Distro.SUSE, OpenSuseBootstraper)
