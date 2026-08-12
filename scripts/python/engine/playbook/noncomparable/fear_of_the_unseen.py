"""`FearOfTheUnseenPlaybook` (0x45b = 1115, `tyranDeathleaper`) -- face DECISION. #952.

REACHABILITY, LUE ET NON SUPPOSEE
---------------------------------
`data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` :

    active   1115   IdunBattle.AI.Playbook.Loki.FearOfTheUnseenPlaybook

Une SEULE entree, dict `active` (+0x68). Pas de code registered-but-dead.

BASE `NonComparablePlaybook<T>`, LUE dans `frida/classes.tsv` (le `.ctor` decompile NOMME
`ComparablePlaybook<...>$$.ctor(this, 0x45b, klass)` : corps trivial DEDUPLIQUE, piege #487-r1).
RECENSEMENT AU BLOC (`ghidra/functions.tsv`, `181238fd0..1812391e0`, encadre par
`Fealty_NormalAttackPlaybook$$.ctor` et `FeederTendrils_NormalAttackPlaybook$$.ctor`) : trois corps
CONTIGUS -- `EvaluateNonComparable`, `.cctor`, `.ctor`. Rien de fondu entre eux.

LE CORPS, TERME A TERME -- ET C'EST UN VETO, PAS UN SCORE
---------------------------------------------------------
`IdunBattle.AI.Playbook.Loki.FearOfTheUnseenPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))     # cctor : Fix64(1)
    vt = BasePlaybook.GetAllNormalAttackTargets(caster)              # ValidTargets
    if (vt != null && vt.<+0x10> != null)
        if (vt.<+0x10>.<+0x18> == 0)                                 # OrderedSet.Count == 0
            bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, caster,
                                                         Fix64.op_Implicit(10)))
    return bucket

`IdunBattle.AI.Playbook.Loki.FearOfTheUnseenPlaybook$$.cctor` : `<statics+0x00> = Fix64(1)`.

Il n'y a **AUCUN appel a `GetEligibleTargetsSelectable`** : la cible n'est pas enumeree, c'est le
CASTER lui-meme (2e argument de `GenerateAction`). L'utilite est la CONSTANTE `10`, tres au-dessus
du `MIN_UTILITY = 1` : tout le discriminant est dans la condition. Le Deathleaper se teleporte
quand il n'a PLUS RIEN a frapper.

`GetAllNormalAttackTargets`, verbatim
--------------------------------------
`IdunBattle.AI.Playbook.BasePlaybook$$GetAllNormalAttackTargets(unit)` :

    return this.<+0x28 = IBattleQuery>.<slot 0x45>(unit,
                                                   UnitExtensions.GetNormalAttackType(unit), false);

Slot RESOLU dans `data/symbols/rnca9r7q6c/metadata/interface_slots.tsv` :
`IBattleQuery 69 (0x45) GetAllValidTargetsFromAllPossibleMovementTiles 3 params`. C'est le MEME
appel que `ExemplarOfTheMontkaPlaybook$$HasNormalAttackTarget` (#952 le reutilise tel quel).

Le retour est un `IdunBattle.Entities.Abilities.ValidTargets` (taille 0x20), dont les DEUX champs
sont lus dans `...ValidTargets$$Merge` et `...ValidTargets$$GetTargetsByPosition` :

    +0x10 = OrderedSet<IEntity>                        <- l'UNION de toutes les cibles
    +0x18 = Dictionary<UnitPosition, OrderedSet<…>>    <- la carte position -> cibles

Le playbook lit `+0x10` puis `+0x18` **de cet OrderedSet-la** (son `Count`), pas le dictionnaire.
La condition est donc : « l'UNION des cibles d'attaque normale, sur TOUTES les tuiles de move,
est VIDE ». Le mirror offline exact est `abilityTargets(uid, <naId>).targets` -- l'UNION, la vue que
le RPC publie pour ce meme slot -- et surtout PAS `fromHere`, qui n'est que la position courante et
rendrait le veto BEAUCOUP trop permissif (le natif refuse de se teleporter des qu'UNE tuile de move
lui donne une cible).

DOMAINE DE CIBLE -- LE CASTER
------------------------------
`...FearOfTheUnseenAbility$$.ctor` -> masque `0x18` =
`AddCasterIfMatchesDynamicRule | CasterHasNotMoved`, `overrideRange = 0` (litteral deja relu dans
`runner/abilities/attack_type.py` / le port COMBAT). `CasterHasNotMoved` verrouille le cast a la
position d'origine => `to = None`, sans supposition.

BORNES DE PORT, nommees
------------------------
* `ctx.ability_targets is None` (aucun RPC) -> `[]` : le veto natif est une condition POSITIVE
  (« aucune cible »), et la fabriquer depuis une NON-MESURE proposerait un teleport que le natif ne
  fait pas. C'est aussi, exactement, le comportement d'avant ce module (1115 sans entree au
  registre).
* `_normal_attack_ids` vide (l'unite n'a pas d'attaque normale dans `ctx.units`) -> `[]`, meme
  raison : on ne sait pas si l'union est vide, on ne l'affirme pas.
* La `ValidTargets` native est calculee par `GetAllValidTargetsFromAllPossibleMovementTiles`, dont
  `abilityTargets(...).targets` est le mirror publie. Une unite qui n'a d'attaque normale que
  depuis une tuile qu'aucune vue RPC ne couvre ferait rendre au port un veto que le natif ne pose
  pas -- borne SUP, nommee, non observee a ce jour.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _normal_attack_ids


class FearOfTheUnseenPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.FearOfTheUnseenPlaybook` (0x45b = 1115, `tyranDeathleaper`).

    VETO booleen : l'ability est proposee -- sur SOI, utilite CONSTANTE 10 -- si et seulement si
    l'union des cibles d'attaque normale du caster est VIDE."""

    ABILITY_ID = int(ActiveAbilityType.FearOfTheUnseen)   # 0x45b = 1115 (argument du ctor natif)
    MIN_UTILITY = 1.0     # `...FearOfTheUnseenPlaybook$$.cctor` : `Fix64$$op_Implicit(1)`
    #: `Fix64.op_Implicit(10)` -- la constante emise, LUE au corps ; sans rapport avec `MIN_UTILITY`.
    UTILITY = 10.0
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`Fix64.op_Implicit(10)` -- constante, aucune lecture de cible ni de position."""
        return self.UTILITY

    def _has_any_normal_attack_target(self, ctx: NCContext) -> bool | None:
        """`GetAllNormalAttackTargets(caster).<+0x10>.Count != 0` -- l'UNION des cibles d'attaque
        normale sur TOUTES les tuiles de move.

        Rend `None` = **NON MESURE** (RPC absent, ou aucune attaque normale connue de `ctx.units`) :
        l'appelant s'abstient alors, il ne fabrique pas un « aucune cible »."""
        if ctx.ability_targets is None:
            return None
        nids = _normal_attack_ids(ctx, ctx.uid)     # `UnitExtensions$$GetNormalAttackType(unit)`
        if not nids:
            return None
        for na_id in sorted(nids):
            at = ctx.ability_targets(ctx.uid, na_id) or {}
            for u in (at.get("units") or []):
                if u.get("unitId") != ctx.uid:
                    continue
                for a in (u.get("abilities") or []):
                    if a.get("abilityId") != na_id:
                        continue
                    # `targets` = `GetAllValidTargetsFromAllPossibleMovementTiles` = `ValidTargets
                    # .<+0x10>` (l'UNION). PAS `fromHere` (la seule position courante).
                    for t in (a.get("targets") or []):
                        if t.get("targetId") is not None:
                            return True
        return False

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """Le corps natif complet : un SEUL candidat possible, sur le caster, en place.

        `CasterHasNotMoved` du masque verrouille l'origine ; l'utilite etant constante, le sweep de
        positions de `<GenerateActions>d__7` ne pourrait de toute facon pas ameliorer strictement."""
        if self._has_any_normal_attack_target(ctx) is not False:
            return []            # cible existante, ou NON MESURE -> le natif n'emet rien / on s'abstient
        util = self.evaluate_non_comparable(ctx.origin, ctx.uid, ctx)
        if util < self.MIN_UTILITY:                 # gate `Bucket$$AddAction` (util >= min)
            return []
        return [{"target": ctx.uid, "ability": self.ABILITY_ID, "to": None, "pred": util}]
