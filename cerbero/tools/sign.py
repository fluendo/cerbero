# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2019, Fluendo, S.A.
#  Author: Manel Jimeno <mjimeno@fluendo.com>, Fluendo, S.A.
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


class Sign(object):
    '''Wrapper for the sign tool'''

    def __init__(self, config, package):
        self.excludes = package.strip_excludes
        self.package = package

    def sign_file(self, path):
        for f in self.excludes:
            if f in path:
                return
        try:
            self.package.sign_dll(path)
        except:
            pass

    def sign_dir(self, dir_path):
        for dirpath, dirnames, filenames in os.walk(dir_path):
            for f in filenames:
                self.sign_file(os.path.join(dirpath, f))
