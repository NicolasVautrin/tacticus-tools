# #477-r21-r1 — les formes `ChangeStats` / `ChangeAbility` du bloc 1

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp, session Frida **1** (chaude, aucun reinject).
Le bloc 1 de `System_StartMatch` est désormais reproduit **INTÉGRALEMENT**, à l'**égalité brute**,
sur les quatre scénarios : **447 / 447**, **491 / 491**, **131 / 131**, **199 / 199**. Les
**84 / 99** lignes écartées par #477-r21 sont entrées ; il n'en reste **0**.

```powershell
python scripts/python/probe_477r21_activation_tree.py       # live, 4 scenarios
python -m pytest scripts/python/tests/engine/test_477r21r1_formes_changestats_offline.py -q
```

## 1. La RE — trois opérations natives, aucune n'est `RefreshEffectsOperation`

Le résidu nommait « `Effect.ApplyModification` et la transformation d'ability ». La lecture en
trouve **trois** artefacts, et le premier n'est atteint qu'au bout d'une chaîne :

```
IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets
  -> la DERNIERE closure de la `List<Action> eventActions`
-> IdunBattle.Operations.RefreshEffectsOperation$$ApplyEffectsForTargets
     foreach (target in targetsToAdd) effect.<slot 0xe>(owner, target, effectEntity);
-> IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification
     IdunBattleLogic.Entities.DSLBehaviors$$ChangeStat(targets, Stat(<statType>,
         StatPart.Modification /*5*/), DSLFormulas$$Direct(...), DSLSelectors$$Entity(...))
-> IdunBattle.Operations.TransformUnitOperation$$Execute(unit, statModifiers, isHidden)
     Events.Action(StepType.ChangeStats /*0xc*/, unit.<Id>, tags)

IdunBattleLogic.Entities.Abilities.Triggered.Loki.TwistedScienceAbility$$CreateBehaviour
     DSLBehaviors$$RemoveActiveAbility(selectors.Caster, ActiveAbilityType 0x12)
   & DSLBehaviors$$AddActiveAbility(selectors.Caster, ActiveAbilityType 0x48f, abilityState)
-> IdunBattle.Operations.RemoveActiveAbilityOperation$$Execute -> Action(ChangeStats)
-> IdunBattle.Operations.AddActiveAbilityOperation$$Execute    -> Action(ChangeAbility /*0xd*/)
```

⚠ **POURQUOI LA LIGNE TOMBE *DANS* LE `Group=Effect_Refresh`, ET C'EST LU.**
`ApplyEffectsForTargets` émet **immédiatement**. Ce qui la place dans le groupe, c'est que
`UpdateEffectTargets` ne l'appelle pas directement : elle en fait la **dernière entrée** d'une
`List<Action>` **différée**, invoquée par `GenerateEventGroup` entre le `StartGroup` et le
`FinishGroup`. Les six entrées, dans l'ordre du décompilé :

| # | entrée | garde |
|---|---|---|
| 1 | `ActivateEffect` | `currentTargets.Count == 0 && desiredTargets.Count > 0` |
| 2 | `RemoveTargetsFromEffect` → les `LoseEffect` | — |
| 3 | `AddTargetsToEffect` → les `ReceiveEffect` | — |
| 4 | `DeactivateEffect` | `currentTargets.Count > 0 && desiredTargets.Count == 0` |
| 5 | `RevertEffectsForTargets` → `ReverseModification` | `targetsToRemove.Count > 0` |
| 6 | `ApplyEffectsForTargets` → **ce port** | `targetsToAdd.Count > 0` |

