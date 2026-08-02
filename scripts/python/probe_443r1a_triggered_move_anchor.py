"""#443-r1a -- le terme MOVE d'une triggered ability est-il ATTRIBUABLE a son unite ET a sa tuile ?

LE PROBLEME QU'ON FERME. Le terme MOVE de `SaviorProtocols` (1120) est PORTE (#443-r1) mais NON
CONFRONTE au natif : l'oracle disponible, `scorerTileTermTrace`, capte le composite `Tile(7)`
COMPLET par candidat **sans aucun `unitId`**. Mesure de #443-r1 sur `MC1_67`/777 : les 4 events
captes portaient TOUS sur des tuiles occupees par un TIERS, et une version anterieure du probe --
celle qui ne filtrait pas -- a rendu un **accord parfait sur le `Tile(7)` d'une AUTRE unite**. Un
canal sans attribution ne rend pas « moins de mesure » : il fabrique du FAUX POSITIF, a l'echelle.

L'ANCRAGE, lu au decompile.
`IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
est le dispatcher PAR TUILE du terme : il itere les triggered abilities de `case.Unit`, charge le
playbook de chacune (`PlaybookDatabase$$LoadPlaybook`), draine son
`CalculateMovementUtilityInSteps(case, weights)` et SOMME les valeurs finales. Son `case` est un
`IdunBattle.AI.Utilities.UtilityMovementCase`, qui porte l'unite (`+0x10`, cf. `$$get_UnitOrParent`
/ `$$StaysOnTile`), la tuile candidate (`+0x18`, `UnitPosition` INLINE dont `$$get_MovementTile`
rend `MainTile`) et le spawner (`+0x30`, cf. `$$get_IsSpawning`). Le capteur
`frida/hooks/features/triggered-move-trace.ts` s'y attache et publie ces trois-la, plus la
DECOMPOSITION par playbook.

CE QUE CE PROBE MESURE, par etages :

  E0 canal  -- le RPC `triggeredMoveTraceStatus` repond-il ? Sinon le capteur n'est pas charge ->
               NON CONFRONTE, et AUCUN etage suivant ne conclut quoi que ce soit.
  E1 tir    -- quel declencheur fait firer le hook ? On en essaie plusieurs et on RAPPORTE lequel a
               produit des events (le case-443-r1 avait mesure qu'`aiStepDryRun` ne faisait firer
               AUCUN hook RVA). MESURE le 2026-08-02, session 10, capteur CHARGE : `decisionView`
               -> 0, `aiMovableTiles` -> 0, **`aiDryRunAllUnits` -> 102 events**. Le sweep de
               mouvement n'est donc parcouru que par un TOUR D'IA, pas par une vue de decision.
  E2 ATTRIB -- LE CRITERE D'ACCEPTATION. Quatre questions, dans cet ordre :
                 (a) chaque event porte-t-il `unitMeasured` ET un `unitId` ?
                 (b) porte-t-il une `tile` ?
                 (c) l'ensemble des tuiles attribuees a une unite est-il EXACTEMENT
                     `aiMovableTiles(u) UNION {position courante de u}` ? C'est CETTE question qui
                     aurait demasque le faux positif de #443-r1 (les tuiles captees appartenaient a
                     des tiers). L'identite -- et non l'inclusion -- refuse aussi une attribution
                     qui n'evaluerait qu'une tuile sur dix. Le terme `UNION {position}` est ancre
                     natif : `UtilityMovementCase$$StaysOnTile` compare la tuile candidate a la
                     tuile courante, donc le sweep evalue le fait de RESTER SUR PLACE (#456) ;
                 (d) les events se repartissent-ils sur PLUSIEURS unites ? Une attribution
                     CONSTANTE passerait (a)-(c) sans rien attribuer du tout.
  E3 decomp -- `sum(contribs) == total` (auto-verification du decodage de l'accumulateur : si la
               lecture du champ Fix64 etait fausse, l'egalite tomberait), et les etiquettes ont-elles
               la forme `<Playbook>.<CalculateMovementUtilityInSteps...>d__N` ?
  E4 savior -- (montage GREFFE) la contribution etiquetee `SaviorProtocolsPlaybook` apparait-elle
               sur le porteur de 1120 ? C'est l'ouverture de la confrontation de #443-r1a.
  E5 valeur -- LA VALEUR, et elle ne demande PAS la decomposition (#456) : le TOTAL natif est
               confronte a `TriggeredAbilities{,NonOwner}Utility.evaluate` du port sur la MEME
               (unite, tuile). Trois gardes contre l'ACCORD DEGENERE : au moins une valeur native
               non nulle, au moins deux valeurs natives distinctes, puis accord partout.

Les VERDICTS sont des fonctions PURES (`check_channel`, `check_attribution`, `check_decomposition`,
`check_savior`), pour que la garde jumelle offline les exerce SANS live -- y compris la detection du
capteur absent, qu'un test live ne saurait pas distinguer d'un « le terme ne fire pas ».

Usage (depuis scripts/python) :
    python probe_443r1a_triggered_move_anchor.py --state-file <ABSOLU> [--board MC1_67]
                                                 [--seed 777] [--no-graft] [--keep]

ASCII only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

HOST = "http://127.0.0.1:8765"
_HERE = os.path.dirname(os.path.abspath(__file__))

BOARD = "MC1_67"
SEED = "777"
# Le porteur GREFFE de 1120 et son voisinage -- MEMES unites que `probe_443r1_savior_protocols_
# move_term`, importees de lui quand c'est possible, pour qu'aucun des deux ne monte une variante
# de l'autre.
FALLBACK_P_UNITS = ["tauCrisis", "tauAunShi", "tauDarkstrider", "ultraTitus"]
FALLBACK_A_UNITS = ["tauShadowsun", "astraCreed"]
SAVIOR_PLAYBOOK = "SaviorProtocolsPlaybook"

HOOK_NOT_REINJECTED = (
    "NON CONFRONTE -- le capteur #443-r1a n'est PAS charge : le RPC `triggeredMoveTraceStatus` "
    "est inconnu de la session. Le capteur vit dans `frida/hooks/features/triggered-move-trace.ts` "
    "et reste INERTE tant que le bundle n'a pas ete rebuilde ET reinjecte. Rien n'est conclu du "
    "natif : ni « le terme MOVE ne fire pas », ni « l'attribution est impossible ».")


# ------------------------------------------------------------------ verdicts (fonctions PURES)

def check_channel(status) -> dict:
    """Le capteur est-il charge ? On discrimine sur la REPONSE du RPC, pas sur le nombre d'events :
    zero event est ambigu (capteur absent / rien n'a score / le declencheur ne mord pas), la reponse
    du RPC ne l'est pas."""
    if status is None:
        return {"status": "not_reinjected", "message": HOOK_NOT_REINJECTED}
    if not isinstance(status, dict) or "installed" not in status:
        return {"status": "malformed",
                "message": "triggeredMoveTraceStatus a repondu %r -- forme inattendue, rien "
                           "n'est conclu" % (status,)}
    inst = status.get("installed") or {}
    ok = [k for k, v in inst.items() if v == "ok"]
    if not ok:
        return {"status": "not-installed",
                "message": ("capteur CHARGE mais AUCUN hook pose : %s. La resolution runtime a "
                            "echoue (classe utility, state machine nested ou MoveNext introuvable) "
                            "-- c'est une vraie limitation a investiguer, pas un cas pour une "
                            "adresse en dur." % json.dumps(inst))}
    fb = []
    for key, info in (status.get("resolved") or {}).items():
        for f in ((info or {}).get("fallbacks") or []):
            fb.append("%s.%s" % (key, f))
    return {"status": "measured",
            "message": ("capteur charge, %d/%d hooks poses (%s)%s"
                        % (len(ok), len(inst), ", ".join(sorted(ok)),
                           ("" if not fb else
                            " ; ATTENTION champs retombes sur leur REPLI : %s -- la mesure reste "
                            "valide mais n'est plus auto-verifiante" % ", ".join(sorted(fb))))),
            "fallbacks": fb}


def check_attribution(entries, movable_by_unit, pos_by_unit=None) -> dict:
    """LE CRITERE D'ACCEPTATION. `movable_by_unit` = {unitId: set((col,row))} d'`aiMovableTiles` ;
    `pos_by_unit` = {unitId: (col,row)} la position COURANTE.

    (c) est le coeur : ce que le capteur attribue a une unite doit etre EXACTEMENT l'ensemble des
    tuiles que le sweep evalue pour elle. On exige donc l'IDENTITE d'ensemble

        {tuiles vues pour u}  ==  aiMovableTiles(u) UNION {position courante de u}

    et non une simple inclusion : une inclusion laisse passer une attribution qui n'evaluerait
    qu'une tuile sur dix, ou qui rabattrait tout un sweep sur une constante.

    LE TERME `UNION {position courante}` N'EST PAS UN ELARGISSEMENT DE CONFORT (#456). Le natif
    evalue explicitement le fait de RESTER SUR PLACE :
    `IdunBattle.AI.Utilities.UtilityMovementCase$$StaysOnTile` compare
    `EntityExtensions.GetMainTile(case.Unit)` a `UnitPosition.get_MainTile(case + 0x18)` -- la tuile
    candidate PEUT donc etre la tuile courante, et trois playbooks lisent ce predicat. La mesure du
    2026-08-02 (session 10, MC1_67/777, `aiDryRunAllUnits`) le confirme des DEUX cotes :
      * 8 events sur 102 tombaient hors `aiMovableTiles`, et **8/8** portaient EXACTEMENT la
        position courante de leur unite ;
      * controle apparie : `aiMovableTiles` n'inclut la position courante d'AUCUNE des 6 unites.
    Avec le terme, les quatre unites mesurees rendent une identite STRICTE (0 manquante, 0 en trop)
    -- c'est-a-dire un critere PLUS FORT que l'inclusion qu'il remplace, pas plus permissif.

    L'identite n'est exigee que des unites pour lesquelles `aiMovableTiles` a rendu quelque chose :
    sinon on transformerait un trou de reference en echec du capteur."""
    if not entries:
        return {"status": "no-events",
                "message": ("aucun event capte -- le declencheur n'a fait scorer AUCUN mouvement, "
                            "ou le trace n'etait pas arme. RIEN n'est conclu de l'attribution.")}
    pos_by_unit = pos_by_unit or {}
    sans_unite = [e for e in entries if not e.get("unitMeasured") or e.get("unitId") is None]
    sans_tuile = [e for e in entries if e.get("tile") is None]
    # Les evaluations de SPAWN n'ont legitimement pas d'unite (`case.Unit == null`) : le natif y
    # consulte le `Parent`. On les compte a part au lieu de les compter en echec.
    spawns = [e for e in sans_unite if e.get("isSpawning") and e.get("parentId") is not None]
    orphelins = [e for e in sans_unite if e not in spawns]
    vues_par_unite: dict = {}
    for e in entries:
        uid, tile = e.get("unitId"), e.get("tile")
        if uid is None or tile is None:
            continue
        vues_par_unite.setdefault(int(uid), set()).add(
            (int(tile.get("col")), int(tile.get("row"))))
    ecarts, verifiees = [], 0
    for uid, vues in sorted(vues_par_unite.items()):
        reach = movable_by_unit.get(int(uid))
        if not reach:
            continue                       # pas de reference pour CETTE unite -> non verifiable
        ref = set(reach)
        courante = pos_by_unit.get(int(uid))
        if courante is not None:
            ref = ref | {(int(courante[0]), int(courante[1]))}
        verifiees += 1
        if vues != ref:
            ecarts.append((uid, sorted(ref - vues)[:4], sorted(vues - ref)[:4]))
    unites = sorted({e.get("unitId") for e in entries if e.get("unitId") is not None})
    probs = []
    if orphelins:
        probs.append("%d event(s) SANS unite attribuee (et hors regime de spawn) -- le capteur "
                     "publierait de la mesure non attribuable, exactement le trou de "
                     "`scorerTileTermTrace`" % len(orphelins))
    if sans_tuile:
        probs.append("%d event(s) SANS tuile" % len(sans_tuile))
    if ecarts:
        probs.append("%d/%d unite(s) dont l'ensemble de tuiles attribuees DIFFERE de "
                     "`aiMovableTiles UNION {position}` (uid, manquantes, en_trop) : %s -- c'est la "
                     "signature du faux positif de #443-r1"
                     % (len(ecarts), verifiees, ecarts[:4]))
    if len(unites) < 2:
        probs.append("les %d event(s) portent tous la MEME unite (%s) : l'attribution n'est pas "
                     "DISCRIMINEE -- une constante passerait les autres controles"
                     % (len(entries), unites))
    if probs:
        return {"status": "wrong", "message": " | ".join(probs)}
    return {"status": "ok",
            "message": ("%d events, %d unites distinctes, %d spawn(s) ; %d/%d unite(s) dont "
                        "l'ensemble de tuiles attribuees est IDENTIQUE a `aiMovableTiles UNION "
                        "{position courante}`"
                        % (len(entries), len(unites), len(spawns), verifiees, verifiees))}


def check_decomposition(entries, eps: float = 1e-6) -> dict:
    """`sum(contribs) == total` -- l'AUTO-VERIFICATION du decodage. Le total vient de
    `<>2__current`, les contributions du DELTA de l'accumulateur entre deux `MoveNext` : deux
    champs distincts, lus par deux chemins distincts. Leur egalite est donc une contrainte reelle,
    pas une tautologie -- si l'offset de l'accumulateur etait faux, elle tomberait."""
    mesurees = [e for e in entries if e.get("contribs") is not None]
    if not entries:
        return {"status": "no-events", "message": "aucun event -- rien a decomposer"}
    if not mesurees:
        return {"status": "not-measured",
                "message": ("aucun event ne porte de decomposition (`contribs: null`) : "
                            "l'accumulateur ou l'enumerateur interne n'a pas ete resolu. Voir les "
                            "`fallbacks` de E0. Ce n'est PAS « aucune ability n'a contribue ».")}
    mauvais, etiquettes = [], set()
    for e in mesurees:
        somme = sum(float(c.get("value") or 0) for c in e["contribs"])
        if abs(somme - float(e.get("total") or 0)) > eps:
            mauvais.append((e.get("unitId"), e.get("tile"), somme, e.get("total")))
        for c in e["contribs"]:
            etiquettes.add(str(c.get("playbook")))
    inconnues = sorted(x for x in etiquettes if "Playbook" not in x)
    probs = []
    if mauvais:
        probs.append("%d/%d event(s) ou sum(contribs) != total : %s -- le decodage de "
                     "l'accumulateur Fix64 est FAUX" % (len(mauvais), len(mesurees), mauvais[:4]))
    if inconnues:
        probs.append("etiquettes sans `Playbook` dans le nom : %s -- le nom de classe de "
                     "l'iterateur interne n'a pas ete qualifie par son declarant"
                     % inconnues[:6])
    if probs:
        return {"status": "wrong", "message": " | ".join(probs)}
    return {"status": "ok",
            "message": ("%d/%d event(s) decomposes, sum(contribs) == total partout ; playbooks vus "
                        ": %s" % (len(mesurees), len(entries), sorted(etiquettes)[:10]))}


def check_value(rows, eps: float = 1e-6) -> dict:
    """E5 -- LA VALEUR. Le TOTAL yielde par la state machine native, confronte au port.

    Pourquoi cet etage existe SANS attendre la decomposition (#456) : le total natif est la SOMME
    des contributions des triggered abilities du mover, et le port en a l'homologue EXACT --
    `engine/utilities/tile.py::TriggeredAbilitiesUtility.evaluate` (et son jumeau
    `TriggeredAbilitiesNonOwnerUtility.evaluate`), qui bouclent sur `load_playbook(ab)` exactement
    comme `PlaybookDatabase$$LoadPlaybook` dans `<EvaluateMovementInSteps>d__2$$MoveNext`. La
    DECOMPOSITION n'est indispensable que pour imputer un ECART a une ability quand le mover en
    porte plusieurs ; elle ne l'est pas pour confronter la valeur.

    `rows` : une par event confrontable, avec `unitId`, `utility`, `tile`, `nat` (le total publie
    par le capteur) et `port`.

    QUATRE conditions -- les trois premieres sont la pour refuser un ACCORD DEGENERE, qui est
    exactement le vice que ce cas ferme :
      (1) au moins une ligne confrontee ;
      (2) au moins une ligne dont le natif est NON NUL -- « 0 == 0 » sur toute la table ne prouve
          rien du port ;
      (3) au moins DEUX valeurs natives distinctes -- un port qui rendrait une constante egale a
          l'unique valeur native passerait (1)+(2) ;
      (4) accord natif/port sur TOUTES les lignes."""
    if not rows:
        return {"status": "no-rows",
                "message": ("aucune ligne confrontable (pas d'event attribue, ou l'etat du port "
                            "n'a pas pu etre construit) -- RIEN n'est conclu de la valeur")}
    ecarts = [r for r in rows if abs(float(r.get("nat") or 0) - float(r.get("port") or 0)) > eps]
    non_nuls = [r for r in rows if abs(float(r.get("nat") or 0)) > eps]
    distinctes = sorted({round(float(r.get("nat") or 0), 6) for r in rows})
    probs = []
    if not non_nuls:
        probs.append("le natif rend 0 sur les %d ligne(s) : la confrontation est DEGENEREE, un "
                     "port qui rendrait 0 partout passerait" % len(rows))
    if len(distinctes) < 2:
        probs.append("une SEULE valeur native distincte (%s) : le montage ne DISCRIMINE pas -- une "
                     "constante cote port passerait" % distinctes)
    if probs:
        return {"status": "wrong", "message": " | ".join(probs)}
    if not ecarts:
        return {"status": "ok",
                "message": ("%d ligne(s) confrontees, accord natif/port PARTOUT ; %d non nulle(s), "
                            "%d valeur(s) natives distinctes : %s"
                            % (len(rows), len(non_nuls), len(distinctes), distinctes[:8]))}
    # VENTILATION DE L'ECART, et c'est la decomposition par etage appliquee au VERDICT. Un ecart sur
    # une unite qui porte une triggered ability ABSENTE du registre du port n'accuse pas une formule
    # : il accuse un playbook NON PORTE (`load_playbook` rend `None` -> `continue`, exactement comme
    # le natif quand `PlaybookDatabase$$LoadPlaybook` rend null -- sauf qu'ici le natif, lui, en
    # trouve un). Les confondre ferait chercher un bug de calcul la ou il n'y a rien de calcule.
    imputables = [r for r in ecarts if r.get("missing")]
    formule = [r for r in ecarts if not r.get("missing")]
    manquantes = sorted({int(a) for r in imputables for a in (r.get("missing") or ())})
    if formule:
        return {"status": "wrong",
                "message": ("%d/%d ligne(s) en ECART sur des unites dont TOUTES les triggered "
                            "abilities sont au registre -- c'est une divergence de FORMULE : %s"
                            % (len(formule), len(rows),
                               [(r.get("unitId"), r.get("tile"), r.get("utility"),
                                 r.get("nat"), r.get("port")) for r in formule[:5]]))}
    return {"status": "gap",
            "message": ("%d/%d ligne(s) en ecart, TOUTES sur des unites portant une triggered "
                        "ability que le registre MOVE du port NE CHARGE PAS : %s. Le port rend 0 "
                        "par `load_playbook -> None`, le natif rend %s. Ce n'est PAS une "
                        "divergence de FORMULE. Deux causes restent NON DEPARTAGEES a cet etage -- "
                        "(i) le playbook de ces abilities n'est pas porte, (ii) le kit lu par le "
                        "port est plus etroit que l'`AbilitiesComponent` que le natif itere -- et "
                        "les separer exige la DECOMPOSITION (E3), qui attend sa fenetre."
                        % (len(ecarts), len(rows), manquantes,
                           sorted({round(float(r["nat"]), 3) for r in imputables})[:8]))}


def check_savior(entries, carrier_id) -> dict:
    """L'ouverture de la confrontation de #443-r1a : la contribution du playbook de 1120 est-elle
    ATTRIBUEE au porteur, tuile par tuile ?"""
    if carrier_id is None:
        return {"status": "skipped", "message": "porteur de 1120 non identifie (montage --no-graft)"}
    vus = []
    for e in entries:
        if e.get("unitId") != carrier_id:
            continue
        for c in (e.get("contribs") or []):
            if SAVIOR_PLAYBOOK in str(c.get("playbook")):
                vus.append((e.get("tile"), c.get("value")))
    if not vus:
        return {"status": "absent",
                "message": ("aucune contribution `%s` attribuee a u%s. Trois causes possibles, "
                            "NON departagees ici : la greffe de 1120 n'a pas pris, le sweep n'a pas "
                            "evalue de tuile pour ce porteur, ou le playbook n'est pas charge par "
                            "cette voie." % (SAVIOR_PLAYBOOK, carrier_id))}
    return {"status": "ok",
            "message": ("%d contribution(s) `%s` attribuees a u%s, par tuile : %s"
                        % (len(vus), SAVIOR_PLAYBOOK, carrier_id, vus[:8]))}


# ------------------------------------------------------------------ transport

def sid() -> int:
    return int(requests.get(f"{HOST}/api/admin/status", timeout=10).json()["session"]["id"])


def rpc(s: int, method: str, args=None, timeout: int = 60, tolerate_unknown: bool = False):
    r = requests.post(f"{HOST}/api/scripts/{s}/rpc",
                      json={"method": method, "args": [args or {}], "timeout": int(timeout) * 1000},
                      timeout=timeout + 30)
    if r.status_code >= 400:
        if tolerate_unknown:
            return None
        raise RuntimeError("%s HTTP %d: %s" % (method, r.status_code, r.text[:400]))
    body = r.json()
    if body.get("error"):
        if tolerate_unknown:
            return None
        raise RuntimeError(str(body["error"])[:400])
    return body.get("result")


def _movable_by_unit(s: int, rid: int) -> dict:
    """{unitId: set((col,row))} pour les DEUX camps -- la reference de l'etage (c)."""
    out: dict = {}
    for side in ("friendly", "enemy"):
        try:
            mt = rpc(s, "aiMovableTiles", {"runnerId": rid, "side": side}, 60)
        except Exception:
            continue
        for u in ((mt or {}).get("units") or []):
            uid = u.get("unitId")
            if uid is None:
                continue
            out.setdefault(int(uid), set()).update(
                (int(t["col"]), int(t["row"])) for t in (u.get("tiles") or [])
                if t.get("col") is not None)
    return out


def _port_rows(s: int, rid: int, entries) -> list:
    """Evalue COTE PORT le terme MOVE de chaque event attribue, sur la MEME (unite, tuile).

    L'etat du port est reconstruit depuis les canaux de capture (`load_state`), puis pour chaque
    unite on batit son `runner_tile_leaf_ctx` -- l'equivalent du `UtilityMovementCase` reduit a ce
    que les feuilles consomment (`dc.unit`, `dc.parent`). Le premier argument d'`evaluate` est la
    POSITION `(col,row)`, ce que le capteur publie tel quel.

    `meta` (elevation/effets de tuile) n'est PAS lu par ces deux feuilles -- elles ne consomment que
    `tile`, `ctx` et les poids. On passe donc un dict vide plutot qu'un meta a moitie construit qui
    ferait croire a une entree qu'aucune des deux ne lit.

    Rend [] -- et non des lignes fausses -- si un canal manque : E5 dira `no-rows`."""
    from engine.entities.pathfinding.board import Board
    from engine.playbook.adjacent_unit_preference import load_playbook
    from engine.runner.snapshot import live_rpc, load_state
    from engine.utilities.tile import (
        TriggeredAbilitiesNonOwnerUtility, TriggeredAbilitiesUtility, runner_tile_leaf_ctx)
    from engine.weights import load as load_weights

    dv = rpc(s, "decisionView", {"runnerId": rid}, 120)
    ob = rpc(s, "observeBattle", {"runnerId": rid}, 60)
    snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 60)
    bg = rpc(s, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        return []
    # `live_rpc` est OBLIGATOIRE (#363, et #456-r1 pour le kit declenche) : sans transport ambiant,
    # `_auto_ability_states` rend `no-transport` et `runner_tile_leaf_ctx` retombe sur le kit
    # GAMECONFIG -- c'est exactement l'etat aveugle que #456 a mesure (`unit_triggered_abilities`
    # rendait `[1133]` sur une unite dont l'`AbilitiesComponent` porte `[1120, 1030]`).
    with live_rpc(lambda method, args=None, timeout=60: rpc(s, method, args, timeout)):
        state = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    wt = load_weights()
    feuilles = {"TriggeredAbilitiesUtility": TriggeredAbilitiesUtility(),
                "TriggeredAbilitiesNonOwnerUtility": TriggeredAbilitiesNonOwnerUtility()}
    ctx_cache: dict = {}
    rows = []
    for e in entries:
        uid, tile, ut = e.get("unitId"), e.get("tile"), e.get("utility")
        feuille = feuilles.get(ut)
        if uid is None or tile is None or feuille is None:
            continue
        cle = (int(uid), e.get("parentId"))
        if cle not in ctx_cache:
            try:
                ctx_cache[cle] = runner_tile_leaf_ctx(state, int(uid), e.get("parentId"))
            except Exception:
                ctx_cache[cle] = None
        leaf = ctx_cache[cle]
        if leaf is None:
            continue
        try:
            val = float(feuille.evaluate((int(tile["col"]), int(tile["row"])), {}, leaf, wt))
        except Exception:
            continue
        # Les triggered abilities du mover que le registre du port NE CHARGE PAS. C'est ce qui
        # permet a E5 de distinguer un TROU DE PORTAGE d'une divergence de formule -- sans quoi
        # « le port rend 0 » enverrait chercher un bug de calcul dans un chemin ou rien n'est
        # calcule. On ne le renseigne que pour la face OWNER : la face NON-OWNER a son propre
        # registre (`load_playbook_non_owner`) et son propre sujet (les AUTRES unites).
        missing = ()
        if ut == "TriggeredAbilitiesUtility":
            missing = tuple(int(ab) for ab in ((leaf or {}).get("unit_triggered_abilities") or ())
                            if load_playbook(int(ab)) is None)
        rows.append({"unitId": int(uid), "utility": ut,
                     "tile": (int(tile["col"]), int(tile["row"])),
                     "nat": float(e.get("total") or 0), "port": val, "missing": missing})
    return rows


def _graft_seed_bc(tag: str):
    """Greffe 1120 sur `tauCrisis` -- MEME voie que `probe_443r1_savior_protocols_move_term`
    (`catalog_inject.write_grafted_seed_bc`). Sortie dans `logs/`, JAMAIS dans `data/`."""
    import catalog_inject as CI
    out = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "logs",
                       "seedbc-443r1a-%s.json" % tag)
    return CI.write_grafted_seed_bc(out, ["tauCrisis:SaviorProtocols"], replace=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--no-graft", action="store_true",
                    help="ne greffe PAS 1120 (E2/E3 restent pleinement discriminants ; E4 est skip)")
    ap.add_argument("--reuse", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    s = sid()

    # ---- E0 : LE CANAL, AVANT TOUT MONTAGE ------------------------------------------------- #
    # On interroge le RPC en premier : inutile de monter un runner si le capteur n'est pas la.
    st = rpc(s, "triggeredMoveTraceStatus", {}, 30, tolerate_unknown=True)
    v0 = check_channel(st)
    print("E0 canal   [%s] %s" % (v0["status"], v0["message"]))
    if v0["status"] == "not_reinjected":
        print("\nVERDICT: %s" % HOOK_NOT_REINJECTED)
        print("Le MONTAGE, lui, est PRET : ce probe monte le scenario greffe de #443-r1 "
              "(1120 sur tauCrisis, board %s, seed %s) et ses quatre etages sont cables. "
              "Il ne manque que la fenetre." % (a.board, a.seed))
        return 7

    seed_bc = None
    if not a.no_graft:
        try:
            seed_bc, _ = _graft_seed_bc(str(os.getpid()))
        except Exception as e:
            print("   greffe 1120 INDISPONIBLE (%s) -- on continue sans, E4 sera skip" % e)

    if not a.reuse:
        argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
                "--board", a.board, "--state-file", a.state_file,
                "--p-units", ",".join(FALLBACK_P_UNITS),
                "--a-units", ",".join(FALLBACK_A_UNITS)]
        if seed_bc:
            argv += ["--seed-bc", str(seed_bc)]
        out = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if out.returncode != 0:
            print("BUILD FAILED rc=%d" % out.returncode)
            print((out.stdout or "")[-1000:])
            print((out.stderr or "")[-1000:])
            return 1
    rid = json.loads(Path(a.state_file).read_text(encoding="utf-8"))["runnerId"]
    print("runnerId=%s board=%s seed=%s session=%s greffe=%s"
          % (rid, a.board, a.seed, s, bool(seed_bc)))

    verdicts: list = []
    try:
        # ---- E1 : QUEL DECLENCHEUR FAIT FIRER LE HOOK ? ------------------------------------ #
        # On ARME avant tout scoring : le case-443-r1 a mesure qu'un etat DEJA score n'est pas
        # RE-score, donc un trace arme trop tard capte le vide.
        rpc(s, "triggeredMoveTraceClear", {}, 30)
        rpc(s, "triggeredMoveTraceOn", {}, 60)
        essais = [
            ("decisionView(allAbilities,maxRank=32)",
             lambda: rpc(s, "decisionView",
                         {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 120)),
            ("aiMovableTiles(friendly)",
             lambda: rpc(s, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 90)),
            ("aiDryRunAllUnits",
             lambda: rpc(s, "aiDryRunAllUnits", {"runnerId": rid}, 180, tolerate_unknown=True)),
        ]
        avant = 0
        firing = []
        for nom, fn in essais:
            try:
                fn()
            except Exception as e:
                print("   declencheur %-38s ERREUR %s" % (nom, str(e)[:120]))
                continue
            d = rpc(s, "triggeredMoveTraceDump", {"runnerId": rid, "max": 4000}, 60) or {}
            n = len(d.get("entries") or [])
            print("   declencheur %-38s -> %d event(s) cumules" % (nom, n))
            if n > avant:
                firing.append((nom, n - avant))
            avant = n
        print("E1 tir     [%s] %s"
              % ("ok" if firing else "aucun",
                 ("declencheurs qui font firer le hook : %s" % firing) if firing else
                 "AUCUN des declencheurs essayes n'a produit d'event -- a rapporter tel quel"))

        dump = rpc(s, "triggeredMoveTraceDump", {"runnerId": rid, "max": 4000}, 60) or {}
        entries = dump.get("entries") or []
        movable = _movable_by_unit(s, rid)

        # ---- E2/E3/E4 ----------------------------------------------------------------------- #
        # Les positions COURANTES entrent dans la reference de (c) : le sweep evalue aussi le fait
        # de RESTER SUR PLACE (`UtilityMovementCase$$StaysOnTile`), et `aiMovableTiles` ne rend
        # jamais la tuile courante (mesure #456 : 0 unite sur 6).
        carrier, positions = None, {}
        try:
            dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90) or {}
            carrier = next((u["id"] for u in (dv.get("units") or [])
                            if u.get("visualId") == "tauCrisis"), None)
            for u in (dv.get("units") or []):
                p = u.get("pos") or {}
                if p.get("col") is not None and u.get("id") is not None:
                    positions[int(u["id"])] = (int(p["col"]), int(p["row"]))
        except Exception:
            pass
        if a.no_graft or not seed_bc:
            carrier = None

        try:
            prows = _port_rows(s, rid, entries)
        except Exception as e:                                        # noqa: BLE001
            print("   E5 : etat du port INDISPONIBLE (%s)" % str(e)[:160])
            prows = []

        for tag, v in (("E2 attrib ", check_attribution(entries, movable, positions)),
                       ("E3 decomp ", check_decomposition(entries)),
                       ("E4 savior ", check_savior(entries, carrier)),
                       ("E5 valeur ", check_value(prows))):
            print("%s [%s] %s" % (tag, v["status"], v["message"]))
            verdicts.append(v)

        bad = [v for v in verdicts if v["status"] not in ("ok", "skipped")]
        if bad:
            print("\nVERDICT: %d etage(s) NON VERTS -- %s"
                  % (len(bad), " | ".join(v["message"] for v in bad)))
            return 8
        print("\nVERDICT: OK -- le terme MOVE d'une triggered ability est ATTRIBUE (unite + tuile "
              "atteignable par elle) et DECOMPOSE par playbook. La confrontation de #443-r1a est "
              "ouverte.")
        return 0
    finally:
        try:
            rpc(s, "triggeredMoveTraceOff", {}, 30, tolerate_unknown=True)
        except Exception:
            pass
        if not a.keep:
            try:
                subprocess.run([sys.executable, "rl_duel.py", "dispose",
                                "--state-file", a.state_file], cwd=_HERE,
                               capture_output=True, text=True)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
