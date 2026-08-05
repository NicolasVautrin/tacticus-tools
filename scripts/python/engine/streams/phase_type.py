"""`PhaseType` -- le vocabulaire des PHASES du processeur de messages natif.

Mirror 1:1 d'`IdunBattle.Core.PhaseType`, le 1er argument d'
`IdunBattle.Messages.InputMessageProcessor$$RunPhase(type, action, isInternalPhase,
isManualTurnEnd)`.

POURQUOI CE FICHIER EXISTE : LE PIEGE EST L'ORDINAL NU
------------------------------------------------------
Une phase s'ecrivait `RunPhase(0xd)` au lieu de `RunPhase(PhaseType.ProcessRemovals /*0xd*/)`
-- un entier nu, que RIEN ne rattache a un nom. Trois
crans du deroule #477 l'ont pris pour un `IdunBattle.Streams.GroupType` (`case-477r18r5` § 1,
`case-477r19` § 1, `case-477r20`), et `revive.py` / `damage.py` l'ont attribue a
`Core.Services.OperationProcessor$$ReviveUnit` pendant trois tranches. Les deux enums ont des
ordinaux qui SE RECOUVRENT (`GroupType.User_PlaceUnit` vaut aussi `13`), donc l'ordinal ne
discrimine pas : **le NOM tranche, et lui seul**. C'est la regle du depot (« un entier qui
DESIGNE quelque chose passe par un ENUM ») appliquee a l'axe des phases.

CE QUE `RunPhase(PhaseType.ProcessRemovals)` DRAINE -- ET CE QU'IL NE DRAINE PAS
--------------------------------------------------------------------------------
`IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` lance DEUX phases :

    if (deaths.Count > 0) RunPhase(PhaseType.ProcessDeaths /*0xc*/,   <VerifyDeaths>b__0,      isInternalPhase: true, false);
    ...                   RunPhase(PhaseType.ProcessRemovals /*0xd*/, <VerifyRemovedUnits>b__0, isInternalPhase: true, false);

La seconde est le corps INLINE d'`IdunBattle.Messages.InputMessageProcessor$$VerifyRemovedUnits`
(meme drapeau d'init, meme `Il2CppClass*` de `<>c__DisplayClass50_0`, meme pointeur de lambda --
mesure #477-r19). Sa lambda vide la file des RETRAITS ; elle ne touche a aucun revive.

⚠ **`ReviveUnit` N'A AUCUNE PHASE, et c'est un RESULTAT MESURE, pas une absence de preuve**
(#477-r24). `Core.Services.OperationProcessor$$ReviveUnit(killed)` n'a AUCUNE xref CODE dans
le binaire -- ses deux seules xrefs sont des entrees DATA de tables de methodes. Son unique site
d'invocation est `IdunBattle.Operations.KillUnitOperation$$Execute`, dans la branche `else` de
la garde `pendingRevive.HasValue` (`UnitComponent + 0xa8`) :

    if (!unitComponent.PendingRevive.HasValue) { ...toute la suite de la mort... }
    else                                       { processor.ReviveUnit(killed); }
    // puis, DANS LES DEUX BRANCHES : purge des 9 qwords +0xa8 .. +0xe8

Le revive s'execute donc SYNCHRONIQUEMENT dans le kill, c'est-a-dire dans la phase de l'action
qui a provoque ce kill -- `PhaseType.ProcessDeaths` quand le kill vient du drain de
`VerifyDeaths`, mais aussi bien `PhaseType.Damage` ou `PhaseType.ActiveAbility` quand
`KillUnit` est appele en ligne. **Aucun `PhaseType` ne nomme un revive**, et c'est verifiable
d'un coup d'oeil sur la table ci-dessous.
"""
from __future__ import annotations

from enum import IntEnum


class PhaseType(IntEnum):
    """`IdunBattle.Core.PhaseType` -- VERBATIM du build (17 valeurs).

    Re-derivable : `data/symbols/<CURRENT>/frida/enums.tsv`, ligne `IdunBattle.Core.PhaseType`.
    C'est le SEUL `PhaseType` du dump d'enums -- contrairement a `Corner` (six homonymes) ou
    `Edge` (deux), le nom court suffit ici ; l'appariement du registre `probe_313` reste
    neanmoins fait sur le nom PLEIN.
    """

    StartBattle = 0
    StartTurn = 1
    EndTurn = 2
    FinishUnitTurn = 3
    AddUnit = 4
    MoveUnit = 5
    ActiveAbility = 6
    Damage = 7
    Surrender = 8
    PickUnit = 9
    RerollDraftOption = 10
    SkipToNextWave = 11
    ProcessDeaths = 12
    ProcessRemovals = 13
    ProcessDamageEvents = 14
    ProcessPendingTriggeredAbilities = 15
    Cheat = 16
