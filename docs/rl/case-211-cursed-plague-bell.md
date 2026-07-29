# case-211 — `CursedPlagueBell` (1071) : le premier playbook de mouvement dont les DEUX faces gatent sur le voisin

Tranche suivante du gisement « playbooks de MOUVEMENT » (case-193c). Le case-193c §7 l'avait mis de
côté avec un avertissement explicite — « pas un simple 3-lignes » — et c'était juste : c'est le
premier concret de la famille `AdjacentUnitPreferenceTriggeredAbilityPlaybook` qui surcharge
**`GetAdjacentFriendUtility` ET `GetAdjacentEnemyUtility`**, et le premier dont un gate lit le
**`WeaponsComponent`** du voisin plutôt qu'un attribut d'unité.

Porteur : `deathBlightbringer` (Corrodius, Death Guard) — **POOL-HERO**, présent tel quel dans
`rl_duel.py build --list-pool` au rank 17.

---

## 1. Le décompilé

`IdunBattle.AI.Playbook.Loki.CursedPlagueBellPlaybook$$.ctor` passe `0x42f = 1071`
(`IdunBattle.Entities.Enum.TriggeredAbilityType.CursedPlagueBell`) à
`IdunBattle.AI.Playbook.AdjacentToOwnerNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor`.

### 1.1 Face AMIS

```csharp
// IdunBattle.AI.Playbook.Loki.CursedPlagueBellPlaybook$$GetAdjacentFriendUtility
if (!UnitExtensions.HasTrait(unit, 0x7ea))                        // UnitTrait.Chaos
    return 0;
return ctx.GetUtilityValue("CursedPlagueBell_AdjacentChaosFriend");   // 20 (BC)
```

### 1.2 Face ENNEMIS

```csharp
// IdunBattle.AI.Playbook.Loki.CursedPlagueBellPlaybook$$GetAdjacentEnemyUtility
var weapons = unit.<WeaponsComponent>.Weapons;                    // List<WeaponProfile>
if (!Enumerable.Any(weapons, this.<GetAdjacentEnemyUtility>b__4_0))
    return 0;
return ctx.GetUtilityValue("CursedPlagueBell_AdjacentPsychicEnemy");  // 10 (BC)

// IdunBattle.AI.Playbook.Loki.CursedPlagueBellPlaybook$$u003CGetAdjacentEnemyUtilityu003Eb__4_0
return w.DamageProfile == _ability.GetDamageProfile() && w.IsMelee;
```

Le profil vient de
`IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$GetDamageProfile` =
`AbilityConfiguration.GetAffectedDamageProfile().GetValueOrDefault(0xd)` ; `0xd = 13 = Psychic`
(`IdunBattle.Entities.Enum.DamageProfileType`), et la constante d'ability
`affectedDamageProfile` vaut `"Psychic"` au gameconfig courant — le défaut coïncide avec la valeur
configurée, mais le port RELIT la constante, comme le natif.

`IdunShared.Battle.WeaponProfile$$get_IsMelee` = `!Range.HasValue || Range.Value < 2`.

### 1.3 Les deux pièges, et pourquoi ils ne se devinent pas

**a) Le trait `Chaos` n'existe pas dans le gameconfig.** Aucune des 669 unités n'a `"Chaos"` dans
son champ `traits` (compté). Le trait vient de la GRANDE ALLIANCE :
`idun.Idun.Source.Shared.GrandAlliance$$GetTrait` mappe la chaîne `GrandAllianceId` sur trois
`UnitTrait` — `Imperial = 0x1a`, `Xenos = 0x3ee`, `Chaos = 0x7ea` — et c'est le
`BattleConfiguration` qui l'ajoute au `UnitConfiguration.Traits`, que
`IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` recopie (config+0xd0) dans le
`BaseUnitComponent.Traits` (+0x40) interrogé par
`IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`. Le pendant offline est donc
`GrandAllianceId`, pas `traits`.

**b) `..._AdjacentPsychicEnemy` ne dit RIEN de la contrainte de mêlée.** Le prédicat exige
`DamageProfile == Psychic` **ET** `IsMelee`. Sur le gameconfig courant, **19 unités** portent une
arme melee-Psychic ; mais `thousAhriman`, `ultraTigurius`, `astraPrimarisPsy`… portent aussi une
arme Psychic **de portée** (`Range = 2`) qui, elle, ne compte pas. Un port qui s'arrêterait au
profil ajouterait 10 là où le natif met 0 — mesuré, §4.3.

