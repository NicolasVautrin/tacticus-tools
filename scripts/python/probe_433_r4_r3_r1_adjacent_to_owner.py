"""probe #433-r4-r3-r1 -- CONFRONTER LIVE le corps PARTAGE d'`AdjacentToOwnerNonOwnerPlaybook<T>`.

CE QUE CE PROBE MESURE
----------------------
Les dix concrets de cette famille PARTAGENT leur `CalculateMovementUtilityInSteps` (un unique corps
gshared) et ne different que par `GetAdjacencyUtility`. Confronter le corps partage une fois vaut
donc pour les dix ; confronter en plus UN `GetAdjacencyUtility` gate prouve la face variable.

  ETAPE A -- `WatchedOver` (1524, poids 20, AUCUN gate sur le mover). Meme forme que le montage
             `PsychicFortress` de #433-r4-r3, et donc meme critere de preuve : un CHANGEMENT DE
             TUILE. On classe les tuiles candidates d'un mover SANS le terme, on DEPLACE le
             porteur sur une tuile voisine NATIVE de la deuxieme (et pas de la premiere), et on
             demande au natif ce qu'il joue. Le couple n'est retenu que si l'ecart sans terme est
             INFERIEUR au poids -- sinon le terme ne pourrait rien renverser et la mesure ne
             prouverait rien.

  ETAPE B -- `PrimarchOfTheFirstLegion` (poids 20, gate `HasFaction(movingUnit, DarkAngels)`).
             Deux resultats en un :
               1. le GATE : meme position du porteur, le terme vaut le poids sur les tuiles
                  adjacentes pour un mover Dark Angels et EXACTEMENT 0 partout pour un mover qui
                  ne l'est pas (balayage complet, pas un echantillon) ;
               2. la CLE DE REGISTRE. Le `.ctor` de cette classe passe `0x5b6` = 1462 =
                  `NetherRealmCasket` (copier-coller du jeu) alors que l'enum la numerote 1511.
                  `probe_433_r4_r3_r1_non_owner_registry.py` tranche OFFLINE que le site
                  d'enregistrement utilise 1511. Cette etape le tranche INDEPENDAMMENT et EN VIVANT :
                  on greffe l'ability **1511** sur le porteur ; si le registre natif n'y avait pas
                  d'entree, `IdunBattle.AI.PlaybookDatabase$$LoadPlaybookNonOwner(1511)` rendrait
                  null, le natif ignorerait le terme, et il ne suivrait PAS le changement de tuile.

MONTAGE -- la GREFFE, et pourquoi elle est LEGITIME ici
-------------------------------------------------------
Aucun des dix porteurs n'arrive en bataille avec son ability par la voie ordinaire :
  * `necroOverlord` (`MyWillBeDoneOverlord`) est le SEUL hero du pool a porter un de ces passifs
    nativement -- et son entree `BC.Units` est PERIMEE (`catalog_inject.STALE_UNIT_ENTRIES`,
    #254-bc/#392-r1) : tout runner bati sur ce seed le deploie avec le kit de `gqfc5mff6c`, donc
    SANS `MyWillBeDoneOverlord`. Le terme y serait inerte des DEUX cotes.
  * trois autres passent par la voie RELIQUE (`AmuletOfTheVoidwyrm`, `NetherRealmCasket`,
    `RelicOfLostCadia`), les autres par des heros hors pool ou des npc.

On greffe donc (`catalog_inject.graft_passive_ability`, `replace=True`) sur une unite DU POOL. La
regle « npc GREFFABLE » du `CLAUDE.md` demande de VERIFIER que l'utilite ne lit ni stat ni trait du
CASTER : les dix `GetAdjacencyUtility` ont ete lus un par un, et tous ne lisent que `movingUnit`
(traits ou faction) -- jamais `owner`, jamais l'etat. La greffe est donc fidele, pas commode.
`replace=True` vide les autres passifs du greffon : c'est ce qui isole la mecanique mesuree.

⚠ PIEGE #271, verifie : les deux cles jouees ici (`WatchedOver_AdjacentFriends`,
`PrimarchOfTheFirstLegion_AdjacentDarkAngels`) valent 20 dans la CAPTURE `data/seed-bc.json` COMME
au gameconfig VIVANT. Quatre autres cles de la famille (IconOfObstinacy, MyWillBeDoneOverlord et
les deux de PropheticSentinel) sont ABSENTES de la capture : un montage bati sur ce seed les
rendrait inertes des deux cotes, et l'accord y serait vide de sens. C'est pourquoi ce probe ne les
joue PAS.

Usage (ASCII only) :
  python probe_433_r4_r3_r1_adjacent_to_owner.py --offline-only
  python probe_433_r4_r3_r1_adjacent_to_owner.py --seed 777 --board MC1_67
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_collect_batch import _resolve_session, _rpc                       # noqa: E402
from probe_433_r4_r3_non_owner_playbooks import (_ctx_for, _dispose,      # noqa: E402
                                                 _r, _score_map)

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

WATCHED_OVER = 1524                # TriggeredAbilityType.WatchedOver (0x5f4)
PRIMARCH = 1511                    # TriggeredAbilityType.PrimarchOfTheFirstLegion
KEY_WO = "WatchedOver_AdjacentFriends"                       # capture=20, gameconfig vivant=20
KEY_PR = "PrimarchOfTheFirstLegion_AdjacentDarkAngels"       # capture=20, gameconfig vivant=20
DARK_ANGELS = 10                   # UnitFaction.DarkAngels

# Greffon : une unite DU POOL, dont `replace=True` vide les autres passifs. `astraBullgryn` est
# aussi le mover du montage #433-r4-r3, donc un terrain deja eprouve sur ce board.
CARRIER = "astraBullgryn"
# Roster CRAFTE : le greffon + DEUX movers de factions differentes (`darkaAzrael` EST Dark Angels,
# `necroWarden` et `orksNob` ne le sont pas) -- c'est ce couple qui rend le gate de l'etape B
# OBSERVABLE au lieu de le supposer.
DEFAULT_P = "astraBullgryn,darkaAzrael,necroWarden,orksNob,orksWarboss"
DEFAULT_A = "worldKharn,templChampion,tauMarksman"
DEFAULT_BOARD = "MC1_67"
DEFAULT_SEED = "777"


class MontageError(RuntimeError):
    """Le montage n'a pas pu etre etabli -- JAMAIS confondu avec un desaccord natif/port."""


