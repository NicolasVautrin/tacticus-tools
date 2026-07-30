"""`IdunBattle.AI.Playbook.Loki.ResurrectionOrbPlaybook` (ability 1009, `necroOverlord` « Anuphet »).

## L'artefact natif

`IdunBattle.AI.Playbook.Loki.ResurrectionOrbPlaybook$$.ctor` =
`ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor(this, 0x3f1, ...)` -> **COMPARABLE**
(0x3f1 = 1009). Le playbook n'override QUE `CalculateCustomUtility` (aucun autre symbole de la classe
sur `rnca9r7q6c` ; l'`EvaluateNonComparable`/`GetUseProbability` de `gqfc5mff6c` a disparu avec le
changement de famille NonComparable -> Comparable).

`IdunBattle.AI.Playbook.Loki.ResurrectionOrbPlaybook$$CalculateCustomUtility` — MIRROR 1:1 :

    u   = Fix64.Zero                                  # statics(Fix64)+0x28
    ctx = zeroed(0x128) ; ctx.caster = caster ; ctx.casterPosition = casterPosition
    if Count(ability.GetPossibleResurrectTargets(), ctx) > 0:
        if Count(ability.GetPossibleSpawnOrResurrectTiles(), ctx) > 0:
            u += GetUtilityValue("ResurrectionOrb_LikesResurrection")          # 90
    numSummons = ability.GetNumSummonsFormula().Calculate(ctx)
    u += Fix64(numSummons) * GetUtilityValue("ResurrectionOrb_LikesSummoning") # 10
    return u

Trois faits que ce corps etablit, et qui tiennent ce module :

1. **`target` et `possibleTargets` ne sont PAS lus.** L'utilite ne depend que de `caster` et de
   `casterPosition` -> elle est CONSTANTE sur les cibles, et VARIE sur la tuile balayee. C'est donc
   la tuile, pas la cible, que l'argmax de `nonattack_candidates` discrimine.
2. **Le terme summoning est calcule INCONDITIONNELLEMENT** (hors du `if nResurrect > 0`), et il est
   MULTIPLICATIF (`numSummons x W`), la ou le terme resurrection est un forfait BOOLEEN.
3. **Le gate resurrection est une CONJONCTION** : il faut a la fois >=1 cible resurrectable ET >=1
   tuile posable. Une seule des deux ne donne rien.

`IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetUtilityValue` =
`Fix64.FromInt(dict[name])` via `TryGetValue`, cle absente -> 0 (+ un warning dev). Cote port c'est
`ctx.wt.sub("ActiveAbilities", <cle>)`, meme semantique d'absence.

## La route

1009 n'a **pas** de `damageProfile` (gameconfig : `constants = {unitId, maxSummons}`) et son masque
refuse toute cible ennemie (`TargetIsCaster`) -> `state_bridge._is_attack_ability` rend False, donc
l'ability n'entre JAMAIS dans `ctx.plans` et `_best_attack` ne la voit pas. C'est exactement le
critere de la seconde route Comparable (`playbook/nonattack.py`) : « Comparable ABSENTE de
`ctx.plans` ». Verifie a l'execution, pas herite (`probe_289_resurrection_orb.py` etape 1).

## Les selecteurs/formules

Ils ne sont PAS redefinis ici : ce sont les arbres DSL de l'ABILITY
(`runner/abilities/necrons.py`), que le natif appelle depuis le playbook exactement comme depuis
`ExecuteBehaviour`. **Un seul artefact natif, un seul port** — meme doctrine que
`SavageEchoesAbility.get_damage_formula`, partagee entre `runner/abilities/bloodangels.py` et
`playbook/prediction/abilities.py`. Ce module ne fait que leur fournir un `DslContext`.
"""
from __future__ import annotations

from dataclasses import replace

from .. import dsl
from ..entities.active_ability_type import ActiveAbilityType
from ..entities.formulas import Count
from ..entities.traits.unit_trait import entity_trait_names, has_trait
from ..runner.abilities.necrons import (resurrection_orb_num_summons_formula,
                                        resurrection_orb_possible_resurrect_targets,
                                        resurrection_orb_possible_spawn_or_resurrect_tiles)
from .nonattack import NonAttackComparablePlaybook, register_nonattack


