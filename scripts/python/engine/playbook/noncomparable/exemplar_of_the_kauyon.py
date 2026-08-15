"""`ExemplarOfTheKauyonPlaybook` (0x43f = 1087, `tauShadowsun`) -- face DECISION, #975.

REACHABILITY, LUE ET NON SUPPOSEE
---------------------------------
`data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` :

    active   1087   IdunBattle.AI.Playbook.Loki.ExemplarOfTheKauyonPlaybook

UNE seule entree, dict `active` (+0x68). ⚠ L'ordinal 1087 est aussi `TriggeredAbilityType.
Diminutive` -- autre enum, autre entite. Le discriminant est l'ENUM, jamais l'entier.

BASE DE HIERARCHIE -- `NonComparablePlaybook<T>`, LUE dans `frida/classes.tsv`
------------------------------------------------------------------------------
    IdunBattle.AI.Playbook.Loki.ExemplarOfTheKauyonPlaybook  112  IdunBattle.AI.Playbook.NonComparablePlaybook`1

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.ExemplarOfTheKauyonPlaybook$$EvaluateNonComparable` :

    bucket   = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))    # cctor : Fix64(1)
    mainTile = casterPosition.get_MainTile()
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, mainTile):
        utility = Fix64.op_Implicit(1)
        if (HasEnemyInRange(entities))                               # <-- corps INLINE, cf. plus bas
            bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10, utility))
    return bucket

`IdunBattle.AI.Playbook.Loki.ExemplarOfTheKauyonPlaybook$$HasEnemyInRange(targetEntities)`, dont le
corps est INLINE dans `EvaluateNonComparable` ci-dessus (les deux decompiles sont superposables) :

    position = new UnitPosition(targetEntities@+0x10)                # LA TUILE VISEE
    list     = BasePlaybook.GetEligibleTargetsForNormalAttack(targetEntities@+0x08 = caster, position)
    return list.<+0x10>.Count > 0

`IdunBattle.AI.Playbook.Loki.ExemplarOfTheKauyonPlaybook$$.cctor` :

    <statics+0x00> = FixMath.NET.Fix64$$op_Implicit(1)

CE QUE LE GATE VEUT DIRE -- ET POURQUOI IL EST LA
--------------------------------------------------
`GetEligibleTargetsForNormalAttack(caster, position)` a lui aussi ete RELU :

    IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsForNormalAttack(caster, casterPosition)
      = <IBattleQuery slot 0x42 = 66 GetValidTargets>(caster, casterPosition,
                                                      UnitExtensions.GetNormalAttackType(caster))

Le natif passe donc la TUILE VISEE comme position du CASTER : la question posee est
<< si Shadowsun se tenait la, aurait-elle une cible d'attaque normale ? >>. C'est exactement le
sens de la face COMBAT, deja portee (`engine/runner/abilities/tau.py::exemplar_of_the_kauyon_tree`)
-- 1087 TELEPORTE Shadowsun sur la tuile visee puis y declenche un `PerformAIAttack`. L'IA ne
depense donc l'ability que si le saut lui donne quelqu'un a frapper.

Utilite CONSTANTE = `Fix64(1)` = `MIN_UTILITY` : toutes les tuiles survivantes sont a EGALITE, et
`Bucket$$AddAction` (remplacement STRICT `>`) garde la PREMIERE enumeree. Tout le discriminant est
dans le gate -- meme forme qu'`UnbreakableDuty` (1061) et `ExemplarOfTheMontka` (1210).

⚠ **NE PAS CONFONDRE AVEC `TheQuickeningPlaybook$$GetNumAttackTargetsInPosition`**, qui a l'air du
meme predicat et ne l'est pas : ce dernier appelle `<IBattleQuery slot 0x80 = 128 GetAdjacentEnemies>
(position, unit, 0)` puis `.Count` -- des ennemis ADJACENTS, pas des cibles LEGALES d'attaque
normale. Les deux slots ont ete lus dans `metadata/interface_slots.tsv` avant de trancher ; le
mirror `_base._get_num_attack_targets_in_position` porte le SECOND et n'est donc pas reutilisable
ici. (C'est le voisin de forme qu'il fallait ecarter.)

BORNES DE PORT, toutes nommees -- residu `#975-r1`
---------------------------------------------------
Le gate est le SEUL point du module qui ne soit pas un mirror exact, et l'obstacle est un CAPTEUR,
pas une lecture :

* `GetValidTargets(caster, <position ARBITRAIRE>, naType)` n'est expose par AUCUN RPC. `abilityTargets`
  ne repond que pour la position COURANTE (`fromHere`) et pour l'UNION sur les tuiles de MOVE
  (`targets`) ; `castFromTiles` balaie `GetMovableTilesFor`, donc l'univers MOVABLE. Or 1087 est un
  TELEPORT (`range = <TargetingRange statics+0x48>` = WHOLE_BOARD, cf. `ExemplarOfTheKauyonAbility.
  TARGETING_OPTIONS`) : ses destinations sont massivement HORS de cet univers. Aucun canal ne repond
  donc a la question posee. Point d'ancrage a hooker : `IdunBattle.Core.Services.BattleQuery$$
  GetValidTargets` (surcharge 3 params) avec une `UnitPosition` fabriquee -- ou, plus simplement,
  un parametre `fromTile` sur le RPC `abilityTargets`.
* Le port mirrore donc les DEUX etages DOMINANTS de `GetValidTargets`, et eux seuls :
  la PORTEE (`distance(T, ennemi) <= portee d'attaque max`, foyer partage
  `engine.ai.state_bridge._max_attack_range`, deja consomme par `playbook/loki_custom.py`) et
  l'OBSCURCISSEMENT (`battle_query.is_target_tile_obscured`, le mirror de
  `TargetingQuery$$IsTargetTileObscured`, exact a distance 2).
  Ne sont PAS portes : le brouillard de guerre, la walkability de la tuile de la cible, et les bits
  du masque de l'attaque normale. Les trois ne peuvent que RETIRER des cibles -> le gate porte est
  une **BORNE SUPERIEURE** : il peut rendre `True` la ou le natif rend `False`, donc proposer 1087
  sur une tuile que le natif ecarte. Il ne peut PAS rater un cast que le natif fait.
* `epos` vide (aucun ennemi publie) -> `False` partout -> aucun candidat. C'est le seul regime ou
  le port s'abstient, et le natif ferait de meme (aucune cible n'existe).
* **AIM depuis l'ORIGINE seule** (`abilityTargets(...).fromHere`) : meme borne que
  `DarkTalonStrikePlaybook` et `RadBombardmentPlaybook` -- le natif balaie aussi les tuiles de move.
  L'utilite etant CONSTANTE, `AddAction` ne remplace jamais, donc balayer plus de positions ne
  changerait QUE la tuile de cast, pas la decision de caster. Residu `#975-r2`.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import (NCContext, NonComparablePlaybook, has_eligible_normal_attack_target,
                    visual_id_of as _visual_id_of)


def has_enemy_in_range(ctx: NCContext, tile: tuple) -> bool:
    """`...ExemplarOfTheKauyonPlaybook$$HasEnemyInRange(entities)` =
    `GetEligibleTargetsForNormalAttack(caster, UnitPosition(entities@+0x10)).Count > 0`.

    ⚠ **LE CORPS VIT DANS `_base.has_eligible_normal_attack_target`, ET C'EST DELIBERE** : le MEME
    predicat natif est appele par `AttemptedPossessionPlaybook$$EvaluateNonComparable` (2e
    increment, `#590-r7`), sur une unite ENNEMIE. Deux transcriptions du meme corps natif se
    desynchroniseraient -- une seule des deux serait corrigee le jour ou un etage manquant est
    porte. Ce qui reste ICI est ce qui est PROPRE a ce site : le caster est `ctx.uid`, et ses
    adversaires sont `ctx.epos`.

    Etages portes, bornes et residu `#975-r1` : cf. le foyer."""
    return has_eligible_normal_attack_target(ctx, ctx.uid, tile, ctx.epos)


class ExemplarOfTheKauyonPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.ExemplarOfTheKauyonPlaybook$$EvaluateNonComparable` (0x43f = 1087).

    Utilite CONSTANTE `Fix64(1)` = `MIN_UTILITY` sur toute tuile visee qui passe `HasEnemyInRange` :
    le playbook ne DEPARTAGE rien, il dit seulement << ce saut me met au contact >>."""
    ABILITY_ID = int(ActiveAbilityType.ExemplarOfTheKauyon)   # 0x43f = 1087
    MIN_UTILITY = 1.0     # `...ExemplarOfTheKauyonPlaybook$$.cctor` : `Fix64$$op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`Fix64.op_Implicit(1)` -- constante, posee AVANT le gate dans le corps natif (le natif
        la calcule puis la jette si `HasEnemyInRange` est faux ; `op_Implicit` n'a aucun effet de
        bord, l'ordre n'est donc pas observable)."""
        return self.MIN_UTILITY

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`ActiveAbilityActionGenerator` + `Bucket$$ChooseAction` pour un cast TILE-TARGET.

        Les tuiles visees viennent d'`abilityTargets(uid, 1087).fromHere` (`kind = "tile"`), qui
        est le mirror de `GetEligibleTargetsSelectable(caster, casterPosition.MainTile)` : c'est le
        RPC natif qui applique le masque (`TargetIsTile | TargetTileIsFree`) ET la regle dynamique
        `ExemplarOfTheKauyonAbility$$GetDynamicInvalidTargetReason` (tuile libre, adjacente a un
        allie), donc l'ensemble des candidates est MESURE, pas reconstruit.

        L'utilite etant CONSTANTE, `AddAction` (remplacement STRICT `>`) garde le PREMIER ajoute :
        la premiere tuile enumeree qui passe le gate. D'ou l'arret immediat et `to = None`."""
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
                    tile = t.get("tile")
                    if t.get("kind") != "tile" or not tile or tile.get("col") is None:
                        continue
                    T = (tile.get("col"), tile.get("row"))
                    if not has_enemy_in_range(ctx, T):
                        continue                      # `if (HasEnemyInRange(...))` natif
                    tile_id = (ctx.tile_id_by_pos or {}).get(T)
                    if tile_id is None:
                        continue        # pas d'entite-tuile -> cible non emettable, on continue
                    util = self.evaluate_non_comparable(T, tile_id, ctx)
                    if util is None or util < self.MIN_UTILITY:
                        continue
                    if ctx.debug:
                        import sys
                        print(f"    [dbg NC u{ctx.uid}] ExemplarOfTheKauyon aim={T} "
                              f"tileId={tile_id} u={util:.1f}", file=sys.stderr)
                    return [{"target": tile_id, "ability": self.ABILITY_ID,
                             "to": None, "pred": float(util)}]
        return []
