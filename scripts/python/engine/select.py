"""Sélection d'action = `Bucket.ChooseAction` (spine §1.4).

Le jeu range les candidats dans une SortedList par priorité (= utilité) et retourne la
PREMIÈRE action VALIDE (gate de faisabilité/légalité). Équivalent décision :
**argmax(utilité) parmi les candidats LÉGAUX**. Le bucket-tree imbriqué est un détail
d'implémentation sans effet sur l'argmax. cf. docs/rl/playbook-engine.md §1.4.

Pure logique → testable OFFLINE.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Candidate:
    """Une action candidate scorée par une playbook."""
    unit_id: int
    kind: str                       # "ability" | "normal" | "move" | "finish"
    utility: float
    ability_id: int | None = None
    target_id: int | None = None    # cible entité
    to: tuple | None = None         # (col,row) — tuile de spawn/bombard/move
    legal: bool = True              # passe le gate de faisabilité (légalité runtime)
    why: str = ""                   # provenance (playbook + termes) pour la traçabilité

    def as_action(self) -> dict:
        """Forme `applyAction` (côté hook)."""
        if self.kind == "move":
            return {"kind": "move", "unitId": self.unit_id,
                    "to": {"col": self.to[0], "row": self.to[1]}}
        if self.kind == "finish":
            return {"kind": "finish", "unitId": self.unit_id}
        a = {"kind": "ability", "casterId": self.unit_id, "abilityType": self.ability_id}
        if self.target_id is not None:
            a["targetId"] = self.target_id
        elif self.to is not None:
            a["to"] = {"col": self.to[0], "row": self.to[1]}
        return a


def choose_action(cands: list[Candidate]) -> Candidate | None:
    """argmax-utilité parmi les LÉGAUX. None si aucun candidat légal (= l'IA passe/finish).
    Tie-break STABLE : à utilité égale, le premier inséré gagne (comme la SortedList du jeu
    qui conserve l'ordre d'insertion à clé égale)."""
    best: Candidate | None = None
    for c in cands:
        if not c.legal:
            continue
        if best is None or c.utility > best.utility:   # strict > => tie-break = premier
            best = c
    return best
