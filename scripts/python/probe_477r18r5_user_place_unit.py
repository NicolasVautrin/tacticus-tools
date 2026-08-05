#!/usr/bin/env python3
"""#477-r18-r5 -- `User_PlaceUnit`, la PREMIERE TRANCHE DU DEROULE, confrontee en live.

    python probe_477r18r5_user_place_unit.py [--session N] [--boards C1_02,MC1_67]
                                             [--p-units X,Y,Z] [--a-units W]

CE QU'IL MESURE
---------------
Le port emet desormais l'ENVELOPPE `User_PlaceUnit` (`engine.streams.input_messages`), mirror
d'`IdunBattle.Messages.InputMessageProcessor$$Visit(message:IdunBattle.Messages.AddUnitMessage)`
et de sa fonction locale
`InputMessageProcessor.u003Cu003Ec__DisplayClass9_0$$u003CVisitu003Eg__AddUnit|0`. Ce probe
confronte TOUS les groupes racines `User_PlaceUnit` du flux natif a ce que le port emet, a
l'egalite BRUTE ligne a ligne -- meme barre et meme cliquet a trois etats que
`probe_477r15a_stream_conformance.py`, dont il reutilise les canaux d'entree.

POURQUOI CETTE TRANCHE EST LA PREMIERE (#477-r18 § 6). Son CONTENU est un `Group=AddUnit`
strictement identique a celui que le port emet deja dans `System_GameSetup` : le seul manque
etait l'enveloppe. D'ou `+1 GroupType, +0 StepType, +0 TagKey` -- verifie par la borne (a),
qui doit montrer `StepType` et `TagKey` INCHANGES. S'ils bougent, la tranche a deborde.

LES ENTREES VIENNENT DE CANAUX INDEPENDANTS DU FLUX -- aucune n'en est copiee
-----------------------------------------------------------------------------
  ordre des groupes   <- l'ordre CROISSANT des ids d'entite. Ce n'est pas un tri de confort :
                         l'allocation ECS est un compteur croissant (#477-r16), donc l'ordre
                         chronologique des `AddUnit` EST l'ordre croissant des ids. La sequence
                         derivee est RECOUPEE contre celle du flux, jamais lue depuis lui ;
  quelles unites      <- `observeBattle.units[].playerId` == l'entite du joueur HUMAIN (le
                         premier `AddPlayer`). Sur un runner monte par `rl_duel build`, les
                         unites adverses sont posees par `SetupGameOperation$$AddPredefinedUnits`
                         (groupe `System_GameSetup`) et celles du joueur par des
                         `AddUnitMessage` separes -- c'est une HYPOTHESE DE MONTAGE, VERIFIEE
                         ici contre le nombre de groupes natifs, jamais supposee ;
  tuile du pied       <- le BOARD DUMP `data/boards/<kind>/<id>.json` + la regle d'allocation
                         de #477-r16, appariee par la position `observeBattle` (col, row) ;
  `Unit_SpawnSource`  <- `SpawnSource.Deployment` (5), LU DANS LE MONTAGE :
                         `frida/hooks/features/launch.ts` ecrit `msg.add(0x28).writeS32(5)`
                         apres le ctor a 4 arguments. Le natif, lui, ne le fixe pas : le
                         decompile de la fonction locale lit `AddUnitMessage+0x28` et le passe
                         tel quel a `Core.Services.OperationProcessor$$AddUnit`. C'est donc
                         une grandeur du MONTAGE, pas une constante du jeu -- cf. borne (c) ;
  stats / abilities   <- `combatSnapshot`, `observeBattle`, `unitAbilityStates`, exactement les
                         memes lectures que #477-r15 tranche D (reutilisees telles quelles).

⚠ UNE HYPOTHESE DE REGIME, MESUREE ET PUBLIEE. Les tags de `ChangeStats`/`ChangeAbility` sont
ecrits AU MOMENT DU PLACEMENT ; le port les lit APRES le build. Entre les deux, le natif joue
`System_StartMatch` (qui applique des effets). Le probe ne suppose pas que rien n'a bouge : il
BALAYE le flux posterieur au dernier `User_PlaceUnit` et signale tout `Tag=UnitStats_*` portant
sur une entite placee. Le critere est le PREFIXE du tag, pas une liste blanche d'actions -- une
liste blanche ne peut pas montrer ce qu'elle a oublie.

DISCIPLINE : deux boards de TAILLES DIFFERENTES, un runner a la fois, dispose dans le `finally`,
state-files sous `logs/`. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe_477r15a_stream_conformance as R15A  # noqa: E402
import probe_477r16_allocation_entites_ecs as R16  # noqa: E402
from engine.entities.spawn_source import SpawnSource  # noqa: E402
from engine.streams import StreamCache, StreamDispatcher  # noqa: E402
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.game_setup import UnitSetup  # noqa: E402
from engine.streams.input_messages import visit_add_unit_message  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "logs"

MesureImpossible = R15A.MesureImpossible

#: Les memes deux boards que #477-r15a : tailles DIFFERENTES (35 vs 63 tuiles), donc bases
#: d'allocation et ids de tuile differents. Un seul board ne prouverait rien sur l'appariement.
BOARDS_DEFAUT = ("C1_02", "MC1_67")
#: TROIS unites cote joueur : un seul `User_PlaceUnit` ne testerait NI l'ordre NI la repetition
#: de l'enveloppe. Les trois portent des kits distincts (stats et abilities differentes), donc
#: le contenu du `Group=AddUnit` varie d'un groupe a l'autre.
ROSTER_P = "astraBullgryn,astraYarrick,adeptCanoness"
ROSTER_A = "thousTzaangor"


def groupes_racines(flux: str, nom: str) -> list[str]:
    """TOUS les groupes racines `Group=<nom>` du flux, dans l'ordre, `Finish_Group` compris.

    Decoupe par PILE (meme regle que `probe_477r15a`) et non par comptes egaux. Rend une LISTE :
    ne prendre que le premier est exactement ce qui ferait passer une tranche a 3 groupes pour
    une tranche a 1."""
    lignes = flux.split("\n")
    out: list[str] = []
    i = 0
    prefixe = "Group=%s " % nom
    while i < len(lignes):
        if not lignes[i].startswith(prefixe):
            i += 1
            continue
        pile = 0
        for j in range(i, len(lignes)):
            if CONF.RE_GROUP.match(lignes[j]):
                pile += 1
            elif CONF.RE_FINISH.match(lignes[j]):
                pile -= 1
                if pile == 0:
                    out.append("\n".join(lignes[i:j + 1]) + "\n")
                    i = j + 1
                    break
        else:
            raise MesureImpossible("groupe `%s` ouvert ligne %d et jamais ferme" % (nom, i))
    return out


def fin_du_dernier(flux: str, groupes: list[str]) -> int:
    """L'index de la ligne qui SUIT le dernier groupe racine extrait.

    Sert au balayage de stabilite d'etat. Derive de la position du dernier groupe dans le flux,
    pas d'un comptage de lignes -- deux groupes de meme texte ne fausseraient rien."""
    if not groupes:
        return 0
    pos = flux.rindex(groupes[-1]) + len(groupes[-1])
    return flux[:pos].count("\n")


