"""Foehammer (actif 1097, `spaceRockfist` «Arjac», Space Wolves) PORT -> arbre DSL, confronte au LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.FoehammerAbility$$ExecuteBehaviour` (DECOMPILE,
mirror 1:1, cf. `engine/runner/abilities/spacewolves.py::foehammer_tree`) =
    op_Addition(
        AddEffect(0x48a = Stunned, AbilityStateReference, Self@0x148, Target@0x178,
                  TurnsFromRounds(1)),
        AttackWithAttackDamage(caster@0x160, target@0x178,
            Sum( MinMaxDamage(minDmg 0xc / maxDmg 0xd),
                 Multiply( Direct(GetVariableForLevel(8 = extraDmg)),
                           Count(GetDeadHeroes) ) ),
            GetDamageProfile = Power, GetNumberConstant(0x2f) = nrOfHits, AbilityOrEffect(1097)) )

avec `FoehammerAbility$$GetDeadHeroes` = `UnitsWithTrait(AllDeadOrResurrectedUnits, 0x10 = Hero)`.

DEUX CAS DISCRIMINANTS, sur la MEME cible et le MEME runner (seule variable = le nb de HEROS morts) :
  A -- 0 heros mort  : degat = MinMaxDamage seul.
  C -- 1 heros mort  : degat = MinMaxDamage + `extraDmg` (le heros sacrifiable `orksNob`, monte a
       100 PV / armure 0, est tue par le cast B intercalaire).
Les deux DOIVENT etre bit-exacts vs live, et DOIVENT differer entre eux (sinon le terme
`extraDmg x Count(deadHeroes)` n'est pas exerce). Mesure de reference (#226, seed 226226, MC1_67) :
A = 365, C = 2142.

Lit l'etat LIVE (aucune valeur/tuile hardcodee), dispose SES runners. ASCII only.
"""
from __future__ import annotations

import pytest

import probe_112_darkangels as PR
import probe_226_hammer_foehammer as P
import rl_collect_batch as R

from engine.runner.abilities.spacewolves import FoehammerAbility

SEED = 226226
P_UNITS = ["spaceRockfist"]
A_UNITS = ["necroOverlord", "necroWarden", "orksNob", "adeptCanoness"]
SACRIFICIAL = "orksNob"          # heros a 100 PV / armure 0 -> tue par UN cast -> +1 heros mort
STUNNED = 1162


def _cast(sid, rid, caster, target):
    """Capture (decisionView/observeBattle/combatSnapshot/boardGraph/dumpRng) -> cast LIVE -> replay
    OFFLINE depuis l'etat capture avec le MEME `state.rng`. Rend (live_hits, off_hits, res)."""
    dec, ob, snap, bg, rngd = P.capture(sid, rid)
    st = P.offline_state(dec, ob, snap, bg, rngd)
    r = PR.cast(sid, rid, caster, target, P.FOEHAMMER)
    lh = [int(h["amt"]) for h in (P.live_hits(r.get("events"), P.FOEHAMMER, target).get(target) or [])]
    res = FoehammerAbility().execute_behaviour(st, caster, target)
    off = [int(x) for x in (((res or {}).get("main_attack") or {}).get("per_hit") or [])]
    return lh, off, res, r


def test_foehammer_live(live_session, rpc):
    """(A) degat bit-exact a 0 heros mort ; (B) le cast tue le heros sacrifiable ; (C) degat
    bit-exact a 1 heros mort ET DIFFERENT de (A) -> le terme `extraDmg x Count(deadHeroes)` est
    exerce et exact. Verifie aussi la pose de `Stunned` (1162) sur la cible."""
    sid = R._resolve_session()
    rid = P.build_custom(sid, P_UNITS, A_UNITS, SEED,
                         hp_by_visual={SACRIFICIAL: (100, 100, True)})
    try:
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        me = P._my_player(dv)
        bv = PR.units_by_visual(dv)
        arjac, sacr = bv["spaceRockfist"]["id"], bv[SACRIFICIAL]["id"]
        legal = PR.legal_from_here(sid, rid, arjac, P.FOEHAMMER)
        others = [t for t in legal if t != sacr]
        if not others or sacr not in legal:
            pytest.skip(f"geometrie: cibles legales insuffisantes ({legal})")
        tgt = others[0]

        # ---- A : 0 heros mort ----
        a_live, a_off, a_res, a_r = _cast(sid, rid, arjac, tgt)
        a_events = a_r.get("events")
        assert a_live, "cast A : aucun coup live (Active_Ability_Type=1097)"
        assert a_res is not None and a_res.get("dead_heroes") == 0, \
            f"cas A cense avoir 0 heros mort, port={a_res}"
        assert a_off == a_live, f"cas A NON bit-exact : live={a_live} off={a_off}"
        # `Stunned` (composite 1162) pose LIVE sur la cible + cote port. On lit les EVENTS du cast
        # (ground truth) et non `decisionView.effects` d'apres-coup, dont la fenetre depend du tick
        # de fin de tour (MESURE : visible sur MC1_67, deja tique sur C3_01).
        assert P.live_effect_posed(a_events, "Stunned", tgt), \
            "aucun groupe d'effet `Stunned` sur la cible dans les events du cast LIVE"
        assert a_res.get("stunned") is True, f"le port n'a pas pose Stunned : {a_res}"

        # ---- B : tuer le heros sacrifiable (generateur de cadavre) ----
        P._next_turn(sid, rid, me)
        _cast(sid, rid, arjac, sacr)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        dead = [u["squadId"] for u in (ob.get("units") or []) if u.get("isDead")]
        assert sacr in dead, f"le heros sacrifiable u{sacr} n'est pas mort (morts={dead})"

        # ---- C : 1 heros mort, MEME cible ----
        P._next_turn(sid, rid, me)
        c_live, c_off, c_res, _ = _cast(sid, rid, arjac, tgt)
        assert c_live, "cast C : aucun coup live"
        assert c_res is not None and c_res.get("dead_heroes") == 1, \
            (f"le selecteur `UnitsWithTrait(AllDeadOrResurrectedUnits, Hero)` ne voit pas le cadavre "
             f"(port={c_res.get('dead_heroes')}) -- les traits d'une unite MORTE viennent du repli "
             f"gameconfig de `_unit_dict`")
        assert c_off == c_live, f"cas C NON bit-exact : live={c_live} off={c_off}"
        # DISCRIMINANT : les deux cas ne doivent pas rendre le meme nombre
        assert c_live != a_live, \
            (f"cas A et C rendent le MEME degat ({a_live}) -- le terme `extraDmg x Count(deadHeroes)` "
             f"n'est pas exerce, l'egalite ne discrimine rien")
    finally:
        PR.dispose(sid, rid)
