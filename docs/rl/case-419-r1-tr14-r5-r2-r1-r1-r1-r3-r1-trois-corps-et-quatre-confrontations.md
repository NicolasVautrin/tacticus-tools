# `#419-r1-tr14-r5-r2-r1-r1-r1-r3-r1` — les trois derniers corps propres, et ce que la confrontation LIVE a retourné

**Critère binaire** : les trois `ShouldExecute` que `-r3` déclarait non portables le sont-ils, et
les gates qu'elle a portés sans les jouer tiennent-ils face au natif ? **Les trois corps sont
tranchés** — un porté, un attesté code MORT, un déjà porté (prémisse périmée). **Et les
confrontations ont trouvé DEUX bugs de port**, tous deux RESTRICTIFS : `1147` lisait les alliés là
où le natif interroge `GetAllEnemiesOf`, et la clause BOSS du soin s'appuyait sur un trait qui
**n'est pas** le substrat de `UnitExtensions$$IsBoss`.

---

## 1. Les trois corps de (A) — et deux prémisses sur trois étaient périmées

| ability | ce que `-r3` annonçait | ce qui est mesuré |
|---|---|---|
| `1154 TacticalPrecision` | résidu, « requête + `Count > 1` » | **DÉJÀ PORTÉ** par #976 — l'en-tête du module était périmé de deux tranches |
| `1014 ArmoriumCherub` | résidu, « requête de zone + `CanKillTarget` » | **PORTÉ ici** — la « requête de zone » est le slot `IBattleQuery` 0x42, dont le port avait déjà le mirror |
| `1175 BloodChalice` | résidu, « somme de déficits de PV » | **CODE MORT** — reachability lue, pas observée |

### 1.1 `1014 ArmoriumCherub` — porté, et confronté

```csharp
// IdunBattle.AI.Playbook.Loki.ArmoriumCherubPlaybook$$ShouldExecute
position = new UnitPosition(casterTile);
list = battleQuery.<slot d'interface 0x42 = 66 GetValidTargets>(
           caster, position, ActiveAbilityType.Loki_NormalAttack);   // 0x45 = 69
if (list.<+0x10>.<+0x18 = Count> < 2)
    return !ArmoriumCherubPlaybook.CanKillTarget(caster, casterTile, target);
return true;

// ...ArmoriumCherubPlaybook$$CanKillTarget(caster, casterTile, target)
abilityState = Playbook<T>.GetAbilityState(caster);
preds = this.<slot de vtable +0x358 = MakeDamagePredictions>(
            caster, new UnitPosition(casterTile), target, abilityState);
foreach (p in preds)
    if (DamagePredictionResult.get_MightBeKill(p.<+0x8>)) return true;
return false;
```

Un gate d'**économie de surtuage** — l'inverse exact de la famille `!WillNormalAttackKill` : avec
moins de deux cibles d'attaque normale à portée depuis la tuile de cast, Vindicta ne dépense le
chérubin que si l'ability ne peut **pas** tuer.

Trois lectures qui ne se devinent pas :

1. **`MightBeKill`, pas `WillBeKill`.** La borne MAX (clé `kill` du composite) et non le SURE-kill
   (`killSure`, qui compte le block du défenseur). Prendre `killSure` rendrait le refus plus rare
   que le natif — dégradation permissive silencieuse.
2. **La « requête de zone » est déjà mirrorée.** Le slot `0x42` est `GetValidTargets` (table du
   build), le même que `BasePlaybook$$GetEligibleTargetsForNormalAttack` qu'`ExemplarOfTheKauyon`
   consomme. Le port en avait la forme BOOLÉENNE (`Count > 0`) ; la tranche extrait le **COMPTE**
   comme foyer et fait dériver le prédicat. C'est ce qui rendait `-r3` prématurée : elle avait
   classé « mirror de requête de zone que le port n'a pas sur cette route » un mirror qui existait
   sous une autre forme.
3. **Le 3ᵉ argument DIFFÈRE entre les deux call-sites, et le port ne le modélise pas.**
   `GetEligibleTargetsForNormalAttack` passe `GetNormalAttackType(unit)`, `ArmoriumCherub` passe le
   LITTÉRAL `Loki_NormalAttack` (69). Les deux coïncident pour tout porteur sans surcharge d'attaque
   normale — dont `adeptRetributor`, le seul porteur `lineup` de 1014. Les deux étages portés
   (PORTÉE + OBSCURCISSEMENT) ne lisent pas ce type : la distinction est **invisible** dans ce
   mirror, et le dire est le seul moyen de ne pas la perdre.

