"""Abilities actives Aeldari (porteurs `eldar*`). Module DEDIE (isolation de faction ; org native = 1 classe
par ability). RE ghidra gqfc5mff6c (VAs citees). Case-220 §6.19 (docs/rl/case-220/aeldari.md).

Executioner (1066, `eldarFarseer` « Eldryon »). Namespace natif `Abilities.Active.Loki.ExecutionerAbility`.
`IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE) :
    Execute( op_BitwiseAnd( op_BitwiseAnd( op_BitwiseAnd(
        SetCache( cacheA = Cache(Damageable(Enemies(@0x160, AdjacentUnits(@0x190, 1, 3)))) ),        # prime pool
        AttackWithAttackDamage( actor@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                                damageProfile = Nullable(0xd = 13 = Psychic), hits = RoundsStarted ) ),  # [MAIN]
        If( IsDead(target@0x178),
            AttackWithAttackDamage( actor@0x160, Cache(PickRandomly(Alive(cacheA), 1)), MEME MinMaxDamage,
                                    Nullable(0xd=Psychic), hits = RoundsStarted ) ) ),                    # [SECONDARY]
        Inform( 0xc1, First( CanAddUnit(AdjacentTiles(target@0x178) & AdjacentTiles(picked)), EntityId ) ) ) )

i2 : « takes 582-2183 Psychic Damage FOR EACH ROUND THAT HAS STARTED. If the target is eliminated, an
adjacent enemy also takes 582-2183 for each round started. ». Attaque RANGED (range 2, `is_melee=False`),
profil Psychic (pierce 100). Decision DEJA portee+validee (#122/#166, prediction `ExecutionerAbility` +
`_PLAYBOOK_PROFILE_OVERRIDE[1066]="Psychic"`).

- `hits = RoundsStarted` (`IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$GetHits` = `IdunBattleLogic.Entities.DSLFormulas$$RoundsStarted` -> `RoundsStartedFormula.
  IdunBattle.Entities.Formulas.RoundsStartedFormula$$Calculate` = SUM `UnitComponent.turnsStarted@+0x58` sur units-in-scope = le CASTER @0x160) =
  stat 12 (`GetStat(caster, 0xc)`), plancher `max(1,.)` (StartTurn incremente AVANT l'action -> round 1 = 1
  coup). Valeur DYNAMIQUE calculee au cast (le runner offline la maintient per-unit, #123 turnflow) — passee
  aux DEUX attaques (main + secondary), == le natif (uVar9 unique reutilise). `_rounds_started` mirror 1:1 de
  la face prediction (`ExecutionerAbility.get_special_hits`).
- `native_factory="attack"` : l'`IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$ExecuteBehaviour` appelle `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (famille ATTACK, 2 tirages/coup a cc=0 — verifie par XREF du decompile : symbole appele =
  `DSLFactory__AttackWithAttackDamage`, PAS `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage/dd0`), pour le MAIN comme le
  SECONDARY. Multi-coups (hits=RoundsStarted) -> classification factory OBLIGATOIRE (tip #2) : "attack".
- SECONDARY : ne fire QUE si la cible est MORTE apres le MAIN (`If(IsDead(Target()))`, evalue APRES le main
  dans la sequence `op_and`). Cible = 1 ennemi VIVANT tire au hasard adjacent (hex 1) a la cible
  (`PickRandomly(Alive(Enemies(AdjacentUnits(TargetTile()))), 1)`) — porte via la feuille `multi=True,
  pick_n=1` (fold du `PickRandomly` natif : pool trie par id -> `_pick_randomly_n(state.rng, 1)`, MEME conso
  rng = `min(len(pool),1)` tirages, y compris a 1 seul candidat -- #130 ; pas de tuile VIDE, la pool est des
  UNITES). Ordre RNG = main (hits) -> pick -> secondary (hits).
- `SetCache(cacheA)` (prime la pool PRE-main) FOLD : mono-cible (le main ne frappe QUE la cible, pas les
  voisins) + le cadavre GARDE sa position (`damage.py` : `alive=False` seulement, pas de retrait board) ->
  recalculer la pool POST-main via `TargetTile()`/`AdjacentUnits` rend le MEME ensemble (no-op observable,
  precedent SetCache-fold SpiritLeech/SavageEchoes). Le priming ne consomme AUCUN rng -> l'ordre rng est
  preserve.
- `Inform(0xc1=193, ...)` (dernier volet) FOLD : noeud AI/UI (hint de tuile intermediaire entre la cible et
  le secondary) -> le runner ne modelise PAS le bus de messages (`Inform` = no-op documente, precedent
  FireOfAbsolution). Aucune mutation de combat -> non porte (residu documente).

HarvesterOfSouls (1067, `eldarMauganRa` « Maugan Ra »). Namespace natif `Abilities.Active.Loki.
HarvesterOfSoulsAbility`. `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE) :
    hits = If( HasFlag(caster@0x160, Moved=0),                                   # IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHits
               ConfigConst(nrOfHits=0x2f),                                       #   a bouge -> nrOfHits
               Sum(ConfigConst(nrOfHits=0x2f), ConfigConst(extraHit=0x2b)) )     #   pas bouge -> nrOfHits+extraHit
    surrSel = SurroundingUnits(caster@0x160, GetNumberConstant(range=0x16))      # A : unites <= range hex du caster
    enemSel = Enemies(caster@0x160, AdjacentFriends(target@0x178, 1))            # B : ennemis ring-1 de la cible
    ExecuteAtomic( op_BitwiseAnd(
        AttackWithAttackDamage( caster@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                                damageProfile = Nullable(0x13 = 19 = HeavyRound), hits ),          # [MAIN]
        AttackWithAttackDamage( caster@0x160, op_BitwiseAnd(surrSel, enemSel),
                                MinMaxDamage2(minDmg_2 0x36/maxDmg_2 0x37),
                                damageProfile = Nullable(0x13 = HeavyRound), hits ) ), 0x2a )       # [SPLASH]

i2 : « 3x [dmg] HeavyRound + 1 extra hit if hasn't moved a un ennemi, ET aux ennemis adjacents dans un rayon ».
Attaque RANGED (`attackRangeType=Ranged`, `is_melee=False`), profil HeavyRound (pierce 55). Config 1067 :
nrOfHits=2, extraHit=1, range=3 ; minDmg_2/maxDmg_2 == minDmg/maxDmg (bornes PARTAGEES). Decision DEJA
portee+validee (#122, `active_ability.HarvesterOfSoulsAbility.GetHits`/`_AOE` ; ground-truth seed777 step-17
per-coup 987/1481 = entree x 0.55 = pierce 55 = HeavyRound).

- `hits = If(HasFlag(caster, Moved=0), nrOfHits, Sum(nrOfHits, extraHit))` (`IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHits` = `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHitFormula`). `HasFlag(caster@0x160, 0)` (`IdunBattleLogic.Entities.DSLTriggers$$HasFlag` -> `IdunBattle.Entities.Conditions.HasFlagAbilityTrigger$$ShouldTrigger` = `UnitFlagsComponent.Has(caster, flag)`, expected=1) = le caster a le flag `UnitFlag.Moved=0`
  (`UnitFlagsComponent.MOVED`, pose par `SetMovedFlag`). Le natif = `If(a_bouge, nrOfHits, nrOfHits+extraHit)` :
  A BOUGE -> nrOfHits=2 coups ; PAS BOUGE -> nrOfHits+extraHit=3 coups (i2 « +1 extra hit if hasn't moved »).
  Valeur DYNAMIQUE calculee au cast, passee aux DEUX attaques (main + splash) == le natif (uVar10 unique reutilise).
  Miroir 1:1 de la face prediction (`HarvesterOfSoulsAbility.GetHits` = MEME arbre `If(HasFlag, ...)`).
- `damageProfile = Nullable(0x13 = 19 = HeavyRound)` : le combat passe un OVERRIDE de profil EXPLICITE (stocke
  `AttackDamageBehaviour+0x88`, `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$.ctor`) = HeavyRound (`DamageProfileType.HeavyRound=19`, pierce 55),
  pour le MAIN comme le SPLASH. Coincide numeriquement avec la face prediction (config SANS damageProfile ->
  fallback arme RANGED = HeavyRound de Maugan, pierce 55, ground-truth seed777) -> profil combat "HeavyRound".
  (Contraste Executioner : `Nullable(0xd=13=Psychic)`.)
- `native_factory="attack"` : l'`IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$ExecuteBehaviour` appelle `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (famille ATTACK, 2 tirages/coup a cc=0 — XREF du decompile = `DSLFactory__AttackWithAttackDamage`,
  PAS `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage/dd0`), pour le MAIN comme le SPLASH. Multi-coups (hits=2/3) ->
  classification factory OBLIGATOIRE (tip #2) : "attack" (== Executioner).
- SPLASH (selecteur MULTI-cible passe DIRECTEMENT a UN `AttackWithAttackDamage`, PAS un `Foreach` -> patron
  PlasmaGrenade/ScythingTalons ; `multi=True`) = `And(SurroundingUnits(caster, range=3), AdjacentEnemies(target,
  1))` : ennemis du caster (1) a dist hex <= range(3) de la tuile COURANTE du caster ET (2) adjacents (ring-1)
  a la tuile de la cible. Le natif B = `Enemies(caster, AdjacentFriends(target,1))` = ennemis-du-caster adjacents
  a la cible ; PORTE via `AdjacentEnemies(TargetTile(), Const(1))` -- le runner `AdjacentFriends` filtre
  `team==CASTER` (PAS subject-relatif comme le natif), donc `Enemies(AdjacentFriends(target))` serait VIDE en
  runner ; `AdjacentEnemies(TargetTile())` = ennemis-du-caster ring-1 de la cible = l'equivalent CORRECT
  (convention etablie #122, active_ability._AOE). A & B PRUNE ASYMETRIQUEMENT (ground-truth seed777 step-17 :
  A dist<=3 exclut les ennemis a dist 4 du caster). `Alive` compense les cadavres offline (mirror : le natif
  `Units(SurroundingTiles)` n'a que les unites DEBOUT = vivantes, convention #202/#148). La cible principale est
  hors splash (B exclut le centre = tuile-cible). Bornes splash = `MinMaxDamage2` (minDmg_2/maxDmg_2 = cles
  0x36/0x37 ; == minDmg/maxDmg ici) ; MEMES hits que le main.
- `ExecuteAtomic(op_BitwiseAnd(main, splash), 0x2a)` -> `AtomicGroup(op_and(main, splash))` (inline #201 ; tag
  0x2a = id du groupe atomique, aucun `EvaluateAbilities` implicite, cf. #209). Ordre = main PUIS splash (cibles
  triees par id, `OrderBy` natif) -> meme `state.rng` -> bit-exact BY CONSTRUCTION vs une sequence directe.
- Passif `InescapableAccuracy` (eldarMauganRa, gated « n'a pas bouge » : +crit-chance/+crit-dmg/override-hits)
  = item SEPARE ([opus]+prerequis), NON porte -> le runner offline l'ignore. Consequence validation : le cas
  A BOUGE (hits=2) gate le passif OFF (cc=0, bit-exact propre) ; le cas PAS BOUGE (hits=3) : le live applique
  le passif (crits) -> divergence per-coup ATTENDUE cote live (non un bug de ce port), la structure (3 coups +
  splash) reste porte fidele.

EmpyricAmbush (1232, `eldarLhykhis` « Lhykhis »). Namespace natif `Abilities.Active.Loki.EmpyricAmbushAbility`.
`IdunBattleLogic.Entities.Abilities.Active.Loki.EmpyricAmbushAbility$$ExecuteBehaviour` (MIRROR du
DECOMPILE, terme a terme, dans l'ordre des `op_BitwiseAnd`) :

    tiles = First( SortTilesByUtility( Randomize( CanAddUnit(AdjacentTiles(Target@+0x60))
                                                  op_Subtraction <DSLSelectors+0x50 = CasterTile> ),
                                       unit = Caster@+0x48, utilityType = 7 = Tile, parent = 0 ),
                   amount = 1, ignoreForcedTargets = 0 )
    AActiveAbility.Execute(
        FlyUnit( Caster@+0x48, tiles )
      & If( <DSLTriggers+0x20> = OwnerIsAlive,
              AttackWithAttackDamage( Caster@+0x48, Target@+0x60, MinMaxDamage(minDmg/maxDmg),
                                      damageProfile = GetDamageProfile(), hits = Get(GetHits()),
                                      abilityOrEffect = AbilityOrEffect(this+0x10),
                                      options = Nullable<AttackDamageBehaviourOptions> VIDE )
            & AddEffect( 0x62a = 1578 EmpyricAmbush, AbilityStateReference,
                         source = Owner@+0x30, targets = Target@+0x60,
                         turns = <DSLFormulas+0x20> = Direct(1) ) ) )

i2 : Lhykhis se TELEPORTE au contact de sa cible, la frappe, et la MARQUE pour un tour (les heros allies
qui la frappent ensuite gagnent +crit -- c'est l'EFFET 1578, deja porte par #589-r1-r1 ;
`entities/effects/loki/empyric_ambush.py`). Ce module-ci porte la **POSE**.

QUATRE lectures que le decompile impose et qu'il ne faut pas « lisser » :

  * **le `If` ne couvre QUE l'attaque et la marque**, pas le vol -- `<DSLTriggers+0x20>` est le MEME slot
    qu'utilisent `WallOfMirrors`, `RammingSpeed`, `SkyStrike` et `ExemplarOfTheKauyon` : `OwnerIsAlive`
    (`IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger`, nomme par #389). APRES un deplacement,
    AVANT l'attaque : « le porteur a-t-il SURVECU au vol ? » (overwatch/piege declenches par la charge).
  * **`Randomize` est un `PickRandomAmountSelector` a `amount = 0x7fffffff` SANS repetition** = une
    PERMUTATION ALEATOIRE COMPLETE du pool, donc **`len(pool)` tirages PRNG**, bornes decroissantes
    (loi #130/#215 : le dernier tirage, `range == 1`, consomme quand meme). Il est ENVELOPPE par
    `SortTilesByUtility`, dont le `Select` finit par un `Enumerable.OrderBy` -- tri **STABLE** : l'alea ne
    survit donc que sur les EX AEQUO d'utilite. Le tirage a lieu a l'EXECUTION de `FlyUnit` (le selecteur
    n'est evalue que la), donc AVANT les tirages de degat de l'attaque -- ordre RNG : `len(pool)` picks,
    puis la salve.
  * **`op_Subtraction <DSLSelectors+0x50>`** retranche l'empreinte du CASTER (`CasterTileSelector`, slot
    identifie par `IdunBattleLogic.Entities.DSLTriggers$$get_CasterIsCasterTile` = `AreEqual(+0x48, +0x50)`)
    -- REDONDANT en pratique avec `CanAddUnit` (`IdunBattle.Entities.TileExtensions$$CanAddUnit` lit le
    `TileContentComponent`, donc la tuile du caster est deja occupee), mais mirrore tel quel. Le port passe
    `CasterTile(as_ids=True)` : sans la conversion en ids, la soustraction comparerait des positions a des
    ids de tuile et ne retrancherait RIEN, silencieusement.
  * **le degat n'a AUCUN override** : `MinMaxDamage` = bornes config brutes, `damageProfile =
    AActiveAbility$$GetDamageProfile` = `AbilityConfiguration$$GetDamageProfile(config)` (= la cle
    `damageProfile` du gameconfig, LUE et non codee en dur), `hits = Get(AActiveAbility$$GetHits)` =
    `GetNumberConstant(0x2f = nrOfHits)`. Le 8e argument `Nullable<AttackDamageBehaviourOptions>` est passe
    **VIDE** (`local_1b8..local_198 = 0`) -> ni `alwaysOverkilled`, ni `alwaysCrit`, ni variance d'arme
    (`amount_spread_pct` hors sujet : on est en mode BORNES). Config 1232 LUE : `attackRangeType = Melee`
    (-> `is_melee=True`), `damageProfile = Eviscerate`, `nrOfHits = 8`.

CONFRONTABILITE : `eldarLhykhis` est **HORS CATALOGUE** du seed BC (`catalog_inject --missing` la liste ;
`rl_duel build --list-pool` ne la rend pas) -> injection `catalog_inject.write_augmented_seed_bc` +
`build --seed-bc` (`docs/rl/case-92-catalog-injection.md` §6). C'est le MEME montage que
`probe_589r1r1_empyric_ambush_live.py`, qui castait deja 1232 en LIVE.

SilentDeath (1068, `eldarJainZar` « Jain Zar »). Namespace natif `Abilities.Active.Loki.
SilentDeathAbility`. C'est une **CHAINE DE DEGAT** -- le seul arbre de ce module dont la structure
est CONSTRUITE PAR UNE BOUCLE C# a la construction du behaviour, pas ecrite en dur.
`IdunBattleLogic.Entities.Abilities.Active.Loki.SilentDeathAbility$$ExecuteBehaviour`
(MIRROR du DECOMPILE, terme a terme, dans l'ordre des allocations) :

    df       = this+0x30                                    # DSLFactory
    sel      = df+0x90                                      # DSLSelectors
    beh      = df+0x78                                      # DSLBehaviors
    d        = new <>c__DisplayClass1_0 { ability = this, abilityState = *abilityState }
    ennemis  = DSLSelectors$$Cache( DSLSelectors$$Enemies( of       = sel+0x48 = Caster,
                                                          entities = sel+0x20 = AllAliveUnits,
                                                          selectionType = 3 ),
                                    matchAbilityEntities = 1 )
    amorce   = DSLBehaviors$$SetCache( ennemis )
    prev     = sel+0x60 = Target
    vus      = new List<TargetsSelector>()
    b        = DSLBehaviors$$Nothing()  op_Addition  d.<ExecuteBehaviour>b__0( prev )
    vus.Add( prev )
    for (i = 0 ; i < GetNumberConstant(config+0x60, 0x11 = nrOfTargets) ; i++) :
        pool = DSLSelectors$$AdjacentUnits( prev, unique = 1, selectionType = 3 )
               op_BitwiseAnd  ennemis
        foreach (s in vus) : pool = pool op_Subtraction s
        pris = DSLSelectors$$Cache( DSLSelectors$$PickRandomly( pool, amount = 1,
                                                               allowDuplicates = 0,
                                                               maxDuplicatesAllowed = 0x7fffffff,
                                                               ignoreForcedTargets = 0 ), 1 )
        b    = b  op_Addition  d.<ExecuteBehaviour>b__0( pris )
        vus.Add( pris )
        prev = pris
    AActiveAbility$$Execute( DSLBehaviors$$Group( amorce op_BitwiseAnd b,
                                                 groupEntity = DSLSelectors$$None(),
                                                 groupType   = 0x1d ),
                             entities )

    <>c__DisplayClass1_0$$<ExecuteBehaviour>b__0(cible) =
        DSLBehaviors$$AttackWithAttackDamage(
            caster        = sel+0x48,
            target        = cible,
            amount        = AActiveAbility$$MinMaxDamage(d.abilityState, isPrediction: 0),
            damageProfile = Nullable( AActiveAbility$$GetDamageProfile() ),
            hits          = DSLFormulas$$Get( GetNumberConstant(config+0x60, 0x2f = nrOfHits) ),
            abilityOrEffect = AbilityOrEffect$$op_Implicit(...),
            options       = <struct ZEROEE, HasValue = 0>,
            selectionType = 2 )

i2 : « Jain Zar throws the Silent Death at an adjacent enemy, dealing 3x minDmg-maxDmg Piercing Damage
to it **and up to nrOfTargets additional enemies adjacent to each other**, before returning to Jain
Zar's hands. » Config 1068 LUE : `attackRangeType = Melee` (-> `is_melee=True`), `damageProfile =
Piercing`, `nrOfHits = 3`, `nrOfTargets = 3` -> jusqu'a **4** unites frappees (la cible + 3 maillons).

CINQ lectures que le decompile impose et qu'on ne devine pas :

  * **La chaine est SEQUENTIELLE, chaque maillon partant du PRECEDENT** : `AdjacentUnits(prev, ...)`
    ou `prev` est le maillon `i-1`, PAS la cible primaire. « up to N additional enemies adjacent to
    EACH OTHER » de l'i2 dit exactement ca. Un port qui prendrait N ennemis adjacents a la CIBLE
    (patron splash Executioner/HarvesterOfSouls) frapperait un ensemble DIFFERENT des le maillon 2.
  * **Les selecteurs sont LAZY, donc la chaine s'INTERLEAVE avec les degats.** Chaque maillon est un
    `Cache(PickRandomly(...))` qui n'est evalue qu'a l'execution de SON `AttackWithAttackDamage` --
    c'est-a-dire APRES que le maillon precedent a encaisse ses coups. Le pool du maillon `i` voit donc
    l'etat POST-degat du maillon `i-1` : une unite tuee par le maillon `i-1` n'est plus sur sa tuile
    (`UnitsOnTilesSelector`, filtre d'occupation mirrore par `_within`) et ne peut pas etre piquee.
    Le `Cache` est ce qui FIGE le tirage : le meme selecteur est relu par le `op_Subtraction` des
    iterations suivantes SANS re-tirer (cache hit, 0 rng).
  * **Le `SetCache(ennemis)` fige le camp ADVERSE AVANT le premier coup** (`amorce` est l'operande
    GAUCHE du `op_BitwiseAnd` final, donc executee en tete). Le pool d'ennemis est donc celui du
    DEBUT du cast, intersecte a chaque maillon avec l'adjacence VIVANTE du moment. C'est ce qui rend
    l'ordre `SetCache` puis attaques observable, et pourquoi il n'est PAS foldable ici (contrairement
    a Executioner, dont le `SetCache` etait un no-op mono-cible).
  * **`vus` retranche TOUS les maillons deja frappes, la cible primaire COMPRISE** : la chaine ne
    revient jamais en arriere, meme si la geometrie le permettrait (deux ennemis mutuellement
    adjacents ne se renvoient pas la balle). C'est une liste, pas un simple `!= prev`.
  * **Le degat n'a AUCUN override, et il est IDENTIQUE sur les 4 feuilles** : le lambda `b__0` est
    UNE seule methode, appelee avec des `cible` differentes -- memes `MinMaxDamage` (bornes config),
    meme `Nullable(GetDamageProfile())` = `Piercing`, memes `hits = nrOfHits` = 3. Le 7e argument
    `Nullable<AttackDamageBehaviourOptions>` est passe **VIDE** (`local_78..local_58 = 0`) -> ni
    `alwaysOverkilled`, ni `alwaysCrit`, ni variance d'arme. Le `pierce` de la mecanique `pierce` du
    kit vient donc du PROFIL (`Piercing.PiercingRatio`) + les stats `ExtraPierce*` du caster, par le
    volet commun `profile_pierce` -- il n'y a AUCUN terme de percage propre a 1068.

`Group(..., 0x1d)` = `GroupType.DamageChain` (LU dans `data/symbols/<build>/frida/enums.tsv`, pas
devine) : groupe de PRESENTATION, pass-through d'etat cote port (#201, meme statut qu'`AtomicGroup`).
Son `groupEntity` est `DSLSelectors$$None()` -- METADONNEE de vue, jamais evaluee.

CONFRONTABILITE : `eldarJainZar` est un HERO du pool `rl_duel build --list-pool` (verifie rank 17) ;
aucune injection catalogue, aucun montage de relique. Portee ADJACENTE (preset `+0x40`) -> le drive
des positions (`--place`/`--a-place`) est OBLIGATOIRE pour qu'un ennemi soit au contact, et il faut
en aligner PLUSIEURS pour exercer la chaine au-dela du maillon 1.

FireAndReposition (1063, `eldarRanger` << Calandis >>) -- #567. TROIS mecaniques, pas une : le
decompile emboite `op_Addition(op_Addition(UseActiveAbility(Caster, Target,
UnitNormalAttackType(Caster)), ResetMovement(Owner)), AddEffect(0x456, source = Caster,
targets = Caster, TurnsFromRounds(1)))`. Detail complet dans le bloc dedie en bas de module.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_add, op_and, If, AtomicGroup, Group, SetCache
from ...entities.effect_type import EffectType
from ...entities.selectors.accessors import CasterTile, Owner, Target, TargetTile
from ...entities.selectors.geometry import (AtIndex, Cache, ConditionalSelector, Null, Otherwise,
                                            PickFirstN, PickLastN, PickRandomly, Randomize,
                                            TilesBehindInLine)
from ...entities.selectors.tiles import (AdjacentTiles, AllAliveUnits, AllTiles, CanAddUnit, Caster,
                                         SortTilesByUtility, TileBehindTargetFromSourceDirection)
from ...entities.selectors.units import (
    AdjacentEnemies, AdjacentUnits, Alive, And, Damageable, Enemies, First, SortByDistance, Sub,
    SurroundingUnits, Tiles, Union, Units, UnitsAttackedThisTurn
)
from ...entities.formulas import Count, Get
from ...streams.group_type import GroupType
from ...entities.triggers import AmountIsGreater, AmountIsGreaterThanZero, AreEqual, CanMove, IsDead, Not, OwnerIsAlive
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.stats import StatType
from ...utilities.utility_type import UtilityType
from ...entities.ability_constant_type import AbilityConstantType
from ...entities.ability_variable_type import AbilityVariableType
from ..components import PositionComponent, StatsComponent, unit_has_moved
from .base import ActiveAbility, active_ability_state
from .behaviours.chain import ChainAttackDamage
from .behaviours.combat import AttackWithAbilityDamage, AttackWithAttackDamage, UseActiveAbility
from .behaviours.context import entities_from_state
from .behaviours.effects import AddEffect, RemoveEffect
from .behaviours.movement import FlyUnit, MoveUnit, ResetMovement
# `DiveAttackAbilityBase` vit dans le namespace natif `...Active.Loki` : le mirror y reste, et les
# deux heritieres (1064 ici, 1091 sur `thousandsons.py`) l'importent -- jamais l'une l'autre.
from .loki.dive_attack import DiveAttackAbility, dive_attack_profile
from .targeting import (RANGE_ADJACENT, RANGE_ADJACENT_IF_MELEE_CASTER, RANGE_FROM_CONFIG,
                        RANGE_SELF, RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE,
                        RANGED_BOOL_IF_RANGED_CASTER, RANGED_BOOL_TRUE, TargetingOptions)
from .targeting_rule import TargetingRule as TR
from ...entities.effects.magnitude import ability_var, ability_var_array
from ...entities.unit_selection_type import UnitSelectionType

#: `UnitSelectionType` LU au dernier argument des `DSLSelectors$$*` de ce fichier -- releve
#: #585-r1, build `rnca9r7q6c`, littéral par littéral (JAMAIS par symetrie : deux call-sites
#: du releve passent `Any` parce que leur source est un ensemble de MORTS).
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3


if TYPE_CHECKING:
    from ..state import State


# =================================================================================================== #
# GATE DE CIBLE (#115) — les `TARGETING_OPTIONS` des 2 actives Aeldari portees.
#
# Le masque est le champ `Rules` (`options+0x28`) des `IdunBattle.Core.Services.TargetingOptions` que
# le `<X>Ability$$.ctor` passe a `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` (qui recopie la
# struct dans `this+0x70..0xaf` et n'ECRASE que `+0x30`/`+0x38`, les deux regles-delegues : `Rules`
# arrive INTACT jusqu'au filtre).
#
# LES DEUX ctors Aeldari sont de la forme PRESET COPIE : ils n'appellent AUCUN
# `TargetingOptions..ctor`, ils recopient les 0x40 octets du champ STATIQUE de `TargetingOptions`
# situe a l'offset +0x140 du bloc `<class>+0xb8`, sans AUCUN flag additionnel. Le masque est donc
# celui qu'ecrit `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` :
# `*(statics + 0x168) = 0x4002`, valeur CONSTANTE lue dans ce cctor.
# Ce n'est PAS la surcharge « preset + flags » (`TargetingOptions..ctor(&opts, &preset, <flags>)`, qui
# fait `Rules <- preset.Rules | flags` et dont le litteral visible ne serait pas le masque effectif) :
# ici la copie est integrale, il n'y a pas de flag a OR-er.
#
# Noms des bits : enum `IdunBattle.Core.Services.TargetingRule` VERBATIM
# (`data/symbols/gqfc5mff6c/frida/enums.tsv`).
#     0x2    TargetMatchesDynamicRule -> consulte `get_dynamic_invalid_target_reason`. AUCUNE des deux
#            abilities n'a de `GetDynamicInvalidTargetReason` natif (le slot vtable +0x480 reste celui
#            de la base) -> le defaut 0 du port est le mirror EXACT, pas une degradation.
#     0x4000 TargetIsEnemy            -> PORTE (`TargetingQuery$$UnitsCanAttackEachOther`) : refus sur
#            soi-meme et sur un allie.
# =================================================================================================== #


def _rounds_started(state: "State", caster_id: int) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$GetHits` = `IdunBattleLogic.Entities.DSLFormulas$$RoundsStarted` -> `RoundsStartedFormula.
    IdunBattle.Entities.Formulas.RoundsStartedFormula$$Calculate` = SUM `UnitComponent.turnsStarted@+0x58` sur units-in-scope (scope = le CASTER
    @0x160) = stat 12 (`GetStat(caster, 0xc)`, `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate`). Plancher
    `max(1,.)` (StartTurn incremente AVANT l'action -> round 1 = 1 coup, jamais 0). MIROIR 1:1 de la face
    prediction (`ExecutionerAbility.get_special_hits`, active_ability.py). Le runner offline maintient
    `turnsStarted` per-unit (#123, `StartTurnOperation.execute` bumpe `UnitComponent+0x58`)."""
    ce = state.get_entity(caster_id)
    sc = ce.get_component(StatsComponent) if ce is not None else None
    us = getattr(sc.ctx, "stats", None) if sc is not None else None
    ts = us.get_stat(int(StatType.TURNS_STARTED), 0) if us is not None else 0
    return max(1, int(ts or 0))


