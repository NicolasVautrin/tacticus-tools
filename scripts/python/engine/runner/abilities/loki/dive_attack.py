"""`IdunBattleLogic.Entities.Abilities.Active.Loki.DiveAttackAbilityBase` -- la BASE des abilities
de PLONGEON EN LIGNE, portee 1:1 ici et partagee par ses DEUX heritieres.

Le natif porte TOUTE la mecanique sur la base (5 methodes : `.ctor`, `ExecuteBehaviour`,
`GetTargetTilesSelector`, `GetTargetUnitsSelector`, `GetMovementBehavior`) et ne laisse aux classes
filles qu'un ctor dont le corps ENTIER est `return DiveAttackAbilityBase$$.ctor(this);` :

    IdunBattleLogic.Entities.Abilities.Active.Loki.SwoopingHawkAbility   -> 1064 Loki_SwoopingHawk (#502)
    IdunBattleLogic.Entities.Abilities.Active.Loki.SlashingDiveAbility   -> 1091 SlashingDive      (#507)

⚠ LES DEUX CTORS SONT LE MEME CORPS, et ce n'est pas une deduction : IL2CPP les a FUSIONNES (corps
identiques), donc `SlashingDiveAbility$$.ctor` n'a AUCUN proprietaire nomme dans les tables --
`frida/methods.tsv` et `ghidra/functions.tsv` sont indexees par ADRESSE. C'est exactement le faux
negatif que le `CLAUDE.md` decrit (« l'ABSENCE d'une methode dans les tables ne prouve RIEN »), et
c'est ce qui avait fait classer 1091 en NON-LU. La preuve est RUNTIME, prise par le slot de methode
de la CLASSE (RPC `resolveMethodPtr`, session live du build `rnca9r7q6c`) :

    SlashingDiveAbility..ctor            entry = SwoopingHawkAbility..ctor entry   (MEME adresse)
    SlashingDiveAbility.ExecuteBehaviour           1er hit a depth=1 = DiveAttackAbilityBase
    SlashingDiveAbility.GetTargetTilesSelector     idem            depth=1
    SlashingDiveAbility.GetTargetUnitsSelector     idem            depth=1
    SlashingDiveAbility.GetMovementBehavior        idem            depth=1

Aucune surcharge a depth=0 : la classe fille est VIDE hors ctor. `classes.tsv` le corrobore par une
seconde voie (`...SlashingDiveAbility  240  ...DiveAttackAbilityBase`, meme taille d'instance que
`SwoopingHawkAbility`). CE QUI DIFFERE entre les deux abilities est donc, et seulement, LA CONFIG
lue au gameconfig : `dmg[0..2]`, `damageProfile`, `nrOfHits`, `attackRangeType`.

i2 de 1064 (niveau 17) : « Flies over and deals a wave of damage from an initial melee target to
targets up to 2 hexes behind. 1x {dmg[0]} Piercing Damage to first target, 1x {dmg[1]} to the second,
and 1x {dmg[2]} to the third. Lands in the hex directly behind the last target hit, or - in case that
hex is occupied - to the closest free hex to it. »

`DiveAttackAbilityBase$$ExecuteBehaviour(abilityState, entities)` -- MIRROR du DECOMPILE :

  dmg     = GetVariableArrayForLevel(cfg, 0xb = AbilityVariableType.dmg, abilityState, 0)  # 3 valeurs
  hitsF   = DSLFormulas.Direct( GetNumberConstant(cfg, 0x2f = AbilityConstantType.nrOfHits) )
  profS   = DSLSelectors.Direct( Nullable(AActiveAbility$$GetDamageProfile()) )
  tiles   = GetTargetTilesSelector()
  result  = DSLBehaviors.Nothing()
  aoe     = AbilityOrEffect(this)
  prev    = DSLSelectors.None()
  last    = <DSLSelectors+0x60 = Target>
  for i in 0..2:                                    # boucle bornee par `local_1f0 > 2`
      cur   = Cache( Enemies(Caster@0x48, Units(AtIndex(tiles, i), 0, 0), 0), 1 )
      next_ = Enemies(Caster@0x48, Units(AtIndex(tiles, i+1), 0, 0), 0)
      b = Nothing()
          & If( !AreEqual(cur, prev),  StartAttack(Caster@0x48, cur, aoe) )
          & AbilityDamage(Caster@0x48, cur, Direct(dmg[i]), profS, hitsF, aoe, false, 2)
          & If( !AreEqual(cur, next_), FinishAttack(Caster@0x48, cur, aoe) )
      result &= If( AmountIsGreaterThanZero(cur), b )
      if cur.<vtable+0x2b8>(entities) > 0:  last = AtIndex(tiles, i)    # EVALUE A LA CONSTRUCTION
      prev = cur
  return ExecuteAtomic( result + GetMovementBehavior(last), entities, 0x2a )

`GetTargetTilesSelector()` :
  First( TilesBehindInLine( origin    = CasterTile@0x50,
                            direction = First(SortByDistance(Tiles(Target@0x60), CasterTile@0x50), 1),
                            settings  = NULL, maxAmount = NULL ), 3 )

`GetMovementBehavior(last)` :
  behind   = CanAddUnit( TileBehindTargetFromSourceDirection(last, Owner@0x30) )
  fallback = First( SortByDistance( Randomize(CanAddUnit(AllTiles@0x18)) + CasterTile@0x50, last ), 1 )
  sel      = ConditionalSelector( AmountIsGreater(Count(behind), Get(0)), behind, fallback )
  return     If( CanMove(Caster@0x48), MoveUnit(Caster@0x48, sel, options = {0}) )

TROIS lectures qui ne se devinent pas, toutes tranchees au decompile (jamais au nom) :
 1. `DSLSelectors$$First(source, amount, ignoreForcedTargets)` boxe son `amount` en `DirectAmount`
    et construit un `PickFirstNSelector` = les N PREMIERS -- ce n'est PAS `IdunBattleLogic.Entities.DSLSelectors$$First`, qui
    est un `PickAtIndexSelector` (un INDEX). D'ou `PickFirstN(..., 3)` ici, et `AtIndex(tiles, i)`
    pour le deroulage de la boucle (`DSLSelectors$$AtIndex`, lui, EST le PickAtIndex).
 2. `settings = NULL` n'est pas une absence : `TilesBehindInLineSelector$$.ctor` construit alors un
    `TilesBehindSettings` PAR DEFAUT (tous champs a zero) -> `check_walkable = False` ET
    `update_reference = False`, exactement les defauts du noeud porte. La ligne des 3 tuiles n'est
    donc bornee QUE par le bord du plateau, jamais par la walkabilite ni par l'elevation.
 3. L'ordre `(source, target)` de `TileBehindTargetFromSourceDirection` : tranche au ctor du
    selecteur (`+0x18 = sourceTileSelector`, `+0x20 = targetTileSelector`), pas au nom de la
    factory -- qui, elle, prend `(target, source)`. Les inverser ferait atterrir le caster DEVANT
    la derniere cible au lieu de DERRIERE : observable en live.

`GetTargetUnitsSelector()` (= `Enemies(Caster@0x48, Units(GetTargetTilesSelector(), 1, 3), 3)`) N'EST
PAS porte ici : c'est l'accesseur de la face PREDICTION/UI (« quelles unites cette ability va-t-elle
toucher »), pas un maillon d'`ExecuteBehaviour`, qui reconstruit son propre `Units(AtIndex(...), 0, 0)`
tuile par tuile. Residu nomme, commun aux deux heritieres.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ....dsl.base import Const
from ....dsl.effects import ExecutionContext
from ....entities.behaviours import AtomicGroup, If, op_add, op_and
from ....entities.effects.magnitude import ability_var, ability_var_array
from ....entities.formulas import Count, Get
from ....entities.selectors.accessors import CasterTile, Owner, Target
from ....entities.selectors.geometry import (AtIndex, Cache, ConditionalSelector, PickFirstN,
                                             Randomize, TilesBehindInLine)
from ....entities.selectors.tiles import (AllTiles, CanAddUnit, Caster,
                                          TileBehindTargetFromSourceDirection)
from ....entities.selectors.units import Enemies, SortByDistance, Tiles, Union, Units
from ....entities.triggers import AmountIsGreater, AmountIsGreaterThanZero, CanMove
from ...components import PositionComponent, StatsComponent
from ..base import ActiveAbility
from ..behaviours.combat import AttackWithAbilityDamage
from ..behaviours.context import entities_from_state
from ..behaviours.movement import MoveUnit

if TYPE_CHECKING:                                     # pragma: no cover
    from ...state import State


#: Longueur de la vague. Ce n'est PAS une constante de config : c'est le litteral `3` du
#: `First(..., 3)` de `GetTargetTilesSelector` ET la borne `local_1f0 > 2` de la boucle
#: d'`ExecuteBehaviour` -- les deux valent 3, et la config le confirme (`dmg` porte 3 valeurs par
#: niveau, sur les DEUX heritieres). On garde le nom du role, pas le chiffre nu.
DIVE_ATTACK_TILES = 3


def dive_attack_caster_level_mult(state: "State", caster_id: int):
    """`(active_ability_level, AbilityVariablesMultiplierPercentage)` du caster -- l'`AbilityState`
    que le natif passe a `AbilityConfiguration$$GetVariableArrayForLevel` (il porte le NIVEAU qui
    indexe la variable et le MULTIPLICATEUR de rarete qui la scale). MEME source que
    `ability_attack_params` et que le jumeau de `runner/abilities/bloodangels.py`."""
    ce = state.get_entity(caster_id)
    sc = ce.get_component(StatsComponent) if ce is not None else None
    ctx = sc.ctx if sc is not None else None
    level = getattr(ctx, "active_ability_level", 0) if ctx is not None else 0
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    return level, mult


def dive_attack_profile(ability_id: str) -> str:
    """`AActiveAbility$$GetDamageProfile` -> `AbilityConfiguration$$GetDamageProfile(config@+0x60)` :
    la constante `damageProfile` de la config de l'ability, RELUE du gameconfig, jamais codee en dur.

    Elle DIFFERE entre les deux heritieres (`Piercing` sur 1064, `Power` sur 1091) : c'est
    precisement l'un des trois axes que la base ne fige pas."""
    import gameconfig as GC
    consts = (GC.ability(ability_id) or {}).get("constants") or {}
    return str(consts.get("damageProfile") or "")


