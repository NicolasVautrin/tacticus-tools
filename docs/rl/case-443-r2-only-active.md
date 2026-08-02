# case-443-r2 — `onlyActive` : le paramètre EST discriminable, et il coûte 35 points

Résidu ouvert par #443 : « basculer `onlyActive` ne déplace RIEN dans le montage retenu »
(contre-épreuve `CE3`, muette). Le brief posait explicitement les deux hypothèses concurrentes —
« le paramètre est mort » contre « le montage n'atteint pas le régime ». **C'est la seconde qui est
vraie**, et la discriminer a fait tomber un écart de port mesuré à **35 points d'utilité de paire**.

## 1. Le critère, avant la méthode — et il se lit au décompilé

`IdunBattle.Entities.EntityExtensions$$HasEffect(entity, state, requestedEffectType, onlyActive)` =
`IsOwnerOfEffect(...) || IsTargetOfEffect(...)`, relu VERBATIM sur `rnca9r7q6c` :

* `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` boucle sur les effets PORTÉS.
  `if ((char)onlyActive == 0)` ⇒ **aucune lecture** de `EffectComponent.IsActive @+0x5c` ; sinon
  `if (comp[0x5c] == 0) continue` **avant** la comparaison `comp[0x58] == requestedEffectType`.
  Le call-site `null` (`Nullable<bool>` vide) présente le même octet bas que `false` : les trois
  littéraux `0` / `false` / `null` prennent la **même** branche.
* `IdunBattle.Entities.EntityExtensions$$IsTargetOfEffect` balaie toutes les entités-effet du state
  et exige `comp[0x58] == type && comp[0x5c] != 0` **inconditionnellement** — cette branche est déjà
  active-only dans les deux régimes, `onlyActive` ne la traverse pas.

⇒ **`HasEffect(e, T, 0)` et `HasEffect(e, T, 1)` divergent SSI `e` PORTE un effet de type `T` dont
`IsActive` est FAUX.** Question binaire du brief : un tel état existe-t-il, avec un porteur qui
l'atteint ? **OUI**, et il s'atteint en un `endturn`.

## 2. L'inventaire — DÉRIVÉ, pas saisi

`scripts/python/probe_443r2_only_active_callsites.py` (offline, **7,5 s**, dans la banque). Il part
du **code exécutable** (AST) et non d'une liste : un call-site PORTÉ est un appel de substrat auquel
s'attache une **citation** de nœud natif portant un littéral `onlyActive`.

Le filtre qui rend la dérivation possible : la citation doit porter un **token de nœud natif**
(`HasEffect`, `IsOwnerOfEffect`, …) dans son contexte immédiat. Il écarte mécaniquement les mentions
de **contraste** — « `onlyActive: true` ne verrait pas le marqueur qu'on vient de poser ; le natif a
mis `false` » (`hateful_assault`), « … sert les call-sites `onlyActive = 0` (le voisin) »
(`savior_protocols`) — qui parlent d'un AUTRE call-site et empoisonneraient l'attribution.

Mesure du 2026-08-02 (à **re-dériver**, jamais citer) : **168** lectures d'effet sous `engine/`,
dont **11 PORTÉES** — 7 PRÉSENCE (`0`/`false`/`null`), 2 ACTIVITÉ (`1`/`true`), 2 INLINE.
**Conformité substrat ↔ littéral : 0 écart.**

Le probe joint ensuite chaque call-site aux **vecteurs d'inactivité PORTÉS** (17 classes
surchargeant `is_active` = `CreateActiveCondition` ; 6 sites écrivant le flag). Verdict :

| atteignabilité | n | ce que ça veut dire |
|---|---|---|
| **FLAG** | **2** | un vecteur porté écrit `IsActive` à faux : régime atteignable EN JEU |
| CONDITION | 0 | l'effectType a une condition portée, recalculée à la lecture |
| SEED | 6 | ni l'un ni l'autre côté port : reste le canal `includeInactive` |
| FOYER / INDÉTERMINÉ | 3 | l'effectType vient de l'appelant, ou n'est pas résolvable |

