# `#419-r1-tr14-r5-r2-r1-r1-r1-r2-r4` — le seuil de `ShouldExecute` vaut `Fix64(10)`

**Critère binaire** : d'où vient le refus natif que #592 mesurait *au-dessus* du seuil porté —
d'une divergence de l'UTILITÉ, ou d'un FILTRE au-dessus du playbook ? **Ni l'un ni l'autre.** Le
gate qui refuse EST `ShouldExecute`, et son seuil n'est pas celui que #592 avait lu : le champ
statique qu'il compare a **DEUX écrivains**, et le dernier écrit `Fix64(10)`.

---

## 1. Le discriminant, ÉNONCÉ AVANT LA MESURE

Les deux causes prédisent le MÊME résultat sur le canal de #592 (`aiDryRunAllUnits` : refus en bas,
acceptation en haut) — c'est pour ça qu'elle ne les séparait pas. Deux canaux les séparent :

| | canal | cause 1 (utilité fausse) prédit | cause 2 (filtre au-dessus) prédit |
|---|---|---|---|
| A | `Bucket$$AddAction` : LIRE le prédicat au décompilé | (muet) | un prédicat qui refuse sur l'utilité |
| B | `pairUtility` = `CalculateUtilityFromPredictions` NATIF | `u_natif ≪ u_port` | `u_natif == u_port` |

**Les deux ont répondu, et les deux causes tombent.**

---

## 2. Canal A — le prédicat, lu au décompilé : `IsValidAction`, et il est INERTE ici

`Bucketu003C…u003E$$AddAction` et `…$$ChooseAction` appellent tous deux le corps désigné par
`<klass.rgctx>+0x40`. Ce corps est
`IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$IsValidAction` :

```c
IsValidAction(this, action):
    if (action == null) return false;
    if (!this.<Nullable @+0x10>.HasValue) return true;
    return Fix64.op_GreaterThanOrEqual(action.Utility, this.<Nullable @+0x10>.Value);
```

Il ne peut refuser sur l'utilité QUE si le bucket porte un seuil. Les DEUX buckets du chemin
`ActiveAbilityActionGenerator` en sont dépourvus, et c'est **lu**, pas supposé :

* bucket RACINE (`…ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`) → surcharge
  `Bucket..ctor(this)` (deux arguments), qui n'écrit ni `+0x10` ni `+0x18` ; l'objet IL2CPP est
  alloué zéro-initialisé ⇒ `HasValue == false` ;
* bucket du PLAYBOOK (`ComparablePlaybooku003C…u003E$$EvaluateInternal`) → `+0x10` reçoit
  `Nullable<Fix64>(Fix64$$op_Implicit(0x80000000))`, et `op_Implicit` vaut `(long)(int)v << 32`,
  donc `(-2147483648L) << 32` = `long.MinValue` = **`Fix64.MinValue`**.

`…$$Merge` n'ajoute rien : il rappelle `AddAction` sur le bucket CIBLE (la racine, sans seuil).

⚠ **Le seul capteur live de cet ancrage est inutilisable sur ce build.**
`frida/hooks/features/bucket-audit.ts` résout ces quatre corps par **RVA écrite en dur**, figée sur
`gqfc5mff6c` : `addAction 0x13fbcc0` contre `0x14eff60` pour `rnca9r7q6c`, et pareil pour les trois
autres (4/4 périmées, mesuré). L'armer attacherait sur du code arbitraire. C'est *pourquoi* le
prédicat devait être lu au décompilé — et c'est une mine dormante à nommer (§7).

---

## 3. Canal B — l'utilité native, mesurée : ACCORD PARFAIT

Montage de #592 repris tel quel (board `MC1_67`, seed `4242`, `darkaTerminator` `Movement=0`,
`adeptRetributor` à distance 3, `--no-ai`), `u` piloté par les PV de la cible.

| bras | PV cible | `u` port | `u` natif (`pairUtility`) | natif propose | port produit |
|---|---|---|---|---|---|
| `lo` | 4 000 000 | 0,08509996 | 0,08509995 | non | non |
| `mid` | 68 078 | 5,000000000 | 5,000000005 | **non** | oui *(avant fix)* |
| `hi` | 17 018 | 20,0 | 19,999999995 | oui | oui |

Et `aiPlaybookPredict` (les `ProbableDamageEvent` NATIFS) rend **la même liste que le port** sur les
trois bras : `{target 77, hMin 2724, hMax 4083, hits 3, prob 1}`.

