# case-270 — `ActiveAbilityType` : 75 ids morts, 0 réattribué, et le sens de la dérive qui coûte

Fiche `[harness] #254b-c`. Question posée **membre par membre** : *la citation du port désigne-t-elle
une mécanique encore atteignable en bataille sur `rnca9r7q6c` ?*

Re-dérivation : `python scripts/python/probe_270_active_ability_type_drift.py` (état courant) et
`--rev <sha d'avant #270>` (rejoue l'inventaire historique). **Ne pas citer les chiffres ci-dessous
sans les re-dériver** : ils se périment au prochain build.

## 0. La prémisse de la fiche est fausse sur un point, et ça change la conclusion

La fiche disait « le build `rnca9r7q6c` **retire** 75 ids ». **Mesure : il n'a rien retiré.** Ces
75 ids sont absents **des DEUX** dumps versionnés — `gqfc5mff6c` (généré le 2026-07-27, donc bien
après ce build) comme `rnca9r7q6c`. Ils viennent d'une source qui n'existe plus : le port a été
généré le 2026-07-13 depuis `data/il2cpp_enums.tsv`, table Il2CppDumper **supprimée le 2026-07-25**
(`8e591496`, « suppression du legacy »).

Conséquence pratique : ce n'est pas une régression de migration à rattraper au coup par coup, c'est
un **héritage** — et son pendant côté hooks avait déjà été traité par **#256** (`142781a1`,
« 255 ids morts retirés »), qui a régénéré `frida/hooks/data/ability-names.ts` (323 → 260 entrées).
Le présent dossier est la moitié Python/SQL du même ménage.

## 1. Les quatre artefacts, et pourquoi leur réparateur était en panne

| Artefact | Rôle | Portait | Le jeu porte |
|---|---|---|---|
| `scripts/python/engine/entities/active_ability_type.py` | mirror `IntEnum` | 332 | 260 |
| `scripts/python/enum_maps.py` `ACTIVE_ABILITY_TYPE` | id↔nom, **lu par le moteur** | 331 | 260 |
| `scripts/sql/006_ref_tables.sql` `ref_active_ability` | **cible de FK** de `stream_event` | 323 | 260 |
| `scripts/sql/013_enum_fk_and_names.sql` | backfill `active_ability_type_name` | 330 | 260 |

Les deux générateurs — `rl_gen_ref_tables.py` et `rl_gen_enum_columns.py` — lisent
`data/dumps/<hash>/dump.cs`, **le même artefact Il2CppDumper supprimé le 2026-07-25**. Ils lèvent
`SystemExit("dump.cs absent … re-dump requis")` avant d'écrire quoi que ce soit. La dérive n'avait
donc plus de réparateur : c'est la cause racine, pas le symptôme.

## 2. Verdict, membre par membre : **75/75 = code mort**, corroboré par quatre sources

Aucune des 75 n'est vue vivante par une source indépendante du dump d'enums :

