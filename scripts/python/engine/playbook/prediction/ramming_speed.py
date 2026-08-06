"""Batchs 3/4 (EXPLOSION) de `IdunBattle.AI.Playbook.Loki.RammingSpeedPlaybook$$MakeDamagePredictions`
-- ability `1059 RammingSpeed`. `#383`, cloture le volet (b) de `#353-r1`.

LE NATIF, remis en C# depuis le decompile (les DEUX premiers batchs sont dans
`prediction/abilities.py` : `_ramming_speed_inputs` et `_ramming_speed_self_events`) :

    list.AddRange(self)                                              // batch 2, le CASTER
    if (!self.Any(p => p.Prediction.WillBeKill)) return list;        // <>c$$<MakeDamagePredictions>b__2_0
    amount = <eval>( ExplodesAbility$$GetDamage(dsl) )               // ctx neuf : SEUL `+0x18 = caster`
    tile   = RammingSpeedAbility$$GetTileToMoveTo(ability)
    list.AddRange(GenerateAttackPredictions(caster, casterPosition, target,
                      Friends(<Caster>, AdjacentUnits(tile, 1, 3), 3), Get(amount),
                      null, Nullable(0xf = DirectDamage), 0))        // batch 3
    list.AddRange(GenerateAttackPredictions(caster, casterPosition, target,
                      Enemies(<Caster>, AdjacentUnits(tile, 1, 3), 3), Get(amount),
                      null, Nullable(0xf), 0))                       // batch 4

`ComparablePlaybook<T>$$GenerateAttackPredictions` emet **UN event PAR ENTITE** rendue par son
selecteur (`TargetsSelector$$SelectUniqueUnits(ctx, 3)`, index 4 de l'interface), et son etage de
degat est le slot `0x24` d'`IBattleQuery` = `BattleQuery$$GetAttackPrediction` -- c'est-a-dire
EXACTEMENT le 1er coup de `BattleQuery$$GetMultiHitAttackPrediction` (dont le corps commence par
`memset(result, 0, 0xa0)` puis appelle `GetAttackPrediction(..., previousHitsPrediction = 0)` et ne
boucle que `nrOfHits - 1` fois de plus). Cote port, ce batch est donc
`generate_multi_hit_attack_prediction(..., hits_override = 1)` -- pas une approximation : le meme
foyer, avec le compteur du natif.

TROIS LECTURES QUI CORRIGENT UN ENONCE HERITE
---------------------------------------------
1. **Le referent de `Friends`/`Enemies` est l'EQUIPE, pas la FACTION.** `case-361` sec.7 ecrivait
   « allouent le meme `UnitsFromFactionSelector` ... partitionnent leur entree par
   `UnitExtensions$$HasFaction` ». C'est FAUX, et c'est le faux negatif de deduplication documente
   au CLAUDE.md : `DSLSelectors$$Friends`/`$$Enemies` allouent la classe `DAT_18336e320` tandis que
   `DSLSelectors$$UnitsFromFaction` alloue `DAT_18336e9b0` -- deux classes DIFFERENTES dont les
   `.ctor` ont le MEME corps (5 ecritures de champ), donc UN SEUL proprietaire dans la table de
   symboles. La classe reelle de Friends/Enemies est celle dont ghidra nomme les autres methodes :
   `IdunBattle.Entities.Selectors.UnitsByTeamSelector`, dont `$$Select` delegue a `$$CountOrAdd`,
   qui filtre par `IdunBattle.Entities.UnitExtensions$$IsFriend(referent, other, state)` compare au
   flag `+0x28` (1 pour Friends, 0 pour Enemies). Le port (`entities/selectors/units.py`) filtre par
   `team` : il etait deja JUSTE.
2. **L'`origin` de `AdjacentUnits` est une TUILE**, donc l'`op_Subtraction origin` de
   `DSLSelectors$$AdjacentUnits` (= `Units(AdjacentTiles(origin), unique, sel) - origin`) ne retire
   AUCUNE unite. En particulier **le CASTER n'est pas exclu** : s'il est adjacent a la tuile
   d'arrivee, il compte dans `Friends` (il est son propre ami). Quirk natif, mirrore tel quel.
3. **`amount` est evalue UNE SEULE FOIS**, hors des deux boucles, dans un contexte que
   `MakeDamagePredictions` construit lui-meme (`memset(ctx, 0, 0x128)` puis SEULEMENT
   `ctx+0x18 = caster`) -- puis re-emballe en `DSLFormulas$$Get(amount)`, une CONSTANTE. Toutes les
   cibles recoivent donc la MEME base ; c'est aussi pourquoi `Owner` (`DSLSelectors+0x30`, lu par
   `ExplodesAbility$$GetDamage`) resout le CASTER et rien d'autre.

QUIRK NATIF, deja releve par `#353` sec.2 et confirme ici : le playbook evalue
`ExplodesAbility$$GetDamage` **sans jamais tester le trait `Explodes` du caster**. Quand le recul
tuerait le caster, l'IA predit la nova, que le caster explose reellement ou non.

RESIDUS NOMMES
--------------
* `TargetsSelector$$SelectUniqueUnits(ctx, 3)` : le `unique` et le masque `3` (= vivante ET sans le
  flag `0x11 NotTargetable`) ne sont pas modelises separement -- `_within` filtre deja les mortes,
  et le flag `0x11` n'est porte par aucun substrat de la face prediction. Meme residu que pour tous
  les autres sets AoE portes.
* L'ORDRE de `MovableTilesInRange` (ids croissants cote port, ordre de visite du BFS cote natif) --
  residu herite de `#353-r1`, il ne departage que des utilites STRICTEMENT egales.
* `#381-r1` : le port de `MovableTilesInRange` rend le `visited` d'un BFS qui TRAVERSE les allies,
  la ou `MovementQuery$$AnyOrFillMoveableTiles` applique ses propres blocages. Sur un ring SATURE,
  `ramming_speed_tile_to_move_to` peut donc designer une tuile que le natif n'atteint pas -- residu
  de plein droit, NON traite ici (il mord sur la tuile, donc sur ces deux batchs, exactement comme
  il mord deja sur l'etage MOVE).
"""
from __future__ import annotations

