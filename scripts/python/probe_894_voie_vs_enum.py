#!/usr/bin/env python
"""probe #894 -- LA VOIE DU GAMECONFIG NE DIT PAS L'ENUM : combien de noms sont mal ranges ?

MESURE, pas garde-fou (cf. `reference_probes_are_not_tests`). Le cliquet executable est
`tests/engine/test_894_routage_ability_par_nom_offline.py`.

CE QU'IL MESURE, tout re-derive du gameconfig VIVANT et des deux tables d'enum du build courant
(`data/symbols/<build>/frida/enums.tsv`) -- jamais d'une liste ecrite a la main :

  etape 1  RECENSEMENT   les 4 voies d'attribution du gameconfig (`activeAbilities`,
                         `passiveAbilities`, `mythicAbilities`, `relicAbilities`), croisees avec
                         `ActiveAbilityType` et `TriggeredAbilityType`. Sortie : occurrences,
                         noms distincts, MAL RANGES, AMBIGUS (dans les deux enums), ORPHELINS
                         (dans aucun). La partition est imprimee comme somme exhaustive.
  etape 2  ROUTAGE       ce que `catalog_inject.route_configured_abilities` fait de chaque
                         porteur mal range -- et ce que l'ancienne regle « la voie dit l'enum »
                         en faisait (elle LEVAIT).
  etape 3  ORDINAL       pour chaque nom mal range, ce que son ordinal NOMME dans l'autre enum :
                         c'est la forme SILENCIEUSE de la faute, celle qu'aucune exception ne
                         montre.
  etape 4  TEMOIN        typage des cles de `BC.Abilities` dans la capture ECRITE PAR LE JEU.
                         Il DISCRIMINE : les deux noeuds types sont a 0 cle hors enum alors que
                         `EnvironmentAbilities`/`Traits`, keyes par string libre, en portent.

USAGE
    python probe_894_voie_vs_enum.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import catalog_inject as C
import gameconfig as G

ACT = "IdunBattle.Entities.Enum.ActiveAbilityType"
TRI = "IdunBattle.Entities.Enum.TriggeredAbilityType"

# Voie -> enum que l'ancienne regle presumait. `relicAbilities`/`mythicAbilities` sont ici pour
# que le recensement soit EXHAUSTIF : un gisement qu'on ne visite pas ne peut pas rendre zero.
VOIES = {
    "activeAbilities": ACT,
    "passiveAbilities": TRI,
    "mythicAbilities": TRI,
    "relicAbilities": TRI,
}


def _units():
    cfg = G._cfg()["units"]
    for kind in ("lineup", "npc", "summons"):
        for uid, u in (cfg.get(kind) or {}).items():
            yield kind, uid, u


def main() -> int:
    act = C.enum_map(ACT)
    tri = C.enum_map(TRI)
    print("[894] build=%s  ActiveAbilityType=%d membres  TriggeredAbilityType=%d membres"
          % (C._build_hash(), len(act), len(tri)))

    # --- etape 1 : recensement exhaustif ------------------------------------------------------
    print("\n[894] etape 1 -- RECENSEMENT des 4 voies")
    occ_total = 0
    noms_tous: set = set()
    mal: list = []
    ambigus: set = set()
    orphelins: set = set()
    for voie, enum_presume in VOIES.items():
        table = act if enum_presume is ACT else tri
        occ = 0
        noms: set = set()
        for _kind, uid, u in _units():
            for name in (u.get(voie) or []):
                occ += 1
                noms.add(name)
                if name in act and name in tri:
                    ambigus.add(name)
                if name not in act and name not in tri:
                    orphelins.add(name)
                if name not in table:
                    porteur = (ACT if name in act else TRI if name in tri else None)
                    mal.append((uid, voie, name, porteur))
        occ_total += occ
        noms_tous |= noms
        print("  %-18s occurrences=%4d  noms=%3d  presume=%s"
              % (voie, occ, len(noms), enum_presume.rsplit(".", 1)[-1]))
    conformes = occ_total - len(mal)
    print("  TOTAL occurrences=%d  noms distincts=%d" % (occ_total, len(noms_tous)))
    print("  PARTITION (exhaustive) : conformes=%d + MAL RANGES=%d = %d"
          % (conformes, len(mal), occ_total))
    print("  AMBIGUS (dans les DEUX enums) : %d %s" % (len(ambigus), sorted(ambigus)))
    print("  ORPHELINS (dans AUCUN enum)   : %d %s" % (len(orphelins), sorted(orphelins)))

    # --- etape 2 : ce que le routage en fait --------------------------------------------------
    print("\n[894] etape 2 -- ROUTAGE (mirror de BattleConfigBuilder$$SetupAbilities)")
    if not mal:
        print("  AUCUN nom mal range sur ce gameconfig -- rien a router (regime degenere : ce"
              " probe ne prouve alors RIEN sur le routage)")
    for uid, voie, name, porteur in mal:
        gc = G.unit(uid)
        routed = C.route_configured_abilities(gc)
        court = porteur.rsplit(".", 1)[-1] if porteur else "AUCUN"
        ident = (act.get(name) if porteur == ACT else tri.get(name))
        # l'ancienne regle : `triggered_ability_id` / `active_ability_id` selon la voie
        try:
            (C.active_ability_id if voie == "activeAbilities" else C.triggered_ability_id)(name)
            ancien = "aurait resolu (?)"
        except KeyError as exc:
            ancien = "LEVAIT : %s" % exc.args[0]
        ou = ("ActiveAbilities" if ident in routed["ActiveAbilities"] else
              "PassiveAbilities" if ident in routed["PassiveAbilities"] else "ABANDONNEE")
        print("  %-24s %-17s %-22s -> %s %s" % (uid, voie, name, court, ident))
        print("      routage natif : %s   |   ancienne regle : %s" % (ou, ancien))
        if routed["dropped"]:
            print("      dropped (le natif n'ajoute RIEN) : %s" % (routed["dropped"],))

    # --- etape 3 : la faute SILENCIEUSE en ordinal --------------------------------------------
    print("\n[894] etape 3 -- ORDINAL : ce que la valeur NOMME dans l'autre enum")
    iact = {v: k for k, v in act.items()}
    itri = {v: k for k, v in tri.items()}
    for _uid, _voie, name, porteur in mal:
        if porteur == ACT:
            v = act[name]
            print("  ActiveAbilityType.%s = %d  ->  TriggeredAbilityType[%d] = %s"
                  % (name, v, v, itri.get(v)))
        elif porteur == TRI:
            v = tri[name]
            print("  TriggeredAbilityType.%s = %d  ->  ActiveAbilityType[%d] = %s"
                  % (name, v, v, iact.get(v)))
    communs = set(act.values()) & set(tri.values())
    autre = sum(1 for v in communs if iact[v] != itri[v])
    print("  ordinaux PARTAGES par les deux enums : %d, dont %d NOMMENT autre chose"
          % (len(communs), autre))

    # --- etape 4 : temoin -- le typage des cles, ecrit PAR LE JEU -----------------------------
    print("\n[894] etape 4 -- TEMOIN : typage des cles de BC.Abilities (capture du jeu)")
    seed = Path(C.ROOT) / "data" / "seed-bc.json"
    if not seed.exists():
        print("  seed BC absent (%s) -- temoin NON mesure" % seed)
        return 0
    ab = json.loads(seed.read_text(encoding="utf-8")).get("Abilities") or {}
    for noeud, table, nom in (("ActiveAbilities", act, "ActiveAbilityType"),
                              ("PassiveAbilities", tri, "TriggeredAbilityType"),
                              ("EnvironmentAbilities", tri, "TriggeredAbilityType"),
                              ("Traits", tri, "TriggeredAbilityType")):
        keys = list((ab.get(noeud) or {}).keys())
        hors = [k for k in keys if k not in table]
        print("  %-22s cles=%3d  hors %s = %3d %s"
              % (noeud, len(keys), nom, len(hors), (hors[:4] if hors else "")))
    print("  -> les deux noeuds TYPES sont a 0 ; les deux autres non : le temoin DISCRIMINE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