**c) `Any`, pas `Count`** : un voisin qui porte deux armes melee-Psychic vaut 10, pas 20.

### 1.4 Aucun `FilterAdjacent*`, aucune face ATTAQUE

Le bloc de code de la classe est **contigu et complet** dans `ghidra/functions.tsv` :
`GetAdjacentEnemyUtility`, `GetAdjacentFriendUtility`, `<GetAdjacentEnemyUtility>b__4_0`, `.ctor` —
entre le bloc `CosmicHorrorPlaybook` et le bloc `DaRevolushunPlaybook`, sans trou d'adresse. Ce
n'est pas l'argument « absent de la table » (qui ne prouve rien, cf. CLAUDE.md) : les voisins
immédiats montrent qu'un playbook émet bien toutes ses méthodes d'affilée, et `CosmicHorrorPlaybook`
y a son `CalculateAttackUtilityInStepsInternal` là où `CursedPlagueBellPlaybook` n'en a pas. Ce
playbook ne pèse donc **que** le mouvement, et ses deux gates vivent dans les accesseurs.

---

## 2. Ce qui a été porté

| Fichier | Contenu |
|---|---|
| `engine/playbook/adjacent_unit_preference.py` | `CursedPlagueBellPlaybook` (1071) + entrée au registre `TRIGGERED_MOVE_PLAYBOOKS` (10 -> 11) ; helpers `_has_trait` (mirror `UnitExtensions$$HasTrait`, alliance comprise), `_unit_weapons`, `_weapon_is_melee` (mirror `WeaponProfile$$get_IsMelee`), `_cursed_plague_bell_damage_profile` |
| `scripts/python/probe_211_cursed_plague_bell.py` (**neuf**) | garde de substrat offline + confrontation live AGRÉGÉE sur plusieurs pas + mutation du registre mesurée en ligne |
| `tests/engine/test_tile_term_unit_gated_playbooks_live.py` | +2 montages (un par face) dans `CASES` |

`_has_ranged_weapon` (case-193c) est réécrit `any(not _weapon_is_melee(w) …)` : la règle `IsMelee`
n'existe plus qu'à un seul endroit. **Value-preserving** — c'était déjà `Range >= 2`.

---

## 3. Le substrat : ce que le port lit vs ce que le natif voit

Le natif interroge des composants ECS (`BaseUnitComponent`, `WeaponsComponent`) ; le port lit le
gameconfig. Ce n'est pas une commodité, c'est une identité **mesurée** — étape 0 de
`probe_211_cursed_plague_bell.py`, sur les 175 unités de `data/seed-bc.json` :

| contrôle | résultat |
|---|---|
| `BC.Traits` == `gameconfig.traits` ∪ {trait de grande alliance} | **175 / 175**, 0 écart (Imperial 74, Xenos 63, Chaos 38) |
| `BC.Weapons[i].DamageProfileType` == `gameconfig.weapons[i].DamageProfile` | **246 armes**, 0 écart |
| `BC.Weapons[i].IsMelee` == `Range is None or Range < 2` | **246 armes**, 0 écart |

Ce que ce substrat ne voit **pas** : les traits accordés/retirés en cours de bataille
(`AddTraitOperation`, `BaseUnitComponent+0x48/+0x50`) et les armes modifiées par un effet. Même
limite que `_unit_faction` (case-193c) et que le `filter_adjacent_friend` de
`FabricatorClawArrayPlaybook`.

---

## 4. Validation live

Décomposition par étage aux hooks EXISTANTS de `scorer-damage-trace` (armés pour un
`aiStepDryRun`, désarmés en `finally`, **aucune réinjection**) :

    X = Tile(7) − Elevation − TileEffects        (natif)

comparé au même résidu côté port. Six montages, board `MC1_67`, quatre seeds — **40 tuiles
confrontées, 0 désaccord**.

### 4.1 Le régime discriminant : le cardinal ne suffit pas

