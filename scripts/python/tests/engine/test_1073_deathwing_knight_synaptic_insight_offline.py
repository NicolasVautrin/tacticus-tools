"""#1073 -- CLIQUETS OFFLINE des deux passifs portes : `DeathwingKnight` (1510) et
`SynapticInsight` (1193).

Ce que ces tests GARDENT, et qui n'est garde nulle part ailleurs :

  1. **QUATRE ordinaux, QUATRE enums** -- `TriggeredAbilityType 1245`/`EffectType 1318` = Deathwing,
     `TriggeredAbilityType 1510`/`EffectType 1512` = DeathwingKnight, et `EffectType 1510` =
     `MastersOfManoeuvre`, sans rapport. Un rapprochement par l'ORDINAL ecrirait le mauvais effet ;
  2. **la CONFIG lue par l'effet** -- `DeathwingKnightEffect.ABILITY_ID == "DeathwingKnight"`. Les
     deux entrees de gameconfig sont DISTINCTES ; leurs 65 paliers coincident sur CE build, donc un
     port qui indexerait les deux sur `Deathwing` rendrait juste par accident, et deviendrait faux
     au premier reequilibrage -- **en silence**. C'est exactement ce que ce cliquet interdit ;
  3. **le fait que `DeathwingKnightAbility` n'override RIEN d'autre** que ses trois valeurs : le
     natif ne declare que `[GetEffectType (slot 35), .ctor]`, donc un `matches`/`execute_behaviour`
     propre serait une invention ;
  4. **l'ABSENCE de gate `IsNormalAttack` sur `SynapticInsight_ExtraHits`** -- ses TROIS voisins de
     forme du meme canal (`PowerTrip_FullHealth`, `VoltagheistField_ExtraHit`, `Waaagh_ExtraHits`)
     en portent un ; le recopier ici eteindrait le bonus sur toute attaque d'ability ;
  5. **le TRI-ETAT et l'INDEPENDANCE des deux disjoints** -- le natif rend un `op_BitwiseOr`, donc
     un disjoint dont le substrat manque se ferme SEUL, sans contaminer l'autre ;
  6. **l'ANCRE GEOMETRIQUE de l'arbre** : `AdjacentFriends` est la VARIANTE B, donc le centre est la
     CIBLE et la reference d'equipe le PORTEUR. Les deux surcharges ont la meme arite ; les
     intervertir ferait compter les amis autour du PORTEUR -- juste sur un montage ou les deux
     coincident, faux partout ailleurs ;
  7. **l'INSCRIPTION** des deux passifs a leur registre CANONIQUE (T pour l'un, O+E pour l'autre),
     et les ORDINAUX ECRITS AU SITE (`probe_313` compare le mirror au build ; il redevient vert des
     qu'on regenere le mirror apres un renumerotage, alors que la valeur ecrite au site, elle,
     aurait change).
"""
from __future__ import annotations

import sys
from pathlib import Path

_PY = Path(__file__).resolve().parents[2]
if str(_PY) not in sys.path:
    sys.path.insert(0, str(_PY))

from engine.entities.ability_constant_type import AbilityConstantType          # noqa: E402
from engine.entities.effect_type import EffectType                             # noqa: E402
from engine.entities.effects.factory import (ABILITY_INIT_OWNER_EFFECTS,       # noqa: E402
                                             EFFECT_CLASSES)
from engine.entities.effects.loki.deathwing import (ABILITY_ID as DW_ABILITY,  # noqa: E402
                                                    ABILITY_ID_KNIGHT,
                                                    DeathwingEffect,
                                                    DeathwingKnightEffect)
from engine.entities.effects.loki.norn_crown import (                          # noqa: E402
    CTX_TEAM_SYNAPSE_POSITIONS)
from engine.entities.effects.loki.synaptic_insight import (                    # noqa: E402
    CTX_ADJACENT_TYRANID, SynapticInsightExtraHitsEffect,
    adjacent_tyranid_friend_trigger)
