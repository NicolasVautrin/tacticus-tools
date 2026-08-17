"""#590-r6-r1 -- CONFRONTATION LIVE du clamp melee sur une unite MULTI-HEX.

LA QUESTION, ET POURQUOI ELLE NE SE POSE QU'EN MULTI-HEX
---------------------------------------------------------
`IdunBattle.Core.Services.DamageCalculations$$ShouldApplyRangedInMelee` boucle sur TOUTES les
tuiles du caster (`foreach (attackerTile in attackerTiles)`) et resout l'occupant de chaque voisine
par `IdunBattle.Entities.UnitExtensions$$GetUnit(adj, state)`, qui remonte de N'IMPORTE QUEL pied a
son unite. Le port lisait la MAIN TILE des DEUX cotes. Sur une unite a 1 pied les deux formes
coincident EXACTEMENT : seule une empreinte multi-hex peut les separer.

LE MONTAGE, ET LE FAIT QUI LE REND POSSIBLE
---------------------------------------------
L'empreinte n'est PAS une propriete de l'unite -- elle vient du BOARD (mesure #894-r2 /
`probe_10018r1_bossunit_footprint.py`) : `GB_Belisarius_01` porte
`BossPlatforms = [{Size: 3, Tiles: [(3,7), (2,7), (3,8)]}]`, et
`IdunBattle.Operations.SetupGameOperation$$AddBossUnit` spawne `BC.BossUnit.UnitId` sur la LISTE de
tuiles de la plateforme. **N'IMPORTE QUELLE unite amenee par ce canal a donc 3 pieds** -- ce qui
permet de choisir un porteur RANGED, condition sans laquelle le test serait DEGENERE :

  * `admecBossBelisarius`, le porteur << naturel >> de ce board, a une arme SANS `Range` -> portee
    1, et il n'est pas ranged -> `onlyAdjacent` est deja vrai AVANT tout clamp. Les deux champs que
    le clamp ecrit y sont donc INDISTINGUABLES : mesure faite, montage ecarte ;
  * `necroWarden` a `weapons[].Range = 3` -> `UnitExtensions$$IsRanged` vrai -> avec le preset
    generique (`onlyAdjacent = IfNotRangedCaster`, `forceMeleeTarget = IfRangedCaster`) la portee
    vaut 3 et `onlyAdjacent` est FAUX sans clamp, VRAI avec. La bascule porte sur les DEUX champs.

GEOMETRIE (derivee de `hexgeo`, verifiee au montage) :

    pieds du caster  : (3,7) MAIN, (2,7), (3,8)
    E1 en (2,8)      : voisine de (2,7) ET (3,8), **PAS** de la MAIN TILE  -> arme le clamp
    E2 en (5,7)      : a distance 2 de TOUS les pieds                      -> dans la portee 3,
                                                                              hors adjacence

CE QUI ME FERAIT CONCLURE QUE LE PORT DIVERGE -- ENONCE AVANT LE MONTAGE

  D1  Le natif ACCEPTE E2 alors que E1 est au contact d'un pied non principal -> le natif ne
      bouclerait pas sur `attackerTiles`, et c'est le PORT CORRIGE qui serait faux.
  D2  Le natif REFUSE E2 mais le port l'accepte -> le port n'a pas arme le clamp (l'ecart PERMISSIF
      du residu, tel qu'il etait AVANT cette tranche).
  D3  Le TEMOIN (meme montage, E1 retire) refuse E2 des deux cotes -> regime DEGENERE : ce ne
      serait pas le clamp qui deciderait mais la geometrie ou la portee. Le probe le DIT et rend
      rc 1 plutot que de conclure.

Usage :
    python probe_590r6r1_clamp_melee_multihex_live.py             # les deux bras
    python probe_590r6r1_clamp_melee_multihex_live.py --temoin    # le bras SANS E1 seulement

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import hexgeo                                                            # noqa: E402
from rl_collect_batch import _resolve_session, _rpc, PLAYER_ID_HUMAN     # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner.snapshot import load_state                            # noqa: E402
import engine.runner.abilities.targeting as T                            # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402

BOARD = "GB_Belisarius_01"
PORTEUR = "necroWarden"          #: RANGED (`weapons[].Range = 3`) -- cf. l'encadre ci-dessus
BOUCHE_TROU = "admecMarshall"    #: `initAndStart` exige des `playerUnits` ; le boss n'y est PAS
ENNEMI = "ultraTitus"
NORMAL_ATTACK = 69               #: `ActiveAbilityType.Loki_NormalAttack`, l'id CONCRET

PIEDS = [(3, 7), (2, 7), (3, 8)]     #: `BossPlatforms[0].Tiles`, LU dans `data/boards/global/`
E1 = (2, 8)                          #: voisine d'un pied NON PRINCIPAL seulement
E2 = (5, 7)                          #: a distance 2 de TOUS les pieds
E0 = (4, 7)                          #: voisine de la MAIN TILE -- l'ETAGE du dessous (cf. `--main`)


def _r(sid, method, body, t=120):
    return (_rpc(sid, method, [body], timeout=t) or {}).get("result") or {}


def _seed_bc(dest: Path) -> Path:
    """Copie du seed BC partage, `BossUnit` RENSEIGNE. N'ecrit JAMAIS le seed partage."""
    bc = copy.deepcopy(json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8")))
    bc["BossUnit"] = {"Id": PLAYER_ID_HUMAN, "UnitId": PORTEUR,
                      "Health": None, "RemainingHealth": None, "Modifiers": []}
    dest.write_text(json.dumps(bc), encoding="utf-8")
    return dest


def _build(sf: Path, proche, seed: int) -> int:
    """`proche` = la tuile ou poser le 2e ennemi (E1 ou E0), ou `None` pour le TEMOIN."""
    bc = _seed_bc(sf.with_name(sf.stem + "-bc.json"))
    places = ["--a-place", "%s:%d,%d" % (ENNEMI, E2[0], E2[1])]
    a_units = [ENNEMI]
    if proche is not None:
        a_units.append(ENNEMI)
        places += ["--a-place", "%s:%d,%d" % (ENNEMI, proche[0], proche[1])]
    # PAS de `--explicit-stats` : il est reserve aux porteurs NPC/SUMMON (la formule heros LEVE sur
    # eux). `necroWarden` est un HEROS du pool -- il passe par la formule normale, et l'ajouter
    # rendait `--explicit-stats necroWarden: 0` (mesure du premier jet).
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", BOARD,
           "--state-file", str(sf), "--no-ai",
           "--p-units", BOUCHE_TROU, "--seed-bc", str(bc),
           "--a-units", ",".join(a_units), *places]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    if not sf.exists():
        raise RuntimeError("build KO (rc=%d) : %s" % (p.returncode, (p.stderr or p.stdout)[-900:]))
    return int(json.loads(sf.read_text(encoding="utf-8"))["runnerId"])


