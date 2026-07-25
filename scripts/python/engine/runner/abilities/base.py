"""Base des abilities actives portées + helpers DSL communs.

`ActiveAbility` = base d'une ability native `AActiveAbility` ; chaque sous-classe porte UNE ability
(VA citée) et implémente `execute_behaviour` (mirror de `<Ability>.ExecuteBehaviour`).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..state import State


def ability_attack_params(state: "State", caster_id: int, ability_id: str,
                          profile_name: str, ranged: bool = False,
                          min_key: str = "minDmg", max_key: str = "maxDmg",
                          hits_key: str = "nrOfHits", hits_add_key: str | None = None,
                          level_slot: str = "active"):
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
    from ..components import StatsComponent
    from ...entities.effects.magnitude import ability_var
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
    pierce = profile_pierce(ctx, profile_name, ranged)
    return int(bmin), int(bmax), pierce, int(hits)


def profile_pierce(ctx, profile_name: str, ranged: bool = False) -> int:
    """Perçage effectif d'une attaque = `clamp(0, 100, profil.PiercingRatio + ExtraPierce +
    ExtraPierce{Melee|Ranged})` (volet perçage commun de `MinMaxDamage`/`AttackWithAttackDamage` :
    PiercingRatio du profil de dégât + les stats de perçage du caster). Extrait de
    `ability_attack_params` pour être PARTAGÉ par les deux feuilles à dégât-node `StatAmount`/`PercentageOf`
    (sans bornes d'arme, elles routent leur base par ce perçage) : le mode `amount` de `AttackWithAttackDamage`
    (Psyker, crit/block) ET la feuille directe `AttackWithAbilityDamage` (DoT feu, sans crit/block — appelée
    avec `ctx=None`). `ctx` = `UnitContext` du caster (None → perçage = PiercingRatio seul, cas de la tuile
    en feu qui n'a pas de stats ExtraPierce)."""
    import gameconfig as GC
    dp = GC.damage_profile(profile_name) or {}
    extra = ctx.extra_pierce if ctx is not None else 0
    dir_pierce = ((ctx.extra_pierce_ranged if ranged else ctx.extra_pierce_melee)
                  if ctx is not None else 0)
    return max(0, min(100, int(dp.get("PiercingRatio") or 0) + extra + dir_pierce))


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
NO_END_TURN_ABILITY_TYPES = frozenset({
    1014, 1063, 1081, 1106, 1118, 1121, 1127, 1131, 1139, 1173, 1189, 1198, 1202, 1210,
})

# Classes overridant `SetsActiveAbilityUsedFlag` (pas de flag ActiveAbilityUsed=2) — 13 classes
# (PAS 1063 FireAndReposition ni 1121 ItItches ; + 1077 EarlyWarningOverride qui n'override QUE celui-ci).
NO_ABILITY_USED_FLAG_ABILITY_TYPES = frozenset({
    1014, 1077, 1081, 1106, 1118, 1127, 1131, 1139, 1173, 1189, 1198, 1202, 1210,
})

# Ability 1081 FightingRetreat (Darkstrider) = SEUL override CONDITIONNEL lu dans le build courant :
# `IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$SetsActiveAbilityUsedFlag = `_dsl.Direct(!Any(battleQuery slot 0x7c
# (caster, currentPlayerEntityId)))` — pose les flags UNIQUEMENT si AUCUN ennemi adjacent (i2 : « does not
# end Darkstrider's turn IF he is adjacent to an enemy »). Son SetsEndTurnFlags (corps foldé, non isolable
# offline) est aligné sur la même condition par le texte i2 — ASSOMPTION DOCUMENTÉE, même prédicat.
FIGHTING_RETREAT = 1081


def _fighting_retreat_sets_flags(state: "State", caster_id: int) -> bool:
    """Mirror IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$SetsActiveAbilityUsedFlag : True (pose les flags = tour fini) ssi PAS d'ennemi VIVANT adjacent (dist hex 1)
    au caster. Ennemi = `team` differente (meme convention que les autres ports, ex. `_nearest_enemy`)."""
    import hexgeo
    from ..components import OwnerComponent, PositionComponent, UnitComponent
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

    def sets_end_turn_flags(self, state: "State", caster_id: int) -> bool:
        """Mirror du virtual `IdunBattle.Entities.Abilities.AActiveAbility$$SetsEndTurnFlags (défaut `_dsl.True`) — résolu par la table
        d'overrides RE (une sous-classe portée PEUT surcharger pour une logique bespoke)."""
        return sets_end_turn_flags_for(self.ABILITY_TYPE, state, caster_id)

    def sets_active_ability_used_flag(self, state: "State", caster_id: int) -> bool:
        """Mirror du virtual `SetsActiveAbilityUsedFlag` (défaut `_dsl.True`, body foldé IdunBattle.Entities.Abilities.AActiveAbility$$SetsEndTurnFlags)."""
        return sets_active_ability_used_flag_for(self.ABILITY_TYPE, state, caster_id)
