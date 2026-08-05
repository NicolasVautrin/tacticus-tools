# #429-r1-r1 — L'attaque NORMALE frappait les cadavres, et le bon étage n'était pas celui du message

**Livré le 2026-08-05.** Build de référence : `rnca9r7q6c`.

`#429-r1` a porté le gate `IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility`
sur la seule voie d'ABILITY, et a nommé le résidu : l'attaque NORMALE n'était gatée **nulle part**.
Elle a aussi nommé ce qu'il fallait établir **avant** de porter — *les attaques déclenchées
empruntent-elles ce visiteur ?* — parce qu'un gate posé au mauvais étage se paie sur des chemins
qu'on n'a pas mesurés.

## 1. La question préalable, et sa réponse mesurée

`probe_429r1r1_normal_attack_dead_target.py --volet portes --check` balaie `engine/**` en AST :

| | mesure |
|---|---|
| modules d'`engine/**` qui **construisent** un `AttackUnitMessage` | **0** |
| appels de `AttackDamageOperation.execute` | **11**, sur **10** fichiers |

Les deux ensembles sont **DISJOINTS**. `DamageHandler.visit_AttackUnitMessage` n'est atteint que
depuis le **harnais** (tests, probes, pilotage RL) : les attaques déclenchées — overwatch
(`effect_triggers.py`), riposte (`draw_fire`, `primarch_first_legion`, `control_edict`), drone
commandé (`mv71`), summon (`summon_ai`, `summon`), feuille DSL `UseActiveAbility` (`combat.py`) —
appellent l'**opération** directement.

⇒ **Un gate posé au rang du MESSAGE n'aurait ni gaté ni sur-refusé ces chemins. Il aurait fermé
UNE porte sur 10.**

**Contre-épreuve intégrée** (`--check`) : le scan doit retrouver les sites **connus** — le visiteur,
un trigger d'effet, une feuille DSL. Sans elle, un « 0 constructeur » ne vaudrait rien : c'est
exactement le reproche que `#429-r1` fait à `search_code`.

## 2. Côté natif il n'y a qu'UN site, et les déclenchées y passent aussi

```
IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviour$$Execute
    -> IOperationProcessor.ActiveAbility(caster, target, abilityType, options)   # 5 args
Core.Services.OperationProcessor$$ActiveAbility
    -> IdunBattle.Operations.ActiveAbilityOperation$$Execute        # SEUL appelant CODE, hors la
                                                                   # re-entree ExecuteForReplacedTarget
    -> $$ExecuteInternal  -> IsDeadUnitAndNotAllowedByAbility(...)  # PREMIER gate
```

`UseActiveAbility` est la feuille par laquelle passent **toutes** les attaques normales déclenchées
(`Overwatch_AutoAttackEffect$$GetAttackBehaviour = UseActiveAbility(NormalAttack)`). Le natif les
gate donc **exactement comme un cast commandé** — il ne fait aucune distinction, parce qu'il n'a
qu'un seul site.

Le gate ne lit **aucun flag d'`AbilityOptions`** (décompilé relu) :

```
IsDeadUnitAndNotAllowedByAbility(this, abilityType, target):
    ability = AbilitiesDatabase.Get(abilityType)
    if (!EntityExtensions.IsUnit(target))            return false
    if (UnitExtensions.IsAlive(target, this@+0x18))  return false
    return slot_0x11(ability) ^ 1                    // !CanContinueOnDeadTarget()
```

