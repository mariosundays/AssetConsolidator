# Integration

Asset Consolidator is **self-contained**. It has no dependencies on any other
tool, it installs on its own, and nothing here needs the notes below to work.

They matter for one reason: a third tool reads from this one, and it is not in
this repo.

| Tool | Job | Repo |
|---|---|---|
| **Asset Consolidator** | Pulls outside files into the project | this one |
| [Asset Cleaner](https://github.com/mariosundays/AssetCleaner) | Finds what nothing uses and moves it out | its own |
| [Scene Optimizer](https://github.com/mariosundays/SceneOptimizer) | Reports on both and launches them | its own |

```
Asset Cleaner ─────┐
                   ├──>  Scene Optimizer      (reads only; never writes)
Asset Consolidator ┘
```

The dependency points one way. This tool knows nothing about Scene Optimizer
and never needs to -- but if you change one of the things below, that panel
stops reporting external and missing files correctly.

Building one of these? [docs/HOUDINI_NOTES.md](docs/HOUDINI_NOTES.md) has the
scene-walking and Qt lessons from this tool, which apply to all three.

## What Scene Optimizer reads from this tool

| It calls | For |
|---|---|
| `scan(root, include_missing=True)` | Its "External references" row. Always `True`, so it can count missing files as a row of their own |
| `project_root()` | Resolving the project, rather than deciding it itself |
| `main()` | Its **Consolidate Assets...** button |
| `Reference.exists` | Splitting present from missing |
| `Reference.size_bytes` | Totalling |
| `Reference.node_path`, `Reference.resolved` | Its Missing files list |

That is the whole surface. Everything else here is private.

## `Reference.exists` is the delicate one

It must stay a **property**. The panel writes `r.exists`, so if it ever became
a method the bound method object would be truthy always, nothing would look
missing, and the panel would quietly report a clean scene forever.

It also has to mean *present on disk*, not *is a file*. This is not
hypothetical -- it used to call `os.path.isfile()`, which reports a real,
populated directory as missing. A File Cache in "Constructed" mode points its
Base Folder at a directory, so two perfectly healthy caches were shown in red
as missing files. See the `folder` location and `Reference.is_dir`.

`missing` is the one verdict in this tool that says something is already
broken, so it has to be right.

## Changes that would break it

- Renaming `scan`, `project_root` or `main`
- Dropping or renaming the `include_missing` parameter
- Changing what `scan` returns -- the panel iterates the list directly
- Renaming `Reference.exists`, `.size_bytes`, `.node_path` or `.resolved`,
  or turning `exists` into a method

Adding things is always safe. Renaming and re-signaturing is what bites.

## How you find out

`SceneOptimizer/tests/test_contract.py` imports this module for real and
checks every item above, including that `exists` is a property and that a
directory reference reports `exists=True` and `selected=False`. Run it from
that repo after changing anything in the list:

    cd ../SceneOptimizer && python tests/run_all.py

It reports `32 checks passed` when all three repos sit side by side, and skips
cleanly when they do not -- so it is only meaningful from a working copy that
has all three, which is where a break would be introduced anyway.

This tool's own suite (`python tests/run_all.py` here) does not know Scene
Optimizer exists, and should stay that way.