def write_grafted_bc(out_path: Path, ability_name: str, carrier: str = CARRIER) -> Path:
    """Seed BC ou `carrier` porte le passif `ability_name` et RIEN d'autre.

    Les deux ecritures de `graft_passive_ability` : l'id dans `BC.Units[carrier].PassiveAbilities`
    (sans lui `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` ne monte rien, en
    silence) ET la config dans `BC.Abilities.PassiveAbilities` (sans elle, « system error » au
    montage -- meme verrou que #226).
    """
    import catalog_inject as CI
    bc = CI._load_seed(None)
    rep = CI.graft_passive_ability(bc, carrier, ability_name, replace=True)
    node = (bc.get("Abilities") or {}).get("PassiveAbilities") or {}
    if ability_name not in node:
        raise MontageError("config %s absente de BC.Abilities.PassiveAbilities" % ability_name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bc), encoding="utf-8")
    return rep


def _build_seedbc(seed, board, p_units, a_units, seed_bc: Path):
    """Runner ISOLE sur un seed BC CUSTOM. State-file ABSOLU a nom unique (`runner.md` §3)."""
    state = ROOT / "logs" / "runners" / ("p433r4r3r1-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--state-file", str(state), "--p-units", p_units, "--a-units", a_units,
            "--seed-bc", str(seed_bc)]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-900:]
    return json.loads(state.read_text())["runnerId"], None


