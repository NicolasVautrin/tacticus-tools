# `#944` — le foyer `behaviours/combat.py` : trois résidus, un bug dormant, et un résidu écrit à l'envers

Quatre points sur un foyer **partagé** — `scripts/python/engine/runner/abilities/behaviours/combat.py`,
lu par tout ce qui attaque. Les confier séparément aurait produit quatre conflits sur le même fichier.

| point | verdict | ce qui l'établit |
|---|---|---|
| `#929-r3` | **REFERMÉ** | reproduit **par exécution**, pas seulement par lecture |
| `#889-r5-r1` | **REFERMÉ** | `UseActiveAbilityBehaviour$$.ctor`, signature **nommée** |
| `#889-r5-r2` | **REFERMÉ** | `ActiveAbilityOperation$$IsInvalidTarget`, signature **nommée** |
| `#925-r2` | **REFERMÉ — et la fiche disait l'inverse du fait** | lecture du code + décompilé des 4 call-sites |

---

## 1. `#929-r3` — le chemin qui LEVAIT, et ses dix tests verts

`hateful_assault_tree` construisait `UnitSet([mover_id])` — une liste d'**entiers** — et la passait à
un `AttackWithAttackDamage(..., multi=True)`, dont la branche `multi` filtre par `(u or {}).get("id")`.

**REPRODUIT** (12 lignes offline, `State` à deux unités, aucun runner) :

```
AttributeError: 'int' object has no attribute 'get'
  engine/runner/abilities/behaviours/combat.py:266
```

Le chemin est ATTEIGNABLE en production (`ABILITY_TRIGGERS["HatefulAssault"]`, `event_id =
PreUnitMove`, vecteur émis par `move_death.py`) : **toute bataille où `blackTerminator` voit un ennemi
adjacent se déplacer plantait le port**. Les **10** tests de `test_hateful_assault_live.py` étaient
verts parce qu'**aucun** n'appelle `execute_behaviour` — les 4 `test_live_*` mesurent le natif, les 6
`test_port_*` n'appellent que `matches`.

**Le correctif n'est pas un contournement.** `HatefulAssaultAbility$$CreateBehaviour` passe
`Target@DSLSelectors+0x60` — un **sélecteur**, pas un ensemble d'ids. C'était l'ARBRE qui était faux,
pas la feuille : `AttackWithAttackDamage` n'a pas été rendue tolérante aux entiers, et une
contre-épreuve exige que le patron d'origine **lève encore**. Sans elle, un filtre défensif ajouté
dans la feuille aurait verdi le garde sans rien réparer.

Corollaire de forme : `hateful_assault_tree()` ne prend plus d'id — le `CreateBehaviour` natif n'en
prend pas non plus, ses deux feuilles lisent le contexte.

**Le seul autre site du même patron a été cherché** : `UnitSet([…])` porte des **dicts** partout
ailleurs (`thousandsons.py` reçoit `by_id[t]`, `momentum.py` construit `{"id": …}`, `haze` passe des
unités). Le gisement était unique.

---

## 2. `#889-r5-r1` — la boucle porte sur les CASTERS

`IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviour$$.ctor` a une signature **nommée**, ce qui
donne le mapping sans deviner :

```
+0x50  activeAbilityType      +0x68..+0x80  parentAbility (28 o)
+0x58  caster                 +0x84..+0x9c  triggerAbilityOrEffect (28 o)
+0x60  target                 +0xa0..+0xb3  options (20 o)
```

et `$$Execute`, lu aux slots d'interface (`interface_slots.tsv` : `ITargetsSelector` slot 0 =
`Select`, slot 1 = `SelectFirst`) :

```
targets = (+0x60 target).SelectFirst(entities)      // ITargetsSelector — UNE cible, la PREMIÈRE
foreach (caster in (+0x58 caster).Select(entities)) // ITargetsSelector — la boucle est ICI
    processor.ActiveAbility(caster, targets, abilityType, options)   // slot 2, arité 4
```

