"""Famille `TriggeredAbilityNonOwnerPlaybook<T>` — utilite de MOUVEMENT que l'ability d'UNE AUTRE
unite exerce sur l'unite QUI BOUGE.

C'est la SECONDE face du moteur Playbook cote mouvement, et la symetrique exacte de la premiere :

  * feuille `TriggeredAbilities(2)` (`adjacent_unit_preference.py`) : on itere les abilities
    declenchees DU MOVER (`case.unit`), chaque playbook pese la tuile candidate. Poids dans
    `Utilities.Default.TriggeredAbilities`.
  * feuille `TriggeredAbilitiesNonOwner(4)` (CE module) : on itere les abilities declenchees des
    AUTRES unites, chaque playbook pese la tuile candidate DU MOVER du point de vue de SON porteur.
    Poids dans `Utilities.Default.TriggeredAbilitiesNonOwner` (categorie SEPAREE, 25 cles).

Chaine native (relue au decompile du build `rnca9r7q6c`) :

    IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CEvaluateMovementInStepsu003Ed__0$$MoveNext
        Fix64 total = 0;
        if (case.unit == null && case.parent == null) { yield 0; return; }
        foreach ((playbook, owner) in IterateAbilities(case))
            total += <somme des steps de> playbook.CalculateMovementUtilityInSteps(case, owner);
        yield total;

    IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CIterateAbilitiesu003Ed__3$$MoveNext
        subject = case.unit ?? case.parent;
        foreach (triggeredAbility in <toutes les TriggeredAbility de la bataille>) {
            if (case.unit != null && case.unit == triggeredAbility.Owner) continue;   // self exclu
            playbook = PlaybookDatabase.LoadPlaybookNonOwner(triggeredAbility.Type);
            if (playbook == null) continue;
            if (playbook.<slot 4> || UnitExtensions.IsFriend(subject, triggeredAbility.Owner, state))
                yield (playbook, triggeredAbility.Owner);
        }

Le pre-gate `<slot 4> || IsFriend` est le complement de
`IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility$$IsInvalidEntityForPlaybook`
(= `!slot4 && !IsFriend`). `slot 4` est un predicat SANS argument de l'interface
`ITriggeredAbilityNonOwnerPlaybook`, dont le corps est TRIVIAL (fondu par l'ICF, donc sans symbole
propre) : on ne le lit pas ici, et on ne l'INVENTE pas. Ce port ne le porte pas parce qu'il est
TRANSPARENT pour le seul playbook enregistre : `KustomForceFieldReworkedNonOwnerPlaybook` RE-TESTE
`IsFriend` dans son propre corps, donc un porteur non-ami rend 0 que le pre-gate l'ait ecarte ou
non. RESIDU NOMME : le jour ou un playbook NonOwner sans auto-gate entre au registre, il faudra
lire ce slot (bloc `methodPointers` du PE, cf. `probe_8889_methodptr_vtable.py`) avant de le porter.

ASCII only dans les sorties ; les accents restent dans les docstrings non imprimees.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..entities.unit_faction import UnitFaction


class TriggeredAbilityNonOwnerPlaybook:
    """Base : `IdunBattle.AI.Playbook.TriggeredAbilityNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateMovementUtilityInSteps`
    yield 0 (la base ne pese rien ; seuls les concrets qui overrident comptent).

    Signature du port : `calculate_movement_utility_in_steps(tile, owner, is_friend, ctx, wt)` ou
      * `tile`      = la tuile candidate du mover (`UtilityMovementCase.get_MovementTile`) ;
      * `owner`     = l'enregistrement du PORTEUR de l'ability (le `owner` du natif), avec `pos` ;
      * `is_friend` = `UnitExtensions.IsFriend(case.unit, owner, state)` ;
      * `ctx`       = le dict par-decision `tile_leaf_ctx` (porte `unit_faction`, `elev_by_pos`, ...).
    Le natif passe le CASE entier ; le port passe ce que le CASE expose deja aux autres familles."""

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        return 0.0


class KustomForceFieldReworkedNonOwnerPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """`KustomForceFieldReworkedNonOwnerPlaybook`
    (`IdunBattle.AI.Playbook.Loki.KustomForceFieldReworkedNonOwnerPlaybook$$.ctor` : litteral
    `0x60b` = 1547 `KustomForceFieldReworked`, passif d'`orksBigMek` — HERO du pool spawnable).

    `IdunBattle.AI.Playbook.Loki.KustomForceFieldReworkedNonOwnerPlaybook.u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext`,
    remis en C# depuis le decompile :

        if (case.unit == null) yield break;
        if (!UnitExtensions.IsFriend(case.unit, owner, state)) yield break;
        ITile ownerTile = EntityExtensions.GetMainTile(owner, state);
        if (ownerTile == null) yield break;
        if (!TileExtensions.IsAdjacentTo(case.MovementTile, ownerTile)) yield break;
        Fix64 v = GetUtilityValue("KustomForceFieldReworked_FriendsLikeToBeAdjacent");
        if (UnitExtensions.HasFaction(case.unit, 5))            // UnitFaction.Orks
            v *= Fix64.FromInt(2);
        yield return v;

    Trois points que le decompile TRANCHE et qu'il ne faut pas deviner :

    * **Le `HasFaction` porte sur `case.unit`, PAS sur `owner`** — c'est le MOVER qui doit etre Ork
      pour doubler, pas le Big Mek (qui l'est toujours). Le terme separe donc DEUX AMIS de
      factions differentes autour du meme porteur : `x2` pour un Ork, `x1` pour un allie d'une
      autre faction. C'est ce qui le rend inexprimable par un poids unique.
    * **Le doublement est un `Fix64.op_Multiply` par `Fix64.FromInt(2)`**, pas un second poids BC :
      rien a chercher dans la table.
    * **La cle vit dans `TriggeredAbilitiesNonOwner`**, pas dans `TriggeredAbilities` (categorie
      distincte du meme `Utilities.Default`). Litteral LU (`probe_212_bc_key_literals.py` sur le
      symbole du `MoveNext`), pas devine.

    `IsAdjacentTo` = `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(a, b)` =
    `|elev(b) - elev(a)| < 2 && (a == b || ConnectivityComponent(a).IsNeighbour(b))` — mirror
    `battle_query.are_entities_adjacent`, le foyer qui porte la branche `a == b` (COURT-CIRCUIT
    D'IDENTITE, #433-r1) en plus de la distance hex 1 et de la porte d'elevation. ⚠ NE PAS retomber
    sur `battle_query.is_adjacent` : celui-la mirrore `TileQuery$$IterateAdjacentTiles` et exclut
    `a == b` a bon droit (distance 0). Cette branche est INATTEIGNABLE ici (la tuile du porteur est
    occupee, donc jamais candidate pour le mover) ; on la mirror quand meme plutot que de la
    supprimer sur un argument d'atteignabilite."""

    ABILITY_ID = int(TriggeredAbilityType.KustomForceFieldReworked)     # 0x60b = 1547
    KEY = "KustomForceFieldReworked_FriendsLikeToBeAdjacent"            # gameconfig vivant = 10

    def calculate_movement_utility_in_steps(self, tile, owner: dict, is_friend: bool,
                                            ctx: dict, wt) -> float:
        if not is_friend:                                    # UnitExtensions.IsFriend(case.unit, owner)
            return 0.0
        opos = (owner or {}).get("pos")
        if not opos:                                         # GetMainTile(owner) == null
            return 0.0
        tile, opos = (tile[0], tile[1]), (opos[0], opos[1])
        elev = (ctx or {}).get("elev_by_pos")
        if not bq.are_entities_adjacent(tile, opos, elev):             # TileExtensions.IsAdjacentTo
            return 0.0
        v = float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))
        if (ctx or {}).get("unit_faction") == int(UnitFaction.Orks):   # HasFaction(case.unit, 5)
            v *= 2.0
        return v


# `IdunBattle.AI.PlaybookDatabase$$LoadPlaybookNonOwner` : singleton par TYPE d'ability, cache
# dict@0xa0 + factories dict@0x98. Le binaire declare 25 concrets `*NonOwnerPlaybook` ; seuls ceux
# qu'un case a montres decisifs sont portes ici. Absence du registre == `LoadPlaybookNonOwner`
# rend null == la paire n'est jamais yieldee : MEME degradation que le natif, pas un trou.
NON_OWNER_MOVE_PLAYBOOKS: dict = {
    # #271 — DEMASQUE par le refresh `catalog_inject.refresh_ai_utilities` : la cle valait 0 dans la
    # table de la CAPTURE, elle vaut 10 au gameconfig VIVANT. Avant le refresh, natif et moteur
    # etaient d'accord ET faux tous les deux.
    int(TriggeredAbilityType.KustomForceFieldReworked): KustomForceFieldReworkedNonOwnerPlaybook(),
}


def load_playbook_non_owner(ability_id: int):
    """Mirror `PlaybookDatabase.LoadPlaybookNonOwner` (movement-relevant uniquement). None -> la
    feuille skip la paire (meme chemin que le `if (playbook == null) continue` natif)."""
    return NON_OWNER_MOVE_PLAYBOOKS.get(int(ability_id))
