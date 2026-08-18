"""GARDE OFFLINE de `NetherRealmCasket` (`TriggeredAbilityType` 0x5b6 = 1462) -- #908.

Les MESURES vivent dans les deux probes (`probe_908_nether_realm_casket_repair_live.py`,
`probe_908_nether_realm_casket_crit_live.py`). CE fichier garde ce qu'une PR ulterieure pourrait
casser SANS qu'aucun test live ne soit joue -- et chaque etage nomme la faute qu'il attrape.

Les CHIFFRES confrontes live (build `rnca9r7q6c`), pour que le lecteur sache ce que ces gardes
protegent :
  * REPAIR  -- porteur `necroDestroyer` relique niveau 3, maxHP 40000 : LIVE `+5086` =
    `round_half_even(10 % x 40000) = 4000` + `hpToHeal[3] = 1086` ; temoin `necroOverlord`
    (LivingMetal, sans relique) `+4000` dans le MEME endturn. Port identique aux deux.
  * CRIT    -- relique niveau 3, `critDmgReduction[3] = 432` : `n = 0` -> aucun terme,
    `n = 1` -> `-432`, `n = 2` -> `-864`, salves LIVE differentes et EGALES au port coup par coup.
  * ETAGE `NormalUnits` -- un compagnon `LivingMetal` **+ `Steppable`** pose ADJACENT n'est compte
    NI par le natif (`actif_natif=False`) NI par le port.

ASCII only (console cp1252).
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
        # LE MODULE D'EFFET et son registre : l'arbre du compteur, les gates, la magnitude.
        "scripts/python/engine/entities/effects/loki/nether_realm_casket.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects/base.py",
        # LES TROIS ENUMS dont ce fichier fige les ordinaux (et la collision 1457).
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/ability_variable_type.py",
        # LES NOEUDS DSL du compteur : un etage retire ou une signature changee doit rougir ici.
        "scripts/python/engine/entities/selectors/units.py",
        "scripts/python/engine/entities/selectors/accessors.py",
        "scripts/python/engine/entities/formulas.py",
        # `IsMechanical` -- le predicat a TROIS traits, load-bearing sur le camp necron.
        "scripts/python/engine/runner/abilities/behaviours/stats.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        # LE CANAL REPAIR de bout en bout : foyer de la regle, les trois etages du rail COMBAT,
        # et le SEUL call-site qui arme la cause.
        "scripts/python/engine/predict.py",
        "scripts/python/engine/runner/operations/repair.py",
        "scripts/python/engine/runner/operations/triggers/loki/living_metal.py",
        "scripts/python/engine/runner/operations/triggers/base.py",
        # LE SUBSTRAT D'ETAT du compteur (cle du `unit_state`) et le canal CRIT (callable par
        # porteur) : les deux points ou la cle peut disparaitre EN SILENCE.
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/operations/damage.py",
    ),
    # `build: True` -- les ordinaux figes (etape 1) et les paliers `critDmgReduction`/`hpToHeal`
    # (etapes 3 et 4) sont RELUS du gameconfig VIVANT et des mirrors d'enum : un changement de
    # build peut les deplacer, et c'est precisement ce que ce fichier doit rougir.
    "build": True,
    "toujours": False,
    "raison": (
        "Ce fichier garde le port de `NetherRealmCasket` (1462) et de ses DEUX effets -- 1455 sur "
        "le canal crit-DEGAT (classe d'effet), 1456 sur le canal `BaseEffect$$RepairBonus` (foyer "
        "`engine.predict`). Les chemins listes sont ceux dont une modification peut faire changer "
        "un verdict de ce fichier : le mirror lui-meme, les trois enums qu'il fige, les noeuds DSL "
        "du compteur, le predicat `IsMechanical`, et les quatre etages du canal de cause."),
}


# ---------------------------------------------------------------------------------------------
# 1. LES ORDINAUX, figes a la valeur MESUREE -- et la collision qui rend le nom obligatoire
# ---------------------------------------------------------------------------------------------

def test_les_ordinaux_du_cas_sont_ceux_du_build():
    """Un ordinal juste aujourd'hui devient faux au changement de build, EN SILENCE. Ces cinq-la
    sont ceux que le decompile a rendus, chacun relu a sa source :

      * `EffectType` 0x5af / 0x5b0 = les DEUX `AddEffect` de
        `...NetherRealmCasketAbility$$CreateBehaviour` ;
      * `TriggeredAbilityType` 0x5b6 = le litteral du `.ctor` de l'effet 1456
        (`ba b6 05 00 00`) ET le `source` des deux descripteurs `EffectBonus` ;
      * `AbilityVariableType` 0x97 / 0x20 = les deux `ConfigVar` ;
      * `TriggeredAbilityType` 0x3f2 = l'argument de `TriggeringAbilityIs`."""
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.entities.ability_variable_type import AbilityVariableType
    assert int(EffectType.NetherRealmCasket_CritDamageReduction) == 0x5af == 1455
    assert int(EffectType.NetherRealmCasket_LivingMetalBonus) == 0x5b0 == 1456
    assert int(TriggeredAbilityType.NetherRealmCasket) == 0x5b6 == 1462
    assert int(TriggeredAbilityType.LivingMetalRepair) == 0x3f2 == 1010
    assert int(AbilityVariableType.critDmgReduction) == 0x97 == 151
    assert int(AbilityVariableType.hpToHeal) == 0x20 == 32


