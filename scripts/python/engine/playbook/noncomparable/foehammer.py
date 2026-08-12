"""`FoehammerPlaybook` (0x449 = 1097, `spaceRockfist` « Arjac ») -- face DECISION. #957.

REACHABILITY, LUE ET NON SUPPOSEE
---------------------------------
`data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` :

    active   1097   IdunBattle.AI.Playbook.Loki.FoehammerPlaybook

Une SEULE entree, dict `active` (+0x68). Pas de code registered-but-dead.

BASE `NonComparablePlaybook<T>`, LUE dans `frida/classes.tsv` (le `.ctor` decompile NOMME
`ComparablePlaybook<...>$$.ctor(this, 0x449, klass)` : corps trivial DEDUPLIQUE).
RECENSEMENT AU BLOC (`ghidra/functions.tsv`, `18123a570..18123ab20`, encadre par
`FloatingDeath_NormalAttackPlaybook$$.ctor` et `ForwardObserversPlaybook$$CalculateCustomUtility`) :
trois corps CONTIGUS -- `EvaluateNonComparable`, `.cctor`, `.ctor`. Rien de fondu entre eux.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.FoehammerPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))      # cctor : Fix64(1)
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition.MainTile):
        u   = Fix64.op_Implicit(0)
        sel = DSLSelectors.AllDeadUnits(this.dsl.<+0x90>)             # AUCUN argument
        f   = DSLFormulas.Count(this.dsl.<+0x80>, sel)                # IAmountFormula
        n   = f.<IAmountFormula.Calculate>(default(AbilityEntities))  # `AbilityEntities` MEMSET a 0
        u   = u + Fix64.op_Implicit(n)
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10, u))
    return bucket

`IdunBattle.AI.Playbook.Loki.FoehammerPlaybook$$.cctor` : `<statics+0x00> = Fix64(1)`.

⚠ **L'`AbilityEntities` PASSE A LA FORMULE EST VIDE** -- le decompile fait un `memset(.., 0, 0x128)`
juste avant, puis copie ce buffer nul. Ce n'est pas une simplification de lecture : `AllDeadUnits`
n'a besoin d'AUCUNE entite (cf. ci-dessous), donc l'utilite ne depend NI de la cible NI de la
position. Elle est **CONSTANTE sur tout le bucket**.

`AllDeadUnits`, resolu jusqu'au query
--------------------------------------
`IdunBattleLogic.Entities.DSLSelectors$$AllDeadUnits()` construit un
`IdunBattle.Entities.Selectors.AllDeadUnitsSelector` (classe distincte d'`AllDefeatedUnitsSelector`
et d'`AllDeadOrResurrectedUnitsSelector`, dont le `.ctor` est DEDUPLIQUE avec le sien -- le nom
Ghidra du ctor ne dit donc pas la classe). Son `Select`, lui, est propre :

    IdunBattle.Entities.Selectors.AllDeadUnitsSelector$$Select
        = this.<+0x18 = IBattleQuery>.<slot 0x8b>(playerEntityId: null)

Slot RESOLU (`metadata/interface_slots.tsv`) : `IBattleQuery 139 (0x8b) GetAllDeadUnits 1 param`.
Et `IdunBattle.Core.Services.BattleQuery$$GetAllDeadUnits(playerEntityId)` filtre par proprietaire
**seulement si le `Nullable` a une valeur** -- ici il est NUL. Donc : **toutes les unites mortes du
plateau, les DEUX camps confondus**.

⚠ ET LE POOL QU'IL ITERE EXCLUT LES MACHINES OF WAR -- c'est LU, pas suppose (#983). Le corps est
`MatchState$$GetPool(<EntityPool>)` puis `UnitExtensions$$IsDead(entity, state)` par element, et
l'argument est un membre d'`IdunBattle.Entities.Enum.EntityPool` :

    GetAllDeadUnits     -> GetPool(EntityPool.DefeatedUnits = 1)
    GetAllUnits         -> GetPool(EntityPool.AllUnits      = 8)
    GetAllAliveMachines -> GetPool(EntityPool.AliveMachines = 6)

`EntityPool` = `0=AliveUnits, 1=DefeatedUnits, 3=PlayingEffects, 4=EffectsToSimulate, 5=Tiles,
6=AliveMachines, 7=MachinePlatforms, 8=AllUnits, 9=DestroyedMachines` (`frida/enums.tsv`). Les
machines ont donc leurs DEUX pools PROPRES (`6` / `9`), disjoints de ceux des unites : une MoW
detruite entre dans `DestroyedMachines`, JAMAIS dans `DefeatedUnits`. Cote entites c'est le meme
fait -- `EntityType.Machine = 6` n'est pas `EntityType.Unit = 1`.

⇒ le substrat du port (`observeBattle.units[].isDead`, MoW exclues -- elles vivent dans `.mows`)
est **le mirror EXACT** de ce pool, et non une approximation. Le residu `#957-r1`, qui affirmait
l'inverse, est REFUTE : il lisait le litteral `1` comme un `includeDead: true` alors que c'est
`EntityPool.DefeatedUnits` -- exactement la faute que la regle << un entier qui DESIGNE quelque
chose passe par un ENUM >> existe pour rendre visible.

⚠ ET C'EST UN QUIRK : LE PLAYBOOK NE COMPTE PAS CE QUE L'ABILITY UTILISE
------------------------------------------------------------------------
`IdunBattleLogic.Entities.Abilities.Active.Loki.FoehammerAbility$$ExecuteBehaviour` construit son
bonus de degat avec un TOUT AUTRE ensemble -- le meme que `...FoehammerAbility$$GetDeadHeroes` :

    UnitsWithTrait( AllDeadOrResurrectedUnits(), 0x10 = UnitTrait.Hero, 0 )

soit les HEROS morts OU RESSUSCITES. Le playbook, lui, compte `AllDeadUnits()` NU : ni le filtre
`Hero`, ni la branche « ressuscite ». Les deux corps sont dans le meme binaire a quelques fonctions
d'ecart et n'interrogent pas le meme ensemble. On mirrore le CODE, pas l'intention -- meme forme de
quirk qu'`AdaptiveStrategy` (#945 §2) et que `MassDriverAccelerator` (#27-r1).

Effet observable : une bataille ou seuls des SUMMONS sont tombes fait monter l'utilite de decision
de 1097 alors que son degat, lui, n'a pas bouge.

DOMAINE DE CIBLE -- l'ENNEMI, et l'eligibilite DEPEND de la position
---------------------------------------------------------------------
`...FoehammerAbility$$.ctor` -> masque `0x4002` = `TargetIsEnemy | TargetMatchesDynamicRule`, portee
`useRangeFromConfig` (litteral deja relu dans le port COMBAT). Contrairement a `ExemplarOfHate`, la
portee est FINIE : l'ensemble des cibles eligibles change avec la position du caster. Le sweep de
`<GenerateActions>d__7` est donc reellement exerce, et le port passe par `_PlanTargetPlaybook`
(1097 est `AbilityAttackType.DirectTargetAttack`, donc presente dans `computeAttackPlans`).

L'utilite etant CONSTANTE, `Bucket$$AddAction` (remplacement STRICT `>`) garde le PREMIER couple
(position, cible) enumere : l'ORIGINE si une cible y est eligible, sinon la premiere tuile de move.
C'est exactement ce que fait `_PlanTargetPlaybook.generate_candidates` (`ctx.reach_nc` origine
d'abord, `nu > best[2]`).

BORNES DE PORT, nommees
------------------------
* Les MORTS sont lus dans `ctx.obs_units[].isDead` -- `decisionView` GARDE les depouilles, donc
  `observeBattle` est la source (cf. `project_decisionview_keeps_dead`, meme voie que
  `RitesOfRestorationPlaybook`). Canal muet -> `0` mort, donc utilite `0 < MIN_UTILITY` -> aucun
  candidat : le port S'ABSTIENT au lieu de proposer, degradation du meme sens que l'absence
  d'entree au registre (l'etat d'avant ce module).
* Les MACHINES OF WAR sont hors d'`observeBattle.units` (elles vivent dans `.mows`), et **c'est
  CONFORME** : le natif itere `GetPool(EntityPool.DefeatedUnits = 1)`, pool disjoint de
  `DestroyedMachines = 9` (cf. l'en-tete). Ce n'est donc PAS une borne du port -- residu `#957-r1`
  REFUTE le 2026-08-12.
* `MIN_UTILITY = 1` fait de ce playbook un VETO tant qu'AUCUNE unite n'est morte : avant la
  premiere mort, 1097 n'est jamais proposee par le tier NonComparable, et le fallback Comparable
  reprend la main. Ce n'est pas un artefact du port -- c'est le `.cctor`.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook


class FoehammerPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.FoehammerPlaybook` (0x449 = 1097, `spaceRockfist` « Arjac »).

    Utilite = |unites MORTES du plateau, les deux camps| -- CONSTANTE sur toutes les cibles et
    toutes les positions. `MIN_UTILITY = 1` => l'ability n'est proposee qu'a partir du 1er mort."""

    ABILITY_ID = int(ActiveAbilityType.Foehammer)   # 0x449 = 1097 (argument du ctor natif)
    MIN_UTILITY = 1.0     # `...FoehammerPlaybook$$.cctor` : `Fix64$$op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`Fix64(0) + Fix64.op_Implicit(Count(AllDeadUnits()))`.

        L'`AbilityEntities` que le natif passe a la formule est MEMSET a zero : ni `tile` ni
        `target` n'entrent dans le calcul, et c'est LU, pas simplifie."""
        return float(self._dead_unit_count(ctx))

    @staticmethod
    def _dead_unit_count(ctx: NCContext) -> int:
        """`IBattleQuery` slot `0x8b` = `BattleQuery$$GetAllDeadUnits(playerEntityId: null)` :
        toutes les unites mortes, SANS filtre de proprietaire ni de trait (cf. l'en-tete -- ce
        n'est PAS l'ensemble que `FoehammerAbility$$ExecuteBehaviour` utilise).

        Substrat : `observeBattle.units[].isDead`, la meme voie que `RitesOfRestorationPlaybook`."""
        return sum(1 for u in (ctx.obs_units or []) if u.get("isDead"))
