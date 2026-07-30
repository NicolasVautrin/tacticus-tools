# case-279 — Le décodeur de prédiction résout ses champs PAR NOM, et on sait où cette voie s'arrête

Question posée, binaire : **le décodeur converti rend-il les MÊMES valeurs qu'à offsets figés, sur
le build courant `rnca9r7q6c` ?**

Réponse en deux morceaux, et il faut les tenir séparés :

* **Sur les OFFSETS : oui, à l'identique — 24 sur 24, zéro écart.** La disposition résolue par nom
  dans les métadonnées IL2CPP reproduit exactement les 20 offsets + 4 tailles que
  `frida/hooks/game/damage-prediction.ts` figeait. Mesuré, pas supposé.
* **Sur les VALEURS ÉMISES par le bundle injecté : NON CONFRONTÉ.** Le fix vit dans
  `frida/hooks/**` ; il n'entre en vigueur qu'après `build:hooks` **+ réinjection**, geste interdit
  tant qu'une session Frida est partagée. Le code est écrit, il compile, sa résolution est
  éprouvée hors process — il n'a jamais tourné dans le jeu.

## 1. Ce que la conversion change réellement

Le décodeur de #276 était juste. Son défaut n'était pas la valeur, c'était la **nature** de ses
offsets : des littéraux, vrais pour un build et faux au suivant, **silencieusement**. C'est la
signature complète de #268 — `aiPredict` rendait `[1,100]` pour un coup à 2375, `mightCrit` valait
25 sur un `bool`, et les tests SKIPPAIENT en accusant leur propre montage.

Le verrou qui interdisait la conversion était supposé, pas réel. `getFieldOffset`
(`frida/hooks/il2cpp/helpers.ts`) résolvait **déjà** par nom au runtime, via `class_get_fields` :
les noms de champs sont dans les métadonnées IL2CPP, **en process**, pas dans un fichier de dump
qu'un worktree n'aurait pas. Ce qui manquait était de savoir **quels noms demander** — comblé par
le RPC `classFields(ns, cls)` (`frida/hooks/features/mode-source-capture.ts`), qui rend nom, offset
et type de chaque champ, la chaîne d'héritage, la taille boxée et la taille des champs déjà
corrigée du header `0x10`.

## 2. La mesure : 24 chemins nommés, disposition live vs littéraux figés

`POST /api/scripts/2/rpc {"method":"classFields", "args":[ns, cls]}`, build `rnca9r7q6c`,
session 2, 2026-07-30. Offsets de CHAMPS (le RPC les rend boxés ; header `0x10` retranché).

