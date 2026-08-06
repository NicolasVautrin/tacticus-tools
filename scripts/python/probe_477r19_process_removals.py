#!/usr/bin/env python3
"""#477-r19 -- `System_ProcessRemovals`, le cran d'ANCRAGE du DEROULE, confronte en live.

    python probe_477r19_process_removals.py [--session N] [--boards C1_02,MC1_67] [--tours 2]

CE QU'IL MESURE, ET POURQUOI CE GROUPE-LA
-----------------------------------------
`System_ProcessRemovals` est un groupe VIDE : deux lignes, aucune `Action=`, aucun `Tag=`
(`+1 GroupType, +0 StepType, +0 TagKey`). C'est precisement sa valeur -- il n'a AUCUNE donnee
pour masquer une erreur de placement. Un groupe vide emis au mauvais moment est une divergence
de POSITION pure, et rien d'autre ne peut l'expliquer.

Le probe tient donc DEUX etages, et le second est le coeur de la tranche :

  ETAGE TEXTE    les `Group=System_ProcessRemovals` du flux natif contre ceux que le port emet
                 (`engine.streams.input_messages.verify_removed_units`), a l'EGALITE BRUTE
                 ligne a ligne -- meme barre et meme cliquet a trois etats que #477-r15a ;
  ETAGE ANCRAGE  chaque occurrence tombe-t-elle sur une ANCRE de `VerifyDeaths` derivee du
                 decompile ? Le test est une INCLUSION, et sa valeur est bornee par la
                 DISCRIMINATION (combien d'ancres sur combien de positions possibles), que le
                 probe imprime : un test d'inclusion sur un ensemble large ne vaut rien.

LA REGLE D'ANCRAGE EST LUE, PAS AJUSTEE (RE : `case-477r19`)
-----------------------------------------------------------
`IdunBattle.Messages.InputMessageProcessor$$VerifyRemovedUnits` N'A AUCUN APPELANT : son corps
est INLINE dans `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths`. Mesure : le
`Il2CppClass*` du `<>c__DisplayClass50_0` et le pointeur de sa lambda ne sont references que par
ces deux fonctions -- il n'existe donc AUCUN autre site d'emission de ce `GroupType`. Les ancres
sont les call-sites de `VerifyDeaths` VISIBLES dans le flux
(`input_messages.VERIFY_DEATHS_ANCHOR_GROUPS`) ; depuis chacune on avance tant que le groupe
suivant n'est pas une BARRIERE (`input_messages.PHASE_BARRIER_GROUPS`).

⚠ CE QUI N'EST PAS PREDIT, ET POURQUOI -- une premiere version de ce probe l'a APPRIS EN
ROUGISSANT. Elle predisait le NOMBRE par « une rafale de morts => un retrait ». Le SECOND board
l'a refutee au premier run : MC1_67 rend 3 occurrences pour 2 rafales de morts, la troisieme
apres un `StartTurn` sans aucune mort en amont. Le decompile le disait deja -- le garde
`deaths.Count > 0` de `VerifyDeaths` ne couvre QUE le `RunPhase` des morts, jamais le bloc des
retraits -- et la file `IdunBattle.Core.MatchState$$AddRemovedActor` qui l'arme n'est observable
par AUCUN canal. Le nombre est donc une ENTREE (borne (c) nommee), le LIEU une prediction.
C'est la mesure du second board qui a corrige la RE, pas l'inverse : sur `C1_02` seul, la regle
fausse rendait un vert parfait (3 predits, 3 reels, positions exactes).

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
from engine.streams import GroupType, StepType, StreamCache, StreamDispatcher, TagKey  # noqa: E402
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.game_setup import MATCH_ENTITY_ID  # noqa: E402
from engine.streams.input_messages import (PHASE_BARRIER_GROUPS,  # noqa: E402
                                           PROCESS_REMOVALS_SOURCE_ID,
                                           VERIFY_DEATHS_ANCHOR_GROUPS,
                                           verify_removed_units)

ROOT = HERE.parents[1]
OUT = ROOT / "logs"

MesureImpossible = R15A.MesureImpossible

#: Les memes deux boards que #477-r15a / -r18-r5 : tailles DIFFERENTES (35 vs 63 tuiles). Un
#: seul board ne prouverait rien -- ni sur le nombre de rafales de morts, ni sur leur place.
BOARDS_DEFAUT = ("C1_02", "MC1_67")
#: Le groupe confronte, et celui dont il est la retombee.
CIBLE = GroupType.System_ProcessRemovals
AMONT = GroupType.System_ProcessDeaths


def sequence_racines(flux: str) -> list:
    """La sequence des groupes RACINES, dans l'ordre : `(symbole, texte, entite)`.

    Decoupe par PILE (meme regle que #477-r15a) : deux comptes egaux couvriraient un
    `Finish_Group` sans groupe ouvert suivi d'un groupe jamais ferme."""
    lignes = flux.split("\n")
    out, pile, debut = [], 0, 0
    for i, s in enumerate(lignes):
        m = CONF.RE_GROUP.match(s)
        if m:
            if pile == 0:
                debut = i
            pile += 1
        elif CONF.RE_FINISH.match(s):
            pile -= 1
            if pile < 0:
                raise MesureImpossible("`Finish_Group` sans groupe ouvert, ligne %d" % i)
            if pile == 0:
                tete = CONF.RE_GROUP.match(lignes[debut])
                out.append((tete.group("sym"), "\n".join(lignes[debut:i + 1]) + "\n",
                            tete.group("entity")))
    if pile != 0:
        raise MesureImpossible("%d groupe(s) racine jamais ferme(s)" % pile)
    return out


def ancres_admissibles(sequence_amputee: list, barriere: "set | None" = None) -> tuple:
    """LES POSITIONS OU UN `System_ProcessRemovals` PEUT TOMBER. Rend `(positions, detail)`.

    ⚠ CE N'EST PAS UN PREDICTEUR DE NOMBRE, ET C'EST UNE MESURE QUI L'A IMPOSE. La premiere
    version de ce probe predisait « une rafale de morts => un retrait » ; le SECOND board l'a
    refutee des le premier run (MC1_67 : 3 occurrences pour 2 rafales de morts, la troisieme
    apres un `StartTurn`). Le decompile le disait deja -- `VerifyDeaths` ne garde par
    `deaths.Count > 0` que le `RunPhase` des morts, jamais le bloc des retraits -- et la file
    `IdunBattle.Core.MatchState$$AddRemovedActor` qui arme ce bloc n'est observable par AUCUN
    canal. Le NOMBRE est donc une entree, pas une prediction ; ce qui se predit, c'est le LIEU.

    Le lieu se derive de `input_messages.VERIFY_DEATHS_ANCHOR_GROUPS` (les deux formes lues de
    call-site de `VerifyDeaths`) : depuis chaque ancre, on avance tant que le groupe suivant
    n'est pas une BARRIERE. `detail` porte, par ancre, `(symbole, position, groupes traverses)`
    -- l'angle mort est ainsi IMPRIME plutot que sous-entendu."""
    barriere = {g.name for g in PHASE_BARRIER_GROUPS} if barriere is None else barriere
    ancres = {g.name for g in VERIFY_DEATHS_ANCHOR_GROUPS}
    positions, detail = [], []
    for k, (sym, _texte, _e) in enumerate(sequence_amputee):
        if sym not in ancres:
            continue
        j = k + 1
        vus = []
        while j < len(sequence_amputee) and sequence_amputee[j][0] not in barriere:
            vus.append(sequence_amputee[j][0])
            j += 1
        positions.append(j)
        detail.append((sym, j, vus))
    return sorted(set(positions)), detail


def positions_reelles(sequence: list) -> tuple:
    """`(positions_dans_l_amputee, sequence_amputee, textes)` pour la CIBLE.

    La conversion est structurelle : la position d'insertion d'une occurrence est le nombre
    d'elements NON-CIBLE qui la precedent. C'est ce qui rend les deux referentiels comparables
    sans qu'aucun des deux ne soit derive de l'autre."""
    amputee, positions, textes = [], [], []
    for sym, texte, entite in sequence:
        if sym == CIBLE.name:
            positions.append(len(amputee))
            textes.append((texte, entite))
        else:
            amputee.append((sym, texte, entite))
    return positions, amputee, textes


class Capture:
    """Un `IStreamCacheListener` : ne garde que les groupes RACINE flushes."""

    def __init__(self) -> None:
        self.racines: list = []

    def on_root_group_finished(self, group: str) -> None:
        self.racines.append(group)

    def on_log(self, chunk: str) -> None:
        pass


#: L'entree que le port recoit pour OUVRIR le groupe : la file `MatchState.RemovedActors`, dont
#: seule la NON-VACUITE compte (`queue.Count < 1` => rien). Elle n'est pas observable depuis nos
#: canaux -- le probe lui passe donc un jeton, et c'est une borne (c) NOMMEE au rapport.
FILE_NON_VIDE = (0,)


def emettre(n: int, match_entity_id: int = MATCH_ENTITY_ID, mutation: str = "") -> tuple:
    """Emet `n` groupes `System_ProcessRemovals` et rend `(texte concatene, nb de racines)`.

    `mutation` est le levier de la CONTRE-EPREUVE. Un flux emis qui reste EGAL au natif apres
    qu'on a casse le port ne prouve rien : chaque mutation doit rougir, et le probe verifie
    AUSSI qu'elle a bien change le texte -- une mutation qui ne mord pas rendrait un rouge...
    ou un vert, tous deux sans valeur."""
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    for _ in range(n):
        if mutation == "enveloppe":
            # L'enveloppe supprimee : le port n'ecrit plus rien la ou le natif ouvre un groupe.
            continue
        if mutation == "entite":
            events.start_group(CIBLE, match_entity_id + 1, PROCESS_REMOVALS_SOURCE_ID, None)
            events.finish_group()
        elif mutation == "source":
            events.start_group(CIBLE, match_entity_id, CIBLE.name, None)
            events.finish_group()
        elif mutation == "contenu":
            # Ce que `RemoveUnitOperation$$Execute` emettrait si ses trois gardes laissaient
            # passer. Le natif ne l'emet dans AUCUN groupe du corpus : l'ecrire doit rougir.
            events.start_group(CIBLE, match_entity_id, PROCESS_REMOVALS_SOURCE_ID, None)
            events.action(StepType.RemoveUnit, match_entity_id,
                          {TagKey.Unit_IsDying: 0, TagKey.Unit_WasOverkilled: 0})
            events.finish_group()
        else:
            verify_removed_units(events, match_entity_id, FILE_NON_VIDE)
    if mutation == "garde":
        # LA GARDE `queue.Count < 1` IGNOREE. Le port sain ne produit RIEN sur une file vide
        # (verifie offline) ; le muter, c'est emettre le groupe quand meme -- une occurrence de
        # plus que le natif, la ou aucune unite n'est a retirer.
        events.start_group(CIBLE, match_entity_id, PROCESS_REMOVALS_SOURCE_ID, None)
        events.finish_group()
    return "".join(capture.racines), len(capture.racines)


def ancrage(amputee: list, reelles: list, mutation: str = "") -> tuple:
    """`(positions retenues, ancres admissibles, hors_ancre)` -- le test d'INCLUSION.

    Le port ecrit ses groupes AUX POSITIONS REELLES (le nombre d'occurrences est une entree du
    natif, borne (c) : la file qui l'arme n'est pas observable). Ce qui MESURE, c'est que
    chacune de ces positions soit une ancre DERIVEE DU DECOMPILE -- un groupe place ailleurs
    sortirait de l'ensemble."""
    if mutation == "barriere":
        # BARRIERE VIDEE : plus rien n'arrete l'avance, chaque ancre court jusqu'a la fin du
        # flux. Mesure que `PHASE_BARRIER_GROUPS` porte bien le placement.
        adm, _d = ancres_admissibles(amputee, barriere=set())
    else:
        adm, _d = ancres_admissibles(amputee)
    retenues = list(reelles)
    if mutation == "position":
        # Decale d'un cran : exactement la faute que ce cran existe pour rendre visible.
        retenues = [p + 1 for p in reelles]
    return retenues, adm, [p for p in retenues if p not in adm]


MUTATIONS_TEXTE = ("enveloppe", "entite", "source", "contenu", "garde")
MUTATIONS_ANCRAGE = ("position", "barriere")


#: Le seed du `rl_duel build`. Il gouverne le RNG du match ET, quand le roster n'est pas impose,
#: le tirage des unites (`rl_duel.py` : `rng = random.Random(a.seed)`). Le fixer est ce qui rend
#: deux runs COMPARABLES ; le rendre PARAMETRABLE est ce qui permet de le dire au lieu de le
#: supposer (#477-r28).
SEED = 777


def build(board: str, state_file: Path, p_units: str, a_units: str, seed: int = SEED) -> int:
    """`rl_duel build`. La CAUSE d'un echec porte son nom (#477-r18-r5 § 5) : une queue brute
    noie la ligne `[error]` sous le rapport de re-synthese du seed BC."""
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
           "--record-replay", "--no-ai", "--state-file", str(state_file)]
    if p_units:
        cmd += ["--p-units", p_units]
    if a_units:
        cmd += ["--a-units", a_units]
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    if not state_file.is_file():
        sortie = "%s\n%s" % (p.stdout or "", p.stderr or "")
        motifs = [l for l in sortie.split("\n")
                  if l.startswith("[error]") or l.lstrip().startswith("pool =")
                  or "Traceback" in l or l.startswith("Error")]
        raise MesureImpossible("build %s echoue (rc=%s) : %s"
                               % (board, p.returncode,
                                  " | ".join(motifs) if motifs else sortie[-400:]))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def vocabulaire(texte: str) -> dict:
    """Les membres d'enum qu'un texte de flux ECRIT, par enum. Sert au delta de la borne (a)."""
    vus = {"GroupType": set(), "StepType": set(), "TagKey": set()}
    for l in CONF.parse_flux(texte):
        if l.forme == "Group":
            vus["GroupType"].add(l.symbole)
        elif l.forme == "Action":
            vus["StepType"].add(l.symbole)
        elif l.forme == "Tag":
            vus["TagKey"].add(l.symbole)
    return vus


