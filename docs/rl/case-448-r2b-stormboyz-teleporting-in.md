# case-448-r2b — `1140 StormboyzStrike_TeleportingIn` : la dérivée SANS `*_Moving`, et le seul régime qui exerce `HasTile`

Tranche 2/4 de la famille `IdunBattle.Entities.Effects.Loki.ATeleportingEffect`
(inventaire : `case-448-r2-ateleporting-effect-family.md`). Build `rnca9r7q6c`.

> **Les §2 à §4 ont été RÉVISÉS par `#448-r3-r1` (2026-08-05).** Ils décrivaient un port où
> `…StormboyzStrike_MissAbility` et `…_FallbackAbility` n'étaient pas encore portées, et les gardes
> l'exigeaient. Ce qui a changé, ce qui reste, et pourquoi le probe ne le montrait pas en ligne de
> commande : **`docs/rl/case-448-r3-r1-etage-entre-depuis.md`**.

Les quatre `Triggered()` de la base ne sont pas relus ici — ils l'ont été par la tranche 1, et le
port les réutilise **tels quels**. Ce document ne traite que ce qui est **propre à 1140**, et c'est
exactement ce qui aurait pu être obtenu par symétrie et faux : le `Nullable` vide de
`GetMovingEffectType`, et le bras FAUX du gate `HasTile(Owner)`.

---

## 1. `GetMovingEffectType` — la surcharge EXISTE, son `Nullable` est VIDE

L'inventaire annonçait « `Nullable` vide ». Une absence de symbole ne prouve rien
(`reference_symbol_table_absence_proves_nothing`) : il fallait le **lire**. Quatre mesures
indépendantes, toutes reproduites par le volet A du probe ou citées ici :

**(a) Le slot virtuel, lu au RUNTIME.** RPC `resolveMethodPtr` (lecture pure, aucun hook), sur les
quatre dérivées :

| classe | `GetMovingEffectType` à la profondeur 0 ? | entrée → symbole |
|---|---|---|
| `TeleportStrike_TeleportingInEffect` | oui | `…TeleportStrike_TeleportingInEffect$$GetMovingEffectType` |
| **`StormboyzStrike_TeleportingInEffect`** | **oui** | **`Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`** (corps DÉDUPLIQUÉ) |
| `FearOfTheUnseen_TeleportingInEffect` | oui | `…FearOfTheUnseen_TeleportingInEffect$$GetMovingEffectType` |
| `TitanhammerSquad_TeleportingInEffect` | oui | `…TitanhammerSquad_TeleportingInEffect$$GetMovingEffectType` |

La base `ATeleportingEffect` rend une entrée **nulle** pour ce nom : le slot est ABSTRAIT, les quatre
le surchargent. « Stormboyz ne surcharge pas » (écrit par `case-366-r1` §7.5) est donc faux ; c'est
le CORPS qui est vide.

**(b) Les octets de ce corps.** `33 c0 c3` = `xor eax, eax ; ret`.
`Nullable<EffectType>` est un `{int32 value; bool hasValue}` de 8 octets, donc **retourné dans RAX**
sur x64 Windows — les trois sœurs le montrent en clair (elles construisent le `Nullable` sur la pile
puis rendent le `local_res20` de 8 octets). `RAX = 0` ⇒ `hasValue = 0` ⇒ **`Nullable` VIDE**.

**(c) L'enum du build.** `data/symbols/rnca9r7q6c/frida/enums.tsv`,
`IdunBattle.Entities.Enum.EffectType` = **629** valeurs, dont exactement **trois** `*_Moving` :
`1036 TeleportStrike_Moving`, `1241 FearOfTheUnseen_Moving`, `1574 TitanhammerSquad_Moving`.
Aucun `StormboyzStrike_Moving`.

**(d) La fabrique.** `IdunBattleLogic.Effects.TeleportMovingEffect$$.ctor` a **trois** appelants,
tous des lambdas d'`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects`
(`b__14_78`, `b__14_260`, `b__14_567`) — une par `*_Moving`.

⇒ **T4 prend la branche `Nothing()`.** La spécialisation du port se réduit à
`effect_type = 1140`, `MOVING_EFFECT_TYPE` hérité à `None`.

Les DEUX autres vslots ne sont **pas** surchargés par `StormboyzStrike_TeleportingInEffect` (même
lecture runtime : `GetAdditionalRemoveTriggers` et `GetCustomMovingEffectCondition` ne résolvent
qu'à la profondeur 1, sur le corps de base partagé avec
`…WayOfTheShortBlade_AdditionalAttackMarkerEffect$$CreateActiveCondition`, qui rend
`<DSLTriggers+0x40>` = le conjonct NEUTRE). Les deux collapses de la base valent donc.

