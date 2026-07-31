# case-366-r1 — `1284 EchoesFromTheWarp_Revive` : la SECONDE instanciation de `GhostEffect`

**Statut : PORTÉ ET VALIDÉ LIVE.** Tranche fille de `#366-r1` (gisement des 96 EffectTypes), table
G3. L'item était classé **NON PERTINENT** par #228 (porteur npc, pool fermé) : ce verdict est
**RÉOUVERT et infirmé** — la voie de confrontation existait, elle demandait un montage que le
harnais ne savait pas encore faire (greffe d'un PASSIF) et un canal que le port n'avait pas encore
branché (les passives RÉELLEMENT montées).

Build RE : `rnca9r7q6c`. Toute VA relue sur ce build ; RVA = VA − 0x180000000, calculée en code.

## 1. Identité de classe — ÉTABLIE, pas supposée

Le tableau G3 annonçait « MÊME classe que `1186 TimeFlux_Revive` ». C'est **vrai**, et voici les
trois lectures indépendantes qui le prouvent — aucune ne repose sur un nom de `.ctor`.

| ce qu'on établit | lecture |
|---|---|
| hiérarchie des ABILITIES | `frida/classes.tsv` : `EchoesFromTheWarpAbility` **et** `TimeFluxReviveAbility` ont pour parent `GhostReviveAbility` (lui-même fils de `BaseTriggeredAbility`) |
| aucune ne surcharge quoi que ce soit | bloc `methodPointers` du PE (technique `case-66` §8.3) : chacune ne déclare **qu'UNE méthode, son `.ctor`** — une seule entrée, encadrée par les blocs des classes voisines (`ECogSupport_InitAbility`/`EcstaticSlaughterAbility` d'un côté, `TimeFluxAbility`/`TimesplinterMantleAbility` de l'autre) |
| l'EFFET est la même classe | `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects` : `0x4a2` et `0x504` mappent sur `...EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_203` et `...b__14_204`, qui allouent depuis **le même slot `Il2CppClass*` (`DAT_1833ea8f0`, dont ce sont les SEULES xrefs)** et appellent le même ctor ; `GhostEffect` n'a par ailleurs **aucune sous-classe** |

Les deux ctors d'ability appellent le même corps de base — que ghidra nomme
`GenericAddEffectToOwnerAbility..ctor` sur ce build et nommait `EnvDefenderHealthBuffAbility..ctor`
sur le précédent : **le nom d'un `.ctor` fondu par ICF ne dit rien**, seul le littéral passé compte
(`0x4a2 = 1186` / `0x504 = 1284`).

### 1.1 Le DISCRIMINANT runtime des deux ids

Les deux lambdas de la fabrique ne diffèrent que par l'immédiat passé à
`IdunBattle.Core.AbilityOrEffect$$op_Implicit` : **`0x485 = 1157 TriggeredAbilityType.TimeFlux`**
pour 1186, **`0x4c3 = 1219 EchoesFromTheWarp`** pour 1284. C'est donc la **fabrique** qui fige le
champ `source` (`Nullable<AbilityOrEffect>` @`GhostEffect+0x14`) que le fork d'`amount` relit —
la bijection `effectType ↔ TriggeredAbilityType poseur` est **structurelle**, pas une coïncidence
de ctors. Corollaire de port : résoudre le fork à l'ENREGISTREMENT (`EFFECT_TRIGGERS[1186]` vs
`[1284]`) est exact, et c'est le mirror du natif — qui résout à la CONSTRUCTION de l'arbre et
n'évalue jamais la branche non prise.

## 2. Le fork d'`amount`, et le mislabel qu'il portait

`IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateTargetTriggerBehaviour` :

```
if (effet.source == 0x485)   // 1157 TimeFlux
     amount = Direct(GetVariableForLevel(config@0x60, 0x1d = 'hp', abilityState));   // 1186
else amount = StatAmount(src, 5 = Health, 3 = StatPart);                             // 1284
```

