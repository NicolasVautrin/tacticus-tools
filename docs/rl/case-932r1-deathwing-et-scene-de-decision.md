# case-932-r1 — `DeathwingKnight` et la scène de décision : six items, quatre lectures natives refaites

Tranche `[opus]` du 2026-08-18, build `t6dpr4k06g`. Six résidus dont **trois avaient une prémisse
fausse ou périmée** — et c'est le fait dominant de la tranche, pas un incident.

| item | verdict |
|---|---|
| `#932-r1` `DeathwingKnight` | **PRÉMISSE PARTIELLEMENT PÉRIMÉE** — les faces COMBAT étaient déjà portées (#1073). La face DÉCISION est portée ici et **confrontée live**. |
| `#953-r5` recensement `scene.hpmax` | **RÉSOLU** — recensement DÉRIVÉ (57 sites), et il **corrige la fiche sur trois points**. |
| `#433-r4-r3-r2` les deux termes OWNER | **RÉSOLU** — accord natif **2/2**, ce que la fiche donnait explicitement pour NON COUVERT. |
| `#1027-r4` caster non repositionné | **RÉSOLU (port)** — et la RE établit que **deux fonctions natives font l'inverse l'une de l'autre**. |
| `#438-r1` régime MULTI-EVENTS | **RÉSOLU** — accord natif, contre-épreuve à **+50,000000 exactement**. |
| `#550-r3` domaine TUILE vs UNITÉ | **PRÉMISSE RÉFUTÉE** par #1030-r5 — et le correctif qui en découle ferme **deux** écarts que personne n'avait comptés. |

---

## 1. `#932-r1` — la fiche décrivait un port qui existait déjà

La fiche annonçait `DeathwingKnight` « porté nulle part ». **Faux depuis #1073** : `EffectType 1512`
(`DeathwingKnightEffect`, sous-classe de config), `TriggeredAbilityType 1510`
(`DeathwingKnightAbility`) et les deux registres étaient en place. Ce qui manquait — et que la
fiche mentionnait en passant, dans la docstring de `DeathwingPlaybook` (« elle n'est PAS portée
ici — une ability par tranche ») — était la **face DÉCISION**.

`IdunBattle.AI.Playbook.Loki.DeathwingKnightPlaybook$$GetAdjacentFriendUtility`, corps entier :

```
if (!UnitExtensions.HasFaction(friend, 0xa)) return 0;        // UnitFaction.DarkAngels
return getUtilityVal(DAT_1833fc908);                          // 10
```

**Deux classes natives, deux corps distincts** — pas une instance de sa jumelle. `frida/classes.tsv`
donne aux DEUX `AdjacentUnitPreferenceTriggeredAbilityPlaybook\`1` (le `.ctor` décompilé nomme
`AdjacentToOwnerNonOwnerPlaybook` : c'est le mislabel de thunk gshared déjà documenté pour
`Deathwing`, `RedRampage`, `IconOfObstinacy` et `PsychicFortress`). Les octets sont identiques **au
slot de littéral près**, ce qui interdit à l'ICF de les fondre.

La clé est **lue au slot**, jamais dérivée du nom : `metadata/string_literals.tsv` donne
`0x33fc908 -> "DEATHWINGKNIGHT_AdjacentDAFriend"` contre `0x33fca48 -> "DEATHWING_AdjacentDAFriend"`
— deux entrées **voisines dans la table**, à un préfixe près. Poids `10` pour les deux dans
`Utilities.Default.TriggeredAbilities` : c'est une **coïncidence de valeur**, pas une clé partagée.

Ce que la classe déclare, lu au bloc `methodPointers` du PE (trois entrées contiguës ancrées sur le
`.ctor`) : `[.ctor, GetAdjacentFriendUtility, <corps "return 0" fondu par l'ICF>]` — la troisième
est **la même adresse** que la troisième de `DeathwingPlaybook`. Ni cap, ni filtre. Faces
ATTACK/REPAIR : aucun corps propre, donc le `yield Fix64(0)` hérité — DEAD, comme chez sa jumelle.

### Le porteur, et pourquoi la greffe n'a pas été nécessaire

`unit_map find --ability DeathwingKnight` : `darkaNpc3Terminator` (**npc**) et `darkaSmnTerminator`
(**summon**). Aucun héros du pool. Mais `darkaNpc3Terminator` porte une table de stats npc à
**45 paliers**, donc le **chemin de stats EXPLICITE** (`case-92` recours 4) l'amène en bataille avec
SES stats, SES traits et SON passif — strictement mieux qu'une greffe, qui perdrait les trois.
Mesuré : `--explicit-stats darkaNpc3Terminator:20` le déploie, et son `TriggeredAbilityComponent`
lu live porte bien `1510`. Son trait `TeleportStrike` lui donne **52 tuiles candidates**, ce qui a
rendu le montage de tuile plus facile, pas plus difficile.

---

## 2. `#433-r4-r3-r2` et `#932-r1` — le montage qui rend un poids de 5 observable

Les trois termes ont la même forme (`w × |amis qualifiants à distance 1 de la tuile candidate|`) et
un seul probe les mesure : `probe_932r1_433r4r3r2_termes_owner_adjacents.py`. Le critère est celui
de `probe_433_r4_r3` transposé de la face NON-OWNER à la face OWNER : **on cherche une
configuration où le terme RENVERSE l'argmax du port, et alors seulement on demande au natif quelle
tuile il joue.** Un accord sur une configuration où le terme ne renverse rien serait parfaitement
lisible et entièrement vide.

**Accord natif 3/3**, une seule passe :

| terme | poids | craft | argmax SANS | argmax AVEC | natif |
|---|---:|---|---|---|---|
| `1510 DeathwingKnight` | 10 | 3 amis DarkAngels déplacés en (4,8),(5,8),(5,7) | (6,5) | **(4,7)** | (4,7) |
| `1000 PsychicFortress` | 5 | 1 ami posé SUR (6,6) | égalité à 3 | **(5,7)** | (5,7) |
| `1487 EcogSupport` | 30 | aucun (l'E-Cog invoqué suffit) | égalité à 3 | **(3,4)** | (3,4) |

### Quatre obstacles de montage, et leur remède — c'est le contenu réutilisable de cette section

1. **Le classement des tuiles est dominé par `MinDistanceToEnemy`**, dont les paliers valent des
   dizaines de points. Un terme de **5** ne peut donc renverser un écart de tête que si cet écart
   est **NUL**. Remède : **un seul ennemi** — les tuiles équidistantes forment alors des ANNEAUX,
   et l'anneau de tête est une ÉGALITÉ. Avec trois ennemis dispersés, les paliers se croisent et le
   classement est strictement étalé (tête à −290, suivante à −305, puis un mur à −380).
2. **Les amis spawnent groupés dans un coin** et n'atteignent aucune tuile de tête. Remède :
   `--unit-stat <vis>:Movement=20`. C'est un levier de MONTAGE — il ne touche ni le poids, ni le
   gate, ni l'adjacence, c'est-à-dire aucun des trois étages que la mesure interroge.
3. **Occuper le sommet est plus puissant que de le battre.** Une tuile occupée sort de l'ensemble
   candidat ; le sommet tombe alors sur le rang suivant, très souvent une ÉGALITÉ, qu'**un seul**
   ami tranche quel que soit l'écart d'origine. C'est ce qui a rendu `PsychicFortress` mesurable.
4. **Un porteur qui a une attaque à portée ne propose PAS un mouvement pur** : le natif rend
   `[MoveUnitMessage, ActiveAbilityMessage]`, et sa destination est alors la **tuile d'ATTAQUE**
   (`UtilityAttackCase`), pas la sortie d'`UnitMovement(6)`. Comparer l'une à l'autre serait
   comparer deux modèles. ⚠ Retirer ses `ActiveAbilities` **ne l'en prive pas** — l'attaque normale
   est elle-même une ability concrète (mesuré : `ultraTigurius` attaque à toute portée de mouvement
   testée, 8/10/12/20). Le probe porte donc **deux voies** et déclare laquelle il mirrore.

### Ce que le montage `EcogSupport` a coûté, et ce qu'il enseigne

Le seul ami QUALIFIANT est l'E-Cog, et il est **immobile** — son tour est terminé dès son
apparition (#291). La phase « déplacer des amis vers T2 » y est donc structurellement vide, et
c'est la phase OCCUPER qui porte le montage : **chaque passe consomme un ami mobile**, d'où un
roster à cinq. Deux pièges mesurés en chemin :

* **`aiPlayByUnit` joue l'équipe du joueur COURANT.** L'appeler sans vérifier la bascule fait jouer
  MA team : `turnsPlayed=9` et bataille terminée dès le premier tour. La garde de bascule vit dans
  `rl_duel cmd_aiturn` (quirk H19 : le `endturn` ne flippe pas toujours) — on passe par lui.
* **`decisionView.toActivate` est une liste d'IDS**, pas de dicts. Le lire comme des dicts rend une
  liste vide et fait conclure « le porteur n'est jamais redevenu activable ».

**Ce qui reste NON CONFRONTÉ** : le porteur **SUMMON** de `1510` (`darkaSmnTerminator`). Le npc
suffit à exercer le playbook — le natif le charge PAR ABILITY — mais la voie summon a sa propre
géométrie d'apparition. Résidu `#932-r3`.

---

## 3. `#953-r5` — un recensement qui corrige sa propre fiche sur trois points

`probe_953r5_consommateurs_hpmax.py` visite l'AST de tout `engine/**` et **dérive** les sites au
lieu de les lister : **57** sites, **0** non classé, **0** entrée orpheline, et le périmètre **dit
ce qu'il écarte** (63 `hp_max` du `HealthComponent`, 12 `ctx.hpmax_by_id` — l'homonyme
d'`AiDecisionContext`, dont le substrat est `observeBattle.hpMax` et qui n'a jamais été touché).

**Trois corrections à la fiche, mesurées :**

1. `engine/predict.py` n'est **pas** un consommateur — ses 17 occurrences sont les paramètres
   `target_max_hp` / `boss_max_hp`, alimentés par `observeBattle.hpMax` via `ai/action_generators.py`.
2. `engine/services/trait_damage_limits.py` non plus — son `max_hp` est l'`initialHealth`, et sa
   propre docstring le dit.
3. Le foyer central est `engine/utilities/damage.py::DamageUtility.evaluate`, que la fiche ne
   nommait pas : `max_hp = target_max_hp if (…) else hp` — `None` retombe sur les **PV COURANTS**,
   donc `combinedMax` SOUS-ESTIME et `u_damage = Clamp(D/combinedMax,0,1)×80` **SUR-ESTIME**. Six
   playbooks NonComparable y arrivaient avec `None`.

### Le fait que personne n'avait écrit : la dégradation n'a pas un seul signe

| classe | n | ce que `None` produit |
|---|---:|---|
| `PRODUCTEUR` | 11 | écrit la table ou la clé |
| `PROPAGE` | 6 | transporte vers un autre foyer |
| `GATE_FERME` | 4 (+1 mixte) | le prédicat rend Faux → **sous-estimation** |
| `GATE_OUVERT` | 4 (+1 mixte) | le prédicat rend Vrai → **l'effet vit alors qu'il ne devrait pas** |
| `ABANDON` | 1 | `return None` : la prédiction entière est abandonnée |
| `REPLI_0` / `REPLI_AUTRE` | 1 / 1 | axe inerte / valeur FAUSSE (les PV courants) |

Côté MAGNITUDE le trou FERME le canal (`_missing_health_steps` → `None`, `Skullsmasher` muet, la
mesure de #953-r1) ; côté CONDITION D'ACTIVITÉ il l'**OUVRE** — `Scene.unit_state` n'écrit `max_hp`
que si elle est non-`None`, donc les `CreateActiveCondition` faisaient `.get("max_hp") -> None ->
return True`. La face COMBAT, elle, écrivait la clé **inconditionnellement**
(`runner/components.py::UnitEffectStateView`) : les gates mordaient d'un côté et pas de l'autre.
**Aucun site ne lève** — tout le trou était silencieux.

### La voie, mesurée : le repli couvre les PROBES, pas la décision live

Dans `engine/**`, `Scene.from_predictor_sctx` n'a qu'**un** appelant qui pré-remplit
`sctx["hpmax_by_id"]` : `ai/context.py`, **depuis `40da9467` (2026-07-20)**, donc bien avant
#953-r1. Hors `engine/**`, **34 fichiers** (probes et outils) l'appellent, dont **6** seulement
pré-remplissent : pour les **28 autres**, `predictor["hpmax_eff_by_id"]` est la SEULE source de PV
max. Le repli de #953-r1 est donc ce qui met **toutes** les voies d'accord.

Re-mesure live sur le chemin `AiDecisionContext` : les deux espaces de clés **coïncident**
(`decisionView.units[].id` ∩ `combatSnapshot.units[].entityId` = les 5 unités) et `scene.hpmax`
rend un entier pour chacune. La panne silencieuse d'un étage en dessous — table REMPLIE mais
STÉRILE — n'existe pas.

⚠ **Le recenseur des voies a rendu `0` à son premier jet**, et ce zéro se lisait comme une mesure :
le filtre était pris sur `p.parts`, or un worktree d'agent vit sous `.claude/`, donc **tous** les
fichiers étaient exclus. Corrigé (filtre sur le chemin RELATIF) **et** cranté : le probe refuse
désormais un recensement vide.

**Ce qui reste** : les six `GATE_OUVERT` ne sont pas confrontés live (il faudrait un porteur dont
l'effet conditionnel change une prédiction observable), et les 28 probes ne sont pas rejoués un par
un. Résidu `#953-r6`.

---

## 4. `#1027-r4` — deux fonctions natives, deux réponses opposées

Relu sur `t6dpr4k06g`, `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable(caster,
possibleCasterPosition)` `memset` son `AbilityEntities` (0x128 o) puis écrit :

```
ae@+0x08 = caster                                             // Caster (l'ENTITÉ)
ae@+0x10 = entity                                             // Target
ae@+0x18 = caster                                             // Owner
ae@+0x30 = EntityExtensions.GetMainTile(entity)               // TargetTile
ae@+0x38 = EntityExtensions.GetTiles(entity)                  // TargetPosition
ae@+0x40 = UnitPosition.get_MainTile(possibleCasterPosition)  // CasterTile
ae@+0x48 = possibleCasterPosition                             // CasterPosition
```

et `IdunBattle.Entities.Selectors.CasterTileSelector$$Select` — corps des DEUX slots
`<DSLSelectors+0x50>` et `<+0x58>` — lit `CasterPosition.Tiles` (+0x48) **d'abord**, puis
`CasterTile.ToList()` (+0x40), puis `GetTiles(Caster)` (+0x08). Sur cette voie, `CasterTiles`
désigne donc l'empreinte **à la position candidate**.

`IdunBattle.AI.Playbook.SolarAtomizerPlaybook$$EvaluateNonComparable` itère exactement cette
fonction, puis évalue `GetTargetTiles()` par
`TargetsSelector$$SelectTiles(sel, <copie de l'AbilityEntities>)` : la **direction** de la bande
(`DirectionTo(AdjacentTiles(Target) & Tiles(CasterTiles), Target)`) en dépend.

⚠ **Et l'autre voie fait l'inverse.**
`IdunBattle.AI.Playbook.PlagueburstMortarPlaybook$$CalculateCustomUtility(this, caster,
casterPosition, target, abilityState, possibleTargets)` construit son `AbilityEntities` par
`AbilityEntities$$.ctor(&ae, caster, caster, target, 0, 0, …)` et **ne passe pas** son paramètre
`casterPosition` (relu aux arguments du `call`). `CasterTiles` y retombe donc sur `GetTiles(Caster)`
= l'empreinte COURANTE, ce qui est **exactement** ce que la docstring d'avant affirmait — elle
n'était pas fausse, elle décrivait l'autre fonction. C'est pourquoi `caster_position` est
**optionnel** : un appelant DÉCLARE laquelle des deux il mirrore, et recopier l'une sur l'autre
serait faux dans les deux sens.

**Deux asymétries à ne pas lisser** :

* le slot `Caster` (+0x08) porte l'ENTITÉ, que `SelectTiles` déplie par `GetTiles(caster, state)` :
  un arbre ancré sur `Caster()` lit la position d'ORIGINE **même quand la candidate est posée**. Le
  port pose donc `caster_pos` sur le contexte, **jamais** `caster["pos"]` ;
* **à l'origine on ne pose RIEN.** Nativement, `CasterPosition.Tiles` à l'origine EST l'empreinte
  d'origine ; côté port, le repli `_feet(caster)` la rend **MESURÉE**
  (`decisionView.units[].feet`) là où `caster_pos` la réduirait à sa main tile. C'est la règle de
  `the_lantern._caster_footprint` (« à l'origine, la MESURE fait autorité sur la dérivation »).

Le résidu `#459-r1` est **inchangé** : `caster_pos` est un `(col,row)`, pas une `UnitPosition`. Le
caster est désormais au bon ENDROIT, pas encore à la bonne FORME. Et le port **n'est pas confronté
live** : `1174` ne publie aucune cible hors de la carte dédiée de Belisarius (`#1027-r6`).

---

## 5. `#438-r1` — le régime MULTI-EVENTS, et deux pistes mortes qu'il faut nommer

La feuille `TriggeredAbilities(2)` de la face ATTACK est évaluée **par event**, chacun avec sa
`DamagePrediction`. #438 avait câblé `ev.prediction` — correct par construction, mais sur un
montage à **un seul** event, où « la prédiction de l'event courant » et « celle du premier event »
sont la même chose.

**Deux pistes mesurées et écartées** (les nommer évite de les rejouer) :

* une arme **`Blast`** (`astraOrdnance`, `{"hits": 3, "DamageProfile": "Blast", "Range": 3}`) :
  **1** event. Le profil d'arme multiplie les COUPS d'un event, pas les events ;
* le **splash Psyker** (`astraPrimarisPsy`) : **1** event aussi. Le splash Psyker est un TERME
  évalué DANS la feuille, pas un event de plus.

La source multi-events est une **ability active à ZONE**. Montage retenu : `1204 BarbedOvipositor`
greffé sur `astraBullgryn` (`PassiveAbilities` — et on **AJOUTE**, on ne remplace pas), qui lance
`FragBomb (1017)` sur un groupe de trois. La greffe est légitime : le playbook ne lit du case que
`DamagePrediction` et le trait `Mechanical` de la CIBLE — ni stat, ni trait, ni arme du caster.

| | résultat |
|---|---|
| events | **3**, régimes `(will=F, might=T)` / `(F, F)` / `(F, F)` |
| `pairUtility` natif | **123.33483331371099** |
| port | **123.334833** → accord |
| contre-épreuve `--mutant premiere-prediction` | port **173.334833**, soit **+50,000000 exactement** = deux `PossibleKill` (25) surnuméraires |

⚠ **Le cran anti-dégénéré a d'abord été VERT SUR UNE ILLUSION.** `will_be_kill` et `might_be_kill`
sont des **méthodes**, pas des propriétés : `getattr(pred, "will_be_kill", False)` rend la méthode
LIÉE, donc un objet **toujours vrai**. Le cran lisait `(True, True)` pour les trois events d'un
montage où deux cibles étaient à 400 000 PV contre 3 de dégât. Un cran qui ne peut pas rendre Faux
ne garde rien — il faut APPELER.

**Ce qui reste** : le régime BLOCK de `get_WillBeKill` (`BlockScenarios[0]` au lieu de `rawMin`) et
`probe_45_psyker.py`, qui appelle la feuille SANS prédiction. Résidu `#438-r2`.

---

## 6. `#550-r3` — la prémisse était réfutée, et le correctif ferme deux écarts non comptés

Le résidu tenait de la lecture « `CountOrAdd` ajoute l'ENTITÉ SOURCE, donc `Enemies(<tuiles>)` rend
des TUILES ». Elle manquait **un étage**, et #1030-r5 l'a établi : ce que `CountOrAdd` itère n'est
pas `Select(entities)` mais le **slot 5 `SelectAllActors`** de son sélecteur source
(`FUN_180026100(5, …, <this+0x20>, entities, <this+0x2c = selectionType>)` — arité 2, concordante
avec `metadata/interface_slots.tsv`), et `TargetsSelector$$SelectAllActors` **résout** chaque
élément par `SelectUnit` (`IsUnitFoot || IsTile -> GetUnit`). L'`entity` ajouté est donc un acteur
**déjà résolu**.

Le port n'a donc plus besoin du `Units(...)` intercalaire — et **il n'était pas inerte** :

1. **Dédoublonnage que le natif n'a pas.** `UnitsByTeamSelector$$Select` alloue un
   `System.Collections.Generic.List<T>` (jamais un `ArraySet`) et `CountOrAdd` y fait `List.Add`
   par élément qualifiant, depuis le slot 5 et non le slot 6 `SelectUniqueActors` : une unité
   atteinte par DEUX éléments sort **deux fois**. `Units`, lui, dédoublonne inconditionnellement
   (`#433-r3-r1a-r1`). La zone d'`ItItches` compte au plus TROIS tuiles
   (`Target + AdjacentTilesIntersection`), donc le régime est atteignable par un ennemi
   **multi-hex** — et `AddEffect(Pinned)`, contrairement au displace, n'a aucun gate
   `IsDisplaceable`/`BigTarget` pour l'écarter.
2. **`selectionType` perdu.** `...ItItchesAbility$$GetTargetUnits`, relu verbatim, finit par
   `DSLSelectors.Enemies(f, of, zone, 3)` — `UnitSelectionType.OnlyAliveAndTargetable`. Le port
   n'en passait **aucun**, ni à `Units` ni à `Enemies`. Le volet VIVANT était rattrapé par accident
   (`_occupants_by_tile` ne garde que les vivants) ; le volet **Untargetable** ne l'était pas — une
   unité en deep strike entrait dans les cibles.

Le port écrit désormais la forme native, `Enemies(<tuiles>, selection_type=3)`.

⚠ **Ne pas généraliser le retrait.** Le motif `Enemies(Units(...))` apparaît à une trentaine de
call-sites du port, et il y est très majoritairement **NATIF** : `DSLSelectors$$AdjacentEnemies` et
`$$SurroundingEnemies` composent littéralement `Enemies(Units(...))`. `ItItches` était le seul
où le port l'INTERPOSAIT. Vérifier au décompilé, call-site par call-site.

**Ce qui reste** : le régime DOUBLON est désormais atteignable par le port mais **non confronté**
(il faut un ennemi multi-hex occupant deux tuiles de la zone). Résidu `#550-r5`.

---

## 7. Fichiers

* Ports : `engine/playbook/adjacent_unit_preference.py` (`DeathwingKnightPlaybook` + registre),
  `engine/playbook/tile_targets.py` (`caster_position`),
  `engine/playbook/noncomparable/solar_atomizer.py` (call-site),
  `engine/runner/abilities/tyranids.py` (`Enemies(zone, 3)`),
  `engine/entities/selectors/units.py` (le fait « aucun dédoublonnage », au foyer).
* Mesures : `probe_932r1_433r4r3r2_termes_owner_adjacents.py`,
  `probe_953r5_consommateurs_hpmax.py`, `probe_438r1_multi_events_aoe.py`.
* Cliquets : `tests/engine/test_932r1_433r4r3r2_termes_owner_live.py`,
  `tests/engine/test_953r5_consommateurs_hpmax_offline.py`,
  `tests/engine/test_1027r4_caster_position_tile_target_offline.py`,
  `tests/engine/test_438r1_multi_events_aoe_live.py`.
