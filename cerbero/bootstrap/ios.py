#!/usr/bin/env python
#
#       ios.py
#
# Copyright (C) 2013 Thibault Saunier <thibaul.saunier@collabora.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.

from cerbero.bootstrap import BootstraperBase
from cerbero.bootstrap.bootstraper import register_bootstraper
from cerbero.config import Distro, DistroVersion
from cerbero.utils import shell


class IOSBootstraper (BootstraperBase):

    def start(self):
        # libvpx needs this change because if You first install Command line tools and then Xcode
        # , your xcode-select variable is set to command line tools not to Xcode itself.
        # Command line tools don't have iOS libraries that are needed for build;
        if self.config.distro_version in [DistroVersion.OS_X_HIGH_SIERRA]:
            shell.call('sudo xcode-select -switch /Applications/Xcode.app')
        # FIXME: enable it when buildbots are properly configured
        return


def register_all():
    register_bootstraper(Distro.IOS, IOSBootstraper)
