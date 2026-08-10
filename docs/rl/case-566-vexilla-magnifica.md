# #566 — `1183 VexillaMagnifica` : la face COMBAT (NO-OP silencieux) et le filtre que la face DÉCISION n'avait pas

**Statut : LIVRÉ.** Les DEUX faces sont portées et confrontées live — **4 régimes** côté COMBAT,
**3 scénarios** côté DÉCISION, toutes contre-épreuves discriminantes. Un résidu ouvert (`#566-r1`),
qui n'est **pas** dans cette ability.

Porteur : `custoVexilusPraetor` « Aesoth » (Adeptus Custodes) — **HERO, dans le pool** rank 17,
porteur UNIQUE.

## 0. La catégorie ANNONCÉE, et la catégorie MESURÉE

`docs/rl/combat-ability-coverage.md` classait 1183 `DAMAGE(Physical)`. **La colonne est JUSTE sur
l'axe dégât, et MUETTE sur tout le reste** : le cast frappe **DEUX** cibles, en stunne **DEUX**, et
pose un buff sur le caster. Ce n'est pas un patron 2-phases (le cast FRAPPE bien, contrairement aux
quatre tranches de la semaine où la colonne dérivait du `damageProfile` de l'ARME du porteur), mais
un port qui aurait suivi la fiche aurait livré **une** attaque sur **une** cible.

## 1. Le décompilé, terme à terme

`IdunBattleLogic.Entities.Abilities.Active.Loki.VexillaMagnificaAbility$$ExecuteBehaviour`
(slots `DSLFactory` : `+0x78 Behaviors`, `+0x80 Formulas`, `+0x90 Selectors` ; slots `DSLSelectors` :
`+0x48 Caster`, `+0x60 Target`) :

```
dmg     = AActiveAbility.MinMaxDamage(this, abilityState, isPrediction = 0)
        = DSLFormulas.RandomAmount(GetVariableForLevel(0xc = minDmg), (0xd = maxDmg))
profile = AbilityConfiguration.GetDamageProfile(config@+0x60)               # "Physical"
hits    = AbilityConfiguration.GetNumberConstant(config@+0x60, 0x2f = nrOfHits)

sec = DSLSelectors.Cache(
          DSLSelectors.First(
              DSLSelectors.SortUnitsByDamageUtility(
                  DSLSelectors.NormalUnits(
                      DSLSelectors.AdjacentEnemies(Caster@+0x48, unique = 1, selectionType = 3), 3)
                  op_Subtraction Target@+0x60,
                  dmg, unitSelectionType = 3, hits = null),
              amount = 1, ignoreForcedTargets = 0),
          matchAbilityEntities = 1)

b1 = DSLBehaviors.AttackWithAttackDamage(Caster@+0x48, Target@+0x60, dmg, profile, hits,
                                         AbilityOrEffect(this), <options ZÉROÉES>, selType = 2)
b2 = DSLBehaviors.AttackWithAttackDamage(Caster@+0x48, sec,         dmg, profile, hits, …)
b3 = DSLBehaviors.AddEffect(0x48a = 1162 Stunned, GetAbilityStateReference(this),
                            source = Caster@+0x48, targets = op_Addition(Target@+0x60, sec),
                            options = <struct 0x20 ZÉROÉE>)
b4 = DSLBehaviors.AddEffect(0x567 = 1383 VexillaMagnifica_DmgReduction,
                            GetAbilityStateReference(this), Caster@+0x48, Caster@+0x48,
                            turns = DSLFormulas.TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds)))

AActiveAbility.ExecuteAtomic(this, ((b1 & b2) & b3) & b4, entities,
                             groupType = 0x2a = GroupType.Ability_AtomicGroup)
```

i2 : « Deals `nrOfHits`x `minDmg`-`maxDmg` Physical Damage to an adjacent enemy target **and an
additional adjacent enemy unit**. **Both** enemies are Stunned for `nrOfRounds` round, and Aesoth
receives -`dmgReductionPct`% Damage for `nrOfRounds` round. »

### 1.1 Les DEUX `AddEffect` n'empruntent PAS la même surcharge, et c'est ce qui donne les durées

Les deux corps sont **homonymes** : le décompilé ne les distingue pas. Ce sont les **XREFS
entrantes** qui tranchent — `VexillaMagnificaAbility$$ExecuteBehaviour` appelle les deux :

| feuille | surcharge `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect` | 6ᵉ argument | durée effective |
|---|---|---|---|
| b3 (Stunned) | `(effectType, abilityState, source, targets, **options**)` | struct 0x20 **ZÉROÉE** au call-site | AUCUN override → `DefaultAmountOfRounds` de 1162 |
| b4 (DmgReduction) | `(effectType, abilityState, source, targets, **turns**)` | nœud `TurnsFromRounds` | `TurnsFromRounds(nrOfRounds)` |

