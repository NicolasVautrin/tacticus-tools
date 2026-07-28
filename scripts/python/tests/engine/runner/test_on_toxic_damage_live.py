"""`OnToxicDamageAbility` (1203) — pose de la CONTAMINATION on-hit, confrontee au LIVE.

RE (decompile ghidra, build gqfc5mff6c) :
    IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateTrigger
        On(0x10, 1) & DamageProfileHasTrait(4 = OnToxic) & !TriggeringEffectIs(0x4dc)
    IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateBehaviour
        If( IsFirstHitInSeries() & Maybe(ConfigConst(0x4b3, Self@0x148, 0x2a = chance)),
            AddEffect(0x4dc = Contaminated, stateRef, Tiles(target@0x178)) )

Son jumeau `OnFireDamageAbility` (porte, `triggers/loki/fire.py`) partage le vecteur, le gate de profil
et la feuille de pose, mais son behaviour est INCONDITIONNEL. Les deux differences REELLES portees ici :
le `If`, et le couple `IsFirstHitInSeries & Maybe(chance)` -> **exactement UN `NextBool(chance)` par
SERIE de coups** (le ET natif `IdunBattle.DSL.MultipleAbilityTrigger$$ShouldTrigger` COURT-CIRCUITE :
aux coups 2..N, `IsFirstHitInSeries` est faux et le `Maybe` n'est PAS evalue).

CE QUE CES TESTS PROUVENT :
  (1) ANCRAGE DE LA MAGNITUDE (offline, sans live) : la `chance` lue par le port
      (`globalValues.toxicDamageContaminationChance`) == la constante que `ConfigConst(1203, ..., 0x2a)`
      interroge REELLEMENT en live, c.-a-d.
      `BattleConfiguration.Abilities.PassiveAbilities.OnToxicDamageAbility.Constants.chance`. Une
      divergence de build casse CE test au lieu de passer inapercue.
  (2) COMPTE ET POSITION DU TIRAGE (etat LIVE, execution offline) : un coup de profil `Toxic` consomme
      EXACTEMENT un `next_bool` du `state.rng` cale sur le MT live, et le verdict de pose est CELUI que
      ce tirage predit (rng clone -> oracle). C'est ce qui discrimine la valeur 25 : un `chance` faux
      donnerait le meme COMPTE mais un VERDICT different.
  (3) GATE DE PROFIL : un coup NON-Toxic (`Power`) ne pose rien ET ne consomme AUCUN tirage.
  (4) IDEMPOTENCE : sur une tuile deja contaminee, le tirage a QUAND MEME lieu (le `Maybe` precede
      l'`AddEffect` dans l'arbre) mais aucune pose n'est rapportee -- mirror du gate `already-present`
      d'`AddEffectOperation`.
  (5) AGREMENT LIVE bout-en-bout : une attaque normale de `genesBiophagus` (arme MELEE `Toxic`, 1 coup)
      rejouee LIVE et OFFLINE sur le MEME etat MT -> memes PV de cible ET meme verdict de contamination
      de la tuile de la cible.

PORTEURS (gate de confrontabilite) : HERO `genesBiophagus`/`admecMarshall`/`deathPutrifier` (arme Toxic),
`deathBlightlord`/`admecDominus` (ability Toxic), MoW `deathCrawler`, SUMMON `admecSmnVanguard` — tous
atteignables ; le reste est NPC. Le canal est TRANSVERSE (tout coup de profil `Toxic`).

ASCII only.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import gameconfig as GC
from engine.entities.damage_trait import DamageTrait
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.components import HealthComponent, PositionComponent, UnitComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.operations.triggers.loki.on_toxic_damage import (TOXIC_CHANCE_KEY,
                                                                    _on_toxic_damage_ability)
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))      # tests/engine/runner -> import du helper sibling

from _on_hit_tile_effect_replay import replay_on_hit_tile_effect   # noqa: E402

ROOT = Path(__file__).resolve().parents[5]           # racine repo (scripts/python/tests/engine/runner)
SEED_BC = ROOT / "data" / "seed-bc.json"
CARRIER_VIS = "genesBiophagus"                        # Hollan — arme MELEE `Toxic` 1 coup (HERO, --list-pool)
# 2e porteur, RANGED (r2) : le gate natif porte sur le PROFIL du coup, pas sur sa portee — confronter
# les DEUX chemins evite qu'un cablage present sur un seul passe pour general. `admecMarshall` porte
# AUSSI une arme `Physical` (2 coups) : le test verifie donc le profil du coup effectivement joue.
RANGED_CARRIER_VIS = "admecMarshall"
ESCORT_VIS = "adeptHospitaller"                       # 2e unite de mon camp : garde une activation (pas de tick)
CONTAMINATED = int(EffectType.Contaminated)           # 0x4dc = 1244 (effet de TUILE)
TOXIC_PROFILE = "Toxic"
PLAIN_FOES = "necroWarden,necroWarden"                # temoin SANS `Daemon` : un seul tirage neuf/attaque
# CROISEMENT avec #221 : `blackObliterator` porte le trait `Daemon` -> son jet de block
# `Daemon_ExtraBlock` (porte depuis `fda9142`) tombe dans la MEME attaque que notre `Maybe`. Meme unite
# que la garde `test_daemon_extra_block_live.py` (Daemon SANS `Resilient`/`Terrifying`).
DAEMON_FOES = "blackObliterator,blackObliterator"


def _build_args(a_units: str) -> list:
    return ["--roster", "2", "--p-units", f"{CARRIER_VIS},{ESCORT_VIS}", "--a-units", a_units]


BUILD = _build_args(PLAIN_FOES)                       # roster par defaut des tests d'etat (1)-(4)
# Le tirage est a `chance`% : une seule attaque ne prouverait le canal que dans 25% des cas. On confronte
# jusqu'a MAX_ATTACKS attaques et on EXIGE qu'au moins une POSE ait ete confrontee (cf. l'assertion
# finale) -- sinon le test ne validerait que le NON-declenchement.
MAX_ATTACKS = 12


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"])
    r.mti = s["mti"]
    return r


def _load(rpc, build_runner, seed="777"):
    """Etat offline charge depuis un runner LIVE frais, `state.rng` cale sur le MT live."""
    rid = build_runner(seed, extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    state = load_state(dec, ob, snap, board=board)
    state.rng = _seed_rng(s0)
    if state.effects is None:
        pytest.skip("EffectsState absent (snapshot sans combatSnapshot) -> AddEffect impossible")
    return state, board, rid


def _unit(state, vis):
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == vis and uc.alive:
            return eid
    return None


def _any_enemy(state, of_id):
    """1re unite VIVANTE d'une autre equipe que `of_id` (cible du coup simule)."""
    from engine.runner.components import OwnerComponent
    mine = state.get_entity(of_id).get_component(OwnerComponent)
    for eid, e in state.entities.items():
        uc, oc = e.get_component(UnitComponent), e.get_component(OwnerComponent)
        if uc is not None and uc.alive and oc is not None and oc.team != mine.team:
            return eid
    return None