# --------------------------------------------------------------------------------------------
# ETAPE 0 -- garde de montage : les poids joues sont-ils NON NULS, capture ET gameconfig ?
# --------------------------------------------------------------------------------------------
def step0_weights(verbose=True) -> int:
    import contextlib
    import io
    from engine import weights as W

    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    cap = ((bc.get("Utilities") or {}).get("Default") or {}).get("TriggeredAbilitiesNonOwner") or {}
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        wt = W.load()
    if "REPLI sur BC.Utilities" in err.getvalue():
        print("[etape0] REFUS : `engine.weights.load` est retombe sur la table de la CAPTURE.")
        return 1
    rc = 0
    for k in (KEY_WO, KEY_PR):
        c, l = cap.get(k), wt.sub("TriggeredAbilitiesNonOwner", k)
        if verbose:
            print("[etape0] %-46s capture=%-5s moteur=%s" % (k, c, l))
        if not l:
            print("[etape0] REFUS : %s vaut 0 cote moteur -- terme inerte." % k)
            rc = 1
        elif c is None or float(c) != float(l):
            print("[etape0] REFUS : %s DIVERGE capture(%s)/gameconfig(%s) -- piege #271, le "
                  "montage bati sur ce seed ne mesurerait pas ce que joue le natif." % (k, c, l))
            rc = 1
    if rc == 0 and verbose:
        print("[etape0] OK : les deux poids sont NON NULS et IDENTIQUES capture/gameconfig.")
    return rc


