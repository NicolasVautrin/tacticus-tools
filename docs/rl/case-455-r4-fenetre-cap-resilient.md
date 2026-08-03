# #455-r4 — le rouge de `test_env_fire_tile_dot_applies_resilient_cap_live` accusait le MONTAGE

`scripts/python/tests/engine/runner/test_env_fire_tile_migration_live.py::test_env_fire_tile_dot_applies_resilient_cap_live`
était **ROUGE sur `master`** (`a86cdab4`) sur `pytest.fail("cible morte avant la fenetre
discriminante")`. Trouvé par l'échantillon de #455, laissé hors périmètre.

**Verdict : MONTAGE.** Le port du cap `Resilient` est un mirror exact du natif, et le natif cape
bien live. C'est le PILOTAGE qui ne pouvait pas amener la cible dans la fenêtre où le cap
discrimine — ni y mesurer le tick isolément.

## 1. Ce que le natif fait (décompilé)

`IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` :

```
if (!isGuaranteedOverkill)
    if (HasTrait(defender, 0x3f1 /*Resilient*/) && initialHealth > 1 && currentHealth > 0)
        y = Fix64(currentHealth - 1);
        if (damage > y) { denied = damage - y; *damage = y; return denied; }
return Fix64(0);
```

et son appelant `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage` calcule
le 6ᵉ argument par
`IsOverkill(initialHealth, (initialHealth - currentHealth) + previousHitsDeniedDamage + minDamage, isCrit, isForcedOverkill, HasFlag(defender,0x13), cfg@+0x30, cfg@+0x34, minimumHealth)`.

Pour un tick de DoT isolé (`currentHealth == initialHealth`), l'accumulateur vaut le tick lui-même,
donc `IsOverkill` est vrai dès que `dot >= 2 x hp` (seuil `overkillDmgPctOfHealth` = 100). **La
fenêtre où le cap discrimine est donc `(dot/2, dot]`** — au-dessus le cap ne mord pas
(`dmg <= hp-1`), en dessous il est bypassé et la cible meurt. Le port
(`engine/services/trait_damage_limits.py`) est le mirror 1:1 des deux fonctions ; rien à y corriger.

## 2. Pourquoi le montage ne pouvait pas y arriver — deux causes, mesurées

`probe_455r4_resilient_window.py --volet descente` (seed 90101, `MC1_67`, `--hp-target 500000`,
`dot = 100000`, fenêtre `(50000, 100000]` **large de 50 000**) :

| tour | hp | pas observé |
|---|---|---|
| 2 | 500000 | 108583 |
| 3 | 391417 | 109269 |
| 4 | 282148 | 109829 |
| 5 | 172319 | 110416 |
| 6 | 61903 | 61902 (cap `Resilient` — hp -> 1) |
| 7 | 1 | mort |

1. **Le pas de descente (~110 000) dépasse la fenêtre entière (50 000).** Y atterrir tenait du
   tirage. Le tour 6 y arrive (hp 61903) mais la tuile ne brûlait pas cet instant-là — la boucle
   ré-attaque, et le tour d'après tue.
2. **L'attaque terminait l'activation de la SEULE p-unit**, donc le tour basculait tout seul et le
   tick de début de tour adverse tombait dans le même geste : `dmg_attaque` observé = attaque
   (~8 600-10 400) **+** tick (100 000), jamais séparables. Contre-mesure du même montage :
   `--volet tick` isole le tick (391417 -> 291417 = **100000**, exactement `dot`) uniquement parce
   qu'il n'attaque pas ce tour-là.

## 3. Le montage réparé — deux leviers

