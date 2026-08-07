"""Abilities Thousand Sons (namespace natif `Abilities.Active.Loki.*`, Tzeentch/Chaos).

Module DEDIE (org faction, comme `deathguard.py`/`genestealer.py`) : l'org native est 1 classe par
ability (`Abilities.Active.Loki.<X>Ability`) ; les arbres SPECIFIQUES vivent avec leur classe.
RE ghidra build `gqfc5mff6c` (symboles cites verbatim).

================================ Doombolt (thousAhriman, actif 1102) ================================

`IdunBattleLogic.Entities.Abilities.Active.Loki.DoomboltAbility$$ExecuteBehaviour` — MIRROR du
DECOMPILE. C'est un `ExecuteBehaviour` **imperatif qui CONSTRUIT un arbre** (et non un arbre pur) :
le natif MATERIALISE la liste de cibles (`ToList`), la RE-ORDONNE (`Remove`/`Insert(0, target)`), puis
DISTRIBUE un nombre total de coups dessus par division entiere, en accumulant un
`op_Addition(behaviour, AttackWithAttackDamage(...))` par cible. Le port mirror CETTE structure :
etage imperatif (ordre + repartition) au-dessus, feuilles DSL en dessous.

    profile   = AActiveAbility.GetDamageProfile(this)                        # Psychic
    nrOfHits  = Min( Sum( ConfigConst(0x2f = nrOfHits, config),
                          Count( EntitiesWithAnyEffect(AllTiles@0x78, 5 = Fire, sourceFlag 6) ) ),
                     Get(9) )                                                # cap LITTERAL 9
                (== `DoomboltAbility$$NrOfHitsFormula`, meme corps recopie inline)
    varMin    = GetVariableForLevel(config, 0xc = minDmg, level)             # pour le TRI seulement
    targets   = DoomboltAbility$$GetTargets()
              = Damageable( Unobscured( caster@0x160,
                                        SurroundingEnemies(caster@0x160, casterTile@0x168,
                                                           ConfigConst(0x16 = range, config), 1, 3) ) )
    sorted    = SortUnitsByDamageUtility( targets, owner@0x148, Direct(AbilityOrEffect(1102)),
                                          UtilityDefinition(0x22 = Damage), Direct(varMin), <dmgMax = null> )
    list      = sorted.ToList()
    if (list.Count == 0) return;                                             # SORTIE ANTICIPEE
    caster = TargetsSelector.SelectUnit (caster@0x160, entities)
    target = TargetsSelector.SelectActor(target@0x178, entities)
    if (caster != null && target != null && !AreEqual(caster, target)) {
        list.Remove(target); list.Insert(0, target);                         # la CIBLE passe en TETE
    }
    N = nrOfHits.Calculate(entities);  C = list.Count;  r = N % C
    damage = MinMaxDamage(this, level)                                       # RandomAmount(minDmg, maxDmg)
    behaviour = Nothing()
    foreach (u in list) {
        k = (r >= 1) ? N / C + 1 : N / C                                     # division ENTIERE
        r = (r >= 1) ? r - 1     : r
        behaviour += AttackWithAttackDamage( owner@0x148, Get(u), damage,
                                             Nullable(profile), k,
                                             AbilityOrEffect(this+0x10 = 0x44e = 1102),
                                             <alwaysOverkilled = null> )
    }
    ExecuteAtomic( 0x61, <lambda qui Execute(behaviour)> )

=> i2 CONCORDANT : « Deals 3x [dmg] Psychic Damage, evenly distributing the hits between all enemies
within 2 hexes. Adds +1 hit for each hex on the battlefield that is currently on Fire. Cannot exceed
9 hits. » La repartition « evenly » EST cette division entiere + reste : les `r = N % C` PREMIERES
cibles de la liste prennent `floor(N/C) + 1` coups, les autres `floor(N/C)` — et la CIBLE DU MESSAGE
est en tete, donc prioritaire pour le coup supplementaire.

⚠ FAMILLE = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (famille ATTACK — crit +
resolve slot-8, 2 tirages/coup a cc=0), CONTRASTE avec PlagueWind qui route
`...$$AttackWithAbilityDamage`. Classification par la CALLEE du decompile, jamais au juge (rngcrit-1202).

NON PORTE, explicitement (residus nommes) :
  * `DoomboltAbility$$GetDynamicInvalidCasterReason` = la regle-delegue `CasterMatchesDynamicRule`
    (bit 0x4 de `TargetingRule`, slot vtable `this+0x470`) : rend `0x8000000` (TargetIsInRange) quand
    `GetTargets()` est VIDE. Le canal CASTER-dynamique n'existe pas dans `abilities/targeting.py`
    (seul le canal CIBLE-dynamique, bit 0x2, y est porte) -> aucun gate invente ici. L'observable
    perdue est le TURN-FLAG d'un cast sans cible (natif : cast refuse = `actionConsumed=false`) ; le
    DEGAT, lui, est identique (la sortie anticipee `list.Count == 0` EST portee).
  * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Doombolt_ResetAbility$$CreateTrigger` = le
    « Doombolt peut etre re-utilise si Ahriman tue avec son attaque normale » de l'i2 : une ability
    TRIGGERED distincte, hors du perimetre de cet `ExecuteBehaviour`.
  * `PsychicStalk` (passif d'Ahriman : +33 % vs cible sur hex en feu, +364 pour les allies Chaos,
    mise a feu de l'hex sur l'attaque NORMALE) : passif SEPARE, ABSENT du registre de triggers
    (`runner/operations/triggers/dispatch.py`) -> non porte. INERTE sans hex en feu (le regime des
    mesures de validation), mais il manquerait des que le plateau brule.

DEJA PORTE ET ACTIF SANS RIEN AJOUTER ICI (canaux generiques, cites pour lever le doute) :
  * `WeaverOfFate` (trait 1041 d'Ahriman / triggered 1161) : le degat MAXIMAL du tour ou >= 3 ennemis
    ont recu du degat Psychic vit dans `runner/abilities/loki/weaver_of_fate.py` + la branche max-out
    des foyers de degat (`operations/damage_ops.py`, #202) -> il s'applique a Doombolt par le canal
    commun, sans cablage propre a cette ability.
"""
from __future__ import annotations

from functools import reduce
from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_add, AtomicGroup
from ...entities.damage_profile_type import DamageProfileType
from ...entities.selectors.accessors import ActiveTarget, CasterTile, Owner, Target
from ...entities.selectors.geometry import EntitiesWithAnyEffect
from ...entities.selectors.tiles import AllAliveUnits, AllTiles, Caster
from ...entities.selectors.units import (AdjacentFriends, And, Damageable, Enemies, Filter,
                                         SurroundingEnemies, UnitSet, Unobscured,
                                         non_steppable_or_object_units)
from ...entities.formulas import Count, Difference, GetPersistentData, Min, Sum
from ...entities.effect_type import EffectType
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.ability_constant_type import AbilityConstantType
from ...entities.effects.magnitude import ability_var
from ...entities.triggers import HasTakenDamageOfDamageProfileThisTurn
from ..components import StatsComponent
from ..operations.damage_prediction_sort import SortTargetsByDamagePrediction
from ..operations.damage_utility import sort_units_by_damage_utility
from .base import ActiveAbility, ability_attack_params
from .behaviours.combat import (AttackWithAttackDamage, ChainLeftOverHitsAttackDamage,
                                SortedAttackSeries)
from .behaviours.context import entities_from_state
# `DiveAttackAbilityBase` vit dans le namespace natif `...Active.Loki` : le mirror y reste, et les
# deux heritieres (1091 ici, 1064 sur `aeldari.py`) l'importent -- jamais l'une l'autre.
from .loki.dive_attack import DiveAttackAbility, dive_attack_profile
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGED_BOOL_FALSE, RANGED_BOOL_TRUE,
                        TargetingOptions)
