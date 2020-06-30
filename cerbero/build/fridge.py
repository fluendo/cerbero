# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2019, Fluendo, S.A.
#  Author: Pablo Marcos Oltra <pmarcos@fluendo.com>, Fluendo, S.A.
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
from ftplib import FTP
import urllib.parse
import asyncio
import aioftp
import logging
import urllib.parse

from cerbero.build.relocatabletar import *
from cerbero.config import Platform
from cerbero.errors import BuildStepError, FatalError, RecipeNotFreezableError, EmptyPackageError, PackageNotFoundError
from cerbero.utils import N_, _, shell, run_until_complete
from cerbero.utils.shell import Ftp
from cerbero.utils import messages as m
from cerbero.packages.disttarball import DistTarball
from cerbero.enums import ArchiveType
from cerbero.packages import PackageType


class BinaryRemote (object):
    """Interface for binary remotes"""

    def fetch_binary(self, package_names, local_dir, remote_dir):
        '''
        Method to be overriden that fetches a binary

        @param package_names: List of packages to fetch
        @type package_names: list
        @param local_dir: Local directory to fetch to
        @type local_dir: str
        @param remote_dir: Remote directory to fetch from where packages exist
        @type remote_dir: str
        '''
        raise NotImplementedError

    def upload_binary(self, package_names, local_dir, remote_dir, env_file):
        '''
        Method to be overriden that uploads a binary

        @param package_names: List of packages to fetch
        @type package_names: list
        @param local_dir: Local directory to fetch to
        @type local_dir: str
        @param remote_dir: Remote directory to fetch from where packages exist
        @type remote_dir: str
        '''
        raise NotImplementedError


class FtpBinaryRemote (BinaryRemote):
    """FtpBinaryRemote is a simple and unsafe implementation"""

    def __init__(self, remote, username='', password=''):
        self.remote = 'ftp://' + remote
        self.username = username if username else 'anonymous'
        self.password = password

    def __str__(self):
        return 'remote \'{}\', username \'{}\', password \'{}\''.format(self.remote, self.username, self.password)

    async def fetch_binary(self, package_names, local_dir, remote_dir):
        remote = urllib.parse.urlparse(self.remote)
        port = 21 if not remote.port else remote.port
        logging.getLogger('aioftp.client').setLevel(logging.CRITICAL)
        async with aioftp.ClientSession(remote.hostname, port, self.username, self.password, socket_timeout=15) as ftp:
            for filename in package_names:
                if filename:
                    local_filename = os.path.join(local_dir, filename)
                    download_needed = True
                    if os.path.isfile(local_filename):
                        local_sha256 = shell.file_sha256(local_filename).hex()
                        remote_sha256_filename = os.path.join(remote.path, remote_dir, filename) + '.sha256'
                        try:
                            await ftp.download(remote_sha256_filename, local_filename + '.sha256', write_into=True)
                            # .sha256 file contains both the sha256 hash and the filename, separated by a whitespace
                            with open(local_filename + '.sha256', 'r') as file:
                                remote_sha256 = file.read().split(' ')[0]
                            if local_sha256 == remote_sha256:
                                download_needed = False
                        except Exception:
                            pass

                    if download_needed:
                        try:
                            remote_file = os.path.join(remote.path, remote_dir, filename)
                            if await ftp.exists(remote_file):
                                await ftp.download(remote_file, local_filename, write_into=True)
                            else:
                                raise PackageNotFoundError(os.path.join(self.remote, remote_dir, filename))
                        except Exception:
                            raise PackageNotFoundError(os.path.join(self.remote, remote_dir, filename))

    def upload_binary(self, package_names, local_dir, remote_dir, env_file):
        ftp = Ftp(self.remote, user=self.username, password=self.password)
        remote_env_file = os.path.join(self.remote, remote_dir, os.path.basename(env_file))
        if not ftp.file_exists(remote_env_file):
            m.message('Uploading environment file to %s' % remote_env_file)
            ftp.upload(env_file, remote_env_file)
        for filename in package_names:
            if filename:
                remote_filename = os.path.join(self.remote, remote_dir, filename)
                local_filename = os.path.join(local_dir, filename)
                local_sha256_filename = local_filename + '.sha256'
                upload_needed = True

                if not os.path.exists(local_sha256_filename):
                    sha256 = shell.file_sha256(local_filename)
                    # .sha256 file contains both the sha256 hash and the
                    # filename, separated by a whitespace
                    with open(local_sha256_filename, 'w') as f:
                        f.write('%s %s' % (sha256.hex(), filename))

                try:
                    tmp_sha256 = tempfile.NamedTemporaryFile()
                    tmp_sha256_filename = tmp_sha256.name
                    ftp.download(remote_filename + '.sha256',
                                 tmp_sha256_filename)
                    with open(local_sha256_filename, 'r') as file:
                        local_sha256 = file.read().split()[0]
                    with open(tmp_sha256_filename, 'r') as file:
                        remote_sha256 = file.read().split()[0]
                    if local_sha256 == remote_sha256:
                        upload_needed = False
                except Exception:
                    pass

                if upload_needed:
                    ftp.upload(local_sha256_filename, remote_filename + '.sha256')
                    ftp.upload(local_filename, remote_filename)
                else:
                    m.action('No need to upload since local and remote SHA256 are the same')
        ftp.close()


