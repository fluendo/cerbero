# Sync Fluendo cerbero fork with Community one

* [Config file](./fluendo-cerbero.toml)
* [Confluence page](https://fluendo.atlassian.net/wiki/spaces/ENG/pages/3957686326/Sync+Fluendo+cerbero+fork+with+Community+one)

## GUW

See [git-upstream-workflow](https://github.com/fluendo/git-upstream-workflow) project

* 🟢 `COM-10816-strip-and-section-mixins`: Make sync method in Strip class public [(PR link)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1521)
* 🟢 `COM-10670-recipe-warn-override`: cookbook: Warn about recipe override by name [(PR link)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1497)
* 🟢 `COM-10979-show-config-build-tools`: Adding more options for show-config (build tools config and universal archs) [(PR link)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1538)
* 🟢 `COM-10967-fix-wix-annotations-for-old-python`: import annotations is missing in cerbero/packages/windows/wix_on_ninja.py [(PR link)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1536)
* 🔄 `COM-12259-fix-variants-override`: Cerbero configs: Fixing variants without changing the order of loading [(PR link)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1550)

## Issues on GitLab

### 484 Platform configs silently override user configs
[Issue on GitLab](https://gitlab.freedesktop.org/gstreamer/cerbero/-/issues/484)

Found during [COM-10815 building 1.0 cross linux arm64](https://fluendo.atlassian.net/browse/COM-10815).

First rejected try to solve the problem: `COM-10979-fix-config-override` -  [Fix config variants override with first option (two passes)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1537)

Second try: `COM-12259-fix-variants-override`:  [Cerbero configs: Fixing variants without changing the order of loading](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1550)

## Projects

### cerbero

[Fluendo repository](https://github.com/fluendo/cerbero)
[Community repository](https://gitlab.freedesktop.org/gstreamer/cerbero)

The main working branch (no PR) for this delivery:
[COM-10606-sync-cerbero](https://github.com/fluendo/cerbero/tree/COM-10606-sync-cerbero)

This branch in our repository is used with GUW:
each time I rebase it on the latest community main with already integrated changes
and not yet integrated work above the main HEAD.

There is no need to create PRs in the Fluendo repository;
it's enough to have MRs in the community GitLab.

### fluendo-cerbero

[Fluendo repository](https://github.com/fluendo/fluendo-cerbero)

The main working branch and PR for this delivery:
[COM-10606-sync-cerbero](https://github.com/fluendo/fluendo-cerbero/tree/COM-10606-sync-cerbero) /
[PR 1396](https://github.com/fluendo/fluendo-cerbero/pull/1396)

Each time the cerbero COM-10606-sync-cerbero branch is moved,
we need to change the git submodule, it produces a commit.

### flu-plugins

[Fluendo repository](https://github.com/fluendo/flu-plugins)

The main working branch for this delivery:
[COM-10606-sync-cerbero](https://github.com/fluendo/flu-plugins/tree/COM-10606-sync-cerbero) /
[PR 570](https://github.com/fluendo/flu-plugins/pull/570)

The branch is needed to:
1. have the same branch as others - this is used to run CI (fluendo-cerbero and flu-plugins must be the same)
1. have some changes (for example, to run buildone in addition to build-deps for infrastructure-as-code, like
[COM-12287](https://fluendo.atlassian.net/browse/COM-12287))

### infrastructure-as-code

[Fluendo repository](https://github.com/fluendo/infrastructure-as-code)

The main working branch and PR for this delivery:
[COM-10606-sync-cerbero](https://github.com/fluendo/infrastructure-as-code/tree/COM-10606-sync-cerbero) /
[PR 265](https://github.com/fluendo/infrastructure-as-code/pull/265)

This PR is used to rebuild all components using the script
[prepare-fluendo-cerbero.sh from flu-plugins](https://github.com/fluendo/flu-plugins/blob/COM-10606-sync-cerbero/scripts/ci/prepare-fluendo-cerbero.sh)

As a result, we've got images with the lablel
[latest_sync_cerbero in Fluendo packages](https://github.com/fluendo/infrastructure-as-code/pkgs/container/docker-flu-plugins-focal-x86-64-projects-codecs-1-0-cross-linux-arm64-cbc/258684249?tag=latest_sync_cerbero)