from .targeting_rule import TargetingRule as TR

if TYPE_CHECKING:
    from ..state import State

DOOMBOLT_ID = "Doombolt"
FIRE = int(EffectType.Fire)          # 5 — `EntitiesWithAnyEffect(AllTiles, 5, 6)` = les hexes EN FEU
# `Get(9)` LITTERAL du decompile (`DSLFactory$$Get(int)` = noeud constante), PAS une constante de
# config : la valeur est codee dans `DoomboltAbility$$NrOfHitsFormula` / `$$ExecuteBehaviour`.
# i2 concordant : « Cannot exceed 9 hits. »
DOOMBOLT_MAX_HITS = 9


def _ability_state(state: "State", caster_id: int) -> tuple:
    """`(level, multiplier)` de l'ability ACTIVE du caster — meme source que `ability_attack_params`
    (`StatsComponent.ctx.active_ability_level` / `.ability_variables_multiplier`)."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    return level, mult


def doombolt_targets_selector() -> Damageable:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DoomboltAbility$$GetTargets` (MIRROR 1:1) :

        Damageable( Unobscured( caster@0x160,
                                SurroundingEnemies(caster@0x160, casterTile@0x168,
                                                   ConfigConst(0x16 = range), 1, 3) ) )

    = les ennemis VIVANTS du caster a distance hex <= `range` (constante config = 2), dont la tuile
    n'est pas obscurcie DEPUIS le caster. `SurroundingEnemies` exclut deja le centre (le natif
    soustrait `Tiles(center)` du disque). Le `range` est lu du gameconfig (`GetNumberConstant(0x16)`)
    : `ctx.config` n'est pas branche par `entities_from_state`, donc on l'injecte en `Const` — meme
    convention que le `nrOfTargets` de `fragstorm_tree`."""
    rng = int(((GC.ability(DOOMBOLT_ID) or {}).get("constants") or {}).get("range") or 2)
    return Damageable(Unobscured(SurroundingEnemies(CasterTile(), Const(rng)), Caster()))


