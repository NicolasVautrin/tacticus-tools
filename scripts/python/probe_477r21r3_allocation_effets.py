"""#477-r21-r3 -- L'ALLOCATION ECS DES ENTITES D'EFFET, portee puis CONFRONTEE.

LA QUESTION EST BINAIRE : le port peut-il DERIVER l'identifiant ECS de chaque entite d'effet,
sans lire aucun id du flux natif ? Ce probe la decompose en cinq etages MESURES separement,
parce qu'un « oui » global aurait masque le seul etage qui repond non.

CE QUI TRANCHE EST LE DECOMPILE, et il est ferme :

    IdunBattle.Entities.Components.MatchComponent$$NextId    this.<+0x10> += 1 ; return
    IdunBattle.Entities.Components.MatchComponent$$ReturnLastId               -= 1
    IdunBattle.Entities.Components.MatchComponent$$.ctor     this.<+0x10> = 1
    IdunBattle.Operations.InitializeMatchOperation$$Execute  matchComponent.<+0x10> += 1
    IdunBattle.Operations.AddEffectOperation$$Execute        UN `NextId`, conditionnel

Neuf sites d'appel de `NextId` (xrefs Ghidra, liste exhaustive), DEUX de `ReturnLastId` -- tous
deux sur le chemin TUILE. Il n'existe donc AUCUN recyclage d'identifiant pendant le deroule.
Le port est `engine/streams/entity_allocator.py` ; ce probe le confronte.

CE QUE LE PROBE COPIE, ET IL LE DECLARE (borne (c)) :
  * le ROSTER deploye -- combien d'unites, combien de pieds chacune. C'est deja la borne (c) de
    #477-r15 (`GameSetup.units`), et cette tranche ne pretend pas la lever ;
  * la SEQUENCE des creations pendant le deroule -- quels effets, dans quel ordre (`#477-r21-r2`) ;
  * les unites SUMMONEES pendant le deroule (nombre et position dans la sequence).

CE QUE LE PROBE DERIVE, et ce sont les seules mesures :
  (A1) TOUS les identifiants du deploiement -- joueurs, tuiles, plateformes, unites, pieds ;
  (A2) l'ANCRE des identifiants du deroule (le premier id d'effet) ;
  (A3) la DENSITE : aucun trou inexplique dans l'intervalle alloue ;
  (A4) la MONOTONIE de l'ordre d'apparition, mesuree en INVERSIONS ;
  (A5) le modele naif « ancre + rang d'apparition », dont ce probe mesure la PORTEE REELLE.

Usage :
    python probe_477r21r3_allocation_effets.py [--session N] [--boards C1_02,MC1_67]
    python probe_477r21r3_allocation_effets.py --auto-test-gardes      # OFFLINE, aucune session
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe_477r15a_stream_conformance as R15A  # noqa: E402
import probe_477r16_allocation_entites_ecs as R16  # noqa: E402
import probe_477r19_process_removals as R19  # noqa: E402
import probe_477r21_activation_tree as R21  # noqa: E402
from engine.entities.entity_type import EntityType  # noqa: E402
from engine.streams.entity_id import BEntityId, NO_ENTITY
from engine.streams.group_type import GroupType
from engine.streams.step_type import StepType
from engine.streams.tag_key import TagKey  # noqa: E402
from engine.streams.entity_allocator import (MatchComponent, add_effect,  # noqa: E402
                                             add_unit, new_match_after_setup)
from engine.streams.game_setup import PLATFORM_POSITIONS  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "logs"

MesureImpossible = R15A.MesureImpossible

#: Memes boards que #477-r16 / -r19 / -r20 / -r21 : 35 vs 63 tuiles.
BOARDS_DEFAUT = ("C1_02", "MC1_67")

#: Le roster crafte du troisieme scenario, identique a celui de #477-r21 -- il DEPLACE le regime
#: (2v2 au lieu de 5v5) au lieu de rejouer le meme.
ROSTER_CRAFTE = ("MC1_67", "adeptHospitaller,astraBullgryn", "blackTerminator,worldJakhal")

RE_ACTION = re.compile(r"^(?P<ind>\s*)Action=(?P<sym>\w+) Entity=(?P<ent>-?\w+)")
RE_GROUPE = re.compile(r"^(?P<ind>\s*)Group=(?P<sym>\w+) Entity=(?P<ent>-?\w+)")
RE_TAGL = re.compile(r"^\s*Tag=(?P<sym>\w+):(?P<val>-?\d+)")

#: Les actions du flux qui SIGNALENT une allocation. `ChangeStats`, `ReceiveEffect`, ... portent
#: un `Entity=` DEJA alloue : les compter fabriquerait des doublons.
ACTIONS_ALLOUANTES = (StepType.AddPlayer.name, StepType.AddTile.name,
                      StepType.AddMachinePlatform.name, StepType.AddUnit.name)


# --------------------------------------------------------------------------------- observation

@dataclass
class UniteObs:
    """Une `Action=AddUnit` observee : son entite et son nombre de PIEDS."""

    entity_id: int
    foot_count: int
    dans_le_deploiement: bool


@dataclass
class Evenement:
    """Un evenement du DEROULE qui consomme des identifiants, dans l'ordre du flux.

    ⚠ CE QUE LE PORT EN RECEVRA EN (A5) EST `kind` ET `foot_count`, JAMAIS `entity_id` : ce
    dernier n'est la que pour la CONFRONTATION. C'est la separation qui fait de (A5) une mesure
    et non un recopiage."""

    kind: str
    """`unit` (`Action=AddUnit` hors deploiement) ou `effect` (1re apparition d'un
    `Group=Effect_Refresh`)."""
    foot_count: int
    entity_id: int
    racine: str


@dataclass
class FluxObs:
    """Ce que le probe LIT du flux -- rien de plus, et chaque champ est declare en borne (c)."""

    joueurs: List[int]
    tuiles: List[int]
    plateformes: List[int]
    unites: List[UniteObs]
    effets_ordre_apparition: List[int]
    """Ordre de PREMIERE apparition d'un `Group=Effect_Refresh Entity=<id>` dans TOUT le flux."""
    effets_bloc1: List[int]
    """Sous-suite restreinte au BLOC 1 de `System_StartMatch` (la decoupe de #477-r21)."""
    evenements: List[Evenement]
    """La SEQUENCE des consommations d'identifiant du deroule, dans l'ordre du flux."""
    lignes: int


