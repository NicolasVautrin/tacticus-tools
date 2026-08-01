# case-366-r1 — `1435 PsychicStalk_FriendlyChaosExtraDamage` : l'ADDITIF ATTAQUANT qui manquait, et qui était déjà chiffré

**Question, binaire.** Le port ajoute-t-il au dégât des attaques Flame/Psychic des unités **Chaos**
amies d'Ahriman exactement ce que le natif ajoute, et se tait-il exactement quand le natif se tait ?

**Réponse : OUI**, sur deux couples (board, seed), sur les **deux pattes** (le porteur attaque / un
allié Chaos attaque), et l'écart de **664** mesuré par la PR de `1215` est **fermé au bit près**.
Porteur `thousAhriman`, HERO **au pool** ; voie directe, ni greffe npc, ni injection catalogue, ni
relique.

## 1. Le canal — `ForAddition`, et c'est un slot DIFFÉRENT de celui du voisin

`IdunBattle.Entities.Effects.Loki.PsychicStalk_FriendlyChaosExtraDamageEffect$$CreateEffectDamageBonusForAttack`
(mirror 1:1, lu au décompilé) :

    EffectBonus.ForAddition(
          AreFriends(Owner@0x30, Caster@0x48, comparisonType = 0, anyEntity = false)
        & HasTrait(Caster@0x48, 0x7ea = 2026 = Chaos)
        & GetTargetIsOnFireTileCondition()
        & GetAttackHasValidDamageProfileCondition(),
          ConfigVar(8 = extraDmg, GetAbilityState(effet), config@+0x60) )

La colonne d'inventaire annonçait `CreateEffectDamageBonusForAttack` — **exact cette fois**, nom du
slot ET fabrique concordent. Ce n'était pas acquis : sur le voisin `1215`, le slot annoncé
(`CreateEffectDamageMalusForDefense`) cachait un `ForPercentIncrease`. Le nom dit OÙ ça se branche,
la fabrique dit CE que ça fait — les deux se lisent séparément.

**Deux entrées DISTINCTES de `IdunBattle.Core.Services.DamageModifiers$$Add`** : `1435` alimente
l'**additif ATTAQUANT** (`mods.additive`, pré-perçage, par coup) ; `1215` alimente le **%-list
DÉFENSEUR**. Elles se **composent** — l'additif traverse le perçage puis est scalé UNE fois par le
%-list. C'est exactement la forme de l'écart que `1215` avait mesuré sans le fermer :
`664 = round(extraDmg[L50] × 1.8 × 1.33)`.

`comparisonType = 0` sélectionne la branche **CurrentPlayer** de
`IdunBattle.Entities.UnitExtensions$$IsFriend` (pas `OriginalPlayer`) : c'est l'équipe COURANTE.

## 2. L'énumération est STATE-WIDE et n'exclut PAS le porteur — d'où DEUX pattes côté port

Le slot `0x16` est invoqué par
`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` sur la liste
**globale** des entités porteuses d'effets actifs (double boucle `GetEnumerator`/`MoveNext` sur un
`List<KVP<entité, List<effet>>>`, l'entité courante étant écrite dans l'`AbilityEntities` avant
l'appel). Forme symétrique exacte de `CalculateDefenderModifiersForPrediction` (slot `0x1a`, cf.
case-68).

**Aucune exclusion du porteur** : `IdunBattle.Entities.UnitExtensions$$IsFriend` compare deux
`GetCurrentPlayer(...).index` et **n'écarte pas l'égalité** — `IsFriend(x, x)` est VRAI. Ahriman
bénéficie donc de son propre effet quand il attaque. Ce n'est pas une déduction : le bras
`--attacker ahriman` le mesure (§4).

Côté port l'énumération native se scinde en **deux foyers DISJOINTS** — patron déjà employé par
`DestroyTheWitch_ExtraDamage` (dont le sélecteur natif est littéralement
`SurroundingFriends(Owner) + Owner`) :