* **`--unit-stat "astraYarrick:RemainingHealth=<v>"`** pose les PV COURANTS dans la fenêtre au build,
  au lieu d'y descendre à l'aveugle. **Le champ MORD** (mesuré : `hp=80000` pour `hpMax=500000`) —
  vérification nécessaire, `Shield` est le contre-exemple d'un champ de `BC.Units` écrit et jamais lu
  (#342). `v = 0.9 x dot` laisse la marge de l'unique attaque qui pose le feu.
* **une 2ᵉ p-unit JAMAIS activée** (`astraDreir`, passif `ToughToKill` = regen + réduction SELF,
  aucune aura sur la cible) : tant qu'une unité de mon camp n'a pas agi, le tour **ne bascule pas**
  après l'attaque, donc le tick reste à venir et se mesure SEUL. Même ressort que le `FOE_IDLE` de
  `probe_213`.

L'approche se fait **sans attaquer** (`_approach_only`), donc aucun feu, aucun tick, et les PV
restent ceux du build jusqu'à l'unique attaque. Les trois assertions du test sont **inchangées** ;
s'y ajoutent quatre gardes de montage qui échouent FRANCHEMENT (jamais un skip) : cible vivante
après l'attaque, `currentPlayer` toujours à moi, tuile en feu, PV dans la fenêtre re-dérivée de
l'état.

Mesure du montage réparé : hp 90000 -> attaque -> **81417, `currentPlayer` maintenu**, tuile en feu
-> tick -> **alive, hp = 1, tick = 81416 = hp-1**.

Le montage est factorisé en `_stage_burning_at(..., start_ratio)` — c'est lui qui rend possible, au
même coût, la garde du bord opposé (§5).

## 4. Le choix de tuile dépendait du board — corrigé aussi

`_approach_only` déduisait sa tuile de la géométrie hexagonale bornée par `W, H = 7, 9` (les
dimensions de `MC1_67`). Sur `C3_01` cette déduction restait **bloquée à distance 5 pendant 8
tours** : un « distance 2 non atteinte » qui se lit comme une limite du montage alors que c'est une
limite du choix de tuile. Les candidates viennent désormais d'**`aiMovableTiles`** (le BFS natif,
creusé par blockers/terrain). Effet de bord mesuré : à périmètre égal (3 tests) le fichier passe de
**120 s à 36 s** ; il rend 4 tests en 45 s.

## 5. Validation adversariale

**Contre-épreuves de mutation** (chacune restaurée et re-vérifiée) :

| mutation | attendu | observé |
|---|---|---|
| `apply_resilient_trait_damage_limit` neutralisée (PORT) | rouge sur l'accord port/natif | `AssertionError: port 100000 != natif 81416` |
| 2ᵉ p-unit retirée (MONTAGE) | rouge franc sur la garde de bascule | `currentPlayer=4, me=3 ... l'unite inerte n'a pas joue son role` |
| `--unit-stat RemainingHealth` retiré (MONTAGE) | rouge franc sur la garde de fenêtre | `PV 491417 hors de la fenetre discriminante (50000, 100000]` |
| gate `IsOverkill` du port ignoré (`if not overkill:` -> `if True:`) | rouge | `le port laisse la cible a 1 PV la ou le natif la TUE` |

**La 4ᵉ mutation a d'abord passé au VERT** — et c'est ce qui a fait ajouter
`test_env_fire_tile_dot_resilient_cap_bypassed_on_overkill_live`. Le test réparé ne joue que le
régime `(dot/2, dot]`, où `overkill` vaut Faux de toute façon : un port qui caperait **toujours**
serait resté vert. La seconde garde monte le régime opposé (`start_ratio = 0.4`) et exige que le
port TUE comme le natif. Le trou n'était pas supposé : il a été mesuré, puis fermé.

**Généralisation** — `--volet frontiere` balaie les trois régimes de part et d'autre des DEUX bornes,
sur **deux couples (board, seed)** :

| PV avant tick | régime attendu (RE) | `MC1_67`/90101 | `C3_01`/31337 |
|---|---|---|---|
| `> dot` | cap inerte, survit à `hp - dot` | 111417 -> 11417 | 107199 -> 7199 |
| `(dot/2, dot]` | cap actif -> `hp = 1` | 81417 / 56417 -> 1 | 77199 / 52199 -> 1 |
| `<= dot/2` | `IsOverkill` -> bypass -> MORTE | 46417 / 31417 -> morte | 42199 / 27199 -> morte |

La borne basse est encadrée à ~4 800 près (52199 capé / 46417 mort, frontière théorique 50000).

**Non couvert** : (a) la borne HAUTE (`hp > dot`, cap inerte) reste **mesurée par le probe, non
gardée** — un port qui caperait au-dessus de `dot` ne serait vu par aucune assertion (résidu
**#455-r4-r1**) ; (b) le cap n'est confronté que sur le porteur `astraYarrick` et le seul profil
`Flame` du DoT de tuile ; (c) `_drive_until_burning` (le test `defender_modifiers`) garde la
déduction hexagonale bornée par `W`/`H` — il n'a pas été touché, et reste donc `MC1_67`-dépendant.

## 6. Ce que ce cas apprend

**Un rouge live sur `master` est structurellement invisible de la validation de PR** : la banque de
cliquets ne couvre que l'offline (`probe_457` exclut `_live.py`). Ce test a survécu depuis
`ad5692e7` sans que rien ne le voie. C'est une limite connue et assumée du périmètre, pas un
garde-fou à réparer ici.

**Le message d'un `pytest.fail` est une HYPOTHÈSE de l'auteur, pas une mesure.** « cible morte avant
la fenêtre » disait vrai sur le fait et faux sur la cause : ce n'était pas « il faut la garder en
vie plus longtemps », c'était « le pas de descente dépasse la fenêtre » **et** « le tick n'est pas
isolable ». Le second n'apparaît dans aucun message — il a fallu le mesurer.
