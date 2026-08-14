"""#570-r5 -- L'ORDRE DE SEEDING : l'instance d'effet naissait AVANT l'`AbilityState` de son owner.

CRITERE BINAIRE, pose avant la methode :

    « Une unite SANS `UnitConfiguration` (toute unite INVOQUEE) voit-elle ses effets materialises
      AVEC le niveau/multiplicateur que publie `unitAbilityStates` -- ou avec le neutre 100/None ? »

CE QUE LE NATIF FAIT, ET DANS QUEL ORDRE. `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$
DefaultEffectBuilder` **COPIE** l'`AbilityStateReference` du poseur dans le `EffectComponent` de
l'entite-effet a la POSE (`+0x18`..`+0x38`) ; a la lecture,
`IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference` relit CE champ et rien d'autre --
l'effet ne consulte JAMAIS son porteur. L'etat doit donc EXISTER avant l'effet. Cote port,
`load_state` materialisait les effets (`_load_stats_and_effects`) AVANT de consommer le canal
`unitAbilityStates` (`_load_passive_abilities`), donc l'effet naissait avec le neutre et le gardait.

CE QUE CE FICHIER GARDE, ETAGE PAR ETAGE (chacun peut rougir seul) :

  [1] la REGLE de priorite (`_ability_state_with_channel`) -- table, y compris le TRI-ETAT
      (« un canal muet n'ecrit RIEN ») ;
  [2] l'instance d'effet CAPTEE d'une unite sans config porte le niveau du canal, et le CONTRE-BRAS
      (`ability_states=False`) montre qu'elle ne le porterait pas sans lui -- sans ce contre-bras,
      un 50 arrive par une autre voie passerait pour une mesure ;
  [3] l'unite CONFIGUREE suit le CANAL quand il MESURE, et les DEUX TABLES (ctx et instance)
      portent la MEME chose ;
  [4] l'OWNER-EFFECT pose a l'init (`IdunBattle.Operations.InitializeActorAbilitiesOperation$$
      Execute`, boucle ABILITIES) -- l'etage que #570-r5 nomme -- porte lui aussi le niveau, alors
      qu'il est materialise A L'INTERIEUR de `_load_stats_and_effects` ;
  [5] ANTI-VACUITE ARITHMETIQUE : les deux bras ne rendent pas la meme magnitude
      (`dmgReduction[1] = 5` contre `dmgReduction[50] x 180 %`), sinon rien n'aurait ete mesure ;
  [6] l'ETAT FINAL du `ctx` est INCHANGE par le deplacement -- il vaut exactement ce que
      `_load_passive_abilities` ecrivait en aval. C'est le RAYON DE SOUFFLE : hors de la fenetre
      « entre la naissance des effets et la fin de `load_state` », rien ne bouge ;
  [7] les DEUX PLACEMENTS d'une reduction plate (PRE- et POST-percage) ne coincident PAS sur le
      regime mesure -- c'est ce qui autorise la mesure live a TRANCHER le placement au lieu de
      constater un accord degenere.

Mesure live : `python scripts/python/probe_570r1_ramshackle.py`. RE : `docs/rl/case-570-grot-tank.md`.
ASCII only. Aucune VA en dur.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from engine.entities.effect_type import EffectType                          # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType     # noqa: E402
from engine.runner.components import StatsComponent                         # noqa: E402
from engine.runner.snapshot import (PASSIVE_HIERARCHY, _ability_state_with_channel,  # noqa: E402
                                    load_state, passive_ability_state_by_unit)

#: Ce qui doit changer pour que ce fichier puisse changer de verdict (#486-r12).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des conftest et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        # PROPRE A CE FICHIER. Foyers load-bearing, pour la relecture :
        # `engine/runner/snapshot.py` (l'ORDRE dans `load_state`, `_ability_state_with_channel`,
        # `passive_ability_state_by_unit`), `engine/runner/operations/spawn.py`
        # (`_seed_ability_owner_effects`), `engine/entities/effects/factory.py`
        # (`ABILITY_INIT_OWNER_EFFECTS`, `EFFECT_CLASSES`), `engine/entities/effects_state.py`
        # (`baked_ability_state`), `engine/entities/effects/loki/ramshackle.py`,
        # `engine/services/damage_prediction.py` + `damage_modifiers.py` (le placement de l'etage 7).
        "scripts/python/engine/**/*.py",
        "scripts/python/*.py",
        # Le KIT du summon (etage 0) et les PALIERS de `dmgReduction` (etage 5) sont LUS du
        # gameconfig, qui vit dans la seed BC.
        "data/seed-bc.json",
    ),
    # Aucun ordinal d'enum n'est ecrit en dur ici (les deux ids sont derives des mirrors), mais les
    # DEUX enums en cause sont apparies par NOM au build : un renumerotage change ce que ce fichier
    # compare.
    "build": True,
    "toujours": False,
    "raison": "Verdicts figes : l'ORDRE de `load_state` (l'`AbilityState` du canal "
              "`unitAbilityStates` existe AVANT que les effets de son owner ne soient "
              "materialises), la PRIORITE du canal sur le proxy `unitConfig` et son TRI-ETAT "
              "(#1049-r1), l'ACCORD des deux tables (ctx et `abstate_by_id`), les DEUX voies de "
              "materialisation (capture et pose a l'init), l'etat FINAL du ctx, et "
              "la NON-COINCIDENCE des deux placements sur le regime que le probe joue. Aucun "
              "runner, aucune session Frida.",
}

#: Le summon du Grot Tank (`1057 GrotTank`) -- `passiveAbilities: ["Ramshackle"]`, LU du gameconfig
#: par le test lui-meme (assertion d'etage 0), jamais suppose.
SUMMON_VID = "orksNpc3GrotTank"
#: Une unite ORDINAIRE, qui a une `UnitConfiguration` -- le contre-bras de la garde d'ecrasement.
CONFIGURED_VID = "orksNob"
RAMSHACKLE_ABILITY = int(TriggeredAbilityType.Ramshackle)          # 0x445 -- la CONFIG
RAMSHACKLE_EFFECT = int(EffectType.Ramshackle_DmgReduction)        # 0x442 -- l'EFFET (autre enum)
#: Un effet SANS classe dediee (`BaseEffect`) porte par l'unite CONFIGUREE : il n'a aucun canal de
#: contribution, mais il PORTE l'`AbilityState` bake -- c'est le temoin de l'etage 3 cote INSTANCE.
TEMOIN_EFFECT = int(EffectType.IgnoreBattleFatigue)
SUMMON_ID, CONFIGURED_ID = 98, 77
#: Ce que le canal publie pour le summon : le niveau/multiplicateur de son SUMMONER (rank 17).
CHAN_LEVEL, CHAN_MULT = 50, 180


def _triggered_row(ability_id: int, level: int, mult: int) -> dict:
    """Une entree `triggered` du payload `unitAbilityStates`, forme EXACTE du capteur : `raw[0]` =
    l'id de `TriggeredAbilityType`, `raw[10]` = la HIERARCHIE (2 = passif du kit)."""
    raw = [ability_id] + [0] * 10
    raw[10] = PASSIVE_HIERARCHY
    return {"raw": raw, "level": level, "mult": mult}


