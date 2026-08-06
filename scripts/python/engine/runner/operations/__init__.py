"""`engine.runner.operations` — mutateurs atomiques de l'ECS (~80 natifs).

Catalogue + VA : docs/rl/runner-engine.md §1.3. Un module/fichier par groupe
fonctionnel (movement, damage, effects, …), une classe `*Operation` par operation
native, méthode `execute` homonyme du natif `*Operation$$Execute` (VA citée).
Remplis tranche par tranche, validés contre le live.
"""
from __future__ import annotations


__all__ = []
