"""HellfyreMissileRackPlaybook -- utilite CONSTANTE = nb d'ennemis ayant pris du Psychic ce tour."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.damage_profile_type import DamageProfileType

from ._base import NCContext, NonComparablePlaybook, native_priority


class HellfyreMissileRackPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.HellfyreMissileRackPlaybook$$EvaluateNonComparable` (id 0x440 =
    1088). Face DECISION de l'ability portee cote COMBAT par #487.

    Corps natif, remis en C# :

        bucket  = new Bucket(0, Nullable<Fix64>(<statique du .cctor> = Fix64(1)))
        ownerId = EntityExtensions.GetCurrentOwnerEntityId(caster)
        utility = Fix64( Sum( Select( battleQuery.<slot itf 0x8e = GetAllEnemiesOf>(ownerId),
                                      u => UnitExtensions.HasTakenDamageOfDamageProfileThisTurn(
                                               u, DamageProfileType.Psychic) ? 1 : 0 ) ) )
        foreach (t in BasePlaybook.GetEligibleTargetsSelectable(this, caster,
                                                               casterPosition.MainTile))
            bucket.AddAction( BasePlaybook.GenerateAction(this, casterPosition, t, utility) )

    L'utilite ne depend NI de la cible NI de la position : elle est calculee UNE fois, avant la
    boucle, et la MEME valeur est passee a chaque `GenerateAction`. `Bucket.AddAction` gate a
    `>= MIN_UTILITY` puis ne remplace que sur `>` STRICT -> a utilite plate, la PREMIERE paire
    (position, cible) enumeree gagne, c.-a-d. l'ORIGINE (`GetCurrentAndMovablePositionsFor` seede
    l'`OrderedSet` avec la position courante) et sa premiere cible `fromHere`. MEME forme que
    `GrapnelLauncherPlaybook`, dont ce module reprend le balayage.

    TROIS lectures que la fiche `case-487` §7 portait FAUSSES, et qui changent le port :

    1. **La hierarchie est `NonComparablePlaybook`1`, PAS `ComparablePlaybook`1`.** Le decompile du
       `.ctor` NOMME `ComparablePlaybooku003C...u003E$$.ctor` -- c'est un corps GSHARED FONDU
       (les deux ctors se reduisent aux memes instructions), et Ghidra n'en nomme qu'un
       proprietaire. La verite est dans `data/symbols/<build>/frida/classes.tsv`, qui donne le
       parent : `IdunBattle.AI.Playbook.NonComparablePlaybook`1`. Temoins de controle dans la meme
       table : `ChronometronPlaybook` y est bien `ComparablePlaybook`1` -- et, coherent avec ca,
       elle n'a AUCUN `EvaluateNonComparable`, elle override `CalculateCustomUtility`. La
       distinction n'est pas cosmetique : elle decide de la ROUTE
       (`ABaseAiActorTactic$$InitAbilityTypeLists` range les NonComparable dans `dict[get_Priority]`,
       evalues AVANT le fallback Comparable), donc un port loge du mauvais cote aurait fait perdre
       -- ou gagner -- l'ability contre toute attaque.
    2. **`MIN_UTILITY = 1`, pas `null`.** Le `.cctor` ecrit `Fix64(1)` dans le premier champ
       statique de la classe, et `EvaluateNonComparable` relit CE champ pour construire le
       `Nullable<Fix64>` passe au `Bucket`. Le gate MORD reellement : quand aucun ennemi n'a pris de
       Psychic ce tour, l'utilite vaut `0 < 1` et le bucket reste VIDE -- l'ability n'est pas
       proposee. C'est le comportement le plus discriminant du playbook, et un `MIN_UTILITY = 0`
       l'aurait rendu inoffensif.
    3. **`0xd` designe `DamageProfileType.Psychic`** (le profil TESTE), pas `HeavyRound` (le profil
       INFLIGE, qui vient de la config). Le meme litteral `0xd` designe `UnitTrait.Object` ailleurs
       dans l'arbre COMBAT de cette ability -- cf. `case-487` §4.

    ⚠ **CANAL TRI-ETAT, et la face LIVE est MUETTE.** `receivedDamageThisTurn`
    (`ActorStatisticsComponent + 0x80`) n'est publie par AUCUN canal de seed -- ni `decisionView`,
    ni `combatSnapshot`, ni le hook `actorStats` (qui ne porte que `+0x20`). En rejeu OFFLINE le
    runner TIENT le compteur (`UnitComponent.received_damage_this_turn`), et `Scene.from_state` le
    transporte -- c'est le regime dans lequel ce playbook est confrontable. En LIVE,
    `Scene.has_taken_damage_of_profile_this_turn` rend `None` = **non mesure** : on rend alors
    AUCUN candidat, et on le DIT (`ctx.debug`), plutot que de compter `0` -- un `0` invente serait
    une AFFIRMATION (« personne n'a pris de Psychic »), et il prononcerait un refus que le natif n'a
    pas prononce. Point d'ancrage a hooker pour fermer ce regime :
    `ActorStatisticsComponent + 0x80` cote `frida/hooks/features/ai-step/rpc-snapshot.ts` (meme
    fenetre de reinject que le residu `#545-r1`, qui vise `+0x24` du meme composant).

    `get_Priority` : 1088 est ABSENTE de `NATIVE_PRIORITY` (sweep exhaustif #170) -> tier 0 =
    `AbilityPriority.Normal`. `ShouldEvaluate` : aucun override natif -> base `True`."""

    ABILITY_ID = int(ActiveAbilityType.HellfyreMissileRack)     # 0x440 = 1088
    #: `IdunBattle.AI.Playbook.Loki.HellfyreMissileRackPlaybook$$.cctor` = `Fix64(1)`, relu dans la
    #: leaf pour le `Nullable<Fix64>` du `Bucket` -> gate `AddAction` a `>= 1`.
    MIN_UTILITY = 1.0
    PRIORITY = native_priority(int(ActiveAbilityType.HellfyreMissileRack))   # 0 = Normal (hors table)
    #: `HasTakenDamageOfDamageProfileThisTurn(u, 0xd)` -- le profil TESTE (cf. §4 de la case-doc).
    TESTED_PROFILE = int(DamageProfileType.Psychic)             # 13

    def _utility(self, ctx: NCContext) -> float | None:
        """`Fix64(Sum(Select(GetAllEnemiesOf(owner), u => HasTaken...(u, Psychic) ? 1 : 0)))`.

        Rend `None` quand le canal est MUET (aucune unite mesuree) : c'est un `null`, pas un `0`."""
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return None
        # `GetAllEnemiesOf` ne filtre NI la mort NI la position (cf. `battle_query.all_enemies_of`) :
        # c'est `ctx.units` (qui garde les depouilles, comme `decisionView`), pas `ctx.enemies`.
        enemies = bq.all_enemies_of(ctx.units or [])
        total = 0
        measured = False
        for u in enemies:
            v = sc.has_taken_damage_of_profile_this_turn(u.get("id"), self.TESTED_PROFILE)
            if v is None:
                continue                    # cette unite-la n'est pas mesuree
            measured = True
            if v:
                total += 1
        return float(total) if measured else None

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        util = self._utility(ctx)
        if util is None or util < self.MIN_UTILITY:
            if ctx.debug:
                import sys
                print(f"    [dbg NC u{ctx.uid}] HellfyreMissileRack util={util} "
                      f"min={self.MIN_UTILITY} -> aucun candidat"
                      f"{' (canal receivedDamageThisTurn MUET)' if util is None else ''}",
                      file=sys.stderr)
            return []
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        # Utilite PLATE + sweep origine-first + remplacement STRICT `>` -> la 1re cible castable
        # DEPUIS L'ORIGINE gagne (`fromHere`) ; a defaut, la 1re cible de l'union (avec move).
        fromhere: list[int] = []
        allelig: list[int] = []
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("fromHere") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        fromhere.append(t["targetId"])
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        allelig.append(t["targetId"])
        fromhere = list(dict.fromkeys(fromhere))
        allelig = list(dict.fromkeys(allelig))
        if fromhere:
            tgt, to = fromhere[0], None
        elif allelig:
            tgt, to = allelig[0], self._first_cast_pos(ctx, allelig[0])
        else:
            return []
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] HellfyreMissileRack tgt={tgt} to={to} util={util} "
                  f"(fromHere={fromhere[:3]})", file=sys.stderr)
        return [{"target": tgt, "ability": self.ABILITY_ID, "to": to, "pred": util}]

    def _first_cast_pos(self, ctx: NCContext, target: int):
        """Origine-preference : cast EN PLACE si castable a l'origine, sinon 1re tuile de move legale
        (`cast_from_tiles`, ordre movable). MEME corps que `GrapnelLauncherPlaybook._first_cast_pos`
        -- les deux mirrorent le meme sweep de `<GenerateActions>d__7` a utilite plate. Seam absente
        -> None (cast en place)."""
        if ctx.cast_from_tiles is None:
            return None
        try:
            cf = ctx.cast_from_tiles(ctx.uid, target, self.ABILITY_ID) or {}
        except Exception:                                   # noqa: BLE001 (seam live faillible)
            return None
        if cf.get("currentValid"):
            return None
        posset = {(t.get("col"), t.get("row")) for t in (cf.get("moveTiles") or [])
                  if t.get("col") is not None}
        for P in (ctx.reach_nc or []):
            if P in posset:
                return None if P == ctx.origin else P
        return None
