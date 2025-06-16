from __future__ import annotations

import os
import sys
from pathlib import Path
from re import compile

from .github_release_updater import (
    ApplicationUpdater,
    ArchiveFormat,
    Asset,
    GitHubRepository,
)
from .steam import Process, Steam


def launch(*, steam: Steam | None = None) -> int:
    env: dict[str, str] = os.environ.copy()
    env["PORT"] = "4747"
    domain = f"127.0.0.1:{env["PORT"]}"
    patcher_args = ["--headless", "--domain", domain]

    is_linux = sys.platform == "linux"
    if is_linux:
        suffix = "-linux"
    else:
        suffix = ""

    updater = ApplicationUpdater(
        name="Peacock",
        repository=GitHubRepository(
            "Peacock", organization="thepeacockproject"
        ),
        assets=[
            Asset(
                pattern=compile(rf"Peacock-v[^-]+\{suffix}.zip"),
                archive_format=ArchiveFormat.ZIP,
                # destination=Path("."),
                strip_archive_components=1,
            )
        ],
        preserved_paths={
            Path("userdata"),
            Path("contracts"),
            Path("contractSessions"),
        },
    )

    install_directory = updater.default_install_directory

    if is_linux:
        if not steam:
            raise AssertionError("steam context must be provided on linux!")
        processes: list[Process] = []
        game_id = "1659040"
        processes.append(
            steam.process_in_prefix(
                [str(install_directory / "PeacockPatcher.exe")] + patcher_args,
                game_id=game_id,
            )
        )
        processes.append(
            Process(["node", "chunk0.js"], env=env, cwd=install_directory)
        )
        wait = True
    else:
        processes = [
            Process([str(install_directory / "Start Server.cmd")], env=env),
            Process(
                [str(install_directory / "PeacockPatcher.exe")] + patcher_args
            ),
        ]
        wait = False
    updater.update()
    updater.launch(processes, wait=wait)

    return 0