| patte | hook port | foyer | qui sert |
|---|---|---|---|
| SELF | `create_effect_damage_bonus_for_attack` | `_attacker_effect_bonuses` (effets de l'attaquant) | le porteur attaque |
| AURA | `create_aura_attack_damage_bonus_for_ally` | `aura_attack_damage_bonus_from_allies` (**exclut** `att_id == owner_id`, même équipe seulement) | un allié attaque |

Ni trou, ni double-compte : les deux ensembles sont complémentaires et leur union est exactement
« tous les effets de l'équipe de l'attaquant », c'est-à-dire ce que `AreFriends(Owner, Caster)`
laisse passer.

**⚠ AUCUN `CreateTargetSelector` sur cette classe** (comme `1215`) : tout le ciblage vit dans le
trigger. Une seule méthode propre à la classe dans les tables — `CreateEffectDamageBonusForAttack`.

## 3. Les deux conditions PARTAGÉES, et le gate qui SÉPARE

`GetTargetIsOnFireTileCondition` et `GetAttackHasValidDamageProfileCondition` vivent sur la base
`IdunBattle.Entities.Effects.Loki.APsychicStalkEffect`, déjà portée. `1435` les intersecte comme
`1215` — d'où le bras SANS FEU, où les DEUX se taisent ensemble.

Le gate qui les SÉPARE est `HasTrait(Caster@0x48, 0x7ea = 2026 = Chaos)`. Trait de
**grande-alliance**, absent de `gameconfig.traits`, dérivé du `GrandAllianceId` par
`idun.Idun.Source.Shared.GrandAlliance$$GetTrait` — même convention que le gate Chaos de
`BeaconOfRage_FriendlyExtraDamage` et le gate Imperial de `RitesOfBattle`.

### Ce que le trigger ne gate PAS : la CIBLE

Contrairement à `1215` (`AreEnemies(Target@0x60, Owner@0x30)`), le trigger de `1435` ne porte **rien**
sur la cible du coup — seule sa TUILE est lue. Un tir fratricide sur un allié posté sur un hex en feu
déclencherait donc l'additif. L'i2 (« **Affected** attacks from friendly Chaos units… ») suggère
l'héritage du « to enemies » de la phrase précédente, mais **aucun nœud ne l'implémente**. Le quirk
est porté tel quel — le décompilé fait foi — et il est NON CONFRONTÉ live (§7).

## 4. La magnitude est SCALÉE par la rareté — et le niveau est celui du PASSIF, tranché LIVE

`ConfigVar(8)` = `AbilityVariableType 8 = extraDmg`. **`extraDmg` EST dans
`variablesAffectedByRarityBonus`** (`['maxDmg', 'extraDmg']`) — à la différence de l'`extraDmgPct` de
`1215`, qui n'y est PAS. Courbe : `extraDmg[L1] = 5`, `[L50] = 277`, `[L65] = 364` ; × multiplier
180 % → **9 / 499 / 655**. L'i2 « +364 Damage » est `extraDmg[L65]` **non scalé** (l'i2 affiche la
valeur de config). Un port qui oublierait le multiplier serait faux d'un **facteur 1,8**, pas d'un
epsilon — la mutation M4 le mesure (§6).

