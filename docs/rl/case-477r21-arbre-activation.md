# #477-r21 — le BLOC 1 de `System_StartMatch` : l'ARBRE D'ACTIVATION porté

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp, session Frida **1** (chaude, aucun reinject).
Le port reproduit à l'**égalité brute** **363 / 447**, **392 / 491** et **131 / 131** lignes du
bloc 1, sur trois scénarios. **34 / 36 / 12 `Effect_Refresh`** deviennent reproductibles ;
**0** devient AUTONOME, et ce zéro est **mesuré**, pas déduit — § 5.

```powershell
python scripts/python/probe_477r21_activation_tree.py          # live, 3 scenarios
python -m pytest scripts/python/tests/engine/test_477r21_activation_tree_offline.py -q
```

## 1. La RE — du slot `0x51` jusqu'aux quatre actions

La chaîne est fermée de bout en bout, chaque maillon étant une fonction **nommée** :

```
IdunBattle.Operations.StartMatchOperation$$Execute
  processor.<slot 0x51>(GetMatchEntity(state), null, null, EventTriggerType.MatchInit /*0x19*/,
                        default(<ability>))                          -- puis MatchStart /*0x1a*/
-> Core.Services.OperationProcessor$$EvaluateAbilities(actor, caster, target, trigger, ability)
-> IdunBattle.Operations.EvaluateTriggerOperation$$Execute
-> IdunBattle.Operations.EvaluateTriggerOperation$$ExecuteInternal
     foreach (item in AOperation.AbilityAndEffectCache.<slot 3>(trigger))
         EvaluateAbilityOrEffectTrigger(trigger, item, createAbilityEntities, onlyNonAtomic)
-> IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger   <- ouvre Ability_Power
-> IdunBattle.Operations.RefreshEffectsOperation$$GenerateEventGroup        <- ouvre Effect_Refresh
     -> $$StartEventGroup / $$FinishEventGroup
     -> $$AddActivateEffectAction / $$AddDeactivateEffectAction
        $$AddLoseEffectAction     / $$AddReceiveEffectAction
        -> IdunBattle.Core.Services.StreamHelper$$GetRefreshEffectTags       <- le foyer des tags
```

