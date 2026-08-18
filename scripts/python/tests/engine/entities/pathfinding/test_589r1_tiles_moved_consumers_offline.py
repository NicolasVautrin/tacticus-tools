"""#589-r1 OFFLINE -- l'AVAL de `tilesMovedThisTurn`, et ce qui decide qu'il bouge ou non.

#589 a rebranche `beeline_pathfinder` sur le `ConnectivityComponent` : le compteur passe de `n_G`
(substrat GEOMETRIE) a `n_C` (substrat CANAL), et le port rendait **4** la ou le natif enregistre
**6**. Ces crans verrouillent les DEUX conclusions de l'aval, celle qui dit « ca bouge » comme
celle qui dit « ca ne bouge pas » -- une garde qui ne garderait que l'inertie resterait verte le
jour ou l'inertie disparait.

CE QUI DECIDE, en deux etages independants
------------------------------------------
1. **LE REGIME** -- `MovementQuery$$GetPathfinderTypeForUnit`. La beeline n'est appelee QUE par
   `MovementQuery$$GetConnectedPathTo`, et seulement `if (GetDistance(last, next) > 1)`. Un
   chemin de `BasePathfinder$$FindPath` a tous ses nuds adjacents -> pour un MARCHEUR la
   densification est un no-op et le substrat n'entre jamais en jeu. Pour un VOLANT
   (`FlyPathfinder$$FindPath` rend des WAYPOINTS) et pour un porteur `TeleportStrike`
   (`ATeleportPathfinder$$FindPath` rend `[from, to]`), il entre.
2. **LE CONSOMMATEUR** -- LINEAIRE ou a SEUIL. Les six call-sites natifs de
   `IdunBattleLogic.Entities.DSLFormulas$$TilesMovedThisTurn` se ventilent ainsi :
     * `ModifiedExoarmour_ExtraDmgEffect$$GetCurrentDamageBonus` / `$$GetExtraDamageMultiplier`
       -> `Multiply(ConfigVar(extraDmg), n)`, LINEAIRE ;
     * `$$CreateActiveCondition` -> `AmountIsGreaterThanZero(n)`, seuil **0** ;
     * `SmashaEadAbility$$CreateTrigger` -> `AmountIsEqualOrGreater(n, Direct(2))`, seuil **2** ;
     * `MastersOfManoeuvreAbility$$CreateTrigger` -> seuil `GetNumberConstant(0x88 =
       tilesTraversed)` ;
     * `EmpyricAmbushEffect$$IsValidAttackForBuff` -> seuil `GetNumberConstant(0x51 = movement)`.

LA BORNE QUI SATURE LES SEUILS <= 2, et elle se DERIVE
------------------------------------------------------
Des que la beeline est appelee, le sous-chemin recousu compte au moins `d >= 2` aretes -- dans
LES DEUX substrats. Donc `min(n_G, n_C) >= 2`, et un seuil `K <= 2` est **deja franchi avant le
rebranchement** : il ne peut pas basculer. Mesure live (`C1_74`, 3906 couples x 4 regimes) :
**aucun** seuil `<= 2` ne bascule, et seul `EmpyricAmbush` (`K = 4`) le fait -- 22 couples en
regime `Fly`, 24 en `TeleportStrike`.

ASCII only (cp1252).
"""
from __future__ import annotations

from engine.entities.pathfinding.board import Board
from engine.entities.pathfinding import pathfinders as PF
from engine.services.movement_query import get_connected_path_to, get_num_tiles_moved

# Grille 3x3 even-q, ids 1..9 par (col,row) : (0,0)=1 (0,1)=2 (0,2)=3 / (1,0)=4 (1,1)=5 (1,2)=6 /
# (2,0)=7 (2,1)=8 (2,2)=9. La tuile 5 est un `Bridge` : `TileComponent$$HasEdge` ne lui laisse que
# l'axe de son pont (4 et 6) -- la forme exacte mesuree sur `C1_74`, ou les 16 aretes dirigees de
# `G \ C` sont TOUTES incidentes aux deux ponts.
_CONN = {1: [2, 4], 2: [1, 3, 6], 3: [2, 6], 4: [1, 5, 7], 5: [4, 6],
         6: [2, 3, 5, 8, 9], 7: [4, 8], 8: [6, 7, 9], 9: [6, 8]}
