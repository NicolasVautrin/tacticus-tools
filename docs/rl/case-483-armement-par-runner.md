# #483 — Les seaux étaient par runner, la PORTE ne l'était pas

**Verdict : bug de harnais FERMÉ côté code, ÉCRIT-MAIS-NON-CONFRONTÉ côté live** (le
correctif vit dans `frida/hooks/*` : il n'est vivant qu'après une fenêtre de reinjection,
qui est un geste d'orchestrateur).

## 1. Le défaut

Six features de `frida/hooks/features/` capturent **par runner** — `OriginBuffers` +
`getTraceOrigin()`, chaque event tagué `originRunnerId` — et leurs RPC `*Dump`/`*Clear`
filtrent bien par `runnerId`. Mais leur **porte d'armement** était un booléen de MODULE,
session-global : `trace.on`, `trace.enabled`, `audit.enabled`, `state.enabled`.

| feature | porte (avant) | RPC d'armement |
|---|---|---|
| `scorer-damage-trace.ts` | `trace.on` | `scorerDamageTraceOn` / `Off` |
| `triggered-move-trace.ts` | `trace.on` | `triggeredMoveTraceOn` / `Off` |
| `effect-bonus-trace.ts` | `trace.on` (+ budget global) | `effectBonusTraceOn` / `Off` |
| `hit-trace.ts` | `state.enabled` + détach physique | `hitTraceArm` / `Disarm` / `SetEnabled` |
| `ai-utility-trace.ts` | `trace.enabled`, `diagSampler.enabled` | `aiUtilityTraceEnable` / `Disable` (+ `DiagSampler*`) |
| `bucket-audit.ts` | **aucune garde** — armement purement physique | `bucketAuditEnable` / `Disable` |

**Le mode de panne est ASYMÉTRIQUE, et c'est lui qu'il fallait fermer.** Les probes
appellent leur `*Off` dans un `finally`, donc il s'exécute **toujours** : en régime
4-en-parallèle — le régime normal — le premier probe qui finit désarme la capture des
autres. La victime dumpe alors un seau **TRONQUÉ, sans aucune erreur** : un vert qui ment,
exactement la classe « un échec rendu se lit comme une mesure ». Le sens inverse (un `On`
de trop) ne corrompt **aucune** donnée, puisque les seaux sont déjà par runner : il ne
coûte que de la perf.

Le correctif ne rend donc pas l'armement « exact ». Il rend le **désarmement incapable de
traverser la frontière d'un autre acteur**.

## 2. Le foyer — `frida/hooks/game/armed-runners.ts`

Un seul module, six familles (sept `TraceKind` avec le diag sampler), pas six rustines.

- `arm(kind)` sans `runnerId` = **GLOBAL** (comportement historique) ;
  `arm(kind, rid)` = **NOMINATIF**.
- `disarm(kind)` sans `runnerId` = désarme le **GLOBAL SEULEMENT** ; les armements
  nominatifs survivent. **C'est l'invariant central.**
- `capturing(kind)` = la garde : consulte `getTraceOrigin()` contre l'ensemble armé.
- `armedReport(kind, rid?)` = ce que publient les `*Dump` : `on` (« ouverte **pour
  l'origine interrogée** »), `armedGlobal`, `armedRunners`.
- `onDisarmed(kind, cb)` = détachement **différé** au moment où plus personne n'est armé
  (`hit-trace`, `bucket-audit`, dont l'armement est physique).
- `purgeArmedForRunner(rid)` — appelé par `runner-registry.disposeRunner`, même hygiène
  que `purgeTracesForRunner`. Sans lui, un runner mort laisserait `anyArmed()` vrai pour
  toujours et les `Interceptor` ne se détacheraient jamais.

**Compatibilité ascendante par construction** : un appelant non migré arme et désarme le
global, comme avant. Le défaut disparaît dès que l'appelant passe son `runnerId`.

### Le coût sur chemin chaud

`capturing()` est appelé depuis des callbacks qui firent **aussi** pendant l'IA du jeu
live (`IdunBattle.Core.Services.ProbableDamageEvent$$.ctor`). Il est écrit pour que le cas
dominant — rien d'armé — coûte **deux lectures de champ** : le `Set` vide court-circuite
**avant** même d'appeler `getTraceOrigin()` (qui est `return current;`). Quand quelque
chose est armé s'y ajoutent une lecture de variable de module et un `Set.has`.

### Ce que le port ne change PAS, délibérément

Les ~20 gardes `if (!trace.on) return;` de `scorer-damage-trace.ts` **n'ont pas bougé d'un
caractère** : `trace.on` est devenu un **accesseur**. Un remplacement d'un token par site
plutôt qu'une réécriture — c'est ce qui rend le diff relisible et évite d'introduire une
faute dans 20 gardes pour en corriger une.

## 3. Deux pièges rencontrés, tous deux dans le CORRECTIF lui-même

**Le budget d'`effect-bonus-trace` rouvrait le même défaut par une autre porte.** Il était
global : deux acteurs en parallèle partageaient un compteur, et l'épuisement de l'un
**éteignait la capture de l'autre**. Il est devenu **par origine** (`spentByOrigin`), même
raison que le CAP par bucket d'`OriginBuffers`. Son extinction passe par `extinguish(kind,
origine)`, dont la post-condition est « `capturingFor(origine)` est faux » — sans quoi le
test se rejouerait à chaque event (extinction stérile).

**`bucket-audit` n'avait AUCUNE garde de capture** : son armement était *purement*
physique, donc `bucketAuditDisable` arrachait les `Interceptor` de tout le monde. Deux
crans posés : une garde `capturing()` avant chaque `push` (les compteurs `diag.*Fires`
restent **hors** garde — ils diagnostiquent l'installation, cf. #475 où `enabled: true` +
0 fire était le symptôme) et le détachement différé.

## 4. Le cliquet offline — `scripts/python/probe_483_armement_par_runner.py`

**Périmètre DÉRIVÉ**, jamais listé : tout fichier de `frida/hooks/features/` portant
`new OriginBuffers<`. Une liste blanche des six ne pourrait pas montrer la **septième**.
Le périmètre s'**assertionne non vide** ; tri-état (`rc 3` = NON MESURÉ) si le périmètre,
les RPC ou les sites d'appel sont introuvables.

| étage | ce qu'il garde |
|---|---|
| E1 | la feature **importe et appelle** `capturing` — sans quoi la porte ne peut structurellement pas distinguer deux acteurs |
| E2 | **aucune porte RÉASSIGNÉE** (`x.on = `, `x.enabled = `) — l'étage qui MORD, ce sont les 15 sites du défaut |
| E3 | tout RPC d'armement (suffixe dérivé `On/Off/Arm/Disarm/Enable/Disable/SetEnabled`) **déclare** un `runnerId` |
| E4 | tout site Python le **passe** — ou porte le marqueur `ARMEMENT GLOBAL ASSUME` |

**Contre-épreuve** (`git archive 5457d00f` + rejeu) : **71 écarts** sur l'état d'avant =
**6** (E1) + **15** (E2) + **15** (E3) + **35** (E4). Sur l'état d'après : **VERT**, et les
**cinq** mutations mordent (E1 import retiré ; E2 forme directe **et** forme castée ;
E3 signature amputée ; E4 site Python sans `runnerId`).

### Deux FAUX VERTS trouvés en écrivant le cliquet

Ils valent d'être notés : ils sont la raison d'être des mutants.

1. **E4 lisait une fenêtre de 3 LIGNES.** Dans `probe_462r4ar1`, la ligne qui suit un
   `effectBonusTraceOff {}` est `capture["runnerId"] = rid` : le mot `runnerId` était dans
   la fenêtre **sans être un argument de l'appel**. Une fenêtre par lignes ne peut pas
   distinguer les deux ; seul l'**appariement des parenthèses** le peut. Le site apparaît
   dès que le découpage devient exact.
2. **E1 cherchait la sous-chaîne `game/armed-runners`**, qui apparaît **aussi en prose**
   dans les six features (« Cf. game/armed-runners.ts ») : le mutant « import retiré »
   passait au vert. Remplacé par le motif d'**import**. Et **E2** n'attrapait que
   `\w+\.on = ` : la forme `(trace as {...}).on = false` — celle qu'écrirait quelqu'un qui
   contourne le `readonly` — passait. Le mutant joue désormais **les deux formes**.

## 5. Les sites d'appel Python

**16 fichiers, 33 sites** convertis : le `rid` était déjà sous la main (ils le passaient au
`*Clear` de la ligne suivante).

**Deux sites restent GLOBAUX et le DISENT** au lieu de le masquer — `probe_437r1.channel()`
et `probe_462r4ar1 --wide` arment **avant que le runner existe**, le `rid` n'y est pas
disponible. Ils restent éteignables par un `Off {}` voisin, mais ne peuvent plus, eux,
éteindre une capture nominative. Marqueur `ARMEMENT GLOBAL ASSUME`, échappatoire consciente
que E4 reconnaît.

⚠ **Un désarmement doit porter le MÊME scope que son armement.** Un `Off {runnerId}` sur un
armement global ne désarme rien — et laisse le global ouvert pour la session entière. C'est
pourquoi les `Off` appariés à ces deux armements globaux restent globaux, marqueur à
l'appui.

⚠ `probe_443r1a` : `rid = None` posé **avant** le `try`. Son `finally` désarme désormais
avec le `rid`, qui doit exister même si le build a levé — sinon `NameError`, avalé par le
`except`, donc désarmement **muet**.

## 6. Ce qui reste OUVERT

- **L'isolation LIVE n'est pas confrontée.** Le probe est écrit
  (`probe_483_isolation_armement_live.py`) : témoin de non-vacuité (A armé **seul** doit
  capter, sinon tout le reste serait un accord en régime dégénéré), puis I1
  (`Off {runnerId: B}` = le `finally` du voisin), I2 (`Off {}` global = l'appelant non
  migré — l'étape qui sépare le plus nettement l'avant de l'après) et F (la porte se
  **ferme** sur `Off {runnerId: A}` ; sans F, « toujours ouvert » satisferait I1 et I2).
  Tri-état **vérifié contre la session courante** : `rc=3` NON MESURÉ, raison nommée
  (`unable to find method traceArmedStatus` ⇒ bundle antérieur), **aucun runner monté**.
- **`frida/host/router.ts` n'est pas touché.** Ses six endpoints
  (`/api/ai-utility-trace/{enable,disable}`, `bucket-audit`, diag sampler) appellent leurs
  RPC sans argument ⇒ armement/désarmement GLOBAL, exactement comme avant. Les toucher
  imposerait un **restart host** en plus de la fenêtre de reinject, pour un gain nul sur le
  défaut mesuré (qui porte sur les probes). Résidu assumé.
- **Le régime GLOBAL reste disputé** : deux acteurs qui arment tous deux en global peuvent
  encore s'éteindre mutuellement. C'est la dette que E4 rend **visible** (marqueur
  obligatoire) plutôt qu'invisible.