def dive_attack_hits(ability_id: str) -> int:
    """`AbilityConfiguration$$GetNumberConstant(config@+0x60, 0x2f)` = `AbilityConstantType.nrOfHits`,
    enveloppe par `DSLFormulas$$Direct` et passe en 6e argument (`hits`) de
    `DSLBehaviors$$AbilityDamage`. Constante absente -> 1 (une application), jamais 0 : un `hits` nul
    ferait un no-op silencieux la ou le natif frappe."""
    return int(ability_var(ability_id, "nrOfHits", is_constant=True) or 1)


def dive_attack_damages(ability_id: str, level, multiplier_pct: int = 100) -> list:
    """`AbilityConfiguration$$GetVariableArrayForLevel(cfg, 0xb = AbilityVariableType.dmg,
    abilityState, 0)` : les DEGATS PAR TUILE de la vague -- 3 valeurs, une par rang de la ligne.

    La config stocke la cellule de niveau comme une chaine CSV (1064 : `"164,128,91"` au niveau 17 ;
    1091 : `"1819,1455,1091"` au niveau 65) ; le natif, lui, rend un `int[]` dont `ExecuteBehaviour`
    lit la longueur (`+0x18`) et les elements (`+0x20`). L'accesseur vectoriel `ability_var_array`
    fait ce decoupage et applique le scaling rarete PAR ENTREE (`dmg` est bien dans
    `variablesAffectedByRarityBonus`, sur les deux configs).

    Le natif ne borne PAS la boucle par la longueur du tableau -- il la borne a 3 et LEVE si l'index
    depasse (`if (i >= arr.Length) throw`). Le port rend la liste telle quelle et l'appelant s'arrete
    a `min(3, len)` : une config amputee produit une vague plus courte au lieu d'une exception, et
    c'est la seule divergence, nommee ici."""
    return ability_var_array(ability_id, "dmg", level, multiplier_pct=multiplier_pct) or []