def _tile_of(state, board, uid):
    pc = state.get_entity(uid).get_component(PositionComponent)
    return board.id_at(pc.col, pc.row) if pc is not None else None


def _oracle_after_one_roll(state, chance):
    """Clone du PRNG avance d'EXACTEMENT un `next_bool(chance)` -> (verdict, etat MT attendu).

    L'etat MT (`mt`/`mti`) est l'oracle de CONSOMMATION : le comparer apres coup prouve « exactement un
    tirage, ni plus ni moins ». `call_count` ne convient PAS (il est incremente par `next_internal` ET
    par `genrand_int32` -> +2 pour un seul `NextBool`)."""
    clone = copy.deepcopy(state.rng)
    verdict = clone.next_bool(int(chance))
    return verdict, (list(clone.mt), clone.mti)


def _mt_state(rng):
    return (list(rng.mt), rng.mti)


# --------------------------------------------------------------------- (1) ancrage de la magnitude

def test_toxic_chance_is_config_driven_and_matches_battle_config():
    """La `chance` du port vient de la CONFIG, et c'est la MEME que celle que le natif interroge.

    Natif : `ConfigConst(0x4b3 = 1203, <config de l'ability>, 0x2a = AbilityConstantType.chance)` ->
    `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant`. La config de 1203 est portee par
    la BattleConfiguration (`Abilities.PassiveAbilities.OnToxicDamageAbility`), PAS par
    `units.abilities` du gameconfig client -- d'ou la lecture du port via `globalValues`. Ce test ANCRE
    l'egalite des deux (une divergence de build echoue ICI, pas silencieusement en bataille).

    Verifie AUSSI le gate de profil : seul `Toxic` porte le `DamageTrait.OnToxic` (4)."""
    gv = GC.global_value(TOXIC_CHANCE_KEY)
    assert gv, f"globalValues.{TOXIC_CHANCE_KEY} absent : la chance du port n'a plus de source config"
    bc = json.loads(SEED_BC.read_text(encoding="utf-8"))
    cfg = ((bc.get("Abilities") or {}).get("PassiveAbilities") or {}).get("OnToxicDamageAbility")
    assert cfg is not None, ("OnToxicDamageAbility absent des PassiveAbilities de la BC capturee -- "
                             "le ConfigConst(1203, ..., chance) natif n'a plus d'ancrage")
    bc_chance = (cfg.get("Constants") or {}).get("chance")
    assert bc_chance is not None, "BC OnToxicDamageAbility.Constants.chance absent"
    assert int(gv) == int(bc_chance), (
        f"chance divergente : globalValues.{TOXIC_CHANCE_KEY}={gv} != BC "
        f"Abilities.PassiveAbilities.OnToxicDamageAbility.Constants.chance={bc_chance} -- le port lirait "
        f"une magnitude que le natif n'utilise pas")

    profiles = {n for n, p in (GC._index()["damageProfiles"] or {}).items()
                if DamageTrait.OnToxic.name in (p.get("Traits") or [])}
    assert profiles == {TOXIC_PROFILE}, (
        f"profils portant {DamageTrait.OnToxic.name} = {sorted(profiles)} (attendu {{'{TOXIC_PROFILE}'}}) "
        f"-- le gate `DamageProfileHasTrait(4)` ne couvre plus le meme ensemble de coups")