def executioner_tree(n_hits: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE ; cf. en-tete module) :
        op_and( AttackWithAttackDamage(Target(), "Executioner", "Psychic", ranged, hits=n),               # MAIN
                If( IsDead(Target()),
                    AttackWithAttackDamage(pool, "Executioner", "Psychic", ranged, multi, pick_n=1,
                                           hits=n) ) )                                                     # SECONDARY

    `pool = Alive(Damageable(Enemies(AdjacentUnits(TargetTile()))))` = ennemis (team != caster) VIVANTS
    adjacents (hex 1) a la tuile de la cible (mirror `Damageable(Enemies(@0x160, AdjacentUnits(@0x190,1,3)))`
    + `Alive` du PickRandomly natif ; `AdjacentUnits` radius defaut 1). `TargetTile()` = tuile de la cible
    (@0x190 = role tuile-cible, distinct de @0x178=Target-unit mais MEME position ; le cadavre garde sa
    tuile). `multi=True, pick_n=1` folde le `PickRandomly(., 1)` (tri par id -> `_pick_randomly_n`, qui tire
    `min(len(pool),1)` fois : **1 tirage des qu'il y a >=1 candidat**, meme unique -- #130, le natif ne
    court-circuite pas). `hits=n` (RoundsStarted) OVERRIDE la config `nrOfHits` sur les 2 feuilles.
    `native_factory="attack"` par defaut (XREF IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage). `If(IsDead(Target()))` s'evalue APRES le MAIN
    (sequence gauche->droite `op_and`) : le secondary ne fire que si le main a tue la cible. `Inform(0xc1)` et
    `SetCache` FOLDES (cf. en-tete)."""
    ability_type = int(ActiveAbilityType.Executioner)               # AbilityOrEffect(this+0x10) threade after-hit
    main = AttackWithAttackDamage(Target(), "Executioner", "Psychic", is_melee=False,
                                  hits=n_hits, native_factory="attack", ability_type=ability_type)
    # #585-r1 : `AdjacentUnits(gs, gs@0x78, unique: 1, 3)` puis `Enemies(gs, gs@0x48, ., 3)` --
    # littéraux LUS dans `...ExecutionerAbility$$ExecuteBehaviour`.
    pool = Alive(Damageable(Enemies(AdjacentUnits(TargetTile(), selection_type=SELECTION),
                                    selection_type=SELECTION)))  # ennemis vivants adjacents a la cible
    secondary = AttackWithAttackDamage(pool, "Executioner", "Psychic", is_melee=False,
                                       multi=True, pick_n=1, hits=n_hits, native_factory="attack",
                                       ability_type=ability_type)
    return op_and(main, If(IsDead(Target()), secondary))


class ExecutionerAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$ExecuteBehaviour` (id 1066, `eldarFarseer` « Eldryon », Aeldari) —
    MIRROR du DECOMPILE, arbre DSL (`executioner_tree`). Attaque RANGED Psychic (pierce 100) `hits=RoundsStarted`
    sur la cible ; SI la cible MEURT, meme attaque sur 1 ennemi VIVANT random adjacent a la cible (`If(IsDead)`
    evalue APRES le main). Le behaviour est l'arbre DSL : la feuille `AttackWithAttackDamage` (mode bornes,
    `hits` override = RoundsStarted) emet la MEME Operation d'attaque d'ability que le pipeline combat porte
    -> bit-exact BY CONSTRUCTION vs une sequence directe sous meme rng. `native_factory="attack"` (IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage,
    XREF) -> conso rng per-coup correcte (2 tirages/coup a cc=0). Decision DEJA portee+validee (#122/#166)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Executioner)   # 1066
    ABILITY_ID = "Executioner"

    # GATE DE CIBLE (#115) — PRESET COPIE (cf. le bloc en tete de module).
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$.ctor` :
    #     opts <- <TargetingOptions statics>+0x140 .. +0x17f    (copie des 0x40 octets, aucun flag ajoute)
    #     AActiveAbility..ctor(this, &opts, 0, 0)
    # `TargetingOptions$$.cctor` : `*(statics+0x168) = 0x4002` = TargetMatchesDynamicRule | TargetIsEnemy.
    # PORTEE (#241) : preset `TargetingOptions` statique `+0x140` -> `TargetingRange`
    # statique `+0x18` (`useRangeFromConfig` = la constante `range` de la config d'ability,
    # ici 2) + `forceMeleeTarget = True` (clamp a 1 si un ennemi est au contact du caster).
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        n_hits = _rounds_started(state, caster_id)                  # GetHits = RoundsStarted (uVar9 unique)
        ectx = ExecutionContext(state=state, rng=state.rng)
        executioner_tree(n_hits).execute(entities_from_state(state, caster_id, target_id), ectx)
        attacks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = attacks[0].get("attack") if attacks else None        # MAIN = 1er volet emis (Target())
        secondary = [{"target": a.get("target"), "attack": a.get("attack")} for a in attacks[1:]]
        return {"ability": "Executioner", "caster": caster_id, "target": target_id,
                "hits": n_hits, "main_attack": main, "secondary_attacks": secondary, "dsl": True}


def _harvester_hits(state: "State", caster_id: int) -> int:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHits` = `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetHitFormula` = arbre DSL
    `If(HasFlag(caster@0x160, Moved=0), ConfigConst(nrOfHits), Sum(ConfigConst(nrOfHits), ConfigConst(extraHit)))`.
    `HasFlag(caster, 0)` (`IdunBattleLogic.Entities.DSLTriggers$$HasFlag` -> `IdunBattle.Entities.Conditions.HasFlagAbilityTrigger$$ShouldTrigger` =
    `UnitFlagsComponent.Has(caster, flag=0)`, expected=1) = le caster porte `UnitFlag.Moved=0` (a bouge ce tour).
    Donc : A BOUGE -> nrOfHits ; PAS BOUGE -> nrOfHits + extraHit (i2 « +1 extra hit if hasn't moved »). MIROIR
    1:1 de la face prediction (`active_ability.HarvesterOfSoulsAbility.GetHits`). `nrOfHits`/`extraHit` lus via
    `ability_var(is_constant=True)` = `GetNumberConstant` (config 1067 : nrOfHits=2, extraHit=1)."""
    n = int(ability_var("HarvesterOfSouls", "nrOfHits", is_constant=True) or 1)
    extra = int(ability_var("HarvesterOfSouls", "extraHit", is_constant=True) or 0)
    # #101 : LECTEUR PARTAGE du flag natif (meme `HasFlag(unit, Moved)` que le gate no-move
    # d'HeavyWeapon_ExtraDmg / la branche fin-de-tour de RadSaturation) -> une seule source.
    return n if unit_has_moved(state, caster_id) else (n + extra)