# --------------------------------------------------------------------------------------------
# Coeur : le montage « CHANGEMENT DE TUILE », parametre par l'ability greffee
# --------------------------------------------------------------------------------------------
def run_tile_flip(ability: int, ability_name: str, key: str, *, seed=DEFAULT_SEED,
                  board=DEFAULT_BOARD, p_units=DEFAULT_P, a_units=DEFAULT_A,
                  mover_faction: int | None = None, verbose=False) -> dict:
    """Cherche un couple discriminant puis mesure le natif sur un runner NEUF.

    `mover_faction` restreint la recherche aux movers de cette faction -- necessaire des que le
    `GetAdjacencyUtility` de l'ability porte un gate, sinon la recherche echouerait sur les movers
    gates DEHORS et le rapport serait ambigu.
    """
    from engine import weights as W
    from engine.utilities.tile import faction_value, tile_leaf_ctx

    sid = _resolve_session()
    if not sid:
        return {"error": "aucune session Frida"}
    wt = W.load()
    w = float(wt.sub("TriggeredAbilitiesNonOwner", key))
    if w <= 0:
        return {"error": "%s vaut 0 cote moteur -- rien a mesurer" % key}

    bcp = ROOT / "logs" / "runners" / ("p433r4r3r1-bc-%s.json" % uuid.uuid4().hex[:8])
    graft = write_grafted_bc(bcp, ability_name)

    rid, err = _build_seedbc(seed, board, p_units, a_units, bcp)
    if rid is None:
        return {"error": "build KO : %s" % err}
    try:
        dv0 = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        ids = {u.get("visualId"): u.get("id") for u in (dv0.get("units") or []) if u.get("ctrl")}
        carrier = ids.get(CARRIER)
        if carrier is None:
            return {"error": "greffon %s absent de la bataille" % CARRIER}
        mov0 = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        mov_by_unit = {u.get("unitId"): u for u in (mov0.get("units") or [])}
        ctx_c, _, _ = _ctx_for(sid, rid, carrier, wt)
        # `nb` = voisinage NATIF (boardGraph), pas hexgeo : c'est ce que le natif appelle adjacent.
        nb = {p: set(tuple(q) for q in (v or [])) for p, v in (ctx_c.neigh_by_pos or {}).items()}
        occupied = {tuple(p) for p in (list(ctx_c.epos or ()) + list(ctx_c.fpos or ()))}
        occupied.add(tuple(ctx_c.origin))
        carrier_tiles = [(t["col"], t["row"])
                         for t in ((mov_by_unit.get(carrier) or {}).get("tiles") or [])]

        pick = None
        for mover_vis, mover in sorted(ids.items()):
            if mover == carrier:
                continue
            if mover_faction is not None and faction_value(mover_vis) != mover_faction:
                continue
            ctx_m, _, _ = _ctx_for(sid, rid, mover, wt)
            base = _score_map(ctx_m, wt, with_term=False, ability=ability)
            if len(base) < 2:
                continue
            order = sorted(base.items(), key=lambda kv: -kv[1])
            t1 = order[0][0]
            for t2, s2 in order[1:]:
                if base[t1] - s2 >= w:          # le terme ne pourrait pas renverser
                    break
                for slot in carrier_tiles:
                    if slot in occupied or slot in (t1, t2):
                        continue
                    if slot in nb.get(t2, ()) and slot not in nb.get(t1, ()):
                        pick = (mover_vis, mover, t1, t2, slot)
                        break
                if pick:
                    break
            if pick:
                break
        if pick is None:
            return {"error": "aucun couple discriminant sur %s/%s (ability %d) -- montage a "
                             "re-etalonner" % (board, seed, ability)}
        mover_vis, mover, t1, t2, slot = pick
        if verbose:
            print("[flip] ability=%d mover=%s(u%s) T1=%s T2=%s greffon u%s -> %s"
                  % (ability, mover_vis, mover, t1, t2, carrier, slot))
    finally:
        _dispose(sid, rid)

    # Runner NEUF : on ne mute jamais celui qui a servi a CHERCHER le montage.
    rid2, err = _build_seedbc(seed, board, p_units, a_units, bcp)
    if rid2 is None:
        return {"error": "build KO (2e) : %s" % err}
    try:
        res = _r(sid, "applyAction", {"runnerId": rid2, "action": {
            "kind": "move", "unitId": carrier, "to": {"col": slot[0], "row": slot[1]}}}, 90)
        if not (res.get("actions") or [{}])[0].get("ok"):
            return {"error": "applyAction move du greffon KO : %r" % res}
        ctx2, _dv2, _ = _ctx_for(sid, rid2, mover, wt)
        off = _score_map(ctx2, wt, with_term=False, ability=ability)
        on = _score_map(ctx2, wt, with_term=True, ability=ability)
        if not on:
            return {"error": "le mover n'a plus de tuile candidate apres le deplacement du greffon"}
        p_off = max(off, key=lambda k: off[k])
        p_on = max(on, key=lambda k: on[k])

        allu = _r(sid, "aiDryRunAllUnits", {"runnerId": rid2}, 240)
        row = next((u for u in (allu.get("units") or []) if u.get("unitId") == mover), None)
        if row is None:
            return {"error": "mover absent de aiDryRunAllUnits"}
        msgs = row.get("proposed") or []
        mv = next((m for m in msgs if m.get("cls") == "MoveUnitMessage"), None)
        if mv is None or any(m.get("cls") == "ActiveAbilityMessage" for m in msgs):
            return {"error": "la proposition native du mover n'est pas un MOVE PUR (%r) -- la tuile "
                             "viendrait du sweep d'ATTAQUE, hors du modele UnitMovement(6)"
                             % [m.get("cls") for m in msgs]}
        native = (mv["to"]["col"], mv["to"]["row"])

        # Kit du greffon sur les DEUX substrats : le port lit le `triggered` du voisin, le natif
        # l'`AbilitiesComponent`. La greffe doit apparaitre dans les DEUX, sinon le bras « AVEC
        # terme » ne mesure que le port.
        leaf = tile_leaf_ctx(ctx2)
        kit_port = []
        for u in ((leaf.get("friend_units") or []) + (leaf.get("enemy_units") or [])):
            if u.get("id") == carrier:
                kit_port = list(u.get("triggered") or ())
        states = _r(sid, "unitAbilityStates", {"runnerId": rid2}, 180)
        srow = next((u for u in (states.get("units") or []) if u.get("entityId") == carrier), None)
        kit_live = [t.get("raw", [None])[0] for t in ((srow or {}).get("triggered") or [])]

        # Balayage du GATE, meme position du greffon : le terme sur CHAQUE tuile candidate, pour
        # le mover retenu ET pour un mover d'une AUTRE faction. C'est la face `GetAdjacencyUtility`.
        gate = {}
        if mover_faction is not None:
            for ovis, ouid in sorted(ids.items()):
                if ouid in (carrier, mover):
                    continue
                if faction_value(ovis) == mover_faction:
                    continue
                ctx_o, _, _ = _ctx_for(sid, rid2, ouid, wt)
                o_off = _score_map(ctx_o, wt, with_term=False, ability=ability)
                o_on = _score_map(ctx_o, wt, with_term=True, ability=ability)
                gate = {"vis": ovis, "faction": faction_value(ovis), "tiles": len(o_on),
                        "max_delta": max([abs(o_on[k] - o_off.get(k, 0.0)) for k in o_on] or [0.0])}
                break

        out = {"ability": ability, "mover": mover, "mover_vis": mover_vis,
               "mover_faction": faction_value(mover_vis), "carrier": carrier, "slot": slot,
               "t1": t1, "t2": t2, "p_on": p_on, "p_off": p_off, "native": native,
               "weight": w, "kit_port": kit_port, "kit_live": kit_live, "graft": graft,
               "gate": gate, "board": board, "seed": seed}
        if verbose:
            print("[flip] argmax port SANS terme=%s  AVEC terme=%s  NATIF=%s"
                  % (p_off, p_on, native))
            print("[flip] kit greffon -- port=%r live=%r" % (kit_port, kit_live))
            if gate:
                print("[gate] mover hors gate %s (faction %s) : %d tuiles, delta max=%s"
                      % (gate["vis"], gate["faction"], gate["tiles"], gate["max_delta"]))
        return out
    finally:
        _dispose(sid, rid2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--seed", default=DEFAULT_SEED)
    ap.add_argument("--board", default=DEFAULT_BOARD)
    ap.add_argument("--only", choices=("A", "B"), help="ne jouer qu'une etape")
    args = ap.parse_args()

    rc = step0_weights()
    if args.offline_only:
        return rc

    plans = []
    if args.only in (None, "A"):
        plans.append(("A WatchedOver (sans gate)", WATCHED_OVER, "WatchedOver", KEY_WO, None))
    if args.only in (None, "B"):
        plans.append(("B PrimarchOfTheFirstLegion (gate DarkAngels + cle de registre 1511)",
                      PRIMARCH, "PrimarchOfTheFirstLegion", KEY_PR, DARK_ANGELS))

    for label, aid, aname, key, fac in plans:
        print("")
        print("=== ETAPE %s ===" % label)
        res = run_tile_flip(aid, aname, key, seed=args.seed, board=args.board,
                            mover_faction=fac, verbose=True)
        if res.get("error"):
            print("  MONTAGE KO : %s" % res["error"])
            rc = 1
            continue
        ok_flip = res["p_on"] != res["p_off"] and res["native"] == res["p_on"]
        print("  %-14s %s" % ("verdict", "OK -- le natif SUIT le terme (changement de tuile)"
                              if ok_flip else "ECART"))
        if not ok_flip:
            rc = 1
        if fac is not None and res.get("gate"):
            g = res["gate"]
            if g["max_delta"] != 0.0:
                print("  GATE KO : le terme mord sur un mover faction %s (delta max=%s)"
                      % (g["faction"], g["max_delta"]))
                rc = 1
            else:
                print("  gate OK : terme EXACTEMENT 0 sur les %d tuiles d'un mover faction %s"
                      % (g["tiles"], g["faction"]))
    return rc


if __name__ == "__main__":
    sys.exit(main())