def doombolt_nr_of_hits_formula() -> Min:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DoomboltAbility$$NrOfHitsFormula` (MIRROR 1:1 ;
    `$$ExecuteBehaviour` recopie le MEME corps inline) :

        Min( Sum( ConfigConst(0x2f = nrOfHits, config),
                  Count( EntitiesWithAnyEffect(AllTiles@0x78, Fire = 5, sourceFlag = 6) ) ),
             Get(9) )

    `AllTiles@0x78` = le slot partage `AllTilesSelector` de `DSLFactory$$InitializeShared` -> le
    compte porte sur TOUT le plateau (pas seulement autour du caster), conforme a l'i2 (« each hex on
    the battlefield that is currently on Fire »). `EntitiesWithAnyEffect` route les entites-TUILE sur
    `ctx.tile_has_effect` (meme cle tile-id que la pose `AddEffectOperation`, cf. case-35 / Stormcaller
    #217). `ConfigConst(0x2f)` est injectee en `Const` (cf. `doombolt_targets_selector`)."""
    hits = int(((GC.ability(DOOMBOLT_ID) or {}).get("constants") or {}).get("nrOfHits") or 3)
    return Min(Sum(Const(hits), Count(EntitiesWithAnyEffect(AllTiles(), [FIRE]))),
               Const(DOOMBOLT_MAX_HITS))


def doombolt_ordered_targets(state: "State", caster_id: int, target_id: Optional[int],
                             candidates: list, dmg_min: int) -> list:
    """`SortUnitsByDamageUtility(...)` puis `list.Remove(target); list.Insert(0, target)` — MIRROR.

    - Le TRI = `IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select` (deja porte,
      `runner/operations/damage_utility.py`) : utilite `UtilityDefinition(0x23 = Damage)` DECROISSANTE.
      Le noeud de degat branche par ce call-site est `Direct(GetVariableForLevel(0xc = minDmg, level))`,
      le noeud d'ABILITY est `Direct(AbilityOrEffect(1102))` (3e argument du factory), et le slot
      `hits` (+0x48) recoit **null** (8e argument = 0) -> la cle predit **UN** coup.
      ⚠ Le commentaire d'avant #494-r1-r1 lisait `+0x48` comme un `dmgMax` : c'est `hits`, cf.
      l'en-tete de `damage_utility.py`.
    - Le REORDONNANCEMENT natif est INCONDITIONNEL des que caster et cible existent et different :
      `Remove` est un no-op si la cible n'etait pas dans la liste, mais `Insert(0, ...)` l'ajoute
      QUAND MEME -> la cible du message est TOUJOURS en tete (et compte dans `C`). On mirror tel quel.

    `candidates` = ids d'unite rendus par `doombolt_targets_selector`."""
    # `owner_id = caster` (#494-r1) : le selecteur natif resout son `+0x20` en unite (`SelectUnit`) et
    # passe SA POSITION a la prediction PAR CIBLE -- sans lui, la cle de tri perd sa part
    # POSITIONNELLE (bonus d'elevation) et le classement diverge des que deux cibles ne sont pas a la
    # meme hauteur. `candidates` arrive dans l'ORDRE SOURCE du selecteur (cube-lex), qui EST le
    # tie-break natif : ne jamais le re-trier ici.
    # #494-r1-r1 : la cle est la PREDICTION COMPLETE -> l'ability du noeud `+0x28`
    # (`Direct(AbilityOrEffect(1102))`) descend jusqu'a elle. Ni PROFIL ni PERCAGE : le selecteur
    # passe `damageProfile: null`, donc percage 0 (cf. l'en-tete de `damage_utility.py`).
    # `is_melee=False` = `attackRangeType = Ranged` de 1102, comme les feuilles de `doombolt_tree`.
    ordered = list(sort_units_by_damage_utility(
        state, candidates, dmg_min, dmg_min, owner_id=caster_id, is_melee=False,
        ability_type=int(ActiveAbilityType.Doombolt)))
    if target_id is None or int(caster_id) == int(target_id):
        return ordered
    tid = int(target_id)
    ordered = [u for u in ordered if int(u) != tid]        # list.Remove(target)
    ordered.insert(0, tid)                                 # list.Insert(0, target)
    return ordered


def doombolt_hits_distribution(total_hits: int, count: int) -> list:
    """Repartition « evenly » des `total_hits` sur `count` cibles — MIRROR EXACT de la boucle native
    (`ExecuteBehaviour`, variables `iVar5 = N`, `iVar6 = C`, `uVar25 = r`) :

        r = N % C
        foreach u :
            k = (r >= 1) ? N / C + 1 : N / C       # division ENTIERE C#
            r = (r >= 1) ? r - 1     : r

    -> les `N % C` PREMIERES cibles prennent un coup de plus. `k` peut valoir **0** (N < C) : le natif
    construit quand meme le behaviour d'attaque pour cette cible (aucun court-circuit), donc le port
    aussi. `count <= 0` -> liste vide (le natif n'atteint jamais ce cas : sortie anticipee si la liste
    initiale est vide)."""
    n, c = int(total_hits), int(count)
    if c <= 0:
        return []
    r = n % c
    out = []
    for _ in range(c):
        out.append(n // c + 1 if r >= 1 else n // c)
        r = r - 1 if r >= 1 else r
    return out


def doombolt_tree(targets: list, hits_per_target: list) -> AtomicGroup:
    """Arbre construit par la boucle de `DoomboltAbility$$ExecuteBehaviour` :
    `ExecuteAtomic(0x61, Nothing() + a1 + a2 + ... + aN)`.

    Chaque `a_i` = `AttackWithAttackDamage(owner@0x148, Get(u_i), MinMaxDamage, Nullable(Psychic),
    k_i, AbilityOrEffect(1102), alwaysOverkilled = null)` -> feuille MONO-CIBLE (`multi=False` : le
    natif passe UNE entite par behaviour, pas un selecteur multi) avec un nb de coups EXPLICITE
    (`hits=k_i`, le natif passe un `int` calcule, PAS `GetNumberConstant(0x2f)`).

    - `owner@0x148` == le caster pour une active top-level (`AbilityEntities` Owner = Caster) ->
      `entities.caster` de la feuille, inchange.
    - `Get(u)` = `IdunBattleLogic.Entities.DSLFactory$$Get(entity)` = selecteur d'UNE entite ->
      `UnitSet([u])` cote port (meme role que `FixedTileIds` en domaine tuile).
    - Le `Nothing()` en tete de l'accumulateur natif est un behaviour NEUTRE (aucune mutation, aucun
      tirage) -> folde ici : la liste est non vide par construction (sortie anticipee en amont).
    - `native_factory="attack"` (defaut) = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`
      LU au decompile -> `AttackDamageOperation` (crit + resolve slot-8). `is_melee=False`
      (`attackRangeType=Ranged`), profil `Psychic` (PiercingRatio 100, `NoBlocking`)."""
    leaves = [AttackWithAttackDamage(UnitSet([u]), DOOMBOLT_ID, "Psychic", is_melee=False,
                                     hits=int(k), ability_type=int(ActiveAbilityType.Doombolt))
              for u, k in zip(targets, hits_per_target)]
    return AtomicGroup(reduce(op_add, leaves))


class DoomboltAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DoomboltAbility$$ExecuteBehaviour` (id 1102,
    `thousAhriman` « Ahriman », Thousand Sons/Chaos — HERO, present dans `rl_duel build --list-pool`).

    `nrOfHits` (=3) + 1 coup PAR HEX EN FEU du plateau, cape a 9, REPARTIS « evenly » sur TOUS les
    ennemis a <= `range` (=2) hexes non obscurcis : les `N % C` premieres cibles prennent
    `floor(N/C) + 1` coups, les autres `floor(N/C)`. L'ordre = utilite de degat DECROISSANTE
    (`SortUnitsByDamageUtility`), la CIBLE DU MESSAGE etant forcee EN TETE. Profil `Psychic`
    (pierce 100, `NoBlocking`), famille ATTACK (crit possible).

    `TARGETING_OPTIONS = None` (defaut) : le masque du `DoomboltAbility$$.ctor` n'est pas RE-lu ici et
    la seule regle propre a l'ability est une regle CASTER-dynamique (bit 0x4), canal NON porte par
    `abilities/targeting.py` -> aucun gate invente (cf. l'en-tete du module). Termine le tour (1102
    hors des frozensets de `base.py`).

    Diag : `{targets, hits, total_hits, attacks}` — `targets`/`hits` sont la liste ORDONNEE et sa
    repartition (ce qui rend la mecanique confrontable coup par coup)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Doombolt)   # 1102
    ABILITY_ID = DOOMBOLT_ID

    # MASQUE — `DoomboltAbility$$.ctor` recopie les 0x40 octets du champ STATIQUE `statics+0x3c0`,
    # les passe a l'overload de COPIE `IdunBattle.Core.Services.TargetingOptions$$.ctor(&dest, &src)`
    # (aucun flag ajoute), puis fait `AActiveAbility..ctor(this, &opts, 2, 0)`. Le masque EFFECTIF est
    # donc la constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a
    # `<preset>+0x28` (= `statics+0x3e8`, ecrit `*(lVar4 + 1000) = 0x200000000000004`) :
    # **0x200000000000004** (LU, pas deduit).
    #     0x200000000000000  TargetIsCasterOrEnemy    -> regle NON portee par la cascade statique
    #                        (cf. l'inventaire de `targeting.py`) : degradation PERMISSIVE assumee.
    #     0x000000000000004  CasterMatchesDynamicRule -> la regle CASTER-dynamique, c.-a-d.
    #                        `DoomboltAbility$$GetDynamicInvalidCasterReason` (refuse le cast quand
    #                        `GetTargets()` est VIDE). Ce CANAL n'existe pas cote port (seul le canal
    #                        CIBLE-dynamique, bit 0x2, y est porte) -> aucun gate invente ici ; residu
    #                        nomme dans `docs/rl/case-psychic-aoe.md` §5.1 et au backlog.
    # ⚠ PAS de `TargetIsEnemy` (0x4000) dans ce masque : la legalite de cible passe ENTIEREMENT par
    # les deux regles ci-dessus. Ne rien ajouter « par symetrie » avec PlagueWind.
    # PORTEE — le preset copie son `TargetingRange` (`<preset>+0x08..0x1f`) depuis le MEME statique
    # que PlagueWind (`TargetingRange statics+0x18`, le cctor lit `*(lVar3+0x18)/+0x20/+0x28`) =
    # `RANGE_FROM_CONFIG` -> `SetConfigValuesInTargetingOptions` y pose
    # `overrideRange = GetNumberConstant(0x16 range)` = 2 (config 1102, la MEME portee que celle du
    # selecteur `GetTargets`). `forceMeleeTarget` = `*(preset+0x20)` = **1** = `RANGED_BOOL_FALSE`
    # (⚠ l'enum natif est INVERSE : True=0, False=1) -> aucun clamp RangedInMelee.
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetIsCasterOrEnemy | TR.CasterMatchesDynamicRule),
        range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        entities = entities_from_state(state, caster_id, target_id)
        # `GetTargets()` materialise (`ToList` natif) : le tri + le reordonnancement operent sur une
        # LISTE figee, pas sur un selecteur lazy.
        cand = [u for u in (doombolt_targets_selector().evaluate(entities) or [])
                if isinstance(u, dict) and u.get("id") is not None]
        if not cand:
            # `if (list.Count == 0) return;` — AUCUNE attaque construite (le natif ne va meme pas
            # jusqu'a l'AtomicGroup). Le cast reste EXECUTE (flags de tour poses par le handler).
            return {"ability": DOOMBOLT_ID, "caster": caster_id, "target": target_id,
                    "targets": [], "hits": [], "total_hits": 0, "attacks": [], "dsl": True}
        by_id = {int(u["id"]): u for u in cand}
        if target_id is not None and entities.target is not None:
            by_id.setdefault(int(target_id), entities.target)   # `Insert(0, target)` hors-liste
        level, mult = _ability_state(state, caster_id)
        dmg_min = int(ability_var(DOOMBOLT_ID, "minDmg", level, multiplier_pct=mult) or 0)
        ordered = doombolt_ordered_targets(state, caster_id, target_id,
                                           [int(u["id"]) for u in cand], dmg_min)
        ordered = [t for t in ordered if t in by_id]
        total_hits = int(doombolt_nr_of_hits_formula().evaluate(entities))
        dist = doombolt_hits_distribution(total_hits, len(ordered))
        ectx = ExecutionContext(state=state, rng=state.rng)
        doombolt_tree([by_id[t] for t in ordered], dist).execute(entities, ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total"), "attack": p.get("attack")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": DOOMBOLT_ID, "caster": caster_id, "target": target_id,
                "targets": ordered, "hits": dist, "total_hits": total_hits,
                "attacks": attacks, "dsl": True}


# ========================= HellfyreMissileRack (thousTerminator, actif 1088) =========================
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.HellfyreMissileRackAbility$$ExecuteBehaviour` --
# arbre `DSLFactory` PUR (aucun etage imperatif, contraste Doombolt), MIRROR du DECOMPILE :
#
#     dmg     = AActiveAbility.MinMaxDamage(this, abilityState)                     # minDmg/maxDmg[level]
#     profile = DSLSelectors.Direct( AbilityConfiguration.GetDamageProfile(cfg) )   # HeavyRound
#     hits    = DSLFormulas.Get( AbilityConfiguration.GetNumberConstant(cfg, 0x2f) ) # nrOfHits = 1
#     atk1    = DSLBehaviors.AbilityDamage(Caster@+0x48, ActiveTarget@+0x68, dmg, profile, hits,
#                                          <AbilityOrEffect 1088>, isOutsideAttack=false, selectionType=2)
#     atk2    = DSLBehaviors.AbilityDamage( <MEMES arguments> )                     # 2e instance
#     extra   = DSLSelectors.FromTrigger(
#                   DSLSelectors.NonSteppableOrObjectUnits(
#                       DSLSelectors.Enemies(Caster@+0x48, AllAliveUnits@+0x20, 3), 3),
#                   DSLTriggers.HasTakenDamageOfDamageProfileThisTurn(ActiveTarget@+0x68, 0xd),
#                   requireContinuous = 0)
#     AActiveAbility.Execute( entities, this,
#         DSLBehaviors.SortedAttackSeries(Caster@+0x48, Target@+0x60, atk1, extra, atk2,
#                                         <AbilityOrEffect 1088>) )
#
# `HellfyreMissileRackAbility$$GetAffectedUnits` re-construit `extra` A L'IDENTIQUE -> le 2e volet est
# bien le sous-arbre ci-dessus, pas une lecture optimiste du decompile.
#
# QUALIFICATION DES ORDINAUX (le point le plus piegeur de cette ability) :
#   * `0x2f`  -> `AbilityConstantType.nrOfHits` (cle gameconfig `nrOfHits` = 1) ;
#   * `0xd`   -> **DEUX enums differents dans la MEME expression** : `DamageProfileType.Psychic` (le
#     trigger) et `UnitTrait.Object` (dans `NonSteppableOrObjectUnits`, avec `0x1b` = `Steppable`).
#     L'ordinal nu aurait confondu les deux SANS erreur.
#   * Le profil INFLIGE est `HeavyRound` (config), le profil TESTE est `Psychic` -- ne PAS deduire
#     l'un de l'autre. i2 : « Deals 1x [dmg] Heavy Round Damage to a target enemy unit within range 3
#     and an additional 1x [dmg] Heavy Round Damage to each enemy unit on the map that was dealt
#     PSYCHIC Damage this turn, which can include the initial target again. »
#
# FAMILLE = `DSLBehaviors$$AbilityDamage` -> `AbilityDamageBehaviour` (famille ABILITY :
# `AbilityDamageOperation$$ExecuteHits`, 1 tirage/coup, PAS de crit/block) -> `native_factory="ability"`.
# CONTRASTE avec `FragBombAbility$$ExecuteBehaviour`, qui a la MEME forme `SortedAttackSeries` mais
# route `DSLBehaviors$$AttackDamage` (famille ATTACK). Classification par la CALLEE, jamais au juge.
# ====================================================================================================

HELLFYRE_ID = "HellfyreMissileRack"
# `GetDamageProfile(cfg)` = gameconfig `HellfyreMissileRack.constants.damageProfile` = `HeavyRound`.
# C'est le profil INFLIGE par les deux volets (ils partagent `profile`, `dmg` et `hits`).
HELLFYRE_PROFILE = DamageProfileType.HeavyRound.name
# `DSLTriggers$$HasTakenDamageOfDamageProfileThisTurn(unit, 0xd)` -- `0xd` est ici un
# `DamageProfileType`, PAS le `UnitTrait.Object` de meme ordinal utilise deux lignes plus haut par
# `NonSteppableOrObjectUnits`. Meme constante que `weaver_of_fate`/`reality_unbound` (Thousand Sons).
HELLFYRE_TRIGGER_PROFILE = int(DamageProfileType.Psychic)   # 0xd = 13


def hellfyre_extra_targets_selector() -> Filter:
    """Sous-arbre `extra` de `HellfyreMissileRackAbility$$ExecuteBehaviour` -- IDENTIQUE au corps
    ENTIER de `$$GetAffectedUnits` (MIRROR 1:1) :

        FromTrigger( NonSteppableOrObjectUnits( Enemies(Caster@+0x48, AllAliveUnits@+0x20, 3), 3 ),
                     HasTakenDamageOfDamageProfileThisTurn(ActiveTarget@+0x68, Psychic),
                     requireContinuous = 0 )

    * `Enemies(Caster, AllAliveUnits)` : le natif passe le slot PARTAGE `DSLSelectors+0x20` (alloue par
      `DSLSelectors$$InitializeShared`) comme source, et `+0x48` (= `Caster`) comme reference. Le port
      `Enemies(inner)` prend sa reference dans `ctx.caster` -> meme semantique a ce call-site.
      `AllAliveUnits` porte le filtre VIVANTES parce que le slot `+0x20` EST
      `IdunBattle.Entities.Selectors.AllAliveUnitsSelector` (pool `EntityPool.AliveUnits`) -- #514.
    * `NonSteppableOrObjectUnits` = la factory de composition (cf. son mirror dans
      `entities/selectors/units.py`) : `source & sans-Steppable & sans-Object`.
    * `FromTrigger` = `Filter` cote port (`DSLFactory$$Filter` est le THUNK de `$$FromTrigger`) : il
      LIE chaque candidat au slot `+0x180` = `ActiveTarget`, exactement le slot que le predicat lit.
      `requireContinuous = 0` -> aucun court-circuit (le port ne porte pas ce flag ; `FilterContinuous`
      est une factory distincte).
    * Le predicat est `HasTakenDamageOfDamageProfileThisTurn` **SANS** `AmountOfTimes` : une PRESENCE
      de cle dans `receivedDamageThisTurn`, donc un ennemi ayant encaisse DEUX coups Psychic compte
      toujours (contraste `RealityUnboundExtraMaxDamageAbility`, qui exige `== 1`)."""
    return Filter(non_steppable_or_object_units(Enemies(AllAliveUnits())),
                  HasTakenDamageOfDamageProfileThisTurn(ActiveTarget(), HELLFYRE_TRIGGER_PROFILE))


def hellfyre_missile_rack_tree() -> SortedAttackSeries:
    """Arbre COMPLET de `HellfyreMissileRackAbility$$ExecuteBehaviour` -- MIRROR 1:1.

    `SortedAttackSeries(Caster@+0x48, Target@+0x60, atk1, extra, atk2, <AbilityOrEffect 1088>)` :
    le noeud resout les DEUX selecteurs D'ABORD (`$$GetAttacks` construit le `Dictionary` complet),
    puis rejoue les behaviours par cible dans l'ORDRE D'INSERTION -- donc :

      * une unite presente dans les DEUX selecteurs (la cible du message ayant DEJA pris du Psychic
        AVANT ce cast) recoit les DEUX attaques, consecutivement. C'est le « which can include the
        initial target again » de l'i2 ;
      * le coup du volet 1 est `HeavyRound`, donc il ne rend JAMAIS sa propre cible eligible au volet
        2 -- et de toute facon le selecteur est deja resolu quand il part.

    ⚠ Le 1er selecteur est `Target@+0x60` NU (le natif ne l'enveloppe PAS dans `Units(...)`, contraste
    `FragBombAbility$$ExecuteBehaviour` qui passe `Units(Target@+0x60, 1, 1)`).

    ⚠ `AActiveAbility$$Execute`, PAS `$$ExecuteAtomic` -> **aucun `AtomicGroup`** ici (FragBomb, lui,
    finit par `ExecuteAtomic(..., 0x43)`).

    Les deux `AbilityDamage` sont deux INSTANCES distinctes aux arguments IDENTIQUES (c'est ce que
    fait le natif : deux allocations de `AbilityDamageBehaviour` sur les memes noeuds)."""
    atk1 = AttackWithAttackDamage(ActiveTarget(), HELLFYRE_ID, HELLFYRE_PROFILE, is_melee=False,
                                  native_factory="ability",
                                  ability_type=int(ActiveAbilityType.HellfyreMissileRack))
    atk2 = AttackWithAttackDamage(ActiveTarget(), HELLFYRE_ID, HELLFYRE_PROFILE, is_melee=False,
                                  native_factory="ability",
                                  ability_type=int(ActiveAbilityType.HellfyreMissileRack))
    return SortedAttackSeries([(Target(), atk1),
                               (hellfyre_extra_targets_selector(), atk2)])


class HellfyreMissileRackAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HellfyreMissileRackAbility$$ExecuteBehaviour`
    (id 1088, `thousTerminator` « Toth », Thousand Sons/Chaos -- HERO, present dans
    `rl_duel build --list-pool`). Cast UNIT-TARGET, RANGED (`attackRangeType = Ranged`, `range = 3`).

    Kit gameconfig 1088 : `damageProfile = HeavyRound`, `range = 3`, `nrOfHits = 1`,
    `minDmg`/`maxDmg`[level] (rarity-affected, `variablesAffectedByRarityBonus`). AUCUNE variable `_2`
    -> les DEUX volets partagent plage, profil et nombre de coups.

    OBSERVABLE : la cible designee encaisse `nrOfHits` coups HeavyRound ; **CHAQUE ennemi vivant du
    plateau** (non-`Steppable`, non-`Object`) ayant deja encaisse du degat **Psychic** ce tour en
    encaisse `nrOfHits` de plus -- la cible designee comprise si elle est dans ce cas.

    AVANT ce port, 1088 etait absente d'`ABILITY_CLASSES` : `visit_ActiveAbilityMessage` rendait
    `ported:False` -> **0 degat, 0 effet, aucune erreur** (no-op SILENCIEUX).

    Flags de tour : defauts base (1088 absente des overrides) -> termine le tour + ActiveAbilityUsed.
    Retour : `{main_attack, extra, order, dsl}` -- `order` est l'ordre d'insertion resolu par
    `SortedAttackSeries`, ce qui rend la SEQUENCE de tirages confrontable coup par coup."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HellfyreMissileRack)   # 1088
    ABILITY_ID = HELLFYRE_ID

    # MASQUE -- `HellfyreMissileRackAbility$$.ctor` n'appelle AUCUN `TargetingOptions$$.ctor` : il
    # recopie les 0x40 octets du champ STATIQUE `<TargetingOptions statics>+0x140` et les passe
    # directement a `AActiveAbility$$.ctor(this, &opts, 0)`. Le masque EFFECTIF est donc la constante
    # ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` (= le
    # `*(lVar4 + 0x168) = 0x4002` de son corps) : **0x4002** (LU, pas deduit).
    #     0x4000  TargetIsEnemy
    #     0x0002  TargetMatchesDynamicRule
    # ⚠ MEME masque que 1027 `PsychicMaelstrom` / 1069 `SeekerMissileFrequencyLock`, mais preset
    # DIFFERENT : `forceMeleeTarget = *(preset+0x20)` vaut **0** ici (`<preset>+0x160 = 0`) =
    # `RangedBool.True` (l'enum natif est INVERSE : True=0, False=1), contre 1 chez eux. C'est le seul
    # champ qui les separe et il change le regime de portee -> ne rien generaliser d'une autre ability.
    # PORTEE : le preset copie son `TargetingRange` depuis `<TargetingRange statics>+0x18` =
    # `RANGE_FROM_CONFIG` -> `SetConfigValuesInTargetingOptions` y pose
    # `overrideRange = GetNumberConstant(0x16 = range)` = 3 (config 1088).
    # Cette entree a MIGRE de `TARGETING_OPTIONS_UNPORTED` vers cette classe dans le meme commit que
    # l'entree au registre COMBAT (contrat de disjonction des deux sources de masque).
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy), self_cast=False,
        range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        hellfyre_missile_rack_tree().execute(
            entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        # ⚠ La cible du message peut recevoir DEUX attaques (volet 1 puis volet 2, consecutivement,
        # cf. `SortedAttackSeries`) : ventiler par `target != target_id` PERDRAIT la seconde. On
        # retire donc la PREMIERE occurrence sur la cible (= le volet 1) et tout le reste est `extra`.
        main, extra, main_taken = None, [], False
        for p in atks:
            if not main_taken and p.get("target") == target_id:
                main, main_taken = p["attack"], True
                continue
            extra.append({"target": p["target"], "attack": p["attack"]})
        order = next((p["order"] for n, p in ectx.emitted if n == "SortedAttackSeries"), [])
        return {"ability": HELLFYRE_ID, "caster": caster_id, "target": target_id,
                "main_attack": main, "extra": extra, "order": order, "dsl": True}


# ====================================================================================================
# SlashingDive (1091, `thousNpc2Screamer` / `thousSmnScreamer` « Screamer ») -- #507
# ====================================================================================================
# Classe native `IdunBattleLogic.Entities.Abilities.Active.Loki.SlashingDiveAbility`. Elle est VIDE
# hors ctor : TOUTE la mecanique vit sur la base `...Active.Loki.DiveAttackAbilityBase`, portee dans
# `engine/runner/abilities/loki/dive_attack.py` -- decompile complet et lectures qui le tranchent
# dans SON en-tete. L'autre heritiere est `1064 Loki_SwoopingHawk` (`aeldari.py`, #502).
#
# ⚠ LE PARTAGE SE PROUVE AU RUNTIME, PAS PAR L'ABSENCE. `SlashingDiveAbility$$.ctor` n'a AUCUN
# proprietaire nomme dans `frida/methods.tsv` ni `ghidra/functions.tsv` : IL2CPP a fusionne son corps
# avec celui de `SwoopingHawkAbility$$.ctor` (les deux sont `return DiveAttackAbilityBase$$.ctor(this);`)
# et ces tables sont indexees par ADRESSE. C'est ce faux negatif qui avait fait classer 1091 en
# « NON-LU » dans `TARGETING_OPTIONS_UNPORTED`. Le slot de methode de la CLASSE, lu en live sur le
# build `rnca9r7q6c` (RPC `resolveMethodPtr`), rend :
#   - `.ctor` a depth=0, a la MEME adresse d'entree que `SwoopingHawkAbility$$.ctor` ;
#   - `ExecuteBehaviour` / `GetTargetTilesSelector` / `GetTargetUnitsSelector` / `GetMovementBehavior`
#     tous a depth=1, sur `DiveAttackAbilityBase` -> AUCUNE surcharge.
# `classes.tsv` corrobore par une seconde voie (parent = `DiveAttackAbilityBase`, taille 240, comme
# `SwoopingHawkAbility`).
#
# CE QUI DIFFERE DE 1064 est la seule CONFIG, RELUE ability par ability (jamais recopiee de la soeur) :
#   `damageProfile` = **Power**  (1064 : Piercing)   -- profil de percage/armure du coup
#   `nrOfHits`      = 1          (1064 : 1)
#   `attackRangeType` = Melee    (1064 : Melee)      -- quelle arme du caster le volet percage lit
#   `dmg`           = 3 valeurs DECROISSANTES par niveau (lvl 65 : 1819 / 1455 / 1091)
#
# PORTEURS (gate de confrontabilite) : `thousNpc2Screamer` (npc), `thousSmnScreamer` et
# `thousSmnScreamerHSE` (summons) -- AUCUN lineup. Le npc porte une table `units.npc[].stats[]` de
# 45 paliers, donc il arrive en bataille par le CHEMIN DE STATS EXPLICITE (`case-92` §5bis recours 4,
# `--explicit-stats thousNpc2Screamer:<palier>`) avec SES stats, SES traits et SON arme : c'est le
# mirror, pas un montage, et il est COMMANDABLE. La voie summon existe aussi (`MasterOfTheTutelaries`
# 1096 d'Abraxas `thousInfernalMaster`, DU POOL, pose l'effet 1197 qui arme la triggered 1173 ->
# Screamer), mais elle n'OBSERVE que ce que l'IA choisit -- elle ne commande pas la geometrie.

SLASHING_DIVE_ID = "SlashingDive"                            # cle gameconfig de l'ability 1091


def slashing_dive_profile() -> str:
    """`AActiveAbility$$GetDamageProfile` pour 1091 (= « Power » au gameconfig courant).

    Accesseur d'ABILITY au-dessus du foyer de la base (`dive_attack_profile`) : le profil est l'un
    des trois axes que `DiveAttackAbilityBase` ne fige PAS -- 1064, MEME code natif, vaut
    « Piercing ». Relire par ability, jamais recopier d'une soeur."""
    return dive_attack_profile(SLASHING_DIVE_ID)


