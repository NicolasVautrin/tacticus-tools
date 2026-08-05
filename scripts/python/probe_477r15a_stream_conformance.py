#!/usr/bin/env python3
"""#477-r15 tranche E -- LE CLIQUET A TROIS ETATS du flux de replay, confronte en live.

    python probe_477r15a_stream_conformance.py [--session N] [--boards C1_02,MC1_67]

CE QU'IL MESURE
---------------
Le port EMET desormais un flux de replay (`engine.streams`, tranches A + B). Ce probe le
confronte au flux NATIF sur le seul morceau entierement atteignable : le groupe racine
`System_GameSetup` (`AddPlayer` / `AddTile` / `AddUnit`), qui ne depend d'aucune mecanique de
combat portee. Le flux natif est deterministe au caractere pres (#477-r11), donc la barre est
l'egalite BRUTE, ligne a ligne.

Verdict a TROIS etats, jamais un pass/fail (`case-477r15` § 6) :
  conforme / divergent CONNU (inscrit au registre avec sa cause) / divergent NOUVEAU (rougit).

CE QUI REND LA MESURE HONNETE -- les entrees du port viennent de canaux INDEPENDANTS
------------------------------------------------------------------------------------
Reconstruire les entrees depuis le flux natif serait une tautologie : le port rendrait
l'oracle. Chaque grandeur comparee vient donc d'ailleurs :

  colonne / ligne de chaque tuile   <- le BOARD DUMP `data/boards/<kind>/<id>.json`, itere
                                       colonne par colonne (`Tiles[c].Tile[r]`) ;
  ordre des tuiles                  <- le meme parcours ; s'il ne correspondait pas a l'ordre
                                       natif, TOUTES les lignes divergeraient ;
  id d'entite de chaque unite       <- `observeBattle.units[].squadId`, dont #477-r15 a mesure
                                       qu'il EST le `Entity=` du flux (5/5 unites, 2 boards) ;
  proprietaire / position d'unite   <- `observeBattle` (playerId, col, row).

Et les grandeurs qu'on ne SAIT pas encore deriver sont prises du natif, donc DECLAREES non
mesurees (borne (c) du rapport) -- jamais comptees comme un accord. C'est l'ordre d'allocation
des entites ECS, `#477-r16`, dispatche en parallele : tant qu'il n'est pas RE'd, l'id d'entite
d'un joueur ou d'une tuile est une ENTREE.

⚠ UNE HYPOTHESE DE MONTAGE, PAS DU NATIF : sur un runner monte par `rl_duel build`, seules les
unites de l'equipe ADVERSE sont posees par `SetupGameOperation$$AddPredefinedUnits` ; celles du
joueur arrivent dans un groupe racine SEPARE (`User_PlaceUnit`). Le probe le VERIFIE au lieu de
le supposer : si le groupe `System_GameSetup` contient un nombre d'`Action=AddUnit` different de
ce que ce filtre predit, il le DIT et n'attribue pas la divergence au port.

DISCIPLINE : deux boards de TAILLES DIFFERENTES (un seul ne prouverait rien sur l'ordre des
tuiles), un runner a la fois, dispose dans le `finally`, state-files sous `logs/`.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe_477r16_allocation_entites_ecs as R16  # noqa: E402
from engine.streams import StreamCache, StreamDispatcher  # noqa: E402
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.game_setup import (GameSetup, PlayerSetup, TileSetup,  # noqa: E402
                                       UnitSetup, emit_game_setup)

ROOT = HERE.parents[1]
BOARDS = ROOT / "data" / "boards"
OUT = ROOT / "logs"
HOST = "http://127.0.0.1:8765"

ROSTER_P = "astraBullgryn"
ROSTER_A = "thousTzaangor"
SEED = 777
#: Tailles DIFFERENTES (35 vs 63 tuiles) : deux boards de meme taille rendraient les memes ids
#: et se liraient a tort comme une preuve (piege mesure par #477-r15).
BOARDS_DEFAUT = ("C1_02", "MC1_67")


class MesureImpossible(RuntimeError):
    """Une source manque -- on le DIT, on ne rend pas un verdict."""


def rpc(session: int, method: str, args: dict, timeout: int = 90) -> dict:
    body = json.dumps({"method": method, "args": [args], "timeout": 60000}).encode()
    req = urllib.request.Request("%s/api/scripts/%d/rpc" % (HOST, session), data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()).get("result") or {}
    except (urllib.error.URLError, OSError) as e:
        raise MesureImpossible("RPC %s injoignable : %s" % (method, e)) from e


def session_courante() -> int:
    try:
        with urllib.request.urlopen("%s/api/admin/status" % HOST, timeout=10) as r:
            st = json.loads(r.read().decode())
    except (urllib.error.URLError, OSError) as e:
        raise MesureImpossible("host injoignable : %s" % e) from e
    sid = ((st.get("session") or {}).get("id"))
    if sid is None:
        raise MesureImpossible("aucune session Frida vivante")
    return int(sid)


def build(board: str, state_file: Path) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(SEED), "--board", board,
           "--p-units", ROSTER_P, "--a-units", ROSTER_A,
           "--record-replay", "--no-ai", "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    if not state_file.is_file():
        raise MesureImpossible("build %s echoue : %s" % (board, (p.stderr or p.stdout)[-500:]))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def dispose(state_file: Path) -> None:
    subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", str(state_file)],
                   cwd=str(HERE), capture_output=True, text=True, timeout=180)


# --- Etape 1 : isoler le groupe racine `System_GameSetup` -------------------

def groupe_racine(flux: str, nom: str) -> str:
    """Le PREMIER groupe racine `Group=<nom>` du flux, `Finish_Group` compris.

    Decoupe par PILE, pas par comptes egaux : deux comptes egaux couvriraient un
    `Finish_Group` sans groupe ouvert suivi d'un groupe jamais ferme."""
    lignes = flux.split("\n")
    debut = next((i for i, l in enumerate(lignes) if l == "Group=%s " % nom
                  or l.startswith("Group=%s " % nom)), None)
    if debut is None:
        raise MesureImpossible("aucun `Group=%s` a profondeur 0 dans le flux" % nom)
    pile = 0
    for i in range(debut, len(lignes)):
        s = lignes[i]
        if CONF.RE_GROUP.match(s):
            pile += 1
        elif CONF.RE_FINISH.match(s):
            pile -= 1
            if pile == 0:
                return "\n".join(lignes[debut:i + 1]) + "\n"
    raise MesureImpossible("groupe `%s` jamais ferme" % nom)


