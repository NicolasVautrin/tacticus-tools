"""probe #287-r14 (volet LIVE) -- LE NATIF RESOUT LUI-MEME : cast de `1018 ValkyrieStrike` avec
`targetId` = un id d'**UNITE**, et l'effet `1022` doit atterrir sur la **TUILE**.

LA QUESTION BINAIRE
-------------------
`#287-r12` a mesure le regime T (cast sur l'entite-TUILE) : le natif inscrit `1022` dans
`tileMeta.tiles[].effects`, `decisionView.units[].effects` restant INCHANGE. Restait ouvert le
regime que TOUS les tests live du port empruntent -- `targetId` = l'**UNITE** (`_ringed_cast.
cast_and_confront`). Le port y posait l'effet sur l'UNITE.

Si `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` est bien applique par le natif AVANT
`IdunBattle.Operations.ActiveAbilityOperation$$GetAbilityEntities`, alors le natif doit poser sur la
TUILE **dans les deux regimes** -- c'est ce que ce probe mesure, et c'est ce qui etablit que le port
avait un regime de trop.

TROIS COLONNES, ET LE TEMOIN EST OBLIGATOIRE
--------------------------------------------
  * NATIF   : le cast live, canaux `tileMeta.tiles[].effects` ET `decisionView.units[].effects` ;
  * PORT    : `AbilityHandler.visit_ActiveAbilityMessage` rejoue offline depuis la MEME capture et
              le MEME MT, avec le MEME `targetId` d'unite ;
  * TEMOIN  : le port d'AVANT la tranche (resolution neutralisee). Sans lui, un accord natif/port ne
              distingue pas « la resolution porte le resultat » de « il vient d'ailleurs ».

⚠ Le champ du canal est `effectType`, PAS `type`, et `tileMeta.tiles[]` n'a PAS de champ `id` (les
entrees sont indexees par `(col,row)`) : les confondre rend deux dicts VIDES, donc « le natif ne pose
RIEN » -- la conclusion exactement inverse de la verite. Faute commise et corrigee dans #287-r12 ;
ce probe reutilise ses deux lecteurs plutot que d'en ecrire de nouveaux.

Discipline runner : state-file ABSOLU sous `logs/` (qui meurt avec le worktree), UN seul runner,
`--dispose` en fin de passe.
Usage (depuis scripts/python, session Frida chaude) :
    python probe_287r14_confront_live.py
    python probe_287r14_confront_live.py --dispose
ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import probe_287r12_confront_live as P12                             # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES, AbilityHandler   # noqa: E402
from engine.runner.messages import ActiveAbilityMessage              # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

VALKYRIE = P12.VALKYRIE                 # 1018
VALK_EFFECT = P12.VALK_EFFECT           # 1022
STATE = ROOT / "logs" / "_probe287r14_state.json"


def _porteurs_offline(st) -> list:
    """[ids] portant l'effet 1022 dans l'`EffectsState` du port -- unites ET tuiles partagent le
    meme dict `by_unit` (cle = l'entite porteuse, cf. case-35)."""
    if st.effects is None:
        return []
    return sorted(int(uid) for uid, effs in st.effects.by_unit.items()
                  for e in effs if int(e.effect_type) == VALK_EFFECT)


def _sans_resolution(fn):
    """TEMOIN = le port d'AVANT #287-r14 : `AActiveAbility$$GetActualTarget` rendait la cible de
    l'APPELANT telle quelle. On neutralise le foyer, pas la classe -- il est appele DEPUIS
    `abilities/base.py` par un import DIFFERE (donc re-execute a chaque appel : forme qui MORD)."""
    import engine.runner.abilities.behaviours.context as CTX
    vrai = CTX.actual_target

    def _identite(_state, _options, _caster_id, target_id):
        return target_id

    CTX.actual_target = _identite
    try:
        return fn()
    finally:
        CTX.actual_target = vrai


def joue(sid, rid) -> int:
    dv, vox = P12._to_my_turn(sid, rid, P12.VOXCASTER)
    if vox is None:
        print("[1018] Voxcaster absent du build -- NON CONFRONTE")
        return 1
    ennemis = P12._alive_enemies(dv, vox.get("owner"))
    if not ennemis:
        print("[1018] aucun ennemi vivant -- NON CONFRONTE")
        return 1
    cible = ennemis[0]
    dv0, ob0, snap0, tiles0, bg0, rng0 = P12._capture(sid, rid)
    board = Board((bg0 or {}).get("tiles") or [], adjacency="evenq")
    tuile = board.id_at(int(cible["pos"]["col"]), int(cible["pos"]["row"]))
    print(f"[1018] caster={vox['id']} cible UNITE={cible['id']} @({cible['pos']['col']},"
          f"{cible['pos']['row']}) -> tuile {tuile}")
    av_u = P12._effets_unites(dv0)
    av_t = P12._effets_tuiles(tiles0, board)

    # --- NATIF : cast avec un id d'UNITE (le regime que le port empruntait) -------------------
    res = P12._r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": vox["id"], "targetId": int(cible["id"]),
        "abilityType": VALKYRIE}}, 120)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    print(f"[1018] cast ok={bool(isinstance(res, dict) and res.get('ok'))} "
          f"action0.ok={a0.get('ok')} reason={a0.get('reason')}")
    dv1 = P12._r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
    tiles1 = P12._r(sid, "tileMeta", {"runnerId": rid}, 60)
    ap_u = P12._effets_unites(dv1)
    ap_t = P12._effets_tuiles(tiles1, board)
    natif_u = sorted(k for k, v in ap_u.items()
                     if VALK_EFFECT in v and VALK_EFFECT not in (av_u.get(k) or []))
    natif_t = sorted(k for k, v in ap_t.items()
                     if VALK_EFFECT in v and VALK_EFFECT not in (av_t.get(k) or []))
    print(f"[1018] NATIF  : 1022 pose sur UNITE(s)={natif_u}  TUILE(s)={natif_t}")

    # --- PORT (apres la tranche) et TEMOIN (avant), meme capture, meme MT ---------------------
    def _rejoue():
        st = load_state(dv0, ob0, snap0, board=board)
        if isinstance(rng0, dict) and "mt" in rng0:
            st.rng = P12._seed_rng(rng0)
        AbilityHandler(st).visit_ActiveAbilityMessage(ActiveAbilityMessage(
            caster_id=int(vox["id"]), target_id=int(cible["id"]), ability_type=VALKYRIE))
        return _porteurs_offline(st)

    port = _rejoue()
    temoin = _sans_resolution(_rejoue)
    print(f"[1018] PORT   : 1022 porte par {port}")
    print(f"[1018] TEMOIN : 1022 porte par {temoin}   (port d'AVANT la tranche)")

    ok_natif = (natif_t == [int(tuile)] and natif_u == [])
    ok_port = (port == [int(tuile)])
    ok_temoin = (temoin == [int(cible["id"])])
    print(f"\n[VERDICT] natif pose sur la TUILE seule      : {'OUI' if ok_natif else 'NON'}")
    print(f"[VERDICT] port apres tranche = natif          : {'OUI' if ok_port else 'NON'}")
    print(f"[VERDICT] temoin (avant) posait sur l'UNITE   : {'OUI' if ok_temoin else 'NON'}")
    return 0 if (ok_natif and ok_port and ok_temoin) else 1


