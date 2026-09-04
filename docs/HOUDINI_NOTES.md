# Houdini path-scanning notes

Things learned building Asset Consolidator that cost real time to find. Written
for anyone building a sibling tool that walks a scene for file references
(Asset Cleaner, Scene Optimizer, anything similar), so the same traps do not
have to be rediscovered.

This is *not* how to use Asset Consolidator -- see the README for that. This is
what Houdini and Qt actually do, as opposed to what you would expect.

---

## Walking the scene for file parameters

```python
for node in hou.node("/").allSubChildren(top_down=True,
                                         recurse_in_locked_nodes=False):
    for parm in node.parms():
        template = parm.parmTemplate()
        if not isinstance(template, hou.StringParmTemplate):
            continue
        if template.stringType() != hou.stringParmType.FileReference:
            continue
        yield parm
```

Notes on each part:

- **`recurse_in_locked_nodes=False`** matters. Locked HDA contents are not the
  user's to rewrite, and descending into them on a heavy scene is slow for no
  benefit.
- **`stringType() == FileReference`** is the check that matters. Do not guess
  from parameter names (`file`, `filename`, `texture`, `map`, `picture`, ...) --
  the list is endless and third-party HDAs invent their own. Houdini already
  knows which parameters are file references; ask it.
- **`node.parms()` can raise `hou.OperationFailed`** on some nodes. Wrap it.
- **Skip `hda_path` / `otl_path`.** They are file references pointing at the
  HDA library itself. Rewriting one detaches the node from its definition.

### Parameters you must not rewrite

```python
if parm.keyframes():
    continue
```

A keyframed or expression-driven parameter holds an expression, not a path.
`parm.set()` on one **destroys the expression** and replaces it with a literal
string. This is silent and not obviously undoable from the user's point of
view. Always skip them.

### `unexpandedString()` raises on keyframed parms

Order matters, and getting it wrong hides parameters completely:

```python
# WRONG -- unexpandedString() raises "Cannot get unexpanded string for parms
# with keyframes", the handler swallows it, and the parm vanishes entirely
try:
    raw = parm.unexpandedString()
except Exception:
    continue
if parm.keyframes():
    continue

# RIGHT -- test for keyframes first
if parm.keyframes():
    continue
raw = parm.unexpandedString()
```

The failure is silent: a keyframed file path is not *skipped*, it is never
seen. Confirmed live on Houdini 21.0.512.

### Values that are not filesystem paths

```python
if resolved.startswith(("op:", "http:", "https:", "opdef:")):
    continue
if not os.path.isabs(resolved):
    continue
```

`op:/obj/geo1` is a live node reference. `opdef:` points inside an HDA.
Neither is a file on disk and neither should be copied, moved or reported as
missing.

---

## `raw` vs `resolved` -- always keep both

```python
raw = parm.unexpandedString()   # "$HIP/tex/smoke.$F4.exr"
resolved = parm.eval()          # "F:/proj/tex/smoke.0001.exr"
```

Use **`resolved`** to decide anything about the filesystem: does it exist, what
size, which drive, is it inside the project.

Use **`raw`** whenever you write a value back, and to see what variable the
path already uses. `eval()` has expanded `$F4` to a concrete frame -- writing
that back would pin an animated sequence to frame 1.

Getting these backwards is the single easiest way to break a scene.

---

## `os.path.commonpath` returns OS-native separators

This one silently inverts an inside/outside test on Windows:

```python
# WRONG on Windows: commonpath returns backslashes, root has forward slashes,
# so this is False even for a file that IS inside root.
os.path.commonpath([filepath.lower(), root.lower()]) == root.lower()

# RIGHT
common = os.path.commonpath([filepath.lower(), root.lower()])
return common.replace("\\", "/").rstrip("/") == root.lower()
```

It also **raises `ValueError`** for paths on different drives rather than
returning `""`, so it has to be wrapped -- and different drives is exactly the
common case for an external reference.

Normalise every path through one helper on the way in (forward slashes, no
trailing slash, `expandvars`) and compare case-insensitively. Windows paths are
case-insensitive; a `.lower()` comparison is not optional.

Do not use a plain `startswith` for this. `C:/proj/shot01_old` starts with
`C:/proj/shot01` but is a completely different folder.

---

## `exists` must mean "present", not "is a file"

```python
# WRONG -- reports a real directory as missing
return os.path.isfile(self.resolved)

# RIGHT
return os.path.exists(self.resolved)
```

A **File Cache in "Constructed" mode** points its Base Folder parameter at a
*directory* and builds the filename from Base Name and Version. The parameter
is a perfectly healthy folder reference. `isfile()` calls it missing.

