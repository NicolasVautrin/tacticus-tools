# Case N13 — le terme de tuile `Tile(7)` short : le registre du dispatcher `TriggeredAbilities(2)`

**Verdict : ce n'est ni un facteur d'échelle, ni une feuille absente du composite — c'est le
REGISTRE DE PLAYBOOKS de la feuille dispatcher `TriggeredAbilities(2)` qui est incomplet, plus une
feuille `UnitEffects*` restée dormante faute de métadonnée.** Les 29 enfants de la `ComposedUtility`
sont TOUS portés côté enfants ; le trou est UN ÉTAGE PLUS BAS, dans ce que la feuille (2) va
chercher par `PlaybookDatabase.LoadPlaybook`.

---

## 1. Énumération des contributeurs natifs de l'utilité de tuile

`IdunBattle.AI.Playbook.ComparablePlaybooku003CTu003E$$CalculateUtilityFromTilePrediction` ne
contient **aucun terme propre** : il construit un `UtilityMovementCase(unit, position, …)` et
délègue à **une seule** utilité, celle enregistrée à la clé `7` (`Tile`) —

```csharp
u = Fix64.FromInt(0);
if (!virt_0x318(this)) {                                  // gate
    pos = virt_0x398(this, …);                            // position candidate
    if (UnitPosition.get_MainTile(&pos) != null) {
        var kase = new UtilityMovementCase(unit, pos, 0, Nullable(this.abilityType), 0, 0);
        var util = Dictionary_TryGet(this.utilities@0x40, 7);     // <- UtilityType.Tile
        u = Fix64.op_Addition(u, util.EvaluateMovement(kase));
    }
}
return u;
```

Donc **tout** le terme de tuile est la somme des enfants de cette `ComposedUtility`. Leur liste,
**relue live** (`scorerComposedDump`, deux runs indépendants, 999 et 31337) — **29 enfants**, dans
cet ordre :

```
ElevationUtility · TemporaryTileUtility · TileEffectsUtility · UnitEffectsAdjacentUtility ·
UnitEffectsSurroundingUtility · UnitEffectsRangedUtility · RangedAdjacentEnemyUtility ·
SteppableUnitUtility · CapturePointTileUtility · TriggeredAbilitiesUtility ·
TriggeredAbilitiesNonOwnerUtility · UnitSpecificBehavioursUtility · KustomForceFieldUtility ·
DefenderOfTheGreaterGoodUtility · SaviorProtocolsUtility · TilePendingBlockableSummonUtility ·
PowerUpTileUtility · AttractMechanicalsUtility · Phantasm_AvoidFriendlyPhantasmUtility ·
EchoesFromTheWarp_FriendliesAvoidGhostUtility · ContaminatedUtility · MoltenForm_TilesUtility ·
BioMinefield_MoveTowardsTargetUtility · MasterOfTheTutelaries_MoveTowardsTargetUtility ·
AttractToDecoysUtility · DespoiledGroundUtility · SummonDislikeDoorOpeningUtility ·
HeroDoorOpeningUtility · EnvEndBombardmentUtility
```

⚠ Un `TileDistanceUtility` apparaît en **30e** position sur d'autres instances de `ComposedUtility`
du même dump : ce n'est **pas** le composite `Tile(7)` (il en existe plusieurs dans le processus),
et c'est exactement le piège du « j'ai vu 30 enfants ». Le composite `Tile(7)` en a **29**, et
`TILE_LEAF_IDS` les couvre 1:1.

⇒ **Aucune feuille ne manque au composite.** Le terme manquant vient donc de l'intérieur d'une
feuille — et deux d'entre elles sont des trous connus :

