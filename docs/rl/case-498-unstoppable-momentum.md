# #498 — `1152 UnstoppableMomentumReworked` : la charge en ligne, du no-op silencieux au bit-exact

`orksNob` « Tanksmasha » (Orks, HERO, **confirmé au pool** rank 17) ; 4 autres porteurs, tous npc
(`orksBossNob`, `orksBossNobLEG`, `orksBossNobLHE`, `orksNpcNob`). Build `rnca9r7q6c`.

**Avant** : 1152 était absente d'`ABILITY_CLASSES` → la décision choisissait le cast, l'exécution
l'ignorait. 0 dégât, 0 effet, 0 déplacement, **aucune erreur**.
**Après** : entrée au registre, avec son `TARGETING_OPTIONS` (migré) et son `ABILITY_ATTACK_TYPE`
dans le même commit ; confrontée live sur **6 montages**, **bit-exacte sur 7 étages**.

---

## 1. Ce que le décompilé dit — et ce qu'il CONTREDIT dans la classification héritée

La colonne `categorie` de l'audit annonçait `DAMAGE(DirectDamage)`. **C'est juste ici**, mais
l'`ExecuteBehaviour` n'est PAS un arbre DSL d'attaque : c'est une **BOUCLE IMPÉRATIVE** qui exécute
un PETIT arbre DSL à chaque pas. `case-220-classification-campaign.md` le classait déjà
« charge-driver en ligne IMPÉRATIF (Move/Push hex-par-hex, dégât scalé per-hex, displacement ami
sans dégât) » (§6.13) — la RE **confirme** cette classification, mot pour mot.

Il n'existe **aucune** version antérieure de l'ability dans le build : `search_symbols_by_name` sur
`UnstoppableMomentum` ne rend que des symboles `…Reworked…` (ability, playbook, visuals). Le suffixe
`Reworked` est donc **inexploitable comme point de comparaison** sur ce build — piste évaluée,
close.

### 1.1 `…UnstoppableMomentumReworkedAbility$$.ctor`

```
this+0xf0 = 10                                        // MAX_CHARGE_TILES
TargetingOptions..ctor(&opts, selfCast: 0, &<TargetingRange statics+0x30>,
                       forceMeleeTarget: 1, rules: 0x10120040, 0, 0)
AActiveAbility..ctor(this, &opts, 0)                  // AbilityAttackType.DirectTargetAttack
```

Surcharge **FLAGS DIRECTS** (7 arguments) : le 3ᵉ argument est un preset de **PORTÉE**
(`TargetingRange`), pas un preset d'options — le littéral `0x10120040` **EST** le masque, aucun
`| preset.rules`. Décomposition :

| bit | règle | effet porté |
|---|---|---|
| `0x40` | `TargetIsTile` | cast TILE-TARGET (domaine tuile, règle non portée par le filtre statique → inerte, délibéré) |
| `0x20000` | `TargetTileIsFreeOrEnemy` | la tuile visée doit être LIBRE ou porter un ENNEMI |
| `0x100000` | `AllowSteppableUnit` | permission (occupant `Steppable` ne bloque pas) |
| `0x10000000` | `CasterCanMove` | refus si le caster ne peut plus bouger |

