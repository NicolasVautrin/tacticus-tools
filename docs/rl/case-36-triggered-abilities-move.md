# Case #36 — TriggeredAbilitiesUtility(2) comme terme de tuile move

**Statut : ✅ RÉSOLU + PORTÉ (2026-07-19). Voir « RÉSOLUTION FINALE » en bas — le modèle correct est
« abilities déclenchées DU MOVER » (GuardianOrganism du TyrantGuard), PAS « carriers adjacents ».
Les sections intermédiaires (driver 909, carriers, contradiction) sont l'HISTORIQUE d'investigation ;
leurs modèles sont SUPERSÉDÉS par la résolution.**

## Symptôme (agreement move-pur, seed 909)

Le composite move `UnitMovement(6) = [Tile(7), MinDistanceToClosestEnemy(16)]`. Dans `Tile(7)`,
la feuille `TriggeredAbilities(2)` est **droppée à 0** dans notre port (`engine/utilities/tile.py:486`,
`2: ("TriggeredAbilities", None)`). Or la capture L3 (ai-trace) montre qu'elle **score par-tuile**
et **décide** deux misses :

- **s4** : natif choisit (3,2) via `TrigAb=30 + TileEffects=9` malgré une Elevation inférieure.
- **s19** : natif choisit (4,3) via `TrigAb=90 + MinDist`.

Notre port, en la laissant à 0, ne reproduit pas ces choix → miss move-pur.

## RE — ce que type 2 calcule vraiment (décompile gqfc5mff6c)

Type 2 n'est **PAS une feuille scalaire** : c'est un **dispatcher vers les playbooks par-capacité**
(le commentaire `tile.py:483-486` avait raison sur la nature). Chaîne native :

### `TriggeredAbilitiesUtility.<EvaluateMovementInSteps>d__2.MoveNext @1810fda80`

```
acc = Fix64(0)
enum = collection( case ).GetEnumerator()          # les unites candidates (voir helpers ci-dessous)
for unit in enum:
    playbook = PlaybookDatabase.LoadPlaybook( case.playbookDb@0x48, unit.get_Id() )   # @LoadPlaybook
    if playbook == null: continue
    inner = playbook.CalculateMovementUtilityInSteps( case@0x20, case+0x58 )  # iface ITriggeredAbilityPlaybook m.2
    for v in inner:
        acc = acc + v                              # Fix64 op_Addition
yield acc
```

- `case+0x48` = la `PlaybookDatabase` ; `case+0x58` = un contexte passé au playbook (steps ?).
- `PlaybookDatabase.LoadPlaybook(db, unitId)` charge le playbook triggered-ability de l'unité.
- La valeur par unité = **somme des utilités de mouvement yieldées par SON playbook** pour la tuile candidate.

### Base `ATriggeredAbilityUtility.<EvaluateMovementInSteps>d__3.MoveNext @1810e4160` (forme abstraite)

Confirme la forme générale d'un `ATriggeredAbilityUtility` :
```
if !gate(case):  yield Fix64(0)          # vtbl+0x258 (gate ShouldEvaluate)
else:
    ev   = getEvaluator(case)            # vtbl+0x278
    val  = ev.<iface DAT_1831e7018 m.2>(case)   # int  (valeur playbook)
    w    = getWeight()                   # vtbl+0x268 (Fix64)
    yield Fix64.FromInt(val) * w
```
=> **score = FromInt(valeur_playbook) x poids**. Les 30/90 = poids x valeur.

### Helpers de ciblage `ATriggeredAbilityUtility` (le "proche du cas")

- `GetUnitsWithAbility @1810ccce0` = `DSLFactory.UnitsWithTriggeredAbility(field@0x60)` — filtre par type de trigger (`@0x60`).
- `GetFriendsAdjacentToMovementTile @1810ccb40` = `Friends( Entity(case.unit) ) INTER AdjacentUnits(CasterTile) MINUS self`.
- `GetFriendsSurroundingToMovementTile @1810ccc30` = `SurroundingFriends(..., radius=param_3)`.

Donc l'ensemble itéré = **amis (même équipe) porteurs d'une capacité déclenchée, adjacents/entourant la tuile candidate**, moins soi-même. Intuition : "me déplacer ICI met mes amis à capacité-déclenchée (overwatch, ripostes, auras trigger) en position de couvrir cette tuile".