def _payload(*rows) -> dict:
    return {"units": list(rows)}


def _unit_row(uid: int, vid: str) -> dict:
    return {"id": uid, "visualId": vid, "alive": True, "team": 1, "owner": 1,
            "pos": {"col": 1, "row": 1}, "effects": []}


def _snapshot_row(uid: int, vid: str, unit_config) -> dict:
    return {"entityId": uid, "entityType": 1, "visualId": vid,
            "stats": {"health": 5000, "movement": 3, "turnsStarted": 1},
            "healthMax": 5000, "traits": [], "unitFlags": [], "unitConfig": unit_config}


def _load(capture_effet: bool, ability_states):
    """`load_state` sur un etat a DEUX unites : le SUMMON (aucune `UnitConfiguration` -- le capteur
    rend litteralement `{"error": "config null"}`) et une unite CONFIGUREE.

    `capture_effet` : l'effet 1090 est-il DEJA dans `decisionView.units[].effects` ? Les deux voies
    de materialisation sont distinctes et doivent etre gardees separement -- la CAPTURE
    (`EffectsState.seed`) et la POSE A L'INIT (`_seed_ability_owner_effects`)."""
    effs = ([{"name": "Ramshackle_DmgReduction", "effectType": RAMSHACKLE_EFFECT,
              "remaining": 0, "level": 1, "source": SUMMON_ID}] if capture_effet else [])
    summon = _unit_row(SUMMON_ID, SUMMON_VID)
    summon["effects"] = effs
    configuree = _unit_row(CONFIGURED_ID, CONFIGURED_VID)
    # TEMOIN de l'etage 3 cote INSTANCE : l'unite CONFIGUREE porte elle aussi un effet capte, dont
    # elle est la SOURCE. Sans lui, une garde inversee (« le canal ecrase toujours ») resterait
    # invisible -- elle ne mord pas sur le ctx (garde propre) mais bien sur `abstate_by_id`.
    configuree["effects"] = [{"name": "IgnoreBattleFatigue", "effectType": TEMOIN_EFFECT,
                              "remaining": 0, "level": 1, "source": CONFIGURED_ID}]
    decision = {"currentPlayer": 1, "units": [summon, configuree]}
    observe = {"units": [{"squadId": u["id"], "hp": 5000, "hpMax": 5000}
                         for u in decision["units"]]}
    snapshot = {"units": [
        # `{"error": "config null"}` = ce que le capteur rend VERBATIM pour une unite invoquee.
        _snapshot_row(SUMMON_ID, SUMMON_VID, {"error": "config null"}),
        _snapshot_row(CONFIGURED_ID, CONFIGURED_VID,
                      {"visualId": CONFIGURED_VID, "level": 50, "passiveAbilityLevel": 50,
                       "activeAbilityLevel": 50, "abilityVariablesMultiplier": 100}),
    ]}
    return load_state(decision, observe, snapshot, ability_states=ability_states)


