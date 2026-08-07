"""migrateur #287-r14 -- pose la RESOLUTION DE CIBLE en tete de l'`execute_behaviour` de chaque
ability TILE-TARGET du registre.

POURQUOI DEUX BRANCHEMENTS, ET POURQUOI CELUI-CI N'EST PAS UN FORK
------------------------------------------------------------------
Cote natif la resolution vit dans `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`,
et le port l'y met (`AbilityHandler._active_ability_operation`). Mais le port FUSIONNE dans
`execute_behaviour` DEUX etages natifs : `IdunBattle.Operations.ActiveAbilityOperation$$
GetAbilityEntities` (la construction de l'`AbilityEntities`) et `AActiveAbility$$ExecuteBehaviour`.
Or la resolution est l'etage IMMEDIATEMENT AMONT du premier des deux -- son ancrage le plus proche,
cote port, est donc bien la tete de `execute_behaviour`.

Elle y est INERTE quand le handler a deja resolu : chaque branche de
`IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` est un projecteur (`GetMainTile(<tuile>)`
rend la tuile, `GetUnit(<unite>)` l'unite, `GetMachine(<MoW>)` la MoW, self-cast rend `caster`).

Usage (depuis scripts/python) :
    python migrate_287r14_resolution_en_tete.py --verifie     # ce qui serait ecrit
    python migrate_287r14_resolution_en_tete.py --ecrit
"""
from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.runner.abilities.handler import ABILITY_CLASSES            # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR  # noqa: E402

SIGNATURE_FIN = 'target_id: Optional[int]) -> Optional[dict]:'
MARQUEUR = "#287-r14"
BLOC = (
    "        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`\n"
    "        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du\n"
    "        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.\n"
    "        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a\n"
    "        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).\n"
    "        target_id = self.get_actual_target(state, caster_id, target_id)\n"
)


def cibles() -> dict:
    """Les abilities du registre dont le masque porte `TargetIsTile` -- lu, jamais devine."""
    out = {}
    for aid, cls in sorted(ABILITY_CLASSES.items()):
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is not None and int(opts.rules) & int(TR.TargetIsTile):
            out[aid] = cls
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ecrit", action="store_true")
    ns = ap.parse_args()
    par_fichier: dict = {}
    for aid, cls in cibles().items():
        src = inspect.getsourcefile(cls.execute_behaviour)
        lignes, debut = inspect.getsourcelines(cls.execute_behaviour)
        if any(MARQUEUR in ligne for ligne in lignes[:10]):
            print(f"  DEJA POSE  {aid} {cls.__name__}")
            continue
        idx = next(i for i, ligne in enumerate(lignes) if SIGNATURE_FIN in ligne)
        # numero de ligne 1-based de la DERNIERE ligne de signature
        par_fichier.setdefault(src, []).append((debut + idx, aid, cls.__name__))
    total = 0
    for src, points in par_fichier.items():
        texte = Path(src).read_text(encoding="utf-8").split("\n")
        for ligne_no, aid, nom in sorted(points, reverse=True):   # du bas vers le haut
            texte.insert(ligne_no, BLOC.rstrip("\n"))
            print(f"  INSERE     {aid} {nom} -> {Path(src).name}:{ligne_no + 1}")
            total += 1
        if ns.ecrit:
            Path(src).write_text("\n".join(texte), encoding="utf-8")
    print(f"\n{total} insertion(s) dans {len(par_fichier)} fichier(s) "
          f"({'ECRITES' if ns.ecrit else 'SIMULEES'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
