# Lot ENGINE `triggers/dispatch/registry.py` — la fourche écartée, le marqueur jamais retiré, et le kit qui ignorait la voie dérivée

Six résidus soumis, **quatre résolus**, un **étage levé en RE**, un **NON RÉSOLU** avec son étage
mesuré. Build `t6dpr4k06g`. Tous les corps cités ont été **relus** dans cette tranche.

---

## 1. `#1001-r1` — la fourche d'`ActOfFaith` n'était pas une cross-instantiation

**Prémisse CONFIRMÉE.** Les deux `CreateBehaviour` sont structurellement identiques, au token près :

```
ActOfFaith_RemoveEffectAbility$$CreateBehaviour
    triggerType != 0x20 = Custom  ->  TriggerAbilityDelayed(Owner@+0x30, 0x3fa = 1018, 3)
    triggerType == 0x20 = Custom  ->  RemoveEffect(Owner@+0x30, Nullable(0x3f9 = 1017), null)

BladeOfTheAncestors_RemoveEffectAbility$$CreateBehaviour
    triggerType != 0x20           ->  TriggerAbilityDelayed(Owner@+0x30, 0x5d3 = 1491, 3)
    triggerType == 0x20           ->  RemoveEffect(Owner@+0x30, Nullable(0x5d1 = 1489), null)
```

**Le corps d'`ActOfFaith` n'est PAS gshared.** Il est nommé, propre à cette classe, et le seul appel
`Il2CppFullySharedGeneric` qu'il contient est le `.ctor` de `System.Nullable<EffectType>` — une
construction de **valeur**, pas un partage de corps. C'est cette confusion qui avait fait écarter la
branche.

L'argument qui la soutenait — « l'accumulate a `Nothing` en `== 0x20` et le réel en `!= 0x20`, donc
les assignations sont *opposées* » — ne conclut rien : **les deux classes de 1018 fourchent sur le
même test et se partagent le travail**, exactement comme les deux de 1491. Vérifié :
`ActOfFaithAbility$$CreateBehaviour` a bien `DSLBehaviors$$Nothing()` en `== 0x20`.

**Porté** : `ActOfFaithResetAbility` ENFILE (`TriggerAbilityDelayed`), et la branche `Custom` devient
`ActOfFaithCustomRemoveEffectAbility`, inscrite dans `CUSTOM_TRIGGERED_ABILITIES[1018]`. Observable :
les coups suivants de l'attaque qui a crité **gardent** le buff ; il ne tombe qu'au drain de
`ProcessPendingTriggeredAbilities`.

### Divergence adjacente, trouvée sur le même décompilé

`ActOfFaithAbility$$CreateBehaviour` porte un conjoint que le port n'avait pas :
`AreEnemies(Targets@+0x60, Owner@+0x30, 0)`. Sans lui, la branche 1 du `CreateTrigger` (« un allié
Imperial **meurt** ») pouvait accorder le 2ᵉ stack probabiliste là où le natif le réserve au cas où
la **victime** est un ennemi. Porté dans le même commit.

---

## 2. `#1074` — `1061` était posé et jamais retiré

`JustSummonedEffect$$CreateRemoveEffectTrigger`, **relu verbatim** (ordre des `op_BitwiseOr`
compris) :

```
( On(0x3a = PhaseEnd, ownerNeedsToBeAlive = 0)
| (On(0x1f = PreUnitMove,   alive 1) & get_OwnerIsActor) )
| (On(0x2a = PreUnitAbility, alive 1) & get_OwnerIsActor)
```

Behaviour = la greffe `Triggered(<ce trigger>, RemoveEffect(df@0x150))` que
`BaseEffect$$CreateHandleTriggerAbilities` ajoute au **même `ArraySet`** — rail ARRAYSET, donc
**aucun gate `EffectComponent.IsActive`** (entrées `probe_229.RAIL` posées dans le même commit).
Trois `On()` disjoints ⇒ trois classes, le dispatch du port étant keyé par `event_id`.

**Et l'inscription au domaine de non-ciblabilité, dans le même commit.**
`UntargetableEffect$$ApplyInternal` pose `UnitFlagsComponent$$Add(0x11)` sur la **cible**,
`$$RevertInternal` le retire, et `JustSummonedEffect` **ne surcharge pas** `IsUntargetableEnabled`
(le seul surchargeur du build est `TitanhammerSquad_TeleportingInEffect`). Inscrire avant le retrait
aurait rendu Celestine non ciblable **pour le reste de la bataille** ; le vecteur dominant
`PhaseEnd` borne la fenêtre au message top-level courant.

