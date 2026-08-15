# #889-r5 -- les noeuds DSL qui manquaient, et `1216 MartialExemplar` qu'ils debloquent

#889 avait **REFUSE** de porter `1216` : son arbre appelle des noeuds absents du port, et livrer la
moitie disponible aurait fait un port infidele SILENCIEUX (le boss cesserait d'enchainer son
attaque normale apres le cast). Cette tranche leve le verrou et porte l'ability.

## 1. L'inventaire, RE-DERIVE -- la fiche annoncait TROIS noeuds, il y en a SEPT

La liste de #889 (`Nearest`, `ClosestPositionToTarget`, `SortUnitsByDamageUtility` ; `CasterTiles`
et `AttackableEnemies` donnes pour triviaux, `UseNormalAttack`/`IfAble` pour « a portee de main »)
est **incomplete dans les deux sens**. Re-derivee du decompile de
`IdunBattleLogic.Entities.Abilities.Active.Loki.MartialExemplarAbility$$ExecuteBehaviour`, appel
par appel :

| noeud natif | statut REEL |
|---|---|
| `DSLSelectors$$Nearest` | **MANQUANT** -> porte (`selectors/pathing.py`) |
| `DSLSelectors$$ClosestPositionToTarget` | **MANQUANT** -> porte (`selectors/pathing.py`) |
| `DSLSelectors$$SortUnitsByDamageUtility` | **MANQUANT comme NOEUD** (le `$$Select` etait deja porte) -> `selectors/units.py` |
| `DSLSelectors$$AttackableEnemies` | **MANQUANT** -> `selectors/composites.py` (composite, pas une classe) |
| `DSLBehaviors$$UseNormalAttack` / `$$UseNormalAttackIfAble` | **MANQUANTS** -> `behaviours/combat.py` |
| `DSLTriggers$$AmountIsGreaterThanZero(ITargetsSelector)` | **MANQUANT, et ABSENT DE LA FICHE** -- surcharge homonyme (cf. §2) |
| `DSLSelectors$$CasterTiles` (slot `+0x58`) | **N'EST PAS MANQUANT** -- le port collapse deja `CasterTile`/`CasterTiles` sur un seul noeud (le natif les alloue depuis le MEME pointeur de classe, meme ctor ; residu anterieur `#478-r1`) |
| `DSLFormulas$$NormalAttackDamage`, `DSLSelectors$$UnitNormalAttackType`, `UtilityDefinition(0x23)` | deja portes (`StatAmount(unit, Attack)`, `formulas.UnitNormalAttackType`, `utilities/decider`) |

Soit **six** portages reels et **un** faux manquant. Le noeud le plus couteux
(`AmountIsGreaterThanZero` variante selecteur) n'etait dans AUCUNE liste.

## 2. Les surcharges, tranchees par les XREFS ENTRANTES

* **`SortUnitsByDamageUtility` -- QUATRE surcharges.** `MartialExemplarAbility$$ExecuteBehaviour`
  appelle `180eb18b0`, celle dont `ability` est un `IAbilityTypeSelector` (7 arguments). Les deux
  plus courtes DELEGUENT a elle (`180eb1a60`, `180eb1b2d` -> `180eb18b0`), donc c'est le FOYER.
  ⚠ Son parametre `unitSelectionType` **n'est pas transmis au ctor** du selecteur : il ne survit
  que dans la surcharge appelante.
* **`AmountIsGreaterThanZero` -- DEUX surcharges au corps IDENTIQUE**, qui ne different que par le
  TYPE DECLARE de leur unique parametre (`IAmountFormula` -> slot `+0x18` ; `ITargetsSelector` ->
  slot `+0x10`). `AmountIsGreaterAbilityTrigger$$ShouldTrigger`, lu en entier :

      amount = 0
      if (+0x10 : ITargetsSelector) amount = (+0x10).Count(entities)        // slot 2
      if (+0x18 : IAmountFormula)   amount = (+0x18).Calculate(entities)    // slot 1
      return (+0x20 : IAmountFormula).Calculate(entities) < amount          // min = Direct(0)

  Le port ne connaissait que la variante FORMULE ; `1216` emprunte la variante SELECTEUR. La faute
  a ete BRUYANTE ici (`TypeError: '>' not supported between 'list' and 'int'`) -- **c'est un coup
  de chance** : sur un noeud dont l'`evaluate` rend un int, la meme confusion aurait ete muette.