C'est la différence avec l'axe **CASTER**, où `UseActiveAbilityBehaviour$$Execute` force le littéral
`1` dans `options@+0x4a` (le seul octet en dur d'une struct autrement recopiée champ par champ) et
autorise un caster mort — d'où `allow_dead_caster` côté port. **Sur l'axe CIBLE, aucune dérogation
n'existe**, donc aucun paramètre.

**`AttackUnitMessage` n'existe pas en natif** (`search_symbols_by_name` : 0 symbole) : c'est une
simplification du port, et c'est la raison de fond pour laquelle son visiteur ne pouvait pas être
le bon étage.

## 3. Aucune attaque normale n'échappe au gate

`CanContinueOnDeadTarget` n'a qu'**une** implémentation (`AActiveAbility`), qui lit le bit 38
`AllowDeadTarget` du masque de **CONTINUE**. Un **seul** site du binaire pose ce bit —
`IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$GetTargetingOptionsForContinue`
(scan d'instructions `probe_429r1_bit_readers_scan.py`, §1 de `case-429r1`). Les trois
implémentations de `GetTargetingOptionsForContinue` sont la base, `EntropyCannonsAbility` et
`GreatFrostAxeAbility` : **aucune `*NormalAttackAbility`**.

⇒ `ability_class=None` au call-site du port n'est pas un défaut de confort : c'est le comportement
natif de **toute** attaque normale.

## 4. Le port, à l'étage OPÉRATION — et re-posé au visiteur pour une raison nommée

Le gate est câblé en **trois** points, un par PORTE du port (le natif n'en a qu'une) :

| point | ce qu'il couvre |
|---|---|
| `AbilityHandler.visit_ActiveAbilityMessage` | cast commandé (#429-r1) |
| `AttackDamageOperation.execute` (tête) | **le foyer** — les 11 call-sites, dont les 10 déclenchés |
| `DamageHandler.visit_AttackUnitMessage` (tête) | attaque normale commandée, **avant** le dispatch `NormalAttackType` concret |

La troisième pose n'est pas décorative : le dispatch `MV71SniperDroneSquad` **SPAWNE un drone**
avant d'attaquer. Côté natif ce dispatch est le corps de l'ability 1076, donc **en aval** du gate
d'`ExecuteInternal` — sans cette pose, un cast sur un cadavre spawnerait le drone puis
n'attaquerait pas, là où le natif ne fait **rien**. Même dédoublement, et pour la même raison, que
le gate acteur-mort (#70 au rang du message, #133 au rang de l'opération).

## 5. Le chiffrage

Montage **écrit** (positions forcées, board `MC1_67`, seed 777, `--hp-target 1`) : `spaceWulfen`
(3,3), `ultraInceptorSgt` (1,3), `tyranWingedPrime` (2,3), **plus un second ennemi loin** — sans
lui, tuer l'unique adversaire termine la bataille et le cadavre disparaît des vues. `spaceWulfen`
tue, puis `ultraInceptorSgt` porte son **attaque normale** (`kind == "normal"`, id **69**
`Loki_NormalAttack`) sur le cadavre, depuis une tuile adjacente.

| | tirages RNG | dégâts | action |
|---|---|---|---|
| NATIF | **0** | 0 | **non consommée** (`hasAction` reste vrai) |
| PORT pré-fix, voie MESSAGE | **6** | **6049 sur un cadavre** | consommée (`ability_used_flag`, `turn_finished`) |
| PORT pré-fix, voie OPÉRATION nue | — | **6049** | — |
| PORT post-fix, les deux voies | **0** | 0 | aucune |
| contre-épreuve **cible VIVANTE** | 3 | 10192 | — |

**Portes gatées : 0 / 11 avant, 11 / 11 après.** La ligne « opération nue » est ce qui sépare les
deux étages : elle mesure ce qu'un gate posé au rang du message aurait laissé ouvert.

### Généralisation

* **Seed** `31337`, même board → identique (natif 0 / pré-fix 6 tirages, 5998 dégâts / post-fix 0 ;
  vivante 3 tirages, 10104).
* **Board** `MC1_75` → identique (natif 0 / pré-fix 6 tirages, 8864 / post-fix 0 ; vivante 3
  tirages, 13326). **Deux** boards confrontés.
* Boards **NON INSTALLÉS**, et le probe le dit (`why` non vide → `pytest.fail`, jamais un vert) :
  `MC1_74` (la cible survit à 1 PV), `MC1_63` (5x7, placement (6,6) hors board), `MC1_70` et
  `MC2_75` (placement non honoré par le natif — tuile interdite/réservée).

### Ce que le live ne peut PAS discriminer, et il faut le dire

`IsDeadUnitAndNotAllowedByAbility` et `IsInvalidTarget` sortent tous deux avant `On(0x2a)`, avant
tout dégât et avant les flags de tour : leur observable depuis le runner est **identique**. Le live
établit « le natif no-oppe » ; que ce soit *ce* gate-là est établi au décompilé.

## 6. La garde

`tests/engine/runner/test_429r1r1_normal_attack_dead_target_live.py` — **7 tests, ~39 s**. Chaque
assertion « refus » a sa contre-épreuve :

* la morsure (gate débranché → 6 tirages, 6049 dégâts, flags posés) ;
* la porte déclenchée (opération nue, même traitement) ;
* **le gate ne refuse pas TOUT** : cible VIVANTE, même porteur, même attaque → 3 tirages, 10192
  dégâts. Sans cette ligne, un gate qui refuserait toute attaque passerait tout le reste ;
* **la question préalable est GARDÉE** (`test_les_deux_ensembles_de_portes_restent_disjoints`) : le
  jour où un module d'`engine/**` construira un `AttackUnitMessage`, l'étage choisi devra être
  re-justifié — le test force cette re-lecture, contre-épreuve du scan comprise.

Non régressé (re-joué) : `test_429r1_dead_target_gate_live` (6), `test_overwatch_live` (1),
`test_runner_attack_live` (2), `test_damage_roll_live` (2), `test_martial_superiority_live` (4),
`test_mv71_sniper_drone_live` (5), `test_control_edict_live` (4), `test_finaljustice_live` (1),
`test_harlequins_panoply_live` (10), `test_437_overwatch_consumes_armour_live` (4),
`test_summon_trait_effects_live` (8).

## 7. Résidus nommés

* **`#429-r1-r1-r1` — l'attaque d'ABILITY déclenchée n'est gatée que par le visiteur.** Symétrique
  exact de cette tranche sur l'autre famille : `AttackDamageOperation.execute_ability_attack` a
  **~9 call-sites hors** `visit_ActiveAbilityMessage` (`splash`, `genestealer`, `destroyer_hive`,
  `hailstrike`, `haze_of_corruption`, `summon_ai`, trois dans `behaviours/combat.py`). **Ils ne se
  valent pas, et c'est tout l'enjeu** : un nœud DSL `AttackDamage` **interne** à une behaviour déjà
  gatée en amont ne doit **pas** l'être une seconde fois (y poser un gate serait un fork — c'est le
  cas du splash, dont les cibles secondaires sont sélectionnées *dans* l'arbre), tandis qu'un
  trigger qui relance un `UseActiveAbility(<ability>)` traverse un **nouveau** `ExecuteInternal` et
  l'est. Le tri se fait **par site, au décompilé** : lire si le natif passe par
  `UseActiveAbilityBehaviour$$Execute` / `OperationProcessor$$ActiveAbility` (→ gaté) ou par un
  nœud `DSLBehaviors$$Attack` interne (→ non gaté). Non fait ici : hors périmètre, et un gate posé
  en bloc sur ce foyer sur-refuserait à coup sûr.
* **`#429-r1-r3`** (ouvert par la tranche parente, **inchangé**) : `GreatFrostAxe` (1089) échappe
  correctement au gate cible-morte, puis le natif le refuse par le gate **suivant** que le port ne
  reproduit pas.

## 8. Trouvé en chemin

**`observeBattle` ne publie plus le cadavre.** `cible_ob_dead` est `None` sur les trois montages
installés, alors que `decisionView` rend bien `alive=False, hp=0` et que le port voit l'entité avec
sa position. Le montage ne s'appuie donc **que** sur le `decisionView` pour établir la mort (c'est
ce que garde `test_le_montage_pose_bien_un_cadavre_visible_et_positionne`). Noté, non investigué :
le préalable est vérifié par une source qui répond.

## 9. Re-dériver

```
python scripts/python/probe_429r1r1_normal_attack_dead_target.py --volet portes --check
python scripts/python/probe_429r1r1_normal_attack_dead_target.py --volet gate
python scripts/python/probe_429r1r1_normal_attack_dead_target.py --volet live --state-file <ABSOLU>
python scripts/python/probe_429r1r1_normal_attack_dead_target.py --volet live --seed 31337 --state-file <ABSOLU>
python scripts/python/probe_429r1r1_normal_attack_dead_target.py --volet live --board MC1_75 --state-file <ABSOLU>
python -m pytest tests/engine/runner/test_429r1r1_normal_attack_dead_target_live.py -q
```

⚠ Les chiffres de cette fiche se **re-dérivent** : `11 call-sites` bouge à chaque porte ajoutée.
