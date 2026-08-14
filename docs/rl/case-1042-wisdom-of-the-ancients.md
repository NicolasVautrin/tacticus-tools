# #1042 — `WisdomOfTheAncients` : l'arbre est LU et CONFRONTÉ, la moitié que l'i2 décrit est INERTE

**Verdict** : la mythique de `ultraDreadnought` (« Galatian ») est mirrorée au décompilé et exercée
étage par étage en live, avec **cinq contre-épreuves qui séparent**. Elle **n'entre pas au port** :
les **trois** étages de son sélecteur sont `UnitsWithRarity(·, Mythic)` et le port n'a **aucun canal
de rareté** — résidu `#1042-r1`, même mur que `#1024-r1` / `#1025-r1` / `#1035-r2` / `#1036-r1`.

Ce que cette fiche ajoute aux précédentes : **le `ConditionalSelector(IsMachine(Owner))` prend
TOUJOURS la même branche sur le seul porteur de jeu**, et c'est mesuré des deux côtés. La branche
`ifFalse` — celle qui porte le « adjacent to **Galatian** » de l'i2 — n'a été atteinte qu'en
**greffant** l'ability sur un porteur ON-BOARD.

---

## 1. Ce que le décompilé écrit

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WisdomOfTheAncientsAbility` — parent LU dans
`data/symbols/rnca9r7q6c/frida/classes.tsv` : `IdunBattle.Entities.Abilities.BaseTriggeredAbility`
(donc PAS `AOwnerEffectTriggeredAbility`), et elle **déclare** ses deux méthodes.

```
$$CreateTrigger   = DSLTriggers.OnOwnerSpecificAbilityInit(0x5ab = 1451
                                                  TriggeredAbilityType.WisdomOfTheAncients)
$$CreateBehaviour = DSLBehaviors.AddEffect(0x5a5 = 1445 EffectType.WisdomOfTheAncients_DamageReduction,
                                           <BaseTriggeredAbility$$get_AbilityStateReference>,
                                           source  = Owner@<DSLSelectors+0x30>,
                                           targets = Owner@<DSLSelectors+0x30>,
                                           options = <Nullable ZERO-initialisé>)
```

Owner-effect **permanent** posé à l'init, par un corps propre et **sans** le `If(CreateCondition)`
que la base interpose — même forme que `CabalOfSorcerers` (#1036). L'appariement `1451 -> 1445` est
**lu au call-site**. Deux surcharges tranchées par la **cible du `call`**, jamais par la forme du
pseudo-C : `AddEffect` est celle à `options:Nullable<AddEffectBehaviourOptions>`, et
`AmountIsGreaterThanZero` (§suivant) celle à `amount:IdunBattle.DSL.ITargetsSelector`.

`IdunBattle.Entities.Effects.Loki.WisdomOfTheAncients_DamageReductionEffect` — parent `BaseEffect`.
`$$.ctor` = `BaseEffect( AbilityOrEffect(TriggeredAbilityType 1451), hasAutomaticActivation = 1 )` ;
l'overload d'`IdunBattle.Core.AbilityOrEffect$$op_Implicit` réellement appelée est celle dont le
**corps** écrit `set_TriggeredAbility`.
`$$CreateActiveCondition` est le corps **dédupliqué** `return <DSLTriggers+0x70>` (le `YesTrigger`
partagé, refcount 182 — celui-là même que `IconOfObstinacy_ExtraArmour`) : l'effet est **toujours
actif**, donc toujours publié par `decisionView.effects`.

### Le sélecteur — trois étages de rareté, et un aiguillage

```
ValidCharacter(x) = UnitsWithRarity(x, idun.meta.Rarity.Mythic = 5,
                                    UnitSelectionType.OnlyAliveAndTargetable = 3)

A = ValidCharacter( AdjacentFriends(Owner@<DSLSelectors+0x30>, unique = true, 3) )
B = ValidCharacter( Friends(of = Owner@<+0x30>, entities = AllUnits@<DSLSelectors+0x20>, 3) )
F = Filter( B, AmountIsGreaterThanZero(
                   UnitsWithTrait( ValidCharacter( AdjacentFriends(
                                       ActiveTarget@<DSLSelectors+0x68>, unique = true, 3) ),
                                   UnitTrait.Hero = 0x10, 3 ) ) )

