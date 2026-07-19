# Case #36 — TriggeredAbilitiesUtility(2) comme terme de tuile move

**Statut : RE fait (nature établie), port NON commencé. Reclassé : playbook-dispatch, pas une feuille.**

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
