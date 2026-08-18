"""`Abilities.Triggered.Loki.FuryOfTheAncientsAbility` -- passif `FuryOfTheAncients` de
`bloodMephiston` (`TriggeredAbilityType` 0x4df = 1247). Face COMBAT. #927.

i2 (`Abilities/FuryOfTheAncients_CurrentLevelDescription`) : « After moving, deals {nrOfHits}x
{minDmg}-{maxDmg} Psychic Damage to an adjacent enemy and an additional enemy adjacent to the
initial one. For 2 rounds, affected units cannot be revived, healed, repaired, nor otherwise restore
Health. If Mephiston does not move, this ability triggers at the end of his turn. »

--------------------------------------------------------------------------------------------------
LES TROIS FACES, ETABLIES AU DECOMPILE (l'audit `kit-coverage` en annonce UNE) :

  1. **DECISION / MOUVEMENT** -- `IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook.
     u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext`. **DEJA PORTEE** (#32,
     `engine/playbook/fury_of_the_ancients.py`), reconciliee EXACTE sur 31337 s5.
  2. **DECISION / ATTAQUE** -- la classe ne surcharge AUCUNE des voies attaque de
     `TriggeredAbilityPlaybook<T>` : les seules methodes du dump sont `.ctor`,
     `GetDamagePrediction`, `GetDamagedEnemyUtility`, `GetAdjacentEnemyUtility`,
     `CalculateMovementUtilityInStepsInternal` (+ son iterateur). Le corps de base rend
     `yield Fix64.op_Implicit(0)` des que `IsRegularAttack` est faux, ce qui est le cas ici
     (#375). **DEAD -- non portee, verdict grave par test** (`test_927_fury_offline.py` etape 5).
  3. **COMBAT** -- `...$$CreateTrigger` + `...$$CreateBehaviour`. C'est CE module.

--------------------------------------------------------------------------------------------------
CHAINE NATIVE (decompile = verite, build `rnca9r7q6c`). Les SURCHARGES sont tranchees par leurs
XREFS ENTRANTES, jamais par le pseudo-C (piege #585-r3) :

`...$$CreateTrigger` =

    On(0x1c = ArrivedAtFinalTile, ownerNeedsToBeAlive = 1)
      & get_OwnerIsActor
      & op_LogicalNot( AmountIsZero( Damageable( AdjacentEnemies(Caster@DSLSelectors+0x48,
                                                                 unique = 1,
                                                                 selectionType = 3) ) ) )

  * `AdjacentEnemies` = la surcharge **A** `(this, unit, unique, selectionType)` -- xref entrante
    verifiee sur les TROIS call-sites de la classe. Elle PROPAGE le `3`
    (`UnitSelectionType.OnlyAliveAndTargetable`) aux deux etages (`Units` interne et `Enemies`) ;
    la surcharge B, dont le 3e argument est une ENTITE, aurait donne `1` = `OnlyAlive`.
  * `AmountIsZero` = la surcharge **SELECTEUR**, xref entrante verifiee.
  * `On` = la surcharge `(triggerType, ownerNeedsToBeAlive)`, xref entrante verifiee. Le volet
    `On(0x1c)` + owner-vivant est porte par le DISPATCH (`arrived_at_final_tile_triggers`), donc
    absent de `matches`. `On(0x1c)` fire AU PLUS UNE FOIS par activation, par l'un de ses DEUX
    emetteurs natifs (`MoveUnitOperation` apres le 1er deplacement, `FinishUnitTurnOperation` a la
    cloture sans mouvement) : c'est cela, et cela seul, qui porte les deux phrases de l'i2
    (« After moving » / « If Mephiston does not move ... at the end of his turn »).

`...$$GetPossibleTargets` = `Damageable(AdjacentEnemies(Caster, 1, 3))` -- le MEME pool.

`...$$GetSecondTargetSelector(lastTarget)` =

    Damageable( Friends( of = lastTarget,
                         AdjacentUnits(lastTarget, unique = 1, selectionType = 3),
                         selectionType = 3 ) )

  ⚠ `Friends` prend `lastTarget` pour REFERENT, pas le caster : ce sont les allies de la CIBLE,
  c.-a-d. les autres ENNEMIS du porteur. `AdjacentUnits` (et non `AdjacentEnemies`) ne filtre
  aucune equipe -- c'est le `Friends` externe qui le fait, et il le fait par rapport a un AUTRE
  referent. Recopier `AdjacentEnemies(Caster)` ici prendrait les ennemis adjacents au CASTER.

`...$$GetDamagePredictionFormula(damageTarget, abilityState)` =

    DamagePredictionFormula( attacker         = Caster@+0x48,
                             attackerPosition = Tiles(Caster@+0x48),
                             defender         = damageTarget,
                             ability          = <DSLSelectors+0x88>,
                             damage           = MinMaxDamage(abilityState),
                             hits             = ConfigConst(0x2f nrOfHits, config),
                             damageProfile    = GetDamageProfileOrDefault(0xd),
                             prioritizeKills  = **false** )

  Le dernier argument s'ecrit `(void *)((ulonglong)<pile> << 8)` dans le pseudo-C -- octet de poids
  faible NUL, l'idiome INVERSE du `CONCAT71(<pile>, 1)` des booleens VRAIS de la meme fonction.
  Donc pas de bonus x3/x2 sur les cibles tuables : la cle de tri est l'esperance de degat NUE.

`...$$GetTarget(abilityState)` =

    Cache( First( SortByFormula( Damageable(AdjacentEnemies(Caster, 1, 3)),
                                 Sum( GetDamagePredictionFormula(ActiveTarget@+0x68, abilityState),
                                      GetDamagePredictionFormula(
                                          GetSecondTargetSelector(ActiveTarget@+0x68), abilityState) ),
                                 ascending = 0 ),
                  amount = 1, ignoreForcedTargets = 0 ),
           matchAbilityEntities = 1 )

  ⚠ **AUCUN TIRAGE DE CIBLE, ET C'EST LA DIFFERENCE CENTRALE AVEC LES DEUX VOISINS DE FORME.**
  `FabricatorClawArray` et `ChampionOfTheFeast` -- les deux autres consommateurs d'`On(0x1c)` --
  choisissent par `PickRandomly`. Celui-ci choisit par **TRI DECROISSANT** sur la somme des deux
  degats predits (cible + sa propre seconde cible), puis prend le PREMIER. Un port qui recopierait
  le voisin frapperait une cible au hasard et consommerait un tirage qui n'existe pas.
  ⚠ Le tri, lui, N'EST PAS gratuit en PRNG : cf. le bloc PRNG ci-dessous.

`...$$CreateBehaviour(abilityState, triggerType)` =

    ChainAttackDamage( preselectedTargets = GetTarget(abilityState),
                       jumpTargetSelector = lastTargets => GetSecondTargetSelector(lastTargets),
                       maxTargets         = <DSLFormulas+0x20>,
                       dmgAmount          = MinMaxDamage(abilityState),
                       damageProfileType  = GetDamageProfileOrDefault(0xd),
                       hits               = ConfigConst(0x2f nrOfHits, config),
                       abilityType        = AbilityOrEffect(this),
                       extraBehaviour     = AddEffect(0x528 = 1320 FuryOfTheAncients,
                                                      abilityState = AbilityStateReference,
                                                      source  = Owner@+0x30,
                                                      targets = ActiveTarget@+0x68,
                                                      turns   = TurnsFromRounds(
                                                                    ConfigConst(0x69 effectTurns))),
                       maxTargetsExtra    = null,
                       damageOptions      = <AttackDamageBehaviourOptions ZERO>,
                       chainOptions       = <+0x10 = 0, +0x11 = 0, +0x12 = 1> )

  ⚠ **`maxTargets` VAUT 1, ET C'EST LA MESURE QUI LE DIT -- PAS L'OFFSET.** Le compteur natif est un
  DELTA sur la liste preselectionnee (`picked.Count - pres.Count < GetCurrentMaxTargets()`), donc
  `1 preselectionnee + 1 saut = 2 cibles`, ce que le natif fait sur les TROIS montages de
  `probe_927` (et le mutant `maxTargets = 0` MORD sur les trois : une seule cible frappee).

  ⚠⚠ **`#927-r1` FERME (2026-08-18) -- AUCUN DES DEUX OFFSETS N'EST FAUX. LA FAUTE ETAIT UNE
  IDENTITE DE CLASSE, ET C'EST LE PIEGE DEJA DOCUMENTE DU DEPOT : `$$.ctor` N'EST PAS LA CLASSE.**

  Ce que le residu affirmait -- « l'un des deux offsets affiches par le pseudo-C est faux » --
  est REFUTE, a l'ASSEMBLEUR :

    `DSLFormulas$$.ctor`  prologue `mov rdi,rcx` (donc `rdi == this`), puis
                          `xor edx,edx ; call <ctor> ; mov [rdi+0x18],rbx`   -> `+0x18 = Direct(0)`
                          `mov edx,1   ; call <ctor> ; mov [rdi+0x20],rbx`   -> `+0x20 = Direct(1)`
    `DSLTriggers$$AmountIsZero`  `mov rax,[rcx+0x10]` (= le `dsl`, pose par `DSLTriggers$$.ctor`)
                          `mov rax,[rax+0x80]` (= `DSLFormulas` -- prouve par
                          `FuryOfTheAncientsAbility$$CreateBehaviour`, qui appelle
                          `DSLFormulas$$ConfigConst` sur CE champ), puis `mov rdi,[rax+0x20]`.

  Les DEUX call-sites lisent donc bien `Direct(1)`. **CE QUI DIFFERE EST LA CLASSE ALLOUEE**, et le
  discriminant est l'`Il2CppClass*` passe a l'allocateur, jamais le nom du `.ctor` :

    `DSLTriggers$$AmountIsZero`             alloue `<classe A>` avec `minAmount = <formulas+0x20> = 1`
    `DSLTriggers$$AmountIsEqualOrGreater`   alloue la **MEME** `<classe A>`
    `DSLTriggers$$AmountIsGreaterThanZero`  alloue `<classe B>` avec `minAmount = <formulas+0x18> = 0`
    `DSLTriggers$$AmountIsGreater`          alloue la **MEME** `<classe B>`

  Or les deux `ShouldTrigger` ne comparent PAS pareil, et ils sont NOMMES tous les deux :
  `IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger` finit par
  `return minAmount.Calculate() <= value;` -- tandis que
  `IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger` finit par `<`.
  Leurs `.ctor` sont des corps TRIVIAUX que l'ICF a FONDUS : Ghidra affiche
  `AmountIsGreaterAbilityTrigger$$.ctor` aux DEUX sites, et la RE d'origine a donc lu le
  `ShouldTrigger` de la MAUVAISE classe.

  D'ou, verbatim :
    `AmountIsZero(x)` = `op_LogicalNot( AmountIsEqualOrGreater(x, Direct(1)) )`
                      = `NOT (1 <= Count(x))` = **`Count(x) == 0`**.

  Tout s'accorde alors : le NOM `AmountIsZero`, la mesure `probe_927 --solo` (un seul ennemi
  adjacent suffit -> `NOT AmountIsZero` = `Count >= 1`), `maxTargets = <formulas+0x20> = 1` et
  ses 2 cibles frappees, et `AmountIsGreaterThanZero(x)` = `AmountIsGreater(x, Direct(0))` = `0 < x`.
  Le port etait CORRECT des deux cotes (`MAX_TARGETS = 1`, gate `count <= 0` nie) ; seule la
  CITATION etait fausse. Le noeud `entities/triggers.py::AmountIsZero` portait deja la bonne
  lecture, comme `engine/battle_query.py` (#293) qui avait rencontre le meme piege sur l'aura.

  ⚠ `chainOptions+0x12 = 1` (le SEUL octet pose) = coup DIFFERE d'un cran : la 2e cible est choisie
  alors que la 1re est encore VIVANTE. Meme valeur que les deux consommateurs de `ChainAbilityDamage`.

--------------------------------------------------------------------------------------------------
PRNG -- CE QUE LE TRI CONSOMME, ET POURQUOI CE N'EST PAS UN DETAIL (loi #215).

`MinMaxDamage(abilityState)` = `RandomAmount(GetVariableForLevel(0xc minDmg),
GetVariableForLevel(0xd maxDmg))`, et `DamagePredictionFormula$$Calculate` l'evalue par le slot **1**
(`IAmountFormula.Calculate`), PAS par le slot 4 (`CalculateAverage`). Or
`IdunBattle.Entities.Formulas.RandomAmount$$Calculate` TIRE (`IntBasedMersenneTwister$$NextInternal(
min, max + 1)`). Donc :

  * la formule de tri consomme **2 tirages PAR CANDIDAT** (un par `GetDamagePredictionFormula`),
  * y compris quand le sous-selecteur de seconde cible ne rend RIEN : le natif tire AVANT ses trois
    null-guards (`if (defender == null || attacker == null || GetUnit(defender) == null) return 0`),
  * ces tirages precedent ceux de l'attaque elle-meme.

Le port respecte l'ordre : `DamagePredictionFormula.calculate` appelle `damage.evaluate(ctx)` en
TETE, avant tout test. C'est ce que garde l'etape 4 de `test_927_fury_offline.py`.

--------------------------------------------------------------------------------------------------
DOCTRINE #149. L'artefact natif est un `CreateTrigger` + un `CreateBehaviour` : c'est donc un ARBRE
DSL, et c'en est un ici -- aucun ciblage n'est recable a la main. Les deux noeuds qui manquaient au
vocabulaire ont ete portes A LEUR PLACE, pas inlines : `DamagePredictionFormula`
(`entities/formulas.py`, foyer de prediction PARTAGE avec `SortUnitsByDamageUtility`) et
`ChainAttackDamage` (`runner/abilities/behaviours/chain.py`, qui HERITE la boucle deja portee de
`ChainBehaviourBehaviour$$Execute`). La FRONTIERE reste le `.Execute` des feuilles :
`AttackWithAttackDamage` appelle `AttackDamageOperation`, `AddEffect` appelle `AddEffectOperation`.

RESIDUS NOMMES :
  * `Cache(..., matchAbilityEntities = 1)` : le natif prend alors la branche DICT de
    `CacheSelector$$Select` (cache keye par l'`AbilityEntities` recue) ; le noeud porte
    `selectors.geometry.Cache` n'implemente que la branche SLOT UNIQUE. Sans effet ici -- l'arbre
    est rebati a chaque declenchement et `GetTarget` n'est evalue QUE par le
    `preselectedTargets` du chain, donc une seule fois par contexte.
  * `attackerPosition = Tiles(Caster)` et `ability = <DSLSelectors+0x88>` : le foyer de prediction
    porte (`multi_hit_attack_prediction`) lit la position COURANTE de l'attaquant et derive les
    gates du profil -- memes valeurs par un autre chemin, donc les deux selecteurs ne sont pas
    materialises. Ils le deviendraient si un call-site passait une position VIRTUELLE (ce que fait
    la face DECISION, sur son propre rail).
  * `damageOptions` (32 octets ZERO) : `isOutsideAttack = 0`. Le port laisse
    `AttackWithAttackDamage.is_outside_attack` a son defaut `True` -- le `ChainAttackDamageBehaviour`
    natif ouvre lui-meme une attaque par cible (`StartAttackBehaviour@+0x80` /
    `FinishAttackBehaviour@+0x90`), et c'est cette PAIRE que le port materialise en ouvrant une
    attaque NEUVE par cible. Meme residu, mot pour mot, que `ChainAbilityDamage`.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import Count, DamagePredictionFormula, RandomAmount, Sum, TurnsFromRounds
from .....entities.selectors.accessors import ActiveTarget, Owner
from .....entities.selectors.geometry import Cache, PickFirstN
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import (
    AdjacentEnemies, AdjacentUnits, Damageable, Friends, SortByFormula
)
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AmountIsZero, Not, OwnerIsActor, TriggerAnd
from ....abilities.behaviours.chain import ChainAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....components import StatsComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

ABILITY_ID = "FuryOfTheAncients"
MIN_DMG_KEY = "minDmg"                 # `AbilityVariableType` 0xc = 12
MAX_DMG_KEY = "maxDmg"                 # `AbilityVariableType` 0xd = 13
HITS_KEY = "nrOfHits"                  # `AbilityConstantType`  0x2f = 47
EFFECT_TURNS_KEY = "effectTurns"       # `AbilityConstantType`  0x69 = 105
DAMAGE_PROFILE = "Psychic"             # `GetDamageProfileOrDefault(DamageProfileType 0xd)`
IS_MELEE = True                        # `attackRangeType: "Melee"` (gameconfig)

# `UnitSelectionType.OnlyAliveAndTargetable`, le litteral propage par la surcharge A
# d'`AdjacentEnemies` a ses DEUX etages, et par `AdjacentUnits`/`Friends` a leur `Select`.
UNIT_SELECTION_TYPE = 3
ADJACENT_UNIQUE = 1                    # le `unique` des trois selecteurs geometriques

# `IdunBattleLogic.Entities.DSLFormulas$$.ctor` : `+0x18 = Direct(0)`, `+0x20 = Direct(1)`,
# `+0x28 = Direct(2)`, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)`. `CreateBehaviour` passe `+0x20`
# en `maxTargets` -> UN saut supplementaire au-dela du preselectionne.
MAX_TARGETS = 1

# `ChainBehaviourOptions` : le ctor n'ecrit QUE `+0x12 = 1` (coup differe d'un cran) ; `+0x10`
# (repetition de cible) et `+0x11` (repetition immediate) restent a 0.
CHAIN_DEFERRED_HIT = True
CHAIN_ALLOW_REPEAT_TARGETS = False
CHAIN_ALLOW_IMMEDIATE_REPEAT = False

_ON_ARRIVED = int(EventTriggerType.ArrivedAtFinalTile)      # 0x1c = 28

# `AbilityOrEffect(this)` -- l'`abilityType` que `CreateBehaviour` passe au `ChainAttackDamage`.
# ⚠ L'ORDINAL EST AMBIGU : `1247` est AUSSI `EffectType.ProtectorImperative`. On le nomme donc par
# son enum, jamais par sa valeur (cf. `probe_1005r3_fury_ability_type.py`, qui MESURE qu'aucun
# lecteur porte ne les confond).
FURY_OF_THE_ANCIENTS = int(TriggeredAbilityType.FuryOfTheAncients)          # 0x4df = 1247


def _ability_state(state: State, owner_id: int):
    """`(niveau PASSIF, multiplicateur de rarete)` du porteur -- les deux membres de l'`abilityState`
    que `AbilityConfiguration$$GetVariableForLevel` consomme. `FuryOfTheAncients` est un PASSIF :
    slot `passive_ability_level`, JAMAIS `active_ability_level`. `minDmg`/`maxDmg` sont dans
    `variablesAffectedByRarityBonus` -> le multiplicateur mord."""
    e = state.get_entity(owner_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    if ctx is None:
        return None, 100
    return (getattr(ctx, "passive_ability_level", None),
            int(getattr(ctx, "ability_variables_multiplier", 100) or 100))


def min_max_damage(state: State, owner_id: int, rng=None) -> RandomAmount:
    """`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage(abilityState)` =
    `DSLFormulas$$RandomAmount( GetVariableForLevel(config, 0xc = minDmg, abilityState, 0),
                                GetVariableForLevel(config, 0xd = maxDmg, abilityState, 0) )`.

    Les DEUX bornes sont resolues AVANT la construction du noeud (le natif les passe deja calculees
    a la factory) -> des `Const`, pas des `ConfigVar` paresseux. `rng` cale le tirage du slot 1 :
    c'est lui que consomme `DamagePredictionFormula` a chaque candidat du tri."""
    lvl, mult = _ability_state(state, owner_id)
    lo = int(ability_var(ABILITY_ID, MIN_DMG_KEY, lvl, multiplier_pct=mult) or 0)
    hi = int(ability_var(ABILITY_ID, MAX_DMG_KEY, lvl, multiplier_pct=mult) or 0)
    return RandomAmount(Const(lo), Const(hi), rng=rng)