def _entite(txt: str) -> int:
    """`Entity=` du flux -> entier. Le writer natif BOXE l'id en `IdunBattle.Core.BEntityId`
    avant de le formater, donc `0` s'y ecrit `NO_ENTITY` et non `0` (cf.
    `engine/streams/entity_id.py`). Un `int()` direct explose dessus."""
    return NO_ENTITY if txt == BEntityId.NO_ENTITY.name else int(txt)


def observer(flux: str) -> FluxObs:
    """Extrait du flux les seules grandeurs dont le probe a besoin.

    ⚠ LE DEPLOIEMENT SE DISTINGUE DU DEROULE PAR SON GROUPE RACINE, pas par une heuristique
    d'id : une unite SUMMONEE porte la meme `Action=AddUnit`, et la confondre avec une unite
    deployee decalerait toute l'ancre."""
    joueurs: List[int] = []
    tuiles: List[int] = []
    plateformes: List[int] = []
    unites: List[UniteObs] = []
    apparition: List[int] = []
    evenements: List[Evenement] = []
    vus = set()
    racine: Optional[str] = None
    courante: Optional[UniteObs] = None
    for ligne in flux.split("\n"):
        mg = RE_GROUPE.match(ligne)
        if mg:
            if len(mg.group("ind")) == 0:
                racine = mg.group("sym")
            if mg.group("sym") == GroupType.Effect_Refresh.name:
                ent = mg.group("ent")
                if ent not in vus:
                    vus.add(ent)
                    apparition.append(_entite(ent))
                    evenements.append(Evenement(kind="effect", foot_count=0,
                                                entity_id=_entite(ent), racine=racine or ""))
            courante = None
            continue
        ma = RE_ACTION.match(ligne)
        if ma:
            sym, ent = ma.group("sym"), _entite(ma.group("ent"))
            courante = None
            if sym == StepType.AddPlayer.name:
                joueurs.append(ent)
            elif sym == StepType.AddTile.name:
                tuiles.append(ent)
            elif sym == StepType.AddMachinePlatform.name:
                plateformes.append(ent)
            elif sym == StepType.AddUnit.name:
                deploiement = racine == GroupType.System_GameSetup.name
                courante = UniteObs(entity_id=ent, foot_count=0,
                                    dans_le_deploiement=deploiement)
                unites.append(courante)
                if not deploiement:
                    evenements.append(Evenement(kind="unit", foot_count=0, entity_id=ent,
                                                racine=racine or ""))
            continue
        mt = RE_TAGL.match(ligne)
        if mt and courante is not None and mt.group("sym").startswith(
                TagKey.Unit_Foot_Tile_Id_1.name[:-1]):
            courante.foot_count += 1
            if evenements and evenements[-1].kind == "unit" \
                    and evenements[-1].entity_id == courante.entity_id:
                evenements[-1].foot_count += 1
    return FluxObs(joueurs=joueurs, tuiles=tuiles, plateformes=plateformes, unites=unites,
                   effets_ordre_apparition=apparition, effets_bloc1=[], evenements=evenements,
                   lignes=flux.count("\n"))


def effets_du_bloc1(flux: str) -> List[int]:
    """Les ids d'effet apparus POUR LA PREMIERE FOIS dans le bloc 1 de `System_StartMatch`.

    La decoupe est celle de #477-r21 (`decouper_bloc1`), et elle porte ses quatre refus : c'est
    elle qui fait foi, pas un decoupage refait ici."""
    sequence = R19.sequence_racines(flux)
    cibles = [t for sym, t, _e in sequence if sym == GroupType.System_StartMatch.name]
    if len(cibles) != 1:
        raise MesureImpossible("%d groupe(s) `%s` -- le montage n'en envoie qu'UN"
                               % (len(cibles), GroupType.System_StartMatch.name))
    dec = R21.decouper_bloc1(cibles[0])
    vus, out = set(), []
    for ligne in dec["bloc1"]:
        m = RE_GROUPE.match(ligne)
        if m and m.group("sym") == GroupType.Effect_Refresh.name:
            ent = m.group("ent")
            if ent not in vus:
                vus.add(ent)
                out.append(_entite(ent))
    return out


# ------------------------------------------------------------------------------- les cinq etages

def etage_a1_deploiement(obs: FluxObs, board: str, seed_bc_path=None) -> dict:
    """(A1) TOUS les identifiants du DEPLOIEMENT, derives -- aucun id lu du flux.

    Les ENTREES sont : `P` et `E` (regle #477-r16, depuis la seule BC), `T` (le board), le
    nombre de plateformes (litteral de `game_setup.PLATFORM_POSITIONS`), et le ROSTER (nombre
    d'unites deployees + pieds de chacune, borne (c))."""
    regle = R16.deriver_regle(seed_bc_path)
    width, height = R16.taille_board(board)
    deployees = [u for u in obs.unites if u.dans_le_deploiement]
    match, alloc = new_match_after_setup(
        player_count=len(obs.joueurs),
        environment_ability_count=regle["E_lu"],
        tile_count=width * height,
        machine_of_war_platform_count=len(PLATFORM_POSITIONS),
        unit_foot_counts=[u.foot_count for u in deployees])
    prevu = {
        "joueurs": list(alloc.players),
        "tuiles": list(alloc.tiles),
        "plateformes": list(alloc.machine_of_war_platforms),
        "unites": [u.entity_id for u in alloc.units],
    }
    reel = {
        "joueurs": obs.joueurs,
        "tuiles": obs.tuiles,
        "plateformes": obs.plateformes,
        "unites": [u.entity_id for u in deployees],
    }
    familles = {k: (prevu[k] == reel[k]) for k in prevu}
    return {"regle": regle, "board_tuiles": width * height, "prevu": prevu, "reel": reel,
            "familles": familles, "exact": all(familles.values()),
            "derniers_ids_derives": sum(len(v) for v in prevu.values())
                                    + sum(len(u.foot_entity_ids) for u in alloc.units),
            "match": match, "alloc": alloc}


