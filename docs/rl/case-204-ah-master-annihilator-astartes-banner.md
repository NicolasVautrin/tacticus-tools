# case-204 — `MasterAnnihilator_AdditionalHitEffect` (1249) et `AstartesBanner_AdditionalHitsEffect` (1106) : le fork du canal #179, fermé

**Critère binaire** : *sur un montage live où le bonus du porteur mord, l'événement de dégât
supplémentaire vaut-il **(a)** un COUP D'ARME (valeur tirée dans les bornes d'arme, dispersée d'un
coup à l'autre), ou **(b)** un coup de GROUPE du canal #179 —
`IdunBattle.Entities.Formulas.FirstHitInCurrentAttackDamageRange`, donc le `IdunBattle.Core.HitDamage`
de l'AttackData de CETTE attaque, dégénéré sur une attaque normale, donc une CONSTANTE égale à la
stat ATTACK réduite ?*

**Réponse, pour les DEUX porteurs : (b).** Mesuré live, même protocole que `case-227` :

| porteur | événement supplémentaire, attaques armées | coups d'ARME de la même campagne | stat ATTACK de l'attaquant |
|---|---|---|---|
| `AstartesBanner` (`templAncient`) | **4617 × 5/5** | 8 valeurs distinctes sur 8, 3832 … 5027 | **4617** |
| `MasterAnnihilator` (`admecDominus`) | **4617 × 5/5** | 8 valeurs distinctes sur 8, 3832 … 5503 | **4617** |

Le contrefactuel « +1 coup d'ARME » (l'ancien port) devrait tirer 4617 **pile** dans
`[0,8·A ; 1,2·A] = [3694 ; 5540]` — 1847 valeurs possibles : **0/5** sur chacun des deux montages.

---

## 1. RE — les deux descripteurs, lus verbatim (build `gqfc5mff6c`)

