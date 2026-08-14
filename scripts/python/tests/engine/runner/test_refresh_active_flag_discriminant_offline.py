"""#366-r1b -- QUI a le droit d'ECRIRE `EffectComponent.IsActive @+0x5c` au refresh.

`IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` (branche `refreshType == Normal`) a
DEUX regimes, lus verbatim :

    if (effectComponent.<+0x5e>)                    return false;
    if (!effect.ShouldRefreshForTrigger(trigger))   return effectComponent.<+0x5c>;   # CONSERVER
    return effect.ShouldBeActive(entities);                                            # RE-EVALUER

Le port n'a NI `RefreshEffectTrigger` NI `ShouldRefreshForTrigger` : il ne peut pas mirrorer le CHOIX
natif du regime. `refresh_stat_modifier_effects` decide donc sur ce qu'il PEUT lire -- la classe
porte-t-elle vraiment sa `CreateActiveCondition` (= surcharge-t-elle `is_active`) ?

CE FICHIER RETIENT LA LECON, parce qu'AUCUN test ne retenait le regime « effet seede INACTIF dont la
condition PORTEE devient vraie en cours de sim » : c'est par HASARD que
`test_contagions_lifecycle_live` l'a attrape. Les quatre regimes sont ici, OFFLINE et deterministes.

Historique, a garder : le discriminant avait d'abord ete pris sur `BaseEffect.active_condition_ported`.
Ce drapeau repond a une AUTRE question (« le flag CAPTE au seed est-il PERIME parce que la condition
porte sur l'etat SIMULE ? », case-322) et n'est pose que par UNE classe. Resultat : les 12 autres
classes a condition portee etaient VERROUILLEES -- une instance seedee `active=False` (le canal
`includeInactive` de `snapshot.decision_view_seed_body` publie bien `active: false`) ne pouvait plus
JAMAIS se rallumer. Mesure : `test_contagions_lifecycle_live`, aura qui grandit, live
`actif=[1072] armure=1387` contre port `actif=[] armure=2312`.

ASCII only.
"""
from __future__ import annotations

#: `chemins` est VIDE, et c'est une MESURE, pas un oubli : `probe_486r15 --proposer` rend
#: « RIEN A DECLARER hors de la cascade » -- la fermeture d'imports de ce fichier (474 modules)
#: tient entierement dans la cascade DERIVEE par le foyer (475 chemins), qu'on ne redeclare pas
#: (#531). Ce fichier ne lit ni le binaire ni `data/symbols/**` : son unique source est le
#: REGISTRE Python `EFFECT_CLASSES`, introspecte a l'execution -- d'ou `build: False`. Ce qu'il
#: prouve : (a) le discriminant du refresh reste la SURCHARGE de `is_active` et jamais le drapeau
#: `active_condition_ported` (case-322), et (b) l'ensemble des classes surchargeantes ne bouge
#: dans AUCUN des deux sens sans etre inscrit -- c'est le cliquet que #229-r2 disait absent.
DECLENCHEUR = {
    "chemins": (),
    "build": False,
    "toujours": False,
    "raison": "Aucun chemin hors cascade : la fermeture d'imports de ce fichier y tient en "
              "entier (mesure `--proposer`). La seule source de verite du cliquet est le "
              "registre `EFFECT_CLASSES` introspecte a l'execution, deja couvert par "
              "`scripts/python/engine/**` de la cascade ; rien n'est fige depuis le binaire, "
              "donc `build: False`.",
}

from engine.entities.effects_state import EffectsState
from engine.entities.effects.base import BaseEffect
from engine.entities.effects.factory import EFFECT_CLASSES, EffectFactory
from engine.entities.effect_type import EffectType
from engine.entities.unit_context import UnitContext
from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                      StatsComponent, UnitComponent)
from engine.runner.operations.refresh_effects import (_active_condition_is_ported,
                                                      refresh_stat_modifier_effects)
from engine.runner.state import State

# Deux temoins REELS du registre, un par regime -- pas des doubles de test : c'est la production
# qu'on garde.
PORTED = "PowerTrip_FullHealth"            # surcharge `is_active` (condition = PV pleins)
UNPORTED = "WireweaveNet_CounterAttack"    # ne la surcharge PAS ; son flag n'est ecrit que par les
#                                            feuilles `ActivateEffect`/`DeactivateEffect` (la riposte
#                                            1111 se DESARME apres son coup -- si le refresh la
#                                            rallumait, elle repartirait le meme tour)