| Feuille | Ce qu'elle va chercher | État du port AVANT |
|---|---|---|
| `TriggeredAbilities(2)` | **dispatcher** : `PlaybookDatabase.LoadPlaybook(ability)` pour CHAQUE ability déclenchée du mover, puis Σ `CalculateMovementUtilityInSteps` | registre `TRIGGERED_MOVE_PLAYBOOKS` = **5 entrées** sur ~25 concrets natifs |
| `UnitEffects{Adjacent,Surrounding,Ranged}(10/11/12)` | Σ des poids BC des EFFETS portés par les amis du voisinage de la tuile | portées, mais `meta.neighbor_effect_names` **plombée par AUCUN appelant** |

---

## 2. La mesure — décomposition par étage, jamais un scalaire

`probe_r1b_native_sweep_order.py` (étendu ici) arme les hooks existants de `scorer-damage-trace` le
temps d'**un** `aiStepDryRun` et rend, par tuile candidate : le **total** `Tile(7)`
(`scorerTileTermTraceDump`), la feuille **Elevation** (`scorerElevTraceDump`) et la feuille
**TileEffects** (`scorerLeafTraceDump`). Le résidu est donc **isolé**, pas déduit :

```
X = Tile(7) - Elevation - TileEffects
```

### 2.1 `C4_09`/999 pas 14 — u98 `templAncient`, origine (5,5)

Amis VIVANTS : u94 (3,4), u96 (6,3). *(u100 et u102 sont des CADAVRES — `decisionView` les garde ;
c'est `alive` qui tranche, et l'ignorer envoyait le diagnostic dans le mur.)*

| tuile | Tile(7) | Elevation | TileEffects | **X** | amis vivants à ≤2 | self à ≤2 |
|---|---|---|---|---|---|---|
| (5,5) | 35 | 20 | 0 | **15** | 2 | oui |
| (5,6) | 34 | 20 | +9 | **5** | 0 | oui |
| (6,4) | 40 | 30 | 0 | **10** | 1 | oui |
| (4,4) | 45 | 30 | 0 | **15** | 2 | oui |
| (4,3) | 10 | 20 | −25 | **15** | 2 | oui |
| (3,5) | 49 | 30 | +9 | **10** | 1 | oui |
| (3,6) | 40 | 30 | 0 | **10** | 1 | oui |
| (5,3) | 35 | 20 | 0 | **15** | 2 | oui |
| (3,3) | 35 | 30 | 0 | **5** | 1 | non |
| (2,4) | 35 | 30 | 0 | **5** | 1 | non |
| (2,6) | 20 | 20 | 0 | **0** | 0 | non |

`X = 5 × (amis vivants à ≤ 2 hex de la tuile, **le mover COMPRIS**)` — **11 tuiles / 11, exact.**

### 2.2 `C4_09`/31337 pas 22 — u84 `admecMarshall`, origine (4,5)

Amis vivants : u86 (3,4), u88 (4,4), u90 `eldarAutarch` (3,3), u92 (2,6). u90 porte l'effet
`PathOfCommand_ExtraDmg`.

| tuile | Tile(7) | Elev | TileEff | **X** | 5 × amis ring-1 (centre exclu, self compris) | +10 si u90 à ≤2 |
|---|---|---|---|---|---|---|
| (4,5) | 10 | 30 | −25 | **5** | 5 | 0 |
| (5,6) | 9 | 20 | −16 | **5** | 5 | 0 |
| (5,5) | 5 | 20 | −25 | **10** | 10 | 0 |
| (3,6) | 40 | 30 | 0 | **10** | 10 | 0 |
| (5,4) | 10 | 20 | −25 | **15** | 5 | +10 |
| (4,3) | 20 | 20 | −25 | **25** | 15 | +10 |
| (2,5) | 35 | 30 | 0 | **5** | 5 | 0 |
| (2,4) | 45 | 30 | 0 | **15** | 5 | +10 |
| (1,5) | 20 | 20 | 0 | **0** | 0 | 0 |
| (1,6) | 25 | 20 | 0 | **5** | 5 | 0 |

**10 tuiles / 10, exact**, avec DEUX termes distincts qui s'additionnent.

### 2.3 GÉNÉRALISATION — `C3_01`/777 pas 14, roster CRAFTÉ, **autre board**

