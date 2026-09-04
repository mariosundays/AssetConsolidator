# Houdini Asset Consolidator

Finds every file your Houdini scene references from outside the project and
copies them in, repointing the parameters as it goes.

Useful before archiving a shot, handing a scene to someone else, or sending it
to a farm -- the cases where a texture on your own D: drive quietly becomes a
missing file for everyone else.

Houdini 20.5+ | Windows, macOS, Linux | GPL-3.0

![The main window](docs/screenshot-main.png)

## Install

1. Download or clone this repo somewhere permanent.
2. Copy `asset_consolidator.json` into your Houdini packages folder
   (`Documents/houdini20.5/packages`, or wherever `HOUDINI_PACKAGE_DIR`
   points), and edit the two paths inside it to point at the folder you just
   put down.
3. Restart Houdini.

It appears under **Tools > Consolidate Assets**. More detail, including how to
check it loaded, is in [INSTALL.md](INSTALL.md).

## Using it

Open it and you get every external reference in the scene: which node uses it,
what it is, where it lives now, and where it will go. The ones worth pulling in
are already ticked.

Tick and untick whatever you like, then press **Consolidate Assets**. Files are
copied into `tex/`, `geo/`, `abc/` or `misc/` under the project, and each
parameter is repointed at its new home.

Nothing is copied until you press the button, and nothing is ever overwritten:
an identical file already there is skipped, and a different file with the same
name gets a `_1` suffix. The whole run is a single undo.

Worth knowing:

- **The `Location` column** says what kind of place each file is in -- another
  drive, a shared library, a temp folder -- ranked by how likely that link is
  to break. Missing files show red and are never ticked.
- **Right-click** a row to consolidate just that file, jump to its node, send a
  selection to a folder you pick, or select a whole group at once (one drive,
  one file type, one folder):

  ![The right-click menu](docs/screenshot-menu.png)
- **`Use variable`** decides what gets written into the repointed paths. `$HIP`
  by default; type any Houdini variable. It turns green when it really resolves
  to your project root, and one that does not is never written.
- **`Update paths in scene`** swaps the variable on paths that already use one
  and already sit inside the project. It copies nothing.
- **Untick `Repoint parameters`** for a dry run: copies the files, leaves every
  parameter alone.

Sequences (`$F4`, `%04d`, `####`, `<UDIM>`) copy every frame and keep their
frame token. Folder references, such as a File Cache Base Folder, are listed
but never ticked for you -- a cache folder can be enormous, so pulling one in
should be a deliberate choice.

## Status

In use on real production scenes. The scanning, routing, variable and selection
logic is covered by 13 test suites that need neither Houdini nor any
dependency:

    python tests/run_all.py

Still worth trying on a copy of a scene the first time.

## Also here

- [docs/HOUDINI_NOTES.md](docs/HOUDINI_NOTES.md) -- what was learned building
  this: walking a scene for file parameters, path handling, and the Qt traps.
  For anyone writing a similar tool.
- [INTEGRATION.md](INTEGRATION.md) -- the small API other tools call.

## Licence

GPL-3.0. See [LICENSE](LICENSE).
