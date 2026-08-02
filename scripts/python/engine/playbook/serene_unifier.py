"""`SereneUnifierPlaybook` (triggered 1145 `SereneUnifier`) -- face MOVE, corps PROPRE.

## Pourquoi ce module existe (#456-r1)

#456 a mesure que le terme MOVE du port rendait `0.0` la ou le natif rendait 101/202/303 sur
`tauAunShi`, sans pouvoir departager deux causes : (a) playbook non porte, (b) kit lu trop etroit.
La mesure de tranchage (`probe_456r1_move_kit_vs_playbook.py`, `MC1_67`/777, session 10) rend, pour
cette unite : kit NATIF (`unitAbilityStates` = l'`AbilitiesComponent`) `[1145]`, kit PORT `[1145]` --
**identiques**. La cause est donc (a), PURE et sans ambiguite : l'ability est bien presentee au
dispatcher, c'est `load_playbook` qui rend `None`.

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.SereneUnifierPlaybook$$.ctor` appelle la base avec le litteral
`0x479` = **1145** -- c'est ce qui identifie l'ability du playbook, pas son nom de classe.

`IdunBattle.AI.Playbook.Loki.SereneUnifierPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` :

    var tile  = UtilityMovementCase.get_MovementTile(case);              // la TUILE CANDIDATE
    var units = this.<>4__this.<query>.GetAdjacentFriends(tile, case.Unit);   // slot 0x83
    units.RemoveAll(u => u.Id == case.Unit.Id);                          // <>c__DisplayClass1_0.b__0
    yield return Fix64.op_Implicit(units.Count * 0x65);                  // 101, LITTERAL

Quatre lectures qui ne se devinent pas :

1. **Le slot `0x83` est `GetAdjacentFriends(tile, unit)`** -- le MEME que
   `KardiocoreGalvanusPlaybook` (deux arguments apres le `this` de la query, comme lui). Ce slot
   valait `0x82` sur le build `gqfc5mff6c` : l'interface a gagne une entree, et le glissement se
   verifie sur un second point d'appui -- `AstartesBannerPlaybook` et `FirstAmongTraitorsPlaybook`
   passent aujourd'hui par `0x75` la ou la docstring de `friends_in_range.py` note `0x74`. Les slots
   se RE-LISENT a chaque build ; on ne les cite ici que comme point d'ancrage, la semantique venant
   des signatures nommees de `IdunBattle.Core.Services.BattleQuery$$GetAdjacentFriends`.
   L'adjacence est celle de `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`,
   donc RING-1 avec la porte d'elevation `abs(delta) < 2` -- `battle_query.is_adjacent`, jamais
   `hexgeo.distance == 1` nu (#271).

2. **`RemoveAll`, pas `FilterInPlace`** -- la liste est MUTEE puis COMPTEE, et le predicat GARDE ce
   qui DIFFERE. La mesure le corrobore independamment : `FilterInPlace(u.Id == case.Unit.Id)` ne
   garderait au plus QUE le mover, donc `count in {0, 1}` et une utilite dans `{0, 101}` -- or le
   natif rend **303** sur ce montage.

3. **Le predicat compare des IDs, et c'est l'EXCLUSION DE SOI.** `<>c__DisplayClass1_0$$
   u003CCalculateMovementUtilityInStepsInternalu003Eb__0(u)` rend `Id(u) == Id(this.case.Unit)`.
   L'accesseur est le meme que celui qu'`IdunBattleLogic.Validation.MessageValidator$$
   RegisterInvalidUnit` boxe comme identifiant d'unite et que
   `IdunBattle.Operations.RemoveTriggeredAbilityOperation$$Execute` passe comme id d'entite a son
   event -- deux sites NOMMES et independants. L'exclusion est NECESSAIRE parce que
   `GetAdjacentFriends` travaille par TUILE et ne connait pas la notion de « soi » : l'unite qui
   evalue est encore SUR SON ORIGINE pendant tout le sweep, donc elle se compterait elle-meme des
   que cette origine tombe en ring-1 de la tuile candidate (c'est exactement le terme que
   `friends_in_range.py` documente, ici NEUTRALISE par le natif).

4. **`101` est un LITTERAL du corps (`imul` par `0x65`), PAS un poids BC.** Aucun
   `GetUtilityValue(<cle>)`, aucun `GetNumberConstant` n'apparait dans la state machine -- contrairement
   a `AstartesBanner` (`Utilities.Default.TriggeredAbilities[...]` x Count) ou a `KardiocoreGalvanus`.
   Il n'y a donc RIEN a chercher dans `BC.Utilities`, et une cle inventee la serait une fausse
   verite. La mesure live le confirme sans passer par le decompile : les totaux natifs observes pour
   le porteur sont exactement `{0, 101, 202, 303}`.

## Confrontabilite du porteur

`tauAunShi` est un HERO du pool (`rl_duel build --list-pool`) et arrive en bataille avec 1145 a son
`AbilitiesComponent` -- verifie par `unitAbilityStates`, pas deduit du gameconfig. Aucune greffe,
aucune injection catalogue, aucune relique : etat 1 de la gate de confrontabilite.

## Registre

Ability TRIGGERED : ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` ne s'appliquent (ces deux
donnees sont celles d'`ABILITY_CLASSES`, le registre des abilities ACTIVES castables). L'entree se
fait dans `TRIGGERED_MOVE_PLAYBOOKS` (`adjacent_unit_preference.py`), l'homologue de
`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook`.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.triggered_ability_type import TriggeredAbilityType

# `imul eax, 0x65` du corps natif -- litteral, PAS une cle de `BC.Utilities` (cf. en-tete §4).
SERENE_UNIFIER_PER_ADJACENT_FRIEND = 101


class SereneUnifierPlaybook:
    """`IdunBattle.AI.Playbook.Loki.SereneUnifierPlaybook` (triggered 1145). Sans etat, comme les
    autres entrees du registre MOVE : le natif n'en tient qu'UN singleton par type d'ability
    (`PlaybookDatabase$$LoadPlaybook`, cache dict)."""

    ability_id: int = int(TriggeredAbilityType.SereneUnifier)      # 1145 = 0x479

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        """Mirror de `<CalculateMovementUtilityInStepsInternal>d__1$$MoveNext` (cf. en-tete).

        `wt` est ACCEPTE et IGNORE : le corps natif ne lit AUCUN poids BC (le facteur est le
        litteral 101). La signature reste celle du registre, comme pour toute entree.

        La liste candidate est reconstruite SELF-INCLUS -- l'image de `GetAdjacentFriends`, qui
        travaille par tuile -- puis le `RemoveAll(u.Id == case.Unit.Id)` est applique EXPLICITEMENT.
        Ecrire directement `count_adjacent(friend_units)` donnerait le meme nombre aujourd'hui
        (les deux listes du `ctx` sont deja self-exclues), mais ferait dependre le port d'une
        propriete de son PRODUCTEUR de contexte plutot que du corps natif -- meme discipline que le
        noeud `!AreEqual(Target, Owner)` de `savior_protocols.py`.

        `self_pos` absent (unite hors plateau) -> elle n'est sur aucune tuile, donc sur aucune tuile
        adjacente : degradation FIDELE (sans `MainTile` le natif ne la trouverait nulle part), et
        sans effet ici puisqu'elle serait de toute facon retiree par le `RemoveAll`."""
        ctx = ctx or {}
        mover_uid = ctx.get("uid")
        # `GetAdjacentFriends(tile, case.Unit)` : amis POSES, self INCLUS.
        candidats = [{"id": u.get("id"), "pos": u.get("pos")}
                     for u in (ctx.get("friend_units") or ()) if u.get("pos")]
        sp = ctx.get("self_pos")
        if sp:
            candidats.append({"id": mover_uid, "pos": tuple(sp)})
        # `units.RemoveAll(u => u.Id == case.Unit.Id)`
        retenus = [u for u in candidats
                   if not (u["id"] is not None and mover_uid is not None
                           and int(u["id"]) == int(mover_uid))]
        n = bq.count_adjacent(tile, [u["pos"] for u in retenus], ctx.get("elev_by_pos"))
        return float(SERENE_UNIFIER_PER_ADJACENT_FRIEND * n)
