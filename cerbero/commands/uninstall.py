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

from cerbero.commands import Command, register_command
from cerbero.build.cookbook import CookBook
from cerbero.errors import FatalError
from cerbero.utils import _, N_, ArgparseArgument, shell, messages as m
from cerbero.build.recipe import BuildSteps


class Uninstall(Command):
    doc = N_('Uninstall a single recipe\'s status')
    name = 'uninstall'

    def __init__(self):
        Command.__init__(self,
                         [ArgparseArgument('recipe', nargs='*',
                                           help=_('Name of the recipes to uninstall')),
                          ArgparseArgument('--deps', action='store_true', default=False,
                                           help=_('Uninstall all its dependencies recursively')),
                          ])

    def run(self, config, args):
        cookbook = CookBook(config)
        recipe_names = []
        if args.deps:
            m.message('Uninstalling the following recipes along with all their dependencies: {}'
                      .format(' '.join(args.recipe)))
            for recipe in args.recipe:
                recipe_names += [r.name for r in cookbook.list_recipe_deps(recipe)]
        else:
            m.message('Uninstalling the following recipes without their dependencies: {}'
                      .format(' '.join(args.recipe)))
            recipe_names = args.recipe

        for recipe_name in recipe_names:
            recipe = cookbook.get_recipe(recipe_name)

            if recipe_name not in cookbook.status:
                m.message('Recipe {} is not installed'.format(recipe_name))
                continue

            # As a first step, we attempt using the uninstall target,
            # that may or not be present
            try:
                recipe.uninstall()
            except Exception as ex:
                m.warning('{}: failed running uninstall. This is expected if the recipe '
                          'was installed using fridge: {}'.format(recipe.name, ex))

            # As a fallback, in case the uninstall target does not exist,
            # or in case it misses some of the installed files, remove
            # them manually
            cookbook.recipe_remove_installed_files(recipe_name)
            cookbook.clean_recipe_status(recipe_name)

            # Lastly, remove the build directory
            build_dir = os.path.join(config.sources, recipe.package_name)
            if os.path.isdir(build_dir):
                shutil.rmtree(build_dir)

        m.message('Recipes uninstalled: {}'.format(' '.join(recipe_names)))


register_command(Uninstall)
