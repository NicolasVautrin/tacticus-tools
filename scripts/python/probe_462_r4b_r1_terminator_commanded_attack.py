#!/usr/bin/env python
"""probe #462-r4b-r1 -- la reduction `TerminatorArmour` sur l'attaque COMMANDEE par `UseActiveAbility`.

RESIDU laisse par #462-r4b (`docs/rl/case-462-r4b-pose-vs-etat-final.md` §7), qu'AUCUN test
n'assertionnait :

    blackAbaddon (trait TerminatorArmour)   PORT 10038 -> 2308   (7730 infliges)
                                            LIVE 10038 -> 7442   (2596 infliges)   facteur 2,98

Ce probe DECOMPOSE PAR ETAGE l'attaque libre de la chaine `ExemplarOfHate` (feuille
`UseActiveAbility` -> `AttackDamageOperation.execute`), sur le MEME etat que le cast natif :

  etage 1 -- l'effet 1147 `TerminatorArmour_ReduceDmg` est-il DANS l'etat charge, et ACTIF ?
  etage 2 -- que rend `defender_modifiers` PENDANT l'attaque libre (%-list, multiplicateur,
             additifs, `is_melee`, `damage_profile`) ? On instrumente le foyer, on ne devine pas.
  etage 3 -- le ledger PAR COUP des deux cotes (`per_hit` du port / tag `Amount` des events natifs)
             + le total et le delta de PV.

Le bras `control` (`blackPossession`, SANS le trait) est le temoin : #462-r4b a mesure que les deux
cotes y infligent le meme degat, donc l'ecart est porte par le TRAIT et non par le montage.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_462_r4b_r1_terminator_commanded_attack.py [immune|control|both]

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import json
import sys

import probe_112_darkangels as PR
import probe_n5_chain_after_refused_addeffect as N5
import rl_collect_batch as R

EXEMPLAR = 1140
TERMINATOR_REDUCE = 1147
TERMINATOR_VISUAL = 1375


def _snapshot(sid, rid):
    from engine.entities.pathfinding.board import Board
    bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym")
    dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40)
    cs = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
    return board, dv, ob, cs


def _seeded_state(sid, rid, board, dv, ob, cs):
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    rng = PR.rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    st = load_state(dv, ob, cs, board=board)
    r = IntBasedMersenneTwister()
    r.mt = list(rng["mt"])
    r.mti = rng["mti"]
    st.rng = r
    return st


def _hp(state, uid):
    from engine.runner.components import HealthComponent
    e = state.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return None if hc is None else hc.hp


def _mods_repr(m):
    """Vue ASCII des DEUX canaux de `DamageModifiers` (#462-r4a) : la LISTE `@0x18` et le
    `Multiplier@0x30`, plus les additifs/soustractions plates."""
    if m is None:
        return "None"
    out = {}
    for k in ("pct_list", "pct_list_defender", "multiplicative", "multiplicative_defender",
              "additive", "flat_reductions", "extra_pierce", "override"):
        v = getattr(m, k, None)
        if v:
            out[k] = v if not isinstance(v, list) else [str(x) for x in v]
    return json.dumps(out, default=str)


def instrument_defender_modifiers():
    """ETAGE 2 -- enregistre CHAQUE appel du foyer `defender_modifiers` (le builder partage
    `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`).
    Rend `(calls, restore)`."""
    from engine.runner import damage_model as DM
    calls = []
    orig = DM.defender_modifiers

    def _wrapped(state, unit_id, hp, is_melee=None, damage_profile=None,
                 attacker_id=None, is_normal_attack=None):
        mods, active = orig(state, unit_id, hp, is_melee=is_melee, damage_profile=damage_profile,
                            attacker_id=attacker_id, is_normal_attack=is_normal_attack)
        calls.append({"unit": unit_id, "is_melee": is_melee, "profile": damage_profile,
                      "attacker": attacker_id, "is_normal_attack": is_normal_attack,
                      "active": [getattr(e, "name", None) for e in (active or [])],
                      "mods": _mods_repr(mods)})
        return mods, active

    DM.defender_modifiers = _wrapped
    # Les modules d'operation importent le symbole DIRECTEMENT (`from ...damage_model import
    # defender_modifiers`) : re-lier le module seul ne suffirait pas, on patche chaque porteur.
    import engine.runner.operations.damage_ops.ability as _AB
    import engine.runner.operations.damage_ops.normal as _NO
    import engine.runner.operations.damage_ops.normal_like as _NL
    holders = [_NO, _NL, _AB]
    prev = [(h, getattr(h, "defender_modifiers", None)) for h in holders]
    for h in holders:
        if getattr(h, "defender_modifiers", None) is not None:
            h.defender_modifiers = _wrapped

    def restore():
        DM.defender_modifiers = orig
        for h, p in prev:
            if p is not None:
                h.defender_modifiers = p

    return calls, restore


def instrument_bounds():
    """ETAGE 2bis -- enregistre les DEUX etages que `_reduced_bounds` enchaine :
    `apply_pierce_and_modifiers(valeur, pierce, armure, mods_attaquant)` (percage + les DEUX
    %-list + les DEUX `Multiplier@0x30`) puis `apply_all_modifiers(., def_mods)` (ce qui RESTE
    dans l'accumulateur DEFENSEUR apres `_apply_defender_flat_reductions`). C'est le couple qui
    dit OU un terme atterrit. Rend `(rows, restore)`."""
    import engine.runner.operations.damage_ops.normal as _NO
    rows = []
    o_pierce, o_all = _NO.apply_pierce_and_modifiers, _NO.apply_all_modifiers
    pending = {}

    def _pierce(value, pierce_pct=100, armor=0, mods=None, hit_mult=1, attacker_additive_pre=False):
        out = o_pierce(value, pierce_pct, armor, mods, hit_mult, attacker_additive_pre)
        pending.clear()
        pending.update({"value": value, "pierce": pierce_pct, "armor": armor,
                        "att_additive": getattr(mods, "additive", None),
                        "att_pct": [str(x) for x in (getattr(mods, "pct_list", None) or [])],
                        "def_pct_moved": [str(x) for x in (getattr(mods, "pct_list_defender", None) or [])],
                        "att_mult": getattr(mods, "multiplicative", None),
                        "def_mult_moved": getattr(mods, "multiplicative_defender", None),
                        "att_details": [(e.kind, e.value, e.owner_is_caster)
                                        for e in (getattr(mods, "details", None) or [])],
                        "after_pierce_mods": out})
        return out

    def _all(value, mods, round_materialize=False):
        out = o_all(value, mods, round_materialize)
        row = dict(pending)
        row.update({"def_additive_left": getattr(mods, "additive", None),
                    "def_pct_left": [str(x) for x in (getattr(mods, "pct_list", None) or [])],
                    "def_details": [(e.kind, e.value, e.owner_is_caster)
                                    for e in (getattr(mods, "details", None) or [])],
                    "final": out})
        rows.append(row)
        return out

    _NO.apply_pierce_and_modifiers = _pierce
    _NO.apply_all_modifiers = _all

    def restore():
        _NO.apply_pierce_and_modifiers = o_pierce
        _NO.apply_all_modifiers = o_all

    return rows, restore


def _live_hits(action, tgt):
    """Ledger natif PAR COUP : tag `Amount` des events de l'action, filtre sur la cible."""
    hits = []
    for ev in (action.get("events") or []):
        td = ev.get("tags")
        td = json.loads(td) if isinstance(td, str) else (td or {})
        if "Amount" in td and int(td.get("Target_Id", td.get("TargetId", tgt)) or tgt) == int(tgt):
            hits.append(int(td["Amount"]))
    return hits


def _no_merge_variant(mods, def_mods) -> None:
    """CONTRE-MODELE ECRIT = l'etat d'`origin/master` AVANT #462-r4b-r1 : tout le foyer SAUF le
    transfert de l'additif defenseur. L'additif reste alors dans `def_mods` et `apply_all_modifiers`
    l'ajoute APRES les %-list et les deux `Multiplier@0x30`. Ce n'est pas une caricature : c'est
    exactement le corps precedent de `_apply_defender_flat_reductions`."""
    if def_mods.flat_reductions:
        mods.additive -= sum(def_mods.flat_reductions)
    if def_mods.pct_list:
        mods.pct_list_defender.extend(def_mods.pct_list)
        def_mods.pct_list = []
    if def_mods.multiplicative != 1.0:
        mods.multiplicative_defender *= def_mods.multiplicative
        def_mods.multiplicative = 1.0
    if def_mods.extra_pierce:
        mods.extra_pierce += def_mods.extra_pierce


def measure(sid, victim_visual, layout, with_variant: bool = False) -> dict:
    """MONTAGE NOMME : un runner, la chaine `ExemplarOfHate` jouee cote PORT sur l'etat CALE SUR LE
    RNG DU RUNNER, puis le MEME cast cote NATIF. Rend le ledger PAR COUP des deux cotes.

    `with_variant=True` rejoue AUSSI la chaine sur un SECOND etat charge a l'identique, avec le
    contre-modele `_no_merge_variant` en place -- c'est ce qui rend la mesure auto-discriminante :
    sans lui, un port qui n'exercerait plus du tout l'axe passerait pour juste."""
    from engine.runner.abilities.darkangels import ExemplarOfHateAbility
    from engine.runner.components import unit_state_for_effects
    from engine.runner.operations.damage import AttackDamageOperation
    rid = N5._build(sid, N5.P_UNITS, N5.A_UNITS, anchor=layout[victim_visual],
                    occupied=layout.values())
    try:
        board, dv, ob, cs = _snapshot(sid, rid)
        bv = PR.units_by_visual(dv)
        if "darkaAsmodai" not in bv or victim_visual not in bv:
            return {"skip": "roster incomplet: %s" % sorted(bv)}
        caster, tgt = bv["darkaAsmodai"]["id"], bv[victim_visual]["id"]
        import hexgeo
        pos = PR.positions(dv)
        if hexgeo.distance(pos[caster], pos[tgt]) > 1:
            return {"skip": "caster non adjacent -> l'attaquant elu n'est pas garanti"}
        if tgt not in PR.legal_from_here(sid, rid, caster, EXEMPLAR):
            return {"skip": "cible %s non legale depuis la position courante" % victim_visual}

        st = _seeded_state(sid, rid, board, dv, ob, cs)
        us = unit_state_for_effects(st, tgt)
        pre_active = sorted(e.effect_type for e in st.effects.active_effects(tgt, us))
        calls, restore = instrument_defender_modifiers()
        rows, restore_b = instrument_bounds()
        try:
            php0 = _hp(st, tgt)
            port = ExemplarOfHateAbility().execute_behaviour(st, caster, tgt)
            php1 = _hp(st, tgt)
        finally:
            restore_b()
            restore()

        variant = None
        if with_variant:
            st2 = _seeded_state(sid, rid, board, dv, ob, cs)
            _orig = AttackDamageOperation._apply_defender_flat_reductions
            AttackDamageOperation._apply_defender_flat_reductions = staticmethod(_no_merge_variant)
            try:
                v = ExemplarOfHateAbility().execute_behaviour(st2, caster, tgt)
                variant = ((v or {}).get("attack") or {}).get("per_hit")
            finally:
                AttackDamageOperation._apply_defender_flat_reductions = _orig

        hp0 = PR.hp_of(sid, rid)
        res = PR.act(sid, rid, {"kind": "ability", "casterId": caster, "targetId": tgt,
                                "abilityType": EXEMPLAR})
        if not res.get("ok"):
            return {"skip": "cast live KO: %s" % str(res)[:200]}
        hp1 = PR.hp_of(sid, rid)
        atk = (port or {}).get("attack") or {}
        return {
            "caster": caster, "target": tgt,
            "pre_active": pre_active,
            "port_per_hit": list(atk.get("per_hit") or []),
            "port_total": atk.get("total"), "port_hits": atk.get("hits"),
            "port_profile": atk.get("profile"), "port_override": port.get("attack_override"),
            "port_hp": (php0, php1), "port_delta": (php0 or 0) - (php1 or 0),
            "variant_per_hit": variant,
            "live_per_hit": _live_hits(res, tgt),
            "live_hp": (hp0.get(tgt), hp1.get(tgt)),
            "live_delta": (hp0.get(tgt) or (0,))[0] - (hp1.get(tgt) or (0,))[0],
            "live_groups": [e.get("source") for e in (res.get("events") or [])
                            if e.get("kind") == "group"],
            "def_mods_calls": calls, "bounds_rows": rows,
            "live_effects_post": PR.eff_names(
                PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 60), tgt),
        }
    finally:
        PR.dispose(sid, rid)


def measure_followup(sid, victim_visual=None) -> dict:
    """GENERALISATION d'ACCORD -- MEME foyer, TROIS variables changees d'un coup :

      * le VECTEUR : plus `UseActiveAbility` mais l'attaque NORMALE ordinaire
        (`AttackUnitMessage` -> `IdunBattle.Operations.AttackDamageOperation$$Execute`) ;
      * l'ATTAQUANT : `darkaHellblaster`, AMENE AU CONTACT (son arme melee `Physical` 1 coup) --
        il ne porte PAS `FearedInterrogator_Owner`, donc l'additif ATTAQUANT est NUL et l'additif
        DEFENSEUR est SEUL en jeu ;
      * le REGIME : la chaine a deja CONSOMME `TerminatorArmour_ReduceDmg` (#432), donc aucune
        `%-list` defenseur -- ce qui reste est l'axe ARMURE a nu.

    ⚠ CE BRAS N'EST PAS DISCRIMINANT, ET C'EST LA MESURE QUI LE DIT (port == contre-modele == natif
    == 2746). Raison, exacte : le plancher de `GetBaseDamageWithFixedPiercedArmor` est
    `max(d x pierce%, d - armure)` ; sur la branche ARMURE il est AFFINE de pente 1, donc
    `P(v + A) = P(v) + A` et les deux placements COINCIDENT. Le profil `Physical` du Hellblaster a un
    perçage tres bas et l'armure de `blackAbaddon` (2510) ne suffit pas a faire gagner la branche
    PERCAGE. C'est exactement pourquoi le residu ne s'etait vu que sur un bras a `%-list` : il faut
    OU une reduction defenseur, OU la branche PERCAGE gagnante, pour que le placement se voie.
    Ce bras vaut donc comme datapoint d'ACCORD sur un autre vecteur, PAS comme garde du correctif.

    Sequence : cast `ExemplarOfHate` (qui POSE `ExemplarOfHate_Target` sur la cible et consomme
    l'armure), puis on DEPLACE le Hellblaster au contact si besoin, on capture l'etat + le RNG, on
    rejoue l'attaque cote PORT, puis on la joue cote NATIF.

    ROSTER ADVERSE REDUIT A LA SEULE VICTIME. Mesure de la geometrie du montage a deux ennemis :
    la tuile de `blackAbaddon` (6,8) sur `MC1_67`/112112 n'a que DEUX voisins MARCHABLES -- (5,8) et
    (6,7) -- et `blackPossession` occupe le second. Aucune tuile LEGALE (`GetMovableTilesFor` natif)
    n'amene alors le Hellblaster au contact : sa plus proche est a d=2. Retirer le second ennemi
    LIBERE (6,7) et les deux unites joueur se deploient a d=1. On CHOISIT la configuration au lieu
    de la subir -- ce n'est pas « bloque par la geometrie de spawn »."""
    import hexgeo
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.runner import Runner
    victim_visual = victim_visual or N5.IMMUNE_VICTIM
    a_units = [victim_visual]
    layout = N5.enemy_layout(sid, a_units=a_units)
    rid = N5._build(sid, N5.P_UNITS, a_units, anchor=layout[victim_visual],
                    occupied=layout.values())
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        bv = PR.units_by_visual(dv)
        for need in ("darkaAsmodai", "darkaHellblaster", victim_visual):
            if need not in bv:
                return {"skip": "roster incomplet: %s" % sorted(bv)}
        caster, hell, tgt = (bv["darkaAsmodai"]["id"], bv["darkaHellblaster"]["id"],
                             bv[victim_visual]["id"])
        pos = PR.positions(dv)
        if hexgeo.distance(pos[caster], pos[tgt]) > 1:
            return {"skip": "caster non adjacent -> la chaine ne porte pas son attaque"}
        if tgt not in PR.legal_from_here(sid, rid, caster, EXEMPLAR):
            return {"skip": "cible non legale depuis la position courante"}
        if not PR.cast(sid, rid, caster, tgt, EXEMPLAR).get("ok"):
            return {"skip": "cast ExemplarOfHate KO"}

        # Le Hellblaster AU CONTACT : son arme melee (`Physical`, 1 coup) est la seule qui satisfasse
        # le gate `IsMeleeAttack` d'`ExemplarOfHate_Target`. On DEPLACE, on ne subit pas la geometrie.
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        pos = PR.positions(dv)
        if hexgeo.distance(pos[hell], pos[tgt]) > 1:
            # Tuiles LEGALES pour CETTE unite (`GetMovableTilesFor` natif) -- jamais l'anneau
            # geometrique brut, qui inclut des tuiles non marchables ou hors portee de mouvement.
            mv = PR.rpc(sid, "aiMovableTiles", {"runnerId": rid}, 90)
            cands = []
            for u in (mv.get("units") or []):
                if int(u.get("unitId") or u.get("id") or -1) != int(hell):
                    continue
                for t in (u.get("tiles") or []):
                    c, r_ = t.get("col"), t.get("row")
                    if c is None or r_ is None:
                        continue
                    cands.append((hexgeo.distance((c, r_), pos[tgt]), (c, r_)))
            cands.sort()
            moved = False
            for _d, (col, row) in [c for c in cands if c[0] == 1]:
                r = PR.act(sid, rid, {"kind": "move", "unitId": int(hell),
                                      "to": {"col": int(col), "row": int(row)}})
                if r.get("ok") and r.get("mutated"):
                    moved = True
                    break
            if not moved:
                return {"skip": "aucune tuile legale au contact pour le Hellblaster (%s)"
                                % (cands[:6],)}
            dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            pos = PR.positions(dv)
            if hexgeo.distance(pos[hell], pos[tgt]) > 1:
                return {"skip": "Hellblaster toujours hors contact"}

        normal_id = None
        for a in ((next((u for u in (dv.get("units") or []) if u.get("id") == hell), {})
                   ).get("abilities") or []):
            if a.get("kind") == "normal":
                normal_id = int(a.get("id"))
        if normal_id is None:
            return {"skip": "attaque normale du Hellblaster introuvable"}

        bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        from engine.entities.pathfinding.board import Board
        board = Board(bg["tiles"], adjacency="native_sym")
        ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        cs = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)

        def _replay(patch=None):
            st = _seeded_state(sid, rid, board, dv, ob, cs)
            saved = AttackDamageOperation._apply_defender_flat_reductions
            if patch is not None:
                AttackDamageOperation._apply_defender_flat_reductions = staticmethod(patch)
            try:
                rn = Runner(st).install_default_handlers(20)
                rn.apply(AttackUnitMessage(int(hell), int(tgt)))
                return dict(rn.damage_handler.last or {}), st
            finally:
                AttackDamageOperation._apply_defender_flat_reductions = saved

        calls, restore = instrument_defender_modifiers()
        try:
            last, _st = _replay()
        finally:
            restore()
        variant, _ = _replay(_no_merge_variant)

        hp0 = PR.hp_of(sid, rid)
        res = PR.act(sid, rid, {"kind": "ability", "casterId": hell, "targetId": tgt,
                                "abilityType": normal_id})
        if not res.get("ok"):
            return {"skip": "attaque normale live KO: %s" % str(res)[:200]}
        hp1 = PR.hp_of(sid, rid)
        return {"attacker": hell, "target": tgt,
                "port_per_hit": list(last.get("per_hit") or []),
                "port_total": last.get("total"), "port_profile": last.get("profile"),
                "variant_per_hit": list(variant.get("per_hit") or []),
                "live_per_hit": _live_hits(res, tgt),
                "live_delta": (hp0.get(tgt) or (0,))[0] - (hp1.get(tgt) or (0,))[0],
                "def_mods_calls": calls}
    finally:
        PR.dispose(sid, rid)


