"""WarHowlPlaybook -- face DECISION de `1106 WarHowl` (`spaceBlackmane` << Ragnar >>). #969."""
from __future__ import annotations

from engine import battle_query as bq          # FORME B (liaison de MODULE) : `has_ranged_weapon`,
#                                               le foyer du predicat `UnitsWithoutRangedWeapons`.
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait

from ._base import NCContext, NonComparablePlaybook, _normal_attack_ids, _traits

#: Les trois valeurs de `FUN_180f6ac60(pct)` = `Round((pct/100) * 100) / 100` -- donc `pct/100` --
#: telles que `...WarHowlPlaybook$$GetUseProbability` les choisit : `n >= 3 -> 100`, `n == 1 -> 75`,
#: sinon `50`. Des SCALAIRES (des pourcentages), pas des identifiants : aucun enum ne les designe.
_PCT_TROIS_OU_PLUS = 100
_PCT_UN_SEUL = 75
_PCT_AUTRE = 50


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

    ⚠ **CET ECART A UN PRIX, MESURE (#969-r1).** Confrontation live
    (`probe_969_contre_epreuve.py`, seed 777 / MC1_67, tour d'IA OBSERVE, mutation temoin VERIFIEE
    avant d'etre jouee) : `6/7 -> 4/7` de match d'ability quand les cinq faces de #969 entrent au
    registre. L'un des deux MATCH perdus est CELUI-CI (pas 7) -- le natif a joue son attaque
    normale sur `u114`, son tirage a `0.50` ou `0.75` etant tombe contre le cast. Le port reste
    PERMISSIF (meme regime que `BlackRage` 0.4) : refuser rendrait l'ability INVISIBLE, ce qui est
    le defaut le plus cher (#967). Le seul canal qui fermerait l'ecart est le tirage natif, hors
    de portee offline. Residu `#969-r1`.

    ⚠ **LE COMPTEUR `n` EST DESORMAIS PORTE, ET L'ARGUMENT QUI L'EN DISPENSAIT EST PERIME.** Il
    disait, a raison : les trois valeurs qu'il produit (0.50 / 0.75 / 1.00) sont toutes strictement
    positives, donc aucune ne fait rendre False, donc porter `n` ne deplacerait AUCUN verdict et
    serait << du code mort >>. Ce qui a change (`#969-r1`) : `p` n'est plus avale par
    `should_evaluate`, il est RENDU par `use_probability`, et le capteur `shouldEvaluateTrace`
    (en vol, `frida/hooks/probes/should-evaluate-trace.ts`) publie la `prob` EXACTE que le natif
    passe a `NextBool`. Une formule fausse se lit donc directement, au lieu de se cacher derriere
    un taux d'agrement que l'ecart de TIRAGE brouille de toute facon. Sans `n`, ce porteur serait
    le seul des trois du residu a n'avoir rien a confronter.

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
    def _has_normal_attack_target_anywhere(ctx: NCContext, unit_id: int | None = None) -> bool | None:
        """`<IBattleQuery slot 69>.GetAllValidTargetsFromAllPossibleMovementTiles(unit,
        GetNormalAttackType(unit), null).Items.Count != 0`.

        Le slot est LU dans `data/symbols/<build>/metadata/interface_slots.tsv`
        (`IBattleQuery 69 GetAllValidTargetsFromAllPossibleMovementTiles 3`), pas deduit.

        `unit_id` par defaut = le CASTER. Le natif pose la MEME question sur chacun des allies
        buffes (2e boucle de `GetUseProbability`), d'ou le parametre : un seul corps natif, un seul
        mirror. `_base._has_valid_targets` prend deja un `unit_id` arbitraire de la meme facon.

        Substrat offline : la vue `targets` d'`abilityTargets(unit, <attaque normale>)`, qui EST
        `GetAllValidTargetsFromAllPossibleMovementTiles` -- l'UNION sur toutes les tuiles de move
        (cf. l'encadre d'`_base.eligible_target_tiles`). Surtout PAS `fromHere`, qui n'enumere que
        depuis l'origine et ferait refuser un cast que le natif accepte.

        ⚠ **CE CANAL NE REPOND QUE POUR LE JOUEUR COURANT**, et ce n'est pas << oriente caster >> :
        le hook filtre `IsControlledByCurrentPlayer` (`frida/hooks/features/ai-step/
        rpc-targeting.ts`), donc TOUT allie vivant du joueur courant repond, et AUCUN ennemi. Les
        allies buffes de WarHowl sont par construction des allies -> ils repondent. Un ennemi
        rendrait `units: []`, indistinguable d'un << aucune cible >> : c'est pourquoi ce mirror
        distingue explicitement l'unite ABSENTE de la reponse (`None`) de l'unite presente sans
        cible (`False`).

        TRI-ETAT : `None` = PAS MESURE (RPC absent, attaque normale introuvable, ou unite absente
        de la reponse). L'appelant ne doit pas le rabattre sur `False`."""
        if ctx.ability_targets is None:
            return None
        uid = ctx.uid if unit_id is None else int(unit_id)
        nids = _normal_attack_ids(ctx, uid)            # GetNormalAttackType(unit), per-unit
        if not nids:
            return None
        for na in nids:
            at = ctx.ability_targets(uid, na) or {}
            for u in (at.get("units") or []):
                if u.get("unitId") != uid:
                    continue
                for a in (u.get("abilities") or []):
                    if a.get("abilityId") == na:
                        return bool(a.get("targets") or [])
            return None            # unite ABSENTE de la reponse -> non mesure, jamais un `False`
        return None

    @staticmethod
    def _other_buff_targets(ctx: NCContext) -> list:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$OtherBuffTargets`, evalue
        cote DECISION -- c'est-a-dire son CARDINAL sur les canaux publies, pas son arbre DSL (celui-ci
        exige un `State` runner ; le foyer COMBAT est
        `engine.runner.abilities.spacewolves.war_howl_other_buff_targets`).

        Les quatre noeuds natifs, terme a terme :

            UnitsWithoutTrait(
                UnitsWithoutRangedWeapons(
                    Friends(of = Owner, entities = AllAliveUnits - Owner, selection = 3)),
                trait = UnitTrait.Summon, selection = 3)

        Soit, sur `ctx.units` : ami VIVANT, caster EXCLU, SANS arme ranged, SANS trait `Summon`.

        `UnitsWithoutRangedWeapons` -> `engine.battle_query.has_ranged_weapon` (le foyer du predicat
        `WeaponsComponent$$HasRangedWeapon(minRange = null)`, qui se reduit a << au moins une arme
        n'est pas `IsMelee` >>) -- surtout pas `UnitExtensions$$IsRanged`, qui est un AUTRE corps a
        un AUTRE seuil.

        ⚠ **UN ECART NOMME : le `selectionType = 3` n'est PORTE QU'A MOITIE.**
        `UnitSelectionType.OnlyAliveAndTargetable` = `IsAlive && !HasFlag(UnitFlag.Untargetable)`.
        Le volet `IsAlive` est porte (`u["alive"]`) ; le volet `Untargetable` ne l'est PAS -- aucun
        accesseur de `Scene` ne publie ce flag (`combatSnapshot.units[].unitFlags` le porte, mais
        seuls `Moved`/`Teleported`/`PreventOverkill`/`ActiveAbilityUsed` sont extraits). MESURE de
        reference (#585) : un allie en DEEP STRIKE (`TeleportStrike_TeleportingIn`) porte ce flag et
        le natif ne le compte pas. L'ecart SUR-compte donc `n`, ce qui ne peut que MONTER `p` --
        or `p` monte ne change aucun verdict ici (les trois valeurs sont deja > 0). Sens de l'ecart
        NOMME, effet sur le gate NUL."""
        out = []
        for u in (ctx.units or []):
            if u.get("id") == ctx.uid or not u.get("ctrl") or not u.get("alive"):
                continue                                    # `AllAliveUnits - Owner`, puis `Friends`
            vid = u.get("visualId")
            if bq.has_ranged_weapon(vid):
                continue                                    # `UnitsWithoutRangedWeapons`
            if UnitTrait.Summon.name in (_traits(vid) or ()):
                continue                                    # `UnitsWithoutTrait(Summon)` -- le KIT
                #                    gameconfig porte les traits par NOM (meme lecture que
                #                    `graviton_rifle`/`exemplar_of_hate`), et le membre est nomme
                #                    plutot que l'ordinal `0x2`.
            out.append(u)
        return out

    def _num_buff_targets_with_attack(self, ctx: NCContext) -> int | None:
        """Le compteur `n` de `...WarHowlPlaybook$$GetUseProbability` : combien d'allies buffes ont
        au moins une cible d'attaque normale depuis leurs tuiles de move.

        TRI-ETAT STRICT : si UN SEUL allie n'est pas mesurable, `n` est `None`. Un compte PARTIEL
        donnerait un `p` FAUX -- et `p` est justement la valeur que ce port rend confrontable au
        `prob` natif ; la rendre approximative retirerait tout son sens a la confrontation."""
        n = 0
        for u in self._other_buff_targets(ctx):
            v = self._has_normal_attack_target_anywhere(ctx, u.get("id"))
            if v is None:
                return None
            if v:
                n += 1
        return n

    def use_probability(self, ctx: NCContext) -> float | None:
        """Slot `0x1f8`, SURCHARGE par `...WarHowlPlaybook$$GetUseProbability(unit)` -- MIRROR 1:1,
        y compris le compteur `n`, qui n'etait PAS porte avant `#969-r1` :

            if (mine.Items.Count == 0) return Fix64(0);                  // ZERO DETERMINISTE
            n = |{ u in OtherBuffTargets : GetAllValidTargets...(u).Items.Count != 0 }|;
            return pct(n >= 3 ? 100 : (n == 1 ? 75 : 50));

        Le triage des trois branches vit dans le foyer `_base.probability_gate`.

        ⚠ **POURQUOI `n` EST DESORMAIS PORTE ALORS QU'IL NE DEPLACE AUCUN VERDICT.** L'argument
        d'origine etait juste et il est perime : les trois valeurs (`0.50`, `0.75`, `1.00`) sont
        strictement positives, donc aucune ne fait rendre `False`, donc porter `n` etait << du code
        mort >>. Ce qui a change, c'est que `p` est maintenant une valeur CONFRONTABLE : le capteur
        `shouldEvaluateTrace` publie la `prob` EXACTE que le natif passe a `NextBool`, et une
        formule fausse s'y lit directement. Sans `n`, ce porteur serait le seul des trois a ne rien
        pouvoir confronter.

        ⚠ **`n == 2` VAUT `50`, PAS UNE INTERPOLATION.** Le decompile rend
        `if (n < 3) { u = (n == 1) ? 75 : 50; } else { u = 100; }` : `n == 0` et `n == 2` partagent
        `50`, ce qui n'est pas monotone. C'est ce que le binaire dit ; le port ne le << corrige >>
        pas.

        TRI-ETAT : `None` = PAS MESURE (canal `abilityTargets` absent, ou un allie non mesurable) ->
        `probability_gate` rend `True`, degradation PERMISSIVE. Un `0.0` a l'aveugle rendrait
        l'ability INVISIBLE du moteur, le trou silencieux de #967. Le zero n'est rendu que sur la
        mesure qui dit vraiment << Ragnar n'a personne a frapper >> -- et c'est le SEUL refus du
        natif."""
        mine = self._has_normal_attack_target_anywhere(ctx)
        if mine is None:
            return None
        if not mine:
            return 0.0                                  # `return Fix64.op_Implicit(0)`
        n = self._num_buff_targets_with_attack(ctx)
        if n is None:
            return None
        pct = (_PCT_TROIS_OU_PLUS if n >= 3
               else (_PCT_UN_SEUL if n == 1 else _PCT_AUTRE))
        return pct / 100.0

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
