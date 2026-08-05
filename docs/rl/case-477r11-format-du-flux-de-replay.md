# #477-r11 — Le FORMAT du flux de replay natif : grammaire, couverture, déterminisme

**Build** `rnca9r7q6c`. Mesuré en live, sessions Frida **6 puis 7** (mêmes chiffres au caractère
près des deux côtés d'un reinject). Probe : `scripts/python/probe_477r11_replay_stream_format.py`.

## Verdict en une ligne

Le flux est **déterministe au caractère près** — trois rejeux, deux boards, deux sessions Frida,
**zéro divergence, pas même incidente** — sa grammaire tient en **quatre formes**, et son
vocabulaire est **entièrement dérivable** de trois enums natifs. Un comparateur de conformité est
donc **constructible**, et la barre est plus haute que la forme canonique espérée : l'égalité
BRUTE suffit. Ce qu'il ne pourra **pas** couvrir est nommé au § 5 — et ce n'est pas mince :
le flux **ne dit jamais quelle unité est quelle entité**.

## 1. La grammaire, lue sur le texte réel

```
Group=<GroupType> Entity=<id|NO_ENTITY> Source=<nom symbolique|vide> InitialTarget=<id|vide>
    Action=<StepType> Entity=<id|NO_ENTITY>
        Tag=<TagKey>:<valeur>
Finish_Group
```

| trait | mesure |
|---|---|
| unité d'indentation | **4 ESPACES** par niveau |
| séparateur de ligne | **LF** |
| profondeur max observée | 6 niveaux (24 caractères) |
| équilibrage | vérifié **par pile** — 223 `Group=` / 223 `Finish_Group`, 46 racines (MC1_67) |
| lignes hors des 4 formes | **0** sur 2 573 |

⚠ **La RE offline disait « tabulations »** (`case-477` § 10.7, dérivée de `StreamCache` sans
pouvoir lire les littéraux IL2CPP). C'est **4 espaces**. Le gabarit reste illisible de Ghidra ;
c'est le texte qui tranche.

⚠ **Ne pas mesurer le séparateur sur un fichier**. `Path.write_text` traduit `\n` en `\r\n` sous
Windows : le premier dump de flux portait des CRLF **qui n'existent pas dans le natif**. Le probe
mesure sur la chaîne rendue par le RPC.

**Trois pièges de lecture**, tous capables d'inverser un verdict :

- **`Match_CurrentPlayerId` / `Match_PreviousPlayerId` portent un id d'ENTITÉ ECS, pas un
  `PlayerId`.** Sur notre seed BC : `E3 = P11`, `E4 = P12`, `E5 = P13`. La correspondance se lit
  dans le flux (`Action=AddPlayer Entity=E` suivi de `Tag=Player_Id:P`). Lue à l'envers, elle
  attribue chaque tour au mauvais joueur — c'est exactement l'erreur que la première version du
  probe a commise.
- **`Match_CurrentPlayerId` annonce le joueur SUIVANT.** Le joueur qui vient de jouer est
  `Match_PreviousPlayerId`, sur le `Action=PrepareTurn` qui clôt le tour.
- **`Source=` d'un groupe est un nom SYMBOLIQUE**, pas un id : `Loki_NormalAttack`,
  `AvalancheOfMuscle_ExtraDamage`, `BlockEnteringUnits`, `BeastSlayer_ExtraBlock`. C'est le
  meilleur point d'ancrage lisible du flux.

**Une forme structurelle que la RE ne laissait pas prévoir** : `Action=` existe **à profondeur 0**,
hors de tout groupe — mesuré `PrepareTurn`, `ChangeStats`, `FinishMatch`. Un parseur qui exige un
groupe ouvert rejette du flux valide.

## 2. Le vocabulaire est DÉRIVABLE — et l'observé n'en est qu'un plancher

Trois enums natifs, lus dans `data/symbols/<build>/frida/enums.tsv` :

| enum | membres | observés (C1_70, 1v1) | observés (MC1_67, 3v3) |
|---|---:|---:|---:|
| `IdunBattle.Streams.GroupType` (ligne `Group=`) | **104** | 13 | 16 |
| `IdunBattle.Streams.StepType` (ligne `Action=`) | **62** | 17 | 21 |
| `IdunBattle.Streams.TagKey` (ligne `Tag=`) | **244** | 68 | 83 |

⚠ **Le périmètre d'un comparateur doit se dériver des ENUMS, jamais de l'observé.** Deux batailles
n'ont exercé que 16 des 104 types de groupe : un comparateur calibré sur l'observé serait muet sur
les 88 autres, **sans le dire**. L'inventaire complet (`OBS` / non vu, membre par membre) est écrit
par le probe dans `logs/replay-stream-couverture-<stamp>.txt`.

## 3. Ce que le flux CONTIENT — confirmé nommément sur le texte

Les détecteurs `Runner.Cheats.*` reconnaissent leurs motifs par texte ; les grandeurs
correspondantes y figurent bien, **vérifié sur le flux réel** et non repris de la RE :

```
Group=Damage Entity=77 Source= InitialTarget=
    Action=UnitDamaged Entity=77
        Tag=UnitStats_RemainingHealth:4176      Tag=Attack_DidCrit:0
        Tag=UnitStats_RemainingArmor:0          Tag=Attack_DidBlock:0
        Tag=UnitStats_NumberOfMembers:1         Tag=Attack_DidEvade:0
        Tag=Attack_Is_First_Hit:1               Tag=Attack_WasOverkill:0
        Tag=Target_Id:77                        Tag=Attack_WasMemberKilled:0
        Tag=Attacker_Id:79                      Tag=Amount:2349
        Tag=Active_Ability_Type:69              Tag=DamageProfileType:0
        Tag=Shields_RemainingAmount:0
```

`Amount` = le dégât **final** appliqué. Un coup à hits multiples produit **un groupe `Damage` par
hit**, chacun avec son `Amount` et son `RemainingHealth` — la décomposition par étage est donc
lisible telle quelle.

**`AbilityVariableAmount` (TagKey 189) existe dans l'enum mais n'a été observé dans AUCUN de mes
scénarios** — aucune ability à variable n'y a été castée. Il est donc *nommé* mais **non confronté**.

## 4. Le DÉTERMINISME — mesuré, avec contre-épreuve

Deux batailles **séquentielles** (jamais concurrentes : deux runners coexistants partageraient
l'état du process et l'accord serait plus faible), même seed, même board, mêmes rosters, même
pilotage. Comparaison **caractère par caractère**, ce que fait
`Runner.ReplayValidator$$CompareOutputStream` via `System.String$$get_Chars`.

| scénario | flux A | flux B | verdict |
|---|---:|---:|---|
| C1_70, 1v1, seed 777 | 23 020 car., 633 lignes, 4 pas, 5 evts PRNG | idem | **IDENTIQUES** |
| MC1_67, 3v3, seed 31337 | 107 837 car., 2 573 lignes, 7 pas, 61 evts PRNG | idem | **IDENTIQUES** |

Rejoué à l'identique sur la **session 7** après reinject : mêmes 23 020 / 107 837 caractères. Le
déterminisme survit donc au redémarrage de la session Frida.

**Ventilation** : il n'y a **rien à ventiler**. Ni incidente (les ids d'entité ECS sont eux-mêmes
reproductibles — l'ordre d'allocation ne bouge pas), ni dérivée du PRNG, ni essentielle. La forme
canonique écrite dans le probe (renumérotation des ids d'entité) **n'a jamais eu à servir** ; elle
reste, comme filet, pour le jour où un scénario la réclamera.

**CONTRE-ÉPREUVE — sans elle, « identiques » ne vaut rien.** Un capteur qui rendrait une chaîne en
cache, ou un flux dégénéré, donnerait exactement le même vert. Bras C, **seed + 1**, tout le reste
égal :

| scénario | 1er écart | lignes divergentes | longueurs | evts PRNG |
|---|---:|---:|---|---:|
| C1_70 | car. 16 962 (`RemainingHealth` 5551 vs 4849) | 9 / 634 | 23 020 = 23 020 | 5 vs 5 |
| MC1_67 | car. 45 504 | **1 294 / 2 711** | 107 837 vs **114 461** | 61 vs **76** |

⇒ la comparaison **discrimine**, donc l'égalité A == B est une mesure.

## 5. Ce que le flux N'A PAS — liste dérivée et PUBLIÉE

> Un comparateur qui ne compare que ce que les deux côtés possèdent est une **projection
> implicite** — pire que le registre de résidus tenu à la main, parce que personne ne l'a écrite.
> **Non comparé ≠ égal.**

### 5a. `IdunBattle.Entities.Enum.StatType` (27) → porteur

| état | stats |
|---|---|
| **AUCUN porteur** | `Defense`, `EvasionChance` |
| **MODIFICATION seule** — le flux rapporte le delta appliqué, **jamais la valeur courante** | `ExtraHits`, `ExtraHitsMelee`, `ExtraMaxDamage`, `ExtraPierce`, `ExtraPierceMelee`, `ExtraPierceRanged`, `ExtraRange` |
| **par JOUEUR, pas par unité** | `TurnsStarted` (→ `Match_AmountOfTurnsStartedByCurrentPlayer`) |

⚠ **Ce tableau vient d'une table d'appariement ÉCRITE, pas d'un critère par nom** — et c'est la
faute que ce probe a d'abord commise : apparier par sous-chaîne rendait **8 stats « sans
porteur », dont SIX étaient fausses**. `CriticalChance` est porté par `UnitStats_CritChance`
(abrégé), `PassiveAbilityLevel` par `UnitStats_TriggeredAbility_Level` (Passive == Triggered dans
ce jeu). Un recenseur qui apparie par le NOM se trompe dès que le natif abrège ou renomme — même
vice que « la VOIE ne dit pas l'enum » (#270-c), transposé du côté des CHAMPS.

### 5b. `observeBattle` — le canal de comparaison ACTUEL du projet (13 champs/unité)

**Sans aucun porteur : `visualId`, `squadId`, `rank`.**

Le plus lourd est `visualId` : **le flux ne nomme jamais l'unité**. `Action=AddUnit` porte
`Unit_Owner_Id`, `Unit_Parent_Id`, `Unit_Foot_Tile_Id_1`, `Unit_IsSummoned`, `Unit_SpawnSource` —
et **rien qui l'identifie**. L'identité ne se reconstitue qu'**indirectement**, par la signature du
kit émise juste après (`UnitStats_ActiveAbility_Id`, `UnitStats_TriggeredAbility_Id` — pour
`thousTzaangor` : `1100`, `69`, `1174`, `1180`, `1161`).

⇒ **Conséquence directe pour le comparateur** : l'appariement des entités entre deux flux repose
sur l'**ordre d'apparition** ou sur cette signature de kit, jamais sur un identifiant. Tant que le
flux est bit-identique (§ 4), l'ordre suffit ; dès qu'on comparera un flux natif à un flux
**émis par le port Python**, il faudra choisir explicitement une clé d'appariement.

Les dix autres champs ont un porteur : `hp` → `UnitStats_RemainingHealth`, `armorMax` →
`UnitStats_MaxArmor`, `col`/`row` → `Unit_Foot_Tile_Id_1..7` **résolus par les `Tile_Column` /
`Tile_Row` des `AddTile`** (le flux donne un id de tuile, pas des coordonnées), `isDead` →
`Unit_IsDying` + `Action=RemoveUnit`, etc. La table complète est dans le probe
(`OBSERVE_FIELD_CARRIER`) et dans le fichier de couverture.

**Cliquet** : le probe **rougit** si un champ d'`observeBattle` ou un membre de `StatType`
n'apparaît pas dans sa table d'appariement. Un champ neuf force donc une décision au lieu de
glisser en silence dans le lot « comparé ».

### 5c. Ce que le flux ne porte structurellement pas

- **Le tirage PRNG brut.** Le flux dit *« a crité : non »*, *« a bloqué : non »* et le dégât final ;
  jamais le nombre tiré ni le seuil. Cette information vit dans l'autre canal (§ 6).
- **Le découpage attribue au seul joueur enregistré** (§ 7).

## 6. Le canal PRNG

`IdunBattleLogic.Replay.Replay$$GetWholeBattleRngEvents` → `List<IdunBattle.Utils.PRNG.RngEvent>`,
comparé par `Runner.RngEventComparer$$DoRngEventsDiffer`.

**Disposition mesurée en live** (RPC `classFields`, offsets BOXÉS ; `RngEvent` est un
`System.ValueType` de taille publiée 48 ⇒ **stride déboxé 32**) :

| champ | offset | type |
|---|---:|---|
| `Event` | 16 | `String` |
| `Output` | 24 | `String` |
| `StackTrace` | 32 | `String` |
| `Index` | 40 | `Int32` |

Un événement porte donc **la pile d'appel du tirage** — nettement plus qu'un compteur.
`Runner.RngEventComparer$$TryParseEventInputFloat(input, out Decimal)` confirme que `Event` porte
une entrée numérique.

**Mesuré** : le compte est **stable d'un rejeu à l'autre** (5 / 5 sur C1_70 ; 61 / 61 sur MC1_67)
et **discrimine** un changement de seed (61 → 76). **Le CONTENU n'est pas lisible** par le RPC
actuel, qui ne rend que `_size`.

Le lecteur est **écrit et livré** (`replayRngEvents`, § 8) mais **NON CONFRONTÉ** — il vit dans
`frida/hooks/`, donc il attend une fenêtre de reinject.

## 7. Le découpage en pas — l'affirmation offline, CONFRONTÉE

`case-477` § 10.6 affirmait, sur lecture seule de `ReplayRecorder$$Listen` : *« le contenu
couvrirait toute la bataille, mais le découpage en pas suivrait le seul joueur 11 »*.

**Mesuré, sur les deux boards** — tours joués un par un, delta de `stepCount` et delta de longueur
à chaque tour, joueur attribué par `Match_PreviousPlayerId` traduit par la table
entité → `PlayerId` :

| board | tour | joueur | Δ caractères | Δ pas |
|---|---:|---:|---:|---:|
| C1_70 | 1 | **11** | 828 | **+1** |
| C1_70 | 2 | **12** | **2 002** | **0** |
| MC1_67 | 1 | **11** | 11 113 | **+1** |
| MC1_67 | 2 | **12** | **16 084** | **0** |
| MC1_67 | 3 | **11** | 24 249 | **+1** |
| MC1_67 | 4 | **12** | **4 767** | **0** |

⇒ **AFFIRMATION CONFIRMÉE.** Les tours du joueur 12 produisent des milliers de caractères de flux
(donc le **contenu** les couvre intégralement) et **aucun pas** (donc le **découpage** les ignore).

**Ce que ça coûte à un comparateur** : rien sur le contenu, tout sur la **granularité**. On ne peut
pas dire « le pas *n* diverge » pour une action de l'adversaire — sa sortie est versée dans le pas
du joueur enregistré qui l'entoure. Un diff **par pas** est donc plus grossier d'un côté du
plateau ; un diff **sur le flux entier** ne perd rien.

## 8. Livré ici, NON CONFRONTÉ — `replaySteps` / `replayRngEvents`

`frida/hooks/features/replay-output-stream.ts`, aucun `Interceptor` posé :

- **`replaySteps({ runnerId })`** — un `ReplayStep` par ligne : `Index`, `Turn`,
  **`InputMessage` NOMMÉ** (ns + classe), `outputStreamLength`, `rngEventCount`. Rend aussi
  `Replay.RecordedPlayerIds` — **la liste que `SetupReplayRecorder` a calculée**, au lieu de la
  déduire du seed BC. Le § 7 a dû passer par des deltas de `stepCount` faute de cet accesseur ;
  avec lui, la mesure est directe et **nomme le message**.
- **`replayRngEvents({ runnerId, includeStackTrace })`** — le contenu du § 6.

**Le stride n'est pas supposé** : il vient de `il2cpp_class_get_element_class` +
`il2cpp_class_get_instance_size` moins le header ; si l'un des deux manque, la lecture est
**REFUSÉE avec une erreur nommée** plutôt que de rendre du garbage plausible (piège de la taille
boxée, `reference_symbol_table_versioned`).

Vérifié : `npx tsc -p tsconfig.hooks.json --noEmit` → 146 erreurs, **toutes préexistantes** (142
dans `hooks/scratch/` gitignoré, 4 dans `debug-rpcs.ts` / `tensorizer.ts`), **aucune** sur ce
fichier ; `npm run build:hooks` → exit 0, bundle 1 145 132 o, les deux symboles présents.

## 9. Verdict : le comparateur est CONSTRUCTIBLE — et sur quel périmètre

**OUI**, et la barre est plus basse qu'anticipé : pas besoin de forme canonique, l'**égalité brute**
tient (§ 4). Périmètre à **dériver des trois enums**, jamais de l'observé (§ 2), et **publier** les
non-comparés (§ 5).

**Ce qui reste à faire, et qui n'est PAS un diff** : le port Python devrait **ÉMETTRE** un flux de
cette grammaire pour être comparé. Ce n'est pas une tranche d'outillage, c'est un portage du
`StreamCache` / `StreamDispatcher` — le projet a déjà matérialisé cet arbre (mig 014), donc la
question à trancher est **combien de la couche de stream est déjà portée**, pas s'il faut la porter.

**Ce que le comparateur ne pourra pas trancher, quoi qu'on fasse** : `visualId` / `squadId` /
`rank`, `Defense` / `EvasionChance`, la valeur courante des sept stats `Extra*`, et le tirage PRNG
brut hors du canal du § 6.

## Résidus

- **#477-r12** — **CONFRONTER `replaySteps` / `replayRngEvents`** (§ 8), livrés et jamais exécutés.
  C'est ce qui donnerait le **contenu** des événements PRNG (`Event` / `Output` / `StackTrace`),
  aujourd'hui réduit à un compte, et la découpe en pas **nommée par son message** au lieu d'un
  delta. **Condition de retournement exécutable**, après la fenêtre de reinject :
  `python scripts/python/probe_477r11_replay_stream_format.py --session <sid> --board MC1_67`
  puis, sur le runner armé, les deux RPC neufs — le résidu tombe si `replaySteps` rend un
  `messageCls` non nul par pas et `recordedPlayerIds == [11]`.
- **#477-r13** — **La couverture observée est un PLANCHER** : 16 / 104 `GroupType`, 21 / 62
  `StepType`, 83 / 244 `TagKey` sur deux batailles. Rien ne dit que les 88 types de groupe non vus
  respectent la même grammaire — en particulier `Ability_AtomicGroup`, `DamageChain`,
  `System_UnitDrafting`, `TerritoryCapture`, et les ~50 groupes nommés par ability
  (`PlagueWind_Attack1`, `Drachnyen_AtomicGroup`, …). **Condition de retournement exécutable** :
  balayer des scénarios ciblés (`--equip-relic`, MoW, summons, abilities à variable pour atteindre
  `AbilityVariableAmount`) et faire remonter la couverture ; le résidu tombe quand l'étape 1 du
  probe reste à **0 ligne hors des 4 formes** sur un corpus qui touche ces groupes.

## Ce que je n'ai PAS fait

- **Aucun comparateur construit** — la tranche décidait s'il l'est ; il l'est.
- **`Replay.Interactions`** (@88) et **`ReplayStep.SimulationRequestMessages`** (@64) : deux
  collections vues à la mesure de disposition, jamais lues. Elles ne sont dans aucun des deux
  canaux du validateur natif.
- **`Runner.ReplayValidator$$RunReplayWithParameters` sur nos runners** — c'est #477-r4, intact.
