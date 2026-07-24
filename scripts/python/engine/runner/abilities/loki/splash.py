"""Abilities actives de SPLASH/AoE du namespace natif `Abilities.Active.Loki.*` — attaque principale +
volet splash multi-cible : CrushingClaws, PlasmaGrenade, Stikkbomb, Fragstorm, ScythingTalons.
+ les helpers de ciblage splash partages (`_adjacent_to_both`, `_adjacent_enemies_of`,
`_splash_ability_behaviour` = oracles imperatifs des tests ; `_pick_randomly_n` = PickRandomly, consomme
par `../behaviours.py` et `../genestealer.py`). Cf. `loki/__init__.py`."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ..base import ActiveAbility, ability_attack_params
from ...operations.damage import AttackDamageOperation
from ...components import OwnerComponent, PositionComponent, UnitComponent
from ....entities.effect_type import EffectType
from ....entities.active_ability_type import ActiveAbilityType
from ....dsl.base import Const
from ....dsl.effects import ExecutionContext
from ....entities.behaviours import Foreach, If, AtomicGroup, op_add, op_and
from ....entities.selectors import (Subject, Caster, Target, CasterTile, TargetTile, AdjacentEnemies,
                                    AdjacentUnits, And, Sub, UnitsWithoutTrait, AdjacentFriends, Alive,
                                    SurroundingEnemies, Unobscured, Unique)
from ....entities.triggers import IsAlive
from ....entities.traits.unit_trait import UnitTrait
from ..behaviours import (AttackWithAttackDamage, AddEffect, AddBondEffect, PushUnit,
                          entities_from_state)

if TYPE_CHECKING:
    from ...state import State

TAUNTED = int(EffectType.Taunted_OnlySpecificTargets)   # 27 — COMPOSITE -> 25/26/1237 ; bond (CrushingClaws)
PINNED = int(EffectType.Pinned)                         # 1065 — UI « Suppressed » — stat-mod Movement


def crushing_claws_splash_tree() -> "op_add":
    """Corps `Func<entities,behaviour>` du `Foreach` splash = lambda `<ExecuteBehaviour>b__0 @1811e3c60`
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
    """Arbre de `CrushingClawsAbility.ExecuteBehaviour @1811cd5e0` (id 1105, tyranTyrantGuard — MIRROR du
    DECOMPILE + du lambda `<ExecuteBehaviour>b__0 @1811e3c60`) :
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
    taunt = AddBondEffect(TAUNTED, "Taunted_OnlySpecificTargets", Caster(), tgt, 1)   # AddBondEffect(0x1b)
    pin = AddEffect(PINNED, "Pinned", tgt, None)                                       # AddEffect(0x429), duree DEFAUT
    main = AttackWithAttackDamage(tgt, "CrushingClaws", "Piercing", is_melee=True)    # MinMaxDamage/Piercing/0x2f=2
    splash = UnitsWithoutTrait(
        And(AdjacentEnemies(CasterTile(), Const(1)), AdjacentEnemies(TargetTile(), Const(1))),
        int(UnitTrait.Object))                                                          # UnitsWithoutTrait(0xd)
    return AtomicGroup(op_add(
        op_add(op_add(taunt, pin), main),                                             # ((taunt+pin)+main)
        Foreach(splash, crushing_claws_splash_tree())))                               # + foreach(splash)


def plasma_grenade_tree():
    """Arbre de `PlasmaGrenadeAbility.ExecuteBehaviour @1811f99e0` (id 1098, eldarSmnGuardian — MIRROR du
    DECOMPILE) :
        Execute( op_Addition(
            AttackWithAttackDamage(caster, target, RandomAmount(minDmg=var0xc, maxDmg=var0xd), Plasma,
                                    nrOfHits=GetNumberConstant(0x2f)),                        # [MAIN]
            AttackWithAttackDamage(caster, Enemies(caster, AdjacentUnits(target,1)), RandomAmount(MEME),
                                    Plasma, nrOfHits_2=GetNumberConstant(0x32)) ) )           # [SPLASH]
    Port : `op_add(main, splash)`. Le SPLASH natif passe un SELECTEUR MULTI-cible directement a UN
    `AttackWithAttackDamage` (PAS un `Foreach`) -> `AttackBehaviour.Execute @180fb91a0` resout la liste,
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
    # rngcrit-1202 : la factory native de PlasmaGrenade est `AttackWithABILITYDamage @180de9c90`
    # (XREFS @1811f9b9a/@1811f9c0e -> @180de9c90 -> core @180de9e50 = AbilityDamageBehaviour), PAS
    # AttackWithAttackDamage comme l'ancien commentaire le disait -> AbilityDamageOperation = 1 tirage/
    # coup (AUCUN resolve slot-8 gaspille) -> native_factory="ability".
    main = AttackWithAttackDamage(tgt, "PlasmaGrenade", "Plasma", is_melee=False,
                                  native_factory="ability")                             # RandomAmount/Plasma/0x2f
    splash = AttackWithAttackDamage(Alive(AdjacentEnemies(TargetTile())), "PlasmaGrenade", "Plasma",
                                     is_melee=False, hits_key="nrOfHits_2", multi=True,
                                     native_factory="ability")                          # MEME plage, 0x32
    return op_add(main, splash)