def etage_a2_ancre(a1: dict, obs: FluxObs) -> dict:
    """(A2) L'ANCRE : le premier identifiant que le DEROULE consomme.

    Elle est DERIVEE -- c'est `match.last_id + 1` a la sortie du deploiement -- et confrontee au
    plus petit identifiant observe apres le deploiement. Ce plus petit est pris sur l'UNION des
    effets et des unites du deroule : le restreindre aux effets supposerait qu'aucun summon ne
    precede, ce que rien ne garantit."""
    match: MatchComponent = a1["match"]
    prevue = match.last_id + 1
    apres = [u.entity_id for u in obs.unites if not u.dans_le_deploiement]
    apres += obs.effets_ordre_apparition
    if not apres:
        raise MesureImpossible("aucune entite allouee apres le deploiement -- l'ancre n'a rien "
                               "a mordre, le scenario ne mesure pas ce qu'il pretend")
    observee = min(apres)
    return {"prevue": prevue, "observee": observee, "exact": prevue == observee,
            "entites_apres_deploiement": len(set(apres))}


def etage_a3_densite(a2: dict, obs: FluxObs) -> dict:
    """(A3) DENSITE : dans l'intervalle `[ancre, max observe]`, tout identifiant absent doit
    s'expliquer.

    Deux explications, et une seule est mecanique :
      * le PIED d'une unite du deroule -- `add_unit` consomme `1 + pieds`, et un pied n'est
        JAMAIS nomme par une ligne du flux (le tag `Unit_Foot_Tile_Id_*` porte l'id de TUILE) ;
      * une entite allouee sans jamais produire de ligne. Celle-la n'est pas explicable depuis
        le flux : c'est ce que l'etage (A6) va NOMMER par introspection."""
    ancre = a2["prevue"]
    effets = set(obs.effets_ordre_apparition)
    summons = [u for u in obs.unites if not u.dans_le_deploiement]
    pieds_implicites = set()
    for u in summons:
        pieds_implicites |= {u.entity_id + 1 + i for i in range(u.foot_count)}
    vus = effets | {u.entity_id for u in summons} | pieds_implicites
    borne = max(vus) if vus else ancre
    manquants = [i for i in range(ancre, borne + 1) if i not in vus]
    return {"ancre": ancre, "borne": borne, "vus": len(vus),
            "pieds_implicites": sorted(pieds_implicites),
            "manquants": manquants, "dense": not manquants}


def etage_a4_monotonie(obs: FluxObs, bloc1: List[int]) -> dict:
    """(A4) L'ordre d'APPARITION est-il l'ordre d'ALLOCATION ?

    Mesure en INVERSIONS : un identifiant qui apparait pour la premiere fois alors qu'un
    identifiant PLUS GRAND est deja apparu. Zero inversion ne prouve pas l'egalite des deux
    ordres, mais UNE SEULE la refute -- et c'est cette asymetrie qui fait de ce compte une
    mesure et non une illustration."""
    def _inv(suite: Sequence[int]) -> List[Tuple[int, int]]:
        out, plafond = [], None
        for v in suite:
            if plafond is not None and v < plafond:
                out.append((plafond, v))
            plafond = max(plafond, v) if plafond is not None else v
        return out

    return {"inversions_flux": _inv(obs.effets_ordre_apparition),
            "inversions_bloc1": _inv(bloc1),
            "n_flux": len(obs.effets_ordre_apparition), "n_bloc1": len(bloc1)}


def _rejouer_deroule(depart: int, evenements: Sequence[Evenement],
                     invisibles: Sequence[int] = ()) -> List[int]:
    """L'ALLOCATEUR, poursuivi SUR LE DEROULE. Il ne recoit que le TYPE de chaque evenement et,
    pour une unite, son nombre de pieds -- jamais un identifiant.

    `invisibles` est la liste des identifiants alloues par une creation que le flux N'ECRIT PAS.
    La passer, c'est mesurer la SUFFISANCE de la regle : si tout tombe juste des lors qu'on
    connait ces creations-la, alors il ne manque QUE leur liste, et rien d'autre."""
    match = MatchComponent()
    match.last_id = depart - 1
    attendus = set(int(i) for i in invisibles)
    rendus: List[int] = []
    for ev in evenements:
        while match.last_id + 1 in attendus:
            add_effect(match)                       # la creation MUETTE consomme son id
        if ev.kind == "unit":
            rendus.append(add_unit(match, ev.foot_count).entity_id)
        else:
            rendus.append(add_effect(match))
    return rendus


