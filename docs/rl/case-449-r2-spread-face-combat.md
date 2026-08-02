# #449-r2 — face COMBAT : le même byte, mais c'est le BEHAVIOUR qui l'écrit

`#449` a établi que, côté PRÉDICTION, le slot de montant **applique** le spread ±20 %. La question
ouverte était : le fait-il aussi côté COMBAT ? **Non — et pour une raison structurelle, pas
accidentelle.** Les deux faces traversent le **même** embranchement natif ; ce qui diffère, c'est
**qui écrit le byte qui l'aiguille**.

Verdict : les `spread_pct=0` / `amount_spread_pct=0` de la face COMBAT sont **JUSTES**. Aucune
correction de port. Ce qui change, c'est qu'ils sont désormais **lus** au lieu d'être supposés, et
**gardés** dans les deux sens.

## 1. La chaîne, lue de bout en bout (build `rnca9r7q6c`)

```
<Ability>$$CreateBehaviour         8e arg = Nullable<AttackDamageBehaviourOptions>  (0x28 octets)
  -> IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage  (ou $$AttackDamage)
  -> IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$.ctor
         Nullable<T>.GetValueOrDefault(options) -> les 0x28 octets sont deposes a `this+0x98`
         donc l'octet d'aiguillage (options+6) EST `behaviour+0x9e`
  -> IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget
         options+0x2f  <- behaviour+0x9e
  -> IdunBattle.Operations.AttackDamageOperation$$ExecuteHit
         request+0x6a  <- options+0x2f            (requete = le memset(0xb8), meme struct qu'en #449)
  -> IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw
         if (request+0x6a == 0)  -> MinMaxDamageFix64(d, maxOverride ?? d)      [PLAT]
         else if (configuration+0x31 != 0) -> MEME branche PLATE
         else                    -> DamagePrediction$$GetBaseDamageFix64        [SPREAD +-20 %]
```

