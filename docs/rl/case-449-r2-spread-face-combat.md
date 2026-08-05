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

## 5bis. Relevé de validation (2026-08-02, APRÈS rebase sur `origin/master` = `133310ba`)

| ce qui a été joué | résultat |
|---|---|
| `tests/engine/runner/test_psyker_splash_live.py` | **1 passed** |
| `tests/engine/runner/test_cursed_plague_bell_attack_live.py` | **7 passed** |
| `tests/engine/runner/test_haze_of_corruption_transfer_live.py` | **9 passed** |
| `tests/test_449_r2_spread_face_combat_offline.py` (garde neuve) | **4 passed** |
| `pwsh -File scripts/ratchets.ps1` | **BANQUE VERTE, rc=0**, mur 160 s ; `probe_449r2` = 7,1 s |

**Contre-épreuves jouées, puis annulées** (toutes vérifiées comme ayant MORDU — par l'AST, pas
seulement par `git diff`) :

* mutant `amount_spread_pct=20` sur les **trois** porteurs → les trois tests live rougissent (§4) ;
* le même mutant sur `psyker.py` seul → `probe_449r2` **rouge** (`regression: attendu 0`) ;
* le même mutant sur `haze_of_corruption.py` (le site en DÉFAUT) → la garde pytest **rouge** sur
  `test_les_sites_lus_au_decompile_sont_toujours_a_zero`.

Après chaque contre-épreuve, `git diff` sur `engine/` est **vide** — aucun résidu de mutation.

## 6. `#449-r2-r5` — le cliquet gardait les call-sites, pas la valeur dont ils dépendent

**Le garde livré ci-dessus restait VERT sous la mutation qui compte.** Contre-épreuve jouée le
2026-08-02, *différente* de celles du §5bis : au lieu d'écrire `spread_pct=20` sur les
call-sites, on change le **défaut de la signature** —

```python
# engine/runner/abilities/behaviours/combat.py
-  is_first_hit: bool = True, amount_spread_pct: int = 0):
+  is_first_hit: bool = True, amount_spread_pct: int = 20):
```

| garde | verdict sous mutation |
|---|---|
| `probe_449r2_spread_inventory.py` | **VERT**, rc 0 |
| `test_449_r2_spread_face_combat_offline.py` | **4 passed** |

**Cause lue** : le probe *écrivait* les défauts (`defaut 0` l.17, `defaut 20` l.19, `else 20`
l.111) au lieu de lire `ast.FunctionDef.args.defaults`. Or le §3 de ce même document établit que
ce défaut **est** la décision de portage : **deux des trois porteurs n'écrivent pas le mot-clé**.
Le garde protégeait donc tout sauf le point unique de vérité.

### Ce qui est désormais DÉRIVÉ, et ce qui reste ATTESTÉ

La ligne de partage : est **attestable** (saisi avec sa raison) ce dont la source est le
**décompilé**, qui n'est pas dans le dépôt ; est **dérivable** — donc jamais recopié — tout fait
lisible dans le dépôt lui-même.

| DÉRIVÉ du dépôt | ce que ça ferme |
|---|---|
| le **périmètre** : toute définition de `engine/` dont la signature porte un nom de `VARIANCE_PARAMS` | 3 rails saisis → **14 définitions**, dont **10** invisibles à l'ancienne liste (`UseActiveAbility`, `DamageHandler`, `install_default_handlers`, `execute_additional_hits`, `predict_attack_raw`, `get_attack_prediction`…). En sens inverse, `AttackWithAbilityDamage` y était déclaré rail alors que sa signature ne porte **aucun** paramètre de variance — il n'a jamais rien capté |
| la **valeur** par défaut | la mutation ci-dessus |
| la **position** positionnelle du paramètre | un call-site qui passe la variance sans mot-clé. Mesuré, ça existe déjà : `DamageHandler(state, spread_pct)` et `spread_to_min_max(base, spread_pct)` |
| le **gate d'activation**, lu dans le corps (`AttackWithAttackDamage` ne lit `amount_spread_pct` que sous `if self.amount is not None`) | les **83** call-sites en mode bornes restent INERTES sans qu'aucune liste ne les déclare — et si le gate disparaît du code, ils redeviennent tous comptés |

| ATTESTÉ (raison native inscrite) | rôle |
|---|---|
| `EXPECTED_ZERO` (inchangé, 3 entrées) | les call-sites dont le natif impose la variance nulle |
| `EXPECTED_DEFAULT` (**neuf**, 14 entrées) | ce que le natif impose à chaque **défaut** |

