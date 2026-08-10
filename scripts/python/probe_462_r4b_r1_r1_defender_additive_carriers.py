#!/usr/bin/env python
"""probe #462-r4b-r1-r1 -- le RAYON DE SOUFFLE de #462-r4b-r1 sur ses DEUX producteurs non confrontes.

#462-r4b-r1 (PR #548) a deplace l'additif DEFENSEUR dans le slot PRE-PERCAGE de l'attaquant
(`AttackDamageOperation._apply_defender_flat_reductions`). RE :
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` resout ses deux accumulateurs par les
slots d'interface `0xd`/`0xe`, lit `Addition@+0x10` de CHACUN et passe `base + Addition(0xd) +
Addition(0xe)` a `CalculateBaseDamageWithAllModifiers` aux DEUX call-sites.

**TROIS producteurs** alimentent `def_mods.additive`, un seul avait ete confronte :

  * `ExemplarOfHate_Target` (1293)      -- CONFRONTE par #548 (blackAbaddon 7730 -> 2596).
  * `Chronometron_ExtraDamage` (1550)   -- CE PROBE, bras `chrono` / `chrono-flat`.
  * `Neuroparasite` (1183/1218)         -- CE PROBE, bras `neuro`.

Un QUATRIEME est entre depuis (PR #836, `HeraldOfTheApocalypse_ExtraDamage` 1027), et il est entre
SANS confrontation -- c'est exactement le regime que le cliquet de
`test_462_r4b_r1_r1_defender_additive_carriers_offline.py` surveille, et qui l'a fait rougir sur
`master`. Bras `herald` (#547-r2).

## Le regime DEGENERE, et pourquoi ce probe force l'armure

Le plancher de `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$
GetDamageWithPiercing` est `max(d x pierce%, d - armure)`. Sur la branche ARMURE il est AFFINE de
pente 1, donc `P(v + A) = P(v) + A` : **les deux placements de l'additif COINCIDENT** et un accord
obtenu la ne prouve RIEN. Il faut la branche PERCAGE gagnante (`armure > d x (1 - pierce/100)`),
d'ou `--armor-target` HAUTE au build. Le bras `chrono-flat` joue EXPRES le regime degenere et
l'assertionne comme BORNE, jamais comme confirmation.

## Montage (gate de confrontabilite)

`necroChronomancer` << Thothmek >> est HORS POOL -> injection catalogue (`case-92` §6). Il caste
`Chronometron` (1226, SELF-CAST) qui pose `Chronometron_ExtraDamage` sur chaque ennemi du disque
rayon 2 ; un ALLIE du Chronomancer frappe ensuite la cible marquee (`AreFriends(caster,
EffectSource(Effect))`). Les unites sont DEPLOYEES autour de la victime (ring placement), jamais
subies.

`tyranNeurothrope` est AU POOL : son passif `Neuroparasite` (triggered 1183) pose l'effet 1218 sur
la cible d'une attaque PSYCHIQUE (`On(9) & OwnerIsCaster & !HasEffect(target,0x4c2) & ... &
CurrentAttackDamageProfilesContain(0xd)`), et l'additif ne joue qu'a la frappe SUIVANTE.

`blackHaarken` << Haarken Worldclaimer >> est AU POOL (verifie sur `rl_duel build --list-pool`,
pas sur `kind == lineup`) : son ACTIVE 1020 `HeraldOfTheApocalypse` est elle-meme une attaque
(`constants` = `damageProfile Piercing, nrOfHits 2, range 2`) et pose l'effet 1027 sur la cible ET
sur l'ennemi DIRECTEMENT DERRIERE. L'effet est une CHARGE A USAGE UNIQUE (`On(9 = Attack) &
get_OwnerIsTarget & IsUnit(caster)` -> `RemoveEffect`), donc le bras `herald` LIT quels ennemis la
portent apres le cast au lieu de le supposer -- la charge de la cible primaire peut avoir ete
consommee par l'attaque du cast lui-meme, celle de l'unite DERRIERE ne le peut pas.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_462_r4b_r1_r1_defender_additive_carriers.py [chrono|chrono-flat|neuro|herald|all]

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile

import hexgeo
import probe_112_darkangels as PR
import probe_462_r4b_r1_terminator_commanded_attack as R1
import rl_collect_batch as R

CHRONOMETRON = 1226                 # ActiveAbilityType
CHRONOMETRON_EXTRA_DAMAGE = 1550    # EffectType 0x60e
NEUROPARASITE_EFFECT = 1218         # EffectType 0x4c2

CHRONO_CARRIER = "necroChronomancer"
CHRONO_ALLY = "darkaHellblaster"
CHRONO_VICTIM = "blackPossession"

HERALD_OF_THE_APOCALYPSE = 1020     # ActiveAbilityType
HERALD_EXTRA_DAMAGE = 1027          # EffectType 0x403

HERALD_CARRIER = "blackHaarken"
HERALD_ALLY = "darkaHellblaster"
HERALD_VICTIMS = ("blackPossession", "blackTerminator")
# `range` de l'active 1020, LU dans `gameconfig.ability("HeraldOfTheApocalypse").constants`.
HERALD_RANGE = 2

NEURO_CARRIER = "tyranNeurothrope"
NEURO_VICTIM = "blackPossession"
# Portee de l'arme PSYCHIQUE du Neurothrope (`gameconfig` weapons[1].Range) -- la SEULE des deux qui
# ouvre le gate `DamageProfileIs(0xd = Psychic)` de l'effet.
NEURO_RANGE = 3

# ARMURE du bras discriminant. La branche PERCAGE l'emporte ssi `armure > d x (1 - pierce/100)` ;
# sur un profil a percage BAS aucune armure du roster n'y suffit -- d'ou une valeur FORCEE tres
# au-dessus de tout degat de base atteignable. Le bras temoin utilise `ARMOR_FLAT`.
ARMOR_PIERCE = 50000
ARMOR_FLAT = 0


def _seed_bc_with(units: list[str]) -> str:
    """Seed BC AUGMENTE des porteurs hors catalogue (`catalog_inject`, cf. `case-92` §6). Ecrit dans
    un tmpdir SYSTEME -- jamais sous `data/` (entrees versionnees) ni sous `scripts/python/` (#455 :
    la banque de cliquets enumere cet arbre en parallele)."""
    import catalog_inject as CI
    out = os.path.join(tempfile.mkdtemp(prefix="tt462r1_"), "seed_bc_augmented.json")
    CI.write_augmented_seed_bc(out, units)
    return out


def _build(sid, p_units, a_units, seed_bc_path=None, armor=None, anchor=None, occupied=(),
           unit_patch=None):
    """Runner isole : seed BC (eventuellement AUGMENTE) + board + rosters explicites + ARMURE forcee
    des a-units. Mirror de `probe_n5_chain_after_refused_addeffect._build`, augmente des trois
    leviers dont ce cas a besoin (`--seed-bc`, `--armor-target` et `--unit-stat` de `rl_duel build`,
    appliques au MEME endroit : sur le BC deja NORMALISE).

    `unit_patch` = `{visualId: {champ: valeur}}`, ecrit VERBATIM dans l'entree `BC.Units` — meme
    geste que `--unit-stat`. Sert a rendre un montage MULTI-TOURS survivable : le tour adverse doit
    pouvoir s'ecouler sans tuer le porteur qu'on mesure (sinon la seconde attaque n'a plus lieu)."""
    seed = R._load_seed_bc(seed_bc_path)
    board_dump = R._load_board_dump(PR.BOARD)
    template, pool, _mow = R._normalize_and_extract_pool(sid, seed, PR.RANK, board_dump=board_dump)
    miss = [u for u in list(p_units) + list(a_units) if u not in pool]
    if miss:
        raise RuntimeError("hors pool rank %d : %s" % (PR.RANK, miss))
    bc = copy.deepcopy(template)
    R._patch_predefined_units(bc, list(a_units))
    if armor is not None:
        a_set = set(a_units)
        for u in bc.get("Units", []):
            if u.get("VisualId") in a_set:
                u["Armor"] = armor
                u["FixedArmor"] = armor
    for vis, fields in (unit_patch or {}).items():
        touched = [u for u in bc.get("Units", []) if u.get("VisualId") == vis]
        if not touched:
            raise RuntimeError("unit_patch: VisualId '%s' absent du catalogue BC.Units" % vis)
        for u in touched:
            u.update(fields)
    if anchor is None:
        pos = PR._contact_placement(bc, len(p_units))
    else:
        pos = _ring_placement(bc, anchor, len(p_units), occupied)
    player_units = [{"unitId": u, "playerId": R.PLAYER_ID_HUMAN,
                     "col": pos[i][0], "row": pos[i][1]} for i, u in enumerate(p_units)]
    resp = R._rpc(sid, "initAndStart",
                  [{"configJson": json.dumps(bc), "seed": PR.SEED, "playerUnits": player_units}],
                  timeout=60)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % (resp.get("error") or resp))
    PR._rids.append(rid)
    return rid


