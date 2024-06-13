# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2024 Fluendo S.A <support@fluendo.com>
#   Authors: Maxim Dementyev <mdementyev@fluendo.com>
#            Andoni Morales <amorales@fluendo.com>
#            Jorge Zapata <jzapata@fluendo.com>
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

from cerbero.bootstrap import BootstrapperBase
from cerbero.bootstrap.bootstrapper import register_toolchain_bootstrapper
from cerbero.enums import Distro
from cerbero.utils import messages as m
from cerbero.utils import shell
import os.path
import shutil


EMSDK_VERSION = '3.1.61'
EMSDK_BUNDLE_EXT = '.tar.gz'
EMSDK_BASE_URL = 'https://github.com/emscripten-core/emsdk/archive/refs/tags/%s' + EMSDK_BUNDLE_EXT
EMSDK_CHECKSUMS = {'3.1.61' + EMSDK_BUNDLE_EXT: '51a4f6ec070147abe8f94546d8e18dde458d63f8c2927f94265ad49ef8431a1c'}


class EmscriptenToolchainBootstrapper(BootstrapperBase):
    """
    Bootstrapper for Emscripten builds.
    Installs the Emscripten SDK
    """

    def __init__(self, config, offline, assume_yes):
        super().__init__(config, offline, 'emscripten')
        url = EMSDK_BASE_URL % (EMSDK_VERSION)
        bundle_name = 'emsdk-' + EMSDK_VERSION + EMSDK_BUNDLE_EXT
        urls = (url, bundle_name, EMSDK_CHECKSUMS[os.path.basename(url)])
        self.fetch_urls.append(urls)
        self.extract_steps.append((url, True, self.config.home_dir))

    async def start(self, jobs=0):
        sdk_path_after_extract = os.path.join(self.config.home_dir, 'emsdk-' + EMSDK_VERSION)
        shutil.rmtree(self.config.toolchain_prefix)  # to be sure it's rename and not a move
        shutil.move(sdk_path_after_extract, self.config.toolchain_prefix)
        m.message(f'Install Emscripten SDK {EMSDK_VERSION}...')
        await shell.async_call_output(
            ['./emsdk', 'install', EMSDK_VERSION], cmd_dir=self.config.toolchain_prefix, cpu_bound=False
        )
        m.message('Activate Emscripten SDK...')
        await shell.async_call_output(
            ['./emsdk', 'activate', EMSDK_VERSION], cmd_dir=self.config.toolchain_prefix, cpu_bound=False
        )


def register_all():
    register_toolchain_bootstrapper(Distro.EMSCRIPTEN, EmscriptenToolchainBootstrapper)
