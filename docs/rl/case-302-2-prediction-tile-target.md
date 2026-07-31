# case-302 tranche 2 — le terme de PREDICTION d'un tile-target a degat (`1169 PlagueburstMortar`)

Tranche 2 de `case-302-route-cible-tuile.md`. La tranche 1 avait porte le terme **custom** de
`1169 PlagueburstMortar` et nomme son residu : « le terme de PREDICTION reste a `0` ». Cette tranche
le porte, et degage le **patron valable pour TOUS les tile-target a degat** (§3) — c'est la moitie de
sa valeur.

**Etat : PORTE et CONFRONTE LIVE** (bras discriminant + bras temoin + preuve par mutation).

---

## 1. L'artefact natif, lu en entier

### 1.1 `PlagueburstMortarPlaybook$$MakeDamagePredictions`

```csharp
// IdunBattle.AI.Playbook.PlagueburstMortarPlaybook$$MakeDamagePredictions(caster, casterPosition,
//                                                                        target, abilityState)
ability = this+0x68;
damage  = VigilanceEternalAbility$$GetDamage(ability, abilityState);   // corps DEDUPLIQUE de
                                                                       // AActiveAbility$$MinMaxDamage(avg)
hits    = AActiveAbility$$GetHits(ability);                            // GetNumberConstant(0x2f = nrOfHits)
profile = Nullable( AActiveAbility$$GetDamageProfile(ability) );       // le damageProfile CONFIG
sel     = PlagueburstMortarAbility$$GetMainDamageTarget(ability);
return ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions(
           this, caster, casterPosition, target,
           targetsSelector: sel, damage, hits, profile,
           probability1: <struct ZERO>, weightSelector: null);
```

⚠ Le nom `VigilanceEternalAbility$$GetDamage` n'a **aucun** rapport avec 1169 : c'est le proprietaire
que la table des symboles a retenu pour un corps `MinMaxDamage(this, abilityState, avgFlag)`
**deduplique** par IL2CPP. Lu en entier, ce corps est l'avg config GENERIQUE — donc **aucun override
d'entree** pour 1169 (ni `_MAKE_DMG_INPUT_OVERRIDES`, ni `_PLAYBOOK_PROFILE_OVERRIDE` : contraste net
avec 1147/1148, dont le playbook passe `param_8 = null`, cf. case-172).

### 1.2 `GenerateMultiHitAttackPredictions` — ce que le `targetsSelector` decide

```csharp
// IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions
list     = new List<ProbableDamageEvent>();
entities = AbilityEntities{ owner: caster, caster: caster, target: target,
                            casterPosition: casterPosition,
                            casterMainTile: UnitPosition$$get_MainTile(casterPosition),
                            targetTiles: EntityExtensions$$GetTiles(target, state),
                            abilityOrEffect: Nullable(AbilityOrEffect(this+0x20)) };
if (damageFormula == null) throw;
dmg = Formula.Calculate(damageFormula, entities);
if (targetsSelector == null) throw;
foreach (t in TargetsSelector.Select(targetsSelector, entities, 3)) {
    pred = (this+0x28).<slot 0x28 = PredictAttack>(entities, caster, t, casterPosition,
                                                   abilityOrEffect, dmg, profile, hits);
    w    = (weightSelector == null) ? Fix64(1) : weightSelector.Evaluate(t);
    list.Add(new ProbableDamageEvent(t, pred, probability1, Nullable(w)));
}
return list;
```

⇒ **UN event par entite du selecteur**, tous avec le MEME `(damage, hits, profile)`. Le `casterPosition`
entre dans l'`AbilityEntities` **et** est forwarde a `PredictAttack` (mods positionnels, gate
`HasMoved`) — contrairement au terme CUSTOM, qui l'ignore (tranche 1).

### 1.3 `GetMainDamageTarget` — et ce qu'il n'inclut PAS

```csharp
// IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$GetMainDamageTarget
return DSLSelectors.Filter(
           DSLSelectors.Enemies(of: Caster@+0x48, entities: Target@+0x60, selectionType: 3),
           PlagueburstMortarAbility$$GetIsValidAdjacentEnemyTrigger(this) );
```