def _dsl_context(ctx, caster_tile):
    """Le contexte d'evaluation des selecteurs/formules de l'ability, cote DECISION.

    Mirror du `SelectorContext` de 0x128 octets que `CalculateCustomUtility` memset a ZERO avant d'y
    ecrire DEUX champs seulement : `+0x08 = caster` et `+0x48 = casterPosition`. Tout le reste est nul
    -- en particulier `target`, que les arbres de 1009 n'interrogent pas.

    `caster_pos = caster_tile` est ce qui fait le SWEEP : le noeud `CasterTile` (mirror du selecteur
    partage `DSLSelectors+0x58`) rend `ctx.caster_pos or _pos(ctx.caster)`, donc l'anneau
    `AdjacentTiles` est bien celui de la tuile CANDIDATE.

    ⚠ Le caster est aussi DEPLACE dans la liste d'unites. Raison : le port `CanAddUnit` compte comme
    occupee la tuile de toute unite VIVANTE, caster inclus (le natif, lui, passe le caster en 4e
    argument d'`UnobscuredEntitiesSelector` -- dont le role exact n'est PAS RE, residu nomme). Sans le
    deplacement, un caster qui bouge d'un hex bloquerait sa tuile de DEPART (qui est un voisin de la
    tuile d'arrivee) et libererait a tort la tuile d'ARRIVEE : les deux erreurs faussent le compte de
    tuiles, donc `numSummons`, donc l'utilite. Le repositionnement est le mirror du `casterPosition`
    natif, pas une invention.

    `has_trait`/`get_stat` sont les DEUX accesseurs hors-state que les arbres exigent
    (`HasTrait(Hero)`, `IsMechanical`, `StatAmount(TURNS_STARTED)`). Ils lisent le `UnitContext` de la
    `Scene` -- le MEME objet que `StatsComponent.ctx` cote runner (cf. `entity_trait_names`)."""
    scene = getattr(ctx, "scene", None)
    if scene is None or getattr(scene, "board", None) is None:
        return None
    units = []
    caster = None
    for u in (scene.units or []):
        if u.get("id") == ctx.uid:
            # `casterPosition` : le caster est vu SUR LA TUILE CANDIDATE (cf. docstring).
            caster = dict(u, pos={"col": caster_tile[0], "row": caster_tile[1]},
                          feet=[(caster_tile[0], caster_tile[1])])
            units.append(caster)
        else:
            units.append(u)
    if caster is None:
        return None
    vis_by_id = {u.get("id"): u.get("visualId") for u in units}

    def _has_trait(u, trait) -> bool:
        uid = (u or {}).get("id")
        return has_trait(entity_trait_names(scene.ctx(uid), vis_by_id.get(uid)), trait)

    def _get_stat(u, stat_type, variant, level) -> int:
        uc = scene.ctx((u or {}).get("id"))
        return int(uc.get_stat(int(stat_type), int(variant or 0))) if uc is not None else 0

    return dsl.DslContext(units=units, caster=caster, board=scene.board,
                          caster_pos=(caster_tile[0], caster_tile[1]),
                          elev_by_pos=scene.elev_by_pos,
                          has_trait=_has_trait, get_stat=_get_stat)


class ResurrectionOrbPlaybook(NonAttackComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.ResurrectionOrbPlaybook` — cf. l'en-tete du module."""

    __slots__ = ()
    ability_id = int(ActiveAbilityType.ResurrectionOrb)          # 0x3f1 = 1009
    W_RESURRECTION = "ResurrectionOrb_LikesResurrection"         # 90 (BC.Utilities, build courant)
    W_SUMMONING = "ResurrectionOrb_LikesSummoning"               # 10

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        """`ResurrectionOrbPlaybook$$CalculateCustomUtility` — mirror 1:1 (cf. l'en-tete).

        `target` est ignore PARCE QUE LE NATIF L'IGNORE (il ne lit ni `param_4` ni `possibleTargets`),
        pas par simplification.

        Contexte DSL indisponible (Scene ou board absents, ex. runner sans `combatSnapshot`) -> 0.0 :
        aucune utilite INVENTEE. La degradation est conservatrice (l'action reste generee par la route
        avec u=0, elle perd juste sa preference) et non silencieuse -- `probe_289` la distingue."""
        dctx = _dsl_context(ctx, caster_tile)
        if dctx is None:
            return 0.0
        u = 0.0
        n_resurrect = Count(resurrection_orb_possible_resurrect_targets()).evaluate(dctx)
        if n_resurrect > 0:
            n_tiles = Count(resurrection_orb_possible_spawn_or_resurrect_tiles()).evaluate(dctx)
            if n_tiles > 0:
                u += ctx.wt.sub("ActiveAbilities", self.W_RESURRECTION)          # 90
        num_summons = resurrection_orb_num_summons_formula().evaluate(dctx)
        return u + float(num_summons) * ctx.wt.sub("ActiveAbilities", self.W_SUMMONING)   # x 10

    def eligible_targets(self, ctx, ability_id) -> list:
        """`BasePlaybook$$GetEligibleTargetsEntities` pour un SELF-CAST STRICT.

        Le masque de `ResurrectionOrbAbility$$.ctor` porte `TargetIsCaster` (0x8000000000) et
        `self_cast = 1` -> le seul target legal est le caster. On garde neanmoins la voie generique
        (`ctx.ability_targets`, le RPC natif `abilityTargets`) comme SOURCE, et on ne retombe sur
        `[ctx.uid]` que si elle ne rend rien -- l'ability est utilisable (`usable` deja teste par
        `nonattack_candidates`) et le natif, lui, ajoute toujours le caster quand
        `GetCasterNotAddedReason` est nul. Sans ce repli, une couture `abilityTargets` muette sur les
        self-casts rendrait la route INERTE (l'action n'existerait pas), ce qui est une degradation
        PLUS grave que le sur-ensemble."""
        out = super().eligible_targets(ctx, ability_id)
        return out or [ctx.uid]

    def is_caster_added(self, ctx, caster_tile) -> bool:
        """`IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason == null` pour ce masque.

        Le masque porte `TargetHasFreeAdjacentTile` (0x20) EN PLUS de `TargetIsCaster` : depuis une
        tuile SANS aucun hex adjacent posable, le caster n'est pas ajoute aux cibles, donc
        `GetEligibleTargetsEntities` est vide et AUCUNE action n'est generee depuis cette tuile. On
        reutilise le selecteur de l'ability (`GetPossibleSpawnOrResurrectTiles`) plutot qu'un compte
        recable a la main -- c'est le meme ensemble.

        Contexte DSL indisponible -> `True` (le defaut permissif de la base : on ne refuse jamais un
        cast sur une donnee qu'on n'a pas lue)."""
        dctx = _dsl_context(ctx, caster_tile)
        if dctx is None:
            return True
        return Count(resurrection_orb_possible_spawn_or_resurrect_tiles()).evaluate(dctx) > 0


register_nonattack(ResurrectionOrbPlaybook())