`EXPECTED_DEFAULT` n'est pas un doublon du sens 2 : pour `execute_normal_like`, **aucun**
call-site ne prend le défaut, donc la voie « call-sites » y est structurellement aveugle. La
contre-épreuve `spread_pct: int = 20 → 0` sur `normal_like.py` n'est vue que par lui.

⚠ **Les 13 attestations à `20` n'existent plus depuis `#449-r2-r4` (2026-08-05).** La réserve
écrite ici — « ce 20 est un littéral hérité, pas une lecture de `BattleConfiguration.Damage.
DamageSpreadPercentage` » — s'est vérifiée en bataille : à `pct = 60` le natif inflige **7774**
contre **9388** pour le port. Les 13 défauts sont passés au régime **`LU_BC`** (défaut `None`,
valeur lue de la BC à l'exécution), et le probe atteste désormais un **RÉGIME**, pas une valeur.
La contre-épreuve citée juste au-dessus (`spread_pct: int = 20 → 0`) se joue maintenant
`= None → 20`, et rougit par **deux** voies. Détail : `case-449-r2-r4-spread-lu-de-la-bc.md`.

### Gardes du garde (tous neufs)

Un `VARIANCE_PARAMS` qui ne désigne plus aucune signature (le probe serait devenu **aveugle**) ;
un défaut **non littéral** ; un **paramètre MORT** — accepté et lu nulle part, donc la variance
cesse d'être appliquée *sans qu'un seul call-site change* ; un `*args`/`**kwargs` classé
**INDÉTERMINÉ** et jamais « défaut » ; les noms d'appel **AMBIGUS** déclarés au lieu d'être
résolus en silence.

### L'auto-test est DANS le probe, et il a trouvé trois bugs du détecteur

Il tourne à chaque run — #427 a mesuré que « être un test » et « être joué » sont indépendants
ici. 13 cas, dont **6 négatifs**, et une contre-épreuve directe du vice : deux arbres synthétiques
identiques *à un caractère près* doivent produire deux classements différents. Ce qu'il a trouvé :

1. la détection « paramètre MORT » cherchait `self.<param>` jusque dans les `@staticmethod`, où
   il est une variable **locale** → 4 paramètres bien vivants déclarés morts ;
2. `ast.walk` revisitant les méthodes en nœuds indépendants → tout nom de méthode comptait
   **double**, et `execute_normal_like` sortait « ambigu », donc **exclu** de la résolution par
   nom, donc ses call-sites en défaut invisibles — le trou se rouvrait par un autre chemin ;
3. la garde « périmètre aveugle » rougissait sur l'arbre synthétique du cas C13 (corrigé dans le
   **cas de test**, jamais dans la garde).

Écriture en **tmpdir système** (`mkdtemp()` sans `dir=`) — #455. Cache de parsing : le verdict
traverse `engine/` trois fois, 19 s → **6,1 s**, sous les 7,1 s de la version précédente.

### Contre-épreuves jouées (2026-08-02), toutes vérifiées comme ayant MORDU (relecture AST)

