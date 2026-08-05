"""Abilities de la faction DarkAngels (faction native id 10, codename « Loki »). RE ghidra gqfc5mff6c
(VA citees). Case-220 / docs/rl/case-220/dark-angels.md.

Org native = 1 classe par ability (`Abilities.Active.Loki.*`) ; les arbres SPECIFIQUES vivent avec leur
ability. Module DEDIE (les modules `loki/` et `behaviours/` sont deja au seuil de split ~1000 lignes).

PlasmaCannon (`PlasmaCannonAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour`, id 1150, unite darkaTerminator) :
attaque RANGED (range 3, profil Plasma) 3x sur la cible + 3x sur JUSQU'A 2 unites tirees au hasard
DIRECTEMENT DERRIERE la cible. Meme plage de degat ET meme nb de coups pour les deux volets. Template
`plasma_grenade_tree` (loki/splash.py) MOINS le selecteur splash (adjacent-cible -> directly-behind) ET
avec une FACTORY NATIVE DIFFERENTE (cf. ci-dessous, piege rngcrit-1202).

Lot #112 (actives DarkAngels NO-OP cote COMBAT) — toutes ont pour ARTEFACT NATIF un
`<Ability>.ExecuteBehaviour` (arbre de noeuds `DSLFactory`) => portees en ARBRE DSL, jamais en `execute_*`
imperatif (frontiere #149) :
  * `SuperchargeAbility$$ExecuteBehaviour`          (1103, darkaHellblaster « Sarquael ») -- 2 volets Plasma
  * `ExemplarOfHateAbility$$ExecuteBehaviour`       (1140, darkaAsmodai « Asmodai »)      -- debuff + branche Chaos
  * `CalibaniteGreatswordAbility$$ExecuteBehaviour` (1189, darkaCompanion « Forcas »)     -- toggle de POSTURE
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import hexgeo

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import AtomicGroup, Foreach, If, op_add, op_and
from ...entities.effect_type import EffectType
from ...entities.formulas import AngleBetweenLines, Count, percentage_of_attack_capped_at_max
from ...entities.selectors import (AdjacentTiles, Alive, Cache, Caster, Enemies, FilterContinuous,
                                   FixedTileIds, PickFirstN, SortByDistance, SortByFormula, Subject,
                                   SurroundingTiles, Target, Tiles, TilesBehindInLine, UnitSet,
                                   Union, Units, UnitsDirectlyBehind)
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.stats import StatPart, StatType
from ...entities.triggers import (AreEnemies, AreEqual, HasEffect, HasGrandAlliance, HasUnit,
                                  TriggerAnd)
# `IdunBattle.Core.Services.MinMaxDamage$$Avg` (demi-vers-le-PAIR) : la cle de tri de
# `SortAttackersByDamagePredictionSelector`. Import AU NIVEAU MODULE pour que le cablage soit
# verifiable sur l'objet importe (garde #344), et non sur le texte du fichier.
from ...services.min_max_damage import min_max_avg
from .base import ActiveAbility
from .behaviours import (AddEffect, AddStatOverrideEffect, AttackWithAttackDamage, RemoveEffect,
                         UseActiveAbility, entities_from_state)
from .targeting import (RANGE_FROM_CONFIG, RANGE_SELF, RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE,
                        RANGED_BOOL_IF_RANGED_CASTER, RANGED_BOOL_TRUE, TargetingOptions)
from .targeting_rule import TargetingRule as TR
from ...dsl.base import _round_fix64
from ...entities.effects import hits_bonus_from_effects
from ...entities.effects.magnitude import ability_var
from ...services.damage_prediction import get_attack_prediction
from ..components import (HealthComponent, OwnerComponent, PositionComponent, ShieldComponent,
                              StatsComponent, UnitComponent)
from ..components import PositionComponent
from ..components import StatsComponent
from ..damage_model import attacker_modifiers, select_weapon_pierce
from .base import convert_rounds_to_turns

if TYPE_CHECKING:
    from ..state import State


# =================================================================================================== #
# GATE DE CIBLE (#115) — les `TARGETING_OPTIONS` des 7 actives DarkAngels portees.
#
# Le masque est le champ `Rules` (`options+0x28`) des `IdunBattle.Core.Services.TargetingOptions` que
# le `<X>Ability$$.ctor` passe a `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor`. LU au
# decompile, ability par ability — jamais deduit d'une autre. `AActiveAbility$$.ctor` recopie la
# struct dans `this+0x70..0xaf` et n'ECRASE que `+0x30`/`+0x38` (les deux regles-delegues) : le champ
# `Rules` arrive donc INTACT jusqu'au filtre, et le litteral du ctor EST le masque effectif.
#
# DEUX FORMES de ctor coexistent dans ce lot, et il faut les distinguer (c'est le piege documente
# dans la docstring de `TargetingOptions`) :
#
#   (A) LITTERAL DIRECT — `TargetingOptions..ctor(&opts, <bool AddCasterMode>, &statsFromClass,
#       <int>, <RULES>, 0, 0, 0)` : la surcharge 8 arguments pose `Rules <- param 5` tel quel
#       (`IdunBattle.Core.Services.TargetingOptions$$.ctor` : `*(param_1 + 0x28) = param_5`).
#       -> DarkTalonStrike, DeathOnTheWind, Hailstrike, ExemplarOfHate, CalibaniteGreatsword.
#
#   (B) PRESET STATIQUE COPIE — le ctor n'appelle AUCUN `TargetingOptions..ctor` : il recopie les
#       0x40 octets d'un champ STATIQUE de `TargetingOptions` (bloc `<class>+0xb8`) directement dans
#       la variable passee a `AActiveAbility..ctor`. Le masque est alors celui qu'ecrit
#       `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28`, VALEUR CONSTANTE lue
#       dans ce cctor. -> PlasmaCannon, Supercharge (preset du bloc statique a l'offset +0x140,
#       `cctor` : `*(statics + 0x168) = 0x4002`).
#       Ce n'est PAS la surcharge « preset + flags » (`TargetingOptions..ctor(&opts, &preset,
#       <flags>)`, qui fait `Rules <- preset.Rules | flags` et dont le litteral visible ne serait pas
#       le masque effectif) : ici il n'y a AUCUN flag additionnel, la copie est integrale.
#
# Noms des bits : enum `IdunBattle.Core.Services.TargetingRule` VERBATIM, via le mirror GENERE
# `engine/runner/abilities/targeting_rule.py` (SEULE source de noms de bits du port).
# =================================================================================================== #


def _ability_profile(ability_id: str, key: str) -> str:
    """`IdunBattleLogic.Entities.DSLFactory$$DamageProfileFromConfig(config@0x60, <AbilityConstantType>)` :
    le NOM du profil de degat lu dans les CONSTANTES de l'ability (`damageProfile` = 0x2e = 46,
    `damageProfile_2` = 0x3f = 63 — enum `IdunBattle.Configuration.AbilityConstantType`, table de symboles
    du build). Oracle = la CONFIG (valeur BRUTE lue telle quelle par le natif). LEVE si la cle manque :
    une cle voisine qui rendrait un repli silencieux rendrait toute assertion aval AVEUGLE."""
    import gameconfig as _GC
    consts = ((_GC.ability(ability_id) or {}).get("constants") or {})
    if key not in consts:
        raise KeyError(f"{ability_id}: constante '{key}' absente du gameconfig")
    return str(consts[key])


def _resolve_target_tile(state, target_id):
    """`target@0x178` d'un cast TILE-TARGET : rend l'id de TUILE. Le message porte deja l'entite-TUILE
    (DarkTalonStrike/DeathOnTheWind : `abilityTargets` live rend `kind=tile`) ; on tolere aussi une
    entite-UNITE (robustesse harnais) en retombant sur sa MainTile — c'est ce que fait le natif partout
    via `EntityExtensions.GetMainTile`. None si non resolvable."""
    board = state.board
    if target_id is None or board is None:
        return None
    if int(target_id) in board.by_id:
        return int(target_id)
    e = state.get_entity(target_id)
    pc = e.get_component(PositionComponent) if e is not None else None
    return board.id_at(pc.col, pc.row) if pc is not None else None


# --- Ids d'effet cites par les arbres (mirror des litteraux du decompile) --------------------------
SUPERCHARGE_EXTRA_PIERCING = int(EffectType.Supercharge_ExtraPiercing)             # 0x4b8 = 1208
EXEMPLAR_OF_HATE_TARGET = int(EffectType.ExemplarOfHate_Target)                    # 0x50d = 1293
PINNED = int(EffectType.Pinned)                                                   # 0x429 = 1065 (UI « Suppressed »)
TEMPORARY_STAT_OVERRIDE = int(EffectType.TemporaryStatOverride)                    # 0x510 = 1296
CG_STRIKE = int(EffectType.CalibaniteGreatswordStrike)                            # 0x57c = 1404
CG_SWEEP = int(EffectType.CalibaniteGreatswordSweep)                              # 0x57d = 1405
CG_STRIKE_HIT_REDUCTION = int(EffectType.CalibaniteGreatsword_StrikeHitReduction)  # 0x57e = 1406
CG_STRIKE_OVERWATCHING = int(EffectType.CalibaniteGreatswordStrike_Overwatching)   # 0x591 = 1425
OVERWATCH_AUTO_ATTACK = int(EffectType.Overwatch_AutoAttack)                      # 0x3f1 = 1009

# `HasTrait(target@0x178, 0x7ea)` d'ExemplarOfHate : 0x7ea = 2026 = le PSEUDO-trait de GRANDE-ALLIANCE
# **Chaos** (`idun.Idun.Source.Shared.GrandAlliance$$GetTrait` : "Imperial"->0x1a=26, ...->0x3ee=1006
# Xenos, ...->0x7ea=2026 Chaos). Ce n'est PAS un trait gameconfig : AUCUNE unite ne porte "Chaos" dans
# sa liste `traits` -> un `HasTrait(Target(), 2026)` naif (via `ctx.has_trait`, qui lit les NOMS
# gameconfig) serait TOUJOURS faux et la branche Chaos serait MORTE. Le port passe donc par
# `HasGrandAlliance(unit, factions)` (meme derivation que le `HasTrait(killer, 26=Imperial)` d'ActOfFaith,
# live-valide). Les 5 factions Chaos des 22 du jeu (`GrandAllianceId == "Chaos"` en gameconfig).
CHAOS_FACTIONS = frozenset({
    "BlackLegion", "DeathGuard", "ThousandSons", "WorldEaters", "EmperorsChildren",
})


def plasma_cannon_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour` (id 1150, darkaTerminator — MIRROR du
    DECOMPILE) :
        ExecuteAtomic( op_BitwiseAnd(
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(var0xc,var0xd), Plasma,
                                   GetHits(0)=GetNumberConstant(0x2f)=nrOfHits),                       # [MAIN]
            AttackWithAttackDamage(caster@0x160,
                PickRandomly( UnitsDirectlyBehind(caster, target), 2 ),
                MinMaxDamage(MEME), Plasma, GetHits(0)=nrOfHits(MEME)) ),                              # [SPLASH]
          0x2a )

    DIFFERENCES vs `plasma_grenade_tree` (le template cite par la roadmap) — 3 divergences LUES au decompile,
    JAMAIS copiees du commentaire du template :

    1. **SELECTEUR splash = `PickRandomly(UnitsDirectlyBehind(target), 2)`** (PlasmaGrenade = `Enemies(caster,
       AdjacentUnits(target,1))`). `IdunBattleLogic.Entities.DSLFactory$$UnitsDirectlyBehind` (DEJA porte, selectors.py:157, cite
       PlasmaCannon) = ennemis-du-caster VIVANTS sur l'anneau R1 de la cible, du COTE OPPOSE au caster
       (`MinDistance(caster,cand) > MinDistance(caster,target)`, STRICT = AmountIsGreater, case #48 : la
       laterale a distance EGALE est EXCLUE), meme elevation (tolerance +-1). Le `IdunBattleLogic.Entities.DSLFactory$$PickRandomly(.,2)` (2 = nrOfTargets, lu au decompile) est FOLDE dans la feuille via `pick_n=2` (comme Fragstorm
       IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormAbility$$ExecuteBehaviour : tire 2 cibles DANS la resolution du selecteur d'attaque via `state.rng`). len<=2 -> les deux
       unites, MAIS le natif TIRE QUAND MEME (`min(len(pool),2)` tirages, bornes decroissantes) -- #130,
       cf. `_pick_randomly_n`. La feuille re-trie par id apres le pick (`OrderBy` de `AttackBehaviour$$Execute`).

    2. **HITS main == HITS splash == `nrOfHits` (0x2f)** : les DEUX volets appellent `GetHits(param_1,0)`
       (`ArmoriumCherubAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits` = `GetNumberConstant(config, 0x2f, 0)` = nrOfHits). PlasmaGrenade
       differenciait main (0x2f) / splash (0x32=nrOfHits_2) ; ICI le splash utilise la MEME cle `nrOfHits` (defaut
       `hits_key`). Plage `MinMaxDamage(minDmg/maxDmg)` PARTAGEE main/splash (memes cles par defaut). Config 1150 :
       nrOfHits=3, range=3, damageProfile=Plasma.

    3. **FACTORY NATIVE = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` -> `native_factory="attack"`** (PlasmaGrenade =
       `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` -> "ability"). CLASSIFIE PAR XREFS de l'ExecuteBehaviour natif (piege
       rngcrit-1202 / tip #2), PAS au nom du template : les deux call-sites `IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour+0x1eb`/`IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour+0x2a6` referencent
       IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage (verifie via `list_xrefs` -- PlasmaCannon ABSENT des xrefs de IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage). `native_factory=
       "attack"` => `AttackDamageOperation.ExecuteHit` = valeur brute + resolve slot-8 GASPILLE = **2 tirages/
       coup a cc=0** (le DEFAUT `is_attack_damage_op=True`). Un port copie a l'aveugle du template (native_factory=
       "ability", 1 tirage/coup) desyncherait le RNG des le coup 2 -- confronte LIVE par le test.

    `op_BitwiseAnd` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ; `ExecuteAtomic` ->
    `AtomicGroup` (inline #201 ; tag 0x2a = id du groupe atomique, aucun `EvaluateAbilities` implicite, cf. #209).
    Ordre = main PUIS splash (cibles triees par id = OrderBy natif) -> meme `state.rng`. RANGED (range 3) ->
    `is_melee=False`.

    GAP (flagge) : (a) FERME par #433-r4-r1-r4 -- le GATE d'ELEVATION de `UnitsDirectlyBehind`
    (`TilesOnSameElevationSelector`, maxDiff=1) etait no-op cote runner faute de `ctx.elev_by_pos` ;
    `DslContext.__post_init__` le derive desormais du `board`, donc un candidat derriere la cible a
    `|dElev| >= 2` de la MAIN TILE de celle-ci sort du pool de splash, comme dans le natif.
    (b) RESIDU #215 restant, >2 candidats derriere la cible : l'ordre d'enumeration natif du pool
    (non id-trie) decide QUELLES 2 unites sont piquees -> le SET peut diverger (la CONSO, elle, est exacte
    dans tous les cas depuis #130). A <=2 derriere : BIT-EXACT, confronte live (ratio live/offline == 1.0 sur
    la main ET le splash, regimes pool=1 et pool=2, `probe_215_pick_randomly_rng.py`)."""
    tgt = Target()
    # [MAIN] cible du message, 3 coups (nrOfHits), plage MinMaxDamage, profil Plasma, ranged.
    main = AttackWithAttackDamage(tgt, "PlasmaCannon", "Plasma", is_melee=False,
                                  native_factory="attack")                       # IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage (XREFS)
    # [SPLASH] jusqu'a 2 unites tirees derriere la cible ; MEME plage, MEME nb de coups (nrOfHits, defaut).
    splash = AttackWithAttackDamage(UnitsDirectlyBehind(), "PlasmaCannon", "Plasma", is_melee=False,
                                    multi=True, pick_n=2, native_factory="attack")  # PickRandomly(UnitsDirectlyBehind,2)
    return AtomicGroup(op_and(main, splash))


