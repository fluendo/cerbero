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


from cerbero.commands import Command, register_command
from cerbero.build.cookbook import CookBook
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m


class Cache(Command):
    doc = N_('Inspect and modify the local cache')
    name = 'cache'

    def __init__(self):
        Command.__init__(self,
                         [
                             ArgparseArgument('recipe', nargs='*',
                                              help=_('Recipe to work with')),
                             ArgparseArgument('--bootstrap', action='store_true', default=False,
                                              help=_('Use bootstrap\'s cache file')),
                             ArgparseArgument('--steps', nargs='*',
                                              help=_('Modify steps')),
                             ArgparseArgument('--needs_build',
                                              help=_('Modify needs_build')),
                             ArgparseArgument('--mtime',
                                              help=_('Modify mtime')),
                             ArgparseArgument('--file_path',
                                              help=_('Modify file_path')),
                             ArgparseArgument('--built_version',
                                              help=_('Modify built_version')),
                             ArgparseArgument('--file_hash',
                                              help=_('Modify file_hash')),
                             ArgparseArgument('--touch', action='store_true', default=False,
                                              help=_('Touch recipe modifying its mtime')),
                             ArgparseArgument('--installed_files', nargs='*',
                                              help=_('Modify file_hash')),
                         ])

    def run(self, config, args):
        if args.bootstrap:
            config.cache_file = config.build_tools_cache
        cookbook = CookBook(config)
        is_modifying = args.steps or args.needs_build or args.mtime or args.file_path \
            or args.built_version or args.file_hash or args.touch or args.installed_files

        global_status = cookbook.get_status()
        recipes = args.recipe or global_status.keys()
        if is_modifying and len(recipes) > 1:
            m.error('Only one recipe can be modified at a time')
            return

        m.message('%s cache values for recipes: %s' %
                  ('Showing' if not is_modifying else 'Modifying', ', '.join(recipes)))

        for recipe in recipes:
            if recipe not in global_status.keys():
                m.error('Recipe %s not in cookbook' % recipe)
                continue
            status = global_status[recipe]
            print('[%s]' % recipe)
            if is_modifying:
                print('Before')
            print('%s\n' % status)
            if is_modifying:
                if args.steps:
                    status.steps = args.steps
                if args.needs_build:
                    status.needs_build = True if args.needs_build.lower() == 'true' else False
                if args.file_path:
                    status.file_path = args.file_path
                if args.built_version:
                    status.built_version = args.built_version
                if args.file_hash:
                    status.file_hash = args.file_hash
                if args.touch:
                    status.touch()
                if args.installed_files:
                    status.installed_files = args.installed_files
                if args.mtime:
                    status.mtime = float(args.mtime)
                cookbook.save()
                print('After\n%s\n' % status)


register_command(Cache)