def volet_1026(sid, rid) -> int:
    """GENERALISATION -- `1026 BasiliskBarrage`, un patron TOUT AUTRE que `1018` : pas de `Target()`
    dans l'arbre, mais un collapse imperatif qui TIRE ses tuiles au PRNG (`basilisk_shell_tiles`).
    C'est le scenario le plus a risque de la tranche : si la resolution deplacait la cible d'un cran
    de trop, la suite de tirages divergerait et les obus tomberaient ailleurs.

    On caste avec `targetId` = l'id d'**UNITE** (le regime que la tranche repare) et on confronte
    les coups NATIF aux coups du port rejoue depuis la MEME capture et le MEME MT."""
    dv, ord_u = P12._to_my_turn(sid, rid, P12.ORDNANCE)
    if ord_u is None:
        print("[1026] astraOrdnance absent du build -- NON CONFRONTE")
        return 1
    ens = P12._alive_enemies(dv, ord_u.get("owner"))
    if not ens:
        print("[1026] aucun ennemi vivant -- NON CONFRONTE")
        return 1
    dv0, ob0, snap0, tiles0, bg0, rng0 = P12._capture(sid, rid)
    board = Board(bg0["tiles"], adjacency="native_sym")
    cible = ens[0]
    tuile = board.id_at(cible["pos"]["col"], cible["pos"]["row"])
    print(f"[1026] caster={ord_u['id']} cible UNITE={cible['id']} -> tuile {tuile}")
    res = P12._r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": ord_u["id"], "targetId": int(cible["id"]),
        "abilityType": P12.BASILISK}}, 120)
    a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
    print(f"[1026] cast ok={bool(isinstance(res, dict) and res.get('ok'))} "
          f"action0.ok={a0.get('ok')} reason={a0.get('reason')}")
    natif = P12._coups(res, P12.BASILISK)
    print(f"[1026] NATIF  coups = {natif}")

    def _rejoue():
        st = load_state(dv0, ob0, snap0, board=board, tiles=tiles0)
        if rng0 and rng0.get("ok"):
            st.rng = P12._seed_rng(rng0)
        h = AbilityHandler(st)
        h.visit_ActiveAbilityMessage(ActiveAbilityMessage(
            caster_id=int(ord_u["id"]), target_id=int(cible["id"]),
            ability_type=P12.BASILISK))
        out = h.last or {}
        return (out.get("tiles"),
                [(a["target"], hh) for a in (out.get("attacks") or [])
                 for hh in ((a.get("attack") or {}).get("per_hit") or [])])

    tiles_ap, coups_ap = _rejoue()
    tiles_av, coups_av = _sans_resolution(_rejoue)
    print(f"[1026] PORT   : tuiles={tiles_ap} coups={coups_ap}")
    print(f"[1026] TEMOIN : tuiles={tiles_av} coups={coups_av}   (port d'AVANT la tranche)")
    ok = (len(natif) > 0 and coups_ap == natif)
    print(f"\n[VERDICT 1026] port apres tranche = natif, coup par coup : {'OUI' if ok else 'NON'}")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volet", choices=["1018", "1026"], default="1018")
    ap.add_argument("--seed", type=int, default=P12.SEED)
    ap.add_argument("--board", default=P12.BOARD)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--dispose", action="store_true")
    ns = ap.parse_args(argv)
    sid = _resolve_session()
    P12.STATE = STATE                      # state-file PROPRE a ce probe (jamais celui d'un autre)
    if ns.dispose:
        if STATE.exists():
            import json
            rid = int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])
            print(_rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=60))
            STATE.unlink()
        return 0
    rid = P12._rid(sid, ns.seed, ns.board, ns.rebuild)
    print(f"[runner] {rid}")
    return volet_1026(sid, rid) if ns.volet == "1026" else joue(sid, rid)


if __name__ == "__main__":
    raise SystemExit(main())
