# #10006 — le foyer `engine/entities/effects/factory.py` : dix résidus, et deux `porteur` qui ne tenaient pas

Tranche du 2026-08-15, build `t6dpr4k06g`. Les dix résidus qui nomment ce foyer dans leur champ
`FOYER:` — le plus gros foyer libre du dépôt au moment du dispatch.

## Le tableau

| résidu | prémisse re-mesurée | verdict | `BLOCAGE` avant → après |
|---|---|---|---|
| `#419-r1-tr9-r4-r1-r2-r1c-r1` | **CONFIRMÉE** | **PORTÉ + validé** — ligne fermée | `aucun` → *(fermé)* |
| `#1078-r3` | **PÉRIMÉE** — déjà livré | **RIEN À FAIRE** — ligne fermée | `aucun` → *(fermé)* |
| `#952-r2` | **RÉFUTÉE ×2** | **volet flag LIVRÉ** | **`porteur` → `aucun`** |
| `#894-r2` | partiellement réfutée | non résolu, blocage re-qualifié | **`porteur` → `seeding`** |
| `#963-r3` | CONFIRMÉE | non résolu (outillage) | `aucun` → `aucun` |
| `#922-r1` | CONFIRMÉE (volet b) | non résolu (outillage) | `aucun` → `aucun` |
| `#924-r1` | CONFIRMÉE + fait neuf | non résolu (outillage) | `aucun` → `aucun` |
| `#999-r1` | CONFIRMÉE | non résolu (outillage) | `aucun` → `aucun` |
| `#1020-r5` | CONFIRMÉE | non résolu | `etage` → `etage` |
| `#965-r2` | CONFIRMÉE | non résolu | `etage` → `etage` |

Six prémisses sur dix tiennent, deux sont fausses, une est périmée, une est à moitié fausse. Le
taux annoncé (« fausses environ une fois sur deux ») ne s'est **pas** vérifié sur ce foyer : la
majorité des fiches était exacte. Re-mesurer reste ce qui l'**établit**.

## Ce qui a été mesuré, et comment

### `#952-r2` — deux prémisses fausses, dont un recensement de call-sites

1. « aucune unité confrontable ». **Faux** : `admecManipulus` est dans `rl_duel build --list-pool`
   (rank 17). Confronté live avec **témoin** — sans lui, un flag universel se lirait comme une
   confirmation :

   ```
   admecManipulus  unitFlags=[24]  abilityStates=[(1117 DefendTheDivineWork, active),
                                                  (1119 Repair_GalvanicField, granted)]
   tauCrisis       unitFlags=[]                     <- TÉMOIN
   ```

   `28 Repair` est bien absente du porteur : les trois feuilles du `CreateBehaviour` natif sont
   confirmées. L'ordinal `24` est **lu** dans `unitFlagTypes` du snapshot, jamais écrit en dur.

2. « les **deux** seuls call-sites de `_seed_ability_owner_effects` ». Il y en a **trois** — le
   troisième est `runner/snapshot.py`, la voie CAPTURE, qui boucle sur chaque entité chargée. C'est
   ce comptage qui portait tout le verdict « port spéculatif ET non validable ».

**Livré** : `ABILITY_INIT_OWNER_FLAGS["GalvanicField"] = [CanRepairFullHealthUnits]` — même flag et
même **lecteur** que son jumeau `EcogSupport`, donc pas un mensonge de couverture. **Reste ouvert** :
les deux échanges d'ability (`RemoveActiveAbility` / `AddActiveAbility`) n'ont aucun canal d'init.

La garde vise le **régime séparant** : sur le chemin live l'entrée est un no-op exact (le capteur
publie déjà le flag), donc un test qui chargerait un état capté serait un accord en régime dégénéré.

### `#894-r2` — le porteur se monte ; c'est son **empreinte** qui manque

`SolarAtomizer` n'a qu'**un** porteur, `admecBossBelisarius` (npc `Boss`). Sa carte dédiée est
`GB_Belisarius_01` (lue dans `gameconfig.battles.campaigns.Event[*].battles[32].BoardId`) et le
fichier **existe** (`data/boards/global/GB_Belisarius_01.json`). Le montage spawne bien l'unité avec
`SolarAtomizer(1174) [prêt]`.

Mais le cast reste refusé, et la raison est **lue** :

```
abilityReason -> casterReason = targetReason =
    {ruleClass: GenericBrokenTargetingRule, hex: 0x1000000000, reasons: ["CasterHas3Tiles"]}
```

C'est le **caster** qui casse la règle. Déplacer les unités n'y change rien (essai fait avec
`--place` / `--a-place`). **Cause mesurée** : l'unité réellement instanciée n'est pas
`admecBossBelisarius` mais `GuildBoss10Boss1AdmecBelisarius` (HP300, `moveNone`), **absente du
gameconfig** — `--explicit-stats` substitue une variante guild-boss sans l'empreinte 3 tuiles.

⇒ Ce qui bloque est le **seeding** du porteur, pas son existence. La piste est la voie BC de
campagne event, pas la recherche d'un autre porteur ni d'un autre board.

### `#1078-r3` — périmée : tout était déjà là

