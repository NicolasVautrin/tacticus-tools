"""probe #585 -- MESURE de la POSE de `WarHowl` (1106) : QUI recoit `WarHowl_ExtraDamage_Unstoppable`
(1222), et le trait `Unstoppable` (0x412) suit-il l'effet dans les DEUX sens ?

CE QUE CE PROBE TRANCHE, et pourquoi il fallait le monter
---------------------------------------------------------
`docs/rl/case-366-r1-war-howl-extra-damage.md` §2 note que le cast n'avait PAS buffe
`spaceRockfist` et l'explique par « (armes a distance) ». Or `spaceRockfist` (« Arjac ») n'a
**qu'une** arme, MELEE (`Range` absent), au gameconfig COMME dans `data/seed-bc.json`
(`Power`, 3 coups, aucune entree a `Range`). Le selecteur natif
`IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$OtherBuffTargets` filtre par
`UnitsWithoutRangedWeapons` -> `IdunBattle.Entities.Selectors.UnitsWithoutWeaponsSelector$$Select`,
dont le predicat est `IdunShared.Battle.WeaponProfile$$get_IsRanged` (= `get_IsMelee ^ 1`, seuil
`Range >= 2`) : Arjac DOIT donc etre buffe. L'annotation de la fiche etait une INTERPRETATION,
jamais mesuree -- les deux unites non buffees ce jour-la etaient tres probablement dans l'equipe
ADVERSE (le montage de `probe_366_r1` ne met que DEUX unites du cote joueur, et `Friends` suffit
alors a les ecarter sans qu'aucune arme n'entre en jeu).

Le probe monte donc les TROIS Space Wolves du MEME cote et regarde qui recoit quoi :

    P : spaceBlackmane (Ragnar, le CASTER)  -- 1 arme Chain, melee
        spaceRockfist  (Arjac)              -- 1 arme Power, MELEE     -> DOIT etre buffe
        spaceStormcaller                    -- 2 armes Psychic, une a `Range = 2` -> NON buffe
    A : deux necrons (le selecteur est `Friends` : ils ne peuvent pas entrer)

C'est un DISCRIMINANT a trois valeurs distinctes attendues sur la MEME equipe, pas un accord
global : le caster entre par le `op_Addition`, Arjac par le filtre d'armes, Stormcaller en est
exclu par lui. Un port qui ne filtrerait rien, un port qui filtrerait sur le mauvais seuil et un
port qui n'ajouterait pas le caster rendent TROIS resultats differents.

TROIS axes mesures, a trois instants (avant cast / apres cast / apres un tour complet) :
  * `combatSnapshot.units[].effects` -> qui porte 1222, et pour combien de tours ;
  * `combatSnapshot.units[].traits`  -> qui porte 1042 (`UnitTrait.Unstoppable`) ;
  * le PORT rejoue sur le MEME etat (`war_howl_buff_targets()` evalue contre le `State` charge du
    snapshot) -- l'ensemble des cibles doit etre IDENTIQUE a celui du live.

⚠ `spaceRockfist` et `spaceStormcaller` portent DEJA `Unstoppable` a leur kit, et c'est
LOAD-BEARING pour le 3e axe : leur trait ne doit PAS disparaitre a l'expiration de 1222. C'est le
cran que porte `BaseEffect.applied_trait_grants` (mirror du `if (!coll.Add(trait)) return` de
`IdunBattle.Operations.AddTraitOperation$$Execute`, transporte jusqu'au revert). `spaceBlackmane`,
lui, ne l'a pas -> c'est LUI le temoin de l'ajout PUIS du retrait.

Usage (depuis `scripts/python`) :
    python probe_585_war_howl_pose.py --state-file <ABSOLU hors data/>.json [--seed 777]
    python probe_585_war_howl_pose.py --state-file ... --keep     # ne dispose pas le runner
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent

RAGNAR = "spaceBlackmane"         # le CASTER -- seul porteur de l'active `WarHowl` (1106)
MELEE_ALLY = "spaceRockfist"      # ami MELEE PUR : le discriminant contre l'annotation de case-366
RANGED_ALLY = "spaceStormcaller"  # ami a arme `Range = 2` -> ecarte par UnitsWithoutRangedWeapons
FOES = "necroWarden,necroSpyder"
BOARD = "MC1_67"

WAR_HOWL = 1106                   # ActiveAbilityType.WarHowl
BUFF = 1222                       # EffectType.WarHowl_ExtraDamage_Unstoppable (0x4c6)
BUFF_NAME = "WarHowl_ExtraDamage_Unstoppable"   # `decisionView` ne publie que le NOM de l'effet
UNSTOPPABLE = 1042                # UnitTrait.Unstoppable (0x412)


def _unwrap(r):
    """Deballe la reponse RPC du host (`{ok, result}` ou la valeur brute)."""
    if isinstance(r, dict) and "result" in r and set(r) <= {"ok", "result", "error"}:
        return r["result"]
    return r


def _by_unit(snap, dv):
    """DEUX canaux, parce qu'aucun ne porte les deux axes :
      * `combatSnapshot.units[]` -> `traits` (l'invoke de
        `IdunBattle.Entities.UnitExtensions$$HasTrait` par valeur d'enum, donc la RESULTANTE des
        collections du `BaseUnitComponent` -- pas une lecture de collection) et
        `unitConfig.visualId` ;
      * `decisionView.units[]`   -> `effects[].name` (le canal ACTIF-ONLY des effets portes).
    Cle commune : `entityId` du snapshot == `id` de la vue decision."""
    names = {}
    for u in (dv or {}).get("units") or []:
        uid = u.get("id")
        if uid is None:
            continue
        names[int(uid)] = sorted(e.get("name") for e in (u.get("effects") or []) if e.get("name"))
    out = {}
    for u in (snap or {}).get("units") or []:
        uid = u.get("entityId")
        if uid is None:
            continue
        out[int(uid)] = {"vis": ((u.get("unitConfig") or {}).get("visualId")),
                         "traits": sorted(int(t) for t in (u.get("traits") or [])),
                         "effects": names.get(int(uid), [])}
    return out


def _line(tag, uid, rec):
    print("[576/%s] u%-4s %-18s buff1222=%-5s unstoppable=%-5s effets=%s"
          % (tag, uid, rec["vis"], BUFF_NAME in rec["effects"],
             UNSTOPPABLE in rec["traits"], rec["effects"]))


def _build(state_file, seed):
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", BOARD,
            "--p-units", "%s,%s,%s" % (RAGNAR, MELEE_ALLY, RANGED_ALLY),
            "--a-units", FOES, "--state-file", state_file, "--no-ai"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not Path(state_file).exists():
        print("[576] build KO : %s" % (p.stderr or p.stdout or "")[-600:])
        return None
    return json.loads(Path(state_file).read_text())["runnerId"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU, hors data/")
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en sortie")
    ap.add_argument("--land-turns", type=int, default=0,
                    help="tours a passer AVANT le cast pour faire ATTERRIR les unites en deep "
                         "strike (`TeleportStrike_TeleportingIn`) -- 2 = un tour complet")
    a = ap.parse_args(argv)

    import rl_collect_batch as R
    sid = R._resolve_session()
    w = _unwrap(R._rpc(sid, "autoBootExtraire", [{}], timeout=180))
    if not (isinstance(w, dict) and w.get("ok")):
        print("[576] amorce KO : %s" % str(w)[:200])
        return 2

    def rpc(method, body=None, timeout=60):
        return _unwrap(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    rid = _build(a.state_file, a.seed)
    if rid is None:
        return 2
    print("[576] runner %s (board %s seed %s)" % (rid, BOARD, a.seed))
    rc = 0
    try:
        # ATTERRISSAGE. `spaceRockfist` porte le trait `TeleportStrike` : au tour 1 il est en DEEP
        # STRIKE (effet `TeleportStrike_TeleportingIn`), donc HORS du pool `EntityPool.AliveUnits`
        # que lit `<DSLSelectors+0x20>`. Sans ce passage de tours, le bras « ami MELEE » ne mesure
        # pas ce qu'il annonce -- c'est un fait de MONTAGE, pas un filtre du selecteur.
        for _ in range(max(0, a.land_turns)):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        # Les canaux d'AVANT le cast sont CAPTURES : c'est l'etat que le port rejouera (bras 4).
        snap0 = rpc("combatSnapshot", {"runnerId": rid})
        dv0 = rpc("decisionView", {"runnerId": rid})
        ob = rpc("observeBattle", {"runnerId": rid})
        bg = rpc("boardGraph", {"runnerId": rid})
        before = _by_unit(snap0, dv0)
        ids = {r["vis"]: uid for uid, r in before.items()}
        caster = ids.get(RAGNAR)
        if caster is None:
            print("[576] KO -- %s absent du snapshot (%s)" % (RAGNAR, sorted(ids)))
            return 2
        print("== AVANT CAST ==")
        for uid in sorted(before):
            _line("avant", uid, before[uid])

        # `isSelfCasting = 1` -> `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` rend le
        # CASTER quelle que soit la cible passee ; on la passe explicitement pour ne rien deviner.
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster, "targetId": caster,
            "abilityType": WAR_HOWL}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        if not (isinstance(res, dict) and res.get("ok") and a0.get("ok")):
            print("[576] cast REFUSE : %s" % str(res)[:300])
            return 2

        snap = rpc("combatSnapshot", {"runnerId": rid})
        dv = rpc("decisionView", {"runnerId": rid})
        after = _by_unit(snap, dv)
        print("== APRES CAST ==")
        for uid in sorted(after):
            _line("apres", uid, after[uid])
        buffed = sorted(uid for uid, r in after.items() if BUFF_NAME in r["effects"])
        print("[576] LIVE  buffes = %s (%s)" % (buffed, [after[u]["vis"] for u in buffed]))
        gained = sorted(uid for uid in before
                        if UNSTOPPABLE not in before[uid]["traits"]
                        and UNSTOPPABLE in after.get(uid, before[uid])["traits"])
        print("[576] TRAIT 1042 gagne au cast (LIVE) : %s (%s)"
              % (gained, [after[u]["vis"] for u in gained]))
        if not gained:
            print("[576] ATTENTION -- aucun temoin d'AJOUT : le bras trait ne prouve rien")
            rc |= 1

        # --- le PORT, sur le MEME etat ---------------------------------------------------------
        from engine.runner.snapshot import load_state
        from engine.runner.abilities.spacewolves import war_howl_buff_targets
        from engine.runner.abilities.behaviours.context import entities_from_state
        from engine.entities.pathfinding.board import Board
        state = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
        sel = war_howl_buff_targets().evaluate(entities_from_state(state, int(caster)))
        port = sorted(int(u["id"]) for u in sel
                      if isinstance(u, dict) and u.get("id") is not None)
        print("[576] PORT  cibles = %s" % port)
        same = (port == buffed)
        print("[576] VERDICT selecteur : %s" % ("OK" if same else "DIVERGE"))
        rc |= 0 if same else 1

        # --- FACE PORT du TRAIT : le port POSE-T-IL, puis RETIRE-T-IL, `Unstoppable` ? -----------
        # ⚠ Ce bras est CE QUI COUPLE la garde a la valeur du PORT. Les trois bras precedents ne
        # lisent que l'oracle natif (`combatSnapshot.units[].traits`) : ils resteraient VERTS si
        # `WarHowlExtraDamageUnstoppableEffect.applied_traits` rendait `[]`. On rejoue donc
        # `execute_behaviour` sur un `State` charge de l'etat d'AVANT le cast et on lit les traits
        # du port -- l'ajout, puis le retrait au tick de fin de tour.
        state0 = load_state(dv0, ob, snap0, board=Board(bg["tiles"], adjacency="native_sym"))
        from engine.runner.abilities.spacewolves import WarHowlAbility
        from engine.runner.components import StatsComponent
        from engine.runner.operations.turnflow import EndTurnOperation
        from engine.entities.traits.unit_trait import entity_trait_names

        def _port_traits(st, uid):
            e = st.get_entity(int(uid))
            sc = e.get_component(StatsComponent) if e is not None else None
            return set(entity_trait_names(getattr(sc, "ctx", None), None))

        pre = {uid: _port_traits(state0, uid) for uid in sorted(before)}
        WarHowlAbility().execute_behaviour(state0, int(caster), int(caster))
        mid = {uid: _port_traits(state0, uid) for uid in sorted(before)}
        gained_port = sorted(uid for uid in pre if "Unstoppable" not in pre[uid]
                             and "Unstoppable" in mid[uid])
        print("[576] PORT  trait Unstoppable gagne au cast : %s" % gained_port)
        ok_port_add = (gained_port == gained)
        print("[576] VERDICT face PORT (ajout du trait) : %s"
              % ("OK" if ok_port_add else "DIVERGE (natif %s)" % gained))
        rc |= 0 if ok_port_add else 1
        # Expiration OFFLINE : `turns = Get(1)` -> UN tick suffit (`EndTurnOperation` -> tick des
        # effets puis `revert_traits_of_removed_effects`).
        EndTurnOperation.execute(state0, advance=False)
        post = {uid: _port_traits(state0, uid) for uid in sorted(before)}
        ok_port_rev = all(pre[uid] == post[uid] for uid in pre)
        for uid in sorted(pre):
            if pre[uid] != post[uid]:
                print("[576] PORT  trait NON RESTITUE u%s : %s -> %s"
                      % (uid, sorted(pre[uid] - post[uid]), sorted(post[uid] - pre[uid])))
        print("[576] VERDICT face PORT (retrait du trait) : %s" % ("OK" if ok_port_rev else "KO"))
        rc |= 0 if ok_port_rev else 1

        # --- expiration : un tour COMPLET (turns = Get(1) = 1 TOUR) -----------------------------
        for _ in range(2):                       # mon tour, puis celui de l'adversaire
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        end = _by_unit(rpc("combatSnapshot", {"runnerId": rid}),
                       rpc("decisionView", {"runnerId": rid}))
        print("== APRES UN TOUR COMPLET ==")
        for uid in sorted(end):
            _line("fin", uid, end[uid])
        still = sorted(uid for uid, r in end.items() if BUFF_NAME in r["effects"])
        print("[576] LIVE  portent ENCORE 1222 = %s" % still)
        ok_traits = True
        for uid in sorted(set(before) & set(end)):
            was, now = UNSTOPPABLE in before[uid]["traits"], UNSTOPPABLE in end[uid]["traits"]
            if was != now:
                print("[576] TRAIT NON RESTITUE u%s %s : avant=%s fin=%s"
                      % (uid, end[uid]["vis"], was, now))
                ok_traits = False
        print("[576] VERDICT trait rendu a l'etat initial : %s" % ("OK" if ok_traits else "KO"))
        rc |= 0 if ok_traits else 1
    finally:
        if not a.keep:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 20)
            except Exception as exc:                       # noqa: BLE001 -- diagnostic seul
                print("[576] dispose KO : %s" % str(exc)[:160])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
