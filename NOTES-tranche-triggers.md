# Tranche TRIGGERS & CASCADE D'EFFETS -- notes de travail (WIP)

Residus : #963-r1, #936-r1-r2, #890-r2, #889-r4, #890-r1, #982-r4.

## #963-r1 -- premisse RE-MESUREE : CONFIRMEE (partiellement)

`IdunBattleLogic.Entities.DSLTriggers$$AreEnemies(dsl, sel1, sel2, selectionType)` ->
`IdunBattle.Entities.Triggers.AreFriendsAbilityTrigger$$.ctor(unit1, unit2, query, selectionType)`
(champ +0x28) puis `op_LogicalNot`.
`AreFriendsAbilityTrigger$$ShouldTrigger` : `u1 = sel1.SelectSingle(entities)` (null -> FAUX),
`u2 = sel2.SelectSingle(entities)` (null -> FAUX), puis `battleQuery.<slot 0x92>(u1, u2, selectionType@+0x28)`
= `IdunBattle.Core.Services.BattleQuery$$AreFriends` -> `IdunBattle.Entities.UnitExtensions$$IsFriend(u1, u2, selectionType, state)` :
  * `selectionType == 0` (ByCurrentTeam)  -> `EntityExtensions$$GetCurrentPlayer` des deux
  * `selectionType == 1` (ByOriginalTeam) -> `EntityExtensions$$GetOriginalPlayer` des deux
  * autre -> FAUX
puis compare `player@+0x20@+0x24` (TeamId).

CONFIRME au decompile : `RedRampage_BuffAbility$$CreateTrigger` passe bien `(void *)0x1`.

## #890-r2 -- premisse RE-MESUREE : CONFIRMEE, et la cause est PLUS PRECISE que l'enonce

`IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$Execute` :
    src = <selecteur @+0x58>.SelectSingle(entities)      ; peut etre NULL
    foreach (target in <selecteur @+0x60>.Select(entities))
        source = src != null ? src : target              <-- le DEFAUT est la CIBLE, pas le caster
        processor.<slot 0x10>(source, target, effectBuilder, statType@+0x68, duration)
Le port passe `source = entities.caster` inconditionnellement.
