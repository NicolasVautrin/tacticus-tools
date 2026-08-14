"""#1015-r1 -- le CLIQUET OFFLINE du trait `CloseCombatWeakness` (16 porteurs, tous `units.npc`).

CE QU'IL GARDE, et contre quoi :

  1. LA CHAINE trait -> ability -> effet, aux TROIS registres. Un maillon retire rend le trait
     silencieusement inerte : le seed n'ajoute plus rien, `EffectFactory` rend un effet anonyme, et
     le dispatcher n'itere plus 1130. Aucun test ne rougirait -- c'est exactement le no-op
     silencieux que #1015-r1 chasse.
  2. LES DEUX MAGNITUDES, figees a la valeur MESUREE (-50 melee, -25 tir). Le natif applique
     `ForPercentIncrease` avec ces constantes NEGATIVES : les recopier en positif (ou passer par
     `ForPercentDecrease`) inverserait le signe sans qu'aucune erreur ne sorte.
  3. LES TROIS TERMES de `NearbyEnemiesCondition`, chacun EXERCE dans les deux sens, et le TRI-ETAT
     (`None` = pas mesure) qui les separe du `False`.
  4. LA NATURE INCONNUE se TAIT. `is_ranged is None` ne veut pas dire << pas melee >> cote port :
     c'est la facade appelante qui n'a pas threade la nature. La branche `else` du `If` natif ne
     doit PAS s'y appliquer.
  5. LA FACE DECISION : le terme MOVE est `-40 x |ennemis adjacents|` (poids BC lu, jamais un
     litteral), et la face ATTAQUE n'est PAS au registre -- son absence EST le comportement natif
     (constante zero).

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PY = HERE.parents[3]
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

#: Ce qui doit faire REJOUER ce fichier.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/loki/close_combat_weakness.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/__init__.py",
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        "scripts/python/engine/dsl/event_trigger_type.py",
        "scripts/python/engine/playbook/close_combat_weakness.py",
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/damage_model.py",
        "scripts/python/engine/runner/operations/triggers/loki/close_combat_weakness.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
    ),
    "build": False,
    "toujours": False,
    "raison": (
        "Cliquet OFFLINE de #1015-r1 : chaine trait -> ability -> effet aux trois registres, "
        "magnitudes figees a la mesure, les trois termes de `NearbyEnemiesCondition` en tri-etat, "
        "et la face DECISION. Aucun runner."),
}

import pytest                                                              # noqa: E402

import engine.entities.effects.loki.close_combat_weakness as CCW           # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType                 # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.effects.base import BaseEffect                        # noqa: E402
from engine.entities.effects.factory import (                              # noqa: E402
    ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES, EffectFactory, TRAIT_DERIVED_ABILITIES)
from engine.entities.traits.unit_trait import UnitTrait                    # noqa: E402
from engine.entities.triggered_ability_type import (                       # noqa: E402
    TRAIT_TRIGGERED_ABILITY_IDS, TriggeredAbilityType)


TRAIT = "CloseCombatWeakness"
EFFET = EffectType.CloseCombatWeakness_ReduceDmg.name
MARQUEUR = EffectType.CloseCombatWeakness_StartedTurnAdjacentToEnemy.name


def _effet():
    e = EffectFactory.create({"name": EFFET})
    assert type(e) is CCW.CloseCombatWeaknessReduceDmgEffect, (
        "`EffectFactory` ne rend PAS la classe portee pour %r (rendu : %s) -- l'effet serait pose "
        "mais inerte." % (EFFET, type(e).__name__))
    return e


def _ctx(n_adj=1, effets=()):
    return {CCW.CTX_ADJACENT_ENEMIES: n_adj, "owner_effect_names": frozenset(effets)}


# ================================================================================================
# 1. LA CHAINE, aux trois registres
# ================================================================================================

def test_les_ordinaux_sont_ceux_du_dict_natif():
    """`Trait$$.cctor` dict `GetTriggeredAbility` (+0x0) : cle `0x40b` -> valeur `0x46a`, et
    `CloseCombatWeakness_AddEffectAbility$$GetEffectType` a pour corps ENTIER `return 0x46a`.
    FIGES ICI : `probe_313` compare le mirror au BUILD, il redevient vert des qu'on regenere le
    mirror apres un renumerotage -- alors que la valeur ECRITE au site, elle, a change."""
    assert int(UnitTrait.CloseCombatWeakness) == 0x40b
    assert int(TriggeredAbilityType.CloseCombatWeakness) == 0x46a
    assert int(EffectType.CloseCombatWeakness_ReduceDmg) == 0x46a
    assert int(EffectType.CloseCombatWeakness_StartedTurnAdjacentToEnemy) == 0x469
    assert int(EffectType.SuppressCloseCombatWeakness) == 0x478
    assert int(EffectType.SuppressRangeCloseCombatWeakness) == 0x487


def test_la_chaine_trait_ability_effet_est_complete():
    """Trois maillons, trois registres. En retirer UN suffit a rendre le trait inerte SANS erreur."""
    assert TRAIT_DERIVED_ABILITIES.get(TRAIT) == [TriggeredAbilityType.CloseCombatWeakness.name], (
        "le trait ne derive plus son ability : `_seed_derived_ability_owner_effects` ne pose plus rien")
    assert ABILITY_INIT_OWNER_EFFECTS.get(TriggeredAbilityType.CloseCombatWeakness.name) == [EFFET], (
        "l'ability ne pose plus son owner-effect a l'init")
    for nom in (EFFET, MARQUEUR):
        assert nom in EFFECT_CLASSES, (
            "%r n'a plus de classe : l'effet serait CAPTE mais anonyme, donc muet" % nom)
    assert TRAIT_TRIGGERED_ABILITY_IDS.get(TRAIT) == (int(TriggeredAbilityType.CloseCombatWeakness),), (
        "sans cette entree le dispatcher d'utilite n'itere JAMAIS 1130 : le playbook MOVE est mort")


def test_le_marqueur_est_pose_au_debut_de_tour_pour_UN_tour():
    """`CreateTargetTrigger` = `On(0x12) & HasAdjacentEnemies(Owner, Tiles(Owner))` ->
    `AddEffect(0x469, turns = <DSLFormulas+0x20> = Direct(1))`. `Direct(1)` = UN TOUR SEC, et PAS
    `TurnsFromRounds(1)` -- les confondre doublerait la duree dans un duel a deux joueurs."""
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    import engine.runner.operations.triggers.loki.close_combat_weakness as T
    classes = EFFECT_TRIGGERS.get(int(EffectType.CloseCombatWeakness_ReduceDmg)) or []
    assert T.CloseCombatWeaknessMarkStartedTurnAdjacent in classes
    cl = T.CloseCombatWeaknessMarkStartedTurnAdjacent
    assert int(cl.event_id) == int(EventTriggerType.TurnStart_EffectActivation) == 0x12
    assert int(cl.effect_type) == int(EffectType.CloseCombatWeakness_ReduceDmg)


# ================================================================================================
# 2. LES MAGNITUDES, figees a la mesure
# ================================================================================================

def test_les_deux_constantes_sont_negatives_et_valent_ce_qui_a_ete_mesure():
    """`ForPercentIncrease` avec des constantes NEGATIVES : le signe est DANS la donnee. Les
    recopier en positif inverserait le malus en bonus, sans aucune erreur."""
    melee = CCW.trait_var(CCW.TRAIT_ID, CCW.VAR_MELEE_PCT)
    tir = CCW.trait_var(CCW.TRAIT_ID, CCW.VAR_RANGE_PCT)
    assert melee == -50, "`%s` = %r (mesure #1015-r1 : -50)" % (CCW.VAR_MELEE_PCT, melee)
    assert tir == -25, "`%s` = %r (mesure #1015-r1 : -25)" % (CCW.VAR_RANGE_PCT, tir)


@pytest.mark.parametrize("is_ranged,attendu", [(False, -50), (True, -25)])
def test_la_branche_du_If_suit_la_nature_du_coup(is_ranged, attendu):
    b = _effet().create_effect_damage_bonus_for_attack(is_ranged=is_ranged, att_ctx=_ctx())
    assert b is not None and b.kind == "PercentIncrease", (
        "canal attendu `ForPercentIncrease` (l'empreinte du corps inline), rendu %r" % (b,))
    assert b.value == attendu
    assert b.owner_is_caster is True, "l'effet vit sur l'ATTAQUANT (`get_OwnerIsActor`)"
    assert b.native_face == "attacker", "slot virtuel `CreateEffectDamageBonusForAttack`"


# ================================================================================================
# 3. LES TROIS TERMES de `NearbyEnemiesCondition`, exerces dans les DEUX sens
# ================================================================================================

def test_le_terme_geometrique_est_inclusif_a_partir_de_UN():
    """`AmountIsEqualOrGreater(<ennemis>, Direct(1))` -- comparateur INCLUSIF, MESURE par
    `probe_293 --inventory` (famille `AmountIsEqualOrGreater`, encodage `setge`) et non lu au nom du
    `.ctor`, que l'ICF a deduplique. Prendre le nom aurait donne `> 1`, donc AUCUN malus au contact
    d'un seul ennemi."""
    e = _effet()
    assert e.nearby_enemies_condition(_ctx(n_adj=1)) is True
    assert e.nearby_enemies_condition(_ctx(n_adj=0)) is False


