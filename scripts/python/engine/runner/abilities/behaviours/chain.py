"""Feuille DSL de CHAINE -- mirror de `IdunBattleLogic.Entities.DSLBehaviors$$ChainAbilityDamage`
-> `IdunBattle.Entities.Behaviours.ChainAbilityDamageBehaviour$$.ctor`, dont la BOUCLE est heritee de
`IdunBattle.Entities.Behaviours.ChainBehaviourBehaviour$$Execute`. Namespace natif
`Entities.Behaviours.*`. Consommateurs natifs de la factory (xrefs ENTRANTES, exhaustives) :
`IdunBattleLogic.Entities.Abilities.Active.Loki.StormOfWrathAbility$$ExecuteBehaviour` (1019) et
`IdunBattleLogic.Entities.Abilities.Active.ChainLightningAbility$$CreateBehaviour`.

⚠ NE PAS CONFONDRE avec `engine.entities.behaviours.ChainBehaviour` : ce dernier mirrore
`IdunBattleLogic.Entities.DSLBehaviors$$ChainBehaviour` (la boucle bornee d'Incursion, qui RE-EVALUE un
`Func` de selecteur et lie `ActiveTarget`), pas la chaine A CIBLES ACCUMULEES de cette famille-ci.
Les deux allouent des classes natives DISTINCTES (`ChainSpawnBehaviour` vs
`ChainAbilityDamageBehaviour`), toutes deux derivees de `ChainBehaviourBehaviour`.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from ....dsl.base import _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ....entities.selectors.accessors import ActiveTarget
from ....entities.selectors.geometry import PickRandomly
from ....entities.selectors.units import Sub, UnitSet, Units
from .combat import AttackWithAbilityDamage, AttackWithAttackDamage


class ChainAbilityDamage(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$ChainAbilityDamage(preselectedTargets,
    jumpTargetSelector, maxTargets, dmgAmount, abilityOrEffect, extraBehaviour, damageOptions,
    chainOptions)` -> `IdunBattle.Entities.Behaviours.ChainAbilityDamageBehaviour$$.ctor`, boucle
    heritee `IdunBattle.Entities.Behaviours.ChainBehaviourBehaviour$$Execute`.

    CE QUE LE `.ctor` NATIF CONSTRUIT (lu champ par champ, aucun nom devine) :

        this+0x50 = dsl                                       # base ChainBehaviourBehaviour
        this+0x58 = preselectedTargetsSelector                # <DSLSelectors+0x60> = Target
        this+0x60 = targetsSelector                           # le `System.Func<>` de saut
        this+0x68 = maxTargets                                # formule
        this+0x70 = maxTargetsExtra = null                    # ChainAbilityDamage passe TOUJOURS 0
        this+0xa0 = chainOptions
        this+0x88 = op_BitwiseAnd(<AbilityDamageBehaviour>, extraBehaviour ?? DSLBehaviors$$Nothing())
        this+0x80 = new <StartAttackBehaviour>(<DSLSelectors+0x48 Caster>, <+0x68 ActiveTarget>, opts)
        this+0x90 = new <FinishAttackBehaviour>(<+0x48 Caster>, <+0x68 ActiveTarget>, opts)

    et l'`AbilityDamageBehaviour` INTERNE (classe LUE : le meme `DAT_1833be940` qu'alloue
    `IdunBattleLogic.Entities.DSLBehaviors$$AbilityDamage`) recoit :

        +0x50 = state
        +0x58 = <DSLSelectors+0x30> = Owner                   # le `caster` de la feuille
        +0x60 = Units(<DSLSelectors+0x68> = ActiveTarget, unique: 1, sel: 3)
        +0x68 = dmgAmount                                     # la formule passee a la factory
        +0x70..0x80 = abilityOrEffect (24 octets)
        +0x88..0xa4 = damageOptions (32 octets, layout LU dans `DSLBehaviors$$AbilityDamage` :
                      isOutsideAttack@+0x00, damageProfile@+0x08, hits@+0x10, 0@+0x18)
        +0xa8 = 2 = `UnitSelectionType.OnlyTargetable`

    -> le degat de la chaine est de la famille **ABILITY** (`IdunBattle.Operations.
    AbilityDamageOperation`), PAS `AttackDamageOperation` : aucun crit, aucun tirage de valeur dans
    l'operation (la valeur est CELLE de la formule, evaluee UNE FOIS PAR CIBLE par
    `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$ExecuteTarget` -> `$$GetDamage`). Le
    block, le bouclier et les caps de trait, eux, MORDENT (cf. `AttackWithAbilityDamage`).

    LA BOUCLE (`ChainBehaviourBehaviour$$Execute`, transcrite -- le 2e parametre decompile est le
    `this` reel, le 1er etant le buffer de retour de l'`OperationResult`) :

        picked   = new List<Entity>()          # closure +0x148
        last     = null                        # closure +0x140
        prevExec = null                        # closure +0x150
        executed = true                        # closure +0x138 (`local_3b0 = '\\x01'`)
        pres     = preselectedTargets.Select(entities).ToList()
        foreach t in pres:
            if (options+0x12 && !executed) performBehaviourOnLastTarget()
            last = t ; picked.Add(t) ; executed = false
            if (!options+0x12)            performBehaviourOnLastTarget()
        while (picked.Count - pres.Count < GetCurrentMaxTargets()):
            cand = targetsSelector.Invoke( Entities(picked) )       # <-- TOUT le pick, pas `last`
            if (!options+0x10) cand = cand op_Subtraction Entities(picked)
            if (!options+0x11 && last != null) cand = cand op_Subtraction Entity(last)
            hit = PickRandomly(cand, 1, allowRepeat: 0, maxRepeats: 0x7fffffff).ToList()
            if (hit.Count == 0) break
            assignAndExecuteTarget(hit[0])                          # meme cadence differee
        if (options+0x12 && !executed) performBehaviourOnLastTarget()
        triggerFinishTargetBehaviour(prevExec)

    et `<Execute>g__performBehaviourOnLastTarget|12_3` :

        if (prevExec != last):
            triggerFinishTargetBehaviour(prevExec)                  # this+0x90 sur prevExec
            if (last != null) <this+0x80>.Execute(entities with Target = last)   # StartAttack
        entities.ActiveTarget@+0x20 = last ; entities.PreviousActiveTarget@+0x28 = prevExec
        result.Combine( <this+0x88>.Execute(entities) )             # le degat
        prevExec = last ; executed = true

    DEUX LECTURES QUE LE DECOMPILE IMPOSE, ET QU'ON NE DEVINE PAS :

    1. **L'ORIGINE DU SAUT EST L'ENSEMBLE DES CIBLES DEJA PIQUEES, PAS LA DERNIERE.** Le `Func` est
       invoque avec `DSLSelectors$$Entities(pickedTargets)` -- la LISTE complete. Son parametre est
       nomme `lastTargets` (PLURIEL) dans le decompile. Lire « la derniere cible » ferait rater tout
       saut depuis un maillon anterieur quand le maillon courant n'a plus de voisin libre.
    2. **LE COUP EST DIFFERE D'UN CRAN quand `chainOptions+0x12` est vrai** (c'est le cas des DEUX
       consommateurs natifs, qui posent ce seul octet). Le degat sur la cible N n'est applique
       qu'une fois la cible N+1 CHOISIE. Consequence observable : la selection du maillon N+1 se
       fait sur un plateau ou la cible N est encore VIVANTE -- une cible tuee ne coupe donc pas la
       chaine a l'endroit ou elle tombe. Appliquer le degat tout de suite (`deferred_hit=False`)
       changerait l'ensemble des unites touchees des qu'un maillon meurt.

    PARAMETRES = les arguments de la factory native, dans son ordre.
      * `preselected_sel` = `preselectedTargets`.
      * `jump_target_selector` = callable `(picked_sel: TargetsSelector) -> TargetsSelector`, mirror
        du `System.Func<TargetsSelector, TargetsSelector>` (une NOUVELLE instance de selecteur par
        iteration, comme le natif -- aucune memoisation).
      * `max_targets` = la formule `maxTargets` (RE-EVALUEE a chaque tour, cf.
        `IdunBattle.Entities.Behaviours.ChainBehaviourBehaviour$$GetCurrentMaxTargets`, dont le
        second terme est gate par `this+0x70 maxTargetsExtra` -- TOUJOURS null ici).
      * `amount` = `dmgAmount` (un `AAmountFormula` ; `AActiveAbility$$MinMaxDamage` =
        `RandomAmount(minDmg, maxDmg)` pour les deux consommateurs).
      * `profile` / `hits` / `is_melee` = le contenu LU de `damageOptions` (`damageProfile`, `hits`,
        et la nature declaree du coup -- `attackRangeType` de la config).
      * `allow_repeat_targets` / `allow_immediate_repeat` / `deferred_hit` = les octets
        `chainOptions+0x10` / `+0x11` / `+0x12`. Le nom de la CLASSE d'options n'est pas resolu par
        le dump (aucun symbole ne la nomme) : on la designe donc par ses OFFSETS, et l'effet de
        chaque octet est celui que `Execute` en fait, LU. Les deux consommateurs natifs posent
        `+0x12 = 1` et laissent `+0x10`/`+0x11` a 0.

    RESIDUS NOMMES (non portes, aucun invente) :
      * `this+0x80` / `this+0x90` (`StartAttack`/`FinishAttack` par cible) ne sont pas des noeuds
        distincts ici : le port materialise une attaque NEUVE par cible dans
        `AttackDamageOperation.execute_ability_attack` (defauts `hit_index0=0`, `crit_allowed0`,
        `failed_block0=None`), ce que la paire native produit aussi par cible. Les DECLENCHEURS
        eventuels attaches a ces deux Operations ne sont donc pas emis separement.
      * `UnitSelectionType.OnlyTargetable` (le `2` de `+0xa8`) et le gate `HasTrait(Invincible)`
        d'`AbilityDamageBehaviour` : meme residu que celui deja nomme par `AttackWithAttackDamage`
        (`tile_domain`). Les occupants rendus par `Units(...)` sont deja VIVANTS.
    """
    __slots__ = ("preselected_sel", "jump_target_selector", "max_targets", "damage",
                 "allow_repeat_targets", "allow_immediate_repeat", "deferred_hit",
                 "extra_behaviour")

    def __init__(self, preselected_sel, jump_target_selector, max_targets, amount,
                 profile: str, is_melee: bool = False, hits: int = 1,
                 extra_behaviour: Optional[AbilityBehaviour] = None,
                 allow_repeat_targets: bool = False, allow_immediate_repeat: bool = False,
                 deferred_hit: bool = True):
        self.preselected_sel = preselected_sel
        self.jump_target_selector = jump_target_selector
        self.max_targets = max_targets
        self.allow_repeat_targets = bool(allow_repeat_targets)
        self.allow_immediate_repeat = bool(allow_immediate_repeat)
        self.deferred_hit = bool(deferred_hit)
        self.extra_behaviour = extra_behaviour
        # `AbilityDamageBehaviour(caster = Owner@<DSLSelectors+0x30>, target = Units(ActiveTarget
        # @<+0x68>), amount, damageOptions)` -- la feuille FAMILLE ABILITY, construite par le
        # `.ctor` natif lui-meme (elle n'est PAS un argument de la factory).
        self.damage = AttackWithAbilityDamage(Units(ActiveTarget()), profile, amount,
                                              is_melee=is_melee, hits=hits, multi=True,
                                              native_operation="ability")

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()

        picked: list = []          # closure +0x148 -- `List<Entity> pickedTargets`
        last = None                # closure +0x140 -- `lastTarget`
        prev_exec = None           # closure +0x150 -- derniere cible DEJA frappee
        executed = [True]          # closure +0x138 -- `local_3b0 = '\x01'` avant la 1re iteration
        res = OperationResult.ok()

        def perform_on_last():
            """`ChainBehaviourBehaviour$$u003CExecuteu003Eg__performBehaviourOnLastTarget|12_3`."""
            nonlocal prev_exec, res
            if last is None:
                executed[0] = True
                prev_exec = last
                return
            # `entities.ActiveTarget@+0x20 = last` (le `PreviousActiveTarget@+0x28 = prevExec` que le
            # natif ecrit juste a cote n'est lu par AUCUN noeud porte -> non materialise).
            sub = replace(entities, active_target=last)
            r = self.damage.execute(sub, ectx)
            if self.extra_behaviour is not None:          # `op_BitwiseAnd(<degat>, extraBehaviour)`
                if not getattr(r, "stop", False):
                    r = r.combine(self.extra_behaviour.execute(sub, ectx))
            res = res.combine(r)
            prev_exec = last
            executed[0] = True

        def assign_and_execute(t):
            """`ChainBehaviourBehaviour$$u003CExecuteu003Eg__assignAndExecuteTarget|12_2`."""
            nonlocal last
            if self.deferred_hit and not executed[0]:
                perform_on_last()
            last = t
            picked.append(t)
            executed[0] = False
            if not self.deferred_hit:
                perform_on_last()

        # --- volet PRESELECTIONNE ---------------------------------------------------------------
        pres = [u for u in _units_of(self.preselected_sel, entities)
                if isinstance(u, dict) and u.get("id") is not None]
        for t in pres:
            assign_and_execute(t)

        # --- volet CHAINE : `while (picked.Count - pres.Count < GetCurrentMaxTargets())` ---------
        # Le compteur natif est un DELTA sur la liste PRESELECTIONNEE : `maxTargets` borne les sauts
        # SUPPLEMENTAIRES, pas le total touche.
        while len(picked) - len(pres) < int(self.max_targets.evaluate(entities)):
            picked_sel = UnitSet(list(picked))            # `DSLSelectors$$Entities(pickedTargets)`
            cand_sel = self.jump_target_selector(picked_sel)
            if not self.allow_repeat_targets:             # chainOptions+0x10 == 0
                cand_sel = Sub(cand_sel, picked_sel)
            if not self.allow_immediate_repeat and last is not None:   # chainOptions+0x11 == 0
                cand_sel = Sub(cand_sel, UnitSet([last]))
            hit = PickRandomly(cand_sel, 1, allow_duplicates=False,
                               max_duplicates=0x7FFFFFFF).evaluate(entities)
            hit = [u for u in hit if isinstance(u, dict) and u.get("id") is not None]
            if not hit:
                break
            assign_and_execute(hit[0])

        if self.deferred_hit and not executed[0]:
            perform_on_last()
        return res


