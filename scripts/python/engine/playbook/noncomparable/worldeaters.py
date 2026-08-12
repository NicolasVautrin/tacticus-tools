"""Les deux playbooks NonComparable WorldEaters de #977 -- `1131 JakhalStimms` (`worldJakhal`
« Macer ») et `1141 OverwhelmingWrath` (`worldEightbound` « Azkor »).

Ils partagent EXACTEMENT un etage : leurs deux `EvaluateNonComparable` enumerent
`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition.MainTile)`
-- la liste des cibles legales POUR LA POSITION BALAYEE -- et leurs deux masques sont
`TargetIsEnemy` + `TargetingRange` ADJACENT (relus dans `runner/abilities/worldeaters.py`, ou ils
vivent deja pour la face COMBAT). Ce lecteur-la vit dans le foyer du paquet
(`_targets.eligible_units_at_position`), pas ici : `1043 ThunderousAssault`, d'une AUTRE faction,
en a besoin a l'identique.

BASE LUE DANS `data/symbols/<build>/frida/classes.tsv`, JAMAIS dans le nom du corps de `.ctor` :

    IdunBattle.AI.Playbook.Loki.JakhalStimmsPlaybook       -> IdunBattle.AI.Playbook.NonComparablePlaybook`1
    IdunBattle.AI.Playbook.Loki.OverwhelmingWrathPlaybook  -> IdunBattle.AI.Playbook.NonComparablePlaybook`1

alors que ghidra etiquette LES DEUX corps de `.ctor`
`ComparablePlaybook<__Il2CppFullySharedGenericType>$$.ctor` (corps gshared partage : il ne fait que
relayer `Playbook<T>..ctor(<id>)`). Les ids y sont lus : `0x46b` = 1131, `0x475` = 1141.

MIN_UTILITY : les DEUX declarent un `.cctor` propre qui ecrit `Fix64(1)` dans leur premier static,
et leur `EvaluateNonComparable` relit CE static pour le passer au `Bucket<T>..ctor` a TROIS
arguments (`(seedAction = 0, Nullable<Fix64> minUtility)`) -> `MIN_UTILITY = 1.0`. Le
`ComparablePlaybook<T>$$.cctor` qui ECRASE ce `1` par `Fix64(10)`
(`playbook/static_threshold_gate.py`) ne les concerne PAS : il est le `.cctor` de
`ComparablePlaybook`1`, absent de leur chaine d'heritage -- et `NonComparablePlaybook`1` n'a, lui,
AUCUN `.cctor` (recherche de symboles : `ComparablePlaybook<T>$$.cctor` existe, son homologue
NonComparable n'existe pas).
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import (NCContext, NonComparablePlaybook, _get_num_attack_targets_in_position,
                    _will_normal_attack_kill)
# Forme B : un import from ._targets import <nom> GELERAIT la liaison au chargement -- une contre-epreuve
# qui substitue le foyer deviendrait MUETTE, en silence (mesure #977 : deux mutations d'ordre
# n'ont RIEN mordu tant que cet import etait en forme A).
from . import _targets as _T


class JakhalStimmsPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.JakhalStimmsPlaybook$$EvaluateNonComparable` (id 0x46b = 1131,
    `worldJakhal` « Macer », WorldEaters).

    CORPS NATIF, relu VERBATIM (le gate est INLINE dans la boucle ; le corps NOMME
    `JakhalStimmsPlaybook$$IsDisallowedTarget` en est la forme factorisee, avec le MEME predicat) :

        bucket = new Bucket(0, Nullable(MIN_UTILITY))                 # .cctor = Fix64(1)
        foreach entities in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition.MainTile):
            n    = JakhalStimmsAbility$$GetAdjacentTargets().<slot itf 2 = Count>(entities)
            util = Fix64(1) + Fix64(n)
            if (!IsDisallowedTarget(entities, n))
                bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, entities.Target, util))

        bool IsDisallowedTarget(entities, n) {
            return BasePlaybook$$WillNormalAttackKill(entities)                 // sure-kill de la normale
                && !(n > 0)                                                     // aucun ennemi en AoE
                && (battleQuery.<slot itf 0x7f>(caster, casterTile).Count - 1) < 1;   // <= 1 cible normale
        }

    ## Le set d'AoE est le MEME que celui de la face COMBAT, et c'est MESURE, pas suppose

    `IdunBattleLogic.Entities.Abilities.Active.Loki.JakhalStimmsAbility$$GetAdjacentTargets` est

        DSLSelectors.AdjacentUnits(<CasterTile>) & DSLSelectors.AdjacentFriends(<TargetTile>)

    et `...JakhalStimmsAbility$$ExecuteBehaviour` construit la MEME expression, avec les MEMES deux
    selecteurs caches (`dsl+0x50` / `dsl+0x60`) et le MEME `TargetsSelector$$op_BitwiseAnd`. Le port
    COMBAT en a deja le mirror (`runner/abilities/worldeaters.py::jakhal_stimms_tree` :
    `And(AdjacentUnits(CasterTile()), AdjacentEnemies(TargetTile()))`) -- « amis de la CIBLE » etant,
    du point de vue du caster, « ennemis du caster ». `GetAdjacentTargets` n'a QU'UN appelant, ce
    playbook (xrefs) : les deux faces ne peuvent donc diverger que si l'une des deux se trompe.

    L'utilite est donc `1 + (nombre d'ennemis qui prennent l'AoE en plus de la cible)` : Macer
    prefere la cible qui maximise le splash, et le `1` plancher garantit l'admission au `Bucket`
    (`MIN_UTILITY = 1`) des qu'une cible est legale.

    ## Le gate n'est PAS « ne gaspille pas sur une cible deja morte »

    Les TROIS clauses doivent etre vraies ENSEMBLE pour refuser. Le natif ne saute la cible que si
    (a) l'attaque NORMALE la tue a coup sur, (b) l'AoE ne toucherait personne d'autre, ET (c) le
    caster n'a QU'UNE cible d'attaque normale depuis cette tuile. La clause (c) est ce qui rend le
    gate rare : des que Macer a deux cibles normales possibles, 1131 reste propose meme sur une
    cible sure-killable. Ecrire seulement (a) -- l'erreur naturelle, celle de `KillMaimBurn` --
    aurait supprime l'ability dans presque tous les regimes de fin de combat.

    Le slot `0x7f` est le MEME que celui de `TheQuickeningPlaybook$$GetNumAttackTargetsInPosition`,
    et le port a deja son mirror (`_base._get_num_attack_targets_in_position`).

    ## Position / cible

    Sweep `ctx.reach_nc` (ORIGINE en tete, ordre movable natif) x cibles eligibles de la position ;
    `Bucket.AddAction` keep-first sur `>` STRICT."""

    ABILITY_ID = int(ActiveAbilityType.JakhalStimms)   # 1131 = 0x46b
    MIN_UTILITY = 1.0     # IdunBattle.AI.Playbook.Loki.JakhalStimmsPlaybook$$.cctor = Fix64(1)
    PRIORITY = 0          # 1131 hors `NATIVE_PRIORITY` (sweep exhaustif #170) -> AbilityPriority.Normal

    def aoe_count(self, ctx: NCContext, P: tuple, tpos: tuple) -> int:
        """`Count(AdjacentUnits(P) & AdjacentFriends(targetTile))` -- les ennemis du caster
        adjacents A LA FOIS a la tuile de cast et a la cible. La cible elle-meme n'y est pas (elle
        n'est pas adjacente a sa propre tuile) et le caster non plus (il n'est pas un ami de la
        cible). Porte d'adjacence = `bq.is_adjacent` (|dElev| < 2 + voisinage NATIF stocke)."""
        neigh = bq.neigh_map(ctx)
        n = 0
        for e in (ctx.epos or []):
            if e == tpos:
                continue
            if bq.is_adjacent(P, e, ctx.elev_by_pos, neigh) and \
               bq.is_adjacent(tpos, e, ctx.elev_by_pos, neigh):
                n += 1
        return n

    def is_disallowed_target(self, ctx: NCContext, P: tuple, target, n: int) -> bool:
        """`JakhalStimmsPlaybook$$IsDisallowedTarget` -- les TROIS clauses, dans l'ordre natif
        (court-circuit compris : sans le sure-kill, aucune des deux autres n'est evaluee)."""
        if not _will_normal_attack_kill(ctx, target, P):
            return False
        if n > 0:
            return False
        return (_get_num_attack_targets_in_position(ctx, ctx.uid, P) - 1) < 1

    def evaluate_at(self, ctx: NCContext, P: tuple):
        """`EvaluateNonComparable(caster, UnitPosition(P))` -> `(target, util)` = le `best` du
        `Bucket` LOCAL a cette position, ou `None` (bucket vide).

        C'est l'unite de mesure de l'oracle `ncEvaluate`, qui invoque exactement ce corps par
        position -- d'ou son existence separee de `generate_candidates` (le generateur, qui
        fusionne les buckets de toutes les positions)."""
        best = None       # (target, util)
        for tgt, tpos in _T.eligible_units_at_position(ctx, self.ABILITY_ID, P):
            if tpos is None:
                continue
            n = self.aoe_count(ctx, P, tpos)
            util = 1.0 + float(n)                 # `Fix64(1) + Fix64(count)`
            if self.is_disallowed_target(ctx, P, tgt, n):
                continue                          # aucune action pour cette cible
            if util < self.MIN_UTILITY:
                continue                          # admission `Bucket.AddAction`
            if best is None or util > best[1]:    # strict > : premiere cible du max gagne
                best = (tgt, util)
        return best

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        best = None       # (target, tile, util)
        for P in (ctx.reach_nc or []):            # ORIGINE en tete puis moves (ordre natif)
            r = self.evaluate_at(ctx, P)
            if r is None:
                continue
            if best is None or r[1] > best[2]:    # strict > : premiere position du max gagne
                best = (r[0], P, r[1])
        if best is None:
            return []
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] JakhalStimms pos={best[1]} tgt={best[0]} u={best[2]}",
                  file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID,
                 "to": (best[1] if best[1] != ctx.origin else None), "pred": best[2]}]


class OverwhelmingWrathPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.OverwhelmingWrathPlaybook$$EvaluateNonComparable` (id 0x475 =
    1141, `worldEightbound` « Azkor », WorldEaters).

    CORPS NATIF, relu VERBATIM -- et il ne BOUCLE PAS sur les cibles :

        bucket  = new Bucket(0, Nullable(MIN_UTILITY))            # .cctor = Fix64(1)
        targets = BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition.MainTile)
        if (targets.Count > 0) {                                  # `List<T>._size`, lu au champ
            util  = Fix64(targets.Count)
            first = System.Linq.Enumerable$$First(targets)
            bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, first.Target, util))
        }
        return bucket

    UNE SEULE action par position, dont l'utilite est le NOMBRE de cibles eligibles et dont la cible
    est la PREMIERE de la liste. C'est coherent avec l'ability : la phase 1 pose un Taunt sur TOUS
    les ennemis adjacents (`runner/abilities/worldeaters.py::overwhelming_wrath_tree`), donc la
    « cible » du message n'est qu'un porteur -- ce qui compte est de se placer la ou il y a le plus
    d'ennemis a provoquer.

    Le test `> 0` sur le COMPTE est ce qui remplace ici la boucle : `MIN_UTILITY = 1` le redouble
    exactement (`Count >= 1`), donc le gate du `Bucket` n'ajoute aucune contrainte.

    ## Le masque, et le volet self-cast

    `...OverwhelmingWrathAbility$$.ctor` (deja relu pour la face COMBAT) :
    `TargetingOptions..ctor(&opts, isSelfCasting = 1, range = <TargetingRange statics+0x30> =
    ADJACENT, forceMeleeTarget = 1, rules = 0x4000 = TargetIsEnemy, 0, 0)`. Le `isSelfCasting = 1`
    fait que `GetValidTargets` AJOUTE le caster aux cibles legales -- mais seulement s'il existe au
    moins une AUTRE cible (`0x800 AddCasterIfAtLeastOneTarget`, branche `else` de
    `TargetingQuery$$GetCasterNotAddedReason`, MESUREE en contre-epreuve G1 de
    `probe_503_generalisation.py` : sans ennemi adjacent le natif REFUSE le cast).

    Consequence DIRECTE sur l'utilite, et c'est le point le plus fragile de ce port : le natif
    COMPTE le caster dans `targets.Count`, donc l'utilite vaut `nAdjacents + 1`, pas `nAdjacents`.
    MESURE #977 (runner MC1_67/777, `worldEightbound` en (2,5), DEUX ennemis adjacents) :
    `abilityTargets.fromHere` rend `[86, 90, 80]` et `ncEvaluate` rend `util = 3`. Le caster est
    donc bien dans le compte, et il y est EN DERNIER -- ce rang decide de la cible emise, puisque
    le corps ne garde que `First(targets)`. C'est `_targets.eligible_units_at_position(...,
    self_cast=True)` qui porte les deux faits."""

    ABILITY_ID = int(ActiveAbilityType.OverwhelmingWrath)   # 1141 = 0x475
    MIN_UTILITY = 1.0     # IdunBattle.AI.Playbook.Loki.OverwhelmingWrathPlaybook$$.cctor = Fix64(1)
    PRIORITY = 0          # 1141 hors `NATIVE_PRIORITY` (sweep exhaustif #170) -> AbilityPriority.Normal

    def evaluate_at(self, ctx: NCContext, P: tuple):
        """`EvaluateNonComparable(caster, UnitPosition(P))` -> `(target, util)` ou `None`.
        L'unite de mesure de l'oracle `ncEvaluate` (cf. le jumeau de `JakhalStimmsPlaybook`)."""
        targets = _T.eligible_units_at_position(ctx, self.ABILITY_ID, P, self_cast=True)
        if not targets:
            return None                           # `targets.Count > 0` : aucune action
        util = float(len(targets))                # `Fix64(targets.Count)`
        if util < self.MIN_UTILITY:
            return None
        return (targets[0][0], util)              # `Enumerable.First(targets)`

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        best = None       # (target, tile, util)
        for P in (ctx.reach_nc or []):            # ORIGINE en tete puis moves (ordre natif)
            r = self.evaluate_at(ctx, P)
            if r is None:
                continue
            if best is None or r[1] > best[2]:    # strict > : premiere position du max gagne
                best = (r[0], P, r[1])
        if best is None:
            return []
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] OverwhelmingWrath pos={best[1]} tgt={best[0]} "
                  f"u={best[2]}", file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID,
                 "to": (best[1] if best[1] != ctx.origin else None), "pred": best[2]}]
