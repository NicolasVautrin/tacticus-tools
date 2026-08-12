# #979 — le recenseur des faces DÉCISION lisait une LISTE BLANCHE, et sur-comptait de 22 %

## 1. Le vice, et pourquoi il s'est rouvert deux fois

`probe_909_decision_actives_kit.py` établissait « la face DÉCISION de cette active de kit est
portée » en testant **trois** appartenances écrites en dur ; `audit_kit_coverage.py` en testait
**quatre**. Deux listes blanches divergentes pour la même question, et les deux incomplètes :

| voie ratée | trouvée par | dégât mesuré |
|---|---|---|
| `playbook.bespoke.BESPOKE_SELFCAST` | #971 | 3 faux GAP (`1175`, `1179`, `1184`) ; `1179` a été **redispatchée** sur cette foi |
| `playbook.prediction.abilities._MAKE_DMG_INPUT_OVERRIDES` | #974 | `1191` déclarée non portée alors qu'elle y vivait déjà ; `1195` idem après #974 |

C'est le vice que le CLAUDE.md nomme deux fois — « un recenseur ne peut pas rendre zéro sur ce
qu'il ne visite pas », « une liste blanche ne peut pas montrer ce qu'elle a oublié ». Il se
rouvrait **à notre propre cadence** : chaque lot de portage qui invente un registre le creuse.

## 2. La parade : PARTITIONNER un périmètre, pas allonger la liste

Foyer unique : `scripts/python/decision_face_voies.py`, lu par **les deux** consommateurs.

* **Périmètre** = `engine/playbook/**` + `engine/entities/abilities/active_ability.py`. Un
  **répertoire**, jamais une liste de modules : une liste ne verrait pas le module NEUF, qui est
  exactement le mode de défaillance qu'on ferme.
* Tout conteneur de niveau module à nom MAJUSCULE y est visité. Il entre dans la partition dès
  qu'**au moins un** de ses éléments résout comme `ActiveAbilityType` (par ordinal ou par nom) —
  seuil le plus bas possible, et le filtre **dit** ce qu'il écarte.
* Chaque entrant est **INSCRIT** (`VOIES`) ou **ÉCARTÉ AVEC SA RAISON** (`ECARTES`). Un conteneur
  neuf sort **MUET** ⇒ `probe_909` étape 6 rend `rc 1`. Patron de l'étape 7 de `probe_313`.

Mesure au premier passage (build `rnca9r7q6c`, `master` = `c7607567`) : 128 fichiers, **156**
conteneurs de niveau module, **14 INSCRITS**, **23 ÉCARTÉS avec raison**, **10** écartés par le
filtre, **0 MUET**.

Les **14 voies** : `PLAYBOOKS`, `REGISTRY`, `_SPECIAL_ABILITY_CLASSES`, `BESPOKE_SELFCAST`,
`_MAKE_DMG_INPUT_OVERRIDES`, `_MAKE_DMG_SELECTOR_ONLY`, `_MAKE_DMG_TARGET_GATE`,
`_MAKE_DMG_EXTRA_EVENTS`, `_PLAYBOOK_PROFILE_OVERRIDE`, `_PREPEND_NORMAL_ATTACK_EVENT`,
`HEAL_PLAYBOOKS`, `NONATTACK_PLAYBOOKS`, `LITERAL_ZERO_THRESHOLD_IDS`, `LITERAL_ZERO_ELSEWHERE`.

**Le critère d'inscription, écrit une fois** : un conteneur est une VOIE si son appartenance
signifie « le port porte, pour cette ability, quelque chose de PROPRE sur la face DÉCISION ». Il
est ÉCARTÉ s'il énonce un **fait natif** (les N classes qui partagent un corps, le tier
`get_Priority`, la forme d'arrondi), une donnée d'un **autre axe**, ou une **négation**
d'inscription.

### Ce que la partition a fait apparaître, et qu'aucune liste n'aurait montré

* **`noncomparable._base.NATIVE_PRIORITY` est un piège d'un autre axe.** Ses 22 clés sont des
  `ActiveAbilityType`, dont **trois** (`1159`, `1200`, `1209`) ne sont portées par rien d'autre.
  L'y compter aurait déclaré portées trois faces qui ne le sont pas : le tier `get_Priority`
  ORDONNE les générateurs, il ne porte aucune utilité.
* **Trois registres `TRIGGERED_*` sont clés par `TriggeredAbilityType`** et « résolvent »
  massivement comme actives par **partage d'ordinaux** — 13/18 pour
  `psyker.TRIGGERED_ATTACK_PLAYBOOKS` (`1204` → `LeadingTheCharge`, `1116` → `RadBombardment`),
  13/27 pour `TRIGGERED_MOVE_PLAYBOOKS`, 2/19 pour `NON_OWNER_MOVE_PLAYBOOKS`. C'est le partage
  que le CLAUDE.md chiffre (233 ordinaux communs, 231 nomment autre chose). Ils sont écartés avec
  cette raison, pas absents — et c'est la démonstration que « un élément qui résout » ne prouve
  rien.
