# #909-r7 — le TREIZIÈME porteur, et les deux confrontations que #957-r4 avait laissées ouvertes

**Build** `t6dpr4k06g` · **mesuré** le 2026-08-18 · **outils**
`scripts/python/probe_909r7_explosive_presents_live.py`,
`scripts/python/probe_957r4_faces_decision_live.py` · **gardes**
`tests/engine/runner/test_909r7_explosive_presents_live.py` (7),
`tests/engine/runner/test_957r4_faces_decision_live.py` (8).

Tous les chiffres se **re-dérivent**. Ne pas les citer : les re-jouer.

## 0. Ce que la tranche rend, en une table

| item | énoncé de la fiche | verdict |
|---|---|---|
| `#909-r1` | « les **12** actives de kit dont le playbook natif surcharge `MakeDamagePredictions` » | **PRÉMISSE PÉRIMÉE** — population **VIDE**. Et l'outil qui la mesure **refusait de mesurer** : `master` était ROUGE (§1) |
| `#909-r7` | *(ouvert et fermé ici)* le porteur que le périmètre de `#909-r1` écartait | **PORTÉ + CONFRONTÉ** — `1170 ExplosivePresents`, natif **5** événements contre **1** au port (§3) |
| `#957-r4` volet `1017` | splash de `FragBomb` porté, jamais confronté | **CONFRONTÉ** — set, coups, friendly-fire, et le port rend les mêmes événements (§4) |
| `#957-r4` volet `1179` | fix d'ancre de `CultDemagogue` porté, jamais confronté | **CONFRONTÉ** — le natif choisit la cible de l'ancre **CIBLE** (§5) |
| `#909-r8` | *(ouvert)* les 4 porteurs de `MakeDamagePredictions` hors des 5 voies d'attribution | 3 = voie ATTAQUE NORMALE, 1 sans voie établie (§6) |

## 1. `master` était ROUGE, et c'est ce qui rendait `#909-r1` inmesurable

`tests/engine/test_909_decision_actives_offline.py` rendait **8 ERRORS** sur `origin/master` :
`data/symbols/t6dpr4k06g/metadata/active_playbook_builders.tsv` n'existait pas. La migration vers
`t6dpr4k06g` avait laissé la table sur `rnca9r7q6c`, et `probe_909_decision_actives_kit.py`
**REFUSE** (rc 2) une table d'un autre build — comme il doit.

C'est la **longue traîne silencieuse** d'un changement de build : le refus est correct, personne ne
le voyait, et le résidu qui s'appuyait sur cet outil était donc indispatchable sans le savoir. Table
régénérée (`--regenerer` : désassemblage d'`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`,
appariement slot→lambda décalage `+1`, 221/233 concordants).

## 2. `#909-r1` : la population est VIDE, et le « 12 » ne se re-dérive plus

Re-dérivé **des registres**, pas de la liste de la fiche : sur les **138** actives distinctes des
unités `kind == lineup`, **134** ont une face DÉCISION portée et **4** sont déclarées CONSTANTE au
ledger — **0 non portée**. Les 12 de la fiche ont été fermées par les tranches intermédiaires.

Les **4 CONSTANTE** ont été **re-lues au décompilé** ici, pas héritées du ledger — leurs quatre
`MakeDamagePredictions` (`EntropyCannonsPlaybook`, `LashOfTormentPlaybook`,
`LeadingTheChargePlaybook`, `StrikeFromTheShadowsPlaybook`) sont **toutes** la forme canonique : un
seul `GenerateMultiHitAttackPredictions`, sélecteur `<DSLSelectors+0x60> = Target`, `GetDamage` /
`GetHits` / `Nullable(GetDamageProfile)` génériques, poids `Nullable` VIDE. Les attestations sont
FRAÎCHES.

⚠ **Le corps générique `ComparablePlaybook<T>$$MakeDamagePredictions` LÈVE** (`FUN_1801f4600`) :
« CONSTANTE » ne peut donc pas vouloir dire « le natif n'a pas de corps propre » — chaque sous-classe
comparable en a un. Ça veut dire « ce corps propre EST la forme que le chemin générique du port
emprunte déjà ».

## 3. `#909-r7` — le périmètre de la fiche écartait un porteur, et il était FAUX

