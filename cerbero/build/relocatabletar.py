"""
RelocatableTar* are classes that represent a .tar file with relocation abilities
"""

import os
from tarfile import TarFile
from cerbero.utils import shell, is_text_file
from cerbero.tools.osxrelocator import OSXRelocator


class RelocatableTar(TarFile):
    """
    Generic RelocatableTar relocates CERBERO_PREFIX and CERBERO_TOOLCHAIN_PREFIX
    for common files
    """

    def extract_and_relocate(self, prefix, toolchain_prefix):
        self.extractall(prefix)
        for member in self.getmembers():
            full_member_path = os.path.join(prefix, member.name)
            if self._is_relocatable(full_member_path):
                self._relocate(full_member_path, prefix, toolchain_prefix)

    def _has_relocatable_content(self, file):
        return False

    def _is_relocatable(self, file):
        if not os.path.islink(file) and not os.path.isdir(file):
            return self._has_relocatable_content(file) or is_text_file(file)
        else:
            return False

    def _relocate(self, file, prefix, toolchain_prefix):
        with open(file, 'rb+') as fo:
            content = fo.read()
            # Relocate first the longest of the paths
            if toolchain_prefix and toolchain_prefix in prefix:
                content = content.replace('CERBERO_PREFIX'.encode('utf-8'), prefix.encode('utf-8'))
                if toolchain_prefix:
                    content = content.replace('CERBERO_TOOLCHAIN_PREFIX'.encode('utf-8'), toolchain_prefix.encode('utf-8'))
            else:
                if toolchain_prefix:
                    content = content.replace('CERBERO_TOOLCHAIN_PREFIX'.encode('utf-8'), toolchain_prefix.encode('utf-8'))
                content = content.replace('CERBERO_PREFIX'.encode('utf-8'), prefix.encode('utf-8'))
            fo.seek(0)
            fo.write(content)
            fo.truncate()
            fo.flush()


class RelocatableTarOSX(RelocatableTar):
    """OSX Specialization, also checks specific OSX files and uses OSXRelocator"""

    def extract_and_relocate(self, prefix, toolchain_prefix):
        self.relocator = OSXRelocator(prefix, prefix, True)
        super().extract_and_relocate(prefix, toolchain_prefix)

    def _has_relocatable_content(self, file):
        return self.relocator.is_mach_o_file(file) or super()._has_relocatable_content(file)

    def _relocate(self, file, prefix, toolchain_prefix):
        if self.relocator.is_mach_o_file(file):
            self.relocator.change_id(file, file)
        else:
            super()._relocate(file, prefix, toolchain_prefix)
