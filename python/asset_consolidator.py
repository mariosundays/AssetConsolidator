# Asset Consolidator -- consolidate external file references into a Houdini project.
# Copyright (C) 2026 Mario Domingos
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <https://www.gnu.org/licenses/>.

"""
Asset Consolidator -- find file references that live outside the current Houdini
project and copy them in, repointing the parameters at $HIP-relative paths.

Works in Houdini 20.5 through 22.x (PySide2 and PySide6 both handled).

Menu entry: Tools > Consolidate Assets
"""

import os
import re
import shutil
import subprocess
import sys

import hou

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Qt compatibility -- H20.5 ships PySide2, H21+ ships PySide6.
# ---------------------------------------------------------------------------

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from PySide6.QtCore import Qt
except ImportError:  # Houdini 20.5
    from PySide2 import QtCore, QtGui, QtWidgets
    from PySide2.QtCore import Qt


# ---------------------------------------------------------------------------
# Destination routing -- which project subfolder each file type belongs in.
# ---------------------------------------------------------------------------

TYPE_FOLDERS = [
    ("tex", {
        ".exr", ".hdr", ".hdri", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
        ".tga", ".bmp", ".dpx", ".cin", ".rat", ".tx", ".psd", ".pic",
    }),
    ("geo", {
        ".bgeo", ".sc", ".geo", ".vdb", ".obj", ".fbx", ".ply", ".stl",
        ".usd", ".usda", ".usdc", ".usdz", ".sim", ".bclip",
    }),
    ("abc", {".abc"}),
]

MISC_FOLDER = "misc"

# .bgeo.sc and friends -- treat the compound extension as one unit.
COMPOUND_EXTS = (".bgeo.sc", ".bgeo.gz", ".geo.gz", ".vdb.sc")

# Parameters that name a file but which we never want to touch.
SKIP_PARM_NAMES = {"hda_path", "otl_path"}


def classify(filepath):
    """Return the project subfolder name this file type belongs in."""
    lower = filepath.lower()
    for compound in COMPOUND_EXTS:
        if lower.endswith(compound):
            ext = "." + compound.split(".")[1]
            break
    else:
        ext = os.path.splitext(lower)[1]

    for folder, extensions in TYPE_FOLDERS:
        if ext in extensions:
            return folder
    return MISC_FOLDER


def classify_folder(folderpath, limit=200):
    """
    Which project subfolder a *directory* reference belongs in.

    A folder has no extension of its own, so it is routed by what is in it:
    whichever destination the files inside vote for most. A geo cache folder
    belongs in geo, not in misc with the loose odds and ends.

    Only the first `limit` files are sampled -- a cache folder can hold tens
    of thousands of frames and they are all going to vote the same way.
    """
    votes = {}
    seen = 0
    try:
        for folder, _dirnames, filenames in os.walk(folderpath):
            for name in filenames:
                target = classify(name)
                votes[target] = votes.get(target, 0) + 1
                seen += 1
                if seen >= limit:
                    raise StopIteration
    except StopIteration:
        pass
    except OSError:
        pass

    if not votes:
        return MISC_FOLDER
    # Most common wins; ties break toward the named folders over misc.
    return sorted(votes.items(),
                  key=lambda kv: (-kv[1], kv[0] == MISC_FOLDER))[0][0]


def file_ext(filepath):
    """
    The extension of a path, lower case, without the dot. Compound suffixes
    are kept whole so a cache reads "bgeo.sc" rather than "sc".
    """
    name = os.path.basename((filepath or "").replace("\\", "/")).lower()
    for compound in COMPOUND_EXTS:
        if name.endswith(compound):
            return compound.lstrip(".")
    ext = os.path.splitext(name)[1].lstrip(".")
    return ext


def ext_label(filepath):
    """Upper-case label for the Type column, e.g. EXR, JPG, BGEO.SC."""
    ext = file_ext(filepath)
    return ext.upper() if ext else "-"


# Distinct colour per extension so file kinds are scannable at a glance.
EXT_COLOURS = {
    "exr": "#7ee787", "hdr": "#7ee787", "hdri": "#7ee787",
    "png": "#6bb3ff", "jpg": "#6bb3ff", "jpeg": "#6bb3ff",
    "tif": "#5fd7d7", "tiff": "#5fd7d7", "tga": "#5fd7d7",
    "tx": "#a5d6a7", "rat": "#a5d6a7", "psd": "#c5a3ff",
    "abc": "#d2a8ff", "usd": "#d2a8ff", "usda": "#d2a8ff",
    "usdc": "#d2a8ff", "usdz": "#d2a8ff",
    "bgeo": "#ffb86b", "bgeo.sc": "#ffb86b", "geo": "#ffb86b",
    "vdb": "#ff9ec4", "obj": "#e3d16b", "fbx": "#e3d16b",
}

DEFAULT_EXT_COLOUR = "#9aa0a6"


def ext_colour(label):
    """Colour for an extension label as shown in the Type column."""
    return EXT_COLOURS.get((label or "").lower(), DEFAULT_EXT_COLOUR)


# ---------------------------------------------------------------------------
# Project root resolution
# ---------------------------------------------------------------------------

def _clean(path):
    """Normalise a path for comparison: forward slashes, no trailing slash."""
    if not path:
        return ""
    path = os.path.normpath(os.path.expandvars(path)).replace("\\", "/")
    return path.rstrip("/")


def project_root():
    """
    The project root: the folder holding the current .hip file ($HIP).

    $HIP is always defined and always correct for the open scene, whereas
    $JOB has to be set per session and silently falls back to the user home
    folder when it is not. Use the variable field in the UI to consolidate
    against $JOB or any other variable instead.
    """
    hip = _clean(hou.getenv("HIP") or "")
    return hip or _clean(hou.getenv("JOB") or "")


# Variables offered in the dropdown. Any other Houdini variable can be typed.
COMMON_VARS = ("$HIP", "$JOB")


def normalise_var(text):
    """Accept HIP, $HIP, ${HIP} or hip and return "$HIP"."""
    text = (text or "").strip()
    if not text:
        return ""
    text = text.strip("${}").strip()
    return "$" + text.upper() if text else ""


def var_value(var):
    """The folder a variable points at, or "" when it is not set."""
    name = normalise_var(var).lstrip("$")
    if not name:
        return ""
    return _clean(hou.getenv(name) or "")


def var_is_usable(var, root):
    """
    True when writing this variable would actually resolve back to root.

    A token that points somewhere else is worse than an absolute path: the
    parameter looks tidy and silently loads the wrong file, or nothing.
    """
    value = var_value(var)
    return bool(value) and value.lower() == _clean(root).lower()


def root_token(root, prefer=None):
    """
    The token to write into repointed parameters for this root.

    `prefer` is the variable the user picked. It is used when it genuinely
    resolves to root; otherwise we fall back to whichever known variable
    matches, and finally to the absolute path, which is at least correct.
    """
    root = _clean(root)
    if not root:
        return ""

    if prefer:
        prefer = normalise_var(prefer)
        if var_is_usable(prefer, root):
            return prefer

    for candidate in COMMON_VARS:
        if var_is_usable(candidate, root):
            return candidate

    return root


