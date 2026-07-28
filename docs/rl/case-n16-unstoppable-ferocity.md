# case-N16 — `UnstoppableFerocity_Owner` (1032) : le canal COUPS de la charge sur un porteur SUMMON

> **Build** `gqfc5mff6c`. Deuxieme consommateur de `IdunBattleLogic.Entities.DSLFactory$$IsCharging`
> porte sur le canal `CreateEffectHitsBonusForAttack`, apres `SagaOfTheWarriorBorn_Owner` (1223,
> `case-ischarging-hits-channel.md`). Residu **`N16`** de `port-residuals-inventory.md`.
>
> Ce qui est NOUVEAU ici n'est pas le canal — il etait deja ouvert — c'est le **porteur** : un
> SUMMON, donc un montage a deux etages.

---

## 1. L'artefact natif, et rien d'autre

`IdunBattle.Entities.Effects.Loki.UnstoppableFerocityOwnerEffect$$CreateEffectHitsBonusForAttack` :

```
EffectBonus.ForAddition(
    get_OwnerIsCaster & IsCharging(caster@0x160, target@0x178),
    Direct( AbilityConfiguration.GetNumberConstant(config@+0x60, 0x2b = extraHit) ),
    <AbilityOrEffect recopie de effect+0x14..+0x2c> )
```

**DEUX noeuds trigger, pas trois** — ni `IsNormalAttack`, ni `IsMeleeAttack`. C'est la meme forme
exacte que 1223, et c'est ce qui autorise le calque : le bonus vaut pour TOUTE attaque du porteur en
charge.

`.ctor` = `IdunBattle.Entities.Effects.ABondEffect$$.ctor(this, 1, 0,
AbilityOrEffect(0x40b = TriggeredAbilityType.UnstoppableFerocity))` — l'`AbilityOrEffect` est ecrit
en `effect+0x14..+0x2c`, exactement les octets que `CreateEffectHitsBonusForAttack` recopie dans le
3e argument de `ForAddition`. `config@+0x60` est donc la config de l'ability **1035
UnstoppableFerocity**, dont `constants.extraHit` vaut **1**.

MAGNITUDE : une **constante** (`GetNumberConstant`, pas `ConfigVar`) — ni indexee par niveau, ni
listee dans `variablesAffectedByRarityBonus`, donc **jamais scalee par le multiplier de rarete**.
Meme forme que `PowerTrip_FullHealth`, qui lit la meme cle 0x2b.

⚠ L'`IsCharging` de cet effet prend `caster@0x160` en 1er argument la ou 1223 prend `owner@0x148`.
Sous `OwnerIsCaster` les deux designent la meme entite : la semantique est identique. La difference
est notee parce qu'elle est REELLE au decompile, pas parce qu'elle change quoi que ce soit.

### Le JUMEAU, qui n'est PAS cet effet

L'i2 de `UnstoppableFerocity` porte **deux** clauses :

> « Scores one additional hit when attacking an enemy **Psyker**.
>   Scores one additional hit when **charging**. »

La premiere est un effet **SEPARE** — `UnstoppableFerocity_ExtraHit` (0x4a8 = **1192**) :

```
UnstoppableFerocity_ExtraHitEffect$$CreateEffectHitsBonusForAttack
    EffectBonus.ForAddition( HasTrait(target@0x178, 0x3ea = Psyker) & get_OwnerIsCaster,
                             Direct(1) )
```

Meme ability source (`BaseEffect..ctor(this, 1, AbilityOrEffect(0x40b))`), **aucun noeud
`IsCharging`**, magnitude litterale `1` (pas de config). Il est **hors perimetre** (l'inventaire le
classe non confrontable) et reste un `BaseEffect` no-op offline.

**Consequence de montage, pas de code** : les deux effets valent chacun **+1 coup**. Sur une cible
Psyker ils se confondraient et le regime discriminant ne discriminerait plus rien. Toute mesure de
1032 se fait donc sur une cible **NON Psyker** — garde explicite
`test_targets_are_not_psykers`, et le probe imprime les traits de la cible.

---

## 2. Le porteur est un SUMMON — et **un summon ne se pilote pas**

`blackSmnBloodletter` <<Bloodletter>> (`passiveAbilities: ["UnstoppableFerocity"]`, arme **1 coup**
Piercing, Movement 3) n'est pas dans `rl_duel.py --list-pool`. Le gate de confrontabilite passe par
son SUMMONER : `blackPossession` <<Archimatos>>, HERO du pool, dont l'**ACTIVE** `Incursion` (1021)
fait apparaitre jusqu'a `maxSummons`=6 Bloodletters sur les hex libres adjacents a sa cible.

