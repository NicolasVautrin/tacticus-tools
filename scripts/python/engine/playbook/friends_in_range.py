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

⚠ Et elle n'est pas homogene EN INTERNE non plus : sur les QUATRE membres, DEUX (`AstartesBanner`,
`Kardiocore`) ne portent NI filtre de trait NI exclusion de self, `FirstAmongTraitors` (#926) porte
LES DEUX, et `GrimEfficiency` (#959-r1) porte l'exclusion de self SANS filtre de trait -- et par un
TROISIEME mecanisme encore (`ICollection<T>.Remove` sur le resultat de la query, la ou
`FirstAmongTraitors` ecrit un `!=` dans sa boucle). Lire chaque corps, jamais le recopier.

⚠ La GEOMETRIE non plus n'est pas commune : `AstartesBanner` passe `includeCenter = 1` (l'ami
DEBOUT SUR la tuile candidate compte), `GrimEfficiency` passe `includeCenter = 0` (il ne compte
pas). Le flag est un LITTERAL du call-site, different d'un membre a l'autre -- il se lit, il ne se
suppose pas.
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


class GrimEfficiencyPlaybook:
    """`GrimEfficiencyPlaybook` (`IdunBattle.AI.Playbook.Loki.GrimEfficiencyPlaybook$$.ctor` :
    litteral `0x5d2` = 1490 `GrimEfficiency`, passif du roster Votann) ;
    `IdunBattle.AI.Playbook.Loki.GrimEfficiencyPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`
    (remis en C# depuis le decompile, champs de la SM : `<>4__this @+0x20`, `case @+0x28`,
    `getUtilityVal @+0x30`) :

        range = AbilityConfiguration.GetNumberConstant(playbook.<+0x58>.<+0x20>, 0x16);  // "range"
        units = IBattleQuery.<slot 0x79 = 121 GetSurroundingFriends>(
                    actor:         case.unit@0x10,
                    from:          case.position@0x18,      // le `UnitPosition` du CASE
                    range:         range,
                    includeCenter: 0);                      // FAUX -- cf. ci-dessous
        units.Remove(case.unit);                            // ICollection<T> slot 6
        yield return Fix64.op_Implicit(
            getUtilityVal("GrimEfficiency_FriendsInRange") * units.Count);

    ⚠ **DEUX ecarts avec `AstartesBanner`, qui est pourtant sa copie de forme** -- et les deux
    changent le compte :

      * **`includeCenter = 0`** (AstartesBanner passe `1`). Le flag descend jusqu'a
        `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`, donc
        l'ami DEBOUT SUR la tuile candidate n'est PAS compte. Et l'overload de
        `IdunBattle.Core.Services.BattleQuery$$GetSurroundingUnits` qui prend une COLLECTION de
        tuiles (celui qu'atteint `GetSurroundingFriends` via `UnitPosition`) ajoute, quand le flag
        est faux, un SECOND filtre : `GetMainTile(u) == null || !from.Contains(GetMainTile(u))`.
        Sur une position mono-tuile les deux coincident ; sur une MoW multi-tuiles le second
        retire aussi les amis debout sur les AUTRES tuiles de la position.
      * **`units.Remove(case.unit)`** -- exclusion EXPLICITE du mover. Elle n'est pas redondante
        avec `includeCenter = 0` : pendant tout le sweep, le mover est encore sur son ORIGINE, qui
        n'est PAS la tuile candidate. Sans ce `Remove`, il se compterait pour lui-meme des que son
        origine tombe dans le disque -- exactement ce que font `AstartesBanner`/`Kardiocore`, qui
        n'ont ni l'un ni l'autre.

    ⚠ Le filtre de camp est `UnitExtensions.IsFriend`, pas `!IsEnemy` : le lambda de
    `IdunBattle.Core.Services.BattleQuery.u003Cu003Ec__DisplayClass142_0$$u003CGetSurroundingFriendsu003Eb__0`
    est LITTERALEMENT `return UnitExtensions.IsFriend(u, actor, state)`, applique par
    `ListExtensions.FilterInPlace` APRES la query. Les deux predicats ne coincident pas sur les
    neutres/objets, que `!IsEnemy` garderait.

    Poids BC : `Utilities.Default.TriggeredAbilities["GrimEfficiency_FriendsInRange"]` = 5
    (litteral `"GrimEfficiency_FriendsInRange"` du corps, LU dans
    `data/symbols/<build>/metadata/string_literals.tsv`).

    Face COMBAT (les deux auras qui partitionnent les stances) : livree par #959, confrontee live a
    0 ecart. C'est la face DECISION que ce port ajoute."""

    ABILITY_ID = TriggeredAbilityType.GrimEfficiency          # 0x5d2 = 1490
    #: `AbilityConfiguration.GetNumberConstant(config, 0x16)` -- la CONSTANTE, pas une variable
    #: de niveau (meme accesseur qu'`AstartesBanner` et `FirstAmongTraitors`).
    CONST_RANGE = AbilityConstantType.range                   # 0x16 = 22
    WEIGHT_KEY = "GrimEfficiency_FriendsInRange"

    def get_range(self) -> "int | None":
        """`AbilityConfiguration.GetNumberConstant(config, 0x16)` = `constants.range`.

        `None` = constante absente -> `GetNumberConstant` LEVE cote natif ; le port rend « aucun
        terme » plutot que d'inventer un rayon (meme degradation que `FirstAmongTraitors`)."""
        r = ability_var("GrimEfficiency", self.CONST_RANGE.name, is_constant=True)
        return None if r is None else int(r)

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0
        rng = self.get_range()
        if rng is None:
            return 0.0
        ctx = ctx or {}
        # `friend_units` du `tile_leaf_ctx` est DEJA self-exclu : c'est exactement le net du
        # filtre `IsFriend` de la query PUIS du `units.Remove(case.unit)` du corps. On n'appelle
        # donc PAS `_friend_positions_including_self` (qui re-injecte l'origine du mover) --
        # c'est la seule difference de cablage avec `AstartesBanner`, et elle est portee par le
        # `Remove` du decompile.
        positions = [u["pos"] for u in (ctx.get("friend_units") or ()) if u.get("pos")]
        # `includeCenter = 0` : la tuile candidate elle-meme ne compte pas.
        n = bq.count_surrounding(tile, positions, rng, include_center_tile=False)
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


class ECogSupportPlaybook:
    """`ECogSupportPlaybook` -- la face **OWNER** de `EcogSupport` (0x5cf = 1487, passif de
    `votanIronmaster` << Vynn >>), dont seule la face NON-OWNER etait portee (`non_owner.py`).
    #433-r4-r3-r2.

    Parente LUE dans la DECLARATION Il2CppDumper : `TriggeredAbilityPlaybook<ECogSupportAbility>`
    -- donc PAS la famille `AdjacentUnitPreference` : la classe a son PROPRE
    `CalculateMovementUtilityInStepsInternal` (slot 10), d'ou sa place dans CE module.

    `IdunBattle.AI.Playbook.Loki.ECogSupportPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`,
    remis en C# depuis le decompile (champs de la SM : `<>4__this @+0x20`, `case @+0x28`,
    `getUtilityVal @+0x30`) :

        int value = 0;
        tile  = UtilityMovementCase.get_MovementTile(case);
        units = IBattleQuery.<slot 0x83 = 131 GetAdjacentFriends>(tile, case.Unit@0x10);
        foreach (childUnit in units)
            if (UnitExtensions.GetParent(childUnit, State, root: false) == case.Unit)
                value += getUtilityVal("EcogSupport_EcogSummonsInRange");
        yield return Fix64.op_Implicit(value);

    ⚠ **C'EST LE PENDANT EXACT DE LA FACE NON-OWNER, PRIS A L'ENVERS, ET LES DEUX NE SE REDUISENT
    PAS L'UNE A L'AUTRE.** La non-owner (`EcogSupport_EcogAdjacentToParent` = 10) dit « ce E-Cog
    aime rester colle a Vynn » et rend un BOOLEEN ; celle-ci (`EcogSupport_EcogSummonsInRange` = 30)
    dit « Vynn aime se placer au milieu de ses E-Cogs » et **SOMME** : N summons adjacents valent
    N x 30.

    ⚠ Et le corps OWNER **ne teste PAS `HasTrait(Summon)`**, la ou la face NON-OWNER le fait :
    `GetParent(childUnit) == case.Unit` suffit, et `GetAdjacentFriends` apporte deja le filtre de
    camp. Recopier le gate de l'autre face ajouterait une condition que le natif n'a pas.

    ⚠ `GetAdjacentFriends` (slot 131, arite 2, LU dans
    `data/symbols/<build>/metadata/interface_slots.tsv`) n'EXCLUT PAS `case.Unit` -- toutes les
    surcharges deleguent a `BattleQuery$$CountOrGetUnitsOnTiles`, qui ne fait que
    `if (friendsOf != null && !IsFriend(u, friendsOf)) continue`. Ici c'est INERTE : le predicat
    `GetParent(u) == case.Unit` est faux pour `u == case.Unit` (une unite n'est pas son propre
    parent). Le `friend_units` self-exclu du `tile_leaf_ctx` est donc EXACT sur ce corps -- mais
    pour cette raison-la, pas parce que la query exclurait quoi que ce soit.

    SUBSTRAT. Le predicat exige le PARENT de CHAQUE VOISIN, la ou le `tile_leaf_ctx` ne publiait
    que celui du SUJET (`unit_parent_id`). La cle `parent` est posee par les TROIS jumeaux depuis
    #175-r1 / #433-r4-r3-r2 (`engine/utilities/tile.py`), sur le meme canal que `Scene.parent`
    (`combatSnapshot.units[].parentId` en live, `UnitComponent.parent_id` offline, #378).
    ⚠ TRI-ETAT : `parent = None` veut dire « pas de parent OU pas mesure ». Le port se tait alors,
    ce qui est le comportement natif quand `GetParent` rend `null` -- mais un canal MUET rendrait
    le terme identiquement nul sans le dire. C'est la borne de ce port.

    ADJACENCE = `IterateAdjacentTiles` -> porte d'elevation `|Delta| < 2` (`battle_query.is_adjacent`),
    jamais `hexgeo.distance == 1`.

    Poids BC : `Utilities.Default.TriggeredAbilities["EcogSupport_EcogSummonsInRange"]` = **30**
    (literal `0x335e288` de `metadata/string_literals.tsv` ; a NE PAS confondre avec `0x335e140` =
    `"EcogSupport_EcogAdjacentToParent"`, la cle de l'AUTRE face, dans l'AUTRE section).

    Porteur : `votanIronmaster`, HERO `lineup`."""

    ABILITY_ID = TriggeredAbilityType.EcogSupport             # 0x5cf = 1487
    WEIGHT_KEY = "EcogSupport_EcogSummonsInRange"

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0
        ctx = ctx or {}
        uid = ctx.get("uid")
        if uid is None:
            return 0.0                       # pas de `case.Unit` -> aucun parent a comparer
        elev = ctx.get("elev_by_pos")
        neigh = bq.neigh_map(ctx)
        n = 0
        for u in (ctx.get("friend_units") or ()):
            p = u.get("pos")
            if not p or not bq.is_adjacent(tile, p, elev, neigh):
                continue
            par = u.get("parent")            # `GetParent(childUnit, State, root: false)`
            if par is not None and int(par) == int(uid):
                n += 1                       # `value += getUtilityVal(...)` par summon retenu
        return float(w * n)