def sequence_de_creation(obs: FluxObs, muettes: Sequence[int]) -> List[Evenement]:
    """L'ORDRE DE CREATION, deduit du DECOMPILE et non du flux.

    `MatchComponent$$NextId` est un compteur STRICTEMENT croissant sans recyclage : l'ordre
    croissant des identifiants EST donc l'ordre d'appel. Ce n'est pas une observation du flux --
    c'est la consequence directe de la fonction native, et c'est ce qui rend cette suite
    constructible sans lire l'ordre d'apparition.

    ⚠ CE N'EST PAS CIRCULAIRE, et la difference se voit sur ce que la passe TESTE : recevoir la
    suite des creations DANS L'ORDRE ne donne pas les identifiants -- il reste a savoir combien
    d'unites en consomment `1 + pieds`, ou se rangent les creations MUETTES, et que rien n'est
    jamais rendu. Les mutations `unite-sans-pieds`, `effet-avec-pied` et `effet-recycle` font
    toutes tomber cette passe."""
    par_id = {ev.entity_id: ev for ev in obs.evenements}
    for eid in muettes:
        par_id.setdefault(int(eid), Evenement(kind="effect", foot_count=0, entity_id=int(eid),
                                              racine="(creation muette)"))
    return [par_id[k] for k in sorted(par_id)]


def etage_a5_allocateur_sequentiel(a2: dict, obs: FluxObs, muettes: Sequence[int]) -> dict:
    """(A5) L'ALLOCATEUR POURSUIVI SUR LE DEROULE -- la mesure qui repond a la question binaire.

    Deux passes, et c'est leur ECART qui est le resultat :

      * par l'ORDRE D'APPARITION : exactement ce que produirait un emetteur alimente par l'ordre
        des sous-arbres du flux (borne (c) de `#477-r21`), sans rien de plus. Il ne couterait
        aucune entree nouvelle -- d'ou l'interet de le CHIFFRER plutot que de le supposer ;
      * par l'ORDRE DE CREATION : le meme allocateur, alimente par la suite que la SELECTION
        (`#477-r21-r2`) produira -- l'ordre des appels a `AddEffectOperation`, creations MUETTES
        comprises. S'il tombe juste, la REGLE est complete et il ne manque QUE cette suite.
        C'est un test de SUFFISANCE : sans lui, « ca ne marche pas » ne dirait pas POURQUOI."""
    depart = a2["prevue"]
    reels = [ev.entity_id for ev in obs.evenements]
    par_apparition = _rejouer_deroule(depart, obs.evenements)
    creations = sequence_de_creation(obs, muettes)
    attendus_creation = [ev.entity_id for ev in creations]
    par_creation = _rejouer_deroule(depart, creations)
    justes_app = sum(1 for p, r in zip(par_apparition, reels) if p == r)
    justes_cre = sum(1 for p, r in zip(par_creation, attendus_creation) if p == r)
    ecart_app = next((i for i, (p, r) in enumerate(zip(par_apparition, reels)) if p != r), None)
    ecart_cre = next((i for i, (p, r) in enumerate(zip(par_creation, attendus_creation))
                      if p != r), None)
    return {"total_apparition": len(reels), "total_creation": len(attendus_creation),
            "justes_apparition": justes_app, "justes_creation": justes_cre,
            "premier_ecart_apparition": ecart_app, "premier_ecart_creation": ecart_cre,
            "par_apparition": par_apparition, "par_creation": par_creation,
            "reels": reels, "attendus_creation": attendus_creation,
            "suffisant": justes_cre == len(attendus_creation) and bool(attendus_creation),
            "autonome": justes_app == len(reels) and bool(reels)}


def etage_a6_nature_des_invisibles(session: int, runner_id: int,
                                   manquants: Sequence[int]) -> dict:
    """(A6) QUE SONT les allocations invisibles ? -- introspection, pas deduction.

    `dumpEntityComponents` parcourt les entites VIVANTES du runner : il rend le `type`
    (`IdunBattle.Entities.Enum.EntityType`) de l'entite portant cet id, ou une absence.

    ⚠ LE DUMP EST PRIS APRES LE DEROULE : une entite DETRUITE entre-temps n'y est plus, et
    `ABSENTE` ne prouve donc pas qu'elle n'a jamais existe. Le tri-etat est publie tel quel --
    rabattre `ABSENTE` sur « jamais allouee » ferait disparaitre le gisement qu'on mesure."""
    natures: Dict[int, str] = {}
    for eid in manquants:
        try:
            r = R15A.rpc(session, "dumpEntityComponents",
                         {"runnerId": runner_id, "entityId": int(eid), "withFields": False})
        except MesureImpossible:
            natures[int(eid)] = "NON MESURE"
            continue
        if not r or not r.get("ok"):
            natures[int(eid)] = "ABSENTE"
            continue
        ty = r.get("type")
        try:
            natures[int(eid)] = EntityType(int(ty)).name
        except (TypeError, ValueError):
            natures[int(eid)] = "type=%r" % (ty,)
    return {"natures": natures}


# ---------------------------------------------------------------- contre-epreuves du PORT (pures)

class _PostIncrement(MatchComponent):
    """MUTATION : `NextId` POST-incremente. Le decompile PRE-incremente -- ce mutant decale
    TOUT le flux de 1, y compris l'id 2 qui n'est jamais attribue."""

    def next_id(self) -> int:
        v = self.last_id
        self.last_id += 1
        return v


