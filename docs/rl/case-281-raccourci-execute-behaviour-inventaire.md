# case-281 — le raccourci `execute_behaviour` : inventaire, tri par GATE, et un montage corrigé

**Résidu #277-r1.** #277 a établi qu'appeler `<X>Ability().execute_behaviour(...)` à la main
court-circuite `AbilityHandler.visit_ActiveAbilityMessage`, donc l'émission de
`On(PreUnitAbility)` que le natif place tout en haut de
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`. Il a laissé au backlog le
balayage des call-sites, en citant « ~136 call-sites dans 71 fichiers » et **trois** familles
consommatrices.

**Les deux chiffres étaient faux, et le second dangereusement.** Re-dérivés ici :

| | #277 (annoncé) | #281 (mesuré) |
|---|---|---|
| call-sites de montage | ~136 dans 71 fichiers | **130 dans 67 fichiers** (AST, `self.`/`super()` exclus) |
| familles natives abonnées | 3 | **10** (13 sites d'abonnement) |
| familles qui rendent le raccourci faux | (non trié) | **1** — `HazeOfCorruption` |

Le tri final n'est donc PAS « 136 montages à router » : c'est **1 famille inconditionnelle** et,
sur l'arbre livré, **2 montages réellement faux — tous deux corrigés ici**. Les 4 autres
call-sites qui la citent prennent le raccourci **exprès**, comme terme de réfutation.

> Chiffres mesurés **après** rebase sur `origin/master` @ `8aa49b93`, qui contient déjà #283 —
> celle-ci a corrigé `probe_178` et ajouté deux raccourcis volontaires. Les re-dériver plutôt que
> citer cette ligne : `python scripts/python/probe_281_pre_unit_ability_shortcut.py --step classify`.

---

## 0. L'ordinal cité par tout le dépôt est FAUX

`EventTriggerType.PreUnitAbility` vaut **42 = 0x2a** — lu dans l'enum porté ET dans le décompilé
(`IdunBattleLogic.Entities.DSLTriggers$$On(df, 0x2a, 1)`). Le dépôt écrit `0x2b` partout :
**113 occurrences** de la forme `On(0x2b)` / `PreUnitAbility = 0x2b`, dans le moteur, les tests,
les probes et 15 case-docs. `0x2b = 43` est `UnitHealed`.

L'erreur est **inerte à l'exécution** (le code lit toujours l'enum, jamais le littéral) mais elle
a contaminé l'énoncé de cette tâche elle-même. Elle n'est pas corrigée ici : 113 sites répartis
sur des fichiers que plusieurs PR en vol modifient — la migration est un lot à part (→ backlog
`#281-r3`). Ce qui est écrit ici cite `On(PreUnitAbility)`, sans ordinal.

⚠ Piège adjacent, et c'est pour ça que le `0x2b` a survécu : **`0x2b` est légitime ailleurs** —
c'est la clé de constante de config `extraHit` (`GetNumberConstant(cfg, 0x2b)`), présente ~100
fois. Un `sed` global sur `0x2b` casserait ces citations-là. Seule la forme accolée à
`PreUnitAbility` est fausse.

## 1. QUI s'abonne — scan binaire, pas grep de décompilé

`probe_281_pre_unit_ability_shortcut.py --step natif` scanne les **44,6 Mo de sections
exécutables** et retient tout `call` vers une cible d'abonnement dont `edx` (2e argument = le
`EventTriggerType`) vaut l'ordinal. **13 sites, 13 fonctions.**

Trois pièges ont dû être franchis, et chacun aurait produit un inventaire silencieusement faux :

1. **Le code managé n'est PAS dans `.text`.** La section `.text` fait 2,8 Mo, la section
   **`il2cpp`** 41 Mo. Un scan limité à `.text` rend **0 abonné** — un « aucun » parfaitement
   crédible. Le probe balaie donc toutes les sections marquées `IMAGE_SCN_MEM_EXECUTE`.
