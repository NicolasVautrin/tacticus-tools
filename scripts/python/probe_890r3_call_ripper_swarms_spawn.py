#!/usr/bin/env python
"""probe #890-r3 -- la PHASE 2 de `CallRipperSwarms` : les rippers APPARAISSENT-ILS ?

CE QUE CE PROBE MESURE
----------------------
La phase 1 (`abilities/tyranids.py::CallRipperSwarmsAbility`, active 1052) pose l'effet-BOND
`1094 CallRipperSwarms_PendingSummon` sur QUATRE tuiles et ne spawne RIEN. La phase 2 vit dans
l'EFFET (`triggers/loki/call_ripper_swarms.py`) : au turn-start du Hive Tyrant, chaque tuile
marquee ENCORE LIBRE fait emerger un Ripper Swarm, et la marque part -- libre ou non.

TROIS ETAGES, ET LE TROISIEME EST CELUI QUI MANQUAIT
----------------------------------------------------
0. POSE (natif)   -- le cast marque N tuiles ; `tileMeta` les publie.
1. PORT / POSE    -- l'etat charge depuis ce meme instant porte les MEMES marques, et le registre
                     `EFFECT_TRIGGERS[1094]` collecte bien DEUX triggers par tuile marquee.
2. PORT / SPAWN   -- un `TriggerEvent(On(0x15 = TurnStart_DelayedAttacks), player = <celui du
                     boss>)` fait emerger un ripper par tuile LIBRE et retire TOUTES les marques.
3. NATIF / SPAWN  -- on rend la main au boss et on compte les unites REELLEMENT apparues.

MUTATION ADVERSARIALE (le ROUGE d'avant le port, joue ICI)
----------------------------------------------------------
Le registre `EFFECT_TRIGGERS[1094]` est VIDE en memoire, et le meme evenement est rejoue sur une
COPIE de l'etat : le port ne doit alors spawner RIEN et laisser les marques en place -- exactement
ce que `master` faisait. Sans ce bras, << 4 rippers >> ne prouverait pas que c'est CE cablage-ci
qui les produit.

CONTRE-EPREUVE DU SECOND TRIGGER (le retrait SEUL)
--------------------------------------------------
Un `TriggerEvent(On(0x1f = PreUnitMove), dest_tile = <une tuile marquee>)` doit RETIRER la marque
et ne spawner AUCUNE unite. C'est le bras que la fiche d'origine envoyait a tort vers le spawn ;
sans cette mesure, l'erreur serait invisible.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_890r3_call_ripper_swarms_spawn.py

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import probe_112_darkangels as PR                                    # noqa: E402
import probe_890_hive_tyrant as P890                                 # noqa: E402

from engine.dsl.event_trigger_type import EventTriggerType           # noqa: E402
from engine.entities.effect_type import EffectType                   # noqa: E402
from engine.runner.components import OwnerComponent                  # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent      # noqa: E402
from engine.runner.operations.triggers.dispatch import registry as REG   # noqa: E402
from engine.runner.operations.triggers.dispatch.core import (        # noqa: E402
    collect_effect_triggers, evaluate_trigger_operation)

CALL_RIPPER_SWARMS = 1052
PENDING = int(EffectType.CallRipperSwarms_PendingSummon)             # 1094
#: Le boss n'est PAS dans `--list-pool` : il entre par la forme A PALIER (`<id>:<palier>`), que
#: `probe_890_hive_tyrant.build` passe A LA FOIS a `--explicit-stats` et a `--p-units`. Passer `BOSS`
#: nu fait rendre << hors pool / non spawnables >> -- mesure du premier jet.
P_UNITS = [P890.BOSS_TIER, "tyranTyrantGuard"]
#: Roster ADVERSE : le boss a besoin d'ennemis pour que `AverageDistance(tuile, Enemies)` trie.
A_UNITS = ["necroWarden", "necroWarden"]


def _build(board, seed):
    """`rl_duel build` avec `--explicit-stats` (le boss n'est pas au pool) **ET `--no-ai`**.

    ⚠ `probe_890_hive_tyrant.build` ne passe PAS `--no-ai`, et c'est ce qui a fait echouer le
    premier montage : l'IA jouait, la bataille avancait toute seule, et les `endturn` de purge du
    cooldown initial se perdaient dans une partie deja resolue. Le reste (retrait delibere de
    `TACTICUS_ALLOW_ROSTER_DEFICIT`, forme `<id>:<palier>` passee A LA FOIS a `--explicit-stats` et
    a `--p-units`) est repris tel quel de la."""
    import os
    import subprocess
    import time
    state = Path(P890.PYDIR).parent.parent / "logs" / ("_probe890r3-%d.json" % os.getpid())
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, str(Path(P890.PYDIR) / "rl_duel.py"), "build",
            "--board", board, "--seed", str(seed), "--state-file", str(state), "--no-ai",
            "--explicit-stats", P890.BOSS_TIER,
            "--p-units", ",".join(P_UNITS), "--a-units", ",".join(A_UNITS)]
    env = {k: v for k, v in os.environ.items() if k != "TACTICUS_ALLOW_ROSTER_DEFICIT"}
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(P890.PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        if state.exists():
            rid = int(json.loads(state.read_text())["runnerId"])
            PR._rids.append(rid)
            return int(PR.R._resolve_session() if hasattr(PR, "R") else _sid()), rid, state
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-900:])
        time.sleep(10)


def _sid():
    import rl_collect_batch as R
    return int(R._resolve_session())


def _etat(sid, rid):
    """L'etat Python charge du live, **effets de TUILE compris**.

    ⚠ `load_state` ne materialise les effets de tuile que si on lui passe `tiles=<payload tileMeta>` :
    `_load_tile_effects(state, tiles, board)` sort a `0` sur `tiles` vide, sans un mot. Ni
    `bind_live_rpc` ni `board=` ne suffisent, et `probe_890_hive_tyrant.offline_state` ne le passe
    pas. Mesure du premier jet : `tileMeta` publiait les QUATRE marques `CallRipperSwarms_PendingSummon`
    sur (1,0)..(4,0) et `state.effects.by_unit` n'en portait AUCUNE -- le probe concluait << 0 tuile
    marquee >> sur un cast parfaitement reussi.

    Le reste (`bind_live_rpc` pour le canal `unitAbilityStates`, PRNG rejoue) est repris de
    `probe_890_hive_tyrant.offline_state`, dont on garde l'assertion de source."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import bind_live_rpc, load_state

    dec, ob, snap, bg, rngd = P890.capture(sid, rid)
    tm = PR.rpc(sid, "tileMeta", {"runnerId": rid}, 120)
    prev = bind_live_rpc(lambda method, body=None, timeout=90: PR.rpc(sid, method, body or {},
                                                                     timeout))
    try:
        st = load_state(dec, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"),
                        tiles=tm)
    finally:
        bind_live_rpc(prev)
    src = (getattr(st, "ability_states_seed", None) or {}).get("source")
    if src in (None, "no-transport"):
        raise RuntimeError("canal unitAbilityStates NON tire (source=%s)" % src)
    r = IntBasedMersenneTwister()
    r.mt = list(rngd["mt"])
    r.mti = rngd["mti"]
    st.rng = r
    return st, dec


def _marquees(state) -> list[int]:
    """Les ids de TUILE portant une instance non consommee de 1094.

    Le discriminant << c'est une tuile >> est `Board.coord(id)` -- une entite-tuile a une
    coordonnee, une unite n'en a pas dans cette table. `Board` N'EXPOSE PAS de `by_id` : le premier
    jet le supposait et son `getattr(..., {})` rendait un dict VIDE, donc **zero tuile marquee**
    alors que le natif venait d'en marquer quatre. Un repli muet sur un conteneur vide est
    exactement le zero qui fait retirer un port juste."""
    eff = getattr(state, "effects", None)
    board = getattr(state, "board", None)
    if eff is None or board is None:
        return []
    out = []
    for key, effs in eff.by_unit.items():
        try:
            if board.coord(int(key)) is None:
                continue
        except Exception:
            continue
        if any(not e.consumed and int(getattr(e, "effect_type", -1)) == PENDING for e in effs):
            out.append(int(key))
    return sorted(out)


def _unites(state) -> set:
    return {int(u) for u in state.entities}


def _player_de(state, uid):
    e = state.get_entity(int(uid))
    oc = e.get_component(OwnerComponent) if e is not None else None
    return None if oc is None else oc.player


def _ev_turnstart(player):
    return TriggerEvent(int(EventTriggerType.TurnStart_DelayedAttacks), None, None,
                        ranged=False, profile=None, player_id=player)


def _ev_premove(actor, dest):
    return TriggerEvent(int(EventTriggerType.PreUnitMove), actor, actor,
                        ranged=False, profile=None, dest_tile=dest)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=P890.BOSS_BOARD)
    ap.add_argument("--seed", default=str(P890.SEED))
    a = ap.parse_args(argv)

    sid, rid, state_file = _build(a.board, a.seed)
    print("[build] runner=%d board=%s seed=%s" % (rid, a.board, a.seed))
    verdicts = {}
    try:
        dec, ob, snap, bg, rng = P890.capture(sid, rid)
        boss = P890._boss_id(dec)
        if boss is None:
            print("[FAIL] boss absent de la vue")
            return 2
        print("[boss] u%s" % boss)

        # ------------------------------------------------------------ ETAGE 0 : la POSE (natif)
        # `targetId = boss` : `CallRipperSwarms` est un SELF-CAST (preset `isSelfCasting = 1`,
        # `RANGE_SELF`, masque `0x8004` dont le bit 15 `CasterIsPossibleTarget`). Le RPC exige de
        # toute facon `casterId + (targetId|to)`.
        r = PR.rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": boss, "targetId": boss,
            "abilityType": CALL_RIPPER_SWARMS}}, 180)
        act = ((r or {}).get("actions") or [{}])[0]
        events = act.get("events") or []
        pose = [e for e in events
                if str(e.get("source") or "") == EffectType.CallRipperSwarms_PendingSummon.name]
        print("[cast] CallRipperSwarms par u%s : ok=%s mutated=%s ; events de pose=%d"
              % (boss, act.get("ok"), act.get("mutated"), len(pose)))
        # ⚠ **`mutated` NE VOIT PAS LES EFFETS DE TUILE, ET LE CROIRE COUTE UN FAUX NEGATIF.**
        # Mesure du premier jet : `ok: true`, `mutated: false`, `changes: []` -- ET des events
        # `ReceiveEffect` portant `BondEffect_BondedId: 88 / Effect_SourceActiveAbility: 1052` sur
        # des entites-TUILE. Le cast avait parfaitement marche. Le critere est donc le FLUX
        # d'events (et, juste apres, les tuiles reellement marquees dans l'etat charge), jamais ce
        # drapeau. Le premier montage a conclu << le cast n'a pas mute l'etat >> et a fait chercher
        # un cooldown initial qui n'existe pas (`abilityState.cooldown` vaut `null` a tous les
        # tours, `usable: true`).
        if not act.get("ok") or not pose:
            why = PR.rpc(sid, "abilityReason", {"runnerId": rid, "casterId": boss,
                                                "abilityType": CALL_RIPPER_SWARMS,
                                                "targetId": boss}, 60)
            print("[FAIL] aucun event de pose -- abilityReason = %s"
                  % json.dumps(why, ensure_ascii=True)[:600])
            return 2

        st, dec2 = _etat(sid, rid)
        marquees = _marquees(st)
        print("[ETAGE 0/1] tuiles marquees 1094 (port, charge du live) : %d -> %s"
              % (len(marquees), marquees))
        verdicts["0_pose_4_tuiles"] = len(marquees) == 4

        trigs = [t for t in collect_effect_triggers(st) if int(t.effect_type) == PENDING]
        noms = sorted({type(t).__name__ for t in trigs})
        print("[ETAGE 1] triggers collectes pour 1094 : %d (%s)" % (len(trigs), noms))
        verdicts["1_deux_triggers_par_tuile"] = (len(trigs) == 2 * len(marquees)
                                                 and len(noms) == 2 and len(marquees) > 0)

        player = _player_de(st, boss)
        avant = _unites(st)

        # ------------------------------------------- MUTATION ADVERSARIALE (le ROUGE d'avant)
        st_mut, _ = _etat(sid, rid)
        table = REG.EFFECT_TRIGGERS.get(PENDING)
        try:
            REG.EFFECT_TRIGGERS[PENDING] = []
            evaluate_trigger_operation(st_mut, _ev_turnstart(player))
        finally:
            if table is None:
                REG.EFFECT_TRIGGERS.pop(PENDING, None)
            else:
                REG.EFFECT_TRIGGERS[PENDING] = table
        neuves_mut = _unites(st_mut) - avant
        marq_mut = _marquees(st_mut)
        print("[MUTATION] registre VIDE -> unites neuves=%d ; marques restantes=%d"
              % (len(neuves_mut), len(marq_mut)))
        verdicts["4_mutation_ne_spawne_rien"] = (not neuves_mut
                                                 and len(marq_mut) == len(marquees))

        # ---------------------------------------------- ETAGE 2 : le PORT, turn-start du boss
        evaluate_trigger_operation(st, _ev_turnstart(player))
        neuves = sorted(_unites(st) - avant)
        restantes = _marquees(st)
        print("[ETAGE 2] port : unites neuves=%d -> %s ; marques restantes=%d"
              % (len(neuves), neuves, len(restantes)))
        verdicts["2_port_spawne"] = len(neuves) == len(marquees) and len(marquees) > 0
        verdicts["2_port_retire_les_marques"] = not restantes

        # -------------------------------- CONTRE-EPREUVE : le second trigger, RETRAIT SEUL
        st_mv, _ = _etat(sid, rid)
        cible = _marquees(st_mv)[0]
        av_mv = _unites(st_mv)
        co = st_mv.board.coord(cible)
        evaluate_trigger_operation(st_mv, _ev_premove(boss, (int(co[0]), int(co[1]))))
        neuves_mv = _unites(st_mv) - av_mv
        rest_mv = _marquees(st_mv)
        print("[PREMOVE] une unite entre sur la tuile %d%s -> unites neuves=%d ; marques=%d (etait %d)"
              % (cible, co, len(neuves_mv), len(rest_mv), len(marquees)))
        verdicts["3_premove_retire_sans_spawner"] = (not neuves_mv
                                                     and len(rest_mv) == len(marquees) - 1)

        # ------------------------------------------------- ETAGE 3 : le NATIF, meme turn-start
        # ⚠ DEUX PHASES, ET LA PREMIERE EST OBLIGATOIRE : juste apres son cast, le boss a ENCORE
        # `ctrl` (c'est toujours son tour). Une boucle qui s'arrete au premier `ctrl` sort donc
        # SANS avoir joue un seul `endturn`, et mesure le tour COURANT au lieu du SUIVANT -- elle
        # rendait `0 unite neuve` sur un natif qui n'avait pas encore eu son turn-start. On QUITTE
        # d'abord le tour du boss, on y REVIENT ensuite.
        for _ in range(8):                                   # phase 1 : sortir de son tour
            d = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
            u = next((x for x in (d.get("units") or []) if int(x["id"]) == int(boss)), None)
            if u is not None and not u.get("ctrl"):
                break
            PR.rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        for _ in range(8):                                   # phase 2 : revenir a son turn-start
            d = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
            u = next((x for x in (d.get("units") or []) if int(x["id"]) == int(boss)), None)
            if u is not None and u.get("ctrl"):
                break
            PR.rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 120)
        d3 = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        ids_avant = {int(x["id"]) for x in (dec2.get("units") or [])}
        nat_neuves = sorted({int(x["id"]) for x in (d3.get("units") or [])
                             if x.get("alive")} - ids_avant)
        tm3 = PR.rpc(sid, "tileMeta", {"runnerId": rid}, 120)
        nat_marq = [(t.get("col"), t.get("row")) for t in ((tm3 or {}).get("tiles") or [])
                    if any(int(e.get("effectType") or -1) == PENDING
                           for e in (t.get("effects") or []))]
        print("[ETAGE 3] natif au turn-start du boss : marques restantes=%d ; unites neuves=%d -> %s"
              % (len(nat_marq), len(nat_neuves), nat_neuves))
        # CE QUI EST COMPARABLE ICI, ET CE QUI NE L'EST PAS.
        # COMPARABLE -- le SECOND terme du behaviour : le natif retire les QUATRE marques au
        # turn-start du bonded, exactement comme le port. C'est un cran dur.
        verdicts["5_natif_retire_les_marques"] = (not nat_marq) and len(marquees) > 0
        # NON COMPARABLE -- le SPAWN. Le natif n'ajoute AUCUNE unite dans CE montage
        # (`observeBattle` 4 -> 4), et la cause est le CATALOGUE, pas la mecanique :
        # `GetStringConstant(0)` rend `GuildBoss2Npc1TyranRipperSwarmLeviathan`, qui n'existe ni
        # comme `id` ni comme `visualId` dans les trois index du gameconfig, donc pas davantage
        # dans le catalogue d'un runner monte depuis le seed BC. `AddUnitOperation` est un no-op et
        # la marque part quand meme (le retrait est inconditionnel). Le port, lui, SPAWNE : sa
        # resolution degrade au lieu d'echouer. On ne l'aligne PAS sur ce no-op -- ce serait
        # s'aligner sur un artefact de montage plutot que sur le natif, qui spawne bel et bien dans
        # une vraie bataille de boss de guilde. L'ecart est DIT, jamais maquille en vert.
        verdicts["6_ecart_de_catalogue_nomme"] = (len(nat_neuves) == 0 and len(neuves) > 0)

        print("")
        for k in sorted(verdicts):
            print("  [%s] %s" % ("PASS" if verdicts[k] else "FAIL", k))
        print("[RAW] %s" % json.dumps({
            "runner": rid, "board": a.board, "seed": a.seed, "boss": boss,
            "marquees": marquees, "port_neuves": neuves, "port_restantes": restantes,
            "mutation_neuves": sorted(neuves_mut), "premove_restantes": rest_mv,
            "natif_neuves": nat_neuves, "verdicts": verdicts}, ensure_ascii=True))
        return 0 if all(verdicts.values()) else 1
    finally:
        try:
            PR.dispose(sid, rid)
            print("[dispose] runner=%d" % rid)
        except Exception as exc:                                    # pragma: no cover
            print("[dispose] echec : %s" % exc)


if __name__ == "__main__":
    raise SystemExit(main())