def _rejouer_allocation(mutation: str, *, player_count: int, environment_ability_count: int,
                        tile_count: int, unit_foot_counts: Sequence[int],
                        evenements: Sequence[Evenement],
                        invisibles: Sequence[int]) -> Tuple[List[int], List[int]]:
    """Rejoue le DEPLOIEMENT PUIS le DEROULE, sous une MUTATION du port.

    Chaque mutation vise UNE lecture du decompile. Une mutation qui ne change rien ne mesure
    rien : `a_morde` est publie SEPAREMENT du verdict."""
    match = _PostIncrement() if mutation == "post-increment" else MatchComponent()
    if mutation != "sans-initialize":
        match.last_id += 1                       # `InitializeMatchOperation$$Execute`
    n_platform = 1 if mutation == "une-plateforme" else len(PLATFORM_POSITIONS)
    for _ in range(player_count):
        match.next_id()
    for _ in range(environment_ability_count):
        match.next_id()
    for _ in range(tile_count):
        match.next_id()
    for _ in range(n_platform):
        match.next_id()
    unites = []
    for foot in unit_foot_counts:
        if mutation == "unite-pas-fixe":
            # « une unite coute 2 » -- vrai sur nos rosters mono-pied, faux des qu'un pied de
            # plus existe. C'est la faute que `#477-r16-r2` garde ouverte.
            unites.append(match.next_id())
            match.next_id()
        elif mutation == "unite-sans-pieds":
            unites.append(match.next_id())
        else:
            unites.append(add_unit(match, foot).entity_id)
    attendus = set(int(i) for i in invisibles)
    deroule: List[int] = []
    for ev in evenements:
        while match.last_id + 1 in attendus:
            add_effect(match)
        if ev.kind == "unit":
            if mutation == "unite-sans-pieds":
                deroule.append(match.next_id())
            elif mutation == "unite-pas-fixe":
                deroule.append(match.next_id())
                match.next_id()
            else:
                deroule.append(add_unit(match, ev.foot_count).entity_id)
        elif mutation == "effet-avec-pied":
            deroule.append(add_unit(match, 1).entity_id)
        elif mutation == "effet-recycle":
            # « un effet retire rend son id » -- `ReturnLastId` n'a AUCUN site sur ce chemin.
            e = add_effect(match)
            match.return_last_id()
            deroule.append(e)
        else:
            deroule.append(add_effect(match))
    return unites, deroule


MUTATIONS = ("post-increment", "sans-initialize", "une-plateforme", "unite-pas-fixe",
             "unite-sans-pieds", "effet-avec-pied", "effet-recycle")


def inerte_par_construction(mutation: str, foot_counts: Sequence[int]) -> str:
    """Pourquoi une mutation NE PEUT PAS mordre sur CE corpus -- ou chaine vide si elle le peut.

    ⚠ UNE MUTATION INERTE NE MESURE RIEN, ET C'EST LE MODE DE PANNE QUI A COUTE QUATRE TRANCHES
    A CE DEPOT. La parade n'est pas de la retirer en silence : c'est de dire ce que le corpus ne
    lui donne pas a mordre, pour que le jour ou il le donne, elle redevienne un cran."""
    if mutation == "unite-pas-fixe" and all(int(f) == 1 for f in foot_counts):
        return ("toutes les unites du corpus sont MONO-PIED : `1 + pieds` et `2` y sont la "
                "meme valeur. La boucle multi-pieds reste LUE et non confrontee -- `#477-r16-r2`")
    return ""


def contre_epreuves(a1: dict, obs: FluxObs, creations: Sequence[Evenement]) -> List[dict]:
    """Chaque mutation DOIT changer la sortie du port (`a_morde`) ET faire tomber le verdict.

    LE VERDICT EST CELUI DES ETAGES CONFRONTES, pas un critere invente ici : les identifiants du
    deploiement (A1) et la suite par ORDRE DE CREATION (A5, la seule passe qui tombe juste sur
    le port non mute). Une mutation est ROUGE des que l'une des deux cesse de coller au flux."""
    regle = a1["regle"]
    deployees = [u for u in obs.unites if u.dans_le_deploiement]
    foot_counts = [u.foot_count for u in deployees]
    kw = dict(player_count=len(obs.joueurs), environment_ability_count=regle["E_lu"],
              tile_count=a1["board_tuiles"], unit_foot_counts=foot_counts,
              evenements=creations, invisibles=())
    ref = _rejouer_allocation("", **kw)
    reels_setup = [u.entity_id for u in deployees]
    reels_deroule = [ev.entity_id for ev in creations]
    lignes = []
    for nom in MUTATIONS:
        mu, md = _rejouer_allocation(nom, **kw)
        a_morde = (mu, md) != ref
        lignes.append({"mutation": nom, "a_morde": a_morde,
                       "verdict_rouge": (mu != reels_setup) or (md != reels_deroule),
                       "inerte_par_construction": inerte_par_construction(nom, foot_counts)})
    return lignes


# ------------------------------------------------------------------------------------- scenario

def scenario(session: int, board: str, tours: int, p_units: str, a_units: str,
             etiquette: str) -> dict:
    state = OUT / ("state-477r21r3-%s.json" % etiquette)
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = R19.build(board, state, p_units, a_units)
    try:
        joues = 0
        for _ in range(tours):
            q = subprocess.run([sys.executable, "rl_duel.py", "aiturn", "--state-file", str(state)],
                               cwd=str(HERE), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900)
            if q.returncode != 0:
                break
            joues += 1
        flux = (R15A.rpc(session, "replayOutputStream",
                         {"runnerId": rid, "maxChars": 8000000}).get("outputStream") or "")
        if not flux:
            raise MesureImpossible("`replayOutputStream` rend un flux VIDE")
        obs = observer(flux)
        obs.effets_bloc1 = effets_du_bloc1(flux)
        a1 = etage_a1_deploiement(obs, board)
        a2 = etage_a2_ancre(a1, obs)
        a3 = etage_a3_densite(a2, obs)
        a6 = etage_a6_nature_des_invisibles(session, rid, a3["manquants"])
    finally:
        R15A.dispose(state)
    a4 = etage_a4_monotonie(obs, obs.effets_bloc1)
    a5 = etage_a5_allocateur_sequentiel(a2, obs, a3["manquants"])
    ce = contre_epreuves(a1, obs, sequence_de_creation(obs, a3["manquants"]))
    with open(OUT / ("477r21r3-%s-flux.txt" % etiquette), "w",
              encoding="utf-8", newline="") as f:
        f.write(flux)
    return {"etiquette": etiquette, "board": board, "tours": joues, "obs": obs,
            "a1": a1, "a2": a2, "a3": a3, "a4": a4, "a5": a5, "a6": a6, "contre_epreuve": ce}


