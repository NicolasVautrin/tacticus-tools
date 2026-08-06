"""`Abilities.Damage.Loki.OnToxicDamageAbility` (1203 = 0x4b3) — pose de la CONTAMINATION on-hit.

JUMEAU STRUCTUREL de `OnFireDamageAbility` (`fire.py`), avec DEUX differences REELLES lues au decompile
(build gqfc5mff6c) — ce n'est PAS « OnFire avec un autre id » :

    IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateTrigger
        On(0x10, 1) & DamageProfileHasTrait(4 = OnToxic) & !TriggeringEffectIs(0x4dc = Contaminated)
    IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateBehaviour
        If( IsFirstHitInSeries() & Maybe( ConfigConst(0x4b3, Self@0x148, 0x2a = chance) ),
            AddEffect(0x4dc = Contaminated, AbilityStateReference, Tiles(target@0x178)) )

    IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateTrigger
        On(0x10, 1) & DamageProfileHasTrait(1 = OnFire)  & !TriggeringEffectIs(5 = Fire)
    IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateBehaviour
        AddEffect(5 = Fire, AbilityStateReference, Tiles(target@0x178))            # INCONDITIONNEL

IDENTIQUE : le vecteur d'evenement (`On(0x10)`, emis PAR COUP par `IdunBattle.Operations.
ApplyDamageOperation$$Execute` -- sequence `On(0x39 = PreDamageTaken)` -> `On(0xf)` -> `On(0x10)`, cf. #85 ; ce n'est
PAS `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`, qui n'emet que `0x3d` puis
`8`), la forme du gate de profil, la feuille de pose
(`AddEffect` TILE-DOMAIN `Tiles(Target())` = la MainTile occupee de la cible), la surcharge d'`AddEffect`
(5 args -> selecteur SOURCE natif NULL, duree par defaut).
DIFFERENT : le behaviour de Toxic est un `If(cond, AddEffect)` — pas une pose inconditionnelle — et la
condition est un ET COURT-CIRCUITANT (`IdunBattle.DSL.MultipleAbilityTrigger$$ShouldTrigger` : le droit
n'est evalue QUE si le gauche est vrai) de deux predicats :
  1. `IsFirstHitInSeries()` -> `IdunBattle.Entities.Triggers.IsFirstHitInSeriesTrigger$$ShouldTrigger`
     = `AbilityEntities.IsFirstHit` = `DamageAppliedResult.get_IsFirstHit` = `hitIndex == 0`. Le natif
     evalue le behaviour a CHAQUE coup ; seul le PREMIER coup de la serie passe ce gate. Consequence
     RNG : **UN SEUL tirage par SERIE de coups** (donc une fois par cible attaquee), pas un par coup —
     le court-circuit garantit qu'aucun `NextBool` n'est consomme aux coups 2..N.
  2. `Maybe(chance)` -> `IdunBattle.Entities.Triggers.MaybeTrigger$$ShouldTrigger` =
     `DisallowablePseudoRNG.NextBool(rng, chance)`. `chance` = `ConfigConst(1203, <config>, 0x2a)` =
     `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(AbilityConstantType.chance)` sur
     la config de l'ability 1203 (`IdunBattle.Entities.Formulas.ConfigAmount$$Calculate`, branche
     `constantKey@+0x38`). `AbilityConstantType 0x2a = chance` est calibre par FireOfAbsolution
     (`GetNumberConstant(0x2a)` <-> `abilities.FireOfAbsolution.constants.chance = "30"`).

SOURCE DE `chance` = **25** (pourcentage), lue en CONFIG et jamais en dur, avec DEUX ancrages concordants :
  - `clientGameConfig.globalValues.toxicDamageContaminationChance = 25` (ce que le port LIT, cf.
    `TOXIC_CHANCE_KEY` — le gameconfig client n'expose PAS d'entree `units.abilities.OnToxicDamage*`) ;
  - la BattleConfiguration capturee (`data/seed-bc.json`) porte
    `Abilities.PassiveAbilities.OnToxicDamageAbility.Constants.chance = "25"` = LITTERALEMENT la
    `AbilityConfiguration` que `ConfigConst(0x4b3, ..., 0x2a)` interroge en live.
Le test `test_on_toxic_damage_live.py` ANCRE cette egalite (globalValue == constante BC) pour qu'une
divergence de build casse un test au lieu de passer inapercue.

VECTEUR (DE-FORKE) : ce canal est desormais un CONSOMMATEUR du bus `On(0x10)` du port
(`operations/triggers/dispatch/attack.py::damage_dealt_triggers`, emis par le chokepoint
`AttackDamageOperation._apply_damage_pipeline`), au lieu d'etre appele imperativement depuis
`after_hit_normal_attack` / `execute_ability_attack`. La difference n'est pas cosmetique : la place
imperative etait APRES les vecteurs de MORT, la place native (bus) est AVANT -- et le regime ou les
deux divergent a ete ARBITRE LIVE (cf. la docstring de `OnToxicDamageAbility` : ordre bus 6/6, ordre
imperatif 3/6). Le bus emet par GROUPE de degat resolu (le natif emet par COUP) et thread
`is_first_hit` = « ce groupe contient le coup d'index 0 » ; le compte de tirages (1 par serie/cible)
reste celui du natif, puisque `IsFirstHitInSeries` ne laisse passer que ce coup-la.

PORTEURS (ventilation, gate de confrontabilite) — le canal se declenche sur TOUT coup dont le profil de
degat porte le `DamageTrait.OnToxic`, c.-a-d. le profil `Toxic` (`damageProfiles.Toxic.Traits`) :
  - HERO (`--list-pool`) : `admecMarshall` (arme ranged Toxic r2), `deathPutrifier` (arme melee Toxic +
    `FoulInfusion`), `genesBiophagus` (arme melee Toxic), `deathBlightlord` (`HazeOfCorruption`),
    `admecDominus` (`RadBombardment`) ;
  - MoW : `deathCrawler` (`PlagueburstMortar`, 3 coups Toxic) ;
  - SUMMON : `admecSmnVanguard` (3 coups Toxic r2, amene par `ControlEdict` d'`admecMarshall`),
    `tyranSmnSporeMine` (`FloatingDeath`, kit non porte) ;
  - NPC : ~20 doublons boss/npc (hors jeu).
Le canal est donc largement confrontable, et il est TRANSVERSE (il ne depend d'aucune ability precise).

ANTI-BOUCLE : `!TriggeringEffectIs(0x4dc)` est structurellement satisfait ici (l'effet de TUILE
Contaminated n'inflige aucun degat Toxic — il pose `Contaminated_Unit` 1245, -30% FixedArmor, cf.
`effect_triggers.ContaminatedTileEffect`), et `AddEffectOperation` no-op si la tuile est deja
contaminee. Cf. `rad_saturation.py` (l'AUTRE poseur porte de 1244) et `loki/__init__.py`."""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

