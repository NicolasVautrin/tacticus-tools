"""#10024 -- `BattleQuery$$IsMeleeAttack` compare des EMPREINTES, pas des MAIN TILES.

## Ce que le decompile DIT (build `t6dpr4k06g`, lu verbatim)

    IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack(
        ability:System.Nullable<IdunBattle.Core.AbilityOrEffect>,
        caster:IdunBattle.Core.IEntity,
        casterPosition:**IdunBattle.Core.UnitPosition**,
        target:IdunBattle.Core.IEntity)

et son unique appel positionnel est la surcharge

    IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent(
        tiles:System.Collections.Generic.IList<IdunBattle.Core.IEntity>, unit:IdunBattle.Core.IEntity)

        tiles2 = IdunBattle.Entities.EntityExtensions$$GetTiles(unit, state);
        return IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(tiles, tiles2);

(xref LUE : `BattleQuery$$IsMeleeAttack` appelle CETTE surcharge-la, comme `$$IsRangedAttack` et les
deux sites de `$$GetAttackRangeType` ; les deux autres surcharges -- `(entity1, entity2)` et
`(tiles1, tiles2)` -- ne sont appelees que par `$$IsCharging` / `$$AreUnitsInMelee`, et par personne.)

`IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(IList, IList)` est un OU sur TOUTES les
paires ; `IdunBattle.Core.UnitPosition` est un `System.ValueType` a UN champ, une `List<IEntity>` de
tuiles (`$$.ctor(tile)` construit la liste, `$$get_MainTile` rend `list[0]`, `$$NullPosition` rend la
liste vide) ; et `IdunBattle.Entities.EntityExtensions$$GetUnitPosition(unit, state)` a pour corps
ENTIER `return GetTiles(unit, state);`.

=> **empreinte du caster x empreinte de la cible**, des DEUX cotes.

## Ce que ce probe MESURE

    --volet lecture   : le port passe-t-il des EMPREINTES ? (offline, sur le code source)
    --volet geometrie : sur des boards REELS, sur combien de configurations le verdict CHANGE
                        entre << main x main >> et << empreinte x empreinte >> ? (offline)
    --volet live      : les empreintes que le JEU publie sur un runner monte (RPC lecture pure)

Le volet GEOMETRIE porte sa CONTRE-EPREUVE : il compte aussi les configurations ou les deux
verdicts COINCIDENT, et il refuse de rendre un resultat si l'un des deux comptes est nul (un
regime degenere ne prouve rien -- ni << ca change tout >>, ni << ca ne change jamais >>).

Usage :
    python scripts/python/probe_10024_empreinte_is_melee.py --volet lecture
    python scripts/python/probe_10024_empreinte_is_melee.py --volet geometrie [--boards 40]
    python scripts/python/probe_10024_empreinte_is_melee.py --volet live --runner <N>

ASCII only.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import hexgeo                                                        # noqa: E402
from engine import battle_query as _bq                               # noqa: E402
from engine.services import battle_query as SBQ                      # noqa: E402

HOST = os.environ.get("TACTICUS_HOST", "http://127.0.0.1:8765")
RACINE = os.path.dirname(os.path.dirname(_HERE))


# --------------------------------------------------------------------------- volet LECTURE

def volet_lecture() -> int:
    """Le port passe-t-il des EMPREINTES aux trois slots freres ?

    Controle EXECUTABLE, pas un grep : on appelle les trois fonctions avec une empreinte qui
    n'est adjacente QUE par un pied non-principal, et on regarde le verdict. Le regime << main
    tile >> rend l'inverse sur les trois -- c'est la contre-epreuve integree."""
    print("VOLET LECTURE -- les trois slots freres prennent-ils l'EMPREINTE ?")
    # (0,0) et (0,2) ne sont PAS adjacents ; (0,1) l'est des deux.
    main_c, main_t = (0, 0), (0, 2)
    feet_c = [(0, 0), (0, 1)]           # empreinte du caster : son 2e pied touche la cible
    feet_t = [(0, 2), (0, 1)]           # empreinte de la cible : son 2e pied touche le caster

    assert not _bq.are_entities_adjacent(main_c, main_t), "temoin : main tiles NON adjacentes"
    assert _bq.are_entities_adjacent((0, 1), main_t), "temoin : le pied EST adjacent a la cible"

    lignes = [
        ("is_melee_attack   main x main ", SBQ.is_melee_attack(None, main_c, main_t), False),
        ("is_melee_attack   feet x main ", SBQ.is_melee_attack(None, feet_c, main_t), True),
        ("is_melee_attack   main x feet ", SBQ.is_melee_attack(None, main_c, feet_t), True),
        ("is_ranged_attack  main x main ", SBQ.is_ranged_attack(None, main_c, main_t), True),
        ("is_ranged_attack  feet x main ", SBQ.is_ranged_attack(None, feet_c, main_t), False),
        ("get_attack_range  main x main ", SBQ.get_attack_range_type(None, main_c, main_t), "Ranged"),
        ("get_attack_range  feet x main ", SBQ.get_attack_range_type(None, feet_c, main_t), "Melee"),
    ]
    rc = 0
    for nom, got, attendu in lignes:
        ok = (got == attendu)
        rc |= 0 if ok else 1
        print("   %-32s -> %-8s attendu %-8s %s" % (nom, got, attendu, "OK" if ok else "ECHEC"))
    print("   VERDICT :", "les EMPREINTES sont lues" if rc == 0 else "REGIME MAIN TILE (bug #10024)")
    return rc


# --------------------------------------------------------------------------- volet GEOMETRIE

def _charger_board(chemin: str):
    """`(elev_by_pos, jouables)` d'un board dumpe. `Tiles[col].Tile[row]`, cf. `board.py`."""
    with open(chemin, encoding="utf-8") as fh:
        brut = json.load(fh)
    b = brut.get("board") or {}
    elev, jouables = {}, set()
    for col, colonne in enumerate(b.get("Tiles") or []):
        for row, tuile in enumerate((colonne or {}).get("Tile") or []):
            if not isinstance(tuile, dict):
                continue
            if tuile.get("ForceUnplayable"):
                continue
            pos = (col, row)
            jouables.add(pos)
            elev[pos] = int(tuile.get("Elevation") or 0)
    return elev, jouables