from engine.entities.effects.magnitude import ability_var                      # noqa: E402
from engine.entities.selectors.accessors import Owner, Subject, Target         # noqa: E402
from engine.entities.selectors.units import AdjacentFriends                    # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType        # noqa: E402
from engine.entities.unit_faction import UnitFaction                           # noqa: E402
from engine.entities.unit_selection_type import UnitSelectionType              # noqa: E402
from engine.runner.operations.triggers.dispatch.registry import ABILITY_TRIGGERS  # noqa: E402
from engine.runner.operations.triggers.loki.deathwing import (                 # noqa: E402
    DeathwingAbility, DeathwingKnightAbility)

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/deathwing.py",
        "scripts/python/engine/entities/effects/loki/synaptic_insight.py",
        "scripts/python/engine/entities/effects/loki/norn_crown.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_constant_type.py",
        "scripts/python/engine/entities/unit_faction.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/triggers.py",
        "scripts/python/engine/runner/operations/triggers/loki/deathwing.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/services/effect_bonus.py",
    ),
    # `build: True` -- la constante `extraHit` et les DEUX tables `extraDmg`/`dmgReduction` sont
    # LUES au gameconfig, pas ecrites ici.
    "build": True,
    "toujours": False,
    "raison": "Les deux ports, les trois mirrors d'enum dont ce fichier FIGE les ordinaux ecrits au "
              "site, l'arbre `Any(AdjacentFriends(...), HasFaction(...))` et ses deux selecteurs, "
              "le foyer `IsInTeamSynapseRange` partage avec #1011, les trois registres, et le "
              "gameconfig d'ou viennent la constante et les deux tables de variables.",
}

#: ORDINAUX MESURES A LA CONVERSION (build `rnca9r7q6c`). Figes ICI parce que `probe_313` compare
#: le MIRROR au BUILD : il redevient vert des qu'on regenere le mirror apres un renumerotage,
#: pendant que la valeur ecrite au site, elle, a change en silence (cf. CLAUDE.md).
DEATHWING_TRIGGERED = 1245           # `TriggeredAbilityType.Deathwing`        = 0x4dd
DEATHWING_EFFECT = 1318              # `EffectType.Deathwing`                  = 0x526
KNIGHT_TRIGGERED = 1510              # `TriggeredAbilityType.DeathwingKnight`  = 0x5e6
KNIGHT_EFFECT = 1512                 # `EffectType.DeathwingKnight`            = 0x5e8
SYNAPTIC_TRIGGERED = 1193            # `TriggeredAbilityType.SynapticInsight`  = 0x4a9
SYNAPTIC_EFFECT = 1231               # `EffectType.SynapticInsight_ExtraHits`  = 0x4cf
FACTION_TYRANIDS = 12                # `UnitFaction.Tyranids`                  = 0xc
CONST_EXTRA_HIT = 0x2b               # `AbilityConstantType.extraHit`
SEL_ALIVE_TARGETABLE = 3             # `UnitSelectionType.OnlyAliveAndTargetable`


def _si_effect():
    return SynapticInsightExtraHitsEffect({"name": "SynapticInsight_ExtraHits",
                                           "effectType": SYNAPTIC_EFFECT})


def _ctx(*, adjacent=None, synapse=None, is_melee=False):
    """Contexte per-coup du canal COUPS (le `board` d'`attack_hits_with_modifiers`).

    `adjacent` / `synapse` = `True` / `False` / `None` (= NON MESURE). Le disjoint synapse est
    arme par une POSITION d'emetteur a distance 2 de la cible -- jamais par un booleen, pour que
    le foyer partage `norn_crown._in_team_synapse_range` soit REELLEMENT traverse."""
    c = {"is_melee": is_melee, "att_id": 1, "team_by_id": {1: 0}, "t_pos": (3, 4)}
    if adjacent is not None:
        c[CTX_ADJACENT_TYRANID] = adjacent
    if synapse is not None:
        # (5,5) est a distance hex 2 de (3,4) sur la grille odd-q du port (LU sur `MC1_67`),
        # (0,0) est hors de la bulle -- deux positions, deux verdicts.
        c[CTX_TEAM_SYNAPSE_POSITIONS] = {0: (((5, 5),) if synapse else ((0, 0),))}
    return c