⚠ **Le gate vit dans `loki_custom.py`, pas dans `should_execute_gates.py`** : le registre est indexé
par `ability_id`, et 1014 y a déjà son entrée pour `CalculateCustomUtility`. Deux entrées se
seraient **écrasées**, le gagnant dépendant de l'ordre d'import.

### 1.2 `1175 BloodChalice` — DEAD CODE, établi par la reachability

`ShouldExecute` vit au slot de vtable **+0x328** et n'a qu'UN appelant,
`ComparablePlaybook<T>$$CalculateActionUtility` ; celle-ci n'a elle-même qu'UN appelant
(`list_xrefs` : un seul `UNCONDITIONAL_CALL`), `ComparablePlaybook<T>$$EvaluateInternal`. Or
`BloodChalicePlaybook` **override** `EvaluateInternal` (même slot +0x238, celui que
`BasePlaybook$$Evaluate` invoque, même signature) et son corps appelle `GenerateAction` +
`Bucket$$AddAction` directement. Le vtable porte donc l'override, et rien ne le franchit.

Le TÉMOIN qui rend ce raisonnement falsifiable est `MomentShacklePlaybook` : elle déclare
`ShouldExecute` et **pas** `EvaluateInternal`, donc son gate est vivant — et il est porté.
`CultDemagoguePlaybook` ferme le carré : `EvaluateInternal` **sans** `ShouldExecute` propre.

