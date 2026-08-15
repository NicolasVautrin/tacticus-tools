"""UnstoppableMomentumReworked (1152, `orksNob` « Tanksmasha », Orks) -- CHARGE-DRIVER EN LIGNE.

Namespace natif `IdunBattleLogic.Entities.Abilities.Active.Loki.UnstoppableMomentumReworkedAbility`.
Classee « charge-driver en ligne IMPERATIF » par case-220 §6.13 ; la RE ci-dessous CONFIRME la
classification : le natif n'est PAS un arbre `DSLFactory` unique, c'est une BOUCLE imperative
(`ExecuteBehaviourStep`, <= `this+0xf0` = 10 iterations) qui execute a chaque pas un PETIT arbre DSL
(`AActiveAbility$$Execute(<arbre>)`). Frontiere #149 respectee : l'ossature (boucle, gates de tuile,
choix de la tuile de poussee) est IMPERATIVE parce que le natif l'est ; les EFFETS (attaque, pose
d'effet, retrait d'effet, move, switch, push) passent par les feuilles DSL deja portees.

i2 / gameconfig 1152 (`Melee`, profil `DirectDamage{PiercingRatio:100}`, `nrOfHits=1`,
`initialCooldownTurns=1`, `effectTurns=1`, `effectTurns_2=1`) :

    « Charges in one of 6 directions and keeps moving in a straight line until he hits an obstacle
      or a Big Target. Any enemies hit by the charge take 1x <dmg> Direct Damage, increased by
      <extraDmg> Damage for each hex traversed from the starting hex to the enemy. Affected enemies
      get pushed and Suppressed for 1 round. A Big Target is Stunned for 1 round instead. Friendly
      units are also displaced, but take no damage or negative effects. »

RE (build rnca9r7q6c, DECOMPILE MIRROR).

`...UnstoppableMomentumReworkedAbility$$.ctor` :

    this+0xf0 = 10                                      // MAX_CHARGE_TILES (longueur de ligne)
    TargetingOptions..ctor(&opts, selfCast: 0, &<TargetingRange statics+0x30>,
                           forceMeleeTarget: 1, rules: 0x10120040, 0, 0)
    AActiveAbility..ctor(this, &opts, 0)                // AbilityAttackType.DirectTargetAttack

`...UnstoppableMomentumReworkedAbility$$CanStillBeUsed(caster, amountOfTimesAlreadyUsed)` :
    `return amountOfTimesAlreadyUsed == 0` (une seule fois par tour ; c'est le DEFAUT du port).

`...UnstoppableMomentumReworkedAbility$$ExecuteBehaviour(abilityState, entities)` :

    Execute( AddFlag(Caster@0x48, 0x19 = UnitFlag.Undisplaceable) )          // 1
    line   = TilesBehindInLine( CasterTile@0x50, Target@0x60,
                                settings{+0x10 = 1, +0x11 = 1}, maxAmount: 0 )
    cache  = Cache( First(line, amount: 10), matchAbilityEntities: true )    // 2
    vector = VectorFromAdjacentTo( Get(GetMainTile(caster)), Get(target), length: 1 )   // 3
    for (index = 0; index < 10; index++) {                                   // 4
        tile = SelectTile( AtIndex(cache, index) );  if (tile == null) return;   // <<< SANS retrait
        if (!ExecuteBehaviourStep(abilityState, entities, vector, tile, index)) break;
    }
    Execute( RemoveFlag(Caster@0x48, 0x19 = UnitFlag.Undisplaceable) )       // 5

⚠ L'ENCADREMENT (1)...(5) N'EST PAS HERMETIQUE, ET LE PORT LE MIRRORE DEPUIS #498-r4-r1. Le
`return` du (4) est ENTRE l'`AddFlag` et le `RemoveFlag`, et il ne retire rien : quand la ligne
comptee par le `First(..., 10)` est plus COURTE que 10 et que la charge la traverse INTEGRALEMENT
(tous les pas rendent `true`), le natif indexe une position vide, sort, et laisse
`UnitFlag.Undisplaceable` POSE SUR LE CASTER POUR LE RESTE DE LA BATAILLE. Aucun autre ecrivain de
`0x19` n'existe (recensement EXHAUSTIF de #498-r4) et `UnitFlagsComponent$$RemoveTurnFlags` ne le
retire pas -> rien ne vient le lever. Le port portait un `try/finally` qui retirait TOUJOURS :
degradation PERMISSIVE (il rendait deplacable un caster que le natif verrouille), MESUREE, fermee.
Le regime est celui d'une cible adossee au BORD DU PLATEAU (ou derriere laquelle la ligne bute sur
une tuile non marchable des le premier prolongement).

`...UnstoppableMomentumReworkedAbility$$ExecuteBehaviourStep(state, entities, startVector, tile, steps)` :

    if (UnitExtensions.IsDead(caster))                     return false;
    if (!TileExtensions.IsWalkable(tile, true))            return false;
    if (!TileExtensions.IsNeighbourOf(tile, GetMainTile(caster)))  return false;
  MOVE:
    if (TileExtensions.IsEmptyOrSteppable(tile, caster))   return Move(caster, tile);
    Execute( RemoveEffect( Units(Get(tile), unique: 1, sel: 0),
                           Nullable(0x425 = GeminaeSuperia_JustSummonedEffect) ) );
    enemies = Enemies( Caster@0x48, Units(Get(tile), unique: 0, sel: 3), 3 );
    Attack(enemies, abilityState, entities, steps);
    SuppressOrStun(enemies, abilityState, entities);
    if (Push(tile, entities, startVector))                 return true;      // SwitchPosition
    if (UnitExtensions.IsDead(caster))                     return false;
    if (!UnitExtensions.CanMove(caster))                   return false;
    if (!TileExtensions.IsEmptyOrSteppable(tile, caster))  return false;
    goto MOVE;                                                               // -> Move(caster, tile)

`...UnstoppableMomentumReworkedAbility$$Move(caster, tile)` :

    if (!TileExtensions.IsFreeTile(tile, caster, allowSteppable: 1, allowTemporary: 0,
                                   allowAnyUnit: 0))       return false;
    Execute( InvalidateCaches() & MoveUnit(Get(caster), Get(tile), <options ZERO>) );
    return true;

`...UnstoppableMomentumReworkedAbility$$Attack(target, abilityState, entities, traversedSteps)` :

    dmg   = Sum( MinMaxDamage(abilityState),
                 Direct( GetVariableForLevel(8 = extraDmg) * traversedSteps ) )
    Execute( AttackWithAttackDamage( Caster@0x48, target, dmg, GetDamageProfile(),
                                     GetNumberConstant(0x2f = nrOfHits), abilityState,
                                     <options ZERO>, selectionType: 2 ) )

  ⚠ `traversedSteps` = l'INDEX de la boucle, 0-BASED : au 1er pas (l'ennemi est ADJACENT au caster)
  le bonus vaut `extraDmg * 0 = 0`. C'est exactement l'i2 (« for each hex traversed FROM THE
  STARTING HEX to the enemy »). Famille ATTACK (`DSLBehaviors$$AttackWithAttackDamage`, PAS
  `AttackWithAbilityDamage`) -> crit/block/extra-hits actifs, `native_factory="attack"`.

`...UnstoppableMomentumReworkedAbility$$SuppressOrStun(target, abilityState, entities)` :

    suppressRounds = GetNumberConstant(0x69 = effectTurns)     // 1
    stunRounds     = GetNumberConstant(0x6a = effectTurns_2)   // 1
    Execute( If( NOT CanBeDisplaced(target),
                 AddEffect(0x48a = Stunned, src = AbilityStateReference, Owner@0x30, target,
                           TurnsFromRounds(suppressRounds)),
                 AddEffect(0x429 = Pinned,  src = AbilityStateReference, Owner@0x30, target,
                           TurnsFromRounds(stunRounds)) ) )

  ⚠ Les DEUX branches sont CROISEES par rapport aux noms de constantes : la branche BIG TARGET
  (`!CanBeDisplaced`) lit `effectTurns` et pose `Stunned` ; la branche ordinaire lit `effectTurns_2`
  et pose `Pinned` (« Suppressed » cote UI). Transcrit VERBATIM -- inerte tant que les deux valent 1,
  mais ecrire l'inverse serait un fork de port silencieux le jour ou elles divergent.

`...UnstoppableMomentumReworkedAbility$$Push(tile, entities, startVector)` :

    if (TileExtensions.IsEmptyOrSteppable(tile, caster))         return false;
    unit = UnitExtensions.GetUnit(tile, caster);
    if (!UnitExtensions.IsDisplaceable(unit))                    return false;   // BigTarget/Immovable
    adj  = Cache( CanAddUnit( AdjacentTiles(Get(tile)) ), true )
    P(d) = TilesInPath( PathDefinition(Get(tile), startVector, [d], includeStartTile: false) )
    prio = ( Randomize(P(ForwardRight) + P(ForwardLeft))
           + Randomize(P(BackwardRight) + P(BackwardLeft))
           + P(Forward) ) & adj
    dest = SelectTile( First(prio, amount: 1) );
    if (dest == null) {
        if (TileExtensions.IsTemporary(GetMainTile(unit)))       return false;
        Execute( SwitchPosition(Caster@0x48, Get(unit)) );       return true;
    }
    Execute( PushToPrioritizedTiles(Caster@0x48, Get(unit), Get(dest), knockbackDamage: true) );
    return false;

  `IdunBattleLogic.Utils.Hex.RelativeDirection` = `0=Forward, 1=ForwardRight, 2=BackwardRight,
  3=Backward, 4=BackwardLeft, 5=ForwardLeft` (enum LU dans `data/symbols/<build>/frida/enums.tsv`).
  Priorite : les deux diagonales AVANT (ordre tire au sort), puis les deux diagonales ARRIERE (idem),
  puis TOUT DROIT. `Backward` (vers le caster) n'est JAMAIS candidat.

  ⚠ Le SENS de rotation (quel cote est « Right ») est INOBSERVABLE ici et ce n'est pas une
  approximation : les deux premiers rangs sont des PAIRES SYMETRIQUES (`{+1, +5}` et `{+2, +4}`
  autour de `Forward`), donc echanger droite et gauche permute deux elements d'un ensemble
  immediatement melange par `Randomize`. Le 3e rang (`Forward`) est invariant. Aucun besoin de
  trancher la convention native.

  `IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPushToPrioritizedTiles(target, tiles)` :
  liste a UN element -> rendue TELLE QUELLE (aucun re-test) ; liste a N > 1 -> filtree par
  `IsEmptyOrSteppable` puis premier element ; liste vide -> null. Ici `prioritizedTiles` est un
  `Get(dest)` d'UNE tuile, deja passee par `CanAddUnit` -> premiere branche.

`...UnstoppableMomentumReworkedAbility$$RemoveJustSummonedEffect(tile, entities)` : corps INLINE dans
`ExecuteBehaviourStep` (meme arbre, meme effet `0x425`), non appele separement dans le flux porte --
mirror rendu par `_remove_just_summoned` ci-dessous.

`...UnstoppableMomentumReworkedAbility$$CanContinue(nextTile)` et `$$GetAllTilesInLine()` sont deux
helpers de la face DECISION/vue (`CanBeDisplaced(Units(nextTile)) | IsCanAddUnit(nextTile)` pour le
premier, la ligne seule pour le second) : AUCUN des deux n'est appele par `ExecuteBehaviour`. Ils ne
sont donc pas portes ici -- RESIDU NOMME (face DECISION, hors perimetre #498).

DEGRADATIONS NOMMEES (aucune n'invente de comportement) :
  * `AddFlag`/`RemoveFlag(UnitFlag.Undisplaceable)` sur le caster : le port POSE et RETIRE le flag
    via `UnitFlagsComponent` (mirror direct, pas de feuille DSL `AddFlag` portee). Son effet natif
    est de rendre le caster non-deplacable pendant sa propre charge -- ET AU-DELA quand la sortie
    prend le `return` du (4), cf. l'avertissement ci-dessus. Le flag EST lu par le port :
    `runner/components.py::unit_extensions_is_displaceable` teste `HasFlag(unit, 0x19)`, et ses six
    lecteurs portes comprennent la tete de `DisplaceUnitOperation$$Execute` (donc TOUT push, pull,
    deplacement direct ou echange de position visant le caster) et `DamagePrediction$$GetKnockback`.
    Le retour porte `flag_leaked` : `True` = le flag est encore pose a la sortie du cast.
  * Une EXCEPTION levee par un pas laisse elle aussi le flag pose (il n'y a plus de `finally`).
    C'est le comportement natif : le `throw` du decompile ne retire rien non plus.
  * `InvalidateCaches()` (compose au `MoveUnit` de `Move`) : vide les caches de selecteurs natifs.
    Le port re-construit son `AbilityEntities` a chaque pas (`entities_from_state`), ce qui EST
    l'invalidation ; aucun cache DSL ne survit entre deux pas.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ..base import ActiveAbility
from ..targeting import (RANGE_ADJACENT, RANGED_BOOL_FALSE, TargetingOptions, has_steppable_unit,
                         unit_of_entity)
from ..targeting_rule import TargetingRule as TR
from ..behaviours.combat import AttackWithAttackDamage
from ..behaviours.context import entities_from_state
from ..behaviours.effects import AddEffect, RemoveEffect
from ..behaviours.movement import MoveUnit, PushToPrioritizedTiles, SwitchPosition
from ...components import PositionComponent, StatsComponent, UnitComponent, UnitFlagsComponent
from ...components import unit_extensions_is_displaceable   # #498-r2 : foyer d'`IsDisplaceable`
from ....dsl.effects import ExecutionContext
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.ability_constant_type import AbilityConstantType
from ....entities.ability_variable_type import AbilityVariableType
from ....entities.effect_type import EffectType
from ....entities.effects.magnitude import ability_var
from ....entities.selectors.accessors import CasterTile, FixedTileIds, SelectTile
from ....entities.selectors.geometry import Randomize, TilesBehindInLine
from ....entities.selectors.tiles import Caster
from ....entities.selectors.units import Enemies, Units, UnitSet
from ....entities.traits.unit_trait import UnitTrait, has_any_trait
from ....entities.unit_flag import UnitFlag
# #943-r7 -- le canal du `ConnectivityComponent` BRUT (SANS porte d'elevation), en FORME B
# (#485-r1-r1). `entities.pathfinding.board` n'importe RIEN d'`engine`.
from ....entities.pathfinding import board as _board

if TYPE_CHECKING:
    from ...state import State

MOMENTUM_ID = "UnstoppableMomentumReworked"

# `*(undefined4 *)((longlong)this + 0xf0) = 10` du `.ctor` -- lu par `First(line, amount: 10)` ET par
# la borne de boucle `index < this+0xf0` d'`ExecuteBehaviour`.
MAX_CHARGE_TILES = 10

# `Nullable(0x425)` du `RemoveEffect` d'`ExecuteBehaviourStep`.
JUST_SUMMONED = int(EffectType.GeminaeSuperia_JustSummonedEffect)   # 0x425 = 1061
STUNNED = int(EffectType.Stunned)                                   # 0x48a = 1162
PINNED = int(EffectType.Pinned)                                     # 0x429 = 1065

# `GetNumberConstant(<index>)` -> cle gameconfig. Transcription des trois index LUS au decompile.
CONST_NR_OF_HITS = AbilityConstantType.nrOfHits            # 0x2f -> "nrOfHits"
CONST_STUN_ROUNDS = AbilityConstantType.effectTurns        # 0x69 -> "effectTurns"   (branche BigTarget)
CONST_PIN_ROUNDS = AbilityConstantType.effectTurns_2       # 0x6a -> "effectTurns_2" (branche ordinaire)
VAR_EXTRA_DMG = AbilityVariableType.extraDmg               # 8    -> "extraDmg" (per-hex)

# `UnitFlag.Undisplaceable` = `0x19` -- le litteral des `AddFlag`/`RemoveFlag` qui encadrent la charge.
CHARGE_FLAG = int(UnitFlag.Undisplaceable)

# Les SIX directions cube, dans un ordre CYCLIQUE (rotation de 60 degres = +1 modulo 6). Ce n'est PAS
# la table `EVENQ_*` de `entities/pathfinding/board.py`, qui est lexicographique (son index n'est donc
# pas une rotation). Base de `_relative_neighbour` ci-dessous ; cf. la note « le SENS de rotation est
# INOBSERVABLE » de l'en-tete de module.
_CUBE_DIRS = ((1, -1, 0), (1, 0, -1), (0, 1, -1), (-1, 1, 0), (-1, 0, 1), (0, -1, 1))


class RelativeDirection:
    """`IdunBattleLogic.Utils.Hex.RelativeDirection` (enum VERBATIM du dump il2cpp) -- les valeurs
    passees comme `nodes` aux cinq `PathDefinition` de `...UnstoppableMomentumReworkedAbility$$Push`."""
    Forward = 0
    ForwardRight = 1
    BackwardRight = 2
    Backward = 3
    BackwardLeft = 4
    ForwardLeft = 5


def _cube(col: int, row: int) -> tuple[int, int, int]:
    import hexgeo
    return hexgeo.to_cube(col, row)


def _from_cube(x: int, z: int) -> tuple[int, int]:
    import hexgeo
    return hexgeo.from_cube(x, z)


def _charge_vector(frm: tuple[int, int], to: tuple[int, int]) -> Optional[tuple[int, int, int]]:
    """`DSLFormulas$$VectorFromAdjacentTo(from, to, length: 1)` -> `FromToVectorFormula` : le vecteur
    UNITAIRE `from -> to`. Le ciblage est ADJACENT (`TargetingRange statics+0x30`), donc `to` est un
    VOISIN de `from` et le delta cube EST deja unitaire. Rend None si les deux tuiles ne sont pas
    voisines (cast impossible cote natif : le gate `IsNeighbourOf` du 1er pas romprait de toute
    facon)."""
    ax, _, az = _cube(frm[0], frm[1])
    bx, _, bz = _cube(to[0], to[1])
    d = (bx - ax, (-(bx - ax) - (bz - az)), bz - az)
    return d if d in _CUBE_DIRS else None


def _relative_neighbour(board, tile: tuple[int, int], vector: tuple[int, int, int],
                        relative: int) -> Optional[int]:
    """UN pas de `TilesInPath(PathDefinition(Get(tile), vector, [relative], includeStartTile: false))` :
    la voisine de `tile` dans la direction `vector` TOURNEE de `relative` crans. `nodes` ne contient
    qu'UN element a chacun des cinq call-sites -> le path fait exactement un pas, et
    `includeStartTile = false` exclut `tile`. Rend l'id de tuile, ou None hors plateau."""
    i = _CUBE_DIRS.index(vector)
    dx, _, dz = _CUBE_DIRS[(i + int(relative)) % 6]
    cx, _, cz = _cube(tile[0], tile[1])
    col, row = _from_cube(cx + dx, cz + dz)
    return board.id_at(col, row)


