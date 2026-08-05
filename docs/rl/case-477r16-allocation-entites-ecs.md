# #477-r16 — La règle d'allocation des entités ECS

**Build** `rnca9r7q6c`. RE Ghidra + confrontation live session Frida **8**
(`probe_477r16_allocation_entites_ecs.py`, 4 runners montés et disposés).

## Verdict en une ligne

**MÉCANIQUE, sans aucun terme libre et sans branche non exercée sur l'axe déduplication.** L'ordre
et le nombre d'allocations se reproduisent depuis la `BattleConfiguration` **plus deux tables
statiques du binaire**, toutes deux lues et mirrorées. Prédiction posée **avant** mesure, vérifiée
**12 critères sur 12**, sur **trois** boards de tailles distinctes (35 / 63 / 70 tuiles) et
**huit** BC, dont sept fabriqués pour faire varier un terme à la fois. Un émetteur de flux est
constructible.

⚠ **Les deux points faibles ont été attaqués comme tels, et par la même méthode : sortir du
régime où le modèle ne peut pas se tromper.**

- Le scalaire `derived`, mesuré par DIFFÉRENCE, absorbait silencieusement toute allocation
  manquée avant les tuiles. Il est **prédit** depuis `#477-r16-r1` (§3ter), et le contre-test le
  fait **bouger dans les deux sens**.
- La **branche de déduplication** d'`IncludeEnvironmentAbility` ne s'exerçait sur aucun montage :
  `BC.EnvironmentAbilities` était vide partout, et **trois modèles de `E` incompatibles** y
  rendaient la même valeur. Elle est **confrontée** depuis `#477-r16-r1-r1` (§3bis), les deux
  concurrents sont **réfutés par les chiffres**, et un **témoin positif** prouve que la
  désérialisation mord — sans lui, un élément ignoré en silence aurait rendu tous les montages
  dédupliqués verts pour rien.

## 1. Qui alloue

Allocateur **unique** — `IdunBattle.Entities.Components.MatchComponent$$NextId` :

```
this.<+0x10> += 1 ; return this.<+0x10>      // PRE-incrementation
```

`MatchComponent$$.ctor` pose le champ à **1**. `MatchComponent$$ReturnLastId` le décrémente.

Les **neuf** sites d'appel (xrefs Ghidra — liste exhaustive, il n'existe aucune autre voie) :

| fonction native | allocations | note |
|---|---|---|
| `AddPlayerOperation$$Execute` | 1 / joueur | → `Blueprints$$Player` |
| `AddEnvironmentAbilityOperation$$Execute` | 1 / ability | deux sites, branches **exclusives** |
| `AddEnvironmentAbilityOperation$$CreateEntity` | 1 / ability | idem ; non appelé par `Execute` |
| `AddTileOperation$$Execute` | 1 / tuile | **rollback** si la factory rend null |
| `AddTileOperation$$CreateTile` | 1 / tuile | **rollback** idem |
| `AddUnitOperation$$Execute` | **1 + 1 par pied** | 2ᵉ site **dans une boucle** sur les tuiles occupées |
| `AddMachineOperation$$Execute` | 1 / machine | `Blueprints$$Machine` — **aucun pied** |
| `AddMachineOfWarPlatformOperation$$Execute` | 1 / plateforme | |
| `AddEffectOperation$$Execute` | 1 / effet | pendant le déroulé |

⚠ **Le rollback n'existe QUE sur le chemin tuile.** `AddUnitOperation` et `AddMachineOperation`
rendent `null` sans appeler `ReturnLastId` : un échec de création **brûle l'id**. Un émetteur qui
suppose « pas d'entité ⇒ pas d'id consommé » divergera sur toute la suite du flux.

## 2. Pourquoi le pas de 2

Ce n'est **pas** « deux entités par unité » : `AddUnitOperation$$Execute` alloue l'unité, puis entre
dans une **boucle** sur les tuiles occupées et alloue une `FootEntity` par tuile
(`Blueprints$$UnitFoot` → `UnitComponent$$AddFoot`). `IdunBattle.Entities.Enum.EntityType` porte
d'ailleurs `5=UnitFoot` à côté de `1=Unit`.

