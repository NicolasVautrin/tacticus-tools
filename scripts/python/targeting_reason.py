#!/usr/bin/env python
"""Decodage du payload `abilityReason` -- LE point ou un refus NATIF devient un code.

POURQUOI CE MODULE EXISTE (#444)
--------------------------------
Le hook `frida/hooks/features/ai-step/rpc-targeting.ts` (`decodeRule`) ne sait extraire le FLAG que
d'un `IdunBattle.Core.Services.GenericBrokenTargetingRule` (dont le champ `Type` est a `obj+0x10`).
Pour toute AUTRE classe de regle rompue il rend :

    { ruleClass: "<nom de classe>", hex: "0x0", reasons: [] }

Or il EXISTE une autre classe, et une seule : `IdunBattle.Core.Services.ObscuredTerrainBrokenTargetingRule`
-- celle que `TargetingQuery$$GetInvalidTargetReason` boxe quand la LIGNE DE VUE est coupee. Son
`get_Type` rend le litteral `0x1000000`, soit `TargetingRule.TargetIsUnobscured`.

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
# de regle rompue autre que la generique. Recense au decompile sur `rnca9r7q6c` : `get_Type` n'a
# qu'UN seul porteur non generique, `ObscuredTerrainBrokenTargetingRule`, qui rend `0x1000000`.
RULE_CLASS_CODES = {
    "NoBrokenTargetingRule": 0,
    "ObscuredTerrainBrokenTargetingRule": 0x1000000,      # = TargetingRule.TargetIsUnobscured
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