# #229-r2 -- ENSEMBLE ATTESTE, pas un plancher. Ce fichier a d'abord garde `len(overrides) >= N`,
# remonte A LA MAIN par quatre commits successifs (16, 17, 18, 20). Un seuil est UNIDIRECTIONNEL :
# il rougit quand une surcharge DISPARAIT, jamais quand une ARRIVE -- donc il se perime en silence,
# ce que ce fichier constatait lui-meme DEUX fois (« une classe entree sans que le plancher bouge »)
# sans pouvoir l'empecher. Mesure a la reprise : plancher ecrit **20**, classes reellement
# surchargeantes **21** -- le cliquet etait en retard d'une, et VERT.
#
# L'ensemble nomme corrige les deux defauts d'un coup :
#   * il rougit dans les DEUX sens (arrivee non inscrite ET disparition) ;
#   * il FUSIONNE PAR UNION entre deux branches paralleles. C'est la reponse a l'avertissement
#     « ce plancher ne se choisit pas entre deux branches en conflit » : sur un NOMBRE, prendre
#     « le mien » (18) ou « le sien » (17) donne un resultat FAUX des deux cotes puisque les deux
#     s'ajoutent ; sur un ENSEMBLE, garder les deux lignes est la resolution evidente.
#
# TU AJOUTES UNE `CreateActiveCondition` PORTEE (surcharge de `is_active`) ? Inscris son nom ici
# DANS LE MEME COMMIT -- meme regle que `TARGETING_OPTIONS`/`ABILITY_ATTACK_TYPE` au registre des
# abilities. Ce n'est pas une loi : c'est l'etat MESURE, et le test dit lequel des deux sens a bouge.
CONDITIONS_PORTEES_ATTESTEES = {
    "AmuletOfTheVoidwyrm_CritDamageReduction",
    "AnvilShield_BlockChanceBelowHealthCap",
    # #576-r1 -- `IsCharging(Owner@sel+0x30, Target@sel+0x60)`, CONSTANTE FAUSSE : le contexte de
    # `RefreshEffectsOperation$$ShouldBeActive` ne renseigne pas `ctx+0x10`, que lit
    # `Selectors.TargetSelector$$Select`. Rendre une constante EST une lecture du natif.
    "BloodChalice_ExtraPiercing",
    "CamoCloak_DmgReduction",
    # #1015-r1 -- `CloseCombatWeakness_ReduceDmg_Effect$$CreateActiveCondition` a pour corps ENTIER
    # `return NearbyEnemiesCondition()`, dont le terme dominant est
    # `HasAdjacentEnemies(Caster@+0x48, CasterTile@+0x50, false, false)` : MEME famille GEOMETRIQUE
    # et MEME noeud que `SupaCyborkBody_CritDmgReduction` juste plus bas, donc meme arbitrage --
    # le flag capte decrit la position REELLE et ne predit rien d'une TUILE SIMULEE.
    # ⚠ La condition est COMMUNE aux deux branches du malus : le `If(IsMeleeAttack, ...)` vit dans
    # la MAGNITUDE, pas ici. Le vert LIVE de la branche melee (x0.50 bit-exact) couvre donc la
    # condition en entier, y compris pour la branche RANGED qui reste non confrontee (#1015-r3).
    "CloseCombatWeakness_ReduceDmg",
    "ContagionsOfNurgle_ArmorReduction1",
    "ContagionsOfNurgle_ArmorReduction2",
    # #943 -- SIX classes arrivees entre le 2026-08-10 et le 2026-08-11 sans leur ligne, ce qui
    # rendait `master` ROUGE ici ET sur `test_camo_seed_inventory_offline`. Conditions toutes LUES
    # (verdicts de pose inscrits dans `probe_366_camo_seed_inventory.POSE_VECTOR` par le meme
    # commit) :
    #   * les DEUX de 1203 `DaemonicPatrons` (#911) --
    #     `ADaemonicPatronsEffect$$CreateActiveCondition` = `AmountIsGreaterThanZero(Count(Filter(
    #     AdjacentEnemies(Owner), HasEffect(It, 0x1b Taunted_OnlySpecificTargets, onlyActive: 0))))`,
    #     le MEME compteur que la magnitude : condition et magnitude ne peuvent pas diverger ;
    #   * 1459 `IntoxicatingElixir` (#919) -- `AmountIsGreaterThanZero(GetLevelFormula(...))`,
    #     geometrique (unites debuffees dans le rayon) ;
    #   * 1461 `MawClawsOfThyrax_ExtraCritDmg` (#917) -- `AmountIsGreaterThanZero(Count(Unique(
    #     UnitsWithTrait(AdjacentUnits(Owner), Summon))))`, geometrique ;
    #   * 1455 `NetherRealmCasket_CritDamageReduction` (#909) -- `AmountIsGreaterThanZero(
    #     AdjacentMechanicalUnits())`, geometrique ;
    #   * 1529 `RitesOfMorkai_ExtraDamage` (#904/#906) -- `HasTrait(Owner, 0x3f6 FinalJustice)
    #     op_BitwiseOr HasEffect(Owner, 0x5ae FinalVengeance_UnitEffect, onlyActive: 0, Both)`.
    "DaemonicPatrons_DmgReduction",
    "DaemonicPatrons_ExtraDamage",
    "DestroyTheWitch_ExtraDamage",
    "DestroyTheWitch_ExtraMove",
    # #962 -- TROIS classes arrivees les 2026-08-11/12 sans leur ligne, ce qui rendait `master`
    # ROUGE ici ET sur `test_camo_seed_inventory_offline` (meme couple, meme cause qu'en #943).
    # Conditions LUES au decompile `rnca9r7q6c`, verdicts de pose inscrits dans
    # `probe_366_camo_seed_inventory.POSE_VECTOR` par le meme commit :
    #   * les DEUX de 1314 `EnmityForTheUnworthy` (#948) --
    #     `..._ExtraDamageEffect$$CreateActiveCondition` =
    #     `AmountIsGreaterThanZero(AdjacentFriendlyDarkaUnitsAmount())` et
    #     `..._ExtraDamagePctEffect$$CreateActiveCondition` =
    #     `AmountIsGreaterThanZero(AdjacentUnitsAmount())` : deux compteurs GEOMETRIQUES distincts
    #     (avec/sans filtre de faction), donc les deux lignes ne sont pas une redondance ;
    #   * 1263 `Skullsmasher_ExtraDamage` (#953/#954) --
    #     `AmountIsGreaterThanZero(GetMissingHealthSteps())`, qui bascule sur les PV du porteur.
    "EnmityForTheUnworthy_ExtraDamage",
    "EnmityForTheUnworthy_ExtraDamagePct",
    # #962 (second lot, apporte par le REBASE) -- les DEUX auras de `1490 GrimEfficiency` (#959).
    # `CreateActiveCondition` LUES et DIFFERENTES : `HasEffect(EffectSource(Effect@+0x38), <stance>,
    # onlyActive: 0, Both)` sur `0x5c7` (HostileAcquisition) et `0x5c8` (FortifyTakeover). Elles
    # PARTITIONNENT les stances du trait `PrioritisedEfficiency` (1059), donc elles ne sont jamais
    # actives ensemble -- c'est le SEUL discriminant entre les deux classes, avec la variable et le
    # stat. La condition est REELLE et le port la lit : le marqueur de stance est SEEDE depuis
    # l'etat live (sa pose vit dans un substrat persistent-data absent du port, residu #121), donc
    # sans cette lecture le flag `active` d'une instance seedee (defaut True) ouvrirait l'aura de
    # la MAUVAISE stance.
    "GrimEfficiency_ExtraArmor",
    "GrimEfficiency_ExtraPierce",
    "HammerOfWrath_ConditionalDamage",
    # #1045 -- `1568 HeadwoppasKillchoppa_ExtraDmg` (#1012-r1), arrivee sans sa ligne : MEME couple de
    # rouges qu'en #943 et #962 (ici ET sur `test_camo_seed_inventory_offline`, ou elle etait l'unique
    # `INCONNU`). Condition RELUE au decompile `rnca9r7q6c` :
    # `...Effects.Loki.HeadwoppasKillchoppaEffect$$CreateActiveCondition` =
    # `AmountIsGreaterThanZero( EffectLevel(Effect@DSLSelectors+0x38) )` -- verbatim, un seul
    # `DSLFormulas$$EffectLevel` passe a un seul `DSLTriggers$$AmountIsGreaterThanZero`.
    # ⚠ POURQUOI LA LECTURE EST LOAD-BEARING ICI, et pas cosmetique : l'effet naît au niveau **0**
    # (`...HeadwoppasKillchoppaAbility$$CreateBehaviour` passe `<DSLFormulas+0x18>` en 3e champ des
    # `options`, et `DSLFormulas$$.ctor` construit ce slot avec le scalaire `0` -- `Direct(0)`), donc
    # la condition est FAUSSE a la pose. Sans cette ligne, le refresh ne re-evalue pas la classe :
    # l'instance seedee resterait a l'etat de son flag capte, alors que le compteur monte
    # (`IncreaseEffectLevelOperation$$Execute` incremente `EffectComponent+0x68`, le NIVEAU) --
    # exactement le regime de `test_contagions_lifecycle_live` cite en tete de fichier.
    # ⚠ ET LE GATE NE DOIT PAS REMONTER PLUS HAUT : `is_active` ne borne QUE la magnitude. Le
    # compteur, lui, passe par `EFFECT_TRIGGERS[1568]` -> `triggers/dispatch/core.py::
    # collect_effect_triggers`, qui ne filtre que `consumed` -- mirror du rail natif
    # `EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities`. Un `is_active` pose en amont
    # du dispatch gelerait le niveau a 0 POUR TOUJOURS (l'effet ne peut plus jamais s'allumer).
    "HeadwoppasKillchoppa_ExtraDmg",
    "InescapableAccuracy_extraCritChance",
    "InescapableAccuracy_extraCritDmg",
    "InescapableAccuracy_overrideHits",
    "IntoxicatingElixir",                    # #943, cf. le bloc ci-dessus
    "MartialSuperiority_Visual",
    "MawClawsOfThyrax_ExtraCritDmg",         # #943, cf. le bloc ci-dessus
    # #552-r1 -- `HasEffect(bonded, 27, null, 6) & AreEqual(BondedEntityFromEffect(EffectFromOwner(
    # bonded, 27)), Owner@sel+0x30)`. Evaluable parce que ses DEUX selecteurs lisent des champs
    # RENSEIGNES du contexte (`EffectSelector$$Select` -> `ctx+0x58`, `OwnerSelector$$Select` ->
    # `ctx+0x18`), contrairement a celui de `BloodChalice_ExtraPiercing` ci-dessus.
    "MindControl_Taunter",
    "ModifiedExoarmour_ExtraDmg",
    "NetherRealmCasket_CritDamageReduction",  # #943, cf. le bloc ci-dessus
    "Pinned",
    "PowerTrip_FullHealth",
    "PsychicStalk_VisualEffect",
    "ReinforcedHiveNode_ExtraArmor",
    "ReinforcedHiveNode_ExtraBlock",
    "RitesOfMorkai_ExtraDamage",              # #943, cf. le bloc ci-dessus
    "Skullsmasher_ExtraDamage",               # #962, cf. le bloc ci-dessus
    "StructuralAnalyser_Visual",
    # #547-r6 -- ARRIVEE SANS SA LIGNE, et le cliquet l'a vue : `SupaCyborkBodyCritDmgReduction
    # Effect.is_active` est entree par la PR qui porte `supa_cybork_body.py`, sans inscription ici,
    # d'ou `master` ROUGE. La condition est REELLE et LUE : `CreateActiveCondition` =
    # `HasAdjacentEnemies(Owner, Tiles(Owner))`, exprimee par le MEME compteur que
    # `GetCalculateLevel` -- donc condition et magnitude ne peuvent pas diverger. Meme famille
    # geometrique qu'`AmuletOfTheVoidwyrm`, et meme degradation : cle ABSENTE = non mesure, on NE
    # FERME PAS.
    "SupaCyborkBody_CritDmgReduction",
    "VisionsOfHeresy_ExtraPierceMelee",
    "VisionsOfHeresy_ExtraPierceRanged",
}


