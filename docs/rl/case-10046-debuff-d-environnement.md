# case-10046 (volet DEBUFF) — débuffer l'adversaire par une ability d'environnement

Mesuré le 2026-08-23, build `t6dpr4k06g`, sur runner isolé. **Aucun changement de hook, aucun
reinject** : tout passe par un seed BC custom.

## 1. La voie BC installe une env-ability sur un RUNNER

`env_ability_patch.py` n'agit que sur la **source vivante** (`LoadBattle.onLeave`, campagne /
sandbox). Pour un banc, il suffit d'écrire le réceptacle dans le seed BC :

```json
BC.EnvironmentAbilities.EnvironmentAbilities = [{"ConfigId": "<Nom>", "Level": 1}]
```

Témoin non ambigu : `EnvStartProtection` posé par cette voie rend des boucliers à
`amount: 500` — exactement le `shieldHp: 500` de sa config au catalogue.

⚠ Une config **absente** du catalogue peut y être **ajoutée** dans le même seed BC
(`BC.Abilities.EnvironmentAbilities["<Nom>"] = {Variables, Constants, ...}`) : clé chaîne, donc
aucun des dangers du dictionnaire à clé de type valeur qui a tué le process le 2026-08-21. Testé,
accepté, aucun « system error ».

## 2. ⚠ DEUX LISTES DANS LE RÉCEPTACLE, ET ELLES NE CIBLENT PAS PAREIL

Le dump de champs (`sources_win`, `Il2CppDumper`) donne la forme exacte :

```csharp
class EnvironmentAbilityConfiguration {
    TriggeredAbilityConfigId ConfigId;    // 0x10
    Level                    Level;       // 0x20
    Nullable<PlayerId>       PlayerId;    // 0x24   <- `ajouterAbility` le laisse NUL
}
class EnhancementsEnvironmentAbilityConfiguration : EnvironmentAbilityConfiguration {
    List<EnhancementTargetConfiguration> Targets;  // { UnitConfigId Target; int Stack; }
    int                                  Stack;
}
```

| liste | ciblage |
|---|---|
| `EnvironmentAbilities` | écrit dans le `CreateTrigger` de l'ability — **pas un argument** |
| `EnhancementsEnvironmentAbilities` | **par unité NOMMÉE**, via `Targets[].Target` |

La seconde est le vecteur de debuff : `EnhancementAddTraitAbility$$CreateTrigger` =
`On(EventTriggerType.PostAbilityInit) & DSLTriggers$$IsEnhancementTarget(target, enhancement)`,
et le behaviour est `DSLBehaviors$$AddTrait(target, AbilityConstantType.trait)` +
`AddEffect(EffectType.EnhancementAddTrait)`.

## 3. La recette, vérifiée

`BC.Abilities.EnvironmentAbilities` porte **106** variantes `EnhancementAddTrait:<Trait>`, toutes
déjà configurées (`Constants: {"trait": "<Trait>"}`). Rien à synthétiser.

```json
BC.EnvironmentAbilities.EnhancementsEnvironmentAbilities = [{
  "ConfigId": "EnhancementAddTrait:Stationary",
  "Level": 1,
  "PlayerId": 12,
  "Targets": [{"Target": {"PureId": "necroWarden", "Rarity": null, "Level": null,
                          "IsBorrowed": false, "IsPvpOpponent": false}, "Stack": 1}],
  "Stack": 1
}]
```

Mesure : `Harmless` (trait 21) posé sur les **deux** unités adverses nommées, **absent** de mes
deux unités. Et `Stationary` : les deux ennemis restent en rangée 8 là où ils sont posés, alors
qu'au run précédent — **même seed, même board, même placement** — ils atteignaient la rangée 5 en
un tour.

## 3bis. BAISSER LES DÉGÂTS : un POURCENTAGE NÉGATIF, et il n'y a aucun garde

Le menu des traits est fermé ; celui des pourcentages ne l'est pas.
`EnhancementDamageBoostAbility$$CreateBehaviour` pose `AddEffect(EffectType 0x5c2)` avec la seule
constante `extraDmgPct`, et **rien ne l'oblige à être positive**. Posée par la même voie
enhancement que ci-dessus (`ConfigId: "EnhancementDamageBoost"`), sur `necroWarden` seul, board
`C1_74`, mêmes placements, même seed :

