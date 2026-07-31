# case-342 — le levier BOUCLIER, et le terme bouclier du dégât CONFRONTÉ

Deux questions binaires, toutes deux tranchées par mesure :

1. **Où se perd `rl_duel build --unit-stat "<u>:Shield=N"` ?** → le BC l'écrit, **le natif ne le
   lit jamais**. `BC.Units[].Shield` n'est pas un levier de déploiement, et ne l'a jamais été.
2. **L'arrondi que #333 a appliqué au terme BOUCLIER par symétrie est-il JUSTE ?** → **OUI**,
   `MidpointRounding.ToEven`, discriminé live sur les deux parités et trois montages.

---

## 1. `BC.Units[].Shield` est INERTE — lu au décompilé (`rnca9r7q6c`), pas déduit

`UnitConfiguration.Shield` est à l'offset **`+0x4c`** (`classFields` live : 37 champs, 200 octets
de champs). Quatre lectures, qui se referment l'une sur l'autre :

| symbole | ce qu'il dit |
|---|---|
| `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` | la fonction qui **remplit** chaque `BC.Units[]` écrit 29 champs et **saute `+0x4c`** |
| `IdunBattle.Operations.AddUnitOperation$$Execute` | le déploiement (1363 lignes décompilées) n'accède **jamais** à `+0x4c` et n'émet aucune `CreateShieldOperation` |
| `IdunBattle.Entities.Components.ShieldComponent$$.ctor` | n'alloue qu'une `List` **VIDE** — aucun paramètre, aucune valeur initiale (appelé par `IdunBattle.Entities.Blueprints$$Unit`) |
| `IdunBattle.Entities.Components.ShieldComponent$$AddOrUpdateShield` | **unique** écrivain de cette liste, et il n'a **qu'un appelant** : `IdunBattle.Operations.CreateShieldOperation$$Execute` |

⇒ Un bouclier ne peut naître que d'une `CreateShieldOperation`, elle-même émise par un des **neuf**
appelants de `IdunBattleLogic.Entities.DSLBehaviors$$CreateShield` : `APowerUpAbility$$AddShield`,
`ArcaneShieldAbility`, `EnvCapturePointShieldAbility`, `EnvReinforcementShieldAbility`,
`EnvStartProtectionAbility`, `ShieldOfFaithAbility`, `TauntAbility`, `WrathfulDevotionAbility`,
`NovaShieldAbility`. Aucun n'est sur le chemin du déploiement.

Cohérent avec la donnée : les **175** unités de `data/seed-bc.json` ont `Shield = 0`.

**Mesure aux deux bouts** (`probe_342_shield_term_rounding.py --part field`) — elle sépare les trois
hypothèses au lieu de les supposer :

```
--unit-stat genesPrimus:Shield=6000 -> accepte par le montage : OUI
  BC ENVOYE a initAndStart : Units[genesPrimus].Shield = 6000   (ECRIT)
  bataille (combatSnapshot) : shields = []                      (AUCUN bouclier)
```

Ni l'outil Python ni `buildNormalizedBC` ne perdent la valeur (ce dernier ne touche pas au champ).

⚠ **Le bouclier fonctionne parfaitement en bataille** — c'est le *posage par le harnais* qui
n'existait pas. Ne pas lire ce cas comme un bug de moteur.

`rl_duel build` **le dit désormais** (`[warn]` sur `--unit-stat <u>:Shield=N` non nul) : accepté
sans erreur puis silencieusement ignoré est exactement la dégradation qui a coûté ce résidu.

## 2. Le levier réel : faire POSER le bouclier en bataille

`ArcaneShieldAbility` (`thousSorcerer`, porté et gardé par #N1) est le plus contrôlable : son
trigger `On(0x1c = ArrivedAtFinalTile)` fire au **1er déplacement** de son porteur — le
`place_ring` du montage suffit donc à le déclencher, sans action dédiée.

**Recette** : mettre `thousSorcerer` **dans l'équipe de la victime** (`--a-units "<victime>,thousSorcerer"`).
Il accorde le bouclier à son meilleur voisin allié — la victime, seule candidate. Mesuré au rank
17 : **5483 points, 2 tours**, `shieldBefore` non nul dans `aiPlaybookPredict`.

Trois autres porteurs `lineup`/MoW existent si le montage l'exige : `adeptExorcist` (MoW,
`ShieldOfFaith`), `worldTerminator` (`WrathfulDevotion`), plus les env-abilities de board.

## 3. Piloter la PARITÉ du terme bouclier

En régime « tout passe au bouclier » (`Damage` bas), les deux bornes valent `hits × round(k × Damage)` :
la somme est **toujours paire**, aucun `.5` n'existe, la mesure serait vide.

