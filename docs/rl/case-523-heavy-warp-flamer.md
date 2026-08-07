# case-523 — `1227 HeavyWarpFlamer` : la face EXECUTION

`thousSekhetar` « Sekhetar Robot » (Thousand Sons/Chaos, **lineup**) — porteur **UNIQUE** de
l'ability. Profil au kit : `2hmp40 / 2hR3p55`, aucune mecanique.

**Seule la face EXECUTION manquait.** La face DECISION est portee depuis #27
(`playbook/loki_custom.py::HeavyWarpFlamerPlaybook` = `W(HeavyWarpFlamer_LikesAdjacentEnemies) x
|ennemis adjacents a la tuile de la CIBLE|`). 1227 etait absente d'`ABILITY_CLASSES` ->
`AbilityHandler.visit_ActiveAbilityMessage` posait `ported: False` et rendait la main : 0 degat,
0 effet, aucune erreur.

Build de lecture : `rnca9r7q6c` (= `data/symbols/CURRENT`).

Kit gameconfig 1227 : `attackRangeType = Ranged`, `damageProfile = Flame` (`PiercingRatio` 25,
trait `OnFire`), `nrOfHits` **4**, `maxNrOfHits` **9**, `range` **2**, `damageProfile_2 = Psychic`
(constante NON lue par `$$ExecuteBehaviour` — cf. §4, ou le `Psychic` qui compte est le litteral
`0xd` du trigger de la triggered 1546).

## 0. Gate de confrontabilite — porteur HORS pool ET hors catalogue

`rl_duel build --list-pool` ne rend pas `thousSekhetar` (le pool derive du seed BC, capture d'UNE
bataille), et `catalog_inject.py --missing` le liste parmi les unites lineup hors catalogue. Ce
n'est **pas** un refus : aucun `data/unspawnable_rank*.json` n'existe. Il entre en bataille par
`catalog_inject.write_augmented_seed_bc` + `rl_duel build --seed-bc` (`case-92` §6) — la MEME voie
qui a servi a #27.

## 1. Le ctor — forme PRESET STATIQUE COPIE (aucun flag ajoute)

`IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyWarpFlamerAbility$$.ctor` :

```
copie 0x40 octets depuis TargetingOptions statics +0x140        # le PRESET
AActiveAbility$$.ctor(this, &opts, 0)                           # 0 = AbilityAttackType.DirectTargetAttack
```

**Aucun appel a `IdunBattle.Core.Services.TargetingOptions$$.ctor`** : le masque effectif est la
constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor`, lue dans son corps :

| champ | offset | valeur |
|---|---|---|
| `isSelfCasting` | `+0x140` | `0` |
| `range` | `+0x148` | copie de `TargetingRange` statics `+0x18` = `RANGE_FROM_CONFIG` (-> 2) |
| `forceMeleeTarget` | `+0x160` | **`0` = `RangedBool.True`** (l'enum natif est INVERSE : True=0, False=1) |
| `rules` | `+0x168` | **`0x4002`** |

Decomposition exhaustive (aucun bit residuel) :

| bit | regle | statut du port |
|---|---|---|
| `0x0002` | `TargetMatchesDynamicRule` | `GetDynamicInvalidTargetReason` NON surchargee par 1227 -> defaut 0. Degradation PERMISSIVE assumee ; c'est pourquoi 1227 n'entre PAS dans `DYNAMIC_TARGET_RULE_UNPORTED`. |
| `0x4000` | `TargetIsEnemy` | PORTE |

⚠ **Le preset voisin `+0x180` (Fragstorm 1048) ne differe QUE par `forceMeleeTarget`**
(`RangedBool.False`). Recopier le masque de la voisine aurait donne le bon `rules` et le mauvais
regime de PORTEE : `IdunBattle.Core.Services.TargetingQuery$$GetRange` rabat la portee a 1 et force
`onlyAdjacent` quand `ForceMeleeTarget` est vrai ET que le caster est au contact. 1227 EST dans ce
cas ; 1048 non. Lire ability par ability.

1227 n'etait dans AUCUNE des listes du contrat de disjonction (`TARGETING_OPTIONS_UNPORTED`,
`DYNAMIC_TARGET_RULE_UNPORTED`) — verifie PAR LE CODE : aucune migration, aucun compteur a
decrementer. Coherent avec un porteur hors du pool spawnable.

## 2. `$$ExecuteBehaviour` — UN seul noeud terminal

```
dp    = AbilityConfiguration$$GetDamageProfile(config)              # Nullable<DamageProfileType> = Flame
dmg   = AActiveAbility$$MinMaxDamage(this, abilityState)
other = <$$GetOtherTargets, RECOPIE INLINE>                         # cf. §3
chain = DSLSelectors$$SortTargetsByDamagePredictionSelector(
            attacker              = Owner@DSLSelectors+0x30,
            units                 = other,
            ability               = DSLSelectors$$Direct(AbilityOrEffect(this+0x10 = 1227)),
            damage                = dmg,
            hits                  = <DSLFormulas+0x20>,             # = 1, cf. l'encadre
            damageProfileType     = DSLSelectors$$Direct(Nullable(dp)),
            attackerSelectionType = 3)
