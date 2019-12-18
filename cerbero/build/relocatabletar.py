"""
RelocatableTar* are classes that represent a .tar file with relocation abilities
"""

import os
from tarfile import TarFile
from cerbero.utils import shell, is_text_file
from cerbero.tools.osxrelocator import OSXRelocator


class RelocatableTar(TarFile):
    """Generic RelocatableTar relocates CERBERO_PREFIX  for common files"""

    def extract_and_relocate(self, extract_to_path):
        self.extractall(extract_to_path)
        for member in self.getmembers():
            full_member_path = os.path.join(extract_to_path, member.name)
            if self._is_relocatable(full_member_path):
                self._relocate(full_member_path, extract_to_path)

    def _is_relocatable(self, file):
        if not os.path.islink(file) and not os.path.isdir(file):
            return is_text_file(file)
        else:
            return False

    def _relocate(self, file, subst_path):
        with open(file, 'rb+') as fo:
            content = fo.read()
            content = content.replace('CERBERO_PREFIX'.encode('utf-8'), subst_path.encode('utf-8'))
            fo.seek(0)
            fo.write(content)
            fo.truncate()
            fo.flush()


class RelocatableTarOSX(RelocatableTar):
    """OSX Specialization, also checks specific OSX files and uses OSXRelocator"""

    def extract_and_relocate(self, extract_to_path):
        self.relocator = OSXRelocator(extract_to_path, extract_to_path, True)
        RelocatableTar.extract_and_relocate(self, extract_to_path)

    def _is_dylib_file(self, file):
        return os.path.splitext(file)[1] in ['.dylib']

    def _has_relocatable_extension(self, file):
        return (RelocatableTar._has_relocatable_extension(self, file) or
                self._is_dylib_file(file))

    def _relocate(self, file, subst_path):
        if self._is_dylib_file(file):
            self.relocator.change_id(file, file)
        else:
            RelocatableTar._relocate(self, file, subst_path)
