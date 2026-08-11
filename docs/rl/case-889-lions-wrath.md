# #889 -- `1217 TheLionsWrath` portee, et l'ecart qui reste est au PREMIER etage

Face COMBAT de l'active `1217` du boss `darkaBossLion` (« le Lion »), **les deux phases**, plus le
canal crit par INDEX DE COUP qu'elle exige. La face DECISION etait deja portee (#27-r4,
`playbook/loki_custom.py::TheLionsWrathPlaybook`) : l'IA CHOISISSAIT donc une ability dont le
`execute_behaviour` ne faisait RIEN -- ni degat, ni effet, ni erreur.

## L'arbre, tel que LU

`IdunBattleLogic.Entities.Abilities.Active.Loki.TheLionsWrathAbility$$ExecuteBehaviour` :

    (   AddEffect( 0x5f2 = 1522 TheLionsWrath_ExtraCritChance, AbilityStateReference,
                   targets = Owner@DSLSelectors+0x30, turns = null )
      + AttackWithAttackDamage( caster = Caster@+0x48, target = Target@+0x60,
                                MinMaxDamage, GetDamageProfile() = Power,
                                ConfigConst(0x2f = nrOfHits) = 2,
                                AbilityOrEffect(this),
                                options = Nullable{ +0x00..0x07 = 0 ; +0x08 = List<int>{1} },
                                selectionType = 2 ) )
    + IfAlive( Target@+0x60,
          AddBondEffect( 0x1b = 27 Taunted_OnlySpecificTargets, source = Owner@+0x30,
                         targets = Target@+0x60, bondedEntity = Owner@+0x30,
                         turns = TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds)) )
        + AddBondEffect( 0x5f1 = 1521 TheLionsWrath_PendingAttack, memes slots,
                         options = <struct ZEROEE> ) )

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TheLionsWrath_PendingAttackAbility$$CreateBehaviour`
(phase 2, `TriggeredAbilityType` 1520) :

    If( IsAlive(Target@+0x60) & IsAdjacent(Caster@+0x48, Target@+0x60, 3),
        RemoveEffect(Owner@+0x30, 1521) + AttackWithAttackDamage(
            Caster@+0x48, Target@+0x60, MinMaxDamage2, GetDamageProfile2 = Piercing,
            ConfigConst(0x32 = nrOfHits_2) = 2, AbilityOrEffect(this), options, 2) )
    + RemoveEffect(Owner@+0x30, 1522)          <-- **HORS** du `If`

Le `rm2` hors du `If` est le point de structure : le +100 % de crit part dans TOUS les cas, meme
si le coup differe ne part pas. L'y ranger laisserait un buff permanent sur le boss.

`IdunBattle.Entities.Effects.Loki.TheLionsWrath_ExtraCritChanceEffect$$CreateCritChanceBonus` :

    ForAddition( get_OwnerIsCaster & AmountIsEqual(CurrentHitIndex(), <DSLFormulas+0x20> = 1),
                 ConfigVar(0x3a = chance) )

`chance = 100` a tous les niveaux et `nrOfHits = 2` -> **le second coup crite par construction**.
⚠ `0x3a = 58 = chance`, **pas** `extraCritChance` (`0x41 = 65`) -- c'est celle-la que lit `1216
MartialExemplar`, l'autre active du MEME boss. L'ordinal seul ne l'aurait pas dit.

`IdunBattle.Entities.Effects.Loki.TheLionsWrath_PendingAttackEffect$$CreateHandleTriggerAbilitiesInternal`
ajoute un **SECOND** `Triggered()` a celui de la base `APendingAttackEffect` :
`On(0x25 = UnitRemoved) & get_OwnerIsTarget -> GetAttackBehaviour(effect)` -- le `TriggerAbility`
SEUL, sans le `RemoveEffect(Effect@+0x38)` de la base. Aucune des deux autres derivees portees
(1123, 1300) n'a ce second chemin.

## Le masque, et son overload

`...TheLionsWrathAbility$$.ctor` est une **STATIC-COPY** : il recopie les 0x40 octets du preset
`<TargetingOptions statics>+0x40` et les passe TELS QUELS a `AActiveAbility$$.ctor(this, &opts, 0)`
-- aucune surcharge de `TargetingOptions$$.ctor` n'est appelee, donc aucun `|` de flags. Le masque
EFFECTIF est la constante du `.cctor` : `rules = 0x4000 = TargetIsEnemy` SEUL,
`isSelfCasting = 0`, `range = <TargetingRange statics>+0x30 = RANGE_ADJACENT`,
`forceMeleeTarget = 1 = RangedBool.False`. Le 3e argument, `0`, est l'`AbilityAttackType`
= `DirectTargetAttack`. Les quatre valeurs MIGRENT de `TARGETING_OPTIONS_UNPORTED[1217]` vers la
classe (contrat de disjonction), re-lues avant migration.

## Ce que la confrontation LIVE a mesure (`probe_889_lions_wrath.py`)

Montage : `--board CE6_boss` (SA carte : 7x10, 65 tuiles jouables, 8 spawns cote boss), boss au
palier `:4` (le SEUL a porter `CritChance 20` / `CritDamage 4735` -- au palier `:1` l'etage crit
serait DEGENERE et son accord ne prouverait rien), cible collee par `--a-place` (le Lion est
`moveNone` : on deplace la CIBLE, jamais « bloque par la geometrie »).

**EMPREINTE (`decisionView.units[].feet`), la mesure qui manquait** : le Lion rend **1 pied**
(`n_feet=1`, `feet=[{col:3,row:3}]`), comme les deux unites ordinaires du montage. Le temoin ne
discrimine donc TOUJOURS PAS -- aucun porteur a `> 1` n'a ete trouve, et `BigTarget` n'y change
rien. On sait desormais que c'est vrai du Lion sur SA carte ; on ne sait toujours pas si le canal
sait rendre autre chose que `1`.

**[A] STRUCTURE DU CAST -- ACCORD, sur les deux regimes**, et le second regime est arrive par
accident :

| regime | natif | port |
|---|---|---|
| cible SURVIT (`--hp-target 400000`) | `84:{1522}` + `86:{27,25,26,1237,1521}` | **identique** |
| cible TUEE (regime nominal, 11044 PV) | `84:{1522}` SEUL | (n'a pas tue) |

Le regime « cible tuee » **confronte l'`IfAlive(Target)`** : le natif ne pose AUCUN bond sur un
cadavre. C'est la faute qu'avait coutee `LashOfTorment` (case-524) et la structure la refuse.

**[B] ECART DE DEGAT -- localise au PREMIER etage, PAS dans l'arbre.** Coups natifs
`[9658, 9998]`, coups port `[5750, 5744]`. Les ratios par coup (1,680 et 1,741) ne se rattachent
a aucun facteur en aval ; ils se rattachent aux BORNES : le port lit `(base_min, base_max) =
(48, 64)` et

    minDmg[12] / 48 = 82/48 = 1,708      maxDmg[12] / 64 = 109/64 = 1,703

-- le MEME ratio sur les DEUX bornes, ce qu'un multiplicateur applique en aval ne peut pas
produire (il donnerait le meme facteur sur le total, pas la meme paire de la table). Le natif lit
donc le niveau d'ability **12** la ou le port en lit un qui rend `(48, 64)`. Le nombre de coups
(2), le profil (`Power`), le crit et la structure ACCORDENT ; **seule la borne d'entree diverge**.
C'est un ecart de SEEDING du niveau d'ability d'une unite **npc** montee par `--explicit-stats`,
hors du perimetre de cet arbre -- residu **#889-r3**.

**[C] PHASE 2 -- NON CONFRONTEE**, et la raison est mesuree : au regime `--hp-target 400000`, le
`endturn` intercalaire laisse l'**IA adverse jouer** (le natif inflige 16 919 PV pendant ce pas,
le port n'a pas d'IA), et a l'issue de ce tour les effets `27` et `1521` ont **disparu** de la
cible cote natif (`remaining` = 1 au cast cote natif, 2 cote port). Le coup differe natif ne part
donc jamais, et le port, lui, le tire. Deux causes candidates NON DEPARTAGEES : (a) la duree
posee diverge reellement, (b) l'IA adverse a consomme/retire les effets. Le montage qui
trancherait est un `endturn` **NU** des deux cotes (`--no-ai`), qui n'a pas ete joue -- residu
**#889-r4**.

## Ce que ce port ne couvre PAS

* le champ `+0x08` des `AttackDamageBehaviourOptions` -- une `List<int>{1}` que les DEUX phases
  passent a `AttackWithAttackDamage`. Chemin LU (`options+0x08` -> `AttackDamageBehaviour+0xa0` ->
  transmis tel quel a la requete de degat), **semantique NON LUE** ; aucun autre call-site du
  depot ne renseigne ce champ. Le port ne lui prete aucun effet -- residu **#889-r2** ;
* le canal crit ne mesure la chance qu'a **deux** index (0 et 1+), la ou le natif la relit a chaque
  coup : exact pour toute serie de 1 ou 2 coups (donc pour ce porteur), LIMITE au-dela -- **#889-r1** ;
* la branche `On(0x25 = UnitRemoved)` du second `Triggered()` : `On(0x25)` n'est publie que par
  `RemoveUnitOperation`, qu'aucune ability du roster de ce montage ne declenche ;
* `Overwatch` et `Parry` du Lion : ils ne mordent pas sur un cast (le Lion est `moveNone`, donc
  aucun deplacement du caster), mais ils mordraient sur une sequence d'attaques normales -- non jouee.

## `1216 MartialExemplar` -- RE integrale, port NON FAIT

`...MartialExemplarAbility$$ExecuteBehaviour`, lu en entier :

    ( AddEffect(0x5f0 = 1520 MartialExemplar_ExtraCritChance, targets = Owner@+0x30,
                turns = <DSLFormulas+0x20> = Direct(1))
    + AttackWithAttackDamage(Owner@+0x30, AdjacentEnemies(Owner@+0x30, 1, 3), MinMaxDamage,
                             GetDamageProfile(), ConfigConst(0x2f = nrOfHits) = 6, ..., 2) )
    + IfAlive( Caster@+0x48,
          KillDeadUnits(Caster@+0x48, AdjacentEnemies(Owner@+0x30, 1, 0))
        + If( AmountIsGreaterThanZero(<attaquables adjacents>),
              UseNormalAttack(Owner@+0x30, SortUnitsByDamageUtility(<attaquables adjacents>, ...)),
              MoveUnit(Owner@+0x30, ClosestPositionToTarget(Owner, Tiles(<cible tiree>),
                                                            ConfigConst(0x17 = nrOfTiles)))
              + UseNormalAttackIfAble(Owner@+0x30, <cible tiree>) ) )

ou `<cible tiree>` = `Cache(PickRandomly(Nearest(Filter(Enemies(Owner, AllAliveUnits, 3),
NOT HasTrait(ActiveTarget@+0x68, 0x1b = Steppable)), CasterTiles@+0x58, Owner@+0x30, 1, null),
1, ...))` et `<attaquables adjacents>` = `Cache(Filter(AttackableEnemies(Owner@+0x30),
IsAdjacent(ActiveTarget@+0x68, Owner@+0x30, 3)))`.

Son effet : `...MartialExemplar_ExtraCritChanceEffect$$CreateCritChanceBonus` =
`ForAddition(get_OwnerIsCaster & HasTrait(Target@+0x60, 0x2 = UnitTrait.Summon),
ConfigVar(0x41 = extraCritChance) = 10)` -- +10 % de crit contre les SUMMONS uniquement.

**Pourquoi non porte** : la seconde moitie de l'arbre exige **cinq noeuds DSL absents du port** --
`DSLSelectors$$Nearest` (-> `NearestSelector`), `$$ClosestPositionToTarget`,
`$$SortUnitsByDamageUtility`, `$$CasterTiles` (slot `+0x58`) et les deux behaviours
`DSLBehaviors$$UseNormalAttack` / `$$UseNormalAttackIfAble`. Les deux derniers sont a portee de
main (`UseNormalAttack` alloue un `UseActiveAbilityBehaviour`, deja porte sous
`behaviours/combat.py::UseActiveAbility`, avec un `activeAbilityType` derive du caster) ;
`AttackableEnemies` l'est aussi (`UnitsWithoutTrait(Enemies(unit, AllAliveUnits, 3), 0x1b, 3)`,
corps LU, les deux briques existent). Restent `Nearest`, `ClosestPositionToTarget` et
`SortUnitsByDamageUtility`, qui sont des selecteurs a corps propre. Porter la PREMIERE moitie
seule (AddEffect + attaque AoE adjacente) serait un port infidele SILENCIEUX : le boss cesserait
d'enchainer son attaque normale apres le cast. Residu **#889-r5**.

Son masque, lui, est deja LU et pose (`TARGETING_OPTIONS_UNPORTED[1216]`, forme PRESET+FLAGS :
`0x8004 | 0x10 = 0x8014`) -- il reste dans cette table tant que la face COMBAT n'est pas portee,
comme le contrat de disjonction l'exige.
