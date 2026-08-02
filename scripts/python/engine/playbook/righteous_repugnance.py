"""`IdunBattle.AI.Playbook.Loki.RighteousRepugnancePlaybook` -- face ATTACK du triggered
`RighteousRepugnance` (1107), passif d'`adeptMorvenn` << Morvenn Vahl >> (HERO, AU POOL) et de
3 npc (`adeptBossMorvenn`, `adeptBossMorvennLHE`, `adeptNpcMorvenn`) : 4 porteurs, tete de liste
des residus ATTACK de #419-r1.

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(34), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae, BarbedOvipositor, Neuroparasite, SaviorProtocols,
AvalancheOfMuscle, Boltstorm, FireOfAbsolution, CosmicHorror, LightImUp et RapidFire
(`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

## (!) L'id `1107` recouvre QUATRE artefacts natifs distincts -- inventaire etabli, pas suppose

| enum QUALIFIE                                  | artefact                                          |
|---|---|
| `TriggeredAbilityType.RighteousRepugnance = 1107` | **CE playbook** + `RighteousRepugnanceAbility`  |
| `ActiveAbilityType.Reveal = 1107`                 | sans rapport                                    |
| `EffectType.PathOfCommand_ExtraCrit = 1107`       | l'axe CRIT d'un effet, traite ailleurs          |
| `TriggeredAbilityType.SagaOfTheWarriorBorn = 1182`| homonyme INVERSE du couple ci-dessous           |

Et le passif porte, en plus, un CINQUIEME et un SIXIEME artefact sous un **autre** id :
`ActiveAbilityType.RighteousRepugnance_NormalAttack = 1182` (le mold d'attaque normale
`RighteousRepugnance_NormalAttackAbility$$PredictAttack` / `$$GetAdditionalDamagePrediction`, porte
et confronte par #446-r3, corrige par #509) et `IdunBattle.AI.Playbook.Loki.
RighteousRepugnance_NormalAttackPlaybook` (le playbook de cette ability ACTIVE-la). **Aucun des deux
n'est l'artefact de ce module** : ils vivent sous 1182, pas sous 1107.

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.RighteousRepugnancePlaybook$$CalculateAttackUtilityInStepsInternal`
monte la SM `d__3` -- disposition LUE dans ce wrapper, jamais par analogie, car elle est l'INVERSE
de celle de `CosmicHorror`/`Boltstorm` sur les deux premiers champs : `sm@+0x20 = this` (le
PLAYBOOK), `sm@+0x28 = case`, `sm@+0x30 = getUtilityVal` (le delegue scorer), `sm@+0x10 = 0`. Le
corps est `RighteousRepugnancePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$
MoveNext`, **UN SEUL** `yield` :

    var sel = RighteousRepugnanceAbility.GetAdditionalTargets(this.<DSL>);
    var entities = new AbilityEntities { Caster = case.Caster,      // memset 0x128 a 0 d'abord
                                         Target = case.Target };   // Actor ET Owner restent NULS
    var units = sel.SelectUniqueUnits(entities, (UnitSelectionType)3);
    yield return Fix64.op_Implicit(GetUtilityValue("RIGHTEOUSREPUGNANCE_AdjacentEnemy")
                                   * units.Count);

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RighteousRepugnanceAbility$$GetAdditionalTargets`
(l'arbre de ciblage, decompile lu integralement) :

    AdjacentEnemies(dsl.Selectors, Caster@0x48, unique: 1, selectionType: 3)
  & AdjacentUnits  (dsl.Selectors, Target@0x60, unique: 1, selectionType: 3)

en developpant les deux primitives de `IdunBattleLogic.Entities.DSLSelectors` (lues aussi) :

    AdjacentEnemies(u) = Enemies(u, Units(AdjacentTiles(u), ...) - u, sel)
    AdjacentUnits(o)   =           Units(AdjacentTiles(o), ...) - o

Six lectures qui ne se devinent pas, et dont aucune ne se generalise depuis un voisin de la liste :

1. **La sortie est un PRODUIT poids x CARDINAL**, pas un terme plat -- meme FORME que `Boltstorm`,
   mais **pas le meme cardinal** : l'arbre d'ici n'a **AUCUN `op_Addition` avec `Target@0x60`**.
   La cible principale n'est donc **jamais comptee**, et une cible isolee vaut **0** (chez
   `Boltstorm`, toute cible valait deja 1 x le poids). Transporter la conclusion du voisin aurait
   pose un plancher de 10 qui n'existe pas.

2. **L'intersection est une DOUBLE adjacence**, et c'est litteralement le texte i2 du passif
   (<< all enemy units adjacent to both the target and to Morvenn Vahl >>) : ennemi DU CASTER,
   adjacent au CASTER (volet gauche) ET adjacent a la CIBLE (volet droit). Les deux
   `op_Subtraction` internes retirent respectivement le caster et la cible, donc ni l'un ni l'autre
   n'entre au compte -- sans qu'aucun test explicite ne soit ecrit.

3. **Le terme ne depend PAS de la tuile d'attaque balayee.** La struct `AbilityEntities` que le
   corps construit est `memset` a 0 puis ne recoit QUE `Caster` (`+0x08` <- `case@+0x10`) et
   `Target` (`+0x10` <- `case@+0x20`) : `Owner` (`+0x18`), `TargetTile` (`+0x30`) et `CasterTile`
   (`+0x40`) restent NULS, et `case.CasterPosition` (`UtilityAttackCase@+0x18`) n'est jamais lu. Or
   `AdjacentTiles` ancre sur `EntityExtensions.IterateTiles(sujet)`, donc sur la MainTile REELLE --
   meme quirk que `boltstorm.count_all_targets`, a l'oppose de `LightImUp` (qui, lui, alimente
   `CasterTile`). Le terme discrimine donc les CIBLES entre elles, jamais les tuiles d'une meme
   cible. ⚠ Ce module ecrit MOINS de champs que `Boltstorm`, qui posait en plus `Owner = Caster` :
   sans consequence ici (l'arbre ne lit ni `Owner@0x30` ni `Actor@0x40`), mais c'est une lecture,
   pas une recopie.

4. **`AdjacentTiles` est le ring-1 STRICT, pas `AreTilesAdjacent`.** Le selecteur passe par
   `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, qui parcourt
   la liste d'adjacence STOCKEE (donc ne rend JAMAIS la tuile centrale) sous la porte
   d'elevation INCONDITIONNELLE `|delta| < 2`. Foyer du port : `battle_query.is_adjacent` --
   surtout PAS `are_entities_adjacent`, qui porte le court-circuit d'identite `t1 == t2` (#433-r1)
   et ferait compter la cible elle-meme dans le volet droit.

5. **Le poids est `RIGHTEOUSREPUGNANCE_AdjacentEnemy`** (`Utilities.Default.TriggeredAbilities`),
   = **10** au seed BC courant. Le literal est **LU**, pas devine :
   `probe_212_bc_key_literals.py --symbol '<le d__3$$MoveNext>'` resout le slot `+0x33b22a0` --
   exactement le `DAT_` du call-site du delegue -- vers cette chaine, et c'est la SEULE cle
   `RIGHTEOUSREPUGNANCE_*` du BC.

6. **Le playbook estime EXACTEMENT ce que le combat va frapper en plus.**
   `RighteousRepugnanceAbility$$GetAdditionalTargets` n'a que DEUX appelants (xrefs mesurees) : ce
   `MoveNext` et `IdunBattleLogic.Entities.Abilities.Active.Loki.RighteousRepugnance_
   NormalAttackAbility$$ExecuteRighteousRepugnance`, qui l'enroule dans un
   `DSLBehaviors.Foreach(sel, t => GetAdditionalTargetsAttackBehavior(t, abilityState))` execute en
   `ExecuteAtomic`. Le MEME arbre sert donc la decision et l'execution -- et la cible principale,
   absente de l'arbre, est traitee a part par `ExecuteNormalAttack` + le fold de #446-r3.

## Face MOVE : `yield Fix64(0)` CONSTANT -- decompile LU, ce n'est pas un trou

`RighteousRepugnancePlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` a UN
seul etat, et cet etat est `Fix64.op_Implicit(0)` ; le wrapper
`$$CalculateMovementUtilityInStepsInternal` n'ecrit meme NI le case NI le playbook dans la SM
(state seul). `probe_212_bc_key_literals.py` confirme : AUCUN string literal lu, ni la face MOVE ni
le `.ctor`. Elle n'entre donc pas au registre `TRIGGERED_MOVE_PLAYBOOKS`, et cette absence EST le
comportement natif -- meme forme que `Lakrimae`, `BarbedOvipositor`, `Neuroparasite`, `Boltstorm`,
`FireOfAbsolution` et `CosmicHorror`.

## Substrat cote port -- ce que ce terme exige, et qui l'ecrit

Le corps ne lit ni stats, ni effets, ni prediction : uniquement les POSITIONS et les CAMPS. Les deux
canaux existent deja dans la `Scene` (`pos_by_id` + `units[].alive` + `units[].team`) -- aucune
piece neuve n'est requise, donc pas de patron << porte + INERTE >>. `attack_tile` et `prediction`
(`UtilityAttackCase@+0x28`, canal #438) sont ACCEPTES et IGNORES, comme le corps natif qui ne lit
ni `case@+0x18` ni `case@+0x28`.
"""
from __future__ import annotations

