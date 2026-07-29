# case-242 — `FabricatorClawArrayPlaybook` (1006) : le cap amis MORD, et il vaut 1

Résidu de `case-212` §7.2, qui avait la RE mais pas la mesure : « le relevé `methodPointers` le
montre sans ambiguïté […] ce n'est **pas** corrigé ici : la validation live manque ».

**Verdict : le cap `vtbl+0x228` vaut 1.** `X_nat` est **PLAT à 30 pour 1, 2 et 3 amis retenus** — le
port qui sommait `30 x n` rendait jusqu'à **120 au lieu de 30**. La constante est posée, gardée par
un test, et la contre-épreuve (cap retiré) fait bien rougir la garde.

Et la mesure a fait tomber un **second écart**, invisible au symbole nommé du filtre : le natif ne
garde pas « tout ami Mechanical » — il exige en plus `CanBeRepaired`, c'est-à-dire **un ami BLESSÉ**.
Ce gate est RE-solu et MESURÉ ici, mais **non porté** (§6.1) : il demande deux clés hors du fichier
de ce cas.

---

## 1. Réponse à la question binaire

> Sur un état où AU MOINS DEUX alliés retenus bordent la MÊME tuile candidate de `necroSpyder`,
> `X_nat` est-elle plate entre n = 1, 2 et 3 ?

**Oui, plate.** Loi native mesurée, sur deux couples board/seed :

| | |
|---|---|
| **Loi native** | terme = **30 si AU MOINS UN ami `Mechanical` ET `CanBeRepaired` est à distance 1**, sinon 0 |
| **Symbole du cap** | corps trivial `mov eax,1 ; ret` (`b8 01 00 00 00 c3`), fondu par l'ICF — **sans symbole propre** |
| **Ce que le port faisait** | `30 x #amis Mechanical adjacents` — jusqu'à **120** là où le natif rend 30 |
| **Ce que le port fait** | `MAX_ADJACENT_FRIENDS = 1` -> `30 x [au moins un ami Mechanical adjacent]` |
| **Reste faux** | le gate `CanBeRepaired` (§6.1) : un ami Mechanical à PV PLEINS est compté par le port, **pas** par le natif |

Aucun verdict antérieur n'est contredit : `#57i` et `#193c` n'ont exercé que `n <= 1`, régime où le
cap **et** le gate sont tous deux transparents dès qu'un ami est blessé.

---

## 2. Le cap, lu au binaire

`IdunBattle.AI.Playbook.AdjacentUnitPreferenceTriggeredAbilityPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext` :

```c
plVar9 = virt_0x248(this, adjacentFriends);          // FilterAdjacentFriends
uVar4  = Count(plVar9);
uVar5  = virt_0x228(this);                           // CAP amis
iVar3  = System.Math.Min(uVar4, uVar5);
for (i = 0; i < iVar3; i++)  val += virt_0x208(this, plVar9[i], ctx);
```

Le getter du cap n'a **aucun symbole** : l'ICF a fondu son corps avec des milliers d'autres. On le
lit dans le bloc `methodPointers` du PE (`scripts/python/probe_8889_methodptr_vtable.py`), où les
méthodes d'un type sont contiguës. Relevé **identique au bit près** pour les deux seules classes du
module qui surchargent aussi `FilterAdjacentFriends` :

| classe | +0x00 | +0x08 | +0x10 | +0x18 | +0x20 |
|---|---|---|---|---|---|
| `FabricatorClawArrayPlaybook` | `.ctor` | `GetAdjacentFriendUtility` | `33 c0 c3` (**ret 0**) | `b8 01 00 00 00 c3` (**ret 1**) | `FilterAdjacentFriends` |
| `SpiritualLeaderPlaybook` | `.ctor` | `GetAdjacentFriendUtility` | `33 c0 c3` (**ret 0**) | `b8 01 00 00 00 c3` (**ret 1**) | `FilterAdjacentFriends` |

