"""`TitanhammerSquadPlaybook` (1231, `astarLysander` << Lysander >>) -- face DECISION.

BASE LUE, JAMAIS DEDUITE DU `.ctor`
-----------------------------------
`data/symbols/<build>/frida/classes.tsv` :

    IdunBattle.AI.Playbook.Loki.TitanhammerSquadPlaybook | 112 | IdunBattle.AI.Playbook.NonComparablePlaybook`1

alors que `IdunBattle.AI.Playbook.Loki.TitanhammerSquadPlaybook$$.ctor` appelle
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor(this,
0x4cf, klass)` -- corps trivial DEDUPLIQUE par ICF, que ghidra etiquette du nom de l'autre
proprietaire. Meme piege, meme correction que `AdaptiveStrategyPlaybook` (#945) et `MindControl`
(#552). Seul l'`ability_id` `0x4cf` = 1231 se lit dans ce `.ctor`.

CE QUE CE PORT CORRIGE, ET POURQUOI RIEN NE LE SIGNALAIT
--------------------------------------------------------
1231 etait absente de `_NONCOMPARABLE_ABILITIES` : `makes_damage_predictions("TitanhammerSquad")`
rendait `True`, donc `playbook/prediction/abilities.make_damage_predictions` FABRIQUAIT un
`ProbableDamageEvent` depuis les `minDmg`/`maxDmg` du gameconfig de 1231. Le natif, lui, n'a
AUCUN `Make*Predictions` (`frida/methods.tsv` ne declare a cette classe que `..ctor`, `.cctor`,
`EvaluateNonComparable`, `GetUtility`, `GetUseProbability`, `GetCustomUnitOrderUtility`,
`IsValidTileForAbility`) -- il n'emet donc AUCUN event de degat pour elle. Degradation
SUR-EVALUANTE et silencieuse, exactement le patron de `#109` (Gauntlets/Hammer) et `#945`.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.TitanhammerSquadPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(<statique de la classe>))   # ctor 3-ARG
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition):
        util = this.GetUtility(caster, entities.<+0x10>)
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities.<+0x10>, util))
    return bucket

`IdunBattle.AI.Playbook.Loki.TitanhammerSquadPlaybook$$.cctor` :

    <statique> = Fix64.op_Implicit(1)          # -> MIN_UTILITY = 1

`IdunBattle.AI.Playbook.Loki.TitanhammerSquadPlaybook$$GetUtility(caster, target)` :

    set = PooledHashSet<IEntity>.Get()
    foreach t in battleQuery.<slot 0x4f>(target, false, true, true):   # GetAdjacentTiles
        set.AddRange(battleQuery.<slot 0x7f>(t, caster, true))         # GetAdjacentEnemies
    return Fix64.op_Implicit(set.Count)

Les deux slots sont LUS dans `data/symbols/<build>/metadata/interface_slots.tsv` (`IBattleQuery
79 GetAdjacentTiles 4` et `IBattleQuery 127 GetAdjacentEnemies 3`), jamais devines -- c'est
exactement la voie que #287-r11-r1-r1 prescrit apres le decalage-de-un qu'elle a trouve.

Trois lectures qui ne se devinent pas :

1. **L'utilite est un COMPTE D'ENNEMIS DISTINCTS, pas un degat.** Le `PooledHashSet` dedoublonne :
   un ennemi voisin de DEUX tuiles de la couronne de la cible ne compte qu'une fois. C'est ce qui
   distingue ce corps d'un `Sum(Count(...))`, et ce que `set` rend litteralement.
2. **La CIBLE est une TUILE.** `IdunBattleLogic.Entities.Abilities.Active.Loki.TitanhammerSquadAbility$$.ctor`
   passe le masque `0x6001042` = `TargetMatchesDynamicRule | TargetIsTile | TargetTileIsFree |
   AllowObscuredTarget` (deja LU et porte par la face COMBAT,
   `engine/runner/abilities/astartes.py`). L'utilite compte donc les ennemis autour du POINT DE
   TELEPORTATION, pas autour d'une unite.
3. **La composition est `adj o adj`, et on ne la remplace PAS par une distance.** `GetAdjacentTiles`
   comme `GetAdjacentEnemies` passent par
   `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, donc par la
   liste de voisins STOCKEE puis la porte d'elevation `|Delta| < 2` -- une relation qui n'est PAS
   la couronne hex des que le relief ou un pont bouge (#433-r4-r1-r4-r2 : 38 aretes d'ecart
   mesurees sur `C3_14`). Le foyer `battle_query.is_adjacent` porte les deux etages ; on l'appelle
   DEUX FOIS plutot que d'ecrire `distance <= 2`.

CE QUI N'EST PAS PORTE ICI, ET C'EST DIT
-----------------------------------------
* `GetUseProbability(unit)` = `HasFlag(unit, UnitFlag.ArrivedAtFinalTile) ? 0
  : (GetUtilityValue("<cle>") + GetUtilityValue("<cle2>") * Count(GetCurrentlyAffectedFriends))
    / 100`. Le port laisse `should_evaluate` a `True` : c'est l'ECART DEJA ASSUME par
  `NonComparablePlaybook.should_evaluate` pour tous les `GetUseProbability` conditionnels
  (`BlackRage` 0.4, `ItItches`), le moteur du port etant deterministe. S'y ajoute ici une raison
  MESUREE : les deux cles de poids que ce corps lit sont **ABSENTES** de
  `BattleConfiguration.Utilities.Default` du seed (`ActiveAbilities` = 18 cles, aucune
  `Titanhammer*`), donc leur valeur portee serait 0 -- et un `0/100 = 0` ferait rendre False a
  `ShouldEvaluate`, c'est-a-dire SUPPRIMER l'ability du generateur. Porter le terme sans ses poids
  serait strictement pire que ne pas le porter. Residu.
* `GetCustomUnitOrderUtility(unit)` = `Fix64(|FilterInPlace(GetAllFriendsOf(GetOriginalOwnerEntityId
  (unit)), f => HasTrait(f, 0x40f = UnitTrait.TerminatorArmour))| + 1) * GetUtilityValue("<cle>")`.
  C'est la couche ORDRE D'ACTIVATION des unites (`Utilities.Default.UnitOrder`), pas la face
  decision d'une ability -- elle ne passe pas par `EvaluateNonComparable`. Meme cle absente du
  seed. Residu.
* `IsValidTileForAbility(unit, position, possiblePositions)` =
  `EntityExtensions.GetUnitPosition(unit, state).Equals(position)` : gate << je ne me deplace pas
  pour lancer >>, le MEME corps que `StormOfFlensingBladesPlaybook$$ShouldExecute` deja porte
  (`should_execute_gates`). Il est INERTE ici parce que `generate_candidates` n'enumere que
  `fromHere` (l'origine) -- cf. la section suivante. Il redeviendrait actif le jour ou l'on
  balaierait les tuiles de move.

VOIE D'ENUMERATION -- TILE-TARGETED, donc PAS le plan
------------------------------------------------------
`computeAttackPlans` ne boucle que sur les ENNEMIS : un port branche dessus rendrait `rankCount =
0` pour toute paire (1231, x) et serait MUET sans erreur. Voie employee : `eligible_target_tiles`
(`abilityTargets(uid, 1231).fromHere`, `kind == "tile"`), le mirror de
`GetEligibleTargetsSelectable(caster, casterPosition)` en domaine TUILE -- la MEME que
`TheQuickeningPlaybook`.

ECART NOMME : `fromHere` n'enumere que depuis l'ORIGINE, alors que le natif balaie aussi les
tuiles de MOVE. Ici l'ecart est NUL par construction et pas par chance :
`IsValidTileForAbility` REFUSE toute position autre que celle du caster, donc le natif lui-meme
n'a qu'une position candidate.
"""
from __future__ import annotations