Le cran bidirectionnel a **mordu comme prévu**, dans le sens « retireur porté sans inscription » —
il garde désormais l'inscription et a été renommé en conséquence
(`..._enters_the_domain_only_when_BOTH_faces_are_ported`) ; sa règle (`_doit_entrer_au_domaine`) n'a
pas bougé.

Les trois autres membres (`1`, `1230`, `1390`) restent dehors pour l'autre raison : **aucun poseur**.

---

## 3. `#894-r7` — le kit déclenché ignorait la voie ACTIVE → TRIGGERED DÉRIVÉE

Les **deux** causes sont re-mesurées et fermées.

**(a) La résolution du `visualId`.** `GC.unit("GuildBoss10Boss1AdmecBelisarius")` rend `None`, là où
`GC.unit("admecBossBelisarius")` rend l'unité — donc kit `[]`. Nouveau foyer
`resolve_unit_id_from_visual_id`.

> ⚠ **La résolution inverse n'est PAS sûre en général, et c'est mesuré** : **429** unités ont
> `visualId != unitId`, et **100 `visualId` sont partagés par plusieurs `unitId`** (jusqu'à **7**) ;
> **72** seulement sont uniques. Rendre le premier venu ferait lire le kit d'une **autre** unité —
> faute pire que le `[]` qu'on répare, parce qu'elle est plausible. Le foyer ne résout donc que
> l'appariement **UNIQUE**. `GuildBoss10Boss1AdmecBelisarius` est dans le cas sûr.
> `gameconfig.resolve_unit_id`, que la fiche citait comme foyer existant, **ne fait pas ce travail**
> (vérifié : il rend `None` sur ce `visualId`).

**(b) La voie dérivée.** `UnitFactory$$AddDerivedAbilities` inscrit au **même**
`TriggeredAbilityComponent` que les `passiveAbilities` :

| source native | dict | entrées relues |
|---|---|---|
| `config@+0xa0` (ActiveAbilities) → `StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities` | `<statics>+0x30` | **43** |
| `config@+0xa8` (PassiveAbilities) → `StaticBattleRules.TriggeredAbility$$GetDerivedTriggeredAbilities` | `<statics>+0x88` | **2** |
| `config@+0xd0` (Traits) → `StaticBattleRules.Trait$$GetTriggeredAbility` | — | déjà porté |

> ⚠ **Ghidra imprime parfois en DÉCIMAL.** Une des 43 valeurs est écrite `1099`, pas `0x44b`. Un
> parseur qui ne lit que l'hexadécimal l'apparie à la ligne suivante, **en silence** — c'est ce qui
> est arrivé au premier jet, et seule la relecture du bloc l'a montré.

**Mesure après correctif** : `triggered_ability_ids("GuildBoss10Boss1AdmecBelisarius")` = `[1474,
1293, 1297]` (avant : `[]`), identique au kit par `unitId`. **`1297` y est**, donc le gate
`GetAbilityState` passe.

**Rayon de souffle, mesuré et borné** : **71 unités sur 683** voient leur kit s'élargir, **32** ids
distincts ajoutés. L'élargissement est **strictement inerte sur la face DÉCISION** — **aucun** des
46 ids dérivés n'a de playbook porté, et le dispatcher skippe les ids sans playbook, exactement
comme le natif (`if (playbook == null) continue`). Il ne mord donc que sur le gate, la cible. En
live, `entity_triggered_ability_ids` privilégie de toute façon le canal mesuré.

---

## 4. `#894-r2` — la phase 2 de `SolarAtomizer` fire, et le premier déclenchement a levé `TypeError`

`1371` entre dans `PENDING_ATTACK_EFFECTS` (4 → 5). Confrontation
(`probe_10018r1_solar_atomizer_phase2_live.py`, runner 45, boss u88) :

```
notCarrying      : [<le boss>]  ->  []          <- le gate est franchi
declenchements   : 0            ->  1
chaine selecteur : tuiles_1372 3 / EntitiesWithAnyEffect 3 / Units 1 / Enemies 1
coups            : 3, sur l'unite 84 -- LA MEME que le natif touche
CONTRE-EPREUVE   : 1371 retire de la table -> 0 declenchement, 0 degat
```

> ⚠ **Le fait le plus transposable de ce lot.** `solar_atomizer_attack_tree` passait
> `source_ref=Owner()` à `AttackWithAttackDamage` — un mot-clé **qui n'existe pas** dans la
> signature du nœud, et qu'aucun autre appelant ne passe (son jumeau `lions_wrath_attack.py` ne le
> passe pas ; l'attaquant vient du contexte `entities`). L'appel était **cassé depuis sa
> livraison**, et **invisible** : le gate du rail avalait le déclenchement, donc la ligne n'avait
> jamais été exécutée. *Un arbre livré mais jamais joué ne peut pas être juste, et rien ne le
> disait.*

**Ce qui n'est PAS confronté** : le probe mesure les deltas de PV natifs sur `act + endturn +
aiturn`, donc **le tour adverse complet y est agrégé** (d'où un delta sur le boss lui-même,
`88: 33936`, qu'aucune attaque différée ne lui inflige). `{84: 19569}` contre `{84: 30154}` n'est
donc **pas un écart mesuré**, c'est une mesure **non isolée**. Résidu **`#894-r8`**.

---

## 5. `#521-r4` — RE complète, oracle live obtenu, port BLOQUÉ par un étage

**Le blocage de LECTURE est levé** : `DaemonicOrdnance_AddCritChance$$CreateTrigger` est absent des
deux tables (corps ICF-dédupliqué) et se résout **par slot de vtable**
(`probe_521r4_daemonic_ordnance_slots.py`, RPC `resolveVtableSlot`) :

```
slot 0x2d8 = CreateTrigger
  AddCritChance     -> corps PARTAGE, proprietaire ghidra
                       `...Active.Loki.SummaryExecutionAddBaseEffectAbility$$CreateTrigger`
                       = `return <DSLTriggers+0x30>`
  RemoveCritChance  -> son corps PROPRE
```

`DSLTriggers$$InitializeShared` (relu) : `this+0x30 = On(0x21 = AbilityInit) & <this+0x70> &
get_OwnerIsActor`, `<+0x70>` étant le `YesTrigger` constant ⇒ **`On(AbilityInit) & OwnerIsActor`**.

Les deux arbres, **mirror du décompilé** :

```
AddCritChance$$CreateBehaviour
    AddStaticStatModifierEffectToOwner( 0x524 = 1316 DaemonicOrdnance_ExtraCritChance,
                                        0x9 = StatType.CRIT_CHANCE,
                                        <DSLFormulas+0x18> = Direct(0),
                                        turns = null, isHidden = 0 )

RemoveCritChance$$CreateTrigger   = On(0xe = UnitPostAbility, alive 1) & get_OwnerIsCaster
RemoveCritChance$$CreateBehaviour = If( AmountIsEqualOrGreater(
                                          CriticalHitsThisTurn(Owner@<DSLSelectors+0x30>),
                                          Direct(BaseTriggeredAbility$$GetHits2()) ),
                                        RemoveEffect(Owner@+0x30, Nullable(0x524), null) )
```

> **`amount` vaut ZÉRO, et ce n'est pas une erreur de lecture.** `DSLFormulas$$.ctor` pose
> `+0x18 = Direct(0)`, `+0x20 = Direct(1)`, `+0x28 = Direct(2)`, `+0x30 = Direct(100)`,
> `+0x38 = Direct(-1)` (corps relu). **Confirmé live** : `statModSources` sur `blackForgefiend` au
> montage rend `mods = {}` — l'effet 1316 est présent et ne modifie **rien**. C'est un marqueur à
> magnitude nulle.

**ORACLE LIVE de la magnitude** (elle vit dans l'étage [4] de l'active, **déjà porté**) :

| état | `critChance` | source du stat-mod |
|---|---|---|
| avant tout cast | `{}` | — |
| après 1ᵉʳ cast | **20** | 117 |
| après 2ᵉ cast | **40** | 128 |

`extraCritChance[niveau normalisé] = 20` au gameconfig, et `TotalActiveAbilityUsed` est lu **avant**
le compteur du cast courant ⇒ `(0+1)×20`, puis `(1+1)×20`. La **source change** entre les deux :
`AddOrUpdateStaticStatModifierEffect` **remplace** l'entité-effet, il ne met pas la valeur à jour en
place.

### Ce qui bloque, et pourquoi le port n'est pas livré

**`CriticalHitsThisTurn` n'existe pas côté port**, ni le nœud ni son substrat.

```
IdunBattleLogic.Entities.DSLFormulas$$CriticalHitsThisTurn(unit)
    -> new IdunBattle.Entities.Formulas.CriticalHitsThisTurnFormula(unit)
IdunBattle.Entities.Formulas.CriticalHitsThisTurnFormula$$Calculate(entities, result)
    u = <sel@+0x10>.SelectActor(entities, Any);   if (u == null) return 0;
    c = u.GetComponent<...>();                    if (c != null) return c.<+0x54>;
```

Le compteur de crits du tour vit donc dans un composant d'unité, champ `+0x54` ; le port n'a **aucun
compteur de crits par tour** (balayage exécutable : 0 site). Le porter exige d'identifier le site
d'**incrément** et celui de **remise à zéro** (candidats lus :
`ActorStatisticsComponent$$RegisterAttackMade(target, rangeType, **totalCrits**)` et
`...$$ResetThisTurn(wasOwnTurn)`), puis de câbler le compteur dans le pipeline de dégât — **foyer
ultra-partagé, tranche à part entière avec sa propre validation**.