| Source | Indépendante de… | Résultat sur les 75 |
|---|---|---|
| `data/symbols/rnca9r7q6c/frida/enums.tsv` | — (la mesure d'entrée) | 0 présent |
| RPC **`dumpEnum` au RUNTIME** (session 25, build courant) | le fichier versionné | 0 présent — **261 noms / 260 valeurs, 0 divergence avec le TSV** |
| `frida/classes.tsv` : existe-t-il une classe `<Nom>Ability` ? | le dump d'enums | **0 / 75** (les 10 ids bas SURVIVANTS, eux, en ont **10 / 10**) |
| `gameconfig.json` `units.abilities` (572 entrées, données serveur) | le binaire entier | **0 / 75** |

Le contraste avec les survivants est le contrôle qui rend la mesure concluante : les onze ids
inférieurs à 1000 que le build garde (`0 None`, `3 ChainLightning`, `4 Taunt`, `8 MassHeal`,
`9 HolyBolt`, `12 NobleCharge`, `13 Test`, `17 NormalAttack`, `18 Heal`, `28 Repair`,
`69 Loki_NormalAttack`) ont **tous** leur classe `<Nom>Ability`. La disparition n'est donc pas un
artefact de la chaîne de dump — le jeu a bien élagué son héritage Idun (Legend of Solgard :
`ForHonor`, `DragonCryRed`, `HatchTadpoles`, `BattleTinkererRepair`…).

⚠ Piège de sous-chaîne écarté : quatre noms morts « matchent » une classe par suffixe
(`RadBombardment**Ability**`, `HolyDuel**Ability**`, `EnhancementLifeSteal**Ability**`,
`Loki_NormalBossAttack**Ability**`). La sonde borne à gauche par un non-mot ; sans ça, on aurait
conclu à tort que 4 des 75 survivaient.

## 3. Le résultat le plus utile : **0 réattribution** sur cet enum — mais 66 ailleurs

La fiche demandait de chercher les collisions de valeur (« l'id a changé sous la citation »).

- `ActiveAbilityType`, port vs build courant : **0 id renuméroté**. La seule différence de nom sur
  une valeur partagée est `0 : None_` (échappement du mot-clef Python) — pas une divergence.
- `ActiveAbilityType`, `gqfc5mff6c` vs `rnca9r7q6c` : **0 renuméroté** (confirme #254 §1).
- Aucun des 75 noms morts n'est réutilisé à une AUTRE valeur d'`ActiveAbilityType`.

**En revanche l'inventaire par NOM a fait tomber une réattribution réelle, dans un autre enum.**
`enum_maps.GROUP_TYPE` (lu par `rl_collect_batch._group_name`, migration 014) porte **66 ids dont
le nom est FAUX** : un membre `Ability_Displace` a été **inséré en 36** dans
`IdunBattle.Streams.GroupType`, décalant tout ce qui suit de +1.

```
36 : le dépôt dit 'Ability_Buff'   le jeu dit ['Ability_Displace']
37 : le dépôt dit 'Ability_Stance' le jeu dit ['Ability_Buff']
...  (66 entrées, jusqu'à la fin de l'enum)
```

`frida/public/src/battle-log.js` porte la **même** liste décalée (tableau indexé, même rupture à
l'index 36). Ce n'est **pas** la migration `rnca9r7q6c` : `GroupType` est identique entre les deux
builds versionnés (104 membres, 0 renuméroté) — la table du dépôt dérive d'un dump **antérieur à
`gqfc5mff6c`**. Hors sujet de cette fiche ; **porté au backlog**, avec ses deux consommateurs.

Trois autres blocs de `enum_maps.py` dérivent aussi (mesure, à re-dériver) :
`EFFECT_TYPE` 682 → 629 (dont **2 faux** : 1563/1564 `DA_Hero6_Passive_*` → `SpecialIssueCombiMelta_*`),
`PASSIVE_ABILITY_TYPE` 574 → 476 (107 morts, 9 manquants), `DAMAGE_PROFILE_TYPE` 1 manquant.
`UNIT_SPAWN_SOURCE` est **sain** (9/9).

## 4. Le sens de la dérive qui coûte : ce n'est PAS les 75

Les 75 ids morts sont **inertes** : le jeu ne les émet jamais, et aucun nom du gameconfig ne leur
correspond — ni `_resolve_ability` (id→nom) ni le reverse (nom→id) ne peuvent les atteindre.

Le **manque**, lui, dégrade en silence. `engine/ai/state_bridge.py:97` le dit noir sur blanc :
« une active dont le nom n'est pas dans l'enum est **ignorée** ». Quatre abilities du build courant
manquaient à `enum_maps.ACTIVE_ABILITY_TYPE`, donc **disparaissaient de la liste d'abilities offline
de leur porteur** — quatre HÉROS, tous confrontables :

| id | ability | porteur (`lineup`) | config gameconfig |
|---|---|---|---|
| 1222 | `MassDriverAccelerator` | `votanChampion` | présente |
| 1227 | `HeavyWarpFlamer` | `thousSekhetar` | présente |
| 1231 | `TitanhammerSquad` | `astarLysander` | présente |
| 1232 | `EmpyricAmbush` | `eldarLhykhis` | présente |

**Preuve directe de l'invisibilité**, mesurée en rejouant `audit_kit_coverage.py` (qui fait
`{v: k for k, v in EM.ACTIVE_ABILITY_TYPE.items()}`) : les quatre abilities n'apparaissaient
**nulle part** dans `docs/rl/kit-coverage.md` avant le correctif, et y entrent après —

```
+| votanChampion  | 2 | MassDriverAccelerator(1222) [--] NO-OP DAMAGE(DirectDamage) | ...
+| thousSekhetar  | 2 | HeavyWarpFlamer(1227)        [-D] NO-OP DAMAGE(Flame)       | ...
+| astarLysander  | 2 | TitanhammerSquad(1231)       [--] NO-OP HEAL                | ...
+| eldarLhykhis   | 2 | EmpyricAmbush(1232)          [--] NO-OP DAMAGE(Eviscerate)  | ...
```

L'audit de couverture ne comptait donc pas quatre trous qu'il aurait dû compter. Le fichier
régénéré n'est **pas** inclus dans cette PR : il lit le gameconfig VIVANT et son diff mélange une
grosse dérive sans rapport (nouveaux passifs du build, ex. `necroOverlord`/`MyWillBeDoneOverlord`).
Sa régénération est un geste à part — `python scripts/python/audit_kit_coverage.py`.

Côté base c'est pire que silencieux : `ref_active_ability` est la **cible de deux FK** de
`stream_event` (`se_active_ability_id_fkey`, `se_effect_source_active_ability_fkey`) et il manquait
**douze** ids du build courant — 1215, 1216, 1217, 1220, 1222, 1223, 1224, 1227, 1228, 1230, 1231,
1232. Une ligne portant l'un d'eux fait **échouer l'insert**.

Et `013` portait une citation **franchement fausse** : `1228 : 'DA_Hero6_Active'` là où le jeu dit
`SternguardFocus`. Le mirror et `enum_maps` avaient été corrigés à la main en #219 (`38e95dbb`,
depuis le RPC live) ; la correction n'était jamais descendue jusqu'au SQL.

## 5. Inventaire des citations — les trois piles

336 occurrences des 75 noms dans les fichiers suivis, dont **308 dans les 4 artefacts générés**
(4 × 75 + les homonymes de `enum_maps`). Restent **28 occurrences hors tables**, ventilées ainsi :

### Pile A — code mort à retirer (traitée dans cette PR)

| Site | Ce que la citation prétendait | Verdict |
|---|---|---|
| les 4 artefacts × 75 ids | membres d'`ActiveAbilityType` | régénérés → 260 chacun |
| `engine/ai/state_bridge.py:283` `REPAIR_ABILITY_IDS = {28, 82, 84, 1119}` | 82 `MechRepair`, 84 `BattleTinkererRepair` | ids morts retirés ; 28/1119 restent |
| `engine/runner/operations/heal.py:5-6` (docstring) | exemples `MechRepair` / `BattleTinkererRepair` | remplacés par `Repair` (28) / `Repair_GalvanicField` (1119) |
| `docs/rl/ai-step-toolkit.md:164` | « `ShadeAttack_Attack=68` » comme exemple d'attaque normale concrète | 68 mort → `TemplarInitiateNormalAttack=1046`, `RogalDorn_NormalAttack=1126` |
| `docs/rl/ai-step-toolkit.md:254` | symbole `BattleTinkererRepair.FindHighestAttackEnemyWithTarget` | **0 occurrence** dans `classes.tsv`/`methods.tsv` des DEUX builds → remplacé par `Common.RepairPlaybook` / `Loki.NanoscarabRepairProtocolsPlaybook`, avec la mention du retrait |

### Pile B — citation devenue fausse (traitée)

| Site | Prétend | Le jeu dit |
|---|---|---|
| `scripts/sql/013_…:1228` | `DA_Hero6_Active` | `SternguardFocus` |
| `docs/rl/case-32-casttile.md:25` et `case-36-…:184` | tag L3 `ability:"ForHonor"` | l'id **1** n'est pas un `ActiveAbilityType` ; le libellé venait d'`ability-names.ts` qui portait alors `1: "ForHonor"` (régénéré en #256). Les deux docs sont ANNOTÉES, pas réécrites — ce sont des relevés de mesure datés. |

### Pile C — homonyme d'un AUTRE enum : la citation est JUSTE, ne rien toucher

Huit des 75 noms vivent dans un autre enum du build. Toute régénération naïve « par nom » les
casserait. Vérifié un par un :

| Nom | Mort dans `ActiveAbilityType` | Vivant dans | Citation concernée | Verdict |
|---|---|---|---|---|
| `DanceOfDaggers` | 41 | `IdunBattle.Configuration.UtilityType` **49** | `engine/utilities/utility_type.py:89`, `ai-utility-trace.ts:493`, clé de poids de `data/seed-bc.json` | **juste** |
| `SummonIceElemental` | 20 | `IdunBattle.Configuration.UtilityConfigCollectionType` **1** | `ai-utility-trace.ts:520` | **juste** |
| `OceanWave` | 54 | `IdunBattle.Entities.Enum.SpawnSource` **6** | `enum_maps.UNIT_SPAWN_SOURCE` | **juste** |
| `DarkDragon` | 67 | `IdunBattle.Streams.GroupType` **30** | `battle-log.js:52` | **juste** (30 est avant la rupture du §3) |
| `AirshipStrike_Attack` | 80 | `GroupType` **54** | `enum_maps.GROUP_TYPE` dit 52 | **fausse — via GROUP_TYPE, cf. §3** |
| `RocketBarrage` | 81 | `GroupType` **57** | `enum_maps.GROUP_TYPE` dit 55 | **fausse — via GROUP_TYPE, cf. §3** |
| `MechRepair` | 82 | `GroupType` **56** | `state_bridge.py:283` / `heal.py:5` — contexte **ability**, donc bien l'enum mort | traité pile A |
| `LifeSteal` | 16 | `…LiveEvents.Modules.MachineOfWarEventEnhancementType` **2** | aucune | — |

Les 7 occurrences `data/i2_en.json` (`Bombardment`, `Duel`) sont des **mots anglais** de
localisation (`Orbital Bombardment`, `Holy Duel`) — aucun rapport. Idem
`docs/rl/case-220/p0-effect-walk.md:17` « `AddBondEffect(0x443 Duel…)` » : `0x443` = 1091 =
`EffectType.HolyDuel_Taunt`, citation correcte d'un AUTRE enum.

## 6. Ce qui a été livré, et ce qui ne l'est pas

Livré :

- `scripts/python/regen_active_ability_tables.py` — le réparateur qui manquait. Même discipline
  que `regen_hook_name_tables.py` (#256) : source = `data/symbols/<CURRENT>/frida/enums.tsv`, on ne
  réécrit **que le bloc** visé, on **garde le nom déjà choisi** quand une valeur en porte plusieurs
  (`9999` reste `testAssetBundles`, comme avant), `--ecrire` sinon simulation ;
- `scripts/python/probe_270_active_ability_type_drift.py` — la garde + l'instrument d'inventaire
  (`--rev`, `--live`, `--citations`) ;
- les 4 artefacts régénérés, les 5 citations hors tables corrigées, 2 docs annotées.

**PAS** livré, et volontairement :

- les autres blocs de `enum_maps.py` / `006` / `013` (`GROUP_TYPE` **66 faux**, `EFFECT_TYPE`,
  `PASSIVE_ABILITY_TYPE` 107 morts + 9 manquants, `ref_triggered_ability`, `ref_effect`) →
  **backlog** : chacun demande sa propre lecture, et `GROUP_TYPE` est une réattribution, donc un
  changement de comportement d'ingestion ;
- la réparation des deux générateurs historiques (`rl_gen_ref_tables.py`,
  `rl_gen_enum_columns.py`), toujours arrimés à `dump.cs` disparu → **backlog** ;
- `frida/public/src/battle-log.js` (même décalage `GroupType`) : front, et toute correction sous
  `frida/hooks|public` demanderait un rebuild ;
- `scripts/python/engine/entities/triggered_ability_type.py` (107 ids morts, même patron) : hors
  sujet de cette fiche, une tâche à part.

## 7. Validation — la contre-épreuve, pas le smoke

`probe_270_carriers_live.py` **monte les porteurs en bataille** (`catalog_inject` → `rl_duel build
--seed-bc`, board `MC1_67`, seed 777) et mesure **trois** choses par ability, dont une
contre-épreuve qui interdit la conclusion tautologique :

| id | ability | porteur | **A** le natif la porte | **B** le port la voit (table corrigée) | **C** le port la voit SANS l'entrée |
|---|---|---|---|---|---|
| 1222 | `MassDriverAccelerator` | `votanChampion` | oui | oui | **non** |
| 1227 | `HeavyWarpFlamer` | `thousSekhetar` | oui | oui | **non** |
| 1232 | `EmpyricAmbush` | `eldarLhykhis` | oui | oui | **non** |
| 1231 | `TitanhammerSquad` | `astarLysander` | *non couvert — voir ci-dessous* | | |

`C = non` est le point : en retirant l'entrée de `ACTIVE_ABILITY_TYPE` en mémoire, l'ability
**disparaît** de la liste offline. Le correctif est donc **portant**, et non une mesure qui aurait
été vraie de toute façon.

Autres rejeux, tous verts :

| Contrôle | Avant | Après |
|---|---|---|
| `probe_270_active_ability_type_drift.py` | exit **1** (4 artefacts en dérive) | exit **0** |
| `probe_270_…  --live` (`dumpEnum`, session 25) | — | 260 valeurs, **0 divergence** avec le TSV |
| `probe_252_hook_name_tables.py` (tables hooks) | 0 | **0** — les 5 tables collent toujours |
| `probe_181_targeting_gaps.py` | 0 manquante | **0 manquante** (94/94) |
| `tests/engine/runner/test_targeting_options_sources.py` | 4 passed | **4 passed** |
| `tests/engine/test_heal_type_gate_decision_live.py` (consomme `build_from_state`, donc la classification heal/repair modifiée) | 28 passed | **28 passed** |

### Ce qui n'est PAS couvert

- **`astarLysander` / 1231 `TitanhammerSquad`** : le porteur **ne se déploie pas** —
  `initAndStart: system error`. Établi par **bissection unité par unité** (les trois autres montent
  SEULS, celui-ci échoue SEUL), donc ce n'est ni le roster ni l'injection. Famille **#254** : son
  passif `IconOfObstinacy` a `constants: null` au gameconfig, et un `GetStringConstant` à la
  construction du trigger lèverait. **Non tranché** — déclaré dans `BLOQUES` de la sonde plutôt que
  masqué en vert, et porté au backlog. Les trois autres porteurs couvrent trois factions
  différentes ; la mécanique testée est la même table pour les quatre.
- **Rien n'a été appliqué en base** (`--apply` non lancé, PostgreSQL hors périmètre agent). Les
  migrations 006/013 sont idempotentes (`ON CONFLICT … DO UPDATE`, `UPDATE … FROM (VALUES …)`) :
  retirer une ligne du fichier **ne supprime rien** en base, ça cesse seulement de la réinsérer. Les
  12 ids ajoutés à `ref_active_ability` ne prendront effet qu'au prochain passage de la migration —
  **c'est le geste qui referme le risque de FK**, et il reste à faire.
- **Le nom retenu pour `9999`** diffère d'un artefact à l'autre (`testAssetBundles` au mirror / dans
  `enum_maps` / dans `013`, `STRIPPED` dans `006`). C'est la **règle 2** qui joue — on garde le nom
  déjà choisi tant qu'il appartient à l'ensemble de la valeur — et les deux noms sont des membres
  réels de cette valeur. Diff minimal contre uniformité : #256 a tranché pareil.
- **Les autres blocs** de `enum_maps` / `006` / `013`, et `triggered_ability_type.py` : cf. §6 et
  #270-a/b/c.