class SlashingDiveAbility(DiveAttackAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SlashingDiveAbility` (id **1091**, Screamer,
    Thousand Sons) -- MIRROR du DECOMPILE.

    Le Screamer plonge sur un ennemi ADJACENT et balaie la ligne : la cible prend `dmg[0]`, l'unite
    un hex derriere `dmg[1]`, celle deux hexes derriere `dmg[2]` -- un coup `Power` chacune
    (`nrOfHits` = 1). Il atterrit ensuite dans l'hex juste derriere la DERNIERE cible touchee, ou,
    s'il est occupe, sur la tuile libre la plus proche de celui-ci.

    La classe native n'a QUE son ctor : toute la mecanique est heritee de `DiveAttackAbilityBase`,
    et ce mirror n'ajoute donc rien d'autre que l'identite et les deux donnees du registre."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SlashingDive)        # 1091 = 0x443
    ABILITY_ID = SLASHING_DIVE_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET STATIQUE COPIE**, la 3e des
    # trois formes : ni `SlashingDiveAbility$$.ctor` (= le corps FUSIONNE avec celui de
    # `SwoopingHawkAbility$$.ctor`, cf. le bandeau) ni `DiveAttackAbilityBase$$.ctor` n'appellent
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor`. La base recopie les 0x40 octets du champ
    # STATIQUE de `TargetingOptions` a l'offset **`+0x40`** du bloc `<class>+0xb8`, puis :
    #     AActiveAbility..ctor(this, &opts, 0)   # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
    # Aucun litteral de masque n'est visible dans le ctor : le masque EFFECTIF est la constante
    # ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28`.
    # Le preset lu EN ENTIER (bloc `statics+0x40`), pas seulement son champ `Rules` :
    #     <preset>+0x00 = *(statics+0x40) = 0                  -> isSelfCasting = false
    #     <preset>+0x08 = copie de `TargetingRange statics+0x30` -> **RANGE_ADJACENT**
    #     <preset>+0x20 = *(statics+0x60) = 1                  -> forceMeleeTarget = RangedBool.False
    #     <preset>+0x28 = *(statics+0x68) = 0x4000             -> Rules = `TargetIsEnemy` SEUL
    # AUCUN `TargetMatchesDynamicRule` (0x2) ni `CasterMatchesDynamicRule` (0x4) -> les deux
    # `GetDynamicInvalid*Reason` de la base restent au defaut 0 : l'absence de 1091 dans
    # `DYNAMIC_TARGET_RULE_UNPORTED` est donc EXACTE (verifiee, pas supposee).
    # 1091 n'etait PAS dans `TARGETING_OPTIONS_UNPORTED` (elle y figurait comme NON-LU explicite,
    # faute de ctor lisible) : aucune migration, aucun compteur a decrementer -- seul le paragraphe
    # de `targeting.py` qui la declarait non-lue est reecrit.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False,
                                         range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)