Le niveau vient de `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState`, donc de
l'`AbilityOrEffect` baké au ctor — et **ce baking n'est PAS attribuable statiquement**, exactement
comme pour `1215` : `PsychicStalk_FriendlyChaosExtraDamageEffect..ctor` **n'existe pas** dans
`frida/methods.tsv` (corps mutualisé avec `APsychicStalkEffect$$.ctor`, qui prend son
`AbilityOrEffect` **en paramètre**), et les deux lambdas nommées qui appellent ce corps bakent
`0x485 = 1157` et `0x4c3 = 1219` — **ni l'une ni l'autre n'est `TriggeredAbilityType.PsychicStalk =
1179`**. Conclure de leur contenu serait l'erreur que décrit `reference_ctor_name_is_not_class_identity`.

**C'est la mesure qui tranche**, et le régime NOMINAL est DÉGÉNÉRÉ (passif == actif == 50) :
`--unit-stat "thousAhriman:PassiveAbilityLevel=1"` dissocie les deux.

| MC1_67 / 31337, passif L1 / actif L50 | valeur |
|---|---|
| natif (live) | **[3522]** |
| port (lit `ability_level` = passif → `extraDmg` = 9) | **[3522]** |
| contrefactuel : port forcé au niveau ACTIF (499) | **[4134]** |

Le régime discrimine (3522 ≠ 4134) **et** c'est le PASSIF qui est lu. Sans le contrefactuel de
niveau, l'accord n'aurait rien prouvé — le bras nominal, lui, rend la MÊME valeur dans les deux
lectures.

## 5. Mesures live — 2 boards, 2 seeds, 3 attaquants, toutes bit-exactes

Montage : `probe_366_r1_psychic_stalk_chaos.py` (`thousAhriman` + un allié vs `necroWarden`, pilotage
des deux camps, pose du feu par le natif, captures, rejeux offline sur le MÊME flux MT).
`--crit 0,0 --crit-target 0,0 --block-target 0,0 --block-player 0,0` et
`--unit-stat "<allié|cible>:PassiveAbilities=[]"` : une seule variable bouge.

| bras | attaquant | E2 SANS FEU live / port | E4 AVEC FEU live / port | port sans `1435` | `att_mods.additive` |
|---|---|---|---|---|---|
| SELF `MC1_67`/31337 | `thousAhriman` (Chaos) | `[2984]` / `[2984]` | **`[4253]` / `[4253]`** | `[3589]` | 499 |
| SELF `MC1_67`/31337, passif L1 | `thousAhriman` | `[2984]` / `[2984]` | **`[3522]` / `[3522]`** | `[3510]` | 9 |
| ANTI-TÉMOIN `MC1_67`/31337 | `astraPrimarisPsy` (Imperial) | `[2984]` / `[2984]` | **`[3993]` / `[3993]`** | `[3993]` | **0** |
| AURA `MC1_67`/31337 | `thousSorcerer` (Chaos) | `[2225]` / `[2225]` | **`[3565]` / `[3565]`** | `[3753]` | 499 |
| SELF `C4_09`/4242 | `thousAhriman` | `[3671]` / `[3671]` | **`[7915]` / `[7915]`** | `[6921]` | 499 |
| AURA `C4_09`/4242 | `thousSorcerer` | `[2698]` / `[2698]` | **`[4600]` / `[4600]`** | `[3144]` | 499 |

**L'écart de 664 est fermé.** La PR de `1215` mesurait, sur le bras `--attacker ahriman` de
`MC1_67`/31337, live `[4253]` contre port `[3589]` ; `[3589]` est aujourd'hui **exactement** ce que
rend le port quand on lui retire `1435` — l'attribution est donc bit-exacte, pas approchée.

**L'ANTI-TÉMOIN est le bras le plus informatif** : `astraPrimarisPsy` a la MÊME arme (Psychic r2), la
MÊME cible sur le MÊME hex en feu, et est ALLIÉ d'Ahriman ; la seule variable qui bouge est sa
grande-alliance. `additive = 0`, et `port sans 1435 == port avec 1435` **au dernier bit** — le gate
ferme, et le port ne sur-accorde pas.

### La décomposition par ÉTAGE dit dans QUEL slot le canal écrit

`attacker_modifiers().additive = 499` / `pct_list = []` / `flat_reductions = []`. Un scalaire final
n'aurait dit que « la somme colle » ; cet étage dit « `ForAddition` a écrit dans le slot de
`ForAddition` ». La mutation M2 (`for_addition` → `for_percent_increase`) le fait rougir avant même
d'atteindre le dégât.

### Non-monotonie du dégât tiré — ce n'est PAS une anomalie

Bras AURA `MC1_67`/31337 : `sans 1435` = `[3753]` > `avec 1435` = `[3565]`. Les modifiers agissent sur
les **BORNES** de la plage (`damage_ops/normal.py::_reduced_bounds`), et le tirage se fait ENSUITE
dedans (`next_internal(lo, hi+1)`) : à état MT identique, une plage de largeur différente donne un
index différent. Le natif fait exactement pareil, et le port le suit bit-exact. C'est pourquoi les
gardes de discriminance assertent `!=` sur le dégât et `==` sur l'ÉTAGE, jamais un signe.

### Un second canal de dégât sort dans la même réponse — il est ATTRIBUÉ, pas mélangé

La réponse de l'action porte aussi un `Amount` avec `Effect_Type = 5` : c'est le **DoT de l'hex en
feu**, pas le coup. `live_amounts` sépare les deux listes (`hits` vs `other`).

## 6. Mutations adversariales — les gardes sont ROUGES quand on les casse

Chaque mutation a été **vérifiée appliquée** (`git diff --stat` non vide) avant d'être interprétée.

| mutation | ce qui rougit | valeur observée |
|---|---|---|
| **M1** inscription `EFFECT_CLASSES` retirée | `1435 est route sur BaseEffect` | port `[3589]` (= l'état pré-port) |
| **M2** `for_addition` → `for_percent_increase` | `patte SELF = ['PercentIncrease', 499]` + étage `pct_list=[[5.99]]` | port `[27272]` |
| **M3** gate `HasTrait(Caster, Chaos)` neutralisé | `additif ATTAQUANT vaut 499 pour un attaquant NON-Chaos` | bras Imperial : port `[4657]` vs live `[3993]` (**+664**) |
| **M4** `multiplier_pct` retiré (rareté oubliée) | `patte SELF = ['Addition', 277]`, attendu `499` | port `[4352]` |
| **M5** patte AURA supprimée | `patte AURA = None` + bras `chaos-ally` diverge | port `[3753]` vs live `[3565]` |
| **M6** patte SELF supprimée | `patte SELF = None` + bras `ahriman` diverge | port `[3589]` vs live `[4253]` |
| **M7** niveau lu = `active_ability_level` | bras `--passive-level 1` : port `[4134]` vs live `[3522]` | — |

⚠ **M7 ne rougit QUE sur le bras `--passive-level 1`** : le bras nominal passe (passif == actif == 50).
C'est la démonstration en acte que le régime nominal est DÉGÉNÉRÉ et que la dissociation n'est pas
un luxe.

## 7. Ce qui n'est PAS couvert

* **Le quirk « aucun gate sur la CIBLE » n'est pas confronté LIVE.** Le trigger de `1435` ne teste ni
  `AreEnemies` ni rien d'autre sur la cible : un tir fratricide sur un allié posté sur un hex en feu
  bonifierait le coup. Porté fidèlement (décompilé = vérité), mais le montage ne joue pas d'attaque
  alliée. Résidu NOMMÉ (`#366-r1-chaos-friendly-fire`).
