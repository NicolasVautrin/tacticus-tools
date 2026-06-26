"""Moteur playbook — réimplémentation Python de l'IA native de Tacticus.

Vit À CÔTÉ de l'oracle (driver pair), pas un remplacement. cf. docs/rl/playbook-engine.md.

Sous-modules :
  weights  — charge BattleConfiguration.Utilities (poids nommés, §1.5)
  select   — ChooseAction = argmax-utilité-parmi-légales (§1.4)
  playbooks— registre abilityType -> Playbook + base (§1.3) [Phase 1+]
  state    — adaptateur d'état via les RPCs (decisionView/...) [live]
  engine   — API driver decide_unit/decide_turn [live]
"""
