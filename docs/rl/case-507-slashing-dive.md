# #507 — `1091 SlashingDive` : l'ability que l'ABSENCE d'un symbole avait classée illisible

**Statut : LIVRÉ (2026-08-07).** `1091 SlashingDive` entre au registre COMBAT avec son masque de
ciblage et son littéral `AbilityAttackType`. Le no-op silencieux est fermé, et le verrou qui la
tenait — « aucun ctor à lire » — était un **faux négatif de table**.

---

## 1. La question, posée avant la méthode

`1091 SlashingDive` et `1064 Loki_SwoopingHawk` sont les **deux seules** héritières de
`IdunBattleLogic.Entities.Abilities.Active.Loki.DiveAttackAbilityBase`. Le port de #502 avait fait
toute la mécanique sur la base. La question de cette tranche n'était donc pas « comment marche
1091 » mais :

> **La classe `SlashingDiveAbility`, dont aucun symbole n'existe dans nos tables, se comporte-t-elle
> exactement comme sa sœur — ou porte-t-elle une surcharge que l'absence cachait ?**

`abilities/targeting.py` posait le problème sans le trancher :

> « aucune classe `SlashingDiveAbility` n'existe dans les tables […] donc aucun ctor à lire.
> L'absence ne prouve RIEN — un ctor trivial `return <Base>$$.ctor(this);` est DÉDUPLIQUÉ par
> IL2CPP et n'a qu'un seul propriétaire nommé. Trancher exige le slot de vtable de l'INSTANCE, au
> runtime. »

C'est exactement ce cran qui manquait, et c'est par là que la tranche commence.

## 2. Le partage, prouvé — et par DEUX voies indépendantes

**Voie 1, RUNTIME** (RPC `resolveMethodPtr`, session live, build `rnca9r7q6c`). On demande le slot de
méthode de la CLASSE, en remontant la hiérarchie :

| cible | profondeur du 1ᵉʳ corps | classe qui le porte |
|---|---|---|
| `SlashingDiveAbility..ctor` | **0** | `SlashingDiveAbility` — **même adresse d'entrée que `SwoopingHawkAbility..ctor`** |
| `SlashingDiveAbility.ExecuteBehaviour` | 1 | `DiveAttackAbilityBase` |
| `SlashingDiveAbility.GetTargetTilesSelector` | 1 | `DiveAttackAbilityBase` |
| `SlashingDiveAbility.GetTargetUnitsSelector` | 1 | `DiveAttackAbilityBase` |
| `SlashingDiveAbility.GetMovementBehavior` | 1 | `DiveAttackAbilityBase` |

Le ctor est à profondeur 0 (la classe en a bien un) **et** à la même adresse que celui de sa sœur :
IL2CPP a **fusionné les deux corps**, qui sont tous deux `return DiveAttackAbilityBase$$.ctor(this);`.
Aucune méthode à profondeur 0 en dehors du ctor ⇒ **aucune surcharge**.

**Voie 2, TABLE DE CLASSES** (`data/symbols/rnca9r7q6c/frida/classes.tsv`) :

```
IdunBattleLogic.Entities.Abilities.Active.Loki.SlashingDiveAbility   240  ...DiveAttackAbilityBase
IdunBattleLogic.Entities.Abilities.Active.Loki.SwoopingHawkAbility   240  ...DiveAttackAbilityBase
```

Même parent, **même taille d'instance** : la fille n'ajoute aucun champ.

⚠ **Le fait générique** : `frida/methods.tsv` et `ghidra/functions.tsv` sont indexées par ADRESSE.
Un corps fusionné n'a **qu'un seul propriétaire nommé** — ici `SwoopingHawkAbility`. « Le symbole
n'existe pas » ne dit donc rien de la classe ; `classes.tsv`, lui, la voit. Les deux tables
viennent du **même dump** : ce n'était pas un manque de données, c'était une lecture par la
mauvaise table.

## 3. Ce qui DIFFÈRE de 1064 — la config, et rien d'autre

Relu au gameconfig, ability par ability (jamais recopié de la sœur) :

| | `1064 Loki_SwoopingHawk` | `1091 SlashingDive` |
|---|---|---|
| `damageProfile` | `Piercing` | **`Power`** |
| `nrOfHits` | 1 | 1 |
| `attackRangeType` | `Melee` | `Melee` |
| `dmg` (3 valeurs/niveau) | `164,128,91` (lvl 17) | `1819,1455,1091` (lvl 65) |

Le profil est le seul axe qui les sépare, et c'est **la garde qui a été rendue mordante** : voir §6.

## 4. Le port

La base a été **déplacée** dans son namespace natif :
`scripts/python/engine/runner/abilities/loki/dive_attack.py` = mirror de
`...Active.Loki.DiveAttackAbilityBase` (sélecteurs de ligne, `GetMovementBehavior`, la feuille
d'attaque d'ability, l'arbre d'`ExecuteBehaviour`, et la classe `DiveAttackAbility` qui porte
`execute_behaviour`).

Les deux héritières n'y ajoutent **que** leur identité et leurs deux données de registre —
exactement ce que fait le natif, dont les classes filles ne contiennent qu'un ctor :