def _canal() -> dict:
    """Le canal COMPLET : le summon porte l'`AbilityState` de son summoner, l'unite configuree en
    porte un AUTRE -- volontairement different de son `unitConfig`, pour que l'etage 3 puisse
    montrer que la garde tient."""
    return _payload(
        {"entityId": SUMMON_ID,
         "triggered": [_triggered_row(RAMSHACKLE_ABILITY, CHAN_LEVEL, CHAN_MULT)]},
        {"entityId": CONFIGURED_ID,
         "triggered": [_triggered_row(RAMSHACKLE_ABILITY, 7, 999)]})


def _instance(state, uid: int, effect_type: int):
    for e in (state.effects.by_unit.get(int(uid)) or []):
        if int(e.effect_type or -1) == int(effect_type):
            return e
    return None


# ---------------------------------------------------------------------------------------------
# [0] LE MONTAGE EST-IL CE QU'IL PRETEND ? (sans ca, tous les etages qui suivent sont vides)
# ---------------------------------------------------------------------------------------------
def test_etage0_le_kit_du_summon_porte_bien_le_passif():
    import gameconfig as GC
    from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS
    assert "Ramshackle" in ((GC.unit(SUMMON_VID) or {}).get("passiveAbilities") or []), (
        "le montage repose sur `%s.passiveAbilities` -- s'il ne porte plus `Ramshackle`, les "
        "etages 4 et 5 mesureraient le vide" % SUMMON_VID)
    assert ABILITY_INIT_OWNER_EFFECTS.get("Ramshackle") == ["Ramshackle_DmgReduction"]


