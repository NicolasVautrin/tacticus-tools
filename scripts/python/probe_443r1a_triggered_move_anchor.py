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

  E0 canal  -- DEUX temps, et les confondre rendait cet etage STRUCTURELLEMENT VIDE (#456-r2).
               (a) AVANT tout montage : le RPC `triggeredMoveTraceStatus` repond-il ? Sinon le
                   capteur n'est pas charge -> NON CONFRONTE, et AUCUN etage suivant ne conclut
                   quoi que ce soit. C'est la seule question qu'on peut poser a ce moment.
               (b) APRES `triggeredMoveTraceOn` : les hooks sont-ils POSES, et surtout quels champs
                   sont retombes sur leur REPLI ? `installed` et `resolved` sont VIDES tant que
                   l'armement n'a pas eu lieu (`install()` n'est appele que par le `On`) -- donc
                   interroger le status avant, comme ce probe le faisait, rendait toujours
                   `not-installed` avec un message accusant a tort la resolution runtime, et ne
                   lisait JAMAIS les `fallbacks`. Or les `fallbacks` sont exactement le canal
                   d'auto-verification que #456 SS3.4 a mis en place apres y avoir trouve un faux
                   silencieux. Un canal de diagnostic dont le verdict est vide se lit comme un
                   succes : c'est le vice de ce cas, deplace d'un cran.
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
               lecture du champ Fix64 etait fausse, l'egalite tomberait), les etiquettes ont-elles
               la forme `<Playbook>.<CalculateMovementUtilityInSteps...>d__N` -- et le regime
               est-il NON DEGENERE (#456-r2) : au moins un event ou DEUX playbooks DISTINCTS
               contribuent. Sans cette derniere garde, `sum(contribs) == total` se reduit a
               `contrib == total` sur un seul terme : le canal `contribs` n'a alors jamais SEPARE
               quoi que ce soit, alors que separer est la seule raison pour laquelle il existe
               (`ai-trace` L3 donne deja le total). MESURE le 2026-08-04 sur le montage de
               reference d'alors (1120 sur `tauCrisis`, `replace=True`) : 102 events,
               distribution {1 contribution: 9, 0: 93}, **ZERO** event a deux contributions --
               E3 rendait donc `ok` sur un regime ou la decomposition ne decomposait rien.
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
from contextlib import contextmanager
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

# ═══ DEUX MONTAGES, ET POURQUOI DEUX (#456-r2) ═══════════════════════════════════════════════
# Un seul montage ne peut pas porter les deux criteres, parce qu'ils exigent des regimes qui
# s'excluent -- et le decouvrir a demande une mesure, pas un raisonnement.
#
# MONO -- 1120 greffee sur `tauCrisis` SEUL, `replace=True`. Le montage de #443-r1a, inchange.
#   `tauCrisis` porte une arme RANGED, donc
#   `IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook$$FilterMovementTiles` court-circuite sur
#   son `if (UnitExtensions.HasRangedWeapon(unit)) return;` : AUCUNE tuile candidate n'est
#   retiree, et l'identite d'ensemble de E2 est donc EXACTE. Mesure : 4/4 unites, 0 manquante,
#   0 en trop.
#
# DOUBLE -- 1120 greffee EN PLUS sur `tauAunShi`, `replace=False` pour qu'il GARDE
#   `1145 SereneUnifier`. C'est le seul regime ou DEUX playbooks contribuent a la MEME evaluation,
#   donc le seul ou `sum(contribs) == total` est une contrainte a deux termes (E3).
#   ⚠ `replace=False` est LOAD-BEARING : avec `replace=True`, `tauAunShi` perdrait `1145` et l'on
#   retomberait a une contribution par event. Mesure du 2026-08-04 : `replace=True` ->
#   distribution {1 contribution: 9, 0: 93}, ZERO event a deux ; `replace=False` -> 4 events a
#   DEUX contributions (u83 (0,0) total 323 = SaviorProtocols 20 + SereneUnifier 303).
#
# ⚠ POURQUOI L'IDENTITE DE E2 N'EST PAS EXIGEE SUR LE MONTAGE DOUBLE, et ce n'est PAS un
# assouplissement de confort : `tauAunShi` est un heros de MELEE, donc le court-circuit
# `HasRangedWeapon` ne mord pas et `FilterMovementTiles` RESTREINT reellement les tuiles
# candidates. Mesure du 2026-08-04, REPRODUCTIBLE a l'identique sur deux passes : u83 perd
# EXACTEMENT une tuile, (0,3), sur les DEUX utilities (owner ET non-owner) -- 11 -> 10 tuiles,
# 102 -> 100 events -- pendant que u81 (ranged, MEME greffe) garde ses 12/12. Le filtre est le
# SEUL hook par lequel une ability retire des tuiles candidates (slot 1 d'`IPlaybook`, qui ne peut
# que restreindre), et la seule difference entre les deux montages est cette greffe.
# C'est donc une observation du residu `#443-r1b` -- que `case-443-r1` SS5 declarait INERTE faute
# de porteur sans arme a distance -- et non un defaut du capteur. Exiger l'identite ici ferait
# rougir un capteur JUSTE sur un comportement natif CORRECT.
MONO_SPECS = ["tauCrisis:SaviorProtocols"]
DOUBLE_SPECS = ["tauCrisis:SaviorProtocols", "tauAunShi:SaviorProtocols"]

HOOK_NOT_REINJECTED = (
    "NON CONFRONTE -- le capteur #443-r1a n'est PAS charge : le RPC `triggeredMoveTraceStatus` "
    "est inconnu de la session. Le capteur vit dans `frida/hooks/features/triggered-move-trace.ts` "
    "et reste INERTE tant que le bundle n'a pas ete rebuilde ET reinjecte. Rien n'est conclu du "
    "natif : ni « le terme MOVE ne fire pas », ni « l'attribution est impossible ».")


# ------------------------------------------------------------------ verdicts (fonctions PURES)

def check_presence(status) -> dict:
    """E0(a) -- LA SEULE question posable AVANT l'armement : le RPC existe-t-il ?

    `install()` n'est appele que par `triggeredMoveTraceOn` ; avant lui, `installed` et `resolved`
    sont VIDES par construction. Poser ici la question de E0(b) -- « les hooks sont-ils poses ? » --
    rend donc invariablement `not-installed`, avec un message qui accuse a tort la resolution
    runtime, ET sans jamais lire les `fallbacks` (le canal d'auto-verification de #456 SS3.4).
    C'est le defaut que #456-r2 ferme : un etage de diagnostic dont le verdict etait
    structurellement vide, et que le probe rendait pourtant AVANT de conclure `VERDICT: OK`."""
    if status is None:
        return {"status": "not_reinjected", "message": HOOK_NOT_REINJECTED}
    if not isinstance(status, dict) or "installed" not in status:
        return {"status": "malformed",
                "message": "triggeredMoveTraceStatus a repondu %r -- forme inattendue, rien "
                           "n'est conclu" % (status,)}
    return {"status": "present",
            "message": ("RPC `triggeredMoveTraceStatus` present -- le capteur est CHARGE. "
                        "Les hooks ne sont pas encore poses (`install()` n'a lieu qu'au "
                        "`triggeredMoveTraceOn`) : leur verdict est celui de E0b.")}


def check_channel(status) -> dict:
    """E0(b) -- APRES l'armement. On discrimine sur la REPONSE du RPC, pas sur le nombre d'events :
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
    if fb:
        # NON VERT, et c'est un durcissement de #456-r2. Un champ retombe sur son repli reste LU --
        # le repli est un offset du decompile, pas une invention -- mais le capteur n'est plus
        # AUTO-VERIFIANT, et c'est precisement dans cet angle mort que #456 SS3.4 avait trouve un
        # faux silencieux (`innerEnum` resolu sur l'enumerateur EXTERNE, hors `fallbacks`). Laisser
        # passer un repli en vert ferait publier des chiffres dont on ne sait plus s'ils mesurent
        # ce qu'ils disent. E3 n'attrape que les replis `acc`/`innerEnum` (via `contribs: null`) :
        # `caseArg`, `state`, `current` ou les offsets du `UtilityMovementCase` passeraient sinon
        # inapercus.
        return {"status": "degraded",
                "message": ("capteur charge, %d/%d hooks poses (%s), MAIS des champs sont retombes "
                            "sur leur REPLI : %s -- la mesure n'est plus auto-verifiante. Publier "
                            "des chiffres dans cet etat, c'est publier ce qu'on ne peut plus "
                            "verifier. Lire les `fields` de `triggeredMoveTraceStatus` : ils "
                            "donnent la disposition REELLE de la state machine sur ce build."
                            % (len(ok), len(inst), ", ".join(sorted(ok)), ", ".join(sorted(fb)))),
                "fallbacks": fb}
    return {"status": "measured",
            "message": ("capteur charge, %d/%d hooks poses (%s) ; AUCUN repli -- tous les champs "
                        "resolus par nom ou par STRUCTURE, la mesure est auto-verifiante"
                        % (len(ok), len(inst), ", ".join(sorted(ok)))),
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
    multi = []
    for e in mesurees:
        somme = sum(float(c.get("value") or 0) for c in e["contribs"])
        if abs(somme - float(e.get("total") or 0)) > eps:
            mauvais.append((e.get("unitId"), e.get("tile"), somme, e.get("total")))
        noms = {str(c.get("playbook")) for c in e["contribs"]}
        if len(noms) >= 2:
            multi.append(e)
        etiquettes |= noms
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
    # LA GARDE ANTI-DEGENERESCENCE (#456-r2) -- le pendant exact de la condition (3) de
    # `check_value`. Tant qu'aucun event ne porte DEUX playbooks distincts, `sum(contribs) == total`
    # se reduit a `contrib == total` : on verifie que l'accumulateur final egale `<>2__current`,
    # mais on ne verifie JAMAIS que le canal SEPARE deux abilities -- la seule chose qu'il apporte
    # sur `ai-trace` L3 (qui donne deja le total). Un montage a un seul contributeur rendait donc
    # E3 vert sans avoir rien decompose : mesure du 2026-08-04, 102 events, 9 a une contribution,
    # 93 a zero, aucun a deux.
    if not multi:
        return {"status": "degenerate",
                "message": ("%d/%d event(s) decomposes et sum(contribs) == total partout, MAIS "
                            "AUCUN event ne porte DEUX playbooks distincts (max observe : %d "
                            "contribution(s) sur un meme event). La decomposition n'a donc jamais "
                            "SEPARE quoi que ce soit : a un seul terme, `sum(contribs) == total` "
                            "n'est que `contrib == total`. Monter un mover portant DEUX triggered "
                            "abilities a playbook MOVE porte (cf. `GRAFT_SPECS`). Playbooks vus : "
                            "%s" % (len(mesurees), len(entries),
                                    max((len({str(c.get('playbook')) for c in e['contribs']})
                                         for e in mesurees), default=0),
                                    sorted(etiquettes)[:10]))}
    exemple = [(e.get("unitId"), e.get("tile"), e.get("total"),
                [(str(c["playbook"]).split(".")[0], c["value"]) for c in e["contribs"]])
               for e in multi[:2]]
    return {"status": "ok",
            "message": ("%d/%d event(s) decomposes, sum(contribs) == total partout ; %d event(s) a "
                        "DEUX playbooks distincts ou plus (regime NON degenere), ex. %s ; playbooks "
                        "vus : %s" % (len(mesurees), len(entries), len(multi), exemple,
                                      sorted(etiquettes)[:10]))}


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


@contextmanager
def _no_binder():
    """CONTRE-EPREUVE du cablage #456-r1 : aucun transport ambiant, donc `_auto_ability_states`
    rend `no-transport` et le port lit le kit GAMECONFIG. C'est l'etat exact d'avant le cablage --
    et sans ce bras, rien ne dirait si le canal deplace la moindre valeur."""
    yield None


def _port_rows(s: int, rid: int, entries, bind: bool = True) -> list:
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
    binder = ((lambda: live_rpc(lambda m, ar=None, to=60: rpc(s, m, ar, to)))
              if bind else _no_binder)
    with binder():
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


def _graft_seed_bc(tag: str, specs, replace: bool):
    """Greffe `specs` -- MEME voie que `probe_443r1_savior_protocols_move_term`
    (`catalog_inject.write_grafted_seed_bc`). Sortie dans `logs/`, JAMAIS dans `data/`."""
    import catalog_inject as CI
    out = os.path.join(os.path.dirname(os.path.dirname(_HERE)), "logs",
                       "seedbc-443r1a-%s.json" % tag)
    return CI.write_grafted_seed_bc(out, specs, replace=replace)


def _build(a, state_file: str, seed_bc) -> int:
    """Monte le runner et rend son `runnerId`. Leve si le build echoue -- jamais un id devine."""
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(a.seed),
            "--board", a.board, "--state-file", state_file,
            "--p-units", ",".join(FALLBACK_P_UNITS),
            "--a-units", ",".join(FALLBACK_A_UNITS)]
    if seed_bc:
        argv += ["--seed-bc", str(seed_bc)]
    out = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError("BUILD FAILED rc=%d\n%s\n%s"
                           % (out.returncode, (out.stdout or "")[-800:],
                              (out.stderr or "")[-800:]))
    return json.loads(Path(state_file).read_text(encoding="utf-8"))["runnerId"]


def _collect(s: int, rid: int, essais: bool = False) -> dict:
    """Arme le trace, declenche le sweep, et rend tout ce que les etages consomment.

    `essais=True` essaie PLUSIEURS declencheurs et rapporte lequel fait firer le hook (E1) : c'est
    l'information dont #443-r1 manquait. Sinon on ne joue que le declencheur qui MORD, mesure
    (`aiDryRunAllUnits`) -- le sweep de mouvement n'est parcouru que par un tour d'IA."""
    rpc(s, "triggeredMoveTraceClear", {}, 30)
    rpc(s, "triggeredMoveTraceOn", {}, 60)
    firing = []
    if essais:
        avant = 0
        for nom, fn in (
            ("decisionView(allAbilities,maxRank=32)",
             lambda: rpc(s, "decisionView",
                         {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 120)),
            ("aiMovableTiles(friendly)",
             lambda: rpc(s, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 90)),
            ("aiDryRunAllUnits",
             lambda: rpc(s, "aiDryRunAllUnits", {"runnerId": rid}, 180, tolerate_unknown=True)),
        ):
            try:
                fn()
            except Exception as e:                                     # noqa: BLE001
                print("   declencheur %-38s ERREUR %s" % (nom, str(e)[:120]))
                continue
            d = rpc(s, "triggeredMoveTraceDump", {"runnerId": rid, "max": 4000}, 60) or {}
            n = len(d.get("entries") or [])
            print("   declencheur %-38s -> %d event(s) cumules" % (nom, n))
            if n > avant:
                firing.append((nom, n - avant))
            avant = n
    else:
        rpc(s, "aiDryRunAllUnits", {"runnerId": rid}, 180, tolerate_unknown=True)
    dump = rpc(s, "triggeredMoveTraceDump", {"runnerId": rid, "max": 4000}, 60) or {}
    entries = dump.get("entries") or []
    # Les positions COURANTES entrent dans la reference de E2(c) : le sweep evalue aussi le fait de
    # RESTER SUR PLACE (`UtilityMovementCase$$StaysOnTile`), et `aiMovableTiles` ne rend jamais la
    # tuile courante (mesure #456 : 0 unite sur 6).
    carrier, positions = None, {}
    try:
        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1}, 90) or {}
        carrier = next((u["id"] for u in (dv.get("units") or [])
                        if u.get("visualId") == "tauCrisis"), None)
        for u in (dv.get("units") or []):
            p = u.get("pos") or {}
            if p.get("col") is not None and u.get("id") is not None:
                positions[int(u["id"])] = (int(p["col"]), int(p["row"]))
    except Exception:                                                  # noqa: BLE001
        pass
    return {"rid": rid, "entries": entries, "firing": firing, "carrier": carrier,
            "positions": positions, "movable": _movable_by_unit(s, rid)}


def _dispose(state_file: str) -> None:
    try:
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", state_file],
                       cwd=_HERE, capture_output=True, text=True)
    except Exception:                                                  # noqa: BLE001
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--no-graft", action="store_true",
                    help="ne greffe PAS 1120 : le montage MONO est joue sans greffe (E1/E2/E5 "
                         "restent discriminants), le montage DOUBLE n'est pas joue (E3/E4 skip)")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    s = sid()

    # ---- E0(a) : LA PRESENCE, AVANT TOUT MONTAGE -------------------------------------------- #
    # On interroge le RPC en premier : inutile de monter un runner si le capteur n'est pas la.
    # ⚠ La SEULE question posable ici est « le RPC existe-t-il » : `installed`/`resolved` restent
    # vides tant que `triggeredMoveTraceOn` n'a pas appele `install()`. Le verdict sur les hooks et
    # sur les REPLIS est celui de E0(b), plus bas, apres l'armement (#456-r2).
    st = rpc(s, "triggeredMoveTraceStatus", {}, 30, tolerate_unknown=True)
    v0 = check_presence(st)
    print("E0a presence [%s] %s" % (v0["status"], v0["message"]))
    if v0["status"] == "not_reinjected":
        print("\nVERDICT: %s" % HOOK_NOT_REINJECTED)
        print("Le MONTAGE, lui, est PRET : ce probe monte le scenario greffe de #443-r1 "
              "(1120 sur tauCrisis, board %s, seed %s) et ses quatre etages sont cables. "
              "Il ne manque que la fenetre." % (a.board, a.seed))
        return 7

    mono_bc = None
    if not a.no_graft:
        try:
            mono_bc, _ = _graft_seed_bc("mono-%s" % os.getpid(), MONO_SPECS, True)
        except Exception as e:                                         # noqa: BLE001
            print("   greffe 1120 INDISPONIBLE (%s) -- on continue sans, E4 sera skip" % e)

    verdicts: list = []
    state2 = "%s.double.json" % a.state_file
    try:
        # ═══ MONTAGE MONO -- E1 (declencheur), E2 (attribution), E5 (valeur) ═══════════════════
        # `FilterMovementTiles` y est INERTE (`tauCrisis` est ranged), donc l'identite d'ensemble
        # de E2 est exacte. Cf. le bloc `MONO_SPECS` / `DOUBLE_SPECS`.
        rid = _build(a, a.state_file, mono_bc)
        print("[MONO]   runnerId=%s board=%s seed=%s session=%s greffe=%s"
              % (rid, a.board, a.seed, s, bool(mono_bc)))
        # On ARME avant tout scoring : le case-443-r1 a mesure qu'un etat DEJA score n'est pas
        # RE-score, donc un trace arme trop tard capte le vide.
        m = _collect(s, rid, essais=True)

        # ---- E0(b) : LE CANAL, UNE FOIS ARME ------------------------------------------------ #
        # C'est ICI que `installed` et `resolved` existent, donc ICI que les REPLIS sont lisibles.
        # Ce verdict entre dans `verdicts` : avant #456-r2, E0 etait imprime mais n'entrait dans
        # AUCUN critere de sortie (seul `not_reinjected` sortait, en rc 7) -- un capteur pose sur
        # des offsets de repli aurait donc rendu `VERDICT: OK`.
        v0b = check_channel(rpc(s, "triggeredMoveTraceStatus", {}, 30, tolerate_unknown=True))
        print("E0b canal    [%s] %s" % (v0b["status"], v0b["message"]))
        verdicts.append(v0b)

        print("E1 tir       [%s] %s"
              % ("ok" if m["firing"] else "aucun",
                 ("declencheurs qui font firer le hook : %s" % m["firing"]) if m["firing"] else
                 "AUCUN des declencheurs essayes n'a produit d'event -- a rapporter tel quel"))

        try:
            prows = _port_rows(s, rid, m["entries"])
        except Exception as e:                                         # noqa: BLE001
            print("   E5 : etat du port INDISPONIBLE (%s)" % str(e)[:160])
            prows = []

        for tag, v in (("E2 attrib  ", check_attribution(m["entries"], m["movable"],
                                                         m["positions"])),
                       ("E5 valeur  ", check_value(prows))):
            print("%s [%s] %s" % (tag, v["status"], v["message"]))
            verdicts.append(v)
        _dispose(a.state_file)                    # on libere AVANT de monter le second runner

        # ═══ MONTAGE DOUBLE -- E3 (decomposition NON degeneree), E4 (SaviorProtocols) ══════════
        if a.no_graft:
            for tag in ("E3 decomp  ", "E4 savior  "):
                v = {"status": "skipped",
                     "message": "montage DOUBLE non joue (--no-graft) : la decomposition exige un "
                                "mover portant DEUX triggered abilities a playbook MOVE porte"}
                print("%s [%s] %s" % (tag, v["status"], v["message"]))
                verdicts.append(v)
        else:
            double_bc, _ = _graft_seed_bc("double-%s" % os.getpid(), DOUBLE_SPECS, False)
            rid2 = _build(a, state2, double_bc)
            print("[DOUBLE] runnerId=%s -- 1120 greffee AUSSI sur tauAunShi (replace=False, il "
                  "GARDE 1145)" % rid2)
            d = _collect(s, rid2)
            # L'attribution est RE-MESUREE ici, mais en INFORMATION : sur ce montage
            # `FilterMovementTiles` mord (tauAunShi est en melee) et retire des tuiles candidates,
            # donc l'identite d'ensemble ne peut pas etre exigee -- ce serait faire rougir un
            # capteur JUSTE sur un comportement natif CORRECT (#443-r1b). On l'imprime pour que
            # l'ecart reste VISIBLE et chiffre, jamais tu.
            va = check_attribution(d["entries"], d["movable"], d["positions"])
            print("   (info) attribution sur le montage DOUBLE [%s] %s" % (va["status"],
                                                                          va["message"]))
            for tag, v in (("E3 decomp  ", check_decomposition(d["entries"])),
                           ("E4 savior  ", check_savior(d["entries"], d["carrier"]))):
                print("%s [%s] %s" % (tag, v["status"], v["message"]))
                verdicts.append(v)
            _dispose(state2)

        # `measured` est le vert de E0b (`check_channel`), `ok` celui des autres etages.
        bad = [v for v in verdicts if v["status"] not in ("ok", "skipped", "measured")]
        if bad:
            print("\nVERDICT: %d etage(s) NON VERTS -- %s"
                  % (len(bad), " | ".join(v["message"] for v in bad)))
            return 8
        print("\nVERDICT: OK -- le terme MOVE d'une triggered ability est ATTRIBUE (unite + tuile "
              "atteignable par elle) et DECOMPOSE par playbook, dans un regime ou DEUX playbooks "
              "contribuent a la meme evaluation. La confrontation de #443-r1a est ouverte.")
        return 0
    except RuntimeError as e:                                          # build casse
        print(str(e))
        return 1
    finally:
        try:
            rpc(s, "triggeredMoveTraceOff", {}, 30, tolerate_unknown=True)
        except Exception:                                              # noqa: BLE001
            pass
        if not a.keep:
            _dispose(a.state_file)
            _dispose(state2)


if __name__ == "__main__":
    raise SystemExit(main())