**Le périmètre `kind == lineup` est ce qui a caché l'item.** Re-dérivé sur les **233** clés du dict
`active` (`+0x68`) plutôt que sur les kits `lineup` : **64** classes portent `MakeDamagePredictions`,
dont **9** n'ont pas d'état `PORTEE` — 4 CONSTANTE, 4 sans porteur `activeAbilities` (§6), et **une**
vraie manquante : `1170 ExplosivePresents`, porteur `orksRedGobbo` (`npc`), dette déclarée par
`probe_1021_face_decision_au_registre.DETTE`.

**L'écart, MESURÉ avant le port : natif 5 événements, port 1.**

### 3.1 Le décompilé

    IdunBattle.AI.Playbook.Loki.ExplosivePresentsPlaybook$$MakeDamagePredictions
        targets = IdunBattleLogic.Entities.Abilities.Active.Loki.ExplosivePresentsAbility$$GetTargets()
                = op_Subtraction( op_Addition(<DSLSelectors+0x60> = Target,
                                              AdjacentUnits(<DSLSelectors+0x60>, unique: 1, sel: 3)),
                                  <DSLSelectors+0x48> = Caster )
        damage  = <X>Ability$$GetDamage(abilityState)        # corps DEDUPLIQUE, etiquete
                                                             # `VigilanceEternalAbility$$GetDamage`
        return GenerateAttackPredictions(caster, casterPosition, target, targets, damage, .., 0, 0)

**Deux lectures que le décompilé impose :**

1. **Le SET n'a AUCUN wrapper `Enemies`** (contraste `MassDriverAcceleratorAbility$$GetAdjacentAttackTargets`,
   qui en a un) ⇒ **friendly-fire**. L'`op_Addition` est une **concaténation dédoublonnée** : l'ordre
   natif est `[cible, puis le voisinage]` — mesuré `[77, 87, 79, 81, 83]`.
2. **`GenerateAttackPredictions` n'est PAS `GenerateMultiHitAttackPredictions`.** La première invoque
   `IBattleQuery` slot `0x24 = GetAttackPrediction`, la seconde le slot `0x28 =
   GetMultiHitAttackPrediction` — et le **corps de la seconde EST la première**, suivie de `hits - 1`
   répétitions (`IdunBattle.Core.Services.DamagePredictionResult$$Add`). Le chemin plain vaut donc
   exactement **UN** coup, et n'appelle jamais `GetDefaultAttackHits` — donc n'ajoute jamais
   `ExtraHits`. Les deux noms de slot sont **LUS** dans
   `data/symbols/<build>/metadata/interface_slots.tsv`, pas devinés.
   ⚠ **INERTE sur la config courante** (`nrOfHits = 1`, aucun producteur d'`ExtraHits` sur le
   porteur) : c'est un mirror de STRUCTURE, exactement comme le `hits` littéral de `1197` l'était
   avant que `#957-r3` ne lui trouve son régime.

### 3.2 Le montage : le VRAI porteur, pas une greffe

`orksRedGobbo` est `npc`, donc hors pool. Le **chemin de stats EXPLICITE**
(`--explicit-stats orksRedGobbo:5`, cf. `case-92` §5bis recours 4) l'y fait entrer **avec ses stats
npc** — ce qui supprime la réserve d'une greffe (« les stats, traits et armes du vrai porteur ne sont
pas exercées »). Géométrie : `_ringed_cast.ring_scenario`, déjà livrée par la face COMBAT.

**Deux régimes armés**, sans quoi l'accord ne prouve presque rien :

* **armure** (`--armor-target 3000`) — à armure nulle le profil `Blast` est inobservable ;
* **élévation** — l'anneau de `MC1_67` porte trois niveaux distincts (1, 2, 3) autour d'une cible en 2.

Résultat, événement par événement :

    NATIF : [(77,1,2822,5734), (87,1,8733,13101), (79,1,2822,5734), (81,1,2822,5734), (83,1,2822,5734)]
    PORT  : identique — set, ordre, coups, magnitude.     (u87 = l'ALLIÉ, élévation 1 sous un caster
                                                           en 2 : x1,5 ; u85 = le caster, ABSENT)

### 3.3 ⚠ L'artefact de MESURE qui a failli faire accuser le port

