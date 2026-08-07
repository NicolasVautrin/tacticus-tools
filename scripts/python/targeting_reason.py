#!/usr/bin/env python
"""Decodage du payload `abilityReason` -- LE point ou un refus NATIF devient un code.

POURQUOI CE MODULE EXISTE (#444)
--------------------------------
Le hook `frida/hooks/features/ai-step/rpc-targeting.ts` (`decodeRule`) ne sait extraire le FLAG que
d'un `IdunBattle.Core.Services.GenericBrokenTargetingRule` (dont le champ `Type` est a `obj+0x10`).
Pour toute AUTRE classe de regle rompue il rend :

    { ruleClass: "<nom de classe>", hex: "0x0", reasons: [] }

Or il EXISTE deux autres classes, et #287-r10 a mesure la seconde :

  * `IdunBattle.Core.Services.ObscuredTerrainBrokenTargetingRule` -- celle que
    `TargetingQuery$$GetInvalidTargetReason` boxe quand la LIGNE DE VUE est coupee. Son `get_Type`
    rend le litteral `0x1000000`, soit `TargetingRule.TargetIsUnobscured`.
  * `IdunBattle.Core.Services.InFogOfWarBrokenTargetingRule` -- boxee par le TOUT PREMIER etage de
    la MEME fonction, avant le moindre test de masque : `foreach (tile in GetTiles(cible))
    if (tile.<TileComponent>.IsInFogOfWar) return <box InFogOfWarBrokenTargetingRule>`. Son
    `get_Type` rend **1**.

⚠ POURQUOI LA SECONDE MANQUAIT, ET C'EST LA FAUTE QUE `CLAUDE.md` NOMME : la ligne « `get_Type`
n'a qu'UN seul porteur non generique » a ete tiree de l'ABSENCE de
`InFogOfWarBrokenTargetingRule$$get_Type` dans les tables de symboles. IL2CPP **DEDUPLIQUE les
corps triviaux** : ce `return 1` est publie sous le nom `AK.Wwise.AuxBus$$get_WwiseObjectType`, et
le `return 0` de `NoBrokenTargetingRule$$get_Type` sous
`Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`. L'absence d'un symbole ne prouve rien.
Ce que la valeur `1` vaut est etabli par les `ToString` du groupe, qui boxent tous EXACTEMENT le
`Type` de leur classe (No -> `0` ; Generic -> le champ ; ObscuredTerrain -> `0x1000000`, valeur
confirmee par son `get_Type` NOMME ; InFogOfWar -> `1`).

⚠ `1` EST DONC REUTILISE A TROIS RANGS, et le `hex` seul ne les separe PAS : `ValidRequest` du
court-circuit amont d'`AttackQuery` (a lire sur `casterReason`), le litteral `1` que la branche
`TargetIsTile` rend pour une tuile non marchable, et ce `Type` de la regle brouillard. Le
discriminant qui les separe est la `ruleClass`, que le RPC publie deja. `GetInvalidCasterReason`,
lui, n'a AUCUNE branche brouillard (LU : il ne boxe que `Generic` et `No`) -- un `casterReason == 1`
reste donc sans ambiguite le court-circuit amont, et `oracle_targeting.oracle_court_circuite` n'est
pas concerne.

⚠ CONSEQUENCE, ET ELLE EST SILENCIEUSE : un lecteur qui fait `int(payload["hex"], 16)` lit **0** sur
un refus de ligne de vue, c'est-a-dire « CIBLE VALIDE ». Tant que le port ne portait pas la regle,
les deux cotes rendaient `0` et l'accord etait PARFAIT -- et FAUX des deux cotes (cf. la note
`feedback_agreement_worthless_on_shared_stale_input`). Depuis que le port rend `TargetIsUnobscured`,
le meme lecteur voit un DESACCORD la ou les deux cotes sont d'accord.

`native_target_reason` est le decodeur a utiliser. Il lit le `hex` quand il porte l'information et
retombe sur la CLASSE sinon, ce qui le rend correct AVANT comme APRES le correctif du hook (qui,
lui, demande une fenetre de reinject).

Le tri-etat rendu est deliberement le meme que celui des probes existants :
    int   -> le code du refus (0 = cible valide) ;
    None  -> le canal n'a pas rendu de verdict lisible (payload absent, classe inconnue).
"""
from __future__ import annotations

from typing import Optional

# `IdunBattle.Core.Services.<X>BrokenTargetingRule$$get_Type` -- le litteral rendu par chaque classe
# de regle rompue autre que la generique. Recense au decompile sur `rnca9r7q6c` par les CLASSES
# (`frida/classes.tsv`), jamais par la presence d'un symbole `get_Type` : trois classes non
# generiques existent, et une seule des trois a son `get_Type` nomme (cf. l'en-tete de module).
RULE_CLASS_CODES = {
    "NoBrokenTargetingRule": 0,
    "ObscuredTerrainBrokenTargetingRule": 0x1000000,      # = TargetingRule.TargetIsUnobscured
    # MESURE LIVE #287-r10 (board `C6_09`, 34 tuiles en brouillard sur 63) : `abilityReason` sur une
    # tuile en brouillard rend `ruleClass: "InFogOfWarBrokenTargetingRule", hex: "0x0", reasons: []`
    # avec `casterReason == 0` -- donc un REFUS de la cascade de ciblage, lu « cible valide » par
    # tout `int(hex, 16)`. Le code VRAI est `1` (cf. en-tete). La `ruleClass` reste le seul canal
    # qui le distingue des deux autres emplois de `1`.
    "InFogOfWarBrokenTargetingRule": 1,                   # = TargetingRule.ValidRequest (ordinal)
}


def native_target_reason(payload: Optional[dict]) -> Optional[int]:
    """Code de refus NATIF porte par un bloc `targetReason` / `casterReason` d'`abilityReason`.

    ORDRE DE LECTURE, et il compte :
      1. `hex` non nul -> c'est le flag decode par le hook (`GenericBrokenTargetingRule`) ;
      2. sinon la CLASSE -> `RULE_CLASS_CODES` (c'est la seule voie pour la ligne de vue tant que le
         hook publie `hex: "0x0"` pour toute classe non generique) ;
      3. sinon `None` -- classe inconnue : on ne fabrique pas un verdict.

    Un `hex` a `0x0` avec `ruleClass == "GenericBrokenTargetingRule"` ne se produit pas (le natif ne
    boxe une generique que sur un flag non nul), mais s'il se produisait la classe le rabattrait sur
    `None` plutot que sur un faux `0`."""
    if not isinstance(payload, dict):
        return None
    h = payload.get("hex")
    if isinstance(h, str) and h:
        try:
            v = int(h, 16)
        except ValueError:
            v = None
        if v:
            return v
    cls = payload.get("ruleClass")
    if cls in RULE_CLASS_CODES:
        return RULE_CLASS_CODES[cls]
    if cls == "GenericBrokenTargetingRule":
        return None
    return None
