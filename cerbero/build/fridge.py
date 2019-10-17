# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2016 Fluendo S.A. <support@fluendo.com>
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
import traceback
import tempfile

from cerbero.build.relocatabletar import *
from cerbero.config import Platform
from cerbero.errors import BuildStepError, FatalError, RecipeNotFreezableError, EmptyPackageError
from cerbero.utils import N_, _, shell
from cerbero.utils import messages as m
from cerbero.utils.shell import upload_curl, download, curl_file_exists
from cerbero.packages.disttarball import DistTarball
from cerbero.enums import ArchiveType
from cerbero.packages import PackageType


class BinaryRemote (object):
    def fetch_binary(self, package_names, local_dir, remote_dir):
        raise NotImplementedError

    def upload_binary(self, package_names, local_dir, remote_dir, env_file):
        raise NotImplementedError


class FtpBinaryRemote (BinaryRemote):
    '''
    FtpBinaryRemote is a simple and unsecure implementation
    '''

    def __init__(self, remote, username='', password=''):
        self.remote = 'ftp://' + remote
        self.username = username
        self.password = password

    def fetch_binary(self, package_names, local_dir, remote_dir):
        for filename in package_names.values():
            if filename:
                local_filename = os.path.join(local_dir, filename)
                download_needed = True
                if os.path.isfile(local_filename):
                    local_sha256 = shell.file_sha256(local_filename).hex()
                    remote_sha256_filename = os.path.join(self.remote, remote_dir, filename) + '.sha256'
                    download(remote_sha256_filename,
                             local_filename + '.sha256',
                             overwrite=True,
                             user=self.username,
                             password=self.password)
                    # .sha256 file contains both the sha256 hash and the filename, separated by a whitespace
                    with open(local_filename + '.sha256', 'r') as file:
                        remote_sha256 = file.read().split(' ')[0]
                    if local_sha256 == remote_sha256:
                        download_needed = False

                if download_needed:
                    download(os.path.join(self.remote, remote_dir, filename),
                             local_filename,
                             overwrite=True,
                             user=self.username,
                             password=self.password)

    def upload_binary(self, package_names, local_dir, remote_dir, env_file):
        remote_env_file = os.path.join(self.remote, remote_dir, os.path.basename(env_file))
        if not curl_file_exists(remote_env_file, user=self.username, password=self.password):
            m.message('Uploading environment file to %s' % remote_env_file)
            upload_curl(env_file, remote_env_file, user=self.username, password=self.password)
        for filename in package_names.values():
            if filename:
                remote_filename = os.path.join(self.remote, remote_dir, filename)
                local_filename = os.path.join(local_dir, filename)
                local_sha256_filename = local_filename + '.sha256'
                upload_needed = True

                if not os.path.exists(local_sha256_filename):
                    sha256 = shell.file_sha256(local_filename)
                    # .sha256 file contains both the sha256 hash and the filename, separated by a whitespace
                    with open(local_sha256_filename, 'w') as f:
                        f.write('%s %s' % (sha256.hex(), filename))

                try:
                    tmp_sha256 = tempfile.NamedTemporaryFile()
                    tmp_sha256_filename = tmp_sha256.name
                    download(remote_filename + '.sha256',
                             tmp_sha256_filename,
                             overwrite=True,
                             user=self.username,
                             password=self.password)
                    with open(local_sha256_filename, 'r') as file:
                        local_sha256 = file.read().split(' ')[0]
                    with open(tmp_sha256_filename, 'r') as file:
                        remote_sha256 = file.read().split(' ')[0]
                    if local_sha256 == remote_sha256:
                        upload_needed = False
                    tmp_sha256.close()
                except Exception:
                    pass

                if upload_needed:
                    upload_curl(local_filename,
                                remote_filename,
                                user=self.username,
                                password=self.password)
                    upload_curl(local_sha256_filename,
                                remote_filename + '.sha256',
                                user=self.username,
                                password=self.password)


