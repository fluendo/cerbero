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
import time

from cerbero.enums import Platform, LibraryType
from cerbero.errors import BuildStepError, FatalError, AbortedError
from cerbero.build.recipe import Recipe, BuildSteps
from cerbero.utils import _, N_, shell, run_until_complete
from cerbero.utils.shell import BuildStatusPrinter
from cerbero.utils import messages as m
from cerbero.build.fridge import Fridge
from cerbero.packages.packagesstore import PackagesStore


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

        # Filter out all those recipes that are either already built or those
        # that don't need to be uploaded to fridge because:
        # 1. Don't allow creating a package
        # 2. Already run the extract_binary step
        # 3. Have already uploaded the binary to fridge
        filtered_ordered_recipes = [x for x in ordered_recipes if self.cookbook.recipe_needs_build(x.name) or \
                            (upload_binaries and x.allow_package_creation and not self.cookbook.step_done(x.name, Fridge.EXTRACT_BINARY[1]) \
                            and not self.cookbook.step_done(x.name, Fridge.UPLOAD_BINARY[1]))]

        m.message(_("Building the following recipes: %s") %
                  ' '.join([x.name for x in filtered_ordered_recipes]))

        recipes_built = [x.name for x in set(ordered_recipes) - set(filtered_ordered_recipes)]
        if recipes_built:
            m.message('Related recipes already built: {}'.format(' '.join(recipes_built)))

        ordered_recipes = filtered_ordered_recipes
        length = len(ordered_recipes)
        fridge = None
        if use_binaries or upload_binaries:
            fridge = Fridge(PackagesStore(self.config, recipes=ordered_recipes, cookbook=self.cookbook),
                            force=self.force, dry_run=shell.DRY_RUN)

        self._build_status_printer = BuildStatusPrinter()
        self._build_status_printer.total = length
        self._static_libraries_built = []
        i = 1
        for recipe in ordered_recipes:
            try:
                if recipe.allow_package_creation:
                    recipe.add_fridge_steps(self.force, use_binaries, upload_binaries)
                else:
                    m.message('Recipe {} does not allow being frozen (allow_package_creation = False)'.format(recipe.name))
                self._cook_recipe(recipe, i, fridge)
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
                    self._cook_recipe(recipe, i, fridge)
                elif action == RecoveryActions.RETRY_STEP:
                    self._cook_recipe(recipe, i, fridge)
                elif action == RecoveryActions.SKIP:
                    i += 1
                    continue
                elif action == RecoveryActions.ABORT:
                    raise AbortedError()
            i += 1

        m.message('[({}/{} @ 100%) All recipes built]'.format(i - 1, i - 1))

    def _cook_recipe(self, recipe, count, fridge=None):
        # A Recipe depending on a static library that has been rebuilt
        # also needs to be rebuilt to pick up the latest build.
        if recipe.library_type != LibraryType.STATIC:
            if len(set(self._static_libraries_built) & set(recipe.deps)) != 0:
                self.cookbook.reset_recipe_status(recipe.name)

        # Create a temp file that will be used to find newer files
        tmp = tempfile.NamedTemporaryFile()

        # the modification time resolution depends on the filesystem, where
        # Windows and macOS have a 1 sec while Linux has millisecond. Hence, we
        # sleep enough to make sure the files from previous recipes are not
        # taken
        if self.config.platform != Platform.LINUX:
            time.sleep(1.5)

        recipe.force = self.force
        steps_run = []
        for desc, step in recipe.steps:
            self._build_status_printer.update_recipe_step(count, recipe, step)
            # check if the current step needs to be done
            if self.cookbook.step_done(recipe.name, step) and not self.force:
                m.action(_("Step done"))
                steps_run.append(step)
                continue

            # check if the recipe was installed from a frozen one,
            # in which case, we won't generate it again unless force is used
            if step in [Fridge.GEN_BINARY[1], Fridge.UPLOAD_BINARY[1]]:
                if self.cookbook.step_done(recipe.name, Fridge.EXTRACT_BINARY[1]) and not self.force:
                    m.action('No need since a package exists in remote for this recipe')
                    self.cookbook.update_step_status(recipe.name, step)
                    steps_run.append(step)
                    continue

            try:
                # We need to update the installed files before the gen_binary
                # and relocate_osx_binaries steps because it needs to know the
                # list of files to packare or the ones that need to be
                # relocated
                # WARNING: the method to automatically detect files will only
                # work when installing recipes not concurrently
                if self.cookbook.recipe_needs_build(recipe.name) and \
                    step in [BuildSteps.RELOCATE_OSX_LIBRARIES[1], Fridge.GEN_BINARY[1]]:
                    self._update_installed_files(recipe, tmp)

                def _run_step(stepfunc, *args):
                    if asyncio.iscoroutinefunction(stepfunc):
                        run_until_complete(stepfunc(*args))
                    else:
                        stepfunc(*args)

                # call step function
                if hasattr(recipe, step):
                    stepfunc = getattr(recipe, step)
                    if not stepfunc:
                        raise FatalError(_('Step %s not found') % step)
                    _run_step(stepfunc)
                else:
                    # Fridge-related steps are not within the recipe, but within
                    # the fridge class. This is done this way to have an isolated
                    # fridge environment. Thus, the fridge steps need to receive
                    # the recipe as an argument.
                    stepfunc = getattr(fridge, step)
                    _run_step(stepfunc, recipe)

                # update status successfully
                self.cookbook.update_step_status(recipe.name, step)
                steps_run.append(step)
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
            except Exception as e:
                if step in [Fridge.FETCH_BINARY[1], Fridge.EXTRACT_BINARY[1]]:
                    m.warning(e)

                    # In case of any error unfreezing the recipe, ensure we clean
                    # whatever files might have been extracted. Also, reset the status
                    # so that the fallback build is done from the beginning since the
                    # current status is inconsistent
                    self._update_installed_files(recipe, tmp)
                    self.cookbook.recipe_remove_installed_files(recipe.name)
                    self.cookbook.reset_recipe_status(recipe.name)
                    recipe.remove_fridge_steps()
                    self._cook_recipe(recipe, count, fridge)
                    return
                raise BuildStepError(recipe, step, traceback.format_exc())
        self.cookbook.update_build_status(recipe.name, recipe.built_version())

        # In case the recipe has been fully installed now, update the internal
        # list of installed files for this recipe
        # WARNING: the method to automatically detect files will only work
        # when installing recipes not concurrently
        if len(recipe.steps) == len(steps_run):
            self._update_installed_files(recipe, tmp)

        if recipe.library_type == LibraryType.STATIC:
            self._static_libraries_built.append(recipe.name)

        if self.missing_files:
            self._print_missing_files(recipe, tmp)

    def _update_installed_files(self, recipe, tmp):
        installed_files = list(set(shell.find_newer_files(recipe.config.prefix,
                                                          tmp.name, include_link=False)))
        if not installed_files:
            m.warning('No installed files found for recipe \'%s\'' % recipe.name)
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
