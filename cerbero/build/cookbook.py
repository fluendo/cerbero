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

from collections import defaultdict
import os
import pickle
import imp
import traceback
import shutil

from cerbero.config import CONFIG_DIR, Platform, Architecture, Distro,\
    DistroVersion, License, LibraryType
from cerbero.build.build import BuildType
from cerbero.build.source import SourceType
from cerbero.errors import FatalError, RecipeNotFoundError, InvalidRecipeError
from cerbero.utils import _, shell, parse_file, run_until_complete
from cerbero.utils import messages as m
from cerbero.utils.manifest import Manifest
from cerbero.build import recipe as crecipe


COOKBOOK_NAME = 'cookbook'
COOKBOOK_FILE = os.path.join(CONFIG_DIR, COOKBOOK_NAME)


class RecipeStatus (object):
    '''
    Stores the current build status of a L{cerbero.recipe.Recipe}

    @ivar steps: list of steps currently done
    @type steps: list
    @ivar needs_build: whether the recipe needs to be build or not
                       True when all steps where successful
    @type needs_build: bool
    @ivar filepath: recipe's file path
    @type filepath: str
    @ivar built_version: string with the last version built
    @type built_version: str
    @ivar file_hash: hash of the file with the recipe description
    @type file_hash: str
    @ivar installed_files: installed files
    @rtpe installed_files: list
    '''

    def __init__(self, filepath, steps=[], needs_build=True,
                 built_version='', file_hash='',
                 installed_files=[]):
        self.steps = steps
        self.needs_build = needs_build
        self.filepath = filepath
        self.built_version = built_version
        self.file_hash = file_hash
        self.installed_files = installed_files

    def __repr__(self):
        return "steps: %r, needs_build: %r, filepath: %r, built_version: %r, file_hash: %r\ninstalled_files: %r" % \
            (self.steps, self.needs_build, self.filepath, self.built_version, self.file_hash,
            self.installed_files)


