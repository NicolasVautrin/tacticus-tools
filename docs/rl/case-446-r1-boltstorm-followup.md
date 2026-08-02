# #446-r1 — l'écart résiduel de `templAggressor` : ÉTAGE LOCALISÉ, CAUSE FERMÉE

Résidu §5 de `case-446-boltstorm-playbook.md` : le port restait **sous** le natif de `4.159792`
(cible entourée) et `5.639718` (cible isolée) sur `pairUtility`, invariant au cardinal `Boltstorm`,
différent par cible. Deux candidats étaient nommés — les traits `CrushingStrike` et `MkXGravis`.
**Les deux sont réfutés par mesure.** La cause est un étage **porté et INERTE**.

## 1. L'étage, localisé avant tout correctif

`probe_446_r1_pair_residual.py` décompose la paire en deux étages et nourrit le second des DEUX
feeds (le port, puis les champs NATIFS d'`aiPlaybookPredict`) :

| cible | natif | port (avant) | formule offline nourrie du NATIF | verdict |
|---|---|---|---|---|
| `T` entourée | 38.219589 | 34.059797 | **38.219589** | étage UTILITÉ exact |
| `A` isolée | 20.974451 | 15.334733 | **20.974451** | étage UTILITÉ exact |

À feed identique l'écart est **nul** : tout l'écart est en **PRÉDICTION**. Le diff champ à champ le
nomme — `appliedHits` : **natif 6, port 3**, et les bornes dans le même rapport.

## 2. Ce que dit le décompilé

L'attaque normale de `templAggressor` n'est pas la générique `69` : c'est **`1128
Boltstorm_NormalAttack`**, instanciée sur une sous-classe qui surcharge la prédiction.

```csharp
// IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$PredictAttack
base   = ALoki_NormalAttackAbility.PredictAttack(entities, abilityState);
weapon = ALoki_NormalAttackAbility.FindAttackWeapon(entities, abilityState);
if (weapon != null && !weapon.get_IsMelee()) {
    add = GetAdditionalDamagePrediction(entities, abilityState);   // scénario VIERGE
    DamagePredictionResult.Add(&add, &base);                       // add += base
    return add;
}
return base;
```

et le fold lui-même :

```csharp
// ...Boltstorm_NormalAttackAbility$$GetAdditionalDamagePrediction
amount  = <slot 4>( TalonOfHorus_NormalAttackAbility.GetAdditionalDamageAmount(...) );
          //  = DSLFormulas.RandomAmount(GetVariableForLevel(0xc), GetVariableForLevel(0xd))
hits    = AbilityConfiguration.GetNumberConstant(cfg, 0x2f);       // nrOfHits
profile = AbilityConfiguration.GetDamageProfile(cfg);
```

Le mold était **porté depuis #57c-C** (`get_additional_damage_prediction`) mais son registre de
dispatch `_RANGED_FOLLOWUP_PASSIVES` était **VIDE** — le commit d'origine le dit : « mold
Boltstorm/ProperKilly porté, ProperKilly seul dispatché ». Le porteur cherché est l'ability qui
donne son nom au mold. `unit_map find --ability Boltstorm` : **5 porteurs** — `templAggressor`
(HERO, au pool) et 4 npc `templBossAggressor*`.

## 3. Les deux corrections, et pourquoi la lecture d'origine était fausse

* **Le slot 4 n'est pas « le MIN ».** `FUN_180025fb0(4, <IAmountFormula>, <nœud>, …)` est
  `IdunBattle.DSL.AAmountFormula$$CalculateAverage` — `(min + max) / 2` en division **entière** —,
  ce que le port DSL documente déjà (`engine.dsl.base.calculate_average`, #339/#350-r3b). Sur
  `Boltstorm` à (level 50, mult 180) : `minDmg = 1496`, `maxDmg = 2194` ⇒ amount **1845**, pas 1496.
  Valeurs relevées au capteur `abilityConfigProbe` : la config est **partagée** entre le passif
  `1090` et l'active `1128` (même `cfgPtr`), 831/1219 à mult 100.
  ⚠ Piège évité : `1090` lu comme **ActiveAbilityType** est une config DIFFÉRENTE qui rend `1496` à
  mult 100 — exactement la coïncidence 831/1496 qui avait coûté deux fausses pistes à #57c-C.
* **Les modifiers de l'attaquant sont APPLIQUÉS.** Aucun argument du slot appelé ne les transporte
  (d'où la lecture d'origine « slot 0x27 SANS widgets modifiers »), mais le service de prédiction
  les recalcule. Mesuré : sur la cible isolée, le fold vaut exactement `(1329, 3183)` avec les mods
  de l'attaque porteuse (`[1.5]` — bonus d'**élévation** de `MC1_67`) contre `(885, 2121)` sans eux,
  et `natif − base_native_mesurée` vaut `(1329, 3183)`.

## 4. La base native, mesurée — c'est ce qui a débloqué l'identification

Tant que `base_natif` était supposée égale à `base_port`, aucun triplet (montant, coups, profil) ne
satisfaisait les deux cibles : les minima requis différaient de 3 alors que la branche perçage les
rend indépendants de l'armure — signature d'une décomposition fausse, pas d'un montant à trouver.

**Contrôle apparié** (même board, même seed, même layout ; seule différence
`--unit-stat "templAggressor:PassiveAbilities=[]"`, ce qui ramène l'attaque normale à `69`) :

| cible | base NATIVE mesurée | base du port |
|---|---|---|
| `T` (armure 3513) | `1302..1950`, 3 coups | `1299..1950`, 3 coups |
| `A` (armure 1507) | `1299..2970`, 3 coups | `1299..2970`, 3 coups |

Les minima requis pour le fold deviennent alors **identiques** (`1329` sur les deux cibles), et le
modèle se résout. Le `+3` sur `T` est le résidu `#446-r2` ci-dessous — **antérieur au fold**.

## 5. Mesure du fix

Runner `MC1_67`/`41504`, `templAggressor`, layout `C=(3,4) T=(1,3) A=(2,5)` :

| cible | natif | port AVANT | port APRÈS | prédiction après |
|---|---|---|---|---|
| `T` entourée | 38.219589 | 34.059797 (**−4.159792**) | 38.212089 (**−0.007500**) | `2628..3942`, 6 coups |
| `A` isolée | 20.974451 | 15.334733 (**−5.639718**) | 20.974451 (**0.000000**) | `2628..6153`, 6 coups — **identique champ à champ** |

**Généralisation** (board `C2_02`, seed `31337`, régime SANS bonus d'élévation donc mods vides, avec
et sans `--armor-target 3000`) : sur `astraBullgryn`, natif `(1752, 2628, 6)` == port, **exact**.
Un témoin sans `Boltstorm` (`ultraTitus`) ne folde pas (`followup = None`).

## 6. Contre-épreuves — les trois mordent, chacune seule

Critère = **déplacement du port par rapport au port NON MUTÉ**, jamais l'écart au natif (la paire
porte encore `#446-r2`, donc `abs(port − natif) > EPS` serait vrai même pour un mutant inerte —
le piège déjà mesuré par #446) :

| mutant | déplacement `T` | déplacement `A` |
|---|---|---|
| `no_dispatch` (registre vidé) | −4.1523 | −5.6397 |
| `amount_min` (l'ancienne lecture « slot 4 = MIN ») | −0.7875 | −2.2749 |
| `no_mods` (l'ancien `mods=None`) | −1.3824 | −1.8799 |

Les deux corrections sont donc **chacune nécessaire** : aucune ne recolle seule.

**La GATE, exercée** : caster amené au contact (arme `Power` choisie), le natif retombe aux 3 coups
de l'arme et le port avec lui — `NAT = (3903, 5850, 3)` contre `PORT = (3900, 5850, 3)`. Sans ce
cran, un port qui folderait inconditionnellement passerait tout le reste.

## 7. Candidats RÉFUTÉS, et par quelle mesure

* **`CrushingStrike` et `MkXGravis`** — contrôle apparié `--unit-stat "templAggressor:Traits=["Hero"]"`
  (même board, même layout) : le natif rend **exactement les mêmes** valeurs qu'avec les traits
  (`T` 2631..3945 / 6, `A` 2628..6153 / 6). Ni l'un ni l'autre n'intervient dans ces prédictions.
  Le `×1.5` que le fold devait porter n'est pas un trait : c'est le **bonus d'élévation** de la
  tuile de tir (il disparaît sur `C2_02`, où le fold reste exact sans lui).
* **« Le fold lit la config à chaque prédiction »** — non discriminé : le balayage
  `aiPlaybookPredict {level, multiplier}` laisse la prédiction de `1128` **invariante** (contrôle :
  le même override fait passer l'active `1048` de `16274..27044` à `33..48`, donc il MORD). Le fold
  lit l'état du passif, pas celui de l'ability normale surchargée.
* **`varTrace` sur `AbilityConfiguration.GetVariableForLevel`** : **0 entrée** pendant la prédiction
  alors que le capteur mord sur un appel de contrôle. Mesure **NON CONCLUANTE** et non retenue —
  `varTraceInstall` résout la surcharge par `findMethodByParamCount(…, 3)` et rien ne prouve que
  c'est celle qu'emprunte ce chemin.

## 8. Résidus NOMMÉS

* **`#446-r2` — 3 points de dégât sur la cible entourée, ANTÉRIEURS au fold.** Mesuré au contrôle
  apparié §4 : `1302..1950` natif contre `1299..1950` port, base nue, sans aucun fold en jeu. Vaut
  `0.0075` d'utilité à 40000 PV. **Il n'est pas propre au régime ranged** : le cran MÊLÉE du probe
  (caster amené au contact de la même cible, arme `Power`, aucun fold) le retrouve à l'identique —
  natif `3903..5850` contre port `3900..5850`, `+3` sur le seul minimum. Il ne se voit PAS sur
  `C2_02` (accord exact), donc il dépend du régime, pas de la seule identité de la cible.
  Distinctif de `T` ici : armure 3513 et trait `BigTarget` — mais `BigTarget` ne porte AUCUN
  multiplicateur dans le port, la piste reste ouverte.
* **Écart de COMPTE DE COUPS de base sur `C2_02`** — sur `astraOrdnance` : natif 4 coups, port 2 de
  base (5 avec fold). Le fold **réduit** l'écart (2 → 1) mais ne le crée pas ; c'est la formule de
  coups (`attack_hits_with_modifiers`), pas ce cas.
* **`aiPredict` et `aiPlaybookPredict` divergent** sur la cible isolée du montage (`1752..4101`
  contre `2628..6153`, rapport exactement `1.5`) alors qu'ils s'accordent sur l'autre. L'oracle de
  DÉCISION est `aiPlaybookPredict` (c'est lui que `pairUtility` consomme), donc sans effet ici.
* **`get_klaw_attack1_prediction` (mold MÊLÉE `ProperKilly`) garde `mods=None`** — non confronté,
  laissé inchangé. Si la lecture « les modifiers sont appliqués » vaut pour les deux molds, il porte
  le même défaut.
* **Un TROISIÈME mold existe et n'est pas porté** :
  `IdunBattleLogic.Entities.Abilities.Active.Loki.RighteousRepugnance_NormalAttackAbility$$PredictAttack`
  — structure IDENTIQUE au mold RANGED avec la gate **inversée** (`IsMelee != 0`). Aucun registre ne
  le dispatche ; porteurs non recensés.
* **Capteur manquant, nommé** : `IndividualHitDamage@0x80` (`List<HitDamage>`, un élément par coup)
  n'est pas exposé par `readDamagePredictionResult`. L'exposer aurait tranché la décomposition
  base/fold en une mesure au lieu d'un contrôle apparié. Point d'ancrage :
  `frida/hooks/game/damage-prediction.ts`.

## 9. Livré

* `scripts/python/engine/playbook/prediction/normal_attack.py` — registre
  `_RANGED_FOLLOWUP_PASSIVES = ("Boltstorm",)`, montant par `calculate_average`, threading des
  `mods` de l'attaque porteuse jusqu'au fold.
* `scripts/python/probe_446_r1_pair_residual.py` — décomposition par étage, hypothèse instruite,
  contre-épreuves, régime MÊLÉE.
* `scripts/python/tests/engine/test_446_r1_boltstorm_followup_live.py` — 5 gardes.
