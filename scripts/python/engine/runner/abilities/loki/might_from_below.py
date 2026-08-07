"""`Abilities.Active.Loki.MightFromBelowAbility` (active 1165, The Patermine `genesPatriarch`) --
face COMBAT (#501). Kit gameconfig `MightFromBelow` : `damageProfile=Psychic`
(`PiercingRatio 100`, trait `NoBlocking`), `attackRangeType=Melee`, `nrOfHits=5`,
`unitId=genesSmnGenestealer`, `minDmg`/`maxDmg`[level] (rarity-affected). i2 : « Deals 5x
<minDmg-maxDmg> Psychic Damage to an adjacent enemy, then summons a Purestrain Genestealer on each
decoy adjacent to the Patermine. The Purestrain Genestealers can immediately attack in melee, but
cannot move this turn. »

RE (decompile ghidra, build `rnca9r7q6c`) -- `IdunBattleLogic.Entities.Abilities.Active.Loki.
MightFromBelowAbility$$ExecuteBehaviour` n'appelle PAS `ExecuteAtomic` : il appelle
**`AActiveAbility$$Execute` TROIS FOIS**, sur trois arbres distincts, dans cet ordre :

    dmg     = AActiveAbility$$MinMaxDamage(this, abilityState, isPrediction: 0)
              = DSLFormulas$$RandomAmount( GetVariableForLevel(0xc minDmg),
                                           GetVariableForLevel(0xd maxDmg) )
    profile = AActiveAbility$$GetDamageProfile(this)          # constants.damageProfile
    hits    = AActiveAbility$$GetHits(this)                   # GetNumberConstant(0x2f nrOfHits)

    attack  = DSLBehaviors$$AttackWithAbilityDamage(
                  caster        = <DSLSelectors+0x48>,        # Caster
                  target        = <DSLSelectors+0x60>,        # Target (mono-cible)
                  amount        = dmg,
                  damageProfile = Nullable(profile),
                  hits          = hits,                       # INT, pas un noeud
                  abilityOrEffect = AbilityOrEffect(this),
                  selectionType = 2 )

    tiles   = DSLSelectors$$Tiles(
                  DSLSelectors$$UnitsWithTrait(
                      DSLSelectors$$AdjacentFriends(unit = <DSLSelectors+0x48>,
                                                    unitTile = <DSLSelectors+0x50>,
                                                    unique = 1),
                      0x41d = UnitTrait.Decoy, 3 ) )
    opts    = SpawnUnitOptions$$WithStatsFromConfig(config@+0x60, abilityState, 0, 0)
    opts.<+0x18> = DSLBehaviors$$PerformAIAttackFromCurrentPosition(<DSLSelectors+0x68>)  # ActiveTarget
    spawn   = DSLBehaviors$$Spawn(<DSLSelectors+0x48>, tiles,
                                  GetStringConstant(config, 0 = unitId), opts)

    [1] AActiveAbility$$Execute( Group(attack, <+0x48>, 0x20 = GroupType.Ability_Attack) )
    [2] AActiveAbility$$Execute( KillDeadUnits(<+0x48>, UnitsDamagedThisPhase(<+0x48>)) )
    [3] AActiveAbility$$Execute( IfAlive(<+0x48>,
                                         Group(spawn, <+0x48>, 0x22 = GroupType.Ability_Summon),
                                         null) )

`MightFromBelowAbility$$GetPossibleSpawnTiles` reconstruit EXACTEMENT le meme `tiles` (memes trois
appels, memes arguments) : un seul artefact natif, d'ou le foyer partage
`might_from_below_spawn_tiles()` ci-dessous.

LE COEUR DU CAS : L'ORDRE DES TROIS PHASES EST LA MECANIQUE
-----------------------------------------------------------
Le sous-arbre `tiles` est CONSTRUIT avant le premier `Execute`, mais un arbre DSL est LAZY : il n'est
EVALUE qu'au 3e. Entre les deux, l'attaque a pu TUER la cible -- et le passif `CosmicHorror` du meme
porteur pose alors un `genesSmnDecoy` sur la tuile du mort
(`IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnKillAbility$$CreateBehaviour`, le
`Spawn` y est INCONDITIONNEL, hors du `Maybe(chance)`). Comme le masque de ciblage impose une cible
ADJACENTE, ce decoy neuf est adjacent au Patermine : `AdjacentFriends & Decoy` le ramasse, et le
Genestealer apparait dessus. C'est le moteur self-feeding kill -> decoy -> summon decrit au wiki
(`docs/rl/wiki.md` §3bis Patermine). Figer les tuiles AVANT l'attaque le CASSERAIT en silence :
sans decoy prealable, le cast rendrait 0 summon (exactement ce que la mesure live du journal
rapporte quand le Patermine n'a pas tue : « Ability_Summon a fire mais spawne RIEN »).

Cote port, l'`AbilityEntities` natif porte une REF d'etat, la ou `entities_from_state` FIGE sa liste
`units` a la construction (cf. la docstring de `behaviours/summon.py::Spawn`, meme piege). Les trois
phases sont donc jouees chacune sur un `AbilityEntities` RECONSTRUIT -- c'est ce qui rend visible au
3e arbre le decoy pose pendant le 1er, et c'est le mirror de la ref d'etat native. `Caster` et
`Target` sont re-lies aux memes entites : rien d'autre ne transite entre les phases (aucun `Cache`,
aucun `children` accumule avant le `Spawn`).

SURCHARGE DE LA FEUILLE, TRANCHEE PAR SES XREFS ENTRANTES -- `DSLBehaviors$$AttackWithAbilityDamage`
a QUATRE surcharges que ghidra decompile toutes sous le meme nom. `list_xrefs` place l'appel de
`MightFromBelowAbility$$ExecuteBehaviour` sur celle a
`(caster, target, amount, damageProfile, hits:System.Int32, abilityOrEffect, selectionType)` : elle
enveloppe `damageProfile` dans un `DSLSelectors$$Direct` et `hits` dans un `Direct(hits)` de formule,
puis delegue au COEUR `(caster, target, amount, abilityOrEffect, options, selectionType)`, qui
construit `AbilityDamageBehaviour` + `AttackBehaviour`. Le nombre de coups est donc bien un SCALAIRE
ici (contraste avec 1027 `PsychicMaelstrom`, dont la meme famille recoit un `IAmountFormula`) : c'est
`GetNumberConstant(0x2f)` = `nrOfHits` = 5, et rien ne le module.

FAMILLE **ABILITY** -> `native_factory="ability"` : `AbilityDamageOperation$$ExecuteHits` =
UN tirage de valeur par coup, AUCUN crit (la famille ABILITY n'a pas de slot `RollCritical`).
Ground truth live du journal (seed 70009) : « 5x Psychic Pierce100 ~1146/1191/1127/1092
DamageProfileType=13 no-crit » -- cinq montants DISTINCTS (donc un tirage par coup) et pas de crit.
Le kit affiche la mecanique `crit` parce que le profil `Psychic` la declare au niveau de l'ARME ;
la face executee, elle, passe par la famille ABILITY et ne roule aucun critique.

PHASE [2] -- `KillDeadUnits(Caster, UnitsDamagedThisPhase(Caster))`. Chez nous la mort est finalisee
INLINE dans l'attaque, donc la feuille portee MIRROR la structure sans re-muter (re-emettre un kill
DOUBLE-FIRE les on-death) : cf. `behaviours/lifecycle.py::KillDeadUnits`. Elle reste dans l'arbre
parce qu'elle est ce qui, cote natif, SEPARE l'attaque du summon -- l'ordre porte, pas la mutation.

RESIDUS NOMMES :
  * `MatchesUnitSelectionType(unit, selectionType = 2)` et `HasTrait(unit, 0x40e Invincible)`, les
    deux gates par-cible d'`AbilityDamageBehaviour$$Execute` : inertes en mono-cible sur une cible
    vivante deja validee par le masque.
  * `UnitExtensions$$IsAttackMaxOutDamage(caster)` (gate de `GetDamage` qui force `min == max`) :
    regime commun a toute la famille, non porte, sans porteur dans un roster de duel.
  * le `Spawn` natif ne passe AUCUN `CanAddUnit` : il pose le Genestealer sur la tuile du decoy,
    qui l'occupe deja. Ce que devient le decoy (crush / cohabitation) n'est PAS lisible dans cet
    `ExecuteBehaviour` -- c'est le comportement d'`AddUnitOperation` face a un occupant `Steppable`,
    hors de cet arbre. Le port ne l'invente pas : il pose le summon comme le natif et laisse le
    decoy en place. Verdict de la mesure live : cf. `docs/rl/case-501-might-from-below.md`.

DOCTRINE #149 : artefact natif = arbres `DSLFactory` -> arbres DSL mirrores feuille a feuille ; les
Operations dessous (`AbilityDamageOperation`, `AddUnitOperation`) restent imperatives."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..base import ActiveAbility
from ..targeting import RANGE_ADJACENT, RANGED_BOOL_FALSE, TargetingOptions
from ..targeting_rule import TargetingRule as TR
from ....dsl.effects import ExecutionContext
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.behaviours import Group, If
from ....entities.selectors.accessors import ActiveTarget, Target
from ....entities.selectors.tiles import Caster
from ....entities.selectors.units import (AdjacentFriends, Tiles, UnitsDamagedThisPhase,
                                          UnitsWithTrait)
from ....entities.traits.unit_trait import UnitTrait
from ....entities.triggers import IsAlive
from ....streams.group_type import GroupType
from ..behaviours.combat import AttackWithAttackDamage
from ..behaviours.context import entities_from_state
from ..behaviours.lifecycle import KillDeadUnits
from ..behaviours.summon import PerformAIAttack, Spawn

if TYPE_CHECKING:
    from ...state import State

MIGHT_FROM_BELOW_ID = "MightFromBelow"

#: `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithTrait(<adjacents amis>, 0x41d, 3)` -- le trait
#: LU au call-site. `0x41d = 1053` est un `UnitTrait`, pas un id d'ability : le meme ordinal existe
#: dans d'autres enums (piege d'homonymie deja documente par `triggers/loki/cosmic_horror.py`).
DECOY_TRAIT = UnitTrait.Decoy                                       # 0x41d = 1053


def might_from_below_spawn_tiles():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MightFromBelowAbility$$GetPossibleSpawnTiles`
    (MIRROR 1:1) -- et le MEME sous-arbre que celui monte inline par `$$ExecuteBehaviour` (memes
    trois appels, memes arguments : un seul artefact natif) :

        Tiles( UnitsWithTrait( AdjacentFriends(unit = Caster@0x48, unitTile = CasterTile@0x50,
                                               unique = 1),
                               0x41d = UnitTrait.Decoy, 3 ) )

    `AdjacentFriends` natif n'a NI rayon NI selecteur de reference : sa surcharge `(unit, unitTile,
    unique)` batit `Friends(reference = unit, Units(AdjacentTiles(unitTile)) - unit)` -- le centre
    EST la reference d'equipe, et le voisinage est l'adjacence de plateau. Cote port, le defaut
    `radius = Const(1)` / `reference = None` (le caster) est exactement ce couple-la, le centre etant
    le caster.

    `as_ids=True` : la feuille `Spawn` consomme des IDS d'entite-tuile (c'est ce que
    `SpawnUnitBehaviour$$Execute` itere avant d'appeler `AddUnitOperation`), la ou `Tiles` rend par
    defaut des positions `(col, row)`. Sans lui, chaque spawn tomberait sur un `tile` non resolvable
    -> `_spawn_config_grot` rend `None` -> **no-op silencieux**, la signature de panne exacte que ce
    port ferme."""
    adjacent_friends = AdjacentFriends(Caster())
    return Tiles(UnitsWithTrait(adjacent_friends, int(DECOY_TRAIT)), as_ids=True)