def harvester_of_souls_tree(n_hits: int, range_r: int) -> AtomicGroup:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE ; cf. en-tete module) :
        AtomicGroup( op_and(
            AttackWithAttackDamage(Target(), "HarvesterOfSouls", "HeavyRound", ranged, hits=n),          # MAIN
            AttackWithAttackDamage( And(SurroundingUnits(CasterTile(), Const(range)),                     # SPLASH
                                        AdjacentEnemies(TargetTile(), Const(1))),
                                    "HarvesterOfSouls", "HeavyRound", ranged, min_key="minDmg_2",
                                    max_key="maxDmg_2", multi=True, hits=n ) ) )

    MAIN = attaque RANGED HeavyRound (pierce 55) sur la cible du message, `hits=n` (RoundsStarted-like : hits
    dynamique = 2 si a bouge / 3 sinon, override la config nrOfHits sur la feuille). SPLASH = MEME attaque sur les
    ennemis du caster a la fois <= `range`(3) hex de la tuile COURANTE du caster ET adjacents (ring-1) a la cible
    (`And(SurroundingUnits(CasterTile(), range), AdjacentEnemies(TargetTile(), 1))`, wrap `Alive` = compense les
    cadavres offline), bornes `MinMaxDamage2` (minDmg_2/maxDmg_2). `damageProfile = Nullable(0x13=HeavyRound)` sur
    les DEUX feuilles (override explicite du combat, pierce 55). `native_factory="attack"` par defaut (XREF
    IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage, 2 tirages/coup a cc=0 == Executioner). `multi=True` folde le selecteur multi-cible (tri par id =
    ordre de lecture natif). `ExecuteAtomic(., 0x2a)` -> `AtomicGroup` (inline #201, aucun EvaluateAbilities #209).
    Ordre = main PUIS splash -> meme `state.rng` -> bit-exact BY CONSTRUCTION."""
    ability_type = int(ActiveAbilityType.HarvesterOfSouls)          # AbilityOrEffect(this+0x10) threade after-hit
    main = AttackWithAttackDamage(Target(), "HarvesterOfSouls", "HeavyRound", is_melee=False,
                                  hits=n_hits, native_factory="attack", ability_type=ability_type)
    splash_sel = Alive(And(SurroundingUnits(CasterTile(), Const(int(range_r))),     # A : <= range hex du caster
                           AdjacentEnemies(TargetTile(), Const(1))))                # B : ennemis ring-1 de la cible
    splash = AttackWithAttackDamage(splash_sel, "HarvesterOfSouls", "HeavyRound", is_melee=False,
                                    min_key="minDmg_2", max_key="maxDmg_2", multi=True, hits=n_hits,
                                    native_factory="attack", ability_type=ability_type)
    return AtomicGroup(op_and(main, splash))


class HarvesterOfSoulsAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$ExecuteBehaviour` (id 1067, `eldarMauganRa` « Maugan Ra », Aeldari) —
    MIRROR du DECOMPILE, arbre DSL (`harvester_of_souls_tree`). Attaque RANGED HeavyRound (pierce 55)
    `hits = If(HasFlag(caster, Moved), nrOfHits=2, nrOfHits+extraHit=3)` sur la cible + MEME attaque sur les
    ennemis adjacents-cible ∩ rayon-`range`(3) du caster (splash `MinMaxDamage2`). Le behaviour est l'arbre DSL :
    les feuilles `AttackWithAttackDamage` (mode bornes, `hits` override = la formule not-moved) emettent la MEME
    Operation d'attaque d'ability que le pipeline combat porte -> bit-exact BY CONSTRUCTION vs une sequence
    directe sous meme rng. `native_factory="attack"` (IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage, XREF) -> conso rng per-coup correcte (2
    tirages/coup a cc=0). `damageProfile` override explicite = HeavyRound (`Nullable(0x13=19)`). `ExecuteAtomic`
    (tag 0x2a) -> `AtomicGroup`. Decision DEJA portee+validee (#122). Passif `InescapableAccuracy` (crit gated
    not-moved) NON porte = item separe -> le cas A BOUGE (hits=2) est le canal de validation bit-exact propre."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.HarvesterOfSouls)   # 1067
    ABILITY_ID = "HarvesterOfSouls"

    # GATE DE CIBLE (#115) — PRESET COPIE (cf. le bloc en tete de module).
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$.ctor` :
    #     opts <- <TargetingOptions statics>+0x140 .. +0x17f    (copie des 0x40 octets, aucun flag ajoute)
    #     AActiveAbility..ctor(this, &opts, 0, 0)
    # `TargetingOptions$$.cctor` : `*(statics+0x168) = 0x4002` = TargetMatchesDynamicRule | TargetIsEnemy.
    # PORTEE (#241) : meme preset `+0x140` -> `useRangeFromConfig`
    # (`HarvesterOfSouls.constants.range` = 3) + `forceMeleeTarget = True`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        n_hits = _harvester_hits(state, caster_id)                  # GetHits = If(HasFlag(Moved), nrOfHits, +extraHit)
        range_r = int(ability_var("HarvesterOfSouls", "range", is_constant=True) or 3)   # GetNumberConstant(0x16)
        ectx = ExecutionContext(state=state, rng=state.rng)
        harvester_of_souls_tree(n_hits, range_r).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)  # MAIN = feuille Target()
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]   # cibles splash != cible principale
        return {"ability": "HarvesterOfSouls", "caster": caster_id, "target": target_id,
                "hits": n_hits, "main_attack": main, "splash": splash, "dsl": True}


# ============================ EmpyricAmbush (1232, eldarLhykhis) ================================ #

EMPYRIC_AMBUSH_CONFIG = "EmpyricAmbush"                     # la cle gameconfig de l'ability 1232
EMPYRIC_AMBUSH_EFFECT = int(EffectType.EmpyricAmbush)       # 0x62a = 1578, la MARQUE posee sur la cible
UTILITY_TYPE_TILE = int(UtilityType.Tile)                   # le litteral 7 du call-site, PAR MEMBRE
# `attackRangeType` de la config 1232 = « Melee » -> `is_melee=True` (le volet PERCAGE lit l'arme melee).
EMPYRIC_AMBUSH_IS_MELEE = True


def empyric_ambush_profile() -> str:
    """`IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile` ->
    `IdunBattle.Configuration.AbilityConfiguration$$GetDamageProfile(config@+0x60)` : la constante
    `damageProfile` de la config 1232, RELUE du gameconfig (= « Eviscerate »), jamais codee en dur.
    C'est la MEME lecture que la face PREDICTION (`entities/abilities/active_ability.py` :
    `prof = (self.config.constants or {}).get("damageProfile")`). Config sans la cle -> `""`, ce que le
    natif rend comme `Nullable` VIDE (`GetValueOrDefault(-1)`) et que le port resout en repli d'arme."""
    import gameconfig as GC
    consts = (GC.ability(EMPYRIC_AMBUSH_CONFIG) or {}).get("constants") or {}
    return str(consts.get("damageProfile") or "")


