# Sync Fluendo cerbero fork with Community one

* [Config file](./fluendo-cerbero.toml)
* [Confluence page](https://fluendo.atlassian.net/wiki/spaces/ENG/pages/3957686326/Sync+Fluendo+cerbero+fork+with+Community+one)

## GUW

See [git-upstream-workflow](https://github.com/fluendo/git-upstream-workflow) project

* 🟢 `COM-10816-strip-and-section-mixins`: Make sync method in Strip class public [(PR link)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1521)
* 🟢 `COM-10670-recipe-warn-override`: cookbook: Warn about recipe override by name [(PR link)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1497)
* 🔄 `COM-10967-fix-wix-annotations-for-old-python`: import annotations is missing in cerbero/packages/windows/wix_on_ninja.py [(PR link)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1536)

## Issues on GitLab

* [484 Platform configs silently override user configs](https://gitlab.freedesktop.org/gstreamer/cerbero/-/issues/484):
    found during [COM-10815 building 1.0 cross linux arm64](https://fluendo.atlassian.net/browse/COM-10815);
    temporary could be solved by “--variants noalsa” option to cli

## Projects

* cerbero
* fluendo-cerbero
* flu-plugins
* infrastructure-as-code
