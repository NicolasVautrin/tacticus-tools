# `#419-r1-tr14-r5-r2` — la voie ACTIVE du dispatch d'attaque normale

Suite de `case-419-r1-tr14-r5-dispatch-attaque-normale.md`, qui a fermé la voie PASSIVE (table à 14
entrées, 14/14 confrontées) et nommé ce résidu : « la voie ACTIVE reste au kit ».

## 1. Ce que dit le décompilé (relu, non hérité)

`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` — la cascade COMPLÈTE, verbatim :

```csharp
if (config.Traits.Contains(0x0e)) return;          // Erratic  -- porté (-r4)
if (config.Traits.Contains(0x15)) return;          // Harmless -- porté (-r4)
var fromPassive = GetCustomNormalAttackTypeFromPassive(this, config);   // config@+0xa8
if (fromPassive.HasValue) { type = fromPassive.Value; state = triggeredAbilityState; }
else {
    var fromActive = GetCustomNormalAttackTypeFromActive(this, config); // config@+0xa0
    if (fromActive.HasValue) { type = fromActive.Value; state = activeAbilityState; }
    else if (config.Traits.Contains(0x7e7)) { type = 0x406; state = activeAbilityState; }
    else {
        var already = ListExtensions.FilterNewList(comp.<+0x20>, <Func statique>);
        if (already.Count > 0) return;              // rien n'est ajouté
        type = this.<+0x20>;
        state = new AbilityState(Level(1), config.<+0x74>);
    }
}
ActiveAbilityComponent.Add(comp, type, state, null);
```

`IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromActive` :

```csharp
foreach (var active in config.<+0xa0> /* UnitConfiguration.ActiveAbilities */) {
    var custom = StaticBattleRules.ActiveAbility.GetCustomNormalAttack(active);
    if (custom.HasValue) return custom;             // le PREMIER actif gagnant s'impose
}
return null;                                        // PAS de branche tertiaire ici (≠ voie passive)
```

Trois différences avec la voie passive, toutes lues :

1. **le substrat** : `config@+0xa0`, pas `+0xa8` ;
2. **la table** : `StaticBattleRules.ActiveAbility` statics `+0xb8` → **`+0x28`**, une AUTRE table que
   `StaticBattleRules.TriggeredAbility` statics `+0xb8` → `+0x50` ;
3. **pas de branche TERTIAIRE** : la voie passive consulte `config@+0xb0` après avoir épuisé la
   liste, la voie active s'arrête à la boucle.

### 1.1 `config@+0xa0` = `UnitConfiguration.ActiveAbilities` — prouvé par un SECOND corps

Pas déduit du nom de la fonction. `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`
lit les TROIS champs dans le même corps, et chacun va à un consommateur qui le nomme :

| champ | ce que le corps en fait |
|---|---|
| `config@+0xa8` | itéré → `TriggeredAbilityComponent$$TryAdd(..., hiérarchie **2**)` = les PASSIFS |
| `config@+0xb0` | `Nullable`, → `TryAdd(..., hiérarchie **3**)` = l'ability TERTIAIRE (relique) |
| `config@+0xa0` | itéré PAR INDEX → `UnitFactory$$AddActiveAbility(...)` = les ACTIVES |

Les hiérarchies 2 et 3 sont exactement celles que le port lit déjà (`snapshot.PASSIVE_HIERARCHY`,
`_load_tertiary_abilities`) : la lecture est donc recoupée par du code déjà confronté.

### 1.2 La table ACTIVE — UNE entrée, lue au `.cctor`

`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$GetCustomNormalAttack`
est un `ContainsKey` + `get_Item` sur `statics+0x28`. Ce champ est écrit UNE fois, par
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$.cctor` : `ctor`
du `Dictionary`, **un seul `Add`**, puis l'assignation. Aucun autre `Add` entre les deux.

| clé `ActiveAbilityType` | → valeur `ActiveAbilityType` |
|---|---|
| `1124 PoundThemToDust` | `1126 RogalDorn_NormalAttack` |

**Orientation clé/valeur** — la voie passive l'avait par un second corps
(`IsCustomNormalAttackDerivedFromTriggeredAbility`) ; ce corps n'a pas d'équivalent côté ACTIVE. Elle
se lit ici par la POSITION D'ARGUMENT, dans le foyer de lecture lui-même :
`GetCustomNormalAttack(activeAbilityType)` fait `ContainsKey(dict, <param>)` puis
`get_Item(dict, <param>, out <résultat>)` — le paramètre est donc la CLÉ. Le `.cctor` appelle
`Add(dict, 0x464, 0x466)`, mêmes positions d'argument. Clé = `0x464` = 1124, valeur = `0x466` = 1126.

⚠ Les deux membres sont des `ActiveAbilityType` (la voie passive, elle, mappe
`TriggeredAbilityType → ActiveAbilityType`). Les qualifier est obligatoire : `1124` et `1126` n'ont
aucun sens hors de leur enum.

## 2. Qui l'invoque — chaîne UNIQUE, et elle EXCLUT les Machines

Xrefs, à chaque étage un seul appelant de code :

```
UnitFactory$$Build
  └─ UnitFactory$$AddNormalAttackAbility        (SEUL appelant)
       └─ UnitFactory$$GetCustomNormalAttackTypeFromActive   (SEUL appelant)
            └─ StaticBattleRules.ActiveAbility$$GetCustomNormalAttack   (SEUL appelant de code)
```

**`IdunBattle.Entities.Factories.MachineFactory$$Build` n'appelle JAMAIS
`AddNormalAttackAbility`.** Son corps appelle `UnitFactory$$InitBaseComponent`,
`MachineFactory$$AddConfiguredAbilities` et `UnitFactory$$AddDerivedAbilities` — et c'est tout.

C'est mécanique, pas interprétatif : `AddNormalAttackAbility` a **un seul** xref de code, et c'est
`UnitFactory$$Build`.

## 3. Ce que ça tranche sur le piège annoncé

(à compléter par la mesure)

## 4. Confrontabilité

(à compléter par la mesure)
