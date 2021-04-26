# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2021, Fluendo, S.A.
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


from cerbero.commands import Command, register_command
from cerbero.build.cookbook import CookBook
from cerbero.utils import _, N_, ArgparseArgument, run_until_complete
from cerbero.build.fridge import Fridge
from cerbero.packages.packagesstore import PackagesStore


class CheckBinariesRemote(Command):
    doc = N_('Checks if a binary remote package exists. This is useful to check whether the binary already '
             'exists in the remote to avoid building and testing again the same recipes')
    name = 'check-binaries-remote'

    def __init__(self):
        Command.__init__(self,
            [ArgparseArgument('recipes', nargs='*',
                             help=_('name of the recipe to check')),
            ])

    def run(self, config, args):
        cookbook = CookBook(config)
        recipes = args.recipes
        fridge = Fridge(PackagesStore(cookbook.get_config(), recipes=recipes, cookbook=cookbook))

        tasks = []
        for recipe_name in args.recipes:
            recipe = cookbook.get_recipe(recipe_name)
            tasks.append(fridge.check_remote_package_exists(recipe))

        run_until_complete(tasks)


register_command(CheckBinariesRemote)
