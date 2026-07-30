# case-292 — `CurrentAbility` vs `TriggeringAbility` : deux champs natifs, DEUX canaux portés

**Verdict : le signalement est REFUTE. Le port lit le BON champ.** Ce qui était faux, c'est le NOM
du canal Python — et c'est ce nom qui a produit le signalement.

**#294 a posé le second canal** (`TriggeringAbility`, `AbilityEntities+0x98` →
`State.trigger_ability_type`) avec sa sémantique propre, **et le montage qui le sépare du premier** :
§7. Sa couverture est partielle **et nommée** — un seul des quatre écrivains natifs du champ (§7.2).

Origine : l'agent qui a porté la face COMBAT de `CursedPlagueBell` (PR #299) a remonté lui-même, en
« non couvert », que « `!CurrentAbilityIs` est porté sur `TriggeringAbility`, champ natif distinct de
`CurrentAbility` ». Il l'a signalé sans le mesurer. Ce cas l'établit.

---

## 1. Le décompilé (build `rnca9r7q6c`)

### 1.1 Trois champs, trois sélecteurs, deux prédicats

`IdunBattle.Entities.Abilities.AbilityEntities` (`classes.tsv` : 312 octets boxés) porte **trois**
`Nullable<AbilityOrEffect>` de 0x1c octets, à des offsets distincts. Chacun a son sélecteur DSL, et
les trois `Select` sont des copies plates — c'est l'offset LU qui les identifie :

| champ | offset | sélecteur (`IdunBattleLogic.Entities.AbilityTypeSelector.*`) | recoupement indépendant |
|---|---|---|---|
| `CurrentAbility` | **+0x60** | `CurrentAbilitySelector$$Select` (lit `+0x60,+0x68,+0x70,+0x78`) | — |
| `ParentAbility` | **+0x7c** | `ParentAbilitySelector$$Select` | `AbilityEntities$$get_ParentAbilityType` lit `+0x7c` |
| `TriggeringAbility` | **+0x98** | `TriggeringAbilitySelector$$Select` | `AbilityEntities$$get_TriggerAbilityType` lit `+0x98` |

`IdunBattle.Entities.Abilities.AbilityEntities$$GetAbilityExecutionContext` recopie les trois dans un
contexte (`+0x60`→ctx`+0x10`, `+0x98`→ctx`+0x2c`, `+0x7c`→ctx`+0x48`) : troisième lecture, même
appariement.

Côté DSL, les prédicats prennent des **slots distincts** de `DSLSelectors` :

```
IdunBattleLogic.Entities.DSLTriggers$$CurrentAbilityIs        -> DSLSelectors+0x88
IdunBattleLogic.Entities.DSLTriggers$$TriggeringAbilityIs     -> DSLSelectors+0x90
IdunBattleLogic.Entities.DSLTriggers$$TriggeringEffectIs      -> DSLSelectors+0x90   (LE MEME)
IdunBattleLogic.Entities.DSLTriggers$$TriggeringAbilityIsNone -> DSLSelectors+0x90   (LE MEME)
```

Les trois prédicats « Triggering* » partagent **un seul** slot — c'est ce qui justifie qu'un port n'ait
qu'UN canal de ce côté (un `AbilityOrEffect` est une union kind+id, d'où `TriggeringEffectIs` sur le
même champ). `CurrentAbilityIs` est seul sur le sien, et n'a **aucun** homologue `CurrentEffectIs`.

⚠ Aucun des trois sélecteurs n'a de `.ctor` nommé dans `frida/methods.tsv` (corps triviaux
dédupliqués) — leur identité vient du **consommateur** et de l'**offset lu**, jamais d'une absence.

### 1.2 Le moment d'écriture : c'est LUI qui sépare les deux champs

`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` écrit `Nullable<AbilityOrEffect>(this.Id)`
dans les **deux**, mais pas au même instant. Ordre lu au décompilé :

```
1.  AbilityOrEffect.op_Implicit(this) -> Nullable<>..ctor   -> ecrit entities+0x60      [CurrentAbility]
2.  copie de `entities` -> local
3.  behaviour.Execute(<la copie>)                                                  <-- LE BEHAVIOUR
4.  AbilityOrEffect.op_Implicit(this) -> Nullable<>..ctor   -> ecrit entities+0x98   [TriggeringAbility]
5.  copie de `entities` -> local
6.  <processor>.Publish(0xd, <la copie>)                    On(0xd = UnitTriggeredAbility)
```

