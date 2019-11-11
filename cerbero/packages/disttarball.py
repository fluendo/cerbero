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
import tarfile
import tempfile

import cerbero.utils.messages as m
from cerbero.utils import shell, _, replace_prefix, is_text_file
from cerbero.enums import Platform
from cerbero.errors import FatalError, UsageError, EmptyPackageError
from cerbero.packages import PackagerBase, PackageType
from cerbero.tools import strip
from functools import lru_cache

RESTORE_SUFFIX = '.relocation_restore'


class DistTarball(PackagerBase):
    ''' Creates a distribution tarball '''

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self.package = package
        self.prefix = config.prefix
        self.package_prefix = ''
        if self.config.packages_prefix is not None:
            self.package_prefix = '%s-' % self.config.packages_prefix
        self.compress = config.package_tarball_compression
        if self.compress not in ('bz2', 'xz'):
            raise UsageError('Invalid compression type {!r}'.format(self.compress))

    @lru_cache(maxsize=None)
    def _files_list(self, devel=True, force=True, split=True):
        try:
            dist_files = super().files_list(PackageType.RUNTIME, force)
        except EmptyPackageError:
            m.warning(_("The runtime package is empty"))
            dist_files = []

        if devel:
            try:
                devel_files = super().files_list(PackageType.DEVEL, force)
            except EmptyPackageError:
                m.warning(_("The development package is empty"))
                devel_files = []
        else:
            devel_files = []

        if not split:
            dist_files += devel_files

        if not dist_files and not devel_files:
            raise EmptyPackageError(self.package.name)

        return dist_files, devel_files

    def pack(self, output_dir, devel=True, force=False, keep_temp=False,
             split=True, package_prefix='', strip_binaries=False, force_empty=False,
             relocatable=False, lib64_link=False):
        dist_files = []
        devel_files = []
        try:
            dist_files, devel_files = self._files_list(force=force, devel=devel, split=split)
        except EmptyPackageError:
            pass
        filenames = []
        create_tarball_func = self._create_tarball if not strip_binaries else self._create_tarball_stripped
        if dist_files or force_empty:
            runtime = create_tarball_func(output_dir, PackageType.RUNTIME,
                                          dist_files, force, package_prefix,
                                          relocatable, lib64_link)
            filenames.append(runtime)

        if split and devel and (len(devel_files) != 0 or force_empty):
            devel = create_tarball_func(output_dir, PackageType.DEVEL,
                                        devel_files, force, package_prefix,
                                        relocatable, lib64_link)
            filenames.append(devel)
        return filenames

    def get_name(self, package_type, ext=None):
        if ext is None:
            ext = 'tar.' + self.compress

        if self.config.target_platform != Platform.WINDOWS:
            platform = self.config.target_platform
        elif self.config.variants.visualstudio:
            platform = 'msvc'
        else:
            platform = 'mingw'

        # Use [devel_]files_list() just to check whether the package is an empty
        # package or not. In case of any error attempting to collect the files,
        # we assume there are no files needed for the package. We use this approach
        # instead of _files_list() because the latter checks for existing files
        # and throws exceptions in case of empty package.
        try:
            files = []
            if package_type == PackageType.DEVEL:
                files = self.package.devel_files_list()
            elif package_type == PackageType.RUNTIME:
                files = self.package.files_list()

            if len(files) == 0:
                return ""
        except Exception:
            return ""

        # Ensure there are no slashes in package version. e.g.
        # 19+git~origin/master-e65a012bc0001ab7a4e351dbed6af4cc to
        # 19+git~origin@master-e65a012bc0001ab7a4e351dbed6af4cc
        package_version = self.package.version.replace('/', '@')
        return "%s%s-%s-%s-%s%s.%s" % (self.package_prefix, self.package.name, platform,
                                       self.config.target_arch, package_version, package_type, ext)

    def _create_tarball_stripped(self, output_dir, package_type, files, force,
                                 package_prefix, relocatable, lib64_link):
        tmpdir = tempfile.mkdtemp(dir=self.config.home_dir)

        if hasattr(self.package, 'strip_excludes'):
            s = strip.Strip(self.config, self.package.strip_excludes)
        else:
            s = strip.Strip(self.config)

        for f in files:
            orig_file = os.path.join(self.prefix, f)
            tmp_file = os.path.join(tmpdir, f)
            tmp_file_dir = os.path.dirname(tmp_file)
            if not os.path.exists(tmp_file_dir):
                os.makedirs(tmp_file_dir)
            shutil.copy(orig_file, tmp_file, follow_symlinks=False)
            s.strip_file(tmp_file)

        prefix_restore = self.prefix
        self.prefix = tmpdir
        tarball = self._create_tarball(output_dir, package_type,
                                       files, force, package_prefix,
                                       relocatable, lib64_link)
        self.prefix = prefix_restore
        shutil.rmtree(tmpdir)

        return tarball

    def _create_tarball(self, output_dir, package_type, files, force,
                        package_prefix, relocatable, lib64_link):
        filename = os.path.join(output_dir, self.get_name(package_type))
        if os.path.exists(filename):
            if force:
                os.remove(filename)
            else:
                raise UsageError("File %s already exists" % filename)

        tar_files = []
        restore_files = []
        for f in files:
            filepath = os.path.join(self.prefix, f)
            if relocatable and not os.path.islink(filepath):
                if os.path.splitext(f)[1] in ['.la', '.pc'] or ('bin' in os.path.splitext(f)[0] and is_text_file(filepath)):
                    shutil.copy(filepath, filepath + RESTORE_SUFFIX)
                    restore_files.append(filepath)
                    with open(filepath, 'r+') as fo:
                        content = fo.read()
                        content = replace_prefix(self.config.prefix, content, 'CERBERO_PREFIX')
                        fo.seek(0)
                        fo.write(content)
                        fo.truncate()
                        fo.flush()
                        tar_files.append(filepath)
                else:
                    tar_files.append(filepath)
            else:
                tar_files.append(filepath)

        # This link allows to rpm packager to install the libs
        # in lib64 instead of lib without changing where cerbero
        # is installing its build artifacts.
        if lib64_link:
            filepath = os.path.join(self.prefix, 'lib64')
            try:
                os.symlink('lib', filepath)
            except OSError:
                pass
            files.append(filepath)

        if self.config.platform == Platform.WINDOWS:
            self._write_tarfile(filename, package_prefix, tar_files)
        else:
            self._write_tar(filename, package_prefix, tar_files)

        # Restore original files
        for f in restore_files:
            if os.path.isfile(f) and os.path.isfile(f + RESTORE_SUFFIX):
                shutil.copy(f + RESTORE_SUFFIX, f)
                os.remove(f + RESTORE_SUFFIX)

        if lib64_link:
            os.unlink(filepath)

        return filename

    def _write_tarfile(self, filename, package_prefix, files):
        try:
            with tarfile.open(filename, 'w:' + self.compress) as tar:
                for f in files:
                    base_filepath = f.replace(self.prefix, '')
                    base_filepath = base_filepath.lstrip('/').rstrip('\\')
                    tar.add(f, os.path.join(package_prefix, base_filepath))
        except OSError:
            os.replace(filename, filename + '.partial')
            raise

    def _write_tar(self, filename, package_prefix, files):
        tar_cmd = ['tar', '-C', self.prefix, '-cf', filename]
        # convert absolute paths to relative paths to the prefix
        for i, file in enumerate(files):
            if self.prefix in file:
                files[i] = file.replace(self.prefix, '')
                files[i] = files[i].lstrip('/').rstrip('\\')
        if package_prefix:
            # Only transform the files (and not symbolic/hard links)
            tar_cmd += ['--transform', 'flags=r;s|^|{}/|'.format(package_prefix)]
        if self.compress == 'bz2':
            # Use lbzip2 when available for parallel compression
            if shutil.which('lbzip2'):
                tar_cmd += ['--use-compress-program=lbzip2']
            else:
                tar_cmd += ['--bzip2']
        elif self.compress == 'xz':
            tar_cmd += ['--use-compress-program=xz --threads=0']
        try:
            shell.new_call(tar_cmd + files)
        except FatalError:
            os.replace(filename, filename + '.partial')
            raise


class Packager(object):

    def __new__(klass, config, package, store):
        return DistTarball(config, package, store)


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro
    register_packager(Distro.NONE, Packager)
    register_packager(Distro.GENTOO, Packager)