Le pas vaut donc **1 + nb de pieds**, et il tombe à 2 uniquement parce que toutes les unités
observables ici sont mono-tuile — c'est **structurel** : `AddPredefinedUnits` passe
`TExtensions.ToList(<un tileId>)`, une liste à UN élément. Le flux le confirme, tag par tag
(`Tag=Unit_Foot_Tile_Id_1:<tileId>`, numéroté, donc extensible).

## 3. Ce que compte l'offset initial

`IdunBattle.Operations.SetupGameOperation$$Execute` fixe une séquence **invariante** :

```
InitializeMatch(matchEntityId = 1, Width, Height, ...)   entite Match = id LITTERAL 1,
                                                         puis InitializeMatchOperation$$Execute
                                                         fait `+= 1` -> compteur = 2
AddPlayers()                    SortedDictionary  -> ordre par cle
AddEnvironmentAbilities()       List de GetEnvironmentAbilities
AddTiles()                      for row in 0..Width-1 { for col in 0..Height-1 }
SetupRoom()                     n'alloue RIEN
AddMachinePlatform()            DEUX appels (teams 2 puis 1), 1 entite chacun
RevealHumanPlayerRoom()         n'alloue RIEN
AddPredefinedUnits() / AddPredefinedMachines() / AddBossUnit()
```

⇒ **l'id 2 n'est jamais attribué** (le Match prend 1, le compteur saute à 2, le premier `NextId`
rend 3). Mesuré : les trois joueurs reçoivent 3, 4, 5 sur les trois boards.

D'où, sans aucun paramètre ajusté :

```
premier id de tuile  = 3 + P + E
premier id d'unite   = premier id de tuile + Width*Height + 2      (+2 = plateformes MoW)
```

`P` se lit dans `BC.Player.Players`. **`E` n'est PAS entièrement dans la BC**, et ses termes
n'ont pas tous le même statut — **trois sont CONDITIONNELS** (cf. § suivant) :

| terme de E | valeur sur le seed | source | ajout |
|---|---:|---|---|
| `BC.EnvironmentAbilities` + `…Enhancements` (2 `AddRange`) | 0 | la BC | inconditionnel |
| `GetDerivedEnvironmentAbilities(passif)` | **1** | table **statique** `+0x38` (2 entrées) | inconditionnel |
| `EnvDespoiledGroundTileDamage`, `EnvFireTileDamage` | 2 | constantes en dur | **dédupliqué** (confronté) |
| `StaticBattleRules.DamageTrait$$GetDamageTraitAbilities` | 3 | table **statique** (`.cctor`, 3 entrées) | inconditionnel |
| `EnvCapturePointShield` si `GameMode == SyncPVP` | 0 | idem | **dédupliqué** (non exercé, `#477-r16-r1-r1-r1`) |

Deux tables statiques du binaire entrent donc dans un offset qu'on croirait dérivable du BC.
**Un émetteur doit les mirrorer.**

### 3bis. `IncludeEnvironmentAbility` DÉDUPLIQUE — la somme n'est pas une somme (#477-r16-r1-r1, CONFRONTÉ)

`IdunBattle.Operations.SetupGameOperation$$IncludeEnvironmentAbility` n'est **pas** un `Add` :
elle construit un prédicat sur l'id, appelle `idun.shared.extensions.ListExtensions$$Contains<T>`
et **retourne sans rien ajouter** si la liste porte déjà cette ability. Le prédicat
(`SetupGameOperation.<>c__DisplayClass18_0$$<IncludeEnvironmentAbility>b__0`) se réduit à
`return *(int*)(cfg + 0x10) == this.<+0x10>` — c'est-à-dire **`ConfigId.AbilityType`**, et lui
seul : ni `VariantId`, ni `Level`, ni `PlayerId` n'entrent dans la comparaison. Les **deux
boucles** (derived, damage traits) font au contraire un `List.Add` **direct** et ne dédupliquent
rien. L'ordre de construction est donc :

