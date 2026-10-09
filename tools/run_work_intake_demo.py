"""Launch a synthetic-only local Work Intake demo; no live client is constructed."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8502)
    parser.add_argument("--initialise", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "src"))
    from edn.operations.intake_security import require_supported_platform

    try:
        require_supported_platform()
    except ValueError:
        parser.error(
            "Protected Work Intake requires Linux or WSL; no storage was opened"
        )
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a local port between 1024 and 65535")
    root = args.data_dir.absolute()
    if ".." in root.parts:
        parser.error("Select a data path without parent traversal segments")
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        parser.error("Synthetic runtime data must remain outside Git")
    from edn.operations.intake import IntakeStore
    from edn.operations.intake_attachments import IntakeAttachmentStore

    if args.initialise:
        from edn.operations.intake_security import AnchoredDirectory

        # A private existing parent is explicit; never mkdir through unknown paths.
        with (
            AnchoredDirectory(root.parent) as parent,
            parent.child(root.name, create=True) as directory,
        ):
            with directory.child("attachments", create=True):
                pass
            with directory.child("synthetic-sync", create=True):
                pass
        IntakeAttachmentStore(root / "attachments")
        IntakeStore(
            root / "requests.db", evidence_root=root / "attachments"
        ).initialise()
    if not (root / "requests.db").is_file():
        parser.error("Use --initialise once with a new synthetic-only data directory")
    IntakeStore(root / "requests.db", read_only=True).list_requests(limit=1)
    env = os.environ.copy()
    env["EDN_INTAKE_ROOT"] = str(root)
    env["PYTHONPATH"] = str(repo / "src")
    print(f"Synthetic Work Intake: http://127.0.0.1:{args.port}", flush=True)
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(repo / "src" / "edn" / "ui" / "work_intake_app.py"),
            "--server.address",
            "127.0.0.1",
            "--server.port",
            str(args.port),
            "--server.maxUploadSize",
            "20",
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
            "--client.toolbarMode",
            "minimal",
        ],
        env=env,
        cwd=repo,
    )


if __name__ == "__main__":
    raise SystemExit(main())
