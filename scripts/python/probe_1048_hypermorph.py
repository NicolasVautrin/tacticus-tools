#!/usr/bin/env python
"""probe_1048_hypermorph -- `Hypermorph` (EffectType 0x54d = 1357), passif du summon
`genesSmnAberrant` << Aberrant Hypermorph >> et du npc `genesNpc1Aberrant`.

LA QUESTION BINAIRE
-------------------
Le bonus d'ATTAQUE que ce passif pose sur son porteur vaut-il, cote port, EXACTEMENT ce que le
natif pose -- y compris sur les PV ou la regle de trois et l'arithmetique Fix64 DIVERGENT ?

CE QUE LE DECOMPILE DIT (build `rnca9r7q6c`)
--------------------------------------------
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HypermorphAbility$$CreateTrigger` =
    <DSLTriggers+0x30> | ( On(0x1e = HealthChanged, ownerNeedsToBeAlive: true) & get_OwnerIsTarget )
`...HypermorphAbility$$CreateBehaviour` =
    RemoveEffect(Owner@<DSLSelectors+0x30>, Nullable<EffectType>(0x54d))
  + AddDynamicStatModifierEffectToOwner(0x54d, statType = 0 = Attack, turns = null, isHidden = false)
`IdunBattle.Entities.Effects.Loki.HypermorphEffect$$GetDynamicStatModificationAmount(owner, target,
effect)` =
    (int)( Fix64(GetStat(target, 5 = Health, 0 = Current))
           * Fix64.Round(Fix64(GetNumberConstant(0x4f = healthPct)) / 100 * 100, 0) / 100 )

CE QUE CE PROBE FORCE, ET POURQUOI
-----------------------------------
`op_Explicit` est un **FLOOR**, et `15/100` vaut `0.14999999997671694` en Q31.32 : le natif rend
donc **une unite de MOINS** que la regle de trois des que `hp * healthPct / 100` tombe sur un
ENTIER. Les PV NATURELS des deux porteurs (75 au palier 1, 4154 au palier 50) ne tombent PAS sur
un entier -- ils confirment la magnitude sans jamais exercer ce quirk. Le montage FORCE donc
`--hp-player 2000` : 15 % de 2000 = 300 exact, et le natif y rend **299**. C'est le seul point de
mesure ou un port naif (`hp * pct // 100`) et le mirror Fix64 DISENT DEUX CHOSES DIFFERENTES.

QUATRE VOLETS
-------------
  A. QUIRK      -- offline pur : table `hp -> mirror Fix64` vs regle de trois, et la liste des hp
                   ou elles divergent. Aucune dependance live (joue meme sans session).
  B. NATIF      -- `combatSnapshot.statDelta.attack` des deux Aberrants a `--hp-player 2000`.
  C. PORT       -- la meme grandeur re-derivee par `load_state` + `applied_stat_mods`, ATTRIBUEE a
                   la cle de l'effet (pas au residu opaque `CAPTURED_SOURCE`).
  D. RECALCUL   -- on BLESSE le porteur (tour de l'IA adverse) et on re-mesure : la seconde branche
                   du trigger (`On(HealthChanged) & OwnerIsTarget`) doit faire SUIVRE le bonus.
                   Cote port il n'y a pas d'event : la magnitude est lue A LA LECTURE, donc c'est
                   la MEME assertion qui la garde.

MONTAGE (les deux porteurs a la fois, aucun n'est un heros)
------------------------------------------------------------
`--explicit-stats genesNpc1Aberrant --explicit-stats genesSmnAberrant` : le npc ET le summon
arrivent avec LEURS stats natives (`UnitProgression$$GetNpcStats` / `$$GetSummonStats`), sans
passer par la formule heros qui LEVE sur eux. La voie summon canonique (spawner `genesBiophagus`
puis `AberrantHypermorph`) n'est PAS necessaire ici : la magnitude ne lit ni le caster ni le
vecteur de pose, seulement les PV du porteur.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.effects.loki.hypermorph import (                # noqa: E402
    HYPERMORPH, hypermorph_extra_damage)
from engine.entities.effects.magnitude import ability_var            # noqa: E402
from engine.entities.stats import StatType                           # noqa: E402
from engine.runner.components import StatsComponent                  # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
_seq = itertools.count()

NPC = "genesNpc1Aberrant"        # npc porteur (npc-registry.tsv)
SUMMON = "genesSmnAberrant"      # summon porteur (summons-registry.tsv), invoque par genesBiophagus
FOES = "ultraTitus,ultraApothecary,ultraCalgar"
SEED = "777"
BOARD = "MC1_67"
#: 15 % de 2000 = 300 EXACT -> c'est la ou le FLOOR Fix64 se voit (natif : 299).
HP_FORCE = 2000
EFFECT_NAME = "Hypermorph"


def _r(sid, method, body, timeout=60):
    out = _rpc(sid, method, [body], timeout) or {}
    return out.get("result", out) if isinstance(out, dict) else out


def _build(sid, hp_player: int, extra: "list[str] | None" = None,
           p_units: "str | None" = None, explicit: "list[str] | None" = None) -> "tuple[int, Path]":
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe1048-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD, "--no-ai",
            "--state-file", str(state),
            "--p-units", p_units or ("%s,%s,ultraTitus" % (NPC, SUMMON)),
            "--hp-player", str(int(hp_player)),
            "--a-units", FOES]
    for uid in (explicit if explicit is not None else [NPC, SUMMON]):
        argv += ["--explicit-stats", uid]
    argv += list(extra or [])
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out and "runner creation paused" not in out:
            raise RuntimeError("build KO : " + out[-400:])
        if time.time() >= deadline:
            raise RuntimeError("build KO (cap/drain jamais libere) : " + out[-400:])
        time.sleep(10)


def _capture(sid, rid):
    dv = _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 150)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    sn = _r(sid, "combatSnapshot", {"runnerId": rid}, 90)
    return dv, ob, sn, load_state(dv, ob, sn)


def _carriers(sn) -> dict:
    """`entityId -> (hp courant, delta d'attaque)` des unites dont le `visualId` est un Aberrant.
    `statDelta` est la part MODIFICATION de la stat, exactement ce que pose
    `AStatModifierEffect$$ApplyModification` (`ChangeStat`, part 5)."""
    out = {}
    for u in (sn.get("units") or []):
        if ((u.get("unitConfig") or {}).get("visualId")) != SUMMON:
            continue
        out[int(u["entityId"])] = (int((u.get("stats") or {}).get("health") or 0),
                                   int((u.get("statDelta") or {}).get("attack") or 0))
    return out


def _port_attr(state, uid: int) -> int:
    """Part de la modification ATTACK que le PORT attribue a l'effet `Hypermorph` chez `uid`.
    La cle de source est le tuple `statmod_source_key` (`("statmod", effect_type, source, name)`) --
    on la reconnait par le NOM de l'effet, jamais par sa position."""
    e = state.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None or getattr(sc, "ctx", None) is None:
        return 0
    comp = sc.ctx.stats.components.get(int(StatType.ATTACK))
    if comp is None:
        return 0
    return sum(int(v) for k, v in comp.modification.per_source.items()
               if isinstance(k, tuple) and EFFECT_NAME in [x for x in k if isinstance(x, str)])


