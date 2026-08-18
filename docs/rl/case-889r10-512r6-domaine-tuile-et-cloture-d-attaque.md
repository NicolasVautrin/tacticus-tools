# case-889r10 / 512r6 / 1008r3 / 927r1 — le domaine TUILE, la cloture d'attaque, et deux identites de classe

Tranche du 2026-08-18, build `t6dpr4k06g`, session Frida 11.
Items : `#889-r10`, `#512-r6`, `#1008-r3`, `#927-r1`.

Foyers edites : `engine/runner/abilities/behaviours/combat.py`, `engine/entities/triggers.py`,
`engine/runner/operations/damage_ops/ability.py`,
`engine/runner/operations/triggers/dispatch/attack.py`,
`engine/runner/operations/triggers/loki/{helspear,fury_of_the_ancients,fabricator_claw_array}.py`.
Cliquets neufs : `tests/engine/runner/test_889r10_domaine_tuile_offline.py`,
`tests/engine/runner/test_927r1_amountiszero_offline.py`, plus l'extension de
`tests/engine/runner/test_512r4_on9_cardinalite_offline.py` et trois tests dans
`tests/engine/test_1008_black_legion_relics_offline.py`.
Probe neuf : `scripts/python/probe_889r10_allie_sur_la_ligne.py`.

**Verdicts** : les QUATRE items sont RESOLUS. Deux d'entre eux avaient une premisse FAUSSE, et les
deux fautes sont la MEME : **`$$.ctor` n'est pas l'identite de classe**.

---

## 1. `#889-r10` — le « NON LU » etait LISIBLE, et le port avait raison

### 1.1 Ce que le decompile dit

Le residu declarait non lu « ce que `SelectSingle(entities, 8)` fait d'une entite TUILE ». Le slot
**8** d'`ITargetsSelector` n'est pas un « SelectSingle » — aucun symbole de ce nom n'existe dans le
build — c'est `IdunBattle.DSL.TargetsSelector$$SelectActor`
(`data/symbols/<build>/metadata/interface_slots.tsv`). Sa chaine est lisible jusqu'au bout :

```
TargetsSelector$$SelectActor(this, entities, selectionType) :
    foreach (entity in this.<slot 23 = Select>(entities)) {
        if (entity == null) continue;
        unit = TargetsSelector.SelectUnit(this, entity, selectionType);   # surcharge ENTITE
        if (unit != null) return unit;
        if (EntityExtensions.IsMachine(entity)) return entity;
    }
    return null;

TargetsSelector$$SelectUnit(this, entity, selectionType) :               # surcharge ENTITE
    if (EntityExtensions.IsUnitFoot(entity) || EntityExtensions.IsTile(entity))
        entity = UnitExtensions.GetUnit(entity, this.<+0x10 = State>);
    return (entity != null && IsUnit(entity)
            && MatchesUnitSelectionType(entity, selectionType, State)) ? entity : null;
```

**Une TUILE resout en son OCCUPANT.** Corrobore par un SECOND etage independant :
`IdunBattle.Entities.EntityExtensions$$GetCurrentPlayer` porte lui-meme une branche
`<TileEntity> -> UnitExtensions.GetUnit(entity, state) -> RECURSION`.

Meme forme cote ATTAQUE : `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$Execute` n'a
**aucune** branche mono/multi — il resout son caster par `SelectActor` (slot 8) et applique
`UnitExtensions$$GetUnit` a CHAQUE entite rendue par `Select`, sautant la cible quand le resultat
est nul (operation `0x25`, tag `0xa1`).

### 1.2 L'ecart, et sa signature

Deux foyers du port, tous deux **PERMISSIFS et SILENCIEUX** :

* `combat.py`, collapse mono-cible : `dsl.base.resolve_unit` rend le premier **dict**, donc `None`
  sur un id de tuile -> `targets = []` : aucune emission, aucune mutation, aucune erreur ;
