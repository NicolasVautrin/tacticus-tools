"""Famille `AdjacentUnitPreferenceTriggeredAbilityPlaybook` — utilité de MOUVEMENT des abilities DÉCLENCHÉES.

Native (ghidra gqfc5mff6c, case-36) : la feuille de tuile `TriggeredAbilitiesUtility(2)` (dispatcher,
`engine/utilities/tile.py`) itère les abilities DE L'UNITÉ QUI BOUGE (`case.unit@0x10` →
AbilitiesComponent), charge le playbook SINGLETON PAR TYPE d'ability (`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook` : cache dict@0x90 + factories dict@0x88, clef = ability type) et somme leurs
`ITriggeredAbilityPlaybook.CalculateMovementUtilityInSteps` (Fix64).

Corps commun `AdjacentUnitPreferenceTriggeredAbilityPlaybook.<CalculateMovementUtilityInStepsInternal>
IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext` :

    owner    = case.unit ; playerId = OwnerComponent.get_CurrentPlayerEntityId(owner)
    adjacent = IBattleQuery.<slot 0x81>(caseTile, playerId) MINUS self      (amis R1 de la tuile)
    n1       = Min(count(filtre vtbl+0x248), cap vtbl+0x228)
    val      = Σ_{i<n1} weightAdjacent(u_i, ctx)                            (vtbl+0x208)
    surround = IBattleQuery.<slot 0x7d>(caseTile, playerId, 0)              (amis R2)
    n2       = Min(count(filtre vtbl+0x258), cap vtbl+0x238)
    val     += Σ_{i<n2} weightSurrounding(u_i, ctx)                         (vtbl+0x218)
    yield Fix64.FromInt(val)

Les CONCRETS (~25 classes `IdunBattle.AI.Playbook.Loki.*Playbook`, base intermédiaire
`AdjacentToOwnerNonOwnerPlaybook<T>..IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor`) overrident `GetAdjacentFriendUtility` /
`GetAdjacentEnemyUtility` = LOOKUP CONFIG PLAT `Utilities.Default.TriggeredAbilities[<clé>]`, l'unité
passée est IGNORÉE — ex. `IdunBattle.AI.Playbook.Loki.GuardianOrganismPlaybook$$GetAdjacentFriendUtility` invoque le
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
    """Base : Σ poids sur AMIS R1 (adjacents) + Σ poids sur ENNEMIS R1 (adjacents) de la tuile candidate.

    Corps natif `<CalculateMovementUtilityInStepsInternal>IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext` (#57i) : DEUX branches,
    toutes deux à DISTANCE 1 de la tuile candidate (PAS adjacent+surrounding — verdict corrigé par le
    comptage d'args de la query interface : GetAdjacentFriends=this+2, GetAdjacentEnemies=this+3,
    GetSurrounding*=this+4) :
      B1 = IBattleQuery.GetAdjacentFriends(caseTile, playerId) MINUS self  (slot 0x81, this+2 args)
           filtre vtbl+0x248 (défaut identité) ; cap vtbl+0x228 (jamais liante <=6 voisins) ;
           Σ get_adjacent_friend_utility (vtbl+0x208)
      B2 = IBattleQuery.GetAdjacentEnemies(caseTile, playerId, false)      (slot 0x7d, this+3 args)
           filtre vtbl+0x258 (défaut identité) ; cap vtbl+0x238 ;
           Σ get_adjacent_enemy_utility (vtbl+0x218)
      yield Fix64.FromInt(val)
    Les poids (vtbl+0x208/0x218) sont des LOOKUP CONFIG PLATS `Utilities.Default.TriggeredAbilities[<clé>]`
    (l'unité est IGNORÉE par `GetAdjacent{Friend,Enemy}Utility` — cf. IdunBattle.AI.Playbook.Loki.MartialApotheosisPlaybook$$GetAdjacentEnemyUtility/IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$GetAdjacentFriendUtility). L'ancien
    modèle (amis R1+R2) rendait EXACT pour GuardianOrganism/RitesOfBattle (poids surrounding + enemy = 0)
    mais RATAIT la branche ennemis — d'où MartialApotheosis(1045) muet (#57i : miss S14 12345).

    Signature du dispatcher (#32) : `calculate_movement_utility_in_steps(tile, ctx, wt)` où `ctx` = le dict
    par-décision `tile_leaf_ctx` (mirror du natif qui passe le CASE entier — chaque famille y lit ses clés :
    ici `friend_units`/`enemy_units` = {pos,traits} vivants self-exclu ; `FuryOfTheAncientsPlaybook` lit
    `enemies`/`scene`/…)."""

    def get_adjacent_friend_utility(self, wt) -> float:      # vtbl+0x208 (défaut base : 0)
        return 0.0

    def get_adjacent_enemy_utility(self, wt) -> float:       # vtbl+0x218 (défaut base : 0)
        return 0.0

    def filter_adjacent_friend(self, unit: dict, ctx: dict) -> bool:   # vtbl+0x248 (défaut : identité)
        return True

    def filter_adjacent_enemy(self, unit: dict, ctx: dict) -> bool:    # vtbl+0x258 (défaut : identité)
        return True

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        ctx = ctx or {}
        val = 0.0
        wf = self.get_adjacent_friend_utility(wt)
        if wf:
            for u in (ctx.get("friend_units") or ()):
                if hexgeo.distance(tile, u["pos"]) == 1 and self.filter_adjacent_friend(u, ctx):
                    val += wf
        we = self.get_adjacent_enemy_utility(wt)
        if we:
            for u in (ctx.get("enemy_units") or ()):
                if hexgeo.distance(tile, u["pos"]) == 1 and self.filter_adjacent_enemy(u, ctx):
                    val += we
        return val


class AdjacentToOwnerNonOwnerPlaybook(AdjacentUnitPreferenceTriggeredAbilityPlaybook):
    """Base intermédiaire des concrets (`..IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor`). Porte AUSSI la face NON-OWNER
    (`<CalculateMovementUtilityInSteps>d__2 IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext` : poids UNIQUE gaté « tuile adjacente au
    porteur ») consommée par la feuille TriggeredAbilitiesNonOwner(4) — NON portée (=0 observé 909 ;
    config séparée `Utilities.Default.TriggeredAbilitiesNonOwner`, 25 clés)."""


class GuardianOrganismPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`GuardianOrganismPlaybook` (`..IdunBattle.AI.Playbook.Loki.GuardianOrganismPlaybook$$.ctor` : ability 0x49d=1181 GuardianOrganism — passif
    Tyrant Guard). `IdunBattle.AI.Playbook.Loki.GuardianOrganismPlaybook$$GetAdjacentFriendUtility` = TriggeredAbilities
    ["GuardianOrganism_AdjacentFriend"] (=30 BC), unité ignorée."""

    def get_adjacent_friend_utility(self, wt) -> float:
        return wt.sub("TriggeredAbilities", "GuardianOrganism_AdjacentFriend")


class RitesOfBattlePlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`RitesOfBattlePlaybook` (`..IdunBattle.AI.Playbook.Loki.RitesOfBattlePlaybook$$.ctor` : ability 0x3f6=1014 RitesOfBattle — passif aura
    ultraCalgar). `IdunBattle.AI.Playbook.Loki.RitesOfBattlePlaybook$$GetAdjacentFriendUtility` = TriggeredAbilities
    ["RITESOFBATTLE_AdjacentFriend"] (=10 BC), unité ignorée. Case-49 résiduel (31337) : ce terme
    manquant faussait les Tile7 de u87 → miss move s3 ((2,2) vs (3,2)) ET miss CIBLE s14
    (l'argmax attaque u_full = paire + Tile7 flippait vers 79@(4,3) au lieu de 81@(3,4))."""

    def get_adjacent_friend_utility(self, wt) -> float:
        return wt.sub("TriggeredAbilities", "RITESOFBATTLE_AdjacentFriend")


# `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook` : singleton par TYPE d'ability. Seuls les types dont le
# playbook CONTRIBUE au mouvement sont enregistrés — les autres (playbooks de cast Comparable/
# NonComparable ; base `IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateMovementUtilityInSteps`) yield 0
# nativement : absence du registre == 0, même dégradation. Étendre en portant les autres concrets
# `GetAdjacent{Friend,Enemy}Utility` (~25, mêmes 3 lignes chacun) quand un case les montre décisifs.
# Le registre accueille TOUTE famille de playbook move-relevant (protocole = la méthode
# `calculate_movement_utility_in_steps(tile, ctx, wt)`) — pas seulement AdjacentUnitPreference :
# `FuryOfTheAncientsPlaybook` (#32) est de la famille `TriggeredAbilityPlaybook<T>` (ennemis
# adjacents + prédiction de dégât), module `fury_of_the_ancients.py`.
class MartialApotheosisPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`MartialApotheosisPlaybook` (`..IdunBattle.AI.Playbook.Loki.MartialApotheosisPlaybook$$.ctor` : ability 0x415=1045 MartialApotheosis — passif
    necroOverlord). `IdunBattle.AI.Playbook.Loki.MartialApotheosisPlaybook$$GetAdjacentEnemyUtility` = TriggeredAbilities["MARTIALAPOTHEOSIS_AdjacentEnemy"]
    (=15 BC), unité ignorée ; branche ENNEMIS R1 (B2). Pas de filtre custom (défaut identité). #57i :
    12345 s14, u87 préfère (3,5) [3 ennemis adjacents -> +45] a (4,3) [0] -> flip cible 69->t77."""

    def get_adjacent_enemy_utility(self, wt) -> float:
        return wt.sub("TriggeredAbilities", "MARTIALAPOTHEOSIS_AdjacentEnemy")


class FabricatorClawArrayPlaybook(AdjacentToOwnerNonOwnerPlaybook):
    """`FabricatorClawArrayPlaybook` (`..IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$.ctor` : ability 0x3ee=1006 FabricatorClawArray — passif
    necroSpyder). `IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$GetAdjacentFriendUtility` = TriggeredAbilities["FABRICATORCLAWARRAY_AdjacentFriend"]
    (=30 BC), unité ignorée ; branche AMIS R1 (B1). `IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$FilterAdjacentFriends` : garde les amis
    ayant le trait Mechanical (UnitTrait 5). #57i : 2468 s16, u79 préfère (3,4) [1 ami mécanique adjacent
    admecRuststalker -> +30] a (4,2) [0] -> flip cible 69->t89."""

    def get_adjacent_friend_utility(self, wt) -> float:
        return wt.sub("TriggeredAbilities", "FABRICATORCLAWARRAY_AdjacentFriend")

    def filter_adjacent_friend(self, unit: dict, ctx: dict) -> bool:
        return "Mechanical" in (unit.get("traits") or ())


from .fury_of_the_ancients import FuryOfTheAncientsPlaybook   # noqa: E402  (après les bases)

TRIGGERED_MOVE_PLAYBOOKS: dict = {
    int(TriggeredAbilityType.GuardianOrganism): GuardianOrganismPlaybook(),
    int(TriggeredAbilityType.RitesOfBattle): RitesOfBattlePlaybook(),
    int(TriggeredAbilityType.MartialApotheosis): MartialApotheosisPlaybook(),   # 1045 (#57i, branche ennemis)
    int(TriggeredAbilityType.FabricatorClawArray): FabricatorClawArrayPlaybook(),  # 1006 (#57i, amis mecaniques)
    int(TriggeredAbilityType.FuryOfTheAncients): FuryOfTheAncientsPlaybook(),   # 1247 (#32)
}


def load_playbook(ability_id: int):
    """Mirror `PlaybookDatabase.LoadPlaybook` (movement-relevant uniquement). None → le dispatcher skip
    (même chemin que le `if playbook == null: continue` natif)."""
    return TRIGGERED_MOVE_PLAYBOOKS.get(int(ability_id))