| `extraDmgPct` | plan d'attaque de l'ennemi | dégâts RÉELLEMENT subis (2 coups) |
|---|---|---|
| `+20` | `[2080-3120]` | **4369** |
| `-50` | `[868-1300]` | — |
| `-100` | `[0-0]` | **0** |
| `-150` | `[0-0]` | — |

868/2080 = **0,4167** = (1 − 0,50)/(1 + 0,20), à la quatrième décimale : c'est un multiplicateur
pur `(1 + pct/100)`, sans clamp jusqu'à `-100`. En dessous, le dégât est **borné à zéro** — pas de
soin par dégât négatif.

⚠ Mesurer sur le COUP, pas sur le plan : `[0-0]` est une **prédiction**. Les `0 dmg` contre
`4369 dmg` du témoin viennent d'un `aiturn` réel, à seed et placement identiques.

Même forme disponible sur les autres constantes de la famille : `EnvStrategicBuff`
(`extraDmgPct`, `extraCritChance`), `EnvStatBoost` (`dmgPct`, `healthPct`, `armorPct`, gardé par
un `trait`), `EnhancementCritBoost`, `EnhancementPierceBoost`, `EnhancementHitBoost`,
`EnhancementLifeSteal` — **non mesurées**.

## 3ter. `EnhancementRegeneration` — soigne TES héros, et le `Stack` MULTIPLIE

`EnhancementRegenerationAbility$$CreateBehaviour`, lu au décompilé :

```
cible   = DSLSelectors$$UnitsWithTrait(DSLSelectors$$UnitsFromTeam(sel, 1), UnitTrait.Hero)
montant = DSLFormulas$$Multiply(
              DSLFormulas$$PercentageOf(StatAmount(unit, StatType.health), AbilityConstantType.hpPct),
              DSLFormulas$$EnhancementStack(sel))
DSLBehaviors$$Foreach(cible,
    DSLBehaviors$$If(DSLSelectors$$Repairable(unit), DSLBehaviors$$Repair(...), DSLBehaviors$$Heal(...)))
```

Team **1** et trait `Hero` sont **écrits dans l'arbre** — c'est un buff pour TOI, pas un debuff.
`Repairable` route les MoW vers `Repair` plutôt que `Heal`.

Mesure (`adeptCanoness`, PV max 8533, `--unit-stat RemainingHealth=2000`, `hpPct: 30`) :

| `Stack` de l'entrée | PV au montage | soin |
|---|---|---|
| 1 | **4560** | +2560 = 30 % × 8533 |
| 2 | **7120** | +5120 = 2 × 2560 |

**D'où ça vient — l'INCURSION.** Un seul live event du gameconfig porte des `enhancements` :
`liveEvents/idunLiveEventConfigs[1545]`, `eventType: mowEvent`. Son graphe de nœuds est fait de
**2178** `incursionBattle` et **1870** `incursionEnhancement` — on choisit un enhancement entre
deux batailles. Les 19 entrées y déclarent exactement les deux boutons trouvés ci-dessus :

```json
"Regeneration_01": {"type": "Regeneration", "abilityId": "EnhancementRegeneration", "stacks": true}
"AddTrait_01":     {"type": "AddTrait", "unitAmount": 1, "abilityId": "EnhancementAddTrait:MkXGravis", "stacks": false}
"DamageBoost_01":  {"type": "DamageBoost", "unitAmount": 1, "abilityId": "EnhancementDamageBoost", "stacks": true}
```

`stacks` ↔ le champ `Stack` de l'entrée (le multiplicateur mesuré) ; `unitAmount` ↔ la longueur de
la liste `Targets`.