def _main_tile(state: "State", unit_id: int) -> Optional[tuple[int, int]]:
    """`EntityExtensions$$GetMainTile(entities, unit)` -- la position (col,row) de l'unite."""
    e = state.get_entity(int(unit_id))
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _is_dead(state: "State", unit_id: int) -> bool:
    """`UnitExtensions$$IsDead(entities, unit)`."""
    e = state.get_entity(int(unit_id))
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc is not None and not uc.alive


def _occupant_of(state: "State", board, tile_id: int) -> Optional[int]:
    """`UnitExtensions$$GetUnit(tile, state)` = l'occupant VIVANT de la tuile (`unit_of_entity` est le
    foyer porte de ce mirror ; il resout une TUILE en son occupant)."""
    return unit_of_entity(state, tile_id)


def _is_empty_or_steppable(state: "State", board, tile_id: int) -> bool:
    """`TileExtensions$$IsEmptyOrSteppable(tile, caster)` = la tuile est VIDE, ou son occupant porte
    le trait `Steppable` (`has_steppable_unit`, foyer porte du meme mirror)."""
    occ = _occupant_of(state, board, tile_id)
    if occ is None:
        return True
    return has_steppable_unit(state, tile_id)


def _is_displaceable(state: "State", unit_id: int) -> bool:
    """`UnitExtensions$$IsDisplaceable(unit)` -- MEME substrat que la tete d'`IdunBattle.Operations.
    DisplaceUnitOperation$$Execute` (`operations/displace.py`), et depuis #498-r2 le MEME FOYER :
    `runner/components.py::unit_extensions_is_displaceable`. Ce module en portait une COPIE qui ne
    testait que `Immovable` et `BigTarget` -- il manquait `Hulking` (0x3) et le flag
    `UnitFlag.Undisplaceable` (0x19), les deux dans le sens PERMISSIF.

    Le gate `alive` ci-dessous n'est PAS dans le natif (relu : `IsDisplaceable` ne teste aucune
    liveness). Il est CONSERVE parce qu'il est deja ventile `INERTE-VIVANT` par #462, et NOMME
    ici : direction RESTRICTIVE (le port refuse de deplacer un cadavre que le natif accepterait)."""
    e = state.get_entity(int(unit_id))
    if e is None:
        return False
    uc = e.get_component(UnitComponent)
    if uc is not None and not uc.alive:
        return False
    return unit_extensions_is_displaceable(e)