# --- Etape 2 : les ENTREES du port, depuis des canaux independants ----------

def tuiles_du_board(board: str) -> list[tuple[int, int]]:
    """(colonne, ligne) de chaque tuile, dans l'ordre de parcours du DUMP DE BOARD.

    C'est un canal INDEPENDANT du flux : si cet ordre ne correspondait pas a celui de
    `SetupGameOperation$$AddTiles`, toutes les lignes `AddTile` divergeraient."""
    for kind in ("pvp", "syncPvp", "global"):
        p = BOARDS / kind / ("%s.json" % board)
        if p.is_file():
            grille = json.loads(p.read_text(encoding="utf-8"))["board"]["Tiles"]
            return [(c, r) for c, col in enumerate(grille)
                    for r in range(len(col["Tile"]))]
    raise MesureImpossible("board dump absent : %s (relancer `python dump_boards.py`)" % board)


def entites_plateformes(flux_setup: str) -> list[int]:
    """Les ids d'entite des `Action=AddMachinePlatform` du flux NATIF.

    Ce n'est plus une ENTREE du port (elles sont derivees depuis #477-r16) : c'est un
    RECOUPEMENT -- la regle derivee doit rendre ces memes ids."""
    return [int(m.group("entity")) for m in
            (CONF.RE_ACTION.match(l) for l in flux_setup.split("\n"))
            if m and m.group("sym") == "AddMachinePlatform"]


def premiere_tuile(flux_setup: str) -> int:
    """L'id d'entite de la PREMIERE tuile. Meme statut que `table_joueurs` : entree du natif."""
    for ligne in flux_setup.split("\n"):
        m = CONF.RE_ACTION.match(ligne)
        if m and m.group("sym") == "AddTile":
            return int(m.group("entity"))
    raise MesureImpossible("aucun `Action=AddTile` dans le groupe de deploiement")


def unites_observees(session: int, rid: int) -> list[dict]:
    return rpc(session, "observeBattle", {"runnerId": rid}).get("units") or []


# --- Etape 3 : emettre et comparer ------------------------------------------

class Capture:
    """Un `IStreamCacheListener` : ne garde que les groupes RACINE flushes."""

    def __init__(self) -> None:
        self.racines: list[str] = []

    def on_root_group_finished(self, group: str) -> None:
        self.racines.append(group)

    def on_log(self, chunk: str) -> None:
        pass


def emettre(setup: GameSetup) -> str:
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    emit_game_setup(events, setup)
    if len(capture.racines) != 1:
        raise MesureImpossible("l'emetteur a flushe %d groupe(s) racine, attendu 1"
                               % len(capture.racines))
    return capture.racines[0]


