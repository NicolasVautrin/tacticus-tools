# #1024-r5 — le gate de couverture d'item avait UN cran, il en fallait DEUX ; et `ShieldOfFaith` est portée

Tranche à deux items de la Sisterhood, appariés par leur voie CONDITIONNELLE. Les deux sont clos,
et pour des raisons **opposées** : l'un était un faux positif de l'audit, l'autre un port entier.

| item | voie | état de départ | verdict |
|---|---|---|---|
| `TheArdentBlade` | item (relique 1468) | `PARTIEL` | **le PARTIEL était FAUX** — mesuré, puis réfuté LIVE |
| `ShieldOfFaith` | mythic (1453) | `ABSENT` | **PORTÉE** et confrontée live, 6 mutations vues rouges |

Effet sur l'audit : voies conditionnelles non portées **5 → 3**, `PARTIEL` **3 → 2**, voie `item`
**1 → 0**. Re-dériver (`audit_kit_coverage.py`), ne pas citer.

---

## 1. `TheArdentBlade` — « le montage est écrit et il ne s'exécute rien » était FAUX

Le gate `GATE_EFFET_CLASSE` de `kit_item_voies` concluait : *une pose d'owner-effect dont la cible
n'a aucune classe dans `EFFECT_CLASSES` ne monte RIEN*. Vrai quand le NATIF a une classe que le port
n'exécute pas ; **faux quand le natif n'en a aucune**.

Mesure sur `rnca9r7q6c` (`data/symbols/<build>/ghidra/functions.tsv`) :

| effet posé | classe native | verdict |
|---|---:|---|
| `CabalOfSorcerers_ExtraDamagePct` | `...Effects.Loki.CabalOfSorcerers_ExtraDamagePctEffect`, **4 corps propres** | dette RÉELLE → `PARTIEL` |
| `GuardianConstruct_ExtraDamagePct` | idem, 4 corps | dette RÉELLE → `PARTIEL` |
| `TheArdentBlade` (1462) | **ZÉRO** symbole `.Entities.Effects.*` dans tout le build | JETON → `PORTE` |

1462 est un **jeton à un coup** : posé par `TheArdentBlade_InitAbility.CreateBehaviour`
(`AddEffect` + `ActivateEffect`), relu par le `HasEffect(Owner, 1462, onlyActive: true)` du
`CreateTrigger` de `TheArdentBlade_TriggerAbility`, et rien d'autre. Le `BaseEffect` générique que
rend `EffectFactory.create` (`registry.get(name, BaseEffect)`) porte le bon `effect_type` et le bon
flag `active` : **c'est le mirror fidèle**, pas un trou. Le compter `PARTIEL` envoyait un agent
porter une classe qui n'existe pas.

### Deux angles morts du détecteur, tous deux trouvés par contre-épreuve

Chacun produisait un **faux `False`** — donc un SUR-comptage en `PORTE`, la direction dangereuse :

1. **deux conventions de nommage coexistent** — `<X>Effect` *et* `<X>_Effect`. Ne lire que la
   première rendait `False` sur `TerminatorArmour_ReduceDmg_Effect`.
2. **le natif nomme parfois sa classe d'après l'ABILITY, pas d'après l'`EffectType`** —
   `IdunBattle.Entities.Effects.Loki.BlightedLandEffect` porte l'effet
   `BlightedLand_ExtraDamagePct`. L'égalité stricte y rendait `False` sur un item à dette réelle.

L'appariement se fait donc **dans les deux sens** (égalité, ou l'un préfixe l'autre en `<x>_`), même
convention que `_item_de`. Délibérément permissif : `False` est le seul verdict qui RETIRE du
travail, il doit être difficile à obtenir.

**NON MESURÉ** (table absente, build désynchronisé) → le gate **tombe**, comme avant ce cran :
sous-compter fait RENONCER, sur-compter fait perdre du temps.

### La confrontation LIVE — l'état 3 d'une relique, joué pour la première fois

`case-1013-r2` nommait ce montage comme NON JOUÉ. Il l'est :
`tests/engine/runner/test_1024r5_the_ardent_blade_jeton_live.py` (5 tests).

* **NATIF** : `decisionView.units[<adeptCelestine>].effects` porte l'`EffectType` 1462
  (`includeInactive: true`, pour que « absent » ne se confonde pas avec « désactivé »).
* **PORT** : la même capture seedée porte l'instance 1462, **ACTIVE**, et
  `TheArdentBladeTriggerAbility` est inscrite sur le porteur.