**Le corps d'arrivée est le même que celui de #449** — même fonction, même byte, même
embranchement (relu ici : le test est `in_R8[0xd]._2_1_`, soit l'octet `+0x6a` du qword `+0x68`).
Ce qui change est **en amont** :

| face | qui écrit `request+0x6a` | valeur |
|---|---|---|
| PRÉDICTION (#449) | `DamagePredictionQuery$$GetAttackPrediction`, ses **trois** surcharges | `1` **EN DUR** → spread toujours |
| COMBAT (ce cas) | `AttackDamageOperation$$ExecuteHit`, depuis les options du behaviour | **variable**, écrite par l'ability |

⇒ **la conclusion de #449 ne se transporte pas**, dans aucun des deux sens. Côté combat, il faut
lire l'ability.

## 2. Ce que les porteurs passent, lu ability par ability

**Les trois portent le Nullable VIDE** — les 0x28 octets sont mis à zéro juste avant l'appel :

* `IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$CreateBehaviour`
  (`local_78 … local_58 = 0`, passés en `&local_78`)
* `IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$CreateBehaviour`
  (`local_88 … local_68 = 0`, passés en `&local_88`)
* `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTriggerBehaviour`
  (`local_328 … local_308 = 0`, passés en `&local_328` — ici la factory est
  `DSLBehaviors$$AttackDamage`, la feuille nue, pas son enveloppe `AttackWith…`)

`GetValueOrDefault` sur un Nullable vide rend `default` — tous champs à zéro. Donc
`behaviour+0x9e = 0` → **branche PLATE**.

**La contre-preuve qui interdit de généraliser** :
`IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` pose ce même
octet à **1** en dur (`uStack_1e2 = 1`, seul octet non nul de la struct) avant de construire le
`Nullable`. Le byte n'est donc pas une constante de la face COMBAT — et le port donne bien `20` à
SkyStrike (`engine/runner/abilities/sisterhood.py`).

## 3. L'inventaire — et pourquoi le grep ment dans le sens rassurant

Balayage **AST** (`probe_449r2_spread_inventory.py`), sur les trois portes d'entrée de la variance :
constructeurs en mode `amount` (défaut `amount_spread_pct=0`), `execute_normal_like` (défaut
`spread_pct=20`), et les foyers d'étalement eux-mêmes.

| rail | sites | à variance NULLE | verdict |
|---|---|---|---|
| R1 mode `amount` | 4 | **3** | 3 JUSTES (§2) ; le 4e est SkyStrike à 20, juste aussi |
| R2 `execute_normal_like` | 2 | 0 | — |
| R3 foyers d'étalement | 3 | 0 | tous propagés |

**Zéro littéral faux. Zéro correction de port.**

Le grep textuel du motif rend un tout autre tableau, et il est **trompeur des deux côtés** —
mesuré sur `engine/` :

```
6 occurrences de `spread_pct=0`  ->  4 docstring, 1 commentaire, 1 CODE
```

Il **sur-rapporte** (5 fantômes sur 6) et surtout il **sous-rapporte** : deux des trois vrais
porteurs — `psyker.py` (runner) et `haze_of_corruption.py` — **ne contiennent pas le motif du
tout**. Ils prennent le **défaut du constructeur**, et l'absence du mot-clé y est précisément la
décision de portage. `haze_of_corruption` n'était nommé nulle part : ni dans #449 §7, ni dans
l'énoncé de ce cas — **c'est l'AST qui l'a trouvé**.

> La règle qui en sort : sur un paramètre à DÉFAUT porteur de sens, l'inventaire se fait sur les
> **call-sites**, jamais sur le texte du mot-clé. Le site le plus dangereux est celui qui ne
> l'écrit pas.

## 4. Validation — par hp-diff, la face qui convient

Un accord de prédiction ne prouverait rien ici : les deux faces ont des artefacts distincts. La
confrontation porte donc sur le **dégât appliqué en bataille**.

**Baseline** (code livré) — 17 passed :

| test | résultat |
|---|---|
| `tests/engine/runner/test_psyker_splash_live.py` | **1 passed** |
| `tests/engine/runner/test_cursed_plague_bell_attack_live.py` | **7 passed** |
| `tests/engine/runner/test_haze_of_corruption_transfer_live.py` | **9 passed** |

**Contre-épreuve** — `amount_spread_pct=20` forcé sur les trois porteurs (mutation vérifiée par
l'AST avant mesure, pas seulement par `git diff` : le piège CRLF rend des mutants verts) :

| porteur | port muté | natif | écart |
|---|---|---|---|
| Psyker smite | 1514 | **1506** | 8 |
| CursedPlagueBell recul (2 cas) | 1696 / 4267 | **1795 / 4860** | 99 / 593 |
| Haze relais (hp 5000) | 4126 | **4164** | 38 |

`1 failed`, `3 failed / 4 passed`, `2 failed / 7 passed` : **les trois rougissent**. Le canal
n'est donc pas dégénéré — il **exerce** la grandeur, et le natif est du côté PLAT sur les trois.

**Le montage qui SÉPARE**, nommément : celui de `test_cursed_plague_bell_attack_live.py`, où le
montant du recul (`GetVariableForLevel(0xb)`, ~1795 et ~4860 après réduction) est assez grand pour
que `0,8·d` et `1,2·d` restent séparés de plusieurs centaines de points après armure — l'écart y
atteint **593**. À l'opposé, le smite Psyker sépare **faiblement sur ce seed** (8 points) : le
tirage y est tombé près de `d`. Il rougit, donc il tranche, mais il ne serait **pas** le montage à
choisir pour discriminer — c'est nommé en résidu `#449-r2-r1`.

## 5. Ce qui est livré

* **Aucune modification de comportement du moteur** — c'est le résultat : les trois `0` sont justes.
* `scripts/python/probe_449r2_spread_inventory.py` — l'inventaire AST, **bidirectionnel**.
* `scripts/python/tests/test_449_r2_spread_face_combat_offline.py` — la garde (4 assertions).
* Entrée `probe_449r2` dans `scripts/ratchets.ps1`.
* Docstrings des trois sites : la raison **lue** remplace la raison supposée.

**Le second sens du garde n'est pas cosmétique.** Dans sa première version, le probe ne gardait que
« tout zéro est justifié ». Mesuré : le mutant posé sur les **trois** porteurs le laissait **VERT**
— il ne voyait plus aucun zéro, donc plus rien à justifier. C'est exactement la forme du trou que
`#449` §8 avait nommée : une garde qui ne porte que sur ce qu'elle OBSERVE, jamais sur ce qu'elle
ATTEND, ne peut pas rougir sur une régression. Le sens 2 (« un site lu au décompilé DOIT rester à
zéro ») a été ajouté, puis **vérifié rouge** sur le mutant.

## 6. Résidus NOMMÉS

* **`#449-r2-r1`** — le montage Psyker **discrimine faiblement** (8 points sur 1506, seed 777) : le
  tirage `spread 20` y est tombé près de `d`. La garde tient parce que le seed est fixe, mais un
  changement de seed ou de roster pourrait rendre ce mutant vert. Le montage qui le durcirait est
  nommé : rejouer le splash sur **N seeds** (`build_runner("777"|"31337"|…)`) et exiger l'accord à
  chaque tirage — la probabilité que TOUS tombent sur `d` est nulle. Non fait : le régime
  CursedPlagueBell sépare déjà de 593 points et porte la démonstration.
* **`#449-r2-r2`** — `configuration+0x31`, le **second** aiguillage vers la branche plate, est lu
  comme faux en pratique (les mesures §4 le prouvent : le mutant DIVERGE, donc la branche spread
  est bien atteignable) mais son champ n'est **pas nommé**. Hérité de `#449-r3`, inchangé.
* **`#449-r2-r3`** — les autres consommateurs du byte ne sont **pas énumérés** : ce cas a lu les
  trois porteurs à variance nulle + SkyStrike. Les abilities qui passeraient un Nullable NON vide
  avec un octet +6 à 1 **et qui ne sont pas encore portées** n'ont pas été recensées ; elles
  entreront par le cliquet (`probe_449r2` rougit sur un zéro non justifié).
* **`#449-r2-r4`** — le `spread_pct=20` **par défaut** des rails de l'attaque NORMALE
  (`Runner.install_default_handlers`, `DamageHandler`, `HitDamage.from_base`) est un littéral
  hérité, alors que le natif le lit dans `BattleConfiguration.Damage.DamageSpreadPercentage`. Hors
  périmètre de ce cas (c'est le canal de l'attaque normale, pas le slot de montant) et sans effet
  observé — la seed BC porte 20 — mais c'est un couplage non lu.

**Ce qui n'est PAS couvert** : les régimes ÉLÉVATION (hérité `#449-r4`), et la face PRÉDICTION des
trois porteurs (hors périmètre — `#449` l'a traitée pour son propre lot).
