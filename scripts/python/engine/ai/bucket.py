"""Bucket — sélection d'action native (namespace `IdunBattle.AI`, cf. playbook/architecture.md §2.3).

Mirror 1:1 de la classe `Bucket` du décideur natif (VAs, build gqfc5mff6c) :

  - `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` : garde comme `default` l'action de plus haute utilité
    (`op_GreaterThan` **STRICT** -> à égalité, le PREMIER inséré est conservé).
  - `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddActionToBucket` : range aussi l'action dans un sous-bucket par catégorie
    (SortedList, SANS seuil) -> arbre de fallback.
  - `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$ChooseAction` : `feasible(default) ? default : ChooseActionFromBuckets(children)`.
  - `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$ChooseActionFromBuckets` : itère la SortedList par clé, 1re action FAISABLE (récursif).
  - `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$Merge` : `AddAction(dest, src.default)` + fusion récursive de l'arbre.
  - gate `FUN_18004cc80` : `action != null && (minUtilityDifference absent OU U >= minUtilityDifference)`.

Nos générateurs n'émettent que des candidats LÉGAUX (le gate de faisabilité/légalité est appliqué en
amont, à l'énumération des cibles/tuiles) -> `ChooseAction` = renvoyer le `default` (l'argmax). Le
sous-arbre par catégorie (`AddActionToBucket`/`ChooseActionFromBuckets`) n'a d'effet que lorsque
l'argmax est ILLÉGAL (fallback) ; non exercé tant que les candidats sont pré-filtrés.

La CLÉ de comparaison est un tuple fourni par l'appelant (le générateur) : `(utilité, …tie-breaks)`.
Le natif compare l'utilité pure et départage par ordre d'insertion ; nos générateurs peuvent encoder
des tie-breaks additionnels dans la clé (ex. « normale d'abord », id de cible) — c'est là que vit la
policy de tie-break, PAS dans le Bucket. Remplace `engine/select.py` (Candidate/choose_action).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Action:
    """Une action scorée insérée dans un Bucket (= `IAction` + son utilité côté natif).

    `key`     = clé de comparaison de l'argmax (tuple, comparé STRICT `>`). Typiquement `(utility,)`
                ou `(utility, tie_break…)`.
    `payload` = la décision normalisée consommée par le harnais : `{kind, target, ability, to, util}`.
    `feasible`= légalité/faisabilité runtime (gate de `ChooseAction`). Défaut True (candidats
                pré-filtrés à l'énumération)."""
    key: tuple
    payload: dict
    feasible: bool = True


@dataclass
class Bucket:
    """`Bucket` natif : conserve l'argmax (`default`) via `AddAction`, le rend via `ChooseAction`."""

    _default: Action | None = field(default=None)

    def add_action(self, action: Action | None) -> None:
        """`IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` — remplace `default` SSI strictement meilleur (`>`),
        donc à clé égale le PREMIER inséré reste (tie-break natif = ordre d'insertion)."""
        if action is None:
            return
        if self._default is None or action.key > self._default.key:
            self._default = action

    def merge(self, other: "Bucket") -> None:
        """`IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$Merge` — fusionne le `default` d'un autre bucket (argmax combiné)."""
        if other is not None and other._default is not None:
            self.add_action(other._default)

    def choose_action(self) -> dict | None:
        """`IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$ChooseAction` — renvoie le payload de `default` s'il est faisable,
        sinon None (nos candidats étant pré-filtrés légaux, le sous-arbre par catégorie n'est
        pas exercé -> pas de recours à `ChooseActionFromBuckets`)."""
        if self._default is not None and self._default.feasible:
            return self._default.payload
        return None

    @property
    def default(self) -> Action | None:
        """L'action-argmax courante (ou None si le bucket est vide)."""
        return self._default

    def __bool__(self) -> bool:
        """Vrai SSI le bucket contient au moins une action (utile au tactic : générateur non-vide)."""
        return self._default is not None


def argmax_action(actions: list[Action]) -> dict | None:
    """Raccourci : construit un Bucket, y verse toutes les `actions`, renvoie `ChooseAction()`.
    Équivalent au `max(...)` par clé STRICT avec tie -> premier énuméré (= sémantique native)."""
    b = Bucket()
    for a in actions:
        b.add_action(a)
    return b.choose_action()
