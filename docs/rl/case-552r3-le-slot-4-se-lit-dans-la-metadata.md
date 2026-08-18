# #552-r3 -- le slot 4 se lit dans la METADATA (et trois autres residus du foyer `noncomparable/`)

Tranche de QUATRE residus partageant le repertoire `engine/playbook/noncomparable/` : `#1033-r2`,
`#552-r3`, `#942-r3`, `#971-r5`. Le fait neuf qui porte la tranche est le §2 -- une voie de mesure
qui rend OFFLINE et DEFINITIF ce que la doctrine posait comme << a trancher en LIVE >>.

Fiches d'origine : `docs/rl/backlog.md`. Faces COMBAT : `case-1033-reveal-...`, `case-942-...`,
`case-10037-playbooks-noncomparable.md` §3.

---

## 1. `#1033-r2` -- `RevealPlaybook` porte, et la borne du `Bucket` RELUE

Corps relu sur le build `t6dpr4k06g` (`IdunBattle.AI.Playbook.Loki.RevealPlaybook$$
EvaluateNonComparable`), pas recopie de la fiche :

    bucket  = new Bucket<UnitAction>(0, Nullable(<statics[0]> = Fix64.op_Implicit(1)))
    targets = BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition.MainTile)
    foreach (e in targets)
        if (BasePlaybook$$WillNormalAttackKill(caster, e.<+0x10 Target>,
                                               casterPosition.MainTile))  continue;
        bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, e.<+0x10 Target>,
                                                      Fix64.op_Implicit(1)))

`.ctor` -> `0x453` = 1107 ; `.cctor` -> `statics[0] = Fix64(1)`. Le `.ctor` decompile NOMME
`ComparablePlaybook<T>..ctor` -- corps gshared DEDUPLIQUE, donc mislabele : ce qui range 1107 du
cote NonComparable est sa METHODE PROPRE. Port : `engine/playbook/noncomparable/reveal.py`.

**LE POINT QUI POUVAIT TUER LE PORT EN SILENCE.** L'utilite est la CONSTANTE `Fix64(1)`, donc
EGALE a `MIN_UTILITY`. Le gate a donc ete LU au lieu d'etre suppose :
`Bucket<T>$$AddAction` -> son helper `FUN_18004ed00` fait
`Nullable.HasValue == false -> accepte tout`, sinon
`action.Utility >= minUtility.Value` (`op_GreaterThanOrEqual`). C'est un `>=` : le candidat SORT.
Lire ce gate en `>` strict aurait produit un playbook a **zero candidat, sans une erreur** --
exactement le no-op d'`IronkinSteeljack` (#971). Le meme corps confirme au passage l'autre bout :
le remplacement dans le bucket est un `op_GreaterThan` STRICT, donc a utilite plate c'est la
PREMIERE paire (position, cible) enumeree qui gagne -- et l'ordre des positions commence par
l'ORIGINE.

Le gate `WillNormalAttackKill` est POSITIONNEL (il predit la normale depuis la tuile candidate),
donc l'utilite plate ne rend PAS le playbook position-independant : une cible sure-kill depuis
l'origine peut ne plus l'etre depuis une tuile de move, et le natif bouge alors.

La ligne de dette `1107` est RETIREE de `probe_1021.DETTE` : c'est ce qui la fait tomber sous le
CRAN A, donc ce qui la protege desormais. `probe_1021` rend `PORTEE / PLAYBOOKS`.

⚠ **Ce que ce port ne peut PAS encore confronter, et ce n'est pas son fait** : le gate DYNAMIQUE
de la face COMBAT (`RevealAbility$$GetDynamicInvalidTargetReason`) refuse encore toute cible en
regime pourtant favorable -- residu `#1033-r4`, etage `UnitExtensions$$IsFriend` sur une unite
MORTE non lu. Tant qu'il refuse, `GetEligibleTargetsSelectable` rend une liste VIDE et les deux
faces s'accordent sur le VIDE : un accord en regime DEGENERE, donc pas une confirmation. C'est
dit, pas maquille.

---

## 2. `#552-r3` -- la mesure que la fiche demandait en LIVE se fait OFFLINE, et elle est DEFINITIVE