_NEIGH = {1: [2, 4], 2: [1, 3, 6], 3: [2, 6], 4: [1, 5, 7], 5: [4, 6],
          6: [2, 3, 5, 8], 7: [4, 8], 8: [6, 7], 9: []}
_ELEV = {i: (2 if i == 9 else 0) for i in range(1, 10)}
_POS = {1: (0, 0), 2: (0, 1), 3: (0, 2), 4: (1, 0), 5: (1, 1), 6: (1, 2),
        7: (2, 0), 8: (2, 1), 9: (2, 2)}


def _grid(canal: bool = True):
    out = []
    for i in range(1, 10):
        t = {"id": i, "col": _POS[i][0], "row": _POS[i][1], "elevation": _ELEV[i],
             "walkable": True, "isWall": False, "neighbours": list(_NEIGH[i]),
             "tileDefId": "Bridge" if i == 5 else "Grass"}
        if canal:
            t["connectivity"] = list(_CONN[i])
            t["teleportTwinTileId"] = 0
        out.append(t)
    return out


def _n_tiles(board, ptype: int, a: int, b: int) -> int:
    """`GetNumTilesMoved(GetConnectedPathTo(...))` -- l'etage COMPLET, pathfinder PUIS
    re-densification. C'est ce que `MoveUnitOperation$$Execute` passe a `RecordTilesMoved`."""
    path = PF.find_path(board, ptype, a, b)
    return get_num_tiles_moved(get_connected_path_to(board, a, b, path))


# --------------------------------------------------------------------- etage 1 : LE REGIME
def test_la_MARCHE_ne_voit_PAS_le_rebranchement():
    """Le porteur du seul consommateur LINEAIRE (`votanChampion`, `ModifiedExoarmour`) est un
    MARCHEUR : ni `Flying`, ni aucun des quatre effets `*_TeleportingIn` de
    `GetPathfinderTypeForUnit`. Son `n` est donc le MEME avant et apres #589 -- l'aval y est
    inerte par le REGIME, pas par une propriete du consommateur.

    Mesure live correspondante : `C1_74`, `ptype = 0`, **0 couple sur 3906** change ; et le natif
    suit le port sur 6 mesures, y compris depuis le pont lui-meme.

    ATTENTION -- ce n'est PAS `pathfinders.find_path(Walk)` qu'il faut interroger : il rend `None`
    par conception (le port materialise la marche par un AUTRE moteur, en domaine POSITION, foyer
    partage avec la face DECISION -- #304), et `get_connected_path_to(.., None)` prend alors la
    branche degeneree `[from, to]`, donc `n = 1` quel que soit le substrat. Un cran ecrit ainsi
    serait VIDE. Mesure vecue : il l'etait, et c'est la contre-epreuve qui l'a dit."""
    from engine.entities.pathfinding.walk_pathfinder import get_path_node_counts_by_pos

    def marche(board, a, b):
        neigh, walk, elev = board.walk_maps_by_pos()
        c = get_path_node_counts_by_pos(_POS[a], neigh_by_pos=neigh, walkable_by_pos=walk,
                                        elev_by_pos=elev, blocking_positions=set())
        n = c.get(_POS[b])
        return int(n) - 1 if n else 0

    avec, sans = Board(_grid(True), adjacency="evenq"), Board(_grid(False), adjacency="evenq")
    for a in range(1, 10):
        for b in range(1, 10):
            if a == b:
                continue
            assert marche(avec, a, b) == marche(sans, a, b), (a, b)
    # ⚠ LA COMPARAISON CI-DESSUS NE SUFFIT PAS, et c'est mesure : une mutation qui bascule la
    # MARCHE sur la geometrie frappe les DEUX montages et la laisse VERTE. Le cran qui mord est
    # une valeur ABSOLUE -- la marche `1 -> 8` doit faire le TOUR du pont (3 aretes), jamais le
    # traverser (2).
    assert marche(avec, 1, 8) == 3
    assert marche(sans, 1, 8) == 3