Donc :

* **`CurrentAbility` est posé AVANT le behaviour** → hérité par TOUT ce que le behaviour engendre
  (attaque, dégât, mort). C'est le champ « quelle ability est en train de s'exécuter ».
* **`TriggeringAbility` est posé APRÈS** → il ne sert qu'à l'événement
  `On(0xd = EventTriggerType.UnitTriggeredAbility)` émis juste après. **Le port ne modélise aucun
  consommateur de `On(0xd)`** — cette face n'existe pas côté port.

L'héritage par le behaviour est explicite : `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
reconstruit bien un `AbilityEntities` neuf, mais via `AbilityEntities$$.ctor(dst, src, activeTarget)`,
qui **copie intégralement** `+0x60`, `+0x7c` et `+0x98` depuis `src` et n'écrase que `+0x20`
(activeTarget), `+0x08` (caster) et `+0x10` (target). Le `CurrentAbility` de la triggered traverse donc
toute la chaîne d'attaque.

Et il ne fuit pas au-delà : l'`AbilityEntities` muté est celui de **cette** évaluation, jeté ensuite —
chaque `IdunBattle.Operations.EvaluateTriggerOperation` en bâtit un neuf (`$$PopulateAbilityEntities`
ne touche ni `+0x60` ni `+0x98`).

### 1.3 Le vecteur MORT n'est ni l'un ni l'autre

`IdunBattle.Operations.RecordKillOperation$$Execute` ne relaie pas le `CurrentAbility` ambiant : il lit
**deux** `Nullable<AbilityOrEffect>` du `KillUnitContext` et les emploie à **deux fins distinctes** —
et c'est cette distinction qui compte :

* `selected = HasValue(context+0x1c) ? context+0x1c : context+0x00` part dans
  `IdunBattle.Core.MatchState$$AddDeath(killer, killed, context+0x00, selected, attackRangeType)` —
  c'est le `killTrigger` **mémorisé dans la file**, rejoué plus tard par le drain ;
* l'événement `On(3 = PendingDeathAdded)`, lui, est publié avec **`context+0x00`** (le buffer est
  ré-écrasé avec ces 0x1c octets juste avant l'appel), via
  `Core.Services.OperationProcessor$$EvaluateAbilities(actor, caster, target, trigger = 3,
  ability = context+0x00)` — donc `+0x60` **et** `+0x98` reçoivent la **même** valeur.

