"""#1024-r2 -- CLIQUET de l'aura mythique `OnMyPosition_ExtraDamagePct` (1444), 100 % OFFLINE.

    EffectType 0x5a4 = 1444  OnMyPosition_ExtraDamagePct   MoW `astraOrdnanceBattery`

Owner-effect PERMANENT de l'ability MYTHIQUE `OnMyPosition` (`TriggeredAbilityType` 0x5ac = 1452),
posee a l'init par le patron `AOwnerEffectTriggeredAbility`. i2 : << Enemies that are adjacent to a
friendly Cadian Guardsman or a friendly Mythic character take +{extraDmgPct}% Damage from ranged
attacks by mythic characters. >>

C'est le TROISIEME membre de la famille des auras `ExtraDamagePct` de MoW (1442 `BlightedLand`,
1449 `MoreGitzOverEre`), et c'est exactement pour ca qu'il faut un cliquet SEPARANT : son
`$$CreateTargetSelector` RESSEMBLE a celui de 1449 et en differe sur DEUX etages qu'une recopie du
voisin de forme emporterait --

  * 1449 : `Filter(AllUnits, AmountIsEqualOrGreater(<amis Mythiques adjacents>, Direct(2)))`
           -> il faut DEUX voisins ;
  * 1444 : `AdjacentUnits( <amis Guardsman> + <amis Mythiques HEROS>, unique, 3 )`
           -> l'UNION est prise AVANT l'adjacence, donc UN SEUL voisin suffit, ET la branche B
              porte un etage `HeroUnits` que 1449 n'a pas.

Etage 1 -- ROUTAGE : la fabrique rend la classe portee, l'appariement se fait par le NOM PLEIN
           (l'ordinal 1444 est PARTAGE avec `TriggeredAbilityType.ThrillSeekers`), et la FACE
           native est `attacker` (elle decide du nombre de `Fix64.Round`).
Etage 2 -- le TRIGGER, conjoint par conjoint : `Enemies(Owner)` sur la cible,
           `AreFriends(Caster, EffectSource)` sur l'attaquant, `HasRarity(Caster, Mythic)`,
           `IsRangedAttack` -- chacun eteint SEUL, tri-etats compris.
Etage 3 -- le SELECTEUR : la branche A (Cadian Guardsman ami) et la branche B (Mythique HERO ami)
           SEPAREMENT, plus les contre-bras qui separent `HeroUnits` de `UnitsWithRarity`.
Etage 4 -- LE DISCRIMINANT ANTI-RECOPIE : sur un voisinage a UN SEUL ami Mythique, 1444 DOIT
           contribuer et 1449 DOIT se taire. Le meme profil, deux verdicts opposes.
Etage 5 -- la MAGNITUDE : paliers du gameconfig, multiplicateur du PORTEUR, et `GetAbilityState`
           du ctx qui PRIME sur le niveau de l'instance.
Etage 6 -- les DEUX faces CONSTRUISENT le 5e champ `is_hero` du profil de voisinage, et elles
           mesurent le MEME ensemble. MESURE en interceptant le foyer reel.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import pytest                                                                   # noqa: E402

import hexgeo                                                                   # noqa: E402
from engine.entities.pathfinding.board import Board                             # noqa: E402
from engine.entities.effect_type import EffectType                              # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType         # noqa: E402
from engine.entities.rarity import Rarity                                       # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait                         # noqa: E402
from engine.entities.effects.factory import (EffectFactory, EFFECT_CLASSES,     # noqa: E402
                                             ABILITY_INIT_OWNER_EFFECTS)
from engine.entities.effects.loki import extra_damage_aura as XDA               # noqa: E402
from engine.runner import damage_model as DM                                    # noqa: E402
from engine.runner.snapshot import load_state                                   # noqa: E402

DECLENCHEUR = {
    "chemins": (
        # La classe portee et son registre (EFFECT_CLASSES + ABILITY_INIT_OWNER_EFFECTS).
        "scripts/python/engine/entities/effects/loki/extra_damage_aura.py",
        "scripts/python/engine/entities/effects/factory.py",
        # Les DEUX faces qui CONSTRUISENT le profil de voisinage (etage 6) et leurs foyers.
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/engine/playbook/adjacency.py",
        # L'agregateur d'aura DEFENSE et le contrat des hooks + le predicat NOMME `IsRangedAttack`.
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/base.py",
        # Le canal de rarete en amont et le seed du porteur MoW.
        "scripts/python/engine/entities/rarity.py",
        "scripts/python/engine/entities/unit_context.py",
        "scripts/python/engine/runner/snapshot.py",
        # Le substrat de traits (`HeroUnits` = `UnitsWithTrait(0x10)`).
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/battle_query.py",
        # Les mirrors d'enum dont les ordinaux sont FIGES au site.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "L'etage 3 lit le GAMECONFIG (`OnMyPosition.constants.unitId` -> "
              "`astraSmnGuardsman.visualId`) et l'etage 5 ses paliers `extraDmgPct`, qui se "
              "periment SEPAREMENT du build ; le fichier fige des ORDINAUX au site (1444, 1452, "
              "`Rarity.Mythic = 5`, `UnitTrait.Hero = 0x10`), qu'un renumerotage rendrait faux "
              "sans toucher aucun des chemins ci-dessus.",
}

COLS, ROWS = 6, 6
#: `MOW_ID` = la MoW PORTEUSE (hors-plateau, aucune position) ; `ATT_ID` = l'attaquant DISTANCE ;
#: `FOE_ID` = la cible ; `HERO_ID` = un ami HERO Mythique voisin de la cible (branche B) ;
#: `GUARD_ID` = le summon `astraSmnGuardsman` voisin de la cible (branche A).
MOW_ID, ATT_ID, FOE_ID, HERO_ID, GUARD_ID = 90, 11, 20, 12, 14
ON_MY_POSITION = EffectType.OnMyPosition_ExtraDamagePct           # 0x5a4 = 1444
MORE_GITZ = EffectType.MoreGitzOverEre_ExtraDamagePct             # 0x5a9 = 1449
#: gameconfig : les paliers de la mythique `OnMyPosition` (`variables.extraDmgPct`).
PALIERS = [10, 13, 16, 20]
#: `VisualUnitIdFromUnitId("astraSmnGuardsman")` -- LU au gameconfig par l'etage 3.
GUARD_VIS = "astraNpc1Guardsman"
ENTITY_TYPE_UNIT, ENTITY_TYPE_MACHINE = 1, 6


def _tid(c: int, r: int) -> int:
    return c * ROWS + r + 1


def _board(elev_by_pos=None) -> Board:
    """Plateau plat, sauf les tuiles listees. `neighbours` porte la porte d'elevation NATIVE
    (`TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : `|dElev| < 2`), comme le substrat
    reel -- un board a couronne hex NUE ferait passer pour vert un port qui lit
    `hexgeo.distance == 1`."""
    ev = elev_by_pos or {}
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            e0 = int(ev.get((col, row), 0))
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS
                  and abs(int(ev.get((c, r), 0)) - e0) < 2]
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": e0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


# ============================== Etage 1 -- ROUTAGE ET FACE NATIVE ==============================

def _effet(source: int = MOW_ID, level=1, mult: int = 100):
    """Instance telle que la FABRIQUE la produit : ca exerce le ROUTAGE du registre en plus de la
    classe (`EffectFactory.create` rend un `BaseEffect` NU pour tout nom inconnu, et un `BaseEffect`
    nu a TOUS ses canaux muets -- le bras vrai le verrait)."""
    inst = EffectFactory.create({"name": ON_MY_POSITION.name, "effectType": int(ON_MY_POSITION),
                                 "source": source, "active": True}, mult, level)
    assert type(inst) is EFFECT_CLASSES[ON_MY_POSITION.name], (
        "la fabrique ne route plus %d vers sa classe portee" % int(ON_MY_POSITION))
    return inst


def test_le_registre_route_l_effet_par_son_NOM_PLEIN():
    assert EFFECT_CLASSES[ON_MY_POSITION.name] is XDA.OnMyPositionExtraDamagePctEffect
    assert EffectType(1444).name == "OnMyPosition_ExtraDamagePct"
    # L'ordinal 1444 est PARTAGE avec `TriggeredAbilityType.ThrillSeekers` : l'appariement passe par
    # le NOM PLEIN, jamais par l'entier. L'ability, elle, est `TriggeredAbilityType` 1452.
    assert TriggeredAbilityType(1444).name == "ThrillSeekers"
    assert TriggeredAbilityType(1452).name == "OnMyPosition"


def test_l_ability_pose_son_owner_effect_a_l_init():
    """`AOwnerEffectTriggeredAbility` (parent LU dans `frida/classes.tsv`) : `CreateTrigger` =
    `OnOwnerSpecificAbilityInit(this.AbilityType)`, `CreateBehaviour` = `AddEffect(GetEffectType(),
    ..., source = targets = Owner)`. Sans cette entree, l'effet n'existe sur AUCUN chemin offline."""
    assert ABILITY_INIT_OWNER_EFFECTS.get(XDA.ON_MY_POSITION_ABILITY) == [ON_MY_POSITION.name]
    assert XDA.ON_MY_POSITION_ABILITY == TriggeredAbilityType.OnMyPosition.name


def test_la_face_native_est_attaquant():
    """`...OnMyPosition_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack` = slot 0x16 ->
    accumulateur ATTAQUANT, malgre le trigger `get_OwnerIsTarget` et le canal PORT defenseur. Le
    nombre de `Fix64.Round` en depend (#437-r1-r1-r1) : ce n'est pas une etiquette."""
    assert XDA.OnMyPositionExtraDamagePctEffect.AURA_DEFENSE_MALUS_NATIVE_FACE == "attacker"


# ==================== Etage 2 -- le TRIGGER, conjoint par conjoint ============================

#: Voisinage MINIMAL qui satisfait la branche B : UN ami HERO Mythique adjacent a la cible.
#: `(uid, team, visual_id, rarity, is_hero)` -- le contrat du producteur.
PROFILS_B = ((HERO_ID, 1, "adeptCanoness", Rarity.Mythic, True),)
#: Voisinage qui satisfait la branche A SEULE : un Cadian Guardsman ami, NON hero, NON mythique.
PROFILS_A = ((GUARD_ID, 1, GUARD_VIS, Rarity.Common, False),)


def _ctx(profils=PROFILS_B, **over):
    """Le ctx que l'agregateur d'aura DEFENSE pose. `is_melee = False` = coup PROUVE distance
    (`runner/damage_model.py` pose `is_melee = (not is_ranged) if is_ranged is not None else None`)."""
    c = {"owner_id": MOW_ID, "owner_team": 1, "owner_pos": None,     # MoW : AUCUNE position
         "tgt_id": FOE_ID, "tgt_team": 2, "t_pos": (3, 3),
         "att_id": ATT_ID, "att_team": 1, "att_pos": (2, 3),
         "att_rarity": Rarity.Mythic, "is_melee": False,
         XDA.CTX_TGT_ADJACENT_UNIT_PROFILES: profils}
    c.update(over)
    return c


def test_bras_vrai():
    """Ami MYTHIQUE de la MoW attaquant A DISTANCE un ennemi voisin d'un ami Mythique HERO.

    ⚠ `owner_pos = None` : le bras vrai DOIT passer alors que le porteur n'a AUCUNE position --
    aucun etage du `$$CreateTargetSelector` ne lit la position du porteur, et c'est ce qui rend
    l'aura evaluable depuis une Machine of War (#999-r3-r1-r1)."""
    eb = _effet(level=1).create_aura_defense_damage_malus_for_ally(_ctx())
    assert eb is not None, "bras VRAI muet : le gate refuse pour une raison non mesuree"
    assert eb.kind == "PercentIncrease", "canal POURCENT (`EffectBonus.ForPercentIncrease`)"
    assert int(eb.value) == PALIERS[0]


def test_contre_bras_equipes():
    """DEUX filtres d'equipe, sur des unites DIFFERENTES : `Enemies(Owner, ...)` sur la CIBLE,
    `AreFriends(Caster@+0x48, EffectSource@+0x38)` sur l'ATTAQUANT."""
    e = _effet()
    assert e.create_aura_defense_damage_malus_for_ally(_ctx(tgt_team=1)) is None
    assert e.create_aura_defense_damage_malus_for_ally(_ctx(att_team=2)) is None
    assert e.create_aura_defense_damage_malus_for_ally(_ctx(owner_team=None)) is None
    assert e.create_aura_defense_damage_malus_for_ally(_ctx(tgt_team=None)) is None
    assert e.create_aura_defense_damage_malus_for_ally(_ctx(att_team=None)) is None


@pytest.mark.parametrize("rarete", [Rarity.Epic, Rarity.Legendary, Rarity.Common, None])
def test_contre_bras_rarete_de_l_attaquant(rarete):
    """`HasRarity( Caster@<DSLSelectors+0x48>, 5 = idun.meta.Rarity.Mythic )` -- le gate porte sur
    l'ATTAQUANT, ni sur la cible ni sur le porteur.

    ⚠ Le cas `None` est le plus important : c'est la degradation RESTRICTIVE nommee. Et le gate est
    INVISIBLE dans le regime par defaut du harnais (`rl_duel build` pose `targetRarity = 5` sur
    toute unite normalisee -> tout le monde est Mythic) : un port qui l'OUBLIERAIT serait d'accord
    avec le natif partout, sauf ici."""
    ctx = _ctx(att_rarity=rarete)
    assert _effet().create_aura_defense_damage_malus_for_ally(ctx) is None


@pytest.mark.parametrize("is_melee", [True, None])
def test_contre_bras_is_ranged_attack(is_melee):
    """`IsRangedAttack` -- tri-etat #106 : le coup MELEE (`is_melee = True`) et le coup de nature
    NON DECLAREE (`None`) FERMENT tous deux le gate. Le natif ne devine pas non plus : quand
    `GetAbilityAttackRangeType` ne tranche pas, `BattleQuery$$IsRangedAttack` rend FALSE.

    ⚠ C'est le conjoint que l'i2 rend le plus visible (<< from ranged attacks >>) et le plus facile
    a perdre : les DEUX jumeaux de la famille (1442, 1449) n'ont pas ce gate, 1449 ayant a sa place
    `IsMeleeAttack & IsNormalAttack` -- la POLARITE EXACTEMENT INVERSE."""
    ctx = _ctx(is_melee=is_melee)
    assert _effet().create_aura_defense_damage_malus_for_ally(ctx) is None


def test_pas_de_gate_IsNormalAttack_ni_de_gate_Hero_sur_l_attaquant():
    """Contre-epreuve du sens OPPOSE : deux gates que 1444 N'A PAS et qu'une recopie de 1449 ou une
    lecture litterale de l'i2 (<< by mythic **characters** >>) y ajouterait.

    Le decompile ne porte QUE `get_OwnerIsTarget & AreFriends & HasRarity & IsRangedAttack` : ni
    `IsNormalAttack`, ni `HeroUnits`/`HasTrait(Hero)` sur le CASTER. Le trait `Hero` n'apparait que
    dans la branche B du SELECTEUR, sur les VOISINS de la cible."""
    e = _effet()
    # `is_normal_attack` ABSENT du ctx (defaut) : le bras vrai passe deja (cf. `test_bras_vrai`).
    assert e.create_aura_defense_damage_malus_for_ally(
        _ctx(is_normal_attack=False)) is not None, "un gate `IsNormalAttack` a ete ajoute a tort"
    assert e.create_aura_defense_damage_malus_for_ally(
        _ctx(att_traits=frozenset())) is not None, "un gate de trait sur le CASTER a ete ajoute"


def test_le_porteur_qui_attaque_lui_meme_beneficie():
    """`AreFriends(Caster, EffectSource)` est VRAI quand `Caster == EffectSource`
    (`UnitExtensions$$IsFriend` n'ecarte PAS l'egalite). Ce cran interdit d'AJOUTER une exclusion
    `att_id == owner_id` par imitation des agregateurs d'aura ATTAQUE (qui, eux, en ont une)."""
    assert _effet().create_aura_defense_damage_malus_for_ally(
        _ctx(att_id=MOW_ID)) is not None


# ======================= Etage 3 -- le SELECTEUR, branche par branche ==========================

def test_le_visual_id_du_guardsman_vient_du_gameconfig():
    """`VisualUnitIdFromUnitId( Get( ConfigConstString(<config>, 0) ) )` -- DEUX lectures gameconfig
    enchainees (`OnMyPosition.constants.unitId`, puis `units.<id>.visualId`), jamais une chaine en
    dur : une constante de build codee en dur deviendrait une fausse verite au prochain build."""
    assert XDA._ability_unit_id_visual_id(XDA.ON_MY_POSITION_ABILITY) == GUARD_VIS
    # Le MEME foyer sert le jumeau 1449 -- un fork y ferait diverger deux mirrors du meme noeud.
    assert XDA._more_gitz_squig_visual_id() == XDA._ability_unit_id_visual_id(
        XDA.MORE_GITZ_OVER_ERE_ABILITY)


def test_branche_A_le_guardsman_seul_suffit():
    """`Friends(Owner, UnitsWithVisualId(<Cadian Guardsman>, 1 = OnlyAlive), 3)` -- un Guardsman
    ami voisin de la cible suffit, MEME s'il n'est ni Mythique ni HERO (c'est un `Summon`, dont les
    traits gameconfig sont `["Summon", "BattleFatigue"]` : il ne passerait JAMAIS `HeroUnits`)."""
    eb = _effet(level=3).create_aura_defense_damage_malus_for_ally(_ctx(PROFILS_A))
    assert eb is not None, "branche A muette"
    assert int(eb.value) == PALIERS[2]


def test_branche_B_le_hero_mythique_seul_suffit():
    """`UnitsWithRarity( Friends(Owner, HeroUnits(AllUnits, 3), 3), 5 = Mythic, 3 )`."""
    eb = _effet(level=2).create_aura_defense_damage_malus_for_ally(_ctx(PROFILS_B))
    assert eb is not None, "branche B muette"
    assert int(eb.value) == PALIERS[1]


def test_branche_B_separe_HeroUnits_de_UnitsWithRarity():
    """Les DEUX etages de la branche B, isoles l'un de l'autre. Un port qui n'en porterait qu'un
    passerait le bras vrai et l'un des deux contre-bras -- il faut les deux."""
    e = _effet()
    # Mythique mais PAS hero (un summon Mythique, p.ex.) -> `HeroUnits` l'ecarte.
    assert e.create_aura_defense_damage_malus_for_ally(
        _ctx(((HERO_ID, 1, "orksSmnSquig", Rarity.Mythic, False),))) is None
    # Hero mais PAS mythique -> `UnitsWithRarity(..., Mythic)` l'ecarte.
    assert e.create_aura_defense_damage_malus_for_ally(
        _ctx(((HERO_ID, 1, "adeptCanoness", Rarity.Legendary, True),))) is None
    # Rarete NON MESUREE -> gate FERME, jamais `Rarity.Common` en repli.
    assert e.create_aura_defense_damage_malus_for_ally(
        _ctx(((HERO_ID, 1, "adeptCanoness", None, True),))) is None


def test_contre_bras_selecteur_equipe_et_canaux_muets():
    """`Friends(Owner@+0x30, ...)` est commun aux DEUX branches, et le canal est TRI-ETAT."""
    e = _effet()
    # Hero Mythique ENNEMI du porteur -> `Friends` l'ecarte (branche B).
    assert e.create_aura_defense_damage_malus_for_ally(
        _ctx(((HERO_ID, 2, "adeptCanoness", Rarity.Mythic, True),))) is None
    # Guardsman ENNEMI du porteur -> meme etage, autre branche.
    assert e.create_aura_defense_damage_malus_for_ally(
        _ctx(((GUARD_ID, 2, GUARD_VIS, Rarity.Common, False),))) is None
    # Voisinage MESURE et VIDE : c'est une mesure, pas une ignorance.
    assert e.create_aura_defense_damage_malus_for_ally(_ctx(())) is None
    # Voisinage NON MESURE -> gate FERME.
    assert e.create_aura_defense_damage_malus_for_ally(_ctx(None)) is None
    assert e.create_aura_defense_damage_malus_for_ally({}) is None
    assert e.create_aura_defense_damage_malus_for_ally(None) is None


def test_ne_contribue_a_aucun_autre_canal():
    """Le natif n'implemente QUE `$$CreateEffectDamageBonusForAttack` (plus son
    `$$CreateTargetSelector`) : ni `$$CreateEffectDamageMalusForDefense`, ni `$$CreateDamageModifier`,
    ni `$$GetStatModification*`. Un port qui cablerait un second canal DOUBLERAIT la contribution."""
    e = _effet()
    c = _ctx()
    assert e.create_aura_attack_damage_bonus_for_ally(c) is None
    assert e.create_aura_attack_damage_malus_for_enemy(c) is None
    assert e.create_aura_attack_bonus(c) is None
    assert e.create_effect_damage_bonus_for_attack(False, None, None, False, True, None, c) is None
    assert e.create_effect_damage_malus_for_defense(True, None, c) is None


# ============ Etage 4 -- LE DISCRIMINANT : 1444 n'a AUCUN seuil de compte ======================

def test_un_seul_voisin_suffit_a_1444_la_ou_1449_en_exige_DEUX():
    """LE cran anti-recopie-du-voisin-de-forme, et il porte sur le MEME profil d'entree.

    1449 : `Filter(AllUnits, AmountIsEqualOrGreater(Friends(Owner, UnitsWithRarity(AdjacentUnits(
           <element>), Mythic, 3), 3), Direct(2)))` -> le SEUIL est DANS le selecteur.
    1444 : `AdjacentUnits( A + B, unique, 3 )` -> l'UNION est prise AVANT l'adjacence, il n'y a
           AUCUN `AmountIsEqualOrGreater`.

    Un port de 1444 recopie sur 1449 rendrait `None` ici ; un port de 1449 recopie sur 1444
    rendrait un bonus. Les deux fautes sont visibles sur cette unique paire d'assertions."""
    profil_un_seul = ((HERO_ID, 1, "adeptCanoness", Rarity.Mythic, True),)
    eb = _effet().create_aura_defense_damage_malus_for_ally(_ctx(profil_un_seul))
    assert eb is not None, "1444 exige a tort un SECOND voisin (seuil recopie de 1449)"

    mg = EffectFactory.create({"name": MORE_GITZ.name, "effectType": int(MORE_GITZ),
                               "source": MOW_ID, "active": True}, 100, 1)
    # Le ctx de 1449 : MEME voisinage, mais son trigger est `IsMeleeAttack & IsNormalAttack`.
    ctx_mg = _ctx(profil_un_seul, is_melee=True, is_normal_attack=True)
    assert mg.create_aura_defense_damage_malus_for_ally(ctx_mg) is None, (
        "1449 a perdu son seuil `AmountIsEqualOrGreater(..., Direct(2))`")
    # TEMOIN NON NUL : avec DEUX amis Mythiques, 1449 contribue -- le contre-bras ci-dessus ne
    # doit pas etre eteint par une autre cause (equipe, rarete, nature du coup).
    ctx_mg2 = _ctx(profil_un_seul + ((13, 1, "orksNob", Rarity.Mythic, True),),
                   is_melee=True, is_normal_attack=True)
    assert mg.create_aura_defense_damage_malus_for_ally(ctx_mg2) is not None, (
        "TEMOIN NUL : le montage de 1449 est eteint par autre chose que son seuil")


# ============================ Etage 5 -- la MAGNITUDE ==========================================

@pytest.mark.parametrize("niveau,attendu", list(zip([1, 2, 3, 4], PALIERS)))
def test_magnitude_par_palier(niveau, attendu):
    """`ConfigVar(0xa = extraDmgPct, GetAbilityState(this))` -- l'`AbilityState` BAKE a la pose,
    donc le palier TERTIAIRE 1..4 de la mythique."""
    eb = _effet(level=niveau).create_aura_defense_damage_malus_for_ally(_ctx())
    assert eb is not None and int(eb.value) == attendu


def test_magnitude_scale_par_le_multiplicateur_du_porteur():
    """`extraDmgPct` EST dans `variablesAffectedByRarityBonus` d'`OnMyPosition` -> le multiplicateur
    du PORTEUR mord. `AbilityConfiguration$$GetVariableForLevel` fait `round(base * mult / 100)`."""
    eb = _effet(level=4, mult=180).create_aura_defense_damage_malus_for_ally(_ctx())
    assert int(eb.value) == round(PALIERS[3] * 180 / 100) == 36


def test_ability_state_du_ctx_prime_sur_le_niveau_de_l_instance():
    """`GetAbilityState(effet)` = le couple TERTIAIRE du PORTEUR (#357). Sans le canal du ctx, on
    lirait le niveau des PASSIFS du porteur (50 sur tout runner normalise), donc le DERNIER palier
    -- une sur-application silencieuse (la faute de #357 / #1011)."""
    ctx = _ctx(tertiary_ability_state_of=lambda oid, ab: (
        (2, 100) if (oid == MOW_ID and ab == XDA.ON_MY_POSITION_ABILITY) else (None, 100)))
    # L'instance porte le palier 4 ; le ctx dit 2 -> c'est le CTX qui doit gagner.
    assert int(_effet(level=4).create_aura_defense_damage_malus_for_ally(ctx).value) == PALIERS[1]
    # Un porteur qui ne porte PAS cette ability -> repli NOMME sur le niveau de l'instance.
    ctx2 = _ctx(owner_id=999, tertiary_ability_state_of=lambda oid, ab: (None, 100))
    assert int(_effet(level=4).create_aura_defense_damage_malus_for_ally(ctx2).value) == PALIERS[3]


# ============ Etage 6 -- les DEUX faces CONSTRUISENT le champ `is_hero` ========================

def _dv():
    """`decisionView` MINIMAL : une MoW alliee PORTEUSE de 1444 (canal `.mows` SEPARE, `pos = null`),
    un attaquant, une cible, un ami HERO voisin de la cible, un summon Guardsman voisin aussi."""
    return {
        "currentPlayer": 1,
        "units": [
            {"id": ATT_ID, "visualId": "adeptRetributor", "alive": True, "team": 1, "owner": 1,
             "pos": {"col": 2, "row": 3}, "effects": []},
            {"id": FOE_ID, "visualId": "tyranTyrantGuard", "alive": True, "team": 2, "owner": 2,
             "pos": {"col": 3, "row": 3}, "effects": []},
            {"id": HERO_ID, "visualId": "adeptCanoness", "alive": True, "team": 1, "owner": 1,
             "pos": {"col": 3, "row": 2}, "effects": []},
            {"id": GUARD_ID, "visualId": GUARD_VIS, "alive": True, "team": 1, "owner": 1,
             "pos": {"col": 4, "row": 3}, "effects": []},
        ],
        "mows": [
            {"casterId": MOW_ID, "visualId": "astraOrdnanceBattery", "alive": True, "team": 1,
             "owner": 1, "pos": None, "slot": 1,
             "effects": [{"id": 8101, "name": ON_MY_POSITION.name,
                          "effectType": int(ON_MY_POSITION), "sourceId": MOW_ID,
                          "active": True, "targetIds": []}]},
        ],
        "effects": [
            {"id": 8101, "name": ON_MY_POSITION.name, "effectType": int(ON_MY_POSITION),
             "ownerId": MOW_ID, "source": MOW_ID, "active": True, "targetIds": []},
        ],
    }


def _snap(rarities=None):
    """`combatSnapshot` portant le canal `rarity` (#1039). REGIME SEPARANT par defaut : l'attaquant
    et l'ami HERO sont Mythiques, la cible et le Guardsman ne le sont pas."""
    r = {ATT_ID: Rarity.Mythic, FOE_ID: Rarity.Epic, HERO_ID: Rarity.Mythic,
         GUARD_ID: Rarity.Common, MOW_ID: Rarity.Mythic}
    r.update(rarities or {})
    vis = {ATT_ID: "adeptRetributor", FOE_ID: "tyranTyrantGuard", HERO_ID: "adeptCanoness",
           GUARD_ID: GUARD_VIS, MOW_ID: "astraOrdnanceBattery"}
    return {"rarityEnum": "idun.meta.Rarity",
            "units": [{"entityId": u, "visualId": vis[u],
                       "entityType": (ENTITY_TYPE_MACHINE if u == MOW_ID else ENTITY_TYPE_UNIT),
                       **({"rarity": int(r[u])} if r[u] is not None else {})}
                      for u in vis]}


def _obs():
    return {"units": [{"squadId": u, "hp": 5000, "hpMax": 5000}
                      for u in (ATT_ID, FOE_ID, HERO_ID, GUARD_ID)]}


def _state(elev=None, rarities=None):
    return load_state(_dv(), _obs(), _snap(rarities), board=_board(elev))


def _scene(elev=None):
    """La `Scene` de la face DECISION, montee sur le MEME `step_context` que le COMBAT."""
    from engine.playbook.scene import Scene, step_context
    from engine.entities.unit_context import UnitContext
    from engine.entities.pathfinding import board as PFB
    import gameconfig as GC
    dv = _dv()
    sctx = step_context({"mult_by_id": {}, "ablvl_by_id": {}, "ctx_by_id": {}}, dv)
    board = _board(elev)
    rar = {ATT_ID: Rarity.Mythic, FOE_ID: Rarity.Epic, HERO_ID: Rarity.Mythic,
           GUARD_ID: Rarity.Common}
    vis = {ATT_ID: "adeptRetributor", FOE_ID: "tyranTyrantGuard", HERO_ID: "adeptCanoness",
           GUARD_ID: GUARD_VIS}
    # ⚠ `traits` DOIT etre seede depuis le kit gameconfig, comme le fait `UnitContext.from_snapshot`
    # (`traits=list(cfg.get("traits") or [])`). `entity_trait_names(ctx, ...)` ne relit PAS le kit
    # quand un ctx existe -- il lit `ctx.traits` et n'y ajoute que le pseudo-trait de
    # grande-alliance. Un ctx sans traits rendrait donc `Hero` FAUX pour tout le monde : c'est un
    # vice de MONTAGE (mesure sur la premiere redaction de ce fichier : la face PREDICTION rendait
    # `is_hero = False` partout alors que la face COMBAT rendait `True`), pas un fork du port.
    # `traits_measured` reste FAUX : c'est bien la RECONSTRUCTION offline qu'on exerce.
    ctxs = {u: UnitContext(entity_id=u, visual_id=v, rarity=rar[u],
                           traits=list((GC.unit(v) or {}).get("traits") or []))
            for u, v in vis.items()}
    return Scene(ctx_by_id=ctxs, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                 vis_by_id=vis, units=sctx.get("units") or [],
                 hp_by_id=sctx.get("hp_by_id") or {}, pos_by_id=sctx.get("pos_by_id") or {},
                 team_by_id=sctx.get("team_by_id") or {}, eff_state=sctx["eff_state"],
                 board=board, elev_by_pos=PFB.elevations_by_pos(board))


def test_le_profil_de_voisinage_porte_is_hero_sur_les_DEUX_faces():
    """Un noeud natif (`HeroUnits` = `UnitsWithTrait(0x10)`), deux substrats -- ils doivent rendre
    le MEME ensemble ET le MEME classement `Hero`.

    ⚠ Threader un seul bout laisserait l'autre INERTE EN SILENCE : c'est le fork
    prediction/combat que #197 et #950-r2 ont paye."""
    combat = DM._adjacent_unit_profiles(_state(), FOE_ID)
    from engine.playbook.prediction._shared import _adjacent_unit_profiles as pred
    prediction = pred(_scene(), FOE_ID)
    assert combat is not None and prediction is not None
    assert {p[0] for p in combat} == {p[0] for p in prediction} == {ATT_ID, HERO_ID, GUARD_ID}
    hero_c = {p[0]: p[4] for p in combat}
    hero_p = {p[0]: p[4] for p in prediction}
    assert hero_c == hero_p, "les deux faces classent `Hero` differemment : %r vs %r" % (
        hero_c, hero_p)
    # TEMOIN NON NUL des DEUX cotes : il faut au moins un `True` ET au moins un `False`, sinon le
    # champ est constant et l'accord ne prouve rien.
    assert hero_c[HERO_ID] is True and hero_c[ATT_ID] is True, (
        "les heros ne sont pas classes `Hero` : %r" % (hero_c,))
    assert hero_c[GUARD_ID] is False, (
        "le summon `astraSmnGuardsman` est classe `Hero` -- `HeroUnits` ne separe plus rien")
    assert UnitTrait.Hero.name == "Hero" and int(UnitTrait.Hero) == 0x10


def test_ctx_aura_defense_combat_porte_le_profil_enrichi(monkeypatch):
    """MESURE en interceptant le foyer REEL : un ctx ecrit a la main mesurerait le test."""
    st = _state()
    vus = []
    reel = DM.aura_defense_damage_malus_from_units

    def _spy(carriers, ctx):
        vus.append((list(carriers or []), ctx))
        return reel(carriers, ctx)

    monkeypatch.setattr(DM, "aura_defense_damage_malus_from_units", _spy)
    DM.defender_modifiers(st, FOE_ID, 5000, is_melee=False, attacker_id=ATT_ID)
    assert vus, "l'agregateur d'aura DEFENSE n'a pas ete appele -- le montage ne mesure rien"
    carriers, ctx = vus[0]
    assert MOW_ID in [c[0] for c in carriers], (
        "la MoW porteuse n'entre pas dans l'univers de porteurs (regression de #999-r3-r1-r1)")
    assert ctx.get("att_rarity") == Rarity.Mythic, "`HasRarity(Caster, ...)` serait muet"
    assert ctx.get("is_melee") is False, "`IsRangedAttack` serait muet"
    assert callable(ctx.get("tertiary_ability_state_of")), "`GetAbilityState` serait muet"
    prof = ctx.get(XDA.CTX_TGT_ADJACENT_UNIT_PROFILES)
    assert prof is not None, "le substrat du `$$CreateTargetSelector` de 1444 serait muet"
    par_id = {p[0]: p for p in prof}
    assert set(par_id) == {ATT_ID, HERO_ID, GUARD_ID}
    assert par_id[HERO_ID][3] == Rarity.Mythic and par_id[HERO_ID][4] is True
    assert par_id[GUARD_ID][2] == GUARD_VIS, "le `visual_id` (branche A) n'est pas porte"


def test_ctx_aura_defense_prediction_porte_le_profil_enrichi(monkeypatch):
    """Pendant exact de l'etage precedent sur l'autre face."""
    from engine.playbook.prediction import _shared as SH
    from engine.entities.effects import DamageModifiers
    vus = []
    reel = SH.aura_defense_damage_malus_from_units

    def _spy(carriers, ctx):
        vus.append((list(carriers or []), ctx))
        return reel(carriers, ctx)

    monkeypatch.setattr(SH, "aura_defense_damage_malus_from_units", _spy)
    sc = _scene()
    SH._add_positional_and_defender_mods(DamageModifiers(), sc, ATT_ID, FOE_ID, False, (2, 3),
                                         (3, 3))
    assert vus, "l'agregateur d'aura DEFENSE (prediction) n'a pas ete appele"
    carriers, ctx = vus[0]
    assert MOW_ID in [c[0] for c in carriers], "la MoW porteuse n'entre pas cote PREDICTION"
    assert ctx.get("att_rarity") == Rarity.Mythic
    assert ctx.get("is_melee") is False
    prof = ctx.get(XDA.CTX_TGT_ADJACENT_UNIT_PROFILES)
    assert prof is not None
    par_id = {p[0]: p for p in prof}
    assert set(par_id) == {ATT_ID, HERO_ID, GUARD_ID}
    assert par_id[HERO_ID][4] is True and par_id[GUARD_ID][4] is False


def test_le_coup_reel_porte_la_contribution_de_1444():
    """Bout en bout COMBAT : le modifier DEFENSEUR construit par le foyer contient bien le
    `PercentIncrease` de 1444, verse dans l'accumulateur ATTAQUANT (face native `attacker`).

    DEUX contre-epreuves dans le MEME test, sur les deux axes que le regime par defaut du harnais
    rend degeneres : la rarete de l'ATTAQUANT (`Epic`) et la NATURE du coup (melee)."""
    from engine.services.damage_modifiers import get_multiplier_from_damage_bonus
    mods, _ = DM.defender_modifiers(_state(), FOE_ID, 5000, is_melee=False, attacker_id=ATT_ID)
    attendu = get_multiplier_from_damage_bonus(PALIERS[0])
    assert any(m == attendu for (m, _cap) in mods.pct_list), (
        "la contribution de 1444 n'atteint pas l'accumulateur ATTAQUANT : %r" % (mods.pct_list,))
    assert not any(m == attendu for (m, _cap) in mods.pct_list_defender), (
        "versee dans l'accumulateur DEFENSEUR : la face native serait fausse")
    mods2, _ = DM.defender_modifiers(_state(rarities={ATT_ID: Rarity.Epic}), FOE_ID, 5000,
                                     is_melee=False, attacker_id=ATT_ID)
    assert not any(m == attendu for (m, _cap) in mods2.pct_list), (
        "TEMOIN NON SEPARANT : l'attaquant Epic recoit quand meme le bonus")
    mods3, _ = DM.defender_modifiers(_state(), FOE_ID, 5000, is_melee=True, attacker_id=ATT_ID)
    assert not any(m == attendu for (m, _cap) in mods3.pct_list), (
        "TEMOIN NON SEPARANT : le coup MELEE recoit quand meme le bonus")