def _can_move(state: "State", unit_id: int) -> bool:
    """`UnitExtensions$$CanMove(unit)` : le port n'a pas d'etat « immobilise » distinct du trait
    `Immovable` ni du flag `Moved` (le natif teste un flag de MOUVEMENT REMANENT que le runner ne
    capte pas). REDUCTION NOMMEE : on rend `not Immovable`. Elle est PERMISSIVE au meme titre que le
    reste du port -- le gate suivant (`IsEmptyOrSteppable` puis `IsFreeTile` dans `Move`) reste le
    vrai verrou du deplacement."""
    e = state.get_entity(int(unit_id))
    if e is None:
        return False
    sc = e.get_component(StatsComponent)
    traits = getattr(sc.ctx, "traits", None) if sc is not None else None
    return not has_any_trait(traits, (UnitTrait.Immovable,))


def _set_charge_flag(state: "State", caster_id: int, on: bool) -> None:
    """`Execute(AddFlag(Caster@0x48, 0x19))` / `Execute(RemoveFlag(Caster@0x48, 0x19))` -- les deux
    arbres qui ENCADRENT la boucle native.

    ⚠ L'appel `on=False` n'est PAS symetrique de `on=True` : il n'est atteint que par la sortie
    NORMALE de la boucle. Le `return` du (4) le saute -- cf. l'avertissement de l'en-tete de module
    (#498-r4-r1). cf. aussi « DEGRADATIONS NOMMEES ».

    ⚠ LE COMPOSANT EST CREE S'IL MANQUE, ET C'EST UN CORRECTIF, PAS UNE COMMODITE (#498-r4-r1).
    `IdunBattle.Entities.Behaviours.AddFlagBehaviour$$Execute` (comme son jumeau `RemoveFlag`)
    accede au `UnitFlagsComponent` de chaque unite selectionnee et **LEVE** s'il est absent -- il ne
    l'ignore pas. Natif, le cas ne se produit jamais : `UnitFlagsComponent$$.ctor` construit un
    `OrderedSet` VIDE et `UnitFactory` le monte sur TOUTE unite. Cote port, en revanche,
    `snapshot._load_unit_flags` ne materialise le composant que si la ligne du snapshot porte une
    liste NON VIDE -- donc une unite sans AUCUN flag n'en a pas, et le `if fc is None: return`
    d'avant faisait de la pose un NO-OP SILENCIEUX. MESURE (`probe_498r4r1_fuite_flag_undisplaceable
    _live.py`, bras `fuite`) : le natif rend `unitFlags = [1, 2, 3, 4, 25]` apres le cast, le port
    ne posait RIEN -- l'ecart de fuite etait donc INOBSERVABLE cote port, masque par un ecart de
    substrat en amont. Meme geste que `turnflow.FinishUnitTurnOperation.execute`, qui cree deja le
    composant absent pour la meme raison. Le FOYER (`_load_unit_flags` devrait materialiser un
    composant VIDE sur toute ligne MESUREE) reste ouvert : residu `#545`."""
    e = state.get_entity(int(caster_id))
    if e is None:
        return
    fc = e.get_component(UnitFlagsComponent)
    if fc is None:
        fc = e.add_component(UnitFlagsComponent())
    if on:
        fc.add(CHARGE_FLAG)
    else:
        fc.remove(CHARGE_FLAG)