`forceMeleeTarget = 1` = `RangedBool.False` (l'enum natif est **INVERSE**) ; portée
`TargetingRange statics+0x30` = **ADJACENT** — c'est ce qui donne les « 6 directions » de l'i2.

⚠ **Le masque vivait déjà dans `TARGETING_OPTIONS_UNPORTED`, et il était JUSTE.** Il a été **RE-LU
au décompilé avant migration** (jamais recopié) : bit-identique champ pour champ. Il a **MIGRÉ** vers
la classe du registre — c'est le **contrat de disjonction** : une ability a UNE source de masque.

### 1.2 `$$CanStillBeUsed(caster, amountOfTimesAlreadyUsed)`

`return amountOfTimesAlreadyUsed == 0` — une seule fois par tour. C'est déjà le **défaut** du port,
rien à écrire.

### 1.3 `$$ExecuteBehaviour(abilityState, entities)`

```
Execute( AddFlag(Caster@0x48, 0x19 = UnitFlag.Undisplaceable) )                       // 1
line   = TilesBehindInLine( CasterTile@0x50, Target@0x60, settings{+0x10=1, +0x11=1}, 0 )
cache  = Cache( First(line, amount: 10), matchAbilityEntities: true )                // 2
vector = VectorFromAdjacentTo( Get(GetMainTile(caster)), Get(target), length: 1 )    // 3
for (index = 0; index < 10; index++) {                                               // 4
    tile = SelectTile( AtIndex(cache, index) );  if (tile == null) return;
    if (!ExecuteBehaviourStep(abilityState, entities, vector, tile, index)) break;
}
Execute( RemoveFlag(Caster@0x48, 0x19) )                                             // 5
```

Trois points **non devinables** :

* `settings` : le ctor écrit `*(short*)(obj + 0x10) = 0x101`, soit (little-endian) `+0x10 = 1`
  (`checkWalkable`) et `+0x11 = 1` (`updateReference`) — **même couple** que
  `DarkTalonStrikeAbility$$GetTilesInLine`. `checkWalkable = 1` arme AUSSI le gate d'ÉLÉVATION (il
  vit dans la branche walkable d'`IdunBattle.Core.Services.TileUtil$$IsTileValidForList`), et la
  ligne **s'arrête au 1ᵉʳ échec** : c'est exactement le « until he hits an obstacle » de l'i2.
* le `Cache` est **LOAD-BEARING** : le caster BOUGE pendant la charge, donc ré-évaluer
  `CasterTile@0x50` à chaque pas donnerait une ligne différente à chaque itération.
* le `vector` est calculé **UNE fois, hors boucle** — donc sur la position de DÉPART du caster.

⚠ `DSLSelectors$$First(source, amount, ignoreForcedTargets)` prend un **`amount`** (nom de paramètre
natif) — les N premiers. Le nœud `First` du port (`entities/selectors/units.py`) est, lui, un
**`AtIndex`** (`PickAtIndexSelector`, UN élément) : les deux ne sont **pas** le même nœud natif. La
troncature à 10 est donc COLLAPSÉE ici (`[:MAX_CHARGE_TILES]`) plutôt que routée par un nœud qui ne
serait pas le bon. Signalé, hors périmètre.

### 1.4 `$$ExecuteBehaviourStep(state, entities, startVector, tile, traversedSteps)`

```
if (UnitExtensions.IsDead(caster))                     return false;
if (!TileExtensions.IsWalkable(tile, true))            return false;
if (!TileExtensions.IsNeighbourOf(tile, GetMainTile(caster)))  return false;
MOVE:
if (TileExtensions.IsEmptyOrSteppable(tile, caster))   return Move(caster, tile);
Execute( RemoveEffect( Units(Get(tile), unique: 1, sel: 0),
                       Nullable(0x425 = GeminaeSuperia_JustSummonedEffect) ) );
enemies = Enemies( Caster@0x48, Units(Get(tile), unique: 0, sel: 3), 3 );
Attack(enemies, abilityState, entities, traversedSteps);
SuppressOrStun(enemies, abilityState, entities);
if (Push(tile, entities, startVector))                 return true;      // SwitchPosition
if (UnitExtensions.IsDead(caster))                     return false;
if (!UnitExtensions.CanMove(caster))                   return false;
if (!TileExtensions.IsEmptyOrSteppable(tile, caster))  return false;
goto MOVE;                                                               // -> Move(caster, tile)
```

Le `goto` saute **directement au bloc `Move`**, ce n'est pas une boucle de re-test.

### 1.5 `$$Attack` — le terme per-hex

```
dmg = Sum( MinMaxDamage(abilityState),
           Direct( GetVariableForLevel(8 = extraDmg) * traversedSteps ) )
Execute( AttackWithAttackDamage( Caster@0x48, target, dmg, GetDamageProfile(),
                                 GetNumberConstant(0x2f = nrOfHits), abilityState,
                                 <options ZERO>, selectionType: 2 ) )
```

⚠ `traversedSteps` est **l'index de la boucle, 0-BASED** : au 1ᵉʳ pas (l'ennemi est ADJACENT au
caster) le bonus vaut `extraDmg * 0 = 0`. C'est exactement l'i2 (« for each hex traversed **from the
starting hex** to the enemy »). Famille **ATTACK** (`DSLBehaviors$$AttackWithAttackDamage`, PAS
`AttackWithAbilityDamage`) → crit/block/extra-hits actifs.