class Fridge (object):
    '''
    This fridge unfreezes or freezes a cook from a recipe
    '''

    # Freeze/Unfreeze steps
    FETCH_BINARY = (N_('Fetch Binary'), 'fetch_binary')
    EXTRACT_BINARY = (N_('Extract Binary'), 'extract_binary')
    GEN_BINARY = (N_('Generate Binary'), 'generate_binary')
    UPLOAD_BINARY = (N_('Upload Binary'), 'upload_binary')

    def __init__(self, store, force=False, dry_run=False):
        self.store = store
        self.cookbook = store.cookbook
        self.config = self.cookbook.get_config()
        self.force = force
        self.binaries_remote = self.config.binaries_remote
        shell.DRY_RUN = dry_run
        if not self.config.binaries_local:
            raise FatalError(_('Configuration without binaries local dir'))
        self.env_checksum = self.config.get_checksum()
        self.binaries_local = os.path.join(self.config.binaries_local, self.env_checksum)
        if not self.binaries_remote:
            raise FatalError(_('Configuration without binaries remote'))
        if not os.path.exists(self.binaries_local):
            os.makedirs(self.binaries_local)
        self.env_file = os.path.join(self.binaries_local, 'ENVIRONMENT')
        if not os.path.exists(self.env_file):
            with open(self.env_file, 'w') as f:
                f.write(self.config.get_string_for_checksum())

    def unfreeze_recipe(self, recipe, count, total):
        if not recipe.allow_package_creation:
            raise RecipeNotFreezableError(recipe.name)
        steps = [self.FETCH_BINARY, self.EXTRACT_BINARY]
        self._apply_steps(recipe, steps, count, total)

    def freeze_recipe(self, recipe, count, total):
        if not recipe.allow_package_creation:
            raise RecipeNotFreezableError(recipe.name)
        steps = [self.GEN_BINARY, self.UPLOAD_BINARY]
        self._apply_steps(recipe, steps, count, total)

    def fetch_binary(self, recipe):
        self.binaries_remote.fetch_binary(self._get_package_names(recipe),
                                          self.binaries_local, self.env_checksum)

    def extract_binary(self, recipe):
        package_names = self._get_package_names(recipe)
        # There is a weird bug where the links in the devel package are overwriting the
        # file it's linking instead of just creating the link.
        # For example libmonosgen-2.0.dylib will be extracted creating a link
        # libmonosgen-2.0.dylib -> libmonosgen-2.0.1.dylib and copying
        # libmonosgen-2.0.dylib to libmonosgen-2.0.1.dylib
        # As a workaround we extract first the devel package and finally the runtime
        for filename in [package_names[PackageType.DEVEL], package_names[PackageType.RUNTIME]]:
            if filename:
                if self.config.target_platform == Platform.DARWIN:
                    tarclass = RelocatableTarOSX
                else:
                    tarclass = RelocatableTar
                tar = tarclass.open(os.path.join(self.binaries_local,
                                                 filename), 'r:bz2')
                tar.extract_and_relocate(self.config.prefix)
                tar.close()

    def generate_binary(self, recipe):
        p = self.store.get_package('%s-pkg' % recipe.name)
        tar = DistTarball(self.config, p, self.store)
        p.pre_package()
        paths = tar.pack(self.binaries_local, devel=True, force=True, force_empty=False,
                         relocatable=True)
        p.post_package(paths, self.binaries_local)

    def upload_binary(self, recipe):
        self.binaries_remote.upload_binary(self._get_package_names(recipe),
                                           self.binaries_local, self.env_checksum, self.env_file)

    def _get_package_names(self, recipe):
        ret = {PackageType.RUNTIME: None, PackageType.DEVEL: None}
        p = self.store.get_package('%s-pkg' % recipe.name)
        tar = DistTarball(self.config, p, self.store)
        # use the package (not the packager) to avoid the warnings
        ret[PackageType.RUNTIME] = tar.get_name(PackageType.RUNTIME)
        ret[PackageType.DEVEL] = tar.get_name(PackageType.DEVEL)
        return ret

    def _apply_steps(self, recipe, steps, count, total):
        for desc, step in steps:
            m.build_step(count, total, recipe.name, step)
            # check if the current step needs to be done
            if self.cookbook.step_done(recipe.name, step) and not self.force:
                m.action(_("Step done"))
                continue

            # call step function
            stepfunc = getattr(self, step)
            if not stepfunc:
                raise FatalError(_('Step %s not found') % step)
            try:
                stepfunc(recipe)
                # update status successfully
                self.cookbook.update_step_status(recipe.name, step)
            except Exception as e:
                m.warning(str(e))
                raise BuildStepError(recipe, step, traceback.format_exc())
        # Update the recipe status
        p = self.store.get_package('%s-pkg' % recipe.name)
        v = p.version.rsplit('-')[0]
        self.cookbook.update_build_status(recipe.name, v)