def imprimer(res: dict) -> None:
    obs, a1, a2, a3, a4, a5, a6 = (res["obs"], res["a1"], res["a2"], res["a3"], res["a4"],
                                   res["a5"], res["a6"])
    deployees = [u for u in obs.unites if u.dans_le_deploiement]
    summons = [u for u in obs.unites if not u.dans_le_deploiement]
    print("  flux : %d lignes, %d tour(s) d'IA joue(s)" % (obs.lignes, res["tours"]))
    print("  ENTREES (borne (c)) : %d joueur(s), %d tuile(s) de board, %d unite(s) deployee(s) "
          "(pieds=%s), %d summon(s), %d effet(s) apparu(s)"
          % (len(obs.joueurs), a1["board_tuiles"], len(deployees),
             ",".join(str(u.foot_count) for u in deployees[:4])
             + ("..." if len(deployees) > 4 else ""),
             len(summons), len(obs.effets_ordre_apparition)))
    print("  (A1) DEPLOIEMENT derive : %d identifiant(s) produits sans en lire aucun -- %s"
          % (a1["derniers_ids_derives"], "EXACT" if a1["exact"] else "ROUGE"))
    for fam, ok in a1["familles"].items():
        if not ok:
            print("        %-12s prevu=%s" % (fam, a1["prevu"][fam][:8]))
            print("        %-12s reel =%s" % ("", a1["reel"][fam][:8]))
    print("      E = %d (BC %d + derived %d + en dur %d + traits %d + syncpvp %d), "
          "1re tuile prevue %d" % (a1["regle"]["E_lu"], a1["regle"]["E_bc"],
                                   a1["regle"]["E_derived"], a1["regle"]["E_en_dur"],
                                   a1["regle"]["E_damage_traits"], a1["regle"]["E_syncpvp"],
                                   a1["regle"]["premier_id_tuile_prevu"]))
    print("  (A2) ANCRE du deroule : prevue=%d  observee=%d -- %s  (%d entite(s) apres le "
          "deploiement)" % (a2["prevue"], a2["observee"], "EXACT" if a2["exact"] else "ROUGE",
                            a2["entites_apres_deploiement"]))
    print("  (A3) DENSITE sur [%d..%d] : %d entite(s) vue(s) ou deduite(s), %d manquant(s) %s"
          % (a3["ancre"], a3["borne"], a3["vus"], len(a3["manquants"]),
             a3["manquants"] if len(a3["manquants"]) <= 20 else a3["manquants"][:20]))
    if a6["natures"]:
        groupes: Dict[str, List[int]] = {}
        for eid, nat in sorted(a6["natures"].items()):
            groupes.setdefault(nat, []).append(eid)
        for nat in sorted(groupes):
            print("        nature des manquants : %-10s x%d  %s"
                  % (nat, len(groupes[nat]), groupes[nat][:12]))
    print("  (A4) MONOTONIE : %d inversion(s) sur %d apparition(s) du flux entier ; "
          "%d sur %d dans le BLOC 1"
          % (len(a4["inversions_flux"]), a4["n_flux"], len(a4["inversions_bloc1"]),
             a4["n_bloc1"]))
    if a4["inversions_flux"]:
        print("        (plafond, arrivant) : %s" % (a4["inversions_flux"][:6],))
    print("  (A5) ALLOCATEUR POURSUIVI SUR LE DEROULE (%d unite(s) + %d effet(s) visibles) :"
          % (sum(1 for e in obs.evenements if e.kind == "unit"),
             sum(1 for e in obs.evenements if e.kind == "effect")))
    print("      par l'ORDRE D'APPARITION : %d/%d juste(s)%s -- %s"
          % (a5["justes_apparition"], a5["total_apparition"],
             "" if a5["premier_ecart_apparition"] is None
             else ", decroche au rang %d (prevu %d, reel %d)"
                  % (a5["premier_ecart_apparition"],
                     a5["par_apparition"][a5["premier_ecart_apparition"]],
                     a5["reels"][a5["premier_ecart_apparition"]]),
             "AUTONOME" if a5["autonome"] else "NON AUTONOME"))
    print("      par l'ORDRE DE CREATION  : %d/%d juste(s)%s -- %s"
          % (a5["justes_creation"], a5["total_creation"],
             "" if a5["premier_ecart_creation"] is None
             else ", decroche au rang %d (prevu %d, attendu %d)"
                  % (a5["premier_ecart_creation"],
                     a5["par_creation"][a5["premier_ecart_creation"]],
                     a5["attendus_creation"][a5["premier_ecart_creation"]]),
             "REGLE SUFFISANTE" if a5["suffisant"] else "REGLE INCOMPLETE"))
    print("  CONTRE-EPREUVE (%d mutations du PORT, chacune doit MORDRE puis rougir) :"
          % len(MUTATIONS))
    for l in res["contre_epreuve"]:
        attendu_inerte = bool(l["inerte_par_construction"])
        etat = ("NON EXERCEE" if attendu_inerte and not l["a_morde"]
                else "OK" if (l["a_morde"] and l["verdict_rouge"]) else "ROUGE")
        print("      %-18s a_morde=%-5s verdict_rouge=%-5s %s"
              % (l["mutation"], l["a_morde"], l["verdict_rouge"], etat))
        if attendu_inerte and not l["a_morde"]:
            print("          NON EXERCEE sur ce corpus : %s" % l["inerte_par_construction"])
        elif not l["a_morde"]:
            print("          ! la mutation n'a PAS change ce qu'elle mute -- elle ne mesure "
                  "rien, quel que soit son verdict.")


# ------------------------------------------------------------------- auto-test des GARDES (offline)

