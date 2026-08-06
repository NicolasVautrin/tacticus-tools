"""Moteur playbook — réimplémentation Python de l'IA native de Tacticus.

Vit À CÔTÉ de l'oracle (driver pair), pas un remplacement. cf. docs/rl/playbook/architecture.md.

Sous-modules :
  weights      — charge BattleConfiguration.Utilities (poids nommés, §1.5)
  ai           — spine décisionnel natif (IdunBattle.AI) : tactic / générateurs / bucket / context
  playbook     — namespace des playbooks par-ability (IdunBattle.AI.Playbook) : comparable/common
                 (attaques/soins) + noncomparable (summons/buffs/retraite)
  battle_query — primitives IBattleQuery (GetAdjacentEnemies/Friends + porte d'élévation)
  predict      — prédiction non-dégât (heal/repair/effet)
"""
