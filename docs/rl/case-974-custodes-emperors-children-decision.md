# #974 — faces DÉCISION Custodes / Emperor's Children : cinq soumises, **deux** à porter

Build `rnca9r7q6c`. Cinq abilities soumises ; le RE en a ramené **deux** à porter, **deux** déjà
portées et **une** sans contenu propre. Le tri s'est fait au décompilé, jamais sur l'audit.

| id | classe native | base (`classes.tsv`) | verdict |
|---|---|---|---|
| 1184 `MomentShackle` | `MomentShacklePlaybook` | `ComparablePlaybook\`1` | **DÉJÀ PORTÉE** — `playbook/bespoke.py` |
| 1191 `MartialInspiration` | `MartialInspirationPlaybook` | `ComparablePlaybook\`1` | **DÉJÀ PORTÉE** — `_MAKE_DMG_INPUT_OVERRIDES` |
| 1195 `TalonsOfTheEmperor` | `TalonsOfTheEmperorPlaybook` | `ComparablePlaybook\`1` | **PORTÉE ICI** |
| 1196 `LashOfTorment` | `LashOfTormentPlaybook` | `ComparablePlaybook\`1` | **SANS CONTENU PROPRE** |
| 1198 `EuphoricStrikes` | `EuphoricStrikesPlaybook` | `NonComparablePlaybook\`1` | **PORTÉE ICI** |

## 1. Le recensement de l'existant — l'audit lit **3 registres sur 5**

`probe_909_decision_actives_kit.py` interroge `noncomparable.PLAYBOOKS`, `playbook.REGISTRY` et
`_SPECIAL_ABILITY_CLASSES`. Deux voies de portage lui échappent, et **deux des cinq abilities du
lot y vivaient** :

* `playbook/bespoke.py::BESPOKE_SELFCAST` (3 ids) — une **Comparable qui override
  `EvaluateInternal` en entier** n'entre dans aucun des trois ; c'est `1184`.
* `playbook/prediction/abilities.py::_MAKE_DMG_INPUT_OVERRIDES` (15 ids) — un override d'ENTRÉE
  n'est pas une classe ; c'est `1191`.

Un `git grep` par NOM **et** par ID reste donc le seul recensement fiable. Mesure faite avant tout
port : sur les 5, **2 étaient déjà portées**.

## 2. Ce que le décompilé dit, terme à terme

### 1195 — deux écarts avec le générique, **en sens opposés**

`TalonsOfTheEmperorPlaybook.<MakeDamagePredictions>d__2$$MoveNext` :

    base   = AbilityConfiguration.GetVariableForLevel(cfg, 0xc, level, null)   # minDmg SEUL
    extra  = <slot 1>( TalonsOfTheEmperorAbility$$GetExtraDamage(ability, level),
                       entities{ +0x08 = caster } )                            # caster SEUL
    met    = TalonsOfTheEmperorAbility$$MeetSecondDamageProfileRequirement(ability)
                .<slot>( entities{ +0x08 = caster, +0x10 = target, +0x40 = casterTile }, 0x20 )
    hits   = AActiveAbility$$GetHits(ability)
    -> GetAttackPrediction(..., extra + base, met ? damageProfile_2 : damageProfile, hits)

* **La base est `minDmg` SEUL** — aucun `MinMaxDamage` dans ce corps. Le générique SUR-évaluait.
  `1195` **manquait** à `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE` : trou trouvé en portant.
* **Un terme FLAT s'ajoute** — le générique SOUS-évaluait.
* **Le profil est CONDITIONNEL**, donc il ne peut pas vivre dans `_PLAYBOOK_PROFILE_OVERRIDE`
  (qui ne porte que des constantes) ; il passe par le handler, qui l'emporte de toute façon.
* **`GetHits` n'est PAS surchargé** : le natif le rappelle dans les deux branches, et les clés
  `minDmg_2` / `nrOfHits_2` **n'existent pas** dans le kit.

Deux écarts de signes contraires ⇒ **un scalaire agrégé peut concorder par compensation**. Seule la
décomposition par étage les sépare — c'est ce que garde `#974-r2`.

### 1198 — l'utilité de `Vexilla`, l'autre conjoint

`EuphoricStrikesPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket(0, Nullable(<statics[0]>))            # .cctor : Fix64(1)
    foreach entities in GetEligibleTargetsSelectable(caster, casterPosition):
        if (WillNormalAttackKill(entities)) continue;         # <- LE GATE, EN TÊTE
        utility = Fix64( GetStat(entities@+0x10, 5 = Health, 0, 0) )
        bucket.AddAction(GenerateAction(casterPosition, entities@+0x10, utility))

Jumeau structurel de `VexillaMagnificaPlaybook` (même utilité PV, même seuil, **même** surcharge de
`GetEligibleTargetsSelectable` — tranchée par les **xrefs entrantes**, trois surcharges existant).
Le conjoint diffère : `HasEffect(Stunned)` **sous** le calcul chez Vexilla, `WillNormalAttackKill`
**au-dessus** ici. Conséquence observable : le gate **CONSTRUIT un `ProbableDamageEvent`** que
l'oracle capte. Mais, à la différence de `KillMaimBurn` qui porte le même gate, **1198 ne construit
aucune prédiction d'ability** : sa trace vaut **au plus UN** event.

### 1196 — sans contenu propre

`LashOfTormentPlaybook$$MakeDamagePredictions` = `GetDamage` / `GetHits` / `GetDamageProfile` →
`GenerateMultiHitAttackPredictions`. Chemin générique strict, déjà couvert, et `1196` figure déjà
dans `_PREDICTION_MINMAX_RANDOM_READ` (famille (b), « lu et confirmé »). Même verdict que
`LeadingTheCharge` (1204) de #945 — et **verrouillé** par un test, pour qu'il ne soit pas re-porté.

## 3. Deux absences, **deux valeurs de preuve différentes**

* **`ShouldExecute` : l'absence CONCLUT.** Les corps de cette famille lisent **chacun le static de
  leur classe**, donc ils sont deux à deux distincts, donc non dédupliquables par ICF — ghidra les
  nomme tous (29 dans ce build). Ni `1195` ni `1196` n'en a : leur `.cctor` `Fix64(1)` n'a **aucun
  lecteur**, ils ne sont pas de la famille « seuil statique `Fix64(10)` ».
* **`ShouldEvaluate` : l'absence NE CONCLUT PAS.** Le gate de tour est un COMDAT **unique**
  (refcount 7). Il a fallu la vtable — voir §4.

⚠ **La voie par xrefs de `DAT_` est FAUSSE** et a failli me faire conclure : `PlasmaCannonPlaybook`
écrit son static via `DAT_1833508f8` et le lit via `DAT_18337d9a8` — **deux slots pour la même
classe**. Un « aucun lecteur » dérivé de ces xrefs est un faux négatif. C'est le **nommage** qui
tranche, pas les xrefs.

## 4. La mesure live — et trois fautes de mesure en chemin

`probe_974_decision_gates_live.py`, runner MC1_67 / seed 777, `custoAtlacoya` (pool) +
`emperExultant` (co-injecté au catalogue avec `emperLucius`) :

| ability | `get_IsComparable` | `ShouldEvaluate` | témoin `turnsStarted` |
|---|---|---|---|
| 1195 | `True` (Comparable) | `True` | 1 |
| 1198 | `False` (NonComparable) | `True` | 1 |

Le régime **discrimine** (`turnsStarted == 1`, où un playbook porteur du gate rendrait `False`) ⇒
**aucun gate de tour**, le défaut permissif du port est juste. **`#974-r1` FERMÉ.** Et
`get_IsComparable` recoupe `classes.tsv` par une source **indépendante** — nécessaire, les deux
`.ctor` étant étiquetés `ComparablePlaybook<...>` par ICF.

Les trois fautes, toutes écrites dans le probe :

1. **`retRaw` est une chaîne HEX** (`ret.toString(16)`) : `bool(retRaw)` est vrai pour toute
   réponse. Le premier tir a annoncé une divergence `get_IsComparable` sur `1198` **qui n'existait
   pas** — elle aurait fait déplacer un port juste. Le canal est `retLow`.
2. **Le témoin ne peut pas être une autre ability** : `pbGate(slot=4)` sur `1202`/`1112`/`1151` —
   les trois porteurs connus du corps foldé — rend `access violation` pour les trois, leurs
   playbooks n'ayant jamais reçu `Init` (aucun porteur dans cette bataille). Un témoin qui
   **crashe** ne discrimine rien.
3. **`units[].stats` est indexé par NOM**, pas par l'ordinal de `StatType` (`statTypes.turnsStarted`
   vaut bien `12`, mais `stats["12"]` rend `None`).

## 5. Gardes

`test_974_custodes_emperors_children_decision_offline.py` — 24 tests, **8/8 mutations vérifiées
mordantes** (base ← moyenne, registre retiré, `hits_override` posé, compteur ← `max` au lieu de la
somme, VETO retiré, utilité ← pourcentage, second event émis, playbook déregistré). Le test du VETO
porte **sa propre contre-épreuve** : le même point de substitution forcé à `False` doit laisser
passer l'utilité — sans elle, un patcheur inerte (forme A) rendrait la garde verte par accident.

Ce qui n'est **pas** couvert : la confrontation des VALEURS à l'oracle natif → `#974-r2`.