```
list.AddRange(BC.EnvironmentAbilities.EnvironmentAbilities)              # AddRange
list.AddRange(BC.EnvironmentAbilities.EnhancementsEnvironmentAbilities)  # AddRange
foreach kv in BC.Abilities.PassiveAbilities: list.Add(derived(kv.Key))   # Add DIRECT
IncludeEnvironmentAbility(EnvDespoiledGroundTileDamage)                  # DEDUP
IncludeEnvironmentAbility(EnvFireTileDamage)                             # DEDUP
foreach x in GetDamageTraitAbilities(): list.Add(x)                      # Add DIRECT
if SyncPVP: IncludeEnvironmentAbility(EnvCapturePointShield)             # DEDUP
```

**Trois modèles de `E` rendent la même valeur quand `BC.EnvironmentAbilities` est vide** — c'est
tout le problème, et la raison pour laquelle « ça tombe juste » ne prouvait rien : le modèle
**DÉDUP** (celui-ci), le modèle **SOMME NAIVE** (`|BC| + derived + 2 + 3 + syncpvp`, la formule
de la première version) et le modèle **TOUT-DÉDUPLIQUÉ** (les cinq termes dédupliquent) valent
tous `6` sur le seed. Cinq montages les séparent, chacun ne changeant qu'une chose, prédictions
imprimées **avant** la mesure (board `C1_02`, session 8) :

| `BC.EnvironmentAbilities.EnvironmentAbilities` | DÉDUP | NAIF | TOUT-DÉDUP | **mesuré** |
|---|---:|---:|---:|---:|
| *(vide — le seed, témoin)* | 6 | 6 | 6 | **6** |
| `[EnvReinforcementShield]` — **témoin positif** | 7 | 7 | 7 | **7** |
| `[EnvFireTileDamage]` | **6** | 7 | 6 | **6** |
| `[EnvFireTileDamage, EnvFireTileDamage]` | **7** | 8 | 6 | **7** |
| `[EnvFireTileDamage, EnvDespoiledGroundTileDamage]` | **6** | 8 | 6 | **6** |
| `[EnvReinforcementShield]` + passif `PowerUp_ReinforcementShield` | **8** | 8 | 7 | **8** |

`E` est mesuré comme l'intervalle entre le dernier joueur et la première tuile —
`AddEnvironmentAbilityOperation$$Execute` alloue sans émettre aucune action dans le flux.
**SOMME NAIVE réfutée** sur trois montages, **TOUT-DÉDUPLIQUÉ** sur deux. Trois faits en
découlent, chacun mesuré :

1. **`IncludeEnvironmentAbility` voit ce que les `AddRange` ont posé** — `EnvFireTileDamage` déjà
   dans le BC n'est pas ajouté une seconde fois. C'est aussi la seule dépendance d'**ORDRE**
   observable ici : des `Include` joués **avant** les `AddRange` auraient rendu `7`.
2. **`List.AddRange` ne déduplique rien** — deux fois la même ability entrent toutes les deux, et
   seul l'`Include` correspondant s'abstient (`7`, pas `8` ni `6`).
3. **La boucle `derived` ne déduplique rien non plus** — elle re-pose `EnvReinforcementShield`
   alors qu'il est déjà dans la liste (`8`, ce qu'aucun modèle dédupliquant ne peut rendre).

⚠ **Le témoin positif n'est pas décoratif : c'est le cran anti-dégénéré.** Trois des cinq
montages prédisent « `E` ne bouge pas » — exactement ce qu'aurait rendu un élément **ignoré à la
désérialisation**. Sans un montage qui fait bouger `E`, leur immobilité se serait lue comme une
confirmation de la déduplication alors qu'elle n'aurait prouvé que l'inertie du harnais. Le probe
**refuse de conclure** si le témoin positif ne monte pas de 1.

### 3quater. La forme sérialisée d'un élément — LUE, puis confrontée

`buildNormalizedBC` ne touche que `Board`, `SpawnPointSetIndex` et `Units[]` : le bloc
`EnvironmentAbilities` du seed BC traverse **intact** jusqu'à
`JsonConvert.DeserializeObject(json, BattleConfiguration)`. La forme attendue est donc celle de
Newtonsoft pour `IdunBattle.Configuration.EnvironmentAbilityConfiguration`, dont la disposition
est **mesurée** (RPC `classFields`, `rnca9r7q6c`) — les getters d'auto-propriété sont des corps
triviaux **dédupliqués** par IL2CPP, donc absents de `frida/methods.tsv` :

