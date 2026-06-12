#! /bin/sh
# Build the llvm (wasm32) toolchain

WIPE=$1
CURDIR=`pwd`
set -ex

echo "Building llvm (wasm32) toolchain"
if test "x$WIPE" = "x1"; then
  ./cerbero-uninstalled -c config/llvm-wasm32.cbc wipe --force
fi
# ./cerbero-uninstalled -c config/mingw-multilib-$p.cbc bootstrap --system=no --toolchains=no
./cerbero-uninstalled -c config/llvm-wasm32.cbc build toolchain

PLAT=wasm32
TC=llvm-$PLAT.tar.xz # TODO: Add version
echo "Creating tarball $TC"
cd  ~/llvm-wasm32/
XZ_OPT=-9 tar cJf $CURDIR/$TC *
cd $CURDIR
md5sum  $TC | awk '{print $1}' > $TC.md5
sha1sum $TC | awk '{print $1}' > $TC.sha1
sha256sum $TC | awk '{print $1}' > $TC.sha256
