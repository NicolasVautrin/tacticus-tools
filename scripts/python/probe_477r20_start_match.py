#!/usr/bin/env python3
"""#477-r20 -- `System_StartMatch` : l'ENVELOPPE confrontee, le CONTENU chiffre.

    python probe_477r20_start_match.py [--session N] [--boards C1_02,MC1_67] [--tours 2]

CE QU'IL MESURE, ET POURQUOI IL NE MESURE PAS TOUT
--------------------------------------------------
`System_StartMatch` est, apres `User_UseAbility`, le plus gros groupe du deroule : 477 lignes
sur le flux temoin. Les deux crans precedents portaient un groupe dont le CONTENU etait deja
emis (`User_PlaceUnit` : le meme `Group=AddUnit` que le setup) ou VIDE
(`System_ProcessRemovals`). Ici ni l'un ni l'autre : ce que
`IdunBattle.Operations.StartMatchOperation$$Execute` ecrit apres sa premiere action n'est porte
NULLE PART cote flux. Ce probe rend donc DEUX choses, et les separe :

  ETAGE TEXTE       l'ENVELOPPE + `Action=StartMatch` a l'EGALITE BRUTE ligne a ligne, meme
                    cliquet a trois etats que #477-r15a. La DECOUPE est structurelle et
                    VERIFIEE, jamais ajustee au port (cf. `decouper` ci-dessous), et l'ecart
                    est impute a l'EGALITE EXACTE : `1 + 1 + contenu + 1 == total` ;
  ETAGE ANCRAGE     quatre predictions DERIVEES du decompile, dont deux discriminantes : le
                    PREMIER `Group=StartTurn` et le PREMIER `Action=PrepareTurn` du flux entier
                    sont DANS ce groupe -- consequence lue du dernier appel de l'operation
                    (`ContinueTurnPhase`), et contraste mesurable avec toutes leurs occurrences
                    suivantes, qui sont racines ou a profondeur 0 ;
  ETAGE ENTITE      le natif obtient l'entite du groupe par TROIS expressions distinctes
                    (`GetMatchEntity(state).Id` a l'ouverture, un litteral pour l'`Action=`, et
                    le litteral de `SetupGameOperation$$Execute` pour `System_GameSetup`). Le
                    probe exige qu'elles coincident : c'est un recoupement, pas une supposition ;
  ETAGE CONTENU     la DECOMPOSITION chiffree de ce qui reste dehors, ventilee -- et en
                    particulier ce que cette tranche fait, ou ne fait pas, pour `Effect_Refresh`.

⚠ CE PROBE NE PEUT PAS RENDRE « VERT » SUR LE CONTENU, ET C'EST VOULU. Un comparateur qui
amputerait le natif de ce que le port ne sait pas produire, sans le dire, serait la projection
implicite que `conformance` existe pour interdire. L'amputation est donc CHIFFREE, ENUMEREE, et
son total est confronte au total du groupe.

DISCIPLINE : deux boards de TAILLES DIFFERENTES, un runner a la fois, dispose dans le `finally`,
state-files sous `logs/`. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe_477r15a_stream_conformance as R15A  # noqa: E402
import probe_477r19_process_removals as R19  # noqa: E402
from engine.streams import GroupType, StepType, StreamCache, StreamDispatcher, TagKey  # noqa: E402
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.game_setup import MATCH_ENTITY_ID  # noqa: E402
from engine.streams.input_messages import (START_MATCH_SOURCE_ID,  # noqa: E402
                                           visit_start_battle_message)

ROOT = HERE.parents[1]
OUT = ROOT / "logs"

MesureImpossible = R15A.MesureImpossible

#: Les memes deux boards que #477-r15a / -r18-r5 / -r19 : tailles DIFFERENTES (35 vs 63 tuiles).
#: Un seul board ne prouverait rien -- au cran 2 une regle rendait 3/3 exact sur `C1_02` et a ete
#: REFUTEE au premier run sur `MC1_67`.
BOARDS_DEFAUT = ("C1_02", "MC1_67")

CIBLE = GroupType.System_StartMatch
#: Les seuls groupes racines qui peuvent PRECEDER la cible : ceux des messages d'entree que le
#: montage envoie AVANT `StartBattleMessage` (`SetupGameMessage`, puis un `AddUnitMessage` par
#: unite deployee). C'est une propriete du MONTAGE, pas du natif -- elle est donc nommee en
#: borne (c) au rapport, et sert de prediction FALSIFIABLE, pas de preuve.
RACINES_AVANT = frozenset((GroupType.System_GameSetup.name, GroupType.User_PlaceUnit.name))


def profondeur(ligne: str) -> int:
    return (len(ligne) - len(ligne.lstrip(" "))) // 4


def decouper(texte_groupe: str) -> dict:
    """LA DECOUPE, structurelle et VERIFIEE -- c'est le point ou un probe complaisant tricherait.

    Elle n'est PAS « tout ce que le port n'emet pas » : elle est lue dans
    `IdunBattle.Operations.StartMatchOperation$$Execute`, qui emet dans cet ordre
    (1) une `Action` de `StepType.StartMatch` a dictionnaire VIDE, puis (2) tout le reste. Le
    port porte l'enveloppe et (1). La decoupe est donc : entete, PREMIERE ligne de profondeur 1,
    reste, `Finish_Group` final.

    Quatre choses sont VERIFIEES, chacune capable de faire rougir la tranche :
      * l'entete est bien un `Group=` de la cible a profondeur 0 ;
      * la PREMIERE ligne de profondeur 1 est bien `Action=StartMatch` -- si le natif y mettait
        autre chose, la lecture serait fausse et le probe le dirait ;
      * cette action ne porte AUCUN `Tag=` -- le dictionnaire est VIDE dans le decompile ;
      * la derniere ligne est le `Finish_Group` de profondeur 0.
    Et le total est confronte : `1 + 1 + len(contenu) + 1 == len(bloc)`."""
    lignes = [l for l in texte_groupe.split("\n") if l != ""]
    if len(lignes) < 3:
        raise MesureImpossible("groupe `%s` de %d ligne(s) -- trop court pour etre decoupe"
                               % (CIBLE.name, len(lignes)))
    entete, fin = lignes[0], lignes[-1]
    m = CONF.RE_GROUP.match(entete)
    if not m or m.group("sym") != CIBLE.name or profondeur(entete) != 0:
        raise MesureImpossible("l'entete du bloc n'est pas un `Group=%s` de profondeur 0 : [%s]"
                               % (CIBLE.name, entete))
    if not CONF.RE_FINISH.match(fin) or profondeur(fin) != 0:
        raise MesureImpossible("la derniere ligne n'est pas un `Finish_Group` de profondeur 0")
    premiere = lignes[1]
    ma = CONF.RE_ACTION.match(premiere)
    porte = (ma is not None and profondeur(premiere) == 1
             and ma.group("sym") == StepType.StartMatch.name)
    # Les `Tag=` d'une action sont ecrits a profondeur 2 IMMEDIATEMENT apres elle
    # (`StreamCache$$Action` les ecrit d'un bloc) : on avance tant qu'on en voit.
    tags_action: list = []
    k = 2
    while k < len(lignes) - 1 and CONF.RE_TAG.match(lignes[k]) and profondeur(lignes[k]) == 2:
        tags_action.append(lignes[k])
        k += 1
    contenu = lignes[2 + len(tags_action):-1]
    return {
        "lignes": lignes, "entete": entete, "fin": fin, "action": premiere,
        "action_est_start_match": porte, "tags_action": tags_action, "contenu": contenu,
        "entite_entete": m.group("entity"), "source_entete": m.group("source"),
        "entite_action": (ma.group("entity") if ma else ""),
        "somme_exacte": (1 + 1 + len(tags_action) + len(contenu) + 1) == len(lignes),
        "texte_ampute": "\n".join([entete, premiere] + tags_action + [fin]) + "\n",
    }


def ventiler(contenu: list) -> dict:
    """Ce qui reste DEHORS, ventile par sous-arbre de profondeur 1 et par forme.

    La ventilation est ce qui rend l'amputation VERIFIABLE : `sum(lignes des sous-arbres) +
    lignes isolees == len(contenu)`, imprime a chaque run."""
    sous_arbres, formes, isolees = [], {}, 0
    i, n = 0, len(contenu)
    while i < n:
        l = contenu[i]
        m = CONF.RE_GROUP.match(l)
        if m and profondeur(l) == 1:
            pile, j = 0, i
            while j < n:
                if CONF.RE_GROUP.match(contenu[j]):
                    pile += 1
                elif CONF.RE_FINISH.match(contenu[j]):
                    pile -= 1
                    if pile == 0:
                        break
                j += 1
            sous_arbres.append((m.group("sym"), m.group("source"), j - i + 1))
            i = j + 1
            continue
        isolees += 1
        i += 1
    for l in contenu:
        for nom, rx in (("Group", CONF.RE_GROUP), ("Action", CONF.RE_ACTION),
                        ("Tag", CONF.RE_TAG)):
            m = rx.match(l)
            if m:
                formes["%s=%s" % (nom, m.group("sym"))] = \
                    formes.get("%s=%s" % (nom, m.group("sym")), 0) + 1
                break
        else:
            if CONF.RE_FINISH.match(l):
                formes["Finish_Group"] = formes.get("Finish_Group", 0) + 1
    total_arbres = sum(t for _s, _src, t in sous_arbres)
    return {"sous_arbres": sous_arbres, "formes": formes, "isolees": isolees,
            "total_arbres": total_arbres,
            "somme_exacte": total_arbres + isolees == len(contenu)}


def profondeurs_effect_refresh(texte_groupe: str) -> dict:
    """CE QUE LA TRANCHE FAIT -- OU NE FAIT PAS -- POUR `Effect_Refresh` (#477-r19-r2).

    Le cran precedent a nomme `System_StartMatch` comme DEBLOQUEUR d'`Effect_Refresh` (42 / 147).
    La mesure ici est plus fine, et c'est elle qui tranche : un `Effect_Refresh` n'est comparable
    que si TOUT le chemin de la racine jusqu'a lui est emis, pas seulement la racine. Le probe
    ventile donc les occurrences par PROFONDEUR et par CHEMIN, et compte celles que l'enveloppe
    seule rend atteignables."""
    lignes = [l for l in texte_groupe.split("\n") if l != ""]
    pile: list = []
    par_profondeur: dict = {}
    par_chemin: dict = {}
    for l in lignes:
        m = CONF.RE_GROUP.match(l)
        if m:
            pile.append(m.group("sym"))
            if m.group("sym") == GroupType.Effect_Refresh.name:
                p = len(pile) - 1
                par_profondeur[p] = par_profondeur.get(p, 0) + 1
                chemin = " > ".join(pile[:-1])
                par_chemin[chemin] = par_chemin.get(chemin, 0) + 1
        elif CONF.RE_FINISH.match(l):
            if pile:
                pile.pop()
    total = sum(par_profondeur.values())
    # Atteignable par l'enveloppe SEULE = les occurrences dont le chemin ne contient QUE des
    # groupes que le port emet. Le port n'emet que la racine : seules celles de profondeur 1
    # auraient un chemin porte -- et encore leur CONTENU resterait a produire.
    chemin_porte = sum(n for c, n in par_chemin.items() if c == CIBLE.name)
    return {"total": total, "par_profondeur": par_profondeur, "par_chemin": par_chemin,
            "chemin_porte": chemin_porte}


class Capture:
    """Un `IStreamCacheListener` : ne garde que les groupes RACINE flushes."""

    def __init__(self) -> None:
        self.racines: list = []

    def on_root_group_finished(self, group: str) -> None:
        self.racines.append(group)

    def on_log(self, chunk: str) -> None:
        pass


def emettre(match_entity_id: int = MATCH_ENTITY_ID, mutation: str = "") -> tuple:
    """Emet l'enveloppe `System_StartMatch` et rend `(texte, nb de racines)`.

    `mutation` est le levier de la CONTRE-EPREUVE. Un flux emis qui reste EGAL au natif apres
    qu'on a casse le port ne prouve rien : chaque mutation doit rougir, ET le probe verifie
    qu'elle a bien change le texte. Au cran precedent une mutation N'A PAS ROUGI parce qu'elle
    ajoutait un groupe qui COMPENSAIT celui qu'elle retirait -- c'est le garde du garde
    (`a_morde` separe du verdict) qui l'a rendu visible."""
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    if mutation == "enveloppe":
        pass                      # rien emis la ou le natif ouvre un groupe
    elif mutation == "entite":
        events.start_group(CIBLE, match_entity_id + 1, START_MATCH_SOURCE_ID, None)
        events.action(StepType.StartMatch, match_entity_id + 1, {})
        events.finish_group()
    elif mutation == "source":
        events.start_group(CIBLE, match_entity_id, CIBLE.name, None)
        events.action(StepType.StartMatch, match_entity_id, {})
        events.finish_group()
    elif mutation == "action":
        # L'`Action=StartMatch` omise : l'enveloppe seule, comme au cran `System_ProcessRemovals`.
        events.start_group(CIBLE, match_entity_id, START_MATCH_SOURCE_ID, None)
        events.finish_group()
    elif mutation == "tags":
        # Le dictionnaire de l'action est VIDE dans le decompile (aucun `Dictionary$$Add` entre
        # le ctor et l'appel). Y ecrire un tag doit rougir.
        events.start_group(CIBLE, match_entity_id, START_MATCH_SOURCE_ID, None)
        events.action(StepType.StartMatch, match_entity_id,
                      {TagKey.Match_CurrentPlayerId: 0})
        events.finish_group()
    elif mutation == "steptype":
        events.start_group(CIBLE, match_entity_id, START_MATCH_SOURCE_ID, None)
        events.action(StepType.StartTurn, match_entity_id, {})
        events.finish_group()
    elif mutation == "grouptype":
        events.start_group(GroupType.System_StartTurn, match_entity_id,
                           START_MATCH_SOURCE_ID, None)
        events.action(StepType.StartMatch, match_entity_id, {})
        events.finish_group()
    else:
        visit_start_battle_message(events, match_entity_id)
    return "".join(capture.racines), len(capture.racines)


MUTATIONS_TEXTE = ("enveloppe", "entite", "source", "action", "tags", "steptype", "grouptype")
MUTATIONS_ANCRAGE = ("position", "premier_startturn", "premier_prepareturn")


def ancrage(sequence: list, flux: str, mutation: str = "") -> dict:
    """LES QUATRE PREDICTIONS, toutes derivees -- et deux d'entre elles DISCRIMINANTES.

    (A1) le groupe est UNIQUE dans le flux ;
    (A2) tout groupe racine qui le PRECEDE est dans `RACINES_AVANT` (borne (c) : c'est le
         montage qui envoie ces messages-la avant `StartBattleMessage`) ;
    (A3) le PREMIER `Group=StartTurn` du flux entier est IMBRIQUE dans ce groupe. C'est LU :
         la derniere chose que fait `StartMatchOperation$$Execute` est
         `processor.<slot 0x16>(TurnStage.<3>, false, true)` -- `ContinueTurnPhase`, le meme
         slot et les memes trois arguments que la lambda `<Visit>b__20_0` de
         `Visit(StartTurnMessage)`. Toutes les occurrences SUIVANTES sont racines : le contraste
         est ce qui rend cette prediction discriminante ;
    (A4) le PREMIER `Action=PrepareTurn` du flux entier est a profondeur 1 DANS ce groupe, alors
         que les suivantes sont a profondeur 0 hors de tout groupe (mesure #477-r18 § 2)."""
    indices = [k for k, (sym, _t, _e) in enumerate(sequence) if sym == CIBLE.name]
    if mutation == "position":
        indices = [i + 1 for i in indices]
    avant = set()
    for i in indices:
        avant |= {sequence[k][0] for k in range(i)}
    lignes = flux.split("\n")
    # bornes du groupe racine cible, en numeros de ligne du flux ENTIER
    bornes = []
    pile, debut = 0, 0
    for i, l in enumerate(lignes):
        if CONF.RE_GROUP.match(l):
            if pile == 0:
                debut = i
            pile += 1
        elif CONF.RE_FINISH.match(l):
            pile -= 1
            if pile == 0:
                m = CONF.RE_GROUP.match(lignes[debut])
                if m and m.group("sym") == CIBLE.name:
                    bornes.append((debut, i))
    def _premier(rx, sym, forme):
        for i, l in enumerate(lignes):
            m = rx.match(l)
            if m and m.group("sym") == sym:
                return i, profondeur(l)
        return None, None
    i_st, p_st = _premier(CONF.RE_GROUP, GroupType.StartTurn.name, "Group")
    i_pt, p_pt = _premier(CONF.RE_ACTION, StepType.PrepareTurn.name, "Action")
    dedans = lambda i: any(a < i < b for a, b in bornes)
    a3 = (i_st is not None and dedans(i_st) and p_st is not None and p_st >= 1)
    a4 = (i_pt is not None and dedans(i_pt) and p_pt is not None and p_pt >= 1)
    if mutation == "premier_startturn":
        a3 = not a3
    if mutation == "premier_prepareturn":
        a4 = not a4
    return {"indices": indices, "unique": len(indices) == 1,
            "avant": sorted(avant), "avant_ok": avant <= set(RACINES_AVANT),
            "premier_startturn": (i_st, p_st), "a3": a3,
            "premier_prepareturn": (i_pt, p_pt), "a4": a4,
            "ok": len(indices) == 1 and avant <= set(RACINES_AVANT) and a3 and a4}


def scenario(session: int, board: str, tours: int, p_units: str, a_units: str) -> dict:
    state = OUT / ("state-477r20-%s.json" % board)
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = R19.build(board, state, p_units, a_units)
    try:
        joues = 0
        for _ in range(tours):
            q = subprocess.run([sys.executable, "rl_duel.py", "aiturn",
                                "--state-file", str(state)],
                               cwd=str(HERE), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900)
            if q.returncode != 0:
                break
            joues += 1
        flux = (R15A.rpc(session, "replayOutputStream",
                         {"runnerId": rid, "maxChars": 8000000}).get("outputStream") or "")
    finally:
        R15A.dispose(state)
    if not flux:
        raise MesureImpossible("`replayOutputStream` rend un flux VIDE")

    sequence = R19.sequence_racines(flux)
    cibles = [t for sym, t, _e in sequence if sym == CIBLE.name]
    if not cibles:
        raise MesureImpossible(
            "aucun `Group=%s` a profondeur 0 -- le montage n'a pas demarre le match "
            "(%d groupe(s) racine)." % (CIBLE.name, len(sequence)))
    if len(cibles) != 1:
        raise MesureImpossible("%d groupes `%s` -- le montage n'envoie qu'UN "
                               "`StartBattleMessage`" % (len(cibles), CIBLE.name))
    dec = decouper(cibles[0])
    vent = ventiler(dec["contenu"])
    eff = profondeurs_effect_refresh(cibles[0])
    anc = ancrage(sequence, flux)

    texte_port, n_port = emettre()
    rap = CONF.comparer(dec["texte_ampute"], texte_port, entrees_du_natif=(
        "le NOMBRE de groupes (1) -- c'est le montage qui envoie UN `StartBattleMessage`, pas "
        "une propriete lue du natif. Ce qui est MESURE, c'est la FORME de l'enveloppe et sa "
        "PLACE, pas le fait qu'il y en ait un seul",
        "l'entite du groupe -- le port ecrit `game_setup.MATCH_ENTITY_ID`, litteral LU dans "
        "`IdunBattle.Operations.SetupGameOperation$$Execute`. Le natif l'obtient ici par "
        "`IdunBattle.Entities.StateExtensions$$GetMatchEntity(state)` puis l'accesseur "
        "d'identifiant : ce que le recoupement mesure, c'est que les TROIS expressions "
        "coincident sur ce flux, PAS que le litteral soit la formule",
        "les %d ligne(s) de CONTENU du groupe, mises hors perimetre parce qu'aucun module de "
        "`engine/streams` ne les produit. Elles sont ENUMEREES et leur total est confronte au "
        "total du groupe (`1 + 1 + %d + %d + 1 == %d`) -- une amputation muette serait la "
        "projection implicite que `conformance` interdit"
        % (len(dec["contenu"]), len(dec["tags_action"]), len(dec["contenu"]),
           len(dec["lignes"])),
    ))

    # --- LE DELTA DE VOCABULAIRE (critere 2), derive du MEME flux natif -- pas du port.
    setup_natif = "".join(t for sym, t, _e in sequence
                          if sym == GroupType.System_GameSetup.name)
    place_natif = "".join(t for sym, t, _e in sequence
                          if sym == GroupType.User_PlaceUnit.name)
    voc_avant = R19.vocabulaire(setup_natif + place_natif)
    voc_apres = R19.vocabulaire(setup_natif + place_natif + dec["texte_ampute"])
    delta = {k: sorted(voc_apres[k] - voc_avant[k]) for k in voc_apres}
    voc_complet = R19.vocabulaire(setup_natif + place_natif + cibles[0])
    delta_complet = {k: sorted(voc_complet[k] - voc_avant[k]) for k in voc_complet}

    # --- CONTRE-EPREUVES : chacune doit MORDRE puis ROUGIR.
    ce = []
    for nom in MUTATIONS_TEXTE:
        texte, _n = emettre(mutation=nom)
        a_morde = texte != texte_port
        r = CONF.comparer(dec["texte_ampute"], texte)
        ce.append((nom, "texte", a_morde, len(r.nouvelles) + len(r.connues)))
    for nom in MUTATIONS_ANCRAGE:
        a_m = ancrage(sequence, flux, mutation=nom)
        a_morde = a_m != anc
        ce.append((nom, "ancrage", a_morde, 0 if a_m["ok"] else 1))

    for nom, contenu in (("natif-ampute", dec["texte_ampute"]), ("port", texte_port),
                         ("natif-groupe", cibles[0])):
        with open(OUT / ("477r20-%s-%s.txt" % (board, nom)), "w",
                  encoding="utf-8", newline="") as f:
            f.write(contenu)

    return {"board": board, "rapport": rap, "tours": joues, "racines": len(sequence),
            "lignes_flux": flux.count("\n"), "decoupe": dec, "ventilation": vent,
            "effect_refresh": eff, "ancrage": anc, "groupes_port": n_port,
            "entite_setup": next((e for sym, _t, e in sequence
                                  if sym == GroupType.System_GameSetup.name), ""),
            "voc_avant": {k: len(v) for k, v in voc_avant.items()},
            "voc_apres": {k: len(v) for k, v in voc_apres.items()},
            "delta_vocabulaire": delta, "delta_complet": delta_complet,
            "contre_epreuve": ce}


def imprimer(res: dict) -> None:
    dec, vent, eff, anc = (res["decoupe"], res["ventilation"], res["effect_refresh"],
                           res["ancrage"])
    print("  flux : %d lignes, %d groupes racines, %d tour(s) d'IA joue(s)"
          % (res["lignes_flux"], res["racines"], res["tours"]))
    print("  DECOUPE du groupe (%d lignes) : entete 1 + `Action=%s` 1 + tags %d + contenu %d "
          "+ Finish 1  -> somme exacte : %s"
          % (len(dec["lignes"]), StepType.StartMatch.name, len(dec["tags_action"]),
             len(dec["contenu"]), "OK" if dec["somme_exacte"] else "ROUGE"))
    if not dec["action_est_start_match"]:
        print("      ROUGE LECTURE : la premiere ligne de profondeur 1 n'est PAS "
              "`Action=%s` -- [%s]" % (StepType.StartMatch.name, dec["action"]))
    if dec["tags_action"]:
        print("      ROUGE LECTURE : l'`Action=%s` porte %d `Tag=`, or le decompile construit "
              "un dictionnaire VIDE (aucun `Dictionary$$Add`)."
              % (StepType.StartMatch.name, len(dec["tags_action"])))
    print("  RECOUPEMENT d'entite (3 voies natives distinctes) : entete=%s  action=%s  "
          "System_GameSetup=%s"
          % (dec["entite_entete"], dec["entite_action"], res["entite_setup"]))
    print("  ANCRAGE  (A1) unique=%s   (A2) racines avant = %s -> %s"
          % ("OK" if anc["unique"] else "KO", ",".join(anc["avant"]) or "(aucune)",
             "OK" if anc["avant_ok"] else "KO"))
    print("           (A3) premier `Group=%s` du flux : ligne %s profondeur %s -> %s"
          % (GroupType.StartTurn.name, anc["premier_startturn"][0],
             anc["premier_startturn"][1], "DEDANS" if anc["a3"] else "DEHORS -- ROUGE"))
    print("           (A4) premier `Action=%s` du flux : ligne %s profondeur %s -> %s"
          % (StepType.PrepareTurn.name, anc["premier_prepareturn"][0],
             anc["premier_prepareturn"][1], "DEDANS" if anc["a4"] else "DEHORS -- ROUGE"))
    print("  CONTENU HORS PERIMETRE : %d lignes, %d sous-arbre(s) de profondeur 1 (%d lignes) "
          "+ %d ligne(s) isolee(s) -> somme exacte : %s"
          % (len(dec["contenu"]), len(vent["sous_arbres"]), vent["total_arbres"],
             vent["isolees"], "OK" if vent["somme_exacte"] else "ROUGE"))
    par_sym: dict = {}
    for sym, _src, n in vent["sous_arbres"]:
        a, b = par_sym.get(sym, (0, 0))
        par_sym[sym] = (a + 1, b + n)
    for sym in sorted(par_sym, key=lambda s: -par_sym[s][1]):
        print("      sous-arbre `%-18s` x%-3d  %4d lignes" % (sym, par_sym[sym][0],
                                                              par_sym[sym][1]))
    for cle in sorted(vent["formes"], key=lambda c: -vent["formes"][c]):
        print("      forme %-34s x%d" % (cle, vent["formes"][cle]))
    print("  `%s` DANS CE GROUPE : %d occurrence(s)" % (GroupType.Effect_Refresh.name,
                                                        eff["total"]))
    for p in sorted(eff["par_profondeur"]):
        print("      profondeur %d : %d" % (p, eff["par_profondeur"][p]))
    for chemin in sorted(eff["par_chemin"], key=lambda c: -eff["par_chemin"][c]):
        print("      chemin `%s` : %d" % (chemin, eff["par_chemin"][chemin]))
    print("      ATTEIGNABLES par l'enveloppe SEULE : %d / %d -- un `%s` n'est comparable que "
          "si TOUT son chemin est emis, et son CONTENU (`ActivateEffect` / `ReceiveEffect` et "
          "leurs ids d'effet ECS) reste a produire meme a profondeur 1."
          % (0, eff["total"], GroupType.Effect_Refresh.name))
    print("  DELTA DE VOCABULAIRE vs (`System_GameSetup` + `User_PlaceUnit`), sur ce qui est "
          "PORTE (attendu +1 / +1 / +0) :")
    for nom in ("GroupType", "StepType", "TagKey"):
        d = res["delta_vocabulaire"][nom]
        print("      %-10s %d -> %d   (+%d) %s"
              % (nom, res["voc_avant"][nom], res["voc_apres"][nom], len(d),
                 ",".join(d) if d else ""))
    print("      et sur le groupe COMPLET (ce que la tranche couterait en entier) :")
    for nom in ("GroupType", "StepType", "TagKey"):
        d = res["delta_complet"][nom]
        print("      %-10s (+%d) %s" % (nom, len(d), ",".join(d) if d else ""))
    print("  CONTRE-EPREUVE (%d mutations, chacune doit MORDRE puis rougir) :"
          % (len(MUTATIONS_TEXTE) + len(MUTATIONS_ANCRAGE)))
    for nom, etage, a_morde, divs in res["contre_epreuve"]:
        marque = "OK" if (a_morde and divs) else "ROUGE"
        print("      %-20s %-8s a_morde=%-5s divergences=%-4d %s"
              % (nom, etage, a_morde, divs, marque))
        if not a_morde:
            print("          ! la mutation n'a PAS change ce qu'elle mute -- elle ne mesure "
                  "rien, quel que soit son verdict.")
    for ligne in CONF.rapport(res["rapport"]):
        print("  " + ligne)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--boards", default=",".join(BOARDS_DEFAUT))
    ap.add_argument("--tours", type=int, default=2)
    ap.add_argument("--p-units", default="")
    ap.add_argument("--a-units", default="")
    args = ap.parse_args()

    try:
        session = args.session if args.session is not None else R15A.session_courante()
    except MesureImpossible as e:
        print("[477-r20] MESURE IMPOSSIBLE : %s" % e)
        return 2

    boards = [b.strip() for b in args.boards.split(",") if b.strip()]
    print("[477-r20] session=%d  boards=%s  tours=%d" % (session, ",".join(boards), args.tours))
    resultats = []
    for board in boards:
        print("")
        print("=== BOARD %s ===" % board)
        try:
            res = scenario(session, board, args.tours, args.p_units, args.a_units)
        except MesureImpossible as e:
            print("  MESURE IMPOSSIBLE : %s" % e)
            return 2
        resultats.append(res)
        imprimer(res)

    print("")
    print("=== VERDICT (corpus = %d board(s)) ===" % len(resultats))
    rc = 0
    for r in resultats:
        rp, anc = r["rapport"], r["ancrage"]
        etat = ("conforme" if rp.conforme and anc["ok"]
                else "divergent NOUVEAU" if rp.nouvelles
                else "ANCRAGE FAUX" if not anc["ok"] else "divergent CONNU")
        print("  %-10s %-18s egales=%d/%d  NOUVELLES=%d  ancrage=%s  contenu hors "
              "perimetre=%d lignes"
              % (r["board"], etat, rp.egales, rp.lignes_natif, len(rp.nouvelles),
                 "OK" if anc["ok"] else "KO", len(r["decoupe"]["contenu"])))
    nouvelles = sum(len(r["rapport"].nouvelles) for r in resultats)
    if nouvelles:
        print("  ROUGE : %d divergence(s) NOUVELLE(s)." % nouvelles)
        rc = 1
    horsforme = sum(len(r["rapport"].hors_forme) for r in resultats)
    if horsforme:
        print("  ROUGE : %d ligne(s) hors des 4 formes -- une forme nous manque." % horsforme)
        rc = 1
    lecture_ko = [r["board"] for r in resultats
                  if not r["decoupe"]["action_est_start_match"] or r["decoupe"]["tags_action"]
                  or not r["decoupe"]["somme_exacte"]
                  or not r["ventilation"]["somme_exacte"]]
    if lecture_ko:
        print("  ROUGE : la DECOUPE ou son total est faux sur %s -- l'amputation ne serait "
              "alors pas imputable." % ",".join(lecture_ko))
        rc = 1
    anc_ko = [r["board"] for r in resultats if not r["ancrage"]["ok"]]
    if anc_ko:
        print("  ROUGE : ANCRAGE faux sur %s." % ",".join(anc_ko))
        rc = 1
    ent_ko = [r["board"] for r in resultats
              if len({r["decoupe"]["entite_entete"], r["decoupe"]["entite_action"],
                      r["entite_setup"]}) != 1]
    if ent_ko:
        print("  ROUGE : recoupement d'entite KO sur %s -- les trois expressions natives ne "
              "coincident pas." % ",".join(ent_ko))
        rc = 1
    deborde = [r["board"] for r in resultats
               if r["delta_vocabulaire"]["TagKey"]
               or set(r["delta_vocabulaire"]["GroupType"]) != {CIBLE.name}
               or set(r["delta_vocabulaire"]["StepType"]) != {StepType.StartMatch.name}]
    if deborde:
        print("  ROUGE : la tranche DEBORDE sur %s -- le delta porte n'est pas "
              "+1 `%s` / +1 `%s` / +0." % (",".join(deborde), CIBLE.name,
                                           StepType.StartMatch.name))
        rc = 1
    ce_ko = [(r["board"], nom) for r in resultats
             for nom, _et, a_morde, divs in r["contre_epreuve"] if not (a_morde and divs)]
    if ce_ko:
        print("  ROUGE : %d mutation(s) de contre-epreuve NE ROUGISSENT PAS -- le vert du "
              "scenario sain ne prouve alors rien : %s"
              % (len(ce_ko), ", ".join("%s/%s" % (b, n) for b, n in ce_ko)))
        rc = 1
    montage_ko = [r["board"] for r in resultats if r["groupes_port"] != 1]
    if montage_ko:
        print("  ROUGE : le port n'emet pas exactement un groupe racine sur %s."
              % ",".join(montage_ko))
        rc = 1
    if rc == 0:
        print("  VERT sur l'ENVELOPPE : `%s` est reproduit a l'EGALITE BRUTE (entete, "
              "`Action=%s` sans tag, `Finish_Group`) et place la ou le natif le place."
              % (CIBLE.name, StepType.StartMatch.name))
        print("  NON COUVERT, et c'est le resultat de la tranche : %s ligne(s) de CONTENU par "
              "board, %s `%s` dont 0 atteignable -- ce qu'il faudrait porter est ENUMERE "
              "ci-dessus, pas sous-entendu."
              % ("/".join(str(len(r["decoupe"]["contenu"])) for r in resultats),
                 "/".join(str(r["effect_refresh"]["total"]) for r in resultats),
                 GroupType.Effect_Refresh.name))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
