"""Les `PowerUp_*` NON-BOOST (#1083-r3) -- la tranche 2 de la famille `APowerUpAbility`.

La tranche 1 (#1083-r1, `loki/power_up.py`) a porte la BASE : le trigger
`APowerUpAbility$$CreateTrigger` et le `CreateBehaviour`
`AddShield & AddPctBasedBoost & AddAbsoluteBoost & <SelfContained> & AdditionalBehavior`.
Ce module ajoute les mecaniques qui ne sont PAS des boosts de stat.

--------------------------------------------------------------------------------------------------
LA PARTITION EST LUE, PAS SUPPOSEE (balayage exhaustif de `ghidra/functions.tsv`, build `rnca9r7q6c`)
--------------------------------------------------------------------------------------------------

`get_PctBasedStatBoost` a EXACTEMENT deux proprietaires (`PowerUp_Damage`, `PowerUp_Health`),
`get_AbsoluteStatBoost` EXACTEMENT deux (`PowerUp_Hits`, `PowerUp_MeleeHits`),
`SelfContainedBoostEffect` AUCUN, et `AdditionalBehavior` quatre (`PowerUp_Armor` -- porte par la
tranche 1 -- plus les TROIS de ce module). Un override qui rend un record ou un arbre a un corps NON
trivial, donc un proprietaire dans la table : l'absence y est concluante, contrairement au cas
general (cf. CLAUDE.md « L'ABSENCE d'une methode dans les tables ne prouve RIEN »).

⚠ **ZERO `CreateTrigger` surcharge chez les 22 `PowerUp_*`** : le trigger de la tranche 1 vaut pour
tous, et n'est donc PAS re-ecrit ici. C'est ce qui permet a ces classes de se reduire a leur seul
vslot.

Les trois de ce module heritent donc `AddShield` -- et c'est le GAMECONFIG, pas le code, qui decide
s'il pose quelque chose (cf. `PowerUp_Bomb` ci-dessous, qui n'a pas de `shieldPct`).

--------------------------------------------------------------------------------------------------
ARTEFACTS NATIFS (decompile ghidra, build `rnca9r7q6c` -- decompile = verite)
--------------------------------------------------------------------------------------------------

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PowerUp_ReactivateAbilityAbility$$AdditionalBehavior` :

    return ResetActiveAbility(target, allowUseless = true);

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PowerUp_HealingAbility$$AdditionalBehavior` :

    healOpts   = new HealBehaviourOptions   { <+0x33> = 1, <+0x34> = 1 }
    amountHeal = PercentageOf( StatAmount(target, 5 = Health, 2 = Maximum, null, 0),
                               Get(GetNumberConstant(config, 0x13 = HealPercentage)), 0 )
    heal       = Heal(Owner@sel+0x30, target, amountHeal, healOpts)
    repairOpts = new RepairBehaviourOptions { <+0x16> = 1, <+0x10> = 0, <+0x14> = 1 }
    amountRep  = <la MEME expression, re-construite a l'identique>
    repair     = Repair(Owner@sel+0x30, target, amountRep, AbilityOrEffect(this), repairOpts)
    return If( IsMechanical(target, 0), repair, heal )

`target` est l'`Actor` (`DSLSelectors+0x40`) que `APowerUpAbility$$CreateBehaviour` passe a TOUS ses
volets -- c'est-a-dire l'unite qui a MARCHE sur le power-up, jamais le power-up lui-meme.

⚠ LE STAT LU PAR LE VOLET SOIN EST `Health / **Maximum**` (`StatPart` 2), alors que le BOUCLIER
commun d'`APowerUpAbility$$AddShield` lit `Health / **Initial**` (3). Les deux parts coexistent donc
dans le MEME arbre pour `PowerUp_Healing`, et elles divergent des qu'un modificateur de PV max est
actif (typiquement apres un `PowerUp_Health`). Ne pas les confondre -- meme piege que celui deja
nomme pour `PowerUp_ArmorEffect` par la tranche 1.

--------------------------------------------------------------------------------------------------
LES OPTIONS DE `Heal` / `Repair` : LES DEFAUTS SONT POSES PAR LE CTOR
--------------------------------------------------------------------------------------------------

Les feuilles portees prennent `(scope, remove_effects)`, deja apparies aux fabriques natives par
#520 : `ForHeal`/`ForRepair` -> `(0, True)`, `ForRegenerate` -> `(1, False)`, avec
`options.scope@+0x10` / `options.removeEffects@+0x14` LUS pour la famille Repair.

Mesure comparative des constructions (offsets relatifs, donc stables entre builds) :

    HealBehaviourOptions   ctor pose <+0x30> = 1, <+0x34> = 3
                           ForHeal       ajoute <+0x2c> = 0, <+0x30> = 1
                           ForRegenerate ajoute <+0x2c> = 1, <+0x30> = 0
                           PowerUp_Healing pose <+0x33> = 1, <+0x34> = 1 -- et NE TOUCHE NI 0x2c NI 0x30

    RepairBehaviourOptions ctor pose <+0x14> = 1, <+0x18> = 3
                           ForRepair     ajoute <+0x10> = 0, <+0x14> = 1
                           ForRegenerate ajoute <+0x10> = 1, <+0x14> = 0
                           PowerUp_Healing pose <+0x10> = 0, <+0x14> = 1, <+0x16> = 1

Donc, sur les DEUX champs dont le role est LU (`scope`, `removeEffects`) :
  * cote REPAIR, `PowerUp_Healing` ecrit exactement ce qu'ecrit `ForRepair()` -> `(0, True)` ;
  * cote HEAL, il ne les touche PAS, donc ils gardent les valeurs du ctor -> `(0, True)` aussi.
C'est-a-dire les DEFAUTS des deux feuilles portees, dans les deux branches. Ni l'un ni l'autre n'est
une regeneration.

⚠ RESIDU NOMME : `<+0x33>`/`<+0x34>` (heal) et `<+0x16>`/`<+0x18>` (repair) sont poses par le natif
et n'ont PAS d'accesseur decompile -- leur role n'est pas LU. Que `<+0x34>`/`<+0x18>` soient un
`UnitSelectionType` (defaut `3 = OnlyAliveAndTargetable`, ramene a `1 = OnlyAlive` cote heal
seulement) est COHERENT avec les valeurs mais reste une HYPOTHESE. Le port ne fait porter aucune
decision a ces champs : il appelle les feuilles avec les defauts LUS, et nomme l'ecart plutot que de
le deviner.

⚠ AUCUN des deux volets ne passe de `guard` : le natif donne `target` NU aux deux feuilles, sans
`HealableUnitsSelector` en amont -- c'est le gate de l'Operation qui tranche. Meme regime que
`RepairAbility$$CreateBehaviour`, deja note dans la docstring de `Repair`. Poser
`healable_heal_type_0` ici EXCLURAIT du set des cibles que le natif y laisse.

DOCTRINE #149 : le trigger reste le collapse imperatif de la base ; les behaviours sont des ARBRES
DSL (`If` / `Heal` / `Repair` / `ResetActiveAbility`), la frontiere etant le `.Execute` des feuilles.
"""
from __future__ import annotations

