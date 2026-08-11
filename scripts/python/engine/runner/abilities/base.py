"""Base des abilities actives portées + helpers DSL communs.

`ActiveAbility` = base d'une ability native `AActiveAbility` ; chaque sous-classe porte UNE ability
(VA citée) et implémente `execute_behaviour` (mirror de `<Ability>.ExecuteBehaviour`).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

# Les deux registres d'override de flags sont indexes par `ActiveAbilityType` (#270-r1-r1).
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effects import piercing_bonus_from_effects
from ...entities.effects.magnitude import ability_var
from ..components import OwnerComponent
from ..components import OwnerComponent, PositionComponent, UnitComponent
from ..components import StatsComponent
from ..components import StatsComponent, UnitComponent, unit_state_for_effects

if TYPE_CHECKING:
    from ..state import State


def ability_attack_params(state: "State", caster_id: int, ability_id: str,
                          profile_name: str, ranged: bool = False,
                          min_key: str = "minDmg", max_key: str = "maxDmg",
                          hits_key: str = "nrOfHits", hits_add_key: str | None = None,
                          level_slot: str = "active", pierce_effect_bonus: int = 0):
    """Paramètres de l'attaque d'une ability (mirror `MinMaxDamage`/`GetHits`/`GetDamageProfile`) depuis
    l'ECS + gameconfig : `(base_min, base_max, pierce, hits)`.
      • base_min/base_max = `GetVariableForLevel(config, 0xc/0xd, level)` = `minDmg`/`maxDmg`[<level_slot>]
        scalés par `AbilityVariablesMultiplier` (vars flaggées rareté) — via `ability_var`.
      • hits = `GetNumberConstant(config, 0x2f)` = `nrOfHits` (constante).
      • pierce = clamp(0,100, profil.PiercingRatio + ExtraPierce + ExtraPierce{Melee|Ranged}) — même
        modèle que l'attaque normale (`select_weapon_pierce`), avec le PROFIL de l'ability.

    `min_key`/`max_key`/`hits_key` = noms des variables/constantes config à lire (défaut minDmg/maxDmg/
    nrOfHits). Une ability à DEUX volets de dégât (ex. CrushingClaws : attaque principale + splash) passe
    le 2ᵉ jeu de clés (`minDmg_2`/`maxDmg_2`/`nrOfHits_2`) + son profil pour le volet secondaire.

    `hits_add_key` = 2ᵉ constante de coups AJOUTÉE à `hits` (mirror d'une bande dont le nb de coups est la
    SOMME de deux `GetNumberConstant` — GauntletsOfUltramar bande adjacente = `GetNumberConstant(0x2f)` +
    `GetNumberConstant(0x32)`, `IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$ExecuteBehaviour`). Défaut None = un seul `hits_key`. Constante
    absente → +0 (le natif `GetNumberConstant` d'un index manquant rend 0, pas 1).

    `level_slot` = SOURCE du niveau qui indexe `minDmg`/`maxDmg` : `"active"` (défaut, ability ACTIVE =
    `ctx.active_ability_level`) ou `"passive"` (ability PASSIVE/TRIGGERED = `ctx.passive_ability_level` —
    l'`AbilityConfiguration` d'un passif est résolue au niveau de la PASSIVE, cf. `scene.py`/`extra_damage`
    côté DÉCISION). Un `MartialApotheosis` (passif necroOverlord) attaque au `passive_ability_level` ; dans
    un runner rank-based `active == passive` (vérifié live necroOverlord 50/50) → observationnellement égal,
    mais on lit la BONNE source pour rester fidèle au natif hors de cette coïncidence."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    if ctx is None:
        level = 0
    elif level_slot == "passive":
        level = ctx.passive_ability_level if ctx.passive_ability_level is not None else ctx.active_ability_level
    else:
        level = ctx.active_ability_level
    mult = ctx.ability_variables_multiplier if ctx is not None else 100
    bmin = ability_var(ability_id, min_key, level, multiplier_pct=mult) or 0
    bmax = ability_var(ability_id, max_key, level, multiplier_pct=mult) or 0
    hits = ability_var(ability_id, hits_key, is_constant=True) or 1
    if hits_add_key is not None:                       # bande somme-de-2-constantes (Gauntlets adjacente)
        hits += ability_var(ability_id, hits_add_key, is_constant=True) or 0
    pierce = profile_pierce(ctx, profile_name, ranged, effect_bonus=pierce_effect_bonus)
    return int(bmin), int(bmax), pierce, int(hits)


def active_ability_state(state: "State", caster_id: int, ability_type: int) -> tuple:
    """`(level, mult)` de l'`AbilityState` de CETTE ability ACTIVE sur CE caster (#889).

    Le natif resout chaque `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel`
    contre l'`abilityState` que `AActiveAbility` lui passe -- celui de l'ability CASTEE, pas un
    niveau global d'unite. Deux actives d'une meme unite peuvent differer : `ultraCalgar` porte
    `1000` au niveau 50 et son attaque normale `69` au niveau 1 (mesure au canal
    `unitAbilityStates`).

    Repli EXPLICITE et documente : si le canal n'a pas ete mesure (`ctx.active_ability_levels is
    None`) ou ne porte pas CETTE ability, on rend le scalaire `(ctx.active_ability_level,
    ctx.ability_variables_multiplier)` -- exactement ce que lisait le port avant. Sans `ctx` du tout,
    `(0, 100)`, qui indexe le niveau 1 : c'est le comportement historique, pas une valeur inventee."""
    e = state.get_entity(caster_id) if state is not None else None
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    if ctx is None:
        return 0, 100
    table = getattr(ctx, "active_ability_levels", None)
    if isinstance(table, dict):
        entry = table.get(int(ability_type))
        if entry:
            return int(entry[0]), int(entry[1])
    return int(ctx.active_ability_level or 0), int(ctx.ability_variables_multiplier or 100)


def profile_pierce(ctx, profile_name: str, ranged: bool = False, effect_bonus: int = 0) -> int:
    """Perçage effectif d'une attaque = `clamp(0, 100, profil.PiercingRatio + ExtraPierce +
    ExtraPierce{Melee|Ranged} + Σ bonus d'effets)` (volet perçage commun de `MinMaxDamage`/
    `AttackWithAttackDamage` : PiercingRatio du profil de dégât + les stats de perçage du caster). Extrait
    de `ability_attack_params` pour être PARTAGÉ par les deux feuilles à dégât-node `StatAmount`/
    `PercentageOf` (sans bornes d'arme, elles routent leur base par ce perçage) : le mode `amount` de
    `AttackWithAttackDamage` (Psyker, crit/block) ET la feuille directe `AttackWithAbilityDamage` (DoT feu,
    sans crit/block — appelée avec `ctx=None`). `ctx` = `UnitContext` du caster (None → perçage =
    PiercingRatio seul, cas de la tuile en feu qui n'a pas de stats ExtraPierce).

    `effect_bonus` = Σ des `EffectBonus` de perçage des effets ACTIFS de l'attaquant
    (`piercing_bonus_from_effects` → `BaseEffect$$PiercingBonusForAttack`) : c'est le terme `Fix64` que
    `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio` additionne DANS la même somme,
    AVANT le `Min(100, …)` — porteur du lot : `GravitonRifle_ExtraPierce` (+extraPierceRatio vs
    TerminatorArmour/MkXGravis/Mechanical). Défaut 0 = comportement historique inchangé."""
    import gameconfig as GC
    dp = GC.damage_profile(profile_name) or {}
    extra = ctx.extra_pierce if ctx is not None else 0
    dir_pierce = ((ctx.extra_pierce_ranged if ranged else ctx.extra_pierce_melee)
                  if ctx is not None else 0)
    return max(0, min(100, int(dp.get("PiercingRatio") or 0) + extra + dir_pierce + int(effect_bonus)))


def ability_pierce_effect_bonus(state: "State", caster_id: int, target_id, ability_type,
                                is_ranged: "bool | None" = None,
                                is_overwatch: bool = False) -> int:
    """Σ des bonus de perçage apportés par les effets ACTIFS du CASTER pour un coup donné — assemble le
    `ctx` des gates natifs (`get_OwnerIsCaster` / `CurrentAbilityIs` / `HasTrait(target, …)` /
    `IsRangedAttack | IsOverwatchAttack`) puis délègue à `piercing_bonus_from_effects` (mirror
    `BaseEffect$$PiercingBonusForAttack`). 0 si l'état n'a pas d'`EffectsState`, si le caster n'a pas de
    stats, ou si aucun effet actif ne contribue.

    `ability_type` = `None` est ADMIS depuis case-117 (l'attaque NORMALE n'a pas d'AbilityOrEffect
    d'ability à threader) : seuls les effets gatés `CurrentAbilityIs` (GravitonRifle) se taisent alors —
    ceux qui n'ont PAS ce gate (Hailstrike_ExtraPierce) contribuent. `is_ranged`/`is_overwatch` =
    nature du coup (tri-état #106 : None ⇒ les gates ranged/melee se taisent).

    `unit_ctx_of` (déposé dans le ctx) = mirror de `BaseEffect$$GetAbilityState` pour les effets dont la
    SOURCE n'est pas le porteur : la magnitude `ConfigVar` s'indexe sur l'état d'ability de CELUI QUI A
    POSÉ l'effet (la Storm Speeder pour Hailstrike), pas sur celui de l'attaquant qui le porte."""
    if state is None or caster_id is None:
        return 0
    ce = state.get_entity(caster_id)
    csc = ce.get_component(StatsComponent) if ce is not None else None
    if csc is None:
        return 0
    effects = None
    if state.effects is not None:
        effects = state.effects.active_effects(
            caster_id, unit_state_for_effects(state, caster_id))
    if not effects:
        effects = getattr(csc.ctx, "active_effects", None)
    if not effects:
        return 0
    traits = None
    if target_id is not None:
        import gameconfig as GC
        te = state.get_entity(target_id)
        tuc = te.get_component(UnitComponent) if te is not None else None
        if tuc is not None:
            traits = frozenset((GC.unit(tuc.visual_id) or {}).get("traits") or ())
    def _unit_ctx_of(uid):
        """`BaseEffect$$GetAbilityState` — `UnitContext` de l'unité `uid` (la SOURCE d'un effet), ou None."""
        if uid is None:
            return None
        e = state.get_entity(int(uid))
        sc = e.get_component(StatsComponent) if e is not None else None
        return getattr(sc, "ctx", None) if sc is not None else None

    return piercing_bonus_from_effects(
        effects, {"owner_id": int(caster_id), "att_id": int(caster_id),
                  "ability_type": (int(ability_type) if ability_type is not None else None),
                  "target_traits": traits,
                  "owner_ctx": csc.ctx, "is_ranged": is_ranged,
                  "is_overwatch": bool(is_overwatch), "unit_ctx_of": _unit_ctx_of})


def turns_from_rounds(rounds: int) -> int:
    """LEGACY -- IDENTITE, **PAS** le mirror de `TurnsFromRounds`. NE PAS l'utiliser pour une duree
    d'effet : le vrai mirror est `convert_rounds_to_turns(state, rounds)` ci-dessous.

    Conservee comme helper d'unite neutre (call-sites qui manipulent deja des TOURS). L'ancienne
    justification (« count(non-Env) = 1 dans nos runners, PROUVE par test_effect_stun_live ») est
    **REFUTEE** (#98) : le `live_remaining = 1` de ce test etait un ARTEFACT DE MESURE (lecture
    POST-tick -- en 1v1 strict le cast est l'action de la SEULE unite du camp, le moteur cloture le
    tour et `RefreshEffects` decremente AVANT la relecture de `decisionView`). Mesure PRE-tick
    (2 unites/camp, cast avec une unite encore activable derriere) : `Stunned` = 2, `Pinned` = 2 --
    soit `count = 2`."""
    return int(rounds)


def convert_rounds_to_turns(state: "State", rounds: int) -> int:
    """`IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (mirror EXACT) = `count(joueurs du turnOrder dont
    PlayerType != 2) * rounds`.

    DECOMPILE : `this+0xa0` = la `BattleConfiguration` (`IdunRunner..IdunBattle.Runner.IdunRunner$$.ctor` :
    `BattleQuery..ctor(state = match.state, bc)`) ; `bc+0x30 -> +0x18` = la liste iteree
    (`BC.Player.TurnOrder`, ids de joueurs) ; pour chaque id : `StateExtensions.GetPlayer(state, id)`
    puis `PlayerComponent+0x20` -- l'entree est comptee SAUF si cette valeur vaut 2 (Environment).
    Retour = `compteur * rounds`.

    DEUX voies natives passent par ici, TOUTES DEUX converties :
      * le noeud DSL `TurnsFromRounds(n)` (`IdunBattle.Entities.Formulas.TurnsFromRoundsFormula$$Calculate` = slot 0x1b
        de `BattleQuery` sur la valeur du noeud) ;
      * la duree PAR DEFAUT dans `IdunBattle.Operations.AddEffectOperation$$Execute` (branche « pas d'override » :
        `ConvertRoundsToTurns(DefaultAmountOfRounds(type).Value)`).
    Une duree passee en `Nullable<int>`/`Direct(n)` par l'appelant est en TOURS et n'est **PAS**
    convertie (le natif la prend telle quelle dans `param_6`).

    Le facteur vient de `state.turn_order_player_count` (seede par `load_state` depuis
    `observeBattle.counts.player - 1`, cf. sa docstring). None/0 -> IDENTITE (etats construits sans
    ce canal : aucun changement de comportement)."""
    n = state.turn_order_player_count
    return int(rounds) * (int(n) if n else 1)


def turns_until_end_of_current_players_next_turn(state: "State") -> int:
    """`IdunBattleLogic.Entities.DSLFormulas$$TurnsUntilEndOfCurrentPlayersNextTurn` (mirror STRUCTUREL) =
    `Sum( TurnsFromRounds(1), Direct(1) )` -- le decompile alloue un `TurnsFromRoundsFormula(ctx, query, 1)`
    ET un noeud constant `1`, puis les combine. SEUL le terme `TurnsFromRounds` passe par
    `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (#98) ; le `Direct(1)` est deja en TOURS.

    => duree = `convert_rounds_to_turns(state, 1) + 1` = « jusqu'a la FIN du prochain tour du joueur
    courant » (un tour de plus que `TurnsFromRounds(1)`, qui expire a son DEBUT).

    GROUND TRUTH LIVE (anvil_shield, Stunned pose par `AnvilShieldAbility_ApplyStun`) : `remaining 3` avec
    `ConvertRoundsToTurns(1) = 2`. Consommateurs : le `Stunned` d'AnvilShield (branche `IsTurnOf`) et les
    TROIS effets de `IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$ExecuteBehaviour`
    (1157/1158 sur les ennemis adjacents + 1122 Markerlight)."""
    return convert_rounds_to_turns(state, 1) + 1


def turns_until_unit_owner_turn(state: "State", unit_id: int) -> int:
    """`IdunBattleLogic.Entities.DSLFormulas$$TurnsUntilUnitOwnerTurn(unit)` ->
    `IdunBattle.Entities.Formulas.TurnsUntilUnitOwnerTurnFormula$$GetTurnsUntilUnitOwnerTurn` (MIRROR
    du decompile) :

        cur = StateExtensions.GetCurrentPlayer(state)
        if (cur == null) return 0
        if (GetOriginalPlayerId(cur) == GetOriginalPlayerId(unit)) return 0     # c'est deja son tour
        order = query.<slot 0x17>()                       # la liste TurnOrder d'ids de joueurs
        i0 = order.IndexOf(GetOriginalPlayerId(cur))
        count = 0
        for k in 0 .. order.Count-1 :
            p = GetPlayer(state, order[(k + i0) % order.Count])
            if (GetOriginalPlayerId(p) == GetOriginalPlayerId(unit)) return count
            if (p.PlayerComponent@+0x20 != 2)             # != Environment
                if (!query.<slot 0x19>(p)) count++        # joueur non-elimine
        return count

    => « nombre de tours de joueur (hors Environment) restant a jouer AVANT que le tour du proprietaire
    de `unit` ne commence ». C'est la duree que `AReactivateOverwatchEffect$$GetAddHitReductionBehaviour`
    donne au stat-mod EXTRA_HITS : la reduction de coups ne vit QUE le reste du tour adverse en cours.

    COLLAPSE ASSUME (doctrine slice-18/19 -- la formule V n'a pas de noeud porte) : le port ne detient
    pas la LISTE `TurnOrder` (`state` n'expose que `current_player_id` et `turn_order_player_count`,
    seede depuis `observeBattle.counts.player - 1`). Sur un runner de duel -- le SEUL vecteur du port,
    `turn_order_player_count == 2` -- la boucle native ne peut compter que le joueur COURANT avant de
    tomber sur le proprietaire : le resultat est **1**. RESIDU NOMME : avec plus de 2 joueurs
    non-Environment le rang exact du proprietaire dans l'ordre n'est pas derivable offline et cette
    fonction rend 1 (borne INFERIEURE, jamais une duree inventee plus longue)."""
    cur = state.current_player_id
    if cur is None:
        return 0                                       # `GetCurrentPlayer(state) == null`
    e = state.get_entity(int(unit_id))
    oc = e.get_component(OwnerComponent) if e is not None else None
    owner_player = oc.player if oc is not None else None
    if owner_player is not None and int(owner_player) == int(cur):
        return 0                                       # c'est deja le tour du proprietaire
    return 1


# ---------------------------------------------------------------------------
# « Does not end turn » (#139) — mirror des virtuals `SetsEndTurnFlags` / `SetsActiveAbilityUsedFlag`.
#
# NATIF : chaque ability active expose deux virtuals retournant un `IdunBattle.DSL.IAbilityTrigger` :
#   • `IdunBattle.Entities.Abilities.AActiveAbility$$SetsEndTurnFlags          = `_dslFactory(+0x30).True(+0xf8)` (défaut)
#   • `AActiveAbility.SetsActiveAbilityUsedFlag`            = `_dslFactory.True` (même body, foldé IL2CPP)
# Après exécution, `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal calcule :
#   skipEndTurn     = options.skipEndTurnFlag  || !ability.SetsEndTurnFlags().Evaluate(entities)
#                     (`IdunBattle.Operations.ActiveAbilityOperation$$GetSkipEndTurnFlag, slot iface 0x17)
#   skipAbilityUsed = options.skipAbilityUsedFlag || !ability.SetsActiveAbilityUsedFlag(caster).Evaluate(...)
#                     (`IdunBattle.Operations.ActiveAbilityOperation$$GetSkipAbilityUsedFlag, slot iface 0x18)
# puis `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution(caster, skipAbilityUsed, skipEndTurn) :
#   !skipAbilityUsed -> UnitFlags.Add(ActiveAbilityUsed=2)
#   !skipEndTurn     -> Core.Services.OperationProcessor$$FinishUnitTurn -> FinishUnitTurnOperation IdunBattle.Operations.FinishUnitTurnOperation$$Execute
#                       (UnitFlags.Add(ArrivedAtFinalTile=1) + Add(TurnFinished=3)).
#
# INVENTAIRE des overrides (dump symbols.json build gqfc5mff6c ; ids = ActiveAbilityType) — les corps
# constants sont FOLDÉS par IL2CPP (dédup) : fold-winners lus = `ArcScourgeAbility.SetsEndTurnFlags`
# IdunBattleLogic.Entities.Abilities.Active.ArcScourgeAbility$$SetsEndTurnFlags (`return _dsl.No(+0x118)`) et `.IdunBattleLogic.Entities.Abilities.Active.ArcScourgeAbility$$SetsActiveAbilityUsedFlag (`return _dsl.False
# (+0x100)`, 27 refs vtable). Sémantique croisée avec les tooltips i2 (« does not end X's turn »).
#
# Ability -> unité (i2) : 1014 ArmoriumCherub=Vindicta · 1063 FireAndReposition=Calandis · 1077
# EarlyWarningOverride=Re'vas · 1081 FightingRetreat=Darkstrider · 1106 WarHowl=Ragnar · 1118
# DoctrinaImperatives=Tan Gi'da · 1121 ItItches=Parasite of Mortrex · 1127 ArmouredMight_Move ·
# 1131 JakhalStimms=Macer · 1139 SentinelDirectives=Sy-Gex · 1173 ArcScourge=Belisarius Cawl ·
# 1189 CalibaniteGreatsword=Forcas · 1198 EuphoricStrikes=Laviscus · 1202 VigilanceEternal=Tyrith ·
# 1210 ExemplarOfTheMontka=Farsight.

# Classes overridant `SetsEndTurnFlags` (l'ability NE termine PAS le tour) — 14 classes.
# #270-r1-r1 : membres nommes plutot qu'ordinaux nus. Le discriminant est le NOM que la prose
# ci-dessus donne deja a chaque id (`1014 ArmoriumCherub=Vindicta` ...) : confronte a
# `frida/enums.tsv`, il matche 14/14 `ActiveAbilityType` (les memes ordinaux nomment autre chose
# en `TriggeredAbilityType` -- 1014 = `RitesOfBattle` -- et en `EffectType`).
NO_END_TURN_ABILITY_TYPES = frozenset({
    ActiveAbilityType.ArmoriumCherub,        # 1014
    ActiveAbilityType.FireAndReposition,     # 1063
    ActiveAbilityType.FightingRetreat,       # 1081
    ActiveAbilityType.WarHowl,               # 1106
    ActiveAbilityType.DoctrinaImperatives,   # 1118
    ActiveAbilityType.ItItches,              # 1121
    ActiveAbilityType.ArmouredMight_Move,    # 1127
    ActiveAbilityType.JakhalStimms,          # 1131
    ActiveAbilityType.SentinelDirectives,    # 1139
    ActiveAbilityType.ArcScourge,            # 1173
    ActiveAbilityType.CalibaniteGreatsword,  # 1189
    ActiveAbilityType.EuphoricStrikes,       # 1198
    ActiveAbilityType.VigilanceEternal,      # 1202
    ActiveAbilityType.ExemplarOfTheMontka,   # 1210
})

# Classes overridant `SetsActiveAbilityUsedFlag` (pas de flag ActiveAbilityUsed=2) — 13 classes
# (PAS 1063 FireAndReposition ni 1121 ItItches ; + 1077 EarlyWarningOverride qui n'override QUE celui-ci).
NO_ABILITY_USED_FLAG_ABILITY_TYPES = frozenset({
    ActiveAbilityType.ArmoriumCherub,         # 1014
    ActiveAbilityType.EarlyWarningOverride,   # 1077
    ActiveAbilityType.FightingRetreat,        # 1081
    ActiveAbilityType.WarHowl,                # 1106
    ActiveAbilityType.DoctrinaImperatives,    # 1118
    ActiveAbilityType.ArmouredMight_Move,     # 1127
    ActiveAbilityType.JakhalStimms,           # 1131
    ActiveAbilityType.SentinelDirectives,     # 1139
    ActiveAbilityType.ArcScourge,             # 1173
    ActiveAbilityType.CalibaniteGreatsword,   # 1189
    ActiveAbilityType.EuphoricStrikes,        # 1198
    ActiveAbilityType.VigilanceEternal,       # 1202
    ActiveAbilityType.ExemplarOfTheMontka,    # 1210
})

# Ability 1081 FightingRetreat (Darkstrider) = SEUL override CONDITIONNEL lu dans le build courant :
# `IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$SetsActiveAbilityUsedFlag = `_dsl.Direct(!Any(battleQuery slot 0x7c
# (caster, currentPlayerEntityId)))` — pose les flags UNIQUEMENT si AUCUN ennemi adjacent (i2 : « does not
# end Darkstrider's turn IF he is adjacent to an enemy »). Son SetsEndTurnFlags (corps foldé, non isolable
# offline) est aligné sur la même condition par le texte i2 — ASSOMPTION DOCUMENTÉE, même prédicat.
FIGHTING_RETREAT = ActiveAbilityType.FightingRetreat


def _fighting_retreat_sets_flags(state: "State", caster_id: int) -> bool:
    """Mirror IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$SetsActiveAbilityUsedFlag : True (pose les flags = tour fini) ssi PAS d'ennemi VIVANT adjacent (dist hex 1)
    au caster. Ennemi = `team` differente (meme convention que les autres ports, ex. `_nearest_enemy`)."""
    import hexgeo
    e = state.get_entity(caster_id)
    if e is None:
        return True
    oc = e.get_component(OwnerComponent)
    pc = e.get_component(PositionComponent)
    if oc is None or pc is None:
        return True
    src = (pc.col, pc.row)
    for oid, other in state.entities.items():
        if oid == caster_id:
            continue
        ouc = other.get_component(UnitComponent)
        ooc = other.get_component(OwnerComponent)
        opc = other.get_component(PositionComponent)
        if ooc is None or opc is None or ooc.team == oc.team:
            continue
        if ouc is not None and not ouc.alive:
            continue
        if hexgeo.distance(src, (opc.col, opc.row)) == 1:
            return False
    return True


def sets_end_turn_flags_for(ability_type: int, state: "State", caster_id: int) -> bool:
    """Verdict `ability.SetsEndTurnFlags().Evaluate(entities)` pour UN ActiveAbilityType (défaut base
    IdunBattle.Entities.Abilities.AActiveAbility$$SetsEndTurnFlags = True ; overrides = inventaire RE ci-dessus). Utilisé par le handler pour TOUTE ability
    exécutée, portée ou non (le natif pose les flags indépendamment du contenu de la behaviour)."""
    at = int(ability_type)
    if at == FIGHTING_RETREAT:
        return _fighting_retreat_sets_flags(state, caster_id)
    return at not in NO_END_TURN_ABILITY_TYPES


def sets_active_ability_used_flag_for(ability_type: int, state: "State", caster_id: int) -> bool:
    """Verdict `ability.SetsActiveAbilityUsedFlag(caster).Evaluate(entities)` (défaut True ; overrides =
    inventaire RE)."""
    at = int(ability_type)
    if at == FIGHTING_RETREAT:
        return _fighting_retreat_sets_flags(state, caster_id)
    return at not in NO_ABILITY_USED_FLAG_ABILITY_TYPES


class ActiveAbility:
    """Base d'une ability active (`AActiveAbility`). `ABILITY_TYPE` = ActiveAbilityType (enum int).
    `execute_behaviour` mute `state` via les operations portées, en miroir 1:1 du DSL natif."""
    __slots__ = ()
    ABILITY_TYPE: int = -1

    # --- GATE DE CIBLE (#115) : les deux membres du contrat natif de validation de cible. ---------
    #
    # `TARGETING_OPTIONS` = les `IdunBattle.Core.Services.TargetingOptions` que le
    # `<X>Ability$$.ctor` passe a `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` (masque de
    # flags `TargetingRule` a `options+0x28`). C'est la SEULE donnee qui arme le filtre statique
    # generique (`abilities/targeting.py`). `None` = masque non RE-lu -> AUCUN gate pour cette
    # ability (on ne devine pas un refus). A ne renseigner qu'apres lecture du ctor decompile — et
    # jamais depuis l'overload « preset + flags », dont le litteral n'est pas le masque effectif
    # (cf. la docstring de `TargetingOptions`).
    TARGETING_OPTIONS = None

    # --- MASQUE DE *CONTINUE* (#429-r1) -----------------------------------------------------------
    #
    # `AActiveAbility` porte DEUX masques, pas un : `_targetingOptions` (+0x70, celui ci-dessus) et
    # `_targetingOptionsForContinue` (+0xb0). Le second est pose par
    # `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` :
    #
    #     n = this.GetTargetingOptionsForContinue();          // virtuel, vtable +0x458
    #     _targetingOptionsForContinue = n.HasValue ? n.Value : targetingOptions;
    #
    # `None` ici = « pas d'override » -> la BASE
    # `IdunBattle.Entities.Abilities.AActiveAbility$$GetTargetingOptionsForContinue`, qui derive du
    # masque principal : `new TargetingOptions(_targetingOptions)`, puis `ForceMeleeTarget =
    # RangedBool.False` et `Rules |= AllowIgnoreForcedAttackTarget` (1 << 40). Cette base n'ajoute
    # JAMAIS `AllowDeadTarget` -- d'ou le defaut `False` de `can_continue_on_dead_target`.
    TARGETING_OPTIONS_FOR_CONTINUE = None

    @classmethod
    def targeting_options_for_continue(cls):
        """`AActiveAbility._targetingOptionsForContinue` — mirror du `.ctor` + de la base virtuelle.

        Rend `None` quand ni l'override ni le masque principal n'ont ete RE-lus (« pas mesure »,
        jamais un masque invente)."""
        override = cls.TARGETING_OPTIONS_FOR_CONTINUE
        if override is not None:
            return override
        base = cls.TARGETING_OPTIONS
        if base is None:
            return None
        from dataclasses import replace                        # noqa: PLC0415
        from .targeting import RANGED_BOOL_FALSE               # noqa: PLC0415
        from .targeting_rule import TargetingRule as TR        # noqa: PLC0415
        # Le `int(TR.<X>)` est HORS du `return` deliberement : le critere de derivation de
        # `probe_429_targeting_rule_inventory.rules_returned_by_port` lit tout `int(TR.<X>)` place
        # dans un `return` comme un CODE DE REFUS rendu. Ici c'est une CONSTRUCTION DE MASQUE
        # (`Rules |= AllowIgnoreForcedAttackTarget` du natif), pas un refus -- l'ecrire dans le
        # `return` faisait rougir `test_le_port_ne_rend_jamais_une_permission_qui_ne_soit_pas_un_
        # refus_natif` sur une PERMISSION que le port ne rend nulle part.
        rules = int(base.rules) | int(TR.AllowIgnoreForcedAttackTarget)
        return replace(base, force_melee_target=RANGED_BOOL_FALSE, rules=rules)

    @classmethod
    def can_continue_on_dead_target(cls) -> bool:
        """`IdunBattle.Entities.Abilities.AActiveAbility$$CanContinueOnDeadTarget` (slot 17 de
        `IActiveAbility`) — LE LECTEUR du bit 38 `AllowDeadTarget`, decompile verbatim :

            SetConfigValuesInTargetingOptions(ref _targetingOptionsForContinue);   // ne touche que Range
            return (_targetingOptionsForContinue.Rules >> 0x26) & 1;

        Le bit est donc lu sur le masque de CONTINUE (+0xb0+0x28 = +0xd8), jamais sur le masque
        principal : c'est pourquoi aucun `TARGETING_OPTIONS` du registre ne le porte, et pourquoi la
        tranche #429 ne l'a trouve dans aucune cascade de ciblage.

        `False` par defaut n'est PAS un refus devine : le scan d'instructions du binaire du build
        courant (`probe_429r1_bit_readers_scan.py`) ne trouve qu'UN SEUL site qui pose ce bit dans
        tout `GameAssembly.dll` --
        `IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$GetTargetingOptionsForContinue`.
        Le natif rend donc `false` pour toutes les autres abilities."""
        from .targeting_rule import TargetingRule as TR        # noqa: PLC0415
        opts = cls.targeting_options_for_continue()
        if opts is None:
            return False
        bit = int(TR.AllowDeadTarget)                          # hors `return` : cf. ci-dessus
        return bool(int(opts.rules) & bit)

    @classmethod
    def get_actual_target(cls, state: "State", caster_id: Optional[int],
                          target_id: Optional[int]) -> Optional[int]:
        """`IdunBattle.Entities.Abilities.AActiveAbility$$GetActualTarget` (slot 16 d'`IActiveAbility`)
        — mirror du corps relu : l'ability recopie SES `TargetingOptions` (`this+0xb0`, les 0x40
        octets) et delegue au slot 6 d'`ITargetingQuery`, c'est-a-dire
        `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`. Les deux numeros de slot sont LUS
        dans `data/symbols/<build>/metadata/interface_slots.tsv`, pas deduits d'un nom.

        C'est la fonction que `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` appelle
        AVANT ses deux gates : la cible que voient `IsDeadUnitAndNotAllowedByAbility`, `IsInvalidTarget`
        et `GetAbilityEntities` est TOUJOURS celle-ci, jamais celle de l'appelant (#287-r14).

        `TARGETING_OPTIONS is None` (masque non RE-lu) -> `target_id` rendu TEL QUEL par le foyer :
        sans masque le port ne devine pas quel domaine de cible l'ability veut."""
        from .behaviours.context import actual_target                 # noqa: PLC0415
        # Import DIFFERE, classe PORTEUR (mesure) : charger `abilities.behaviours.context` seul dans
        # un process FRAIS fait deja atterrir `abilities.base` dans `sys.modules` -- hisser fermerait
        # donc un cycle. Meme classe que les trois differes voisins de ce module.
        return actual_target(state, cls.TARGETING_OPTIONS, caster_id, target_id)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:  # pragma: no cover
        raise NotImplementedError(
            f"{type(self).__name__}.execute_behaviour non porté (cf. plan tranche EFFETS/ABILITIES)")

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`<X>Ability$$GetDynamicInvalidTargetReason` — LE PATRON a instancier par ability (mirror
        du virtuel slot vtable `+0x480`, que `AActiveAbility$$.ctor` lie en
        `TargetingOptions.DynamicTargetingTargetRule` a `options+0x38`).

        Rend un `TargetingRule` (0 = cible valide). N'est consulte que si l'ability pose le bit
        `TargetMatchesDynamicRule` (0x2) dans ses `TARGETING_OPTIONS` — exactement comme le natif,
        qui n'invoque la regle-delegue que sous ce bit.

        Defaut 0 : une sous-classe qui pose le bit 0x2 SANS surcharger cette methode degrade en
        « pas de refus dynamique » (permissif), jamais en refus invente. 1re instanciation :
        `WaaaghAbility` (1058), cf. `engine/runner/abilities/orks.py`."""
        return 0

    def get_dynamic_invalid_caster_reason(self, state: "State", caster_id: int) -> int:
        """`<X>Ability$$GetDynamicInvalidCasterReason` — le PENDANT CASTER du patron ci-dessus
        (mirror du virtuel slot vtable `+0x470`, que `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor`
        lie a `options+0x30`).

        Rend un `TargetingRule` (0 = caster valide). N'est consulte que si l'ability pose le bit
        `CasterMatchesDynamicRule` (0x4) dans ses `TARGETING_OPTIONS` — exactement comme
        `IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason`, qui n'invoque la
        regle-delegue `options+0x30` que sous ce bit :

            if ((rules & 4) != 0) {
                r = options[+0x30].Invoke(caster, casterTiles);
                if (r != 0) return GenericBrokenTargetingRule(r);
            }

        Defaut 0 : une sous-classe qui pose le bit 0x4 SANS surcharger cette methode degrade en
        « pas de refus dynamique » (permissif), jamais en refus invente. 1re instanciation (#250) :
        `GetEmRuntzAbility` (1045), cf. `engine/runner/abilities/loki/summon.py`."""
        return 0

    def sets_end_turn_flags(self, state: "State", caster_id: int) -> bool:
        """Mirror du virtual `IdunBattle.Entities.Abilities.AActiveAbility$$SetsEndTurnFlags (défaut `_dsl.True`) — résolu par la table
        d'overrides RE (une sous-classe portée PEUT surcharger pour une logique bespoke)."""
        return sets_end_turn_flags_for(self.ABILITY_TYPE, state, caster_id)

    def sets_active_ability_used_flag(self, state: "State", caster_id: int) -> bool:
        """Mirror du virtual `SetsActiveAbilityUsedFlag` (défaut `_dsl.True`, body foldé IdunBattle.Entities.Abilities.AActiveAbility$$SetsEndTurnFlags)."""
        return sets_active_ability_used_flag_for(self.ABILITY_TYPE, state, caster_id)