# ---------------------------------------------------------------------------------------------
# [1] LA REGLE DE PRIORITE -- l'AbilityState de l'INSTANCE prime sur le proxy `unitConfig`
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("config,canal,attendu", [
    # le TROU : aucune config -> le canal repond, mult COMPRIS
    ((100, None, None), (50, 180), (180, 50, None)),
    # ⚠ #1049-r1 -- LE CANAL PRIME, MEME SUR UNE VALEUR PRESENTE DANS LE `unitConfig`.
    # Ce cas gardait l'inverse (« une valeur MESUREE n'est JAMAIS ecrasee »), sur la premisse
    # que les deux canaux sont deux vues d'une meme mesure. Ils ne le sont pas :
    # `IdunBattle.Entities.Factories.UnitFactory$$Build` BAKE l'`AbilityState` dans chaque
    # instance d'ability, et c'est lui -- pas la configuration -- que
    # `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` consomme ; tandis que
    # le capteur RE-RESOUT une configuration par
    # `IdunBattle.Core.Services.BattleQuery$$GetUnitConfig(VisualId)`, jointure N->1 qui peut
    # designer une AUTRE entree de `BC.Units[]`. Mesure : `bloodNpc1Intercessor:45` porte le
    # `visualId` de son jumeau summon, d'ou `unitConfig = (100, 1, 1)` contre `(65, 200)` sur
    # l'instance.
    ((100, 50, 50), (7, 999), (999, 7, 50)),
    # TRI-ETAT -- canal muet : strictement rien. C'est ce qui distingue « l'autorite prime »
    # de « le canal ecrase toujours », y compris a vide.
    ((100, None, None), None, (100, None, None)),
    ((100, 50, 50), None, (100, 50, 50)),
    # le canal peut ne pas porter de multiplicateur : on garde celui de la config
    ((123, None, None), (50, None), (123, 50, None)),
    # `activeAbilityLevel` n'est jamais INVENTE : le canal de hierarchie 2 ne le porte pas.
    # C'est la BORNE connue du fix -- cet axe est seede separement (`_load_active_ability_state`).
    ((100, None, 42), (50, 180), (180, 50, 42)),
    ((100, 50, 42), (7, 999), (999, 7, 42)),
])
def test_etage1_regle_de_priorite(config, canal, attendu):
    assert _ability_state_with_channel(config, canal) == attendu


# ---------------------------------------------------------------------------------------------
# [2] L'INSTANCE CAPTEE, ET SON CONTRE-BRAS
# ---------------------------------------------------------------------------------------------
def test_etage2_instance_captee_porte_le_niveau_du_canal():
    avec = _instance(_load(True, _canal()), SUMMON_ID, RAMSHACKLE_EFFECT)
    assert avec is not None, "l'effet capte n'a pas ete materialise -- le montage est vide"
    assert (avec.ability_level, avec.ability_variables_multiplier) == (CHAN_LEVEL, CHAN_MULT)


def test_etage2b_contre_bras_sans_canal_l_instance_reste_neutre():
    """CE QUI PROUVE QUE L'ETAGE 2 MESURE. `ability_states=False` est le refus EXPLICITE du canal :
    l'instance doit retomber sur le neutre. Si elle portait 50/180 ici aussi, l'etage 2 ne dirait
    rien du canal."""
    sans = _instance(_load(True, False), SUMMON_ID, RAMSHACKLE_EFFECT)
    assert sans is not None
    assert (sans.ability_level, sans.ability_variables_multiplier) == (None, 100)


# ---------------------------------------------------------------------------------------------
# [3] L'UNITE CONFIGUREE SUIT LE CANAL, ET LES DEUX TABLES RESTENT D'ACCORD
# ---------------------------------------------------------------------------------------------
def test_etage3_unite_configuree_suit_le_canal():
    """#1049-r1 -- INVERSION ASSUMEE, et voici ce qui l'etablit.

    Cet etage gardait « le `unitConfig` gagne ». La premisse etait que les deux canaux mesurent la
    MEME chose par deux voies ; elle est FAUSSE. Le `unitConfig` du capteur n'est pas la
    configuration qui a monte l'entite : `readUnitConfig` la RE-RESOUT par
    `IdunBattle.Core.Services.BattleQuery$$GetUnitConfig(VisualId)`, dont le corps compare
    `+0x10` puis `IdunBattle.Configuration.UnitConfiguration$$get_ConfigId` sur `BC.Units[]` --
    jointure N->1. Le canal, lui, lit l'`AbilityState` BAKE dans l'instance par
    `IdunBattle.Entities.Factories.UnitFactory$$Build`, celui-la meme que
    `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` consomme.

    RAYON DE SOUFFLE MESURE (`probe_1049r1_autorite_ability_state.py`, MC1_67/777) : sur 8 heros
    ORDINAIRES du pool, les trois canaux concordent 8/8 -- l'inversion ne mord QUE la ou le proxy
    ment. Ici le canal porte (7, 999) DELIBEREMENT contre un `unitConfig` a (50, 100), pour que
    l'etage ait quelque chose a montrer."""
    st = _load(True, _canal())
    ctx = st.get_entity(CONFIGURED_ID).get_component(StatsComponent).ctx
    assert (ctx.passive_ability_level, ctx.ability_variables_multiplier) == (7, 999), (
        "le canal porte (7, 999) pour cette unite ; le `unitConfig` porte (50, 100). "
        "L'`AbilityState` de l'INSTANCE fait autorite -- le `unitConfig` n'en est qu'un proxy.")