def _state_with(effect_name: str, active: bool, hp: int, hp_max: int = 1000):
    """`State` minimal : UNE unite portant UNE instance d'effet, dans l'etat `active` demande."""
    st = State()
    st.effects = EffectsState.seed({})
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id="eldarRanger", alive=True))
    e.add_component(OwnerComponent(team=1, player=1))
    ctx = UnitContext(entity_id=e.id, visual_id="eldarRanger", active_ability_level=50,
                      passive_ability_level=50, ability_variables_multiplier=100)
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=hp, hp_max=hp_max))
    e.add_component(PositionComponent(col=2, row=2))
    etype = EffectType.__members__.get(effect_name)
    inst = EffectFactory.create({"name": effect_name,
                                 "effectType": (int(etype) if etype is not None else None),
                                 "remaining": 0, "active": active})
    inst.target = e.id
    st.effects.add_effect(e.id, inst)
    return st, e.id, inst


def test_discriminant_is_the_is_active_override_not_the_case322_flag():
    """CLIQUET du DISCRIMINANT. `_active_condition_is_ported` doit repondre a « la classe
    surcharge-t-elle `is_active` ? », et surtout PAS a `active_condition_ported`. Les deux ensembles
    sont mesures ici : les confondre re-verrouille les classes a condition portee."""
    overrides = {n for n, k in EFFECT_CLASSES.items() if k.is_active is not BaseEffect.is_active}
    helper = {n for n, k in EFFECT_CLASSES.items() if _active_condition_is_ported(k(n))}
    flagged = {n for n, k in EFFECT_CLASSES.items()
               if getattr(k, "active_condition_ported", False)}
    assert helper == overrides, (
        f"le helper ne mirrore plus la surcharge de `is_active` : {helper ^ overrides}")
    # #229-r2 -- CLIQUET BIDIRECTIONNEL (cf. `CONDITIONS_PORTEES_ATTESTEES` en tete de fichier).
    # L'ancien `len(overrides) >= N` ne voyait qu'un seul des deux sens et etait VERT en retard
    # d'une classe. On nomme les DEUX mouvements separement : ils ne demandent pas le meme geste.
    apparues = overrides - CONDITIONS_PORTEES_ATTESTEES
    disparues = CONDITIONS_PORTEES_ATTESTEES - overrides
    assert not disparues, (
        f"une surcharge de `is_active` a DISPARU du registre : {sorted(disparues)} -- c'est une "
        "REGRESSION (l'instance ne pourra plus se rallumer/s'eteindre au refresh), pas une ligne "
        "d'attestation a retirer. Corriger la classe, ou dire ici pourquoi la condition n'est plus "
        "portee.")
    assert not apparues, (
        f"condition(s) PORTEE(S) non attestee(s) : {sorted(apparues)} -- inscris-les dans "
        "`CONDITIONS_PORTEES_ATTESTEES` DANS LE MEME COMMIT que le port (l'ensemble est l'etat "
        "mesure, et deux branches paralleles fusionnent par UNION).")
    assert flagged < overrides, (
        "`active_condition_ported` n'est PAS un sur-ensemble des conditions portees : "
        f"flagged={sorted(flagged)} overrides={len(overrides)}")
    assert len(flagged) < len(overrides), (
        f"les DEUX ensembles coincident ({len(flagged)}) -- le discriminant a ete reconfondu avec "
        "le drapeau case-322, ce qui VERROUILLE les classes a condition portee (cf. en-tete)")
    # les deux temoins de ce fichier doivent rester de part et d'autre de la frontiere
    assert PORTED in overrides and UNPORTED not in overrides


