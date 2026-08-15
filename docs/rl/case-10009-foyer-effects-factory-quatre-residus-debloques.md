# #10009 — le foyer `effects/factory.py`, deuxième passe : ce que ghidra a débloqué, et deux façons de conclure faux d'un bloc `methodPointers`

Tranche du 2026-08-15, build `t6dpr4k06g`. Les quatre résidus que #10006 avait préparés sans
pouvoir les résoudre — ghidra-mcp était injoignable de bout en bout. Il est debout, la table est
complète (154 183 symboles, dont les 4 874 `__Il2CppFullySharedGeneric`).

| résidu | prémisse re-mesurée | verdict | `BLOCAGE` |
|---|---|---|---|
| `#963-r3` | **CONFIRMÉE** | **PORTÉ + gardé** | `aucun` → *(fermé)* |
| `#999-r1` | **CONFIRMÉE** (11 nœuds sur 12) | **PORTÉ + gardé** | `aucun` → *(fermé)* |
| `#922-r1` volet b | **RÉFUTÉE sur l'ARTEFACT** | **volet b LIVRÉ** | `aucun` → `aucun` |
| `#924-r1` | **CONFIRMÉE**, mais 3 VA fausses | RE livré, **non porté** | `aucun` → `aucun` |

Trois prémisses sur quatre tiennent ; la quatrième est vraie sur le fond et fausse sur le nom de
l'artefact. **Aucune des quatre n'était vérifiable sans le décompilé** — c'est bien l'outillage qui
bloquait, pas le fond.

## 1. Deux façons de conclure faux d'un bloc `methodPointers`, et elles sont inverses

Le bloc est l'outil que le dépôt utilise quand `frida/methods.tsv` déduplique. Cette tranche en
donne les **deux** modes de défaillance, dans le même lot.

**(a) Il fait rater un override — `LifewardsBondEffect`.** Son bloc porte exactement DEUX entrées
(`.ctor`, `CreateActiveCondition`). Conclure de lui aurait posé
`BOND_REMOVAL_GATES[1060] = (False, None, False)` : **aucun retrait de bond**, et le lien aurait
survécu à la mort de Celestine, en silence. La mesure
`probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared` — voie `class_get_methods`, qui lit la
**MÉTADATA** et non les corps — rend l'inverse :

```
LifewardsBondEffect | get_Range=none | get_Adjacent=false | get_RemoveOnBondedEntityDeath=TRUE
TRIGGERS DE RETRAIT CONSTRUITS : a
```

Un virtuel à corps trivial est ICF-dédupliqué : **absent du bloc des CORPS, présent dans la
métadata**. Le bloc énumère des corps, pas des déclarations.

**(b) Ses adresses périment à 100 %, et la structure survit — `#924-r1`.** La fiche citait
`18326d838..d850` pour 1145 ; décodé sur `t6dpr4k06g`, ce bloc porte des corps `18103d*` sans
rapport. Le vrai bloc, retrouvé par `list_xrefs` sur les méthodes nommées puis borné par lecture
des pointeurs voisins, porte QUATRE entrées dont le corps partagé de `GetOverwatchExtraDamage` en
3ᵉ position, et bascule ensuite sur `EarlyWarningOverride_VisualEffect$$.ctor`. **La prémisse
tient.** Les quatre VA du tableau d'`inescapable_death.py` étaient périmées de la même façon
(lues sur `rnca9r7q6c`) : **churn de 100 % sur les adresses, structure identique**.

⇒ Elles sont remplacées par une écriture **par SLOT**, qui survit au changement de build et se
re-vérifie en un `list_xrefs` sur `<Classe>$$.ctor` suivi d'un `read_bytes` de N pointeurs.

## 2. Trois énoncés écrits qui étaient faux — dont un qui a survécu à sa propre correction

- `reactivate_overwatch.py` portait encore, **mot pour mot**, « 1145 n'override PAS
  `GetOverwatchExtraDamage` », alors qu'`inescapable_death.py` §5 annonce depuis #924 avoir corrigé
  cette phrase « dans le même commit ». La correction avait été faite à un endroit, pas à l'autre.
