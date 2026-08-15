# #951-r7 — re-attester les DIX verdicts sur `t6dpr4k06g` : ce que la clause `build` attrape, et ce qu'elle ne voit pas

Le changement de build a périmé les **10** attestations du ledger `#951-r2` d'un coup
(`coverage_attestations.py` → `0 VALIDES / 10 PERIMEES`), rendant `master` rouge sur **4** tests de
`test_951r2_voies_de_couverture_offline.py`.

**Re-attester n'est pas retamponner** : chaque `raison` a été RÉÉCRITE avec ce qui a été relu au
décompilé sur le build courant. Une mise à jour du seul champ `build` aurait été exactement la
liste blanche que ce ledger existe pour remplacer.

## 1. Les dix verdicts TIENNENT — mais deux d'entre eux ne se relisaient plus par la voie écrite

| item | verdict | ce qui a été relu sur `t6dpr4k06g` |
|---|---|---|
| `LeadingTheCharge` | RIEN_A_PORTER | `.ctor` = `ComparablePlaybook<T>$$.ctor(this, 0x4b4)` ; `MakeDamagePredictions` prend `StaffOfStarsAbility$$GetDamage(…, isPrediction: 1)` = forme **(a)**, sél. `DSLSelectors.Target`, poids `Nullable` VIDE |
| `LashOfTorment` · `StrikeFromTheShadows` · `EntropyCannons` | RIEN_A_PORTER | forme **(b)** (`VigilanceEternalAbility$$GetDamage` = `MinMaxDamage(…, isPrediction: 0)`) ; le détour de `StrikeFromTheShadowsAbility$$GetTarget` est bien `return *(*(this+0x30)+0x90)+0x60` |
| `ExcruciatingFrequencies` | PORTE_HORS_REGISTRE | sélecteur PROPRE (`…$$GetAttackTargets`, cible TUILE) ; gate = seuil statique, et son écrivain `ComparablePlaybook<T>$$.cctor` relu : `Fix64$$op_Implicit(0xa)` = **Fix64(10)** |
| `DevoutPush` · `MV71SniperDroneSquadAttack` | RIEN_A_PORTER | **un seul** corps chacune, leur `.ctor` = `ALoki_NormalAttackPlaybook<T>$$.ctor(this, 0x41d / 0x434)` |
| `PrecisionShot` | RIEN_A_PORTER | dict `+0x68` de `PlaybookDatabase` → `DefaultActiveAbilityPlaybook` (§2) |
| `GalvanicField` | RIEN_A_PORTER | `AddFlag(0x18) & RemoveActiveAbility(0x1c) & AddActiveAbility(0x45f)` ; les DEUX utilités du playbook écrivent `0` dans leur champ de valeur |
| `IndirectFire` | PORTE_HORS_REGISTRE | **0** symbole dans `ghidra/functions.tsv` ET **0** classe dans `frida/classes.tsv` ; les deux consommateurs impératifs relus (`TargetingQuery$$GetTilesObscuringTerrain` teste `HasTrait(caster, 0x3ed)` ; `DamageCalculations$$CalculateTrenchReduction` le teste aussi, sous `IsTrench` / `IsNeighbourOf`) |

Les ancrages ont été vérifiés **en contenu**, pas seulement en existence : `1204` dans
`_A_VIA_STAFF_OF_STARS_GET_DAMAGE` ; `1196` / `1225` / `1168` / `1197` dans
`_PREDICTION_MINMAX_RANDOM_READ` ; `ABILITY_CLASSES[1119]` = `Repair_GalvanicFieldAbility` ;
`1197` dans `static_threshold_gate.NOT_REGISTERED` ; `INDIRECT_FIRE_TRAIT` = `UnitTrait.IndirectFire`
= `1005 = 0x3ed`.

## 2. La source citée par DEUX attestations n'existe plus pour ce build — et sa note était FAUSSE

`PrecisionShot` et `EntropyCannons` citaient `data/symbols/<build>/metadata/active_playbook_builders.tsv`.
Cette table **n'existe pas** pour `t6dpr4k06g` : aucun générateur versionné ne la régénère (résidu
**#951-r8**). Le fichier de `rnca9r7q6c` écrit en outre un décalage slot→lambda de `+1` ; la mesure
refaite sur ce build rend **`+0`** (calibrée à **218/228** par concordance de noms, contre **0 à 2/228**
pour tout autre décalage). Une citation reprise telle quelle aurait donc été fausse deux fois.

L'appariement a été refait **au binaire** : `PlaybookDatabase$$InitializePlaybookBuilders` est
inaccessible à `decompile_function` (**64 672** octets, **12 566** instructions — timeout puis buffer
dépassé), donc désassemblé hors ligne. Chaque entrée est un bloc
`mov rsi, [rax + <OFF>]` (cache du délégué) / construction du `Func<>` sur le `MethodInfo*` de
`u003Cu003Ec$$u003CInitializePlaybookBuildersu003Eb__31_<M>` / `mov edx, <CLE>` / `Dictionary$$Add` :
le couple (cache, CLÉ) se lit **dans le même bloc**, jamais par rang. Le dict `+0x68` compte **232**
entrées, bornées par `mov [r14 + 0x68/0x88/0x98/0xa8], rdi`.