2. **Un `call` clobbe `rdx`.** Remonter naïvement au dernier `mov edx, imm32` sans s'arrêter aux
   `call` intermédiaires « résout » 350/350 sites — dont plusieurs avec l'immédiat du site voisin,
   et surtout en masquant les relais. Le balayage arrière s'arrête au premier `call`.
3. **Trois voies d'abonnement, pas une.** Au-delà de `DSLTriggers$$On` :
   * **ctor de trigger INLINE** — la fonction alloue l'objet et appelle son `.ctor(obj, ordinal,
     flag)`. C'est le cas d'`…AnvilShieldAbility_FrozenAttackerAdvantage$$CreateTrigger`. Ghidra
     nomme ce ctor `Stash.Native.StashNative.u003COpenCardOrModalInternalu003Ed__46$$.ctor` :
     corps trivial **dédupliqué**, le nom ne veut rien dire. Ce qui l'identifie est la
     distribution de son 2e argument sur ses **361** sites — elle épouse `EventTriggerType`
     (`UnitDeath=0` ×224, `PreUnitDeath=1` ×17, `Attack=9` ×7, `TurnEnd=23` ×4…).
   * **relais** — `IdunBattle.Entities.Effects.BaseEffect$$On(this, eventTrigger)` repasse
     l'ordinal reçu, dans le même registre. 48 sites, **1** à `PreUnitAbility`.

### Les 13 sites

| fonction contenante | voie |
|---|---|
| `IdunBattle.Entities.Effects.Idun_MeleeCounterAttackEffect$$CreateTargetTrigger` | On |
| `IdunBattle.Entities.Effects.Idun_MeleeCounterAttackEffect$$GetTriggerType` | On |
| `IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal` | relais |
| `IdunBattle.Entities.Effects.Loki.JustSummonedEffect$$CreateRemoveEffectTrigger` | On |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateTrigger` | On |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtectorAbility$$CreateTrigger` | On |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtector_ProtectAbility$$CreateTrigger` | On |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_FrozenAttackerAdvantage$$CreateTrigger` | **ctor** |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuryFromTheDelveAbility$$CreateTrigger` | On |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MartialSuperiorityAbility$$CreateTrigger` | On |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SavageKillerAbility$$CreateCharacterActiveAbilityTrigger` | On |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SavageKillerAbility$$GetInitialTarget` | On |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.StandVigil_UpdateEffectRangeAbility$$CreateTrigger` | On |

`GetTriggerType` et `GetInitialTarget` ne sont **pas** des attributions bancales : le premier
choisit entre `On(0x11)` et `On(PreUnitAbility) & IsNormalAttack` ; le second enveloppe
`On(PreUnitAbility, 1)` dans un `ConditionalSelector`. Relus au décompilé pour cette fiche.

`AnvilShield` manquait à un scan « `DSLTriggers$$On` seul » — et c'est exactement la famille que
#277 citait. Sans le motif ctor, l'inventaire aurait été à la fois plus court ET faussement
rassurant.

## 2. Le tri se fait sur le GATE D'ATTAQUE, pas sur l'abonnement

C'est le point que #277 n'avait pas franchi, et il retourne complètement le verdict :
**`execute_behaviour` est TOUJOURS une voie de CAST d'ability**. Une famille gatée
`IsNormalAttack` ne peut donc structurellement pas partir sur ce chemin — son abonnement est réel
mais **inerte pour ce motif**.