def dive_attack_is_melee(ability_id: str) -> bool:
    """`attackRangeType` de la config -- il decide quelle ARME du caster le volet PERCAGE lit.
    `Melee` sur les DEUX heritieres, mais RELU par ability : le supposer commun serait exactement la
    generalisation que le `CLAUDE.md` interdit sur les donnees de config."""
    import gameconfig as GC
    return str((GC.ability(ability_id) or {}).get("attackRangeType") or "") == "Melee"


def dive_attack_target_tiles_selector():
    """`DiveAttackAbilityBase$$GetTargetTilesSelector` -- MIRROR du DECOMPILE (cf. l'en-tete) :

        First( TilesBehindInLine( CasterTile@0x50,
                                  First(SortByDistance(Tiles(Target@0x60), CasterTile@0x50), 1) ), 3 )

    `Tiles(Target)` = les tuiles occupees par la CIBLE (une grande unite en occupe plusieurs) ;
    `SortByDistance(..., CasterTile)` + `First(1)` retient CELLE qui touche le caster -- c'est elle
    qui donne la direction de la vague. `TilesBehindInLine` prolonge la ligne au-dela, et sa 1re
    tuile rendue EST cette tuile de la cible (propriete du noeud, deja live-reconciliee par ses
    autres consommateurs), donc `First(3)` = « la cible + 2 hexes derriere » -- exactement l'i2.

    Les DEUX `First` natifs sont des `DSLSelectors$$First` = `PickFirstN` (un CARDINAL), pas des
    index -- cf. lecture 1 de l'en-tete."""
    tuile_de_contact = PickFirstN(SortByDistance(Tiles(Target()), CasterTile()), 1)
    return PickFirstN(TilesBehindInLine(CasterTile(), tuile_de_contact), DIVE_ATTACK_TILES)