def _capture(sid, rid):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 90)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 120)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    return dv, ob, snap, bg


def _mesure(sid, rid, proche) -> dict:
    dv, ob, snap, bg = _capture(sid, rid)
    st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    from engine.runner.components import get_unit_feet                   # noqa: PLC0415
    porteur = None
    for u in (dv.get("units") or []):
        pieds = sorted((f["col"], f["row"]) for f in (u.get("feet") or [])) or None
        if pieds is not None and len(pieds) == 3 and set(pieds) == set(PIEDS):
            porteur = u
            break
    if porteur is None:
        vus = [(u.get("id"), u.get("visualId"), len(u.get("feet") or []),
                (u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
               for u in (dv.get("units") or [])]
        raise RuntimeError("aucune unite a 3 pieds sur la plateforme : %r" % (vus,))
    cid = int(porteur["id"])
    out = {"caster": cid, "feet_dv": sorted((f["col"], f["row"]) for f in porteur["feet"]),
           "feet_port": sorted(get_unit_feet(st, cid)),
           "main_port": (get_unit_feet(st, cid) or [None])[0],
           "type_attaque": T.normal_attack_type_for(st, cid),
           "is_ranged": T.unit_is_ranged(st, cid),
           "clamp_port": T.should_apply_ranged_in_melee(st, cid), "cibles": []}
    opts = T.normal_attack_targeting_options(st, cid)
    rr = T.get_range(st, cid, opts)
    out["range_port"] = (rr.value, rr.only_adjacent) if rr is not None else None

    # ================================================================================
    # LE CAPTEUR QUI PORTE L'EMPREINTE COMPLETE, ET POURQUOI CE N'EST PAS `abilityReason`
    # ================================================================================
    # `abilityReason` appelle la surcharge **`IEntity`** d'`AttackQuery$$GetInvalidTargetReason`
    # avec `getUnitMainTile(caster)` (LU dans `frida/hooks/features/ai-step/rpc-targeting.ts`).
    # Cette surcharge-la fait `UnitPosition..ctor(&pos, attackerTile)` puis, plus bas,
    # `TargetingQuery$$GetInvalidTargetReason(caster, casterTile, ...)` -> `TExtensions.ToList(
    # casterTile)`. Le natif n'y voit donc **QU'UNE TUILE** : ce capteur mesure, par construction,
    # le regime MONO-HEX -- exactement ce que le port faisait AVANT #590-r6-r1. Il ne peut pas voir
    # l'ecart, et un desaccord avec lui n'est PAS une divergence de moteur.
    # `abilityTargets.fromHere`, lui, appelle `AttackQuery$$GetValidTargets(unit,
    # UnitPosition{Tiles = GetTiles(unit, state)}, ability)` -- l'EMPREINTE COMPLETE, la meme que
    # celle que la cascade du jeu passe. C'est LUI le capteur de cette tranche ; l'autre est garde
    # comme TEMOIN de la voie mono-tuile, et son desaccord attendu est CHIFFRE.
    at = _r(sid, "abilityTargets", {"runnerId": rid, "unitId": cid,
                                    "abilityType": NORMAL_ATTACK, "allAbilities": True}, 180)
    from_here = None
    out["at_diag"] = {"ok": at.get("ok"), "err": at.get("error"),
                      "fromHereResolved": at.get("fromHereResolved"),
                      "unitIds": [u.get("unitId") for u in (at.get("units") or [])]}
    for u in (at.get("units") or []):
        if int(u.get("unitId", -1)) != cid:
            continue
        for ab in (u.get("abilities") or []):
            if int(ab.get("abilityId", -1)) == NORMAL_ATTACK:
                # ⚠ la cle est `targetId` -- ni `unitId`, ni `squadId` : `mapTargets` publie
                # `units -> squadId/visualId/pos`. Mesure du premier jet : `fromHereCount = 1`
                # avec une liste LUE vide -- un zero qui n'etait pas une mesure.
                from_here = sorted(int(t["targetId"]) for t in (ab.get("fromHere") or [])
                                   if t.get("targetId") is not None)
                out["at_diag"]["ab"] = {k: ab.get(k) for k in
                                        ("abilityId", "ability", "kind", "targetCount",
                                         "fromHereCount", "usable", "err")}
                out["at_diag"]["targets"] = sorted(
                    int(t["targetId"]) for t in (ab.get("targets") or [])
                    if t.get("targetId") is not None)
    out["from_here_natif"] = from_here
    out["from_here_port"] = sorted(int(x) for x in
                                   (T.valid_normal_attack_targets(st, cid) or []))

    for u in (dv.get("units") or []):
        if int(u["id"]) == cid or u.get("owner") == porteur.get("owner"):
            continue
        pos = (int(u["pos"]["col"]), int(u["pos"]["row"]))
        nat = _r(sid, "abilityReason", {"runnerId": rid, "casterId": cid,
                                        "abilityType": NORMAL_ATTACK,
                                        "targetId": int(u["id"])}, 90)
        port = int(T.get_invalid_target_reason(st, cid, int(u["id"]),
                                               T._NormalAttackTargeting(opts)) or 0)
        rz = (nat.get("targetReason") or {})
        out["cibles"].append({
            "id": int(u["id"]), "pos": pos,
            "d_min": min(hexgeo.distance(pos, f) for f in PIEDS),
            "adjacent_main": pos in set(hexgeo.neighbors(*PIEDS[0])),
            # ⚠ `ok` est TROMPEUR : mesure faite, il reste `True` sur un refus. C'est le HEX de
            # `targetReason` qui porte le verdict (`0x0` = cible valide).
            "natif_hex": int(str(rz.get("hex") or "0x0"), 16),
            "natif_reasons": rz.get("reasons") or [],
            "port": port})
    out["proche"] = proche
    return out


def _run(proche, seed: int) -> dict:
    sid = _resolve_session()
    tag = "temoin" if proche is None else ("%d%d" % proche)
    sf = ROOT / "logs" / "runners" / ("p590r6r1-%s-%s.json" % (tag, uuid.uuid4().hex[:6]))
    sf.parent.mkdir(parents=True, exist_ok=True)
    rid = _build(sf, proche, seed)
    try:
        return dict(_mesure(sid, rid, proche), rid=rid)
    finally:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(sf)],
                       cwd=str(PYDIR), capture_output=True, text=True, timeout=180)