class Fridge (object):
    """This fridge packages recipes thar are already built"""

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
        self.env_checksum = None
        shell.DRY_RUN = dry_run
        if not self.config.binaries_local:
            raise FatalError(_('Configuration without binaries local dir'))

    def unfreeze_recipe(self, recipe, build_status_printer, count):
        '''
        Unfreeze the recipe, downloading the package and installing it

        @param recipe: The recipe to unfreeze
        @type recipe: L{cerbero.build.cookbook.Recipe}
        @param count: Current number of step
        @type count: int
        @param total: Total number of step
        @type total: int
        '''
        self._ensure_ready(recipe)
        steps = [self.FETCH_BINARY, self.EXTRACT_BINARY]
        run_until_complete(self._apply_steps(recipe, steps, build_status_printer, count))

    def freeze_recipe(self, recipe, build_status_printer, count):
        '''
        Freeze the recipe, creating a package and uploading it

        @param recipe: The recipe to freeze
        @type recipe: L{cerbero.build.cookbook.Recipe}
        @param count: Current number of step
        @type count: int
        @param total: Total number of step
        @type total: int
        '''
        self._ensure_ready(recipe)
        steps = [self.GEN_BINARY, self.UPLOAD_BINARY]
        run_until_complete(self._apply_steps(recipe, steps, build_status_printer, count))

    async def fetch_recipe(self, recipe, build_status_printer, count):
        '''
        Fetch the recipe

        @param recipe: The recipe to fetch
        @type recipe: L{cerbero.build.cookbook.Recipe}
        @param count: Current number of step
        @type count: int
        @param total: Total number of step
        @type total: int
        '''
        self._ensure_ready(recipe)
        try:
            await self._apply_steps(recipe, [self.FETCH_BINARY], build_status_printer, count)
        except Exception:
            build_status_printer.update_recipe_step(count, recipe.name, 'fetch')
            await recipe.fetch()
            self.cookbook.update_step_status(recipe.name, 'fetch')
        self.cookbook.update_needs_build(recipe.name, True)

    async def fetch_binary(self, recipe):
        self._ensure_ready(recipe)
        await self.binaries_remote.fetch_binary(self._get_package_names(recipe).values(),
                                          self.binaries_local, self.env_checksum)

    def extract_binary(self, recipe):
        self._ensure_ready(recipe)
        package_names = self._get_package_names(recipe)
        # There is a weird bug where the links in the devel package are overwriting the
        # file it's linking instead of just creating the link.
        # For example libmonosgen-2.0.dylib will be extracted creating a link
        # libmonosgen-2.0.dylib -> libmonosgen-2.0.1.dylib and copying
        # libmonosgen-2.0.dylib to libmonosgen-2.0.1.dylib
        # As a workaround we extract first the devel package and finally the runtime
        for filename in package_names.values():
            if filename:
                if self.config.target_platform == Platform.DARWIN:
                    tarclass = RelocatableTarOSX
                else:
                    tarclass = RelocatableTar
                tar = tarclass.open(os.path.join(self.binaries_local,
                                                 filename), 'r:bz2')
                tar.extract_and_relocate(self.config.prefix, self.config.toolchain_prefix)
                tar.close()

    def generate_binary(self, recipe):
        self._ensure_ready(recipe)
        p = self.store.get_package('%s-pkg' % recipe.name)
        tar = DistTarball(self.config, p, self.store)
        p.pre_package()
        files = self.cookbook.recipe_installed_files(recipe.name)
        if not files:
            m.warning('The recipe %s has no installed files. Try running all steps for the recipe from scratch' % recipe.name)
            raise EmptyPackageError(p.name)

        # Update list of installed files to make sure all of the files actually exist
        installed_files = self.cookbook.update_installed_files(recipe.name, files)
        paths = tar.pack_files(self.binaries_local, PackageType.DEVEL, installed_files)
        p.post_package(paths, self.binaries_local)

    def upload_binary(self, recipe):
        self._ensure_ready(recipe)
        packages = self._get_package_names(recipe)
        fetch_packages = []
        for p in packages.values():
            if os.path.exists(os.path.join(self.binaries_local, p)):
                fetch_packages.append(p)
            else:
                m.warning("No package was created for %s" % p)
        self.binaries_remote.upload_binary(fetch_packages, self.binaries_local,
                                           self.env_checksum, self.env_file)

    def _ensure_ready(self, recipe):
        if not recipe.allow_package_creation:
            raise RecipeNotFreezableError(recipe.name)
        if not self.env_checksum:
            self.env_checksum = self.config.get_checksum()[:8]
            self.binaries_local = os.path.join(self.config.binaries_local, self.env_checksum)
            if not self.binaries_remote:
                raise FatalError(_('Configuration without binaries remote'))
            if not os.path.exists(self.binaries_local):
                os.makedirs(self.binaries_local)
            self.env_file = os.path.join(self.binaries_local, 'ENVIRONMENT')
            if not os.path.exists(self.env_file):
                with open(self.env_file, 'w') as f:
                    f.write('%s\n\n%s' % (self.env_checksum, self.config.get_string_for_checksum()))
            m.message('Fridge initialized with environment hash {}'.format(self.env_checksum))

    def _get_package_names(self, recipe):
        ret = dict()
        p = self.store.get_package('%s-pkg' % recipe.name)
        tar = DistTarball(self.config, p, self.store)
        ret[PackageType.DEVEL] = tar.get_name(PackageType.DEVEL)
        return ret

    async def _apply_steps(self, recipe, steps, build_status_printer, count):
        self._ensure_ready(recipe)
        for desc, step in steps:
            build_status_printer.update_recipe_step(count, recipe.name, step)
            # check if the current step needs to be done
            if self.cookbook.step_done(recipe.name, step) and not self.force:
                continue

            # check if the recipe was installed from a frozen one,
            # in which case, we won't generate it again unless force is used
            if step in [self.GEN_BINARY[1], self.UPLOAD_BINARY[1]]:
                if self.cookbook.step_done(recipe.name, self.EXTRACT_BINARY[1]) and not self.force:
                    m.action('No need since a package exists in remote for this recipe')
                    self.cookbook.update_step_status(recipe.name, step)
                    continue

            # call step function
            if not hasattr(self, step):
                raise FatalError(_('Step %s not found for recipe %s') % (step, recipe.name))
            stepfunc = getattr(self, step)
            if not stepfunc:
                raise FatalError(_('Step %s not found for recipe %s') % (step, recipe.name))
            try:
                if asyncio.iscoroutinefunction(stepfunc):
                    await stepfunc(recipe)
                else:
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