def auto_test_gardes() -> Tuple[bool, List[str]]:
    """Chaque cran doit avoir ete VU ROUGE. Les verdicts sont des fonctions PURES : ce mode les
    exerce sur une mesure FABRIQUEE conforme, puis MUTEE une chose a la fois."""
    lignes: List[str] = []
    ok = True

    # 1. le compteur lui-meme
    m = MatchComponent()
    if m.last_id != 1:
        ok = False
        lignes.append("ROUGE : `MatchComponent$$.ctor` doit poser 1, pas %d" % m.last_id)
    m.last_id += 1                                     # InitializeMatch
    premier = m.next_id()
    lignes.append("compteur : `.ctor`=1, `InitializeMatch`, 1er `NextId` -> %d %s"
                  % (premier, "OK" if premier == 3 else "ROUGE"))
    ok = ok and premier == 3

    # 2. l'id 2 n'est jamais attribue
    m2 = MatchComponent()
    m2.last_id += 1
    rendus = [m2.next_id() for _ in range(4)]
    ok2 = 2 not in rendus
    lignes.append("l'id 2 n'est JAMAIS attribue : %s %s" % (rendus, "OK" if ok2 else "ROUGE"))
    ok = ok and ok2

    # 3. les mutations doivent MORDRE -- sur un corpus qui leur DONNE de quoi mordre. Le roster
    #    porte donc une unite BI-PIED : sur du mono-pied, `unite-pas-fixe` ne peut pas mordre,
    #    et un auto-test qui l'ignorerait declarerait vert un cran non exerce.
    evenements = [Evenement(kind="unit", foot_count=1, entity_id=0, racine="User_PlaceUnit"),
                  Evenement(kind="effect", foot_count=0, entity_id=0, racine="System_StartMatch"),
                  Evenement(kind="effect", foot_count=0, entity_id=0, racine="System_StartMatch")]
    kw = dict(player_count=3, environment_ability_count=6, tile_count=35,
              unit_foot_counts=[1] * 9 + [2], evenements=evenements, invisibles=())
    ref = _rejouer_allocation("", **kw)
    inertes = [nom for nom in MUTATIONS if _rejouer_allocation(nom, **kw) == ref]
    lignes.append("mutations INERTES (roster 9 mono-pied + 1 BI-PIED) : %s %s"
                  % (inertes or "aucune", "ROUGE" if inertes else "OK"))
    ok = ok and not inertes

    # 3bis. et le probe doit SAVOIR DIRE pourquoi elle ne mord pas sur du mono-pied -- sans quoi
    #       « NON EXERCEE » et « cran casse » deviennent indiscernables.
    kw_mono = dict(kw, unit_foot_counts=[1] * 10)
    mono_inerte = _rejouer_allocation("unite-pas-fixe", **kw_mono) == _rejouer_allocation(
        "", **kw_mono)
    dit = bool(inerte_par_construction("unite-pas-fixe", [1] * 10))
    ne_dit_pas = not inerte_par_construction("unite-pas-fixe", [1] * 9 + [2])
    ok3b = mono_inerte and dit and ne_dit_pas
    lignes.append("`unite-pas-fixe` sur du MONO-PIED : inerte=%s, declaree=%s, et NON declaree "
                  "sur du bi-pied=%s %s" % (mono_inerte, dit, ne_dit_pas,
                                            "OK" if ok3b else "ROUGE"))
    ok = ok and ok3b

    # 4. le temoin reproduit les DEUX chiffres publies par #477-r16 sur `C1_02` : 1re tuile 12
    #    (`3 + P + E`) et 1re unite 49 (`1re tuile + T + 2`). Le roster est celui de la mesure
    #    #477-r16 -- DIX unites deployees. Un flux reel en met cinq dans `System_GameSetup` et
    #    cinq dans `User_PlaceUnit` : le total est le meme, la SEPARATION ne l'est pas, et c'est
    #    (A1)/(A2) qui la confrontent. Ce cran-ci ne teste que la REGLE.
    _match, alloc = new_match_after_setup(player_count=3, environment_ability_count=6,
                                          tile_count=35, machine_of_war_platform_count=2,
                                          unit_foot_counts=[1] * 10)
    attendu = (12, 49, 69)
    obtenu = (alloc.first_tile_entity_id, alloc.first_unit_entity_id, _match.last_id + 1)
    lignes.append("temoin #477-r16 (regle, 10 unites) : (1re tuile, 1re unite, id suivant) = %s %s"
                  % (obtenu, "OK" if obtenu == attendu else "ROUGE, attendu %s" % (attendu,)))
    ok = ok and obtenu == attendu

    # 5. le ROLLBACK n'existe QUE sur la tuile
    from engine.streams.entity_allocator import add_tile
    m3 = MatchComponent()
    avant = m3.last_id
    rendu = add_tile(m3, factory_returned_entity=False)
    ok5 = rendu is None and m3.last_id == avant
    lignes.append("rollback TUILE : id rendu=%r, compteur %d -> %d %s"
                  % (rendu, avant, m3.last_id, "OK" if ok5 else "ROUGE"))
    ok = ok and ok5

    # 6. l'etage (A5) doit savoir REFUTER, ET distinguer ses deux passes. Corpus fabrique :
    #    une creation MUETTE (71) et une INVERSION (70 apparait apres 72).
    evs = [Evenement(kind="effect", foot_count=0, entity_id=69, racine=""),
           Evenement(kind="effect", foot_count=0, entity_id=72, racine=""),
           Evenement(kind="effect", foot_count=0, entity_id=70, racine=""),
           Evenement(kind="unit", foot_count=1, entity_id=73, racine="")]
    faux_obs = FluxObs(joueurs=[], tuiles=[], plateformes=[], unites=[],
                       effets_ordre_apparition=[], effets_bloc1=[], evenements=evs, lignes=0)
    a5 = etage_a5_allocateur_sequentiel({"prevue": 69}, faux_obs, [71])
    ok6 = (not a5["autonome"]) and a5["suffisant"] and a5["justes_apparition"] == 1 \
        and a5["total_creation"] == 5
    lignes.append("(A5) discrimine : APPARITION=%d/%d (autonome=%s), CREATION=%d/%d "
                  "(suffisant=%s) %s"
                  % (a5["justes_apparition"], a5["total_apparition"], a5["autonome"],
                     a5["justes_creation"], a5["total_creation"], a5["suffisant"],
                     "OK" if ok6 else "ROUGE"))
    ok = ok and ok6

    # 6bis. et il ne doit PAS declarer suffisante une regle qui ne l'est pas : sans la creation
    #       muette, la 2e passe decroche a l'endroit meme du trou.
    a5b = etage_a5_allocateur_sequentiel({"prevue": 69}, faux_obs, [])
    ok6b = (not a5b["suffisant"]) and a5b["premier_ecart_creation"] == 2
    lignes.append("(A5) sans la creation muette : suffisant=%s, decroche au rang %s (attendu 2) %s"
                  % (a5b["suffisant"], a5b["premier_ecart_creation"],
                     "OK" if ok6b else "ROUGE"))
    ok = ok and ok6b

    # 7. l'etage (A4) doit compter les inversions, et une suite croissante doit en rendre ZERO
    temoin = FluxObs(joueurs=[], tuiles=[], plateformes=[], unites=[],
                     effets_ordre_apparition=[69, 70, 72, 71], effets_bloc1=[], evenements=[],
                     lignes=0)
    inv = etage_a4_monotonie(temoin, [69, 70, 72])
    ok7 = len(inv["inversions_flux"]) == 1 and len(inv["inversions_bloc1"]) == 0
    lignes.append("(A4) inversions : flux=%d (attendu 1), bloc1=%d (attendu 0) %s"
                  % (len(inv["inversions_flux"]), len(inv["inversions_bloc1"]),
                     "OK" if ok7 else "ROUGE"))
    ok = ok and ok7
    return ok, lignes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--boards", default=",".join(BOARDS_DEFAUT))
    ap.add_argument("--tours", type=int, default=2)
    ap.add_argument("--sans-roster-crafte", action="store_true")
    ap.add_argument("--auto-test-gardes", action="store_true")
    args = ap.parse_args()

    if args.auto_test_gardes:
        ok, lignes = auto_test_gardes()
        print("[477-r21-r3] AUTO-TEST DES GARDES (offline)")
        for l in lignes:
            print("  " + l)
        print("  -> %s" % ("TOUS LES CRANS ONT MORDU" if ok else "AU MOINS UN CRAN EST INERTE"))
        return 0 if ok else 1

    try:
        session = args.session if args.session is not None else R15A.session_courante()
    except MesureImpossible as e:
        print("[477-r21-r3] MESURE IMPOSSIBLE : %s" % e)
        return 2

    plans = [(b.strip(), "", "", b.strip()) for b in args.boards.split(",") if b.strip()]
    if not args.sans_roster_crafte:
        plans.append((ROSTER_CRAFTE[0], ROSTER_CRAFTE[1], ROSTER_CRAFTE[2],
                      "%s-2v2" % ROSTER_CRAFTE[0]))
    print("[477-r21-r3] session=%d  scenarios=%s  tours=%d"
          % (session, ",".join(p[3] for p in plans), args.tours))

    resultats = []
    for board, pu, au, etiquette in plans:
        print("")
        print("=== SCENARIO %s (board %s%s) ==="
              % (etiquette, board, ", roster crafte" if pu or au else ""))
        try:
            res = scenario(session, board, args.tours, pu, au, etiquette)
        except MesureImpossible as e:
            print("  MESURE IMPOSSIBLE : %s" % e)
            return 2
        resultats.append(res)
        imprimer(res)

    print("")
    print("=== VERDICT (corpus = %d scenario(s)) ===" % len(resultats))
    rc = 0
    for r in resultats:
        inertes = [l["mutation"] for l in r["contre_epreuve"]
                   if not l["a_morde"] and not l["inerte_par_construction"]]
        muettes = [l["mutation"] for l in r["contre_epreuve"]
                   if not l["verdict_rouge"] and not l["inerte_par_construction"]]
        etat_ok = (r["a1"]["exact"] and r["a2"]["exact"] and r["a5"]["suffisant"]
                   and not inertes and not muettes)
        print("  %-14s (A1) deploiement=%-5s (A2) ancre=%-5s (A3) muettes=%-3d "
              "(A4) inv. bloc1=%-2d (A5) apparition=%d/%d creation=%d/%d"
              % (r["etiquette"], r["a1"]["exact"], r["a2"]["exact"], len(r["a3"]["manquants"]),
                 len(r["a4"]["inversions_bloc1"]), r["a5"]["justes_apparition"],
                 r["a5"]["total_apparition"], r["a5"]["justes_creation"],
                 r["a5"]["total_creation"]))
        if not etat_ok:
            rc = 1
    print("")
    print("  DERIVE : les identifiants du DEPLOIEMENT (A1), l'ANCRE du deroule (A2), et TOUTE la")
    print("  suite du deroule des lors que la SEQUENCE DE CREATION est connue (A5, 2e passe).")
    print("  NON DERIVE : cette sequence elle-meme. Le flux ne l'ecrit pas -- il n'ordonne que")
    print("  les APPARITIONS, qui en different (A4), et il TAIT des creations entieres (A3),")
    print("  nommees `Effect` par introspection ECS (A6). Il y faut la SELECTION")
    print("  (`#477-r21-r2`) : elle seule sait quels `AddEffectOperation` ont ete appeles.")
    print("  `AUTONOMES` reste donc la valeur que (A5) par APPARITION mesure, jamais une valeur")
    print("  deduite de cette livraison.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