* `triggers.py::_select_actor` : meme cause, mais l'effet s'INVERSE. Un operande qui ne resout rien
  fait rendre FAUX a `AreFriends`, et `AreEnemies` est une negation NUE (#963-r4) — donc
  `AreEnemies(Owner, <tuile>)` valait **VRAI POUR TOUT OCCUPANT, ALLIE COMPRIS**.

### 1.3 Le correctif

`combat.py::_collapse_mono_cible` sert desormais `AttackWithAttackDamage` **et**
`AttackWithAbilityDamage`. Il evalue le selecteur **UNE SEULE FOIS** — load-bearing : un selecteur
peut consommer le PRNG (`Randomize`, `PickRandomly`), donc une seconde passe deplacerait la sequence
de tirages. `triggers.py::_select_actor` resout la tuile par le foyer unique
`dsl.base._occupants_by_tile` (indexe par les PIEDS, donc n'importe quel pied d'une multi-hex rend
SON unite).

### 1.4 Ce qui l'etablit

* **Cliquet offline** `test_889r10_domaine_tuile_offline.py` — 10 tests, avec CONTRE-CAS integre
  (`resolve_unit` rend `None` sur la meme entree ; l'ancien `_select_actor` aussi) et TEMOIN
  (sur un ENNEMI les deux regimes s'accordent, donc l'ecart porte bien sur le CAMP). Contre-epreuve
  JOUEE : mutation des deux foyers -> **5 failed / 5 passed**, source restauree -> 10 passed.
* **Le montage qui TRANCHE, joue LIVE** — `probe_889r10_allie_sur_la_ligne.py`, **RC 0**. Deux
  passes : une RECO qui relit les tuiles marquees `1518`, puis une MESURE ou l'allie est pose
  DESSUS. TROIS non-vacuites assertees, pas supposees : l'allie porte la marque `1518` ; il est de
  la MEME equipe que le caster ; il est ENCORE sur sa tuile au moment du coup differe. Resultat :
  allie `ultraTitus` en `(1,3)` -> **HP 9537 -> 9537, PAS FRAPPE** ; ennemi `u88` ->
  **400000 -> 348024**. L'hypothese concurrente (« le natif compare l'equipe de la TUILE ») est
  **REFUTEE LIVE**.
* **Non-regression** — `probe_889r7_instruments_phase2.py` : ACCORD BIT-EXACT
  (`88: 400000 -> 387447`, `92: 400000 -> 376210` des deux cotes), spawn 4/4 sur les MEMES tuiles,
  marques `1518` 13 posees -> 0 restantes.

---

## 2. `#512-r6` — les DEUX evenements de cloture sortent de la MEME fonction

Fin de `IdunBattle.Operations.FinishAttackOperation$$Execute`, relue verbatim :

```
FUN_1800280e0(0x50, <IOperationProcessor>, proc, 9, entities)        # On(Attack = 9)   : TOUJOURS
if (*(char *)(currentAttack + 0x2c) != '\0')
    FUN_1800280e0(0x50, <IOperationProcessor>, proc, 10, entities)   # On(AttackDamageAttack) : GATE
```

`currentAttack` est le `GetCurrentAttack()` lu en TETE de la fonction : le gate **EST**
`is_attack_damage_op`, pas un second canal. DEUX ecritures suffisent :

* `combat.py::_emettre_finish_attack_de_noeud` emet les DEUX, dans l'ordre du decompile ;
* le call-site de `damage_ops/ability.py` porte desormais `is_attack_damage_op and
  is_outside_attack` — jumeau exact de l'`emit_finish_attack` d'`On(9)` pose par `#512-r4`.

**Ce qui l'etablit** : `test_512r4_on9_cardinalite_offline.py` etendu (9 tests). Le cran qui compte
est le (6) : il MESURE sur l'OPERATION REELLE (`execute_ability_attack` sur un `State` complet et un
PRNG cale) que `is_outside_attack = False` eteint **9 ET 10 ensemble**, et que `On(8)` / `On(0x42)`
survivent des DEUX cotes — sans quoi le gate aurait pu eteindre autre chose que la cloture. Le cran
(4) asserte la **SEQUENCE**, pas des comptes : avant cette tranche, le noeud cloturant apres ses
feuilles, `On(10)` partait le PREMIER. Contre-epreuve JOUEE : mutation des deux gates ->
**4 failed / 5 passed**.

