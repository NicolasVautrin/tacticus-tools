"""CLIQUETS OFFLINE #920 -- la relique `MawClawsOfThyrax`, ses DEUX faces.

Ce que ces etages figent, et POURQUOI chacun :

  1. les ORDINAUX ECRITS AUX SITES, contre le build (un renumerotage silencieux ferait lire la
     config d'une AUTRE relique) ;
  2. les DEUX collisions -- `EffectType 1469 = MischiefMakers` et `TriggeredAbilityType 1461 =
     BookOfFate` : l'appariement inverse ne LEVERAIT PAS, il lirait la mauvaise config ;
  3. la STRUCTURE de l'arbre du compteur, et surtout que son etage de voisinage est
     `AdjacentUnits` -- **PAS** `AdjacentFriends`. C'est LE point ou la recopie d'un voisin de
     forme (`KardiocoreGalvanus`, `AmuletOfTheVoidwyrm`) donnerait un port faux, et il est
     CONFRONTE LIVE (bras `--ennemi` du probe : compteur natif 2 avec les compagnons cote ADVERSE) ;
  4. le canal `ForAddition` et ses gates, chacun se taisant pour SA raison ;
  5. la condition d'activite = le MEME compteur compare a zero (l'INVERSE de 1450, `YesTrigger`) ;
  6. la face DECISION owner (playbook MOVE) : registre, cle BC, filtre `Summon`, DEUX camps, et
     l'absence DELIBEREE au registre ATTACK (le corps natif y rend un zero constant) ;
  7. les cles du substrat d'etat, LA OU elles sont consommees ;
  8. l'import isole (cliquet #433-r1).

ASCII only.
"""
from __future__ import annotations

import inspect