# --------------------------------------------------------------- 1. ordinaux ECRITS AU SITE

def test_ordinaux_figes_a_la_conversion():
    assert int(TriggeredAbilityType.Deathwing) == DEATHWING_TRIGGERED
    assert int(EffectType.Deathwing) == DEATHWING_EFFECT
    assert int(TriggeredAbilityType.DeathwingKnight) == KNIGHT_TRIGGERED
    assert int(EffectType.DeathwingKnight) == KNIGHT_EFFECT
    assert int(TriggeredAbilityType.SynapticInsight) == SYNAPTIC_TRIGGERED
    assert int(EffectType.SynapticInsight_ExtraHits) == SYNAPTIC_EFFECT
    assert int(UnitFaction.Tyranids) == FACTION_TYRANIDS
    assert int(AbilityConstantType.extraHit) == CONST_EXTRA_HIT
    assert int(UnitSelectionType.OnlyAliveAndTargetable) == SEL_ALIVE_TARGETABLE


def test_les_quatre_ordinaux_ne_se_rapprochent_pas_par_leur_valeur():
    """`EffectType 1510` n'est PAS `DeathwingKnight` -- c'est `MastersOfManoeuvre`. Le seul canal ou
    la faute serait visible est le NOM ; l'ordinal, lui, ne ment pas mais ne discrimine pas."""
    assert EffectType(KNIGHT_TRIGGERED).name == "MastersOfManoeuvre"
    assert EffectType(KNIGHT_TRIGGERED).name != "DeathwingKnight"
    # ... et symetriquement, `TriggeredAbilityType 1512` n'est pas `DeathwingKnight` non plus.
    assert int(TriggeredAbilityType.DeathwingKnight) != KNIGHT_EFFECT


# ------------------------------------------------------- 2. DeathwingKnight -- le jumeau STRICT

def test_effet_knight_est_la_meme_classe_native_a_la_config_pres():
    """`frida/classes.tsv` ne porte AUCUNE `DeathwingKnightEffect` : les deux `EffectType` sont
    servis par le MEME `DeathwingEffect`, avec deux `triggeringAbilityType`. Cote port, la seule
    chose qui distingue les deux classes est donc la CLE DE CONFIG."""
    assert issubclass(DeathwingKnightEffect, DeathwingEffect)
    assert DeathwingEffect.ABILITY_ID == DW_ABILITY == "Deathwing"
    assert DeathwingKnightEffect.ABILITY_ID == ABILITY_ID_KNIGHT == "DeathwingKnight"
    # AUCUN comportement propre : tout attribut redefini par la fille serait une invention.
    propres = {k for k in vars(DeathwingKnightEffect)
               if not k.startswith("__") and k != "ABILITY_ID"}
    assert propres == set(), "la fille redefinit autre chose que sa cle de config : %s" % propres


def test_les_deux_configs_de_gameconfig_sont_DISTINCTES():
    """Elles coincident sur CE build (memes 65 paliers), et c'est precisement le piege : indexer les
    deux sur `Deathwing` rendrait JUSTE aujourd'hui et FAUX au premier reequilibrage. On garde donc
    que les deux entrees EXISTENT chacune de son cote, pas qu'elles different."""
    for cle in ("Deathwing", "DeathwingKnight"):
        for var in ("extraDmg", "dmgReduction"):
            v = ability_var(cle, var, 50)
            assert v, "gameconfig %s.%s illisible au niveau 50 (lu: %r)" % (cle, var, v)


