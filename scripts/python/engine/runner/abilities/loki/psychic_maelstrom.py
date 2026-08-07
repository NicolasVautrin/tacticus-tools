"""`Abilities.Active.Loki.PsychicMaelstromAbility` (active 1027, Sibyll `astraPrimarisPsy`) -- face
COMBAT (#490). Kit gameconfig `PsychicMaelstrom` : `damageProfile=Psychic`, `range=2`, `nrOfHits=1`,
`chance=75`, `chance_2=50`, `chance_3=25`, `chance_4=10`, `minDmg`/`maxDmg`[level] (rarity-affected).
La face DECISION est deja portee (`playbook/prediction/abilities.py`, mirror de
`IdunBattle.AI.Playbook.Loki.PsychicMaelstromPlaybook$$MakeDamagePredictions`, live bit-exact).

RE (decompile ghidra, build `rnca9r7q6c`) -- `IdunBattleLogic.Entities.Abilities.Active.Loki.
PsychicMaelstromAbility$$ExecuteBehaviour` est un ARBRE DSL, une seule feuille :

    nbRolls = Sum( <DSLFormulas+0x20 = Direct(1)>,
                   ConditionalAmount( Maybe(GetNumberConstant(0x2a chance)),   Direct(1) ),
                   ConditionalAmount( Maybe(GetNumberConstant(0x33 chance_2)), Direct(1) ),
                   ConditionalAmount( Maybe(GetNumberConstant(0x39 chance_3)), Direct(1) ),
                   ConditionalAmount( Maybe(GetNumberConstant(0x3a chance_4)), Direct(1) ) )

    hits    = Multiply( nbRolls, Direct(GetNumberConstant(0x2f nrOfHits)) )

    attack  = AttackWithAbilityDamage(
                  caster  = <DSLSelectors+0x48>,          # singleton CASTER
                  target  = <DSLSelectors+0x60>,          # singleton TARGET (mono-cible)
                  amount  = AActiveAbility$$MinMaxDamage(this, abilityState, isPrediction: 0),
                  abilityOrEffect = AbilityOrEffect(this+0x10 = 1027),
                  options = { +0x00 flags 0,
                              +0x08 DSLSelectors$$Direct(GetDamageProfile()),
                              +0x10 hits,
                              +0x18 killerOverride null },
                  selectionType = 2 )

    AActiveAbility$$ExecuteAtomic( attack, entities, 0x46 )   # GroupType.PsychicMaelstrom_Attack

LE COEUR DU CAS : LE NOMBRE DE COUPS EST UNE **FORMULE**, PAS UN SCALAIRE
------------------------------------------------------------------------
Le natif appelle la surcharge de `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`
dont le 5e argument est un `AbilityDamageBehaviourOptions` portant un `IAmountFormula` de coups
(`AbilityDamageBehaviour+0x98`), et `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$
ExecuteTarget` l'EVALUE a l'execution, par cible (`if (this+0x98 != 0) nrOfHits = <slot 1>(...)`,
defaut 1 sinon). Les quatre `Maybe` tirent donc quatre `NextBool` AU CAST : le nombre de coups
effectif est **1 a 5** (x `nrOfHits`), jamais une constante. Porter une moyenne, un maximum, ou une
valeur ajustee sur une mesure serait un scalaire FITTE -- l'arbre est mirrore, et c'est lui qui
produit le nombre.

CONFIRMATION PAR LA FONCTION SOEUR. `PsychicMaelstromAbility$$GetRollChanceForHitNumber(n)` (lue au
decompile, consommee par le playbook) rend `100` en dur pour `n == 1`, puis `GetNumberConstant` de
`chance` / `chance_2` / `chance_3` / `chance_4` pour `n = 2, 3, 4, >=5` -- meme jeu de cles, meme
ordre que l'arbre, et le `100` en dur correspond au premier terme INCONDITIONNEL du `Sum`.
C'est aussi ce que dit le profil de kit `1hmp100` : un premier coup garanti.

SURCHARGE DE LA FEUILLE, TRANCHEE PAR SES XREFS ENTRANTES (jamais a l'oeil) -- `DSLBehaviors$$
AttackWithAbilityDamage` a QUATRE surcharges, que ghidra decompile toutes sous le meme nom.
`list_xrefs` place l'appel de `PsychicMaelstromAbility$$ExecuteBehaviour` sur celle a
`(caster, target, amount, abilityOrEffect, options, selectionType)` -- le **COEUR**, auquel les
trois autres delegent. Ce n'est donc PAS la surcharge `hits:System.Int32` (qui aurait fige les
coups), et c'est le MEME noeud natif que Stormcaller/SpiritLeech -> meme route portee
`execute_ability_attack(..., is_attack_damage_op=False)`, deja live-validee bit-exact.

`ConditionalAmount(trigger, formulaTrue)` A DEUX ARGUMENTS : la surcharge lue construit le noeud
avec `(trigger, formulaTrue, this+0x18)`, et `this+0x18` est le `Direct(0)` cache de la factory
(`IdunBattleLogic.Entities.DSLFormulas$$.ctor` pose `+0x18 = Direct(0)`, `+0x20 = Direct(1)`,
`+0x28 = Direct(2)`, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)`). La branche FAUSSE vaut donc 0,
et `formulaTrue` (= `+0x20`) vaut 1 : chaque jet reussi ajoute exactement 1 au compte de jets.

ORDRE DES TIRAGES. `IdunBattle.Entities.Formulas.SumAmount$$Calculate` additionne `a, b, c, d, e`
dans cet ordre (cf. `entities/formulas.py::Sum`), donc les quatre `NextBool` partent dans l'ordre
`chance, chance_2, chance_3, chance_4`, AVANT les tirages de degat de l'attaque. Le port evalue le
noeud au meme endroit du pipeline (`AttackWithAttackDamage.execute`, apres la resolution des bornes
et avant `execute_ability_attack`), donc meme flux `state.rng`.

DEGAT. `AActiveAbility$$MinMaxDamage(this, abilityState, isPrediction: 0)` =
`DSLFormulas$$RandomAmount( GetVariableForLevel(0xc minDmg), GetVariableForLevel(0xd maxDmg) )` --
les BORNES, pas une valeur : `AbilityDamageBehaviour$$GetDamage` lit les slots `CalculateMin` et
`CalculateMax` du noeud et rend un `HitDamage(min, Nullable(max))`, le tirage etant fait par coup
dans l'Operation. C'est exactement le mode BORNES de la feuille portee
(`ability_attack_params` -> `minDmg`/`maxDmg` rarity-scales). La branche `isPrediction != 0`
(`Half(Sum(Direct(min), Direct(max)))` = la moyenne) est celle de la face DECISION, deja portee.

RESIDUS NOMMES (aucun ne touche le nombre porte ici) :
  * `IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage(caster)` -- gate de `GetDamage` qui,
    quand il est vrai, force `HitDamage(max)` (min == max). Non porte (aucun porteur dans un roster
    de duel) ; c'est le regime commun a toute la famille, pas propre a 1027.
  * les deux gates par-cible d'`AbilityDamageBehaviour$$Execute`
    (`MatchesUnitSelectionType(unit, selectionType = 2)` et `HasTrait(unit, 0x40e Invincible)`) :
    inertes en mono-cible sur une cible vivante deja validee par le masque de ciblage.
  * `ExecuteAtomic(..., 0x46)` = `GroupType.PsychicMaelstrom_Attack` : frontiere de GROUPE de la
    couche vue, pass-through cote etat (RE #201) -- porte pour le mirror structurel.

DOCTRINE #149 : artefact natif = arbre `DSLFactory` -> arbre DSL mirrore feuille a feuille ;
l'Operation dessous (`AbilityDamageOperation`) reste imperative."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..base import ActiveAbility
from ..targeting import RANGE_FROM_CONFIG, RANGED_BOOL_FALSE, TargetingOptions
from ..targeting_rule import TargetingRule as TR
from ....dsl.base import Const as _AmountConst
from ....dsl.effects import ExecutionContext
from ....entities.ability_constant_type import AbilityConstantType
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.behaviours import AtomicGroup
from ....entities.effects.magnitude import ability_var
from ....entities.formulas import ConditionalAmount, Multiply, Sum
from ....entities.selectors.accessors import Target
from ....entities.triggers import MaybeTrigger
from ....streams.group_type import GroupType
from ..behaviours.combat import AttackWithAttackDamage
from ..behaviours.context import entities_from_state

if TYPE_CHECKING:
    from ...state import State

PSYCHIC_MAELSTROM_ID = "PsychicMaelstrom"

# Les quatre constantes de CHANCE, dans l'ordre ou `ExecuteBehaviour` les lit (== l'ordre des jets
# de `GetRollChanceForHitNumber` pour n = 2, 3, 4, >=5). Membres d'`AbilityConstantType` : c'est
# l'accesseur natif `AbilityConfiguration$$GetNumberConstant` qui fixe CET enum-la et pas
# `AbilityVariableType` (ils partagent 141 ordinaux et nomment autre chose a valeur egale).
_EXTRA_HIT_CHANCE_CONSTANTS = (
    AbilityConstantType.chance,      # 0x2a -- jet du 2e coup
    AbilityConstantType.chance_2,    # 0x33 -- jet du 3e coup
    AbilityConstantType.chance_3,    # 0x39 -- jet du 4e coup
    AbilityConstantType.chance_4,    # 0x3a -- jet du 5e coup
)

# `DSLFormulas+0x20` et `DSLFormulas+0x18` -- les deux constantes CACHEES de la factory, posees par
# `IdunBattleLogic.Entities.DSLFormulas$$.ctor` : `formulaTrue` (1) des quatre `ConditionalAmount`
# et de la premiere branche du `Sum`, et le `formulaFalse` implicite (0) de la surcharge a deux
# arguments. Ce sont des CONSTANTES de noeud, pas des ordinaux qui designeraient une entite.
_DSL_ONE = 1
_DSL_ZERO = 0


def psychic_maelstrom_hits(rng):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.PsychicMaelstromAbility$$ExecuteBehaviour`,
    volet NOMBRE DE COUPS (MIRROR 1:1) :

        Multiply( Sum( Direct(1),
                       ConditionalAmount(Maybe(chance),   Direct(1)),
                       ConditionalAmount(Maybe(chance_2), Direct(1)),
                       ConditionalAmount(Maybe(chance_3), Direct(1)),
                       ConditionalAmount(Maybe(chance_4), Direct(1)) ),
                  Direct(nrOfHits) )

    Rend le NOEUD, jamais un entier : la feuille d'attaque l'evalue A L'EXECUTION
    (`AttackWithAttackDamage.hits_override`, == `AbilityDamageBehaviour$$ExecuteTarget` qui evalue
    `+0x98`), et chaque `Maybe` y consomme un `NextBool` sur `state.rng`.

    `rng` = le RNG que la factory native pose dans chaque `MaybeTrigger` (`DSLFactory+0x18` ->
    `MaybeTrigger+0x18`) : il est pris AU CONSTRUCTEUR, comme le natif. `rng=None` = la branche
    `!CanUseRandom` du natif (cote DECISION/PREDICTION), ou `MaybeTrigger` rend `99 < chance` --
    donc faux pour les quatre chances de 1027, soit `1 x nrOfHits`, exactement ce que predit le
    playbook pour son premier batch.

    Les cinq constantes sont resolues par l'ORACLE gameconfig (`ability_var`, constantes) et non par
    un `ConfigConst` : le `DslContext` du runner ne porte pas de `config` -- meme convention que
    BrazierOfHolyFire / ThriceBlessed / PlagueburstMortar."""
    one = _AmountConst(_DSL_ONE)                       # `DSLFormulas+0x20` = Direct(1)
    zero = _AmountConst(_DSL_ZERO)                     # `DSLFormulas+0x18` = Direct(0)
    rolls = [ConditionalAmount(MaybeTrigger(rng, _chance(key)), one, zero)
             for key in _EXTRA_HIT_CHANCE_CONSTANTS]
    nb_rolls = Sum(one, rolls[0], rolls[1], rolls[2], rolls[3])   # SumAmount a 5 branches, ordre LU
    nr_of_hits = ability_var(PSYCHIC_MAELSTROM_ID, AbilityConstantType.nrOfHits.name,
                             is_constant=True)         # `GetNumberConstant(0x2f)`
    return Multiply(nb_rolls, _AmountConst(int(nr_of_hits or 0)))