def is_inside(filepath, root):
    """True when filepath lives under root."""
    if not root:
        return False
    filepath = _clean(filepath)
    root = _clean(root)
    if not filepath:
        return False
    try:
        # commonpath returns OS-native separators, so normalise it back to
        # forward slashes before comparing against our cleaned root.
        common = os.path.commonpath([filepath.lower(), root.lower()])
        return common.replace("\\", "/").rstrip("/") == root.lower()
    except ValueError:
        # Different drives -- commonpath raises rather than returning "".
        return False


# ---------------------------------------------------------------------------
# Recommendation -- why a reference is worth consolidating
# ---------------------------------------------------------------------------

# Folders that are never a safe place to leave a dependency: caches the OS or
# a browser may clear without warning.
VOLATILE_HINTS = (
    "/temp/", "/tmp/", "/appdata/local/temp/", "/downloads/",
    "/windows/temp/", "/cache/", "/$recycle.bin/",
)

# Recommendation codes, strongest reason first.
PICK_MISSING = "missing"
PICK_VOLATILE = "temp folder"
PICK_NETWORK = "network path"
PICK_OTHER_DRIVE = "other drive"
PICK_LIBRARY = "shared library"
PICK_OUTSIDE = "outside project"
PICK_FOLDER = "folder"


def verdict(resolved, root, exists, is_dir=False):
    """
    What kind of location this reference lives in, and whether it is
    worth consolidating.

    Everything the scan returns already lives outside the project, so the
    baseline answer is always "consolidate it". The codes exist to say how
    urgent it is: a file on a teammate's drive letter or in %TEMP% will break
    far sooner than one sitting beside the project on the same disk.

    Returns (recommend, location).
    """
    if not exists:
        return False, PICK_MISSING

    # A folder reference is valid and present, but consolidating it means
    # copying a whole tree -- a cache folder can be tens of gigabytes. Never
    # volunteer that; it has to be an explicit choice.
    if is_dir:
        return False, PICK_FOLDER

    lowered = (resolved or "").lower()

    for hint in VOLATILE_HINTS:
        if hint in lowered:
            return True, PICK_VOLATILE

    if lowered.startswith("//") or lowered.startswith("\\\\"):
        return True, PICK_NETWORK

    # A different volume from the project is the classic broken-link case.
    if drive_of(resolved) != drive_of(root):
        return True, PICK_OTHER_DRIVE

    # Same drive, but a shared asset library rather than project content.
    for token in ("library", "_1library_", "/assets/", "megascans",
                  "/hdri", "/textures/", "/gobos"):
        if token in lowered:
            return True, PICK_LIBRARY

    return True, PICK_OUTSIDE


LOCATION_HELP = {
    PICK_MISSING:
        "The file is not on disk at this path.\n"
        "Nothing to copy -- fix the path first.",
    PICK_VOLATILE:
        "A temp or downloads folder.\n"
        "Windows and browsers clear these, so the file may simply vanish.",
    PICK_NETWORK:
        "A network share.\n"
        "Unavailable off the network, and slow to load over it.",
    PICK_OTHER_DRIVE:
        "A different drive from the project.\n"
        "Any machine without that drive letter sees a missing file.",
    PICK_LIBRARY:
        "A shared asset or texture library.\n"
        "Moving or reorganising the library breaks the scene.",
    PICK_OUTSIDE:
        "Outside the project folder, but otherwise unremarkable.\n"
        "Fine locally, missing for anyone you hand the scene to.",
    PICK_FOLDER:
        "A folder, not a file -- a File Cache Base Folder, say.\n"
        "It exists and is not broken. Consolidating copies the whole tree,\n"
        "so it is never ticked for you.",
}


# Colour per reason so the column scans quickly.
PICK_COLOURS = {
    PICK_FOLDER: "#6bb3ff",
    PICK_MISSING: "#ff6b6b",
    PICK_VOLATILE: "#ff9ec4",
    PICK_NETWORK: "#ffb86b",
    PICK_OTHER_DRIVE: "#ffb86b",
    PICK_LIBRARY: "#6bb3ff",
    PICK_OUTSIDE: "#7ee787",
}


# ---------------------------------------------------------------------------
# Sequence handling -- $F, $F4, %04d, ####
# ---------------------------------------------------------------------------

SEQ_PATTERNS = [
    re.compile(r"\$F\d*", re.IGNORECASE),
    re.compile(r"%0?\d*d"),
    re.compile(r"#+"),
    re.compile(r"<UDIM>", re.IGNORECASE),
    re.compile(r"<[Uu]?[Dd][Ii][Mm]>"),
]


def is_sequence(path):
    return any(p.search(path) for p in SEQ_PATTERNS)


def sequence_glob(path):
    """Turn a sequence path into a glob so we can find every frame on disk."""
    import glob as _glob

    pattern = path
    for p in SEQ_PATTERNS:
        pattern = p.sub("*", pattern)
    # Collapse runs of wildcards produced by overlapping patterns.
    pattern = re.sub(r"\*+", "*", pattern)
    try:
        return sorted(_glob.glob(pattern))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

class Reference(object):
    """One external file reference found on one parameter."""

    def __init__(self, parm, raw, resolved, root, prefer_var=None):
        self.parm = parm
        self.raw = raw                # unexpanded parm value
        self.resolved = resolved      # expanded, absolute
        self.root = root
        self.prefer_var = prefer_var  # variable the user chose, e.g. "$HIP"
        self.is_seq = is_sequence(resolved)
        self.frames = sequence_glob(resolved) if self.is_seq else []
        # Some parameters name a FOLDER rather than a file -- File Cache in
        # "Constructed" mode points its Base Folder at a directory and builds
        # the filename from Base Name and Version. Such a path is perfectly
        # valid and present, and calling it missing was wrong.
        self.is_dir = (not self.is_seq) and os.path.isdir(resolved)
        self.error = ""

        # Why this one is worth pulling in, and whether to tick it by default.
        self.recommend, self.location = verdict(resolved, root, self.exists,
                                                self.is_dir)
        self.selected = self.recommend

        # A folder has no extension of its own, so it is routed by what is
        # inside it -- a geo cache folder belongs in geo, not misc.
        if self.is_dir:
            self.subfolder = classify_folder(resolved)
        else:
            self.subfolder = classify(resolved)
        self.dest_dir = "{}/{}".format(_clean(root), self.subfolder)
        self.dest = "{}/{}".format(self.dest_dir, os.path.basename(resolved))

    @property
    def ext_label(self):
        # A folder has no extension; saying FOLDER is more use than "-".
        if getattr(self, "is_dir", False):
            return "FOLDER"
        return ext_label(self.resolved)

    @property
    def node_path(self):
        return self.parm.node().path()

    @property
    def parm_name(self):
        return self.parm.name()

    @property
    def exists(self):
        if self.is_seq:
            return bool(self.frames)
        # isfile() alone reports a real, populated directory as missing. A
        # File Cache Base Folder is exactly that, and "missing" is the one
        # verdict in this tool that says something is already broken -- so it
        # has to be right.
        return os.path.exists(self.resolved)

    @property
    def dir_files(self):
        """Every file under a folder reference, recursively."""
        if not self.is_dir:
            return []
        found = []
        for folder, _dirnames, filenames in os.walk(self.resolved):
            for name in filenames:
                found.append(os.path.join(folder, name))
        return found

    @property
    def file_count(self):
        if self.is_seq:
            return len(self.frames)
        if self.is_dir:
            return len(self.dir_files)
        return 1 if self.exists else 0

    @property
    def size_bytes(self):
        try:
            if self.is_seq:
                return sum(os.path.getsize(f) for f in self.frames)
            if self.is_dir:
                total = 0
                for path in self.dir_files:
                    try:
                        total += os.path.getsize(path)
                    except OSError:
                        pass
                return total
            return os.path.getsize(self.resolved) if self.exists else 0
        except OSError:
            return 0

    def dest_relative(self):
        """The root-relative path we will write back into the parameter."""
        name = os.path.basename(self.raw.replace("\\", "/"))
        return "{}/{}/{}".format(
            root_token(self.root, self.prefer_var), self.subfolder, name)