⚠ **`1015` se prouve SEULE, sans la relation d'offset** : sa lambda `b__31_9` a pour corps
`DefaultActiveAbilityPlaybook$$.ctor(this, 0x3f7, 0)` — la clé est **passée en argument au ctor**.
Deux témoins choisis d'avance sortent comme attendu (`0x454` → `KissOfDeathPlaybook`, `0x12` →
`HealPlaybook`) et `1012` sort sur sa classe PROPRE `PrecisionShot_AimPlaybook` : la mesure
**discrimine**.

## 3. Le contrôle d'EMPREINTE — et pourquoi `h_local` est la seule couche qui périme un verdict

31 symboles de la chaîne relue, confrontés entre les deux builds
(`data/symbols/<build>/fingerprints/functions.tsv`) : **29 identiques sur toutes les couches**,
1 absent des deux tables (`DefaultActiveAbilityPlaybook$$MakeDamagePredictions`, corps générique
non nommé), **1 DIFFÉRENT** — `ALoki_NormalAttackPlaybook<T>$$MakeDamagePredictions`, la BASE dont
dépendent `DevoutPush` et `MV71SniperDroneSquadAttack`.

Sa ventilation tranche : `taille`, `n_ins`, `h_mnem`, `h_imm` **et `h_local` IDENTIQUES** ; seuls
`h_body` et `h_calls` diffèrent. Or `fingerprint_functions.py` écrit que `h_local` est *le verdict*
(le corps PROPRE, références de code anonymisées) et que `h_body`/`h_calls` **propagent d'un niveau**.
Le corps de la base est donc bit-pour-bit le même ; c'est un APPELÉ qui a bougé — la cascade descend
par `ProbableDamageEvent$$.ctor` (même profil : `h_local` identique, `h_body`/`h_calls` différents).
Le slot `0x22` d'`IBattleQuery` que la base invoque est, lui, **inchangé**.

⚠ **Comparer `h_body` sans `h_local` fabrique un faux positif.** La première passe de ce contrôle ne
lisait pas `h_local` et a rendu « la base a changé », ce qui aurait périmé deux verdicts justes.

## 4. Le churn RÉEL entre les deux builds, et où il tombe

| couche | symboles communs différents |
|---|---:|
| `h_local` (le verdict) | **3 175** / 128 605 = **2,47 %** |
| `h_body` (propagé) | 7 807 |
| `h_calls` (propagé) | 5 702 |

Les **2,47 %** recoupent le « ~2,5 % » du CLAUDE.md. ⚠ Mais **2 205 des 3 175** sont des placeholders
`FUN_<addr>`, appariés **par leur adresse** — donc un appariement faux par construction, à ne jamais
compter. Ventilation du reste : 483 runtime/Unity, 220 `Idun.*` (méta), 148 autres, **88
`IdunBattle.View.*`** (visuels), et **31 de LOGIQUE COMBAT** (`IdunBattle.*` hors `View` + `IdunBattleLogic.*`).

**Aucun** des dix playbooks n'y figure. Les 31, en revanche, contiennent un lot cohérent —
`StatComponent$$ApplyModifier` / `$$GetStatPart`, `FillUpStatComponent$$…` (mêmes deux),
`UnitExtensions$$GetStat` / `$$ApplyStatModifier` / `$$GetStatComponent` / `$$GetStatOverride` /
`$$HasStat`, plus `DisplaceUnitOperation$$Execute`, `BattleQuery$$GetTilesInTriangleShape`,
`CubeCoordinate$$NeighbourAt`, `VerifyMatchEndOperation$$HasWon`. Sur presque tous : **même taille,
même `n_ins`, même `h_mnem`, mais `h_imm` différent** — le signal « même squelette, opérandes
changées » que `fingerprint_functions` désigne comme le plus intéressant pour un mirror. Aucun port
n'a été confronté à ce changement : résidu **#482-r7**.

## 5. Le QUATRIÈME rouge n'était PAS la péremption — c'était un TÉMOIN rattrapé

`test_la_peremption_REMET_l_item_au_compte` nommait `GalvanicField` **en dur**. Le 2026-08-15 à
04:10, la PR #1102 l'a inscrit dans `engine.entities.effects.factory.ABILITY_INIT_OWNER_FLAGS`
(valeur `[24]` = le flag `CanRepairFullHealthUnits`) : l'item est devenu PORTE **par une voie**, donc
périmer son attestation ne le décompte plus, et le test rougissait **en accusant le gate** — qui n'y
était pour rien.