Live : `probe_487_hellfyre_missile_rack.py` **RC 0** (per-coup bit-exact
`[(81, 2792), (81, 2792), (83, 3989), (85, 2792)]`, etage « 3ter doublement conditionnel » vert),
plus 65 tests live verts sur les consommateurs (`haze`, `overwatch`, `terminator`, `shock assault`,
`overwhelming wrath`, `daemonic patrons`).

**PORTEE NEUVE, ET ELLE EST DITE** : `HazeOfCorruption` passe deja `is_attack_damage_op=True` au
foyer de NOEUD (lecture ecrite avant cette tranche : ses feuilles sont des
`DSLBehaviors$$AttackDamage`, donc `AttackDamageOperation$$Execute` pose `+0x2c`). Elle emet donc
desormais **UN** `On(10)` la ou elle n'en emettait AUCUN — une fois par `Attack(...)`, jamais N.
C'est ce que le natif fait ; le consommateur concerne (`LegendaryCommander_ExtraHits`) n'est pas
idempotent, d'ou la mention explicite. Les 27 tests live d'`HazeOfCorruption` restent verts.

**Residu ouvert** : `#512-r7` — sur une feuille AUTONOME, la paire de cloture encadre `On(8)` et
`On(0x42)` au lieu de les suivre. Ecart d'ORDRE anterieur a `#512-r4`, mesure ici
(`[5, 6, 57, 15, 16, 9, 8, 66, 10]`) et non observe par aucun consommateur porte.

---

## 3. `#1008-r3` — le nom de CHAMP est plus fort que le nom de classe

Le residu cherchait l'appariement par la TAILLE de classe et declarait `BLOCAGE: capteur`. Aucun
capteur n'etait requis : le RPC `classFields` est en vol, en lecture pure, sans runner. RE-MESURE
du 2026-08-18 (session 11) :

```
+0x40 True   +0x48 False   +0x50 IsOwnerEmpty   +0x58 HasOwnersActiveAbilityBeenUsed
+0x60 No     +0x68 Never   +0x70 Yes
```

Elle CONFIRME l'identification de `#1064` et REFUTE au passage une premisse intermediaire du
residu : `<+0x50>` n'est pas `NoTrigger` mais `IsOwnerEmpty`, donc l'enumeration « trois classes
derivant d'`AbilityTrigger` de taille 16 » ne pouvait de toute facon pas trancher.

SEMANTIQUE, lue au corps de
`IdunBattle.DSL.HasActiveAbilityBeenUsedByOwnerAbilityTrigger$$ShouldTrigger` — jamais deduite du
nom :

```
foreach (a in owner.<ActiveAbilitiesComponent>.<+0x20>)
    if (StaticBattleRules.ActiveAbility.IsActiveAbility(a.<+0x44>) && a.<+0x28> == 0)
        return true
return false
```

