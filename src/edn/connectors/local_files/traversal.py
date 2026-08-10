"""Durable, deterministic depth-first traversal cursor for approved roots."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from edn.connectors.local_files.config import ApprovedRoot

CURSOR_SCHEMA_VERSION = 1


class IncompatibleTraversalStateError(ValueError):
    """The saved cursor cannot safely describe the current source tree."""


class TraversalAccessError(OSError):
    """A directory could not be enumerated without exposing its path."""

    def __init__(self, error_type: str) -> None:
        super().__init__("directory enumeration failed")
        self.error_type = error_type


@dataclass(slots=True)
class _Frame:
    relative_path: str
    next_index: int
    device: int
    inode: int
    modified_ns: int


class DurableTraversal:
    """Traverse directory entries without replaying previously completed subtrees."""

    def __init__(
        self,
        roots: tuple[ApprovedRoot, ...],
        *,
        state: str | None = None,
    ) -> None:
        self.roots = tuple(sorted(roots, key=lambda item: item.root_id))
        self.root_index = 0
        self.frames: list[_Frame] = []
        if state is not None:
            self._restore(state)

    def next_path(self) -> tuple[ApprovedRoot, Path, int, bool] | None:
        while self.root_index < len(self.roots):
            root = self.roots[self.root_index]
            root_path = root.path.resolve(strict=True)
            root_device = root_path.stat().st_dev
            if not self.frames:
                self.frames.append(self._new_frame(root_path, root_path))
            frame = self.frames[-1]
            directory = root_path / frame.relative_path
            self._validate_frame(directory, frame)
            try:
                entries = sorted(os.scandir(directory), key=lambda item: item.name)
            except OSError as error:
                raise TraversalAccessError(type(error).__name__) from error
            if frame.next_index >= len(entries):
                self.frames.pop()
                if not self.frames:
                    self.root_index += 1
                continue
            entry = entries[frame.next_index]
            frame.next_index += 1
            path = Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                self.frames.append(self._new_frame(path, root_path))
                return root, path, root_device, True
            if frame.next_index == len(entries):
                self.frames.pop()
                if not self.frames:
                    self.root_index += 1
            return root, path, root_device, False
        return None

    @property
    def complete(self) -> bool:
        return self.root_index >= len(self.roots)

    def skip_current_directory(self) -> None:
        """Discard a just-entered child after connector policy rejects it."""
        if len(self.frames) < 2:
            raise RuntimeError("no child directory is available to skip")
        self.frames.pop()

    def skip_inaccessible_directory(self) -> None:
        if not self.frames:
            raise RuntimeError("no directory is available to skip")
        self.frames.pop()
        if not self.frames:
            self.root_index += 1

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": CURSOR_SCHEMA_VERSION,
                "root_ids": [root.root_id for root in self.roots],
                "root_index": self.root_index,
                "frames": [
                    {
                        "relative_path": frame.relative_path,
                        "next_index": frame.next_index,
                        "device": frame.device,
                        "inode": frame.inode,
                        "modified_ns": frame.modified_ns,
                    }
                    for frame in self.frames
                ],
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    def _restore(self, payload: str) -> None:
        try:
            value: object = json.loads(payload)
        except json.JSONDecodeError as error:
            raise IncompatibleTraversalStateError(
                "saved traversal cursor is invalid"
            ) from error
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != CURSOR_SCHEMA_VERSION
        ):
            raise IncompatibleTraversalStateError(
                "saved traversal cursor version is unsupported"
            )
        expected_roots = [root.root_id for root in self.roots]
        if value.get("root_ids") != expected_roots:
            raise IncompatibleTraversalStateError("saved traversal roots do not match")
        root_index = value.get("root_index")
        frames = value.get("frames")
        if not isinstance(root_index, int) or not isinstance(frames, list):
            raise IncompatibleTraversalStateError(
                "saved traversal cursor shape is invalid"
            )
        self.root_index = root_index
        self.frames = [self._decode_frame(item) for item in frames]
        if not 0 <= self.root_index <= len(self.roots):
            raise IncompatibleTraversalStateError(
                "saved traversal root index is invalid"
            )
        if self.frames and self.root_index >= len(self.roots):
            raise IncompatibleTraversalStateError(
                "completed traversal cannot retain frames"
            )
        if self.frames:
            root_path = self.roots[self.root_index].path.resolve(strict=True)
            for frame in self.frames:
                self._validate_frame(root_path / frame.relative_path, frame)

    @staticmethod
    def _decode_frame(value: object) -> _Frame:
        if not isinstance(value, dict):
            raise IncompatibleTraversalStateError("saved traversal frame is invalid")
        try:
            frame = _Frame(
                str(value["relative_path"]),
                int(value["next_index"]),
                int(value["device"]),
                int(value["inode"]),
                int(value["modified_ns"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise IncompatibleTraversalStateError(
                "saved traversal frame is invalid"
            ) from error
        if (
            frame.next_index < 0
            or Path(frame.relative_path).is_absolute()
            or ".." in Path(frame.relative_path).parts
        ):
            raise IncompatibleTraversalStateError(
                "saved traversal frame escapes its root"
            )
        return frame

    @staticmethod
    def _new_frame(path: Path, root: Path) -> _Frame:
        stat = path.stat()
        relative = path.relative_to(root)
        return _Frame(
            "." if not relative.parts else relative.as_posix(),
            0,
            stat.st_dev,
            stat.st_ino,
            stat.st_mtime_ns,
        )

    @staticmethod
    def _validate_frame(path: Path, frame: _Frame) -> None:
        try:
            stat = path.stat()
        except OSError as error:
            raise IncompatibleTraversalStateError(
                "saved traversal directory is unavailable"
            ) from error
        if (stat.st_dev, stat.st_ino, stat.st_mtime_ns) != (
            frame.device,
            frame.inode,
            frame.modified_ns,
        ):
            raise IncompatibleTraversalStateError("saved traversal directory changed")
