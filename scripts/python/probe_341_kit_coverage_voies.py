"""Probe #341 -- de quelles VOIES d'attribution `audit_kit_coverage.py` est-il aveugle,
et quel volume cette cecite retire-t-elle du doc genere ?

Contexte : `docs/rl/kit-coverage.md` derivait parce que plus personne ne le regenerait (chaque
agent voyait un delta inexplique). Le delta lui-meme s'explique (cf. `docs/rl/case-341-kit-
coverage-derive.md`), mais le precedent #323 impose de verifier que l'instrument n'est pas
aveugle a une voie -- c'est exactement ce qui avait fait rendre un faux « 0 unite, DEAD » a
`unit_map find --ability`.

Volet A : les voies LUES par l'audit vs les 5 voies indexees par `unit_map` (#323).
Volet B : sur les unites LINEUP, le volume d'abilities atteint par une voie NON lue.
Volet C : de ces abilities invisibles, combien seraient comptees MANQUANTES (aucun registre
          moteur ne les couvre) -- c'est le volume que le doc sous-estime.

Usage : depuis `scripts/python/`  ->  `python probe_341_kit_coverage_voies.py`
"""
from __future__ import annotations

import os
import sys

_PYROOT = os.path.dirname(os.path.abspath(__file__))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

import enum_maps as EM
import gameconfig as GC
import unit_map as UM
import decision_face_voies as DFV     # #979 : foyer UNIQUE de la face DECISION
import kit_item_voies as KIV          # #1041 : foyer UNIQUE de la face COMBAT d'un item

# Les voies que `audit_kit_coverage.collect()` lit sur le gameconfig d'une unite.
AUDIT_VOIES = ("activeAbilities", "passiveAbilities", "traits")


def _covered_any_face(nm: str) -> bool:
    """Couverture au sens de l'audit, LES DEUX FACES.

    ⚠ CE PROBE PORTAIT SA PROPRE COPIE DU PREDICAT (#1041) -- une TROISIEME liste blanche, plus
    etroite encore que celle de l'auditeur (3 registres de combat sur les 6 alors lus). Deux copies
    d'une meme question derivent en silence : celle-ci rendait `PhoenixGem` non couverte alors que
    l'audit, corrige, la rend portee. Elle delegue desormais aux DEUX foyers, qui PARTITIONNENT
    leur perimetre au lieu d'enumerer -- il n'y a plus de liste a tenir a jour ici.

    Le `PARTIEL` de `kit_item_voies` compte comme NON couvert : ce probe mesure le VOLUME de
    travail atteint par une voie, et une face manquante en est."""
    aid = {v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}.get(nm)
    return (KIV.etat(nm)[0] == KIV.PORTE) or bool(DFV.face_portee(aid, nm))


def main():
    print("== VOLET A : voies lues par l'audit vs voies indexees par unit_map (#323)")
    print("   audit_kit_coverage lit  :", ", ".join(AUDIT_VOIES))
    print("   unit_map indexe (#323)  :", ", ".join(UM.VOIE_KEYS))
    non_lues = [v for v in UM.VOIE_KEYS if v not in ("active", "passive")]
    print("   -> NON lues par l'audit :", ", ".join(non_lues))
    print()

    lineup = [k for k in UM.all_kits() if k.get("kind") == "lineup"]
    print("== VOLET B : volume atteint par une voie NON lue, sur les %d unites LINEUP" % len(lineup))

    # On lit `k["voies"]` (l'index #323 de `unit_map`) et non le gameconfig brut : c'est LUI la
    # reference des 5 voies, et il porte deja la voie `item` (qui n'est PAS sur la fiche d'unite).
    per_voie: dict[str, set] = {v: set() for v in non_lues}
    units_touched: dict[str, set] = {v: set() for v in non_lues}
    for k in lineup:
        for v in non_lues:
            for nm in (k.get("voies") or {}).get(v, []):
                per_voie[v].add(nm)
                units_touched[v].add(k["id"])
    for v in non_lues:
        print("   voie %-8s : %3d abilities distinctes, %3d unites lineup"
              % (v, len(per_voie[v]), len(units_touched[v])))

    invisibles = set()
    for v in non_lues:
        invisibles |= per_voie[v]
    deja_vues = set()
    for k in lineup:
        u = GC.unit(k["id"]) or {}
        deja_vues |= set(u.get("activeAbilities") or [])
        deja_vues |= set(u.get("passiveAbilities") or [])
    only_hidden = invisibles - deja_vues
    print("   union voies non lues            : %d abilities" % len(invisibles))
    print("   dont INVISIBLES a l'audit       : %d (aucun porteur lineup en active/passive)"
          % len(only_hidden))
    print()

    print("== VOLET C : de ces invisibles, combien ne sont couvertes par AUCUN registre moteur ?")
    non_portees = sorted(nm for nm in only_hidden if not _covered_any_face(nm))
    portees = sorted(nm for nm in only_hidden if _covered_any_face(nm))
    print("   portees (au moins un registre)  : %d" % len(portees))
    print("   NON portees -> items que le doc ne compte pas : %d" % len(non_portees))
    for nm in non_portees:
        carriers = sorted(k["id"] for k in lineup
                          if any(nm in (k.get("voies") or {}).get(v, []) for v in non_lues))
        voies_de = sorted({v for k in lineup for v in non_lues
                           if nm in (k.get("voies") or {}).get(v, [])})
        print("     - %-32s voie=%-14s porteurs lineup=%d  ex.: %s"
              % (nm, "/".join(voies_de), len(carriers), ", ".join(carriers[:4]) or "-"))


if __name__ == "__main__":
    main()