def test_etage3b_les_deux_tables_portent_la_meme_chose():
    """L'INVARIANT QUI COMPTE, et il survit a l'inversion -- il en sort meme RENFORCE. Le ctx et
    `abstate_by_id` sont DEUX tables ; c'est `abstate_by_id` qui bake l'`AbilityState` dans les
    effets, donc un ecart entre elles serait SILENCIEUX. Un fix pose sur une seule des deux les
    ferait diverger : c'est exactement ce que cet etage interdit, avant comme apres."""
    st = _load(True, _canal())
    ctx = st.get_entity(CONFIGURED_ID).get_component(StatsComponent).ctx
    inst = _instance(st, CONFIGURED_ID, TEMOIN_EFFECT)
    assert inst is not None, "le temoin n'a pas ete materialise -- l'etage est vide"
    assert (inst.ability_level, inst.ability_variables_multiplier) == (7, 999)
    assert (inst.ability_level, inst.ability_variables_multiplier) == (
        ctx.passive_ability_level, ctx.ability_variables_multiplier), (
        "le ctx et l'instance DIVERGENT -- une des deux tables suit le proxy et l'autre l'instance")


def test_etage3c_un_canal_MUET_ne_touche_a_rien():
    """CONTRE-BRAS DE L'ETAGE 3, et il est OBLIGATOIRE : sans lui, « le canal prime » serait
    indistinguable de « le canal ecrase, mesure ou pas ». Sans payload, l'unite configuree doit
    porter EXACTEMENT son `unitConfig`."""
    st = _load(True, False)
    ctx = st.get_entity(CONFIGURED_ID).get_component(StatsComponent).ctx
    assert (ctx.passive_ability_level, ctx.ability_variables_multiplier) == (50, 100)
    inst = _instance(st, CONFIGURED_ID, TEMOIN_EFFECT)
    assert inst is not None
    assert (inst.ability_level, inst.ability_variables_multiplier) == (50, 100)


# ---------------------------------------------------------------------------------------------
# [4] L'OWNER-EFFECT POSE A L'INIT -- l'etage exact que #570-r5 nomme
# ---------------------------------------------------------------------------------------------
def test_etage4_owner_effect_pose_a_l_init_porte_le_niveau():
    """`capture_effet=False` : AUCUN effet dans `decisionView` -- la seule voie possible est
    `_seed_ability_owner_effects`, appele DEPUIS `_load_stats_and_effects`, donc AVANT le seed
    d'aval. C'est precisement la fenetre ou l'ordre mordait."""
    st = _load(False, _canal())
    inst = _instance(st, SUMMON_ID, RAMSHACKLE_EFFECT)
    assert inst is not None, ("l'owner-effect n'a pas ete pose -- `_seed_ability_owner_effects` "
                              "ne voit plus le passif du kit")
    assert (inst.ability_level, inst.ability_variables_multiplier) == (CHAN_LEVEL, CHAN_MULT)


def test_etage4b_contre_bras_owner_effect_sans_canal():
    """MEME contre-bras que 2b, et il ne rend PAS la meme chose : cette voie-ci thread
    explicitement `ctx.passive_ability_level`, dont le DEFAUT est `0` (et non `None`). C'est
    exactement le `0` que `probe_570r1_ramshackle` lisait avant cette tranche, et
    `RamshackleDmgReductionEffect` le traite comme le niveau 1 (`self.ability_level is not None`
    -> `dmgReduction[0] = 5`). On le FIGE tel quel : la difference des deux `None`/`0` est
    porteuse, la confondre effacerait la trace de la voie empruntee."""
    inst = _instance(_load(False, False), SUMMON_ID, RAMSHACKLE_EFFECT)
    assert inst is not None
    assert (inst.ability_level, inst.ability_variables_multiplier) == (0, 100)