def _chance(constant: AbilityConstantType) -> int:
    """`AbilityConfiguration$$GetNumberConstant(config, <constant>)` pour 1027, via l'oracle
    gameconfig. Une constante absente rendrait `None` cote oracle la ou le natif LEVE ; on la
    rabat sur 0 = jet impossible (degradation SURE : aucun coup invente)."""
    return int(ability_var(PSYCHIC_MAELSTROM_ID, constant.name, is_constant=True) or 0)


def psychic_maelstrom_tree(rng, profile: str):
    """Arbre de `PsychicMaelstromAbility$$ExecuteBehaviour` (MIRROR 1:1, cf. docstring module) :

        ExecuteAtomic( AttackWithAbilityDamage(caster, target, MinMaxDamage, AbilityOrEffect(1027),
                                               {profil, hits}, selectionType 2),
                       0x46 = GroupType.PsychicMaelstrom_Attack )

    - `AtomicGroup` = `AActiveAbility$$ExecuteAtomic` (pass-through cote etat, RE #201) ;
    - la feuille est en mode BORNES (`MinMaxDamage` -> `minDmg`/`maxDmg`) et MONO-CIBLE : le natif
      passe les deux singletons `DSLSelectors+0x48`/`+0x60` (CASTER / TARGET), donc la cible du
      message -- pas de selecteur de zone malgre le nom « Maelstrom » ;
    - `native_factory="ability"` = la factory `IdunBattleLogic.Entities.DSLBehaviors$$
      AttackWithAbilityDamage` (famille ABILITY -> `AbilityDamageOperation` : percage/armure + mods
      DEFENSEUR + block + bouclier + caps, AUCUN crit), tranchee par `list_xrefs` ;
    - `hits_override` = le NOEUD de coups, evalue a l'execution (cf. `psychic_maelstrom_hits`) ;
    - `is_melee=False` : `attackRangeType = Ranged` au kit."""
    return AtomicGroup(
        AttackWithAttackDamage(Target(), PSYCHIC_MAELSTROM_ID, profile, is_melee=False,
                               native_factory="ability",
                               hits_override=psychic_maelstrom_hits(rng),
                               ability_type=int(ActiveAbilityType.PsychicMaelstrom)))


class PsychicMaelstromAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.PsychicMaelstromAbility$$ExecuteBehaviour`
    (id 1027, `astraPrimarisPsy` « Sibyll », HERO Astra Militarum) -- cf. docstring module.
    Behaviour = `psychic_maelstrom_tree()` (mirror 1:1). Turn-flags = defauts de la base (1027 est
    absente des overrides `SetsEndTurnFlags` / `SetsActiveAbilityUsedFlag` : le cast termine le
    tour)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.PsychicMaelstrom)  # 1027
    ABILITY_ID = "PsychicMaelstrom"

    # GATE DE CIBLE -- FORME 4, « STATIC-COPY » : `PsychicMaelstromAbility$$.ctor` n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les 0x40 octets du preset
    # `<TargetingOptions statics>+0x180` dans un local et le passe tel quel a
    # `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor`. Le masque EFFECTIF est donc la
    # constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor`, LUE a ce preset :
    #     +0x180 isSelfCasting    = 0
    #     +0x188 range           <- `TargetingRange` statics+0x18 = RANGE_FROM_CONFIG
    #     +0x1a0 forceMeleeTarget = 1 = RangedBool.False
    #     +0x1a8 rules            = 0x4002
    # Decomposition EXHAUSTIVE (`IdunBattle.Core.Services.TargetingRule`), somme = 0x4002 :
    #     0x2     TargetMatchesDynamicRule -> non surchargee cote port -> defaut 0 (PERMISSIF)
    #     0x4000  TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie)
    # PORTEE : `RANGE_FROM_CONFIG` -> `AActiveAbility$$SetConfigValuesInTargetingOptions` pose
    # `overrideRange = GetNumberConstant(0x16 range)` = `constants.range` de 1027 = **2** ;
    # `forceMeleeTarget = RangedBool.False` -> aucun clamp de melee.
    # ⚠ Le preset +0x140 porte le MEME masque 0x4002 et la MEME portee, et ne differe que par
    # `forceMeleeTarget = 0` (RangedBool.True) : recopier la voisine aurait donne le bon masque et
    # le MAUVAIS regime de portee au contact. Lu preset par preset.
    # ⚠ Et « Maelstrom » ne designe PAS une zone : le masque n'ouvre aucun domaine de TUILE, et
    # l'arbre cible le singleton TARGET. Cible = UNE unite ENNEMIE.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsEnemy
    ), self_cast=False, range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # `IdunBattle.Configuration.AbilityConfiguration$$GetDamageProfile(config@+0x60)` ->
        # `DSLSelectors$$Direct(profil)` = l'option `+0x08` de la feuille. Lu au kit (`Psychic`).
        import gameconfig as GC                                   # noqa: PLC0415
        profile = ((GC.ability(PSYCHIC_MAELSTROM_ID) or {}).get("constants") or {}).get(
            "damageProfile") or "Psychic"
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        psychic_maelstrom_tree(state.rng, profile).execute(entities, ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total"),
                    # nb de coups REELLEMENT joues = ce que le noeud a rendu au cast (1..5 x nrOfHits)
                    "hits": len((p.get("attack") or {}).get("per_hit") or [])}
                   for name, p in ectx.emitted if name == "AttackWithAttackDamage"]
        return {"ability": PSYCHIC_MAELSTROM_ID, "caster": caster_id, "target": target_id,
                "group": int(GroupType.PsychicMaelstrom_Attack),   # ExecuteAtomic(..., 0x46)
                "attacks": attacks, "dsl": True}