| mutation | `probe_449r2` | garde pytest |
|---|---|---|
| `amount_spread_pct: int = 0 → 20` (celle de l'énoncé) | **ROUGE**, par **2** voies : défaut attesté **et** régression des 2 porteurs en défaut | **2 failed / 5 passed** |
| `execute_normal_like(spread_pct: int = 20 → 0)` | **ROUGE** (défaut attesté — seule voie possible) | — |
| lecture supprimée : `spread_pct=self.amount_spread_pct` → `spread_pct=0` | **ROUGE**, cause `parametre MORT` en tête + 84 conséquences capées | — |
| `sisterhood.py` `amount_spread_pct=20 → 0` | **ROUGE**, `zero NON JUSTIFIE`, 1 ligne | — |
| aucune mutation (`master` propre) | **VERT** | **7 passed** |

Après chaque contre-épreuve, `git diff` sur `engine/` est **vide**.

### Ce que ce critère NE PEUT PAS voir (nommé, pas laissé croire)

* **Les noms d'appel ambigus.** `AttackDamageOperation.execute(...)` : `execute` désigne **94**
  définitions sous `engine/`, dont **une seule** porte `spread_pct`. Ses call-sites ne sont pas
  inventoriables par nom — seuls leurs **mots-clés littéraux** sont vus (filet de rattrapage), et
  un appelant qui prendrait son **défaut** n'est vu que par l'attestation du défaut. Le probe
  l'imprime en clair sous « ANGLE MORT NOMMÉ ». Résolu par MRO, ce serait une réimplémentation de
  l'import Python : non fait, nommé.
* **Un paramètre de variance au nom différent** (`spread`, `variance_pct`…) est hors périmètre par
  construction. Le garde qui l'atténue : `VARIANCE_PARAMS` doit désigner ≥ 1 signature, sinon
  rouge.
* **Une valeur dynamique** (`spread_pct=x`) n'est pas tranchée — elle est classée DYNAMIQUE, pas
  « nulle » ni « juste ». 13 call-sites sont dans ce cas.
* **La face `frida/` (TypeScript)** n'est pas balayée : le port de la variance y est absent, mais
  ce n'est pas *vérifié* ici.

## 7. Résidus NOMMÉS

* **`#449-r2-r1`** — le montage Psyker **discrimine faiblement** (8 points sur 1506, seed 777) : le
  tirage `spread 20` y est tombé près de `d`. La garde tient parce que le seed est fixe, mais un
  changement de seed ou de roster pourrait rendre ce mutant vert. Le montage qui le durcirait est
  nommé : rejouer le splash sur **N seeds** (`build_runner("777"|"31337"|…)`) et exiger l'accord à
  chaque tirage — la probabilité que TOUS tombent sur `d` est nulle. Non fait : le régime
  CursedPlagueBell sépare déjà de 593 points et porte la démonstration.
* **`#449-r2-r2`** — **FERMÉ par `#449-r2-r4` (2026-08-05)**. `configuration+0x31` est
  **`BattleConfiguration.Damage.IgnoreDamageSpread`**, lu par
  `IdunBattle.Core.Services.DamagePrediction$$get_IgnoreDamageSpread` (`this+0x10` =
  `configuration`, posé par `$$.ctor` ; même section que `DamageSpreadPercentage`, 0x11 octets plus
  loin). **Confronté live** : une BC portant `IgnoreDamageSpread = true` rend des bornes natives
  plates `[8434, 8434]` malgré `DamageSpreadPercentage = 20`. Détail :
  `case-449-r2-r4-spread-lu-de-la-bc.md` §3.
* **`#449-r2-r3`** — les autres consommateurs du byte ne sont **pas énumérés** : ce cas a lu les
  trois porteurs à variance nulle + SkyStrike. Les abilities qui passeraient un Nullable NON vide
  avec un octet +6 à 1 **et qui ne sont pas encore portées** n'ont pas été recensées ; elles
  entreront par le cliquet (`probe_449r2` rougit sur un zéro non justifié).
* **`#449-r2-r4`** — **RÉSOLU (2026-08-05)**, et la divergence était bien réelle : à
  `DamageSpreadPercentage = 60`, le natif inflige **7774** là où le port à `20` en dur calcule
  **9388**. Les **13** défauts littéraux sont supprimés au profit d'un foyer unique
  (`engine/services/damage_config.py`) dont le défaut est **dérivé** de `data/seed-bc.json`.
  Détail, mesures et contre-épreuves : `case-449-r2-r4-spread-lu-de-la-bc.md`.

* **`#449-r2-r5-r1`** — l'**angle mort des noms d'appel ambigus** (§6). `AttackDamageOperation.
  execute(...)` n'est pas inventoriable par nom. Ce qui le fermerait : résoudre le receveur par la
  MRO syntaxique (`AttackDamageOperation(_DamageOpsMixin, _DamageHitsMixin)` → … → `_Normal`), ce
  qui revient à réimplémenter la résolution d'attribut de Python. Le défaut, lui, est gardé par
  attestation, donc le résidu porte uniquement sur un call-site **explicite** à valeur nulle sur
  un nom ambigu.
* **`#449-r2-r5-r2`** — **FERMÉ par `#449-r2-r4` (2026-08-05)**. Les 13 attestations à `20`
  n'existent plus : elles sont devenues des attestations de **RÉGIME** (`LU_BC` = défaut `None`,
  la valeur est lue de la BC à l'exécution). Le cliquet a gagné en chemin un motif qu'il n'avait
  pas — `LITTERAL DE SPREAD REVENU` — qui rougit sur *tout* défaut entier non nul, sans qu'aucune
  attestation puisse le blanchir.
* **`#449-r2-r5-r3`** — le gate d'activation n'est dérivé que pour la forme `if self.G ...` /
  `if self.G is not None` **positive**. Une réécriture en `if self.amount is None: continue` ferait
  perdre le gate : le probe rougirait alors massivement (83 sites), ce qui est un **faux rouge**
  bruyant, jamais un faux vert. Non fermé : la sortie est capée à 10 lignes par motif et la CAUSE
  est imprimée en tête.

**Ce qui n'est PAS couvert** : les régimes ÉLÉVATION (hérité `#449-r4`), et la face PRÉDICTION des
trois porteurs (hors périmètre — `#449` l'a traitée pour son propre lot).