⚠ **L'incursion n'expose qu'une FRACTION du catalogue, et l'écart est le gisement.** `units/abilities`
du gameconfig porte **20** entrées `Enhancement*` ; l'event en cite **17** (toutes présentes, et
toutes au catalogue de la BC). Mais côté `AddTrait`, le gameconfig n'en connaît que **quatre** —
`MkXGravis`, `RapidAssault`, `Resilient`, `Infiltrate` — là où le catalogue de la BC porte **106**
variantes `EnhancementAddTrait:<Trait>`. Les 102 autres n'existent **que** dans la BC : elles sont
hors de portée de l'UI d'incursion, et c'est exactement ce qui les rend atteignables par la voie
seed-BC ci-dessus.

⚠ **Elle tire AU MONTAGE, pas par tour.** Mesuré : un héros qui encaisse sur deux tours
(8533 → 6418 → 1385) n'est **jamais** soigné — `6418 − 5033 = 1385` exactement. C'est un héros
**déjà blessé à la construction** qui l'est. Contrairement à `EnhancementDamageBoost`, qui pose un
EFFET persistant, celle-ci exécute une ACTION : sans re-déclenchement, elle ne joue qu'une fois.
Les deux classes n'overrident que `CreateBehaviour` — leur trigger est hérité et n'a **pas** été
lu ici.

## 4. ⚠ LE NOM D'UN TRAIT NE DIT PAS SA SÉMANTIQUE — deux essais perdus dessus

`Harmless` posé : l'adversaire attaque quand même (2115 dmg encaissés). `Immovable` posé :
l'adversaire avance de trois rangées. Les deux traits étaient bel et bien **sur les unités** —
le mécanisme marchait, c'est mon hypothèse sur leur sens qui était fausse (`Immovable` n'est pas
« ne se déplace pas », c'est vraisemblablement « ne se fait pas déplacer »).

Le trait qui immobilise est `Stationary`. **Le dériver du moteur, jamais du nom** :

```powershell
git grep -oh "UnitTrait\.[A-Za-z_]*" -- scripts/python/engine | sort | uniq -c | sort -rn
```

Les traits réellement consultés, par nombre de sites : `Steppable` 113 · `Hero` 77 · `Summon` 67 ·
`Chaos`/`Psyker` 46 · `Object` 43 · `Immune` 34 · `Mechanical` 23 · `BigTarget` 21 · `Decoy` 17 ·
`Vehicle`/`Stationary` 16 … Un trait absent de cette liste peut se poser sans rien changer.

## 5. ⚠ `EnvAttemptDebuff` (1288) EST UN LEURRE — il cible juste, et ne fait RIEN

C'est la seule ability **nommée** pour débuffer l'adversaire, et son ciblage est le plus net du
lot : `On(EventTriggerType.InitialMatchUnitAdded) & DSLTriggers$$IsInTeam(sel, TeamId 2)` —
l'équipe adverse **en dur**, `IsInTeam` prenant un `IdunBattle.Core.TeamId` absolu. Deux
constantes seulement, lisibles dans
`idun.shared.commands.ShowGuildWarsBattlePreviewPopupCommand$$AddAttemptDebuffEnvironmentAbility` :
`AbilityConstantType.amount` (110) et `AbilityConstantType.hpPct` (18).

Posé, il s'installe proprement et l'effet `AttemptsDebuff` apparaît sur **les deux adversaires et
aucun allié**. Mais il ne fait rien : `IdunBattle.Entities.Effects.Loki.EnvAttemptsDebuffEffect$$.ctor`
n'appelle que `BaseEffect$$.ctor` sans modification, `$$GetLocalizationDataInternal` rend un
dictionnaire **vide**, et le diff de stats contre un témoin sans debuff donne **zéro écart**
(seuls les `entityId` glissent). Balayer `hpPct` de 30 à 90 ne change rien non plus.

Son appelant est une popup de **prévisualisation** de guerre de guilde : c'est du mobilier
d'affichage, pas une mécanique de combat.

⚠ Corollaire de méthode : « l'effet est ACTIF sur la bonne cible » ne dit rien de « l'effet FAIT
quelque chose ». Il a fallu le diff de stats **et** le décompilé du ctor pour le trancher.

## 5bis. VISER L'ADVERSAIRE : il faut la chaîne EXACTE, et il n'y a PAS de wildcard