La fiche posait : << lire le slot 4 de la vtable de `MindControlPlaybook` sur une instance
materialisee et le comparer a l'adresse de `BasePlaybook$$ShouldEvaluate` >>. C'etait la seule
voie connue, pour une raison juste : les DEUX tables (`frida/methods.tsv`, `ghidra/functions.tsv`)
sont indexees par ADRESSE et IL2CPP DEDUPLIQUE les corps, donc << la classe n'expose que trois
symboles >> ne prouve RIEN -- c'est ainsi que le slot 4 de `VexillaMagnificaPlaybook` avait ete
rate puis retrouve LIVE (#46).

**LA VOIE QUI TRANCHE.** `global-metadata.dat` ne decrit pas des CORPS mais des DEFINITIONS : le
`Il2CppTypeDefinition` porte `methodStart`/`methodCount`, la liste des methodes qu'un type
DECLARE. La deduplication est un phenomene du LINKER (ICF), **posterieur** : elle ne peut rien y
effacer. Le depot sait deja lire cette table (`il2cpp_metadata.MetadataReader.type_methods`,
employe par `probe_10015` et `probe_175r2`). La question devient binaire et offline.

**MESURE** (`probe_552r3_slot4_declare.py`, build `t6dpr4k06g`) :

    IdunBattle.AI.Playbook.Loki.MindControlPlaybook  declare  {.ctor, .cctor, EvaluateNonComparable}

Ni `ShouldEvaluate`, ni `GetUseProbability`. Le slot 4 est donc `BasePlaybook$$ShouldEvaluate`
(= `GetUseProbability >= 1` = True constant), et c'est ce que le port rend depuis #552. **Le port
etait juste ; il ne l'etait pas MESURE.**

**LE TEMOIN, sans lequel la voie ne vaut rien.** Un critere qui rendrait << pas de surcharge >>
partout donnerait la MEME reponse et serait entierement faux. L'etage 1 du probe le confronte
donc a HUIT playbooks dont le verdict est etabli PAR AILLEURS, **dans les deux polarites** :

| classe | attendu | source de l'attente |
|---|---|---|
| `VexillaMagnificaPlaybook` | surcharge | **LIVE #46** -- slot 4 resolu a la vtable |
| `HammerOfWrathPlaybook` | surcharge | decompile : `!EnemyWillBeKilledWithNormalAttack` |
| `AlphaWarriorPlaybook` | surcharge | decompile : `GetStat(unit, 0xc) > 1` (corps COMDAT) |
| `NovaChargePlaybook` | surcharge | #1032-r1 : `HasMinimumRemainingTurns(unit, 2)` |
| `EuphoricStrikesPlaybook` | aucune | **LIVE probe_974** -- `pbGate(slot 4)` = True a `turnsStarted == 1` |
| `BlackRagePlaybook` | aucune | decompile : la modulation est dans `GetUseProbability` (0.4) |
| `ItItchesPlaybook` | aucune | decompile : idem |
| `WaaaghPlaybook` | aucune | #971-r2 : `p = 0.05 x ts x nB`, CONFRONTE live |

**8/8 concordants, 4 contre 4.** Trois de ces attentes viennent d'une mesure LIVE independante,
dont celle du cas #46 qui MOTIVE la fiche. L'etage 1 exige aussi la BILATERALITE (>= 3 de chaque
cote) : un temoin unilateral ne discrimine rien, et c'est le mutant `MC` de la contre-epreuve.

**PORTEE, dite a chaque run** : le probe ne lit pas le CORPS du `ShouldEvaluate` qu'il trouve, et
il n'etablit pas que la declaration EST le slot 4 d'`IPlaybook` (un homonyme suffirait) -- au-dela
des huit temoins, c'est une BORNE SUPERIEURE de surcharge.

Corollaire, et il vaut au-dela de cette tranche : **le meme geste repond desormais a toute
question de la forme << telle classe surcharge-t-elle telle methode ? >>**, sans capteur, sans
fenetre de reinject, et sans le faux negatif de la deduplication.

---

## 3. `#552-r4` -- ce que la meme mesure OUVRE, et le BUG qu'elle a deja fait tomber

Applique aux **98** playbooks portes, le critere rend d'abord **20 ecarts** entre ce que le port
surcharge (`should_evaluate` / `use_probability`) et ce que la chaine native DECLARE. Ils ne sont
**pas** rendus rouges, et c'est mesure : une partie est un GAP ASSUME et documente au site (une
porte ALEATOIRE que le moteur deterministe ne modelise pas -- `BlackRage`, `ScarabSummon`,
`EmpyricAmbush` l'ecrivent noir sur blanc), une autre un `GetUseProbability` dont la valeur
constante `>= 1` rend le port EXACT malgre l'absence de surcharge. Un cliquet qui rougirait sur
les vingt se ferait desarmer.