def _config_const(key: str) -> int:
    """`IdunBattleLogic.Entities.DSLFormulas$$ConfigConst(constantType, config)` ->
    `IdunBattle.Entities.Formulas.ConfigAmount` : la CONSTANTE de la config d'ability (pas une
    variable indexee par niveau). Surcharge tranchee par ses arguments : `CreateBehaviour` passe
    `(0x2f, this+0x20 = AbilityConfiguration)` et `(0x69, la meme config)`."""
    import gameconfig as GC
    consts = ((GC.ability(ABILITY_ID) or {}).get("constants") or {})
    try:
        return int(consts.get(key))
    except (TypeError, ValueError):
        return 0


def fury_possible_targets():
    """`...$$GetPossibleTargets` = `Damageable(AdjacentEnemies(Caster@+0x48, 1, 3))`.

    Une NOUVELLE instance a chaque appel, EXPRES : le natif appelle cette forme depuis
    `CreateTrigger` **et** depuis `GetTarget`, et l'ordre du pool n'est pas re-derive."""
    return Damageable(AdjacentEnemies(Caster(), Const(ADJACENT_UNIQUE),
                                      selection_type=UNIT_SELECTION_TYPE))


def fury_second_target_selector(last_target):
    """`...$$GetSecondTargetSelector(lastTarget)` =
    `Damageable( Friends(of = lastTarget, AdjacentUnits(lastTarget, 1, 3), 3) )`.

    `last_target` est un SELECTEUR (le natif recoit un `ITargetsSelector`) : `ActiveTarget()` sous
    le tri, et le `Entities(pickedTargets)` de la boucle de chaine -- la LISTE COMPLETE des cibles
    deja piquees, pas la derniere (`ChainBehaviourBehaviour$$Execute`, cf. `chain.py`)."""
    return Damageable(Friends(AdjacentUnits(last_target, Const(ADJACENT_UNIQUE),
                                            selection_type=UNIT_SELECTION_TYPE),
                              reference=last_target, selection_type=UNIT_SELECTION_TYPE))