class PlasmaCannonAbility(ActiveAbility):
    """`PlasmaCannonAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$ExecuteBehaviour` (id 1150, darkaTerminator ; faction DarkAngels).

    Sequence native (`ExecuteAtomic`, `op_BitwiseAnd`) :
        AttackWithAttackDamage(actor, target, MinMaxDamage, Plasma, nrOfHits=GetHits(0)=0x2f)             # principale
      & AttackWithAttackDamage(actor, PickRandomly(UnitsDirectlyBehind(actor,target), 2), MEME MinMaxDamage,
                               Plasma, nrOfHits=GetHits(0)=0x2f)                                            # splash <=2
    Splash = jusqu'a 2 unites ennemies tirees au hasard DIRECTEMENT DERRIERE la cible (anneau R1, cote oppose au
    caster), MEME plage de degat ET MEME nb de coups que la principale. RANGED (range 3, profil Plasma).

    `execute_behaviour` DELEGUE a `plasma_cannon_tree()` (mirror 1:1 du decompile). Le SPLASH est un SEUL
    `AttackWithAttackDamage(selecteur-multi, pick_n=2)` (== le natif, PAS un `Foreach`) : `AttackBehaviour.Execute`
    resout la liste + `OrderBy` par id + `PickRandomly(2)`. FACTORY `native_factory="attack"` (IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage, prouve
    par XREFS -- CONTRASTE le template PlasmaGrenade "ability" IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage, piege rngcrit-1202/tip #2) => 2 tirages/
    coup a cc=0. Passif porteur `Deathwing` [fable] non porte (no-op ; se declenche on-block, hors path degat)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.PlasmaCannon)  # 1150
    ABILITY_ID = "PlasmaCannon"

    # GATE DE CIBLE (#115) — forme (B) PRESET COPIE.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaCannonAbility$$.ctor` :
    #     opts <- <TargetingOptions statics>+0x140 .. +0x17f    (copie des 0x40 octets, aucun flag ajoute)
    #     AActiveAbility..ctor(this, &opts, 0, 0)
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit ce preset : `*(statics+0x168) = 0x4002`
    # (= `<preset>+0x28` = `Rules`). Decomposition :
    #     0x2    TargetMatchesDynamicRule -> consulte `get_dynamic_invalid_target_reason` ; PlasmaCannon
    #            n'a PAS de `GetDynamicInvalidTargetReason` natif (le slot vtable +0x480 reste celui de
    #            la base) -> defaut 0 cote port = mirror exact.
    #     0x4000 TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie).
    # PORTEE (#241) : le preset `TargetingOptions` statique `+0x140` embarque le
    # `TargetingRange` statique `+0x18` (`useRangeFromConfig`) et `forceMeleeTarget = True`
    # -> portee = `PlasmaCannon.constants.range` (3), clampee a 1 des que le caster a un
    # ennemi au contact.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        plasma_cannon_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]      # cibles splash != cible principale
        return {"ability": "PlasmaCannon", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


# =================================================================================================== #
# DarkTalonStrike (1092, `darkaAzrael` — Azrael, HERO) — case #117 (face COMBAT ; la face DECISION
# `DarkTalonStrikePlaybook` etait deja portee).
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$ExecuteBehaviour` (MIRROR) :
#   mainUnits = Cache( Units(target@0x178) )                       # l'OCCUPANT de la tuile visee
#   targets   = Enemies( owner@0x148, Units(GetTilesInBestLine()) )
#   Execute( Foreach(targets, <lambda b__0>) )
#
# `<lambda b__0>` (`DarkTalonStrikeAbility.u003Cu003Ec__DisplayClass1_0$$u003CExecuteBehaviouru003Eb__0`)
# = pour CHAQUE cible :
#   Group( AddEffect(0x429 = 1065 Pinned, AbilityStateReference, targets = <cible>)
#          op_Addition  DamageUnit(mainUnits, <cible>),
#          <cible>, 0x5b )
#
# `DarkTalonStrikeAbility$$DamageUnit(mainSel, cible)` (MIRROR) :
#   isMain = AreEqual(<cible>, mainSel)
#   AttackWithAbilityDamage( caster@0x160, <cible>,
#       If(isMain, MinMaxDamage(minDmg/maxDmg), MinMaxDamage2(minDmg_2/maxDmg_2)),
#       If(isMain, DamageProfileFromConfig(0x2e = damageProfile), DamageProfileFromConfig(0x3f = damageProfile_2)),
#       ConditionalAmount(isMain, GetHits() = GetNumberConstant(0x2f = nrOfHits),
#                                 GetHitsToBonusTarget() = GetNumberConstant(0x32 = nrOfHits_2)),
#       AbilityOrEffect(0x444 = 1092) )
#
# `DarkTalonStrikeAbility$$GetTilesInBestLine` (MIRROR ; corps INLINE dans ExecuteBehaviour) :
#   ring    = AdjacentTiles(target@0x178)
#   nearest = First( SortByDistance(AdjacentTiles(caster@0x160), target@0x178), 1 )
#   angle   = AngleBetweenLines(caster@0x160, nearest, target@0x178, subject@0x180)
#   count   = Count( Units( GetTilesInLine(subject@0x180) ) )
#   best    = First( SortByFormula( SortByFormula(ring, angle, flag 1 = ASC), count, flag 0 = DESC ), 1 )
#   return    target@0x178  op_Addition  GetTilesInLine(best)
#
# `DarkTalonStrikeAbility$$GetTilesInLine(from)` (MIRROR) :
#   settings = new TilesBehindInLineSettings { +0x10 = 1, +0x11 = 1 }        # cf. TilesBehindInLine
#   pred     = HasUnit(subject@0x180) op_BitwiseAnd AreEnemies(owner@0x148, Units(subject@0x180))
#   return     FilterContinuous( TilesBehindInLine(target@0x178, from, settings, /*count*/ null), pred )
#
# GEOMETRIE (le point NON EVIDENT, et ce que la face DECISION ne modelise PAS) : le `settings +0x10 = 1`
# active `IsWalkable` **ET** le gate d'ELEVATION de `TileUtil$$IsTileValidForList` (|delta| < 2), et
# `+0x11 = 1` fait SUIVRE la tuile de reference le long de la ligne -> le rayon casse des qu'une MARCHE
# de 2 niveaux se presente. MESURE LIVE (runner 669, board C4_02, colonne 5) : caster (5,4), cible
# (5,5) el.1, ennemis alignes (5,6) el.1 / (5,7) el.3 / (5,8) el.3 -> le natif ne frappe QUE (5,5) et
# (5,6) ; la marche 1->3 entre (5,6) et (5,7) coupe le beam.
# =================================================================================================== #

DARK_TALON_STRIKE_ID = "DarkTalonStrike"
DTS_PINNED = int(EffectType.Pinned)                      # 0x429 = 1065 (i2 : « Suppressed »)


def dark_talon_get_tiles_in_line(target_ref, from_sel):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInLine` (MIRROR 1:1).

    `AreEnemies(owner@0x148, Units(subject))` : `Caster()` tient lieu d'`Owner@0x148` (Owner == Caster pour
    un cast d'active, convention deja en place dans tout le port)."""
    pred = TriggerAnd(HasUnit(Subject()), AreEnemies(Caster(), Units(Subject())))
    return FilterContinuous(
        TilesBehindInLine(target_ref, from_sel, check_walkable=True, update_reference=True), pred)


