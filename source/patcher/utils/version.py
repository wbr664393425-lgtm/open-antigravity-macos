"""Минимальная замена packaging.version — только stdlib.

Зачем: оригинальный патчер тянул внешний пакет `packaging` ради
Version(...) в ide/discovery.py и manager/patcher.py. Для запуска
одной командой на macOS (без venv и pip) зависимость убрана:
сравнение версий покрывает все реальные случаи — "2.5.5", "2.32.1",
"1.107.0", "1.2.7-beta", "v2.0".

Публичный API совместим в объёме, который использует патчер:
    Version("2.5.5") >= Version("2.5.5")
"""

import re

_VERSION_RE = re.compile(
    r"^\s*[vV]?(\d+(?:[._-]\d+)*)(?:[-+._]?([0-9A-Za-z.\-+]+))?\s*$"
)


class InvalidVersion(ValueError):
    pass


class Version:
    """Сравнимая версия: числовые части + pre-release суффикс.

    Порядок: 1.2.7-beta < 1.2.7 < 1.2.7.1.
    """

    __slots__ = ("raw", "parts", "pre")

    def __init__(self, text):
        self.raw = str(text)
        m = _VERSION_RE.match(self.raw)
        if not m:
            raise InvalidVersion(f"Invalid version: {text!r}")

        numbers = re.split(r"[._-]", m.group(1))
        self.parts = tuple(int(n) for n in numbers if n != "")
        suffix = (m.group(2) or "").strip()
        self.pre = suffix

    def _key(self):
        # Дополняем нулями, чтобы 1.2 == 1.2.0 при сравнении.
        padded = (self.parts + (0, 0, 0, 0))[:4]
        # Отсутствие суффикса = релиз, он больше любого pre-release.
        release_rank = 0 if self.pre else 1
        return (padded, release_rank, self.pre)

    def __eq__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() == other._key()

    def __lt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() < other._key()

    def __le__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() <= other._key()

    def __gt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() > other._key()

    def __ge__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() >= other._key()

    def __hash__(self):
        return hash(self._key())

    def __repr__(self):
        return f"<Version {self.raw!r}>"

    def __str__(self):
        return self.raw