def test_le_VOL_PUR_voit_le_rebranchement_c_est_l_item_2_de_589():
    """`fly_pathfinder` garde la GEOMETRIE (override natif `FlyPathfinder$$AddNeighbours` ->
    `GetSurroundingTiles`), et c'est fidele -- mais `GetConnectedPathTo` recoud SES waypoints par
    la beeline, qui, elle, est rebranchee. La route `Fly` PURE n'est donc PAS inerte.

    Mesure live (`blackHaarken`, `ptype = 3`, `C1_74`) : 9 mesures, accord CANAL **9/9**, accord
    GEOMETRIE **4/9** -- sur `(1,5) -> (5,5)` le natif enregistre **6** la ou la geometrie donne
    **4**. Le meme ecart de 50 % que sur la route `TeleportStrike`."""
    avec, sans = Board(_grid(True), adjacency="evenq"), Board(_grid(False), adjacency="evenq")
    bouge = [(a, b) for a in range(1, 10) for b in range(1, 10) if a != b
             and _n_tiles(avec, PF.PathfinderType.Fly, a, b)
             != _n_tiles(sans, PF.PathfinderType.Fly, a, b)]
    assert bouge, "regime DEGENERE : la grille ne fait pas mordre le vol, elle ne garde rien"
    # Et il MORD dans le bon sens : le canal ne peut qu'ALLONGER (`C` est inclus dans `G`).
    for (a, b) in bouge:
        assert _n_tiles(avec, PF.PathfinderType.Fly, a, b) > \
               _n_tiles(sans, PF.PathfinderType.Fly, a, b), (a, b)
    # Valeur ABSOLUE, pour la meme raison que ci-dessus : un test qui ne compare que deux
    # montages est aveugle a une mutation qui frappe les deux.
    assert _n_tiles(avec, PF.PathfinderType.Fly, 1, 8) == 3
    assert _n_tiles(sans, PF.PathfinderType.Fly, 1, 8) == 2


def test_TELEPORT_STRIKE_voit_le_rebranchement():
    """`ATeleportPathfinder$$FindPath` rend `[from, to]` : TOUT le trajet est recousu par la
    beeline, donc `tilesMovedThisTurn` EST sa longueur. C'est l'oracle direct de #589."""
    avec, sans = Board(_grid(True), adjacency="evenq"), Board(_grid(False), adjacency="evenq")
    ts = PF.PathfinderType.TeleportStrikeFly if hasattr(PF.PathfinderType, "TeleportStrikeFly") \
        else 7
    bouge = [(a, b) for a in range(1, 10) for b in range(1, 10) if a != b
             and _n_tiles(avec, ts, a, b) != _n_tiles(sans, ts, a, b)]
    assert bouge, "regime DEGENERE sur la route TeleportStrike"


# --------------------------------------------------------------------- la BORNE des seuils
def test_la_BORNE_des_seuils_n_est_JAMAIS_sous_2_quand_la_beeline_mord():
    """Ce cran est ce qui SATURE les trois consommateurs a seuil `<= 2`
    (`ModifiedExoarmour$$CreateActiveCondition` K=0, `SmashaEadAbility` K=2,
    `MastersOfManoeuvreAbility` K=`tilesTraversed`). Il se DERIVE de
    `GetConnectedPathTo` (`if (GetDistance(last, next) > 1)`) et il est mesure ici, pas suppose.

    Le point qui compte : la borne vaut dans LES DEUX substrats. Un seuil deja franchi AVANT le
    rebranchement ne peut pas basculer APRES -- l'ecart `n_C - n_G` est positif."""
    avec, sans = Board(_grid(True), adjacency="evenq"), Board(_grid(False), adjacency="evenq")
    vus = 0
    for a in range(1, 10):
        for b in range(1, 10):
            if a == b:
                continue
            ng = _n_tiles(sans, PF.PathfinderType.Fly, a, b)
            nc = _n_tiles(avec, PF.PathfinderType.Fly, a, b)
            if ng == nc:
                continue
            vus += 1
            assert min(ng, nc) >= 2, (a, b, ng, nc)   # LA BORNE
            assert nc > ng, (a, b, ng, nc)            # le canal ne peut qu'allonger
    assert vus, "aucun couple ou les substrats divergent -- la borne n'est pas exercee"


