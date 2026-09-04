# Tests

Pure logic tests for the parts that do not need Houdini. `hou` and PySide are
stubbed, so these run under any Python 3 with no dependencies:

    python tests/run_all.py

| Suite | Covers |
|---|---|
| `test_logic.py` | Path classification, inside/outside, sequence globbing |
| `test_copy.py` | Copy and repoint end to end, on real temp files |
| `test_ui.py` | Drive colouring, context-menu grouping |
| `test_ext.py` | Extension labels, root token, isolate selection |
| `test_verdict.py` | Which references get recommended, and why |
| `test_fit2.py` | Column width budgeting at various window sizes |
| `test_sort.py` | Sorting keys, and refs surviving row reorder |
| `test_vars.py` | Variable choice, validation and fallback |
| `test_retoken.py` | Swapping the variable on already-relative paths |
| `test_folders.py` | Folder references (File Cache Base Folder) |
| `test_custom_dest.py` | Per-row custom destination folders |
| `test_show_internal.py` | Listing in-project files; variables pointing outside |
| `test_keyframed.py` | Keyframed parms, which raise rather than return |

Suites that touch the filesystem write to a temp directory and clean up after
themselves.

Not covered: the Qt widgets themselves and the Houdini scene walk, both of
which need a live Houdini session.
