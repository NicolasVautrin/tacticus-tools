# #241 — les deux feuilles de tuile à occupant STEPPABLE : `SteppableUnitUtility` (19) et `AttractToDecoysUtility` (64)

> ⚠ **Collision de numérotation** : `case-241-range-gate.md` occupe déjà le numéro `241` dans
> `docs/rl` (gate de portée d'un cast, cité par `case-115` et `backlog.md`). Le tag `#241` de cette
> fiche est celui du registre de campagne, attribué indépendamment. Les deux cas n'ont aucun rapport ;
> les commentaires de code qui portent `#241` nomment toujours leur sujet, donc l'ambiguïté ne mord
> nulle part — mais elle est signalée ici plutôt que masquée.

Résidu de `case-212` §7.1, entièrement attribué mais laissé ouvert :

> Les deux classes EXISTENT dans `engine/utilities/tile.py` et sont correctes ; elles rendent 0 parce
> que leurs métadonnées par tuile ne sont **jamais posées** par `apply_tile_attributes`. Gap de
> CONTEXTE, pas de feuille.

**Verdict : c'était bien un gap de contexte, et il est fermé — mais la RE a aussi trouvé DEUX
branches de la feuille 19 que le port n'avait pas.** Le résidu de +25 tombe à 0 sur les deux
montages, et deux faits du décompilé que `case-212` ne pouvait pas exercer sont maintenant mesurés.

---

## 1. Réponse à la question binaire

> Quelles opérations natives ÉCRIVENT l'attribut lu par chaque feuille, et sur quel COMPOSANT ?

**Aucune.** Il n'y a pas d'attribut « steppable » stocké sur une tuile, ni de compteur de decoys
posé quelque part : les deux feuilles **calculent** leur donnée à la volée, au moment de
l'évaluation, depuis deux composants ECS existants.

| feuille | ce qu'elle lit | composant natif |
|---|---|---|
| 19 `SteppableUnitUtility` | l'OCCUPANT de la tuile candidate, s'il porte `UnitTrait.Steppable` | `TileContentComponent` (`tile+0x38`) → l'entité, puis `BaseUnitComponent.HasTrait(0x1b)` |
| 64 `AttractToDecoysUtility` | le même occupant (gate) **+** toutes les unités vivantes de la bataille (compte) | idem, **+** `GetAllAliveUnits` (slot **0x88** de l'interface de query) |

C'est pourquoi le port n'avait aucune « clé de contexte de tuile » à recevoir d'un RPC : la donnée se
**dérive** des unités que `leaf_ctx` porte déjà. `apply_tile_attributes` en est le foyer.

---

## 2. Ce que dit le décompilé

### 2.1 `IdunBattle.AI.Utilities.SteppableUnitUtility.u003CEvaluateMovementInStepsu003Ed__10$$MoveNext`

```csharp
Fix64 u = 0;
if (!TileExtensions.GetSteppableUnit(case.position.MainTile, ctx, out u_))  goto done;
string key;
if      (UnitExtensions.HasTriggeredAbility(u_, 0x4d))  key = "SpikyStingOnMovementTile";
else if (UnitExtensions.HasTriggeredAbility(u_, 0x72))  key = "Landmine";
else if (UnitExtensions.HasTrait(u_, 0x41d))                          // UnitTrait.Decoy = 1053
     key = UnitExtensions.IsFriend(u_, case.unit, ctx) ? "FriendlyDecoy" : "EnemyDecoy";
else key = UnitExtensions.IsEnemy(u_, case.unit, ctx)  ? "EnemySteppableUnit"
                                                      : "FriendlySteppableUnit";
u += GetUtilityValue(key);
done: ...
```

**SIX clés, pas quatre.** Les deux premières branches manquaient au port. Elles sont résolues, pas
devinées — `probe_212_bc_key_literals.py --symbol <ce symbole>` rend les six slots :

| slot lu | littéral | BC `Utilities.Default.SteppableUnit` |
|---|---|---|
| `+0x31d0218` | `SpikyStingOnMovementTile` | **ABSENT** |
| `+0x3222d90` | `Landmine` | **ABSENT** |
| `+0x323aa58` | `FriendlyDecoy` | −50 |
| `+0x31f2f90` | `EnemyDecoy` | 1 |
| `+0x31f3480` | `EnemySteppableUnit` | 50 |
| `+0x323ae18` | `FriendlySteppableUnit` | −50 |

Les deux clés absentes rendent **0** (`BaseUtility$$GetUtilityValue` : `TryGetValue` sur le dict
`this+0x58`, échec → log + `Fix64.FromInt(0)` — exactement ce que fait `Weights.sub`). Elles sont
portées quand même parce qu'elles **court-circuitent** : un steppable porteur de
`TriggeredAbilityType.SpikySting` (77) ou `LandMine` (114) vaut **0**, pas −50. Aucune unité du
gameconfig ne porte ces deux abilities (`unit_map.py find --ability SpikySting|LandMine` → 0 unité),
donc la branche est aujourd'hui inatteignable — mais l'omettre aurait été un pari, pas un mirror.

⚠ **Qualification des enums** : `0x4d`/`0x72` sont des `TriggeredAbilityType` (77 `SpikySting`,
114 `LandMine`) et `0x41d` un `UnitTrait` (1053 `Decoy`) — homonymes à écarter : `EffectType` 1053 =
`ShadowInTheWarp_LessDmg_Effect`, `ActiveAbilityType` 1053 = `DevoutPush`, `TriggeredAbilityType`
1053 = `BroodProgenitor`.

⚠ **Le natif n'utilise pas le même prédicat des deux côtés** : `IsFriend` sur la branche Decoy,
`IsEnemy` sur l'autre. `IdunBattle.Entities.UnitExtensions$$IsFriend` et `$$IsEnemy` comparent tous
deux `GetCurrentPlayer(a).id` à `GetCurrentPlayer(b).id` (égal / différent) et rendent **false** si
l'un des deux est nul — ils sont donc complémentaires tant que `case.unit != null`, et seulement
alors. D'où les DEUX booléens `is_friend`/`is_enemy` dans `meta.steppable` plutôt qu'un seul.
(Le régime `case.unit == null` est celui du call-site SUMMON, cf. `case-205` §`SteppableUnit(19)` ;
la face DÉCISION pose `is_spawning: False` et n'y entre jamais.)

### 2.2 `IdunBattle.Entities.TileExtensions$$GetSteppableUnit`

```csharp
unit = UnitExtensions.GetUnit(tile, ctx);                 // TileContentComponent.IsFilled -> l'entité
if (unit != null) {
    bc = UnitExtensions.GetBaseUnitComponent(unit);
    if (bc != null && bc.HasTrait(0x1b)) { out = unit; return true; }   // UnitTrait.Steppable = 27
}
out = null; return false;
```

Le trait qui compte est **`Steppable`, pas `Decoy`** — n'importe quel summon traversable arme la
feuille. Et `GetUnit` ne rend qu'**UNE** entité : une tuile n'a qu'un occupant, il n'y a pas de
« mode d'occupation » à deux occupants à ce niveau.

### 2.3 `IdunBattle.AI.Utilities.AttractToDecoysUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`

```csharp
if (case.unit == null)                                        yield break;
if (!UnitExtensions.HasFaction(case.unit, 0xf))               yield break;   // UnitFaction.Genestealers
if (!TileExtensions.HasSteppableUnit(case.CasterTile, ctx))   yield break;
if (TileExtensions.GetSteppableUnit(case.CasterTile, ctx, out u)
    && UnitExtensions.IsEnemy(u, case.unit, ctx))             yield break;
foreach (v in ctx.GetAllAliveUnits())                                        // slot 0x88
    if (UnitExtensions.IsFriend(v, case.unit, ctx)
        && UnitExtensions.HasTriggeredAbility(v, 0x518))                     // 1304
        yield return GetUtilityValue("DecoysAndMisdirection_FriendlyGSCLikeDecoys");   // 75
```

Trois faits que le nom des clés ne dit pas :

* le gate de tuile porte sur `Steppable`, **pas** sur `Decoy` — et pas non plus sur la faction de
  l'occupant. Il suffit d'un summon steppable **non ennemi** ;
* la boucle n'a **aucun filtre de position**. Le slot 0x88 est identifié par corrélation :
  `IdunBattle.Entities.Selectors.AllAliveUnitsSelector$$Select` l'appelle (le slot 0x87 étant
  `AllUnitsSelector`), et `IdunBattle.AI.Playbook.BasePlaybook$$GetAllEnemies` itère le même 0x88
  avant de filtrer par `IsEnemy` (slot 0x90). C'est donc un compte de **bataille**, pas de
  voisinage — **constant sur la décision**, seul le gate varie par tuile ;
* `IsFriend(v, case.unit)` compare les playerId : **le mover lui-même satisfait le prédicat**. Aucune
  exclusion de self, contrairement aux feuilles `AUnitEffects*` (qui, elles, passent explicitement
  par un `op_Subtraction` du sélecteur de `case.unit`).

`IdunBattle.Entities.UnitExtensions$$HasFaction(unit, <UnitFaction>)` ne compare **pas** un entier :
`System.Enum.ToString(UnitFaction)` puis `String.Equals` contre `FactionComponent+0x30`. La faction
est une CHAÎNE côté natif ; le pendant offline est le `FactionId` du gameconfig.

---

## 3. Ce qui a été câblé

| foyer | ajout |
|---|---|
| `engine/utilities/tile.py::apply_tile_attributes` | `meta.steppable` (via `_steppable_occupant`), `meta.decoy_gate`, `meta.decoy_friend_count` (via `_attract_to_decoys_friend_count`) |
| `engine/utilities/tile.py::tile_leaf_ctx` (face DÉCISION) | `ctx.unit_faction` = `faction_value(visualId)` |
| `engine/utilities/tile.py::build_move_leaf_ctx` (chemin OFFLINE runner) | idem + `id`/`triggered` par unité |
| `engine/utilities/tile.py::_adjacent_units` | `id` + `triggered` (kit gameconfig ∪ lecture live) sur chaque ami/ennemi |
| `engine/utilities/tile.py::SteppableUnitUtility` | les 2 branches court-circuit ; `is_friend` **et** `is_enemy` |
| `engine/entities/unit_faction.py` (**neuf**) | `IdunBattle.Entities.Enum.UnitFaction`, 21 membres transcrits de `data/symbols/<build>/frida/enums.tsv` + `faction_value(visualId)` |
| `engine/entities/triggers.py` | `UNIT_FACTION_NAMES` (8 valeurs, table PARTIELLE) **dérive** du foyer unique — value-preserving |
| `engine/ai/context.py` | `AiDecisionContext.live_triggered_kits()` : UN seul `unitAbilityStates` pour toute la bataille (cache par rid) au lieu de N appels |
| `engine/move.py` | le paramètre **mort** `steppable_by_pos` est supprimé (aucun appelant, et seconde source pour `meta.steppable`) |

Le compte `decoy_friend_count` vit dans le `meta` bien qu'il soit constant sur la décision : c'est
la feuille qui le lit là, et déplacer la clé aurait modifié une signature de feuille correcte pour
un gain nul.

### 3.1 Écart de substrat assumé

`friend_units` ne retient que les amis **vivants ET POSITIONNÉS**, là où `GetAllAliveUnits` ne filtre
que sur la vie. Une unité vivante sans position (non déployée) manquerait au compte. Aucune n'est
observable sur les montages de runner ; c'est le seul écart connu entre le port et la boucle native.

---

## 4. Validation

### 4.1 Le résidu de `case-212`, avant / après

`probe_212_spiritual_leader_tile_term.py` (décomposition `X = Tile(7) − Elevation − TileEffects` sur
les hooks **existants** de `scorer-damage-trace`, armés pour UN `aiStepDryRun` puis désarmés ;
**aucune réinjection**), inchangé :

| montage | `occupant → {X_nat − X_port}` AVANT | APRÈS |
|---|---|---|
| `MC1_67`/777 pas 47 (16 tuiles, 4 à decoy) | `decoy → {25}` · `autre → {0}` | `decoy → {0}` · `autre → {0}` |
| `C4_09`/31337 pas 21 (6 tuiles, 2 à decoy) | `decoy → {25}` · `autre → {0}` | `decoy → {0}` · `autre → {0}` |

**22 tuiles, 2 boards, 0 désaccord.** Les 4+2 tuiles à +25 sont à 0 ; les 18 autres, déjà à 0, y
restent — une pose trop large s'y serait vue.

Le détail par tuile montre aussi que le gate est bien l'**occupant** et non l'adjacence :
`MC1_67` (3,3) et (5,2) ont **0 decoy adjacent** mais portent un decoy, et valent 25 des deux côtés.

### 4.2 Généralisation — les deux faits que `case-212` ne pouvait pas exercer

Le mover de `case-212` (`genesMagus`) ne porte pas 1304 : ni le **self-count** ni l'**absence de
filtre de position** n'y étaient discriminants. `probe_241_decoy_tile_leaves.py` prend le carrier en
paramètre et cherche le pas où une candidate porte un occupant steppable.

`--carrier genesPrimus` (Isaak — **LE** porteur de `DecoysAndMisdirection` 1304 du roster) :

| montage | porteurs de 1304 vus | tuiles à occupant steppable | distances porteur→tuile | désaccord |
|---|---|---|---|---|
| `MC1_67`/777 pas 22 (16 tuiles) | `[('SELF', (3,4))]` | (4,4) (1,5) (2,1) → 25 chacune | **1, 2 et 3** | **0 / 16** |
| `C4_09`/31337 pas 14 (5 tuiles) | `[('SELF', (3,3))]` | (4,4) (5,4) → 25 chacune | 2 et 2 | **0 / 5** |

* **SELF-COUNT prouvé** : le seul porteur de 1304 est le mover lui-même. `X_nat` vaut 25 → le natif
  le compte. Un port qui excluait self aurait rendu −50 (écart +75), pas −25.
* **ABSENCE DE FILTRE DE POSITION prouvée** : sur `MC1_67`, trois tuiles à distance **1, 2 et 3** du
  porteur valent **la même chose**. Aucun voisinage R1/R2 ne produit ça.
* et le tout sur un mover DIFFÉRENT de celui de `case-212`.

### 4.3 Gardes (`tests/engine/test_steppable_decoy_tile_leaves_live.py`, 14 passed)

Deux montages × 6 gardes live + 2 gardes de table de branchement. Aucune valeur gelée : tout est
re-dérivé de la BC et du contexte du pas.

Les gardes live vérifient la faction résolue, la présence des clés BC utilisées **et l'absence des
deux clés court-circuit** (si elles apparaissaient un jour, le port continuerait à rendre 0 pour
elles, ce qui deviendrait faux), que le montage exerce les deux natures de tuile, que les deux
feuilles tirent **exactement** sur les tuiles à occupant steppable ami, et que leur somme vaut
`FriendlyDecoy + n × GSC`.

### 4.4 Contre-épreuves — mutations de mon propre fix

| mutation | résultat |
|---|---|
| pose retirée (`occ = None`) | **4 failed / 8 passed** — le message nomme la valeur attendue (25 = −50 + 75) |
| `ctx.unit_faction = None` | **3 failed / 5 passed** — la somme tombe à −50, donc le message **nomme la feuille qui reste armée** |
| gate `Steppable` retiré (pose trop large) | **12 passed — INOBSERVABLE en live** |

Le troisième cas est le résultat intéressant, et il est **structurel** : les tuiles candidates sont
`[origine] + aiMovableTiles`, et `aiMovableTiles` n'expose que des tuiles libres ou occupées par un
`Steppable` — c'est précisément ce que le trait autorise. Une candidate à occupant **non** steppable
autre que l'origine **n'existe pas**, donc aucun montage ne peut faire tomber cette mutation. D'où
les deux tests de **table de branchement** (offline) : ils ne gèlent aucune mesure, ils gèlent la
structure de branchement lue au décompilé (le filtre `0x1b`, `IsFriend`/`IsEnemy` selon la branche,
les deux court-circuits qui priment sur le trait `Decoy`). Avec eux, la mutation **tombe**.

### 4.5 Non-régression

| suite | résultat |
|---|---|
| `test_spiritual_leader_tile_term_live` + `test_tile_term_unit_gated_playbooks_live` + `test_tile_term_triggered_playbooks_live` | **52 passed** |
| `test_move_tile_sweep_order_live` + `test_stay_in_place_live` | **7 passed / 3 skipped** — mêmes skips que ceux documentés par `case-212` §6.3 (montages sans tie), inchangés |

Runners disposés au fil de l'eau.

### 4.6 ⚠ NON CONFRONTÉ LIVE — différé par la MAJ `gqfc5mff6c` → `rnca9r7q6c`

Un seul point reste ouvert, et il est **hors du chemin modifié** :

* **`tests/engine/test_thrice_blessed_decision_live.py`** (2 tests) n'a pas pu être re-joué. Il
  touche `HasFaction`, dont la table `UNIT_FACTION_NAMES` est passée en dérivée dans ce commit. Le
  run a rougi **pendant la fenêtre d'arrêt du jeu** — le message d'échec porte lui-même la preuve
  (`"running": false, "launcherOnly": true`, `no active Frida session`), donc il ne dit rien du code.
  Le changement est **value-preserving par construction** : les 8 valeurs de l'ancienne table
  (0 `Ultramarines` … 7 `Necrons`) sont identiques dans l'enum, et `HasFaction` ne lit que
  `UNIT_FACTION_NAMES[value]`. **À re-jouer tel quel après la migration de build** :
  `python -m pytest tests/engine/test_thrice_blessed_decision_live.py` (montages `C1_25`/777 et le
  gate munitions), attendu **2 passed**.

Tout le reste de §4.1–§4.5 a été mesuré **avant** l'arrêt, sur `gqfc5mff6c`, cohérent avec le
décompilé et les tables de ce même build. Aucune mesure de cette fiche ne provient d'un build
postérieur.

---

## 5. Résidus

* **Les deux branches court-circuit (77 `SpikySting` / 114 `LandMine`) sont portées mais MUETTES** :
  leurs clés BC n'existent pas (→ 0) et aucune unité du gameconfig ne porte ces abilities. Statut :
  *mirror sans porteur*. Si une BC future introduisait `SpikyStingOnMovementTile` ou `Landmine`, le
  port les lirait correctement — la garde
  `test_bc_keys_are_present_and_shortcircuit_keys_are_absent` échoue exprès dans ce cas, pour forcer
  la relecture plutôt que laisser passer un 0 silencieux.
* **Le régime `case.unit == null` de la feuille 19** (call-site SUMMON `SortTilesByUtilityForSummon`,
  `case-205`) reste non porté : `is_spawning` est `False` sur la face DÉCISION, et
  `_steppable_occupant` suppose un mover. Inchangé par ce cas.
* **`friend_units` = amis vivants ET POSITIONNÉS** vs `GetAllAliveUnits` = vivants (§3.1).
* Les résidus frères de `case-212` restent ouverts : `FabricatorClawArrayPlaybook` (1006) et son cap
  `vtbl+0x228`, `ExplosiveMaladies` (1068), `darkaSmnWatcher`.

## 6. Reproduire

```bash
cd scripts/python
python probe_212_bc_key_literals.py \
    --symbol "IdunBattle.AI.Utilities.SteppableUnitUtility.u003CEvaluateMovementInStepsu003Ed__10\$\$MoveNext" \
    --symbol "IdunBattle.AI.Utilities.AttractToDecoysUtility.u003CEvaluateMovementInStepsu003Ed__1\$\$MoveNext"
python probe_212_spiritual_leader_tile_term.py --board MC1_67 --seed 777 --max-steps 60 --extra \
    --hp-target 100000 --hp-player 100000 \
    --p-units "genesMagus,genesPrimus,genesKelermorph,orksNob,spaceWulfen" \
    --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"
python probe_241_decoy_tile_leaves.py --board MC1_67 --seed 777 --carrier genesPrimus \
    --max-steps 60 --extra --hp-target 100000 --hp-player 100000 \
    --p-units "genesMagus,genesPrimus,genesKelermorph,orksNob,spaceWulfen" \
    --a-units "darkaHellblaster,eldarRanger,worldKharn,templChampion,tauMarksman"
python -m pytest tests/engine/test_steppable_decoy_tile_leaves_live.py
```

⚠ Les deux probes de tuile arment des hooks **RVA build-spécifiques** (`gqfc5mff6c`, hérités de
`probe_193c`) : ils vérifient le hash et **refusent** de tourner sur un autre build. Après la
migration `rnca9r7q6c`, ces RVA sont à re-résoudre avant de rejouer §4.1/§4.2.
