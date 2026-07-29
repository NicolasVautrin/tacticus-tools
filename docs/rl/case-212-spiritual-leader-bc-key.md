# case-212 — la clé BC de `SpiritualLeader` (1275) : `SPIRITUALLDEADER_AdjacentDecoy`, et le cap qui la borne

Résidu de `case-193c` §7, qui laissait la structure tranchée mais **la clé non résolue** :
« aucune clé de `Utilities.Default.TriggeredAbilities` ne matche leur préfixe : soit le terme vaut 0,
soit la clé ne suit pas la convention de nommage. Résoudre les littéraux `DAT_*` avant de conclure. »

**Verdict : la clé existe, elle vaut 30, et le port ne la lisait pas.** Le préfixe ne matchait pas
parce que le littéral du jeu porte **une faute de frappe** : `SPIRITUALLDEADER_` (L-D-E-A-D-E-R),
pas `SPIRITUALLEADER_`. Aucune recherche par préfixe correct ne pouvait la trouver.

Et la confrontation live a fait tomber un **second** écart, invisible au décompilé nommé : le terme
est **borné à UN decoy** (`vtbl+0x228 = 1`). Sommer `30 x n` aurait été aussi faux que rendre 0.

---

## 1. Réponse à la question binaire

| | |
|---|---|
| **Clé BC** | `Utilities.Default.TriggeredAbilities["SPIRITUALLDEADER_AdjacentDecoy"]` = **30** |
| **Symbole qui la lit** | `IdunBattle.AI.Playbook.Loki.SpiritualLeaderPlaybook$$GetAdjacentFriendUtility` |
| **Ce que le port lisait AVANT** | **rien** — `SpiritualLeaderPlaybook` était absent de `TRIGGERED_MOVE_PLAYBOOKS`, donc `load_playbook(1275)` rendait `None` et le terme valait **0** |
| **Loi effective** | terme = **30 si AU MOINS UN decoy allié est à distance 1** de la tuile candidate, sinon 0 — *pas* `30 x n` (cap `vtbl+0x228` = 1) |
| **Face concernée** | DÉCISION (utilité de MOUVEMENT). La face COMBAT (`runner/operations/triggers/loki/spiritual_leader.py`) ne lit **aucune** clé BC — elle lit le gameconfig (`constants.unitId/unitId_2`, `summonHp/Dmg/Armor`) ; elle n'est pas en cause et n'est pas touchée. |

---

## 2. Comment la clé a été résolue (et pourquoi elle ne l'avait pas été)

`case-193c` avait buté sur le fait que le littéral n'est **pas** dans le binaire : IL2CPP range les
string literals dans `global-metadata.dat`, et le code généré ne référence qu'un **slot de metadata
usage** (`DAT_<addr>` chez Ghidra) initialisé paresseusement :

```c
// IdunBattle.AI.Playbook.Loki.SpiritualLeaderPlaybook$$GetAdjacentFriendUtility
if (<once-flag> == '\0') { il2cpp_codegen_initialize_runtime_metadata(&<slot>); <once-flag> = 1; }
(**(code **)(param_3 + 0x18))(*(undefined8 *)(param_3 + 0x40), <slot>, local_res18,
                             *(undefined8 *)(param_3 + 0x28));
return local_res18[0];
```

C'est **le même corps, instruction pour instruction**, que
`IdunBattle.AI.Playbook.Loki.GuardianOrganismPlaybook$$GetAdjacentFriendUtility` (lookup PLAT :
l'argument `unit` n'est lu par AUCUNE instruction) — seul le slot change.

La chaîne de résolution, portée par `scripts/python/probe_212_bc_key_literals.py` :

1. **symbole -> adresse** via `data/symbols/<build>/ghidra/functions.tsv` (versionné) — aucune VA en
   entrée du script ;