return ConditionalSelector( IsMachine(Owner@<+0x30>), ifTrue = F, ifFalse = Unique(A + F) )
```

- `ValidCharacter` est une **méthode déclarée** de l'effet (`$$ValidCharacter`), que
  `$$CreateTargetSelector` **inline trois fois** — d'où les trois `UnitsWithRarity` du pseudo-C.
- Les **deux** `AdjacentFriends` visent la surcharge `(unit, unique, selectionType)` — tranchée par
  les **xrefs entrantes** des deux corps homonymes, pas par la forme du call-site.
- `Filter(entities, filter)` = `DSLSelectors$$FromTrigger(entities, filter, 0)` : il lie chaque
  élément de `B` à `ActiveTarget@<DSLSelectors+0x68>`, que le prédicat relit.
- L'**ordre** des deux branches est lu : `DSLSelectors$$ConditionalSelector(abilityTrigger,
  selectorTrue, selectorFalse)` transmet ses arguments dans cet ordre au ctor du sélecteur.
- `IsMachineTrigger$$ShouldTrigger` prend la **première** entité du sélecteur et rend
  `IdunBattle.Entities.EntityExtensions$$IsMachine(entity)` =
  `entity.GetEntityType() == IdunBattle.Entities.Enum.EntityType.Machine = 6` (enum **qualifié**).
- `UnitsWithRaritySelector$$Select` compare `GetBaseUnitComponent(e)->[+0x74]` au littéral par
  **égalité** (jamais `>=`), et `Friends` ne retire **pas** le sujet
  (`UnitsByTeamSelector$$CountOrAdd` garde toute entité dont `UnitExtensions$$IsFriend(unit, other)`
  égale son flag, et `IsFriend(u, u)` est vrai).

En clair : **F** = « amis Mythiques du porteur ayant au moins un ami Mythique portant le trait
`Hero` en adjacence » ; **A** = « amis Mythiques adjacents au PORTEUR ».

### Le malus

```
$$CreateEffectDamageMalusForDefense
  = Nullable<EffectBonus>( EffectBonus.ForPercentDecrease(
        get_OwnerIsTarget,
        ConfigVar(AbilityVariableType.dmgReductionPct = 0x46, GetAbilityState(effet), <effet+0x60>) ) )
