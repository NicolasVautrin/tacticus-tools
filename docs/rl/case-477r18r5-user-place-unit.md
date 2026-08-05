# #477-r18-r5 — `User_PlaceUnit`, première tranche du DÉROULÉ

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp, session Frida **10**.

```powershell
python scripts/python/probe_477r18r5_user_place_unit.py            # live, 2 boards
python -m pytest scripts/python/tests/engine/test_477r18r5_place_unit_offline.py -q
```

## 1. La RE — l'enveloppe, lue par ADRESSE

`IdunBattle.Messages.InputMessageProcessor$$Visit(message:IdunBattle.Messages.AddUnitMessage)`
(le message ne s'appelle **pas** `PlaceUnitMessage`) assemble un `<>c__DisplayClass9_0` puis
appelle la fonction locale
`InputMessageProcessor.u003Cu003Ec__DisplayClass9_0$$u003CVisitu003Eg__AddUnit|0`, qui émet
**exactement trois choses** :

```
Events.StartGroup(GroupType.User_PlaceUnit /*0xd*/, 0 /*NO_ENTITY*/, String.Empty, default(BEntityId?));
processor.AddUnit(unitId, unitFeetTileIds, playerId, spawnSource, options);   // slot 5 d'IOperationProcessor
Events.FinishGroup();
```

L'appel du milieu est `Core.Services.OperationProcessor$$AddUnit` →
`IdunBattle.Operations.AddUnitOperation$$Execute`, c'est-à-dire le `Group=AddUnit` que
`engine/streams/game_setup.py` émet **déjà**. Le port n'ajoute donc que l'enveloppe :
`engine/streams/input_messages.py`, 1 fonction.

Trois points **lus**, pas déduits :

- **`sourceId` = `String.Empty`**, pas un slot de littéral : le décompilé lit le premier champ
  statique de `System.String` (même motif que `System.Security.NamedPermissionSet$$set_Name`,
  qui compare à `String.Empty` via `System.String$$op_Equality`).
- **`entityId` = `NO_ENTITY`** est **structurel** : le groupe s'ouvre avant que l'unité existe.
- **`spawnSource` est un CHAMP DU MESSAGE** (`AddUnitMessage+0x28`), pas une constante — le
  natif le passe tel quel. Le `5` (`SpawnSource.Deployment`) vient de **notre montage** :
  `frida/hooks/features/launch.ts` fait `msg.add(0x28).writeS32(5)` après le ctor à 4 arguments.

⚠ **Le nom `Visit` ne se décompile pas** (37 surcharges → corps vide, sans erreur : piège 1 de
#477-r18). Chaque surcharge est identifiée par le **type de son paramètre**, lu dans
`data/symbols/<build>/frida/methods.tsv`, et interrogée par **adresse**.

⚠ **`RunPhase` n'est pas un `GroupType`.** `Visit` appelle `RunPhase(this, 4, …)` quand
`AddUnitMessage+0x40` est vrai ; le `4` est un `IdunBattle.Core.PhaseType` (signature lue), pas
`GroupType.System_StartMatch`. Les **deux** branches appellent la même fonction locale.

## 2. Le résultat, mesuré

| scénario | groupes | égalité | delta vocabulaire |
|---|---:|---|---|
| C1_02, 3 héros | 3 | **146 / 146** | +1 / +0 / +0 |
| MC1_67, 3 héros | 3 | **146 / 146** | +1 / +0 / +0 |
| C1_02, 2 héros + MoW | 2 | **96 / 96** | +1 / +0 / +0 |
| MC1_67, 5 héros vs 3 | 5 | 283 / 286 **+3 au CANAL** | +1 / +0 / +0 |

Le critère écrit avant la tranche (`case-477r18` § 6) est tenu : `GroupType` **2 → 3**,
`StepType` **6 → 6**, `TagKey` **36 → 36** — le delta est dérivé du **même flux natif**, pas du
port. Les **6** mutations de contre-épreuve rougissent, chacune après avoir **mordu**.

**L'ordre n'est pas copié** : il est **dérivé** de l'allocation ECS croissante (#477-r16) — donc
l'ordre chronologique des `AddUnit` **est** l'ordre croissant des ids — puis **recoupé** contre
le flux. 4 scénarios, 13 groupes, 13/13.

## 3. Ce que le 4ᵉ scénario a trouvé — et pourquoi ce n'est pas le port

Sur `MC1_67` avec 5 héros (dont `ultraCalgar`), **3 divergences de VALEUR**. Les canaux du port
(`combatSnapshot`) lisent l'état **après le build**, donc après les auras de `System_StartMatch`,
alors que les tags sont écrits **au placement**. Les trois s'expliquent **au chiffre près** par
une modification publiée ensuite :

```
entite 85 : Attack   1507 -> 2805   UnitStats_Attack_Modification:1298
entite 87 : Attack   2512 -> 3410   UnitStats_Attack_Modification:898
entite 87 : Movement    3 ->    4   UnitStats_Movement_Modification:1
```

Le probe **attribue** désormais ce cas au CANAL au lieu de laisser le lecteur le faire — mais
**seulement à l'égalité exacte** : même entité, même stat, `port - natif == modification`. Deux
tests offline interdisent qu'il absolve autre chose (écart ≠ modification, autre entité, autre
stat, aucune modification, et le cas qui compte : un port faux de `+1` dans un flux où la
modification vaut 1298). Verdict rendu : `conforme /CANAL`, avec le compte des lignes qui ne sont
**pas** des égalités.

## 4. Ce qui n'est PAS couvert

- **`Unit_SpawnSource` hors du montage** — le natif le lit du message ; une partie réelle peut y
  mettre autre chose. Ce que le port garantit (test offline) : la valeur émise **suit**
  `UnitSetup.source`, jamais une constante en dur.
- **Un `User_PlaceUnit` contenant autre chose qu'un `AddUnit`** — **borné, pas éliminé** : la
  fonction locale n'émet que les trois choses ci-dessus, et le scénario MoW mesure que la Machine
  of War du joueur passe par `Group=AddMachine` **dans `System_GameSetup`**, pas ici. Le probe
  imprime le **contenu** trouvé sous l'enveloppe à chaque run.
- **Les régimes de `Group=AddUnit` que le montage n'atteint pas** : `Unit_Foot_Tile_Id_2..7`
  (le ctor à 4 arguments ne porte qu'une coordonnée), `Unit_IsSummoned` / `Unit_Parent_Id` non
  nuls, `UnitStats_IsBoss:1`, et `MaxMembers != InitAliveMembers` (les 5 unités multi-membres du
  seed sont npc/summon, hors pool — même limite que #477-r15-r5). → `#477-r18-r5-r1`.
- **La branche `RunPhase`** de `Visit` : non discriminée live. Les deux branches appellent la
  même fonction locale (**lu**), donc l'enveloppe est identique — mais `RunPhase` ajoute ensuite
  `VerifyDeaths` / `ProcessDamageEvents` / `ProcessPendingTriggeredAbilities`, qui produisent
  leurs **propres** groupes racines. → `#477-r18-r5-r1`.
- `AmmoCost` / `EnoughAmmo` : borne (c) héritée de #477-r15 (aucune unité régulière ne les
  porte).

## 5. Deux notes d'outillage

- **`engine/streams/__init__.py` ne réexporte PAS `input_messages`** (ni `game_setup`) : les
  deux tirent `engine.services.machine_of_war_position`. Mesuré — avec le réexport,
  `import engine.streams` passe de **99 à 104** modules `engine.*` (11 → 12 `engine.services`) ;
  sans lui, **99 / 11**, identique à `origin/master`. Le paquet reste le **writer** seul.
- **Un échec de build dit sa cause.** `rl_duel` termine sa sortie par le rapport de re-synthèse
  du seed BC : une queue brute de 600 caractères noie la ligne `[error]`. Mesuré — « hors pool »
  est ressorti en `...PsykerLikesToBeAdjacent']`. Le probe extrait désormais les lignes `[error]`
  / `pool =` / `Traceback`.

## Résidus

- **#477-r18-r5-r1** — **les régimes de `Group=AddUnit` que le montage `rl_duel build` n'atteint
  pas**, et la branche `RunPhase` non discriminée (cf. § 4). Condition de retournement : un
  montage qui pose une unité multi-tuiles ou multi-membres par `AddUnitMessage`, et un flux où
  `AddUnitMessage+0x40` est vrai — puis vérifier que l'enveloppe est bien inchangée.