def fury_damage_prediction_formula(target_sel, damage, hits: int):
    """`...$$GetDamagePredictionFormula(damageTarget, abilityState)` -- cf. l'en-tete du module.

    `damage` est l'instance `RandomAmount` du call-site : le natif en construit UNE PAR APPEL de
    `GetDamagePredictionFormula`, donc l'arbre de tri en porte DEUX distinctes -- et chacune tire
    a chaque evaluation."""
    return DamagePredictionFormula(Caster(), None, target_sel, None, damage, hits,
                                   damage_profile=DAMAGE_PROFILE, prioritize_kills=False,
                                   is_melee=IS_MELEE)


def fury_target(state: State, owner_id: int, hits: int, rng=None):
    """`...$$GetTarget(abilityState)` -- le TRI, pas un tirage (cf. l'en-tete).

    Les deux `MinMaxDamage` sont construits ICI et non partages : le natif appelle
    `BaseTriggeredAbility$$MinMaxDamage` deux fois, une par branche du `Sum`."""
    first = fury_damage_prediction_formula(ActiveTarget(), min_max_damage(state, owner_id, rng), hits)
    second = fury_damage_prediction_formula(fury_second_target_selector(ActiveTarget()),
                                            min_max_damage(state, owner_id, rng), hits)
    ranked = SortByFormula(fury_possible_targets(), Sum(first, second), ascending=False)
    # `...FuryOfTheAncientsAbility$$GetTarget` finit par `mov r8b, 1 ; jmp <DSLSelectors$$Cache>`
    # -- un TAIL CALL, donc `matchAbilityEntities = 1` (mode DICT), qui est le defaut du noeud.
    return Cache(PickFirstN(ranked, Const(1)))