def _ring_placement(bc, anchor, n_units, occupied=()):
    """Tuiles de deploiement joueur les plus PROCHES d'`anchor`, hors tuiles OCCUPEES (une tuile deja
    prise fait SILENCIEUSEMENT echouer le deploiement)."""
    taken = set(tuple(p) for p in occupied)
    board = bc.get("Board") or {}
    w, h = int(board.get("Width") or 0), int(board.get("Height") or 0)
    cands = [(c, r) for c, r in hexgeo.disk(anchor[0], anchor[1], 4)
             if (c, r) not in taken and 0 <= c < w and 0 <= r < h]
    cands.sort(key=lambda p: (hexgeo.distance(p, anchor), p))
    if len(cands) < n_units:
        raise RuntimeError("pas assez de tuiles libres autour de %s" % (anchor,))
    return cands[:n_units]


def _enemy_layout(sid, p_units, a_units, seed_bc_path=None):
    """Build de RECONNAISSANCE : `{visualId: (col,row)}` du camp adverse, place par la BC (spawn
    points) donc REPRODUCTIBLE a seed et BC egales dans le build suivant."""
    rid = _build(sid, p_units, a_units, seed_bc_path=seed_bc_path)
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        pos = PR.positions(dv)
        return {u.get("visualId"): pos[u["id"]] for u in (dv.get("units") or [])
                if not u.get("ctrl")}
    finally:
        PR.dispose(sid, rid)


