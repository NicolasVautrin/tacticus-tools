# case-589-r1-r1-r2-r1 — `AmuletOfTheVoidwyrm_CritDamageReduction`, l'axe RÉDUCTION du canal crit-dégât

`#589-r1-r1-r2-r1`. L'élargissement de #589-r1-r1 (les deux canaux CRIT balaient désormais
`board_effect_carriers`) avait rendu cet effet **atteignable** sans le porter. Il l'est.

## 1. La question binaire, et sa réponse mesurée

> « Le natif retranche-t-il `critDmgReduction[niveau de RELIQUE] × <summons/decoys alliés adjacents
> au porteur>` du dégât de CRIT reçu par ce porteur, et le port fait-il pareil ? »

**OUI, et il s'accorde — 9 bras, 9 accords, 0 désaccord.** `--crit 100,2000` (tous les coups
critent, aucun tirage sur le crit ; `2000` laisse la marge qui empêche `Math.Max(0, …)` de saturer) :

| board | `n` | niveau | trait | réduction | LIVE | port | `NOCHANNEL` | `PASSIF` |
|---|---|---|---|---|---|---|---|---|
| `MC1_67` | 0 | 3 | `Decoy` | — | `[3703, 3661, 2679, 2971]` | == | inchangé | inchangé |
| `MC1_67` | **1** | 3 | `Decoy` | **432** | `[2493, 2636, 2377, 2537]` | == | `[3703, …]` | `[2256, …]` |
| `MC1_67` | **2** | 3 | `Decoy` | **864** | `[2568, 2438, 2074, 2456]` | == | `[3703, …]` | `[2006, …]` |
| `MC1_67` | 1 | **1** | `Decoy` | **390** | `[2739, 2727, 3062, 2767]` | == | mord | mord |
| `MC1_67` | 1 | **10** | `Decoy` | **579** | `[2256, 2717, 2818, 2066]` | == | mord | *ne peut pas mordre* |
| `MC1_67` | 1 | 3 | **`Summon`** | 432 | `[2579, 2398, 2441, 2598]` | == | mord | mord |
| `MC1_67` | 2 | 3 | **`Summon`** | 864 | `[1817, 2092, 2099, 2688]` | == | mord | mord |
| `C1_74` | 0 / 1 / 2 | 6 | `Decoy` | 0 / **495** / **990** | 3 salves | == | conforme | conforme |
| `C3_14` | 1 (géo) | 6 | `Decoy` | **495** | `[2713, 2198, 2962, 2787]` | == ⛔ | mord | mord |