# ------------------------------------------------- (2)(3)(4) compte/position du tirage, gates

def test_toxic_hit_rolls_exactly_once_and_matches_the_predicted_roll(live_session, rpc, build_runner):
    """Un coup `Toxic` consomme EXACTEMENT un `next_bool(chance)`, et pose ssi ce tirage passe.

    Le clone du PRNG donne l'oracle du tirage AVANT l'appel ; on confronte (a) le nombre de tirages
    consommes (`call_count`), (b) le verdict de pose, (c) la TUILE posee = `Tiles(Target())` = la
    MainTile de la cible, (d) la SOURCE de l'effet = cette MEME tuile (selecteur source natif NUL ->
    `AddEffectBehaviour$$Execute` retombe sur la cible)."""
    state, board, _rid = _load(rpc, build_runner)
    att = _unit(state, CARRIER_VIS)
    if att is None:
        pytest.skip(f"{CARRIER_VIS} absent de l'etat offline")
    tgt = _any_enemy(state, att)
    if tgt is None:
        pytest.skip("aucun ennemi vivant")
    tile = _tile_of(state, board, tgt)
    assert tile is not None, "cible sans position -> Tiles(Target()) non resoluble"
    assert not state.effects.has_effect(tile, effect_type=CONTAMINATED), "tuile deja contaminee (pre-cond KO)"

    chance = int(GC.global_value(TOXIC_CHANCE_KEY))
    expect_placed, mt_expected = _oracle_after_one_roll(state, chance)
    out = _on_toxic_damage_ability(state, att, tgt, TOXIC_PROFILE)
    placed = state.effects.has_effect(tile, effect_type=CONTAMINATED)
    print(f"[toxic roll] chance={chance} predicted={expect_placed} placed={placed} "
          f"mti={state.rng.mti} want_mti={mt_expected[1]} out={out}")

    assert _mt_state(state.rng) == mt_expected, (
        f"etat MT apres le canal != etat apres EXACTEMENT un `next_bool({chance})` "
        f"(mti {state.rng.mti} vs {mt_expected[1]}) : le natif n'evalue le `Maybe` qu'au PREMIER coup de "
        f"la serie (`IsFirstHitInSeries` + ET court-circuitant) -- toute autre consommation desync le MT")
    assert placed == expect_placed, (
        f"verdict de pose {placed} != tirage predit {expect_placed} sur next_bool({chance}) : soit la "
        f"chance portee n'est pas celle du natif, soit le tirage n'est pas le 1er conso apres le coup")
    if expect_placed:
        assert out and out[0].get("placed_on_tile") == tile, (
            f"pose rapportee sur {out and out[0].get('placed_on_tile')} != tuile de la cible {tile} "
            f"(`Tiles(Target())` = MainTile de la cible)")
        srcs = {e.source for e in state.effects.active_effects(tile)
                if e.effect_type == CONTAMINATED}
        assert srcs == {tile}, (
            f"source de l'effet {srcs} != la TUILE {tile} : la surcharge `AddEffect` a 5 args passe un "
            f"selecteur SOURCE NUL, et `AddEffectBehaviour$$Execute` retombe alors sur la CIBLE")
    else:
        assert not out, f"tirage perdu mais pose rapportee : {out}"


