"""`1101 AttemptedPossession` (`thousSorcerer` << Thaumachus >>, Thousand Sons) -- #590.

`IdunBattleLogic.Entities.Abilities.Active.Loki.AttemptedPossessionAbility$$ExecuteBehaviour` --
MIRROR du DECOMPILE (build `rnca9r7q6c`), terme a terme, dans l'ordre. Slots de `DSLSelectors`
(`factory+0x90`) : `sel+0x30 = Owner`, `sel+0x38 = Effect`, `sel+0x40 = Actor`, `sel+0x48 = Caster`,
`sel+0x60 = Target`, `sel+0x68 = It` ; `factory+0x78 = DSLBehaviors`, `+0x80 = DSLFormulas`,
`+0x88 = DSLTriggers`, `+0x90 = DSLSelectors`. Constantes de `DSLFormulas` (LUES dans son `.ctor`,
qui alloue cinq `ConstantAmountFormula` dans l'ordre) : `+0x18 = 0`, `+0x20 = 1`, `+0x28 = 2`,
`+0x30 = 100`, `+0x38 = -1`.

    possedes = UnitsWithoutTrait(
                   DSLSelectors.If( HasTrait(Target@0x60, 0x19 = 25 Immune),
                                    Alive(Children(Target@0x60)),
                                    Target@0x60 + Alive(Children(Target@0x60)) ),
                   0xd = 13 Object, selectionType: 3 )

    mvt   = ConditionalAmount( HasTrait(Actor@0x40, 0x2 = 2 Summon),
                               StatAmount(Actor@0x40, statType: 1 = MOVEMENT, statPart: 0 = CURRENT,
                                          modificationEntity: null, selectionType: 0),
                               <DSLFormulas+0x18 = Constant(0)> )

    bond  = AddBondEffect( 0x4b9 = 1209 AttemptedPossession_Possessed,
                           abilityState = AActiveAbility.get_AbilityStateReference(this),
                           source = Caster@0x48, targets = possedes, bondedEntity = Caster@0x48,
                           turns = <DSLFormulas+0x20 = Constant(1)> )
    rmBond = RemoveEffect( possedes, Nullable(0x4b9), replaceableEffectType: 0 )

    ai    = PerformAIAbility( unit = possedes,
                              getAbilityType = <Func statique du <>c -- l'ATTAQUE NORMALE>,
                              allowOnlyMove = 0, overrideMovement = mvt,
                              utilityEntity = Owner@0x30,
                              customUtility = Func(this, GetAttackCustomUtility) )

    dmg   = PercentageOfAttackCappedAtMax( unit = It@0x68, statPart: 3 = INITIAL,
                                           maxAmount  = ConfigVar(0xd  = maxDmg, abilityState, config),
                                           percentage = ConfigVar(0x4a = dmgPct, abilityState, config),
                                           roundingRule: 0 )
    ovr   = AddStatOverrideEffect( targets = possedes, 0x4ba = 1210 AttemptedPossession_DmgOverride,
                                   statType: 0 = ATTACK, amount = dmg, turns = null, isHidden = 1 )
    rmOvr = RemoveEffect( possedes, Nullable(0x4ba), 0 )

    AActiveAbility.Execute( (((bond + ovr) + ai) + rmOvr) & rmBond )

CATEGORIE REELLE : **CONTROLE (owner-swap transitoire) + ATTAQUE COMMANDEE**. L'audit
`docs/rl/combat-ability-coverage.md` classe 1101 en **EFFECT/BUFF** -- cette colonne derive du
`damageProfile` de l'ARME du porteur, pas du behaviour, et elle est INSUFFISANTE ici : l'arbre ne
pose pas de buff, il RETOURNE des unites et les fait FRAPPER. **DIX mecaniques**, enumerees dans le
rapport de tranche ; sept sont portees, trois sont des residus nommes (`#590-r2`, `#590-r3`,
`#590-r5`).

⚠ **CONTRAIREMENT A `1164 MindControl`, L'OWNER-SWAP EST REEL -- ET C'EST LU.**
`IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect$$ApplyInternal` a pour corps
ENTIER `ChangeUnitOwner(target, state.Get(BondedEntityId(effet)))` (slot `IOperationProcessor 127`)
et son `$$RevertInternal` `ResetUnitOwner(target)` (slot 128). Le nom n'a servi a rien : c'est
l'appel de slot, resolu dans `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`, qui
tranche. Voir `entities/effects/loki/possession.py`.

⚠ **LE SWAP EST TRANSITOIRE, ET C'EST L'ARBRE QUI LE DIT.** Le `turns = Constant(1)` du
`AddBondEffect` n'est jamais atteint sur les cibles du cast : le meme `Execute` retire l'effet en
queue (`... & RemoveEffect(possedes, 0x4b9)`). La sequence complete d'un cast est donc
<< je te possede -> j'ecrase tes degats -> tu attaques pour moi -> je rends tes degats -> je te
rends a ton camp >>.

⚠ **`op_Addition` ET `op_BitwiseAnd` SONT LE MEME PATRON D'ALLOCATION** (`left@+0x50`,
`right@+0x58`), lu aux deux decompiles ; le port les mirrore tous deux par `Seq` (`op_add` /
`op_and` d'`entities/behaviours.py`), qui est deja la convention du depot. La position du
`op_BitwiseAnd` de tete n'est donc PAS un choix de precedence a interpreter : le retrait du bond est
la DERNIERE feuille executee, ce que la parenthese du decompile dit sans ambiguite.

⚠ **`If` EST CELUI DU DOMAINE SELECTEUR** (`DSLSelectors$$If` @ la surcharge
`(abilityTrigger, selectorTrue, selectorFalse)`, tranchee par ses XREFS ENTRANTES parmi les TROIS
homonymes a 4 arguments), donc `SelectIf` cote port -- pas le `If` behaviour ni le `If` formule.

⚠ **LA BRANCHE `Immune` NE PROTEGE QUE LA CIBLE, PAS SES SUMMONS.** `If(HasTrait(Target, Immune),
Alive(Children(Target)), Target + Alive(Children(Target)))` : une cible `Immune` est retiree de la
selection, ses enfants restent possedes. Et l'effet 1209 n'arme PAS `get_CanBeImmuneTo`
(`can_be_immune_to.tsv`) : le gate d'immunite generique d'`AddEffectOperation` ne le couvre pas
non plus -- c'est cette branche d'arbre, et elle seule, qui porte l'immunite.

⚠ **`UnitsWithoutTrait(..., Object)` FILTRE LES DECORS**, pas les summons : le trait `13` est
`Object` (LU dans le mirror `UnitTrait`), tandis que `2` est `Summon` et sert ailleurs (le budget
de deplacement). Confondre les deux inverserait exactement le comportement decrit par l'i2.

i2 (`GC.ability_description("AttemptedPossession")`, verbatim) :
  << Target an enemy within 2 hexes. The target and any Summons it has summoned become possessed
  and immediately perform a normal attack against the closest enemy unit, preferring unpossessed
  targets. Possessed units deal 100% of their own Damage to a maximum of 4001 Damage per hit.
  Possessed Summons will move before attacking. >>

L'appariement tooltip <-> noeuds est un a un : << target and any Summons >> = le `If`/`Children`,
<< become possessed >> = `AddBondEffect(1209)`, << immediately perform a normal attack >> =
`PerformAIAbility`, << closest enemy unit, preferring unpossessed >> = `GetPreferredAttackTarget`,
<< 100% of their own Damage to a maximum of 4001 >> = `PercentageOfAttackCappedAtMax(dmgPct,
maxDmg)`, << Possessed Summons will move before attacking >> = `overrideMovement`.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ....dsl.effects import ExecutionContext
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.behaviours import op_add, op_and
from ....entities.effect_type import EffectType
from ....entities.ability_variable_type import AbilityVariableType
from ....entities.formulas import ConditionalAmount, ConfigVar, Get, Min, PercentageOf, StatAmount
from ....entities.selectors.accessors import Actor, Owner, Subject, Target
from ....entities.selectors.geometry import SelectIf
from ....entities.selectors.tiles import Caster, ChildrenOf
from ....entities.selectors.units import Alive, Union, UnitsWithoutTrait
from ....entities.stats import StatPart, StatType
import engine.entities.traits.unit_trait as _unit_trait   # FORME B (#547-r2), et ABSOLUE pour la
# meme raison que ci-dessous : le MODULE, pas le paquet parent, pas le symbole. `_has_trait` lit
# `_unit_trait.entity_trait_names` a chaque appel, donc un `monkeypatch.setattr(
# "engine.entities.traits.unit_trait.<x>", ...)` mord encore.
from ....entities.traits.unit_trait import UnitTrait
from ....entities.triggers import HasTrait
from ..base import ActiveAbility
from ..behaviours.ai_control import PerformAIAbility
from ..behaviours.context import entities_from_state
from ..behaviours.effects import AddBondEffect, RemoveEffect
from ..behaviours.stats import AddStatOverrideEffect
import engine.runner.abilities.targeting as _targeting   # FORME B (#547-r2), et ABSOLUE
# `valid_normal_attack_targets` est SUBSTITUE par `test_590_attempted_possession_offline.py`
# (3 sites) via le chemin PLEIN. Hisser en forme A (`from ..targeting import
# valid_normal_attack_targets`) gelerait la liaison a l'import et DESARMERAIT ces trois patchs --
# mesure de `migrate_485r1_barils_reexport.py morsure` (couple classe HISSAGE_DESARMERAIT).
# ⚠ ABSOLUE, PAS `from .. import targeting` : cette derniere DECLARE une arete vers le PAQUET
# PARENT et referme un SCC (`engine.runner.abilities` / `.loki` / `.loki.attempted_possession`) --
# MESURE, `test_270r4r2_cycles_imports_offline::test_etage1_aucun_cycle_module_level`. La forme
# absolue nomme le MODULE, donc l'arete va au module et le cycle ne se ferme pas.
from ..targeting import (RANGE_FROM_CONFIG, RANGED_BOOL_FALSE, TargetingOptions)
from ..targeting_rule import TargetingRule as TR
from ....entities.effects.aura_selectors import hex_distance
from ...components import HealthComponent, UnitComponent
from ...components import PositionComponent
from ...components import StatsComponent, UnitComponent
from ...components import UnitComponent
from ...operations.change_unit_owner import (ChangeUnitOwnerOperation, ResetUnitOwnerOperation)

if TYPE_CHECKING:
    from ...state import State


#: La cle gameconfig de l'ability 1101 (les deux `ConfigVar` de l'override de degat s'y indexent).
ABILITY_ID = "AttemptedPossession"

#: `AddBondEffect(0x4b9, ...)` -- l'OWNER-SWAP, pose sur chaque unite possedee.
POSSESSED = int(EffectType.AttemptedPossession_Possessed)          # 0x4b9 = 1209
#: `AddStatOverrideEffect(..., 0x4ba, ...)` -- l'override de la stat ATTACK.
DMG_OVERRIDE = int(EffectType.AttemptedPossession_DmgOverride)     # 0x4ba = 1210

#: `AddBondEffect(..., turns = <DSLFormulas+0x20>)` -- la CONSTANTE `1` du `DSLFormulas$$.ctor`,
#: pas un `ConfigVar` et pas un `TurnsFromRounds` : le natif recopie le champ pre-alloue.
#: (En pratique jamais atteint sur les cibles du cast, cf. l'en-tete.)
POSSESSION_TURNS = 1


def attempted_possession_targets():
    """Le sous-arbre de SELECTION des possedes -- MIRROR 1:1, cf. l'en-tete.

        UnitsWithoutTrait(
            DSLSelectors.If( HasTrait(Target, Immune),
                             Alive(Children(Target)),
                             Target + Alive(Children(Target)) ),
            Object, selectionType: 3 )

    ⚠ `Children` est ici `DSLSelectors$$Children(parent)` -- le selecteur SCOPE sur un parent, porte
    par `entities/selectors/tiles.py::ChildrenOf` -- et **NON** `DSLFactory$$Children` (sans
    argument), qui est l'accumulateur des summons du CAST courant. La confusion rendrait un
    selecteur toujours vide sur cette ability, qui ne spawne rien.

    ⚠ Le `selectionType: 3` (`OnlyAliveAndTargetable`) du `UnitsWithoutTrait` n'est PAS consomme par
    la couche selecteur du port -- residu `#433-r3-r2`, PARTAGE par tous les call-sites portes.
    Consequence bornee ici : le `Alive(...)` de la branche interne couvre deja les enfants, et la
    cible elle-meme est vivante par construction (le cast la vise). L'ecart porterait sur une cible
    non ciblable pour une autre raison que la mort."""
    enfants = Alive(ChildrenOf(Target()))                     # `Alive(Children(Target@0x60))`
    base = SelectIf(HasTrait(Target(), int(UnitTrait.Immune)),  # `HasTrait(Target, 0x19)`
                    enfants,                                    # branche VRAIE
                    Union(Target(), enfants))                   # `Target + Alive(Children(Target))`
    return UnitsWithoutTrait(base, int(UnitTrait.Object))        # `UnitsWithoutTrait(..., 0xd, 3)`


def attempted_possession_movement():
    """`ConditionalAmount( HasTrait(Actor@0x40, Summon), StatAmount(Actor, MOVEMENT), Constant(0) )`
    -- le budget de deplacement passe a `PerformAIAbility` en `overrideMovement` (`+0x78`).

    i2 : << Possessed Summons will move before attacking >>. Un possede NON-summon a donc `0` =
    sa tuile COURANTE pour seul domaine d'action (`ABaseAiUnitTactic$$GenerateActionTiles(unit,
    true, 0)`), un summon a sa MOVEMENT courante.

    ⚠ Le sujet est `Actor@sel+0x40`, PAS `It@sel+0x68` ni `Target@sel+0x60` : c'est l'unite
    COURANTE de l'iteration du behaviour (le natif re-ecrit l'acteur dans l'`AbilityEntities` avant
    d'evaluer la formule). Le port evalue donc la formule PAR ACTEUR, dans
    `PerformAIAbility.execute`.

    ⚠ `statPart: 0 = CURRENT` (et non `INITIAL`) -- le decompile passe `(void *)0x0` en 3e argument
    de `DSLFormulas$$StatAmount(unit, statType, statPart, modificationEntity, selectionType)` : le
    budget suit donc les modificateurs de mouvement actifs sur le summon."""
    return ConditionalAmount(
        HasTrait(Actor(), int(UnitTrait.Summon)),                  # `HasTrait(Actor@0x40, 0x2)`
        StatAmount(Actor(), int(StatType.MOVEMENT),                # `StatAmount(Actor, 1, 0, ...)`
                   int(StatPart.CURRENT)),                         # 3e arg = `variant` = statPart
        Get(0))                                                    # `<DSLFormulas+0x18>` = 0


def attempted_possession_damage():
    """`PercentageOfAttackCappedAtMax( It@0x68, statPart: 3 = INITIAL, maxAmount = ConfigVar(maxDmg),
    percentage = ConfigVar(dmgPct), roundingRule: 0 )` -- l'amount de l'override de stat.

    MIRROR du corps natif de la primitive (`IdunBattleLogic.Entities.DSLFormulas$$
    PercentageOfAttackCappedAtMax`), lu terme a terme, car c'est lui qui fixe le statType :

        base = StatAmountFormula(unit, statType: 0, statPart, modificationEntity: null,
                                 selectionType: 0)          # <- le `0` est ECRIT PAR LA PRIMITIVE
        pct  = DSLFormulas.PercentageOf(base, percentage, roundingRule)
        return <Min>(maxAmount, pct)                        # ctor mislabele `QuoteInstruction`,
                                                            # structure lue : (maxAmount, pct)

    donc `min( maxDmg , dmgPct% x StatAmount(It, ATTACK, INITIAL) )`. i2 : << Possessed units deal
    100% of their own Damage to a maximum of 4001 Damage per hit >> -- `100` est `dmgPct[L65]` et
    `4001` `maxDmg[L65]`, jamais codes en dur ici.

    ⚠ **`statPart = INITIAL` est LOAD-BEARING, et il evite une boucle.** L'amount est celui d'un
    `AddStatOverrideEffect` sur la stat ATTACK ; le lire en `CURRENT` le ferait dependre de
    l'override qu'il alimente. Le natif passe `3` en 2e argument -- la stat de BASE de l'unite
    possedee, hors modificateurs.

    ⚠ Les deux `ConfigVar` sont des `AbilityVariableType` (le 2e parametre de
    `DSLFormulas$$ConfigVar(this, variableType, abilityState, config)` est DECLARE `variableType`
    dans `frida/methods.tsv`) : `0xd` y nomme `maxDmg` et `0x4a` `dmgPct`, et le gameconfig de
    `AttemptedPossession` porte ces deux cles sous `variables`. Les `AbilityConstantType` homonymes
    nomment autre chose -- les confondre lirait la mauvaise cle SANS lever.

    ⚠ **L'ORDRE DES ARGUMENTS DE LA PRIMITIVE EST `(maxAmount, percentage)`**, pas l'inverse : la
    signature native est `(unit, statPart, maxAmount, percentage, roundingRule)` et le call-site
    passe `ConfigVar(0xd)` en 3e position. Intervertir donnerait `min(100, 4001% x ATK)` -- une
    valeur PLAUSIBLE (100 degats plats) qu'aucun ordre de grandeur ne trahirait sur un seul point
    de mesure.

    Le sujet `It@sel+0x68` est le `Subject()` du port : `AddStatOverrideEffectBehaviour$$Execute`
    LIE l'unite courante au slot SUJET (`param_3[4] = current`) AVANT d'evaluer le noeud montant --
    chaque possede lit donc SA propre stat ATTACK, pas celle du caster.

    ⚠ Les cles sont derivees de l'enum (`AbilityVariableType.maxDmg.name`), jamais recopiees en
    litteral : le port de `ConfigVar` s'indexe par NOM de variable gameconfig, mais le natif y passe
    l'ORDINAL (`0xd` / `0x4a`). Passer par le membre nomme est ce qui rend le glissement visible au
    prochain build (cf. la regle << un ENTIER qui DESIGNE passe par un ENUM >>)."""
    base = StatAmount(Subject(), int(StatType.ATTACK),         # statType `0` ECRIT par la primitive
                      int(StatPart.INITIAL))                   # `statPart: 3` (3e arg = `variant`)
    pct = PercentageOf(ConfigVar(AbilityVariableType.dmgPct.name), base)   # (pct, base)
    return Min(ConfigVar(AbilityVariableType.maxDmg.name), pct)


def attempted_possession_tree(possedes, custom_utility=None):
    """Arbre COMPLET de `...AttemptedPossessionAbility$$ExecuteBehaviour` (cf. l'en-tete).

    `possedes` = l'instance PARTAGEE du selecteur (`attempted_possession_targets()`), passee par
    l'appelant : le natif la construit UNE fois et la donne aux CINQ consommateurs (le bond, son
    retrait, le `PerformAIAbility`, l'override de stat, son retrait). Le port rebatit l'arbre a
    chaque cast, donc la re-evaluation est per-cast comme le natif -- mais l'INSTANCE est bien
    unique, ce qui compte pour tout noeud memoisant qu'on y brancherait.

    ⚠ **L'ATTAQUE COMMANDEE N'ABOUTIT PAS ENCORE DANS LE FLUX DU CAST -- RESIDU `#590-r8`,
    LOCALISE PAR MESURE.** Confront live (probe_590, MC1_67) : le natif fait perdre **7006 PV** a
    la proie du camp de la CIBLE (et **rien** au notre -- l'owner-swap est donc CONFIRME par son
    observable) ; le port pose le bond, le swap, l'override et la contrainte de cible correctement
    (`bonds=[{1209 -> 81, bonded=77}]`, `allowed_targets=[83]`, ATTACK apres override = 2411) mais
    rend `result: null`. La decomposition par etage EXCLUT tout ce qui est au-dessus :
      * `GetPreferredAttackTarget` rend **83**, la cible que le natif frappe reellement ;
      * le moteur d'utilite DECIDE juste : `{"kind": "ability", "target": 83, "to": (3,4)}` ;
      * le `range_gate` compose PASSE (`[["83", "(3,4)", true]]`) ;
      * et `perform_ai_ability_unit_behaviour(state, 81, False, 0, allowed_targets={83})` appele
        DIRECTEMENT sous simulation du swap rend **`{"target": 83, "total": 8252}`**.
    L'ecart est donc STRICTEMENT entre ce corps appele depuis `PerformAIAbility.execute` pendant le
    cast et le meme corps appele hors cast -- un foyer PARTAGE par huit call-sites, qu'on ne
    FITTERA pas depuis cette tranche. `BLOCAGE: etage`.

    ⚠ **L'ORDRE DES CINQ FEUILLES EST OBSERVABLE ET NON COMMUTATIF** : le bond (donc le swap
    d'owner) precede l'override de degat, qui precede l'action IA, qui precede les deux retraits --
    et le retrait du BOND est le dernier. Poser l'override avant le bond changerait l'equipe vue
    par le calcul de degat ; retirer le bond avant l'override rendrait l'unite a son camp pendant
    qu'elle porte encore des degats ecrases.

    ⚠ `scale_from_source` reste FAUX sur l'`AddBondEffect` : le 3e argument natif est bien
    `AActiveAbility$$get_AbilityStateReference(this)`, mais `AttemptedPossession_PossessedEffect`
    ne lit AUCUN `ConfigVar` (ses seuls corps propres sont `.ctor`, `ApplyInternal`,
    `RevertInternal`, `CreateHandleTriggerAbilitiesInternal`) -- le drapeau serait inerte. Meme
    lecture que les deux `AddBondEffect` de `mind_control_tree`.

    ⚠ `duration_turns` (et non `duration_rounds`) : le parametre natif de la surcharge
    `AddBondEffect(effectType, abilityState, source, targets, bondedEntity, **turns**)` -- tranchee
    par ses XREFS ENTRANTES, l'autre surcharge a 6 arguments prenant `options`. Le passer en
    `rounds` doublerait la duree (`TurnsFromRounds`), un ecart qu'aucune mesure ne verrait ici
    puisque le `RemoveEffect` de queue retire l'effet avant tout tick."""
    bond = AddBondEffect(POSSESSED, EffectType.AttemptedPossession_Possessed.name,
                         Caster(), possedes,
                         duration_rounds=None, duration_turns=POSSESSION_TURNS,
                         bonded_ref=Caster())
    ovr = AddStatOverrideEffect(possedes, DMG_OVERRIDE, int(StatType.ATTACK),
                                attempted_possession_damage(),
                                name=EffectType.AttemptedPossession_DmgOverride.name,
                                duration_rounds=None, duration_turns=None,
                                is_modifiable=True)          # 7e arg natif = 1
    ai = PerformAIAbility(possedes, override_movement=attempted_possession_movement(),
                          allow_only_move=False, utility_entity=Owner(),
                          custom_utility=custom_utility)
    rm_ovr = RemoveEffect(DMG_OVERRIDE, possedes)
    rm_bond = RemoveEffect(POSSESSED, possedes)
    return op_and(op_add(op_add(op_add(bond, ovr), ai), rm_ovr), rm_bond)


