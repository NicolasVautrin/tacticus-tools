# #999-r3-r1 — le contrat de RARETÉ des canaux de dégât : quatre canaux, un port, et le blocage qui restait

**Verdict** : le contrat est **POSÉ et CONFRONTÉ LIVE en régime SÉPARANT**. Il débloque **UN** effet
sur les six annoncés — `1448 HyperCorrosiveAcid_ExtraDamagePct`, porté et inscrit. Les cinq autres
butent sur un **second blocage, mesuré** : leur porteur est une MACHINE OF WAR, et l'univers de
porteurs des deux agrégateurs d'aura l'exclut (`#999-r3-r1-r1`).

Deux énoncés du résidu se sont révélés **faux à la relecture du décompilé**, et c'est ce qui a
changé la forme du livrable.

---

## 1. Le résidu nommait DEUX agrégateurs — il en fallait QUATRE

`#999-r3-r1` désignait `aura_attack_damage_bonus_from_allies` et
`aura_defense_damage_malus_from_units`. Re-mesure : **deux de ses six effets n'exposent AUCUN
`$$CreateTargetSelector`**.

| effet | symboles rendus par `search_symbols_by_name` | ⇒ canal PORT |
|---|---|---|
| `1448 ...HyperCorrosiveAcid_ExtraDamagePctEffect` | `$$.ctor`, `$$CreateEffectDamageBonusForAttack` | `create_effect_damage_malus_for_defense` (self) |
| `1446 ...ElectrochaffBackups_DamageReductionPctEffect` | `$$.ctor`, `$$CreateDamageModifier` | `create_effect_damage_bonus_for_attack` (self) |

Pas de `CreateTargetSelector` ⇒ l'`Owner` de l'effet **est son porteur** ⇒ le natif l'évalue dans la
boucle des effets de l'entité, pas dans la boucle `effet × cibles`. Les inscrire au canal AURA les
aurait rendus **matérialisés et inertes**, sans erreur.

Le contrat porte donc sur **quatre** canaux :

| canal PORT | clé | bénéficiaire | consommateur |
|---|---|---|---|
| `create_aura_attack_damage_bonus_for_ally` | `att_rarity` | l'ATTAQUANT | `1442 BlightedLand` |
| `create_aura_defense_damage_malus_for_ally` | `tgt_rarity` | la CIBLE | `1443 ContemptuousDisregard` |
| `create_effect_damage_malus_for_defense` | `rarity` (le CASTER) | — | `1448 HyperCorrosiveAcid` |
| `create_effect_damage_bonus_for_attack` | `tgt_rarity` | — | `1446 ElectrochaffBackups` — **NON POSÉE**, cf. §5 |

**Pourquoi la clé d'un canal AURA porte sur le BÉNÉFICIAIRE et non sur le porteur** :
`CalculateDefenderModifiersForPrediction` / `...AttackerModifiers...` écrivent
`AbilityEntities+0x18 (Owner) <- CHAQUE CIBLE du sélecteur` avant d'évaluer le trigger. Un étage
`UnitsWithRarity(…, Mythic)` du `$$CreateTargetSelector` se lit donc sur l'attaquant (trigger
`get_OwnerIsCaster`) ou sur la cible (`get_OwnerIsTarget`).

**Foyers de lecture**, tri-état strict (`None` = NON MESURÉ ⇒ le gate se FERME ; jamais
`Rarity.Common` en repli, qui serait PERMISSIF) :
`runner/damage_model.py::_unit_rarity` et `playbook/prediction/_shared.py::_entity_rarity`, tous
deux sur le `UnitContext.rarity` de #999-r3 — le même que la clé `rarity` du dict d'unité DSL.

**Une clé de plus, du même geste** : la MAIN TILE de l'**ATTAQUANT** entre dans
`tile_effects_by_pos` du canal aura ATTAQUE. `1442` ferme son sélecteur par
`UnitsOnTilesWithEffect(…, Contaminated)`, qui lit la tuile de l'ÉLÉMENT du sélecteur — pas celle de
la cible, seule que le ctx portait. La face PRÉDICTION n'a rien eu à ajouter :
`scene.tile_effects_by_pos` porte déjà tout le plateau (le COMBAT était le plus étroit des deux).