Livrer la moitié serait pire que rien : la **pose** seule ferait cumuler le crit-chance
indéfiniment, le retrait natif ne se produisant jamais côté port — exactement le vice que `#1074`
vient de fermer, en pire (la magnitude croît). Le module écrit a donc été **retiré**, et sa RE vit
ici. Résidu : **`#521-r10`**.

**Re-mesure des deux autres blocages `porteur`** : `1032 Catalyst` est **portée** dans
`ABILITY_CLASSES` (`abilities/tyranids.py`), `1118 DoctrinaImperatives` et `1189
CalibaniteGreatsword` aussi, `1148 DaemonicOrdnance` aussi (`abilities/blacklegion.py`) — seule
`1070 BreathOfSilence` est **absente d'`ABILITY_CLASSES`**, donc `1128` n'a toujours pas d'active
portée en amont.

---

## 6. `#443-r2-b2` — l'étage est LEVÉ en RE : l'émetteur d'`On(0x11)` est localisé

Le second verrou de la fiche (« le port n'émet pas `On(PostDamageTaken = 0x11)`, **site d'émission
natif non localisé** ») tombe. Chaîne **relue de bout en bout** :

```
InputMessageProcessor$$RunPhase
  -> $$ProcessDamageEvents
       RunPhase(PhaseType 0xe, <b__0>, isInternalPhase = 1)
  -> <ProcessDamageEvents>b__0
       q = state.<IMatchState slot 7 = GetDamageEvents>()
       items = new List<T>(q) ; q.Clear()          // SNAPSHOT puis CLEAR, dans CET ordre
       foreach it in items:
           processor.<IOperationProcessor slot 71 = ProcessPostDamageEvent>(ability, caster, target)
  -> ProcessPostDamageEventOperation$$Execute
       processor.<slot 81 = EvaluateAbilities>(caster, caster, target, **0x11**, <ability>)
```

