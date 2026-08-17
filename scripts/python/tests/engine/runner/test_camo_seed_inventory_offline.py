"""case-366-r1-camo-seed -- CLIQUETS offline du gisement << effet condition-gated absent de la
capture >>. Aucun RPC : ces gardes tournent en < 1 s et protegent deux acquis.

1. LE VERDICT DE POSE EST OBLIGATOIRE. Toute classe d'`EFFECT_CLASSES` qui surcharge `is_active`
   doit avoir son verdict dans `probe_366_camo_seed_inventory.POSE_VECTOR` -- c'est-a-dire qu'on
   doit avoir LU son `<X>Ability$$CreateBehaviour` au decompile pour savoir si le natif pose
   l'instance MEME quand la condition est fausse. Sans ce verdict on ne peut pas dire si l'absence
   d'une instance a la capture est FIDELE (pose runtime) ou un TROU (pose d'init inconditionnelle).
   Meme forme de cliquet que `probe_181` sur `TARGETING_OPTIONS` : le gisement est alimente par
   notre propre cadence de portage, donc c'est la regle qui MAINTIENT le compte, pas qui le vise.

2. LE SECOND `RefreshEffects` DU MOVE EST CABLE. `IdunBattle.Operations.MoveUnitOperation$$Execute`
   appelle `RefreshEffects({trigger = 7 UnitPositionChanged, effectEntity = null})` DEUX fois, de
   part et d'autre de `EvaluateAfterMoveTriggers`. Cote port, le premier vit dans
   `MoveUnitOperation.execute` et le second doit etre appele APRES `after_move_triggers` -- sinon
   tout effet dont la condition lit un effet POSE PAR le vecteur after-move (`1013 LightCover` ->
   `1014 CamoCloak_DmgReduction`) reste eteint. La garde LIVE est
   `test_camo_cloak_seed_move_live.py` ; celle-ci est le filet structurel, qui rougit meme sans
   session.

ASCII only (cp1252).
"""
from __future__ import annotations

import inspect

import probe_366_camo_seed_inventory as INV


def test_every_condition_gated_class_has_a_pose_verdict():
    """CLIQUET 1 -- re-derive le compte depuis le CODE (jamais recopie) et exige un verdict de
    pose pour CHAQUE classe surchargeante."""
    r = INV.scan()
    counts = {}
    for row in r["rows"]:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    print("\n[camo-seed inventaire] EFFECT_CLASSES=%d surchargent_is_active=%d %s"
          % (r["n_effect_classes"], len(r["rows"]), counts))

    assert r["rows"], (
        "AUCUNE classe ne surcharge `is_active` : la re-derivation est cassee (import ? MRO ?), "
        "pas le registre")
    assert not r["unknown"], (
        "%d classe(s) surchargent `is_active` sans verdict de POSE dans "
        "`probe_366_camo_seed_inventory.POSE_VECTOR` : %s. Lire leur "
        "`<X>Ability$$CreateBehaviour` au decompile -- pose d'init INCONDITIONNELLE (l'instance "
        "existe toujours cote natif, donc son absence offline est un TROU) ou vecteur RUNTIME "
        "(l'absence est FIDELE) ?" % (len(r["unknown"]), r["unknown"]))


def test_les_canaux_de_seed_sont_derives_du_consommateur():
    """CLIQUET 1bis (#547-r11) -- LA DERIVATION DES CANAUX, ET SON PROPRE NON-VIDE.

    `scan()` classait en `COUVERT-SEED` d'apres DEUX tables ECRITES A LA MAIN, quand le seed en
    consomme davantage. Mesure qui l'a montre : `Lifewards_BondEffect` est seede par
    `ABILITY_INIT_OWNER_BOND_EFFECTS` (#963-r5) et sortait en `EXPOSE` -- un TROU annonce la ou le
    port materialise l'instance. Le remede n'est pas d'allonger la liste (elle re-vieillirait au
    canal suivant) mais de la DERIVER du CONSOMMATEUR (`runner/operations/spawn.py`).

    ⚠ CE TEST ASSERTIONNE SON PROPRE NON-VIDE, et ce n'est pas une precaution de style : si l'AST
    ne trouvait plus aucun import (module deplace, `factory` renomme, imports refactores), `seeded`
    deviendrait VIDE -- tout basculerait de `COUVERT-SEED` vers `EXPOSE`/`NON-EXPOSE` sans qu'AUCUNE
    assertion existante ne rougisse, parce que le cliquet de `POSE_VECTOR`, lui, ne regarde que
    `unknown`. Un recensement qui ne trouve rien passe pour vert.

    Il NE FIGE PAS la liste des canaux (ce serait la liste blanche qu'on vient de retirer) : il
    exige que la derivation MORDE -- au moins deux tables, un volume d'effets non trivial, et le
    canal BOND present, qui est celui dont l'absence a produit le defaut."""
    c = INV.canaux_de_seed()
    print("\n[camo-seed canaux] %s | ecartes=%s"
          % ({t: len(n) for t, n in sorted(c["tables"].items())}, c["ecartes"]))

    assert len(c["tables"]) >= 2, (
        "la derivation des canaux de seed depuis `runner/operations/spawn.py` rend %d table(s) : "
        "elle est CASSEE (module deplace ? imports refactores ?), pas le registre -- et un `seeded` "
        "vide ferait passer TOUT le gisement en `EXPOSE` sans qu'aucune autre assertion ne rougisse"
        % len(c["tables"]))
    total = set().union(*c["tables"].values()) if c["tables"] else set()
    assert len(total) >= 10, (
        "seulement %d nom(s) d'effet seedes derives, tous canaux confondus : la derivation ne mord "
        "plus (le filtre `in EFFECT_CLASSES` ecarte-t-il tout ?). Noms vus : %s"
        % (len(total), sorted(total)))
    assert "ABILITY_INIT_OWNER_BOND_EFFECTS" in c["tables"], (
        "le canal BOND (`ABILITY_INIT_OWNER_BOND_EFFECTS`, #963-r5) n'est plus derive depuis "
        "`spawn.py` : c'est EXACTEMENT le canal dont l'absence classait `Lifewards_BondEffect` en "
        "`EXPOSE` a tort. Tables vues : %s" % sorted(c["tables"]))


