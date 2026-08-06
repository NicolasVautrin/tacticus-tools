# Case #26 — RadSaturationPlaybook (face DECISION du Skitarii Vanguard)

Etat RE de la **face DECISION** de RadSaturation (le passif contamination du Skitarii Vanguard
`admecSmnVanguard`, mecanique deja portee #25 + branche 2 UnitDisplaced #26).

> ⚠ **CETTE FICHE A ETE FAUSSE SUR TROIS FAITS, ET ILS ALLAIENT TOUS DANS LE MEME SENS.** Elle
> specifiait un terme NEGATIF (`-25`) sur LES DEUX CAMPS, filtre par l'immunite a `Contaminated`.
> Le build courant dit : terme POSITIF (`+10`), sur les **ALLIES** seuls, filtre par
> `HasActiveAbility(DoctrinaImperatives)`. Le detail, la mesure live qui separe les deux camps et
> la contre-epreuve vivent dans **`docs/rl/case-477r29-radsaturation-camp.md`** ; ce qui suit est
> l'etat FINAL, pas l'historique.

## Contrat (build `rnca9r7q6c`)

- **Famille = `Playbook<T>` step-utility** (ni Comparable ni NonComparable). Override
  `Calculate{Movement,Attack}UtilityInStepsInternal -> IEnumerator<Fix64>` (yield 1 step).
- **Cle d'enregistrement = 1202** (`TriggeredAbilityType.RadSaturation`) :
  `IdunBattle.AI.Playbook.Loki.RadSaturationPlaybook$$.ctor` passe `0x4b2`.
  `IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders` mappe 1202 -> `new RadSaturationPlaybook()` ;
  `LoadPlaybook(1202)` est appele par le dispatcher `TriggeredAbilitiesUtility(2)`.

## Formule MOVE — `…RadSaturationPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`

```
units = query.<slot 0x83 = GetAdjacentFriends, 2 arguments>(case.MovementTile, case.Unit@+0x10)
n     = System.Linq.Enumerable.Count(units, <>c.<>9__2_0)
w     = <delegue de lookup>("RadSaturation_AdjacentMarshals")     // Utilities.Default.TriggeredAbilities = 10
yield Fix64.op_Implicit((int)(w * n))
```

- **Le predicat a un SYMBOLE sur ce build** (il n'en avait pas sur `gqfc5mff6c`, d'ou le pari
  d'alors) — `…RadSaturationPlaybook.u003Cu003Ec$$u003CCalculateMovementUtilityInStepsInternalu003Eb__2_0` :
  `return IdunBattle.Entities.UnitExtensions$$HasActiveAbility(f, 0x45e);`
  `0x45e` = 1118 = **`ActiveAbilityType.DoctrinaImperatives`**, l'ACTIVE d'`admecMarshall`
  (« Tan Gi'da »). D'ou le nom de la cle BC. L'ordinal ne discrimine pas (1118 nomme
  `TerrorsLament` en `TriggeredAbilityType`) : c'est la CALLEE qui tranche.
- **Le litteral BC est RESOLU**, pas devine :
  `probe_212_bc_key_literals.py --symbol "…RadSaturationPlaybook…MoveNext"` -> slot `+0x33b4a50`
  -> `'RadSaturation_AdjacentMarshals'`, `[BC Default.TriggeredAbilities = 10]`.
- **SELF compte.** Aucun `RemoveAll(u.Id == case.Unit.Id)` dans ce corps, contrairement au corps
  partage `AdjacentUnitPreference`. Inerte PAR ALGEBRE sur ce build (aucune unite ne porte a la
  fois 1202 et 1118) — assertionne dans les deux sens par la garde, jamais tu.
- **ATTACK = `Fix64.op_Implicit(0)`** (`…u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`) :
  RadSaturation ne biaise QUE le move.

⇒ **Terme = +10 par ALLIE ADJACENT porteur de `DoctrinaImperatives`** — il ATTIRE le Vanguard vers
son Marshal. Il ne penalise rien, et il ne regarde ni la contamination ni les ennemis.

## Ce que la fiche disait, et qui est mort

| ecrit ici jusqu'au 2026-08-06 | ce que dit le build |
|---|---|
| « adjacent units, ring-1, **both teams** » <!-- [slot-attribution:refute] --> | `GetAdjacentFriends`, arite 2 (slot `0x83`) : **les ALLIES** |
| multiplicateur `Utilities.Default.Contaminated.AffectedUnit` = **-25** | `…TriggeredAbilities.RadSaturation_AdjacentMarshals` = **+10** |
| predicat = « allie non immunise a `Contaminated` » (`ContaminatedEffect$$EntityIsImmuneToEffect`) | `HasActiveAbility(0x45e = DoctrinaImperatives)` — l'immunite n'intervient PAS |
| face DECISION « ENREGISTREE-MAIS-MORTE, ne rien porter » | **REFUTE** : le natif applique le terme, mesure `X_nat = 10` |

Le raisonnement d'alors (« un `-25` par voisin n'a de sens que pour eviter de contaminer ses
allies ») etait une deduction de PLAUSIBILITE sur un lambda gshared illisible. Elle a produit trois
faits faux d'un coup, et le seul qui ait ete corrige avant #477-r29 l'a ete au titre de la
CITATION (#477-r25), pas de la specification.

⚠ **La confusion avait un modele reel dans le meme build** : `IdunBattle.AI.Utilities.AttractMechanicalsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`
(feuille `DoctrinaImperatives_AttractMechanicals`) lit le MEME predicat `0x45e` et interroge, LUI,
le slot `0x7a` = `GetAdjacentUnits` a QUATRE arguments — donc les DEUX CAMPS, avec un `!= case.Unit`
explicite. La specification ecrite ici decrivait en fait CETTE feuille-la. Elle est **inerte cote
port** : residu **#477-r31**.

## Porteurs et confrontation

- `admecSmnVanguard` (SUMMON de ControlEdict / DoctrinaImperatives Protector), plus
  `admecNpc1Vanguard` / `admecNpc1VanguardSurv` (npc). Tous **Mechanical**, donc self-immunes a
  leur propre contamination (`ContaminatedEffect$$EntityIsImmuneToEffect` : `ContagionsOfNurgle`
  2027 | `IsMechanical`) — fait qui reste vrai, et qui concerne la face RUNTIME, pas ce terme.
- Le summon s'OBSERVE, il ne se COMMANDE pas (#291) : la confrontation passe par une **GREFFE** du
  passif sur un heros du pool (`catalog_inject.graft_passive_ability`), legitime ici parce que le
  corps ne lit ni stats ni traits du caster. Le greffon doit etre **NON Mechanical**, sinon la
  feuille `DoctrinaImperatives_AttractMechanicals` ajoute son propre `+10` sur les memes tuiles.

## Bilan #26

- **Face RUNTIME** (contamination sur move #25 + sur push #26 volet 2) : PORTEE + VALIDEE (93fac2f).
- **Face DECISION** : **PORTEE** (`engine/playbook/rad_saturation.py`, registre
  `TRIGGERED_MOVE_PLAYBOOKS`) et **CONFRONTEE LIVE** par #477-r29 — `X_nat` = 10 sur le bras ALLIE,
  0 sur le bras ENNEMI, 0 desaccord sur 8 tuiles.

## Symboles clefs

`…RadSaturationPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` (MOVE) ;
`…u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext` (ATTACK = 0) ;
`…RadSaturationPlaybook$$.ctor` (0x4b2) ;
`…RadSaturationPlaybook.u003Cu003Ec$$u003CCalculateMovementUtilityInStepsInternalu003Eb__2_0` (le predicat) ;
`IdunBattle.Entities.UnitExtensions$$HasActiveAbility` ;
`IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$EntityIsImmuneToEffect` (face RUNTIME) ;
cousins : `IdunBattle.AI.Utilities.OptimizedGait_AdjacentFriendsUtility.u003CEvaluateAttackInStepsu003Ed__1$$MoveNext`
(meme slot `0x83`, poids BC **0** — cf. `case-477r29` sec. 5) et
`IdunBattle.AI.Utilities.AttractMechanicalsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext`
(slot `0x7a`, les deux camps).