def test_non_toxic_profile_places_nothing_and_rolls_nothing(live_session, rpc, build_runner):
    """Gate `DamageProfileHasTrait(OnToxic=4)` : un coup `Power` (profil SANS le trait) est un NO-OP
    STRICT -- aucune pose, et surtout AUCUN tirage (sinon le MT deriverait sur toute attaque non-Toxic)."""
    state, board, _rid = _load(rpc, build_runner)
    att = _unit(state, CARRIER_VIS)
    tgt = _any_enemy(state, att) if att is not None else None
    if att is None or tgt is None:
        pytest.skip("porteur/cible absents")
    assert DamageTrait.OnToxic.name not in ((GC.damage_profile("Power") or {}).get("Traits") or []), \
        "le profil `Power` porte OnToxic : ce test n'a plus de profil temoin"
    tile = _tile_of(state, board, tgt)

    mt0 = _mt_state(state.rng)
    out = _on_toxic_damage_ability(state, att, tgt, "Power")
    print(f"[toxic gate] out={out} mti={state.rng.mti} want={mt0[1]}")

    assert out == [], f"coup non-Toxic : pose rapportee {out}"
    assert _mt_state(state.rng) == mt0, \
        "coup non-Toxic : le MT a AVANCE (un tirage consomme -> desync garanti sur toute attaque)"
    assert not state.effects.has_effect(tile, effect_type=CONTAMINATED), "tuile contaminee par un coup Power"


def test_toxic_rolls_again_but_places_nothing_on_already_contaminated_tile(live_session, rpc,
                                                                          build_runner):
    """Tuile DEJA contaminee : le `Maybe` est evalue AVANT l'`AddEffect` dans l'arbre natif -> le tirage a
    LIEU (1 conso MT) mais la pose est un no-op (`AddEffectOperation` gate `already-present`)."""
    from engine.runner.operations.effects import AddEffectOperation
    state, board, _rid = _load(rpc, build_runner)
    att = _unit(state, CARRIER_VIS)
    tgt = _any_enemy(state, att) if att is not None else None
    if att is None or tgt is None:
        pytest.skip("porteur/cible absents")
    tile = _tile_of(state, board, tgt)
    AddEffectOperation.execute(state, source=tile, target=tile, effect_type=CONTAMINATED,
                               name=EffectType.Contaminated.name)
    assert state.effects.has_effect(tile, effect_type=CONTAMINATED), "pre-contamination KO"

    _verdict, mt_expected = _oracle_after_one_roll(state, int(GC.global_value(TOXIC_CHANCE_KEY)))
    out = _on_toxic_damage_ability(state, att, tgt, TOXIC_PROFILE)
    print(f"[toxic already] out={out} mti={state.rng.mti} want={mt_expected[1]}")

    assert _mt_state(state.rng) == mt_expected, (
        "le MT n'a pas avance d'EXACTEMENT un tirage sur une tuile deja contaminee : le natif evalue le "
        "`Maybe` AVANT la pose -- court-circuiter ce tirage desynchroniserait le MT")
    assert out == [], f"re-pose rapportee sur une tuile deja contaminee : {out}"


