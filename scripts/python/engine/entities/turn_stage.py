"""`TurnStage` -- les CINQ etages d'un tour, et la fonction qui les enchaine.

Mirror 1:1 d'`IdunBattle.Entities.Enum.TurnStage`. C'est le 1er argument de
`Core.Services.OperationProcessor$$ContinueTurnPhase`, et la valeur que
`IdunBattle.Entities.Components.TurnComponent$$GetNextTurnStage` fait avancer d'un cran a
chaque tour de la boucle d'`IdunBattle.Operations.ContinueTurnPhaseOperation$$Execute`.

⚠ CE N'EST NI UN `GroupType` NI UN `PhaseType`, ET LES TROIS SE RECOUVRENT EN ORDINAL. Le `3`
qu'`IdunBattle.Operations.StartMatchOperation$$Execute` passe a `ContinueTurnPhase` est
`TurnStage.Start` ; le meme `3` est `GroupType.System_GameSetup` et
`IdunBattle.Core.PhaseType.<le 4e membre>`. C'est le NOM qui tranche, jamais l'ordinal --
quatrieme occurrence du meme piege sur ce dossier (`case-477r18r5` § 1, `case-477r19` § 1,
`case-477r20` § 1). Les cinq membres sont re-derivables :
`data/symbols/<CURRENT>/frida/enums.tsv`, ligne `IdunBattle.Entities.Enum.TurnStage`.
"""
from __future__ import annotations

from enum import IntEnum
from typing import List


class TurnStage(IntEnum):
    """`IdunBattle.Entities.Enum.TurnStage` -- VERBATIM du build (5 valeurs)."""

    Change = 0
    Prepare = 1
    Draft = 2
    Start = 3
    End = 4


def next_value_or_first(stage: int) -> TurnStage:
    """`Idun.Shared.Extensions.EnumExt$$NextValueOrFirst<TurnStage>`, lu verbatim :

        var values = Enum.GetValues(typeof(T));
        var i = Array.IndexOf(values, value);
        return (T)values.GetValue((i + 1) % values.Length);

    ⚠ L'AVANCE SE FAIT PAR INDICE DANS LA LISTE DES VALEURS, PAS PAR `+ 1` SUR L'ORDINAL. Les
    deux coincident sur `TurnStage` (0..4 contigus, aucun alias) mais pas en general -- le port
    mirror la sematique du generique, pas la coincidence de cet enum-la.

    ⚠ LE `OrFirst` DU NOM EST LE CAS `IndexOf == -1` : une valeur absente de l'enum donne
    `(-1 + 1) % len == 0`, donc le PREMIER membre. C'est lu, pas suppose -- `System.Array$$IndexOf`
    rend `-1` et le decompile ne teste pas ce retour."""
    valeurs: List[TurnStage] = list(TurnStage)
    indice = -1
    for k, valeur in enumerate(valeurs):
        if int(valeur) == int(stage):
            indice = k
            break
    return valeurs[(indice + 1) % len(valeurs)]
