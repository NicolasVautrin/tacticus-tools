# case-295 — Le seuil d'`IsActiveAbilityCountedAsUsed` : comparateur **STRICT**, seuil `Direct(1)`, et un écart qui ne pouvait rougir nulle part

## Verdict

`IdunBattleLogic.Entities.DSLTriggers$$IsActiveAbilityCountedAsUsed(isPreAbilityTrigger = false)`
évalue **`used > 1`**. Le port écrivait `used >= 1` — une utilisation de retard. **Corrigé.**

La lecture héritée de `case-293` §5 est **confirmée mot pour mot**. Ce qui change, c'est son statut :
elle était *lue en marge*, elle est maintenant **mesurée**, par deux chemins indépendants et une
garde re-dérivable en une commande.

| ce qui est établi | par quoi |
|---|---|
| classe instanciée = famille **STRICTE** (`AmountIsGreaterAbilityTrigger`) | **pointeur de classe** chargé avant `il2cpp_object_new` (le sujet touche le global STRICT, **aucun** global INCLUSIF) |
| le comparateur de cette classe est `minAmount < amount` | encodage `setg` de son `ShouldTrigger`, contre `setge` pour `AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger` |
| `amount` = le compteur, `minAmount` = le seuil | `IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$.ctor(this, amount, minAmount)` — `[this+0x18] = amount`, `[this+0x20] = minAmount`, relus par `ShouldTrigger` |
| seuil de la branche mirrorée = `Direct(1)` | **découvert**, pas supposé : la branche `isPreAbilityTrigger == 0` lit le champ `+0x20` du cache de `IdunBattleLogic.Entities.DSLFormulas$$.ctor`, qui y range le nœud constant `1` |
| la branche mirrorée est bien `false` | l'appelant passe le littéral `0` |

---

## 1. La fonction, telle qu'elle est écrite

```csharp
seuil = DSLFormulas@(isPreAbilityTrigger ? +0x18 : +0x20);   // +0x18 = Direct(0) | +0x20 = Direct(1)
left  = new <classe>( amount   = DSLFormulas.TotalActiveAbilityUsed(unit, ability),
                      minAmount = seuil )                    // <-- LA question
        & IsAbilityCountedOnlyOnce(ability);
right = IsNormalAttack(ability) | <kind attaque-normale>;
return !right & !left;
```

`IdunBattleLogic.Entities.DSLFormulas$$.ctor` met cinq nœuds constants en cache — `+0x18 = 0`,
`+0x20 = 1`, `+0x28 = 2`, `+0x30 = 100`, `+0x38 = -1`. La branche ne choisit **que le seuil**, jamais
la classe du comparateur : il n'y a qu'**un seul** site d'allocation dans la fonction. Le verdict
« STRICT » vaut donc pour les deux branches ; seule la valeur comparée change.

Les deux branches disent d'ailleurs la **même chose à un cran près**, selon que le compteur inclut
déjà l'utilisation courante : `pre` compare à `0` (avant incrément), `post` à `1` (après). C'est la
cohérence sémantique qui achève de trancher — avec `used >= 1` sur la branche `post`, une ability du
HashSet « comptée une seule fois par bataille » n'aurait **jamais** compté, pas même à sa première
utilisation.

### Le piège, identique à #293 — et il ne s'est pas déclenché ici, mais il aurait pu

Le `.ctor` appelé a pour corps `base..ctor` + deux stores. Ce corps est **identique pour toutes les
conditions de même layout**, donc **dédupliqué par IL2CPP** : la table lui donne **un seul
propriétaire**, qui ne dit rien de la classe réellement allouée. Sur ce build, ce propriétaire est
`AmountIsGreaterAbilityTrigger$$.ctor` — et cette fois la classe *est* bien la stricte. **L'accord du
nom et de la classe est ici une coïncidence, pas une preuve** : sur `IsInUnitContagionsOfNurgleAura`
(#293) le même accord apparent était FAUX, et dans le sens inverse.

⇒ On ne conclut jamais du nom. La seule ancre est le pointeur de classe, et il est désormais lu
mécaniquement.

## 2. La branche mirrorée est bien `false`, et ce fait est lui aussi un corps dédupliqué

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ExtraDamageAbility$$CreateTrigger`
**n'existe pas** dans la table du build courant. Son corps y est nommé
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TalonsOfTheEmperor_UsedAbilitiesAbility$$CreateTrigger`
— même arbre, mêmes octets, un seul propriétaire :

```csharp
On(0xe) & AreFriends(...) & ( HasTrait(caster, 0x10) & !HasTrait(caster, 0x419) )
        & IsActiveAbilityCountedAsUsed(0)     // <-- littéral false
```

C'est le troisième corps dédupliqué du même cas (le `.ctor`, le `CreateTrigger`, et le `.ctor` de
nœud constant que Ghidra étiquette `Stash…OpenCardOrModalInternal…`). **Sur cette famille de code,
l'absence d'un symbole et le nom d'un symbole sont deux non-informations.**

