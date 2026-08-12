"""DeathFromAbovePlaybook -- face DECISION de `1003 DeathFromAbove` (`ultraInceptorSgt`). #969."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from . import _targets as T
from ._base import NCContext, NonComparablePlaybook


class DeathFromAbovePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.DeathFromAbovePlaybook` -- MIRROR du decompile.

    ⚠ **BASE `NonComparablePlaybook`1`, LUE dans `frida/classes.tsv`** ; le `.ctor` decompile en
    `ComparablePlaybook<...>..ctor(this, 0x3eb)` (corps gshared DEDUPLIQUE). `0x3eb = 1003`.

    `...DeathFromAbovePlaybook$$.cctor` : `<statique +0x00> = Fix64.op_Implicit(1)`
    -> `MIN_UTILITY = 1`.

    `...DeathFromAbovePlaybook$$EvaluateNonComparable(caster, casterPosition, abilityState)` :

        bucket = new Bucket<UnitAction>( priority: 0, minUtility: Nullable(<statique> = 1) );
        foreach (var e in BasePlaybook$$GetEligibleTargetsSelectable(this, caster,
                                                                     casterPosition.MainTile))
        {
            int n = this.GetNumPossibleSpawnTilesForTarget(e.Target);
            bucket.AddAction( BasePlaybook$$GenerateAction(this, casterPosition, e.Target,
                                                           Fix64.op_Implicit(n)) );
        }
        return bucket;

    => **utilite = nombre de tuiles OU UN INCEPTOR PEUT ATTERRIR autour de la cible**. Aucun gate
    `n > 0` dans le corps -- contrairement a `BioMinefieldPlaybook` : c'est `MIN_UTILITY = 1` qui
    ecarte les cibles a zero tuile, et le port reproduit CETTE forme-la (le compte est admis tel
    quel, le seuil fait le reste).

    `...DeathFromAbovePlaybook$$GetNumPossibleSpawnTilesForTarget(target)` :

        var sel = <l'arbre de DeathFromAboveAbility$$GetPossibleSpawnTiles>(
                      DSLSelectors$$Entity(<this.+0x18>.+0x90, target) );
        return sel.<ITargetsSelector slot 2 = Count>( default(AbilityEntities) );

    ⚠ **LE CORPS APPELE EST NOMME `SpawnTermagantsAbility$$<ExecuteBehaviour>b__1_0` PAR GHIDRA** --
    fusion ICF : deux constructeurs d'arbre identiques partagent un corps, et la table n'en garde
    qu'UN proprietaire. L'appelant est `DeathFromAbovePlaybook`, l'arbre est celui de `1003`, deja
    porte cote COMBAT (`engine.runner.abilities.ultramarines._dfa_spawn_tiles` :
    `AdjacentTiles(Target) -> CanAddUnit -> SortByDistance(caster)`). Se fier au NOM aurait fait
    porter le selecteur des Termagants.

    ⚠ **LE CONTEXTE PASSE A `Count` EST VIDE** (`memset(entities, 0, 0x128)` juste avant l'appel).
    C'est LU, pas suppose, et c'est inoffensif : `Count` ne consomme ni `Caster` ni `Owner` -- seul
    le `SortByDistance(caster)` en aurait besoin, et un tri ne change pas un cardinal. La cible,
    elle, n'est PAS dans ce contexte : elle est bakee dans le selecteur par `DSLSelectors$$Entity`,
    reconstruit A CHAQUE CIBLE. Le terme n'est donc pas constant sur les cibles, malgre un
    `AbilityEntities` hisse hors de la boucle -- c'est exactement le piege de #957/#967, et il se
    tranche ici par le SLOT (`ITargetsSelector 2 Count 1`, LU dans `metadata/interface_slots.tsv`),
    pas par la position du constructeur.

    `...DeathFromAbovePlaybook$$ShouldEvaluate(unit)` -- SURCHARGE DIRECTE du slot 4 (le playbook
    ne passe donc PAS par `BasePlaybook$$ShouldEvaluate`) :

        var target = this.GetBestTarget(unit);              // corps INLINE dans ShouldEvaluate
        if (target == null) return false;
        int n = this.GetNumSummons(unit, target);
        var prob = (n < 1) ? Fix64.op_Implicit(0)
                           : Fix64.FromIntFraction(15, 100) * Fix64.op_Implicit(n)
                             + <pct>(100 - UnitExtensions$$GetStat(unit, 5 = Health,
                                                                   1 = StatPart.CurrentPct, null));
        return this.<+0x30>.<slot 4>(prob);                 // tirage RNG

    `...DeathFromAbovePlaybook$$GetBestTarget(unit)` : argmax de
    `GetNumPossibleSpawnTilesForTarget` sur `<IBattleQuery slot 69>
    .GetAllValidTargetsFromAllPossibleMovementTiles(unit, this.<+0x10> = 1003, null)` -- donc sur
    l'UNION des tuiles de move, la ou `EvaluateNonComparable` enumere PAR POSITION. Remplacement sur
    `>` STRICT : keep-first a egalite.

    `...DeathFromAbovePlaybook$$GetNumSummons(unit, target)` :
    `Math.Min( DeathFromAboveAbility$$GetNumSummons(ability).Calculate(entities{Owner = unit}),
               GetNumPossibleSpawnTilesForTarget(target) )` -- soit
    `min(StatAmount(caster, 12 = TURNS_STARTED), tuiles libres autour de la cible)`. Le `Calculate`
    est `IAmountFormula` slot 1 (LU dans `metadata/interface_slots.tsv`).

    CE QUE `should_evaluate` REND : le refus DETERMINISTE `prob <= 0`, c'est-a-dire
    `GetBestTarget == null` OU `numSummons < 1`. Le terme `0.15 x n + PVmanquants%` est strictement
    positif des que `n >= 1`, donc il ne peut produire aucun autre refus ; il n'entre que dans le
    TIRAGE, que le moteur deterministe ne modelise pas (ecart assume, cf.
    `NonComparablePlaybook.should_evaluate`). Le porter serait du code mort.

    `PRIORITY` reste au defaut `0` (`AbilityPriority.Normal`) : `1003` est ABSENTE de
    `NATIVE_PRIORITY` (22 entrees, sweep #170).

    ⚠ **UTILITE POSITION-INDEPENDANTE -> LE CASTER NE BOUGE PAS** : ni le compte de tuiles ni la
    cible ne dependent de `casterPosition`. Le balayage natif met l'ORIGINE en tete et
    `Bucket$$AddAction` ne remplace que sur un STRICTEMENT superieur -> `to = None` (meme raison que
    `BioMinefieldPlaybook` / `GetEmRuntzPlaybook`)."""
    ABILITY_ID = int(ActiveAbilityType.DeathFromAbove)   # 1003 = 0x3eb (argument du ctor natif)
    MIN_UTILITY = 1.0                                    # `...DeathFromAbovePlaybook$$.cctor`

    @staticmethod
    def _spawn_tiles(ctx: NCContext, pos: tuple) -> int:
        """`GetNumPossibleSpawnTilesForTarget(target)` = `|CanAddUnit(AdjacentTiles(target))|`.

        DELEGUE au foyer `engine.battle_query.adjacent_addable_count`, celui-la meme qui sert
        `HammerOfWrathPlaybook` (#116) et `ScarabHivePlaybook` : voisins ring-1 de la liste
        d'adjacence STOCKEE du board (avec la porte d'elevation `|dElev| < 2`), filtres par
        `CanAddUnit` (marchable, non occupe). Aucune geometrie recalculee ici.

        Canaux `neigh_by_pos` / `walkable_by_pos` / `elev_by_pos` vides -> le foyer degrade seul
        vers `hexgeo.neighbors` ; c'est la degradation PERMISSIVE deja documentee sur `NCContext`,
        jamais un zero fabrique."""
        occupied = set(ctx.epos or ()) | set(ctx.fpos or ())
        if ctx.origin is not None:
            occupied.add(ctx.origin)
        return bq.adjacent_addable_count(pos, getattr(ctx, "neigh_by_pos", None),
                                         getattr(ctx, "walkable_by_pos", None), occupied,
                                         ctx.elev_by_pos)

    def _best_target_tiles(self, ctx: NCContext) -> int | None:
        """`GetNumPossibleSpawnTilesForTarget(GetBestTarget(unit))` -- le MAX sur l'UNION des cibles
        atteignables depuis toutes les tuiles de move (slot 69, pas `fromHere`).

        `None` = PAS MESURE (RPC muet) ; `0` = mesure et aucune tuile. Les deux ne se confondent
        pas : le premier ne doit pas faire refuser."""
        if ctx.ability_targets is None:
            return None
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        pos_by_id = {u.get("id"): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
                     for u in (ctx.units or []) if u.get("id") is not None and u.get("pos")}
        best = 0
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):     # UNION = slot 69, l'entree de GetBestTarget
                    src = t.get("pos") or t.get("tile") or {}
                    p = ((src.get("col"), src.get("row")) if src.get("col") is not None
                         else pos_by_id.get(t.get("targetId")))
                    if not p or p[0] is None:
                        continue
                    n = self._spawn_tiles(ctx, tuple(p))
                    if n > best:                        # `>` STRICT, keep-first (mirror du natif)
                        best = n
        return best

    def should_evaluate(self, ctx: NCContext) -> bool:
        """Surcharge DIRECTE du slot 4 : `GetBestTarget == null` ou `GetNumSummons < 1` -> False.

        `GetNumSummons = min(turnsStarted(caster), spawnTiles(bestTarget))`, donc le refus se lit
        `turnsStarted < 1 or spawnTiles(best) < 1`. Canal muet (`scene` absente, RPC absent) ->
        `True` : un `False` a l'aveugle rendrait l'ability INVISIBLE du moteur, le trou silencieux
        de #967."""
        best = self._best_target_tiles(ctx)
        if best is not None and best < 1:
            return False                                # GetBestTarget == null, ou 0 tuile libre
        if ctx.scene is not None:
            ts = ctx.scene.turns_started(ctx.uid)       # StatAmount(caster, 12 = TURNS_STARTED)
            if ts is not None and ts < 1:
                return False                            # min(...) < 1 -> prob = 0
        return True

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        best = None
        # ORDRE NATIF de `GetEligibleTargetsSelectable` = la vue `fromHere` (liste, jamais un set :
        # a utilite egale c'est la PREMIERE cible enumeree que `Bucket$$AddAction` garde).
        for tid, pos in T.eligible_units(ctx, self.ABILITY_ID):
            if pos is None:
                continue
            util = float(self._spawn_tiles(ctx, tuple(pos)))
            if util < self.MIN_UTILITY:                 # admission `Bucket$$AddAction` (util >= min)
                continue
            if best is None or util > best["pred"]:     # `>` STRICT -> keep-first
                best = {"target": tid, "ability": self.ABILITY_ID, "to": None, "pred": util}
        return [best] if best is not None else []
