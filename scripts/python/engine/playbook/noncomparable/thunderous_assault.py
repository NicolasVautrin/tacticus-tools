"""`ThunderousAssaultPlaybook` (1043, `templSwordBrother` « Sword Brother », Black Templars) -- #977.

C'est le SEUL playbook porte a ce jour qui passe par
`IdunBattle.AI.Playbook.NonComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateBucketWithMultipleStrategies`,
et cette voie change TROIS choses par rapport au patron `EvaluateNonComparable` ordinaire.

## 1. Le Bucket n'a AUCUN seuil -- `MIN_UTILITY = -inf`, pas `0.0`

    IdunBattle.AI.Playbook.Loki.ThunderousAssaultPlaybook$$EvaluateNonComparable(caster, casterPosition):
        strategies = new List<Strategy> {
            new Strategy(<lambda b__1_0>,           order = 2),
            new Strategy(this.GenerateStrategy2Action, order = 1),
        };
        return GenerateBucketWithMultipleStrategies(strategies, caster, casterPosition);

    NonComparablePlaybook<T>$$GenerateBucketWithMultipleStrategies(strategies, caster, casterPos):
        bucket = new Bucket();                       // ctor a UN argument -> pas de minUtility
        foreach (s in strategies) {
            action = s.func(caster, casterPos.MainTile);
            if (action != null) { bucket.AddActionToBucket(s.order, action); break; }
        }
        return bucket;

`IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$.ctor` a DEUX
surcharges : celle a trois arguments ecrit `this+0x10..0x18 = Nullable<Fix64> minUtility`, celle a
un seul argument ne l'ecrit PAS -> `minUtility.HasValue == false`. Et `ThunderousAssaultPlaybook`
n'a **aucun `.cctor`** (recherche de symboles : ses seuls membres sont `.ctor`,
`EvaluateNonComparable`, `GenerateStrategy2Action`, `GetHighestTileUtilityUnitCanMoveTo`,
`GetPushableTargetOnHighestUtilityTile`, `GetTargetIfWillPush`, `<EvaluateNonComparable>b__1_0`).
Le defaut `MIN_UTILITY = 0.0` de la classe de base Python AURAIT donc TUE ce playbook en silence :
son utilite est un ECART d'utilite de tuile, qui vaut **0 sur tout plateau plat**.

## 2. La PREMIERE strategie qui rend une action non nulle GAGNE -- ce n'est pas un argmax

Le `break` du corps ci-dessus est le `while (local_68 == 0)` du decompile : la boucle continue TANT
QUE l'action est nulle. La strategie 2 n'est donc evaluee QUE si la strategie 1 a rendu `null`.
L'`order` (2 puis 1) ne sert qu'a choisir le SOUS-bucket de `AddActionToBucket` ; avec une seule
action ajoutee, `Bucket$$ChooseAction` -> `ChooseActionFromBuckets` la rend quel que soit ce rang.
Le port ne modelise donc pas l'`order` : il serait INERTE, et l'ecrire ferait croire l'inverse.

## 3. Les deux strategies

### Strategie 1 (`<EvaluateNonComparable>b__1_0`) -- « pousser la cible vers une PIRE tuile »

    r = Playbook<T>$$GetTargetWithBiggestUtilityDiffOnDisplace(unit, tile, this.GetPushableTiles);
    return r == null ? null : GenerateAction(tile, r.Target, r.Value);

    Playbook<T>$$GetTargetWithBiggestUtilityDiffOnDisplace(unit, tile, tilesFunc):
        best = null;
        foreach (t in BasePlaybook$$GetEligibleTargetsEntities(unit, tile)) {
            r = GetTargetUtilityDiffOnDisplace(unit, tile, tilesFunc, t);   // (t, diff)
            if (r.Value > Fix64(0) && (best == null || r.Value > best.Value)) best = r;
        }
        return best;

`GetTargetUtilityDiffOnDisplace` est le corps GENERIQUE deja porte (foyer
`playbook/displace_utility.py`, partage avec `1004 MortisRound`) : le MAX sur l'arc arriere de
`Tile(7)@tuileCourante(cible) - Tile(7)@tuileDePush`, evalue AVEC LE KIT DE LA CIBLE, gate a `> 0`.
Ici la valeur est consommee BRUTE -- la troncature vers `int` appartient a
`MortisRoundPlaybook$$CalculateCustomUtility`, pas au corps generique.

### Strategie 2 (`GenerateStrategy2Action`) -- « voler la MEILLEURE tuile a l'ennemi »

    GenerateStrategy2Action(unit, actionTile):
        highest = GetHighestTileUtilityUnitCanMoveTo(unit);
        r       = GetPushableTargetOnHighestUtilityTile(unit, actionTile);
        if (r != null && r.Value >= highest)
            return GenerateAction(actionTile, r.Target, r.Value);
        return null;

    GetHighestTileUtilityUnitCanMoveTo(unit):
        best = Fix64(0);
        // slot itf `0x0b` = `GetMovableTilesFor` -- RESOLU (#977-r1), pas suppose : le movable
        // SEUL, sans la position courante (c'est `0x0e` qui la seed). Les elements sont des
        // TUILES, donc aucun `.MainTile` n'est applique.
        foreach (t in battleQuery.GetMovableTilesFor(unit, ignoreFlags: false, options: default))
            best = max(best, GetUtility(Tile).EvaluateAttack(
                                 UtilityAttackCase.Base(unit, t, t, aoe)));
        return best;                                   // strict `>`, plancher Fix64(0)

    GetPushableTargetOnHighestUtilityTile(unit, actionTile):
        best = null;
        foreach (t in battleQuery.<slot itf 0x42 = GetValidTargets>(
                          unit, UnitPosition(actionTile), 0x413).AllTargets) {
            if (Playbook<T>$$GetPushableTiles(actionTile, t).Count < 1) continue;
            tt = EntityExtensions$$GetMainTile(t);
            v  = GetUtility(Tile).EvaluateAttack(UtilityAttackCase.Base(unit, tt, tt, aoe));
            if (best == null || v > best.Value) best = (t, v);
        }
        return best;

⚠ **L'UNITE du `UtilityAttackCase` n'est PAS la meme dans les deux strategies, et c'est le piege**
de ce playbook. Strategie 1 : `UtilityAttackCase.Base(**target**, ...)` -- on mesure ce que la
CIBLE perd. Strategie 2 : `UtilityAttackCase.Base(**unit** = le caster, tuile de la cible)` -- on
mesure ce que le CASTER gagnerait a occuper cette tuile. Le port passe donc par
`base.tile_utility_for_unit` d'un cote et `base.tile_utility` de l'autre, et ce n'est pas une
commodite : les feuilles Tile(7) recopient le champ `unit` du case dans
`UtilityMovementCase+0x10` avant de le passer a `HasTrait(case.unit, ...)` / `HasFaction(...)` et
aux comptes d'adjacence.

## Le `MIN_UTILITY = -inf` est FIDELE, mais INDISCERNABLE du defaut -- mesure #977-r4

`-inf` est le mirror exact du `Bucket<T>..ctor` a UN argument. Mais l'affirmation « le defaut
`0.0` aurait TUE ce playbook en silence » est **FAUSSE**, et elle l'etait deja quand elle a ete
ecrite : le gate du port est `if util < MIN_UTILITY: return None`, donc STRICT -- une utilite
`0.0` passe les DEUX seuils. Le natif est identique (`Bucket$$AddAction` admet `util >= min`).

Les deux valeurs ne divergent que pour `util < 0`, et ce regime est **INATTEIGNABLE** : la
strategie 1 gate chaque cible a `diff > 0`, et la strategie 2 n'emet que si
`r.Value >= highest`, ou `highest` part de `Fix64(0)` et ne fait que croitre. Toute action de ce
playbook porte donc `util >= 0`.

⇒ `MIN_UTILITY` reste `-inf` **par FIDELITE**, pas parce qu'un montage l'exigerait ; et le
regime que `#977-r4` cherchait a exercer n'existe pas. Garde : `test_977r4_min_utility_offline.py`.

## Ce que le port NE tranche PAS (residus nommes)

* **`GetTargetIfWillPush`** est un membre de la classe qu'AUCUN des deux corps ci-dessus n'appelle
  (relu : `b__1_0` construit son delegue sur `GetPushableTiles`, dont la signature a DEUX arguments
  correspond a l'invocation de `GetTargetUtilityDiffOnDisplace` ; `GetTargetIfWillPush` en a
  TROIS). Il est cite ici pour que sa non-utilisation soit une LECTURE, pas un oubli.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType
# Forme B ABSOLUE (pas `from engine.playbook import X`, qui passerait a travers le paquet et
# refermerait le SCC `engine.playbook.__init__ -> noncomparable -> ...`) : une seule arete, et la
# liaison de module reste patchable.
import engine.playbook.displace_utility as _displace
import engine.playbook.base as _pbbase

from ._base import NCContext, NonComparablePlaybook
# Forme B : un import from ._targets import <nom> GELERAIT la liaison au chargement -- une contre-epreuve
# qui substitue le foyer deviendrait MUETTE, en silence (mesure #977 : deux mutations d'ordre
# n'ont RIEN mordu tant que cet import etait en forme A).
import engine.playbook.noncomparable._targets as _T

#: `Bucket<T>..ctor` a UN argument -> `minUtility.HasValue == false` -> aucun seuil d'admission.
#: Le defaut `0.0` de `NonComparablePlaybook` tuerait ce playbook (son utilite vaut 0 sur plat).
_NO_MIN_UTILITY = float("-inf")


class ThunderousAssaultPlaybook(NonComparablePlaybook):
    """1043 -- deux strategies, la premiere non nulle gagne. Cf. l'en-tete du module pour la RE."""

    ABILITY_ID = int(ActiveAbilityType.ThunderousAssault)   # 1043 = 0x413
    MIN_UTILITY = _NO_MIN_UTILITY
    PRIORITY = 0          # 1043 hors `NATIVE_PRIORITY` (sweep exhaustif #170) -> AbilityPriority.Normal

    # ---- strategie 1 : `<EvaluateNonComparable>b__1_0` (order 2) ---------------------------------
    def strategy1(self, ctx: NCContext, P: tuple):
        """`GetTargetWithBiggestUtilityDiffOnDisplace(unit, P, this.GetPushableTiles)` ->
        `(target, diff)` ou `None`. Argmax STRICT sur `diff`, gate `diff > 0` PAR CIBLE (une cible a
        `diff == 0` n'entre jamais dans `best`, meme si aucune autre ne la depasse)."""
        best = None
        for tgt, _tpos in _T.eligible_units_at_position(ctx, self.ABILITY_ID, P):
            diff = _displace.target_utility_diff_on_displace(ctx, P, tgt)
            if diff > 0.0 and (best is None or diff > best[1]):
                best = (tgt, diff)
        return best

    # ---- strategie 2 : `GenerateStrategy2Action` (order 1) ---------------------------------------
    def highest_tile_utility_unit_can_move_to(self, ctx: NCContext) -> float:
        """`GetHighestTileUtilityUnitCanMoveTo(unit)` = max de `Tile(7)` sur les tuiles de MOVE du
        CASTER -- **l'ORIGINE EXCLUE** -- plancher `Fix64(0)` (le seed), comparaison STRICTE.

        SUBSTRAT, TRANCHE (#977-r1). Le slot d'interface est RESOLU, plus suppose :
        `IBattleQuery` slot **`0x0b` = `GetMovableTilesFor`** (3 parametres), mesure au runtime par
        le RPC `interfaceSlotProbe` sur `IdunBattle.Core.Services.IBattleQuery` -- table CALEE par
        trois ancres concordantes (`0x0d = GetMovablePositionsFor`,
        `0x0e = GetCurrentAndMovablePositionsFor`, `0x40 = HasValidTargets`, `0x42 = GetValidTargets`).
        Le corps le confirme : `GetHighestTileUtilityUnitCanMoveTo` invoque ce slot avec
        `(unit, ignoreFlags: 0, options: default)` -- 48 octets a zero -- puis evalue
        `UtilityAttackCase.Base(unit, tile, tile, aoe)` sur CHAQUE element, SANS `.MainTile` (les
        elements SONT deja des tuiles, d'ou le nom `...TilesFor`).

        C'est donc le movable SEUL. `ctx.reach_nc` (slot `0x0e`,
        `GetCurrentAndMovablePositionsFor`) y ajoute la position COURANTE en tete -- ce seed est
        precisement ce qui distingue les deux slots. L'inclure faisait rendre un `highest` >= au
        vrai, donc rendait la strategie 2 (`r.Value >= highest`) trop SEVERE : elle refusait des
        actions que le natif emet, des que l'ORIGINE portait strictement la plus haute utilite de
        tuile de l'univers atteignable.

        BORNE NOMMEE, qui reste : `GetMovableTilesFor` rend des TUILES et `GetMovablePositionsFor`
        des `UnitPosition` (footprint). Le port ne modelise qu'une tuile par unite -- exact pour
        toute unite mono-tuile, ce que sont toutes celles du pool."""
        best = 0.0
        for p in (ctx.reach_nc or []):
            if ctx.origin is not None and p == ctx.origin:
                continue                      # slot 0x0b : l'ORIGINE n'est pas dans le movable
            v = _pbbase.tile_utility(ctx, p)
            if v > best:
                best = v
        return best

    def pushable_target_on_highest_utility_tile(self, ctx: NCContext, P: tuple):
        """`GetPushableTargetOnHighestUtilityTile(unit, actionTile)` -> `(target, tileUtility)` ou
        `None`. Parmi les cibles legales DEPUIS `P` qui sont effectivement poussables (arc arriere
        non vide), celle dont la tuile COURANTE porte la plus haute `Tile(7)` -- evaluee du point de
        vue du CASTER (`UtilityAttackCase.Base(unit, ...)`), pas de la cible. Argmax STRICT."""
        best = None
        for tgt, tpos in _T.eligible_units_at_position(ctx, self.ABILITY_ID, P):
            if tpos is None:
                continue
            if len(_displace.pushable_tiles(ctx, P, tgt)) < 1:
                continue
            v = _pbbase.tile_utility(ctx, tpos)
            if best is None or v > best[1]:
                best = (tgt, v)
        return best

    def strategy2(self, ctx: NCContext, P: tuple):
        """`GenerateStrategy2Action(unit, actionTile)` : la meilleure cible poussable, admise
        seulement si son utilite de tuile est `>=` (comparaison NON stricte) la meilleure utilite de
        tuile que le caster pourrait atteindre en bougeant."""
        highest = self.highest_tile_utility_unit_can_move_to(ctx)
        r = self.pushable_target_on_highest_utility_tile(ctx, P)
        if r is not None and r[1] >= highest:
            return r
        return None

    def evaluate_at(self, ctx: NCContext, P: tuple):
        """`EvaluateNonComparable(caster, UnitPosition(P))` -> `(target, util)` ou `None` -- la
        PREMIERE strategie non nulle, jamais un argmax entre les deux (`break` natif).

        C'est l'unite de mesure de l'oracle `ncEvaluate`, qui invoque exactement ce corps par
        position. `MIN_UTILITY` vaut `-inf` : le test est ecrit pour que le lecteur voie qu'il
        n'est JAMAIS franchi, pas parce qu'un seuil existe."""
        r = self.strategy1(ctx, P)
        if r is None:
            r = self.strategy2(ctx, P)        # `break` natif : la 2e ne tire que si la 1re rend null
        if r is None:
            return None
        util = float(r[1])
        if util < self.MIN_UTILITY:           # `-inf` : jamais franchi (aucun seuil natif)
            return None
        return (r[0], util)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """Le generateur natif balaie les positions (`<GenerateActions>d__7`) et fusionne les
        Buckets ; PAR position, `EvaluateNonComparable` prend la PREMIERE strategie non nulle. Le
        `Bucket` externe garde-first sur `>` STRICT -> a utilite egale, la premiere position de
        `ctx.reach_nc` (l'ORIGINE) gagne."""
        best = None       # (target, tile, util)
        for P in (ctx.reach_nc or []):            # ORIGINE en tete puis moves (ordre natif)
            r = self.evaluate_at(ctx, P)
            if r is None:
                continue
            if best is None or r[1] > best[2]:    # strict > : premiere position du max gagne
                best = (r[0], P, r[1])
        if best is None:
            return []
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] ThunderousAssault pos={best[1]} tgt={best[0]} "
                  f"u={best[2]}", file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID,
                 "to": (best[1] if best[1] != ctx.origin else None), "pred": best[2]}]
