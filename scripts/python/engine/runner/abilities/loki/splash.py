"""Abilities actives de SPLASH/AoE du namespace natif `Abilities.Active.Loki.*` — attaque principale +
volet splash multi-cible : CrushingClaws, PlasmaGrenade, Stikkbomb, Fragstorm, ScythingTalons.
+ les helpers de ciblage splash partages (`_adjacent_to_both`, `_adjacent_enemies_of`,
`_splash_ability_behaviour` = oracles imperatifs des tests ; `_pick_randomly_n` = PickRandomly, consomme
par `../behaviours.py` et `../genestealer.py`). Cf. `loki/__init__.py`."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ..base import ActiveAbility, ability_attack_params
from ..targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGED_BOOL_FALSE, RANGED_BOOL_TRUE,
                         TargetingOptions, custom_range)
from ..targeting_rule import TargetingRule as TR
from ...operations.damage import AttackDamageOperation
from ...components import OwnerComponent, PositionComponent, UnitComponent
from ....entities.effect_type import EffectType
from ....entities.active_ability_type import ActiveAbilityType
from ....dsl.base import Const
from ....dsl.effects import ExecutionContext
from ....entities.behaviours import Foreach, If, AtomicGroup, op_add, op_and
from ....entities.selectors.accessors import CasterTile, Subject, Target, TargetTile
from ....entities.selectors.tiles import AdjacentTiles, Caster
from ....entities.selectors.units import (
    AdjacentEnemies, AdjacentFriends, AdjacentUnits, Alive, And, Friends, Sub, SurroundingEnemies,
    Tiles, Unique, Units, UnitsWithoutTrait, Unobscured
)
from ....entities.triggers import IsAlive
from ....entities.traits.unit_trait import UnitTrait
from ..behaviours.combat import AttackWithAttackDamage
from ..behaviours.context import entities_from_state
from ..behaviours.effects import AddBondEffect, AddEffect
from ..behaviours.movement import PushUnit
from ....entities.unit_selection_type import UnitSelectionType

#: `UnitSelectionType` LU au dernier argument des `DSLSelectors$$*` de ce fichier -- releve
#: #585-r1, build `rnca9r7q6c`, littéral par littéral (JAMAIS par symetrie : deux call-sites
#: du releve passent `Any` parce que leur source est un ensemble de MORTS).
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3


if TYPE_CHECKING:
    from ...state import State

TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)   # 27 — COMPOSITE -> 25/26/1237 ; bond (CrushingClaws)
PINNED = int(EffectType.Pinned)                         # 1065 — UI « Suppressed » — stat-mod Movement


def crushing_claws_splash_tree() -> "op_add":
    """Corps `Func<entities,behaviour>` du `Foreach` splash = lambda `<ExecuteBehaviour>b__0 IdunBattleLogic.Entities.Abilities.Active.Loki.CrushingClawsAbility.u003Cu003Ec__DisplayClass1_0$$u003CExecuteBehaviouru003Eb__0`
    (DECOMPILE) pour l'unite splash COURANTE (`Subject()`, posee par le `Foreach`) :
        PushUnit(caster, s)                                          # [DEPLACEMENT differe -> omis]
        + If(IsAlive(s)) AddEffect(0x429 Pinned, stateRef, s, 0)     # « Suppressed » splash (duree DEFAUT)
        + If(IsAlive(s)) AttackWithAttackDamage(caster, s, MinMaxDamage2, GetDamageProfile2=Physical,
                                                GetNumberConstant(0x32)=nrOfHits_2)
    `If(IsAlive(Subject()))` gate le pin ET l'attaque : le natif inclut les morts-adjacents dans le SET et
    les skippe ICI (l'imperatif les pre-excluait via `_adjacent_to_both` -> MEME resultat observable).
    **slice-21a** : `PushUnit(Caster(), s)` est PORTE (recul du splash 1 hex a l'oppose du caster), place EN
    TETE et UNGATED (== le natif : le push precede le pin/attaque et n'est pas gate par IsAlive). `op_add` =
    `op_Addition` (`CombinedBehaviour`, effets purs -> tous les volets s'executent). Le push est DETERMINISTE
    (aucun rng) -> n'affecte pas l'ordre RNG du degat. Volet secondaire = clés `minDmg_2`/`maxDmg_2`/
    `nrOfHits_2` (profil Physical). En 1v1 le SET splash est vide -> ce corps ne s'execute pas (aucun push)."""
    s = Subject()
    return op_add(op_add(
        PushUnit(Caster(), s),                                      # recul du splash (avant pin/attaque, ungated)
        If(IsAlive(s), AddEffect(PINNED, "Pinned", s, None))),      # duree DEFAUT (arg natif 0, sans TurnsFromRounds)
        If(IsAlive(s), AttackWithAttackDamage(s, "CrushingClaws", "Physical", is_melee=True,
                                               min_key="minDmg_2", max_key="maxDmg_2", hits_key="nrOfHits_2")))


def crushing_claws_tree() -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.CrushingClawsAbility$$ExecuteBehaviour` (id 1105, tyranTyrantGuard — MIRROR du
    DECOMPILE + du lambda `<ExecuteBehaviour>b__0 IdunBattleLogic.Entities.Abilities.Active.Loki.CrushingClawsAbility.u003Cu003Ec__DisplayClass1_0$$u003CExecuteBehaviouru003Eb__0`) :
        splash = UnitsWithoutTrait( AdjacentEnemies(caster) & (AdjacentFriends(target) - target), 0xd=Object )
        ExecuteAtomic(
            ((  AddBondEffect(0x1b Taunted, caster, target, TurnsFromRounds(1))            # taunt cible
              + AddEffect(0x429 Pinned, target, DEFAUT) )                                  # « Suppressed » cible
              + AttackWithAttackDamage(caster, target, MinMaxDamage, Piercing, 0x2f=2) )   # attaque principale
            + Foreach(splash, crushing_claws_splash_tree) )
    Port mirror-natif. `AdjacentEnemies(caster) & (AdjacentFriends(target) - target)` = ennemis du caster
    adjacents aux DEUX (les amis de la cible = ennemis du caster) -> convention ETABLIE Harvester
    (`AdjacentEnemies(<tile>)` = ennemis-du-caster autour de <tile>, active_ability.py) :
    `And(AdjacentEnemies(CasterTile()), AdjacentEnemies(TargetTile()))` — chaque centre s'auto-exclut
    (`_within` d>0), donc target/caster hors splash. `UnitsWithoutTrait(Object=13=0xd)` exclut la scenerie
    (0xd MAPPE UnitTrait.Object #158 ; l'imperatif le SKIPPAIT -> le DSL est PLUS fidele, degrade en no-op
    pour une unite sans le trait). ORDRE natif = taunt, pin, main, foreach (l'imperatif faisait main
    d'abord ; equivalent bit-exact : taunt/pin ne tirent PAS de rng et n'affectent pas le degat principal ->
    MEME sequence rng). **slice-21a** : `PushUnit(caster, s)` du splash est PORTE (recul 1 hex, dans
    `crushing_claws_splash_tree`, deterministe -> n'affecte pas l'ordre rng du degat). `KillDeadUnits`/
    `MoveUnit(caster)` restent differes. Duree Pinned = DEFAUT (`duration_rounds=None`). Bit-exact BY
    CONSTRUCTION (memes Operations/args/state.rng que l'imperatif). L'imperatif `CrushingClawsAbility.
    execute_behaviour` est REMPLACE par l'execution de l'arbre."""
    tgt = Target()
    # duree = `TurnsFromRounds(1)` natif (IdunBattleLogic.Entities.Abilities.Active.Loki.CrushingClawsAbility$$ExecuteBehaviour) -> convertie par `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns (#98)
    # `bonded_ref = Caster()` = le **5e argument** de `IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect`
    # au call-site (`CrushingClawsAbility$$ExecuteBehaviour` : `AddBondEffect(ctx, 0x1b, stateRef,
    # <sel +0x48>, <sel +0x60>, <sel +0x48>, TurnsFromRounds(1))` -- `+0x48` = Caster, `+0x60` = Target,
    # le meme couple que l'`AttackWithAttackDamage` juste au-dessus). C'est ce que relit
    # `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId`, et donc la SEULE cible que la cible
    # tauntee aura le droit d'attaquer (`TargetIsAllowedForCaster`, #436).
    taunt = AddBondEffect(TAUNTED, "Taunted_OnlySpecificTargets", Caster(), tgt, duration_rounds=1,
                          bonded_ref=Caster())
    pin = AddEffect(PINNED, "Pinned", tgt, None)                                       # AddEffect(0x429), duree DEFAUT
    main = AttackWithAttackDamage(tgt, "CrushingClaws", "Piercing", is_melee=True)    # MinMaxDamage/Piercing/0x2f=2
    # #585-r1 -- ⚠ MOITIE IMPLICITE : `...CrushingClawsAbility$$ExecuteBehaviour` ecrit
    # `AdjacentEnemies(gs, gs@0x48, unique: 1, 3)` (VARIANTE A, explicite) puis
    # `AdjacentFriends(gs, gs@0x60, gs@0x78, unique: 1)` -- VARIANTE B, qui code `3` EN DUR et dont
    # le port fait le second `AdjacentEnemies` (allies de la CIBLE = ennemis du caster). Le `3` du
    # second terme ne s'ecrit donc NULLE PART dans le corps natif ; il se lit a la XREF ENTRANTE.
    # Puis `UnitsWithoutTrait(gs, ., 0xd, 3)`, explicite.
    splash = UnitsWithoutTrait(
        And(AdjacentEnemies(CasterTile(), Const(1), selection_type=SELECTION),
            AdjacentEnemies(TargetTile(), Const(1), selection_type=SELECTION)),
        int(UnitTrait.Object), selection_type=SELECTION)                                # UnitsWithoutTrait(0xd)
    return AtomicGroup(op_add(
        op_add(op_add(taunt, pin), main),                                             # ((taunt+pin)+main)
        Foreach(splash, crushing_claws_splash_tree())))                               # + foreach(splash)


def plasma_grenade_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaGrenadeAbility$$ExecuteBehaviour` (id 1098, eldarSmnGuardian — MIRROR du
    DECOMPILE) :
        Execute( op_Addition(
            AttackWithAttackDamage(caster, target, RandomAmount(minDmg=var0xc, maxDmg=var0xd), Plasma,
                                    nrOfHits=GetNumberConstant(0x2f)),                        # [MAIN]
            AttackWithAttackDamage(caster, Enemies(caster, AdjacentUnits(target,1)), RandomAmount(MEME),
                                    Plasma, nrOfHits_2=GetNumberConstant(0x32)) ) )           # [SPLASH]
    Port : `op_add(main, splash)`. Le SPLASH natif passe un SELECTEUR MULTI-cible directement a UN
    `AttackWithAttackDamage` (PAS un `Foreach`) -> `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` resout la liste,
    l'`OrderBy` puis attaque chaque cible : porte via `multi=True` (feuille `AttackWithAttackDamage`, tri
    par id = ordre de lecture natif). Selecteur splash = `Alive(AdjacentEnemies(TargetTile()))` = ennemis
    VIVANTS du caster adjacents (hex) a la CIBLE (`AdjacentEnemies(<tuile>)` = ennemis-du-caster autour de
    <tuile>, convention Harvester/CrushingClaws ; `Alive` = compense l'inclusion des cadavres offline, mirror
    du fait que le natif `Units(AdjacentTiles)` n'a que les unites DEBOUT = vivantes, cf. `AllUnits`=alive
    #202). La plage `RandomAmount(minDmg/maxDmg)` est PARTAGEE main/splash (memes cles config par defaut) ;
    seule la constante de coups differe (nrOfHits vs nrOfHits_2 = 0x2f/0x32). Profil Plasma, ranged (range 2).
    `op_Addition` = effets purs -> les deux volets s'executent ; plain `Execute` (PAS ExecuteAtomic). Bit-exact
    BY CONSTRUCTION vs l'ancien imperatif (memes bornes/hits/profil, splash `sorted` par
    id, meme `state.rng`). L'imperatif `PlasmaGrenadeAbility.execute_behaviour` est REMPLACE par cet arbre."""
    tgt = Target()
    # rngcrit-1202 : la factory native de PlasmaGrenade est `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`
    # (XREFS IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaGrenadeAbility$$ExecuteBehaviour+0x1ba/IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaGrenadeAbility$$ExecuteBehaviour+0x22e ->
    # l'ENVELOPPE `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage(damageProfile:System.Nullable<IdunBattle.Entities.Enum.DamageProfileType>, hits:System.Int32)`
    # -> le COEUR `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage(abilityOrEffect, options:IdunBattle.Entities.Behaviours.AbilityDamageBehaviourOptions)`
    # = AbilityDamageBehaviour -- #1032-r5 : cette chaine disait `X -> core X`, une tautologie nee
    # de la migration VA -> SYMBOLE ; le parametre qui separe les quatre surcharges est LU dans
    # `data/symbols/<build>/frida/methods.tsv`), PAS
    # AttackWithAttackDamage comme l'ancien commentaire le disait -> AbilityDamageOperation = 1 tirage/
    # coup (AUCUN resolve slot-8 gaspille) -> native_factory="ability".
    main = AttackWithAttackDamage(tgt, "PlasmaGrenade", "Plasma", is_melee=False,
                                  native_factory="ability")                             # RandomAmount/Plasma/0x2f
    splash = AttackWithAttackDamage(Alive(AdjacentEnemies(TargetTile())), "PlasmaGrenade", "Plasma",
                                     is_melee=False, hits_key="nrOfHits_2", multi=True,
                                     native_factory="ability")                          # MEME plage, 0x32
    return op_add(main, splash)


def scything_talons_tree() -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ScythingTalonsAbility$$ExecuteBehaviour` (id 1065, tyranSmnWarrior — MIRROR du
    DECOMPILE) :
        splash = Unique( Enemies(caster, AdjacentUnits(casterTile,1) & AdjacentUnits(targetTile,1), 3) )
        ExecuteAtomic( op_BitwiseAnd(
            AttackWithAttackDamage(caster, target, MinMaxDamage, Bio, condHits1=GetNumberConstant(0x2f)=3),
            AttackWithAttackDamage(caster, splash,  MinMaxDamage, Bio, condHits2=GetNumberConstant(0x32)=2) ) )
    Port : `AtomicGroup( op_and( AttackWithAttackDamage(Target(),"ScythingTalons","Bio",melee),
                                 AttackWithAttackDamage(<splash>,"ScythingTalons","Bio",melee,
                                                         hits_key="nrOfHits_2", multi=True) ) )`.
    Le SPLASH natif passe un SELECTEUR MULTI-cible directement a UN `AttackWithAttackDamage` (PAS un `Foreach`
    -> DIFFERE de CrushingClaws) : `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` resout la liste + `OrderBy` (cle
    par-unite = ordre de lecture) puis attaque chaque cible -> porte via `multi=True` (feuille
    `AttackWithAttackDamage`, tri par id = ordre de lecture natif). Selecteur splash =
    `Alive(And(AdjacentEnemies(CasterTile()), AdjacentEnemies(TargetTile())))` = ennemis du caster adjacents
    (hex) aux DEUX tuiles (== l'imperatif `_adjacent_to_both`) : le natif `Enemies(A ∩ B)` == `Enemies(A) ∩
    Enemies(B)` (Enemies DISTRIBUE sur l'intersection) et `Unique` est un no-op (`And` dedup deja par id).
    `Alive` compense l'inclusion des cadavres offline (mirror du fait que le natif `AdjacentUnits` n'a que les
    unites DEBOUT = vivantes, convention PlasmaGrenade #202/#148). La plage `MinMaxDamage(minDmg/maxDmg)` est
    PARTAGEE main/splash ; seule la constante de coups differe (nrOfHits 0x2f=3 vs nrOfHits_2 0x32=2). Profil
    Bio, MELEE (range 1).
    `op_BitwiseAnd` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ; `ExecuteAtomic` ->
    `AtomicGroup` (inline #201 ; le tag `0x57` = id du groupe atomique, PAS un auto-fire de triggered-abilities
    -- `IdunBattle.Entities.Abilities.AActiveAbility$$ExecuteAtomic` = `DSLFactory.AtomicGroup`, aucun `EvaluateAbilities` implicite, cf. #209).
    Ordre = main PUIS splash (== l'ancien imperatif, meme `state.rng`) -> bit-exact BY CONSTRUCTION vs
    l'ancien imperatif (`_adjacent_to_both`). L'imperatif `ScythingTalonsAbility.execute_behaviour` est
    REMPLACE par cet arbre.
    GAP (hors migration, tache #211) : les coups natifs = `ConditionalAmount(HasTrait(target,
    UnitTrait.Summon=2), hits*2, hits)` -> DOUBLENT si la CIBLE est un SUMMON (main 3->6, splash 2->4). Coups
    de BASE portes ici (== l'imperatif, jamais de sur-compte) ; le doublement = tranche behaviour-changing separee."""
    tgt = Target()
    main = AttackWithAttackDamage(tgt, "ScythingTalons", "Bio", is_melee=True)                 # MinMaxDamage/Bio/0x2f=3
    # #585-r1 : `...ScythingTalonsAbility$$ExecuteBehaviour` ecrit `AdjacentUnits(gs, gs@0x50,
    # unique: 1, 3)` ET `AdjacentUnits(gs, gs@0x60, unique: 1, 3)`, puis `Enemies(gs, gs@0x48, ., 3)`
    # -- les trois EXPLICITES (aucune variante B ici, contrairement a CrushingClaws ci-dessus).
    # Le port collapse `Enemies(A n B)` en deux `AdjacentEnemies` ; predicat PUR, donc idempotent.
    splash = AttackWithAttackDamage(
        Alive(And(AdjacentEnemies(CasterTile(), Const(1), selection_type=SELECTION),
                  AdjacentEnemies(TargetTile(), Const(1), selection_type=SELECTION))),
        "ScythingTalons", "Bio", is_melee=True, hits_key="nrOfHits_2", multi=True)              # MEME plage, 0x32=2
    return AtomicGroup(op_and(main, splash))


def stikkbomb_tree() -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.StikkbombAbility$$ExecuteBehaviour` (id 1051, Ork Boy — MIRROR du DECOMPILE) :
        Execute( AtomicGroup( op_Addition(
            AttackWithAttackDamage(caster, target, RandomAmount(var0xc,var0xd), Blast, nrOfHits=0x2f=2),  # [MAIN]
            AttackWithAttackDamage(caster, AdjacentUnits(target,1,3), RandomAmount(MEME), Blast,
                                   nrOfHits_2=0x32=1) ) ) )                                                # [SPLASH]
    Le SPLASH natif passe un SELECTEUR MULTI-cible directement a UN `AttackWithAttackDamage` (PAS un `Foreach`)
    -> `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` resout la liste + `OrderBy` puis attaque chaque cible : porte via
    `multi=True` (feuille `AttackWithAttackDamage`, tri par id = ordre de lecture natif).

    ⚠ FRIENDLY-FIRE (fidelite #213, RESOLUE) : le selecteur splash = `AdjacentUnits(target,1,3)` BRUT, SANS
    wrapper `Enemies(...)` -- DECOMPILE-conclusif (contraste PlasmaGrenade `Enemies(caster, AdjacentUnits(...))`
    enemies-only et Fragstorm `AdjacentTiles - Tiles(Friends(...))` excl-amis ; `AdjacentUnits`/`Units`/`Enemies`
    decompiles : le 1/3 = flags `UnitsOnTilesSelector`, PAS un masque d'equipe) ET corrobore par l'i2 (Stikkbomb
    = « units in hexes adjacent to the target », les 3 autres = « enemy units »/« excluding friendly hexes »).
    => splash = TOUTES les unites adjacentes a la cible (allies du caster INCLUS), hors cible. Selecteur porte =
    `Alive(AdjacentUnits(TargetTile()))` (AUCUN filtre team ; `Alive` compense les cadavres offline, mirror du
    natif `Units(AdjacentTiles)` qui n'a que les unites DEBOUT = vivantes, cf. PlasmaGrenade #202/#148).

    Plage `RandomAmount(minDmg/maxDmg)` PARTAGEE main/splash (memes cles par defaut) ; seule la constante de
    coups differe (nrOfHits 0x2f=2 vs nrOfHits_2 0x32=1). Profil Blast, RANGED (range 2, Indirect Fire).
    `op_Addition` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ; `AtomicGroup` = inline
    (#201) ; plain `Execute` (PAS ExecuteAtomic, contraste ScythingTalons). Ordre = main PUIS splash (meme
    `state.rng`). L'imperatif `StikkbombAbility.execute_behaviour` (ancien splash `_adjacent_enemies_of` =
    enemies-only, ERRONE) est REMPLACE par cet arbre (et CORRIGE en friendly-fire). Le passif `FireOfAbsolution`
    (trigger) porte le MEME correctif friendly-fire via le SELECTEUR DSL `Alive(Sub(Sub(AdjacentUnits(TargetTile()),
    Caster()), Target()))` (mirror natif `AdjacentUnits(target) − caster − target`, meme bug #213)."""
    tgt = Target()
    main = AttackWithAttackDamage(tgt, "Stikkbomb", "Blast", is_melee=False)                    # RandomAmount/Blast/0x2f=2
    splash = AttackWithAttackDamage(Alive(AdjacentUnits(TargetTile())), "Stikkbomb", "Blast",
                                     is_melee=False, hits_key="nrOfHits_2", multi=True)          # MEME plage, friendly-fire, 0x32=1
    return AtomicGroup(op_add(main, splash))


def fragstorm_tree() -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormAbility$$ExecuteBehaviour` (id 1078, templSmnAggressor — MIRROR du DECOMPILE) :
        ExecuteAtomic( op_BitwiseAnd(
            AttackWithAttackDamage(caster@0x160, target@0x178, RandomAmount(var0xc,var0xd), Blast, nrOfHits=0x2f=4),  # [MAIN]
            AttackWithAttackDamage(caster@0x160,
                PickRandomly( op_Subtraction( AdjacentTiles(target),
                                              Tiles(Friends(caster, AdjacentTiles(target), 3)) ),
                              nrOfTargets=GetNumberConstant(0x11)=4 ),
                RandomAmount(MEME), Blast, nrOfHits_2=0x32=2) ) )                                                     # [SPLASH]
    Le SPLASH natif attaque un SELECTEUR `PickRandomly(<tuiles>, 4)` = jusqu'a 4 HEXES ALEATOIRES adjacents a la
    cible, EXCLUANT les tuiles occupees par un AMI DU CASTER (`AdjacentTiles(target) − Tiles(Friends(caster))`).
    i2 concordant : « 2x [dmg] Blast to up to 4 random hexes adjacent to the target, excluding hexes with
    friendly units on them ». CONTRASTE Stikkbomb (`AdjacentUnits` BRUT = friendly-fire, i2 « units ») : ici le
    natif SOUSTRAIT explicitement les tuiles amies -> enemies-only (les seuls occupants restants d'un duel).

    Port (R28-2, 2026-07-27) : le SPLASH echantillonne des **HEXES**, pas des occupants —
    `Sub(AdjacentTiles(TargetTile()), Tiles(Friends(Units(AdjacentTiles(TargetTile()))), as_ids=True))`
    = les tuiles voisines de la cible MOINS celles portant un ami du caster, **tuiles VIDES INCLUSES**.
    Le `PickRandomly(4)` est FOLDE dans la feuille (`multi=True, pick_n=4, tile_domain=True`) : elle tire
    4 TUILES dans l'ordre source (`Board.neighbours_native`, R28-1), applique l'`OrderBy` sur l'id
    d'entite-tuile, puis ne resout l'occupant qu'ENSUITE (`AttackDamageBehaviour$$ExecuteTarget`) — une
    tuile piquee sans occupant est un COUP GASPILLE. Consequences MESURABLES vs l'ancien pool-en-occupants
    (`Alive(Sub(AdjacentUnits, AdjacentFriends))`, en place jusqu'au 2026-07-27) : le CARDINAL du pool
    passe de « nb d'ennemis adjacents » a « nb de tuiles voisines libres-ou-ennemies » (jusqu'a 6), donc
    (a) le nombre de tirages `_pick_randomly_n` change -> tout le flux rng aval se decale, (b) l'ensemble
    des unites touchees change (un ennemi adjacent peut n'etre PAS touche alors que l'ancien port le
    touchait toujours des qu'ils etaient <= 4).

    `Friends(caster, AdjacentTiles(target), 3)` natif prend un selecteur de TUILES : le port compose
    `Friends(Units(AdjacentTiles(...)))` (le natif `UnitsByTeamSelector` resout l'occupation de la meme
    facon) puis `Tiles(..., as_ids=True)` pour revenir au domaine ID — `Tiles` rend des POSITIONS par
    defaut, qui ne se soustraient PAS a des ids (cf. son docstring).

    Plage `RandomAmount(minDmg/maxDmg)` PARTAGEE main/splash (memes cles par defaut) ; seule la constante
    de coups differe (nrOfHits 0x2f=4 vs nrOfHits_2 0x32=2). Profil Blast, RANGED (range 2).
    `op_BitwiseAnd` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ; `ExecuteAtomic`
    -> `AtomicGroup` (inline #201, == ScythingTalons, CONTRASTE Stikkbomb plain Execute). Ordre = main
    PUIS splash (meme `state.rng`).

    #130 : la LOI de consommation du pick est exacte (`min(len(pool), 4)` tirages, bornes decroissantes,
    MEME quand le pool tient dans 4 -- cf. `_pick_randomly_n`)."""
    # nrOfTargets = GetNumberConstant(0x11), lue live du gameconfig ; 4 = valeur config/i2 (« up to 4 ») si absente.
    n_targets = int(((GC.ability("Fragstorm") or {}).get("constants") or {}).get("nrOfTargets") or 4)
    tgt = Target()
    main = AttackWithAttackDamage(tgt, "Fragstorm", "Blast", is_melee=False)                        # RandomAmount/Blast/0x2f=4
    adj = AdjacentTiles(TargetTile())                                                                # AdjacentTiles(target@0x178)
    # #585-r1 : `Friends(gs, gs@0x48, AdjacentTiles(gs@0x60), 3)` -- littéral LU dans
    # `...FragstormAbility$$ExecuteBehaviour`. ⚠ Le `Units(...)` ci-dessous ne recoit RIEN : le natif
    # passe les TUILES directement a `Friends`, dont `UnitsFromFactionSelector$$Select` resout
    # l'occupant PAR `SelectUniqueUnits` -- ce `Units` est la materialisation de cette resolution,
    # pas un noeud natif. Lui poser un selectionType serait inventer.
    friend_tiles = Tiles(Friends(Units(AdjacentTiles(TargetTile())), selection_type=SELECTION),
                         as_ids=True)                                                            # Tiles(Friends(caster, adjTiles, 3))
    splash_sel = Sub(adj, friend_tiles)                                                              # op_Subtraction -> HEXES (vides inclus)
    splash = AttackWithAttackDamage(splash_sel, "Fragstorm", "Blast", is_melee=False,
                                     hits_key="nrOfHits_2", multi=True, pick_n=n_targets,
                                     tile_domain=True)                                               # MEME plage, PickRandomly(4), 0x32=2
    return AtomicGroup(op_and(main, splash))


def gauntlets_of_ultramar_tree() -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$ExecuteBehaviour` (id 1000, ultraCalgar — MIRROR du
    DECOMPILE) : AoE SELF-CAST a DEUX BANDES DE PORTEE (aucune cible unique -- ancre sur le CASTER, pas
    `Target()`) :
        adjSel  = `IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$GetAdjacentTargetsSelector`  = Unique(Enemies(caster, AdjacentTiles(casterTile), 3))
        surrSel = `IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$GetSurroundingTargetsSelector` = Unobscured(caster,
                     SurroundingEnemies(caster, r=2) - adjSel)
        ExecuteAtomic( op_BitwiseAnd(
            AttackWithAttackDamage(caster, snapshot(adjSel), MinMaxDamage, Bolter,
                                    hits = GetNumberConstant(0x2f) + GetNumberConstant(0x32)),   # BANDE ADJACENTE
            AttackWithAttackDamage(caster, surrSel,          MinMaxDamage, Bolter,
                                    hits = GetNumberConstant(0x32)) ), 0x1d )                     # BANDE SURROUNDING

    - **Deux bandes DISJOINTES par distance** : adjacente = ennemis dist 1 (`AdjacentEnemies(CasterTile())`) ;
      surrounding = ennemis a dist EXACTEMENT 2 = `SurroundingEnemies(r=2)` (DISQUE dist<=2, cf. case-49x
      `bq.surrounding_enemies`) MOINS `AdjacentEnemies` (dist<=1) -> dist 2 seul (le disque exclut deja le
      centre). Aucun chevauchement -> l'ordre eager(adj)/lazy(surr) natif == mes deux `multi=True` sequentiels.
    - **hits par bande (DECOMPILE, `iVar11=const(0x2f)` `iVar12=const(0x32)`)** : adjacente = `iVar12 + iVar11`
      = nrOfHits + nrOfHits_2 (via `hits_add_key`) ; surrounding = `iVar12` = nrOfHits_2 seul. Config 1000 :
      nrOfHits=1, nrOfHits_2=1 -> adjacente 2 coups, surrounding 1 coup. (Le verdict p0-damage.md notait
      surrounding=nrOfHits(0x2f) ; le decompile dit nrOfHits_2(0x32) -- NUMERIQUEMENT identiques ici, les 2
      constantes valant 1 ; je mirror le decompile.)
    - **Plage `MinMaxDamage(minDmg=var0xc, maxDmg=var0xd)` PARTAGEE** (RandomAmount, flag 0) et **profil
      `GetDamageProfile(config,0)` = Bolter** (PiercingRatio 20), pour les DEUX bandes ; seul le nb de coups
      differe. `attackRangeType=Ranged` -> `is_melee=False`.
    - **Snapshot eager de la bande adjacente** (`Get(SelectAllUnits(adjSel)) IdunBattle.DSL.TargetsSelector$$SelectAllUnits`) : le natif fige la
      liste adjacente AVANT la 1re attaque ; comme la 1re attaque est le premier acte et que les bandes sont
      disjointes (tuer un adjacent ne retire aucun ennemi dist-2), la resolution LAZY `multi=True` a
      l'execution == le snapshot -> bit-exact.
    `op_BitwiseAnd` = `CombinedBehaviour` (effets PURS -> les deux bandes s'executent) ; `ExecuteAtomic` ->
    `AtomicGroup` (inline #201 ; tag 0x1d = id du groupe atomique, aucun `EvaluateAbilities` implicite, cf.
    #209). Ordre = adjacente PUIS surrounding, cibles triees par id (OrderBy natif) -> meme `state.rng` ->
    bit-exact BY CONSTRUCTION. `Unobscured` = geometrie DEJA validee live cote PREDICTION (case-49/#50,
    MC1_67) : NE PAS la contredire."""
    adj_sel = Unique(AdjacentEnemies(CasterTile(), Const(1)))                       # Unique(Enemies(AdjacentTiles(caster)))
    surr_sel = Unobscured(                                                          # Unobscured(caster, Surrounding - adj)
        Sub(SurroundingEnemies(CasterTile(), Const(2)), AdjacentEnemies(CasterTile(), Const(1))),
        Caster())
    band_adj = AttackWithAttackDamage(adj_sel, "GauntletsOfUltramar", "Bolter", is_melee=False,
                                      hits_key="nrOfHits", hits_add_key="nrOfHits_2", multi=True)   # 0x2f + 0x32
    band_surr = AttackWithAttackDamage(surr_sel, "GauntletsOfUltramar", "Bolter", is_melee=False,
                                       hits_key="nrOfHits_2", multi=True)                            # 0x32 seul
    return AtomicGroup(op_and(band_adj, band_surr))


def _adjacent_to_both(state: "State", caster_id: int, target_id: int) -> list[int]:
    """Splash CrushingClaws : ennemis VIVANTS du caster adjacents (hex) **À LA FOIS** au caster ET à la
    cible, hors cible. Mirror `IdunBattleLogic.Entities.Abilities.Active.Loki.CrushingClawsAbility$$GetAdjacentDamageTargetsUnits =
    `AdjacentEnemies(actor) & (AdjacentFriends(target) - target)` (les amis de la cible = ennemis du
    caster ⇒ ennemis adjacents aux deux). Requiert `state.board` (evenq). ⚠ exclusion
    `UnitsWithoutTrait(0xd=13)` NON portée (mapping de l'enum trait 13 inconnu offline) → TODO ; sans
    board → [] (no-op fidèle)."""
    board = state.board
    caster = state.get_entity(caster_id)
    tgt = state.get_entity(target_id)
    if board is None or caster is None or tgt is None:
        return []
    cp = caster.get_component(PositionComponent)
    tp = tgt.get_component(PositionComponent)
    co = caster.get_component(OwnerComponent)
    if cp is None or tp is None or co is None:
        return []
    ctile = board.id_at(cp.col, cp.row)
    ttile = board.id_at(tp.col, tp.row)
    if ctile is None or ttile is None:
        return []
    c_neigh = set(board.neighbours(ctile))
    t_neigh = set(board.neighbours(ttile))
    out: list[int] = []
    for eid, e in state.entities.items():
        if eid == caster_id or eid == target_id:
            continue
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if oc is None or pc is None or oc.team == co.team:        # ennemis du caster uniquement
            continue
        if uc is not None and not uc.alive:
            continue
        tile = board.id_at(pc.col, pc.row)
        if tile in c_neigh and tile in t_neigh:                   # adjacent au caster ET à la cible
            out.append(eid)
    return sorted(out)                                            # ordre déterministe (tie-break id)


def _adjacent_enemies_of(state: "State", caster_id: int, target_id: int) -> list[int]:
    """Splash cible-centré ENEMIES-ONLY : ennemis VIVANTS du caster adjacents (hex) à la CIBLE, hors cible.
    Mirror `Enemies(caster, AdjacentUnits(target))` = les ennemis du caster sur `board.neighbours(target tile)`.
    Requiert `state.board` (evenq) ; sans board → [] (no-op fidèle). Ordre déterministe (tie-break id).
    RÉFÉRENCE IMPÉRATIVE des tests de bit-exactness des arbres DSL enemies-only (`Alive(AdjacentEnemies(
    TargetTile()))` de PlasmaGrenade == ce set ; ArmoriumCherub scanne dessus) ; plus aucun appelant PRODUCTION
    (Fragstorm migré ; FireOfAbsolution utilise le sélecteur DSL friendly-fire `AdjacentUnits(target) − caster −
    target`). Équivaut à `Alive(AdjacentEnemies(TargetTile()))` (DSL) = ce set + le filtre `team != caster`."""
    board = state.board
    caster = state.get_entity(caster_id)
    tgt = state.get_entity(target_id)
    if board is None or caster is None or tgt is None:
        return []
    co = caster.get_component(OwnerComponent)
    tp = tgt.get_component(PositionComponent)
    if co is None or tp is None:
        return []
    ttile = board.id_at(tp.col, tp.row)
    if ttile is None:
        return []
    t_neigh = set(board.neighbours(ttile))
    out: list[int] = []
    for eid, e in state.entities.items():
        if eid == caster_id or eid == target_id:
            continue
        oc = e.get_component(OwnerComponent)
        uc = e.get_component(UnitComponent)
        pc = e.get_component(PositionComponent)
        if oc is None or pc is None or oc.team == co.team:        # ennemis du caster uniquement
            continue
        if uc is not None and not uc.alive:
            continue
        if board.id_at(pc.col, pc.row) in t_neigh:                # adjacent à la cible
            out.append(eid)
    return sorted(out)


def _pick_randomly_n(state: "State", items: list, n: int,
                     allow_repeat: bool = False, max_repeats: int = 0x7fffffff) -> list:
    """`IdunBattleLogic.Entities.DSLSelectors$$PickRandomly(source, amount, allowRepeat, maxRepeats)` ->
    `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` — MIRROR 1:1 de la boucle native
    (#130 / GAP #215 CLOS).

    Boucle LUE au décompilé (`allowRepeat` = champ `+0x30`, `maxRepeats` = `+0x34` ; mapping des
    arguments lu dans `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$.ctor` :
    `(entities, source, amount, rng, allowRepeat -> +0x30, maxRepeats -> +0x34, skipForced -> +0x38)`).
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormAbility$$ExecuteBehaviour` passe
    `0`/`0x7fffffff` (SANS repetition) ;
    `IdunBattleLogic.Entities.Abilities.Active.Loki.BasiliskBarrageAbility$$ExecuteBehaviour` passe
    **`1`/`0x7fffffff`** pour ses TROIS tirages d'obus -> AVEC repetition et cap jamais atteint, donc
    le pool ne retrecit JAMAIS : deux obus peuvent tomber sur la MEME tuile (confirme live : un obus
    sur la tuile-cible tire deux fois = 2x `nrOfHits` coups sur son occupant).

    Boucle native (branche `allowRepeat` LUE : le pool ne perd l'element que lorsqu'il apparait
    `maxRepeats` fois dans le resultat) :

        result = []                                   # List<T>
        i = result.Count                              # 0 hors forced-targets
        while i < amount:
            if candidates.Count < 1: return result    # SEULE sortie anticipée
            idx = rng.NextInternal(0, candidates.Count)   # <-- 1 TIRAGE, INCONDITIONNEL
            pick = candidates.ElementAt(idx)
            result.Add(pick)
            if (!allowRepeat)                       candidates.RemoveAt(idx)
            elif (result.Count(x => x == pick) == maxRepeats) candidates.RemoveAt(idx)
            i += 1

    -> **le natif tire `min(len(pool), n)` fois, bornes `len(pool)`, `len(pool)-1`, … 1 — MÊME quand le
    pool tient déjà dans `n`** (il n'y a AUCUN court-circuit `pool.Count <= amount`). La dernière borne
    vaut 1 : `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal` à `range==1` prend la branche
    PUISSANCE-DE-2 qui CONSOMME un `genrand_int32` et retourne 0 — un tirage « sans choix » reste un
    tirage. Court-circuiter DÉSALIGNE tout le flux RNG en aval (dégât/crit/cible suivants).
    MESURÉ LIVE (`probe_215_pick_randomly_rng.py`, PlasmaCannon 1150, deux régimes) :
    pool=1 -> 1 `genrand` de plus que le port court-circuité ; pool=2 -> 2. Sous cette loi le per-coup
    live/offline devient BIT-EXACT (ratio 1.0 partout) sur la main ET le splash.

    L'ordre rendu est l'ordre de TIRAGE (le natif `Add`e dans l'ordre des picks). Un consommateur qui
    mirror un `OrderBy` natif re-trie APRÈS (ex. `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
    trie la liste résolue quand `Count > 1`) — ce tri vit chez l'appelant, pas ici.

    ⚠ **`items` DOIT arriver dans l'ORDRE SOURCE** (R28-1). `candidates` natif =
    `source.Select(entities).ToList()` : le sélecteur est évalué et sa liste consommée TELLE QUELLE,
    aucun tri n'intervient avant la boucle de tirage. Un appelant qui id-trie son pool AVANT
    `_pick_randomly_n` change donc QUI est piqué dès que `len(pool) > n` (la CONSO, elle, reste juste).
    L'ordre source des sélecteurs d'occupation est celui des TUILES (`_tile_enum_rank`, `dsl/base.py`) :
    `AdjacentTiles` = liste d'adjacence stockée (`Board.neighbours_native`), `SurroundingTiles` = triple
    boucle CUBE d'`IterateSurroundingTiles`.

    `AddForcedTargetsAndUpdateCandidates` (R28-3) — **NON PORTÉ, et c'est un verdict, pas un trou**.
    `PickRandomAmountSelector$$Select` appelle bien `IdunBattle.DSL.APickSelector$$AddForcedTargetsAndUpdateCandidates`
    avant sa boucle (le champ `+0x38` qui la gate vaut `false` à tous les call-sites : `DSLSelectors$$PickRandomly`
    propage le 5e argument, et les `ExecuteBehaviour` lus passent `(…, 0, 0x7fffffff, false)`). Mais elle
    PRÉ-REMPLIT `result` depuis `IdunBattle.Entities.UnitExtensions$$GetOnlyTargets(entities.Caster)` — la
    liste de cibles FORCÉES du CASTER — et cette liste n'a **qu'un seul écrivain natif** :
    `IdunBattleLogic.Entities.Abilities.Active.Loki.InstinctiveBehaviour_UpdateTargetAbility$$CreateBehaviour`
    (unique XREF de `DSLBehaviors$$AddForcedAttackTarget`). Ses 23 porteurs = le trait `InstinctiveBehaviour`
    (2021), tous des npc/summons Tyranides SANS active ability — donc aucun d'eux n'atteint jamais un
    `PickRandomly`. Sur tout porteur confrontable la liste est VIDE, la fonction retourne immédiatement,
    `i = result.Count = 0` et **aucun tirage n'est consommé** : porter la branche serait un no-op
    spéculatif. À rouvrir SI un jour un porteur d'`InstinctiveBehaviour` gagne une ability à PickRandomly.

    `state.rng` None (replay effet-seul, aucun flux à mirrorer) -> `pool[:n]` déterministe (mode
    `allow_repeat` : cycle sur le pool, meme cardinal rendu)."""
    pool = list(items)
    n = max(0, int(n))
    if state.rng is None:
        if allow_repeat and pool:
            return [pool[i % len(pool)] for i in range(n)]
        return pool[:n]
    out: list = []
    while len(out) < n and pool:                        # `while (i < amount) { if (Count < 1) break; … }`
        idx = state.rng.next_internal(0, len(pool))     # NextInternal(0, candidates.Count)
        pick = pool[idx]
        out.append(pick)
        if not allow_repeat:
            pool.pop(idx)                               # `!allowRepeat -> RemoveAt(idx)`
        elif out.count(pick) == int(max_repeats):       # `allowRepeat` : retire au maxRepeats-ieme
            pool.pop(idx)
    return out


def _splash_ability_behaviour(state: "State", caster_id: int, target_id: int, ability_id: str,
                              profile: str, ranged: bool, splash_set: list,
                              is_attack_damage_op: bool = True) -> dict:
    """Mécanique partagée B1 (mirror `CrushingClaws` SANS var-séparées) : 1 attaque MAIN sur `target`
    (hits=`nrOfHits`) + 1 volet SPLASH sur `splash_set`, PARTAGEANT la MÊME plage `minDmg/maxDmg` — seul le
    nb de hits diffère (splash = `nrOfHits_2`). ⚠ le splash réutilise minDmg/maxDmg/pierce (PAS
    minDmg_2/maxDmg_2 : ce pattern var-séparées = CrushingClaws only). Chaque volet = `execute_ability_attack`.

    RÉFÉRENCE IMPÉRATIVE des tests de bit-exactness des arbres DSL splash (PlasmaGrenade/ScythingTalons tests
    comparent leur arbre `AttackWithAttackDamage(multi=True)` à ce retour) : plus AUCUN appelant PRODUCTION
    (tous les splash migrés en arbres DSL, Fragstorm compris slice-13), conservé pour l'oracle des tests.
    `is_attack_damage_op` = famille de factory native (rngcrit-1202, cf. behaviours/combat.py) — l'oracle doit
    passer la MÊME famille que l'arbre DSL comparé (PlasmaGrenade = "ability" -> False)."""
    bmin, bmax, pierce, hits = ability_attack_params(state, caster_id, ability_id, profile, ranged=ranged)
    main = AttackDamageOperation.execute_ability_attack(state, caster_id, target_id, bmin, bmax, pierce, hits,
                                                        damage_profile=profile, is_melee=not ranged,
                                                        is_attack_damage_op=is_attack_damage_op)
    # splash : MÊME plage (minDmg/maxDmg/pierce), seule la constante de hits change (nrOfHits_2).
    _bmin2, _bmax2, _pierce2, hits2 = ability_attack_params(
        state, caster_id, ability_id, profile, ranged=ranged, hits_key="nrOfHits_2")
    splash: list[dict] = []
    for sid in splash_set:
        satk = AttackDamageOperation.execute_ability_attack(state, caster_id, sid, bmin, bmax, pierce, hits2,
                                                            damage_profile=profile, is_melee=not ranged,
                                                            is_attack_damage_op=is_attack_damage_op)
        splash.append({"target": sid, "attack": satk})
    return {"main_attack": main, "splash": splash, "hits_main": hits, "hits_splash": hits2}


class CrushingClawsAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.CrushingClawsAbility$$ExecuteBehaviour (id 1105, tyranTyrantGuard).

    Séquence native (`&`/`+` = compositions de behaviour) :
        AttackWithAttackDamage(actor, target, MinMaxDamage, profile=Piercing, nrOfHits=const 0x2f=2)  # principale
      & AddBondEffect(0x1b=27 Taunted, TurnsFromRounds(1))         # Taunt cible (COMPOSITE → 25/26/1237)
      & AddEffect(0x429=1065 Pinned, target)                       # « Suppressed » cible (DefaultRounds=1)
      & Foreach(splash = AdjacentEnemies(actor) & (AdjacentFriends(target) − target), UnitsWithoutTrait(0xd)):
            PushUnit(actor, s)                                     # recul 1 hex  [slice-21a : PORTE]
          + If(alive) AddEffect(0x429 Pinned, s)                   # « Suppressed » splash
          + If(alive) AttackWithAttackDamage(actor, s, MinMaxDamage2, profile2=Physical, nrOfHits=const 0x32=1)

    Matérialise (vecteur ATTAQUE, tranche EFFETS) : la CIBLE porte Taunted(27)+enfants 25/26/1237 +
    Pinned(1065) ; chaque unité splash subit 1× Physique + Pinned(1065). Le **push** du splash (recul 1 hex
    à l'opposé du caster) est PORTÉ (slice-21a) ; `KillDeadUnits`/`MoveUnit(caster)` = tranche DEPLACEMENT
    différée (cf. ThunderousAssault).

    #149 slice-4 : `execute_behaviour` DÉLÈGUE à `crushing_claws_tree()` (mirror 1:1 du décompilé +
    lambda `<ExecuteBehaviour>b__0`). L'exclusion **trait 0xd** du splash (`UnitsWithoutTrait(Object=13)`)
    est désormais PORTÉE (0xd mappé `UnitTrait.Object` #158) — plus fidèle que l'ancien impératif qui la
    skippait. Splash gated `If(IsAlive(s))` (pin + attaque). Bit-exact BY CONSTRUCTION."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.CrushingClaws)  # 1105
    ABILITY_ID = "CrushingClaws"

    # GATE DE CIBLE (#115). FORME **PRESET STATIQUE COPIE, AUCUN `TargetingOptions..ctor`** :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.CrushingClawsAbility$$.ctor` recopie les 0x40
    # octets du champ STATIQUE de `TargetingOptions` a l'offset RELATIF `+0x40` du bloc
    # `<class>+0xb8`, puis `AActiveAbility..ctor(this, &opts, 0, 0)` (3e arg = 0 =
    # `AbilityAttackType.DirectTargetAttack`). Aucun litteral de masque n'est visible dans le ctor.
    # Le contenu du preset est celui qu'ecrit `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    #     <preset>+0x00 isSelfCasting    = 0
    #     <preset>+0x08 range            <- copie du `TargetingRange` statique `+0x30`
    #                                       (`TargetingRange$$.cctor` : onlyAdjacent = `RangedBool.True`,
    #                                        overrideRange = Nullable(1)) = RANGE_ADJACENT
    #     <preset>+0x20 forceMeleeTarget = 1 = `RangedBool.False`
    #     <preset>+0x28 rules            = 0x4000
    #     <preset>+0x30/+0x38            = 0 (ecrases par `AActiveAbility$$.ctor`)
    # Decomposition EXHAUSTIVE du masque (`IdunBattle.Core.Services.TargetingRule`) :
    #     bit 14  0x4000  TargetIsEnemy  -> PORTE (`UnitsCanAttackEachOther`)
    #     0x4000 = 0x4000 : somme exacte, aucun bit residuel.
    # C'est le MEME preset `+0x40` que `ThunderousAssault` (1043, case-246) -- mais 1043 passe par la
    # surcharge PRESET+FLAGS et OR-e `CasterCanMove` par-dessus (0x10004000). Ici : aucun flag.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        crushing_claws_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]   # cibles splash != cible principale
        return {"ability": "CrushingClaws", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


class PlasmaGrenadeAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaGrenadeAbility$$ExecuteBehaviour` (id 1098, eldarSmnGuardian).

    Séquence native (`+` = op_Addition, plain `Execute`) :
        AttackWithAttackDamage(actor, target, RandomAmount(minDmg/maxDmg), Plasma, nrOfHits=0x2f)   # principale
      + AttackWithAttackDamage(actor, Enemies(caster, AdjacentUnits(target,1)), MÊME RandomAmount,
                                Plasma, nrOfHits_2=0x32)                                              # splash multi-cible
    Splash = ennemis adjacents (hex) à la CIBLE, plage de dégât PARTAGÉE (seul le nb de hits change).
    Ranged (range 2).

    #149 slice-6 : `execute_behaviour` DÉLÈGUE à `plasma_grenade_tree()` (mirror 1:1 du décompilé). Le
    SPLASH est un SEUL `AttackWithAttackDamage(selecteur-multi)` (== le natif, PAS un `Foreach`) porté via
    le mode `multi=True` de la feuille (`AttackBehaviour.Execute` résout la liste + `OrderBy` par id).
    Bit-exact BY CONSTRUCTION vs l'ancien impératif (mêmes bornes/hits/profil, splash trié par
    id, même `state.rng`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.PlasmaGrenade)  # 1098
    ABILITY_ID = "PlasmaGrenade"

    # GATE DE CIBLE (#115). FORME **PRESET + FLAGS** :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.PlasmaGrenadeAbility$$.ctor` recopie le preset
    # STATIQUE de `TargetingOptions` a l'offset RELATIF `+0x140` du bloc `<class>+0xb8`, puis :
    #     TargetingOptions..ctor(&opts, &preset, 0x2000000, 0)   # surcharge (dst, preset, flags)
    #     AActiveAbility..ctor(this, &opts, 0, 0)                # 3e arg = 0 = DirectTargetAttack
    # Cette surcharge recopie le preset champ par champ SAUF `Rules`, qu'elle **COMBINE** --
    # decompile VERBATIM : `*(ulonglong *)(param_1 + 0x28) = param_3 | *(param_2 + 0x28);`
    # => masque EFFECTIF = `flags | preset.Rules`, ni l'un ni l'autre seul.
    # Preset `+0x140` lu dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    #     <preset>+0x00 isSelfCasting    = 0
    #     <preset>+0x08 range            <- copie du `TargetingRange` statique `+0x18`
    #                                       (`useRangeFromConfig = true`) = RANGE_FROM_CONFIG
    #                                       -> `AActiveAbility$$SetConfigValuesInTargetingOptions`
    #                                          pose `overrideRange = constants.range` = 2
    #     <preset>+0x20 forceMeleeTarget = 0 = `RangedBool.True`  <- DIFFERE de Fragstorm (voir plus bas)
    #     <preset>+0x28 rules            = 0x4002
    # Decomposition EXHAUSTIVE de `0x2000000 | 0x4002` = **0x2004002** :
    #     bit  1  0x2         TargetMatchesDynamicRule       -> point d'extension ; aucune surcharge
    #                                                           de `get_dynamic_invalid_target_reason`
    #                                                           ici -> defaut 0 (permissif)
    #     bit 14  0x4000      TargetIsEnemy                  -> PORTE (`UnitsCanAttackEachOther`)
    #     bit 25  0x2000000   AllowObscuredTargetByElevation -> PERMISSIF (leve la ligne de vue par
    #                                                           elevation ; la LOS n'est pas portee)
    #     0x2 + 0x4000 + 0x2000000 = 0x2004002 : somme exacte, aucun bit residuel.
    # `forceMeleeTarget = RangedBool.True` ARME le clamp de melee de `TargetingQuery$$GetRange` :
    # si `AttackQuery$$ShouldApplyRangedInMelee` est vrai (un ennemi non-Steppable au contact du
    # caster), la portee tombe a `min(1, 2)` et `onlyAdjacent` passe a vrai. C'est le SEUL champ qui
    # separe ce preset de celui de Fragstorm (`+0x180`).
    # CONFRONTE LIVE (#243) -- le marqueur « pose sur RE seule » de #248 est LEVE. Porteur
    # `eldarSmnGuardian` amene par catalogue injecte + trait `Summon` retire (recette case-245). Ce
    # retrait n'est PAS un contournement de gate : le trait `Summon` (`UnitTrait` 2) rend l'unite
    # AUTOMATIQUE (`IdunBattle.Entities.UnitExtensions$$IsAutomatic`), le moteur la joue lui-meme
    # (`IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute`), elle consomme sa charge, et
    # `CanStillBeUsed` retombe a false par l'USAGE. Le retirer rend l'unite CONTROLABLE. cf. #250.
    # 14/14 lignes d'accord natif/port sur DEUX montages, seuil encadre des DEUX cotes (d=2 accepte,
    # d=3/5/6 -> `TargetIsInRange`) et CLAMP EXERCE : avec un ennemi au contact, la cible a d=2
    # bascule de `0x0` a `0x8000000`, et le contrefactuel `fmtFlip` faux-ACCEPTE exactement cette
    # ligne. cf. `probe_243_splash_range_clamp.py`, garde `test_splash_range_clamp_live.py`.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy | TR.AllowObscuredTargetByElevation,
        self_cast=False, range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        plasma_grenade_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]      # cibles splash != cible principale
        return {"ability": "PlasmaGrenade", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


class StikkbombAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.StikkbombAbility$$ExecuteBehaviour (id 1051, Ork Boy — orksNpc2OrkBoy/orksOrkBoys).

    #149 slice-12 : la behaviour EST l'**arbre DSL** `stikkbomb_tree()` (mirror 1:1 du décompilé IdunBattleLogic.Entities.Abilities.Active.Loki.StikkbombAbility$$ExecuteBehaviour :
    `Execute(AtomicGroup(op_Addition(main, splash)))` — cf. `stikkbomb_tree`), en remplacement du portage
    impératif (`_splash_ability_behaviour`+`_adjacent_enemies_of`).

    ⚠ FIDÉLITÉ CORRIGÉE (#213, RÉSOLUE) : le splash natif = `AdjacentUnits(target,1,3)` BRUT (SANS wrapper
    `Enemies(...)`) → **FRIENDLY-FIRE** = TOUTES les unités adjacentes à la cible (alliés du caster INCLUS),
    hors cible. L'ancien port (`_adjacent_enemies_of` = enemies-only) était ERRONÉ. Preuve DOUBLE et concordante :
    (1) décompile — contraste PlasmaGrenade `Enemies(caster, AdjacentUnits(...))` et Fragstorm
    `AdjacentTiles − Tiles(Friends(...))`, avec `AdjacentUnits`/`Units`/`Enemies` décompilés (le 1/3 = flags
    `UnitsOnTilesSelector`, pas un masque d'équipe) ; (2) i2 — Stikkbomb « units in hexes adjacent to the target »
    vs « enemy units »/« excluding friendly hexes » des 3 autres splash. Le sélecteur porté `Alive(AdjacentUnits(
    TargetTile()))` n'applique donc AUCUN filtre d'équipe. Plage main/splash PARTAGÉE (nrOfHits=2 / nrOfHits_2=1),
    profil Blast, ranged (range 2, Indirect Fire)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Stikkbomb)  # 1051
    ABILITY_ID = "Stikkbomb"

    # GATE DE CIBLE (#115). FORME **PRESET + FLAGS**, preset `+0x140` + flags `0x2000000` --
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.StikkbombAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, &<preset +0x140>, 0x2000000, 0)
    #     AActiveAbility..ctor(this, &opts, 0, 0)                # 0 = DirectTargetAttack
    # STRICTEMENT le meme preset et les memes flags que `PlasmaGrenade` (1098) -- verifie ctor par
    # ctor, PAS deduit de la voisine : dans ce meme module `Fragstorm` (1078) prend le preset `+0x180`,
    # qui ne differe que par `forceMeleeTarget`, et `ScythingTalons`/`CrushingClaws` le preset `+0x40`.
    #     <preset +0x140>+0x00 isSelfCasting    = 0
    #     <preset +0x140>+0x08 range            <- `TargetingRange` statique `+0x18` = RANGE_FROM_CONFIG
    #                                              -> `overrideRange = constants.range` = 2
    #     <preset +0x140>+0x20 forceMeleeTarget = 0 = `RangedBool.True` (clamp melee ARME)
    #     <preset +0x140>+0x28 rules            = 0x4002
    # Masque EFFECTIF `0x2000000 | 0x4002` = **0x2004002**, decompose EXHAUSTIVEMENT :
    #     bit  1  0x2         TargetMatchesDynamicRule       -> defaut 0 (aucune surcharge) = permissif
    #     bit 14  0x4000      TargetIsEnemy                  -> PORTE
    #     bit 25  0x2000000   AllowObscuredTargetByElevation -> PERMISSIF (LOS non portee)
    #     0x2 + 0x4000 + 0x2000000 = 0x2004002 : somme exacte, aucun bit residuel.
    # CONFRONTE LIVE (#243) -- le marqueur « pose sur RE seule » de #248 est LEVE. Porteur
    # `orksOrkBoys` amene par catalogue injecte + trait `Summon` retire (recette case-245).
    # 14/14 lignes d'accord natif/port sur DEUX montages, seuil encadre des DEUX cotes (d=2 accepte,
    # d=3/5/6 -> `TargetIsInRange`) et CLAMP EXERCE : avec un ennemi au contact, la cible a d=2
    # bascule de `0x0` a `0x8000000` -- exactement l'inverse de Fragstorm (1078), mesuree dans le
    # MEME runner. cf. `probe_243_splash_range_clamp.py`, garde `test_splash_range_clamp_live.py`.
    # NOTE : `TargetIsEnemy` gate la CIBLE DESIGNEE du message, pas le splash. Le friendly-fire du
    # splash (#213 : `AdjacentUnits(TargetTile())` BRUT, allies inclus) reste entier -- ce sont deux
    # etages distincts (gate de cast vs selecteur de behaviour).
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy | TR.AllowObscuredTargetByElevation,
        self_cast=False, range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # behaviour = arbre DSL (feuille AttackWithAttackDamage x2, splash multi=True friendly-fire) ; émet les
        # MÊMES Operations (`AttackDamageOperation.execute_ability_attack`) -> même mutation, diag main/splash.
        ectx = ExecutionContext(state=state, rng=state.rng)
        stikkbomb_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]      # cibles splash != cible principale
        return {"ability": "Stikkbomb", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


class FragstormAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormAbility$$ExecuteBehaviour (id 1078, templSmnAggressor).

    #149 slice-13 : la behaviour EST l'**arbre DSL** `fragstorm_tree()` (mirror 1:1 du décompilé IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormAbility$$ExecuteBehaviour :
    `ExecuteAtomic(op_BitwiseAnd(main, splash))` — cf. `fragstorm_tree`), en remplacement du portage impératif
    (`_pick_randomly_n(_adjacent_enemies_of(...))` + `_splash_ability_behaviour`, désormais supprimé).

    Splash natif = `PickRandomly(AdjacentTiles(target) − Tiles(Friends(caster)), nrOfTargets=4)` = jusqu'à 4
    HEXES aléatoires adjacents à la cible, EXCLUANT les tuiles à ami-du-caster (i2 « up to 4 random hexes
    adjacent to the target, excluding hexes with friendly units »). CONTRASTE Stikkbomb (`AdjacentUnits` BRUT =
    friendly-fire) : Fragstorm SOUSTRAIT explicitement les tuiles amies → enemies-only. Porté =
    `Alive(Sub(AdjacentUnits(TargetTile()), AdjacentFriends(TargetTile())))` (occupants non-amis) + `pick_n=4`
    folde le PickRandomly dans la feuille (tire 4 via `state.rng`, == l'impératif → bit-exact). Plage main/splash
    PARTAGÉE (nrOfHits=4 / nrOfHits_2=2), profil Blast, ranged (range 2). ⚠ GAP #215 (RNG-exact) : le natif tire
    des HEXES (vides incluses = coup gaspillé) et l'ordre/coût du tirage ne sont pas calés → divergence possible
    quand >4 tuiles adjacentes non-amies."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Fragstorm)  # 1078
    ABILITY_ID = "Fragstorm"

    # GATE DE CIBLE (#115). FORME **PRESET + FLAGS** --
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, &<preset +0x180>, 0x2000000, 0)
    #     AActiveAbility..ctor(this, &opts, 0, 0)                # 0 = DirectTargetAttack
    # ⚠ LE PRESET N'EST PAS CELUI DE SES VOISINES. Stikkbomb (1051) et PlasmaGrenade (1098) prennent
    # `+0x140`, Fragstorm prend `+0x180`. Les deux blocs de `TargetingOptions$$.cctor` sont identiques
    # SAUF le champ `+0x20` :
    #     <preset +0x140>+0x20 forceMeleeTarget = 0 = `RangedBool.True`
    #     <preset +0x180>+0x20 forceMeleeTarget = 1 = `RangedBool.False`   <- ICI
    # Recopier le masque de la voisine aurait donc donne le bon `rules` et le MAUVAIS volet portee :
    # `RangedBool.False` DESARME le clamp de melee de `TargetingQuery$$GetRange`, donc Fragstorm garde
    # sa portee 2 meme avec un ennemi au contact, la ou Stikkbomb/PlasmaGrenade retombent a 1.
    #     <preset +0x180>+0x00 isSelfCasting    = 0
    #     <preset +0x180>+0x08 range            <- `TargetingRange` statique `+0x18` = RANGE_FROM_CONFIG
    #                                              -> `overrideRange = constants.range` = 2
    #     <preset +0x180>+0x28 rules            = 0x4002
    # Masque EFFECTIF `0x2000000 | 0x4002` = **0x2004002**, decompose EXHAUSTIVEMENT :
    #     bit  1  0x2         TargetMatchesDynamicRule       -> defaut 0 (aucune surcharge) = permissif
    #     bit 14  0x4000      TargetIsEnemy                  -> PORTE
    #     bit 25  0x2000000   AllowObscuredTargetByElevation -> PERMISSIF (LOS non portee)
    #     0x2 + 0x4000 + 0x2000000 = 0x2004002 : somme exacte, aucun bit residuel.
    # CONFRONTE LIVE (#243) -- le marqueur « pose sur RE seule » de #248 est LEVE, et c'est LE cas
    # qui paie la lecture preset-par-preset. Porteur `templSmnAggressor` amene par catalogue injecte
    # + trait `Summon` retire (recette case-245). 14/14 lignes d'accord natif/port sur DEUX montages,
    # seuil encadre des DEUX cotes (d=2 accepte, d=3/5/6 -> `TargetIsInRange`), et surtout : avec un
    # ennemi AU CONTACT, la cible a d=2 reste ACCEPTEE (`0x0`), la ou 1051/1098 -- mesurees dans le
    # MEME runner, meme geometrie -- basculent en `0x8000000`. Le contrefactuel `fmtFlip` faux-REFUSE
    # exactement cette ligne. cf. `probe_243_splash_range_clamp.py`, garde
    # `test_splash_range_clamp_live.py`.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy | TR.AllowObscuredTargetByElevation,
        self_cast=False, range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        # behaviour = arbre DSL (main + splash multi=True/pick_n=4) ; émet les MÊMES Operations
        # (`AttackDamageOperation.execute_ability_attack`) -> même mutation, diag main/splash.
        ectx = ExecutionContext(state=state, rng=state.rng)
        fragstorm_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]      # cibles splash != cible principale
        return {"ability": "Fragstorm", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


class ScythingTalonsAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ScythingTalonsAbility$$ExecuteBehaviour` (id 1065, tyranSmnWarrior).

    Séquence native (`ExecuteAtomic`, `op_BitwiseAnd`) :
        AttackWithAttackDamage(actor, target, MinMaxDamage, Bio, hits=condHits1=0x2f=3)          # principale
      & AttackWithAttackDamage(actor, splash-MULTI, MÊME MinMaxDamage, Bio, hits=condHits2=0x32=2)  # splash
    Splash = `Unique(Enemies(caster, AdjacentUnits(casterTile,1) & AdjacentUnits(targetTile,1), 3))` = ennemis
    du caster adjacents à la FOIS au caster ET à la cible (`_adjacent_to_both`), plage PARTAGÉE. Melee (Bio).

    #149 slice-8 : `execute_behaviour` DÉLÈGUE à `scything_talons_tree()` (mirror 1:1 du décompilé). Le SPLASH
    est un SEUL `AttackWithAttackDamage(selecteur-multi)` (== le natif, PAS un `Foreach` -> DIFFERE de
    CrushingClaws) porté via le mode `multi=True` de la feuille (résout la liste + `OrderBy` par id). Bit-exact
    BY CONSTRUCTION vs l'ancien impératif (`_adjacent_to_both` — mêmes bornes/hits/
    profil, splash trié par id, même `state.rng`). `_splash_ability_behaviour` a été retiré (slice-13, dernier
    appelant Fragstorm migré).

    ⚠ HITS CONDITIONNELS (GAP, tâche #211, HORS migration) : `condHits = ConditionalAmount(HasTrait(target,
    UnitTrait.Summon=2), nrOfHits×2, nrOfHits)` — les hits DOUBLENT (3→6 main, 2→4 splash) si la CIBLE est un
    SUMMON. On porte les hits de BASE (3/2, jamais de sur-compte, == l'impératif) ; le doublement =
    behaviour-changing (noeud `ConditionalAmount` + feuille hits-formule + validation live)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ScythingTalons)  # 1065
    ABILITY_ID = "ScythingTalons"

    # GATE DE CIBLE (#115). FORME **PRESET STATIQUE COPIE, AUCUN `TargetingOptions..ctor`** :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.ScythingTalonsAbility$$.ctor` recopie les 0x40
    # octets du preset `+0x40` du bloc `<class>+0xb8`, puis
    # `AActiveAbility..ctor(this, &opts, 0, 0)` (0 = `AbilityAttackType.DirectTargetAttack`).
    # Contenu du preset (`IdunBattle.Core.Services.TargetingOptions$$.cctor`) :
    #     <preset>+0x00 isSelfCasting    = 0
    #     <preset>+0x08 range            <- `TargetingRange` statique `+0x30` = RANGE_ADJACENT
    #                                       (onlyAdjacent = `RangedBool.True`, overrideRange = 1)
    #     <preset>+0x20 forceMeleeTarget = 1 = `RangedBool.False`
    #     <preset>+0x28 rules            = 0x4000
    # Decomposition EXHAUSTIVE : bit 14 `0x4000 TargetIsEnemy` seul -- 0x4000 = 0x4000, aucun residu.
    # `onlyAdjacent` fait prendre au filtre statique la branche `battleQuery.AreEntitiesAdjacent`
    # (et non un `dist <= N`) : la cible doit etre AU CONTACT. Coherent avec le kit (melee Bio, splash
    # = ennemis adjacents A LA FOIS au caster ET a la cible).
    # CONFRONTE LIVE (#250) sur le PORTEUR REEL `tyranSmnWarrior` -- le marqueur « valide par
    # IDENTITE DE PRESET avec 1105 » est LEVE. Le porteur est DEJA au catalogue `data/seed-bc.json`
    # (`VisualId` `tyranNpc4Warrior`) : aucun catalogue injecte, seuls `Health` 0 -> 5000 et le
    # retrait du trait `Summon` (qui rend l'unite AUTOMATIQUE, cf. #250) amenagent son entree.
    # 6/6 lignes d'accord natif/port, seuil de portee encadre des DEUX cotes (ENNEMI d=1 -> `0x0`,
    # ENNEMI d=2 -> `0x8000000 TargetIsInRange`), ALLIE d=1 et le CASTER -> `0x4000 TargetIsEnemy`.
    # Contrefactuels (lignes divergentes / 6) : `TARGETING_OPTIONS=None` 5, `rules=0` 2,
    # `range=None` 3 -- chaque champ PORTE. `fmtFlip` 0 : `force_melee_target` est INERTE ici, et
    # c'est LU au decompile, pas suppose -- `RANGE_ADJACENT` pose deja `overrideRange = 1`, donc le
    # clamp `v = Math.Min(1, v)` de `IdunBattle.Core.Services.TargetingQuery$$GetRange` est
    # idempotent. cf. `probe_250_summon_automatic.py --only cast`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False,
                                         range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        scything_talons_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]      # cibles splash != cible principale
        return {"ability": "ScythingTalons", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


class GauntletsOfUltramarAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$ExecuteBehaviour` (id 1000, ultraCalgar).

    AoE SELF-CAST a DEUX BANDES DE PORTEE (ancre sur le CASTER, PAS `Target()`) : la bande ADJACENTE frappe
    tous les ennemis a dist 1 (`Unique(Enemies(AdjacentTiles(caster)))`, 2 coups = nrOfHits 0x2f + nrOfHits_2
    0x32) ; la bande SURROUNDING frappe les ennemis a dist EXACTEMENT 2, NON obscurcis (`Unobscured(
    SurroundingEnemies(caster,r=2) - Adjacent)`, 1 coup = nrOfHits_2 0x32). Meme plage `MinMaxDamage` +
    profil Bolter pour les deux bandes.

    La behaviour EST l'arbre DSL `gauntlets_of_ultramar_tree()` (mirror 1:1 du decompile IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$ExecuteBehaviour :
    `ExecuteAtomic(op_BitwiseAnd(bandeAdj, bandeSurr), 0x1d)`). Les deux bandes = `AttackWithAttackDamage(
    multi=True)` (`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` resout la liste + `OrderBy` par id) -> memes Operations
    (`AttackDamageOperation.execute_ability_attack`) que l'imperatif -> bit-exact BY CONSTRUCTION (memes
    bornes/hits/profil, cibles triees par id, meme `state.rng`). La face PREDICTION (arc NC) est portee a part
    (`playbook/noncomparable/gauntlets_of_ultramar.py`, case-49/#50) ; ici = la face COMBAT (execute) seule,
    alignee sur la MEME geometrie Unobscured/surrounding validee live.

    `target_id` (cible que l'IA a choisie pour le message) est IGNORE pour le degat : Gauntlets frappe TOUT
    l'entourage du caster, pas cette cible (l'arbre n'utilise ni `Target()` ni `TargetTile()`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.GauntletsOfUltramar)  # 1000
    ABILITY_ID = "GauntletsOfUltramar"

    # GATE DE CIBLE (#115). FORME **FACTORY NOMMEE** -- une QUATRIEME forme, distincte des trois
    # documentees (flags directs / preset+flags / preset statique copie).
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$.ctor` :
    #     TargetingOptions..SelfCastIfEnemyInCustomRangeOptions(&opts, 2)   # range = 2
    #     AActiveAbility..ctor(this, &opts, 2, 0)                           # 2 = AbilityAttackType.Others
    # C'est le SEUL appelant natif de cette factory (`list_xrefs` : 1 UNCONDITIONAL_CALL) ; les trois
    # autres porteurs du meme profil (ResurrectionOrb 1009, Chronometron 1226, AncestralFortune 1207)
    # l'ont recue INLINEE par IL2CPP. Ici elle est lisible telle quelle --
    # `IdunBattle.Core.Services.TargetingOptions$$SelfCastIfEnemyInCustomRangeOptions(int range)`
    # ecrit, champ par champ :
    #     +0x00 isSelfCasting    = 1           (`*param_1 = 1`)               -> self_cast=True
    #     +0x08 range            = `TargetingRange` INLINE : onlyAdjacent = 1 (`RangedBool.False`),
    #                              useRangeFromConfig = false, useWholeBoard = false,
    #                              overrideRange = `Nullable<int>(range)` = Nullable(2),
    #                              overrideRangeFunc = null   == `TargetingRange$$CustomRange(2)`
    #     +0x20 forceMeleeTarget = 1 = `RangedBool.False`
    #     +0x28 rules            = 0x4000
    #     +0x30/+0x38            = 0 (ecrases par `AActiveAbility$$.ctor`)
    # Decomposition EXHAUSTIVE : bit 14 `0x4000 TargetIsEnemy` seul -- 0x4000 = 0x4000, aucun residu.
    # SEMANTIQUE : l'ability est SELF-CASTEE (l'arbre est ancre sur le CASTER, il n'utilise ni
    # `Target()` ni `TargetTile()`), et `TargetIsEnemy` + `range=2` servent au predicat « existe-t-il
    # au moins un ennemi a portee 2 ? » -- c'est exactement ce que dit le nom de la factory. Le byte
    # `+0x00` aiguille l'overload 5 arguments de `TargetingQuery$$GetInvalidTargetReason` vers
    # `GetCasterNotAddedReason` (non porte -> 0) des que la cible EST le caster ; une cible TIERCE,
    # elle, traverse le filtre statique et subit `TargetIsEnemy` + le volet portee.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy, self_cast=True,
                                         range=custom_range(2),
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # behaviour = arbre DSL (2 bandes AttackWithAttackDamage multi=True) ; target_id inutilise (AoE
        # ancree caster). Emet les MEMES Operations (execute_ability_attack) -> meme mutation, diag par bande.
        ectx = ExecutionContext(state=state, rng=state.rng)
        gauntlets_of_ultramar_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [{"target": p["target"], "attack": p["attack"]}
                for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": "GauntletsOfUltramar", "caster": caster_id, "target": target_id,
                "attacks": atks, "dsl": True}