def test_les_seuils_se_RELISENT_du_gameconfig_et_se_ventilent():
    """Les seuils ne sont PAS recopies du decompile : `0x51` et `0x88` sont resolus par
    `IdunBattle.Configuration.AbilityConstantType` (`81 = movement`, `136 = tilesTraversed`) et
    leur VALEUR vient du gameconfig courant. Si le jeu la change, ce cran le dit."""
    import gameconfig as GC
    emp = ((GC.ability("EmpyricAmbush") or {}).get("constants") or {}).get("movement")
    mom = ((GC.ability("MastersOfManoeuvre") or {}).get("constants") or {}).get("tilesTraversed")
    assert emp is not None and mom is not None, (emp, mom)
    # La ventilation qui decide de l'aval, et la borne qui la produit.
    assert int(mom) <= 2, "MastersOfManoeuvre n'est plus sature par la borne -- l'aval est ROUVERT"
    assert int(emp) > 2, "EmpyricAmbush est passe sous la borne -- il devient sature, a re-mesurer"


# --------------------------------------------------------------------- etage 2 : LE CONSOMMATEUR
def test_le_consommateur_PORTE_est_LINEAIRE_donc_4_vers_6_le_change():
    """`ModifiedExoarmour_ExtraDmgEffect$$GetCurrentDamageBonus` = `Multiply(ConfigVar(extraDmg),
    TilesMovedThisTurn(Owner))`. L'additif est `V x n` : le passage `4 -> 6` le change de `2V`.

    Mesure live correspondante (greffe sur `blackHaarken`, `C1_74`, `aiPredict` a tuile CONSTANTE)
    -- trois couples discriminants, les deux valeurs de `n` lues sur la MEME tuile :
      `(2,4)->(0,5)` n=2 -> 6024, n=3 -> 7624 ; `(3,4)->(0,5)` n=3 -> 7624, n=4 -> 9220 ;
      `(4,3)->(0,5)` n=4 -> 9220, n=5 -> 10816. Pente **+1596 a +1600 par tuile**, et **0.0** sans
    la greffe (contre-bras)."""
    from engine.entities.effects.loki.extra_damage import ModifiedExoarmourExtraDmgEffect

    e = ModifiedExoarmourExtraDmgEffect(name="ModifiedExoarmour_ExtraDmg", effect_type=1544,
                                        ability_level=50, ability_variables_multiplier=180)

    def add(n):
        b = e.create_effect_damage_bonus_for_attack(is_ranged=False,
                                                    att_ctx={"tiles_moved_this_turn": n})
        return None if b is None else b.value

    a4, a6 = add(4), add(6)
    assert a4 is not None and a6 is not None
    assert a6 != a4, "le consommateur ne serait plus sensible a n -- l'aval de #589 change"
    # LINEAIRE, pas seulement monotone : `V x n` exactement.
    v = add(1)
    assert a4 == 4 * v and a6 == 6 * v, (v, a4, a6)
    assert add(0) is None                      # `n = 0` -> additif nul -> aucune contribution
    # ... et sa CONDITION D'ACTIVITE, elle, est SATUREE : seuil `> 0`, franchi des `n = 1`.
    assert e.is_active({"tiles_moved_this_turn": 4}) is True
    assert e.is_active({"tiles_moved_this_turn": 6}) is True


