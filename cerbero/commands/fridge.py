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

from cerbero.commands import Command, register_command
from cerbero.build.fridge import Fridge
from cerbero.packages.packagesstore import PackagesStore
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m


class FridgeCommand(Command):
    doc = N_('Generate binaries from the recipes built')
    name = 'fridge'

    def __init__(self):
        args = [
            ArgparseArgument('recipes', nargs='*',
                             help=_('name of the recipes to generate binaries')),
            ArgparseArgument('--dry-run', action='store_true',
                             default=False,
                             help=_('only print commands instead of running them ')),
            ArgparseArgument('-f', '--force', action='store_true',
                             default=False, help=_('Force the creation of the binary package')),
        ]
        Command.__init__(self, args)

    def run(self, config, args):
        store = PackagesStore(config)
        cookbook = store.cookbook
        recipes = args.recipes
        if not recipes:
            recipes = [recipe.name for recipe in cookbook.get_recipes_list()]
        fridge = Fridge(store, args.force, args.dry_run)

        recipes_to_generate = []
        for recipe_name in recipes:
            bv = cookbook.recipe_built_version(recipe_name)
            recipe = cookbook.get_recipe(recipe_name)
            cv = recipe.built_version()
            if bv == cv:
                recipes_to_generate.append(recipe)

        if recipes_to_generate:
            m.message('Generating binaries for the following recipes: %s' %
                      ' '.join([x.name for x in recipes_to_generate]))
        else:
            m.message('No recipes to generate binaries. The built version do not match the one on the recipe')

        # finally freeze them
        i = 1
        for recipe in recipes_to_generate:
            try:
                fridge.freeze_recipe(recipe, i, len(recipes_to_generate))
            except:
                pass
            i += 1


register_command(FridgeCommand)
