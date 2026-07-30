"""Probe case-224 item 4 -- le predicat d'AURA `IsInContagionsOfNurgleRange`.

Ce que le probe MESURE, etage par etage (jamais un scalaire fitte) :

  etape 0  OFFLINE  garde de substrat : la table `GetRangeOnOwnerTurn` (1/2/3), son identite avec
                    `ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange(unit)` deja porte, et
                    l'IDENTITE des deux rayons effectifs (les deux comparateurs sont INCLUSIFS).
  etape A  LIVE     l'etage DISTANCE + TRAIT, mesure par `abilityTargets` sur `EntropyCannons`
                    (1168, MoW `deathCrawler`) : son `GetDynamicInvalidTargetReason` rend 0 SSI
                    `IsInTeamContagionsOfNurgleAura(target, caster)` OU `HasNegativeModifier(target,
                    FixedArmor)`. Sur un runner FRAIS la 2e branche est muette (aucun modificateur
                    negatif d'armure) -> la legalite de la cible EST le predicat d'aura natif.
  etape B  LIVE     l'etage TOURS : on fait avancer `TurnsStarted(porteur)` et on re-mesure le
                    SEUIL de distance. 0-2 -> 1 ; 3-4 -> 2 ; 5+ -> 3.

Les deux versions du predicat partagent EXACTEMENT l'etage de portee (`entities/effects/aura.py` :
`GetTrait` + `GetCurrentRange`) ET le meme comparateur INCLUSIF -- la version UNITE instancie un
`AmountIsEqualOrGreaterAbilityTrigger`, ce que le nom DEDUPLIQUE de son `.ctor` masquait (#293, cf.
`entities/triggers.py::IsInUnitAura` et `probe_293_aura_predicate_comparator.py`). Confronter la
version EQUIPE live valide donc l'etage commun ; le comparateur, lui, se lit au decompile -- sur le
POINTEUR DE CLASSE, jamais sur le nom du ctor.

Usage (depuis scripts/python) :
    python probe_224_contagions_aura_range.py --offline-only
    python probe_224_contagions_aura_range.py --board C1_02 --seed 4242
    python probe_224_contagions_aura_range.py --board C1_02 --advance 6   # etape B (paliers)

ASCII only (cp1252). Discipline runner : state-file ABSOLU unique sous logs/, dispose en fin de passe.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
HOST = "http://127.0.0.1:8765"
STATE = ROOT / "logs" / "probe_224_aura.json"

AURA = 1071                 # EffectType.ContagionsOfNurgle_ArmorReduction1 (PAS TriggeredAbilityType)
ENTROPY_CANNONS = 1168


# --------------------------------------------------------------------------- plomberie RPC

def _sid() -> int:
    with urllib.request.urlopen(f"{HOST}/api/admin/status", timeout=20) as r:
        return json.loads(r.read())["session"]["id"]


def rpc(method: str, arg=None, timeout: int = 90):
    body = json.dumps({"method": method, "args": [arg] if arg is not None else [],
                       "timeout": timeout * 1000}).encode()
    req = urllib.request.Request(f"{HOST}/api/scripts/{_sid()}/rpc", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 30) as r:
        out = json.loads(r.read())
    return out.get("result", out)


def build(p_units: str, a_units: str, board: str, seed: str, p_mow: str, advance: int = 0) -> int:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        STATE.unlink()
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
           "--p-units", p_units, "--a-units", a_units, "--p-mow", p_mow,
           "--state-file", str(STATE)]
    if advance:
        # `--advance N` = N tours joues par l'IA des deux camps -> c'est le SEUL levier qui fait
        # monter `TurnsStarted` du porteur, donc le seul qui exerce les paliers 2 et 3 de
        # `GetRangeOnOwnerTurn`. Sans lui, la table n'est confrontee qu'en son premier point.
        cmd += ["--advance", str(int(advance)), "--maxpump", "400"]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not STATE.exists():
        raise SystemExit("build KO: " + (proc.stderr or proc.stdout)[-800:])
    return json.loads(STATE.read_text())["runnerId"]


def dispose(rid: int):
    try:
        rpc("disposeRunner", {"runnerId": rid}, 30)
    except Exception as exc:                                     # noqa: BLE001
        print("dispose KO:", exc)


def targets_of(rid, caster, ability):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ability}) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    if row is None:
        return []
    for a in (row.get("abilities") or []):
        if a.get("abilityType") in (ability, None):
            return a.get("targets") or []
    return []


def move(rid, uid, col, row):
    r = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": col, "row": row}}})
    return (r.get("actions") or [{}])[0].get("error")


# --------------------------------------------------------------------------- etape 0 (offline)

def offline_guard() -> int:
    from engine.entities.effects.aura import (aura_trait, aura_max_range, aura_current_range,
                                              aura_next_turn_range, aura_range_on_owner_turn,
                                              is_aura_effect)
    from engine.entities.traits.unit_trait import UnitTrait
    bad = 0
    # (a) `$$GetTrait` = 0x7eb, `$$GetMaxRange` = Direct(3), cast IAuraEffect refuse le reste.
    if aura_trait(AURA) != int(UnitTrait.ContagionsOfNurgle):
        print("KO trait", aura_trait(AURA)); bad += 1
    if aura_max_range(AURA) != 3:
        print("KO maxrange", aura_max_range(AURA)); bad += 1
    for other in (1065, 1244, 5, 17):
        if is_aura_effect(other):
            print("KO cast accepte", other); bad += 1
    # (b) la table `GetRangeOnOwnerTurn` == la surcharge compilee `CalculateRange(roundsInGame)`
    #     (`if (2 < n) return (4 < n) + 2 ; return 1`), transcrite ici a l'identique.
    for n in range(0, 12):
        # transcription LITTERALE du corps compile `$$CalculateRange(roundsInGame)` :
        #     if (2 < n) return (4 < n) + 2 ;  return 1
        native = (int(n > 4) + 2) if n > 2 else 1
        if aura_range_on_owner_turn(n) != native:
            print("KO table n=", n, aura_range_on_owner_turn(n), "!=", native); bad += 1
        if aura_current_range(AURA, n) != native:
            print("KO current n=", n); bad += 1
        if aura_next_turn_range(AURA, n) != aura_range_on_owner_turn(n + 1):
            print("KO nextturn n=", n); bad += 1
    # (c) le foyer deja porte (`CalculateRange(unit)`, SpawnPoxwalkers) doit rester value-identique.
    for n in range(0, 12):
        legacy = (3 if n > 4 else 2) if n > 2 else 1
        if aura_range_on_owner_turn(n) != legacy:
            print("KO fork vs deathguard.contagions_of_nurgle_range n=", n); bad += 1
    print("etape 0 table:", [aura_range_on_owner_turn(n) for n in range(0, 8)],
          "(TurnsStarted 0..7)")
    # (d) Les deux comparateurs natifs, cote a cote : ils sont INCLUSIFS TOUS LES DEUX (#293 -- la
    # version UNITE instancie un `AmountIsEqualOrGreaterAbilityTrigger`, malgre le nom DEDUPLIQUE de
    # son `.ctor`). Meme rayon effectif des deux cotes : c'est un INVARIANT, on l'imprime comme tel.
    unite = [aura_range_on_owner_turn(n) for n in range(0, 8)]
    equipe = [aura_range_on_owner_turn(n) for n in range(0, 8)]
    print("etape 0 comparateurs : version UNITE (AmountIsEqualOrGreater) = dist <= range"
          " -> rayon effectif", unite)
    print("                      version EQUIPE (GetInRangeAuraAmount)  = dist <= range"
          " -> rayon effectif", equipe)
    if unite != equipe:
        print("KO : les deux rayons effectifs ont diverge -- cf. #293"); bad += 1
    print("etape 0:", "OK" if bad == 0 else f"{bad} ECARTS")
    return bad


# --------------------------------------------------------------------------- confrontation live

def _load(rid, board_tiles):
    from engine.runner.snapshot import load_state
    from engine.entities.pathfinding.board import Board
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dec, ob, snap, board=Board(board_tiles, adjacency="evenq"))
    return dec, ob, snap, state


def _port_verdicts(state, mow_id, carrier_id, enemy_id):
    """Verdicts du PORT sur la MEME scene : version EQUIPE (le predicat que le natif expose par
    `abilityTargets`) ET version UNITE (le predicat de case-224). Les deux sont INCLUSIFS (#293),
    donc ils doivent s'accorder sur toute scene ou le TRAIT du porteur est le meme."""
    from engine.runner.abilities.behaviours import entities_from_state
    from engine.runner.abilities.deathguard import is_in_contagions_of_nurgle_range
    from engine.entities.triggers import IsInTeamAura
    from engine.entities.selectors import Caster, Target
    team_ctx = entities_from_state(state, caster_id=mow_id, target_id=enemy_id)
    team = IsInTeamAura(Target(), AURA, Caster()).should_trigger(team_ctx)
    unit_ctx = entities_from_state(state, caster_id=carrier_id, target_id=enemy_id,
                                   actor_id=enemy_id)
    unit = is_in_contagions_of_nurgle_range().should_trigger(unit_ctx)
    return bool(team), bool(unit)


def _turns_started(state, uid):
    """`GetStat(unit, 0xc = TurnsStarted)` -- l'ENTREE de `GetCurrentRange`, lue par la MEME voie que
    le port (`StatsComponent.ctx.stats`), pas par un champ devine du snapshot brut."""
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    e = state.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    st = getattr(sc.ctx, "stats", None) if sc is not None else None
    return int(st.get_stat(int(StatType.TURNS_STARTED), 0)) if st is not None else None


def scenario(args) -> int:
    """deathCrawler (MoW joueur, EntropyCannons) + deathTyphus (PORTEUR de ContagionsOfNurgle)
    + necroWarden (allie SANS le trait) vs un ennemi qu'on promene a distances croissantes."""
    # ROSTER CRAFTE pour l'objectif : `deathTyphus` = le PORTEUR du trait ContagionsOfNurgle ;
    # `necroWarden` = un allie SANS le trait (etape C) ; face a lui TROIS ennemis TANKY -- avec un
    # seul ennemi, `--advance` termine la bataille avant la mesure et la MoW quitte `decisionView`
    # (mesure : advance 6 vs `ultraTitus` seul -> plus aucune MoW).
    rid = build("deathTyphus,necroWarden", args.a_units, args.board, args.seed, "deathCrawler",
                advance=args.advance)
    print("runner", rid, "| advance", args.advance)
    bad = 0
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        tiles = bg["tiles"]
        byrc = {(t["col"], t["row"]): t for t in tiles}
        dec, ob, snap, state = _load(rid, tiles)
        mow = next((m for m in (dec.get("mows") or []) if m.get("visualId") == "deathCrawler"), None)
        if mow is None:
            print("KO: pas de MoW deathCrawler dans decisionView"); return 1
        mow_id, mow_team = mow["casterId"], mow["team"]
        carrier = next(u for u in ob["units"] if u["visualId"] == "deathTyphus")
        nocar = next(u for u in ob["units"] if u["visualId"] == "necroWarden")
        enemy = next(u for u in ob["units"] if u["teamId"] != mow_team and not u.get("isDead"))
        print("mow", mow_id, "team", mow_team, "| porteur", carrier["squadId"],
              "| non-porteur", nocar["squadId"], "| ennemi", enemy["squadId"])
        print("TurnsStarted(porteur) =", _turns_started(state, carrier["squadId"]))

        import hexgeo
        # DRIVE POSITIONS : on ECARTE d'abord le non-porteur (il ne doit jamais etre le voisin qui
        # decide), puis on promene le PORTEUR a distance 1, 2, 3, 4 de l'ennemi -- c'est la geometrie
        # qui est l'entree du predicat, on ne la subit pas.
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        ek = (enemy["col"], enemy["row"])
        far = [t for t in tiles if t.get("walkable", True)
               and (t["col"], t["row"]) not in occ
               and hexgeo.distance((t["col"], t["row"]), ek) >= 6]
        if far:
            err = move(rid, nocar["squadId"], far[0]["col"], far[0]["row"])
            print("ecarte non-porteur ->", (far[0]["col"], far[0]["row"]), err or "")

        rows = []
        for want in (1, 2, 3, 4):
            _d, ob, snap, state = _load(rid, tiles)
            cur = next(u for u in ob["units"] if u["squadId"] == carrier["squadId"])
            occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
            occ.discard((cur["col"], cur["row"]))
            cand = [t for t in tiles if t.get("walkable", True)
                    and (t["col"], t["row"]) not in occ
                    and hexgeo.distance((t["col"], t["row"]), ek) == want]
            if not cand:
                print(f"d={want}: aucune tuile libre a cette distance -- saute")
                continue
            err = move(rid, carrier["squadId"], cand[0]["col"], cand[0]["row"])
            _d, ob, snap, state = _load(rid, tiles)
            cur = next(u for u in ob["units"] if u["squadId"] == carrier["squadId"])
            got = hexgeo.distance((cur["col"], cur["row"]), ek)
            if got != want:
                print(f"d={want}: deplacement refuse ({err}), distance reelle {got}")
            tg = targets_of(rid, mow_id, ENTROPY_CANNONS)
            native = any(t.get("targetId") == enemy["squadId"] for t in tg)
            team, unit = _port_verdicts(state, mow_id, carrier["squadId"], enemy["squadId"])
            ts = _turns_started(state, carrier["squadId"])
            rows.append((got, ts, native, team, unit))
            flag = "OK " if native == team else "KO "
            if native != team:
                bad += 1
            # Les deux predicats etant INCLUSIFS (#293) et ce montage n'ayant qu'UN porteur d'aura,
            # `unit` doit EGALER `team` : un ecart signale une divergence d'etage, pas un choix de
            # comparateur. On l'affiche explicitement plutot que de le laisser passer.
            print(f"{flag}d={got} TurnsStarted={ts} | natif(equipe)={native} port(equipe)={team}"
                  f" | port(UNITE,inclusif)={unit}"
                  + ("" if unit == team else "  <-- UNITE != EQUIPE (inattendu, cf. #293)"))
        print("etape A:", "OK" if bad == 0 else f"{bad} DESACCORDS", "| lignes", len(rows))
        # etape C -- le gate TRAIT : le porteur loin, on ramene le NON-porteur au contact.
        _d, ob, snap, state = _load(rid, tiles)
        cur = next(u for u in ob["units"] if u["squadId"] == carrier["squadId"])
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        occ.discard((cur["col"], cur["row"]))
        away = [t for t in tiles if t.get("walkable", True)
                and (t["col"], t["row"]) not in occ
                and hexgeo.distance((t["col"], t["row"]), ek) >= 6]
        if away:
            move(rid, carrier["squadId"], away[0]["col"], away[0]["row"])
        _d, ob, snap, state = _load(rid, tiles)
        occ = {(u["col"], u["row"]) for u in ob["units"] if not u.get("isDead")}
        n2 = next(u for u in ob["units"] if u["squadId"] == nocar["squadId"])
        occ.discard((n2["col"], n2["row"]))
        adj = [t for t in tiles if t.get("walkable", True)
               and (t["col"], t["row"]) not in occ
               and hexgeo.distance((t["col"], t["row"]), ek) == 1]
        if adj:
            move(rid, nocar["squadId"], adj[0]["col"], adj[0]["row"])
            _d, ob, snap, state = _load(rid, tiles)
            tg = targets_of(rid, mow_id, ENTROPY_CANNONS)
            native = any(t.get("targetId") == enemy["squadId"] for t in tg)
            team, unit = _port_verdicts(state, mow_id, nocar["squadId"], enemy["squadId"])
            ok = (native == team)
            if not ok:
                bad += 1
            print(f"{'OK ' if ok else 'KO '}etape C (gate TRAIT) : voisin ADJACENT sans le trait"
                  f" -> natif={native} port={team} (attendu False des deux cotes)")
        else:
            print("etape C: aucune tuile adjacente libre -- non exercee")
        print("VERDICT:", "OK" if bad == 0 else f"{bad} DESACCORDS")
    finally:
        if not args.keep:
            dispose(rid)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--board", default="C1_02")
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--a-units", default="custoKyrus,astraBullgryn,ultraTitus")
    ap.add_argument("--advance", type=int, default=0,
                    help="tours d'IA joues AVANT la mesure -- fait monter TurnsStarted(porteur), "
                         "seul levier qui exerce les paliers 2 et 3 de GetRangeOnOwnerTurn")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    bad = offline_guard()
    if not args.offline_only:
        bad += scenario(args)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