def test_ability_knight_n_override_que_ses_trois_valeurs():
    """Le natif declare exactement `[GetEffectType (slot 35), .ctor]` : trigger, behaviour et
    `GetEffect` viennent du parent. Un `matches`/`execute_behaviour` propre serait une invention."""
    assert issubclass(DeathwingKnightAbility, DeathwingAbility)
    assert DeathwingKnightAbility.EFFECT_TYPE == KNIGHT_EFFECT
    assert DeathwingAbility.EFFECT_TYPE == DEATHWING_EFFECT
    assert DeathwingKnightAbility.EFFECT_NAME == "DeathwingKnight"
    assert DeathwingKnightAbility.ABILITY_KEY == "DeathwingKnight"
    assert int(DeathwingKnightAbility.TRIGGERED_ABILITY_ID) == KNIGHT_TRIGGERED
    # meme `On(9 = Attack)` que le parent, et AUCUNE methode propre.
    assert DeathwingKnightAbility.event_id == DeathwingAbility.event_id
    for meth in ("matches", "execute_behaviour"):
        assert getattr(DeathwingKnightAbility, meth) is getattr(DeathwingAbility, meth), \
            "%s est redefinie alors que le natif ne la declare pas" % meth


def test_knight_inscrit_a_ses_registres_canoniques():
    assert ABILITY_TRIGGERS.get("DeathwingKnight") == [DeathwingKnightAbility]
    assert EFFECT_CLASSES.get("DeathwingKnight") is DeathwingKnightEffect
    # ... sans avoir DEPLACE le parent.
    assert EFFECT_CLASSES.get("Deathwing") is DeathwingEffect


# ------------------------------------------------------- 3. SynapticInsight -- l'arbre et le gate

def test_arbre_du_premier_disjoint_ancre_sur_la_CIBLE():
    """`AdjacentFriends(unit = Owner, unitTile = Target, unique)` = VARIANTE B : le 3e argument
    natif est l'ANCRE GEOMETRIQUE. Cote port, `center` = `Target()` et `reference` = `Owner()`.
    Les intervertir compterait les amis autour du PORTEUR -- indiscernable sur un montage ou les
    deux coincident, faux partout ailleurs."""
    tree = adjacent_tyranid_friend_trigger()
    assert type(tree).__name__ == "Any"
    sel = tree.list_selector
    assert isinstance(sel, AdjacentFriends)
    assert isinstance(sel.center, Target), "l'ancre geometrique doit etre la CIBLE"
    assert isinstance(sel.reference, Owner), "la reference d'equipe doit etre le PORTEUR"
    assert int(sel.selection_type) == SEL_ALIVE_TARGETABLE
    assert int(sel.radius.evaluate(None)) == 1        # ring-1 : `AdjacentTiles`
    pred = tree.trigger
    assert type(pred).__name__ == "HasFaction"
    assert isinstance(pred.unit, Subject), "le predicat lit l'ELEMENT COURANT (`It@+0x68`)"
    assert int(pred.faction) == FACTION_TYRANIDS


def test_magnitude_est_une_CONSTANTE():
    """`ConfigConst(0x2b = extraHit)` -- ni indexee par niveau, ni scalee par la rarete."""
    assert ability_var("SynapticInsight", "extraHit", is_constant=True) == 2


def test_gate_ranged_tri_etat():
    e = _si_effect()
    # nature PROUVEE distance + disjoint arme -> bonus
    assert e.create_effect_hits_bonus_for_attack(True, _ctx(adjacent=True)).value == 2
    # nature MELEE -> rien (`IsRangedAttack` est FAUX)
    assert e.create_effect_hits_bonus_for_attack(True, _ctx(adjacent=True, is_melee=True)) is None
    # nature NON DECLAREE -> rien (tri-etat : on ne fabrique pas une attaque a distance)
    assert e.create_effect_hits_bonus_for_attack(True, _ctx(adjacent=True, is_melee=None)) is None
    # aucun contexte du tout -> rien
    assert e.create_effect_hits_bonus_for_attack(True, None) is None


