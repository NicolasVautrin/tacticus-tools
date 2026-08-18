"""RevealPlaybook -- face DECISION de `1107 Reveal` (`eldarNpc2Warlock`). #1033-r2.

La face COMBAT vit dans `engine/runner/abilities/loki/reveal.py` (#1033) ; celle-ci est le
pendant que le residu `#1033-r2` nommait, et sa RE a ete RELUE sur le build courant, pas
recopiee de la fiche.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook, _will_normal_attack_kill
# FORME B (liaison de MODULE), differe CLASSE GRATUIT : `make_normal_attack_predictions` est
# SUBSTITUE par les patcheurs de la banque -- une liaison `from X import f` au niveau module
# rendrait le patch inerte (cf. `euphoric_strikes`, meme forme, meme raison).
from engine.playbook.prediction import normal_attack as _pred_na


class RevealPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.RevealPlaybook` -- MIRROR du decompile, terme a terme.

    `...RevealPlaybook$$.ctor` : `ComparablePlaybook<__Il2CppFullySharedGenericType>..ctor(this,
    0x453)` -> `ABILITY_ID = 1107`. ⚠ **LE NOM DE LA BASE DANS LE DECOMPILE NE FAIT PAS FOI** : le
    corps gshared du ctor est DEDUPLIQUE, donc Ghidra l'etiquette `ComparablePlaybook<T>` pour
    toutes les hierarchies qui partagent ce corps. Ce qui tranche, c'est la METHODE PROPRE --
    `EvaluateNonComparable` -- qui n'existe que sur `NonComparablePlaybook<T>` (derivation de
    `probe_909` etape 4). C'est exactement la meme lecture que `MindControlPlaybook`, dont le ctor
    affiche lui aussi `ComparablePlaybook<T>..ctor(this, 0x48c)`.

    `...RevealPlaybook$$.cctor` : `<statics[0]> = FixMath.NET.Fix64$$op_Implicit(1)` -> la borne
    d'utilite du bucket vaut **1**.

    `...RevealPlaybook$$EvaluateNonComparable(caster, casterPosition, abilityState)` -- MIRROR :

        bucket = new Bucket<UnitAction>( priority: 0,
                                         minUtility: Nullable(<statics[0]> = Fix64(1)) )
        targets = BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition.MainTile)
        foreach (e in targets)
            if (BasePlaybook$$WillNormalAttackKill(caster, e.<+0x10 Target>,
                                                   casterPosition.MainTile))  continue;
            bucket.AddAction( BasePlaybook$$GenerateAction(casterPosition, e.<+0x10 Target>,
                                                           Fix64.op_Implicit(1)) )
        return bucket

    ⚠ **LA BORNE EST BIEN POSEE, ET ELLE EST `>=`.** Le `Bucket` est construit par la surcharge a
    QUATRE arguments (`this, 0, &nullable, typeinfo`), donc `minUtility.HasValue == true` -- la
    surcharge a DEUX arguments, elle, n'en pose AUCUNE et `AddAction` accepterait tout, y compris
    une utilite negative. Le gate lu (`Bucket$$AddAction` -> son helper) est
    `Nullable.HasValue == false -> accepte`, sinon `action.Utility >= minUtility.Value`
    (`op_GreaterThanOrEqual`). L'utilite CONSTANTE `1` est donc EGALE a `MIN_UTILITY` et
    **passe** : lire ce gate en `>` strict ferait de ce playbook un mort silencieux.

    ⚠ **L'UTILITE EST CONSTANTE, DONC C'EST LE GATE QUI DECIDE -- ET LE GATE EST POSITIONNEL.**
    `WillNormalAttackKill` predit l'attaque NORMALE **depuis `casterPosition.MainTile`**, la
    position candidate courante : une cible sure-kill depuis l'origine peut ne plus l'etre depuis
    une tuile de move, et inversement. Au tie d'utilite (toutes les cibles retenues valent 1),
    `Bucket$$AddAction` SEED le premier puis ne remplace que sur `op_GreaterThan` STRICT : c'est
    donc la PREMIERE paire (position, cible) de l'ordre natif qui gagne, et l'ordre natif des
    positions commence par l'ORIGINE (`GetCurrentAndMovablePositionsFor`, cf. `_PlanTargetPlaybook`).
    Le port herite cet ordre de `generate_candidates` -- il n'y a rien a ecrire ici pour l'obtenir.

    SENS TACTIQUE : le natif ne gaspille pas le marquage `1219 Revealed` sur une unite que
    l'attaque normale du caster tue deja a coup sur. C'est le patron des quinze playbooks de
    `engine/playbook/normal_attack_kill_gate.py` et de `StormcallerPlaybook`, a ceci pres qu'ici
    il ne reste RIEN d'autre : l'utilite ne discrimine pas les survivantes.

    PAS DE `should_evaluate` PORTE, ET C'EST MESURE, PAS DEDUIT D'UNE ABSENCE. Les tables de
    symboles sont indexees par ADRESSE et IL2CPP DEDUPLIQUE les corps : << trois symboles
    seulement >> ne prouverait RIEN (c'est ainsi que le slot 4 de `VexillaMagnificaPlaybook` avait
    ete rate puis retrouve LIVE, #46). La metadata, elle, decrit des DEFINITIONS, pas des corps --
    `IdunBattle.AI.Playbook.Loki.RevealPlaybook` DECLARE exactement
    `{.ctor, .cctor, EvaluateNonComparable}`, ni `ShouldEvaluate` ni `GetUseProbability`
    (`probe_552r3_slot4_declare`, build `t6dpr4k06g`, temoin BILATERAL 8/8). Le slot 4 est donc
    `BasePlaybook$$ShouldEvaluate` = `GetUseProbability >= 1` = True constant, et c'est ce que le
    port rend.

    `PRIORITY` reste au defaut `0` (`AbilityPriority.Normal`) : 1107 est ABSENTE de la table
    mesuree `NATIVE_PRIORITY` (sweep exhaustif #170), donc `native_priority(1107)` rendrait `0`.

    ⚠ **CE QUE CE PORT NE PEUT PAS ENCORE CONFRONTER, ET CE N'EST PAS SON FAIT** : le gate
    DYNAMIQUE de la face COMBAT (`RevealAbility$$GetDynamicInvalidTargetReason`, qui exige une
    unite AELDARI AMIE defaite PAR la cible) refuse encore toute cible en regime pourtant
    favorable -- residu `#1033-r4`, etage `UnitExtensions$$IsFriend` sur une unite MORTE non lu.
    Tant qu'il refuse, `GetEligibleTargetsSelectable` rend une liste VIDE et ce playbook ne
    produit AUCUN candidat : le natif non plus. Les deux faces sont d'accord sur le vide, ce qui
    est un accord en regime DEGENERE -- donc pas une confirmation."""

    ABILITY_ID = int(ActiveAbilityType.Reveal)   # 0x453 = 1107 (argument du ctor natif)
    MIN_UTILITY = 1.0   # `...RevealPlaybook$$.cctor` : `Fix64.op_Implicit(1)` -> statics[0]
    PRIORITY = 0        # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`WillNormalAttackKill -> continue`, sinon l'utilite CONSTANTE `Fix64.op_Implicit(1)`.

        L'ORDRE est celui du natif : le gate est la PREMIERE instruction du corps de boucle, et
        c'est lui qui construit le `ProbableDamageEvent` que l'oracle `ncPlaybookPredict` voit
        (cf. `damage_predictions`). Le natif, lui, n'a rien a calculer apres : `1` est un
        litteral."""
        if tile is None or target is None:
            return None
        if _will_normal_attack_kill(ctx, target, tile):
            return None                    # `continue` natif : la normale sure-kill deja la cible
        return 1.0                         # `FixMath.NET.Fix64$$op_Implicit(1)`, litteral du corps

    def damage_predictions(self, tile, target, ctx: NCContext) -> list:
        """AU PLUS UN event, et il vient du GATE -- jamais de l'ability.

        `BasePlaybook$$WillNormalAttackKill` construit un `ProbableDamageEvent` pour l'attaque
        NORMALE depuis `tile` ; `EvaluateNonComparable` n'en construit aucun autre (son utilite
        est un litteral). La sequence que l'oracle voit vaut donc `[gate]`, que le gate morde ou
        non -- le `continue` ne supprime pas l'event deja construit.

        ⚠ Independamment du corps du playbook, `1107` n'a AUCUNE prediction d'ABILITY a emettre :
        `gameconfig.abilities.Reveal` n'a ni `minDmg`/`maxDmg`, ni `nrOfHits`, ni `damageProfile`
        (mesure de la face COMBAT, `runner/abilities/loki/reveal.py`). Le tag `"ability"` ne peut
        donc pas apparaitre ici."""
        if tile is None or ctx.scene is None or target is None:
            return []
        na = _pred_na.make_normal_attack_predictions(ctx.scene, ctx.uid, target, tile)
        return [] if na is None else [("WillNormalAttackKill", na.prediction)]