C'est ce dernier point qui rend `TriggeringAbilityIs` évaluable sur `On(3)` : sans lui, le gate de
`FuelledByFury_ReviveAbility` serait toujours faux (l'écriture de `+0x98` par
`BaseTriggeredAbility$$Execute` arrive APRÈS le behaviour, donc après le `On(3)` qu'il engendre).
Ventilation complète des écrivains de `+0x98` : **§7**.

---

## 2. Ce que lit le port, et pourquoi c'est juste

Le port a **un** canal, `State.triggering_ability`, écrit dans un foyer unique
(`triggers/dispatch/core.py::evaluate_trigger_operation`) :

```python
prev_trig = getattr(state, "triggering_ability", None)
if entry.TRIGGERED_ABILITY_ID is not None:
    state.triggering_ability = int(entry.TRIGGERED_ABILITY_ID)
try:
    r = entry.execute_behaviour(state, ev)
finally:
    state.triggering_ability = prev_trig
```

Posé **avant** `execute_behaviour`, restauré **après** : c'est, trait pour trait, la sémantique de
`CurrentAbility` (+0x60) — pas celle de `TriggeringAbility` (+0x98), qui n'est écrit qu'après et pour
un seul événement non porté.

⇒ **`CursedPlagueBellAttackAbility.matches` lit le bon champ.** Le prédicat natif est
`!CurrentAbilityIs(this)` ; le canal du port EST `CurrentAbility`.

Le nom `triggering_ability` est **historique** et trompeur : il désigne le champ natif voisin. Les
quatre docstrings qui affirmaient « `BaseTriggeredAbility$$Execute` écrit `TriggeringAbility` avant le
behaviour » sont corrigées par ce cas (`state.py`, `triggers/base.py`, `dispatch/core.py`,
`loki/cursed_plague_bell.py`).

### 2.1 Les consommateurs `TriggeringAbilityIs` du port — approximation, nommée

`FuelledByFury_ReviveAbility` (`TriggeringAbilityIs(0x400 = FinalJustice)` sur `On(3)`) et
`haze_of_corruption` lisent le **même** canal. Sur le vecteur MORT, le natif y lit le `killTrigger` du
`KillUnitContext` (§1.3), pas `CurrentAbility`. Les deux **coïncident dans tous les régimes portés** —
le coup fatal est porté par la triggered en cours, donc son `AbilityOrEffect` est celui-là — mais ce
sont deux artefacts distincts. **RESIDU NOMME** : aucun montage ne les sépare aujourd'hui ; les séparer
demanderait un `killTrigger` explicitement différent de l'ability en cours d'exécution.

---

## 3. Le régime discriminant, exercé et mesuré

Le régime demandé (« une riposte ou un passif qui se déclenche PENDANT l'exécution d'une autre
ability ») est le **double déclenchement** de `bloodMephiston`, déjà présent dans le montage de
`case-224` : une seule action produit l'attaque primaire, la cloche, **puis le smite
`PsykerExtraAttack` (tag natif `Passive_Ability_Type = 1013`) qui est une attaque DISTINCTE**, donc un
second `On(9)`, donc un second coup de cloche.

C'est le seul point où la **restauration** du canal devient observable : sans elle, ce second `On(9)`
verrait encore `CurrentAbility == 1071` et serait gaté.

Montage : `probe_224_cursed_plague_bell_attack.py`, board `C1_02`, seed `4242`, `--advance 10`.
Deux mutations ajoutées, aux signatures **opposées** :

| mutation | ce qu'elle neutralise | `astraPrimarisPsy` d=2 | `bloodMephiston` d=3 | `spaceStormcaller` d=4 | verdict |
|---|---|---|---|---|---|
| *(aucune)* | — | 1795 / 1 fire == port | **4860 / 2 fires == port** | 0 == port | 0 désaccord |
| `nogate` | le gate `!CurrentAbilityIs` **seul** | == | == | == | **0 désaccord** |
| `persist` | la **restauration** du canal | == | natif **4860 / 2 fires** vs port **2430 / 1 fire** | == | **1 désaccord** |

Flot natif du cas `bloodMephiston` (dump des coups, mutation `persist`) :

```
{a:59 t:51 amt:813  prof:13}              attaque primaire
{a:59 t:59 amt:2430 prof:13 pass:1071}    cloche #1
{a:59 t:55 amt:628  prof:13 pass:1013}    smite PsykerExtraAttack  <-- l'attaque DISTINCTE
{a:59 t:59 amt:2430 prof:13 pass:1071}    cloche #2                <-- ce que `persist` supprime
```

**Ce que chaque signature établit :**

* `persist` rougit ⇒ le canal a bien la **portée** de `CurrentAbility` (valeur jetée avec
  l'`AbilityEntities` de l'évaluation), et le gate le LIT réellement. Un port qui aurait branché le
  gate sur un champ persistant, ou sur le champ `+0x98` (posé après, donc encore vide au moment du
  premier `On(9)` interne), ne produirait pas ce flot.
* `nogate` ne rougit pas ⇒ le gate `!CurrentAbilityIs(this)` est **REDONDANT** avec `!CasterIsTarget`
  sur ce montage : la riposte étant une auto-attaque (`caster == target == le psyker`), le premier
  gate mord déjà. Ce n'est pas un accord vide — c'est un fait, et c'est la raison pour laquelle une
  erreur de champ sur CE prédicat n'aurait cassé aucun test : elle est **masquée** par la seconde
  ceinture. C'est aussi ce qui rend le signalement d'origine plausible, et sa vérification nécessaire.

---

## 4. Gardes posées

* `test_triggered_ability_id_channel_mirrors_current_ability_not_triggering_ability` (OFFLINE,
  déterministe) — une `TriggeredAbility` espionne vérifie les **deux** moitiés de la sémantique
  `+0x60` : l'id est visible DANS `execute_behaviour`, la valeur ambiante est RESTAUREE après, et
  `matches` s'évalue AVANT l'écriture (il voit l'ambiante, jamais la sienne).
* `test_double_trigger_regime_is_reached_and_agrees_live` (LIVE) — **exerce** le régime : exige qu'un
  cas atteigne `live_fires >= 2`, que `port_fires == live_fires` (l'ETAGE, pas le total agrégé), et
  que le tag `1013` soit dans le flot (le second déclenchement vient d'une attaque native distincte,
  pas d'un second coup d'arme). Sans la clause `multi`, un montage dégradé passerait au vert sans
  jamais atteindre le régime.
* `probe_224 --mutate {nogate,persist}` — les deux contre-épreuves ci-dessus, rejouables.

---

## 5. Ce que ce cas n'établit PAS

* **Le gate `!CurrentAbilityIs(this)` n'est pas exercé SEUL.** `nogate` = 0 désaccord : `!CasterIsTarget`
  le couvre. Pour l'isoler il faudrait un montage où le `CurrentAbility` vaut 1071 sur un `On(9)` dont
  le caster n'est PAS la cible — or le seul émetteur d'attaque parmi les trois classes du passif est
  cette classe-ci, et son attaque est une auto-attaque. Le gate est porté en **mirror**, sa face
  discriminante propre reste non mesurée.
* **La face `TriggeringAbility` (+0x98) est PORTÉE depuis #294** — `State.trigger_ability_type`, et
  le montage qui la sépare de `+0x60` existe (**§7**). Ce que #294 n'établit pas, ce sont les **trois
  autres écrivains natifs** de ce champ : eux restent des résidus nommés (§7.3).
* **La divergence `killTrigger` vs `CurrentAbility`** sur le vecteur MORT (§2.1) reste non séparée par
  un montage : les deux coïncident partout où le port les exerce. #294 en donne la **raison
  structurelle** (§7.2, écrivain 1) — sur `On(3)` le natif écrit la MÊME valeur dans les deux champs,
  donc aucun montage ne peut les y séparer. La divergence réelle est ailleurs, sur `On(0)/On(1)`
  (écrivain 2), et elle n'est pas exercée non plus.
* **La collision d'espace d'id** (`ActiveAbilityType 1071 = AnnihilatorBeam` vs
  `TriggeredAbilityType 1071 = CursedPlagueBell`) reste la raison pour laquelle `ability_type` ne peut
  pas porter cet id ; elle est re-dérivée par l'étape 0 du probe, pas héritée.

---

## 6. Reproduire

```bash
cd scripts/python
python probe_224_cursed_plague_bell_attack.py --board C1_02 --seed 4242 --advance 10 --dists 2,3,4
python probe_224_cursed_plague_bell_attack.py --board C1_02 --seed 4242 --advance 10 --dists 2,3,4 \
    --mutate persist      # attendu : 1 desaccord, bloodMephiston 4860/2 fires vs 2430/1 fire
python probe_224_cursed_plague_bell_attack.py --board C1_02 --seed 4242 --advance 10 --dists 2,3,4 \
    --mutate nogate       # attendu : 0 desaccord (gate redondant avec !CasterIsTarget)
python -m pytest tests/engine/runner/test_cursed_plague_bell_attack_live.py -q
```

---

## 7. Le SECOND canal — `TriggeringAbility` (+0x98) porté et SÉPARÉ (#294)

### 7.1 Le montage, parce que sans lui le canal ne vaut rien

Poser `+0x98` « parce que le décompilé le montre » ne prouve rien : `BaseTriggeredAbility$$Execute`
écrit **la même** `AbilityOrEffect(this.Id)` dans les deux champs. Sur une triggered ISOLÉE, un canal
`+0x98` correctement câblé et un canal `+0x98` recâblé par erreur sur `+0x60` sont **indiscernables**.
Ce qui les sépare est le MOMENT, donc il faut une **chaîne** — une triggered qui en engendre une autre.

`probe_294_trigger_ability_channels.py` monte cette chaîne dans un `State` nu (OFFLINE, déterministe,
zéro RNG, zéro runner) : trois triggered espionnes `A --On(0xd)--> B --On(9)--> C`, où `B` porte le
mirror d'un `TriggeringAbilityIs(A)`. Trace **mesurée** :

```
site                 +0x60 (triggering_ability)   +0x98 (trigger_ability_type)
A.matches            None                         None
A.exec               4242                         None      <- +0x98 pas encore ecrit (etape 4/6)
B.matches            None                         4242      <- SEPARATION : le gate lit bien +0x98
B.exec               4343                         4242      <- DEUX NON-NULS DIFFERENTS  *** livrable
A.matches (sous B)   4343                         4242
C.matches (sous B)   4343                         4242      <- +0x60 herite, +0x98 NON
B.matches (On 0xd    None                         4343      <- gate faux -> pas de boucle
           de B)
C.matches            None                         None
final                None                         None      <- les deux restaures
```

La ligne `B.exec` est le seul point du montage où les deux canaux portent **deux valeurs non nulles
différentes**. C'est là, et nulle part ailleurs, qu'une confusion des deux champs devient visible.

### 7.2 Les QUATRE écrivains natifs de `+0x98` — et le seul que le port modélise

`+0x98` a **36** consommateurs DSL (`DSLTriggers$$TriggeringAbilityIs`), plus `$$TriggeringEffectIs`,
`$$TriggeringAbilityIsNone` et `$$TriggeringAbilityIsNormalAttack` — les quatre partagent le slot
`DSLSelectors+0x90` (le case-292 §1.1 n'en citait que trois). Ils ne sont pas alimentés par
`BaseTriggeredAbility$$Execute` :

| # | écrivain | ce qu'il écrit | événements | porté ? |
|---|---|---|---|---|
| 1 | `Core.Services.OperationProcessor$$EvaluateAbilities(actor, caster, target, [tiles,] trigger, ability [, prev, wasCrit])` | `+0x60` **et** `+0x98` = `ability` ; `+0x7c` = `default` | la voie universelle, dont `On(3)` via `RecordKillOperation` | **non** |
| 2 | `IdunBattle.Operations.KillUnitOperation$$Execute` | `+0x98` = `KillUnitOptions+0x04` ; **`+0x60` reste ZÉRO** | `On(0)`, `On(1)`, `On(2)`, `On(53)`, `On(54)` | **non** |
| 3 | `IdunBattle.Operations.AddEffectOperation$$Execute` | `+0x60` = `+0x98` = `AbilityOrEffect(effectType)` | `On(61)`, `On(62)`, `On(70)` | **non** |
| 4 | `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` | `+0x98` = `this.Id`, APRÈS le behaviour | `On(0xd)` | **OUI** |

Deux résultats NÉGATIFS, à ne pas supposer :

* `IdunBattle.Operations.RemoveEffectOperation$$Execute` n'écrit **que** `+0x60` (= l'effet retiré) et
  laisse `+0x98` à zéro ⇒ sur `On(63)`/`On(64)`, c'est `CurrentAbilityIs` qui porte l'effet, pas
  `TriggeringEffectIs`. Asymétrie ADD/REMOVE contre-intuitive.
* `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` met `+0x60 = abilityOrEffect` et
  `+0x98 = default` (`On(8)`, `On(60)`).

### 7.3 Ce que #294 n'établit PAS

* **L'événement `On(0xd)` n'a AUCUN consommateur** — ni porté, ni **natif**. Côté port : 86
  classes-triggers enregistrées, 37 `event_id` distincts, **0** sur 13. Côté natif : le balayage de
  toutes les voies de construction d'un nœud d'événement (`DSLTriggers$$On` et ses deux overloads,
  `$$OnDeathEvent`, `$$OnOwnerSpecificAbilityInit`, `$$OnNormalAttackOrSmite`, `$$OnAttackFromAbility`,
  `BaseEffect$$On`) ne rend aucun `CreateTrigger` sur `0xd`. **Trou déclaré** : 4
  `Env*Ability$$CreateTrigger` construisent leur liste d'événements par
  `RuntimeHelpers.InitializeArray` — le blob n'est pas lisible depuis ghidra-mcp (il faudrait le dump
  IL2CPP). Ce sont des abilities d'environnement, hors périmètre confrontable.
  ⇒ L'écriture native de `+0x98` avant `On(0xd)` semble n'exister que pour la cohérence de la struct
  publiée. Le port l'émet quand même : c'est le mirror, et c'est ce qui rend le canal observable.
  **Coût mesuré** : sur les 86 classes-triggers du registre, **7 seulement** déclarent un
  `TRIGGERED_ABILITY_ID` — les 79 autres sortent de `_publish_unit_triggered_ability` par un `return`
  immédiat. Le surcoût est donc un dispatch qui rend `[]` pour 7 familles de triggers, et il est
  invisible bout-en-bout : `test_death_queue_ordering_live.py` (22 tests, session Frida 2, même
  machine, runs consécutifs) — **AVANT 148,43 s / APRÈS 147,07 s**, soit −0,9 %, dans le bruit.
* **Les écrivains 1, 2 et 3 ne sont pas portés.** Le seul qui produise une **divergence réelle** est
  le 2 : sur `On(0)/On(1)/On(2)`, le natif laisse `+0x60` à zéro alors que le port y pose l'ambiant.
  Aucun montage ne l'exerce ici ; le porter changerait un vecteur EXERCÉ (la mort) et déborde #294.
* **Aucune mesure LIVE**, et c'est délibéré : sans consommateur porté ni capteur, `+0x98` n'a aucune
  observable de bataille. Un montage live serait du théâtre. Ce qui est verrouillé est le MOMENT
  D'ÉCRITURE et la PORTÉE, offline et déterministes.
* La lecture des quatre écrivains vient d'**une** passe RE (recoupée sur les offsets par
  `TriggeringAbilitySelector$$Select` et `AbilityEntities$$get_TriggerAbilityType`). Le point le plus
  fragile signalé : `AttackDamageOperation$$ExecuteHit` (fonction énorme, blocs 0x1c coalescés par
  Ghidra) — à relire au désassemblage si un trigger d'attaque diverge.

### 7.4 Gardes posées (#294)

`tests/engine/runner/test_trigger_ability_channels.py`, fixture `trigger_ability_channel_case` :

* `test_the_two_channels_are_distinct_slots_on_state` — écrire l'un ne touche pas l'autre ;
* `test_channels_separate_in_a_chained_triggered_ability` — les cinq faits de la trace §7.1 ;
* `test_channel_carries_the_MOST_RECENT_triggered_not_the_first` — **généralisation en PROFONDEUR** :
  sous le `On(0xd)` de `B`, `+0x98` vaut `B` (pas `A`) ; c'est ce qui referme la chaîne
  (`fires["B.exec"] == 1`). Un port qui n'écrirait `+0x98` qu'à la racine passerait tout le reste ;
* `test_effect_triggers_publish_the_event_too` — **généralisation à l'AUTRE famille du registre** :
  un `EffectTrigger` pose le canal et publie `On(0xd)` comme une `TriggeredAbility` (les deux
  convergent nativement sur `BaseTriggeredAbility$$Execute`). Un port qui aurait câblé la
  publication sur `isinstance(entry, TriggeredAbility)` — ce que fait légitimement le cap de phase —
  serait faux **ici et nulle part ailleurs** ;
* `test_each_mutation_reddens_the_montage` — les **4** contre-épreuves, chacune doit ROUGIR ;
* `test_nominal_and_mutations_do_not_agree_by_accident` — anti-contre-épreuve-no-op ;
* `test_publish_is_a_no_op_for_an_entry_without_id` — pas d'id, pas d'écriture ni d'`On(0xd)`.

**10 tests, tous OFFLINE et déterministes** (~2 s). Non-régression LIVE re-jouée après rebase :
`test_cursed_plague_bell_attack_live.py` (7), `test_death_queue_ordering_live.py` (22),
`test_on_toxic_damage_live.py` — ce dernier étant le plus discriminant du lot, puisqu'il mesure la
**cardinalité RNG** du dispatch (un `NextBool` par série de coups) : une émission d'`On(0xd)` qui
réveillerait un trigger global le ferait rougir.

Rouge VU **avant** le fix (code stashé, montage inchangé) :

```
garde: ROUGE -- site 'B.matches' non atteint (occurrence 0) -- la chaine n'est pas montee ;
sites observes = ['A.matches', 'A.exec', 'C.matches']
```

Les quatre mutations, chacune avec sa signature propre :

```
--mutate before   ROUGE -- +0x98 est deja ecrit PENDANT le behaviour de A : (4242, 4242) != (4242, None).
--mutate alias    ROUGE -- le gate TriggeringAbilityIs(A) ne lit pas +0x98 : (4242, None) != (None, 4242).
--mutate persist  ROUGE -- un canal FUIT hors de son evaluation : final=(None, 4343) != (None, None).
--mutate noevent  ROUGE -- site 'B.matches' non atteint (occurrence 0) -- la chaine n'est pas montee.
```

### 7.5 Reproduire (#294)

```bash
cd scripts/python
python probe_294_trigger_ability_channels.py
python probe_294_trigger_ability_channels.py --mutate before    # attendu : ROUGE, canaux egaux
python probe_294_trigger_ability_channels.py --mutate alias     # attendu : ROUGE, B ne fire pas
python probe_294_trigger_ability_channels.py --mutate persist   # attendu : ROUGE, fuite finale
python probe_294_trigger_ability_channels.py --mutate noevent   # attendu : ROUGE, B ne fire pas
python -m pytest tests/engine/runner/test_trigger_ability_channels.py -q
```
