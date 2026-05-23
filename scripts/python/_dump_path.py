"""Resolve the path to the IL2CPP dump matching the currently installed
Tacticus binary.

Tacticus stores each build under `tacticus/games/<HASH>/`, where <HASH>
changes at every game update. RVAs, decompilations, and analytical caches
are all bound to that hash — using a stale dump silently produces incoherent
results (RVAs map to wrong methods, hooks fire on random code).

Usage:
    from _dump_path import current_dump_dir, current_game_hash

    dump = current_dump_dir()              # e.g. Path('data/dumps/uu2fr8mv6c')
    script_json = dump / 'script.json'

`current_dump_dir()` raises FileNotFoundError if no dump matches the
currently-installed binary — that's by design: refusing to run is much
better than silently using stale data. Re-run Il2CppDumper on the new
binary first (see CLAUDE.md "Hash du build = identité du dump").
"""

from pathlib import Path

GAMES_DIR = Path('C:/Users/nicolasv/AppData/Local/tacticus/games')
DUMPS_DIR = Path('data/dumps')


def current_game_hash() -> str:
    """Return the single hash directory currently present in the games root.

    If multiple are present (rare — usually only one build is installed),
    pick the most recently modified.
    """
    if not GAMES_DIR.exists():
        raise FileNotFoundError(f'tacticus games dir missing: {GAMES_DIR}')
    hashes = sorted(
        (d for d in GAMES_DIR.iterdir()
         if d.is_dir() and not d.name.startswith('.')),
        key=lambda d: d.stat().st_mtime, reverse=True)
    if not hashes:
        raise FileNotFoundError(f'no build under {GAMES_DIR}')
    return hashes[0].name


def current_dump_dir() -> Path:
    """Resolve the dump directory matching the currently-installed binary.

    Returns the Path. Raises FileNotFoundError with an actionable message
    if the dump doesn't exist or its HASH marker doesn't match.
    """
    h = current_game_hash()
    dump = DUMPS_DIR / h
    if not dump.exists():
        raise FileNotFoundError(
            f'no dump for current binary hash {h!r} at {dump}. '
            f'Re-run Il2CppDumper (v39) on the new binary first.')
    hash_file = dump / 'HASH'
    if not hash_file.exists():
        raise FileNotFoundError(
            f'dump at {dump} missing HASH marker. Aborting.')
    marker = hash_file.read_text().strip()
    if marker != h:
        raise FileNotFoundError(
            f'dump HASH marker mismatch at {dump}: '
            f'marker={marker!r} but current binary hash={h!r}. '
            f'Stale dump — re-run Il2CppDumper.')
    return dump


if __name__ == '__main__':
    print(f'current_game_hash = {current_game_hash()}')
    print(f'current_dump_dir  = {current_dump_dir()}')