# ====================================================================================================
# HeavyWarpFlamer (1227, `thousSekhetar` « Sekhetar Robot ») -- #523
# ====================================================================================================

HEAVY_WARP_FLAMER_ID = "HeavyWarpFlamer"                     # cle gameconfig de l'ability 1227
HEAVY_WARP_FLAMER_PROFILE = "Flame"      # `AbilityConfiguration$$GetDamageProfile` (gameconfig 1227)
# `DAT_183370b30`, le litteral de `dataKey` que PARTAGENT les deux seuls lecteurs/ecrivains du sac
# persistant de cette ability -- `HeavyWarpFlamerAbility$$GetNumExtraHits` (lecture) et
# `HeavyWarpFlamer_AttackTrackingAbility$$CreateBehaviour` (Set + Clear). Resolu par le slot du
# build : `data/symbols/rnca9r7q6c/metadata/string_literals.tsv` ligne `13388 0x3370b30
# "PSYCHIC_ATTACKS_KEY"`. Les xrefs du slot sont EXHAUSTIVEMENT ces deux fonctions -> cle privee.
HEAVY_WARP_FLAMER_STACK_KEY = "PSYCHIC_ATTACKS_KEY"
# `hits` du selecteur de PREDICTION : le natif passe le champ `<DSLFormulas+0x20>` de l'instance
# partagee, que `IdunBattleLogic.Entities.DSLFormulas$$.ctor` initialise avec la constante **1**
# (il alloue `0 / 1 / 2 / 100 / -1` aux slots `+0x18 / +0x20 / +0x28 / +0x30 / +0x38`). Ce n'est
# donc PAS `nrOfHits` : le classement des cibles de report se fait sur la prediction d'UN coup.
HEAVY_WARP_FLAMER_PREDICTION_HITS = 1