* Les **six registres de FORME** de `active_ability.py` (`_PREDICTION_MINMAX_*`, `_A_VIA_*`) disent
  « lu et CONFORME au générique », donc l'inverse d'un port propre.

## 3. Le TROISIÈME état : CONSTANTE

« Portée / non portée » est un axe **faux** pour une active dont le playbook natif EST le chemin
générique : il n'y a rien à porter, et la compter comme du travail est aussi faux que de rater un
port. Cet état ne se dérive d'aucune table offline — il s'établit en **lisant le corps natif** —
donc il est **DÉCLARÉ avec sa source**, dans le ledger qui existe déjà pour ça
(`coverage_attestations.py`, catégorie `active-decision`, verdict `RIEN_A_PORTER`). Une
attestation PÉRIMÉE remet l'item au compte des manquants : aucun chemin ne fait disparaître du
travail.

**Deux verdicts CONSTANTE de #974/#976 n'étaient écrits que dans un message de commit et un test**
— donc recomptés « à porter » à chaque régénération. Ils sont inscrits au ledger, **relus au
décompilé** avant de l'être :

* `1196 LashOfTorment` — `IdunBattle.AI.Playbook.Loki.LashOfTormentPlaybook$$MakeDamagePredictions`
  fait UN SEUL appel à `ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions`, avec
  `sel = this@+0x18 (dsl) ->+0x90 ->+0x60` = `DSLSelectors.Target`,
  `base = VigilanceEternalAbility$$GetDamage`, `hits = AActiveAbility$$GetHits`,
  `prof = AActiveAbility$$GetDamageProfile`, poids `Nullable` VIDE.
* `1225 StrikeFromTheShadows` — même forme, **mais le sélecteur passe par**
  `IdunBattleLogic.Entities.Abilities.Active.Loki.StrikeFromTheShadowsAbility$$GetTarget`. C'est
  ce détour qui pouvait le faire passer pour un override : le corps ENTIER de `GetTarget` est
  `return *(*(this+0x30)+0x90)+0x60`, c'est-à-dire `DSLSelectors.Target`. Rien de propre.

## 4. La QUATRIÈME forme : portée HORS registre

`1197 ExcruciatingFrequencies` est portée depuis #56-t3b, par un **générateur bespoke appelé en
dur** dans `ComparableAbilityGenerator.generate` (`cands += excruciating_frequencies_candidates(ctx)`) —
son playbook natif cible une **TUILE** (ligne-AoE) et ses evals ont `rankCount = 0`, donc aucun
`plan` ne l'amène. Aucun conteneur de niveau module ne peut l'exprimer : c'est exactement ce que
le verdict `PORTE_HORS_REGISTRE` du ledger existe pour porter, avec son `porteur` **résolvable**
(si le port disparaît, l'attestation périme et l'item redevient du travail).

`static_threshold_gate.NOT_REGISTERED` disait déjà la moitié du fait (son gate vit ailleurs) ;
c'est une **négation** d'inscription, donc écartée — inscrire une négation comme voie compterait
portée toute ability qu'un module refuse d'enregistrer.

## 5. Le compte VRAI

138 actives distinctes d'unités `kind == lineup`. Le compte cité au dispatch (« 32 non portées,
106 portées ») datait d'avant #976/#978/#975 : la **correction de lecture** et l'**avancée des
autres lots** sont deux effets distincts, et les mélanger masquerait le premier.