## Conséquence de scope

#36 n'est pas un one-liner de feuille : c'est une **tranche playbook-engine** (`project_playbook_engine`).
Port fidèle =
1. Sélecteur DSL : amis-avec-trigger adjacents/entourant la tuile candidate (helpers ci-dessus).
2. `PlaybookDatabase.LoadPlaybook(unitId)` par unité.
3. `CalculateMovementUtilityInSteps` de chaque playbook triggered-ability (au moins ceux présents dans
   les rosters de test) — c'est LA pièce lourde (une famille de playbooks : `TriggeredAbilityPlaybook`,
   `AdjacentUnitPreferenceTriggeredAbilityPlaybook @18134eb30`, etc.).
4. Le poids (`vtbl+0x268`) — à capturer (probablement issu de la `UtilityDefinition`/BC, pas hardcodé).

## Driver concret 909 IDENTIFIÉ (analyse roster live, sans reinject — 2026-07-19)

Acteur des deux misses = **u89 tyranTyrantGuard** (team 1). Le terme type-2 itère les **amis porteurs
d'une capacité déclenchée "préférence-adjacence"** et somme, par ami, la valeur de SON
`AdjacentUnitPreferenceTriggeredAbilityPlaybook` (buff d'allié adjacent → le playbook incite les alliés
à se coller au porteur). Les amis à trigger de ce roster :

| unit | ability | id | playbook |
|------|---------|----|----------|
| u87 custoBladeChampion | **MartialInspiration** | 1191 | AdjacentUnitPreference |
| u91 genesPatriarch | **MightFromBelow** | 1165 | AdjacentUnitPreference |
| u95 custoKyrus | **VigilanceEternal** | 1202 | AdjacentUnitPreference |

Le score = **~30 par ami-à-trigger ADJACENT (hexdist=1) à la tuile candidate** :

- **s4** winner (3,2) : u87@(3,3) adjacent → **1 ami = 30**. loser (0,3) : 0 ami → **0**. (natif prend (3,2)).
- **s19** winner (4,3) : u87@(4,4), u91@(5,4), u95@(5,3) adjacents → **3 amis = 90**. loser (4,2) : u95 seul → **30**.
  (natif prend (4,3) ; delta TrigAb +60 vs (4,2)).

=> **TrigAb(2) move = Σ_{ami à trigger AdjacentUnitPreference, adjacent à la tuile} playbookValue(≈30)**.
Le pattern colle EXACTEMENT aux deux pas et le delta favorise la tuile native. Match 30/90 confirmé.

### Formule du playbook `AdjacentUnitPreferenceTriggeredAbilityPlaybook.<CalculateMovementUtilityInStepsInternal>d__1.MoveNext @18134eb30`

`value = Fix64.FromInt(iVar14)` où
`iVar14 = Σ_{u in AdjacentUnits} weightAdj(u)  +  Σ_{u in SurroundingUnits} weightSurr(u)`
(deux loops bornées par `Math.Min(count, cap)`). Poids/cap = slots vtbl du playbook (0x208/0x218 =
poids par-unité adjacent/surrounding ; 0x228/0x238 = caps ; 600/0x248 = getters de collections), lus
depuis la **config AI de l'ability**. Empiriquement la somme = 30 par ami dans ce roster ; la valeur
EXACTE (constante 30 vs somme dépendante du voisinage) reste à capturer pour le port (voir ci-dessous).

## Reste pour le PORT (tranche playbook-engine)

