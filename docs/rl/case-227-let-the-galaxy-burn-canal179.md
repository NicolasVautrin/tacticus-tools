# case-227 — `LetTheGalaxyBurn` : le « +1 coup » est un GROUPE du canal #179, et sa valeur dépend du VECTEUR

**Critère binaire** : *« le coup surnuméraire de `LetTheGalaxyBurn` vaut-il, offline, ce qu'il vaut
en natif — et sort-il du bon canal ? »*

**Réponse** : **NON** avant ce cas, sur le vecteur ATTAQUE NORMALE — il en sortait une valeur
**tirée** là où le natif rend une **constante** (mesuré : live 1909 sur 8 attaques armées, port
1570…2275). **OUI** désormais, sur les DEUX vecteurs, bit-exact live.

Le budget de tirages, lui, était déjà juste (1 tirage des deux côtés) : **aucun compteur de flux RNG
ne pouvait voir ce bug** — c'était un écart de VALEUR pur.

---

## 1. La tension à lever — verdict : **les deux constats sont VRAIS et COMPATIBLES**

| constat | vecteur mesuré | statut |
|---|---|---|
| `case-159` §3.2 — le coup natif est une CONSTANTE, le port tire | ATTAQUE NORMALE | **VRAI** |
| `case-bl-1029-1020` §5.4 — `blackHaarken` bit-exact avec le modèle « +1 coup d'ARME » | ABILITY (`HeraldOfTheApocalypse`) | **VRAI** |

Aucun des deux n'est faux. Ce qui manquait, c'est **la mécanique qui les réconcilie** — et elle se
lit intégralement au décompilé (§2) : le degré de liberté n'est pas le vecteur, c'est le
`HitDamage` de l'`AttackData`, dégénéré sur l'un et pas sur l'autre.

---

## 2. RE — ce que rend vraiment `FirstHitInCurrentAttackDamageRange`

### 2.1 Le descripteur

`IdunBattle.Entities.Effects.Loki.LetTheGalaxyBurnEffect$$CreateAdditionalHits`, lu verbatim
(build `gqfc5mff6c`) :

```
EffectAdditionalHits$$Create(
    condition   = get_OwnerIsCaster & ( LetTheGalaxyBurnAbility$$TargetHasTileEffect
                                      | IsPersistentData(0x5ca, Self@0x148, Get(<statique>)) ),
    amountNode  = FirstHitInCurrentAttackDamageRange(),   # +0x08  ROLL
    profileType = -1  (Nullable NULL),                    # +0x28
    countNode   = 0   (-> defaut 1),                      # +0x18
    minNode     = FirstHitInCurrentAttackDamageRange())   # +0x10  DISPLAY (2e instance)
```

C'est un **descripteur `EffectAdditionalHits`** — le même artefact que SquigHound/CordClaw/
FleshmetalGuns. Ce n'est **pas** un `EffectHitsBonusForAttack`. Le port l'implémentait pourtant en
`create_effect_hits_bonus_for_attack` (un `+1` de la **formule de coups**) : **fork de port**, une
face native pour deux façades offline.

Deux autres effets partagent le même nœud, et le même fork subsiste chez eux (résidus nommés, §6) :
`MasterAnnihilator_AdditionalHitEffect` et `AstartesBanner_AdditionalHitsEffect`.

### 2.2 Le nœud, de l'écriture à la lecture

**Qui écrit.** `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits`, après chaque coup :

```
List<T>.Add( currentAttack@+0x50, <les 16 premiers octets de l'AttackData> )
```