def _iter_file_parms():
    """Yield every file-typed parameter in the scene."""
    for node in hou.node("/").allSubChildren(top_down=True,
                                             recurse_in_locked_nodes=False):
        try:
            parms = node.parms()
        except hou.OperationFailed:
            continue

        for parm in parms:
            try:
                template = parm.parmTemplate()
            except Exception:
                continue

            if not isinstance(template, hou.StringParmTemplate):
                continue
            if template.stringType() != hou.stringParmType.FileReference:
                continue
            if parm.name() in SKIP_PARM_NAMES:
                continue
            yield parm


def scan(root=None, include_missing=True, prefer_var=None):
    """
    Walk the scene and return a list of Reference objects for every file
    parameter pointing outside the project root.
    """
    root = root or project_root()
    found = []
    seen = set()

    for parm in _iter_file_parms():
        try:
            raw = parm.unexpandedString()
        except Exception:
            continue

        if not raw or not raw.strip():
            continue

        # Skip parms driven by an expression or channel -- rewriting those
        # would destroy the expression.
        try:
            if parm.keyframes():
                continue
        except Exception:
            pass

        try:
            resolved = parm.eval()
        except Exception:
            continue

        if not resolved or not resolved.strip():
            continue

        resolved = _clean(resolved)

        # Opaque / non-filesystem references we should not try to copy.
        if resolved.startswith(("op:", "http:", "https:", "opdef:")):
            continue
        if not os.path.isabs(resolved):
            continue
        if is_inside(resolved, root):
            continue

        key = (parm.node().path(), parm.name())
        if key in seen:
            continue
        seen.add(key)

        ref = Reference(parm, raw, resolved, root, prefer_var)
        if not ref.exists and not include_missing:
            continue
        found.append(ref)

    found.sort(key=lambda r: (r.subfolder, r.node_path))
    return found


# ---------------------------------------------------------------------------
# Consolidation
# ---------------------------------------------------------------------------

def _unique_dest(dest):
    """Avoid clobbering a different file that already has this name."""
    if not os.path.exists(dest):
        return dest
    stem, ext = os.path.splitext(dest)
    for i in range(1, 1000):
        candidate = "{}_{}{}".format(stem, i, ext)
        if not os.path.exists(candidate):
            return candidate
    return dest


def _same_file(a, b):
    try:
        return (os.path.getsize(a) == os.path.getsize(b) and
                int(os.path.getmtime(a)) == int(os.path.getmtime(b)))
    except OSError:
        return False


def consolidate(refs, repoint=True, progress=None):
    """
    Copy each selected reference into the project and repoint its parameter.
    Returns (copied_files, skipped, errors) where errors is a list of strings.
    """
    copied = 0
    skipped = 0
    errors = []

    total = len(refs)
    for index, ref in enumerate(refs):
        if progress is not None:
            if not progress(index, total, ref):
                errors.append("Cancelled by user.")
                break

        try:
            if not os.path.isdir(ref.dest_dir):
                os.makedirs(ref.dest_dir)
        except OSError as exc:
            errors.append("{}  cannot create {}: {}".format(
                ref.node_path, ref.dest_dir, exc))
            continue

        try:
            if ref.is_seq:
                for frame in ref.frames:
                    target = "{}/{}".format(ref.dest_dir,
                                            os.path.basename(frame))
                    if os.path.exists(target) and _same_file(frame, target):
                        skipped += 1
                        continue
                    shutil.copy2(frame, target)
                    copied += 1
            elif ref.is_dir:
                # A folder reference (a File Cache Base Folder, say) copies as
                # a whole tree. copy2 would raise on a directory.
                target = ref.dest
                if os.path.isdir(target):
                    target = _unique_dest(target)
                shutil.copytree(ref.resolved, target)
                ref.dest = target
                copied += ref.file_count
            else:
                target = ref.dest
                if os.path.exists(target) and _same_file(ref.resolved, target):
                    skipped += 1
                else:
                    target = (target if not os.path.exists(target)
                              else _unique_dest(target))
                    shutil.copy2(ref.resolved, target)
                    ref.dest = target
                    copied += 1
        except (OSError, IOError) as exc:
            errors.append("{}  copy failed: {}".format(ref.node_path, exc))
            continue

        if repoint:
            try:
                new_value = ref.dest_relative()
                if ref.is_seq:
                    # Keep the original frame token, only swap the directory.
                    token = os.path.basename(ref.raw.replace("\\", "/"))
                    new_value = "{}/{}/{}".format(
                        root_token(ref.root, ref.prefer_var),
                        ref.subfolder, token)
                ref.parm.set(new_value)
            except hou.PermissionError as exc:
                errors.append("{}  locked, not repointed: {}".format(
                    ref.node_path, exc))
            except Exception as exc:
                errors.append("{}  repoint failed: {}".format(
                    ref.node_path, exc))

    return copied, skipped, errors


# ---------------------------------------------------------------------------
# Re-tokenising paths that are already inside the project
# ---------------------------------------------------------------------------

def leading_var(raw):
    """
    The variable a path starts with, e.g. "$HIP" for "$HIP/tex/a.exr".

    Returns "" for a bare absolute path. Used to tell an already-relative
    path from a hard-coded one -- only the former gets re-tokenised.
    """
    raw = (raw or "").strip().replace("\\", "/")
    match = re.match(r"^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?(?=/|$)", raw)
    return "$" + match.group(1).upper() if match else ""


def find_internal(root):
    """
    File parameters inside the project that already use a variable.

    Bare absolute paths are deliberately excluded: turning a hard-coded path
    into a variable is a different decision from swapping one variable for
    another, and doing it silently would rewrite paths the user never asked
    to touch.
    """
    root = _clean(root)
    found = []

    for parm in _iter_file_parms():
        try:
            raw = parm.unexpandedString()
        except Exception:
            continue
        if not raw or not raw.strip():
            continue
        try:
            if parm.keyframes():
                continue
        except Exception:
            pass
        try:
            resolved = _clean(parm.eval())
        except Exception:
            continue
        if not resolved or resolved.startswith(("op:", "http:", "https:",
                                                "opdef:")):
            continue
        if not os.path.isabs(resolved):
            continue
        if not is_inside(resolved, root):
            continue
        if not leading_var(raw):
            continue  # hard-coded path, not ours to re-tokenise
        found.append((parm, raw, resolved))

    return found