Le `$$.ctor`, lu à l'octet : `mov edx, 0x475` (**1141**) puis l'overload d'
`IdunBattle.Core.AbilityOrEffect$$op_Implicit` qui appelle `$$set_TriggeredAbility` — la source est
bien `TriggeredAbilityType.StormboyzStrike`, pas l'homonyme `ActiveAbilityType.OverwhelmingWrath`.

---

## 2. Le RÉGIME : hors plateau, donc `HasTile(Owner)` FAUX

`…StormboyzStrike_TeleportAbility$$CreateBehaviour` fait
`RemoveUnitFromItsTiles(Owner, removeTileFromUnit: true)` **avant** de poser 1140 : le porteur est
**hors plateau** tout le temps où il porte l'effet. C'est le seul des quatre dans ce cas.

Conséquence sur les quatre triggers de la base, et c'est ce que la tranche apporte :

| trigger | condition NATIVE, écrite en entier | pour 1140 |
|---|---|---|
| T1 `On(0x04 UnitAfterMove)` | `OwnerIsActor & <0x738>` | **matche** — c'est le retrait du port au pas |
| T2 `On(0x2a PreUnitAbility)` | `OwnerIsActor & <0x738>` | **matche**, mais aucun geste ne l'atteint (§4) |
| T3 `On(0x28 UnitFinishedTurn)` | `OwnerIsActor & HasTile(Owner) & <0x738>` | **NE MATCHE PAS** — l'effet SURVIT à la fin du tour |
| T4 `On(0x1f PreUnitMove)` | `OwnerIsActor & <0x738> & <0x748>` | matche, et exécute `Nothing()` |

⚠ **Le vslot `0x738` est dans les QUATRE, T4 compris** — `ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal`
fait `(**(code **)(*in_RDX + 0x738))()` une fois par trigger. Point établi par `#448-r2c`, dont la
sœur `1238` **surcharge** ce vslot : chez elle il gouverne donc aussi la pose du marqueur `*_Moving`.
**Ici il ne change rien, et c'est vérifié plutôt que supposé** : `1140` ne surcharge NI `0x738` NI
`0x748` (mesure runtime, §1), les deux rendent `True`, la condition de T4 se réduit à `OwnerIsActor`,
et la branche prise dépend du seul `GetMovingEffectType`. La garde
`test_T4_declares_no_moving_effect_and_poses_nothing` distingue explicitement « la condition est
fausse » de « la condition est vraie mais le behaviour est `Nothing()` » — seule la seconde est le
natif.

**Deux tiers du même kit décident QUEL étage agit** — et ne pas le dire aurait fait lire un
désaccord de port là où il n'y en a pas. Ils sont **PORTÉS depuis `9fc0deca` (#448-r1,
2026-08-03)**, donc les deux côtés empruntent désormais le même étage :

* `…StormboyzStrike_MissAbility` — `On(0x1f PreUnitMove) & OwnerIsActor & HasEffect(Owner, 0x474)`
  → `… & RemoveEffect(Caster, 0x474) & …`, le `RemoveEffect` étant **hors** du `If`, donc
  INCONDITIONNEL. C'est **elle** qui retire 1140, au pré-move ; T1 n'a plus rien à retirer.
* `…StormboyzStrike_FallbackAbility` — `On(0x28 UnitFinishedTurn) & OwnerIsActor &
  HasEffect(Owner, 0x474)` → `MoveUnitBehaviour(…)` qui REPOSE l'unité. Après quoi `HasTile(Owner)`
  devient vrai et **T3 retire**. C'est la lecture de `case-448-r1` §5, et cette tranche la joue.

> ⚠ **Ce paragraphe a été écrit alors que les deux étaient NON PORTÉES, et les gardes de cette
> tranche exigeaient du port qu'il s'en écarte.** Elles ont rougi trois jours durant en accusant le
> port. Réparé par **`#448-r3-r1`** — `docs/rl/case-448-r3-r1-etage-entre-depuis.md`, qui refond le
> §3 ci-dessous.

---

## 3. Ce que la mesure live établit

Montage : **greffe du passif** `StormboyzStrike` sur une unité du pool (`case-92` §5bis, recours 3 —
porteur réel `orksNpc6Stormboy` npc sans summoner), pipeline `catalog_inject.write_grafted_seed_bc`
déjà validé 3/3 par #366-r1. Deux montages : `orksNob`/`MC1_67`/777 (base pathfinder WALK) et
`thousTzaangor`/`C3_26`/31337 (base FLY, comme le porteur réel qui a le trait `Flying`).

