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

import os, sys
import urllib
import json

from cerbero.commands import Command, register_command
from cerbero.build.cookbook import CookBook
from cerbero.enums import LibraryType
from cerbero.errors import FatalError, PackageNotFoundError
from cerbero.packages.packagesstore import PackagesStore
from cerbero.utils import _, N_, ArgparseArgument, remove_list_duplicates, git, shell, run_until_complete
from cerbero.utils import messages as m
from cerbero.build.source import Tarball
from cerbero.config import Distro
from cerbero.build.fridge import Fridge
from cerbero.build.recipe import BuildSteps

NUMBER_OF_JOBS_IF_USED = 8
NUMBER_OF_JOBS_IF_UNUSED = NUMBER_OF_JOBS_IF_USED

class Fetch(Command):

    def __init__(self, args=[]):
        args.append(ArgparseArgument('--reset-rdeps', action='store_true',
                    default=False, help=_('reset the status of reverse '
                    'dependencies too')))
        args.append(ArgparseArgument('--print-only', action='store_true',
                    default=False, help=_('print all source URLs to stdout')))
        args.append(ArgparseArgument('--full-reset', action='store_true',
                    default=False, help=_('reset to extract step if rebuild is needed')))
        args.append(ArgparseArgument('--use-binaries', '--fridge', action='store_true',
                    default=False, help=_('use fridge to download binary packages if available')))
        args.append(ArgparseArgument('--jobs', '-j', action='store', nargs='?', type=int,
                    const=NUMBER_OF_JOBS_IF_USED, default=NUMBER_OF_JOBS_IF_UNUSED, help=_('number of async jobs')))
        Command.__init__(self, args)

    @staticmethod
    def fetch(cookbook, recipes, no_deps, reset_rdeps, full_reset, print_only, jobs, use_binaries=False):
        fetch_recipes = []
        if not recipes:
            fetch_recipes = cookbook.get_recipes_list()
        elif no_deps:
            fetch_recipes = [cookbook.get_recipe(x) for x in recipes]
        else:
            for recipe in recipes:
                fetch_recipes += cookbook.list_recipe_deps(recipe)
            fetch_recipes = remove_list_duplicates (fetch_recipes)
        m.message(_("Fetching the following recipes using %s async job(s): %s") %
                  (jobs, ' '.join([x.name for x in fetch_recipes])))
        to_rebuild = []
        tasks = []

        fridge = None
        if use_binaries:
            fridge = Fridge(PackagesStore(cookbook.get_config(), recipes=fetch_recipes, cookbook=cookbook))

        async def _run_fetch(cookbook, fridge, recipe, step_name):
            # Fetch step
            if hasattr(recipe, step_name):
                stepfunc = getattr(recipe, step_name)
                await stepfunc()
            # Fetch binary step
            else:
                try:
                    # Ensure the built_version is collected asynchronously before
                    # calling _get_package_name, because that is done in a sync way and
                    # would call otherwise the sync built_version, which takes time.
                    # Since the built_version is cached, we can gather it here and will be
                    # reused by both the sync and async flavors of built_version
                    if hasattr(recipe, 'async_built_version'):
                        await recipe.async_built_version()

                    # Attempt to run fetch_binary step only if remote binary exists
                    try:
                        await fridge.check_remote_binary_exists(recipe)
                    except PackageNotFoundError as e:
                        # Fallback to fetch step instead
                        m.action('{}: {}. Falling back to fetch from source'.format(recipe, e))
                        await _run_fetch(cookbook, fridge, recipe, BuildSteps.FETCH[1])
                        return
                    stepfunc = getattr(fridge, step_name)
                    await stepfunc(recipe)
                except:
                    m.warning('Error downloading remote package {}. Falling back to fetch from source'.format(recipe.name))
                    # Something failed using fridge. Fallback to normal fetch step
                    return await _run_fetch(cookbook, fridge, recipe, BuildSteps.FETCH[1])

            cookbook.update_step_status(recipe.name, step_name)
            cookbook.update_needs_build(recipe.name, True)

        for i in range(len(fetch_recipes)):
            recipe = fetch_recipes[i]
            if print_only:
                # For now just print tarball URLs
                if isinstance(recipe, Tarball):
                    m.message("TARBALL: {} {}".format(recipe.url, recipe.tarball_name))
                continue
            step_name = BuildSteps.FETCH[1]
            if recipe.allow_package_creation and fridge:
                step_name = Fridge.FETCH_BINARY[1]

            if cookbook.step_done(recipe.name, step_name):
                continue
            tasks.append(_run_fetch(cookbook, fridge, recipe, step_name))

        run_until_complete(tasks, max_concurrent=jobs)
        m.message("All async fetch jobs finished")

        # Checking the current built version against the fetched one
        # needs to be done *after* actually fetching
        for recipe in fetch_recipes:
            bv = cookbook.recipe_built_version(recipe.name)
            cv = recipe.built_version()
            if bv != cv:
                # On different versions, only reset recipe if:
                #  * forced
                #  * OR it was fully built already
                if full_reset or not cookbook.recipe_needs_build(recipe.name):
                    to_rebuild.append(recipe)
                    cookbook.reset_recipe_status(recipe.name)
                    if recipe.library_type == LibraryType.STATIC or reset_rdeps:
                        for r in cookbook.list_recipe_reverse_deps(recipe.name):
                            to_rebuild.append(r)
                            cookbook.reset_recipe_status(r.name)

        if to_rebuild:
            to_rebuild = sorted(list(set(to_rebuild)), key=lambda r:r.name)
            m.message(_("These recipes have been updated and will "
                        "be rebuilt:\n%s") %
                        '\n'.join([x.name for x in to_rebuild]))