C'est ce qui a decide du choix de l'item parmi les quatre de `N16` : des trois porteurs summon,
`blackSmnBloodletter` est le seul dont le summoner spawne par une ability **castable directement**
(`RedThirst` 1322 passe par `AggressiveOnslaught`, un TRIGGERED sur `On(0xb)` dont la face COMBAT
n'existe pas offline ; `FragLance` 1475 emprunte en plus un canal DIFFERENT, les coups
ADDITIONNELS).

Le montage vit dans `scripts/python/tests/engine/runner/_bloodletter_montage.py`. Le piege qu'il
encapsule est celui deja documente par `_summon_montage` : **la porte de TARGETING est plus large
que la garde d'EXECUTION**. `abilityTargets` publie une cible bien au-dela de 2 hex, alors que
`IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$GetNextSpawnTile` exige
`IsInRange(caster, target, range=2)` — un cast « legal » a distance 5 rend **zero** summon. Le
driver exige donc les DEUX conditions.

**AUCUNE face SUMMON offline n'est requise** pour que le lot conclue : le summon existe LIVE au
moment du snapshot, et `load_state` le reconstruit avec ses effets. GROUND TRUTH live (runner 2076,
seed 1357, MC1_67) — le Bloodletter frais porte, des son apparition :

    u98 blackSmnBloodletter owner=3 pos=(5,8)
        effects = ["UnstoppableFerocity_OwnerEffect", "UnstoppableFerocity_ExtraHit",
                   "BlessingsOfKhorne", "Daemon_ExtraBlock"]

Le nom capte est **`UnstoppableFerocity_OwnerEffect`** — le membre d'enum `EffectType`
(`effect-type-names.ts:157`), **suffixe `Effect` COMPRIS**. Il differe du nom de la classe native
(`UnstoppableFerocityOwnerEffect`) par un `_`, et du voisin 1192 (`UnstoppableFerocity_ExtraHit`,
sans suffixe) par ce meme suffixe. Le registre de la factory etant indexe par NOM, se tromper
dessus produit un port silencieusement inerte.

Ni `BlessingsOfKhorne` (%-degat) ni `Daemon_ExtraBlock` (source de BLOCK cote DEFENSE) ne touchent
au NOMBRE de coups : aucun confond sur l'observable.

### 2bis. Le harnais de charge ne s'applique PAS tel quel — et c'est structurel

`_charge_regime.ChargeRegimeHarness` veut **PILOTER** le caster : poser la geometrie, jouer le pas,
puis l'attaque. Ses `place()` fonctionnent (ce sont de vrais `MoveUnitOperation`), mais **l'attaque
finale est refusee**, parce qu'un summon n'est pas une unite du joueur : il est **AUTO-ACTIVE par
l'IA** au debut de chaque tour de son camp, et cette activation est **consommee par son
deplacement**. Mesures verbatim :

    [endturn] mutated=True currentPlayer=3
    [caster]  hasAction=False
    [manuel]  mutated=False eventCount=2 hits=[]      <- applyAction {kind:"ability"} : signature #111
    [ia]      activations=1 demos=1 hits=[]           <- aiPlayByUnit ne le fait pas attaquer non plus

