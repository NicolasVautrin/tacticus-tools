# case-366-r1 — `1215 PsychicStalk_ExtraAttackDamage` : un canal DÉFENSEUR qui AJOUTE du dégât

**Question, binaire.** Le port ajoute-t-il au dégât reçu par un ennemi d'Ahriman exactement ce que
le natif ajoute, et se tait-il exactement quand le natif se tait ?

**Réponse : OUI**, sur deux couples (board, seed), dans quatre régimes, bit-exact. Porteur
`thousAhriman`, HERO **au pool** (`rl_duel build --list-pool`) ; voie directe, ni greffe npc, ni
injection catalogue, ni relique.

## 1. Le canal — la colonne de l'inventaire nomme la MÉTHODE, pas l'OPÉRATION

`IdunBattle.Entities.Effects.Loki.PsychicStalk_ExtraAttackDamageEffect$$CreateEffectDamageMalusForDefense` :

    EffectBonus.ForPercentIncrease(
          ( IsUnit(Caster@0x48) | IsMachine(Caster@0x48) | CasterIsCasterTile )
        & AreEnemies(Target@0x60, Owner@0x30)
        & GetTargetIsOnFireTileCondition()
        & GetAttackHasValidDamageProfileCondition(),
          ConfigVar(0xa = extraDmgPct, GetAbilityState(effet), config@+0x60) )

Le §3.3 du gisement annonçait `CreateEffectDamageMalusForDefense`, et c'est **exact** — mais c'est
le nom du **slot d'interface** (le canal DÉFENSEUR), pas l'opération. La fabrique est
`ForPercentIncrease`, donc le dégât **reçu AUGMENTE** : « Malus…ForDefense » = malus *pour* le
défenseur, pas réduction *du* défenseur.