Les deux corps fondus sont **les mêmes adresses** dans les deux blocs, aux mêmes positions
relatives.

**Ce relevé a été REFAIT sur le build `rnca9r7q6c`** (2026-07-29), après la mise à jour du jeu, à
partir des seules VA re-résolues par grep dans `data/symbols/rnca9r7q6c/ghidra/functions.tsv` : le
tableau ci-dessus est **inchangé, y compris les adresses des deux corps fondus**, qui restent
communes aux deux classes. La structure ne doit donc rien à un hasard de layout d'un build donné.

La position seule ne distingue pas `0x228` (cap amis) de `0x238` (cap ennemis) —
c'est la mesure live qui tranche (§5), exactement comme pour `SpiritualLeaderPlaybook` (`case-212`
§4.1). Un cap ENNEMIS n'aurait ici aucun effet : la face ennemis n'est pas surchargée (le `<ret 0>`
du +0x10) et rend 0.

## 3. Le filtre, lu au binaire — et son second gate

`IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$FilterAdjacentFriends` :

```csharp
foreach (u in friends)
    if (UnitExtensions.HasTrait(u, 5)               // UnitTrait.Mechanical
        && <this.field[3]>.<IBattleQuery slot 0x2e>(u, false))
        result.Add(u);
```

⚠ **`HasTrait(u, 5)` — pas `IsMechanical`.** `IdunBattle.Entities.UnitExtensions$$IsMechanical`
teste bien TROIS traits (`Mechanical` 5, `LivingMetal` 1000, `Vehicle` 0x405), mais **ce filtre ne
l'appelle pas** : il teste le trait 5 seul. Le port était correct sur ce point ; c'était un
faux-ami.

L'invocation d'interface se lit par le helper `FUN_180007b90(<slot>, <interface klass>, obj, arg, 0)`
(recherche de l'interface dans `klass+0xb0`, puis `vtable[interfaceOffset + slot]` à `klass+0x138`).
Le slot `0x2e` de cette interface est identifié par son SEUL autre appelant dans tout le binaire :
`IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass78_0$$u003CCanBeRepairedu003Eb__0`
— donc **`IBattleQuery.CanBeRepaired(unit, false)`**.

`IdunBattle.Core.Services.BattleQuery$$CanBeRepaired` délègue à
`IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired` (overload à 5 paramètres, avec
`attacker = null` et le dernier flag à 0). Sous ces arguments, les branches ACTIVES sont :

```
!EntityExtensions.IsMachine(u)                                   // entityType != 6 (MoW)
&& ( AttackQuery.IsDamagedUnit(u)                                // HealthComponent.IsWounded : hp < hpMax
     || UnitExtensions.GetStat(u, 4, 4) > 0 )
&& !UnitExtensions.HasHealBlockers(u)
&& UnitExtensions.IsAffectedByHealType(u, 1)                     // vrai d'office : trait 5 => IsMechanical
```

Les deux branches neutralisées par les arguments : `HasNegativeUnitEffect` (dernier flag 0) et
`HasFlag(attacker, 0x18)` (`attacker` nul).

⚠ **La seconde branche du OU est neutralisée par le MONTAGE, pas par le natif.**
`IdunBattle.Entities.Enum.StatType` `4 = Armor` — et `--hp-target`/`--hp-player` mettent
`Armor` ET `FixedArmor` **à 0** (piège de mesure documenté dans `runner.md` §3). Dans les deux
montages de §5, `GetStat(u, 4, …) > 0` est donc toujours FAUX et le gate se réduit exactement à
`IsWounded`. En bataille ORDINAIRE (armure non nulle) cette branche peut au contraire rendre le gate
passant sur une unité à PV pleins. Le second littéral (`4` en position 3) n'est PAS qualifié — le
symbole a deux surcharges (`GetStat(unit, statType)` et un thunk qui dépaquette
`param_2 >> 0x20`), donc l'argument peut être un mode de calcul. **À lire avant de porter le
gate** (§6.1) : s'en tenir à `IsWounded` produirait un filtre TROP STRICT hors de ce montage.

Conclusion utilisable telle quelle : **armure à 0, un ami Mechanical à PV pleins n'est PAS retenu**
— c'est ce que la mesure montre, et c'est ce qui borne la portée du résidu.

---

## 4. Le montage — c'est lui, le travail

Trois verrous, tous mesurés, aucun contournable :

1. **La géométrie de spawn ne donne jamais 2 alliés retenus autour d'une même tuile** (ce qui a
   manqué à `case-212` §7.2). On la FORCE : `_drive_cluster` cherche la tuile `T` atteignable par le
   carrier qui maximise le nombre d'alliés pouvant occuper des **voisins DISTINCTS** de `T`
   (affectation par backtracking sur `aiMovableTiles`), applique les `move`, puis **termine le tour**
   de ces alliés — l'IA n'a plus que le carrier à activer. `T` est laissée LIBRE : elle porte
   `n = |alliés placés|`, ses propres voisines donnant les régimes intermédiaires. Un seul DRIVE
   produit la gamme `n = 0, 1, 2, 3, 4`.
   Le forçage est tenté des **deux** côtés de la boucle (allié activé ou carrier activé) :
   `aiStepDryRun` ne mute pas, donc on peut déplacer les alliés puis redemander la décision du
   carrier. Sans ce second point d'entrée, le cluster ne se refaisait plus dès le tour 2 — mesure :
   **2 seules activations utiles en 140 pas** sur `C4_09`/31337.