Il **rebouge** seul au tour suivant et **expire** apres ~2 tours :

    [apres-place(0,0)] cp=4  summon pos=(0,0)
    [endturn#1]        cp=3  summon pos=(0,3)     <- 3 hex vers l'ennemi (Movement=3)
    [endturn#3]        cp=3  summon pos=(2,5)
    [endturn#5]        cp=3  summon ABSENT

**La sortie n'est pas de trouver le bon appel, c'est de changer de POSTURE** : on pose la geometrie,
on laisse l'IA jouer, et on LIT le resultat dans les `changes` de l'`applyAction endturn` — qui
portent exactement ce qu'il faut :

    {"squadId": 77, "from": (0,1), "to": (0,1), "moved": false,
     "hpBefore": 118279, "hpAfter": 114994, "hpDelta": -3285}     <- la CIBLE encaisse
    {"squadId": 99, "from": (0,3), "to": (0,2), "moved": true,
     "hpBefore": 3888,   "hpAfter": 3888,   "hpDelta": 0}         <- le SUMMON a CHARGE

⚠ `eventCount` vaut **0** sur cette action et `events` est **vide** : les coups n'y sont pas publies
event par event. Le `hpDelta` des `changes` est la seule observable du degat.

**Deux pieges de ROSTER, tous deux mesures** (detail dans `_bloodletter_montage.py`) :

1. Un Bloodletter n'a **pas** de PV gonfles (`--hp-player` ne s'applique qu'aux unites du BUILD :
   il a 3888 PV) — il meurt au moindre degat, et le montage se lit alors comme « geometrie non
   realisable ». Avec `necroWarden,necroDestroyer` la trace des poses le dit sans ambiguite : la 1re
   pose du caster echoue, puis TOUTES les suivantes ont une position de depart `None` (l'unite n'est
   plus dans `alive()`). `necroDestroyer` porte **Overwatch** (il tire sur toute unite qui bouge dans
   sa zone — et les `place()` SONT des deplacements), `necroWarden` porte `RelentlessMarch_DangerZone`.
2. Cible **non Psyker** (cf. §1) — sinon 1192 et 1032 se confondent.

`orksNob` / `tyranTyrantGuard` / `admecMarshall` / `astraBullgryn` satisfont les deux conditions.

**Corollaire : UN RUNNER PAR REGIME.** Sans `endturn` entre deux poses, aucun
`FinishUnitTurnOperation$$Execute` ne survient, et `UpdateCharging` **ajoute sans jamais vider**
(mirror lu : `if (!before.Contains(u)) if (!ChargedUnitIds.Contains(u.Id)) Add(u.Id)`) — enchainer
deux regimes sur le meme caster laisserait la charge du premier polluer le second.

---

## 3. Ce que le port ajoute — et ce qu'il ne re-ecrit pas

Le socle etait complet : le foyer `engine/battle_query.py::is_charging`, le gate
`engine/entities/effects/base.py::is_charging_attack`, et la cle `att_ctx["is_charging"]` posee
**une seule fois** par face (COMBAT : `runner/damage_model.py::build_hits_board`, la facade partagee
des deux vecteurs d'attaque ; PREDICTION : `playbook/prediction/normal_attack.py`).

Le port se reduit donc a **une classe + une entree de registre** :

| fichier | ajout |
|---|---|
| `engine/entities/effects/loki/hits.py` | `UnstoppableFerocityOwnerEffect` (mirror 1:1, calque de `SagaOfTheWarriorBornOwnerEffect`) |
| `engine/entities/effects/loki/__init__.py` | re-export |
| `engine/entities/effects/factory.py` | `"UnstoppableFerocity_OwnerEffect": UnstoppableFerocityOwnerEffect` |

Aucun predicat n'est re-derive, aucun contexte n'est elargi, aucun fichier partage n'est touche.

---

## 4. Mesure — la confrontation est **BIT-EXACTE**, pas encadrante

Le MT est recale sur le dump PRIS AVANT l'`endturn` et le pas ne consomme aucun tirage : le total
offline se compare au `hpDelta` live **a l'unite pres**. `off-1032` = meme rejeu, l'effet 1032
RETIRE du caster juste avant l'attaque — c'est la borne qui rend le MATCH probant (sans elle, un
accord pourrait etre le MATCH trivial « aucun bonus des deux cotes »).

`probe_ischarging_unstoppable_ferocity.py`, seed 1357 / `MC1_67`, cibles `orksNob,tyranTyrantGuard` :

| observation | live | offline **avec** 1032 | offline **sans** 1032 | `charged` offline |
|---|---|---|---|---|
| **temoin `on-appearance`** (apparait AU CONTACT, aucun `MoveUnitOperation`) | **1 coup, 1721** | — | — | — |
| **`CHARGE`** (pose a distance 2, l'IA l'amene au contact) | delta **3285** | n=**2** `[1707, 1578]` total **3285** ✅ | n=1 `[1707]` total **1707** ❌ | `[77]` |
| **`ADJACENT`** (pose au contact, cible amenee en dernier) | delta **1707** | n=**1** `[1707]` total **1707** ✅ | n=1 total 1707 | `[]` |

Le temoin `on-appearance` est ce qui separe « adjacent » de « a charge » : le summon apparait au
contact et frappe **l'arme nue**. Le spawn ne passe donc pas par `UpdateCharging`.

Generalisation — **autre board, autre seed, autres cibles** (`C1_25` / 31337 /
`admecMarshall,astraBullgryn`) : live delta **6104**, port **6104** (2 coups) ; sans l'effet, 3025.
Le rapport 6104 / 3025 vaut **2.02** — c'est bien un coup de plus, pas un scalaire.

### Le regime `STEP_ADJACENT` — le seul qui separe `IsCharging` de `HasFlag(Moved)`

Il est **construit offline sur un etat LIVE**, et c'est une contrainte, pas un raccourci : le caster
etant joue par l'IA, celle-ci **attaque sans bouger** quand elle est deja au contact (mesure :
`caster_moved=None` sur `ADJACENT`), et le pas de MONTAGE a lieu au tour PRECEDENT — or
`StartTurnOperation$$ResetUnit` purge le flag `Moved` a l'entree du tour. La situation « a bouge mais
n'a pas charge » **n'existe pas** dans une activation pilotee par l'IA.

On la fabrique donc depuis le snapshot LIVE d'`ADJACENT` (caster reellement au contact, effet 1032
reellement porte, `ChargedUnitIds` reellement vide) en rejouant un pas ADJACENT -> ADJACENT **par le
moteur** (`MoveUnitMessage`, donc `update_charging` + `set_moved_flag` poses par le moteur, jamais
declares) : `Moved` = VRAI, `IsCharging` = FAUX, port = **1 coup**.

### Epreuve du fix par MUTATION adversariale — deux mutations, deux signatures distinctes

**(a) le port RETIRE du registre** (`factory.py`, l'entree commentee) — 3 rouges, et exactement ceux
qui exercent la charge :

```
AssertionError: CHARGE : le port doit porter 2 coups (arme 1 + extraHit 1) ; obtenu n=1 [1707]
AssertionError: CHARGE (C1_25/31337) : live delta=6104, off+1032 n=1 [3025] total=3025, off-1032 total=3025
```

**(b) le GATE remplace par le proxy** — `build_hits_board` pose `unit_has_moved(state, att_id)` a la
place de `battle_query_is_charging(...)`, tout le reste inchange. **Exactement UN test tombe**, celui
du regime discriminant :

```
AssertionError: STEP_ADJACENT : le port sur-applique le +extraHit (gate `has_moved` ?) --
caster deplace de (0, 0) vers (1, 1) (cible en (0, 1), deja adjacente), attendu n=1, obtenu n=2 [1707, 1578]
```

La garde discrimine donc le GATE, et rien d'autre : ni la magnitude, ni le canal, ni le porteur.
Les deux mutations sont revertees (`git diff` vide sur `factory.py` et `damage_model.py`).

---

## 5. Ce qui n'est PAS couvert

* **La face PREDICTION** : elle est **traversee par construction** — `playbook/prediction/
  normal_attack.py` thread deja la cle `is_charging` dans le board du canal COUPS, et l'agregateur
  `hits_bonus_from_effects` interroge les memes effets d'attaquant. Elle n'est en revanche **pas
  mesuree ici** : la face DECISION d'un summon passerait par `aiPlaybookPredict` sur une unite que
  l'IA active elle-meme, ce que le montage d'observation ne permet pas d'isoler. Non fait, dit.
* **Le nombre de Bloodletters** : `Incursion` peut en invoquer jusqu'a 6 ; les mesures ci-dessus en
  ont eu **1** (geometrie des hex libres autour de la cible). L'effet est per-porteur, donc rien ne
  depend du compte — mais aucun scenario multi-summon n'a ete exerce.
* **`UnstoppableFerocity_ExtraHit` (1192)**, la seconde clause du meme kit (+1 coup vs Psyker, sans
  `IsCharging`) : hors perimetre, non porte, reste un `BaseEffect` no-op. Il est **materialise live**
  sur le summon — d'ou la garde « cible non Psyker », qui n'est pas une precaution theorique.
* **L'absence de `CreateActiveCondition` / de face CRIT sur 1032** repose sur la table de symboles
  (seuls `.ctor` et `CreateEffectHitsBonusForAttack` y figurent pour cette classe) — or l'absence
  dans les tables ne prouve rien (corps dedupliques). Le contre-argument reel est live : l'effet est
  `active: true` des l'apparition et le port est confronte dans cet etat.
* **Les 3 consommateurs de charge restants** du canal COUPS / ADDITIONNELS / ActiveCondition
  (`RedThirst_ExtraDamageAndHit` 1322, `FragLance` 1475, `BloodChalice_ExtraPiercing` 1369) —
  residu `N16`, chacun une tranche a part entiere.
