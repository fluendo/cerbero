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
import time
import shutil
import cerbero.utils.messages as m

from cerbero.config import Platform
from cerbero.utils import shell, run_until_complete, _
from cerbero.errors import FatalError

GIT = 'git'


def ensure_user_is_set(git_dir, logfile=None):
    # Set the user configuration for this repository so that Cerbero never warns
    # about it or errors out (it errors out with git-for-windows)
    try:
        shell.call('%s config user.email' % GIT, logfile=logfile)
    except FatalError:
        shell.call('%s config user.email "cerbero@gstreamer.freedesktop.org"' %
                   GIT, git_dir, logfile=logfile)

    try:
        shell.call('%s config user.name' % GIT, logfile=logfile)
    except FatalError:
        shell.call('%s config user.name "Cerbero Build System"' %
                   GIT, git_dir, logfile=logfile)

def init(git_dir, logfile=None):
    '''
    Initialize a git repository with 'git init'

    @param git_dir: path of the git repository
    @type git_dir: str
    '''
    os.makedirs(git_dir, exist_ok=True)
    shell.call('%s init' % GIT, git_dir, logfile=logfile)
    ensure_user_is_set(git_dir, logfile=logfile)


def clean(git_dir, logfile=None):
    '''
    Clean a git respository with clean -dfx

    @param git_dir: path of the git repository
    @type git_dir: str
    '''
    return shell.call('%s clean -dfx' % GIT, git_dir, logfile=logfile)


def list_tags(git_dir, fail=True):
    '''
    List all tags

    @param git_dir: path of the git repository
    @type git_dir: str
    @param fail: raise an error if the command failed
    @type fail: false
    @return: list of tag names (str)
    @rtype: list
    '''
    tags = shell.check_call('%s tag -l' % GIT, git_dir, fail=fail)
    tags = tags.strip()
    if tags:
        tags = tags.split('\n')
    return tags


def create_tag(git_dir, tagname, tagdescription, commit, fail=True, logfile=None):
    '''
    Create a tag using commit

    @param git_dir: path of the git repository
    @type git_dir: str
    @param tagname: name of the tag to create
    @type tagname: str
    @param tagdescription: the tag description
    @type tagdescription: str
    @param commit: the tag commit to use
    @type commit: str
    @param fail: raise an error if the command failed
    @type fail: false
    '''

    shell.call('%s tag -s %s -m "%s" %s' %
               (GIT, tagname, tagdescription, commit), git_dir,
               fail=fail, logfile=logfile)
    return shell.call('%s push origin %s' % (GIT, tagname), git_dir,
                      fail=fail, logfile=logfile)


def delete_tag(git_dir, tagname, fail=True, logfile=None):
    '''
    Delete a tag

    @param git_dir: path of the git repository
    @type git_dir: str
    @param tagname: name of the tag to delete
    @type tagname: str
    @param fail: raise an error if the command failed
    @type fail: false
    '''
    return shell.call('%s tag -d %s' % (GIT, tagname), git_dir, fail=fail, logfile=logfile)


async def fetch(git_dir, fail=True, logfile=None):
    '''
    Fetch all refs from all the remotes

    @param git_dir: path of the git repository
    @type git_dir: str
    @param fail: raise an error if the command failed
    @type fail: false
    '''
    # git 1.9 introduced the possibility to fetch both branches and tags at the
    # same time when using --tags: https://stackoverflow.com/a/20608181.
    # centOS 7 ships with git 1.8.3.1, hence for old git versions, we need to
    # run two separate commands.
    cmd = [GIT, 'fetch', '--all']
    ret = await shell.async_call(cmd, cmd_dir=git_dir, fail=fail, logfile=logfile)
    if ret != 0:
        return ret
    cmd.append('--tags')
    # To avoid "would clobber existing tag" error
    cmd.append('-f')
    return await shell.async_call(cmd, cmd_dir=git_dir, fail=fail, logfile=logfile)

