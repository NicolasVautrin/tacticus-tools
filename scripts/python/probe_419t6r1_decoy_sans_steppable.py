"""#419-t6-r1 -- le gate de `CosmicHorror` est `HasTrait(Decoy)` SEUL, et on le MONTRE.

## Le residu, et pourquoi il annoncait `BLOCAGE: porteur`

`IdunBattle.AI.Playbook.Loki.CosmicHorrorPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
teste l'occupant de la tuile d'attaque par `UnitExtensions.HasTrait(u, 0x41d)` -- `UnitTrait.Decoy`
SEUL. Le montage de #419-t6 ne pouvait pas le distinguer d'un gate `Decoy && Steppable` : les DEUX
seules unites du catalogue qui portent `Decoy` (`genesDecoy` npc, `genesSmnDecoy` summon) portent
AUSSI `Steppable` -- re-mesure du 2026-08-15 sur `t6dpr4k06g`, la premisse tient. Un port qui
AJOUTERAIT `Steppable` passait donc toutes les mesures de la tranche.

## Le debloqueur -- ACCORDER le trait, et au CASTER

`catalog_inject.add_unit_trait(bc, 'genesPatriarch', 'Decoy')` ecrit `BC.Units[].Traits`, que
`buildNormalizedBC` LIT sans jamais l'ECRIRE : l'injection survit a la normalisation. Le Patermine
ne porte NI `Decoy` NI `Steppable` (kit mesure : `Hero, Infiltrate, Synapse, Terrifying,
Unstoppable`), donc l'accorder fabrique exactement le porteur qui manquait -- `Decoy` SANS
`Steppable`.

⚠ POURQUOI LE CASTER, ET PAS UN VOISIN. Le terme lit l'occupant de la TUILE D'ATTAQUE, et une
tuile n'entre dans les tuiles d'action que si elle est vide ou si son occupant est `Steppable`
(`IdunBattle.Entities.TileExtensions$$IsEmptyOrSteppable`). Un leurre NON `Steppable` pose sur une
tuile voisine serait donc structurellement hors du movable set, et `pairUtility` refuserait la
tuile : le regime serait INATTEIGNABLE par cette voie. La tuile COURANTE du caster, elle, est
toujours acceptee -- c'est deja la tuile `C` du montage #419-t6, celle qui y rend 0 parce que son
occupant (le caster) est ami mais PAS leurre. Lui accorder `Decoy` la fait passer a 10 : le
discriminant est exactement la tuile temoin de la tranche precedente, retournee.

⚠ `IsFriend(u, case.Caster, state)` avec `u == caster` : LU au decompile
(`IdunBattle.Entities.UnitExtensions$$IsFriend`), c'est la comparaison de
`GetCurrentPlayer(x).<+0x20>.<+0x24>` des deux cotes -- aucune exclusion de l'identite. Le gate
passe donc trivialement quand l'occupant EST le caster.

## Ce que le montage mesure

Deux bras (deux runners), deux tuiles chacun :

| bras | `C` = tuile COURANTE du caster | `F` = tuile LIBRE voisine de la cible |
|---|---|---|
| SANS le trait | 0 | 0 |
| AVEC le trait | **+ le poids** | 0 |

`F` est le contre-bras INTERNE au bras AVEC : sans lui, un port qui rendrait le poids PARTOUT
passerait. Le bras SANS est le contre-bras EXTERNE : il etablit que l'ecart vient du TRAIT et non
de la geometrie.

Et la contre-epreuve qui FERME le residu : le mutant `steppable_too` ajoute `Steppable` au gate --
exactement le port que #419-t6 ne pouvait pas ecarter. Il doit rendre 0 sur `C` dans le bras AVEC,
donc DIVERGER du natif.

Usage :
    python scripts/python/probe_419t6r1_decoy_sans_steppable.py --state-file <chemin ABSOLU>
        [--bras avec|sans] [--mutants]

ASCII only. Garde jumelle :
`scripts/python/tests/engine/test_419t6r1_decoy_sans_steppable_live.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import catalog_inject as CI                                      # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait          # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402

BOARD = "MC1_67"
SEED = "51278"
CASTER = "genesPatriarch"       # HERO au pool, `CosmicHorror` est son SEUL triggered
TARGET = "astraBullgryn"        # cible de mesure -- aucune ability de summon/spawn (cf. #419-t6)
TRAIT = UnitTrait.Decoy.name    # le trait ACCORDE : `Decoy`, SANS `Steppable`

ABILITY = int(TriggeredAbilityType.CosmicHorror)             # 1277
DECOY_TRAIT_ID = int(UnitTrait.Decoy)                        # 1053 = 0x41d
STEPPABLE_TRAIT_ID = int(UnitTrait.Steppable)                # le trait qu'on veut voir ABSENT
WEIGHT_KEY = "COSMICHORROR_StepOnDecoyToAttack"
EPS = 1e-4
HP_BIG = 400000                 # personne ne meurt : la mesure porte sur une paire, pas un kill

_STATS = (f"{CASTER}:Health={HP_BIG},RemainingHealth={HP_BIG};"
          f"{TARGET}:Health={HP_BIG},RemainingHealth={HP_BIG}")


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- seed BC des bras

def seed_bc_for(bras: str, out_path: str) -> str:
    """Ecrit le seed BC du bras. `avec` accorde `Decoy` au caster ; `sans` le laisse intact.

    On passe par `write_trait_seed_bc` plutot que par un patch a la main : c'est la primitive qui
    valide le nom contre l'enum `UnitTrait` du build COURANT (un nom hors enum ferait lever
    `initAndStart` au deserialize, pas ici) et qui injecte le porteur au catalogue s'il manque.
    """
    if bras not in ("avec", "sans"):
        raise ValueError(f"bras inconnu {bras!r}")
    if bras == "sans":
        return ""                                    # seed BC partage, aucun patch
    p, reports = CI.write_trait_seed_bc(out_path, [f"{CASTER}:{TRAIT}"])
    rep = reports[0]
    if TRAIT not in rep["traitsAfter"]:
        raise MontageError(f"le trait {TRAIT} n'a pas ete pose : {rep}")
    if rep["alreadyPresent"]:
        raise MontageError(
            f"{CASTER} portait DEJA {TRAIT} au seed BC -- le bras `avec` ne mesure plus rien, "
            f"et le bras `sans` non plus. Re-lire le catalogue avant de conclure.")
    return str(p)


def build_args(bras: str, seed_bc: str) -> list[str]:
    out = ["--board", BOARD, "--p-units", CASTER, "--a-units", TARGET, "--unit-stat", _STATS]
    if seed_bc:
        out += ["--seed-bc", seed_bc]
    return out


# --------------------------------------------------------------------------- oracles

def pair_native(rpc, rid, cid, tgt, ab, tile) -> float:
    r = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                            "abilityType": ab, "col": tile[0], "row": tile[1]}, 90)
    v = (r or {}).get("utility")
    if not isinstance(v, (int, float)):
        raise MontageError(f"pairUtility natif indisponible pour {tile} / cible {tgt}: {r}")
    return float(v)


def pair_port(ctx, ab, tgt, tile) -> float:
    cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
    if cand is None:
        raise MontageError(f"le port ne produit AUCUNE action depuis {tile} sur {tgt}")
    return float(cand["u"])


def _fresh_ctx(rpc, rid, cid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return dv, _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))


def _normal_ability(rpc, rid, uid):
    r = rpc("abilityTargets", {"runnerId": rid, "unitId": uid}, 60) or {}
    for u in (r.get("units") or ()):
        if u.get("unitId") != uid:
            continue
        for a in (u.get("abilities") or ()):
            if a.get("kind") == "normal":
                return a.get("abilityId")
    return None


def _attest_traits(rpc, rid, eid, bras: str) -> dict:
    """Le trait EFFECTIF de l'entite, lu au canal `combatSnapshot.units[].traits` (#233/#267) --
    l'invocation native de `HasTrait` par valeur d'enum, donc l'ensemble que le natif teste.

    ⚠ Surtout PAS `decisionView.units[].traits` : il vaut `null` sur ce runner (mesure #419-t6),
    et une attestation batie dessus rendrait FAUX sur un montage correct. C'est aussi une source
    INDEPENDANTE du substrat que consomme le port, donc un port aveugle aux traits ne peut pas se
    faire valider par sa propre cecite.
    """
    cs = rpc("combatSnapshot", {"runnerId": rid}, 90) or {}
    for u in (cs.get("units") or ()):
        if u.get("entityId") != eid:
            continue
        ids = set(u.get("traits") or ())
        got = {"entityId": eid, "trait_ids": sorted(ids),
               "decoy": DECOY_TRAIT_ID in ids, "steppable": STEPPABLE_TRAIT_ID in ids}
        want_decoy = bras == "avec"
        if got["decoy"] != want_decoy:
            raise MontageError(
                f"montage NON INSTALLE : bras `{bras}` attend Decoy={want_decoy} sur le caster, "
                f"canal combatSnapshot rend {got}")
        # LE POINT DU RESIDU : le porteur fabrique doit etre `Decoy` SANS `Steppable`. S'il portait
        # les deux, le montage retomberait exactement dans le regime que #419-t6 ne separait pas.
        if got["steppable"]:
            raise MontageError(
                f"montage NON INSTALLE : le caster porte AUSSI `Steppable` -- le montage ne "
                f"distingue plus `Decoy` de `Decoy && Steppable` : {got}")
        return got
    raise MontageError(f"montage NON INSTALLE : entite {eid} absente de combatSnapshot")


# --------------------------------------------------------------------------- montage

def build_case(sid, rpc, rid: int, bras: str) -> dict:
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mine = [u for u in units if u.get("ctrl")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    myplayer = mine[0].get("owner")
    cid = next((u["id"] for u in mine if u.get("visualId") == CASTER), None)
    if cid is None:
        raise MontageError(f"montage NON INSTALLE : {CASTER} absent de mon roster")
    tgt_id = next((u["id"] for u in units
                   if u.get("owner") != myplayer and u.get("visualId") == TARGET), None)
    if tgt_id is None:
        raise MontageError(f"montage NON INSTALLE : {TARGET} absent du roster adverse")

    # (a) CABLAGE : le passif doit etre dans l'AbilitiesComponent, sinon le dispatcher ne l'itere
    #     pas et un terme nul se lirait comme « le gate coupe » (moitie CABLAGE du patron #419).
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live_ids = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
    if ABILITY not in live_ids:
        raise MontageError(
            f"montage NON INSTALLE : {ABILITY} n'est PAS dans l'AbilitiesComponent de {CASTER} "
            f"-- triggered live lus = {sorted(set(live_ids))}")

    # (b) le TRAIT accorde -- atteste sur le canal ECS, et le refus porte les DEUX sens.
    traits = _attest_traits(rpc, rid, cid, bras)

    # (c) la GEOMETRIE : caster et cible ADJACENTS au sens NATIF. On DEPLACE, on ne subit pas le
    #     spawn -- et on choisit le couple de tuiles dans le graphe de mouvement reel.
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    lay = None
    for ck in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        nb = [q for q in bq_neighbours(ck, cells, elev)]
        for tt in nb:
            libres = [q for q in bq_neighbours(tt, cells, elev) if q not in (ck, tt)]
            if len(libres) >= 1:
                lay = {"Ck": ck, "Tt": tt}
                break
        if lay:
            break
    if lay is None:
        raise MontageError("montage NON INSTALLE : aucun couple (caster, cible) adjacent avec une "
                           "tuile libre voisine sur ce board")
    if not P124._drive_to(sid, rid, walk, elev, {cid: lay["Ck"], tgt_id: lay["Tt"]}):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {lay}, obtenu "
                           f"caster={pos.get(cid)} cible={pos.get(tgt_id)}")
    P124._give_turn_back(sid, rid, myplayer)

    _dv2, pos = P124._positions(sid, rid)
    dv, ctx = _fresh_ctx(rpc, rid, cid)
    p_c, p_t = pos.get(cid), pos.get(tgt_id)
    if not bq.is_adjacent(p_c, p_t, elev):
        raise MontageError(f"montage NON INSTALLE : caster {p_c} et cible {p_t} ne sont pas "
                           f"adjacents au sens NATIF (porte d'elevation comprise)")
    act = [t for t in (ctx.action_tiles or []) if t and t[0] is not None]
    if p_c not in act:
        raise MontageError(f"montage NON INSTALLE : la tuile COURANTE du caster {p_c} n'est pas "
                           f"dans les tuiles d'action ({sorted(act)}) -- rien a mesurer")
    busy = set(pos.values())
    f_tile = next((t for t in act if t not in busy and bq.is_adjacent(t, p_t, elev)), None)
    if f_tile is None:
        raise MontageError(f"montage NON INSTALLE : aucune tuile TEMOIN libre, voisine NATIVE de "
                           f"la cible {p_t} et dans les tuiles d'action {sorted(act)}")
    return {"rid": rid, "cid": cid, "tgt": tgt_id, "bras": bras, "ctx": ctx, "dv": dv,
            "traits": traits, "C": p_c, "F": f_tile, "elev": elev, "walk": walk}


def bq_neighbours(t, cells, elev) -> list:
    """Voisins NATIFS (ring-1 hex + porte `|delta elev| < 2`, cf.
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`)."""
    import hexgeo
    cs = set(cells)
    return [q for q in hexgeo.neighbors(t[0], t[1]) if q in cs and bq.is_adjacent(t, q, elev)]


def _tiles(case: dict) -> tuple:
    return (("C", case["C"]), ("F", case["F"]))


def measure(rpc, case: dict) -> list[dict]:
    """Une ligne par tuile : natif, port, et `expected` pose EN DUR depuis le decompile -- le poids
    BC si et seulement si l'occupant de la tuile porte `Decoy` et est ami du caster."""
    import engine.playbook.psyker as PSY
    weight = float(case["ctx"].wt.triggered(WEIGHT_KEY))
    if weight <= 0:
        raise MontageError(f"montage NON INSTALLE : le poids {WEIGHT_KEY} vaut {weight} dans le BC "
                           f"servi -- le terme serait nul et la mesure ne trancherait rien")
    ab = _normal_ability(rpc, case["rid"], case["cid"])
    if ab is None:
        raise MontageError("montage NON INSTALLE : le caster n'a pas d'attaque normale")
    out = []
    for key, tile in _tiles(case):
        expected = weight if (key == "C" and case["bras"] == "avec") else 0.0
        nat = pair_native(rpc, case["rid"], case["cid"], case["tgt"], ab, tile)
        port = pair_port(case["ctx"], ab, case["tgt"], tile)
        saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
        if saved is None:
            raise MontageError(f"le playbook {ABILITY} n'est PAS au registre -- rien a muter")
        try:
            muted = pair_port(case["ctx"], ab, case["tgt"], tile)
        finally:
            PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
        out.append({"tile_key": key, "tile": tile, "weight": weight, "expected": expected,
                    "native": nat, "port": port, "port_muted": muted, "ability": ab,
                    "bras": case["bras"]})
    return out


# --------------------------------------------------------------------------- contre-epreuves

def measure_mutant(rpc, case: dict, mutant: str) -> list[dict]:
    """Re-mesure le port avec le playbook 1277 REMPLACE.

      `steppable_too` -- LE MUTANT DU RESIDU : le gate devient `Decoy && Steppable`, c'est-a-dire
                         exactement le port que #419-t6 ne pouvait pas ecarter. Sur le bras `avec`
                         il doit rendre 0 sur `C` la ou le natif rend le poids.
      `no_trait`      -- gate `HasTrait` retire : `C` prend le poids meme dans le bras `sans`.

    ⚠ Le critere est le DEPLACEMENT par rapport au port NON MUTE (jamais l'ecart au natif : la
    paire porte un residu constant hors-perimetre)."""
    import engine.playbook.psyker as PSY
    from engine.playbook import cosmic_horror as CH
    from engine.playbook.prediction._shared import _entity_traits

    class _Mut(CH.CosmicHorrorPlaybook):
        def calculate_attack_utility_in_steps(self, ctx, attacker_uid, ability_id, case_tgt_id,
                                              attack_tile, prediction=None):
            sc = getattr(ctx, "scene", None)
            if sc is None or attack_tile is None:
                return 0.0
            occ = CH.tile_occupant(sc, attack_tile)
            if occ is None:
                return 0.0
            tr = _entity_traits(sc, occ)
            if mutant != "no_trait" and UnitTrait.Decoy.name not in tr:
                return 0.0
            if mutant == "steppable_too" and UnitTrait.Steppable.name not in tr:
                return 0.0
            if sc.team(occ) != sc.team(attacker_uid):
                return 0.0
            return float(ctx.wt.triggered(WEIGHT_KEY))

    ab = _normal_ability(rpc, case["rid"], case["cid"])
    ref = {k: pair_port(case["ctx"], ab, case["tgt"], t) for k, t in _tiles(case)}
    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY]
    PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = _Mut()
    try:
        return [{"mutant": mutant, "tile_key": k, "tile": t, "bras": case["bras"],
                 "port": pair_port(case["ctx"], ab, case["tgt"], t), "port_ref": ref[k]}
                for k, t in _tiles(case)]
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved


# --------------------------------------------------------------------------- CLI

def _build(state_file: str, extra: list[str]) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file (le probe construit SON runner dessus)")
    ap.add_argument("--bras", choices=("avec", "sans"), default="avec",
                    help="`avec` accorde Decoy au caster (defaut), `sans` est le contre-bras")
    ap.add_argument("--mutants", action="store_true",
                    help="joue aussi les contre-epreuves (elles doivent MORDRE)")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    bc = seed_bc_for(args.bras, os.path.join(
        os.path.dirname(os.path.dirname(_HERE)), "logs", "419t6r1-seed-bc.json"))
    rid = _build(args.state_file, build_args(args.bras, bc))
    print(f"[419t6r1] runner {rid} bras={args.bras} seed-bc={bc or '(partage)'}")
    case = build_case(sid, rpc, rid, args.bras)
    print(f"[419t6r1] traits ECS du caster : {case['traits']}")
    rows = measure(rpc, case)
    rc = 0
    for r in rows:
        ok = abs((r["port"] - r["port_muted"]) - r["expected"]) <= EPS
        rc |= 0 if ok else 1
        print("  %s %-8s natif=%.6f port=%.6f port_sans_1277=%.6f terme_port=%+.6f "
              "attendu=%+.6f %s"
              % (r["bras"], "%s%s" % (r["tile_key"], r["tile"]), r["native"], r["port"],
                 r["port_muted"], r["port"] - r["port_muted"], r["expected"],
                 "OK" if ok else "DIVERGE"))
        if abs(r["native"] - r["port"]) > EPS:
            print("     ECART natif<->port : %+.6f" % (r["native"] - r["port"]))
    if args.mutants:
        for m in ("steppable_too", "no_trait"):
            rows_m = measure_mutant(rpc, case, m)
            bouge = [x for x in rows_m if abs(x["port"] - x["port_ref"]) > EPS]
            print("  mutant %-14s mord sur %s" % (m, [x["tile_key"] for x in bouge] or "RIEN"))
            for x in rows_m:
                print("     %-8s port_mute=%.6f port_ref=%.6f"
                      % ("%s%s" % (x["tile_key"], x["tile"]), x["port"], x["port_ref"]))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