Pour sortir le résultat du seul `C4_09`, un troisième montage est **fabriqué** :
`--p-units templAncient,ultraApothecary,astraCreed,templChampion,tauDarkstrider` sur `C3_01`/777,
où `templAncient` (u87, origine (2,3)) attaque au pas 14. Amis vivants : u89 (2,4), u91 (2,2),
u93 (3,6).

| tuile | Tile(7) | Elev | TileEff | **X** | amis vivants ≤2 | self ≤2 | 5 × total |
|---|---|---|---|---|---|---|---|
| (3,5) | 45 | 30 | 0 | **15** | 2 | oui | 15 |
| (4,5) | 40 | 30 | 0 | **10** | 2 | non | 10 |
| (5,5) | 25 | 20 | 0 | **5** | 1 | non | 5 |

**3 / 3, exact**, sur une géométrie entièrement différente — et c'est bien la tuile de X maximal,
(3,5), que le natif joue. La contribution de `self` bascule ici sur la seule tuile à d(origine) ≤ 2,
ce qui re-teste précisément le point le moins intuitif du §3.1.

---

## 3. Ce que le décompilé dit — et qui prédit la mesure

### 3.1 `AstartesBannerPlaybook` (couple 1)

`IdunBattle.AI.Playbook.Loki.AstartesBannerPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

```csharp
tile  = UtilityAttackCase.get_CasterTile(kase);
range = AbilityConfiguration.GetNumberConstant(config, 0x16);        // "range" = 2 (gameconfig)
units = IBattleQuery.<slot 0x74>(tile, range, kase.unit, true);      // GetSurroundingFriends
yield Fix64.FromInt( config["AstartesBanner_NearbyFriend"] * units.Count );   // 5 (BC)
```

Trois points que la mesure confirme et qu'aucune intuition ne donne :

1. **Le mover se compte lui-même.** Le corps ne contient **aucun** test `!= kase.unit`. Or son
   jumeau `FirstAmongTraitorsPlaybook` — même slot 0x74, même forme — écrit ce test
   EXPLICITEMENT (`if (u != kase.unit && HasTrait(u, 0x7ea))`). L'asymétrie est la preuve : la
   query ne retire pas l'unité, seulement les ENNEMIS (`GetSurroundingUnits` →
   `UnitExtensions.IsEnemy`). Et pendant tout le sweep l'unité est encore **sur son origine** :
   elle compte donc dès que son origine tombe dans le disque de la tuile candidate. C'est
   *exactement* la colonne « self à ≤2 » du §2.1, et c'est ce qui rend le terme
   **position-dépendant** au-delà du simple voisinage.
2. **Le dernier argument `true`** est le flag `includeCenterTile` de
   `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` : l'ami
   DEBOUT SUR la tuile candidate compte (mesuré : (6,4), occupée par un allié).
3. **Le voisinage est un disque cube pur, sans porte d'élévation.** L'itérateur énumère
   `for x in cx±R: for y in cy±R: for z in cz±R: if (x+y+z == 0)` puis `ToAxialCoordinate` +
   `GetTileEntityAt` ; le `abs(elev(a) − elev(b)) < 2` d'`IterateAdjacentTiles` **n'y est pas**.

### 3.2 `KardiocoreGalvanusPlaybook` + `UnitEffectsRangedUtility` (couple 2)

`IdunBattle.AI.Playbook.Loki.KardiocoreGalvanusPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

```csharp
tile  = UtilityAttackCase.get_CasterTile(kase);
units = IBattleQuery.<slot 0x82>(tile, kase.unit);                   // GetAdjacentFriends
foreach (var u in units) val += config["KardiocoreGalvanus_LikesAdjacentMechanicalFriends"];  // 5
yield Fix64.FromInt(val);
```