def dive_attack_movement_behaviour(last_tile_sel):
    """`DiveAttackAbilityBase$$GetMovementBehavior(lastUnitTile)` -- MIRROR du DECOMPILE :

        behind   = CanAddUnit( TileBehindTargetFromSourceDirection(lastUnitTile, Owner@0x30) )
        fallback = First( SortByDistance( Randomize(CanAddUnit(AllTiles@0x18)) + CasterTile@0x50,
                                          lastUnitTile ), 1 )
        sel      = ConditionalSelector( AmountIsGreater(Count(behind), Get(0)), behind, fallback )
        return     If( CanMove(Caster@0x48), MoveUnit(Caster@0x48, sel, options = {0}) )

    C'est le « Lands in the hex directly behind the last target hit, or - in case that hex is
    occupied - to the closest free hex to it » de l'i2, verbatim : la branche VRAIE est la tuile
    derriere, la branche FAUSSE la tuile libre la plus proche d'elle.

    ⚠ RNG -- le `ConditionalSelector` n'evalue QU'UNE branche (mirror lu, cf. son noeud), et la
    branche FAUSSE contient un `Randomize` sur toutes les tuiles libres du plateau = une permutation
    aleatoire COMPLETE, donc `len(pool)` tirages. Evaluer les deux branches, ou court-circuiter
    celle-la, desalignerait tout le flux RNG en aval. Le `SortByDistance` qui suit est STABLE :
    l'ordre aleatoire ne survit que sur les EX AEQUO de distance -- c'est exactement ce qui rend la
    tuile de repli non deterministe quand plusieurs tuiles libres sont a egale distance.

    ⚠ `CasterTile` est UNIONNEE au pool de repli (`op_Addition`) : le caster peut donc « atterrir »
    sur sa propre tuile, c'est-a-dire ne pas bouger. C'est LU, pas deduit -- et c'est ce qui garantit
    que le repli n'est jamais vide.

    `options = {0}` : les 0x40 octets de la struct passee a `DSLBehaviors$$MoveUnit` sont TOUS nuls
    au call-site (defauts natifs), donc aucun des 5 selecteurs d'options n'est arme -- meme regime
    que le `MoveUnit` de ThunderousAssault, cf. la docstring du noeud."""
    behind = CanAddUnit(TileBehindTargetFromSourceDirection(last_tile_sel, Owner()))
    repli = PickFirstN(
        SortByDistance(Union(Randomize(CanAddUnit(AllTiles())), CasterTile()), last_tile_sel), 1)
    sel = ConditionalSelector(AmountIsGreater(Count(behind), Get(0)), behind, repli)
    return If(CanMove(Caster()), MoveUnit(Caster(), sel))


