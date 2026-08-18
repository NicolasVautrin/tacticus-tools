# #10037 -- sept residus de playbooks NonComparable, tranches ensemble

Numero **#10037** alloue par `probe_468_collision_numeros.py --suggere` (reservation exclusive dans
le `.git` commun ; `#10036` etait deja pris). Residus neufs ouverts par cette tranche :
**`#1032-r6`** et **`#971-r5`**.

Sept fiches, un seul repertoire (`engine/playbook/noncomparable/**` + `engine/playbook/
savior_protocols.py`). Le fil commun n'est pas thematique : c'est que **cinq des sept premisses
etaient perimees ou fausses**, et que les trancher a demandé de relire le natif plutot que la
fiche.

| Fiche | Verdict | Ce que la relecture a change |
|---|---|---|
| `#585-r2` | **PREMISSE REFUTEE** | la face DECISION de `1106` etait DEJA portee (#969 / #969-r1) |
| `#1032-r1` | **LIVRE** (offline) | `1052` et `1193` portees ; residu live `#1032-r6` |
| `#971-r4` | **LIVRE + CONFRONTE** | foyer d'ordre partage par les TROIS ; residu `#971-r5` |
| `#202-r1` | **FERME** | sommet a TUILE UNIQUE trouve (seed 777), natif MATCH |
| `#433-r4-r2-r3` | **TRANCHE** | `MIN_UTILITY` etait FAUX -- aucune borne native |
| `#433-r4-r1-r4-r2-r2` | **PREMISSE INVERSEE** | brancher les canaux aurait ete la REGRESSION |
| `#456-r2-r1` | **CRITERE TRANCHE** | disque GEOMETRIQUE **et** condition de plus, plus anti-vidage |

Cliquet : `tests/engine/playbook/test_10037_playbooks_noncomparable_offline.py` (27 tests, 7
etages, 100 % offline). Contre-epreuve : `probe_10037_mutants.py`, **8/8 mordent**.

---

## 1. `#433-r4-r2-r3` -- `EarlyWarningOverridePlaybook` n'a AUCUNE borne d'utilite

La fiche disait << reste a etablir qui lit ce statique ici (un `get_MinUtility` consomme par le
generateur ?) >>. **Personne ne le lit, et il n'existe pas de `get_MinUtility`.** Trois lectures
independantes, toutes trois faites sur le build courant :

1. **Le ctor du Bucket.** `...EarlyWarningOverridePlaybook$$EvaluateNonComparable` appelle
   `IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$.ctor(bucket,
   <type>)` -- la surcharge a DEUX arguments, sans `Nullable<Fix64>`. Son voisin immediat
   `...HeroicFusilladePlaybook$$EvaluateNonComparable` construit, lui,
   `System.Nullableu003C__Il2CppFullySharedGenericStructTypeu003E$$.ctor(&n, &statics[0])` PUIS
   `Bucket$$.ctor(bucket, 0, &n, <type>)`. La difference est LOCALE, pas un artefact de
   decompilation -- `MasterOfTheTutelaries`, `GrotTank`, `WarHowl`, `NovaCharge` et
   `CallRipperSwarms` sont tous du second cote.
2. **Le gate d'`AddAction`** : `if (!this.minUtility.HasValue) return true;` AVANT toute
   comparaison (deja lu par `#971`).
3. **La CLASSE ne declare que TROIS methodes** (`.ctor`, `EvaluateNonComparable`, `.cctor`) et un
   champ `private static readonly Fix64 MIN_UTILITY`. Liste des methodes DECLAREES prise au dump
   `Il2CppDumper` -- `ghidra/functions.tsv` ne prouverait rien, IL2CPP deduplique les corps
   triviaux.

Effet : `MIN_UTILITY = 1.0` -> `float("-inf")`. L'utilite de ce playbook est
`Somme(+50 par ennemi hors de sa portee) - 10 x Somme(distances)` : elle est NEGATIVE des que les
ennemis sont loin, donc le port REFUSAIT l'ability dans le regime le plus courant. C'est le no-op
silencieux exact d'`IronkinSteeljack` (#971), et l'observation live qui avait ouvert le residu
(`ncEvaluate` rend un `best` NEGATIF a chaque position) en etait deja la preuve.

⚠ **Le cliquet a MORDU des son premier passage** : son inventaire << les DEUX playbooks sans
borne >> etait FAUX -- il y en a **TROIS**. `1043 ThunderousAssault` est dans ce cas depuis #977
(surcharge de `Bucket<T>$$.ctor` a UN argument, voie
`NonComparablePlaybook<T>$$GenerateBucketWithMultipleStrategies`, classe sans `.cctor`). Le
commentaire du registre disait encore << SEUL playbook du registre SANS borne >> ; il est corrige.
C'est le genre d'inventaire qu'on ne peut pas ecrire de memoire.

## 2. `#433-r4-r1-r4-r2-r2` -- la premisse etait INVERSEE

Le residu accusait `heroic_fusillade` de << compter des voisins SANS elevation NI voisinage >>.
La lecture du call-site le REFUTE : **c'est le seul comportement correct**, et brancher les deux
canaux aurait ete la regression.

`IBattleQuery` slot **119** = `GetSurroundingUnits` (arite 3, `metadata/interface_slots.tsv`), avec
les litteraux `(<tuiles de la cible>, range = 1, includeCenter = 0)`. La famille descend a
`IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`, dont le corps
est une **triple boucle CUBE** (`x+y+z == 0`, `|d| <= range`) sur `StateExtensions$$GetTileAt` --
**aucune porte d'elevation**, **aucune liste d'adjacence stockee**. C'est l'exact CONTRAIRE
d'`IterateAdjacentTiles`, que mirrore `battle_query.is_adjacent`.

Le port passe donc a `hexgeo.distance(...) <= 1` ECRIT explicitement. **Value-preserving** :
`is_adjacent(t, p, None, None)` EST `hexgeo.distance == 1`. Ce qui change, c'est la PRIMITIVE
CITEE -- un futur lecteur qui << reparerait >> le site en y branchant les canaux le casserait, et
le cliquet l'en empeche desormais.

Bonus de la relecture de `BasePlaybook$$GetEligibleTargetsSelectable` : le champ `+0x38` de
l'`AbilityEntities` que ce call-site passe a `GetSurroundingUnits` est `GetTiles(entity)` --
l'EMPREINTE de la cible. Sur une cible multi-tuiles le natif verrait plus de voisins que le port,
qui n'a que la tuile principale. Ecart NOMME, aucun porteur du pool ne l'expose.

## 3. `#971-r4` -- l'ordre par position, en FOYER PARTAGE

Premisse RE-MESUREE et VRAIE : les ctors de `...GrotTankAbility$$.ctor`,
`...MasterOfTheTutelariesAbility$$.ctor` et `...IronkinSteeljackAbility$$.ctor` sont **identiques
octet pour octet** -- `TargetingOptions..ctor(&opts, 0, <TargetingRange statics>+0x30, 1, 0x1040,
0, 0)` puis `AActiveAbility..ctor(this, &opts, 2)`. Meme `onlyAdjacent`, meme masque
`TargetIsTile | TargetTileIsFree`, donc MEME chaine d'enumeration.

Le corps qui derivait l'ordre par position vivait sur `IronkinSteeljackPlaybook` seul. Il est
DEPLACE en `_base.tiles_in_native_order` et les TROIS l'empruntent -- recopier l'aurait fait
diverger au port suivant, ce qui est exactement pourquoi `#971-r4` existait apres `#971`.

L'ordre est ETABLI, pas suppose : `BasePlaybook$$GetEligibleTargetsSelectable` empile ses
`AbilityEntities` dans l'ordre EXACT de la liste que rend `IBattleQuery` slot 0x42 =
`GetValidTargets(caster, UnitPosition(possibleCasterTile), abilityType)`, apres un
`idun.shared.extensions.ListExtensions$$Remove` qui filtre EN PLACE -- aucun tri, aucun
`OrderedSet` intermediaire.

**CONFRONTE LIVE** : `test_971_summon_decision_live.py` 5/5, `test_grot_tank_live.py` 5/5,
`test_ironkin_steeljack_live.py` 3/3, `test_master_tutelaries_active_gate_live.py` +
`test_master_tutelaries_object_target_live.py` 12/12, et le walk d'Abraxas ci-dessous.

Residu **`#971-r5`** : aucun montage ne force un TIE d'utilite depuis une position de MOVE (le
seul regime ou l'ordre par position se distingue de l'union). L'ecart est ferme par LECTURE, pas
par mesure discriminante.