# ------------------------------------------------------------------- (5) agrement LIVE bout-en-bout

@pytest.mark.parametrize("a_units", [PLAIN_FOES, DAEMON_FOES], ids=["plain", "daemon"])
def test_toxic_normal_attack_agrees_with_live(live_session, rpc, build_runner, a_units):
    """REPLAY-DIFF : la MEME attaque normale (arme `Toxic` de `genesBiophagus`) jouee LIVE et OFFLINE sur
    le MEME etat MT -> memes PV de cible ET meme verdict de contamination de la tuile de la cible.

    C'est la confrontation qui repond au critere : « quand un coup de profil Toxic touche, le moteur
    offline declenche-t-il le meme canal que le natif, et avec quelle magnitude ? ». Le verdict de pose
    est piloté par le tirage `next_bool(chance)` : si la chance portee n'etait pas celle du natif, le
    verdict divergerait (le tirage tombe au MEME point de la sequence des deux cotes).

    DEUX ROSTERS ADVERSES, et le second est un CROISEMENT :
      - `plain`  : `necroWarden` -- defenseur SANS `Daemon`, un seul tirage neuf dans l'attaque (le notre) ;
      - `daemon` : `blackObliterator` -- defenseur `Daemon`, donc le jet de block `Daemon_ExtraBlock`
        (#221, `case-221-daemon-extrablock-rng.md`) ET le `Maybe` de 1203 tombent dans la MEME attaque.
        Ce sont les DEUX moities du meme etage RNG ; si l'un des deux tirages etait mal place ou compte,
        les PV de la cible ou le verdict de contamination divergeraient ICI. Meme Daemon que la garde
        #221 (`blackObliterator` : trait `Daemon` sans `Resilient`/`Terrifying` -> geometrie propre)."""
    rid = build_runner("777", extra=_build_args(a_units))["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    compared, placements = 0, 0
    for attempt in range(MAX_ATTACKS):
        drive = _drive_to_contact(rpc, rid, board)
        if drive is None:
            break                                        # plus de contact possible (porteur mort / fini)
        me_id, tgt_id, norm_id = drive

        # Etat OFFLINE + MT live, PUIS attaque des DEUX cotes (l'offline ne mute que sa copie).
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s1 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s1):
            pytest.skip("dumpRng KO")
        state = load_state(dv2, ob2, snap, board=board)
        if state.effects is None:
            pytest.skip("EffectsState absent")
        state.rng = _seed_rng(s1)
        tgt_tile = _tile_of(state, board, tgt_id)
        pre_live = _tiles_with(rpc, rid, board, CONTAMINATED)
        if tgt_tile is None or tgt_tile in pre_live:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue                                     # cas non discriminant : on retente au tour suivant

        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": me_id, "targetId": tgt_id,
            "abilityType": norm_id}}, 60)
        if not (_ok(res) and (res.get("actions") or [{}])[0].get("ok")):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        live_hp = next((u.get("hp") for u in (res.get("units") or [])
                        if u.get("squadId") == tgt_id), None)
        live_contaminated = tgt_tile in _tiles_with(rpc, rid, board, CONTAMINATED)

        runner = Runner(state).install_default_handlers(20)
        runner.apply(AttackUnitMessage(me_id, tgt_id))
        off_hp = state.get_entity(tgt_id).get_component(HealthComponent).hp
        off_contaminated = state.effects.has_effect(tgt_tile, effect_type=CONTAMINATED)
        last = runner.damage_handler.last or {}
        print(f"[toxic live/{a_units.split(',')[0]} #{attempt}] profile={last.get('profile')} "
              f"hp live={live_hp} off={off_hp} contaminated live={live_contaminated} "
              f"off={off_contaminated} tile={tgt_tile}")

        assert last.get("profile") == TOXIC_PROFILE, (
            f"le coup offline n'a pas le profil {TOXIC_PROFILE} (got {last.get('profile')}) -- la "
            f"selection d'arme a change, ce test ne confronte plus le canal OnToxic")
        if live_hp is not None:
            assert off_hp == live_hp, (
                f"PV cible offline {off_hp} != live {live_hp} : le coup lui-meme diverge, le verdict de "
                f"contamination n'est plus interpretable (desync MT en amont du tirage)")
        assert off_contaminated == live_contaminated, (
            f"contamination de la tuile {tgt_tile} : offline={off_contaminated} live={live_contaminated} "
            f"-- le canal `OnToxicDamageAbility` (1203) diverge (declenchement absent, chance differente, "
            f"ou tirage a la mauvaise position de la sequence MT)")
        compared += 1
        placements += int(live_contaminated)
        if placements:                                   # au moins une POSE confrontee -> discriminant
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    print(f"[toxic live] attaques confrontees={compared} poses observees={placements}")
    assert compared, "aucune attaque Toxic n'a pu etre confrontee au live (rien n'a ete valide)"
    assert placements, (
        f"{compared} attaques Toxic confrontees SANS aucune contamination live : le test ne prouve alors "
        f"que le NON-declenchement. Avec chance={GC.global_value(TOXIC_CHANCE_KEY)}%% c'est improbable "
        f"(mais deterministe par seed) -- change le seed du build si ce cas se fige")