**Contre-épreuve** : attestation périmée + la seule entrée `GalvanicField` retirée du registre →
`covered` retombe à `False`. Le gate n'a jamais cessé de fonctionner.

⚠ **Dériver le témoin ne suffisait pas.** `collect()` rend **116 passifs distincts, 116 PORTE, 0 non
couvert** : il n'existe plus aucun passif dont l'attestation soit la seule source, donc un témoin
« non porté » est introuvable et la contre-épreuve serait **VACANTE**. La première version du
correctif l'a montré en rougissant sur sa propre assertion de non-vide — ce qui est le bon
comportement, et la raison de l'écrire.

Le test prend donc **n'importe quel passif visité** (non-vide par construction) et **NEUTRALISE ses
voies** pour la durée du test, en substituant la table que `collect()` demande à
`kit_item_voies.voies_par_item` (forme B — accès attributaire, elle mord). Il mesure alors les **DEUX
SENS** à voies égales : attestation VALIDE → compte ; la MÊME entrée périmée par son seul champ
`build` → décompte. **Contre-épreuve du test lui-même** : sous une mutation qui rend `validite`
toujours `VALIDE` — le gate permissif exact qu'il existe pour attraper — il **rougit**.

## 6. Le rouge jumeau : les quatre conteneurs MUETS de `#1041`

Quatre registres neufs arrivés par nos propres PR. Le tri se fait par une **mesure**, pas par
l'apparence — le discriminant est *« est-ce CE conteneur qui établit le montage ? »* :

| conteneur | verdict | mesure |
|---|---|---|
| `ancient_fury.WIDENED_NORMAL_ATTACKS` | **VOIE** | pendant exact de `NORMAL_ATTACK_CLEAVES` sur l'autre vslot (`$$GetTarget` `0x4a8` vs `$$GetCustomNormalAttackBehaviour` `0x4e8`) ; lu par `operations/damage.py` via `widened_for` |
| `power_up_spawn.POWER_UP_SPAWN_ABILITIES` | **VOIE** | **SPLATÉ** par `dispatch/registry.py` dans `ABILITY_TRIGGERS` |
| `power_up.POWER_UP_STAT_BOOST_ABILITIES` | **ÉCARTÉ** | doublon MORT : les 5 sont bien au registre, mais par cinq lignes **manuelles** ; le dict n'est importé **nulle part** |
| `targeting.TARGETING_OPTIONS_FOR_CONTINUE_OVERRIDES` | **ÉCARTÉ** | donnée annexe (un masque) ; le module écrit lui-même « AUCUN CONSOMMATEUR CÔTÉ PORT ». Ses **2 bascules sont FAUSSES** : `RunsAround` / `ArchContaminator` sont des `TriggeredAbilityType` d'ordinal égal à `1089`/`1168`, alors que la clé DÉCLARÉE est `ActiveAbilityType` |

⚠ Le message du test mettait en garde : *« un power-up paraît n'être pas un item de kit »*. **Vérifié,
ils le sont** — une unité `powup<X>` par passif (kind `npc`), voie d'attribution `passiveAbilities`.

⚠ **Le REBASE en a fait apparaître DEUX de plus, et c'est la raison d'être du re-jeu après rebase.**
Les 8 commits d'amont ont apporté `static_battle_rules.PARTIAL_ATTACK_TRIGGERED_ABILITY_TYPES` et
`…PARTIAL_ATTACK_EFFECT_TYPES` (#1113) : deux **FAITS NATIFS** — les `HashSet` statiques `+0x80` et
`+0x38` que lisent `StaticBattleRules.TriggeredAbility$$IsPartialAttackAbility` et
`StaticBattleRules.Effect$$IsPartialAttack` — donc **écartés**, comme leur voisin
`TILE_STATUS_EFFECT_TYPES` du même module. Le second a **1 bascule, FAUSSE** : sous la clé
`EffectType` qu'il déclare, `1077` nomme `HazeOfCorruption_DamageTransfer`, mais un balayage à trois
enums ferait basculer `Volatile` — et c'est le module lui-même qui met en garde (« les deux sets
sont dans deux enums différents, et l'ordinal ne les distingue pas »).

Effet : MUETS **4 → 0** (puis **2 → 0** après rebase), VOIES 20 → 22, ÉCARTÉS 27 → **31**, items
PORTE **inchangé (428)**.

## Résidus ouverts

* **#951-r8** — `metadata/active_playbook_builders.tsv` n'est régénérée par aucun générateur
  versionné, donc elle périme en silence à chaque build et sa note d'appariement peut devenir fausse
  (mesuré : `+1` écrit, `+0` réel).
* **#482-r7** — 31 fonctions de logique combat ont un `h_local` différent entre `rnca9r7q6c` et
  `t6dpr4k06g`, dont le lot STAT ; aucun port n'a été confronté à ce changement.
