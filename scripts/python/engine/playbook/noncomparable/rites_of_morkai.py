"""`RitesOfMorkaiPlaybook` (1211, `spaceWolfPriest`) -- face DECISION. Ferme `#906-r1` / `#985-r1`.

LE BLOCAGE `seeding` DE LA FICHE ETAIT FAUX -- SUR SES DEUX POINTS, ET C'EST MESURE
=====================================================================================
`#985-r1` ecrivait : << `NCContext.fpos` est le voisinage ADJACENT (rayon 1) ; ici le rayon est
`GetMovementRange()` de l'ability, VARIABLE, et aucun canal ne le publie cote decision >>. Les
deux moities sont fausses, et aucune ne demandait un capteur :

  1. **LE RAYON EST UNE CONSTANTE DU GAMECONFIG, PAS UN ETAT RUNTIME.**
     `...VigilanceEternalAbility$$GetMovementRange` (corps DEDUPLIQUE, partage avec 1211) est
     `AbilityConfiguration$$GetNumberConstant(config, 0x16)`, et `0x16` est
     `AbilityConstantType.range`. Il se lit offline par
     `services.ability_caster_gates.try_get_number_constant`, exactement comme les autres
     `GetNumberConstant` deja portes. Pour `RitesOfMorkai` il vaut **1**.
  2. **`fpos` N'EST PAS LE VOISINAGE ADJACENT.** `engine/ai/context.py` le construit ainsi :
     `[pos(u) for u in units if u["ctrl"] and u["alive"] and u["id"] != uid]` -- soit TOUTES les
     positions alliees vivantes, self exclu. AUCUN filtre de rayon. Le commentaire de champ dit
     << GetAdjacentFriends >> parce que c'est son consommateur habituel, pas parce qu'il filtre :
     c'est cette ligne de commentaire, lue comme une definition, qui a fabrique le blocage.

Le port lit donc le rayon a la config et compte sur `fpos` par `battle_query.count_surrounding`,
ce qui GENERALISE a tout rayon au lieu de dependre du fait que celui-ci vaut 1.

BASE LUE, JAMAIS DEDUITE DU `.ctor`
-----------------------------------
`data/symbols/<build>/frida/classes.tsv` :

    IdunBattle.AI.Playbook.Loki.RitesOfMorkaiPlaybook | 112 | IdunBattle.AI.Playbook.NonComparablePlaybook`1

LE GATE AMONT -- DEUX CLAUSES CONJOINTES
------------------------------------------
`IdunBattle.AI.Playbook.Loki.RitesOfMorkaiPlaybook$$ShouldEvaluate(unit, position, possiblePositions)`,
lu verbatim :

    adj = battleQuery.<slot 0x7b = 123 GetAdjacentUnits>(position, null, false, ...)
    return adj.Any(<b__0>) ? adj.Any(<b__1>) : false

    <ShouldEvaluate>b__0(u) = UnitExtensions.IsFriend(u, unit, state)
    <ShouldEvaluate>b__1(u) = UnitExtensions.IsEnemy (u, unit, state)

Le `?:` du decompile EST la conjonction : le second `Any` n'est evalue que si le premier est vrai,
et c'est lui qu'on rend. Donc **au moins un ami ADJACENT ET au moins un ennemi ADJACENT**.
`friendsOf = null` au call-site -> `GetAdjacentUnits` rend les DEUX camps, et ce sont les deux
lambdas qui trient : ne pas confondre avec un `GetAdjacentFriends`.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.RitesOfMorkaiPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket(0, Nullable(<premier statique>))       # `.cctor` = Fix64(1)
    foreach entities in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition):
        util = Fix64.op_Implicit(1)
        adjE  = battleQuery.<slot 0x80 = 128 GetAdjacentEnemies>(casterPosition, caster, false)
        range = <ability@+0x68>.GetMovementRange()             # GetNumberConstant(0x16 = range)
        frnds = battleQuery.<slot 0x79 = 121 GetSurroundingFriends>(caster, casterPosition,
                                                                    range, includeCenter: false)
        if (adjE.<get_Count>() > 0) {
            c = Enumerable.Count(frnds, <EvaluateNonComparable>b__0)
            util = util + Fix64.op_Implicit(c * 100)
            bucket.AddAction(GenerateAction(casterPosition, entities.<+0x10 = target>, util))
        }
    return bucket

    <EvaluateNonComparable>b__0(f) = f != <caster>             # le caster s'exclut lui-meme

TROIS LECTURES QUI NE SE DEVINENT PAS
--------------------------------------
1. **L'UTILITE NE DEPEND PAS DE LA CIBLE.** Les deux requetes sont ancrees sur `casterPosition`,
   jamais sur `entities.Target` : toutes les cibles eligibles recoivent la MEME valeur. Le tie se
   resout donc par l'ORDRE d'enumeration -- `Bucket$$AddAction` ne remplace que sur `>` STRICT,
   donc c'est la PREMIERE cible de `fromHere` qui gagne. Un port qui trierait par utilite
   choisirait au hasard parmi des egaux.
2. **LE GATE `adjE.Count > 0` EST DANS LA BOUCLE MAIS INVARIANT** : ne dependant pas de la cible,
   il vaut pour toutes ou pour aucune. Quand il tombe, le `Bucket` est VIDE (aucun `AddAction`),
   et non pas rempli d'utilites plancher.
3. **`c * 100` EST MULTIPLIE AVANT LA CONVERSION** (`Fix64.op_Implicit(c * 100)`), donc c'est bien
   `1 + 100c` et non `(1 + c) * 100`.

CE QUE `includeCenter: false` CHANGE, ET POURQUOI `f != caster` EXISTE QUAND MEME
----------------------------------------------------------------------------------
`IdunBattle.Core.Services.BattleQuery$$GetSurroundingFriends(actor, from, range, includeCenter)`
= `GetSurroundingUnits(from, range, includeCenter)` puis `FilterInPlace(IsFriend(u, actor))`. Avec
`includeCenter = false`, la tuile `from` -- celle du caster -- est exclue du disque, donc le caster
ne peut deja plus s'y trouver par sa MAIN tile ; le predicat `f != caster` est la CEINTURE qui
couvre le cas multi-pieds. Cote port les deux sont poses : `include_center_tile=False`, et `fpos`
exclut deja le caster par construction (`u["id"] != uid`).

⚠ `GetSurroundingUnits` passe par `IterateSurroundingTiles` -- disque cube PUREMENT GEOMETRIQUE,
**sans porte d'elevation**. C'est `count_surrounding` (et non `count_adjacent`, qui mirrore
`IterateAdjacentTiles` et SA porte `|dElev| < 2`). Les deux primitives coexistent dans
`battle_query` precisement pour ne pas confondre ces deux voisinages : le gate amont et le gate de
cible utilisent bien `is_adjacent`, le COMPTAGE utilise `is_surrounding`.

VOIE D'ENUMERATION
-------------------
`GetEligibleTargetsSelectable(caster, casterPosition)`, domaine UNITE (`eligible_units`). Le
porteur est une unite a `PositionComponent`, donc l'ecart nomme en tete de `_targets` -- `fromHere`
n'enumere que depuis l'ORIGINE -- n'est PAS inerte ici. Il reste NOMME : le natif balaie aussi les
tuiles de move, et comme l'utilite depend de `casterPosition`, une autre position pourrait scorer
plus haut. Ce que le port couvre est la position d'ORIGINE, celle que le natif evalue EN PREMIER.

`PRIORITY = 0` -- 1211 ne surcharge pas `get_Priority` (absente de `NATIVE_PRIORITY`), donc le
defaut `AbilityPriority.Normal`.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.active_ability_type import ActiveAbilityType
from engine.services.ability_caster_gates import try_get_number_constant

import engine.playbook.noncomparable._targets as TGT      # FORME B, ABSOLU (#962)
from ._base import NCContext, NonComparablePlaybook


class RitesOfMorkaiPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.RitesOfMorkaiPlaybook` -- gate conjonctif ami+ennemi adjacents,
    puis `util = 1 + 100 * |amis dans le disque de rayon `range`, caster exclu|`, la MEME pour
    toutes les cibles. cf. l'en-tete du module."""

    ABILITY_ID = int(ActiveAbilityType.RitesOfMorkai)      # 0x4bb = 1211
    #: `...RitesOfMorkaiPlaybook$$.cctor` : `Fix64.op_Implicit(1)` -> `minUtility` du `Bucket`.
    MIN_UTILITY = 1.0
    #: `Fix64.op_Implicit(1)` POSE AVANT le terme -- plancher, pas un compte nu.
    BASE_UTILITY = 1.0
    #: `Fix64.op_Implicit(c * 100)` -- le 100 est un LITTERAL du corps, AUCUN `GetUtilityValue`,
    #: donc AUCUNE cle `BC.Utilities` a aller chercher (meme lecture que `DaemonicOrdnance.10`).
    FRIEND_UTILITY = 100.0
    PRIORITY = 0        # hors `NATIVE_PRIORITY` -> defaut `AbilityPriority.Normal`

    def _range(self) -> int | None:
        """`<ability>.GetMovementRange()` = `AbilityConfiguration$$GetNumberConstant(0x16 = range)`.

        `None` = la cle est ABSENTE du gameconfig. Le natif, lui, LEVE dans ce cas
        (`GetNumberConstant` jette sur cle manquante, contrairement a `TryGetNumberConstant`) :
        cote port on refuse d'evaluer plutot que de substituer un rayon invente -- un `1` par
        defaut serait juste pour CETTE ability et faux pour la suivante."""
        v = try_get_number_constant(self.ABILITY_ID, AbilityConstantType.range.name)
        return int(v) if v is not None else None

    def should_evaluate(self, ctx: NCContext) -> bool:
        """`RitesOfMorkaiPlaybook$$ShouldEvaluate` : `adj.Any(IsFriend) && adj.Any(IsEnemy)` sur
        `GetAdjacentUnits(position, friendsOf: null, ...)`.

        `friendsOf = null` -> la liste porte les DEUX camps ; les deux lambdas trient. Cote port
        les deux camps sont deja separes (`fpos` / `epos`), donc la conjonction se lit directement
        comme << au moins un de chaque dans le ring-1 >>.

        Position INCONNUE (`origin is None`, cas d'une MoW) -> `False` : le natif appellerait
        `GetAdjacentUnits(null)` et n'aurait aucun voisin, donc aucune des deux clauses ne pourrait
        etre vraie. Le porteur de 1211 est de toute facon une unite a position."""
        if ctx.origin is None:
            return False
        neigh = bq.neigh_map(ctx)
        elev = ctx.elev_by_pos
        amis = bq.count_adjacent(ctx.origin, ctx.fpos, elev, neigh)
        ennemis = bq.count_adjacent(ctx.origin, ctx.epos, elev, neigh)
        return amis > 0 and ennemis > 0

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`1 + 100 * Count(GetSurroundingFriends(caster, tile, range, includeCenter: false),
        f => f != caster)`, sous le gate `GetAdjacentEnemies(tile, caster, false).Count > 0`.

        `target` n'entre PAS dans la formule -- c'est la lecture centrale du corps natif : les deux
        requetes sont ancrees sur `casterPosition`. La signature le garde par contrat de la classe
        de base.

        Gate tombe, ou rayon indisponible -> `None` : le natif n'emet alors AUCUNE action pour
        cette cible (pas d'`AddAction`), et non une action d'utilite plancher."""
        if tile is None:
            return None
        neigh = bq.neigh_map(ctx)
        # `<slot 128 GetAdjacentEnemies>(casterPosition, caster, false).Count > 0` -- porte
        # d'elevation d'`IterateAdjacentTiles`, donc `is_adjacent`.
        if bq.count_adjacent(tile, ctx.epos, ctx.elev_by_pos, neigh) <= 0:
            return None
        rng = self._range()
        if rng is None:
            return None
        # `<slot 121 GetSurroundingFriends>` -> `IterateSurroundingTiles` : disque PUREMENT
        # geometrique, AUCUNE porte d'elevation -> `count_surrounding`, jamais `count_adjacent`.
        # `ctx.fpos` exclut deja le caster (`u["id"] != uid`), ce qui porte le predicat
        # `<EvaluateNonComparable>b__0` = `f != caster`.
        n = bq.count_surrounding(tile, ctx.fpos, rng, include_center_tile=False)
        return self.BASE_UTILITY + self.FRIEND_UTILITY * float(n)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`ActiveAbilityActionGenerator` + `Bucket$$ChooseAction`, domaine UNITE.

        ⚠ L'utilite etant la MEME pour toutes les cibles, le choix se joue ENTIEREMENT sur l'ordre :
        `Bucket$$AddAction` ne remplace que sur `>` STRICT, donc la PREMIERE cible de `fromHere`
        gagne. `eligible_units` preserve cet ordre natif (c'est sa raison d'etre)."""
        if not self.should_evaluate(ctx):
            return []                                   # gate AMONT : l'ability est SAUTEE
        util = self.evaluate_non_comparable(ctx.origin, None, ctx)
        if util is None or util < self.MIN_UTILITY:
            return []
        cibles = TGT.eligible_units(ctx, self.ABILITY_ID)
        if not cibles:
            return []
        tid = cibles[0][0]                              # keep-first : utilites toutes egales
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] RitesOfMorkai target=%s util=%s (%d cible(s) a egalite)"
                  % (ctx.uid, tid, util, len(cibles)), file=sys.stderr)
        return [{"target": tid, "ability": self.ABILITY_ID, "to": None, "pred": util}]


__all__ = ["RitesOfMorkaiPlaybook"]
