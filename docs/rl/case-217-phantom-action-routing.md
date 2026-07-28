# case #217 — actions FANTÔMES `(1100 SorcerousFacade, ennemi)` : un problème de ROUTAGE de ciblage

**Verdict : quirk porté.** Le générateur d'actions OFFLINE fabriquait, pour chaque ennemi à portée,
une paire `(1100, ennemi)` que le natif refuse intégralement. La cause n'est ni l'utilité (fermée par
la PR #208) ni la formule : c'est le prédicat de routage `state_bridge._is_attack_ability`, qui ne
regarde que `constants.damageProfile` — une donnée qui dit « cette ability produit du dégât », pas
« sa cible est un ennemi ».

## 1. Ce que dit le natif

### 1.1 Le masque de `SorcerousFacade`

`IdunBattleLogic.Entities.Abilities.Active.Loki.SorcerousFacadeAbility$$.ctor` (forme « flags
directs ») :

```
TargetingOptions..ctor(&opts,
                       isSelfCasting   = 0,
                       range           = <TargetingRange statics+0x48 = UseWholeBoard>,
                       forceMeleeTarget= 1 (RangedBool.False),
                       rules           = 0x402,
                       0, 0, 0)
AActiveAbility..ctor(this, &opts, 2, 0)
```

`0x402` = `TargetIsFriendly | TargetMatchesDynamicRule`. La cible est un **ALLIÉ**, point — et la
règle dynamique la restreint encore :

```
SorcerousFacadeAbility$$GetDynamicInvalidTargetReason(caster, casterTiles, target) :
    if (UnitExtensions.HasTrait(target, 0x3ea /* Psyker */)) {
        normal = UnitExtensions.GetNormalAttackType(caster);
        if (battleQuery.<slot 0x3f>(caster, casterTiles, normal)) return 0;   // valide
    }
    return 2;   // TargetMatchesDynamicRule
```

⚠ Le masque n'est pas lisible sur le nom ni sur le profil de dégât : `constants.damageProfile` vaut
`Psychic` et `constants.range` est absent (portée = arme, 2). Les DEUX signaux gameconfig disent
« attaque » ; le camp ne vit QUE dans le littéral du ctor.

### 1.2 Pourquoi le natif ne rend AUCUNE tuile sur un ennemi

`IdunBattle.Core.Services.AttackQuery$$GetBestTileToAttackFrom(unit, tiles, target, ability)` —
l'homologue natif exact du producteur de `plans` — **gate chaque tuile candidate** :

```
best = null; bestUtility = Fix64.MinValue;
foreach (tile in tiles) {
    reason = AttackQuery.GetInvalidTargetReason(unit, new UnitPosition(tile), target, ability);
    if (IBrokenTargetingRuleExtensions.IsInvalid(reason)) continue;      // <-- LE GATE
    u = utilities.EvaluateMovement(new UtilityMovementCase(unit, tile, target, Nullable(ability), null, null));
    if (best == null || u > bestUtility) { bestUtility = u; best = tile; }
}
return best;
```

Sur une ability `TargetIsFriendly`, la cascade rompt pour **tout** ennemi
(`TargetingQuery$$GetInvalidTargetReason` : `if (!UnitsAreFriendly(caster, target)) broken(0x400)`).
Le natif rend donc `null` pour chaque tuile ⇒ **zéro** paire `(1100, ennemi)`.

### 1.3 `!IsEnemyTargeting` n'est PAS un refus — le piège à éviter

`IdunBattle.Core.Services.TargetingOptions$$get_IsEnemyTargeting` (= `TargetIsEnemy` OU
`TargetIsCasterOrEnemy`) et ses frères (`get_IsTileTargeting`, `get_IsUnitTargeting`,
`get_IsMachineTargeting`, `get_IsActorTargeting`, `get_IsCasterOrEnemyTargeting`,
`get_CanTargetCaster`) sont des **lectures déclaratives** du masque, consommées par
`IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` pour choisir le **domaine**
énuméré (`GetTilesInRange` / `GetUnitsInRange` / la liste des machines).

Un masque qui ne porte **ni** `TargetIsFriendly` **ni** `TargetIsEnemy` n'interdit **rien** par camp :
`GetPossibleTargetsForOptions` énumère `GetUnitsInRange` (les deux camps) et ses deux prédicats de
purge ne retirent que les morts / les tuiles à occupant `Steppable`
(`…u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__0`) et les ennemis
**obscurcis** (`…b__1` : `if (IsFriend(target, caster)) return false;` puis
`GetTilesObscuringTerrain(...).Count > 0`).

⇒ Le prédicat « cette ability refuse toute cible ennemie » n'a que **deux** termes, les deux seules
règles de camp/identité du filtre statique : **`TargetIsFriendly`** et **`TargetIsCaster`**. S'appuyer
sur `not is_enemy_targeting` inventerait des refus (ex. `CalibaniteGreatsword`, masque `0x80`
`AddCaster` seul, dont la cascade ne rompt sur aucun ennemi).

## 2. Le fix

| Fichier | Changement |
|---|---|
| `engine/runner/abilities/targeting.py` | Port 1:1 des 7 lectures déclaratives natives sur `TargetingOptions` ; `refuses_all_enemy_targets(options)` ; `TARGETING_OPTIONS_UNPORTED` (masques RE-lus d'abilities hors registre COMBAT) ; résolveur `targeting_options_for(ability_id)`. |
| `engine/ai/state_bridge.py` | `_refuses_all_enemy_targets(aid)` = **VETO NATIF** ; `_is_attack_ability` le consulte AVANT la signature gameconfig ; `_ability_kind` rend `ally` (masque `TargetIsFriendly`) ou `self` (`TargetIsCaster`). |
| `engine/runner/operations/summon_ai.py` | `_is_active_attack_ability` hérite du veto : une ability à cible ALLIÉE ne tombe plus dans le repli générique `AttackWithAttackDamage`. |

**Le veto est STRICTEMENT SOUSTRACTIF** — il ne PROMEUT jamais vers la route ennemie. Une ability
dont le masque porte `TargetIsEnemy` sans `damageProfile` reste hors de `_best_attack` (résidu §4).

**Pourquoi une 2ᵉ source de masque.** Le littéral vit dans `<X>Ability$$.ctor`, pas dans
`ExecuteBehaviour` : il se lit indépendamment du registre COMBAT. Inscrire `SorcerousFacadeAbility`
dans `ABILITY_CLASSES` juste pour porter son masque la ferait passer `ported:True` côté
`AbilityHandler` alors que sa behaviour est un no-op — ce qui **éteindrait** le diagnostic
`unported`. La table est donc **disjointe** du registre, contrat gardé par
`tests/engine/runner/test_targeting_options_sources.py`.

## 3. Mesure — confrontation live (`probe_217_facade_live.py`, runner `MC1_67`, seed 217)

Montage : `thousTzaangor` (porteur de 1100) + `thousSorcerer` (l'allié **Psyker**) vs 3 Ultramarines ;
le caster est rapproché jusqu'à ce que la règle dynamique soit satisfiable.

```
1) NATIF abilityTargets(1100).targets = [('unit', 85)]      # l'ALLIE Psyker, et lui seul
   dont ENNEMIS : []
2) LIVE attackPlans (1100, ennemi) -> (targetId, rankCount) = [(77, 0), (79, 0), (81, 0)]
   avec rankCount > 0 : []
3) OFFLINE ability_targets_offline(1100) = [('unit', 83), ('unit', 85)]
   OFFLINE plans (1100, cible) = []
   [AVANT fix] ability_targets_offline(1100) = [('unit', 79), ('unit', 81)]
   [AVANT fix] plans (1100, cible)           = [(1100, 79), (1100, 81)]
5) EXECUTION forcee (1100, ennemi u77) APRES fix = 'noop'
   EXECUTION forcee (1100, ennemi u77) AVANT fix = 'generic_attack'
```

Trois enseignements, dont un **correctif de diagnostic** :

- **la couture LIVE était déjà propre.** `decisionView.attackPlans` porte bien les trois entrées
  `(1100, ennemi)`, mais avec `rankCount = 0` — le gate natif de `GetBestTileToAttackFrom` a fait son
  travail — et `_best_attack` saute les évals à `rankCount` nul. Les termes ±45 relevés en #27
  tranche 3 venaient d'un probe qui évaluait `calculate_custom_utility` sur **toutes** les évals,
  `rankCount` compris à 0 : sur le chemin live, ces actions n'atteignaient jamais le Bucket.
- **le fantôme était OFFLINE**, et bien réel : `_plans_for_unit` construit ses tuiles par la SEULE
  distance hex, sans aucun équivalent du gate natif → 2 actions inexistantes dans le même état.
- **la face EXÉCUTION basculait aussi** : le repli générique de `summon_ai` routait le cast vers
  `AttackWithAttackDamage` (`routed: generic_attack`) ; il retombe maintenant sur le `noop` documenté
  des abilities non portées. (La magnitude observée est 0 sur un état `load_state` — le dégât du
  repli générique n'est pas le sujet ici ; c'est le ROUTAGE qui est l'observable.)

Le sur-ensemble `[83, 85]` de `ability_targets_offline` (le caster en plus de l'allié) est la
dégradation **permissive** assumée : la règle dynamique de 1100 (`HasTrait(target, Psyker)`) vit sur
la classe d'ability, qui n'existe pas côté port. Le natif, lui, écarte le Tzaangor — il n'est pas
Psyker.

## 4. Balayage de la classe — combien d'autres abilities ?

Sur les **170** `ActiveAbilityType` déclarées par au moins une unité du gameconfig (probe
`probe_217_phantom_action_routing.py`, mesuré après rebase sur `359231a` : masques applicables =
**57** = 56 du registre COMBAT + 1 de la table hors-registre). ⚠ Ces comptes bougent à chaque port —
les re-dériver avec le probe plutôt que citer ce tableau :

| classe | compte | statut |
|---|---|---|
| masque refusant TOUTE cible ennemie (`TargetIsFriendly`/`TargetIsCaster`) | **5** — 1002 CombatRestoratives, 1009 ResurrectionOrb, **1100 SorcerousFacade**, 1187 ThriceBlessedConflagration, 1214 Hailstrike | **fermé** (veto) |
| dont **routées vers les ennemis avant le fix** | **3** — 1100, 1187, 1214 | **fermé** |
| divergence de **DOMAINE** : routée vers des UNITÉS ennemies, masque TILE-targeting | **7** — 1017 FragBomb, 1026 BasiliskBarrage, 1116 RadBombardment, 1159 MacroPlasmaIncinerator, 1188 DevastatingRefrain, 1201 SquigMine, 1213 DeathOnTheWind | **résidu nommé** (§5) |
| **sous-génération** : masque `TargetIsEnemy`, ability NON routée (pas de `damageProfile`) | **11** | **résidu nommé** (§5) |
| masque **non RE-lu**, routée vers les ennemis | **56** | **résidu nommé** (§5) |

**Corroboration croisée du balayage.** Le masque de `ArmoriumCherub` (1014) a été relu pendant cette
tâche (preset `TargetingOptions` statique `+0x140` → `rules = 0x4002`) AVANT que #222-1 ne le porte
sur la classe ; le littéral posé par #222-1
(`TargetMatchesDynamicRule | TargetIsEnemy`) est **identique**. Le veto ne change donc PAS le verdict
de 1014 : `TargetIsEnemy` est présent, elle reste routée vers les ennemis — c'est le comportement
attendu, et c'est aussi la démonstration que le veto ne mord que sur les masques qui refusent
réellement (il est soustractif, pas « prudent »).

1002 et 1009 n'étaient déjà pas routées vers les ennemis (pas de `damageProfile`) — le veto ne change
que leur `kind` (1009 : `tile` → `self`, ce qui est **exactement** le domaine natif, `rules &
TargetIsCaster` ⇒ le candidat set vaut `{caster}`). 1187 et 1214 sont portées par des **Machines of
War**, qui ne sont pas des unités de décision offline (`_dv_units` les exclut) : le changement y est
inerte mais conforme — le playbook déjà porté de 1187 documente lui-même « cible = une UNITÉ ALLIÉE ».

**Couverture du balayage au décompilé** : 42 des 57 `<X>Ability$$.ctor` à masque non lu ont été
relus pendant cette tâche (aucun `TargetIsFriendly`/`TargetIsCaster` supplémentaire trouvé ; 1014 a
depuis été porté par #222-1, d'où 56 restants). Les 15 non relus sont pour l'essentiel des abilities
de **MoW** (1142, 1147, 1148, 1160, 1161, 1168, 1169, 1209) et de **boss NPC** (1215, 1216, 1217),
plus 1064 `Loki_SwoopingHawk` et 1091 `SlashingDive` (corps délégué à
`DiveAttackAbilityBase$$.ctor`, non résolu par le symbole).

**Recette du balayage** (utile au prochain lot) : les ctors passent le plus souvent par un **PRESET**
statique + flags, pas par un littéral. Décompiler UNE fois
`IdunBattle.Core.Services.TargetingOptions$$.cctor` donne toute la table des presets (offset dans le
bloc de statiques → `rules` à `<preset>+0x28`), après quoi chaque ctor se lit d'un coup d'œil :

| preset | `self_cast` | `TargetingRange` | `rules` |
|---|---|---|---|
| `+0x000` | 0 | `+0x00` adjacent-if-melee | `0x4002` |
| `+0x040` | 0 | `+0x30` adjacent | `0x4000` |
| `+0x080` | 0 | `+0x00` | `0x4000` |
| `+0x0c0` | 0 | `+0x00` | `0x80040` |
| `+0x100` | 0 | `+0x00` | `0x8500` |
| `+0x140` | 0 | `+0x18` from-config | `0x4002` |
| `+0x180` | 0 | `+0x18` | `0x4002` |
| `+0x1c0` | 0 | `+0x48` whole-board | `0x6000040` |
| `+0x200` | 0 | `+0x18` | `0x42` |
| `+0x240` | 0 | `+0x48` | `0x102004032` |
| `+0x280` | 1 | `+0x60` self | `0x8004` |
| `+0x2c0` | 1 | `+0x00` | `0x4000` |
| `+0x300` | 1 | `+0x18` | `0x4000` |
| `+0x340` | 1 | `+0x30` | `0x4000` |
| `+0x380` | 1 | `+0x30` | `0x400` |
| `+0x3c0` | 0 | `+0x18` | `0x200000000000004` |

## 5. Ce qui n'est PAS couvert

- **Divergence de DOMAINE (7 abilities)** — leur masque est `TargetIsTile` : le natif énumère des
  TUILES (`GetPossibleTargetsForOptions` → `GetTilesInRange`), le moteur des UNITÉS ennemies. Non
  corrigé **délibérément** : les playbooks NonComparable déjà portés (`dark_talon_strike`,
  `heroic_fusillade`, …) consomment `ability_targets` sous la forme « unités ennemies », et basculer
  le domaine est un chantier séparé, à faire playbook par playbook. À noter que ce n'est pas non plus
  un refus de la cascade : `GetInvalidTargetReason(caster, pos, uniteEnnemie, <ability tile>)` résout
  `GetMainTile(target)` et peut rendre « valide ».
- **Sous-génération (11 abilities)** — masque `TargetIsEnemy` mais aucun `damageProfile`, donc jamais
  candidates offline. Le veto est soustractif par construction ; les promouvoir demanderait de savoir
  leur produire une utilité (elles n'ont pas de prédiction de dégât).
- **Règle dynamique de 1100 non portée** — `ability_targets_offline(1100)` rend un SUR-ENSEMBLE des
  alliés (le caster inclus) là où le natif ne rend que l'allié **Psyker**. Aucun consommateur
  aujourd'hui (1100 n'a pas de playbook, cf. PR #208), donc inerte ; à fermer avec le port de la
  face COMBAT de 1100.
- **15 masques non relus** (§4) — MoW et boss NPC pour l'essentiel.
- **Pas de flip de DÉCISION mesuré** : dans le montage exercé, l'action retenue est la même avant et
  après (`ability 17` attaque normale, `util 51.92`). C'est attendu — le dégât config de 1100
  (`[1197,1795]`, cf. `case-171`) est **sous** l'attaque normale du Tzaangor (`[1623,3591]`), donc le
  fantôme perdait l'argmax. Il restait une action ILLÉGALE offerte à l'espace d'action (et exécutable
  en dégât générique) : c'est ce trou qui est fermé, pas un choix d'IA observé.