*(#943 — les deux numéros de slot d'`ITargetsSelector` sont donnés dans la phrase juste au-dessus
et plus en fin des deux lignes de pseudo-C : écrits là, `probe_477r24r1` les appariait au
`processor.<Nom>` de la ligne suivante — il juge le receveur sur le SPAN du couple. Le couple faux
était `(slot 0, ActiveAbility)`, alors que le slot 0 cité ici est celui d'une AUTRE interface.)*

Le port faisait l'exact contraire : il itérait les cibles, **triées par id**. Le natif n'appelle
**aucun** `OrderBy` ici (contraste `AttackBehaviour$$Execute`, qui trie quand `Count > 1`).

**Le compte de la fiche était périmé de treize.** Elle annonçait « son unique call-site
(`FinalJustice`) » ; le recensement AST en trouve **14**. La divergence reste néanmoins INERTE sur les
14 — tous ont un sélecteur de cible collapsé à une unité (**9** `Target()`, **5**
`First(...)` / `PickRandomly(…, 1)`) *et* un sélecteur de caster mono. Elle mordrait au premier
call-site dont le sélecteur de cibles rend N : `MartialExemplarAbility$$ExecuteBehaviour` passe
`SortUnitsByDamageUtility(<attaquables adjacents>)` **sans `First`**.

Second volet du résidu, littéral : **les trois nœuds partagent désormais un seul corps**.
`UseNormalAttack` et `UseNormalAttackIfAble` héritent de `UseActiveAbility` ; un test FIGE l'absence
d'`execute` dans leur `vars()` — sinon la réparation ne vaudrait que pour l'une d'elles, ce qui est
l'état d'où l'on vient.

**Le montage qui mesure.** 2 casters × 2 cibles : l'ancien port et le natif rendent le **même
cardinal** (2 dispatches) avec des couples **opposés**. Comparer un compte n'aurait rien vu — le
garde compare les couples.

---

## 3. `#889-r5-r2` — le champ `+0x00`, et pourquoi il ne change rien

Chaîne suivie jusqu'au bout. Le champ arrive en tête des `ActiveAbilityOptions` du slot 2, puis
`ActiveAbilityOperation$$ExecuteInternal` en prend le `GetValueOrDefault` et le passe en **6ᵉ
argument** d'`$$IsInvalidTarget` — dont la signature le **nomme** `invalidTargetPolicy` (le 7ᵉ,
`options+0x08`, est un `ExecutionType` de défaut `StartAbility` ; aucun call-site porté ne l'écrit,
il n'a donc pas de mirror).

L'enum est **lu** dans `enums.tsv` :
`IdunBattle.Operations.ActiveAbilityOperation.InvalidTargetPolicy` = `1=Allow, 2=Skip, 3=Error`.

Corps d'`$$IsInvalidTarget`, verbatim :

```c
if (invalidTargetPolicy == Allow) return false;      // gate COURT-CIRCUITÉ
...
if (!IBrokenTargetingRuleExtensions.IsInvalid(rule)) return false;
if (invalidTargetPolicy != Error) return true;       // invalide, SANS log
<LogError(...)>;                                     // invalide, AVEC log
return true;
```

⇒ **`Skip` et `Error` rendent le MÊME verdict** ; seul le `LogError` les sépare. C'est bien le sens de
« IfAble » — un cast opportuniste dont le refus n'est pas un bug — mais **ce n'est pas un gate
supplémentaire**. Le port avait donc raison de ne pas en inventer un ; ce qui manquait, c'était le
**nom**. La seule valeur qui changerait quelque chose est `Allow`, qu'**aucun** call-site lu ne pose.

`AutoCounterAttackAbility$$CreateBehaviour` pose `Skip` lui aussi : le champ n'est pas spécifique à
« IfAble ».

Le mirror `engine/entities/invalid_target_policy.py` entre au registre `probe_313` **dans le même
commit** — son namespace est `IdunBattle.Operations`, pas `IdunBattle.Entities.Enum`, donc le nom
court aurait cherché en vain. 37 mirrors en bijection, 0 dette.

⚠ **`probe_313` ne tient pas tout** : il compare le *mirror* au *build* et redeviendrait vert après un
renumérotage suivi d'une régénération. Le cran manquant est un test qui garde l'ordinal **mesuré à la
conversion** (`Skip = 2`), plus la démonstration que `2` **nomme autre chose** dans les enums voisins
de la même chaîne d'appel (`ExecutionType[2] = ContinueAbility`) — c'est ce qui rend le nom
obligatoire. Ce test **assertionne son propre non-vide**.

Effet de bord assumé : la clé de diagnostic `if_able` de `darkangels.py` devient
`invalid_target_policy`. Elle n'avait **aucun** autre lecteur.

---

## 4. `#925-r2` — le résidu était écrit À L'ENVERS

La fiche annonçait : « la voie `amount` émet `On(PreAttack = 5)` **inconditionnellement** », et
prédisait **N** émissions pour `HazeOfCorruption`.

**La lecture du code dit 0.** `execute_normal_like` n'appelait pas `pre_attack_triggers` ; elle
appelle `pre_attack_hit_triggers` — `On(PreAttackHit = 6)`, per-coup, un autre événement. La fiche
avait confondu les deux. Le sens de la divergence est donc l'**inverse** : il *manquait* des
émissions.

Les **quatre** call-sites du mode `amount`, tranchés un par un sur leur factory native — jamais par
famille ni par ressemblance :

| call-site | factory native | `isOutsideAttack` |
|---|---|---|
| `PsykerExtraAttackAbility$$CreateBehaviour` | `DSLBehaviors$$AttackWithAttackDamage` | **True** |
| `CursedPlagueBellAttackAbility$$CreateBehaviour` | `DSLBehaviors$$AttackWithAttackDamage` | **True** |
| `SkyStrikeAbility$$ExecuteBehaviour` | `DSLBehaviors$$AttackWithAttackDamage` | **True** |
| `HazeOfCorruption_DamageTransferEffect$$CreateTargetTriggerBehaviour` | **N** × `DSLBehaviors$$AttackDamage` **NUES** sous **UN** `$$Attack` | **False** + 1 émission par l'englobant |

La surcharge d'`AttackWithAttackDamage` a été désignée par ses **xrefs entrantes** (`180ea0f90` pour
Psyker), et son corps lu verbatim : elle construit `AttackDamageBehaviour` **puis**
`AttackBehaviour$$.ctor`, et **retourne ce dernier** — donc `StartAttack` (slot 58) →
`StartAttackOperation$$Execute` → `EvaluateAbilitiesImmediately(PreAttack = 5)`.