def volet_a() -> int:
    """QUIRK Fix64, offline pur -- ou le mirror et la regle de trois divergent."""
    pct = int(ability_var(HYPERMORPH, "healthPct", is_constant=True) or 0)
    print("[A] gameconfig %s.constants.healthPct = %d" % (HYPERMORPH, pct))
    if pct <= 0:
        print("[A] KO : constante illisible")
        return 1
    ko = 0
    print("[A] %8s %8s %8s" % ("hp", "fix64", "hp*p//100"))
    for hp in (20, 75, 100, 1000, 1234, 2000, 2001, 4154, 999999):
        a, b = hypermorph_extra_damage(hp, pct), hp * pct // 100
        print("[A] %8d %8d %8d %s" % (hp, a, b, "<-- DIVERGE" if a != b else ""))
    div = [hp for hp in range(1, 4001) if hypermorph_extra_damage(hp, pct) != hp * pct // 100]
    print("[A] %d hp sur 4000 ou la regle de trois DIVERGE du natif (tous multiples de 20 : %s)"
          % (len(div), all(h % 20 == 0 for h in div)))
    if not div:
        print("[A] KO : aucun point de divergence -> le montage ne peut rien discriminer")
        ko = 1
    return ko


def _duel(state_file: Path, *args, timeout=600) -> str:
    p = subprocess.run([sys.executable, "rl_duel.py", *args, "--state-file", str(state_file)],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return (p.stdout or "") + (p.stderr or "")


def volet_bc(sid) -> int:
    """Les DEUX porteurs a `hp = 2000` : `15 % x 2000 = 300` exact, le natif rend 299."""
    ko = 0
    pct = int(ability_var(HYPERMORPH, "healthPct", is_constant=True) or 0)
    rid, state_file = _build(sid, HP_FORCE)
    try:
        dv, ob, sn, st = _capture(sid, rid)
        live = _carriers(sn)
        if not live:
            print("[B] KO : aucun porteur Aberrant dans le snapshot")
            return 1
        for uid, (hp, delta) in sorted(live.items()):
            want = hypermorph_extra_damage(hp, pct)
            naif = hp * pct // 100
            got = _port_attr(st, uid)
            tag = "OK " if (delta == want and got == want) else "KO "
            ko |= 0 if tag == "OK " else 1
            print("[B/C] %s u%-4d hp=%-6d natif=%-5d port=%-5d mirror=%-5d naif=%-5d"
                  % (tag, uid, hp, delta, got, want, naif))
    finally:
        _duel(state_file, "dispose")
    return ko


def volet_d(sid) -> int:
    """RECALCUL -- on BLESSE le porteur et le bonus doit SUIVRE (2e branche du trigger,
    `On(0x1e = HealthChanged) & get_OwnerIsTarget`).

    La geometrie est PILOTEE, jamais subie : les DEUX porteurs sont poses au CONTACT du camp
    adverse (l'IA a donc de quoi frapper des le premier tour), et leurs PV sont montes a 900 000
    pour qu'ils ENCAISSENT au lieu de mourir -- `GetStat(Health, Current)` d'un cadavre ne
    mesurerait rien. On joue jusqu'a `MAX_TOURS` echanges et on s'arrete des qu'un porteur a
    change de PV : la mesure porte sur la RELATION `delta == f(hp COURANT)`, pas sur une valeur
    de PV choisie d'avance (que l'IA ne nous doit pas).

    ⚠ `900000 % 20 == 0` : ce montage exerce AUSSI le quirk Fix64 au depart
    (`15 % x 900000 = 135000` exact, natif `134999`)."""
    ko = 0
    MAX_TOURS = 4
    pct = int(ability_var(HYPERMORPH, "healthPct", is_constant=True) or 0)
    rid, state_file = _build(
        sid, 900000,
        extra=["--place", "%s:3,5" % NPC, "--place", "%s:2,5" % SUMMON,
               "--place", "ultraTitus:1,1", "--a-place", "ultraTitus:3,6"])
    try:
        dv, ob, sn, st = _capture(sid, rid)
        live = _carriers(sn)
        if not live:
            print("[D] KO : aucun porteur Aberrant dans le snapshot")
            return 1
        for _ in range(MAX_TOURS):
            _duel(state_file, "act", "endturn")
            _duel(state_file, "aiturn")
            dv2, ob2, sn2, st2 = _capture(sid, rid)
            live2 = _carriers(sn2)
            blesse = [u for u in live2 if u in live and live2[u][0] != live[u][0]]
            if blesse:
                break
        if not blesse:
            print("[D] NON CONFRONTE : aucun porteur n'a change de PV en %d tours adverses "
                  "(PV lus : %s -> %s)" % (MAX_TOURS, sorted(live.items()), sorted(live2.items())))
            return 1
        for uid in sorted(blesse):
            hp, delta = live2[uid]
            want = hypermorph_extra_damage(hp, pct)
            got = _port_attr(st2, uid)
            tag = "OK " if (delta == want and got == want) else "KO "
            ko |= 0 if tag == "OK " else 1
            print("[D] %s u%-4d hp %d -> %d  natif=%-5d port=%-5d mirror=%-5d"
                  % (tag, uid, live[uid][0], hp, delta, got, want))
    finally:
        _duel(state_file, "dispose")
    return ko


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="volet A seul (aucune session requise)")
    args = ap.parse_args()
    ko = volet_a()
    if args.offline:
        return ko
    sid = _resolve_session()
    print("[probe_1048] session %s" % sid)
    ko |= volet_bc(sid)
    ko |= volet_d(sid)
    print("[probe_1048] %s" % ("KO" if ko else "OK"))
    return ko


if __name__ == "__main__":
    raise SystemExit(main())