| off | champ | type |
|---|---|---|
| `+0x10` | `ConfigId` | `IdunShared.TriggeredAbilityConfigId` (`AbilityType` `+0x00`, `VariantId` `+0x08`) |
| `+0x20` | `Level` | `Idun.Shared.Level` |
| `+0x24` | `PlayerId` | `Nullable<int>` |

`EnhancementsEnvironmentAbilityConfiguration` en hérite et ajoute `Targets` `+0x30`,
`Stack` `+0x38`.

⚠ **`ConfigId` n'est PAS un objet JSON.** `IdunShared.TriggeredAbilityConfigId` porte
`TriggeredAbilityConfigIdJsonConverter : Idun.Shared.Serialization.StringJsonConverter<T>` :
il se sérialise en **chaîne**. Écriture (`$$ToConfigId`) : `Enum.ToString(AbilityType)`, puis
`+ ":" + VariantId` si le variant est non vide. Lecture (`$$CreateFromString`) : chaîne vide →
`{0, null}` ; chaîne avec séparateur → `Split`, `[0]` parsé par
`Enum.TryParse<TriggeredAbilityType>`, `[1]` = `VariantId` ; sinon la chaîne entière est parsée.
Un `TryParse` en échec **ne fait pas échouer le montage** : il rend `AbilityType = 0`, et
l'entité est allouée quand même.

Le séparateur est **lu**, pas deviné : le `DAT_*` que `$$ToConfigId` passe à `String.Concat` est
un littéral IL2CPP, que la table livrée par #477-r15-r1 résout en `":"`
(`string_literals.charger().by_va(<slot cité par ToConfigId>)`, index 3113 sur `rnca9r7q6c`).
Corroboré par le gameconfig, où 66 ids d'ability portent cette forme
(`EnvFactionSummons:AdeptusMechanicus`).

D'où le montage minimal, confronté :

```json
{"ConfigId": "EnvFireTileDamage", "Level": 1, "PlayerId": null}
```

`Level >= 1` : `0` est la valeur « verrouillé » que `Idun.Shared.Level$$ToZeroBasedIndex` refuse
(`InvalidOperationException`), verrou déjà payé en #237. `PlayerId` null → `Execute` retombe sur
`StateExtensions$$GetPlayer(state, 2)`.

`AddEnvironmentAbilityOperation$$Execute` teste le **type** de la config
(`EnhancementsEnvironmentAbilityConfiguration` ⇒ `Blueprints$$EnhancementEnvironmentAbility`,
sinon `Blueprints$$EnvironmentAbility`) : deux branches **exclusives**, **un** `NextId` dans
chacune. Le compte est donc `1` par config, quelle que soit la liste d'origine.

### 3ter. `derived` est LU, plus mesuré par différence (#477-r16-r1, FERMÉ)

`StaticBattleRules.TriggeredAbility$$GetDerivedEnvironmentAbilities(passiveAbilityType)` est un
`TryGetValue` sur le champ **statique `+0x38`** de `StaticBattleRules.TriggeredAbility`, un
`Dictionary<TriggeredAbilityType, TriggeredAbilityType>` — signature lue dans
`frida/methods.tsv`, pas déduite. La valeur trouvée est un **scalaire**, emballé par
`IdunBattleLogic.Extensions.TExtensions$$ToList<T>` : le retour est une liste à **UN** élément,
ou `null`. Le `.cctor` y écrit **DEUX** entrées, et rien d'autre :

| clé (passif du BC) | valeur (env ability allouée) |
|---|---|
| `PowerUp_ReinforcementShield` | `EnvReinforcementShield` |
| `Ambush` | `EnvAmbushResurrect` |

⚠ **Deux, et pas une de plus** : le `.cctor` fait 980 lignes décompilées et peuple **19** champs
statiques, mais il les écrit dans une séquence d'offsets **strictement croissante**
(`+0x0, +0x8, +0x10, … +0x90`), chacun **une seule fois**. `+0x38` n'a donc **qu'un seul site
d'écriture**, et il porte ces deux `Dictionary.Add`.