Le régime utile est celui du **CAP** : dès que le dégât max dépasse le bouclier,
`AccurateShieldDamage.Max` est figé à `shieldBefore` (**5483, impair**) pendant que `Min` reste
multiple du nombre de coups (**pair**) — la somme est alors **impaire**, et un pas de **1** sur
`--unit-stat "<attaquant>:Damage=D"` fait basculer la parité de la partie entière. C'est le pendant
exact du `--hp-target` de #333.

## 4. La mesure — `probe_342_shield_term_rounding.py`

Les quatre variantes remplacent la **seule** méthode `DamageUtility.get_shield_damage` (le terme
SANTÉ garde son arrondi natif) : sans cette isolation, le terme santé suffirait à expliquer l'écart.
Une 5<sup>e</sup> mesure, `current`, évalue le port **sans aucun patch** — sinon la garde ne
verrouillerait que le catalogue de variantes, pas le moteur.

`ultraInceptorSgt -> genesPrimus`, board `MC1_67`, bouclier 5483, `combinedMax` 12511,
`pas = 100/combinedMax = 7.993e-3` :

| bras | `Damage` | shieldDmg | somme | floor | natif | `to_even` | `half_up` | `kept_half` | `trunc` |
|---|---|---|---|---|---|---|---|---|---|
| UP | 762 | `[3660, 5483]` | 9143 impaire | 4571 **impair** | 36.5438 | **0** | 0 | **+0.5 pas** | **+1 pas** |
| DOWN | 764 | `[3666, 5483]` | 9149 impaire | 4574 **pair** | 36.5838 | **0** | **−1 pas** | **−0.5 pas** | 0 |

⇒ **`to_even` est la SEULE variante nulle sur les DEUX bras.** L'arrondi du terme BOUCLIER est
**JUSTE**, plus seulement plausible.

**Généralisation** (le même protocole, ailleurs) :

| montage | bouclier | bras UP / DOWN | verdict |
|---|---|---|---|
| `ultraInceptorSgt -> genesPrimus`, `MC1_67`, anneau (3,4) | 5483 | `Damage` 762 / 764 | OK |
| `emperNoiseMarine -> necroWarden`, `MC1_67`, anneau (3,4) | 5483 | `Damage` 1525 / 1527 | OK |
| `ultraInceptorSgt -> genesPrimus`, **`C1_03`**, anneau (3,6) | 5483 | `Damage` 762 / 764 | OK |

## 5. Gardes

`tests/engine/test_342_shield_term_rounding_live.py` (8 tests) : le champ `BC.Units[].Shield` écrit
mais jamais matérialisé ; le terme bouclier réellement exercé (bouclier posé **et** borne haute
capée **et** somme impaire) ; les deux parités ; `to_even` seul mode nul des deux côtés ; le port
**en vigueur** égal au natif ; la mutation.

**Mutation jouée** (`get_shield_damage` remis à `(min+max)/2.0` dans `engine/utilities/damage.py`) :
**2 rouges**, écart mesuré `+0.500` pas sur le bras UP.

## 6. Ce qui n'est PAS couvert

- **La FORMULE de `AccurateShieldDamage`** n'est pas portée : le split santé/bouclier vient du feed
  natif (`aiPlaybookPredict`). Mesuré au passage : hors régime de cap le split est trivial
  (`healthDmg = [0,0]`), mais dans le régime de cap `shieldDmgMin` **n'est pas** `min(shield, totalDmgMin)`
  (ex. `[3875, 5483]` pour `totalDmg [4813, 6005]`) — `IdunBattle.Core.Services.DamagePrediction$$CalculateDamagePredictionScenario`
  n'a pas été relu ici. Résidu nommé.
- **La face COMBAT du bouclier** : `engine/runner/operations/damage_utility.py` rend toujours
  `shieldBefore = 0` (résidu pré-existant, hors périmètre). Ce cas ne touche que la face DÉCISION.
- **Aucun renversement de DÉCISION** n'a été construit : l'écart vaut un demi-pas d'utilité.
- **Les autres porteurs de bouclier** (`ShieldOfFaith`, `WrathfulDevotion`, `NovaShield`,
  `Taunt`, les env-abilities) ne sont pas exercés — un seul vecteur suffisait à débloquer le terme.
- **Autres champs de `BC.Units[]` non honorés** : non recensé. Seul `Shield` est mesuré ici ; les 8
  champs que `GetUnitConfiguration` n'écrit pas sont soit posés par le ctor
  (`TertiaryAbilityVariablesMultiplierPercentage` = 100), soit par
  `BattleConfigBuilder$$SetupAbilities` (les niveaux et listes d'abilities) — `+0x4c` est le seul
  qu'aucun des deux ne touche.
