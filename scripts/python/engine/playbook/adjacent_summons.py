"""Playbook de MOUVEMENT qui COMPTE LES SUMMONS AUTOUR DE LA TUILE CANDIDATE, tous camps confondus.

Famille « corps propre » (chaque concret a son propre `CalculateMovementUtilityInStepsInternal`,
iterateur dedie dans le binaire), MEME dispatcher que `friends_in_range.py` et
`adjacent_unit_preference.py` : feuille de tuile `TriggeredAbilitiesUtility(2)` ->
`IdunBattle.AI.PlaybookDatabase$$LoadPlaybook(abilityType)`, d'ou l'enregistrement commun dans
`TRIGGERED_MOVE_PLAYBOOKS`.

Ce module existe SEPAREMENT de `friends_in_range.py` parce que la query n'est pas la meme, et
l'ecart est LU au call-site :

    friends_in_range  -> `FUN_1800051d0(0x83, IBattleQuery, query, tile, case.unit)`
                          = `GetAdjacentFriends(tile, unit)`   -- AMIS, arite 2
    ce module         -> `FUN_18002dac0(0x7a, IBattleQuery, query, tile, 0, 0, 0)`
                          = `GetAdjacentUnits(tile, friendsOf: null, enemiesOf: null,
                                              ignoreSteppables: false)`  -- TOUS, arite 4

Le slot `0x7a` est deja etabli (#443-r1, `playbook/savior_protocols.py`) : identifie par le COMPTE
ET L'ORDRE des arguments contre les signatures nommees de
`IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery$$GetAdjacentUnits`. Les trois
litteraux `0, 0, 0` disent **aucun filtre de camp** et **steppables INCLUS**.

⚠ COMME toute la famille « corps propre », ce corps natif N'EXCLUT PAS l'unite qui evalue : la
query travaille par TUILE et ne connait pas la notion de « soi », et le mover est encore SUR SON
ORIGINE pendant tout le sweep. Il se compte donc lui-meme des que son origine tombe dans le
voisinage de la tuile candidate -- ici sous condition qu'il porte lui-meme `Summon`. C'est le meme
fait que documente l'en-tete de `friends_in_range.py`, et `SaviorProtocolsPlaybook` (meme slot
`0x7a`) doit ecrire un `!AreEqual(Target, Owner)` EXPLICITE dans son trigger pour s'exclure --
preuve que le natif ne l'exclut pas tout seul.

ASCII only.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.traits.unit_trait import UnitTrait, has_trait
from ..entities.triggered_ability_type import TriggeredAbilityType


class MawClawsOfThyraxPlaybook:
    """`MawClawsOfThyraxPlaybook` (`IdunBattle.AI.Playbook.Loki.MawClawsOfThyraxPlaybook$$.ctor` :
    litteral `0x5bd` = 1469 `MawClawsOfThyrax` -- RELIQUE, pas un passif de kit) ;
    `IdunBattle.AI.Playbook.Loki.MawClawsOfThyraxPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`,
    remis en C# depuis le decompile :

        tile  = UtilityMovementCase.get_MovementTile(case)                 // case @+0x28
        units = query.<slot 0x7a>(tile, null, null, false)                 // GetAdjacentUnits
        val   = 0
        foreach (u in units)
            if (UnitExtensions.HasTrait(u, 0x2))                           // UnitTrait.Summon
                val += getUtilityVal("MawClawsOfThyrax_LikesAdjacentSummons");   // 5
        yield Fix64.FromInt(val)

    QUATRE lectures qui ne se devinent pas :

    * **La query est `GetAdjacentUnits`, pas `GetAdjacentFriends`** -- tranchee par l'ARITE du
      call-site (4 arguments apres `this`, litteraux `0, 0, 0`) contre les signatures de
      `frida/methods.tsv`. Un summon ENNEMI adjacent verse donc le poids AUSSI. C'est cohérent avec
      l'EFFET de la relique, dont le compteur natif est lui aussi `AdjacentUnits` (cf.
      `entities/effects/loki/maw_claws_of_thyrax.py`) -- et c'est l'inverse de
      `KardiocoreGalvanusPlaybook`, dont la query EST `GetAdjacentFriends` (slot `0x83`, arite 2) ;
    * **il y a un FILTRE, contrairement a `KardiocoreGalvanusPlaybook`** : le corps appelle
      `IdunBattle.Entities.UnitExtensions$$HasTrait(u, 0x2)` sur chaque element de l'enumerateur.
      Chez `KardiocoreGalvanus` le `get_Current` de l'enumerateur est appele et son resultat
      DISCARDE (le corps ne fait que compter) -- deux corps de meme forme, un filtre chez l'un et
      pas chez l'autre : recopier le voisin donnerait un terme faux d'un facteur egal au nombre de
      voisins non-summon ;
    * **la cle BC est `MawClawsOfThyrax_LikesAdjacentSummons`** (slot de litteral `0x33d90d0`), a
      NE PAS confondre avec `MawClawsOfThyrax_AdjacentSummons` (`0x33d8f88`), qui est celle de la
      face NON-OWNER (`playbook/non_owner.py`). Les deux valent 5 au gameconfig vivant, donc une
      confusion serait aujourd'hui INVISIBLE -- raison de plus pour la lire au slot ;
    * **la face ATTACK de cette meme classe est un ZERO CONSTANT.**
      `...MawClawsOfThyraxPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
      a pour corps ENTIER `yield return Fix64.op_Implicit(0)` -- aucune lecture du case, aucun
      poids. Elle n'est donc pas portee : l'inscrire au registre ATTACK n'ajouterait qu'un terme
      nul. Dit plutot que suppose.

    Porteurs (voie RELIQUE, `catalog_inject.relic_carriers`) : `genesPatriarch`, `tyranParasite`,
    `tyranTyrantGuard`, `tyranWingedPrime` -- les QUATRE au pool, relique NON equipee au seed
    (etat 2, `--equip-relic`).

    Poids BC : `Utilities.Default.TriggeredAbilities["MawClawsOfThyrax_LikesAdjacentSummons"]` = 5.
    """

    ABILITY_ID = TriggeredAbilityType.MawClawsOfThyrax        # 0x5bd = 1469
    WEIGHT_KEY = "MawClawsOfThyrax_LikesAdjacentSummons"
    #: `UnitExtensions$$HasTrait(u, 0x2)` -- enum QUALIFIE `UnitTrait` (homonymes a ecarter :
    #: `EffectType` 2 = `Damaged`, `UnitSelectionType` 2 = `OnlyTargetable`).
    TRAIT = UnitTrait.Summon

    def calculate_movement_utility_in_steps(self, tile, ctx: dict, wt) -> float:
        """`GetAdjacentUnits(tile, null, null, false)` filtre par `HasTrait(u, Summon)`, x le poids.

        `ctx` = le dict tile-leaf des DEUX foyers (`tile_leaf_ctx` cote decision,
        `runner_tile_leaf_ctx` cote runner). Les deux listes `friend_units`/`enemy_units` sont
        SELF-EXCLUES : le mover est reintroduit explicitement par `self_pos`/`unit_traits`, parce
        que la query native, elle, ne l'exclut pas (cf. l'en-tete du module).

        ADJACENCE NATIVE (`bq.is_adjacent`), jamais `hexgeo.distance == 1` nu : `GetAdjacentUnits`
        passe par `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`,
        donc liste STOCKEE puis porte d'elevation `abs(delta) < 2` (#271).

        DEGRADATION : `self_pos` ou `unit_traits` absent du `ctx` (regime SPAWN, producteur sans
        cle de sujet) -> le mover n'est pas compte, les voisins le sont quand meme. C'est le meme
        arbitrage que `savior_protocols.py` sur `unit_parent_id`."""
        w = wt.sub("TriggeredAbilities", self.WEIGHT_KEY)
        if not w:
            return 0.0
        ctx = ctx or {}
        elev = ctx.get("elev_by_pos")
        neigh = bq.neigh_map(ctx)
        n = 0
        for units in (ctx.get("friend_units") or (), ctx.get("enemy_units") or ()):
            for u in units:
                if not bq.is_adjacent(tile, u["pos"], elev, neigh):
                    continue
                if has_trait(u.get("traits"), self.TRAIT):     # HasTrait(u, 0x2)
                    n += 1
        # Le MOVER lui-meme : la query natives travaille par TUILE et ne l'exclut pas, et il est
        # encore sur son ORIGINE pendant tout le sweep. `unit_traits` du `ctx` est une liste d'IDS
        # (`entity_trait_ids`), la ou le `traits` d'un voisin est une liste de NOMS -- d'ou le
        # `int(...)` ici et le `has_trait` ci-dessus, sur deux substrats de forme differente.
        sp = ctx.get("self_pos")
        if sp is not None and int(self.TRAIT) in (ctx.get("unit_traits") or ()) \
                and bq.is_adjacent(tile, sp, elev, neigh):
            n += 1
        return float(w * n)
