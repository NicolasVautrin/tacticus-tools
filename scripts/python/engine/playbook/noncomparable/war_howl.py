"""WarHowlPlaybook -- face DECISION de `1106 WarHowl` (`spaceBlackmane` << Ragnar >>). #969."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _normal_attack_ids


class WarHowlPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.WarHowlPlaybook` -- MIRROR du decompile.

    ⚠ **BASE `NonComparablePlaybook`1`, LUE dans `frida/classes.tsv`** ; le `.ctor` decompile en
    `ComparablePlaybook<...>..ctor(this, 0x452)` (corps gshared DEDUPLIQUE, mislabele). `0x452 = 1106`.

    `...WarHowlPlaybook$$.cctor` : `<statique +0x00> = Fix64.op_Implicit(1)` -> `MIN_UTILITY = 1`.

    `...WarHowlPlaybook$$EvaluateNonComparable(caster, casterPosition, abilityState)` -- MIRROR 1:1 :

        bucket = new Bucket<UnitAction>( priority: 0, minUtility: Nullable(<statique> = 1) );
        foreach (var e in BasePlaybook$$GetEligibleTargetsSelectable(this, caster,
                                                                     casterPosition.MainTile))
            bucket.AddAction( BasePlaybook$$GenerateAction(this, casterPosition, e.Target,
                                                           Fix64.op_Implicit(1)) );
        return bucket;

    => **utilite PLATE = 1**, sans AUCUN terme. Rien dans le corps ne lit la cible, la position, ni
    une stat : `Fix64.op_Implicit(1)` est reconstruit a chaque tour de boucle et c'est tout.

    ⚠ **TOUT LE DISCRIMINANT EST DANS `GetUseProbability`, ET IL EST EN AMONT.** L'utilite plate ne
    dit pas << l'IA cast toujours >> : `...WarHowlPlaybook$$GetUseProbability(unit)` (slot `0x1f8`,
    celui que `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate(unit)` consulte) est ce qui
    decide, et il peut rendre ZERO :

        var naType = UnitExtensions$$GetNormalAttackType(unit);
        var mine   = <IBattleQuery slot 69>.GetAllValidTargetsFromAllPossibleMovementTiles(unit,
                                                                                naType, null);
        if (mine.Items.Count == 0) return Fix64.op_Implicit(0);      // <-- ZERO DETERMINISTE
        int n = 0;
        foreach (var u in WarHowlAbility$$OtherBuffTargets(this.<+0x68>)
                              .SelectUniqueUnits(entities{Owner = unit}, 3))
            if (<slot 69>.GetAllValidTargetsFromAllPossibleMovementTiles(
                    u, UnitExtensions$$GetNormalAttackType(u), null).Items.Count != 0)
                n++;
        return <pct>(n >= 3 ? 100 : (n == 1 ? 75 : 50));            // /100, arrondi 2 decimales

    `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate(unit)` applique ensuite
    `prob >= 1 -> True ; prob <= 0 -> False ; sinon tirage RNG (this.<+0x30> slot 4)`.

    CE QUE LE PORT REND, ET POURQUOI C'EST EXACTEMENT LE NATIF SAUF LE TIRAGE :

      * `mine.Items.Count == 0` -> `prob = 0` -> `ShouldEvaluate` **FALSE, deterministe**. C'est le
        seul refus du natif, et il est PORTE (`should_evaluate` ci-dessous). Sans lui l'ability
        serait proposee alors que Ragnar n'a personne a frapper -- le buff dure UN TOUR.
      * `n >= 3` -> `prob = 1` -> True deterministe. Egalement rendu.
      * `n == 1` (0.75) et `n in {0, 2}` (0.50) -> tirage RNG. Le moteur est DETERMINISTE : le port
        rend True, ecart assume et deja documente sur `NonComparablePlaybook.should_evaluate`.

    ⚠ **LE COMPTEUR `n` N'EST DONC PAS PORTE, ET C'EST UNE LECTURE, PAS UN OUBLI** : les trois
    valeurs qu'il produit (0.50 / 0.75 / 1.00) sont toutes **strictement positives**, donc aucune ne
    fait rendre False. Porter `n` ne deplacerait AUCUN verdict de `should_evaluate` -- ce serait du
    code mort qui donnerait l'illusion d'une fidelite en plus. La branche qui compte, `Count == 0`,
    est celle qui est portee.

    ⚠ **LA VALEUR `50` POUR `n == 2` EST TRANSCRITE TELLE QUELLE.** Le decompile rend
    `if (n < 3) { u = (n == 1) ? 75 : 50; } else { u = 100; }` : `n == 0` et `n == 2` partagent donc
    `50`, ce qui n'est pas monotone. C'est ce que le binaire dit ; le port ne le << corrige >> pas,
    et de toute facon ne le consomme pas (cf. ci-dessus).

    `...WarHowlAbility$$OtherBuffTargets` est DEJA porte, cote COMBAT, par
    `engine.runner.abilities.spacewolves.war_howl_other_buff_targets` (#585) : amis VIVANTS ET
    CIBLABLES, hors caster, sans arme ranged, sans trait `Summon`, SANS rayon. Le natif appelle ce
    meme corps depuis les DEUX faces -- decider et executer lisent le meme ensemble.

    ⚠ **LA CIBLE EST LE CASTER.** `...WarHowlAbility$$.ctor` pose `self_cast = True` /
    `RANGE_SELF` (cf. `runner/abilities/spacewolves.py`), donc l'unique cible eligible que
    `GetEligibleTargetsSelectable` rend est `caster` lui-meme, et c'est ce que `GenerateAction`
    reemet. L'ability BUFFE, elle, tous les allies melee du plateau : l'ensemble buffe n'a rien a
    voir avec la cible du cast.

    ⚠ **AUCUN DEPLACEMENT.** L'utilite est plate, donc toutes les positions de `reach_nc` sont a
    egalite, et `Bucket$$AddAction` ne remplace que sur un STRICTEMENT superieur -> la premiere
    position enumeree gagne, c'est-a-dire l'ORIGINE. `to = None`. (Le masque de ciblage porte de
    surcroit `TR.CasterHasNotMoved`, qui interdirait le cast apres un move.)

    `PRIORITY` reste au defaut `0` (`AbilityPriority.Normal`) : `1106` est ABSENTE de la table
    mesuree `NATIVE_PRIORITY` (22 entrees, sweep #170)."""
    ABILITY_ID = int(ActiveAbilityType.WarHowl)   # 1106 = 0x452 (argument du ctor natif)
    MIN_UTILITY = 1.0                             # `...WarHowlPlaybook$$.cctor` = Fix64(1)

    @staticmethod
    def _has_normal_attack_target_anywhere(ctx: NCContext) -> bool | None:
        """`<IBattleQuery slot 69>.GetAllValidTargetsFromAllPossibleMovementTiles(caster,
        GetNormalAttackType(caster), null).Items.Count != 0`.

        Le slot est LU dans `data/symbols/<build>/metadata/interface_slots.tsv`
        (`IBattleQuery 69 GetAllValidTargetsFromAllPossibleMovementTiles 3`), pas deduit.

        Substrat offline : la vue `targets` d'`abilityTargets(caster, <attaque normale>)`, qui EST
        `GetAllValidTargetsFromAllPossibleMovementTiles` -- l'UNION sur toutes les tuiles de move
        (cf. l'encadre d'`_base.eligible_target_tiles`). Surtout PAS `fromHere`, qui n'enumere que
        depuis l'origine et ferait refuser un cast que le natif accepte.

        TRI-ETAT : `None` = PAS MESURE (RPC absent, ou attaque normale introuvable). L'appelant ne
        doit pas le rabattre sur `False` -- cf. `should_evaluate`."""
        if ctx.ability_targets is None:
            return None
        nids = _normal_attack_ids(ctx, ctx.uid)        # GetNormalAttackType(unit), per-unit
        if not nids:
            return None
        for na in nids:
            at = ctx.ability_targets(ctx.uid, na) or {}
            for u in (at.get("units") or []):
                if u.get("unitId") != ctx.uid:
                    continue
                for a in (u.get("abilities") or []):
                    if a.get("abilityId") == na and (a.get("targets") or []):
                        return True
            return False
        return None

    def should_evaluate(self, ctx: NCContext) -> bool:
        """`BasePlaybook$$ShouldEvaluate(unit)` -> slot `0x1f8` `...WarHowlPlaybook$$
        GetUseProbability(unit)`, dont le seul ZERO est `mine.Items.Count == 0`.

        DEGRADATION PERMISSIVE quand le canal est MUET (`None`) : on rend `True`. Un `False` a
        l'aveugle rendrait l'ability INVISIBLE du moteur -- exactement le trou silencieux qu'une
        exclusion juste mais non gardee a deja creuse (#967). Le refus n'est prononce que sur une
        mesure qui dit vraiment << aucune cible >>."""
        v = self._has_normal_attack_target_anywhere(ctx)
        return True if v is None else v

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`EvaluateNonComparable` : utilite PLATE `Fix64(1)` sur la cible eligible (= le caster,
        self-cast), position = l'ORIGINE par keep-first.

        `_targets.eligible_units` n'est PAS utilise ici : le domaine est un self-cast a `RANGE_SELF`,
        donc l'unique element que le selecteur natif peut rendre est `caster`. On le lit quand meme
        par `ability_targets` pour ne PAS proposer un cast que la cascade de ciblage refuse
        (cooldown, `CasterHasNotMoved`, `CasterMatchesDynamicRule`)."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("fromHere") or []):
                    if t.get("kind") == "unit" and t.get("targetId") == ctx.uid:
                        # Utilite plate 1 == MIN_UTILITY -> admise par `Bucket$$AddAction`
                        # (`utilite >= min`). `to = None` : l'origine est EN TETE du balayage natif
                        # des positions (`_sweep_origin_first`) et, l'utilite etant plate, aucune
                        # tuile de move ne peut la battre STRICTEMENT -> le natif ne bouge pas.
                        return [{"target": ctx.uid, "ability": self.ABILITY_ID,
                                 "to": None, "pred": 1.0}]
        return []
