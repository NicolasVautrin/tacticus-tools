"""`BasiliskBarragePlaybook` (1026, `astraOrdnance` « Thaddeus Noble ») — face DECISION (#1026-r1).

TROISIEME membre de la route de decision a cibles TUILE, apres 1169 (`PlagueburstMortar`) et
1148 (`DaemonicOrdnance`). **Decider != executer** : la face COMBAT est portee et confrontee live
depuis #253 (`runner/abilities/astramilitarum.py::BasiliskBarrageAbility`, tirage des obus rejoue
sur 7 seeds) ; ce qui manquait est l'utilite de DECISION — invisible en replay, puisque
l'execution est juste.

## L'artefact natif, lu en entier

`...BasiliskBarragePlaybook$$.ctor` = `ComparablePlaybook<T>..ctor(this, 0x402 = 1026)` : c'est un
**Comparable**, pas un NonComparable — il n'y a ni `EvaluateNonComparable` ni `ShouldEvaluate` a
chercher. Les seuls corps propres sont `$$MakeDamagePredictions` et son helper
`$$GenerateAttackPredictionsForShells`.

```
BasiliskBarragePlaybook$$MakeDamagePredictions(caster, casterPosition, target, abilityState) :

    entities   = { owner/caster: caster, target: target }
    nMiss      = BasiliskBarrageAbility$$GetNumShellsMiss      .Evaluate(entities)
    nMaybe     = BasiliskBarrageAbility$$GetNumShellsMaybe     .Evaluate(entities)
    nGuar      = BasiliskBarrageAbility$$GetNumShellsGuaranteed.Evaluate(entities)
    tilesMiss  = BasiliskBarrageAbility$$GetPossibleTargetTilesMiss     # TilesAtDistance(Target, 2)
    tilesMaybe = BasiliskBarrageAbility$$GetPossibleTargetTilesMaybe    # TargetTiles + TilesAtDistance(Target, 1)

    list  = GenerateAttackPredictionsForShells(..., nMiss,  tilesMiss)
    list += GenerateAttackPredictionsForShells(..., nMaybe, tilesMaybe)
    list += GenerateAttackPredictionsForShells(..., nGuar,  DSLSelectors$$Entity(target))
    return list
```

⚠ Le troisieme groupe n'utilise **PAS** `GetPossibleTargetTileGuaranteed` (que la face COMBAT, elle,
appelle) : le playbook lui substitue `DSLSelectors$$Entity(target)`. Les deux valent
`TargetTiles@<DSLSelectors+0x78>` sur le chemin normal, mais c'est une difference ECRITE, donc
portee telle quelle (`[target]`).

```
GenerateAttackPredictionsForShells(caster, casterPosition, target, abilityState, numShells, shellTargets) :

    if (int)numShells < 1: return []                     # <- les groupes vides ne coutent RIEN
    dmg     = <ability>$$GetDamageAmountMain(abilityState)   # -> AActiveAbility$$MinMaxDamageAverage
    hits    = AActiveAbility$$GetHits                        # GetNumberConstant(0x2f = nrOfHits) = 2
    profile = <ability>$$GetDamageProfileType
    entities = { caster, target, targetTiles: EntityExtensions$$GetTiles(target, state) }
    tiles = shellTargets.Select(entities)
    for i in 0 .. tiles.Count - 1 :
        e     = tiles[i]
        ratio = Fix64(numShells) / Fix64(tiles.Count)        # <- LE POIDS
        list += ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions(
                    caster, casterPosition, e, DSLSelectors$$Entity(e),
                    dmg, hits, profile, Nullable<Fix64>(ratio), weightSelector: 0 )
    return list
```

Le rang 9 de `GenerateMultiHitAttackPredictions` va **tel quel** dans `ProbableDamageEvent+0xC8` =
`probability1` ; `weightSelector = 0` ⇒ `probability2 = Fix64(1)`. C'est exactement la semantique
de `probable_damage_event.py`, donc **aucun mecanisme neuf** : le « batch a poids propre » EST le
champ `probability1`, qui existe depuis le premier jour.

⚠ **Le poids se divise par le pool ENTIER, pas par les tuiles OCCUPEES.** `tiles.Count` est evalue
avant toute resolution d'occupant. Filtrer d'abord puis diviser gonflerait l'utilite des barrages
qui tombent surtout a vide — exactement le regime que 1026 produit en pratique.

⚠ **Aucun tirage n'entre dans la DECISION.** Le playbook ENUMERE le pool et pondere ; la face
COMBAT, elle, TIRE (trois `PickRandomly` avec remise, `state.rng`). Les deux faces partagent les
memes noeuds de pool — d'ou le foyer partage (`basilisk_num_shells_from_turns`,
`basilisk_tiles_at_distance_on_board`), jamais un fork.

## Le verrou, LEVE par la mesure

`IdunBattle.Entities.Selectors.EntitySelector$$Select` rend l'entite **telle quelle** (elle appelle
`GetEntity`, jamais `GetUnit`), et le pool d'obus est fait de TUILES : le `ProbableDamageEvent.Target`
du natif est donc une entite-TUILE, et le decompile seul ne dit pas si l'occupant est resolu en aval.

MESURE (`probe_1026_face_decision_live.py`, `MC1_67`, seed 777, montage SEPARANT — seule variable :
la position d'un temoin) : `u(T1)` passe de **4,161933** a **20,194460** quand une tuile de l'anneau 1
devient occupee, temoin de controle a **+0,000000 exactement**. ⇒ **le natif RESOUT l'occupant de
chaque tuile d'obus et SOMME leurs contributions.**

Le port materialise donc ici une resolution que le natif fait plus bas dans la pile
(`PredictAttack`), par le noeud DSL `Units(FixedTileIds([...]))` — mirror de
`IdunBattle.Entities.UnitExtensions$$GetUnit(tile, state)`, dont le premier gate est
`TileContentComponent$$IsFilled`. La mesure etablit que c'est value-identique : `u(<tuile>)` ==
`u(<unite qui l'occupe>)` a la derniere decimale dans les deux bras (meme propriete que 1169, #302-2).

## Pourquoi la route NON-ATTAQUE — et pourquoi ce n'est PAS un doublon

La fiche `#1026-r1` posait « contrairement a 1169/1148, 1026 EST visible de `attackPlans`, donc
`register_nonattack` la DOUBLERAIT ». **RE-MESURE : c'est FAUX**, et l'enonce du critere l'etait
aussi. `nonattack.py` porte deja un ⚠⚠ explicite la-dessus (mesure #289) : « ABSENTE de `ctx.plans` »
n'est PAS le critere — 1009 est LISTEE dans `decisionView.attackPlans` a `rankCount = 0` et vit
pourtant sur cette route. Le critere reel est **« Comparable invisible de `_best_attack` »**.

Mesure du 2026-08-15 (`state_bridge._attack_abilities`, offline) — les TROIS tile-target sont
visibles au MEME titre, il n'y a aucune difference de route entre 1026 et ses deux precedents :

    deathCrawler    PlagueburstMortar   [(17, 1), (1168, 1), (1169, 1)]
    blackForgefiend DaemonicOrdnance    [(17, 1), (1147, 2), (1148, 1)]
    astraOrdnance   BasiliskBarrage     [(17, 3), (1026, 3)]

Ce qui empeche le doublon n'est donc pas l'absence des plans, c'est que `_best_attack` presente une
cible **UNITE** a `make_damage_predictions` : le `target` est alors interprete comme un id de TUILE,
le selecteur ne rend rien, la liste est vide, et `calculate_action_utility` rend `None` — aucune
action. C'est le mecanisme deja en place pour 1169 et 1148, et l'etage 3 du cliquet
`probe_1026r1_face_decision.py` le VERIFIE plutot que de le supposer.
"""
from __future__ import annotations