`2468` pas 14+19, roster « aucun ami Chaos » (la face amie est muette, le terme ne vient que des
ennemis) :

| tuile | X nat | X port | terme | voisins R1 |
|---|---|---|---|---|
| (3,5) | 10 | 10 | 10 | ennemi **melee-Psychic** + ami **hors Chaos** |
| (4,4) | **0** | 0 | 0 | ennemi **Psychic de PORTÉE** (`thousAhriman`) |
| (5,4) | **10** | 10 | 10 | ennemi melee-Psychic + ennemi Psychic de portée |
| (3,6) | **0** | 0 | 0 | **2** ennemis non-Psychic |
| (2,4) | **10** | 10 | 10 | ennemi melee-Psychic + ennemi non-Psychic |
| (5,5) / (4,3) | 0 | 0 | 0 | ennemi Psychic de portée |
| (1,4) / (3,5) | 10 / 0 | idem | idem | 1 ennemi melee-Psychic / 1 non-Psychic |

**(3,6), (5,4) et (2,4) ont TOUTES TROIS deux voisins**, et valent **0, 10, 10**. Aucun poids par
voisin ne produit cette table : c'est la composition, pas le cardinal, qui décide.

`12345` pas 14+25, même roster :

| tuile | X nat | X port | terme | voisins R1 |
|---|---|---|---|---|
| (4,4) | 0 | 0 | 0 | ennemi Psychic de portée |
| (5,4) | 10 | 10 | 10 | ennemi melee-Psychic + ennemi Psychic de portée |
| (3,4) | **40** | 40 | 40 | ennemi non-Psychic + ami hors Chaos + **2 amis Chaos** |

(3,4) porte **quatre** voisins et vaut **40 = 2 × 20** : les deux amis Chaos comptent, l'ami hors
alliance et l'ennemi non-Psychic comptent pour zéro.

`777` pas 25+28, roster mixte (2 amis Chaos, 2 hors Chaos) : 11 tuiles, termes {0, 10, 20, 30} —
(2,4) = 30 (1 ami Chaos + 1 ennemi melee-Psychic) contre (4,4) = 0 (2 ennemis non-Psychic), à
cardinal 2 des deux côtés. Trois autres montages (`777` ennemis non-Psychic seuls : 10 tuiles ;
`777` 3v3 : 2 tuiles ; `777` amis hors Chaos : 3 tuiles) complètent les 40.

### 4.2 Couverture des cas de voisinage

Les cinq cas que les deux gates distinguent sont **tous** exercés live, chacun sur au moins une
tuile mesurée : ami Chaos (**+20**), ami hors Chaos (**0**), ennemi melee-Psychic (**+10**), ennemi
Psychic **de portée** (**0**), ennemi non-Psychic (**0**).

### 4.3 Mutation adversariale — trois mutations, trois morsures

Chaque gate a été retiré à tour de rôle, et la mesure rejouée **sur les mêmes montages** :

| mutation | effet mesuré |
|---|---|
| entrée `1071` retirée du registre | 4 à 7 tuiles rouges par montage ; en pytest **3 failed**, dont l'AGREEMENT natif : `pas 19 (deathBlightbringer) : le port retient (3, 6), le natif joue (2, 4)` |
| `&& _weapon_is_melee(w)` retiré (gate `IsMelee`) | **5 / 11 tuiles rouges** (`2468`) — exactement les tuiles à ennemi Psychic **de portée** : natif 0, port muté 10 |
| `if not _has_trait(unit, "Chaos")` retiré | **3 / 11 tuiles rouges** (`12345`) — exactement les tuiles à ami **hors Chaos** : natif 0, port muté 20 |

La deuxième et la troisième sont ce qui donne son poids au cas : elles prouvent **live** que le
seuil `Range >= 2` de `WeaponProfile$$get_IsMelee` et le trait d'alliance `Chaos` sont l'un et
l'autre EFFECTIFS dans le natif — pas seulement lisibles au décompilé.

### 4.4 Gardes et non-régression

`tests/engine/test_tile_term_unit_gated_playbooks_live.py` — les deux nouveaux montages passent
(10/10), et les quatre montages de case-193c (`HatefulAssault`, `FearedInterrogator`) restent verts
malgré la réécriture de `_has_ranged_weapon` ; `test_tile_term_triggered_playbooks_live.py` (N13)
inchangé.