def _tokens_en_position_EXECUTABLE(source):
    """Les noms qui apparaissent en position EXECUTABLE : identifiants, attributs, noms de
    classe/fonction, et chaines qui ne sont PAS des docstrings.

    ⚠ POURQUOI un AST et pas un `re.search` sur le texte brut : le cran ci-dessous a rougi sur
    `master` le 2026-08-14 pour UNE occurrence, dans un COMMENTAIRE de
    `engine/runner/operations/triggers/loki/maugetar.py` qui enumere les abilities nommees du
    meme bloc. Aucun trigger n'etait porte. Un detecteur qui lit la PROSE accuse le progres
    documentaire et se fait desarmer par le premier qui veut faire taire le rouge -- exactement
    ce que `probe_va_in_code_vs_prose.py` evite ailleurs dans le depot.

    Les COMMENTAIRES n'entrent jamais dans l'AST : ils sont exclus gratuitement. Les DOCSTRINGS,
    elles, y sont (un `Expr(Constant(str))` en tete de corps) -- on les retire explicitement.
    Les autres chaines RESTENT : un trigger enregistre par son nom (`{"X": ...}`) doit continuer
    a faire rougir, c'est le regime que ce cran existe pour attraper."""
    import ast
    import re

    arbre = ast.parse(source)
    docstrings = set()
    for n in ast.walk(arbre):
        corps = getattr(n, "body", None)
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                and corps and isinstance(corps[0], ast.Expr) \
                and isinstance(corps[0].value, ast.Constant) \
                and isinstance(corps[0].value.value, str):
            docstrings.add(id(corps[0].value))

    out = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(n.name)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings:
            out.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", n.value))
    return out


def test_le_detecteur_du_cran_ci_dessous_SEPARE_le_code_de_la_PROSE():
    """CONTRE-EPREUVE EMBARQUEE du detecteur, pour qu'il ne puisse pas devenir vide en silence.

    Le bras POSITIF est ce qui empeche « ne rien detecter » de passer pour un vert : si le
    detecteur cessait de voir une cle de registre, ce test-ci rougirait AVANT que le cran du
    dessous ne se taise."""
    CODE = 'REGISTRE = {"MastersOfManoeuvre": _handler}\n'
    PROSE = '"""bloc voisin : MastersOfManoeuvre, MischiefMakers."""\n# MastersOfManoeuvre aussi\nX = 1\n'
    assert "MastersOfManoeuvre" in _tokens_en_position_EXECUTABLE(CODE), (
        "le detecteur ne voit plus une cle de registre -- le cran du dessous serait VIDE")
    assert "MastersOfManoeuvre" not in _tokens_en_position_EXECUTABLE(PROSE), (
        "le detecteur lit encore la PROSE -- il accusera le progres documentaire")