class ChainAttackDamage(ChainAbilityDamage):
    """`IdunBattleLogic.Entities.DSLBehaviors$$ChainAttackDamage(preselectedTargets,
    jumpTargetSelector, maxTargets, dmgAmount, damageProfileType, hits, abilityType,
    extraBehaviour, maxTargetsExtra, damageOptions, chainOptions)` ->
    `IdunBattle.Entities.Behaviours.ChainAttackDamageBehaviour$$.ctor` (#927).

    **LA BOUCLE EST LA MEME** -- `ChainAttackDamageBehaviour` derive de `ChainBehaviourBehaviour`
    comme `ChainAbilityDamageBehaviour`, et son `.ctor` remplit LES MEMES champs, dans le meme
    ordre (`+0x58 preselected`, `+0x60 targetsSelector`, `+0x68 maxTargets`, `+0x70
    maxTargetsExtra`, `+0xa0 chainOptions`, `+0x80 StartAttackBehaviour`, `+0x90
    FinishAttackBehaviour`, `+0x88 op_BitwiseAnd(<degat>, extraBehaviour ?? Nothing())`). D'ou
    l'heritage : la boucle et `performBehaviourOnLastTarget` ne sont PAS re-ecrites.

    **CE QUI DIFFERE, ET C'EST LA SEULE CHOSE** : le behaviour interne `+0x88`. La ou
    `ChainAbilityDamage` alloue un `AbilityDamageBehaviour` (famille ABILITY, aucun crit, aucun
    tirage dans l'operation), celui-ci alloue un **`AttackDamageBehaviour`** :

        AttackDamageBehaviour..ctor(state,
                                    <DSLSelectors+0x30 = Owner>,
                                    Units(<DSLSelectors+0x68 = ActiveTarget>, unique: 1, sel: 3),
                                    dmgFormula,
                                    Nullable<DamageProfileType>(damageProfileType),
                                    hits,
                                    abilityOrEffect,
                                    Nullable<AttackDamageBehaviourOptions>(damageOptions),
                                    2 = UnitSelectionType.OnlyTargetable)

    -> famille **ATTACK** : `AttackDamageOperation`, donc CRIT, BLOCK, bouclier et pipeline
    after-hit complets, et un tirage de valeur PAR COUP dans l'operation. `damageProfileType` et
    `hits` sont des ARGUMENTS de la factory ici (`ChainAbilityDamage` les lisait dans ses
    `damageOptions`) -- c'est la seule difference de SIGNATURE entre les deux.

    RESIDUS NOMMES -- les MEMES que `ChainAbilityDamage`, pour la meme raison :
      * `this+0x80` / `this+0x90` (`StartAttackBehaviour` / `FinishAttackBehaviour` par cible) ne
        sont pas materialises separement : le port ouvre une attaque NEUVE par cible dans
        `AttackDamageOperation.execute_ability_attack` (d'ou `is_outside_attack` laisse a son defaut
        `True`), ce que la paire native produit aussi par cible. Les declencheurs eventuels attaches
        a ces deux Operations ne sont donc pas emis separement ;
      * `UnitSelectionType.OnlyTargetable` (le `2` du dernier argument) : les occupants rendus par
        `Units(...)` sont deja VIVANTS."""
    __slots__ = ()

    def __init__(self, preselected_sel, jump_target_selector, max_targets, amount,
                 ability_id: str, profile: str, is_melee: bool = True, hits=None,
                 extra_behaviour: Optional[AbilityBehaviour] = None,
                 allow_repeat_targets: bool = False, allow_immediate_repeat: bool = False,
                 deferred_hit: bool = True, level_slot: str = "passive",
                 ability_type=None, amount_spread_pct: int = 0):
        self.preselected_sel = preselected_sel
        self.jump_target_selector = jump_target_selector
        self.max_targets = max_targets
        self.allow_repeat_targets = bool(allow_repeat_targets)
        self.allow_immediate_repeat = bool(allow_immediate_repeat)
        self.deferred_hit = bool(deferred_hit)
        self.extra_behaviour = extra_behaviour
        # `AttackDamageBehaviour(caster = Owner@<DSLSelectors+0x30>, target = Units(ActiveTarget
        # @<+0x68>), dmgFormula, profile, hits, options)` -- construit par le `.ctor` natif lui-meme,
        # ce n'est PAS un argument de la factory. En revanche le `dmgFormula` qu'il recoit, LUI, EST
        # le 4e argument de la factory (`dmgAmount`), et les deux consommateurs natifs ne le
        # remplissent PAS de la meme facon (#940) :
        #   * `FuryOfTheAncientsAbility$$CreateBehaviour` passe `BaseTriggeredAbility$$MinMaxDamage`
        #     = `RandomAmount(minDmg, maxDmg)` -> `amount = None` cote port = mode BORNES, dont
        #     `ability_attack_params` rend exactement les deux bornes depuis la config ;
        #   * `KissOfDeathAbility$$ExecuteBehaviour` passe `DSLFormulas$$Direct(
        #     GetVariableForLevel(0xb = dmg))` -- une valeur MONO, qui n'a NI minDmg NI maxDmg dans
        #     sa config. La rabattre sur le mode bornes lirait deux cles ABSENTES.
        # D'ou : `amount` non nul -> mode `amount` de la feuille, TEL QUEL. `amount_spread_pct` porte
        # l'octet +6 du `Nullable<AttackDamageBehaviourOptions>` de la factory (0 = aucune variance
        # d'arme) ; il n'a de sens qu'en mode `amount`, comme le dit la feuille.
        self.damage = AttackWithAttackDamage(Units(ActiveTarget()), ability_id, profile,
                                             is_melee=is_melee, multi=True, hits=hits,
                                             level_slot=level_slot, amount=amount,
                                             ability_type=ability_type,
                                             amount_spread_pct=amount_spread_pct)