def _dive_attack_leaf(cur_sel, montant: int, profil: str, hits: int, is_melee: bool):
    """LA feuille de degat -- `DSLBehaviors$$AbilityDamage(caster@0x48, cur, Direct(dmg[i]), profS,
    hitsF, aoe, isOutsideAttack = false, selectionType = 2)`, qui construit un
    `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour` et route
    `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits`.

    `native_operation="ability"` est la traduction EXACTE de cette Operation : percage/armure + mods
    DEFENSEUR + block + bouclier + caps (mode 2), AUCUN crit (la famille ABILITY n'a pas de slot
    `RollCritical`), et **0 tirage de valeur** puisque le montant est FIXE (`Direct`, min == max).
    C'est ce qui distingue cette vague d'une attaque d'arme et c'est ce que la validation live doit
    separer : le `dmg_bonus` entre par les mods, le `pierce` par le profil de la config, et le `crit`
    n'entre PAS -- l'absence de crit est un OBSERVABLE, pas une simplification.

    ⚠ FOLD NOMME -- `StartAttack` / `FinishAttack`. Le natif encadre CHAQUE maillon par
    `If(!AreEqual(cur, prev), StartAttack(...))` et `If(!AreEqual(cur, next), FinishAttack(...))` :
    ces deux behaviours empilent/depilent le contexte d'attaque (`MatchState+0x60`, cf.
    `IdunBattle.Core.MatchState$$StartAttack` / `$$FinishAttack`). Leur SEUL effet observable est de
    FUSIONNER en UNE attaque les tuiles consecutives occupees par la MEME unite -- le cas d'une
    grande unite couchee sur 2 ou 3 tuiles de la ligne, qui prend alors `dmg[i] + dmg[i+1]` sous un
    seul `StartAttack`. Le port n'a aucun substrat DSL pour cette pile ; il emet donc une attaque
    d'ability PAR TUILE. Le TOTAL de degats est identique ; ce qui differe est le nombre d'attaques
    encadrantes (donc le rang des triggers on-attack). Residu documente, mesure a part."""
    return AttackWithAbilityDamage(cur_sel, profil, Const(int(montant)),
                                   is_melee=bool(is_melee), hits=max(1, int(hits)),
                                   multi=True,                # le behaviour resout son selecteur en LISTE
                                   native_operation="ability")  # AbilityDamageOperation$$ExecuteHits


def dive_attack_tree(entities, damages, profil: str, hits: int, is_melee: bool):
    """Arbre de `DiveAttackAbilityBase$$ExecuteBehaviour` (MIRROR du DECOMPILE ; la boucle C# native
    est DEROULEE ici, comme elle l'est chez le natif -- ce n'est pas un raccourci de port, c'est la
    CONSTRUCTION du behaviour). Rend `(noeud, last_tile_sel, cibles_par_tuile)`.

    Le natif deroule 3 iterations (borne `local_1f0 > 2`) et, DANS LA MEME BOUCLE, fait DEUX choses
    de natures differentes -- c'est le point a ne pas confondre :

      * il ASSEMBLE le behaviour (`result &= If(AmountIsGreaterThanZero(cur), b)`), qui sera execute
        plus tard par `ExecuteAtomic` ;
      * il EVALUE `cur` immediatement (`cur.<vtable+0x2b8>(entities)`, un cardinal) pour retenir la
        DERNIERE tuile portant un ennemi -- `last`, l'ancre du deplacement.

    Donc **`last` est fige sur l'etat AU MOMENT DU CAST**, avant tout degat : une unite tuee par le
    1er coup compte quand meme comme « derniere cible touchee » si elle est sur la 3e tuile. C'est
    LU, et c'est directement observable (le caster atterrit derriere un cadavre).

    Cette evaluation a un second effet, voulu : elle REMPLIT le `Cache` de chaque `cur`. L'ensemble
    des ennemis de la tuile `i` est donc FIGE au cast et ne change plus pendant l'execution --
    memoisation OBSERVABLE, exactement comme chez `SilentDeath`.

    `last` vaut `Target@0x60` par defaut : si AUCUNE des 3 tuiles ne porte d'ennemi (regime que le
    gate de cible rend theorique, mais que le natif prevoit), le deplacement s'ancre sur la cible.

    `prev` demarre a `DSLSelectors$$None()` = selecteur VIDE ; `AreEqual(cur, prev)` est alors faux,
    donc le 1er maillon ouvre bien son attaque.

    L'ARBRE EST RECONSTRUIT PAR CAST (les `Cache` sont a etat) -- appeler cette fonction une fois par
    `execute_behaviour`, jamais la memoiser au niveau module."""
    tiles = dive_attack_target_tiles_selector()
    node = None                                   # `DSLBehaviors.Nothing()` : feuille NEUTRE, NON materialisee
    last_tile_sel = Target()                      # `last = <DSLSelectors+0x60>`
    cibles = []
    for i in range(min(DIVE_ATTACK_TILES, len(damages))):
        # `Cache( Enemies(Caster@0x48, Units(AtIndex(tiles, i), unique=0, sel=0), 0), 1 )`.
        # `unique = 0` (regime `SelectAllUnits`, sans dedoublonnage) est INERTE ici : `AtIndex` rend
        # UNE tuile, donc au plus un occupant -- le dedoublonnage inconditionnel du noeud porte
        # (residu #433-r3-r1a-r1) ne peut pas mordre.
        cur = Cache(Enemies(Units(AtIndex(tiles, i))))
        maillon = _dive_attack_leaf(cur, damages[i], profil, hits, is_melee)
        # `result &= If(AmountIsGreaterThanZero(cur), b)` -- le gate « cette tuile porte un ennemi ».
        etage = If(AmountIsGreaterThanZero(Count(cur)), maillon)
        node = etage if node is None else op_and(node, etage)
        # EVALUATION IMMEDIATE (cf. docstring) : elle fige `last` ET amorce le `Cache`.
        occupants = cur.evaluate(entities)
        cibles.append(list(occupants or []))
        if occupants:
            last_tile_sel = AtIndex(tiles, i)
    return node, last_tile_sel, cibles