* **LE GATE** : `ardent_blade_trigger_tree().should_trigger(...)` rend **VRAI** — le jeton est
  *consommé*, pas seulement posé. C'est la différence entre « l'effet existe » et « la mécanique
  tourne ».
* **CONTRE-ÉPREUVE** : même porteur injecté au catalogue, relique NON équipée → aucun 1462 des deux
  côtés, aucune inscription.

⚠ **`--equip-relic` n'injecte PAS son porteur, contrairement à `--equip-mythic`** — et c'est ce qui
bloquait l'état 3 en une commande. `rl_duel build --equip-relic` s'applique au BC **normalisé**
(après que le pool est figé) et refuse `'adeptCelestine' absent de BC.Units` ; `--equip-mythic`,
lui, augmente le catalogue avant la normalisation. Le montage tient donc en deux temps
(`catalog_inject.write_relic_seed_bc` puis `build --seed-bc`). Résidu `#237-r1`.

---

## 2. `ShieldOfFaith` — le port entier

RE : décompilé ghidra, `rnca9r7q6c`. Transcription verbatim dans l'en-tête de
`engine/runner/operations/triggers/loki/shield_of_faith.py`. Le décompilé **confirme mot pour mot**
la lecture de `case-1024` §1 — rien à corriger.

```
CreateTrigger   = ( On(5 = PreAttack, true) & IsUnitOnTileWithEffect(Target@+0x60, [5 = Fire]) )
                | ( On(9 = Attack, true) & WasCrit() )
                & IsUnit(Attacker) & AreFriends(Owner@+0x30, Attacker, 0, false)
                & HasRarity(Attacker, idun.meta.Rarity.Mythic = 5)
CreateBehaviour != Custom -> TriggerAbilityDelayed(Owner@+0x30, 1453, OnlyAliveAndTargetable)
CreateBehaviour == Custom -> If( IsAlive(Attacker) & AmountIsZero(CurrentShieldAmount(Attacker,3)),
                                 CreateShield(Attacker, PercentageOf(StatAmount(Attacker, Health,
                                     Maximum), ConfigVar(0x96 = shieldPct)), TurnsFromRounds(1)) )
```

**L'ability se re-déclenche elle-même** : les deux vecteurs ne posent rien, ils enfilent un
`TriggerAbilityDelayed` qui revient en `EventTriggerType.Custom`. Câbler le behaviour directement
sur `On(Attack)` donnerait le bon observable et le **mauvais ordre**.

### Le registre — le natif n'a qu'UNE voie tertiaire

L'entrée va dans **`RELIC_ABILITY_TRIGGERS`**, pas dans un registre `MYTHIC_*` : `equip_mythic`
écrit le MÊME `BC.Units[].TertiaryAbility` et déclenche le MÊME
`TriggeredAbilityComponent$$TryAdd(id, tertiaryState, 3)` qu'une relique équipée — seule la GARDE
d'attribution diffère. Un second registre inventerait une distinction que le natif n'a pas. C'est
aussi ce qui donne à `triggered_ability_state` le couple **TERTIAIRE** (niveau 1..4, mult 100) et
non le couple PASSIF (50/180), qui lirait le dernier palier en silence.

Aucun `TARGETING_OPTIONS` / `ABILITY_ATTACK_TYPE` : ce sont des données d'`ABILITY_CLASSES` (actives)
et `ShieldOfFaithAbility` dérive de `BaseTriggeredAbility`.

### Un étage neuf, parce que le natif l'a

`CurrentShieldAmount` — mirror 1:1 de
`IdunBattle.Entities.Formulas.CurrentShieldAmountFormula$$Calculate`, qui est une **SOMME** de
`IdunBattle.Entities.UnitExtensions$$GetShield` sur les unités du sélecteur, pas la lecture d'une
unité unique. Accesseur `ctx.current_shield_amount` (même substrat `ShieldComponent` que la pose).
Sa dégradation est **permissive** et elle est nommée : l'unique forme d'emploi native est
`AmountIsZero(CurrentShieldAmount(...))`, donc un `0` non mesuré ferait PASSER le gate. Le seul
consommateur porté tourne toujours avec un `State`.

`DSLSelectors$$Attacker` trouve ici son **second** consommateur, et le premier à le rendre
OBSERVABLE : il est résolu une fois puis passé en `actor_id` du contexte DSL, donc `Actor()` désigne
le `Attacker` natif — branche `MV71SniperDroneSquad` comprise.

### La confrontation live — replay-diff sur la même graine