def _normal_attack_id(dv, uid):
    """Id CONCRET de l'attaque normale de l'unite (`ActiveAbilityComponent.NormalAttackType@0x28`
    est PER-UNIT -- jamais le 17 generique)."""
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), {})
    for a in (u.get("abilities") or []):
        if a.get("kind") == "normal":
            return int(a.get("id"))
    return None


def _move_within(sid, rid, dv, mover, target_pos, want_dist, min_dist=0):
    """DEPLACE `mover` sur une tuile LEGALE (`GetMovableTilesFor` natif via `aiMovableTiles`) a
    distance dans `[min_dist, want_dist]` de `target_pos`. On CHOISIT la configuration, on ne la
    subit pas.

    `min_dist` est le levier qui SELECTIONNE L'ARME : l'attaque normale native choisit l'arme selon
    la distance, et un porteur bi-arme frappe en MELEE des qu'il est au contact. Le Neurothrope a
    une melee `Physical` et une ranged `Psychic` (portee 3) ; son passif `Neuroparasite` est gate
    `CurrentAttackDamageProfilesContain(0xd = Psychic)`, donc l'amener au CONTACT le rend
    structurellement incapable de poser son parasite -- MESURE : premiere passe de ce probe,
    `parasite 1218 NON pose` avec un mover a d=1."""
    pos = PR.positions(dv)
    if min_dist <= hexgeo.distance(pos[mover], target_pos) <= want_dist:
        return True, dv
    mv = PR.rpc(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    cands = []
    for u in (mv.get("units") or []):
        if int(u.get("unitId") or u.get("id") or -1) != int(mover):
            continue
        for t in (u.get("tiles") or []):
            c, r_ = t.get("col"), t.get("row")
            if c is None or r_ is None:
                continue
            d = hexgeo.distance((c, r_), target_pos)
            if min_dist <= d <= want_dist:
                cands.append((d, (c, r_)))
    cands.sort(reverse=bool(min_dist))     # vise la BORNE utile de la plage
    for _d, (col, row) in cands:
        res = PR.act(sid, rid, {"kind": "move", "unitId": int(mover),
                                "to": {"col": int(col), "row": int(row)}})
        if res.get("ok") and res.get("mutated"):
            dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1,
                                              "allAbilities": True}, 90)
            return True, dv
    return False, dv


def _advance_to_my_turn(sid, rid, my_team, max_rounds=3):
    """Rend la main au JOUEUR -- mirror du patron canonique de `rl_duel aiturn` : on pilote sur
    `decisionView.currentPlayer` (`amine`/`aenemy` derives de `my_team`), pas sur le `ctrl` des
    unites.

    MESURE qui a impose ce changement : apres un seul couple `endturn` + `aiPlayByUnit(maxTurns=1)`,
    `ctrl` restait `False` et `toActivate` vide -- `ctrl` ne suffit pas a decider qui a la main, et
    `endturn` peut demander plusieurs passes pour basculer (quirk H19 documente dans `rl_duel`)."""
    amine = 3 if my_team == 1 else 4
    aenemy = 4 if my_team == 1 else 3
    dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if dv.get("currentPlayer") != aenemy:
        for _ in range(max_rounds):
            PR.act(sid, rid, {"kind": "endturn"})
            dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1,
                                              "allAbilities": True}, 90)
            if dv.get("currentPlayer") == aenemy:
                break
        else:
            return False, dv
    PR.rpc(sid, "aiPlayByUnit",
           {"runnerId": rid, "maxTurns": 1, "maxActivations": 9999, "maxPump": 400}, 300)
    dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    return dv.get("currentPlayer") == amine, dv


def _replay_attack(sid, rid, board, dv, ob, cs, attacker, target, patch=None):
    """Rejoue l'attaque NORMALE cote PORT sur l'etat CALE SUR LE RNG DU RUNNER (meme flux des deux
    cotes). `patch` remplace `_apply_defender_flat_reductions` (contre-modele ECRIT)."""
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.runner import Runner
    st = R1._seeded_state(sid, rid, board, dv, ob, cs)
    saved = AttackDamageOperation._apply_defender_flat_reductions
    if patch is not None:
        AttackDamageOperation._apply_defender_flat_reductions = staticmethod(patch)
    try:
        rn = Runner(st).install_default_handlers(20)
        rn.apply(AttackUnitMessage(int(attacker), int(target)))
        return dict(rn.damage_handler.last or {}), st
    finally:
        AttackDamageOperation._apply_defender_flat_reductions = saved