**Lecture decisive** : le batch de prediction couvre **le seul occupant de la tuile visee**.
`...PlagueburstMortarAbility$$GetAdjacentDamageTargets` (les ennemis des tuiles ADJACENTES) est
utilise par `ExecuteBehaviour` et **pas** par `MakeDamagePredictions`. La face DECISION voit donc :

| ce que l'IA voit | par quel terme | artefact natif |
|---|---|---|
| les ennemis qui BORDENT la tuile visee | **custom** (`n x GetUtilityValue("PlagueburstMortar_AdjacentEnemy")`) | `GetAdjacentEnemies` (SANS Filter) |
| l'ennemi qui OCCUPE la tuile visee | **prediction** (degat) | `GetMainDamageTarget` (AVEC Filter) |

Deux ensembles a roles DISJOINTS — surtout pas un doublon a dedoublonner. Un port qui aurait branche
`plagueburst_damage_targets` (l'union COMBAT) sur la prediction aurait double-compte les voisins.

### 1.4 Le predicat, et pourquoi il n'est PAS structurellement mort

`...PlagueburstMortarAbility$$GetIsValidAdjacentEnemyTrigger` =
`IsInTeamContagionsOfNurgleAura(Subject, Caster) | (HasNegativeModifier(Subject, FixedArmor)
& AmountIsGreaterThanZero(StatAmount(Subject, FixedArmor, Initial)))` — deja porte des case-224
(`deathguard.plagueburst_is_valid_adjacent_enemy_trigger`, LES DEUX branches).

Contraste avec `1148 DaemonicOrdnance` (tranche 3), dont le selecteur de prediction exige une tuile
**deja en feu** alors que c'est ce meme cast qui pose le feu — la, le `0` est STRUCTUREL. Ici il ne
l'est pas : la branche AURA s'allume par le seul **deplacement** d'un porteur du trait
`ContagionsOfNurgle` (`0x7eb = 2027`) du camp du caster a portee de l'occupant. C'est ce qui rend la
tranche confrontable, et c'est le montage du §4.

### 1.5 Entite TUILE ou UNITE dans l'ensemble rendu ?

`IdunBattle.Entities.Selectors.UnitsByTeamSelector$$CountOrAdd` resout `other =
UnitExtensions$$GetUnitOrMachine(entity, state)` **pour le test d'equipe** puis fait
`result.Add(entity)` — l'entite **BRUTE**. Avec `Target` = une entite TUILE, l'ensemble natif est
donc fait de TUILES, la ou le port materialise la resolution (`Enemies(Units(target_sel))`).

**MESURE, pas hypothese** (`probe_302_2 --stage`, §4.2) : `pairUtility(caster, <tuile>, 1169)` et
`pairUtility(caster, <unite qui l'occupe>, 1169)` rendent la MEME valeur **a la derniere decimale**
sur les 3 cibles du montage. La resolution materialisee est donc value-identique sur ce chemin, et le
choix deja fait par la face COMBAT (#90) est confirme plutot que suppose.

---

## 2. Ce qui est porte

| fichier | changement |
|---|---|
| `engine/runner/abilities/deathguard.py` | `plagueburst_main_damage_target` (= `GetMainDamageTarget`) et `plagueburst_adjacent_damage_targets` (= `GetAdjacentDamageTargets`) extraits comme fonctions NOMMEES ; `plagueburst_damage_targets` devient leur `Unique(Union(...))`. Un artefact natif = une fonction de port, deux consommateurs (COMBAT / DECISION) |
| `engine/playbook/tile_targets.py` | `dsl_context_for_tile_target` fournit desormais `has_negative_modifier` et `is_in_team_aura` (+ `_turns_started`, canal mesure `Scene.turns_started_by_id` avec repli `UnitContext`) |
| `engine/playbook/plagueburst_mortar.py` | `PlagueburstMortarPlaybook.make_damage_predictions` — mirror 1:1 de `MakeDamagePredictions` |
| `probe_302_2_plagueburst_prediction.py` | **neuf** — oracle par etage + montage discriminant + bras temoin |
| `tests/engine/test_plagueburst_mortar_prediction_live.py` | **neuf** — 9 gardes |

### 2.1 Le cablage etait le sujet, et il manquait DEUX accesseurs

Le predicat etait porte, mais son contexte d'evaluation cote DECISION ne fournissait ni
`ctx.has_negative_modifier` ni `ctx.is_in_team_aura` : les deux noeuds retombaient sur leur
degradation `False` (`triggers.HasNegativeModifier` / `triggers.IsInTeamAura`), donc le `Filter`
vidait l'ensemble **partout**, et le terme valait `0` **y compris dans le regime ou le natif predit
du degat**. La face COMBAT, elle, les cable depuis case-224 (`entities_from_state`). Meme substrat,
deux sources d'etat : l'ECS la-bas, la `Scene` ici.

> **C'est le patron du bug, pas un detail de 1169** : un accesseur de `DslContext` absent ne CASSE
> rien — il rend `False`/`0` et le port devient silencieusement conservateur. La seule facon de le
> voir est de crafter le regime ou le predicat est VRAI.

---

## 3. LE PATRON — il vaut pour TOUT tile-target a degat

C'est le livrable generalisable de la tranche. Pour porter la face DECISION d'une ability a cible
TUILE qui inflige des degats, la sequence est TOUJOURS celle-ci :

1. **Lire le `targetsSelector` que `MakeDamagePredictions` passe a
   `GenerateMultiHitAttackPredictions`** — et LUI SEUL. Ce n'est presque jamais l'ensemble des cibles
   de `ExecuteBehaviour` : 1169 predit sur `GetMainDamageTarget` (l'occupant) alors qu'il FRAPPE
   `Unique(main + adjacents)` ; 1148 predit sur `GetAllDamageableTargets` (ennemis sur tuile en feu)
   alors qu'il frappe toute la zone. **Le batch de prediction est un SOUS-ensemble propre, et l'ecart
   entre les deux est une propriete NATIVE a porter, pas une approximation.**
2. **Verifier les trois entrees `(damage, hits, profile)`** au decompile. Generiques
   (`MinMaxDamage(avg)` / `GetNumberConstant(0x2f)` / `GetDamageProfile`) -> chemin generique
   `generate_multi_hit_attack_prediction`, AUCUN override. Non generiques -> entree dans
   `_MAKE_DMG_INPUT_OVERRIDES` / `_PLAYBOOK_PROFILE_OVERRIDE` (piege du `param_8 = null`, case-165/172).
   Les noms de corps DEDUPLIQUES (`VigilanceEternalAbility$$GetDamage` pour 1169) ne disent RIEN :
   ouvrir le corps.
3. **Emettre UN `ProbableDamageEvent` par element du selecteur**, `attack_pos = caster_tile` (le
   natif forwarde `casterPosition` a `PredictAttack`), `probability` par defaut sauf
   `weightSelector != null`.
4. **Le vehicule de collapse est `FixedTileIds([<tileEntityId>])`** — la cible circule dans le meme
   slot qu'une unite (`UnitAction..ctor` prend un `IEntity` non type, case-302 §1.2), et
   `ctx.tile_id_by_pos` (RPC `boardGraph`) donne l'id que `applyOneAction` attend.
5. **Auditer les ACCESSEURS que le predicat de ce selecteur consomme** dans
   `dsl_context_for_tile_target`. Chaque accesseur manquant = un `False` silencieux = un port
   conservateur qu'aucune statistique d'agrement ne verra (§2.1).
6. **Confronter PAR ETAGE avec `pairUtility` sur la CIBLE TUILE** — cet oracle EXISTE (§4.1),
   `case-302` §7 disait le contraire et c'est PERIME.
7. **Crafter le regime ou le predicat est VRAI**, sinon le vert ne dit rien : le terme vaut `0` des
   deux cotes et un port qui ne calcule RIEN passe. Puis un bras TEMOIN hors regime, et une MUTATION
   qui doit changer la decision.

### 3.1 Membres connus du patron

| id | ability | selecteur de PREDICTION | etat |
|---|---|---|---|
| 1169 | PlagueburstMortar | `GetMainDamageTarget` (occupant, filtre aura/armure) | **PORTE** (cette tranche) |
| 1148 | DaemonicOrdnance | `GetAllDamageableTargets` (ennemis sur tuile en FEU) | residu nomme, `0` STRUCTUREL hors regime (case-302 §8.4) |
| 1147 | HadesAutocannons | — | face DECISION non portee |
| 16 autres du bit `TargetIsTile` | cf. `probe_302 --inventory` | — | non portees |

---

## 4. Validation live

Runner `MC1_67` / seed 909 / rank 17, greffe de 1169 sur `deathTyphus` (case-92 §5bis), cooldown
initial purge (lecon `case-302` §5), `--hp-target 20000`.

### 4.1 L'oracle PAR ETAGE existe — `case-302` §7 est PERIME sur ce point

`case-302` §7 (tranche 5) ecrivait : « `rpc-predict.ts::pairUtility` ne resout `targetId` que sur
`EntityType.Unit` — il n'existe donc aucun oracle PAR ETAGE pour une cible tuile ». **C'etait vrai a
la redaction et ne l'est plus** : le commit hooks `#302-t5` resout la cible sur TOUS les
`EntityType` et publie `targetEntityType`. Mesure : `pairUtility(u83, tile 52, 1169)` repond
`ok: true, targetEntityType: 0` (= `Tile`).

`pairUtility` invoque `ComparablePlaybook$$CalculateUtilityFromPredictions` — **exactement** le terme
de cette tranche (le custom n'y est pas). La tranche 2 valide donc PAR ETAGE, pas seulement par la
decision complete.

### 4.2 Etage 1 — le terme, tuile par tuile

Montage : anneau hex autour de `CENTER = (3,4)`, trois ennemis sur trois voisins **consecutifs**
(`(3,5) - (4,4) - (4,3)`), caster au CENTRE (donc a portee d'aura `ContagionsOfNurgle` des trois).

| tuile | occupant | events port | port | natif (`pairUtility`) | ecart |
|---|---|---|---|---|---|
| `(4,4)` | orksWarboss | 1 | 25.91590841 | 25.91840817 | **+2.500e-03** |
| `(3,5)` | necroWarden | 1 | 23.55514449 | 23.55764424 | **+2.500e-03** |
| `(4,3)` | astraCreed | 1 | 15.70342966 | 15.70342965 | -2.8e-09 (EXACT) |
| 59 autres | — | 0 | 0 | 0 | 0 |

`pairUtility(TUILE)` == `pairUtility(UNITE occupante)` **a 1e-12** sur les trois (cf. §1.5).

**Champs de prediction : BIT-EXACTS** (`aiPlaybookPredict` sur l'unite occupante vs
`make_damage_predictions`) — `healthDmgMin/Max`, `hpBefore`, `appliedHits` identiques
(ex. `3771 / 5652 / 3 coups`). L'ecart residuel n'est donc PAS dans la prediction : il est en aval,
dans le composite (§5).

### 4.3 Etage 2 — la DECISION complete

| bras | caster | natif | moteur | moteur SANS le terme |
|---|---|---|---|---|
| **DISCRIMINANT** | `(3,4)`, au centre | `(1169, tile 52 = (4,4))` | `(1169, tile 52)`, `to=(2,3)` | **`(1169, tile 43 = (3,4))`** |
| **TEMOIN** | `(0,2)`, hors aura | `(1169, tile 43 = (3,4))` | `(1169, tile 43)`, `to=(0,3)` | `(1169, tile 43)` — INERTE |

Le bras discriminant oppose deux tuiles que **seul** le terme de prediction departage :

| tuile visee | custom | prediction | total |
|---|---|---|---|
| `(3,4)` (centre, 3 ennemis adjacents) | **30** | 0 (occupant = un ALLIE) | 30.00 |
| `(4,4)` (l'ennemi du MILIEU, 2 adjacents) | 20 | **25.92** | **45.92** |

La mutation (`MakeDamagePredictions` vide) fait donc changer **la TUILE, a ability constante** — pas
l'ability. C'est la forme de rouge qu'on voulait : elle teste la CIBLE, pas 1169-contre-69.

### 4.4 Gardes

`scripts/python/tests/engine/test_plagueburst_mortar_prediction_live.py` — **9 tests, 9 verts**
(147 s, re-joues APRES rebase sur `origin/master` `7166cbfa`, qui contient #337 — lequel a modifie
le foyer per-cible `generate_multi_hit_attack_prediction` que ce port appelle). Non-regression des
tranches voisines, re-jouee elle aussi apres rebase : `test_plagueburst_mortar_decision_live.py` +
`test_deathguard_targeting_live.py` **16/16**, `test_daemonic_ordnance_decision_live.py` **13/13**.
Chaque garde porte un enonce falsifiable : disponibilite de l'oracle par etage (ECHEC explicite,
jamais un skip), montage qui atteint REELLEMENT le predicat, `nev <= 1` par tuile (les adjacents
n'entrent pas), bit-exactitude des champs, attribution du residu (§5), accord sur les deux bras,
mutation qui change la tuile, inertie hors regime.

### 4.5 Preuve par MUTATION — la garde SAIT virer au rouge

Deux mutations, deux signatures DISJOINTES. Une garde jamais vue rouge ne prouve rien.

| mutation | resultat MESURE |
|---|---|
| **M0 — terme de prediction VIDE** (`MakeDamagePredictions` -> `[]`) | jouee EN CONTINU par la garde D (bras `mutated`) : bras discriminant `(1169, tile 52)` -> `(1169, tile 43)`, **meme ability, AUTRE tuile** ; bras temoin INCHANGE |
| **M1 — predicat retire de `GetMainDamageTarget`** (`Filter(...)` remplace par `Enemies(Units(...))` nu) | **2 rouges / 9** : `test_prediction_term_is_inert_outside_the_regime` (bras TEMOIN : moteur `(1169, 52)` vs natif `(1169, 43)`) et `test_engine_matches_native_on_both_arms`. Les 7 autres restent verts — le rouge est LOCALISE sur le canal du predicat, pas diffus |

M1 est la mutation qui compte : elle attaque precisement le cablage neuf (`has_negative_modifier` /
`is_in_team_aura`). Sans le predicat, le port predit du degat sur un occupant que le natif REFUSE,
et c'est le bras TEMOIN — celui qui « passe tout seul » quand tout vaut 0 — qui le detecte.

---

## 5. RESIDU NOMME — `MinMaxDamage$$Avg` arrondit, le port gardait le `.5`  → **FERME par #333**

> **FERME le 2026-07-31 (`case-333-arrondi-minmax-avg.md`).** Le port applique desormais l'arrondi
> au foyer (`engine.services.min_max_damage.min_max_avg`, appele par les DEUX methodes de
> `DamageUtility`). Ecart re-mesure sur CE montage : `+2.500e-03` -> `~8e-09` sur les tuiles a
> somme IMPAIRE.
>
> ⚠ **Ce que cette section ne pouvait PAS etablir, et ne l'a pas etabli** : le MODE d'arrondi. Ses
> trois cibles a somme IMPAIRE ont toutes un `floor` IMPAIR (`4711`), et sur ce cote-la
> demi-vers-le-pair et demi-vers-le-haut **coincident**. L'assertion « le port SOUS-ESTIME »
> (ci-dessous) n'est donc vraie que d'une moitie du regime : sur un `floor` PAIR le natif DESCEND et
> l'ecart est NEGATIF. La discrimination du mode a demande de PILOTER la parite par les PV de la
> cible — `case-333` §4.

**Ce residu n'appartenait PAS a cette tranche** : il vit dans le composite Damage PARTAGE, il touche
TOUTES les abilities, et il se mesure a l'identique sur l'attaque NORMALE (69). Il est documente ici
parce que c'est la mesure qui l'a fait apparaitre.

```csharp
// IdunBattle.AI.Utilities.DamageUtility$$GetHealthDamage
hAvg = MinMaxDamage$$Avg(prediction + 0x40);       // AccurateHealthDamage
if (prediction.LimitedByMinHp) hAvg = CurrentHealth;

// IdunBattle.Core.Services.MinMaxDamage$$Avg
return (int) Fix64.Round( (Fix64(min) + Fix64(max)) / Fix64(2), midpointRounding: 0 );

// FixMath.NET.Fix64$$Round(value, midpointRounding)
//   frac <  0.5                      -> floor
//   frac == 0.5 && midpointRounding==0 -> ((value >> 0x20) & 1) == 0 ? floor : floor + 1   // DEMI-VERS-LE-PAIR
//   sinon                            -> floor + 1
```

Le port (`engine/utilities/damage.py::DamageUtility.get_health_damage`) rend `(dmin + dmax) / 2.0` —
un flottant qui garde le `.5`. Ecart des que `min + max` est **IMPAIR** : le natif rend un ENTIER
arrondi demi-vers-le-pair, le port un demi. `get_shield_damage` a la meme forme (meme `Avg` natif).

**Mesure** (bras discriminant, `hpmax = 20000`, `combinedMax = 20002`, `dU/dD = (80+20)/combinedMax`) :

| cible | min | max | somme | ecart natif - port |
|---|---|---|---|---|
| orksWarboss | 3771 | 5652 | IMPAIRE | `+2.500e-03` = `0.5 x 100 / 20002` |
| necroWarden | 3771 | 5652 | IMPAIRE | `+2.500e-03` |
| astraCreed | 2514 | 3768 | PAIRE | `-2.8e-09` (bruit flottant) |

**Preuve par construction** : en appliquant l'arrondi natif en monkeypatch, l'ecart DISPARAISSAIT
sur toutes les tuiles (`< 1e-6`). La garde correspondante
(`test_the_shared_minmax_rounding_is_applied_and_the_gap_is_closed`) est desormais l'INVERSE : elle
exige un ecart NUL, et rejoue le `.5` conserve en MUTATION pour verifier qu'elle sait virer au rouge.

**Meme mesure sur l'attaque NORMALE (69), meme runner** : `orksWarboss` port `0.6773716131` vs natif
`0.6774966139` (`+1.250e-04` a `hpmax = 400000`), `astraCreed` EXACT. Le residu etait donc bien
GLOBAL, pas une propriete de 1169.

**Pourquoi ce n'etait pas corrige ici** : rayon d'impact GLOBAL (toute utilite de degat du moteur
bouge d'au plus 0.5 point de degat), donc une re-validation bien plus large que les tests cibles de
cette tranche. Fait en **tranche dediee** : `case-333-arrondi-minmax-avg.md`.

---

## 6. Ce que cette tranche n'etablit PAS

- **La branche ARMURE du predicat n'est pas exercee** : le montage l'allume par la branche AURA.
  `--hp-target` met `Armor`/`FixedArmor` a **0** (cf. `runner.md` §3), donc
  `AmountIsGreaterThanZero(StatAmount(Subject, FixedArmor, Initial))` est FAUX par construction dans
  ce regime. Pour l'exercer : `--armor-target N` + une source de modification NEGATIVE d'armure sur
  l'occupant. Le canal (`Scene.ctx(uid).stats.has_negative_modifier`) est cable et partage avec le
  gate ConquerorImperative, deja valide ailleurs ; c'est le SCENARIO qui manque, pas le port.
- **`weightSelector != null`** (`param_10` de `GenerateMultiHitAttackPredictions`) : 1169 passe
  `null`, donc `probability2 = Fix64(1)`. La branche pondere-par-cible n'est ni portee ici ni exercee.
- **Une unite MULTI-TUILES occupant la cible** : `Units(...)` resout l'occupant par la MAIN tile,
  la ou le natif passe par `TileContentComponent` (rempli pour CHAQUE pied). Meme residu que
  `tile_targets.unit_on_tile` (case-302 §8.4). Non exerce : les heros du pool sont mono-tuile.
- **Le `Filter` sur une entite TUILE non occupee** : le natif evalue son predicat sur l'entite
  BRUTE (une TUILE), le port sur l'occupant resolu. Value-identique **mesure** quand la tuile est
  occupee par un ennemi (§1.5) ; sur une tuile VIDE les deux rendent l'ensemble vide, mais par des
  chemins differents (le natif teste `GetUnitOrMachine == null`, le port n'a rien a filtrer).
- **La face COMBAT est inchangee** : `plagueburst_damage_targets` est reecrit en termes des deux
  fonctions nommees mais rend le MEME arbre (`Unique(Union(main, adj))`, meme predicat).

---

## 7. Reproduire

```bash
cd scripts/python
python probe_302_2_plagueburst_prediction.py --stage       # oracle par etage + attribution du residu
python probe_302_2_plagueburst_prediction.py --decision    # 2 bras + mutation
python -m pytest tests/engine/test_plagueburst_mortar_prediction_live.py -q
```

Le probe n'arme AUCUN hook : `decisionView` / `abilityTargets` / `boardGraph` / `combatSnapshot` /
`pairUtility` / `aiPlaybookPredict` / `aiDryRunAllUnits`, et pilote par `applyAction`. Aucune
reinjection.