* **`Nearest`, `ClosestPositionToTarget`, `AttackableEnemies` : UNE seule implementation chacune**
  (xrefs entrantes, refcount 9 / 5 / 4). Les voisins `NearestFreeTilesAmount` et
  `NearestAttackableEnemies` sont des noms DISTINCTS, pas des surcharges.

⚠ **UN CTOR MISLABELE, ET IL AURAIT BRANCHE LE MAUVAIS `$$Select`.** Ghidra nomme le ctor alloue
par `ClosestPositionToTarget` `TilesUnitCanAttackFromSelector$$.ctor` -- corps DEDUPLIQUE, partage
avec `DSLSelectors$$TilesUnitCanAttackFrom`, dont le 3e parametre est un **`System.String`** (un
`unitId` de gameconfig) et dont le `$$Select` appelle `GetUnitConfig`/`GetUnitMaxRange`. Lire ces
noms-la aurait range un `IAmountFormula` dans un slot string. La signature RETENUE est celle de
`frida/methods.tsv` (`unit, targetTiles, maxDistance:IAmountFormula, ignoreFlags:bool`), et la
classe reellement allouee est `IdunBattle.Entities.Selectors.ClosestPositionToTarget`
(`classes.tsv`, 64 octets, base `TargetSelector`), dont le `$$Select` est a `180fda110`.

## 3. Les corps portes, et ce que chacun exige

* **`NearestSelector$$Select`** : `foreach c in candidates / foreach t in targets`, avec
  `d <= best && d <= maxDist` -> `if (d < best) Clear()` puis `Add(c)` -> les EX-AEQUO
  s'accumulent (un argmax classique en rendrait un seul). Branche NATIVE qu'il ne faut pas lisser :
  `pathfindingUnit` nul **et** `distanceType == PathLength` -> le selecteur rend ses candidats
  **INTACTS** (avec un log), ni vides ni filtres.
  `GetDistance` : `Simple` -> distance hex ; `PathLength` -> `1` si adjacent, sinon
  `GetMinPathLength(pathfindingUnit, target, GetFreeAdjacentTiles(candidate))`, **moins 1 si le
  candidat n'est PAS une unite**.
* **`ClosestPositionToTarget$$Select`** : `GetMovablePositionsFor(unit, ignoreFlags,
  Nullable(maxDistance))` puis argmax `<` STRICT de `GetDistance(tile, targetTiles)`.
  ⚠ **Son gate d'entree est `!CanMove(unit)` -> ensemble VIDE**, et c'est ce que le port avait
  d'abord manque (cf. §5).
* **`UseNormalAttack` / `UseNormalAttackIfAble`** : les deux allouent le MEME
  `UseActiveAbilityBehaviour(caster, target, UnitNormalAttackType(caster), parentAbility,
  triggerAbilityOrEffect, options)`. **La seule difference des deux corps** est que `IfAble` ecrit
  `options.<champ 0 : System.Nullable<enum4>> = 2` avant le ctor. Le champ suit la chaine jusqu'au
  premier champ d'`ActiveAbilityOptions` puis a `IOperationProcessor.ActiveAbility` (slot 2) ; il
  est aussi renseigne par la voie JOUEUR (`InputMessageProcessor.<>c__DisplayClass13_0$$<Visit>b__0`)
  et par `AutoCounterAttackAbility` -- il n'est donc PAS specifique a << IfAble >>. **Semantique
  NON LUE** -> residu `#889-r5-r2` ; le port transporte la valeur sans lui preter d'effet.