class CookBook (object):
    '''
    Stores a list of recipes and their build status saving it's state to a
    cache file

    @ivar recipes: dictionary with L{cerbero.recipe.Recipe} availables
    @type recipes: dict
    @ivar status: dictionary with the L{cerbero.cookbook.RecipeStatus}
    @type status: dict
    '''

    RECIPE_EXT = '.recipe'

    def __init__(self, config, load=True, offline=False):
        self.offline = offline
        self.set_config(config)
        self.recipes = {}  # recipe_name -> recipe
        self._invalid_recipes = {} # recipe -> error

        if not load:
            return

        self._restore_cache()

        if not os.path.exists(config.recipes_dir):
            raise FatalError(_("Recipes dir %s not found") %
                             config.recipes_dir)
        self.update()

    def set_config(self, config):
        '''
        Set the configuration used

        @param config: configuration used
        @type config: L{cerbero.config.Config}
        '''
        self._config = config
        config.cookbook = self
        for c in config.arch_config.keys():
            config.arch_config[c].cookbook = self

    def get_config(self):
        '''
        Gets the configuration used

        @return: current configuration
        @rtype: L{cerbero.config.Config}
        '''
        return self._config

    def set_status(self, status):
        '''
        Sets the recipes status

        @param status: the recipes status
        @rtype: dict
        '''
        self.status = status

    def update(self):
        '''
        Reloads the recipes list and updates the cookbook
        '''
        self._load_recipes()
        self._load_manifest()
        self.save()

    def get_recipes_list(self):
        '''
        Gets the list of recipes

        @return: list of recipes
        @rtype: list
        '''
        recipes = list(self.recipes.values())
        recipes.sort(key=lambda x: x.name)
        return recipes

    def add_recipe(self, recipe):
        '''
        Adds a new recipe to the cookbook

        @param recipe: the recipe to add
        @type  recipe: L{cerbero.build.cookbook.Recipe}
        '''
        self.recipes[recipe.name] = recipe

    def get_recipe(self, name):
        '''
        Gets a recipe from its name

        @param name: name of the recipe
        @type name: str
        '''
        if name not in self.recipes:
            if name in self._invalid_recipes:
                raise self._invalid_recipes[name]
            raise RecipeNotFoundError(name)
        return self.recipes[name]

    def update_step_status(self, recipe_name, step):
        '''
        Updates the status of a recipe's step

        @param recipe_name: name of the recipe
        @type recipe: str
        @param step: name of the step
        @type step: str
        '''
        status = self._recipe_status(recipe_name)
        status.steps.append(step)
        status.steps = list(set(status.steps))
        self._update_status(recipe_name, status)

    def update_installed_files(self, recipe_name, files):
        '''
        Updates the installed files of the recipe

        @param recipe_name: name of the recipe
        @type recipe: str
        @param files: installed files
        @type files: list
        '''
        def _file_exists(install_dir, file):
            f = os.path.join(install_dir, file)
            return os.path.exists(f)

        status = self._recipe_status(recipe_name)
        installed_files = set(files)
        existing_files = set(filter(lambda x: _file_exists(self._config.install_dir, x), installed_files))
        non_existing_files = list(installed_files - existing_files)
        if non_existing_files:
            m.warning('There are some installed files for recipe {} that don\'t exist anymore. '
                      'Removing them from recipe\'s cache:\n{}'.format(recipe_name, '\n'.join(non_existing_files)))
        status.installed_files = list(existing_files)
        self._update_status(recipe_name, status)
        return status.installed_files

    def update_build_status(self, recipe_name, built_version):
        '''
        Updates the recipe's build status

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @param built_version: built version or None to reset it
        @type built_version: str
        '''
        status = self._recipe_status(recipe_name)
        status.needs_build = built_version == None
        status.built_version = built_version
        self._update_status(recipe_name, status)

    def update_needs_build(self, recipe_name, needs_build):
        '''
        Updates the recipe's needs_build field

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @param needs_build: whether the recipe needs to be built
        @type needs_build: bool
        '''
        status = self._recipe_status(recipe_name)
        status.needs_build = needs_build
        self._update_status(recipe_name, status)

    def recipe_built_version (self, recipe_name):
        '''
        Get the las built version of a recipe from the build status

        @param recipe_name: name of the recipe
        @type recipe_name: str
        '''
        try:
            return self._recipe_status(recipe_name).built_version
        except:
            return None

    def step_done(self, recipe_name, step):
        '''
        Whether is step is done or not

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @param step: name of the step
        @type step: bool
        '''
        return step in self._recipe_status(recipe_name).steps

    def clean_recipe_status(self, recipe_name):
        '''
        Cleans completely the build status of a recipe

        @param recipe_name: name of the recipe
        @type recipe_name: str
        '''
        if recipe_name in self.status:
            del self.status[recipe_name]
            self.save()

    def reset_recipe_status(self, recipe_name):
        '''
        Resets the build status of a recipe

        @param recipe_name: name of the recipe
        @type recipe_name: str
        '''
        if recipe_name in self.status:
            # We need to save the previous installed_files to remove the
            # old files that may not be present in a new installation
            installed_files = self.status[recipe_name].installed_files
            self.clean_recipe_status(recipe_name)
            if installed_files:
                self._recipe_status(recipe_name).installed_files = installed_files
            self.save()

    def recipe_remove_installed_files(self, recipe_name):
        installed_files = self.recipe_installed_files(recipe_name)
        for f in [os.path.join(self._config.install_dir, f) for f in installed_files]:
            # os.path.exists returns False for broken symbolic links
            if os.path.exists(f) or os.path.islink(f):
                os.remove(f)
        self._config.cookbook.update_installed_files(recipe_name, [])

    def recipe_needs_build(self, recipe_name):
        '''
        Whether a recipe needs to be build or not

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @return: True if the recipe needs to be build
        @rtype: bool
        '''
        return self._recipe_status(recipe_name).needs_build

    def recipe_installed_files(self, recipe_name):
        '''
        Return the list of installed files for a given recipe

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @return: installed files
        @rtype: list
        '''
        return self._recipe_status(recipe_name).installed_files

    def list_recipe_deps(self, recipe_name):
        '''
        List the dependencies that needs to be built in the correct build
        order for a recipe

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @return: list of L{cerbero.recipe.Recipe}
        @rtype: list
        '''
        recipe = self.get_recipe(recipe_name)
        return self._find_deps(recipe, {}, [])

    def list_recipe_reverse_deps(self, recipe_name):
        '''
        List the dependencies that depends on this recipe

        @param recipe_name: name of the recipe
        @type recipe_name: str
        @return: list of reverse dependencies L{cerbero.recipe.Recipe}
        @rtype: list
        '''
        recipe = self.get_recipe(recipe_name)
        return list(set([r for r in list(self.recipes.values()) if recipe.name in r.deps]))

    def save(self):
        try:
            cache_file = self._cache_file(self.get_config())
            if not os.path.exists(os.path.dirname(cache_file)):
                os.makedirs(os.path.dirname(cache_file))
            with open(cache_file, 'wb') as f:
                pickle.dump(self.status, f)
        except IOError as ex:
            m.warning(_("Could not cache the CookBook: %s") % ex)

    def _update_status(self, recipe_name, status):
        self.status[recipe_name] = status
        self.save()

    def _runtime_deps (self):
        return [x.name for x in list(self.recipes.values()) if x.runtime_dep]

    def _cache_file(self, config):
        if config.cache_file is not None:
            return os.path.join(config.home_dir, config.cache_file)
        else:
            return COOKBOOK_FILE

    def _restore_cache(self):
        try:
            with open(self._cache_file(self.get_config()), 'rb') as f:
                self.status = pickle.load(f)
        except Exception:
            self.status = {}
            m.warning(_("Could not recover status"))

    def _find_deps(self, recipe, state={}, ordered=[]):
        if state.get(recipe, 'clean') == 'processed':
            return
        if state.get(recipe, 'clean') == 'in-progress':
            raise FatalError(_("Dependency Cycle: {0}".format(recipe.name)))
        state[recipe] = 'in-progress'
        recipe_deps = recipe.list_deps()
        if not recipe.runtime_dep:
            recipe_deps = self._runtime_deps () + recipe_deps
        for recipe_name in recipe_deps:
            try:
                recipedep = self.get_recipe(recipe_name)
            except RecipeNotFoundError as e:
                raise FatalError(_("Recipe %s has a unknown dependency %s"
                                 % (recipe.name, recipe_name)))
            try:
                self._find_deps(recipedep, state, ordered)
            except FatalError:
                m.error('Error finding deps of "{0}"'.format(recipe.name))
                raise
        state[recipe] = 'processed'
        ordered.append(recipe)
        return ordered

    def _recipe_status(self, recipe_name):
        recipe = self.get_recipe(recipe_name)
        if recipe_name not in self.status:
            filepath = None
            if hasattr(recipe, '__file__'):
                filepath = recipe.__file__
            self.status[recipe_name] = RecipeStatus(filepath, steps=[],
                    file_hash=recipe.get_checksum(), installed_files=[])
        return self.status[recipe_name]

    def _recipe_is_reset(self, recipe_name):
        if not recipe_name in self.status:
            return True

        st = self.status[recipe_name]
        return not st.steps

    def _reset_recipe_status(self, recipe, change_name, previous, now):
        if self._recipe_is_reset(recipe.name):
            return

        m.message('Resetting {}\'s status because its {} changed from {} to {}'.format(
            recipe.name, change_name, previous, now))
        self.reset_recipe_status(recipe.name)
        if recipe.library_type == LibraryType.STATIC:
            rdeps = self.list_recipe_reverse_deps(recipe.name)
            rdeps = [r for r in rdeps if not self._recipe_is_reset(r.name)]
            if rdeps:
                rdeps_names = ' '.join([r.name for r in rdeps])
                m.message('Resetting also the status of all its reverse dependencies '
                    'because it\'s a static library: {}'.format(rdeps_names))
                for r in rdeps:
                    self.reset_recipe_status(r.name)

    def _reset_recipe_if_needed(self, recipe):
        # Check that the recipe still exists in cache, because
        # a prior recipe might have reset its status
        if self._recipe_is_reset(recipe.name):
            return
        st = self.status[recipe.name]
        # Need to check the version too, because the version can be
        # inherited from a different file, f.ex. recipes/custom.py
        # This only needs to be done when the checksum does not depend
        # on the parents, hence when strict_recipe_checksum is not used
        if not self._config.strict_recipe_checksum:
            bv = recipe.built_version()
            if bv != st.built_version:
                self._reset_recipe_status(recipe, 'built_version', st.built_version, bv)
                return

        # Use getattr as file_hash we added later
        saved_hash = getattr(st, 'file_hash', '')
        current_hash = recipe.get_checksum()
        if saved_hash != current_hash:
            self._reset_recipe_status(recipe, 'file_hash', saved_hash, current_hash)

    def _load_recipes(self):
        self.recipes = {}
        recipes = defaultdict(dict)
        recipes_repos = self._config.get_recipes_repos()
        for _, (repodir, priority) in recipes_repos.items():
            recipes[int(priority)].update(self._load_recipes_from_dir(repodir))
        # Add recipes by asceding pripority
        for key in sorted(recipes.keys()):
            self.recipes.update(recipes[key])

        async_tasks = []
        # Check for updates in the recipe file to reset the status
        for recipe in list(self.recipes.values()):
            # Set the offline property, used by the recipe while performing the
            # fetch build step
            recipe.offline = self.offline
            if recipe.name not in self.status:
                continue
            st = self.status[recipe.name]
            # filepath attribute was added afterwards
            if not hasattr(st, 'filepath') or not getattr(st, 'filepath'):
                st.filepath = recipe.__file__
            # if filepath has changed, force using get_checksum(), this will
            # allow safe relocation of the recipes.
            if recipe.__file__ != st.filepath:
                st.filepath = recipe.__file__
            if not self._recipe_is_reset(recipe.name):
                # We only need to collect the built version in case we don't use the strict recipe
                # checksum, because it'll be used to make sure that no parent has changed the
                # version
                if self._config.strict_recipe_checksum:
                    self._reset_recipe_if_needed(recipe)
                else:
                    recipe.run_func_depending_on_built_version(async_tasks, self._reset_recipe_if_needed, recipe)

        run_until_complete(async_tasks)

    def _load_recipes_from_dir(self, repo):
        recipes = {}
        recipes_files = shell.find_files('*%s' % self.RECIPE_EXT, repo)
        recipes_files.extend(shell.find_files('*/*%s' % self.RECIPE_EXT, repo))
        custom = None
        m_path = os.path.join(repo, 'custom.py')
        if os.path.exists(m_path):
            custom = imp.load_source('custom', m_path)
            custom.GStreamer.using_manifest_force_git = self._config.manifest is not None
        for f in recipes_files:
            # Try to load the custom.py module located in the recipes dir
            # which can contain private classes to extend cerbero's recipes
            # and reuse them in our private repository
            try:
                recipes_from_file = self._load_recipes_from_file(f, custom)
            except RecipeNotFoundError:
                m.warning(_("Could not found a valid recipe in %s") % f)
            if recipes_from_file is None:
                continue
            for recipe in recipes_from_file:
                recipes[recipe.name] = recipe
        return recipes

    def _load_recipes_from_file(self, filepath, custom=None):
        recipes = []
        d = {'Platform': Platform, 'Architecture': Architecture,
                'BuildType': BuildType, 'SourceType': SourceType,
                'Distro': Distro, 'DistroVersion': DistroVersion,
                'License': License, 'recipe': crecipe, 'os': os,
                'BuildSteps': crecipe.BuildSteps,
                'InvalidRecipeError': InvalidRecipeError,
                'FatalError': FatalError,
                'custom': custom, '_': _, 'shell': shell,
                'LibraryType' : LibraryType}
        d_keys = set(list(d.keys()))
        try:
            new_d = d.copy ()
            parse_file(filepath, new_d)
            # List new objects parsed added to the globals dict
            diff_keys = [x for x in set(new_d.keys()) - d_keys]
            # Find all objects inheriting from Recipe
            for recipe_cls_key in [x for x in diff_keys if self._is_recipe_class(new_d[x])]:
                if self._config.target_arch != Architecture.UNIVERSAL:
                    recipe = self._load_recipe_from_class(
                        new_d[recipe_cls_key], self._config, filepath, custom)
                else:
                    recipe = self._load_universal_recipe(d, new_d[recipe_cls_key],
                        recipe_cls_key, filepath)

                if recipe is not None:
                    recipes.append(recipe)
        except Exception:
            m.warning("Error loading recipe in file %s" % (filepath))
            print(traceback.format_exc())
        return recipes

    def _is_recipe_class(self, cls):
        # The final check for 'builtins' is to make sure we only take in
        # account classes defined in the recipe file and not the imported
        # ones in the, for example base classes that inherit from Recipe
        return isinstance(cls, type) and \
            issubclass (cls, crecipe.Recipe) and \
            cls.__module__ == 'builtins'

    def _load_recipe_from_class(self, recipe_cls, config, filepath, setup_env=False):
        try:
            r = recipe_cls(config)
            r.__file__ = os.path.abspath(filepath)
            if setup_env:
                config.do_setup_env()
            r.env = os.environ.copy()
            r.prepare()
            return r
        except InvalidRecipeError as e:
            self._invalid_recipes[r.name] = e

    def _load_universal_recipe(self, globals_dict, recipe_cls,
            recipe_cls_key, filepath, custom=None):
        if self._config.target_platform in [Platform.IOS, Platform.DARWIN]:
            recipe = crecipe.UniversalFlatRecipe(self._config)
        else:
            recipe = crecipe.UniversalRecipe(self._config)
        for c in list(self._config.arch_config.keys()):
            conf = self._config.arch_config[c]
            if self._config.target_platform not in [Platform.IOS,
                    Platform.DARWIN]:
                conf.prefix = os.path.join(self._config.prefix, c)
            # For univeral recipes, we need to parse again the recipe file.
            # Otherwise, class variables with mutable types like the "deps"
            # dictionary are reused in new instances
            if recipe_cls is None:
                parsed_dict = dict(globals_dict)
                parse_file(filepath, parsed_dict)
                recipe_cls = parsed_dict[recipe_cls_key]
            r = self._load_recipe_from_class(recipe_cls, conf, filepath, True)
            if r is not None:
                recipe.add_recipe(r)
            recipe_cls = None
        if recipe.is_empty():
            return None
        return recipe

    def _load_manifest(self):
        manifest_path = self._config.manifest

        if not manifest_path:
         return

        manifest = Manifest(manifest_path)
        manifest.parse()

        for project in manifest.projects.values():
            for recipe in self.recipes.values():
                if recipe.stype not in [SourceType.GIT,
                                        SourceType.GIT_TARBALL]:
                    continue;

                default_fetch = manifest.get_fetch_uri(project, manifest.default_remote)
                if recipe.remotes['origin'] in [default_fetch,
                                                default_fetch[:-4]]:
                    recipe.remotes['origin'] = project.fetch_uri
                    recipe.commit = project.revision
