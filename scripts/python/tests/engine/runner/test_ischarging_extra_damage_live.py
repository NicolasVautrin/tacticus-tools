"""CLIQUET `IsCharging` du canal EXTRA-DEGAT (case-r32) -- le gate n'est PAS « l'unite a bouge ».

Le canal modifier attaquant portait ce noeud natif par le proxy `has_moved` (`UnitFlag.Moved`).
Le predicat reel est `IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)` :

    AreEntitiesAdjacent(caster, target)
    && GetComponent<UnitComponent>(caster).ChargedUnitIds@+0x190.Contains(target.Id)

et `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` n'ajoute a cette liste que les unites
devenues **NOUVELLEMENT adjacentes** pendant le pas. Le proxy est donc strictement PLUS LARGE :
un caster qui BOUGE vers une cible DEJA adjacente avant son pas a `Moved` VRAI et `IsCharging` FAUX.

Effets concernes (les TROIS `CreateEffectDamageBonusForAttack` qui appellent
`IdunBattleLogic.Entities.DSLTriggers$$IsCharging`, xrefs relues) :
  * `IdunBattle.Entities.Effects.Loki.AvalancheOfMuscleTargetEffect$$...` (1025, `astraBullgryn`)
  * `IdunBattle.Entities.Effects.Loki.FeederTendrils_ExtraDamageEffect$$...` (1197, Deathleaper)
  * `IdunBattle.Entities.Effects.Loki.BlackRage_ExtraDamageEffect$$...` (1343, `bloodDeathCompany`)
(`SmashaEadEffect$$...` n'a AUCUN noeud `IsCharging` -- son trigger seul porte la condition de pas.)

Ce que le test GARDE : le rejeu offline est bit-exact avec le live DANS LES DEUX REGIMES, donc la
CHARGE accorde le bonus et le DECALAGE ADJACENT ne l'accorde pas. Un port revenu au proxy
`has_moved` sur-appliquerait dans le second et le test tomberait.

Ce module verrouille la voie « snapshot AVANT le pas, pas REJOUE offline (`MoveUnitMessage`) » : ce
qui est confronte ici, c'est le mirror PORT d'`UpdateCharging` (`components.update_charging`), qui
pose `ChargedUnitIds` lui-meme. La voie COMPLEMENTAIRE -- capture MI-ACTIVATION + SEED de la liste
par `load_state` (#230) -- est verrouillee par `test_load_state_turn_state_live.py`. Les deux sont
necessaires : elles confrontent deux morceaux de port DIFFERENTS sur le meme predicat.

Historique, parce qu'il explique la methode : `test_avalanche_of_muscle_live.py` (#o10-a) a ete
RETIRE le 2026-07-28 parce qu'il gatait par le proxy refute, et parce qu'il rejouait l'attaque
offline depuis un snapshot post-pas en DECLARANT la charge par `set_moved_flag` -- a l'epoque aucun
RPC n'exposait `UnitComponent.ChargedUnitIds@+0x190`, donc un snapshot post-pas ne pouvait pas la
porter. Ce n'est plus vrai depuis `f790ff4` + #230 ; ce qui reste faux, c'est de DECLARER la charge
par un proxy au lieu de la lire. Les garanties propres a l'ancien fichier (non-vacuite de la
magnitude, materialisation sur les PV) sont reprises par `test_charge_bonus_is_not_vacuous`.

ASCII only.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # helpers siblings
from _ability_cast_replay import ability_cast_harness   # noqa: E402,F401  (fixture)
from _charge_regime import (CHARGE, NO_STEP, STEP_ADJACENT,       # noqa: E402,F401  (fixture)
                            charge_regime)

from engine.runner.abilities.loki.strike import BlackRageAbility   # noqa: E402
from engine.runner.components import HealthComponent               # noqa: E402
from engine.runner.messages import AttackUnitMessage               # noqa: E402
from engine.runner.runner import Runner                            # noqa: E402

AVALANCHE_EFFECT_TYPE = 1025           # "AvalancheOfMuscle_ExtraDamage"


@pytest.fixture(scope="module")
def bullgryn(charge_regime):
    """`astraBullgryn` (HERO du pool) porte le passif `AvalancheOfMuscle` -> l'effet 1025 sur
    lui-meme. Cibles Necrons a PV gonfles : aucune ne meurt pendant le montage."""
    return charge_regime(p_units="astraBullgryn", a_units="necroOverlord,necroWarden")


def _run(h, regime):
    rec = h.run(caster_visual="astraBullgryn", regime=regime)
    if rec is None:
        pytest.skip("geometrie %s non realisable sur ce board" % regime)
    if not rec["live_ok"] or not rec["live_per_hit"]:
        pytest.skip("attaque normale live refusee/vide (%s)" % regime)
    return rec, h.replay_offline(rec)


def test_step_adjacent_is_not_charging(bullgryn):
    """CAS DISCRIMINANT -- le caster BOUGE, mais la cible etait DEJA adjacente avant le pas.

    `UpdateCharging` ne l'ajoute donc PAS aux `ChargedUnitIds` -> `IsCharging` FAUX -> AUCUN
    +extraDmg, alors que le flag `Moved` est VRAI. C'est ce que le proxy `has_moved` ne savait pas
    distinguer."""
    rec, off = _run(bullgryn, STEP_ADJACENT)
    assert rec["target"] not in off["charged"], (
        "la cible ne doit PAS entrer dans ChargedUnitIds (elle etait deja adjacente avant le pas) ; "
        "charged=%s target=%s" % (off["charged"], rec["target"]))
    assert off["per_hit"] == rec["live_per_hit"], (
        "STEP_ADJACENT : le port sur-applique le +extraDmg de charge -- live=%s offline=%s "
        "(delta/coup=%s)" % (rec["live_per_hit"], off["per_hit"],
                             [o - l for l, o in zip(rec["live_per_hit"], off["per_hit"])]))


@pytest.fixture(scope="module")
def charge_rec(bullgryn):
    """Le regime CHARGE monte UNE SEULE fois (il joue une bataille live) et sert les deux tests qui
    en dependent : le controle positif du gate, et la garde de non-vacuite."""
    return _run(bullgryn, CHARGE)


def test_charge_is_charging(charge_rec):
    """CONTROLE POSITIF -- le caster arrive AU CONTACT d'une cible qui n'etait PAS adjacente : la
    cible entre dans `ChargedUnitIds`, `IsCharging` est VRAI, le +extraDmg s'applique des DEUX
    cotes."""
    rec, off = charge_rec
    assert rec["target"] in off["charged"], (
        "la cible DOIT entrer dans ChargedUnitIds (nouvellement adjacente) ; charged=%s target=%s"
        % (off["charged"], rec["target"]))
    assert off["per_hit"] == rec["live_per_hit"], (
        "CHARGE : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit"]))


def test_charge_bonus_is_not_vacuous(bullgryn, charge_rec):
    """GARDE DE NON-VACUITE + MATERIALISATION -- reprise des deux verrous que portait le fichier
    retire `test_avalanche_of_muscle_live.py` (#o10-a), les seuls qui n'etaient pas deja ici.

    Pourquoi ce test existe : `test_charge_is_charging` compare live et offline coup par coup. Si le
    bonus de charge valait ZERO (magnitude non resolue, effet absent de l'etat, gate cable a un
    predicat toujours faux), les deux cotes seraient egaux et le controle positif passerait A VIDE --
    il ne prouverait plus rien de l'additif. On exige donc, sur le MEME enregistrement :

      (a) le noeud `IsCharging` OUVRE et FERME reellement ce canal, les DEUX polarites lues sur
          l'objet effet du porteur (`AvalancheOfMuscleTargetEffect$$CreateEffectDamageBonusForAttack` =
          `ForAddition(OwnerIsCaster & IsCharging, ConfigVar(8 = extraDmg))`) ;
      (b) la magnitude resolue depuis gameconfig (`AvalancheOfMuscleAbility$$GetExtraDamage` =
          `AbilityConfiguration.GetVariableForLevel(config, 8, ...)` x multiplier de l'unite) est
          STRICTEMENT positive ;
      (c) elle est OBSERVABLE dans le scenario compare : le MEME etat, le MEME flux de PRNG, rejoue
          sans l'effet 1025, ne rend pas les memes coups. Comme (c) part du rejeu deja prouve
          bit-exact avec le live, c'est bien le LIVE qui porte l'additif -- rien n'est fitte ;
      (d) les coups calcules ATTERRISSENT : PV de la cible apres l'attaque, offline == live (le canal
          per-coup peut etre juste et l'application fausse -- deux etages distincts).
    """
    rec, off = charge_rec
    caster, target = rec["caster"], rec["target"]

    # (a)+(b) -- l'effet materialise du porteur, ses deux polarites de gate, sa magnitude.
    eff = next((e for e in (off["state"].effects.by_unit.get(caster) or [])
                if e.effect_type == AVALANCHE_EFFECT_TYPE), None)
    assert eff is not None, (
        "l'effet %d AvalancheOfMuscle_ExtraDamage n'est pas materialise sur le porteur %s -- le "
        "scenario ne peut RIEN prouver de l'additif" % (AVALANCHE_EFFECT_TYPE, caster))
    on = eff.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx={"is_charging": True})
    offb = eff.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx={"is_charging": False})
    assert offb is None, (
        "gate IsCharging FERME : le canal doit rendre None hors charge, obtenu %s" % (offb,))
    assert on is not None and on.value and on.value > 0, (
        "gate IsCharging OUVERT : magnitude ConfigVar(8) non resolue ou nulle (%s) -- niveau=%s "
        "mult=%s" % (on, eff.ability_level, eff.ability_variables_multiplier))

    # (c) -- contrefactuel offline : MEME etat, MEME PRNG, effet 1025 RETIRE du porteur.
    st = bullgryn.offline_state(rec)
    st.effects.by_unit[caster] = [e for e in (st.effects.by_unit.get(caster) or [])
                                  if e.effect_type != AVALANCHE_EFFECT_TYPE]
    r = Runner(st).install_default_handlers(20)
    r.apply(AttackUnitMessage(attacker_id=caster, target_id=target))
    without = list((r.damage_handler.last or {}).get("per_hit") or [])
    assert len(without) == len(off["per_hit"]), (
        "l'additif ne doit PAS changer la CARDINALITE des coups (canal magnitude, pas cardinalite) "
        "-- avec=%s sans=%s" % (off["per_hit"], without))
    assert without != off["per_hit"] and sum(off["per_hit"]) > sum(without), (
        "scenario NON DISCRIMINANT : retirer l'effet %d ne change pas les coups (avec=%s sans=%s) -- "
        "le controle positif CHARGE comparerait live et offline a vide"
        % (AVALANCHE_EFFECT_TYPE, off["per_hit"], without))

    # (d) -- materialisation : PV de la cible APRES LE DERNIER COUP, offline == live.
    #
    # ⚠ PIEGE DE MESURE (mesure `probe_o10a_charge_hp_stage.py`, 2026-07-28) : NE PAS lire les PV
    # dans `applyAction.units[].hp`. Ce tableau est l'etat de FIN DE CASCADE, pas de fin d'attaque --
    # l'attaque etait la derniere action du caster, donc le tour BASCULE dans la meme reponse
    # (`Match_CurrentPlayerId` 3 -> 4) et la cible encaisse ensuite son propre debut de tour. Mesure
    # sur `necroOverlord` : les 4 coups descendent bien a 106098 (= offline, bit-exact), puis le
    # groupe `LivingMetalRepair` la remonte a **118098** (+12000 = 10 % des PV max) et deux coups de
    # riposte (`Passive_Ability_Type` 1045) partent sur le caster. Lire `units[].hp` fait donc voir un
    # ecart de 12000 la ou le port est EXACT -- un faux « bug de port » pret a l'emploi.
    # L'etage propre est le `UnitStats_RemainingHealth` porte par le DERNIER evenement de degat de
    # cette attaque : c'est le meme point du pipeline que l'etat offline apres `AttackUnitMessage`.
    live_hp_after_hits = None
    a0 = ((rec.get("live_raw") or {}).get("actions") or [{}])[0]
    for ev in (a0.get("events") or []):
        td = ev.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if (td.get("Attacker_Id") == caster and td.get("Target_Id") == target
                and "Amount" in td and "UnitStats_RemainingHealth" in td):
            live_hp_after_hits = td["UnitStats_RemainingHealth"]
    assert live_hp_after_hits is not None, (
        "aucun evenement de degat ne porte UnitStats_RemainingHealth -- l'etage PV n'est pas lisible")
    e_t = off["state"].get_entity(target)
    off_hp = e_t.get_component(HealthComponent).hp if e_t is not None else None
    assert off_hp == live_hp_after_hits, (
        "PV apres le dernier coup : offline %s != live %s (coups pourtant identiques %s) -- les "
        "montants per-coup sont justes mais leur APPLICATION diverge"
        % (off_hp, live_hp_after_hits, off["per_hit"]))


@pytest.fixture(scope="module")
def bullgryn_alt(charge_regime):
    """GENERALISATION : meme invariant, AUTRE board et AUTRE seed, AUTRES cibles. Le seed n'est
    qu'un generateur de bataille et le board change la geometrie (elevations, connectivite) -- si le
    verdict tenait par accident de tuile, il ne tiendrait pas ici."""
    return charge_regime(p_units="astraBullgryn", a_units="orksNob,tyranTyrantGuard",
                         seed="31337", board="C1_25")


def test_step_adjacent_is_not_charging_other_board(bullgryn_alt):
    """Le cas discriminant, rejoue sur `C1_25` / seed 31337 / cibles Orks-Tyranides."""
    rec, off = _run(bullgryn_alt, STEP_ADJACENT)
    assert rec["target"] not in off["charged"]
    assert off["per_hit"] == rec["live_per_hit"], (
        "STEP_ADJACENT (C1_25/31337) : live=%s offline=%s"
        % (rec["live_per_hit"], off["per_hit"]))


def test_charge_is_charging_other_board(bullgryn_alt):
    """Controle positif du meme montage alternatif."""
    rec, off = _run(bullgryn_alt, CHARGE)
    assert rec["target"] in off["charged"]
    assert off["per_hit"] == rec["live_per_hit"], (
        "CHARGE (C1_25/31337) : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit"]))


def test_no_step_is_not_charging(bullgryn):
    """CONTROLE NEGATIF -- aucun pas du tour : ni `Moved` ni `ChargedUnitIds`. Les deux modeles
    s'accordent ici ; le test verrouille que le retrofit n'a rien casse sur ce regime, le seul que
    le proxy traitait deja juste."""
    rec, off = _run(bullgryn, NO_STEP)
    assert off["charged"] == [], "aucun pas -> ChargedUnitIds vide, obtenu %s" % (off["charged"],)
    assert off["per_hit"] == rec["live_per_hit"], (
        "NO_STEP : live=%s offline=%s" % (rec["live_per_hit"], off["per_hit"]))


# ---------------------------------------------------------------------------------------------
# 3e consommateur du meme noeud : `BlackRage_ExtraDamage` (1343, `bloodDeathCompany` <<Lucien>>).
# Son canal n'est PAS porte, et ce test VERROUILLE POURQUOI -- pas par prudence rhetorique, par un
# bloqueur MESURE : l'effet est pose par le cast lui-meme (`AddEffect(1343, caster)` du
# `black_rage_tree`) SANS que le niveau d'ability de la source soit propage, donc `ConfigVar(8)`
# s'indexe au niveau ~1 (`extraDmg[1] = 10`) au lieu du niveau reel (`[50] = 554`). Le canal
# rendrait 18 par coup au lieu de 997 : une valeur FAUSSE, pas une valeur manquante.
#
# Le test echouera le jour ou le vecteur de pose propagera le niveau (`_source_scaling`, comme
# `Waaagh_ExtraDamage` 1100) -- c'est exactement le signal « le blocage est leve, porte le canal ».
# ---------------------------------------------------------------------------------------------

def _hp_by_id(ob):
    """PV live par id d'unite -- cle sur `squadId` (l'id du decisionView, celui du port), PAS
    `entityId` (l'entite ECS interne), sinon aucune ligne ne se recoupe avec l'offline."""
    return {int(u["squadId"]): int(u.get("hp") or 0)
            for u in ((ob or {}).get("units") or []) if u.get("squadId") is not None}


def test_black_rage_effect_level_not_propagated(ability_cast_harness):
    """BLOQUEUR du 3e port : apres un cast `BlackRage` (1163), l'effet 1343 pose sur le caster
    n'a AUCUN niveau d'ability exploitable -> sa magnitude s'indexerait au niveau 1.

    Verrou a DOUBLE SENS : il constate le bloqueur ET rappelle ce qu'il faut faire quand il tombe."""
    h = ability_cast_harness(p_units="bloodDeathCompany",
                             a_units="necroOverlord,necroWarden",
                             extra=["--hp-target", "120000", "--hp-player", "120000"])
    me = h.by_visual("bloodDeathCompany")
    if me is None:
        pytest.skip("bloodDeathCompany absent du build")
    h.my_player = me.get("owner")
    ens = h.enemies_of(h.my_player)
    if not ens:
        pytest.skip("aucun ennemi")
    tgt = ens[0]
    # Geometrie : cible ancree, caster a distance 2 (la charge de BlackRage doit avoir un pas a
    # faire) ; les autres ennemis ecartes pour ne pas polluer le flux d'evenements.
    t_pos = None
    for tid in sorted(h.board.by_id):
        c = h.board.coord(tid)
        if h.board.walkable(tid) and len(h.free_neighbours(c, 1)) >= 3 \
                and len(h.free_neighbours(c, 2)) >= 1:
            t_pos = c
            break
    if t_pos is None or not h.place(tgt["id"], t_pos):
        pytest.skip("ancre cible non trouvee")
    for other in ens[1:]:
        far = h.free_neighbours(t_pos, 4, exclude=(other["id"],))
        if far:
            h.place(other["id"], far[0])
    # Le pas de charge de BlackRage a une PORTEE (`BlackRageAbility$$GetPossibleMovementTiles` +
    # `GetMovementBonus`) : une cible trop loin rend le cast NO-OP en silence (`ok=True`,
    # `mutated` absent, 2 evenements -- signature #111, reproduite ici). On ne DEVINE donc pas la
    # bonne distance : on interroge `abilityTargets` (dont `targets` = « ce tour, MOVE inclus »)
    # et on rapproche le caster jusqu'a ce que la cible y figure.
    placed = False
    for radius in (2, 3, 1, 4):
        cands = h.free_neighbours(t_pos, radius, exclude=(me["id"],))
        for start in cands[:4]:
            if not h.place(me["id"], start):
                continue
            if h.reach_my_turn() is None:
                pytest.skip("mon tour non atteint")
            at = h.rpc("abilityTargets",
                       {"runnerId": h.rid, "unitId": me["id"], "abilityType": 1163}, 60)
            tids = [t.get("targetId") if isinstance(t, dict) else t
                    for u in ((at or {}).get("units") or []) if u.get("unitId") == me["id"]
                    for ab in (u.get("abilities") or []) if ab.get("abilityId") == 1163
                    for t in (ab.get("targets") or [])]
            if tgt["id"] in tids:
                placed = True
                break
        if placed:
            break
    if not placed:
        pytest.skip("aucune position de depart ne met la cible a portee de charge de BlackRage")

    snap = h.snapshot()
    st = h.offline_state(snap)
    BlackRageAbility().execute_behaviour(st, me["id"], tgt["id"])
    posed = [e for e in (st.effects.by_unit.get(me["id"]) or []) if e.effect_type == 1343]
    if not posed:
        pytest.skip("le cast offline n'a pas pose l'effet 1343 (montage a moitie fait)")
    eff = posed[0]
    lvl = (eff.active_ability_level if eff.active_ability_level is not None
           else (eff.ability_level if eff.ability_level is not None else eff.level))
    assert not lvl or int(lvl) <= 1, (
        "BLOQUEUR LEVE : l'effet 1343 arrive desormais au niveau %s. Le canal "
        "`create_effect_damage_bonus_for_attack` de `BlackRageExtraDamageEffect` peut donc etre "
        "PORTE (mirror : ForAddition(OwnerIsCaster & IsCharging & IsNormalAttack, "
        "ConfigVar(8=extraDmg))) -- retire ce verrou et ecris le controle positif a la place." % lvl)
