# Houdini Asset Consolidator

A Houdini tool that finds every file your scene references from outside the
project and copies those files in, repointing the parameters as it goes.

Useful before archiving a shot, handing a scene to someone else, or sending it
to a farm -- the cases where a texture sitting on your own D: drive quietly
turns into a missing file for everyone else.

Houdini 20.5+ | Windows, macOS, Linux | GPL-3.0

Menu: **Tools > Consolidate Assets**

![The main window](docs/screenshot-main.png)

Every external reference in the scene, with why each one is worth pulling in
and where it will land. Right-click isolates a group -- one drive, one file
type, one folder, or one kind of location:

![The right-click menu](docs/screenshot-menu.png)

## What it does

1. Walks every file-typed parameter in the scene.
2. Flags the ones resolving outside the project root.
3. Shows them in a table: node, type, current path, why, size, destination.
4. You tick and untick whatever you want.
5. "Consolidate Assets" copies them in and repoints the parameters.

Nothing is copied until you press the button, and nothing is ever overwritten.

## Project root

`$HIP` -- the folder holding the open `.hip` file. `$JOB` is used instead when
it is set to a real folder *and* the `.hip` sits underneath it. The root is
shown at the top of the window and can be overridden with Browse.

### Why $HIP and not $JOB

`$HIP` is always defined and always correct, because Houdini sets it from the
open scene. `$JOB` has to be set per session, and when it is not it silently
falls back to the user home folder -- so a "portable" path resolves only on the
machine that wrote it.

If you Browse to a root that is neither `$HIP` nor `$JOB`, the tool writes an
absolute path rather than a token that would point somewhere wrong.

## Destination routing

| File type | Goes to |
|---|---|
| exr hdr png jpg tif tga dpx rat tx psd | `<root>/tex` |
| bgeo bgeo.sc geo vdb obj fbx usd sim | `<root>/geo` |
| abc | `<root>/abc` |
| anything else | `<root>/misc` |

## Recommendations

Everything the scan lists is outside the project, so everything is a valid
candidate. The `Location` column says what kind of place each file lives in,
ranked by how likely that link is to break. The recommended rows are ticked
for you on scan:

| Location | Meaning |
|---|---|
| `temp folder` | In %TEMP% or Downloads. Could vanish on reboot |
| `network path` | On a UNC share. Breaks when the share is offline |
| `other drive` | A different drive from the project |
| `shared library` | Same drive, but a shared asset or library folder |
| `outside project` | Outside the project, nothing else notable |
| `missing` | Not on disk. Never recommended, never ticked |

"Select recommended" re-applies that choice at any time.

## Colour coding

Source paths are tinted **per drive**, assigned in first-seen order so any
drive letter or UNC share gets a stable colour. The `Type` column is coloured
**per extension**, and destinations **per target folder**. Missing files are
red and override everything. A legend sits above the status line.

## Table

- **Drag any column divider** to resize -- every column is interactive.
- **Double-click a divider** fits that column; **double-click the header** fits
  every column. Also on the right-click menu.
- **Drag a header** to reorder columns.
- Columns are budgeted against the window width, so long paths elide in the
  middle rather than pushing later columns off screen.
- **Double-click a row** to jump to that node in the network editor.

## Right-click menu

Menu actions **isolate**: they clear every tick first, then select what you
asked for. "Select only this row" on a fully selected table leaves exactly one
row ticked. "Add to selection" is there when you want the additive version.

- Select only these rows / Add to selection / Deselect these rows
- Select only what is on the same **drive**
- Select only files of the same **extension**
- Select only this **folder**
- Select only the same kind of **location**
- **Consolidate this file now** -- copies just that one file, whatever is
  ticked. With several rows selected you also get "Consolidate these N files".
- Copy path, Show in Explorer, Fit columns

Right-clicking a row outside the current selection acts on that row, the way a
file manager does. Missing files are never ticked by any bulk action, and the
per-file consolidate is greyed out for them.

## Behaviour worth knowing

- **Sequences** (`$F`, `$F4`, `%04d`, `####`, `<UDIM>`) copy every frame on
  disk; the parameter keeps its frame token.
- **Name collisions** with a *different* file get a `_1` suffix. An identical
  file already at the destination is skipped, so re-running is a no-op.
- **Missing files** are listed in red, cannot be selected, and never have their
  parameter rewritten.
- **Expression and keyframed parameters are skipped**, so rewriting cannot
  destroy an expression.
- Locked and read-only parameters are reported rather than silently failing.
- The whole run is a single undo block.

## Install

See [INSTALL.md](INSTALL.md). Short version: put the folder somewhere, point a
Houdini package `.json` at it, restart Houdini.

## Status

Working and in use, but young. The scanning, routing and selection logic is
covered by unit tests; the copy step has been tested on synthetic files rather
than years of production scenes. Try it on a copy of a scene first.

## Licence

GPL-3.0. See [LICENSE](LICENSE).