2. **La relique du carrier fabrique un SECOND terme sur le MÊME voisinage.** `necroSpyder` porte
   `NetherRealmCasket` (`TertiaryAbility: 1462` au seed BC), et
   `IdunBattle.AI.Playbook.Loki.NetherRealmCasketPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`
   est un playbook de mouvement à part entière :

   ```c
   list = IBattleQuery.<slot 0x83>(tile, ...);      // amis adjacents
   list.RemoveAll(b__0);                            // retire self, puis !HasTrait(u, 5)
   yield Fix64.FromInt(ctx["NetherRealmCasket_LikesAdjacentFriendlyMechanicals"] * list.Count);
   ```

   soit **`+5 x #amis Mechanical adjacents`, sans cap ni gate** — terme à terme superposé à celui de
   1006, et non porté. Mesuré avec la relique, `X_nat` valait `35 / 70 / 60 / 100` : **illisible**.
   Le montage écrit un seed BC dérivé où toutes les `TertiaryAbility` sont nulles (`--seed-bc`) ;
   ça neutralise du même geste les reliques des alliés (`KardiocoreGalvanus_
   LikesAdjacentMechanicalFriends`, même forme).

3. **Un allié du roster allumait une autre feuille de tuile.** `admecMarshall` porte l'active
   `DoctrinaImperatives` (1118), qui déclenche `AttractMechanicalsUtility` (feuille 57 : +10 sur
   toute tuile voisine de lui, dès lors que le mover a le trait 5 — `necroSpyder` l'a). Il est
   **exclu du roster** ; sans ça deux tuiles portaient un +10 qu'aucune ligne du port n'explique
   (la feuille est portée mais INERTE, sa métadonnée `attract_mechanicals_neighbor` n'étant jamais
   posée — résidu voisin, hors périmètre).

Roster retenu : `necroSpyder, admecDestroyer, admecManipulus, admecRuststalker, necroDestroyer`
(4 alliés `Mechanical`, aucun porteur de 1118) contre
`darkaHellblaster, eldarRanger, worldKharn, templChampion, tauMarksman`, `--hp-target/--hp-player`
à 100000 pour que la bataille dure (les alliés se blessent au fil des tours, ce qui fait franchir
le gate `CanBeRepaired`).

### 4.1 Deux voies de mesure ÉCARTÉES (pour qu'on ne les re-tente pas)

> Une **troisième** les a rejointes depuis, mesurée elle aussi : l'argmax sans hook (§7.4).

* **Compter les lectures de la clé BC** (`aiUtilityTrace*`) aurait donné le cap directement — le
  corps commun lit `FABRICATORCLAWARRAY_AdjacentFriend` une fois par ami retenu, donc la longueur
  d'une suite consécutive vaut `Min(count, cap)`. Ça ne marche PAS sur un runner isolé :
  `prePopulateKnownConfigs` ne peuple `knownConfigs` que depuis l'`UtilitiesDatabase` du **MIRROR**
  (capturée sous `state.buildingMirror`), et le filtre des hooks rejette tout le reste —
  `knownConfigs = 0`, buffer vide (mesuré : 0 entrée). L'armer autrement suppose
  `aiUtilityTraceEnable`, qui installe des hooks GLOBAUX sur un chemin chaud : proscrit tant qu'un
  autre agent tourne.
* **Blesser les alliés au seed BC** (`RemainingHealth = Health // 2`) pour franchir le gate dès le
  tour 1 : écrasé par `frida/hooks/features/normalize-bc/json-build.ts`, qui fait
  `if ("RemainingHealth" in u) u.RemainingHealth = u.Health` APRÈS le chargement (mesuré : 102
  unités patchées, `nRep = 0` sur toutes les candidates). Le seul point d'insertion utile est le
  template DÉJÀ normalisé — ce que fait `rl_duel --hp-player`, et ce que refait à la main
  `probe_226_hammer_foehammer._build_custom_once`.

---

## 5. La mesure

`probe_242_fabricator_claw_cap.py` — même décomposition par étage que `probe_212` (hooks EXISTANTS
de `scorer-damage-trace`, armés pour UN `aiStepDryRun`, désarmés en `finally` ; aucune réinjection) :

    X_nat (tuile) = Tile(7) - Elevation - TileEffects
    X_port(tuile) = somme des feuilles du port, MEME retranchement

`nMech` = amis `Mechanical` à distance 1 (ce que le filtre du port retient) ; `nRep` = les mêmes,
restreints aux BLESSÉS (mirror de `CanBeRepaired`).

### 5.1 `MC1_67` / 777 — 18 tuiles hookées, **AVANT** le fix

| `nMech` | `nRep` | `X_nat` | `X_port` | `DELTA` |
|---|---|---|---|---|
| 0 | 0 | **0** | 0 | 0 |
| 1 | 0 | **0** | 30 | −30 |
| 1 | 1 | **30** | 30 | 0 |
| 2 | 1 | **30** | 60 | −30 |
| 2 | 2 | **30** | 60 | −30 |
| 4 | 3 | **30** | 120 | **−90** |

`X_nat` ne bouge pas de `nRep` = 1 à 3 : **le cap mord**. Et il vaut 30, pas 60 ni 90 : il vaut
exactement **1**. Le régime `(1, 0) -> 0` isole le gate `CanBeRepaired` — même poids BC, aucun ami
retenu, terme nul.

### 5.2 `C4_09` / 31337 — second couple, **APRÈS** le fix

| `nMech` | `nRep` | `X_nat` | `X_port` | `DELTA` |
|---|---|---|---|---|
| 0 | 0 | **0** | 0 | 0 |
| 1 | 0 | **0** | 30 | −30 |
| 2 | 1 | **30** | 30 | 0 |
| 4 | 1 | **30** | 30 | 0 |

Une fois le cap posé, `DELTA = 0` **partout sauf** dans le régime du gate `CanBeRepaired` (§6.1) —
y compris à `nMech = 4`, où le port rendait 120 avant le fix.

⚠ **Ce couple ne DISCRIMINE PAS le cap** : `nRep` n'y dépasse jamais 1 (les ennemis n'ont blessé
qu'un seul des quatre alliés en 90 pas), régime où `Min(nRep, cap)` vaut 1 pour tout cap `>= 1`. Il
confirme le gate et l'accord post-fix ; c'est `MC1_67`/777 (§5.1) qui tranche le cap. Un second
couple discriminant reste à produire — le levier est le nombre d'alliés BLESSÉS, pas la géométrie
(le DRIVE, lui, donne bien `nMech = 4`).

### 5.3 Ce que la mesure NE dit pas

Le cap est établi à 1 par `X_nat` plat de 1 à 3 amis retenus. Elle ne distingue pas formellement
`vtbl+0x228` de `vtbl+0x238` **au binaire seul** — c'est le fait que la face ennemis ne soit pas
surchargée (donc muette) qui exclut le second, comme pour `SpiritualLeaderPlaybook`.

---

## 6. Résidus

### 6.1 Le gate `CanBeRepaired` — RE FAITE, MESURÉE, NON PORTÉE

`IBattleQuery.CanBeRepaired` (§3) est le second terme du `&&` de
`IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook$$FilterAdjacentFriends`. Conséquence
mesurée : `nMech = 1, nRep = 0 -> X_nat = 0` alors que le port rend 30 — sur **les deux** couples
board/seed. C'est le régime NORMAL en début de bataille (personne n'est blessé), donc l'écart est
fréquent.

