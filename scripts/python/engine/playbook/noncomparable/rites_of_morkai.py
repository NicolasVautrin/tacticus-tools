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

    def _amis_pour_le_gate(self, ctx: NCContext, pos: tuple) -> list:
        """Les positions AMIES que `GetAdjacentUnits(pos, friendsOf: null)` peut rendre, du point
        de vue du gate -- `ctx.fpos` **PLUS LE CASTER LUI-MEME** quand `pos` n'est pas sa position.

        ⚠ C'EST LA LECTURE QUI A ETE TROUVEE PAR LA CONFRONTATION, ET ELLE EST CONTRE-INTUITIVE.
        Le gate est evalue AVANT tout deplacement : quand le generateur teste une position de MOVE
        `P`, le caster occupe encore son ORIGINE. Si `P` est adjacente a l'origine -- ce qui est le
        cas de tout le ring-1 de move -- alors `GetAdjacentUnits(P)` contient LE CASTER, et
        `<ShouldEvaluate>b__0` = `UnitExtensions.IsFriend(caster, caster, state)` est VRAI.
        La clause << au moins un ami adjacent >> est donc satisfaite PAR LE CASTER SEUL sur toute
        position de move voisine.

        MESURE qui l'etablit (regime E de `probe_1066_rites_of_morkai_decision_live.py`) : caster
        en `(3,4)`, allies en `(0,0)` et `(6,0)`, un ennemi en `(3,5)`. AUCUNE position candidate
        n'a d'ami au sens `fpos`, et pourtant `aiDryRunAllUnits` propose `MoveUnitMessage -> (4,4)`
        puis `ActiveAbilityMessage(1211)`. La seule unite amie adjacente a `(4,4)` est le caster
        lui-meme, reste en `(3,4)`.

        ⚠ Ne PAS confondre avec le COMPTE : celui-la porte le predicat EXPLICITE
        `<EvaluateNonComparable>b__0` = `f != caster`, donc le caster s'y exclut. Les deux
        lectures cohabitent dans le meme corps natif, et les melanger donne un port faux dans un
        sens ou dans l'autre."""
        amis = list(ctx.fpos or [])
        if ctx.origin is not None and (pos[0], pos[1]) != (ctx.origin[0], ctx.origin[1]):
            amis.append(ctx.origin)
        return amis

    def should_evaluate_at(self, ctx: NCContext, pos: tuple) -> bool:
        """`RitesOfMorkaiPlaybook$$ShouldEvaluate(unit, position, possiblePositions)` -- `IPlaybook`
        slot **6** (arite 3), LU dans `metadata/interface_slots.tsv` :

            adj = battleQuery.<slot 123 GetAdjacentUnits>(position, null, false, ...)
            return adj.Any(u => IsFriend(u, unit)) ? adj.Any(u => IsEnemy(u, unit)) : false

        ⚠ CE GATE EST PAR POSITION, PAS PAR UNITE. `ActiveAbilityActionGenerator.
        <GenerateActions>d__7$$MoveNext` appelle le slot 4 (arite 1) puis le slot 5 (arite 2) UNE
        FOIS chacun, puis ENTRE dans la boucle des positions candidates et y appelle le slot 6, le
        slot 64 `HasValidTargets` et le slot 7 `Evaluate` -- les buckets par position etant
        ensuite MERGES. Porter ce gate dans le `should_evaluate()` sans position (slot 4 de la
        classe de base) le rendrait BEAUCOUP trop strict : il refuserait a l'origine des cas que
        le natif accepte depuis une tuile de move.

        `possiblePositions` n'est PAS lu par le corps -- il figure dans la signature du slot, pas
        dans les instructions."""
        if pos is None:
            return False
        neigh = bq.neigh_map(ctx)
        elev = ctx.elev_by_pos
        amis = bq.count_adjacent(pos, self._amis_pour_le_gate(ctx, pos), elev, neigh)
        ennemis = bq.count_adjacent(pos, ctx.epos, elev, neigh)
        return amis > 0 and ennemis > 0

    def should_evaluate(self, ctx: NCContext) -> bool:
        """Slot 4 (arite 1) -- `BasePlaybook$$ShouldEvaluate(unit)`, que 1211 ne surcharge PAS.

        Le gate propre a 1211 est le slot 6, PAR POSITION (`should_evaluate_at`) : le poser ici
        reviendrait a refuser l'ability avant meme le sweep. Rendre `True` est donc le mirror,
        pas une permissivite."""
        return True

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
        """Mirror de `ActiveAbilityActionGenerator.<GenerateActions>d__7$$MoveNext` pour 1211 :
        SWEEP DES POSITIONS candidates, gate slot 6 par position, puis `Evaluate`, buckets MERGES
        et `Bucket$$ChooseAction` en argmax STRICT.

        L'ordre balaye est `ctx.reach_nc` -- ORIGINE EN TETE puis les tuiles de move
        (`ABaseAiUnitTactic$$GenerateActionTiles`). `AddAction`/`Merge` ne remplacent que sur `>`
        STRICT, donc a utilite egale le natif RESTE SUR PLACE : le keep-first sur cet ordre est le
        mirror, pas une commodite.

        ⚠ L'utilite etant la MEME pour toutes les CIBLES a une position donnee, la cible se resout
        elle aussi par keep-first, sur l'ordre de `fromHere` (`eligible_units`).

        ⚠ ECART NOMME : `eligible_units` ne connait les cibles que depuis l'ORIGINE (`fromHere`).
        Pour une position de move, le port reutilise cette liste faute de vue par-position cote
        RPC ; `HasValidTargets(unit, position, ability)` (slot 64), que le natif interpose, n'a pas
        d'equivalent offline. Le masque de 1211 etant SELF-CAST (la mesure live rend `targetId ==
        casterId` dans les quatre regimes passants), l'ecart est inerte ici : la cible ne depend
        pas de la position."""
        positions = list(ctx.reach_nc or ([ctx.origin] if ctx.origin is not None else []))
        cibles = TGT.eligible_units(ctx, self.ABILITY_ID)
        if not positions or not cibles:
            return []
        best = None                                     # (position, utilite)
        for p in positions:
            if p is None or not self.should_evaluate_at(ctx, p):
                continue                                # gate slot 6, PAR POSITION
            util = self.evaluate_non_comparable(p, None, ctx)
            if util is None or util < self.MIN_UTILITY:
                continue                                # gate `minUtility` du `Bucket`
            if best is None or util > best[1]:          # STRICT -> keep-first au tie
                best = (p, util)
        if best is None:
            return []
        pos, util = best
        tid = cibles[0][0]                              # keep-first : utilites toutes egales
        to = None if (ctx.origin is not None
                      and (pos[0], pos[1]) == (ctx.origin[0], ctx.origin[1])) else pos
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] RitesOfMorkai target=%s util=%s depuis %s (to=%s)"
                  % (ctx.uid, tid, util, pos, to), file=sys.stderr)
        return [{"target": tid, "ability": self.ABILITY_ID, "to": to, "pred": util}]


__all__ = ["RitesOfMorkaiPlaybook"]
