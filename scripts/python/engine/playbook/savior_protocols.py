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
from .base import BasePlaybook

# Ids RE'd (hex/déc) — pour le plumbing de la metadata.
ABILITY_ID = 0x460          # 1120
MARKER_EFFECT_ID = 0x462    # 1122
FACTION_GATE = 9            # T'au-style (HasFaction(9))


class SaviorProtocolsPlaybook(BasePlaybook):
    """DORMANT — référence RE d'un playbook bespoke à clés-strings (modèle `case`/GetUtilityValue).
    NON enregistré dans le registry de scoring (pas sur le chemin live ; le générateur retombe sur
    DefaultActiveAbilityPlaybook pour 1120). Conservé pour la doc des poids TriggeredAbilities."""
    ability_id = ABILITY_ID  # 1120
    cat = "TriggeredAbilities"

    def w(self, wt: Weights, key: str) -> float:
        """Poids BC `Utilities.Default.<cat>.<key>` (défaut 0 = GetUtilityValue natif)."""
        return wt.sub(self.cat, key)

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

# NON enregistré (dormant) : pas de register(...) — le générateur retombe sur DefaultActiveAbilityPlaybook
# pour l'ability 1120 si elle apparaît.
