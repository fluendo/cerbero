# Packaging

## Specific workflow in cerbero when packaging
### Files provider
Files provider is in charge of list, merge and decide which files will be included in the package. Todo so, is iterates through some atrributes of the class. Here will be described something that may help you.

In the FilesProvider class some categories are defined like follows:

```
    LIBS_CAT = 'libs'
    BINS_CAT = 'bins'
    PY_CAT = 'python'category"
    DEVEL_CAT = 'devel'
    LANG_CAT = 'lang'
    TYPELIB_CAT = 'typelibs'
```

A file category is considered any class attribute whose prefix is `files_`, so the following categories will be included in the package:
```
files_extra
files_to_not_package
files_misc
```

All this processes are done through the following functions:
`files_list_by_categories` -> `_list_files_by_category` -> `_get_category_files_list` 

So, if want to add files your packages just create an attribute with the prefix `files_` that will be processed afterwards.