Recopier la durée de l'un sur l'autre inventerait un `TurnsFromRounds(1)` sur le Stun. **Mesuré
live** : les deux sortent à `RemainingTurns = 2` (2 joueurs ⇒ 1 round = 2 tours) — les valeurs
COÏNCIDENT, donc l'erreur aurait été indiscernable sur ce montage-là ; c'est la LECTURE qui tranche,
pas le chiffre.

### 1.2 Le masque et l'`AbilityAttackType`, LUS

`...VexillaMagnificaAbility$$.ctor` — forme **PRESET + FLAGS** : recopie des 0x40 octets du preset
`<TargetingOptions statics>+0x40`, puis `TargetingOptions..ctor(&opts, &preset, 0x200000000)`, dont
le corps fait `rules = additionalRules | template.rules` (LU). `TargetingOptions$$.cctor` écrit ce
preset : `isSelfCasting = 0`, `range ← <TargetingRange statics>+0x30` = `RANGE_ADJACENT`,
`forceMeleeTarget = 1` (= `RangedBool.False`, l'enum natif est INVERSE), `rules = 0x4000`.

⇒ masque EFFECTIF `0x200004000` = **`TargetIsEnemy | TargetIsNotAnObject`**. **MÊME preset** que
`MartialInspirationAbility$$.ctor` (1191) et `TalonsOfTheEmperorAbility$$.ctor` (1195) du même
module, **MÊME couple preset/flags** que `HolyDuelAbility$$.ctor` (1050) — et c'est exactement
pourquoi il se relit ability par ability : le flag `0x200000000` ne se devine d'aucune voisine.

`AActiveAbility..ctor(this, &opts, **0**)` ⇒ `AbilityAttackType.DirectTargetAttack`. TRANSCRIT :
1183 frappe deux cibles et pose deux effets, ce qui aurait pu faire pencher pour `Others` — c'est
justement ce que fait 1195 (mono-cible) avec le littéral `2`.

## 2. Ce qui préexistait, et ce que #566 ajoute

| pièce | avant #566 |
|---|---|
| effet `1383 VexillaMagnifica_DmgReduction` | **PORTÉ** (`entities/effects/loki/damage_reduction.py`) |
| effet composite `1162 Stunned` (+ 1165/1166/1167) | **PORTÉ** (`entities/effects/loki/status.py`) |
| masque de ciblage | **LU**, mais rangé dans `TARGETING_OPTIONS_UNPORTED` |
| face DÉCISION (`VexillaMagnificaPlaybook`) | **PORTÉE** — utilité = PV de la cible, `MIN_UTILITY = 1`, `ShouldEvaluate` — **SAUF le filtre `HasEffect(Stunned)`**, marqué `TODO` dans sa docstring |
| face COMBAT | **NO-OP SILENCIEUX** : 1183 absente d'`ABILITY_CLASSES` ⇒ cast accepté, tour consommé, 0 dégât, 0 effet, aucune erreur |

#566 livre : la classe `VexillaMagnificaAbility` (arbre DSL), son entrée au registre, la MIGRATION
du masque sur la classe (contrat de disjonction), l'entrée `ABILITY_ATTACK_TYPE`, et le **filtre
`HasEffect(cible, Stunned)`** de la face DÉCISION.

### 2.1 Le filtre de la face DÉCISION, relu intégralement

`IdunBattle.AI.Playbook.Loki.VexillaMagnificaPlaybook$$EvaluateNonComparable` :

```
bucket = new Bucket(0, Nullable(<statics[0]>))            # `$$.cctor` : Fix64(1) = MIN_UTILITY
foreach entity in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition):
    utility = Fix64(UnitExtensions.GetStat(entity, 5 = Health, 0, 0))
    if (EntityExtensions.HasEffect(entity, this.State@+0x20, 0x48a = 1162 Stunned,
                                   onlyActive: null))  continue;
    bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entity, utility))
```

L'exclusion n'est pas théorique : **1183 stunne ses deux cibles**, donc au cast suivant le natif
refuse de re-viser une unité qu'il vient d'immobiliser, même si elle est la plus grosse en PV.
`onlyActive` vaut le littéral `0` ⇒ le port passe par le foyer PARTAGÉ
`battle_query.scene_has_effect` (le MÊME que `SuppressiveFire` 1044 et la triggered `Neuroparasite`
1183 — attention, `1183` est ici un `TriggeredAbilityType`, pas notre `ActiveAbilityType`).

## 3. Les DEUX étages que le décompilé impose et qu'un port naïf rate

### 3.1 Le tri est un ARGMAX, et il consomme UN TIRAGE — placé ENTRE les deux attaques

`SortUnitsByDamageUtilitySelector$$Select` évalue `damage.Calculate(entities)` **UNE fois, AVANT sa
boucle par cible**. Ici `damage` est `MinMaxDamage(isPrediction: **0**)` = un `RandomAmount`
(contraste `AncestralFortuneAbility$$GetAttackTarget`, qui passe `1` = `Half(Sum(...))`,
déterministe) : le `Calculate` finit sur `query.NextInternal(min, max + 1)` du PRNG de BATAILLE.

Le `Cache` étant résolu **paresseusement** par son premier consommateur — et `b1` ne le touche pas —
la séquence `state.rng` est : *coups de b1*, **puis le tirage de tri**, puis *coups de b2*. Le
collapse impératif est donc porté **DANS un `TargetsSelector`** (`VexillaMagnificaSecondTarget`),
jamais calculé d'avance dans `execute_behaviour` : le pré-calculer avancerait le tirage et
désynchroniserait toute la suite.

**MESURÉ, et c'est l'étage qui sépare l'arithmétique de la structure** (régimes à alea neutralisé) :

| régime | coups | tirages NATIF | tirages PORT | identité |
|---|---|---|---|---|
| `nominal` | 2 | 5 | 5 | `2 × 2 + 1` |
| `bascule` | 2 | 5 | 5 | `2 × 2 + 1` |
| `solo` (pool VIDE) | 1 | **3** | **3** | `2 × 1 + 1` |
| `alea` (crit/block naturels) | 2 | 8 | 8 | — (pas d'identité, `PORT == NATIF` seul) |

Le régime `solo` est une **prédiction falsifiable** de la lecture : pool vide ⇒ une seule attaque,
un seul Stun, **et le tirage du tri tombe quand même**. La contre-épreuve `tri_par_ordre_source`
(un `First` NU, sans tri) consomme **un de moins** : le tirage est donc ATTRIBUÉ, pas supposé.

### 3.2 La clé de tri est la PRÉDICTION COMPLÈTE — l'argmax BASCULE avec l'armure

Le call-site emploie la surcharge **4-args** `SortUnitsByDamageUtility(targets, damage,
unitSelectionType, hits)` : **aucun nœud d'ability** (`+0x28` nul) ⇒ le natif prédit avec
`AbilityOrEffect(GetNormalAttackType(owner))`, et `damageProfile: null` ⇒ **perçage 0**, donc
`max(0, d − armure)` (cf. `operations/damage_utility.py` et `case-527-r1`). `hits = null` ⇒ **1**
coup.

**MESURÉ** (même seed, même géométrie, seule l'armure change) :

| régime | armure `tauCrisis` | 2ᵉ cible NATIVE | 2ᵉ cible PORT |
|---|---|---|---|
| `nominal` | naturelle | `u85 tauCrisis` | `u85 tauCrisis` |
| `bascule` | **9000** (> `maxDmg`) | `u83 bloodMephiston` | `u83 bloodMephiston` |

Un port qui prendrait la TÊTE de l'énumération d'adjacence rendrait `u85` **dans les deux** : c'est
exactement ce que fait la contre-épreuve `tri_par_ordre_source`, et elle diverge sur les trois
régimes à pool non vide.

## 4. La confrontation live, et ce qu'elle a établi

### 4.1 Face COMBAT — `probe_566_vexilla_magnifica.py`, 4 régimes

Montage : Aesoth en (3,4), **trois** ennemis adjacents ((3,5) cible du message, (3,3) et (4,4)
candidats), un figurant allié loin (sans lui le cast basculerait le tour et le `dumpRng` d'après
compterait le turn-start ennemi).

* **E1 séquence coup par coup** — `PORT == NATIF` bit-exact dans les **4/4** régimes ;
* **E2 tirages `genrand_int32`** — table du §3.1 ;
* **E3 seconde cible** — table du §3.2 ;
* **E4 effets** — `Stunned(2)` sur les DEUX cibles frappées, `VexillaMagnifica_DmgReduction(2)` sur
  le SEUL caster, **et les trois sous-effets du composite** (`1165` à 2 tours, `1166`/`1167` sans
  durée) — identiques des deux côtés.

Les **quatre contre-épreuves** divergent (chacune retire UNE lecture) :
`sans_2e_attaque`, `pool_sans_soustraction` (le 2ᵉ coup retombe sur la cible du message),
`tri_par_ordre_source`, `stun_sur_cible_seule`.

### 4.2 Face DÉCISION — `probe_566_vexilla_magnifica_decision.py`, 3 scénarios

Oracle = `aiDryRunAllUnits` (`CalculateNextActionForUnit`, read-only). Montage : **DEUX** Aesoth —
le stun n'est atteignable qu'ainsi, le `cooldownTurns` (2) d'un porteur unique étant du même ordre
que la durée du stun. `Movement = 0` sur les deux (le balayage de positions du générateur se réduit
à l'origine, donc l'ensemble des cibles éligibles d'Aesoth#2 est exactement `{A, C}`).

| scénario | état | NATIF | PORT | PORT sans le filtre |
|---|---|---|---|---|
| `sans_stun` | `PV(A)=200000 > PV(C)=100000` | 1183 → **A** | 1183 → **A** | 1183 → A |
| `avec_stun` | A `Stunned` | 1183 → **C** | 1183 → **C** | 1183 → **A** ⇐ MORD |
| `sure_kill` | C à 50 PV, block 0 | **abstention** (attaque normale) | **abstention** | abstention |

Le scénario `avec_stun` est celui qui prouve le fix : **sans le filtre, `master` visait A**, la
cible que le natif écarte.

## 5. Ce qui n'est PAS couvert, nommé

* `IdunBattle.View.AbilityConfigs.Loki.VexillaMagnificaVisuals$$ExecuteInternal` — couche VUE,
  aucun état de bataille. Hors périmètre par nature.
* Les arguments **structurels** que le port ne matérialise sur AUCUN call-site (résidus PARTAGÉS,
  pas ouverts par cette tranche) : `selectionType = 2 / 3` d'`AttackWithAttackDamage` et des
  sélecteurs, `ignoreForcedTargets = 0` de `First`, `matchAbilityEntities = 1` de `Cache` (le
  `Cache` porté est un mémo à slot unique ; le natif a aussi une variante clé par contexte).
* Le régime **cible morte pendant le cast** (b1 tue la cible du message avant que b2 ne résolve son
  sélecteur) : non monté.
* Le `ShouldEvaluate` de la face DÉCISION est confronté **dans les deux sens** (§4.2), mais son
  substrat porté diverge du natif sur un régime précis — c'est `#566-r1` ci-dessous.

## 6. `#566-r1` — **RÉSOLU** : `_enemy_killed_by_normal_attack` était un QUATRIÈME lieu où `get_WillBeKill` était ré-assemblé à la main

> **Fermé le 2026-08-10.** Le foyer LIT désormais `ranked[].killSure`. Confrontation live :
> scénario **`sure_kill_bloque`** (le montage `sure_kill` **sans** `--block-target 0,0`) — natif
> `1183 → u81`, port `1183 → u81`, et la contre-épreuve qui rejoue `dmgMin >= hp` **s'abstient**
> (attaque normale `69 → u85`). Garde offline : `tests/engine/test_566r1_sure_kill_gate_offline.py`
> (10 bras : les trois états du tri-état, le court-circuit, le bruit, le recensement des lecteurs).
>
> ⚠ **La liste des consommateurs, ci-dessous, était FAUSSE — mesure du 2026-08-10.** Les xrefs
> entrantes de `IdunBattle.AI.Playbook.BasePlaybook$$EnemyWillBeKilledWithNormalAttack` en donnent
> **TROIS** : `GravitonRiflePlaybook$$ShouldEvaluate`, `VexillaMagnificaPlaybook$$ShouldEvaluate`
> (le corps COMDAT que `HammerOfWrathPlaybook$$ShouldEvaluate` partage) et
> `SupremeCommanderPlaybook$$ShouldEvaluate` — ce dernier **omis** par la fiche. Les quatre autres
> qu'elle nommait ne portent pas ce gate : `VigilanceEternalPlaybook$$ShouldEvaluate` teste
> `GetStat(unit, 0xc) > 1`, `BloodyFuryPlaybook` et `BlackRagePlaybook` n'ont qu'un
> `GetUseProbability`, `StormcallerPlaybook` n'a ni l'un ni l'autre (il lit l'AUTRE corps natif,
> `WillNormalAttackKill`, par CIBLE, dont le foyer porte déjà les deux crans #372). Le rayon de
> souffle était donc **deux fois plus large** que la réalité — et c'est ce qui avait fait DIFFÉRER
> ce fix. Côté port, `GravitonRiflePlaybook` n'a pas d'équivalent (face DÉCISION non portée).

**DIVERGENCE MESURÉE** (premier montage `sure_kill`, avant que le probe ne neutralise le block) :
`tauCrisis` à **50 PV** sous un coup dont le plan publie `dmgMin = dmgMax = 50` —

* NATIF : `killSure = False` ⇒ `ShouldEvaluate` VRAI ⇒ **il caste 1183** ;
* PORT : `dmgMin >= hp` ⇒ « sure-kill » ⇒ `ShouldEvaluate` FAUX ⇒ **il s'abstient**.

La cause est LUE. `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` :

```
if (this+0x89 != 0) return false;                       # CannotBeGuaranteedKilled
if (this+0x38 == null || Count(this+0x38) < 1) v = this+0x1c;   # dégât MIN
else                                           v = BlockScenarios[0]+0x0c;   # dégât SI BLOQUÉ
return this+0x00 <= v;                                  # PV <= v
```

Une cible à `blockChance > 0` n'est donc **jamais** un sure-kill, quel que soit le dégât. Le port
(`engine/playbook/noncomparable/hammer_of_wrath.py::_enemy_killed_by_normal_attack`) rejoue
`dmgMin >= hp` et rate les **deux** mêmes crans que `projection.ts` avait déjà corrigés chez lui
(#372, commentaire in situ : « c'était un TROISIÈME lieu où la règle de `get_WillBeKill` était
ré-assemblée à la main, donc un troisième endroit où il manquait le gate
`CannotBeGuaranteedKilled@0x89` et la préférence pour `BlockScenarios[0]+0x0c` »).

**Le plan publie déjà le verdict** : `ranked[].killSure` EST `p.willBeKill` décodé, avec les deux
crans. Le port devrait le LIRE au lieu de le re-dériver. ⚠ `killSure` est **TRI-ÉTAT** (`willBeKill
== null` ⇒ le champ n'est pas posé) : la tranche doit décider ce que « non mesuré » vaut, sans
fabriquer un `False` indiscernable d'un « pas de kill garanti ».

**Pourquoi ce n'était PAS fermé ici** (raison d'époque, conservée pour la traçabilité) : la fiche
croyait le foyer partagé par **six** playbooks NonComparable, et `engine/playbook/noncomparable/`
était un foyer d'agents en vol. Le compte réel est **trois** (encadré ci-dessus).

**Le contournement du probe est LEVÉ** : le scénario `sure_kill` garde son `--block-target 0,0`
(il mesure `ShouldEvaluate` en régime sure-kill), et le scénario **`sure_kill_bloque`** qui le
suit retire ce flag — c'est lui qui mesure `#566-r1`. Les deux montages ne diffèrent que par ce
seul argument, et leurs verdicts sont **opposés** : abstention d'un côté, cast de l'autre.

**Le tri-état, tranché.** `killSure` est ABSENT du `ranked` quand `computeWillBeKill`
(`frida/hooks/game/damage-prediction.ts`) rend `null` — décodeur en échec sur `BlockScenarios`, ou
plan d'un bundle antérieur à #372. Le foyer `_normal_attack_sure_kill_state` rend donc `True` /
`False` / `None`, et le booléen public `_enemy_killed_by_normal_attack` rabat `None` sur `False`
= « le gate ne MORD PAS » — même direction que les deux bornes de
`engine.playbook.base.will_normal_attack_kill`, même comportement que le port d'avant, et
**DISCERNABLE** puisque le tri-état reste interrogeable.

## 7. Instruments, rejouables

```
python probe_566_vexilla_magnifica.py [--regimes nominal,bascule,alea,solo]
python probe_566_vexilla_magnifica_decision.py
python -m pytest tests/engine/runner/test_566_vexilla_magnifica_live.py -q
```

La garde (`test_566_vexilla_magnifica_live.py`) ne duplique NI les montages NI les critères : elle
appelle `campagne()` des deux probes — foyer unique. Elle **exige** la bascule d'armure : sans elle
le montage ne distingue pas un argmax d'un `First` d'ordre source, et elle échoue plutôt que de
rendre un vert de régime dégénéré.

## 8. Un rouge de `master` réparé en chemin

`tests/engine/test_433_r4_r2_r1_r2_ability_range_offline.py` était **ROUGE avant cette tranche** :
`1121 ItItches` était sortie de `TARGETING_OPTIONS_UNPORTED` avec son port (#550) **sans** sortir de
`POOL_ABILITIES_WITHOUT_COMBAT_CLASS`, donc `test_the_pool_abilities_carry_a_read_mask` rendait
`masque non lu : [1121]`. #566 retire les DEUX (`1121` et `1183`). C'est le cinquième endroit du
contrat de disjonction, et il se relit **après résolution**, il ne se rature pas d'un seul côté.
