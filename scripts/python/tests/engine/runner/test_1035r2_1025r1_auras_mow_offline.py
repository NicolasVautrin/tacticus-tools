"""#1035-r2 / #1025-r1 -- CLIQUET des DEUX auras `ExtraDamagePct` de MACHINE OF WAR, 100 % OFFLINE.

Les deux effets portes ici sont les owner-effects PERMANENTS de deux abilities MYTHIQUES :

    EffectType 0x5a2 = 1442  BlightedLand_ExtraDamagePct        MoW `deathCrawler`     (#1035-r2)
    EffectType 0x5a9 = 1449  MoreGitzOverEre_ExtraDamagePct     MoW `orksRukkatrukk`   (#1025-r1)

Ils implementent le MEME slot natif (`$$CreateEffectDamageBonusForAttack`) et atterrissent sur des
canaux de port OPPOSES, parce que leurs `$$CreateTargetSelector` projettent sur des populations
opposees : 1442 sur les AMIS de la MoW (beneficiaire = l'ATTAQUANT), 1449 sur ses ENNEMIS
(beneficiaire = la CIBLE DU COUP). Confondre les deux serait SILENCIEUX -- l'effet se contenterait
de ne jamais fire.

Etage 1 -- ROUTAGE : la fabrique rend bien les deux classes portees, et la FACE native de 1449 est
           `attacker` (elle decide du nombre de `Fix64.Round`, donc c'est arithmetique).
Etage 2 -- 1442 : UN bras vrai et QUATRE contre-bras, chacun eteignant UN etage du selecteur. Un
           bras vrai seul ne prouverait rien (le gate pourrait etre ferme ailleurs) ; un
           contre-bras seul non plus (il pourrait etre eteint par le mauvais etage).
Etage 3 -- 1442 : la MAGNITUDE suit les paliers du gameconfig ET le multiplicateur du PORTEUR
           (`extraDmgPct` est dans `variablesAffectedByRarityBonus`). Une magnitude figee passerait
           le bras vrai sans rien prouver.
Etage 4 -- 1449 : les DEUX branches du selecteur (Squig ami adjacent / >= 2 amis Mythiques
           adjacents) SEPAREMENT, plus un contre-bras par conjoint du trigger.
Etage 5 -- les ctx que les DEUX faces CONSTRUISENT portent les cles neuves. MESURE en interceptant
           le foyer reel, jamais en relisant le source ni en fabriquant un dict a la main.
Etage 6 -- le substrat d'adjacence de 1449 est le MEME sur les deux faces, et il porte la porte
           d'elevation du natif (`|dElev| < 2`) : un voisin hexagonal separe d'une marche N'EST PAS
           adjacent. Sans ce cran, un `hexgeo.distance == 1` passerait tous les autres etages.

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
from engine.entities.rarity import Rarity                                       # noqa: E402
from engine.entities.effects.factory import EffectFactory, EFFECT_CLASSES       # noqa: E402
from engine.entities.effects.loki import extra_damage_aura as XDA               # noqa: E402
from engine.runner import damage_model as DM                                    # noqa: E402
from engine.runner.snapshot import load_state                                   # noqa: E402

DECLENCHEUR = {
    "chemins": (
        # Les DEUX classes portees et leur registre.
        "scripts/python/engine/entities/effects/loki/extra_damage_aura.py",
        "scripts/python/engine/entities/effects/factory.py",
        # Les DEUX faces qui construisent les ctx (etage 5) et leurs foyers d'adjacence (etage 6).
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/playbook/prediction/_shared.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/engine/playbook/adjacency.py",
        # Les agregateurs eux-memes et le contrat des hooks d'aura.
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effects/base.py",
        # Le canal de rarete en amont (sans lui les deux gates sont muets) et le seed du porteur.
        "scripts/python/engine/entities/rarity.py",
        "scripts/python/engine/entities/unit_context.py",
        "scripts/python/engine/runner/snapshot.py",
        # L'arbre DSL du noeud d'adjacence et sa primitive.
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/battle_query.py",
        # Les mirrors d'enum dont les ordinaux sont FIGES au site.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/unit_selection_type.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "Les etages 3 et 4 lisent le GAMECONFIG (`BlightedLand.extraDmgPct`, "
              "`MoreGitzOverEre.extraDmgPct` et `constants.unitId` -> `orksSmnSquig.visualId`), qui "
              "se perime SEPAREMENT du build ; le fichier fige des ORDINAUX au site (1442, 1449, "
              "`EffectType.Contaminated = 0x4dc`, `Rarity.Mythic = 5`, "
              "`UnitSelectionType.OnlyAliveAndTargetable = 3`), qu'un renumerotage rendrait faux "
              "sans toucher aucun des chemins ci-dessus.",
}

COLS, ROWS = 6, 6
#: `MOW_ID` = la Machine of War PORTEUSE (hors-plateau, aucune position) ; `ATT_ID` = l'attaquant ;
#: `FOE_ID` = la cible ; `M1`/`M2` = deux amis Mythiques de la MoW, voisins de la cible (branche B) ;
#: `SQUIG_ID` = le summon `orksSmnSquig` voisin de la cible (branche A).
MOW_ID, ATT_ID, FOE_ID, M1_ID, M2_ID, SQUIG_ID = 90, 11, 20, 12, 13, 14
BLIGHTED = EffectType.BlightedLand_ExtraDamagePct                 # 0x5a2 = 1442
MORE_GITZ = EffectType.MoreGitzOverEre_ExtraDamagePct             # 0x5a9 = 1449
CONTAMINATED = EffectType.Contaminated                            # 0x4dc = 1244
#: gameconfig : les DEUX abilities portent les MEMES quatre paliers de mythique.
PALIERS = [10, 13, 16, 20]
ENTITY_TYPE_UNIT, ENTITY_TYPE_MACHINE = 1, 6


def _tid(c: int, r: int) -> int:
    return c * ROWS + r + 1


def _board(elev_by_pos=None) -> Board:
    """Plateau plat, sauf les tuiles listees dans `elev_by_pos` (etage 6).

    ⚠ `neighbours` est construit AVEC la porte d'elevation, et ce n'est pas un raccourci : c'est
    l'identite LUE du substrat (`Board.base_add_neighbours`) -- le champ `boardGraph.neighbours`
    est capte a travers `BattleQuery$$GetAdjacentTiles(t, false, false, true)`, donc a travers
    `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, dont la porte `|dElev| < 2` est
    INCONDITIONNELLE. Un board synthetique qui y mettrait la couronne hex NUE ne serait pas << un
    board plus simple >> : il serait un board qui n'existe pas, et il ferait passer pour vert un
    port qui lit `hexgeo.distance == 1`."""
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

def _effet(effect_type, source: int, level=1, mult: int = 100):
    """Instance telle que la FABRIQUE la produit -- c'est ce qui exerce le routage du registre en
    plus de la classe (`EffectFactory.create` rend un `BaseEffect` NU pour tout nom inconnu, et un
    `BaseEffect` nu a TOUS ses canaux muets : le bras vrai le verrait)."""
    inst = EffectFactory.create({"name": effect_type.name, "effectType": int(effect_type),
                                 "source": source, "active": True}, mult, level)
    assert type(inst) is EFFECT_CLASSES[effect_type.name], (
        "la fabrique ne route plus %d vers sa classe portee" % int(effect_type))
    return inst


def test_le_registre_route_les_deux_effets():
    assert EFFECT_CLASSES[BLIGHTED.name] is XDA.BlightedLandEffect
    assert EFFECT_CLASSES[MORE_GITZ.name] is XDA.MoreGitzOverEreExtraDamagePctEffect
    # L'ordinal 1449 est PARTAGE avec le passif `UnwaveringSentinel` de `custoKyrus`
    # (`TriggeredAbilityType` 1449) : l'appariement se fait par le NOM PLEIN, jamais par l'entier.
    assert EffectType(1449).name == "MoreGitzOverEre_ExtraDamagePct"
    assert EffectType(1442).name == "BlightedLand_ExtraDamagePct"


def test_la_face_native_de_1449_est_attaquant():
    """`...MoreGitzOverEre_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack` = slot 0x16 ->
    accumulateur ATTAQUANT, malgre le trigger `get_OwnerIsTarget` et le canal PORT defenseur. Le
    nombre de `Fix64.Round` en depend (#437-r1-r1-r1) : ce n'est pas une etiquette."""
    assert XDA.MoreGitzOverEreExtraDamagePctEffect.AURA_DEFENSE_MALUS_NATIVE_FACE == "attacker"


# ==================== Etage 2 -- 1442 : un bras VRAI et QUATRE contre-bras =====================

def _ctx_1442(**over):
    """Le ctx que l'agregateur d'aura ATTAQUE pose -- forme MINIMALE, surchargeable par bras."""
    c = {"owner_id": MOW_ID, "owner_team": 1, "owner_pos": None,     # MoW : AUCUNE position
         "att_id": ATT_ID, "att_team": 1, "att_pos": (2, 2),
         "att_rarity": Rarity.Mythic,
         "tile_effects_by_pos": {(2, 2): [CONTAMINATED.name]}}
    c.update(over)
    return c


def test_1442_bras_vrai():
    """Ami MYTHIQUE de la MoW, sur une tuile CONTAMINEE -> `+extraDmgPct %`.

    ⚠ `owner_pos = None` : le bras vrai DOIT passer alors que le porteur n'a aucune position.
    C'est la propriete qui rend cette aura evaluable depuis une MoW -- aucun etage du
    `$$CreateTargetSelector` ne lit la position du porteur."""
    eb = _effet(BLIGHTED, MOW_ID, 1).create_aura_attack_damage_bonus_for_ally(_ctx_1442())
    assert eb is not None, "bras VRAI muet : le gate refuse pour une raison non mesuree"
    assert eb.kind == "PercentIncrease", "canal POURCENT (`ForPercentIncrease` inline)"
    assert int(eb.value) == PALIERS[0]


@pytest.mark.parametrize("rarete", [Rarity.Epic, Rarity.Legendary, Rarity.Common, None])
def test_1442_contre_bras_rarete(rarete):
    """`UnitsWithRarity(..., 5 = Mythic, 3)` -- `UnitsWithRaritySelector$$Select` compare
    `GetBaseUnitComponent(e)+0x74` par EGALITE stricte.

    Le cas `None` est le plus important : c'est la degradation RESTRICTIVE nommee. Un port qui
    rabattrait le non-mesure sur `Rarity.Common` puis testerait `!= Mythic` passerait ce cas-la ;
    un port qui OMETTRAIT l'etage buffe TOUS les amis sur tuile contaminee."""
    ctx = _ctx_1442(att_rarity=rarete)
    assert _effet(BLIGHTED, MOW_ID, 1).create_aura_attack_damage_bonus_for_ally(ctx) is None


def test_1442_contre_bras_equipe():
    """`Friends(Owner@+0x30, AllUnits@+0x20, 3)` -- un ENNEMI Mythique sur tuile contaminee ne
    beneficie PAS de l'aura. Sans cet etage, la MoW bufferait l'adversaire."""
    e = _effet(BLIGHTED, MOW_ID, 1)
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx_1442(att_team=2)) is None
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx_1442(owner_team=None)) is None
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx_1442(att_team=None)) is None


def test_1442_contre_bras_tuile_non_contaminee():
    """`UnitsOnTilesWithEffect(..., 0x4dc = Contaminated)` -- la tuile lue est celle du
    BENEFICIAIRE (l'element courant du selecteur), pas celle de la cible du coup."""
    e = _effet(BLIGHTED, MOW_ID, 1)
    # Tuile sans effet du tout.
    assert e.create_aura_attack_damage_bonus_for_ally(
        _ctx_1442(tile_effects_by_pos={(2, 2): []})) is None
    # Tuile portant un AUTRE effet de tuile : l'etage doit discriminer, pas se contenter du non-vide.
    assert e.create_aura_attack_damage_bonus_for_ally(
        _ctx_1442(tile_effects_by_pos={(2, 2): [EffectType.Fire.name]})) is None
    # La tuile CONTAMINEE est celle de la CIBLE, pas celle de l'attaquant -> aucune contribution.
    assert e.create_aura_attack_damage_bonus_for_ally(
        _ctx_1442(tile_effects_by_pos={(3, 3): [CONTAMINATED.name]})) is None


def test_1442_contre_bras_canaux_non_mesures():
    """Canal ABSENT -> aucune contribution. << present != applique >>, et un canal muet ne doit
    JAMAIS se degrader en gate ouvert."""
    e = _effet(BLIGHTED, MOW_ID, 1)
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx_1442(tile_effects_by_pos=None)) is None
    assert e.create_aura_attack_damage_bonus_for_ally(_ctx_1442(att_pos=None)) is None
    assert e.create_aura_attack_damage_bonus_for_ally({}) is None
    assert e.create_aura_attack_damage_bonus_for_ally(None) is None


def test_1442_ne_contribue_a_aucun_autre_canal():
    """La classe n'override QUE le canal d'aura ATTAQUE. Le natif n'implemente ni
    `$$CreateEffectDamageMalusForDefense`, ni `$$CreateDamageModifier`, ni `$$GetStatModification*` :
    un port qui cablerait un second canal DOUBLERAIT la contribution."""
    e = _effet(BLIGHTED, MOW_ID, 1)
    assert e.create_aura_defense_damage_malus_for_ally(_ctx_1442()) is None
    assert e.create_aura_attack_damage_malus_for_enemy(_ctx_1442()) is None
    assert e.create_aura_attack_bonus(_ctx_1442()) is None
    assert e.create_effect_damage_bonus_for_attack(False, None, None, False, True, None,
                                                   _ctx_1442()) is None


# ============ Etage 3 -- 1442 : la MAGNITUDE suit les paliers ET le multiplicateur =============

@pytest.mark.parametrize("niveau,attendu", list(zip([1, 2, 3, 4], PALIERS)))
def test_1442_magnitude_par_palier(niveau, attendu):
    """`ConfigVar(0xa = extraDmgPct, GetAbilityState(this))` -- l'`AbilityState` BAKE a la pose,
    donc le palier TERTIAIRE 1..4 de la mythique."""
    eb = _effet(BLIGHTED, MOW_ID, niveau).create_aura_attack_damage_bonus_for_ally(_ctx_1442())
    assert eb is not None and int(eb.value) == attendu


def test_1442_magnitude_scale_par_le_multiplicateur_du_porteur():
    """`extraDmgPct` EST dans `variablesAffectedByRarityBonus` -> le multiplicateur MORD.
    `AbilityConfiguration$$GetVariableForLevel` fait `round(base * mult / 100)`."""
    eb = _effet(BLIGHTED, MOW_ID, 4, mult=180).create_aura_attack_damage_bonus_for_ally(_ctx_1442())
    assert int(eb.value) == round(PALIERS[3] * 180 / 100) == 36


def test_1442_ability_state_du_ctx_prime_sur_le_niveau_de_l_instance():
    """`GetAbilityState(effet)` = le couple TERTIAIRE du PORTEUR (#357). Le ctx le fournit par
    `tertiary_ability_state_of` ; sans lui, on lirait le niveau des PASSIFS du porteur (50 sur tout
    runner normalise), donc le DERNIER palier -- une sur-application silencieuse."""
    ctx = _ctx_1442(tertiary_ability_state_of=lambda oid, ab: (
        (2, 100) if (oid == MOW_ID and ab == "BlightedLand") else (None, 100)))
    # L'instance porte le palier 4 ; le ctx dit 2 -> c'est le CTX qui doit gagner.
    eb = _effet(BLIGHTED, MOW_ID, 4).create_aura_attack_damage_bonus_for_ally(ctx)
    assert int(eb.value) == PALIERS[1]
    # Un porteur qui ne porte PAS cette ability -> repli NOMME sur le niveau de l'instance.
    ctx2 = _ctx_1442(owner_id=999,
                     tertiary_ability_state_of=lambda oid, ab: (None, 100))
    assert int(_effet(BLIGHTED, MOW_ID, 4)
               .create_aura_attack_damage_bonus_for_ally(ctx2).value) == PALIERS[3]


# ================== Etage 4 -- 1449 : les DEUX branches et chaque conjoint =====================

SQUIG_VIS = "orksNpc7Squig"      # `VisualUnitIdFromUnitId("orksSmnSquig")`, LU au gameconfig


def _ctx_1449(profils, **over):
    """Le ctx que l'agregateur d'aura DEFENSE pose. `profils` = `tgt_adjacent_unit_profiles`."""
    c = {"owner_id": MOW_ID, "owner_team": 1, "owner_pos": None,     # MoW : AUCUNE position
         "tgt_id": FOE_ID, "tgt_team": 2, "t_pos": (3, 3),
         "att_id": ATT_ID, "att_team": 1, "att_pos": (2, 3),
         "att_rarity": Rarity.Mythic, "is_melee": True, "is_normal_attack": True,
         XDA.CTX_TGT_ADJACENT_UNIT_PROFILES: profils}
    c.update(over)
    return c


#: Voisinage de la cible portant DEUX amis Mythiques du porteur -> branche B seule.
PROFILS_B = ((M1_ID, 1, "orksNob", Rarity.Mythic), (M2_ID, 1, "orksNob", Rarity.Mythic))
#: Voisinage portant UN Squig ami (et AUCUN Mythique) -> branche A seule.
PROFILS_A = ((SQUIG_ID, 1, SQUIG_VIS, Rarity.Common),)


def test_1449_squig_visual_id_vient_du_gameconfig():
    """`VisualUnitIdFromUnitId( ConfigConstString(<config>, 0) )` -- DEUX lectures gameconfig
    enchainees (`constants.unitId` puis `units.<id>.visualId`), jamais une chaine en dur."""
    assert XDA._more_gitz_squig_visual_id() == SQUIG_VIS


def test_1449_bras_vrai_branche_b():
    """>= 2 amis MYTHIQUES du porteur adjacents a la cible -> `+extraDmgPct %` sur le coup."""
    eb = _effet(MORE_GITZ, MOW_ID, 1).create_aura_defense_damage_malus_for_ally(
        _ctx_1449(PROFILS_B))
    assert eb is not None, "bras VRAI (branche B) muet"
    assert eb.kind == "PercentIncrease" and int(eb.value) == PALIERS[0]


def test_1449_bras_vrai_branche_a():
    """Un SQUIG ami adjacent a la cible suffit, meme sans aucun Mythique dans le voisinage."""
    eb = _effet(MORE_GITZ, MOW_ID, 3).create_aura_defense_damage_malus_for_ally(
        _ctx_1449(PROFILS_A))
    assert eb is not None, "bras VRAI (branche A) muet"
    assert int(eb.value) == PALIERS[2]


def test_1449_contre_bras_selecteur():
    """`op_Addition(A, B)` est une UNION : il faut qu'AU MOINS une branche contienne la cible."""
    e = _effet(MORE_GITZ, MOW_ID, 1)
    # UN SEUL ami Mythique adjacent -> `AmountIsEqualOrGreater(..., Direct(2))` est FAUX.
    assert e.create_aura_defense_damage_malus_for_ally(
        _ctx_1449((PROFILS_B[0],))) is None
    # Deux Mythiques, mais ENNEMIS du porteur -> `Friends(Owner, ...)` les ecarte.
    assert e.create_aura_defense_damage_malus_for_ally(
        _ctx_1449(tuple((u, 2, v, r) for (u, _t, v, r) in PROFILS_B))) is None
    # Un Squig ENNEMI du porteur -> meme etage `Friends`, autre branche.
    assert e.create_aura_defense_damage_malus_for_ally(
        _ctx_1449(((SQUIG_ID, 2, SQUIG_VIS, Rarity.Common),))) is None
    # Voisinage MESURE et VIDE : c'est une mesure, pas une ignorance -> aucune contribution.
    assert e.create_aura_defense_damage_malus_for_ally(_ctx_1449(())) is None
    # Voisinage NON MESURE -> gate FERME (jamais accorde par defaut).
    assert e.create_aura_defense_damage_malus_for_ally(_ctx_1449(None)) is None
    assert e.create_aura_defense_damage_malus_for_ally({}) is None


@pytest.mark.parametrize("rarete", [Rarity.Epic, Rarity.Legendary, Rarity.Common, None])
def test_1449_contre_bras_rarete_de_l_attaquant(rarete):
    """`HasRarity(Caster@<DSLSelectors+0x48>, 5 = Mythic)` -- le gate porte sur l'ATTAQUANT, PAS sur
    la cible ni sur le porteur. i2 : << ... from normal melee attacks by Mythic characters >>."""
    ctx = _ctx_1449(PROFILS_B, att_rarity=rarete)
    assert _effet(MORE_GITZ, MOW_ID, 1).create_aura_defense_damage_malus_for_ally(ctx) is None


def test_1449_contre_bras_equipes():
    """Les DEUX filtres d'equipe : `Enemies(Owner, ...)` sur la CIBLE, `AreFriends(Caster,
    EffectSource)` sur l'ATTAQUANT. Ils portent sur des unites DIFFERENTES."""
    e = _effet(MORE_GITZ, MOW_ID, 1)
    # Cible ALLIEE du porteur -> `Enemies(Owner, ...)` l'ecarte.
    assert e.create_aura_defense_damage_malus_for_ally(_ctx_1449(PROFILS_B, tgt_team=1)) is None
    # Attaquant ENNEMI du porteur -> `AreFriends(Caster, EffectSource)` est FAUX.
    assert e.create_aura_defense_damage_malus_for_ally(_ctx_1449(PROFILS_B, att_team=2)) is None
    # Equipes NON MESUREES -> gate FERME.
    assert e.create_aura_defense_damage_malus_for_ally(_ctx_1449(PROFILS_B, owner_team=None)) is None
    assert e.create_aura_defense_damage_malus_for_ally(_ctx_1449(PROFILS_B, tgt_team=None)) is None
    assert e.create_aura_defense_damage_malus_for_ally(_ctx_1449(PROFILS_B, att_team=None)) is None


def test_1449_le_porteur_qui_attaque_lui_meme_beneficie():
    """`AreFriends(Caster, EffectSource)` est VRAI quand `Caster == EffectSource` --
    `UnitExtensions$$IsFriend` n'ecarte PAS l'egalite. Ce cran interdit d'AJOUTER une exclusion
    `att_id == owner_id` par imitation des agregateurs d'aura ATTAQUE (qui, eux, en ont une)."""
    ctx = _ctx_1449(PROFILS_B, att_id=MOW_ID)
    assert _effet(MORE_GITZ, MOW_ID, 1).create_aura_defense_damage_malus_for_ally(ctx) is not None


@pytest.mark.parametrize("cle", ["is_melee", "is_normal_attack"])
@pytest.mark.parametrize("val", [False, None])
def test_1449_contre_bras_nature_du_coup(cle, val):
    """`IsMeleeAttack` et `IsNormalAttack` -- tri-etat : `None` (nature non declaree) FERME le gate,
    comme `False`. Le natif ne devine pas non plus."""
    ctx = _ctx_1449(PROFILS_B, **{cle: val})
    assert _effet(MORE_GITZ, MOW_ID, 1).create_aura_defense_damage_malus_for_ally(ctx) is None


def test_1449_ne_contribue_a_aucun_autre_canal():
    """Le natif n'expose QUE `$$CreateEffectDamageBonusForAttack` : cabler un second canal
    doublerait la contribution."""
    e = _effet(MORE_GITZ, MOW_ID, 1)
    ctx = _ctx_1449(PROFILS_B)
    assert e.create_aura_attack_damage_bonus_for_ally(ctx) is None
    assert e.create_aura_attack_damage_malus_for_enemy(ctx) is None
    assert e.create_effect_damage_malus_for_defense(True, None, ctx) is None


def test_1449_magnitude_scale_par_le_multiplicateur_du_porteur():
    """`extraDmgPct` est dans `variablesAffectedByRarityBonus` de `MoreGitzOverEre` aussi."""
    eb = _effet(MORE_GITZ, MOW_ID, 4, mult=180).create_aura_defense_damage_malus_for_ally(
        _ctx_1449(PROFILS_B))
    assert int(eb.value) == round(PALIERS[3] * 180 / 100) == 36


# =============== Etage 5 -- les DEUX faces CONSTRUISENT les cles neuves ========================

def _dv():
    """`decisionView` MINIMAL : une MoW alliee porteuse des DEUX auras, un attaquant, une cible,
    deux amis Mythiques VOISINS de la cible. La MoW est publiee comme le fait le capteur -- canal
    `.mows` SEPARE, `pos = null`."""
    return {
        "currentPlayer": 1,
        "units": [
            {"id": ATT_ID, "visualId": "orksNob", "alive": True, "team": 1, "owner": 1,
             "pos": {"col": 2, "row": 3}, "effects": []},
            {"id": FOE_ID, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
             "pos": {"col": 3, "row": 3}, "effects": []},
            {"id": M1_ID, "visualId": "orksNob", "alive": True, "team": 1, "owner": 1,
             "pos": {"col": 3, "row": 2}, "effects": []},
            {"id": M2_ID, "visualId": "orksNob", "alive": True, "team": 1, "owner": 1,
             "pos": {"col": 4, "row": 3}, "effects": []},
        ],
        "mows": [
            {"casterId": MOW_ID, "visualId": "orksRukkatrukk", "alive": True, "team": 1,
             "owner": 1, "pos": None, "slot": 1,
             "effects": [{"id": 8001, "name": MORE_GITZ.name, "effectType": int(MORE_GITZ),
                          "sourceId": MOW_ID, "active": True, "targetIds": []},
                         {"id": 8002, "name": BLIGHTED.name, "effectType": int(BLIGHTED),
                          "sourceId": MOW_ID, "active": True, "targetIds": []}]},
        ],
        "effects": [
            {"id": 8001, "name": MORE_GITZ.name, "effectType": int(MORE_GITZ),
             "ownerId": MOW_ID, "source": MOW_ID, "active": True, "targetIds": []},
            {"id": 8002, "name": BLIGHTED.name, "effectType": int(BLIGHTED),
             "ownerId": MOW_ID, "source": MOW_ID, "active": True, "targetIds": []},
        ],
    }


def _snap(rarities=None):
    """`combatSnapshot` portant le canal `rarity` (#1039). REGIME SEPARANT par defaut :
    l'attaquant et les deux voisins sont Mythiques, la cible ne l'est pas."""
    r = {ATT_ID: Rarity.Mythic, FOE_ID: Rarity.Epic, M1_ID: Rarity.Mythic,
         M2_ID: Rarity.Mythic, MOW_ID: Rarity.Mythic}
    r.update(rarities or {})
    vis = {ATT_ID: "orksNob", FOE_ID: "necroWarden", M1_ID: "orksNob", M2_ID: "orksNob",
           MOW_ID: "orksRukkatrukk"}
    return {"rarityEnum": "idun.meta.Rarity",
            "units": [{"entityId": u, "visualId": vis[u],
                       "entityType": (ENTITY_TYPE_MACHINE if u == MOW_ID else ENTITY_TYPE_UNIT),
                       **({"rarity": int(r[u])} if r[u] is not None else {})}
                      for u in vis]}


def _obs():
    return {"units": [{"squadId": u, "hp": 5000, "hpMax": 5000}
                      for u in (ATT_ID, FOE_ID, M1_ID, M2_ID)]}


def _state(elev=None, rarities=None):
    return load_state(_dv(), _obs(), _snap(rarities), board=_board(elev))


def test_ctx_aura_defense_combat_porte_les_quatre_cles_neuves(monkeypatch):
    """MESURE en interceptant le foyer REEL : un ctx ecrit a la main mesurerait le test."""
    st = _state()
    vus = []
    reel = DM.aura_defense_damage_malus_from_units

    def _spy(carriers, ctx):
        vus.append((list(carriers or []), ctx))
        return reel(carriers, ctx)

    monkeypatch.setattr(DM, "aura_defense_damage_malus_from_units", _spy)
    DM.defender_modifiers(st, FOE_ID, 5000, is_melee=True, attacker_id=ATT_ID,
                          is_normal_attack=True)
    assert vus, "l'agregateur d'aura DEFENSE n'a pas ete appele -- le montage ne mesure rien"
    carriers, ctx = vus[0]
    assert MOW_ID in [c[0] for c in carriers], (
        "la MoW porteuse n'entre pas dans l'univers de porteurs (regression de #999-r3-r1-r1)")
    assert ctx.get("att_rarity") == Rarity.Mythic, "`HasRarity(Caster, ...)` serait muet"
    assert ctx.get("is_normal_attack") is True, "`IsNormalAttack` serait muet"
    assert callable(ctx.get("tertiary_ability_state_of")), "`GetAbilityState` serait muet"
    prof = ctx.get(XDA.CTX_TGT_ADJACENT_UNIT_PROFILES)
    assert prof is not None, "le substrat du `$$CreateTargetSelector` de 1449 serait muet"
    par_id = {p[0]: p for p in prof}
    assert set(par_id) == {M1_ID, M2_ID, ATT_ID}, (
        "voisinage de la cible mal mesure : %r" % (prof,))
    assert par_id[M1_ID][1] == 1 and par_id[M1_ID][3] == Rarity.Mythic
    assert par_id[M1_ID][2] == "orksNob", "le `visual_id` (branche A) n'est pas porte"


def test_le_coup_reel_porte_la_contribution_de_1449():
    """Bout en bout COMBAT : le modifier DEFENSEUR construit par le foyer contient bien le
    `PercentIncrease` de 1449, verse dans l'accumulateur ATTAQUANT (`pct_list`, face `attacker`).

    Contre-epreuve dans le MEME test : en regime NON separant sur la rarete de l'ATTAQUANT
    (`Epic`), la contribution DISPARAIT. Un accord obtenu sans ce temoin ne separerait rien."""
    from engine.services.damage_modifiers import get_multiplier_from_damage_bonus
    mods, _ = DM.defender_modifiers(_state(), FOE_ID, 5000, is_melee=True, attacker_id=ATT_ID,
                                    is_normal_attack=True)
    attendu = get_multiplier_from_damage_bonus(PALIERS[0])
    assert any(m == attendu for (m, _cap) in mods.pct_list), (
        "la contribution de 1449 n'atteint pas l'accumulateur ATTAQUANT : %r" % (mods.pct_list,))
    assert not any(m == attendu for (m, _cap) in mods.pct_list_defender), (
        "versee dans l'accumulateur DEFENSEUR : la face native serait fausse (un Fix64.Round de "
        "trop ou de moins)")
    mods2, _ = DM.defender_modifiers(_state(rarities={ATT_ID: Rarity.Epic}), FOE_ID, 5000,
                                     is_melee=True, attacker_id=ATT_ID, is_normal_attack=True)
    assert not any(m == attendu for (m, _cap) in mods2.pct_list), (
        "TEMOIN NON SEPARANT : l'attaquant Epic recoit quand meme le bonus")


def _scene(elev=None):
    """La `Scene` de la face DECISION, montee sur le MEME `step_context` que le COMBAT."""
    from engine.playbook.scene import Scene, step_context
    from engine.entities.unit_context import UnitContext
    from engine.entities.pathfinding import board as PFB
    dv = _dv()
    sctx = step_context({"mult_by_id": {}, "ablvl_by_id": {}, "ctx_by_id": {}}, dv)
    board = _board(elev)
    rar = {ATT_ID: Rarity.Mythic, FOE_ID: Rarity.Epic, M1_ID: Rarity.Mythic, M2_ID: Rarity.Mythic}
    vis = {ATT_ID: "orksNob", FOE_ID: "necroWarden", M1_ID: "orksNob", M2_ID: "orksNob"}
    return Scene(ctx_by_id={u: UnitContext(entity_id=u, visual_id=vis[u], rarity=rar[u])
                            for u in vis},
                 armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={}, vis_by_id=vis,
                 units=sctx.get("units") or [], hp_by_id=sctx.get("hp_by_id") or {},
                 pos_by_id=sctx.get("pos_by_id") or {}, team_by_id=sctx.get("team_by_id") or {},
                 eff_state=sctx["eff_state"], board=board,
                 elev_by_pos=PFB.elevations_by_pos(board))


def test_ctx_aura_defense_prediction_porte_les_memes_cles(monkeypatch):
    """Pendant exact de l'etage precedent sur l'autre face : threader un seul bout laisserait
    l'autre INERTE EN SILENCE -- c'est le fork prediction/combat que #197 et #950-r2 ont paye."""
    from engine.playbook.prediction import _shared as SH
    from engine.entities.effects import DamageModifiers
    vus = []
    reel = SH.aura_defense_damage_malus_from_units

    def _spy(carriers, ctx):
        vus.append((list(carriers or []), ctx))
        return reel(carriers, ctx)

    monkeypatch.setattr(SH, "aura_defense_damage_malus_from_units", _spy)
    sc = _scene()
    SH._add_positional_and_defender_mods(DamageModifiers(), sc, ATT_ID, FOE_ID, True, (2, 3),
                                         (3, 3), is_normal_attack=True)
    assert vus, "l'agregateur d'aura DEFENSE (prediction) n'a pas ete appele"
    carriers, ctx = vus[0]
    assert MOW_ID in [c[0] for c in carriers], "la MoW porteuse n'entre pas cote PREDICTION"
    assert ctx.get("att_rarity") == Rarity.Mythic
    assert ctx.get("is_normal_attack") is True
    prof = ctx.get(XDA.CTX_TGT_ADJACENT_UNIT_PROFILES)
    assert prof is not None
    assert {p[0] for p in prof} == {M1_ID, M2_ID, ATT_ID}
    assert {p[0]: p[3] for p in prof}[M1_ID] == Rarity.Mythic


# ============ Etage 6 -- l'adjacence est la MEME sur les deux faces, ELEVATION comprise =========

def test_les_deux_faces_mesurent_le_MEME_voisinage():
    """Un noeud natif, deux substrats -- ils doivent rendre le meme ensemble."""
    combat = DM._adjacent_unit_profiles(_state(), FOE_ID)
    from engine.playbook.prediction._shared import _adjacent_unit_profiles as pred
    prediction = pred(_scene(), FOE_ID)
    assert {p[0] for p in combat} == {p[0] for p in prediction} == {M1_ID, M2_ID, ATT_ID}
    assert {p[0]: p[3] for p in combat} == {p[0]: p[3] for p in prediction}


def test_la_porte_d_elevation_du_natif_MORD():
    """`TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` retient `|dElev| < 2` : un voisin
    hexagonal separe d'une MARCHE de 2 n'est PAS adjacent.

    Sans ce cran, un `hexgeo.distance == 1` passerait TOUS les autres etages -- et la branche B de
    1449 compterait des amis Mythiques que le natif ne compte pas."""
    from engine.playbook.prediction._shared import _adjacent_unit_profiles as pred
    plat = DM._adjacent_unit_profiles(_state(), FOE_ID)
    assert {p[0] for p in plat} == {M1_ID, M2_ID, ATT_ID}, "temoin PLAT degenere"
    # M1 est en (3,2), la cible en (3,3) : on creuse une marche de 3 entre les deux.
    marche_elev = {(3, 2): 3, (3, 3): 0}
    marche = DM._adjacent_unit_profiles(_state(elev=marche_elev), FOE_ID)
    assert {p[0] for p in marche} == {M2_ID, ATT_ID}, (
        "la porte d'elevation ne mord pas cote COMBAT : %r" % (marche,))
    # La face PREDICTION doit BASCULER PAREIL -- sinon les deux faces divergeraient sur la
    # geometrie, exactement le fork que le foyer partage existe pour interdire.
    marche_pred = pred(_scene(elev=marche_elev), FOE_ID)
    assert {p[0] for p in marche_pred} == {M2_ID, ATT_ID}, (
        "la porte d'elevation ne mord pas cote PREDICTION : %r" % (marche_pred,))
    # Et la branche B de 1449 BASCULE : un seul ami Mythique adjacent, donc plus de bonus.
    e = _effet(MORE_GITZ, MOW_ID, 1)
    assert e.create_aura_defense_damage_malus_for_ally(_ctx_1449(plat)) is not None
    assert e.create_aura_defense_damage_malus_for_ally(_ctx_1449(marche)) is None


def test_le_voisinage_est_tri_etat():
    """`None` = NON MESURE (pas d'unite / pas de position / pas d'equipe), jamais un tuple vide --
    qui, lui, est une MESURE (<< aucun voisin >>)."""
    st = _state()
    assert DM._adjacent_unit_profiles(st, None) is None
    assert DM._adjacent_unit_profiles(st, 9999) is None
    # La MoW n'a AUCUNE position -> question NON POSEE, pas << aucun voisin >>.
    assert DM._adjacent_unit_profiles(st, MOW_ID) is None