DSLBehaviors$$ChainLeftOverHitsAttackDamage(
            caster                     = Owner@+0x30,
            firstTarget                = Target@+0x60,
            dmgAmount                  = dmg,
            damageProfileType          = Direct(Nullable(dp)),
            hits                       = $$GetNumTotalHits(this),    # cf. §4
            abilityType                = this+0x10,
            otherTargetSelector        = chain,
            extraHitsAfterTargetKilled = **null**)
-> AActiveAbility$$Execute(this, behaviour)
```

Les noms d'arguments du selecteur sont ceux de la signature native
(`DSLSelectors$$SortTargetsByDamagePredictionSelector(attacker, units, ability, damage, hits,
damageProfileType, attackerSelectionType)`), pas une reconstruction.

> **`<DSLFormulas+0x20>` vaut 1, et ce n'est pas une deduction de contexte.**
> `IdunBattleLogic.Entities.DSLFormulas$$.ctor` alloue cinq formules-constantes et les range :
> `+0x18 <- 0`, `+0x20 <- 1`, `+0x28 <- 2`, `+0x30 <- 100`, `+0x38 <- -1` (la structure du ctor est
> lisible meme si ghidra mislabel les `.ctor` gshared). Corroboration INDEPENDANTE : le meme `+0x38`
> est l'operande de `DSLFormulas$$Subtract(a, b) = SumAmount(a, MultiplyAmount(b, +0x38))`, qui n'a
> de sens qu'a `-1` ; et le meme `+0x20` sert d'increment dans
> `HeavyWarpFlamer_AttackTrackingAbility$$CreateBehaviour`
> (`SetPersistentData(..., Sum(GetPersistentData(...), +0x20))`), ou il ne peut valoir que 1.

**Quatre ecarts LUS avec `1048 FragstormGrenadeLauncher`**, qui monte la MEME feuille — aucun n'est
copie de la voisine :

| | 1227 HeavyWarpFlamer | 1048 FragstormGrenadeLauncher |
|---|---|---|
| ensemble de report | `AdjacentFriends(TARGET) & SurroundingEnemies(CASTER, range)` | `SurroundingEnemies(Owner, range) - Target` |
| tri amont | AUCUN | `SortByFormula(PV, ascending)` — no-op mesure (#489) |
| `hits` du selecteur de prediction | `<DSLFormulas+0x20>` = **1** | `Direct(nrOfHits)` |
| `hits` de la feuille | noeud DYNAMIQUE `$$GetNumTotalHits` | `Direct(nrOfHits)` |

Communs : `extraHitsAfterTargetKilled` **null** (donc `extra = 0` dans `GetLeftOverHits`) et
l'execution par `AActiveAbility$$Execute`.

## 3. `$$GetOtherTargets` — l'intersection de DEUX volets

```
Damageable( AdjacentFriends(unit = Target@DSLSelectors+0x60, unique = 1, unitSelectionType = 3) )
op_BitwiseAnd
SurroundingEnemies(unit = Caster@DSLSelectors+0x48,
                   range = Get(GetNumberConstant(0x16 = range)), unique = 1, unitSelectionType = 3)