⛔ **La dernière ligne est un accord par COMPENSATION, pas un accord** (#589-r1-r1-r2-r1-r8) : le
`1` du natif venait de `genesSmnDecoy` (allié, `Decoy`, présent au déploiement sur un voisin
**stocké**), celui du port d'une couronne géométrique. Le dégât coïncide, la mécanique non. Cf. §6.

**Recoupement croisé, non cherché** : la salve du bras `PASSIF` à `n=1` (`[2256, 2717, 2818, 2066]`)
est **exactement** le LIVE du bras `niveau = 10`. Le repli passif lit donc bien le dernier palier
(579), ce que le bras `PASSIF` prétendait — mesuré des deux côtés, indépendamment.

## 2. L'artefact natif — `ForSubtraction`, et c'est le premier de l'axe

`IdunBattle.Entities.Effects.Loki.AmuletOfTheVoidwyrm_CritDamageReductionEffect$$CreateCritDamageBonus`
(ghidra inline `ForSubtraction` ; il se reconnaît à l'**offset écrit** dans `EffectBonus` — `+0x00`
trigger, `+0x10` addition, `+0x18` subtraction ; ici `+0x18` reçoit le montant et `+0x10` reste `0`) :

    EffectBonus.ForSubtraction( get_OwnerIsTarget,                    <- trigger NU, aucun `&`
                                GetCritDmgReductionAmount() )

    GetCritDmgReductionAmount = Multiply( ConfigVar(0x97 = critDmgReduction, GetAbilityState(effect)),
                                          GetAdjacentFriendlySummonsAndDecoysCount() )

    GetAdjacentFriendlySummonsAndDecoysCount =
        Count( UnitsWithTrait(AdjacentFriends(Owner@+0x30, unique: 1, selectionType: 3), 0x2   = Summon)
               op_Addition
               UnitsWithTrait(AdjacentFriends(Owner@+0x30, unique: 1, selectionType: 3), 0x41d = Decoy) )

    CreateActiveCondition = AmountIsGreaterThanZero( <le MÊME compteur> )
    GetCalculateLevel     = <le MÊME compteur>        (niveau d'AFFICHAGE, aucun observable de combat)

Résolutions relues d'`enums.tsv` : `AbilityVariableType 0x97 = 151 = critDmgReduction`,
`UnitTrait 0x2 = Summon`, `UnitTrait 0x41d = 1053 = Decoy`. `AmountIsGreaterThanZero(x)` =
`AmountIsGreaterAbilityTrigger(x, minAmount = <DSLFormulas+0x18> = Direct(0))`.

**Consommation, relue** : `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects`
accumule littéralement `addition − subtraction` (`uVar14 += (int)v − (int)(v >> 32)`), et
`$$CalculateCriticalDamage` fait `Math.Max(0, GetStat(10) + somme)`. Le port rend donc un entier
**NÉGATIF** — mirror du terme soustractif, pas une convention locale.

**La surcharge d'`AdjacentFriends` se tranche par la POSITION des arguments** : l'appel passe
`(this, <Owner@+0x30>, 1, 3)`, et les deux surcharges natives sont `(this, unit, unique,
selectionType)` et `(this, unit, unitTile, unique)` — un `1` littéral ne peut pas être un sélecteur
de tuile. La référence d'équipe de `Friends` **est le centre**, d'où `reference=Owner()` explicite
côté port.

## 3. TROIS enums, deux valent 1460 — le piège du cas

    EffectType            0x5b4 = 1460 = AmuletOfTheVoidwyrm_CritDamageReduction   <- l'effet
    TriggeredAbilityType  0x5b8 = 1464 = AmuletOfTheVoidwyrm                       <- sa CONFIG
    TriggeredAbilityType  0x5b4 = 1460 = TalismanOfRage                            <- une AUTRE relique

Le `.ctor` de l'effet, relu **octet à octet** (`ba b8 05 00 00` = `mov edx, 0x5b8`), passe par la
surcharge d'`AbilityOrEffect$$op_Implicit` dont le corps appelle `set_TriggeredAbility` — les
surcharges sont homonymes, elles se tranchent par ADRESSE. Lire l'EffectType comme identité de
config ferait lire les variables de `TalismanOfRage`. Un test offline garde les trois valeurs.

## 4. La POSE — owner-effect PERMANENT, et sa `CreateActiveCondition` la rend INVISIBLE au seed

`classes.tsv` : `AmuletOfTheVoidwyrmAbility` dérive d'`IdunBattle.Entities.Abilities.
AOwnerEffectTriggeredAbility`, dont le `CreateBehaviour` (corps de BASE) est

    If( <trigger>, AddEffect( GetEffectType() = 0x5b4,
                              AbilityState(entities, Owner@+0x30, <cette ability>),
                              source = Owner, targets = Owner, turns = <zéroé> ) )

sur `CreateTrigger = OnOwnerSpecificAbilityInit(<this+0x10>)`. **Source == porteur == Owner**,
permanent : ce qui l'éteint est la CONDITION.

Deux conséquences, et la seconde est ce qui a coûté le plus :

* l'`AbilityState` baké dans `EffectComponent+0x18` est celui de la **relique sur son porteur**,
  donc l'état **TERTIAIRE** (`TertiaryAbilityLevel` / `TertiaryAbilityVariablesMultiplierPercentage`,
  cf. `case-237`). Le port le relit par le foyer UNIQUE `triggered_ability_state` (#357) — exact ici
  *parce que* la source est le porteur ;
* l'effet est **INACTIF** sans voisin qualifiant, donc **absent du canal `decisionView` par défaut**
  (ACTIF-ONLY, ground truth #100) — même motif qu'`AnvilShield_BlockChanceBelowHealthCap`,
  `HammerOfWrath_ConditionalDamage`, `ModifiedExoarmour_ExtraDmg`, `VisionsOfHeresy_*`.

## 5. Ce que le montage a coûté, et qui resservira

* **La relique est à l'ÉTAT 2** : `genesKelermorph` / `genesPrimus` / `genesBiophagus` sont les trois
  porteurs autorisés (`catalog_inject --list-relics`) et **tous trois sont au pool** →
  `rl_duel build --equip-relic "genesKelermorph:AmuletOfTheVoidwyrm:<niveau>"`, qui pose les trois
  écritures d'un bloc. Mesuré en bataille : `unitAbilityStates` rend une entrée de **hiérarchie 3**
  `{id: 1464, level: 3, mult: 100}`.
* **Les trois porteurs autorisés portent `Ambush`, et une unité en embuscade n'est pas CIBLABLE.**
  L'attaque part alors sans la moindre erreur et **ne mute RIEN** (`ok: true`, `mutated: false`,
  `changes: []`). `--unit-stat 'genesKelermorph:Traits=["Hero"]'` le retire ; le trait n'a aucun
  rapport avec le canal mesuré.
* **Le compteur se pilote par `--unit-stat '<vid>:Traits=["Decoy"]'`** — le substrat d'ENTITÉ
  (`BC.Units[].Traits` → `BaseUnitComponent`) que lit `UnitsWithTrait` (#264), le même champ qu'un
  vrai summon renseignerait. Les **59** unités à trait `Summon` sont hors pool et
  `--a-units` les refuse ; amener un summoner ne donnerait aucun contrôle sur `n`.
* **`my_player` se pose AVANT `reach_my_turn`.** Sans lui le harnais le devine (`alive(dv)[0].owner`)
  et peut s'arrêter sur le tour de l'AUTRE camp — l'attaque part hors tour et rend `mutated: false`
  **sans erreur**. Signature : `abilityTargets.playerId` = 4 alors que l'attaquant est au joueur 3.
* **Le canal RELIQUE exige un transport RPC ambiant.** `load_state` tire `unitAbilityStates`
  elle-même, mais seulement si `snapshot.bind_live_rpc` a été appelé (#357/#363). La fixture `rpc`
  des tests le fait ; **un probe doit le faire lui-même**. Sans lui, mesuré :
  `ability_state = (50, 180)` au lieu de `(3, 100)`, donc `critDmgReduction` au dernier palier
  (**579**) au lieu de celui du niveau demandé (**432**). Le tri-état du port a fait son travail —
  c'est le harnais qui ne fournissait pas le canal.

## 6. Le bras SUBSTRAT — ⛔ RÉFUTÉ (#589-r1-r1-r2-r1-r8, 2026-08-10)

**Ce que cette section affirmait est FAUX, et la version qui suit est la mesure qui l'a établi.**

Elle disait : sur `C3_14`, porteur en `(5,4)` et compagnon en `(5,3)` (arête absente du substrat
stocké dans les deux sens), « le natif **ACTIVE** l'effet et retranche `495 × 1` », donc
« `AdjacentTilesSelector` et `BattleQuery$$IterateAdjacentTiles` ne lisent pas le même substrat ».

**Les deux conclusions sont réfutées** :

* **le chemin est UNIQUE** — `AdjacentTiles` → `AdjacentTilesSelector$$Select` → `IBattleQuery`
  **slot 80** = `IterateAdjacentTiles` (slot LU dans `metadata/interface_slots.tsv`), qui énumère
  une **liste STOCKÉE** (`TileQuery.<IterateAdjacentTiles>d__8$$MoveNext`). Aucune géométrie ;
* **le natif ne comptait PAS ce compagnon.** L'activité de l'effet venait de **`genesSmnDecoy`**,
  une unité **amie** portant `Decoy`, présente **au déploiement** en `(6,4)` — c'est-à-dire sur un
  voisin **stocké** du porteur. Le bras `--geo-only` ne figeait que les **deux compagnons** et n'a
  jamais fait l'inventaire des porteurs de trait.

Mesure différentielle (une seule unité bouge, tout le reste figé, tous les porteurs poussés à
hex ≥ 4) : compagnon LOIN → **inactif** ; compagnon en `(5,3)` → **inactif** ; compagnon sur un
voisin stocké → **actif** ; retour LOIN → **inactif**. Et compteur lu du **DÉGÂT** : intrus seul
= **1**, intrus + compagnon en `(5,3)` = **1** — le compagnon n'ajoute rien.

⚠ **L'accord annoncé ici, et celui de la ligne `C3_14` du §1, étaient une COMPENSATION** : le port
comptait 1 par géométrie, le natif comptait 1 par `genesSmnDecoy`. Deux causes différentes, le même
`1`, donc le même dégât — d'où un accord parfait sur une mécanique que ni l'un ni l'autre ne
décrivait correctement.

Le vrai écart, lui, était ailleurs et bien réel : le port ne comptait pas `genesSmnDecoy`, parce
que `HealthComponent$$IsAlive` porte **trois** branches et que le port n'en portait qu'une — une
unité à `0/0` PV est **vivante** pour le natif. Détail, correctif et gardes :
`docs/rl/case-589-r1-r1-r2-r1-r8-unite-sans-sante.md`.

### 6bis. Le bras est RÉPARÉ, et il mesure désormais la réfutation lui-même (#589-r1-r1-r2-r1-r9, 2026-08-11)

Tant que `_stage_geo` ne figeait que les deux compagnons, il pouvait re-mesurer autre chose que ce
qu'il annonce. Quatre changements, et le troisième est celui qui empêche le vert vide :

1. **INVENTAIRE NATIF** des porteurs de `Summon`/`Decoy` (`combatSnapshot.units[].traits`, clé
   `entityId`) puis **ÉLOIGNEMENT** de tous sauf le compagnon GEO. Le second compagnon n'a plus de
   traitement spécial : c'est un porteur comme un autre.
2. **`n` est DÉRIVÉ** de l'occupation mesurée de la liste **stockée**, plus jamais écrit. La ligne
   `n = 1  # le natif COMPTE le voisin géométrique` a disparu.
3. **TÉMOIN DIFFÉRENTIEL** sur le même runner, une seule unité bougeant : `S1` GEO → **inactif**,
   `S2` voisin **stocké** → **actif** (contrôle POSITIF), `S3` retour GEO → **inactif**. Le régime
   visé rend `n = 0` : LIVE == OFFLINE, `NOCHANNEL` no-op, `PASSIF` no-op — **le bras serait vert
   même sans relique équipée**. `S2` est ce qui l'interdit, `S3` ce qui interdit un état collant.
4. Le plan exige désormais **≥ 4** tuiles à hex ≥ 4 (il en exigeait UNE — c'est cette étroitesse
   qui laissait l'intruse en place).

Mesure (`--geo-only --n 1 --board C3_14 --level 6`) : porteurs natifs `genesMagus (5,3)` hex 1,
`genesPrimus (0,0)` hex 6, `genesSmnDecoy (0,1)` hex 5 (**éloignée**) ; témoin `S1 False / S2 (4,4)
True / S3 False` ; `n` dérivé **0**, `actif_natif` **False**, compteur port **0**, LIVE == OFFLINE.

`inventaire_traits` / `pousser_loin` deviennent le **foyer unique** (ils vivent dans le probe
amulette ; `probe_589r1r1r2r1r8_compteur_natif` y DÉLÈGUE et transpose le tri-état en refus) — deux
lectures séparées d'`entityId` referaient exactement le fork qu'on évite.

## 7. Les gardes

* `tests/engine/runner/test_amulet_voidwyrm_crit_reduction_live.py` — **9 passed**. Montage
  **importé** du probe, jamais retranscrit. Couvre : les trois régimes de `n` (dont la
  `CreateActiveCondition` à `n = 0`), le PRODUIT (`n=1` vs `n=2`, second cas discriminant), les deux
  niveaux (1 et 10, dont le bras `PASSIF` qui prouve le canal tertiaire), le trait `Summon`, le bras
  SUBSTRAT, et la garde de registre offline sur les trois enums.
  ⚠ **Le test du bras SUBSTRAT gardait la claim RÉFUTÉE** (`…_est_geometrique`, `actif_natif is
  True`, `compteur == 1`) : c'était le dernier porteur de l'inférence, et il est **renommé et
  inversé** par #589-r1-r1-r2-r1-r9 (`…_est_la_liste_STOCKEE` : `actif_natif is False`,
  `compteur == 0`, `mut == off`). Il assertionne le **témoin différentiel AVANT le reste** —
  à `n = 0` tout s'accorde trivialement, donc `S2` (voisin stocké → **ACTIF**) est ce qui interdit le
  vert vide — et exige que l'**inventaire** contienne bien l'intruse (≥ 3 porteurs, **un seul** à
  hex 1).
* `scripts/python/probe_589r1r1r2r1_amulet_crit_reduction_live.py` — la mesure, avec ses gardes de
  régime jouées **avant** tout montage : niveau hors paliers (le clamp haut rendrait le bras NIVEAU
  non discriminant), **saturation** de `Math.Max(0, …)` (deux modèles algébriquement confondus =
  accord DÉGÉNÉRÉ), et niveau == dernier palier (le bras `PASSIF` ne peut alors pas mordre — il est
  SAUTÉ, pas déclaré vert). `--verbose` imprime la DÉCOMPOSITION PAR ÉTAGE du port
  (compteur / `AbilityState` / `ConfigVar` / scalaire signé) : c'est elle qui a nommé l'étage fautif
  au premier désaccord, sans jamais fitter un scalaire.

**CONTRE-ÉPREUVES JOUÉES** : `NOCHANNEL` (l'effet retiré d'`EFFECT_CLASSES` → `BaseEffect`, canal
`None`) mord **exactement** quand `n > 0` et jamais sinon ; `PASSIF` (le callable
`tertiary_ability_state_of` retiré du contexte) mord **exactement** quand le niveau demandé n'est pas
le dernier palier.

## 8. Reproduction

    python probe_589r1r1r2r1_amulet_crit_reduction_live.py --n 0,1,2 --level 3 --verbose
    python probe_589r1r1r2r1_amulet_crit_reduction_live.py --n 1 --level 1
    python probe_589r1r1r2r1_amulet_crit_reduction_live.py --n 1 --level 10
    python probe_589r1r1r2r1_amulet_crit_reduction_live.py --n 1,2 --level 3 --trait Summon
    python probe_589r1r1r2r1_amulet_crit_reduction_live.py --n 0,1,2 --level 6 --board C1_74
    python probe_589r1r1r2r1_amulet_crit_reduction_live.py --n 1 --level 6 --board C3_14 --geo-only
    python -m pytest tests/engine/runner/test_amulet_voidwyrm_crit_reduction_live.py

## 9. Ce qui n'est PAS couvert

* ~~**La POSE offline n'est pas portée** — résidu **`#589-r1-r1-r2-r1-r1`**~~ — **FERMÉ (#10035,
  2026-08-18), et la prémisse ci-dessous était périmée DEUX FOIS.** « Poser
  `ABILITY_INIT_OWNER_EFFECTS["AmuletOfTheVoidwyrm"]` serait INERTE » est faux depuis **#1005**
  (`spawn.py::_seed_ability_owner_effects` lit `ctx.tertiary_ability` et l'ajoute à sa liste
  d'abilities, au couple TERTIAIRE) ; l'entrée elle-même est posée depuis le **2026-08-15**. Le
  mécanisme était donc entier — et pourtant rien n'arrivait dans l'état chargé. La cause est un
  **ordre de passes** dans `snapshot.load_state` : `_load_stats_and_effects`, qui porte la boucle de
  seed, tourne **avant** `_load_tertiary_abilities`, seul écrivain de `ctx.tertiary_ability`. Corrigé
  par `snapshot._seed_tertiary_owner_effects`, placée entre l'écrivain et le re-bake de #1009.
  Le probe de cette case-doc reste **PASS** après le correctif (3 accords, les deux contre-épreuves
  mordent exactement où attendu), et `test_amulet_voidwyrm_crit_reduction_live.py` reste **9 passed**.
  Détail : `docs/rl/case-10035-pose-tertiaire-au-chargement.md`.
* **L'union du compteur ne dédoublonne PAS, et ce n'est pas observable sur ce build** — résidu
  **`#589-r1-r1-r2-r1-r2`**. `TargetsSelector$$op_Addition` construit un `CombinedSelector` de
  mode **1**, et `CombinedSelector$$SelectUnion` est littéralement
  `new List(n1 + n2); AddRange(left); AddRange(right)` : une unité portant à la fois `Summon` et
  `Decoy` compterait **deux fois**. Le port mirrore le quirk (`Union` = concaténation). Mesuré sur le
  gameconfig : les deux seuls porteurs de `Decoy` (`genesDecoy`, `genesSmnDecoy`) valent
  `['Steppable', 'Decoy']`, et **aucune** unité ne porte les deux traits — le régime est
  inatteignable, donc le quirk est **lu, non confronté**.
* **La face PRÉDICTION n'est pas touchée** — résidu **`#589-r1-r1-r2-r1-r3`**, préexistant
  (`case-366-r1` §6.4) : `services/damage_prediction.py` n'appelle pas les canaux crit, donc la
  réduction n'entre pas dans la prédiction de dégât (ni pour l'IA, ni pour le preview).
* **La CAUSE de l'écart de substrat n'est pas tranchée** — résidu **`#589-r1-r1-r2-r1-r4`** (§6).
  Point d'ancrage natif à hooker pour la trancher :
  `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` (ce que
  l'itérateur rend RÉELLEMENT en bataille) confronté au champ `connectivity` que publie
  `boardGraph`. Aucun hook existant ne l'expose ; il reste à écrire (fenêtre de reinject requise).
* **Aucun VRAI summon n'a été joué** : le compteur est piloté par le trait posé au BC. Le natif ne
  lit que `HasFlag(unit, trait)`, donc la voie est équivalente **par construction** — mais elle n'a
  pas été confrontée avec un summon issu de son summoner.
* **`GetCalculateLevel`** (le même compteur, lu par les visuels) n'est pas porté : aucun observable
  de combat.
* **Un seul porteur joué** (`genesKelermorph`) sur les trois autorisés, et deux niveaux de
  multiplicateur non explorés (`TertiaryAbilityVariablesMultiplierPercentage` valait **100** sur tous
  les montages ; le seed porte **200** sur ses 175 entrées, mais la variable
  `critDmgReduction` n'est pas dans `variablesAffectedByRarityBonus`, donc le multiplicateur ne peut
  pas mordre — **lu au gameconfig**, pas confronté).
