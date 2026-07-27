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
from ...entities.selectors import (AllTiles, Caster, CasterTile, Damageable, EntitiesWithAnyEffect,
                                   SurroundingEnemies, Unobscured, UnitSet)
from ...entities.formulas import Count, Min, Sum
from ...entities.effect_type import EffectType
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects.magnitude import ability_var
from ..components import StatsComponent
from ..operations.damage_utility import sort_units_by_damage_utility
from .base import ActiveAbility
from .behaviours import entities_from_state, AttackWithAttackDamage
from .targeting import RANGE_FROM_CONFIG, RANGED_BOOL_FALSE, TargetingOptions
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
      `runner/operations/damage_utility.py`) : utilite `UtilityDefinition(0x22 = Damage)` DECROISSANTE.
      Le noeud de degat branche par ce call-site est `Direct(GetVariableForLevel(0xc = minDmg, level))`
      et le slot `dmgMax` (+0x48) recoit **null** (8e argument du factory = 0) -> `dmax == dmin`.
    - Le REORDONNANCEMENT natif est INCONDITIONNEL des que caster et cible existent et different :
      `Remove` est un no-op si la cible n'etait pas dans la liste, mais `Insert(0, ...)` l'ajoute
      QUAND MEME -> la cible du message est TOUJOURS en tete (et compte dans `C`). On mirror tel quel.

    `candidates` = ids d'unite rendus par `doombolt_targets_selector`."""
    ordered = list(sort_units_by_damage_utility(state, candidates, dmg_min, dmg_min))
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