### 1.6 `$$SuppressOrStun` — les deux branches, et leurs constantes CROISÉES

```
suppressRounds = GetNumberConstant(0x69 = effectTurns)     // 1
stunRounds     = GetNumberConstant(0x6a = effectTurns_2)   // 1
Execute( If( NOT CanBeDisplaced(target),
             AddEffect(0x48a = Stunned, …, TurnsFromRounds(suppressRounds)),
             AddEffect(0x429 = Pinned,  …, TurnsFromRounds(stunRounds)) ) )
```

⚠ **Les branches sont CROISÉES par rapport aux noms de constantes** : la branche BIG TARGET
(`!CanBeDisplaced`) lit `effectTurns` et pose `Stunned` ; la branche ordinaire lit `effectTurns_2`
et pose `Pinned` (« Suppressed » côté UI). Transcrit **VERBATIM** — inerte tant que les deux valent
`1`, mais écrire l'inverse serait un fork de port silencieux le jour où elles divergent.

### 1.7 `$$Push` — cinq `PathDefinition`, deux `Randomize`, et une symétrie qui sauve la mise

```
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
```

`IdunBattleLogic.Utils.Hex.RelativeDirection` = `0=Forward, 1=ForwardRight, 2=BackwardRight,
3=Backward, 4=BackwardLeft, 5=ForwardLeft` (enum **LU** dans
`data/symbols/<build>/frida/enums.tsv`, jamais déduit). `nodes` ne contient **qu'un** élément à
chacun des cinq call-sites → le path fait exactement UN pas, et `includeStartTile = false` exclut la
tuile de départ. Priorité : les deux diagonales AVANT (ordre tiré au sort), puis les deux diagonales
ARRIÈRE (idem), puis TOUT DROIT. **`Backward` (vers le caster) n'est JAMAIS candidat.**

⚠ **Le SENS de rotation est INOBSERVABLE ici, et ce n'est pas une approximation** : les deux premiers
rangs sont des **paires symétriques** (`{+1, +5}` et `{+2, +4}` autour de `Forward`), donc échanger
droite et gauche permute deux éléments d'un ensemble **immédiatement mélangé** par `Randomize`. Le
3ᵉ rang (`Forward`) est invariant. Aucun besoin de trancher la convention native — et le live le
confirme : les tuiles de poussée concordent, port et natif, sur les 6 montages.

`Push` rend **`true` UNIQUEMENT sur le `SwitchPosition`** — c'est ce `true` qui fait CONTINUER la
charge sans `Move`, puisque l'échange a déjà porté le caster sur la tuile. Un `PushToPrioritizedTiles`
réussi rend **`false`**, et c'est le `Move` d'après qui fait avancer le caster sur la tuile libérée.

`IdunBattle.Operations.DisplaceUnitOperation$$FindTileToPushToPrioritizedTiles(target, tiles)` :
liste à **UN** élément → rendue TELLE QUELLE (aucun re-test) ; `N > 1` → filtrée par
`IsEmptyOrSteppable` puis premier ; vide → null. Ici `prioritizedTiles` est un `Get(dest)` d'UNE
tuile déjà passée par `CanAddUnit` → première branche.

---

## 2. Ce que le port ajoute au moteur