Les deux appellent `CreateAdditionalHits` (le marqueur du canal #179), **pas**
`CreateEffectHitsBonusForAttack` (le marqueur de la formule de coups). C'est exactement le fork
identifié — et refermé sur `LetTheGalaxyBurn` — par `case-227`.

```
IdunBattle.Entities.Effects.Loki.MasterAnnihilator_AdditionalHitEffect$$CreateAdditionalHits
  -> EffectAdditionalHits$$Create(
       condition   = get_OwnerIsTarget & !AreEqual(CurrentAttackDamageProfile, 0xd = Psychic),
       amountNode  = FirstHitInCurrentAttackDamageRange(),   # param_3  ROLL
       profileType = CONCAT44(0, 0xffffffff)  -> NULL,       # param_5
       countNode   = ConfigConst(0x2f = nrOfHits),           # param_6
       minNode     = FirstHitInCurrentAttackDamageRange(),   # param_8  DISPLAY (2e instance)
       capNode     = ConfigVar(0xd = maxDmg))                # param_9

IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect$$CreateAdditionalHits
  -> (Create INLINÉ, même layout de struct)
       condition   = get_OwnerIsCaster & IsMeleeAttack,
       amountNode  = FirstHitInCurrentAttackDamageRange(),
       profileType = 0xffffffff -> NULL,
       countNode   = ConfigConst(0x64 = extraHits),
       minNode     = FirstHitInCurrentAttackDamageRange(),
       capNode     = ConfigVar(0xd = maxDmg)
IdunBattle.Entities.Effects.Loki.AstartesBanner_AdditionalHitsEffect$$CreateTargetSelector
  -> SurroundingFriends(Self@0x148, ConfigConst(0x16 = range), excludeSelf = 1, 3)
```

### 1.1 Les identifiants de config, RE-LUS — l'ancienne docstring confondait COUNT et CAP

Les ids sont des index dans deux énumérations **distinctes**
(`data/symbols/gqfc5mff6c/frida/enums.tsv`) :

| énumération | id | nom |
|---|---|---|
| `IdunBattle.Configuration.AbilityConstantType` | `0x16` | `range` |
| `IdunBattle.Configuration.AbilityConstantType` | `0x2f` | `nrOfHits` |
| `IdunBattle.Configuration.AbilityConstantType` | `0x64` | `extraHits` |
| `IdunBattle.Configuration.AbilityVariableType`  | `0xd`  | `maxDmg` |

La docstring d'`AstartesBannerExtraHitEffect` lisait `ConfigVar(0xd = extraHits)` : `0xd` est
`maxDmg` **dans l'espace des VARIABLES**, et le count est `ConfigConst(0x64)` **dans l'espace des
CONSTANTES**. Croisé avec le gameconfig, c'est cohérent et sans ambiguïté :
`AstartesBanner.constants = {range: 2, extraHits: 1}`, `AstartesBanner.variables = {dmg, maxDmg}` ;
`MasterAnnihilator.constants = {nrOfHits: 1}`, `variables = {maxDmg, nrOfAttacks}`.

### 1.2 Ce que le nœud rend, et pourquoi c'est une constante

Chaîne identique à `case-227` §2, non re-dérivée ici :
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` pousse les 16 premiers octets de
l'AttackData (dont le champ 0 **est** son `IdunBattle.Core.HitDamage`) dans `currentAttack@+0x50` ;
les trois accesseurs du nœud font `FirstOrDefault` sur cette liste ;
`IdunBattle.Core.HitDamage$$GetDamage` ouvre sur `if (min == max) return min`. Sur une attaque
NORMALE l'AttackData porte un `HitDamage` **dégénéré** ⇒ court-circuit ⇒ `reduce(base)`,
**déterministe**. Sur une ability bounds-mode il est non dégénéré ⇒ le groupe TIRE (et coïncide alors
fortuitement avec l'ancien modèle : c'est le piège que `case-227` §2.3 documente, et la raison pour
laquelle **le discriminant vit sur l'attaque normale**).

### 1.3 Le profil NULL choisit le call-site

Les deux passent le même littéral de profil que `LetTheGalaxyBurnEffect` (`0xffffffff`,
`HasValue`/`-1` traité comme « pas de profil » par
`AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`, qui teste
`hasValue && value == -1`). Le groupe est donc exécuté **INLINE** depuis
`AttackDamageOperation$$Execute`, avant les groupes à profil, et emprunte le **profil de l'arme**.
Vérifié offline : profil du groupe = `Piercing` avec `ultraApothecary` (arme Piercing) et `Psychic`
avec `astraPrimarisPsy` (arme Psychic) — dans les deux cas celui de l'arme, jamais un profil propre.

### 1.4 Direction — établie depuis le SÉLECTEUR, pas depuis la place du port

- `MasterAnnihilator` : condition `get_OwnerIsTarget` ⇒ l'effet est porté par la **CIBLE** de
  l'attaque. Il y est posé par `IdunBattleLogic.Entities.Abilities.Triggered.Loki.
  MasterAnnihilatorAbility$$CreateBehaviour` (`RemoveEffect(OwnerOfEffect(EffectsFromUnitSource(
  Self, 0x4e1))) + AddEffect(0x4e1, …, Target@0x178)`) sur `On(0x26 = NormalAttack) & OwnerIsCaster
  & AreEnemies(…)`. Les bénéficiaires sont donc les **ennemis du porteur du marqueur** = les alliés
  du poseur : le « friendly unit » de l'i2 est **structurel**, il n'est pas dans le trigger.
- `AstartesBanner` : condition `get_OwnerIsCaster` + `CreateTargetSelector = SurroundingFriends` ⇒
  l'effet est porté par `templAncient` (`AstartesBannerAbility$$CreateBehaviour` =
  `AddEffect(0x452, …, Self@0x148)`) et ses **cibles** (les alliés dans le rayon 2, self exclu) sont
  les attaquants qui gagnent le coup.

**Porteur cité à tort dans le brief** : `blackPossession`. Le porteur réel de `MasterAnnihilator`
est **`admecDominus`** (« Vitruvius ») — `unit_map find --ability MasterAnnihilator` ne rend que la
famille `admec*Dominus*`. Les deux porteurs sont **dans le pool** (`rl_duel build --list-pool`,
rank 17), donc directement confrontables ; aucun n'est un summon ni un npc.

---

## 2. Le port

| avant | après |
|---|---|
| `MasterAnnihilatorAdditionalHitEffect.create_effect_hits_malus_for_defense` → `for_addition(True, nrOfHits)` | `.create_aura_additional_hits_for_ally` → `{count: nrOfHits, min: hd0, max: hd1, profile: None}` |
| `AstartesBannerExtraHitEffect.create_aura_hits_bonus_for_attack` → `for_addition(True, extraHits)` | `.create_aura_additional_hits_for_ally` → `{count: extraHits, min: hd0, max: hd1, profile: None}` |
| canal `aura_hits_bonus_for_attack` (agrégateur + hook + appel dans `attack_hits_with_modifiers`) | **SUPPRIMÉ** — `AstartesBanner` en était le SEUL alimenteur ; le laisser aurait été un gate mort |
| ctx du canal #179 : `{att_*, owner_*, is_melee}` | `+ tgt_id, t_pos, damage_profile, attack_hit_damage` |

`collect_additional_hit_groups` prend un paramètre `damage_profile` de plus, threadé par les deux
façades COMBAT (`damage_ops/normal.py` → `_profile`, `damage_ops/ability.py` → `damage_profile`).

### 2.1 Pourquoi `create_aura_additional_hits_for_ally` porte AUSSI un descripteur `OwnerIsTarget`

Le natif n'a **qu'un** canal d'énumération (`AdditionalHitsFromEffects$$
GetAdditionalHitsFromEffectsInternal`), **global** : il énumère tous les couples (effet, entités
ciblées) et laisse la CONDITION du descripteur trancher. La scission du port en
`additional_hit_groups` (effets de l'attaquant) / `create_aura_additional_hits_for_ally` (effets
hostés ailleurs) est une commodité ; `collect_additional_hit_groups` balaie déjà **toutes** les
entités sauf l'attaquant — **la cible comprise**. Le suffixe `_for_ally` est donc un raccourci
historique : le hook porte les deux conditions (`OwnerIsCaster` et `OwnerIsTarget`), ce qui est
documenté dans sa docstring plutôt que masqué par un renommage hors périmètre.

### 2.2 Face PRÉDICTION — une correction, pas une régression

`attack_hits_with_modifiers` (facade `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`)
**ne compte plus** ces coups : c'est ce que fait le natif, puisque le descripteur n'est pas un
`EffectHitsBonusForAttack`. Et `AActiveAbility$$GetAdditionalHitsFromEffectsForPrediction` tourne
hors `OngoingAttack` ⇒ `FirstHitInCurrentAttackDamageRange` rend 0 ⇒ le groupe prédit serait un coup
à 0 dégât : le port n'en émet donc aucun quand `attack_hit_damage` est absent. L'ancien port
sur-prédisait un coup **plein** dès qu'un allié `templAncient` était à ≤ 2 hex ou qu'une cible portait
le marqueur 1249.

### 2.3 Le CAP `ConfigVar(0xd = maxDmg)` — transporté, non porté, et MESURÉ inerte

`IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits` évalue le nœud cap (slot 1) et le range en
`Nullable<int>` à `AdditionalHits+0x20` ; `AdditionalHitsFromEffects$$GetAdditionalHitsData` le
recopie dans l'`AdditionalHitsData`. Le seul consommateur **lu** est la face PRÉDICTION :
`AActiveAbility$$AddAdditionalHitsToPrediction` le passe à
`AActiveAbility$$GetEffectAdditionalHitPrediction`, qui le relaie au slot 0x26 de `DamagePrediction`.
Sur la voie COMBAT sans profil, `ExecuteAdditionalHitsWithoutDamageProfileType` ne tire de cet
enregistrement que le **count** et le **profil**.

**Mesure** (`probe_204_cap_and_stat.py`) : `maxDmg` est une variable à 65 paliers (75 … 5456) indexée
sur le niveau d'ability du PORTEUR et affectée par le multiplicateur de rareté. Dans un runner
`rl_duel`, ce niveau vaut **50** quel que soit le `--rank` (le rank ne bouge que les stats) et le
multiplicateur **180 %** ⇒ cap = **7477**, au-dessus de toute stat ATTACK atteignable (max observé
5022, `admecDominus` au rank 17 ; 63 au rank 1). **Aucun régime spawnable ne le fait mordre.** Il
n'est donc pas porté — figer une sémantique d'application non lue serait pire que l'absence. À
rouvrir si un régime `reduce(base) > cap` devient atteignable.

---

## 3. Mesure

### 3.1 Le discriminant, porteur par porteur — `probe_204_ah_channel.py`

Montage commun : `--board MC1_67`, `--hp-target 900000` (met AUSSI l'armure de la cible à **0**, donc
`reduce(base) == base`), `--crit 0,0 --block-target 0,0`, attaquant témoin `ultraApothecary`
(**1 seul** coup mêlée, `mech: {}`), cible `bloodSanguinary`. Phase NUE d'abord (contrefactuel), puis
phase ARMÉE. Les positions sont **pilotées** à chaque tour.

```
--case astartes                        --case master
  nue   n=1 [4307]                       nue   n=1 [4307]
  nue   n=1 [4852]                       nue   n=1 [4852]
  nue   n=1 [3832]                       nue   n=1 [3832]
  ARMED n=2 [4414, 4617]                 ARMED n=2 [4830, 4617]
  ARMED n=2 [4231, 4617]                 ARMED n=2 [5092, 4617]
  ARMED n=2 [5027, 4617]                 ARMED n=2 [4553, 4617]
  ARMED n=2 [4069, 4617]                 ARMED n=2 [5176, 4617]
  ARMED n=2 [4430, 4617]                 ARMED n=2 [5503, 4617]
```

- 1 valeur distincte pour l'événement supplémentaire (**4617**), 8 pour les coups d'arme, sur chacun
  des deux montages ;
- `4617` = la stat ATTACK d'`ultraApothecary`, lue indépendamment (`probe_204_cap_and_stat.py`) ;
- les deux porteurs rendent **la même** constante alors que leurs coups d'arme diffèrent : la valeur
  ne vient pas du descripteur, elle vient de l'AttackData ;
- OFFLINE, même montage, bonus forcé : **20/20** attaques à `4617`, `coups_arme = 1` (la formule de
  coups n'est plus augmentée), profil du groupe = celui de l'arme.

### 3.2 GÉNÉRALISATION 1 — attaquant MULTI-COUPS (`tauAunShi`, 5 coups mêlée Power)

```
  nue   n=5 [1422, 1500, 1302, 1507, 1094]
  ARMED n=6 [1220, 1319, 1217, 1267, 1221, 1304]
  ARMED n=6 [1319, 1412, 1261, 1105, 1081, 1304]
  ARMED n=6 [1728, 2375, 1871, 1942, 2485, 2101]     <- attaque sous %-mod
  ARMED n=6 [1416, 1149, 1309, 1068, 1081, 1304]
  ARMED n=6 [1180, 1472, 1533, 1110, 1133, 1304]
```

Trois choses d'un coup :

1. **la POSITION** — le coup de groupe est le **6ᵉ** événement, après les 5 coups d'arme (call-site
   INLINE, mais postérieur à la boucle d'arme) ;
2. **la VALEUR** — `1304` = stat ATTACK offline de `tauAunShi`, sur 4/5 attaques armées, quand les
   coups d'arme prennent **38 valeurs distinctes sur 40** ;
3. **la constante SUIT les %-mods** — la 3ᵉ attaque armée vaut `2101`, et ses cinq coups d'arme
   (1728 … 2485) encadrent exactement `[0,8 × 2101 ; 1,2 × 2101] = [1681 ; 2521]`. C'est
   `reduce(base)` avec le multiplicateur du moment, la même signature que `case-227` §4.2
   (`1133 = 906 × 1,25`). Le contrefactuel « +1 coup d'arme » exigerait de tirer 1304 pile quatre
   fois de suite dans une cellule de 523 valeurs.

### 3.3 GÉNÉRALISATION 2 — le gate `Psychic`, en discriminant CROISÉ

Même attaquant (`astraPrimarisPsy`, arme mêlée de profil **Psychic**), même cible, même seed, deux
porteurs :

| montage | événements par attaque armée | verdict |
|---|---|---|
| `--case master` (gate `!Psychic`) | `n=1` — **5/5**, aucun coup supplémentaire | le gate mord |
| `--case astartes` (aucun gate de profil) | `n=2`, 2ᵉ événement = **3011 × 5/5** = stat ATTACK | le gate n'existe pas là |

Le marqueur 1249 **est** bien présent sur la cible dans le premier montage (`decisionView.effects`) :
c'est donc bien la condition du descripteur, et non l'absence de pose, qui annule le coup. L'offline
reproduit les deux : `[]` contre `[3011] × 20`, avec un profil de groupe `Psychic` (celui de l'arme).

---

## 4. Non-régression

Tests rejoués (tous verts) :

| fichier | n |
|---|---|
| `test_let_the_galaxy_burn_live.py` + `test_additional_hits_amount_bounds_live.py` + `test_lot_pose_live.py` | 12 |
| `test_black_legion_1029_1020_live.py` + `test_additional_hits_roll_order_live.py` + `test_additional_hits_rounding_live.py` + `test_additional_hits_scalar_bounds_live.py` | 24 |
| `test_lord_of_tempests_ice_live.py` + `test_mv71_sniper_drone_live.py` + `test_additional_hits_after_hit_maybe_live.py` (les deux premiers embarquent `templAncient`) | 15 |
| `test_tile_term_triggered_playbooks_live.py` (face DÉCISION, playbook `AstartesBanner` 1106) | 12 |
| `test_ah_master_annihilator_astartes_banner_live.py` (**neuf**) | 3 |

Garde neuve : deux montages LIVE (un par porteur) qui asservissent leurs assertions à des
**relations** mesurées sur la session (jamais une constante de dégât en dur) — l'événement
supplémentaire est unique et vaut la stat ATTACK lue, les coups d'arme prennent ≥ 2 valeurs, et la
constante est **intérieure** à leur dispersion (sans quoi le contrefactuel ne serait pas
discriminant) — plus un test de CONTRAT offline (formule de coups inchangée, groupe attendu, face
prédiction vide, chaque gate testé isolément, y compris la non-contamination croisée du gate
`Psychic`).

---

## 5. Ce qui n'est PAS couvert

- **Le CAP `maxDmg`** (§2.3) : transporté par le natif, lu seulement par la face PRÉDICTION, et
  **inerte** dans tout régime spawnable (7477 contre une ATTACK max de 5022). Non porté, non mesuré
  en régime mordant — aucun levier de build ne permet de l'atteindre (`--rank` ne change pas le
  niveau d'ability, qui reste 50).
- **Le vecteur ABILITY** pour ces deux porteurs : le canal y est le même et le threading est
  identique (`damage_ops/ability.py` passe `damage_profile` et `attack_hit_damage`), mais aucun
  montage live n'a été monté — sur ce vecteur le groupe TIRE et coïncide avec l'ancien modèle
  (`case-227` §2.3), donc la mesure n'y serait de toute façon **pas discriminante**.
  `test_black_legion_1029_1020_live.py` garde ce vecteur pour `LetTheGalaxyBurn`.
- **`MasterAnnihilator_AdditionalHitEffect$$CreateRemoveEffectTrigger`**
  (`On(0 = UnitDeath) & AreEqual(target, EffectSource(thisEffect))` — le marqueur se retire quand SA
  source meurt) : résidu **préexistant** de `#222`, inchangé par ce cas.
- **Le crit sur un coup de groupe** : `execute_additional_hits` passe `crit_chance=0` pour TOUS les
  groupes du canal — résidu préexistant du canal, déjà nommé par `case-227` §6, no-op tant que
  `cc == 0` (le cas de toutes les mesures ci-dessus).
- **`nrOfAttacks`** (variable `MasterAnnihilator`, valeurs 1/2/3 par palier) n'apparaît dans AUCUN
  des deux descripteurs lus — elle appartient à un autre volet du kit, non investigué ici.
