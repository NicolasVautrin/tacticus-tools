# #442 — `TargetIsNotSteppable` : la règle du DECOY, armée par défaut chez 83 abilities

**Livré le 2026-08-01.** Build de référence : `rnca9r7q6c`. Deuxième tranche du gisement de #429.

## 1. La règle, relue verbatim

`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge **7 arguments**), juste
après `TargetIsTargetable` et **avant** les règles `TargetHasNTiles`, donc avant le volet PORTÉE :

```
if ((rules >> 0x33 & 1) == 0) {                      // bit 51 TargetIsNotSteppable NON posé
    if (TargetingOptions.get_IsUnitTargeting(options)) {
        if ((rules & 0x100000) == 0) goto TEST;      // !AllowSteppableUnit (bit 20)
    }
} else {
TEST:
    if (TileExtensions.HasSteppableUnit(puVar12, state)) -> broken(0x8000000000000);
}
```

**Deux armements, et le second est tout le gisement.** Compte re-dérivé du registre (103 masques
lisibles) : **1** ability pose le bit 51 — `1011 TunnelingHorror`, TILE-targeting — et **82**
arment la règle par `get_IsUnitTargeting`, qui n'est pas un bit à elle mais l'**ABSENCE** des bits
6/44/46, donc vraie par défaut. Total **83**. L'**ATTAQUE NORMALE** en fait partie (preset `0x4002`,
aucun bit de domaine) : *on ne peut pas attaquer normalement une unité `Steppable`*.

**L'ordre des trois gates n'est pas commutatif** : le bit 51 est testé **en premier** et branche
directement sur le prédicat (`else: goto TEST`). `AllowSteppableUnit` ne désarme donc **que** la voie
unit-targeting — une ability qui pose le bit refuse même avec le bit 20. **0** ability du registre
pose le bit 20.

Le prédicat, `IdunBattle.Entities.TileExtensions$$HasSteppableUnit(tile, matchState)` :

```
u = UnitExtensions.GetUnit(tile, matchState);   if (u == null) return false;
b = UnitExtensions.GetBaseUnitComponent(u);     if (b == null) return false;
return BaseUnitComponent.HasTrait(b, 0x1b);     // UnitTrait.Steppable
```

Son nom dit « tile » mais son argument est `GetUnit`-é, et la cascade lui passe `puVar12`, la cible
**résolue** par la tête de domaine — une UNITÉ sur une ability unit-targeting, une TUILE sous
`TargetIsTile`. `GetUnit` couvre les deux (sur une tuile il rend son occupant) : le port emploie donc
`unit_of_entity`, et surtout pas `_unit_of` (qui raterait le cas TUILE).

⚠ **Cette règle précède `TargetTileIsFree` (bit 12), et ce n'est pas cosmétique** : le natif appelle
`IsFreeTile(tile, state, allowSteppable: 1, ...)`, donc une tuile portée par une unité `Steppable`
est « libre » pour le bit 12. Chez 1011, qui porte les deux bits, c'est bien 51 qui refuse la tuile
d'un decoy, jamais 12.

## 2. Qui écrit l'état que la règle lit — la question de #436, et sa réponse est différente

Pour le TAUNT, la liste interrogée n'était écrite par personne côté port : le gate était vert et
vide. Ici l'état est un **TRAIT** (`UnitTrait.Steppable` = 0x1b), pas un effet — personne n'a à
l'« écrire », il arrive avec l'unité. **Deux canaux, mesurés séparément et REDONDANTS** :

| canal | quand | mesuré par |
|---|---|---|
| `snapshot._load_unit_traits` (#264) — `combatSnapshot.units[].traits`, une mesure de `UnitExtensions$$HasTrait` | état RECHARGÉ | étage A |
| `UnitContext.from_snapshot` / `build_decoy_context` / `build_summon_context` — `traits` gameconfig par `visualId` | repli, et unité SPAWNÉE par le port | contre-épreuve CE3 |

**CE3 (mesurée)** : `_load_unit_traits` neutralisé en no-op → l'étage A reste **VERT** et l'accord
reste 18/18. Le repli gameconfig suffit. Ce vert-là n'est pas une garde inerte, c'est une
**redondance** — et CE4 le prouve en purgeant `Steppable` des deux canaux à la fois : l'étage A passe
alors à `0 entité Steppable` et **ROUGIT**, l'accord tombe à 10/18.

Aucune pièce manquante à livrer, donc, contrairement à la tranche 1.

## 3. Gate de confrontabilité — 27 porteurs, dont 2 summons joignables

Porteurs du trait `Steppable` au gameconfig, re-dérivés (`lineup`/`npc`/`summons`) : **27** — **25
npc** (loot `LootObj_*`, les 15 `powup*`, `astarNpc1HaywireMine`, `genesDecoy`) et **2 summons** :

* **`genesSmnDecoy`** — posé par `CultDemagogue` (**1179**), ability ACTIVE **portée**, dont le
  porteur `genesPrimus` est **au pool**. C'est le montage retenu : il en pose N à volonté.
  Deuxième poseur, non piloté : la passive `Ambush_Summon`, à la mort de tout porteur du trait
  `Ambush`. Mesuré : **un decoy préexistait** au montage, avant tout cast.
* **`astarSmnHaywireMine`** — posé par la passive `HaywireMine` d'`astarCyrus`, **hors pool**
  (injection catalogue nécessaire). Non joué : le premier suffit et se pilote.

## 4. La confrontation — `probe_442_steppable_targeting.py`, quatre étages

Montage : `genesPrimus` amené au **contact** d'un `necroWarden`, puis `CultDemagogue(1179)` sur lui —
les decoys se posent sur les tuiles libres à ≤ 2 hex de la **cible**, donc au contact de celle-ci. Le
`necroWarden` est ensuite l'**attaquant** mesuré : les decoys sont ses ennemis (ils héritent de
l'owner du caster) et son attaque normale arme la règle.

| cible | d | natif | port | portAvant (bit 20) |
|---|---|---|---|---|
| `necroWarden` (allié, et soi) | 0 / 2 | `0x4000` | `0x4000` | `0x4000` |
| `genesSmnNeophyte` (ennemi non-Steppable, à portée) | 2 | `0x0` | `0x0` | `0x0` |
| `genesSmnDecoy` à d=1 | 1 | **`0x8000000000000`** | **`0x8000000000000`** | **`0x0`** |
| `genesSmnDecoy` à d=5, 6, 10 | — | `0x8000000000000` | `0x8000000000000` | `0x8000000` |

Accord natif/port **18/18**, **5** lignes refusées `TargetIsNotSteppable`, dont **1** que le port
acceptait avant la tranche (`0x0`), et **3** lignes acceptées — la mesure discrimine.

**La ligne à d=10 est une preuve d'ORDRE, mesurée in vivo** : le natif y rend `0x8000000000000` et
non `TargetIsInRange`, ce qui confirme que la règle 51 précède le volet portée. C'est aussi
pourquoi une seule des cinq lignes montre la dégradation permissive : les quatre autres decoys sont
hors portée, donc `portAvant` y rendait déjà `TargetIsInRange`.

Les étages :

* **A — SUBSTRAT** : les 5 decoys de l'état rechargé portent `Steppable` (§2).
* **B — LA RÈGLE** (live) : le tableau ci-dessus.
* **C — DÉSARMEMENT** `AllowSteppableUnit` (bit 20) posé sur le masque : 5/18 lignes basculent, et
  **uniquement** celles refusées par la règle 51. **NON CONFRONTÉ** au natif : 0 porteur du bit au
  registre, aucun cast live ne l'exerce.
* **D — LA VOIE DU BIT 51** (offline) : une ability qui pose le bit refuse **malgré** le bit 20
  (5/5), et refuse aussi en mode TILE-targeting sur la **tuile** du decoy (5/5) — le régime de 1011.
  **NON CONFRONTÉ** au natif : voir §6.

Garde : `tests/engine/runner/test_steppable_targeting_live.py` (8 tests, ~74 s).

### Généralisation

Même verdict sur un montage **entièrement différent** — autre board (`C4_09`), autre seed (`31337`),
autre attaquant (`deathBlightlord`, Death Guard, mêlée), **et une ability ACTIVE** au lieu de
l'attaque normale (`1042 FlailSwing`, masque `0x4000`) : accord **18/18 sur les deux abilities**,
4 refus `TargetIsNotSteppable` chacune, dont 1 que le port acceptait avant.

```
python scripts/python/probe_442_steppable_targeting.py --seed 31337 --board C4_09 \
    --a-units "deathBlightlord,deathBlightlord,necroWarden,necroWarden" \
    --victim-vis deathBlightlord --extra-ability 1042