⚠ **La garde de `TExtensions$$ToList<T>` est le `x != null` générique d'IL2CPP — pas « valeur ≠
défaut », et sur un enum elle est TOUJOURS vraie.** `ToList<T>` teste `FUN_1801f53a0(klass, &v)`
avant son unique `List.Add` et rend `null` si le test échoue. Le helper n'est pas nommé, mais
chacune de ses trois marches se lit par un **export nommé** du même binaire :

```c
if (-1 < *(int*)(klass + 0x28))            return *(void**)v != NULL;  // il2cpp_class_is_valuetype
if (klass->[0x60] != 0 && (klass->[0x135] & 8))  return *(char*)v;     // il2cpp_class_is_inflated
return true;                                                           // valuetype simple
```

`il2cpp_class_is_valuetype(k)` **est** `*(uint*)(k+0x28) >> 31` ; `il2cpp_class_is_inflated(k)`
**est** `*(void**)(k+0x60) != 0` ; et le bit `& 8` de `+0x135` est `nullabletype`, encadré par
`il2cpp_class_is_enum` (bit 2) et `il2cpp_class_is_generic` (bit 4) — la marche lit alors le
premier octet du `Nullable<T>`, c'est-à-dire `hasValue`. Pour `T = TriggeredAbilityType` (enum,
value type, non inflaté), **la garde rend `true` inconditionnellement**, y compris pour la valeur
`0`. Le **seul** chemin qui rend `null` est donc le `TryGetValue` négatif — la table `+0x38`
détermine entièrement le résultat.

La boucle appelante n'en lit que les **clés**, et le dictionnaire itéré est
**`BC.Abilities.PassiveAbilities`** (`BC+0x90` = `AbilitiesConfiguration` par son `.ctor`,
`+0x18` = le dict des passifs, cf. `AbilitiesConfiguration$$GetPassive`). D'où :

```
derived = |{PowerUp_ReinforcementShield, Ambush} INTER keys(BC.Abilities.PassiveAbilities)|
```

**Domaine `0..2`.** Le `1` du seed n'est donc pas un scalaire ajusté : `Ambush` y est présent,
`PowerUp_ReinforcementShield` non. `GetEnvironmentAbilities` est le **seul** appelant (xrefs).

**Contre-test joué, et il DISCRIMINE** (`probe … --contre-derived`, session 8, board `C1_02`,
prédictions imprimées avant mesure) :

| montage | `derived` | 1ʳᵉ tuile prévue | mesurée |
|---|---:|---:|---:|
| seed intact (témoin, 3 boards) | 1 | 12 | **12** |
| `+ PowerUp_ReinforcementShield` dans `BC.Abilities.PassiveAbilities` | 2 | 13 | **13** |
| `− Ambush` | 0 | 11 | **11** |