## 4. `#202-r1` -- un sommet a TUILE UNIQUE, et le natif y va

La fiche proposait deux gestes : << etablir l'ordre natif au decompile >> OU << crafter une
geometrie ou le sommet est UNIQUE >>. **Les deux sont faits.**

Le premier est le §3 ci-dessus. Le second : `probe_202r_decision_abraxas.py` accepte desormais une
LISTE de seeds (un runner vivant a la fois) et VENTILE le sommet en trois regimes -- sommet
UNIQUE, sommet ex aequo mais TUILE unique, sommet ex aequo sur plusieurs tuiles.

MESURE, board `MC1_67`, `thousInfernalMaster + thousSorcerer` vs 3 necrons :

| seed | sommet | couples | tuiles distinctes | verdict |
|---|---|---|---|---|
| 20203 | 141 | 7 | **2** -- `(2,4)` et `(3,5)` | ex aequo : accord COMPATIBLE, non probant |
| 777 | 151 | 4 | **1** -- `(2,4)` | **la CIBLE ne depend d'aucun tie-break** |

Sur la seed 777, pas 12, u83 : `pos native->(3,4) engine->(3,4) [EXACT]` **et**
`ABIL native(ab=1096,tgt=34) engine=ability(ab=1096,tgt=34) [MATCH]`. La tuile 34 est `(2,4)`,
seule tuile du sommet -- l'accord sur la CIBLE est donc PROBANT sans rien supposer.