def test_AUCUN_gate_is_normal_attack():
    """Les TROIS voisins de forme de ce canal (`PowerTrip_FullHealth`, `VoltagheistField_ExtraHit`,
    `Waaagh_ExtraHits`) portent `IsNormalAttack` ; le corps natif de celui-ci ne le porte PAS. Le
    recopier eteindrait le bonus sur toute attaque d'ability de la famille ATTACK."""
    e = _si_effect()
    b = e.create_effect_hits_bonus_for_attack(False, _ctx(adjacent=True))
    assert b is not None and b.value == 2


def test_les_deux_disjoints_sont_INDEPENDANTS():
    """Le natif joint par `op_BitwiseOr` : chacun suffit, et un disjoint dont le substrat manque se
    ferme SEUL. C'est ce qu'ont mesure les mutants `ctxAdj` / `ctxSynapse` du probe live -- chacun
    n'a fait DIVERGER que SON regime."""
    e = _si_effect()
    # A seul
    assert e.create_effect_hits_bonus_for_attack(True, _ctx(adjacent=True, synapse=False)).value == 2
    # B seul
    assert e.create_effect_hits_bonus_for_attack(True, _ctx(adjacent=False, synapse=True)).value == 2
    # les deux
    assert e.create_effect_hits_bonus_for_attack(True, _ctx(adjacent=True, synapse=True)).value == 2
    # aucun des deux, tous deux MESURES -> rien
    assert e.create_effect_hits_bonus_for_attack(True, _ctx(adjacent=False, synapse=False)) is None


def test_substrat_absent_FERME_le_disjoint_sans_contaminer_l_autre():
    e = _si_effect()
    # A non mesure, B vrai -> le bonus TIENT (le `None` de A ne contamine pas B)
    assert e.create_effect_hits_bonus_for_attack(True, _ctx(adjacent=None, synapse=True)).value == 2
    # B non mesure, A vrai -> idem
    assert e.create_effect_hits_bonus_for_attack(True, _ctx(adjacent=True, synapse=None)).value == 2
    # les DEUX non mesures -> rien (degradation RESTRICTIVE, jamais un bonus invente)
    assert e.create_effect_hits_bonus_for_attack(True, _ctx()) is None


def test_synapse_le_sujet_n_est_jamais_son_propre_emetteur():
    """`GetSurroundingUnits(target, range, friendsOf: null, includeCenter: FALSE)` -- l'emetteur pose
    SUR la cible ne compte pas (`0 < d <= 2`). Cran du foyer partage `norn_crown` (#1011), rejoue
    ici parce que ce port en est un SECOND consommateur."""
    e = _si_effect()
    c = _ctx()
    c[CTX_TEAM_SYNAPSE_POSITIONS] = {0: ((3, 4),)}        # exactement SUR la cible -> d == 0
    assert e.create_effect_hits_bonus_for_attack(True, c) is None
    c[CTX_TEAM_SYNAPSE_POSITIONS] = {0: ((5, 5),)}        # d == 2 -> dans la bulle
    assert e.create_effect_hits_bonus_for_attack(True, c).value == 2


def test_synaptic_inscrit_a_ses_registres_canoniques():
    """Canal **O** (`ABILITY_INIT_OWNER_EFFECTS`) + canal **E** (`EFFECT_CLASSES`), et surtout PAS
    `ABILITY_TRIGGERS` : le trigger natif est `On(AbilityInit) & get_OwnerIsActor`, pas un
    evenement de combat."""
    assert ABILITY_INIT_OWNER_EFFECTS.get("SynapticInsight") == ["SynapticInsight_ExtraHits"]
    assert EFFECT_CLASSES.get("SynapticInsight_ExtraHits") is SynapticInsightExtraHitsEffect
    assert "SynapticInsight" not in ABILITY_TRIGGERS