def empyric_ambush_landing_tiles():
    """Chaine de TUILES d'`EmpyricAmbushAbility$$ExecuteBehaviour` (cf. docstring de module) :

        First( SortTilesByUtility( Randomize( CanAddUnit(AdjacentTiles(Target@+0x60))
                                              op_Subtraction <DSLSelectors+0x50 = CasterTile> ),
                                   Caster@+0x48, 7 = Tile ), 1 )

    Rend une liste de 0/1 **id d'entite-tuile**. `CasterTile(as_ids=True)` : les deux operandes de
    l'`op_Subtraction` doivent vivre dans le MEME domaine (le natif compare des references d'entite-tuile) --
    a defaut la soustraction ne retranche RIEN, silencieusement.

    Ce n'est PAS un collapse : le noeud est passe TEL QUEL a `FlyUnit`, qui ne l'evalue qu'a son `execute`.
    C'est la que les `len(pool)` tirages de `Randomize` sont consommes, donc AVANT ceux de la salve."""
    tiles = Sub(CanAddUnit(AdjacentTiles(Target())), CasterTile(as_ids=True))
    return First(SortTilesByUtility(Randomize(tiles), unit_sel=Caster(),
                                    utility_type=UTILITY_TYPE_TILE))


def empyric_ambush_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.EmpyricAmbushAbility$$ExecuteBehaviour`
    (MIRROR du DECOMPILE ; cf. docstring de module) :

        FlyUnit(Caster@+0x48, empyric_ambush_landing_tiles())
      & If( OwnerIsAlive,   AttackWithAttackDamage(Target@+0x60, config 1232, profil/coups CONFIG)
                          & AddEffect(1578, source = Owner@+0x30, targets = Target@+0x60, 1 TOUR) )

    `damageProfile` = `AActiveAbility$$GetDamageProfile` -> `AbilityConfiguration$$GetDamageProfile` = la
    cle `damageProfile` du gameconfig (LUE, jamais codee en dur). `hits` = defaut du port
    (`hits_key="nrOfHits"`) == `Get(AActiveAbility$$GetHits)` = `GetNumberConstant(0x2f)`.
    `native_factory="attack"` : le call-site vise `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`
    (famille ATTACK, 2 tirages/coup a cc=0), jamais `AttackWithAbilityDamage`.
    `duration_turns=1` : le natif passe `<DSLFormulas+0x20>` = `Direct(1)`, un nombre de TOURS deja resolu
    (PAS un `TurnsFromRounds`), cf. `entities/effects/loki/empyric_ambush.py`."""
    ability_type = int(ActiveAbilityType.EmpyricAmbush)      # AbilityOrEffect(this+0x10), threade after-hit
    attack = AttackWithAttackDamage(Target(), EMPYRIC_AMBUSH_CONFIG, empyric_ambush_profile(),
                                    is_melee=EMPYRIC_AMBUSH_IS_MELEE,
                                    native_factory="attack", ability_type=ability_type)
    mark = AddEffect(EMPYRIC_AMBUSH_EFFECT, EffectType.EmpyricAmbush.name, Target(),
                     duration_turns=1, source_ref=Owner())  # source = Owner@+0x30, cible = Target@+0x60
    return op_and(FlyUnit(Caster(), empyric_ambush_landing_tiles()),
                  If(OwnerIsAlive(), op_and(attack, mark)))  # `<DSLTriggers+0x20>`, SANS operande


class EmpyricAmbushAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.EmpyricAmbushAbility$$ExecuteBehaviour` (id **1232**,
    `eldarLhykhis` « Lhykhis », Aeldari) — MIRROR du DECOMPILE, arbre DSL (`empyric_ambush_tree`).

    Lhykhis VOLE sur la meilleure tuile libre adjacente a sa cible (ex aequo departages au hasard), puis --
    SI elle a survecu au vol -- la frappe (`nrOfHits` coups melee `damageProfile` de la config) et pose sur
    elle la marque `EmpyricAmbush` (1578) pour UN tour. L'effet et son gate etaient deja portes (#589-r1-r1) ;
    c'est la POSE qui manquait, donc l'effet n'arrivait dans l'etat du port QUE par la capture live."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.EmpyricAmbush)      # 1232 = 0x4d0
    ABILITY_ID = EMPYRIC_AMBUSH_CONFIG

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.EmpyricAmbushAbility$$.ctor` -- FORME
    # « FLAGS DIRECTS », surcharge TRANCHEE PAR SES XREFS ENTRANTES : le call-site `...$$.ctor+0x9d` vise
    # la surcharge a 7 parametres `(isSelfCasting, range, forceMeleeTarget, rules,
    # getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)`, celle qui ECRIT `rules` TEL QUEL dans
    # `options+0x28` -- AUCUN preset, donc AUCUN `|` a appliquer :
    #   TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x48, 1, 0x6004020, 0, 0)
    #     isSelfCasting    = 0
    #     range            = `TargetingRange` statics+0x48 = RANGE_WHOLE_BOARD (`useWholeBoard`)
    #     forceMeleeTarget = 1 = RangedBool.False
    #     rules            = 0x6004020
    # puis `AActiveAbility..ctor(this, &opts, 0)` -> `AbilityAttackType = 0 = DirectTargetAttack`
    # (transcrit dans `abilities/attack_type.py`, cf. la regle du meme commit).
    # Decomposition EXHAUSTIVE de 0x6004020, somme exacte, aucun bit residuel :
    #     0x20       (bit 5)  TargetHasFreeAdjacentTile -> la cible doit avoir >= 1 tuile LIBRE au contact.
    #                C'est le pendant DECISION exact du `CanAddUnit(AdjacentTiles(Target))` du behaviour :
    #                sans tuile libre autour de la cible, le `FlyUnit` n'aurait nulle part ou poser Lhykhis.
    #     0x4000     (bit 14) TargetIsEnemy
    #     0x6000000  (25|26)  AllowObscuredTarget (composite declare par l'enum natif)
    # `UseWholeBoard` -> le volet PORTEE generique ne teste RIEN : Lhykhis se teleporte, la distance ne la
    # borne pas (i2 ne mentionne aucune portee). Aucun `GetDynamicInvalid*Reason` natif (les deux delegues
    # sont passes a 0) -> le defaut du port est le mirror EXACT, pas une degradation.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetHasFreeAdjacentTile
        | TR.TargetIsEnemy
        | TR.AllowObscuredTarget),
        self_cast=False, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        empyric_ambush_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        fly = next((p for n, p in ectx.emitted if n == "FlyUnit"), None)
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        mark = next((p for n, p in ectx.emitted if n == "AddEffect"), None)
        return {"ability": EMPYRIC_AMBUSH_CONFIG, "caster": caster_id, "target": target_id,
                "move": fly, "attack": (atk or {}).get("attack"), "mark": mark, "dsl": True,
                "emitted": [n for n, _ in ectx.emitted]}


# ====================== SilentDeath (1068, eldarJainZar) -- #497 ================================ #

SILENT_DEATH_ID = "SilentDeath"                             # la cle gameconfig de l'ability 1068
#: `attackRangeType` de la config 1068 = « Melee » -> `is_melee=True` (le volet PERCAGE lit l'arme melee).
SILENT_DEATH_IS_MELEE = True
#: `DSLBehaviors$$Group(..., groupType = 0x1d)` -- membre LU dans `frida/enums.tsv` du build, pas devine.
SILENT_DEATH_GROUP = GroupType.DamageChain                  # 0x1d = 29


def silent_death_profile() -> str:
    """`IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile` ->
    `IdunBattle.Configuration.AbilityConfiguration$$GetDamageProfile(config@+0x60)` : la constante
    `damageProfile` de la config 1068, RELUE du gameconfig (= « Piercing »), jamais codee en dur.
    Config sans la cle -> `""`, ce que le natif rend comme `Nullable` VIDE et que le port resout en
    repli d'arme. MEME lecture que `empyric_ambush_profile` ci-dessus."""
    import gameconfig as GC
    consts = (GC.ability(SILENT_DEATH_ID) or {}).get("constants") or {}
    return str(consts.get("damageProfile") or "")


def silent_death_num_targets() -> int:
    """`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(config@+0x60, 0x11)` =
    `AbilityConstantType.nrOfTargets` -- la BORNE de la boucle qui construit la chaine (= 3 sur 1068).

    C'est un nombre de maillons ADDITIONNELS : le natif attaque la cible primaire AVANT d'entrer dans
    la boucle, donc le cardinal maximal frappe est `1 + nrOfTargets`. Constante absente -> 0 (le natif
    `GetNumberConstant` d'un index manquant rend 0, pas 1) = la cible primaire seule."""
    return int(ability_var(SILENT_DEATH_ID, "nrOfTargets", is_constant=True) or 0)


def _silent_death_attack(target_sel):
    """`<>c__DisplayClass1_0$$<ExecuteBehaviour>b__0(cible)` -- LA feuille, UNIQUE cote natif et
    re-instanciee par maillon cote port (le natif n'a qu'UNE methode, invoquee avec des `cible`
    differentes) :

        AttackWithAttackDamage( caster = <DSLSelectors+0x48>, target = cible,
                                amount        = MinMaxDamage(abilityState, isPrediction: 0),
                                damageProfile = Nullable(GetDamageProfile()),
                                hits          = Get(GetNumberConstant(0x2f = nrOfHits)),
                                abilityOrEffect = AbilityOrEffect(this+0x10),
                                options       = <Nullable VIDE> )

    Mode BORNES (`min_key`/`max_key`/`hits_key` par defaut = `minDmg`/`maxDmg`/`nrOfHits`), aucun
    override de degat ni de coups. `native_factory="attack"` : le call-site vise bien
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (famille ATTACK, 2 tirages/coup a
    cc=0), jamais `AttackWithAbilityDamage`. `multi=True` : le natif passe TOUJOURS par
    `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` (resolution de LISTE + `OrderBy`), y
    compris quand le selecteur est un singleton -- et le maillon d'une chaine epuisee resout un
    ensemble VIDE, que le mode multi traite en no-op exact (aucune attaque emise)."""
    return AttackWithAttackDamage(target_sel, SILENT_DEATH_ID, silent_death_profile(),
                                  is_melee=SILENT_DEATH_IS_MELEE, multi=True,
                                  native_factory="attack",             # DSLBehaviors$$AttackWithAttackDamage
                                  ability_type=int(ActiveAbilityType.SilentDeath))


