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
import sysconfig
import shutil

from cerbero.config import Config, Platform, DistroVersion
from cerbero.bootstrap import BootstrapperBase
from cerbero.build.oven import Oven
from cerbero.build.cookbook import CookBook
from cerbero.commands.fetch import Fetch
from cerbero.utils import _, shell
from cerbero.utils import messages as m
from cerbero.errors import FatalError, ConfigurationError

from pathlib import PurePath

class BuildTools (BootstrapperBase, Fetch):

    # XXX: Remove vala-m4 and introspection-m4 once all GNOME recipes are
    # ported to Meson, and revisit gtk-doc-lite too.
    BUILD_TOOLS = ['automake', 'autoconf', 'm4', 'libtool', 'gettext-tools',
                   'pkg-config', 'orc-tool', 'gettext-m4', 'vala-m4',
                   'gobject-introspection-m4', 'gtk-doc-lite', 'meson']
    PLAT_BUILD_TOOLS = {
        Platform.DARWIN: ['intltool', 'yasm', 'bison', 'flex'],
        Platform.WINDOWS: ['intltool', 'yasm'],
        Platform.LINUX: ['intltool-m4', 'patchelf'],
    }

    def __init__(self, config, offline, use_binaries=False, upload_binaries=False,
                 missing_files=False):
        BootstrapperBase.__init__(self, config, offline)

        self.use_binaries = use_binaries
        self.upload_binaries = upload_binaries
        self.missing_files = missing_files

        if self.config.platform == Platform.WINDOWS:
            if 'm4' in self.BUILD_TOOLS:
                self.BUILD_TOOLS.remove('m4')
            self.BUILD_TOOLS.append('gperf')
        if self.config.platform == Platform.DARWIN:
            self.BUILD_TOOLS.append('gperf')
        if self.config.platform == Platform.LINUX:
            if self.config.distro_version == DistroVersion.UBUNTU_LUCID or \
                self.config.distro_version == DistroVersion.DEBIAN_SQUEEZE or \
                self.config.distro_version == DistroVersion.DEBIAN_WHEEZY:
                # x264 requires yasm >= 1.2
                self.BUILD_TOOLS.append('yasm')
        if self.config.target_platform == Platform.IOS:
            self.BUILD_TOOLS.append('gas-preprocessor')
        if self.config.distro_version in [DistroVersion.UBUNTU_LUCID,
                                          DistroVersion.UBUNTU_NATTY]:
            self.BUILD_TOOLS.append('glib-tools')
        if self.config.target_platform != Platform.LINUX and not \
           self.config.prefix_is_executable():
            # For glib-mkenums and glib-genmarshal
            self.BUILD_TOOLS.append('glib-tools')
        self.BUILD_TOOLS += self.config.extra_build_tools

    def check_build_tools(self):
        '''
        Check whether the build tools we have are new enough, and if not, build
        them ourselves. On Windows, we always build nasm ourselves, and we tell
        the user to install CMake using the installer.
        '''
        ret = []
        if self.config.platform in (Platform.LINUX, Platform.DARWIN):
            # need cmake > 3.10.2 for out-of-source-tree builds.
            tool, found, newer = shell.check_tool_version('cmake' ,'3.10.2', env=None)
            if not newer:
                ret.append('cmake')
        return ret

    def _setup_env(self):
        # Start with the original env that cerbero was called with
        os.environ.clear()
        os.environ.update(self.config._pre_environ)
        # Use a common prefix for the build tools for all the configurations
        # so that it can be reused
        config = Config()
        config.prefix = self.config.build_tools_prefix
        config.home_dir = self.config.home_dir
        config.local_sources = self.config.local_sources
        config.load()

        config.prefix = self.config.build_tools_prefix
        config.build_tools_prefix = self.config.build_tools_prefix
        config.sources = self.config.build_tools_sources
        config.build_tools_sources = self.config.build_tools_sources
        config.cache_file = self.config.build_tools_cache
        config.build_tools_cache = self.config.build_tools_cache
        config.external_recipes = self.config.external_recipes
        config.toolchain_prefix = self.config.toolchain_prefix
        config.binaries_local = self.config.binaries_local
        config.binaries_remote = self.config.binaries_remote

        if config.toolchain_prefix and not os.path.exists(config.toolchain_prefix):
            os.makedirs(config.toolchain_prefix)
        if not os.path.exists(config.prefix):
            os.makedirs(config.prefix)
        if not os.path.exists(config.sources):
            os.makedirs(config.sources)

        config.do_setup_env()
        self.cookbook = CookBook(config, offline=self.offline)
        self.recipes = self.BUILD_TOOLS
        self.recipes += self.PLAT_BUILD_TOOLS.get(self.config.platform, [])

    def insert_python_site(self):
        try:
            import setuptools.version as stv
        except ImportError:
            return

        version = [int(v) for v in stv.__version__.split('.')]
        if len(version) < 1 or version[:1] < [49]:
            return

        m.warning('detected setuptools >= 49.0.0, installing fallback site.py file. '
            'See https://github.com/pypa/setuptools/issues/2295')

        # Since python-setuptools 49.0.0, site.py is not installed by
        # easy_install/setup.py anymore which breaks python installs outside
        # the system prefix.
        # https://github.com/pypa/setuptools/issues/2295
        #
        # Install the previously installed site.py ourselves as a workaround
        config = self.cookbook.get_config()

        py_prefix = sysconfig.get_path('purelib', 'posix_prefix', vars={'base': ''})
        # Must strip \/ to ensure that the path is relative
        py_prefix = PurePath(config.prefix) / PurePath(py_prefix.strip('\\/'))
        src_file = os.path.join(os.path.dirname(__file__), 'site-patch.py')
        shutil.copy(src_file, py_prefix / 'site.py')

    def start(self, jobs=0):
        self._setup_env()
        self.insert_python_site()
        # Check build tools at the last minute because we may have installed them
        # in system bootstrap
        self.recipes += self.check_build_tools()
        oven = Oven(self.recipes, self.cookbook, missing_files=self.missing_files)
        oven.start_cooking(self.use_binaries, self.upload_binaries)
        self.config.do_setup_env()

    def fetch_recipes(self, jobs):
        self._setup_env()
        # Check build tools at the last minute because we may have installed them
        # in system bootstrap
        self.recipes += self.check_build_tools()
        Fetch.fetch(self.cookbook, self.recipes, False, False, False, False, jobs, use_binaries=self.use_binaries)
        self.config.do_setup_env()