Le coeur du residu : **CINQ classes natives DECLARENT `ShouldEvaluate`** alors que le port ne
surchargeait rien -- `1039 RitesOfRestoration`, `1140 ExemplarOfHate`, `1192 NovaBoost`,
`1194 NovaShield`, `1223 ReanimationBeam`. Trois d'entre elles ne mentionnaient meme pas
`ShouldEvaluate` dans leur module : personne n'avait regarde.

### 3bis. DEUX des cinq sont PORTEES par cette tranche (20 ecarts -> 18)

Les corps de `NovaBoostPlaybook$$ShouldEvaluate` et `NovaShieldPlaybook$$ShouldEvaluate` sont
IDENTIQUES entre eux, et IDENTIQUES a celui de `NovaChargePlaybook` (1193), deja porte par
`#1032-r1` -- trois abilities du meme kit Riptide :

    if (!<IBattleQuery slot 0x1b = 27 = HasMinimumRemainingTurns>(unit, 2))  return false;
    return BasePlaybook$$ShouldEvaluate(unit);

Le slot est RESOLU (`metadata/interface_slots.tsv` : `IBattleQuery 27 HasMinimumRemainingTurns
2 params`) et son ARITE concorde avec les deux arguments du call-site. Le pont de substrat existe
deja (`_base.has_minimum_remaining_turns`, `#1027-r5`), donc le port tient en quatre lignes par
classe.

⚠ **UNE RAISON ECRITE MAIS NON MESUREE AVAIT FIGE LE TROU.** `nova_boost.py` portait, sous
l'etiquette `N1`, << gate `query.slot0x1a(unit,2)` (precondition Nova, prob. charge) NON
modelise >>. `0x1a` = 26 = `ShouldPlayerSkipTurn`, qui prend **UN** parametre : l'arite l'exclut.
La note nommait donc le mauvais slot ET donnait une semantique inventee -- et, en donnant
l'impression que quelqu'un avait regarde, elle decourageait la verification. C'est le vice que le
CLAUDE.md decrit pour les imports differes, transpose ici.

⚠ **LES TROIS NE SONT PAS INTERCHANGEABLES SUR LE SECOND ETAGE**, et le cliquet a MORDU dessus a
son premier passage : la metadata declare `GetUseProbability` sur `NovaCharge` SEUL. Recopier
l'etage d'une soeur a l'autre aurait ajoute une probabilite que le natif n'a pas.

### 3ter. Les TROIS qui restent, et pourquoi elles ne se lisent pas de la meme facon

* **`1039 RitesOfRestoration`** -- corps LU :
  `RitesOfRestorationAbility$$GetPossibleResurrectTargets(this.<+0x68>)` puis un selecteur
  (`Count > 0`). C'est-a-dire << y a-t-il au moins une unite ressuscitable ? >>. Portable, mais son
  substrat (`obs_units` + le selecteur de resurrection) demande une lecture propre.
* **`1140 ExemplarOfHate` et `1223 ReanimationBeam`** -- **Ghidra ne nomme AUCUN corps sous ces
  noms** alors que la metadata les DECLARE. C'est la deduplication a l'oeuvre, et c'est exactement
  le regime que le §2 explique : leur corps est FOLDE sur celui d'une autre classe. Les lire exige
  soit de resoudre `rid -> VA` (comme `probe_10015`), soit un `pbGate(slot=4)` live. **Ne pas
  conclure de cette absence.**

L'etage 3 du probe imprime l'inventaire a chaque run (`--inventaire` pour la liste complete).

---

## 4. `#942-r3` -- le gate de `1210` BASCULE

`...ExemplarOfTheMontkaPlaybook$$ShouldEvaluate` surcharge DIRECTEMENT le slot 4 (confirme au §2 :
la metadata le DECLARE, avec son auxiliaire `HasNormalAttackTarget`), donc **sans tirage
aleatoire** : c'est le cas rare ou le port peut etre EXACT, et donc ou une divergence serait un
vrai bug. Le corps ne dit pas ce que son nom dit -- << ai-je une cible que mon attaque normale NE
TUE PAS ? >>, la negation est dans la boucle.

