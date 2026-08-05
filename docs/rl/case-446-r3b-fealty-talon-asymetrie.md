# #446-r3b — `Fealty` et `TalonOfHorus` : le mirror est ATTESTÉ, et l'asymétrie a une CAUSE

Résidu §9 de `case-446-r3-repugnance-followup.md`. Rien à porter côté DÉCISION : ce qui manquait
était la **confrontation live**, et elle est faite. Ce qui change, c'est la **description** de la
face COMBAT — elle n'est pas ce que la fiche parente disait.

## 1. La prémisse est vraie À LA LETTRE, fausse dans son MÉCANISME

La fiche parente écrivait « ces deux-là foldent en combat et pas en décision ». Le fait de symbole
est exact ; l'image du « fold » ne l'est pas, et le décompilé relu sur `rnca9r7q6c` le tranche.

Les **quatre** `<X>_NormalAttackAbility` de la famille (`Boltstorm`, `RighteousRepugnance`,
`Fealty`, `TalonOfHorus`) ont la **même** forme d'exécution :

```csharp
<X>_NormalAttackAbility$$ExecuteBehaviour(abilityState, entities):
    weapon = ALoki_NormalAttackAbility$$FindAttackWeapon(entities)
    if (weapon == null) return
    if (weapon.get_IsMelee())  return Execute<X>(abilityState, entities, weapon)
    else                       return ALoki_NormalAttackAbility$$ExecuteBehaviour(...)

<X>_NormalAttackAbility$$Execute<X>(abilityState, entities, weapon):
    sel = <X>Ability$$GetAdditionalTargets(dsl)              // Triggered.Loki.<X>Ability
    ALoki_NormalAttackAbility$$ExecuteInformWeapon(weapon, entities, null)
    ALoki_NormalAttackAbility$$ExecuteNormalAttack(abilityState, entities, weapon)   // la PRIMAIRE
    b = DSLBehaviors$$Foreach(sel, t => GetAdditionalTargetsAttackBehavior(t, abilityState))
    AActiveAbility$$ExecuteAtomic(b, entities, 0x2a)
    return ALoki_NormalAttackAbility$$ExecuteTriggerAbilities(entities, weapon)

<X>_NormalAttackAbility$$GetAdditionalTargetsAttackBehavior(target, abilityState):
    return DSLBehaviors$$Attack(caster, target,
                                GetAdditionalDamageBehaviour(abilityState, target), ctx)
```

⇒ `$$GetAdditionalTargetsAttackBehavior` consomme `<X>_NormalAttackAbility$$GetAdditionalDamageBehaviour`
sur une cible **ADDITIONNELLE** — jamais la cible PRIMAIRE. Cette face-là est un **CLEAVE**, et elle
vaut pour les quatre.