**La surcharge du slot `0x51` est ÉTABLIE, pas devinée.**
`Core.Services.OperationProcessor` porte **six** `EvaluateAbilities` ; le call-site passe cinq
arguments plus le `MethodInfo*`, et **une seule** des six a cette arité —
`EvaluateAbilities(actor, caster, target, trigger, ability)`. Les cinq littéraux se lisent :
l'entité de match, `null`, `null`, l'ordinal du déclencheur, et une struct d'ability
**entièrement nulle** (les quatre mots sont mis à zéro juste avant l'appel).

### Les deux groupes se comportent à l'INVERSE, et c'est le point le plus facile à rater

| | `Group=Ability_Power` | `Group=Effect_Refresh` |
|---|---|---|
| producteur | `EvaluateAbilityTrigger` | `GenerateEventGroup` |
| ordinal | `0x15` | `0x16` |
| `Entity=` | l'**unité** porteuse | l'**entité ECS de l'effet** |
| `Source=` | `((TriggeredAbilityType)Order).ToString()` | `((EffectType)component+0x58).ToString()` |
| ouverture | **inconditionnelle** (dépend du seul porteur) | **`if (eventActions.Count > 0)`** |
| vide observé | **oui** — 2 / 1 / 1 selon le scénario | **jamais** — 0 sur 94 occurrences |

Confondre les deux ferait disparaître deux groupes sur `C1_02` — ou en fabriquerait de vides que
le natif n'écrit pas. C'est l'inverse exact du cran `System_ProcessRemovals` (#477-r19), où le
groupe s'ouvrait pour un contenu qui restait vide.

### `GetRefreshEffectTags` — une branche unique, et une sortie COMMUNE

```
if (stepType == StepType.ReceiveEffect /*0xf*/) {
    if (effectEntity.TryGetComponent<...>(out c) && c != null) Add(0xa4, c.<+0x10>);
    if (effectComponent.<+0x10> != 0)                          Add(0xa8, effectComponent.<+0x10>);
    // <slot 6> de la CONFIG : deux Nullable imbriquees            Add(0xa9) puis Add(0xaa)
    // <slot 7> de la CONFIG                                       Add(0xab)
    if (effectComponent.<+0x5d> != 0)                          Add(0xa5, effectComponent.<+0x64>);
    if (effectComponent.<+0x2c>.HasValue)                      Add(0xac) et Add(0xad);
                                                               Add(0xa7, effectComponent.<+0x68>);
}
                                                               Add(0xae, effectEntity.<Id>);
```

Les onze clés forment un **intervalle contigu sans trou**, `0xa4`..`0xae`, que `TagKey` nomme
`BondEffect_BondedId` .. `Effect_Id` — c'est ce qui rend la lecture vérifiable autrement que par
le flux. Le dernier `Add` est la **sortie commune aux deux branches** (le `else` y saute) : voilà
pourquoi `Effect_Id` est présent sur les **quatre** formes, et pourquoi les trois autres actions
n'en portent **qu'un**.

⚠ **L'asymétrie des quatre actions est structurelle.** `AddReceiveEffectAction` est la **seule**
qui ne calcule pas ses tags — elle les reçoit tout faits de son appelant ; les trois autres
appellent `GetEffectTags`. Uniformiser les quatre est la faute la plus facile, et c'est la
contre-épreuve `tags_activate`.

⚠ **L'ordre des `Add` n'est pas observable** : `StreamCache$$Action` recopie dans un
`SortedDictionary<TagKey,int>`, donc le flux écrit dans l'ordre des **ordinaux**. Le mirror
conserve l'ordre du décompilé pour se relire contre le natif, pas parce qu'il compterait.

### Ce qui est LU et volontairement NON porté

- **La garde `state.<slot 0xb>()`**, identique en tête de `StartEventGroup`, `FinishEventGroup`
  et des quatre `Add*Action` : les six sortent sans rien émettre quand elle est vraie. C'est le
  régime de **simulation** (`OperationProcessor$$SimulateEffects<T>`), jamais atteint sur un
  déroulé réel — le flux témoin porte 86 / 94 actions d'effet, donc la garde y est fausse partout.
- **Les deux gardes en amont d'`EvaluateAbilityTrigger`** :
  `TriggeredAbilityComponent$$GetTimesTriggeredThisPhase(order) >= 0x33` (51 — la branche part
  alors dans `AOperation.get_Logger`, pas dans le flux) et le slot 2 de l'ability. Les deux
  dépendent de l'état ECS.
- **La boucle intermédiaire entre les deux `EvaluateAbilities`** (slot `0x5f` par unité) :
  elle n'écrit rien, et le flux le confirme — **aucune** ligne entre le dernier groupe de
  `MatchInit` et le premier de `MatchStart`.

## 2. Le recoupement qui confirme la lecture du `Source=`

Le groupe `Ability_Power` écrit un **nom**, l'effet qu'il enveloppe écrit un **ordinal** — deux
canaux natifs distincts. Sur `C1_02`, les **13** noms qui apparaissent des deux côtés concordent
**13 / 13** via `engine/entities/triggered_ability_type.py` : `OnOnMeltaDamageAbility` = 1211,
`InescapableAccuracy` = 1115, `TerrifyingAbility` = 98, `StructuralAnalyser` = 1143,
`BlessingsOfKhorne` = 1216, `TeleportStrike` = 1037, `RapidAssault` = 1188,
`TerminatorArmour` = 1142, `PowerTrip` = 1285, `BigTarget` = 1030, `StandVigil` = 1308,
`MartialSuperiority` = 1092, `Parry` = 1085, `CrushingStrike` = 1186. L'accord **confirme** la
lecture du décompilé ; il ne la remplace pas.

## 3. Le résultat, mesuré

| scénario | flux | groupe | BLOC 1 | PORTÉ | HORS | égalité | `Effect_Refresh` repr. / hors |
|---|---:|---:|---:|---:|---:|---|---:|
| `C1_02`, 2 tours | 2 776 l. | 477 l. | 447 l. | **363** (30 s.-a.) | 84 (4) | **363 / 363** | **34** / 6 |
| `MC1_67`, 2 tours | 2 930 l. | 521 l. | 491 l. | **392** (31 s.-a.) | 99 (4) | **392 / 392** | **36** / 6 |
| `MC1_67`, **roster 2v2 crafté** | 1 169 l. | 142 l. | 131 l. | **131** (13 s.-a.) | **0** | **131 / 131** | **12** / 0 |

Couverture du groupe `System_StartMatch` entier : **3 / 477 → 366 / 477** et **3 / 521 → 395 / 521**
(**134 / 142** sur le roster crafté). Les deux sommes sont confrontées à chaque run — découpe
(`1 + 1 + bloc1 + queue + 1 == total`) **et** partition (`portées + hors == bloc1`), OK sur 3 / 3.

**Le scénario crafté porte la généralisation, et sur l'axe qui compte ici** : il fait varier le
contenu d'un facteur **3,4** (447 → 131 lignes, 30 → 13 sous-arbres) et **annule** les lignes hors
périmètre (84 → 0). C'est le seul des trois où le bloc 1 est porté **intégralement**, ce qui
montre que les 84 / 99 lignes écartées ailleurs sont une propriété du **roster**, pas une limite
structurelle du port.

### Ce qui reste HORS PÉRIMÈTRE, énuméré

Un sous-arbre part hors périmètre **en entier** dès qu'il porte une forme non portée — jamais
amputé ligne à ligne, ce qui laisserait croire que le reste est comparable. Les **4** sous-arbres
écartés sur chacun des deux boards par défaut se ventilent en **trois** motifs :

| motif | occ. |
|---|---:|
| `Action=ChangeStats` + les 4 `Tag=UnitStats_Movement_Modification*` / `UnitStats_Transformed` | 2 |
| `Action=ChangeStats` + les 4 `Tag=UnitStats_FixedArmor_Modification*` / `UnitStats_Transformed` | 1 |
| `Action=ChangeAbility` + `Action=ChangeStats` + les 6 `Tag=UnitStats_ActiveAbility_*` + `UnitStats_RemoveActiveAbility` | 1 |

Ces lignes sortent d'`Effect.ApplyModification` et de la transformation d'ability, pas de
`RefreshEffectsOperation` — résidu **#477-r21-r1**.

## 4. Ce qui est MESURÉ, et ce qui est COPIÉ

Le port émet une **forme** à partir de **données**. Les données viennent du flux natif : elles
comptent en borne (c) **sans rien prouver**. Ce qui est mesuré est ce que le port **dérive** —
et chaque dérivation publie son **compte d'exercice**, parce qu'une dérivation qu'aucune donnée
n'exerce ne prouve rien quel que soit le verdict :

| | dérivation | `C1_02` | `MC1_67` | 2v2 |
|---|---|---:|---:|---:|
| (D1) | `Tag=Effect_Id` reconstruit sur les 4 formes, depuis le SEUL id de l'entête de groupe | 70 act. | 76 | 24 |
| (D2) | ordre des tags : blocs où l'ordre des ordinaux **diffère** de l'alphabétique | 36 | 40 | 12 |
| (D3) | placement porteur / cible : sous-arbres où les deux **divergent** | 3 | 4 | 1 |
| (D4) | ouverture conditionnelle : `Ability_Power` **vides** vs pleins ; `Effect_Refresh` vides | 2 / 23 ; **0** | 1 / 25 ; **0** | 1 / 12 ; **0** |
| (D5) | couverture des mirrors : noms `EffectType` / `TriggeredAbilityType` | 24 / 16 | 24 / 16 | 9 / 9 |

⚠ **(D2) est mesuré, mais pas PAR cette tranche** : le tri vit dans `StreamCache$$Action`, porté
et confronté par #477-r15a. Aucune mutation ne le vise, **parce qu'aucune ne pourrait mordre
dessus** — le writer re-trie ses clés quel qu'en soit le conteneur.

**Copié, et déclaré en borne (c)** : la sélection et l'ordre des sous-arbres (le cache
`AbilityAndEffectCache`, #477-r21-r2) ; les identifiants d'entité ECS (33 / 35 / 12 valeurs
distinctes d'effet, #477-r21-r3) ; les valeurs de chaque tag et leur traduction en champs
d'`EffectSetup` (table `TAG_VERS_CHAMP` du probe) ; les lignes hors périmètre.
**`Effect_Id` n'est PAS dans cette table** — c'est ce qui fait de (D1) une mesure.

## 5. `Effect_Refresh` — DEUX chiffres, et ils ne disent pas la même chose

#477-r19 avait annoncé `System_StartMatch` comme débloqueur (42 / 147) ; #477-r20 l'a **réfuté par
la mesure** (0 / 42). Cette tranche ne réintroduit pas l'inférence — elle **mesure** :

> **REPRODUITS** à l'égalité brute, données fournies : **34 / 40**, **36 / 42**, **12 / 12**.
> **AUTONOMES**, sans aucune entrée copiée du flux : **0 / 40**, **0 / 42**, **0 / 12**.

Le second chiffre est **mesuré, pas déduit du premier**. Ce qui manque pour le lever est nommé et
séparé : la **sélection** (quels effets s'activent, sur quelles unités, dans quel ordre —
#477-r21-r2) et l'**allocation ECS** des identifiants d'effet (#477-r21-r3). Ni l'un ni l'autre
n'est une face stream : les deux vivent dans l'état.

⚠ Le contraste avec #477-r20 est le résultat de la tranche : la racine était **nécessaire et non
suffisante**, et le chemin complet l'est désormais — mais un chemin émis ne suffit pas non plus
tant que les **valeurs** qu'il porte viennent de l'oracle.

## 6. Les 8 contre-épreuves rougissent, chacune après avoir MORDU

`effect_id`, `effect_source`, `ability_source`, `placement`, `step_activate`, `tags_activate`,
`sans_source_id`, `ouverture_vide` — **8 / 8 sur les 3 scénarios**, `a_morde` séparé du verdict.

⚠ **Deux mutations ont été écrites puis RETIRÉES parce qu'inertes par construction**, et c'est le
cran qui a sauvé les deux crans précédents :

- **le tri des tags** — `StreamCache$$Action` re-trie ses clés quel qu'en soit le conteneur, donc
  la mutation n'aurait **jamais** mordu. Elle aurait mesuré #477-r15a, pas ce port ;
- **forcer un corps sur un `Ability_Power` déjà vide** — elle n'ajoute aucune ligne, donc aucun
  verdict qu'elle rendrait n'aurait de sens.

⚠ **`placement` est INERTE sur un sous-arbre où porteur et cible coïncident**, c'est-à-dire sur la
majorité. C'est pourquoi le compte (D3) est publié, et pourquoi la garde offline fige **les deux
côtés** : elle mord sur l'aura (`StructuralAnalyserDmgBoost`, porteur 51 vs cibles 49/55/53), elle
ne mord pas sur le cas nominal.

## 7. Ce qui n'est PAS couvert

- **Les 84 / 99 lignes hors périmètre** (§ 3) → **#477-r21-r1**.
- **La SÉLECTION et l'ORDRE** des sous-arbres → **#477-r21-r2**.
- **L'ALLOCATION ECS** des identifiants d'effet → **#477-r21-r3**.
- **La queue du groupe** (27 lignes : `Action=PrepareTurn` + le `Group=StartTurn` complet de
  `ContinueTurnPhase`) — bloc 2 de #477-r20, hors de cette tranche.
- **`Effect_State_Level` / `Effect_State_VariableMultiplierPercentage`** : **LUS** (le décompilé
  teste `HasValue` une fois puis émet les deux tags), **jamais confrontés** — aucune occurrence
  sur les trois flux. Le port les rend exprimables plutôt que de les taire.
- **`Effect_SourceActiveAbility`** et **`BondEffect_BondedId`** : lus, aucune occurrence.
- **La garde de simulation** `state.<slot 0xb>()` et les deux gardes de déclenchement (§ 1) :
  lues, non portées, non atteignables par un émetteur de replay.
- **Les trois sources simultanées** : le décompilé n'impose pas l'exclusivité (trois `HasValue`
  indépendants), le flux n'en montre jamais deux. Le port ne transforme pas cette observation en
  règle — le test offline le fige.

## Résidus

- **#477-r21-r1** — **les formes `ChangeStats` / `ChangeAbility` du bloc 1** : 84 / 99 / 0 lignes,
  4 sous-arbres par board, trois motifs nommés (§ 3). Elles sortent d'`Effect.ApplyModification`
  (les `UnitStats_*_Modification` + `UnitStats_Transformed`) et de la transformation d'ability
  (`TwistedScience` : `UnitStats_RemoveActiveAbility` puis un `Action=ChangeAbility` complet).
  RETOURNEMENT **déjà mesuré** : sur le roster 2v2 ce résidu vaut **0 ligne** — il est une
  propriété du roster, pas une limite du port.
- **#477-r21-r2** — **la SÉLECTION et l'ORDRE** : quels effets et quelles abilities déclenchées
  s'activent, sur quelles unités, dans quel ordre. C'est `AOperation.AbilityAndEffectCache.<slot 3>`
  parcouru par `EvaluateTriggerOperation$$ExecuteInternal`, plus les gardes de
  `RefreshEffectsOperation` (`ShouldBeActive`, `GetTargetsToAdd`, `GetTargetsToRemove`,
  `UpdateEffectTargets`) et les deux d'`EvaluateAbilityTrigger` (§ 1). C'est le plus gros des
  trois, et le seul qui ne soit pas une face stream.
- **#477-r21-r3** — **l'ALLOCATION ECS des entités d'effet** : 33 / 35 / 12 identifiants distincts
  par scénario (69…113 sur `C1_02`). #477-r16 n'a porté que le versant unités / tuiles. C'est le
  verrou qui rend `Effect_Refresh` non AUTONOME même quand tout son chemin est émis (§ 5).