**RE RE-LUE sur `t6dpr4k06g`** (le module citait `rnca9r7q6c`) -- les deux corps sont inchanges :

    ShouldEvaluate(this, unit)  =>  return HasNormalAttackTarget(this, unit);

    HasNormalAttackTarget(this, unit) :
        naType = UnitExtensions$$GetNormalAttackType(unit)
        res    = <IBattleQuery slot 0x45>(this.<+0x28 Query>, unit, naType, false)
        foreach (kv in res.<+0x18> as Dictionary<UnitPosition, List<IEntity>>)
            foreach (target in kv.Value)
                if (!BasePlaybook$$WillNormalAttackKill(this, unit, target,
                                                        kv.Key.get_MainTile()))
                    return true
        return false

⚠ Detail qui compte pour la MESURE et pas pour le port : **le slot 4 prend UN parametre**
(`unit`). Le probe lit l'arite dans `pbSlots(...).slots[4].params` au lieu de la supposer --
passer zero argument ferait lire le `MethodInfo*` comme si c'etait l'unite. (`probe_974` invoque
ce slot avec `args: []` ; sur `EuphoricStrikes` le verdict tient quand meme, la base rendant
`Fix64(1)` sans lire `unit` -- mais la mesure y est plus faible qu'elle n'en a l'air.)

Montage : `probe_942r3_montka_gate_live.py`. `tauFarsight` est HORS POOL -> injection catalogue.
Deux regimes, meme board, meme placement, meme roster, **seuls les PV des a-units changent** :
`--hp-target 1` (toute cible sure-kill -> natif attendu `False`) contre `--hp-target 400000`
(natif attendu `True`). Deux controles, tous deux bloquants :

* **TEMOIN** -- `abilityTargets(uid, <attaque normale>)` doit publier au moins une cible dans les
  DEUX regimes. Sans lui, un `False` en A viendrait peut-etre d'une liste VIDE, pas du sure-kill ;
* **NON-DEGENERESCENCE** -- le gate natif doit RENDRE DES VALEURS DIFFERENTES entre A et B. Deux
  mesures identiques sont un ECHEC meme si le port les reproduit : un gate qui ne bascule pas ne
  discrimine rien.

**RESULTAT : CONFRONTE, LE GATE BASCULE, LE PORT SUIT DANS LES DEUX SENS.** Runner MC1_67/777,
`tauFarsight` injecte au catalogue, `orksNob` place en (5,5) face au caster en (4,5) :

| regime | `--hp-target` | cibles d'attaque normale | natif (slot 4) | port | verdict |
|---|---|---|---|---|---|
| A sure-kill | 1 | **2** | `False` | `False` | OK |
| B survivant | 400000 | **2** | `True` | `True` | OK |

`pbSlots` confirme au passage la classe chargee (`ExemplarOfTheMontkaPlaybook`), le nom du slot 4
(`ShouldEvaluate`) et son ARITE (`params=1`) -- c'est cette arite que le probe LIT au lieu de la
supposer.

Les deux controles passent : le TEMOIN est non vide **dans les deux regimes** (2 cibles), donc le
`False` de A vient bien du sure-kill et pas d'une liste vide ; et le gate BASCULE (`False -> True`),
donc l'accord porte sur un regime **DISCRIMINANT**, pas sur un regime degenere.

⚠ Premier tir bloque par un cap de runners sature -- ventilation par PROPRIETAIRE : 45 des 50
appartenaient au worktree de merge (`merge-tmp3`), pas a une concurrence d'agents. Purge par
l'orchestrateur, puis mesure. C'est cette ventilation qui a evite de chercher du mauvais cote.

---

## 5. `#971-r5` -- le TIE depuis une position de MOVE

`_base.tiles_in_native_order` (foyer partage des trois playbooks de spawn ring-1) ne se distingue
de l'ordre de l'UNION que dans UN regime : un TIE d'utilite depuis une position de MOVE. A
l'ORIGINE le port lit `fromHere`, qui EST la reponse par-position du RPC ; hors TIE, l'utilite
tranche seule. `#971-r4` fermait donc l'ecart par LECTURE (trois ctors identiques octet pour
octet), pas par mesure.

Montage : `probe_971r5_ordre_par_position_live.py`. Il **cherche** le regime au lieu de l'esperer
-- balayage des positions de move, retenue de celles ou (a) >= 2 tuiles de spawn sont a utilite
MAXIMALE EGALE et (b) l'ordre STOCKE et l'ordre de l'UNION ne designent pas la meme tuile parmi
les ex aequo -- puis confronte la PARTITION des positions par cible a `ncEvaluate --sweep`
(`action.targetLow` est le bas d'un POINTEUR d'entite : opaque mais STABLE, donc la partition se
compare, pas la valeur).