def measure_chronometron(sid, armor: int) -> dict:
    """BRAS `chrono` -- `Chronometron_ExtraDamage` (1550) sur le vecteur COMBAT.

    Sequence : le Chronomancer caste `Chronometron` cote NATIF (l'effet 1550 entre alors dans l'etat
    et sera SEEDE au chargement), l'allie est amene a portee, puis SON attaque normale est rejouee
    cote PORT (arbre courant + contre-modele ECRIT) avant d'etre jouee cote NATIF.

    `armor` HAUTE -> branche PERCAGE (discriminant) ; BASSE -> branche ARMURE (regime DEGENERE, cf.
    l'en-tete : les deux placements coincident et l'accord ne prouve rien)."""
    from engine.runner.components import unit_state_for_effects
    seed_bc = _seed_bc_with([CHRONO_CARRIER])
    p_units = [CHRONO_CARRIER, CHRONO_ALLY]
    a_units = [CHRONO_VICTIM]
    layout = _enemy_layout(sid, p_units, a_units, seed_bc_path=seed_bc)
    if CHRONO_VICTIM not in layout:
        return {"skip": "victime absente du layout adverse: %s" % sorted(layout)}
    rid = _build(sid, p_units, a_units, seed_bc_path=seed_bc, armor=armor,
                 anchor=layout[CHRONO_VICTIM], occupied=layout.values())
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        bv = PR.units_by_visual(dv)
        for need in (CHRONO_CARRIER, CHRONO_ALLY, CHRONO_VICTIM):
            if need not in bv:
                return {"skip": "roster incomplet: %s" % sorted(bv)}
        chrono, ally, tgt = bv[CHRONO_CARRIER]["id"], bv[CHRONO_ALLY]["id"], bv[CHRONO_VICTIM]["id"]
        pos = PR.positions(dv)

        # (1) le Chronomancer a portee : `SurroundingEnemies(casterTile, range=2)`.
        ok, dv = _move_within(sid, rid, dv, chrono, pos[tgt], 2)
        if not ok:
            return {"skip": "aucune tuile legale a d<=2 de la victime pour le Chronomancer"}
        pos = PR.positions(dv)

        # (2) cast NATIF de Chronometron (SELF-CAST : `isSelfCasting=1`).
        res_cast = PR.act(sid, rid, {"kind": "ability", "casterId": chrono, "targetId": chrono,
                                     "abilityType": CHRONOMETRON})
        if not res_cast.get("ok"):
            return {"skip": "cast Chronometron KO: %s" % str(res_cast)[:200]}
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        eff_post = PR.eff_names(dv, tgt)
        types_post = sorted(e.get("effectType") for u in (dv.get("units") or [])
                            if u.get("id") == tgt for e in (u.get("effects") or []))
        if CHRONOMETRON_EXTRA_DAMAGE not in types_post:
            return {"skip": "1550 NON pose sur la victime (effets=%s)" % (types_post,)}

        # (3) l'allie a portee de SON attaque normale.
        pos = PR.positions(dv)
        normal_id = _normal_attack_id(dv, ally)
        if normal_id is None:
            return {"skip": "attaque normale de l'allie introuvable"}
        legal = PR.legal_from_here(sid, rid, ally, normal_id)
        if tgt not in legal:
            ok, dv = _move_within(sid, rid, dv, ally, pos[tgt], 1)
            if not ok:
                return {"skip": "aucune tuile legale au contact pour l'allie"}
            legal = PR.legal_from_here(sid, rid, ally, normal_id)
            if tgt not in legal:
                return {"skip": "cible non legale pour l'attaque normale de l'allie"}

        board, dv, ob, cs = R1._snapshot(sid, rid)
        st_probe = R1._seeded_state(sid, rid, board, dv, ob, cs)
        us = unit_state_for_effects(st_probe, tgt)
        pre_active = sorted(e.effect_type for e in st_probe.effects.active_effects(tgt, us))

        calls, restore = R1.instrument_defender_modifiers()
        rows, restore_b = R1.instrument_bounds()
        try:
            last, _st = _replay_attack(sid, rid, board, dv, ob, cs, ally, tgt)
        finally:
            restore_b()
            restore()
        variant, _ = _replay_attack(sid, rid, board, dv, ob, cs, ally, tgt, R1._no_merge_variant)

        hp0 = PR.hp_of(sid, rid)
        res = PR.act(sid, rid, {"kind": "ability", "casterId": ally, "targetId": tgt,
                                "abilityType": normal_id})
        if not res.get("ok"):
            return {"skip": "attaque normale live KO: %s" % str(res)[:200]}
        hp1 = PR.hp_of(sid, rid)
        return {"armor": armor, "chrono": chrono, "ally": ally, "target": tgt,
                "pre_active": pre_active, "eff_post_cast": eff_post,
                "port_per_hit": list(last.get("per_hit") or []),
                "port_total": last.get("total"), "port_profile": last.get("profile"),
                "variant_per_hit": list(variant.get("per_hit") or []),
                "variant_total": variant.get("total"),
                "live_per_hit": R1._live_hits(res, tgt),
                "live_hp": (hp0.get(tgt), hp1.get(tgt)),
                "live_delta": (hp0.get(tgt) or (0,))[0] - (hp1.get(tgt) or (0,))[0],
                "def_mods_calls": calls, "bounds_rows": rows}
    finally:
        PR.dispose(sid, rid)


