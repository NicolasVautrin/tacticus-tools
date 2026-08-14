"""Playbook de MOUVEMENT de `1298 VengeanceForTheOmnissiah` (passif d'`admecSmnTechpriest`
<< Tech-Priest Enginseer >> et de son jumeau npc `admecNpc2Techpriest`). #1071, face DECISION.

Famille << corps propre >> : `IdunBattle.AI.Playbook.Loki.VengeanceForTheOmnissiahPlaybook` a son
PROPRE iterateur -- elle n'herite ni d'`AdjacentUnitPreferenceTriggeredAbilityPlaybook` ni
d'`AdjacentToOwnerNonOwnerPlaybook`, donc elle n'override aucun accesseur de poids.

## Le corps natif, LU

`IdunBattle.AI.Playbook.Loki.VengeanceForTheOmnissiahPlaybook$$.ctor` appelle la base avec le
litteral `0x512` = **1298** -- c'est ce qui identifie l'ability du playbook, pas le nom de classe.

`...VengeanceForTheOmnissiahPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`,
remis en C# :

    var tile    = UnitPosition.get_MainTile(case.<+0x18>);          // la TUILE CANDIDATE
    var friends = this.<>4__this.<query>.<slot 0x83>(tile, case.<+0x10>);   // GetAdjacentFriends
    int value   = 0;
    foreach (var u in friends) {
        if (!UnitExtensions.IsMechanical(u))  continue;
        if (u == case.<+0x10>)                continue;             // pas SOI-MEME
        value = getUtilityVal("VengeanceForTheOmnissiah_LikesAdjacentMechanical");
        break;                                                      // <-- SORTIE AU PREMIER
    }
    yield return Fix64.op_Implicit(value);

QUATRE lectures qui ne se devinent pas :

1. **LE TERME EST BINAIRE, PAS UN PRODUIT.** Le `break` du decompile (`while (unit == case+0x10)`
   sortant du `do`, suivi immediatement de l'appel au poids puis du `Dispose`) fait que la valeur
   vaut `poids` des qu'UN voisin qualifie, et jamais `poids x N`. C'est ce qui distingue ce corps
   de TOUS ses voisins de forme (`legacy_of_combat`, `close_combat_weakness`, `first_among_traitors`
   : tous des `Count x poids`). Recopier leur `count_adjacent` ici multiplierait le terme par le
   nombre d'amis mecaniques -- silencieusement, et seulement sur les tuiles a plusieurs voisins.
   ⚠ C'est coherent avec ce que le passif FAIT (il gagne `effectLevel` = 1 niveau par mort, quel que
   soit le nombre de voisins), mais le port ne s'appuie PAS sur cette coherence : il mirroire le
   `break`.

2. **Le slot `0x83` = 131 est `IBattleQuery.GetAdjacentFriends`, arite 2** -- LU dans
   `data/symbols/<build>/metadata/interface_slots.tsv` (les slots 129..132 portent ce nom, les
   125..128 `GetAdjacentEnemies`), pas deduit du nom du playbook. Ce sont donc bien des AMIS.
   ⚠ Les slots se RE-LISENT a chaque build ; c'est la table qui tranche, pas le numero cite ici.

3. **`u == case.<+0x10>` EXCLUT LE MOVER LUI-MEME, et ce gate n'est pas decoratif** : le porteur est
   sa propre unite alliee, il est `Mechanical` (trait reel de `admecSmnTechpriest`), donc sans ce
   filtre il se compterait et le terme serait CONSTANT sur toutes les tuiles -- exactement le piege
   que la famille `friends_in_range` documente en sens inverse (elle, elle s'inclut).

4. **`IsMechanical` est une DISJONCTION de trois traits**, pas `HasTrait(Mechanical)` :
   `IdunBattle.Entities.UnitExtensions$$IsMechanical` = `HasTrait(5 Mechanical) ||
   HasTrait(1000 LivingMetal) || HasTrait(1029 Vehicle)`. Le port passe par le foyer
   `entities/traits/unit_trait.py::is_mechanical` -- ecrire le raccourci raterait DEUX traits sur
   trois, sans lever.

## La face ATTAQUE est DEAD, et c'est un RESULTAT

`...VengeanceForTheOmnissiahPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
a pour corps ENTIER, a l'etat 0 : `Fix64.op_Implicit(0)` puis `return true` ; a l'etat 1 :
`return false`. Un seul step, valeur **0**, aucun `getUtilityVal`, aucune query, aucun champ lu.
=> l'ability n'entre PAS dans `psyker.TRIGGERED_ATTACK_PLAYBOOKS`, et **son absence EST le
comportement natif** (la feuille ATTAQUE somme des steps ; un step a 0 ne se distingue pas d'un
playbook absent). Meme forme que `close_combat_weakness.py` et `legacy_of_combat.py`.

## La cle BC

`VengeanceForTheOmnissiah_LikesAdjacentMechanical`, presente dans la capture `data/seed-bc.json`
(`Utilities.Default.TriggeredAbilities`) ou elle vaut **30**.

## Confrontabilite du porteur

Les deux porteurs sont hors pool (`admecSmnTechpriest` SUMMON, `admecNpc2Techpriest` npc), mais le
JUMEAU NPC -- apparie par `visualId` -- s'amene par `--explicit-stats admecNpc2Techpriest:45`.
C'est un MIRROR, pas une greffe : il porte le MEME kit et ses PROPRES stats. Cf.
`probe_1071_vengeance_for_the_omnissiah.py` (face COMBAT, ACCORD live).

## Registre

Ability TRIGGERED : ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` ne s'appliquent (ces deux
donnees sont celles d'`ABILITY_CLASSES`, le registre des abilities ACTIVES castables). L'entree
MOVE se fait dans `TRIGGERED_MOVE_PLAYBOOKS` (`adjacent_unit_preference.py`), homologue de
`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook` ; l'ability atteint le dispatcher par son
`passiveAbilities` de kit.

ASCII only (cp1252).
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.traits.unit_trait import is_mechanical
from ..entities.triggered_ability_type import TriggeredAbilityType

#: La cle de poids du corps natif, telle qu'elle apparait dans
#: `BC.Utilities.Default.TriggeredAbilities` (= 30 dans la capture).
VENGEANCE_LIKES_ADJACENT_MECHANICAL = "VengeanceForTheOmnissiah_LikesAdjacentMechanical"


class VengeanceForTheOmnissiahPlaybook:
    """`IdunBattle.AI.Playbook.Loki.VengeanceForTheOmnissiahPlaybook` (triggered 1298). Sans etat,
    comme les autres entrees du registre MOVE : le natif n'en tient qu'UN singleton par type
    d'ability (`PlaybookDatabase$$LoadPlaybook`, cache dict).

    Terme BINAIRE : `30` s'il existe AU MOINS UN ami MECANIQUE (autre que le mover) adjacent a la
    tuile candidate, `0` sinon. Le porteur cherche donc a se placer au contact d'un allie mecanique
    -- ce qui est exactement la condition de declenchement de son passif (`On(UnitDefeated) &
    AreFriends & IsAdjacent & IsMechanical`), mais le corps d'utilite ne connait ni la mort ni
    l'effet : il ne pese que la PRESENCE."""

    ability_id: int = int(TriggeredAbilityType.VengeanceForTheOmnissiah)      # 0x512 = 1298
    WEIGHT_KEY = VENGEANCE_LIKES_ADJACENT_MECHANICAL                          # = 30 (capture)

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        """Mirror de `<CalculateMovementUtilityInStepsInternal>d__2$$MoveNext` (cf. en-tete).

        ⚠ PAS de `bq.count_adjacent` ici, DELIBEREMENT : le natif `break` au premier voisin
        qualifie, donc le terme est BINAIRE. `count_adjacent` rendrait `N` et le produit `30 x N`
        divergerait des la 2e unite mecanique adjacente -- silencieusement (lecture 1 de l'en-tete).

        L'adjacence passe par `battle_query.is_adjacent` (liste de voisinage STOCKEE + porte
        d'elevation `|delta| < 2` d'`IdunBattle.Core.Services.TileQuery.
        u003CIterateAdjacentTilesu003Ed__8$$MoveNext`), le meme foyer que toutes les feuilles
        ring-1 -- et non `hexgeo.distance == 1`, qui SUR-COMPTE au bord d'une marche (#271).

        `friend_units` = les amis VIVANTS poses, **self INCLUS** : c'est pourquoi le filtre
        `u["id"] != ctx["uid"]` est indispensable et non decoratif (lecture 3)."""
        ctx = ctx or {}
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0
        moi = ctx.get("uid")
        elev, neigh = ctx.get("elev_by_pos"), bq.neigh_map(ctx)
        for u in (ctx.get("friend_units") or ()):
            pos = u.get("pos")
            if not pos:
                continue
            # ORDRE des deux gates = celui du decompile (`IsMechanical` puis l'identite), sans effet
            # observable puisque les deux sont purs, mais on ne reordonne pas un mirror.
            if not is_mechanical(u.get("traits") or ()):
                continue
            if moi is not None and u.get("id") == moi:
                continue                                  # `u == case.<+0x10>` -- pas SOI-MEME
            if bq.is_adjacent(tile, pos, elev, neigh):
                return float(w)                           # `break` natif : terme BINAIRE
        return 0.0