⇒ **Cause 1 réfutée** : aucune divergence d'utilité ni de prédiction.
⇒ Or `CalculateCustomUtility` vaut `Fix64(0)` (corps de base, et `resolveMethodPtr` montre que
`PlasmaCannonPlaybook` ne surcharge QUE `MakeDamagePredictions` et `ShouldExecute`), donc
l'argument de `ShouldExecute` **est** ce `u`. À `u = 5 > 1`, le gate au seuil lu accepterait.
⇒ **Le seuil lu est faux.**

---

## 4. La cause : le champ statique a DEUX écrivains

`<X>Playbook$$ShouldExecute` lit `**(Il2CppClass* + 0xb8)` = le PREMIER static de sa classe. Ce
slot est écrit par :

1. `<X>Playbook$$.cctor` — **quatre** des douze classes en déclarent un, qui y met `Fix64(1)` ;
2. `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.cctor` :

```c
value = FixMath.NET.Fix64$$op_Implicit(0xa);          // Fix64(10)
klass  = <rgctx>[22];                                  // Il2CppClass*, résolu par RGCTX
if (!klass.initialized) Class::Init(klass);
**(klass + 0xb8) = value;                              // le PREMIER static de CETTE classe
```

C'est le **seul `Fix64(10)` de la couche playbook** (recherche littérale sur les 65 000 corps
décompilés : 5 occurrences, une seule dans la chaîne du gate). Et il écrit en DERNIER : le `.cctor`
dérivé part au `class_init` de la classe dérivée (à l'allocation), celui de la base part plus tard,
avec `ComparablePlaybook<T>..ctor` que le `.ctor` dérivé appelle ENSUITE.

---

## 5. La mesure — le seuil encadré, sur DEUX identités aux `.cctor` OPPOSÉS

`u × (maxHP + 2)` est invariant à dégât constant : un premier bras à PV énormes donne la constante,
les deux points de l'encadrement s'en dérivent. Le pas d'UN point de vie donne ~3·10⁻⁴ en `u`.

| ability | `.cctor` dérivé | seuil que #592 déclarait | bascule NATIVE mesurée |
|---|---|---|---|
| `1150 PlasmaCannon` | oui, `Fix64(1)` | 1 | **(9,9997062 ; 10,0002938]** |
| `1069 SeekerMissileFrequencyLock` | **aucun** | 0 | **(9,9998703 ; 10,0001297]** |

`Fix64(10)` (raw `42949672960`) est dans les deux intervalles ; `1` et `0` en sont exclus de
plusieurs ordres de grandeur. **Deux seuils déclarés opposés, un seul seuil effectif.** C'est ce
témoin qui interdit de relire le seuil dans le `.cctor` dérivé — un montage sur `1150` seule
laisserait « 1 » plausible.

`1069` est **greffée** sur `darkaTerminator` (`case-92` §5bis) : légitime ici parce que
`ShouldExecute` ne lit NI stats NI traits du caster — il lit un champ statique de sa classe. Le
playbook effectivement chargé est vérifié (`pairUtility.playbookClass` =
`SeekerMissileFrequencyLockPlaybook`), et le natif le PROUVE en émettant `ActiveAbilityMessage(1069)`.

### 5.1 L'égalité EXACTE au seuil — un régime que le port ne peut pas suivre

À `u_port == 10,0` **pile** (PV calibrés à l'entier près), le natif rend `10 + 9,3·10⁻⁹` (Fix64
Q32.32 accumule ses arrondis) : il **accepte**, le port **refuse**. Mesuré sur les deux identités.
C'est un écart d'**ARITHMÉTIQUE**, pas de seuil — le fermer demanderait de porter Fix64 dans tout
l'étage utilité. Le cran évite donc ce point (il prend `hp0 ± 1`), et le nomme ici.

---

## 6. Le port

* `engine/playbook/static_threshold_gate.py` — **`STATIC_UTILITY_THRESHOLD = 10.0`**, foyer UNIQUE.
  `THRESHOLD_BY_ID` s'en dérive pour les douze. Les deux groupes de #592 sont conservés sous leur
  vrai nom (`DERIVED_CCTOR_IDS` / `NO_DERIVED_CCTOR_IDS`) : la présence du `.cctor` dérivé reste un
  FAIT mesuré — c'est simplement un fait sur les écrivains, pas sur le seuil.
* `engine/playbook/bespoke.py` — `MomentShacklePlaybook.MIN_UTILITY` **consomme** la constante.
* `engine/playbook/excruciating_frequencies.py` — `_score` passe de `u <= 0` à `not u > 10`.

Effet mesuré : le port devient FIDÈLE là où il était PERMISSIF. Sur les trois bras de #592,
l'accord natif/port passe d'un seul sens (« le port ne refuse jamais ce que le natif choisit ») aux
**deux sens**.

---

## 7. Ce qui n'est PAS couvert

* **Deux identités confrontées sur douze.** Les dix autres partagent le MÊME corps `ShouldExecute`,
  le MÊME slot statique et la MÊME base générique ; leur seuil est porté par déduction structurelle,
  pas par mesure. Les deux mesurées ont été choisies pour être les cas OPPOSÉS.
* **`1184 MomentShackle` et `1197 ExcruciatingFrequencies` ne sont pas confrontées** : leur gate vit
  sur une route bespoke. Le seuil y est le même par construction (même famille), et le changement
  n'y mord que dans un régime étroit (`MomentShackle` : `adj_enemies == 0` et `self_heal_u ∈ (1,10]`).
* **L'égalité exacte au seuil** (§5.1) — divergence d'arithmétique, nommée, non fermée.
* **Le mécanisme d'ORDRE d'initialisation** est une lecture, pas une mesure : ce qui est mesuré,
  c'est la valeur EFFECTIVE (10) et le fait qu'elle ne dépend pas du `.cctor` dérivé. On n'a pas
  observé les deux écritures se succéder.
* **`bucket-audit.ts` porte 4/4 RVA d'un autre build** (§2). Ce n'est pas corrigé ici : le geste
  utile est un reinject, qui ne m'appartient pas — et corriger des RVA en dur sans le rafraîchir à
  chaque build ne ferait que replanter la mine. Un cran MESURE la péremption (il rougira aussi si
  quelqu'un rafraîchit les RVA sans le dire).

---

## 8. Résidus NOMMÉS

* **`-r4-r1` — `BloodChalicePlaybook` et `CultDemagoguePlaybook` portent `MIN_UTILITY = 1.0`.**
  #592 les rangeait hors périmètre (« leur seuil vient d'`EvaluateInternal`, pas de
  `ShouldExecute` »). Si leur `MIN_UTILITY` venait en réalité du même slot statique, il vaudrait 10
  lui aussi. À lire avant de toucher : les deux gates sont numériquement INERTES dans leur régime
  courant (un seul ami adjacent donne déjà `1 × 50 = 50`), donc l'enjeu est la fidélité, pas le
  comportement.
* **`-r4-r2` — le prédicat `IsValidAction` n'est réfuté que pour le chemin
  `ActiveAbilityActionGenerator`.** `NonComparablePlaybooku003C…u003E$$GenerateBucketWithMultipleStrategies`
  appelle `AddActionToBucket` avec une CLÉ, et `ChooseActionFromBuckets` parcourt la `SortedList`
  par ordre de clé : sur cette route-là, les sous-buckets sont créés par `GetOrCreateBucket` /
  `CreateBucket`, tous deux via la surcharge SANS seuil — mais la lecture n'a pas été poussée
  jusqu'aux appelants NC.

---

## 9. La technique, réutilisable

**« Le `.cctor` de la classe donne le seuil » est un raisonnement à UN écrivain.** Un champ statique
peut en avoir plusieurs, et le dernier gagne. Le contre-poison n'est pas de relire le même `.cctor`
plus attentivement : c'est de **confronter deux identités dont les `.cctor` déclarent des valeurs
OPPOSÉES**. Si elles basculent au même endroit, aucun des deux `.cctor` n'est la source — et il
reste à chercher qui écrit ce slot par ailleurs (ici : une recherche littérale du littéral mesuré,
`op_Implicit(0xa)`, sur le décompilé entier).

**Encadrer plutôt que fitter.** Le seuil n'a jamais été « ajusté » : il a été ENCADRÉ par deux
points calibrés (`u × (maxHP+2)` invariant), puis confronté au seul littéral candidat trouvé au
décompilé. L'encadrement à 3·10⁻⁵ exclut mécaniquement les deux valeurs précédemment portées.

**Ne pas mesurer à l'égalité exacte.** Deux arithmétiques différentes (Fix64 côté natif, flottant
côté port) coïncident partout SAUF au point de bascule. Un cran posé pile au seuil mesure la
représentation, pas la règle.
