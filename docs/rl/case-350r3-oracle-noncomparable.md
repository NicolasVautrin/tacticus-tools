# case-350-r3 (a) — l'oracle de la face NonComparable

Résidu `#350-r3` **mur (a)** : « les playbooks **NonComparable** rendent 0 event à `aiPlaybookPredict`
(mesuré sur `1132 KillMaimBurn` ; concerne aussi 1111, 1173, 1202) — il manque un oracle pour la face
NonComparable. »

Question binaire posée : **existe-t-il un point d'observation natif qui rende la prédiction de dégât
d'un playbook NonComparable ?** Réponse : **OUI** — mais pas au même endroit, et il faut un capteur.
Le détail ci-dessous sépare ce qui est *structurellement impossible* de ce qui est *observable*.

## 1. Pourquoi `aiPlaybookPredict` ne peut RIEN rendre — et pourquoi c'est la réponse JUSTE

La hiérarchie est lue dans la table VERSIONNÉE `data/symbols/rnca9r7q6c/frida/classes.tsv`
(colonne « parent »), pas déduite :

```
BasePlaybook              (System.Object)
  └── Playbook`1
        ├── ComparablePlaybook`1        <- MakeDamage/Heal/Effect/RepairPredictions y sont DÉCLARÉES
        └── NonComparablePlaybook`1     <- EvaluateInternal
