"""Playbooks de MOUVEMENT qui COMPTENT DES AMIS AUTOUR DE LA TUILE CANDIDATE (famille « corps propre »).

Ces concrets NE sont PAS de la famille `AdjacentUnitPreferenceTriggeredAbilityPlaybook` : ils
n'overrident pas `GetAdjacent{Friend,Enemy}Utility` sur le corps partage, ils ont CHACUN leur
propre `CalculateMovementUtilityInStepsInternal` (iterateur dedie dans le binaire). Le dispatcher
est le meme (feuille de tuile `TriggeredAbilitiesUtility(2)` ->
`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(abilityType)`), d'ou l'enregistrement commun dans
`TRIGGERED_MOVE_PLAYBOOKS` (`adjacent_unit_preference.py`).

Motif commun aux trois corps natifs, LU au decompile :

    query   = <service IBattleQuery du playbook>
    tile    = UtilityAttackCase.get_CasterTile(case)         // la TUILE CANDIDATE
    units   = query.<slot>(tile, ..., case.unit@0x10, ...)   // amis AUTOUR de la tuile
    weight  = config[<cle BC>]                               // Utilities.Default.TriggeredAbilities[...]
    yield Fix64.FromInt(weight * units.Count)                // ou Sigma weight, meme chose

⚠ POINT DECISIF, mesure ET decompile concordants : ces corps N'EXCLUENT PAS l'unite qui evalue --
sauf celui qui l'ecrit. La query native ne retire que les ENNEMIS (`GetSurroundingUnits` ->
`IsEnemy`), et `FirstAmongTraitorsPlaybook` — meme slot, meme forme — ecrit un `!= case.unit`
EXPLICITE pour s'exclure, la ou `AstartesBanner`/`Kardiocore` n'en ecrivent aucun. Or l'unite qui
evalue est encore SUR SON ORIGINE pendant tout le sweep : elle compte donc pour elle-meme des que
son origine tombe dans le voisinage de la tuile candidate. C'est ce terme, invisible d'un
raisonnement « une aura ne se compte pas elle-meme », qui rend le residu POSITION-DEPENDANT
(cf. `docs/rl/case-n13-tile-term-triggered-playbooks.md`).

Cette famille se distingue donc d'`AdjacentUnitPreference` sur DEUX axes a la fois (self compte /
self exclu, disque cube sans porte d'elevation / ring-1 avec porte) : ne PAS les fusionner.

⚠ Et elle n'est pas homogene EN INTERNE non plus : sur les trois membres, DEUX (`AstartesBanner`,
`Kardiocore`) ne portent NI filtre de trait NI exclusion de self, le troisieme
(`FirstAmongTraitors`, #926) porte LES DEUX. Lire chaque corps, jamais le recopier.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.effects.magnitude import ability_var
from ..entities.ability_constant_type import AbilityConstantType   # #270-r1-r1-r3
from ..entities.triggered_ability_type import TriggeredAbilityType   # #270-r1-r1-r3
from ..entities.traits.unit_trait import UnitTrait   # #926 : `HasTrait(u, 0x7ea = Chaos)`


def _friend_positions_including_self(ctx: dict) -> list:
    """Positions des AMIS VIVANTS de l'unite qui evalue, **self INCLUS a son origine**.

    Mirror du contenu de `IdunBattle.Core.Services.BattleQuery$$GetSurroundingUnits` filtre par
    `ListExtensions.FilterInPlace(!IsEnemy(u, unit))` : toutes les unites POSEES du camp de
    `unit`, l'unite comprise (la query travaille par TUILE et ne connait pas la notion de
    « soi »). `ctx` = le dict par-decision `tile_leaf_ctx` :
      * `friend_units` = allies vivants SELF-EXCLU ({pos, traits, effects}) ;
      * `self_pos`     = origine de l'unite qui evalue (None si hors plateau -> non comptee,
                         degradation fidele : sans MainTile le natif ne la trouve sur aucune tuile).
    """
    out = [u["pos"] for u in (ctx.get("friend_units") or ()) if u.get("pos")]
    sp = ctx.get("self_pos")
    if sp:
        out.append(tuple(sp))
    return out


class AstartesBannerPlaybook:
    """`AstartesBannerPlaybook` (`IdunBattle.AI.Playbook.Loki.AstartesBannerPlaybook$$.ctor` ; ability
    0x452 = 1106 AstartesBanner — passif des Ancients Astartes, ex. templAncient) ;
    `IdunBattle.AI.Playbook.Loki.AstartesBannerPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

        tile  = UtilityAttackCase.get_CasterTile(case)
        range = AbilityConfiguration.GetNumberConstant(config, 0x16)          // "range" = 2
        units = IBattleQuery.<slot 0x75>(tile, range, case.unit, true)        // GetSurroundingUnits
        yield Fix64.FromInt( config["AstartesBanner_NearbyFriend"] * units.Count )

    ⚠ Le slot est `0x75` = **117** et non `0x74` : `data/symbols/<build>/metadata/interface_slots.tsv`
    donne `IBattleQuery 117 GetSurroundingUnits (arite 4)` (`0x74` = 116 = `GetUnitsAtDistance`,
    arite 2, incompatible avec les 4 arguments du call-site). Le numero ecrit ici avant #926 etait
    faux ; la SEMANTIQUE decrite, elle, etait juste --
    `IdunBattle.Core.Services.BattleQuery$$GetSurroundingUnits(from, range, friendsOf, includeCenter)`
    filtre par `if (friendsOf != null && IsEnemy(u, friendsOf)) skip`, ce qui est exactement le
    filtre d'amitie de `GetSurroundingFriends` (qui, lui, delegue a ce meme corps).

    Le dernier argument (`true`) est le flag `includeCenterTile` de
    `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` : l'ami
    DEBOUT SUR la tuile candidate compte (mesure `C4_09`/999 pas 14, tuile (6,4)). Aucun filtre de
    trait, aucune exclusion de self (cf. l'en-tete du module).

    Poids BC : `Utilities.Default.TriggeredAbilities["AstartesBanner_NearbyFriend"]` = 5."""

    ABILITY_ID = TriggeredAbilityType.AstartesBanner
    CONST_RANGE = AbilityConstantType.range          # GetNumberConstant(0x16) -> gameconfig `constants.range`
    WEIGHT_KEY = "AstartesBanner_NearbyFriend"

    def get_range(self) -> int:
        """`AbilityConfiguration.GetNumberConstant(config, 0x16)` = `constants.range` (= 2)."""
        r = ability_var("AstartesBanner", "range", is_constant=True)
        return int(r) if r is not None else 0

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0
        n = bq.count_surrounding(tile, _friend_positions_including_self(ctx or {}),
                                 self.get_range(), include_center_tile=True)
        return float(w * n)


class KardiocoreGalvanusPlaybook:
    """`KardiocoreGalvanusPlaybook` (`IdunBattle.AI.Playbook.Loki.KardiocoreGalvanusPlaybook$$.ctor` ;
    ability 0x5b1 = 1457 KardiocoreGalvanus — RELIQUE, pas un passif de kit) ;
    `IdunBattle.AI.Playbook.Loki.KardiocoreGalvanusPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

        tile  = UtilityAttackCase.get_CasterTile(case)
        units = IBattleQuery.<slot 0x82>(tile, case.unit)                     // GetAdjacentFriends
        foreach u in units:  val += config["KardiocoreGalvanus_LikesAdjacentMechanicalFriends"]
        yield Fix64.FromInt(val)

    ⚠ Le corps natif n'a **AUCUN filtre** : ni `HasTrait(Mechanical)`, ni `!= case.unit`. Le nom de
    la cle BC (« LikesAdjacentMechanicalFriends ») decrit l'EFFET de la relique (« +Crit Damage pour
    chaque unite Mecanique amie adjacente »), PAS l'utilite d'IA — l'utilite, elle, compte TOUS les
    amis adjacents. Ecart mesure et assume (`C4_09`/31337 pas 22 : les 3 amis comptes en (4,3) sont
    custoBladeChampion / bloodMephiston / eldarAutarch, aucun Mecanique).

    La query est un `GetAdjacentFriends` (ring-1 via `IterateAdjacentTiles`, tuile centrale EXCLUE,
    porte d'elevation `|Delta elev| < 2` — cf. `battle_query.is_adjacent`), la ou AstartesBanner passe
    par le disque `IterateSurroundingTiles`. Self compte des que l'origine est ring-1 de la tuile.

    Poids BC : `Utilities.Default.TriggeredAbilities["KardiocoreGalvanus_LikesAdjacentMechanicalFriends"]` = 5."""

    ABILITY_ID = TriggeredAbilityType.KardiocoreGalvanus
    WEIGHT_KEY = "KardiocoreGalvanus_LikesAdjacentMechanicalFriends"

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0
        ctx = ctx or {}
        n = bq.count_adjacent(tile, _friend_positions_including_self(ctx),
                              ctx.get("elev_by_pos"), bq.neigh_map(ctx))
        return float(w * n)


class FirstAmongTraitorsPlaybook:
    """`FirstAmongTraitorsPlaybook` (`IdunBattle.AI.Playbook.Loki.FirstAmongTraitorsPlaybook$$.ctor` :
    litteral `0x428` = 1064 `FirstAmongTraitors`, passif de `blackAbaddon`) ;
    `IdunBattle.AI.Playbook.Loki.FirstAmongTraitorsPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`
    (remis en C# depuis le decompile, champs de la SM : `case @+0x28`, `getUtilityVal @+0x30`) :

        tile  = UtilityMovementCase.get_MovementTile(case)
        range = FirstAmongTraitorsAbility.GetRange(playbook.<+0x58>)      // GetNumberConstant(0x16)
        units = IBattleQuery.<slot 0x75>(tile, range, case.unit@0x10, true)   // GetSurroundingUnits
        int value = 0;
        foreach (u in units)
            if (u != case.unit && UnitExtensions.HasTrait(u, 0x7ea))          // UnitTrait.Chaos
                value += getUtilityVal("FIRSTAMONGTRAITORS_SurroundingChaosFriend");
        yield return Fix64.op_Implicit(value);

    ⚠ **DEUX filtres que ses deux voisins de module n'ont PAS**, et c'est le tout du cas :
      * `u != case.unit` -- exclusion EXPLICITE du mover, alors que la query, elle, le rend (elle
        ne retire que les ENNEMIS de `case.unit`, et `IsEnemy(u, u)` est faux). Sans ce test le
        mover se compterait pour lui-meme des que son origine tombe dans le disque, exactement
        comme le font `AstartesBanner`/`Kardiocore` ;
      * `HasTrait(u, 0x7ea = UnitTrait.Chaos)` -- le pseudo-trait de GRANDE-ALLIANCE, ABSENT de
        `gameconfig.unit().traits` et present dans le substrat d'ENTITE. C'est le meme substrat que
        celui de la face NON-OWNER (`playbook/non_owner.py`), dont un recensement par gameconfig
        avait conclu a tort « terme inerte, 0 unite sur 1083 ».
    Et la FORME differe aussi : le natif SOMME le poids par unite retenue (`value += w`) au lieu de
    `w x Count` -- egalite arithmetique ici, mais c'est la boucle qui porte les deux filtres.

    Le `range` est celui de l'ABILITY (`FirstAmongTraitorsAbility$$GetRange` =
    `AbilityConfiguration.GetNumberConstant(config, 0x16)`, un `AbilityConstantType`, = 2), pas une
    variable de niveau -- meme accesseur que la face NON-OWNER et que le `CreateTargetSelector` de
    l'effet de combat, d'ou le FOYER partage `effects.loki.first_among_traitors`.

    ⚠ Le rayon d'UTILITE et le rayon de l'AURA sont donc le MEME nombre, mais les DEUX faces ne se
    recouvrent pas : l'utilite compte les amis Chaos autour de la TUILE CANDIDATE **tuile centrale
    COMPRISE** (`includeCenter = true`), la ou le selecteur de l'effet EXCLUT les tuiles du porteur
    (`SurroundingTiles - Tiles(Owner)`). Ne pas unifier les deux geometries.

    Poids BC : `Utilities.Default.TriggeredAbilities["FIRSTAMONGTRAITORS_SurroundingChaosFriend"]`
    = 10 (la face NON-OWNER lit une cle DIFFERENTE, `FIRSTAMONGTRAITORS_SurroundingOwner` = 20, dans
    une SECTION differente `TriggeredAbilitiesNonOwner`)."""

    ABILITY_ID = TriggeredAbilityType.FirstAmongTraitors      # 0x428 = 1064
    #: `FirstAmongTraitorsAbility$$GetRange` = `GetNumberConstant(config, 0x16)` -- la CONSTANTE.
    CONST_RANGE = AbilityConstantType.range                   # 0x16 = 22
    WEIGHT_KEY = "FIRSTAMONGTRAITORS_SurroundingChaosFriend"
    #: `UnitExtensions.HasTrait(u, 0x7ea)` du corps -- grande-alliance Chaos (substrat d'ENTITE).
    TRAIT = UnitTrait.Chaos                                   # 0x7ea = 2026

    def get_range(self) -> "int | None":
        """`AbilityConfiguration.GetNumberConstant(config, 0x16)` = `constants.range` (= 2).

        `None` = constante absente -> `GetNumberConstant` LEVE cote natif ; le port rend « aucun
        terme » plutot que d'inventer un rayon (meme degradation que la face NON-OWNER)."""
        r = ability_var("FirstAmongTraitors", self.CONST_RANGE.name, is_constant=True)
        return None if r is None else int(r)

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0
        rng = self.get_range()
        if rng is None:
            return 0.0
        ctx = ctx or {}
        # `friend_units` du `tile_leaf_ctx` est DEJA self-exclu quand il y a un sujet -- c'est
        # exactement le net du `!IsEnemy(u, case.unit)` de la query PUIS du `u != case.unit` du
        # corps. `traits` y est le substrat d'ENTITE (`entity_trait_names`), le seul ou le
        # pseudo-trait de grande-alliance `Chaos` existe.
        n = 0
        for u in (ctx.get("friend_units") or ()):
            p = u.get("pos")
            if not p:
                continue
            if self.TRAIT.name not in (u.get("traits") or ()):     # HasTrait(u, 0x7ea)
                continue
            # `GetSurroundingUnits(tile, range, ., includeCenter = true)` = le disque cube EXACT,
            # tuile centrale COMPRISE, sans porte d'elevation (cf. `battle_query.is_surrounding`).
            if bq.is_surrounding(tile, p, rng, include_center_tile=True):
                n += 1                                            # `value += w` par unite retenue
        return float(w * n)
