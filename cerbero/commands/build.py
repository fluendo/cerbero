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


#from cerbero.oven import Oven
from cerbero.commands import Command, register_command
from cerbero.errors import BuildStepError
from cerbero.build.cookbook import CookBook
from cerbero.packages.packagesstore import PackagesStore
from cerbero.build.fridge import Fridge
from cerbero.build.oven import Oven
from cerbero.utils import _, N_, ArgparseArgument


class Build(Command):
    doc = N_('Build a recipe')
    name = 'build'

    def __init__(self, force=None, no_deps=None):
            args = [
                ArgparseArgument('recipe', nargs='*',
                    help=_('name of the recipe to build')),
                ArgparseArgument('--missing-files', action='store_true',
                    default=False,
                    help=_('prints a list of files installed that are '
                           'listed in the recipe')),
                ArgparseArgument('--dry-run', action='store_true',
                    default=False,
                    help=_('only print commands instead of running them ')),
                ArgparseArgument('--use-binaries', action='store_true',
                    default=False,
                    help=_('use binaries from the repo before building')),
                ArgparseArgument('--upload-binaries', action='store_true',
                    default=False,
                    help=_('after a recipe is built upload the corresponding binary package')),
                ArgparseArgument('--build-missing', action='store_true',
                    default=False,
                    help=_('in case a binary package is missing try to build it'))]
            if force is None:
                args.append(
                    ArgparseArgument('--force', action='store_true',
                        default=False,
                        help=_('force the build of the recipe ingoring '
                                    'its cached state')))
            if no_deps is None:
                args.append(
                    ArgparseArgument('--no-deps', action='store_true',
                        default=False,
                        help=_('do not build dependencies')))

            self.force = force
            self.no_deps = no_deps
            Command.__init__(self, args)

    def run(self, config, args):
        if self.force is None:
            self.force = args.force
        if self.no_deps is None:
            self.no_deps = args.no_deps
        self.runargs(config, args.recipe, args.missing_files, self.force,
                     self.no_deps, dry_run=args.dry_run,
                     use_binaries=args.use_binaries,
                     upload_binaries=args.upload_binaries,
                     build_missing=args.build_missing)

    def runargs(self, config, recipes, missing_files=False, force=False,
                no_deps=False, store=None, dry_run=False, use_binaries=False,
                upload_binaries=False, build_missing=False):
        if not store:
            store = PackagesStore(config)
        cookbook = store.cookbook

        oven = Oven(cookbook, force=self.force, missing_files=missing_files,
                    dry_run=dry_run)

        if isinstance(recipes, str):
            recipes = [recipes]

        if no_deps:
            ordered_recipes = recipes
        else:
            ordered_recipes = cookbook.list_recipes_deps(recipes)

        if use_binaries or upload_binaries:
            fridge = Fridge(store, force=self.force, dry_run=dry_run)
            i = 1
            for recipe in ordered_recipes:
                if use_binaries:
                    try:
                        fridge.unfreeze_recipe(recipe, i, len(ordered_recipes))
                    except BuildStepError as e:
                        if build_missing:
                            oven.cook_recipe(recipe, i, len(ordered_recipes))
                            if upload_binaries:
                                fridge.freeze_recipe(recipe, i, len(ordered_recipes))
                        else:
                            raise e
                else:
                    oven.cook_recipe(recipe, i, len(ordered_recipes))
                    if upload_binaries:
                       fridge.freeze_recipe(recipe, i, len(ordered_recipes))
                i += 1
        else:
            oven.start_cooking(ordered_recipes)


class BuildOne(Build):
    doc = N_('Build or rebuild a single recipe without its dependencies')
    name = 'buildone'

    def __init__(self):
        Build.__init__(self, True, True)


register_command(BuildOne)
register_command(Build)