# ---------------------------------------------------------------------------------------------
# [5] ANTI-VACUITE ARITHMETIQUE -- les deux bras ne rendent pas le meme nombre
# ---------------------------------------------------------------------------------------------
def test_etage5_les_deux_bras_rendent_des_magnitudes_differentes():
    """Le niveau ne compte que s'il CHANGE la magnitude. `Physical` a `PiercingRatio` 1 <= 30, donc
    le gate de `Ramshackle` PASSE et le canal repond des deux cotes."""
    avec = _instance(_load(True, _canal()), SUMMON_ID, RAMSHACKLE_EFFECT)
    sans = _instance(_load(True, False), SUMMON_ID, RAMSHACKLE_EFFECT)
    b_avec = avec.create_effect_damage_malus_for_defense(damage_profile="Physical")
    b_sans = sans.create_effect_damage_malus_for_defense(damage_profile="Physical")
    assert b_avec is not None and b_sans is not None, "le gate doit PASSER sur un profil a 1 %"
    assert b_avec.value != b_sans.value, (
        "les deux bras rendent la MEME magnitude -- l'etage 2 serait vrai sans rien mesurer")
    assert b_avec.value > b_sans.value, "le palier 50 doit etre au-dessus du palier 1"


# ---------------------------------------------------------------------------------------------
# [6] RAYON DE SOUFFLE -- l'ETAT FINAL du ctx est celui d'AVANT le deplacement
# ---------------------------------------------------------------------------------------------
def test_etage6_etat_final_du_ctx_inchange():
    """Le deplacement ne devait rien changer HORS de la fenetre. La reference est ce que le seed
    d'aval (`_load_passive_abilities`) ecrivait : `passive_ability_state_by_unit`, la MEME table.
    Si les deux divergeaient, le port se serait mis a lire un autre niveau apres `load_state`."""
    st = _load(True, _canal())
    # ⚠ L'ATTENDU N'EST PAS DERIVE DE LA FONCTION SOUS TEST. Mesure adversariale : en le tirant de
    # `passive_ability_state_by_unit`, une mutation qui vide le canal vidait AUSSI l'attendu -- la
    # boucle ne tournait plus et le test passait A VIDE. On ecrit donc les couples EN CLAIR, et on
    # verifie separement que le parsing les rend bien.
    assert passive_ability_state_by_unit(_canal()) == {SUMMON_ID: (CHAN_LEVEL, CHAN_MULT),
                                                       CONFIGURED_ID: (7, 999)}, (
        "le PARSING du canal a change -- l'attendu ci-dessous ne decrirait plus le meme etat")
    attendu = {SUMMON_ID: (CHAN_LEVEL, CHAN_MULT),   # aucune config -> le canal repond
               CONFIGURED_ID: (7, 999)}              # #1049-r1 : le canal PRIME sur le proxy
    for uid, couple in attendu.items():
        ctx = st.get_entity(uid).get_component(StatsComponent).ctx
        assert (ctx.passive_ability_level, ctx.ability_variables_multiplier) == couple, (
            "u%d : l'etat FINAL du ctx a bouge -- le deplacement devait etre invisible ICI" % uid)
    # et le seed d'aval a bien tourne : il compte la MEME unite, il ne l'a simplement pas reecrite
    assert (st.ability_states_seed or {}).get("seededPassives") == 2


# ---------------------------------------------------------------------------------------------
# [7] LE PLACEMENT EST DECIDABLE -- les deux modeles ne coincident pas
# ---------------------------------------------------------------------------------------------
#: L'armure du Grot Tank sur le montage du probe (`MC1_67`, seed 777), et une reduction au palier
#: 50 x 180 %. Les deux `brut` sont pris SOUS l'armure : c'est le regime que le probe joue, celui
#: ou `GetDamageWithPiercing` retient la branche PERCAGE.
ARMURE, REDUCTION = 3193, 499


def _pre_et_post(brut: int, pierce: int, armure: int, reduction: int) -> tuple:
    """Les deux placements, calcules par le MEME etage natif
    (`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$
    GetDamageWithPiercing` = `max(0, d - armure, d x percage/100)`) :

      * PRE-percage  = ce que fait le port (`for_subtraction` -> `flat_reductions` ->
        `mods.additive`, consomme AVANT le percage) ;
      * POST-percage = la reduction retranchee du degat FINAL.

    Rend `(nu, pre, post)` -- `nu` est le degat SANS reduction, l'ancre qui rend les deux modeles
    comparables."""
    from engine.services.damage_modifiers import DamageModifiers
    from engine.services.damage_prediction import apply_pierce_and_modifiers
    mods = DamageModifiers()
    mods.additive -= reduction
    pre = int(apply_pierce_and_modifiers(brut, pierce, armure, mods, attacker_additive_pre=True))
    nu = int(apply_pierce_and_modifiers(brut, pierce, armure, DamageModifiers(),
                                        attacker_additive_pre=True))
    return nu, pre, max(0, nu - reduction)


