# Fridge

The fridge functionality of Cerbero aims to reduce the time taken to cook recipes by freezing them once they are built and uploading their content to some FTP server that acts as a fridge for the recipes. This way, we avoid the configure and compile steps, which are arguably the most time-consuming ones.

## How recipes are reused

A hash is generated for the current environment used in the configuration. This means everything that `config::get_env` considers plus the compiler version. e.g. the linker flags, include dir, etc. Hence, the idea is to reuse the same binaries already built in a conservative way to ensure they will work.

The environment is sanitized before creating the hash, so that the prefix, Cerbero's home and user's home are normalized. Apart from that, the package naming already contains the target platform and target architecture.

## How recipes are stored in the fridge

The fridge consists of a FTP server with write permissions granted so that the client can create a different directory per configuration. This directory will contain all the packages built for this specific configuration for all target platforms and target architectures.

Every frozen recipe is uploaded along a sha256 files containing the hash of the packages file. This file will be used on the local fridge to know whether the remote one needs to be downloaded or not. In other words, the `binaries_local` directory specified in the config acts as a local cache for the frozen recipes.

The following example contains the devel and runtime packages of yasm and zlib for macOS 64bit, along with their sha256:

```
└── ffdfa03d41ab86a88f559ab46546c7ac
    ├── yasm-pkg-darwin-x86_64-1.3.0-aa98cab175d302577087dcaa225f4df3-devel.tar.bz2
    ├── yasm-pkg-darwin-x86_64-1.3.0-aa98cab175d302577087dcaa225f4df3-devel.tar.bz2.sha256
    ├── yasm-pkg-darwin-x86_64-1.3.0-aa98cab175d302577087dcaa225f4df3.tar.bz2
    ├── yasm-pkg-darwin-x86_64-1.3.0-aa98cab175d302577087dcaa225f4df3.tar.bz2.sha256
    ├── zlib-pkg-darwin-x86_64-1.2.11-dffcadaf533a8451920690663494d892-devel.tar.bz2
    ├── zlib-pkg-darwin-x86_64-1.2.11-dffcadaf533a8451920690663494d892-devel.tar.bz2.sha256
    ├── zlib-pkg-darwin-x86_64-1.2.11-dffcadaf533a8451920690663494d892.tar.bz2
    └── zlib-pkg-darwin-x86_64-1.2.11-dffcadaf533a8451920690663494d892.tar.bz2.sha256
```

## How to use the fridge functionality

First, we need add the `binaries_remote` element into the configuration. e.g.: `binaries_remote=FtpBinaryRemote('127.0.0.1:2121')`.

Apart from that, the following arguments have been added to the `build` and `bootstrap` commands:

```
--use-binaries     use binaries from the repo before building
--upload-binaries  after a recipe is built upload the corresponding binary package
--build-missing    in case a binary package is missing try to build it
--fridge           equivalent to '--build-missing --use-binaries --upload-binaries'
```