def test_toxic_ranged_carrier_agrees_with_live(live_session, rpc, build_runner):
    """GENERALISATION du canal a un SECOND porteur, RANGED : `admecMarshall` (arme `Toxic` 1 coup,
    range 2). Le test (5) ci-dessus ne confronte que `genesBiophagus` (arme MELEE) -- or le gate natif
    est `DamageProfileHasTrait(OnToxic = 4)` sur le PROFIL du coup, jamais sur sa portee : si le canal
    n'etait cable que sur le chemin melee, ce test le verrait et l'autre non.

    Montage : `_on_hit_tile_effect_replay.replay_on_hit_tile_effect` (fixture NOMMEE, partagee avec
    les autres poses on-hit de tile-effect). Elle encapsule les deux pieges qui produisent des faux
    verts -- gate d'activation `toActivate` (et pas seulement `currentPlayer`) et « placer d'abord,
    tirer ensuite » -- et marque `noop=True` tout coup non joue cote live plutot que de le compter
    comme un ecart.

    Trois choses sont exigees, et la 3e est celle qui discrimine la MAGNITUDE :
      - PV de la cible identiques (le coup lui-meme ne diverge pas -> le reste est interpretable) ;
      - **etat MT identique apres l'attaque** : le canal consomme EXACTEMENT le meme nombre de
        tirages que le natif. C'est l'oracle de CONSOMMATION du couple
        `IsFirstHitInSeries() & Maybe(chance)` -- un tirage de trop ou de moins desynchronise tout
        ce qui suit dans la bataille ;
      - au moins UNE pose confrontee, sinon le test ne prouverait que le NON-declenchement."""
    conf, rid = replay_on_hit_tile_effect(
        rpc, build_runner, carrier_vis=RANGED_CARRIER_VIS, effect_type=CONTAMINATED,
        p_units=f"{RANGED_CARRIER_VIS},{ESCORT_VIS}", a_units=PLAIN_FOES)
    real = [c for c in conf if not c.get("noop")]
    print(f"[toxic ranged] confrontations={len(real)} (noop ignores={len(conf) - len(real)}) "
          f"poses={sum(1 for c in real if c['live_effect'])}")
    for c in real:
        print(f"[toxic ranged] profile={c['profile']} hits={c['hits']} hp live={c['live_hp']} "
              f"off={c['off_hp']} effect live={c['live_effect']} off={c['off_effect']} "
              f"mt_same={c['mt_same']} mti {c['mti_before']}->off {c['mti_off']}/live {c['mti_live']}")

    assert real, (f"aucune attaque de {RANGED_CARRIER_VIS} confrontee au live -- le canal ranged "
                  f"n'a rien valide (drive sans contact, ou toutes les tentatives no-op)")
    for c in real:
        assert c["profile"] == TOXIC_PROFILE, (
            f"le coup offline n'a pas le profil {TOXIC_PROFILE} (got {c['profile']}) -- la selection "
            f"d'arme a change ({RANGED_CARRIER_VIS} porte AUSSI une arme Physical), ce test ne "
            f"confronte plus le canal OnToxic")
        assert c["off_hp"] == c["live_hp"], (
            f"PV cible offline {c['off_hp']} != live {c['live_hp']} : le coup lui-meme diverge")
        assert c["off_effect"] == c["live_effect"], (
            f"contamination de la tuile {c['tile']} : offline={c['off_effect']} "
            f"live={c['live_effect']} -- le canal `OnToxicDamageAbility` (1203) diverge sur le "
            f"chemin RANGED (declenchement absent, chance differente, ou tirage mal place)")
        assert c["mt_same"], (
            f"etat MT divergent apres l'attaque (mti avant={c['mti_before']} off={c['mti_off']} "
            f"live={c['mti_live']}) : le canal ne consomme pas le MEME nombre de tirages que le "
            f"natif -- `IsFirstHitInSeries() & Maybe(chance)` doit en consommer EXACTEMENT UN par "
            f"serie de coups, et le ET natif COURT-CIRCUITE aux coups 2..N")
    assert any(c["live_effect"] for c in real), (
        f"{len(real)} attaques Toxic ranged confrontees SANS aucune contamination live : le test ne "
        f"prouve alors que le NON-declenchement (deterministe par seed -- changer le seed si ce cas "
        f"se fige)")