def silent_death_tree(n_targets: int) -> Group:
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.SilentDeathAbility$$ExecuteBehaviour`
    (MIRROR du DECOMPILE ; la boucle C# native est deroulee ICI, comme elle l'est chez le natif -- ce
    n'est pas un raccourci de port, c'est la CONSTRUCTION du behaviour) :

        ennemis = Cache( Enemies( AllAliveUnits() ) )   # Enemies(<dsl>+0x48, <dsl>+0x20, 3)
        prev    = Target()                                        # <DSLSelectors+0x60>
        vus     = [ prev ]
        b       = Attack(prev)                                    # Nothing() + b__0(Target)
        pour i dans [0, n_targets) :
            pool = And( AdjacentUnits(prev), ennemis )            # AdjacentUnits(prev,1,3) & <cache>
            pour s dans vus : pool = Sub(pool, s)                 # foreach : pool = pool - s
            pris = Cache( PickRandomly(pool, 1) )                 # PickRandomly(pool,1,0,MAXINT,0)
            b    = op_add( b, Attack(pris) )
            vus.append(pris) ; prev = pris
        Group( op_and( SetCache(ennemis), b ), DamageChain, None() )

    `Nothing()` (`IdunBattleLogic.Entities.DSLBehaviors$$Nothing`) = feuille NEUTRE en tete du
    `op_Addition` : aucun etat, aucun tirage -> NON materialisee (meme convention que
    `early_warning_override_tree`, `runner/abilities/tau.py`). L'arbre porte demarre a la 1re attaque.

    `AdjacentUnits(prev)` (radius 1 par defaut) mirrore `DSLSelectors$$AdjacentUnits(prev, unique: 1,
    selectionType: 3)` = `Units(AdjacentTiles(prev), 1, 3) op_Subtraction prev`. Le volet ALIVE de
    `UnitSelectionType.OnlyAliveAndTargetable` (3) est deja porte PAR `_within` (`dsl/base.py`, filtre
    `_is_alive`, mirror de `UnitsOnTilesSelector` : un mort n'est plus sur sa tuile, #57m) -- d'ou
    l'absence de wrapper `Alive` ICI, qui serait redondant. RESIDU NOMME : le volet « Targetable »
    (deep strike / `TeleportingIn`) n'est modelise nulle part cote port.

    `Cache` porte le `matchAbilityEntities = 1` du natif en mode SLOT UNIQUE : tout l'arbre s'evalue
    sous LE MEME `AbilityEntities` (aucun `Foreach` au-dessus), donc les deux modes coincident. La
    memoisation est OBSERVABLE et REQUISE : sans elle, le `op_Subtraction` des iterations suivantes
    re-tirerait le `PickRandomly` et desalignerait tout le flux rng.

    L'ARBRE EST RECONSTRUIT PAR CAST (les `Cache` sont a etat) -- appeler cette fonction une fois par
    `execute_behaviour`, jamais la memoiser au niveau module."""
    # #585-r1 : `Enemies(gs, gs@0x48, gs@0x20, 3)` puis `AdjacentUnits(gs, prev, unique: 1, 3)` --
    # littéraux LUS dans `...SilentDeathAbility$$ExecuteBehaviour`.
    ennemis = Cache(Enemies(AllAliveUnits(), selection_type=SELECTION))   # DSLSelectors$$Cache(Enemies(...), 1)
    prev = Target()                                         # <DSLSelectors+0x60>
    vus = [prev]                                            # List<TargetsSelector>, primaire en tete
    node = _silent_death_attack(prev)                       # Nothing() + b__0(Target) -> la 1re attaque
    for _ in range(max(0, int(n_targets))):
        pool = And(AdjacentUnits(prev, selection_type=SELECTION), ennemis)   # & <cache ennemis> (fige AVANT le 1er coup)
        for seen in vus:                                    # foreach s in vus : pool = pool - s
            pool = Sub(pool, seen)
        pris = Cache(PickRandomly(pool, 1))                 # 1 tirage rng des que le pool est non vide
        node = op_add(node, _silent_death_attack(pris))
        vus.append(pris)
        prev = pris                                         # le maillon SUIVANT part d'ICI
    # `groupEntity` = `DSLSelectors$$None()` : le port n'a pas d'homonyme `None` -- `Null` (« entite
    # NULLE ») est le plus proche, et c'est une METADONNEE de vue que `Group` n'evalue jamais.
    return Group(op_and(SetCache(ennemis), node),
                 group_id=int(SILENT_DEATH_GROUP), targets_sel=Null())


class SilentDeathAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SilentDeathAbility$$ExecuteBehaviour` (id
    **1068**, `eldarJainZar` « Jain Zar », Aeldari) -- MIRROR du DECOMPILE, arbre DSL
    (`silent_death_tree`).

    Jain Zar lance le Silent Death sur un ennemi ADJACENT (`nrOfHits` = 3 coups `Piercing` melee),
    puis l'arme REBONDIT jusqu'a `nrOfTargets` = 3 fois : chaque rebond pique AU HASARD un ennemi
    encore vivant, adjacent au maillon PRECEDENT, jamais deja frappe. Jusqu'a 4 unites, 3 coups
    chacune. La chaine s'arrete d'elle-meme des qu'un maillon n'a aucun voisin eligible (le
    `PickRandomly` rend un ensemble vide -> la feuille est un no-op, et les maillons suivants aussi
    puisqu'ils partent de ce vide).

    Le behaviour EST l'arbre DSL : les feuilles `AttackWithAttackDamage` (mode bornes) emettent la
    MEME Operation d'attaque d'ability que le pipeline combat porte -> bit-exact BY CONSTRUCTION vs
    une sequence directe sous meme rng. ORDRE RNG, et il est CONTRAINT : `SetCache` (0 tirage), puis
    pour chaque maillon `k` -- les 3 coups du maillon `k`, PUIS le tirage du maillon `k+1`. Le pick
    vient APRES les degats parce que le selecteur est LAZY et n'est evalue qu'a l'execution de SA
    feuille.

    Retour : {ability, caster, target, chain, hits, max_targets, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SilentDeath)        # 1068 = 0x42c
    ABILITY_ID = SILENT_DEATH_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET STATIQUE COPIE** (la 3e des
    # trois formes) : `...SilentDeathAbility$$.ctor` n'appelle AUCUN
    # `IdunBattle.Core.Services.TargetingOptions$$.ctor`. Il recopie les 0x40 octets du champ STATIQUE
    # de `TargetingOptions` a l'offset **`+0x40`** du bloc `<class>+0xb8`, puis :
    #     AActiveAbility..ctor(this, &opts, 0)   # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
    # Aucun litteral de masque n'est visible dans le ctor : le masque EFFECTIF est la constante ecrite
    # par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` = `*(statics+0x68)`.
    #
    # Le preset lu EN ENTIER (bloc `statics+0x40` du `cctor`), pas seulement son champ `Rules` :
    #     <preset>+0x00 = *(statics+0x40) = 0                  -> isSelfCasting = false
    #     <preset>+0x08 = copie de `TargetingRange statics+0x30` -> **RANGE_ADJACENT**
    #                     (`cctor` : `+0x30 = 0` onlyAdjacent, `+0x38 = Nullable(1)`)
    #     <preset>+0x20 = *(statics+0x60) = 1                  -> forceMeleeTarget = RangedBool.False
    #     <preset>+0x28 = *(statics+0x68) = 0x4000             -> Rules = `TargetIsEnemy` SEUL
    # C'est le preset PARTAGE par 1053/1064/1108/1129/1132/1165/1191/1195 et par
    # `DiveAttackAbilityBase$$.ctor` -- mais il a ete RELU sur CE ctor, pas recopie d'une voisine
    # (mesure de la vague #491 : deux abilities a masque identique peuvent differer sur
    # `forceMeleeTarget`, et ce seul champ change le regime de portee).
    #
    # AUCUN `TargetMatchesDynamicRule` (0x2) ni `CasterMatchesDynamicRule` (0x4) -> les deux
    # `GetDynamicInvalid*Reason` de la base (defaut 0) sont le mirror EXACT, pas une degradation.
    # Cette entree MIGRE depuis `TARGETING_OPTIONS_UNPORTED` (`abilities/targeting.py`) : contrat de
    # disjonction -- une ability portee porte son masque sur SA classe.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False,
                                         range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        n_targets = silent_death_num_targets()               # GetNumberConstant(0x11 = nrOfTargets)
        ectx = ExecutionContext(state=state, rng=state.rng)
        silent_death_tree(n_targets).execute(                # arbre NEUF par cast (les `Cache` ont un etat)
            entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        # ORDRE D'EMISSION = ordre de la chaine (le 1er est la cible primaire, cf. l'arbre) : on le
        # conserve tel quel, c'est lui l'observable a confronter au natif.
        chain = [{"target": p.get("target"), "attack": p.get("attack")} for p in atks]
        return {"ability": SILENT_DEATH_ID, "caster": caster_id, "target": target_id,
                "chain": chain, "hits": len(chain), "max_targets": 1 + int(n_targets), "dsl": True}

# =================================================================================================
# Loki_SwoopingHawk (1064, `eldarAutarch` « Aethana ») -- #502, base partagee depuis #507
# =================================================================================================
# Classe native `IdunBattleLogic.Entities.Abilities.Active.Loki.SwoopingHawkAbility`, dont le corps
# ENTIER est `return DiveAttackAbilityBase$$.ctor(this);` : TOUTE la mecanique vit sur la BASE
# `IdunBattleLogic.Entities.Abilities.Active.Loki.DiveAttackAbilityBase`, portee dans
# `engine/runner/abilities/loki/dive_attack.py` (namespace natif `...Active.Loki`) -- decompile
# complet, les trois lectures qui le tranchent et la preuve RUNTIME du partage : dans SON en-tete.
# L'autre heritiere de cette base est `SlashingDive` (1091), portee en #507 sur `thousandsons.py`.

SWOOPING_HAWK_ID = "Loki_SwoopingHawk"                       # cle gameconfig de l'ability 1064


def swooping_hawk_profile() -> str:
    """`AActiveAbility$$GetDamageProfile` pour 1064 (= « Piercing » au gameconfig courant).

    Accesseur d'ABILITY au-dessus du foyer de la base (`dive_attack_profile`) : le profil est l'un
    des trois axes que `DiveAttackAbilityBase` ne fige PAS -- 1091, meme code natif, vaut
    « Power ». Relire par ability, jamais recopier d'une soeur."""
    return dive_attack_profile(SWOOPING_HAWK_ID)


class SwoopingHawkAbility(DiveAttackAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.SwoopingHawkAbility` (id **1064**,
    `eldarAutarch` « Aethana », Aeldari) -- MIRROR du DECOMPILE.

    Aethana plonge sur un ennemi ADJACENT et balaie la ligne : la cible prend `dmg[0]`, l'unite un
    hex derriere `dmg[1]`, celle deux hexes derriere `dmg[2]` -- un coup `Piercing` chacune
    (`nrOfHits` = 1). Elle atterrit ensuite dans l'hex juste derriere la DERNIERE cible touchee, ou,
    s'il est occupe, sur la tuile libre la plus proche de celui-ci.

    La classe native n'a QUE son ctor : toute la mecanique est heritee de `DiveAttackAbilityBase`,
    et ce mirror n'ajoute donc rien d'autre que l'identite et les deux donnees du registre."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Loki_SwoopingHawk)   # 1064 = 0x428
    ABILITY_ID = SWOOPING_HAWK_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET STATIQUE COPIE** : ni
    # `SwoopingHawkAbility$$.ctor` (corps entier = `return DiveAttackAbilityBase$$.ctor(this);`) ni
    # `DiveAttackAbilityBase$$.ctor` n'appellent `IdunBattle.Core.Services.TargetingOptions$$.ctor`.
    # La base recopie les 0x40 octets du champ STATIQUE de `TargetingOptions` a l'offset **`+0x40`**
    # du bloc `<class>+0xb8`, puis :
    #     AActiveAbility..ctor(this, &opts, 0)   # 3e arg = 0 = AbilityAttackType.DirectTargetAttack
    # Aucun litteral de masque n'est visible : le masque EFFECTIF est la constante ecrite par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` = `*(statics+0x68)`.
    # Le preset lu EN ENTIER (bloc `statics+0x40`), pas seulement son champ `Rules` :
    #     <preset>+0x00 = *(statics+0x40) = 0                  -> isSelfCasting = false
    #     <preset>+0x08 = copie de `TargetingRange statics+0x30` -> **RANGE_ADJACENT**
    #     <preset>+0x20 = *(statics+0x60) = 1                  -> forceMeleeTarget = RangedBool.False
    #     <preset>+0x28 = *(statics+0x68) = 0x4000             -> Rules = `TargetIsEnemy` SEUL
    # C'est le preset `+0x40`, PARTAGE avec 1053/1068/1108/1129/1132/1165/1191/1195 -- mais il a ete
    # RELU sur CE ctor, pas recopie d'une voisine (deux abilities a masque identique peuvent differer
    # sur `forceMeleeTarget`, et ce seul champ change le regime de portee).
    # AUCUN `TargetMatchesDynamicRule` (0x2) ni `CasterMatchesDynamicRule` (0x4) -> pas de regle
    # dynamique, et l'absence de 1064 dans `DYNAMIC_TARGET_RULE_UNPORTED` est donc EXACTE.
    # Cette entree MIGRE depuis `TARGETING_OPTIONS_UNPORTED` (`abilities/targeting.py`) : contrat de
    # disjonction -- une ability portee porte son masque sur SA classe.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False,
                                         range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)


# ================== FireAndReposition (eldarRanger « Calandis », actif 1063) -- #567 ==============
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.FireAndRepositionAbility$$ExecuteBehaviour`
# (MIRROR du DECOMPILE, build `rnca9r7q6c`), remis en C# :
#
#     atk    = DSLBehaviors$$UseActiveAbility(
#                  subject     = Caster@DSLSelectors+0x48,
#                  targets     = Target@DSLSelectors+0x60,
#                  abilityType = DSLSelectors$$UnitNormalAttackType(Caster@+0x48),
#                  source      = Nullable(AbilityOrEffect$$op_Implicit(this)),
#                  <opts>, <opts> )
#     reset  = DSLBehaviors$$ResetMovement( targets = Owner@DSLSelectors+0x30 )
#     eff    = DSLBehaviors$$AddEffect(
#                  effectType   = 0x456,                      # EffectType.FireAndReposition_ReduceDmg
#                  abilityState = AActiveAbility$$get_AbilityStateReference(this),
#                  source       = Caster@DSLSelectors+0x48,
#                  targets      = Caster@DSLSelectors+0x48,   # SUR ELLE-MEME
#                  turns        = DSLFormulas$$TurnsFromRounds(1) )
#     return AActiveAbility$$Execute(entities, this, op_Addition(op_Addition(atk, reset), eff))
#
# LA CATEGORIE ANNONCEE ETAIT FAUSSE, ET LE COMPTE DE MECANIQUES AUSSI.
# `docs/rl/combat-ability-coverage.md` classait 1063 en EFFECT/BUFF -- colonne derivee du
# `damageProfile` de l'ARME du porteur, pas du behaviour. Le decompile en porte **TROIS**, et l'i2
# s'y apparie un pour un :
#   << May move as normal and attack. >>                          -> [1] `UseActiveAbility`
#   << After attacking, she may make one more normal movement. >> -> [2] `ResetMovement`
#   << In the following enemy turn, she takes -{dmgReduction}
#      Damage from ranged attacks. >>                             -> [3] `AddEffect(1110)`
#   << Can only be used if Calandis has a target in range. >>     -> le masque de ciblage
#
# LE CAST FRAPPE, mais par l'attaque NORMALE de l'unite -- pas par une attaque d'ability. La config
# le confirme independamment : `abilities.FireAndReposition` n'a NI `minDmg`/`maxDmg`, NI `nrOfHits`,
# NI `damageProfile`, NI constante `range` -- **une seule variable, `dmgReduction`** (65 niveaux,
# 30 -> 2183, `variablesAffectedByRarityBonus`). Meme configuration que `HolyDuel` (1050) et
# `Drachnyen` (1029). Le `-2183` de l'i2 n'est donc PAS un degat : c'est la magnitude de [3].
#
# ORDRE LU, PAS DEVINE -- les deux `AbilityBehaviour$$op_Addition` du decompile s'emboitent
# `(atk + reset) + eff` : l'attaque part D'ABORD, le mouvement est rendu ENSUITE, l'effet pose EN
# DERNIER. Contraste avec `StrikeFromTheShadows` (1225), dont le natif emboite `(atk + eff) + reset`
# -- deux abilities du meme patron a trois feuilles, deux ordres DIFFERENTS : il se lit, il ne se
# recopie pas. DETERMINISTE hors le degat : ni `ResetMovement` ni `AddEffect` ne tirent -> le flux
# `state.rng` est celui d'une attaque normale nue, et permuter les trois feuilles ne le decalerait
# PAS. L'ordre reste LOAD-BEARING sur l'ETAT (cf. `test_567_fire_and_reposition_offline.py`,
# garde d'ORDRE) -- un test « ca fire » ne le verrait pas.
#
# ⚠ `ResetMovement` ne rend PAS l'active : `UnitFlag.ActiveAbilityUsed(2)` n'est pas dans les quatre
# flags que retire `ResetMovementBehavior$$Execute` (cf. `_RESET_MOVEMENT_FLAGS`). Calandis
# re-bouge et peut attaquer normalement, elle ne peut pas re-caster.
# ================================================================================================ #

FIRE_AND_REPOSITION_ID = "FireAndReposition"                 # cle gameconfig de l'ability 1063
FIRE_AND_REPOSITION_REDUCE_DMG = int(EffectType.FireAndReposition_ReduceDmg)   # 0x456 = 1110


def fire_and_reposition_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.FireAndRepositionAbility$$ExecuteBehaviour`
    (MIRROR 1:1, cf. le bloc de commentaire ci-dessus) :

        op_Addition( op_Addition( UseActiveAbility(Caster, Target, UnitNormalAttackType(Caster)),
                                  ResetMovement(Owner) ),
                     AddEffect(1110, source=Caster, targets=Caster, TurnsFromRounds(1)) )

    - `UseActiveAbility(Caster(), Target())` = la feuille deja portee, specialisee au dispatch
      d'ATTAQUE NORMALE (`UnitNormalAttackType(Caster@+0x48)` -> `AttackDamageOperation.execute`,
      resolveur d'arme par distance). MEME forme que `HolyDuel` (1050) et `Drachnyen` (1029).
    - `ResetMovement(Owner())` = le selecteur `DSLSelectors+0x30`, PAS `+0x48` : le natif ecrit bien
      l'OWNER ici et le CASTER pour les deux autres feuilles. Les deux coincident pour une active,
      mais on transcrit ce qui est ecrit (meme lecture que `StrikeFromTheShadows`).
    - `AddEffect(..., Caster(), source_ref=Caster())` : la cible EST le caster (`targets` et `source`
      lisent tous deux `DSLSelectors+0x48`) -- l'effet est un buff DEFENSIF sur soi, pas un debuff.
    - `duration_rounds=1` = `TurnsFromRounds(1)` NU. ⚠ Ce n'est PAS le `Sum(TurnsFromRounds(1),
      <DSLFormulas+0x20 = Direct(1)>)` de `StrikeFromTheShadows` : le decompile de 1063 passe le
      resultat de `TurnsFromRounds` DIRECTEMENT en 6e argument d'`AddEffect`, sans `Sum`. Ecrire
      `turns_until_end_of_current_players_next_turn` ici depasserait d'un tour.
    - `scale_from_source=True` = le 3e argument natif `abilityState`
      (`AActiveAbility$$get_AbilityStateReference(this)`), que l'entite-effet BAKE et que relit
      `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState`. Il est LOAD-BEARING ici :
      `FireAndRepositionReduceDmgEffect` indexe sa magnitude sur le niveau de l'ability **ACTIVE**
      (`ConfigVar(0x12 = dmgReduction)`, cf. `entities/effects/loki/damage_reduction.py`), et c'est
      exactement le regime qui a refute le port initial de l'effet (#366-r1 : natif 716, port 2992,
      parce que le niveau PASSIF avait ete lu)."""
    atk = UseActiveAbility(Caster(), Target())          # UnitNormalAttackType(Caster@+0x48)
    reset = ResetMovement(Owner())                      # targets = Owner@+0x30
    eff = AddEffect(FIRE_AND_REPOSITION_REDUCE_DMG, EffectType.FireAndReposition_ReduceDmg.name,
                    Caster(), source_ref=Caster(),      # targets ET source = Caster@+0x48
                    duration_rounds=1,                  # `TurnsFromRounds(1)` NU (pas de `Sum`)
                    scale_from_source=True)             # 3e argument natif : `abilityState`
    return op_add(op_add(atk, reset), eff)


class FireAndRepositionAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.FireAndRepositionAbility$$ExecuteBehaviour`
    (id **1063**, `eldarRanger` « Calandis », Aeldari) -- arbre DSL `fire_and_reposition_tree`.

    CE port est la face EXECUTION, qui etait un NO-OP SILENCIEUX (1063 absente d'`ABILITY_CLASSES` :
    `AbilityHandler.visit_ActiveAbilityMessage` l'ignorait -- 0 degat, 0 mouvement rendu, 0 effet,
    aucune erreur). La DECISION pouvait la choisir alors que l'EXECUTION ne faisait rien.

    KIT (gameconfig, ZERO hardcode) : `attackRangeType = Normal`, variables = `dmgReduction` SEULE
    (`variablesAffectedByRarityBonus`). AUCUNE variable de degat propre, aucun `nrOfHits`, aucun
    `damageProfile`, aucune constante -> le cast n'a pas d'attaque d'ability, il DISPATCHE l'attaque
    NORMALE de l'unite.

    OBSERVABLE porte, les TROIS volets dans l'ordre du decompile : (1) une attaque NORMALE de
    Calandis sur la cible du message ; (2) `ResetMovement(Owner)` -- elle RECUPERE son deplacement
    et son activation, PAS son active ; (3) l'effet 1110 `FireAndReposition_ReduceDmg` pose SUR
    ELLE-MEME pour 1 round, dont le port est deja livre et valide live (#366-r1,
    `entities/effects/loki/damage_reduction.py::FireAndRepositionReduceDmgEffect`).

    Face DECISION **NON portee** : `IdunBattle.AI.Playbook.Loki.FireAndRepositionPlaybook` (un
    `ComparablePlaybook<T>` a `0x427`, avec `GetTileUtility` / `GetAverageDistance`) n'a aucun
    equivalent dans `engine/playbook/` -- residu `#567-r1`.

    Diag : {ability, caster, target, attack, reset, reset_reopened, effect_placed}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.FireAndReposition)   # 1063 = 0x427
    ABILITY_ID = FIRE_AND_REPOSITION_ID

    # GATE DE CIBLE (#115) + PORTEE (#241) -- forme de ctor = **PRESET STATIQUE COPIE** :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.FireAndRepositionAbility$$.ctor` n'appelle
    # AUCUN `TargetingOptions$$.ctor` -- il recopie les 0x40 octets du champ STATIQUE de
    # `TargetingOptions` a l'offset **`+0x00`** du bloc `<class>+0xb8` (le TOUT PREMIER preset), puis
    #     AActiveAbility..ctor(this, &opts, 2)   # 3e arg = 2 = AbilityAttackType.Others
    # Le preset lu EN ENTIER dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
    #     <preset>+0x00 = 0                                     -> isSelfCasting = false
    #     <preset>+0x08 = copie de `TargetingRange statics+0x00` -> **RANGE_ADJACENT_IF_MELEE_CASTER**
    #     <preset>+0x20 = 2                                     -> forceMeleeTarget = IfRangedCaster
    #     <preset>+0x28 = 0x4002                                -> Rules = TargetMatchesDynamicRule
    #                                                                     | TargetIsEnemy
    # ⚠ `forceMeleeTarget = 2` (`RangedBool.IfRangedCaster`) : 1063 est la SEULE du lot de
    # `TARGETING_OPTIONS_UNPORTED` dans ce regime -- recopier le `1` d'une voisine serait faux.
    # ⚠ Le `range` du preset `+0x00` est `RANGE_ADJACENT_IF_MELEE_CASTER` (`onlyAdjacent =
    # IfNotRangedCaster`), PAS `RANGE_FROM_CONFIG` : coherent avec une config 1063 qui ne porte
    # AUCUNE constante `range` -- il n'y en aurait rien a lire. La portee effective est celle de
    # l'ARME de Calandis, ce que dit l'i2 (« if Calandis has a target in range »).
    # Cette entree MIGRE depuis `TARGETING_OPTIONS_UNPORTED` (`abilities/targeting.py`) : contrat de
    # disjonction -- une ability portee porte son masque sur SA classe.
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy),   # `<preset +0x00>+0x28` = 0x4002
        self_cast=False, range=RANGE_ADJACENT_IF_MELEE_CASTER,
        force_melee_target=RANGED_BOOL_IF_RANGED_CASTER)             # `<preset +0x00>+0x20` = 2

    # `AbilityAttackType` = 3e argument d'`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` = le
    # litteral **`2`** (`Others`), LU au ctor -> transcrit dans la table `ABILITY_ATTACK_TYPE`
    # (`abilities/attack_type.py`), qui est le registre de cette donnee. TRANSCRIT, jamais deduit :
    # le cast FRAPPE bel et bien (attaque normale), ce qui ferait ecrire `DirectTargetAttack` a
    # l'oeil -- exactement la meme configuration que `FoulInfusion` (1038) et `WallOfMirrors` (1186),
    # deux autres dispatcheurs d'attaque normale dont le litteral vaut aussi `2`.

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        fire_and_reposition_tree().execute(entities, ectx)
        atk = next((p for n, p in ectx.emitted if n == "UseActiveAbility"), None)
        rst = next((p for n, p in ectx.emitted if n == "ResetMovement"), None)
        eff = next((p for n, p in ectx.emitted if n == "AddEffect"), None)
        return {"ability": FIRE_AND_REPOSITION_ID, "caster": caster_id, "target": target_id,
                "attack": atk,
                "reset": (rst or {}).get("subject"),
                "reset_reopened": bool((rst or {}).get("reopened")),
                "effect_placed": bool((eff or {}).get("placed")),
                "dsl": True}