from .....entities.ability_constant_type import AbilityConstantType
from .....entities.behaviours import If as IfBehaviour
from .....entities.formulas import Get, PercentageOf, StatAmount
from .....entities.selectors.accessors import Actor
from .....entities.stats import StatPart, StatType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import is_mechanical
from ....abilities.behaviours.ability_state import ResetActiveAbility
from ....abilities.behaviours.stats import Heal, Repair
from ....state import State
from .power_up import APowerUpAbility, _const

#: `GetNumberConstant(config, 0x13)` du volet soin de `PowerUp_HealingAbility$$AdditionalBehavior`.
HEAL_PCT_KEY = AbilityConstantType.HealPercentage        # 0x13 = 19
#: `ResetActiveAbility(target, allowUseless = **true**)` -- le litteral natif, lu au site.
#: ⚠ Le parametre s'appelle `allowUseless` dans la signature native
#: (`DSLBehaviors.ResetActiveAbility(units:ITargetsSelector, allowUseless:System.Boolean)`), et la
#: feuille portee le nomme `ignore_turn_flag`. Meme POSITION, meme destination (il est transmis tel
#: quel au gate `BattleQuery$$EntityCanHaveActiveAbilityReset`), donc le port est fidele -- mais le
#: nom porte n'a pas de repondant dans le binaire.
REACTIVATE_ALLOW_USELESS = True


