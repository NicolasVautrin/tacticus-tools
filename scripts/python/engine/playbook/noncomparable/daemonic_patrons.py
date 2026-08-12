"""DaemonicPatronsPlaybook -- face DECISION de `1203 DaemonicPatrons` (`emperFlawlessBlade`). #969."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook, _will_normal_attack_kill


class DaemonicPatronsPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.DaemonicPatronsPlaybook` -- MIRROR du decompile.

    ⚠ **LA BASE EST `NonComparablePlaybook`, ET LE `.ctor` DIT LE CONTRAIRE.**
    `...DaemonicPatronsPlaybook$$.ctor` decompile en
    `ComparablePlaybook<__Il2CppFullySharedGenericType>..ctor(this, 0x4b3)` -- corps gshared
    DEDUPLIQUE par IL2CPP, donc mislabele par ghidra. La hierarchie LUE dans
    `data/symbols/<build>/frida/classes.tsv` tranche :
    `IdunBattle.AI.Playbook.Loki.DaemonicPatronsPlaybook` -> `IdunBattle.AI.Playbook.
    NonComparablePlaybook`1`. Meme piege que #487-r1 / #552 / #945 -- et il s'est referme ici sur
    les CINQ playbooks de la tranche (5/5 `.ctor` nomment `ComparablePlaybook`, 5/5 sont des
    `NonComparablePlaybook`1` dans `classes.tsv`).

    `0x4b3 = 1203` -> `ABILITY_ID`.

    `...DaemonicPatronsPlaybook$$.cctor` : `<statique +0x00> = FixMath.NET.Fix64.op_Implicit(1)`
    -> `MIN_UTILITY = 1`.

    `...DaemonicPatronsPlaybook$$EvaluateNonComparable(caster, casterPosition, abilityState)` --
    MIRROR 1:1, terme a terme :

        bucket = new Bucket<UnitAction>( priority: 0, minUtility: Nullable(<statique> = 1) )
        foreach (var e in BasePlaybook$$GetEligibleTargetsSelectable(this, caster, casterPosition))
        {
            if (BasePlaybook$$WillNormalAttackKill(this, e.<+0x08>, e.Target, e.<+0x40>))
                continue;                                   // le `do { } while (kill)` du decompile
            var utility = Fix64.op_Implicit( UnitExtensions$$GetStat(e.Target, 5 = Health, 0, null) );
            bucket.AddAction( BasePlaybook$$GenerateAction(this, casterPosition, e.Target, utility) );
        }
        return bucket;

    => **utilite = PV COURANTS de la cible**, avec un GATE : la cible que l'attaque NORMALE tue
    deja a coup sur est SAUTEE. C'est le patron de `MindControlPlaybook` (meme `GetStat(target, 5)`,
    meme `MIN_UTILITY`) PLUS le gate de `KillMaimBurnPlaybook` / `StormcallerPlaybook` -- les deux
    briques etaient deja portees, aucune n'est reinventee ici.

    ⚠ **LE GATE EST LE SEUL DISCRIMINANT DE CE PLAYBOOK, ET IL EST POSITION-DEPENDANT.** L'utilite
    (les PV) ne depend NI de la position du caster NI de rien d'autre que la cible ; c'est
    `WillNormalAttackKill`, qui predit l'attaque normale DEPUIS la position candidate, qui fait
    varier le resultat d'une tuile a l'autre. Le rabattre a un terme constant (ou l'omettre) rendrait
    un argmax « qui a l'air juste » -- la cible la plus grosse -- en visant justement celle qu'il
    fallait laisser a l'attaque normale.

    ⚠ **LA CIBLE EST UN ENNEMI.** `...DaemonicPatronsAbility$$.ctor` pose
    `AbilityAttackType.DirectTargetAttack` (cf. `runner/abilities/attack_type.py`), donc l'ability
    figure dans le plan d'attaque natif et `_PlanTargetPlaybook` est la base d'enumeration correcte
    (identique a `MindControlPlaybook`). Les DEUX effets que l'arbre de COMBAT pose (`1464
    DaemonicPatrons_ExtraDamage`, `1465 DaemonicPatrons_DmgReduction`, portes par #911) vont sur le
    CASTER : c'est le taunt de la cible qui alimente leur compte
    (`ADaemonicPatronsEffect$$GetNumAdjacentTauntedEnemies`). Decider et executer ne visent donc pas
    la meme entite -- les confondre viserait un allie.

    `PRIORITY` reste au defaut `0` (`AbilityPriority.Normal`) : `1203` est ABSENTE de la table
    mesuree `NATIVE_PRIORITY` (22 entrees, sweep #170), donc `native_priority(1203)` rendrait `0` --
    l'ecrire n'ajouterait aucune mesure.

    `should_evaluate` : non surchargee. `frida/methods.tsv` n'expose que trois corps pour cette
    classe (`.ctor`, `.cctor`, `EvaluateNonComparable`) -- et cette absence ne PROUVE rien (dedup
    des corps triviaux), exactement comme pour `MindControlPlaybook`. Le defaut de base
    (`BasePlaybook$$ShouldEvaluate` -> `GetUseProbability` = `Fix64(1)` = True constant) est donc ce
    que le port rend."""
    ABILITY_ID = int(ActiveAbilityType.DaemonicPatrons)   # 1203 = 0x4b3 (argument du ctor natif)
    MIN_UTILITY = 1.0                                     # `...DaemonicPatronsPlaybook$$.cctor`

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`WillNormalAttackKill -> continue` puis `Fix64(GetStat(target, 5 = HEALTH, 0, 0))`.

        `ctx.hp_cur_by_id` EST le substrat porte de `UnitExtensions$$GetStat(unit, HEALTH)` (meme
        lecture que `MindControlPlaybook` / `VexillaMagnificaPlaybook`). Cible absente ou PV nuls ->
        `None` : le natif y produirait l'utilite `0`, sous `MIN_UTILITY = 1`, donc jamais retenue
        par `Bucket$$AddAction` -- meme verdict, une allocation en moins."""
        if target is None:
            return None
        # `BasePlaybook$$WillNormalAttackKill(this, ..., e.Target, ...)` -> `continue` du decompile.
        # Predicteur absent -> le foyer rend False (borne inf assumee, cf. `_will_normal_attack_kill`).
        if _will_normal_attack_kill(ctx, target, tile):
            return None
        hp = ctx.hp_cur_by_id.get(target)                 # GetStat(target, 5 = StatType.HEALTH)
        return float(hp) if hp and hp > 0 else None