def scything_talons_tree() -> AtomicGroup:
    """Arbre de `ScythingTalonsAbility.ExecuteBehaviour @1812059f0` (id 1065, tyranSmnWarrior — MIRROR du
    DECOMPILE) :
        splash = Unique( Enemies(caster, AdjacentUnits(casterTile,1) & AdjacentUnits(targetTile,1), 3) )
        ExecuteAtomic( op_BitwiseAnd(
            AttackWithAttackDamage(caster, target, MinMaxDamage, Bio, condHits1=GetNumberConstant(0x2f)=3),
            AttackWithAttackDamage(caster, splash,  MinMaxDamage, Bio, condHits2=GetNumberConstant(0x32)=2) ) )
    Port : `AtomicGroup( op_and( AttackWithAttackDamage(Target(),"ScythingTalons","Bio",melee),
                                 AttackWithAttackDamage(<splash>,"ScythingTalons","Bio",melee,
                                                         hits_key="nrOfHits_2", multi=True) ) )`.
    Le SPLASH natif passe un SELECTEUR MULTI-cible directement a UN `AttackWithAttackDamage` (PAS un `Foreach`
    -> DIFFERE de CrushingClaws) : `AttackBehaviour.Execute @180fb91a0` resout la liste + `OrderBy` (cle
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
    -- `ExecuteAtomic @180fb0930` = `DSLFactory.AtomicGroup`, aucun `EvaluateAbilities` implicite, cf. #209).
    Ordre = main PUIS splash (== l'ancien imperatif, meme `state.rng`) -> bit-exact BY CONSTRUCTION vs
    l'ancien imperatif (`_adjacent_to_both`). L'imperatif `ScythingTalonsAbility.execute_behaviour` est
    REMPLACE par cet arbre.
    GAP (hors migration, tache #211) : les coups natifs = `ConditionalAmount(HasTrait(target,
    UnitTrait.Summon=2), hits*2, hits)` -> DOUBLENT si la CIBLE est un SUMMON (main 3->6, splash 2->4). Coups
    de BASE portes ici (== l'imperatif, jamais de sur-compte) ; le doublement = tranche behaviour-changing separee."""
    tgt = Target()
    main = AttackWithAttackDamage(tgt, "ScythingTalons", "Bio", is_melee=True)                 # MinMaxDamage/Bio/0x2f=3
    splash = AttackWithAttackDamage(
        Alive(And(AdjacentEnemies(CasterTile(), Const(1)), AdjacentEnemies(TargetTile(), Const(1)))),
        "ScythingTalons", "Bio", is_melee=True, hits_key="nrOfHits_2", multi=True)              # MEME plage, 0x32=2
    return AtomicGroup(op_and(main, splash))