def run(sid, victim_visual, layout):
    m = measure(sid, victim_visual, layout, with_variant=True)
    print("[%s] %s" % (victim_visual, m.get("skip") or "cible u%s (caster u%s)"
                       % (m["target"], m["caster"])))
    if m.get("skip"):
        return
    print("  [1] effets ACTIFS cible au chargement : %s" % (m["pre_active"],))
    for row in m["bounds_rows"]:
        print("  [2bis] %s" % json.dumps(row, default=str))
    for c in m["def_mods_calls"]:
        print("  [2] defender_modifiers u%s melee=%s profil=%s att=%s normal=%s"
              % (c["unit"], c["is_melee"], c["profile"], c["attacker"], c["is_normal_attack"]))
        print("      active=%s" % (c["active"],))
        print("      mods=%s" % (c["mods"],))
    print("  [3] PORT hp %s -> %s (inflige %s) total=%s hits=%s profil=%s override=%s"
          % (m["port_hp"][0], m["port_hp"][1], m["port_delta"], m["port_total"],
             m["port_hits"], m["port_profile"], m["port_override"]))
    print("      PORT per_hit    = %s" % (m["port_per_hit"],))
    print("      VARIANT per_hit = %s   (contre-modele POST-%%list)" % (m["variant_per_hit"],))
    print("      LIVE per_hit    = %s" % (m["live_per_hit"],))
    print("  [3] LIVE hp %s -> %s (inflige %s)"
          % (m["live_hp"][0], m["live_hp"][1], m["live_delta"]))
    print("      LIVE groupes=%s" % (m["live_groups"],))
    print("      LIVE effets cible POST=%s" % (m["live_effects_post"],))