```

Les deux surcharges sont tranchees par leurs **XREFS ENTRANTES** (chacune existe en plusieurs corps
homonymes ; ghidra les nomme pareil) :

* `IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(unit, unique, selectionType)` (3 args) =
  `Friends(reference = unit, Units(AdjacentTiles(unit), unique, sel) op_Subtraction unit, sel)` ->
  la **REFERENCE d'equipe EST le centre**. Le centre est ici la CIBLE : ce sont donc les allies DE
  LA CIBLE = les **ennemis du caster**, anneau d'adjacence, cible EXCLUE.
* `IdunBattleLogic.Entities.DSLSelectors$$SurroundingEnemies(unit, range, unique, selectionType)`
  (4 args) = `Enemies(reference = unit, Units(SurroundingTiles(unit, includeCenter = 1, range)
  op_Subtraction Tiles(unit), unique, sel), sel)` -> le MEME selecteur est centre ET reference.
  **Pas d'`Unobscured`** dans cette surcharge.

⚠ **Les deux `reference` sont OBLIGATOIRES cote port.** `AdjacentFriends`/`SurroundingEnemies` y
collapsent `reference=None` sur `ctx.caster` ; avec le centre sur la CIBLE, ce collapse rendrait le
camp **INVERSE** (les allies du caster), sans erreur.

⚠ Le `Damageable` ne porte QUE sur le volet `AdjacentFriends` (le natif fait
`op_BitwiseAnd(Damageable(adj), surrounding)`), sans effet observable — une intersection ne peut pas
rajouter de mort — mais on ecrit ce qui est lu.

⇒ « les ennemis du caster ADJACENTS a la cible ET a distance <= `range`(2) du CASTER ». C'est la
geometrie que recompense l'utilite IA `HeavyWarpFlamer_LikesAdjacentEnemies` (#27).

## 4. `$$GetNumTotalHits` — un noeud DYNAMIQUE, et une cle PARTAGEE avec la triggered 1546

```
$$GetNumBaseHits  = Direct(GetNumberConstant(0x2f = nrOfHits))          # appelee par PERSONNE
$$GetNumExtraHits = Min( GetPersistentData(AbilityOrEffect(1227), Owner@+0x30, "PSYCHIC_ATTACKS_KEY"),
                         Subtract( Direct(GetNumberConstant(0x48 = maxNrOfHits)),
                                   Direct(GetNumberConstant(0x2f = nrOfHits)) ) )
$$GetNumTotalHits = Sum( Direct(GetNumberConstant(0x2f)), $$GetNumExtraHits() )
```

`DSLFormulas$$Subtract(a, b)` construit `SumAmount(a, MultiplyAmount(b, <+0x38 = -1>))` = `a - b`
(LU) : le plafond est `maxNrOfHits - nrOfHits`, pas l'inverse. => `[4, 9]` a la config courante.

Le compteur est alimente par la TRIGGERED `1546 HeavyWarpFlamer_AttackTracking`
(`...Triggered.Loki.HeavyWarpFlamer_AttackTrackingAbility`), lue en entier :

```
CreateTrigger :  On(0x9) & <clause partagee DSLTriggers+0x28>
                       & NOT AreEqual(Attacker, Owner@+0x30)
                       & AreFriends(Attacker, Owner@+0x30)
                       & CurrentAttackDamageProfilesContain(DamageProfileType.Psychic = 0xd)
                 | On(EventTriggerType.TurnEnd = 0x17)
CreateBehaviour: triggerType == TurnEnd -> ClearPersistentData(AbilityOrEffect(1227), Owner, KEY)
                 sinon                  -> SetPersistentData(AbilityOrEffect(1227), Owner, KEY,
                                                Sum(GetPersistentData(...), <DSLFormulas+0x20 = 1>))
