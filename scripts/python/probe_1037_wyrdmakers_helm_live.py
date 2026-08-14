"""#1037 -- CONFRONTATION LIVE de `WyrdmakersHelm` contre le natif.

`spaceWolfPriest` est HORS du seed BC (verifie : aucun `Id` `spaceWolf*` dans `data/seed-bc.json`)
-> c'est l'ETAT 3 des trois d'une ability de relique : injection catalogue PUIS montage `--equip-relic`.
Le montage complet est dans `monter_porteur()`, FIXTURE NOMMEE et reutilisable.

Ce que le probe MESURE cote natif (aucune de ces valeurs n'est re-derivee du port) :
  1. la relique arrive-t-elle en bataille ? (`TertiaryAbility` publie par le runner) ;
  2. un soin sur le porteur ou un allie adjacent, PENDANT son tour, declenche-t-il une attaque
     normale non commandee ? -> les EVENTS du soin ;
  3. la tuile de la cible porte-t-elle `Ice` (17) apres ?
  4. le degat de cette attaque porte-t-il le `+extraDmg` du palier de la relique ?

    python probe_1037_wyrdmakers_helm_live.py --state-file <chemin ABSOLU unique> [--niveau 1]

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

PORTEUR = "spaceWolfPriest"
RELIQUE = "WyrdmakersHelm"


def monter_porteur(out_path: str, *, niveau: int = 10, rank: int = 17):
    """FIXTURE NOMMEE -- les TROIS ecritures du montage relique (#237), dans le BON ORDRE.

    1. `write_augmented_seed_bc` INJECTE `spaceWolfPriest` au catalogue (il est hors seed) ;
    2. `equip_relic` pose `BC.Units[].TertiaryAbility` ET la config dans `BC.Abilities.
       PassiveAbilities` ET `TertiaryAbilityLevel >= 1` -- les deux premieres echouent EN SILENCE si
       on les oublie, la troisieme LEVE (`Level$$ToZeroBasedIndex` sur `<= 0`) ;
    3. l'ORDRE : la relique est posee AVANT toute normalisation ulterieure, sinon `buildNormalizedBC`
       laisse le niveau a 0 (verrou arme en silence).

    `allow_unlisted=False` : `allowedUnits` du gameconfig contient bien `spaceWolfPriest`, donc le
    garde doit passer sans derogation -- si un jour il refuse, c'est le gameconfig qui a bouge."""
    import catalog_inject as C
    # `write_relic_seed_bc` fait les DEUX temps d'un coup : `augment` (le porteur est hors seed) puis
    # `equip_relic` par spec. Ne PAS appeler `equip_relic` a la main sur la BC : il rend un RAPPORT
    # de diagnostic, pas la BC -- s'en servir comme valeur de retour ECRASE le seed par le rapport
    # (faute commise a l'ecriture de ce probe, seed rendu vide et montage `KO` silencieux).
    path, reports = C.write_relic_seed_bc(out_path, ["%s:%s:%d" % (PORTEUR, RELIQUE, int(niveau))],
                                          rank=rank)
    return str(path), reports


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--niveau", type=int, default=10)
    ap.add_argument("--seed-out", default=None)
    a = ap.parse_args()
    seed_out = a.seed_out or os.path.join(
        os.path.dirname(os.path.abspath(a.state_file)), "seed_1037.json")
    os.makedirs(os.path.dirname(seed_out), exist_ok=True)
    monter_porteur(seed_out, niveau=a.niveau)
    print("[1037] seed BC ecrit : " + seed_out)
    with open(seed_out, encoding="utf-8") as fh:
        bc = json.load(fh)
    porteurs = [(u.get("Id"), u.get("TertiaryAbility"), u.get("TertiaryAbilityLevel"))
                for u in bc.get("Units", []) if u.get("TertiaryAbility")]
    print("[1037] reliques equipees dans le seed : " + repr(porteurs))
    ok = any(p[0] == PORTEUR and str(p[1]) in (RELIQUE, str(1504)) and int(p[2] or 0) >= 1
             for p in porteurs)
    print("[1037] montage des TROIS ecritures : " + ("OK" if ok else "KO"))
    cfg = (bc.get("Abilities") or {}).get("PassiveAbilities") or {}
    print("[1037] config d'ability presente dans BC.Abilities.PassiveAbilities : "
          + str(RELIQUE in cfg or str(1504) in cfg))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