`HunterOfSouls_ExtraDamage` (1495) est **présent** dans `EFFECT_CLASSES`, avec sa classe
(`effects/loki/hunter_of_souls.py`), le substrat COMBAT
(`components.hunter_of_souls_adjacent_psyker_friends_count` → `damage_model`), le substrat DÉCISION
(`scene.hunter_of_souls_adjacent_psyker_friends` → `normal_attack` + `abilities`) et son test
(7 verts). **Piège de mesure re-payé par la fiche elle-même** : interroger ce registre par
l'ORDINAL rend un faux négatif — c'est le **nom** qui répond.

### `#924-r1` — fait neuf sur le porteur

Mesuré incidemment sur un runner de cette tranche : **`tauCrisis` porte `EarlyWarningOverride` en
`kind: active`** (`abilityStates` = `[{id: 1077, name: EarlyWarningOverride, kind: active,
level: 50, multiplier: 180}]`). Le montage annoncé comme « DISTINCT » est en réalité immédiat —
pool, une commande, ni injection ni greffe.

## Le port de `1394 LegendaryCommander_ExtraDamage`

Arbre lu terme à terme sur `t6dpr4k06g` —
`IdunBattle.Entities.Effects.Loki.LegendaryCommander_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` :

```
EffectBonus.ForAddition(
    get_OwnerIsTarget & AreFriends(Caster@<DSLSelectors+0x48>, EffectSource(<+0x38>), 0, false),
    ConfigVar(AbilityVariableType 8 = extraDmg, GetAbilityState(this), <config@+0x60>) )
```

Le sélecteur est le **tronc** de la base `ALegendaryCommander_BaseEffect$$CreateTargetSelector`
(trois nœuds), **sans** le quatrième `Filter(., IsAdjacent(Owner, Subject, 3))` que seule la
surcharge de 1395 porte.

**Quatre absences vérifiées**, chacune recopiable d'un voisin de forme : aucun `HasTrait(Hero)`
(l'i2 « friendly **Characters** » sur-spécifie), aucun gate de nature d'attaque, aucun `HasRarity`,
aucune `CreateTargetSelector` propre.

**Canal** : `create_aura_defense_damage_malus_for_ally` + `AURA_DEFENSE_MALUS_NATIVE_FACE =
"attacker"` — même arbitrage que `MoreGitzOverEre` / `OnMyPosition` : slot natif ATTAQUANT,
bénéficiaire du sélecteur = la CIBLE du coup. **Ce n'est donc pas le canal de son jumeau 1395**
(axe COUPS) : un artefact, deux axes, deux canaux.

**Substrat** : aucune clé neuve. `tgt_adjacent_unit_profiles` existait ; `used_active_by_id` est la
clé, le store et le foyer que `build_hits_board` pose déjà pour 1395 — relayée au ctx du canal
aura-défense sur les **deux** faces dans le même commit.

### Validation adversariale — 8 mutations, 8 qui mordent

| mutation | verdict |
|---|---|
| recopier le 4ᵉ nœud `IsAdjacent` de 1395 | MORD |
| recopier le gate `!IsNormalAttack` de 1395 | MORD |
| poser le gate `HasTrait(Hero)` suggéré par l'i2 | MORD |
| rendre le gate d'équipe permissif sur une valeur non mesurée | MORD |
| rabattre le tri-état non mesuré sur PERMISSIF | MORD |
| retirer la clé de contexte côté COMBAT seulement | MORD |
| retirer la clé de contexte côté PRÉDICTION seulement | MORD |
| désinscrire 1394 du registre | MORD |

⚠ Une **neuvième** mutation — rabattre `None` sur un ensemble **vide** — **NE MORD PAS**, et c'est
un **résultat**, pas un trou : sur ce sélecteur, une boucle vide ferme déjà le gate et `{}.get(uid)`
rend `None`. Les deux écritures calculent la même chose. Le fait est écrit dans le module, pour que
personne ne relise ce garde en croyant qu'il produit la dégradation restrictive.

## Ce qui n'est PAS couvert

- **Quatre résidus non résolus pour une raison d'OUTILLAGE, pas de fond** : `#963-r3`, `#922-r1`,
  `#924-r1`, `#999-r1`. **ghidra-mcp est resté injoignable (port 13337 refusé) de bout en bout de la
  tranche**, et chacun exige une relecture du décompilé (cinq artefacts pour Lifewards ; les
  `<X>_InitAbility$$CreateBehaviour` des trois owner-effects de #922 ; `GetOverwatchExtraDamage`
  pour 1145 ; les deux arbres de la pose de `MastersOfManoeuvre`). Aucun n'a été porté « depuis la
  fiche » : ce serait un port sans sa vérité.
- **`#1020-r5` et `#965-r2`** : blocages `etage` **confirmés**, aucun n'a bougé d'un cran.
- **`#952-r2`** : seules deux des trois feuilles restent — les échanges d'ability n'ont pas de canal.
- **`#894-r2`** : le seeding de l'empreinte 3 tuiles n'est pas réparé.
- **`1394` n'est pas confronté LIVE.** Le port est validé offline (24 assertions, 8 mutations) et
  son substrat est câblé des deux côtés, mais aucun bras live n'a mesuré l'écart de dégât sur
  `custoTrajann` — il faudrait un allié castant une active adjacent à un ennemi, puis un second
  allié qui l'attaque.