def test_ported_condition_relights_a_seeded_inactive_instance():
    """REGIME QUI N'ETAIT RETENU PAR RIEN (celui de Contagions) : une instance arrivee INACTIVE du
    seed (`includeInactive` publie `active: false`), dont la condition PORTEE devient vraie, doit se
    RALLUMER au refresh. Le verrou `active = e.active and cond` sans reecriture l'en empechait."""
    st, uid, inst = _state_with(PORTED, active=False, hp=1000, hp_max=1000)   # PV pleins -> vraie
    assert inst.active is False
    refresh_stat_modifier_effects(st, uid)
    assert inst.active is True, (
        "une instance seedee INACTIVE dont la condition PORTEE est vraie n'a pas ete rallumee -- "
        "c'est le verrou qui a fait rougir test_contagions_lifecycle_live")


def test_ported_condition_extinguishes_when_it_becomes_false():
    """Symetrique : la meme classe, condition PORTEE fausse -> le refresh ETEINT l'instance."""
    st, uid, inst = _state_with(PORTED, active=True, hp=400, hp_max=1000)     # PV entames -> fausse
    refresh_stat_modifier_effects(st, uid)
    assert inst.active is False, (
        "la condition portee est fausse et l'instance reste allumee -- le refresh n'ecrit plus rien")


def test_unported_condition_is_never_relit_by_the_refresh():
    """REGIME INVERSE (celui de la riposte 1111) : sans condition portee, `is_active()` rend le
    DEFAUT `True` -- une valeur inventee, pas une lecture. Le refresh doit CONSERVER le flag, sinon
    il ecrase le `DeactivateEffect` que la feuille vient de poser et la riposte repart le meme tour
    (mesure : riposte fantome de 2849 PV, `test_wireweave_net_counter_is_once_per_enemy_turn`)."""
    st, uid, inst = _state_with(UNPORTED, active=False, hp=1000, hp_max=1000)
    refresh_stat_modifier_effects(st, uid)
    assert inst.active is False, (
        "le refresh a RALLUME un effet sans condition portee -- il ecrit un DEFAUT par-dessus le "
        "flag pose par ActivateEffect/DeactivateEffect")


def test_unported_condition_active_instance_is_left_alone():
    """Et il ne l'ETEINT pas non plus : sans lecture, on ne touche a rien."""
    st, uid, inst = _state_with(UNPORTED, active=True, hp=400, hp_max=1000)
    refresh_stat_modifier_effects(st, uid)
    assert inst.active is True, "le refresh a ETEINT un effet sans condition portee"
