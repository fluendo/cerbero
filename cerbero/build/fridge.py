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
import tarfile
import tempfile
import shutil

from cerbero.errors import BuildStepError, FatalError, RecipeNotFreezableError
from cerbero.utils import N_, _, shell
from cerbero.utils import messages as m
from cerbero.utils.shell import upload_curl, download_curl
from cerbero.packages.distarchive import DistArchive
from cerbero.enums import ArchiveType
from cerbero.packages import PackageType

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
        shell.DRY_RUN = dry_run
        if not self.config.binaries:
           raise FatalError(_('Configuration without binaries path'))
        self.binaries = os.path.join(self.config.binaries, self.config.get_md5())
        if not self.config.binary_repo:
           raise FatalError(_('Configuration without binary repo'))
        self.binary_repo = os.path.join(self.config.binary_repo, self.config.get_md5())
        m.message('Using config MD5: %s' % self.config.get_md5())
        if not os.path.exists(self.binaries):
            os.makedirs(self.binaries)

    def unfreeze_recipe(self, recipe_name, count, total):
        recipe = self.cookbook.get_recipe(recipe_name)
        if not recipe.allow_package_creation:
            raise RecipeNotFreezableError(recipe_name)
        steps = [self.FETCH_BINARY, self.EXTRACT_BINARY]
        self._apply_steps(recipe, steps, count, total)

    def freeze_recipe(self, recipe_name, count, total):
        recipe = self.cookbook.get_recipe(recipe_name)
        if not recipe.allow_package_creation:
            raise RecipeNotFreezableError(recipe_name)
        steps = [self.GEN_BINARY, self.UPLOAD_BINARY]
        self._apply_steps(recipe, steps, count, total)

    def fetch_binary(self, recipe):
        packages_names = self._get_packages_names(recipe)
        # TODO we need to fetch the ${filename}.md5 file first
        # compare the md5 with the current md5 and then download
        # or not
        for filename in packages_names.itervalues():
            if filename:
                download_curl(os.path.join(self.binary_repo, filename),
                            os.path.join(self.binaries, filename),
                            user=self.config.binary_repo_username,
                            password=self.config.binary_repo_password,
                            overwrite=True)

    def extract_binary(self, recipe):
        packages_names = self._get_packages_names(recipe)
        for filename in packages_names.itervalues():
            if filename:
                tar = tarfile.open(os.path.join(self.binaries,
                                   filename), 'r:bz2')
                tar.extractall(self.config.prefix)
                for member in tar.getmembers():
                    # Simple sed for .la and .pc files
                    if os.path.splitext(member.name)[1] in ['.la', '.pc']:
                        shell.replace(os.path.join(self.config.prefix, member.name),
                            {"CERBERO_PREFIX": self.config.prefix})
                tar.close()

    def generate_binary(self, recipe):
        p = self.store.get_package('%s-pkg' % recipe.name)
        tar = DistArchive(self.config, p, self.store, ArchiveType.TARBALL)
        p.pre_package()
        paths = tar.pack(self.binaries, devel=True, force=True, force_empty=True, relocatable=True)
        p.post_package(paths)

    def upload_binary(self, recipe):
        packages_names = self._get_packages_names(recipe)
        # TODO we need to upload the .md5 files too for a smart cache system
        for filename in packages_names.itervalues():
            if filename:
                upload_curl(os.path.join(self.binaries, filename),
                            os.path.join(self.binary_repo, filename),
                            user=self.config.binary_repo_username,
                            password=self.config.binary_repo_password)

    def _get_packages_names(self, recipe):
        ret = {PackageType.RUNTIME: None, PackageType.DEVEL: None}
        p = self.store.get_package('%s-pkg' % recipe.name)
        tar = DistArchive(self.config, p, self.store, ArchiveType.TARBALL)
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
