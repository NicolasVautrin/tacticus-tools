"""DoomboltPlaybook -- face DECISION de `1102 Doombolt` (`thousAhriman`). #978.

La face COMBAT est portee et confrontee de longue date
(`engine/runner/abilities/thousandsons.py`, case-psychic-aoe / #494 / #494-r1) ; c'est la face
DECISION qui manquait -- l'ability ne pouvait donc etre proposee par le moteur que par le fallback
Comparable, jamais par son playbook propre.

BASE, LUE dans `data/symbols/<build>/frida/classes.tsv` :
`IdunBattle.AI.Playbook.Loki.DoomboltPlaybook` -> `IdunBattle.AI.Playbook.NonComparablePlaybook`1`.
Le `.ctor` decompile NOMME `ComparablePlaybook<__Il2CppFullySharedGenericType>..ctor(this, 0x44e)`
-- corps gshared trivial DEDUPLIQUE, donc mislabele (piege #487-r1 / #945 / #957 / #967).

REACHABILITY, LUE dans `data/symbols/<build>/metadata/active_playbook_builders.tsv` :
`active 1102 -> ...DoomboltPlaybook`.
"""
from __future__ import annotations

import gameconfig as _gc
import hexgeo

from engine import battle_query as bq
from engine.ai import cast_positions as CP        # FORME B (liaison de MODULE) : carte
#                                                 position x cible, foyer #350-r3a-r4.
from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.active_ability_type import ActiveAbilityType

import engine.playbook.noncomparable._targets as TGT              # FORME B, ABSOLU (#962)
from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first


class DoomboltPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.DoomboltPlaybook$$EvaluateNonComparable` (0x44e = 1102).

    LE CORPS, TERME A TERME
    -----------------------
        bucket = new Bucket<UnitAction>( 0, Nullable(<statics+0x00>) )    # `.cctor` : Fix64(1)
        foreach entities in GetEligibleTargetsSelectable(caster, casterPosition.get_MainTile()):
            util = Fix64(0)
            n    = <DoomboltAbility>$$GetTargets(this.ability@+0x68)
                       .<ITargetsSelector slot 2 = Count>(entities)
            util = util + Fix64(n)
            bucket.AddAction( GenerateAction(casterPosition, entities.Target@+0x10, util) )

    Soit : **le nombre d'ennemis que le souffle frapperait**, et rien d'autre.

    ⚠ L'UTILITE NE DEPEND PAS DE LA CIBLE -- ET CE N'EST PAS UNE ERREUR DE LECTURE. Le selecteur
    `GetTargets()` est ancre sur le CASTER et sa TUILE, jamais sur `Target` :

        Damageable( Unobscured( caster@+0x48,
                                SurroundingEnemies(caster@+0x48, casterTile@+0x50,
                                                   ConfigConst(0x16 = range), unique: 1, 3) ) )

    (mirror deja etabli et confronte par la face COMBAT :
    `thousandsons.doombolt_targets_selector`). `Count(entities)` rend donc la MEME valeur pour
    toutes les cibles d'une meme position -- l'argmax est alors decide par `Bucket.AddAction`, qui
    ne remplace que sur `>` STRICT : **la PREMIERE cible enumeree gagne**, dans l'ordre du
    selecteur natif. C'est le sens inverse du piege de #957 (« l'arbre est bati hors boucle donc le
    terme est constant » -- faux la, vrai ici), et il se tranche par la LECTURE de l'ancrage, pas
    par la position de la construction dans le corps.

    ⚠ EN REVANCHE L'UTILITE DEPEND DE LA POSITION, et c'est tout le sel du playbook.
    `AbilityEntities.CasterTile` est ecrit par `BasePlaybook$$GetEligibleTargetsSelectable` avec la
    tuile CANDIDATE (`possibleCasterTile`, overload TUILE ici -- lu dans le corps de l'overload :
    `local_258 = possibleCasterTile`). Le generateur balayant les positions, Ahriman **se DEPLACE
    pour maximiser le nombre d'ennemis dans son rayon**. Un port qui n'evaluerait qu'a l'origine
    serait silencieusement plat.

    ⚠ QUIRK NATIF TRANSCRIT TEL QUEL : le DISQUE est ancre sur la tuile CANDIDATE
    (`casterTile@+0x50`) mais l'`Unobscured` est ancre sur le CASTER **ENTITE** (`caster@+0x48`),
    donc sur sa MainTile **REELLE** -- `SurroundingTilesSelector$$Select` part d'
    `EntityExtensions$$IterateTiles(unit)`, exactement le quirk que `battle_query.
    surrounding_enemies_in_range` documente pour `SavageEchoes` (#216). Les deux ancres coincident
    a l'origine ; elles divergent sur toute tuile de move. On ne les unifie PAS.

    `MIN_UTILITY = 1` : l'ability n'est pas proposee quand le rayon est vide -- ce que la face
    COMBAT dit deja d'un autre cote (`GetDynamicInvalidCasterReason` rend `TargetIsInRange` quand
    `GetTargets()` est VIDE).

    `GetUseProbability` EST SURCHARGEE, ET ELLE NE GATE RIEN
    --------------------------------------------------------
    `...DoomboltPlaybook$$GetUseProbability(unit)` :

        hits = NrOfHitsFormula().Calculate(<AbilityEntities memset a ZERO>)
        return Fix64( (int) Math.Round( (float) hits / 9.0 * 100.0 ) )

    C'est un POURCENTAGE (0..100), pas une probabilite dans [0,1]. Le consommateur
    `BasePlaybook$$ShouldEvaluate` teste `prob >= 1 -> True` : avec `nrOfHits = 3` (gameconfig)
    la valeur vaut `round(3/9*100) = 33`, donc **True de facon DETERMINISTE**. Le defaut
    `should_evaluate` de la base (True constant) est donc ICI un mirror EXACT, et non l'ecart
    « porte aleatoire non modelisee » que `_base` assume pour BlackRage/ItItches -- contraste avec
    `EmpyricAmbushPlaybook` de la meme tranche, dont le `GetUseProbability` vaut `0.5` et ouvre,
    lui, un vrai tirage. Ne rien porter est le bon geste ; le dire evite qu'on l'ajoute a tort.
    Le seul regime ou ce gate mordrait est `hits == 0`, impossible : `nrOfHits` est une constante
    de config `>= 1` et la formule y AJOUTE le nombre d'hexes en feu."""
    ABILITY_ID = int(ActiveAbilityType.Doombolt)        # 0x44e = 1102 (argument du ctor natif)
    MIN_UTILITY = 1.0     # `DoomboltPlaybook$$.cctor` : `FixMath.NET.Fix64.op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    #: `utility = Fix64(0)` POSE AVANT l'ajout -- aucun plancher (contraste 1209/1143).
    BASE_UTILITY = 0.0

    def _range(self) -> int:
        """`DSLFormulas.ConfigConst(0x16, config)` = `constants.range` du gameconfig.

        Meme lecture que la face COMBAT (`thousandsons.doombolt_targets_selector`), meme defaut
        `2`. La valeur n'est JAMAIS figee dans le code : elle est relue a chaque appel."""
        consts = (_gc.ability(ActiveAbilityType(self.ABILITY_ID).name) or {}).get("constants") or {}
        return int(consts.get(AbilityConstantType.range.name) or 2)

    def _count_targets(self, ctx: NCContext, tile: tuple) -> int:
        """`GetTargets().Count(entities)` avec `entities.CasterTile == tile`.

        Mirror terme a terme de `Damageable(Unobscured(SurroundingEnemies(caster, tile, range)))` :
          * **disque** `0 < dist <= range` autour de `tile` -- `SurroundingTiles(includeCenter: 1,
            range)` PUIS `- Tiles(caster)`, donc le centre est retire ;
          * **`Unobscured`** depuis la tuile **REELLE** du caster (`ctx.origin`), cf. le quirk
            ci-dessus. `battle_query.is_target_tile_obscured` ne repond QUE pour `dist == 2` (le
            seul regime que le natif exerce) : au-dela il rend `False`, donc le port ne retire
            RIEN -- borne SUPERIEURE assumee et nommee si un build montait `range` au-dessus de 2.
          * **`Damageable`** : `ctx.epos` est deja le canal des ennemis VIVANTS et ciblables du
            port ; le filtre `Damageable` (unites `Object`/non-attaquables) n'a pas de canal propre
            dans `NCContext` -- ecart NOMME, il ne peut que SUR-compter.
          * **`unique: 1`** : une position = une unite, la deduplication est structurelle offline.

        Le filtre de tuiles de `SurroundingTiles` (`TileUtil$$IsTileValidForList(tile, src, 1, 0)`
        = non-mur + walkable, SANS elevation ni occupation) est un no-op offline : une unite
        stationne forcement sur du walkable -- meme raisonnement que
        `battle_query.surrounding_enemies`."""
        rng = self._range()
        origin = ctx.origin
        n = 0
        for p in (ctx.epos or []):
            if not p or p[0] is None:
                continue
            pk = (p[0], p[1])
            d = hexgeo.distance((tile[0], tile[1]), pk)
            if d == 0 or d > rng:
                continue                          # `SurroundingTiles(range)` moins `Tiles(caster)`
            # `Unobscured(caster@+0x48, ...)` : ancre sur la tuile REELLE, PAS sur `tile`.
            if origin is not None and bq.is_target_tile_obscured(origin, pk, ctx.elev_by_pos):
                continue
            n += 1
        return n

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        # CIBLES : le selecteur natif (`GetValidTargets`, slot 66) -- la meme source que le foyer
        # `_targets.py`. On garde une LISTE, jamais un `set` : a utilite egale (le cas GENERAL
        # ici, l'utilite ne dependant pas de la cible) c'est la PREMIERE enumeree qui gagne, et un
        # `set` ferait decider le hachage (le second cran trouve par #957).
        elig = TGT.eligible_any(ctx, self.ABILITY_ID)
        if not elig:
            return []
        best = None                                    # (target, tile, util)
        for P in _sweep_origin_first(ctx) or ([ctx.origin] if ctx.origin else []):
            if P is None:
                continue
            util = self.BASE_UTILITY + self._count_targets(ctx, P)
            if util < self.MIN_UTILITY:
                continue                               # gate Bucket `util >= min`
            for tid, _pos, _kind in elig:
                if tid is None:
                    continue
                # La paire (ability, cible) est-elle castable DEPUIS `P` ? `positions_castables`
                # est le foyer #350-r3a-r4 (`castFromTiles` = `GetInvalidTargetReason` tuile par
                # tuile, SANS troncature). `ev = {}` -> `ranked` vide, donc un canal muet rend un
                # ensemble VIDE et la cible est ignoree a cette position : degradation
                # CONSERVATRICE, jamais un cast illegal propose.
                if P != ctx.origin:
                    ok = CP.positions_castables({}, getattr(ctx, "cast_from_tiles", None),
                                                ctx.uid, tid, self.ABILITY_ID, ctx.origin)
                    if P not in ok:
                        continue
                if best is None or util > best[2]:     # strict > : 1re position/cible du max gagne
                    best = (tid, P, util)
                break                                  # utilite CONSTANTE sur les cibles ->
                #                                        `AddAction` garde la 1re a cette position
        if best is None:
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] Doombolt target=%s tile=%s util=%s"
                  % (ctx.uid, best[0], best[1], best[2]), file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID,
                 "to": (best[1] if best[1] != ctx.origin else None), "pred": best[2]}]
