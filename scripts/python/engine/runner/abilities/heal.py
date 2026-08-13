"""`18 Heal` -- le SOIN GENERIQUE accorde par le trait `Healer` (#931-r1).

Module DEDIE et NON factionnel, exactement pour la meme raison que `abilities/repair.py` :
`18 Heal` n'appartient a aucune faction. C'est une ability **DERIVEE D'UN TRAIT** --
`IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities` appelle
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetActiveAbility` sur le
trait `Healer` et pousse le resultat dans `ActiveAbilityComponent$$Add`. Ses porteurs traversent
cinq factions -- la ranger dans l'un des modules factionnels serait FAUX.

⚠ **CE MODULE N'EST PAS `repair.py`, ET C'EST UNE LECTURE, PAS UNE COMMODITE.** Les deux abilities
sont jumelles par leur FORMULE (`Multiply(StatAmount(Caster, ATTACK, Current),
Max(WeaponHighestHits(Caster), Get(1)))`, terme pour terme) et par leur origine (un trait), mais
elles sont deux CLASSES natives distinctes, de deux namespaces distincts
(`IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility` contre
`IdunBattleLogic.Entities.Abilities.Active.RepairAbility`), et leurs `TargetingOptions` **ne se
recopient pas** -- cf. le tableau ci-dessous : ni la meme portee, ni le meme masque, ni le meme
regime de refus.

------------------------------------------------------------------------------------------------
## L'ARBRE -- `...Active.Common.HealAbility$$CreateBehaviour`, MIRROR du decompile

Le natif INLINE `$$HealAmount` dans `$$CreateBehaviour` (les deux corps existent ; celui de
`CreateBehaviour` ne rappelle pas le premier) :

    healer   = <bundle@0x90>+0x48                                  # `Caster`
    selector = <bundle@0x90>+0x60                                  # `ActiveTarget` (la cible du cast)
    hits     = DSLFormulas.Max( WeaponHighestHits(<+0x48> Caster),
                                DSLFormulas.Get(1) )
    amount   = DSLFormulas.Multiply( StatAmount(<+0x48> Caster, 0 = ATTACK, 0 = Current,
                                                modificationEntity = null, selectionType = 0),
                                     hits )
    source   = AbilityOrEffect.op_Implicit(this)
    options  = HealBehaviourOptions.ForHeal(source)                # scope 0, removeEffects 1
    return DSLBehaviors.Heal(healer, selector, amount, options)

C'est l'arbre NU : aucun buff, aucun effet pose, aucun gate de faction. Le seul filtre est celui du
CIBLAGE (masque ci-dessous) et le gate `HealUnitOperation` de la feuille.

`ForHeal` relu (`IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForHeal`) : `+0x2c = 0`
(scope) et `+0x30 = 1` (removeEffects) -- les deux litteraux que la feuille `Heal` du port prend en
`scope=0, remove_effects=True`, et qui sont son DEFAUT (19 des 25 call-sites du build). Il est
DECLARE ici quand meme, pas herite du defaut.

------------------------------------------------------------------------------------------------
## LE MASQUE -- forme 3 « COPIE STATIQUE », et il DIFFERE de celui de `28 Repair`

`...Common.HealAbility$$.ctor` **n'appelle AUCUN ctor de `TargetingOptions`** : il recopie les 0x40
octets du preset `<TargetingOptions statics>+0x100` (`lVar1 = *(<TargetingOptions class>+0xb8)`,
puis huit qwords depuis `lVar1+0x100`), puis appelle
`ADeprecatedActiveAbility..ctor(this, &opts, 2)`.

Le preset est LU dans `IdunBattle.Core.Services.TargetingOptions$$.cctor`, aux offsets
`+0x100..+0x138` :

    +0x100  isSelfCasting    = 0
    +0x108  range            = <TargetingRange statics>+0x00 = RANGE_ADJACENT_IF_MELEE_CASTER
                               (`onlyAdjacent = 3 = IfNotRangedCaster`, rien d'autre)
    +0x120  forceMeleeTarget = 2 = RangedBool.IfRangedCaster
    +0x128  rules            = **0x8500**
    +0x130  getDynamicInvalidCasterReason = 0
    +0x138  getDynamicInvalidTargetReason = 0

Decomposition de `0x8500` (`IdunBattle.Core.Services.TargetingRule`, bit a bit, RESTE = 0) :

    0x0100  TargetIsHealable        -> la cible doit etre SOIGNABLE (slot 0x11 d'`IAttackQuery`)
    0x0400  TargetIsFriendly        -> une cible ENNEMIE est refusee
    0x8000  CasterIsPossibleTarget  -> le soigneur PEUT se cibler lui-meme

⚠ **`TargetMatchesDynamicRule` (0x0002) est ABSENT, et c'est le contraste exact avec `28 Repair`.**
`RepairAbility` porte `0x8002` : son masque ne dit RIEN du camp ni du domaine, et TOUT son refus
vit dans `$$GetDynamicInvalidTargetReason`. `HealAbility`, elle, n'a **aucun** override dynamique
(la classe ne porte que trois methodes nommees : `$$.ctor`, `$$HealAmount`, `$$CreateBehaviour`) --
et le bit qui ferait consulter une regle dynamique n'est pas arme. Les deux refus sont donc poses
STATIQUEMENT, par `TargetIsHealable` et `TargetIsFriendly`. Recopier le masque de `Repair` aurait
inverse le regime : plus aucun gate statique, et un gate dynamique inexistant.

| | `28 Repair` | `18 Heal` |
|---|---|---|
| classe | `...Active.RepairAbility` | `...Active.Common.HealAbility` |
| forme du ctor | 1, FLAGS DIRECTS | **3, COPIE STATIQUE** (`statics+0x100`) |
| `rules` | `0x8002` | **`0x8500`** |
| `range` | `RANGE_ADJACENT` (statics+0x30) | **`RANGE_ADJACENT_IF_MELEE_CASTER`** (statics+0x00) |
| refus | DYNAMIQUE (`GetDynamicInvalidTargetReason`) | **STATIQUE** (`TargetIsHealable`) |

------------------------------------------------------------------------------------------------
## LA SPECIALISATION : un SWAP DSL, pas un heritage

Deux passifs SUBSTITUENT une active a `18` sur leur porteur, par un couple
`RemoveActiveAbility(Owner, 18) & AddActiveAbility(Owner, <id>, abilityState)` :

  * `TwistedScience` (`genesBiophagus` << Hollan >>) -> `1167 Heal_TwistedScience` (#931) ;
  * `HealingBalms`   (`spaceWolfPriest` << Baldr >>) -> `1212 HealingBalms_Heal` (#966).

Les DEUX classes derivent d'`IdunBattle.Entities.Abilities.AActiveAbility`, **pas** de
`Common.HealAbility` (lu dans `classes.tsv`) : c'est pourquoi porter les specialisations ne portait
PAS la generique, contrairement au couple `28 Repair` / `1119 Repair_GalvanicField`, ou `1119`
HERITE au binaire (`Repair_GalvanicFieldAbility$$.ctor` = `return RepairAbility..ctor(this)`).

PORTEURS -- trait `Healer`, 18 unites, dont **6 en lineup** et **5 au pool rank 17** :
`adeptHospitaller`, `bloodSanguinary`, `deathRotbone`, `ultraApothecary` gardent `18` ;
`genesBiophagus` et `spaceWolfPriest` le PERDENT au swap (ce sont les contre-temoins).

ASCII only (console cp1252).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.effects import ExecutionContext
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.selectors.accessors import Target
from ...entities.stats import StatType
from ...predict import heal_amount_weapon
from ..components import StatsComponent
from .base import ActiveAbility
from .behaviours.context import entities_from_state
from .behaviours.stats import Heal
from .targeting import (RANGE_ADJACENT_IF_MELEE_CASTER, RANGED_BOOL_IF_RANGED_CASTER,
                        TargetingOptions)
from .targeting_rule import TargetingRule as TR

if TYPE_CHECKING:
    from ..state import State


# Preset `<TargetingOptions statics>+0x100`, LU dans `IdunBattle.Core.Services.TargetingOptions$$.cctor`
# (cf. l'en-tete de module). ⚠ Ce preset n'est PAS celui de `RepairAbility` et n'est PAS celui de
# l'attaque normale (`statics+0x00`, `rules = 0x4002`) : les trois se ressemblent au `range` pres et
# au masque pres, et c'est exactement le piege << meme masque, presets differents >>.
HEAL_TARGETING_OPTIONS = TargetingOptions(
    rules=(TR.TargetIsHealable | TR.TargetIsFriendly | TR.CasterIsPossibleTarget),   # 0x8500
    self_cast=False, range=RANGE_ADJACENT_IF_MELEE_CASTER,
    force_melee_target=RANGED_BOOL_IF_RANGED_CASTER)


def heal_amount(state: "State", caster_id: int) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility$$HealAmount` =
    `Multiply(StatAmount(Caster, ATTACK, Current), Max(WeaponHighestHits(Caster), Get(1)))`.

    COLLAPSE V assume (doctrine slice-23), MEME arbitrage que `repair.py::repair_amount` : les trois
    feuilles `DSLFormulas` se resolvent en deux lectures du `UnitContext` du caster, et le produit
    vit deja dans `engine.predict.heal_amount_weapon` -- LA seule lecture de cette formule dans le
    moteur, deja confrontee live cote DECISION (#45c) et partagee avec `1167` et `1212`. On
    l'appelle, on ne la duplique pas : un 4e site recalculerait la meme regle et divergerait.

    `StatAmount(..., part 0 = Current)` = la stat Attack RESOLUE (initial + modifiers + overrides).
    Sans contexte de stats -> `0` (aucune valeur inventee)."""
    e = state.get_entity(int(caster_id)) if caster_id is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None)
    if ctx is None:
        return 0
    return int(heal_amount_weapon(int(ctx.stat(StatType.ATTACK)),
                                  int(getattr(ctx, "normal_weapon_hits", 1) or 1)))