def retoken_paths(root, target_var, progress=None):
    """
    Rewrite already-relative internal paths to use `target_var`.

    Only paths that already start with a variable are touched -- a $JOB path
    becomes a $HIP one. Hard-coded absolute paths are left alone.

    The new value is rebuilt from the resolved location rather than by
    string-replacing the old token, so any variable converges on the target.

    Returns (changed, skipped, errors).
    """
    root = _clean(root)
    token = normalise_var(target_var)

    if not var_is_usable(token, root):
        return 0, 0, ["{} does not point at {} -- nothing changed.".format(
            token or "That variable", root)]

    entries = find_internal(root)
    changed = 0
    skipped = 0
    errors = []

    for index, (parm, raw, resolved) in enumerate(entries):
        if progress is not None and not progress(index, len(entries), parm):
            errors.append("Cancelled by user.")
            break

        # The path below the root, e.g. "tex/wood.exr".
        relative = resolved[len(root):].lstrip("/")
        if not relative:
            skipped += 1
            continue

        # Keep whatever frame token the original used -- resolved has it
        # already expanded to a concrete frame.
        tail = os.path.basename(raw.replace("\\", "/"))
        if is_sequence(raw) and tail:
            relative = "/".join(relative.split("/")[:-1] + [tail])

        new_value = "{}/{}".format(token, relative)
        if new_value == raw:
            skipped += 1
            continue

        try:
            parm.set(new_value)
            changed += 1
        except hou.PermissionError as exc:
            errors.append("{} locked: {}".format(parm.node().path(), exc))
        except Exception as exc:
            errors.append("{}: {}".format(parm.node().path(), exc))

    return changed, skipped, errors


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def _human(size):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return "{:.0f} {}".format(size, unit) if unit == "B" \
                else "{:.1f} {}".format(size, unit)
        size /= 1024.0
    return "{:.1f} PB".format(size)


# ---------------------------------------------------------------------------
# Colour coding
# ---------------------------------------------------------------------------

# Source drive -> tint for the "Current path" cell. Assigned in first-seen
# order so any drive letter gets a stable colour, not just known ones.
DRIVE_COLOURS = [
    "#6bb3ff",  # blue
    "#ffb86b",  # orange
    "#7ee787",  # green
    "#d2a8ff",  # purple
    "#ff9ec4",  # pink
    "#5fd7d7",  # teal
    "#e3d16b",  # yellow
]

# Destination subfolder -> tint for the "Will be copied to" cell.
TYPE_COLOURS = {
    "tex":  "#7ee787",
    "geo":  "#ffb86b",
    "abc":  "#d2a8ff",
    "misc": "#9aa0a6",
}

MISSING_COLOUR = "#ff6b6b"


def drive_of(path):
    """Return a label for the volume a path lives on: 'E:' or '//server/share'."""
    path = (path or "").replace("\\", "/")
    if path.startswith("//"):
        parts = path.split("/")
        return "//" + "/".join(parts[2:4]) if len(parts) >= 4 else path
    drive = os.path.splitdrive(path)[0]
    return drive.upper() if drive else "?"


(COL_ON, COL_NODE, COL_EXT, COL_FILE, COL_LOCATION, COL_FILES, COL_SIZE,
 COL_DEST) = range(8)

class SortableItem(QtWidgets.QTableWidgetItem):
    """
    A cell that sorts on a supplied key rather than its displayed text.

    Without this, Size would sort as a string -- "9.0 MB" landing between
    "8.3 KB" and "99.7 KB" -- and the file count would put "seq 10" before
    "seq 9".
    """

    def __init__(self, text, key=None):
        super(SortableItem, self).__init__(text)
        self._key = text if key is None else key

    def __lt__(self, other):
        if isinstance(other, SortableItem):
            try:
                return self._key < other._key
            except TypeError:
                return str(self._key) < str(other._key)
        return super(SortableItem, self).__lt__(other)


CHECK_COL_W = 28    # checkbox column, always this wide
MIN_COL_W = 90      # a wide column never shrinks below this