import hexgeo

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait

from ._base import NCContext, NonComparablePlaybook, _traits, eligible_target_tiles

#: `GetAdjacentEnemies(..., ignoreSteppables: true)` -- le 3e argument du call-site de `GetUtility`.
#: `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies` le relaie a `GetUnitsOnTiles`, qui
#: ECARTE les unites portant ce trait. Nom LU dans `data/symbols/<build>/frida/enums.tsv`.
_IGNORED_TRAIT = UnitTrait.Steppable.name


class TitanhammerSquadPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.TitanhammerSquadPlaybook$$EvaluateNonComparable` -- utilite =
    nombre d'ENNEMIS DISTINCTS du caster adjacents a une tuile de la couronne de la TUILE cible."""

    ABILITY_ID = int(ActiveAbilityType.TitanhammerSquad)   # 0x4cf = 1231
    #: `.cctor` : `Fix64.op_Implicit(1)` -> le `minUtility` du `Bucket` (gate `AddAction`).
    MIN_UTILITY = 1.0
    PRIORITY = 0        # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    @staticmethod
    def _ring(pos: tuple, ctx: NCContext) -> list:
        """`IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(from, false, true, true)` en
        domaine POSITION -- l'ENUMERATION de la liste stockee puis la PORTE d'elevation.

        On n'appelle pas `battle_query.get_adjacent_tiles` : elle enumere `hexgeo.neighbors` et
        exige des accesseurs `walkable_at`/`tile_exists` que `NCContext` ne publie pas sous cette
        forme. On prend la MEME source que `is_adjacent` -- `neigh_by_pos`, c.-a-d. la liste
        `ConnectivityComponent` captee -- et on lui repasse `is_adjacent` pour la porte
        d'elevation (idempotent sur ce canal, cf. sa docstring).

        TRI-ETAT : canal absent POUR CETTE TUILE -> repli GEOMETRIQUE nomme (couronne hex), la
        meme degradation PERMISSIVE que `is_adjacent`, jamais un ensemble vide."""
        neigh = bq.neigh_map(ctx)
        cand = None if neigh is None else neigh.get((pos[0], pos[1]))
        if cand is None:
            cand = hexgeo.neighbors(pos[0], pos[1])
        out = []
        for q in cand:
            p = (q[0], q[1])
            if bq.is_adjacent(pos, p, ctx.elev_by_pos, neigh):
                out.append(p)
        return out

    def _enemies_ignoring_steppables(self, ctx: NCContext) -> list:
        """Les unites que `GetAdjacentEnemies(..., unit: caster, ignoreSteppables: true)` peut
        retenir : les ennemis du CASTER, moins les `Steppable`.

        Substrat : `ctx.enemies` ({id, pos}) pour l'appartenance au camp adverse et la position --
        c'est deja le mirror de `<camp adverse de unit>` --, `ctx.obs_units` pour le `visualId` qui
        donne les traits (meme canal que `AdaptiveStrategyPlaybook._friend_units_non_hero`). Une
        unite dont le `visualId` n'est pas publie n'est PAS ecartee : borne SUPERIEURE nommee, et
        c'est la degradation permissive du reste du fichier -- un ecartement par defaut ferait
        DISPARAITRE des ennemis reels du comptage."""
        vis = {u.get("squadId"): u.get("visualId") for u in (ctx.obs_units or [])}
        out = []
        for e in (ctx.enemies or []):
            eid = e.get("id")
            p = e.get("pos")
            if p is None:
                continue
            col, row = (p.get("col"), p.get("row")) if isinstance(p, dict) else (p[0], p[1])
            if col is None or row is None:
                continue
            vid = vis.get(eid)
            if vid is not None and _IGNORED_TRAIT in _traits(vid):
                continue                                  # `ignoreSteppables: true`
            out.append((eid, (col, row)))
        return out

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`Fix64(|union_{t in GetAdjacentTiles(target)} GetAdjacentEnemies(t, caster)|)`.

        `target` est ici une POSITION de tuile `(col, row)` (cf. `eligible_target_tiles`), pas un
        id d'unite : le masque de 1231 porte `TargetIsTile`.

        `tile` (la position candidate du caster) N'ENTRE PAS dans la formule -- l'ancre est la
        TUILE CIBLE. Terme position-INDEPENDANT, donc le keep-first du `Bucket` retient l'origine,
        ce que `IsValidTileForAbility` impose de toute facon."""
        if target is None:
            return None
        tpos = (target[0], target[1])
        neigh = bq.neigh_map(ctx)
        enemies = self._enemies_ignoring_steppables(ctx)
        hit = set()
        for t in self._ring(tpos, ctx):                   # `GetAdjacentTiles(target, ...)`
            for eid, epos in enemies:                     # `GetAdjacentEnemies(t, caster, true)`
                if bq.is_adjacent(t, epos, ctx.elev_by_pos, neigh):
                    hit.add(eid)                          # `PooledHashSet` -> DISTINCTS
        return float(len(hit))

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`ActiveAbilityActionGenerator` + `Bucket$$ChooseAction` pour une ability TILE-TARGETED.

        L'ordre d'enumeration de `fromHere` EST celui du selecteur natif ; `Bucket$$AddAction` ne
        remplace que sur amelioration STRICTE, donc a utilite egale la PREMIERE tuile gagne. Le
        `>` ci-dessous herite cette semantique."""
        from_here, _union = eligible_target_tiles(ctx, self.ABILITY_ID)
        best = None                                        # (tuile, utilite)
        for tpos in from_here:
            util = self.evaluate_non_comparable(ctx.origin, tpos, ctx)
            if util is None or util < self.MIN_UTILITY:
                continue                                   # gate `minUtility` du `Bucket`
            if best is None or util > best[1]:             # STRICT -> keep-first au tie
                best = (tpos, util)
        if best is None:
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] TitanhammerSquad tile=%s util=%s"
                  % (ctx.uid, best[0], best[1]), file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None, "pred": best[1]}]