* ⚠ **LA BOUCLE DU NATIF PORTE SUR LES CASTERS, ET LA CIBLE EST `SelectFirst`.** Lu aux slots
  d'interface (`ITargetsSelector` : 0 = `Select`, 1 = `SelectFirst`, 7 = `SelectUnit`),
  `UseActiveAbilityBehaviour$$Execute` prend **UNE** cible et itere les casters. Le noeud
  `UseActiveAbility` deja porte fait l'INVERSE (il itere les cibles, triees par id) : inerte sur
  son unique call-site (`FinalJustice`, un caster + un `First`), mais `1216` passe un
  `SortUnitsByDamageUtility` **SANS `First`** -- iterer les cibles y frapperait N unites la ou le
  natif n'en frappe qu'UNE. D'ou deux classes distinctes, et le residu `#889-r5-r1` sur le voisin.

## 4. `1216 MartialExemplar` -- l'arbre

    ( AddEffect(0x5f0 = 1520, AbilityStateReference, Owner@+0x30, turns = <DSLFormulas+0x20> = Direct(1))
    + AttackWithAttackDamage(Owner@+0x30, AdjacentEnemies(Owner, unique:true, OnlyAliveAndTargetable),
                             MinMaxDamage, GetDamageProfile() = Power,
                             ConfigConst(0x2f = nrOfHits) = 6, AbilityOrEffect(this),
                             options = ZERO, selectionType = 2) )
    + IfAlive( Caster@+0x48,
          KillDeadUnits(Caster@+0x48, AdjacentEnemies(Owner, unique:true, UnitSelectionType.Any))
        + If( AmountIsGreaterThanZero(<attaquables adjacents>),
              UseNormalAttack(Owner, SortUnitsByDamageUtility(<attaquables adjacents>, Owner,
                  UnitNormalAttackType(Owner), UtilityDefinition(0x23), NormalAttackDamage(Owner),
                  OnlyAliveAndTargetable, hits: null)),
              MoveUnit(Owner, ClosestPositionToTarget(Owner, Tiles(<cible tiree>),
                                                      ConfigConst(0x17 = nrOfTiles) = 1, false))
            + UseNormalAttackIfAble(Owner, <cible tiree>) ) )

`<cible tiree>` = `Cache(PickRandomly(Nearest(Filter(Enemies(Owner, AllAliveUnits, 3),
NOT HasTrait(ActiveTarget@+0x68, Steppable)), CasterTiles@+0x58, Owner, PathLength, null), 1))` ;
`<attaquables adjacents>` = `Cache(Filter(AttackableEnemies(Owner), IsAdjacent(ActiveTarget@+0x68,
Owner, OnlyAliveAndTargetable)))`.

⚠ **`AdjacentEnemies` est appele DEUX fois avec des `selectionType` DIFFERENTS** : la frappe passe
`OnlyAliveAndTargetable(3)`, le `KillDeadUnits` qui suit passe **`Any(0)`** -- il doit voir les
cadavres que la frappe vient de faire. Recopier `3` aux deux rangs aurait laisse des morts non
nettoyes, en silence.

**Masque** (forme PRESET+FLAGS) : preset `<TargetingOptions statics>+0x280` (`rules = 0x8004`) OR
`additionalRules = 0x10` -> `0x8014` = `CasterIsPossibleTarget | CasterHasNotMoved |
CasterMatchesDynamicRule`, `isSelfCasting = 1`, `forceMeleeTarget = RangedBool.False`,
`range = None` (bloc non resolu, aucun gate invente). **MIGRE** de
`TARGETING_OPTIONS_UNPORTED[1216]` vers la classe (contrat de disjonction), valeurs RE-LUES avant
migration. **`AbilityAttackType` = `2` = `Others`** -- litteral du `AActiveAbility..ctor(this,
&opts, 2)`, et il **DIFFERE de celui de sa jumelle 1217** (`0`), alors que les deux frappent et
appartiennent au meme boss : le deduire aurait ecrit `0`.