## 3. Pourquoi cet écart ne pouvait rougir nulle part — et ce qu'on en fait

`State` n'expose **aucun** `total_active_ability_used` (il n'est pas dans ses `__slots__`). Donc
`_total_active_ability_used` rend **toujours** `None`, la comparaison de seuil n'est **jamais**
atteinte en bataille, et **aucun test live ne peut changer de couleur** sur ce seuil — ni avant, ni
après la correction. C'est exactement le patron de dégradation qu'on chasse : le jour où le compteur
sera câblé, l'écart serait devenu actif **en silence**, sans lever, sans casser un test.

Il n'y a donc **aucune validation live** dans ce cas, et il ne faut pas en fabriquer une. Ce qui tient
l'invariant à sa place, ce sont deux gardes qui n'attendent pas le câblage :

| garde | ce qu'elle tient | vue rouge par |
|---|---|---|
| `scripts/python/probe_295_active_ability_counted_as_used.py` | la face NATIVE (famille de classe, encodage, seuil découvert) **et** l'accord du port ; dit aussi l'état du canal | `>=` remis → `used qui COMPTENT = [0]` au lieu de `[0, 1]` |
| `scripts/python/tests/engine/runner/test_active_ability_counted_as_used_offline.py` (8 tests) | les DEUX côtés du seuil, en **injectant** le compteur par une sous-classe de `State` | `>=` remis → `test_used_one_still_counts_strict_comparator` ; seuil décalé → `test_used_two_no_longer_counts` |

Le probe se re-dérive en une commande au prochain changement de build, et **ne hardcode aucun
offset** : il découvre les deux déplacements de branche dans le sujet (`test dl,dl` + `je`), la table
`<champ> -> <littéral>` dans le ctor de cache, puis les croise. Sans `GameAssembly.dll` du build
courant il rend `NON MESURÉ` et sort en erreur — jamais un « 0 écart » qui se lirait comme un accord.

Le test unitaire porte en tête, en toutes lettres, que le canal est inerte et qu'il est **la seule
chose qui exerce ce seuil** ; le port le redit à ses deux points de lecture. Le prochain lecteur ne
peut pas croire ce chemin couvert par le live.

## 4. Ce que ce cas n'établit PAS

* **Aucun changement de comportement observable n'est livré aujourd'hui.** La branche corrigée est
  inatteignable tant que le compteur n'est pas câblé. Ce cas paie une dette *à l'avance* ; il ne se
  mesure pas en bataille et ne doit pas prétendre le contraire.
* **Le compteur lui-même reste un résidu nommé** :
  `IdunBattle.Entities.Formulas.TotalActiveAbilityUsedFormula$$Calculate` résout l'unité puis
  l'`AbilityOrEffect`, et lit un compteur per-unité qu'aucun RPC ne rend. Point de câblage unique :
  `triggers/loki/fuelled_by_fury.py::_total_active_ability_used`. Le jour où il est câblé, **les deux
  gardes ci-dessus passent du statut « seul filet » à celui de garde-fou d'une mécanique vivante** —
  et c'est à ce moment-là qu'un test live devient possible.
* **La branche `isPreAbilityTrigger = true` n'est pas portée** : aucun appelant du port ne la demande.
  Son seuil est lu (`Direct(0)`) et vérifié par le probe, mais rien ne l'exerce.
* **Le volet `!right` n'a pas été rejugé.** Sur le build courant il est *inliné* en
  `AbilityIsNormalAttackTrigger(ability) | <kind 0x3f5>` là où la docstring du port cite
  `IsNormalAttackOrHealOrRepair` ; le port délègue de toute façon au foyer unique
  `abilities/attack_type.py::is_normal_attack`, qui porte exactement cette disjonction. Hors périmètre
  de la question posée.
* **L'étape 3b du probe sur-génère** (décodage linéaire : elle attribue un littéral à des champs
  voisins qui ne portent pas de nœud constant). C'est signalé dans sa sortie, et sans conséquence :
  seuls les deux champs désignés par l'étape 3a sont croisés.
