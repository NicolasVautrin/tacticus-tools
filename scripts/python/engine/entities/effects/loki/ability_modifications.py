"""Effets qui modifient les CONSTANTES D'UNE ABILITY d'une autre unite (et non une stat).

Famille a un seul membre dans le build `gqfc5mff6c` : `ListenUpMaggotsEffect` (0x426 = 1062), le passif
de `astraSmnKell` (« Kell »). C'est la SEULE source native d'ecriture dans
`IdunBattle.Entities.Components.ActiveAbilityModificationsComponent` (xrefs exhaustives de
`IdunBattle.Operations.AddUnitActiveAbilityModificationOperation$$Execute`), et donc le seul chemin qui
rende `IdunBattle.Entities.UnitExtensions$$GetAbilityStatModification` NON NUL.

Chaine complete (#95-RESTE2) :
  `SwornProtectorAbility` (passif d'`astraCreed`) -> spawn de Kell
    -> `ListenUpMaggotsAbility` (`On(AbilityInit)`) -> `AddEffect(0x426, Self)`
      -> CET effet -> `AddUnitActiveAbilityModification(Parent(Self)=Creed, key, delta)`
        -> lu par les 2 call-sites de
           `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour`.
"""
from __future__ import annotations

import gameconfig as GC

from ..base import BaseEffect
from ...selectors.tiles import Caster, Parent
from ....entities.ability_constant_type import AbilityConstantType   # #270-r1-r1-r3

# Index des constantes lues par `IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$ApplyInternal`
# (`AbilityConfiguration.GetNumberConstant(config, <index>)`), DANS L'ORDRE du decompile.
LUM_CONST_RANGE = AbilityConstantType.range          # GetNumberConstant(0x16) -> ListenUpMaggots.constants['range']       = 3
LUM_CONST_NR_OF_SUMMONS = AbilityConstantType.nrOfSummons  # GetNumberConstant(0x10) -> ListenUpMaggots.constants['nrOfSummons'] = 1
LISTEN_UP_MAGGOTS_ABILITY = "ListenUpMaggots"


class ListenUpMaggotsEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect` (0x426 = 1062) — MIRROR du decompile.

    `.ctor` : `BaseEffect(AbilityOrEffect.op_Implicit(0x427 = ListenUpMaggots, l'ability TRIGGERED
    1063), 1)` -> l'`EffectSource` est l'ability du porteur.

    `CreateTargetSelector` = `Parent(Self@0x148)` : l'effet est PORTE par Kell et s'APPLIQUE sur son
    parent (Creed). C'est la subtilite du kit — le buff n'est pas sur le porteur.

    `CreateActiveCondition` = `df@0x98` (la condition de base pre-cachee du `DSLFactory`, cf.
    `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared`) : AUCUNE condition propre -> l'effet est
    actif tant qu'il existe. Son cycle de vie EST celui de Kell (l'effet disparait avec son porteur).

    `ApplyInternal(target)` (ordre du decompile, les DEUX appels vont a
    `IdunBattle.Operations.OperationProcessor$$AddUnitActiveAbilityModification`) :
        AddUnitActiveAbilityModification(target, AbilityVarOrConst(0x16), GetNumberConstant(0x16))
        AddUnitActiveAbilityModification(target, AbilityVarOrConst(0x10), GetNumberConstant(0x10))
    `RevertInternal(target)` : LES MEMES appels avec `-GetNumberConstant(...)`.

    i2 : « When Kell is in play, Lord Castellan Creed's active ability summons 1 extra Cadian Guardsman
    and has 3 hexes range instead of 2. » -> la CONSOMMATION est asymetrique et vit cote
    SupremeCommander (nrOfSummons ADDITIF, range OVERRIDE si non nul), pas ici : cet effet ne fait
    qu'ECRIRE `+3` et `+1` dans le registre.

    GROUND TRUTH LIVE (session 78, runner MC1_67) : Kell apparait en portant `ListenUpMaggotsEffect`
    et le cast SupremeCommander de Creed spawne **3** gardes au lieu de 2."""

    def ability_modifications(self) -> list:
        """Les DEUX `AddUnitActiveAbilityModification` de `ApplyInternal`, dans l'ORDRE du decompile.
        Les magnitudes sont les `GetNumberConstant` de la config de `ListenUpMaggots` (CONSTANTES, hors
        niveau : `range=3`, `nrOfSummons=1`) — lues de gameconfig, jamais codees en dur."""
        consts = (GC.ability(LISTEN_UP_MAGGOTS_ABILITY) or {}).get("constants") or {}
        return [(LUM_CONST_RANGE, int(consts.get("range") or 0)),
                (LUM_CONST_NR_OF_SUMMONS, int(consts.get("nrOfSummons") or 0))]

    def ability_modifications_target_selector(self):
        """`IdunBattle.Entities.Effects.Loki.ListenUpMaggotsEffect$$CreateTargetSelector` =
        `Parent(Self@0x148)`. Le port n'expose pas de noeud `Self`/`Owner` unit-domain : la couche
        runner monte le `DslContext` d'application avec `caster` = le PORTEUR de l'effet (Kell), donc
        `Caster()` EST ici le `Self@0x148` natif (meme convention que les triggers portes, ou
        Owner == Caster)."""
        return Parent(Caster())