import pytest

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des deux `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/gameconfig.py",
        # LE MODULE D'EFFET et son registre : l'arbre du compteur, les gates, la magnitude.
        "scripts/python/engine/entities/effects/loki/maw_claws_of_thyrax.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/magnitude.py",
        # LE CONTRE-TEMOIN : 1450 doit rester `active_condition_ported = False` (`YesTrigger`).
        "scripts/python/engine/entities/effects/loki/kardiocore_galvanus.py",
        # LES DEUX ENUMS dont ce fichier fige les ordinaux ECRITS AUX SITES, et les DEUX collisions.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        # LES NOEUDS DSL du compteur : un etage retire ou une signature changee doit rougir ici.
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/formulas.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/entities/unit_selection_type.py",
        # LA FACE DECISION : le playbook MOVE, son registre, et les deux registres qui doivent
        # rester DISJOINTS (MOVE inscrit / ATTACK deliberement absent).
        "scripts/python/engine/playbook/adjacent_summons.py",
        "scripts/python/engine/playbook/adjacent_unit_preference.py",
        "scripts/python/engine/playbook/non_owner.py",
        "scripts/python/engine/playbook/psyker.py",
        "scripts/python/engine/battle_query.py",
        # LE SUBSTRAT D'ETAT du compteur (cle du `unit_state`, gate de presence) et le canal CRIT
        # (callable par porteur) : les deux points ou la cle peut disparaitre EN SILENCE.
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/operations/damage.py",
    ),
    # `build: True` -- les ordinaux figes (etage 1) et les paliers `extraCritDmg` (etage 3) sont
    # RELUS du gameconfig VIVANT et des mirrors d'enum : un changement de build peut les deplacer,
    # et c'est precisement ce que ce fichier doit rougir.
    "build": True,
    "toujours": False,
    "raison": (
        "Ce fichier garde le port de la relique `MawClawsOfThyrax` (1469) et de son effet 1461 sur "
        "le canal crit-DEGAT, PLUS sa face DECISION owner (playbook MOVE). Les chemins listes sont "
        "ceux dont une modification peut faire changer un verdict : le mirror lui-meme, les deux "
        "enums qu'il fige, les noeuds DSL du compteur (dont l'interdiction d'`AdjacentFriends`), "
        "le contre-temoin 1450, les deux registres de playbook, et les deux points du substrat "
        "d'etat ou la cle du compteur peut disparaitre."),
}

EFFECT_NAME = "MawClawsOfThyrax_ExtraCritDmg"
ABILITY_ID = "MawClawsOfThyrax"


# ---------------------------------------------------------------------------------------------
# 1. IDENTITE -- les ordinaux ECRITS aux sites, contre le build
# ---------------------------------------------------------------------------------------------

def test_les_ordinaux_du_cas_sont_ceux_du_build():
    """`MawClawsOfThyraxAbility$$GetEffectType` a pour corps ENTIER `return 0x5b5` (= 1461), et le
    `.ctor` de l'effet porte `mov edx, 0x5bd` (= 1469) suivi de la surcharge
    `AbilityOrEffect$$op_Implicit(triggeredAbility: TriggeredAbilityType)`, resolue par son RVA.

    Ce test fige les ordinaux **ECRITS AU SITE** : `probe_313` compare le MIRROR au BUILD et
    redevient vert des qu'on regenere le mirror apres un renumerotage, alors que la valeur ecrite
    au site, elle, a change (CLAUDE.md, cran #270-r1-r1-r3)."""
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    assert int(EffectType.MawClawsOfThyrax_ExtraCritDmg) == 0x5b5 == 1461
    assert int(TriggeredAbilityType.MawClawsOfThyrax) == 0x5bd == 1469


def test_les_DEUX_collisions_existent_et_c_est_elles_qui_rendent_le_NOM_obligatoire():
    """`EffectType 1469` et `TriggeredAbilityType 1461` nomment AUTRE CHOSE, et l'un des deux
    designe une AUTRE RELIQUE dont la config EXISTE -- donc l'appariement inverse ne leverait
    aucune erreur : il lirait `BookOfFate.variables` en silence."""
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    assert EffectType(1469).name == "MischiefMakers"
    assert TriggeredAbilityType(1461).name == "BookOfFate"


def test_la_config_lue_est_celle_de_la_TRIGGERED_et_elle_a_ses_dix_paliers():
    """`_ABILITY_ID` sert de cle a `ability_var` -> `gameconfig.ability(<nom>)`. La variable est
    `extraCritDmg` (`AbilityVariableType 0x42 = 66`, `enums.tsv`)."""
    import gameconfig as GC
    from engine.entities.effects.loki import maw_claws_of_thyrax as M
    assert M._ABILITY_ID == ABILITY_ID and M._VAR_KEY == "extraCritDmg"
    paliers = ((GC.ability(ABILITY_ID) or {}).get("variables") or {}).get(M._VAR_KEY)
    assert paliers and len(paliers) == 10, "paliers absents/incomplets : %r" % (paliers,)


# ---------------------------------------------------------------------------------------------
# 2. LE COMPTEUR -- un arbre DSL, et son etage de voisinage NE FILTRE PAS L'EQUIPE
# ---------------------------------------------------------------------------------------------

def test_le_compteur_est_l_arbre_natif_a_quatre_noeuds():
    """`GetCalculateLevel` = `Count(Unique(UnitsWithTrait(AdjacentUnits(Owner@+0x30, unique: 1,
    selectionType: 3), 0x2 = Summon, selectionType: 3)))`.

    Les QUATRE cibles de `call` du corps ont ete resolues par leur RVA (`AdjacentUnits`,
    `UnitsWithTrait`, `Unique`, `Count`), pas par le nom affiche. Le test lit la STRUCTURE, pas une
    valeur : c'est ce qui attrape un port qui « simplifierait » un etage -- et notamment le `Unique`,
    que ni 1450 ni 1460 ne portent."""
    from engine.entities.effects.loki.maw_claws_of_thyrax import adjacent_summons_selector, _SEL
    from engine.entities.selectors.units import AdjacentUnits, Unique, UnitsWithTrait
    from engine.entities.selectors.accessors import Owner
    from engine.entities.formulas import Count
    from engine.entities.traits.unit_trait import UnitTrait

    arbre = adjacent_summons_selector()
    assert isinstance(arbre, Count)
    uniq = arbre.source if hasattr(arbre, "source") else arbre.selector
    assert isinstance(uniq, Unique), "etage Unique absent : %r" % (uniq,)
    wt = uniq.source
    assert isinstance(wt, UnitsWithTrait), "etage UnitsWithTrait absent : %r" % (wt,)
    assert int(wt.trait) == int(UnitTrait.Summon) == 2
    adj = wt.source
    assert isinstance(adj, AdjacentUnits)
    assert isinstance(adj.center, Owner)
    # le litteral `selectionType = 3 = OnlyAliveAndTargetable` est PROPAGE aux DEUX etages.
    assert _SEL == 3
    assert wt.selection_type == 3 and adj.selection_type == 3


def test_l_etage_de_voisinage_n_est_PAS_AdjacentFriends():
    """LE point de ce port. `DSLSelectors$$AdjacentUnits` =
    `op_Subtraction(Units(AdjacentTiles(origin), unique, sel), origin)` -- aucun `Friends`, aucun
    `Enemies` : un summon ENNEMI adjacent compte AUTANT qu'un allie.

    Ses DEUX voisins de forme, eux, filtrent l'equipe (`AmuletOfTheVoidwyrm` :
    `AdjacentFriends` + Summon/Decoy ; `KardiocoreGalvanus` : `AdjacentFriends` +
    `MechanicalUnits`). Recopier l'un des deux passerait TOUS les bras a compagnons AMIS et
    manquerait les summons adverses -- sur l'axe Tyranides/Genestealer, ou les DEUX camps en
    produisent. CONFRONTE LIVE : bras `--ennemi` du probe, compteur natif = 2 avec les compagnons
    cote adverse (`decisionView.effects[].level`), bonus 654 = 327 x 2, salve bit-exacte."""
    from engine.entities.effects.loki.maw_claws_of_thyrax import adjacent_summons_selector
    from engine.entities.selectors.units import AdjacentFriends, MechanicalUnits, Union
    noeuds, pile = [], [adjacent_summons_selector()]
    while pile:
        n = pile.pop()
        noeuds.append(type(n).__name__)
        for attr in ("source", "selector", "entities", "center", "left", "right"):
            v = getattr(n, attr, None)
            if hasattr(v, "select") or hasattr(v, "calculate"):
                pile.append(v)
    assert "AdjacentFriends" not in noeuds, (
        "l'arbre porte un `AdjacentFriends` : le natif est `AdjacentUnits` (aucun filtre d'equipe)")
    assert "MechanicalUnits" not in noeuds and "Union" not in noeuds, (
        "arbre contamine par celui d'un voisin de forme : %r" % (noeuds,))
    del AdjacentFriends, MechanicalUnits, Union      # importes pour NOMMER ce qui est interdit


# ---------------------------------------------------------------------------------------------
# 3. LA MAGNITUDE -- un PRODUIT signe POSITIVEMENT, etage par etage
# ---------------------------------------------------------------------------------------------

def _effet(level=3, mult=100):
    """Instancie l'effet PAR LE REGISTRE (jamais la classe importee en direct) : c'est le chemin que
    suit la factory quand elle materialise un effet CAPTE."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effect_type import EffectType
    cls = EFFECT_CLASSES[EFFECT_NAME]
    return cls(EFFECT_NAME, effect_type=int(EffectType.MawClawsOfThyrax_ExtraCritDmg),
               level=level, ability_level=level, ability_variables_multiplier=mult)


def test_le_bonus_crit_est_le_PRODUIT_signe_POSITIVEMENT():
    """`ForAddition(get_OwnerIsCaster, Multiply(ConfigVar(0x42), EffectLevel(Effect@+0x38)))`,
    la surcharge `ForAddition` tranchee par l'ADRESSE de son `call` (`0x181047dc0`, et NON
    `0x181048090` = `ForSubtraction`).

    Le retour POSITIF n'est pas une convention locale : `GetCritDamageBonusFromEffects` accumule
    `addition - subtraction`, et `CalculateCriticalDamage` fait `Math.Max(0, GetStat(10) + somme)`.
    Chiffres CONFRONTES LIVE a `extraCritDmg[3] = 327` : n=1 -> 327, n=2 -> 654, n=4 -> 1308."""
    import gameconfig as GC
    paliers = ((GC.ability(ABILITY_ID) or {}).get("variables") or {}).get("extraCritDmg")
    v3 = int(paliers[2])
    e = _effet(level=3)
    for n in (1, 2, 4):
        ctx = {"owner_id": 7, "att_id": 7, "adjacent_summons_of": (lambda oid, _n=n: _n)}
        assert e.create_effect_crit_damage_bonus_for_attack(ctx) == v3 * n


def test_le_niveau_indexe_le_palier_et_ce_n_est_pas_celui_de_l_EFFET():
    """`GetAbilityState(effet)` rend le couple TERTIAIRE du porteur ; `ability_var` l'indexe.

    Deux niveaux differents doivent rendre deux paliers differents -- sans quoi le bras `PASSIF`
    du probe (qui retire le callable `tertiary_ability_state_of`) ne pourrait rien mordre."""
    import gameconfig as GC
    paliers = [int(x) for x in
               ((GC.ability(ABILITY_ID) or {}).get("variables") or {}).get("extraCritDmg")]
    ctx = {"owner_id": 7, "att_id": 7, "adjacent_summons_of": lambda oid: 1}
    assert _effet(level=1).create_effect_crit_damage_bonus_for_attack(ctx) == paliers[0]
    assert _effet(level=10).create_effect_crit_damage_bonus_for_attack(ctx) == paliers[9]
    assert paliers[0] != paliers[9], "paliers plats : le bras NIVEAU ne discriminerait rien"
    # ... et le callable TERTIAIRE prime sur les niveaux portes par l'instance.
    ctx2 = dict(ctx, tertiary_ability_state_of=(lambda oid, ab: (1, 100)))
    assert _effet(level=10).create_effect_crit_damage_bonus_for_attack(ctx2) == paliers[0]


def test_les_gates_du_bonus_se_TAISENT_chacun_pour_sa_raison():
    """Trois portes, trois `None` -- et aucune n'est permissive :

      * `get_OwnerIsCaster` faux (le porteur n'est pas l'ATTAQUANT) -- c'est le bras
        `--porteur-defenseur` du probe, ou le COMPTEUR reste PLEIN (2) et le bonus vaut `None` ;
      * identite NON PROUVEE (une des deux cles absente) -> noeud FAUX, jamais VRAI ;
      * compteur NUL -> `Multiply` rend 0, et `ForAddition(0)` ne verse rien (bras `--trait Hero`
        et bras `n = 0` du probe : canal muet des deux cotes)."""
    e = _effet()
    assert e.create_effect_crit_damage_bonus_for_attack(
        {"owner_id": 7, "att_id": 8, "adjacent_summons_of": lambda oid: 3}) is None
    assert e.create_effect_crit_damage_bonus_for_attack(
        {"owner_id": 7, "adjacent_summons_of": lambda oid: 3}) is None
    assert e.create_effect_crit_damage_bonus_for_attack(
        {"owner_id": 7, "att_id": 7, "adjacent_summons_of": lambda oid: 0}) is None


def test_le_compteur_NON_MESURE_retombe_sur_le_NIVEAU_CAPTE_et_non_sur_None():
    """⚠ Le second facteur natif n'est PAS le compteur : c'est `EffectLevel(Effect@+0x38)` =
    `EffectComponent+0x68`, un champ STOCKE que `RefreshEffectsOperation$$UpdateLevel` tient egal a
    `GetCalculateLevel`. Le port privilegie le compteur RECALCULE (il suit l'etat courant du board)
    et retombe sur le niveau CAPTE quand aucun `state` n'est threade -- ce repli EST le mirror du
    noeud natif, pas une commodite. Meme forme que `KardiocoreGalvanusExtraCritDmgEffect`.

    ⚠ ET LE CHAMP STOCKE PEUT ETRE PERIME, c'est MESURE (#920) : sur un effet INACTIF le
    `decisionView` publie `level = 1` avec un voisinage VIDE, parce qu'`UpdateLevel` n'est atteint
    que par le chemin qui rafraichit un effet ACTIF. Le natif lirait ce meme 1 ; le port aussi. Ce
    n'est donc pas une divergence -- c'est pourquoi la mesure live thread TOUJOURS le compteur.

    Ne rendre `None` que si NI le compteur NI le niveau capte ne sont connus."""
    import gameconfig as GC
    paliers = [int(x) for x in
               ((GC.ability(ABILITY_ID) or {}).get("variables") or {}).get("extraCritDmg")]
    ctx = {"owner_id": 7, "att_id": 7, "adjacent_summons_of": lambda oid: None}
    assert _effet(level=3).create_effect_crit_damage_bonus_for_attack(ctx) == paliers[2] * 3
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effect_type import EffectType
    muet = EFFECT_CLASSES[EFFECT_NAME](
        EFFECT_NAME, effect_type=int(EffectType.MawClawsOfThyrax_ExtraCritDmg),
        level=None, ability_level=3, ability_variables_multiplier=100)
    assert muet.create_effect_crit_damage_bonus_for_attack(ctx) is None


# ---------------------------------------------------------------------------------------------
# 4. LA CONDITION D'ACTIVITE -- le MEME compteur compare a zero (l'INVERSE de 1450)
# ---------------------------------------------------------------------------------------------

def test_la_condition_d_activite_est_le_MEME_compteur_compare_a_zero():
    """`CreateActiveCondition` = `AmountIsGreaterThanZero(<vslot +0x5f8> = GetCalculateLevel())`,
    surcharge `(amount: IAmountFormula)` tranchee par l'ADRESSE (`0x180ed52d0`).

    Le slot `+0x5f8` EST `GetCalculateLevel` : `BaseEffect$$IsCalculatingLevel` et
    `$$NeedsRefreshing` l'appellent tous deux et cachent le resultat dans `this+0x88`.

    ⚠ C'est l'INVERSE de `KardiocoreGalvanus`, dont la `CreateActiveCondition` est
    `<DSLTriggers+0x70>` = `YesTrigger` (constante VRAIE) -- d'ou son `active_condition_ported`
    absent. Confonder les deux rendrait cet effet TOUJOURS present dans `decisionView.effects`,
    alors que la mesure live le publie `active: false` a compteur nul.

    Cle ABSENTE = NON MESURE -> on NE FERME PAS (degradation fidele)."""
    from engine.entities.effects.loki.maw_claws_of_thyrax import CARRIER_COUNT_KEY
    from engine.entities.effects.loki.kardiocore_galvanus import (
        KardiocoreGalvanusExtraCritDmgEffect as K)
    e = _effet()
    assert e.active_condition_ported is True
    assert e.is_active({CARRIER_COUNT_KEY: 1}) is True
    assert e.is_active({CARRIER_COUNT_KEY: 0}) is False
    assert e.is_active({}) is True
    assert e.is_active(None) is True
    assert K.active_condition_ported is False, (
        "1450 a une `CreateActiveCondition` CONSTANTE VRAIE : lui poser le flag inventerait un gate")


# ---------------------------------------------------------------------------------------------
# 5. LA FACE DECISION -- playbook owner MOVE, et l'absence DELIBEREE au registre ATTACK
# ---------------------------------------------------------------------------------------------

def test_le_playbook_MOVE_est_au_registre_avec_sa_cle_BC():
    """`MawClawsOfThyraxPlaybook$$.ctor` porte le litteral `0x5bd` = 1469, et son corps MOVE lit
    `MawClawsOfThyrax_LikesAdjacentSummons` (slot de litteral `0x33d90d0`).

    ⚠ A ne pas confondre avec `MawClawsOfThyrax_AdjacentSummons` (`0x33d8f88`), la cle de la face
    NON-OWNER : les deux valent 5 au gameconfig vivant, donc une confusion serait AUJOURD'HUI
    invisible."""
    from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
    from engine.playbook.adjacent_summons import MawClawsOfThyraxPlaybook
    from engine.playbook.non_owner import MawClawsOfThyraxNonOwnerPlaybook
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    pb = TRIGGERED_MOVE_PLAYBOOKS[int(TriggeredAbilityType.MawClawsOfThyrax)]
    assert isinstance(pb, MawClawsOfThyraxPlaybook)
    assert pb.WEIGHT_KEY == "MawClawsOfThyrax_LikesAdjacentSummons"
    assert MawClawsOfThyraxNonOwnerPlaybook.KEY == "MawClawsOfThyrax_AdjacentSummons"
    assert pb.WEIGHT_KEY != MawClawsOfThyraxNonOwnerPlaybook.KEY


def test_la_face_ATTACK_n_est_PAS_au_registre_et_c_est_LU():
    """`...MawClawsOfThyraxPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
    a pour corps ENTIER `yield return Fix64.op_Implicit(0)` : aucune lecture du case, aucun poids.

    L'inscrire au registre ATTACK n'ajouterait qu'un terme nul. Le test fige l'ARBITRAGE -- sans
    lui, « il manque une entree » se lirait comme un oubli et quelqu'un l'ajouterait."""
    from engine.playbook.psyker import TRIGGERED_ATTACK_PLAYBOOKS
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.playbook.adjacent_summons import MawClawsOfThyraxPlaybook
    assert int(TriggeredAbilityType.MawClawsOfThyrax) not in TRIGGERED_ATTACK_PLAYBOOKS
    assert not hasattr(MawClawsOfThyraxPlaybook, "calculate_attack_utility_in_steps")


class _Poids:
    """Duck-type minimal du `wt` que le dispatcher passe (`GetUtilityValue(<cle>)`)."""
    def __init__(self, v=5):
        self.v = v

    def sub(self, groupe, cle):
        assert groupe == "TriggeredAbilities"
        return self.v


def test_le_playbook_MOVE_compte_les_DEUX_camps_et_filtre_le_trait():
    """`GetAdjacentUnits(tile, null, null, false)` (slot `0x7a`, arite 4) filtre par
    `HasTrait(u, 0x2)`. Le corps natif n'a NI cap NI tri, et ne filtre AUCUN camp.

    ⚠ C'est le pendant DECISION du point d'execution : un port cale sur `GetAdjacentFriends`
    (slot `0x83`, ce que fait `KardiocoreGalvanusPlaybook`) manquerait les summons adverses."""
    from engine.playbook.adjacent_summons import MawClawsOfThyraxPlaybook
    pb = MawClawsOfThyraxPlaybook()
    tile = (2, 2)
    ctx = {"friend_units": [{"id": 1, "pos": (2, 3), "traits": ["Summon"]},
                            {"id": 2, "pos": (2, 1), "traits": ["Hero"]}],
           "enemy_units": [{"id": 3, "pos": (1, 2), "traits": ["Summon"]},
                           {"id": 4, "pos": (9, 9), "traits": ["Summon"]}]}
    # 1 ami Summon adjacent + 1 ennemi Summon adjacent = 2 ; le `Hero` adjacent et le Summon
    # LOINTAIN ne comptent pas.
    assert pb.calculate_movement_utility_in_steps(tile, ctx, _Poids(5)) == 10.0
    # poids nul -> le natif sommerait des zeros : on court-circuite, meme resultat.
    assert pb.calculate_movement_utility_in_steps(tile, ctx, _Poids(0)) == 0.0


def test_le_playbook_MOVE_compte_le_MOVER_LUI_MEME_quand_il_est_Summon():
    """`GetAdjacentUnits` travaille par TUILE et n'exclut PAS l'unite qui evalue -- encore sur son
    ORIGINE pendant tout le sweep. C'est le meme fait que l'en-tete de `friends_in_range.py`, et
    `SaviorProtocolsPlaybook` (MEME slot `0x7a`) doit ecrire un `!AreEqual(Target, Owner)`
    EXPLICITE pour s'exclure -- preuve que le natif ne l'exclut pas tout seul.

    DEGRADATION : `self_pos`/`unit_traits` absents (regime SPAWN) -> le mover n'est pas compte."""
    from engine.playbook.adjacent_summons import MawClawsOfThyraxPlaybook
    from engine.entities.traits.unit_trait import UnitTrait
    pb = MawClawsOfThyraxPlaybook()
    tile = (2, 2)
    base = {"friend_units": [], "enemy_units": []}
    # `unit_traits` du ctx est une liste d'IDS (`entity_trait_ids`), pas de noms.
    ctx = dict(base, self_pos=(2, 3), unit_traits=[int(UnitTrait.Summon)])
    assert pb.calculate_movement_utility_in_steps(tile, ctx, _Poids(5)) == 5.0
    assert pb.calculate_movement_utility_in_steps(
        tile, dict(base, self_pos=(9, 9), unit_traits=[int(UnitTrait.Summon)]), _Poids(5)) == 0.0
    assert pb.calculate_movement_utility_in_steps(
        tile, dict(base, self_pos=(2, 3), unit_traits=[int(UnitTrait.Hero)]), _Poids(5)) == 0.0
    assert pb.calculate_movement_utility_in_steps(tile, base, _Poids(5)) == 0.0