* **Un seul profil de dégât exercé LIVE (Psychic).** La branche `Flame` de
  `GetAttackHasValidDamageProfileCondition` n'est confrontée qu'offline (vue d'effet + config) —
  l'arme Flame d'Ahriman est en MÊLÉE, et le feu est posé par son attaque RANGED.
* **Le vecteur ABILITY n'est pas confronté séparément.** Le trigger n'a AUCUN `IsNormalAttack`, donc
  `1435` entre aussi sur une attaque d'ability ; le câblage y est posé (`damage_ops/ability.py`
  threade désormais `damage_profile` pour la famille ATTACK, `normal_like.py` idem), mais il n'est
  **exercé** que par la voie NORMALE. `Doombolt` (l'active d'Ahriman) est un vecteur ability à profil
  Psychic — montage possible, non joué.
* **La face DÉCISION n'est pas confrontée séparément.** Le câblage y est posé aux QUATRE sites qui
  construisent un `att_ctx` attaquant (`prediction/normal_attack.py`, `prediction/abilities.py`,
  `playbook/psyker.py`, `playbook/fury_of_the_ancients.py`) + l'agrégateur aura
  (`prediction/_shared.py`), avec les MÊMES clés que le COMBAT — pas de fork — mais il n'est
  **exercé** que par la voie COMBAT.