Les deux offsets sont DEJA nommes par le port (`runner/components.py::ActiveAbility` :
`+0x44 AbilityName`, `+0x28 CanStillBeUsed`) et `IsActiveAbility` est deja mirrore
(`runner/abilities/attack_type.py`, y compris ses cinq litteraux d'exclusion) : ce port ne
re-derive **aucun** etage.

**TRI-ETAT, par mesure et non par gout** : `runner/snapshot.py::_active_abilities` n'ajoute le
composant que si la vue de decision porte `allAbilities: true` — il le DIT. Composant ABSENT =
canal NON MESURE -> on ne bloque pas, ce qui est STRICTEMENT le comportement d'avant ce port ;
composant PRESENT et VIDE = mesure -> FAUX.

**Ce qui l'etablit** : trois tests dans `test_1008_black_legion_relics_offline.py`, qui REMPLACENT
le cran-signal `assert "CINQ" in src` — celui-la etait le signal du residu et devait tomber avec la
tranche. Contre-epreuve JOUEE : gate neutralise -> **3 failed / 23 passed**.

**NON CONFRONTE LIVE** : Helspear est une RELIQUE (etat 2 — montage `--equip-relic`), comme
`#1008-r2` le note deja.

---

## 4. `#927-r1` — deux offsets justes, deux classes differentes

Le residu demandait de relire le `.ctor` **au desassemblage**. Fait :

```
DSLFormulas$$.ctor  prologue `mov rdi,rcx`                 -> rdi == this
                    `xor edx,edx ; call <ctor> ; mov [rdi+0x18],rbx`   -> +0x18 = Direct(0)
                    `mov edx,1   ; call <ctor> ; mov [rdi+0x20],rbx`   -> +0x20 = Direct(1)
DSLTriggers$$AmountIsZero
                    `mov rax,[rcx+0x10]`     -> le `dsl` (pose par DSLTriggers$$.ctor)
                    `mov rax,[rax+0x80]`     -> DSLFormulas
                    `mov rdi,[rax+0x20]`     -> minAmount = Direct(1)
```

Que `dsl+0x80` soit bien `DSLFormulas` est **prouve** et non suppose :
`FuryOfTheAncientsAbility$$CreateBehaviour` appelle `DSLFormulas$$ConfigConst` sur CE champ du MEME
`dsl`, et lit `+0x20` en `maxTargets` quelques lignes plus loin.

**Les deux call-sites lisent donc `Direct(1)`. La premisse est REFUTEE.** Ce qui differe est la
CLASSE allouee, et le discriminant est l'`Il2CppClass*` passe a l'allocateur :

| factory `DSLTriggers$$…` | classe allouee | `minAmount` lu |
|---|---|---|
| `AmountIsZero` | A | `<formulas+0x20>` = 1 |
| `AmountIsEqualOrGreater` | **A** (la meme) | argument |
| `AmountIsGreaterThanZero` | B | `<formulas+0x18>` = 0 |
| `AmountIsGreater` | **B** (la meme) | argument |

Or les deux `ShouldTrigger` sont NOMMES et ne comparent pas pareil :
`IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger` finit par
`return minAmount.Calculate() <= value;`, quand
`IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger` finit par `<`. Leurs
`.ctor` sont des corps TRIVIAUX que l'ICF a FONDUS — Ghidra affiche
`AmountIsGreaterAbilityTrigger$$.ctor` aux deux sites, et la RE d'origine a lu le `ShouldTrigger` de
la MAUVAISE classe.

D'ou : `AmountIsZero(x)` = `NOT (1 <= x)` = **`x == 0`**. Tout s'accorde alors — le NOM, la mesure
`probe_927 --solo`, et la VIVACITE de `FabricatorClawArray` (son selecteur est un
`PickRandomly(..., 1)`, donc `Count <= 1` toujours : la lecture `AmountIsGreater` en aurait fait un
gate `Count >= 2`, JAMAIS vrai — un reductio que le residu n'avait pas vu).

**Le PORT etait correct des deux cotes** (`MAX_TARGETS = 1`, `AmountIsZero` = `count <= 0`, ce que
`entities/triggers.py` ecrivait deja). Seules les CITATIONS etaient fausses ; elles sont corrigees.
Dans `fabricator_claw_array.py`, `<Zero @formulas+0x20>` portait **deux** erreurs qui se
compensaient : le champ est `One`, et la classe est `AmountIsEqualOrGreater`.

⚠ Le meme piege avait deja ete rencontre — et documente — sur l'aura (`#293`,
`engine/battle_query.py`). C'est la SECONDE occurrence connue du motif sur ce couple de classes.

Cliquet : `test_927r1_amountiszero_offline.py` (7 tests). Le cran discriminant compare le port a la
lecture REFUTEE et exige que l'ecart soit **ISOLE sur `x == 1`** — sinon la mesure ne designerait
pas le comparateur. Contre-epreuve JOUEE : `should_trigger` mute en `<= 1` -> **3 failed**.

---

## 5. Rayon de souffle rejoue

| fichiers | verdict |
|---|---|
| `test_889r10_domaine_tuile_offline.py` (neuf) | 10 passed ; **5 failed** sous mutation |
| `test_512r4_on9_cardinalite_offline.py` (etendu) | 9 passed ; **4 failed** sous mutation |
| `test_927r1_amountiszero_offline.py` (neuf) | 7 passed ; **3 failed** sous mutation |
| `test_1008_black_legion_relics_offline.py` | 26 passed ; **3 failed** sous mutation |
| `test_963r4_areenemies_null_operand_offline.py` + `test_963r1_...` + `test_944_...` + `test_925_boltstorm_faces_...` + `test_889r6_...` + `test_1077_...` + `test_523r1_...` + `test_overwatch_single_shot_per_activation.py` + `test_shock_assault_buff_expiry.py` + `test_963_red_rampage_geminae_...` | 124 passed |
| `test_1008r2_...` + `test_462_r4b_...` + `test_effect_1582_...` + `test_927_fury_offline.py` + `test_927r4_...` + `test_fabricator_claw_cap_binary.py` + `test_919_...` + `test_1081_...` | 70 passed |
| `test_487_hellfyre_missile_rack_live.py` / `test_haze_of_corruption_transfer_live.py` / `test_haze_bonded_chain_live.py` / `test_shock_assault_buff_live.py` | 4 + 9 + 18 + 7 passed |
| `test_overwatch_single_shot_per_activation_live.py` / `test_437_overwatch_consumes_armour_live.py` / `test_432_terminator_armour_cycle_live.py` / `test_503r1_overwhelming_wrath_phase2_live.py` | 1 + 4 + 4 + 10 passed |
| `test_911r1_daemonic_patrons_finale_live.py` | 8 passed |
| `test_927_fury_of_the_ancients_live.py` / `test_fabricator_claw_array_live.py` / `test_fabricator_claw_cap_live.py` / `test_repair_execution_live.py` | 12 + 8 + 10 + 7 passed |
| `probe_487_hellfyre_missile_rack.py` | **RC 0** |
| `probe_889r7_instruments_phase2.py` | **ACCORD BIT-EXACT** (roster repare a la main, cf. `#889-r12`) |
| `probe_889r10_allie_sur_la_ligne.py` (neuf) | **RC 0** |

**ROUGE PRE-EXISTANT, verifie sur un arbre `origin/master` FRAIS** (`git archive` dans un
repertoire jetable : **20 passed / 1 failed**) — donc PAS imputable a cette tranche et PAS repare
ici : `test_489r1_foyer_combat_offline.py::test_etage4_les_DEUX_noeuds_de_la_famille_ATTACK_le_threadent`.
Cause nommee et residu ouvert : **`#489-r3`**.

## 6. Ce qui n'est PAS couvert

* `#1008-r3` n'a **aucune confrontation live** : Helspear est une relique, etat 2.
* Le gate `MatchesUnitSelectionType` et le repli MACHINE de `SelectActor` restent hors du port
  (residu `#433-r3-r2` / `#1034`), et `_select_actor` le dit desormais au site.
* La normalisation AU SITE d'`instruments_of_vengeance_attack.py` (`Units(ActiveTarget(), 3)`) est
  devenue REDONDANTE. La retirer restaurerait le mirror 1:1 du natif (`ActiveTarget@+0x68` BRUT) et
  n'a **aucun effet observable** — non fait ici, ce fichier etant hors des foyers de la tranche.
* Sur la voie FEUILLE, l'ordre `9 / 8 / 0x42 / 10` reste celui du port : `#512-r7`.
* Aucun scenario live ne rend la CARDINALITE d'`On(10)` observable par un consommateur — meme
  limite que `#512-r4`, et pour la meme raison (les consommateurs d'`On(10)` portes sont
  idempotents ou absents des montages joues).
