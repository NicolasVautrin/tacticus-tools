# Case #26 — RadSaturationPlaybook (face DECISION du Skitarii Vanguard)

Etat RE de la **face DECISION** de RadSaturation (le passif contamination du Skitarii Vanguard
`admecSmnVanguard`, mecanique deja portee #25 + branche 2 UnitDisplaced #26). Ce doc fige les
faits durs pour ne PAS re-deriver apres /compact.

## Contrat (PROUVE, build ghidra gqfc5mff6c)

- **Famille = `Playbook<T>` step-utility** (3e famille, NON portee ; ni Comparable ni NonComparable).
  Override `Calculate{Movement,Attack}UtilityInStepsInternal -> IEnumerator<Fix64>` (yield 1 step).
- **Cle d'enregistrement = 1202** (`TriggeredAbilityType.RadSaturation`). `.ctor @181186cc0` passe 1202.
  Dispatch : `PlaybookDatabase.InitializePlaybookBuilders @1810d02b0` mappe 1202 -> `new RadSaturationPlaybook()`.
  Charge par `LoadPlaybook(1202)` dans `ActiveAbilityActionGenerator` (le bucket per-position).

## Formule MOVE (PROUVE — MoveNext @181193c90, decompile lu ligne a ligne)

```
utility = Fix64.FromInt( multiplier * count )
  count      = System.Linq.Enumerable.Count( coll, predicate )
  coll       = IBattleQuery.slot0x82( service, casterTile, unit )
  multiplier = context.<vtbl+0x18>( dict@+0x40, ENUM=DAT_18322a4c0, &out, default@+0x28 )   # GetValue(enum)->int
```
- `casterTile = UtilityAttackCase.get_CasterTile(case)` (d__2+0x28) ; `unit = case+0x10`.
- **ATTACK utility = `Fix64.FromInt(0)`** (MoveNext @18118ece0) -> RadSaturation ne biaise QUE le move.

## Residus resolus (4 des 5 faits)

1. **multiplier = `-25`** = BC `Utilities.Default.Contaminated.AffectedUnit` (LU dans data/seed-bc.json ;
   `MovementSuggestion.Contaminated` = null -> canal `Default`). `UtilityType.Contaminated = 25`
   (`engine/utilities/utility_type.py:37`). **A LIRE, jamais hardcoder** : `wt.sub("Contaminated","AffectedUnit")`.
2. **slot 0x82 = adjacent units, ring-1, BOTH teams** (PROUVE par elimination : le MEME slot 0x82 est
   utilise par `OptimizedGait_AdjacentFriendsUtility` = une utility de FRIENDS -> slot 0x82 ne peut PAS etre
   enemy-only ; c'est un `GetAdjacentUnits(tile, unit)` sans arg de range = ring-1). 18 playbooks step-utility
   appellent slot 0x82 pareil (RelentlessMarch @181192d50 fait get_Count SANS predicat ; RadSaturation FILTRE).
3. **immunite = exclure Mechanical + ContagionsOfNurgle(2027)** (`ContaminatedEffect.EntityIsImmuneToEffect
   @180f3a400`). Helper deja porte : `engine/runner/operations/triggers/effect_triggers.py::_is_immune_to_contaminated`
   (runner) ; `UnitTrait.ContagionsOfNurgle = 2027`.
4. **enum DAT_18322a4c0 = UtilityType.Contaminated (25)** (via la cle BC `Contaminated`).

## Le predicate (equipe comptee) — RESOLU par semantique decompilee (RE, pas inference-en-l-air)

Le `predicate` (`Func<T,bool>`, singleton `<>c` = DAT_1831bd4e8, MethodInfo = **DAT_183224b80**) est un
**lambda gshared resolu au RUNTIME** : AUCUN symbole ghidra (Playbook<T> full-generic-sharing partout ->
`__Il2CppFullySharedGenericType` ; DAT_183224b80 est un slot MethodInfo* nul dans l'image statique, rempli
par FUN_1801f2030/MetadataCache au runtime ; cctor <>c @18119b7a0 ne cree QUE le singleton, ne reference
PAS le pointeur de fonction du lambda). => le CORPS du lambda est INDETERMINABLE en RE statique.

MAIS l'EQUIPE comptee est fixee par la **semantique decompilee** de ContaminatedEffect (pas par un pari) :

- **`ContaminatedEffect.EntityIsImmuneToEffect @180f3a400`** : immunite PUREMENT par trait ->
  `HasTrait(0x7eb=2027 ContagionsOfNurgle)` OU `IsMechanical` => immune ; sinon `BaseEffect` (defaut).
  **AUCUN test d'equipe.**
- **`ContaminatedEffect.CreateHandleTriggerAbilitiesInternal @180f3a1d0`** : le DoT (On(0x12) & Not(HasEffect
  0x4dd) -> AddEffectBehavior ; On(4) & AreEqual(unit-on-tile) & Not(HasEffect) -> AddEffectBehavior) n'a
  **AUCUNE porte IsEnemy/IsFriend** sur la victime. Le selecteur `DSLFactory.Units(...,1,3,0)` + immunite
  trait => Contaminated frappe TOUT non-immune sur la tuile, **ami comme ennemi (friendly-fire)**.

=> Le Skitarii Vanguard est **Mechanical** = self-immune a sa propre contamination. Un **-25 par unite
adjacente** en utility de MOVE n'a de sens tactique QUE pour **penaliser l'adjacence a tes propres allies
non-immunises** (eviter de les contaminer). Penaliser l'adjacence aux ENNEMIS serait a l'envers (tu VEUX
les ennemis dans ta contamination). **DONC predicate = adjacent ALLIES non-immunises, ring-1.**

Deuxieme sous-fait non lisible (le lambda filtre-t-il l'immunite ?) : porte AVEC le filtre immunite (compte
= allies *harmables*, coherent avec "AffectedUnit" ; reutilise le helper `_is_immune_to_contaminated` deja
porte). Les DEUX sous-faits (equipe=allies, filtre-immunite) sont ensuite **confrontes en live** par
agreement-validation (`engine_validate.py`, metrique POSITIONING) : si le positionnement natif matche,
c'est confirme ; s'il flippe, on revise (drop immunite, ou flip equipe). La validation EST la capture live.

## Validation-prep (fait durable)

Le Skitarii Vanguard (`admecSmnVanguard`, summon de ControlEdict/DoctrinaImperatives Protector) porte les
traits **Summon + Mechanical** (confirme : `engine/runner/operations/triggers/loki/control_edict.py`
`SUMMON_TRAITS = ("Summon","Mechanical")` + `AttackWithMinions @180e1d150`). => **self-immune** a sa propre
contamination (immunite = Mechanical, cf. EntityIsImmuneToEffect @180f3a400). Coherent avec le -25 "eviter
de contaminer les allies NON-immunises" : le Skitarii lui-meme ne compte jamais dans son propre count.
Pour le scenario d'agreement-validation : placer des allies **NON-Mechanical / non-Nurgle** adjacents au
Skitarii pour rendre le -25xcount non nul et dominant sur le choix de tuile de move.

## Integration -- SEAM CONTESTE : TriggeredAbilitiesUtility semble ENREGISTREE-MAIS-MORTE (a trancher)

**Verdict re-expert #1 (a REVISER)** : consumer = chaine `TriggeredAbilitiesUtility.<EvaluateMovementInSteps>d__2
@1810fda80` (somme sur les triggered abilities de l'unite) -> leaf `ATriggeredAbilityUtility.<EvaluateMovementInSteps>d__3
@1810e4160` (guard slot+0x258 "unite a l'ability?" ; sinon yield 0 ; sinon LoadPlaybook slot+0x278 ->
playbook.CalculateMovementUtilityInSteps -> Fix64.FromInt(val) * weight slot+0x268). Base
`ATriggeredAbilityUtility` calcule `GetFriendsAdjacentToMovementTile @1810ccb40` / `GetFriendsSurroundingToMovementTile
@1810ccc30` => **corrobore predicate=ALLIES par une methode native nommee (plus une inference).** Decision-path
propose = MovementActionGenerator / best_move_faithful.

**CONTRADICTION trouvee a l'integration (RE moi-meme, ghidra gqfc5mff6c)** — le seam best_move_faithful est
FAUX ou la face est morte :
1. `_composedUtilityLookup` (InitializeUtilities @1810C9390, lu EN ENTIER, doc journal §13.3) = 7 composites,
   **TriggeredAbilities dans AUCUN** : MovementSuggestion(32)=[Tile7,TileDistance33] ; UnitMovement(6)=[Tile7,MinDist16] ;
   UnitMovementFromTemporary(5)=[UnitMovement6,MaxDistUnitTile17] ; Damage34 ; Repair46 ; Spawn0 ; Tile7=[29].
2. `MovementActionGenerator.<GenerateActions>d__6 @181199d50` evalue `FUN_1800051a0(0, DAT_1831eee00, cases,
   children, UtilityDefinition((isTemp^1)+5))` = def 5|6 = UnitMovement(6)/FromTemporary(5) = **Tile+MinDist SEUL**.
   Ne consomme PAS TriggeredAbilitiesUtility. => best_move_faithful (qui modelise UnitMovement(6)) est le MAUVAIS seam.
3. xrefs `TriggeredAbilitiesUtility.ctor @1810f32c0` = DATA + SEUL appelant = builder on-demand `b__18_17 @1810c1ba6`.
   xrefs des 3 publics `EvaluateMovementInSteps @1810f31e0` / base @1810ccad0 / `EvaluateAttackInSteps @1810f3170`
   = **TOUS DATA, ZERO call-site**.
4. Memoire projet "AI overwatch blind spot" : l'IA fonce dans l'overwatch (ignore l'awareness triggered-ability
   en pratique) -> corrobore NonOwner (et p.-e. Owner) NON CABLE.

=> **VERDICT DEFINITIF (re-expert, confirme) : TriggeredAbilitiesUtility (face DECISION de RadSaturation) est
ENREGISTREE-MAIS-MORTE dans ce build. NE RIEN PORTER cote decision — c'est un GAP AI-inert, PAS un miss
d'agreement.** Le natif n'applique JAMAIS le -25xcount a une decision IA dans gqfc5mff6c.

### Preuve d'INATTEIGNABILITE (VAs, gqfc5mff6c) -- pas une heuristique

1. **Le seul resolveur d'utility d'un decideur = `IdunRunner.Initialize @180e35400`**, qui appelle
   `UtilitiesDatabase.GetUtility @1810c8b30` exactement DEUX fois : `GetUtility(db, 0x20=32, 2)` @180e361f9
   = **MovementSuggestion(32)** ; `GetUtility(db, 0x22=34, 2)` @180e3621f = **Damage(34)**. Ce sont les 2
   utilities top-level cablees (move + attaque).
2. **`GetUtility @1810c8b30` = 3 call-sites reels** (le reste DATA/vtable) : ces 2 + le resolveur recursif de
   children de composite `<>c__DisplayClass16_0.<GetUtility>b__0 @1810c2e9b`. => une utility n'existe QUE si
   (a) demandee par Initialize, ou (b) enfant d'un composite demande.
3. **TriggeredAbilities (owner+nonowner) n'est ni (a) ni (b)** : absente des args de Initialize ET enfant
   d'aucun des 7 composites (`_composedUtilityLookup` lu en entier). Le builder b__18_17/b__18_18 remplit le
   REGISTRE de factories mais rien ne REQUETE ces cles.
4. **Chaine entiere DATA-only (0 UNCONDITIONAL_CALL)** : EvaluateMovementInSteps @1810f31e0 / base @1810ccad0 /
   EvaluateAttackInSteps @1810f3170 / leaf d__3 @1810e4160 / RadSaturationPlaybook InStepsInternal @181186c40 +
   @18118ece0. Le composite owner d__2 @1810fda80 -> LoadPlaybook -> -25xcount n'est atteignable QUE si
   TriggeredAbilitiesUtility est instanciee+iteree = jamais.
5. Corrobore la memoire "AI overwatch blind spot" (l'IA ignore l'awareness triggered-ability = meme racine
   structurelle cote OWNER).

**Portee du verdict = gqfc5mff6c uniquement.** Garde non-regression possible (non requise, preuve statique
airtight) : Skitarii (1202) live, verifier que sa decision de move est INSENSIBLE au nombre de voisins ring-1
(aucun biais -25xcount) -> confirme l'inertie AI.

### Bilan #26
- **Face RUNTIME** (contamination sur move #25 + sur push #26 volet 2) : PORTEE + VALIDEE + COMMITTEE (93fac2f).
- **Face DECISION** (RadSaturationPlaybook -25xcount) : **AI-inerte dans ce build -> aucun port** (ce doc = la trace).
- => #26 termine : volet 2 code + volet 1 resolu en GAP-documente (no-op fidele au natif).

- Nouveau `engine/playbook/insteps/` (famille step-utility) : `_base.py` (contrat `calculate_movement_utility
  (tile, ctx)->float` + registre keye 1202) + `rad_saturation.py` (`RadSaturationPlaybook`, ABILITY_ID=1202).
- Terme ADDITIF au scoring de MOVE-position de l'ability-action generator (le `full`/CalculateActionUtility
  per-position, `engine/ai/action_generators.py`), gate "unite possede 1202". PAS le last-resort
  `MovementActionGenerator`/`best_move_faithful` (celui-la = MovementSuggestion) ni le bucket NonComparable.
  (Archi : `docs/rl/playbook/architecture.md` — CalculateActionUtility @181406ee0 = predictions + Tile7 ; les
  termes per-position sont ~plats -> RadSaturation discrimine la position.)
- Reutiliser `engine/battle_query.py` (ring-1 adjacents), `UnitTrait.ContagionsOfNurgle`, `_is_immune_to_contaminated`.

## VAs clefs
RadSat MoveNext @181193c90 (MOVE) / @18118ece0 (ATTACK=0) ; factory @181186c40 / @181186bf0 ; .ctor @181186cc0 ;
<>c cctor @18119b7a0 ; predicate MethodInfo = DAT_183224b80 (runtime) ; enum = DAT_18322a4c0=UtilityType.Contaminated(25) ;
IBattleQuery = DAT_18327ff80, slot 0x82 = GetAdjacentUnits (ring-1, both teams) ; immunite @180f3a400 ;
cousins : RelentlessMarch @181192d50 (get_Count nu), ArchContaminator @181177b00, OptimizedGait_AdjacentFriends
(partage slot 0x82). multiplier BC = Utilities.Default.Contaminated.AffectedUnit = -25.