* **`PsychicStalk_ApplyFireTile` (la pose du feu) n'est toujours pas portée** : le runner offline ne
  sait pas allumer l'hex lui-même, il le reçoit par le seed `snapshot._load_tile_effects`. Suffisant
  pour tout ce qui est mesuré ici ; résidu déjà nommé au backlog.
* **Aucune mesure de l'EXPIRATION du feu** ni du comportement quand la cible QUITTE l'hex en feu
  entre deux coups (le montage re-pose le feu avant chaque mesure).
* **`comparisonType = 0` (CurrentPlayer) n'est pas discriminé de `1` (OriginalPlayer)** : aucune
  unité mind-controlled dans le montage. Lu au décompilé, non confronté.

## 8. Effet de bord ASSUMÉ, hors périmètre strict

`damage_ops/ability.py` et `damage_ops/normal_like.py` threadent désormais `damage_profile` jusqu'aux
modifiers **ATTAQUANT** (ils ne le passaient qu'au DÉFENSEUR). Cela réveille aussi le gate
`!DamageProfileIs(0xd = Psychic)` de `DefenderOfTheGreaterGood_ExtraDmg` sur ces deux vecteurs, où il
était **aveugle** faute de contexte — correction de fidélité, dans le sens RESTRICTIF. Vérifié :
`test_dotgg_extra_hits_live.py`, `test_psyker_splash_live.py`, `test_doctrina_imperatives_live.py`,
`test_destroy_the_witch_live.py`, `test_lord_of_tempests_ice_live.py`, `test_heavy_weapon_moved_gate_live.py`,
`test_doombolt_live.py`, `test_damage_roll_live.py`, `test_runner_attack_live.py` — tous verts.

La fusion de la tuile de la CIBLE dans `att_ctx["tile_effects_by_pos"]` se fait par **`setdefault`** :
une position déjà remplie par `_positional_att_ctx` (centre + ring-1 de l'attaquant, qui porte EN PLUS
les covers de terrain que `LordOfTempests` compte) n'est **jamais écrasée**.

## 9. Artefacts

| quoi | où |
|---|---|
| classe d'effet | `scripts/python/engine/entities/effects/loki/extra_damage_aura.py` (`PsychicStalkFriendlyChaosExtraDamageEffect`, sous `APsychicStalkEffect`) |
| registre | `scripts/python/engine/entities/effects/factory.py` + `effects/loki/__init__.py` |
| fil COMBAT self | `scripts/python/engine/runner/damage_model.py` (`attacker_modifiers` : `att_grand_alliance`, `damage_profile`, `t_pos`, `tgt_team`, `tile_effects_by_pos`) |
| fil COMBAT aura | idem (`_apply_ally_attack_damage_auras` : `tile_effects_by_pos`) |
| fil COMBAT vecteurs | `runner/operations/damage_ops/ability.py`, `damage_ops/normal_like.py` (`damage_profile`) |
| fil DÉCISION | `playbook/prediction/normal_attack.py`, `prediction/abilities.py`, `playbook/psyker.py`, `playbook/fury_of_the_ancients.py`, `prediction/_shared.py` |
| contrat du hook | `scripts/python/engine/entities/effects/base.py`, `effects/__init__.py` |
| montage live | `scripts/python/probe_366_r1_psychic_stalk_chaos.py` |
| gardes | `scripts/python/tests/engine/runner/test_psychic_stalk_friendly_chaos_live.py` (8) |