2. **adresse -> octets** en lisant `GameAssembly.dll` sur disque (PE : VA -> offset fichier) ;
3. **octets -> slots** : balayage des déplacements RIP-relatifs candidats du corps de la fonction ;
4. **slot -> token** : la valeur 8 octets écrite STATIQUEMENT dans le slot est le token de metadata
   usage `(kind << 29) | index` ; `kind == 5` = `kIl2CppMetadataUsageStringLiteral` ;
5. **token -> chaîne** : `global-metadata.dat` (sanity `0xfab11baf`, **version 39**), table
   d'offsets `stringLiteral` (29 473 bornes, 29 472 chaînes) + blob `stringLiteralData`.
   **L'index encodé vaut `2*i + 1`**, où `i` est l'indice de borne — relation **calibrée sur 9
   ancres** dont la chaîne était déjà connue par une autre voie (§3), pas supposée. Elle sert aussi
   de filtre anti-faux-positif : un slot de string literal ne porte que des index IMPAIRS.

Résultat pour le slot lu par `SpiritualLeaderPlaybook$$GetAdjacentFriendUtility` :
token `0xa0006fcf` -> kind 5, index 28623 -> borne 14311 -> **`SPIRITUALLDEADER_AdjacentDecoy`**.

Et cette chaîne **est** une clé de `Utilities.Default.TriggeredAbilities` (107 clés,
`data/seed-bc.json`), de valeur **30**. La double confirmation (littéral natif == clé BC existante)
ferme le doute : ce n'est ni une clé morte ni 0.

---

## 3. Calibration de la méthode — 9 ancres, 9/9