| famille | trigger natif (lu) | rôle du porteur | gate d'attaque | porté | raccourci faux ? |
|---|---|---|---|---|---|
| **HazeOfCorruption** | `On(PreUnitAbility, 1) & get_OwnerIsCaster` | **caster** | **AUCUN** | oui | **OUI, toujours** |
| SwornProtector (×2) | `… & AreEnemies & (AbilityHasAttackType(0)|AbilityHasAttackType(1)) & …` | ennemi du caster | `AbilityHasAttackType(0\|1)` | oui | seulement si l'ability est une attaque |
| MartialSuperiority | `… & IsDirectTargetAttack(@0x130) & OwnerOrOwnerTileIsTarget & NOT IsTurnOf(Owner) & IsMeleeAttack` | **cible** | attaque directe + melee adjacent + tour adverse | oui | conditionnel |
| AnvilShield | `… & IsNormalAttack & get_OwnerIsTarget & …` | cible | **`IsNormalAttack`** | oui | **non** (jamais sur un cast) |
| FuryFromTheDelve | `(… & IsNormalAttack & get_OwnerIsActor) \| On(0x26) & …` | acteur | **`IsNormalAttack`** | non | **non** |
| SavageKiller / StandVigil | — | — | — | **non portés** | non (offline) |
| MeleeCounterAttack / JustSummoned / ATeleporting | effets, sans porteur de kit | — | — | **non portés** | non (offline) |

**`HazeOfCorruption` est la seule famille sans aucun gate d'attaque avec le porteur en position de
caster.** C'est elle, et elle seule, qui rend le raccourci faux inconditionnellement — et c'est
cohérent avec #277, qui l'avait rencontrée sur `deathBlightlord`.

Corollaire pour les 4 call-sites de `test_supreme_commander_live.py` / `probe_95r2` : le caster y
est `astraCreed`, porteur de `SwornProtector`, mais l'ability castée (`SupremeCommander`) est un
buff — `AbilityHasAttackType(0|1)` est faux, le trigger ne part pas. **Les router aurait été le
piège** : ça leur aurait ajouté des vecteurs de turn-flow qu'ils n'ont pas, pour corriger un
défaut inexistant.

## 3. L'inventaire des call-sites

`--step callsites` / `--step classify`. AST sur tout `scripts/python` **sauf le moteur**
(`scripts/python/engine/**`, où l'appel EST la voie normale : le handler appelle la behaviour
après avoir émis le vecteur).

> **Piège de filtre, mesuré** : `tests/engine/runner/…` contient le segment `engine`. Un filtre
> « le chemin ne contient pas `engine` » efface **toute** la suite de tests — c'est ce qui donnait
> d'abord « 23 call-sites dans 16 fichiers ». L'exclusion se fait par `Path.relative_to`, pas par
> sous-chaîne.

Le caster n'est presque jamais un littéral au call-site : il est **constante de module**
(`CASTER_VIS = "deathBlightlord"`). Le périmètre d'un call-site est donc
`littéraux de la fonction ∪ littéraux top-level`. Sans les constantes de module,
`test_flail_swing_live.py` — dont le caster EST un porteur Haze — ressortait « sain ».

**130 call-sites, 67 fichiers** : `SAIN` 109, `A EXAMINER` 10, `INDÉTERMINÉ` 7, `A CORRIGER` 4.

`INDÉTERMINÉ` (7) = le montage ne nomme **aucune** unité (roster du seed BC, ou caster passé en
CLI comme `probe_61_ability_hits.py`). « Aucun porteur cité » n'y est pas une preuve — c'est dit
plutôt que compté comme sain.

### Les montages réellement faux — et ceux qui ne le sont qu'en apparence

Corrigés par cette fiche :

| call-site | caster | geste |
|---|---|---|
| `tests/engine/runner/test_flail_swing_live.py` volet (1) | `deathBlightlord` | routé par `Runner.apply` |
| `tests/engine/runner/test_flail_swing_live.py` volet (3) | `deathBlightlord` | routé par `Runner.apply` |

Les 4 `A CORRIGER` que le gate signale encore sont tous **tolérés**, chacun avec sa raison dans
`GATE_ALLOWLIST` — et la distinction est de fond, pas de confort :