def _carriers_of(dv, effect_type: int) -> list:
    """Ids des unites qui portent CET effectType, LUS de `decisionView` -- jamais supposes."""
    return [u["id"] for u in (dv.get("units") or [])
            if any(int(e.get("effectType") or -1) == int(effect_type)
                   for e in (u.get("effects") or []))]


def measure_herald(sid, armor: int = ARMOR_PIERCE) -> dict:
    """BRAS `herald` -- `HeraldOfTheApocalypse_ExtraDamage` (1027) sur le vecteur COMBAT.

    QUATRIEME producteur d'additif DEFENSEUR, entre par la PR #836 sans confrontation (#547-r2).

    Sequence : Haarken est amene a portee 2, caste l'ACTIVE 1020 cote NATIF (elle FRAPPE et pose
    1027 sur la cible + l'ennemi derriere), on LIT qui porte 1027, puis l'attaque normale d'un ALLIE
    sur ce porteur est rejouee cote PORT (arbre courant + contre-modele ECRIT) avant d'etre jouee
    cote NATIF.

    ⚠ La charge est A USAGE UNIQUE et son retrait est declenche par `On(9 = Attack)` : on ne
    presume pas qu'elle survive a l'attaque du cast lui-meme -- on relit `decisionView` et on
    choisit un porteur EFFECTIF. C'est aussi pourquoi le roster adverse compte DEUX unites : celle
    qui est DERRIERE ne peut pas avoir consomme sa charge.

    `armor` HAUTE -> branche PERCAGE (discriminante) ; la lecon du bras `chrono-flat` vaut ici mot
    pour mot -- sur la branche ARMURE le plancher est affine de pente 1 et les deux placements
    COINCIDENT, donc un accord n'y prouverait rien.

    L'effet n'a NI `IsMeleeAttack` NI `DamageProfileIs` NI `AreFriends` (deux conjoints seulement :
    `get_OwnerIsTarget & IsUnit(caster)`), donc aucun gate a ouvrir cote attaquant -- contrairement
    au bras `neuro`, ou l'arme PSYCHIQUE devait etre selectionnee."""
    from engine.runner.components import unit_state_for_effects
    p_units = [HERALD_CARRIER, HERALD_ALLY]
    a_units = list(HERALD_VICTIMS)
    layout = _enemy_layout(sid, p_units, a_units)
    anchor_vis = next((v for v in HERALD_VICTIMS if v in layout), None)
    if anchor_vis is None:
        return {"skip": "aucune victime dans le layout adverse: %s" % sorted(layout)}
    # Les deux victimes doivent SURVIVRE au cast (1020 = 2 hits) puis a l'attaque de l'allie : sans
    # PV hors de portee d'un kill, le porteur mesure disparait avant la mesure. Aucun de ces champs
    # n'entre dans le degat mesure (attaque de l'ALLIE vers le porteur).
    patch = {v: {"Health": 300000, "RemainingHealth": 300000} for v in HERALD_VICTIMS}
    rid = _build(sid, p_units, a_units, armor=armor, unit_patch=patch,
                 anchor=layout[anchor_vis], occupied=layout.values())
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        bv = PR.units_by_visual(dv)
        for need in (HERALD_CARRIER, HERALD_ALLY, anchor_vis):
            if need not in bv:
                return {"skip": "roster incomplet: %s" % sorted(bv)}
        haarken, ally = bv[HERALD_CARRIER]["id"], bv[HERALD_ALLY]["id"]
        prim = bv[anchor_vis]["id"]
        pos = PR.positions(dv)

        # (1) Haarken a portee de son active (`constants.range = 2`).
        ok, dv = _move_within(sid, rid, dv, haarken, pos[prim], HERALD_RANGE)
        if not ok:
            return {"skip": "aucune tuile legale a d<=%d de la victime pour Haarken"
                            % HERALD_RANGE}
        if prim not in PR.legal_from_here(sid, rid, haarken, HERALD_OF_THE_APOCALYPSE):
            return {"skip": "cible non legale pour 1020 depuis la tuile atteinte"}

        # (2) cast NATIF de 1020 : il FRAPPE et pose 1027 sur la cible + l'ennemi derriere.
        res_cast = PR.act(sid, rid, {"kind": "ability", "casterId": haarken, "targetId": prim,
                                     "abilityType": HERALD_OF_THE_APOCALYPSE})
        if not res_cast.get("ok"):
            return {"skip": "cast HeraldOfTheApocalypse KO: %s" % str(res_cast)[:200]}
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        porteurs = _carriers_of(dv, HERALD_EXTRA_DAMAGE)
        if not porteurs:
            types_post = sorted(int(e.get("effectType") or -1) for u in (dv.get("units") or [])
                                for e in (u.get("effects") or []))
            return {"skip": "1027 porte par AUCUNE unite apres le cast (effets vus=%s) -- la "
                            "charge a-t-elle ete consommee par l'attaque du cast ?" % (types_post,)}
        pos = PR.positions(dv)
        vivants = [t for t in porteurs if t in pos]
        if not vivants:
            return {"skip": "les porteurs de 1027 ne sont plus sur le plateau: %s" % (porteurs,)}

        # (3) l'allie a portee de SON attaque normale sur UN porteur de 1027.
        normal_id = _normal_attack_id(dv, ally)
        if normal_id is None:
            return {"skip": "attaque normale de l'allie introuvable"}
        tgt = None
        legal = PR.legal_from_here(sid, rid, ally, normal_id)
        for cand in vivants:
            if cand in legal:
                tgt = cand
                break
        if tgt is None:
            for cand in vivants:
                ok, dv = _move_within(sid, rid, dv, ally, pos[cand], 1)
                if not ok:
                    continue
                if cand in PR.legal_from_here(sid, rid, ally, normal_id):
                    tgt = cand
                    break
        if tgt is None:
            return {"skip": "aucun porteur de 1027 atteignable par l'attaque normale de l'allie "
                            "(porteurs=%s)" % (vivants,)}

        board, dv, ob, cs = R1._snapshot(sid, rid)
        st_probe = R1._seeded_state(sid, rid, board, dv, ob, cs)
        us = unit_state_for_effects(st_probe, tgt)
        pre_active = sorted(e.effect_type for e in st_probe.effects.active_effects(tgt, us))

        calls, restore = R1.instrument_defender_modifiers()
        rows, restore_b = R1.instrument_bounds()
        try:
            last, _st = _replay_attack(sid, rid, board, dv, ob, cs, ally, tgt)
        finally:
            restore_b()
            restore()
        variant, _ = _replay_attack(sid, rid, board, dv, ob, cs, ally, tgt, R1._no_merge_variant)

        hp0 = PR.hp_of(sid, rid)
        res = PR.act(sid, rid, {"kind": "ability", "casterId": ally, "targetId": tgt,
                                "abilityType": normal_id})
        if not res.get("ok"):
            return {"skip": "attaque normale live KO: %s" % str(res)[:200]}
        hp1 = PR.hp_of(sid, rid)
        return {"armor": armor, "haarken": haarken, "ally": ally, "target": tgt,
                "porteurs_1027": porteurs, "primaire": prim,
                "pre_active": pre_active,
                # `port_detail` = le reste du ledger par coup du handler (roll, crit, block, arme).
                # Sans lui, un `per_hit` HORS des bornes imprimees ci-dessus reste inexplique -- et
                # un scalaire qu'on ne sait pas decomposer ne vaut pas confirmation.
                "port_detail": {k: v for k, v in (last or {}).items() if k != "per_hit"},
                "variant_detail": {k: v for k, v in (variant or {}).items() if k != "per_hit"},
                "port_per_hit": list(last.get("per_hit") or []),
                "port_total": last.get("total"), "port_profile": last.get("profile"),
                "variant_per_hit": list(variant.get("per_hit") or []),
                "variant_total": variant.get("total"),
                "live_per_hit": R1._live_hits(res, tgt),
                "live_hp": (hp0.get(tgt), hp1.get(tgt)),
                "live_delta": (hp0.get(tgt) or (0,))[0] - (hp1.get(tgt) or (0,))[0],
                "def_mods_calls": calls, "bounds_rows": rows}
    finally:
        PR.dispose(sid, rid)