def heal_tree(state: "State", caster_id: int) -> Heal:
    """L'arbre de `...Common.HealAbility$$CreateBehaviour` : la feuille `DSLBehaviors$$Heal` NUE.

    `targets_sel = Target()` (le `<bundle@0x90>+0x60` = `ActiveTarget`), `guard = None` -- le natif
    ne pre-filtre PAS ce selecteur (contraste `1037 RevitalizingMalignancy`, qui l'enveloppe d'un
    `HealableUnitsSelector`) : le refus est deja pose EN AMONT par le bit statique
    `TargetIsHealable` du masque, et le gate `HealUnitOperation` tranche en dernier ressort.
    `scope=0` / `remove_effects=True` = les deux champs de
    `IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForHeal`, DECLARES et non herites du
    defaut de la feuille."""
    return Heal(Target(), heal_amount(state, caster_id), guard=None,
                scope=0, remove_effects=True)


class HealAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Common.HealAbility` (id 18,
    `ActiveAbilityType.Heal`) -- le soin GENERIQUE accorde par le trait `Healer`.

    Cast sur un ALLIE SOIGNABLE (adjacent si le caster est de melee, a portee d'arme sinon) :
    restaure `Attack(caster) x Max(WeaponHighestHits(caster), 1)` PV, cape a ce qui manque
    (`FillUpStatComponent$$MaxFillUp`). Aucun degat, aucun effet pose.

    C'est cette entree au registre qui ferme #931-r1 : avant elle, `AbilityHandler` rendait
    `ported: False` -- cast accepte, tour consomme, ZERO PV restaure, et sans masque le moteur
    acceptait en plus des cibles que `ActiveAbilityOperation$$IsInvalidTarget` REFUSE (une cible
    ennemie, une cible non soignable). Les DEUX degradations etaient silencieuses."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Heal)   # 0x12 = 18
    # Ability DERIVEE d'un trait -> AUCUNE entree gameconfig, exactement comme `28 Repair`. `None`
    # rend `AActiveAbility$$SetConfigValuesInTargetingOptions` inerte -- CORRECT ici, le range etant
    # `RANGE_ADJACENT_IF_MELEE_CASTER` (litteral) et non `RANGE_FROM_CONFIG`. La magnitude ne vient
    # pas non plus du gameconfig : elle vient de l'ARME (`heal_amount_weapon`), la branche que
    # `engine.predict.heal_amount_for_ability` reserve a 18 / 1167 / 1212 -- seul `8 MassHeal` lit
    # une variable de config.
    ABILITY_ID = None
    TARGETING_OPTIONS = HEAL_TARGETING_OPTIONS

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        heal_tree(state, caster_id).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        h = next((p for n, p in ectx.emitted if n == "Heal"), None) or {}
        return {"ability": "Heal", "caster": caster_id, "target": target_id,
                "amount": h.get("amount"), "heals": h.get("heals"), "dsl": True}
