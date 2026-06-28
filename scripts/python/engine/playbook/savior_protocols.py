"""SaviorProtocolsPlaybook — playbook représentatif (RE docs/rl/playbook-engine.md §14.4).

Base native : `TriggeredAbilityPlaybook<SaviorProtocolsAbility>`, ability id **1120 (0x460)**.
Poids résolus OFFLINE (playbook_keys.py → stringliteral.json → Utilities.Default.TriggeredAbilities) :
  SAVIORPROTOCOLS_MarkedTarget      = 60   (attaque : cible porte l'effet marqueur 1122 / 0x462)
  SAVIORPROTOCOLS_AdjacentTauFriend = 20   (move : par candidat allié valide)
  SAVIORPROTOCOLS_AdjacentTauParent = 30   (move : bonus si le caster est le parent/owner du candidat)

DORMANT : lit un `case` (contrat ci-dessous), rend 0 si la metadata n'est pas plombée.

Contrat `case` :
  attack_utility :
    target_has_marker : bool   — la cible porte l'effet marqueur 1122 (RE : HasEffect(target, …, 0x462))
  movement_utility :
    valid_candidates : [ {is_owned_by_caster: bool} ]
        — alliés près de la tuile-caster passant TargetIsValidTrigger (AreFriends + HasFaction(9)
          + NOT casterHasAbility(1120) + target≠self) ; `is_owned_by_caster` = caster == GetParent(candidat).
"""
from __future__ import annotations

from ..weights import Weights
from .base import Playbook, register

# Ids RE'd (hex/déc) — pour le plumbing de la metadata.
ABILITY_ID = 0x460          # 1120
MARKER_EFFECT_ID = 0x462    # 1122
FACTION_GATE = 9            # T'au-style (HasFaction(9))


class SaviorProtocolsPlaybook(Playbook):
    ability_id = ABILITY_ID  # 1120

    def attack_utility(self, case: dict, wt: Weights) -> float:
        """Gate : la cible porte l'effet marqueur 1122 → +MarkedTarget. (1 yield natif)."""
        if not (case or {}).get("target_has_marker"):
            return 0.0
        return self.w(wt, "SAVIORPROTOCOLS_MarkedTarget")

    def movement_utility(self, case: dict, wt: Weights) -> float:
        """Σ sur les candidats alliés valides : +AdjacentTauFriend chacun, +AdjacentTauParent si owned."""
        cands = (case or {}).get("valid_candidates") or []
        if not cands:
            return 0.0
        w_friend = self.w(wt, "SAVIORPROTOCOLS_AdjacentTauFriend")
        w_parent = self.w(wt, "SAVIORPROTOCOLS_AdjacentTauParent")
        u = 0.0
        for c in cands:
            u += w_friend
            if c.get("is_owned_by_caster"):
                u += w_parent
        return u


register(SaviorProtocolsPlaybook())