**Les DEUX call-sites FLAG portent le MÊME effectType — `Overwatch_AutoAttack` (1009) — avec des
littéraux OPPOSÉS** :

```
playbook/suppressive_fire.py::_target_has_overwatch      onlyActive: null -> substrat PRESENCE
triggers/loki/reactivate_overwatch.py::matches           onlyActive: true -> substrat ACTIVITE
```

C'est la dérivation qui a désigné le montage ; elle n'a pas été choisie.

## 3. Le régime PRÉSENT-mais-INACTIF tient dans un `endturn`

`IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal` rend trois
`Triggered()` qui pilotent le flag de l'instance 1009. Le deuxième est
`On(TurnStart_EffectActivation = 0x12) & IsTurnOf(owner@0x148) -> DeactivateEffect` : **pendant le
tour de son porteur, l'overwatch est présent et inerte.**

État MESURÉ aux DEUX canaux de `readEffectsByUnit` (jamais supposé) :

```
tour du CASTER    decisionView defaut [True]   includeInactive [True]     -> 1009 ACTIF
tour du PORTEUR   decisionView defaut []       includeInactive [False]    -> 1009 INERTE
```

Le canal par défaut **DROPPE** l'instance inerte : c'est ce qui rend le régime intéressant, et c'est
ce qui a fait tomber l'écart du §5.

`pairUtility` **accepte un caster hors de son tour** (mesuré : `ok: true`, `posSrc: tile(c,r)`) —
aucun cast, aucun kill n'est nécessaire, un `endturn` suffit.

## 4. La mesure qui DISCRIMINE