et le champ 0 de l'`AttackData` **est** son `IdunBattle.Core.HitDamage` — c'est exactement celui que
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` passe en tête de coup à
`IdunBattle.Core.HitDamage$$GetDamage`. La liste `currentAttack@+0x50` est créée par
`IdunBattle.Core.OngoingAttack$$.ctor` ; l'`OngoingAttack` est empilé une fois par attaque
(`IdunBattle.Core.MatchState$$StartAttack`).

**Qui lit.** Les trois accesseurs du nœud font `ListExtensions.FirstOrDefault` sur cette liste
(champ `AbilityEntities@+0xF8`, posé par
`IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` depuis
`currentAttack@+0x50`) :

| accesseur | rend |
|---|---|
| `IdunBattle.Entities.Formulas.FirstHitInCurrentAttackDamageRange$$CalculateMin` (slot 2) | `.min` |
| `…$$CalculateMax` (slot 3) | `.max` |
| `…$$Calculate` (slot 4, canal DISPLAY) | `HitDamage$$GetDamage(., rng, useAverage = 0)` |

Liste vide / pas d'attaque en cours → les trois rendent **0**.

⇒ le dégât du groupe est **le `HitDamage` de l'ATTAQUE COURANTE**, pris **BRUT** (avant spread,
avant perçage). Il est constant d'un coup à l'autre : c'est un champ de l'`AttackData`, pas une
valeur par coup — « FirstHit » ne désigne donc pas « la valeur du premier coup » mais « la plage
enregistrée au premier coup ».

### 2.3 Le pivot : `HitDamage$$GetDamage`, lu verbatim

```
if (min == max)   return min ;                      # 0 tirage
if (useAverage)   return (min + max) / 2 ;          # division ENTIERE
return rng.Range(min, max + 1) ;                    # 1 tirage
```

C'est **ce gate `min == max`** qui produit toute la différence entre les deux vecteurs :

| vecteur | `AttackData.HitDamage` | `GetDamage` | valeur du coup LTGB | tirages |
|---|---|---|---|---|
| **attaque NORMALE** | **DÉGÉNÉRÉ** `(base, base)` (c'est ce qui donne 1 tirage/coup) | court-circuit | `reduce(base)` — **CONSTANTE** | 1 (le resolve slot-8 gaspillé) |
| **ability bounds-mode, famille ATTACK** | `[minDmg, maxDmg]`, NON dégénéré | **TIRE** | `reduce(tirage)` — ALÉATOIRE | 2 (tirage + resolve) |

Sur le vecteur ABILITY, cela **coïncide exactement** avec l'ancien modèle « +1 coup d'ARME » : mêmes
bornes brutes, même `reduce`, même resolve, même position dans le flux. D'où le bit-exact de
`case-bl-1029-1020` — **fortuit, mais réel**. Sur le vecteur NORMAL, l'ancien modèle tirait dans la
cellule d'arme *déjà réduite* : c'est là, et là seulement, que le port divergeait.

### 2.4 Le profil NULL n'est pas un détail : il choisit le call-site

`profileType = -1` (Nullable NULL) ⇒ le groupe est exécuté par
`AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` (qui filtre justement sur ce
champ), appelée **INLINE** par `AttackDamageOperation$$Execute` — donc **avant** les groupes à
profil, qui partent en sous-opérations planifiées
(`ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute`). Le coup emprunte alors le **profil
de l'arme** (perçage, trait `NoBlocking`, `RegisterDamage`).

Cohérent avec la décomposition de tirages de `case-159` §2.c : LTGB (1 tirage) **avant** les 2 coups
FleshmetalGuns (4 tirages).

### 2.5 Face PRÉDICTION

`IdunBattle.Entities.Abilities.AActiveAbility$$GetAdditionalHitsFromEffectsForPrediction` tourne
**hors de toute `OngoingAttack`** ⇒ `currentAttack@+0x50` est vide ⇒ le nœud rend **0** sur ses trois
accesseurs ⇒ le groupe prédit est un coup à **0 dégât** (no-op numérique), et
`IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` n'est **pas** augmenté (ce n'est pas un
`EffectHitsBonusForAttack`).

Le port ajoutait, lui, **un coup d'arme PLEIN** à la prédiction dès que la cible se tenait sur une
tuile à status-effect : sur-prédiction d'un coup entier. Corrigé.

---

## 3. Le port

| avant | après |
|---|---|
| `LetTheGalaxyBurnEffect.create_effect_hits_bonus_for_attack` → `for_addition(True, 1)` | `LetTheGalaxyBurnEffect.additional_hit_groups` → `[{count: 1, min: hd0, max: hd1, profile: None}]` |
| gate threadé dans `attack_hits_with_modifiers` (`tile_effects_by_pos`, `attacker_persistent_data`) | gate threadé dans `collect_additional_hit_groups` (`t_pos`, `tile_effects_by_pos`, `persistent_data`) **+** `attack_hit_damage` |
| — | `execute_additional_hits` : `profile is None` → profil de l'attaque (`attack_profile`) ; groupes sans profil exécutés **en premier** |

`attack_hit_damage` = le `HitDamage` BRUT de l'attaque : `(ATTACK, ATTACK)` sur le vecteur normal
(`damage_ops/normal.py`), `(base_min, base_max)` **avant max-out** sur le vecteur ability
(`damage_ops/ability.py` — le natif applique `IsAttackMaxOutDamage` dans `ExecuteHit`, pas sur
l'`AttackData` enregistrée).

Les deux paramètres `tile_effects_by_pos` / `attacker_persistent_data` ont **quitté**
`attack_hits_with_modifiers` : `LetTheGalaxyBurn` en était le seul consommateur, les laisser aurait
été un gate mort.

`abilities/blacklegion.py` (`HeraldOfTheApocalypse`) expose désormais `additional_hits` dans son
diag `attacks` — sans quoi la séquence d'événements de dégât qu'il rend est **tronquée** et le
confront per-coup vs live faussement rouge.

---

## 4. Mesure

### 4.1 Vecteur NORMAL — `probe_227_ltgb_channel.py` (`blackTerminator` « Angrax » vs `bloodSanguinary`, `MC1_67`, `--crit 0,0 --block-target 0,0`)

Statistique du dernier événement de dégât des attaques **armées** (base+1 événements) :

| passe | attaques armées | dernier événement | coups d'ARME de la même attaque |
|---|---|---|---|
| probe, 2 builds | 14 | **1909** ×14 | 1530 … 2258 |
| probe, 1 build | 2 | **1909** ×2 | 1624 … 2282 |
| garde live (test 1) | 8 | **1909** ×8 | 1570 … 2275, **55 valeurs distinctes** |

`stat ATTACK` d'Angrax = **1909**, armure de la cible = 0 (`--hp-target` la met à 0) ⇒
`reduce(base) = 1909` **exactement**, soit le milieu de la cellule d'arme `[0.8·A, 1.2·A]` =
`[1527, 2291]`.

- port livré (groupe #179) : **24/24** ;
- contrefactuel « +1 coup d'ARME » (ancien port) : **0/24** — il faudrait tirer 1909 pile,
  ~1 chance sur 765 par attaque.

Offline, même montage, branche `TargetHasTileEffect` forcée : coup de groupe = **1909** sur 60/60
attaques (et sur les 88 attaques armées du run à 300).

### 4.2 GÉNÉRALISATION — 2ᵉ porteur, attaque à DISTANCE, groupe profilé coexistant

`probe_227_ltgb_channel.py --carrier blackObliterator --target necroWarden --dist 3` (Volk, arme
ranged, porteur du cycle `FleshmetalGuns` → 2 coups de groupe **à profil** en plus). Séquence live
d'une attaque armée : **6 coups d'arme, puis 1 coup, puis 2 coups FleshmetalGuns** (9 événements ;
8 quand le `Maybe` n'arme pas).

| | valeur |
|---|---|
| live, événement d'**index 6** sur les attaques armées | **1133** — **7/7** |
| live, index 6 sur les attaques NUES (témoin) | 1106 / 1301 / 1264 — varie |
| offline, 1ᵉʳ coup de groupe (groupe SANS profil) | **1133** — 12/12, `coups_arme = 6` |
| tous les événements de la campagne | 73 valeurs distinctes, 759 … 1829 |

Deux choses sont prouvées d'un coup :

1. **la VALEUR** — `1133 = 906 (stat ATTACK) × 1,25` (`HeavyWeapon_ExtraDmg`, l'attaquant ayant
   bougé). C'est **exactement** le chiffre mesuré par `case-159` §3.2 sur ce même montage, ici
   re-dérivé de l'`ATTACK` stat au lieu d'être lu comme « milieu de la cellule d'arme ». Sur une
   passe où l'attaquant n'avait **pas** bougé, la même position vaut **906** — la constante suit les
   %-mods de l'attaque, comme doit le faire `reduce(base)` ;
2. **l'ORDRE** — la constante est à l'index 6, **avant** les 2 coups FleshmetalGuns. Le groupe sans
   profil (`ExecuteAdditionalHitsWithoutDamageProfileType`, inline) passe donc bien avant les groupes
   à profil (sous-opérations planifiées). C'est la seule mesure live de cet étage.

### 4.3 Vecteur ABILITY — non-régression

`tests/engine/runner/test_black_legion_1029_1020_live.py` : **10/10 verts**, per-coup **bit-exact**
sur les deux géométries, coup `LetTheGalaxyBurn` compris :

```
(777, MC1_67)  live {77:[1738,1979,1846], 79:[1805,1632,1536]}
               offline arme {77:[1738,1979], 79:[1805,1632]} + groupe #179 {77:[1846], 79:[1536]}