```

Corps **inline** (aucun `call` vers `ForPercentDecrease`) : le canal se lit à la **disposition des
champs** — montant écrit à `+0x08`, le slot de `ForPercentIncrease`/`ForPercentDecrease`, distinct
de `ForAddition` (`+0x10`) et `ForSubtraction` (`+0x18`). **Aucun gate de rareté ici** : tout le
ciblage vit dans le sélecteur.

`dmgReductionPct` = `[10, 13, 16, 20]` (4 paliers ; `variablesAffectedByRarityBonus` =
`["dmgReductionPct"]`, mais la voie TERTIAIRE passe `mult = 100`, donc pas de scaling).

i2 `Abilities/WisdomOfTheAncients_CurrentLevelDescription` :
> Friendly **Mythic characters** take **-{dmgReductionPct}% Damage** if they are adjacent to
> **Galatian** or a friendly Mythic character.

Les deux membres de la phrase sont **A** et **F**. Or **A n'est que dans la branche `ifFalse`**.

---

## 2. Ce que le live a rendu — six bras, cinq séparations

`probe_1042_wisdom_of_the_ancients_live.py`. Board `MC1_67` (7×9, tout Grass sauf 8 tuiles LUES au
dump), seed 777, niveau 4 (`dmgReductionPct` = 20), géométrie **pilotée** par `--place` /
`--a-place` et **assertionnée** avant tout build.

L'aura est montée du côté **ADVERSE** : `decisionView.attackPlans` ne publie que MES unités, donc
la prédiction native **contre** un défenseur affecté ne s'obtient qu'en plaçant le porteur en face.

```
team 2 (l'aura)   P1 adeptRetributor (1,1) - P2 adeptCanoness (2,1) - P3 adeptHospitaller (3,1)
                  H  astraCreed (5,7) - X astraBullgryn (6,7)      d(P·,H/X) >= 7 ; d(P1,P3) = 2
team 1 (moi)      A1 blackTerminator (2,2) adj. P2 ; A2 bloodDeathCompany (6,6) adj. X ;
                  A3 bloodSanguinary (0,6) hors de tout
```

`H` est forcé à `Rarity = 4` dans **tous** les bras (`--unit-stat`, écrit APRÈS la normalisation) :
c'est ce qui fait de `X` un discriminant — `X` n'a qu'un voisin ami, `H`, non-Mythique, donc `X`
n'est **jamais** dans `F` et n'entre dans le set que par `A`.

| bras | `targetIds` de 1445 | P1 | P2 | P3 | H | X |
|---|---|---|---|---|---|---|
| `sans-mythique` | **[]** | – | – | – | – | – |
| `mow` | `[85, 87, 89]` | oui | oui | oui | non | **non** |
| `greffe` (owner ON-BOARD) | `[84, 86, 88, 92]` | oui | oui | oui | non | **oui** |
| `mow` + `P1:Rarity=4` | `[87, 89]` | **non** | oui | oui | non | non |
| `mow` + `P2:Rarity=4` | **[]** | **non** | **non** | **non** | non | non |
| `mow` + `P2:Traits=Imperial,ActOfFaith,NPC` | `[87]` | **non** | oui | **non** | non | non |

⚠ La dernière ligne exige le **trait porteur** `NPC` : sans lui,
`IdunBattle.Operations.AddUnitOperation$$AddUnitTypeTraits` re-pose `Hero` après la fabrique et le
bras ne mesure rien (`rc 2`). Détail et montage : `docs/rl/case-1044-mur-des-traits.md`.

Et la prédiction native, sur les mêmes builds (`Loki_NormalAttack`, par tuile de départ) :

| bras | A1 -> P2 (AFFECTÉ) | A2 -> X (TÉMOIN, tuile (6,5)) |
|---|---|---|
| `sans-mythique` | 2444 – 3664 | 2034 – 3048 |
| `mow` | **1956 – 2932** | 2034 – 3048 (**identique**) |
| `greffe` | 1956 – 2932 | **1626 – 2439** |
| `mow` + `P1:Rarity=4` | 1956 – 2932 | 2034 – 3048 |
| `mow` + `P2:Rarity=4` | **2444 – 3664** (base) | 2034 – 3048 |

Cinq séparations, de natures différentes :

1. **existence** — sans `--equip-mythic`, aucun effet 1445 et la prédiction est la base. Le bras
   positif ne mesure donc pas un artefact de montage.
2. **`ConditionalSelector(IsMachine(Owner))`** — même géométrie, même `--unit-stat`, seul le
   PORTEUR change : `X` est **absent** sous la MoW et **présent** sous un porteur on-board, et son
   attaquant perd exactement 20 % dans le second cas. C'est la seule chose qui distingue les deux
   branches ici, et rien d'autre ne la produit.
3. **étage de rareté EXTÉRIEUR (`B`)** — `P1` (bout de chaîne) en `Rarity=4` sort du set ; `P2`
   reste, parce que son autre voisin `P3` est toujours un Héros Mythique.
4. **étage de rareté INTÉRIEUR (sous le `Filter`)** — `P2` (milieu) en `Rarity=4` **vide** le set :
   `P1` et `P3` sont pourtant restés `Rarity=5` (donc dans `B`), mais leur unique voisin ami n'est
   plus Mythique, donc `AmountIsGreaterThanZero` tombe. Sans ce bras, le précédent ne distingue pas
   les deux étages.
5. **le nœud `UnitsWithTrait(·, UnitTrait.Hero)`** — `P2` privé de `Hero` (et lui seul) laisse le
   set à `{P2}` : ses deux voisins sortent parce que leur unique voisin ami n'est plus un Héros,
   pendant que `P2` reste visé parce que les siens le sont restés. Aucune des quatre séparations
   précédentes ne produit cette signature — c'est le seul bras qui isole le conjoint TRAIT du
   conjoint RARETÉ, les deux étant portés par le même `Filter`.

La **magnitude** suit exactement le set : `1956 / 2444 = 0.8003` et `2932 / 3664 = 0.8002` ;
sur le témoin du bras `greffe`, `1086/1356 = 0.8009`, `1626/2031 = 0.8006`, `1626/2034 = 0.7994`,
`2439/3048 = 0.8002`, `96/120 = 0.8000`, `144/180 = 0.8000`. Le `-20 %` n'est donc **pas** un
facteur appliqué à la valeur AFFICHÉE — il entre dans le pipeline avant l'arrondi final (même
lecture que le `+20 %` d'`OnMyPosition`, #1024). L'étage exact n'est pas décomposé ici : on rapporte
la mesure, on ne fitte pas un scalaire.

⚠ **`H` n'est jamais visé**, dans aucun bras : `Friends` ne retire pas le sujet, mais les trois
étages de rareté l'excluent. Et la MoW porteuse non plus — mesuré, elle est publiée
`pos = null`, `feet = []`.

---

## 3. Pourquoi l'i2 promet quelque chose que le jeu ne rend pas (sur ce porteur)

`decisionView` publie la MoW avec **`pos = null` et `feet = []`** : une Machine of War n'occupe
**aucune tuile**. Donc `AdjacentFriends(Owner)` — et avec lui **tout `A`** — est **structurellement
vide** dès que l'Owner est la MoW, **quelle que soit la branche prise**. Les deux branches du
`ConditionalSelector` COÏNCIDENT sur le porteur de jeu, et c'est exactement le régime dégénéré que
le bras `greffe` casse.

Autrement dit, le « **adjacent to Galatian** » de l'i2 n'est atteignable que si l'ability change de
propriétaire pour une entité **posée sur le plateau**. Le kit en offre précisément une voie :
`IdunBattleLogic.Entities.Abilities.Active.Loki.DutyEternalAbility$$ExecuteBehaviour` transfère la
**première** triggered ability du caster à l'unité fraîchement spawnée
(`AddTriggeredAbility(ActiveTarget@<DSLFactory+0x180>, …)`, cf. `case-91` §8 et
`engine/runner/abilities/behaviours/grants.py`). `case-91` classait cette branche « non atteignable :
un `ultraDreadnought` de rang courant n'a pas de triggered ability » — **ce n'est plus vrai depuis
#999** : `--equip-mythic ultraDreadnought:WisdomOfTheAncients` lui en donne une, et le RE ci-dessus
dit ce que la copie fera une fois transférée. Résidu `#1042-r2`.

---

## 4. Le mur du PORT — la rareté, et rien d'autre

`UnitsWithRaritySelector$$Select` compare `GetBaseUnitComponent(e)->[+0x74]` ; le port n'a **aucun**
canal `rarity` (mesuré #1024 §4 : absent d'`observeBattle`, `combatSnapshot` et `decisionView`).
Point d'ancrage à hooker déjà nommé là-bas (`frida/hooks/features/ai-step/rpc-snapshot.ts`,
`readUnitConfig`) — **ne pas le re-mesurer**.

Inscrire 1445 dans `EFFECT_CLASSES` sans ce gate serait **permissif** : l'aura protégerait tout ami
adjacent à un ami Héros, Mythique ou non. Et le régime par défaut le cacherait — `rl_duel build`
impose `targetRarity = 5`, donc les trois étages sont uniformément vrais ; un port sans gate serait
d'accord avec le natif dans **tous** les bras par défaut. Les deux bras `--rarity` ci-dessus sont la
seule sortie de ce régime.

Ce qui EST livré : `ABILITY_INIT_OWNER_EFFECTS["WisdomOfTheAncients"] =
["WisdomOfTheAncients_DamageReduction"]` (seed de l'owner-effect par la voie tertiaire, filet pour
les chemins purement offline — sur un runner live l'effet est de toute façon capté) + la RE au site.

**Face DÉCISION** — `IdunBattle.AI.Playbook.Loki.WisdomOfTheAncientsPlaybook`
(`TriggeredAbilityNonOwnerPlaybook<WisdomOfTheAncientsAbility>`, `.ctor` : clé `0x5ab`) surcharge
`$$CalculateMovementUtilityInSteps`. Corps LU (`<CalculateMovementUtilityInSteps>d__2$$MoveNext`) :

```
if (case == null || case.unit@+0x10 == null)                    yield break   // regime SPAWN
u = GetBaseUnitComponent(case.unit)
if (u->[+0x74] != 5)                                            yield break   // Rarity.Mythic
foreach (e in <voisins de case.MovementTile>) :
    if (e == case.unit) continue
    c = GetBaseUnitComponent(e)
    if (c->[+0x74] == 5 && c.HasTrait(0x10 = UnitTrait.Hero))    yield GetUtilityValue(...)
    if (e == owner)                                              yield GetUtilityValue(...)
yield break
```

— **le même couple de conditions que le sélecteur**, sur l'axe MOUVEMENT, et **le même verrou de
rareté**. Déjà recensé par le résidu `#477-r37-r1`, qui nomme `1451` explicitement : rien à rouvrir.

---

## 5. Ce qui N'EST PAS couvert

- **Le PORT de l'effet 1445** — `#1042-r1`, BLOCAGE capteur.
- **La voie NATIVE de la branche `ifFalse`** (`DutyEternal` → `AddTriggeredAbility` sur le spawn) :
  la branche est établie par un porteur **greffé**, pas par le transfert du jeu. `#1042-r2`.
- **Le nœud `UnitsWithTrait(·, UnitTrait.Hero)`** : **CONFRONTÉ** (2026-08-14, #1044) — le bras est
  au §2. `--unit-stat "<vis>:Traits=[…]"` mord bien ; ce qui manquait était le **trait porteur**,
  sans lequel `IdunBattle.Operations.AddUnitOperation$$AddUnitTypeTraits` re-pose `Hero` après la
  fabrique. Le probe **refuse** toujours (`rc 2`) quand `Hero` survit, et **nomme la sortie**.
  `docs/rl/case-1044-mur-des-traits.md`.
- **L'étage exact** où entre le `-20 %` (§2) : mesuré comme facteur ~0.800 sur la valeur rendue,
  non décomposé.
- **Les paliers 1/2/3** (`dmgReductionPct` 10/13/16) : seul le palier 4 est joué.
- **Le multiplicateur de rareté** de `dmgReductionPct` : la voie tertiaire passe `mult = 100`
  (#999/#1005), donc le flag `variablesAffectedByRarityBonus` n'a pas été exercé.