et l'**enfilement** est `IMatchState` **slot 8 = `AddDamageEvent(ability, target, damageResult)`**,
appelé par `ApplyDamageOperation$$Execute` **juste après** la publication d'`On(0xf = DamageTaken)`,
dans le même bloc gardé. Les deux slots sont **lus** dans
`data/symbols/<build>/metadata/ioperationprocessor_slots.tsv` et
`.../metadata/interface_slots.tsv`, pas devinés.

⇒ `On(0x11)` est **le même patron que la file des triggered-abilités différées** : une file drainée
après l'arbre d'opérations du message top-level. Le porter est donc mécaniquement clair, mais touche
`state`, `Runner.apply` et `dispatch/attack.py` — **hors du `FOYER:` déclaré du résidu**, et chaque
nouvel event peut réveiller des consommateurs. Résidu à ouvrir par la tranche qui le prendra.

Le **premier** verrou (pas d'oracle : `matches` d'un effet-trigger n'a aucun pendant natif
interrogeable) est **intact**, et le montage à trois morts contrôlées reste celui de la fiche.
**NON CONFRONTÉ.**

---

## 7. Résidus ouverts par ce lot

| id | quoi |
|---|---|
| `#894-r8` | isoler la fenêtre de mesure de la phase 2 de `SolarAtomizer` (le probe agrège le tour adverse) |
| `#521-r10` | porter `DSLFormulas$$CriticalHitsThisTurn` et son substrat, puis inscrire `1244` |