Le suffixe d'un `unitId` **doit être scindé** : `UnitConfigId$$op_Implicit(string)` délègue à
`CreateFromString`, qui coupe sur le `:` — `tyranNpc3Termagant:6` devient
`{PureId: "tyranNpc3Termagant", Level: 6}`. Écrire `PureId: "tyranNpc3Termagant:6"` tel quel
n'apparie **rien**, et c'est **silencieux** : l'installation reste `ok`, `EnhancementAbilities`
compte 1, l'effet ne se pose pas. Toute unité de **vague** est dans ce cas — donc précisément
l'adversaire. Corrigé côté hook (mirror 1:1 dans `environment-abilities.ts`) ; les quatre branches
sont `:<entier>` → Level, `:<Rarity>` → Rarity, `:borrowed`, `:pvp`, et suffixe inconnu →
`PureId` = la partie **avant** le `:`.

**Un `*` ne peut pas marcher**, sur les deux consommateurs de `Targets` :

| consommateur | appariement |
|---|---|
| `EnhancementTargetSelector$$Select` | balayage + `UnitConfigId$$op_Equality` → `String.op_Equality` |
| `EnhancementStackForTargetFormula$$Calculate` | `Dictionary<UnitConfigId,int>.get_Item` — **hachage** |

Le second est structurel : un dictionnaire ne fait pas de motif. Et la donnée corrobore — **0**
unitId et **0** constante contenant `*` dans le seed BC.

⇒ La réponse est l'**énumération**, et elle est outillée :
`python scripts/python/bc_apparitions.py --bc <BC> --camp 12 --cibles`.

⚠ Et l'énumération à la main RATE : sur la BC Waves du banc, viser les seuls termagants laissait
passer `tyranNpc4Warrior:6` (vagues 6, 8) et `tyranNpc6SporeMine:6` (vague 5).

⚠ **`PlayerId` n'est PAS le levier de ciblage** — lu au décompilé sur
`AddEnvironmentAbilityOperation$$Execute` : il fixe le **propriétaire** de l'entité
d'environnement (défaut **câblé** au joueur 2), pas qui est affecté. Atteste par la mesure :
l'effet s'est posé sur une unité du joueur 11 avec un propriétaire joueur 2.

## 5ter. ⚠ AUCUNE env-ability À CONSTANTE DE DÉGÂTS N'EST TEAM-SCOPÉE — les 4 lues, les 4 écartées

Le catalogue (166) n'en porte que quatre qui touchent aux dégâts hors `EnhancementDamageBoost`.
Ciblages **lus au décompilé**, pas déduits des noms :

| ability | ciblage | pourquoi ça ne sert pas |
|---|---|---|
| `EnvAttemptDebuff` | `IsInTeam(.., TeamId 2)` | cible juste, **ne fait rien** (§5) |
| `EnvStrategicBuff` | `Filter(unités, IsHumanPlayer(OriginalOwner))` | vise le **joueur humain**, ampleur indexée sur `NumControlledTerritory` |
| `EnvThinVeil` | `On(UnitAdded \| InitialMatchUnitAdded) AND HasTrait(Psyker) AND HasTrait(Hero)` | **aucun filtre d'équipe** — frappe les deux camps |
| `EnvDespoiledGroundTileDamage` | `UnitsWithoutTraits(all, [Steppable, Immune]) AND Units(EntitiesWithAnyEffect(all, DespoiledGround))` | **positionnel**, les deux camps |

⇒ Le « tout l'adversaire sans le nommer » **n'existe pas** dans ce catalogue. L'énumération
(§5bis) reste la voie.

**Deux leviers en sont quand même sortis**, différents mais réels :

- `EnvDespoiledGroundTileDamage` inflige
  `AttackWithAbilityDamage(RandomAmount(PVmax × minHpPct%, PVmax × maxHpPct%))` à chaque
  `TurnStart_EnvironmentEffects`, soit **6–9 % des PV max par tour** à qui piétine la zone.
  ⚠ Son `extraDmgPct: 15` **n'est pas ce dégât** : c'est un **buff** posé par
  `If(IsTurnOf(cible) AND HasTrait(Chaos) AND NOT HasTrait(Immune), AddEffect(DespoiledGround_ExtraDamagePct))`.