**Conséquence directe : le foyer `flat_reductions` de `1110` (PR #408) n'est PAS le bon slot.**
`1110 FireAndReposition_ReduceDmg` appelle `ForSubtraction` → `flat_reductions` (additif défenseur
pré-perçage) ; `1215` appelle `ForPercentIncrease` → **`pct_list` défenseur**. Ce sont deux entrées
différentes de `IdunBattle.Core.Services.DamageModifiers$$Add`, et le port les distingue déjà
(`services/damage_modifiers.py::add_modifier`). Rien à recréer, mais rien à réutiliser non plus.

Slots lus (carte `IdunBattleLogic.Entities.DSLFactory$$InitializeShared`, cf.
`entities/selectors/accessors.py`) : `DSLSelectors+0x30 = Owner` (`factory+0x148`), `+0x48 = Caster`
(`+0x160`), `+0x60 = Target` (`+0x178`), `+0x78 = TargetTiles` (`+0x190`).

### L'effet vit sur AHRIMAN → canal AURA state-wide, pas le canal défenseur ordinaire

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PsychicStalk_ExtraAttackDamageAbility$$CreateBehaviour` :

    AddEffect(0x4bf = 1215, <AbilityStateReference>, targets = Owner@0x30)
  + AddEffect(0x4c0 = 1216, …)  + AddEffect(0x59b = 1435, …)

Les **trois** effets du kit sont posés sur le PORTEUR. Le natif les attrape par l'énumération
**GLOBALE** de `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`
(elle itère la liste des effets ACTIFS de l'état — un `List<KVP<entité, List<effet>>>` passé en 5ᵉ
argument — et appelle le slot `0x1a` sur chacun), pas seulement les effets de la cible. Côté port,
c'est **`create_aura_defense_damage_malus_for_ally`** (agrégateur `aura_defense_damage_malus_from_units`,
le mirror de cette boucle, cf. `case-68`), et **non** `create_effect_damage_malus_for_defense`.

⚠ **Aucun `CreateTargetSelector` sur cette classe** — contrairement à `DaughterOfTheAbyss` ou au
voisin `1216`, qui en ont un. Tout le ciblage vit dans le TRIGGER. C'est le premier consommateur de
ce canal dans ce cas de figure ; l'agrégateur le sert sans modification.

## 2. Les deux conditions PARTAGÉES vivent sur la base `APsychicStalkEffect`

`1215` et `1435` dérivent tous deux d'`IdunBattle.Entities.Effects.Loki.APsychicStalkEffect`, qui
porte les deux nœuds qu'ils intersectent chacun dans son canal. Le port mirror cette hiérarchie.

**`APsychicStalkEffect$$GetTargetIsOnFireTileCondition`** :

    AmountIsEqualOrGreater( EntitiesWithAnyEffect( Tiles(Target@0x60), Fire = 5, effectTarget = 6 ),
                            <DSLFormulas+0x20 = Direct(1)> )

Trois lectures qui ne se devinent pas :
* le `6` n'est **pas** un second EffectType — la surcharge à 4 arguments
  (`IdunBattleLogic.Entities.DSLSelectors$$EntitiesWithAnyEffect`, tranchée par l'ADRESSE du `call`,
  pas par le nom) emballe elle-même le scalaire `5` dans un `int[1]` et passe `6` comme
  `effectTarget` — c'est le défaut que la surcharge à 3 arguments écrit en dur ;
* `Tiles` = `IdunBattle.Entities.Selectors.UnitsMainTilesSelector` → la **MAIN TILE** de la cible,
  pas son empreinte ;
* `DSLFormulas+0x20 = Direct(1)` (`DSLFormulas$$.ctor` alloue `+0x18 = Direct(0)`, `+0x20 = Direct(1)`,
  `+0x28 = Direct(2)`, `+0x30 = Direct(100)`, `+0x38 = Direct(-1)`), et la surcharge d'arrivée est
  celle qui prend un SÉLECTEUR (`AmountIsGreaterAbilityTrigger(selector, minAmount)`), résolue par
  l'adresse du tail-call.

**`APsychicStalkEffect$$GetAttackHasValidDamageProfileCondition`** :

    DamageProfileIs([ AbilityConfiguration.GetAffectedDamageProfile()  ?? 3   (Flame),
                      AbilityConfiguration.GetAffectedDamageProfile2() ?? 0xd (Psychic) ])

Les deux valeurs sont lues **sur la config** (`effet+0x60`) via `GetValueOrDefault(<défaut>)`. Pour
`PsychicStalk` la config fournit les deux (`affectedDamageProfile = "Flame"`,
`affectedDamageProfile_2 = "Psychic"`) : elles coïncident avec les défauts, mais le port lit la
CONFIG, pas les défauts.

## 3. Ce que le trigger ne gate PAS : l'ATTAQUANT — et c'est ça qui rend le cas mesurable

`AreEnemies` porte sur `Target` vs `Owner`, jamais sur le caster. **N'importe qui** bénéficie du
+X %, y compris un ennemi d'Ahriman qui tire sur un autre ennemi d'Ahriman. Le seul terme sur le
caster est le OU `IsUnit | IsMachine | CasterIsCasterTile`, vrai pour tout attaquant réel. Conforme
à l'i2, qui ne nomme aucun sujet : « **Attacks** that deal Flame Damage and Psychic Damage to
enemies that are on hexes with Fire deal +33% Damage. »

C'est exactement ce qui SÉPARE `1215` de son voisin
`IdunBattle.Entities.Effects.Loki.PsychicStalk_FriendlyChaosExtraDamageEffect$$CreateEffectDamageBonusForAttack` :

    ForAddition( AreFriends(Owner@0x30, Caster@0x48) & HasTrait(Caster@0x48, 0x7ea = Chaos)
               & GetTargetIsOnFireTileCondition() & GetAttackHasValidDamageProfileCondition(),
                 ConfigVar(8 = extraDmg) )

Un attaquant **allié mais NON-Chaos** fait taire `1435` et laisse `1215` seul. Le montage prend donc
`astraPrimarisPsy` (Imperial, arme PSYCHIC r2, 1 coup) — et le bras `--attacker ahriman` sert
d'**anti-témoin** (§6).

Le troisième effet du kit, `1216 PsychicStalk_VisualEffect`, n'a **aucun canal de dégât** :
`CreateActiveCondition = op_LogicalNot(IsDead(Owner@0x30))`,
`CreateTargetSelector = Units(EntitiesWithAnyEffect(Tiles(Enemies(Owner)), Fire, 6))`. Il ne pollue
rien — vérifié, il est bien présent au déploiement (E1), donc son absence de contribution est
MESURÉE, pas supposée.

## 4. La magnitude est indexée par le niveau du PASSIF — tranché LIVE, pas au décompilé

`ConfigVar(0xa)` = `AbilityVariableType 10 = extraDmgPct` (ancrage indépendant :
`runner/abilities/sisterhood.py` lit le même index sur `BrazierOfHolyFire`). Courbe : L1..L8 = 25,
L20 = 29, L30 = 31, L40..L65 = **33**. **HORS `variablesAffectedByRarityBonus`** ⇒ le multiplier de
rareté (180 %) ne le touche pas. i2 : « +33% Damage » = `extraDmgPct[L65]`.

Le niveau vient de `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState`, donc de
l'`AbilityOrEffect` baké au ctor. **Ce baking n'est PAS attribuable statiquement** :
`PsychicStalk_ExtraAttackDamageEffect..ctor` **n'existe pas** dans `frida/methods.tsv` — le corps est
mutualisé avec `APsychicStalkEffect$$.ctor`, qui prend son `AbilityOrEffect` **en paramètre** (c'est
la fabrique d'`EffectsDatabase` qui le passe). Les deux lambdas nommées qui appellent ce corps
(`EffectsDatabase.<>c$$<InitializeEffects>b__14_203` / `b__14_204`) bakent `0x485 = 1157` et
`0x4c3 = 1219` via la surcharge d'`op_Implicit` qui écrit `set_TriggeredAbility` — **ni l'une ni
l'autre n'est `TriggeredAbilityType.PsychicStalk = 1179`** ; elles construisent d'autres effets qui
partagent ce corps trivial. Conclure de leur contenu aurait été l'erreur exacte que décrit
`reference_ctor_name_is_not_class_identity`.

**C'est la mesure qui tranche.** `--unit-stat "thousAhriman:PassiveAbilityLevel=1"` dissocie le
passif (25 %) de l'actif (33 %), que `buildNormalizedBC` égalise à 50 :

| C4_09 / 4242, passif L1 / actif L50 | valeur |
|---|---|
| natif (live) | **[3029]** |
| port (lit `ability_level` = passif → 25 %) | **[3029]** |
| contrefactuel : port forcé au niveau ACTIF (33 %) | **[3684]** |

Le régime discrimine (3029 ≠ 3684) **et** c'est le PASSIF qui est lu. Sans le contrefactuel de
niveau, l'accord n'aurait rien prouvé.

## 5. Mesures live — 2 boards, 2 seeds, 4 régimes, toutes bit-exactes

Montage : `probe_366_r1_psychic_stalk.py` (`thousAhriman` + `astraPrimarisPsy` vs `necroWarden`,
pilotage des deux camps, pose du feu par le natif, captures, rejeux offline sur le MÊME flux MT).
`--crit 0,0 --crit-target 0,0 --block-target 0,0 --block-player 0,0` et
`--unit-stat "<allié|cible>:PassiveAbilities=[]"` : une seule variable bouge.

| | `MC1_67` / 31337 (L50) | `C4_09` / 4242 (passif L1) |
|---|---|---|
| E1 — `1215`/`1216`/`1435` posés sur Ahriman | oui / oui / oui | oui / oui / oui |
| E2 SANS FEU — **live** / **port** | `[2984]` / `[2984]` | `[3382]` / `[3382]` |
| E3 — feu posé par le natif, cible dessus | `(6,8)` oui | `(5,9)` oui |
| E4 AVEC FEU — **live** / **port** | `[3993]` / `[3993]` | `[3029]` / `[3029]` |
| CONTRE-ÉPREUVE (sans `1215`, même flux) | `[3348]` | `[2773]` |
| CONTREFACTUEL de TUILE (feu éteint) | `[3348]` | `[2773]` |
| CONTREFACTUEL de NIVEAU (forcé à l'ACTIF) | `[3993]` (L50 == L50) | `[3684]` |
| ÉTAGE `def_mods.pct_list` — avec / sans | `[1.33]` / `[]` | `[1.25]` / `[]` |
| `extraDmgPct` lu | 33 | 25 |

**La POSE du feu est ce qui rend le cas jouable** : `PsychicStalk_ApplyFireTileAbility`
(`CreateTrigger = OnNormalAttackOrSmite(1) & OwnerIsCaster & IsRangedAttack`,
`CreateBehaviour = AddEffect(Fire = 5, targets = TargetTiles@0x78)`) allume l'hex de la cible quand
Ahriman tire. Le montage l'exploite : au tour 1 personne n'a tiré (gate FERMÉ, bras E2), au tour 2
Ahriman re-pose le feu sous la position COURANTE de la cible juste avant le coup mesuré.

**`tiles=` de `load_state` est indispensable** : sans le seed des effets de tuile (#102) l'état
offline repartirait d'un plateau vierge et le gate serait faux **pour une raison de harnais**.

### Pourquoi 3993 ≠ 1.33 × 3348 — la décomposition par étage

Le %-list ne multiplie pas le dégât tiré : il s'applique aux **BORNES** de la plage
(`damage_ops/normal.py::_reduced_bounds` → `apply_all_modifiers(…, def_mods, round_materialize=True)`
sur `lo` et `hi`), et le tirage se fait ENSUITE dedans (`next_internal(lo, hi+1)`). Deux plages
différentes, un même état MT ⇒ deux valeurs qui ne sont pas dans le rapport des multiplicateurs.
C'est pour ça que le probe expose l'étage `def_mods` LUI-MÊME : `pct_list = [1.33]` (resp. `[1.25]`),
`additive = 0`, `flat_reductions = []`. Un scalaire final n'aurait dit que « la somme colle » ; cet
étage dit « le canal a écrit dans LE bon slot ».

### Un second canal de dégât sort dans la même réponse — il est ATTRIBUÉ, pas mélangé

La réponse de l'action porte aussi `Amount = 106400` avec `Effect_Type = 5` : c'est le **DoT de
l'hex en feu**, pas le coup. `live_amounts` sépare les deux listes (`hits` vs `other`) ; les
mélanger aurait comparé une somme à un coup.

## 6. Mutations adversariales — les gardes sont ROUGES quand on les casse

| mutation | ce qui rougit |
|---|---|
| **M1** inscription `EFFECT_CLASSES` retirée | `1215 est route sur BaseEffect` + `retirer 1215 ne change RIEN au degat` |
| **M2** `ForPercentIncrease` → `for_subtraction` | `le canal a ecrit dans flat_reductions/additive` (étage) + les deux bras de dégât |
| **M3** gate `TargetIsOnFireTile` neutralisé | `le gate ... ne ferme pas sur une tuile SANS feu` + le bras E2 (`live != port`) |
| **M4** gate `DamageProfileIs` neutralisé | `laisse passer un profil Physical` |
| **M5** niveau lu = `active_ability_level` | bras `--passive-level 1` : port `[3684]` vs natif `[3029]` |

**L'ANTI-TÉMOIN est la mutation qu'on ne contrôle pas — c'est le NATIF qui la joue.** Bras
`--attacker ahriman` (Chaos, allié de lui-même ⇒ `1435` tire AUSSI), `MC1_67` / 31337 :

| | SANS FEU | AVEC FEU |
|---|---|---|
| live | `[2984]` | **`[4253]`** |
| port | `[2984]` | **`[3589]`** |
| sans `1215` | — | `[2582]` |

Écart **664** = `round(extraDmg[L50] × 1.8 × 1.33)` = `round(499 × 1.33)` : l'additif ATTAQUANT de
`1435` (`ConfigVar(8 = extraDmg)` = 499 pré-perçage) scalé par le %-list DÉFENSEUR de `1215`. Le bras
SANS FEU, lui, **concorde** — les deux effets partagent `GetTargetIsOnFireTileCondition`.

Cet écart prouve trois choses d'un coup : (a) l'accord du bras nominal n'est pas fortuit ; (b) le
gate `HasTrait(Caster, Chaos)` de `1435` est réel (muet avec l'Imperial, actif avec Ahriman) ;
(c) `1435` est un résidu VIVANT et CHIFFRÉ, pas un effet inerte.

## 7. Ce qui n'est PAS couvert

* **`1435 PsychicStalk_FriendlyChaosExtraDamage` n'est PAS porté** — hors périmètre (une ability par
  tâche). Résidu NOMMÉ et CHIFFRÉ : `ForAddition(AreFriends(Owner, Caster) & HasTrait(Caster, Chaos)
  & <les 2 conditions partagées>, ConfigVar(8 = extraDmg))`, canal ATTAQUANT
  (`create_aura_attack_damage_bonus_for_ally`, comme `BeaconOfRage_FriendlyExtraDamage`).
  La base `APsychicStalkEffect` est déjà en place ; il ne resterait que la classe + son inscription.
* **`1216 PsychicStalk_VisualEffect` n'est PAS porté** — aucun canal de dégât (vérifié au décompilé),
  et sa présence au déploiement est mesurée par E1.
* **`PsychicStalk_ApplyFireTile` (la pose du feu) n'est pas portée** : le runner offline ne sait pas
  allumer l'hex lui-même, il le reçoit par le seed `snapshot._load_tile_effects`. Suffisant pour tout
  ce qui est mesuré ici ; résidu NOMMÉ (une TRIGGERED de plus au registre des triggers).
* **`IsMachine(Caster)` et `CasterIsCasterTile` n'ont pas de substrat propre** : côté port les MoW
  portent aussi un `UnitComponent` (`snapshot._load_machines`), donc `att_is_unit` couvre les deux
  premiers termes du OU ; le troisième (un attaquant qui EST une entité-tuile) n'a aucun canal
  offline. Dégradation RESTRICTIVE et nommée : les trois clés absentes ⇒ gate fermé.
* **La face DÉCISION n'est pas confrontée séparément.** Le câblage y est posé
  (`playbook/prediction/_shared.py` : mêmes clés `att_id` / `att_is_unit` / `tile_effects_by_pos`,
  même sémantique que le COMBAT — pas de fork), mais il n'est **exercé** que par la voie COMBAT.
* **Aucune mesure de l'EXPIRATION du feu** ni du comportement quand la cible QUITTE l'hex en feu
  entre deux coups (le montage re-pose le feu avant chaque mesure).
* **Un seul profil de dégât exercé LIVE (Psychic).** La branche `Flame` de
  `GetAttackHasValidDamageProfileCondition` n'est confrontée qu'offline (vue d'effet + config).

## 8. Artefacts

| quoi | où |
|---|---|
| base native partagée | `scripts/python/engine/entities/effects/loki/extra_damage_aura.py` (`APsychicStalkEffect`) |
| classe d'effet | idem (`PsychicStalkExtraAttackDamageEffect`) |
| registre | `scripts/python/engine/entities/effects/factory.py` + `effects/loki/__init__.py` |
| fil COMBAT | `scripts/python/engine/runner/damage_model.py` (`defender_modifiers` : `att_is_unit`, `tile_effects_by_pos`) |
| fil DÉCISION | `scripts/python/engine/playbook/prediction/_shared.py` (mêmes clés) |
| contrat du hook | `scripts/python/engine/entities/effects/base.py`, `effects/__init__.py` |
| montage live | `scripts/python/probe_366_r1_psychic_stalk.py` |
| gardes | `scripts/python/tests/engine/runner/test_psychic_stalk_extra_attack_damage_live.py` (6) |