Le porter demande `hp` / `hp_max` dans les `friend_units` du `tile_leaf_ctx` — deux clés à ajouter
dans `engine/utilities/tile.py::_adjacent_units`, fichier **hors du périmètre de ce cas**. Poser le
cap sans ce gate est strictement moins faux : sur les 6 régimes mesurés en §5.1, il corrige 3 tuiles
et n'en dégrade aucune.

⚠ La branche `UnitExtensions.GetStat(u, 4, 4) > 0` du prédicat n'est pas qualifiée (quel `UnitStat`
vaut 4 ?) : à lire avant de porter, sous peine d'un gate trop strict.

### 6.2 `NetherRealmCasketPlaybook` (relique 1462) — playbook de mouvement NON porté

Structure entièrement RE-solue (§4 point 2) : `+5 x #amis Mechanical adjacents (self exclu)`, sans
cap ni gate, clé `NetherRealmCasket_LikesAdjacentFriendlyMechanicals` = 5 (BC). Il s'applique à
**tout** porteur de la relique, pas seulement `necroSpyder` — 4 unités du seed BC en portent une.
Une `NetherRealmCasketNonOwnerPlaybook` existe aussi
(`NetherRealmCasket_AdjacentMechanicals` = 5, `TriggeredAbilitiesNonOwner`), face qui n'est portée
pour aucun playbook.

