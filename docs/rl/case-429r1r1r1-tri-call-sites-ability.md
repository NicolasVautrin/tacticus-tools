# #429-r1-r1-r1 — Le gate cadavre de la famille ABILITY : 1 site sur 9, et les 8 autres seraient un fork

**Livré le 2026-08-05.** Build de référence : `rnca9r7q6c`.

`#429-r1-r1` a posé le gate cadavre au **foyer** de l'attaque NORMALE, parce que ses 11 call-sites
empruntent tous, côté natif, la même porte. La famille ABILITY est le contre-exemple : ici le
foyer ne doit **pas** être gaté, et le livrable est un **tri**.

## 1. Le décompte réel, et où la prémisse était fausse

| | prémisse du brief | mesure (AST, `--volet tri`) |
|---|---|---|
| call-sites d'`execute_ability_attack` | « ~9 hors `visit_ActiveAbilityMessage` » | **10 appels / 9 sites distincts** (splash en porte 2) |
| dont dans `visit_ActiveAbilityMessage` | sous-entendu : il y en a | **0** |

Le visiteur **n'appelle jamais** `execute_ability_attack` : il dispatche vers les classes du
registre, qui atteignent le foyer par leurs feuilles DSL. « L'ability déclenchée n'est gatée que
par son visiteur » décrit donc bien le trou, mais pas la topologie — aucun des 9 sites n'est un
`UseActiveAbility` non plus (cette feuille route vers `AttackDamageOperation.execute`, déjà gaté).

## 2. Le critère est natif, et il se mesure en xrefs

`IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility` a exactement
**DEUX appelants CODE** dans tout le binaire :

* `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
* `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteForReplacedTarget`

et l'étage qui y mène est verrouillé de la même façon : `ActiveAbilityOperation$$Execute` n'a que
deux appelants code (`Core.Services.OperationProcessor$$ActiveAbility` + la ré-entrée), et
`ExecuteInternal` **un seul**.

L'étage des nœuds DSL d'attaque, lui, ne gate **rien** — lu au décompilé :

```
IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute
  -> IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget
  -> Core.Services.OperationProcessor$$AttackDamage
  -> IdunBattle.Operations.AttackDamageOperation$$Execute      # GetCurrentAttackOrDefault,
                                                               # GetAttackHits, SetupHitGroup,
                                                               # ExecuteHits -- aucun test de mort
```

Idem pour `IdunBattle.Entities.Behaviours.ChainLeftOverHitsAttackDamageBehaviour$$Execute` et
`IdunBattle.Operations.AbilityDamageOperation$$Execute` (ce dernier teste
`IdunBattle.Entities.EntityExtensions$$IsUnit` pour lire une stat, jamais `IsAlive`).

> **Un site se gate si et seulement s'il ÉMULE un cast d'ability active.** Un site qui mirror un
> nœud DSL d'attaque interne à une behaviour ne se gate pas : l'y gater serait un fork.

## 3. Le tri, site par site

| site | verdict | artefact natif |
|---|---|---|
| `summon_ai.py::_apply_active_ability` | **GATÉ** | `ActiveAbilityOperation$$ExecuteInternal` — repli générique qui émule un cast d'ability active |
| `combat.py::AttackWithAttackDamage::execute` | non gaté | `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` |
| `combat.py::ChainLeftOverHitsAttackDamage::execute` | non gaté | `ChainLeftOverHitsAttackDamageBehaviour$$Execute` |
| `combat.py::AttackWithAbilityDamage::execute` | non gaté | `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` |
| `splash.py::_splash_ability_behaviour` (×2) | non gaté | `CrushingClawsAbility$$ExecuteBehaviour` — nœuds internes ; **plus aucun appelant production** (oracle des tests DSL) |
| `genestealer.py::…::_counter_attack` | non gaté | `HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour` |
| `destroyer_hive.py::…::execute_behaviour` | non gaté | `DestroyerHiveAbility$$CreateBehaviour` |
| `hailstrike.py::…::execute_behaviour` | non gaté | `HailstrikeAttackAbility$$CreateBehaviour` |
| `haze_of_corruption.py::…::execute_behaviour` | non gaté | `HazeCorruption_BonusHitAbility$$CreateBehaviour` |

Trois non-gatés méritent leur raison propre, parce qu'elle n'est pas la même :

* **`genestealer`** — le natif gate la vie de la cible **dans l'arbre**
  (`IsAlive(attaquant) & IsAlive(judh)`), et le port porte déjà ce gate-là (`_counter_gate`). Y
  ajouter le gate d'ability serait un **second** gate que le natif n'a pas.
* **`destroyer_hive`** — la cible est vivante **par construction du sélecteur**
  (`Damageable(Enemies(AdjacentUnits(caster,1)))`), pas par un gate.
* **`haze_of_corruption`** — la cible est **morte par construction** : le trigger est
  `OnPreDeath(1,0) & get_OwnerIsActor & IsDead(Target@0x178)`. Le natif frappe le cadavre
  **exprès**, pour que le coup déborde en `LeftOverDamage`. C'est le site qui chiffre le prix d'un
  gate en bloc.

## 4. Le fix

Une seule ligne de gate, au **call-site** et non au foyer — le foyer ne peut pas le porter, les 8
autres sites l'interdisent :

```python
if is_dead_unit_and_not_allowed_by_ability(state, ABILITY_CLASSES.get(int(ability)), target):
    return {"ability": ability, "target": target, "routed": "dead_target_not_allowed"}