def test_aucun_trigger_a_SEUIL_n_est_porte_sinon_l_aval_est_a_RECONFRONTER():
    """Le porteur a seuil encore non exerce (`SmashaEad`) n'a AUCUN trigger porte -- son seuil
    n'est donc exerce nulle part dans le moteur, et c'est ce qui rend le verdict « aval sature »
    suffisant pour lui. Son seuil est le litteral `Direct(2)` de `SmashaEadAbility$$CreateTrigger`,
    donc SOUS la borne : meme exerce, il ne pourrait pas basculer.

    ⚠ `EmpyricAmbush` est SORTI de cette liste en #589-r1-r1, et ce n'est pas un contournement :
    son seuil est desormais EXERCE (l'effet 1578 est porte, cf. `EmpyricAmbushEffect`) et il a ete
    CONFRONTE au natif -- c'est exactement ce que ce cran reclamait. Le garde qui le remplace est
    `test_le_seuil_porte_d_EmpyricAmbush_bascule_a_movement` ci-dessous, plus le cliquet live
    `tests/engine/runner/test_empyric_ambush_threshold_live.py`.

    ⚠ `MastersOfManoeuvre` en est SORTI de meme, en #589-r2, et pour la MEME raison : son trigger
    est porte depuis #999-r1 (`MastersOfManoeuvrePlaceOnMove`, branche `<A>`), donc son seuil est
    EXERCE, et la reconfrontation que ce cran reclamait A ETE FAITE -- elle n'est pas deduite de la
    borne, elle est MESUREE sur deux boards a `Bridge` : **5253 couples divergents (`n_G != n_C`),
    0 bascule du gate porte**, avec le TEMOIN non-nul qui empeche de confondre ce zero avec une
    mesure aveugle (`EmpyricAmbush`, K=4, bascule **1328** fois sur les memes couples).
    `C1_74` : 326 divergents / 70 bascules temoin ; `C3_14` : 4927 / 1258.
    Le garde qui le remplace est `test_le_seuil_porte_de_MastersOfManoeuvre_ne_BASCULE_pas`
    ci-dessous ; la mesure se rejoue par
    `probe_589r2_masters_of_manoeuvre_aval.py --only GATE --board C1_74`."""
    import pathlib

    trig = pathlib.Path(__file__).resolve().parents[4] / "engine" / "runner" / "operations" \
        / "triggers"
    assert trig.is_dir(), trig
    fichiers = sorted(trig.rglob("*.py"))
    assert fichiers, "aucun fichier balaye -- un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas"

    tokens = set()
    for p in fichiers:
        tokens |= _tokens_en_position_EXECUTABLE(p.read_text(encoding="utf-8", errors="replace"))
    # ... et le balayage assertionne SON PROPRE non-vide : un detecteur qui rendrait l'ensemble
    # vide (parse muet, arborescence deplacee) ferait passer ce cran pour VERT sans rien mesurer.
    assert len(tokens) > 100, (
        "detecteur muet : %d token(s) sur %d fichier(s) -- ce cran ne mesure plus rien"
        % (len(tokens), len(fichiers)))
    for ab in ("SmashaEad",):
        assert ab not in tokens, (
            "`%s` a maintenant un trigger porte : son seuil est desormais exerce, l'aval de #589 "
            "doit etre RECONFRONTE pour ce consommateur" % ab)
    # ... et le cran assertionne que sa cible EXISTE encore : si `SmashaEad` disparaissait du
    # recensement natif, la boucle ci-dessus tournerait a vide et ce test passerait pour VERT sans
    # rien garder. C'est le meme vice que le `len(tokens) > 100` juste au-dessus, sur l'autre axe.
    assert "MastersOfManoeuvre" in tokens, (
        "`MastersOfManoeuvre` n'a PLUS de trigger porte : la sortie de ce cran (#589-r2) reposait "
        "sur le fait qu'il en avait un. Le garde qui l'a remplace ne mesure donc plus rien -- "
        "remettre l'ability dans la boucle ci-dessus, ou re-justifier sa sortie.")