```

Les deux valeurs de groupe **diffèrent** (1846 vs 1536) : sur ce vecteur le coup est bien **tiré**,
comme le prédit §2.3 — et le port le reproduit à l'unité.

---

## 5. Ce que ça change pour l'IA

Le nombre de coups rendu par `GetAttackHits` **baisse de 1** pour un porteur Black Legion dont la
cible est sur une tuile à status-effect, et la prédiction perd le dégât correspondant. C'est une
**correction** : la prédiction native n'a jamais compté ce coup (§2.5). L'ancien port sur-estimait
d'un coup plein (≈ +25 % sur une attaque à 4 coups) exactement dans le régime où le kit pose lui-même
`DespoiledGround` sous sa cible — donc en permanence après le premier succès du `Maybe`.

---

## 6. Ce qui n'est PAS couvert

- **`MasterAnnihilator_AdditionalHitEffect` et `AstartesBanner_AdditionalHitsEffect`** : même nœud
  `FirstHitInCurrentAttackDamageRange`, **même fork de port** (rendus en `hits_malus_for_defense` /
  `aura_hits_bonus_for_attack`). Leur correction demande son propre montage live (porteurs
  `blackPossession` « Vitruvius » côté défenseur avec un cap `ConfigVar(0xd)`, et l'aura Astartes) :
  hors périmètre d'un cas « un seul sujet », résidus **nommés** dans les docstrings.
- **Le crit sur un coup de groupe** : `execute_additional_hits` passe `crit_chance=0`,
  `crit_enabled=False` pour TOUS les groupes du canal, alors que le natif fait passer ces coups par
  `AttackDamageOperation$$ExecuteHit`, qui roule un crit. Résidu **préexistant** du canal, pas
  introduit ici — strictement no-op tant que `cc == 0` (le cas de toutes les mesures ci-dessus, et
  le défaut des runners), mais un porteur LTGB à `cc > 0` désynchroniserait le flux. Non mesuré.
- **Le volet `DespoiledGround`** (effet 1476 + `DespoiledGround_ExtraDamagePct` 1478) — porté
  entre-temps par `#85` (`runner/operations/triggers/loki/despoiled_ground.py`, arrivé sur `master`
  pendant ce cas). Ce cas ne le touche pas ; le rebase le prend et les gardes des deux côtés sont
  vertes (`test_despoiled_ground_live.py` 5/5, `test_let_the_galaxy_burn_live.py` 3/3).
- **Le régime `useAverage = true`** de `HitDamage$$GetDamage` (division ENTIÈRE, donc ≠ `Round`)
  n'est emprunté par aucun chemin de combat porté — lu, non exercé.
- **La face PRÉDICTION n'a pas été confrontée live** : la RE est complète et le port en découle (le
  nœud rend 0 hors `OngoingAttack`), mais aucune mesure `aiPredict` n'a été montée sur une cible
  posée sur une tuile à status-effect. C'est le seul volet du cas dont la validation est
  **structurelle** et non **mesurée**.