### 6.3 `AttractMechanicalsUtility` (feuille 57) INERTE

Portée et correcte, mais `meta["attract_mechanicals_neighbor"]` n'est jamais posé par
`apply_tile_attributes` : +10 natif non rendu sur toute tuile voisine d'un porteur de
`DoctrinaImperatives` (1118), quand le mover a le trait 5. Même nature que le résidu `case-212` §7.1
(`meta.steppable` / `meta.decoy_gate`) — gap de CONTEXTE, pas de feuille. Contourné ici en excluant
`admecMarshall` du roster.

### 6.4 Le défaut de la BASE pour les caps — toujours non lu

Le relevé `methodPointers` ne le donne pas : le corps du défaut appartient à la base générique
`AdjacentUnitPreferenceTriggeredAbilityPlaybook<T>`, absente du dump (le bloc d'un concret ne
contient que ce que le concret DÉCLARE). On sait seulement qu'il est `>= 3`
(`GuardianOrganismPlaybook`, qui n'override pas, somme bien 3 amis — `case-36`). `MAX_ADJACENT_*`
reste donc `None` quand le concret est muet.

---

## 7. Validation

### 7.1 Le cap — mesuré au natif (build `gqfc5mff6c`)

| | |
|---|---|
| **Le cap vaut 1** | `MC1_67`/777, 18 tuiles hookées : `X_nat` = 30 pour `nRep` = 1, 2 **et** 3 (§5.1). C'est LA question binaire du cas, et elle est tranchée par la mesure. |
| **Le gate `CanBeRepaired` mord** | `nMech = 1, nRep = 0 -> X_nat = 0` sur les DEUX couples (§5.1, §5.2) |
| **Accord port/natif après le fix** | `C4_09`/31337 : `DELTA = 0` sur toutes les tuiles hors régime du gate, y compris à `nMech = 4` (§5.2) |
| **Le cap côté PORT** | `30 / 30 / 30 / 30` pour 1 à 4 amis Mechanical adjacents (vérifié hors runner, contexte synthétique) |

### 7.2 Re-confrontation après la MAJ `gqfc5mff6c` -> `rnca9r7q6c` (2026-07-29)

| confronté | résultat |
|---|---|
| **La RE au binaire du NOUVEAU build** | relevé `methodPointers` REFAIT sur `rnca9r7q6c` : blocs des deux classes **inchangés**, mêmes corps fondus aux mêmes positions (§2). La RE ne dépend pas du build. |
| **`tests/engine/test_fabricator_claw_cap_live.py`** | **10 passed / 0 skipped** (2 montages × 5), build `rnca9r7q6c`. Le fichier n'arme aucun hook RVA. |
| **Contre-épreuve** | `MAX_ADJACENT_FRIENDS = None` -> **2 failed / 8 passed**, `test_term_is_capped_at_one_adjacent_mechanical` rouge sur les DEUX montages : `MC1_67`/777 `(1,3): (120.0, 4)` et `(2,1): (60.0, 2)` ; `C4_09`/31337 `(3,3): (120.0, 4)`, `(4,1)` et `(5,3): (60.0, 2)`. Le montage exerce donc `n = 4` sur les deux couples. |
| **Non-régression** | `test_spiritual_leader_tile_term_live.py` + `test_tile_term_unit_gated_playbooks_live.py` + `test_tile_term_triggered_playbooks_live.py` : **48 passed / 4 failed**. Aucun échec sur 1006 ni sur 1275 (l'autre porteur de cap) — les 4 sont sur `blackTerminator`/1038, `deathBlightbringer`/1071 et `templAncient`, et se reproduisent sur `origin/master` **sans aucune modification de `engine/`** (`git diff --stat HEAD -- scripts/python/engine/` vide). Étrangers à ce cas ; à traiter en fiche propre. |
| **La RE, transformée en GARDE** | `tests/engine/test_fabricator_claw_cap_binary.py` — **5 passed**, offline pur (~1 s). Rejoue le relevé `methodPointers` à chaque passe, en partant de `data/symbols/CURRENT` : **aucune VA écrite**, donc valable au prochain build. Contre-épreuve : attendre `mov eax,2` fait rougir les 2 classes. |

### 7.3 Ce qui reste NON CONFRONTÉ, et pourquoi

| ouvert | état |
|---|---|
| **`X_nat` sur `rnca9r7q6c`** | **inaccessible** : `probe_242_fabricator_claw_cap.py` lit `X_nat` par les hooks de `scorer-damage-trace`, dont `RVA_CALC_TILE_PRED` / `RVA_ELEVATION_LEAF` / la table `leafHooks` sont **hardcodées pour `gqfc5mff6c`**. Les re-résoudre exige un rebuild du bundle **et une réinjection** — proscrite tant qu'une session est partagée. Le probe vérifie le hash et refuse de tourner : il ne mesure pas à côté, il s'arrête. |
| **Un second couple board/seed DISCRIMINANT pour le cap** | toujours ouvert. `C4_09`/31337 plafonne à `nRep = 1` (re-mesuré 2026-07-29 : 2 activations du carrier, trajectoire épuisée) ; `MC1_67`/777 atteint bien `nRep = 3`. Le levier reste le nombre d'alliés BLESSÉS, pas la géométrie. |
| **La voie « argmax sans hook »** | **ÉCARTÉE, mesurée** — cf. §7.4. |

### 7.4 Une troisième voie de mesure écartée : l'argmax sans hook

`probe_242b_fabricator_claw_argmax.py` tente de trancher le cap **sans hooker quoi que ce soit**, en
confrontant la tuile que l'IA JOUE (`aiStepDryRun` -> `MoveUnitMessage`) aux deux hypothèses
`H_cap` (terme = 30) et `H_somme` (terme = 30 × n), évaluées côte à côte sur le même contexte de
feuille par une sous-classe qui ne diffère que par `MAX_ADJACENT_FRIENDS`.

**Résultat : NÉGATIF.** Sur `MC1_67`/777, le montage atteint le régime visé (pas 28, candidate
`(1,1)` à `nMech = 4, nRep = 3` — exactement le `(4,3)` de §5.1), mais le natif joue `(5,4)`, une
tuile à `n = 0` que **ni** `H_cap` (argmax `(3,2)`) **ni** `H_somme` (argmax `(1,1)`) ne place en
tête. Le terme de tuile n'est donc pas ce qui décide l'action du carrier à ce pas : même un écart de
**+120** entre les deux hypothèses ne se lit pas dans le choix, noyé par les autres composantes de
l'utilité totale (approche / prédiction d'attaque).

À ranger avec les deux voies de §4.1 : **on ne re-tente pas de trancher ce cap par le choix natif.**
Ce qui reste utilisable du probe : son MONTAGE (il produit bien `nRep = 3`) et sa table par tuile,
prêts pour le jour où les hooks seront re-résolus.

## 8. Reproduire

VA du build `rnca9r7q6c` — les re-résoudre par un grep dans
`data/symbols/<build>/ghidra/functions.tsv` au changement de hash (aucune n'est à recopier telle
quelle) :

```bash
cd scripts/python
python -m pytest tests/engine/test_fabricator_claw_cap_binary.py      # le cap AU BINAIRE, offline
python -m pytest tests/engine/test_fabricator_claw_cap_live.py        # la loi du port, live

# la meme lecture a la main (le test ci-dessus resout ces VA tout seul depuis data/symbols/CURRENT) :
python probe_8889_methodptr_vtable.py --dll "C:/Users/nicolasv/AppData/Local/tacticus/games/rnca9r7q6c/GameAssembly.dll" \
    --window 8 0x181262370 0x181262310 0x181262050

# X_nat : NE TOURNE QUE SUR `gqfc5mff6c` (hooks RVA) -- cf. par.7.3
python probe_242_fabricator_claw_cap.py --board MC1_67 --seed 777 --extra \
    --hp-target 100000 --hp-player 100000 \
    --p-units "necroSpyder,admecDestroyer,admecManipulus,admecRuststalker,necroDestroyer" \
    --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"

# le MONTAGE seul, sans aucun hook (tourne sur tout build) : produit `nRep = 3` sur MC1_67/777.
# Son verdict d'argmax ne conclut PAS (par.7.4) ; ce qu'il sert, c'est la table par tuile.
python probe_242b_fabricator_claw_argmax.py --board MC1_67 --seed 777 --max-steps 140 --extra \
    --hp-target 100000 --hp-player 100000 \
    --p-units "necroSpyder,admecDestroyer,admecManipulus,admecRuststalker,necroDestroyer" \
    --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"
```

Les deux corps fondus se lisent ensuite à leurs adresses (`33 c0 c3` = `ret 0`, `b8 01 00 00 00 c3`
= `ret 1`) — sur `rnca9r7q6c`, `0x1802b45b0` et `0x1802cfd00`, communes aux deux classes.