def momentum_charge_line(state: "State", caster_id: int, aim_tile_id: int) -> list:
    """`Cache( First( TilesBehindInLine(CasterTile@0x50, Target@0x60, settings{+0x10=1, +0x11=1}, 0),
    amount: 10 ), true )` -- la LIGNE de charge, EVALUEE UNE FOIS.

    * `settings` : le ctor natif ecrit `*(short*)(obj + 0x10) = 0x101`, soit (little-endian)
      `+0x10 = 1` (`checkWalkable`) et `+0x11 = 1` (`updateReference`) -- MEME couple que
      `DarkTalonStrikeAbility$$GetTilesInLine`. `checkWalkable = 1` arme AUSSI le gate d'ELEVATION
      (il vit dans la branche walkable d'`IdunBattle.Core.Services.TileUtil$$IsTileValidForList`) et
      la ligne S'ARRETE au 1er echec -- c'est exactement le « until he hits an obstacle » de l'i2.
    * `TilesBehindInLine(from, to)` rend `to` EN PREMIER puis prolonge : la 1re tuile de la charge
      EST la tuile visee (adjacente au caster).
    * `First(line, amount: 10)` = les DIX premieres. Le `First` du port (`selectors/units.py`) est un
      `AtIndex` (UN element) : la troncature est donc COLLAPSEE ici (`[:MAX_CHARGE_TILES]`).
    * Le `Cache` est LOAD-BEARING : le caster BOUGE pendant la charge, donc re-evaluer
      `CasterTile@0x50` a chaque pas donnerait une ligne differente a chaque iteration."""
    board = state.board
    if board is None:
        return []
    entities = entities_from_state(state, caster_id)
    line = TilesBehindInLine(SelectTile(CasterTile()), FixedTileIds([int(aim_tile_id)]),
                             max_count=None, check_walkable=True, update_reference=True)
    return list(line.evaluate(entities))[:MAX_CHARGE_TILES]


class UnstoppableMomentumReworkedAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.UnstoppableMomentumReworkedAbility` (id 1152,
    `orksNob` « Tanksmasha », HERO Orks -- 4 autres porteurs npc) -- cf. la docstring de module.

    `target_id` = un id de TUILE (cast TILE-TARGET, `TargetIsTile`). On accepte aussi un id d'UNITE
    (on prend alors sa MainTile), meme convention que `RadBombardmentAbility`/`PlagueburstMortar`.

    Turn-flags = defauts base (1152 absent des overrides `NO_END_TURN`/`NO_ABILITY_USED_FLAG`).
    Retour : {ability, caster, aim, line, steps, attacks, effects, moves, pushes, switches,
    flag_leaked, dsl} -- `flag_leaked` (#498-r4-r1) = le cast est sorti par le `return` du (4) et
    `UnitFlag.Undisplaceable` est RESTE pose sur le caster."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.UnstoppableMomentumReworked)   # 1152
    ABILITY_ID = MOMENTUM_ID

    # GATE DE CIBLE (#115 / #498). `...UnstoppableMomentumReworkedAbility$$.ctor` appelle la surcharge
    # a 7 arguments « FLAGS DIRECTS » de `IdunBattle.Core.Services.TargetingOptions$$.ctor` :
    #     TargetingOptions..ctor(&opts, 0, &<TargetingRange statics+0x30>, 1, 0x10120040, 0, 0)
    # Le 3e argument est un PRESET DE PORTEE (`TargetingRange`), pas un preset d'options -> le
    # litteral `0x10120040` EST le masque effectif (aucun `| preset.rules`). Decomposition :
    #     0x40         TargetIsTile             -> cast TILE-TARGET (domaine tuile, regle non portee
    #                  par le filtre statique -> inerte, et c'est delibere).
    #     0x20000      TargetTileIsFreeOrEnemy  -> la tuile visee doit etre LIBRE ou porter un ennemi.
    #     0x100000     AllowSteppableUnit       -> permission (un occupant Steppable ne bloque pas).
    #     0x10000000   CasterCanMove            -> refus si le caster ne peut plus bouger.
    # `selfCast = 0` ; `forceMeleeTarget = 1` = `RangedBool.False` (l'enum natif est INVERSE, cf. le
    # bloc `ItItches` de `targeting.py`). Portee = `TargetingRange statics+0x30` = ADJACENT, ce qui
    # est ce qui donne les « 6 directions » de l'i2.
    # Cette entree a MIGRE depuis `TARGETING_OPTIONS_UNPORTED` (contrat de disjonction) : elle y
    # vivait a l'identique, RE-LUE au decompile avant migration.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetIsTile
        | TR.TargetTileIsFreeOrEnemy
        | TR.AllowSteppableUnit
        | TR.CasterCanMove
    ), self_cast=False, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    # ------------------------------------------------------------------------------------------- #
    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        board = state.board
        if board is None or target_id is None:
            return None
        aim = int(target_id) if int(target_id) in board.by_id else None
        if aim is None:
            pos = _main_tile(state, target_id)
            aim = board.id_at(pos[0], pos[1]) if pos is not None else None
        if aim is None:
            return None
        caster_pos = _main_tile(state, caster_id)
        aim_pos = board.coord(aim)
        if caster_pos is None or aim_pos is None:
            return None
        # (3) `VectorFromAdjacentTo(Get(GetMainTile(caster)), Get(target), 1)` -- FIGE avant la boucle
        # (le natif le calcule UNE fois, hors boucle, donc sur la position de DEPART du caster).
        vector = _charge_vector(caster_pos, (int(aim_pos[0]), int(aim_pos[1])))
        if vector is None:
            return None
        # (2) la ligne, mise en cache AVANT le 1er pas.
        tiles = momentum_charge_line(state, caster_id, aim)
        out = {"ability": MOMENTUM_ID, "caster": caster_id, "aim": aim, "line": list(tiles),
               "steps": 0, "attacks": [], "effects": [], "moves": [], "pushes": [], "switches": [],
               "flag_leaked": False, "dsl": True}
        _set_charge_flag(state, caster_id, True)                       # (1) AddFlag(Undisplaceable)
        # (4) LA BOUCLE NATIVE, MIRROR : `for (index = 0; index < this+0xf0; index++)`, dont le
        # premier geste est `tile = SelectTile(AtIndex(cache, index))`. Elle N'ITERE PAS sur le
        # cache : elle l'INDEXE, et l'index sort du cache des que la ligne est plus COURTE que
        # `MAX_CHARGE_TILES`. Le decompile fait alors `return 0` -- AVANT le `RemoveFlag`.
        for index in range(MAX_CHARGE_TILES):
            if index >= len(tiles):
                # `if (tile == null) return;` -- LA FUITE (#498-r4-r1) : le natif SORT SANS retirer
                # `UnitFlag.Undisplaceable`, donc le caster reste indeplacable POUR LE RESTE DE LA
                # BATAILLE. Aucun autre ecrivain de `0x19` n'existe (recensement EXHAUSTIF de
                # #498-r4 : 10 appelants de `DSLBehaviors$$AddFlag`, 40 sites d'
                # `UnitFlagsComponent$$Add`, `RemoveTurnFlags` qui ne retire que 0,1,2,3,4,0xc,0x1b)
                # -> rien ne vient le lever ensuite. Le port RETIRAIT TOUJOURS (`try/finally`),
                # ce qui etait PERMISSIF : il rendait deplacable un caster que le natif verrouille.
                out["flag_leaked"] = True
                return out
            out["steps"] = index + 1
            if not self._execute_behaviour_step(state, caster_id, vector, int(tiles[index]),
                                                index, out):
                break
        # Sortie NORMALE de boucle (un pas a rendu `false`, ou les 10 tuiles ont ete consommees) :
        # c'est le SEUL chemin qui atteint le `RemoveFlag` natif.
        _set_charge_flag(state, caster_id, False)                      # (5) RemoveFlag
        return out

    # ------------------------------------------------------------------------------------------- #
    def _execute_behaviour_step(self, state: "State", caster_id: int,
                                vector: tuple[int, int, int], tile_id: int, steps: int,
                                out: dict) -> bool:
        """`...UnstoppableMomentumReworkedAbility$$ExecuteBehaviourStep` -- MIRROR ligne a ligne (cf.
        l'en-tete de module). Rend `true` = la charge CONTINUE au pas suivant."""
        board = state.board
        if _is_dead(state, caster_id):
            return False
        if not board.walkable(tile_id):                       # TileExtensions.IsWalkable(tile, true)
            return False
        caster_pos = _main_tile(state, caster_id)
        tile_pos = board.coord(tile_id)
        if caster_pos is None or tile_pos is None:
            return False
        # `TileExtensions$$IsNeighbourOf(targetTile, GetMainTile(caster))` -- LU (#943-r7), et ce
        # N'EST PAS le meme substrat que le reste de la famille : le corps enumere
        # `ConnectivityComponent+0x10` de la tuile CIBLE et compare l'id de la tuile du caster,
        # **SANS AUCUNE PORTE D'ELEVATION** (contraste avec `IterateAdjacentTiles`, qui en porte
        # une). Ni `battle_query.is_adjacent` ni `Board.neighbours_native` ne conviennent donc :
        # tous deux ajouteraient la porte, et le champ `neighbours` capte EST deja
        # `connectivity INTERSECTE {|dElev| < 2}` (identite lue dans `Board.base_add_neighbours`).
        # Le canal juste est `Board.neighbours_connectivity`, TRI-ETAT.
        #
        # ⚠ TRI-ETAT, ET LE `None` N'EST PAS RARE : le champ `connectivity` du `boardGraph` n'existe
        # QU'EN LIVE (`InitializeConnectivityOperation$$Execute` le construit en bataille), les
        # `data/boards/*.json` etant des ASSETS qui ne peuvent structurellement pas le porter.
        # Canal absent -> repli GEOMETRIQUE nomme, c.-a-d. le comportement d'avant ce cablage.
        # L'inclusion mesuree est `neighbours SOUS-ENSEMBLE connectivity SOUS-ENSEMBLE geometrie`,
        # donc le cablage est strictement RESTRICTIF -- il ferme des pas que la couronne ouvrait.
        conn = _board.connectivity_neighbours(board, tile_id)
        if conn is None:
            import hexgeo
            if hexgeo.distance(caster_pos, (int(tile_pos[0]), int(tile_pos[1]))) != 1:
                return False                                  # repli : canal non capte
        else:
            caster_tid = board.id_at(int(caster_pos[0]), int(caster_pos[1]))
            if caster_tid is None or int(caster_tid) not in {int(x) for x in conn}:
                return False                                  # TileExtensions.IsNeighbourOf
        if _is_empty_or_steppable(state, board, tile_id):
            return self._move(state, caster_id, tile_id, out)
        # --- tuile OCCUPEE : retrait de l'effet 0x425, attaque, effet, poussee -------------------
        self._remove_just_summoned(state, caster_id, tile_id, out)
        self._attack(state, caster_id, tile_id, steps, out)
        self._suppress_or_stun(state, caster_id, tile_id, out)
        if self._push(state, caster_id, tile_id, vector, out):
            return True                                       # SwitchPosition -> on continue
        if _is_dead(state, caster_id):
            return False
        if not _can_move(state, caster_id):
            return False
        if not _is_empty_or_steppable(state, board, tile_id):
            return False
        return self._move(state, caster_id, tile_id, out)     # `goto MOVE` du decompile

    # ------------------------------------------------------------------------------------------- #
    def _ectx(self, state: "State"):
        return ExecutionContext(state=state, rng=state.rng)

    def _remove_just_summoned(self, state: "State", caster_id: int, tile_id: int,
                              out: dict) -> None:
        """`Execute( RemoveEffect( Units(Get(tile), unique: 1, sel: 0), Nullable(0x425) ) )` -- le
        corps de `...UnstoppableMomentumReworkedAbility$$RemoveJustSummonedEffect`, inline dans
        `ExecuteBehaviourStep`."""
        entities = entities_from_state(state, caster_id)
        ectx = self._ectx(state)
        RemoveEffect(JUST_SUMMONED, Units(FixedTileIds([int(tile_id)]))).execute(entities, ectx)
        for name, p in ectx.emitted:
            if name == "RemoveEffect" and p.get("removed"):
                out["effects"].append({"kind": "RemoveEffect", "effect": JUST_SUMMONED,
                                       "target": p.get("target"), "removed": p.get("removed")})

    def _enemies_on(self, tile_id: int):
        """`Enemies( Caster@0x48, Units(Get(tile), unique: 0, sel: 3), 3 )` -- SEULS les ENNEMIS sur la
        tuile prennent le degat et les effets ; un ALLIE est seulement DEPLACE (i2 : « Friendly units
        are also displaced, but take no damage or negative effects »)."""
        return Enemies(Units(FixedTileIds([int(tile_id)])))

    def _attack(self, state: "State", caster_id: int, tile_id: int, steps: int,
                out: dict) -> None:
        """`...UnstoppableMomentumReworkedAbility$$Attack` -- cf. l'en-tete de module.

        `Sum(MinMaxDamage, Direct(extraDmg * traversedSteps))` : le terme flat s'ajoute aux DEUX
        bornes (`SumAmount$$CalculateMin`/`$$CalculateMax` sont compositionnels), MEME forme que
        `FoehammerAbility` (`spacewolves.py`). `traversedSteps` est 0-BASED."""
        ce = state.get_entity(caster_id)
        sc = ce.get_component(StatsComponent) if ce is not None else None
        ctx = sc.ctx if sc is not None else None
        level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
        per_hex = int(ability_var(MOMENTUM_ID, AbilityVariableType.extraDmg.name, level,
                                  multiplier_pct=mult) or 0)
        flat = per_hex * int(steps)
        profile = ((GC.ability(MOMENTUM_ID) or {}).get("constants") or {}).get(
            "damageProfile") or "DirectDamage"

        def damage_override(_st, _caster, _target, bmin, bmax):
            return bmin + flat, bmax + flat

        entities = entities_from_state(state, caster_id)
        ectx = self._ectx(state)
        AttackWithAttackDamage(self._enemies_on(tile_id), MOMENTUM_ID, profile, is_melee=True,
                               damage_override=damage_override, multi=True,
                               ability_type=self.ABILITY_TYPE).execute(entities, ectx)
        for name, p in ectx.emitted:
            if name == "AttackWithAttackDamage":
                out["attacks"].append({"target": p.get("target"), "total": p.get("total"),
                                       "attack": p.get("attack"), "steps": int(steps),
                                       "extra_dmg": flat})

    def _suppress_or_stun(self, state: "State", caster_id: int, tile_id: int,
                          out: dict) -> None:
        """`...UnstoppableMomentumReworkedAbility$$SuppressOrStun` -- le `If(NOT CanBeDisplaced(...))`
        est COLLAPSE par cible (doctrine slice-18/19/24 : les predicats T se replient, seule
        l'ossature E reste feuille DSL). `DSLTriggers$$CanBeDisplaced` == `UnitExtensions$$
        IsDisplaceable` (meme substrat que le gate de `_push`) -> BigTarget/Immovable ⇒ `Stunned`,
        sinon `Pinned`. Les DEUX index de constante sont transcrits VERBATIM (cf. l'avertissement
        « branches CROISEES » de l'en-tete)."""
        const = (GC.ability(MOMENTUM_ID) or {}).get("constants") or {}
        stun_rounds = int(const.get(AbilityConstantType.effectTurns.name) or 1)      # 0x69
        pin_rounds = int(const.get(AbilityConstantType.effectTurns_2.name) or 1)     # 0x6a
        entities = entities_from_state(state, caster_id)
        targets = [u for u in self._enemies_on(tile_id).evaluate(entities)
                   if isinstance(u, dict) and u.get("id") is not None]
        for u in sorted(targets, key=lambda x: x["id"]):
            big = not _is_displaceable(state, int(u["id"]))
            eff, name, rounds = ((STUNNED, EffectType.Stunned.name, stun_rounds) if big
                                 else (PINNED, EffectType.Pinned.name, pin_rounds))
            ectx = self._ectx(state)
            AddEffect(eff, name, UnitSet([u]), duration_rounds=rounds).execute(entities, ectx)
            for ename, p in ectx.emitted:
                if ename == "AddEffect":
                    out["effects"].append({"kind": "AddEffect", "effect": eff, "name": name,
                                           "target": p.get("target"), "placed": p.get("placed"),
                                           "rounds": rounds})

    # ------------------------------------------------------------------------------------------- #
    def _move(self, state: "State", caster_id: int, tile_id: int, out: dict) -> bool:
        """`...UnstoppableMomentumReworkedAbility$$Move(caster, tile)` : gate `IsFreeTile(tile, caster,
        allowSteppable: 1, allowTemporary: 0, allowAnyUnit: 0)` puis
        `Execute(InvalidateCaches() & MoveUnit(Get(caster), Get(tile), <options ZERO>))`.

        Le gate est le MEME predicat que `_is_empty_or_steppable` (branche `allowAnyUnit == 0` d'
        `IdunBattle.Entities.TileExtensions$$IsFreeTile` : `content.IsEmpty() || GetUnit(t).HasTrait(
        Steppable)`), PLUS `walkable`. On le re-teste : le natif le re-teste aussi (les deux appelants
        de `Move` viennent de chemins ou l'etat a pu changer -- un push vient de liberer la tuile)."""
        board = state.board
        if not board.walkable(tile_id) or not _is_empty_or_steppable(state, board, tile_id):
            return False
        entities = entities_from_state(state, caster_id)
        ectx = self._ectx(state)
        MoveUnit(Caster(), FixedTileIds([int(tile_id)])).execute(entities, ectx)
        moved = False
        for name, p in ectx.emitted:
            if name == "MoveUnit":
                moved = bool(p.get("moved"))
                out["moves"].append({"to": p.get("to"), "moved": moved, "tile": int(tile_id)})
        return moved

    def _push(self, state: "State", caster_id: int, tile_id: int,
              vector: tuple[int, int, int], out: dict) -> bool:
        """`...UnstoppableMomentumReworkedAbility$$Push(tile, entities, startVector)` -- cf. l'en-tete
        de module pour l'arbre natif complet. Rend `true` UNIQUEMENT sur le `SwitchPosition` (aucune
        tuile de poussee disponible) : c'est ce `true` qui fait CONTINUER la charge sans `Move`,
        puisque l'echange a deja mis le caster sur la tuile."""
        board = state.board
        if _is_empty_or_steppable(state, board, tile_id):
            return False
        unit_id = _occupant_of(state, board, tile_id)
        if unit_id is None or not _is_displaceable(state, int(unit_id)):
            return False                                    # BigTarget/Immovable : la charge S'ARRETE
        tile_pos = board.coord(tile_id)
        if tile_pos is None:
            return False
        tile_xy = (int(tile_pos[0]), int(tile_pos[1]))
        entities = entities_from_state(state, caster_id)
        # `adj = Cache( CanAddUnit( AdjacentTiles(Get(tile)) ), true )` -- COLLAPSE : les voisines
        # walkable ET libres (l'occupant POUSSE ne s'auto-bloque pas : il quitte sa tuile).
        occupied = set()
        for eid, e in state.entities.items():
            if int(eid) == int(unit_id):
                continue
            uc = e.get_component(UnitComponent)
            if uc is not None and not uc.alive:
                continue
            pc = e.get_component(PositionComponent)
            if pc is not None:
                occupied.add((pc.col, pc.row))
        import hexgeo
        adj = set()
        for nb in hexgeo.neighbors(tile_xy[0], tile_xy[1]):
            tid = board.id_at(nb[0], nb[1])
            if tid is not None and board.walkable(tid) and (nb[0], nb[1]) not in occupied:
                adj.add(int(tid))
        # Les CINQ `TilesInPath`, dans l'ordre natif, avec les DEUX `Randomize` -- feuille portee
        # `Randomize` (permutation complete, `len(pool)` tirages) pour que la consommation RNG soit
        # celle du natif. `Backward` (3) n'est JAMAIS candidat.
        def path(rel: int):
            tid = _relative_neighbour(board, tile_xy, vector, rel)
            return [] if tid is None else [{"id": int(tid)}]

        front = Randomize(UnitSet(path(RelativeDirection.ForwardRight)
                                  + path(RelativeDirection.ForwardLeft))).evaluate(entities)
        back = Randomize(UnitSet(path(RelativeDirection.BackwardRight)
                                 + path(RelativeDirection.BackwardLeft))).evaluate(entities)
        prioritized = [int(t["id"]) for t in list(front) + list(back) + path(RelativeDirection.Forward)]
        dest = next((t for t in prioritized if t in adj), None)     # `& adj` puis `First(1)`
        ectx = self._ectx(state)
        if dest is None:
            # Aucune tuile de poussee -> ECHANGE de position caster <-> occupant.
            main = _main_tile(state, int(unit_id))
            if main is None or board.id_at(main[0], main[1]) is None:
                return False
            # `TileExtensions$$IsTemporary(GetMainTile(unit))` : le port n'a pas de tuile TEMPORAIRE
            # (aucune capture live ne l'expose) -> gate INERTE, nomme.
            SwitchPosition(Caster(), UnitSet([{"id": int(unit_id)}])).execute(entities, ectx)
            switched = False
            for name, p in ectx.emitted:
                if name == "SwitchPosition":
                    switched = bool(p.get("switched"))
                    out["switches"].append({"unit": int(unit_id), "switched": switched})
            return True                                     # le natif rend `true` INCONDITIONNELLEMENT
        PushToPrioritizedTiles(Caster(), UnitSet([{"id": int(unit_id)}]),
                               FixedTileIds([int(dest)])).execute(entities, ectx)
        for name, p in ectx.emitted:
            if name == "PushToPrioritizedTiles":
                out["pushes"].append({"pushed": int(unit_id), "to": p.get("to"),
                                      "moved": bool(p.get("moved")), "dest_tile": int(dest)})
        return False
