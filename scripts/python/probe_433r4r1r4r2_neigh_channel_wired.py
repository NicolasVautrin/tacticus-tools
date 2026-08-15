"""#433-r4-r1-r4-r2 -- CLIQUET : le substrat de VOISINAGE NATIF est branche partout ou le port
declare le mirrorer.

CE QU'IL EST SEUL A VOIR
------------------------
`battle_query.is_adjacent` porte DEUX etages du natif
(`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`) : l'ENUMERATION
de la liste STOCKEE (`neigh_by_pos`) puis la PORTE d'elevation (`elev_by_pos`). Les deux sont des
parametres OPTIONNELS, donc un call-site qui en oublie un degrade **en silence** -- ni erreur, ni
crash, juste un predicat plus PERMISSIF que le natif. C'est exactement la signature de degradation
de `TARGETING_OPTIONS` (cf. `CLAUDE.md`), et le seul gisement que notre propre cadence de portage
alimente : chaque nouveau playbook qui compte des voisins peut le rouvrir.

MESURE qui justifie le cliquet (`probe_433r4r1r4r2_is_adjacent_substrat_live.py`) : la couronne hex
sur-atteint la liste stockee de **4** aretes dirigees sur `C1_74` et **38** sur `C3_14`, pour **0**
arete dans l'autre sens -- un ecart strictement PERMISSIF.

DEUX ETAPES, et la seconde existe parce que la premiere ne peut pas voir son gisement
-------------------------------------------------------------------------------------
* **ETAPE 1 -- l'invariant de COUPLE sur les call-sites.** « Un call-site qui a su fournir
  l'elevation a forcement un porteur de contexte sous la main, donc il peut fournir le voisinage. »
  Un call-site qui ne passe NI l'un NI l'autre est hors gisement (arbre purement numerique, test
  unitaire) et n'est pas compte.

  ⚠ La detection RESOUT l'import, elle ne compare pas des noms (#433-r4-r1-r4-r2-r1). Un
  `bq.is_adjacent(...)` etait vu, mais pas un appel en nom NU ni sous ALIAS -- or la face PREDICTION
  n'importe QUE sous alias (`from ..battle_query import is_charging as bq_is_charging`), et les
  foyers de `battle_query.py` s'appellent entre eux en nom nu. Comparer les seuls noms produirait
  l'erreur SYMETRIQUE : `engine/services/movement_query.py` definit son propre `is_adjacent(board,
  a, b)` et `engine/services/battle_query.py` son propre `are_entities_adjacent(a, b, board)` --
  homonymes dont le 3e parametre n'est PAS `elev_by_pos`. On n'accepte donc un nom que s'il resout
  vers `engine.battle_query` (import resolu, `level` relatif compris) ou s'il est defini dans CE
  fichier-la.

* **ETAPE 2 -- pas de GEOMETRIE NUE dans un mirror declare du substrat stocke**
  (#433-r4-r1-r4-r2-r1). L'etape 1 est structurellement AVEUGLE au vice qui a rouvert ce residu :
  `battle_query.newly_adjacent_ids` et `runner.components.update_charging` mirroraient
  `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` -> `GetAdjacentUnits` ->
  `IterateAdjacentTiles` avec un `hexgeo.distance == 1` **NU** -- donc sans elevation, donc hors
  gisement de l'invariant de couple, PAR CONSTRUCTION. Mesure du 2026-08-04 : 2 foyers, 0 vus par
  l'etape 1.

  Le critere est DERIVE du contenu, jamais une liste de noms (#440), et il tient en trois termes
  conjoints : la fonction CITE un natif dont le substrat d'enumeration est la liste stockee ; son
  corps COMPARE une distance hexagonale a 1 (la geometrie nue) ; et elle n'a AUCUN acces au canal
  (ni parametre, ni derivation depuis un board). Les trois ensemble sont exactement le vice ; deux
  d'entre eux ne le sont pas -- `is_adjacent` porte les termes 1 et 2 et c'est son repli documente,
  le terme 3 l'en sort. Le module qui DEFINIT le foyer du canal est exclu par la meme derivation
  (on le localise en cherchant ou `adjacent_neigh_by_pos` est `def`-ini) : la source du canal ne
  peut pas le recevoir en entree.

* **ETAPE 3 -- la DERIVATION LAISSEE MORTE** (#433-r4-r1-r4-r2-r1-r1). Les etapes 1 et 2 cotent la
  PRESENCE du canal : un nom passe au call-site, un nom cite dans le corps. Aucune ne cote sa
  CONSOMMATION. Une fonction qui derive le canal puis n'en fait rien -- `neigh = neigh_map(ctx)`
  jamais relu, ou `is_adjacent(...)` appele en statement nu -- a exactement l'ALLURE d'un mirror
  branche et exactement le COMPORTEMENT d'avant le branchement. C'est la mutation qui restait VERTE
  a la contre-epreuve de #611.

  Deux formes, toutes deux des no-op DEMONTRABLES, sans allowlist : (a) un nom TEINTE par la valeur
  du canal, assigne et jamais relu dans la fonction (le teint se propage par point fixe : ce qui
  derive d'une valeur du canal EST une valeur du canal) ; (b) un appel a une fonction PURE du foyer
  (les CIBLES + `neigh_map`, qui rendent un bool / un compte / un set) dont la valeur est jetee.
  La forme (b) exige la meme RESOLUTION D'IMPORT que l'etape 1 -- un `update_charging(...)` en
  statement nu est LEGITIME (c'est un mutateur ECS), donc seules les fonctions PURES du foyer
  comptent. Seule cible exclue : le nom `_` exactement, qui DIT qu'on jette.

* **ETAPE 4 -- la GEOMETRIE qui decide MALGRE le canal.** Complement exact de l'etape 2 sur le meme
  gisement : la ou l'etape 2 garde le mirror declare SANS canal, celle-ci garde le mirror declare
  AVEC canal. Ensemble elles disent la meme regle -- dans un mirror declare, une geometrie nue ne
  peut etre qu'un REPLI, donc elle doit etre atteinte sur un chemin ou le canal a ete etabli
  INDISPONIBLE.

  Le critere est un critere de FLOT, pas de presence : on propage le long des branches un booleen
  « le canal est etabli indisponible ici », initialise a FAUX, retourne par un test qui parle du
  canal (`X is None` -> vrai dans le body, `X is not None` -> vrai dans le orelse), et FUSIONNE en ET
  a la sortie d'un `if` (l'etat n'est garanti que si TOUS les chemins entrants le garantissent) --
  une branche qui TERMINE (return/raise) ne participe pas a la fusion. Ce sont ces deux regles qui
  separent les replis LEGITIMES du vice : `battle_query.is_adjacent` met sa geometrie sous
  `if neigh is None`, et `services.battle_query.are_tiles_adjacent` la met APRES un bloc canal dont
  toutes les feuilles retournent -- alors qu'une garde inerte (`if neigh_by_pos is None: pass`) ou
  un canal consulte puis ignore laissent la geometrie decider sur un chemin ou le canal repondait.

  Le groupe de noms qui « parle du canal » se DERIVE lui aussi : valeurs du canal, PORTEURS (les
  arguments d'une derivation -- `board` dans `connectivity_neighbours(board, t)`, `ctx` dans
  `neigh_map(ctx)`) et ce qui derive d'un porteur. Il est volontairement LARGE : il ne sert qu'a
  RECONNAITRE un test de disponibilite, donc l'elargir ne peut que retenir le cliquet, jamais le
  faire hurler. Approximations NOMMEES : les boucles et les `try` ne propagent pas leur etat de
  sortie (l'etat courant y entre, l'etat apres est celui d'avant), et un test qui parle du canal
  sous une forme non reconnue vaut credit (les deux branches sont dites « hors canal »).

* **ETAPE 5 -- la SUSPENSION d'un natif lu est-elle encore justifiee ?**
  (#433-r4-r1-r4-r2-r1-r1-r1). `NATIFS_LISTE_STOCKEE` est une liste LITTERALE, et la mesure a
  REFUTE les deux derivations candidates (cf. le commentaire de la liste : 28 tokens rendus,
  3 vrais, 25 faux). Ce qu'on peut deriver, en revanche, c'est qu'une liste partielle ne le reste
  pas en SILENCE. Un natif LU comme substrat stocke mais dont l'armement rougirait sur un vice
  OUVERT hors perimetre entre au registre SUSPENDU, avec son numero de residu ; cette etape
  l'arme POUR DE FAUX a chaque passe et rougit si plus personne n'en souffre -- la suspension est
  alors PERIMEE, et c'est elle le vice. Critere INVERSE des quatre autres, et derive du contenu.

VERDICT : 0 = vert. Non nul = des mirrors non branches (listes). 99 = INDISPONIBLE (#471).
`--inventaire` imprime, SANS peser sur le verdict, les fonctions qui melangent une geometrie nue et
un acces au canal HORS mirror declare : le gisement que le critere « docstring » ne couvre pas.
ASCII only.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r12).
#: MESURE : 438 fichiers -- `scripts/python/engine/**` et SON PROPRE source, rien d'autre. Il
#: n'IMPORTE pas `engine`, il le PARSE : sa fermeture est donc celle de `git ls-files
#: scripts/python/engine`, pas celle d'un `import`.
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/**/*.py",),
    "build": False,
    "toujours": False,
    "raison": "Perimetre DERIVE, `git ls-files scripts/python/engine` (#434), lu en AST. Le "
              "verdict n'est PAS local a un fichier -- l'etape 1 RESOUT les imports pour "
              "distinguer le foyer de ses homonymes, et les etapes 3/4 suivent le flot d'un "
              "canal a travers le module -- mais il ne sort jamais de `engine/`. Aucune table "
              "de symboles : la propriete natif est ATTESTEE dans le source (cf. l'en-tete), "
              "pas derivee du build.",
}

# ETAPE 1 -- nom -> index du parametre ELEVATION dans la signature positionnelle de
# `engine.battle_query`. Seuls comptent les appels qui RESOLVENT vers ce module.
CIBLES = {"is_adjacent": 2, "are_entities_adjacent": 2, "count_adjacent": 2,
          "count_adjacent_matching": 3, "is_charging": 4, "newly_adjacent_ids": 3}
MODULES = ("bq", "battle_query", "_bq")     # porteurs de module pour la forme `bq.is_adjacent(...)`
FOYER = "engine.battle_query"

# ETAPE 2 -- les natifs dont le substrat d'ENUMERATION est la liste stockee du
# `ConnectivityComponent` (`+0x10`). Citer l'un d'eux, c'est declarer mirrorer ce substrat.
# Echappement `u003C`/`u003E` conserve tel quel (convention `CLAUDE.md`).
#
# ⚠ CETTE LISTE EST LITTERALE, ET CE N'EST PAS UN OUBLI -- c'est REFUTE par la mesure
# (#433-r4-r1-r4-r2-r1-r1-r1, cf. la case-doc SS7). La propriete « substrat = liste stockee » est une
# propriete du CORPS natif ; le depot ne versionne AUCUN artefact qui la porte (`data/symbols/`
# n'a que des tables adresse<->nom, `sources_win/` est gitignore, et faire dependre un cliquet de
# ghidra-mcp le rendrait INDISPONIBLE en permanence). Les deux derivations candidates ont ete
# mesurees et rejetees : par le NOM (un marqueur `Adjacent|Neighbour|Melee|Charging`) et par
# FERMETURE sur les docstrings du port -- **28 tokens rendus, 3 vrais, 25 faux** (des enums
# `TargetIsNotAdjacent`, des `UtilityType` `AdjacentTauFriend`, des triggers `IsMeleeAttack`, et
# jusqu'aux VARIABLES LOCALES du decompile cite en pseudo-code : `isAdjacent`, `onlyAdjacent`).
# Un cliquet a 89 % de bruit se fait desactiver, et l'allowlist qui le sauverait SERAIT cette
# liste-ci. Ce qui est derive, c'est donc l'OBLIGATION de ne pas laisser la liste partielle en
# SILENCE : cf. `NATIFS_LISTE_STOCKEE_SUSPENDUS` et l'etape 5.
NATIFS_LISTE_STOCKEE = ("IterateAdjacentTiles", "GetAdjacentUnits", "GetAdjacentTiles",
                        "GetAdjacentEnemies", "GetAdjacentFriends", "AreTilesAdjacent",
                        "IsNeighbour", "UpdateCharging",
                        # LUS le 2026-08-05 (#433-r4-r1-r4-r2-r1-r1-r1) :
                        #   `BattleQuery$$AreEntitiesAdjacent` -- les TROIS surcharges
                        #     ((IList,IList) / (IList,IEntity) / (IEntity,IEntity)) appellent
                        #     `MovementUtil$$AreTilesAdjacent`, donc `ConnectivityComponent$$IsNeighbour` ;
                        #   `BattleQuery$$AreUnitsInMelee(caster, target)` -- corps ENTIER =
                        #     `return AreEntitiesAdjacent(caster, target)`, alias pur ;
                        #   `BattleQuery$$GetFreeAdjacentTiles(from)` -- `GetAdjacentTiles(from, 1, 1)`
                        #     suivi d'un `ListExtensions$$FilterInPlace`.
                        "AreEntitiesAdjacent", "AreUnitsInMelee", "GetFreeAdjacentTiles",
                        # ARME le 2026-08-12 (#943-r7) -- il etait SUSPENDU, et c'est l'etape 5 qui
                        # a demande son armement : apres le cablage de `make_hammer_wrath_events`
                        # (son DERNIER foyer), l'armer ne faisait plus rougir personne, donc la
                        # suspension etait devenue le vice. `DSLSelectors$$AdjacentTiles` ->
                        # `AdjacentTilesSelector$$Select` = slot 0x50 d'`IBattleQuery`
                        # (`GetAdjacentTiles(tile, 0, 1, 1)`) moins `SelectTiles(origin)`.
                        "AdjacentTiles",
                        # ARME le 2026-08-12 (#983) -- meme mecanique que `AdjacentTiles` un cran
                        # plus tot : l'etape 5 l'a DEMANDE. Apres le cablage de ses deux derniers
                        # foyers (`dark_angels_passives::marks_target` et
                        # `extra_damage_aura::create_aura_attack_bonus`), l'armer ne faisait plus
                        # rougir personne. `DSLSelectors$$AdjacentUnits(origin, unique, selType)` =
                        # `op_Subtraction(Units(AdjacentTiles(origin), unique, selType), origin)`,
                        # LU au decompile -- donc `AdjacentTiles`, donc la liste stockee.
                        "AdjacentUnits",
                        # ARME le 2026-08-12 (#983) -- il etait en SILENCE TOTAL (ni arme ni
                        # suspendu) alors qu'il est LU. L'inscrire au registre suspendu a fait
                        # parler l'etape 5 : 0 foyer HORS TOLERANCE ne le justifie, donc la
                        # suspension serait PERIMEE d'avance. `DSLSelectors$$AdjacentEnemies` =
                        # `Enemies(unit, Units(AdjacentTiles(unit)) - unit, selType)`.
                        "AdjacentEnemies",
                        # ARME le 2026-08-15 (#943-r7) -- TROISIEME sortie par la porte du haut, et
                        # c'est encore l'etape 5 qui l'a DEMANDE : apres le cablage de ses trois
                        # derniers foyers (`imperative.py` x2 -- dont le ctx portait DEJA `board` sur
                        # ses deux faces -- et `triggers/loki/icon_of_obstinacy.py`, cable EN MEME
                        # TEMPS que sa jumelle d'aura pour ne pas ouvrir de divergence), l'armer ne
                        # faisait plus rougir personne. `DSLSelectors$$AdjacentFriends(unit, unique,
                        # selType)` = `Friends(unit, Units(AdjacentTiles(unit), unique, selType) -
                        # unit, selType)`, LU au decompile -- donc `AdjacentTiles`, donc la liste
                        # stockee.
                        "AdjacentFriends")

# Natifs LUS au decompile comme substrat stocke, mais dont l'ARMEMENT est SUSPENDU : les faire
# entrer ci-dessus ferait rougir la banque sur un vice OUVERT, hors du perimetre qui les a lus --
# meme sequencement que #614 s'est impose pour `orks.py`. La valeur est le residu qui porte la dette.
# C'est l'etape 5 qui empeche cette suspension de devenir un oubli : elle RE-MESURE a chaque passe
# que la suspension est encore justifiee.
NATIFS_LISTE_STOCKEE_SUSPENDUS: dict = {
    # ⚠ LE REGISTRE EST VIDE, ET C'EST UN RESULTAT DE L'ETAPE 5, PAS UNE DISPENSE. Les trois natifs
    # qui y ont vecu en sont sortis PAR LE HAUT, chacun quand son DERNIER foyer a ete cable, et
    # chaque fois c'est l'etape 5 qui l'a demande en declarant la suspension PERIMEE :
    # `AdjacentTiles` (#943-r7, 2026-08-12), `AdjacentUnits` (#983, 2026-08-12), `AdjacentFriends`
    # (#943-r7, 2026-08-15). `AdjacentEnemies`, lui, n'y a fait qu'un aller-retour dans la meme
    # passe : inscrit par #983, immediatement declare PERIME, donc arme.
    #
    # VIDE != INERTE. L'etape 5 rend alors `(0 perime, 0 suspendu)` et ne pese sur rien -- c'est
    # explicite dans sa docstring (<< Registre VIDE = rien a garder ici (tout est arme), pas un
    # perimetre casse >>). Ce qui garde le gisement dans cet etat, ce sont les etapes 2/4/6, qui
    # voient desormais TOUS ces natifs. La seule chose que ce registre doit rester capable de faire,
    # c'est d'accueillir un natif LU dont l'armement ferait rougir un vice ENCORE OUVERT : le
    # laisser vide sans le supprimer est ce qui rend cette porte disponible.
}

# TOLERANCE NOMMEE de l'etape 2 -- les mirrors declares dont la geometrie nue est un ECART ASSUME,
# et non un oubli. Cle = `(chemin, nom de fonction)` : PAS la ligne, qui bouge a chaque edition du
# fichier et ferait perimer la liste sans que rien n'ait change au fond.
#
# ⚠ ELLE EST VIDE DEPUIS #943-r7 (2026-08-15), ET C'EST SON PROPRE CRITERE QUI L'A VIDEE. Elle ne
# disait pas << cette geometrie est correcte >> mais << la reparer ICI SEULEMENT serait un fork >> --
# un FAIT DU DEPOT, vrai tant qu'une FAMILLE de sites portait la meme geometrie sans etre vue. Ce
# fait a cesse : la famille est cablee sur le foyer `engine.battle_query.is_adjacent`, et l'`etape6`
# ne rend plus AUCUN site `LISTE_STOCKEE`. Ses trois entrees sont sorties par le HAUT, chacune une
# fois son blocage RE-MESURE et trouve plus etroit que ce qui etait ecrit :
#
#   * `aura_selectors.py::adjacent_friends_including_owner` -- AUCUN blocage propre : la fonction
#     recoit l'ECS, donc `State.board`, et n'a qu'UNE face (`kustom_force_field.py`) ;
#   * `loki/icon_of_obstinacy.py::create_aura_attack_damage_bonus_for_ally` -- son ctx d'aura
#     PORTAIT DEJA `board` sur les DEUX faces (`aura_attack_damage_bonus_from_allies`) ; cable dans
#     le MEME commit que l'autre expression du meme `AIconOfObstinacyAbility$$GetAffectedUnits`
#     (le trigger runner), pour que le buff d'ARMURE et le bonus de DEGAT ne divergent pas ;
#   * `loki/terrors_lament.py::_adjacent_enemy_melee` -- << ce ctx d'aura ne publie aucun board >>
#     etait plus LARGE que le fait : sur ses QUATRE call-sites, deux passent le board de coups et
#     deux le ctx defenseur, et les quatre publient la cle depuis le meme commit, sur les deux faces.
#
# ⚠ VIDE != SUPPRIMEE. Le mecanisme reste arme et garde par ses deux contre-epreuves : un mirror
# declare NEUF a geometrie nue rougit (la tolerance ne dispense QUE ce qu'elle NOMME), et vider la
# liste doit faire reapparaitre exactement ce qu'elle nommait. La porte reste disponible pour un
# ecart REELLEMENT assume -- elle n'a simplement plus d'occupant.
GEOMETRIE_NUE_TOLEREE: dict = {}

# ETAPE 6 -- LE REGISTRE DE CLASSIFICATION, et c'est lui qui a fait cesser le critere de PROSE
# (#943-r4, 2026-08-12). Cle = `(chemin, nom de fonction)`, comme la tolerance ci-dessus.
#
# ⚠ CE QU'IL REPARE. Les etapes 2 et 4 n'entrent au gisement que si la docstring NOMME un natif de
# `NATIFS_LISTE_STOCKEE` : leur critere d'entree est un token de PROSE, pas une propriete du CODE.
# Mesure de la tranche precedente : **30 fonctions comparent une distance hex a 1 ; 2 vues, 2 avec
# canal, 26 MUETTES**. Le cas d'ecole etait nomme -- `imperative.create_aura_attack_damage_bonus_
# for_ally` applique EXACTEMENT le meme `hexgeo.distance != 1` que son jumeau `icon_of_obstinacy`,
# sans le nommer : l'un invisible, l'autre rouge. Reparer les visibles laissait 26 sites divergents.
#
# Le critere d'entree est desormais le CONTENU (une distance hex comparee a 1, aucun acces au
# canal) et l'entree au registre exige une LECTURE : la valeur porte le natif LU, verbatim. Un site
# a geometrie nue qui n'est pas ici fait ROUGIR -- il ne peut donc plus etre invisible parce qu'il
# ne nomme pas son natif ; au pire il est NON CLASSE, ce qui se voit.
#
# DEUX classes, et la premiere est un RESULTAT, pas une dispense :
#   * `GEOMETRIQUE` -- le natif mirrore fait LUI-MEME de la geometrie hex. La geometrie nue du port
#     est alors le mirror EXACT, et le cabler serait une REGRESSION. Substrats lus :
#       - `BattleQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` balaie le CUBE
#         `[c-d, c+d]^3` sous `x+y+z == 0` puis `StateExtensions$$GetTileAt(axial)` -- aucune liste
#         stockee, aucune porte d'elevation. C'est le substrat de `DSLSelectors$$SurroundingTiles`,
#         donc de `SurroundingUnits/Friends/Enemies` ;
#       - `MovementQuery$$GetDistance` = `min(CubeCoordinate$$Distance(pieds, pieds))` ;
#       - `MovementQuery$$u003CGetTilesObscuringTerrainu003Eg__DetermineBlockingTiles|40_0` lit deux
#         LISTES DE COORDONNEES a l'index donne et fait `GetTileAt` -- une ligne hex, pas un
#         voisinage.
#   * `LISTE_STOCKEE` -- le natif enumere la liste stockee du `ConnectivityComponent`, le port
#     DEVRAIT porter le canal. Substrats lus :
#       - `DSLSelectors$$AdjacentFriends(unit, unique, selType)` =
#         `Friends(unit, Units(AdjacentTiles(unit)) - unit, selType)`, et `AdjacentEnemies` le
#         pendant exact avec `Enemies` -- les DEUX passent donc par `AdjacentTiles` ;
#       - `BattleQuery$$GetAdjacentUnits(from, ...)` (slots 122-124) =
#         `GetUnitsOnTiles(IterateAdjacentTiles(from, 0, 1, 1), ...)`, et `GetAdjacentEnemies`
#         (slots 125-126) de meme ;
#       - `TileExtensions$$IsNeighbourOf(tile, other)` enumere `ConnectivityComponent+0x10` de
#         `tile` et compare l'id -- liste stockee SANS porte d'elevation ;
#       - `Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger` = `AreEntitiesAdjacent` (slot 96) sur
#         chaque paire, donc `MovementUtil$$AreTilesAdjacent` -> `ConnectivityComponent$$IsNeighbour`.
#     La valeur porte alors le residu qui tient la dette.
#
# ⚠ LE VOLET `LISTE_STOCKEE` EST VIDE DEPUIS #943-r7 (2026-08-15) -- 19 -> 11 -> 9 -> **0**, et
# aucune de ces sorties n'est une dispense : chaque site a ete CABLE, donc il ne compare plus aucune
# distance a 1 et quitte le gisement de l'etape 6 PAR LE HAUT. La classe reste DECLAREE (constante,
# substrats lus, contre-epreuve) parce que c'est elle qui accueillera le prochain site a geometrie
# nue dont le natif enumere la liste stockee.
#
# CE QUI A DEBLOQUE LES NEUF DERNIERS, ET CE N'EST PAS UN EFFORT : c'est une RE-MESURE. Le blocage
# ecrit (`BLOCAGE: seeding` -- << les cabler exige de PUBLIER les deux cartes en amont >>) etait plus
# LARGE que le fait, pour les neuf :
#   * `imperative.py` x2 (canal DEGAT) et le ctx d'aura d'`icon_of_obstinacy.py` -- leur agregateur
#     `aura_attack_damage_bonus_from_allies` PUBLIAIT DEJA `ctx["board"]` sur ses DEUX faces
#     (`damage_model._apply_ally_attack_damage_auras`, `_shared._apply_ally_attack_dmg_bonus`) :
#     ZERO seeding. Meme constat que pour `extra_damage_aura` en #983 ;
#   * `hits.py` x4 et `traits/combat.py` -- le seeding tenait en UNE cle (`board`) ajoutee au board
#     de coups et aux deux ctx d'`additional_hits`, sur les DEUX faces, dont les constructeurs
#     avaient tous le board SOUS LA MAIN (`state.board` / `scene.board`). Une cle ADDITIVE dans un
#     dict, pas un canal a construire ;
#   * `triggers/loki/icon_of_obstinacy.py` -- le << COUPLE NON FERMABLE >> se fermait des que sa
#     jumelle (le ctx d'aura ci-dessus) etait cablable : les DEUX l'ont ete dans le meme commit ;
#   * `runner/abilities/loki/momentum.py` -- SUBSTRAT DIFFERENT, et c'est le seul dont l'analyse
#     tenait : `TileExtensions$$IsNeighbourOf(targetTile, GetMainTile(caster))` enumere
#     `ConnectivityComponent+0x10` **SANS porte d'elevation**, donc ni `is_adjacent` ni
#     `neighbours_native` ne conviennent (tous deux ajouteraient la porte -- le champ capte EST deja
#     `connectivity INTERSECTE {|dElev| < 2}`). Cable sur `Board.neighbours_connectivity`, TRI-ETAT :
#     le champ n'existe QU'EN LIVE (les `data/boards/*.json` sont des ASSETS), donc canal absent ->
#     repli GEOMETRIQUE nomme. L'etiquette `BLOCAGE: capteur` etait fausse -- le capteur EXISTE
#     (`rpc-board.ts` publie `connectivity` depuis #448-r1-r1-r1-r1-r2) ; ce qui manque est une
#     confrontation OFFLINE, pas un capteur.
#
# ⚠ CE QUE LA CLE `(chemin, nom)` NE SEPARE PAS, et c'est nomme plutot que corrige :
# `hits.py` portait DEUX `create_aura_additional_hits_for_ally` (deux classes, deux abilities). Une
# seule entree les couvrait, donc la disparition de l'UNE ne perimait pas l'entree tant que l'AUTRE
# vivait. Une cle par ligne perimerait a chaque edition -- le vice que la tolerance ci-dessus evite.
GEOMETRIQUE = "GEOMETRIQUE"          # le natif fait lui-meme de la geometrie hex -> port EXACT
LISTE_STOCKEE = "LISTE_STOCKEE"      # le natif enumere la liste stockee -> le canal MANQUE

GEOMETRIE_NUE_CLASSEE = {
    # ---- GEOMETRIQUE : le natif mirrore est geometrique, la geometrie nue est le port EXACT ----
    ("scripts/python/engine/battle_query.py", "is_target_tile_obscured"):
        (GEOMETRIQUE, "MovementQuery$$u003CGetTilesObscuringTerrainu003Eg__DetermineBlockingTiles|40_0"),
    ("scripts/python/engine/entities/effects/loki/damage_reduction.py",
     "create_aura_defense_damage_malus_for_ally"):
        (GEOMETRIQUE, "DSLSelectors$$SurroundingUnits -> SurroundingTiles -> IterateSurroundingTiles"),
    ("scripts/python/engine/entities/effects/loki/extra_damage.py", "get_hexes_increasing_damage"):
        (GEOMETRIQUE, "LordOfTempests_ExtraDamageEffect$$GetHexesIncreasingDamage -> SurroundingTiles"),
    ("scripts/python/engine/entities/selectors/units.py", "select"):
        (GEOMETRIQUE, "DSLSelectors$$UnitsDirectlyBehind -> SurroundingTiles(target, 1, 1)"),
    ("scripts/python/engine/services/movement_query.py", "is_valid_unit_feet_list"):
        (GEOMETRIQUE, "MovementQuery$$IsValidUnitFeetList -> GetDistance = CubeCoordinate$$Distance"),
    # ---- LES QUATRE ENTREES CI-DESSOUS SONT ARRIVEES AVEC L'ELARGISSEMENT DU CRITERE
    # (#433-r4-r1-r4-r2-r1-r1-r1-r1, 2026-08-15) : elles etaient INVISIBLES parce qu'elles ecrivent
    # `> 1` / `< 2` (la NEGATION) ou passent la distance par une VARIABLE, pas parce qu'elles
    # seraient nouvelles. Les trois premieres sont GEOMETRIQUES par lecture, la quatrieme est une
    # DETTE. ----
    ("scripts/python/engine/entities/effects/loki/destroy_the_witch.py",
     "create_aura_attack_damage_bonus_for_ally"):
        (GEOMETRIQUE, "DSLSelectors$$SurroundingFriends -> SurroundingTiles -> IterateSurroundingTiles"),
    ("scripts/python/engine/services/movement_query.py", "get_connected_path_to"):
        (GEOMETRIQUE, "BattleQuery$$GetConnectedPathTo -> GetDistance = CubeCoordinate$$Distance"),
    ("scripts/python/engine/runner/abilities/genestealer.py", "get_dynamic_invalid_target_reason"):
        (GEOMETRIQUE, "BattleQuery$$GetMinDistance -> CubeCoordinate$$Distance sur les empreintes"),
    # ---- LISTE_STOCKEE : le natif enumere la liste stockee, le canal MANQUE. ----
    #
    # `PsykerPlaybook` choisit l'arme du coup par une COURONNE HEX (`d <= 1` passe en `is_adjacent`
    # a `select_weapon_pierce`) la ou le natif descend sur la LISTE STOCKEE. Chaine LUE :
    #   `PsykerPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext` appelle le
    #   slot **175** d'`IBattleQuery` = `BattleQuery$$GetAttackWeaponForDefaultNormalAttack`
    #   (3 args), dont le corps ENTIER est : `if (slot 21 d'IAttackQuery(attacker, attackerTiles,
    #   ignoreTrait: 1)) { FindMeleeWeapon sinon FindRangedWeapon } else { l'inverse }` ;
    #   le slot 21 est `AttackQuery$$ShouldApplyRangedInMelee` -> `DamageCalculations$$
    #   ShouldApplyRangedInMelee`, qui pour chaque tuile de l'attaquant ENUMERE la liste `+0x10` du
    #   composant de connectivite et retient un voisin ENNEMI vivant/targetable/non-steppable
    #   passant `DamageCalculations$$CanMeleeAttackOverElevationDifference`.
    # ⚠ LE NOM DE LA METHODE EST TROMPEUR et l'ordinal ne le dit pas : le PREDICAT est
    # « un ennemi valide est ADJACENT », d'ou la branche MELEE quand il rend vrai.
    # Le gisement DEPASSE ce site : `damage_model.select_weapon_pierce` derive `adj = dist <= 1`
    # des que son appelant ne passe pas `is_adjacent`, donc TOUT appelant de la selection d'arme est
    # concerne. Residu `#433-r4-r1-r4-r2-r1-r1-r1-r1-r1` -- le cabler ICI SEULEMENT serait le fork
    # que ce cliquet reproche.
    ("scripts/python/engine/playbook/psyker.py", "calculate_attack_utility_in_steps"):
        (LISTE_STOCKEE, "BattleQuery$$GetAttackWeaponForDefaultNormalAttack -> AttackQuery$$"
                        "ShouldApplyRangedInMelee -> DamageCalculations$$ShouldApplyRangedInMelee "
                        "(liste stockee + CanMeleeAttackOverElevationDifference) -- "
                        "#433-r4-r1-r4-r2-r1-r1-r1-r1-r1"),
}

#: Les substrats LUS AU DECOMPILE, par classe -- c'est ce qui rend `GEOMETRIE_NUE_CLASSEE`
#: VERIFIABLE au lieu de declaratif. Une entree doit citer un substrat de SA classe et AUCUN de
#: l'autre : sans ce cran, << j'ai lu >> se reduirait a << j'ai ecrit un nom >>, et un site a liste
#: stockee pourrait etre range en `GEOMETRIQUE` d'un trait de plume -- exactement la dispense que
#: ce registre existe pour interdire. Le cran est garde par
#: `test_433r4r1r4r2r1r1_derivation_morte_offline.py`, contre-epreuve dans les deux sens comprise.
SUBSTRATS_LUS = {
    GEOMETRIQUE: ("IterateSurroundingTiles", "SurroundingTiles", "CubeCoordinate$$Distance",
                  "DetermineBlockingTiles"),
    #: `ShouldApplyRangedInMelee` est entre le 2026-08-15 (#433-r4-r1-r4-r2-r1-r1-r1-r1) : c'est un
    #: substrat a liste stockee que RIEN dans son NOM n'annonce -- il enumere la liste `+0x10` du
    #: composant de connectivite de chaque tuile de l'attaquant, puis applique la porte d'elevation
    #: par `DamageCalculations$$CanMeleeAttackOverElevationDifference`. C'est la preuve, par
    #: l'exemple, que cette table doit se remplir par LECTURE et non par famille de noms.
    LISTE_STOCKEE: ("AdjacentTiles", "AdjacentUnits", "AdjacentFriends", "AdjacentEnemies",
                    "IterateAdjacentTiles", "IsNeighbourOf", "AreEntitiesAdjacent",
                    "ShouldApplyRangedInMelee"),
}

# Les foyers qui rougiraient, PAR natif suspendu, remplis par `etape5` a chaque passe et imprimes
# par `main`. Ils ne pesent sur AUCUN verdict -- c'est du CONTEXTE.
#
# ⚠ Pourquoi ils existent (#433-r4-r1-r4-r2-r1-r1-r1-r1, 2026-08-10). L'etape 5 mesurait bien << la
# suspension est-elle encore justifiee ? >> et elle repondait JUSTE. Mais elle ne disait pas DE QUI
# la suspension est faite. Resultat : la prose qui, elle, nommait les foyers
# (`aberrant_hypermorph.py`, `master_of_the_tutelaries.py`) a SURVECU a leur reparation -- les deux
# consomment `bq.is_adjacent(...)` depuis longtemps, et la ligne de backlog envoyait quand meme
# corriger un vice inexistant, pendant que les TROIS vrais foyers n'etaient nulle part. Un cliquet
# qui rend un COMPTE juste peut donc laisser perimer la seule chose qu'un lecteur va lire.
_FOYERS_SUSPENDUS: dict = {}
# Formes d'ACCES au canal reconnues : parametre, ou derivation nommee depuis un board.
ACCES_CANAL = ("neigh_by_pos", "neigh_map", "adjacent_neigh_by_pos", "neighbours_native",
               "neighbours_connectivity", "connectivity_neighbours")
FOYER_CANAL = "adjacent_neigh_by_pos"       # sa DEFINITION localise le module a exclure


def _fichiers(sous_arbre: str) -> list[pathlib.Path] | None:
    """Les sources versionnees de `sous_arbre`, DANS CE CHECKOUT (#434).

    `git ls-files` borne le balayage a l'arbre courant : un `rglob` depuis la racine lirait le
    code en cours des autres agents sous `.claude/worktrees/` et leur rouge serait impute ici.
    `None` = git n'a pas repondu -> INDISPONIBLE (#471), jamais un zero silencieux."""
    try:
        r = subprocess.run(["git", "ls-files", sous_arbre], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        print("INDISPONIBLE: git ls-files injouable (%s)" % type(e).__name__)
        return None
    if r.returncode != 0:
        print("INDISPONIBLE: git ls-files rc=%d" % r.returncode)
        return None
    return [ROOT / ln.strip() for ln in r.stdout.splitlines()
            if ln.strip().endswith(".py")]


def _paquet(p: pathlib.Path) -> str:
    """Le paquet Python du fichier, tel qu'un import ABSOLU le nommerait (`engine.playbook...`).

    La racine d'import est `scripts/python` (le CWD impose a tous les probes et a pytest)."""
    rel = p.relative_to(ROOT / "scripts" / "python")
    return ".".join(rel.parts[:-1])


def _module_importe(p: pathlib.Path, node: ast.ImportFrom) -> str:
    """Le module ABSOLU que designe un `from ... import`, `level` relatif RESOLU.

    C'est ce qui distingue `from ..battle_query import ...` (le foyer) de
    `from .battle_query import ...` ecrit DANS `engine/services/` (un homonyme)."""
    base = _paquet(p)
    if not node.level:
        return node.module or ""
    parts = base.split(".") if base else []
    montee = node.level - 1
    if montee:
        parts = parts[:-montee] if montee <= len(parts) else []
    return ".".join(parts + ([node.module] if node.module else []))


def _noms_du_foyer(p: pathlib.Path, tree, noms=None) -> dict:
    """{nom tel qu'il apparait dans CE fichier: nom reel dans `engine.battle_query`}.

    Deux sources, et deux seulement : les imports qui RESOLVENT vers le foyer (alias compris), et
    -- si le fichier EST le foyer -- les definitions locales."""
    noms = CIBLES if noms is None else noms
    out = {}
    if _paquet(p) + "." + p.stem == FOYER:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in noms:
                out[node.name] = node.name
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and _module_importe(p, node) == FOYER:
            for a in node.names:
                if a.name in noms:
                    out[a.asname or a.name] = a.name
    return out


def _resout(f, locaux: dict, noms) -> str | None:
    """Le nom REEL dans `engine.battle_query` que designe la fonction appelee `f`, ou `None`.

    C'est le coeur de la detection : elle RESOUT l'import au lieu de comparer des noms
    (#433-r4-r1-r4-r2-r1). Partage par les etapes 1 et 3, pour qu'un homonyme de `services/`
    n'entre au gisement d'aucune des deux."""
    if isinstance(f, ast.Attribute):
        # `bq.is_adjacent(...)` : porteur de module connu, sinon un homonyme de methode
        # (`self.is_adjacent`) entrerait au gisement a tort.
        if f.attr in noms and getattr(f.value, "id", None) in MODULES:
            return f.attr
        return None
    if isinstance(f, ast.Name):
        return locaux.get(f.id)              # nom NU / alias, RESOLU vers le foyer
    return None


def etape1(arbres) -> tuple[list, int]:
    """Rend `(call-sites a moitie branches, total des call-sites gates)`."""
    manquants, total = [], 0
    for p, tree in arbres.items():
        locaux = _noms_du_foyer(p, tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            reel = _resout(node.func, locaux, CIBLES)
            if reel is None:
                continue
            idx = CIBLES[reel]
            kw = {k.arg for k in node.keywords if k.arg}
            a_elev = len(node.args) > idx or "elev_by_pos" in kw
            a_neigh = len(node.args) > idx + 1 or "neigh_by_pos" in kw
            if not a_elev:
                continue                     # hors gisement : aucun des deux canaux
            total += 1
            if not a_neigh:
                manquants.append((p.relative_to(ROOT).as_posix(), node.lineno, reel))
    return manquants, total


#: Les SIX ecritures d'une adjacence hexagonale sur des entiers, en `(operateur, constante)`.
#: `> 1` et `>= 2` sont la NEGATION de `<= 1` / `< 2` -- la forme de GARDE (`if d > 1: return None`),
#: qui est la plus repandue dans nos mirrors et que le critere d'origine ne voyait pas.
#: `<= 2` / `== 2` n'y sont PAS : ils mirrorent `IterateSurroundingTiles`, qui EST geometrique.
_ADJACENCE_HEX = ((ast.Eq, 1), (ast.NotEq, 1), (ast.LtE, 1), (ast.Lt, 2),
                  (ast.Gt, 1), (ast.GtE, 2))
#: L'ecriture MIROIR (`1 == d`, `2 > d`, ...) : meme predicat, operateur retourne.
_ADJACENCE_HEX_MIROIR = ((ast.Eq, 1), (ast.NotEq, 1), (ast.GtE, 1), (ast.Gt, 2),
                         (ast.Lt, 1), (ast.LtE, 2))


def _est_appel_distance(node) -> bool:
    """CE noeud est-il un appel a une fonction de distance hexagonale ?"""
    return (isinstance(node, ast.Call)
            and (getattr(node.func, "attr", None) == "distance"
                 or getattr(node.func, "id", "").endswith("distance")
                 or getattr(node.func, "attr", None) == "get_distance"
                 or getattr(node.func, "id", "").endswith("get_distance")))


def _vars_de_distance(fn) -> set:
    """Les noms LOCAUX lies a une distance hexagonale (`d = hexgeo.distance(a, b)`).

    ⚠ SANS CETTE RESOLUTION, LE CRITERE EST AVEUGLE A LA MOITIE DU GISEMENT
    (#433-r4-r1-r4-r2-r1-r1-r1-r1, re-mesure du 2026-08-15). `_est_compare_geo` exigeait que
    l'operande GAUCHE soit l'APPEL lui-meme, donc l'ecriture

        d = hexgeo.distance(op, ap)
        adjacent = (d == 1)            # AdjacentFriends -- liste STOCKEE

    ne comptait pour rien. Mesure : **4 sites** dans cette seule forme, dont TROIS portent le meme
    selecteur natif partage x4 (`DefenderOfTheGreaterGoodAbility$$GetBaseBuffTargetSelector`) --
    exactement le genre de site que le registre existe pour voir."""
    noms = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and _est_appel_distance(n.value):
            noms |= {t.id for t in n.targets if isinstance(t, ast.Name)}
        elif isinstance(n, ast.AnnAssign) and n.value is not None \
                and _est_appel_distance(n.value) and isinstance(n.target, ast.Name):
            noms.add(n.target.id)
    return noms


def _est_compare_geo(node, vars_dist=()) -> bool:
    """CE noeud est-il la comparaison d'une distance hexagonale a 1 ?

    C'est la forme EXACTE de la geometrie nue : une adjacence decidee sur la couronne hex au lieu
    de la liste stockee. `<= 2` (un disque) et `== 2` (un ring-2) n'en sont pas -- ils mirrorent
    `IterateSurroundingTiles`, qui EST geometrique.

    ⚠ LE CRITERE A ETE ELARGI DEUX FOIS, ET LES DEUX FOIS SUR UNE MESURE, PAS SUR UNE INTUITION :
    il ne connaissait que `== 1` / `!= 1` / `<= 1`, l'appel de distance devant etre l'operande
    GAUCHE. Il ratait donc (a) la NEGATION `> 1` -- la forme de garde `if d > 1: return None`,
    **3 sites** -- et (b) la distance passee par une VARIABLE locale, **4 sites**. Soit
    **7 sites invisibles**, dont deux dans le foyer meme du residu. Un cliquet dont le critere
    ne couvre qu'une des six ecritures d'un predicat rend un ZERO qui ne prouve rien.

    L'ordre des operandes est traite par `_ADJACENCE_HEX_MIROIR` (`1 == d`), pour la meme raison :
    une ecriture equivalente ne doit pas dependre de la position du litteral."""
    if not isinstance(node, ast.Compare):
        return False

    def _porte_distance(n) -> bool:
        return (_est_appel_distance(n)
                or (isinstance(n, ast.Name) and n.id in vars_dist))

    # ECRITURE DIRECTE : la distance a gauche, le litteral a droite (`d == 1`, `d > 1`).
    if _porte_distance(node.left):
        for op, cmp in zip(node.ops, node.comparators):
            if not isinstance(cmp, ast.Constant):
                continue
            for cls, val in _ADJACENCE_HEX:
                if isinstance(op, cls) and cmp.value == val:
                    return True
    # ECRITURE MIROIR : le litteral a gauche, la distance a droite (`1 == d`, `2 > d`).
    if isinstance(node.left, ast.Constant):
        for op, cmp in zip(node.ops, node.comparators):
            if not _porte_distance(cmp):
                continue
            for cls, val in _ADJACENCE_HEX_MIROIR:
                if isinstance(op, cls) and node.left.value == val:
                    return True
    return False


def _compare_distance_a_un(fn) -> bool:
    """Le corps compare-t-il une distance hexagonale a 1 quelque part ?"""
    vars_dist = _vars_de_distance(fn)
    return any(_est_compare_geo(n, vars_dist) for n in ast.walk(fn))


def etape2(arbres) -> tuple[list, int]:
    """Rend `(mirrors declares qui font de la geometrie NUE sans acces au canal, total examine)`.

    Le module qui DEFINIT `adjacent_neigh_by_pos` est exclu par derivation : il EST la source du
    canal, il ne peut pas le recevoir."""
    exclus = {p for p, tree in arbres.items()
              if any(isinstance(n, ast.FunctionDef) and n.name == FOYER_CANAL
                     for n in ast.walk(tree))}
    manquants, total = [], 0
    for p, tree in arbres.items():
        if p in exclus:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            doc = ast.get_docstring(node) or ""
            if not any(nat in doc for nat in NATIFS_LISTE_STOCKEE):
                continue
            if not _compare_distance_a_un(node):
                continue                     # pas de geometrie nue -> rien a garder ici
            total += 1
            # ⚠ Le critere porte sur l'USAGE, pas sur la DISPONIBILITE. Contre-epreuve du
            # 2026-08-04 : coter la SIGNATURE laissait passer la mutation qui remettait
            # `newly_adjacent_ids` en geometrie nue -- ses parametres `elev_by_pos`/`neigh_by_pos`
            # restaient declares, donc le cliquet la voyait « branchee ». Un parametre non lu ne
            # branche rien. En AST un parametre n'apparait comme `ast.Name` QUE s'il est utilise :
            # ne regarder que le corps rend le critere exact.
            corps = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            corps |= {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            if not corps & set(ACCES_CANAL):
                manquants.append((p.relative_to(ROOT).as_posix(), node.lineno, node.name))
    return manquants, total


def etape2_hors_tolerance(arbres, brut=None) -> tuple[list, int]:
    """`etape2` PRIVEE des sites nommement toleres (`GEOMETRIE_NUE_TOLEREE`).

    C'est CETTE version qui pese sur le verdict ; `etape2` reste la mesure BRUTE du gisement, parce
    qu'un cliquet doit pouvoir dire ce qu'il tolere ET combien. Un site tolere qui DISPARAIT ou qui
    est RENOMME cesse simplement d'etre soustrait -- la liste ne peut donc pas dispenser un site
    qu'elle ne designe plus.

    `brut` = le resultat d'`etape2` deja calcule, pour ne pas re-balayer les 438 arbres. C'est un
    parametre de COUT, jamais de comportement : sans lui le calcul est identique."""
    manquants, total = etape2(arbres) if brut is None else brut
    return ([m for m in manquants if (m[0], m[2]) not in GEOMETRIE_NUE_TOLEREE], total)


def etape6(arbres) -> tuple[list, int]:
    """MESURE BRUTE -- le gisement COMPLET des geometries nues, docstring ou pas.

    Les etapes 2 et 4 gardent les mirrors qui DECLARENT mirrorer le substrat stocke : leur critere
    d'entree est un token de PROSE. Cette etape-ci enleve ce filtre et ne garde que le CONTENU (une
    distance hex comparee a 1, aucun acces au canal) -- elle mesure donc ce que les deux autres ne
    peuvent PAS voir, et c'est ce qui justifie la tolerance ci-dessus : sans elle, << 2 sites
    rouges >> se lit comme l'ampleur du gisement, alors que c'en est la part DOCUMENTEE.

    ⚠ ELLE NE RENDAIT AUCUN VERDICT, ET C'ETAIT LE FOND DU RESIDU (#943-r4). << Coter ces sites sans
    les avoir LUS un par un ferait l'erreur que ce cliquet reproche aux ports -- decider sans lire >>
    etait vrai, et restait vrai TANT QUE personne ne les avait lus. Ils le sont : les 26 muets ont
    ete tries au decompile, natif par natif, et le resultat est `GEOMETRIE_NUE_CLASSEE`. Le verdict
    est desormais porte par `etape6_non_classee` ci-dessous -- non pas << toute geometrie est un
    vice >> (5 sites sur 26 mirrorent un natif GEOMETRIQUE, les cabler serait une regression), mais
    << toute geometrie doit avoir ete LUE >>.

    Rend `(sites MUETS, total des geometries nues sans canal)`."""
    exclus = {p for p, tree in arbres.items()
              if any(isinstance(n, ast.FunctionDef) and n.name == FOYER_CANAL
                     for n in ast.walk(tree))}
    muets, total = [], 0
    for p, tree in arbres.items():
        if p in exclus:
            continue
        for fn in _fonctions_racine(tree):
            if not _compare_distance_a_un(fn):
                continue
            if _noms_du_corps(fn) & set(ACCES_CANAL):
                continue                     # la fonction a le canal : etape 4, pas ici
            total += 1
            doc = ast.get_docstring(fn) or ""
            if not any(nat in doc for nat in NATIFS_LISTE_STOCKEE):
                muets.append((p.relative_to(ROOT).as_posix(), fn.lineno, fn.name))
    return muets, total


def etape6_non_classee(arbres, brut=None) -> tuple[list, int]:
    """Rend `(geometries nues MUETTES et NON CLASSEES, total des muettes)`. PESE SUR LE VERDICT.

    C'est ce qui fait cesser le critere de PROSE (#943-r4) : `etape6` reste la mesure BRUTE du
    gisement -- exactement comme `etape2` reste la mesure brute sous sa tolerance -- et CELLE-CI
    porte le verdict. Un site a geometrie nue non inscrit a `GEOMETRIE_NUE_CLASSEE` rougit, quelle
    que soit sa docstring : il ne peut donc plus etre invisible pour la raison qu'il ne nomme pas
    son natif. Au pire il est NON CLASSE -- et ca, ca se voit.

    ⚠ LE REGISTRE N'EST PAS UNE DISPENSE : `GEOMETRIQUE` est un RESULTAT (le natif fait lui-meme de
    la geometrie, cabler serait une REGRESSION), `LISTE_STOCKEE` est une DETTE NOMMEE (le canal
    manque, le residu est cite). Les deux exigent d'avoir LU le natif, et la valeur le porte.

    Le second membre est le total des MUETTES (pas des geometries nues) : c'est le perimetre que
    cette etape-ci garde, et un zero de ce total dirait que le balayage ne garde rien.

    `brut` = le resultat d'`etape6` deja calcule -- parametre de COUT, jamais de comportement."""
    muets, _total = etape6(arbres) if brut is None else brut
    return ([m for m in muets if (m[0], m[2]) not in GEOMETRIE_NUE_CLASSEE], len(muets))


# --------------------------------------------------------------------------------------------
# ETAPES 3 et 4 -- la CONSOMMATION du canal, pas sa presence (#433-r4-r1-r4-r2-r1-r1)
# --------------------------------------------------------------------------------------------

_CACHE_NOMS: dict = {}


def _noms_du_corps(node) -> set:
    """Les noms (variables ET attributs) qui apparaissent dans le sous-arbre.

    Memoise par identite de noeud : le point fixe de `_teinte` et le flot de l'etape 4 reinterrogent
    les memes sous-arbres des dizaines de fois, et un `ast.walk` par interrogation faisait le
    cliquet a lui seul plus cher que les deux etapes historiques reunies."""
    # Cle = le NOEUD, jamais son `id()` : un arbre temporaire libere ferait recycler l'adresse et
    # empoisonnerait le cache (les arbres SYNTHETIQUES des tests sont exactement ce cas).
    hit = _CACHE_NOMS.get(node)
    if hit is None:
        hit = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Name):
                hit.add(n.id)
            elif isinstance(n, ast.Attribute):
                hit.add(n.attr)
        _CACHE_NOMS[node] = hit
    return hit


_CACHE_DECLARES: dict = {}


def _noms_declares(node) -> set:
    """Les noms du sous-arbre, PARAMETRES COMPRIS.

    Un parametre inerte n'apparait comme `ast.Name` NULLE PART -- c'est meme sa definition. Le
    filtre « cette fonction touche-t-elle le canal ? » de l'etape 3 doit donc le voir, sans quoi sa
    forme (c) serait structurellement inatteignable. L'etape 2 et son complement, eux, gardent le
    filtre par USAGE : la, un parametre non lu ne branche rien, et c'est tout l'objet du critere."""
    hit = _CACHE_DECLARES.get(node)
    if hit is None:
        hit = set(_noms_du_corps(node))
        hit |= {a.arg for a in ast.walk(node) if isinstance(a, ast.arg)}
        _CACHE_DECLARES[node] = hit
    return hit


def _fonctions_racine(tree) -> list:
    """Les fonctions qui ne sont IMBRIQUEES dans aucune autre.

    C'est la bonne unite pour les etapes 3 et 4 : une derivation faite dans la fonction englobante
    et consommee dans une closure (`update_charging` -> `_adjacent_ids`) ne doit pas passer pour
    morte, et le flot qui gouverne une geometrie ecrite dans une closure est celui du point de
    DEFINITION de cette closure."""
    out, pile = [], list(ast.iter_child_nodes(tree))
    while pile:
        n = pile.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(n)                        # on NE descend PAS : ses filles sont imbriquees
        else:
            pile.extend(ast.iter_child_nodes(n))
    return out


def _cibles_assignees(st) -> list:
    """Les `ast.Name` ECRITS par un statement d'AFFECTATION, avec la ligne.

    Les liaisons de PARCOURS (`for`, `with`) en sont exclues a dessein : ce ne sont pas des
    derivations du canal mais des noms de balayage, et une cible de boucle inutilisee est un
    idiome, pas un no-op de branchement."""
    out = []
    if isinstance(st, ast.Assign):
        for t in st.targets:
            out += [(n.id, st.lineno) for n in ast.walk(t) if isinstance(n, ast.Name)]
    elif isinstance(st, ast.AnnAssign) and st.value is not None:
        out += [(n.id, st.lineno) for n in ast.walk(st.target) if isinstance(n, ast.Name)]
    elif isinstance(st, ast.NamedExpr):
        out += [(n.id, st.lineno) for n in ast.walk(st.target) if isinstance(n, ast.Name)]
    return out


def _teinte(fn, porteurs: bool) -> set:
    """Les noms qui portent une VALEUR du canal dans `fn`, par point fixe.

    `porteurs=True` ajoute les ARGUMENTS d'une derivation (`board` dans
    `connectivity_neighbours(board, t)`, `ctx` dans `neigh_map(ctx)`) et tout ce qui en derive.
    C'est ce groupe ELARGI que l'etape 4 emploie pour RECONNAITRE un test de disponibilite --
    l'elargir ne peut donc que retenir le cliquet. L'etape 3, elle, cote une valeur MORTE : elle
    prend le groupe STRICT, sinon le moindre code mort derive d'un `board` deviendrait un vice."""
    g = set(ACCES_CANAL)
    for a in list(fn.args.args) + list(fn.args.kwonlyargs) + list(fn.args.posonlyargs):
        if a.arg in ACCES_CANAL:
            g.add(a.arg)
    if porteurs:
        for n in ast.walk(fn):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            nom = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if nom not in ACCES_CANAL:
                continue
            if isinstance(f, ast.Attribute):
                g |= {x.id for x in ast.walk(f.value) if isinstance(x, ast.Name)}
            for arg in list(n.args) + [k.value for k in n.keywords]:
                g |= {x.id for x in ast.walk(arg) if isinstance(x, ast.Name)}
    change = True
    while change:
        change = False
        for st in ast.walk(fn):
            val = getattr(st, "value", None)
            if val is None or not isinstance(st, (ast.Assign, ast.AnnAssign, ast.AugAssign,
                                                  ast.NamedExpr)):
                continue
            if not (_noms_du_corps(val) & g):
                continue
            cibles = ([st.target] if hasattr(st, "target") else list(st.targets))
            for t in cibles:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name) and n.id not in g:
                        g.add(n.id)
                        change = True
        if porteurs:
            for st in ast.walk(fn):
                if isinstance(st, (ast.For, ast.AsyncFor)) and (_noms_du_corps(st.iter) & g):
                    for n in ast.walk(st.target):
                        if isinstance(n, ast.Name) and n.id not in g:
                            g.add(n.id)
                            change = True
    return g


def etape3(arbres) -> tuple[list, int]:
    """Rend `(derivations du canal laissees MORTES, total des fonctions qui touchent le canal)`.

    Trois formes, toutes des no-op DEMONTRABLES -- aucune n'a besoin d'une allowlist :
      (a) un nom TEINTE assigne et jamais relu dans la fonction ;
      (b) un appel a une fonction PURE du foyer (les CIBLES + `neigh_map`) dont la valeur est jetee
          -- resolution d'import comprise, pour qu'un mutateur homonyme n'y entre pas ;
      (c) un PARAMETRE du canal jamais lu : « un parametre accepte mais non lu se refait passer un
          jour pour un canal actif » (case-433r4r1r4r2r1 §1).

    DEUX limites NOMMEES, toutes deux choisies du cote qui ne hurle pas : le critere porte sur le
    NOM (« jamais relu dans la fonction »), donc une reaffectation qui tue un store precis lui
    echappe ; et un store d'ATTRIBUT (`self._neigh = ...`) n'est pas cote du tout -- sa lecture peut
    vivre hors du perimetre balaye, et un faux positif la-dessus ferait desarmer le cliquet."""
    manquants, total = [], 0
    for p, tree in arbres.items():
        if not (_noms_declares(tree) & set(ACCES_CANAL)):
            continue                             # pre-filtre par FICHIER : un walk au lieu de N
        rel = p.relative_to(ROOT).as_posix()
        purs = _noms_du_foyer(p, tree, dict(CIBLES, neigh_map=0))
        for fn in _fonctions_racine(tree):
            if not (_noms_declares(fn) & set(ACCES_CANAL)):
                continue                         # la fonction ne touche pas le canal
            total += 1
            g = _teinte(fn, porteurs=False)
            lus = {n.id for n in ast.walk(fn)
                   if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
            vus = set()
            for st in ast.walk(fn):              # (a) store teinte jamais relu
                cibles = _cibles_assignees(st)
                # DEBALLAGE : la question « la valeur de cette affectation est-elle CONSOMMEE ? »
                # se repond au niveau du STATEMENT, pas de la cible. `best, _came = _dijkstra_by_pos
                # (origin, neigh_by_pos, ...)` consomme `best` -- le canal a donc bien MORDU, et
                # coter `_came` seul rendait un FAUX POSITIF (mesure : `walk_pathfinder.
                # get_path_node_counts_by_pos`, entre avec #824 ; il rendait `master` ROUGE sur
                # `test_arbre_courant_vert_et_perimetres_non_vides`). Une affectation SIMPLE est
                # inchangee : son unique cible teintee est aussi son unique chance d'etre relue,
                # et un deballage INTEGRALEMENT jete reste cote sur chacune de ses cibles.
                # On ne regarde que les cibles TEINTEES : sinon le `self` d'un `self.x, y = ...`
                # (toujours relu) desarmerait le critere.
                teintees = [(n, l) for (n, l) in cibles if n in g and n != "_"]
                if len(teintees) > 1 and any(n in lus for (n, _l) in teintees):
                    continue
                for (nom, ligne) in cibles:
                    if nom in g and nom != "_" and nom not in lus and (nom, ligne) not in vus:
                        vus.add((nom, ligne))
                        manquants.append((rel, ligne, fn.name, "derivation `%s` jamais relue" % nom))
            for st in ast.walk(fn):              # (b) appel PUR du foyer, valeur jetee
                if not isinstance(st, ast.Expr) or not isinstance(st.value, ast.Call):
                    continue
                reel = _resout(st.value.func, purs, dict(CIBLES, neigh_map=0))
                if reel is not None:
                    manquants.append((rel, st.lineno, fn.name,
                                      "appel `%s` dont la valeur est jetee" % reel))
            for a in (list(fn.args.args) + list(fn.args.kwonlyargs)     # (c) parametre inerte
                      + list(fn.args.posonlyargs)):
                if a.arg in ACCES_CANAL and a.arg not in lus:
                    manquants.append((rel, fn.lineno, fn.name,
                                      "parametre `%s` jamais lu" % a.arg))
    return manquants, total


class _Flot:
    """Propage « le canal est etabli INDISPONIBLE ici » et marque chaque geometrie nue avec l'etat
    qui la gouverne.

    L'etat part de FAUX (rien n'a encore ete etabli), un test qui parle du canal le retourne selon
    sa polarite, et la sortie d'un `if` FUSIONNE EN ET les branches qui ne terminent pas -- une
    garantie ne vaut que si TOUS les chemins entrants la portent. C'est cette fusion qui separe le
    repli legitime (`if neigh is None: <geo>`, ou un bloc canal dont toutes les feuilles retournent)
    du vice (une garde inerte, ou un canal consulte puis ignore)."""

    def __init__(self, groupe: set):
        self.groupe = groupe
        self.geos = []                           # (lineno, hors_canal)

    def _parle_du_canal(self, node) -> bool:
        return bool(_noms_du_corps(node) & self.groupe)

    def _dit(self, t):
        """VRAI = le test affirme la DISPONIBILITE du canal ; FAUX = son INDISPONIBILITE ;
        `None` = forme non reconnue."""
        if isinstance(t, ast.BoolOp):
            v = [self._dit(x) for x in t.values if self._parle_du_canal(x)]
            if False in v:
                return False
            return True if True in v else None
        if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not):
            d = self._dit(t.operand)
            if d is None:
                return False if self._parle_du_canal(t.operand) else None
            return not d
        if isinstance(t, ast.Compare) and len(t.ops) == 1:
            op, droite = t.ops[0], t.comparators[0]
            nul = isinstance(droite, ast.Constant) and droite.value is None
            if self._parle_du_canal(t.left) and nul:
                return isinstance(op, (ast.IsNot, ast.NotEq))
            if isinstance(op, (ast.In, ast.NotIn)) and \
                    (self._parle_du_canal(t.left) or self._parle_du_canal(droite)):
                return True                      # on CONSULTE le canal
            return None
        if isinstance(t, (ast.Name, ast.Attribute, ast.Call)) and self._parle_du_canal(t):
            return True
        return None

    def _branches(self, test, hors: bool) -> tuple[bool, bool]:
        """(etat du `body`, etat du `orelse`) pour ce test."""
        if not self._parle_du_canal(test):
            return hors, hors
        d = self._dit(test)
        if d is True:
            return False, True
        if d is False:
            return True, False
        return True, True                        # credit : le code TESTE le canal, forme inconnue

    def expr(self, node, hors: bool) -> None:
        """Marque les geometries d'une EXPRESSION (ou d'un statement simple)."""
        if node is None:
            return
        if isinstance(node, ast.IfExp):
            self.expr(node.test, hors)
            hb, he = self._branches(node.test, hors)
            self.expr(node.body, hb)
            self.expr(node.orelse, he)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.bloc(node.body, hors)           # closure : l'etat de son point de DEFINITION
            return
        if _est_compare_geo(node):
            self.geos.append((node.lineno, hors))
        for enfant in ast.iter_child_nodes(node):
            self.expr(enfant, hors)

    def bloc(self, stmts, hors: bool) -> tuple[bool, bool]:
        """(etat sortant, ce bloc termine-t-il TOUJOURS ?)"""
        for st in stmts or ():
            if isinstance(st, ast.If):
                self.expr(st.test, hors)
                hb, he = self._branches(st.test, hors)
                fb, tb = self.bloc(st.body, hb)
                fe, te = self.bloc(st.orelse, he) if st.orelse else (he, False)
                if tb and te:
                    return hors, True            # les deux branches sortent : la suite est morte
                hors = fe if tb else (fb if te else (fb and fe))
            elif isinstance(st, (ast.Return, ast.Raise)):
                self.expr(st, hors)
                return hors, True
            elif isinstance(st, (ast.For, ast.AsyncFor, ast.While)):
                # APPROXIMATION NOMMEE : le corps est visite avec l'etat courant, et l'etat APRES
                # la boucle reste celui d'avant (aucun raffinement par iteration).
                self.expr(getattr(st, "test", None) or st.iter, hors)
                if isinstance(st, (ast.For, ast.AsyncFor)):
                    self.expr(st.target, hors)
                self.bloc(st.body, hors)
                self.bloc(st.orelse, hors)
            elif isinstance(st, (ast.With, ast.AsyncWith)):
                for item in st.items:
                    self.expr(item.context_expr, hors)
                self.bloc(st.body, hors)
            elif isinstance(st, ast.Try) or type(st).__name__ == "TryStar":
                self.bloc(st.body, hors)         # APPROXIMATION NOMMEE : idem, etat non propage
                for h in st.handlers:
                    self.bloc(h.body, hors)
                self.bloc(st.orelse, hors)
                self.bloc(st.finalbody, hors)
            elif isinstance(st, (ast.Break, ast.Continue, ast.Pass, ast.Import,
                                 ast.ImportFrom, ast.Global, ast.Nonlocal)):
                continue
            else:
                self.expr(st, hors)
        return hors, False


def _mirrors_avec_canal(arbres):
    """Les mirrors DECLARES du substrat stocke qui font de la geometrie ET touchent le canal.

    C'est le complement exact du gisement de l'etape 2 (meme critere, `corps & ACCES_CANAL`
    inverse), et le module qui DEFINIT le foyer du canal en est exclu par la meme derivation."""
    exclus = {p for p, tree in arbres.items()
              if any(isinstance(n, ast.FunctionDef) and n.name == FOYER_CANAL
                     for n in ast.walk(tree))}
    for p, tree in arbres.items():
        if p in exclus or not (_noms_declares(tree) & set(ACCES_CANAL)):
            continue                             # pre-filtre par FICHIER (cf. `etape3`)
        for fn in _fonctions_racine(tree):
            doc = ast.get_docstring(fn) or ""
            if not any(nat in doc for nat in NATIFS_LISTE_STOCKEE):
                continue
            if not _compare_distance_a_un(fn):
                continue
            if not (_noms_du_corps(fn) & set(ACCES_CANAL)):
                continue                         # aucun acces : c'est l'ETAPE 2 qui parle
            yield p, fn


def etape4(arbres) -> tuple[list, int]:
    """Rend `(geometries qui decident MALGRE un canal disponible, total des mirrors examines)`."""
    manquants, total = [], 0
    for p, fn in _mirrors_avec_canal(arbres):
        total += 1
        flot = _Flot(_teinte(fn, porteurs=True))
        flot.bloc(fn.body, False)
        for (ligne, hors) in flot.geos:
            if not hors:
                manquants.append((p.relative_to(ROOT).as_posix(), ligne, fn.name))
    return manquants, total


def etape5(arbres, reference=None) -> tuple[list, int]:
    """Rend `(suspensions PERIMEES, total des natifs suspendus)`.

    Le critere est INVERSE de celui des autres etapes, et c'est tout son objet : un natif du
    registre SUSPENDU n'a le droit d'y rester que TANT QU'IL Y A UN VICE. On l'arme pour de faux,
    le temps de la mesure ; s'il ne fait plus rougir personne, la suspension n'a plus de raison et
    c'est ELLE qui devient le vice -- une liste partielle qui se perpetue en silence est exactement
    le mode de defaillance que #433-r4-r1-r4-r2-r1-r1-r1 a paye (`AreEntitiesAdjacent` absent
    pendant que `orks.py` le citait).

    La justification se RE-MESURE donc a chaque passe, elle ne se DECLARE pas -- c'est la seule
    partie de ce cliquet qui soit derivee du contenu plutot qu'ecrite a la main.

    Registre VIDE = rien a garder ici (tout est arme), pas un perimetre casse : aucune garde de
    perimetre n'est posee dessus, contrairement aux etapes 1 et 3.

    ⚠ LE CRITERE EST UN DELTA, ET IL NE L'ETAIT PAS (#943). L'etape mesurait la rougeur ABSOLUE du
    tour d'essai (`etape2 + etape4` avec le natif arme), pas ce qui rougit A CAUSE DE LUI. Tant que
    les deux autres etapes sont vertes les deux quantites coincident -- mais des qu'un vice OUVERT
    existe ailleurs (ce qui est le regime NORMAL de ce cliquet : il EXISTE pour trouver des vices),
    toute suspension devient << justifiee >>, y compris celle d'un natif qui n'apparait dans AUCUNE
    docstring. MESURE : sur l'arbre du 2026-08-11, `etape2` porte deux foyers ouverts
    (`aura_selectors.adjacent_friends_including_owner`, `icon_of_obstinacy.
    create_aura_attack_damage_bonus_for_ally`, residu #943-r3), et la contre-epreuve
    `test_etape5_ROUGIT_sur_une_suspension_perimee` -- qui suspend `NatifQuiNexistePas` -- rendait
    un ensemble VIDE au lieu de le denoncer. Un garde-fou qui devient inerte precisement quand il y
    a quelque chose a garder est pire qu'absent : il DIT que tout va bien.

    Le delta est aussi ce que `_FOYERS_SUSPENDUS` doit porter -- ce registre existe pour dire DE QUI
    la suspension est faite (#433-r4-r1-r4-r2-r1-r1-r1-r1), et une liste absolue y melangeait des
    foyers qui n'ont rien a voir avec le natif suspendu."""
    global NATIFS_LISTE_STOCKEE
    manquants = []
    base = NATIFS_LISTE_STOCKEE
    #: La rougeur SANS aucun natif suspendu arme -- la reference a soustraire.
    #: HORS TOLERANCE des deux cotes : la question est << armer ce natif ferait-il rougir le
    #: VERDICT ? >>, or un site nommement tolere ne le fait pas rougir. Compter la mesure brute
    #: ferait passer pour justifiee une suspension dont le seul foyer est deja excuse.
    #: `reference` = ce couple deja calcule -- parametre de COUT, jamais de comportement.
    if reference is None:
        reference = (etape2_hors_tolerance(arbres)[0], etape4(arbres)[0])
    reference = set(reference[0]) | {tuple(f) for f in reference[1]}
    for nat, residu in sorted(NATIFS_LISTE_STOCKEE_SUSPENDUS.items()):
        try:
            NATIFS_LISTE_STOCKEE = base + (nat,)
            arme = etape2_hors_tolerance(arbres)[0] + etape4(arbres)[0]
        finally:
            NATIFS_LISTE_STOCKEE = base
        foyers = [f for f in arme if tuple(f) not in reference]
        if not foyers:
            manquants.append((nat, residu))
        _FOYERS_SUSPENDUS[nat] = foyers
    return manquants, len(NATIFS_LISTE_STOCKEE_SUSPENDUS)


def inventaire(arbres) -> list:
    """HORS VERDICT -- les fonctions qui melangent une geometrie nue et un acces au canal SANS
    declarer de natif a liste stockee.

    Le critere « docstring » des etapes 2 et 4 ne les voit pas, par construction. Elles ne sont ni
    vertes ni rouges : elles demandent une LECTURE du natif qu'elles mirrorent (#433-r4-r1-r4-r2-r2
    est deja ouvert sur cette forme). Les lister, c'est nommer ce que le cliquet ne couvre pas."""
    out = []
    for p, tree in arbres.items():
        if not (_noms_du_corps(tree) & set(ACCES_CANAL)):
            continue                             # pre-filtre par FICHIER (cf. `etape3`)
        for fn in _fonctions_racine(tree):
            noms = _noms_du_corps(fn)
            if not (noms & set(ACCES_CANAL)) or not _compare_distance_a_un(fn):
                continue
            doc = ast.get_docstring(fn) or ""
            if any(nat in doc for nat in NATIFS_LISTE_STOCKEE):
                continue                         # deja couvert par l'etape 4
            flot = _Flot(_teinte(fn, porteurs=True))
            flot.bloc(fn.body, False)
            nues = [ln for (ln, hors) in flot.geos if not hors]
            if nues:
                out.append((p.relative_to(ROOT).as_posix(), fn.lineno, fn.name, nues))
    return out


def main() -> int:
    fichiers = _fichiers("scripts/python/engine")
    if fichiers is None:
        return 99                            # INDISPONIBLE -- le harnais, pas le depot (#471)
    arbres = {}
    for p in fichiers:
        try:
            with open(p, encoding="utf-8", newline="") as fh:
                arbres[p] = ast.parse(fh.read())
        except (OSError, SyntaxError):
            continue
    # ⚠ Les resultats BRUTS sont calcules UNE fois et passes aux etapes qui les FILTRENT : sans ca,
    # `main()` re-balaie les 438 arbres plusieurs fois de trop (les etapes 2 et 4 sont les plus
    # cheres, et l'etape 5 les rejoue une fois par natif suspendu). Ce sont des parametres de COUT
    # -- le verdict est identique avec ou sans.
    # ⚠ CONTRAINTE POUR QUI SUBSTITUE UNE ETAPE : `etape2_hors_tolerance`, `etape5` et
    # `etape6_non_classee` sont appelees ici avec un ARGUMENT NOMME en plus des arbres. Une
    # substitution de test doit donc accepter `**kw` (`lambda arbres, **kw: ...`), sans quoi elle
    # leve `TypeError` au lieu de mesurer -- un echec BRUYANT, pas un faux vert, mais un echec qui
    # accuse le mauvais coupable.
    m1, t1 = etape1(arbres)
    brut2 = etape2(arbres)
    m2_brut, _ = brut2
    m2, t2 = etape2_hors_tolerance(arbres, brut=brut2)
    m3, t3 = etape3(arbres)
    m4, t4 = etape4(arbres)
    m5, t5 = etape5(arbres, reference=(m2, m4))
    brut6 = etape6(arbres)
    m6, t6 = brut6
    m6nc, t6nc = etape6_non_classee(arbres, brut=brut6)
    print("== #433-r4-r1-r4-r2 -- substrat de voisinage natif")
    print("-- etape 1 : invariant de COUPLE sur les call-sites (imports RESOLUS)")
    print("   call-sites gates par l'elevation : %d" % t1)
    print("   sans le canal de voisinage       : %d (attendu 0)" % len(m1))
    for (rel, ln, name) in m1:
        print("      %s:%d  %s -- elevation fournie, voisinage MANQUANT" % (rel, ln, name))
    print("-- etape 2 : geometrie NUE dans un mirror declare du substrat stocke")
    print("   mirrors declares qui comparent une distance a 1 : %d" % t2)
    print("   dont SANS acces au canal                        : %d" % len(m2_brut))
    print("   dont NON tolere nommement                       : %d (attendu 0)" % len(m2))
    for (rel, ln, name) in m2:
        print("      %s:%d  %s -- mirror declare, geometrie NUE, canal INACCESSIBLE" % (rel, ln, name))
    for (rel, ln, name) in m2_brut:
        if (rel, name) in GEOMETRIE_NUE_TOLEREE:
            print("      [TOLERE %s] %s:%d  %s" % (GEOMETRIE_NUE_TOLEREE[(rel, name)], rel, ln, name))
    print("-- etape 3 : la DERIVATION du canal est-elle CONSOMMEE ? (#433-r4-r1-r4-r2-r1-r1)")
    print("   fonctions qui touchent le canal : %d" % t3)
    print("   dont une derivation laissee MORTE : %d (attendu 0)" % len(m3))
    for (rel, ln, name, quoi) in m3:
        print("      %s:%d  %s -- %s" % (rel, ln, name, quoi))
    print("-- etape 4 : geometrie qui DECIDE malgre un canal disponible")
    print("   mirrors declares AVEC canal et geometrie : %d" % t4)
    print("   dont une geometrie NON GARDEE            : %d (attendu 0)" % len(m4))
    for (rel, ln, name) in m4:
        print("      %s:%d  %s -- canal disponible sur ce chemin, geometrie decide quand meme"
              % (rel, ln, name))
    print("-- etape 5 : la SUSPENSION d'un natif lu est-elle encore justifiee ?"
          " (#433-r4-r1-r4-r2-r1-r1-r1)")
    print("   natifs a l'armement suspendu : %d" % t5)
    print("   dont la suspension est PERIMEE : %d (attendu 0)" % len(m5))
    for (nat, residu) in m5:
        print("      %s -- l'armer ne fait plus rougir personne (%s) : ARME-LE" % (nat, residu))
    # HORS VERDICT -- les foyers QUI justifient chaque suspension, derives a chaque passe. Sans eux,
    # seul un COMPTE etait publie, et la prose des fiches a perime en silence (cf.
    # `_FOYERS_SUSPENDUS`). Un lecteur doit pouvoir aller voir, pas croire.
    for nat in sorted(_FOYERS_SUSPENDUS):
        foyers = _FOYERS_SUSPENDUS[nat]
        print("      %s : %d foyer(s) le justifient encore" % (nat, len(foyers)))
        for (rel, ln, name) in foyers:
            print("         %s:%d  %s" % (rel, ln, name))
    # L'AMPLEUR reelle du gisement, celle que le critere << docstring >> ne peut pas voir. Elle
    # JUSTIFIE `GEOMETRIE_NUE_TOLEREE` (sans elle le compte de l'etape 2 se lirait comme l'ampleur
    # du gisement alors qu'il n'en est que la part DOCUMENTEE) -- et depuis #943-r4 elle PESE, par
    # `etape6_non_classee` : chaque muette doit avoir ete LUE et classee.
    print("-- etape 6 : ampleur reelle de la geometrie nue, et sa CLASSIFICATION (#943-r4)")
    print("   fonctions a geometrie nue SANS acces au canal : %d" % t6)
    print("   dont MUETTES (aucun natif declare)            : %d -- invisibles aux etapes 2 et 4"
          % t6nc)
    print("   dont NON CLASSEES (natif jamais lu)           : %d (attendu 0)" % len(m6nc))
    _classes = {}
    for (rel, ln, name) in m6:
        cl = GEOMETRIE_NUE_CLASSEE.get((rel, name))
        _classes[cl[0] if cl else "NON CLASSEE"] = _classes.get(
            cl[0] if cl else "NON CLASSEE", 0) + 1
        print("      [%s] %s:%d  %s%s"
              % (cl[0] if cl else "NON CLASSEE", rel, ln, name,
                 ("  <- %s" % cl[1]) if cl else ""))
    print("   ventilation : %s" % ", ".join("%s=%d" % kv for kv in sorted(_classes.items())))
    for (rel, ln, name) in m6nc:
        print("      %s:%d  %s -- geometrie nue JAMAIS LUE : classe-la (natif LU) ou cable le canal"
              % (rel, ln, name))
    if "--inventaire" in sys.argv:
        inv = inventaire(arbres)
        print("-- inventaire HORS VERDICT : geometrie nue + canal, natif NON declare")
        print("   fonctions concernees : %d" % len(inv))
        for (rel, ln, name, nues) in inv:
            print("      %s:%d  %s -- geometrie(s) non gardee(s) ligne(s) %s"
                  % (rel, ln, name, ",".join(str(x) for x in nues)))
    if t1 == 0 or t3 == 0 or t6nc == 0:
        # Un zero de TOTAL n'est pas un vert : le balayage n'a rien vu, donc il ne garde rien.
        print("ECART: un perimetre est VIDE (etape 1 : %d, etape 3 : %d, etape 6 : %d)"
              " -- le cliquet ne garde rien (perimetre casse ?)" % (t1, t3, t6nc))
        return 1
    n = len(m1) + len(m2) + len(m3) + len(m4) + len(m5) + len(m6nc)
    print("VERDICT: %s" % ("PASS" if not n else "FAIL (%d)" % n))
    return 0 if not n else 1


if __name__ == "__main__":
    raise SystemExit(main())