Ce qui reste NON COUVERT, et qui est nomme : la POSITION `(3,4)` est l'une de QUATRE positions a
egalite ; le port la choisit par l'ordre de `ctx.reach_nc`, et le natif choisit la meme. Cet ordre
est celui de `BattleQuery$$GetCurrentAndMovablePositionsFor` (origine en tete), etabli ailleurs
(#76 / R1) et INDEPENDANT de l'ordre des tuiles de spawn qui faisait l'objet de ce residu.

## 5. `#1032-r1` -- les deux faces DECISION

### `1052 CallRipperSwarms` (`tyranBossHiveTyrantLeviathan`, npc)

Base LUE dans `frida/classes.tsv` : `CallRipperSwarmsPlaybook` derive de
`ABossSummonAbilityPlaybook`1`, elle-meme de `NonComparablePlaybook`1`. **La base intermediaire
porte du code que la classe fille n'a pas.**

Corps propre : `Bucket(0, Nullable(<statics[0]> = Fix64(1)))` puis une action par cible eligible a
l'utilite PLATE `Fix64(1)`. SELF-CAST (preset `<TargetingOptions statics>+0x280`, `isSelfCasting`,
`rules = 0x8004`), donc l'unique cible est le caster ; utilite plate -> `to = None` par keep-first.

`ABossSummonAbilityPlaybooku003Cobjectu003E$$GetUseProbability(unit)`, MIRROR :

    if (unit.GetComponent<BaseUnitComponent>().StartedTurns < 2)  return FIRST_TURN_PROBABILITY;
    n   = UnitExtensions$$GetChildren(unit, state, u => UnitExtensions$$IsAlive(u, state)).Count
    return Fix64(1) - (Fix64.FromIntFraction(8,10) * Fix64(n)) / Fix64(GetMaxSummons());

Trois lectures qui ne se devinent pas :