La relation `index_encodé = 2*i + 1` n'est pas déduite d'une doc : elle est **mesurée** sur les
playbooks dont la clé était déjà connue et vérifiée autrement (case-36, #57i, #193c, #211, N13).
`probe_212_bc_key_literals.py --anchors` rejoue la calibration :

| symbole (`IdunBattle.AI.Playbook.Loki.` …) | littéral résolu | BC |
|---|---|---|
| `GuardianOrganismPlaybook$$GetAdjacentFriendUtility` | `GuardianOrganism_AdjacentFriend` | 30 |
| `RitesOfBattlePlaybook$$GetAdjacentFriendUtility` | `RITESOFBATTLE_AdjacentFriend` | 10 |
| `MartialApotheosisPlaybook$$GetAdjacentEnemyUtility` | `MARTIALAPOTHEOSIS_AdjacentEnemy` | 15 |
| `FabricatorClawArrayPlaybook$$GetAdjacentFriendUtility` | `FABRICATORCLAWARRAY_AdjacentFriend` | 30 |
| `FearedInterrogatorPlaybook$$GetAdjacentFriendUtility` | `FearedInterrogator_AdjacentDAFriend` | 30 |
| `HatefulAssaultPlaybook$$GetAdjacentEnemyUtility` | `HATEFULASSAULT_AdjacentEnemyRanged` + `..._AdjacentEnemyDefault` | 20 / 10 |
| `CursedPlagueBellPlaybook$$GetAdjacentFriendUtility` | `CursedPlagueBell_AdjacentChaosFriend` | 20 |
| `CursedPlagueBellPlaybook$$GetAdjacentEnemyUtility` | `CursedPlagueBell_AdjacentPsychicEnemy` | 10 |
| `AstartesBannerPlaybook.<CalculateMovementUtilityInStepsInternal>d__2$$MoveNext` (autre famille) | `AstartesBanner_NearbyFriend` | 5 |

Aucune ancre ne rend une chaîne inattendue ; aucune ne rend une chaîne absente de la BC.

---

## 4. Ce que dit le décompilé — et le cap que les tables de symboles CACHENT

`IdunBattle.AI.Playbook.Loki.SpiritualLeaderPlaybook` :

```csharp
// $$.ctor  ->  AdjacentToOwnerNonOwnerPlaybook<T>..ctor(this, 0x4fb /* 1275 SpiritualLeader */, ...)

// $$FilterAdjacentFriends(friends) : OrderedSet<Unit>
foreach (u in friends)
    if (UnitExtensions.HasTrait(u, 0x41d))   // UnitTrait.Decoy = 1053
        result.Add(u);

// $$GetAdjacentFriendUtility(unit, ctx)     // LOOKUP PLAT : `unit` n'est lu par aucune instruction
return ctx.GetUtilityValue("SPIRITUALLDEADER_AdjacentDecoy");   // 30 (BC)
```

Le tri du voisin est donc **dans le FILTRE** (comme `FabricatorClawArrayPlaybook`), pas dans
l'accesseur de poids (comme `FearedInterrogatorPlaybook`).

⚠ **Qualification de l'enum** : `0x41d = 1053` est **`UnitTrait`.Decoy** — homonymes à écarter :
`EffectType` 1053 = `ShadowInTheWarp_LessDmg_Effect`, `ActiveAbilityType` 1053 = `DevoutPush`,
`TriggeredAbilityType` 1053 = `BroodProgenitor`. Même `UnitTrait` que la face COMBAT.

### 4.1 Le cap `vtbl+0x228` — un corps que `search_symbols_by_name` ne peut PAS montrer

Le corps commun
`IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext`
ne somme pas tous les voisins retenus :

```c
plVar9 = virt_0x248(this, adjacentFriends);          // FilterAdjacentFriends
uVar4  = Count(plVar9);
uVar5  = virt_0x228(this);                           // CAP amis
iVar3  = System.Math.Min(uVar4, uVar5);
for (i = 0; i < iVar3; i++)  val += virt_0x208(this, plVar9[i], ctx);
```

`SpiritualLeaderPlaybook` **override ce slot**. Son getter est un corps trivial (`mov eax,1 ; ret`)
que l'ICF a **fondu** avec des milliers d'autres : il n'a donc **aucun symbole propre** et
`search_symbols_by_name` ne le montre pas — le faux négatif exact que documente le CLAUDE.md
(« l'ABSENCE d'une méthode dans les tables ne prouve RIEN »).

On le lit par le **bloc `methodPointers` du PE** (`scripts/python/probe_8889_methodptr_vtable.py`),
où les méthodes d'un type sont **contiguës, dans l'ordre des slots**. Relevé sur les 11 concrets du
module — c'est la corrélation, pas une lecture isolée, qui identifie le slot :

| playbook | groupe `methodPointers` | lecture |
|---|---|---|
| `CursedPlagueBell` (2 faces surchargées, pas de filtre) | `.ctor, GetAdjFriendUtil, GetAdjEnemyUtil, b__4_0` | **aucun** corps fondu |
| `GuardianOrganism`, `RitesOfBattle`, `Deathwing`, `TaintedNarthecium`, `FearedInterrogator`, `ExplosiveMaladies` (face AMIS) | `.ctor, GetAdjFriendUtil, <ret 0>` | `<ret 0>` = la face ENNEMIS non surchargée |
| `MartialApotheosis`, `HatefulAssault` (face ENNEMIS) | `.ctor, <ret 0>, GetAdjEnemyUtil` | `<ret 0>` = la face AMIS, **avant** la face ennemis : l'ordre est bien `0x208` puis `0x218` |
| **`FabricatorClawArray`**, **`SpiritualLeader`** (face AMIS **+ filtre**) | `.ctor, GetAdjFriendUtil, <ret 0>, <ret 1>, FilterAdjFriends` | `<ret 1>` s'intercale entre `0x218` et `0x248` : c'est un **cap**, et il vaut **1** |

Les deux corps fondus sont `xor eax,eax ; ret` (0) et `mov eax,1 ; ret` (1). Le `<ret 1>`
n'apparaît **que** chez les deux classes qui surchargent aussi `FilterAdjacentFriends` — 2 sur 11.

La position ne distingue pas à elle seule `0x228` (cap amis) de `0x238` (cap ennemis) ; **la mesure
live tranche** : `X_nat` vaut 30 pour 1, 2 ET 3 decoys adjacents (§6). Un cap ennemis n'aurait aucun
effet (la face ennemis rend 0). Donc `vtbl+0x228 = 1`.

**Terme = 30 si >= 1 decoy allié à distance 1, sinon 0.**

---

## 5. Confrontabilité

Porteur : **`genesMagus` (Xybia)**, `passiveAbilities = ['SpiritualLeader']` (son SEUL passif, ce qui
isole le terme), **HERO du pool** (`rl_duel.py build --list-pool`, rank 17). Le passif est
**auto-alimenté** : sa face COMBAT pose un `genesSmnDecoy` (`traits: ['Steppable','Decoy']`) à la fin
de chaque activation (`On(0x1c = ArrivedAtFinalTile)`). Il suffit donc de faire DURER la bataille
(`--hp-target/--hp-player` élevés) pour obtenir des candidates à 0, 1, 2 et 3 decoys adjacents.

⚠ Sans ce levier, la 1ʳᵉ activation de Xybia donne `#decoys = [0]` sur **toutes** les candidates :
un montage qui ne peut rien contredire.

---

## 6. Validation

### 6.1 Arithmétique par tuile, contre la mesure native

`probe_212_spiritual_leader_tile_term.py` — décomposition par étage sur les hooks **existants** de
`scorer-damage-trace` (armés pour UN `aiStepDryRun`, désarmés en `finally` ; **aucune réinjection**) :

    X_nat  = Tile(7) − Elevation − TileEffects        (scorerTileTermTrace / Elev / Leaf)
    X_port = somme des feuilles du port, MÊME retranchement

`MC1_67`/777 pas 47 (u87 `genesMagus`, 16 tuiles) et `C4_09`/31337 pas 21 (u94, 6 tuiles) :

| | |
|---|---|
| `#decoys adjacents -> {X_nat}` | `n=0 -> {0, 25}` · `n=1 -> {30, 55}` · `n=2 -> {30}` · `n=3 -> {30}` |
| `occupant de la tuile -> {X_nat − X_port}` | `autre -> {0}` (18 tuiles) · `decoy ami -> {25}` (4 tuiles) |

**Lecture** : `X_nat` ne croît PAS avec `n` — 1, 2 et 3 decoys donnent 30. Le cap mord. Et une fois
le cap porté, `X_nat − X_port` est **exactement 0 sur les 18 tuiles** dont l'occupant n'est pas un
decoy ami. Les 4 restantes portent un résidu **constant** de +25, entièrement attribué (§7.1) et
étranger à 1275.

Avant le port : le terme valait 0 et le désaccord était de 10 tuiles / 16 sur le seul `MC1_67`.
Avec le port mais **sans** le cap : 30/60/90 au lieu de 30 — le désaccord changeait de signe sans
disparaître. C'est la décomposition par étage, pas l'ajustement d'un scalaire, qui a séparé les deux.

### 6.2 Gardes vues ROUGES (contre-épreuve)

`tests/engine/test_spiritual_leader_tile_term_live.py` — **10 passed** en l'état (2 montages × 5).
Deux mutations adversariales de mon propre fix :

| mutation | résultat |
|---|---|
| `MAX_ADJACENT_FRIENDS = None` (cap retiré) | **2 failed / 8 passed** — `test_term_is_capped_at_one_adjacent_decoy` tombe sur les DEUX montages (`(4,3): (60.0, 2)`) |
| entrée `1275` retirée du registre (état d'avant ce commit) | **4 failed / 6 passed** — `load_playbook(1275) is None` |

La garde `test_bc_key_is_the_misspelled_one_and_is_non_zero` couvre le troisième mode de panne, celui
que ce cas a mis au jour : **« corriger » la faute de frappe** rendrait `Weights.sub` = 0 et
tuerait le terme sans erreur ni crash. Elle asserte les deux sens (le littéral du jeu est non nul, et
son orthographe corrigée est absente de la BC).

`test_montage_exercises_more_than_one_adjacent_decoy` empêche la garde du cap de passer à vide si une
trajectoire dérive vers une géométrie où aucune candidate n'a 2 decoys adjacents.

### 6.3 Non-régression

| suite | résultat |
|---|---|
| `test_tile_term_unit_gated_playbooks_live.py` + `test_tile_term_triggered_playbooks_live.py` (les 11 autres concrets du module, dont les 4 à lookup plat et les 3 gatés de #193c/#211) | **42 passed**, 0 skipped |
| `test_move_tile_sweep_order_live.py` + `test_playbook_live.py` + `test_stay_in_place_live.py` | **8 passed / 3 skipped** — mêmes skips que ceux documentés par case-193c §5.4 (montages sans tie), inchangés |

Le passage `MAX_ADJACENT_*` par défaut à `None` (= « le concret n'override pas le slot ») rend le
changement **value-preserving** pour les 11 concrets déjà portés : aucun ne borne, donc `Min` n'est
pas appliqué. Runners disposés au fil de l'eau ; `listRunners` vide en fin de course.

---

## 7. Résidus (hors périmètre de ce cas, à ouvrir en fiches)

### 7.1 Deux feuilles de tuile PORTÉES mais INERTES — le résidu de +25, entièrement attribué

Sur toute tuile candidate **occupée par un decoy ami**, `X_nat − X_port` = **+25**, constant, sur les
deux boards. Le compte est exact et se lit dans la BC :

* `SteppableUnitUtility` (19) : `Utilities.Default.SteppableUnit.FriendlyDecoy` = **−50** ;
* `AttractToDecoysUtility` (64) : `Utilities.Default.DecoysAndMisdirection_AttractToDecoys.`
  `DecoysAndMisdirection_FriendlyGSCLikeDecoys` = **+75** (×1 ami porteur de 1304).

−50 + 75 = **+25**. Les deux classes EXISTENT dans `engine/utilities/tile.py` et sont correctes ;
elles rendent 0 parce que leurs métadonnées par tuile ne sont **jamais posées** par
`apply_tile_attributes` : `meta["steppable"] = {is_enemy, is_decoy}`, `meta["decoy_gate"]`,
`meta["decoy_friend_count"]` (et `ctx["unit_faction"] == 15`). Gap de CONTEXTE, pas de feuille.
Conséquence mesurée : le port ÉGALISE des tuiles que le natif sépare de 25 dès qu'un decoy est en
jeu — donc sur toute bataille Genestealers. **Fiche à ouvrir.**

### 7.2 `FabricatorClawArrayPlaybook` (1006) porte le MÊME corps de cap `<ret 1>` — non appliqué ici

Le relevé `methodPointers` du §4.1 le montre sans ambiguïté : `FabricatorClawArrayPlaybook` a
exactement le même groupe de 5 méthodes, avec le corps fondu `mov eax,1 ; ret`. Son port somme donc
`30 x #amis Mechanical` là où le natif s'arrête très probablement à 30. Ce n'est **pas** corrigé ici :
la RE est faite, mais la validation live manque (les montages de #57i/#193c n'ont jamais exercé
**2 amis Mechanical adjacents** — `n ∈ {0,1}` seulement, donc aucun de leurs verdicts n'est
contredit). Il faut son propre montage (`necroSpyder` + 2 alliés Mechanical adjacents) avant de
poser `MAX_ADJACENT_FRIENDS = 1` sur cette classe. **Fiche à ouvrir.**

### 7.3 `ExplosiveMaladies` (1068) — les DEUX clés sont résolues, le port reste à faire

La même méthode les rend, et la faute de frappe est du même acabit :
`EXPLOSIBEMALADIES_AdjacentRangedFriend` (**B** au lieu de **V**) = 15, et
`EXPLOSIBEMALADIES_AdjacentChoasMeleeFriend` (`Choas` au lieu de `Chaos`) = 15 — les deux **existent**
en BC. `IdunBattle.AI.Playbook.Loki.ExplosiveMaladiesPlaybook$$GetAdjacentFriendUtility` est de la
3ᵉ forme : `HasRangedWeapon(unit)` -> clé `_AdjacentRangedFriend`, sinon `HasTrait(unit, 0x7ea)`
(`UnitTrait.Chaos`) -> clé `_AdjacentChoasMeleeFriend`, sinon 0.
⚠ Le nom de la 2ᵉ clé dit « Melee » mais **aucune instruction ne teste `IsMelee`** : la branche est
simplement le `else` de `HasRangedWeapon`. Son groupe `methodPointers` est
`[.ctor, GetAdjFriendUtil, <ret 0>]` — **pas de cap**, et pas de `FilterAdjacentFriends`.
**Fiche à ouvrir** (un item par cas).

### 7.4 Autres

* **`darkaSmnWatcher`** (porteur de `WatchedOver` 1524) : chemin d'octroi non établi, intact. Sa clé
  BC, elle, se résout par la même voie : `WatchedOver_FriendsInRange` = 20.
* **La face `TriggeredAbilitiesNonOwner(4)`** de `SpiritualLeader` : `Utilities.Default.`
  `TriggeredAbilitiesNonOwner` n'a **aucune** clé au préfixe `SPIRITUALL*` (vérifié) — rien à porter
  de ce côté, comme pour 1038/1235.
* **Le cap ENNEMIS (`vtbl+0x238`)** n'est overridé par aucun des 11 concrets : `MAX_ADJACENT_ENEMIES`
  reste `None` partout. Et le défaut de la BASE (amis comme ennemis) n'a toujours pas été lu — on
  sait seulement qu'il est `>= 3` (`GuardianOrganismPlaybook`, qui ne l'override pas, somme bien
  3 amis : case-36, 30/90 exacts).

---

## 8. Ce que cette méthode débloque au-delà du cas

`probe_212_bc_key_literals.py` résout **n'importe quel** littéral de chaîne lu par **n'importe
quelle** fonction native, à partir de son SYMBOLE seul (aucune VA en entrée). Trois conséquences :

* « aucune clé BC ne matche le préfixe » n'est plus un verdict acceptable — la clé se **LIT** ;
* les fautes de frappe du jeu (`SPIRITUALLDEADER`, `EXPLOSIBEMALADIES`, `Choas`) cessent d'être des
  angles morts : sur 107 clés `TriggeredAbilities`, au moins **3** ne sont pas devinables par le nom
  de leur ability ;
* couplée au bloc `methodPointers` (§4.1), elle rend lisibles les **deux** catégories que les tables
  de symboles cachent : les chaînes (dans `global-metadata.dat`) et les corps triviaux (fondus par
  l'ICF). Les deux étaient en jeu sur ce seul item.

## 9. Reproduire

```bash
cd scripts/python
python probe_212_bc_key_literals.py --anchors          # calibration 9/9
python probe_212_bc_key_literals.py                    # la cle du cas (+ ExplosiveMaladies)
python probe_8889_methodptr_vtable.py --window 4 0x181188ed0 0x181188e70 0x181188c40   # le cap
python probe_212_spiritual_leader_tile_term.py --board MC1_67 --seed 777 --max-steps 60 --extra \
    --hp-target 100000 --hp-player 100000 \
    --p-units "genesMagus,genesPrimus,genesKelermorph,orksNob,spaceWulfen" \
    --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"
python -m pytest tests/engine/test_spiritual_leader_tile_term_live.py
```

⚠ `probe_212_spiritual_leader_tile_term.py` arme des hooks **RVA build-spécifiques** (`gqfc5mff6c`,
hérités de `probe_193c`) : il vérifie le hash, arme pour un `aiStepDryRun`, désarme en `finally`.
Les VA passées à `probe_8889` sont celles de `SpiritualLeaderPlaybook` dans ce build — les
re-résoudre par `search_symbols_by_name` au changement de hash.
