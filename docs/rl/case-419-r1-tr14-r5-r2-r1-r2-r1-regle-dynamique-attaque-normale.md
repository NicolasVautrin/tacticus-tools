# `#419-r1-tr14-r5-r2-r1-r2-r1` — la regle dynamique de l'attaque normale

**Critere binaire** : le port offre-t-il, sur le chemin de l'attaque normale, des cibles que le
natif REFUSE ?

**Verdict** : OUI, il en offrait — ecart **PERMISSIF** confirme et **ferme**. Le refus porte est
exact sur le VERDICT (6/6 contre 3/6 pour la baseline, **3 lignes gagnees, 0 perdue**), et il ne
s'arme que sur les 13 types qui posent le bit. La RE amont designait la mauvaise surcharge native :
c'est le slot `0xb0`, pas celle a `GetAbilityAttackRangeType`.

---

## 1. La chaine, LUE — et la surcharge n'est PAS celle annoncee

`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason`
(5 parametres : `this, caster, casterTile, target, targetTiles`) :

```
w = <IBattleQuery slot 0xb0>(caster, casterTile, targetTiles)
return (w != null) ? 0 : 2   /* TargetMatchesDynamicRule */
```

`IBattleQuery` porte **TROIS** surcharges de `GetAttackWeaponForDefaultNormalAttack`, et elles ne
font pas la meme chose :

| slot | signature (noms de params, metadata IL2CPP) | corps |
|---|---|---|
| `0xae` | `(attacker, attackerTiles)` | appel d'interface -> chaine de repli melee/ranged |
| `0xaf` | `(attacker, attackerTiles, **target**)` | `GetNormalAttackType` -> `BattleQuery$$GetAbilityAttackRangeType` -> `UnitExtensions$$HasFlag(0x15)` / `AreEntitiesAdjacent` |
| `0xb0` | `(attacker, attackerTiles, **targetTiles**)` | `MovementUtil$$AreTilesAdjacent` -> `FindMeleeWeapon` / `FindRangedWeapon` |

**C'est le slot `0xb0`** — la surcharge SIMPLE. Le residu amont annoncait la surcharge a
`GetAbilityAttackRangeType` : c'est le slot `0xaf`, qu'aucun chemin porte n'emprunte. Trois lectures
concordantes le tranchent :

1. `IdunBattle.View.FSM.VisualBattleQuery$$GetAttackWeaponForDefaultNormalAttack(unit, unitTile)`
   (2 arguments) delegue **explicitement** au slot `0xae` — ce qui FIXE l'appariement arite<->slot et
   laisse `0xaf`/`0xb0` aux deux surcharges a 3 arguments.
2. Les deux surcharges de `ALoki_NormalAttackAbility$$FindAttackWeapon` appellent respectivement le
   slot `0xaf` (parametre `target`) et le slot `0xb0` (parametre `targetTiles`) ; c'est ce second
   que `GetDynamicInvalidTargetReason` invoque. Corollaire : la regle dynamique n'appelle **pas** le
   meme slot que « `FindAttackWeapon` » au singulier — l'ecriture amont confondait deux surcharges.
3. Les TYPES concordent : la surcharge `targetTiles` deref ses deux arguments comme des collections,
   la surcharge `target` passe `target` tel quel a `AreEntitiesAdjacent` / `FindMeleeWeapon`.

## 2. Les etages, et le SEUL regime de refus

```
GetAttackWeaponForDefaultNormalAttack(attacker, attackerTiles, targetTiles):     # slot 0xb0
    if (MovementUtil.AreTilesAdjacent(attackerTiles, targetTiles))
         return FindMeleeWeapon(attacker, unitPosition: null, target: null)
    else return FindRangedWeapon(attacker)
```

`AreTilesAdjacent` y est la surcharge **LISTE** (xref lue depuis ce corps vers
`MovementUtil$$AreTilesAdjacent(IList, IList)`) : produit cartesien vrai des qu'UNE paire de tuiles
est adjacente — donc l'EMPREINTE complete, le meme predicat que `BattleQuery$$AreEntitiesAdjacent`,
et non la seule tuile principale.

* `BattleQuery$$FindMeleeWeapon` / `$$FindRangedWeapon` : `EntityExtensions$$IsUnit` faux -> `null` ;
  sinon filtrent les `WeaponProfile` du `WeaponsComponent` par
  `IdunShared.Battle.WeaponProfile$$get_IsMelee` (`!Range.HasValue || Range.Value < 2` — **le seuil
  `< 2` est LU** : une portee de 1 est encore de la melee), puis `SelectMaxRangeWeapon`.
  Le `target` etant NUL sur ce call-site, la branche `SelectBestDamageWeapon` est MORTE.
* `BattleQuery$$SelectMaxRangeWeapon` : `Count == 0 -> null`, `Count == 1 -> weapons[0]`, sinon max
  par `Range.GetValueOrDefault(0)` (`<=`, donc le DERNIER a egalite).

**L'ensemble VIDE est l'unique porte de sortie `null`** — donc l'unique regime de refus.

## 3. Ce que la regle deplace, VENTILE sur le catalogue (683 unites, re-derive)

