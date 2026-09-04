# Changelog

## 1.1.0 -- 2026-09-04

First round of use on real production scenes. Most of what follows came out of
that: two ways a file could be silently skipped, and a set of controls for the
cases where the default routing is not what you want.

### Fixed -- references the scan could not see

- **Keyframed file parameters were dropped entirely.**
  `unexpandedString()` *raises* on a parameter with keyframes ("Cannot get
  unexpanded string for parms with keyframes") rather than returning a value,
  and all three scene walks called it before testing for keyframes. The
  exception handler then swallowed the parameter, so an animated file path was
  never seen at all rather than deliberately skipped. `raw_value()` now checks
  keyframes first and returns `None` for anything not ours to touch.

- **Folder references were reported as missing files.**
  A File Cache in "Constructed" mode points its Base Folder at a *directory*
  and builds the filename from Base Name and Version. `exists` called
  `os.path.isfile()`, which reports a real, populated directory as missing --
  and `missing` is the one verdict in this tool that says something is already
  broken. Folders now report as present, carry their real file count and total
  size, are routed by what is inside them, and are **never ticked**, because
  consolidating one copies the whole tree.

- **`dest_relative()` built the filename from the raw value**, so a collision
  rename (`wood_1.exr`) was ignored and the parameter was repointed at the
  file already sitting there.

- **A sequence whose frames are missing from disk lost its `$F4` token**,
  because the frame-token check keyed on `is_seq` rather than on the value
  being written.

### Added

- **Send selected rows to a folder you pick.** Right-click any selection and
  "Send N rows to a folder..." to override the type routing for just those
  files; "Reset to default destination" undoes it. A custom folder inside the
  project still gets a variable so the scene stays portable; one outside it
  cannot, so the parameter becomes an absolute path and the tool warns once.

- **Show files already in the project.** `scan(include_internal=True)` lists
  every file the scene references, with an "in project" location that is never
  recommended or ticked. Without it there was no way to see the files that are
  already correct.

- **Choose which variable to write** (`$HIP`, `$JOB`, or any you type). A
  variable that does not resolve to the project root is refused with an
  explanation, and the tool offers to adopt its folder as the root instead.

- **"Go to this node"** on the right-click menu. Double-clicking a row already
  jumped to the node, but nothing in the UI said so.

- **[docs/HOUDINI_NOTES.md](docs/HOUDINI_NOTES.md)** collects the scene-walking
  and Qt lessons that cost real time here, so the sibling tools do not
  rediscover them.

- **[INTEGRATION.md](INTEGRATION.md)** documents the small surface Scene
  Optimizer reads from this tool, and what changing it would break.

### Changed

- "Update paths in scene" no longer reports "All 79 relative paths already use
  $HIP" in a scene full of `$JOB` parameters. Those resolved *above* the
  project root and were correctly skipped, but the message counted only what
  was inside and read as though nothing used `$JOB` at all.

- `dest_dir` and `dest` are properties rather than values fixed at
  construction, so a destination override applies without rebuilding the
  reference.

13 test suites, no Houdini or Qt needed to run them.

## 1.0.0

Initial release. Walks every file parameter in the scene, finds the ones
resolving outside the project, and copies them in while repointing the
parameters at `$HIP`-relative paths.