**Effet `1520`** : `ForAddition(get_OwnerIsCaster & HasTrait(Target@+0x60, 0x2 = UnitTrait.Summon),
ConfigVar(0x41 = extraCritChance) = 10)`. ⚠ `0x41 = extraCritChance`, **pas** `0x3a = chance` (la
variable de `1217`, meme boss, variables voisines). Son predicat porte sur le trait du **DEFENSEUR**
-- unique dans le depot, d'ou l'ajout de `tgt_traits` au foyer `AttackDamageOperation._crit_board`,
pendant exact d'`att_traits`. ⚠ `1520` est AUSSI `TriggeredAbilityType.TheLionsWrath_PendingAttack` :
c'est l'`AddEffect` (2e argument = `EffectType`) qui fixe l'enum.

## 5. Ce que la confrontation LIVE a mesure (`probe_889r5_martial_exemplar.py`)

Montage : `--board CE6_boss` (SA carte), boss au palier `:4`, cible collee par `--a-place`.
**MOUVEMENT DU PORTEUR, MESURE et non suppose** : le Lion est **`moveNone` sur `CE6_boss`**
(la generalisation « tous les boss sont `moveNone` » est fausse -- `deathBossMortarion` rend
`+move[2]`). **EMPREINTE** : `feet = 1` ; le canal `feet` ne discrimine pas (il rend 1 pour tout le
monde), mais le temoin NATIF le tranche -- `1193 NovaCharge` porte `CasterHas7Tiles` et rend
`0` cible la ou `1194` en rend 66 sur le meme caster : **les boss montes par `rl_duel` sont
MONO-HEX, et c'est le jeu qui le dit**. Le nombre de pieds du Lion est donc **1**.

TROIS regimes, et le troisieme existe parce que les deux premiers ne prenaient PAS la branche ELSE :

| regime | branche prise | AoE natif vs port | second volet |
|---|---|---|---|
| `survit` (`--hp-target 400000`) | THEN | `88` : **-8632 / -8632 EXACT** ; `86` : **-17134 / -17134 EXACT** | natif +10645 (attaque normale), port **0** |
| `meurt` (PV nominaux) | THEN | `88` : **-6172 / -6172 EXACT** | natif +2897, port **0** |
| `vide` (`--hp-target 1`) | **ELSE** | `86` et `88` : **1 -> 0 des DEUX cotes** | aucun des deux ne frappe de plus |

**[A] STRUCTURE DE DECISION -- ACCORD sur les TROIS regimes.** Le port prend la MEME branche que le
natif, et dans la branche THEN il vise la MEME cible (`86`) : c'est l'ecart de PV qui l'etablit,
puisque le supplement natif porte **exactement** sur l'unite que le
`SortUnitsByDamageUtility` du port a classee premiere.

**[B] FRAPPE AoE -- BIT-EXACTE** sur les deux cibles, dans les trois regimes, y compris le crit du
coup d'index 0 et les six tirages.