Le `ChangeStats` est donc **toujours** après les `ReceiveEffect` du même groupe — dérivé, pas
observé. `UpdateEffectTargets` elle-même reste **hors périmètre** (elle est nommément dans
#477-r21-r2) ; ce tableau est le renseignement que cette tranche lui laisse.

### Les deux tables de configuration, lues verbatim

Le `switch` d'`AddTagsForModifiable` / `AddTagsForFillUp` porte sur le **`StatPart`**, pas sur le
`StatType` — et son `default` construit un `System.NotImplementedException` qu'il **LÈVE**. Les
clés, elles, viennent de deux dictionnaires :

- **`MOD_STAT_TRANSFORM_CONFIG`** — 15 entrées, champ **statique** écrit par
  `IdunBattle.Operations.TransformUnitOperation$$.cctor` ;
- **`FILL_STAT_TRANSFORM_CONFIG`** — **une** entrée (`StatType.Health`), reconstruite à chaque
  instance par `IdunBattle.Operations.TransformUnitOperation$$.ctor`. L'asymétrie est native.

L'**ordre des champs** vient de la signature des ctors dans `frida/methods.tsv`
(`ModStatTransformConfig..ctor(currentKey, modificationKey, modificationChangeKey,
modificationEntityKey, overrideKey, overrideEntityKey, overrideIsModifiableKey,
eventTriggerType)`), et il est confirmé par **deux canaux indépendants** :

1. le **nom** des `TagKey` obtenus (`StatType.Attack` → `UnitStats_Attack`, `..._Modification`,
   `..._Modification_Change`, `..._Modification_Entity`, `..._Override`, `..._Override_Entity`,
   `..._Override_IsModifiable`) ;
2. le **nom** de l'`EventTriggerType`, présent sur exactement **trois** entrées et qui nomme sa
   stat à chaque fois : `Attack` → `AttackChanged` (55), `BlockDamage` → `BlockDamageChanged`
   (56), `Health` → `HealthChanged` (30). Aucune erreur de décalage d'offset ne produirait cela.

⚠ **L'ORDRE DES ORDINAUX N'EST PAS L'ORDRE DES CHAMPS — c'est ce qui rend la table NÉCESSAIRE.**
`UnitStats_Movement_*` numérote `Modification`(48), `_Entity`(49), `_Change`(50) ;
`UnitStats_MaxHealth_*` numérote `Modification`(10), `_Change`(11), `_Entity`(12). Les deux
familles **inversent** leurs deux derniers. Un port qui dériverait les clés par arithmétique
serait juste sur l'une et faux sur l'autre.

⚠ **SEPT ENTRÉES ONT `currentKey == modificationKey`**, et le `.cctor` l'écrit littéralement
(`0x4f0000004f`, `0x5200000052`, …) : ce sont les stats « modification seule », dont le flux ne
rapporte jamais la valeur courante. Même constat que le registre de `engine/streams/conformance.py`.

### Les gardes et asymétries que le port PRÉSERVE

- **`AddTagIfImplemented` refuse la clé `0`** (`TagKey.UnitStats_Unimplemented`) : c'est LE
  mécanisme « non implémenté » du natif, et c'est ce que les configs écrivent partout où une stat
  n'expose pas la grandeur. Et un **doublon ne réécrit pas** — le natif part dans
  `AOperation$$get_Logger` et laisse le dictionnaire intact : la **première** valeur gagne.
- ⚠ **`is_modifiable` est testé dans les DEUX SENS** : `!= 0` dans `AddTagsForModifiable`, `== 0`
  dans `AddTagsForFillUp`, à quelques centaines d'octets l'une de l'autre. L'uniformiser serait un
  choix, donc une invention. Le port porte les deux verbatim, la garde offline les fige.
- **`AddModificationTags` existe en DEUX surcharges** au corps strictement identique : seuls les
  offsets de `config` diffèrent (`+0x04/+0x08/+0x0c` vs `+0x08/+0x0c/+0x10`), parce que
  `FillStatTransformConfig` porte un champ de plus en tête. Les fusionner ferait perdre la trace
  de cette raison.
- **`UnitStats_Transformed` est INCONDITIONNEL** : posé avant la boucle, sans garde. C'est
  l'invariant qui distingue cette `Action=ChangeStats` des deux autres du flux.
- **Le troisième étage de l'aiguillage** (`StatType.ActiveAbilityLevel`, hors des deux tables)
  n'utilise **pas** `AddTagIfImplemented` : il appelle `Dictionary$$Add` directement, qui **lève**
  sur doublon. Le port refuse au lieu d'écraser.

⚠ **LES SIX TAGS D'`AddActiveAbilityOperation` NE SONT PAS `GetFullStateUpdateTags(activeAbility)`,
et les confondre est SILENCIEUX.** L'opération **inline** son propre dictionnaire ; la surcharge
d'`IdunBattle.Entities.UnitExtensions` (portée par `unit_extensions.py`) écrit les **mêmes six**
plus **deux** conditionnels (`UnitStats_TriggeredAbility_AmmoCost`, `_EnoughAmmo`) sous
`AmmoCost.HasValue`. Sur une ability sans munitions les deux fonctions **coïncident** — la faute
ne se verrait que sur une Machine of War. Le test l'oppose : il exige d'abord la coïncidence, puis
la divergence.

### Le recoupement qui confirme `TwistedScience`

`TwistedScienceAbility$$CreateBehaviour` passe `0x12` à `RemoveActiveAbility` et `0x48f` à
`AddActiveAbility` — soit exactement les `18` et `1167` que le flux écrit. Deux canaux natifs
distincts qui concordent ; l'accord **confirme** la lecture, il ne la remplace pas.

## 2. Où vit le port, et pourquoi pas dans `refresh_effects.py`

Deux modules **neufs**, un par famille d'artefact natif, comme `refresh_effects.py` ←
`RefreshEffectsOperation` et `evaluate_trigger.py` ← `EvaluateTriggerOperation` :

- **`engine/streams/transform_unit.py`** — `TransformUnitOperation` (les deux tables, les quatre
  fonctions de tags, `Execute` face stream) ;
- **`engine/streams/active_ability_ops.py`** — `RemoveActiveAbilityOperation` et
  `AddActiveAbilityOperation`.

**Aucune ligne de `refresh_effects.py` ni d'`evaluate_trigger.py` n'a été touchée**, et ce n'est
pas une précaution : le point de couture **existait déjà**. `generate_event_group(events,
event_actions, effect)` prend une **séquence de callables** parce que la `List<Action>` native en
est une — sa docstring annonçait même ce raccord. Les `ChangeStats` de modification y entrent comme
des callables de plus ; les deux actions de `TwistedScience` entrent par le `corps` d'
`evaluate_ability_trigger`. Ces deux modules restent donc **entièrement disponibles** pour
#477-r21-r2. `engine/streams/__init__.py` n'a pas bougé non plus : comme `refresh_effects` et
`game_setup`, ces émetteurs s'importent par leur module.

## 3. Le chiffre, avant / après

| scénario | BLOC 1 | AVANT porté / écarté | APRÈS porté / écarté | égalité |
|---|---:|---:|---:|---|
| `C1_02`, 2 tours | 447 l. | 363 / **84** (4 s.-a.) | **447 / 0** | **447 / 447** |
| `MC1_67`, 2 tours | 491 l. | 392 / **99** (4 s.-a.) | **491 / 0** | **491 / 491** |
| `MC1_67`, roster 2v2 | 131 l. | 131 / 0 | 131 / 0 | **131 / 131** |
| `C1_02`, **roster r1 crafté** | 199 l. | — (scénario neuf) | **199 / 0** | **199 / 199** |

`Effect_Refresh` reproduits : **34 → 40**, **36 → 42**, **12**, **18**. La couverture du groupe
`System_StartMatch` entier passe à **450 / 477** et **494 / 521** (le reste étant la queue du
bloc 2, portée par #477-r22). Découpe et partition sont confrontées à chaque run — **4 / 4 OK**.

**Aucun sous-arbre n'est partiellement reproduit** : la règle du probe (écarter EN ENTIER plutôt
qu'amputer) est inchangée, et le compte d'écartés est passé à zéro par entrée de forme, pas par
relâchement du filtre.

### Le scénario crafté neuf, et ce qu'il LÈVE

`C1_02-r1` (`custoVexilusPraetor,bloodIntercessor` vs `genesBiophagus,astraBullgryn`) est choisi
**par porteur**, via `unit_map.py find --ability` : `StandVigil` (1308) → `UnitStats_FixedArmor_*`,
`RapidAssault` (1188) → `UnitStats_Movement_*`, `TwistedScience` → Remove + Add d'ability. Il
existe parce que le roster 2v2 hérité **ne prouve rien** sur cette tranche : il porte **zéro**
`ChangeStats` / `ChangeAbility`, donc les cinq mutations neuves y ont un domaine **nul**.

Il **lève un régime dégénéré** que les deux boards par défaut ne pouvaient pas séparer :
`_Modification` et `_Modification_Change` y sont **égaux sur 3 / 3 et 4 / 4** couples (un seul
modificateur par stat), alors qu'il les **discrimine 1 / 3**. Sans lui, l'égalité brute n'aurait
jamais départagé ces deux clés.

## 4. Ce que le port DÉRIVE — quatre mesures de plus, chacune avec son compte d'exercice

| | dérivation | `C1_02` | `MC1_67` | 2v2 | `C1_02-r1` |
|---|---|---:|---:|---:|---:|
| (D6) | `Tag=UnitStats_Transformed` posé **sans garde** | 3 | 4 | **0** | 3 |
| (D7) | entité du modificateur **reconstruite depuis l'entête du groupe** ; le tag `..._Modification_Entity` est lu pour rien | 3 | 4 | **0** | 3 |
| (D8) | clés de tag **dérivées de la table** `StatType -> config` | `Movement`, `FixedArmor` | idem | — | idem |
| (D9) | aiguillage des 3 producteurs (retrait / ajout / transformation) | 1 / 1 / 3 | 1 / 1 / 4 | 0 / 0 / 0 | 1 / 1 / 3 |

(D7) est le **jumeau exact de (D1)** : un seul canal (l'entête `Group=Effect_Refresh Entity=`)
alimente une valeur que le natif réécrit dans un tag. (D9) repose sur deux invariants **lus** : un
retrait n'écrit qu'un tag, une transformation écrit toujours `UnitStats_Transformed`, et seul
l'ajout émet un `StepType.ChangeAbility`.

**Copié, déclaré en borne (c)** : la table inverse `TagKey -> (StatType, rôle)` du probe — pendant
exact de `TAG_VERS_CHAMP`. Le rôle `entity` n'y est **jamais consommé** (c'est (D7)).

## 5. Les contre-épreuves — et le DOMAINE, qui sépare deux échecs qui se lisaient pareil

Cinq mutations neuves : `stat_table` (la config d'un **autre** `StatType`), `sans_transformed`,
`modifier_entity`, `remove_step` (le retrait émis en `ChangeAbility`), `ability_tags_ammo`
(`GetFullStateUpdateTags` à la place de l'inline). **13 / 13 mutations** mordent et rougissent sur
`C1_02`, `MC1_67` et `C1_02-r1`.

⚠ **CHAQUE MUTATION PORTE DÉSORMAIS SON DOMAINE, calculé DEPUIS LES DONNÉES.** Sans lui, deux
échecs différents se lisent pareil :

- **inerte par CONSTRUCTION** (domaine > 0, ne mord pas) → **ROUGE** : elle ne mesure rien, quel
  que soit son verdict. C'est ce qui a fait retirer deux mutations à #477-r21 ;
- **inerte par ABSENCE DE DONNÉE** (domaine == 0) → **ATTENTION publiée** : elle n'a rien pu
  mesurer *ici*, ce qui n'accuse ni le port ni elle.

Le second cas est **mesuré**, pas hypothétique : sur `MC1_67-2v2`, les cinq mutations neuves ont
un domaine **nul**, et le probe le dit au lieu de rendre un `OK` creux ou un rouge injuste. Un
troisième garde ferme la boucle : une mutation dont le domaine est nul sur **tous** les scénarios
est un **ROUGE du corpus** — rien ne la confronte.

Le même cran vaut offline : `test_477r21_activation_tree_offline.py` paramètre sa boucle de
mutations **sur le domaine**, et un test séparé fige NOMMÉMENT les cinq qui n'y sont pas — sans
quoi retirer un fragment du corpus ferait disparaître des cas sans que rien ne le dise (#455-r3).

## 6. Ce qui n'est PAS couvert

- **13 `StatType` sur 15** ne sont pas exercés : seuls `Movement` et `FixedArmor` apparaissent sur
  les quatre flux. Leurs clés sont **lues** (et figées par le test), jamais **confrontées**.
- **Les branches `Override` / `RemoveOverride` / `ResetModification` / `Initial`** de
  `TransformUnitOperation` : portées verbatim, **zéro occurrence** sur les quatre flux. Elles
  **LÈVENT** si l'appelant ne fournit pas la lecture ECS qu'elles demandent — jamais un `0`
  silencieux.
- **La seconde boucle d'`Execute`** (une ligne `ChangeStats` par modification existante, sur
  `StatPart.Initial`) : portée, non confrontée, et refuse sans son substrat.
- **`isHidden`** (`UnitStats_Modification_Hidden`) : lu, aucune occurrence.
- **Les gardes d'état ECS** — `Contains` de `RemoveActiveAbilityOperation` et
  d'`AddActiveAbilityOperation`, `IsRegularAttack` + `<slot 0x2a>`, le `<slot 0x51>` de
  re-déclenchement et `AddDerivedAbilities` : lus, non portés. Sur le seul cas confronté, le
  groupe se ferme immédiatement après la ligne — c'est une **observation**, pas une règle.
- **`ClampModifiers`, `ApplyStatModifiers` et le re-déclenchement par `OrderedSet`** de
  `TransformUnitOperation$$Execute` : hors de la face stream, comme les gardes de
  `RefreshEffectsOperation` le sont de `refresh_effects.py`.
- **`Effect_Refresh` AUTONOMES : 0 / 0 / 0 / 0** — inchangé, et c'est attendu : cette tranche
  ajoute des formes, pas de l'autonomie. Le verrou reste **#477-r21-r2**.

## 7. Le raccord avec le volet A de #477-r21-r2 — ouvert, et nommé des DEUX côtés

Le volet A a été mergé pendant cette tranche (rebase, puis re-jeu complet : 161 tests offline
verts, probe live re-joué). Il porte `update_effect_targets` côté **décision**
(`engine/runner/operations/refresh_effects.py`) et rend déjà le **plan complet dans l'ordre
natif** — `RefreshAction(ACTION_REVERT, …)` et `RefreshAction(ACTION_APPLY, …)` compris. En face,
`engine/streams/refresh_effects.bind_refresh_actions` les **ignore explicitement** et renvoie
à #477-r21-r1.

Il manque donc **une seule chose**, et ce n'est pas la forme : que `bind_refresh_actions`
traduise `ACTION_APPLY` en un `transform_unit(events, <cible>, <modificateurs>)`. **Ce qui bloque
est la DONNÉE** — les `StatModifierSetup` demandent des lectures `UnitExtensions$$GetStat` que la
couche décision ne produit pas encore. C'est le **même manque que #477-r26**, pas un trou de
port. `ACTION_REVERT`, lui, sort d'un artefact que cette tranche **n'a pas lu**
(`RevertEffectsForTargets` → le slot d'interface `IEffect+0xf`, `ReverseModification`) et n'a
**aucune occurrence** sur les quatre flux témoins.

⚠ **Ce raccord n'a PAS été écrit ici volontairement** : `engine/streams/refresh_effects.py` et
`engine/runner/operations/refresh_effects.py` étaient la zone sérialisée du volet A. Les deux
côtés portent désormais le renvoi, de sorte que le manque est visible depuis l'un comme depuis
l'autre.

## Résidus

Aucun résidu neuf. Ce que cette tranche laisse à **#477-r21-r2**, en plus de ce qui était déjà
nommé : l'**ORDRE des six blocs d'`eventActions`** que fixe
`IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets` (§ 1) — le volet A le porte
côté décision, le probe le **copie** encore côté émission, et c'est le § 7 qui dit ce qui reste.