def run_followup(sid, _layout=None):
    m = measure_followup(sid)
    if m.get("skip"):
        print("[followup] %s" % m["skip"])
        return
    print("[followup] u%s (Hellblaster, melee) -> u%s   profil=%s"
          % (m["attacker"], m["target"], m["port_profile"]))
    for c in m["def_mods_calls"]:
        print("  [2] defender_modifiers u%s melee=%s profil=%s att=%s  active=%s"
              % (c["unit"], c["is_melee"], c["profile"], c["attacker"], c["active"]))
        print("      mods=%s" % (c["mods"],))
    print("  PORT per_hit    = %s (total %s)" % (m["port_per_hit"], m["port_total"]))
    print("  VARIANT per_hit = %s   (contre-modele POST-%%list)" % (m["variant_per_hit"],))
    print("  LIVE per_hit    = %s (delta PV %s)" % (m["live_per_hit"], m["live_delta"]))


def main():
    sid = R._resolve_session()
    only = sys.argv[1] if len(sys.argv) > 1 else "immune"
    try:
        layout = N5.enemy_layout(sid)
        if only in ("immune", "both", "all"):
            run(sid, N5.IMMUNE_VICTIM, layout)
        if only in ("control", "both", "all"):
            run(sid, N5.CONTROL_VICTIM, layout)
        if only in ("followup", "all"):
            run_followup(sid, layout)
    finally:
        for rid in list(PR._rids):
            PR.dispose(sid, rid)


if __name__ == "__main__":
    main()