def test_le_seuil_porte_d_EmpyricAmbush_bascule_a_movement():
    """LE GARDE qui remplace l'inscription d'`EmpyricAmbush` a la liste ci-dessus (#589-r1-r1).

    Le seuil natif est `AmountIsEqualOrGreater(TilesMovedThisTurn(Caster@DSLSelectors+0x48),
    Direct(GetNumberConstant(0x51 = movement)))`. Il est RELU du gameconfig, jamais code en dur :
    si la config bougeait, ce cran suivrait -- et si le port cessait de basculer AU seuil, il
    rougirait. Confronte live (natif == port sur n = 2, 3, 4, 5, deux regimes) :
    `probe_589r1r1_empyric_ambush_live.py`.

    Le SUJET est le CASTER DE L'ATTAQUE, pas le porteur : le contexte porte donc `att_*`, et
    `owner_id`/`tgt_id` ne servent qu'au `get_OwnerIsTarget` du canal."""
    import gameconfig as GC
    from engine.entities.effects.loki.empyric_ambush import EmpyricAmbushEffect

    k = int(((GC.ability("EmpyricAmbush") or {}).get("constants") or {}).get("movement"))
    assert k > 2, "EmpyricAmbush est passe sous la borne -- il redevient sature, a re-mesurer"

    e = EmpyricAmbushEffect(name="EmpyricAmbush", effect_type=1578, active_ability_level=50,
                            ability_variables_multiplier=180, source=7)
    # ATTAQUANT : Hero, NON-Aeldari (sinon le `op_BitwiseOr` sature), ennemi de la cible, ami de la
    # source (7) et distinct d'elle ; PORTEUR de l'effet == la cible du coup (`get_OwnerIsTarget`).
    ctx = {"att_id": 1, "tgt_id": 9, "owner_id": 9, "att_team": 0, "tgt_team": 1,
           "team_by_id": {1: 0, 7: 0, 9: 1}, "att_faction": "Ultramarines", "att_traits": ("Hero",)}

    for n in range(0, k):
        assert e.create_effect_crit_chance_bonus_for_attack({**ctx, "tiles_moved_this_turn": n}) is None
        assert e.create_effect_crit_damage_bonus_for_attack({**ctx, "tiles_moved_this_turn": n}) is None
    for n in (k, k + 1):
        cc = e.create_effect_crit_chance_bonus_for_attack({**ctx, "tiles_moved_this_turn": n})
        cd = e.create_effect_crit_damage_bonus_for_attack({**ctx, "tiles_moved_this_turn": n})
        assert isinstance(cc, int) and cc > 0, "n=%d >= %d doit ouvrir extraCritChance" % (n, k)
        assert isinstance(cd, int) and cd > 0, "n=%d >= %d doit ouvrir extraCritDmg" % (n, k)

    # TRI-ETAT : compteur NON MESURE != compteur a zero (« present != applique »).
    assert e.create_effect_crit_chance_bonus_for_attack(ctx) is None

    # Le OR : un attaquant AELDARI passe SANS avoir bouge -- c'est ce qui rend le regime de mesure
    # degenere si on choisit mal l'attaquant, et c'est pourquoi le probe le REFUSE.
    aeldari = {**ctx, "att_faction": "Aeldari", "tiles_moved_this_turn": 0}
    assert e.create_effect_crit_chance_bonus_for_attack(aeldari), "HasFaction(Aeldari) doit ouvrir"

    # Le SUJET est le CASTER : le compteur du PORTEUR ne doit RIEN ouvrir (confronte live).
    assert e.create_effect_crit_chance_bonus_for_attack(
        {**ctx, "tiles_moved_this_turn": 0, "owner_tiles_moved_this_turn": k + 5}) is None

    # `get_OwnerIsTarget` : un porteur qui n'est PAS le defenseur ne contribue pas.
    assert e.create_effect_crit_chance_bonus_for_attack(
        {**ctx, "owner_id": 5, "tiles_moved_this_turn": k}) is None


def _eval_gate_mom(gate, n):
    """Le gate PORTE de `MastersOfManoeuvre`, evalue sur un `AbilityEntities` MINIMAL dont
    l'ACTEUR porte `n`. `Actor().select(ctx)` rend `ctx.actor` -- un namespace suffit, et c'est
    VOULU : on exerce le NOEUD, pas le montage d'un `State`. `n = None` = compteur NON MESURE."""
    import types
    actor = {} if n is None else {"tilesMovedThisTurn": int(n)}
    return bool(gate.should_trigger(types.SimpleNamespace(
        actor=actor, subject=None, owner=None, caster=None, target=None)))