def might_from_below_attack_tree(profile: str):
    """Arbre du PREMIER `AActiveAbility$$Execute` (MIRROR 1:1) :

        Group( AttackWithAbilityDamage(Caster@0x48, Target@0x60, MinMaxDamage,
                                       Direct(GetDamageProfile()), GetHits(), AbilityOrEffect(1165),
                                       selectionType 2),
               Caster@0x48, 0x20 = GroupType.Ability_Attack )

    - `Group` = frontiere de GROUPE de la couche vue, pass-through cote etat (RE #201) ; son
      selecteur de cibles et son `groupId` sont conserves en METADONNEE ;
    - mode BORNES (`MinMaxDamage` -> `minDmg`/`maxDmg` rarity-scales) et MONO-CIBLE : le natif passe
      les deux singletons `DSLSelectors+0x48`/`+0x60`, donc la cible du message ;
    - `native_factory="ability"` (surcharge tranchee par `list_xrefs`, cf. l'en-tete du module) ;
    - `hits` vient de `GetNumberConstant(0x2f nrOfHits)` = le defaut `hits_key` de la feuille ; le
      natif passe ici un **INT**, pas un noeud -> aucun `hits_override` ;
    - `is_melee=True` : `attackRangeType = Melee` au kit."""
    return Group(
        AttackWithAttackDamage(Target(), MIGHT_FROM_BELOW_ID, profile, is_melee=True,
                               native_factory="ability",
                               ability_type=int(ActiveAbilityType.MightFromBelow)),
        group_id=int(GroupType.Ability_Attack),                     # 0x20
        targets_sel=Caster())