**Aucun filtre** : ni `HasTrait(Mechanical)`, ni `!= kase.unit`. Le nom de la clé BC décrit
l'EFFET de la relique (« +Crit Damage pour chaque unité **Mécanique** amie adjacente ») ; l'utilité
d'IA, elle, compte **tous** les amis adjacents. Mesuré et assumé : en (4,3), les 3 amis comptés sont
`custoBladeChampion` / `bloodMephiston` / `eldarAutarch`, **aucun** Mécanique.

`KardiocoreGalvanus` est une **RELIQUE**, pas un passif de kit : elle est ABSENTE de
`gameconfig.passiveAbilities`. Le natif, lui, itère l'`AbilitiesComponent` ECS (passifs + abilities
accordées par TRAIT + reliques). C'est le second trou, et il est **de source**, pas de formule.

`IdunBattle.AI.Utilities.UnitEffectsRangedUtility$$GetSourceUnits` =
`IdunBattleLogic.Entities.DSLFactory$$SurroundingFriends(…, 2, 1, 3)` **MINUS** le sélecteur de
l'unité (`IdunBattle.DSL.TargetsSelector$$op_Subtraction`) — disque r=2, self EXCLU. Le corps
partagé `AUnitEffectsUtility.<EvaluateMovementInSteps>d__1$$MoveNext` prend ensuite, pour chaque
unité source, chaque effet de son `EffectsOwnedComponent`, son `EffectType.ToString()`, et somme
`HasUtilityValue(nom) ? GetUtilityValue(nom) : 0`. Les deux sœurs :
`UnitEffectsAdjacentUtility` = `AdjacentFriends(…, 1)` (ring-1, porte d'élévation), et
`UnitEffectsSurroundingUtility` = `SurroundingFriends(…, 1, 1, 3)` (disque r=1).

---

## 4. Ce qui a été porté

| Fichier | Contenu |
|---|---|
| `engine/playbook/friends_in_range.py` (**neuf**) | `AstartesBannerPlaybook` (1106) et `KardiocoreGalvanusPlaybook` (1457) — deux corps PROPRES, pas la famille `AdjacentUnitPreference` |
| `engine/playbook/adjacent_unit_preference.py` | les deux entrent dans `TRIGGERED_MOVE_PLAYBOOKS` (5 → 7) |
| `engine/battle_query.py` | `is_surrounding` / `count_surrounding` — mirror de `TileQuery.<IterateSurroundingTiles>d__6` (disque cube, `includeCenterTile`, **pas** de porte d'élévation) |
| `engine/utilities/tile.py` | `tile_leaf_ctx` : clé `self_pos` (l'origine du mover, indispensable au « self se compte ») + UNION du kit déclenché gameconfig avec la lecture LIVE ; `_adjacent_units` remonte les `effects` ; `apply_tile_attributes` plombe enfin `neighbor_effect_names` (feuilles 10/11/12) |
| `engine/ai/context.py` | `AiDecisionContext.live_triggered_ability_ids(uid)` — lecture du `TriggeredAbilityComponent` via le RPC **existant** `unitAbilityStates`, cache par `(rid, uid)`. C'est la source du dispatcher natif ; le gameconfig ignore traits et reliques |

**UNION et pas remplacement** pour le kit : une lecture live partielle ne peut jamais RETIRER un id
que le port évaluait déjà (les 5 playbooks historiques restent servis par gameconfig).

⚠ **Le RPC `unitAbilityStates` ne NOMME PAS le type déclenché.** Il expose `level`, `mult` et un
`raw` de 12 int32 lus à partir de `TriggeredAbility+0x10` ; l'id est **`raw[0]`** (le champ
`AbilityName`). La base est vérifiable par recoupement : `level`/`mult`, exposés séparément depuis
`+0x20`/`+0x24`, retombent exactement sur `raw[4]`/`raw[5]`. Mesure de contrôle sur `C4_09`/31337 —
u84 `admecMarshall` = `[1200 ControlEdict, 1457 KardiocoreGalvanus, 1201]`, u94 `ultraCalgar` =
`[1014 RitesOfBattle, 1186, 1024]`, u96 `spaceStormcaller` = `[1194 LordOfTempests, …]` : chaque
`raw[0]` retombe sur le passif gameconfig connu, **plus** ce que le gameconfig ignore.

**C'est le test de SOURCE qui a attrapé la première version.** Avec un parsing sur une clé `type`
inexistante, `live_triggered_ability_ids` rendait `[]` en silence — et la suite passait quand même
au VERT, parce que sur ce couple `UnitEffectsRanged` suffisait à casser le tie et à retrouver la
tuile native. Le playbook `KardiocoreGalvanus` était donc enregistré et **jamais appelé** : un port
spéculatif, vert par coïncidence. `test_kit_source_carries_the_triggered_ability` existe pour ça.

**Ce qu'on ne fusionne PAS** : cette famille diffère d'`AdjacentUnitPreference` sur **deux** axes à
la fois (self compté / self exclu, disque cube sans porte / ring-1 avec porte). Les fusionner
casserait `GuardianOrganism` et `RitesOfBattle`, validés exacts par le case-36 et le case-49.

---

## 5. Validation

### 5.1 Arithmétique par tuile, contre la mesure native

Les deux corps portés reproduisent **exactement** le résidu isolé au §2 : **11/11** tuiles sur
`C4_09`/999 pas 14 (AstartesBanner), **10/10** sur `C4_09`/31337 pas 22 (KardiocoreGalvanus, une
fois les +10 d'`UnitEffectsRanged` retirés) et **3/3** sur `C3_01`/777 pas 14 (autre board, roster
crafté). Aucune constante n'a été cherchée : les deux poids (5 et 5) et le rayon (2) sortent de la
BC et du gameconfig, lus AVANT la mesure.

### 5.2 Garde vue ROUGE avant le fix

`tests/engine/test_tile_term_triggered_playbooks_live.py` (4 tests × 3 montages), sur la fixture
partagée `tests/engine/_move_tile_sweep_order.py` (étendue d'un champ `tile_terms`). Mutation
adversariale = **retirer les 2 playbooks du registre + rendre `neighbor_effect_names` muette** (le
comportement d'avant ce commit) → **4 failed / 2 passed**. Messages VERBATIM :

```
AssertionError: pas 14 (templAncient) : TIE ARTEFACT sur [(6, 4), (4, 4)] a u=192.8506 -- le natif
separe ces tuiles, le port les egalise : un terme de Tile(7) manque. Tile(7) du port = {(5, 5):
20.0, (5, 6): 29.0, (6, 4): 30.0, (4, 4): 30.0, (4, 5): 30.0, (5, 7): 29.0, (4, 3): -5.0, (3, 5):
39.0, (3, 6): 30.0, (5, 8): 29.0, (4, 7): 30.0, (5, 3): 20.0, (3, 3): 30.0, (2, 4): 30.0, (2, 6): 20.0}
```

```
AssertionError: pas 22 (admecMarshall) : TIE ARTEFACT sur [(3, 6), (2, 5), (2, 4)] a u=58.7948 --
le natif separe ces tuiles, le port les egalise : un terme de Tile(7) manque. Tile(7) du port =
{(4, 5): 5.0, (5, 6): 4.0, (5, 5): -5.0, (3, 6): 30.0, (5, 4): -5.0, (4, 3): -5.0, (2, 5): 30.0,
(2, 4): 30.0, (1, 5): 20.0, (1, 6): 20.0, (2, 7): 20.0, (1, 7): 19.0}
```

```
AssertionError: pas 14 (templAncient) : le port retient la tuile (6, 4), le natif joue (4, 4).
Tile(7) du port = {…} ; action_tiles=[(5, 5), (5, 6), (6, 4), (4, 4), …]
```

```
AssertionError: pas 22 (admecMarshall) : le port retient la tuile (3, 6), le natif joue (2, 4).
Tile(7) du port = {…} ; action_tiles=[(4, 5), (5, 6), (5, 5), (3, 6), …]
```

Les deux valeurs de tie — **192.8506** et **58.7948** — sont *exactement* celles que la fiche R1-b
avait relevées : le montage reproduit bien l'artefact qu'il prétend supprimer.

Sans mutation : **6 passed**.

### 5.3 Effet de bord ASSUMÉ sur les gardes R1-b

`tests/engine/test_move_tile_sweep_order_live.py` passe de **5 passed / 1 skipped** à
**3 passed / 3 skipped**. Ce n'est pas une régression : le montage `C4_09`/999 pas 14 **n'a plus de
tie** —

```
SKIPPED tests/engine/test_move_tile_sweep_order_live.py:75: pas 14 sans tie (1 tuile(s) a
l'utilite max) -- ne departage aucun ordre
```

— et ce tie était précisément l'ARTEFACT que ce commit supprime (la fiche R1-b le disait déjà :
« le tie 192.851 est un artefact du port »). Le keep-first de `Bucket$$AddAction` **reste gardé**
par l'autre montage (`C4_09`/4242 pas 15, tie réel sur `[(6,4),(4,4)]`, test 2 vert). Ce qui est
perdu, c'est le montage DISCRIMINANT (ordre `ranked` ≠ ordre `action_tiles` sur les tuiles à
égalité) : le ré-étalonner demande de trouver un pas portant un tie NATIF, et c'est un travail à
part.

### 5.4 Non-régression — `ab_tile_tgt` sur 13 couples

`probe_r1b_move_tile_order.py`, colonne `ab_tile_tgt` = « (ability, cible, tuile) == natif », la
métrique que la fiche R1-b avait vue passer de **140** à **138** en imposant l'ordre natif. Les
douze premières lignes « avant » sont la table §6.2 de `case-r1b-move-tile-sweep-order.md`
(mêmes couples, mêmes dénominateurs) ; la treizième a été **re-mesurée** ici (la table R1-b l'avait
prise sur une marche plus courte : 7/9).

| board / seed | avant | après | Δ |
|---|---|---|---|
| `MC1_67`/777 | 14/20 | 14/20 | — |
| `MC1_67`/2468 | 9/15 | **10/15** | **+1** |
| `MC1_67`/999 | 13/17 | 13/17 | — |
| `C3_01`/31337 | 9/14 | 9/14 | — |
| `C3_01`/999 | 11/20 | **12/20** | **+1** |
| `C4_09`/999 | 10/20 | **12/20** | **+2** |
| `C4_09`/4242 | 7/16 | 7/16 | — |
| `C4_09`/1234 | 14/19 | 14/19 | — |
| `C4_09`/31337 | 9/16 | **10/16** | **+1** |
| `C4_09`/777 | 14/20 | 14/20 | — |
| `C4_02`/4242 | 9/17 | 9/17 | — |
| `C4_02`/999 | 12/19 | 12/19 | — |
| `MC1_44`/555 | 9/11 (re-mesuré) | 9/11 | — |
| **total** | **140/224** | **145/224** | **+5** |

**Zéro régression, +5 chunks.** Les **deux** chunks que R1-b avait échangés contre le mirror
(`C4_09`/999 et `C4_09`/31337) sont regagnés — et cette fois pour la raison mécanique, pas par la
coïncidence du proxy `ranked`. Les **trois autres** (`MC1_67`/2468, `C3_01`/999, et le second de
`C4_09`/999) sont des gains de GÉNÉRALISATION : ils tombent sur des couples qu'aucune des deux
mesures fondatrices n'exerçait.

Effet visible sur les ties : `C4_09`/999 ne porte plus qu'**1 pas à égalité sur 25** (la fiche
R1-b comptait **50 pas à tie** sur les 13 couples).

Le « avant » de `MC1_44`/555 a été mesuré en restaurant les 5 fichiers moteur au commit de base
(`git checkout <merge-base> -- engine/…`), pas en supposant.

---

## 6. Ce qui n'est PAS couvert

- **77 playbooks de mouvement restants — le gisement est BEAUCOUP plus gros que ne le disait
  l'estimation « ~25 » de `adjacent_unit_preference.py`.** Compte **re-dérivé du binaire** :
  `search_symbols_by_name("Playbook\$\$CalculateMovementUtilityInStepsInternal")` rend **84** corps
  concrets (60 + 24 en pagination) ; le registre du port en couvre **7**. Tous ne sont pas
  contributifs (`ControlEdictPlaybook` yield `Fix64.FromInt(0)`), mais chacun est un terme
  potentiel du `Tile(7)` de son porteur. La cause racine N13 est **nommée et outillée** ; elle se
  re-manifestera sur tout porteur dont le playbook n'est pas porté. Côté config :
  `Utilities.Default.TriggeredAbilities` a **107 clés**.
- **Le kit déclenché OFFLINE.** `engine/ai/state_bridge.py` (la voie qui joue réellement en
  self-play/RL) construit ses unités depuis l'ECS simulé et n'expose PAS les abilities déclenchées :
  `live_triggered_ability_ids` n'existe que sur le contexte LIVE. Un porteur de RELIQUE reste donc
  muet côté offline. **Résidu de source, pas de formule** — le porter demande de remonter le kit
  déclenché dans le bridge.
- **`TriggeredAbilitiesNonOwner(4)` et `UnitSpecificBehaviours(3)`** restent à `None` : aucune des
  deux mesures ne les a vus contribuer (aucune unité des deux rosters ne porte une des 25 clés
  NonOwner ni une des 3 clés UnitSpecificBehaviours).
- **La prédiction de DÉGÂT par position** (`C4_09`/31337 pas 22 : 82.78 en (2,4) contre 28.79
  ailleurs, soit ~54 points hors terme de tuile) — c'est un **autre** résidu, sur l'axe dégât. Il ne
  flippe pas l'argmax de ce pas (le Tile(7) corrigé suffit), mais il n'est pas expliqué ici.
- **Les 2e/3e littéraux de `DSLFactory.SurroundingFriends(…, R, 1, 3)`** ne sont pas résolus ; le
  voisinage MESURÉ (disque plein, self exclu) suffit à reproduire les deux couples.
- **La porte d'élévation de `KardiocoreGalvanus`** : le port applique `battle_query.is_adjacent`
  (donc `|Δelev| < 2`, le gate inconditionnel d'`IterateAdjacentTiles` — le décompilé fait foi),
  mais **aucun couple mesuré ne l'exerce** : sur les 10 tuiles du couple 2, aucune paire
  (tuile, ami) n'a un écart d'élévation ≥ 2. Le choix est donc fidèle au décompilé, pas confirmé
  par la mesure. `AstartesBanner`, lui, n'a PAS de porte (disque cube pur) — et là c'est mesuré,
  puisque (4,3) elev 2 compte u96 depuis une tuile elev 3.
- **Les caps** `vtbl+0x228/0x238` de la famille `AdjacentUnitPreference` — inchangés, toujours non
  répliqués (aucun cas ne les montre saturer).

---

## 7. Reproduire

```
cd scripts/python
python probe_r1b_native_sweep_order.py --seed 999   --board C4_09 --step 14   # X par tuile + voisinage
python probe_r1b_native_sweep_order.py --seed 31337 --board C4_09 --step 22
python -m pytest tests/engine/test_tile_term_triggered_playbooks_live.py \
                 tests/engine/test_move_tile_sweep_order_live.py \
                 tests/engine/test_playbook_live.py tests/engine/test_stay_in_place_live.py
```

⚠ `probe_r1b_native_sweep_order.py` arme des hooks **RVA build-spécifiques** (`gqfc5mff6c`) : il
vérifie le hash, arme pour UN `aiStepDryRun`, et désarme (`scorerDamageTraceOff`) en `finally`.
