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

    def _has_relocatable_content(self, file):
        return False

    def _is_relocatable(self, file):
        if not os.path.islink(file) and not os.path.isdir(file):
            return self._has_relocatable_content(file) or is_text_file(file)
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
        super().extract_and_relocate(extract_to_path)

    def _has_relocatable_content(self, file):
        return self.relocator.is_mach_o_file(file) or super()._has_relocatable_content(file)

    def _relocate(self, file, subst_path):
        if self.relocator.is_mach_o_file(file):
            self.relocator.change_id(file, file)
        else:
            super()._relocate(file, subst_path)