def heal_amount_tree(ability_name: str):
    """L'expression de montant COMMUNE aux deux branches de
    `PowerUp_HealingAbility$$AdditionalBehavior` -- le natif la construit DEUX FOIS a l'identique
    (une par branche), ce qui est sans effet observable : elle est deterministe (aucun `RandomAmount`)
    et les deux branches sont exclusives.

        PercentageOf( StatAmount(target, Health, **Maximum**), Get(HealPercentage) )

    ⚠ L'ORDRE DES OPERANDES EST INVERSE cote port (`PercentageOf(pct, base)` contre
    `PercentageOf(base, pct)` natif) -- meme convention que la tranche 1, cf.
    `entities/formulas.py`. Rend `None` quand la constante manque, ce qui eteint le volet."""
    pct = _const(ability_name, HEAL_PCT_KEY)
    if pct is None:
        return None
    return PercentageOf(Get(pct),
                        StatAmount(Actor(), int(StatType.HEALTH), int(StatPart.MAXIMUM)))


class PowerUpReactivateAbilityAbility(APowerUpAbility):
    """`PowerUp_ReactivateAbilityAbility$$AdditionalBehavior`, corps ENTIER :

        return ResetActiveAbility(target, allowUseless = true);

    Herite donc de la base son BOUCLIER (`shieldPct = 100`, `nrOfRounds = 1` au gameconfig) et n'y
    ajoute que la remise a zero. Aucun boost de stat : ni `get_PctBasedStatBoost` ni
    `get_AbsoluteStatBoost` ne sont surcharges (balayage exhaustif)."""

    ABILITY_NAME = "PowerUp_ReactivateAbility"
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.PowerUp_ReactivateAbility)      # 1272

    def additional_behavior(self, state: State):
        return ResetActiveAbility(Actor(), ignore_turn_flag=REACTIVATE_ALLOW_USELESS)


class PowerUpHealingAbility(APowerUpAbility):
    """`PowerUp_HealingAbility$$AdditionalBehavior`, corps ENTIER :

        return If( IsMechanical(target, 0), Repair(...), Heal(...) );

    Les deux branches portent le MEME montant (`HealPercentage` % des PV **MAXIMAUX** de la cible) et
    les MEMES options (`(scope=0, remove_effects=True)`, cf. l'en-tete du module). Herite aussi le
    bouclier de la base (`shieldPct = 100`).

    `Heal`/`Repair` prennent leur SOIGNEUR dans `entities.caster`, que le vecteur du power-up pose a
    l'`owner` (le power-up lui-meme) -- exactement le `Owner@sel+0x30` que le natif passe en premier
    argument des deux feuilles."""

    ABILITY_NAME = "PowerUp_Healing"
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.PowerUp_Healing)                # 1273

    def additional_behavior(self, state: State):
        montant = heal_amount_tree(self.ABILITY_NAME)
        if montant is None:
            return None                              # constante absente -> volet eteint
        amount_fn = (lambda entities, ectx, _n=montant: int(_n.evaluate(entities)))
        # `(scope, remove_effects)` = les DEFAUTS des deux feuilles, et c'est ce que le natif ecrit
        # (cf. l'en-tete) -- explicites plutot qu'implicites, pour que le fait soit fige au site.
        heal = Heal(Actor(), amount_fn, guard=None, scope=0, remove_effects=True)
        repair = Repair(Actor(), amount_fn, guard=None, scope=0, remove_effects=True)
        # `IsMechanical(target, 0)` -- le `selectionType` natif est `0 = Any`, qui est aussi le
        # defaut de la factory portee ; il est ecrit pour que le litteral reste visible.
        return IfBehaviour(is_mechanical(Actor(), selection_type=0), repair, heal)