class ChainBehaviourGeneric(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$ChainBehaviour(preselectedTargets, jumpTargetSelector,
    maxTargets, behaviour, options)` -- la variante GENERIQUE de la meme famille (#894).

    LU : la factory n'alloue PAS de sous-classe, elle construit
    `IdunBattle.Entities.Behaviours.ChainBehaviourBehaviour$$.ctor(this_00, dsl, maxTargets,
    preselectedTargets, jumpTargetSelector, behaviour, options, 0)` -- c'est la classe de BASE
    elle-meme. La boucle est donc EXACTEMENT celle transcrite dans `ChainAbilityDamage` ci-dessus
    (meme `Execute`, memes lambdas `assignAndExecuteTarget` / `performBehaviourOnLastTarget`,
    meme delta `picked.Count - pres.Count`, meme invocation du `Func` sur `Entities(picked)` --
    la liste COMPLETE, pas la derniere cible). Seule difference : `this+0x88` n'est pas un
    `AbilityDamageBehaviour` construit par le ctor mais le `behaviour` PASSE par l'appelant.

    ⚠ POURQUOI CETTE CLASSE ET PAS `engine.entities.behaviours.ChainBehaviour` : ce dernier est un
    mirror SIMPLIFIE, ecrit pour `IncursionAbility` -- il ignore `preselectedTargets` (`init`,
    stocke mais jamais lu par son `execute`), invoque son `Func` sur `entities` au lieu de
    `Entities(picked)`, et ne connait pas le cran DIFFERE de `chainOptions+0x12`. Pour Incursion,
    `preselectedTargets` vaut `Null()` et l'ecart est invisible ; pour `ArcScourge` il vaut
    `Target@<DSLSelectors+0x60>` -- la premiere victime EST la cible designee -- et `+0x12` vaut 1.
    Un port sur la classe simplifiee raterait donc la premiere cible ET l'ordre des coups.
    L'ecart de `entities.behaviours.ChainBehaviour` est un RESIDU NOMME, pas repare ici (son seul
    consommateur, Incursion, n'est pas affecte).

    `body` = le `behaviour` natif ; il est execute avec `ActiveTarget` lie a la cible du maillon
    (`entities.ActiveTarget@+0x20 = last`), comme le fait `performBehaviourOnLastTarget`.
    """
    __slots__ = ("preselected_sel", "jump_target_selector", "max_targets", "body",
                 "allow_repeat_targets", "allow_immediate_repeat", "deferred_hit")

    def __init__(self, preselected_sel, jump_target_selector, max_targets,
                 body: AbilityBehaviour, allow_repeat_targets: bool = False,
                 allow_immediate_repeat: bool = False, deferred_hit: bool = True):
        self.preselected_sel = preselected_sel
        self.jump_target_selector = jump_target_selector
        self.max_targets = max_targets
        self.body = body
        self.allow_repeat_targets = bool(allow_repeat_targets)
        self.allow_immediate_repeat = bool(allow_immediate_repeat)
        self.deferred_hit = bool(deferred_hit)

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()

        picked: list = []
        last = None
        prev_exec = None
        executed = [True]
        res = OperationResult.ok()

        def perform_on_last():
            """`ChainBehaviourBehaviour$$u003CExecuteu003Eg__performBehaviourOnLastTarget|12_3`."""
            nonlocal prev_exec, res
            if last is None:
                executed[0] = True
                prev_exec = last
                return
            sub = replace(entities, active_target=last)
            res = res.combine(self.body.execute(sub, ectx))
            prev_exec = last
            executed[0] = True

        def assign_and_execute(t):
            """`ChainBehaviourBehaviour$$u003CExecuteu003Eg__assignAndExecuteTarget|12_2`."""
            nonlocal last
            if self.deferred_hit and not executed[0]:
                perform_on_last()
            last = t
            picked.append(t)
            executed[0] = False
            if not self.deferred_hit:
                perform_on_last()

        pres = [u for u in _units_of(self.preselected_sel, entities)
                if isinstance(u, dict) and u.get("id") is not None]
        for t in pres:
            assign_and_execute(t)

        while len(picked) - len(pres) < int(self.max_targets.evaluate(entities)):
            picked_sel = UnitSet(list(picked))
            cand_sel = self.jump_target_selector(picked_sel)
            if not self.allow_repeat_targets:
                cand_sel = Sub(cand_sel, picked_sel)
            if not self.allow_immediate_repeat and last is not None:
                cand_sel = Sub(cand_sel, UnitSet([last]))
            hit = PickRandomly(cand_sel, 1, allow_duplicates=False,
                               max_duplicates=0x7FFFFFFF).evaluate(entities)
            hit = [u for u in hit if isinstance(u, dict) and u.get("id") is not None]
            if not hit:
                break
            assign_and_execute(hit[0])

        if self.deferred_hit and not executed[0]:
            perform_on_last()
        return res