| fichier | ajout |
|---|---|
| `engine/runner/abilities/loki/momentum.py` | **NOUVEAU** — la classe, la boucle de charge, `Move`/`Attack`/`Push`/`SuppressOrStun`, la table cyclique des 6 directions cube et `RelativeDirection` |
| `engine/runner/abilities/behaviours/movement.py` | feuille `PushToPrioritizedTiles` (`DSLBehaviors$$PushToPrioritizedTiles` → `DisplaceUnitBehaviour(direction: 2)`) |
| `engine/runner/operations/displace.py` | mode `prioritized_tiles` de `DisplaceUnitOperation` = le **case 2** du switch natif (`FindTileToPushToPrioritizedTiles`) ; tout l'aval (`MoveUnit` → `AddTilesMoved` → `On(UnitDisplaced)`) est **partagé**, comme dans le natif |
| `handler.py` / `attack_type.py` / `targeting.py` / `loki/__init__.py` | câblage : registre, `AbilityAttackType.DirectTargetAttack`, **migration** du masque hors de `TARGETING_OPTIONS_UNPORTED` |

**Frontière #149** respectée : l'ossature (boucle, gates de tuile, choix de la tuile de poussée) est
IMPÉRATIVE **parce que le natif l'est** ; les EFFETS passent par les feuilles DSL portées
(`AttackWithAttackDamage`, `AddEffect`, `RemoveEffect`, `MoveUnit`, `SwitchPosition`,
`PushToPrioritizedTiles`).

---

## 3. Validation live — 6 montages, 7 étages, bit-exact

`probe_498_unstoppable_momentum.py` (`--phase ligne|bigtarget|allie|crit|block|switch|all`), board
`MC1_67`, seed 777, positions **DRIVÉES** par `--place`/`--a-place` (jamais subies).

| étage | ce qu'il isole |
|---|---|
| E1 CÂBLAGE | `abilityTargets(...).fromHere` non vide **et** `last['ported'] is True` |
| E2 TRAJET | position finale du caster, offline == live |
| E3 DÉGÂT | dégâts **par cible et par coup**, offline == live |
| E4 SCALING | linéarité de `extraDmg × traversedSteps` (jamais un scalaire fitté) |
| E5 EFFETS | `Pinned` / `Stunned`, par cible |
| E6 DÉPLACEMENT | tuile finale des cibles poussées |
| E7 AMI ÉPARGNÉ | l'ami est DÉPLACÉ, sans coup ni effet négatif |

Résultats (**0 écart sur les 6 phases**) :

| phase | trajet | dégâts (off == live) | effets | poussées |
|---|---|---|---|---|
| `ligne` | (3,2) → (3,8), **6 pas** | `{u79:[4612], u81:[4622]}` | `Pinned`, `Pinned` | (4,3) / (2,4) |
| `bigtarget` | (3,2) → (3,2), **1 pas** (charge ARRÊTÉE) | `{u79:[5534]}` | **`Stunned`** | aucune (BigTarget) |
| `allie` | (3,2) → (3,8), 6 pas | `{u81:[4612], u83:[7217]}` | `Pinned` ×2 | (4,3) / (2,5) ; **ami (3,4) → (4,4)** |
| `crit` (100 %) | idem `ligne` | `{u79:[2064], u81:[2074]}`, `did_crit=True` | `Pinned` ×2 | idem |
| `block` (100 %) | idem `ligne` | `{u79:[864], u81:[874]}`, `did_block=True`, `rolls=[1364/1374]` | `Pinned` ×2 | idem |
| `switch` | (1,0) ⟷ (0,0) **échange** | `{u79:[4612]}` | `Pinned` | aucune (`SwitchPosition`) |

`extraDmg` mesuré = **99/hex** : terme **0** au pas 0, **99** au pas 1, **198** au pas 2 —
strictement linéaire, sur deux montages indépendants.

### 3.1 Trois contre-épreuves — chacune fait ROUGIR le probe

Un accord ne prouve rien si le contrôle ne peut pas rougir. Trois mutations posées puis retirées :

| mutation | effet mesuré |
|---|---|
| `flat = 0` (terme per-hex désarmé) | u81 offline **4523** vs live **4622** — écart **99 exactement** ; **2 échecs** (E3 + E4) |
| `Enemies(...)` retiré du sélecteur d'attaque | l'ami prend `[4622]` + `Pinned` ; **7 échecs** (E3, E5, E6, E7) |
| branches du `If(NOT CanBeDisplaced)` inversées | BigTarget reçoit `Pinned` au lieu de `Stunned` ; **1 échec** (E5) |