Avant de passer `attack_pos`, le port rendait `8733` **contre** `5822` pour l'allié — un écart de
`x1,5` qui ressemblait à un bug de port. Cause :
`engine/playbook/prediction/_shared.py` garde le terme d'élévation derrière
`if scene.elev_by_pos and attack_pos and t_pos` — **un appel sans `attack_pos` saute l'élévation**.

Le terme suit la **TUILE**, pas l'unité : établi par **échange contrôlé** des deux occupants (u87
`8733 → 3901` en montant d'un niveau, u79 `5822 → 8733` en descendant). C'est la forme d'erreur que
le CLAUDE.md décrit sur les régimes de montage — **deux bras qui n'étaient pas dans le même régime**,
transposée à l'axe de l'appel.

### 3.4 Contre-épreuve par mutation — 3 mutants, 2 mordent, le 3ᵉ est DÉCLARÉ muet

| mutant | effet |
|---|---|
| `1170` hors de `_SPECIAL_ABILITY_CLASSES` | `port []` contre 5 événements natifs — avec `selector_only`, **sans classe d'ability le port n'émet plus RIEN** |
| `_AOE` sans `Sub(..., Caster())` | le CASTER `u85` apparaît en 2ᵉ position |
| `1170` hors de `_MAKE_DMG_SELECTOR_ONLY` | **MUET** — voir ci-dessous |