- `EnvThinVeil` cible par **trait** — et un trait se **pose** (`EnhancementAddTrait:<Trait>`).

⚠ **PIÈGE DE LECTURE, ÉVITÉ DE JUSTESSE.** Le décompilé de `CreateBehaviour` montre deux
constantes lues avec les littéraux `9` et `10`. Résolus contre `AbilityConstantType` ils donnent
`unitToSpawn_red` / `unitToSpawn_green` — absurde pour un `PercentageOf(Health, X)`. Vérification :
`minHpPct` = **132**, `maxHpPct` = **133**. Les `9`/`10` ne sont donc **pas** des ordinaux de cet
enum (argument d'un accesseur générique, ou artefact de convention d'appel). Aggravant :
`extraDmgPct` a l'ordinal **15** et sa valeur dans la BC vaut aussi **15** — une coïncidence qui
rend une lecture fausse plausible. **Le nom d'une constante se recoupe contre les `Constants` de
la BC, jamais contre le seul littéral du décompilé.**

## 6. Résidus

- `PlayerId` de `EnvironmentAbilityConfiguration` : **tranché** (cf. §5bis) — il fixe le
  propriétaire de l'entité, pas la cible. Ce qui reste ouvert : ce que ce propriétaire CHANGE pour
  une ability dont l'arbre cible relativement au caster.
