"""probe #227 -- RAYON DE SOUFFLE du vecteur `On(UnitRemoved = 0x25 = 37)`.

Deux questions, mesurees sur le code (jamais heritees d'une fiche) :

  1. QUI ecoute `On(0x25)` cote port ? On balaie les QUATRE registres de
     `engine/runner/operations/triggers/dispatch/registry.py` (TRAIT / ABILITY /
     ACTIVE_ABILITY / EFFECT) et on retient toute classe dont `event_id` vaut
     `EventTriggerType.UnitRemoved` ou dont `event_ids` le contient.

  2. QUI l'EMET cote port ? On grep les appels de `unit_removed_triggers(` hors du module
     qui la definit et hors des re-exports `__init__` -- c'est le critere binaire de la
     fiche #227 (« le vecteur a-t-il un emetteur de production ? »).

Sortie ASCII pure (console cp1252). Usage : `python probe_227_unit_removed_blast_radius.py`
depuis `scripts/python`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.dsl.event_trigger_type import EventTriggerType          # noqa: E402
from engine.runner.operations.triggers.dispatch import registry     # noqa: E402

TARGET = int(EventTriggerType.UnitRemoved)
ENGINE = Path(__file__).resolve().parent / "engine"
VECTOR = "unit_removed_triggers"
# Le module qui DEFINIT le vecteur + les deux re-exports : ce ne sont pas des emetteurs.
NON_EMITTERS = {
    Path("runner/operations/triggers/dispatch/move_death.py"),
    Path("runner/operations/triggers/dispatch/__init__.py"),
    Path("runner/operations/triggers/__init__.py"),
}


def _listens(cls) -> bool:
    if int(getattr(cls, "event_id", -1)) == TARGET:
        return True
    return TARGET in tuple(int(e) for e in getattr(cls, "event_ids", ()) or ())


def listeners() -> list[tuple[str, str, str]]:
    """(nom du registre, cle, classe) de tout trigger porte qui ecoute `On(0x25)`."""
    out = []
    for reg_name in ("TRAIT_TRIGGERS", "ABILITY_TRIGGERS", "ACTIVE_ABILITY_TRIGGERS",
                     "EFFECT_TRIGGERS"):
        reg = getattr(registry, reg_name)
        for key, classes in reg.items():
            for cls in classes:
                if _listens(cls):
                    out.append((reg_name, str(key), cls.__name__))
    return sorted(out)


def emitters() -> list[tuple[str, int, str]]:
    """(chemin relatif, ligne, texte) de tout APPEL du vecteur hors definition/re-exports."""
    pat = re.compile(re.escape(VECTOR) + r"\s*\(")
    out = []
    for path in ENGINE.rglob("*.py"):
        rel = path.relative_to(ENGINE)
        if rel in NON_EMITTERS:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line) and not line.lstrip().startswith("#"):
                out.append((rel.as_posix(), i, line.strip()))
    return out


def main() -> int:
    print("== probe #227 : rayon de souffle de On(UnitRemoved = 0x25 = %d) ==" % TARGET)

    lis = listeners()
    print("\n[1] ECOUTEURS portes : %d" % len(lis))
    for reg_name, key, cls in lis:
        print("    %-24s %-28s %s" % (reg_name, key, cls))

    emi = emitters()
    print("\n[2] EMETTEURS de production (appels de %s hors definition/re-exports) : %d"
          % (VECTOR, len(emi)))
    for rel, line_no, text in emi:
        print("    %s:%d  %s" % (rel, line_no, text[:100]))

    if not emi:
        print("\nVERDICT : le vecteur n'a AUCUN emetteur -> les %d ecouteur(s) sont MORTS"
              " (degradation RESTRICTIVE et silencieuse)." % len(lis))
        return 1
    print("\nVERDICT : le vecteur a %d emetteur(s) de production." % len(emi))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