def attempted_possession_preferred_target(state: "State", caster_id: int,
                                          possessed_id: int) -> Optional[int]:
    """`...AttemptedPossessionAbility$$GetPreferredAttackTarget(caster, possessedUnit)` -- MIRROR.

    Le natif construit un `<>c__DisplayClass5_0` (`+0x10 = possessedUnit`, `+0x18 = this`), en fait
    un `Func<...>` sur `b__0`, et le confie a un service (`this+0x40`) avec l'effectType `0x4b9` et
    l'id du caster. Le CORPS DE LA DECISION est `b__0`, LU terme a terme :

        isSummon = UnitExtensions.HasTrait(unit, 0x2 = Summon)
        canMove  = UnitExtensions.CanMove(unit)
        if (canMove && isSummon)
            res = query.<IBattleQuery 69 GetAllValidTargetsFromAllPossibleMovementTiles>(
                      unit, GetNormalAttackType(unit), 1)
        else
            res = query.<IBattleQuery 66 GetValidTargets>(
                      unit, EntityExtensions.GetUnitPosition(unit, state), GetNormalAttackType(unit))
        l1 = ListExtensions.FilterNewList(res.<+0x10>, <>c.b__5_1)     # !HasTrait(u, 0xd = Object)
        l2 = ListExtensions.FilterNewList(l1,          dc.b__2)        # !HasEffect(u, 0x4b9)
        chosen = (l2.Count > 0) ? l2 : l1                              # <- PREFERENCE, pas exclusion
        return query.<IBattleQuery 75 GetNearestUnit>(unit, chosen)

    -- l'i2 mot pour mot : << a normal attack against **the closest enemy unit**, **preferring**
    unpossessed targets >>. Le repli sur `l1` est ce qui fait de << unpossessed >> une PREFERENCE et
    non un filtre dur : si tous les candidats sont deja possedes, on frappe quand meme.

    Les deux lambdas de filtre sont LISIBLES (contrairement au `getAbilityType` de l'arbre) :
      * `AttemptedPossessionAbility.<>c$$<GetPreferredAttackTarget>b__5_1` = `HasTrait(u, 0xd) ^ 1`
        -- exclut les `Object` (decors) ;
      * `AttemptedPossessionAbility.<>c__DisplayClass5_0$$<GetPreferredAttackTarget>b__2` =
        `!<slot 1>(target, 0x4b9, null)` -- exclut ceux qui portent DEJA `1209`.

    ⚠ **LA BRANCHE MOBILE (slot 69) EST PORTEE DEPUIS #590-r6** -- elle etait rabattue sur la
    branche statique (slot 66). `targeting.all_valid_targets_from_all_possible_movement_tiles` en
    est le mirror : `GetMovablePositionsFor` (slot `IMovementQuery 2`) + la position COURANTE, puis
    `GetValidTargetsInSteps` (slot `IAttackQuery 4`), qui n'est que l'UNION de la MEME cascade
    position par position. Les deux etages que le residu declarait manquants ne l'etaient pas tous
    les deux : **l'enumeration des tuiles de mouvement EXISTAIT** (`services/movement_query.
    get_movable_tiles_for` + `get_movable_positions_for`, foyer partage par trois collapses de
    `genestealer.py`) ; seul le second manquait -- un `GetValidTargets` prenant une LISTE de tuiles
    de cast -- et il tenait a un unique parametre, `casterTiles`, que le natif passe deja
    explicitement partout ou le port lisait la position REELLE.

    Le sous-regime qui divergeait, et qui ne diverge plus : un summon mobile SANS cible a portee
    sans bouger. Ce corps rendait `None`, donc `GetAttackCustomUtility` rendait `null`, donc AUCUNE
    contrainte -- le moteur d'utilite du port choisissait lui-meme sa cible apres approche. On
    perdait la PREFERENCE (<< closest >>, << unpossessed >>), pas l'attaque : l'ecart etait
    CONSERVATIF, ce qui est exactement pourquoi il a pu vivre.

    ⚠ **`CanMove` EST LE FOYER EXISTANT** `runner.operations.turnflow._can_move` (mirror des quatre
    etages d'`UnitExtensions$$CanMove`), TRI-ETAT : `None` = substrat non lisible. Le port ne prend
    la branche mobile que sur un `True` MESURE -- un `None` rabattu sur `True` prendrait une branche
    plus PERMISSIVE (plus de cibles) sur une non-mesure.

    ⚠ `GetNearestUnit` (slot 75) : le TIE-BREAK natif n'est pas lu (son corps n'est pas dans le
    perimetre de cette tranche). Le port trie par `(distance, id)` -- meme convention que
    `loki/summon.py::_nearest_enemy`, deterministe. Un ex aequo de distance est le seul regime ou
    les deux peuvent diverger.

    ⚠ **LE FUNC EST EVALUE SOUS SIMULATION DE L'EFFET `0x4b9`, ET C'EST LA CLE DE TOUT.** Le natif
    ne rend pas `b__0` directement : il le confie au service `this+0x40` AVEC l'effectType `0x4b9`
    et l'id du caster. Ce service SIMULE la pose de l'effet (le residu `#287-r5` le nomme deja :
    << SIMULATION d'effet (GetChildren + SimulateEffects) >>) puis appelle le Func. Autrement dit,
    `GetValidTargets` est evalue **APRES** l'owner-swap : les << ennemis >> de l'unite interrogee
    sont ceux de son NOUVEAU proprietaire -- ses propres anciens allies.

    MESURE qui l'etablit (probe_590, MC1_67, geometrie forcee) : sans la simulation, le port
    divergeait du natif dans les DEUX SENS a la fois, ce qu'aucun biais simple n'explique --
      * cible legale (81, un camarade adjacent, nous a distance 2) : port `GetValidTargets = []`
        (= NATIF), donc `preferred = None`, donc REFUS -- alors que le natif ACCEPTE et lui fait
        retirer 7006 PV a son camarade ;
      * temoin isole (85, personne d'adjacent, le caster a portee de SON arme) : port
        `GetValidTargets = [77]` contre NATIF `[]`, donc ACCEPTATION -- alors que le natif REFUSE.
    Les deux s'expliquent par la MEME cause : l'un et l'autre etaient evalues du mauvais cote du
    swap. Le port applique donc le swap AVANT d'interroger, et le defait apres -- litteralement
    `SimulateEffects(0x4b9)`, avec les deux Operations deja portees.

    ⚠ Le swap de simulation est IDEMPOTENT par construction : quand ce corps est appele PENDANT le
    cast (via le `customUtility` du `PerformAIAbility`), l'unite est DEJA possedee -- le gate
    `IsOwnerOverridden` de `ChangeUnitOwnerOperation` refuse alors le 2e swap et rend `False`, donc
    on ne defait rien. C'est exactement ce qu'il faut : la vraie possession ne doit pas etre
    annulee par une simulation imbriquee.

    Rend l'id de la cible preferee, ou `None` (aucun candidat)."""
    ent = state.get_entity(int(possessed_id))
    if ent is None:
        return None
    # `SimulateEffects(0x4b9)` -- l'owner-swap, applique le temps de la question.
    simule = ChangeUnitOwnerOperation.execute(state, int(possessed_id), int(caster_id))
    try:
        # DIFFERE **PORTEUR**, et la classe est MESUREE (pas supposee) : `import
        # engine.runner.operations.turnflow` dans un process FRAIS fait atterrir CE module-ci dans
        # `sys.modules` (`turnflow` -> `abilities.handler` -> `abilities.loki` -> nous), donc le
        # hisser refermerait le cycle -- `ImportError: cannot import name 'MindControlAbility' from
        # partially initialized module`, joue. Les DEUX leviers d'avant lui ont ete regardes et
        # ecartes pour cause de PERIMETRE, pas d'impossibilite : (1) DEPLACER `_can_move` /
        # `_has_active_movement_blocker` vers `runner/components.py` -- ou leurs deux dependances non
        # triviales (`is_machine_of_war`, `unit_state_for_effects`) vivent DEJA -- supprimerait
        # l'arete pour de bon, et c'est la vraie reparation (residu `#590-r6-r2`) ; (2) alleger
        # `abilities/loki/__init__.py`, la cause racine, est un baril a part entiere.
        # FORME C assumee : l'instruction est re-executee a chaque appel, donc un
        # `monkeypatch.setattr("engine.runner.operations.turnflow._can_move", ...)` MORD.
        from ...operations import turnflow as _turnflow
        # `if (canMove && isSummon)` -- LES DEUX BRANCHES, dans l'ordre natif. Le predicat combine
        # `UnitExtensions$$CanMove(unit)` et `HasTrait(unit, 0x2 Summon)`, et il est evalue SOUS la
        # simulation de l'owner-swap comme tout le reste de `b__0`.
        mobile = (_turnflow._can_move(state, int(possessed_id)) is True
                  and _has_trait(state, int(possessed_id), int(UnitTrait.Summon)))
        if mobile:
            # `<IBattleQuery 69 GetAllValidTargetsFromAllPossibleMovementTiles>(unit,
            #  GetNormalAttackType(unit), 1)` -- depuis TOUTE tuile de deplacement (#590-r6).
            cands = [int(t) for t in
                     (_targeting.all_valid_targets_from_all_possible_movement_tiles(
                         state, int(possessed_id)) or [])]
        else:
            # `res.<+0x10>` -- les cibles legales de l'attaque normale de l'ACTEUR (pas du caster).
            cands = [int(t) for t in
                     (_targeting.valid_normal_attack_targets(state, int(possessed_id)) or [])]
        if not cands:
            return None
        # `b__5_1` : `HasTrait(u, 0xd = Object) ^ 1`
        l1 = [t for t in cands if not _has_trait(state, t, int(UnitTrait.Object))]
        # `b__2` : `!HasEffect(u, 0x4b9)`
        l2 = [t for t in l1 if not _has_effect(state, t, POSSESSED)]
        chosen = l2 if l2 else l1                # `(l2.Count > 0) ? l2 : l1` -- PREFERENCE
        return _nearest_of(state, int(possessed_id), chosen)
    finally:
        if simule:
            ResetUnitOwnerOperation.execute(state, int(possessed_id))


