"""InvocationOfMachineVengeancePlaybook (1172, `admecBossBelisarius`) -- #1027.

Face DECISION de l'active de spawn+buff de Belisarius Cawl. Le PENDANT COMBAT vit dans
`engine.runner.abilities.admec.InvocationOfMachineVengeanceAbility`.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first, native_priority


class InvocationOfMachineVengeancePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.InvocationOfMachineVengeancePlaybook$$EvaluateNonComparable` --
    MIRROR du decompile, remis en C# :

        bucket = new Bucket(0, Nullable<Fix64>(<statique du cctor> = Fix64.op_Implicit(1)));
        targets = BasePlaybook.GetEligibleTargetsSelectable(this, caster, casterPosition);
        foreach (e in targets) {
            cur = EntityExtensions.GetUnitPosition(caster, <this+0x20 = state>);
            u   = Fix64.op_Implicit( (int)(casterPosition != cur) + 1 );   // 1 ou 2
            bucket.AddAction( BasePlaybook.GenerateAction(this, casterPosition, e.<+0x10>, u) );
        }
        return bucket;

    L'UTILITE NE LIT QUE LA POSITION, et c'est tout le contenu du playbook : `1` quand la position
    candidate EST la position courante du caster, `2` sinon. Le `Bucket` ne remplace que sur
    STRICTEMENT superieur et la liste `tiles` du generateur commence par la position COURANTE
    (`BattleQuery$$GetCurrentAndMovablePositionsFor`, `OrderedSet` seede par
    `GetUnitPosition(unit)`) -- donc l'origine est evaluee EN PREMIER a l'utilite 1, puis la
    PREMIERE tuile de move la bat a 2 et aucune autre ne la depasse. **Belisarius BOUGE des qu'il
    le peut**, et il va sur la premiere tuile du movable set.

    C'est le comportement EXACTEMENT INVERSE de `NovaBoostPlaybook` (utilite CONSTANTE ->
    keep-first -> cast EN PLACE), alors que les deux sont des self-cast a cible unique : le voisin
    de forme ne predit pas le verdict, seule l'utilite le fait.

    `.ctor` -> `<base>..ctor(this, 0x494 = 1172)` : le litteral est l'ABILITY_ID, pas une priorite.
    ⚠ Ghidra nomme ce ctor `ComparablePlaybook<T>$$.ctor` -- c'est un corps GSHARED DEDUPLIQUE
    (`NovaShieldPlaybook$$.ctor` et `ThriceBlessedConflagrationPlaybook$$.ctor` n'ont AUCUN symbole
    propre, alors que leurs playbooks sont NonComparable et portes comme tels). Le discriminant LU
    est l'OVERRIDE de `EvaluateNonComparable` : `NonComparablePlaybook<T>$$EvaluateInternal` a pour
    corps ENTIER `(**(vtable + 0x318))()`, l'appel virtuel de cette methode-la.

    `.cctor` : `<statique> = Fix64.op_Implicit(1)` -> le `minUtility` du Bucket = **1**.
    Tier `get_Priority` = **-1000** (`AbilityPriority.Last`), mesure #170.

    RESIDU NOMME (`#1027-r2`) : le port ne modelise pas `GetEligibleTargetsSelectable` PAR POSITION
    pour cette ability (elle est self-cast a portee 0, `RANGE_SELF` + `CasterIsPossibleTarget`), il
    teste seulement que la liste est NON VIDE, comme `NovaBoostPlaybook`. Une position de move d'ou
    le self-cast serait illegal serait donc retenue a tort ; aucun gate natif connu ne la produit
    (la portee 0 ne depend pas de la position)."""
    ABILITY_ID = int(ActiveAbilityType.InvocationOfMachineVengeance)   # 1172
    MIN_UTILITY = 1.0
    PRIORITY = native_priority(int(ActiveAbilityType.InvocationOfMachineVengeance))  # -1000

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if not self._has_eligible_target(ctx):
            return []          # `GetEligibleTargetsSelectable` vide -> le natif n'emet rien
        best = None            # (position, utilite) -- `Bucket.AddAction` remplace sur STRICT `>`
        for pos in _sweep_origin_first(ctx):
            u = 1.0 + (1.0 if pos != ctx.origin else 0.0)   # `(casterPosition != cur) + 1`
            if best is None or u > best[1]:
                best = (pos, u)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        pos, u = best
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,
                 "to": (pos if pos != ctx.origin else None), "pred": u}]

    def _has_eligible_target(self, ctx: NCContext) -> bool:
        """`BasePlaybook$$GetEligibleTargetsSelectable` non-vide. Cible eligible d'un self-cast =
        le caster (via `abilityTargets`, qui inclut les cibles NON-attaque). PERMISSIF quand la
        source d'eligibilite est indisponible -- le driver filtre deja `usable is False`."""
        if ctx.ability_targets is None:
            return True
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == self.ABILITY_ID and (a.get("targets") or []):
                    return True
        return False