def measure_neuroparasite(sid, armor: int = ARMOR_PIERCE) -> dict:
    """BRAS `neuro` -- `Neuroparasite` (effet 1218) sur le vecteur COMBAT.

    Le passif du Neurothrope pose le parasite a la CLOTURE (`On(9)`) d'une attaque PSYCHIQUE ; son
    additif ne joue donc qu'a la frappe SUIVANTE. On joue DEUX attaques natives consecutives et on
    rejoue la SECONDE cote PORT sur l'etat qui porte deja le parasite."""
    from engine.runner.components import unit_state_for_effects
    p_units = [NEURO_CARRIER]
    a_units = [NEURO_VICTIM]
    layout = _enemy_layout(sid, p_units, a_units)
    if NEURO_VICTIM not in layout:
        return {"skip": "victime absente du layout adverse: %s" % sorted(layout)}
    # Le montage est MULTI-TOURS (le parasite ne joue qu'a la frappe SUIVANTE), donc le tour adverse
    # doit s'ecouler sans casser la mesure : PV des deux cotes hors de portee d'un kill, et frappe
    # adverse ramenee a 1 (MESURE de la passe precedente : `unite disparue apres le tour adverse`).
    # Aucun de ces champs n'entre dans le degat que l'on mesure (attaque du Neurothrope VERS la
    # cible) -- ils bornent seulement la survie des deux acteurs.
    # `Movement: 0` FIGE la cible : sans lui, le tour adverse la deplace et la geometrie qui rendait
    # l'attaque legale au tour 1 ne l'est plus au tour 2 (MESURE : `cible non legale au tour 2`).
    # On CHOISIT la configuration au lieu de la subir.
    patch = {NEURO_CARRIER: {"Health": 300000, "RemainingHealth": 300000},
             NEURO_VICTIM: {"Health": 300000, "RemainingHealth": 300000, "Damage": 1,
                            "Movement": 0}}
    rid = _build(sid, p_units, a_units, armor=armor, unit_patch=patch,
                 anchor=layout[NEURO_VICTIM], occupied=layout.values())
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        bv = PR.units_by_visual(dv)
        for need in (NEURO_CARRIER, NEURO_VICTIM):
            if need not in bv:
                return {"skip": "roster incomplet: %s" % sorted(bv)}
        neuro, tgt = bv[NEURO_CARRIER]["id"], bv[NEURO_VICTIM]["id"]
        # `my_team` LU AVANT toute action. Avec un roster d'UNE unite, le tour bascule des qu'elle a
        # agi : lu apres l'attaque, `ctrl` est deja False partout et `my_team` sort `None`, ce qui
        # INVERSE `amine`/`aenemy` dans l'avance de tour (MESURE : `currentPlayer` satisfait mais
        # `ctrl=False`, `toActivate=[]`).
        my_team = next((u.get("team") for u in (dv.get("units") or []) if u.get("ctrl")), None)
        normal_id = _normal_attack_id(dv, neuro)
        if normal_id is None:
            return {"skip": "attaque normale du Neurothrope introuvable"}
        # L'arme PSYCHIQUE est la RANGED (portee 3) : le Neurothrope doit rester HORS CONTACT,
        # sans quoi l'attaque normale part en melee `Physical` et le gate
        # `CurrentAttackDamageProfilesContain(0xd)` du passif ne peut pas s'ouvrir.
        pos = PR.positions(dv)
        ok, dv = _move_within(sid, rid, dv, neuro, pos[tgt], NEURO_RANGE, min_dist=2)
        if not ok:
            return {"skip": "aucune tuile legale a 2<=d<=%d de la victime" % NEURO_RANGE}
        if tgt not in PR.legal_from_here(sid, rid, neuro, normal_id):
            return {"skip": "cible non legale pour l'attaque du Neurothrope"}

        # (1) PREMIERE attaque native -> `On(9)` pose le parasite (1218) sur la cible.
        first = PR.act(sid, rid, {"kind": "ability", "casterId": neuro, "targetId": tgt,
                                  "abilityType": normal_id})
        if not first.get("ok"):
            return {"skip": "1ere attaque live KO: %s" % str(first)[:200]}
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        types_post = sorted(e.get("effectType") for u in (dv.get("units") or [])
                            if u.get("id") == tgt for e in (u.get("effects") or []))
        parasite_live = NEUROPARASITE_EFFECT in types_post
        if not parasite_live:
            return {"skip": "parasite 1218 NON pose apres la 1ere attaque (effets=%s) -- le gate "
                            "`CurrentAttackDamageProfilesContain(0xd)` ne s'est pas ouvert, donc "
                            "l'attaque est partie en MELEE `Physical`" % (types_post,)}

        # (1bis) TOUR SUIVANT. Une unite n'agit qu'une fois par tour : sans ce passage, la seconde
        # attaque native est refusee en silence (`per_hit = []`, delta PV 0) -- MESURE de la passe
        # precedente de ce probe. On rend la main a l'IA adverse (`aiPlayByUnit`) puis on
        # RE-VERIFIE la geometrie, que son tour a pu changer.
        ok, dv = _advance_to_my_turn(sid, rid, my_team)
        if not ok:
            return {"skip": "la main n'est pas revenue au joueur (currentPlayer=%s, my_team=%s)"
                            % (dv.get("currentPlayer"), my_team)}
        pos = PR.positions(dv)
        if tgt not in pos or neuro not in pos:
            return {"skip": "unite disparue apres le tour adverse"}
        ok, dv = _move_within(sid, rid, dv, neuro, pos[tgt], NEURO_RANGE, min_dist=2)
        if not ok:
            return {"skip": "hors plage [2,%d] apres le tour adverse" % NEURO_RANGE}
        if tgt not in PR.legal_from_here(sid, rid, neuro, normal_id):
            pos = PR.positions(dv)
            un = next((x for x in (dv.get("units") or []) if x.get("id") == neuro), {})
            return {"skip": "cible non legale au tour 2 (d=%s, legales=%s, toActivate=%s, "
                            "neuro ctrl=%s abilities=%s)"
                            % (hexgeo.distance(pos[neuro], pos[tgt]),
                               PR.legal_from_here(sid, rid, neuro, normal_id),
                               dv.get("toActivate"), un.get("ctrl"),
                               [(a.get("kind"), a.get("id"), a.get("ready"))
                                for a in (un.get("abilities") or [])])}
        types_t2 = sorted(e.get("effectType") for u in (dv.get("units") or [])
                          if u.get("id") == tgt for e in (u.get("effects") or []))
        if NEUROPARASITE_EFFECT not in types_t2:
            return {"skip": "parasite 1218 expire avant le tour 2 (effets=%s)" % (types_t2,)}

        # (2) SECONDE attaque : c'est celle dont l'additif defenseur depend du parasite.
        board, dv, ob, cs = R1._snapshot(sid, rid)
        st_probe = R1._seeded_state(sid, rid, board, dv, ob, cs)
        us = unit_state_for_effects(st_probe, tgt)
        pre_active = sorted(e.effect_type for e in st_probe.effects.active_effects(tgt, us))
        calls, restore = R1.instrument_defender_modifiers()
        rows, restore_b = R1.instrument_bounds()
        try:
            last, _st = _replay_attack(sid, rid, board, dv, ob, cs, neuro, tgt)
        finally:
            restore_b()
            restore()
        variant, _ = _replay_attack(sid, rid, board, dv, ob, cs, neuro, tgt, R1._no_merge_variant)

        hp0 = PR.hp_of(sid, rid)
        res = PR.act(sid, rid, {"kind": "ability", "casterId": neuro, "targetId": tgt,
                                "abilityType": normal_id})
        if not res.get("ok"):
            return {"skip": "2e attaque live KO: %s" % str(res)[:200]}
        hp1 = PR.hp_of(sid, rid)
        return {"armor": armor, "neuro": neuro, "target": tgt,
                "parasite_live": parasite_live, "types_post": types_post,
                "pre_active": pre_active,
                "port_per_hit": list(last.get("per_hit") or []),
                "port_total": last.get("total"), "port_profile": last.get("profile"),
                "variant_per_hit": list(variant.get("per_hit") or []),
                "live_per_hit": R1._live_hits(res, tgt),
                "live_delta": (hp0.get(tgt) or (0,))[0] - (hp1.get(tgt) or (0,))[0],
                "def_mods_calls": calls, "bounds_rows": rows}
    finally:
        PR.dispose(sid, rid)


