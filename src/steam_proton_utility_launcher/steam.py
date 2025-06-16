from __future__ import annotations

import logging
import os
import platform
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import KeysView, Mapping, Sequence, Union

import vdf  # type: ignore

VDFTree = Mapping[str, Union[str, "VDFTree"]]

logger = logging.getLogger(__name__)


@dataclass
class Process:
    command_line: list[str]
    env: dict[str, str] | None = None
    cwd: Path | None = None

    def __post_init__(self) -> None:
        if not self.command_line:
            raise AssertionError("command_line must be a non-empty list.")

    def start(self) -> subprocess.Popen[bytes]:
        command_line = list(self.command_line)
        logger.info(f"Starting subprocess: {command_line}")
        return subprocess.Popen(
            command_line,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            cwd=self.cwd,
            env=self.env,
        )


class Verb(StrEnum):
    RUN = "run"
    WAIT_FOR_EXIT_AND_RUN = "waitforexitandrun"


@dataclass
class VDFNode:
    tree: VDFTree

    @classmethod
    def from_path(cls, path: Path) -> VDFNode:
        with open(path, "r", encoding="utf-8") as handle:
            return cls(tree=vdf.load(handle))

    @classmethod
    def from_path_binary(cls, path: Path) -> VDFNode:
        with open(path, "rb") as handle:
            return cls(tree=vdf.binary_load(handle))

    def keys(self) -> KeysView[str]:
        return self.tree.keys()

    def section(self, keys: Sequence[str]) -> VDFNode:
        if isinstance(keys, str):
            keys = [keys]
        tree: VDFTree = self.tree
        for key in keys:
            inner_tree = tree[key]
            if isinstance(inner_tree, str):
                raise ValueError(
                    f"Expected object, got str: {key}={inner_tree}"
                )
            tree = inner_tree
        if tree is self.tree:
            return self
        return VDFNode(tree=tree)

    def __getitem__(self, keys: Sequence[str]) -> str:
        if isinstance(keys, str):
            keys = [keys]
        else:
            keys = list(keys)
        if not keys:
            raise ValueError("no keys passed")
        leaf = keys.pop()
        section = self.section(keys=keys)
        value = section.tree[leaf]
        if not isinstance(value, str):
            raise TypeError(f"value expected to be str, but is {type(value)}")
        return value

    def get(self, keys: Sequence[str], default: str = "") -> str:
        try:
            return self[keys]
        except KeyError:
            return default


_PROTON_PATTERN = re.compile(r"^Proton($|[- _])", re.IGNORECASE)


@dataclass
class CompatibilityTool:
    internal_name: str
    manifest_vdf: Path
    install_path: Path
    display_name: str
    binary_path: Path
    binary_argument_template: list[str]

    def is_proton(self) -> bool:
        return _PROTON_PATTERN.match(self.internal_name) is not None

    @classmethod
    def from_toolmanifest_vdf(
        cls,
        manifest_vdf: Path,
        internal_name: str = "",
        display_name: str = "",
    ) -> CompatibilityTool:
        install_path = manifest_vdf.parent
        if not internal_name:
            internal_name = install_path.name.lower().replace(" ", "_")
        if not display_name:
            display_name = install_path.name
        manifest = VDFNode.from_path(manifest_vdf).section("manifest")
        manifest_version = manifest["version"]
        if manifest_version != "2":
            raise NotImplementedError(
                f"Only supports manifest v2, but found v{manifest_version}"
            )
        command_line_template = shlex.split(manifest["commandline"])
        if not command_line_template:
            raise ValueError("Couldn't retrieve command line!")
        binary = command_line_template[0]
        if binary.startswith("/"):
            binary = str(install_path / binary[1:])
        else:
            which_path = shutil.which(binary)
            if not which_path:
                raise ValueError(f"Couldn't find binary in PATH: {binary}")
            binary = which_path
        return CompatibilityTool(
            internal_name=internal_name,
            install_path=install_path,
            manifest_vdf=manifest_vdf,
            display_name=display_name,
            binary_path=Path(binary),
            binary_argument_template=command_line_template[1:],
        )

    @classmethod
    def from_compatibilitytool_vdf(
        cls, tool_vdf: Path
    ) -> list[CompatibilityTool]:
        tools: list[CompatibilityTool] = []
        compat_tools = VDFNode.from_path(tool_vdf).section(
            ["compatibilitytools", "compat_tools"]
        )
        vdf_dir = tool_vdf.parent
        for internal_name in compat_tools.keys():
            tool_section = compat_tools.section(internal_name)
            install_path = vdf_dir / tool_section["install_path"]
            manifest_vdf = install_path / "toolmanifest.vdf"
            tools.append(
                cls.from_toolmanifest_vdf(
                    manifest_vdf,
                    internal_name=internal_name,
                    display_name=tool_section.get("display_name"),
                )
            )
        return tools

    @property
    def manifest_path(self) -> Path:
        return self.install_path / "toolmanifest.vdf"

    def command_line(self, *, verb: Verb = Verb.RUN) -> list[str]:
        return [str(self.binary_path)] + [
            tool_arg if tool_arg != "%verb%" else str(verb)
            for tool_arg in self.binary_argument_template
        ]


