# case-547-r13 — le gate `KeepOnRevive` est armé par UN SEUL producteur, et ce n'est pas la mort

`#547-r13` opposait deux mesures : l'observation live de `#547-r12` (`effects=[]` sur trois
cadavres, runners 638 et 669, board `MC1_67`, `includeInactive: true` compris) et une lecture
(`LifewardsProtectingEffect` hérite `get_KeepOnRevive = TRUE`, corps `b0 01 c3`, donc il *devrait*
survivre). Verdict : **les deux étaient justes**. La lecture fausse était une **troisième**, tacite —
appliquer ce getter au chemin de **mort**.

## 1. Le `if` imbriqué est une CONJONCTION, et le résumé en avait perdu le premier terme

`IdunBattle.Operations.RemoveEffectsOperation$$Execute`, relu verbatim :

    if (options.step.HasValue && effect.<IEffect slot 4> != options.step.Value) continue
    if (options.<+0x08>       && effect.<IEffect slot 2>)                       continue
        ^^^^^^^^^^^^^^^^ CE conjoint
    toRemove.Add(effectId)

**Le layout est PROUVÉ, pas déduit d'offsets** : `Core.Services.OperationProcessor$$RemoveEffects`
recopie la struct avant de la passer, et il recopie exactement `*(undefined8*)options` puis
`*(undefined4*)(options + 8)` — 8 + 4 octets, rien de plus.

## 2. Les SEPT `$$RemoveEffects` du binaire, lus un par un

| producteur | voie | `options.step` | `options.<+0x08>` |
|---|---|---|---|
| `IdunBattle.Operations.KillUnitOperation$$RemoveEffects` | slot 0x5a | `Nullable(step)` | **0** |
| `IdunBattle.Operations.DestroyMachineOperation$$RemoveEffects` | slot 0x5a | `Nullable(step)` | **0** |
| `IdunBattle.Operations.FleeOperation$$RemoveEffects` | slot 0x5a | `Nullable(step)` | **0** |
| `IdunBattle.Operations.RemoveUnitOperation$$RemoveEffects` | slot 0x5a | sans valeur | **0** |
| `IdunBattle.Operations.ReviveUnitOperation$$RemoveEffects` | slot 0x5a | sans valeur | **1** |
| `IdunBattle.Operations.ChangeUnitOwnerOperation$$RemoveEffects` | boucle inline | — | lit le slot **3** `get_KeepOnChangeOwner` |
| `IdunBattle.Operations.RemoveMachineOperation$$RemoveEffects` | boucle inline | — | aucun filtre, retire tout |

⇒ le gate est armé **à un seul endroit**, le revive. Sur le chemin de mort, `IEffect` slot 2 n'est
**jamais lu** — le port, qui ne porte pas ce prédicat, y est donc **fidèle**, et l'état rechargé
l'est aussi. C'est l'issue (a) que la fiche envisageait ; il n'y a rien à seeder.

⚠ `IdunBattle.Operations.ReviveUnitOperation$$RemoveEffects` n'a **aucune xref CODE** (2 entrées
DATA de tables de méthodes). Son corps est le **doublon** qu'IL2CPP a émis : l'appel réel est
**inliné** dans `IdunBattle.Operations.ReviveUnitOperation$$Execute`, entre
`IdunBattle.Operations.ReviveUnitOperation$$SetHealth` et la rafale de flags — même octet de garde
de cctor, mêmes deux écritures, même slot. Conclure « mort » d'une absence de xref aurait été faux.

## 3. La valeur du getter est DÉRIVÉE, pas lue dans une table indexée par adresse

`probe_547r13_keep_on_revive.py` (même machinerie que `probe_1088` pour le slot 4 : déclaration lue
dans le `global-metadata.dat`, valeur lue **aux octets** dans le bloc `methodPointers`, contrôles
d'alignement locaux) — entrée versionnée `data/symbols/<build>/metadata/keep_on_revive.tsv` :

* défaut de `IdunBattle.Entities.Effects.BaseEffect` = **True** (`b0 01 c3`, 66 contrôles locaux) —
  la fiche citait juste ;
* **3** classes le renversent : `Loki.HealingBalmsEffect`, `Loki.PrecisionShot_AimEffect`,
  `Loki.RitesOfMorkai_ExtraDamageEffect` ;
* **50** classes sur 465 lisent un **champ d'instance** (`AStatModifierEffect` et sa descendance
  prennent `keepOnRevive` en argument de `.ctor`) → rendues `INDÉTERMINÉES`, jamais un faux `True`.

⚠ L'avertissement multi-VA était fondé et **ne mord pas ici** : trois classes (`NoneEffect`,
`TemporaryEffect`, `HuntTheFallen_FallenEffect`) partagent le corps `0f b6 81 80 04 00 00 c3`,
donc un seul propriétaire dans la table indexée par adresse. La dérivation ne lit pas la table.

## 4. Le cliquet livré

`tests/engine/runner/test_547r13_cadavre_sans_effet_offline.py` — 5 tests, 3 étages :

1. un effet déclarant `keep_on_revive = True` est retiré **quand même** (témoin non dégénéré : deux
   effets de même step, l'un avec le flag) ;
2. les passes de la séquence de mort sont **LUES dans l'AST** de `damage.py`, et leur union doit
   **égaler** le domaine de `KillUnitStep` ⇒ aucun effet ne survit ; balayage de **303** classes
   d'effet portées sur **104** modules, `remove_on_kill_step` = {1:301, 0:1, 2:1}, **0 hors domaine** ;
3. concordance avec l'entrée versionnée.

Mutants joués : ajouter le gate `keep_on_revive` au chemin de mort → **étage 1 rouge** ; remplacer
`KillUnitStep.AfterDeathTrigger` par `AfterUnitRemove` dans la 3ᵉ passe → **2 rouges**.

## 5. Ce qui n'est PAS couvert

* **Le revive n'est pas porté** : le natif y retire tous les effets sauf `KeepOnRevive`,
  `revive.py::ReviveUnitOperation.execute` n'en retire aucun → résidu **`#547-r14`** (le substrat
  est déjà là : la table versionnée et son lecteur).
* **50 classes indéterminées** : leur valeur dépend d'un argument de constructeur, hors de portée
  d'une lecture de constante. Porter le défaut pour elles serait fidèle au sens mais **non mesuré**.
* Rien de cette tranche n'est confronté LIVE : tout est décompilé + dérivation binaire + offline.
  L'observable qu'elle explique, lui, l'était (`#547-r12`, trois cadavres).
