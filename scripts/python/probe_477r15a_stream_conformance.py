#!/usr/bin/env python3
"""#477-r15 tranches D + E -- LE CLIQUET A TROIS ETATS du flux de replay, confronte en live.

    python probe_477r15a_stream_conformance.py [--session N] [--boards C1_02,MC1_67]
                                               [--p-units X,Y] [--a-units Z,W]

CE QU'IL MESURE
---------------
Le port EMET desormais un flux de replay (`engine.streams`, tranches A + B + D). Ce probe le
confronte au flux NATIF sur le seul morceau entierement atteignable : le groupe racine
`System_GameSetup` (`AddPlayer` / `AddTile` / `AddUnit` / `ChangeStats` / `ChangeAbility`), qui
ne depend d'aucune mecanique de combat portee. Le flux natif est deterministe au caractere pres
(#477-r11), donc la barre est l'egalite BRUTE, ligne a ligne.

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
  proprietaire / position d'unite   <- `observeBattle` (playerId, col, row) ;
  stats de `ChangeStats`            <- `combatSnapshot` (`GetStat` par `StatType`, `unitFlags`,
                                       `traits`) et `observeBattle` (hp/hpMax, armor/armorMax,
                                       champs bruts `RemainingValue@0x18` / `MaximumValue@0x14`
                                       du `FillUpStatComponent`) ;
  abilities de `ChangeAbility`      <- `unitAbilityStates`, qui lit les DEUX collections
                                       natives DANS LEUR ORDRE (`ActiveAbilityComponent
                                       .Abilities@0x20`, `TriggeredAbilityComponent
                                       .Abilities@0x18`) -- le meme ordre qu'itere
                                       `AddUnitOperation$$Execute` ;
  cooldown / disabled / munitions   <- `decisionView.units[].abilities[]` (`readAbilityState`),
                                       apparie par id d'ability.

⚠ AUCUN de ces canaux ne lit le flux : ils lisent l'ECS par reflexion IL2CPP. Ce qu'ils NE
discriminent PAS est publie en borne (c), jamais compte comme un accord.

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
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe_477r16_allocation_entites_ecs as R16  # noqa: E402
from engine.entities.entity_type import EntityType  # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait  # noqa: E402
from engine.entities.unit_flag import UnitFlag  # noqa: E402
from engine.streams import StreamCache, StreamDispatcher  # noqa: E402
from engine.streams import conformance as CONF  # noqa: E402
from engine.streams.game_setup import (GameSetup, PlayerSetup, TileSetup,  # noqa: E402
                                       UnitSetup, emit_game_setup)
from engine.streams.unit_extensions import (DEATH_ANIMATION_ABILITIES,  # noqa: E402
                                            ActiveAbilityState, TriggeredAbilityState,
                                            UnitFullState)

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


def build(board: str, state_file: Path, p_units: str = ROSTER_P,
          a_units: str = ROSTER_A) -> int:
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(SEED), "--board", board,
           "--p-units", p_units, "--a-units", a_units,
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


# --- Etape 2bis : le substrat de `ChangeStats` / `ChangeAbility` (tranche D) --
#
# TRI-ETAT PARTOUT. Un canal muet doit rendre `MesureImpossible`, jamais une valeur par defaut :
# une stat rabattue sur 0 produirait une divergence de VALEUR qui accuserait le port alors que
# c'est le CAPTEUR qui n'a rien dit. Meme discipline que `host_inputs.py`.

def _index(rows, cle: str) -> dict:
    return {int(r[cle]): r for r in (rows or [])
            if isinstance(r, dict) and r.get(cle) is not None}


def _stat(u_cs: dict, nom: str) -> int:
    """Une entree de `combatSnapshot.units[].stats` = `UnitExtensions$$GetStat(unit, <StatType>,
    StatPart.Current)`. C'est EXACTEMENT ce que lit `StatComponent$$get_CurrentValue`, que le
    natif appelle pour huit des seize tags."""
    stats = u_cs.get("stats")
    if not isinstance(stats, dict) or stats.get(nom) is None:
        raise MesureImpossible("combatSnapshot ne publie pas la stat `%s` de l'unite %s"
                               % (nom, u_cs.get("entityId")))
    return int(stats[nom])


def etat_complet(u_cs: dict, u_obs: dict, u_ua: dict) -> UnitFullState:
    """Le substrat de `GetFullStateUpdateTags(unit)`, assemble depuis TROIS canaux ECS.

    ⚠ DEUX GRANDEURS N'ONT AUCUN CANAL, et elles sont declarees en borne (c) -- pas maquillees :

      * `UnitStats_Range` -- `StatType.Range` (2) n'est pas dans la table `COMBAT_STAT_IDS` du
        hook, donc AUCUN RPC ne le publie. Emis a 0, valeur MESUREE sur 8 unites / 6 kits /
        2 boards, jamais lue. Residu `#477-r15-r4`.
      * `UnitStats_MaxMembers` -- le natif appelle `get_CurrentMaximumValue()` sur le composant
        de membres ; le seul canal, `stats.numberOfMembers`, est le `StatPart.Current`. Au
        deploiement aucun membre n'est mort, donc courant == maximum, mais LE CANAL NE
        DISCRIMINE PAS les deux tags. Residu `#477-r15-r5`."""
    flags = u_cs.get("unitFlags")
    traits = u_cs.get("traits")
    if flags is None or traits is None:
        raise MesureImpossible("combatSnapshot rend `unitFlags`/`traits` a null (PAS MESURE) "
                               "sur l'unite %s" % u_cs.get("entityId"))
    for cle in ("hp", "hpMax", "armor", "armorMax"):
        if u_obs.get(cle) is None:
            raise MesureImpossible("observeBattle ne publie pas `%s`" % cle)
    triggered_types = {int(t["raw"][0]) for t in (u_ua.get("triggered") or [])
                       if t.get("raw")}
    membres = _stat(u_cs, "numberOfMembers")
    return UnitFullState(
        entity_type=int(EntityType.Unit),
        # `MaximumValue@0x14` brut. `get_CurrentMaximumValue()` y ajoute la modification
        # (`+0x28`) et l'override (`+0x38`) : identiques au deploiement, ou les deux sont nuls.
        max_health=int(u_obs["hpMax"]), max_armor=int(u_obs["armorMax"]),
        max_members=membres,                      # cf. docstring -- NON DISCRIMINE
        fixed_armor=_stat(u_cs, "fixedArmor"),
        # `RemainingValue@0x18` brut, lu par le projecteur (`game/match-state.ts`).
        init_remaining_health=int(u_obs["hp"]), init_remaining_armor=int(u_obs["armor"]),
        init_alive_members=membres,
        attack=_stat(u_cs, "attack"),
        range=0,                                  # cf. docstring -- AUCUN CANAL
        movement=_stat(u_cs, "movement"),
        block_chance=_stat(u_cs, "blockChance"), block_damage=_stat(u_cs, "blockDamage"),
        crit_chance=_stat(u_cs, "critChance"), crit_damage=_stat(u_cs, "critDamage"),
        turn_finished=int(UnitFlag.TurnFinished) in {int(f) for f in flags},
        has_death_animation_trait=int(UnitTrait.FinalJustice) in {int(t) for t in traits},
        has_death_animation_abilities=tuple(int(a) in triggered_types
                                            for a in DEATH_ANIMATION_ABILITIES))


def abilities_unite(u_ua: dict, u_dv: dict) -> tuple:
    """Les deux collections d'ability, DANS L'ORDRE que le natif itere.

    `unitAbilityStates` lit `Abilities@0x20` / `@0x18` element par element : c'est la meme
    liste que parcourt `AddUnitOperation$$Execute`, donc l'ordre est mesure, pas suppose.
    `decisionView` complete l'etat castable, apparie PAR ID d'ability.

    ⚠ L'ENTREE D'ATTAQUE NORMALE N'A PAS D'ETAT PUBLIE, et c'est en borne (c). `decisionView`
    la sort de `AbilityComponent.NormalAttackType` SANS objet `ActiveAbility` derriere (kind
    `normal`), donc sans `usable` / `cooldown` / `disabled` ; `GetActives()` la filtre. Ses
    trois tags correspondants sont donc poses a l'etat NEUF d'une ability qui vient d'etre
    fabriquee -- non mesures. Residu `#477-r15-r6`."""
    etats_dv = {int(a["id"]): a for a in ((u_dv or {}).get("abilities") or [])
                if a.get("id") is not None}
    actives = []
    for a in (u_ua.get("actives") or []):
        dv = etats_dv.get(int(a["type"]), {})
        actives.append(ActiveAbilityState(
            ability_name=int(a["type"]), level=int(a["level"]),
            variable_multiplier_percentage=int(a["mult"]),
            can_still_be_used=bool(dv.get("usable", True)),
            remaining_cooldown_turns=dv.get("cooldown"),
            is_disabled=bool(dv.get("disabled", False)),
            ammo_cost=dv.get("ammoCost"),
            has_enough_ammo=bool(dv.get("hasAmmo", True))))
    triggered = []
    for t in (u_ua.get("triggered") or []):
        if not t.get("raw"):
            raise MesureImpossible("unitAbilityStates ne publie pas le type d'une declenchee")
        # `raw[0]` = `TriggeredAbility+0x10`, le champ dont la KeyedCollection
        # `TriggeredAbilityComponent.Abilities` fait sa CLE ; `raw[4]`/`raw[5]` (+0x20/+0x24)
        # sont l'`AbilityState` que lit `TriggeredAbilityComponent$$GetAbilityState`.
        triggered.append((int(t["raw"][0]),
                          TriggeredAbilityState(level=int(t["level"]),
                                                variable_multiplier_percentage=int(t["mult"]))))
    return actives, triggered


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


def scenario(session: int, board: str, p_units: str = ROSTER_P,
             a_units: str = ROSTER_A) -> dict:
    # Le state-file porte le board ET une signature du roster : deux passes qui ne different que
    # par leurs rosters ne doivent pas se marcher dessus (discipline runner, `runner.md` §3).
    signature = "%08x" % (zlib.crc32(("%s|%s" % (p_units, a_units)).encode()) & 0xffffffff)
    state = OUT / ("state-477r15a-%s-%s.json" % (board, signature))
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = build(board, state, p_units, a_units)
    try:
        flux = (rpc(session, "replayOutputStream",
                    {"runnerId": rid, "maxChars": 8000000}).get("outputStream") or "")
        if not flux:
            raise MesureImpossible("`replayOutputStream` rend un flux VIDE")
        setup_natif = groupe_racine(flux, "System_GameSetup")
        obs = unites_observees(session, rid)
        # Tranche D : les trois canaux du substrat, captes AVANT le dispose.
        par_cs = _index(rpc(session, "combatSnapshot", {"runnerId": rid}).get("units"),
                        "entityId")
        par_ua = _index(rpc(session, "unitAbilityStates", {"runnerId": rid}).get("units"),
                        "entityId")
        par_dv = _index(rpc(session, "decisionView",
                            {"runnerId": rid, "allAbilities": True}).get("units"), "id")
    finally:
        dispose(state)

    # --- LES IDS D'ENTITE SONT DERIVES, plus copies -- ET L'OFFSET EST DESORMAIS ENTIEREMENT LU
    # (#477-r16 puis #477-r16-r1, merge le 2026-08-05). `deriver_regle()` rend `3 + P + E` depuis
    # les ENTREES versionnees seules : le dernier terme libre (`GetDerivedEnvironmentAbilities`)
    # est LU dans une table statique, plus obtenu par difference. Consequence directe pour ce
    # probe : la base de tuile n'est plus une ENTREE du natif -- c'est une PREDICTION, et le flux
    # natif la CONFRONTE. Elle sort donc de la borne (c) et entre dans les recoupements rouges.
    regle = R16.deriver_regle()
    largeur, hauteur = R16.taille_board(board)
    #  Le natif itere un `SortedDictionary`, d'ou le tri par cle.
    joueurs = [(3 + i, int(cle)) for i, cle in enumerate(regle["cles_joueurs"])]
    base_tuile = int(regle["premier_id_tuile_prevu"])
    base_natif = premiere_tuile(setup_natif)
    derived = int(regle["E_derived"])
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
        sid = int(u["squadId"])
        if sid not in par_cs or sid not in par_ua:
            raise MesureImpossible("substrat de ChangeStats/ChangeAbility absent pour "
                                   "l'entite %d (combatSnapshot=%s unitAbilityStates=%s)"
                                   % (sid, sid in par_cs, sid in par_ua))
        actives, triggered = abilities_unite(par_ua[sid], par_dv.get(sid, {}))
        units.append(UnitSetup(entity_id=sid,
                               owner_id=int(u["playerId"]),
                               foot_tile_ids=[entite_de_tuile[xy]],
                               full_state=etat_complet(par_cs[sid], u, par_ua[sid]),
                               active_abilities=actives,
                               triggered_abilities=triggered))
    setup_port = emettre(GameSetup(
        players=[PlayerSetup(ent, pid) for ent, pid in joueurs],
        tiles=[TileSetup(entite_de_tuile[xy], xy[0], xy[1]) for xy in coords],
        platform_entity_ids=plateformes_derivees,
        units=units))

    rap = CONF.comparer(setup_natif, setup_port, entrees_du_natif=(
        "Tag=Tile_IsTerritory -- aucun porteur dans le board dump, emis a 0 en dur "
        "(#477-r15-r3)",
        "Tag=UnitStats_Range -- `StatType.Range` (2) absent de `COMBAT_STAT_IDS` : AUCUN RPC ne "
        "le publie. Emis a 0, valeur observee sur tout le corpus, jamais lue (#477-r15-r4)",
        "Tag=UnitStats_MaxMembers -- pris de `stats.numberOfMembers` (`StatPart.Current`) alors "
        "que le natif appelle `get_CurrentMaximumValue()`. Le canal ne DISCRIMINE pas ce tag de "
        "`UnitStats_InitAliveMembers` (#477-r15-r5)",
        "Tag=UnitStats_ActiveAbility_{CanStillBeUsed,RemainingCooldownTurns,IsDisabled} de la "
        "SEULE entree d'attaque normale -- `decisionView` la sort de "
        "`AbilityComponent.NormalAttackType` sans objet `ActiveAbility`, donc sans etat ; "
        "posee a l'etat neuf. Mesuree pour toutes les autres actives (#477-r15-r6)",
        "Tag=UnitStats_TriggeredAbility_{AmmoCost,EnoughAmmo} -- NON CONFRONTES : `AmmoCost` est "
        "null sur toute unite reguliere (les munitions ne mordent que sur les Machines of War, "
        "qui passent par `AddMachineOperation`, hors de ce groupe)",
    ))
    return {"board": board, "rapport": rap, "tuiles": len(coords),
            "unites_emises": len(units), "addunit_natifs": attendus,
            "montage_coherent": len(units) == attendus,
            "derived": derived, "base_tuile": base_tuile, "base_natif": base_natif,
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
    # Les rosters sont PARAMETRABLES pour qu'un scenario de generalisation (plus d'unites, kits
    # varies, donc d'autres stats et d'autres abilities) se joue sans toucher au probe. Les
    # defauts sont ceux de la mesure de reference des tranches A + B + E.
    ap.add_argument("--p-units", default=ROSTER_P)
    ap.add_argument("--a-units", default=ROSTER_A)
    args = ap.parse_args()

    try:
        session = args.session if args.session is not None else session_courante()
    except MesureImpossible as e:
        print("[477-r15a] MESURE IMPOSSIBLE : %s" % e)
        return 2

    boards = [b.strip() for b in args.boards.split(",") if b.strip()]
    print("[477-r15a] session=%d  boards=%s  p=%s  a=%s"
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
        print("  tuiles du board dump = %d   unites emises = %d   `Action=AddUnit` natifs = %d"
              % (res["tuiles"], res["unites_emises"], res["addunit_natifs"]))
        print("  ALLOCATION DERIVEE (#477-r16) : 1re tuile = %d  plateformes = %s  1re unite = %d"
              % (res["base_tuile"], res["plateformes_derivees"], res["premiere_unite_derivee"]))
        # Recoupements : la regle DERIVEE contre trois canaux qui ne la connaissent pas. La base
        # de tuile en fait partie DEPUIS #477-r16-r1 : elle n'est plus prise du flux.
        if res["base_tuile"] != res["base_natif"]:
            print("  ROUGE ALLOCATION : 1re tuile prevue %d != flux natif %d"
                  % (res["base_tuile"], res["base_natif"]))
        if res["plateformes_derivees"] != res["plateformes_natives"]:
            print("  ROUGE ALLOCATION : plateformes derivees %s != flux natif %s"
                  % (res["plateformes_derivees"], res["plateformes_natives"]))
        if res["premiere_unite_observee"] != res["premiere_unite_derivee"]:
            print("  ROUGE ALLOCATION : 1re unite derivee %d != observeBattle.squadId %s"
                  % (res["premiere_unite_derivee"], res["premiere_unite_observee"]))
        print("  GetDerivedEnvironmentAbilities = %d -- LU dans la table statique depuis "
              "#477-r16-r1, plus mesure par difference" % res["derived"])
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
                if r["base_tuile"] != r["base_natif"]
                or r["plateformes_derivees"] != r["plateformes_natives"]
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
