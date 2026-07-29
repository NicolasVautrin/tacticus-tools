# case-254 — Ce que la MIGRATION DE BUILD casse en silence, et les trois cliquets qui le referment

`gqfc5mff6c` -> `rnca9r7q6c` (2026-07-29). Symptome d'entree : `pytest
tests/engine/runner/test_targeting_masks_live.py` = **1 passed, 12 errors**, chaque erreur
`build runner KO (rl_duel): [error] initAndStart: system error`.

Trois causes INDEPENDANTES, toutes de la meme famille — **une donnee capturee sur l'ancien build
confrontee a du code neuf** — et aucune ne signale son etat degrade.

## 1. La correlation d'entree etait FAUSSE : ce n'est pas l'injection de catalogue

L'hypothese soumise etait « le seed BC augmente par `catalog_inject` est invalide ». **Refutee par
dichotomie**, en trois mesures :

| Montage | Resultat |
|---|---|
| `rl_duel build --seed 777 --board MC1_67` (roster aleatoire, 0 injection) | OK |
| roster EXPLICITE `eldarFarseer,eldarMauganRa,worldJakhal,worldKharn,eldarAutarch` vs `orksWarboss,orksNob,tyranWingedPrime,ultraInceptorSgt,eldarRanger`, **0 injection** | `initAndStart: system error` |
| chacun des 10 ids ci-dessus SEUL contre un temoin | 9 OK, **`ultraInceptorSgt` KO** |

La variable n'est ni l'injection ni le roster explicite : c'est **UNE unite du pool**,
`ultraInceptorSgt`. Le fixture `masks_da` injectait bien `darkaStormSpeeder`, mais `masks_ea`
n'injecte rien et echouait pareil — les deux partageaient `ultraInceptorSgt` dans `FOES`.

**Confirme independamment** par la bissection de #245, en ligne de commande directe (donc en amont
de tout code Python) : `... --a-units ultraInceptorSgt,ultraApothecary` -> system error ;
`... --a-units ultraEliminatorSgt,ultraApothecary` -> OK. Le repro minimal est **une seule unite du
pool**, sans la moindre injection.

Le diff d'enums, verifie AVANT d'aller plus loin (`probe_254_build_migration.py`), REFUTE aussi la
piste « ids d'ability renumerotes » : `ActiveAbilityType` 257 -> 260 membres et
`TriggeredAbilityType` 467 -> 476, **0 id renumerote**, **0 unite du catalogue** dont un id ne
resout plus vers une config presente. Les enums de la BC ont bouge par AJOUT, pas par insertion.

## 2. Cause A — le catalogue `BC.Abilities` est PERIME (le blocage)

`data/seed-bc.json` est la capture d'UNE bataille, faite sur UN build ; `scripts/python/
gameconfig.py` lit le fichier **VIVANT** de `AppData/LocalLow/Snowprint`, donc celui du build
COURANT. Une MAJ qui **AJOUTE** une variable ou une constante a une ability laisse la capture en
arriere — et le code natif neuf la lit.

**Decompile (verite) —** `IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant` fait un
`TryGetValue` sur `Constants` (this+0x18) ; sur ECHEC il construit une `System.Exception` et la
**LEVE** (`System_Exception___ctor` puis le throw). `$$GetNumberConstant` y delegue,
`$$GetVariableForLevel` a la meme forme. Une exception managee levee sous `invokeMethod` remonte
cote Frida en **« system error »**.

**Ou la faute frappe depend de QUAND la cle est lue.** Pour `ultraInceptorSgt` c'est au
DEPLOIEMENT, donc `initAndStart` lui-meme :
`IdunBattleLogic.Entities.Abilities.Active.Loki.ShockAssaultAbility$$CreateTrigger` bâtit l'arbre DSL
du passif a la creation de l'unite, et appelle `$$GetAffectedUnits`, dont la premiere ligne utile est
`GetStringConstant(...)` -> `DSLTriggers$$IsUnitWithVisualId(..., id)`.

**Les 4 divergences, TOUTES des ajouts (0 retrait, 0 changement de valeur) :**

| Ability | Porteur (pool) | Ajoute par la MAJ | Frappe |
|---|---|---|---|
| `ShockAssault` (PASSIF) | `ultraInceptorSgt` | constante `unitId = ultraSmnInceptor` | **DEPLOIEMENT** |
| `ResurrectionOrb` (ACTIVE) | `necroOverlord` | variable `hpPct`, constante `maxSummons = 5` | CAST |
| `FearOfTheUnseen` (ACTIVE) | `tyranDeathleaper` | constante `initialCooldownTurns = 1` | CAST |

Mesure discriminante, meme bloc `Units`, seule la config change :

```
config ShockAssault CAPTUREE  (Constants {})                              -> initAndStart: system error
config ShockAssault RE-SYNTHETISEE ({unitId: "ultraSmnInceptor"})         -> build OK
```

**Le cliquet** : `catalog_inject.refresh_ability_configs(bc)` re-synthetise `BC.Abilities` depuis le
gameconfig VIVANT, et `rl_collect_batch._load_seed_bc` l'appelle a **chaque** chargement — donc pour
tout `rl_duel build`, injecte ou non. Ce n'est pas un hack : `BC.Abilities` est construit par le jeu
depuis SON gameconfig a chaque bataille ; `synthesize_ability` en est le mirror, prouve par
`catalog_inject.py --validate`. **Le refresh est un no-op mesure sur 273 des 277 entrees** : il ne
reecrit pas le catalogue, il le RATTRAPE. Il ajoute en outre les configs des abilities qu'une MAJ
donne a une unite deja au catalogue (cause symetrique — ici `MyWillBeDoneOverlord`).

## 3. Cause B — `TILE_LEAVES` decale de +1 : le composite Tile(7) sommait les MAUVAISES feuilles

Independant du seed BC, et **plus grave** : `#252 fe5b9245` a re-derive `UtilityType` sur le nouveau
build (`AttackTile` **INSERE** en 8, 59 membres decales de +1). `TILE_LEAF_IDS` est une liste de
MEMBRES ; `TILE_LEAVES` etait un dict de **litteraux ANCIENS**. L'appariement a saute pour **26 des
29 entrees** (`#158` avait note « value-preserving, IntEnum -> cles TILE_LEAVES[i] inchangees » —
hypothese devenue fausse).