def _imprime(m: dict) -> None:
    p = m["proche"]
    print("=== bras %s (runner %s) ==="
          % ("TEMOIN sans ennemi proche" if p is None
             else ("ennemi proche en %r (%s)"
                   % (p, "MAIN TILE" if p in set(hexgeo.neighbors(*PIEDS[0]))
                      else "pied NON PRINCIPAL")), m["rid"]))
    print("  caster u%s  feet(dv)=%r  feet(port)=%r  main(port)=%r"
          % (m["caster"], m["feet_dv"], m["feet_port"], m["main_port"]))
    print("  attaque normale=%r  is_ranged(port)=%r  clamp(port)=%r  get_range(port)=%r"
          % (m["type_attaque"], m["is_ranged"], m["clamp_port"], m["range_port"]))
    print("  EMPREINTE COMPLETE  fromHere natif=%r  port=%r"
          % (m["from_here_natif"], m["from_here_port"]))
    print("  diag abilityTargets : %r" % (m.get("at_diag"),))
    for c in m["cibles"]:
        print("   cible u%-4s pos=%-8s d_min=%d adj_main=%-5s | MONO-TUILE natif hex=0x%08x %-18s"
              " | port(empreinte)=0x%08x"
              % (c["id"], c["pos"], c["d_min"], c["adjacent_main"],
                 c["natif_hex"], ",".join(c["natif_reasons"]) or "-", c["port"]))