La première lève le seul doute qu'un lecteur pouvait avoir : l'écart de base entre les deux cibles
vaut 10 en apparence (4612 / 4622), ce qui n'est **pas** 99 — parce que les deux tirages RNG sont
indépendants. Sans le terme, le port rend 4523 : le +99 est bien appliqué **et nécessaire**.

### 3.2 Un écart DIAGNOSTIC qui n'en est pas un

Sur les cibles portant `LivingMetal` (`necroWarden`), le HP **live** post-cast remonte au maximum
alors que le HP offline porte le dégât. Cause **mesurée** : le cast TERMINE le tour du caster
(`AddFlagsAfterAbilityExecution`), donc le tour adverse démarre et `LivingMetal` régénère
`livingMetalHp = 10 %` du max — largement de quoi effacer 4 622. Le port offline, lui, ne joue pas
le tour adverse. **E3 (le dégât émis) et E6 (les positions) concordent** : ce n'est pas un écart de
port, c'est le turn-flow qui suit le cast.

### 3.3 Deux cobayes FIGÉS réparés — trouvés au rebase, et c'est le gisement de `1c6145a7`

La migration hors de `TARGETING_OPTIONS_UNPORTED` **casse tout cobaye qui FIGE le contenu de cette
table** — elle RÉTRÉCIT à chaque port, et la péremption est donc *programmée*. Le rebase a rendu
**4 rouges, tous réels** :