def test_le_seuil_porte_de_MastersOfManoeuvre_ne_BASCULE_pas():
    """LE GARDE qui remplace l'inscription de `MastersOfManoeuvre` a la liste ci-dessus (#589-r2).

    Son trigger est porte depuis #999-r1 (`MastersOfManoeuvrePlaceOnMove`, branche `<A>`), donc
    son seuil est EXERCE. Le natif, relu VERBATIM sur `t6dpr4k06g` :

        AmountIsEqualOrGreater( TilesMovedThisTurn( Actor@<DSLSelectors+0x40> ),
                                Get( GetNumberConstant( config, tilesTraversed = 0x88 ) ) )

    Ce cran garde les DEUX faces, et la seconde est celle que le rouge reclamait :
      1. le gate bascule a `K` EXACTEMENT (`>=`, pas `>`), `K` RELU du gameconfig ;
      2. il rend le MEME verdict sur les deux substrats, pour TOUS les couples ou le
         rebranchement de #589 mord -- c'est la saturation, exercee au lieu d'etre deduite.

    ⚠ LE TEMOIN EST CE QUI EMPECHE CE CRAN D'ETRE VIDE. « aucune bascule » et « la grille ne sait
    pas produire de bascule » sont indistinguables sans lui : on verifie donc qu'un seuil PLACE
    AU-DESSUS DE LA BORNE bascule bel et bien sur les MEMES couples. C'est le role que tient
    `EmpyricAmbush` (K=4) sur les vrais boards ; sur cette grille les longueurs sont petites, donc
    le temoin est le seuil **3**.

    Mesure live correspondante (`probe_589r2_masters_of_manoeuvre_aval.py --only GATE`), deux
    boards a `Bridge` : `C1_74` **326** couples divergents / **0** bascule / temoin **70** ;
    `C3_14` **4927** / **0** / temoin **1258**."""
    import gameconfig as GC
    from engine.runner.operations.triggers.loki.masters_of_manoeuvre import (
        masters_of_manoeuvre_tiles_gate)

    k = int(((GC.ability("MastersOfManoeuvre") or {}).get("constants") or {}).get("tilesTraversed"))
    assert k <= 2, ("`tilesTraversed` = %d est passe AU-DESSUS de la borne : le consommateur n'est "
                    "plus sature et l'aval de #589 est ROUVERT pour lui" % k)
    gate = masters_of_manoeuvre_tiles_gate()

    # --- face 1 : la bascule est a K, et le tri-etat est RESTRICTIF.
    for n in range(0, k):
        assert not _eval_gate_mom(gate, n), "n=%d < K=%d ne doit pas ouvrir" % (n, k)
    for n in (k, k + 1, k + 7):
        assert _eval_gate_mom(gate, n), "n=%d >= K=%d doit ouvrir" % (n, k)
    # `TilesMovedThisTurnFormula$$Calculate` rend 0 quand l'entite n'a pas le composant -> ferme.
    assert not _eval_gate_mom(gate, None)

    # --- face 2 : la SATURATION, exercee sur les couples ou le rebranchement mord.
    avec, sans = Board(_grid(True), adjacency="evenq"), Board(_grid(False), adjacency="evenq")
    TEMOIN = 3                      # un seuil AU-DESSUS de la borne, comme `EmpyricAmbush` (K=4)
    divergents = bascule_temoin = 0
    for ptype in (PF.PathfinderType.Fly,
                  getattr(PF.PathfinderType, "TeleportStrikeFly", 7)):
        for a in range(1, 10):
            for b in range(1, 10):
                if a == b:
                    continue
                ng, nc = _n_tiles(sans, ptype, a, b), _n_tiles(avec, ptype, a, b)
                if ng == nc:
                    continue
                divergents += 1
                assert _eval_gate_mom(gate, ng) == _eval_gate_mom(gate, nc), (
                    "le gate porte de `MastersOfManoeuvre` BASCULE entre les substrats sur "
                    "(%d,%d) : n_G=%d n_C=%d -- l'aval de #589 le touche, il n'est PAS sature"
                    % (a, b, ng, nc))
                if (ng >= TEMOIN) != (nc >= TEMOIN):
                    bascule_temoin += 1
    assert divergents, ("aucun couple divergent : la grille ne fait pas mordre le rebranchement, "
                        "ce cran ne garderait RIEN")
    assert bascule_temoin, (
        "le TEMOIN (seuil %d, au-dessus de la borne) ne bascule sur AUCUN des %d couples "
        "divergents : cette grille ne sait pas produire de bascule, donc le zero de "
        "`MastersOfManoeuvre` ci-dessus ne prouve rien" % (TEMOIN, divergents))