# ---------------------------------------------------------------------------------------------
# 6. LE SUBSTRAT -- les cles LA OU elles sont consommees
# ---------------------------------------------------------------------------------------------

def test_les_cles_du_compteur_sont_publiees_par_le_substrat_d_etat():
    """La `CreateActiveCondition` lit `unit_state[CARRIER_COUNT_KEY]` et le canal CRIT lit
    `att_ctx[CTX_COUNT_OF]`. Les deux noms doivent exister LA OU ils sont consommes, sinon l'effet
    degrade en « toujours actif, jamais de bonus » -- silencieusement.

    ⚠ LE CANAL CRIT SE MESURE, IL NE SE GREPPE PLUS (#10026). L'assertion d'origine cherchait
    `CTX_COUNT_OF` dans le SOURCE de `_crit_board` ; #1042-r5 y a remplace les litteraux par des
    ALIAS importes (`_CTX_ADJACENT_SUMMONS_OF`), et le grep est tombe alors que la cle etait
    toujours publiee -- un rouge qui n'accusait rien. La faute est symetrique et bien pire : le
    meme grep passe sur une cle qui n'est **plus** publiee des qu'un COMMENTAIRE la nomme, et
    `_crit_board` en nomme quatre pour dire qu'il ne les reutilise PAS. On interroge donc le dict
    RENDU, ce qui est strictement plus fort que le texte : la cle doit etre presente ET porter un
    callable (forme paresseuse par-porteur, cf. la docstring de `_crit_board`).

    Le `State()` nu suffit : les deux compteurs de ce foyer sont des lambdas, donc rien n'est
    calcule a la construction du dict."""
    from engine.entities.effects.loki import maw_claws_of_thyrax as M
    from engine.runner.components import UnitEffectStateView
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.state import State
    assert M.CARRIER_COUNT_KEY in inspect.getsource(UnitEffectStateView.__getitem__)
    assert M.CARRIER_COUNT_KEY in inspect.getsource(UnitEffectStateView.__iter__)
    board = AttackDamageOperation._crit_board(State(), None, None)
    assert board, "`_crit_board` rend un substrat VIDE : l'assertion suivante serait VACUE"
    assert M.CTX_COUNT_OF in board, (
        "`%s` n'est PAS publiee par `_crit_board` (cles vues : %s)"
        % (M.CTX_COUNT_OF, sorted(board)))
    assert callable(board[M.CTX_COUNT_OF]), (
        "`%s` doit rester un CALLABLE par-porteur : la boucle native ECRASE "
        "`AbilityEntities+0x18` a chaque iteration, donc la grandeur depend de l'instance d'effet "
        "qui interroge -- une valeur figee serait celle du dernier porteur" % (M.CTX_COUNT_OF,))
    # CONTRE-EPREUVE du critere lui-meme : un nom que `_crit_board` ne publie pas doit MANQUER.
    # Sans elle, un `board` qui rendrait tout (`defaultdict`, `__contains__` permissif) passerait.
    assert (M.CTX_COUNT_OF + "_absent") not in board, (
        "le substrat accepte n'importe quelle cle -- le test ci-dessus ne garde rien")