def _empreintes_3hex(jouables: set, elev: dict) -> list:
    """Les triangles de 3 tuiles MUTUELLEMENT adjacentes -- la forme que `DutyEternal` pose
    (i2 : << Summons Galatian as a stationary unit in a 3 hex area >>) et celle que
    `snapshot._load_feet` a MESUREE live (<< Galatian, 3 pieds >> : (2,1) (2,2) (3,2)).

    On les derive de la GEOMETRIE du board (aucune constante), et on garde l'ordre des pieds :
    `feet[0]` est la main tile (`UnitPosition$$get_MainTile` = `list[0]`)."""
    out = []
    for a in sorted(jouables):
        voisins = [q for q in hexgeo.neighbors(a[0], a[1])
                   if q in jouables and _bq.are_entities_adjacent(a, q, elev)]
        for i, b in enumerate(voisins):
            for c in voisins[i + 1:]:
                if _bq.are_entities_adjacent(b, c, elev):
                    out.append([a, b, c])
    return out


def volet_geometrie(n_boards: int) -> int:
    """Sur combien de configurations le verdict CHANGE-t-il ?

    Plan : un caster d'empreinte 3-hex (le triangle de Galatian), une cible MONO-tuile balayee sur
    tout le board. Pour chaque couple on compare
        A = `AreEntitiesAdjacent(mainTile(caster), cible)`   -- le regime d'AVANT #10024
        B = `AreEntitiesAdjacent(feet(caster), cible)`       -- le natif
    et on ventile. `B` domine `A` par construction (le OU sur les paires contient la paire des
    main tiles), donc la seule divergence possible est `A=faux, B=vrai` : le port REFUSAIT une
    adjacence que le natif ACCORDE."""
    print("VOLET GEOMETRIE -- combien de configurations le verdict CHANGE-t-il ?")
    fichiers = sorted(glob.glob(os.path.join(RACINE, "data", "boards", "*", "*.json")))
    if not fichiers:
        print("   AUCUN board dumpe (data/boards/) -- MESURE IMPOSSIBLE, pas un zero.")
        return 99
    pas = max(1, len(fichiers) // max(1, n_boards))
    echantillon = fichiers[::pas][:n_boards]
    tot_acc, tot_div, tot_boards, tot_empr = 0, 0, 0, 0
    par_board = []
    for chemin in echantillon:
        elev, jouables = _charger_board(chemin)
        if len(jouables) < 10:
            continue
        empreintes = _empreintes_3hex(jouables, elev)
        if not empreintes:
            continue
        tot_boards += 1
        tot_empr += len(empreintes)
        acc = div = 0
        for feet in empreintes:
            main = feet[0]
            for cible in jouables:
                if cible in feet:
                    continue
                a = _bq.are_entities_adjacent(main, cible, elev)
                b = SBQ.are_entities_adjacent(feet, [cible], elev_by_pos=elev)
                if a and b:
                    acc += 1
                elif b and not a:
                    div += 1
                elif a and not b:                    # impossible : B domine A
                    print("   INCOHERENCE : A vrai et B faux sur", feet, cible)
                    return 1
        tot_acc += acc
        tot_div += div
        par_board.append((os.path.basename(chemin), len(empreintes), acc, div))
    if tot_boards == 0:
        print("   AUCUN board exploitable -- MESURE IMPOSSIBLE.")
        return 99
    print("   boards visites          : %d" % tot_boards)
    print("   empreintes 3-hex totales: %d" % tot_empr)
    print("   couples ACCORD (les deux disent adjacent)     : %d" % tot_acc)
    print("   couples DIVERGENTS (natif oui, main tile non) : %d" % tot_div)
    if tot_acc == 0 or tot_div == 0:
        print("   REGIME DEGENERE (un des deux comptes est nul) -- ce probe ne conclut PAS.")
        return 1
    print("   ratio divergents / (accord + divergents) : %.3f"
          % (tot_div / float(tot_acc + tot_div)))
    print("   detail (5 premiers boards) : board | empreintes | accord | divergents")
    for nom, ne, acc, div in par_board[:5]:
        print("      %-14s %6d %8d %8d" % (nom, ne, acc, div))
    print("   VERDICT : le regime est NON VIDE et NON TOTAL -- la correction change des verdicts,")
    print("             et toujours dans le sens PERMISSIF (le natif accorde plus).")
    return 0


# --------------------------------------------------------------------------- volet LIVE

def _rpc(session_id: int, methode: str, args: dict):
    import requests
    r = requests.post("%s/api/scripts/%d/rpc" % (HOST, session_id),
                      json={"method": methode, "args": args}, timeout=60)
    r.raise_for_status()
    return r.json()


def _session_vivante() -> int:
    import requests
    ss = requests.get("%s/api/sessions" % HOST, timeout=10).json()
    vivantes = [s for s in ss if s.get("status") == "running"]
    if not vivantes:
        raise SystemExit("[10024] aucune session Frida en cours -- MESURE IMPOSSIBLE")
    return int(vivantes[-1]["id"])


def volet_live(runner_id: int) -> int:
    """Les empreintes que le JEU publie -- lecture PURE (`decisionView`), aucun ecrit.

    On lit `units[].feet` (mirror `EntityExtensions$$GetTiles`, tri-etat : `null` = capteur muet,
    `[]` = mesure vide) et `mows[].{feet,platformTiles}`. C'est le seul canal qui dise combien de
    tuiles une entite occupe REELLEMENT : aucun champ de gameconfig ne porte la taille d'une unite
    (elle est fixee au spawn par la liste de tuiles passee a `AddUnitOperation`)."""
    print("VOLET LIVE -- empreintes publiees par le jeu (runner %d)" % runner_id)
    sid = _session_vivante()
    rep = _rpc(sid, "decisionView", {"runnerId": runner_id})
    vue = rep.get("result") if isinstance(rep, dict) and "result" in rep else rep
    if not isinstance(vue, dict):
        print("   REPONSE INATTENDUE :", str(rep)[:300])
        return 1
    unites = vue.get("units") or []
    mows = vue.get("mows") or []
    muets = [u.get("id") for u in unites if u.get("feet") is None]
    print("   unites : %d  (capteur `feet` MUET sur %d)" % (len(unites), len(muets)))
    multi = 0
    for u in unites:
        pieds = u.get("feet")
        if pieds is None:
            continue
        if len(pieds) > 1:
            multi += 1
        print("      u%-4s %-22s pieds=%d %s"
              % (u.get("id"), (u.get("unitId") or u.get("visualId") or "?"), len(pieds),
                 [(f.get("col"), f.get("row")) for f in pieds]))
    for m in mows:
        pieds = m.get("feet") or []
        plat = m.get("platformTiles") or []
        print("      MoW casterId=%-4s %-22s feet=%d platformTiles=%d"
              % (m.get("casterId"), (m.get("unitId") or "?"), len(pieds), len(plat)))
        if len(pieds) > 1 or len(plat) > 1:
            multi += 1
    print("   entites MULTI-TUILES sur ce runner : %d" % multi)
    if multi == 0:
        print("   -> aucune entite multi-hex ICI : ce montage n'exerce PAS #10024.")
    return 0


# --------------------------------------------------------------------------- volet CONFRONTATION

#: Le playbook TRIGGERED qui sert de RECEPTEUR a `readTriggeredGates`. Il n'a pas besoin d'etre
#: porte par le caster : `IdunBattle.AI.Playbook.TriggeredAbilityPlaybook<T>$$IsMeleeAttack(case)`
#: ne lit QUE le case (`case@+0xf0` ability, `+0x10` caster, `+0x18` casterPosition, `+0x20` target)
#: et le relaie a `IBattleQuery` slot 2 -- le playbook n'est que le `this` de la methode generique.
_TRIGGERED_RECEPTEUR = 1103        # `TriggeredAbilityType.LightImUp`


def volet_confrontation(runner_id: int, caster_id: int, target_id: int, tuiles: list) -> int:
    """NATIF vs PORT sur le MEME slot 2, tuile par tuile.

    ORACLE NATIF : `ncPlaybookPredict(abilityKind="triggered", col, row)` rend `gates.isMeleeAttack`,
    LU sur le `UtilityAttackCase` reellement soumis, AVANT toute invocation d'utilite -- donc une
    erreur en aval (`itération IEnumerator<Fix64>`) ne la salit pas. La chaine native est
    `TriggeredAbilityPlaybook<T>$$IsMeleeAttack(case)` -> `IBattleQuery` slot 2 =
    `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack`, et le `casterPosition` du case est
    `unitPositionAtTile(caster, tile)` = `IdunBattle.Entities.EntityExtensions$$GetUnitPositionsAtTiles`.

    ORACLE PORT : `engine.runner.battle_query_state.is_melee_attack` sur l'etat charge du MEME
    runner, avec `caster_position` = l'empreinte du caster POSE sur cette tuile.

    CONTRE-EPREUVE INTEGREE : le meme port en regime MAIN TILE (la cible reduite a `feet[0]`) --
    c'est EXACTEMENT le port d'avant #10024. Il doit DIVERGER sur au moins une tuile, sinon le
    montage ne prouve rien."""
    print("VOLET CONFRONTATION -- natif vs port, slot 2, runner %d" % runner_id)
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner import battle_query_state as BQS

    sid = _session_vivante()

    def rpc(m, a, t=120):
        import requests
        r = requests.post("%s/api/scripts/%d/rpc" % (HOST, sid),
                          json={"method": m, "args": a}, timeout=t)
        r.raise_for_status()
        rep = r.json()
        return rep.get("result") if isinstance(rep, dict) and "result" in rep else rep

    dv = rpc("decisionView", {"runnerId": runner_id, "allAbilities": True, "maxRank": 32}, 180)
    ob = rpc("observeBattle", {"runnerId": runner_id}, 60)
    snap = rpc("combatSnapshot", {"runnerId": runner_id}, 60)
    bg = rpc("boardGraph", {"runnerId": runner_id}, 60)
    if not (isinstance(bg, dict) and "tiles" in bg):
        print("   boardGraph indisponible -- MESURE IMPOSSIBLE, pas un zero.")
        return 99
    state = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))

    pieds_cible = BQS.unit_tiles(state, target_id)
    pieds_caster_courants = BQS.unit_tiles(state, caster_id)
    print("   cible  u%d : empreinte %s (main tile %s)"
          % (target_id, pieds_cible, pieds_cible[0] if pieds_cible else None))
    print("   caster u%d : empreinte %s (main tile %s)"
          % (caster_id, pieds_caster_courants,
             pieds_caster_courants[0] if pieds_caster_courants else None))
    # `AreEntitiesAdjacent(tiles, unit)` lit les DEUX empreintes : il suffit que L'UNE des deux
    # soit multi-tuiles pour que #10024 soit exerce. Exiger la CIBLE fermerait l'axe INVERSE
    # (un caster multi-hex contre une cible mono-tuile), qui est le meme ecart par l'autre bout.
    if len(pieds_cible) < 2 and len(pieds_caster_courants) < 2:
        print("   LES DEUX ENTITES SONT MONO-TUILE -- ce montage n'exerce PAS #10024,")
        print("   on ne conclut PAS.")
        return 1
    nom = BQS.normal_attack_name(state, caster_id)
    print("   ability soumise au slot 2 : %s (attaque normale concrete du caster)" % nom)

    n_div_avant, n_acc = 0, 0
    lignes = []
    for tuile in tuiles:
        # `None` = AUCUN `col`/`row` -> le hook prend `unitPositionCurrent(caster)`, c'est-a-dire
        # `IdunBattle.Entities.EntityExtensions$$GetUnitPosition` = l'EMPREINTE du caster. C'est
        # l'axe INVERSE : un caster MULTI-HEX contre une cible mono-tuile.
        args = {"runnerId": runner_id, "unitId": caster_id,
                "abilityType": _TRIGGERED_RECEPTEUR, "abilityKind": "triggered",
                "targetId": target_id, "attackAbility": "normalAttack"}
        if tuile is not None:
            args["col"], args["row"] = tuile[0], tuile[1]
        rep = rpc("ncPlaybookPredict", args, 120) or {}
        gates = rep.get("gates") or {}
        natif = gates.get("isMeleeAttack")
        etiquette = tuile if tuile is not None else "current"
        if natif is None:
            lignes.append((etiquette, None, None, None, (rep.get("error") or "")[:48]))
            continue
        pieds_caster = [tuile] if tuile is not None else BQS.unit_tiles(state, caster_id)
        port = BQS.is_melee_attack(state, nom, caster_id, target_id,
                                   caster_position=pieds_caster)
        # CONTRE-EPREUVE : le port d'AVANT #10024, restitue LITTERALEMENT -- deux TUPLES passes au
        # service, c'est-a-dire main tile du caster x main tile de la cible (`unit_position`).
        neigh, elev = BQS.board_maps(state)
        avant = SBQ.is_melee_attack(nom, pieds_caster[0] if pieds_caster else None, pieds_cible[0],
                                    elev_by_pos=elev,
                                    force_ranged_attack=BQS.force_ranged_attack(state, caster_id),
                                    neigh_by_pos=neigh)
        lignes.append((etiquette, natif, port, avant, ""))
        if natif == port:
            n_acc += 1
        if natif != avant:
            n_div_avant += 1
    print("   tuile     natif  port(APRES)  port(AVANT, main tile)  note")
    rc = 0
    for tuile, natif, port, avant, note in lignes:
        if natif is None:
            print("      %-9s  --     --           --                     %s" % (str(tuile), note))
            continue
        mark = "OK " if natif == port else "ECHEC"
        if natif != port:
            rc = 1
        print("      %-9s  %-5s  %-11s  %-22s  %s" % (str(tuile), natif, port, avant, mark))
    print("   accords natif==port(APRES) : %d" % n_acc)
    print("   tuiles ou le port d'AVANT DIVERGE du natif : %d" % n_div_avant)
    if n_div_avant == 0:
        print("   CONTRE-EPREUVE VIDE : ce montage ne discrimine pas -- on ne conclut PAS.")
        return 1
    print("   VERDICT :", "port == natif, et l'ancien regime est REFUTE" if rc == 0
          else "PORT != NATIF")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volet", choices=["lecture", "geometrie", "live", "confrontation"],
                    required=True)
    ap.add_argument("--boards", type=int, default=40)
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--caster", type=int, default=None)
    ap.add_argument("--target", type=int, default=None)
    ap.add_argument("--tuiles", default="",
                    help="col,row;col,row;... (volet confrontation). Le jeton `current` interroge "
                         "la position COURANTE du caster (= son EMPREINTE via "
                         "`EntityExtensions$$GetUnitPosition`) -- c'est l'axe INVERSE, un caster "
                         "MULTI-HEX contre une cible mono-tuile.")
    a = ap.parse_args()
    if a.volet == "lecture":
        return volet_lecture()
    if a.volet == "geometrie":
        return volet_geometrie(a.boards)
    if a.runner is None:
        raise SystemExit("[10024] ce volet exige --runner <N>")
    if a.volet == "live":
        return volet_live(a.runner)
    if a.caster is None or a.target is None or not a.tuiles:
        raise SystemExit("[10024] --volet confrontation exige --caster --target --tuiles")
    tuiles = [None if t.strip() == "current" else tuple(int(x) for x in t.split(","))
              for t in a.tuiles.split(";") if t.strip()]
    return volet_confrontation(a.runner, a.caster, a.target, tuiles)


if __name__ == "__main__":
    raise SystemExit(main())