def fury_trigger_tree():
    """`...$$CreateTrigger`, moins le volet `On(0x1c)` / owner-vivant que porte le DISPATCH :

        get_OwnerIsActor & op_LogicalNot( AmountIsZero( Damageable(AdjacentEnemies(Caster,1,3)) ) )

    `AmountIsZero` prend un SELECTEUR cote natif (surcharge verifiee par xref) ; le noeud porte
    prend une VALEUR, d'ou le `Count(...)` explicite -- meme predicat, `count <= 0`.
    **ZERO tirage** : le sous-arbre du trigger ne porte ni `PickRandomly` ni prediction."""
    return TriggerAnd(OwnerIsActor(), Not(AmountIsZero(Count(fury_possible_targets()))))


def fury_behaviour_tree(state: State, owner_id: int, hits: int, effect_turns: int, rng=None):
    """`...$$CreateBehaviour` = le `ChainAttackDamage` de l'en-tete, avec son `extraBehaviour`.

    L'`AddEffect` est le SECOND membre de l'`op_BitwiseAnd` que le `.ctor` du chain range en
    `+0x88` : il s'execute donc APRES le degat, sur la MEME cible (`ActiveTarget` lie par
    `performBehaviourOnLastTarget`), a chaque maillon."""
    add_effect = AddEffect(int(EffectType.FuryOfTheAncients), EffectType.FuryOfTheAncients.name,
                           ActiveTarget(), duration_rounds=effect_turns,
                           source_ref=Owner())
    return ChainAttackDamage(fury_target(state, owner_id, hits, rng),
                             fury_second_target_selector,
                             Const(MAX_TARGETS),
                             None, ABILITY_ID, DAMAGE_PROFILE,
                             is_melee=IS_MELEE, hits=hits, extra_behaviour=add_effect,
                             allow_repeat_targets=CHAIN_ALLOW_REPEAT_TARGETS,
                             allow_immediate_repeat=CHAIN_ALLOW_IMMEDIATE_REPEAT,
                             deferred_hit=CHAIN_DEFERRED_HIT,
                             # #1005-r3 -- `abilityType = AbilityOrEffect(this)`, 7e argument de
                             # `IdunBattleLogic.Entities.DSLBehaviors$$ChainAttackDamage`. Le port
                             # ne le passait PAS : tout le coup partait avec `CurrentAbility` VIDE.
                             # Meme forme, mot pour mot, que `CalibaniteGreatsword` (`ability_type
                             # = 1316`), qui est l'AUTRE consommateur porte de ce parametre.
                             ability_type=FURY_OF_THE_ANCIENTS)


