"""Probe #341 -- le format de `kit-coverage.md` produit-il un diff PROPORTIONNE au changement ?

Le doc a derive parce que trois agents d'affilee ont renonce a le regenerer devant un delta
qu'ils ne s'expliquaient pas. La mesure montre pourquoi : le delta reel valait **3 changements
de fond** (3 ports mergés le 2026-07-31) et le diff en affichait **58 lignes** -- le tri des
sections par VOLUME reordonne des sections entieres des qu'un seul compte bouge, donc le signal
se noie dans le deplacement.

Ce probe REJOUE le meme changement de fond dans les deux formats et compte les lignes de diff :

  etat AVANT  = les 3 ports retires des registres (monkeypatch)
  etat APRES  = les registres tels quels
  format ANCIEN = `audit_kit_coverage.py` a `origin/master`
  format NOUVEAU = la version de travail

Usage : depuis `scripts/python/`  ->  python probe_341_regen_churn.py
"""
from __future__ import annotations

import difflib
import importlib.util
import os
import subprocess
import sys
import tempfile

_PYROOT = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_PYROOT))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

# Les 3 ports mergés entre la derniere regeneration (`48eee1af`, 2026-07-30) et aujourd'hui.
# Les retirer des registres reconstitue l'etat du doc commite, sans checkout.
PORTS = (
    ("#322 ModifiedExoarmour_ExtraDmg", "291b44a9"),
    ("#328 RelentlessMarch",            "526cb0a9"),
    ("#334 DefendTheDivineWork (1117)", "8e35a956"),
)


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _render(mod, tmpdir: str, tag: str) -> list[str]:
    out = os.path.join(tmpdir, tag + ".md")
    saved, mod.OUT = mod.OUT, out
    try:
        _stdout = sys.stdout
        sys.stdout = open(os.devnull, "w")
        try:
            mod.main()
        finally:
            sys.stdout.close()
            sys.stdout = _stdout
    finally:
        mod.OUT = saved
    with open(out, encoding="utf-8") as f:
        return f.readlines()


def _diff_size(a: list[str], b: list[str]) -> int:
    return sum(1 for L in difflib.unified_diff(a, b, n=0)
               if (L.startswith("+") or L.startswith("-"))
               and not L.startswith("+++") and not L.startswith("---"))


def main():
    from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS

    tmpdir = tempfile.mkdtemp(prefix="probe341_")

    # Le format ANCIEN, recupere a `origin/master` -- pas une reconstitution de memoire.
    old_src = subprocess.run(
        ["git", "-C", _REPO, "show", "origin/master:scripts/python/audit_kit_coverage.py"],
        capture_output=True, text=True, check=True).stdout
    old_path = os.path.join(tmpdir, "audit_old.py")
    with open(old_path, "w", encoding="utf-8") as f:
        f.write(old_src)
    old = _load(old_path, "audit_kit_coverage_old")
    new = _load(os.path.join(_PYROOT, "audit_kit_coverage.py"), "audit_kit_coverage_new")

    print("== etat APRES (registres tels quels)")
    old_after = _render(old, tmpdir, "old_after")
    new_after = _render(new, tmpdir, "new_after")

    # --- monkeypatch : retirer les 3 ports des registres -> etat AVANT -------------------
    removed = []
    for d, k in ((ABILITY_CLASSES, 1117), (ABILITY_TRIGGERS, "RelentlessMarch"),
                 (ABILITY_INIT_OWNER_EFFECTS, "ModifiedExoarmour"),
                 (EFFECT_CLASSES, "ModifiedExoarmour_ExtraDmg"),
                 (EFFECT_CLASSES, "RelentlessMarch_Effect")):
        if k in d:
            removed.append((d, k, d.pop(k)))
    print("== etat AVANT : %d entrees de registre retirees (%s)"
          % (len(removed), ", ".join(n for n, _ in PORTS)))
    old_before = _render(old, tmpdir, "old_before")
    new_before = _render(new, tmpdir, "new_before")
    for d, k, v in removed:                       # restaurer -- les dicts sont partages
        d[k] = v

    d_old = _diff_size(old_before, old_after)
    d_new = _diff_size(new_before, new_after)
    print()
    print("MEME changement de fond (3 ports), lignes de diff produites :")
    print("  format ANCIEN  (sections triees par VOLUME) : %3d lignes" % d_old)
    print("  format NOUVEAU (sections triees par NOM)    : %3d lignes" % d_new)
    print()
    print("Detail du diff NOUVEAU format :")
    for L in difflib.unified_diff(new_before, new_after, n=0, lineterm=""):
        if L.startswith(("+++", "---")):
            continue
        if L.startswith(("+", "-", "@@")):
            print("  " + L.rstrip()[:150])
    return 0


if __name__ == "__main__":
    sys.exit(main())
