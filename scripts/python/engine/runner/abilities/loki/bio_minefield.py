"""`1144 BioMinefield` -- l'ability active de la MoW `tyranBiovore` (le second porteur,
`tyranNpcMowBiovore`, est npc).

ARTEFACT NATIF : `IdunBattleLogic.Entities.Abilities.Active.Loki.BioMinefieldAbility$$
ExecuteBehaviour` -- un ARBRE DSL pur (17 primitives `DSLSelectors`/`DSLBehaviors`/`DSLTriggers`/
`DSLFormulas`, recensement corrobore par `docs/rl/dsl-usage/dsl-usage-owners.tsv`). Rien n'y est
recable a la main : le ciblage, la condition et les deux branches EMERGENT des noeuds.

⚠ **L'AUDIT LA CLASSAIT `SUMMON`, ET CE N'EST QUE LA MOITIE DE SA FACE.** La colonne SUMMON de
`docs/rl/combat-ability-coverage.md` derive du KIT gameconfig, pas du behaviour. Le cast fait TROIS
choses, dont le summon n'est qu'UNE BRANCHE sur deux :

    Execute(   AddEffect(EffectType.BioMinefield_Target, <abilityStateRef>,
                         source  = Owner@DSLSelectors+0x30,
                         targets = Target@DSLSelectors+0x60,
                         turns   = <DSLFormulas+0x20> = Direct(1))
             & If( AmountIsEqualOrGreater( Count(Alive(Children(Owner))),
                                           Direct(GetNumberConstant(nrOfSummons)) ),
                   then =   PerformAIMovement( EntitiesWithoutEffects(Alive(Children(Owner)),
                                                    [EffectType.Taunted_BlockMovement]),
                                               Direct(1), <ability+0xf0 : UtilityDefinition> )
                          & Kill( Filter(Alive(Children(Owner)),
                                         HasAdjacentEnemies(Subject@+0x68, Tiles(Subject@+0x68),
                                                            includeObjects: false,
                                                            includeSteppables: false)),
                                  <le MEME selecteur>, options: 0 ),
                   else =   Spawn( parent = Caster@DSLSelectors+0x48,
                                   tiles  = RandomAdjacentFreeTile(Target@+0x60,
                                                Direct(GetNumberConstant(nrOfSummons_2))),
                                   unitId = GetStringConstant(unitId),
                                   options= SpawnUnitOptions.WithStatsFromConfig(config,
                                                abilityState, Get(abilityState.Level),
                                                Get(abilityState.VariableMultiplierPercentage)) ) ) )

soit, en clair : **on MARQUE la cible** (effet `1315`, 1 tour) ; puis **si le Biovore a deja au moins
`nrOfSummons` mines vivantes**, elles AVANCENT (celles qui ne sont pas `Taunted_BlockMovement`) et
celles qui touchent un ennemi EXPLOSENT (`Kill` sur elles-memes) ; **sinon** on POSE `nrOfSummons_2`
mines sur des tuiles libres adjacentes a la CIBLE. Config LUE (`units.abilities.BioMinefield.
constants`) : `unitId = tyranSmnSporeMine`, `nrOfSummons = 3`, `nrOfSummons_2 = 3`.

FACES RECENSEES sur `rnca9r7q6c`, et leur verdict :
  * `$$ExecuteBehaviour`  -- VIVANTE (vtable). Portee ici.
  * `$$AliveChildren` / `$$MoveChildren` / `$$AttackWithChildren` / `$$SpawnUnits` -- **DEAD comme
    corps standalone** : leurs SEULES xrefs sont des DATA (bloc `methodPointers` + metadata),
    AUCUN `CALL`. IL2CPP les a INLINEES dans `ExecuteBehaviour`, dont elles sont exactement les
    quatre sous-arbres -- elles CORROBORENT donc la structure ci-dessus, sous-arbre par
    sous-arbre, et c'est a ce titre qu'elles ont ete relues.
  * `IdunBattle.AI.Playbook.Loki.BioMinefieldPlaybook` -- VIVANTE, enregistree
    (`metadata/active_playbook_builders.tsv` : `active 1144 -> BioMinefieldPlaybook`). Portee dans
    `engine/playbook/noncomparable/bio_minefield.py`.
  * `IdunBattle.AI.Utilities.BioMinefield_MoveTowardsTargetUtility` -- **DEJA PORTEE**
    (`engine/utilities/tile.py`, `UtilityType.BioMinefield_MoveTowardsTarget` = 62, enregistree
    dans `TILE_LEAVES`).
  * `IdunBattle.View.AbilityConfigs.Loki.BioMinefieldVisuals` -- couche VUE, hors moteur.
  * **AUCUN `CreateTrigger`, `CreateBehaviour`, ni `Effect$$Create*`** : l'effet `1315
    BioMinefield_Target` n'a AUCUNE classe native dans `ghidra/functions.tsv` -- c'est un effet
    MARQUEUR, instancie par `AddEffectBehaviour` a partir de son seul `EffectType`, et son unique
    lecteur est la feuille d'utilite 62 (`_ABILITY_ID = 1315`).

(#939)
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..base import ActiveAbility
from ..targeting import RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE, TargetingOptions
from ..targeting_rule import TargetingRule as TR
from ....dsl.base import Const
from ....dsl.effects import ExecutionContext
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.effect_type import EffectType
from ....entities.behaviours import If, Seq
from ....entities.formulas import Count
from ....entities.selectors.accessors import Owner, Subject, Target
from ....entities.selectors.composites import random_adjacent_free_tile
from ....entities.selectors.geometry import EntitiesWithoutEffects
from ....entities.selectors.tiles import Caster, ChildrenOf
from ....entities.selectors.units import Alive, Filter, Tiles
from ....entities.triggers import AmountIsEqualOrGreater, has_adjacent_enemies
from ....utilities.utility_type import UtilityType
from ..behaviours.ai_control import PerformAIMovement
from ..behaviours.context import entities_from_state
from ..behaviours.effects import AddEffect
from ..behaviours.lifecycle import Kill
from ..behaviours.summon import Spawn

if TYPE_CHECKING:                                        # pragma: no cover
    from ...state import State

BIO_MINEFIELD_ID = "BioMinefield"

#: Le `UtilityDefinition` range a `<ability>+0xf0` par `BioMinefieldAbility$$.ctor`, et passe en 3e
#: argument de `DSLBehaviors$$PerformAIMovement`. Le ctor alloue un TABLEAU d'UN element, y ecrit
#: `new IdunBattleLogic.AI.Utilities.UtilityBucket(0x3e, default)` puis construit le
#: `UtilityDefinition` sur ce tableau. `0x3e` = 62 = `UtilityType.BioMinefield_MoveTowardsTarget` --
#: l'utilite est donc IMPOSEE au scoring de tuile, et elle est la SEULE (elle REMPLACE le playbook
#: de mouvement par defaut, elle ne s'y ajoute pas).
BIO_MINEFIELD_MOVE_UTILITY = (int(UtilityType.BioMinefield_MoveTowardsTarget),)      # 62


def _constant(name: str, default: int) -> int:
    """`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(config, <AbilityConstantType>)`
    lu sur `units.abilities.BioMinefield.constants`. Les DEUX cles utilisees par le cast sont
    NOMMEES par leur membre au call-site ci-dessous ; ce helper ne fait que la conversion."""
    import gameconfig as GC                              # noqa: PLC0415 (cf. voisins de ce paquet)
    raw = ((GC.ability(BIO_MINEFIELD_ID) or {}).get("constants") or {}).get(name)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def bio_minefield_alive_children():
    """`BioMinefieldAbility$$AliveChildren` (helper INLINE, cf. docstring de module) :
    `Alive(Children(Owner@DSLSelectors+0x30))`.

    ⚠ **`DSLSelectors$$Children(parent)` EST `ChildrenOf`, PAS `Children`.** Deux primitives
    natives homonymes coexistent : `IdunBattleLogic.Entities.DSLSelectors$$Children` (SANS argument, l'accumulateur des summons
    produits par CE cast) et `DSLSelectors$$Children(this, parent)` (AVEC un argument, les unites
    dont `parent` est le parent). Le call-site passe `<selectors>+0x30` -- il a donc un argument.
    Brancher la premiere ici rendrait un ensemble TOUJOURS VIDE au premier cast (rien n'a encore ete
    spawne), donc la condition serait TOUJOURS fausse et la branche `then` INATTEIGNABLE -- le no-op
    invisible que ce port ferme. (Le piege est celui de #590.)"""
    return Alive(ChildrenOf(Owner()))


def bio_minefield_move_children():
    """`BioMinefieldAbility$$MoveChildren` (helper INLINE) :

        PerformAIMovement( EntitiesWithoutEffects(AliveChildren(), [EffectType.Taunted_BlockMovement]),
                           Direct(1), <ability+0xf0> )

    Le tableau d'`EffectType` est alloue AVEC UN SEUL element, ecrit a `+0x20` = `0x19` = 25 =
    `Taunted_BlockMovement` (LU : `*(array + 0x20) = 0x19`). Les mines TAUNTEES ne bougent donc pas.
    `Direct(1)` = le budget de deplacement : **une tuile**."""
    return PerformAIMovement(
        EntitiesWithoutEffects(bio_minefield_alive_children(),
                               [int(EffectType.Taunted_BlockMovement)]),   # 25
        Const(1),
        override_utility=BIO_MINEFIELD_MOVE_UTILITY)


def bio_minefield_attack_with_children():
    """`BioMinefieldAbility$$AttackWithChildren` (helper INLINE) :

        Kill( killer  = Filter(AliveChildren(), HasAdjacentEnemies(<sel>+0x68, Tiles(<sel>+0x68),
                                                                   false, false)),
              targets = <LE MEME selecteur>,
              options = 0 )

    ⚠ **`killer` ET `targets` sont LE MEME sous-arbre** (`Kill(pvVar13, pvVar13, 0)` -- la variable
    est passee DEUX FOIS, LU au decompile) : les mines adjacentes a un ennemi se tuent
    ELLES-MEMES. C'est l'EXPLOSION de la mine, et le DEGAT qu'elle inflige n'est PAS ici -- il
    appartient au kit de `tyranSmnSporeMine` (declenche a sa mort), pas a `1144`.

    `<sel>+0x68` = `Subject` -- le singleton que `Filter` lie a l'element courant (le port lie
    `subject` ET `active_target`, cf. `selectors.units.Filter`)."""
    mines = bio_minefield_alive_children()
    exploding = Filter(mines, has_adjacent_enemies(Subject(), Tiles(Subject())))
    return Kill(exploding, exploding)


def bio_minefield_spawn_units():
    """`BioMinefieldAbility$$SpawnUnits(abilityState)` (helper INLINE) :

        Spawn( parent  = Caster@DSLSelectors+0x48,
               tiles   = RandomAdjacentFreeTile(Target@+0x60, Direct(GetNumberConstant(nrOfSummons_2))),
               unitId  = GetStringConstant(AbilityConstantType.unitId),
               options = SpawnUnitOptions$$WithStatsFromConfig(config, abilityState,
                                                               Get(abilityState.<f0>),
                                                               Get(abilityState.<f1>)) )

    ⚠ **LES DEUX FORMULES DE `WithStatsFromConfig` SONT EXACTEMENT SON PROPRE FALLBACK, ET C'EST
    UNE LECTURE.** La surcharge a 4 arguments delegue a celle a 5, dont le corps fait :

        if (abilitiesLevel == null)               abilitiesLevel = new Direct(abilityState.<f0>);
        if (variableMultiplierPercentage == null) variableMultiplier... = new Direct(abilityState.<f1>);

    Or `1144` passe precisement `Get(abilityState.<f0>)` et `Get(abilityState.<f1>)` -- soit les
    memes valeurs que le fallback. L'effet est donc STRICTEMENT identique a `WithStatsFromConfig(
    config, abilityState, null, null)`, la forme qu'utilise `MightFromBelowAbility$$
    ExecuteBehaviour` et que le port rend par le DEFAUT de `Spawn` (`ability_state=None` -> niveau
    et multiplicateur lus sur le `StatsComponent` du caster, c'est-a-dire l'`AbilityState` de CE
    cast). Passer un couple explicite ici n'ajouterait rien et ferait croire a une divergence.

    `unit_id_constant="unitId"` : le call-site passe `GetStringConstant(config, 0)` et
    `AbilityConstantType.unitId == 0` -- ce n'est donc PAS `unitToSpawn` (8)."""
    return Spawn(
        random_adjacent_free_tile(Target(), Const(_constant("nrOfSummons_2", 3))),
        BIO_MINEFIELD_ID,
        unit_id_constant="unitId")                        # AbilityConstantType.unitId = 0


def bio_minefield_tree():
    """L'arbre ENTIER de `BioMinefieldAbility$$ExecuteBehaviour`, dans l'ordre de construction natif
    (cf. la transcription en tete de module). Le `Seq` externe est
    `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd(AddEffect, If)` -- l'AddEffect passe donc
    TOUJOURS, quelle que soit la branche prise."""
    marque = AddEffect(int(EffectType.BioMinefield_Target),       # 1315
                       BIO_MINEFIELD_ID, Target(),
                       # `turns = <DSLFormulas+0x20>` = `Direct(1)`, deja en TOURS (LU dans
                       # `IdunBattleLogic.Entities.DSLFormulas$$.ctor`, qui alloue
                       # `+0x18 Direct(0) . +0x20 Direct(1) . +0x28 Direct(2) . +0x30 Direct(100)
                       # . +0x38 Direct(-1)`).
                       duration_turns=1,
                       # `source = Owner@DSLSelectors+0x30` : l'effet est SOURCE par le caster
                       # (c'est ce que la feuille d'utilite 62 relira pour designer la cible).
                       source_ref=Owner())
    assez_de_mines = AmountIsEqualOrGreater(
        Count(bio_minefield_alive_children()),
        Const(_constant("nrOfSummons", 3)))                # AbilityConstantType.nrOfSummons = 16
    return Seq(marque,
               If(assez_de_mines,
                  Seq(bio_minefield_move_children(), bio_minefield_attack_with_children()),
                  bio_minefield_spawn_units()))


class BioMinefieldAbility(ActiveAbility):
    """`1144 BioMinefield` (`tyranBiovore`). cf. docstring de module pour l'arbre et les verdicts
    de face.

    `TARGETING_OPTIONS` -- `BioMinefieldAbility$$.ctor` appelle la surcharge FLAGS-DIRECTS a 7
    parametres : `TargetingOptions$$.ctor(&opts, isSelfCasting: 0, &<TargetingRange statics+0x48>,
    forceMeleeTarget: 1, rules: 0x40004020, 0, 0)`. Le litteral EST le masque (ce corps ecrit
    `this+0x28 <- rules`, sans `|` avec un preset).
        0x40004020 = `TargetHasFreeAdjacentTile` (0x20) | `TargetIsEnemy` (0x4000)
                     | `AllowNullCasterTile` (0x40000000)          -- AUCUN bit residuel
        `<TargetingRange statics+0x48>` = RANGE_WHOLE_BOARD.
    Le bit `AllowNullCasterTile` est la signature d'une MoW (une machine n'a aucune tuile).
    ⚠ Ce masque VIVAIT dans `TARGETING_OPTIONS_UNPORTED` (lot HORS REGISTRE de
    `#433-r4-r2-r1-r2-r2-r1-r1-r1`) ; il MIGRE ici avec la face COMBAT, comme l'exige le contrat de
    disjonction (`test_433_..._source_tile_zone_offline.py::
    test_les_deux_sources_de_masques_restent_disjointes`). Valeurs INCHANGEES par la migration : le
    ctor a ete RELU par cette tranche et il CONCORDE champ pour champ avec la lecture anterieure --
    deux lectures independantes, meme resultat.

    `ABILITY_ATTACK_TYPE` -- `AActiveAbility$$.ctor(this, &opts, 2)` : le 3e argument est
    l'`AbilityAttackType`, et il vaut **2 = `Others`** (LU au ctor, pas deduit du profil de degat --
    l'ability n'inflige aucun degat direct)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.BioMinefield)    # 1144
    ABILITY_ID = BIO_MINEFIELD_ID
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetHasFreeAdjacentTile | TR.TargetIsEnemy | TR.AllowNullCasterTile,
        self_cast=False, range=RANGE_WHOLE_BOARD,
        force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        # UN `AbilityEntities` par `AActiveAbility$$Execute` : le natif n'en a qu'UN ici (le cast
        # est un SEUL `Execute`), donc un seul `entities_from_state` -- mais il porte une REF
        # d'etat, la ou le `DslContext` du port FIGE sa liste `units` a la construction. La feuille
        # `Spawn` compense en poussant chaque enfant dans `entities.units` (liste partagee), ce qui
        # rend les summons visibles aux etages AVAL du meme arbre.
        entities = entities_from_state(state, caster_id, target_id)
        bio_minefield_tree().execute(entities, ectx)

        spawns = [{"unit": p.get("unit"), "tile": p.get("tile")}
                  for name, p in ectx.emitted if name == "SpawnUnit"]
        killed = [p for name, p in ectx.emitted if name == "Kill"]
        moved = [p for name, p in ectx.emitted if name == "PerformAIMovement"]
        effects = [p for name, p in ectx.emitted if name == "AddEffect"]
        return {"ability": self.ABILITY_TYPE, "caster": caster_id, "target": target_id,
                "effects": effects, "summons": spawns, "killed": killed, "moved": moved,
                # La BRANCHE prise, pour que le cliquet puisse la lire sans re-deriver l'etat :
                # `spawn` = `else` (moins de `nrOfSummons` mines vivantes), `mines` = `then`.
                "branch": "spawn" if spawns else "mines",
                "dsl": True}