**LE SECOND BRAS EST CE QUI FAIT LA MESURE** : dans le MEME etat, le meme port avec
`tiles_in_native_order` degenere en `list(union)` doit rendre une partition DIFFERENTE. Un accord
sans ce bras ne prouverait rien -- c'est precisement le reproche de `#971-r5`.

⚠ Detail qui aurait rendu la contre-epreuve INERTE : `grot_tank.py` lie le foyer en **FORME A**
(`from ._base import tiles_in_native_order`), donc substituer `_base.tiles_in_native_order` ne
mord PAS. Le probe substitue l'attribut du module CONSOMMATEUR.

**RESULTAT : REGIME ATTEINT, ORDRE PAR POSITION CONFIRME, ORDRE DE L'UNION REFUTE DANS LE MEME
ETAT.** Runner MC1_67/4242, `orksBigMek` en (4,5), `orksNob` en (5,5) :

* **29 positions de MOVE balayees, 13 DISCRIMINANTES** -- (3,5), (5,7), (6,6), (6,5), (4,3),
  (3,4), (2,4), (5,8), (4,7), (3,3), (2,3), (1,5), (1,6). Sur chacune, >= 2 tuiles de spawn sont a
  utilite MAXIMALE EGALE **et** les deux ordres designent des tuiles differentes -- par exemple en
  (5,7) : 5 ex aequo a l'utilite 3, l'ordre STOCKE donne (5,8), l'ordre de l'UNION donne (4,7) ;
* **PARTITION native = 18 classes**, reproduite **EXACTEMENT** par le port avec l'ordre STOCKE ;
* le meme port avec `tiles_in_native_order` degenere en `list(union)` rend **14 classes** --
  une partition DIFFERENTE, donc l'ordre de l'union est REFUTE par la mesure, pas seulement par la
  lecture.

⚠ **LA RECHERCHE DU REGIME N'ETAIT PAS DECORATIVE.** Le premier montage (`C3_14`/4242, le board a
15 tuiles `Bridge` que `#971-r4` avait employe) balaie 6 positions de move et n'en produit
**AUCUNE** discriminante : partout les deux ordres s'accordent. Un probe qui aurait suppose le
regime au lieu de le CHERCHER aurait rendu un vert sur ce montage-la, et ce vert n'aurait rien
prouve -- c'est exactement ce que `#971-r5` reprochait a la tranche precedente. Deux autres
montages `C3_14` ont ete refuses au placement (`placement REFUSE: orksBigMek @(3,4)` -- tuile hors
du `SpawnPointGroup`), ce qui est dit et non maquille.

Ce que ce resultat FERME : la transposition de `#971-r4` (le foyer partage) n'est plus soutenue
seulement par << les trois ctors sont identiques octet pour octet >>, elle est **mesuree sur le
consommateur** dans le seul regime ou elle se distingue.

---

## 6. Validation

**Ce qui est MESURE**

| etage | mesure | resultat |
|---|---|---|
| `#1033-r2` corps natif | `RevealPlaybook$$EvaluateNonComparable` / `.ctor` / `.cctor`, build `t6dpr4k06g` | relu, mirror 1:1 |
| `#1033-r2` gate du Bucket | `Bucket<T>$$AddAction` + `FUN_18004ed00` | `>=` (inclusif), remplacement `>` STRICT |
| `#1033-r2` registre | `probe_1021_face_decision_au_registre.py` | `1107 Reveal PORTEE PLAYBOOKS` ; CRAN A/B/C OK |
| `#1033-r2` cliquet | `test_1033r2_reveal_decision_offline.py` | 8 passed |
| `#1033-r2` mutants | `probe_1033r2_mutants.py` | **8/8 MORDENT** |
| `#552-r3` verdict | `probe_552r3_slot4_declare.py` | temoin **8/8**, bilateral 4/4 ; MindControl et Reveal declarent `{.ctor, .cctor, EvaluateNonComparable}` |
| `#552-r3` mutants | `probe_552r3_mutants.py` | **3/3 MORDENT** |
| `#552-r4` gates Nova | `ShouldEvaluate` de 1192 / 1194 vs 1193, build `t6dpr4k06g` | corps IDENTIQUES ; slot 27 resolu par `interface_slots.tsv` |
| `#552-r4` cliquet | `test_552r4_gate_nova_remaining_turns_offline.py` | 4 passed (a MORDU au 1er passage) |
| `#552-r4` mutants | `probe_552r4_mutants.py` | **5/5 MORDENT** |
| `#552-r4` effet | `probe_552r3_slot4_declare.py --inventaire` | ecarts **20 -> 18** |
| `#942-r3` RE | `ShouldEvaluate` + `HasNormalAttackTarget`, build `t6dpr4k06g` | relus, inchanges ; slot 4 d'arite 1 |
| `#942-r3` LIVE | `probe_942r3_montka_gate_live.py`, MC1_67/777 | gate BASCULE `False -> True`, port **2/2 OK**, temoin 2 cibles dans les deux regimes |
| `#971-r5` LIVE | `probe_971r5_ordre_par_position_live.py`, MC1_67/4242 | **13 positions discriminantes** ; partition natif 18 classes == port STOCKE ; port UNION 14 classes (**REFUTE**) |