from ..entities.active_ability_type import ActiveAbilityType
from ..entities.selectors import Units
from ..entities.selectors.accessors import FixedTileIds
from ..runner.abilities.astramilitarum import (BASILISK_ID, basilisk_num_shells_from_turns,
                                               basilisk_tiles_at_distance_on_board)
import engine.playbook.prediction as prediction   # sous-paquet FRERE, pas `from . import` (#270-r4-r2)
from .nonattack import NonAttackComparablePlaybook, register_nonattack
from .probable_damage_event import ProbableDamageEvent
from .tile_targets import dsl_context_for_tile_target


class BasiliskBarragePlaybook(NonAttackComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.BasiliskBarragePlaybook` — cf. l'en-tete du module."""

    __slots__ = ()
    ability_id = int(ActiveAbilityType.BasiliskBarrage)             # 0x402 = 1026
    ability_name = BASILISK_ID                                      # cle gameconfig

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        """`BasiliskBarragePlaybook$$MakeDamagePredictions` — mirror 1:1 (cf. l'en-tete).

        `target` est une entite-TUILE (masque `TargetIsTile`, bit 6). Les trois groupes sont emis
        DANS L'ORDRE NATIF (miss, maybe, guaranteed) : l'ordre ne change pas la somme, mais il
        change la TRACE, et c'est elle qu'une confrontation par tuile compare.

        Contexte DSL indisponible, cible absente, ou `turns_started` NON MESURE -> `[]` : le terme
        de prediction est alors nul, jamais invente. Le tri-etat de `turns_started` est load-bearing
        — c'est lui qui fixe `guaranteed`, donc la ventilation des trois groupes."""
        dctx = dsl_context_for_tile_target(ctx)
        scene = getattr(ctx, "scene", None)
        if dctx is None or target is None or scene is None or scene.board is None:
            return []
        turns = scene.turns_started(ctx.uid)
        if turns is None:
            return []                       # NON MESURE -- pas un zero (cf. `host_inputs` tri-etat)
        ttile = int(target)
        # ⚠ CE GARDE EST LE MECANISME ANTI-DOUBLON, et il doit etre EXPLICITE.
        # `_best_attack` presente des cibles UNITE (`state_bridge._plans_for_unit` enumere les
        # ennemis) et 1026 EST dans `_attack_abilities` de son porteur -- exactement comme 1169 et
        # 1148. Ce qui empeche la double comptabilisation, c'est qu'un id d'UNITE n'est pas une
        # entite-TUILE : la liste est vide, donc `calculate_action_utility` rend `None`, donc
        # aucune action. TROUVE PAR LA CONFRONTATION (`probe_1026r1_face_decision_port.py` etage 3) :
        # sans ce test, `Board.coord` levait `KeyError` sur un id d'unite -- le port CRASHAIT la ou
        # 1169 rend `[]`, parce que 1169 passe par un selecteur et jamais par `coord`.
        if ttile not in (getattr(scene.board, "by_id", None) or {}):
            return []
        tp = scene.board.coord(ttile)
        if tp is None:
            return []
        guaranteed, maybe, miss, _total = basilisk_num_shells_from_turns(turns)

        # Les pools, dans la forme NATIVE du playbook. `GetPossibleTargetTilesMaybe` =
        # `TargetTiles op_Addition TilesAtDistance(Target, 1)` -- `TargetTiles` EN TETE.
        pool_miss = basilisk_tiles_at_distance_on_board(scene.board, tp, 2)
        pool_maybe = [ttile] + basilisk_tiles_at_distance_on_board(scene.board, tp, 1)
        pool_guar = [ttile]                 # `DSLSelectors$$Entity(target)`, pas `GetPossibleTargetTileGuaranteed`

        out = []
        out += self._shells(ctx, dctx, caster_tile, ability_id, miss, pool_miss)
        out += self._shells(ctx, dctx, caster_tile, ability_id, maybe, pool_maybe)
        out += self._shells(ctx, dctx, caster_tile, ability_id, guaranteed, pool_guar)
        return out

    def _shells(self, ctx, dctx, caster_tile, ability_id, num_shells, tiles) -> list:
        """`BasiliskBarragePlaybook$$GenerateAttackPredictionsForShells` — mirror 1:1.

        Le `if (int)numShells < 1: return []` natif est en tete : un groupe vide ne produit AUCUN
        event, et surtout ne divise pas par zero.

        ⚠ `ratio` se calcule sur `len(tiles)` — le pool ENTIER, occupation comprise ou non. Le natif
        evalue `tiles.Count` avant de rien resoudre. Il PEUT depasser 1 (aucun clamp au decompile,
        et aucun ici) : `guaranteed` shells sur un pool `TargetTiles` de cardinal 1 donne
        `ratio = guaranteed`, ce qui est le comportement natif recherche — c'est la traduction du
        « pour chaque round termine, un obus de plus frappe la tuile cible » de l'i2."""
        if int(num_shells) < 1 or not tiles:
            return []
        ratio = float(num_shells) / float(len(tiles))
        out = []
        for tid in tiles:
            # `Units(FixedTileIds([tid]))` = `UnitExtensions$$GetUnit(tile, state)` : l'occupant
            # VIVANT de la tuile, ou rien. Une tuile vide ne produit aucun event -- et son poids
            # reste compte au denominateur, ci-dessus.
            for u in (Units(FixedTileIds([int(tid)])).select(dctx) or []):
                uid = u.get("id") if isinstance(u, dict) else None
                if uid is None:
                    continue
                dp = prediction.generate_multi_hit_attack_prediction(
                    ctx.scene, ctx.uid, int(uid), int(ability_id), self.ability_name,
                    attack_pos=caster_tile)
                if dp is not None:
                    out.append(ProbableDamageEvent(target=int(uid), prediction=dp,
                                                   probability1=ratio))
        return out


register_nonattack(BasiliskBarragePlaybook())