from .. import battle_query as bq

from ..entities.triggered_ability_type import TriggeredAbilityType

# L'UNIQUE string literal de la face ATTACK, resolu par `probe_212_bc_key_literals.py` sur le
# symbole du `d__3$$MoveNext` (slot `+0x33b22a0`) ; = 10 sur le seed BC courant, SEULE cle
# `RIGHTEOUSREPUGNANCE_*` de `Utilities.Default.TriggeredAbilities`.
_WEIGHT_KEY = "RIGHTEOUSREPUGNANCE_AdjacentEnemy"


def count_additional_targets(scene, caster_uid: int, target_uid: int) -> int:
    """`RighteousRepugnanceAbility.GetAdditionalTargets(dsl).SelectUniqueUnits(entities, 3).Count`
    -- le CARDINAL de l'arbre de ciblage, evalue contre l'`AbilityEntities` que le playbook
    construit (`Caster = case.Caster`, `Target = case.Target`, TOUT le reste NUL -- cf. en-tete
    point 3).

    = |{ u : `Enemies(Caster)`(u) ET `AdjacentUnits(Caster)`(u) ET `AdjacentUnits(Target)`(u) }|,
    soit les ennemis du caster, VIVANTS, adjacents A LA FOIS a la tuile REELLE du caster et a celle
    de la cible. Ni le caster ni la cible n'y figurent : les deux `op_Subtraction` de l'arbre les
    retirent, et la geometrie le ferait de toute facon (`is_adjacent` mirroir `IterateAdjacentTiles`,
    qui ne rend jamais la tuile centrale -- cf. en-tete point 4). On ne pose donc AUCUN gate
    explicite dessus : ce serait ajouter une regle que le natif n'a pas.

    Les unites MORTES sont exclues parce que `AdjacentTiles` + `Units` resolvent des OCCUPANTS DE
    TUILE et qu'un mort a quitte la sienne (meme regle que `dsl/base.py::_within` (#57m),
    `boltstorm.count_all_targets` et `fire_of_absolution.count_adjacent_by_camp`).

    Degradations, toutes nommees et rendant `0` -- le natif, lui, n'a aucune sortie anticipee : il
    deref sans garde et tombe sur une levee si le case ou le composant manque. On ne mirroir pas une
    levee : caster ou cible inconnus -> aucun terme, meme degradation que l'absence du playbook au
    registre."""
    if caster_uid is None or target_uid is None:
        return 0
    cpos = scene.pos(caster_uid)
    tpos = scene.pos(target_uid)
    cteam = scene.team(caster_uid)
    if cpos is None or tpos is None or cteam is None:
        return 0
    elev = getattr(scene, "elev_by_pos", None)
    n = 0
    for u in (scene.units or ()):
        uid = u.get("id")
        if uid is None or not u.get("alive"):
            continue
        # `Enemies(Caster@0x48, ..., 3)` : equipe != celle du caster (meme substrat `scene.team` que
        # tous les `IsFriend`/`IsEnemy` deja portes). Le caster est ecarte par ce filtre meme.
        if u.get("team") == cteam:
            continue
        p = scene.pos(uid)
        if p is None:
            continue
        # `AdjacentEnemies(Caster@0x48)` -> `Units(AdjacentTiles(caster))` : ring-1 hex AVEC la porte
        # d'elevation `|delta| < 2`.
        if not bq.is_adjacent(cpos, p, elev):
            continue
        # `AdjacentUnits(Target@0x60, unique: 1, sel: 3)` = `Units(AdjacentTiles(target)) - target` :
        # meme ring-1, meme porte. `is_adjacent` etant STRICT, la cible s'auto-exclut.
        if not bq.is_adjacent(tpos, p, elev):
            continue
        n += 1
    return n