def _drive_to_contact(rpc, rid, board):
    """DRIVE les positions (doctrine : jamais « bloque par la geometrie de spawn ») : avance jusqu'a mon
    tour, rapproche le porteur des ennemis, et rend `(porteur, cible, abilityType normal)` des qu'un
    `attackPlan` LIVE existe — le MOVE de ce plan est joue ici, si bien qu'au retour le porteur est deja
    en position de frapper. Meme patron que `_drive_to_alignment` de `test_rad_bombardment_live`.
    None si aucun contact en 12 iterations."""
    from collections import deque

    def bfs(src):
        dist, q = {src: 0}, deque([src])
        while q:
            x = q.popleft()
            for n in board.neighbours(x):
                if n not in dist and (n == src or board.walkable(n)):
                    dist[n] = dist[x] + 1
                    q.append(n)
        return dist

    my = None
    for _ in range(12):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        units = dv.get("units") or []
        me = next((u for u in units if u.get("visualId") == CARRIER_VIS and u.get("alive")), None)
        if me is None:
            return None                                  # porteur mort -> plus rien a confronter
        if my is None:
            my = me.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        norm = next((ab for ab in (me.get("abilities") or []) if ab.get("kind") == "normal"), None)
        if norm is None:
            return None
        plan = next((ap for ap in (dv.get("attackPlans") or []) if ap.get("unitId") == me["id"]), None)
        ev = next((e for e in ((plan or {}).get("evals") or [])
                   if e.get("targetId") is not None and (e.get("ranked") or [])), None)
        if ev is not None:
            rk = ev["ranked"][0]
            if rk.get("col") is not None:                # move au contact (overwatch consomme AVANT dumpRng)
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": me["id"], "to": {"col": rk["col"], "row": rk["row"]}}}, 60)
            return me["id"], ev["targetId"], norm["id"]
        # pas de plan ce tour : on se rapproche de l'ennemi le plus proche, puis on rend la main.
        pos = (me.get("pos") or {})
        enemies = [u for u in units if u.get("owner") != my and u.get("alive") and (u.get("pos") or {})]
        if pos.get("col") is None or not enemies:
            return None
        tgt_pos = min(((u["pos"]["col"], u["pos"]["row"]) for u in enemies),
                      key=lambda p: abs(p[0] - pos["col"]) + abs(p[1] - pos["row"]))
        dist = bfs(board.id_at(*tgt_pos))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60) or {}
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == me["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist]
        if pool:
            col, row = reach[min(pool, key=lambda t: dist[t])]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": me["id"], "to": {"col": col, "row": row}}}, 60)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None


def _tiles_with(rpc, rid, board, effect_type):
    """Ids de tuiles portant `effect_type` (lecture LIVE via `tileMeta`)."""
    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    out = set()
    for t in (tm.get("tiles") or []):
        if any(e.get("effectType") == effect_type for e in (t.get("effects") or [])):
            tid = board.id_at(t["col"], t["row"])
            if tid is not None:
                out.add(tid)
    return out