---

## 5. Ce que ce cas n'établit PAS

* **La face `TriggeredAbilitiesNonOwner(4)`** : `Utilities.Default.TriggeredAbilitiesNonOwner` n'a
  aucune clé `CursedPlagueBell` (vérifié) — rien à porter de ce côté, la feuille (4) reste
  globalement non portée.
* **Un voisin dont le trait `Chaos` serait ACCORDÉ en bataille** (`AddTraitOperation`) ou dont une
  arme serait ajoutée par un effet : hors substrat gameconfig, non exercé.
* **Un voisin SUMMON** : aucun des six montages n'en a dans le voisinage mesuré. Le cas « le `vis`
  d'un summon ne retombe pas sur son unitId gameconfig » reste non exercé (déjà noté case-193c §7).
* **Les caps `vtbl+0x228 / 0x238`** du corps commun : toujours non répliqués, jamais vus saturer
  (max mesuré ici : 4 voisins, dont 2 qualifiants).
* **Le comportement de l'ability elle-même** — ce cas ne porte que le PLAYBOOK (l'utilité de
  mouvement de l'IA), pas l'effet de jeu. TROIS morceaux en sont depuis SORTIS, portés et validés
  live par des cas dédiés :
  * `CursedPlagueBellMovementAbility` → `case-224-cursed-plague-bell-movement.md` (pose de
    `CursedPlagueBell_ExtraMove` 1073 au turn-start du porteur, 11 tours confrontés / 0 désaccord) ;
  * `CursedPlagueBell_ExtraMoveEffect` → `case-224-cursed-plague-bell-extramove.md` (l'effet 1073
    lui-même : `ChangeStat(Stat(1 = Movement, 5 = Modification), 4 = Modify,
    Direct(GetNumberConstant(0xe)), Entity(effect))` = le +1 Movement effectif, et son revert
    `part 6 = ResetModification` à l'expiration) ;
  * `CursedPlagueBellAttackAbility$$IsInContagionsOfNurgleRange` →
    `case-224-is-in-contagions-of-nurgle-range.md` (nœud DSL `IsInUnitAura`, table de portée
    `entities/effects/aura.py`).

  Restent non portés : `CursedPlagueBell_DangerZoneEffect`, et le reste du `CreateTrigger` / le
  `CreateBehaviour` de `CursedPlagueBellAttackAbility`.

---

## 6. Reproduire

```bash
cd scripts/python
python probe_211_cursed_plague_bell.py --offline-only          # garde de substrat (BC vs gameconfig)
python probe_211_cursed_plague_bell.py --seed 2468 --board MC1_67 --max-steps 60 --max-arm 10 \
    --p-units "deathBlightbringer,astraBullgryn,necroWarden,orksNob,eldarRanger" \
    --a-units "bloodMephiston,astraPrimarisPsy,thousAhriman,tauMarksman,templChampion"
python probe_211_cursed_plague_bell.py --seed 777 --board MC1_67 --max-steps 60 --max-arm 10
python -m pytest tests/engine/test_tile_term_unit_gated_playbooks_live.py -k deathBlightbringer
```

⚠ Le probe arme des hooks **RVA build-spécifiques** (`gqfc5mff6c`) : il vérifie le hash, arme pour
un `aiStepDryRun`, désarme en `finally`.

L'option `--herd <visualIds>` déplace des unités VERS le contact du porteur au lieu de laisser l'IA
les jouer (doctrine « drive positions ») : elle n'a pas été le levier qui a produit les cas
manquants ici — c'est le ROSTER qui l'a été — mais elle reste le levier à sortir quand un cas de
voisinage refuse d'apparaître.

---

## 7. Le compte, après

```
NATIF     108
PORTE      11   (10 + CursedPlagueBell 1071)
GISEMENT   42   (etait 43)
```

`CursedPlagueBell` était le 3e plus gros poids du rang A confrontable (20 + 10). Restent notamment
`MedicusMinistorum` (15), `Deathwing` (10), `TaintedNarthecium` — tous de la 2e forme (gate sur le
voisin, un poids), donc plus proches des 3-lignes que celui-ci.
