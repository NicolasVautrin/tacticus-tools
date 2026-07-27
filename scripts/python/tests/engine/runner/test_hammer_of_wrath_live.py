"""HammerOfWrath (actif 1153, `bloodIntercessor` «Mataneo», Blood Angels) PORT -> arbre DSL, LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.HammerOfWrathAbility$$ExecuteBehaviour` (DECOMPILE,
mirror 1:1, cf. `engine/runner/abilities/bloodangels.py::hammer_of_wrath_tree`) =
    op_and( op_and( AddEffect(0x416 = Infiltrate_UnitEffect, Self, duree = Direct(1) TOUR),
                    MoveUnit(caster, First(SortTilesByUtility(Filter(CanAddUnit(AdjacentTiles(target)),
                             NOT(AmountIsGreater(MinDistance(It, CasterTiles), range))), caster,
                             UtilityDefinition(7 = Tile)), 1)) ),
            If( IsAlive(caster),
                AtomicGroup( AttackWithAbilityDamage(target, GetDamage,  Power,    nrOfHits)
                           & AttackWithAbilityDamage(GetAdjacentTargets, GetDamage2, Physical,
                                                     nrOfHits_2) ) ) )
    GetDamage(2)  = ConditionalAmount( HasEffect(Self, 0x534), Multiply(MinMaxDamage(2), 2),
                                       MinMaxDamage(2) )

DEUX CAS DISCRIMINANTS (deux runners, meme seed/board/roster ; seule variable = les PV de Mataneo) :
  A -- PV pleins   : l'owner-effect 1332 `HammerOfWrath_ConditionalDamage` est INACTIF
                     (`HealthPctIsBelowOrEqual(Self, healthPct = 50)`) -> degat SIMPLE.
  B -- ~33 % PV    : 1332 ACTIF -> degat DOUBLE (les DEUX bornes).
Chaque cast porte DEUX volets aux nombres DIFFERENTS (2x Power sur la cible / 1x Physical sur chaque
ennemi adjacent A LA CIBLE). Tous les coups NON CLAMPES par la mort doivent etre bit-exacts vs live.

Verifie AUSSI la tuile de CHARGE : `SortTilesByUtility(UtilityDefinition(7 = Tile))` est mirrore par
le composite Tile(7) porte (`engine/utilities/tile.py`) -- sur MC1_67 c'est la feuille `Elevation` qui
tranche, et le natif charge bien sur la tuile la PLUS ELEVEE (pas la plus proche).

Lit l'etat LIVE (aucune valeur/tuile hardcodee), dispose SES runners. ASCII only.
"""
from __future__ import annotations

import hexgeo
import pytest

import probe_112_darkangels as PR
import probe_226_hammer_foehammer as P
import rl_collect_batch as R

from engine.runner.abilities.bloodangels import HammerOfWrathAbility

SEED = 226226
P_UNITS = ["bloodIntercessor"]
A_UNITS = ["necroOverlord", "necroWarden", "necroWarden", "necroWarden"]
MATANEO_MAX_HP = 9035            # `Health` du template BC (le RATIO courant/max est ce qui compte)
CONDITIONAL_DAMAGE = 1332        # HammerOfWrath_ConditionalDamage (owner-effect, ActiveCondition HP%)


def _clean_prefix(live: list, hp: int) -> int:
    """Nb de coups LIVE NON CLAMPES par la mort de la cible : le tag `Amount` est le degat APPLIQUE
    (borne par les PV restants) alors que le `per_hit` offline est le degat DEMANDE. Meme convention
    d'exclusion que `test_great_frost_axe_live`."""
    run, n = 0, 0
    for a in live:
        if hp is not None and run + a >= hp:
            break
        run += a
        n += 1
    return n