def test_la_collision_1457_existe_et_c_est_elle_qui_rend_le_NOM_obligatoire():
    """`EffectType.RelicBoltPistol_ExtraPierce` **et** `TriggeredAbilityType.KardiocoreGalvanus`
    valent TOUS DEUX 1457, a un cran des ordinaux de ce cas.

    Ce test ASSERTIONNE SA PROPRE PREMISSE : si un build faisait disparaitre la collision, un test
    qui se contenterait de « les deux enums different » passerait pour vert sans rien mesurer."""
    from engine.entities.effect_type import EffectType
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    a, b = int(EffectType.RelicBoltPistol_ExtraPierce), int(TriggeredAbilityType.KardiocoreGalvanus)
    assert a == b == 1457, ("la collision d'ordinal a DISPARU du build (%d / %d) : ce test ne "
                            "mesure plus rien, le re-deriver au lieu de le supprimer" % (a, b))
    # et les deux nomment bien AUTRE CHOSE -- c'est le seul canal ou la faute serait visible.
    assert EffectType.RelicBoltPistol_ExtraPierce.name != TriggeredAbilityType.KardiocoreGalvanus.name


# ---------------------------------------------------------------------------------------------
# 2. LE COMPTEUR -- un arbre DSL de TROIS etages, et chacun est load-bearing
# ---------------------------------------------------------------------------------------------

def test_le_compteur_est_l_arbre_natif_a_trois_etages():
    """`AdjacentMechanicalUnits` = `Count(MechanicalUnits(NormalUnits(AdjacentFriends(Owner, 1, 3),
    3), 3))`. Le test lit la STRUCTURE de l'arbre, pas une valeur : c'est ce qui attrape un port
    qui « simplifierait » un etage.

    L'etage `NormalUnits` a ete confronte LIVE (compagnon `LivingMetal` + `Steppable` : natif et
    port comptent 0) ; le retirer rendrait le compteur PERMISSIF."""
    from engine.entities.effects.loki.nether_realm_casket import (
        adjacent_mechanical_units_selector, SELECTION_TYPE)
    from engine.entities.selectors.units import AdjacentFriends, MechanicalUnits, NormalUnits
    from engine.entities.selectors.accessors import Owner
    from engine.entities.formulas import Count

    arbre = adjacent_mechanical_units_selector()
    assert isinstance(arbre, Count)
    mech = arbre.source if hasattr(arbre, "source") else arbre.selector
    assert isinstance(mech, MechanicalUnits), "etage MechanicalUnits absent : %r" % (mech,)
    normal = mech.source
    assert isinstance(normal, NormalUnits), (
        "etage NormalUnits absent -- il ECARTE les Object/Steppable, et le natif le porte : %r"
        % (normal,))
    adj = normal.entities
    assert isinstance(adj, AdjacentFriends)
    assert isinstance(adj.center, Owner) and isinstance(adj.reference, Owner), (
        "`AdjacentFriends(unit = Owner, ...)` : le centre ET la reference d'equipe sont l'Owner")
    # le litteral `selectionType = 3` est PROPAGE aux trois etages (variante A d'`AdjacentFriends`,
    # tranchee par la CIBLE de son `call` -- `0x180eac2a0`).
    assert SELECTION_TYPE == 3
    assert mech.selection_type == 3 and normal.selection_type == 3 and adj.selection_type == 3