def _report(tag, m, degenerate=False):
    if m.get("skip"):
        print("[%s] SKIP %s" % (tag, m["skip"]))
        return
    print("[%s] armure=%s  cible u%s  profil=%s" % (tag, m.get("armor"), m["target"],
                                                    m.get("port_profile")))
    print("  effets ACTIFS cible au chargement : %s" % (m["pre_active"],))
    for row in m.get("bounds_rows") or []:
        print("  [etages] %s" % json.dumps(row, default=str))
    for c in m.get("def_mods_calls") or []:
        print("  [def_mods] u%s melee=%s profil=%s att=%s  active=%s"
              % (c["unit"], c["is_melee"], c["profile"], c["attacker"], c["active"]))
        print("             mods=%s" % (c["mods"],))
    if m.get("port_detail"):
        print("  [detail port]    %s" % json.dumps(m["port_detail"], default=str)[:400])
    if m.get("variant_detail"):
        print("  [detail variant] %s" % json.dumps(m["variant_detail"], default=str)[:400])
    print("  PORT    per_hit = %s (total %s)" % (m["port_per_hit"], m.get("port_total")))
    print("  VARIANT per_hit = %s   (contre-modele POST-%%list)" % (m["variant_per_hit"],))
    print("  LIVE    per_hit = %s (delta PV %s)" % (m["live_per_hit"], m["live_delta"]))
    if degenerate:
        print("  ATTENTION : regime DEGENERE (branche ARMURE, plancher affine de pente 1) --")
        print("  port == contre-modele == natif y est une BORNE, jamais une confirmation.")


def main():
    sid = R._resolve_session()
    only = sys.argv[1] if len(sys.argv) > 1 else "chrono"
    try:
        if only in ("chrono", "all"):
            _report("chrono/PERCAGE", measure_chronometron(sid, ARMOR_PIERCE))
        if only in ("chrono-flat", "all"):
            _report("chrono/ARMURE", measure_chronometron(sid, ARMOR_FLAT), degenerate=True)
        if only in ("neuro", "all"):
            _report("neuro/PERCAGE", measure_neuroparasite(sid))
        if only in ("herald", "all"):
            _report("herald/PERCAGE", measure_herald(sid))
    finally:
        for rid in list(PR._rids):
            PR.dispose(sid, rid)


if __name__ == "__main__":
    main()
