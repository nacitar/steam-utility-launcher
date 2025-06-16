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
    config_domain_line = f"CustomConfigDomain=127.0.0.1:{env["PORT"]}"

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
                [str(install_directory / "PeacockPatcher.exe")],
                game_id=game_id,
            )
        )
        game_wine_prefix = steam.game_wine_prefix(game_id=game_id)
        appdata_dir = (
            game_wine_prefix
            / "drive_c"
            / "users"
            / "steamuser"
            / "AppData"
            / "Roaming"
        )
        processes.append(
            Process(["node", "chunk0.js"], env=env, cwd=install_directory)
        )
        wait = True
    else:
        processes = [
            Process([str(install_directory / "Start Server.cmd")], env=env),
            Process([str(install_directory / "PeacockPatcher.exe")]),
        ]
        appdata_dir = Path(env["APPDATA"])
        wait = False
    patcher_config = appdata_dir / "PeacockProject" / "peacock_patcher2.conf"
    if not patcher_config.exists():
        patcher_config.parent.mkdir(parents=True, exist_ok=True)
        patcher_config.write_text(
            "\r\n".join(
                [
                    config_domain_line,
                    "UseHttp=True",
                    "DisableForceDynamicResources=True",
                    "DarkModeEnabled=False",
                    "startInTray=False",
                    "minToTray=False",
                ]
            ),
            encoding="utf-8",
        )
    else:
        config_lines = patcher_config.read_text(encoding="utf-8").splitlines()
        found = False
        write = True
        for index, line in enumerate(config_lines):
            if line.startswith("CustomConfigDomain="):
                found = True
                if line == config_domain_line:
                    write = False
                else:
                    config_lines[index] = config_domain_line
                break
        if not found:
            config_lines = [config_domain_line] + config_lines
        if write:
            patcher_config.write_text(
                "\r\n".join(config_lines), encoding="utf-8"
            )
    updater.update()
    updater.launch(processes, wait=wait)

    return 0