- Le `:6` d'un identifiant est un **niveau** (`Int32.TryParse` → `UnitConfigId..ctor(pureId,
  level)`), pas un ordre de spawn — les 20 termagants d'une vague le portent tous. Mais la
  `UnitConfiguration` résolue de `tyranNpc3Termagant:6` porte `Level: 8`. **Ce qui fait 6 → 8
  n'est pas établi.**
- `bc_apparitions.py` sort les summons en **CANDIDATS** : la BC ne distingue pas un spawn d'une
  liste blanche (mesuré — `HailOfLivingAmmunition.unitIds` est un filtre), seul l'arbre DSL
  (`SpawnUnitBehaviour`) tranche. Le recoupement au décompilé reste à faire.
- ~~La voie LIVE reste sans levier~~ — **LIVRÉE le 2026-08-23** (`environmentAbilityConfigs` +
  `environmentEnhancements`), validée sur BC vivante : `catalogue 166 -> 167` et
  `installées={"Abilities":1,"EnhancementAbilities":1}`. Deux crans appris en route, et le
  premier corrige une erreur de ce document :
  * ⚠ **le catalogue n'est PAS à clé chaîne**, contrairement à ce que la ligne d'origine
    affirmait. Sa clé est un `TriggeredAbilityConfigId` — un TYPE VALEUR. Le JSON le fait croire
    parce qu'un `TriggeredAbilityConfigId` se *sérialise* en nom sans être *stocké* comme tel.
    Donc on n'y écrit pas soi-même : on passe par
    `IdunBattle.Configuration.AbilitiesConfiguration$$AddEnvironmentAbility(TriggeredAbilityType, …)`,
    l'enum plat, en sélectionnant la surcharge par le TYPE de son 1ᵉʳ paramètre (il y en a deux à
    2 paramètres). **Corollaire : une VARIANTE est inexprimable par le patch** (ordinal +
    `VariantId`) ; les 106 `EnhancementAddTrait:<Trait>` restent réservées à la voie seed BC, où
    Newtonsoft construit les clés — et le CLI refuse explicitement.
  * ⚠ **`GetEnvironmentAbility` ne sait pas dire « absent »** : il rendait non-nul *avant*
    l'écriture alors que le compte passait de 166 à 167 — il fabrique un défaut au lieu de rendre
    `null`. Une relecture bâtie dessus serait sortie verte quoi qu'il arrive. Le verdict est le
    **compte du dictionnaire**, pris avant/après chaque entrée.
- **Retiré le même jour** : `playerTeamIds` et `spawnGroupPlayerIndexes` (327 lignes), qui
  réécrivaient les `TeamId` et les index de groupes de spawn pour contourner un symptôme qui
  n'était pas le leur (cf. `case-10046-pose-des-unites-predefinies.md` §5ter : la cause était le
  `TWPI 0` du harnais). `turnOrder` et `environmentEnhancements` couvrent leurs usages.
- ⚠ Rectification d'une ligne du commit `e44ccb6b` : « `EnvReinforcementShield` 0 occurrence dans
  le gameconfig » accusait la **mauvaise table**. Les configs d'env-ability vivent dans
  `BC.Abilities.EnvironmentAbilities`, pas dans le gameconfig — `EnvThinVeil` y est à 0 occurrence
  alors qu'il **est** au catalogue de la BC. La conclusion (absent) restait juste, la preuve non.

## Cibler « moi » et « l'adversaire » sans les nommer (2026-08-23)

**Le patch se résout à l'APPLICATION, pas à l'armement** (`ciblesAuto: "adversaire" | "moi"`).
Un armement unique mord alors sur n'importe quelle source. Validé en PvP live.

**L'ADVERSAIRE se dérive de la BC.** `BC.Player.Players` : `PlayerType 0` = le joueur humain, son
`TeamId` définit « moi ». Les groupes `PredefinedUnits`/`PredefinedMachines` portent leur playerId,
`UnitSpawningOverTime.Tiers` est keyé par playerId — les vagues se rattachent donc à un camp.

⚠ **NE PAS écrire « `PredefinedUnits` = l'adversaire ».** Règle tirée d'UNE BC d'Arène, **INVERSÉE**
sur une BC à vagues où le champ porte MES unités : le `-100 %` s'est armé sur ma propre équipe
(9 cibles = mes 5 + les 4 de vague) et l'Immune sur personne. Une règle tirée d'un mode n'est pas
une règle.

**MOI ne se dérive PAS de la BC — on le DEMANDE À LA SOURCE.** Mesuré sur une BC PvP **réelle**
(forgée par `pvp-source-forge`, aucune tentative consommée) : le camp du joueur y est **VIDE**, les
unités n'entrent qu'au **déploiement** par `AddUnitMessage`, donc **après** `LoadBattle.onLeave`.
Deux replis tentés, tous deux faux : épingler la lineup (5 ids d'onslaught contre une lineup
d'arène → **0 appariement, aucun trait posé, rien ne le signalait**) ; dériver de la BC (rend 0, ce
qui se lit « pas de camp » au lieu de « pas dans cet objet »).

Foyer unique : **`frida/hooks/game/source-lineup.ts`** — `GetBattleLineup(places)` +
`GetBattleMachineOfWarLineup()`, `places` **lu** sur la source (`MaxUnitsPossibleToStartBattle`),
jamais un `5` écrit. Le hook `LoadBattle` capture `args[0]` à l'`onEnter` : c'est le `this` de la
source, on est déjà sur le thread principal, et l'objet est complet. Mesure PvP : 5 unités +
`blackForgefiend`, `places=5`.

⚠ **`GetBattleLineup` prend une TAILLE, pas un index** — son paramètre s'appelle `lineupIndex` dans
le dump et dit le contraire. `0 -> []`, `1 -> 1`, `18 -> 18`.

⚠ **`UnitConfigId.PureId` RETIRE le suffixe `:pvp`** (`CreateFromString` scinde). Un homonyme d'en
face est donc apparié : sur 6 unités à moi, **2 retirées** (`worldKharn`, `blackForgefiend`, joués
des deux côtés). Ce n'est pas contournable — le natif lui-même ne les distingue pas ; leur donner
l'Immune le donnerait aussi aux copies adverses.

⛔ **`TestSceneBattleModeSource` est un FAUX ANCRAGE, désormais refusé.** Son `LoadBattle` est un
corps **trivial dédupliqué** par IL2CPP : il tire **hors de toute bataille** et rend n'importe quel
type (`List`1`, `RectTransform`, `UnitEntity`, `DefaultJsonNameTable` sur quatre tirs). La garde de
type refusait d'écrire — mais chaque tir **ÉCRASAIT `lastApply`**, seul témoin de ce qu'une vraie
source avait installé. Effet mesuré : une BC PvP appliquée à 18:32 était recouverte à 18:33, et on
lisait « les camps ne sont pas dérivables » en croyant juger le PvP alors qu'on jugeait un
`RectTransform`. **Un anti-écrasement vaut mieux qu'un verdict plausible.**