Un terme obtenu par différence aurait absorbé n'importe quelle allocation manquée en amont ;
celui-ci **bouge dans les deux sens, de la quantité prévue**. Le probe porte un cran
anti-régime-dégénéré : `_load_seed_bc` re-synthétise `BC.Abilities` (#254) et pourrait recombler
une clé retirée — si la prédiction de la variante n'est pas distincte du témoin, il **refuse de
conclure** au lieu de rendre un vert.

## 4. Effets, summons, machines, projectiles

Même compteur, aucune exception : un **effet** = 1 (`AddEffectOperation$$Execute`, au fil du
déroulé — cohérent avec les `Effect_Id` 97/98 consécutifs mesurés en #477-r15) ; un **summon** passe
par `AddUnitOperation` donc 1 + pieds ; une **machine** = 1 sans pied ; une **plateforme MoW** = 1.
Les **projectiles n'ont pas d'entité** — ils ne figurent pas dans `EntityType`.

## 5. Chemins non déterministes

Aucun sur le chemin d'allocation, à une réserve près :

- `AddPlayers` — `SortedDictionary` : ordre **par clé**, déterministe et dérivable du BC ;
- `AddTiles` — double boucle **indexée** ;
- `AddPredefinedUnits` / `AddPredefinedMachines` — `List` ;
- `SetupRoom` itère un **`HashSet<int>`**, mais **n'alloue rien** : sans effet sur les ids ;
- rien d'asynchrone — les coroutines (`System_GameSetup_GroupHandler$$ExecuteStepInternalCoroutine`)
  sont côté **vue**, pas dans la logique.

⚠ **La seule réserve** : `GetEnvironmentAbilities` itère un **`Dictionary<,>`**
(`BC.Abilities.PassiveAbilities`) pour appeler
`GetDerivedEnvironmentAbilities`. `Dictionary` ne garantit pas son ordre par contrat ;
en pratique il rend l'ordre d'insertion tant qu'aucun `Remove` n'a eu lieu, et les insertions
viennent de la désérialisation du BC. Cela n'affecte que **l'ordre interne** du bloc env abilities,
jamais leur nombre ni les blocs suivants — donc jamais les ids des tuiles ni des unités.

## Mesure — 12/12, trois tailles de board et huit BC

```
python scripts/python/probe_477r16_allocation_entites_ecs.py \
    --session <sid> --mow adeptExorcist --contre-derived --contre-dedup
python scripts/python/probe_477r16_allocation_entites_ecs.py --auto-test-gardes   # OFFLINE
python -m pytest tests/engine/test_477r16r1r1_dedup_env_abilities_offline.py      # OFFLINE
```

joueurs `3..2+P` / nb tuiles == `Width*Height` / tuiles contiguës / 2 plateformes MoW juste après /
première unité == 1ʳᵉ tuile + T + 2 / pas == 2 / aucun trou dans `3..max` / `derived` invariant /
`derived` mesuré == `derived` **lu** / tout pas expliqué par `1 + pieds + intercalées` /
`derived` **fait varier expres** suit la prédiction / **la branche de déduplication exercée sépare
les trois modèles** / **la dépendance d'ordre `derived → Include` est déclarée inobservable, et
rougit si elle cesse de l'être**.

Le probe **refuse de conclure** sous trois tailles distinctes — deux points valident n'importe
quelle droite, et `MC1_67`/`C1_70` font tous deux 63 tuiles (piège payé en #477-r15). Il refuse
**aussi** de conclure si une mutation de contre-épreuve n'a pas mordu, et si le **témoin positif**
du volet déduplication n'a pas fait bouger `E`.

⚠ **Chaque cran doit avoir été VU rouge — `--auto-test-gardes` l'exige.** Les verdicts sont des
fonctions **pures** (`verdicts_etages`, `verdict_contre_derived`, `verdict_dedup`) que ce mode
exerce sur une mesure **fabriquée conforme**, puis **mutée** une chose à la fois : une tuile de
moins, un trou dans les ids, une seule plateforme, un pas de 3, la table `+0x38` fausse de +1,
toutes les tuiles décalées de 1… Chaque mutation doit faire tomber le cran nommé. Un cran qui
reste vert est **inerte** et fait échouer le probe — c'est le mode de panne mesuré en #430, où
`probe_181` rendait `0` inconditionnellement. Mesuré : **10 mutations d'étage, 9 cas de
contre-épreuve, 0 inerte**. Le test offline, lui, a été vu rouge en désarmant la déduplication
dans `deriver_regle` (2 tests sur 8 tombent, dont le principal).

## Cinq pièges payés ici même

1. **Un accord parfait peut venir de deux erreurs qui s'annulent.** La première version prédisait
   `3 + P + E + T` avec un `E` trop grand de 2 et **sans** les plateformes MoW : la prédiction sur
   l'unité tombait juste sur les **trois** boards (49 / 77 / 84) alors que l'offset des tuiles était
   faux. Un seul point d'observation ne valide pas une décomposition — le probe vérifie désormais
   **chaque étage séparément**.
2. **L'enum ne dit pas la table.** `E` avait été dérivé de `IdunBattle.Entities.Enum.DamageTrait`
   (6 membres) au lieu de `StaticBattleRules.DamageTrait$$.cctor` (**3** entrées). L'enum nomme des
   *traits*, la table nomme des *abilities*.
3. **Le build qui fait foi ne se devine pas.** Le probe re-dérivait « quel build » à la main et
   retenait `gqfc5mff6c` (archive) au lieu de `rnca9r7q6c`. Foyer unique :
   `symbols_layout.current_build()`.
4. **Une liste d'`Add` n'est pas forcément une somme.** Trois des cinq termes de `E` passent par
   `IncludeEnvironmentAbility`, qui **déduplique** (§3bis) — la formule additive tenait par
   accident, parce que les listes du BC sont vides sur ce seed. Le nom de la fonction ne le
   disait pas ; seul son corps le dit. Corollaire général : **lire le corps de chaque « helper
   d'ajout » avant de compter ses appels.**
5. **Un montage qui prédit « rien ne bouge » ne prouve rien SANS un montage qui bouge.** Trois des
   cinq montages de déduplication prédisent une valeur **inchangée** — indistinguable, en l'état,
   d'un élément que la désérialisation aurait ignoré. La forme sérialisée n'était d'ailleurs pas
   celle qu'on croyait : l'ancien extracteur lisait un champ `Id` qui **n'existe pas** (c'est
   `ConfigId`, et c'est une **chaîne**). Sans le témoin positif, le volet entier serait passé au
   vert en mesurant l'inertie du harnais. **Toute contre-épreuve dont la prédiction est un
   non-changement exige un témoin de changement dans la même passe.**

## Résidus

- ~~**#477-r16-r1**~~ — **FERMÉ** (§3ter) : la table est lue (2 entrées), `derived` est prédit et
  confronté, et le contre-test le fait varier dans les deux sens.
- ~~**#477-r16-r1-r1**~~ — **FERMÉ** (§3bis, §3quater) : la branche **DÉDUPLICATION** est exercée
  sur cinq montages, les deux modèles concurrents sont réfutés par les chiffres, la **forme
  sérialisée** d'un élément est lue puis confrontée, et la garde de `TExtensions$$ToList` est
  **lue** (l'hypothèse « valeur ≠ défaut » est réfutée : c'est `x != null`, toujours vrai sur un
  enum).
- **#477-r16-r1-r1-r1** — **deux branches conditionnelles restent NON EXERCÉES**, et elles sont
  du même type que celle que cette tranche vient de fermer :
  **(a)** la seconde liste, `BC.EnvironmentAbilities.EnhancementsEnvironmentAbilities` — le
  `AddRange` est le même, mais `AddEnvironmentAbilityOperation$$Execute` y prend l'**autre**
  branche (`Blueprints$$EnhancementEnvironmentAbility`), et un
  `EnhancementsEnvironmentAbilityConfiguration` porte deux champs de plus (`Targets`, `Stack`)
  dont la forme sérialisée n'a jamais été observée ;
  **(b)** `EnvCapturePointShield` en `GameMode == SyncPVP` — le terme vaut `0` sur **tous** les
  montages joués (le seed est `Campaign`), donc la troisième déduplication n'a jamais été
  exercée. Montage à écrire : un BC en `SyncPVP` portant déjà `EnvCapturePointShield`.
- **#477-r16-r2** — la **boucle sur les pieds** est lue au décompilé mais **non confrontée** : aucun
  porteur multi-tuiles n'est atteignable par les montages testés (les unités prédéfinies sont
  mono-tuile par construction, une MoW n'a aucun pied). Le porteur est le **BOSS**
  (`AddBossUnit` / `GetBossPlatform`) — montage à écrire.

## Ce que je n'ai PAS fait

- **Aucun émetteur écrit** — la tranche RE et mesure, elle ne porte rien.
  `engine/runner/events.py` et le writer de grammaire n'ont pas été touchés.
- **Le déroulé n'est pas confronté** — la mesure porte sur `System_GameSetup`. Les allocations
  d'effets *pendant* la bataille suivent le même compteur (lu), mais leur ORDRE dépend de l'ordre
  d'exécution des opérations : c'est la fidélité du port, pas une règle d'allocation supplémentaire.
- **`replaySteps` / `replayRngEvents` non utilisés** — déployés pendant la fenêtre #10, mais ma
  mesure n'en avait pas besoin : le flux porte déjà `Entity=` sur chaque ligne.