```

C'est la **troisième et dernière** porte de ce module : la voie « port dédié » est gatée en amont
par #429-r1 (dans `visit_ActiveAbilityMessage`), la voie attaque-normale par #429-r1-r1 (tête
d'`AttackDamageOperation.execute`).

`ability_class` est relu du registre plutôt que câblé à `None` : la branche n'est atteinte que
lorsqu'il vaut `None` (sinon la voie 1 a déjà rendu), mais la dérogation `GreatFrostAxe` (1089,
seul porteur du bit 38 `AllowDeadTarget`) reste ainsi portée si l'ordre des voies change. 1089
**est** au registre, donc la voie 1 le prend aujourd'hui.

**Le trou n'était pas anecdotique** : **56** abilities d'attaque active sont hors
`ABILITY_CLASSES` et atteignent ce repli.

## 5. Le chiffrage

### Offline (`--volet gate`), observable = total DEMANDÉ + tirages RNG

⚠ **Pas le delta de PV** : sur un cadavre les PV valent déjà 0, donc un bras en PV rend 0 que
l'attaque parte ou non — un bras muet qui se lirait comme un refus. La première rédaction est
tombée dans ce piège, et c'est la contre-épreuve « gate débranché » qui l'a fait rougir.

| bras | total | tirages |
|---|---|---|
| (a) `summon_ai`, cible **MORTE** | **0** | **0** |
| (a) même, **gate débranché** | **4739** | **12** |
| (b) `summon_ai`, cible **VIVANTE**, même porteur, même ability | **4739** | 12 |
| (c) foyer `execute_ability_attack` **nu** sur cadavre | **40** | — |
| (c) même, **gate posé EN BLOC** | **0** | — |
| (d) `HazeCorruption_BonusHit` sur cadavre | **40** | — |
| (d) même, **gate posé EN BLOC** | **0** | — |

Le couple (ability, porteur) est **dérivé**, jamais codé en dur, sous **trois** critères : hors
registre, classée attaque active, et **bornes non nulles** (`1044 IncendiaryShells` /
`templNeophyte`). Le troisième n'est pas cosmétique : `1015 PrecisionShot` — seul candidat porté
par un vrai **summon** (`necroSmnDeathmark`) — nomme sa variable `dmg` et non `minDmg`/`maxDmg`,
donc `ability_attack_params` rend `(0, 0)` et le bras vivant aurait mesuré 0 des deux côtés.

### Live (`--volet live`) — le bras qui rend le tri attribuable

Montage case-209 (`probe_209_haze_damage_transfer`), seed 777, PV cible **5000** : la cible meurt
avant le dernier coup, le coup bonus tombe sur le **cadavre**, sa `LeftOverDamage` part sur le
relais bondé.

| | dégât encaissé par le relais |
|---|---|
| **NATIF** | **4164** |
| **PORT** (arbre livré, ce tri) | **4164** — accord |
| **PORT** avec gate posé **EN BLOC** sur le foyer | **2767** |

Écart **1397** = exactement la contribution du coup bonus sur le cadavre (le montant du transfert
profil Toxic déjà mesuré par case-209). Un gate en bloc aurait donc fait **diverger le port du
natif** sur une mécanique vivante.

## 6. La garde

`tests/engine/runner/test_429r1r1r1_ability_attack_dead_target_live.py` — **9 tests, ~27 s**.

* le **cliquet** du tri : tout call-site doit être trié, tout site trié doit exister, et la
  **pose** du gate dans le code doit correspondre au tri. Un call-site neuf rougit ⇒ il devra être
  lu au décompilé avant d'être rangé ;
* **le cliquet a sa propre contre-épreuve** — 4 mutations de la table, 4 rouges attendus. Un
  cliquet qui ne rougit jamais ne garde rien. La mutation « site NON GATE déclaré GATE » est celle
  qui attraperait un gate posé en bloc ;
* les 4 bras + les 2 contre-épreuves offline ;
* le bras live. Montage KO ⇒ `pytest.fail`, jamais un skip.

Non régressé (re-joué, **54 tests**) : `test_429r1_dead_target_gate_live` (6),
`test_429r1r1_normal_attack_dead_target_live` (7), `test_summon_automatic_live` (8),
`test_summon_ability_ports_live` (2), `test_haze_of_corruption_transfer_live` (9),
`test_destroyer_hive_live` (6), `test_hailstrike_phase2_live` (4),
`test_chain_leftover_hits_live` (2), `test_damage_crushingclaws_live` (1).

## 7. Ce qui n'est PAS couvert

* **Le site gaté n'est pas confronté au NATIF.** Son refus est établi **structurellement** (le
  gate est sur le seul chemin d'exécution d'une ability active, mesure d'xrefs) et **offline**,
  pas par un montage live où un summon jouerait une ability hors registre sur un cadavre. La
  raison est celle déjà nommée en `case-429r1r1` §5 : `IsDeadUnitAndNotAllowedByAbility` et
  `IsInvalidTarget` sortent tous deux avant tout dégât, donc le live ne les **discrimine pas** —
  il redirait « le natif no-oppe », ce que `test_429r1_dead_target_gate_live` établit déjà pour le
  même gate natif. Ce que le live apporte ici de neuf est l'**asymétrie**, et c'est elle qui est
  mesurée (§5, Haze).
* **Le bras live ne couvre qu'UN des 8 sites non gatés** (`haze_of_corruption`). Les 7 autres sont
  triés au décompilé et gardés par le cliquet, pas confrontés individuellement.
* **Un seul seed / un seul board** sur le bras live (777, board de case-207). La généralisation
  n'apporterait rien ici : le discriminant est un écart structurel (le coup bonus part ou ne part
  pas), pas un scalaire à ajuster.

## 8. Résidus nommés

* **`#429-r1-r1-r1-r1`** — *le repli générique de `summon_ai` ignore les abilities dont la config
  ne nomme pas ses bornes `minDmg`/`maxDmg`.* Trouvé en chemin : `1015 PrecisionShot`
  (`necroSmnDeathmark`, le seul summon candidat) porte sa valeur dans `dmg` ; `ability_attack_params`
  aux clés par défaut rend `(0, 0)` et le repli inflige **0** — silencieusement. Combien
  d'abilities parmi les 56 sont dans ce cas n'est **pas mesuré** ici. Ce n'est pas un défaut du
  gate, mais du repli lui-même.
* ~~**`#429-r1-r3`** (ouvert par la tranche grand-parente) : `GreatFrostAxe` (1089).~~ **LIVRÉ le
  2026-08-05** — `case-429r1r3-gate-message-cible-morte.md`. Le tri de CETTE fiche est **intact** :
  le gate trouvé vit au rang du MESSAGE, pas au rang de l'opération, donc aucun des 9 sites n'a
  changé de verdict et le cliquet reste vert.

## 9. Re-dériver

```
python scripts/python/probe_429r1r1r1_ability_attack_dead_target.py --volet tri
python scripts/python/probe_429r1r1r1_ability_attack_dead_target.py --volet gate
python scripts/python/probe_429r1r1r1_ability_attack_dead_target.py --volet live --hp 5000
python -m pytest tests/engine/runner/test_429r1r1r1_ability_attack_dead_target_live.py -q
```

⚠ Les chiffres se re-dérivent : `9 sites` et `56 abilities hors registre` bougent à chaque tranche
portée.