This matters because "missing" is usually the one verdict that means *something
is already broken*. It has to be right, or it cries wolf.

If your tool distinguishes them, keep an `is_dir` flag rather than overloading
`exists`.

---

## Sequences

Detected from the **raw** value:

```python
SEQ_PATTERNS = [r"\$F\d*", r"%0?\d*d", r"#+", r"<UDIM>"]
```

`$F`, `$F4`, `%04d`, `####`, `<UDIM>`. To find the frames on disk, substitute
`*` for the token and glob. To write a path back, keep the original token and
change only the directory.

A sequence is one *reference* but many *files*. Any count or total you show has
to decide which it means; showing "1" for a 200-frame cache is misleading, and
so is counting it as 200 references.

---

## Variables ($HIP, $JOB and friends)

**Prefer `$HIP`.** Houdini always defines it, from the open scene. `$JOB` has
to be set per session and, when it is not, silently falls back to the user's
home folder -- so a path that looks portable resolves only on the machine that
wrote it.

**Never write a variable that does not resolve to the folder you mean.** Check
first:

```python
hou.getenv("JOB")  # -> the folder, or None
```

A token pointing somewhere else is *worse* than an absolute path: the parameter
looks tidy and correct, and silently loads the wrong file or nothing at all.
Fall back to an absolute path instead.

Watch for the ancestor case: a `$JOB` of `.../HD` with a scene in
`.../HD/SHOT/performance` is set, valid, and still the wrong token for that
scene's files.

**To change which variable a path uses, rebuild from the resolved location**
rather than string-replacing the old token. That way `$JOB/tex/a.exr`, a bare
absolute path and any third variable all converge on the same result. Preserve
the frame token from `raw` when doing it.

`hou.getenv` is the right call, not `os.environ` -- Houdini variables are not
process environment variables.

---

## Writing back safely

- Wrap the whole operation in `with hou.undos.group("..."):` so it is one undo
  step, not hundreds.
- Catch `hou.PermissionError` separately -- a locked parameter is a normal
  thing to hit and should be reported, not crash the run.
- Never overwrite a file at the destination. If something is already there,
  compare (size + mtime) and skip if identical; otherwise write to a `_1`
  variant. `shutil.copy2` preserves mtime, which is what makes the "already
  copied this" check work and the operation idempotent.

---

## Qt notes (PySide2 and PySide6)

Houdini 20.5 ships PySide2, 21+ ships PySide6. Import with a fallback and the
same code runs on both:

```python
try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt
```

`QMenu.exec_()` (PySide2) vs `.exec()` (PySide6) -- check with `hasattr`.

### Table traps, all found the hard way

- **Never index your data by row number** if the table can be sorted. Store the
  object on the row (`item.setData(Qt.UserRole, obj)`) and read it back. Qt
  reorders rows; your list does not follow. The failure is silent and awful:
  the user ticks one row and a different file gets acted on.
- **Turn sorting off while populating.** With sorting on, Qt re-sorts after
  every `setItem`, interleaving rows mid-fill.
- **Block signals when updating cells programmatically**, or `setText` fires
  `itemChanged` and your handler runs for edits the user did not make.
- **Fit columns in `showEvent`, not `__init__`.** Before the dialog is shown
  the viewport has no real width, so any layout you compute is against the
  wrong number.
- **`resizeColumnsToContents()` ignores the window.** One long path will happily
  take 1200px and push later columns off screen. Budget the available width
  yourself and give the leftovers to the columns that need it.
- **`setTextElideMode(Qt.ElideMiddle)`** for paths. The default elides the
  right, which throws away the filename -- the part you actually need.
- Connect signals **after** all widgets exist. `addItems()` on a combo fires
  `currentTextChanged`, and if the handler touches a widget built later in the
  same function, that is an `AttributeError` on open.

---

## Testing without Houdini

All of the logic above is testable with `hou` and PySide stubbed -- no Houdini,
no dependencies, runs in CI:

```python
hou = types.ModuleType("hou")
hou.getenv = lambda k: os.environ.get(k)
sys.modules["hou"] = hou
```

Fake parameter objects need only `node().path()`, `name()`,
`unexpandedString()`, `eval()`, `keyframes()` and `set()`. Monkeypatch the
scene walk (`_iter_file_parms`) to yield them.

Worth testing on real temp files rather than mocks: the copy path, name
collisions, and idempotency. Those are the ones where being wrong loses data.

A Qt stub needs `__mro_entries__` to be usable as a base class, and a real
`text()` if you assert on cell contents.

---

## See also

- `INTEGRATION.md` -- the API surface Scene Optimizer depends on, and what
  breaks it
- `../AssetCleaner` -- the same scene walk pointed at the opposite question