def stabilite_etat(flux: str, depuis: int, entites: set) -> tuple:
    """Le flux POSTERIEUR au dernier `User_PlaceUnit` touche-t-il les grandeurs que le port a
    lues APRES coup ?

    Rend `(alertes, lignes_examinees, actions_sur_entites)`. Le critere est le PREFIXE du tag
    (`UnitStats_`), derive du vocabulaire, jamais une liste blanche d'`Action=` : une liste
    blanche ne peut pas montrer le mutateur qu'elle a oublie. `actions_sur_entites` est le
    TEMOIN -- un zero d'alerte sur zero action visitee ne prouve rien."""
    lignes = flux.split("\n")[depuis:]
    alertes: list[str] = []
    action_courante = None
    entite_courante = None
    actions_sur_entites = 0
    for ligne in lignes:
        m = CONF.RE_ACTION.match(ligne)
        if m:
            action_courante = m.group("sym")
            try:
                entite_courante = int(m.group("entity"))
            except ValueError:
                entite_courante = None      # NO_ENTITY
            if entite_courante in entites:
                actions_sur_entites += 1
            continue
        t = CONF.RE_TAG.match(ligne)
        if t and entite_courante in entites and t.group("sym").startswith("UnitStats_"):
            alertes.append("Action=%s Entity=%s %s"
                           % (action_courante, entite_courante, ligne.strip()))
    return alertes, len(lignes), actions_sur_entites