**Non-regression rejouee** (offline, apres l'entree de 1107 au registre) :
`test_10037_playbooks_noncomparable_offline`, `test_979_ports_decision_offline`,
`test_985_faces_decision_offline`, `test_945_loki_decision_faces_offline`,
`test_957_decision_faces_offline` (106 passed) ;
`test_967_mow_decision_faces_offline`, `test_969_effect_buff_decision_faces_offline`,
`test_976_lot_astartes_astra_offline`, `test_566r1_sure_kill_gate_offline`,
`test_1210_exemplar_of_the_montka_offline`, `test_1033_reveal_offline` (116 passed) ;
`test_462_r4b_substrat_mort_appelants_offline` (15 passed) ; `probe_181_targeting_gaps` (0
manquante sur 182).

**CE QUI N'EST PAS COUVERT, nomme**

* **`#971-r5` : la mesure porte sur `GrotTank` (1057) SEUL.** Les deux autres emprunteurs du foyer
  (`1152 MasterOfTheTutelaries`, `1219 IronkinSteeljack`) ne sont pas re-confrontes ici -- ce qui
  est mesure, c'est le FOYER, sur un consommateur, dans le regime discriminant. La transposition
  aux deux autres reste soutenue par les ctors identiques octet pour octet.
* **`#971-r5` : un seul couple (board, seed) porte le regime.** `C3_14`/4242 ne le produit PAS, et
  deux montages `C3_14` ont ete refuses au placement. La discipline << au moins deux couples >>
  n'est donc pas tenue pour CE regime-la.
* **`#942-r3` : la carte `{position: cibles}` du slot `0x45` reste non publiee.** Le port itere
  l'UNION et reconstruit les positions par `castFromTiles` -- borne INF nommee dans le module, que
  cette mesure n'exerce pas (les deux regimes ont la meme geometrie).
* **`#1033-r2` n'a AUCUNE confrontation live**, et n'en aura pas tant que `#1033-r4` tient : le
  gate dynamique de la face COMBAT rend `GetEligibleTargetsSelectable` VIDE, donc les deux faces
  s'accordent sur le vide. C'est un accord DEGENERE, pas une validation.
* **Le §2 n'etablit pas que la declaration EST le slot 4** d'`IPlaybook` -- hors des huit temoins,
  c'est une BORNE SUPERIEURE de surcharge. Le probe l'imprime a chaque run.
* **Les 18 ecarts restants du §3 ne sont pas lus** : c'est `#552-r4`. Trois d'entre eux sont des
  gates AMONT natifs que le port ignore encore, et DEUX (`ExemplarOfHate`, `ReanimationBeam`)
  n'ont aucun corps nomme par Ghidra -- leur lecture demande `rid -> VA` ou du live.
* **Les deux gates Nova portes ne sont CONFRONTES QUE OFFLINE.** Leur porteur natif est
  `tauBossRiptide` (npc), et le regime discriminant (une BC portant reellement un plafond de
  tours) n'a pas ete joue live -- meme cause que le §4. Ce qui est mesure, c'est que les trois
  corps natifs sont identiques et que le gate porte MORD dans les deux sens sur le substrat.
* **Aucune couverture generee n'a ete regeneree** (ni `refresh_audits.py`, ni `probe_603 --index`).
  L'entree de `1107` au registre `PLAYBOOKS` fait bouger la couverture DECISION : a regenerer au
  MERGE.