import gameconfig as GC

from ...entities.effect_type import EffectType
from ...entities.formulas import ConditionalAmount, Get, PercentageOf, StatAmount, Sum
from ...entities.selectors.accessors import FixedTile, Owner
from ...entities.selectors.units import AdjacentUnits, Enemies, Friends
from ...entities.stats import StatPart, StatType
from ...entities.triggers import HasEffect
from ...dsl.base import Const, DslContext
from ..probable_damage_event import ProbableDamageEvent
from ...runner.abilities.orks import (RAMMING_SPEED_TILE_UTILITY,
                                          ramming_speed_charge_tiles_selector)
from ...utilities.tile import SceneTileState, first_tile_by_utility, scene_tile_leaf_ctx
from .abilities import generate_multi_hit_attack_prediction

# `AddEffect(0x44a, ...)` de `RammingSpeedAbility$$ExecuteBehaviour` = le SEUL poseur de cet effet.
RAMMING_SPEED_EXTRA_EXPLODE = int(EffectType.RammingSpeed_ExtraExplode)     # 0x44a = 1098
# `ConfigConst(0x3fd = 1021 Explodes, Owner, key 0xf)` — l'ability `Explodes` n'a AUCUNE entree
# `abilities` en gameconfig : sa config vient des `traitVariables` du trait homonyme (cf.
# `runner/operations/triggers/loki/death_nova.py`, qui lit la MEME cle cote COMBAT).
EXPLODES_TRAIT = "Explodes"
EXPLODES_DMG_KEY = "explodesDmg"
# `ConfigConst(0x423 = 1059 RammingSpeed, Owner, key 0xf)` — constante d'ability (hors niveau).
RAMMING_SPEED_ABILITY = "RammingSpeed"
RAMMING_SPEED_EXTRA_KEY = "extraDmgPct"
# `Nullable(0xf)` = `DamageProfileType.DirectDamage`, le `param_8` des DEUX `GenerateAttackPredictions`.
EXPLOSION_PROFILE = "DirectDamage"
# `GetNumberConstant(0x16 = range)` — la portee que `MovableTilesInRange` recoit dans
# `RammingSpeedAbility$$GetTileToMoveTo`. Cle gameconfig : `abilities.RammingSpeed.constants.range`.
RAMMING_SPEED_RANGE_KEY = "range"