def test_le_marqueur_du_debut_de_tour_suffit_seul():
    """`HasAdjacentEnemies | HasEffect(Owner, 1129)` : le porteur qui a COMMENCE son tour au contact
    garde le malus meme s'il se DESENGAGE. Sans ce terme, le port surestimerait ses degats sur
    exactement le geste qu'une unite T'AU fait le plus souvent."""
    e = _effet()
    assert e.nearby_enemies_condition(_ctx(n_adj=0, effets=(MARQUEUR,))) is True


def test_la_suppression_ferme_tout_meme_au_contact():
    """`NOT HasEffect(Owner, 1144)` est le membre GAUCHE d'un `op_BitwiseAnd` : il domine les deux
    autres. Porteur : `EarlyWarningOverride` (tau)."""
    e = _effet()
    ctx = _ctx(n_adj=3, effets=(EffectType.SuppressCloseCombatWeakness.name, MARQUEUR))
    assert e.nearby_enemies_condition(ctx) is False
    assert e.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx=ctx) is None


def test_la_suppression_RANGED_ne_ferme_QUE_le_tir():
    """`If(HasEffect(Caster, 1159), Direct(0), ConfigConst(0x53))` est DANS le bras `else` du `If`
    exterieur : il ne touche pas la branche MELEE."""
    e = _effet()
    ctx = _ctx(n_adj=1, effets=(EffectType.SuppressRangeCloseCombatWeakness.name,))
    assert e.create_effect_damage_bonus_for_attack(is_ranged=True, att_ctx=ctx) is None
    b = e.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx=ctx)
    assert b is not None and b.value == -50


