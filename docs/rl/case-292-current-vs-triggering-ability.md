# case-292 — `CurrentAbility` vs `TriggeringAbility` : deux champs natifs, un canal porté

**Verdict : le signalement est REFUTE. Le port lit le BON champ.** Ce qui était faux, c'est le NOM
du canal Python — et c'est ce nom qui a produit le signalement.

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
un `killTrigger` **explicite** dans le `KillUnitContext` — le `Nullable<AbilityOrEffect>` de
`context+0x20` s'il a une valeur, **sinon** celui de `context+0x00` — et c'est CE `AbilityOrEffect`
qu'il passe à `MatchState.AddDeath` puis au publieur d'`On(3 = PendingDeathAdded)`.

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
* **La face `TriggeringAbility` (+0x98) n'est pas portée du tout** : aucun consommateur de
  `On(0xd = UnitTriggeredAbility)` n'existe côté port. Si une ability future en écoute un, elle NE
  DOIT PAS réutiliser `State.triggering_ability` — il faudra un second canal, posé APRÈS le behaviour.
* **La divergence `killTrigger` vs `CurrentAbility`** sur le vecteur MORT (§2.1) reste non séparée par
  un montage : les deux coïncident partout où le port les exerce.
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
