"""`engine.ai` — spine décisionnel natif (namespace `IdunBattle.AI`, port fidèle).

Réimplémente la chaîne de décision par-unité du jeu (cf. docs/rl/playbook/architecture.md §2) :

    DefaultAiUnitTactic  (tactic.py)          — liste ordonnée de générateurs, PREMIÈRE action non-null
      -> ActiveAbilityActionGenerator          — par tier : sweep (tuiles x abilities) -> Bucket
         MovementActionGenerator               — fallback (approche) EN DERNIER
      -> Bucket (bucket.py)                     — argmax d'action (AddAction/ChooseAction/Merge)
    AiDecisionContext    (context.py)          — l'état de la décision, alimenté par RPC (la COUTURE)

Les playbooks par-ability (Comparable/NonComparable) vivent dans `engine.playbook` (namespace
`IdunBattle.AI.Playbook`) et sont invoqués par les générateurs.
"""
from __future__ import annotations


__all__ = []