```

### Quatre contre-épreuves, chacune vérifiée mordante

| # | mutation | attendu | mesuré |
|---|---|---|---|
| CE1 | la règle neutralisée (`if False and …`) | rouge | **4 rouges** (accord, désarmement, voie du bit, verdict) |
| CE2 | `has_steppable_unit` → `return False` | rouge | **4 rouges**, étage A **vert** — A et B mesurent bien deux choses distinctes |
| CE3 | `_load_unit_traits` → no-op | ? | **VERT** — redondance des deux canaux de substrat (§2) |
| CE4 | `entity_trait_names` purgé de `Steppable` (les deux canaux) | rouge | étage A **rouge**, accord 18/18 → **10/18** |

Les tests restés verts sous CE1/CE2 portent sur le NATIF (`le natif refuse bien …`) et sur la
baseline (`la ligne refusée était acceptée par le port avant`), pas sur le port courant — c'est
attendu, et c'est `test_accord_natif_port_sur_toutes_les_lignes` qui garde le port.

## 5. Ce que la tranche change pour le reste du moteur

La règle est armée pour **83** des 103 masques lisibles **et pour l'attaque normale**, donc pour
`valid_normal_attack_targets` et tout ce qui en dépend. Un decoy / une mine / un power-up n'est plus
une cible légale. Les 16 fichiers de test rejoués (§7) couvrent les consommateurs : gate de cible,
masques, taunt (#436, même cascade), decoys (fondation, CultDemagogue, misdirection, hypersensory),
tuiles Steppable, summons, splash, attaque, choix de cible IA. Aucun n'a bougé.

## 6. Résidus nommés

* **La voie du BIT 51 est NON CONFRONTÉE au natif.** Son unique porteur, `1011 TunnelingHorror`, n'a
  que des npc (`necroNpc4Destroyer*`) et le summon **`necroSmnDestroyer`**, qui est un summon
  d'**ENVIRONNEMENT** (`EnvFactionSummons:Necrons`, `nrOfSummons: 2`) — posé par le BOARD, sans
  aucun summoner d'unité. La greffe (#92 §5bis) ne s'applique pas : `catalog_inject` ne greffe que
  les abilities **passives**, et `abilityReason` exige que le caster POSSÈDE l'ability. Le montage
  qui fermerait ce résidu : faire entrer `necroSmnDestroyer` au catalogue comme unité régulière
  (`write_augmented_seed_bc`), ou un board qui pose ses `EnvFactionSummons` — non tenté. La voie
  est confrontée OFFLINE (étage D) et le mirror est verbatim.
* **`AllowSteppableUnit` (bit 20) non confronté** — 0 porteur au registre (§4, étage C).
* **`astarSmnHaywireMine` non joué** : second summon `Steppable`, poseur `astarCyrus` **hors pool**
  (injection catalogue requise). Le régime est le même que celui du decoy ; rien n'indique un écart.
* **Les 25 npc `Steppable`** (loot, power-ups) ne sont pas dans un duel `rl_duel build` : leur
  régime est celui de l'étage B, par le même prédicat, mais n'a pas été observé.

## 7. Ce qui a été joué (relevé daté, AVANT rebase)

`test_steppable_targeting_live` 8 ✅ · `test_ability_target_gate_live` 13 ✅ ·
`test_taunt_targeting_live` 7 ✅ · `test_targeting_masks_live` 13 ✅ ·
`test_decoy_foundation_live` 3 ✅ · `test_cultdemagogue_migration_live` 6 ✅ ·
`test_decoys_misdirection_migration_live` 3 ✅ · `test_hypersensory_moveandspawndecoy_live` 5 ✅ ·
`test_steppable_decoy_tile_leaves_live` 14 ✅ · `test_summon_targeting_live` 6 ✅ ·
`test_splash_targeting_live` 10 ✅ · `test_runner_attack_live` 2 ✅ ·
`test_targeting_rule_inventory` 17 ✅ · `test_targeting_options_sources` 5 ✅ ·
`test_ability_target_gate_lot181_live` 26 ✅ · `test_ai_target_choice_live` 2 ✅
— et la **banque de cliquets VERTE** (`scripts/ratchets.ps1`, 22 cliquets, mur 127,2 s).

Audits régénérés (`audit_kit_coverage.py`, `audit_combat_ability_coverage.py`) : **inchangés** —
cette tranche ne porte aucune ability, elle porte une règle de la cascade.

**Re-jeu APRÈS rebase sur `origin/master`** (branche repartie de `dca7fa73`, soit 4 commits
entre-temps — #441 `Neuroparasite`, #419-r1 tranche 2) : `test_steppable_targeting_live` 8 ✅ ·
`test_ability_target_gate_live` 13 ✅ · `test_taunt_targeting_live` 7 ✅ ·
`test_targeting_masks_live` 13 ✅ · `test_steppable_decoy_tile_leaves_live` 14 ✅ ·
`test_summon_targeting_live` 6 ✅ · `test_cultdemagogue_migration_live` 6 ✅ ·
`test_runner_attack_live` 2 ✅ — et la **banque VERTE, 24 cliquets, mur 96,2 s** (elle en comptait
22 avant le rebase : deux entrées sont arrivées avec les merges).

## 8. Re-dériver

```
python scripts/python/probe_442_steppable_targeting.py
python scripts/python/probe_429_targeting_rule_inventory.py --only-gaps
python -m pytest tests/engine/runner/test_steppable_targeting_live.py -q
```

Après cette tranche, `probe_429` compte **23** règles GATE non portées sur 46 (contre 24), et le
gisement restant est la **ligne de vue** (`TargetIsUnobscured`, 103 abilities, armée par défaut,
aucun bit ne l'arme). ⚠ Chiffres à re-dériver, pas à citer.