Consequence, silencieuse : `TILE_UTILITY` sommait `TileEffectsUtility` la ou l'ordre runtime
demandait `Elevation`, et **6 feuilles disparaissaient du composite** (26 enfants attendus, 20
obtenus) — dont `SteppableUnitUtility` et `AttractToDecoysUtility`, les deux que #241 venait de
poser, et `DespoiledGroundUtility`.

**Le cliquet** : les cles de `TILE_LEAVES` sont desormais des MEMBRES `UtilityType`, et une
assertion au chargement du module refuse toute entree dont la cle ne vaut pas `UtilityType.<name>`.
Un balayage des autres tables du package `engine/utilities` rend **0** table restante mal keyee.
Les tests qui designaient une feuille par son litteral (`_leaf(19)`, `TILE_LEAVES[28]`) passent par
le membre.

## 4. Cause C — « un seul build sous `data/symbols/` »

On conserve l'ancien build **expres** (son diff est le rapport de changement du jeu), mais deux
lecteurs exigeaient encore un repertoire unique et mouraient a la migration :
`tests/engine/test_218_amulet_custom_utility_vtable.py::_classes_tsv` et
`probe_212_bc_key_literals.py::resolve_build`. Tous deux passent maintenant par
`symbols_layout.current_build()` (`data/symbols/CURRENT`) — meme correction que
`catalog_inject._build_hash`.

## 5. Ce que la correction debloque, mesure

| Test | Avant | Apres |
|---|---|---|
| `runner/test_targeting_masks_live.py` | 1 passed, **12 errors** | **13 passed** |
| `runner/test_ability_target_gate_lot181_live.py` | **26 errors** | **26 passed** |
| `runner/test_ability_target_gate_live.py` | **13 errors** | **13 passed** |
| `test_steppable_decoy_tile_leaves_live.py` | 13 passed, **5 failed** | **14 passed** |
| `test_tile_leaf_unit_traits_live.py` | 3 passed, **1 failed** | **4 passed** |
| `test_218_amulet_custom_utility_vtable.py` | 1 passed, **1 failed** | **2 passed** |

## 5bis. Ce que le deblocage a REVELE : un attendu perime, merge a l'aveugle

`test_ability_target_gate_lot181_live.py` etait injouable (26 ERROR) — son roster porte
`ultraInceptorSgt`. Pendant ce temps **#245 a porte `TargetIsHealable`** (bit 8, predicat
`attack_query.entity_can_be_healed`, slot 0x11 d'`IAttackQuery`) **sans pouvoir faire tourner le
test qui garde cette ability**. Le parametrage y encodait encore « regle NON portee -> port == 0 » :