def stikkbomb_tree() -> AtomicGroup:
    """Arbre de `StikkbombAbility.ExecuteBehaviour @18120c180` (id 1051, Ork Boy — MIRROR du DECOMPILE) :
        Execute( AtomicGroup( op_Addition(
            AttackWithAttackDamage(caster, target, RandomAmount(var0xc,var0xd), Blast, nrOfHits=0x2f=2),  # [MAIN]
            AttackWithAttackDamage(caster, AdjacentUnits(target,1,3), RandomAmount(MEME), Blast,
                                   nrOfHits_2=0x32=1) ) ) )                                                # [SPLASH]
    Le SPLASH natif passe un SELECTEUR MULTI-cible directement a UN `AttackWithAttackDamage` (PAS un `Foreach`)
    -> `AttackBehaviour.Execute @180fb91a0` resout la liste + `OrderBy` puis attaque chaque cible : porte via
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
    """Arbre de `FragstormAbility.ExecuteBehaviour @1811e0a00` (id 1078, templSmnAggressor — MIRROR du DECOMPILE) :
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

    Port : SPLASH = `Alive(Sub(AdjacentUnits(TargetTile()), AdjacentFriends(TargetTile())))` = occupants VIVANTS
    des tuiles adjacentes MOINS les amis-du-caster adjacents = la soustraction de tuiles native RESOLUE aux
    occupants (== ennemis adjacents pour un duel 2-teams ; `_within` exclut deja la cible dist 0, `AdjacentFriends`
    retire le caster). Le `PickRandomly(4)` est FOLDE dans la feuille via `pick_n` (tire 4 cibles DANS la
    resolution du selecteur d'attaque, comme `multi=True` folde l'`OrderBy` ; `state.rng`, == l'imperatif
    `_pick_randomly_n(_adjacent_enemies_of, 4)`). Plage `RandomAmount(minDmg/maxDmg)` PARTAGEE main/splash (memes
    cles par defaut) ; seule la constante de coups differe (nrOfHits 0x2f=4 vs nrOfHits_2 0x32=2). Profil Blast,
    RANGED (range 2). `op_BitwiseAnd` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ;
    `ExecuteAtomic` -> `AtomicGroup` (inline #201, == ScythingTalons, CONTRASTE Stikkbomb plain Execute). Ordre =
    main PUIS splash (meme `state.rng`). L'imperatif `FragstormAbility.execute_behaviour` (`_pick_randomly_n(
    _adjacent_enemies_of)` + `_splash_ability_behaviour`) est REMPLACE par cet arbre (bit-exact BY CONSTRUCTION :
    meme pool id-trie, meme pick, meme rng).

    ⚠ GAP #215 (RNG-exact) : le natif tire des HEXES (tuiles VIDES incluses -> un tirage peut tomber sur une
    tuile vide = coup gaspille) et l'ORDRE/cout exact du tirage `PickRandomlySelector.Select` ne sont pas cales ;
    le port tire des OCCUPANTS (id-tries, jamais de tuile vide) -> quand >4 tuiles adjacentes non-amies, les
    unites touchees ET la conso `state.rng` peuvent differer. Structure fidele (soustraction des amis, cap 4) ;
    RNG-exact = raffinement flagge."""
    # nrOfTargets = GetNumberConstant(0x11), lue live du gameconfig ; 4 = valeur config/i2 (« up to 4 ») si absente.
    n_targets = int(((GC.ability("Fragstorm") or {}).get("constants") or {}).get("nrOfTargets") or 4)
    tgt = Target()
    main = AttackWithAttackDamage(tgt, "Fragstorm", "Blast", is_melee=False)                        # RandomAmount/Blast/0x2f=4
    splash_sel = Alive(Sub(AdjacentUnits(TargetTile()), AdjacentFriends(TargetTile())))              # AdjacentTiles − Tiles(Friends) -> occupants non-amis
    splash = AttackWithAttackDamage(splash_sel, "Fragstorm", "Blast", is_melee=False,
                                     hits_key="nrOfHits_2", multi=True, pick_n=n_targets)            # MEME plage, PickRandomly(4), 0x32=2
    return AtomicGroup(op_and(main, splash))


def gauntlets_of_ultramar_tree() -> AtomicGroup:
    """Arbre de `GauntletsOfUltramarAbility.ExecuteBehaviour @1811e1c80` (id 1000, ultraCalgar — MIRROR du
    DECOMPILE) : AoE SELF-CAST a DEUX BANDES DE PORTEE (aucune cible unique -- ancre sur le CASTER, pas
    `Target()`) :
        adjSel  = `GetAdjacentTargetsSelector @1811e2010`  = Unique(Enemies(caster, AdjacentTiles(casterTile), 3))
        surrSel = `GetSurroundingTargetsSelector @1811e20d0` = Unobscured(caster,
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
    - **Snapshot eager de la bande adjacente** (`Get(SelectAllUnits(adjSel)) @18100ee50`) : le natif fige la
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
    cible, hors cible. Mirror `GetAdjacentDamageTargetsUnits` @1811cdad0 =
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


def _pick_randomly_n(state: "State", items: list, n: int) -> list:
    """`PickRandomly(items, n)` — n éléments DISTINCTS (extension de `_pick_randomly` spawn.py à n). len<=n
    → tous (le natif ne roll pas quand le set tient). Sinon tire n index SANS REMISE via `next_internal`
    (coût/ordre RNG NON calibré → GAP flaggé : désync possible de `state.rng` ; cf. spawn.py). `state.rng`
    None → subset trié déterministe `[:n]` (placement RNG-exact = raffinement, structure d'abord)."""
    items = list(items)
    n = max(0, int(n))
    if len(items) <= n:
        return items
    if state.rng is None:
        return items[:n]
    pool, out = list(items), []
    for _ in range(n):
        out.append(pool.pop(state.rng.next_internal(0, len(pool))))
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
    """`CrushingClawsAbility.ExecuteBehaviour` @1811cd5e0 (id 1105, tyranTyrantGuard).

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
    """`PlasmaGrenadeAbility.ExecuteBehaviour @1811f99e0` (id 1098, eldarSmnGuardian).

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
    """`StikkbombAbility.ExecuteBehaviour` @18120c180 (id 1051, Ork Boy — orksNpc2OrkBoy/orksOrkBoys).

    #149 slice-12 : la behaviour EST l'**arbre DSL** `stikkbomb_tree()` (mirror 1:1 du décompilé @18120c180 :
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
    """`FragstormAbility.ExecuteBehaviour` @1811e0a00 (id 1078, templSmnAggressor).

    #149 slice-13 : la behaviour EST l'**arbre DSL** `fragstorm_tree()` (mirror 1:1 du décompilé @1811e0a00 :
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
    """`ScythingTalonsAbility.ExecuteBehaviour @1812059f0` (id 1065, tyranSmnWarrior).

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
    """`GauntletsOfUltramarAbility.ExecuteBehaviour @1811e1c80` (id 1000, ultraCalgar).

    AoE SELF-CAST a DEUX BANDES DE PORTEE (ancre sur le CASTER, PAS `Target()`) : la bande ADJACENTE frappe
    tous les ennemis a dist 1 (`Unique(Enemies(AdjacentTiles(caster)))`, 2 coups = nrOfHits 0x2f + nrOfHits_2
    0x32) ; la bande SURROUNDING frappe les ennemis a dist EXACTEMENT 2, NON obscurcis (`Unobscured(
    SurroundingEnemies(caster,r=2) - Adjacent)`, 1 coup = nrOfHits_2 0x32). Meme plage `MinMaxDamage` +
    profil Bolter pour les deux bandes.

    La behaviour EST l'arbre DSL `gauntlets_of_ultramar_tree()` (mirror 1:1 du decompile @1811e1c80 :
    `ExecuteAtomic(op_BitwiseAnd(bandeAdj, bandeSurr), 0x1d)`). Les deux bandes = `AttackWithAttackDamage(
    multi=True)` (`AttackBehaviour.Execute @180fb91a0` resout la liste + `OrderBy` par id) -> memes Operations
    (`AttackDamageOperation.execute_ability_attack`) que l'imperatif -> bit-exact BY CONSTRUCTION (memes
    bornes/hits/profil, cibles triees par id, meme `state.rng`). La face PREDICTION (arc NC) est portee a part
    (`playbook/noncomparable/gauntlets_of_ultramar.py`, case-49/#50) ; ici = la face COMBAT (execute) seule,
    alignee sur la MEME geometrie Unobscured/surrounding validee live.

    `target_id` (cible que l'IA a choisie pour le message) est IGNORE pour le degat : Gauntlets frappe TOUT
    l'entourage du caster, pas cette cible (l'arbre n'utilise ni `Target()` ni `TargetTile()`)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.GauntletsOfUltramar)  # 1000
    ABILITY_ID = "GauntletsOfUltramar"

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