# ============ KissOfDeath (1108, eldarSmnHarlequin / eldarNpc3Harlequin) -- #940 ================= #
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.KissOfDeathAbility$$ExecuteBehaviour`
# (MIRROR du DECOMPILE, terme a terme, dans l'ordre des allocations) :
#
#     damageProfile = AActiveAbility$$GetDamageProfile(this)                      # "DirectDamage"
#     hitsF         = DSLFormulas$$Direct( AActiveAbility$$GetHits(this) )        # nrOfHits (0x2f)
#     dmgF          = DSLFormulas$$Direct( AbilityConfiguration$$GetVariableForLevel(
#                                              config, 0xb = dmg, abilityState, 0) )
#     maxTargetsF   = DSLFormulas$$ConfigVar( 0x0 = maxAdjacentTargets, abilityState, config )
#     chainOptions  = new <ChainBehaviourOptions> { +0x12 = 1 }   # +0x10 / +0x11 laisses a 0
#     jumpSel       = new Func<TargetsSelector, TargetsSelector>( this, <lambda> )
#
#     chain  = DSLBehaviors$$ChainAttackDamage(
#                  preselectedTargets = Target@<DSLSelectors+0x60>,
#                  jumpTargetSelector = jumpSel,
#                  maxTargets         = maxTargetsF,
#                  dmgAmount          = dmgF,
#                  damageProfileType  = damageProfile,
#                  hits               = hitsF,
#                  abilityType        = AbilityOrEffect$$op_Implicit(this),
#                  extraBehaviour     = null,
#                  maxTargetsExtra    = null,
#                  damageOptions      = <AttackDamageBehaviourOptions ZERO>,
#                  chainOptions       = chainOptions )
#
#     attacked = DSLSelectors$$UnitsAttackedThisTurn( Caster@<DSLSelectors+0x48> )
#     landA    = DSLSelectors$$CanAddUnit( AdjacentTiles( Last(attacked, 1, false) ) )
#                    op_Subtraction <DSLSelectors+0x50 = CasterTile>
#     landB    = DSLSelectors$$CanAddUnit( AdjacentTiles( AtIndex(attacked, 1) ) )
#                    op_Subtraction <DSLSelectors+0x50 = CasterTile>
#     landC    = DSLSelectors$$CanAddUnit( AdjacentTiles( Target@<DSLSelectors+0x60> ) )
#                    op_Subtraction <DSLSelectors+0x50 = CasterTile>
#     land     = DSLSelectors$$First(
#                    SortTilesByUtility( landA.Otherwise(landB).Otherwise(landC),
#                                        unit = Caster@+0x48, utilityType = 7 = Tile, parent = null ),
#                    amount = 1, ignoreForcedTargets = false )
#     fly      = DSLBehaviors$$FlyUnit( unit = Caster@+0x48, tiles = land )
#
#     addEff = DSLBehaviors$$AddEffect( 0x414 = EffectType.Untargetable,
#                                       abilityState = AActiveAbility$$get_AbilityStateReference(this),
#                                       source  = Caster@+0x48,
#                                       targets = Caster@+0x48,
#                                       options = <Nullable<AddEffectBehaviourOptions> VIDE> )
#     remEff = DSLBehaviors$$RemoveEffect( selector   = Caster@+0x48,
#                                          effectType = Nullable(0x414 Untargetable),
#                                          replaceableEffectType = null )
#
#     AActiveAbility$$ExecuteAtomic( this, ((addEff & chain) & fly) & remEff,
#                                    entities, GroupType 0x2a = Ability_AtomicGroup )
#
# i2 (`Abilities/KissOfDeath_CurrentLevelDescription`) : « The Harlequin Player DISAPPEARS and deals
# {nrOfHits}x {dmg} Direct Damage to an adjacent enemy, and up to {maxAdjacentTargets} additional
# enemies adjacent to A PREVIOUS target, then it REAPPEARS in a hex adjacent to the last target
# hit. » -- chacune des quatre propositions est l'un des quatre membres de l'`op_BitwiseAnd`.
#
# CINQ LECTURES QUE LE DECOMPILE IMPOSE, ET QU'AUCUNE TABLE NE DIT :
#
#  1. **L'ability FRAPPE, et l'audit ne le savait pas.** La colonne `DAMAGE(DirectDamage)` de
#     `combat-ability-coverage.md` derive du `damageProfile` de l'ARME du porteur, pas du behaviour
#     -- elle est VRAIE ici, mais par coincidence : le degat vient d'un `ChainAttackDamage` (famille
#     ATTACK -> `AttackDamageOperation`, donc crit/block/bouclier complets), pas d'une attaque
#     directe. Le profil, lui, est LU (`GetDamageProfile` -> constante `damageProfile` de la config).
#
#  2. **`dmgAmount` est un `Direct(GetVariableForLevel(dmg))`, PAS un `MinMaxDamage`.** La config
#     1108 n'a NI `minDmg` NI `maxDmg` : elle porte `dmg` (une variable indexee par niveau, dans
#     `variablesAffectedByRarityBonus`) et `maxAdjacentTargets`. Le mode BORNES de la feuille
#     d'attaque lirait donc deux cles ABSENTES -> 0 degat, silencieusement. D'ou le mode `amount` et
#     le passage du 4e argument de la factory, que `ChainAttackDamage` ignorait jusqu'ici (son unique
#     consommateur, `FuryOfTheAncients`, est en bornes).
#     `damageOptions` = 32 octets ZERO -> `amount_spread_pct = 0` : AUCUNE variance d'arme.
#
#  3. **`maxTargets` borne les SAUTS, pas le total.** Le compteur natif est un DELTA sur la liste
#     preselectionnee (`picked.Count - pres.Count < GetCurrentMaxTargets()`, cf. `chain.py`) : avec
#     `maxAdjacentTargets = 2` et UNE cible preselectionnee, ce sont **3 unites** frappees au plus --
#     ce que dit l'i2 (« an adjacent enemy, AND UP TO 2 ADDITIONAL »).
#
#  4. **`chainOptions+0x12 = 1`** = coup DIFFERE d'un cran : le maillon N+1 est choisi alors que le
#     maillon N est encore VIVANT. Une cible tuee ne coupe donc pas la chaine a l'endroit ou elle
#     tombe. Meme octet, meme valeur que les trois autres consommateurs de la famille.
#
#  5. **L'ATTERRISSAGE SE LIT APRES LA CHAINE, ET C'EST LA TOUTE LA SUBTILITE.** `UnitsAttackedThisTurn`
#     est l'`ActorStatisticsComponent+0x40` du CASTER -- un `OrderedSet` que CHAQUE maillon de la
#     chaine vient d'allonger, dans l'ordre des coups. `FlyUnit` n'evalue son selecteur de destination
#     qu'a son `execute`, donc APRES le `chain` dans la sequence `&` : `Last(attacked, 1)` est bien
#     « the last target hit ». Un port qui figerait ce champ au debut de l'arbre lirait une liste
#     VIDE et le Harlequin ne bougerait pas -- d'ou l'entree de `unitsAttackedThisTurn` dans
#     `_LIVE_KEYS` (`behaviours/context.py`) et le passage de `set` a `dict` ORDONNE (`components.py`).
#     Les DEUX replis suivent : `AtIndex(attacked, 1)` = la DEUXIEME unite frappee du tour (pas la
#     derniere), puis `Target@+0x60` = la cible designee. Chacun subit le meme
#     `CanAddUnit(AdjacentTiles(.)) - CasterTile`, et `Otherwise` ne bascule que sur un VIDE.
#
# ⚠ LE LAMBDA `jumpTargetSelector` N'EST DANS AUCUNE DES DEUX TABLES -- ATTRIBUTION ETAYEE, PAS LUE.
#   `KissOfDeathAbility` ne porte que DEUX methodes (`.ctor`, `ExecuteBehaviour`) dans
#   `frida/methods.tsv` comme dans `ghidra/functions.tsv`, et le voisinage du bloc `methodPointers`
#   (entre `KillMaimBurnAbility$$.ctor` et `LashOfTormentAbility$$ExecuteBehaviour`) ne contient rien
#   d'autre : son `<ExecuteBehaviour>b__N_0` a donc ete FONDU PAR L'ICF, comme le prevoit la regle
#   « l'ABSENCE d'une methode dans les tables ne prouve RIEN ». Le corps retenu est celui de
#   `IdunBattleLogic.Entities.Abilities.Active.Loki.StormOfWrathAbility$$u003CExecuteBehaviouru003Eb__1_0` :
#
#       lastTargets => DSLSelectors$$Enemies( of       = Caster@<DSLSelectors+0x48>,
#                                             entities = DSLSelectors$$AdjacentUnits(lastTargets,
#                                                            unique = 1, selectionType = 3),
#                                             selectionType = 3 )
#
#   TROIS arguments concordants, et aucune mesure ne les separe : (a) c'est la seule des cinq
#   lambdas `-> TargetsSelector` du binaire dont le corps ne porte AUCUN litteral propre ni bloc
#   d'init de metadata-usage -- donc le seul candidat que l'ICF PEUT fondre avec un homologue d'une
#   autre classe ; (b) sa semantique est mot pour mot celle de l'i2 (« additional ENEMIES ADJACENT
#   to a previous target ») ; (c) `KissOfDeath` et `StormOfWrath` partagent deja le pointeur de
#   classe des `chainOptions` (`DAT_183343388`) et celui du `Func<>` (`DAT_183336970`), donc la MEME
#   forme de construction. Le port ecrit ce lambda et le DIT hypothese ; le residu `#940-r1` porte
#   la mesure qui le trancherait (lire le `MethodInfo*` du delegue en live).
#   ⚠ `lastTargets` est PLURIEL : la boucle native invoque le `Func` sur `Entities(pickedTargets)`,
#   la liste COMPLETE des cibles deja piquees -- « adjacent to A PREVIOUS target », pas « the ».
#
# CONFRONTABILITE -- les deux porteurs, et pourquoi la voie SUMMON est FERMEE :
#   `eldarNpc3Harlequin` est un **npc** ; `eldarSmnHarlequin` est un **summon**, et son summoner
#   n'est PAS une unite : l'unique ability du gameconfig dont `constants.unitId` vaut
#   `eldarSmnHarlequin` est `EnvFactionSummons:Aeldari`, que `unit_map find --ability` ne rattache a
#   AUCUNE unite du catalogue (spawner d'ENVIRONNEMENT, pose par le board). On ne peut donc pas
#   « spawner son summoner » depuis `rl_duel build`. La voie retenue est la GREFFE sur une unite du
#   pool (`docs/rl/case-92-catalog-injection.md` §5bis), dont la CONDITION est VERIFIEE ici :
#   `KissOfDeathPlaybook` est enregistre PAR ABILITY (`metadata/active_playbook_builders.tsv` :
#   `active  1108  IdunBattle.AI.Playbook.Loki.KissOfDeathPlaybook`), et NI `ExecuteBehaviour` NI
#   `KissOfDeathPlaybook$$EvaluateNonComparable` ne lisent une stat ou un trait du caster -- tout
#   vient de la config d'ability (`GetDamageProfile`, `GetHits`, `GetVariableForLevel`, `ConfigVar`).