def attempted_possession_custom_utility(state: "State", caster_id: int):
    """`Func(this, GetAttackCustomUtility)` -- le `customUtility` (`behaviour+0x90`) que l'arbre
    passe a `PerformAIAbility`. MIRROR de
    `...AttemptedPossessionAbility$$GetAttackCustomUtility(input)` :

        target = GetPreferredAttackTarget(this, caster = input+8, possessedUnit = input+0)
        if (target == null)  return null;                     # <- AUCUNE contrainte
        return new UtilityDefinition( new OnlyCertainTargetUtility(target) )

    et `IdunBattle.AI.Utilities.OnlyCertainTargetUtility$$.ctor(target)` fait `this+0x60 =
    [target].ToList()` -- une liste d'UN element. Cote port, le contrat est
    `(state, actor_id) -> set[int] | None` : l'ensemble des cibles autorisees, `None` quand le natif
    rend `null`. Cf. l'ecart NOMME (score -> exclusion) dans `behaviours/ai_control.py`.

    ⚠ `input+0` = l'ACTEUR (l'unite possedee) et `input+8` = le CASTER : c'est l'ordre du
    `AbilityEntities` que le behaviour construit par acteur. Les intervertir ferait chercher la
    cible preferee DU CASTER pour chaque possede.

    ⚠ **`input+8` VIENT DU CANAL `utilityEntity`, PAS DE LA FERMETURE (#590-r9).** Le natif ne
    capture rien : `input` est le `ValueTuple(Item1 = acteur, Item2 = <utilityEntity resolu>)` que
    `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute` construit depuis le
    champ `+0x80` de la feuille (resolu UNE fois par le slot 1 d'`ITargetsSelector`). Ce corps
    declare donc un TROISIEME parametre -- c'est ce que `PerformAIAbility._accepte_utility_entity`
    teste pour alimenter le canal (#590-r4). Le `caster_id` capture au call-site n'est plus la
    SOURCE, seulement le **repli nomme** quand le canal rend `None` (aucun selecteur `+0x80`, ou
    selecteur qui ne resout sur aucune unite) : sans lui ce corps rendrait `None`, donc AUCUNE
    contrainte de cible -- une degradation PERMISSIVE, exactement ce qu'on ne veut pas.
    ⚠ **Aucun temoin ne peut distinguer les deux regimes sur `1101`** : son arbre cable
    `utilityEntity = Owner@sel+0x30`, qui resout au caster -- la reparation est VALUE-PRESERVANTE
    sur le seul call-site porte, et c'est une reparation de CANAL, pas de valeur. Elle deviendrait
    observable le jour ou un call-site passerait autre chose que l'owner en `+0x80`."""
    def _utility(st, actor_id, utility_entity_id=None):
        ref = caster_id if utility_entity_id is None else utility_entity_id
        tgt = attempted_possession_preferred_target(st, int(ref), int(actor_id))
        return None if tgt is None else {int(tgt)}
    return _utility