> ⚠ **RECTIFIÉ par #478** (`case-478-cleave-additional-targets.md`) : « l'**unique** consommateur »
> était FAUX. Il y en a **DEUX**. Le second est
> `<X>_NormalAttackAbility$$GetCustomNormalAttackBehaviour` (vslot `0x4a8`, appelé par
> `ALoki_NormalAttackAbility$$ExecuteNormalAttack` et composé **dans** l'attaque primaire), il frappe
> bien la cible **PRIMAIRE**, et il **n'existe que pour `Boltstorm` et `RighteousRepugnance`** — le
> symbole est absent pour `Fealty` et `TalonOfHorus`. C'est donc lui, la **cause nommée** de
> l'asymétrie décrite ci-dessous : un symbole présent d'un côté, absent de l'autre. Mesure :
> `adeptMorvenn` inflige `787, 969` (coups d'arme) **puis** `502, 506, 557` à sa cible primaire dans
> une géométrie où son cleave n'a **aucune** cible — **1565 PV** que ce dossier ne voyait pas.
> La gate est aussi INVERSÉE pour `Boltstorm` : il cleave sur `IsMelee == 0`, pas sur `IsMelee`.

Côté DÉCISION, seuls ces deux derniers portent `$$PredictAttack` + `$$GetAdditionalDamagePrediction`
— et ce qu'ils font est d'**attribuer UN paquet de dégât additionnel à la cible PRIMAIRE**
(mesuré et mirroré par #446-r1 / #446-r3). `Fealty` et `TalonOfHorus` ne font **aucune** attribution :
leur prédiction est la base `ALoki` nue.

**Le texte i2 corrobore, et c'est une seconde source indépendante du décompilé** :

| ability | texte i2 |
|---|---|
| `RighteousRepugnance` | « deal an additional 3x 873-1164 Power Damage **to the target** and to all enemy units adjacent to both the target and to Morvenn Vahl » |
| `TalonOfHorus` | « he also deals 3x 1746-2325 Power Damage to all enemies adjacent to both the target of the attack and to Abaddon » — **aucune clause « to the target »** |

L'asymétrie est **dessinée**, pas un oubli. Les inscrire au registre `_MELEE_FOLLOWUP_PASSIVES`
« par cohérence » serait un fork de port — et donnerait `+2700/+4050/+3 coups` de trop sur `Fealty`,
`+1953/+2931/+3` sur `TalonOfHorus` (mesuré, §4).

Le sélecteur de cibles additionnelles, lu (`DSLSelectors+0x48` = Caster, `+0x60` = Target ;
`AdjacentEnemies(unit, unitTile, unique)` = `Enemies(unit, Units(AdjacentTiles(unitTile)) − unitTile)`) :

* `TalonOfHorusAbility$$GetAdditionalTargets` = `AdjacentEnemies(Caster, <+0x50>) & AdjacentFriends(Target, <+0x78>)` ;
* `FealtyAbility$$GetAdditionalTargets` = la même intersection (ancre `<+0x58>`), **moins `Target`** ;
* `RighteousRepugnanceAbility$$GetAdditionalTargets` = `AdjacentEnemies(Caster, 1, 3) & AdjacentUnits(Target, 1, 3)`
  — l'autre surcharge, même sémantique (déjà portée côté playbook, `playbook/righteous_repugnance.py`).

## 2. Confrontabilité — les deux porteurs, et par quel chemin

| ability | porteurs gameconfig | état |
|---|---|---|
| `Fealty` (1512) | `darkaBossLion` (Lion El'Jonson), **npc**, voie `passive` | absent du seed BC ⇒ **greffe écrite** |
| `TalonOfHorus` (1484) | `blackAbaddon` (**lineup, AU POOL**) voie `item` + 5 npc `blackBossAbaddon*` voie `relic` | `BC.Units[blackAbaddon].PassiveAbilities` = `[1064]` ⇒ **greffe écrite** |

`blackAbaddon` est au pool et porte l'arme mêlée (`Power`, pierce 40) : c'est le porteur **nominal**
de `TalonOfHorus` (l'i2 nomme Abaddon). `Fealty` se greffe sur `ultraTitus` (au pool, mêlée `Chain`).

**⚠ `--unit-stat "X:PassiveAbilities=[<id>]"` NE SUFFIT PAS**, et le croire coûte la mesure de la
face COMBAT. Il n'écrit que `BC.Units[].PassiveAbilities`. Or **`Fealty` et `TalonOfHorus` sont
absentes de `BC.Abilities.PassiveAbilities`** du seed, et `refresh_ability_configs` **ne les dérive
pas non plus** (leurs porteurs de catalogue sont un npc et la voie ITEM) — mesuré, pas supposé. La
face DÉCISION s'en moque (`PredictAttack` ne lit aucune config), mais la face COMBAT lit
`AbilityConfiguration$$GetVariableForLevel(0xc/0xd)` dans `$$GetAdditionalDamageBehaviour` : config
nulle ⇒ exception managée ⇒ **« system error » au cast**, même verrou que #226/#237.

Mesure du premier passage : l'attaque **primaire** passe (2493 PV retirés) puis le cleave **faute**.
C'est au passage une confirmation que le natif entre bien dans la branche cleave en mêlée — mais la
mesure est inexploitable. Le montage passe donc par `catalog_inject.write_grafted_seed_bc`, qui fait
les **deux** écritures, puis `rl_duel build --seed-bc`.

## 3. Le montage — un seul runner, trois porteurs, la même cible

`MC1_67` / seed `4463111`, placement EXACT au build (`--place` / `--a-place`, aucun drive) :

```
              adeptMorvenn (3,3)
blackAbaddon (2,4)   astraBullgryn T (3,4)   ultraTitus (4,4)
              necroWarden A (3,5)
```

`A` est adjacente NATIVE à `T` **et** aux deux porteurs greffés : elle appartient donc à leur
`GetAdditionalTargets`, et le cleave natif a bien une cible. Sans cette contrainte, « pas de fold en
décision » se mesurerait là où il n'y a de toute façon **rien** d'additionnel — une mesure vide.

Attestations qui font échouer le montage (`MontageError` → `pytest.fail`, jamais un skip) :
attaques normales live `1220` / `1205` / `1182` (sans la greffe, les deux premières rendraient `69`),
`1512`/`1484`/`1107` présents dans l'`AbilitiesComponent`, adjacence native des trois porteurs à `T`,
adjacence native de `A` à `T` et aux deux cleaveurs, positions obtenues == positions voulues.

## 4. Mesure DÉCISION — le DIFFÉRENTIEL à trois lignes

`adeptMorvenn` porte `RighteousRepugnance` **naturellement** : c'est le **témoin POSITIF**, mesuré
sur le même board, le même seed et la même cible. Oracle = `aiPlaybookPredict` (l'étage PRÉDICTION,
surtout pas `pairUtility` — cf. #446-r3 §9).

| porteur | passif | attaque normale | natif `(rawMin, rawMax, hits)` | port LIVRÉ | port SANS registre | port fold GREFFÉ |
|---|---|---|---|---|---|---|
| `ultraTitus` | `Fealty` | `1220` | `2004, 3008, 4` | **identique** | *identique* (rien à retirer) | **`4704, 7058, 7`** |
| `blackAbaddon` | `TalonOfHorus` | `1205` | `2410, 3615, 5` | **identique** | *identique* | **`4363, 6546, 8`** |
| `adeptMorvenn` | `RighteousRepugnance` | `1182` | `2885, 4324, 5` | **identique** | **`1544, 2314, 2`** | *identique* |

Les trois lignes, ensemble, sont ce qui interdit le régime dégénéré :

* la 2ᵉ prouve que la mesure **sait voir un fold qui manque** (elle déplace le témoin positif) ;
* la 3ᵉ prouve qu'elle **sait voir un fold de trop** (elle déplace les deux autres) ;
* sans elles, « natif et port sont d'accord » serait vrai pour une raison structurelle.

⚠ `adeptMorvenn` rend ici **exactement** les chiffres de #446-r3 (`2885, 4324, 5` au contact,
`1544, 2314, 2` sans fold) alors que sa tuile diffère — recoupement inter-tranches, non recherché.

## 5. Mesure COMBAT — le cleave natif inflige bien le dégât

Exécution live de l'attaque normale sur `T`, PV lus avant/après :

| porteur | ability | PV perdus par `astraBullgryn` (PRIMAIRE) | PV perdus par `necroWarden` (ADDITIONNELLE) |
|---|---|---|---|
| `ultraTitus` (`Fealty`) | `1220` | 2493 | **3104** |
| `blackAbaddon` (`TalonOfHorus`) | `1205` | 3756 | **3632** |

La face COMBAT native **existe et mord**. L'asymétrie ne veut donc pas dire « ces abilities ne font
rien » : elle veut dire que l'IA **ne compte pas** ce dégât dans la prédiction de la cible primaire.

**Côté PORT, le cleave n'était implémenté NULLE PART** au moment de ce dossier — balayage à
périmètre dérivé de `engine/runner/**` : **0 site**. L'unique vecteur d'attaque normale du port
combat était `damage_ops._Normal.execute(attacker, target)`, **mono-cible**. Résidu **`#478`**,
**LIVRÉ depuis** (`engine/runner/abilities/loki/additional_targets.py`) — avec un **second volet**
que ce dossier n'avait pas vu, cf. l'encadré du §1.

⚠ Le décompte des coups du cleave n'est **pas** décomposé ici (le montant est
`RandomAmount(minDmg, maxDmg)` × `ConfigConst(0x2f)`, mais la matérialisation par coup et l'étage
armure ne sont pas séparés) : c'est le travail de la tranche qui **portera** le cleave, pas de
celle-ci, qui atteste un mirror de DÉCISION.

## 6. Contre-épreuves — le cliquet mord, et il discrimine

Trois mutations jouées, chacune rejouée puis annulée :

| mutation | attendu | mesuré |
|---|---|---|
| `_MELEE_FOLLOWUP_PASSIVES += ("Fealty", "TalonOfHorus")` — le geste « par cohérence » | rouge | **`test_le_mirror_tient_champ_a_champ` ROUGE**, message chiffré (`port 4704 / nat 2004`, `hits 7 / 4`) |
| `_MELEE_FOLLOWUP_PASSIVES = ()` — la régression de #446-r3 | rouge | **2 rouges** (`mirror` + `greffer_le_fold`) |
| le bras « fold greffé » greffe un passif INEXISTANT — **le discriminant est tué** | rouge | **`test_greffer_le_fold_par_analogie_fait_diverger` ROUGE** (« le discriminant est MORT ») pendant que `mirror` reste **VERT** |

La troisième est la plus importante : elle mesure que **le vert du test de mirror, seul, ne vaudrait
rien**. C'est exactement le régime dégénéré, provoqué et vu.

## 7. Résidus NOMMÉS

* ~~**`#478` — le CLEAVE de la face COMBAT n'est porté pour AUCUNE des quatre abilities.**~~
  **LIVRÉ (2026-08-05), `case-478-cleave-additional-targets.md`.** ⚠ Et la façon dont ce résidu était
  écrit a coûté : « le sélecteur est **déjà porté** côté playbook […] c'est un câblage COMBAT, pas
  une RE de sélecteur » est **faux sur les deux membres**. Les quatre sélecteurs sont distincts (dont
  deux par la **surcharge** de primitive appelée, tranchée par les xrefs entrantes), la gate est
  **inversée** pour `Boltstorm`, et il manquait un **second consommateur** entier — celui qui frappe
  la cible primaire. Écart réellement livré : **3104 / 4835 / 2894 / 3038** PV de cleave **plus**
  **1565** et **1584** PV de fold primaire.
* **Les playbooks TRIGGERED `FealtyPlaybook` (1512) et `TalonOfHorusPlaybook` (1484) ne sont pas
  portés** — ils sont nommément dans la liste des résidus ATTACK de `#419-r1` (`Fealty` y figure,
  `TalonOfHorus` y est cité en tête des 4 ATTACK de relique). Cette tranche ne les touche pas ;
  conséquence directe : ne pas lire un écart de `pairUtility` sur ces porteurs comme un reliquat
  de la face PRÉDICTION, qui est ici attestée exacte.
* **`--armor-target` n'est pas exercé** : le montage tourne sur l'armure nominale. La prédiction
  d'attaque normale étant pré-armure (`armorBefore = 0`, cf. #446-r3 §6), ce levier ne mord pas sur
  ce canal — mais il mordrait sur la face COMBAT, qui reste à porter.
* **Non couvert** : le régime `FindAttackWeapon == null`, la cible à bouclier, le régime `hit_mult`
  (`MkXGravis`), et le cran RANGED (aucune gate à contrôler ici — il n'y a de fold d'aucun côté,
  donc pas de bascule à observer ; le contrôle de gate vit dans #446-r3).

## 8. Livré

* `scripts/python/probe_446_r3b_fealty_talon_asymetrie.py` — montage attesté (greffe à deux
  écritures + placement exact), différentiel à trois lignes, volet COMBAT, balayage dérivé du port.
* `scripts/python/tests/engine/test_446_r3b_fealty_talon_live.py` — **5 gardes**, dont le cliquet
  d'asymétrie et ses deux bras de discrimination.
* **Aucune ligne de `engine/` modifiée** : le port était juste, c'est l'attestation qui manquait.