KISS_OF_DEATH_ID = "KissOfDeath"                              # la cle gameconfig de l'ability 1108
KISS_OF_DEATH_UNTARGETABLE = int(EffectType.Untargetable)     # 0x414 = 1044, pose ET retire par l'arbre
#: `attackRangeType` de la config 1108 = « Melee » -> `is_melee=True`.
KISS_OF_DEATH_IS_MELEE = True
#: `chainOptions` : le ctor n'ecrit QUE `+0x12 = 1` (coup differe d'un cran).
KISS_OF_DEATH_DEFERRED_HIT = True
KISS_OF_DEATH_ALLOW_REPEAT_TARGETS = False                    # `chainOptions+0x10`
KISS_OF_DEATH_ALLOW_IMMEDIATE_REPEAT = False                  # `chainOptions+0x11`
#: `unique`/`selectionType` du lambda de saut -- les DEUX litteraux du corps retenu.
KISS_OF_DEATH_JUMP_UNIQUE = 1
#: L'indice du 2e repli d'atterrissage : `AtIndex(attacked, 1)`, le litteral du call-site.
KISS_OF_DEATH_FALLBACK_INDEX = 1


def kiss_of_death_profile() -> str:
    """`AActiveAbility$$GetDamageProfile` -> `AbilityConfiguration$$GetDamageProfile(config)` : la
    constante `damageProfile` de la config 1108, RELUE du gameconfig (= « DirectDamage »), jamais
    codee en dur. Config sans la cle -> `""` (le natif rend un `Nullable` VIDE, replie sur l'arme)."""
    import gameconfig as GC
    consts = (GC.ability(KISS_OF_DEATH_ID) or {}).get("constants") or {}
    return str(consts.get("damageProfile") or "")


def kiss_of_death_hits() -> int:
    """`Direct( AActiveAbility$$GetHits(this) )` = `GetNumberConstant(0x2f = nrOfHits)` : une
    CONSTANTE de config (hors niveau), d'ou `is_constant=True`. Absente -> 1, comme le port partout
    ailleurs (`abilities/base.py::ability_attack_params`)."""
    return int(ability_var(KISS_OF_DEATH_ID, AbilityConstantType.nrOfHits.name,
                           is_constant=True) or 1)


def kiss_of_death_damage(state: "State", caster_id: int) -> int:
    """`Direct( AbilityConfiguration$$GetVariableForLevel(config, 0xb = dmg, abilityState, 0) )`.

    L'`abilityState` est celui de CETTE active sur CE caster (`active_ability_state`, #890), pas un
    niveau global d'unite. `dmg` est dans `variablesAffectedByRarityBonus` -> le multiplicateur de
    rarete MORD, et c'est `ability_var` qui l'applique."""
    level, mult = active_ability_state(state, caster_id, int(ActiveAbilityType.KissOfDeath))
    return int(ability_var(KISS_OF_DEATH_ID, AbilityVariableType.dmg.name, level,
                           multiplier_pct=mult) or 0)


def kiss_of_death_max_targets(state: "State", caster_id: int) -> int:
    """`DSLFormulas$$ConfigVar(0x0 = maxAdjacentTargets, abilityState, config)`.

    Le natif garde un NOEUD (re-evalue a chaque tour de boucle par
    `ChainBehaviourBehaviour$$GetCurrentMaxTargets`) ; le port resout la valeur au cast et la passe
    en `Const`. C'est value-preserving ICI et seulement ici : `maxAdjacentTargets` est une variable
    de CONFIG indexee par le seul niveau d'ability, que rien ne fait varier pendant l'execution de
    l'arbre (contrairement, par exemple, a un `StatAmount`). Meme `abilityState` que `dmg`."""
    level, mult = active_ability_state(state, caster_id, int(ActiveAbilityType.KissOfDeath))
    return int(ability_var(KISS_OF_DEATH_ID, AbilityVariableType.maxAdjacentTargets.name, level,
                           multiplier_pct=mult) or 0)


def kiss_of_death_jump_targets(picked_sel):
    """Le `jumpTargetSelector` -- cf. l'avertissement ICF de l'en-tete de section : corps ATTRIBUE
    (`StormOfWrathAbility$$u003CExecuteBehaviouru003Eb__1_0`), pas lu sous le nom de cette classe.

        lastTargets => Enemies( of = Caster@+0x48,
                                AdjacentUnits(lastTargets, unique = 1, selectionType = 3),
                                selectionType = 3 )

    `picked_sel` est la liste COMPLETE des cibles deja piquees (`Entities(pickedTargets)`), pas la
    derniere. Une NOUVELLE instance par iteration, comme le natif -- aucune memoisation."""
    return Enemies(AdjacentUnits(picked_sel, Const(KISS_OF_DEATH_JUMP_UNIQUE),
                                 selection_type=SELECTION),
                   selection_type=SELECTION)


def kiss_of_death_landing_tiles():
    """Chaine de TUILES d'atterrissage (cf. l'en-tete de section, lecture 5) :

        First( SortTilesByUtility( A.Otherwise(B).Otherwise(C), Caster@+0x48, 7 = Tile ), 1, false )

    avec `X = CanAddUnit(AdjacentTiles(<origine>)) op_Subtraction <DSLSelectors+0x50 = CasterTile>` et
    `<origine>` = `Last(UnitsAttackedThisTurn(Caster), 1)` / `AtIndex(<les memes>, 1)` / `Target@+0x60`.

    `CasterTile(as_ids=True)` : les deux operandes de l'`op_Subtraction` doivent vivre dans le MEME
    domaine (le natif compare des references d'entite-tuile) -- sans la conversion, la soustraction
    ne retrancherait RIEN, silencieusement (meme piege et meme parade qu'`EmpyricAmbush`).

    Le noeud est passe TEL QUEL a `FlyUnit`, qui ne l'evalue qu'a son `execute` : c'est ce qui rend
    `UnitsAttackedThisTurn` porteur de la chaine qui vient de s'executer."""
    attacked = UnitsAttackedThisTurn(Caster())
    def _free_around(origin):
        return Sub(CanAddUnit(AdjacentTiles(origin)), CasterTile(as_ids=True))
    a = _free_around(PickLastN(attacked, Const(1)))
    b = _free_around(AtIndex(attacked, KISS_OF_DEATH_FALLBACK_INDEX))
    c = _free_around(Target())
    ranked = SortTilesByUtility(Otherwise(Otherwise(a, b), c), unit_sel=Caster(),
                                utility_type=UTILITY_TYPE_TILE)
    return PickFirstN(ranked, Const(1))


