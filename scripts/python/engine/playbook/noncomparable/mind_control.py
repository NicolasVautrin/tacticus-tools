"""MindControlPlaybook -- face DECISION de `1164 MindControl` (`genesMagus`). #598."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import _PlanTargetPlaybook


class MindControlPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.MindControlPlaybook` -- MIRROR du decompile.

    ⚠ **LA BASE EST `NonComparablePlaybook`, ET LE NOM GHIDRA DIT LE CONTRAIRE.** Le ctor decompile
    affiche `ComparablePlaybook<__Il2CppFullySharedGenericType>..ctor(this, 0x48c)` -- corps gshared
    DEDUPLIQUE, donc mislabele. La chaine de parents LUE dans `data/symbols/<build>/frida/
    classes.tsv` tranche : `IdunBattle.AI.Playbook.Loki.MindControlPlaybook` ->
    `IdunBattle.AI.Playbook.NonComparablePlaybook`1` -> `Playbook`1` -> `BasePlaybook`. C'est la
    STRUCTURE qui decide, jamais le nom (doctrine gshared).

    `...MindControlPlaybook$$.ctor` : `NonComparablePlaybook<MindControlAbility>..ctor(this, 0x48c)`
    -> `ABILITY_ID = 1164`.

    `...MindControlPlaybook$$.cctor` : `<champ statique> = FixMath.NET.Fix64.op_Implicit(1)`
    -> `MIN_UTILITY = 1`.

    `...MindControlPlaybook$$EvaluateNonComparable(caster, casterPosition, abilityState)` -- MIRROR
    1:1, terme a terme :

        bucket = new Bucket<UnitAction>( priority: 0, minUtility: Nullable(<statique> = 1) )
        foreach (target in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition))
            utility = Fix64.op_Implicit( UnitExtensions.GetStat(target, 5 = HEALTH, 0, 0) )
            bucket.AddAction( BasePlaybook.GenerateAction(casterPosition, target, utility) )
        return bucket

    => l'utilite est les **PV COURANTS de la cible**, sans aucune transformation : le Magus vise
    l'ennemi le plus gros. C'est le PATRON EXACT de `VexillaMagnificaPlaybook` (meme
    `GetStat(target, 5)`, meme `MIN_UTILITY = 1`), a ceci pres que la cible y est un ALLIE et ici un
    ENNEMI -- le corps natif, lui, est le meme.

    ⚠ **`GetStat(target, 5)` lit la MEME stat que le `StatAmount(It, 5)` de l'arbre de COMBAT, mais
    sur une AUTRE unite** : la DECISION classe les CIBLES (des ennemis) par PV, l'EXECUTION classe
    les TAUNTEURS (nos allies adjacents a la cible) par PV. Les confondre donnerait une decision
    qui a l'air juste et vise la mauvaise unite.

    PAS DE `should_evaluate` PORTE, et c'est une LECTURE, pas un oubli : `MindControlPlaybook`
    n'expose que trois corps (`.ctor`, `.cctor`, `EvaluateNonComparable`) dans les DEUX tables
    (`frida/methods.tsv`, `ghidra/functions.tsv`). L'absence dans les tables ne PROUVE pas l'absence
    de surcharge (dedup de corps triviaux) -- c'est exactement ainsi que le slot 4 de
    `VexillaMagnificaPlaybook` avait ete rate puis retrouve LIVE (#46). Le defaut de base
    (`BasePlaybook$$ShouldEvaluate` = `GetUseProbability >= 1` = True constant) est donc ce que le
    port rend, et le residu `#598-r3` nomme la mesure qui manque : lire le slot 4 de la vtable de
    ce playbook en live (`BLOCAGE: capteur`).

    `PRIORITY` reste au defaut `0` (`AbilityPriority.Normal`) : 1164 est ABSENTE de la table mesuree
    `NATIVE_PRIORITY` (22 entrees), donc `native_priority(1164)` rendrait `0` de toute facon --
    l'ecrire n'ajouterait aucune mesure."""
    ABILITY_ID = int(ActiveAbilityType.MindControl)   # 1164 = 0x48c (argument du ctor natif)
    MIN_UTILITY = 1.0                                 # `...MindControlPlaybook$$.cctor` = Fix64(1)

    def evaluate_non_comparable(self, tile, target, ctx):
        """`Fix64.op_Implicit(GetStat(target, 5 = HEALTH, 0, 0))` -- les PV COURANTS de la cible.

        `ctx.hp_cur_by_id` est le substrat porte de `UnitExtensions$$GetStat(unit, HEALTH)` (meme
        lecture que `VexillaMagnificaPlaybook`). Cible absente / PV nuls -> `None` = pas de
        candidat (le natif y produirait une utilite `0`, sous `MIN_UTILITY = 1`, donc jamais
        retenue par `Bucket.AddAction` : meme verdict, une allocation en moins)."""
        # `hp_cur_by_id` EST le canal `StatType.HEALTH` du port : aucun `5` litteral n'est ecrit
        # ici, donc rien a nommer -- l'enum vit au site qui en a besoin (l'arbre de COMBAT).
        hp = ctx.hp_cur_by_id.get(target)                # GetStat(target, 5 = StatType.HEALTH)
        return float(hp) if hp and hp > 0 else None