def _has_trait(state: "State", unit_id: int, trait: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasTrait(unit, trait)`.

    Le substrat de traits du port est `entity_trait_names` (le FOYER : kit gameconfig + traits
    ACCORDES en bataille + pseudo-trait d'alliance) -- pas `sc.ctx.traits` brut, qui rate les
    traits accordes."""
    ent = state.get_entity(int(unit_id))
    if ent is None:
        return False
    sc = ent.get_component(StatsComponent)
    uc = ent.get_component(UnitComponent)
    traits = _unit_trait.entity_trait_names(
        sc.ctx if sc is not None else None,
        getattr(uc, "visual_id", None) if uc is not None else None)
    return _unit_trait.has_trait(traits, int(trait))


def _has_effect(state: "State", unit_id: int, effect_type: int) -> bool:
    """`<slot 1>(target, effectType, null)` du `b__2` -- l'unite porte-t-elle cet effet, non consomme ?"""
    if state.effects is None:
        return False
    return bool(state.effects.has_effect(int(unit_id), effect_type=int(effect_type)))


def _nearest_of(state: "State", unit_id: int, candidates) -> Optional[int]:
    """`IBattleQuery 75 GetNearestUnit(unit, candidates)` -- la plus proche par distance hex.
    Tie-break `id` (NON lu au natif, cf. `attempted_possession_preferred_target`)."""
    ent = state.get_entity(int(unit_id))
    pc = ent.get_component(PositionComponent) if ent is not None else None
    if pc is None or not candidates:
        return None
    best, best_key = None, None
    for cid in candidates:
        ce = state.get_entity(int(cid))
        cpc = ce.get_component(PositionComponent) if ce is not None else None
        if cpc is None:
            continue
        d = hex_distance((pc.col, pc.row), (cpc.col, cpc.row))
        if d is None:
            continue
        key = (int(d), int(cid))
        if best_key is None or key < best_key:
            best, best_key = int(cid), key
    return best


class AttemptedPossessionAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.AttemptedPossessionAbility$$ExecuteBehaviour`
    (id 1101, `thousSorcerer` << Thaumachus >>, HERO Thousand Sons -- au pool `rl_duel build
    --list-pool` du rank courant). Arbre DSL `attempted_possession_tree()`, cf. l'en-tete de module.

    ROUGE MESURE AVANT CE PORT : 1101 etait ABSENTE d'`ABILITY_CLASSES` -> le cast etait ACCEPTE
    par la DECISION et IGNORE par l'EXECUTION : 0 possession, 0 attaque commandee, 0 override de
    degat, AUCUNE erreur. C'est ce no-op silencieux que ce port ferme.

    Termine le tour (1101 n'est dans aucun des deux frozensets de `base.py` -> flags par defaut).

    Retour : {ability, caster, target, possessed, attacks, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.AttemptedPossession)      # 1101
    ABILITY_ID = ABILITY_ID

    # GATE DE CIBLE (#115) + PORTEE (#241). FORME **PRESET + FLAGS** :
    #     `...AttemptedPossessionAbility$$.ctor` recopie les 0x40 octets du champ statique
    #     `<TargetingOptions statics>+0x180` dans un temporaire (preset), puis
    #         TargetingOptions..ctor(&opts, &preset, 0x200000002)
    #         AActiveAbility..ctor(this, &opts, 0)
    #     -- le litteral `0x200000002` n'est PAS le masque : le masque effectif est le OU du preset
    #     (`<preset>+0x28` = `0x4002`) avec les flags, soit **`0x200004002`**. Le `0x2` du litteral
    #     etait DEJA dans le preset ; c'est le OU qui le dit, pas l'oeil.
    # Decomposition EXHAUSTIVE de `0x200004002` (aucun bit residuel) :
    #     0x2          (bit  1) TargetMatchesDynamicRule -> consulte `get_dynamic_invalid_target_reason`,
    #                           SURCHARGE ci-dessous (le natif a un vrai corps, cf. `GetDynamic...`).
    #     0x4000       (bit 14) TargetIsEnemy            -> refus sur soi-meme / un allie.
    #     0x200000000  (bit 33) TargetIsNotAnObject      -> refus sur un decor.
    # `isSelfCasting = 0`, `forceMeleeTarget = 1 = RangedBool.False` (l'enum natif est INVERSE :
    # True = 0, False = 1). PORTEE : `RANGE_FROM_CONFIG` -> `AActiveAbility$$SetConfigValues
    # InTargetingOptions` pose `OverrideRange = GetNumberConstant(0x16 = range)` =
    # `AttemptedPossession.constants.range` = **2** (== l'i2 << within 2 hexes >>).
    # ⚠ Valeur MIGREE depuis la table de repli `TARGETING_OPTIONS_UNPORTED` d'`abilities/
    # targeting.py` (contrat de DISJONCTION : une ability au registre porte son masque sur SA
    # classe). Le ctor a ete RELU au decompile avant migration et le masque est bit-identique a
    # celui qui vivait la-bas.
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy | TR.TargetIsNotAnObject),
        self_cast=False, range=RANGE_FROM_CONFIG,
        force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...AttemptedPossessionAbility$$GetDynamicInvalidTargetReason` -- MIRROR du decompile,
        terme a terme :

            unit = UnitExtensions.GetUnit(target, this.state);
            if (unit == null) return 2;                             // 2 = TargetMatchesDynamicRule

            vivants = UnitExtensions.GetChildren(unit, state, <Func b__3_0>);   // b__3_0 = IsAlive
            if (vivants.Count == 0 && UnitExtensions.HasTrait(target, 0x19 = Immune)) return 2;

            tous = UnitExtensions.GetChildren(unit, state, null);   // SANS filtre
            if (tous.Count < 1 && GetPreferredAttackTarget(this, caster, unit) == null) return 2;
            return 0;

        Les DEUX refus disent la meme chose sous deux angles : **le cast doit produire quelque
        chose**.
          * Une cible `Immune` sans enfant VIVANT ne serait possedee ni elle (la branche `If` de
            l'arbre l'exclut) ni personne -> refus.
          * Une cible sans AUCUN enfant et qui, elle-meme, n'aurait aucune cible d'attaque preferee
            -> le `PerformAIAbility` ne ferait rien -> refus.

        ⚠ **LE PREDICAT `b__3_0` EST LISIBLE**, contrairement a celui de `MindControl` :
        `...AttemptedPossessionAbility$$<GetDynamicInvalidTargetReason>b__3_0(entity)` =
        `IdunBattle.Entities.UnitExtensions$$IsAlive(entity, this.state)` -- une ligne, LUE.

        ⚠ Le SECOND `GetChildren` passe `null` en filtre : il compte les enfants MORTS aussi. Ce
        n'est pas une redite du premier -- une cible dont tous les summons sont morts passe ce
        gate-la (`tous.Count >= 1`) alors qu'elle echoue potentiellement au premier. Recopier le
        premier appel a la place du second retrecirait le domaine legal du cast.

        Cible non resolue -> `2` (le natif le dit explicitement). Substrat absent (pas de board,
        pas d'`EffectsState`) -> `0` : on ne fabrique pas un refus sur un substrat non mesure --
        meme convention que `mind_control.py`."""
        if target_id is None:
            return 0
        ent = state.get_entity(int(target_id))
        if ent is None:
            return int(TR.TargetMatchesDynamicRule)          # `unit == null` -> 2
        enfants = self._children_of(state, int(target_id))
        vivants = [c for c in enfants if self._is_alive(state, c)]
        if not vivants and _has_trait(state, int(target_id), int(UnitTrait.Immune)):
            return int(TR.TargetMatchesDynamicRule)
        if state.board is None:
            return 0                                         # substrat non mesure -> pas de refus
        if len(enfants) < 1 and attempted_possession_preferred_target(
                state, int(caster_id), int(target_id)) is None:
            return int(TR.TargetMatchesDynamicRule)
        return 0

    @staticmethod
    def _children_of(state: "State", unit_id: int) -> list:
        """`IdunBattle.Entities.UnitExtensions$$GetChildren(unit, state, filtre)` avec `filtre =
        null` -- TOUS les enfants, morts compris. Meme substrat que le selecteur `ChildrenOf`
        (`UnitComponent.parent_id`)."""
        out = []
        for eid, ent in state.entities.items():
            uc = ent.get_component(UnitComponent)
            if uc is not None and getattr(uc, "parent_id", None) == int(unit_id):
                out.append(int(eid))
        return out

    @staticmethod
    def _is_alive(state: "State", unit_id: int) -> bool:
        """`IdunBattle.Entities.UnitExtensions$$IsAlive` (= le lambda `b__3_0`) : vivant ET PV > 0."""
        ent = state.get_entity(int(unit_id))
        if ent is None:
            return False
        uc = ent.get_component(UnitComponent)
        hc = ent.get_component(HealthComponent)
        return bool(uc is not None and uc.alive and (hc is None or hc.hp > 0))

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # UNE instance de selecteur, partagee par les CINQ consommateurs natifs (cf. l'en-tete).
        possedes = attempted_possession_targets()
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        arbre = attempted_possession_tree(
            possedes, custom_utility=attempted_possession_custom_utility(state, int(caster_id)))
        arbre.execute(entities, ectx)
        posee = [{"effect_type": p.get("effect_type"), "target": p.get("target"),
                  "bonded": p.get("bonded")}
                 for n, p in ectx.emitted if n == "AddBondEffect"]
        ai = [p for n, p in ectx.emitted if n == "PerformAIAbility"]
        return {"ability": ABILITY_ID, "caster": caster_id, "target": target_id,
                "possessed": [d.get("target") for d in posee],
                "bonds": posee, "ai": ai, "dsl": True}