def dive_attack_pos_of(state: "State", unit_id: int):
    """Position `(col,row)` courante d'une unite, pour l'observable `moved`/`landed_on` du retour.
    PLOMBERIE de rapport -- aucun equivalent natif, et rien du behaviour n'en depend."""
    u = state.get_entity(unit_id)
    pc = u.get_component(PositionComponent) if u is not None else None
    return (pc.col, pc.row) if pc is not None else None


class DiveAttackAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DiveAttackAbilityBase` -- la classe de BASE.

    Elle porte `ExecuteBehaviour` et rien d'autre de commandable : les heritieres n'ajoutent QUE
    leur identite (`ABILITY_TYPE`, `ABILITY_ID`) et les deux donnees du registre
    (`TARGETING_OPTIONS` ici, `ABILITY_ATTACK_TYPE` dans `abilities/attack_type.py`), ce qui mirrore
    exactement des classes filles dont le corps entier est un appel au ctor de la base.

    Retour : {ability, caster, target, tiles, wave, damages, occupants, landed_on, moved, dsl}."""
    __slots__ = ()

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ability_id = self.ABILITY_ID
        level, mult = dive_attack_caster_level_mult(state, caster_id)
        damages = dive_attack_damages(ability_id, level, mult)  # GetVariableArrayForLevel(0xb = dmg)
        if not damages:
            return None                                        # config absente -> aucun behaviour
        hits = dive_attack_hits(ability_id)                    # GetNumberConstant(0x2f = nrOfHits)
        profil = dive_attack_profile(ability_id)               # GetDamageProfile()
        is_melee = dive_attack_is_melee(ability_id)            # attackRangeType de la config
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        # Arbre NEUF par cast (les `Cache` ont un etat). La construction EVALUE deja les 3 `cur` --
        # c'est le natif qui le fait, pas le port (cf. `dive_attack_tree`).
        node, last_tile_sel, cibles = dive_attack_tree(entities, damages, profil, hits, is_melee)
        avant = dive_attack_pos_of(state, caster_id)
        # `ExecuteAtomic( result + GetMovementBehavior(last), entities, 0x2a )`. `op_add` = le
        # `AbilityBehaviour$$op_Addition` natif : sequence SANS court-circuit -- tous les degats,
        # PUIS le deplacement. L'inverse ferait bouger le caster avant de frapper.
        arbre = op_add(node, dive_attack_movement_behaviour(last_tile_sel))
        AtomicGroup(arbre).execute(entities, ectx)
        apres = dive_attack_pos_of(state, caster_id)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAbilityDamage"]
        vague = [{"target": p.get("target"), "attack": p.get("attack"),
                  "total": (p.get("attack") or {}).get("total")} for p in atks]
        return {"ability": ability_id, "caster": caster_id, "target": target_id,
                "tiles": DIVE_ATTACK_TILES, "wave": vague, "damages": list(damages),
                "occupants": [[u.get("id") for u in lot if isinstance(u, dict)] for lot in cibles],
                "landed_on": apres, "moved": (avant != apres), "dsl": True}