def scenario(session: int, board: str) -> dict:
    state = OUT / ("state-477r15a-%s.json" % board)
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = build(board, state)
    try:
        flux = (rpc(session, "replayOutputStream",
                    {"runnerId": rid, "maxChars": 8000000}).get("outputStream") or "")
        if not flux:
            raise MesureImpossible("`replayOutputStream` rend un flux VIDE")
        setup_natif = groupe_racine(flux, "System_GameSetup")
        obs = unites_observees(session, rid)
    finally:
        dispose(state)

    # --- LES IDS D'ENTITE SONT DERIVES, plus copies (#477-r16, merge le 2026-08-05).
    # `deriver_regle()` rend P, E et `3 + P + E` depuis les ENTREES versionnees (seed BC, dumps,
    # tables statiques lues au decompile). Un SEUL terme lui manque -- `GetDerivedEnvironmentAbilities`,
    # obtenu par DIFFERENCE et donc capable d'absorber en silence toute autre allocation manquee
    # avant les tuiles. C'est `#477-r16-r1` : on ne le fige PAS, on le mesure et on le PUBLIE.
    regle = R16.deriver_regle()
    largeur, hauteur = R16.taille_board(board)
    #  Les JOUEURS sont derives INTEGRALEMENT : ils sont alloues AVANT les env abilities, donc en
    #  amont du terme inconnu. Le natif itere un `SortedDictionary`, d'ou le tri par cle.
    joueurs = [(3 + i, int(cle)) for i, cle in enumerate(regle["cles_joueurs"])]
    base_sans_derived = int(regle["premier_id_tuile_sans_derived"])
    base_natif = premiere_tuile(setup_natif)
    derived = base_natif - base_sans_derived      # LE terme non derive -- #477-r16-r1
    base_tuile = base_sans_derived + derived
    coords = tuiles_du_board(board)
    # (col, row) -> entite de tuile, table CONSTRUITE par le port a partir de son propre ordre.
    entite_de_tuile = {xy: base_tuile + i for i, xy in enumerate(coords)}
    #  Plateformes puis unites : DERIVES de la base, plus lus du flux.
    plateformes_derivees = [base_tuile + largeur * hauteur,
                            base_tuile + largeur * hauteur + 1]
    premiere_unite_derivee = base_tuile + largeur * hauteur + R16.NB_PLATEFORMES_MOW

    # ⚠ `observeBattle.units[].playerId` porte deja l'ENTITE du joueur, pas son `PlayerId` de
    # configuration -- MESURE ici (il vaut 3/4, pas 11/12), et c'est exactement le premier des
    # trois pieges de lecture de #477-r11, transpose du flux vers le RPC d'etat. Il alimente
    # donc `Unit_Owner_Id` DIRECTEMENT, sans passer par la table des joueurs.
    entites_joueurs = [ent for ent, _ in joueurs]
    # Les unites du deploiement sont celles de l'equipe ADVERSE (hypothese de MONTAGE, verifiee
    # plus bas contre le nombre d'`Action=AddUnit` du groupe natif). Le joueur humain est le
    # PREMIER `AddPlayer` du flux.
    mien = entites_joueurs[0] if entites_joueurs else None
    adverses = [u for u in obs if int(u.get("playerId", -1)) != mien]
    attendus = len(re.findall(r"^ *Action=AddUnit ", setup_natif, re.M))

    units = []
    for u in sorted(adverses, key=lambda x: int(x["squadId"])):
        xy = (int(u["col"]), int(u["row"]))
        units.append(UnitSetup(entity_id=int(u["squadId"]),
                               owner_id=int(u["playerId"]),
                               foot_tile_ids=[entite_de_tuile[xy]]))
    setup_port = emettre(GameSetup(
        players=[PlayerSetup(ent, pid) for ent, pid in joueurs],
        tiles=[TileSetup(entite_de_tuile[xy], xy[0], xy[1]) for xy in coords],
        platform_entity_ids=plateformes_derivees,
        units=units))

    rap = CONF.comparer(setup_natif, setup_port, entrees_du_natif=(
        "GetDerivedEnvironmentAbilities = %d -- LE SEUL terme non derive de l'offset "
        "d'allocation (#477-r16-r1) : table statique non lue, obtenue ici par DIFFERENCE, donc "
        "capable d'absorber toute autre allocation manquee avant les tuiles" % derived,
        "Tag=Tile_IsTerritory -- aucun porteur dans le board dump, emis a 0 en dur "
        "(#477-r15-r3)",
    ))
    return {"board": board, "rapport": rap, "tuiles": len(coords),
            "unites_emises": len(units), "addunit_natifs": attendus,
            "montage_coherent": len(units) == attendus,
            "derived": derived, "base_tuile": base_tuile,
            # Recoupement GRATUIT : l'id d'unite derive de la regle vs celui du canal
            # INDEPENDANT `observeBattle.squadId`. Deux sources, un seul chiffre.
            "premiere_unite_derivee": premiere_unite_derivee,
            "premiere_unite_observee": (min(int(u["squadId"]) for u in adverses)
                                        if adverses else None),
            "plateformes_derivees": plateformes_derivees,
            "plateformes_natives": entites_plateformes(setup_natif)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--boards", default=",".join(BOARDS_DEFAUT))
    args = ap.parse_args()

    try:
        session = args.session if args.session is not None else session_courante()
    except MesureImpossible as e:
        print("[477-r15a] MESURE IMPOSSIBLE : %s" % e)
        return 2

    boards = [b.strip() for b in args.boards.split(",") if b.strip()]
    print("[477-r15a] session=%d  boards=%s" % (session, ",".join(boards)))
    resultats, exercees_corpus = [], set()
    for board in boards:
        print("")
        print("=== BOARD %s ===" % board)
        try:
            res = scenario(session, board)
        except MesureImpossible as e:
            print("  MESURE IMPOSSIBLE : %s" % e)
            return 2
        resultats.append(res)
        exercees_corpus |= res["rapport"].cles_exercees
        print("  tuiles du board dump = %d   unites emises = %d   `Action=AddUnit` natifs = %d"
              % (res["tuiles"], res["unites_emises"], res["addunit_natifs"]))
        print("  ALLOCATION DERIVEE (#477-r16) : 1re tuile = %d  plateformes = %s  1re unite = %d"
              % (res["base_tuile"], res["plateformes_derivees"], res["premiere_unite_derivee"]))
        # Recoupements : la regle DERIVEE contre deux canaux qui ne la connaissent pas.
        if res["plateformes_derivees"] != res["plateformes_natives"]:
            print("  ROUGE ALLOCATION : plateformes derivees %s != flux natif %s"
                  % (res["plateformes_derivees"], res["plateformes_natives"]))
        if res["premiere_unite_observee"] != res["premiere_unite_derivee"]:
            print("  ROUGE ALLOCATION : 1re unite derivee %d != observeBattle.squadId %s"
                  % (res["premiere_unite_derivee"], res["premiere_unite_observee"]))
        print("  terme NON derive (#477-r16-r1) GetDerivedEnvironmentAbilities = %d"
              % res["derived"])
        if not res["montage_coherent"]:
            print("  ⚠ MONTAGE : le filtre « unites adverses » ne predit pas le nombre d'AddUnit "
                  "du groupe natif -- les divergences d'AddUnit ci-dessous accusent le MONTAGE, "
                  "pas le port.".replace("⚠", "!"))
        for ligne in CONF.rapport(res["rapport"]):
            print("  " + ligne)

    # --- PURGE : evaluee sur le CORPUS COMPLET, jamais sur un scenario isole.
    perimees = CONF.entrees_perimees(exercees_corpus)
    nouvelles = sum(len(r["rapport"].nouvelles) for r in resultats)
    horsforme = sum(len(r["rapport"].hors_forme) for r in resultats)
    montage_ko = [r["board"] for r in resultats if not r["montage_coherent"]]

    print("")
    print("=== VERDICT (3 etats, corpus = %d board(s)) ===" % len(resultats))
    for r in resultats:
        rp = r["rapport"]
        etat = ("conforme" if rp.conforme else
                ("divergent CONNU" if not rp.nouvelles else "divergent NOUVEAU"))
        print("  %-10s %-18s egales=%d/%d  connues=%d  NOUVELLES=%d"
              % (r["board"], etat, rp.egales, rp.lignes_natif,
                 len(rp.connues), len(rp.nouvelles)))
    if perimees:
        print("  REGISTRE PERIME : %d entree(s) -- a SUPPRIMER du registre :" % len(perimees))
        for cle in perimees:
            print("      %s" % cle)
    rc = 0
    if nouvelles:
        print("  ROUGE : %d divergence(s) NOUVELLE(s)." % nouvelles)
        rc = 1
    if horsforme:
        print("  ROUGE : %d ligne(s) hors des 4 formes -- une forme nous manque." % horsforme)
        rc = 1
    if perimees:
        print("  ROUGE : le registre porte des entrees que le corpus n'exerce plus.")
        rc = 1
    alloc_ko = [r["board"] for r in resultats
                if r["plateformes_derivees"] != r["plateformes_natives"]
                or r["premiere_unite_observee"] != r["premiere_unite_derivee"]]
    if alloc_ko:
        print("  ROUGE : la regle d'allocation DERIVEE (#477-r16) ne recoupe pas le live sur %s."
              % ",".join(alloc_ko))
        rc = 1
    if montage_ko:
        print("  ROUGE : montage incoherent sur %s -- verdict non attribuable au port."
              % ",".join(montage_ko))
        rc = 2
    if rc == 0:
        print("  VERT : toutes les divergences sont CONNUES et le registre est a jour.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
