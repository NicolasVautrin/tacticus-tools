"""Famille `AdjacentUnitPreferenceTriggeredAbilityPlaybook` — utilité de MOUVEMENT des abilities DÉCLENCHÉES.

Native (ghidra gqfc5mff6c, case-36) : la feuille de tuile `TriggeredAbilitiesUtility(2)` (dispatcher,
`engine/utilities/tile.py`) itère les abilities DE L'UNITÉ QUI BOUGE (`case.unit@0x10` →
AbilitiesComponent), charge le playbook SINGLETON PAR TYPE d'ability (`PlaybookDatabase.LoadPlaybook
@1810dfd10` : cache dict@0x90 + factories dict@0x88, clef = ability type) et somme leurs
`ITriggeredAbilityPlaybook.CalculateMovementUtilityInSteps` (Fix64).

Corps commun `AdjacentUnitPreferenceTriggeredAbilityPlaybook.<CalculateMovementUtilityInStepsInternal>
d__1.MoveNext @18134eb30` :

    owner    = case.unit ; playerId = OwnerComponent.get_CurrentPlayerEntityId(owner)
    adjacent = IBattleQuery.<slot 0x81>(caseTile, playerId) MINUS self      (amis R1 de la tuile)
    n1       = Min(count(filtre vtbl+0x248), cap vtbl+0x228)
    val      = Σ_{i<n1} weightAdjacent(u_i, ctx)                            (vtbl+0x208)
    surround = IBattleQuery.<slot 0x7d>(caseTile, playerId, 0)              (amis R2)
    n2       = Min(count(filtre vtbl+0x258), cap vtbl+0x238)
    val     += Σ_{i<n2} weightSurrounding(u_i, ctx)                         (vtbl+0x218)
    yield Fix64.FromInt(val)

Les CONCRETS (~25 classes `IdunBattle.AI.Playbook.Loki.*Playbook`, base intermédiaire
`AdjacentToOwnerNonOwnerPlaybook<T>..ctor @1813824d0`) overrident `GetAdjacentFriendUtility` /
`GetAdjacentEnemyUtility` = LOOKUP CONFIG PLAT `Utilities.Default.TriggeredAbilities[<clé>]`, l'unité
passée est IGNORÉE — ex. `GuardianOrganismPlaybook.GetAdjacentFriendUtility @181166df0` invoque le
délégué de lookup avec la string `"GuardianOrganism_AdjacentFriend"` (=30 BC).

Caps (vtbl+0x228/0x238) : corps gshared non symbolisés dans le dump — jamais liants observés (max 3
amis adjacents, 909 s19) ; non répliqués tant qu'aucun cas ne les montre saturer. Poids surrounding :
défaut base = 0 (confirmé 909 : (4,2)=30 exactement alors que u87/u91 sont en ring-2 — s'ils
comptaient, le score dépasserait 30) ; seules les classes qui overrident (StandVigil & co, corps
propres) comptent.

Cas d'origine : `docs/rl/case-36-triggered-abilities-move.md` — 909 s4/s19, u89 tyranTyrantGuard
(passif GuardianOrganism 1181) : TrigAb = 30 × #amis-adjacents-à-la-tuile → 30/90 EXACTS vs L3.
"""
from __future__ import annotations

import hexgeo

from ..entities.triggered_ability_type import TriggeredAbilityType


class AdjacentUnitPreferenceTriggeredAbilityPlaybook:
    """Base : Σ poids sur amis R1 (adjacents) + Σ poids sur amis R2 (surrounding) de la tuile candidate.
    `friend_positions` = positions ALLIÉES vivantes self-exclu (mirror du MINUS self natif — `ctx.fpos`)."""

    def get_adjacent_friend_utility(self, wt) -> float:      # vtbl+0x208 (défaut base : 0)
        return 0.0

    def get_surrounding_friend_utility(self, wt) -> float:   # vtbl+0x218 (défaut base : 0)
        return 0.0

    def calculate_movement_utility_in_steps(self, tile, friend_positions, wt) -> float:
        val = 0.0
        for p in friend_positions:
            d = hexgeo.distance(tile, p)
            if d == 1:
                val += self.get_adjacent_friend_utility(wt)
            elif d == 2:
                val += self.get_surrounding_friend_utility(wt)
        return val


class AdjacentToOwnerNonOwnerPlaybook(AdjacentUnitPreferenceTriggeredAbilityPlaybook):
    """Base intermédiaire des concrets (`..ctor @1813824d0`). Porte AUSSI la face NON-OWNER
    (`<CalculateMovementUtilityInSteps>d__2 @18134f250` : poids UNIQUE gaté « tuile adjacente au
    porteur ») consommée par la feuille TriggeredAbilitiesNonOwner(4) — NON portée (=0 observé 909 ;
    config séparée `Utilities.Default.TriggeredAbilitiesNonOwner`, 25 clés)."""


class GuardianOrganismPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`GuardianOrganismPlaybook` (`..ctor @181166e50` : ability 0x49d=1181 GuardianOrganism — passif
    Tyrant Guard). `GetAdjacentFriendUtility @181166df0` = TriggeredAbilities
    ["GuardianOrganism_AdjacentFriend"] (=30 BC), unité ignorée."""

    def get_adjacent_friend_utility(self, wt) -> float:
        return wt.sub("TriggeredAbilities", "GuardianOrganism_AdjacentFriend")


# `PlaybookDatabase.LoadPlaybook @1810dfd10` : singleton par TYPE d'ability. Seuls les types dont le
# playbook CONTRIBUE au mouvement sont enregistrés — les autres (playbooks de cast Comparable/
# NonComparable ; base `TriggeredAbilityPlaybook.CalculateMovementUtilityInSteps @18150f630`) yield 0
# nativement : absence du registre == 0, même dégradation. Étendre en portant les autres concrets
# `GetAdjacent{Friend,Enemy}Utility` (~25, mêmes 3 lignes chacun) quand un case les montre décisifs.
TRIGGERED_MOVE_PLAYBOOKS: dict[int, AdjacentUnitPreferenceTriggeredAbilityPlaybook] = {
    int(TriggeredAbilityType.GuardianOrganism): GuardianOrganismPlaybook(),
}


def load_playbook(ability_id: int) -> AdjacentUnitPreferenceTriggeredAbilityPlaybook | None:
    """Mirror `PlaybookDatabase.LoadPlaybook` (movement-relevant uniquement). None → le dispatcher skip
    (même chemin que le `if playbook == null: continue` natif)."""
    return TRIGGERED_MOVE_PLAYBOOKS.get(int(ability_id))
