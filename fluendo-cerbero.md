# Sync Fluendo cerbero fork with Community one

* [Config file](./fluendo-cerbero.toml)
* [Confluence page](https://fluendo.atlassian.net/wiki/spaces/ENG/pages/3957686326/Sync+Fluendo+cerbero+fork+with+Community+one)

## GUW

See [git-upstream-workflow](https://github.com/fluendo/git-upstream-workflow) project

* 🟢 `COM-10816-strip-and-section-mixins`: Make sync method in Strip class public [(PR link)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1521)
* 🟢 `COM-10670-recipe-warn-override`: cookbook: Warn about recipe override by name [(PR link)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1497)
* 🟢 `COM-10979-show-config-build-tools`: Adding more options for show-config (build tools config and universal archs) [(PR link)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1538)
* 🟢 `COM-10967-fix-wix-annotations-for-old-python`: import annotations is missing in cerbero/packages/windows/wix_on_ninja.py [(PR link)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1536)
* 🔄 `COM-10979-fix-config-override`: Fix config variants override with first option (two passes) [(PR link)](https://gitlab.freedesktop.org/gstreamer/cerbero/-/merge_requests/1537)

## Issues on GitLab

* [484 Platform configs silently override user configs](https://gitlab.freedesktop.org/gstreamer/cerbero/-/issues/484):
    found during [COM-10815 building 1.0 cross linux arm64](https://fluendo.atlassian.net/browse/COM-10815);
    see `COM-10979-fix-config-override`

## Projects

* cerbero
* fluendo-cerbero
* flu-plugins
* infrastructure-as-code