class ConsolidatorDialog(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super(ConsolidatorDialog, self).__init__(parent)
        self.setWindowTitle("Consolidate Assets  v{}".format(VERSION))
        self.resize(1100, 620)
        self.setWindowFlags(self.windowFlags() |
                            Qt.WindowMinMaxButtonsHint)

        self.refs = []
        self._drive_map = {}   # drive label -> colour, stable per session
        self._suppress_fit_all = False  # guards the double-signal above
        self._did_initial_fit = False
        self._user_sized = False    # true once a column is dragged
        self._applying_fit = False  # guards our own width changes
        self._build_ui()
        self.refresh()

    def showEvent(self, event):
        """
        Fit the columns the first time the dialog is actually shown. Doing it
        in __init__ measures a viewport that has not been laid out yet, which
        is how the paths ended up truncated with dead space to the right.
        """
        super(ConsolidatorDialog, self).showEvent(event)
        if not self._did_initial_fit and self.refs:
            self._did_initial_fit = True
            QtCore.QTimer.singleShot(0, self.fit_columns)

    def resizeEvent(self, event):
        """
        Re-budget the columns when the window is resized, but only while the
        user has not resized a column themselves -- otherwise a window resize
        would throw away widths they set by hand.
        """
        super(ConsolidatorDialog, self).resizeEvent(event)
        if self._did_initial_fit and self.refs and not self._user_sized:
            QtCore.QTimer.singleShot(0, self.fit_columns)

    def _on_section_resized(self, _index, _old, _new):
        """Mark the columns as user-owned once one is dragged by hand."""
        if not self._applying_fit:
            self._user_sized = True

    # -- construction -------------------------------------------------------

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)

        # Project root row
        root_row = QtWidgets.QHBoxLayout()
        root_row.addWidget(QtWidgets.QLabel("Project root:"))
        self.root_field = QtWidgets.QLineEdit(project_root())
        self.root_field.setToolTip(
            "Files outside this folder are treated as external.")
        root_row.addWidget(self.root_field, 1)
        browse = QtWidgets.QPushButton("Browse...")
        browse.clicked.connect(self._browse_root)
        root_row.addWidget(browse)
        rescan = QtWidgets.QPushButton("Rescan")
        rescan.clicked.connect(self.refresh)
        root_row.addWidget(rescan)
        layout.addLayout(root_row)

        # Which variable to write into repointed paths. Editable, so a studio
        # variable can be typed rather than only $HIP or $JOB.
        var_row = QtWidgets.QHBoxLayout()
        var_row.addWidget(QtWidgets.QLabel("Use variable:"))

        self.var_box = QtWidgets.QComboBox()
        self.var_box.setEditable(True)
        self.var_box.addItems(COMMON_VARS)
        self.var_box.setFixedWidth(140)
        self.var_box.setToolTip(
            "The variable written into consolidated paths.\n"
            "Any Houdini variable can be typed, not just these two.")
        var_row.addWidget(self.var_box)

        self.var_status = QtWidgets.QLabel("")
        var_row.addWidget(self.var_status, 1)

        self.update_btn = QtWidgets.QPushButton("Update paths in scene")
        self.update_btn.setToolTip(
            "Rewrite paths that already use a variable and point inside\n"
            "the project so they use this one instead. Copies nothing,\n"
            "and leaves hard-coded absolute paths alone.")
        self.update_btn.clicked.connect(self._retoken)
        var_row.addWidget(self.update_btn)
        layout.addLayout(var_row)

        # Table
        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["", "Node", "Type", "Current path", "Location", "Files", "Size",
             "Will be copied to"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(-1, Qt.AscendingOrder)
        self.table.setWordWrap(False)
        # Elide in the middle: the right end of a path holds the filename,
        # which is exactly what you need to keep when space is short.
        self.table.setTextElideMode(Qt.ElideMiddle)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemDoubleClicked.connect(self._on_double_click)

        # Right-click menu on rows.
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)

        # Every column drag-resizable (Excel style). Interactive rather than
        # Stretch, otherwise the user cannot drag them at all.
        header = self.table.horizontalHeader()
        for col in range(8):
            header.setSectionResizeMode(col, QtWidgets.QHeaderView.Interactive)
        # Off: it would override manual dragging of the last column.
        header.setStretchLastSection(False)
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        # Double-click a header divider to size that column to its contents;
        # double-click anywhere else on the header to fit every column.
        header.sectionHandleDoubleClicked.connect(self._fit_column)
        header.sectionResized.connect(self._on_section_resized)
        header.sectionDoubleClicked.connect(self._header_double_clicked)

        # Starting widths. Replaced by a real fit once rows exist -- with an
        # empty table there is nothing to measure.
        for col, width in ((COL_ON, CHECK_COL_W), (COL_NODE, 230),
                           (COL_EXT, 55), (COL_FILE, 330), (COL_LOCATION, 110),
                           (COL_FILES, 55), (COL_SIZE, 75), (COL_DEST, 300)):
            self.table.setColumnWidth(col, width)
        layout.addWidget(self.table, 1)

        # Selection buttons
        sel_row = QtWidgets.QHBoxLayout()
        for label, slot in (("Select recommended", self._select_recommended),
                            ("Select all", self._select_all),
                            ("Select none", self._select_none),
                            ("Invert", self._select_invert)):
            btn = QtWidgets.QPushButton(label)
            btn.clicked.connect(slot)
            sel_row.addWidget(btn)

        sel_row.addSpacing(16)
        self.hide_missing = QtWidgets.QCheckBox("Hide missing files")
        self.hide_missing.stateChanged.connect(self.refresh)
        sel_row.addWidget(self.hide_missing)

        self.repoint_box = QtWidgets.QCheckBox(
            "Repoint parameters to relative paths")
        self.repoint_box.setToolTip(
            "Rewrites each parameter to point at the consolidated copy.")
        self.repoint_box.setChecked(True)
        sel_row.addWidget(self.repoint_box)

        sel_row.addStretch(1)
        self.legend = QtWidgets.QLabel("")
        self.legend.setTextFormat(Qt.RichText)
        self.legend.setToolTip(
            "Source paths are tinted per drive, destinations per type folder.")
        sel_row.addWidget(self.legend)
        layout.addLayout(sel_row)

        # Status + action
        bottom = QtWidgets.QHBoxLayout()
        self.status = QtWidgets.QLabel("")
        bottom.addWidget(self.status, 1)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        bottom.addWidget(close_btn)

        self.go_btn = QtWidgets.QPushButton("Consolidate Assets")
        self.go_btn.setDefault(True)
        self.go_btn.setMinimumWidth(170)
        self.go_btn.clicked.connect(self._run)
        bottom.addWidget(self.go_btn)
        layout.addLayout(bottom)

        # Connected last: addItems() above would otherwise fire the handler
        # before var_status and repoint_box exist.
        self.var_box.currentTextChanged.connect(self._on_var_changed)
        self._on_var_changed(self.var_box.currentText())

    # -- population ---------------------------------------------------------

    def current_var(self):
        """The variable the user picked, normalised to "$NAME" form."""
        return normalise_var(self.var_box.currentText())

    def _on_var_changed(self, _text):
        """Report whether the typed variable actually points at the root."""
        var = self.current_var()
        root = _clean(self.root_field.text())
        value = var_value(var)

        if not var:
            self.var_status.setText("")
            self.update_btn.setEnabled(False)
        elif not value:
            self.var_status.setText(
                "<span style='color:#ff6b6b'>{} is not set</span>".format(var))
            self.update_btn.setEnabled(False)
        elif value.lower() != root.lower():
            self.var_status.setText(
                "<span style='color:#ffb86b'>{} points at {}</span>".format(
                    var, value))
            self.update_btn.setEnabled(False)
        else:
            self.var_status.setText(
                "<span style='color:#7ee787'>{} = {}</span>".format(var, value))
            self.update_btn.setEnabled(True)

        # Destinations are shown with this token, so redraw them. Block
        # signals and sorting first: setText would otherwise fire
        # itemChanged and, with sorting on, reorder rows mid-update.
        for ref in self.refs:
            ref.prefer_var = var

        self.table.blockSignals(True)
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        try:
            for row in range(self.table.rowCount()):
                ref = self._ref_at(row)
                item = self.table.item(row, COL_DEST)
                if ref is not None and item is not None:
                    item.setText(ref.dest_relative())
                    item.setToolTip(
                        "Type folder: {}\nAbsolute:\n{}".format(
                            ref.subfolder, ref.dest))
        finally:
            self.table.setSortingEnabled(was_sorting)
            self.table.blockSignals(False)

        self._update_repoint_label()

    def _retoken(self):
        """Swap the variable on every path already inside the project."""
        var = self.current_var()
        root = _clean(self.root_field.text())

        entries = find_internal(root)
        pending = [e for e in entries if leading_var(e[1]) != var]
        if not pending:
            if entries:
                hou.ui.displayMessage(
                    "All {} relative path(s) already use {}.".format(
                        len(entries), var))
            else:
                hou.ui.displayMessage(
                    "No paths using a variable point inside the project." 
                    " Hard-coded absolute paths are left alone.")
            return

        confirm = QtWidgets.QMessageBox.question(
            self, "Update paths in scene",
            "Rewrite {} path(s) to use {}?\n\n"
            "These already use a variable and point inside the project. "
            "No files are copied or moved, and hard-coded absolute "
            "paths are left alone.".format(len(pending), var),
            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        if confirm != QtWidgets.QMessageBox.Ok:
            return

        dialog = QtWidgets.QProgressDialog(
            "Updating paths...", "Cancel", 0, len(pending), self)
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)

        def progress(index, total, parm):
            dialog.setValue(index)
            dialog.setLabelText(parm.node().path())
            QtWidgets.QApplication.processEvents()
            return not dialog.wasCanceled()

        with hou.undos.group("Update paths to {}".format(var)):
            changed, skipped, errors = retoken_paths(root, var, progress)
        dialog.setValue(len(pending))

        summary = "Updated {} path(s) to {}.".format(changed, var)
        if skipped:
            summary += "\n{} already correct.".format(skipped)
        if errors:
            summary += "\n\n{} problem(s):\n{}".format(
                len(errors), "\n".join(errors[:12]))
            QtWidgets.QMessageBox.warning(self, "Update paths", summary)
        else:
            QtWidgets.QMessageBox.information(self, "Update paths", summary)

        self.refresh()

    def _browse_root(self):
        start = self.root_field.text() or project_root()
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose project root", start)
        if chosen:
            self.root_field.setText(_clean(chosen))
            self.refresh()

    def refresh(self):
        root = _clean(self.root_field.text())
        if not root:
            self.refs = []
            self._populate()
            self.status.setText(
                "No project root. Save the scene first.")
            return

        with hou.InterruptableOperation("Scanning scene", open_interrupt_dialog=False):
            self.refs = scan(
                root,
                include_missing=not self.hide_missing.isChecked(),
                prefer_var=self.current_var())
        self._populate()

    def _drive_colour(self, drive):
        """Stable colour per source volume, assigned in first-seen order."""
        if drive not in self._drive_map:
            index = len(self._drive_map) % len(DRIVE_COLOURS)
            self._drive_map[drive] = DRIVE_COLOURS[index]
        return self._drive_map[drive]

    def fit_columns(self):
        """
        Size every column to fit the window.

        Natural widths alone do not work: one long path wants ~1200px and
        pushes later columns off screen. Sharing the shortfall in proportion
        to natural width does not work either, because the Node column then
        keeps space it does not need while the paths -- the columns you
        actually read -- get squeezed to nothing.

        So: narrow columns take what they need, Node is capped at something
        sensible, and whatever is left goes to the two path columns.
        """
        table = self.table
        self._applying_fit = True
        try:
            self._fit_columns_inner(table)
        finally:
            self._applying_fit = False

    def _fit_columns_inner(self, table):
        table.resizeColumnsToContents()
        table.setColumnWidth(COL_ON, CHECK_COL_W)

        for col in (COL_EXT, COL_LOCATION, COL_FILES, COL_SIZE):
            table.setColumnWidth(col, table.columnWidth(col) + 10)

        viewport = table.viewport().width()
        if viewport <= 0:
            return

        fixed = sum(table.columnWidth(c)
                    for c in (COL_ON, COL_EXT, COL_LOCATION, COL_FILES, COL_SIZE))

        # Node rarely needs more than a quarter of the window, and on a
        # narrow one it has to give way further so both path columns stay
        # readable -- node paths elide far better than file paths do.
        node_natural = table.columnWidth(COL_NODE)
        ratio = 0.26 if viewport >= 1500 else 0.20
        node_cap = max(MIN_COL_W, int(viewport * ratio))
        node = min(node_natural, node_cap)

        available = viewport - fixed - node - 4
        path_natural = table.columnWidth(COL_FILE)
        dest_natural = table.columnWidth(COL_DEST)
        wanted = path_natural + dest_natural

        if wanted <= available:
            # Everything fits: give Node back any slack the paths do not use.
            node = min(node_natural, node + (available - wanted))
            table.setColumnWidth(COL_NODE, node)
            table.setColumnWidth(COL_FILE, path_natural)
            table.setColumnWidth(COL_DEST, dest_natural)
            return

        if available < MIN_COL_W * 2:
            # Very narrow window: give the paths the floor and let Node go.
            node = max(MIN_COL_W, viewport - fixed - MIN_COL_W * 2 - 4)
            available = max(MIN_COL_W * 2, viewport - fixed - node - 4)

        # Split the remaining space between source and destination in
        # proportion to what each wants, with a floor on both.
        share = path_natural / float(wanted) if wanted else 0.5
        # Cap the source column's share so a very long source path cannot
        # starve the destination, which the user needs to verify.
        share = min(share, 0.62)
        path_w = max(MIN_COL_W, int(available * share))
        dest_w = max(MIN_COL_W, available - path_w)

        table.setColumnWidth(COL_NODE, node)
        table.setColumnWidth(COL_FILE, path_w)
        table.setColumnWidth(COL_DEST, dest_w)

    def _header_double_clicked(self, _index):
        """
        Double-click on the header body fits every column. Qt can emit this
        alongside sectionHandleDoubleClicked when the click lands on a
        divider, so ignore it if _fit_column just ran.
        """
        if self._suppress_fit_all:
            self._suppress_fit_all = False
            return
        self.fit_columns()

    def _fit_column(self, index):
        """
        Double-click on a header divider fits just that column, capped so one
        long path cannot take over the whole window.
        """
        self._suppress_fit_all = True
        table = self.table
        table.resizeColumnToContents(index)

        if index == COL_ON:
            table.setColumnWidth(COL_ON, CHECK_COL_W)
            return

        cap = max(MIN_COL_W, int(table.viewport().width() * 0.45))
        if table.columnWidth(index) > cap:
            table.setColumnWidth(index, cap)

    def _populate(self):
        self.table.blockSignals(True)

        # Qt re-sorts after every setItem while sorting is on, which would
        # interleave rows mid-fill. Remember the sort, fill unsorted, then
        # re-apply it so a rescan keeps the order the user chose.
        header = self.table.horizontalHeader()
        sort_col = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        was_sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)

        self.table.setRowCount(0)

        for ref in self.refs:
            row = self.table.rowCount()
            self.table.insertRow(row)

            check = QtWidgets.QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled |
                           Qt.ItemIsSelectable)
            check.setCheckState(Qt.Checked if ref.selected else Qt.Unchecked)
            # Carry the reference on the row itself. Once the table can be
            # sorted, row number no longer matches the index in self.refs.
            check.setData(Qt.UserRole, ref)
            self.table.setItem(row, COL_ON, check)

            node_item = QtWidgets.QTableWidgetItem(ref.node_path)
            node_item.setToolTip(
                "{}\nparameter: {}\n\nDouble-click to jump to this node.".format(
                    ref.node_path, ref.parm_name))
            self.table.setItem(row, COL_NODE, node_item)

            # File type, coloured per extension.
            ext_item = QtWidgets.QTableWidgetItem(ref.ext_label)
            ext_item.setTextAlignment(Qt.AlignCenter)
            ext_item.setForeground(QtGui.QColor(ext_colour(ref.ext_label)))
            ext_item.setToolTip("Routed to the {} folder".format(ref.subfolder))
            self.table.setItem(row, COL_EXT, ext_item)

            # Source path, tinted per drive.
            path_item = QtWidgets.QTableWidgetItem(ref.resolved)
            drive = drive_of(ref.resolved)
            path_item.setForeground(QtGui.QColor(self._drive_colour(drive)))
            path_item.setToolTip("Drive: {}\nParameter value:\n{}".format(
                drive, ref.raw))
            self.table.setItem(row, COL_FILE, path_item)

            location_item = QtWidgets.QTableWidgetItem(ref.location)
            location_item.setForeground(QtGui.QColor(
                PICK_COLOURS.get(ref.location, DEFAULT_EXT_COLOUR)))
            location_item.setToolTip(LOCATION_HELP.get(ref.location, ref.location))
            self.table.setItem(row, COL_LOCATION, location_item)

            count = "seq {}".format(ref.file_count) if ref.is_seq \
                else ("1" if ref.exists else "missing")
            count_item = SortableItem(count, ref.file_count)
            count_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, COL_FILES, count_item)

            size_item = SortableItem(
                _human(ref.size_bytes) if ref.exists else "-",
                ref.size_bytes)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, COL_SIZE, size_item)

            # Destination, tinted per type folder.
            dest_item = QtWidgets.QTableWidgetItem(ref.dest_relative())
            dest_item.setForeground(QtGui.QColor(
                TYPE_COLOURS.get(ref.subfolder, TYPE_COLOURS["misc"])))
            dest_item.setToolTip("Type folder: {}\nAbsolute:\n{}".format(
                ref.subfolder, ref.dest))
            self.table.setItem(row, COL_DEST, dest_item)

            # Missing files override every other colour and cannot be selected.
            if not ref.exists:
                missing = QtGui.QColor(MISSING_COLOUR)
                for col in (COL_NODE, COL_EXT, COL_FILE, COL_LOCATION,
                            COL_FILES, COL_DEST):
                    self.table.item(row, col).setForeground(missing)
                path_item.setToolTip(
                    "FILE NOT FOUND ON DISK\n{}".format(ref.resolved))
                check.setCheckState(Qt.Unchecked)
                ref.selected = False

        if was_sorting:
            self.table.setSortingEnabled(True)
            if sort_col >= 0:
                self.table.sortByColumn(sort_col, sort_order)

        self.table.blockSignals(False)
        self._update_status()

        # The first fit is deferred to showEvent: until the dialog is on
        # screen the viewport has no meaningful width to budget against.

    # -- context menu -------------------------------------------------------

    def _ref_at(self, row):
        """
        The reference shown on a given row. Rows are reordered by sorting,
        so never index self.refs by row number -- go through here.
        """
        item = self.table.item(row, COL_ON)
        return item.data(Qt.UserRole) if item is not None else None

    def _selected_rows(self):
        return sorted({idx.row() for idx in self.table.selectedIndexes()})

    def _set_rows(self, rows, state):
        self.table.blockSignals(True)
        for row in rows:
            ref = self._ref_at(row)
            if ref is None:
                continue
            if state and not ref.exists:
                continue  # never tick something that is not on disk
            ref.selected = state
            self.table.item(row, COL_ON).setCheckState(
                Qt.Checked if state else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_status()

    def _isolate_rows(self, rows):
        """
        Clear every tick, then select just these rows. This is what the menu
        actions do: choosing "these 3 rows" means those and nothing else.
        """
        self.table.blockSignals(True)
        wanted = set(rows)
        for row in range(self.table.rowCount()):
            ref = self._ref_at(row)
            if ref is None:
                continue
            state = row in wanted and ref.exists
            ref.selected = state
            self.table.item(row, COL_ON).setCheckState(
                Qt.Checked if state else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_status()

    def _rows_where(self, predicate):
        rows = []
        for row in range(self.table.rowCount()):
            ref = self._ref_at(row)
            if ref is not None and predicate(ref):
                rows.append(row)
        return rows

    def _context_menu(self, pos):
        item = self.table.itemAt(pos)
        rows = self._selected_rows()

        # Right-clicking a row that is not part of the selection acts on the
        # row under the cursor, which is what every file manager does.
        if item is not None and item.row() not in rows:
            rows = [item.row()]
            self.table.selectRow(item.row())

        menu = QtWidgets.QMenu(self)
        ref = self._ref_at(item.row()) if item is not None else None

        # The consolidate actions come first: they are what the tool is for,
        # and they act immediately on what you clicked rather than changing
        # the tick boxes.
        if ref is not None:
            act_one = menu.addAction("Consolidate this file now")
            act_one.setEnabled(ref.exists)
            act_one.triggered.connect(lambda: self._consolidate_refs(
                [ref], "Consolidate this file"))

            if len(rows) > 1:
                chosen = [self._ref_at(r) for r in rows]
                chosen = [r for r in chosen if r is not None and r.exists]
                act_these = menu.addAction(
                    "Consolidate these {} files now".format(len(chosen)))
                act_these.setEnabled(bool(chosen))
                act_these.triggered.connect(lambda: self._consolidate_refs(
                    chosen, "Consolidate selected files"))
            menu.addSeparator()

        if rows:
            count = len(rows)
            plural = "s" if count != 1 else ""

            act_only = menu.addAction(
                "Select only {} row{}".format(count, plural))
            act_only.triggered.connect(lambda: self._isolate_rows(rows))

            act_add = menu.addAction("Add to selection")
            act_add.triggered.connect(lambda: self._set_rows(rows, True))

            act_off = menu.addAction("Deselect {} row{}".format(count, plural))
            act_off.triggered.connect(lambda: self._set_rows(rows, False))
            menu.addSeparator()

        if ref is not None:
            drive = drive_of(ref.resolved)
            folder = os.path.dirname(ref.resolved)
            label = ref.ext_label

            act_drive = menu.addAction("Select only what is on {}".format(drive))
            act_drive.triggered.connect(lambda: self._isolate_rows(
                self._rows_where(lambda r: drive_of(r.resolved) == drive)))

            act_ext = menu.addAction("Select only {} files".format(label))
            act_ext.triggered.connect(lambda: self._isolate_rows(
                self._rows_where(lambda r: r.ext_label == label)))

            act_location = menu.addAction(
                'Select only "{}"'.format(ref.location))
            act_location.triggered.connect(lambda: self._isolate_rows(
                self._rows_where(lambda r: r.location == ref.location)))

            act_folder = menu.addAction("Select only this folder")
            act_folder.triggered.connect(lambda: self._isolate_rows(
                self._rows_where(
                    lambda r: os.path.dirname(r.resolved) == folder)))
            menu.addSeparator()

            act_copy = menu.addAction("Copy path")
            act_copy.triggered.connect(
                lambda: QtWidgets.QApplication.clipboard().setText(
                    ref.resolved))
            act_open = menu.addAction("Open with default app")
            act_open.setEnabled(ref.exists)
            act_open.triggered.connect(lambda: self._open_file(ref))

            act_show = menu.addAction("Show in Explorer")
            act_show.triggered.connect(lambda: self._reveal(ref))
            menu.addSeparator()

        act_all = menu.addAction("Select all")
        act_all.triggered.connect(self._select_all)
        act_none = menu.addAction("Select none")
        act_none.triggered.connect(self._select_none)
        menu.addSeparator()
        act_fit = menu.addAction("Fit columns to contents")
        act_fit.triggered.connect(self.fit_columns)

        # PySide2 spells it exec_, PySide6 exec.
        where = self.table.viewport().mapToGlobal(pos)
        if hasattr(menu, "exec_"):
            menu.exec_(where)
        else:
            menu.exec(where)
    def _open_file(self, ref):
        """
        Open the file in whatever the OS has associated with its type. For a
        sequence this opens the first frame on disk, matching Show in
        Explorer.
        """
        target = ref.frames[0] if (ref.is_seq and ref.frames) else ref.resolved
        target = os.path.normpath(target)

        if not os.path.exists(target):
            hou.ui.displayMessage(
                "File not found:\n{}".format(target),
                severity=hou.severityType.Warning)
            return

        try:
            if sys.platform == "win32":
                os.startfile(target)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as exc:
            hou.ui.displayMessage(
                "Could not open the file:\n{}\n\n{}".format(target, exc),
                severity=hou.severityType.Error)

    def _reveal(self, ref):
        target = ref.frames[0] if (ref.is_seq and ref.frames) else ref.resolved
        target = os.path.normpath(target)
        try:
            if os.path.exists(target):
                subprocess.Popen(["explorer", "/select,", target])
            else:
                folder = os.path.dirname(target)
                if os.path.isdir(folder):
                    subprocess.Popen(["explorer", folder])
        except Exception:
            pass

    # -- interaction --------------------------------------------------------

    def _on_item_changed(self, item):
        if item.column() != COL_ON:
            return
        ref = self._ref_at(item.row())
        if ref is not None:
            ref.selected = (item.checkState() == Qt.Checked)
            self._update_status()

    def _on_double_click(self, item):
        ref = self._ref_at(item.row())
        if ref is None:
            return
        node = ref.parm.node()
        try:
            node.setCurrent(True, clear_all_selected=True)
            for pane in hou.ui.paneTabs():
                if pane.type() == hou.paneTabType.NetworkEditor:
                    pane.cd(node.parent().path())
                    pane.homeToSelection()
                    break
        except Exception:
            pass

    def _set_all(self, state):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            ref = self._ref_at(row)
            if ref is None:
                continue
            if state and not ref.exists:
                continue  # never auto-select something that isn't there
            ref.selected = state
            self.table.item(row, COL_ON).setCheckState(
                Qt.Checked if state else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_status()

    def _select_recommended(self):
        """Tick exactly the references worth consolidating."""
        self._isolate_rows(self._rows_where(lambda r: r.recommend))

    def _select_all(self):
        self._set_all(True)

    def _select_none(self):
        self._set_all(False)

    def _select_invert(self):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            ref = self._ref_at(row)
            if ref is None:
                continue
            flipped = not ref.selected
            if flipped and not ref.exists:
                continue
            ref.selected = flipped
            self.table.item(row, COL_ON).setCheckState(
                Qt.Checked if flipped else Qt.Unchecked)
        self.table.blockSignals(False)
        self._update_status()

    def _update_repoint_label(self):
        """Name the token that will actually be written, not a guess."""
        token = root_token(_clean(self.root_field.text()),
                           self.current_var())
        if token.startswith("$"):
            self.repoint_box.setText(
                "Repoint parameters to {}-relative paths".format(token))
        elif token:
            self.repoint_box.setText(
                "Repoint parameters to absolute paths under the project")
        else:
            self.repoint_box.setText("Repoint parameters")

    def _update_legend(self):
        """Drive colours on the left, the extensions actually present after."""
        chunks = []
        for drive, colour in self._drive_map.items():
            chunks.append(
                '<span style="color:{}">&#9632;</span> {}'.format(
                    colour, drive))

        seen = []
        for ref in self.refs:
            if ref.ext_label not in seen:
                seen.append(ref.ext_label)
        for label in seen[:8]:
            chunks.append(
                '<span style="color:{}">&#9632;</span> {}'.format(
                    ext_colour(label), label))

        if any(not r.exists for r in self.refs):
            chunks.append(
                '<span style="color:{}">&#9632;</span> missing'.format(
                    MISSING_COLOUR))
        self.legend.setText("&nbsp;&nbsp;".join(chunks))

    def _update_status(self):
        self._update_repoint_label()
        self._update_legend()
        chosen = [r for r in self.refs if r.selected]
        missing = len([r for r in self.refs if not r.exists])
        files = sum(r.file_count for r in chosen)
        size = sum(r.size_bytes for r in chosen)

        if not self.refs:
            self.status.setText(
                "No external file references found. Everything is already "
                "inside the project.")
        else:
            recommended = len([r for r in self.refs if r.recommend])
            msg = "{} external reference(s), {} recommended   |   {} " \
                  "selected, {} file(s), {}".format(
                      len(self.refs), recommended, len(chosen), files,
                      _human(size))
            if missing:
                msg += "   |   {} missing on disk".format(missing)
            self.status.setText(msg)

        self.go_btn.setEnabled(bool(chosen))

    # -- run ----------------------------------------------------------------

    def _run(self):
        chosen = [r for r in self.refs if r.selected]
        if chosen:
            self._consolidate_refs(chosen, "Consolidate Assets")

    def _consolidate_refs(self, refs, title):
        """
        Copy and repoint a specific set of references. Shared by the main
        button and the right-click "consolidate this file" actions, so both
        get the same confirmation, progress and reporting.
        """
        refs = [r for r in refs if r.exists]
        if not refs:
            return

        root = _clean(self.root_field.text())
        files = sum(r.file_count for r in refs)
        size = _human(sum(r.size_bytes for r in refs))

        if self.repoint_box.isChecked():
            note = "Parameters will be repointed to {}-relative paths.".format(
                root_token(root, self.current_var()))
        else:
            note = "Parameters will NOT be changed."

        if len(refs) == 1:
            what = os.path.basename(refs[0].resolved)
            if refs[0].is_seq:
                what += "  ({} frames)".format(refs[0].file_count)
        else:
            what = "{} file(s) ({})".format(files, size)

        confirm = QtWidgets.QMessageBox.question(
            self, title,
            "Copy {} into:\n{}\n\n{}".format(what, root, note),
            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        if confirm != QtWidgets.QMessageBox.Ok:
            return

        dialog = QtWidgets.QProgressDialog(
            "Consolidating...", "Cancel", 0, len(refs), self)
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)

        def progress(index, total, ref):
            dialog.setValue(index)
            dialog.setLabelText("{}\n{}".format(
                ref.node_path, os.path.basename(ref.resolved)))
            QtWidgets.QApplication.processEvents()
            return not dialog.wasCanceled()

        with hou.undos.group(title):
            copied, skipped, errors = consolidate(
                refs, repoint=self.repoint_box.isChecked(),
                progress=progress)
        dialog.setValue(len(refs))

        summary = "Copied {} file(s).".format(copied)
        if skipped:
            summary += "\n{} already present and identical, skipped.".format(
                skipped)
        if errors:
            summary += "\n\n{} problem(s):\n{}".format(
                len(errors), "\n".join(errors[:12]))
            if len(errors) > 12:
                summary += "\n... and {} more.".format(len(errors) - 12)
            QtWidgets.QMessageBox.warning(self, title, summary)
        else:
            QtWidgets.QMessageBox.information(self, title, summary)

        self.refresh()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_dialog = None


def main(kwargs=None):
    global _dialog

    if hou.hipFile.path().endswith("untitled.hip") and not hou.getenv("JOB"):
        hou.ui.displayMessage(
            "Save the scene first so the project root can be "
            "determined.", severity=hou.severityType.Warning)
        return

    if _dialog is not None:
        try:
            _dialog.close()
            _dialog.deleteLater()
        except Exception:
            pass

    _dialog = ConsolidatorDialog(parent=hou.qt.mainWindow())
    _dialog.show()
    return _dialog