* le champ compare a `2` est `BaseUnitComponent.StartedTurns @+0x58` -- **le NOM du statique le
  dit** (`FIRST_TURN_PROBABILITY`, lu au dump), et l'offset le confirme : c'est le meme compteur
  que le corps folde `AlphaWarriorPlaybook$$ShouldEvaluate` (`GetStat(unit, 0xc) > 1`) interroge.
  `< 2` en est la NEGATION exacte, donc le port reutilise son substrat ;
* `GetChildren` prend un PREDICAT (`IsAlive`) : les depouilles ne comptent PAS. Contraste
  `UnitExtensions$$GetChildrenCount` (predicat NUL, liste append-only) que `DoctrinaImperatives`
  mirrore -- deux natifs voisins, deux semantiques ;
* **la formule ne rend JAMAIS `<= 0`** (`0.8 n / max <= 0.8`), donc ce mirror ne deplace AUCUN
  verdict. Il est porte parce que `p` est desormais CONFRONTABLE au capteur `shouldEvaluateTrace`.

`GetMaxSummons` delegue au corps DEDUPLIQUE etiquete `WaaaghAbility$$GetNumSummons` =
`GetNumberConstant(config, 0x10 = nrOfSummons)`. La cle est lue sur le gameconfig de **1052** (= 4),
surtout pas celui de `Waaagh` : le symbole ne designe que le corps.

⚠ Le natif monte CETTE MEME classe pour **1052, 1054 et 1055** (son `.ctor` prend l'id EN
PARAMETRE, contrairement a tous ses voisins). Le port n'inscrit que `1052` : `1054`/`1055` n'ont
aucune face COMBAT, et proposer une ability que le runner ignore est le no-op silencieux de #996.
Le cliquet garde CETTE premisse explicitement -- si elles entrent au registre COMBAT, il faut le
RE-ETALONNER.

### `1193 NovaCharge` (`tauBossRiptide`, npc boss)

    bucket = Bucket(0, Nullable(<statics[0]> = Fix64(1)))
    if (this.<+0x70> == null)  this.<+0x70> = NovaChargeAbility$$GetLineTiles(ability)
    foreach entities in GetEligibleTargetsSelectable(caster, casterPosition):
        lines = this.<+0x70>.Select(entities)
        util  = Fix64(CountEnemiesOnTiles(caster, lines) * 100 + lines.Count)
        bucket.AddAction(GenerateAction(casterPosition, entities.<+0x10>, util))

La classe pese **120 octets** (0x78) la ou ses voisines en font 112 : c'est ce champ `+0x70`, et
`$$ResetCaches` le remet a `null`. C'est un cache d'ARBRE, pas de RESULTAT -- `Select` est
re-evalue par cible, et c'est ce qui rend l'utilite dependante de la cible.

`Playbook<T>$$CountEnemiesOnTiles(caster, tiles)` (relu) : l'OCCUPANT de chaque tuile
(`UnitExtensions$$GetUnit`), compte s'il n'est PAS ami (`IBattleQuery` slot 146 `AreFriends`).
Meme residu nomme que `NovaShield` : `AreFriends` est a trois etats cote natif, le port ne connait
que `ctx.epos`.

**AUCUN terme de mouvement** -- contraste `NovaShieldPlaybook`, qui en a DEUX
(`GetMovementUtility(Tile)` + `DislikeStartingTiles`). Deux playbooks freres du meme boss, deux
formules.

Les deux gates AMONT :

* `$$ShouldEvaluate` : `IBattleQuery` slot **27** = `HasMinimumRemainingTurns(unit, 2)` PUIS
  `BasePlaybook$$ShouldEvaluate` -- **le seul des deux qui REFUSE** ;