| regime | unites | la regle deplace-t-elle un verdict ? |
|---|---|---|
| caster sans arme A DISTANCE, cible NON adjacente | 271 | **non** — le volet PORTEE refuse deja EN AMONT (`onlyAdjacent = IfNotRangedCaster` vrai pour un caster non-ranged). Meme refus, autre raison. |
| caster sans arme de MELEE, cible ADJACENTE | **0** | regime VIDE : aucune unite n'a une arme a distance sans arme de melee. |
| caster sans AUCUNE arme | 81 | **OUI** — les deux branches rendent `null`, le natif refuse TOUTE cible. |

Sur les 81 sans arme, **79 portent le bit** (type generique `69`) ; les 2 autres sont les Spore Mines
(`tyranNpc6SporeMine`, `tyranSmnSporeMine`), dont le type `1146 FloatingDeath_NormalAttack` ne le
pose pas — **le natif desarme lui-meme la regle exactement sur les deux unites sans arme qui
attaquent**. C'est la table par type (#419-r1-tr14-r5-r2-r1-r2) qui porte cette distinction : sans
elle, ce port armerait un refus sur cinq types que le natif desarme.

⚠ **Les 11 MACHINES OF WAR de ce lot n'ont AUCUNE attaque normale, et c'est STRUCTUREL** :
`IdunBattle.Entities.Factories.MachineFactory$$Build` n'appelle jamais
`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` (unique xref de code :
`UnitFactory$$Build`). Ce port ne peut donc pas leur fabriquer un refus — elles n'en ont pas.
Le risque « les MoW ne pourraient plus attaquer » est ecarte par lecture, pas par pari.

**Aucun caster a arme `Range == 1` au catalogue** (mesure : 0) — le seuil `< 2` de `get_IsMelee` ne
separe donc aujourd'hui aucun cas reel, mais il est mirrore tel quel.

## 4. Le port

* `engine/services/battle_query.py` — `get_attack_weapon_for_default_normal_attack_from_tiles`
  (slot `0xb0`) : compose `find_melee_weapon` / `find_ranged_weapon`, deja portes fidelement.
  A NE PAS confondre avec `get_attack_weapon_for_default_normal_attack` (distance-aware), qui sert
  la selection d'arme des DEGATS.
* `engine/runner/abilities/targeting.py` — `normal_attack_dynamic_invalid_target_reason`, cablee
  dans `_NormalAttackTargeting.get_dynamic_invalid_target_reason`.

**Le rayon de souffle est borne par le BIT** : la cascade n'appelle cette methode que sous
`options.has(TR.TargetMatchesDynamicRule)`. Les 5 types a `0x4000` ne l'atteignent jamais.

**TRI-ETAT DU SUBSTRAT** : `GC.unit(visualId)` absent = substrat NON MESURE -> `0`, aucun refus
invente. A ne pas confondre avec `weapons == []`, qui est une MESURE et refuse.

## 5. La CONFRONTATION

`probe_419r1tr14r5r2r1r2r1_normal_attack_dynamic_rule.py` — **deux summons de la MEME equipe**,
invoques par le MEME cast (`genesPrimus` -> `CultDemagogue` 1179), meme attaque normale `69`, meme
geometrie. **Seules leurs armes different** :

| caster | `weapons` (kit ET `BC.Units`) | role |
|---|---|---|
| `genesSmnDecoy` | `[]` | DISCRIMINANT |
| `genesSmnNeophyte` | `[melee Physical, Projectile R2]` | TEMOIN |

Substrats CONCORDANTS — indispensable : le port lit le kit gameconfig la ou le natif lit le
`WeaponsComponent`. Un montage qui ne viderait que `BC.Units[].Weapons` mesurerait la divergence des
SUBSTRATS, pas la regle.

Geometrie PILOTEE, et l'ORDRE a ete mesure : on amene D'ABORD `genesPrimus` au contact, on caste
ENSUITE (les summons apparaissent autour du caster). La voie inverse — subir le spawn au camp de
depart puis pousser les ennemis vers les summons — a ete **essayee et abandonnee** : les decoys sont
`Steppable` et ephemeres, la geometrie se defaisait tour par tour et les ennemis disparaissaient
avant la mesure.

Oracle natif : `abilityReason(casterId, 69, targetId)` -> `AttackQuery$$GetInvalidTargetReason`.

```
CASTER SANS ARME  u160 genesSmnDecoy          natif       portApres   portAvant
  u77 tauCrisis        d=2                    0x8000000   0x2         0x0        <- DISCRIMINANT
  u79 tauMarksman      d=2                    0x8000000   0x2         0x0        <- DISCRIMINANT
  u81 necroSpyder      d=1                    0x2         0x2         0x0        <- DISCRIMINANT

CASTER ARME       u114 genesSmnNeophyte       natif       portApres   portAvant
  u77 tauCrisis        d=2                    0x8000000   0x8000000   0x8000000
  u79 tauMarksman      d=1                    0x0         0x0         0x0
  u81 necroSpyder      d=2                    0x8000000   0x8000000   0x8000000
```