* `probe_277_flail_damage_stages.py::_replay` et `test_flail_swing_live.py::…_cast_entry_point_
  haze_pool_live` (arrivés avec #283) plus `probe_281::measure_flail` : le raccourci y est la
  **colonne de réfutation**. Ces montages exigent `direct != live`. **Les router les viderait de
  leur contenu** — c'est le cas limite où « corriger » détruit la mesure.
* `test_ability_hits_channel_live.py::_frenzy_offline` : **faux positif** de l'heuristique
  « constantes de module ». Le caster de CE call-site est `FRENZY_VIS = blackObliterator` ;
  `deathBlightlord` est la constante `CASTER_VIS` d'**autres** volets du même fichier, qui eux ne
  prennent pas le raccourci.

`probe_178_overkill_gate.py::_replay_attack`, 3ᵉ montage faux de l'inventaire initial, a été
corrigé par #283 pendant ce travail : le gate ne le voit plus.

## 4. Le montage corrigé, et sa preuve

`tests/engine/runner/test_flail_swing_live.py` — ses deux rejeux offline passent de
`FlailSwingAbility().execute_behaviour(...)` à `Runner.apply(ActiveAbilityMessage(...))`.

Le montage était **juste par accident de placement** : `_advance_and_place` pose le 2e ennemi à
`distance(coord, caster) > 1`, ce qui vide le pool
`Damageable(AdjacentEnemies(Self) & AdjacentFriends(Target))` de
`HazeOfCorruption_TargetFinderAbility$$CreateBehaviour`. Le seul paramètre qui sépare les deux
régimes est **cette distance**.

`probe_281_pre_unit_ability_shortcut.py --step mesure --regime {far,near}` monte le MÊME montage
et ne bouge QUE le 2e ennemi (`applyAction move` ignore portée et propriété) :

| régime | d(caster, 2e ennemi) | bonds natifs | genrand natif | tirages raccourci | tirages production | live | raccourci | production |
|---|---|---|---|---|---|---|---|---|
| `far` (géométrie ACTUELLE) | 2 | 0 | 6 | 6 | 6 | `[5070, 4555, 4881]` | **== live** | **== live** |
| `near` | 1 | 1 | 12 | **6** | **7** | `[4762, 4852, 4819]` | `[5070, 4555, 4881]` **+0,51 %** | **== live** |

Deux lectures que ce tableau donne d'un coup :

* en `far`, **la correction ne change rien** — non-régression garantie par construction, pas par
  espoir ;
* en `near`, le raccourci rend **exactement** ce que le live rendait en `far`. La fenêtre a
  glissé d'un tirage : ce n'est pas un facteur, c'est un **décalage**, et il vaut `|pool|`.

L'écart n'est « que » +0,51 % ici, mais son signe et sa magnitude suivent la seed et le cardinal
(#277 : +0,51 / +1,25 / +3,13 / −0,07 %) — d'où le refus de tout correctif multiplicatif.

## 5. Le cliquet

`--step classify` rend **exit 1** si un montage prend le raccourci avec un caster porteur d'une
famille inconditionnelle (aujourd'hui `HazeOfCorruption`), hors allowlist documentée. La liste des
familles n'est pas figée dans le probe : elle est **re-dérivée** du binaire (`--step natif`) et du
registre Python (`--step port`, qui lit l'attribut de classe `event_id`, pas un grep).

C'est le même gisement que `TARGETING_OPTIONS` / `ABILITY_ATTACK_TYPE` : **notre propre cadence
l'alimente**. Chaque nouveau montage qui prend le raccourci avec un blightlord le rouvre.

État : `GATE VERT`.

## 6. Validation

```
python probe_281_pre_unit_ability_shortcut.py --step natif --verbose
python probe_281_pre_unit_ability_shortcut.py --step port
python probe_281_pre_unit_ability_shortcut.py --step classify        # exit 1 = gate rouge
python probe_281_pre_unit_ability_shortcut.py --step mesure --regime near
python probe_281_pre_unit_ability_shortcut.py --step mesure --regime far
python -m pytest tests/engine/runner/test_flail_swing_live.py -q
python -m pytest tests/engine/runner/test_pre_unit_ability_fork_live.py \
                tests/engine/runner/test_haze_of_corruption_transfer_live.py -q
python probe_181_targeting_gaps.py
```

Résultats, **re-joués après le rebase sur `8aa49b93`** : `test_flail_swing_live.py` **4 passed**
(3 volets + le volet (4) de #283) ; garde du vecteur + transfert Haze **15 passed** ; `probe_181`
**94/94, 0 manquante** ; gate **VERT** ; les deux régimes de `--step mesure` reproduits à
l'identique.

Le rebase n'a pas été neutre, et c'est le cliquet qui l'a dit : #283 avait introduit deux
raccourcis volontaires que `--step classify` a fait rougir immédiatement. Sans lui, ils seraient
entrés dans l'inventaire comme des faux — ou pire, auraient été « corrigés ».

## 6bis. `#281-r1` — les 10 `A EXAMINER`, CONFRONTÉS. Et le critère de tri est faux.

`probe_281r1_confronte_examiner.py`. L'observable n'est pas une utilité ni un dégât : c'est le
**retour de `pre_unit_ability_triggers`** (le foyer d'émission du vecteur côté port), instrumenté
pendant que le montage réel est routé par `Runner.apply(ActiveAbilityMessage(...))`. Liste vide ⇒
le vecteur n'a rien déclenché ⇒ le raccourci était équivalent, **mesuré**. Second observable,
indépendant : empreinte d'état complète (PV / vie / position / effets de **chaque** entité) et
**compteur de tirages** des deux voies, sur deux copies fraîches du même état-avant et du même flux.

**Un témoin ouvre la mesure**, parce qu'une liste vide partout est aussi ce que rendrait une
instrumentation qui ne mord pas — l'accord en régime dégénéré ne prouve rien. Le témoin est
`deathBlightlord` en géométrie `near` (pool Haze non vide) :

| cas | famille | fires | tirages prod / raccourci | empreinte |
|---|---|---|---|---|
| **témoin** | HazeOfCorruption | **1** (`pool [79]`, bond `(77,79)`) | **7 / 6** | ≠ (`HazeOfCorruption_DamageTransfer` posé d'un seul côté, cible à 75567 vs 75494) |
| `sworn` (5 sites) | SwornProtector, cast `SupremeCommander` 1028 | **0** | 2 / 2 | = |
| `fury` (4 sites) | FuryFromTheDelve, cast `AugmentedAssault` 1221 | **0** | 8 / 8 | = |
| `anvil` (1 site) | AnvilShield, cast `Foehammer` 1097 | **1** | 2 / 2 | **≠** |

Le témoin reproduit exactement la signature de #277 : le décalage vaut `min(|pool|, 2)` = 1 tirage.

**9 des 10 sont confirmés inertes par la mesure.** Le dixième, `test_foehammer_live.py:50`,
**DIVERGE** — et pas du tout par la famille que la fiche examinait :

```
vecteur(ability_type=1097) -> 1 trigger : {'effect': 1035, 'owner': 85, 'removed': 1, 'event': 42}
production : ('AnvilShield_AdditionalBlock', 'AnvilShield_BlockChanceBelowHealthCap', 'TerminatorArmour_*')
raccourci  : ('AnvilShield_AdditionalBlock', 'TeleportStrike_TeleportingIn',            'TerminatorArmour_*')
```

Le gate `IsNormalAttack` d'AnvilShield est bien fermé — c'est
`TeleportStrikeTeleportingInRemoveOnPreUnitAbility` qui a fire. `spaceRockfist` deep-strike, donc
il porte `TeleportStrike_TeleportingIn` (effet 1035) au premier cast ; le natif le **retire** sur
`On(PreUnitAbility)`, le raccourci le **laisse posé**.

### Le trou est dans le CRITÈRE, pas dans la lecture d'un gate

`--step classify` attribue un call-site à une famille par le **porteur cité** (un `visualId` dans
les littéraux du montage). **Six des onze abonnés portés n'ont aucun porteur** : les cinq
`*TeleportingInRemoveOnPreUnitAbility` et `WireweaveNetCounterAttack` se déclenchent sur la présence
d'un **EFFET**, pas d'une unité. Aucun `visualId` ne peut les révéler — le tri leur est
structurellement aveugle, et c'est pourquoi ce montage était classé `A EXAMINER` avec la mauvaise
famille au lieu d'`A CORRIGER`.

Conséquence pratique : tout montage dont le caster **deep-strike** (Terminator) ou porte un filet
`WireweaveNet` est faux, quel que soit son `visualId`. → résidu `#281-r4`.

Le test `test_foehammer_live.py` reste **juste aujourd'hui** : il n'assert que le dégât (bit-exact),
`dead_heroes` et `Stunned`, dont aucun ne dépend de `TeleportingIn`. Ce n'est pas une raison de le
laisser — `TeleportingIn` rend l'unité **non ciblable**, donc son rejeu offline part d'un état que
le natif n'a plus. Le geste n'est pas fait ici : router ce montage change son étage after-hit et
demande sa propre validation.

## 7. Ce qui n'est PAS couvert
* **Les `INDÉTERMINÉ`** (13 après re-dérivation, 7 à l'écriture) — montages sans unité nommée.
  **`#281-r2` : la prémisse est MESURÉE, et le refus est posé.** « Aucun porteur cité » n'était pas
  une preuve, et ce n'en est effectivement pas une : `deathBlightlord`, **seul** porteur
  inconditionnel, **est** dans les 168 unités du seed BC partagé — et sept unités deep-strike y
  sont aussi (`spaceRockfist`, `blackTerminator`, `thousTerminator`, `worldTerminator`,
  `darkaTerminator`, 2 npc), ce qui étend le vice à `#281-r4`. Un roster tiré du seed peut donc
  tomber dessus.
  La réponse n'est pas de la prose : `probe_281_pre_unit_ability_shortcut.py::refus_du_raccourci`
  tranche **au runtime**, quand le caster est enfin connu, sur les deux critères que la mesure a
  établis (famille inconditionnelle **ou** effet retiré par le vecteur). Il est câblé sur le cas
  franc, `probe_61_ability_hits.py::_offline_cast`, qui accepte littéralement n'importe quel
  `--caster` : il rend désormais la RAISON au lieu d'un chiffre faux.
  Les 12 autres `INDÉTERMINÉ` ne sont **pas** câblés — ils tirent leur roster du seed BC, donc
  leur caster n'est pas un paramètre mais une donnée du montage ; les instrumenter un par un est un
  autre geste. Ce qui est acquis ici : le foyer de décision existe, il est re-dérivé (jamais
  recopié), et il mord dans les deux sens (vérifié sur `deathBlightlord`, sur
  `spaceRockfist + TeleportStrike_TeleportingIn`, et **négativement** sur `necroWarden` et sur
  `spaceRockfist` nu).
* **`MartialSuperiority` en position de cible** n'a **aucun** montage confronté. Le seul fichier
  qui cite `templChampion` près d'un raccourci (`test_ability_hits_channel_live.py`) le place
  comme ennemi d'un cast **ranged** ; la riposte exige `IsMeleeAttack` (prédicat POSITIONNEL :
  caster adjacent). Une géométrie adjacente n'a pas été montée — le symptôme attendu serait une
  **riposte manquante** (2 coups Power sur le caster), bien plus franc qu'un décalage RNG.
* **Le volet (2) `native_factory`** de `test_flail_swing_live.py` reste sur
  `AttackDamageOperation.execute_ability_attack` : c'est un A/B d'étage de dégât, pas un point
  d'entrée de cast — il n'a jamais eu ce défaut.
* **Le régime CRIT** : les mesures sont à `--crit 0,0`. Un crit change le nombre de tirages **par
  coup**, pas le tirage amont ; le décalage devrait être identique, ce n'est pas mesuré.
* **`|pool| > 2`** : la consommation est exacte à tout cardinal (`min(k, 2)`) mais **qui** est
  piqué dépend de l'ordre source — résidu #215, inchangé.
* **Les 113 citations `0x2b`** — migration non faite (§0). → backlog `#281-r3`.