class Capture:
    """Un `IStreamCacheListener` : ne garde que les groupes RACINE flushes."""

    def __init__(self) -> None:
        self.racines: list[str] = []

    def on_root_group_finished(self, group: str) -> None:
        self.racines.append(group)

    def on_log(self, chunk: str) -> None:
        pass


def emettre(units: list) -> tuple:
    """Emet un `User_PlaceUnit` par unite et rend `(texte concatene, nb de groupes racine)`.

    Le natif flushe UN groupe racine par message d'entree : la concatenation reproduit ce que
    `IdunBattleLogic.Replay.ReplayRecorder$$OnStreamCacheRootGroupFinished` append au tampon."""
    cache = StreamCache()
    capture = Capture()
    cache.add_listener(capture)
    events = StreamDispatcher()
    events.subscribe(cache)
    for unit in units:
        visit_add_unit_message(events, unit)
    return "".join(capture.racines), len(capture.racines)


def scenario(session: int, board: str, p_units: str, a_units: str) -> dict:
    signature = "%08x" % (zlib.crc32(("%s|%s" % (p_units, a_units)).encode()) & 0xffffffff)
    state = OUT / ("state-477r18r5-%s-%s.json" % (board, signature))
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = R15A.build(board, state, p_units, a_units)
    try:
        flux = (R15A.rpc(session, "replayOutputStream",
                         {"runnerId": rid, "maxChars": 8000000}).get("outputStream") or "")
        if not flux:
            raise MesureImpossible("`replayOutputStream` rend un flux VIDE")
        natifs = groupes_racines(flux, "User_PlaceUnit")
        obs = R15A.unites_observees(session, rid)
        par_cs = R15A._index(R15A.rpc(session, "combatSnapshot",
                                      {"runnerId": rid}).get("units"), "entityId")
        par_ua = R15A._index(R15A.rpc(session, "unitAbilityStates",
                                      {"runnerId": rid}).get("units"), "entityId")
        par_dv = R15A._index(R15A.rpc(session, "decisionView",
                                      {"runnerId": rid, "allAbilities": True}).get("units"), "id")
    finally:
        R15A.dispose(state)

    if not natifs:
        raise MesureImpossible(
            "aucun `Group=User_PlaceUnit` a profondeur 0 -- le montage ne place pas d'unite "
            "joueur par message (verifier `--p-units`)")

    # --- Les ids d'entite sont DERIVES (#477-r16 / -r16-r1), plus copies du flux.
    regle = R16.deriver_regle()
    largeur, hauteur = R16.taille_board(board)
    base_tuile = int(regle["premier_id_tuile_prevu"])
    coords = R15A.tuiles_du_board(board)
    entite_de_tuile = {xy: base_tuile + i for i, xy in enumerate(coords)}
    # L'entite du joueur HUMAIN : le premier `AddPlayer`, c'est-a-dire la premiere cle du
    # `SortedDictionary` des joueurs -- meme derivation que `probe_477r15a`.
    entites_joueurs = [3 + i for i, _ in enumerate(regle["cles_joueurs"])]
    mien = entites_joueurs[0] if entites_joueurs else None
    # ⚠ L'ORDRE EST DERIVE, PAS LU : l'allocation ECS etant un compteur croissant, l'ordre
    # chronologique des `AddUnit` est l'ordre croissant des ids d'entite.
    miennes = sorted((u for u in obs if int(u.get("playerId", -1)) == mien),
                     key=lambda x: int(x["squadId"]))

    units = []
    ecarts_dv: list[str] = []
    for u in miennes:
        sid = int(u["squadId"])
        xy = (int(u["col"]), int(u["row"]))
        if sid not in par_cs or sid not in par_ua:
            raise MesureImpossible("substrat de ChangeStats/ChangeAbility absent pour l'entite "
                                   "%d (combatSnapshot=%s unitAbilityStates=%s)"
                                   % (sid, sid in par_cs, sid in par_ua))
        if xy not in entite_de_tuile:
            raise MesureImpossible("position (%d,%d) hors du board dump %s" % (xy[0], xy[1], board))
        actives, triggered = R15A.abilities_unite(par_ua[sid], par_dv.get(sid, {}))
        ecarts_dv += R15A.recouper_avec_decision_view(par_ua[sid], par_dv.get(sid, {}))
        units.append(UnitSetup(entity_id=sid,
                               owner_id=int(u["playerId"]),
                               foot_tile_ids=[entite_de_tuile[xy]],
                               # LU dans `frida/hooks/features/launch.ts`, pas dans le flux.
                               source=int(SpawnSource.Deployment),
                               full_state=R15A.etat_complet(par_cs[sid], u, par_ua[sid]),
                               active_abilities=actives,
                               triggered_abilities=triggered))
    texte_port, groupes_port = emettre(units)
    texte_natif = "".join(natifs)

    # --- RECOUPEMENT D'ORDRE : la sequence derivee contre celle du flux. Le port n'a jamais lu
    #     cette derniere ; si les deux different, la regle « ids croissants » est fausse.
    ordre_natif = [int(m.group("entity")) for m in
                   (CONF.RE_ACTION.match(l) for g in natifs for l in g.split("\n"))
                   if m and m.group("sym") == "AddUnit"]
    ordre_port = [int(u.entity_id) for u in units]
    entites_placees = set(ordre_natif)
    alertes, lignes_apres, actions_apres = stabilite_etat(
        flux, fin_du_dernier(flux, natifs), entites_placees)
    # TEMOIN DE MONTAGE : la valeur reellement emise par le natif pour `Unit_SpawnSource`.
    sources_natives = sorted({int(m.group("value")) for m in
                              (CONF.RE_TAG.match(l) for g in natifs for l in g.split("\n"))
                              if m and m.group("sym") == "Unit_SpawnSource"})

    rap = CONF.comparer(texte_natif, texte_port, entrees_du_natif=(
        "Tag=Tile_IsTerritory -- hors de ce groupe (aucune `Action=AddTile` sous "
        "`User_PlaceUnit`) ; l'entree reste NOMMEE pour le deploiement (#477-r15-r3)",
        "Tag=UnitStats_TriggeredAbility_{AmmoCost,EnoughAmmo} -- NON CONFRONTES : `AmmoCost` "
        "est null sur toute unite reguliere (les munitions ne mordent que sur les Machines of "
        "War, qui passent par `AddMachineOperation`, hors de ce groupe)",
        "Tag=Unit_SpawnSource -- la valeur `Deployment` (5) est celle que NOTRE MONTAGE ecrit "
        "(`frida/hooks/features/launch.ts`, `msg.add(0x28).writeS32(5)`). Le natif la LIT du "
        "message (`AddUnitMessage+0x28`) : ce que ce probe confronte, c'est que le port la "
        "recopie dans le tag, PAS qu'une partie reelle envoie cette valeur-la",
    ))
    return {"board": board, "rapport": rap,
            "groupes_natifs": len(natifs), "groupes_port": groupes_port,
            "unites_miennes": len(units), "mien": mien,
            "ordre_natif": ordre_natif, "ordre_port": ordre_port,
            "base_tuile": base_tuile, "tuiles": len(coords),
            "largeur_hauteur": (largeur, hauteur),
            "alertes_stabilite": alertes, "lignes_apres": lignes_apres,
            "actions_apres": actions_apres, "sources_natives": sources_natives,
            "ecarts_dv": ecarts_dv,
            "lignes_natif_total": flux.count("\n"),
            "lignes_groupe": sum(g.count("\n") for g in natifs)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--boards", default=",".join(BOARDS_DEFAUT))
    ap.add_argument("--p-units", default=ROSTER_P)
    ap.add_argument("--a-units", default=ROSTER_A)
    args = ap.parse_args()

    try:
        session = args.session if args.session is not None else R15A.session_courante()
    except MesureImpossible as e:
        print("[477-r18-r5] MESURE IMPOSSIBLE : %s" % e)
        return 2

    boards = [b.strip() for b in args.boards.split(",") if b.strip()]
    print("[477-r18-r5] session=%d  boards=%s  p=%s  a=%s"
          % (session, ",".join(boards), args.p_units, args.a_units))
    resultats, exercees_corpus = [], set()
    for board in boards:
        print("")
        print("=== BOARD %s ===" % board)
        try:
            res = scenario(session, board, args.p_units, args.a_units)
        except MesureImpossible as e:
            print("  MESURE IMPOSSIBLE : %s" % e)
            return 2
        resultats.append(res)
        exercees_corpus |= res["rapport"].cles_exercees
        print("  board %dx%d, %d tuiles, 1re tuile derivee = %d"
              % (res["largeur_hauteur"][0], res["largeur_hauteur"][1],
                 res["tuiles"], res["base_tuile"]))
        print("  groupes `User_PlaceUnit` : natif = %d   port = %d   unites du joueur (entite "
              "%s) = %d" % (res["groupes_natifs"], res["groupes_port"], res["mien"],
                            res["unites_miennes"]))
        print("  POIDS : %d lignes de groupe sur %d lignes de flux"
              % (res["lignes_groupe"], res["lignes_natif_total"]))
        print("  ORDRE derive (ids croissants) = %s" % res["ordre_port"])
        print("        flux natif              = %s" % res["ordre_natif"])
        if res["ordre_natif"] != res["ordre_port"]:
            print("  ROUGE ORDRE : la regle « ids croissants » ne recoupe pas le flux.")
        print("  MONTAGE : `Unit_SpawnSource` emis par le natif = %s (le port ecrit %d, LU dans "
              "launch.ts)" % (res["sources_natives"], int(SpawnSource.Deployment)))
        print("  STABILITE D'ETAT : %d alerte(s) `Tag=UnitStats_*` sur une entite placee, apres "
              "le dernier groupe ; %d ligne(s) examinee(s), %d `Action=` portant sur ces entites"
              % (len(res["alertes_stabilite"]), res["lignes_apres"], res["actions_apres"]))
        if res["actions_apres"] == 0:
            print("      ! TEMOIN VIDE : aucune `Action=` posterieure ne porte sur une entite "
                  "placee -- ce zero d'alerte ne prouve RIEN sur d'autres regimes (un tour joue, "
                  "une aura). Il dit seulement que CE corpus ne bouge pas entre placement et "
                  "lecture.")
        for a in res["alertes_stabilite"][:8]:
            print("      ALERTE : %s" % a)
        print("  RECOUPEMENT unitAbilityStates.state <-> decisionView : %d ecart(s)"
              % len(res["ecarts_dv"]))
        for e in res["ecarts_dv"]:
            print("      ROUGE RECOUPEMENT : %s" % e)
        for ligne in CONF.rapport(res["rapport"]):
            print("  " + ligne)

    nouvelles = sum(len(r["rapport"].nouvelles) for r in resultats)
    horsforme = sum(len(r["rapport"].hors_forme) for r in resultats)

    print("")
    print("=== VERDICT (3 etats, corpus = %d board(s)) ===" % len(resultats))
    for r in resultats:
        rp = r["rapport"]
        etat = ("conforme" if rp.conforme else
                ("divergent CONNU" if not rp.nouvelles else "divergent NOUVEAU"))
        print("  %-10s %-18s egales=%d/%d  connues=%d  NOUVELLES=%d  groupes=%d"
              % (r["board"], etat, rp.egales, rp.lignes_natif,
                 len(rp.connues), len(rp.nouvelles), r["groupes_natifs"]))
    rc = 0
    if nouvelles:
        print("  ROUGE : %d divergence(s) NOUVELLE(s)." % nouvelles)
        rc = 1
    if horsforme:
        print("  ROUGE : %d ligne(s) hors des 4 formes -- une forme nous manque." % horsforme)
        rc = 1
    ordre_ko = [r["board"] for r in resultats if r["ordre_natif"] != r["ordre_port"]]
    if ordre_ko:
        print("  ROUGE : ordre derive != ordre du flux sur %s." % ",".join(ordre_ko))
        rc = 1
    stab_ko = [r["board"] for r in resultats if r["alertes_stabilite"]]
    if stab_ko:
        print("  ROUGE : l'etat lu APRES le build n'est pas celui du placement sur %s -- les "
              "divergences de VALEUR accusent le CANAL, pas le port." % ",".join(stab_ko))
        rc = 1
    recoup_ko = [r["board"] for r in resultats if r["ecarts_dv"]]
    if recoup_ko:
        print("  ROUGE : `GetActives()` et le walk de `Abilities@0x20` ne s'accordent pas sur %s."
              % ",".join(recoup_ko))
        rc = 1
    montage_ko = [r["board"] for r in resultats
                  if r["groupes_natifs"] != r["groupes_port"]]
    if montage_ko:
        print("  ROUGE : montage incoherent sur %s (nombre de groupes natif != port) -- verdict "
              "non attribuable au port." % ",".join(montage_ko))
        rc = 2
    if rc == 0:
        print("  VERT : les %d groupes `User_PlaceUnit` sont reproduits a l'EGALITE BRUTE."
              % sum(r["groupes_natifs"] for r in resultats))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