```
HEALABLE_1002 : natif 0x100 TargetIsHealable | port 0x100 | attendu du test 0x0
```

Port et natif sont d'accord ; c'est l'attendu qui etait perime. Corrige au rebase (5e champ
`TR.TargetIsHealable`). **Lecon** : un harnais bloque ne rougit pas, il DISPARAIT — et une PR qui
change le comportement garde par un test eteint le fait sans contradicteur. Le sens PERMISSIF du
contrat reste garde par les deux tests de balayage, qui ne dependent d'aucune ligne du parametrage.

## 6. Le montage de `DeathOnTheWind` (1213) : les MUNITIONS, sinon le masque n'est jamais confronte

Une fois le build debloque, 1213 rendait `0x1 ValidRequest` pour TOUTE cible.
`AttackQuery$$GetInvalidTargetReason` sort EN AMONT du filtre de cible quand l'ability n'est pas
disponible ; `DeathOnTheWind` porte `munitionsCost = 1` et le seed BC capture pose
`MachineOfWarAmmo = 0` sur les trois joueurs. Mesure (`probe_254_mow_ammo.py`, montage `masks_da`,
6 endturns) :

```
ammo 0 -> 1213 : 0x1 sur les 10 cibles                        (masque jamais confronte)
ammo 5 -> 1213 : 0x80000 TargetTileHasEnemyUnit sur les 5 ALLIES
                 0x2     TargetMatchesDynamicRule  sur les 5 ENNEMIS
```

Le fixture pose donc `MachineOfWarAmmo = 5` — extension de HARNAIS (parametre de bataille, comme
`probe_123_hailstrike_phase2.py`), pas une mecanique. Le `0x80000` du volet #249, ajoute sans
confrontation live, est **desormais reproduit a l'identique par le port** ; le `0x2` reste le trou
DECLARE (regle dynamique non portee, permissive).

## 7. Ce qui n'est PAS couvert

- **`necroOverlord` porte encore l'ANCIEN passif.** Son entree `Units` capturee a
  `PassiveAbilities [1045]` la ou le gameconfig vivant dit `MyWillBeDoneOverlord` (1556), et ses
  `Traits` n'ont pas `Resilient`. Le refresh ne touche QUE `BC.Abilities` : rafraichir le bloc
  `Units` toucherait aussi des champs d'ETAT JOUEUR (progression, relique) que la synthese ne
  connait pas. La voie propre est un **re-dump du seed BC** (`python dump_boards.py`), a arbitrer —
  il change le pool et les stats de reference de tous les tests.
- ~~**`test_tau_targeting_live.py` : 2 rouges PRE-EXISTANTES**~~ et
  ~~**`test_charge_tile_utility_live.py::test_forward_spotter_spawn_tile_follows_tile_utility`**~~ :
  **LES TROIS SONT FERMEES (2026-07-29)** — `case-254bis-trois-rouges-de-montage.md`. Le verdict
  « defaut de MONTAGE » etait juste pour les trois, mais **le diagnostic etait faux sur deux** :
  * `test_1082_inspired_to_greatness` : la cible alliee hors contact ETAIT bien la (d=2, accord
    parfait avec le natif). Ce qui manquait, c'est le faux-accept du contrefactuel — depuis que
    #247 porte la regle dynamique de 1082, un allie hors contact a PLEINS PV est refuse DEUX fois
    (portee **et** regle dynamique), donc neutraliser la portee ne revele plus rien. Corrige en
    amenant cet allie au regime BLESSE ;
  * `test_dynamic_rules_bite_and_flip` : l'ennemi n'infligeait pas « aucun degat », **il n'attaquait
    pas du tout** — `applyAction{"kind":"attack"}` n'existe pas (`unknown kind`, `mutated:false`),
    et le retour n'etait pas lu ;
  * `test_forward_spotter_...` : meme famille que la cause B ci-dessus (§3) — le littéral
    `step == 10` = `StepType.AddUnit` vaut **9** sur `rnca9r7q6c`, le membre `RestoreArmorInfo` (7)
    ayant ete RETIRE de l'enum. Le test lit desormais le TAG `Unit_IsSummoned`, pas l'ordinal.
- **Les autres sections du seed BC** (`Utilities`, `Effect`, boards) n'ont pas ete confrontees au
  gameconfig vivant : seul le catalogue d'abilities l'est.