⚠ **`StatPart 3` est `Initial`, PAS `Maximum` (= 2).** `IdunBattle.Entities.Enum.StatPart` =
`0=Current,1=CurrentPct,2=Maximum,3=Initial,4=Missing,5=Modification,6=ResetModification,7=Override,
8=RemoveOverride,9=MultiplierModification`, et
`IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart` le confirme au corps :
`case 3: return *(this+0x10)` (le champ base, posé une fois par `$$Initialize`) contre
`case 2: get_CurrentMaximumValue()` (= base + modification clampée, ou l'override). La fiche
`case-66` §8.4 écrivait « max = 3 » — et sa note de port disait même de router `Maximum` sur
`hp_max`. C'était un **mislabel**, corrigé ici.

La signature est lue, pas devinée :
`IdunBattleLogic.Entities.DSLFormulas$$StatAmount(this, unit, statType, statPart, modificationEntity,
selectionType)`.

**Le montant final vaut donc la PV INITIALE**, et le clamp le confirme :
`IdunBattle.Entities.Behaviours.ReviveBehaviour$$GetMaxReviveAmount` →
`IdunBattle.Core.Services.BattleQuery$$GetMaximumReviveHealth` =
`Min(GetStat(unit, Health, Initial), <cap config slot 0x12>(CurrentMaximum, …))`. On a donc
`Min(Health_Initial, Health_Initial, cap)`.

**Confirmation croisée i2** (authoritatif) : « When this unit moves, it leaves a time ghost behind on
the hex it moved from. The time ghost vanishes if the hex becomes occupied by another unit or if the
terrain becomes impassable (as with **Broken Ice**). **The first time this unit dies each battle**,
if its time ghost is on the battlefield then it revives with **Full Health** at its location. This
works even if this unit is **Overkilled**. »

Chaque membre de phrase a son nœud : `On(0x1f = PreUnitMove)` · les retraits n°2/n°3 · le gate
`TileHasTriggeredAbility(tile, 0x1d = 29 BrokenIce)` · `NOT HasBeenRevivedByAbility` (registre de
BATAILLE, jamais remis à zéro) · `StatAmount(Health, Initial)` · `tiles = Owner@0x148` ·
`OnPreDeath(ignoreOverkill = 1)`.

**Deuxième confirmation croisée** : le gameconfig d'`EchoesFromTheWarp` porte `variables: {}` et
`constants: {}` — cette ability ne peut PAS lire de variable de config, ce qui exclut la branche
`Direct(ConfigVar('hp'))` indépendamment du décompilé.

## 3. Confrontabilité — pourquoi #228 concluait faux

#228 avait raison sur les faits et tort sur la conclusion. Les faits, **re-dérivés** ici
(`probe_366r1_echoes_revive.py` volet A) :

- porteur unique `thousNpc4Terminator` (« Scarab Occult Terminator », ThousandSons), bucket **npc** ;
- **aucun summoner** (0 ability du gameconfig ne cite son id) ;
- `buildNormalizedBC` le refuse à tous les ranks, et c'est **structurel** :
  `IdunMetaLogic.Formulas.StatsFormula$$StatsUsingProgressionIndexFor` fait un `Dictionary.get_Item`
  **par unitId** qui ne couvre que le bucket `lineup` → `KeyNotFoundException`. Aucun enrichissement
  du seed BC ne peut lever ce refus (le hook ne passe à la formule que
  `(unitId, isMow, rank, progressionIndex, items)`).

Ce que #228 n'a pas fait : **la GREFFE**. Le natif charge l'ability depuis
`BattleConfiguration.Units[].PassiveAbilities`, pas depuis un kit indexé par unité — on peut donc
la poser sur une unité DU POOL. La condition de légitimité (`case-92` §5bis) est ici remplie et même
mieux que remplie : l'arbre ne lit **ni trait ni arme** du caster, et la seule stat lue
(`Health` part `Initial`) est celle du **greffon** — ce qui en fait un **discriminant** (deux
greffons de PV différentes doivent rendre deux montants différents), jamais un confond.

### 3.1 Le montage : DEUX écritures, dont une échoue en silence

`catalog_inject.graft_passive_ability` / `write_grafted_seed_bc` (pendant PASSIF de la recette
`case-92` §5bis, qui ne couvrait que `ActiveAbilities`) :

1. `BC.Units[<greffon>].PassiveAbilities = [<TriggeredAbilityType>]` — ce que
   `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` monte réellement ;
2. `BC.Abilities.PassiveAbilities[<nom>]` = la config d'ability. Sans elle,
   `AbilityConfiguration$$GetVariableForLevel`/`$$GetStringConstant` **lèvent**, et pour un PASSIF
   (dont l'arbre DSL est bâti à la création de l'unité) la faute frappe **le DÉPLOIEMENT** —
   « system error » sur `initAndStart`. `refresh_ability_configs` ne comble PAS ce trou : sa 2ᵉ
   boucle dérive les noms d'abilities de l'`Id` de l'unité **au gameconfig**, donc elle ignore une
   liste greffée.

Pas de verrou de NIVEAU ici, contrairement à la relique : `buildNormalizedBC` pose
`PassiveAbilityLevel = targetAbilityLevel` **inconditionnellement** et ne touche **jamais** la liste
`PassiveAbilities` (`frida/hooks/features/normalize-bc/json-build.ts`) — greffer avant ou après la
normalisation donne le même résultat.

**Greffon retenu : `thousTerminator` (« Toth »)** — même faction, mêmes traits `WeaverOfFate` +
`TerminatorArmour` que le vrai porteur. La greffe **remplace** sa liste de passives, donc `TimeFlux`
(ghost 1186 **et** regen) disparaît : aucun confond possible entre les deux instanciations.

## 4. Le trou qui rendait tout ça invalidable — les passives montées

`triggers/dispatch/core.py::collect_triggered_abilities` dérivait les passiveAbilities du
**gameconfig par `visualId`**. Le natif, lui, monte `BC.Units[].PassiveAbilities` :

```
IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities
  foreach (id in config+0xa8 = UnitConfiguration.PassiveAbilities)
      TriggeredAbilityComponent$$TryAdd(id, passiveAbilityState, 2)     <- hiérarchie 2
  if (config+0xb0 /* TertiaryAbility */ .HasValue)
      TriggeredAbilityComponent$$TryAdd(id, tertiaryAbilityState, 3)    <- la relique (#357)
  foreach (id in config+0xa0 = ActiveAbilities)  UnitFactory$$AddActiveAbility(...)
```

La **hiérarchie 2** est donc l'image EXACTE de `BC.Units[].PassiveAbilities`. C'est la même faute et
le même correctif que **#264 sur l'axe TRAITS** : une reconstruction à partir d'une AUTRE source, qui
laisse INERTE — sans erreur ni trace — tout passif que le BC porte et que le kit ignore.

**Aucun reinject** : le capteur `unitAbilityStates` publie déjà `raw[10]` (#237/#357). Le port lit
désormais ce canal (`UnitContext.passive_abilities`, `snapshot._load_passive_abilities`), en
tri-état — `None` = canal muet → fallback gameconfig, comportement strictement d'avant ; une liste
(fût-elle vide) = mesure, et elle fait autorité.

**Validation croisée du discriminant de hiérarchie**, mesurée sans le chercher : sur `astraBullgryn`,
la hiérarchie **2** rend `AvalancheOfMuscle` (= son `passiveAbilities`) et la hiérarchie **0** rend
`BigTarget` (= son **trait**). Le décompilé et la mesure disent la même chose.

## 5. Port (fichiers)

| Fichier | Contenu |
|---|---|
| `triggers/loki/ghost_revive.py` | `GhostReviveAbility` devient la BASE paramétrée par `GHOST_EFFECT_TYPE` (mirror du ctor natif) ; sous-classes `TimeFluxReviveAbility` / `EchoesFromTheWarpAbility` ; `GhostEffectRevive` + hook `amount_node()` et ses deux instanciations ; les 5 retraits × 2 effectTypes |
| `triggers/revive_effect.py` | la feuille `Revive` accepte un **nœud d'amount** explicite (le 4ᵉ argument natif est TOUJOURS une formule ; le port collapsait le cas archi-majoritaire `Direct(ConfigVar('hp'))`) |
| `triggers/dispatch/registry.py` | `ABILITY_TRIGGERS["EchoesFromTheWarp"]` + `EFFECT_TRIGGERS[1284]` (6 entrées, comme 1186) |
| `engine/entities/unit_context.py` + `runner/snapshot.py` | `passive_abilities` (canal mesuré, hiérarchie 2) |
| `triggers/dispatch/core.py` | la mesure fait autorité sur le gameconfig quand elle existe |
| `catalog_inject.py` | `graft_passive_ability` / `parse_graft_spec` / `write_grafted_seed_bc` |

Rien à ajouter côté DÉCISION : `EchoesFromTheWarp_FriendliesAvoidGhostUtility` (UtilityType **59**)
était **déjà portée** (`engine/utilities/tile.py`) et lisait déjà l'effet 1284 — elle était
structurellement morte tant que rien ne posait cet effet. Elle ne l'est plus.

## 6. Validation

### 6.1 Live vs port — `probe_366r1_echoes_revive.py --live`

**4 régimes** = 2 boards × 2 valeurs de `Health` (donc de `StatPart.Initial`). Le greffon démarre son
tour en A, bouge en B (B ≠ A), y encaisse un coup létal.

| board | `Health` (Initial) | live : pos après mort / hp | port : pos après mort / hp |
|---|---|---|---|
| `MC1_67` | 9 000 | A `(1,2)` — **hp 9 000** | A `(1,0)` — **hp 9 000** |
| `MC1_67` | 15 000 | A `(1,2)` — **hp 15 000** | A `(1,0)` — **hp 15 000** |
| `C4_09` | 9 000 | A `(3,3)` — **hp 9 000** | A `(2,1)` — **hp 9 000** |
| `C4_09` | 15 000 | A `(3,3)` — **hp 15 000** | A `(2,1)` — **hp 15 000** |

Le montant **suit la PV initiale** dans les deux moteurs, la position de revive est la tuile du
ghost, le ghost est consommé, et `kill_cancelled_by_revive` est signalé côté port. Les tuiles A
diffèrent entre live et port parce que le bras live approche l'ennemi avant de mesurer (le port part
de l'état capturé) : l'invariant testé est le même des deux côtés — « revive sur la tuile de DÉBUT DE
TOUR », pas une coordonnée fixe.

**Ce que ce montage exclut, nommément** : une constante (les deux régimes rendraient la même
valeur), la branche `Direct(ConfigVar('hp'))` de TimeFlux (qui rendrait 3 290 — et
`EchoesFromTheWarp` n'a de toute façon aucune variable), et `StatPart.Current` (qui rendrait 0,
l'unité venant de mourir).

### 6.2 Non-régression du canal — volet B

Roster **aléatoire 5v5**, runner NON greffé : **10 unités, 0 écart** entre la hiérarchie 2 mesurée et
`gameconfig.passiveAbilities`. La substitution est donc un **no-op strict** sur des kits quelconques.

> ⚠ Ce volet a d'abord rendu **« 0 unité(s), 0 écart(s) »** — un **faux vert** : `observeBattle.units[]`
> porte `entityId`/`squadId`, pas `id`, donc le mapping vers `visualId` rendait `{None: …}`. Corrigé,
> et le probe **refuse désormais de rendre vert un balayage à zéro**.

### 6.3 Tests

- **neufs** : `tests/engine/runner/test_echoes_from_the_warp_revive_live.py` (**6**) — garde du canal
  (le passif greffé est VU du port, et `TimeFlux` ne l'est plus), face positive tuile-de-mort ≠
  tuile-de-revive, **le discriminant à deux régimes de `Health`**, « pas de move → pas de ghost »,
  once-per-battle, dissipation par arrivée d'une autre unité ;
- **zéro-reg ciblée** : `test_ghost_revive_live` (5), famille revive complète — narthecium / tainted /
  rites_of_morkai / retrofit / revive_cancels_death / fuelled_by_fury (**51**), canal et relique —
  `load_state_turn_state` / `363_ability_states_default` / `357_relic_rail` / `237_relic_equip`
  live+offline (**44**). **Total 106 PASS.**
- garde-fous : `probe_181` (98/98, 0 manquante), `probe_120 --step 0`, `probe_273 --only-scan`,
  `probe_365` — tous verts.

## 7. Résidus nommés

- **`StatPart.Initial` ≡ `Maximum` côté port.** `HealthComponent` n'a que `hp`/`hp_max`, donc
  `FillUpStatComponent.get_stat_part` rend le même `maximum` pour les parts 2 et 3. Les deux ne
  divergent côté natif que sous une modification de MAX-PV (`FillUpStatComponent$$ModifyMax` /
  `$$MaxReduce`, ou une stat-modification de `Health`) : `Maximum = base + modification clampée`,
  `Initial = base`. **Aucun effet modifiant le max-PV n'est porté à ce jour** — le jour où l'un le
  sera, ce revive est l'un des consommateurs à re-vérifier.
- **`TileHasTriggeredAbility(tile, 29 = BrokenIce)`** — inchangé depuis #213 : la table
  `TriggeredAbilityType → tileDefId` vit dans les assets Unity de tuile, hors gameconfig ; le gate est
  structurellement présent mais toujours faux. Il ne peut refuser un ghost à tort que sur un board à
  glace brisée.
- **Retrait n°5 (`On(UnitRemoved)`) inerte en bataille réelle** — inchangé depuis #227 : l'émetteur
  est porté, mais aucune des cinq abilities natives `RemoveUnit` ne retire le poseur d'un ghost.
- **Ce que la greffe ne couvre pas**, et qui reste donc NON CONFRONTÉ : les stats, traits et armes
  propres à `thousNpc4Terminator`. Ici c'est sans conséquence (l'arbre n'en lit aucun, et la seule
  stat lue est prise sur le greffon), mais ça reste à écrire.
- **Docstrings de `EchoesFromTheWarp_FriendliesAvoidGhostUtility`** : une mention résiduelle
  « UtilityType.=58 » subsiste dans `engine/utilities/tile.py` alors que le code et l'enum du build
  disent **59** (`AttractMechanicalsUtility` est le 58). Cosmétique, non touché ici.