| chemin nommé | figé (avant #279) | live | verdict |
|---|---|---|---|
| `DamagePredictionResult.CurrentHealth` | `0x00` | `0x00` | OK |
| `DamagePredictionResult.CurrentShield` | `0x04` | `0x04` | OK |
| `DamagePredictionResult.DefaultScenario.Probability` | `0x10` | `0x10` | OK |
| `DamagePredictionResult.DefaultScenario.Damage.HealthDamage` | `0x14` | `0x14` | OK |
| `DamagePredictionResult.DefaultScenario.Damage.ShieldDamage` | `0x24` | `0x24` | OK |
| `DamagePredictionResult.BlockScenarios` | `0x38` | `0x38` | OK |
| `DamagePredictionResult.AccurateHealthDamage` | `0x40` | `0x40` | OK |
| `DamagePredictionResult.AccurateShieldDamage` | `0x50` | `0x50` | OK |
| `DamagePredictionResult.TotalDamage` | `0x60` | `0x60` | OK |
| `DamagePredictionResult.IndividualHitDamage` | `0x80` | `0x80` | OK |
| `DamagePredictionResult.LimitedByMinHp` | `0x88` | `0x88` | OK |
| `DamagePredictionResult.MightCrit` | `0x8a` | `0x8a` | OK |
| `DamagePredictionResult.ForceOverkill` | `0x8b` | `0x8b` | OK |
| `DamagePredictionResult.PreventOverkill` | `0x8c` | `0x8c` | OK |
| `DamagePredictionResult.AppliedHits` | `0x98` | `0x98` | OK |
| `MinMaxDamage.Min` / `.Max` | `0x08` / `0x0c` | `0x08` / `0x0c` | OK |
| `ProbableDamageEvent.DamagePrediction` | `0x08` | `0x08` | OK |
| `ProbableDamageEvent.Probability` / `.Weight` | `0xa8` / `0xb0` | `0xa8` / `0xb0` | OK |
| `DamagePredictionResult` fieldsSize | `0xa0` | `0xa0` | OK |
| `ProbableDamageEvent` fieldsSize | `0xb8` | `0xb8` | OK |
| `ProbableHealEvent` / `ProbableEffectEvent` fieldsSize | `0x18` | `0x18` | OK |

**`ECARTS fige/live : 0 sur 24`.** Le fichier ne mentait pas sur le build courant — c'est un
résultat en soi : il ferme l'hypothèse « #276 a laissé un offset faux ».

### 2bis. Ce que la liste EXHAUSTIVE des champs a tranché, et que la XREF ne pouvait pas

`classFields` rend les **18 champs** d'instance de `DamagePredictionResult`. Une liste exhaustive
prouve des ABSENCES, ce qu'une XREF ne fait jamais :

* **`CurrentArmor` n'existe pas.** #276 écrivait « aucun lecteur identifié » — une absence de
  preuve. C'est désormais une preuve d'absence : aucun des 18 champs ne porte ce nom.
  `armorBefore = null` était le bon choix, il est maintenant fondé.
* Les trois « non identifiés » de #276 ont un nom : `0x08` = **`DamageProfile`** (référence, 8 o),
  `0x70` = **`Modifiers`** (`List\`1`), `0x78` = **`DeniedDamage`** (`Int32`), et le `bool` de
  `0x89` que `get_WillBeKill` teste sans le nommer = **`CannotBeGuaranteedKilled`**.
* Le `0x9c` listé « dernier mot non identifié » **n'est aucun champ** : c'est du padding
  d'alignement entre `AppliedHits@0x98` et la fin du struct à `0xA0`.
* Les noms de CHAMPS ne sont pas ceux des accesseurs : le champ s'appelle `DefaultScenario`
  (l'accesseur est `DamagePredictionResult$$get_DefaultBlockScenario`), et les deux `MinMaxDamage`
  agrégés s'appellent `AccurateHealthDamage` / `AccurateShieldDamage`.
* **Correction d'un commentaire faux** : `ProbableHealEvent.HealPrediction@0x08` est un
  `HealPredictionResult` **INLINE** — un ValueType de 8 octets (`CurrentHealth@0x00`,
  `TotalHeal@0x04`) — et **pas un pointeur**, comme l'écrivait l'en-tête de
  `damage-prediction.ts`. `Probability` étant à `0x10`, il ne reste que 8 octets pour la charge
  utile, et `classFields` donne `boxedSize` 24 / `fieldsSize` 8 pour ce type.
  `frida/hooks/features/ai-step/playbook-predict.ts` décodait déjà correctement (deux `int`) : la
  doc était seule à se tromper, et personne ne pouvait le voir.

## 3. La garde inversée : la dérive devient une information, plus une panne

Avant #279, la garde de layout confrontait la **taille de classe live** à une taille RE figée. Elle
disait « le build a changé, ce décodeur est périmé » — et elle avait raison, parce qu'un champ
déplacé cassait effectivement la lecture.

Elle ne peut plus dire ça : le décodeur SUIT le déplacement. La garde change donc de question :

* `predictionLayoutError()` — non nul seulement si un **chemin NOMMÉ n'existe plus**. C'est le seul
  cas qui invalide une mesure, et il signifie « le struct a été RENOMMÉ », pas « déplacé ».
* `predictionLayoutDrift()` — **nouveau, non bloquant** : liste les offsets qui s'écartent de la
  table RE `rnca9r7q6c`. Non nul = la documentation en tête du fichier est à refaire ; le décodeur,
  lui, reste juste. Cette information ne disqualifie **aucune** mesure et ne doit pas remonter dans
  `predictionLayoutError` (que `conftest.py` lit pour déclarer « CANAL MORT »).

Une hypothèse tacite de l'ancien code est au passage devenue une **vérification** :
`SMALL_EVENT_STRIDE` était partagé entre `ProbableHealEvent` et `ProbableEffectEvent` parce qu'ils
faisaient la même taille. Les deux tailles sont désormais résolues séparément et leur **égalité est
contrôlée** ; un désaccord lève au lieu de rendre un stride unique arbitraire.

## 4. La borne de la voie — mesurée

**`class_get_fields` NE DESCEND PAS dans un ValueType imbriqué.** C'était le point à trancher.
Mesuré : `DamagePredictionResult` rend 18 champs, `DefaultScenario` y figure comme **UN** champ de
type `DamagePredictionScenario`, et ni `Probability` ni `Damage` n'y apparaissent. Il faut
interroger `DamagePredictionScenario` (2 champs), puis `DamagePredictionDamage` (2 champs), puis
`MinMaxDamage` (3 champs).

**Ce n'est pas un mur.** La classe du sous-type se déduit du champ lui-même
(`il2cpp_field_get_type` → `il2cpp_type_get_class_or_element_class`), donc la chaîne se compose
sans jamais nommer une classe intermédiaire : `resolveFieldPath` descend
`DefaultScenario` → `Damage` → `HealthDamage` → `Min` et rend `0x10 + 0x04 + 0x00 + 0x08 = 0x1c`,
exactement l'offset que lit `IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill`. Le
coût est un aller-retour de métadonnées par maillon, payé une seule fois au chargement du module.

Là où la voie s'arrête vraiment, quatre points :

1. **Le header `0x10` n'est pas dans les noms.** `il2cpp_field_get_offset` rend un offset BOXÉ pour
   un ValueType ; savoir qu'il faut le retrancher est une connaissance de FORME, extérieure aux
   noms. D'où l'ajout de `class_is_valuetype` dans `helpers.ts` et le refus de composer un maillon
   qui n'en est pas un — un champ de type référence devrait être DÉRÉFÉRENCÉ, pas additionné.
   Si l'export manquait, le décodeur refuserait de lire plutôt que de deviner.
2. **Ce qui n'a pas de nom reste indécodable par nom** : le padding `0x9c`, et le `T` d'un
   `List<T>` — le champ rend `List\`1`, jamais l'élément. Le stride d'un `List<ProbableDamageEvent>`
   se prend donc sur la classe de l'ÉLÉMENT, jamais sur le champ qui la contient.
3. **Un RENOMMAGE inter-build reste une RE.** La conversion ne supprime pas ce coût, elle le rend
   BRUYANT : au lieu de rendre `[1,100]`, le canal nomme le chemin qui n'existe plus.
4. **`classFields` ne dit pas si une classe est un ValueType.** L'information est disponible en
   process (`il2cpp_class_is_valuetype`), mais pas dans la réponse du RPC — donc un lecteur
   OFFLINE de `classFields` doit la poser lui-même. C'est une entrée du harnais de garde, pas une
   donnée mesurée par lui.

## 5. La garde, vue ROUGE puis VERTE

`frida/tools/probe-279-layout-by-name.ts` — `npx tsx tools/probe-279-layout-by-name.ts` depuis
`frida/` (ajouter `--offline` pour l'étape 2 seule, sans host).

Le harnais exécute le **code de production** (`resolveFieldPath`, `resolveFieldsSize`,
`resolvePredictionLayout`), pas une copie : la résolution est paramétrée par un `LayoutProbe`, et
le harnais en fournit un construit sur la disposition RÉELLE rendue par `classFields`. C'est ce qui
rend la garde exécutable **sans réinjection**.

Huit cas, dont une contre-épreuve verte et une contre-épreuve de dérive. **Rouge obtenu par
mutation du code de production** — le `throw` sur champ absent neutralisé (comportement naïf de
`getFieldOffset`, qui rend `-1`), puis la garde d'offset hors-instance neutralisée à son tour pour
atteindre le naïf complet :

```
ROUGE champ renomme -> resolution directe : AUCUNE exception -- la resolution a rendu une valeur
ROUGE resolvePredictionLayout : layout rendu malgre un champ absent
ROUGE offset hors instance (statique) : AUCUNE exception -- la resolution a rendu une valeur
BILAN : 4 ECHEC(S)
```

Gardes restaurées, `BILAN : OK` (8/8). Messages verbatim des cas nominaux :

```
CHAMP INTROUVABLE (#279) : DamagePredictionResult.AccurateHealthDamage -- absent des metadonnees
IL2CPP de ce build. Le decodeur REFUSE de lire plutot que de retomber sur un offset de repli.

RESOLUTION PAR NOM IMPOSSIBLE (#279) : DamagePredictionResult.DefaultScenario.Damage.HealthDamage
-- le conteneur DamagePredictionDamage n'est PAS un ValueType, ses champs ne sont pas INLINE
(il faudrait dereferencer)

OFFSET HORS INSTANCE (#279) : DamagePredictionResult.MightCrit -- offset boxe 4096 hors [16,176[ ;
champ STATIQUE ou litteral, pas un champ d'instance

STRIDE PARTAGE INVALIDE (#279) : ProbableHealEvent=24 != ProbableEffectEvent=32 --
SMALL_EVENT_STRIDE ne peut plus etre unique
```

**Pourquoi lever, et pas rendre 0.** `getFieldOffset` rend `-1` sur un nom absent. Lire à `-1`
serait PIRE que l'offset périmé : périmé mais STABLE, il produisait au moins une valeur
reproductible qu'on a fini par identifier ; `-1` lit une adresse voisine, différente à chaque
appel. Tous les appelants de hook sont déjà sous `try`
(`frida/hooks/features/ai-trace/state.ts`, `frida/hooks/features/scorer-damage-trace.ts`,
`frida/hooks/features/ai-step/rpc-predict.ts`) — lever y est sûr, et remonte l'erreur au lieu de la
lisser.

## 6. Ce qui reste à confronter au prochain reinject

Rien de ce qui suit n'est validé, et le code ne doit pas être présenté comme tel :

* que le bundle injecté **émette les mêmes valeurs** qu'avant sur une prédiction réelle —
  `probe_276_prediction_decoder.py` est la sonde qui le dira, en confrontant la plage rendue au
  dégât mesuré live ;
* que la résolution top-level (`RESOLUTION`, calculée au chargement du module) trouve bien les 5
  classes **au moment où le script s'installe** — `findClassAnywhere` y est appelé plus tôt que
  dans l'ancienne garde, qui était paresseuse. Si une classe n'était pas encore indexée à cet
  instant, `predictionLayoutError()` le dirait ; le comportement est SÛR mais NON OBSERVÉ ;
* que `il2cpp_class_is_valuetype` soit bien résolu en live. L'export est présent dans
  `data/symbols/rnca9r7q6c/ghidra/functions.tsv` et `hooks-legacy/_utils/il2cpp-serializer.js`
  l'utilise, mais la résolution n'a pas été exercée dans la session courante ;
* les tests `tests/engine/runner/test_prevent_overkill_decision_live.py` (4 rouges « CANAL MORT »
  hérités de #268) restent rouges tant que le reinject n'a pas eu lieu.