---

## 2. `1448 HyperCorrosiveAcid_ExtraDamagePct` — porté

```
...HyperCorrosiveAcid_ExtraDamagePctEffect$$CreateEffectDamageBonusForAttack =
    EffectBonus.ForPercentIncrease(
        get_OwnerIsTarget
        & ( AreFriends( Caster@<DSLSelectors+0x48>,
                        EffectSource(Effect@<DSLSelectors+0x38>), 0, false )
            & HasRarity( Caster@<DSLSelectors+0x48>, idun.meta.Rarity.Mythic = 5 )
            & HasTrait(  Caster@<DSLSelectors+0x48>, 0x10 = UnitTrait.Hero ) ),
        DSLFormulas$$ConfigVar( 0xa = extraDmgPct, GetAbilityState(effet), effet@+0x60 ) )
```

L'effet vit sur l'**ENNEMI** blessé par une Spore Mine (`AddEffect(0x5a8, source = Owner,
targets = Target)`, pose portée par #1035) et **majore le dégât qu'il reçoit** — mold
`ExemplarOfHate_Target` / `Chronometron`. Gameconfig : `extraDmgPct = [10, 13, 16, 20]`,
`variablesAffectedByRarityBonus = ['extraDmgPct']`.

⚠ **Face native = ATTAQUANT** (`CreateEffectDamageBonusForAttack`, slot 0x16) malgré le trigger
`get_OwnerIsTarget` ⇒ `DEFENSE_MALUS_NATIVE_FACE = "attacker"`. Canal POURCENT, donc l'attribution
coûte un `Fix64.Round` (`probe_437r1r1r1` : 100 classes, **0 divergence**, 4 non résolus inchangés).

⚠ `EffectType 1448` ≠ `TriggeredAbilityType 1448` (`HuntersInstincts`, qui porte AUSSI une magnitude
de dégât — la confusion ne lèverait pas). `ActiveAbilityType` n'a aucun membre 1448.

---

## 3. La confrontation — LIVE, en régime SÉPARANT

`probe_999r3r1_ctx_rarete_live.py` (board `MC1_67`, seed 777). Le bras de reconnaissance est le bras
**DÉGÉNÉRÉ** de #999-r3 (il doit NE PAS séparer, le probe le refuse sinon) ; il sert à choisir un
**HÉROS** du roster, pour que les deux attaquants comparés portent tous deux `UnitTrait.Hero` et
soient tous deux alliés de la source de l'effet — **seule la rareté change**.

Bras séparant `admecDominus -> Rarity.Epic` : capteur `[3, 5]` sur 10/10 lignes, port `[3, 5]`.

| attaquant | `att_rarity` | `rarity` | `tgt_rarity` | gate 1448 |
|---|---|---|---|---|
| 83 `admecDominus` (Epic, Hero) | 3 | 3 | 5 | **None** |
| 77 `eldarMauganRa` (Mythic, Hero) | 5 | 5 | 5 | **`PercentIncrease 10`** |

Même cible (87), même source d'effet (77), même trait `Hero`. Le palier `10` est celui de
l'`AbilityState` **TERTIAIRE** niveau 1.

**Contre-épreuve adversariale : 10 mutations du code de PRODUCTION, 10 rouges** — les trois clés de
ctx (combat), la clé de la face PRÉDICTION, le tri-état du foyer rabattu sur `Rarity.Common`, la
tuile de l'attaquant retirée, les trois conjoints de 1448, et l'admission des MoW comme porteurs.

⚠ **La 10ᵉ a d'abord été VERTE, et la cause vaut d'être écrite** : le probe **recopiait** la boucle
de collecte des porteurs au lieu de l'**intercepter**. Il mesurait donc son propre artefact, et une
réparation du vrai foyer le laissait vert. Il passe désormais par un espion posé sur l'attribut de
`damage_model` (forme B de morsure), et le montage porte un **témoin** (un porteur retenu) sans quoi
« la MoW n'est pas porteuse » serait vrai par construction.

---

## 4. `#999-r3-r1-r1` — le blocage qui restait, et il n'a rien à voir avec la rareté

`probe_999r3r1_porteurs_aura_mow.py`. Une MoW porteuse de l'aura 1442, dans un état offline :

| fait mesuré | valeur |
|---|---|
| MoW matérialisée comme entité | oui |
| MoW SANS `PositionComponent` | oui (`snapshot._load_machines` : hors-plateau, le natif non plus) |
| rareté de la MoW MESURÉE | `Rarity.Mythic` |
| aura 1442 active dans `state.effects` | oui |
| retenue comme porteur — aura ATTAQUE / DÉFENSE | **non / non** (témoins : les deux agrégateurs TOURNENT) |
| face PRÉDICTION — MoW dans `EffectsState.by_unit` | **non** |
| face PRÉDICTION — MoW dans `pos_by_id` | **non** (témoin #360 : `team_by_id` la porte, lui) |

Cause : les deux collectes exigent un `PositionComponent`
(`_apply_ally_attack_damage_auras`, `defender_modifiers`). Le natif, lui, itère une
`List<KeyValuePair<entité, List<effet>>>` de l'ÉTAT, **board-wide, sans lire aucune position** — le
filtre est un **artefact du port**. Côté PRÉDICTION le blocage est double :
`playbook/scene.py::step_context` seede son `EffectsState` depuis `dv["units"]` **seulement**.

⚠ **Ne réparer qu'une face serait un FORK prediction/combat**, le vice que #197 et #950-r2 ont déjà
payé. C'est pourquoi la réparation n'est pas faite ici : elle touche `scene.py`, foyer partagé, et
mérite sa propre tranche avec sa mesure de rayon de souffle.

Ce que ça débloque : les **six `PARTIEL`** de `kit-coverage.md` — `1442 BlightedLand`,
`1443 ContemptuousDisregard`, `1445 WisdomOfTheAncients`, `1449 MoreGitzOverEre`,
`1494 CabalOfSorcerers`, `1548 GuardianConstruct`.

---

## 5. Ce qui n'est PAS couvert

- **La MAGNITUDE de 1448 confrontée au natif.** Le gate est confronté live ; le *nombre* ne l'est
  pas. Montage requis, écrit ici et non joué : `rl_duel build --equip-mythic
  tyranBiovore:HyperCorrosiveAcid:<n> --board MC1_67`, amener une **Spore Mine**
  (`tyranSmnSporeMine`) amie à blesser un ennemi (vecteur `On(0x0f = DamageTaken)`), puis
  `aiPredict` avec un attaquant **Mythic + Hero** allié du Biovore, contre un contre-bras à rareté
  abaissée. ⚠ **Un A/B par REJEU de combat ne séparerait rien** : le tirage consomme le RNG
  différemment selon les modificateurs (mesuré #1038 : balayage 0→20 non monotone).
- **`1446 ElectrochaffBackups`** : son canal est `create_effect_damage_bonus_for_attack`, dont
  l'`att_ctx` se construit sur **~10 sites** (`damage_model.attacker_modifiers` ;
  `playbook/prediction/normal_attack.py` ×4 ; `prediction/abilities.py` ;
  `playbook/{avalanche_of_muscle,fury_of_the_ancients,heavy_bolt_pistol,light_im_up,psyker,shrapnel}.py`).
  Poser `tgt_rarity` sur un seul d'entre eux créerait un fork silencieux. Résidu : `#1025-r1`.
- **Les faces DÉCISION** (`CabalOfSorcerersPlaybook` `#1036-r3`, `WisdomOfTheAncientsPlaybook`
  `#433-r4-r3-r1-r1`) : le canal les rend évaluables, elles ne sont pas portées ici.
- **L'audit ne bouge pas, et c'est normal** : `kit-coverage.md` comptait déjà `HyperCorrosiveAcid`
  parmi les **35 portées** (par sa face TRIGGER, #1035). Son axe `PARTIEL` ne recense que les
  owner-effects — il est **structurellement aveugle** à un effet posé sur autrui dont seule la face
  dégât manquait. Les six `PARTIEL` restent six.
