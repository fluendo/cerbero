#! /bin/sh
# Build the Windows cross and native toolchains for x86 and x86_64

WIPE=$1
CURDIR=`pwd`
set -e

for p in "lin" "win"
do
    echo "Building $p-w64 toolchain"
    if test "x$WIPE" = "x1"; then
      ./cerbero-uninstalled -c config/mingw-w64-$p.cbc wipe --force
    fi
  ./cerbero-uninstalled -c config/mingw-w64-$p.cbc build toolchain

  ARCH=x86_64
  if test "x$p" = "xwin"; then
      PLAT=windows
  else
      PLAT=linux
  fi
  TC=mingw-w64-gcc-8.2.0-$PLAT-$ARCH.tar.xz
  echo "Creating tarball $TC"
  cd  ~/mingw/$PLAT/w64
  XZ_OPT=-9 tar cJf $CURDIR/$TC *
  cd $CURDIR
  md5sum  $TC | awk '{print $1}' > $TC.md5
  sha1sum $TC | awk '{print $1}' > $TC.sha1
done