class FetchRecipes(Fetch):
    doc = N_('Fetch the recipes sources')
    name = 'fetch'

    def __init__(self):
        args = [
                ArgparseArgument('recipes', nargs='*',
                    help=_('list of the recipes to fetch (fetch all if none '
                           'is passed)')),
                ArgparseArgument('--no-deps', action='store_true',
                    default=False, help=_('do not fetch dependencies')),
                ]
        Fetch.__init__(self, args)

    def run(self, config, args):
        cookbook = CookBook(config)
        return self.fetch(cookbook, args.recipes, args.no_deps,
                          args.reset_rdeps, args.full_reset, args.print_only, args.jobs,
                          args.use_binaries)


class FetchPackage(Fetch):
    doc = N_('Fetch the recipes sources from a package')
    name = 'fetch-package'

    def __init__(self):
        args = [
                ArgparseArgument('package', nargs=1,
                    help=_('package to fetch')),
                ArgparseArgument('--deps', action='store_false',
                    default=True, help=_('also fetch dependencies')),
                ]
        Fetch.__init__(self, args)

    def run(self, config, args):
        store = PackagesStore(config)
        package = store.get_package(args.package[0])
        return self.fetch(store.cookbook, package.recipes_dependencies(),
                          args.deps, args.reset_rdeps, args.full_reset,
                          args.print_only, args.jobs, args.use_binaries)

class FetchCache(Command):
    doc = N_('Fetch a cached build from GitLab CI based on cerbero git '
            'revision.')
    name = 'fetch-cache'

    base_url = 'https://gitlab.freedesktop.org/%s/cerbero/-/jobs'
    build_dir = '/builds/%s/cerbero/cerbero-build'
    log_size = 50

    def __init__(self, args=[]):
        args.append(ArgparseArgument('--commit', action='store', type=str,
                    default='HEAD', help=_('the commit to pick artifact from')))
        args.append(ArgparseArgument('--namespace', action='store', type=str,
                    default='gstreamer', help=_('GitLab namespace to search from')))
        args.append(ArgparseArgument('--branch', action='store', type=str,
                    default='master', help=_('Git branch to search from')))
        args.append(ArgparseArgument('--job-id', action='store', type=str,
                    default='master', help=_('Artifact job id, this will skip'
                        ' commit matching')))
        args.append(ArgparseArgument('--skip-fetch', action='store_true',
                    default=False, help=_('Skip fetching cached build, the '
                        'commit/url log will be updated if --job-id is present')))
        Command.__init__(self, args)

    def request(self, url, values, token=None):
        headers = {}
        if token:
            headers = {"Private-Token": token}

        data = urllib.parse.urlencode(values)
        url = "%s?%s" % (url, data)
        req = urllib.request.Request(url, headers=headers)

        m.message("GET %s" % url)

        try:
            resp = urllib.request.urlopen(req);
            return json.loads(resp.read())
        except urllib.error.URLError as e:
            raise FatalError(_(e.reason))

    def get_deps(self, config, args):
        namespace = args.namespace
        branch = args.branch
        distro = config.target_distro
        arch = config.target_arch
        if distro == Distro.REDHAT:
            distro = 'fedora'

        base_url = self.base_url % namespace
        url = "%s/artifacts/%s/raw/cerbero-build/cerbero-deps.log" % (base_url, branch)

        deps = []
        try:
            deps = self.request(url, values = {
                    'job': "cerbero deps %s %s" % (distro, arch)
                    })
        except FatalError as e:
            m.warning("Could not get cache list: %s" % e.msg)

        return deps

    def find_dep(self, deps, sha):
        for dep in deps:
            if dep['commit'] == sha:
                return dep

        m.warning("Did not find cache for commit %s" % sha)
        return None

    def fetch_dep(self, config, dep, namespace):
        try:
            artifacts_path = "%s/cerbero-deps.tar.gz" % config.home_dir
            run_until_complete(shell.download(dep['url'], artifacts_path, check_cert=True, overwrite=True))
            run_until_complete(shell.unpack(artifacts_path, config.home_dir))
            os.remove(artifacts_path)
            origin = self.build_dir % namespace
            m.message("Relocating from %s to %s" % (origin, config.home_dir))
            # FIXME: Just a quick hack for now
            shell.call(("grep -lnrIU %(origin)s | xargs "
                        "sed \"s#%(origin)s#%(dest)s#g\" -i") % {
                            'origin': origin, 'dest': config.home_dir},
                        config.home_dir)
        except FatalError as e:
            m.warning(("Could not retrieve artifact for commit %s (the artifact "
                    "may have expired): %s") % (dep['commit'], e.msg))

    def update_log(self, config, args, deps, sha):
        base_url = self.base_url % args.namespace
        url = "%s/%s/artifacts/raw/cerbero-deps.tar.gz" % (base_url, args.job_id)
        deps.insert(0, {'commit': sha, 'url': url})
        deps = deps[0:self.log_size]
        with open("%s/cerbero-deps.log" % config.home_dir, 'w') as outfile:
                json.dump(deps, outfile, indent=1)

    def run(self, config, args):
        if not config.uninstalled:
            raise FatalError(_("fetch-cache is only available with "
                        "cerbero-uninstalled"))

        git_dir = os.path.dirname(sys.argv[0])
        sha = git.get_hash(config, git_dir, args.commit)
        deps = self.get_deps(config, args)
        if not args.skip_fetch:
            dep = self.find_dep(deps, sha)
            if dep:
                self.fetch_dep(config, dep, args.namespace)
        if args.job_id:
            self.update_log(config, args, deps, sha)

register_command(FetchRecipes)
register_command(FetchPackage)
register_command(FetchCache)