⚠ **Le mutant muet est un résultat, pas un oubli.** La voie `selector_only = False` émet
`[<Target>] + (sélecteur \ <Target>)`, or l'`op_Addition` natif place **déjà** `Target` en tête du
sélecteur : les deux voies rendent la **même liste, dans le même ordre**. L'appartenance reste JUSTE
(le natif n'a aucun batch `<Target>` séparé) et **redeviendrait observable** dès qu'un
`aoe_overrides` distinguerait les deux batchs. Ce qui la garde n'est donc pas un observable mais la
**FORME** (`test_l_appartenance_aux_registres`), et le commentaire du registre le **dit**.

## 4. `#957-r4` volet `1017 FragBomb` — l'oracle DIRECT

`FragBombPlaybook` surcharge `MakeDamagePredictions` : l'oracle est `aiPlaybookPredict`, qui invoque
cette méthode même. Montage `ring_scenario` (cible au centre d'un anneau à 6 voisins marchables,
caster dans l'anneau, allié `astraCreed` dans le voisinage de la CIBLE) :

    caster=u85 cible=u77 allie=u87 anneau=[87, 79, 81, 83]
    NATIF : [(77,[6]), (79,[3]), (81,[3]), (83,[3]), (87,[3])]
    PORT  : identique     (`make_damage_predictions` via `ai.context.build`)

* **SET** : exactement cible + voisinage natif, **caster EXCLU** ;
* **COUPS** : `nrOfHits` = 6 sur la cible, `nrOfHits_2` = 3 sur chaque adjacent — les deux surcharges
  de `_frag_bomb_inputs` ;
* **FRIENDLY-FIRE** : l'ALLIÉ `u87` **EST** prédit. La face COMBAT le mesurait déjà ; la face DÉCISION
  ne l'avait jamais mesuré.
* **CONTRE-CAS** (seed 31337, tout le monde à ≥ 4 hex) : un SEUL événement. Le splash n'est pas un
  forfait.

Mutants : `_AOE` sans `Sub(Caster)` → `u85` apparaît ; `_AOE` en `AdjacentEnemies` → `u87` disparaît ;
`_frag_bomb_inputs` sans `aoe_overrides` → le splash passe à 6 coups. **3/3 mordent.**

## 5. `#957-r4` volet `1179 CultDemagogue` — un autre oracle, et un régime à DEUX conditions

`CultDemagoguePlaybook` surcharge `EvaluateInternal` et n'a **aucune** `MakeDamagePredictions` : ni
`aiPlaybookPredict` ni `pairUtility` ne rendent son utilité (le corps générique **lève**). L'oracle
est le **tour d'IA observé** (`aiDryRunAllUnits`) — la CIBLE que le natif choisit.

**Le régime discriminant exige DEUX choses**, et c'est ce qui a demandé 19 montages :

* **(a)** un écart de tuiles libres entre les deux cibles **sous le plafond `nrOfSummons`** — au-dessus,
  `min(., 8)` égalise les deux et l'ancre ne départage plus ;
* **(b)** que la cible **PAUVRE** soit la **PREMIÈRE énumérée** — l'ancre CASTER a un terme 1 CONSTANT
  sur les cibles et un terme 2 nul (aucun decoy/neophyte posé), donc toutes ses utilités sont ÉGALES,
  et `IdunBattle.AI.BucketSystem.Bucket<…>$$AddAction` ne remplace que sur amélioration STRICTE.

L'ordre d'énumération **n'est pas celui des identifiants** (mesuré `[79, 83, 77, 81]` sur un montage) :
il se **LIT** (`abilityTargets`), il ne se suppose pas.

    caster=u85  nrOfSummons=8  encombreurs=4  montages joues=19
    cible PAUVRE=u77 (1 tuile libre <=2hex)  cible RICHE=u79 (10)  ecart plafonne=7
    ordre d'enumeration natif : [77, 79]      (la PAUVRE est premiere)
    natif             : 1179 -> u79
    port ancre CIBLE  : 1179 -> u79       port ancre CASTER : 1179 -> u77

⚠ **Le critère de sélection du montage ne doit JAMAIS regarder le port qu'il teste.** La première
version triait sur « les deux ancres du port désignent des cibles différentes » : sous la mutation
« ancre ramenée au CASTER », la **RECHERCHE** échouait (« aucun montage n'arme le régime ») au lieu du
**VERDICT** — un rouge qui accuse le harnais. Le critère ne porte plus que sur des propriétés du
PLATEAU et du SÉLECTEUR NATIF ; la dégénérescence est redevenue un **témoin que le test évalue**.

Mutant (`_free_tiles_around` ancré au caster) : témoin `« régime DÉGÉNÉRÉ : les deux ancres désignent
u77 toutes les deux »` **et** verdict `« le natif cible u79 ; ancre CIBLE -> u77 ; ancre CASTER -> u77 »`.

## 6. `#909-r8` — les 4 porteurs hors des 5 voies d'attribution

`17 NormalAttack`, `1030 Loki_NormalBossAttack`, `1157 BladeOfMagnus`,
`1162 AncientFury_NormalAttack` portent `MakeDamagePredictions` et **aucune unité ne les porte** dans
les 5 voies dérivables du gameconfig (`unit_map find --ability` rend 0 pour les quatre).

**Trois sur quatre sont la voie ATTAQUE NORMALE**, portée par un chemin ENTIÈREMENT DIFFÉRENT
(`engine/playbook/prediction/normal_attack.py`) : `1030` y est explicitement câblée (branche
`Traits.Contains(0x7e7 Boss)`, cf. `#419-r1-tr14-r5-r2-r1`). Ce n'est donc pas un trou, c'est un
**autre axe**.

Le quatrième, **`1157 BladeOfMagnus`**, existe comme **config d'ability** (`attackRangeType: Melee`,
plus une entrée `abilityPowerModifiers`) et n'a **aucune voie établie** — ni les 5 du gameconfig, ni
un câblage normal-attack lisible. Résidu `#909-r8`.

## 7. Ce que cette tranche NE couvre PAS

* la **fidélité** des 134 faces DÉCISION portées : `probe_909` atteste leur EXISTENCE, jamais leur
  justesse — et cette tranche n'en a re-lu que 5 (les 4 CONSTANTE et `1170`) ;
* les dicts `+0x88` (triggered), `+0x98` (non-owner), `+0xa8` (specific) — hors axe ;
* les **11** `SANS_VERDICT` restants de `probe_1021` (dette déclarée, hors périmètre) ;
* pour `1179`, la **magnitude** de l'utilité : seul l'ARGMAX est confronté (le natif ne publie pas
  l'utilité d'un comparable qui surcharge `EvaluateInternal`) ;
* pour `1017`, le **domaine de ciblage TUILE** côté générateur Comparable — résidu PRÉEXISTANT
  `#419-r1-tr14-r5-r2-r1-r1-r1-r1`, non rouvert ;
* la couverture générée (`kit-coverage`, `combat-ability-coverage`) n'a **pas** été régénérée : elle
  appartient au MERGE. `1170` étant `npc`, la couverture de kit ne devrait pas bouger ; le compte de
  face DÉCISION de `probe_1021`, lui, passe de 12 à **11** sans-verdict.
