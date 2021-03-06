# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2013 Andoni Morales Alastruey <ylatuya@gmail.com>
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
import re

from cerbero.config import Platform
from cerbero.utils import shell, run_until_complete, messages as m


class RecursiveLister():

    async def async_list_file_deps(self, prefix, path):
        raise NotImplemented()

    async def async_find_deps(self, prefix, lib, state={}, ordered=[]):
        lib_state = state.get(lib, 'clean')
        if lib_state == 'processed' or lib_state == 'in-progress':
            return ordered
        state[lib] = 'in-progress'
        lib_deps = await self.async_list_file_deps(prefix, lib)
        for libdep in lib_deps:
            await self.async_find_deps(prefix, libdep, state, ordered)
        state[lib] = 'processed'
        ordered.append(lib)
        return ordered

    async def async_list_deps(self, prefix, path):
        return await self.async_find_deps(prefix, os.path.realpath(path))


class ObjdumpLister(RecursiveLister):

    async def async_list_file_deps(self, prefix, path):
        try:
            files = await shell.async_check_output(['objdump', '-xw', path])
        except Exception as e:
            m.warning(e)
            return []

        files = files.splitlines()
        prog = re.compile(r"(?i)^.*DLL[^:]*: (\S+\.dll)$")
        files = [prog.sub(r"\1", x) for x in files if prog.match(x) is not None]
        files = [os.path.join(prefix, 'bin', x) for x in files if
                 x.lower().endswith('dll')]
        return [os.path.realpath(x) for x in files if os.path.exists(x)]


class OtoolLister(RecursiveLister):

    async def async_list_file_deps(self, prefix, path):
        try:
            files = await shell.async_check_output(['otool', '-L', path])
        except Exception as e:
            m.warning(e)
            return []

        files = files.split('\n')[1:]
        files = [x.split(' ')[0][1:] for x in files if prefix in x or "@rpath" in x]
        return [x.replace("@rpath/", prefix) for x in files]


class LddLister():

    async def async_list_deps(self, prefix,  path):
        try:
            files = await shell.async_check_output(['ldd', path])
        except Exception as e:
            m.warning(e)
            return []

        files = files.split('\n')
        return [x.split(' ')[2] for x in files if prefix in x]


class DepsTracker():

    BACKENDS = {
        Platform.WINDOWS: ObjdumpLister,
        Platform.LINUX: LddLister,
        Platform.DARWIN: OtoolLister}

    def __init__(self, platform, prefix):
        self.libs_deps = {}
        self.prefix = prefix
        if self.prefix[:-1] != '/':
            self.prefix += '/'
        self.lister = self.BACKENDS[platform]()

    def list_deps(self, path):
        deps = run_until_complete(self.lister.async_list_deps(self.prefix, path))
        rdeps = []
        for d in deps:
            if os.path.islink(d):
                rdeps.append(os.path.realpath(d))
        return [x.replace(self.prefix, '') for x in deps + rdeps]