import gameconfig as GC

from ....state import State
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from .....entities.behaviours import If
from .....entities.damage_trait import DamageTrait
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import Target
from .....entities.selectors.units import Tiles
from .....entities.triggers import IsFirstHitInSeries, MaybeTrigger, TriggerAnd
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent

CONTAMINATED_TILE = int(EffectType.Contaminated)   # 1244 (0x4dc) — effet de TUILE (aval = ContaminatedTileEffect)
# `ConfigConst(0x4b3=1203, <config>, 0x2a=AbilityConstantType.chance)` : la config de l'ability 1203 vient
# de la BC (`Abilities.PassiveAbilities.OnToxicDamageAbility.Constants.chance`), elle-meme derivee de ce
# globalValue — SEULE cle gameconfig du chiffre (25). Jamais un litteral cote port.
TOXIC_CHANCE_KEY = "toxicDamageContaminationChance"


def on_toxic_damage_tree(rng, chance: int, contaminated_effect_type: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateBehaviour`
    (MIRROR 1:1 du DECOMPILE) :

        If( op_BitwiseAnd( IsFirstHitInSeries(),
                           Maybe( ConfigConst(0x4b3, Self@0x148, 0x2a = chance) ) ),
            AddEffect( effectType = 0x4dc (Contaminated),
                       source     = <selecteur NULL -> la cible>,
                       stateRef   = AbilityStateReference,
                       target     = Tiles(target@0x178) ) )                        # TILE-domain

    - `If` = `IdunBattle.Entities.Behaviours.IfBehaviour$$Execute` (cond @+0x50, then @+0x58,
      else @+0x60 ABSENT ici -> resultat vide si la condition tombe).
    - `TriggerAnd` = `IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd` -> `MultipleAbilityTrigger` :
      COURT-CIRCUIT (le `Maybe` n'est PAS evalue si `IsFirstHitInSeries` est faux) -> aucun tirage
      gaspille sur les coups 2..N d'une serie.
    - `MaybeTrigger` = le PREDICAT (surcharge `Maybe(chance)` a 1 arg), pas le noeud EFFET homonyme :
      il porte son PRNG en champ (`MaybeTrigger+0x18`), comme le natif.
    - `AddEffect` : la surcharge NATIVE appelee est celle a 5 arguments (`AddEffect(factory, 0x4dc,
      stateRef, Tiles(target), 0)`), qui construit
      `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor(this, X, effectType, stateRef,
      SOURCE = 0, TARGETS = Tiles(target), options)`. Le selecteur SOURCE (`+0x60`) est donc NUL, et
      `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` applique son fallback
      (`lVar14 = <cible courante>; if (<source selectionnee> != 0) lVar14 = <celle-ci>;`) => **la SOURCE
      de l'effet EST la TUILE ciblee**, pas le caster -> `source_from_target=True` (meme motif et meme
      port que le volet Contaminated de `RadBombardmentAbility`). Le 5e argument `0` = pas de
      `TurnsFromRounds` -> duree PAR DEFAUT `DefaultAmountOfRounds(0x4dc) = 2 rounds`
      (`duration_rounds=None`), convertie par `AddEffectOperation`.

    `rng`/`chance`/`contaminated_effect_type` sont passes par l'appelant (`state.rng`,
    `GC.global_value(TOXIC_CHANCE_KEY)`, `CONTAMINATED_TILE`) — meme convention que
    `env_fire_tile_tree`/`fire_of_absolution_tree`, pour eviter tout couplage d'import."""
    cond = TriggerAnd(IsFirstHitInSeries(), MaybeTrigger(rng, Const(int(chance))))
    return If(cond, AddEffect(contaminated_effect_type, EffectType.Contaminated.name, Tiles(Target()),
                              duration_rounds=None, source_from_target=True))


class OnToxicDamageAbility(TriggeredAbility):
    """`OnToxicDamageAbility` (TriggeredAbilityType 1203, `Abilities.Damage.Loki`) — pose de la
    CONTAMINATION on-hit, branchee sur le BUS `On(DamageDealt = 0x10)`.

    Gate de DECLENCHEMENT (= `CreateTrigger`) : `DamageProfileHasTrait(DamageTrait.OnToxic = 4)` sur le
    profil du coup (gameconfig `damageProfiles[<profil>].Traits` — seul `Toxic` le porte) ET
    `!TriggeringEffectIs(0x4dc)`, desormais PORTE (`ev.triggering_effect`) au lieu d'etre « satisfait
    structurellement » par la place de l'appel.

    ABILITY GLOBALE (`owner_is_global`) : le `CreateTrigger` ne porte aucun predicat d'owner ; le canal
    se declenche sur le PROFIL du coup, pour n'importe quel attaquant. Inscription UNIQUE dans
    `GLOBAL_TRIGGERS` — la CARDINALITE est une MESURE (exactement UN `NextBool` par serie de coups en
    live, oracle = etat MT), pas une hypothese.

    VECTEUR (de-fork) — la place du `Maybe` dans le flux RNG est ARBITREE LIVE. Ce canal etait appele
    IMPERATIVEMENT depuis `after_hit_normal_attack` / `execute_ability_attack`, c.-a-d. APRES la
    resolution complete de l'attaque, donc APRES les vecteurs de MORT emis par `_fire_death_if_killed`.
    Le natif emet `On(0x10)` dans `IdunBattle.Operations.ApplyDamageOperation$$Execute`, AVANT que la
    mort ne soit traitee (`VerifyDeaths` -> `IdunBattle.Operations.KillUnitOperation$$Execute`).
    MESURE (`probe_o10_rng_order.py`, `tyranParasite` arme `Toxic` + passif `BarbedOvipositor` dont le
    behaviour consomme un `PickRandomly` sur `On(0 = UnitDeath)` ; victime `astraBullgryn` one-shottee) :
    sur 6 confrontations / 3 seeds, l'ordre BUS concorde avec le live **6/6**, l'ordre imperatif
    **3/6** — et ses 3 desaccords vont dans LES DEUX SENS (2 contaminations manquees, 1 de trop), la
    signature d'une PERMUTATION de tirages. NB : l'etat MT final est IDENTIQUE dans les deux ordres
    (meme cardinalite) -> un critere « delta mti » seul aurait conclu a tort « rien ne bouge ».

    `is_first_hit` vient desormais de l'EVENEMENT (`ev.is_first_hit`) et non d'un litteral : le natif
    evalue le behaviour PAR COUP et `IsFirstHitInSeries` ne laisse passer que le coup d'index 0 ; le bus
    du port emet par GROUPE de degat resolu et thread le drapeau « ce groupe contient le coup 0 ». Un
    groupe de coups ADDITIONNELS (#179, index de sortie > 0) le porte donc a False -> aucun tirage,
    exactement comme le court-circuit natif de `IdunBattle.DSL.MultipleAbilityTrigger$$ShouldTrigger`."""
    event_id = int(EventTriggerType.DamageDealt)     # 0x10 = 16
    owner_is_global = True

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if not ev.profile or state.effects is None or getattr(state, "board", None) is None:
            return False
        traits = (GC.damage_profile(ev.profile) or {}).get("Traits") or []
        if DamageTrait.OnToxic.name not in traits:   # DamageProfileHasTrait(DamageTrait.OnToxic = 4)
            return False
        if ev.triggering_effect == CONTAMINATED_TILE:            # !TriggeringEffectIs(0x4dc)
            return False
        return state.rng is not None                 # le `Maybe` natif EXIGE un PRNG

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        chance = GC.global_value(TOXIC_CHANCE_KEY)   # ConfigConst(1203, ..., 0x2a) == 25, non hardcode
        if not chance:
            return None
        entities = replace(entities_from_state(state, ev.actor_id, ev.target_id),
                           is_first_hit=bool(ev.is_first_hit))
        ectx = ExecutionContext(state=state, rng=state.rng)
        on_toxic_damage_tree(state.rng, int(chance), CONTAMINATED_TILE).execute(entities, ectx)
        placed = [p["target"] for n, p in ectx.emitted if n == "AddEffect" and p.get("placed")]
        if not placed:                               # tirage perdu OU tuile deja contaminee -> no-op
            return None
        return {"tile_effect": EffectType.Contaminated.name, "placed_on_tile": placed[0],
                "by": ev.actor_id, "on": ev.target_id, "placement": "OnToxicDamage"}