@pytest.mark.parametrize("brut,pierce", [(1800, 1), (2400, 30)])
def test_etage7_pre_et_post_percage_ne_coincident_pas(brut, pierce):
    """LE REGIME OU LA MESURE TRANCHE : degat brut SOUS l'armure, donc la branche retenue est
    `d x percage/100` et une reduction PRE-percage sort DILUEE d'un facteur `percage/100`, tandis
    qu'une reduction POST-percage sort entiere. Ce test FIGE la non-coincidence -- sans elle,
    l'accord live ne trancherait rien."""
    assert brut - ARMURE <= 0, ("hors regime : a `brut > armure` c'est la branche SOUSTRACTIVE qui "
                                "gagne, et les deux placements se confondent (cf. le test suivant)")
    nu, pre, post = _pre_et_post(brut, pierce, ARMURE, REDUCTION)
    assert nu > 0, "regime DEGENERE : sans reduction le degat est deja nul"
    assert pre != post, ("les deux placements rendent %d -- sur ce regime la mesure live ne "
                         "pourrait pas trancher" % pre)


def test_etage7b_le_regime_armure_est_degenere_et_c_est_une_LIMITE():
    """LA LIMITE, ECRITE PLUTOT QUE SUBIE. Des que la branche SOUSTRACTIVE gagne
    (`d - armure > d x percage/100`), l'etage percage est l'IDENTITE sur l'axe additif : une
    reduction PRE et une reduction POST rendent EXACTEMENT le meme nombre. Un montage tombe dans ce
    regime rendrait un accord qui ne prouve RIEN sur le placement -- c'est pour cela que le probe
    choisit une cible a forte armure. Ce test existe pour qu'on ne re-lise jamais cet accord-la
    comme une confirmation."""
    nu, pre, post = _pre_et_post(9000, 30, ARMURE, REDUCTION)
    assert nu == 9000 - ARMURE, "le montage ne place pas la branche soustractive en tete"
    assert pre == post, "ce regime DOIT etre degenere -- s'il ne l'est plus, la limite a bouge"


# ---------------------------------------------------------------------------------------------
# [8] DEUX ECRITURES, UN SEUL BAC -- la « divergence de famille » n'en est plus une
# ---------------------------------------------------------------------------------------------
def test_etage8_for_subtraction_et_for_addition_negatif_atterrissent_au_MEME_endroit():
    """CE QUE CE TEST EMPECHE DE RECROIRE. La docstring de `ramshackle.py` presentait un CHOIX de
    famille entre deux jumeaux : `HolyDuel_DmgReduction` (`for_addition(False, -v)`, cru
    POST-percage) et `PsychicFortress_DmgReduction` (`for_subtraction(False, v)`, PRE-percage).
    Depuis #462-r4b-r1, l'`Addition@+0x10` du DEFENSEUR est versee dans le MEME accumulateur
    PRE-percage que `flat_reductions` (`AttackDamageOperation._apply_defender_flat_reductions`) --
    les deux ecritures rendent donc EXACTEMENT le meme nombre. Il n'y avait plus de fourche a
    trancher cote port ; ce que la mesure live tranche est le placement NATIF, contre le modele
    POST-percage construit a la main."""
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.services.damage_modifiers import DamageModifiers, add_modifier
    from engine.services.effect_bonus import for_addition, for_subtraction
    sorties = []
    for eb in (for_subtraction(False, REDUCTION), for_addition(False, -REDUCTION)):
        mods, def_mods = DamageModifiers(), DamageModifiers()
        add_modifier(def_mods, eb)
        AttackDamageOperation._apply_defender_flat_reductions(mods, def_mods)
        sorties.append((mods.additive, def_mods.additive))
    assert sorties[0] == sorties[1] == (-float(REDUCTION), 0.0), (
        "les deux ecritures ne tombent plus dans le meme bac : %r" % (sorties,))