class RighteousRepugnancePlaybook:
    """`RighteousRepugnancePlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1107 -- l'id passe
    par `$$.ctor` a la base `TriggeredAbilityPlaybook<T>` est bien `0x453`). Seule la face ATTACK a
    un corps ; la face MOVE est un `yield 0` constant au natif (cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.RighteousRepugnance)   # 0x453 = 1107

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror de `<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` (cf. en-tete) : le poids
        `RIGHTEOUSREPUGNANCE_AdjacentEnemy` MULTIPLIE par le cardinal de
        `RighteousRepugnanceAbility.GetAdditionalTargets`.

        `attack_tile` est accepte et IGNORE : la struct `AbilityEntities` du corps natif ne porte NI
        `CasterTile` NI `TargetTile` (memset a 0), et les deux selecteurs geometriques ancrent sur la
        MainTile REELLE -- le terme ne varie donc pas d'une tuile d'attaque a l'autre (en-tete,
        point 3). `prediction` est accepte et IGNORE de meme : le corps ne lit que `case@+0x10`
        (Caster) et `case@+0x20` (Target), jamais `case.DamagePrediction` (`UtilityAttackCase@+0x28`).
        """
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        n = count_additional_targets(sc, attacker_uid, case_tgt_id)
        if n == 0:
            return 0.0
        return float(ctx.wt.triggered(_WEIGHT_KEY)) * n     # `GetUtilityValue(cle) * count`


__all__ = ["RighteousRepugnancePlaybook", "count_additional_targets"]