def test_le_gate_de_presence_de_la_cle_est_GEOMETRIQUE_SEUL():
    """⚠ La cle `adjacent_summons` est la SEULE de cette vue dont le gate n'exige PAS d'equipe :
    son selecteur est `AdjacentUnits`, qui ne filtre aucun camp. L'aligner sur `_has_sa` (position
    ET equipe), comme ses quatre voisines, rendrait la cle ABSENTE la ou le natif compte -- et la
    `CreateActiveCondition` degraderait alors en VRAI sur un porteur sans `OwnerComponent`.

    Le test lit le SOURCE : construire un `UnitEffectStateView` demande un `State` complet."""
    from engine.entities.effects.loki import maw_claws_of_thyrax as M
    from engine.runner.components import UnitEffectStateView, adjacent_summons_count
    src = inspect.getsource(UnitEffectStateView.__getitem__)
    ligne = next(l for l in src.splitlines() if 'key == "%s"' % M.CARRIER_COUNT_KEY in l)
    assert "_has_pos" in ligne, ("le gate de `%s` doit etre `_has_pos` (POSITION seule), lu : %s"
                                 % (M.CARRIER_COUNT_KEY, ligne.strip()))
    # ... et le compteur lui-meme ne doit exiger qu'une POSITION.
    csrc = inspect.getsource(adjacent_summons_count)
    assert "get_component(OwnerComponent)" not in csrc, (
        "`adjacent_summons_count` ne doit PAS exiger d'equipe : `AdjacentUnits` n'en lit aucune")
    assert "get_component(PositionComponent)" in csrc, (
        "le selecteur est GEOMETRIQUE : sans tuile le compteur doit rendre `None`, pas 0")


def test_1461_a_sa_classe_au_registre():
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.maw_claws_of_thyrax import MawClawsOfThyraxExtraCritDmgEffect
    assert EFFECT_CLASSES.get(EFFECT_NAME) is MawClawsOfThyraxExtraCritDmgEffect


@pytest.mark.parametrize("mod", [
    "engine.entities.effects.loki.maw_claws_of_thyrax",
    "engine.playbook.adjacent_summons",
])
def test_le_module_s_importe_SEUL_en_process_frais(mod):
    """Cliquet #433-r1 : chaque module d'`engine/**` doit s'importer seul. Une arete neuve le
    casserait sans qu'aucun test fonctionnel ne bouge."""
    import subprocess
    import sys as _s
    r = subprocess.run([_s.executable, "-c", "import " + mod], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]