def kiss_of_death_tree(dmg: int, hits: int, max_targets: int) -> AtomicGroup:
    """Arbre de `KissOfDeathAbility$$ExecuteBehaviour` -- MIRROR du DECOMPILE (cf. l'en-tete).

        ExecuteAtomic( ((AddEffect(1044 Untargetable, Caster, Caster) & ChainAttackDamage(...))
                        & FlyUnit(Caster, <tuiles>)) & RemoveEffect(1044, Caster),
                       0x2a = Ability_AtomicGroup )

    `duration_rounds=None` : le natif passe un `Nullable<AddEffectBehaviourOptions>` **VIDE** (32
    octets a zero) -- ni duree ni niveau, donc la duree DEFAUT de l'effet. C'est sans consequence
    observable ici puisque le MEME arbre le retire trois membres plus loin, mais c'est ce qui est
    ECRIT, et rien n'autorise a inventer un `TurnsFromRounds`."""
    add = AddEffect(KISS_OF_DEATH_UNTARGETABLE, EffectType.Untargetable.name, Caster(),
                    duration_rounds=None, source_ref=Caster())   # source ET cible = Caster@+0x48
    chain = ChainAttackDamage(Target(), kiss_of_death_jump_targets, Const(max_targets), Const(dmg),
                              KISS_OF_DEATH_ID, kiss_of_death_profile(),
                              is_melee=KISS_OF_DEATH_IS_MELEE, hits=hits,
                              allow_repeat_targets=KISS_OF_DEATH_ALLOW_REPEAT_TARGETS,
                              allow_immediate_repeat=KISS_OF_DEATH_ALLOW_IMMEDIATE_REPEAT,
                              deferred_hit=KISS_OF_DEATH_DEFERRED_HIT, level_slot="active",
                              ability_type=int(ActiveAbilityType.KissOfDeath))
    fly = FlyUnit(Caster(), kiss_of_death_landing_tiles())
    rem = RemoveEffect(KISS_OF_DEATH_UNTARGETABLE, Caster())
    return AtomicGroup(op_and(op_and(op_and(add, chain), fly), rem))


class KissOfDeathAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.KissOfDeathAbility$$ExecuteBehaviour` (id
    **1108**, `eldarSmnHarlequin` summon / `eldarNpc3Harlequin` npc, Aeldari) -- MIRROR du DECOMPILE,
    arbre DSL (`kiss_of_death_tree`). Avant #940 l'ability etait un **NO-OP SILENCIEUX** : absente
    d'`ABILITY_CLASSES`, elle etait choisie par l'IA puis n'executait RIEN -- zero degat, aucune
    erreur, invisible en self-play.

    Le Harlequin devient INTARGETABLE (effet 1044), enchaine `nrOfHits` coups `damageProfile` sur sa
    cible puis sur jusqu'a `maxAdjacentTargets` ennemis adjacents a une cible deja frappee, REAPPARAIT
    sur la meilleure tuile libre au contact de sa derniere victime, et perd l'intargetabilite.
    Chaine native, options et attribution du lambda : cf. l'en-tete de section."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.KissOfDeath)         # 1108 = 0x454
    ABILITY_ID = KISS_OF_DEATH_ID

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.KissOfDeathAbility$$.ctor` -- FORME
    # « RECOPIE D'UN PRESET STATIQUE », la seconde forme du piege (aucun `TargetingOptions$$.ctor`
    # n'est appele) : le corps copie les 0x40 octets de `<TargetingOptions statics>+0x40` dans un
    # temporaire, puis `AActiveAbility..ctor(this, &opts, 0)`. Le masque EFFECTIF est donc la
    # constante qu'ecrit `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28`,
    # c'est-a-dire `<statics>+0x68` = **0x4000**. Relu dans le `.cctor` ligne a ligne :
    #     statics+0x40 = 0        (isSelfCasting)
    #     statics+0x60 = 1        (forceMeleeTarget = RangedBool.False)
    #     statics+0x68 = 0x4000   (rules)            <-- le seul bit pose
    # Decomposition EXHAUSTIVE, somme exacte, aucun bit residuel :
    #     0x4000 (bit 14) TargetIsEnemy
    # Aucun `TargetHasFreeAdjacentTile` ici, contrairement a `EmpyricAmbush` : le natif n'exige PAS
    # de tuile libre au contact de la cible, parce que l'atterrissage a DEUX replis (cf. l'arbre) et
    # que `FlyUnit` sur une destination vide est simplement un no-op.
    # ⚠ **LA PORTEE NE SE DEDUIT PAS DE `attackRangeType`** : le `.cctor` recopie dans ce preset le
    # `TargetingRange` de `<TargetingRange statics>+0x30` (`*(lVar3 + 0x30)` puis `+0x38`, `+0x40`),
    # et `IdunBattle.Core.Services.TargetingRange$$.cctor` ecrit LA : `+0x30 = 0`
    # (`onlyAdjacent = RangedBool.True`), `+0x38 = Nullable(1)` (`overrideRange = 1`), `+0x40 = 0`
    # -> c'est **RANGE_ADJACENT**, pas `RANGE_FROM_CONFIG` (qui vit a `statics+0x18`). La config
    # 1108 n'a d'ailleurs AUCUNE constante `range`. Mesure du 2026-08-11 : avec `RANGE_FROM_CONFIG`,
    # le port acceptait les QUATRE ennemis du montage plus le caster la ou le natif n'en accepte
    # qu'UN (`abilityTargets.fromHere = [T]`) -- le gate sautait en silence.
    # `AbilityAttackType` = 3e argument d'`AActiveAbility$$.ctor(this, &opts, 0)` = **0**
    # (`DirectTargetAttack`), TRANSCRIT dans `abilities/attack_type.py` au meme commit.
    TARGETING_OPTIONS = TargetingOptions(rules=int(TR.TargetIsEnemy),        # `<statics>+0x68` = 0x4000
                                         self_cast=False, range=RANGE_ADJACENT,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        dmg = kiss_of_death_damage(state, caster_id)
        hits = kiss_of_death_hits()
        max_targets = kiss_of_death_max_targets(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        kiss_of_death_tree(dmg, hits, max_targets).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        attacks = [p for (n, p) in ectx.emitted if n == "AttackWithAttackDamage"]
        fly = next((p for n, p in ectx.emitted if n == "FlyUnit"), None)
        return {"ability": KISS_OF_DEATH_ID, "caster": caster_id, "target": target_id,
                "dmg": int(dmg), "hits": int(hits), "maxTargets": int(max_targets),
                "targets": [a.get("target") for a in attacks],
                "attacks": [a.get("attack") for a in attacks],
                "move": fly, "dsl": True,
                "emitted": [n for n, _ in ectx.emitted]}


# ============ WarConstruct (1133, `eldarNpc4Wraithguard` / `eldarNpc4WraithguardSurv`) =============
# Lot #996 -- « six no-op silencieuses » (docs/rl/case-996-six-no-op-silencieuses-reconnaissance.md).
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.WarConstructAbility$$ExecuteBehaviour`
# (MIRROR 1:1 du DECOMPILE) :
#
#   [1] AddEffect( 0x516 = 1302 IgnoreUsedAbilityInOverwatch, AbilityStateReference,
#                  targets = Owner@+0x30,  DSLFormulas$$TurnsFromRounds(1) )
#   [2] AddEffect( 0x506 = 1286 WarConstruct_CounterAttack, AbilityStateReference,
#                  targets = Target@+0x60, DSLFormulas$$TurnsFromRounds(1) )
#   AActiveAbility$$Execute( op_Addition([2], [1]) )     # <- l'ordre EST celui-la au decompile
#
# CATEGORIE ANNONCEE PAR L'AUDIT = EFFECT/BUFF -> **CONFIRMEE**. Le cast ne frappe pas : aucun
# `AttackWith*`, aucun `UseActiveAbility`, aucune stat touchee. (Cette colonne derive du
# `damageProfile` de l'ARME du porteur et ne vaut rien tant que l'`ExecuteBehaviour` n'a pas ete lu
# -- 4 des 6 no-op du lot #996 la portaient FAUSSE.)
#
# LES DEUX DUREES SONT LE LITTERAL `1`, PAS UNE CONSTANTE DE CONFIG : le kit gameconfig 1133 ne
# porte NI `constants` NI `variables`, et le decompile passe `(void *)0x1` a `TurnsFromRounds` aux
# deux volets. Aller chercher un `nrOfRounds` inexistant rendrait `None`.
#
# CAST SELF -- `Target@+0x60` EST le caster ici : le ctor pose `isSelfCasting = 1`, donc
# `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` rend `caster` quelle que soit la cible
# demandee (mirror `actual_target`). Les deux selecteurs sont ecrits SEPAREMENT quand meme, parce
# que c'est ce que le natif ecrit -- les rabattre sur un seul perdrait la structure.

WAR_CONSTRUCT_ID = "WarConstruct"
IGNORE_USED_ABILITY_IN_OVERWATCH = int(EffectType.IgnoreUsedAbilityInOverwatch)   # 0x516 = 1302
WAR_CONSTRUCT_COUNTER_ATTACK = int(EffectType.WarConstruct_CounterAttack)         # 0x506 = 1286
WAR_CONSTRUCT_ROUNDS = 1              # `TurnsFromRounds(1)` -- LITTERAL du decompile, pas un kit


def war_construct_tree():
    """Arbre de `...WarConstructAbility$$ExecuteBehaviour` (MIRROR 1:1, cf. le bloc ci-dessus) :

        op_Addition( AddEffect(1286 WarConstruct_CounterAttack -> Target, TurnsFromRounds(1)),
                     AddEffect(1302 IgnoreUsedAbilityInOverwatch -> Owner, TurnsFromRounds(1)) )
    """
    counter = AddEffect(WAR_CONSTRUCT_COUNTER_ATTACK, EffectType.WarConstruct_CounterAttack.name,
                        Target(), duration_rounds=WAR_CONSTRUCT_ROUNDS)
    overwatch = AddEffect(IGNORE_USED_ABILITY_IN_OVERWATCH,
                          EffectType.IgnoreUsedAbilityInOverwatch.name,
                          Owner(), duration_rounds=WAR_CONSTRUCT_ROUNDS)
    return op_add(counter, overwatch)


class WarConstructAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.WarConstructAbility$$ExecuteBehaviour`
    (id 1133, `eldarNpc4Wraithguard` + `eldarNpc4WraithguardSurv`, npc Aeldari). Cast SELF.

    Kit gameconfig 1133 : NI `constants` NI `variables` -- rien a lire, tout est litteral.

    OBSERVABLE porte : deux effets poses pour `ConvertRoundsToTurns(1)` --
    `WarConstruct_CounterAttack` (1286) et `IgnoreUsedAbilityInOverwatch` (1302), tous deux sur le
    caster (cast SELF).

    RESIDU NOMME -- la MECANIQUE des deux effets n'est pas portee, seule leur POSE l'est. Tout
    l'appareil natif de la contre-attaque vit dans l'EFFET, hors de cet `ExecuteBehaviour` :
    `IdunBattle.Entities.Effects.Loki.WarConstruct_CounterAttackEffect$$GetCounterAttackBehaviour`,
    `$$GetCounterAttackTrigger`, `$$GetCounterAttackCondition`, `$$GetDamage`,
    `$$CreateActiveCondition`. Idem pour 1302, dont le sens (« l'overwatch ignore le fait qu'une
    ability ait ete utilisee ») se joue dans le gate d'overwatch. Les deux effets sont donc POSES
    (visibles, duree juste) et INERTES tant que ces artefacts-la ne sont pas portes.

    Flags de tour : defauts base (1133 absent des tables d'override)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.WarConstruct)   # 1133
    ABILITY_ID = WAR_CONSTRUCT_ID

    # GATE DE CIBLE + PORTEE -- forme de ctor = **FLAGS DIRECTS** (le litteral du ctor EST le
    # masque ; aucun preset recopie, aucun OR de flags). `...WarConstructAbility$$.ctor` :
    #     TargetingOptions..ctor(&opts, isSelfCasting=1, range=<TargetingRange statics+0x60>,
    #                            forceMeleeTarget=1, rules=0x8000, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)   # 3e arg = 2 = AbilityAttackType.Others
    #
    # Decomposition EXHAUSTIVE -- 0x8000 SEUL, aucun bit residuel :
    #     0x8000  (bit 15) CasterIsPossibleTarget -> flag DECLARATIF (preview / IA), deja mirrore
    #             (`TargetingOptions.can_target_caster`). AUCUN bit `TargetIsEnemy`/`TargetIsFriendly`
    #             n'est pose : le domaine de cible est fixe par `isSelfCasting`, pas par le masque.
    # PORTEE : `TargetingRange statics+0x60` = `RANGE_SELF` (`overrideRange = 0`), et la constante
    # `range` du kit n'est PAS consultee (elle n'existe pas). `forceMeleeTarget` = 1 =
    # `RangedBool.False`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.CasterIsPossibleTarget, self_cast=True,
                                         range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        war_construct_tree().execute(
            entities_from_state(state, caster_id, target_id), ectx)
        posed = [{"target": p.get("target"), "effect": p.get("effect_type"),
                  "placed": p.get("placed")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": WAR_CONSTRUCT_ID, "caster": caster_id, "target": target_id,
                "posed": posed, "dsl": True}