def test_MechanicalUnits_couvre_les_TROIS_traits_pas_seulement_Mechanical():
    """`UnitExtensions$$IsMechanical` = `Mechanical 5 | LivingMetal 1000 | Vehicle 0x405`.

    Load-bearing ICI plus qu'ailleurs : la relique est NECRON, tout le roster necron porte
    `LivingMetal`, et plusieurs SANS `Mechanical`. Le bras live `--trait LivingMetal` du probe
    mesure exactement ce point -- le natif COMPTE ces compagnons."""
    from engine.runner.abilities.behaviours.stats import is_mechanical
    from engine.entities.traits.unit_trait import UnitTrait
    for trait in (UnitTrait.Mechanical, UnitTrait.LivingMetal, UnitTrait.Vehicle):
        ht = (lambda u, t, _w=int(trait): int(t) == _w)
        assert is_mechanical(ht, {"id": 1}), "IsMechanical rate %s" % trait.name
    assert not is_mechanical(lambda u, t: False, {"id": 1})


# ---------------------------------------------------------------------------------------------
# 3. LA MAGNITUDE CRIT -- un PRODUIT signe, etage par etage (jamais un scalaire fitte)
# ---------------------------------------------------------------------------------------------

def _effet_crit(level=3, mult=100):
    """Instancie l'effet PAR LE REGISTRE (jamais la classe importee en direct) : c'est le chemin
    que suit la factory quand elle materialise un effet CAPTE."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effect_type import EffectType
    cls = EFFECT_CLASSES["NetherRealmCasket_CritDamageReduction"]
    return cls("NetherRealmCasket_CritDamageReduction",
               effect_type=int(EffectType.NetherRealmCasket_CritDamageReduction),
               level=level, ability_level=level, ability_variables_multiplier=mult)


def test_le_bonus_crit_est_le_PRODUIT_signe_negativement():
    """`ForSubtraction(get_OwnerIsTarget, Multiply(ConfigVar(0x97), AdjacentMechanicalUnits()))`.

    Le retour NEGATIF n'est pas une convention locale : `GetCritDamageBonusFromEffects` accumule
    `addition - subtraction`, et `CalculateCriticalDamage` fait `Math.Max(0, GetStat(10) + somme)`.
    Chiffres confrontes live a `critDmgReduction[3] = 432` : n=1 -> -432, n=2 -> -864."""
    import gameconfig as GC
    paliers = ((GC.ability("NetherRealmCasket") or {}).get("variables") or {}).get("critDmgReduction")
    assert paliers and len(paliers) >= 3, "paliers absents du gameconfig : %r" % (paliers,)
    v3 = int(paliers[2])
    e = _effet_crit(level=3)
    for n in (1, 2, 3):
        ctx = {"owner_id": 7, "tgt_id": 7,
               "adjacent_friendly_mechanical_units_of": (lambda oid, _n=n: _n)}
        assert e.create_effect_crit_damage_bonus_for_attack(ctx) == -v3 * n


def test_les_gates_du_bonus_crit_se_TAISENT_chacun_pour_sa_raison():
    """Trois portes, trois `None` -- et aucune n'est permissive :

      * `get_OwnerIsTarget` faux (le porteur n'est pas le defenseur) ;
      * identite NON PROUVEE (une des deux cles absente) -> noeud FAUX, jamais VRAI ;
      * compteur NON MESURE (`None`) -> pas de produit invente. Un 0 rendu a la place ferait
        passer une reduction reelle pour une absence de reduction."""
    e = _effet_crit()
    assert e.create_effect_crit_damage_bonus_for_attack(
        {"owner_id": 7, "tgt_id": 8,
         "adjacent_friendly_mechanical_units_of": lambda oid: 3}) is None
    assert e.create_effect_crit_damage_bonus_for_attack(
        {"owner_id": 7, "adjacent_friendly_mechanical_units_of": lambda oid: 3}) is None
    assert e.create_effect_crit_damage_bonus_for_attack(
        {"owner_id": 7, "tgt_id": 7,
         "adjacent_friendly_mechanical_units_of": lambda oid: None}) is None
    # compteur NUL -> `Multiply` rend 0, et `ForSubtraction(0)` ne verse rien (mesure live n=0).
    assert e.create_effect_crit_damage_bonus_for_attack(
        {"owner_id": 7, "tgt_id": 7,
         "adjacent_friendly_mechanical_units_of": lambda oid: 0}) is None


def test_la_condition_d_activite_est_le_MEME_compteur_compare_a_zero():
    """`CreateActiveCondition` = `AmountIsGreaterThanZero(<le MEME compteur>)`.

    Cle ABSENTE = NON MESURE -> on NE FERME PAS (degradation fidele : masquer l'effet a tort serait
    pire que le laisser actif, et le natif ne peut pas etre dans cet etat)."""
    e = _effet_crit()
    assert e.active_condition_ported is True
    assert e.is_active({"adjacent_friendly_mechanical_units": 1}) is True
    assert e.is_active({"adjacent_friendly_mechanical_units": 0}) is False
    assert e.is_active({}) is True
    assert e.is_active(None) is True


# ---------------------------------------------------------------------------------------------
# 4. LE CANAL REPAIR -- le gate de CAUSE, et ce qui arrive s'il disparait
# ---------------------------------------------------------------------------------------------

def test_le_bonus_repair_exige_la_cause_LivingMetalRepair():
    """`ForAddition(get_OwnerIsTarget & TriggeringAbilityIs(LivingMetalRepair 0x3f2),
    ConfigVar(0x20 = hpToHeal))`.

    `get_OwnerIsTarget` est porte par la BOUCLE (`target_effects` = les seuls effets de la CIBLE) ;
    ce qui reste est le gate de CAUSE. Cause ABSENTE ou AUTRE -> aucun terme, jamais un bonus
    verse « au cas ou » : c'est ce qui garde la face DECISION exacte (elle ne declenche jamais
    `LivingMetalRepair`, donc elle ne doit RIEN voir).

    Le mutant `NOCAUSE` du probe mesure exactement ce point LIVE : 4000 au lieu de 5086."""
    from engine.predict import calculate_repair_modifier_for_prediction as C
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    rows = [{"name": "NetherRealmCasket_LivingMetalBonus", "level": 3, "source": None}]
    assert C(rows) == (0, 1.0)                                        # cause NON threadee
    # AUTRE cause : la relique ELLE-MEME (1462) -- volontairement proche, pour que le test attrape
    # une confusion entre le `source` du descripteur et l'argument de `TriggeringAbilityIs`.
    assert C(rows, ability_or_effect=int(TriggeredAbilityType.NetherRealmCasket)) == (0, 1.0)
    add, mul = C(rows, ability_or_effect=int(TriggeredAbilityType.LivingMetalRepair))
    assert mul == 1.0 and add > 0, "la cause juste doit verser un terme ADDITIF"


def test_le_niveau_du_bonus_repair_vient_de_l_AbilityState_TERTIAIRE():
    """`ConfigVar(0x20, GetAbilityState(effect), config@+0x60)`.

    Sans le canal #357, le foyer indexe `hpToHeal` par le `level` de l'EFFET CAPTE -- qui n'a
    AUCUN rapport avec le niveau de la relique. MESURE (bras `PASSIF` du probe) : 980 au lieu de
    1086, la ou le natif rend 1086. `ability_state_of` est ce qui corrige."""
    import gameconfig as GC
    from engine.predict import calculate_repair_modifier_for_prediction as C
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    paliers = ((GC.ability("NetherRealmCasket") or {}).get("variables") or {}).get("hpToHeal")
    assert paliers and len(paliers) >= 7
    cause = int(TriggeredAbilityType.LivingMetalRepair)
    rows = [{"name": "NetherRealmCasket_LivingMetalBonus", "level": 1, "source": None}]
    # sans canal : le niveau de l'EFFET (1) -> premier palier
    assert C(rows, ability_or_effect=cause)[0] == int(paliers[0])
    # avec canal : le niveau TERTIAIRE l'emporte
    assert C(rows, ability_or_effect=cause,
             ability_state_of=lambda name: (7, 100))[0] == int(paliers[6])
    # canal present mais MUET (`(None, None)`) -> repli, jamais une exception
    assert C(rows, ability_or_effect=cause,
             ability_state_of=lambda name: (None, None))[0] == int(paliers[0])


def test_le_canal_de_cause_traverse_les_TROIS_etages_du_rail_COMBAT():
    """`RepairBehaviour+0x68` -> `RepairUnitOperation$$Execute` -> `PredictRepair` ->
    `CalculateRepairModifierForPrediction`. Le port doit porter le parametre a CHAQUE etage --
    l'oublier a UN seul le rend inatteignable, en silence."""
    from engine.runner.operations.repair import RepairUnitOperation, predict_repair, _repair_modifier
    for fn in (RepairUnitOperation.execute, predict_repair):
        assert "ability_or_effect" in inspect.signature(fn).parameters, fn
    assert "ability_or_effect" in inspect.signature(_repair_modifier).parameters