def dark_talon_get_tiles_in_best_line(target_ref):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$GetTilesInBestLine` (MIRROR 1:1).

    Les DEUX `SortByFormula` sont CHAINES (angle ASC puis count DESC) : tri STABLE -> cle PRIMAIRE =
    nb d'ennemis alignes (DECROISSANT), tie-break = ecart ANGULAIRE a la direction d'approche du Dark
    Talon (CROISSANT, donc « tout droit » gagne a egalite). `First(., 1)` = `PickFirstN(., 1)`."""
    ring = AdjacentTiles(target_ref)
    nearest = PickFirstN(SortByDistance(AdjacentTiles(Caster()), target_ref), 1)
    angle = AngleBetweenLines(Caster(), nearest, target_ref, Subject())
    count = Count(Units(dark_talon_get_tiles_in_line(target_ref, Subject())))
    best = PickFirstN(SortByFormula(SortByFormula(ring, angle, ascending=True),
                                    count, ascending=False), 1)
    return Union(target_ref, dark_talon_get_tiles_in_line(target_ref, best))


def dark_talon_strike_tree(target_ref):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$ExecuteBehaviour`
    (MIRROR 1:1) :

        Foreach( Enemies(Units(GetTilesInBestLine())),
                 AddEffect(1065 Pinned, <cible>) + DamageUnit(Cache(Units(target)), <cible>) )

    - ORDRE des cibles = celui des TUILES (cible d'abord, puis la ligne en s'eloignant) : c'est le
      contrat de `Units` (`UnitsOnTilesSelector` itere les tuiles), et il fixe la consommation de
      `state.rng` coup par coup.
    - `op_Addition` = `CombinedBehaviour` (effets PURS) -> Pinned pose AVANT le degat, comme le live
      (`Group#22 Pinned` precede `Group#26` du coup dans la cascade).
    - le `Group(., <cible>, 0x5b)` natif est du REGROUPEMENT VISUEL (aucune mutation) -> non porte,
      comme pour ThriceBlessedConflagration.
    - `DamageUnit` : les TROIS noeuds conditionnels natifs (`If` degat, `If` profil, `ConditionalAmount`
      coups) partagent le MEME predicat `AreEqual(<cible courante>, Cache(Units(target@0x178)))`, bati
      PAR ELEMENT du `Foreach` -> constant pour l'element. On les factorise en UN `If` de BEHAVIOUR
      autour de deux feuilles `AttackWithAttackDamage(native_factory="ability")` qui ne different que
      par leurs cles de config : evaluation strictement identique au natif.
    - `native_factory="ability"` = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` (lu au
      decompile de `DamageUnit`) -> `AbilityDamageOperation.ExecuteHits` = 1 tirage/coup, pas de crit."""
    main_sel = Cache(Units(target_ref))                       # Cache(Units(target@0x178))
    is_main = AreEqual(Subject(), main_sel)
    main_hit = AttackWithAttackDamage(
        Subject(), DARK_TALON_STRIKE_ID, _ability_profile(DARK_TALON_STRIKE_ID, "damageProfile"),
        is_melee=False, native_factory="ability",
        ability_type=int(ActiveAbilityType.DarkTalonStrike))
    line_hit = AttackWithAttackDamage(
        Subject(), DARK_TALON_STRIKE_ID, _ability_profile(DARK_TALON_STRIKE_ID, "damageProfile_2"),
        is_melee=False, native_factory="ability",
        min_key="minDmg_2", max_key="maxDmg_2", hits_key="nrOfHits_2",
        ability_type=int(ActiveAbilityType.DarkTalonStrike))
    body = op_and(AddEffect(DTS_PINNED, EffectType.Pinned.name, Subject(), duration_rounds=None),
                  If(is_main, main_hit, line_hit))
    return Foreach(Enemies(Units(dark_talon_get_tiles_in_best_line(target_ref))), body)


class DarkTalonStrikeAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$ExecuteBehaviour`
    (id 1092, `darkaAzrael` — Azrael, Dark Angels) — cf. le bloc de commentaire ci-dessus.

    Kit gameconfig 1092 : `damageProfile=DirectDamage` (PiercingRatio 100), `nrOfHits=1`,
    `damageProfile_2=Bolter`, `nrOfHits_2=6`, `range=2`, `minDmg`/`maxDmg` + `minDmg_2`/`maxDmg_2`
    (rarity-affected), `attackRangeType=Ranged`.

    CIBLE = une **TUILE** (`abilityTargets` live : `kind=tile`) portant un ennemi — le `target_id` du
    message est l'entite-TUILE, pas l'unite (meme regime que SquigMine/DevastatingRefrain). L'unite
    principale est `Units(target)` = son occupant.

    OBSERVABLE : (1) l'occupant de la tuile visee prend `nrOfHits` coup(s) `DirectDamage` ;
    (2) chaque ennemi de la ligne CONTIGUE partant de la tuile visee, dans la direction qui en aligne le
    plus (tie-break = alignement avec l'approche), prend `nrOfHits_2` coups `Bolter` ; (3) TOUTES les
    unites frappees recoivent `Pinned` (1065).

    Turn-flags = defauts base (1092 absent des overrides -> le cast finit le tour)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.DarkTalonStrike)   # 1092
    ABILITY_ID = DARK_TALON_STRIKE_ID

    # GATE DE CIBLE (#115) — forme (A) LITTERAL DIRECT.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.DarkTalonStrikeAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, 0, &statsFromClass, 2, 0x80040, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 0, 0)
    # Decomposition (`TargetingRule`) :
    #     0x40    TargetIsTile           -> PORTE (branche `GetMainTile(target)` + `IsWalkable`, qui
    #                                       rend le litteral `ValidRequest`).
    #     0x80000 TargetTileHasEnemyUnit -> **PORTE depuis #249** (`IsEmptyOrSteppable(GetMainTile)` ou
    #                                       `!UnitsCanAttackEachOther(caster, GetUnit(target))` -> refus).
    # C'EST CE MASQUE QUI PORTAIT LE GAP MESURE : avant #249 la ligne ci-dessus disait « NON PORTE » et
    # notait « le port rend 0 sur toutes les cibles, y compris celles que le natif refuse en
    # `TargetTileHasEnemyUnit` ». Le trou est ferme ; il reste PERMISSIF pour une cible que le port ne
    # resout pas en tuile (`entity_tiles` vide) et pour une MoW-cible (le natif rend `GetUnit` NUL la
    # ou le port pose un `UnitComponent` d'identite -- le port accepte, le natif refuse).
    # PORTEE (#241) : `range = TargetingRange` statique `+0x18` (`useRangeFromConfig` ->
    # `DarkTalonStrike.constants.range` = 2), `forceMeleeTarget = IfRangedCaster` (clamp a 1
    # seulement si le caster est RANGED et a un ennemi au contact).
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsTile | TR.TargetTileHasEnemyUnit,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_IF_RANGED_CASTER)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        board = state.board
        if target_id is None or board is None:
            return None
        # `target@0x178` = une entite-TUILE (cast tile-target) ; on accepte aussi une entite-UNITE
        # (robustesse harnais) en retombant sur sa MainTile.
        tile_id = _resolve_target_tile(state, target_id)
        if tile_id is None:
            return None
        target_ref = FixedTileIds([tile_id])
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id)
        dark_talon_strike_tree(target_ref).execute(entities, ectx)
        hits = [{"target": p["target"], "attack": p["attack"]}
                for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        pinned = [p["target"] for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": DARK_TALON_STRIKE_ID, "caster": caster_id, "tile": tile_id,
                "hits": hits, "pinned": pinned, "dsl": True}


# =================================================================================================== #
# DeathOnTheWind (1213, `darkaStormSpeeder` — Storm Speeder, MACHINE OF WAR) — case #117.
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$ExecuteBehaviour` (MIRROR) :
#   tiles   = Cache( GetMachineAttackTiles(), 1 )
#   enemies = Enemies( caster@0x160, Units(tiles) )
#   attack  = Attack( caster@0x160, subject@0x180,
#                     AbilityDamage(caster@0x160, subject@0x180, MinMaxDamage,
#                                   Direct(Nullable(GetDamageProfile())), Get(GetHits()),
#                                   AbilityOrEffect(this+0x10)),
#                     AbilityOrEffect(this+0x10) )              # == DSLFactory.AttackWithAbilityDamage
#   Execute( ( InformList(0xc1, tiles)  &  Foreach(enemies, attack) )
#            &  AddEffect(0x4e9 = 1257 DeathOnTheWind_ExtraPctDamage, AbilityStateReference,
#                         source = caster@0x160, targets = Alive(enemies), duree = dsl+0xc0 = Direct(1)) )
#
# `DeathOnTheWindAbility$$GetMachineAttackTiles` (MIRROR) :
#   ring  = SurroundingTiles(target@0x178, includeCenter = 0, radius = 1)
#   cnt   = Count( Enemies(caster@0x160, Units(GetTilesInLine(subject@0x180))) )
#   best  = First( SortByFormula(ring, cnt, flag 0 = DESC), 1 )
#   line  = GetTilesInLine(best)
#   start = First( SortByDistance(Tiles(target@0x178), First(line, 1)), 1 )     # singleton -> IDENTITE
#   return  Tiles( start  op_Addition  line )                                   # tile-domain -> IDENTITE
#
# `DeathOnTheWindAbility$$GetTilesInLine(from)` (MIRROR) :
#   n        = GetNumberConstant(config@0x60, 0x17 = nrOfTiles)
#   settings = new TilesBehindInLineSettings { +0x10 = 0, +0x11 = 1 }   # PAS de gate walkable/elevation
#   return     TilesBehindInLine(target@0x178, from, settings, Get(n - 1))
# -> `nrOfTiles - 1` tuiles a partir de la voisine choisie + la tuile de la cible = `nrOfTiles` hexes
#    (i2 : « straight line 3 hexes long, starting on the hex of the targeted enemy »). AUCUN
#    `FilterContinuous` : tous les ennemis PRESENTS sur ces hexes sont frappes, trous compris.
#
# GATE DE CIBLAGE `DeathOnTheWindAbility$$GetDynamicInvalidTargetReason` (MIRROR) :
#   unit = UnitExtensions.GetUnit(<cible>) ; if (unit == null) return 0 /*valide*/
#   return EntityExtensions.GetNumAttacksReceivedThisTurn(unit) != 0 ? 0 : 2 /*INVALIDE*/
# -> la cible doit avoir DEJA recu >= 1 attaque ce tour (i2 : « Targets an enemy unit that was already
#    attacked this turn »). Gate de CIBLAGE natif (amont d'`ExecuteInternal`, cf. case-111) : il vit
#    dans `abilityTargets` live, PAS dans `ExecuteBehaviour` -> non re-implemente ici (le port n'a pas
#    encore le gate de ciblage generique, tache #115).
# =================================================================================================== #

DEATH_ON_THE_WIND_ID = "DeathOnTheWind"
DOTW_EXTRA_PCT_DAMAGE = int(EffectType.DeathOnTheWind_ExtraPctDamage)      # 0x4e9 = 1257


def death_on_the_wind_get_tiles_in_line(target_ref, from_sel, nr_of_tiles: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$GetTilesInLine` (MIRROR 1:1).
    `nr_of_tiles` = `GetNumberConstant(0x17 = nrOfTiles)` ; le noeud natif est `Get(n - 1)`."""
    return TilesBehindInLine(target_ref, from_sel, Const(int(nr_of_tiles) - 1),
                             check_walkable=False, update_reference=True)


def death_on_the_wind_machine_attack_tiles(target_ref, nr_of_tiles: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$GetMachineAttackTiles`
    (MIRROR 1:1).

    TROIS REDUCTIONS notees (aucune divergence d'evaluation) : (a) `First(SortByDistance(Tiles(target),
    First(line,1)), 1)` porte sur un SINGLETON (la MainTile de la cible) -> le tri et le `First` sont
    l'IDENTITE, on passe la tuile de la cible directement (meme reduction que ThriceBlessedConflagration) ;
    (b) le `Tiles(...)` ENVELOPPANT est l'identite sur un ensemble deja tile-domain
    (`UnitsMainTilesSelector` d'une entite-TUILE rend la tuile elle-meme) ; (c) `target_ref` EST deja
    tile-domain (la cible du message est une entite-TUILE, cf. `abilityTargets` live `kind=tile`), donc
    le `Tiles(target@0x178)` du natif est lui aussi l'identite."""
    ring = SurroundingTiles(target_ref, Const(1), include_center=False)
    cnt = Count(Enemies(Units(death_on_the_wind_get_tiles_in_line(target_ref, Subject(), nr_of_tiles))))
    best = PickFirstN(SortByFormula(ring, cnt, ascending=False), 1)
    line = death_on_the_wind_get_tiles_in_line(target_ref, best, nr_of_tiles)
    return Union(target_ref, line)


def death_on_the_wind_tree(target_ref, nr_of_tiles: int, profile: str):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$ExecuteBehaviour`
    (MIRROR 1:1) :

        ( InformList(0xc1, tiles) & Foreach(<ennemis des tuiles>, AttackWithAbilityDamage(...)) )
        & AddEffect(1257, source = caster, targets = Alive(<ennemis>), duree = Direct(1))

    - `InformList` = notification du bus de messages (aucune mutation) -> non porte, comme `Inform`.
    - `Cache(GetMachineAttackTiles())` : le natif MEMOISE les tuiles ; le port re-utilise l'instance de
      noeud `Cache` pour les DEUX consommateurs (le Foreach d'attaque et l'`Alive` de la pose d'effet),
      donc la ligne est resolue UNE fois — necessaire parce que l'attaque peut TUER (un mort quitte sa
      tuile -> un recalcul rendrait un ensemble different).
    - `Alive(enemies)` : seuls les SURVIVANTS de la salve recoivent l'effet (`Alive` est re-evalue
      APRES les attaques, sur le meme `Cache` d'unites).
    - duree = `dsl+0xc0` = le noeud constant `Direct(1)` (#98) : deja en TOURS, PAS un `TurnsFromRounds`.
    - `native_factory="ability"` : le natif compose `AbilityDamage` + `Attack` = exactement ce que
      `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` construit."""
    tiles = Cache(death_on_the_wind_machine_attack_tiles(target_ref, nr_of_tiles))
    enemies = Cache(Enemies(Units(tiles)))
    attack = Foreach(enemies, AttackWithAttackDamage(
        Subject(), DEATH_ON_THE_WIND_ID, profile, is_melee=False, native_factory="ability",
        ability_type=int(ActiveAbilityType.DeathOnTheWind)))
    buff = AddEffect(DOTW_EXTRA_PCT_DAMAGE, EffectType.DeathOnTheWind_ExtraPctDamage.name,
                     Alive(enemies), duration_rounds=None, duration_turns=1)
    return op_and(attack, buff)


class DeathOnTheWindAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$ExecuteBehaviour`
    (id 1213, `darkaStormSpeeder` — Storm Speeder, Dark Angels, MACHINE OF WAR) — cf. le bloc ci-dessus.

    Kit gameconfig 1213 : `damageProfile=HeavyRound` (PiercingRatio 55), `nrOfHits=6`, `nrOfTiles=3`,
    `initialCooldownTurns =1`, `munitionsCost =1`, `minDmg`/`maxDmg` (rarity-affected), `extraDmgPct`
    (magnitude de l'effet 1257, consommee par l'EFFET pas par ce behaviour).

    OBSERVABLE : `nrOfHits` coups `HeavyRound` sur CHAQUE ennemi des `nrOfTiles` hexes de la ligne droite
    partant de la tuile de la cible dans la direction qui aligne le plus d'ennemis ; puis
    `DeathOnTheWind_ExtraPctDamage` (1257, 1 tour) sur les SURVIVANTS."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.DeathOnTheWind)   # 1213
    ABILITY_ID = DEATH_ON_THE_WIND_ID

    # GATE DE CIBLE (#115) — forme (A) LITTERAL DIRECT.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, 0, &statsFromClass, 1, 0x40080042, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 0, 0)
    # Decomposition (`TargetingRule`) :
    #     0x2        TargetMatchesDynamicRule -> consulte `get_dynamic_invalid_target_reason`.
    #     0x40       TargetIsTile             -> PORTE (branche `GetMainTile` + `IsWalkable`).
    #     0x80000    TargetTileHasEnemyUnit   -> **PORTE depuis #249**. Il est evalue AVANT le bit 0x2
    #                                            dans la cascade native, donc une cible ALLIEE rompt
    #                                            ICI (`0x80000`) et n'atteint jamais la regle dynamique.
    #     0x40000000 AllowNullCasterTile      -> PERMISSIF (le caster est une MACHINE OF WAR : sans ce
    #                                            bit, `GetInvalidCasterReason` refuserait un caster aux
    #                                            `casterTiles` vides).
    # TROU DECLARE sur le bit 0x2 : le natif surcharge bien la regle
    # (`DeathOnTheWindAbility$$GetDynamicInvalidTargetReason` = « la cible doit avoir DEJA recu >= 1
    # attaque ce tour », `EntityExtensions.GetNumAttacksReceivedThisTurn(unit) != 0`), mais elle N'EST
    # PAS portee : `UnitComponent.times_attacked_this_turn` n'est PAS seede par `load_state` (le RPC ne
    # l'expose pas) -> sur un etat CHARGE il vaut 0 pour tout le monde, et la porter refuserait des
    # cibles que le natif ACCEPTE (regression exactement interdite). Le defaut de base (0) laisse donc
    # la regle permissive, comme pour toute regle non portee. Point d'ancrage pour la fermer : exposer
    # `GetNumAttacksReceivedThisTurn` dans `combatSnapshot`/`decisionView`.
    # PORTEE (#241) : `range = TargetingRange` statique `+0x48` = `useWholeBoard` -> le
    # filtre statique NE TESTE PAS la portee (`forceMeleeTarget = False`, jamais consulte).
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsTile
        | TR.TargetTileHasEnemyUnit
        | TR.AllowNullCasterTile
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # `target@0x178` = une entite-TUILE (`abilityTargets` live : `kind=tile` -- la tuile de l'ennemi
        # DEJA attaque ce tour). On accepte aussi une entite-UNITE (robustesse harnais) via sa MainTile.
        tile_id = _resolve_target_tile(state, target_id)
        if tile_id is None:
            return None
        n_tiles = int(ability_var(self.ABILITY_ID, "nrOfTiles", is_constant=True) or 0)
        profile = _ability_profile(self.ABILITY_ID, "damageProfile")
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id)
        death_on_the_wind_tree(FixedTileIds([tile_id]), n_tiles, profile).execute(entities, ectx)
        hits = [{"target": p["target"], "attack": p["attack"]}
                for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        buffed = [p["target"] for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": DEATH_ON_THE_WIND_ID, "caster": caster_id, "tile": tile_id,
                "nrOfTiles": n_tiles, "hits": hits, "buffed": buffed, "dsl": True}


# =================================================================================================== #
# Hailstrike (1214, `darkaStormSpeeder` — Storm Speeder, MACHINE OF WAR) — case #117.
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.HailstrikeAbility$$ExecuteBehaviour` (MIRROR INTEGRAL —
# le behaviour de cast n'est QUE la pose d'effet, patron « MoW effect-poser », cf. case-90) :
#   rounds = GetNumberConstant(config@0x60, 0x45 = nrOfRounds)
#   Execute( AddEffect(0x5e5 = 1509 Hailstrike, AbilityStateReference,
#                      source = caster@0x160, targets = target@0x178, TurnsFromRounds(rounds)) )
#
# La PHASE 2 vit ailleurs (portee separement) :
#   * `IdunBattle.Entities.Effects.Loki.Hailstrike_ExtraPierceEffect$$CreatePiercingBonusForAttack` =
#     `EffectBonus.ForPiercing( OwnerIsCaster & (IsRangedAttack | IsOverwatchAttack),
#                               ConfigVar(0x3f = extraPierceRatio) )`  -> effects/loki/extra_damage.py
#   * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Hailstrike_AttackAbility` (On(9) + attaque de la
#     MACHINE sur la meme cible) -> runner/operations/triggers/loki/hailstrike.py
# =================================================================================================== #

HAILSTRIKE_ID = "Hailstrike"
HAILSTRIKE_EFFECT = int(EffectType.Hailstrike)            # 0x5e5 = 1509


def hailstrike_tree(target_ref, duration_turns: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.HailstrikeAbility$$ExecuteBehaviour`
    (MIRROR 1:1) : `AddEffect(1509 Hailstrike, source = caster@0x160, targets = target@0x178,
    TurnsFromRounds(nrOfRounds))`. `duration_turns` = `TurnsFromRounds(...)` DEJA converti par la classe
    d'ability (`convert_rounds_to_turns`) -> passe tel quel (le natif met la valeur convertie dans les
    options, `AddEffectOperation` ne la reconvertit pas).

    `scale_from_source=True` = le PORT de l'`AbilityStateReference` du 2e argument natif (case-117
    phase 2) : la magnitude de l'effet 1509 est `ConfigVar(0x3f = extraPierceRatio,
    GetAbilityState(effect), config@0x60)`, resolue contre l'etat d'ability de la **SOURCE**
    (la Storm Speeder) et NON du porteur. Sans ce flag, l'effet materialise portait le niveau de
    l'ALLIE buffe -> mauvaise entree de la courbe `extraPierceRatio` (10 / 12 / 15)."""
    return AddEffect(HAILSTRIKE_EFFECT, EffectType.Hailstrike.name, target_ref,
                     duration_rounds=None, duration_turns=duration_turns, scale_from_source=True)


class HailstrikeAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HailstrikeAbility$$ExecuteBehaviour`
    (id 1214, `darkaStormSpeeder` — Storm Speeder, Dark Angels, MACHINE OF WAR).

    Kit gameconfig 1214 : `damageProfile=Projectile` (PiercingRatio 15), `nrOfHits=3`, `nrOfRounds=1`,
    `minDmg`/`maxDmg` (rarity-affected, consommes par l'ability TRIGGERED de phase 2),
    `extraPierceRatio` (magnitude de l'effet 1509), `attackRangeType=Ranged`.

    CIBLE = un ALLIE sur le plateau. Le cast pose `Hailstrike` (1509) pour `nrOfRounds` round(s) ; l'effet
    donne `+extraPierceRatio` de percage aux attaques RANGED/OVERWATCH du porteur et arme l'ability
    triggered `Hailstrike_Attack` (la MoW attaque la meme cible, `nrOfHits` coups `Projectile`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Hailstrike)      # 1214
    ABILITY_ID = HAILSTRIKE_ID

    # GATE DE CIBLE (#115) — forme (A) LITTERAL DIRECT.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.HailstrikeAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, 0, &statsFromClass, 1, 0x200240000400, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x400            TargetIsFriendly     -> PORTE. C'est le SEUL masque du lot qui refuse dans
    #                                              l'AUTRE sens : Hailstrike se lance sur un ALLIE, un
    #                                              ENNEMI est refuse. Le caster etant une MACHINE, le
    #                                              natif prend la branche `IsMachine(caster)` du bit 10
    #                                              (`battleQuery.<slot 0x90>(caster, target)`) qui tombe
    #                                              sur le meme predicat d'equipe que `UnitsAreFriendly`.
    #     0x40000000       AllowNullCasterTile  -> PERMISSIF (caster = MACHINE OF WAR).
    #     0x200000000      TargetIsNotAnObject  -> NON PORTE (`HasTrait(cible, 0xd)` INTERDIT).
    #     0x200000000000   TargetIsUnit         -> non teste par les DEUX etages du gate
    #                                              (`GetInvalidCasterReason` / `GetInvalidTargetReason`
    #                                              7 args ne lisent jamais ce bit) : c'est le CODE DE
    #                                              RAISON que rend le filtre quand la cible n'a pas
    #                                              d'unite, contrainte INCONDITIONNELLE. Declaratif
    #                                              dans le masque -> rien a porter.
    # PORTEE (#241) : `TargetingRange` statique `+0x48` = `useWholeBoard` -> aucun test de
    # portee.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetIsFriendly
        | TR.AllowNullCasterTile
        | TR.TargetIsNotAnObject
        | TR.TargetIsUnit
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(target_id) is None:
            return None
        rounds = int(ability_var(self.ABILITY_ID, "nrOfRounds", is_constant=True) or 0)
        turns = convert_rounds_to_turns(state, rounds)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        hailstrike_tree(Target(), turns).execute(entities, ectx)
        posed = [p["target"] for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": HAILSTRIKE_ID, "caster": caster_id, "target": target_id,
                "rounds": rounds, "turns": turns, "posed": posed, "dsl": True}


# =====================================================================================================
# Supercharge (1103, darkaHellblaster « Sarquael ») -- #112
# =====================================================================================================

def _supercharge_behind(state: "State", caster_id: int, target_id: int) -> list:
    """COLLAPSE du selecteur `PickRandomly(UnitsDirectlyBehind(caster@0x160, target@0x178), 2)` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SuperchargeAbility$$ExecuteBehaviour`.

    Le natif construit UN SEUL noeud selecteur (`uVar12`) et le passe aux DEUX consommateurs : le
    `TargetsSelector.op_Addition(target@0x178, uVar12)` de l'`AddEffect` ET le selecteur de cibles du
    volet SPLASH. On le resout UNE fois ici et on l'injecte en `UnitSet` aux deux -- doctrine de collapse
    S (slice-18/19). EXACT pour <=2 candidats sur le SET (`_pick_randomly_n` rend tout le pool) -- et depuis
    #130 la CONSO rng du pick est exacte aussi (`min(len(pool),2)` tirages) ; c'est la lecture i2
    (« these units » = les memes que celles attaquees).
    RESIDU (>2 candidats derriere la cible) : le natif re-evalue son `PickRandomly` a chaque `Select`
    (potentiellement 2 sets differents + 2 series de tirages) ; le port n'en fait qu'un.

    `UnitsDirectlyBehind` = le noeud DEJA porte (mirror `IdunBattleLogic.Entities.DSLFactory$$
    UnitsDirectlyBehind`) ; `PickRandomly` = `_pick_randomly_n` (== PlasmaCannon/Fragstorm).
    R28-1 (2026-07-27) : le pool est passe au tirage dans l'ORDRE SOURCE (enumeration CUBE de
    `SurroundingTiles(target,1,1)`, portee par le noeud) et NON id-trie -- `PickRandomAmountSelector$$Select`
    ne trie jamais son `candidates` ; l'`OrderBy` natif est celui d'`AttackBehaviour$$Execute`, APRES la
    resolution du selecteur, et il vit deja dans la feuille (`multi=True`)."""
    from .loki import _pick_randomly_n
    ents = entities_from_state(state, caster_id, target_id)
    cands = [u for u in UnitsDirectlyBehind().evaluate(ents) if u.get("id") is not None]
    return _pick_randomly_n(state, cands, 2)


def supercharge_tree(behind: list):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.SuperchargeAbility$$ExecuteBehaviour`
    (id 1103, darkaHellblaster -- MIRROR du DECOMPILE) :

        primary   = AActiveAbility.MinMaxDamage(this)     # RandomAmount(ConfigVar 0xc, ConfigVar 0xd)
        secondary = AActiveAbility.MinMaxDamage2(this)    # RandomAmount(ConfigVar 0x36, ConfigVar 0x37)
        profile   = AActiveAbility.GetDamageProfile(this)                             # Plasma
        hits      = GetHits(this)   [corps FOLDE affiche `ArmoriumCherubAbility$$GetHits`]
                                                          # = GetNumberConstant(0x2f) = nrOfHits
        hits2     = GetHitsToSecondaryTargets(this)  [corps FOLDE affiche
                    `BringerOfDespairAbility$$GetHitsToBonusTarget`]
                                                          # = GetNumberConstant(0x32) = nrOfHits_2
        behind    = PickRandomly( UnitsDirectlyBehind(caster@0x160, target@0x178), 2 )
        ExecuteAtomic(
          op_BitwiseAnd(
            op_BitwiseAnd(
              AddEffect(0x4b8 Supercharge_ExtraPiercing, stateRef, source=caster@0x160,
                        target = TargetsSelector.op_Addition(target@0x178, behind),
                        TurnsFromRounds(1)),                                          # [1] EFFET
              AttackWithAttackDamage(caster, target@0x178, primary,   Plasma, hits) ), # [2] MAIN
            AttackWithAttackDamage(caster, behind,        secondary, Plasma, hits2) ), # [3] SPLASH
          0x2a)

    ORDRE : l'`AddEffect` est le PREMIER volet -> le bonus de percage est POSE AVANT les deux attaques,
    donc les hits de Supercharge EUX-MEMES en beneficient (i2 : « ... all with +35% pierce ratio »).
    CONFIRME LIVE (#112, MC1_67 au contact) : les 3 groupes `Supercharge_ExtraPiercing` (cible +
    2 unites derriere, `Effect_RemainingTurns=2`) precedent les 2 groupes de degat dans la cascade.
    Les DEUX volets d'attaque appellent `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`
    (LU au decompile, pas au juge du template) -> `native_factory="attack"` = 2 tirages/coup a cc=0
    (piege rngcrit-1202). Config 1103 : nrOfHits=1, nrOfHits_2=1, damageProfile=Plasma, range=3."""
    behind_sel = UnitSet(behind)
    # [1] `AddEffect(0x4b8, ..., op_Addition(target, behind), TurnsFromRounds(1))` -- +extraPierceRatio
    #     Plasma sur la cible ET les unites derriere, jusqu'au debut du prochain tour du caster.
    #     `scale_from_source=True` : la magnitude est un `ConfigVar(0x3f)` resolu contre l'AbilityState
    #     de la SOURCE (`BaseEffect.GetAbilityState`, cf. `Supercharge_ExtraPiercingEffect$$
    #     CreatePiercingBonusForAttack`).
    eff = AddEffect(SUPERCHARGE_EXTRA_PIERCING, "Supercharge_ExtraPiercing",
                    Union(Target(), behind_sel), duration_rounds=1, scale_from_source=True)
    # [2] MAIN : minDmg/maxDmg, nrOfHits, Plasma, RANGED (range 3).
    main = AttackWithAttackDamage(Target(), "Supercharge", "Plasma", is_melee=False,
                                  native_factory="attack")
    # [3] SPLASH : minDmg_2/maxDmg_2 (MinMaxDamage2) + nrOfHits_2, MEME profil Plasma.
    splash = AttackWithAttackDamage(behind_sel, "Supercharge", "Plasma", is_melee=False,
                                    min_key="minDmg_2", max_key="maxDmg_2", hits_key="nrOfHits_2",
                                    multi=True, native_factory="attack")
    return AtomicGroup(op_and(op_and(eff, main), splash))


class SuperchargeAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SuperchargeAbility$$ExecuteBehaviour` (id 1103,
    darkaHellblaster « Sarquael » ; faction DarkAngels). Cast RANGED (range 3, cible ennemie).

    i2 : « Deals 1x <minDmg-maxDmg> Plasma Damage to a target enemy within range 3 and 1x
    <minDmg_2-maxDmg_2> Plasma Damage to up to two enemies in adjacent hexes behind the target, all with
    +<extraPierceRatio>% pierce ratio. Until the beginning of Sarquael's next turn, any further hits that
    deal Plasma Damage against these units also have +<extraPierceRatio>% pierce ratio. »

    `execute_behaviour` DELEGUE a `supercharge_tree()` (mirror 1:1). Le +percage est porte par l'EFFET
    `Supercharge_ExtraPiercing` (1208, `entities/effects/loki/damage_reduction.py`) : `EffectBonus.
    ForPiercing(DamageProfileIs(Plasma) & OwnerIsTarget, ConfigVar(0x3f=extraPierceRatio))` -- l'effet vit
    sur la VICTIME et bonifie le percage de QUI l'attaque en Plasma (canal DEFENSEUR, fusionne dans
    `mods.extra_pierce` par `AttackDamageOperation._apply_defender_flat_reductions`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Supercharge)  # 1103
    ABILITY_ID = "Supercharge"

    # GATE DE CIBLE (#115) — forme (B) PRESET COPIE (MEME preset que PlasmaCannon).
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.SuperchargeAbility$$.ctor` :
    #     opts <- <TargetingOptions statics>+0x140 .. +0x17f    (copie des 0x40 octets, aucun flag ajoute)
    #     AActiveAbility..ctor(this, &opts, 0, 0)
    # `TargetingOptions$$.cctor` : `*(statics+0x168) = 0x4002` (= `<preset>+0x28` = `Rules`).
    #     0x2    TargetMatchesDynamicRule -> pas de `GetDynamicInvalidTargetReason` natif pour 1103 ->
    #            defaut 0 (mirror exact).
    #     0x4000 TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie).
    # PORTEE (#241) : meme preset `+0x140` que PlasmaCannon -> `useRangeFromConfig`
    # (`Supercharge.constants.range` = 3) + `forceMeleeTarget = True`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        behind = _supercharge_behind(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        supercharge_tree(behind).execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        return {"ability": "Supercharge", "caster": caster_id, "target": target_id,
                "main_attack": main,
                "splash": [{"target": p["target"], "attack": p["attack"]}
                           for p in atks if p.get("target") != target_id],
                "behind": [u["id"] for u in behind],
                "pierce_effect": [p["target"] for n, p in ectx.emitted if n == "AddEffect"],
                "dsl": True}


# =====================================================================================================
# ExemplarOfHate (1140, darkaAsmodai « Asmodai ») -- #112
# =====================================================================================================

def _exemplar_capped_attack_vars(state: "State", caster_id: int) -> tuple:
    """COLLAPSE des deux feuilles V `ConfigVar(0xd=maxDmg)` / `ConfigVar(0x4a=dmgPct)` que
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfHateAbility$$GetAttackDamage` passe a
    `PercentageOfAttackCappedAtMax` (doctrine slice-23 : une formule `ConfigVar` sans consommateur
    dynamique est calculee imperativement via `ability_var` et passee en SCALAIRE).

    Les DEUX `ConfigVar` sont resolus contre la config de l'ABILITY QUI S'EXECUTE (`ability+0x60`) --
    donc contre le niveau + le multiplier de rarete du CASTER (Asmodai), PAS de l'allie qui frappera.
    Seule l'ATTACK du sujet (l'attaquant) est per-unite, et elle vit dans le noeud `StatAmount` de
    l'arbre. Rend `(cap, pct)`.

    VALIDE LIVE (#112) : Asmodai lvl50 mult180 -> cap = maxDmg = 5983, pct = dmgPct = 100 ;
    `UnitStats_Attack_Override` mesure = 2008 = min(5983, round(Attack_CURRENT 2008 x 100 / 100))."""
    e = state.get_entity(caster_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    lvl = getattr(sc.ctx, "active_ability_level", None) if sc is not None else None
    mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100) if sc is not None else 100
    cap = ability_var("ExemplarOfHate", "maxDmg", lvl, multiplier_pct=mult)   # rarity-scale
    pct = ability_var("ExemplarOfHate", "dmgPct", lvl, multiplier_pct=mult)   # hors rarity-scale
    return (int(cap or 0), int(pct or 0))


def sort_attackers_by_damage_prediction_key(pred_min, pred_avg, pred_max) -> int:
    """`IdunBattle.Entities.Selectors.SortAttackersByDamagePredictionSelector.u003Cu003Ec__DisplayClass8_0$$u003CSelectu003Eb__0`
    -- la CLE que `Select` passe a `OrderByDescending`. Mirror 1:1 des trois lignes finales du
    lambda, LUES au decompile (#344-r2) :

        if (DamagePredictionResult$$get_WillBeKill(predMax))  return 0x7fffffff;
        if (DamagePredictionResult$$get_MightBeKill(predMin)) return 0x7ffffffe;
        return MinMaxDamage$$Avg(predAvg + 0x60);      # +0x60 = `TotalDamage`

    Les TROIS arguments sont trois `DamagePredictionResult` DISTINCTS, batis avec les bornes
    `CalculateMin` / `CalculateAverage` / `CalculateMax` (slots 2 / 4 / 3 d'`IAmountFormula`) du
    noeud de degat -- l'appariement borne <-> test est ASYMETRIQUE et c'est celui du natif :
    le sure-kill se lit sur la borne HAUTE, le kill possible sur la borne BASSE.

    Fonction SEPAREE parce que le natif en fait une : c'est le seul point ou l'appariement est
    verifiable sans monter d'etat.

    #372 -- LE RESIDU « borne PERMISSIVE » DE #344-r2 EST FERME, ET LA REPONSE EST « INERTE ICI ».
    `get_WillBeKill` sort en tete sur `CannotBeGuaranteedKilled@0x89` ; ce champ existe desormais
    dans le port (`DamagePredictionResult.cannot_be_guaranteed_killed`) et `will_be_kill` le lit.
    Sur CE site il vaut structurellement False, et c'est LU, pas suppose : le lambda natif appelle
    `IBattleQuery` slot 0x28 = `BattleQuery$$GetMultiHitAttackPrediction` (7 arguments : attacker,
    target, attackerPosition, ability, damage, damageProfile, hits -- la meme signature que
    `ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` emprunte), or cette methode
    commence par `memset(result, 0, 0xa0)` puis delegue au slot 0xb (`PredictAttack`). Le SEUL
    ecrivain du flag est `DamagePrediction$$PredictNormalAttack` (slot 9), atteint par
    `GetNormalAttackPrediction` -- que ce lambda n'emprunte PAS. `DamagePredictionResult$$Add` ne
    fusionne aucun flag booleen, donc le cumul des coups ne peut pas le rallumer non plus.
    La borne `will_be_kill` de ce site n'etait donc PAS permissive : elle etait exacte, sans
    preuve. La preuve est faite, et la garde `test_372_*` la verrouille dans les DEUX sens (le
    gate mord quand le flag est pose ; il ne mord pas sur la voie multi-hit)."""
    if pred_max.will_be_kill():
        return 0x7fffffff
    if pred_min.might_be_kill():
        return 0x7ffffffe
    # `IdunBattle.Core.Services.MinMaxDamage$$Avg` = `Fix64.Round(., 0)` demi-vers-le-PAIR. #344
    # avait corrige l'ARRONDI (c'etait une troncature) ; #344-r2 corrige la SOURCE -- le port
    # moyennait `raw_health_damage` (= `DefaultScenario.Damage.HealthDamage`, @0x1c/@0x20), le natif
    # moyenne `TotalDamage` (@0x60). C'est une CLE DE TRI : un ecart d'une unite renverse un ordre.
    return min_max_avg(pred_avg.total_damage.min, pred_avg.total_damage.max)


def _exemplar_of_hate_attackers(state: "State", caster_id: int, target_id: int,
                                cap: int, pct: int) -> list:
    """COLLAPSE du selecteur AI-target `IdunBattleLogic.Entities.Abilities.Active.Loki.
    ExemplarOfHateAbility$$GetAttacker` (kind S LOURD -- meme doctrine que `_finaljustice_target`).
    Chaine native LUE :

        possible = UnitsWhoCanAttack(
                     UnitsFromFaction( Friends(caster@0x160, AllUnits@0x80 + caster@0x160), 10 ),
                     target@0x178 )                       # == `...$$GetPossibleAttackers`
        attacker = First( SortAttackersByDamagePredictionSelector(
                            possible, target@0x178, UnitNormalAttackType(Subject@0x180),
                            GetAttackDamage(...), AttackHits(Subject, target),
                            NormalAttackDamageProfile(Subject, target) ), 1 )

    - `IdunBattle.Entities.Selectors.UnitsWhoCanAttackTargetSelector$$Select` garde un candidat ssi
      `GetBrokenTargetingRules(unit, unit.MainTile, target, unit.NormalAttackType).IsValid` (aucune regle
      de ciblage cassee DEPUIS SA TUILE COURANTE). Port : unite VIVANTE dont la portee d'arme maximale
      couvre la distance hex a la cible -- la regle DOMINANTE ; LoS/obscurcissement/hauteur = RESIDU flagge.
    - `IdunBattle.Entities.Selectors.SortAttackersByDamagePredictionSelector$$Select` ->
      `OrderByDescending(key)` avec, pour cle, le lambda
      `SortAttackersByDamagePredictionSelector.u003Cu003Ec__DisplayClass8_0$$u003CSelectu003Eb__0`.
      STRUCTURE LUE (#344-r2) -- le lambda batit TROIS `DamagePredictionResult`, une par borne du
      noeud de degat :

          hits    = damage@+0x40 . slot 1                       # `Calculate`
          dMin    = damage@+0x30 . slot 2                       # `CalculateMin`
          dAvg    = damage@+0x30 . slot 4                       # `CalculateAverage`
          dMax    = damage@+0x30 . slot 3                       # `CalculateMax`
          predMin = query@+0x48 . slot 0x28 (attacker, target, pos, abilityType, dMin, profile, hits)
          predAvg = idem avec dAvg ; predMax = idem avec dMax
          key     = 0x7fffffff  si predMax.WillBeKill
                    0x7ffffffe  si predMin.MightBeKill
                    MinMaxDamage$$Avg(predAvg + 0x60)  sinon

      Le mapping des slots d'`IAmountFormula` est DERIVE du binaire, pas herite :
      `IdunBattle.Entities.Formulas.PercentageOf$$Calculate` appelle le slot 1 sur ses deux enfants,
      `$$CalculateMin` le slot 2, `$$CalculateMax` le slot 3 -> le slot 4 restant est
      `CalculateAverage` (seul membre d'`IAmountFormula` non encore attribue, et le seul dont
      `IdunBattle.DSL.AAmountFormula` porte un corps).
      `predAvg + 0x60` = le champ `TotalDamage` (table d'offsets NOMMEE de
      `frida/hooks/game/damage-prediction.ts`), PAS `DefaultScenario.Damage.HealthDamage` (@0x1c/@0x20,
      les bornes que lisent `get_WillBeKill` / `get_MightBeKill`) ni `AccurateHealthDamage` (@0x40).
      `TotalDamage` = bloque-par-bouclier NON cape + degat sante pre-scenario : il DIVERGE de la sante
      des que la cible porte un bouclier. Le port moyennait `raw_health_damage` -- c'etait le bug.

    - Les TROIS bornes COINCIDENT pour CE porteur, et c'est DEMONTRE (pas suppose) : le noeud de degat
      est `IdunBattle.Entities.Formulas.MinAmount` (bati par
      `IdunBattleLogic.Entities.DSLFormulas$$PercentageOfAttackCappedAtMax`), qui derive de
      `IdunBattle.DSL.ASimpleAmountFormula` -- et `ASimpleAmountFormula$$CalculateMax` est
      `return Calculate(...)` (slot vtable +0x1d8), `CalculateMin` partageant ce corps (dedupe).
      `AAmountFormula$$CalculateAverage` rend alors `(v + v) / 2 == v`. Le sur-cout des trois appels
      est donc nul en resultat -- la structure est portee parce qu'elle est la VERITE du natif, pas
      parce qu'un montage la separe. `SortAttackersByDamagePredictionSelector` n'a qu'UN appelant
      (`ExemplarOfHateAbility$$GetAttacker`, xrefs LUES) : aucun autre noeud de degat ne l'emprunte.

      Port : la prediction est batie comme celle de `_finaljustice_target` (`get_attack_prediction`
      PRE-ARMURE armor=0/pierce=100, profil 0 -- cf. l'en-tete de `services/damage_prediction`) mais
      avec `initial_damage` = l'OVERRIDE (le natif passe justement `GetAttackDamage()` comme noeud de
      degat au selecteur de tri) et `target_shield` = le bouclier COURANT de la cible, sans lequel
      `TotalDamage` serait structurellement egal a `raw_health_damage` et la correction ci-dessus
      inobservable. `OrderByDescending` LINQ est STABLE -> tie-break = ordre source, approxime par id
      croissant.

    RESIDU NOMME (hors perimetre #344-r2) : le port ne fournit a la prediction ni l'armure/le percage
    reels ni le `defender_block_amount` de la cible -- donc `block_raw_min` reste `None` et
    `will_be_kill` retombe sur le scalaire `raw_health_damage.min`, exactement comme le fallback natif
    "liste `BlockScenarios` vide". (#372 : le gate `CannotBeGuaranteedKilled@0x89` EXISTE desormais
    dans le port et vaut structurellement False sur cette voie -- cf.
    `sort_attackers_by_damage_prediction_key`. Le residu restant est donc le seul `block_raw_min`.)

    Rend la liste ORDONNEE (le `First(...,1)` est applique par l'appelant)."""
    from ...ai.action_generators import _faction
    import gameconfig as GC
    ce = state.get_entity(caster_id)
    te = state.get_entity(target_id)
    coc = ce.get_component(OwnerComponent) if ce is not None else None
    tpc = te.get_component(PositionComponent) if te is not None else None
    thc = te.get_component(HealthComponent) if te is not None else None
    if coc is None or tpc is None:
        return []
    tpos = (tpc.col, tpc.row)
    thp = int(thc.hp) if (thc is not None and thc.hp is not None) else 0
    # `TotalDamage@0x60` = bloque-par-bouclier + degat sante : sans le bouclier COURANT de la cible
    # (`IdunBattle.Entities.Components.ShieldComponent$$GetTotalShield`), le champ que le natif
    # moyenne serait indiscernable de `raw_health_damage`.
    tshc = te.get_component(ShieldComponent) if te is not None else None
    tshield = int(tshc.get_total_shield()) if tshc is not None else 0
    scored = []
    for uid, e in sorted(state.entities.items()):
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        sc = e.get_component(StatsComponent)
        if uc is None or oc is None or pc is None or sc is None:
            continue
        if oc.team != coc.team or not uc.alive:            # Friends(caster, AllUnits + caster)
            continue
        if _faction(uc.visual_id) != "DarkAngels":         # UnitsFromFaction(..., 10 = DarkAngels)
            continue
        # `UnitsWhoCanAttack` : la cible est-elle a portee d'UNE de ses armes depuis sa tuile courante ?
        dist = hexgeo.distance((pc.col, pc.row), tpos)
        rng = max([int(w.get("Range") or 1)
                   for w in ((GC.unit(uc.visual_id) or {}).get("weapons") or [])] or [1])
        if dist > rng:
            continue
        # Montant de l'override (== le noeud `GetAttackDamage` que le natif passe au selecteur de tri).
        atk = int(sc.ctx.stat(StatType.ATTACK))
        override = min(int(cap), _pct_of(atk, pct)) if cap else _pct_of(atk, pct)
        ahc = e.get_component(HealthComponent)
        _pierce, is_ranged, whits = select_weapon_pierce(sc.ctx, dist)
        mods, active = attacker_modifiers(state, uid, ahc.hp if ahc else None, is_ranged=is_ranged)
        hits = max(1, whits + sc.ctx.stat(StatType.EXTRA_HITS) + hits_bonus_from_effects(active))
        # Slots 2 / 4 / 3 d'`IAmountFormula` sur le noeud de degat `GetAttackDamage()`. Ce noeud est
        # une `ASimpleAmountFormula` (cf. docstring) : ses trois bornes retombent sur `Calculate`,
        # donc les trois montants sont EGAUX ici. On les NOMME quand meme, parce que ce sont trois
        # evaluations distinctes cote natif et que le collapse doit rester lisible comme tel.
        dmg_min = dmg_avg = dmg_max = override

        def _predict(amount: int):
            return get_attack_prediction(
                target_current_health=thp, initial_damage=amount, hits=hits,
                profile_type=0, armor=0, pierce_pct=100, mods=mods, spread_pct=20,
                target_shield=tshield, attacker_effects=active)   # PRE-ARMURE (== `_finaljustice_target`)
        key = sort_attackers_by_damage_prediction_key(
            _predict(dmg_min), _predict(dmg_avg), _predict(dmg_max))
        scored.append((uid, key))
    scored.sort(key=lambda t: (-t[1], t[0]))               # OrderByDescending(key), tie-break id (stable)
    return [uid for uid, _k in scored]


def _pct_of(value: int, pct: int) -> int:
    """`PercentageOf(StatAmount(unit, ATTACK, part), pct, mode 0)` — mirror IMPERATIF (arrondi Fix64
    half-to-even, `AAmountFormula.RoundFix64Result` mode 0) utilise UNIQUEMENT pour la CLE DE TRI du
    collapse `SortAttackersByDamagePrediction`. L'arbre, lui, porte le VRAI noeud
    `percentage_of_attack_capped_at_max` (evalue a l'execution sur l'attaquant lie au slot sujet)."""
    from fractions import Fraction
    return _round_fix64(Fraction(int(value) * int(pct), 100), 0) if pct else 0


def exemplar_of_hate_tree(attacker: list, cap: int, pct: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfHateAbility$$ExecuteBehaviour`
    (id 1140, darkaAsmodai -- MIRROR du DECOMPILE, ordre des `op_BitwiseAnd` LU dans le decompile) :

        attacker = Cache( GetAttacker(entities), 1 )     # cf. `_exemplar_of_hate_attackers`
        op_BitwiseAnd(
          AddEffect(0x50d ExemplarOfHate_Target, stateRef, caster@0x160, target@0x178,
                    TurnsFromRounds(2)),                                                  # [1] toujours
          If( HasTrait(target@0x178, 0x7ea = Chaos),
              op_BitwiseAnd(
                AddEffect(0x429 Pinned, stateRef, caster@0x160, target@0x178, <duree ZERO>),   # [2]
                op_BitwiseAnd(
                  op_BitwiseAnd(
                    AddStatOverrideEffect(attacker, 0x510, stat=0 ATTACK, GetAttackDamage(), 0, 1),  # [3]
                    UseActiveAbility(attacker, target@0x178,
                                     UnitNormalAttackType(attacker), <options>) ),                   # [4]
                  RemoveEffect(attacker, Nullable(0x510)) ) ) )                                      # [5]

    i2 : « Targets an enemy on the battlefield. For this round and the next, all friendly units deal
    +<extraDmg> Damage against that enemy with melee or Overwatch attacks. If that enemy is Chaos, it
    gets Suppressed and Asmodai or another friendly Dark Angel immediately performs a normal attack
    against the target, dealing <dmgPct>% of its own damage, to a maximum of <maxDmg> Damage per hit. »

    - [1] est INCONDITIONNEL (hors du `If`) : le debuff 2 rounds tombe meme sur une cible non-Chaos
      (MESURE LIVE #112 : cible Chaos -> `ExemplarOfHate_Target` `Effect_RemainingTurns=4` = 2 rounds x
      2 joueurs).
    - Le `Pinned` (0x429) est pose SANS `TurnsFromRounds` (arg duree ZERO) -> duree =
      `DefaultAmountOfRounds(0x429)` = 1 round, converti en tours par l'Operation (LIVE : `Effect_
      RemainingTurns=2`). MEME patron que CrushingClaws/SpiritLeech.
    - [3]-[5] = le triptyque override/attaque-libre/retrait, porte par l'ALLIE choisi (`attacker`).
      Le montant est le VRAI noeud `percentage_of_attack_capped_at_max(Subject@0x180, CURRENT, cap, pct)`
      -- evalue A L'EXECUTION sur l'Attack de CET allie, la feuille `AddStatOverrideEffect` liant l'unite
      courante au slot SUJET (mirror `param_3[4] = current`). Seules les deux feuilles `ConfigVar` sont
      collapsees en scalaires (`_exemplar_capped_attack_vars`, doctrine slice-23).
      LIVE : `UnitStats_Attack_Override=2008` sur Asmodai (l'attaquant elu), puis `Loki_NormalAttack`
      melee sur la cible, puis retrait de l'override (aucun `TemporaryStatOverride` residuel).

    RESIDU NOMME (hors perimetre, generique) : le gate d'IMMUNITE d'effet
    (`BaseEffect.EntityIsImmuneToEffect` + surcharges par effet) n'est PAS porte par
    `AddEffectOperation`. MESURE LIVE #112 : `Pinned` n'est PAS pose sur une cible a trait
    `TerminatorArmour` (i2 : « This unit cannot be Suppressed ») ; le port, lui, le posera."""
    a_sel = UnitSet(attacker)
    target_debuff = AddEffect(EXEMPLAR_OF_HATE_TARGET, "ExemplarOfHate_Target", Target(),
                              duration_rounds=2, scale_from_source=True)
    suppress = AddEffect(PINNED, "Pinned", Target(), duration_rounds=None)   # duree = DefaultAmountOfRounds
    amount = percentage_of_attack_capped_at_max(Subject(), Const(int(cap)), Const(int(pct)),
                                                stat_part=int(StatPart.CURRENT))  # param_3 = 0 (LU)
    override = AddStatOverrideEffect(a_sel, TEMPORARY_STAT_OVERRIDE, int(StatType.ATTACK), amount,
                                     name="TemporaryStatOverride")
    free_attack = UseActiveAbility(a_sel, Target())        # UseActiveAbility(attacker, target, normalAttack)
    clear = RemoveEffect(TEMPORARY_STAT_OVERRIDE, a_sel)
    chaos_branch = op_and(suppress, op_and(op_and(override, free_attack), clear))
    return op_and(target_debuff, If(HasGrandAlliance(Target(), CHAOS_FACTIONS), chaos_branch))


class ExemplarOfHateAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfHateAbility$$ExecuteBehaviour` (id 1140,
    darkaAsmodai « Asmodai » ; faction DarkAngels). Cast NORMAL (cible ennemie, portee illimitee).

    `execute_behaviour` DELEGUE a `exemplar_of_hate_tree()` (mirror 1:1). Les deux COLLAPSES S/V sont
    resolus AVANT l'arbre (`_exemplar_of_hate_attackers` = le selecteur AI `GetAttacker` + son `Cache` ;
    `_exemplar_capped_attack_vars` = les deux `ConfigVar` de `GetAttackDamage`), conformement a la
    doctrine slice-18/19/23. Cible non-Chaos ou aucun attaquant DarkAngels a portee -> seul le debuff
    0x50d est pose (pour une cible non-Chaos ; pour une cible Chaos sans attaquant, le `Pinned` tombe
    quand meme -- c'est le premier volet du `&` interne)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ExemplarOfHate)  # 1140
    ABILITY_ID = "ExemplarOfHate"

    # GATE DE CIBLE (#115) — forme (A) LITTERAL DIRECT.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfHateAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, 0, &statsFromClass, 1, 0x6004000, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)
    # Decomposition (`TargetingRule`) :
    #     0x4000    TargetIsEnemy      -> PORTE (refus sur soi-meme / un allie).
    #     0x6000000 AllowObscuredTarget (= AllowObscuredTargetByElevation | ...ByWalls, valeur
    #               COMPOSITE de l'enum) -> PERMISSIF : aucune contrainte de ligne de vue (coherent
    #               avec « portee illimitee » du kit 1140).
    # PORTEE (#241) : `TargetingRange` statique `+0x48` = `useWholeBoard` -> aucun test de
    # portee, ce qui CONFIRME au binaire la « portee illimitee » du kit 1140.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetIsEnemy
        | TR.AllowObscuredTargetByElevation
        | TR.AllowObscuredTargetByWalls
    ), range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        cap, pct = _exemplar_capped_attack_vars(state, caster_id)
        ranked = _exemplar_of_hate_attackers(state, caster_id, target_id, cap, pct)
        attacker = ranked[:1]                              # `IdunBattleLogic.Entities.DSLFactory$$First(., 1)`
        ectx = ExecutionContext(state=state, rng=state.rng)
        ents = entities_from_state(state, caster_id, target_id)
        att_units = [u for u in ents.units if u.get("id") in attacker]
        exemplar_of_hate_tree(att_units, cap, pct).execute(ents, ectx)
        atk = next((p for n, p in ectx.emitted if n == "UseActiveAbility"), None)
        ov = next((p for n, p in ectx.emitted if n == "AddStatOverrideEffect"), None)
        return {"ability": "ExemplarOfHate", "caster": caster_id, "target": target_id,
                "effects": [p["effect_type"] for n, p in ectx.emitted
                            if n == "AddEffect" and p.get("placed")],
                # `effects_active` = les poses qui CONTRIBUENT a l'instant de la pose (le pendant du
                # groupe d'evenement live, cf. `_placed_effect_is_active`). `effects` seul ne
                # distingue pas la pose INERTE sur une cible `TerminatorArmour` (#208/#462-r4b), et
                # l'etat FINAL ne le peut pas non plus des que la chaine TUE la cible.
                "effects_active": [p["effect_type"] for n, p in ectx.emitted
                                   if n == "AddEffect" and p.get("active")],
                "attacker": attacker[0] if attacker else None,
                "attack_override": (ov or {}).get("amount"),
                "attack": (atk or {}).get("attack"), "dsl": True}


# =====================================================================================================
# CalibaniteGreatsword (1189, darkaCompanion « Forcas ») -- #112
# =====================================================================================================

def calibanite_greatsword_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.CalibaniteGreatswordAbility$$ExecuteBehaviour`
    (id 1189, darkaCompanion -- MIRROR du DECOMPILE) :

        If( HasEffect(Self@0x148, 0x57c CalibaniteGreatswordStrike, activeOnly=0, sourceFlags=6),
            /* THEN -- posture STRIKE -> bascule SWEEP */
            op_Addition( AddEffect(0x57d Sweep, stateRef, Self@0x148, dureeNode=0),
                         RemoveStrikeEffects() ),
            /* ELSE -- posture SWEEP (ou aucune) -> bascule STRIKE ; AddStrikeEffects INLINE */
            op_Addition( op_Addition( op_Addition( AddEffect(0x57c Strike,  stateRef, Self@0x148),
                                                   AddEffect(0x591 Strike_Overwatching, ...) ),
                                       AddEffect(0x3f1 Overwatch_AutoAttack, ...) ),
                         RemoveEffect(Self@0x148, Nullable(0x57d Sweep)) ) )

    ou `...$$RemoveStrikeEffects` = `RemoveEffect(Self, 0x57c) + RemoveEffect(Self, 0x591) +
    RemoveEffect(Self, 0x3f1) + RemoveEffect(Self, 0x57e CalibaniteGreatsword_StrikeHitReduction)` et
    `...$$AddStrikeEffects` = les 3 `AddEffect` de la branche ELSE (le compilateur les a INLINEES dans
    `ExecuteBehaviour` -- corps VERIFIE identique). `AddStrikeEffects` est AUSSI le corps de la triggered
    `CalibaniteGreatsword_SetStartAbility` -> Forcas demarre la bataille en posture STRIKE.

    `activeOnly = 0` est LU au decompile (`DSLFactory$$HasEffect(dsl, unitSel, effectType, activeOnly,
    sourceFlags)` : les call-sites AnvilShield passent 1, celui-ci 0) -> `active_only=False` cote port.

    L'ability est un TOGGLE PUR : aucune attaque, aucun degat, aucun tirage RNG. Toute la mecanique
    OBSERVABLE (Sweep : les attaques normales frappent aussi les ennemis adjacents a la fois a Forcas et
    a la cible ; Strike : overwatch en fin de tour avec un coup de moins) vit dans des abilities TRIGGERED
    portees par ces effets (`CalibaniteGreatsword_NormalAttackAdditionalDamageAbility` 1316,
    `CalibaniteGreatsword_StrikeOverwatchingEffect`) -- HORS de ce port (surface triggered separee).

    Cast SELF (aucune cible requise ; `abilityTargets.fromHere` = [self]). 1189 est dans les DEUX
    inventaires `NO_END_TURN_ABILITY_TYPES` / `NO_ABILITY_USED_FLAG_ABILITY_TYPES` (base.py) -> ne termine
    pas le tour et ne pose pas le flag ActiveAbilityUsed (i2 : « This ability can be used once per turn ;
    each use switches the active Stance and does not end Forcas' turn »).

    MESURE LIVE #112 (2 casts consecutifs, runner isole MC1_67) :
      * PRE  : Forcas porte `CalibaniteGreatswordStrike` (1404) seul ;
      * cast 1 : +1405 Sweep, -1404 Strike ;
      * cast 2 (tour suivant) : +1404 Strike, -1405 Sweep.
    Les effets 0x591 et 0x3f1 n'apparaissent JAMAIS dans `decisionView.effects` -- mais ce n'est PAS une
    preuve de non-pose : le hook `frida/hooks/game/effects.ts` DROPPE toute entree dont
    `EffectComponent.IsActive @+0x5c` est nul (`readEffectsByUnit` : `if (!info.active || info.removed)
    continue`), et l'overwatch de la posture Strike ne s'active qu'EN FIN DE TOUR (i2). Le port MIRRORE
    donc le decompile (3 `AddEffect`).
    RESIDU NOMME : le port n'a pas d'`ActiveCondition` pour 0x591/0x3f1 -> ils y sont ACTIFS des le cast,
    alors que le natif les active plus tard. Consequence bornee a Forcas-en-posture-Strike : le trigger
    d'effet `Overwatch_AutoAttack` (1009) du port peut declencher un overwatch plus TOT que le natif.
    Point d'ancrage pour trancher : exposer `EffectComponent.IsActive` dans `decisionView.effects`."""
    self_sel = Caster()                                    # Self@0x148 (Owner == Caster pour un cast actif)
    to_sweep = op_add(
        AddEffect(CG_SWEEP, "CalibaniteGreatswordSweep", self_sel, duration_rounds=None),
        op_add(op_add(op_add(RemoveEffect(CG_STRIKE, self_sel),
                             RemoveEffect(CG_STRIKE_OVERWATCHING, self_sel)),
                      RemoveEffect(OVERWATCH_AUTO_ATTACK, self_sel)),
               RemoveEffect(CG_STRIKE_HIT_REDUCTION, self_sel)))
    to_strike = op_add(
        op_add(op_add(AddEffect(CG_STRIKE, "CalibaniteGreatswordStrike", self_sel, duration_rounds=None),
                      AddEffect(CG_STRIKE_OVERWATCHING, "CalibaniteGreatswordStrike_Overwatching",
                                self_sel, duration_rounds=None)),
               AddEffect(OVERWATCH_AUTO_ATTACK, "Overwatch_AutoAttack", self_sel, duration_rounds=None)),
        RemoveEffect(CG_SWEEP, self_sel))
    return If(HasEffect(self_sel, CG_STRIKE, 0, False), to_sweep, to_strike)


class CalibaniteGreatswordAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CalibaniteGreatswordAbility$$ExecuteBehaviour`
    (id 1189, darkaCompanion « Forcas » ; faction DarkAngels). TOGGLE de POSTURE Strike <-> Sweep.

    `execute_behaviour` DELEGUE a `calibanite_greatsword_tree()` (mirror 1:1). Cast SELF : `target_id`
    est ignore (le natif n'utilise que `Self@0x148`). Aucun degat -> aucun tirage RNG consomme.
    ⚠ Les constantes `damageProfile=Power` / `nrOfHits_2=3` et les variables `minDmg/maxDmg/nrOfHits` de
    la config 1189 alimentent la TRIGGERED `CalibaniteGreatsword_NormalAttackAdditionalDamage` (1316,
    volet Sweep), PAS cette active -- l'etiquette « NO-OP DAMAGE(Power) » de la couverture kit est
    trompeuse : l'ExecuteBehaviour de 1189 ne porte AUCUNE attaque."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.CalibaniteGreatsword)  # 1189
    ABILITY_ID = "CalibaniteGreatsword"

    # GATE DE CIBLE (#115) — forme (A) LITTERAL DIRECT.
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.CalibaniteGreatswordAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, 1, &statsFromClass, 1, 0x80, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)
    # Le 2e argument (`options+0x00`) vaut 1 ici, contre 0 pour toutes les autres actives du module :
    # c'est ce booleen que teste la surcharge 5 arguments de
    # `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` — a 1 et cible == caster, elle
    # route vers `TargetingQuery$$GetCasterNotAddedReason` AU LIEU du filtre statique (c'est le regime
    # d'un cast SELF, ce qu'est ce toggle de posture).
    # Unique bit du masque : 0x80 `AddCaster` — et `GetCasterNotAddedReason` commence justement par
    # `if (-1 < (char)Rules)` (bit 7 clair) : bit POSE = tous ses controles sont sautes, la cible est
    # valide d'office. Aucun bit lu par le filtre statique => masque pose pour ce qu'il est, aucun
    # refus arme (annotation exacte, comportement offline inchange).
    # `self_cast=True` : le commentaire ci-dessus decrivait deja le `1` du ctor, mais le
    # litteral portait le defaut `False` -- corrige avec #241. Sans effet observable ici (le
    # seul bit du masque, `AddCaster`, n'est lu par AUCUNE regle du filtre statique, et
    # `get_caster_not_added_reason` rend 0), mais le champ doit dire ce que dit le ctor.
    # PORTEE (#241) : `range = TargetingRange` statique `+0x60` = `overrideRange = 0`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.AddCaster,
                                         self_cast=True,
                                         range=RANGE_SELF,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        calibanite_greatsword_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        added = [p["effect_type"] for n, p in ectx.emitted if n == "AddEffect" and p.get("placed")]
        removed = [p["effect_type"] for n, p in ectx.emitted if n == "RemoveEffect" and p.get("removed")]
        return {"ability": "CalibaniteGreatsword", "caster": caster_id,
                "stance": "Sweep" if CG_SWEEP in added else ("Strike" if CG_STRIKE in added else None),
                "added": added, "removed": removed, "dsl": True}
