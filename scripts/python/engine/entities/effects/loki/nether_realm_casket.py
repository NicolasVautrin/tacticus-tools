"""`NetherRealmCasket` (`TriggeredAbilityType` 0x5b6 = **1462**) -- la relique necron, et ses DEUX
effets. #908.

## L'ABILITY -- une seule, DEUX `AddEffect`, et c'est ce qui la distingue de ses soeurs

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.NetherRealmCasketAbility$$CreateBehaviour`
(mirror ; la surcharge d'`AddEffect` est tranchee par la CIBLE de son `call`, `0x180e9e8b0` =
`AddEffect(this, effectType, abilityState, source, targets, options)`, pas par le pseudo-C) :

    AddEffect( 0x5af = 1455 NetherRealmCasket_CritDamageReduction,
               abilityState = BaseTriggeredAbility.get_AbilityStateReference(this),
               source  = Owner@<DSLSelectors+0x30>,
               targets = Owner@<DSLSelectors+0x30>,
               options = <32 octets ZEROES>          -> PERMANENT )
    op_BitwiseAnd
    AddEffect( 0x5b0 = 1456 NetherRealmCasket_LivingMetalBonus,  <memes arguments> )

Les autres reliques a owner-effect derivent d'`IdunBattle.Entities.Abilities.
AOwnerEffectTriggeredAbility`, dont le `CreateBehaviour` de BASE pose **UN** effet
(`GetEffectType()`) enveloppe dans un `If(<trigger>, ...)`. Celle-ci en pose DEUX, donc elle ne
peut pas emprunter cette base : `classes.tsv` la donne fille directe de
`IdunBattle.Entities.Abilities.BaseTriggeredAbility` et elle ecrit son propre `CreateBehaviour`.

⚠ **SON `CreateTrigger` N'EST PAS LISIBLE, et c'est dit plutot que devine.** La classe ne porte que
DEUX methodes dans le binaire (`CreateBehaviour`, `GetLocalizationData` -- verifie sur
`frida/methods.tsv` ET sur le voisinage d'adresses de `ghidra/functions.tsv`, ou les fonctions
encadrantes appartiennent a `NeedsMoreDakka_AttackAbility` et `NetworkedTargetingAbility`).
`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetTrigger` appelle le slot virtuel `+0x2d8`,
et aucun `BaseTriggeredAbility$$CreateTrigger` n'existe dans les tables -- ce qui **ne prouve
rien** (dedup IL2CPP des corps identiques, cf. CLAUDE.md « L'ABSENCE d'une methode dans les tables
ne prouve RIEN »). **150 des 452** filles directes de `BaseTriggeredAbility` sont dans ce cas.
Aucun des **20** appelants de `IdunBattleLogic.Entities.DSLTriggers$$OnOwnerSpecificAbilityInit`
n'est cette classe. Ce qui est ETABLI : les deux effets sont poses sur l'**Owner**, avec des
options **ZEROEES** (donc sans duree), et ce qui les eteint est leur `CreateActiveCondition`, pas
un timer. La POSE elle-meme n'est PAS portee ici -- meme regime que
`AmuletOfTheVoidwyrm_CritDamageReduction` (residu `#589-r1-r1-r2-r1-r1`) : les effets entrent
dans l'etat du port par la CAPTURE live.

## LA CONFIG -- une seule, sans le piege 1455/1462

Le `.ctor` de `NetherRealmCasket_LivingMetalBonusEffect`, relu OCTET A OCTET, porte
`ba b6 05 00 00` = `mov edx, 0x5b6` = **1462** avant `IdunBattle.Core.AbilityOrEffect$$op_Implicit`
puis `41 b0 01` (`hasAutomaticActivation = 1`) et `IdunBattle.Entities.Effects.BaseEffect$$.ctor`.
Le meme `0x5b6` est le `source` des DEUX descripteurs `EffectBonus`. La config lue est donc la
TRIGGERED `NetherRealmCasket` 1462 -- et le gameconfig n'a qu'UNE entree de ce nom, portant les
DEUX variables (`critDmgReduction` 10 paliers `[390 .. 579]`, `hpToHeal` 10 paliers
`[980 .. 1456]`). Contrairement a 1460/1464 (`AmuletOfTheVoidwyrm` / `TalismanOfRage`), il n'y a
ici aucune ambiguite d'enum a lever.

⚠ En revanche le PIEGE D'ORDINAL existe a cote : `EffectType.RelicBoltPistol_ExtraPierce = 1457`
**et** `TriggeredAbilityType.KardiocoreGalvanus = 1457`. D'ou l'ecriture systematique par MEMBRE
NOMME dans tout ce module.

## EFFET 1455 -- `NetherRealmCasket_CritDamageReduction`, axe REDUCTION du canal crit-DEGAT

`IdunBattle.Entities.Effects.Loki.NetherRealmCasket_CritDamageReductionEffect$$
CreateCritDamageBonus` (mirror ; le 2e facteur est un appel VIRTUEL au slot `+0x5f8`, que
l'assembleur montre en `mov r8,[rdx+0x5f8] ; call r8` -- c'est `$$AdjacentMechanicalUnits`) :

    EffectBonus.ForSubtraction( get_OwnerIsTarget,                    <- trigger NU, aucun `&`
                                Multiply( ConfigVar(0x97 = critDmgReduction,
                                                    GetAbilityState(effect), config@+0x60),
                                          AdjacentMechanicalUnits() ),
                                AbilityOrEffect(NetherRealmCasket 0x5b6) )

`AbilityVariableType 0x97 = 151 = critDmgReduction` (LU dans le mirror d'enum, jamais recopie du
decompile). MEME forme que `AmuletOfTheVoidwyrm_CritDamageReductionEffect$$CreateCritDamageBonus`
et `SupaCyborkBody_CritDmgReductionEffect$$CreateCritDamageBonus` : seul le COMPTEUR change.

`...$$CreateActiveCondition` = `DSLTriggers.AmountIsGreaterThanZero( <le MEME compteur> )`, et
`...$$GetCalculateLevel` rend lui aussi ce compteur (niveau d'affichage, lu par
`NetherRealmCasket_CritDamageReductionEffectVisuals$$OnEffectLevelIncreased` -- aucun observable
de combat, non porte). `...$$GetAmount(abilityState)` = `Multiply(ConfigVar(0x97),
EffectLevel(...))` : la voie LOCALISATION, qui lit le niveau STOCKE la ou le canal de combat
recalcule le compteur -- les deux coincident tant que `RefreshEffectsOperation$$UpdateLevel` tient
le niveau egal a `GetCalculateLevel`.

CONSOMMATION : `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects` accumule
`addition - subtraction`, et `$$CalculateCriticalDamage` fait `Math.Max(0, GetStat(10) + somme)`.
Le port rend donc un entier **NEGATIF** -- mirror du terme soustractif, pas une convention locale.

## LE COMPTEUR -- un arbre DSL de TROIS etages, et il n'est PAS `UnitsWithTrait`

`IdunBattle.Entities.Effects.Loki.NetherRealmCasket_CritDamageReductionEffect$$
AdjacentMechanicalUnits(dsl)` (mirror, dans l'ordre du decompile) :

    Count( MechanicalUnits( NormalUnits( AdjacentFriends(Owner@<DSLSelectors+0x30>,
                                                         unique: 1, selectionType: 3),
                                         selectionType: 3 ),
                            selectionType: 3 ) )

⚠ **La surcharge d'`AdjacentFriends` est tranchee par la CIBLE de son `call`**, comme la doctrine
l'exige (`reference_targeting_options_ctor_forms` : « trancher par ses XREFS ENTRANTES, jamais par
le pseudo-C »). L'assembleur donne `0x180eac2a0`, soit la variante
`AdjacentFriends(this, unit, unique, selectionType)` -- **pas** la variante `(this, unit, unitTile,
unique)`, dont le 3e argument est une ancre geometrique. Le litteral `3` est donc bien un
`selectionType`, et il est PROPAGE aux deux etages internes de la variante A.

⚠ **`MechanicalUnits` n'est PAS `HasTrait(Mechanical)`** : `IdunBattle.Entities.Selectors.
MechanicalUnitsSelector$$Select` delegue a `IdunBattle.Entities.UnitExtensions$$IsMechanical` =
`HasTrait(Mechanical 5) || HasTrait(LivingMetal 1000) || HasTrait(Vehicle 0x405)`. C'est
load-bearing ICI plus qu'ailleurs : le porteur canonique de la relique, `necroSpyder`, est un
NECRON, et tout le roster necron porte `LivingMetal` -- dont plusieurs unites SANS le trait
`Mechanical` (`necroWarden`, mesure #220). Un port par `UnitsWithTrait(Mechanical)` compterait
donc systematiquement TROP PEU sur le camp meme ou la relique s'equipe.

⚠ **`NormalUnits` est un etage REEL**, pas un habillage : `IdunBattle.Entities.Triggers.
IsNormalUnitTrigger$$ShouldTrigger` -> `UnitExtensions$$IsNormalUnit` = `!HasTrait(Object 0xd) &&
!HasTrait(Steppable 0x1b)`. Il ecarte les objets de plateau et les decoys pietinables -- qui
peuvent parfaitement etre `Mechanical` et amis adjacents.

## EFFET 1456 -- `NetherRealmCasket_LivingMetalBonus`, un `RepairBonus` GATE

`IdunBattle.Entities.Effects.Loki.NetherRealmCasket_LivingMetalBonusEffect$$
CreateEffectRepairBonus` (mirror ; les deux `AbilityOrEffect` relus OCTET A OCTET) :

    EffectBonus.ForAddition( get_OwnerIsTarget
                             op_BitwiseAnd
                             TriggeringAbilityIs( AbilityOrEffect(LivingMetalRepair 0x3f2) ),
                             ConfigVar(0x20 = hpToHeal, GetAbilityState(effect), config@+0x60),
                             AbilityOrEffect(NetherRealmCasket 0x5b6) )

`AbilityVariableType 0x20 = 32 = hpToHeal` ; `TriggeredAbilityType 0x3f2 = 1010 =
LivingMetalRepair`. C'est le TROISIEME et dernier implementeur du canal
`IdunBattle.Entities.Effects.BaseEffect$$RepairBonus` (avec `NanoscarabRepairProtocolsEffect` 1545
et `VoltagheistField_RepairReductionEffect` 1382), et le SEUL dont le gate porte un
`TriggeringAbilityIs`.

CE QUE CE GATE IMPLIQUE, et c'est ce que la tranche a ouvert : la face DECISION ne peut JAMAIS le
satisfaire (`engine/predict.py` predit `Repair` 28 / `Repair_GalvanicField` 1119, jamais
`LivingMetalRepair`), donc le seul chemin ou ce bonus vaut autre chose que 0 est la face COMBAT --
le trigger `LivingMetal` du porteur, rebranche sur `RepairUnitOperation` par #310. Le canal qui
transporte la cause (`RepairBehaviour+0x68` -> `RepairUnitOperation$$Execute` ->
`PredictRepair(..., abilityOrEffect)` -> `CalculateRepairModifierForPrediction(..., source)`)
etait NOMME comme manquant par `runner/operations/repair.py` ; il est desormais porte.

ASCII only (console cp1252).
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var
from ....dsl.base import Const
from ...selectors.accessors import Owner
from ...selectors.units import AdjacentFriends, MechanicalUnits, NormalUnits
from .. import ctx_keys as _ctx_keys      # #1042-r5 : foyer UNIQUE des chaines de cle de ctx

#: `TriggeredAbilityType` 0x5b6 = 1462 -- la CONFIG des DEUX effets (relue au `.ctor` : `mov edx,
#: 0x5b6`), et le `source` de leurs deux descripteurs `EffectBonus`.
ABILITY_ID = "NetherRealmCasket"
#: `AbilityVariableType` 0x97 = 151
VAR_CRIT_DMG_REDUCTION = "critDmgReduction"
#: `AbilityVariableType` 0x20 = 32
VAR_HP_TO_HEAL = "hpToHeal"
#: le litteral `selectionType` que les TROIS etages du compteur recoivent au decompile.
SELECTION_TYPE = 3

#: cle du compteur, posee par le foyer `runner/components.py::adjacent_friendly_mechanical_units_count`
CARRIER_COUNT_KEY = "adjacent_friendly_mechanical_units"
#: callable `(owner_id) -> int | None` pose dans le contexte du canal CRIT par `_crit_board`
CTX_COUNT_OF = "adjacent_friendly_mechanical_units_of"
#: callable `(owner_id, ability_name) -> (level, multiplier)` -- mirror de `GetAbilityState(effect)`
CTX_ABILITY_STATE_OF = _ctx_keys.CTX_TERTIARY_ABILITY_STATE_OF


def adjacent_mechanical_units_selector():
    """L'ARBRE DSL de `IdunBattle.Entities.Effects.Loki.NetherRealmCasket_CritDamageReductionEffect$$
    AdjacentMechanicalUnits`, noeud par noeud (doctrine #149 : l'artefact natif est un SELECTEUR,
    donc le port est un arbre, pas une boucle recablee).

        Count( MechanicalUnits( NormalUnits( AdjacentFriends(Owner, unique: 1, selectionType: 3),
                                             3 ),
                                3 ) )

    Le `selectionType` litteral `3` est PASSE explicitement aux trois etages -- c'est ce que
    l'assembleur montre (`mov r9d, 3` puis `mov r8d, 3` deux fois), et la variante A
    d'`AdjacentFriends` le propage a son `Units` interne.

    `reference=Owner()` est EXPLICITE : la surcharge native construit `Friends(reference = unit,
    ...)` ou `unit` est le centre. Le defaut du port (`ctx.caster`) serait exact tant que le
    contexte est bati sur le porteur, mais l'ecrire evite de dependre du montage -- meme arbitrage
    qu'`AmuletOfTheVoidwyrm`.

    Import PARESSEUX de `Count` : `entities/formulas` est assemble APRES le package
    `entities/effects` (meme convention que les autres modules d'effet de ce paquet)."""
    from ...formulas import Count

    # `DSLSelectors$$AdjacentFriends(this, unit = Owner@+0x30, unique = 1, selectionType = 3)`
    # -- surcharge tranchee par la CIBLE du `call` (`0x180eac2a0`), cf. l'en-tete de module.
    adjacent = AdjacentFriends(Owner(), Const(1), Owner(), SELECTION_TYPE)
    return Count(MechanicalUnits(NormalUnits(adjacent, SELECTION_TYPE), SELECTION_TYPE))


class NetherRealmCasketCritDamageReductionEffect(BaseEffect):
    """`NetherRealmCasket_CritDamageReduction` (`EffectType` 0x5af = 1455) -- owner-effect PERMANENT
    de la relique `NetherRealmCasket` : quand son porteur est la CIBLE d'un coup CRITIQUE, le degat
    de crit de l'attaquant est reduit de `critDmgReduction[niveau de relique] x <nombre d'unites
    MECANIQUES amies NORMALES adjacentes au porteur>`.

    Troisieme implementeur porte de l'axe REDUCTION du canal crit-DEGAT, apres
    `AmuletOfTheVoidwyrm_CritDamageReduction` (1460) et `SupaCyborkBody_CritDmgReduction` (1468) --
    meme `ForSubtraction`, meme `get_OwnerIsTarget` NU, meme `ConfigVar(0x97)`. La seule difference
    de forme est le COMPTEUR (cf. `adjacent_mechanical_units_selector`)."""

    # La `CreateActiveCondition` est GEOMETRIQUE : elle rebascule des qu'une unite bouge, et le
    # natif la reevalue (`RefreshEffectsOperation$$RefreshEffect` -> `Activate`/`DeactivateEffect`).
    # La condition PORTEE fait donc foi sur le flag `IsActive` capte -- meme arbitrage
    # qu'`AmuletOfTheVoidwyrmCritDamageReductionEffect` et `StructuralAnalyser_Visual`.
    active_condition_ported = True

    @staticmethod
    def _adjacent_count(ctx: "Mapping | None") -> "int | None":
        """`AdjacentMechanicalUnits()` EVALUE pour le PORTEUR de CETTE instance.

        Le canal pose `owner_id` par porteur (mirror de l'ecriture `AbilityEntities+0x18` que fait
        `GetCritDamageBonusFromEffects` a chaque iteration), et `_crit_board` pose le callable
        `adjacent_friendly_mechanical_units_of` -- paresseux, donc rien n'est calcule tant qu'aucune
        instance ne le demande.

        TRI-ETAT : callable ou `owner_id` ABSENT => `None` = « non mesure », JAMAIS 0. Un 0 invente
        annulerait le produit et ferait passer une reduction reelle pour une absence de
        reduction."""
        c = ctx or {}
        fn = c.get(CTX_COUNT_OF)
        oid = c.get("owner_id")
        if fn is None or oid is None:
            return None
        n = fn(oid)
        return None if n is None else int(n)

    def _ability_state(self, ctx: "Mapping | None") -> tuple:
        """`GetAbilityState(effect)` -> `(level, multiplier)` de l'`AbilityState` bake a la pose.

        `NetherRealmCasketAbility$$CreateBehaviour` passe
        `BaseTriggeredAbility$$get_AbilityStateReference(this)` et pose l'effet SUR l'Owner : source
        == porteur, donc le couple se relit sur le porteur (`owner_id`). C'est l'etat TERTIAIRE
        quand la relique est EQUIPEE (`BC.Units[].TertiaryAbilityLevel`), l'etat PASSIF sinon --
        exactement l'arbitrage du foyer UNIQUE `runner/operations/triggers/base.py::
        triggered_ability_state` (#357).

        Sans lui, `critDmgReduction` rendrait TOUJOURS `[10] = 579` : `ability_level` vaut 50 sur
        tout runner normalise et `ability_var` clampe au dernier palier.

        Callable absent (contexte sans `state` : probe, test offline) -> repli sur les niveaux que
        l'effet porte deja, comme toutes les autres classes d'effet."""
        c = ctx or {}
        fn, oid = c.get(CTX_ABILITY_STATE_OF), c.get("owner_id")
        if fn is not None and oid is not None:
            lvl, mult = fn(oid, ABILITY_ID)
            if lvl is not None:
                return int(lvl), int(mult if mult is not None else 100)
        lvl = self.ability_level if self.ability_level is not None else self.level
        return lvl, int(self.ability_variables_multiplier or 100)

    def _owner_is_target(self, att_ctx: "Mapping | None" = None) -> bool:
        """`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` = `AreEqual(Owner@+0x30,
        Target@+0x60)`. Identite NON PROUVEE (une des deux cles absente) => noeud FAUX, jamais
        permissif -- meme foyer de raisonnement qu'`AmuletOfTheVoidwyrmCritDamageReductionEffect`."""
        c = att_ctx or {}
        oid, tid = c.get("owner_id"), c.get("tgt_id")
        return oid is not None and tid is not None and oid == tid

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`CreateActiveCondition` = `AmountIsGreaterThanZero(AdjacentMechanicalUnits())`, ou le
        `minAmount` natif est `<DSLFormulas+0x18>` = `Direct(0)`.

        Cle ABSENTE = **non mesure** -> on NE FERME PAS (degradation fidele, meme regime
        qu'`AmuletOfTheVoidwyrmCritDamageReductionEffect.is_active`). Cote COMBAT la cle EST posee :
        `UnitEffectStateView` la calcule paresseusement des que le porteur a une equipe et une
        tuile."""
        n = (unit_state or {}).get(CARRIER_COUNT_KEY)
        return True if n is None else int(n) > 0

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `...NetherRealmCasket_CritDamageReductionEffect$$CreateCritDamageBonus` :

            EffectBonus.ForSubtraction( get_OwnerIsTarget,
                                        Multiply( ConfigVar(0x97 = critDmgReduction,
                                                            GetAbilityState(effect), config@+0x60),
                                                  AdjacentMechanicalUnits() ) )

        Retour ENTIER NEGATIF : `GetCritDamageBonusFromEffects` accumule `addition - subtraction`,
        et son consommateur est `Math.Max(0, GetStat(10) + somme)` dans `CalculateCriticalDamage`.

        Les etages sont SEPARES et chacun peut se taire independamment (aucun scalaire fitte) :
          1. `get_OwnerIsTarget`  -- le porteur est-il le defenseur ?
          2. le COMPTEUR          -- tri-etat, `None` = non mesure ;
          3. l'`AbilityState`     -- niveau/multiplicateur de la relique sur le porteur ;
          4. `ConfigVar`          -- `critDmgReduction[niveau]`, relu du gameconfig ;
          5. `Multiply`           -- le produit, puis le signe de `ForSubtraction`."""
        if not self._owner_is_target(att_ctx):                              # 1
            return None
        n = self._adjacent_count(att_ctx)                                   # 2
        if n is None:
            return None
        lvl, mult = self._ability_state(att_ctx)                            # 3
        v = ability_var(ABILITY_ID, VAR_CRIT_DMG_REDUCTION, lvl, multiplier_pct=mult)   # 4
        if v is None:
            return None
        amount = int(v) * int(n)                                            # 5  Multiply
        return -amount if amount else None                                  #    ForSubtraction


#: `EffectType` 0x5b0 = 1456 -- le nom runtime de l'effet `RepairBonus`. Il n'a **pas** de classe
#: d'effet, et c'est un CHOIX : la regle du canal `IdunBattle.Entities.Effects.BaseEffect$$
#: RepairBonus` (quels `EffectType` contribuent, `add` vs `pct`, et desormais le gate
#: `TriggeringAbilityIs`) vit dans le foyer UNIQUE
#: `engine.predict.calculate_repair_modifier_for_prediction`, partage par les DEUX faces -- c'est
#: l'arbitrage deja pris pour les DEUX autres implementeurs du canal (`NanoscarabRepairProtocols`
#: 1545, `VoltagheistField_RepairReduction` 1382), qui n'ont pas de classe non plus. En creer une
#: ici dupliquerait la regle : un fork, pas un port.
LIVING_METAL_BONUS_EFFECT_NAME = "NetherRealmCasket_LivingMetalBonus"