* `abilities/aeldari.py::SwoopingHawkAbility` (1064)
* `abilities/thousandsons.py::SlashingDiveAbility` (1091)

**Pourquoi déplacer plutôt qu'importer d'une faction à l'autre** : il n'existe **aucun** import
croisé entre modules de faction dans `abilities/` (mesuré : `handler.py` est le seul consommateur
de chacun). Un `thousandsons -> aeldari` aurait été le premier, pour du code qui n'appartient à
aucune des deux. Le namespace natif tranche : la base est un `Loki.*`, elle vit sous `loki/`.
La généralisation a porté sur **quatre** accesseurs de config (`dive_attack_profile`, `_hits`,
`_damages`, `_is_melee`), tous clés par `ABILITY_ID`, plus le paramètre `is_melee` de la feuille —
seule donnée que #502 avait figée en constante de module.

Données de registre, posées **dans le même commit** que l'entrée :

* `TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy, self_cast=False,
  range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)` — forme de ctor **PRESET STATIQUE
  COPIÉ** : la base recopie les 0x40 octets du preset `+0x40` et les passe à
  `AActiveAbility..ctor(this, &opts, 0)`. Masque effectif = `<preset>+0x28` du
  `TargetingOptions$$.cctor` = `0x4000`.
* `ABILITY_ATTACK_TYPE[SlashingDive] = DirectTargetAttack` — le 3ᵉ argument, **transcrit**, ni
  déduit du profil (`Power`) ni de la forme de l'arbre (une VAGUE, pas une cible unique).

**Aucun compteur à décrémenter** : `1091` n'avait **pas** d'entrée dans
`TARGETING_OPTIONS_UNPORTED` — elle y figurait comme non-lu **en commentaire**. Seul ce paragraphe
est réécrit (la raison de son absence a changé : « illisible » → « portée ailleurs, contrat de
disjonction »). Vérifié en re-comptant par le code, pas en soustrayant d'un chiffre écrit :
`probe_181` = 116/116, `test_targeting_options_sources` + les trois autres gardes = 44 verts.

## 5. La gate de confrontabilité — le NPC est le mirror, pas un montage

`1091` n'a **aucun porteur lineup** : `thousNpc2Screamer` (npc), `thousSmnScreamer` et
`thousSmnScreamerHSE` (summons). Les trois voies ont été instruites ; c'est la **quatrième** qui a
gagné :

1. **SUMMON via son invocateur** — elle existe et a été tracée : `MasterOfTheTutelaries` (1096,
   `thousInfernalMaster` « Abraxas », **DU POOL**, et déjà portée) pose l'effet 1197, qui arme la
   triggered 1173 → Screamer. Mais un summon **s'observe et ne se commande pas** (#291) : ni le
   choix de cible ni l'alignement de la ligne ne sont pilotables. Écartée comme **moins fidèle**,
   pas comme impossible.
2. **GREFFE de l'ability sur une unité du pool** — non nécessaire.
3. **Injection catalogue du npc** — non nécessaire.
4. **CHEMIN DE STATS EXPLICITE** (`case-92` §5bis recours 4) — **retenue**.
   `units.npc[thousNpc2Screamer].stats[]` porte **45 paliers**, donc
   `--explicit-stats thousNpc2Screamer:45` amène le porteur RÉEL avec **ses** stats (HP 9796,
   Damage 3959, AbilityLevel 65), **ses** traits (`Daemon`, `Flying`, `WeaverOfFate`) et **son**
   arme, **commandable** comme n'importe quelle unité joueur.

⚠ **Un bug d'outillage bloquait cette voie, et il a été corrigé** : `rl_duel._parse_place_specs`
coupait la spec de placement au **premier** `:`, or un unitId de palier npc en porte déjà un —
`--place thousNpc2Screamer:45:3,0` rendait `col/row non entiers`. Autrement dit **aucun porteur npc
à palier n'était plaçable sur une tuile choisie**, alors que `--explicit-stats` exige justement
cette forme d'id. Corrigé en coupant au **dernier** `:` (sans effet sur la forme sans palier, qui
n'en a qu'un).

## 6. Validation — cinq scénarios, tous port == natif, et QUATRE contre-épreuves

Montage : `MC1_67`, colonne 0, caster en `(0,0)`, trois `orksNob` alignés en `(0,1)/(0,2)/(0,3)`,
atterrissage attendu `(0,4)`. `state.rng` calé sur le MT live (`dumpRng`) avant les deux casts.

| scénario | ce qu'il exerce | port | natif |
|---|---|---|---|
| **VAGUE** (seed 31337) | topologie + 3 montants | `1477 / 1164 / 873`, atterrit `(0,4)` | **identique** |
| **REPLI** (bouchon sur `(0,4)`) | branche FAUSSE du `ConditionalSelector` (le `Randomize`) | atterrit `(1,4)` | **identique** |
| **ANCRE** (1 seule cible) | « dernière tuile OCCUPÉE » ≠ « fin de la ligne » | atterrit `(0,2)` | **identique** |
| **LÉTAL** (PV forcés à 900) | létalité + ancre figée AU CAST | 3 morts, atterrit `(0,4)` — **derrière un cadavre** | **identique** |
| **BLOCK** (seed 777) | la branche block du dégât | `1477 / 0 / 873` | **identique** |