⚠ **Et le gate mort n'est pas équivalent à celui d'`EvaluateInternal`** : l'écart serait
OBSERVABLE s'il vivait. `EvaluateInternal` compte les amis strictement sous le seuil
(`if (pct < thr) count++`, gate `count >= 1`), `ShouldExecute` somme des écarts SIGNÉS
(`sum += thr - pct`) — un ami à 90 % de PV y pèse **−40** et peut annuler un ami à 20 %. Les deux
n'interrogent même pas la même surcharge : `EvaluateInternal` le slot **0x84 = 132**, `ShouldExecute`
le slot **0x83 = 131** (appariées par les TYPES DÉCLARÉS de `frida/methods.tsv`, pas par l'ordre).

⚠ **`methods.tsv` sous-rapporte, et c'est mesuré ici** : `CultDemagoguePlaybook$$ShouldExecute` est
ABSENTE de la table et PRÉSENTE au `resolveMethodPtr` live. C'est le faux négatif que le CLAUDE.md
décrit (dédup IL2CPP des corps triviaux). L'étape offline ne juge donc que les **présences**
d'`EvaluateInternal` ; l'étape live juge les deux.

---

## 2. `1147 HadesAutocannons` — le port lisait les ALLIÉS

```csharp
// IdunBattle.AI.Playbook.Loki.HadesAutocannonsPlaybook$$ShouldExecute
owner = EntityExtensions.GetCurrentOwnerEntityId(caster);
foreach (u in battleQuery.<slot d'interface 0x8e = 142 GetAllEnemiesOf>(owner))
    if (UnitExtensions.HasTrait(u, UnitTrait.Summon)) return true;
return false;
```

**La faute n'était pas une faute de lecture du pseudo-C.** Le décompilé n'affiche que
`FUN_180003b70(0x8e, <IBattleQuery>, ...)`, et les deux corps candidats de
`IdunBattle.Core.Services.BattleQuery` sont IDENTIQUES au sens de la comparaison d'owner près :

```csharp
// $$GetAllEnemiesOf(playerEntityId)          // $$GetAllFriendsOf(playerEntityId)
foreach (e in matchState.<slot 0x2f = GetPool>(0))
    if (GetCurrentOwnerEntityId(e) != playerEntityId)   //  == playerEntityId
        set.Add(e);
```

Le seul canal qui tranche est `data/symbols/<build>/metadata/interface_slots.tsv` :
`IBattleQuery 142 GetAllEnemiesOf 1`, `141 GetAllFriendsOf 1` — deux slots **voisins**. Le cran
d'étape 1 du probe fige les cinq slots de la famille pour cette raison.

### 2.1 Ce que la confrontation a retourné : le gate est une TAUTOLOGIE, et le bug était RESTRICTIF

Le premier montage visait trois bras (`none` / `ally` / `enemy`) en attendant un refus natif sur les
deux premiers. Il a rendu **zéro cible légale** sur `none` et `ally`, et `abilityReason` a nommé la
cause :

```
targetReason = { ruleClass: "GenericBrokenTargetingRule",
                 hex: "0x0000000000002000", reasons: ["TargetIsSummon"] }
```

Le masque de `HadesAutocannonsAbility` porte **`TargetIsSummon`** (bit 13), et ce bit est **le même
prédicat que le gate** : `HasTrait(target, UnitTrait.Summon)` (bloc TRAITS de
`engine/runner/abilities/targeting.py`). Donc, sur la route du natif, `CalculateActionUtility` n'est
appelée que pour une cible déjà filtrée « summon ennemi » — **le gate ne peut jamais refuser**.

Conséquence, plus forte que ce que la tranche cherchait : l'ancienne lecture faisait **REFUSER au
port un cast que le natif émet**, dès que le camp du caster n'avait pas de summon à lui.

Mesure (session 96, board `MC1_67`, greffe de `[1147]` sur `darkaTerminator`, `Movement = 0`,
distance 2) :

| bras | summon ennemi | summon allié | cibles légales | natif | port corrigé | port ANCIEN |
|---|---|---|---|---|---|---|
| `enemy` | 1 | 0 | 1 | OUI | OUI | **NON** |
| `both` | 1 | 1 | 1 | OUI | OUI | oui |
| `none` | 0 | 0 | **0** | non | non | non |

Le bras `both` est le témoin de **coïncidence** : il montre que l'ancien port ne « marchait » que
quand un allié portait par hasard le trait. Le bras `none` mesure la **non-discrimination**
(aucune cible légale ⇒ le gate n'est jamais atteint), c'est-à-dire la tautologie elle-même.

⚠ **La GREFFE est légitime ici, et la condition est vérifiée** : `ShouldExecute` de 1147 ne lit du
caster que `GetCurrentOwnerEntityId` — ni stats ni traits. C'est exactement ce qu'exige
`case-92` §5bis.

⚠ **Le résolveur de summon apparie par le TRAIT MESURÉ, pas par le `visualId` demandé** :
`--p-units thousSmnScreamer` fait apparaître `thousNpc2Screamer` sur le plateau (la normalisation
substitue le jumeau npc). Un montage qui apparie par le nom demandé accuse alors une absence qui
n'en est pas une.

---

## 3. La clause BOSS du soin (volet C1) — le PROXY est RÉFUTÉ

`-r3` avait porté `Common.HealPlaybook$$ShouldExecute` = `u > 0 && (!IsBoss(caster) || caster != target)`
en employant un **PROXY** : le trait `Boss` (`UnitTrait` 0x7e7). Le natif, lui, ne lit pas un trait —
`UnitExtensions$$IsBoss` résout un composant et rend l'octet `<composant>+0x88`, qu'aucun canal ne
publie. Le bras manquait ; le voici, deux bras sur `ultraTigurius` (trait `Healer` greffé ⇒ ability
`18`), caster BLESSÉ (200/20000) et SEUL de son camp :

| bras | traits mesurés | attaque normale | natif self-heal | port AVANT |
|---|---|---|---|---|
| `nonboss` | `Healer, Hero, Psyker` | `69` | **OUI** | oui |
| `boss` | **`Boss`**, `Healer, Hero, Psyker` | **`1030`** | **OUI** | **NON** |

Le **témoin de lecture** est l'attaque normale : elle bascule sur `1030 Loki_NormalBossAttack`, donc
`UnitFactory$$AddNormalAttackAbility` a bel et bien LU le trait greffé (`else if
(config.Traits.Contains(0x7e7)) type = 0x406;`). Et le natif se soigne quand même.

⇒ **`UnitExtensions$$IsBoss` ne lit PAS ce trait.** Le proxy produisait une dégradation
**RESTRICTIVE** : le port refusait un cast que le natif émet. Sans ce témoin, « le natif se soigne »
se serait lu « la greffe n'a pas pris ».

**Correctif** : `HealPlaybook._is_boss` devient TRI-ÉTAT et rend `None` (= PAS MESURÉ) ; la clause se
dégrade en VRAI — la même convention que le `turns_started` de `ReapingScythePlaybook` (« un canal
muet se DIT muet »). Le **corps** du gate est conservé : quand le substrat répondra, la clause mordra
exactement comme le décompilé le dit (cran offline dédié). Point d'ancrage à hooker :
`IdunBattle.Entities.UnitExtensions$$IsBoss`, ou l'octet `<composant>+0x88` par unité dans
`combatSnapshot`.

⚠ **Le même trait reste le BON substrat ailleurs** : `services/custom_normal_attack.NORMAL_BOSS_ATTACK_TRAIT`
dispatche l'attaque normale boss, et la mesure ci-dessus le CONFIRME (`1030`). Un seul proxy
confondait deux prédicats natifs distincts.

---

## 4. Les trois autres gates de (B), confrontés — et ce que chacun rend

### 4.1 `1095 ReapingScythe` — la bascule est EXACTEMENT au seuil natif

`if (!(u > Fix64(0))) return false; return GetStat(caster, TurnsStarted) > 2;` — le discriminant est
le TEMPS, donc les mesures vivent sur UN SEUL runner et partagent le même état à `turnsStarted` près.

| `turnsStarted` | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|
| port | **REFUSE** | ACCEPTE | ACCEPTE | ACCEPTE | ACCEPTE | ACCEPTE |
| port, gate COUPÉ | ACCEPTE | ACCEPTE | ACCEPTE | ACCEPTE | ACCEPTE | ACCEPTE |
| natif propose 1095 | non | non | non | non | non | non |

⚠ **Le montage à DEUX placements du même tour de déploiement est ce qui rend le bras mesurable.**
Le premier jet approchait le caster tour par tour, et l'approche à elle seule portait
`turnsStarted` à **4** dès la première mesure — au-dessus de la bascule. On place donc le caster,
PUIS on amène l'adversaire au contact, dans le même tour.

⚠ **Le natif ne propose 1095 sur AUCUN cycle**, et c'est nommé dans la sortie : `ReapingScythe` est
MÊLÉE, donc la cible est à un hex, donc l'ATTAQUE NORMALE a toujours un plan et son
`CalculateCustomUtility = Fix64(1)` rafle l'argmax. `aiDryRunAllUnits` rend l'action GAGNANTE, pas
« l'ability est proposable ». Ce qui reste exigible dans les deux sens : **le port ne refuse jamais
ce que le natif choisit** ; et SOUS le seuil, le natif ne peut pas le proposer.

### 4.2 `1010 StormOfFlensingBlades` — le gate est INERTE dans le port, et ce n'est pas lui qui bloque

Le bras cherchait la bascule « je ne me déplace pas pour lancer ». Il a rendu, sur les deux côtés,
`okAvecGate = okSansGate = 0` : le port ne produit **aucune** prédiction pour 1010, donc
`calculate_action_utility` rend `None` à la garde `if not events` — **avant** le gate. La
contre-épreuve qui devait le falsifier est elle-même muette.

La cause est LUE. `IdunBattle.AI.Playbook.Loki.StormOfFlensingBladesPlaybook$$MakeDamagePredictions`
existe et n'est pas portée :

```csharp
pred = battleQuery.<slot d'interface 0x22 = 34 -- la prediction d'ABILITY>(caster, target, casterPosition);
ev   = new ProbableDamageEvent(target, pred, default, default);
if (ev.<DamagePredictionResult @+0x8>.get_WillBeKill())
    return new ProbableDamageEvent[0];             // liste VIDE si le kill est SUR
return new ProbableDamageEvent[2] { ev, ev };      // sinon l'event DEUX FOIS
```

Deux quirks qu'aucun chemin générique ne reproduit : la liste VIDE sur SURE-kill (donc
`attackHealUtility = custom` seul) et le **double comptage** de l'unique event. Le port passe par la
prédiction générique, qui ne sait rien faire d'une ability dont le gameconfig ne porte AUCUNE
constante (`StormOfFlensingBlades.constants` est `null`).

**TÉMOIN** : le natif, lui, PROPOSE bien 1010 (`ActiveAbilityMessage(1010)` sur le bras `here`).
L'écart port/natif est RESTRICTIF et il **précède** le gate. Résidu ouvert :
`#419-r1-tr14-r5-r2-r1-r1-r1-r3-r1-r2`.

### 4.3 `1056 StranglethornCannon` — NON DISCRIMINANT par construction

Son corps est `attackHealUtility > Fix64(0)` LITTÉRAL. Le seul régime qui le ferait refuser est
`u <= 0`, et il est **inatteignable** sur cette route : `u` est un composite de dégât, positif, et
la seule façon de le rendre négatif est un event FRIENDLY (utilité NIÉE) — que le masque de ciblage
de 1056 exclut. Le cran offline de la comparaison STRICTE existe déjà (`-r2`) ; aucun bras live ne
peut le discriminer. Verdict : **porté, non discriminable live**, et c'est structurel.

---

## 5. Le volet `Untargetable` (C2) — bras OFFLINE posé, bras LIVE non joué

`#419-r1-tr10-r4` avait porté la seconde clause de `UnitSelectionType.OnlyAliveAndTargetable`
(`!HasFlag(unit, UnitFlag.Untargetable)`) sans jamais lui donner de bras. Il en a un ici, OFFLINE :
sur une scène où l'unique voisin est VIVANT et adjacent, `adjacency.unit_matches` passe de **1 à 0**
dès que ce voisin porte un effet du domaine `UNTARGETABLE_EFFECT_TYPES` — et le tri-état est gardé
(pas d'état d'effets ⇒ `None` ⇒ clause dégradée en VRAI).

**Le bras LIVE reste NON JOUÉ**, et l'obstacle est nommé : il exige une unité en deep-strike
(`1035 TeleportStrike_TeleportingIn` / `1140 StormboyzStrike_TeleportingIn`) adjacente au caster
**ET** à la cible **au même pas** — un état transitoire entre le cast du deep-strike et son
atterrissage, sur un caster qui doit être `1182 RighteousRepugnance` ou `1128 Boltstorm` (les deux
consommateurs du foyer). Résidu inchangé.

---

## 6. Ce qui est livré

* `engine/playbook/should_execute_gates.py` — `1147` corrigé (ENNEMIS), en-tête re-mesuré
  (les trois « résidus » clos, chacun pour une raison différente).
* `engine/playbook/loki_custom.py` — le gate de `1014` + `_can_kill_target`.
* `engine/playbook/noncomparable/_base.py` — `count_eligible_normal_attack_targets`, le foyer de
  COMPTE dont le prédicat booléen dérive.
* `engine/playbook/common.py` — `_is_boss` TRI-ÉTAT (substrat réfuté en live).
* `engine/playbook/bespoke.py` — l'attestation de code MORT de `1175`.
* `scripts/python/probe_419r1tr14r5r2r1r1r1r3r1_gates.py` — **le probe que la fiche de `-r3` citait
  et qui n'existait pas** : étapes 1 (slots) et 2 (reachability) offline, 2b/3/4/5/6/7 live.
* `scripts/python/tests/engine/test_419r1tr14r5r2r1r1r1r3r1_gates_offline.py` — six crans.
* Le cran `1147` du fichier de test de `-r3` **figeait le bug** : il est retourné, avec ses
  contre-épreuves (un ALLIÉ porteur ne suffit PAS, le CASTER ne se valide pas lui-même).

---

## 7. Ce qui n'est PAS couvert

* **Le bras LIVE d'`Untargetable`** (§5) — obstacle nommé, montage décrit.
* **`1010` reste sans prédiction portée** (§4.2) : son gate est inerte tant que
  `$$MakeDamagePredictions` ne l'est pas. Le probe garde le constat par un cran qui **rougira** le
  jour où le port produira des candidats — c'est un déclencheur, pas un constat figé.
* **`1056` n'est pas discriminable live** (§4.3), par construction.
* **`1095` n'a pas de témoin natif POSITIF** (§4.1) : la bascule du port est mesurée au seuil exact
  et le refus natif sous le seuil aussi, mais le cast natif AU-DESSUS n'est pas prouvé — l'attaque
  normale rafle l'argmax à un hex.
* **La clause BOSS reste inerte** tant que `<composant>+0x88` n'est pas publié (§3). Ce n'est plus
  un proxy faux, c'est un canal muet qui se dit muet.
* **Le 3ᵉ argument de `GetValidTargets`** (`Loki_NormalAttack` littéral vs `GetNormalAttackType`)
  n'est pas modélisé (§1.1) : invisible sur les deux étages portés, dit explicitement.

---

## 8. Résidus NOMMÉS

* **`#419-r1-tr14-r5-r2-r1-r1-r1-r3-r1-r1`** — `UnitExtensions$$IsBoss` n'est publié par aucun
  canal ; le trait `Boss` a été RÉFUTÉ comme substrat. `BLOCAGE: capteur`, point d'ancrage
  `IdunBattle.Entities.UnitExtensions$$IsBoss` (ou l'octet `<composant>+0x88` dans `combatSnapshot`).
* **`#419-r1-tr14-r5-r2-r1-r1-r1-r3-r1-r2`** — `StormOfFlensingBladesPlaybook$$MakeDamagePredictions`
  n'est pas portée (RE complet en §4.2, y compris les deux quirks : liste VIDE sur SURE-kill,
  double comptage). Tant qu'elle ne l'est pas, le gate de `1010` est inerte et le port ne propose
  jamais une ability que le natif propose. `BLOCAGE: etage`.
* **`#419-r1-tr10-r4`** garde son bras de confrontation `Untargetable` ouvert (§5) — le volet
  OFFLINE est désormais gardé.