def explodes_damage_tree(explodes_pct: int, ramming_extra_pct):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ExplodesAbility$$GetDamage` — MIRROR
    1:1 du decompile, MEME forme que la face COMBAT (`triggers/loki/death_nova.explodes_tree`) :

        PercentageOf( StatAmount(Owner@0x30, Health = 5, part = 2 -> MAX),
                      Sum( ConfigConst(0x3fd = 1021 Explodes, key 0xf),
                           ConditionalAmount( HasEffect(Owner@0x30, 0x44a = 1098, 1, 6),
                                              ConfigConst(0x423 = 1059 RammingSpeed, key 0xf),
                                              Get(0) ) ),
                      roundingRule = 0 )

    `PercentageOf(amount, percentage, mode)` cote natif ; le port prend `(pct, base, mode)` --
    multiplication commutative, `_round_fix64` mode 0 (half-to-even) identique.

    La BASE est le PV **MAXIMUM** (`StatPart.MAXIMUM`), pas les PV courants."""
    pct = Sum(Const(int(explodes_pct)),
              ConditionalAmount(HasEffect(Owner(), RAMMING_SPEED_EXTRA_EXPLODE),
                                Const(int(ramming_extra_pct or 0)),
                                Get(0)))
    return PercentageOf(pct, StatAmount(Owner(), int(StatType.HEALTH), int(StatPart.MAXIMUM)))


def _get_stat_from_scene(scene):
    """`ctx.get_stat(unit, statType, variant, level)` = `UnitExtensions$$GetStat`, substrat `Scene`.

    ⚠ Le couple (`Health`, `Maximum`) NE PASSE PAS par `UnitContext.get_stat`, et c'est MESURE, pas
    prudentiel. Le natif dispatche `StatType.Health` vers un
    `IdunBattle.Entities.Components.FillUpStatComponent`, dont `GetStatPart(2)` rend
    `get_CurrentMaximumValue`. Le port, lui, seede `Health` en `StatComponent` GENERIQUE
    (`entities/stats.seed_unit_stats` : « les stats fill-up sont seedees en StatComponent generique
    ... le FillUpStatComponent specifique est pose au besoin »), et `StatComponent.get_stat_part(2)`
    rend la valeur **COURANTE**. Le canal du maxPV cote `Scene` est `hpmax_by_id` (`observeBattle`).

    MESURE (#383, montage `--hp-player 60 --hp-current 30`, board MC1_67) : le natif rend
    `[18, 27]` par voisin (base = 25 % de **60**), le port qui lisait `ctx.get_stat(5, 2)` rendait
    `[9, 15]` (25 % de **30**). L'axe etait INOBSERVABLE tant que `--hp-player` posait `Health` ET
    `RemainingHealth` -- c'est la generalisation qui l'a rendu visible.

    Repli sur `ctx.get_stat` quand `hpmax` n'est pas capte : ce n'est pas la meme grandeur, mais
    c'est la seule lecture disponible, et rendre 0 ferait un degat NUL -- une sous-prediction
    muette."""
    def _get_stat(u, stat_type, variant, level=None) -> int:
        uid = (u or {}).get("id")
        if uid is None:
            return 0
        if int(stat_type) == int(StatType.HEALTH) and int(variant or 0) == int(StatPart.MAXIMUM):
            mx = scene.hpmax(uid)
            if mx:
                return int(mx)
        uc = scene.ctx(uid)
        return int(uc.get_stat(int(stat_type), int(variant or 0))) if uc is not None else 0
    return _get_stat


def _has_effect_from_scene(scene):
    """`ctx.has_effect(unit, effectType, ...)` = branche UNITE d'`EntityExtensions$$HasOneOfEffects`,
    substrat `Scene.eff_state` (les effets MATERIALISES, meme table que `Scene.effects`).

    `eff_state` absent -> `None` : le noeud `HasEffect` rend alors False LUI-MEME (l'effet 1098 est
    inconnu, jamais suppose)."""
    eff = getattr(scene, "eff_state", None)
    if eff is None:
        return None

    def _has_effect(u, effect_type, source_flag=6, min_level=0, active_only=True) -> bool:
        # Signature imposee par `HasEffectTrigger.should_trigger` : `(unit, effectType, sourceFlags,
        # minLevel, activeOnly)`. `EffectsState.has_effect` filtre deja les effets CONSOMMES ; le
        # niveau et le flag actif ne sont pas modelises sur ce substrat (residu commun a toute la
        # face PREDICTION, cf. la docstring du noeud).
        uid = (u or {}).get("id")
        return uid is not None and bool(eff.has_effect(int(uid), effect_type=int(effect_type)))
    return _has_effect


def dsl_context(scene, caster_id: int, target_id, attack_pos=None) -> DslContext | None:
    """Le contexte d'evaluation des selecteurs/formules de ces deux batchs, depuis la `Scene`.

    Champs poses = ceux que `ComparablePlaybook<T>$$GenerateAttackPredictions` renseigne dans le
    sien (LUS au decompile) : `+0x08 caster`, `+0x10 target`, `+0x18 owner`, `+0x40
    get_MainTile(casterPosition)` et `+0x48 casterPosition`. Cote port, `caster_pos = attack_pos` :
    c'est ce que lit `CasterTile()`, donc le point de depart du `MovableTilesInRange` de
    `GetTileToMoveTo` -- la tuile d'attaque CANDIDATE, pas la position courante.

    `get_stat`/`has_effect` alimentent `ExplodesAbility$$GetDamage` ; `board`/`elev_by_pos` les
    selecteurs de tuiles. Rend `None` si le caster n'est pas dans la scene."""
    units = list(getattr(scene, "units", None) or [])
    by_id = {u.get("id"): u for u in units}
    caster = by_id.get(caster_id)
    if caster is None:
        return None
    return DslContext(units=units, caster=caster, target=by_id.get(target_id), owner=caster,
                      caster_pos=(tuple(attack_pos) if attack_pos else None),
                      board=getattr(scene, "board", None),
                      elev_by_pos=getattr(scene, "elev_by_pos", None),
                      get_stat=_get_stat_from_scene(scene),
                      has_effect=_has_effect_from_scene(scene))


def tile_to_move_to(scene, caster_id: int, target_id: int, attack_pos=None, move_range=None):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RammingSpeedAbility$$GetTileToMoveTo`, evaluee
    sur le substrat `Scene` de la face PREDICTION.

    MEME arbre et MEME definition d'utilite que la face COMBAT
    (`runner/abilities/orks.ramming_speed_tile_to_move_to`) -- les deux appellent
    `ramming_speed_charge_tiles_selector` et `RAMMING_SPEED_TILE_UTILITY`, il n'y a QU'UN mirror de
    `GetTileToMoveTo` dans le depot. Seule la source d'etat differe (ECS la-bas, `Scene` ici), comme
    pour `runner_tile_leaf_ctx` / `scene_tile_leaf_ctx`.

    Rend une `(col, row)`, ou `None` si l'intersection est vide (le natif ne designe alors rien et
    les deux batchs sont VIDES -- pas d'erreur, pas d'event)."""
    board = getattr(scene, "board", None)
    dctx = dsl_context(scene, caster_id, target_id, attack_pos)
    if board is None or dctx is None or dctx.target is None:
        return None
    if move_range is None:
        consts = (GC.ability(RAMMING_SPEED_ABILITY) or {}).get("constants") or {}
        move_range = int(consts.get(RAMMING_SPEED_RANGE_KEY) or 0)   # GetNumberConstant(0x16)
    cands = ramming_speed_charge_tiles_selector(int(move_range)).evaluate(dctx)
    if not cands:
        return None
    best = first_tile_by_utility(SceneTileState(scene), cands, unit_id=caster_id,
                                 utility_definition=RAMMING_SPEED_TILE_UTILITY,
                                 leaf_ctx=scene_tile_leaf_ctx(scene, caster_id))
    return board.coord(best) if best is not None else None


def explosion_amount(scene, caster_id: int, target_id=None, attack_pos=None):
    """`<eval>( ExplodesAbility$$GetDamage(dsl) )` -- le montant UNIQUE des deux batchs.

    Le natif l'evalue dans un contexte NEUF ou seul `+0x18` (Owner) est pose ; on lui presente le
    contexte complet, ce qui est indifferent : l'arbre ne lit QUE `Owner`. `None` si la constante
    de trait manque (config absente -> aucun event invente, meme convention que
    `_ramming_speed_self_events`)."""
    base_pct = ((GC.trait(EXPLODES_TRAIT) or {}).get("variables") or {}).get(EXPLODES_DMG_KEY)
    if not base_pct:
        return None
    extra = ((GC.ability(RAMMING_SPEED_ABILITY) or {}).get("constants") or {}).get(
        RAMMING_SPEED_EXTRA_KEY)
    dctx = dsl_context(scene, caster_id, target_id, attack_pos)
    if dctx is None:
        return None
    return int(explodes_damage_tree(int(base_pct), int(extra) if extra else 0).evaluate(dctx))


def explosion_events(scene, caster_id: int, target_id, ability_id: int, ability_name: str,
                     attack_pos=None) -> list:
    """Les batchs 3 et 4 dans l'ORDRE natif : `Friends(...)` d'abord, `Enemies(...)` ensuite.

    L'appelant a DEJA verifie la gate `self.Any(p => p.Prediction.WillBeKill)` -- elle appartient au
    playbook, pas a ce batch (cf. `_ramming_speed_self_events`).

    `friendly` n'est pas une convention de port : `IdunBattle.AI.Utilities.DamageUtility.
    u003CEvaluateAttackInStepsu003Ed__2$$MoveNext` termine par `if (IsFriend(caster, actor)) u = u *
    -1`. Le batch 3 ne selectionne QUE des amis du caster, le batch 4 QUE des ennemis : le drapeau
    est donc une propriete du BATCH, lue au selecteur.

    Une cible dont la prediction est `None` (non-attaque) n'emet pas d'event -- meme regle que
    `make_damage_predictions._event`."""
    amount = explosion_amount(scene, caster_id, target_id, attack_pos)
    if not amount:
        return []
    tile = tile_to_move_to(scene, caster_id, target_id, attack_pos)
    if tile is None:
        return []                       # `First(...)` ne designe rien -> les deux batchs sont vides
    dctx = dsl_context(scene, caster_id, target_id, attack_pos)
    if dctx is None:
        return []
    # `AdjacentUnits(<tile>, unique = 1, selectionType = 3)` = `Units(AdjacentTiles(tile), 1, 3)
    # op_Subtraction tile` -- l'origine etant une TUILE, la soustraction ne retire aucune unite.
    adjacent = AdjacentUnits(FixedTile(tile), Const(1))
    out: list = []
    for sel, friendly in ((Friends(adjacent), True), (Enemies(adjacent), False)):
        for u in sel.evaluate(dctx):
            tid = u.get("id")
            if tid is None:
                continue
            dp = generate_multi_hit_attack_prediction(
                scene, caster_id, tid, ability_id, ability_name, attack_pos=attack_pos,
                base_override=amount, hits_override=1, profile_override=EXPLOSION_PROFILE)
            if dp is not None:
                out.append(ProbableDamageEvent(target=tid, prediction=dp, friendly=friendly))
    return out