```

**DEUX lectures qui ne se devinent pas :**

1. **L'`AbilityOrEffect` de la TRIGGERED est le litteral `0x4cb` = 1227**, pas son propre id 1546.
   Le decompile ne le montre pas (ghidra perd le registre) ; il est LU a l'assembleur —
   `HeavyWarpFlamer_AttackTrackingAbility$$CreateBehaviour+0x49` porte `mov edx, 0x4cb` juste avant
   l'`op_Implicit`, la ou `HeavyWarpFlamerAbility$$GetNumExtraHits+0x4a` porte `mov edx,[rbx+0x10]`
   (le champ de type de l'active). Les deux cotes adressent donc la MEME cle composite —
   `AbilityOrEffect$$GetPersistentDataId` rend l'ordinal du premier de ses trois `Nullable`
   renseigne. Sans cette lecture on aurait ecrit `(1546, ...)` d'un cote et `(1227, ...)` de
   l'autre : le mecanisme aurait ete inerte, **sans erreur**.
2. **La `dataKey` est la chaine `"PSYCHIC_ATTACKS_KEY"`.** Le decompile n'affiche qu'un
   `DAT_183370b30` (slot de litteral IL2CPP) ; il est resolu par
   `data/symbols/rnca9r7q6c/metadata/string_literals.tsv` ligne `13388 0x3370b30
   "PSYCHIC_ATTACKS_KEY"`. Les xrefs de ce slot sont EXHAUSTIVEMENT ces deux fonctions -> cle privee
   a la paire.

⇒ semantique : **chaque attaque d'un ALLIE (jamais du porteur) qui contient le profil `Psychic`
ajoute 1 coup au prochain `HeavyWarpFlamer`, plafonne a `maxNrOfHits`, remis a zero a la fin du
tour.**

**ETAT DU PORT** : le noeud de LECTURE est monte pour de vrai (il interroge `ctx.persistent_data`,
donc le `PersistentDataComponent` de l'ECS). L'ECRITURE n'existe pas tant que **1546 n'est pas
portee** (residu **#523-r1**) -> la cle est absente, `GetPersistentDataFormula$$Calculate` rend son
`out` par defaut = 0, et `GetNumTotalHits` vaut `nrOfHits`. Le jour ou 1546 est portee, ce noeud lit
la valeur **sans changer d'une ligne** — les trois regimes de valeur sont figes par
`test_523_heavy_warp_flamer_offline.py`.

## 5. Ce que le port ecrit

`engine/runner/abilities/thousandsons.py` : `heavy_warp_flamer_other_targets`,
`heavy_warp_flamer_num_extra_hits`, `heavy_warp_flamer_num_total_hits`, `heavy_warp_flamer_tree`,
`HeavyWarpFlamerAbility`. Cablage : `handler.py` (registre), `attack_type.py`
(`DirectTargetAttack`), `TARGETING_OPTIONS` sur la classe.

`probe_181` : **125/125, 0 manquante** (124 avant). `test_ability_registry_ratchet` : 9 passed.
Audits regeneres : `combat-ability-coverage.md` **120 -> 121 ported**, **55 -> 54 no-op**,
`DAMAGE` 26 -> 25.

## 6. Le montage live — la geometrie est FABRIQUEE, avec DEUX contre-exemples

L'ensemble de report a deux volets ; un montage ou ils coincident ne prouve rien. Sur `MC1_67`
(7x9, tout jouable), `--place` / `--a-place` :

```
C = caster (0,0)     ADJACENT A AUCUN ennemi, sinon `ForceMeleeTarget` rabat la portee a 1
T = cible  (0,2)     d(C,T) = 2 = range
B = (1,2)            adjacent a T, d(C,B) = 2   -> ELIGIBLE
D = (0,3)            adjacent a T, d(C,D) = 3   -> EXCLU par `SurroundingEnemies(C, 2)`
E = (2,0)            d(C,E) = 2, NON adjacent a T -> EXCLU par `AdjacentFriends(T)`
```

Deux choix de montage sont des MESURES, pas des preferences :

* **la CIBLE est `astraBullgryn`, pas `eldarRanger`.** `AttackHitsWithModifiersFormula` (foyer
  PARTAGE, hors #523) rabat la salve a **2** coups sur `eldarRanger` et a **3** sur `astraBullgryn`
  — mesure, port ET natif d'accord dans les deux cas. Avec H = 2, `max(0, H - k - 1)` ne peut JAMAIS
  etre > 0 : le regime de chaine serait INEXERCABLE.
* **le RELAIS a ses propres PV** (`--unit-stat`, 90 000). Un relais qui meurt au 1er coup n'emet
  plus rien : son compte d'events ne dirait PAS combien de coups lui ont ete demandes.

## 7. Ce qui a ete mesure

`python scripts/python/probe_523_heavy_warp_flamer.py` (sept verdicts). Toutes les lignes ci-dessous
sont `rc=0`.

| regime | board / seed | montage | chaine offline == live | report | per-coup |
|---|---|---|---|---|---|
| survivant | MC1_67 / 4242 | `hp-target 60000` | `[u79]` | 0 | `[3452, 3231, 3529]` des DEUX cotes |
| chaine | MC1_67 / 4242 | `hp-target 3300`, relais 90 000 | `[u79, u81]` | 1 | u81 : `9153` des DEUX cotes |
| fort overkill | MC1_67 / 4242 | `hp-target 900`, relais 90 000 | `[u79, u81]` | 1 | u81 : `9153` des DEUX cotes |
| tri (2 relais) | MC1_67 / 4242 | relais A 90 000 / relais B 3 300 | `[u79, u81]` (A) | 1 | u81 : `9153` |
| tri (2 relais) | MC1_67 / 4242 | relais A 90 000 / relais B **100** | `[u79, u83]` (**B**) | 1 | u83 : `100` |
| geometrie 2 | MC1_67 / 777 | caster (2,2), cible (0,1) | `[u79, u81]` | 1 | `3355` des DEUX cotes |
| board 2 | C1_35 / 31337 | 2 relais | `[u79, u83]` | 1 | `3300` |

**Le couple qui MORD est celui du tri** : meme geometrie, meme ordre source, seul le PV du relais B
change (3 300 -> 100) et **la chaine bascule de A vers B, des DEUX cotes**. Un port qui aurait saute
`SortTargetsByDamagePredictionSelector` aurait rendu le premier de l'ordre geometrique dans les deux
cas.

**Face DECISION confrontee au meme montage** : le port rend `get_invalid_target_reason` == 0
exactement sur les entites qu'`abilityTargets(...).fromHere` accepte, et le bon bit sur les autres —
`0x4000 TargetIsEnemy` sur le caster lui-meme (le masque ne porte pas `CasterIsPossibleTarget`),
`0x8000000 TargetIsInRange` a d = 3, `0x1000000 TargetIsUnobscured` sur la geometrie 2.

⚠ **UN ECART DE FORME, PAS DE VALEUR, ET IL EST DOCUMENTE** : sur une cible TUEE, le port applique
tous ses coups la ou le natif cesse d'emettre des que
`UnitExtensions.HasFlag(target, UnitFlag.Overkilled)` est vrai a l'entree
d'`IdunBattle.Operations.ApplyDamageOperation$$Execute`. La sequence LIVE est donc un **PREFIXE** de
la sequence offline clampee, dont la queue est NULLE — c'est le critere assertionne, ni plus laxiste
ni plus strict que le natif.

⚠ **Le residu #505 (`max(0,H-k-1)` vs `max(0,H-k)`) NE se reproduit PAS ici** : mesure dans les DEUX
regimes d'overkill (`hp-target 3300` = +4,6 % d'excedent, `hp-target 900` = +283 %), le relais
SURVIVANT recoit **1** coup, ce que rend `max(0, H-k-1)` = 1 et non `max(0, H-k)` = 2. Point de
mesure supplementaire pour #505, sur une ability et un profil de degat nouveaux.

## 8. Residu

* **#523-r1** — la triggered `1546 HeavyWarpFlamer_AttackTracking` n'est pas portee. Elle est LUE en
  entier (§4) ; tant qu'elle manque, le compteur `(1227, "PSYCHIC_ATTACKS_KEY")` reste a 0 et
  `GetNumTotalHits` rend `nrOfHits`. Le montage qui la confronterait : un allie du porteur qui
  attaque avec un profil `Psychic` (ex. `thousAhriman` / `1102 Doombolt`, deja porte) AVANT le cast
  de 1227, puis lecture du nombre de coups. Meme forme que les phases 2 non portees de 1069 (#491-r1)
  et 1141 (#503-r1).

## Fichiers

* port : `scripts/python/engine/runner/abilities/thousandsons.py` (section HeavyWarpFlamer)
* cablage : `.../abilities/handler.py`, `.../abilities/attack_type.py`
* mesure : `scripts/python/probe_523_heavy_warp_flamer.py`
* gardes : `scripts/python/tests/engine/runner/test_523_heavy_warp_flamer_offline.py` (10),
  `.../test_523_heavy_warp_flamer_live.py` (11)
