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

import sys
import tempfile
import shutil
import traceback
import asyncio
from subprocess import CalledProcessError
import os
import time

from cerbero.enums import Architecture, Platform, LibraryType
from cerbero.errors import BuildStepError, FatalError, AbortedError, RecipeNotFreezableError
from cerbero.build.recipe import Recipe, BuildSteps
from cerbero.utils import _, N_, shell, run_until_complete
from cerbero.utils.shell import BuildStatusPrinter
from cerbero.utils import messages as m
from cerbero.build.fridge import Fridge
from cerbero.packages.packagesstore import PackagesStore

import inspect

class RecoveryActions(object):
    '''
    Enumeration factory for recovery actions after an error
    '''

    SHELL = N_("Enter the shell")
    RETRY_ALL = N_("Rebuild the recipe from scratch")
    RETRY_STEP = N_("Rebuild starting from the failed step")
    SKIP = N_("Skip recipe")
    ABORT = N_("Abort")

    def __new__(klass):
        return [RecoveryActions.SHELL, RecoveryActions.RETRY_ALL,
                RecoveryActions.RETRY_STEP, RecoveryActions.SKIP,
                RecoveryActions.ABORT]


class Oven (object):
    '''
    This oven cooks recipes with all their ingredients

    @ivar recipes: Recipes to build
    @type: L{cerberos.recipe.recipe}
    @ivar cookbook: Cookbook with the recipes status
    @type: L{cerberos.cookbook.CookBook}
    @ivar force: Force the build of the recipes
    @type: bool
    @ivar no_deps: Ignore dependencies
    @type: bool
    @ivar missing_files: check for files missing in the recipes
    @type missing_files: bool
    @ivar dry_run: don't actually exectute the commands
    @type dry_run: bool
    @ivar deps_only: only build depenencies and not the recipes
    @type deps_only: bool
    '''

    def __init__(self, recipes, cookbook, force=False, no_deps=False,
                 missing_files=False, dry_run=False, deps_only=False):
        if isinstance(recipes, Recipe):
            recipes = [recipes]
        self.recipes = recipes
        self.cookbook = cookbook
        self.force = force
        self.no_deps = no_deps
        self.missing_files = missing_files
        self.config = cookbook.get_config()
        self.interactive = self.config.interactive
        self.deps_only = deps_only
        shell.DRY_RUN = dry_run

    def start_cooking(self, use_binaries=False, upload_binaries=False):
        '''
        Cooks the recipe and all its dependencies
        '''
        recipes = [self.cookbook.get_recipe(x) for x in self.recipes]

        if self.no_deps:
            ordered_recipes = recipes
        else:
            ordered_recipes = []
            for recipe in self.recipes:
                deps = self.cookbook.list_recipe_deps(recipe)
                # remove recipes already scheduled to be built
                deps = [x for x in deps if x not in ordered_recipes]
                ordered_recipes.extend(deps)

        if self.deps_only:
            ordered_recipes = [x for x in ordered_recipes if x not in recipes]

        m.message(_("Building the following recipes: %s") %
                  ' '.join([x.name for x in ordered_recipes]))

        length = len(ordered_recipes)
        fridge = None
        if use_binaries or upload_binaries:
            fridge = Fridge(PackagesStore(self.config, recipes=ordered_recipes, cookbook=self.cookbook),
                            force=self.force, dry_run=shell.DRY_RUN)

        steps = [step[1] for step in recipes[0].steps]
        if upload_binaries:
            steps += [Fridge.GEN_BINARY, Fridge.UPLOAD_BINARY]
        self._build_status_printer = BuildStatusPrinter(steps, False) #self.interactive)
        self._build_status_printer.total = length
        self._static_libraries_built = []
        i = 1
        for recipe in ordered_recipes:
            try:
                self._cook_recipe(recipe, i, fridge, use_binaries, upload_binaries)
            except BuildStepError as be:
                if not self.interactive:
                    raise be
                msg = be.msg
                msg += _("Select an action to proceed:")
                action = shell.prompt_multiple(msg, RecoveryActions())
                if action == RecoveryActions.SHELL:
                    shell.enter_build_environment(self.config.target_platform,
                            be.arch, recipe.get_for_arch (be.arch, 'build_dir'))
                    raise be
                elif action == RecoveryActions.RETRY_ALL:
                    shutil.rmtree(recipe.get_for_arch (be.arch, 'build_dir'))
                    self.cookbook.reset_recipe_status(recipe.name)
                    self._cook_recipe(recipe, i, fridge, use_binaries, upload_binaries)
                elif action == RecoveryActions.RETRY_STEP:
                    self._cook_recipe(recipe, i, fridge, use_binaries, upload_binaries)
                elif action == RecoveryActions.SKIP:
                    i += 1
                    continue
                elif action == RecoveryActions.ABORT:
                    raise AbortedError()
            i += 1

    def _cook_recipe(self, recipe, count, fridge=None, use_binaries=False, upload_binaries=False):
        # A Recipe depending on a static library that has been rebuilt
        # also needs to be rebuilt to pick up the latest build.
        if recipe.library_type != LibraryType.STATIC:
            if len(set(self._static_libraries_built) & set(recipe.deps)) != 0:
                self.cookbook.reset_recipe_status(recipe.name)
        if not self.cookbook.recipe_needs_build(recipe.name) and \
                not self.force:
            if upload_binaries:
                try:
                    fridge.freeze_recipe(recipe, self._build_status_printer, count)
                except RecipeNotFreezableError:
                    m.message('Recipe {} does not allow being frozen (allow_package_creation = False)'.format(recipe.name))
                    pass

            return

        # Create a temp file that will be used to find newer files
        tmp = tempfile.NamedTemporaryFile()

        # the modification time resolution depends on the filesystem, where
        # Windows and macOS have a 1 sec while Linux has millisecond. Hence, we
        # sleep enough to make sure the files from previous recipes are not
        # taken
        if self.config.platform != Platform.LINUX:
            time.sleep(1.5)

        if use_binaries:
            try:
                fridge.unfreeze_recipe(recipe, self._build_status_printer, count)
                self._update_installed_files(recipe, tmp)
                return
            except Exception:
                return self._cook_recipe(recipe, count, fridge, False, upload_binaries)

        recipe.force = self.force
        for desc, step in recipe.steps:
            self._build_status_printer.update_recipe_step(count, recipe.name, step)
            # check if the current step needs to be done
            if self.cookbook.step_done(recipe.name, step) and not self.force:
                m.action(_("Step done"))
                continue
            try:
                # call step function
                stepfunc = getattr(recipe, step)
                if not stepfunc:
                    raise FatalError(_('Step %s not found') % step)

                # We need to update the installed files before the relocate_osx_binaries step
                # because it needs to know the list of files that needs to relocate
                # WARNING: the method to automatically detect files will only work
                # when installing recipes not concurrently
                if step == BuildSteps.RELOCATE_OSX_LIBRARIES[1]:
                    self._update_installed_files(recipe, tmp)

                if asyncio.iscoroutinefunction(stepfunc):
                    run_until_complete(stepfunc())
                else:
                    stepfunc()
                # update status successfully
                self.cookbook.update_step_status(recipe.name, step)

            except FatalError as e:
                exc_traceback = sys.exc_info()[2]
                trace = ''
                # Don't print trace if the FatalError is merely that the
                # subprocess exited with a non-zero status. The traceback
                # is just confusing and useless in that case.
                if not isinstance(e.__context__, CalledProcessError):
                    tb = traceback.extract_tb(exc_traceback)[-1]
                    if tb.filename.endswith('.recipe'):
                        # Print the recipe and line number of the exception
                        # if it starts in a recipe
                        trace += 'Exception at {}:{}\n'.format(tb.filename, tb.lineno)
                    trace += e.args[0] + '\n'
                self._handle_build_step_error(recipe, step, trace, e.arch)
            except Exception:
                raise BuildStepError(recipe, step, traceback.format_exc())
        self.cookbook.update_build_status(recipe.name, recipe.built_version())

        # In case the recipe has been fully installed now, update the internal
        # list of installed files for this recipe
        # WARNING: the method to automatically detect files will only work
        # when installing recipes not concurrently
        if set([BuildSteps.INSTALL, BuildSteps.POST_INSTALL]).intersection(set(recipe.steps)):
            self._update_installed_files(recipe, tmp)

        if recipe.library_type == LibraryType.STATIC:
            self._static_libraries_built.append(recipe.name)

        if self.missing_files:
            self._print_missing_files(recipe, tmp)

        if upload_binaries:
            try:
                fridge.freeze_recipe(recipe, self._build_status_printer, count)
            except RecipeNotFreezableError:
                m.message('Recipe {} does not allow being frozen (allow_package_creation = False)'.format(recipe.name))
                pass

    def _update_installed_files(self, recipe, tmp):
        installed_files = list(set(shell.find_newer_files(recipe.config.prefix,
                                                          tmp.name, include_link=False)))
        if not installed_files:
            m.warning('No installed files found for recipe %s' % recipe.name)
        self.cookbook.update_installed_files(recipe.name, installed_files)

    def _handle_build_step_error(self, recipe, step, trace, arch):
        if step in [BuildSteps.FETCH, BuildSteps.EXTRACT]:
            # if any of the source steps failed, wipe the directory and reset
            # the recipe status to start from scratch next time
            shutil.rmtree(recipe.build_dir)
            self.cookbook.reset_recipe_status(recipe.name)
        raise BuildStepError(recipe, step, trace=trace, arch=arch)

    def _print_missing_files(self, recipe, tmp):
        recipe_files = set(recipe.files_list())
        installed_files = list(set(shell.find_newer_files(recipe.config.prefix,
                                                          tmp.name, include_link=False)))
        not_in_recipe = list(installed_files - recipe_files)
        not_installed = list(recipe_files - installed_files)

        if len(not_in_recipe) != 0:
            m.message(_("The following files were installed, but are not "
                        "listed in the recipe:"))
            m.message('\n'.join(sorted(not_in_recipe)))

        if len(not_installed) != 0:
            m.message(_("The following files are listed in the recipe, but "
                        "were not installed:"))
            m.message('\n'.join(sorted(not_installed)))
