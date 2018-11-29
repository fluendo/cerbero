#------------------------------------------------------------------------------
# RelocatableTar* are classes that represent a .tar file
# with relocation abilities
#------------------------------------------------------------------------------

import os
from tarfile import TarFile
from cerbero.utils import shell, is_text_file
from cerbero.tools.osxrelocator import OSXRelocator

#------------------------------------------------------------------------------
# Generic RelocatableTar relocates CERBERO_PREFIX
# for common files
#------------------------------------------------------------------------------


class RelocatableTar(TarFile):

    def extractAndRelocate(self, extract_to_path):
        self.extractall(extract_to_path)
        for member in self.getmembers():
            fullMemberPath = os.path.join(extract_to_path, member.name)
            if self._isRelocatable(fullMemberPath):
                self._relocate(fullMemberPath, extract_to_path)

    def _isScript(self, file):
        return ('bin' in os.path.splitext(file)[0] and is_text_file(file))

    def _hasRelocatableExtension(self, file):
        return os.path.splitext(file)[1] in ['.la', '.pc']

    def _isRelocatable(self, file):
        if not os.path.islink(file) and not os.path.isdir(file):
            return self._hasRelocatableExtension(file) or self._isScript(file)
        else:
            return False

    def _relocate(self, file, subst_path):
        shell.replace(file, {"CERBERO_PREFIX": subst_path})

#------------------------------------------------------------------------------
# OSX Specialization, also checks specific OSX files
# and uses OSXRelocator
#------------------------------------------------------------------------------


class RelocatableTarOSX(RelocatableTar):

    def extractAndRelocate(self, extract_to_path):
        self.relocator = OSXRelocator(extract_to_path, extract_to_path, True)
        RelocatableTar.extractAndRelocate(self, extract_to_path)

    def _isDyLibFile(self, file):
        return os.path.splitext(file)[1] in ['.dylib']

    def _hasRelocatableExtension(self, file):
        return (RelocatableTar._hasRelocatableExtension(self, file) or
                self._isDyLibFile(file))

    def _relocate(self, file, subst_path):
        if self._isDyLibFile(file):
            self.relocator.change_id(file, file)
        else:
            RelocatableTar._relocate(self, file, subst_path)