def test_le_SEUL_call_site_qui_arme_la_cause_est_LivingMetal():
    """`...LivingMetalRepairAbility$$CreateBehaviour` passe `cause = AbilityOrEffect(
    LivingMetalRepair 0x3f2)` -- c'est le seul du build qui peut satisfaire le gate.

    Ce test attrape la regression exacte que #908 a levee : la cause etait CONSTRUITE par le natif
    et JETEE par le port."""
    from engine.runner.operations.triggers.loki import living_metal as LM
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    assert LM.REPAIR_CAUSE == int(TriggeredAbilityType.LivingMetalRepair)
    src = inspect.getsource(LM.LivingMetalRepairAbility.execute_behaviour)
    assert "ability_or_effect=REPAIR_CAUSE" in src, (
        "le trigger LivingMetal doit PASSER sa cause a l'Operation, sinon le gate "
        "`TriggeringAbilityIs` est inatteignable et le bonus 1456 vaut 0 partout")


# ---------------------------------------------------------------------------------------------
# 5. LES DEUX EFFETS, ET LEURS CANAUX DE PORT -- l'un a une classe, l'autre PAS, et c'est un CHOIX
# ---------------------------------------------------------------------------------------------

def test_1455_a_sa_classe_et_1456_n_en_a_DELIBEREMENT_pas():
    """1455 est un `CreateCritDamageBonus` -> il lui faut une classe (gates + magnitude + niveau).
    1456 est un `BaseEffect$$RepairBonus` -> sa regle vit dans le foyer UNIQUE
    `engine.predict.calculate_repair_modifier_for_prediction`, comme celle de ses DEUX
    co-implementeurs. Une classe pour 1456 dupliquerait la regle : un fork, pas un port.

    Le test fige les deux moities du choix -- sans quoi « il manque une entree » se lirait comme un
    oubli et quelqu'un l'ajouterait."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki.nether_realm_casket import (
        NetherRealmCasketCritDamageReductionEffect, LIVING_METAL_BONUS_EFFECT_NAME)
    assert (EFFECT_CLASSES.get("NetherRealmCasket_CritDamageReduction")
            is NetherRealmCasketCritDamageReductionEffect)
    assert LIVING_METAL_BONUS_EFFECT_NAME not in EFFECT_CLASSES
    # ... et ses deux co-implementeurs du MEME canal non plus : c'est la coherence de l'arbitrage.
    assert "NanoscarabRepairProtocols" not in EFFECT_CLASSES
    assert "VoltagheistField_RepairReduction" not in EFFECT_CLASSES


def test_la_cle_du_compteur_est_publiee_par_le_substrat_d_etat():
    """La `CreateActiveCondition` lit `unit_state[CARRIER_COUNT_KEY]` et le canal CRIT lit
    `att_ctx[CTX_COUNT_OF]`. Les deux noms doivent exister LA OU ils sont consommes, sinon l'effet
    degrade en « toujours actif, jamais de bonus » -- silencieusement.

    ⚠ CE CRAN ETAIT UN FAUX VERT, ET C'EST MESURE (#10026). L'assertion du canal CRIT cherchait
    `CTX_COUNT_OF` dans le SOURCE de `_crit_board` ; or ce source NOMME quatre cles voisines dans
    ses COMMENTAIRES, precisement pour dire qu'il ne les reutilise PAS. Contre-epreuve jouee :
    `_CTX_ADJACENT_FRIENDLY_MECHANICAL_UNITS_OF` remplace par un nom mort dans le dict rendu ->
    la cle N'EST PLUS PUBLIEE et ce fichier restait **14 passed**. On interroge donc le dict RENDU,
    ce qui rougit dans ce regime (verifie). Le jumeau de ce cran vit dans
    `tests/engine/test_920_maw_claws_of_thyrax_offline.py`."""
    from engine.entities.effects.loki import nether_realm_casket as NRC
    from engine.runner.components import UnitEffectStateView
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.state import State
    assert NRC.CARRIER_COUNT_KEY in inspect.getsource(UnitEffectStateView.__getitem__)
    assert NRC.CARRIER_COUNT_KEY in inspect.getsource(UnitEffectStateView.__iter__)
    board = AttackDamageOperation._crit_board(State(), None, None)
    assert board, "`_crit_board` rend un substrat VIDE : l'assertion suivante serait VACUE"
    assert NRC.CTX_COUNT_OF in board, (
        "`%s` n'est PAS publiee par `_crit_board` (cles vues : %s)"
        % (NRC.CTX_COUNT_OF, sorted(board)))
    assert callable(board[NRC.CTX_COUNT_OF]), (
        "`%s` doit rester un CALLABLE par-porteur : la boucle native ECRASE "
        "`AbilityEntities+0x18` a chaque iteration" % (NRC.CTX_COUNT_OF,))
    assert (NRC.CTX_COUNT_OF + "_absent") not in board, (
        "le substrat accepte n'importe quelle cle -- le test ci-dessus ne garde rien")


@pytest.mark.parametrize("mod", [
    "engine.entities.effects.loki.nether_realm_casket",
])
def test_le_module_s_importe_SEUL_en_process_frais(mod):
    """Cliquet #433-r1 : chaque module d'`engine/**` doit s'importer seul. Une arete neuve le
    casserait sans qu'aucun test fonctionnel ne bouge."""
    import subprocess
    import sys as _s
    r = subprocess.run([_s.executable, "-c", "import " + mod], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]
