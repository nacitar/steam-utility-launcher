from __future__ import annotations

import sys
from re import compile

from .github_release_updater import (
    ApplicationUpdater,
    ArchiveFormat,
    Asset,
    GitHubRepository,
)
from .steam import Process, Steam


def launch(*, steam: Steam | None = None) -> int:
    updater = ApplicationUpdater(
        name="DSR-Gadget",
        repository=GitHubRepository("DSR-Gadget", organization="JKAnderson"),
        assets=[
            Asset(
                pattern=compile(r"DSR\.Gadget(\.[0-9]+)+.zip"),
                archive_format=ArchiveFormat.ZIP,
                # destination=Path("."),
                strip_archive_components=1,
            )
        ],
        preserved_paths=set(),
    )
    install_directory = updater.default_install_directory
    gadget_path = [str(install_directory / "DSR-Gadget.exe")]
    if sys.platform.startswith("linux"):
        if not steam:
            raise AssertionError("steam context must be provided on linux!")
        processes = [steam.process_in_prefix(gadget_path, game_id="570940")]
    else:
        processes = [Process(gadget_path)]
    updater.update()
    updater.launch(processes, wait=True)

    return 0