## Un enhancement N'ATTEINT JAMAIS une Machine of War — par construction (2026-08-24)

**Mesuré.** A/B à montage identique (sandbox PvP, proposition n=1, board `C1_38`, les DEUX camps
avec leur MoW en jeu) : témoin **45** effets, avec trois enhancements **60** — écart **+15**, soit
5 buff + 5 Immune + 5 debuff. **15 et non 18** : les deux machines ne reçoivent rien, alors que
`blackForgefiend` **est** dans les cibles écrites (les 6 « de la SOURCE » = 5 unités + la MoW) et
que `astraOrdnanceBattery` est dans le camp visé. Le ciblage les NOMME, le sélecteur ne les retient
pas.

**Cause, et elle est structurelle : les familles de sélecteurs sont DISJOINTES.** Les machines ont
la leur — `IdunBattle.Entities.Selectors.AllAliveMachinesSelector`,
`IdunBattle.Entities.Selectors.MachineFromPlayerSelector`, exposées par
`IdunBattleLogic.Entities.DSLSelectors$$AllAliveMachines` et
`IdunBattleLogic.Entities.DSLSelectors$$EnemyMachine`.

⚠ **La preuve est l'EXHAUSTIVITÉ des xrefs, pas leur contenu.** Ces deux sélecteurs n'ont, dans tout
le build, que **deux** appelants :

| sélecteur | unique appelant |
|---|---|
| `AllAliveMachines` | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeavyRailRifle_AttackAbility$$CreateBehaviour` |
| `EnemyMachine` | `IdunBattleLogic.Entities.Abilities.Triggered.Loki.IllusionsOfTzeentchAbility$$CreateBehaviour` |

**Aucun n'est un `Enhancement*`.** La famille `IsEnhancementTarget` →
`IdunBattle.Entities.Selectors.EnhancementTargetSelector` opère sur le sélecteur d'UNITÉS que
l'ability lui passe ; aucune ne lui passe un sélecteur de machines. Ce n'est donc pas un défaut de
notre montage, et il n'y a rien à réparer — le vocabulaire du gameconfig le dit d'ailleurs déjà
(`unitAmount`).

⇒ **Poser la MoW reste utile** (elle joue, elle encaisse), mais ne jamais compter sur un buff ou un
debuff d'environnement pour l'atteindre.

### Mais leurs SUMMONS, si — et notre dérivation les lit (2026-08-24)

Une MoW **invoque** : `astraOrdnanceBattery` porte `ForwardSpotter` → `astraSmnGuardsman`
(ordinal `1143`). Sur les 14 porteurs de summon d'une BC PvP, **un est une machine**.

Le summon, lui, est une **UNITÉ** — donc dans la famille de sélecteurs que l'enhancement balaie.
Il est atteint dès que son id est dans les `Targets`, et il y est : les machines figurent dans
`BC.Units` **avec leurs `ActiveAbilities`**, exactement ce que la dérivation de summons parcourt.
Mesuré, camp adverse de la proposition n=1 :

```
+3 SUMMON(S) que l'adversaire peut invoquer (derives de ses abilities)
CIBLES : ultraTigurius, blackHaarken, bloodDeathCompany, blackPossession, darkaAzrael,
         astraOrdnanceBattery, blackSmnBloodletter, thousSmnBlueHorror, astraSmnGuardsman
```

⚠ **La jointure est obligatoire, et c'est elle qui pourrait faire un faux zéro.** Le catalogue est
keyé par NOM (`ForwardSpotter`), les unités référencent par ORDINAL (`1143`) : sans le join
`ActiveAbilityType`, aucun summon ne serait dérivé — ni ceux des héros, ni ceux des machines.

⇒ **La machine n'est jamais buffée ; ce qu'elle pose sur le plateau l'est.**
