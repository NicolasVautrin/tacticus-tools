"""SternguardFocusPlaybook -- face DECISION de `1228 SternguardFocus` (`darkaSternguard`). #969."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.unit_faction import UnitFaction
from engine.playbook import adjacent_unit_preference as AUP

import engine.playbook.noncomparable._targets as T
from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first


class SternguardFocusPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.SternguardFocusPlaybook` -- MIRROR du decompile.

    ⚠ **BASE `NonComparablePlaybook`1`, LUE dans `frida/classes.tsv`** ; le `.ctor` decompile en
    `ComparablePlaybook<...>..ctor(this, 0x4cc)` (corps gshared DEDUPLIQUE). `0x4cc = 1228`.

    `...SternguardFocusPlaybook$$.cctor` : `<statique +0x00> = Fix64.op_Implicit(1)`
    -> `MIN_UTILITY = 1`.

    `...SternguardFocusPlaybook$$EvaluateNonComparable(caster, casterPosition, abilityState)` :

        bucket = new Bucket<UnitAction>( priority: 0, minUtility: Nullable(<statique> = 1) );
        foreach (var e in BasePlaybook$$GetEligibleTargetsSelectable(this, caster, casterPosition))
        {
            var utility = Fix64.op_Implicit(1);
            if (this.HasAdjacentDarkAngels(caster,
                                           AbilityEntities$$get_CasterPosition(e)))
                utility = utility + Fix64.op_Implicit(10);
            bucket.AddAction( BasePlaybook$$GenerateAction(this, casterPosition, e.Target, utility) );
        }
        return bucket;

    => **utilite = 1, + 10 si un AUTRE Dark Angel ami est adjacent a la POSITION DU CASTER**.

    ⚠ **LE TERME `+10` EST CONSTANT SUR LES CIBLES ET VARIABLE SUR LES POSITIONS -- ET C'EST BIEN
    L'INVERSE DU PIEGE HABITUEL.** Il est calcule DANS la boucle des cibles, ce qui donne l'illusion
    qu'il les departage ; son argument est `e.CasterPosition`, identique pour tous les elements d'un
    meme appel (le selecteur est evalue POUR UNE position). Il ne peut donc RIEN departager entre
    cibles -- a une position donnee, toutes les cibles ont la meme utilite et c'est la PREMIERE
    enumeree qui gagne (`Bucket$$AddAction` ne remplace que sur `>` STRICT). En revanche
    `EvaluateNonComparable` est rappele PAR POSITION candidate : le `+10` departage les POSITIONS.
    La preuve n'est pas << le calcul est dans la boucle >>, c'est **ce que l'argument designe** --
    la lecon inverse et symetrique de #957 (terme hors boucle qui, lui, departageait).

    Consequence concrete : **le Sternguard SE DEPLACE** vers une tuile flanquee d'un Dark Angel ami
    avant de tirer ; `to` n'est pas `None`.

    `...SternguardFocusPlaybook$$HasAdjacentDarkAngels(unit, target)` -- MIRROR :

        foreach (var u in <IBattleQuery slot 132>.GetAdjacentFriends(target, unit))
            if (u != unit && UnitExtensions$$HasFaction(u, 10 = UnitFaction.DarkAngels))
                return true;
        return false;

    (slot LU dans `metadata/interface_slots.tsv` : `IBattleQuery 132 GetAdjacentFriends 2` ; l'ordre
    des arguments est LU au call-site : `(target, unit)`, soit << les amis de `unit` adjacents a la
    tuile `target` >>.)

    `...SternguardFocusPlaybook$$GetUseProbability(unit, actionTiles)` -- surcharge du slot `0x208`,
    celui que consulte `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate(unit, actionTiles)`
    (l'autre `ShouldEvaluate`, a UN parametre, passe par le slot `0x1f8` -- les deux corps ont ete
    relus cote a cote) :

        foreach (var tile in actionTiles)
            if (this.HasAdjacentDarkAngels(unit, tile)) return <Fix64 statics +0x20>;
        return Fix64.FromIntFraction(75, 100);

    ⚠ **AUCUN REFUS DETERMINISTE ICI, ET C'EST UNE LECTURE.** Les deux valeurs rendues sont
    strictement positives (`0.75`, et un statique de `Fix64` qui ne peut valoir zero puisqu'il
    recompense la presence d'un allie), donc `prob <= 0` n'arrive JAMAIS : `ShouldEvaluate` ne
    refuse pas, il tire. Le port laisse donc `should_evaluate` au defaut `True` -- ce n'est pas un
    gate oublie, c'est le gate ABSENT. Contraste avec `WarHowlPlaybook` et
    `CrusadeOfWrathPlaybook`, ou le zero existe et EST porte.

    ⚠ **LA CIBLE EST UN ENNEMI** : `...SternguardFocusAbility$$.ctor` pose
    `TR.TargetMatchesDynamicRule | TR.TargetIsEnemy`, `self_cast = False` (cf.
    `runner/abilities/darkangels.py`). L'ability arme une ATTAQUE NORMALE sur elle
    (`AddTemporaryAttackOverrideEffect` -> `UseNormalAttack` -> `Reset`, #905) ; le playbook, lui,
    ne lit NI les PV NI l'armure de la cible : son seul discriminant est ou se tient le caster.

    `PRIORITY` reste au defaut `0` (`AbilityPriority.Normal`) : `1228` est ABSENTE de
    `NATIVE_PRIORITY` (22 entrees, sweep #170)."""
    ABILITY_ID = int(ActiveAbilityType.SternguardFocus)   # 1228 = 0x4cc (argument du ctor natif)
    MIN_UTILITY = 1.0                                     # `...SternguardFocusPlaybook$$.cctor`
    #: `Fix64.op_Implicit(10)` du `utility + Fix64(10)` -- le bonus << un Dark Angel me couvre >>.
    _ADJACENT_DARK_ANGEL_BONUS = 10.0

    @staticmethod
    def _visual_by_pos(ctx: NCContext) -> dict:
        """`{(col, row): visualId}` des unites VIVANTES -- le substrat de `HasFaction`.

        Source `ctx.obs_units` (`observeBattle.units`), qui porte `visualId` ; `decisionView` garde
        les depouilles (cf. `project_decisionview_keeps_dead`), d'ou le filtre `isDead`."""
        out: dict = {}
        for u in (ctx.obs_units or []):
            if u.get("isDead"):
                continue
            c, r = u.get("col"), u.get("row")
            if c is None or r is None:
                continue
            out[(c, r)] = u.get("visualId")
        return out

    def _has_adjacent_dark_angels(self, ctx: NCContext, tile: tuple, vis_by_pos: dict) -> bool:
        """`HasAdjacentDarkAngels(caster, tile)` : un ami (caster exclu) adjacent a `tile` dont la
        faction est `UnitFaction.DarkAngels`.

        ⚠ **ADJACENCE = LE FOYER, PAS `hexgeo.distance == 1`.** `GetAdjacentFriends` descend sur
        `GetAdjacentTiles` -> `TileQuery.<IterateAdjacentTiles>` : liste d'adjacence STOCKEE du
        board PLUS la porte d'elevation `|dElev| < 2`. `engine.battle_query.is_adjacent` EST ce
        foyer et degrade seul vers `hexgeo` quand les canaux sont vides. (C'est bien un
        `GetAdjacent*`, pas un `GetSurrounding*` : les deux ne se portent PAS pareil -- cf.
        `CrusadeOfWrathPlaybook._buff_targets_count`, qui est geometrique.)

        `ctx.fpos` exclut DEJA le caster (`engine.ai.context` : `id != uid`), ce qui EST le
        `u != unit` du natif."""
        neigh = bq.neigh_map(ctx)
        for f in (ctx.fpos or ()):
            if not bq.is_adjacent(tile, f, ctx.elev_by_pos, neigh):
                continue
            vis = vis_by_pos.get(tuple(f))
            if vis is None:
                continue
            # Foyer PARTAGE de `HasFaction` (chaine `FactionId` du gameconfig, jamais un entier --
            # le natif compare `Enum.ToString(UnitFaction)` au champ `FactionComponent+0x30`).
            if AUP._unit_faction({"vis": vis}) == UnitFaction.DarkAngels.name:
                return True
        return False

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """Sweep natif : positions (ORIGINE en tete) x cibles eligibles (ordre du selecteur).

        L'utilite ne depend PAS de la cible, donc a chaque position la PREMIERE cible enumeree
        l'emporte ; entre positions, `+10` tranche. `_targets.eligible_units` rend une LISTE (jamais
        un `set` : le hachage deciderait de l'argmax -- le cran trouve par #957).

        ECART NOMME, commun aux appelants de `_targets` : `fromHere` n'enumere les cibles que depuis
        l'ORIGINE, la ou le natif re-selectionne par position. Ici l'effet est BORNE -- l'utilite
        etant cible-independante, une cible manquante ne peut pas changer le CHOIX DE POSITION ; elle
        ne pourrait changer que l'identite de la cible emise depuis une tuile de move d'ou d'autres
        ennemis seraient a portee."""
        cibles = T.eligible_units(ctx, self.ABILITY_ID)
        if not cibles:
            return []
        premiere = cibles[0][0]                        # keep-first a utilite egale
        vis_by_pos = self._visual_by_pos(ctx)
        best_p, best_u = None, None
        for P in _sweep_origin_first(ctx):
            u = 1.0                                    # `Fix64.op_Implicit(1)`
            if self._has_adjacent_dark_angels(ctx, P, vis_by_pos):
                u += self._ADJACENT_DARK_ANGEL_BONUS   # `utility + Fix64.op_Implicit(10)`
            if u < self.MIN_UTILITY:                   # admission `Bucket$$AddAction`
                continue
            if best_u is None or u > best_u:           # `>` STRICT -> keep-first (origine gagne)
                best_p, best_u = P, u
        if best_p is None:
            return []
        return [{"target": premiere, "ability": self.ABILITY_ID,
                 "to": (None if best_p == ctx.origin else best_p), "pred": best_u}]