- La docstring de `masters_of_manoeuvre.py` déclarait la pose bloquée par `HasRarity`, « canal
  ABSENT du port ». Vrai sur `rnca9r7q6c`, **périmé** : capteur #1039, foyer `UnitContext.rarity`
  (#999-r3), nœud `HasRarity` porté avec son tri-état.
- La fiche `#999-r1` appelait `TERTIARY_ABILITY_POSED_EFFECTS` un « raccourci d'init » avec lequel
  le port devrait se confronter. **Faux** : `snapshot._rebake_tertiary_posed_effects` re-bake le
  couple `(niveau, multiplicateur)` d'instances **déjà captées** et ne pose rien. Les deux canaux
  sont disjoints par leur entrée — live, le natif pose et le re-bake corrige ; offline, personne ne
  posait.

## 3. Le 2ᵉ argument natif que le port n'exprimait pas

`AddEffectBehaviour..ctor(effectType, **abilityState**, source, targets, turns)`. Le port ne
l'exprimait que par le dérivé `scale_from_source`, qui lit `_source_scaling` — le couple des
**PASSIFS** de la source. Exact tant que l'ability qui pose est un passif ou une active. **Faux
quand elle est TERTIAIRE** : `UnitFactory$$Build` fabrique un troisième `AbilityState`
(`config+0xc0 TertiaryAbilityLevel`, `config+0x78`), soit `level 1..4 / mult 100`, et c'est celui
que `get_AbilityStateReference(this)` rend. Le couple passif d'un runner normalisé vaut `50 / 180`,
et `ToZeroBasedIndex(50)` clampe au dernier palier : sur `dmgReductionPct = [10, 13, 16, 20]`, la
pose aurait donné **20 %** là où le natif donne **10 %** au niveau 1. Même cause que #1005 / #1009.

`AddEffect` reçoit donc `ability_state` (couple déjà résolu, défaut `None` = comportement
strictement inchangé), alimenté par `triggered_ability_state`.

## 4. `#922-r1` — l'artefact nommé par la fiche n'existe pas

Elle exigeait de lire « le `<X>_InitAbility$$CreateBehaviour` de chacune ». Il n'y a **aucune**
classe `IntoxicatingElixir_InitAbility` / `AmuletOfTheVoidwyrm_InitAbility` /
`NetherRealmCasket_InitAbility` dans le build — et ce n'est pas un corps dédupliqué :
`frida/classes.tsv` liste les **classes** indépendamment de leurs corps, et les 23 `_InitAbility`
du build y sont nommés un par un.

Les vrais artefacts sont de **DEUX formes**, ce que la fiche ne disait pas :

- **`AOwnerEffectTriggeredAbility` + `GetEffectType`** (`return 0x5b3` = 1459, `return 0x5b4` =
  1460) pour les deux premières — tout le reste vient de la base, lue verbatim ;
- **un `CreateBehaviour` propre** pour `NetherRealmCasket`, dont la base est `BaseTriggeredAbility`
  et qui pose DEUX effets (`0x5af`, `0x5b0`) sans aucun `If`. Son trigger a dû être résolu slot à
  slot : corps ICF `WayOfTheShortBlade_InitAbility$$CreateTrigger` =
  `OnOwnerSpecificAbilityInit(this.AbilityType)`.

## 5. Validation adversariale — la 1ʳᵉ passe a trouvé un trou dans ma propre garde

**14 mutations, 14 MORD, 0 MUET.** La première passe rendait **13 MORD / 1 MUET** : neutraliser la
prise en compte d'`ability_state` (`if False:`) laissait la garde VERTE. L'étage vérifiait la
**signature** et le **call-site**, jamais l'**effet** — un paramètre déclaré, cité, et ignoré à
l'exécution serait passé. L'étage refait mesure la **valeur réellement posée** sur l'instance.

Les treize autres, toutes mordues : rabattre le 2ᵉ conjoint de Lifewards sur `IsAlive` seul ·
poser le bond sans son `bondedEntity` · retirer le gate `IsAlive` du 2ᵉ `If` · retirer l'adjacence ·
retirer la parenté · déplacer le retrait de 1240 · conclure du bloc `methodPointers` qu'aucun
retrait de bond n'est armé · coder `tilesTraversed` en dur · mettre les deux branches de
`MastersOfManoeuvre` sur le même event · figer `tilesMovedThisTurn` hors de `_LIVE_KEYS` · retirer
l'une ou l'autre des entrées de #922-r1.

## Ce qui n'est PAS couvert

- **`#924-r1` n'est pas porté**, et la dépendance à `#924-r2` est maintenue : la face reproduirait
  le +45 % mesuré. Son montage est désormais **écrit et immédiat** (`tauCrisis`, `kind: active`, au
  pool ; le cast pose 1009/1144/**1145**/1149 sur le caster en `TurnsFromRounds(1)`). ⚠ Piège
  mesuré : les deux sœurs sont des **miroirs croisés** — 1145 override `LegitDeathReasons` et *pas*
  `GetAdditionalExtraDamageTrigger`, `InescapableDeath` l'inverse. Le `<vtable +0x768>` de 1145 est
  celui de la BASE ; recopier le 3ᵉ conjoint d'`InescapableDeath` serait le piège du voisin de
  forme, et le voisin est littéralement la classe sœur.
- **Aucune confrontation LIVE** : les trois ports sont validés offline et par mutation. Pour
  `MastersOfManoeuvre`, le bras live doit passer par `--unit-stat "<vis>:Rarity=4"` — `rl_duel
  build` pose `targetRarity = 5`, donc en runner standard **toute unité est Mythic** et les deux
  `HasRarity(., Mythic)` sont uniformément VRAIS : le régime par défaut est **dégénéré**.
- **`#963-r5`** (ouvert, numéro alloué) : `_materialize_owner_effect` n'écrit pas `bonded`, donc
  toute pose de BOND à l'init est hors d'atteinte. Générique, pas propre à Lifewards.
- **`#922-r1`** reste ouvert sur (a) la décomposition du 3ᵉ étage (`[462, 1600, 988]`) et (c) le
  balayage du rayon de `ChargeRegimeHarness`.