1. **Sélecteur** : amis (même team que l'acteur) avec une ability de playbook AdjacentUnitPreference,
   adjacents à la tuile candidate. (Étendre au-delà des 3 abilities : énumérer la famille complète
   `AdjacentUnitPreferenceTriggeredAbilityPlaybook` — quelles abilities l'utilisent.)
2. **Valeur par ami** : porter `d__1.MoveNext @18134eb30` (Σ poids adjacents + surrounding, caps),
   ou — si la config donne un poids constant — capturer ce poids (30 ?) depuis la config AI de l'ability.
   NE PAS hardcoder 30 sans preuve config (règle no-fit-scalaire).
3. **Poids du terme** dans le composite (vtbl+0x268 de `ATriggeredAbilityUtility`) — probablement 1 ici
   (le 30 vient du playbook, pas d'un multiplicateur externe), à confirmer.
4. Validation : rejouer 909 s4/s19 ; la tuile native doit repasser argmax une fois TrigAb portée.

### Décomposition EXACTE 30/90 (optionnel, plus tard) — reinject requis

Enrichir la capture ai-trace L3 pour logguer, sous le `utility_score` de type 2, les `LoadPlaybook(unitId)`
+ valeur par playbook (split du 30/90 par ami).

## Diagnostic AUTO du terme manquant (leviers 1+3, VALIDÉ 2026-07-19)

`engine_agreement_stages.py` NOMME désormais ce terme manquant automatiquement sur tout miss move
(au lieu du fourre-tout `move-formula`), via deux leviers (docs : agreement-stages.md) :

- **Lever 1 (offline, sans capture)** : précondition « ami à ability `AdjacentUnitPreference`
  (`ADJ_PREF_TRIGGER_ABILITIES` = {1191,1165,1202}) adjacent à la tuile candidate ». Tag `suspect` +
  `est_delta = 30 x (nb amis adj nat - nb amis adj eng)`. 909 : s4 `est_delta=30` (u87), s19 `est_delta=60`
  (u87+u91+u95 vs u95).
- **Lever 3 (`--l3`, capture L3 SOLO)** : diff natif par-feuille sur la fenêtre seq du pas → `native_terms`
  + `missing_terms`. 909 confirme les scores EXACTS : s4 (3,2)=30 / (0,3)=0 ; s19 (4,3)=90 / (4,2)=30.

**Le breakdown natif L3 prouve que TrigAb est le SEUL terme manquant** (Elevation/TileEffects/MinDist
matchent notre port) et qu'il FLIPPE le choix :
- s4 : (3,2) = Elev20 + TileEff9 + **TrigAb30** + MinDist(-700) = **-641** vs (0,3) Elev50 + MinDist(-700)
  = **-650**. Sans TrigAb, (3,2) = -671 < -650 → on prend (0,3) (le miss). Avec, (3,2) gagne.
- s19 : (4,3) = Elev30 + **TrigAb90** + MinDist(-400) = **-280** vs (4,2) Elev50 + **TrigAb30** +
  MinDist(-500) = **-420**. Delta TrigAb +60 décisif.

=> le port (ci-dessus) fermera s4 + s19 dès que TrigAb(2) sera calculée. ⚠ L3 est SESSION-GLOBALE :
lancer `--l3` en SOLO (garde-fou `--l3-force` ; un walk concurrent d'un autre agent crashe IL2CPP — cf.
memory `feedback_l3_session_global_crash`).

## VAs

- `TriggeredAbilitiesUtility.<EvaluateMovementInSteps>d__2.MoveNext @1810fda80`
- `TriggeredAbilitiesUtility..ctor @1810f32c0` (hérite `UnitTimelines.TypeToTimeline..ctor`)
- `ATriggeredAbilityUtility.<EvaluateMovementInSteps>d__3.MoveNext @1810e4160`
- `ATriggeredAbilityUtility.EvaluateMovementInSteps @1810ccad0`
- `ATriggeredAbilityUtility.GetUnitsWithAbility @1810ccce0`
- `ATriggeredAbilityUtility.GetFriendsAdjacentToMovementTile @1810ccb40`
- `ATriggeredAbilityUtility.GetFriendsSurroundingToMovementTile @1810ccc30`
- `PlaybookDatabase.LoadPlaybook` (chargé via `case@0x48`)
- iface `ITriggeredAbilityPlaybook` (DAT_1831e7018 / DAT_1831ebb60) méthode 2 = `CalculateMovementUtilityInSteps`
- `TriggeredAbilityPlaybook.CalculateMovementUtilityInSteps @18150f630`
- `AdjacentUnitPreferenceTriggeredAbilityPlaybook.<...>d__1.MoveNext @18134eb30`

## MAJ 2026-07-19 (RE reprise EN DIRECT par l'orchestrateur — l'agent re-expert delegue est MORT, transcript 0 octet)

**CORRECTION MAJEURE du modele "30 flat" ci-dessus : le poids est une CONFIG BC PAR-COMPORTEMENT, pas un 30 constant.**

### Source du poids = CONFIG (preuve config trouvee — resout le no-fit-scalaire)

`Utilities.Default.TriggeredAbilities` (dans la BC, ex. `data/seed-bc.json`) = **dict de 107 poids nommes
par-comportement**, valeurs 5..100. Exemples : `RITESOFBATTLE_AdjacentFriend=10`, `INSPIRINGPRESENCE_AdjacentFriend=10`,
`FABRICATORCLAWARRAY_AdjacentFriend=30`, `SWEEPINGBLOW_AdjacentEnemy=40`, `NOMNOM_LikesAdjacentEnemySummon=100`.
=> Le leaf lit `wt.category("TriggeredAbilities")[<behaviourKey>]` (meme pattern que les feuilles UnitEffects*
qui lisent deja `wt.category("UnitEffectsAdjacent")`). Le "30" observe = le poids config de CES comportements,
**PAS un constant a hardcoder** ; d'autres comportements valent 5/10/15/20/40/50/100.

### Adjacence = BattleQuery (confirme)

`getAdjacentUnits(tile)` = `BattleQuery.GetAdjacentUnits @18105bca0` (rayon 1) ; `getSurroundingUnits` =
`GetSurroundingUnits @181068880` (rayon 2). Boucles `Min(count, cap)` ; caps = getters vtbl (0x228/0x238).

### Ground truth L3 (trace `40-...305Z.jsonl`, 13928 events TriggeredAbilities)

- Playbooks OBSERVES pour le roster 909 : **`MartialInspirationPlaybook`, `MightFromBelowPlaybook`** (+ `Loki_NormalAttackPlaybook`).
  Confirme que MartialInspiration(1191) et MightFromBelow(1165) SONT des carriers AdjacentUnitPreference.
- Total DISPATCHER par-tuile (evt `ability=None playbook=None`) pour **u89 tyranTyrantGuard** : **(3,2)=30** (winner s4),
  (2,2)=30. Coherent avec le case ci-dessus (s4 TrigAb=30).
- Autres movers : `custoBladeChampion` (ability=`ForHonor` -- LIBELLE PERIME, cf. #270 : le tracer
  resolvait l'id 1 via `ability-names.ts`, qui portait alors `1: "ForHonor"` ; 1 n'est pas un membre
  d'`ActiveAbilityType`, le champ trace n'en etait donc pas un) score 10/20/30/60 sur SES propres tuiles ; `adeptHospitaller`
  45/30/15 ; `deathPutrifier` 15/30. => les poids VARIENT (multiples/sommes de poids config par-comportement).
- **`VigilanceEternalPlaybook` ABSENT du top-40 combos** => l'attribution 1202 du case ci-dessus est INCERTAINE
  (a re-verifier ; 1202 n'est peut-etre pas un AdjacentUnitPreference, ou apparait tres rarement).

### BLOCKER pour le PORT (ce qui reste, non trivial)

Le **behaviourKey config par ability est OPAQUE** : (a) PAS derivable du nom (les cles sont des noms de COMPORTEMENT
`RITESOFBATTLE_*`, pas les noms d'ability ; `MARTIALINSPIRATION`/`MIGHTFROMBELOW`/`VIGILANCEETERNAL` ABSENTS des 107 cles) ;
(b) PAS dans le gameconfig (la def d'ability n'a aucun champ playbook/utility) ; (c) donc **baked dans la sous-classe
native du playbook** (`MartialInspirationPlaybook`, `MightFromBelowPlaybook`, ...) qui passe une string au lookup config.

=> **Port fidele bloque sur** : RE ghidra PAR-PLAYBOOK de chaque carrier (`MartialInspirationPlaybook` etc.) pour
extraire la **string de cle config** exacte (donc le poids exact), + confirmer/infirmer 1202. Tant que ce map
`ability -> behaviourKey` n'est pas etabli, le leaf ne peut PAS lire le bon poids (et le "30 flat" serait un fit,
interdit). C'est la vraie piece lourde restante — candidate re-expert/fable-solver (le 1er agent delegue est mort).

### Carriers CORRIGES + ctors (RE 2026-07-19)

- **`VigilanceEternalPlaybook` @181180050 a `EvaluateNonComparable @18117fae0`** => c'est un playbook **NonComparable**,
  PAS un carrier AdjacentUnitPreference de mouvement. **1202 est RETIRE des carriers #36** (l'attribution du case
  ci-dessus etait fausse). Les carriers reels du roster 909 = **MartialInspiration(1191) + MightFromBelow(1165)** SEULEMENT.
- Ctors (decompile) : `MightFromBelowPlaybook..ctor @18114bf20` = `ComparablePlaybook..ctor(this, 0x48d=1165, DAT_18321c880)` ;
  `MartialInspirationPlaybook..ctor @18114b2a0` = `ComparablePlaybook..ctor(this, 0x4a7=1191, DAT_18321c740)`.
  => ces playbooks etendent **ComparablePlaybook** (le playbook du CAST actif de l'ability). Le 3e param (statique
  `DAT_18321c880`/`DAT_18321c740`) est le candidat cle-config / type — **a resoudre via lecture du slot statique**
  (couche suivante). NB relation a clarifier : ComparablePlaybook (cast) vs `AdjacentUnitPreferenceTriggeredAbilityPlaybook`
  (le mouvement-utility charge par `LoadPlaybook` dans le dispatcher) — le trace L3 nomme `MartialInspirationPlaybook`
  sur les events TriggeredAbilities, donc le lien passe par ce playbook (composition ou base commune ITriggeredAbilityPlaybook).
- VAs ajoutees : `MightFromBelowPlaybook..ctor @18114bf20` · `MartialInspirationPlaybook..ctor @18114b2a0` /`.cctor @18114b230`
  · `VigilanceEternalPlaybook..ctor @181180050` /`EvaluateNonComparable @18117fae0` · `BattleQuery.GetAdjacentUnits @18105bca0`
  /`GetSurroundingUnits @181068880`.

### ⚠ CONTRADICTION NON RESOLUE (le modele n'est PAS self-consistant) — STOP RE offline

Retirer 1202 CASSE l'arithmetique s19 du case ci-dessus :
- s19 (4,3)=90 exigeait 3 carriers adjacents (u87 MI + u91 MFB + **u95 VigilanceEternal**) x30. Sans u95 => 2 carriers => 60, pas 90.
- s19 (4,2)=30 etait attribue a "u95 seul". Sans u95 carrier => (4,2) devrait etre 0, pas 30.

Donc AU MOINS une hypothese est fausse parmi : (a) poids flat-30 (peut varier : MI=?, MFB=?, un 3e=?), (b) le set
de carriers, (c) "1202 pas un carrier" (VigilanceEternal a un cast NonComparable MAIS pourrait AUSSI porter un
comportement triggered AdjacentUnitPreference SEPARE — un ability peut avoir un behaviour triggered independant de son
playbook de cast). Le gameconfig ne relie PAS ability->behaviourKey ; les defs d'ability sont des configs d'ATTAQUE
(minDmg/nrOfHits), aucun champ playbook/utility/behaviour.

**=> La resolution fidele necessite soit (1) un PROBE LIVE lisant les sous-scores TriggeredAbilities PAR-CARRIER a
s19 (split du 90) + le weight-field de chaque `AdjacentUnitPreferenceTriggeredAbilityPlaybook` instance, soit (2) une
RE de la REGISTRATION triggered-behaviour->config-key (couche non atteinte). PAS un port a l'aveugle.** Cas dur
multi-couches a verdicts qui se retournent (flat-30 -> config-par-behaviour -> carrier corrige -> contradiction s19)
=> candidat **fable-solver** (ou re-expert frais avec mandat PROBE LIVE). Findings persistes ; port NON fait.

*(NB : les deux options ci-dessus se sont averees inutiles — la contradiction est tombee par pur decompile,
voir la RESOLUTION FINALE ci-dessous.)*

## ✅ RÉSOLUTION FINALE (2026-07-19, décompile pur — AUCUN reinject)

### Le modèle correct : les abilities déclenchées DU MOVER, pas des « carriers adjacents »

Le dispatcher `TriggeredAbilitiesUtility.<EvaluateMovementInSteps>d__2.MoveNext @1810fda80` itère
**les abilities de L'UNITÉ QUI BOUGE** (`case.unit@0x10` → GetComponent(AbilitiesComponent) → collection
@0x18), PAS les amis porteurs. Par ability : `PlaybookDatabase.LoadPlaybook @1810dfd10` =
**singleton PAR TYPE d'ability** (cache dict@0x90 + factories dict@0x88 — les 190 lambdas
`InitializePlaybookBuilders`), null → skip, sinon `Σ ITriggeredAbilityPlaybook.CalculateMovementUtilityInSteps`.

Corps commun `AdjacentUnitPreferenceTriggeredAbilityPlaybook.<CalculateMovementUtilityInStepsInternal>
d__1.MoveNext @18134eb30` (lecture propre, les « MethodInfo slots » résolus) :

```
owner    = case.unit@0x10 ; playerId = OwnerComponent.get_CurrentPlayerEntityId(owner)
adjacent = IBattleQuery.<slot 0x81>(caseTile=case@0x18, playerId)  MINUS ToArray(self)   # amis R1
n1       = Min(count(vtbl+0x248 filtre), vtbl+0x228 cap)
val      = Σ_{i<n1} vtbl+0x208 weightAdjacent(u_i, ctx)
surround = IBattleQuery.<slot 0x7d>(caseTile, playerId, 0)                               # amis R2
n2       = Min(count(vtbl+0x258 filtre), vtbl+0x238 cap)
val     += Σ_{i<n2} vtbl+0x218 weightSurrounding(u_i, ctx)
yield Fix64.FromInt(val)
```

Les ~25 concrets (`RitesOfBattlePlaybook`, `FabricatorClawArrayPlaybook`, `GuardianOrganismPlaybook`,
`DrawFirePlaybook`, … base intermédiaire `AdjacentToOwnerNonOwnerPlaybook<T>..ctor @1813824d0`)
overrident `GetAdjacentFriendUtility`/`GetAdjacentEnemyUtility` = **lookup config plat, l'unité passée
est IGNORÉE** : `GuardianOrganismPlaybook.GetAdjacentFriendUtility @181166df0` invoque le délégué de
lookup (l'arg ctx du dispatcher = `utility@0x58`) avec la string-slot `DAT_183267540` →
`Utilities.Default.TriggeredAbilities["GuardianOrganism_AdjacentFriend"]` **= 30 (BC)**.

### Pourquoi 909 s4/s19 : GuardianOrganism = le passif du TYRANT GUARD (le mover !)

`GuardianOrganismPlaybook..ctor @181166e50` = base(0x49d=**1181** = `TriggeredAbilityType.GuardianOrganism`) ;
gameconfig : `tyranTyrantGuard` = actif CrushingClaws(1105) + **passif GuardianOrganism**. Donc :

**TrigAb(2) du move de u89 = 30 × #amis-vivants-adjacents-à-la-tuile (self exclu).**

- s19 (4,3) : u87+u91+u95 adjacents → 3×30 = **90** ✓ · (4,2) : u95 seul → **30** ✓ · (3,4) : u87 seul → **30** ✓
- s4 (3,2) : u87 seul → **30** ✓ · (0,3) : 0 → **0** ✓  (5/5 points L3 exacts, check offline)

### Pourquoi la contradiction était un ARTEFACT (leçon)

L'ancien modèle « Σ carriers {1191,1165,1202} adjacents × 30 » collait s4/s19 par **coïncidence
géométrique** : à ces tuiles, les amis adjacents ÉTAIENT justement u87/u91/u95. « Retirer 1202 des
carriers » cassait l'arithmétique parce que le modèle carrier lui-même était faux — u95 comptait comme
*ami adjacent*, pas comme *carrier*. MartialInspiration/MightFromBelow/VigilanceEternal sont les
playbooks de CAST de u87/u91/u95 (chargés quand EUX bougent) — hors sujet pour le move de u89.
La clé qui a tout débloqué : lire le champ `case@0x10` du d__1 (= l'ENTITÉ mover, dont on tire
`OwnerComponent.CurrentPlayerEntityId`) au lieu de présumer le sélecteur « amis porteurs ».

### Structure du composite (trace L3, parents reconstruits)

Le composite move (`ComposedUtility#0/#4`) contient UNE `TriggeredAbilitiesUtility` (la feuille 2) +
UNE `TriggeredAbilitiesNonOwnerUtility` (feuille 4, config séparée `TriggeredAbilitiesNonOwner` 25 clés,
`IterateAbilities @1810f2fb0` → tuples `(ITriggeredAbilityNonOwnerPlaybook, IEntity owner)`, face
d__2 @18134f250 = poids unique gaté « tuile adjacente au porteur ») — **=0 partout sur 909**, non portée.
Les instances `#1/#2/#5/#6` taguées `ab=ForHonor` sont d'AUTRES composites (contexte ability), pas le move.

### PORT (fait, 2026-07-19)

- `engine/playbook/adjacent_unit_preference.py` (NOUVEAU) : base `AdjacentUnitPreferenceTriggeredAbilityPlaybook`
  (Σ R1/R2, mirror d__1) + `AdjacentToOwnerNonOwnerPlaybook` + `GuardianOrganismPlaybook` (clé
  `GuardianOrganism_AdjacentFriend`) + registre `TRIGGERED_MOVE_PLAYBOOKS` / `load_playbook` (mirror LoadPlaybook).
- `engine/utilities/tile.py` : feuille `TriggeredAbilitiesUtility` (dispatcher @1810fda80) branchée à
  `TILE_LEAVES[2]` ; consomme `ctx.unit_triggered_abilities` + `ctx.friend_positions`.
- `engine/entities/triggered_ability_type.py` : `triggered_ability_ids(visualId)` (gameconfig
  `passiveAbilities` → enum) — source offline de l'AbilitiesComponent.
- `engine/ai/action_generators.py` : `tile_leaf_ctx(ctx)` (kit passif mover + `ctx.fpos`) passé par
  `MovementActionGenerator` → `best_move_faithful(..., leaf_ctx=)` (`engine/move.py`).
- `engine_agreement_stages.py` : `_move_utils` passe le même leaf_ctx ; LEVER 1 réécrit sur le modèle
  correct (suspect = passif du mover à clé config `<NOM>_Adjacent*` NON portée), l'ancien set
  {1191,1165,1202} supprimé.

Restant hors-scope (étendre quand un case le montre décisif) : les ~24 autres concrets
`GetAdjacent{Friend,Enemy}Utility` (3 lignes chacun), la face NonOwner(4), les caps vtbl+0x228/0x238
(gshared non symbolisés, jamais liants observés — max 3 amis adjacents).

### VALIDATION (offline + LIVE, 2026-07-19)

- **Offline** : 5/5 points L3 exacts — s19 (4,3)=90 / (4,2)=30 / (3,4)=30, s4 (3,2)=30 / (0,3)=0
  (leaf + kit helper + poids config, aucun fit).
- **LIVE (walk stages 909, 20 pas, runner 3)** : **s19 u89 → (4,3) EXACT** (le miss phare TrigAb=90
  est fermé). Move 12/16 (les 3 autres = pos-downstream-of-ability, hors move-pur).
- **s4 u89 : RÉSOLU par #37** ([case-37](case-37-tileeffects-elevation-move.md)) — ce N'ÉTAIT PLUS TrigAb
  (notre (3,2) tile=45 incluait déjà le +30 = 20 élév − 5 + 30) ; le résiduel vs natif (59) = 2 gaps
  PRÉ-EXISTANTS d'autres feuilles, corrigés : (1) TileEffects LightCover=9 (cover hébergé par la DryBush,
  Loop2) ; (2) Elevation LowestElevation (−5) indu (`LoadRelevantTileElevations` = board ENTIER, pas les
  candidats). **(3,2) = −641 > (0,3) = −650 → s4 EXACT** (walk 909 : move 12/16 → 13/16, `move-formula` = 0).

### VAs (résolution)

- `TriggeredAbilitiesUtility.<EvaluateMovementInSteps>d__2.MoveNext @1810fda80` (dispatcher, abilities du mover)
- `PlaybookDatabase.LoadPlaybook @1810dfd10` (singleton par ability-type ; factories dict@0x88, cache dict@0x90)
- `AdjacentUnitPreferenceTriggeredAbilityPlaybook.<CalculateMovementUtilityInStepsInternal>d__1.MoveNext @18134eb30`
- `AdjacentToOwnerNonOwnerPlaybook<T>..ctor @1813824d0` · face NonOwner `<CalculateMovementUtilityInSteps>d__2 @18134f250`
- `GuardianOrganismPlaybook..ctor @181166e50` (ability 0x49d=1181) · `GetAdjacentFriendUtility @181166df0`
  (lookup `DAT_183267540` = "GuardianOrganism_AdjacentFriend")
- Famille concrète (extension future) : `RitesOfBattlePlaybook$$GetAdjacentFriendUtility @181187d70`,
  `FabricatorClawArrayPlaybook @181165af0`, `DrawFirePlaybook @1811652f0`, `DeathwingPlaybook @181165080`, …
