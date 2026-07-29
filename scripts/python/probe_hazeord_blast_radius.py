"""case-haze-ord -- RAYON DE SOUFFLE du deplacement du drainage de la mort.

Question : combien de call-sites du moteur dependent du drainage IMMEDIAT de la mort, et
lesquels changent de comportement quand `AttackDamageOperation._fire_death_if_killed` devient
`RecordKillOperation` (ENQUEUE) + `VerifyDeaths` (DRAIN NON REENTRANT) ?

Ce probe ne mesure RIEN en live : il DERIVE l'inventaire du code (registres de triggers +
scan statique des call-sites), pour que le chiffre soit re-derivable et non recopie.

Trois familles :
  (1) les SITES qui appliquent du degat -- donc les entrees possibles de la mort ;
  (2) les CONSOMMATEURS des vecteurs de mort (`On(3)`, `On(1)`, `On(2)`, `On(0)`, `On(55)`) :
      leur ORDRE RELATIF change UNIQUEMENT quand une mort survient PENDANT une autre ;
  (3) les consommateurs de (2) dont le behaviour peut TUER (attaque / degat) -- l'ensemble
      REELLEMENT touche : c'est la seule facon d'imbriquer deux morts.

CLI (depuis scripts/python) : python probe_hazeord_blast_radius.py
ASCII only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ENGINE = PYDIR / "engine"

# Les cinq vecteurs emis par le couple `RecordKillOperation$$Execute` / `KillUnitOperation$$Execute`.
DEATH_EVENTS = {
    0: "UnitDeath",
    1: "PreUnitDeath",
    2: "PreUnitDeath_2",
    3: "PendingDeathAdded",
    55: "UnitDefeated",
}
# Marqueurs, dans le SOURCE d'un `execute_behaviour`, d'un behaviour capable de TUER.
_KILLING = ("execute_ability_attack", "execute_normal_like", "execute_direct",
            "AttackWithAttackDamage", "AttackWithAbilityDamage", "AttackDamageOperation.execute",
            "_apply_damage_pipeline", "DirectDamage", "displace")


def _scan_callsites(needle: str) -> list:
    """Les call-sites STATIQUES de `needle` sous `engine/` (hors la definition elle-meme)."""
    out = []
    for p in ENGINE.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
            s = line.strip()
            if needle + "(" not in s or s.startswith("#") or s.startswith("def "):
                continue
            if "def " + needle in s:
                continue
            out.append((str(p.relative_to(PYDIR)).replace("\\", "/"), i, s[:90]))
    return out


def _registry():
    from engine.runner.operations.triggers.dispatch import registry as R
    classes = []
    # Les QUATRE registres consommes par `dispatch/core.py::collect_*` -- les oublier (le premier
    # jet de ce probe ne lisait que `ABILITY_TRIGGERS`) fait DISPARAITRE la famille DEATH-NOVA,
    # qui vit dans `TRAIT_TRIGGERS`.
    for reg in (R.ABILITY_TRIGGERS, R.TRAIT_TRIGGERS, R.ACTIVE_ABILITY_TRIGGERS, R.EFFECT_TRIGGERS):
        for lst in reg.values():
            classes.extend(lst)
    classes.extend(R.GLOBAL_TRIGGERS)
    seen, uniq = set(), []
    for c in classes:
        if c in seen:
            continue
        seen.add(c)
        uniq.append(c)
    return uniq


def main() -> int:
    import inspect
    print("=" * 92)
    print("case-haze-ord -- RAYON DE SOUFFLE (derive du code, pas recopie)")
    print("=" * 92)

    # (1) SITES d'application de degat -- entrees possibles de la mort.
    print()
    print("(1) SITES qui traversent le chokepoint de degat")
    for needle in ("_apply_damage_pipeline", "_fire_death_if_killed", "_verify_deaths",
                   "_add_death"):
        cs = _scan_callsites(needle)
        print("    %-26s %d call-site(s) sous engine/" % (needle, len(cs)))
        for f, i, s in cs:
            print("        %-62s :%-5d %s" % (f, i, s))

    # (2) CONSOMMATEURS des vecteurs de mort.
    print()
    print("(2) CONSOMMATEURS des vecteurs de mort du registre")
    classes = _registry()
    per_ev = {}
    for c in classes:
        ids = set()
        e = getattr(c, "event_id", None)
        if e is not None:
            ids.add(int(e))
        for x in (getattr(c, "event_ids", ()) or ()):
            ids.add(int(x))
        for e in ids & set(DEATH_EVENTS):
            per_ev.setdefault(e, []).append(c)
    total = sum(len(v) for v in per_ev.values())
    print("    registre TOTAL = %d classes ; consommateurs de mort = %d" % (len(classes), total))
    killers = []
    for e in sorted(per_ev):
        names = sorted(x.__name__ for x in per_ev[e])
        print("    On(%-2d %-17s) x%-2d : %s" % (e, DEATH_EVENTS[e], len(names), ", ".join(names)))
    # (3) parmi eux, ceux dont le behaviour peut TUER (donc imbriquer une 2e mort).
    print()
    print("(3) Parmi (2), ceux dont le behaviour peut TUER -- le SEUL sous-ensemble reellement")
    print("    touche par le drain non reentrant (une mort ne s'imbrique que dans une autre)")
    # Le behaviour d'un trigger delegue souvent a une fonction de MODULE (`FinalJusticeAbility` ->
    # `_finaljustice_attack`) : `inspect.getsource(<classe>)` seul RATE ces cas. On rend donc les DEUX
    # bornes -- classe (STRICTE) et module (LARGE) -- plutot qu'un chiffre unique faussement precis.
    strict = []
    for e in sorted(per_ev):
        for c in sorted(per_ev[e], key=lambda x: x.__name__):
            try:
                cls_src = inspect.getsource(c)
                mod_src = inspect.getsource(sys.modules[c.__module__])
            except (OSError, KeyError):
                continue
            hits_cls = [k for k in _KILLING if k in cls_src]
            hits_mod = [k for k in _KILLING if k in mod_src]
            if hits_cls:
                strict.append(c.__name__)
            if hits_mod:
                killers.append((e, c.__name__, hits_mod, bool(hits_cls)))
    for e, n, hits, s in killers:
        print("    On(%-2d) %-42s %-8s <- %s" % (e, n, "[classe]" if s else "[module]",
                                                 ",".join(hits[:3])))
    print()
    print("    BILAN : %d classes du registre ; %d consommateurs de mort ; %d peuvent TUER"
          % (len(classes), total, len(killers)))
    print("            (dont %d avec le vecteur de degat DANS le corps de classe)" % len(strict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