@dataclass
class SteamLocation:
    root: Path
    system_config_dirs: list[Path]

    @classmethod
    def from_detection(cls) -> SteamLocation:
        if platform.system() != "Linux":
            raise NotImplementedError("currently only implemented for linux")
        XDG_DATA_HOME = Path(
            os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        )
        root = XDG_DATA_HOME / "Steam"
        system_config_dirs = [
            Path(path) / "steam"
            for path in os.environ.get(
                "XDG_DATA_DIRS", "/usr/local/share:/usr/share"
            ).split(":")
        ]
        return SteamLocation(root=root, system_config_dirs=system_config_dirs)

    @property
    def config_dirs(self) -> list[Path]:
        return [self.root] + self.system_config_dirs

    @property
    def steamapps(self) -> Path:
        return self.root / "steamapps"

    @property
    def config_vdf(self) -> Path:
        return self.root / "config" / "config.vdf"


@dataclass
class Steam:
    location: SteamLocation
    compatibility_tools: list[CompatibilityTool]

    @classmethod
    def from_location(cls, location: SteamLocation) -> Steam:
        compatibility_tools: list[CompatibilityTool] = []
        for manifest_vdf in (location.steamapps / "common").glob(
            "*/toolmanifest.vdf"
        ):
            compatibility_tools.append(
                CompatibilityTool.from_toolmanifest_vdf(manifest_vdf)
            )

        for dir in location.config_dirs:
            for vdf_path in dir.glob(
                "compatibilitytools.d/*/compatibilitytool.vdf"
            ):
                try:
                    tools = CompatibilityTool.from_compatibilitytool_vdf(
                        vdf_path
                    )
                except Exception:
                    logger.warn(
                        f"Exception when loading {vdf_path}:", exc_info=True
                    )
                    continue
                compatibility_tools.extend(tools)
        return Steam(
            location=location, compatibility_tools=compatibility_tools
        )

    @classmethod
    def from_detection(cls) -> Steam:
        return cls.from_location(SteamLocation.from_detection())

    def game_compatibility_tool(self, id: str) -> str:
        steam_section = VDFNode.from_path(self.location.config_vdf).section(
            ["InstallConfigStore", "Software", "Valve", "Steam"]
        )
        try:
            tool_mapping = steam_section.section("CompatToolMapping")
        except KeyError:
            return ""
        return tool_mapping.get(
            [id, "name"], tool_mapping.get(["0", "name"], "")
        )

    def game_compatdata_path(self, *, game_id: str) -> Path:
        return self.location.root / "steamapps" / "compatdata" / game_id

    def game_wine_prefix(self, *, game_id: str) -> Path:
        return self.game_compatdata_path(game_id=game_id) / "pfx"

    def process_in_prefix(
        self,
        command_line: list[str],
        *,
        game_id: str,
        cwd: Path | None = None,
        system_wine: bool = False,
    ) -> Process:
        env = os.environ.copy()
        is_wine = False
        if system_wine:
            is_wine = True
            command_line = ["wine"] + command_line
        else:
            tool_name = self.game_compatibility_tool(game_id)
            if tool_name:
                matched_tools = [
                    tool
                    for tool in self.compatibility_tools
                    if tool.internal_name == tool_name
                ]
                if not matched_tools:
                    raise RuntimeError(
                        f"No compatibility tools matched: {tool_name}"
                    )
                if len(matched_tools) > 1:
                    raise RuntimeError(
                        f"Multiple compatibility tools matched: {tool_name}"
                    )
                tool = matched_tools[0]
                if tool.is_proton():
                    is_wine = True
                    command_line = (
                        tool.command_line(verb=Verb.RUN) + command_line
                    )
                    env.update({"PROTON_DIR": str(tool.binary_path.parent)})
        if is_wine:
            env.update(
                {
                    "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(
                        self.location.root
                    ),
                    "WINEPREFIX": str(self.game_wine_prefix(game_id=game_id)),
                    "STEAM_COMPAT_DATA_PATH": str(
                        self.game_compatdata_path(game_id=game_id)
                    ),
                }
            )
            logger.info(f"Process will run in prefix: {command_line}")
        else:
            logger.warning(
                f"Process will run directly (no prefix): {command_line}"
            )
        return Process(command_line=command_line, env=env, cwd=cwd)