def test_le_tri_etat_distingue_PAS_MESURE_de_FAUX():
    """`None` = la cle n'est pas au contexte. Le rabattre sur `False` (ou sur `True`) serait une
    degradation SILENCIEUSE : ici on rend `None`, et le canal degat se tait."""
    e = _effet()
    assert e.nearby_enemies_condition(None) is None
    assert e.nearby_enemies_condition({}) is None                     # aucune des deux cles
    assert e.nearby_enemies_condition({"owner_effect_names": frozenset()}) is None
    assert e.create_effect_damage_bonus_for_attack(is_ranged=False, att_ctx=None) is None


def test_la_nature_inconnue_ne_prend_AUCUNE_branche():
    """Le natif n'a pas d'etat << inconnu >> ; le port, si. `is_ranged is None` = la facade n'a pas
    threade la nature -- appliquer le bras `else` (-25 %) y imputerait un malus que le natif ne met
    que sur un coup REELLEMENT non-melee."""
    assert _effet().create_effect_damage_bonus_for_attack(is_ranged=None, att_ctx=_ctx()) is None


def test_la_condition_active_est_PORTEE_et_le_drapeau_est_HONORE():
    """`CreateActiveCondition` = `return NearbyEnemiesCondition()` (corps ENTIER).

    LE COUPLE EST INDISSOCIABLE, et c'est ce qui a fait rougir
    `test_refresh_active_flag_discriminant_offline` a la premiere livraison : poser
    `active_condition_ported = True` SANS surcharger `is_active` fait s'en remettre au defaut
    `BaseEffect.is_active -> True`, c'est-a-dire a une valeur INVENTEE -- « un inerte capte
    transforme en contributeur », exactement ce que l'encadre d'`effects/base.py` proscrit.
    Le cliquet voisin garde l'invariant global (`flagged < overrides`) ; celui-ci garde le couple
    POUR CETTE CLASSE, en local, avec la raison."""
    e = _effet()
    assert e.active_condition_ported is True
    assert type(e).is_active is not BaseEffect.is_active, (
        "`active_condition_ported` est pose mais `is_active` n'est PAS surchargee : le refresh et "
        "`active_effects` liraient le defaut `True` sans AUCUNE lecture du natif")


def test_is_active_ne_ferme_PAS_sur_une_cle_absente():
    """CLE ABSENTE = non mesure -> `True`. Le `unit_state` de `RefreshEffectsOperation$$
    ShouldBeActive` ne porte ni le compteur geometrique ni les effets du porteur ; rendre `False`
    ferait DISPARAITRE l'instance d'`active_effects` et avec elle toute chance de contribuer.
    C'est sans risque parce que la MAGNITUDE re-evalue la MEME condition au coup."""
    e = _effet()
    assert e.is_active(None) is True
    assert e.is_active({}) is True
    # ... mais elle FERME des que la mesure est la et qu'elle est fausse.
    assert e.is_active(_ctx(n_adj=0)) is False
    assert e.is_active(_ctx(n_adj=2)) is True
    assert e.is_active(_ctx(n_adj=3, effets=(EffectType.SuppressCloseCombatWeakness.name,))) is False