`tests/engine/runner/test_1024r1_shield_of_faith_live.py` (5 tests). L'attaque normale est jouée au
NATIF puis **rejouée** au port (`Runner.apply(AttackUnitMessage)`) sur la MÊME graine MT
(`dumpRng`), et les boucliers sont comparés **par entité**.

Mesure : natif **3765** = 50 % × hpMax 7530 ; port **3765**. `remaining` 2 des deux côtés.

| bras | montage | attendu |
|---|---|---|
| `positif` | mythique L4, `--crit 100,700` | bouclier NON NUL des deux côtés |
| `sans_crit` | `--crit 0,0` | ZÉRO des deux côtés — gate `WasCrit()` |
| `sans_rarete` | `--unit-stat <att>:Rarity=4` | ZÉRO des deux côtés — gate `HasRarity` |

Le bras de rareté est **le seul qui sorte du régime dégénéré** (`rl_duel build` impose
`targetRarity = 5`, donc partout ailleurs `HasRarity` est uniformément VRAI). Les deux bras négatifs
**citent** le bras positif et exigent qu'il soit non nul — un double zéro seul serait un accord vide.

---

## 3. Ce que les MATRICES DE MUTATION ont trouvé — deux gardes qui ne gardaient rien

Les deux fixes de cette tranche ont été soumis à mutation, et **chacune a révélé un cran aveugle**.

**Sur le gate (`test_1041`, 4 mutations)** — remplacer l'appariement à deux sens par une égalité
stricte ne faisait rougir **AUCUN** des 15 étages. Cause : aucun item *dans la portée du gate* n'en
dépend aujourd'hui (`BlightedLand`, qui en dépendait, a été porté depuis et en est sorti). Étage
ajouté, ancré sur une propriété du **BUILD** (indépendante de l'état du port), avec son propre
non-vide assertionné. Après : 4 mutations → **4 assertions distinctes**.

**Sur le port (`test_1024r1`, 6 mutations)** — muter `StatPart.MAXIMUM` en `CURRENT` ne faisait
rougir personne : l'attaquant était à PV pleins, les deux parts de stat coïncident. Le montage
blesse donc l'attaquant (`--unit-stat RemainingHealth=3000`) et le test **assertionne son propre
régime discriminant** avant d'en conclure quoi que ce soit. Après : **6/6** vues rouges.

> Au passage, ce tri-état a mordu : `combatSnapshot` ne publie pas de champ `health` courant, la
> première écriture rendait `None` — l'assertion l'a attrapé au lieu de dégrader en vert.

---

## 4. Un BLOCAGE périmé, corrigé au passage

`engine/playbook/non_owner_attack.py` déclarait `ShieldOfFaithNonOwnerPlaybook` bloquée
**`capteur`** : « AUCUN canal `rarity` n'existe côté port… il faudrait
`combatSnapshot.units[].rarity`, donc une fenêtre de reinject ». **Périmé** : le capteur est armé
depuis #1039 et consommé depuis #999-r3, et c'est MESURÉ en live sur cette ability même —
`ctx.rarity == 5`, et la contre-épreuve `Rarity=4` éteint le bouclier des deux côtés. Le blocage
passe à `aucun` ; ce qui reste est le PORT du corps. Résidu `#1024-r7`.

C'est exactement le mode de défaillance que le CLAUDE.md nomme : un champ `BLOCAGE` n'est jamais
re-mesuré, donc il fait écarter un résidu au dispatch longtemps après que sa cause a disparu.

---

## 5. Ce qui n'est PAS couvert

* le vecteur `On(PreAttack) & IsUnitOnTileWithEffect(Target, Fire)` de `ShieldOfFaith` est **PORTÉ**
  mais **NON CONFRONTÉ** live (seul `Attack & WasCrit` l'a été). `adeptCanoness`, au roster, porte
  `BrazierOfHolyFire` qui pose du feu — le montage existe. Résidu `#1024-r6` ;
* la face **DÉCISION** de `ShieldOfFaith` (`ShieldOfFaithNonOwnerPlaybook`) — `#1024-r7` ;
* la **résurrection** de `TheArdentBlade` elle-même (spawn de la Geminae, sa mort, le
  `Resurrect`) : ce fichier prouve le JETON et son gate, pas le cycle complet. Le port du cycle est
  livré depuis #1013-r2 et gardé offline (23 tests) ;
* `TurnsFromRounds` : le port passe par `convert_rounds_to_turns` (1 tour/round en 1v1), non
  re-confronté ici — `remaining` coïncide, ce qui le contraint sans le décomposer ;
* le `customUtility` de `TheArdentBlade` (face DÉCISION, `#1013-r3`) reste ouvert.