def _run_case(sid, rpc, hp_frac, label):
    """Monte un runner, laisse Mataneo ATTERRIR (TeleportStrike : les passives -- dont l'owner-effect
    1332 -- ne sont initialisees qu'a l'atterrissage), cast LIVE + replay OFFLINE. Rend un dict."""
    hp = None
    if hp_frac is not None:
        hp = {"bloodIntercessor": (MATANEO_MAX_HP, int(MATANEO_MAX_HP * hp_frac), False)}
    rid = P.build_custom(sid, P_UNITS, A_UNITS, SEED, hp_by_visual=hp)
    try:
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        me = P._my_player(dv)
        P._next_turn(sid, rid, me)                      # atterrissage deep-strike
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        bv = PR.units_by_visual(dv)
        mat = bv["bloodIntercessor"]["id"]
        legal = PR.legal_from_here(sid, rid, mat, P.HAMMER_OF_WRATH)
        if not legal:
            pytest.skip(f"[{label}] aucune cible legale depuis la position courante")
        pos = PR.positions(dv)

        def n_adj(t):
            return sum(1 for u in (dv.get("units") or [])
                       if u["id"] != t and not u.get("ctrl") and pos.get(u["id"])
                       and hexgeo.distance(pos[t], pos[u["id"]]) == 1)
        tgt = max(legal, key=n_adj)

        dec, ob, snap, bg, rngd = P.capture(sid, rid)
        st = P.offline_state(dec, ob, snap, bg, rngd)
        hp_by_id = {u["squadId"]: u.get("hp") for u in (ob.get("units") or [])}
        pre_1332 = bool(P.eff_of(dec, mat, CONDITIONAL_DAMAGE))
        r = PR.cast(sid, rid, mat, tgt, P.HAMMER_OF_WRATH)
        live = {k: [int(h["amt"]) for h in v]
                for k, v in P.live_hits(r.get("events"), P.HAMMER_OF_WRATH).items()}
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        live_pos = PR.positions(dv2).get(mat)
        res = HammerOfWrathAbility().execute_behaviour(st, mat, tgt)
        off = {tgt: [int(x) for x in (((res or {}).get("main_attack") or {}).get("per_hit") or [])]}
        for s in ((res or {}).get("splash") or []):
            off[s["target"]] = [int(x) for x in ((s.get("attack") or {}).get("per_hit") or [])]
        return {"rid": rid, "caster": mat, "target": tgt, "live": live, "off": off,
                "res": res, "live_pos": live_pos, "hp": hp_by_id, "pre_1332": pre_1332}
    finally:
        PR.dispose(sid, rid)


def _assert_bit_exact(case, label):
    live, off, hp = case["live"], case["off"], case["hp"]
    assert live, f"[{label}] aucun coup LIVE tagge Active_Ability_Type=1153"
    assert set(off) == set(live), \
        (f"[{label}] cibles touchees differentes : off={sorted(off)} live={sorted(live)} "
         f"(selecteur `Enemies(caster, AdjacentUnits(target, 1))`)")
    total_clean = 0
    for t, lh in live.items():
        n = _clean_prefix(lh, hp.get(t))
        assert len(off[t]) == len(lh), \
            f"[{label}] u{t} : {len(off[t])} coups port != {len(lh)} live"
        for i in range(n):
            assert off[t][i] == lh[i], \
                (f"[{label}] u{t} coup{i} NON bit-exact : live={lh[i]} off={off[t][i]} "
                 f"(live_all={lh} off_all={off[t]})")
        total_clean += n
    assert total_clean >= 2, \
        f"[{label}] moins de 2 coups PROPRES (non clampes) : rien de discriminant ({live}, hp={hp})"
    return total_clean


def test_hammer_of_wrath_live(live_session, rpc):
    """A (PV pleins, pas de doublement) et B (~33 % PV, effet 1332 ACTIF -> doublement) : les deux
    bit-exacts vs live sur tous les coups propres, avec des nombres DIFFERENTS entre A et B.
    Verifie aussi la tuile de charge (mirror `SortTilesByUtility(Tile)`) et le gate `HasEffect(1332)`."""
    sid = R._resolve_session()
    a = _run_case(sid, rpc, None, "A pv-pleins")
    _assert_bit_exact(a, "A pv-pleins")
    assert a["res"].get("doubled") is False, \
        f"[A] l'effet 1332 ne devrait PAS etre actif a PV pleins (port doubled={a['res'].get('doubled')})"
    assert a["pre_1332"] is False, \
        "[A] 1332 expose ACTIF par decisionView a PV pleins -- l'ActiveCondition HP%<=healthPct est fausse"
    # tuile de CHARGE : le port doit atterrir SUR la tuile ou le natif a mis le caster
    assert a["res"].get("moved_to") == a["live_pos"], \
        (f"[A] tuile de charge divergente : port={a['res'].get('moved_to')} live={a['live_pos']} "
         f"-- collapse `SortTilesByUtility(UtilityDefinition(7 = Tile))`")

    b = _run_case(sid, rpc, 0.33, "B 33pct")
    _assert_bit_exact(b, "B 33pct")
    assert b["pre_1332"] is True, \
        "[B] 1332 ABSENT de decisionView a 33 % PV -- l'owner-effect / son ActiveCondition sont faux"
    assert b["res"].get("doubled") is True, \
        f"[B] le port ne double pas a 33 % PV (doubled={b['res'].get('doubled')})"
    assert b["res"].get("moved_to") == b["live_pos"], \
        f"[B] tuile de charge divergente : port={b['res'].get('moved_to')} live={b['live_pos']}"
    # DISCRIMINANT : le volet principal doit rendre des nombres DIFFERENTS entre A et B
    assert b["live"][b["target"]][0] != a["live"][a["target"]][0], \
        (f"[A/B] meme 1er coup ({a['live'][a['target']][0]}) : le doublement n'est pas exerce, "
         f"l'egalite ne discrimine rien")