class FuryOfTheAncientsAbility(TriggeredAbility):
    """`FuryOfTheAncientsAbility` (`TriggeredAbilityType` 0x4df = 1247, passif `bloodMephiston`).

    `On(0x1c = ArrivedAtFinalTile) & OwnerIsActor & NOT AmountIsZero(Damageable(AdjacentEnemies))`
    -> chaine de 2 cibles (`nrOfHits` x Psychic chacune), chacune recevant l'effet 1320
    `FuryOfTheAncients` pour `effectTurns` rounds -- un BLOQUEUR DE SOIN
    (`HealBlockingEffect` : plus de heal, plus de repair, plus de resurrection).

    Cf. l'en-tete du module pour la chaine native, les trois faces, le bloc PRNG et les residus."""
    event_id = _ON_ARRIVED
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.FuryOfTheAncients)     # 0x4df = 1247

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        """`CreateTrigger` moins le volet porte par le dispatch (`On(0x1c)` + owner vivant).

        N'evalue NI `PickRandomly` NI prediction -> aucune consommation PRNG dans le gate."""
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        return bool(fury_trigger_tree().evaluate(entities))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        hits = _config_const(HITS_KEY)
        effect_turns = _config_const(EFFECT_TURNS_KEY)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, None, actor_id=ev.actor_id)
        fury_behaviour_tree(state, self.owner_id, hits, effect_turns,
                            rng=state.rng).execute(entities, ectx)
        attacks = [p for (n, p) in ectx.emitted if n == "AttackWithAttackDamage"]
        effects = [p for (n, p) in ectx.emitted if n == "AddEffect"]
        return {"passive": ABILITY_ID, "owner": int(self.owner_id),
                "hits": int(hits), "effect_turns": int(effect_turns),
                "targets": [a.get("target") for a in attacks],
                "attacks": [a.get("attack") for a in attacks],
                "heal_blocked": [e.get("target") for e in effects if e.get("placed")],
                "dsl": True}