| volet | ce qui est comparé | résultat (les DEUX montages) |
|---|---|---|
| **E1** | état de départ natif | `pos = null`, empreinte vide, vivant, `1140 remaining = 2` |
| **E1b** | les autres effets du porteur sous 1140 | `orksNob` : `[1516 BeastSlayer_ExtraDmg, 1517 BeastSlayer_ExtraBlock]` **déjà posés** |
| **T2-VIDE** | `abilityTargets.fromHere` du porteur hors plateau | `[]` des deux côtés |
| **E-PORTED** | les classes de `StormboyzStrike` montées côté port | les **trois** (`Teleport`, `Fallback`, `Miss`) |
| **E-PREMOVE** | l'état de part et d'autre du vecteur `On(0x1f)`, côté port | `1140` **là** avant, **parti** après ; le Miss a rendu son résultat |
| **E-MOVING** | l'état à l'entrée du vecteur after-move, côté port | **aucun** `*_Moving`, et `1140` déjà parti |
| **CONFRONT-MOVE** | `pos`/`feet`/`alive`/**liste entière** des effets/`untargetable` | égalité terme à terme, **position comprise** (PRNG aligné) |
| **CONFRONT-MOVE** | la CASCADE d'events native (20 puis 15 events) | retrait de `1140` **avant** le `ChangePosition` (`[5,6]`<`9`, `[4,5]`<`8`) ; **AUCUNE** ligne `*_Moving` |
| **T3-GATE** | le bras FAUX du gate, Fallback retiré du registre | `matches()` = `False` ; `1140` survit, unité hors plateau |
| **T3-POSITIF** | le bras VRAI, unité posée et aucun mouvement | `1140` retiré par T3 |
| **FINISH-a/b/c** | port et natif sur le `finish` nominal | reposé en `(1,3)` / `(0,4)`, **1140 retiré**, ciblable — **égalité terme à terme** |

Le **témoin positif** du scan de cascade est la tranche 1 : sur `eldarAutarch`, le MÊME scan remonte
deux `Effect_Refresh «TeleportStrike_Moving»` encadrant le `ChangePosition`. Une cascade vide ne
prouverait rien — le probe exige donc `cascadeCount > 0`.

⚠ **Le `_MissAbility` mord, et le PORT le suit hex pour hex.** Sur `MC1_67`/777 les deux côtés
atterrissent en `(2,4)` alors que `(3,4)` était demandé —
`OverrideUnitMovementTarget(Owner, PickRandomly(CanAddUnit(AdjacentTiles(<dest>)), 1))`. Sur
`C3_26`/31337 le Miss ne dévie pas et les deux côtés vont en `(4,0)`. Le terme position est donc
comparé **à l'identique**, et c'est l'**alignement PRNG** (`dumpRng` → `state.rng`, même recette que
`test_448_r1_stormboyz_port_live.py`) qui le permet. Le seuil « distance 0 ou 1 » que cette fiche
prescrivait avant `#448-r3-r1` acceptait, lui, un vrai désaccord de port du moment qu'il restait
adjacent.

⚠ **Un canal ment sur l'unité hors plateau, et il faut RECONSTITUER l'entrée.** Une unité sans tuile
sort d'`observeBattle` et arrive dans `decisionView` avec `visualId = pos = hp = owner = team = null`
(mesure #366-r1). Le port charge donc un `OwnerComponent` à `team = player = None`, et le premier
étage qui les lit — `refresh_stat_modifier_effects` → `UnitEffectStateView.is_turn_of_owner` —
**lève**. Le probe monte un runner TÉMOIN (même seed, même board, mêmes unités, seed BC par le même
pipeline mais SANS greffe), y lit `(team, player)`, vérifie que l'id d'entité coïncide, et ne
remplit **que** ce que le canal a laissé à `None`. C'est une reconstitution d'ENTRÉE, pas un
correctif de port.

### Contre-épreuves

    python scripts/python/probe_448_r2b_stormboyz_teleporting_in.py --mutate           # 1 rouge (T3-POSITIF)
    python scripts/python/probe_448_r2b_stormboyz_teleporting_in.py --mutate-hastile   # 2 rouges (T3-GATE)
    python scripts/python/probe_448_r2b_stormboyz_teleporting_in.py --mutate-nograft   # 12 rouges (E-PORTED)

`--mutate` VIDE `EFFECT_TRIGGERS[1140]` ; `--mutate-hastile` neutralise le gate `HasTile` de T3 ;
`--mutate-nograft` délie le transport RPC ambiant, donc la greffe n'est plus montée côté port.

⚠ **`--mutate` ne mordait plus, et c'est un enseignement, pas un détail.** Une fois le Miss et le
Fallback portés, les **quatre** `Triggered()` propres de `1140` sont devenus observationnellement
INERTES sur le geste nominal — le kit qui les entoure les masque tous. Le bras **T3-POSITIF**
(unité posée, aucun mouvement dans le vecteur, Fallback retiré) est ce qui rend la main à T3 et
restaure la contre-épreuve. Ventilation trigger par trigger : `case-448-r3-r1` §5.

Côté OFFLINE, **six** mutations adversariales, toutes tuées par
`tests/engine/runner/test_448_r2b_stormboyz_teleporting_in_offline.py` : `MOVING_EFFECT_TYPE = 1036`,
gate `HasTile` à `True`, registre vidé, domaine de non-ciblabilité sans 1140, mixin d'atterrissage
greffé sur 1140, `OwnerIsActor` neutralisé.

---

## 4. Ce que cette tranche NE fait PAS, nommément

* **T2 n'est CONFRONTÉ par aucun geste.** Sous 1140 le porteur est hors plateau : il n'a ni portée
  ni ligne de vue, et `abilityTargets` rend un `fromHere` **VIDE** (mesuré, les deux montages).
  Le trigger est porté parce qu'il est dans l'`ArraySet` natif de la classe de base — pas parce
  qu'un geste l'exerce. Le seul chemin qui l'atteindrait est un cast *après* que le Fallback ait
  reposé l'unité, mais T3 a déjà retiré l'effet à ce moment-là.
* ~~**`…StormboyzStrike_MissAbility` et `…StormboyzStrike_FallbackAbility` restent NON PORTÉES**~~ —
  **PÉRIMÉ** : `9fc0deca` (#448-r1, 2026-08-03) les a portées toutes les deux, avec leurs pièces
  natives (`OverrideMovementTargetOperation`, `TRIGGERED_ABILITY_BEHAVIOURS[1134]` pour
  `FullThrottle` ; le `PerformAIMovementBehaviour` annoncé **n'existait pas** — c'est un `If`, ctor
  dédupliqué mal lu). Le pas dévie donc bien 20 % du temps, la tuile `1179 _AlreadyUsedTile` est
  marquée, et une unité qui finit son tour hors plateau est **reposée**. Seul
  `FullThrottle$$CreateTrigger` (le passif autonome) reste non porté — `case-448-r1` §6.3.
* **Aucune couche impérative derrière le retrait.** 1140 ne porte pas `_TeleportStrikeLandingMixin`,
  et c'est une lecture : le régime « passives DÉFÉRÉES » de 1035 tient à ce que l'effet est là
  *avant* l'initialisation des abilities du porteur, alors que pour 1140 c'est
  `On(0x21 = AbilityInit)` **lui-même** qui pose l'effet. Mesure : volet E1b — le porteur greffé
  arrive sous 1140 en portant déjà ses owner-effects, et ceux-là ne peuvent venir que de la capture
  native (`snapshot.load_state` ne sème que les owner-effects d'ABILITY, et `_seed_trait_owner_effects`
  n'est appelé que par `initialize_deferred_actor_abilities`, que cette tranche n'accroche pas).
* **Le `RemoveEffect` du port reste un COLLAPSE D'INSTANCE**, comme pour toute la famille : le natif
  retire *cette* instance (`RemoveEffect(EffectSelf)`), le port retire tous les stacks non consommés
  du type sur le porteur. Le gate « déjà présent » d'`AddEffectOperation` garantit au plus une
  instance.

---

## 5. Effet de bord assumé : la non-ciblabilité devient un DOMAINE

`IdunBattle.Entities.Effects.Common.UntargetableEffect$$ApplyInternal` fait
`IdunBattle.Entities.Components.UnitFlagsComponent$$Add(0x11)` sur la **cible**, pour TOUTE
sous-classe (`$$RevertInternal` le retire). Le flag ne vient donc pas de l'effet feuille : porter
1140 sans le dire aurait laissé son porteur **CIBLABLE** côté port, là où le natif le retire de
l'énumération.

Le port lisait `TeleportStrike_TeleportingIn` **en dur**, à deux endroits
(`ai/state_bridge.py::_is_untargetable`, `entities/effects/aura_selectors.py::is_targetable`, ce
dernier par comparaison de NOM). C'est maintenant un domaine unique,
`aura_selectors.UNTARGETABLE_EFFECT_TYPES`, et les deux lecteurs le partagent.

Fermeture NATIVE du domaine (`classes.tsv`, parent `UntargetableEffect`) : `ATeleportingEffect`
(4 dérivées) **et `IdunBattle.Entities.Effects.Loki.JustSummonedEffect`**. Le port n'y inscrit que
ce qu'il a confronté **SUR CE CANAL** — aujourd'hui **{1035, 1140}** — et un test le FIGE. Ce qui
reste dehors, pour des raisons **distinctes**, et c'est le point à ne pas rabattre :

* **`1238`** — **INSCRIT (#448-r2b-r1, 2026-08-07)**. La RE est nette : la classe dérive
  d'`ATeleportingEffect` donc d'`UntargetableEffect` (`frida/classes.tsv`), **le port POSE
  réellement l'effet** (`runner/abilities/tyranids.py::fear_of_the_unseen_tree` →
  `AddEffect(1238, …, Caster())` au cast de `1115 FearOfTheUnseen`, porteur `tyranDeathleaper`,
  HERO **au pool**), le porteur reste **sur sa tuile** côté port — il restait donc énumérable
  pendant tout son round de disparition, là où i2 dit « The Deathleaper vanishes and **cannot be
  targeted** or damaged for 1 round ». Écart PERMISSIF fermé.
  ⚠ ~~**La garde est OFFLINE**~~ — **CONFRONTÉE LIVE (#546, 2026-08-08)**, et l'explication
  ci-dessous était **FAUSSE**. `decisionView` EST rendu du point de vue du joueur **COURANT** :
  `computeAttackPlans` partitionne par
  `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer`, dont le corps entier est
  `OwnerComponent.get_CurrentPlayerEntityId == TurnComponent.get_CurrentPlayerId`. Il ne manquait
  donc **aucun point d'observation** : ce qui bloquait était le MONTAGE — `act endturn` ne flippe
  pas toujours le joueur courant (quirk H19), d'où le `{81, 83}` qui était *mes* cibles. Le probe
  re-`endturn` jusqu'au flip et REFUSE de mesurer sinon ; mesure : témoin `[77, 79]` (porteur
  DEDANS), cast `[79]` (porteur DEHORS). Contre-épreuve `--mutate-un-seul-endturn` : `[81, 83]`
  sur les DEUX bras. Ce qui tenait la décision sans le live reste vrai et n'est plus load-bearing :
  `1035` et `1140`, sœurs de `ATeleportingEffect`, sont confrontées et posent bien le flag.
  Résidu `#448-r2b-r1-r1` **FERMÉ** ;
* **`1573`** — arrive avec #448-r2d ;
* **`JustSummonedEffect`** — **REFUS MESURÉ (#448-r2b-r1)**, et la raison n'est pas le rayon de
  souffle : **aucun** de ses quatre `EffectType` n'est POSÉ par le port. `1230` est posé puis retiré
  dans le même behaviour natif et le port l'OMET ; `1390` n'est pas posé
  (`triggers/loki/spiritual_leader.py` le dit explicitement) ; `1061` n'est que RETIRÉ
  (`operations/spawn.py`, `abilities/loki/momentum.py`) ; `1` n'a aucun site. Les inscrire serait
  **strictement inerte** — `has_effect` rendrait toujours faux — tout en donnant l'illusion d'avoir
  fermé le trou. **L'étage manquant est le POSEUR, pas le domaine.** Un cliquet le garde
  (`test_the_just_summoned_family_stays_out_because_nothing_POSES_it`), et il lit l'**AST** : un
  premier jet en `re` avait rendu « 1061 est POSÉ par `spawn.py` » sur… un commentaire disant
  « aucun `AddEffect(1061)` dans ce kit ». Il porte aussi sa **contre-épreuve** — il doit voir le
  poseur de `1238` —, et c'est elle qui a montré qu'il était aveugle aux constantes de module.

Le rayon de souffle (le `ClosestEnemy` du seed `MinDist(16)` et les plans d'attaque de tout scénario
à summons) est ce qui interdit d'inscrire quoi que ce soit sans mesure.

---

## 6. Reproduction

    python scripts/python/probe_448_r2b_stormboyz_teleporting_in.py              # A + 2 montages live
    python scripts/python/probe_448_r2b_stormboyz_teleporting_in.py --offline    # volet A seul (0 runner)
    python scripts/python/probe_448_r2b_stormboyz_teleporting_in.py --mutate
    python scripts/python/probe_448_r2b_stormboyz_teleporting_in.py --mutate-hastile
    python -m pytest scripts/python/tests/engine/runner/test_448_r2b_stormboyz_teleporting_in_offline.py
    python -m pytest scripts/python/tests/engine/runner/test_448_r2b_stormboyz_teleporting_in_live.py

Chaque montage consomme **trois** runners séquentiels (témoin, mouvement, finish), tous disposés.