async def submodules_update(git_dir, src_dir=None, fail=True, offline=False, logfile=None):
    '''
    Update somdules from local directory

    @param git_dir: path of the git repository
    @type git_dir: str
    @param src_dir: path or base URI of the source directory
    @type src_dir: src
    @param fail: raise an error if the command failed
    @type fail: false
    @param offline: don't use the network
    @type offline: false
    '''
    if not os.path.exists(os.path.join(git_dir, '.gitmodules')):
        m.log(_(".gitmodules does not exist in %s. No need to fetch submodules.") % git_dir, logfile)
        return

    if src_dir:
        config = shell.check_call('%s config --file=.gitmodules --list' % GIT,
                                  git_dir)
        config_array = [s.split('=', 1) for s in config.split('\n')]
        for c in config_array:
            if c[0].startswith('submodule.') and c[0].endswith('.path'):
                submodule = c[0][len('submodule.'):-len('.path')]
                shell.call("%s config --file=.gitmodules submodule.%s.url %s" %
                           (GIT, submodule, os.path.join(src_dir, c[1])),
                           git_dir, logfile=logfile)
    shell.call("%s submodule init" % GIT, git_dir, logfile=logfile)
    if src_dir or not offline:
        await shell.async_call("%s submodule sync" % GIT, git_dir, logfile=logfile)
        await shell.async_call("%s submodule update" % GIT, git_dir, fail=fail, logfile=logfile)
    else:
        await shell.async_call("%s submodule update --no-fetch" % GIT, git_dir, fail=fail, logfile=logfile)
    if src_dir:
        for c in config_array:
            if c[0].startswith('submodule.') and c[0].endswith('.url'):
                shell.call("%s config --file=.gitmodules %s  %s" %
                           (GIT, c[0], c[1]), git_dir, logfile=logfile)
        await shell.async_call("%s submodule sync" % GIT, git_dir, logfile=logfile)

async def checkout(git_dir, commit, logfile=None):
    '''
    Reset a git repository to a given commit

    @param git_dir: path of the git repository
    @type git_dir: str
    @param commit: the commit to checkout
    @type commit: str
    '''
    cmd = [GIT, 'reset', '--hard', commit]
    return await shell.async_call(cmd, git_dir, logfile=logfile)

async def async_get_hash(config, git_dir, commit, remotes=None):
    '''
    Get a commit hash from a valid commit.
    Can be used to check if a commit exists

    @param git_dir: path of the git repository
    @type git_dir: str
    @param commit: the commit to log
    @type commit: str
    @param remote: the repo's remote
    @type remote: str
    '''

    # Ensure git uses the system's libraries instead of the ones in the home_dir
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = config._pre_environ.get("LD_LIBRARY_PATH", "")

    # In case this hash is taken when the repo has not been cloned yet
    # (e.g. changing stype from tarball to git, during fridge), we need
    # to collect the actual commit we would checkout. Otherwise, fridge
    # wouldn't be able to reuse the same package.
    if not os.path.isdir(os.path.join(git_dir, '.git')):
        if remotes:
            remote = remotes['origin']
            commit_split = commit.split('/')
            if len(commit_split) > 1:
                remote = remotes[commit_split[0]]
                commit = commit_split[1]

            remote_commit = await shell.async_check_output('%s ls-remote %s %s' % (GIT, remote, commit), env=env)
            # If the commit/tag/branch given doesn't show up using ls-remote, it means
            # it is not the HEAD of any refs. Hence, it must be a previous commit
            # that we can use directly
            if remote_commit:
                return remote_commit.split()[0]
            else:
                return commit
        else:
            raise Exception('Cannot retrieve hash of a commit without cloning or knowing the remote')
    output = await shell.async_check_output('%s rev-parse %s' %
                            (GIT, commit), git_dir, env=env)
    return output.rstrip()

