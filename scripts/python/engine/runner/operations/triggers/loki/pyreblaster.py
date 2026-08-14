"""`Pyreblaster` -- passif `TriggeredAbilityType` 0x44a = **1098** (#1052).

PORTEURS (gate de confrontabilite, ventiles) :
  * `templNpc3InitiatePyreblaster` -- **npc**, `units.npc[].stats[]` present -> confrontable par le
    CHEMIN DE STATS EXPLICITE (`rl_duel build --explicit-stats templNpc3InitiatePyreblaster:3`,
    case-92 Sec.5bis recours 4). Le porteur arrive avec SES stats, SES traits, SES armes ;
  * `templInitiatePyreblaster` -- **summon**, `visualId == templNpc3InitiatePyreblaster` (le jumeau
    npc ci-dessus). **AUCUN invocateur n'existe** : un balayage EXHAUSTIF du gameconfig (tout
    `str` de l'arbre, pas seulement `constants.unitId*`) ne trouve cet `unitId` NULLE PART hors de
    sa propre definition. `EnvFactionSummons:BlackTemplars` invoque `templInitiate`, PAS lui. C'est
    le cas 2 de case-92 Sec.5bis (« summon SANS invocateur »), et c'est pourquoi l'audit rendait
    `S?` ; le jumeau NPC le rend confrontable quand meme.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PyreblasterAbility$$CreateTrigger` -- INVISIBLE
des tables (corps DEDUPLIQUE par ICF avec `...Active.Loki.FireOfAbsolutionAbility$$CreateTrigger` :
MEME RVA, appartenance etablie slot a slot dans le bloc `methodPointers` du PE, puis CONFIRMEE par
le CONTENU -- le trigger lu est exactement l'i2 de Pyreblaster) :

    On(0x4a = AttackInAtomicGroup, ownerNeedsToBeAlive = 1)
  & get_OwnerIsActor
  & IsRangedAttack

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PyreblasterAbility$$CreateBehaviour` :

    minDmg   = AbilityConfiguration.GetVariableForLevel(0xc = minDmg, abilityState)
    maxDmg   = AbilityConfiguration.GetVariableForLevel(0xd = maxDmg, abilityState)
    nrOfHits = AbilityConfiguration.GetNumberConstant(0x2f = nrOfHits)          # 3
    profile  = AbilityConfiguration.GetDamageProfile()                          # Flame

    cibles   = Enemies( Caster@<DSLSelectors+0x48>,
                        Units( TileBehindFilled(CasterTile@<+0x50>, Target@<+0x60>),
                               unique = 1, selectionType = 3 ),
                        selectionType = 3 )
    tuiles   = Walkable( TileBehindFilled(CasterTile@<+0x50>, Target@<+0x60>)
                         op_Addition Tiles(Target@<+0x60>) )

    return op_Addition(
        AttackWithAttackDamage( caster = Caster@<+0x48>, target = cibles,
                                amount = RandomAmount(minDmg, maxDmg), damageProfile = profile,
                                hits = nrOfHits, abilityOrEffect = AbilityOrEffect(this),
                                options = <struct ZEROEE>, selectionType = 2 ),
        AddEffect( 0x5 = 5 Fire, AbilityStateReference, targets = tuiles, turns = null ) )

`...PyreblasterAbility$$GetUnitBehindTarget` est le MEME sous-arbre `cibles`, extrait pour le
PLAYBOOK (`IdunBattle.AI.Playbook.Loki.PyreblasterPlaybook.u003CCalculateAttackUtilityInSteps
Internalu003Ed__2$$MoveNext` en est l'unique appelant) -- face DECISION, hors perimetre de cette
tranche.

i2 : « When performing a ranged attack, sets the hex behind the enemy on Fire and deals 3x
{minDmg}-{maxDmg} Flame Damage to any enemy on that hex. »

⚠ **L'ORDRE DU `op_Addition` EST ATTAQUE PUIS FEU** (`AbilityBehaviour$$op_Addition(attaque,
feu)`), alors que le noeud `AddEffect` est CONSTRUIT en premier. C'est l'ordre d'EXECUTION qui
compte, et c'est celui-la qui est mirrore.

⚠ **LE FEU COUVRE DEUX TUILES, L'ATTAQUE UNE SEULE.** `tuiles` = la tuile derriere **plus** la
tuile de la CIBLE (`op_Addition Tiles(Target)`), le tout filtre `Walkable` ; `cibles`, elle, ne
lit que `TileBehindFilled`. L'i2 ne mentionne que « the hex behind » -- le decompile fait foi.

⚠ **`AddEffect` A QUATRE ARGUMENTS -> SOURCE = LA CIBLE.** La surcharge appelee
(`DSLBehaviors$$AddEffect(effectType, abilityState, targets, turns)`) passe litteralement `0` en
SOURCE a `AddEffectBehaviour$$.ctor` : chaque TUILE en feu est sa PROPRE source
(`source_from_target=True`), meme lecture que `OrbsOfDecay`.

RESIDUS NOMMES
  * **`#1052-r1`** -- la branche NON-ALIGNEE de `BattleQuery$$GetTilesBehindFilled` (deux tuiles
    via `MovementUtil$$RoundDirection`) n'est pas portee : ni le facteur `by` du `Lerp` (XMM) ni le
    nudge (champ statique ecrit par un `.cctor`) ne sont lisibles dans le pseudo-C. Le mirror rend
    `[]` dans ce regime -- degradation RESTRICTIVE et DITE. Impossible a distance 1 (deux hexes
    adjacents partagent toujours une composante cube), donc a partir de la distance 2 seulement.
  * **rang / portee de l'emetteur** : le port n'emet `On(0x4a)` que depuis
    `DamageHandler.visit_AttackUnitMessage` (voie MESSAGE de l'attaque normale) et depuis le noeud
    DSL `EvaluateAbilities`. Les portes qui appellent `AttackDamageOperation.execute` DIRECTEMENT
    (overwatch, `UseActiveAbility`) ne l'emettent pas -- MEME residu preexistant que `#478-r3` /
    celui deja ecrit par `OrbsOfDecay`.
  * **`selectionType = 2`** (9e argument d'`AttackWithAttackDamage`) n'a pas d'equivalent dans la
    feuille portee -- non modelise, comme sur tous les autres call-sites portes.

CE QUE `ABILITY_TRIGGERS` N'EXIGE PAS : 1098 est une `TriggeredAbilityType`, donc elle n'entre NI
dans `ABILITY_CLASSES`, NI dans `TARGETING_OPTIONS`, NI dans `ABILITY_ATTACK_TYPE` -- ces trois
registres sont ceux des abilities ACTIVES.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors.accessors import CasterTile, Target
from .....entities.selectors.tiles import TileBehindFilled, TileUnion
from .....entities.selectors.geometry import Walkable
from .....entities.selectors.units import Enemies, Tiles, Units
from .....entities.unit_selection_type import UnitSelectionType
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.behaviours import op_and
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import AddEffect
from ....state import State
from ..base import TriggeredAbility, TriggerEvent

#: Cle du registre `ABILITY_TRIGGERS` = le NOM gameconfig du passif (`units.<kind>.<id>.
#: passiveAbilities`), donc aucune traduction -- DERIVE du mirror d'enum, jamais un litteral
#: (meme convention que `SPLIT_KEY`/`FLAMES_OF_MUTATION_KEY` de `loki/horrors.py`).
PYREBLASTER_KEY = TriggeredAbilityType.Pyreblaster.name              # "Pyreblaster"
ABILITY_ID = PYREBLASTER_KEY

#: `AbilityConfiguration$$GetDamageProfile()` -- LU au gameconfig (`constants.damageProfile`), pas
#: deduit du nom de l'ability.
DAMAGE_PROFILE = "Flame"
#: `AddEffect(0x5 = 5 Fire, ...)`.
FIRE = int(EffectType.Fire)
#: `Units(..., 1, 3)` et `Enemies(..., 3)` -- le litteral `3` aux DEUX etages.
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)


def units_behind_target():
    """`...PyreblasterAbility$$GetUnitBehindTarget` = le sous-arbre de CIBLES, tel quel :

        Enemies( Caster@<+0x48>,
                 Units( TileBehindFilled(CasterTile@<+0x50>, Target@<+0x60>), 1, 3 ),
                 3 )

    `TileBehindFilled` rend des IDS de tuile (domaine du noeud), que `Units` resout en occupants ;
    `Enemies` sans `reference` explicite prend le CASTER, ce qui EST `Caster@+0x48`."""
    behind = TileBehindFilled(CasterTile(), Target())
    return Enemies(Units(behind, selection_type=SELECTION), selection_type=SELECTION)


def fire_tiles():
    """`Walkable( TileBehindFilled(CasterTile@<+0x50>, Target@<+0x60>) op_Addition
    Tiles(Target@<+0x60>) )`.

    `Tiles(..., as_ids=True)` : `Walkable` et `TileUnion` travaillent en IDS de tuile, et une
    composition positions <-> ids ne raterait RIEN bruyamment -- elle rendrait simplement une union
    heterogene que `board.walkable(t)` ferait lever. Meme parametre, meme raison qu'au call-site
    `Fragstorm` deja porte."""
    behind = TileBehindFilled(CasterTile(), Target())
    return Walkable(TileUnion(behind, Tiles(Target(), as_ids=True)))


def pyreblaster_tree():
    """`...PyreblasterAbility$$CreateBehaviour` = `op_Addition(attaque, feu)`, dans CET ordre.

    * l'attaque route `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (famille
      ATTACK : crit/block, 2 tirages/coup) -> `native_factory="attack"`, le defaut. Le mode BORNES
      (`ability_attack_params`) EST le mirror de `RandomAmount(GetVariableForLevel(0xc),
      GetVariableForLevel(0xd))` + `GetNumberConstant(0x2f)` + `GetDamageProfile()` -- les trois
      accesseurs natifs que le noeud consomme ;
    * `is_melee=False` : le coup pose est un tir (profil `Flame`, arme de portee 2 du porteur), et
      le trigger exige de toute facon `IsRangedAttack` sur l'attaque DECLENCHANTE ;
    * `multi=True` : le natif passe un SELECTEUR multi-cible, donc `AttackBehaviour$$Execute`
      resout la liste, l'`OrderBy` puis attaque chaque cible ;
    * `level_slot="passive"` : `GetVariableForLevel` se resout contre l'`abilityState` sous lequel
      l'ability est MONTEE, et `Pyreblaster` arrive par `passiveAbilities` ;
    * `AddEffect` avec `source_from_target=True` (surcharge 4 arguments, source litterale `0`) et
      `duration_rounds=None` (`turns = null` -> `DefaultAmountOfRounds(0x5)`)."""
    attack = AttackWithAttackDamage(
        units_behind_target(), ABILITY_ID, DAMAGE_PROFILE, is_melee=False, multi=True,
        level_slot="passive", ability_type=int(TriggeredAbilityType.Pyreblaster))
    fire = AddEffect(FIRE, EffectType.Fire.name, fire_tiles(),
                     duration_rounds=None, source_from_target=True)
    return op_and(attack, fire)


class PyreblasterAbility(TriggeredAbility):
    """`...PyreblasterAbility` (triggered 0x44a = 1098) -- cf. l'en-tete du module.

    OBSERVABLE : sur toute attaque RANGED de son porteur, (1) `nrOfHits` coups `Flame` contre le ou
    les ennemis debout sur la tuile DERRIERE la cible, et (2) `Fire` sur cette tuile ET sur celle de
    la cible, les deux filtrees `Walkable`."""
    event_id = int(EventTriggerType.AttackInAtomicGroup)      # `On(0x4a, ownerNeedsToBeAlive = 1)`
    TRIGGERED_ABILITY_ID = int(TriggeredAbilityType.Pyreblaster)          # 0x44a = 1098

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsActor` : l'`AbilityEntities` de ce vecteur porte l'attaquant en `Actor@+0x40`,
        # et le port ne thread qu'`actor_id`. MEME collapse que `OrbsOfDecayAbility` sur ce vecteur.
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False
        if ev.target_id is None:
            return False
        # `IsRangedAttack` -- nature du coup DECLENCHANT, threadee par l'emetteur. Tri-etat : le
        # port pose `ranged` en booleen sur ce vecteur, jamais None.
        return bool(ev.ranged)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, self.owner_id, ev.target_id)
        pyreblaster_tree().execute(entities, ectx)
        hits = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        fires = [p for n, p in ectx.emitted if n == "AddEffect"]
        if not hits and not fires:
            return None
        return {"passive": ABILITY_ID, "owner": int(self.owner_id), "target": int(ev.target_id),
                "behind": [{"target": p.get("target"), "attack": p.get("attack")} for p in hits],
                "fire": [{"tile": p.get("target"), "placed": p.get("placed")} for p in fires]}