| fichier | ce qui cassait | réparation |
|---|---|---|
| `tests/engine/test_433_r4_r2_r1_r2_ability_range_offline.py` | `POOL_ABILITIES_WITHOUT_COMBAT_CLASS` portait `1152` → `manquants` **et** `intrus` non vides | `1152` retirée de la liste, inscrite dans la ligne des SORTIES (7ᵉ depuis #487) |
| `tests/engine/test_270r1_volet2_dict_keys_enum_offline.py` | le snapshot du volet 2 portait `(1152, (269615168, …))` → **3** tests rouges (value-preserving, cardinalités, lookup par int brut) | entrée retirée, **valeur relue au ctor avant retrait**, cardinalité 38 → 37 (122 → 121) |

Les deux fichiers suivent **exactement** le patron des six sorties précédentes
(1027 / 1048 / 1068 / 1069 / 1087 / 1088) : rien n'est affaibli, la valeur est **relue**, et le
commentaire dit POURQUOI. Balayage complet de `\b1152\b` sur `scripts/python/**` : **aucun autre
cobaye figé** — les deux probes qui la citent encore le font comme *ability non régulière*
(`probe_419r1tr14r5r2r2`) et comme entrée `activeAbilities` du gameconfig (`probe_579`), deux
propriétés que la migration ne touche pas.

⚠ **Ce gisement est structurel, pas accidentel** : `1c6145a7` (fix #433) l'a documenté trois jours
plus tôt sur `1069`, et il se rouvrira au prochain port. Le seul contrôle qui le voit est **le
re-jeu APRÈS rebase** — les tests concernés ne sont pas dans le périmètre « naturel » d'un port.

### 3.4 Tests de garde rejoués

* `tests/engine/runner/test_unstoppable_momentum_live.py` — **9 passed** (17,7 s), avec
  `DECLENCHEUR` au niveau module (déclaré LARGE : tout `engine/**` + le socle `conftest`).
* `test_thunderous_assault_push_live.py` + `test_489_fragstorm_grenade_launcher_offline.py` —
  **8 passed** (gardes des deux foyers partagés touchés : `displace.py`, `attack_type.py`).
* `test_targeting_options_sources.py` + `test_287r11r1_regles_ciblage_offline.py` — **26 passed**.
* `probe_181_targeting_gaps.py` — **108/108, 0 manquante** ; `ABILITY_ATTACK_TYPE` — **0 manquant**.
* Cliquets structurels : `probe_313_enum_mirror_bijection` (34 mirrors, 0 dette),
  `probe_270r4r2_cycles_imports` (0 cycle), `probe_270r4r2_import_en_premier` (201/201),
  `probe_433_r1_identity_shortcircuit` (OK), `probe_273_gitignored_inputs --only-scan` (OK),
  `probe_365` (OK), `probe_486r15_declencheurs_tests` (ce fichier n'est **pas** en faute).

---

## 4. Ce qui N'EST PAS couvert

* **Face DÉCISION** : `$$CanContinue` (`CanBeDisplaced(Units(nextTile)) | IsCanAddUnit(nextTile)`),
  `$$GetAllTilesInLine` et `IdunBattle.AI.Playbook.Loki.UnstoppableMomentumReworkedPlaybook$$EvaluateNonComparable`
  ne sont **pas** portés — aucun n'est appelé par `ExecuteBehaviour`. Résidu **#498-r1**.
* **`extra_hits`** : le kit annonce la mécanique, mais `nrOfHits = 1` et aucun des 6 montages n'a
  produit de coup additionnel (`additional_hits` toujours vide). La face est donc **non exercée**,
  pas « validée ». Elle passe par le foyer PARTAGÉ `execute_ability_attack`, déjà gardé ailleurs.
* **`UnitFlag.Undisplaceable`** posé/retiré autour de la charge. ⚠ La phrase qui vivait ici
  (« inerte : **aucun étage porté ne le lit** ») est **PÉRIMÉE depuis #498-r3** : les six miroirs
  runner d'`IdunBattle.Entities.UnitExtensions$$IsDisplaceable` le lisent désormais, par le foyer
  `runner/components.py::unit_extensions_is_displaceable`. Ce qui reste vrai, et qui est la VRAIE
  raison de l'inertie : le flag n'a qu'**un seul écrivain** et il ne porte que sur le **caster**,
  que les gates de sa propre charge n'évaluent jamais. Il mordrait dès qu'un déplacement viserait
  ce caster **pendant** sa charge. Détail : `case-498-r3-is-displaceable-quatre-conditions.md`.
* **`UnitExtensions$$CanMove`** : réduction NOMMÉE à `not Immovable` (le port n'a pas d'état
  « immobilisé » distinct). Permissive ; le vrai verrou reste `IsEmptyOrSteppable` puis `IsFreeTile`.
* **`TileExtensions$$IsTemporary`** (gate du `SwitchPosition`) : gate **inerte**, le port n'a pas de
  tuile temporaire.
* **Charge tronquée par un MUR** (et non par le bord du plateau ou un BigTarget) : non montée.
  `check_walkable=True` la porte, mais aucun montage ne l'exerce.
* **Un summon `Steppable` sur la ligne** : le port passerait par la branche `IsEmptyOrSteppable` →
  `Move` direct, sans attaque. Non monté.

---

## 5. Résidus

| # | sujet |
|---|---|
| **#498-r2** | **FERMÉ par #498-r3.** `IsDisplaceable` testait QUATRE refus là où le port en portait DEUX. Re-dérivé : **neuf** miroirs (pas cinq), et `SwitchPositionOperation` n'en portait **aucun**. Corrigé par un foyer unique, confronté LIVE. |
| **#498-r3** | **FERMÉ (cette tranche).** `docs/rl/case-498-r3-is-displaceable-quatre-conditions.md`. |
| **#498-r4** | **OUVERT.** Les deux miroirs de la face **DÉCISION** (`MortisRoundPlaybook._is_displaceable`, `ItItchesPlaybook._is_displaceable`) portent les trois traits mais pas `HasFlag(0x19 UnitFlag.Undisplaceable)` ni la tête `EntityType == Unit` : leur substrat (`Scene` / `NCContext`) ne publie que quatre `UnitFlag`. Direction PERMISSIVE. |
| **#498-r1** | **Face DÉCISION de 1152 non portée.** `$$CanContinue` et `$$GetAllTilesInLine` sont lus (cf. §1) et le playbook `UnstoppableMomentumReworkedPlaybook$$EvaluateNonComparable` est cité par `case-477r33` comme un non-owner dont le port ne rend rien. La face COMBAT est portée et confrontée (#498) ; celle-ci est un résidu de SCORING/prévisualisation, entièrement lisible. |
