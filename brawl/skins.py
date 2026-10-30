"""Persistent palettes, PNG costumes and player preferences.

SkinLibrary(project_root) stores editable skins in user_data/skins and returns
hex colors and an absolute local sprite path. Ten procedural looks and six
photo-inspired friends ship with the project. PNG imports preserve their transparency. ProfileStore uses
user_data/profile.json. Writes are atomic; invalid files are reported in errors.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata

PATTERNS = ("solid", "stripe", "circuit", "split")
HATS = ("none", "visor", "horns", "crown", "halo")
PARTY_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "skins_party"


@dataclass(frozen=True)
class Skin:
    key: str
    name: str
    primary: str
    secondary: str
    accent: str
    pattern: str = "solid"
    hat: str = "visor"
    sprite: str | None = None


PROCEDURAL_SKINS = (
    Skin("ciano", "CIANO", "#35E5DA", "#16313C", "#F4FFB8", "circuit", "visor"),
    Skin("rubi", "RUBI", "#FF536B", "#3A2035", "#FFE3AB", "split", "horns"),
    Skin("solar", "SOLAR", "#FFCE55", "#493628", "#FEF7DD", "stripe", "visor"),
    Skin("violeta", "VIOLETA", "#A789FF", "#2A294C", "#9FFFF0", "circuit", "halo"),
    Skin("lima", "LIMA", "#B3F455", "#243B32", "#E8FDFF", "split", "visor"),
    Skin("coral", "CORAL", "#FF966A", "#4C2E3C", "#C6FCF3", "stripe", "crown"),
    Skin("gelo", "GELO", "#DAF5FF", "#37536B", "#63D8FF", "solid", "halo"),
    Skin("onix", "ONIX", "#617080", "#202630", "#F8AB48", "circuit", "horns"),
    Skin("cobalto", "COBALTO", "#568AFF", "#1D2C56", "#FAEBA3", "stripe", "visor"),
    Skin("fantasma", "FANTASMA", "#C5BBDD", "#302B48", "#FF8FA6", "split", "none"),
)

# Resolve from this package so the bundled art follows a copied game folder,
# even when launching from a shortcut with a different working directory.
PARTY_SKINS = (
    Skin("party_emannoel", "EMANNOEL", "#FA3E45", "#20242B", "#53B4D0",
         "solid", "none", str(PARTY_ASSET_DIR / "emannoel.png")),
    Skin("party_john", "JOHN", "#F54346", "#20242B", "#FFF0DA",
         "solid", "none", str(PARTY_ASSET_DIR / "john.png")),
    Skin("party_julio", "JULIO", "#F4E5CE", "#24232B", "#92B6FF",
         "solid", "none", str(PARTY_ASSET_DIR / "julio.png")),
    Skin("party_luiz", "LUIZ", "#EFE0C8", "#26242B", "#5DBEFF",
         "solid", "none", str(PARTY_ASSET_DIR / "luiz.png")),
    Skin("party_vini", "VINI", "#F44247", "#252931", "#C2EC40",
         "solid", "none", str(PARTY_ASSET_DIR / "vini.png")),
    Skin("party_yan", "YAN", "#343039", "#1F2028", "#FF5355",
         "solid", "none", str(PARTY_ASSET_DIR / "yan.png")),
)

BUILTIN_SKINS = PROCEDURAL_SKINS + PARTY_SKINS


def _atomic_json(path: Path, data: dict):
    """Replace the complete file only after encoding and writing succeeded."""
    encoded = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pending-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _color(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError("Use uma cor hexadecimal no formato #RRGGBB.")
    return value.upper()


def _name(value) -> str:
    if not isinstance(value, str):
        raise ValueError("A skin precisa de um nome.")
    cleaned = " ".join("".join(c for c in value if c.isprintable()).split())[:36]
    if not cleaned:
        raise ValueError("A skin precisa de um nome.")
    return cleaned


def _slug(value: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:42] or "skin"


class SkinLibrary:
    def __init__(self, root: Path):
        self.folder = Path(root) / "user_data" / "skins"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.errors: list[str] = []
        self._skins: list[Skin] = []
        self.reload()

    def all(self) -> list[Skin]:
        return list(self._skins)

    def get(self, key: str | None) -> Skin:
        return next((skin for skin in self._skins if skin.key == key), BUILTIN_SKINS[0])

    def _sprite_from_json(self, value) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value:
            raise ValueError("Caminho PNG invalido.")
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("O PNG deve ficar na pasta de skins.")
        full = (self.folder / relative).resolve()
        if not full.is_relative_to(self.folder.resolve()) or not full.is_file() or full.suffix.lower() != ".png":
            raise ValueError("PNG local nao encontrado ou caminho invalido.")
        self._validate_png(full)
        return str(full)

    @staticmethod
    def _validate_png(path: Path):
        import pygame
        if not path.is_file() or path.suffix.lower() != ".png":
            raise ValueError("Selecione uma imagem PNG.")
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("O PNG deve ter no maximo 16 MB.")
        with path.open("rb") as stream:
            if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                raise ValueError("O arquivo nao e um PNG valido.")
        try:
            image = pygame.image.load(str(path))
        except Exception as exc:
            raise ValueError("Nao foi possivel abrir esse PNG.") from exc
        width, height = image.get_size()
        if width < 1 or height < 1 or width > 2048 or height > 2048:
            raise ValueError("O PNG deve ter entre 1 e 2048 pixels em cada lado.")

    def reload(self):
        self.errors.clear()
        self._skins = list(BUILTIN_SKINS)
        keys = {skin.key for skin in self._skins}
        for path in sorted(self.folder.glob("*.json")):
            try:
                if path.stat().st_size > 64 * 1024:
                    raise ValueError("Arquivo de skin muito grande.")
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("A skin deve ser um objeto JSON.")
                key = data.get("key", path.stem)
                if not isinstance(key, str) or not re.fullmatch(r"custom_[a-z0-9][a-z0-9_-]{0,55}", key) or key != path.stem or key in keys:
                    raise ValueError("Identificador da skin invalido ou reservado.")
                pattern, hat = data.get("pattern", "solid"), data.get("hat", "visor")
                if pattern not in PATTERNS or hat not in HATS:
                    raise ValueError("Padrao ou acessorio desconhecido.")
                skin = Skin(key, _name(data.get("name")), _color(data.get("primary")),
                            _color(data.get("secondary")), _color(data.get("accent")), pattern, hat,
                            self._sprite_from_json(data.get("sprite")))
                self._skins.append(skin)
                keys.add(key)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                self.errors.append(f"{path.name}: {exc}")

    def _copy_sprite(self, source: Path, key: str) -> str:
        source = source.expanduser().resolve()
        self._validate_png(source)
        target = self.folder / "sprites" / f"{key}.png"
        target.parent.mkdir(exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".pending-", suffix=".png", dir=target.parent)
        os.close(fd)
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return str(target.resolve())

    def save_custom(self, name: str, primary: str, secondary: str, accent: str,
                    pattern: str = "solid", hat: str = "visor", sprite: str | Path | None = None) -> Skin:
        name = _name(name)
        primary, secondary, accent = _color(primary), _color(secondary), _color(accent)
        if pattern not in PATTERNS or hat not in HATS:
            raise ValueError("Padrao ou acessorio desconhecido.")
        base = "custom_" + _slug(name)
        key, counter = base, 2
        known = {skin.key for skin in self._skins}
        while key in known or (self.folder / f"{key}.json").exists():
            key, counter = f"{base}-{counter}", counter + 1
        local_sprite = self._copy_sprite(Path(sprite), key) if sprite else None
        skin = Skin(key, name, primary, secondary, accent, pattern, hat, local_sprite)
        data = asdict(skin)
        data["version"] = 1
        if local_sprite:
            data["sprite"] = Path(local_sprite).relative_to(self.folder.resolve()).as_posix()
        _atomic_json(self.folder / f"{key}.json", data)
        self._skins.append(skin)
        return skin

    def import_png(self, path: str | Path, name: str | None = None) -> Skin:
        path = Path(path)
        return self.save_custom(name or path.stem, "#35E5DA", "#16313C", "#F4FFB8", "solid", "none", path)


class ProfileStore:
    def __init__(self, root: Path):
        self.path = Path(root) / "user_data" / "profile.json"
        self.errors: list[str] = []

    def load(self) -> dict:
        self.errors.clear()
        if not self.path.exists():
            return {}
        try:
            if self.path.stat().st_size > 1024 * 1024:
                raise ValueError("Perfil muito grande.")
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Perfil invalido.")
            return value
        except (OSError, ValueError, TypeError) as exc:
            self.errors.append(str(exc))
            return {}

    def save(self, data: dict):
        if not isinstance(data, dict):
            raise ValueError("O perfil deve ser um objeto.")
        _atomic_json(self.path, data)