def get_hash(config, git_dir, commit, remotes=None):
    '''
    Get a commit hash from a valid commit.
    Can be used to check if a commit exists

    @param git_dir: path of the git repository
    @type git_dir: str
    @param commit: the commit to log
    @type commit: str
    @param remote: the repo's remote
    @type remote: str
    '''

    # Ensure git uses the system's libraries instead of the ones in the home_dir
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = config._pre_environ.get("LD_LIBRARY_PATH", "")

    # In case this hash is taken when the repo has not been cloned yet
    # (e.g. changing stype from tarball to git, during fridge), we need
    # to collect the actual commit we would checkout. Otherwise, fridge
    # wouldn't be able to reuse the same package.
    if not os.path.isdir(os.path.join(git_dir, '.git')):
        if remotes:
            remote = remotes['origin']
            commit_split = commit.split('/')
            if len(commit_split) > 1:
                remote = remotes[commit_split[0]]
                commit = commit_split[1]

            remote_commit = shell.check_output('%s ls-remote %s %s' % (GIT, remote, commit), env=env)
            # If the commit/tag/branch given doesn't show up using ls-remote, it means
            # it is not the HEAD of any refs. Hence, it must be a previous commit
            # that we can use directly
            if remote_commit:
                return remote_commit.split()[0]
            else:
                return commit
        else:
            raise Exception('Cannot retrieve hash of a commit without cloning or knowing the remote')
    output = shell.check_output('%s rev-parse %s' %
                            (GIT, commit), git_dir, env=env)
    return output.rstrip()

async def local_checkout(git_dir, local_git_dir, commit, logfile=None):
    '''
    Clone a repository for a given commit in a different location

    @param git_dir: destination path of the git repository
    @type git_dir: str
    @param local_git_dir: path of the source git repository
    @type local_git_dir: str
    @param commit: the commit to checkout
    @type commit: false
    '''
    branch_name = 'cerbero_build'
    await shell.async_call([GIT, 'checkout', commit, '-B', branch_name], local_git_dir, logfile=logfile)
    await shell.async_call([GIT, 'clone', local_git_dir, '-s', '-b', branch_name, '.'],
               git_dir, logfile=logfile)
    ensure_user_is_set(git_dir, logfile=logfile)
    await submodules_update(git_dir, local_git_dir, logfile=logfile)

def add_remote(git_dir, name, url, logfile=None):
    '''
    Add a remote to a git repository

    @param git_dir: destination path of the git repository
    @type git_dir: str
    @param name: name of the remote
    @type name: str
    @param url: url of the remote
    @type url: str
    '''
    try:
        shell.call('%s remote add %s %s' % (GIT, name, url), git_dir, logfile=logfile)
    except:
        shell.call('%s remote set-url %s %s' % (GIT, name, url), git_dir, logfile=logfile)


def check_line_endings(platform):
    '''
    Checks if on windows we don't use the automatic line endings conversion
    as it breaks everything

    @param platform: the host platform
    @type platform: L{cerbero.config.Platform}
    @return: true if git config is core.autorlf=false
    @rtype: bool
    '''
    if platform != Platform.WINDOWS:
        return True
    val = shell.check_call('git config --get core.autocrlf')
    if ('false' in val.lower()):
        return True
    return False


def init_directory(git_dir, logfile=None):
    '''
    Initialize a git repository with the contents
    of a directory

    @param git_dir: path of the git repository
    @type git_dir: str
    '''
    init(git_dir, logfile=logfile)
    try:
        shell.call('%s add --force -A .' % GIT, git_dir, logfile=logfile)
        shell.call('%s commit -m "Initial commit" > /dev/null 2>&1' % GIT,
            git_dir, logfile=logfile)
    except:
        pass


def apply_patch(patch, git_dir, logfile=None):
    '''
    Applies a commit patch usign 'git am'
    of a directory

    @param git_dir: path of the git repository
    @type git_dir: str
    @param patch: path of the patch file
    @type patch: str
    '''
    shell.call('%s am --ignore-whitespace %s' % (GIT, patch), git_dir, logfile=logfile)