def test_camo_cloak_owner_effect_is_seeded():
    """CLIQUET 2 -- `1014` doit rester materialisable depuis le canal de capture par DEFAUT.
    Sa pose native (`CamoCloakAbility$$CreateBehaviour`) est un `AddEffect` NU : l'instance existe
    toujours, seul le CAPTEUR la cache quand elle est inerte."""
    from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS
    names = ABILITY_INIT_OWNER_EFFECTS.get("CamoCloak") or []
    assert "CamoCloak_DmgReduction" in names, (
        "`ABILITY_INIT_OWNER_EFFECTS['CamoCloak']` ne pose plus 1014 : un etat charge depuis le "
        "canal `decisionView` par DEFAUT n'aura AUCUNE instance a rallumer quand la sim fera "
        "entrer Certus en couvert (entrees vues : %s)" % (names,))


def test_move_operation_calls_the_second_refresh():
    """CLIQUET 3 -- filet STRUCTUREL sur l'ordre `after_move_triggers` PUIS refresh. Le corps qui
    joue le mouvement doit citer `refresh_effects_after_move_triggers` APRES `after_move_triggers` :
    c'est l'ordre natif (`RefreshEffects({7,null})` ENCADRE `EvaluateAfterMoveTriggers`), et
    l'inverser rendrait le second refresh strictement redondant avec le premier.

    ⚠ LE FOYER A DEMENAGE (#448-r1-r1-r2-r1) : ce cliquet lisait
    `MovementHandler.visit_MoveUnitMessage`. Le vecteur est desormais joue par
    `MoveUnitOperation.execute` -- c'est le RANG NATIF (`EvaluateAfterMoveTriggers` n'a que DEUX
    xrefs, toutes deux dans `IdunBattle.Operations.MoveUnitOperation$$Execute`), et c'est ce qui le
    fait EMERGER pour les feuilles DSL de mouvement. Le cliquet garde la MEME loi, sur le bon corps :
    le deplacer etait la reparation, le retirer aurait ete la faute."""
    from engine.runner.operations.movement import MoveUnitOperation
    src = inspect.getsource(MoveUnitOperation.execute)
    assert "after_move_triggers(" in src, (
        "`MoveUnitOperation.execute` n'appelle plus `after_move_triggers` -- le vecteur after-move "
        "(overwatch, LightCover a l'arrivee) est mort")
    assert "refresh_effects_after_move_triggers(" in src, (
        "`MoveUnitOperation.execute` n'appelle plus `refresh_effects_after_move_triggers` : le "
        "SECOND `RefreshEffects({7, null})` d'`IdunBattle.Operations.MoveUnitOperation$$Execute` "
        "n'est plus porte. Un effet dont la `CreateActiveCondition` lit un effet pose PAR le "
        "vecteur after-move ne se rallumera plus (mesure : 1014 CamoCloak, live 31907 / port 32655)")
    i_vect = src.index("after_move_triggers(\n") if "after_move_triggers(\n" in src else -1
    i_refr = src.index("refresh_effects_after_move_triggers(state)")
    assert i_vect != -1 and i_vect < i_refr, (
        "le second refresh est appele AVANT `after_move_triggers` : il est alors strictement "
        "redondant avec le premier (celui qui precede le vecteur), et le trou reste ouvert")
    # ... et le handler de message ne le rejoue PAS : deux appels = deux overwatchs par pas.
    from engine.runner.operations.movement import MovementHandler
    hsrc = inspect.getsource(MovementHandler.visit_MoveUnitMessage)
    assert "after_move_triggers(" not in hsrc, (
        "`visit_MoveUnitMessage` rejoue le vecteur que l'Operation joue deja -- DOUBLE emission")