`scripts/python/probe_443r2_only_active_overwatch.py`. Porteurs NATURELS, voie directe :
`emperNoiseMarine` (trait `SuppressiveFire` 1010 → triggered 1044) contre `eldarRanger` (trait
`Overwatch` → 1009 sur elle-même), distance 3 (le prédicat natif est NIÉ : au contact le terme
n'entre pas).

```
board MC1_67 / seed 41504                         board C4_09 / seed 777
A  1009 ACTIF    natif 40.043221                  A  natif 42.563165
   port[defaut]          40.043221  terme 35         port[defaut]          42.563165  terme 35
   port[includeInactive] 40.043221  terme 35         port[includeInactive] 42.563165  terme 35
   mutation du substrat : deplacement +0.000000      mutation : +0.000000
B  1009 INERTE   natif 40.043221                  B  natif 42.563165
   port[defaut]           5.043221  terme  0         port[defaut]           7.563165  terme  0
   port[includeInactive]  40.043221 terme 35         port[includeInactive] 42.563165  terme 35
   mutation du substrat : deplacement -35.000000     mutation : -35.000000
```

Deux couples (board, seed) aux bases DIFFÉRENTES (40,04 contre 42,56) : c'est bien un autre état,
pas un rejeu.

**Trois faits, dans cet ordre** :

1. **`onlyActive` faux est CONFIRMÉ PAR MESURE, pas seulement lu** : le natif verse le même terme
   sur un overwatch armé et sur un overwatch inerte. Le littéral du décompilé et le comportement
   observable concordent.
2. **La contre-épreuve MORD** : basculer le substrat de `has_effect` vers `active_effects` (= ce que
   le port ferait si le littéral valait `1`) fait perdre **exactement le poids BC**, et **rien** en
   régime actif. Critère = déplacement par rapport au port NON MUTÉ, jamais l'écart au natif.
   `CE3` de #443 était muette parce que son montage n'avait que le régime ACTIF, où les deux
   substrats **coïncident** — le §2bis du test garde désormais ce contre-cas.
3. **Le résidu #443-r2 est CLOS** : le paramètre n'est pas mort, il est *load-bearing*.

## 5. Ce que la discrimination a fait tomber — résidu `#443-r2-b1` (BUG, mesuré) — **FERMÉ**

> **FERMÉ le 2026-08-02** : la face DÉCISION prend désormais la MÊME porte
> (`decision_view_seed_body`), et ce que le canal ajoute n'atteint que le substrat STRUCTURÉ.
> Gain confirmé à une autre échelle que celle qui l'avait ouvert : **une décision de CIBLE passe de
> MISS à MATCH** sur une marche d'agreement (`C4_09`/777, `ability` 9/13 → 10/13), déplacement
> intégralement dans la feuille TRIGGERED et égal à `35.000000`. Détail, contre-épreuves et résidus :
> **`docs/rl/case-443-r2-b1-canal-decision.md`**. Ce qui suit décrit l'état AVANT la fermeture, et
> reste vrai comme diagnostic.

**La face DÉCISION seede son `EffectsState` depuis le canal `decisionView` PAR DÉFAUT** — donc elle
ne voit AUCUN effet inerte, là où le natif en voit. Écart mesuré : **−35 points d'utilité de paire**
sur le régime B, sur les deux couples.

Le foyer est `engine/playbook/scene.py::step_context(predictor, dv)` : il seede `EffectsState` depuis
le `dv` que son appelant lui donne, et tous les appelants passent le canal nu. La face COMBAT, elle,
a sa porte NOMMÉE depuis #219 (`runner/snapshot.py::decision_view_seed_body`, `includeInactive:
true`) — l'asymétrie est là.

**Remède identifié** : donner à la face DÉCISION le même canal. **Rayon de souffle MESURÉ** (3v3,
`MC1_67`, régime B) : **+2 entrées d'effet sur 11 → 13**, **1 unité touchée**, types
`Overwatch_AutoAttack` (1009) et `WireweaveNet_CounterAttack` (1111). Un effet ajouté n'entre dans
AUCUN nombre passant par `active_effects` (il y est filtré par le flag) : seuls les lecteurs
`has_effect` le voient — c'est-à-dire **exactement les mirrors d'un `onlyActive` FAUX, qui DOIVENT
le voir**.

**NON FAIT ICI, et volontairement** : la bascule touche tous les lecteurs `has_effect` de la face
décision (`scene._camo_cloak_cover_keys`, `scene.carries`,
`scene._seed_condition_gated_owner_effects` — dont le gate « déjà présent » interagit avec le
rattrapage `factory.ABILITY_INIT_OWNER_EFFECTS` —, `ai/action_generators._heal_candidates`,
`ai/state_bridge._is_untargetable`, `playbook/prediction/_shared`, `doctrina_imperatives`,
`loki_custom.any_enemy_has_markerlight`). C'est une tranche avec sa propre validation d'agreement,
pas un « pendant que j'y suis ». Le test de garde verrouille le **mécanisme** en attendant :
l'écart du canal par défaut vaut `0` **ou EXACTEMENT le poids**, jamais une troisième valeur — donc
il reste vrai le jour où le canal bascule.

## 6. Le second call-site — NON CONFRONTÉ live, sensibilité GARDÉE offline

`triggers/loki/reactivate_overwatch.py::EarlyWarningOverrideHitReductionPurge.matches` porte le
littéral OPPOSÉ sur le même effectType :

```
( On(0 = UnitDeath) | On(0x11 = PostDamageTaken) )
  & NOT HasEffect(Owner@0x148, 0x3f1, onlyActive=1, targetType=6=Both)
-> RemoveEffect(Owner@0x148, Nullable(GetHitReductionEffectType()))
```

**Sensibilité au flag : MESURÉE, offline et sans runner** — même état, au seul `IsActive` de
l'instance 1009 près, verdicts **opposés** (`{actif: False, inerte: True}`). Un port qui aurait lu
`has_effect` ici serait insensible, et muet. C'est le test
`test_le_call_site_onlyActive_VRAI_est_sensible_au_flag`.

**NON CONFRONTÉ au natif**, montage tenté et verrous :

* **Montage requis** : `tauCrisis` (Re'vas) caste `EarlyWarningOverride` (1077, pose 1145) ; elle
  TUE en overwatch pendant un tour adverse — `LegitDeathReasons` exige une `DamageSource` d'ability
  `1009` **ou** `1148 CyclicIonBlaster_AdditionalHits` — ce qui pose `1146` **et** RÉACTIVE 1009 ;
  puis 1009 doit REDEVENIR inerte (un second tir d'overwatch qui ne tue pas, ou le début du tour de
  Re'vas) **sans que 1146 ait expiré** (sa durée est `TurnsUntilUnitOwnerTurn`) ; puis une mort
  quelconque doit survenir pour émettre `On(UnitDeath)`.
* **Verrou 1 — pas d'oracle** : `matches` d'un effet-trigger n'a aucun pendant natif interrogeable
  (il n'existe pas de `pairUtility` du côté COMBAT). La confrontation passerait par l'OBSERVATION du
  retrait de 1146 (`decisionView`) et de l'`EXTRA_HITS` du tir suivant — faisable, mais c'est un
  montage à trois morts contrôlées, soit une tranche entière.
* **Verrou 2 — moitié du vecteur absente** : le port n'émet pas `On(PostDamageTaken = 0x11)` (site
  d'émission natif non localisé, cf. l'en-tête du module). La classe l'écoute pour rester fidèle ;
  elle ne fire aujourd'hui que sur `On(UnitDeath)`.

Ce n'est **ni** « non pertinent » **ni** un zéro non qualifié : le régime est atteignable, le port y
est sensible, seul l'oracle manque.

## 7. Résidus nommés

* ~~**`#443-r2-b1`**~~ — la face DÉCISION est aveugle aux effets INERTES (canal de seed par défaut).
  **BUG mesuré à −35**. **FERMÉ le 2026-08-02** — `docs/rl/case-443-r2-b1-canal-decision.md`.
  Trois résidus en sont nés (`-r1` lecteurs de la liste brute en présence native, `-r2` slot 0x13 de
  `CanUseAbility` non résolu, `-r3` rallumage de `1014` en simulation).
* **`#443-r2-c1`** — la conformité n'est gardée que là où une citation est ATTACHABLE. Les **157**
  lectures d'effet NON DÉCLARÉES (aucun nœud `HasEffect` cité en portée) sont inventoriées, jamais
  rouges : un mirror écrit sans citer son littéral échappe à l'étape de conformité.
* **`#443-r2-c2`** — les substrats **INLINE** (`by_unit` relu à la main : `harlequins_panoply`,
  `necrons`) sont recensés, jamais confrontés. Ce n'est pas un formalisme : mesuré,
  `master_of_the_tutelaries._master_effect_is_carried_and_active` déclare `onlyActive=0` **et** lit
  `any(e.active …)` — son gate mirroire le couplage `DeactivateEffect → UpdateEffectTargets(vide) →
  Revert → RemoveTriggeredAbility` (#231), pas le 4ᵉ argument. Un verdict mécanique le rougirait à
  tort.
* **`#443-r2-c3`** — l'attribution d'un effectType à un vecteur de flag retombe au **FICHIER** quand
  la portée ne le fixe pas (l'écriture est souvent déportée d'un cran :
  `_set_ranged_auto_attack_active` écrit `e.active`, c'est `_ranged_auto_attack_instances` qui nomme
  le type). Assumé : une attribution trop large **élargit** l'atteignabilité, elle n'en cache aucune.

## 8. Fichiers

* Inventaire + cliquet : `scripts/python/probe_443r2_only_active_callsites.py` (offline, 7,5 s).
* Mesure : `scripts/python/probe_443r2_only_active_overwatch.py`
  (`--board`/`--seed`/`--blast`/`--roster`).
* Garde : `scripts/python/tests/engine/test_443r2_only_active_overwatch_live.py` (6 tests, ~11 s).
  Contre-épreuve JOUÉE : substrat `has_effect` → `active_effects` dans `battle_query.scene_has_effect`
  ⇒ **3 tests rouges sur 6** ; restauration vérifiée (`git diff` vide) et re-jeu **6/6 verts**.
