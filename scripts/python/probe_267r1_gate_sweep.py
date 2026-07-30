"""probe #267-r1 (derivation) -- QUELS traits font basculer un consommateur des 12 sites ?

On ne DEVINE pas la liste : on la DERIVE. Pour chaque classe d'effet du registre et pour chaque
valeur de l'enum `UnitTrait`, on appelle les DEUX pattes de bonus de degat en ne faisant varier
QUE l'ensemble de traits passe (`target_traits` cote cible, `att_traits` cote attaquant) et on
retient les couples (effet, trait) dont la SORTIE CHANGE. C'est le pendant offline du balayage
`dumpEnum` : un gate qu'on n'aurait pas lu ne peut pas nous echapper.

Puis on croise avec les deux sources d'ecart entre le KIT BRUT (`gameconfig.unit(vis).traits`, ce
que les 12 sites relisaient) et le SUBSTRAT D'ENTITE (`_entity_traits`, ce qu'ils lisent depuis
#267-r1) :

  A. le pseudo-trait de GRANDE ALLIANCE -- `IdunBattle.Entities.Components.BaseUnitComponent`
     le porte (le BC l'ecrit dans `+0x40`, et la mesure `combatSnapshot.units[].traits` le rend),
     mais AUCUN `gameconfig.unit().traits` ne le contient : ecart de 100 % des unites, sans
     dependre d'aucune capture ;
  B. l'ecart `BC.Units[].Traits` vs kit du seed BC (5 unites en moins, 48 en plus).

Sortie = la liste des gates REELLEMENT reveilles par le cablage, avec leur magnitude.

ASCII only (console cp1252). Usage :  python probe_267r1_gate_sweep.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gameconfig as GC                                                        # noqa: E402
from engine.entities.effects.factory import EFFECT_CLASSES                     # noqa: E402
from engine.entities.traits.unit_trait import (GRAND_ALLIANCE_TRAITS,          # noqa: E402
                                               UnitTrait, unit_trait_names)

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED_BC = ROOT / "data" / "seed-bc.json"

# Les deux pattes de bonus de DEGAT qui recoivent un ensemble de traits (cf. `entities/effects/base.py`).
PATTES = ("create_effect_damage_bonus_for_attack", "create_aura_attack_damage_bonus_for_ally")


def _sortie(obj) -> str:
    """Empreinte comparable d'un `EffectBonus | None` (kind/value/cap)."""
    if obj is None:
        return "None"
    return "%s:%s:%s" % (getattr(obj, "kind", "?"), getattr(obj, "value", "?"),
                         getattr(obj, "cap", "?"))


def _essai(eff, patte, trait_name, cote):
    """Appelle `patte` avec / sans `trait_name` et rend (sans, avec) si la signature l'accepte."""
    fn = getattr(eff, patte, None)
    if fn is None:
        return None
    vide, plein = frozenset(), frozenset({trait_name})
    try:
        if cote == "target" and patte == PATTES[0]:
            a = fn(is_ranged=False, has_moved=False, target_traits=vide)
            b = fn(is_ranged=False, has_moved=False, target_traits=plein)
        elif cote == "target":
            a = fn({"tgt_traits": vide, "is_melee": True})
            b = fn({"tgt_traits": plein, "is_melee": True})
        elif cote == "att" and patte == PATTES[0]:
            a = fn(is_ranged=False, has_moved=False, target_traits=frozenset(),
                   att_ctx={"traits": vide})
            b = fn(is_ranged=False, has_moved=False, target_traits=frozenset(),
                   att_ctx={"traits": plein})
        else:
            a = fn({"att_traits": vide, "is_melee": True})
            b = fn({"att_traits": plein, "is_melee": True})
    except Exception:
        return None
    return (_sortie(a), _sortie(b))


def main() -> int:
    noms = sorted({t.name for t in UnitTrait})
    sensibles: dict = {}
    for cle, klass in sorted(EFFECT_CLASSES.items()):
        try:
            eff = klass(name=cle)
        except Exception:
            continue
        for patte in PATTES:
            for cote in ("target", "att"):
                for tn in noms:
                    r = _essai(eff, patte, tn, cote)
                    if r is None or r[0] == r[1]:
                        continue
                    sensibles.setdefault(tn, []).append(
                        "%s.%s[%s] %s -> %s" % (cle, patte.split("_for_")[-1], cote, r[0], r[1]))

    print("== GATES DE TRAIT reveilles/eteints par l'ensemble passe (derivation exhaustive) ==")
    print("   %d classes d'effet balayees x %d valeurs d'enum UnitTrait" % (len(EFFECT_CLASSES), len(noms)))
    for tn in sorted(sensibles):
        print("  %-18s : %s" % (tn, " | ".join(sensibles[tn][:3])))

    # -- A. GRANDE ALLIANCE : ecart STRUCTUREL, 100 % des unites, sans dependre d'une capture ----
    print("")
    print("== A -- gates d'ALLIANCE : le kit BRUT ne peut PAS les ouvrir ==")
    allies = sorted(GRAND_ALLIANCE_TRAITS & set(sensibles))
    if not allies:
        print("  aucun gate d'alliance parmi les consommateurs -> vecteur A INOPERANT")
    for tn in allies:
        porteurs = [v for v in GC.all_unit_ids() if tn in (unit_trait_names(v) or ())]
        brut = [v for v in porteurs if tn in ((GC.unit(v) or {}).get("traits") or ())]
        print("  %-9s : %d unites le portent au SUBSTRAT, %d au kit BRUT -> gate MORT avant #267-r1"
              % (tn, len(porteurs), len(brut)))
        for ligne in sensibles[tn]:
            print("      %s" % ligne)

    # -- B. ecart BC vs kit du seed --------------------------------------------------------------
    print("")
    print("== B -- gates touches par l'ecart `BC.Units[].Traits` vs kit (seed BC) ==")
    if SEED_BC.exists():
        bc = json.loads(SEED_BC.read_text(encoding="utf-8"))
        vus: dict = {}
        for u in (bc.get("Units") or []):
            v = u.get("VisualId")
            if not v:
                continue
            m, k = frozenset(u.get("Traits") or ()), frozenset(unit_trait_names(v))
            for t in (m - k):
                vus.setdefault(t, {"BC": set(), "KIT": set()})["BC"].add(v)
            for t in (k - m):
                vus.setdefault(t, {"BC": set(), "KIT": set()})["KIT"].add(v)
        touches = sorted(set(vus) & set(sensibles))
        if not touches:
            print("  aucun trait CONSOMME ne diverge sur le seed BC")
        for t in touches:
            print("  %-18s BC-seul=%d  kit-seul=%d  | %s"
                  % (t, len(vus[t]["BC"]), len(vus[t]["KIT"]), sensibles[t][0]))
    else:
        print("  seed BC absent -- etage saute")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