| base | lecture | portées | constantes | non portées |
|---|---|---|---|---|
| `c7607567` (#978) | 3 registres | 111 | — | **27** |
| `c7607567` (#978) | 14 voies + ledger | **117** | **3** | **18** |
| `f6e2674b` (#975) | 14 voies + ledger | 123 | 3 | 12 |
| `0798b33d` (#977) + les 2 ports de #979 | 14 voies + ledger | **128** | **3** | **7** |

**À périmètre de commit égal, la seule correction de lecture vaut `27 → 21`** — un sur-comptage
de **22 %** — et les trois attestations en retirent trois de plus.

Les items soumis à ce lot passent au recenseur réparé **avant** toute lecture de décompilé :

| id | ability | verdict du recenseur réparé |
|---|---|---|
| `1175` | `BloodChalice` | **DÉJÀ PORTÉE** — `bespoke.BESPOKE_SELFCAST` (`BloodChalicePlaybook`, #82) |
| `1188` | `DevastatingRefrain` | ouverte → **PORTÉE** par cette tranche |
| `1158` | `DutyEternal` | ouverte (résidu `#970-r5`) → **PORTÉE** par cette tranche |
| `1159` | `MacroPlasmaIncinerator` | ouverte (résidu `#970-r4`) |
| `1200` | `SquigLaunchas` | ouverte (résidu `#970-r3`) |
| `1043` | `ThunderousAssault` | retirée du lot en vol (portée par un lot parallèle) |

**`1197 ExcruciatingFrequencies` n'est PAS une face libre** : elle est portée depuis #56-t3b par
son générateur bespoke (cf. §4), et l'ancien recenseur la listait « non portée » — c'est
exactement le faux GAP que cette tranche ferme.

## 6. Ce qui n'est PAS couvert

* La **fidélité** des faces portées n'est pas évaluée — seulement leur EXISTENCE. Le recenseur
  dit qu'une entrée de registre existe, jamais qu'elle est juste.
* Le périmètre ne couvre **que** `engine/playbook/**` et `active_ability.py`. Une voie de face
  DÉCISION qui naîtrait ailleurs (p. ex. sous `engine/ai/`) sortirait invisible ; le cliquet ne
  promet pas l'inverse.
* Les voies **CONDITIONNELLES** (`mythicAbilities`, relique `items[*].abilityId`) restent hors du
  compte, comme avant — une active de relique n'est pas dans `activeAbilities` (cf. `case-323`).
* **Aucune confrontation LIVE** des deux ports : le budget est parti dans le volet 1 et la RE.
  Les deux faces sont validées **offline sur substrat synthétique**, avec géométrie DRIVÉE et
  contre-épreuve jouée (`tests/engine/test_979_ports_decision_offline.py`, 10 tests). Restent à
  mesurer, et le montage est écrit dans le rapport : le tour IA de `adeptExorcist` (1188) et de
  `ultraDreadnought` (1158), tous deux **Machines of War** — donc `build --p-mow`, contexte
  `AICTX.build_machine`, et `initialCooldownTurns = 1` sur 1188 écarte l'ability du PREMIER tour.

## 7. Le portage — les deux faces de cette tranche

### `1188 DevastatingRefrain` (`adeptExorcist`, MoW)

`IdunBattle.AI.Playbook.Loki.DevastatingRefrainPlaybook$$EvaluateNonComparable` :
`util = 1 + |ennemis du caster OCCUPANT une tuile de la forme|`, forme ancrée sur la **tuile
visée**. Base `NonComparablePlaybook`1` LUE dans `frida/classes.tsv` (son `.ctor` nomme
`ComparablePlaybook<...>` — le piège vérifié 5/5 par #976).

La forme est l'artefact **déjà porté** par la face COMBAT (#90-B,
`sisterhood.devastating_refrain_shape`) : appelé, jamais recâblé. Son
`If(IsPositionMachineForCurrentPlayer(2), {3,1,5}, {0,2,4})` exigeait un canal que `NCContext` ne
portait pas — le callable `machine_of_war_position` y entre, **identique** à celui
d'`AiDecisionContext` (cascade à quatre étages, tri-état). Sans lui le prédicat rendait `False`
d'office, donc la **mauvaise** des deux formes sur tout plateau où la MoW du joueur courant est en
`Bottom`.

⚠ `_CtxBoard` de `daemon_prince.py` ne fait **PAS** ce travail : c'est l'adaptateur
`NCContext -> Board` de `spawn_tile_shape` (`tile_at`/`id_at`/`neighbours`/`elevation`), un autre
étage. Les deux ont été confondus au dispatch ; ils sont orthogonaux.

### `1158 DutyEternal` (`ultraDreadnought`, MoW) — ferme `#970-r5`

`util = 1 + Σ_{t ∈ ThreeTileUnitSpawnShape(cible)} Σ_{u ∈ GetSurroundingUnits(t, 2, null, false)}
(10 si GetDistance(u, t) < 2 sinon 1)`.

Trois lectures du 4ᵉ argument, toutes silencieuses si on les rate :

1. **`includeCenter = false`** — l'occupant de `t` n'est **pas** compté, donc la branche `10` ne
   peut valoir que `distance == 1` : c'est le bonus des **adjacentes**, jamais celui d'un occupant.
2. **`friendsOf = null`** — `IsEnemy` n'est **jamais** appelé : le natif compte les ennemis **et**
   les alliés. Le réflexe (filtrer par camp, comme `TitanhammerSquad` et `1188`) sous-compterait.
3. **`OrderedSet` par appel** — une unité voisine de deux pieds compte **deux fois**, une par
   itération de la boucle externe.

Le `BLOCAGE: etage` de sa fiche (`ThreeTileUnitSpawnShape` sans adaptateur `board`) est levé par
`CtxBoard`, arrivé avec #978. Ce sont les **deux seules xrefs natives** du sélecteur : le shim est
donc **DÉPLACÉ** dans `_targets.py` (foyer partagé du paquet) plutôt que recopié — option (1) de la
doctrine des cycles, et exactement ce que sa propre docstring interdisait de forker.