**Témoin de non-dégénérescence** : trois montants **non nuls et deux à deux distincts**
(`1477 / 1164 / 873`), un rang qui **bloque**, trois unités qui **meurent**.

⚠ **Le seed est un choix MESURÉ, pas un confort.** Sous `777`, le 2ᵉ rang **bloque** et son montant
natif vaut `0` — un rang à zéro rend une vague « splash » (même montant partout) **irréfutable**.
Deux parades ont été essayées et **écartées par la mesure** : `--block-target 0,0` (il met la stat
de BASE à zéro, les traits posent leur bonus par-dessus) et le déplacement de la ligne de la
colonne 3 à la colonne 0 (même résultat, **aux mêmes montants** — c'est le TIRAGE, pas la tuile).
Le seed `777` n'a pas été jeté : il est promu en **scénario BLOCK**, parce qu'un rang bloqué est un
observable que le port doit suivre.

**CONTRE-ÉPREUVES** (mutation d'un seul terme du port, montage nominal inchangé) :

| mutation | accord port/natif | verdict |
|---|---|---|
| aucune (témoin) | **oui** | — |
| `profil = Piercing` (celui de 1064) | **non** — port `2910/2328/1746` | la garde MORD |
| `hits = 2` | **non** — port `2954/2328/1746` | la garde MORD |
| `dmg = [dmg0]*3` (modèle splash) | **non** — port `1477/1477/1477` | la garde MORD |
| `is_melee = False` | **oui** | **N'EXERCE RIEN** — cf. §7 |

Tests rejoués : `test_slashing_dive_live` **14 verts** ; `test_swooping_hawk_live` **11 verts**
(la base déplacée) ; `test_487_hellfyre_missile_rack_live` + `test_doombolt_live` **6 verts**
(`thousandsons.py` modifié) ; `test_ability_registry_ratchet` **9 verts** ;
`test_targeting_options_sources` + `test_270r1_volet2_dict_keys_enum_offline` +
`test_433_r4_r2_r1_r2_ability_range_offline` + `test_287r4_targeting_needs_instance_offline`
**44 verts** ; `probe_181` **116/116, 0 manquante** ; `probe_120` étage 0 « littéral de ctor
manquant : aucun ».

## 7. Résidus

* **`#507-r1` — `attackRangeType` (l'axe `is_melee`) n'est PAS discriminé, et ce n'est pas une
  limite du port mais du PORTEUR.** Contre-épreuve mesurée : forcer `is_melee = False` ne change
  RIEN au dégât, parce que le Screamer n'a qu'**une** arme (`weapons` = un seul bloc, sans `Range`)
  — les deux branches lisent la même. Les **trois** porteurs de 1091 sont des Screamers, donc
  aucun montage ne peut l'exercer sur cette ability. La valeur reste **relue** de la config (jamais
  codée en dur) ; le jour où la base gagne une héritière à deux armes, l'axe devient mesurable.
* **`#502-r1` (hérité, inchangé)** — `StartAttack` / `FinishAttack` non portés : leur seul effet
  observable est de fusionner en UNE attaque les tuiles consécutives occupées par la MÊME unité.
  Il faut une unité **multi-hex** alignée sur la vague. Vaut identiquement pour 1091.
* **`DiveAttackAbilityBase$$GetTargetUnitsSelector` non porté** (commun aux deux héritières) :
  c'est l'accesseur de la face PRÉDICTION/UI (`Enemies(Caster, Units(GetTargetTilesSelector(), 1, 3), 3)`),
  pas un maillon d'`ExecuteBehaviour`, qui reconstruit son propre `Units(AtIndex(tiles, i), 0, 0)`
  tuile par tuile. Nommé ici, non ouvert en résidu séparé : il appartient à la face décision.

## 8. Ce que cette tranche referme dans le backlog

* `#433-r4-r2-r1-r2-r2-r1-r1-r1-r2` — « `1091 SlashingDive` n'a pas de masque, et son ctor est
  illisible ». **Le masque est lu**, et la méthode qu'il prescrivait (« le slot au runtime ») est
  celle qui a tranché.
* La puce « `1091 SlashingDive` reste non portée » de `case-502-swooping-hawk.md` §1.

## 9. Ce qu'on retient

**Une table qui ne voit pas un symbole n'a pas dit qu'il n'existe pas — et la table d'à côté, tirée
du MÊME dump, le voit.** Le verrou de 1091 tenait depuis `#433-r4-r2-r1-r2-r2-r1-r1-r1-r2` sur une
lecture de `methods.tsv` / `functions.tsv`, indexées par adresse. `classes.tsv` portait la réponse
tout du long, et le slot runtime l'a confirmée en une requête. Avant de conclure « illisible »,
demander **quelle table** on a interrogée, et **ce qu'elle indexe**.