def _cible(m: dict, pos):
    for c in m["cibles"]:
        if c["pos"] == pos:
            return c
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--temoin", action="store_true", help="le bras SANS ennemi proche seulement")
    ap.add_argument("--main", action="store_true",
                    help="l'ETAGE DU DESSOUS : l'ennemi proche en E0, ADJACENT A LA MAIN TILE. Il "
                         "separe << le natif ne boucle pas sur les pieds >> de << le natif n'arme "
                         "pas ce clamp du tout >>, ce qu'aucun bras multi-hex ne peut faire.")
    ap.add_argument("--seed", type=int, default=777)
    a = ap.parse_args()

    # La geometrie est DERIVEE, jamais recopiee : un board qui bougerait doit faire ROUGIR ici.
    vm = set(hexgeo.neighbors(*PIEDS[0]))
    autres = set(hexgeo.neighbors(*PIEDS[1])) | set(hexgeo.neighbors(*PIEDS[2]))
    if E1 in vm or E1 not in autres:
        print("MONTAGE INVALIDE : E1=%r n'est plus << voisine d'un pied NON PRINCIPAL seulement >>"
              % (E1,))
        return 1
    if min(hexgeo.distance(E2, f) for f in PIEDS) != 2:
        print("MONTAGE INVALIDE : E2=%r n'est plus a distance 2 de tous les pieds" % (E2,))
        return 1

    temoin = _run(None, a.seed)
    _imprime(temoin)
    if a.temoin:
        return 0
    if a.main:
        etage = _run(E0, a.seed)
        print("")
        _imprime(etage)
        t2, e2 = _cible(temoin, E2), _cible(etage, E2)
        print("")
        print("=== ETAGE DU DESSOUS : le clamp s'arme-t-il DEPUIS LA MAIN TILE ? ===")
        print("  Il separe << le natif ne boucle pas sur les pieds >> de << ce capteur-ci ne voit")
        print("  qu'une tuile >>. Les DEUX capteurs doivent basculer ici, puisque la tuile qui")
        print("  declenche est justement celle qu'ils partagent.")
        print("  MONO-TUILE (abilityReason) sur E2 : TEMOIN hex=0x%08x -> MAIN hex=0x%08x %r"
              % (t2["natif_hex"], e2["natif_hex"], e2["natif_reasons"]))
        print("  EMPREINTE  (fromHere)        sur E2 : TEMOIN %r -> MAIN %r"
              % (temoin["from_here_natif"], etage["from_here_natif"]))
        print("  port : clamp %r -> %r ; get_range %r -> %r ; targets %r -> %r"
              % (temoin["clamp_port"], etage["clamp_port"],
                 temoin["range_port"], etage["range_port"],
                 temoin["from_here_port"], etage["from_here_port"]))
        return 0
    avec = _run(E1, a.seed)
    print("")
    _imprime(avec)

    print("")
    print("=== VERDICT -- capteur EMPREINTE COMPLETE (`abilityTargets.fromHere`) ===")
    rc = 0
    t2, a2 = _cible(temoin, E2), _cible(avec, E2)
    a1 = _cible(avec, E1)
    if t2 is None or a2 is None or a1 is None:
        print("  MESURE INCOMPLETE : E2 temoin=%r / E2 avec=%r / E1=%r" % (t2, a2, a1))
        return 1
    if temoin["from_here_natif"] is None or avec["from_here_natif"] is None:
        print("  CAPTEUR MUET : `abilityTargets.fromHere` n'a rien rendu -- rien n'est confronte.")
        return 1
    # D3 -- regime DEGENERE : sans ennemi proche, le natif doit ACCEPTER E2 (portee 3, d = 2)
    if a2["id"] not in temoin["from_here_natif"]:
        print("  D3 REGIME DEGENERE : le natif refuse deja E2 SANS clamp (fromHere=%r) -- ce "
              "montage ne mesure pas le clamp." % (temoin["from_here_natif"],))
        rc = 1
    # D1 -- le natif doit REFUSER E2 quand E1 est au contact d'un pied NON PRINCIPAL
    if a2["id"] in avec["from_here_natif"]:
        print("  D1 : le natif ACCEPTE E2 malgre E1 au contact d'un pied non principal -- la "
              "boucle sur `attackerTiles` ne serait pas ce que le decompile dit (fromHere=%r)."
              % (avec["from_here_natif"],))
        rc = 1
    # D2 -- le port doit rendre EXACTEMENT le meme ensemble, dans LES DEUX bras
    for nom, m in (("TEMOIN", temoin), ("AVEC E1", avec)):
        if m["from_here_natif"] != m["from_here_port"]:
            print("  D2 DIVERGENCE (%s) : natif fromHere=%r / port=%r"
                  % (nom, m["from_here_natif"], m["from_here_port"]))
            rc = 1
    if not avec["clamp_port"]:
        print("  le port n'arme PAS le clamp dans le bras AVEC E1 : `should_apply_ranged_in_melee` "
              "rend False alors qu'un ennemi touche un pied non principal.")
        rc = 1
    if temoin["clamp_port"]:
        print("  le port arme le clamp dans le TEMOIN : la bascule ne vient pas de E1.")
        rc = 1
    if rc == 0:
        print("  OK -- clamp(port) %r -> %r ; get_range(port) %r -> %r ; natif fromHere %r -> %r"
              % (temoin["clamp_port"], avec["clamp_port"],
                 temoin["range_port"], avec["range_port"],
                 temoin["from_here_natif"], avec["from_here_natif"]))
    print("")
    print("=== TEMOIN du capteur MONO-TUILE (`abilityReason`, `getUnitMainTile`) ===")
    print("  Son desaccord est ATTENDU et il est le POINT : ce capteur passe la MAIN TILE seule au")
    print("  natif, donc il mesure le regime que #590-r6-r1 corrige. Sur E2 :")
    print("     TEMOIN  hex=0x%08x %r" % (t2["natif_hex"], t2["natif_reasons"]))
    print("     AVEC E1 hex=0x%08x %r  (pied NON principal -> le natif mono-tuile ne voit rien)"
          % (a2["natif_hex"], a2["natif_reasons"]))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
