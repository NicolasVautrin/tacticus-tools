"""`ExemplarOfHatePlaybook` (0x474 = 1140, `darkaAsmodai` « Asmodai ») -- face DECISION. #957.

REACHABILITY, LUE ET NON SUPPOSEE
---------------------------------
`data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` (extrait de
`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`) :

    active   1140   IdunBattle.AI.Playbook.Loki.ExemplarOfHatePlaybook

Une SEULE entree, dans le dict `active` (+0x68). Pas de code registered-but-dead.

BASE DE HIERARCHIE -- `NonComparablePlaybook<T>`, LUE dans `frida/classes.tsv`
-----------------------------------------------------------------------------
    IdunBattle.AI.Playbook.Loki.ExemplarOfHatePlaybook  ->  IdunBattle.AI.Playbook.NonComparablePlaybook`1

Ghidra nomme pourtant le `.ctor` `ComparablePlaybook<...>$$.ctor(this, 0x474, klass)` : corps trivial
DEDUPLIQUE (le piege de #487-r1 / #945, qui frappe 4 `.ctor` sur 6 du lot precedent). Le `0x474` du
ctor EST l'ability_id -- lu la, jamais devine du nom.

RECENSEMENT DES METHODES -- au BLOC, pas par grep
-------------------------------------------------
Les trois corps de la classe sont CONTIGUS dans `ghidra/functions.tsv` (bloc `18122ecf0..18122f160`,
encadre par `ExecutionerPlaybook$$.ctor` avant et `InvocationOfMachineVengeancePlaybook$$
EvaluateNonComparable` apres) : `EvaluateNonComparable`, `.cctor`, `.ctor`. RIEN d'autre n'est emis
entre eux -- aucun `CreateTrigger` / `CreateActiveCondition` / `CreateTargetSelector` fondu ne s'y
cache. (Le recensement par bloc est ce qui distingue une classe a 3 corps d'une classe dont un corps
a ete FONDU ailleurs : cf. `FragBombPlaybook$$ShouldExecute`, qui siege au milieu du bloc de
`BasiliskBarragePlaybook`.)

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.ExemplarOfHatePlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))        # cctor : Fix64(1)
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition.MainTile):
        t = entities@+0x10                                             # la CIBLE
        if (UnitExtensions.HasTrait(t, 0xd = UnitTrait.Object)) continue
        u = Fix64.op_Implicit(1)
        u = u + Fix64.FromIntFraction(UnitExtensions.GetStat(t, 5 = StatType.Health,
                                                             1 = StatPart.CurrentPct, null), 100)
        if (!UnitExtensions.HasTrait(t, 0x3ec = UnitTrait.Infiltrate))
            u = u + Fix64.op_Implicit(2)
        if (UnitExtensions.HasTrait(t, 0x7ea = <pseudo-trait Chaos>))
            u = u + Fix64.op_Implicit(1)
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, t, u))
    return bucket

`IdunBattle.AI.Playbook.Loki.ExemplarOfHatePlaybook$$.cctor` : `<statics+0x00> = Fix64.op_Implicit(1)`.

Utilite dans `[1.0, 4.0]` : un plancher de 1, plus la FRACTION de PV courants de la cible, plus 2
si elle n'est PAS `Infiltrate`, plus 1 si elle est de grande-alliance `Chaos`. Le tri est donc
d'abord « pas Infiltrate » (+2 domine tout le reste), puis « Chaos » (+1), puis les PV (< 1).

⚠ `0x7ea` N'EST PAS UN TRAIT GAMECONFIG. C'est le pseudo-trait de GRANDE-ALLIANCE Chaos
(`idun.Idun.Source.Shared.GrandAlliance$$GetTrait` : Imperial=0x1a, Xenos=0x3ee, Chaos=0x7ea), pose
par le BattleConfiguration et recopie dans `BaseUnitComponent.Traits` (+0x40) par
`IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent`. Un `HasTrait` naif sur la liste
`traits` du gameconfig serait TOUJOURS faux et la branche Chaos serait MORTE -- c'est exactement le
piege que la face COMBAT documente deja (`runner/abilities/darkangels.py`, `CHAOS_FACTIONS`). Le
port derive donc du `GrandAllianceId`, comme `adjacent_unit_preference._has_trait`.

⚠ `statPart = 1 = CurrentPct`, PAS `Current`. `MindControlPlaybook` (meme forme apparente,
`GetStat(target, 5, …)`) lit `statPart = 0 = Current` : la ou 1164 classe par PV BRUTS, 1140 classe
par POURCENTAGE, et le terme y est borne a `< 1` -- donc il ne departage que des cibles a egalite
sur les deux drapeaux. Confondre les deux `StatPart` ne leve aucune erreur et donne un ordre
different des que deux cibles ont des `maxHp` distincts.

DOMAINE DE CIBLE -- l'ENNEMI, et l'eligibilite est POSITION-INDEPENDANTE
------------------------------------------------------------------------
`...ExemplarOfHateAbility$$.ctor` : `TargetingOptions..ctor(&opts, 0, &statsFromClass, 1, 0x6004000,
0, 0, 0)` = `TargetIsEnemy | AllowObscuredTargetByElevation | AllowObscuredTargetByWalls`, sur le
preset `useWholeBoard` (cf. `runner/abilities/darkangels.ExemplarOfHateAbility.TARGETING_OPTIONS`,
litteral deja relu la). Aucune portee, aucune ligne de vue => **l'ensemble des cibles eligibles est
le MEME depuis toute position candidate**, et l'utilite ne lit ni la position ni le caster.

Consequence, avec `IdunBattle.AI.BucketSystem.Bucket<…>$$AddAction` (SEED le 1er ajoute puis ne
remplace que si STRICTEMENT superieur) et `ctx.reach_nc` en ORIGINE D'ABORD : le maximum est atteint
des la premiere position, donc le natif caste SANS BOUGER. D'ou `to = None`.

VOIE D'ENUMERATION : `abilityTargets(uid, 1140).fromHere` -- le mirror de
`GetEligibleTargetsSelectable(caster, casterPosition.MainTile)` a la position courante, la meme voie
que `UnbreakableDuty` / `ThriceBlessedConflagration` / `ExemplarOfTheMontka`. PAS le plan
`computeAttackPlans` : 1140 est `AbilityAttackType.Others` (`runner/abilities/attack_type.py`), donc
rien ne garantit qu'elle y figure -- et un port branche sur un plan vide serait MUET sans erreur.

BORNES DE PORT, nommees
------------------------
* `ctx.ability_targets is None` (aucun RPC) -> `[]`. NON MESURE, jamais un candidat invente.
* PV% : le natif lit `FillUpStatComponent.GetStatPart(CurrentPct)` = `round(cur/max*100)` ; le port
  le recalcule depuis `obs_units[].hp` / `.hpMax` (meme derivation que `BloodChalicePlaybook`).
  Ligne absente -> 100 % (unite pleine), le meme defaut que 1175.
* Les traits accordes/retires EN COURS de bataille (`AddTraitOperation`, `BaseUnitComponent+0x48` /
  `+0x50`) ne sont pas dans ce substrat : meme limite que `adjacent_unit_preference._has_trait`.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait

from ._base import NCContext, NonComparablePlaybook, _traits, _unit_cfg


#: Les trois pseudo-traits que `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` DERIVE du
#: `GrandAllianceId` -- ils n'existent PAS dans la liste `traits` du gameconfig (foyer jumeau :
#: `playbook/adjacent_unit_preference._GRAND_ALLIANCE_TRAITS`).
_GRAND_ALLIANCE_TRAITS: dict[int, str] = {
    int(UnitTrait.Imperial): "Imperial",      # 0x1a  = 26
    int(UnitTrait.Xenos): "Xenos",            # 0x3ee = 1006
    int(UnitTrait.Chaos): "Chaos",            # 0x7ea = 2026
}


def _has_trait(visual_id, trait: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasTrait(u, <UnitTrait>)` ->
    `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`, restreint au substrat DECISION.

    Deux voies, dans l'ordre du natif : la liste `traits` du gameconfig (= `Traits` +0x40 tel que le
    kit le pose), puis -- pour les TROIS pseudo-traits d'alliance seulement -- le `GrandAllianceId`,
    que le BattleConfiguration ajoute au meme champ."""
    name = _GRAND_ALLIANCE_TRAITS.get(int(trait))
    if name is None:
        return UnitTrait(int(trait)).name in (_traits(visual_id) or ())
    return (_unit_cfg(visual_id) or {}).get("GrandAllianceId") == name


class ExemplarOfHatePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.ExemplarOfHatePlaybook` (0x474 = 1140, `darkaAsmodai`).

    Utilite = `1 + PV%(cible)/100 + 2*(cible NON Infiltrate) + 1*(cible Chaos)`, cible `Object`
    ECARTEE. Position-INDEPENDANTE -> cast en place (`to = None`)."""

    ABILITY_ID = int(ActiveAbilityType.ExemplarOfHate)   # 0x474 = 1140 (argument du ctor natif)
    MIN_UTILITY = 1.0     # `...ExemplarOfHatePlaybook$$.cctor` : `Fix64$$op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """Le corps de la boucle native, terme a terme. Rend `None` pour une cible `Object` --
        le `continue` du natif, donc AUCUNE action pour elle (et non une utilite basse)."""
        vis = self._visual_id(ctx, target)
        if _has_trait(vis, int(UnitTrait.Object)):          # `HasTrait(t, 0xd)` -> `continue`
            return None
        u = 1.0                                             # `Fix64.op_Implicit(1)`
        # `Fix64.FromIntFraction(GetStat(t, Health, CurrentPct), 100)`
        u += self._hp_pct(ctx, target) / 100.0
        if not _has_trait(vis, int(UnitTrait.Infiltrate)):  # `!HasTrait(t, 0x3ec)` -> `+ Fix64(2)`
            u += 2.0
        if _has_trait(vis, int(UnitTrait.Chaos)):           # `HasTrait(t, 0x7ea)`  -> `+ Fix64(1)`
            u += 1.0
        return u

    @staticmethod
    def _visual_id(ctx: NCContext, target) -> str | None:
        for u in (ctx.obs_units or []):
            if u.get("squadId") == target:
                return u.get("visualId")
        for u in (ctx.units or []):
            if u.get("id") == target:
                return u.get("visualId")
        return None

    @staticmethod
    def _hp_pct(ctx: NCContext, target) -> int:
        """`GetStat(t, 5 = Health, 1 = CurrentPct)` = `FillUpStatComponent$$GetStatPart(CurrentPct)`
        = `round(cur / max * 100)`. Meme derivation que `BloodChalicePlaybook` ; ligne absente ->
        100 (unite pleine), pas 0 -- un 0 fabrique depuis une NON-MESURE deplacerait l'argmax."""
        for u in (ctx.obs_units or []):
            if u.get("squadId") != target:
                continue
            mx = int(u.get("hpMax") or 0)
            cur = int(u.get("hp") or 0)
            return round(cur / mx * 100) if mx > 0 else 100
        return 100

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`ActiveAbilityActionGenerator` + `Bucket$$ChooseAction` sur le domaine ENNEMI.

        L'eligibilite ET l'utilite etant toutes deux position-independantes (cf. l'en-tete), le
        maximum est deja atteint a l'ORIGINE -- premiere entree de `ctx.reach_nc` -- et
        `Bucket$$AddAction` ne remplace que sur amelioration STRICTE. On enumere donc `fromHere`
        UNE fois, dans l'ordre natif du selecteur, et on garde le premier maximum."""
        if ctx.ability_targets is None:
            return []                                   # NON MESURE -> aucun candidat invente
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        best = None                                     # (target, util)
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("fromHere") or []):
                    tid = t.get("targetId")
                    if tid is None:
                        continue
                    util = self.evaluate_non_comparable(ctx.origin, tid, ctx)
                    if util is None or util < self.MIN_UTILITY:
                        continue                        # `continue` natif / gate `AddAction`
                    if best is None or util > best[1]:  # strict `>` : le 1er max garde
                        best = (tid, util)
        if best is None:
            return []
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None, "pred": best[1]}]