```

`ComparablePlaybook`1` et `NonComparablePlaybook`1` sont **frères**. Les quatre `Make*Predictions`
n'existent que sur la branche Comparable :
`ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeDamagePredictions` (corps de base :
enumerable vide), `$$MakeHealPredictions`, `$$MakeEffectPredictions`, `$$MakeRepairPredictions`.
`NonComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E` n'en déclare **aucune** — ses seuls
membres propres sont `$$EvaluateInternal` (un dispatch nu vers le slot de vtable `+0x318`, c.-à-d.
`EvaluateNonComparable`), `$$GenerateBucketWithActionForEveryEligibleTarget` et
`$$GenerateBucketWithMultipleStrategies`.

⇒ Sur un playbook NonComparable, le `findMethodByParamCount(pbCls, "MakeDamagePredictions", 4|3)` de
`playbook-predict.ts::makeDamagePredictions` **ne résout rien** : le RPC rend `makeArity: 0`,
`listNull: true`, `count: -1`. Ce n'est pas un silence à interpréter — c'est la **valeur de retour**
qui dit « ce chemin n'existe pas ici ». **Le « 0 event » de #350 est exact et le restera.**

Portée : `classes.tsv` compte **134** classes de parent direct `NonComparablePlaybook`1` contre **96**
de parent `ComparablePlaybook`1`. Le mur ne concernait donc pas 4 abilities mais la moitié du
catalogue de playbooks.

## 2. Ce que le natif fait à la place — et où la prédiction de dégât EXISTE

`<X>Playbook$$EvaluateNonComparable(this, caster, casterPosition, abilityState)` boucle sur
`BasePlaybook$$GetEligibleTargetsSelectable` (une `List<AbilityEntities>`, une entrée par cible
éligible) et, par cible :

1. évalue le nœud de dégât de l'ability (`this+0x68`) — corps et **slot d'`IAmountFormula`** relus
   site par site (le slot n'est PAS constant, cf. §3) ;
2. lit `AActiveAbility$$GetDamageProfile` et `AActiveAbility$$GetHits` ;
3. appelle `Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent` avec
   le triplet `(damage, profile, hits)` ;
4. `BasePlaybook$$GenerateAction(position, target, utility)` puis `Bucket$$AddAction`.

**Le point clé est l'étape 3.** Les deux surcharges « triplet » de
`Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent` — celle à
`(entities, damage, profile, hits)` et celle à `(caster, target, position, damage, profile, hits)` —
font TOUTES DEUX, avant de scorer :

* `IBattleQuery` slot `0x28` (`GetAttackPrediction`) avec `(caster, target, casterPosition,
  AbilityOrEffect, damage, Nullable(profile), hits)` → un `DamagePredictionResult` **complet** ;
* `IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor(target, damagePrediction, probability, weight)` ;
* puis délèguent à la surcharge finale `(ProbableDamageEvent, caster, casterPosition, …)`, qui
  construit l'`UtilityAttackCase$$ForDamagePrediction`.

⇒ **Un playbook NonComparable CONSTRUIT le même `ProbableDamageEvent` qu'un Comparable.** Il ne le
met simplement dans aucune liste : il le consomme sur place. La différence entre les deux faces n'est
pas « prédiction vs heuristique », c'est **« prédiction RENDUE vs prédiction CONSOMMÉE »**.

C'est ce qui rend un oracle possible, et avec le décodeur DÉJÀ écrit : la struct est celle que
`playbook-predict.ts::readDamageEvent` lit (stride et offsets résolus dans `game/damage-prediction.ts`,
#276), puisque c'est littéralement le même ctor.

## 3. Le slot d'évaluation n'est pas constant — relu sur les quatre abilities du résidu

`FUN_180025fb0(slot, IAmountFormula, node, entities, out)` est l'invocation d'interface par slot.
Lu VERBATIM au call-site de chaque `EvaluateNonComparable` :

| id | corps de la formule | slot |
|---|---|---|
| 1132 KillMaimBurn | `StaffOfStarsAbility$$GetDamage(state, isPrediction = 1)` | **4** (`CalculateAverage`) |
| 1111 LivingBatteringRam | `StaffOfStarsAbility$$GetDamage(state, isPrediction = 1)` | **1** (`Calculate`) |
| 1173 ArcScourge | `StranglethornCannonAbility$$GetDamageAmountMain(state)` | **1** (`Calculate`) |
| 1202 VigilanceEternal | `VigilanceEternalAbility$$GetDamage(state)` (pas d'`isPrediction`) | **4** (`CalculateAverage`) |

`IdunBattle.DSL.AAmountFormula$$CalculateAverage` n'est PAS inconditionnellement `(min + max) / 2` :
il teste d'abord le prédicat de vtable `+0x1c8` et, s'il est vrai, retombe sur `Calculate` (`+0x1d8`) ;
sinon seulement il fait `(vtable+0x1f8 + vtable+0x1e8) / 2` en division entière C (troncature).
Slot 1 et slot 4 coïncident donc pour un nœud déterministe et divergent pour un `RandomAmount` —
ce qui est cohérent avec les inscriptions de #350 (1132/1111 en (a2), 1202 en (b)), **mais la
coïncidence est une propriété du nœud, pas une identité des slots**. Un port qui recalculerait la
moyenne sans lire le slot du call-site serait juste par accident.

1173 ajoute au triplet un terme propre : pour chaque unité poussée, `Playbook<T>$$GetUtilityValue`
d'une constante différente selon `UnitExtensions$$IsEnemy`. Il n'affecte pas la prédiction de dégât.

## 4. Ce qui existe DÉJÀ, et ce qui manque

| oracle | rend | état |
|---|---|---|
| `aiPlaybookPredict` | `ProbableDamageEvent[]` d'un playbook **Comparable** | livré ; **inapplicable** à la face NC (§1) |
| `ncEvaluate` (#46) | l'**utilité** `best` du Bucket d'un playbook NC, par position | **livré et applicable** — jamais branché au rail #344 |
| `ncPlaybookPredict` | les `ProbableDamageEvent` **construits** pendant l'évaluation NC | **capteur neuf** (§5) |

`ncEvaluate` répond déjà à « la face NC vit-elle, et que vaut-elle ? ». Il ne répond pas à « quelle
prédiction de dégât l'a produite » : entre les deux il y a `UtilityAttackCase$$ForDamagePrediction` et
tout le composite d'utilité, qu'il faudrait porter pour inverser. Pour l'objet de #350 — la FORME de la
moyenne, un écart d'une unité — c'est le mauvais étage : on mesurerait un scalaire agrégé au lieu de
l'entrée (doctrine « décomposer par étage, jamais fitter un scalaire »).

## 5. Le capteur livré — `ncPlaybookPredict`

Ancrage : **`IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor`**, corps UNIQUE, présent dans
`data/symbols/rnca9r7q6c/frida/methods.tsv` avec sa signature
`(target: IEntity, damagePrediction: DamagePredictionResult, probability: Nullable<Fix64>,
weight: Nullable<Fix64>)` — donc résoluble par `findClassAnywhere` + `findMethod`, **sans aucune RVA**.

Le ctor écrit dans `this` (= `args[0]`) : `Target` à `+0x00`, les **0xa0** octets du
`DamagePredictionResult` de `+0x08` à `+0xa4`, `Probability` à `+0xa8`, `Weight` à `+0xb0` — donc
exactement ce que `readDamageEvent` lit, et la capture se fait en `onLeave` (la struct vit sur la pile
de l'appelant et n'est remplie qu'au retour). Les deux `Nullable<Fix64>` sont **résolues par le ctor
lui-même** (`Fix64(1)` quand `hasValue` est faux), donc le champ capturé est la valeur effective.

Le RPC est **fenêtré**, pas armé en permanence : il attache le trampoline, invoque le wrapper
`Evaluate` du playbook (même résolution que `ncEvaluate` — appeler la leaf nue crashe, l'`AbilityState`
manque), détache immédiatement, puis décode le buffer avec `readDamageEvent`. Il n'existe donc à aucun
moment de hook permanent sur ce ctor, qui est chaud (tout `MakeDamagePredictions` comparable le traverse).

La réponse mirror celle d'`aiPlaybookPredict` (`events[]` avec `healthDmgMin/Max`, `appliedHits`, …),
de sorte que le gabarit `probe_344_ability_damage_average.py` puisse commuter d'oracle sans changer sa
logique de verdict.

**Déploiement** : `frida/hooks/*` ne vit qu'après réinjection. Le code est livré, **non déployé**.

## 6. État de la mesure

`probe_350r3_noncomparable_oracle.py` porte les quatre étapes. Fixtures **nommées** (`_FIXTURE_*`),
jamais de montage inline.

| étape | ce qu'elle tranche | plateforme | état |
|---|---|---|---|
| 0 structure | §1 : frères, exclusivité des `Make*Predictions`, les 4 playbooks sont NC | **aucune** | **VERTE** |
| 1 valeur de retour | `aiPlaybookPredict` rend bien `makeArity 0` / `listNull` **et** la bonne `playbookClass` | session Frida | **NON CONFRONTÉE** |
| 2 `ncEvaluate` | non-vacuité : « 0 event » ne se lit pas « rien ne se passe » | session Frida | **NON CONFRONTÉE** |
| 3 capteur | verrou (`via=makeDamagePredictions` sur une Comparable : capture == liste rendue) puis NC | session **+ capteur déployé** | **NON CONFRONTÉE** |

Étape 0, jouée (`--offline`) : `siblings = True`, **134** NC / **96** Comparable, les 4
`Make*Predictions` présentes sur la branche Comparable et **aucune** sur la NC, membres propres de
`NonComparablePlaybook`1` = `EvaluateInternal`, `GenerateBucketWithActionForEveryEligibleTarget`,
`GenerateBucketWithMultipleStrategies`, et les 4 playbooks du résidu de parent
`NonComparablePlaybook`1`.

Étapes 1-3 : **NON CONFRONTÉES — plateforme DOWN.** Aucun process n'écoutait sur `127.0.0.1:8765`
au moment de ce travail (host Frida non lancé), donc aucun RPC. Ni le compte hérité (« 0 event sur
1132 ») ni les trois faces du §4 n'ont pu être re-mesurés. Le probe le **DIT** (`LIVE NON CONFRONTE`)
au lieu de rendre un zéro. Ce qui est établi ci-dessus l'est **au décompilé et par la table de
symboles versionnée**, deux sources indépendantes du live.

L'étape 1 a une propriété utile pour la reprise : **le caster n'y entre pas**. `LoadPlaybook` charge
par ability et la résolution de méthode échoue avant tout usage du caster — le verdict est une
propriété de la CLASSE du playbook, donc un montage trivial suffit (le contrôle `playbookClass` évite
le faux positif du `fallbackToDefault`, qui rendrait le playbook d'attaque normale).

**Le capteur compile** : `frida-compile hooks/main.ts` sort en `exit 0`, bundle 1 039 732 o,
`ncPlaybookPredict` présent. Il n'est **pas déployé** — `frida/hooks/*` ne vit qu'après réinjection.