def might_from_below_kill_tree():
    """Arbre du DEUXIEME `AActiveAbility$$Execute` (MIRROR 1:1) :

        KillDeadUnits( killer = Caster@0x48, targets = UnitsDamagedThisPhase(Caster@0x48) )

    Structurel : chez nous la mort est finalisee INLINE par l'attaque, donc la feuille journalise les
    DOWNED sans re-muter (cf. `behaviours/lifecycle.py::KillDeadUnits`). Elle est portee parce
    qu'elle EST la separation native entre l'attaque et le summon."""
    return KillDeadUnits(Caster(), UnitsDamagedThisPhase(Caster()))


def might_from_below_summon_tree():
    """Arbre du TROISIEME `AActiveAbility$$Execute` (MIRROR 1:1) :

        IfAlive( Caster@0x48,
                 Group( Spawn(Caster@0x48, <tuiles des decoys adjacents>,
                              GetStringConstant(config, 0 = unitId),
                              WithStatsFromConfig(config, abilityState){ +0x18 =
                                  PerformAIAttackFromCurrentPosition(ActiveTarget@0x68) }),
                        Caster@0x48, 0x22 = GroupType.Ability_Summon ),
                 null )

    `IfAlive(sel, then, else)` est LITTERALEMENT `If(IsAlive(sel), then, else)` --
    `DSLBehaviors$$IfAlive` appelle `DSLTriggers$$IsAlive` puis `DSLBehaviors$$If` : la composition
    EST le mirror, pas de noeud dedie (meme lecture que `abilities/loki/facade.py`).

    `unit_id_constant="unitId"` = `GetStringConstant(config, 0)` LU au call-site (`genesSmnGenestealer`).

    `on_appearance` = le sous-behaviour embarque dans `SpawnUnitOptions+0x18`, fire PAR SUMMON par
    `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` juste apres la pose, avec `ActiveTarget` lie
    au summon frais. `PerformAIAttack(...)` sans argument supplementaire = le noeud
    `PerformAIAttackFromCurrentPosition` (`+0x70 allowMoveAction = 0`, `+0x78 moveAmount =
    Direct(0)`), exactement ce que l'i2 decrit : « can immediately attack in melee, but cannot move
    this turn ».

    `ability_state` reste au DEFAUT (None) : le natif passe l'`abilityState` de l'ability ACTIVE en
    cours, ce qui est deja le couple `(active_ability_level, ability_variables_multiplier)` que la
    feuille lit sur le `StatsComponent` du caster. Le parametre n'existe que pour les call-sites
    dont l'`AbilityState` est celui d'un PASSIF (la mine Haywire)."""
    spawn = Spawn(might_from_below_spawn_tiles(), MIGHT_FROM_BELOW_ID,
                  on_appearance=PerformAIAttack(ActiveTarget()),
                  unit_id_constant="unitId")                        # GetStringConstant(config, 0)
    return If(IsAlive(Caster()),
              Group(spawn, group_id=int(GroupType.Ability_Summon),  # 0x22
                    targets_sel=Caster()),
              None)                                                 # le 4e argument natif = null


class MightFromBelowAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MightFromBelowAbility$$ExecuteBehaviour`
    (id 1165, `genesPatriarch` « The Patermine », HERO Genestealer Cults) -- cf. docstring module.

    TROIS arbres joues dans l'ordre natif, chacun sur un `AbilityEntities` reconstruit (mirror de la
    ref d'etat native, cf. l'en-tete). Turn-flags = defauts de la base (1165 est absente des
    overrides `SetsEndTurnFlags` / `SetsActiveAbilityUsedFlag` : le cast termine le tour)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MightFromBelow)             # 1165
    ABILITY_ID = MIGHT_FROM_BELOW_ID

    # GATE DE CIBLE -- FORME « STATIC-COPY » : `MightFromBelowAbility$$.ctor` n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les 0x40 octets du preset
    # `<TargetingOptions statics>+0x40` dans un local et le passe tel quel a
    # `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(this, &opts, 0)`. Le masque EFFECTIF est
    # donc la constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor`, LUE a ce
    # preset (et relue pour CETTE ability, jamais recopiee d'une voisine) :
    #     +0x40 isSelfCasting    = 0
    #     +0x48 range           <- `<TargetingRange statics>+0x30` = RANGE_ADJACENT
    #     +0x60 forceMeleeTarget = 1 = RangedBool.False
    #     +0x68 rules            = 0x4000, et RIEN d'autre
    # Decomposition EXHAUSTIVE (`IdunBattle.Core.Services.TargetingRule`), somme = 0x4000 :
    #     0x4000  TargetIsEnemy  -> PORTE (refus sur soi-meme / un allie)
    # Aucun `TargetMatchesDynamicRule` -> aucune regle dynamique a surcharger (et 1165 n'a pas de
    # `$$GetDynamicInvalidTargetReason` dans le binaire).
    # ⚠ Le preset VOISIN `+0x180` porte `rules = 0x4002` et une portee `RANGE_FROM_CONFIG` : recopier
    # le masque d'une voisine de ce bloc aurait change A LA FOIS le masque et le regime de portee.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # `IdunBattle.Configuration.AbilityConfiguration$$GetDamageProfile(config@+0x60)` ->
        # `DSLSelectors$$Direct(profil)`, le 4e argument de la feuille. Lu au kit (`Psychic`).
        import gameconfig as GC                                     # noqa: PLC0415
        profile = ((GC.ability(MIGHT_FROM_BELOW_ID) or {}).get("constants") or {}).get(
            "damageProfile") or "Psychic"
        ectx = ExecutionContext(state=state, rng=state.rng)

        # [1] Execute( Group(attack, Ability_Attack) )
        might_from_below_attack_tree(profile).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        # [2] Execute( KillDeadUnits(Caster, UnitsDamagedThisPhase(Caster)) )
        might_from_below_kill_tree().execute(
            entities_from_state(state, caster_id, target_id), ectx)
        # [3] Execute( IfAlive(Caster, Group(spawn, Ability_Summon)) ) -- l'`AbilityEntities` est
        #     RECONSTRUIT : le decoy pose par `CosmicHorror_OnKillAbility` pendant [1] doit etre
        #     visible du selecteur `AdjacentFriends`, comme il l'est de la ref d'etat native.
        summon_entities = entities_from_state(state, caster_id, target_id)
        might_from_below_summon_tree().execute(summon_entities, ectx)

        # `attack` est THREADE tel quel : la validation de cette ability compare la SEQUENCE coup
        # par coup (`per_hit`), pas un total -- cinq coups dont la somme coincide par compensation
        # passeraient un test de total.
        attacks = [{"target": p.get("target"), "total": p.get("total"),
                    "attack": p.get("attack"),
                    "per_hit": list(((p.get("attack") or {}).get("per_hit")) or ()),
                    "hits": len((p.get("attack") or {}).get("per_hit") or [])}
                   for name, p in ectx.emitted if name == "AttackWithAttackDamage"]
        summons = [{"unit": p.get("unit"), "tile": p.get("tile")}
                   for name, p in ectx.emitted if name == "SpawnUnit"]
        downed = [uid for name, p in ectx.emitted if name == "KillDeadUnits"
                  for uid in (p.get("downed") or ())]
        summon_attacks = [a for name, p in ectx.emitted if name == "PerformAIAttack"
                          for a in (p.get("attacks") or ())]
        return {"ability": MIGHT_FROM_BELOW_ID, "caster": caster_id, "target": target_id,
                "attacks": attacks, "downed": downed, "summons": summons,
                "summon_attacks": summon_attacks,
                "groups": [int(GroupType.Ability_Attack), int(GroupType.Ability_Summon)],
                "dsl": True}


__all__ = ["MIGHT_FROM_BELOW_ID", "MightFromBelowAbility", "might_from_below_attack_tree",
           "might_from_below_kill_tree", "might_from_below_spawn_tiles",
           "might_from_below_summon_tree"]