⚠ **L'`AbilityOrEffect` de l'englobant de Haze est MIS À ZÉRO**, et c'est lu aux octets
(`local_3b8 = uStack_3b0 = local_3a8 = 0` juste avant l'appel), alors que chaque feuille reçoit le
vrai (`AbilityOrEffect$$op_Implicit`, 24 octets recopiés). Recopier `0x435` sur l'englobant aurait
**inventé** une valeur que le natif ne passe pas — et elle n'est pas neutre :
`BattleQuery$$IsRangedAttack` (slot 3) commence par `if (!ability.HasValue) return false`.

L'émission est placée **avant** la collecte des mods attaquant, exactement où son jumeau
`execute_ability_attack` la place, et pour la même raison native : `SuppressiveFire` écoute ce vecteur
et pose `Pinned`, ce que le coup en cours doit voir.

**Ce que ça coûte** : pour toute unité qui n'écoute pas l'event 5, rien (zéro mutation, zéro tirage —
seuls `SuppressiveFireAddEffectAbility` et `LetTheGalaxyBurnArmAbility` y sont abonnés). Mesure de
non-décalage : `test_sky_strike_live.py` rend les **valeurs identiques** avant et après
(`[6395, 2531, 3409]`), et les tests de flux RNG de Haze passent.

---

## 5. Validation

**Mutants — 12 sur 12 MORDENT, 0 inerte.** Un mutant par cause réparée, plus les inverses :
retour au `UnitSet` d'ids ; itération des cibles ; tri des casters ; `execute` redéfini dans une
sous-classe ; ordinal `Error` au lieu de `Skip` ; champ écrit par `UseNormalAttack` ; gate d'`On(5)`
supprimé ; émission retirée ; drapeau non threadé ; feuilles de Haze emballées ; englobant muet ;
englobant recopiant l'`AbilityOrEffect` des feuilles.

**Tests rejoués** — `test_944_combat_behaviours_offline.py` (17), et, en ciblé :

| passe | résultat |
|---|---|
| offline `925` + `512` + `937` | 29 passed |
| `hateful_assault` + `synaptic_linchpin` | 22 passed |
| `925_fold_pre_attack` + `haze_transfer` | 22 passed |
| `905_sternguard_focus` + `500_foul_infusion` | 16 passed |
| `psyker_splash`, `cursed_plague_bell_attack`, `haze_rng_flow` | 1 + 7 + 9 passed |
| `overwatch` + `549_holy_duel` | 12 passed |
| `summon_consumers` + `normal_like_bounds_rounding` | 30 passed, 1 skipped |
| `478_cleave` | 13 passed |
| `sorcerous_facade_combat` + `929_savage_killer` | 13 passed |
| `black_legion_1029_1020` + `429r1r1_dead_target` | 17 passed |
| `906_rites_of_morkai` | inclus dans les 29 de sternguard |
| cliquets | `probe_313` **0 dette / 37 mirrors**, `probe_181` **0 manquante**, `probe_486r15` sans faute de cette tranche, empreinte `#457` gravée |

**QUATRE rouges rencontrés, QUATRE préexistants** — chacun attribué sur **arbre témoin détaché**
(`git archive origin/master`), et non sur une intuition :

* `test_haze_rng_flow_live.py::test_on_damage_dealt_n_est_pas_gate_par_l_applique` — gate lu
  `if is_attack:` ; `damage.py` n'est pas dans le diff de cette tranche ;
* `test_sky_strike_live.py::test_skystrike_attack_ab_and_spread` — **valeurs identiques**
  `[6395, 2531, 3409]` des deux côtés, ce qui prouve *en plus* que la nouvelle émission ne décale rien ;
* `test_summon_ability_ports_live.py::test_valkyrie_strike_no_immediate_damage` — identique ;
* `test_512_excruciating_frequencies_offline.py::test_1197_…_UNE_seule_source_de_masque` — apparu au
  **rebase**, rouge sur `origin/master` frais (`1108 KissOfDeath`, PR #940). C'est exactement le vice
  « garde d'existence aveugle à la double déclaration » : `probe_181` reste vert à côté.

---

## 6. Ce qui n'est PAS couvert

* **La boucle sur les CASTERS n'est confrontée par aucun montage LIVE à N casters** — aucun des 14
  call-sites portés n'en produit. Le garde est un montage synthétique 2×2 ; la fidélité repose sur la
  lecture du `.ctor` nommé et des slots d'interface, le live n'en est que la non-régression.
* **`InvalidTargetPolicy.Allow` n'est exercé nulle part** : aucun call-site lu ne le pose, donc la
  branche de court-circuit d'`$$IsInvalidTarget` n'est ni portée ni confrontée. Elle le deviendrait si
  un jour un arbre la posait.
* **Le gate `IsInvalidTarget` lui-même n'est pas porté sur cette voie** : le port dispatche
  directement `AttackDamageOperation.execute`. Tant qu'il en est ainsi, `Skip` et `Error` sont
  indistinguables *par construction*, pas seulement par sémantique.
* **`ExecutionType` (`options+0x08`) est lu mais non mirroré** — aucun call-site porté ne l'écrit ;
  le créer sans consommateur alourdirait `probe_313` sans rien garder.
* **`HazeOfCorruption` ne passe pas son `AbilityOrEffect` à ses feuilles** côté port (le natif le
  fait). Écart préexistant, hors périmètre, non instruit ici.
* **La nouvelle émission d'`On(5)` n'est pas confrontée sur un porteur de `LetTheGalaxyBurn`** — le
  seul consommateur qui *consomme un tirage*. Sur les montages joués, le flux RNG est inchangé
  (valeurs identiques), ce qui établit l'absence de régression, pas la présence de l'effet.
* **`summon.py::_summon_on_appearance_attack`** appelle `execute_normal_like` en direct et prend donc
  le défaut `True` : le natif émet bien `On(5)` sur ce chemin (l'attaque normale ouvre son
  `AttackBehaviour`), mais l'effet n'a pas été mesuré isolément — seule la non-régression l'a été
  (`summon_consumers`, `scarab_hive_migration`, `summon_ability_ports`).