* `$$GetUseProbability` : `CanCurrentlyUseAbility(unit, 0x4aa)` ? `<Fix64 statics>+0x30` :
  `<Fix64 statics>+0x20`. Les deux statiques sont LUS dans `FixMath.NET.Fix64$$.cctor` --
  `+0x20 = 0x100000000` = **One**, `+0x30 = op_Division(0x100000000, 0x200000000)` = **Half**.
  `0x4aa = 1194 NovaShield` est l'ability **SOEUR**, pas celle du playbook : le Riptide met la
  piece en l'air tant qu'il garde son bouclier en reserve, et devient deterministe quand il l'a
  depense.

La GEOMETRIE reste le foyer de la face COMBAT : `tau.nova_charge_line_tiles` est PARAMETRE
(`target_sel`, defaut `Target()`) et la face DECISION lui passe `FixedTileIds([<tuile visee>])` --
le montage exact de `macro_plasma_incinerator_target_area_tiles` (#1066). Un second mirror aurait
fait diverger les deux faces sur les trois lignes, EN SILENCE.

**Residu `#1032-r6`** : les deux ports sont MIRROR-OFFLINE. Les porteurs sont des BOSS npc,
montables par `--explicit-stats` sur leur carte dediee ; `1193` est en outre GREFFABLE (precedent
mesure : `1194 NovaShield` sur `tauCrisis`, `case-92` §5bis, greffe qui avait trouve un bug de
port).

## 6. `#456-r2-r1` -- le critere de `FilterMovementTiles`, TRANCHE

Deux phrases de `savior_protocols.py` etaient FAUSSES et sont retirees :

* << INERTE sur le porteur >> -- vrai des six porteurs NATURELS, faux du montage : greffe sur un
  porteur de MELEE, le filtre RETIRE des tuiles (mesure `#456-r2`) ;
* << NON tranche faute d'un second call-site nomme >> -- le critere se lit ENTIEREMENT dans le
  corps.

    if (HasRangedWeapon(unit, null))  return;                          // COURT-CIRCUIT TOTAL
    trigger = SaviorProtocolsAbility$$TargetIsValidTrigger(ability)
    for (i = Count - 1; i >= 0; i--)
        if (!Any(query.<slot 119 = GetSurroundingUnits>(tiles[i], 2, includeCenter: false),
                 u => trigger.ShouldTrigger({Target: u, Owner: unit})))
            toRemove.Add(tiles[i])
    if (toRemove.Count == tiles.Count)  return;                        // ANTI-VIDAGE
    ListExtensions.RemoveRange(tiles, toRemove)

QUATRE lectures, dont deux REFUTENT la prediction de `case-443-r1` §5 :

1. **le rayon est GEOMETRIQUE** (meme slot 119, meme triple boucle cube qu'au §2) -- pas la liste
   d'adjacence stockee, que la face MOVE de CE MEME playbook utilise pourtant (slot 0x7a). Deux
   slots, deux geometries, une seule classe ;
2. `includeCenter = 0` : la tuile candidate elle-meme est EXCLUE du disque ;
3. **il y a bien une CONDITION DE PLUS**, et c'est `TargetIsValidTrigger` -- `AreFriends & 
   HasFaction(Tau) & !ActorHasTriggeredAbility(1120) & !AreEqual`. C'est ce qui explique la mesure
   de `#456-r2` : `(0,3)` et `(1,3)` ont toutes deux `ultraTitus` a `d = 2`, mais << un protegeable
   dans le rayon >> ne suffit pas -- il faut un protegeable **VALIDE** ;
4. **l'ANTI-VIDAGE** est un cran a part : si TOUTES les tuiles tombaient, le natif n'en retire
   AUCUNE. L'oublier immobiliserait le mover.

Livre : `SaviorProtocolsPlaybook.filter_movement_tiles`, mirror EXECUTABLE, garde par l'etage 6 du
cliquet (6 tests). **Aucun appelant ne le consomme encore** : le natif l'applique PAR ABILITY dans
`ABaseAiUnitTactic$$GenerateActionTiles`, la ou le port n'a qu'une liste de positions PARTAGEE
(`ai.context.action_tiles_for`, qui NOMME deja ce hook). `#443-r1b` est donc reduit au seul
CABLAGE.

## 7. `#585-r2` -- premisse REFUTEE

La fiche annonce << `WarHowlPlaybook` existe et n'est pas porte >>. Il l'est depuis `e34af43e`
(#969), et son `GetUseProbability` -- palier compris -- depuis `7361747f` (#969-r1). La fiche
n'avait jamais ete fermee.

Le palier relu sur le build courant confirme le port au caractere pres :

    if (iVar14 < 3) { if (iVar14 == 1) uVar6 = 0x4b; else uVar6 = 0x32; } else uVar6 = 100;

soit `n = 0 -> 50`, `n = 1 -> 75`, `n = 2 -> 50`, `n >= 3 -> 100`. **`2` vaut MOINS que `1`.** Le
port transcrit tel quel, et l'etage 7 du cliquet FIGE les quatre valeurs -- creux compris. Le
mutant M8 (`n == 2 -> 62`, l'interpolation tentante) mord.

## 8. Validation

**Offline** : `test_10037_...` 27/27 ; 8/8 mutants mordent. Rejoues sans regression :
`test_433r4r1r4r2r1r1r1_selecteur_spawn`, `test_924r1_early_warning_override`,
`test_971r1_nearest_enemy_foyer`, `test_433_r4_r2_adjacency_foyer`,
`test_969_effect_buff_decision_faces`, `test_969r1_use_probability`,
`test_master_tutelaries_object_or_steppable`, `test_570r5_ordre_de_seeding`,
`test_1077_firing_position_mischief_makers`, `test_287r12_role_target_tuile`,
`test_270r1r1_container_enum`, `test_287r11r1_regles_ciblage`,
`test_barbed_ovipositor_object_or_steppable`, `test_447r1r1r3r1_has_moved`,
`test_433r4r2r4r1_channel_counterproof`, `test_1015r1_close_combat_weakness`.

**UN test a du etre RE-ETALONNE**, et c'est DIT ici, pas passe sous silence :
`test_433_r4_r2_adjacency_foyer_offline.py::test_early_warning_emitted_action_changes_with_the_gate`
attendait `on == []`
en s'appuyant sur `MIN_UTILITY = 1` -- la premisse que le §1 refute. Le DISCRIMINANT du test (la
porte d'elevation BASCULE le consommateur d'une branche a l'autre, et cela se lit sur l'action
EMISE) est INCHANGE ; seule la valeur attendue du bras `on` passe de << rien >> a << l'action a
l'utilite de la branche A >> (`-10 x d` a la meilleure position). C'est la difference entre un
test qui garde une MECANIQUE et un test qui avait fige un SEUIL faux.

**Registres** : `probe_1021_face_decision_au_registre` OK (les deux lignes de dette 1052/1193
RETIREES -- le CRAN A prend le relais) ; `probe_181` 182/182 ; `probe_120` etape 0 << litteral de
ctor manquant : aucun >> ; `test_ability_registry_ratchet` 10/10 ; `probe_313`, `probe_365`,
`probe_273 --only-scan`, `probe_485`, `probe_486r2`, `probe_433_r1_identity_shortcircuit` verts.

**Live** : `test_971_summon_decision_live` 5/5, `test_grot_tank_live` 5/5,
`test_ironkin_steeljack_live` 3/3, `test_master_tutelaries_active_gate_live` +
`test_master_tutelaries_object_target_live` 12/12 ; `probe_202r` sur trois geometries.

**Ce qui n'est PAS couvert** :

* la confrontation LIVE des deux faces `#1032-r1` (`#1032-r6`) ;
* un TIE d'utilite depuis une position de MOVE pour les trois ring-1 (`#971-r5`) ;
* la POSITION du sommet d'Abraxas reste un ex aequo a quatre (§4) ;
* le CABLAGE de `filter_movement_tiles` (`#443-r1b`) ;
* pour `1193`, la geometrie du sweep sur un caster a SEPT tuiles : `CasterTile` n'en garde que la
  MAIN TILE (`#459-r1`, structurel), et `CenterTiles` d'une liste a un element rend cet element.