**VERDICT (refuse/accepte) : 6/6 apres, 3/6 avant, 3 GAGNEES, 0 PERDUE.**
**CODE (regle exacte) : 4/6 apres, 3/6 avant.**

La ligne `d=1` est le discriminant PUR : le natif rompt `TargetMatchesDynamicRule`, la baseline
l'ACCEPTAIT (`0x0`). Le temoin est inchange sur les 3 lignes — aucune cible legitime perdue.

**CONTRE-EPREUVE JOUEE** : refus neutralise (`return 0` avant le retour reel, mutation VERIFIEE en
place), **3 crans sur 9 rougissent** :

```
FAILED test_le_port_est_daccord_avec_le_natif_sur_le_verdict
FAILED test_la_baseline_diverge_du_natif
  AssertionError: REGIME DEGENERE : la baseline (regle non portee) est d'accord partout -- cette
  geometrie ne separe pas les deux modeles (il faut un caster SANS ARME et une cible ADJACENTE)
  assert 0 >= 1
FAILED test_le_refus_est_nomme_sur_la_ligne_adjacente
  assert 0 == 2
```

Le port a ete restaure et re-verifie identique a HEAD (0 diff, 0 trace de mutation).

## 6. Ce qui GARDE

* `tests/engine/test_419r1tr14r5r2r1r2r1_normal_attack_dynamic_rule_live.py` — 9 crans : les trois
  etages hors ligne, le montage, l'accord sur le VERDICT, la contre-epreuve (regime degenere), la
  non-perte, le temoin arme inchange, et le refus NOMME.
* `test_419r1tr14r5r2r1r2_normal_attack_options_live.py` cran 5 **change de sens** — et c'est la loi
  que sa version precedente ANNONCAIT (« il rougira quand la regle sera portee, et c'est voulu »).
  Il assertait l'INERTIE du bit ; il garde desormais que la regle **ne mord pas un caster ARME**
  (`necroWarden` a melee ET distance -> les deux `Find*Weapon` rendent non-null). Loi plus FORTE :
  elle interdit l'echec symetrique, restrictif.

## 7. Residus nommes

* **`#419-r1-tr14-r5-r2-r1-r2-r1-r1` — `get_range` desarme `only_adjacent` quand la portee d'arme
  n'est pas observable.** `unit_weapon_range` rend `None` pour les 81 unites sans arme (`StatType.Range`
  n'est pas dans `combatSnapshot`), et `get_range` en deduit `return None`, ce qui abandonne TOUT le
  volet portee — **y compris la branche `only_adjacent`, qui n'utilise pourtant jamais la valeur**
  (`get_range_broken_rule` : `if rr.only_adjacent: ... are_entities_adjacent(...)`). Le natif, lui,
  calcule `onlyAdjacent` AVANT la valeur et le teste independamment. Mesure : les 2 lignes `d=2`
  ci-dessus, ou natif et port refusent tous deux mais le port impute le refus a
  `TargetMatchesDynamicRule` au lieu de `TargetIsInRange`. **PREEXISTANT** (avant cette tranche ces
  memes lignes rendaient `0x0`, c.-a-d. ACCEPTE) et **hors mandat** : le foyer `get_range` est
  partage par TOUTES les abilities, le resserrer demande sa propre confrontation. Point d'ancrage :
  `engine/runner/abilities/targeting.py::get_range`, la branche `if value is None: return None`.
* **`#419-r1-tr14-r5-r2-r1-r2-r1-r2` — le port n'a AUCUN canal d'ENTITE pour les armes.**
  Le natif itere le `WeaponsComponent` de l'ECS ; le port lit le kit gameconfig
  (`GC.unit(visualId).weapons`), comme le faisaient deja `find_melee_weapon` / `find_ranged_weapon`.
  En bataille standard les deux concordent (`buildNormalizedBC` derive du catalogue, et
  `BC.Units[].Weapons` porte bien `IsMelee`/`IsRanged`), mais un montage qui patche `BC.Units[].Weapons`
  seul les ferait diverger — et rien ne le signalerait. Capteur manquant, point d'ancrage natif a
  hooker : `IdunBattle.Entities.Components.WeaponsComponent` (par entite), a projeter dans
  `combatSnapshot.units[]`. **Aucun hook existant ne le publie** (verifie : `frida/hooks/` n'a que
  des dumps de CHAMPS de classe, `dump-weapons*.ts`, pas de donnee par entite). Demande un reinject,
  donc hors de portee d'un agent.
* **`#419-r1-tr14-r5-r2-r1-r2-r1-r3` — la surcharge slot `0xaf` n'est pas portee.**
  `GetAttackWeaponForDefaultNormalAttack(attacker, attackerTiles, target)` resout
  `BattleQuery$$GetAbilityAttackRangeType` puis teste `UnitExtensions$$HasFlag(attacker, 0x15)` et
  `AreEntitiesAdjacent`. Aucun consommateur PORTE ne l'emprunte (la regle dynamique passe par
  `0xb0`) — donc rien a porter aujourd'hui, mais le recensement le dit plutot que de le taire.