# ================================================================================================
# 4. L'ARBRE du selecteur -- la forme, pas seulement le resultat
# ================================================================================================

def test_l_arbre_has_adjacent_enemies_a_ses_quatre_etages():
    """`UnitsWithoutTrait( UnitsWithoutTrait( Enemies(of, AdjacentUnits(tile, 1, 3), 3), Object, 3),
    Steppable, 3)` -- les deux filtres de trait sont CHAINES (le natif re-affecte a chaque etage),
    pas une intersection comme `NonSteppableOrObjectUnits`."""
    from engine.entities.selectors import AdjacentUnits, Enemies, UnitsWithoutTrait
    sel = CCW.has_adjacent_enemies_selector()
    assert isinstance(sel, UnitsWithoutTrait) and sel.trait == int(UnitTrait.Steppable)
    inner = sel.source
    assert isinstance(inner, UnitsWithoutTrait) and inner.trait == int(UnitTrait.Object)
    ennemis = inner.source
    assert isinstance(ennemis, Enemies)
    assert isinstance(ennemis.reference, (type(CCW.Caster()), type(CCW.Owner()))), (
        "le REFERENT d'equipe d'`Enemies` doit etre l'unite (`Caster@+0x48` ou `Owner@+0x30`), "
        "rendu %s -- l'ordre des arguments du port (`inner`, `reference`) est INVERSE de celui du "
        "natif (`of`, `entities`), et les intervertir passe SILENCIEUSEMENT." % type(ennemis.reference).__name__)
    for etage in (sel, inner, ennemis):
        assert getattr(etage, "selection_type", None) == CCW._SEL, (
            "le `UnitSelectionType 3` doit etre propage a TOUS les etages : c'est lui qui ecarte "
            "une unite vivante mais NON CIBLABLE (deep-strike), et son oubli sur-compte le contact")
    assert isinstance(ennemis.inner, AdjacentUnits), (
        "l'etage geometrique doit etre `AdjacentUnits(unitTile, unique: 1, 3)` -- c'est la TUILE du "
        "caster qui est le centre, pas le caster : `NearbyEnemiesCondition` passe `Caster@+0x48` et "
        "`CasterTile@+0x50` SEPAREMENT, et `CreateTargetTrigger` passe `Owner` et `Tiles(Owner)`.")
    assert ennemis.inner.selection_type == CCW._SEL


# ================================================================================================
# 5. LA FACE DECISION
# ================================================================================================

def test_le_playbook_MOVE_est_au_registre_et_vaut_moins_40_par_ennemi():
    import engine.weights as W
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    from engine.playbook.close_combat_weakness import (
        CLOSE_COMBAT_WEAKNESS_PER_ADJACENT_ENEMY, CloseCombatWeaknessPlaybook)
    pb = TRIGGERED_MOVE_PLAYBOOKS.get(int(TriggeredAbilityType.CloseCombatWeakness))
    assert isinstance(pb, CloseCombatWeaknessPlaybook)
    wt = W.load()
    poids = wt.sub("TriggeredAbilities", CLOSE_COMBAT_WEAKNESS_PER_ADJACENT_ENEMY)
    assert poids == -40, (
        "poids BC %r -- la cle est le LITTERAL `0x336efa0` du `MoveNext`, lue dans "
        "`metadata/string_literals.tsv`. NEGATIF : le porteur FUIT le contact." % poids)
    ctx = {"enemy_units": [{"pos": (5, 5)}, {"pos": (5, 6)}, {"pos": (0, 0)}], "elev_by_pos": None}
    assert pb.calculate_movement_utility_in_steps((5, 5), ctx, wt) == float(poids)   # 1 adjacent
    assert pb.calculate_movement_utility_in_steps((0, 8), ctx, wt) == 0.0            # aucun


def test_la_face_ATTAQUE_n_est_PAS_au_registre_et_c_est_le_natif():
    """`<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` yield `Fix64(0)` : un seul step, a
    ZERO. Un step nul ne se distingue pas d'un playbook absent -- l'inscrire fabriquerait un terme
    que le natif n'a pas."""
    from engine.playbook.psyker import TRIGGERED_ATTACK_PLAYBOOKS
    assert int(TriggeredAbilityType.CloseCombatWeakness) not in TRIGGERED_ATTACK_PLAYBOOKS