def scenario(session: int, board: str, tours: int, p_units: str, a_units: str) -> dict:
    state = OUT / ("state-477r19-%s.json" % board)
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = build(board, state, p_units, a_units)
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

    sequence = sequence_racines(flux)
    reelles, amputee, textes = positions_reelles(sequence)
    if not reelles:
        raise MesureImpossible(
            "aucun `Group=%s` a profondeur 0 -- le montage ne produit aucun retrait "
            "(%d tour(s) d'IA joue(s), %d groupe(s) racine). Sans occurrence, ce probe ne "
            "mesure RIEN : augmenter `--tours`." % (CIBLE.name, joues, len(sequence)))

    retenues, admissibles, hors_ancre = ancrage(amputee, reelles)
    _adm, detail_ancres = ancres_admissibles(amputee)
    texte_natif = "".join(t for t, _e in textes)
    texte_port, n_port = emettre(len(reelles))
    rap = CONF.comparer(texte_natif, texte_port, entrees_du_natif=(
        "le NOMBRE de groupes -- la file `IdunBattle.Core.MatchState$$AddRemovedActor` qui arme "
        "le bloc n'est observable par AUCUN canal, et le decompile ne la lie PAS aux morts (le "
        "garde `deaths.Count > 0` ne couvre que le `RunPhase` des morts). Ce qui est MESURE "
        "ici, c'est le LIEU : chaque occurrence tombe-t-elle sur une ancre de `VerifyDeaths` ?",
        "l'entite du groupe -- le port ecrit `game_setup.MATCH_ENTITY_ID`, litteral LU dans "
        "`IdunBattle.Operations.SetupGameOperation$$Execute`. Le natif, lui, la CALCULE "
        "(`((IEntity)state).Id`) : ce que le recoupement mesure, c'est que les deux expressions "
        "coincident sur ce flux, PAS que le litteral soit la formule",
    ))

    # --- RECOUPEMENT D'ENTITE : le decompile donne la MEME expression aux deux groupes.
    ent_cible = sorted({e for _t, e in textes})
    ent_amont = sorted({e for sym, _t, e in sequence if sym == AMONT.name})

    # --- LE DELTA DE VOCABULAIRE (critere 2), derive du MEME flux natif -- pas du port.
    setup_natif = "".join(t for sym, t, _e in sequence if sym == GroupType.System_GameSetup.name)
    place_natif = "".join(t for sym, t, _e in sequence if sym == GroupType.User_PlaceUnit.name)
    voc_avant = vocabulaire(setup_natif + place_natif)
    voc_apres = vocabulaire(setup_natif + place_natif + texte_natif)
    delta = {k: sorted(voc_apres[k] - voc_avant[k]) for k in voc_apres}

    # --- CONTRE-EPREUVES : chacune doit MORDRE puis ROUGIR.
    ce = []
    for nom in MUTATIONS_TEXTE:
        texte, _n = emettre(len(reelles), mutation=nom)
        a_morde = texte != texte_port
        r = CONF.comparer(texte_natif, texte)
        ce.append((nom, "texte", a_morde, len(r.nouvelles) + len(r.connues)))
    for nom in MUTATIONS_ANCRAGE:
        ret_m, adm_m, hors_m = ancrage(amputee, reelles, mutation=nom)
        a_morde = (ret_m, adm_m) != (retenues, admissibles)
        ce.append((nom, "ancrage", a_morde, len(hors_m)))

    for nom, contenu in (("natif", texte_natif), ("port", texte_port),
                         ("flux-complet", flux)):
        with open(OUT / ("477r19-%s-%s.txt" % (board, nom)), "w",
                  encoding="utf-8", newline="") as f:
            f.write(contenu)

    return {"board": board, "rapport": rap, "tours": joues,
            "racines": len(sequence), "lignes_flux": flux.count("\n"),
            "lignes_groupe": sum(t.count("\n") for t, _e in textes),
            "reelles": reelles, "admissibles": admissibles, "hors_ancre": hors_ancre,
            "detail_ancres": detail_ancres, "positions_possibles": len(amputee) + 1,
            "amonts": sum(1 for sym, _t, _e in sequence if sym == AMONT.name),
            "groupes_port": n_port, "ent_cible": ent_cible, "ent_amont": ent_amont,
            "voc_avant": {k: len(v) for k, v in voc_avant.items()},
            "voc_apres": {k: len(v) for k, v in voc_apres.items()},
            "delta_vocabulaire": delta, "contre_epreuve": ce,
            "voisins": [(amputee[p - 1][0] if p else "(debut)",
                         amputee[p][0] if p < len(amputee) else "(fin)") for p in reelles]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--boards", default=",".join(BOARDS_DEFAUT))
    ap.add_argument("--tours", type=int, default=2,
                    help="tours d'IA joues. Il en faut assez pour qu'une unite MEURE : sans "
                         "mort, aucun `System_ProcessRemovals` et le probe rend MESURE "
                         "IMPOSSIBLE plutot qu'un vert vide.")
    ap.add_argument("--p-units", default="")
    ap.add_argument("--a-units", default="")
    args = ap.parse_args()

    try:
        session = args.session if args.session is not None else R15A.session_courante()
    except MesureImpossible as e:
        print("[477-r19] MESURE IMPOSSIBLE : %s" % e)
        return 2

    boards = [b.strip() for b in args.boards.split(",") if b.strip()]
    print("[477-r19] session=%d  boards=%s  tours=%d" % (session, ",".join(boards), args.tours))
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
        print("  flux : %d lignes, %d groupes racines, %d tour(s) d'IA joue(s)"
              % (res["lignes_flux"], res["racines"], res["tours"]))
        print("  POIDS : %d lignes de groupe `%s` (%d occurrence(s), %d en amont `%s`)"
              % (res["lignes_groupe"], CIBLE.name, len(res["reelles"]),
                 res["amonts"], AMONT.name))
        print("  ANCRAGE  occurrences REELLES   = %s" % res["reelles"])
        print("           ancres ADMISSIBLES   = %s" % res["admissibles"])
        print("           DISCRIMINATION : %d ancre(s) sur %d position(s) possible(s) = %.0f%% "
              "-- un test d'inclusion ne vaut que ce que vaut ce chiffre"
              % (len(res["admissibles"]), res["positions_possibles"],
                 100.0 * len(res["admissibles"]) / max(1, res["positions_possibles"])))
        for sym, p, vus in res["detail_ancres"]:
            porte = "PORTE un groupe" if p in res["reelles"] else "vide (file non armee)"
            print("             ancre `%-22s` -> %-4d %-22s traverse : %s"
                  % (sym, p, porte, ", ".join(vus) or "(rien)"))
        for (av, ap_), p in zip(res["voisins"], res["reelles"]):
            print("             occurrence a %-4d entre `%s` et `%s`" % (p, av, ap_))
        if res["hors_ancre"]:
            print("  ROUGE ANCRAGE : %d occurrence(s) HORS de toute ancre lue : %s. C'est la "
                  "condition de retournement de `VERIFY_DEATHS_ANCHOR_GROUPS` -- il manque une "
                  "forme de call-site de `VerifyDeaths`."
                  % (len(res["hors_ancre"]), res["hors_ancre"]))
        print("  RECOUPEMENT d'entite : `%s` = %s   `%s` = %s"
              % (CIBLE.name, res["ent_cible"], AMONT.name, res["ent_amont"]))
        if res["ent_cible"] != res["ent_amont"]:
            print("      ROUGE RECOUPEMENT : le decompile donne la MEME expression "
                  "(`((IEntity)state).Id`) aux deux groupes -- elles divergent ici.")
        print("  DELTA DE VOCABULAIRE vs (`System_GameSetup` + `User_PlaceUnit`) "
              "(attendu +1 / +0 / +0) :")
        for nom in ("GroupType", "StepType", "TagKey"):
            d = res["delta_vocabulaire"][nom]
            print("      %-10s %d -> %d   (+%d) %s"
                  % (nom, res["voc_avant"][nom], res["voc_apres"][nom], len(d),
                     ",".join(d) if d else ""))
        if res["delta_vocabulaire"]["StepType"] or res["delta_vocabulaire"]["TagKey"]:
            print("      ROUGE DEBORDEMENT : la tranche ajoute du vocabulaire d'ACTION ou de "
                  "TAG -- le groupe devait etre VIDE.")
        print("  CONTRE-EPREUVE (%d mutations, chacune doit rougir) :"
              % (len(MUTATIONS_TEXTE) + len(MUTATIONS_ANCRAGE)))
        for nom, etage, a_morde, divs in res["contre_epreuve"]:
            marque = "OK" if (a_morde and divs) else "ROUGE"
            print("      %-12s %-8s a_morde=%-5s divergences=%-4d %s"
                  % (nom, etage, a_morde, divs, marque))
            if not a_morde:
                print("          ! la mutation n'a PAS change ce qu'elle mute -- elle ne mesure "
                      "rien, quel que soit son verdict.")
        for ligne in CONF.rapport(res["rapport"]):
            print("  " + ligne)

    print("")
    print("=== VERDICT (corpus = %d board(s)) ===" % len(resultats))
    rc = 0
    for r in resultats:
        rp = r["rapport"]
        ancre = not r["hors_ancre"]
        etat = ("conforme" if rp.conforme and ancre
                else "divergent NOUVEAU" if rp.nouvelles
                else "ANCRAGE FAUX" if not ancre else "divergent CONNU")
        print("  %-10s %-18s egales=%d/%d  NOUVELLES=%d  ancrage=%s  occurrences=%d  "
              "ancres=%d/%d"
              % (r["board"], etat, rp.egales, rp.lignes_natif, len(rp.nouvelles),
                 "OK" if ancre else "KO", len(r["reelles"]),
                 len(r["admissibles"]), r["positions_possibles"]))
    nouvelles = sum(len(r["rapport"].nouvelles) for r in resultats)
    if nouvelles:
        print("  ROUGE : %d divergence(s) NOUVELLE(s)." % nouvelles)
        rc = 1
    horsforme = sum(len(r["rapport"].hors_forme) for r in resultats)
    if horsforme:
        print("  ROUGE : %d ligne(s) hors des 4 formes -- une forme nous manque." % horsforme)
        rc = 1
    ancre_ko = [r["board"] for r in resultats if r["hors_ancre"]]
    if ancre_ko:
        print("  ROUGE : ANCRAGE faux sur %s -- une occurrence tombe hors de toute ancre lue. "
              "C'est exactement ce que ce cran existe pour voir." % ",".join(ancre_ko))
        rc = 1
    ent_ko = [r["board"] for r in resultats if r["ent_cible"] != r["ent_amont"]]
    if ent_ko:
        print("  ROUGE : recoupement d'entite KO sur %s." % ",".join(ent_ko))
        rc = 1
    deborde = [r["board"] for r in resultats
               if r["delta_vocabulaire"]["StepType"] or r["delta_vocabulaire"]["TagKey"]]
    if deborde:
        print("  ROUGE : la tranche DEBORDE sur %s." % ",".join(deborde))
        rc = 1
    ce_ko = [(r["board"], nom) for r in resultats
             for nom, _et, a_morde, divs in r["contre_epreuve"] if not (a_morde and divs)]
    if ce_ko:
        print("  ROUGE : %d mutation(s) de contre-epreuve NE ROUGISSENT PAS -- le vert du "
              "scenario sain ne prouve alors rien : %s"
              % (len(ce_ko), ", ".join("%s/%s" % (b, n) for b, n in ce_ko)))
        rc = 1
    montage_ko = [r["board"] for r in resultats if r["groupes_port"] != len(r["reelles"])]
    if montage_ko:
        print("  ROUGE : le port n'emet pas autant de groupes que le natif sur %s."
              % ",".join(montage_ko))
        rc = 1
    if rc == 0:
        print("  VERT : les %d groupes `%s` sont reproduits a l'EGALITE BRUTE, et places la ou "
              "le natif les place." % (sum(len(r["reelles"]) for r in resultats), CIBLE.name))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
