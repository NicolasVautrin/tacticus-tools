"""`ExemplarOfTheMontkaPlaybook` (0x4ba = 1210, `tauFarsight`) -- face DECISION.

REACHABILITY, LUE ET NON SUPPOSEE
---------------------------------
`data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` (extrait de
`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`) :

    active   1210   IdunBattle.AI.Playbook.Loki.ExemplarOfTheMontkaPlaybook

Une SEULE entree, dans le dict `active` (+0x68) -- rien dans `triggered`, `nonowner` ni
`specific`. Ce playbook n'est donc PAS du code registered-but-dead, et il n'a PAS de face
non-owner (celle-ci n'existe que pour la famille `TriggeredAbilityNonOwnerPlaybook<T>`).

BASE DE HIERARCHIE -- `NonComparablePlaybook<T>`, et le `.ctor` ne le dit PAS
-----------------------------------------------------------------------------
Ghidra nomme le `.ctor` `ComparablePlaybook<...>$$.ctor(this, 0x4ba, klass)` : c'est un corps
trivial DEDUPLIQUE, le meme piege que #487-r1 et qu'`UnbreakableDuty`. Le discriminant est la
METHODE SURCHARGEE, pas le nom du ctor -- la classe declare
`IdunBattle.AI.Playbook.Loki.ExemplarOfTheMontkaPlaybook$$EvaluateNonComparable`, dont la
signature `(caster, casterPosition, abilityState) -> Bucket<UnitAction>` est celle de
`NonComparablePlaybook<T>`. Le `0x4ba` du ctor est l'`ability_id` -- LU la, jamais devine du nom.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.ExemplarOfTheMontkaPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))       # cctor : Fix64(1)
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition):
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10,
                                                     Fix64.op_Implicit(1)))
    return bucket

Utilite CONSTANTE, et c'est le MEME `Fix64(1)` que le plancher du Bucket -- structure IDENTIQUE
a `UnbreakableDutyPlaybook$$EvaluateNonComparable`, a une difference pres : 1061 relit le statique
`<statics+0x00>` pour l'utilite, 1210 reconstruit `Fix64.op_Implicit(1)` a chaque iteration. Meme
valeur, donc meme comportement -- le gate `Bucket$$AddAction` (`util >= min`) passe toujours et
toutes les cibles eligibles sont a EGALITE. Tout le discriminant est dans `ShouldEvaluate`.

`IdunBattle.AI.Playbook.Loki.ExemplarOfTheMontkaPlaybook$$.cctor` :

    <statics+0x00> = FixMath.NET.Fix64$$op_Implicit(1)

LE GATE -- `ShouldEvaluate`, SURCHARGE DIRECTE DU SLOT 4 (pas un `GetUseProbability`)
--------------------------------------------------------------------------------------
    ShouldEvaluate(this, unit)  =>  return HasNormalAttackTarget(this, unit);

C'est un ECART DE FORME avec `UnbreakableDuty` (qui, lui, passe par
`BasePlaybook$$ShouldEvaluate` + un `GetUseProbability` en pourcents) : ici le slot 4 est
surcharge par un predicat BINAIRE, sans tirage aleatoire. Il n'y a donc AUCUNE porte aleatoire a
ne pas modeliser -- le port peut etre exact.

`IdunBattle.AI.Playbook.Loki.ExemplarOfTheMontkaPlaybook$$HasNormalAttackTarget`, verbatim :

    naType = UnitExtensions.GetNormalAttackType(unit)
    res    = <IBattleQuery slot 0x45>(unit, naType, false)
    foreach (kv in res.<+0x18> as Dictionary<UnitPosition, List<IEntity>>)
        foreach (target in kv.Value)
            casterTile = kv.Key.get_MainTile()
            if (!BasePlaybook.WillNormalAttackKill(this, unit, target, casterTile))
                return true
    return false

⚠ **LE NOM MENT SUR LA SEMANTIQUE, ET C'EST LU** : ce n'est pas « ai-je une cible d'attaque
normale ? » mais « ai-je une cible que mon attaque normale NE TUE PAS ? ». La negation est dans le
corps (`if (!WillNormalAttackKill) return true`). Le sens tactique est celui des quinze
`ShouldExecute` du gisement `normal_attack_kill_gate` -- ne pas depenser une ability sur une cible
que la frappe de base acheve deja -- mais applique ici en AMONT, au slot 4, et sur un buff.

Le slot `0x45` est RESOLU, pas suppose : `data/symbols/rnca9r7q6c/metadata/interface_slots.tsv`
donne `IBattleQuery 69 (0x45) GetAllValidTargetsFromAllPossibleMovementTiles 3 params` -- d'ou la
forme du retour (une carte POSITION -> cibles, l'union sur toutes les tuiles de move).

BORNES DE PORT, nommees
------------------------
* La carte `{position: [cibles]}` n'est publiee par AUCUN canal offline. `abilityTargets` publie
  `targets` (l'UNION, = l'ensemble des valeurs du dict natif) et `fromHere` (les cibles depuis la
  seule position COURANTE). Le port itere l'UNION -- le bon ensemble de cibles -- et reconstruit
  les positions par `ctx.cast_from_tiles(uid, target, naId)` quand la seam est cablee ; sinon il
  teste depuis l'ORIGINE seule. Comme le natif rend `true` des qu'UNE paire (position, cible)
  survit, l'ecart est une borne INF : le port peut rendre `false` la ou le natif rend `true`, si
  la seule cible survivante n'est atteignable qu'apres deplacement ET que la seam manque.
* `WillNormalAttackKill` n'est pas re-porte : le foyer `engine.playbook.base.
  will_normal_attack_kill` sert deja la route Comparable (les 15 playbooks de
  `normal_attack_kill_gate`) et la route NonComparable (`_base._will_normal_attack_kill`).
  Predicteur absent -> il rend `false`, donc `not false = true` : le gate ne refuse pas a
  l'aveugle. Meme polarite que `_turns_started_gate`.
* `ability_targets` absent (aucun RPC) -> `True`, pour la meme raison : un `False` fabrique
  depuis une NON-MESURE retirerait un cast que le natif fait. C'est aussi, exactement, le
  comportement d'avant ce module (1210 n'avait aucune entree au registre NonComparable).
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _normal_attack_ids, _will_normal_attack_kill


class ExemplarOfTheMontkaPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.ExemplarOfTheMontkaPlaybook` (0x4ba = 1210, `tauFarsight`).

    Utilite CONSTANTE = `MIN_UTILITY` = `Fix64(1)` : le playbook ne DEPARTAGE rien, il dit
    seulement << castable ici >>. Tout le discriminant est dans `should_evaluate`."""
    ABILITY_ID = int(ActiveAbilityType.ExemplarOfTheMontka)   # 0x4ba = 1210
    MIN_UTILITY = 1.0     # `...ExemplarOfTheMontkaPlaybook$$.cctor` : `Fix64$$op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def should_evaluate(self, ctx: NCContext) -> bool:
        """`...ExemplarOfTheMontkaPlaybook$$ShouldEvaluate` = `return HasNormalAttackTarget(unit)`
        -- surcharge DIRECTE du slot 4, sans `GetUseProbability` et donc sans tirage."""
        return self._has_normal_attack_target(ctx)

    def _has_normal_attack_target(self, ctx: NCContext) -> bool:
        """`...ExemplarOfTheMontkaPlaybook$$HasNormalAttackTarget` -- << existe-t-il une cible
        d'attaque normale que cette attaque NE TUERAIT PAS ? >>. Cf. l'en-tete du module : le nom
        natif ment sur la semantique, la negation est dans le corps.

        Les CIBLES viennent de `<IBattleQuery slot 0x45> =
        GetAllValidTargetsFromAllPossibleMovementTiles(unit, naType, false)`, dont le mirror
        offline est `abilityTargets(uid, <naId>).targets` (l'UNION sur toutes les tuiles de move,
        = l'ensemble des valeurs de la carte native). Les POSITIONS viennent de
        `ctx.cast_from_tiles` quand la seam est cablee -- c'est la MEME carte, indexee dans
        l'autre sens ; sinon on retombe sur l'origine (borne INF nommee en en-tete)."""
        if ctx.ability_targets is None:
            return True                              # NON MESURE -> on ne gate pas a l'aveugle
        nids = _normal_attack_ids(ctx, ctx.uid)      # `UnitExtensions$$GetNormalAttackType(unit)`
        if not nids:
            return False                             # pas d'attaque normale -> la boucle native est vide
        for na_id in sorted(nids):
            at = ctx.ability_targets(ctx.uid, na_id) or {}
            for u in (at.get("units") or []):
                if u.get("unitId") != ctx.uid:
                    continue
                for a in (u.get("abilities") or []):
                    if a.get("abilityId") != na_id:
                        continue
                    for t in (a.get("targets") or []):
                        tid = t.get("targetId")
                        if tid is None:
                            continue
                        for pos in self._positions_for(ctx, tid, na_id):
                            # `if (!WillNormalAttackKill(unit, target, casterTile)) return true`
                            if not _will_normal_attack_kill(ctx, tid, pos):
                                return True
        return False

    @staticmethod
    def _positions_for(ctx: NCContext, target_id, na_id) -> list:
        """Les `kv.Key.get_MainTile()` de la carte native, pour UNE cible -- reconstruits par
        `castFromTiles` (le MEME predicat `AttackQuery$$GetInvalidTargetReason`, tuile par tuile,
        SANS troncature). Seam absente ou muette -> `[ctx.origin]`, la borne INF de l'en-tete."""
        cft = getattr(ctx, "cast_from_tiles", None)
        if cft is None:
            return [ctx.origin]
        try:
            res = cft(ctx.uid, target_id, na_id) or {}
        except Exception:
            return [ctx.origin]
        out = [ctx.origin] if res.get("currentValid") else []
        for t in (res.get("moveTiles") or []):
            if isinstance(t, dict):
                c, r = t.get("col"), t.get("row")
                if c is not None and r is not None:
                    out.append((c, r))
            elif isinstance(t, (list, tuple)) and len(t) == 2:
                out.append((t[0], t[1]))
        return out or [ctx.origin]

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`GenerateAction(casterPosition, entities@+0x10, Fix64.op_Implicit(1))` -- l'utilite est
        la MEME constante que `MIN_UTILITY`, pour TOUTE cible eligible. Aucune lecture de la cible,
        aucune lecture de la position : c'est ce que dit le corps, terme pour terme."""
        return self.MIN_UTILITY

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`ActiveAbilityActionGenerator` + `Bucket$$ChooseAction`, pour un cast **SELF**.

        Le masque de 1210 est `0x8004 = CasterIsPossibleTarget | CasterMatchesDynamicRule` sur
        `RANGE_SELF` (STATIC-COPY du preset `<TargetingOptions statics>+0x280`, cf.
        `runner/abilities/tau.py::ExemplarOfTheMontkaAbility`) : la seule cible eligible est le
        CASTER. Le generateur de `_PlanTargetPlaybook` ne conviendrait donc pas -- il enumere
        `ctx.plan["evals"]`, et `computeAttackPlans` ne boucle que sur les ENNEMIS. Voie employee,
        la MEME que `UnbreakableDuty` et `ThriceBlessedConflagration` :
        `abilityTargets(uid, 1210).fromHere` = le mirror de
        `BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition)`.

        L'utilite etant CONSTANTE, `Bucket$$AddAction` (remplacement STRICT `>`) garde le PREMIER
        ajoute : la premiere position de `reach_nc` -- l'ORIGINE -- et la premiere cible de
        l'enumeration native. D'ou `to = None` (cast en place) et l'arret a la premiere cible."""
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
                    tid = t.get("targetId")
                    if tid is None:
                        continue
                    util = self.evaluate_non_comparable(ctx.origin, tid, ctx)
                    if util is None or util < self.MIN_UTILITY:
                        continue
                    return [{"target": tid, "ability": self.ABILITY_ID, "to": None, "pred": util}]
        return []