def heavy_warp_flamer_other_targets(range_val: int) -> And:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyWarpFlamerAbility$$GetOtherTargets`
    -- MIRROR 1:1 :

        Damageable( AdjacentFriends(unit = Target@DSLSelectors+0x60, unique = 1,
                                    unitSelectionType = 3) )
        op_BitwiseAnd
        SurroundingEnemies(unit = Caster@DSLSelectors+0x48,
                           range = Get(GetNumberConstant(0x16 = range)),
                           unique = 1, unitSelectionType = 3)

    Les DEUX surcharges sont tranchees par leurs XREFS ENTRANTES (deux corps homonymes chacune) :
      * `AdjacentFriends(unit, unique, selectionType)` (3 args) =
        `Friends(reference = unit, Units(AdjacentTiles(unit), unique, sel) op_Subtraction unit, sel)`
        -> la REFERENCE d'equipe EST le centre. Le centre est ici la CIBLE, pas le caster : ce sont
        donc les ALLIES DE LA CIBLE = les ENNEMIS du caster, anneau d'adjacence, cible EXCLUE (le
        `- unit` du corps natif). Le collapse `reference=None` (== `ctx.caster`) rendrait le camp
        INVERSE -> `reference=Target()` est OBLIGATOIRE ici.
      * `SurroundingEnemies(unit, range, unique, selectionType)` (4 args) =
        `Enemies(reference = unit, Units(SurroundingTiles(unit, includeCenter=1, range)
        op_Subtraction Tiles(unit), unique, sel), sel)` -> le MEME selecteur sert de centre ET de
        reference, d'ou `reference=Caster()` explicite. Pas d'`Unobscured` dans cette surcharge.

    => « les ennemis du caster ADJACENTS a la cible ET a distance <= `range`(2) du CASTER ». C'est la
    geometrie que l'utilite IA `HeavyWarpFlamer_LikesAdjacentEnemies` recompense (elle compte les
    ennemis adjacents a la TUILE DE LA CIBLE, cf. `playbook/loki_custom.py`).

    ⚠ Le `Damageable` ne porte QUE sur le volet `AdjacentFriends` (le natif fait
    `op_BitwiseAnd(Damageable(adj), surrounding)`, pas `Damageable(adj & surrounding)`) -- sans effet
    observable ici (l'intersection ne peut pas RAJOUTER de mort), mais on ecrit ce qui est lu.

    ⚠ Le meme ensemble est RECOPIE INLINE par `$$ExecuteBehaviour` (le natif ne rappelle pas
    `$$GetOtherTargets`) -> un seul foyer cote port, comme pour 1048."""
    return And(Damageable(AdjacentFriends(Target(), reference=Target())),
               SurroundingEnemies(Caster(), Const(range_val), reference=Caster()))


def heavy_warp_flamer_num_extra_hits(nr_of_hits: int, max_nr_of_hits: int) -> Min:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyWarpFlamerAbility$$GetNumExtraHits`
    -- MIRROR 1:1 :

        Min( GetPersistentData(AbilityOrEffect(this+0x10 = 1227), Owner@DSLSelectors+0x30,
                               "PSYCHIC_ATTACKS_KEY"),
             Subtract( Direct(GetNumberConstant(0x48 = maxNrOfHits)),
                       Direct(GetNumberConstant(0x2f = nrOfHits)) ) )

    `DSLFormulas$$Subtract(a, b)` construit `SumAmount(a, MultiplyAmount(b, <DSLFormulas+0x38 = -1>))`
    = `a - b` (LU) : le plafond est bien `maxNrOfHits - nrOfHits`, pas l'inverse.

    LE COMPTEUR est alimente par la TRIGGERED `1546 HeavyWarpFlamer_AttackTracking`
    (`...Triggered.Loki.HeavyWarpFlamer_AttackTrackingAbility$$CreateBehaviour`, HORS PERIMETRE #523) :

        On(0x9) & <clause partagee +0x28> & !AreEqual(Attacker, Owner@+0x30)
                & AreFriends(Attacker, Owner@+0x30)
                & CurrentAttackDamageProfilesContain(DamageProfileType.Psychic = 0xd)
        | On(EventTriggerType.TurnEnd = 0x17)
        --------------------------------------------------------------------------------------------
        triggerType == TurnEnd -> ClearPersistentData(AbilityOrEffect(1227), Owner, KEY)
        sinon                  -> SetPersistentData(AbilityOrEffect(1227), Owner, KEY,
                                                    Sum(GetPersistentData(...), <DSLFormulas+0x20 = 1>))

    ⚠ L'`AbilityOrEffect` de la TRIGGERED est le LITTERAL `0x4cb` = **1227** (`mov edx,0x4cb` juste
    avant l'`op_Implicit`, LU a l'assembleur) -- PAS son propre id 1546. Les deux cotes adressent donc
    la MEME cle composite `(1227, "PSYCHIC_ATTACKS_KEY")`, et c'est ce qui rend le mecanisme coherent
    (`AbilityOrEffect$$GetPersistentDataId` rend l'ordinal du premier des trois `Nullable` renseigne).

    ETAT DU PORT : le noeud de LECTURE est monte pour de vrai (il interroge `ctx.persistent_data`,
    donc le `PersistentDataComponent` de l'ECS) ; l'ECRITURE n'existe pas tant que 1546 n'est pas
    portee -> la cle est absente, `GetPersistentDataFormula$$Calculate` rend l'`out` par defaut = 0,
    et `GetNumTotalHits` vaut `nrOfHits`. C'est la MEME degradation, nommee, que la face DECISION
    (`playbook/loki_custom.py::HeavyWarpFlamerPlaybook`). Le jour ou 1546 est portee, ce noeud lit la
    valeur sans changer d'une ligne."""
    return Min(GetPersistentData(int(ActiveAbilityType.HeavyWarpFlamer), Owner(),
                                 HEAVY_WARP_FLAMER_STACK_KEY),
               Difference(Const(int(max_nr_of_hits)), Const(int(nr_of_hits))))


def heavy_warp_flamer_num_total_hits(nr_of_hits: int, max_nr_of_hits: int) -> Sum:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyWarpFlamerAbility$$GetNumTotalHits`
    -- MIRROR 1:1 :

        Sum( Direct(GetNumberConstant(0x2f = nrOfHits)), GetNumExtraHits() )

    (`$$GetNumBaseHits` est exactement la 1re branche -- `Direct(GetNumberConstant(0x2f))` -- et
    n'est appelee par PERSONNE dans le build : elle n'a pas de foyer distinct cote port.)

    => `nrOfHits + min(<coups Psychic allies ce tour>, maxNrOfHits - nrOfHits)`, soit `[4, 9]` a la
    config courante. Ce noeud est passe TEL QUEL a `ChainLeftOverHitsAttackDamage` (`+0x98 hits`), qui
    l'evalue au moment de l'execution -- pas un scalaire fige a la construction."""
    return Sum(Const(int(nr_of_hits)), heavy_warp_flamer_num_extra_hits(nr_of_hits, max_nr_of_hits))


def heavy_warp_flamer_tree(state, range_val: int, base_min: int, base_max: int,
                           nr_of_hits: int, max_nr_of_hits: int,
                           pierce: int) -> ChainLeftOverHitsAttackDamage:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyWarpFlamerAbility$$ExecuteBehaviour`
    -- MIRROR 1:1 (UN SEUL noeud terminal, passe a `AActiveAbility$$Execute`) :

        dp    = AbilityConfiguration$$GetDamageProfile(config)         # Nullable<DamageProfileType>
        dmg   = AActiveAbility$$MinMaxDamage(this, abilityState)
        other = <GetOtherTargets, recopie inline>
        chain = DSLSelectors$$SortTargetsByDamagePredictionSelector(
                    attacker              = Owner@+0x30,
                    units                 = other,
                    ability               = DSLSelectors$$Direct(AbilityOrEffect(this+0x10)),
                    damage                = dmg,
                    hits                  = <DSLFormulas+0x20>,
                    damageProfileType     = DSLSelectors$$Direct(Nullable(dp)),
                    attackerSelectionType = 3)
        DSLBehaviors$$ChainLeftOverHitsAttackDamage(
                    caster                     = Owner@+0x30,
                    firstTarget                = Target@+0x60,
                    dmgAmount                  = dmg,
                    damageProfileType          = Direct(Nullable(dp)),
                    hits                       = GetNumTotalHits(this),
                    abilityType                = this+0x10,
                    otherTargetSelector        = chain,
                    extraHitsAfterTargetKilled = **null**)

    QUATRE ecarts LUS avec `1048 FragstormGrenadeLauncher`, qui monte la MEME feuille
    (`blacktemplars.py`) -- aucun n'est copie de la voisine :
      * l'ensemble de report est `AdjacentFriends(TARGET) & SurroundingEnemies(CASTER, range)` (1048 :
        `SurroundingEnemies(Owner, range) - Target`) -> la chaine reste COLLEE a la cible ;
      * il n'y a AUCUN `SortByFormula` par PV en amont du selecteur de prediction (1048 en a un, qui y
        est de surcroit un no-op) -> l'ordre SOURCE est la geometrie brute, puis le tri par kill ;
      * le `hits` du selecteur de PREDICTION est `<DSLFormulas+0x20>` = **1** (1048 : `nrOfHits`) --
        le champ est pose par `DSLFormulas$$.ctor`, qui alloue cinq constantes `0 / 1 / 2 / 100 / -1`
        aux slots `+0x18 / +0x20 / +0x28 / +0x30 / +0x38`. Corroboration independante : le meme
        `+0x20` sert d'increment (`Sum(GetPersistentData(...), +0x20)`) dans la triggered 1546, ou il
        ne peut valoir que 1 ;
      * le `hits` de la FEUILLE est le noeud DYNAMIQUE `GetNumTotalHits` (1048 : `Direct(nrOfHits)`).
    Communs : `extraHitsAfterTargetKilled` **null** (donc `extra = 0` dans `GetLeftOverHits`) et
    l'execution par `AActiveAbility$$Execute`.

    `attackRangeType = Ranged` (gameconfig 1227) -> `is_melee=False`. Famille de factory = **ATTACK**
    (le nom natif est `...AttackDamage` et la feuille construit le mold `AttackDamageBehaviour`) ->
    `native_factory="attack"`, le defaut de la feuille.

    ⚠ Sans `extraHits`, un maillon ne peut REPORTER que si la cible meurt AVANT le dernier coup :
    `GetLeftOverHits` rend `max(0, H - k - 1) + 0`."""
    other = heavy_warp_flamer_other_targets(range_val)
    chain = SortTargetsByDamagePrediction(
        state=state, attacker=Owner(), targets=other,
        ability_type=int(ActiveAbilityType.HeavyWarpFlamer),
        damage_min=base_min, damage_max=base_max,
        hits=HEAVY_WARP_FLAMER_PREDICTION_HITS,
        damage_profile=HEAVY_WARP_FLAMER_PROFILE, pierce=pierce, is_melee=False)
    return ChainLeftOverHitsAttackDamage(
        Owner(), Target(), chain, HEAVY_WARP_FLAMER_ID, HEAVY_WARP_FLAMER_PROFILE,
        heavy_warp_flamer_num_total_hits(nr_of_hits, max_nr_of_hits), 0, is_melee=False)


class HeavyWarpFlamerAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyWarpFlamerAbility$$ExecuteBehaviour`
    (id **1227**, `thousSekhetar` « Sekhetar Robot », Thousand Sons/Chaos).

    Kit gameconfig 1227 : `attackRangeType = Ranged`, `damageProfile = Flame`
    (`PiercingRatio` 25, trait `OnFire`), `nrOfHits` 4, `maxNrOfHits` 9, `range` 2.

    OBSERVABLE : la cible designee encaisse `GetNumTotalHits` coups Flame ; les coups qui tombent sur
    le CADAVRE sont REPORTES sur l'ennemi suivant -- parmi les ennemis du caster ADJACENTS a la cible
    ET a distance <= 2 du caster, tries par priorite de kill (prediction de degat). Le report lui-meme
    vit dans la feuille partagee `ChainLeftOverHitsAttackDamage` (`behaviours/combat.py`, mirror de
    `IdunBattle.Entities.Behaviours.ChainLeftOverHitsAttackDamageBehaviour$$Execute` et de son
    `GetLeftOverHits`, garde de 100 iterations) ; ici, seulement la CONSTRUCTION de l'arbre.

    GATE DE CONFRONTABILITE : porteur lineup UNIQUE, ABSENT du seed BC partage (unite ajoutee par le
    build `rnca9r7q6c`) -> il arrive en bataille par `catalog_inject.write_augmented_seed_bc` +
    `rl_duel build --seed-bc` (#92 §6), la MEME voie qui a servi a la face DECISION (#27).
    « Absent du pool » n'est pas « non confrontable » : aucun `data/unspawnable_rank*.json` n'existe.

    Face DECISION deja portee (#27, `playbook/loki_custom.py::HeavyWarpFlamerPlaybook` --
    `W(HeavyWarpFlamer_LikesAdjacentEnemies) x |ennemis adjacents a la tuile de la CIBLE|`). Ce
    port-ci est la face EXECUTION, qui etait un NO-OP SILENCIEUX (absente d'`ABILITY_CLASSES` ->
    `visit_ActiveAbilityMessage` rendait `ported: False` : 0 degat, 0 effet, aucune erreur).

    Flags de tour : defauts base (1227 absente des overrides) -> termine le tour + ActiveAbilityUsed.
    Retour : `{ability, caster, target, range, hits, chain, dsl}`."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HeavyWarpFlamer)        # 1227
    ABILITY_ID = HEAVY_WARP_FLAMER_ID

    # GATE DE CIBLE (#523) -- forme de ctor = **PRESET STATIQUE COPIE** (aucun appel a
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor`, donc AUCUN flag ajoute) :
    #     opts <- <TargetingOptions statics>+0x140 .. +0x17f      (copie des 0x40 octets)
    #     AActiveAbility..ctor(this, &opts, 0)                    # 3e arg = AbilityAttackType = 0
    # Le preset `+0x140` est LU dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    #     <preset>+0x00 = *(statics+0x140) = 0        -> isSelfCasting = false
    #     <preset>+0x08 = copie de `TargetingRange statics+0x18` -> **RANGE_FROM_CONFIG**
    #     <preset>+0x20 = *(statics+0x160) = 0        -> forceMeleeTarget = RangedBool.True
    #                                                    (l'enum natif est INVERSE : True=0, False=1)
    #     <preset>+0x28 = *(statics+0x168) = 0x4002   -> Rules
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`), exhaustive :
    #     0x0002  TargetMatchesDynamicRule  -> `GetDynamicInvalidTargetReason` NON surchargee par
    #                                          1227 -> defaut 0 (degradation PERMISSIVE assumee, et
    #                                          c'est pourquoi 1227 n'entre pas dans
    #                                          `DYNAMIC_TARGET_RULE_UNPORTED`)
    #     0x4000  TargetIsEnemy             -> PORTE
    # ⚠ Le preset voisin `+0x180` (Fragstorm 1048) ne differe QUE par `forceMeleeTarget`
    # (`RangedBool.False`, valeur 1) : recopier le masque de la voisine aurait donne le bon `Rules` et
    # le mauvais regime de PORTEE (`TargetingQuery$$GetRange` rabat a 1 au contact quand
    # `ForceMeleeTarget` est vrai). 1227, LUI, est rabattu au contact -- lire ability par ability.
    # 1227 n'etait dans AUCUNE des listes du contrat de disjonction (`TARGETING_OPTIONS_UNPORTED`,
    # `DYNAMIC_TARGET_RULE_UNPORTED`) -- verifie PAR LE CODE au moment du port, coherent avec un
    # porteur hors du pool spawnable : aucune migration, aucun compteur a decrementer.
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy), self_cast=False,
        range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_TRUE)

    # `AbilityAttackType` = 3e argument d'`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` = `0`
    # (`DirectTargetAttack`), LU au ctor -> transcrit dans la table `ABILITY_ATTACK_TYPE`
    # (`abilities/attack_type.py`), qui est le registre de cette donnee (pas un attribut de classe).

    def _params(self, state: "State", caster_id: int) -> tuple:
        """`(range, base_min, base_max, nrOfHits, maxNrOfHits, pierce)`.

        `range` = `GetNumberConstant(0x16)`, `maxNrOfHits` = `GetNumberConstant(0x48)` ; les bornes,
        `nrOfHits` (`0x2f`) et le percage du profil viennent du foyer partage `ability_attack_params`
        (mirror `AActiveAbility$$MinMaxDamage` / `GetHits` / `GetDamageProfile`)."""
        rng_range = ability_var(self.ABILITY_ID, "range", is_constant=True) or 1
        max_hits = ability_var(self.ABILITY_ID, "maxNrOfHits", is_constant=True) or 0
        base_min, base_max, pierce, hits = ability_attack_params(
            state, caster_id, self.ABILITY_ID, HEAVY_WARP_FLAMER_PROFILE, ranged=True)
        return int(rng_range), int(base_min), int(base_max), int(hits), int(max_hits), int(pierce)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        entities = entities_from_state(state, caster_id, target_id)
        rng_range, base_min, base_max, hits, max_hits, pierce = self._params(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        heavy_warp_flamer_tree(state, rng_range, base_min, base_max, hits, max_hits,
                               pierce).execute(entities, ectx)
        chain = next((p["chain"] for n, p in ectx.emitted if n == "ChainLeftOverHits"), [])
        return {"ability": HEAVY_WARP_FLAMER_ID, "caster": caster_id, "target": target_id,
                "range": rng_range, "hits": (chain[0]["hits"] if chain else None),
                "chain": chain, "dsl": True}


# Les trois constantes de config LUES au decompile de 1227, nommees (regle « un entier qui DESIGNE
# passe par un ENUM ») : `GetNumberConstant(0x16)`, `(0x2f)` et `(0x48)`.
assert (int(AbilityConstantType.range) == 0x16 and int(AbilityConstantType.nrOfHits) == 0x2F
        and int(AbilityConstantType.maxNrOfHits) == 0x48)