**[C] ATTAQUE NORMALE ENCHAINEE -- NON EXECUTEE par le port, cause NOMMEE et MESUREE.**
`AttackDamageOperation.execute` rend `None`, et le temoin de substrat dit pourquoi :
**`sc.ctx.weapons` est VIDE** pour le boss (`caster_armes = 0`). Ce n'est pas un ecart d'ARBRE --
le port decide juste, il ne peut pas resoudre l'arme d'un porteur dont le canal de seed ne publie
aucune arme. Meme famille que `#889-r3` (seeding d'une unite montee par `--explicit-stats` sous un
id remappe). Residu **`#889-r5-r3`**. Le noeud publie desormais un tri-etat (`skipped =
`rng_non_cale` | `operation_refusee` | `None`) : sans lui, un `attack: null` ne disait pas SI
l'operation avait ete refusee ni pourquoi.

**[D] BRANCHE ELSE -- ACCORD, et le gate `CanMove` tient.** Aucun deplacement des deux cotes ;
`ClosestPositionToTarget` rend `[]` parce que `!CanMove(Lion)`. ⚠ **Ce temoin de position est
DEGENERE dans ce regime** : la bataille se termine au cast (les deux ennemis meurent), donc les
unites sortent de `decisionView` et les positions rendent `null`. L'accord y est donc etabli sur
le DEGAT, pas sur la geometrie -- dit, pas tu.

**[E] EFFET `1520` -- ECART NON TRANCHE.** Le port le pose (`{84: {1520: 1}}`), le natif ne le
publie PAS dans `decisionView.units[].effects` (le caster y porte `1026, 1516, 1561, 1562, 1082`
apres le cast, jamais `1520`). Deux causes NON DEPARTAGEES : (a) le natif ne le pose pas, (b) ce
canal ne publie pas cet effet. Le montage qui trancherait exige un capteur d'effets INDEPENDANT de
`decisionView` (le hook `modifier-observe` ou `statModSources`). Residu **`#889-r5-r3`** (meme
residu que [C] : les deux sont des trous du meme SUBSTRAT de boss, pas de l'arbre).

## 6. Ce que ce port ne couvre PAS

* le champ `+0x00` des `UseActiveAbilityBehaviourOptions` (`Nullable(2)` ecrit par
  `UseNormalAttackIfAble`) -- chemin LU jusqu'a `IOperationProcessor.ActiveAbility`, **semantique
  NON LUE**. Residu **`#889-r5-r2`** ;
* la boucle inversee du noeud `UseActiveAbility` deja porte (cibles au lieu de casters) -- inerte
  sur son unique call-site, mais c'est une divergence structurelle reelle. Residu **`#889-r5-r1`** ;
* le bonus de crit de `1520` : aucun ennemi du montage ne porte `UnitTrait.Summon`, donc l'effet
  est confronte dans sa STRUCTURE, jamais dans sa MAGNITUDE ;
* `MovementComponent$$IsAllowedToMove`, 4e etage de `CanMove` : residu NOMME anterieur, aucun canal
  de seed. La degradation est PERMISSIVE et bornee a ce seul etage ;
* `1215 InstrumentsOfVengeance` -- **NON PORTE**, cf. §7.

## 7. `1215 InstrumentsOfVengeance` -- RE partielle, port NON FAIT

`...InstrumentsOfVengeanceAbility$$ExecuteBehaviour`, lu :

    b1 = GetEffectBehavior(direction = 1, first = true) + GetEffectBehavior(direction = 5, first = false)
    b2 = GetEffectBehavior(direction = 2, first = true) + GetEffectBehavior(direction = 4, first = false)
    main = If( Maybe(0x32 = 50 %), b1, b2 )
         + AddBondEffect(0x5ef = 1519 InstrumentsOfVengeance_PendingAttack, AbilityStateReference,
                         source/targets/bonded = Owner@+0x30, options = ZERO)
         + If( NOT HasAdjacentEnemies(Owner@+0x30, Owner@+0x30, 0, false),
               ActivateEffect(Owner@+0x30, 0x3f1 = 1009), null )

et chaque `GetEffectBehavior(direction, first)` est a lui seul un arbre de la taille d'une ability :
`EdgeExtensions$$Rotate(direction, 3)`, `TilesBehindInLine`, `EdgeTilesByDirection`, deux
`GetPersistentData` + deux `SetPersistentData` (cles `String.Concat(<litteral>, index)`),
`Randomize`, trois `SortByFormula(Count(...))` imbriques (tuiles derriere / amis / ennemis),
`First`, `Cache`, `EntityId`, et `AddEffect(0x5ee = 1518 InstrumentsOfVengeance_LocationTarget)`.
S'y ajoute la PHASE 2 : `InstrumentsOfVengeance_AttackAbility$$CreateBehaviour` + `$$AttackLine` +
`$$AttackTargetTiles` + `$$AttackTileBehavior`, et
`InstrumentsOfVengeance_PendingAttackEffect$$GetAttackingUnitSelector`.

Son `.ctor` est une **STATIC-COPY** du MEME preset que `1216` (`statics+0x280`) **sans** les flags
-> `rules = 0x8004` (pas de `CasterHasNotMoved`), `AbilityAttackType = 2`. Sa ligne RESTE dans
`TARGETING_OPTIONS_UNPORTED`.

C'est une tranche d'ampleur comparable a `1217` (#889) a elle seule -- au moins six noeuds neufs
(`EdgeTilesByDirection`, `GetPersistentData`/`SetPersistentData` sous cle composite,
`HasAdjacentEnemies`, `ActivateEffect` sur un effet non porte, `EdgeExtensions.Rotate`) plus une
phase 2 complete. La porter ICI, apres six noeuds DSL et une ability, aurait reproduit exactement
la faute que #889 avait evitee : livrer une moitie. Residu **`#889-r6`**.

## `#889-r5-r3` volet (b) : le natif POSE `1520`, puis il le RETIRE

La fiche opposait deux causes a l'absence de `1520 MartialExemplar_ExtraCritChance` dans
`decisionView.units[].effects` apres le cast : « le natif ne le pose pas » vs « ce canal ne le
publie pas ». Elle exigeait pour trancher « un capteur d'effets INDEPENDANT de `decisionView` ».
Ce capteur **existait et etait deploye** -- `effectsAll` (#231-r) ; c'est maintenant **mesure**, et
non plus seulement dit.

### La mesure (`probe_889r5_martial_exemplar.py --regime survit`, deux runners)

    effectsAll(effectType = 1520) -> count: 1
        { effectType: 1520, ownerId: 84, inOwnerList: false, removed: true }
    effectsAll(TOUS)              -> count: 16, 15 types distincts
        RETIRES = [[1520, 84]]        <- UN SEUL effet retire dans TOUT l'etat
        VIVANTS = 15 couples (type, owner)

Les trois regimes que le hook distingue au couple (`inOwnerList`, `removed`) donnent ici **POSE
PUIS RETIRE**. Le canal n'est pas degenere (16 effets), et `1520` est le **seul** retire : ce n'est
donc pas une expiration generale de fin de tour, c'est propre a cet effet.

⇒ « le natif ne pose pas `1520` » est **FAUX**. Son absence de `decisionView` s'explique par le
RETRAIT : ce canal part d'`EffectsOwnedComponent.ActiveEffectIds`, dont
`IdunBattle.Operations.RemoveEffectOperation$$Execute` sort l'effet (`List.Remove` puis `Removed`
@+0x5f, **sans detruire l'entite** -- exactement ce que `effectsAll` voit encore). **Volet (b) CLOS.**

### Fait neuf : le port GARDE ce que le natif a deja retire -- et la cause est lue

Le port pose `1520` avec `duration_turns = 1` (`runner/abilities/darkangels.py`) et le conserve
(`off_cast = {"84": {"1520": 1}}`) au meme point d'observation.

Les deux soeurs du MEME boss passent des `turns` **differents** a `DSLBehaviors$$AddEffect` :

| ability | appel natif | `turns` |
|---|---|---|
| `1217 TheLionsWrath` | `AddEffect(0x5f2, abilityState, Owner, **null**)` | aucun |
| `1216 MartialExemplar` | `AddEffect(0x5f0, abilityState, Owner, **<DSLFormulas + 0x20>**)` | fini |

(surcharge `(effectType, abilityState, targets, turns: IAmountFormula)`). L'ecart de survie des deux
effets vient donc de la, et non d'un mecanisme d'expiration.

### Ce qui reste, et pourquoi cette mesure ne le tranche PAS

La **valeur** de `<DSLFormulas + 0x20>` -- `0` ou `1` -- que le port ecrit `1`. C'est exactement le
litige ouvert de **`#927-r1`**, et cette mesure en est un **troisieme call-site independant** (les
deux precedents mesurent `maxTargets = 1` et `minAmount = 0`, incompatibles entre eux).

⚠ Elle ne le tranche pas a elle seule : un effet a `turns = 1` pose pendant le tour de son porteur
et retire a la FIN de ce meme tour rendrait la **meme** observation qu'un `turns = 0`, le cast de
`1216` terminant le tour (`FinishUnitTurn`). Le discriminant manquant est une lecture de l'etage de
decrementation, ou une observation ENTRE la pose et la fin de tour -- qu'`applyAction`, atomique, ne
permet pas. A verser a `#927-r1`.
