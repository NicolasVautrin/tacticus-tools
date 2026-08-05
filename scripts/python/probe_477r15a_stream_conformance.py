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
  `UnitStats_Range`                 <- `combatSnapshot.stats.range` (#477-r15-r4) =
                                       `GetStat(unit, StatType.Range, StatPart.Current)`, dont
                                       `StatComponent$$GetStatPart` case 0 EST
                                       `get_CurrentValue` -- l'appel exact du tag ;
  `UnitStats_MaxMembers`            <- `combatSnapshot.numberOfMembersMax` (#477-r15-r5) =
                                       `StatPart.Maximum`, dont
                                       `FillUpStatComponent$$GetStatPart` case 2 EST
                                       `get_CurrentMaximumValue()` ;
  abilities de `ChangeAbility`      <- `unitAbilityStates`, qui lit les DEUX collections
                                       natives DANS LEUR ORDRE (`ActiveAbilityComponent
                                       .Abilities@0x20`, `TriggeredAbilityComponent
                                       .Abilities@0x18`) -- le meme ordre qu'itere
                                       `AddUnitOperation$$Execute` ;
  etat castable de chaque active    <- `unitAbilityStates.actives[].state` (#477-r15-r6),
                                       `readAbilityState` sur L'INSTANCE de la meme boucle.
                                       Ce canal-la n'a rien a apparier et ne filtre rien : il
                                       couvre l'entree d'ATTAQUE NORMALE, que
                                       `ActiveAbilityComponent$$GetActives` -- donc
                                       `decisionView` -- laisse tomber. `decisionView` reste
                                       branche en RECOUPEMENT (voir
                                       `recouper_avec_decision_view`).

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


def _champ_unite(u_cs: dict, nom: str) -> int:
    """Un champ de NIVEAU UNITE de `combatSnapshot` (hors du dict `stats`), en tri-etat.

    `null` = PAS MESURE (le capteur n'a pas resolu), jamais rabattu sur une valeur : c'est
    exactement le regime ou le port se remettrait a copier l'oracle sans le dire."""
    if u_cs.get(nom) is None:
        raise MesureImpossible(
            "combatSnapshot ne publie pas `%s` de l'unite %s -- capteur #477-r15-r5 absent "
            "(bundle anterieur a la fenetre de reinject ?)" % (nom, u_cs.get("entityId")))
    return int(u_cs[nom])


def etat_complet(u_cs: dict, u_obs: dict, u_ua: dict) -> UnitFullState:
    """Le substrat de `GetFullStateUpdateTags(unit)`, assemble depuis TROIS canaux ECS.

    #477-r15-r4 et -r5 -- LES DEUX GRANDEURS QUI ETAIENT COPIEES SONT DESORMAIS LUES, et chaque
    canal est le mirror 1:1 de l'accesseur natif, verifie au decompile :

      * `UnitStats_Range` <- `stats.range` = `GetStat(unit, StatType.Range, StatPart.Current)`.
        Le `case 2` d'`IdunBattle.Entities.UnitExtensions$$GetStatComponent` et la ligne du tag
        chargent le MEME pointeur de classe ; et les `case 0` / `case 2` de
        `IdunBattle.Entities.Components.StatComponent$$GetStatPart` rendent tous deux
        `get_CurrentValue(this)`, l'appel exact que fait le tag.
      * `UnitStats_MaxMembers` <- `numberOfMembersMax` = `GetStat(.., StatPart.Maximum)`, dont
        `IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart` `case 2` EST
        `get_CurrentMaximumValue()`. Son `case 0` (Current) est le champ BRUT
        `RemainingValue(+0x18)`, c'est-a-dire l'autre tag : les deux ont enfin chacun le sien.

    ⚠ AU DEPLOIEMENT LES DEUX MEMBRES COINCIDENT (aucun membre mort, aucune modification), donc
    l'egalite du flux ne DISCRIMINE toujours pas les deux tags. Ce que le changement ferme, c'est
    la COPIE ; la discrimination, elle, demande de sortir du regime -- c'est ce que mesure
    `probe_477r15r5_membres_discrimine.py`, et le present probe l'affiche a chaque run."""
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
    return UnitFullState(
        entity_type=int(EntityType.Unit),
        # `MaximumValue@0x14` brut. `get_CurrentMaximumValue()` y ajoute la modification
        # (`+0x28`) et l'override (`+0x38`) : identiques au deploiement, ou les deux sont nuls.
        # (Non couvert par cette tranche -- le pendant `healthMax` du capteur existe, mais le
        # changer sort du perimetre de #477-r15-r4/r5/r6 ; c'est dit en borne (c).)
        max_health=int(u_obs["hpMax"]), max_armor=int(u_obs["armorMax"]),
        max_members=_champ_unite(u_cs, "numberOfMembersMax"),      # StatPart.Maximum -- MESURE
        fixed_armor=_stat(u_cs, "fixedArmor"),
        # `RemainingValue@0x18` brut, lu par le projecteur (`game/match-state.ts`).
        init_remaining_health=int(u_obs["hp"]), init_remaining_armor=int(u_obs["armor"]),
        init_alive_members=_stat(u_cs, "numberOfMembers"),         # StatPart.Current -- MESURE
        attack=_stat(u_cs, "attack"),
        range=_stat(u_cs, "range"),                                # MESURE (#477-r15-r4)
        movement=_stat(u_cs, "movement"),
        block_chance=_stat(u_cs, "blockChance"), block_damage=_stat(u_cs, "blockDamage"),
        crit_chance=_stat(u_cs, "critChance"), crit_damage=_stat(u_cs, "critDamage"),
        turn_finished=int(UnitFlag.TurnFinished) in {int(f) for f in flags},
        has_death_animation_trait=int(UnitTrait.FinalJustice) in {int(t) for t in traits},
        has_death_animation_abilities=tuple(int(a) in triggered_types
                                            for a in DEATH_ANIMATION_ABILITIES))


#: Les cinq champs d'etat que la surcharge ACTIVE lit, et le nom que `readAbilityState` leur
#: donne. Ecrit ici plutot qu'en dur au site : le controle de presence et la construction
#: doivent porter sur LA MEME liste, sans quoi un champ ajoute au capteur serait consomme sans
#: etre verifie -- ou l'inverse.
CHAMPS_ETAT_ACTIVE = ("usable", "cooldown", "disabled", "ammoCost", "hasAmmo")


def abilities_unite(u_ua: dict, u_dv: dict) -> tuple:
    """Les deux collections d'ability, DANS L'ORDRE que le natif itere.

    `unitAbilityStates` lit `Abilities@0x20` / `@0x18` element par element : c'est la meme
    liste que parcourt `AddUnitOperation$$Execute`, donc l'ordre est mesure, pas suppose.

    #477-r15-r6 -- L'ETAT CASTABLE VIENT DESORMAIS DE LA MEME BOUCLE, plus de `decisionView`.
    Celui-ci enumere par `IdunBattle.Entities.Components.ActiveAbilityComponent$$GetActives`, qui
    FILTRE : la seule entree d'attaque normale en sort par `AbilityComponent.NormalAttackType`,
    SANS objet `ActiveAbility` derriere, donc sans `usable` / `cooldown` / `disabled`. Ses trois
    tags etaient posesa l'etat NEUF -- justes (le ctor
    `IdunBattle.Entities.Components.ActiveAbility$$.ctor` ecrit `CanStillBeUsed(+0x28) = 1`,
    laisse `RemainingCooldownTurns(+0x2c)` a un `Nullable` VIDE et `IsDisabled(+0x35)` a 0) mais
    NON MESURES. `actives[].state` les lit sur l'instance elle-meme, donc pour TOUTES les entrees.

    ⚠ `state.level` / `state.multiplier` sont `ActiveAbility$$get_AbilityState()` (l'OVERRIDE
    prime), c'est-a-dire ce que le natif ecrit dans les tags 24/25 ; `a["level"]` / `a["mult"]`
    sont le champ BRUT `_abilityState`. On lit les premiers : les deux coincident tant qu'aucun
    override n'existe, et prendre le brut serait une SEPTIEME copie silencieuse."""
    actives = []
    for a in (u_ua.get("actives") or []):
        st = a.get("state")
        if not isinstance(st, dict):
            raise MesureImpossible(
                "unitAbilityStates ne publie pas `actives[].state` (ability %s) -- capteur "
                "#477-r15-r6 absent (bundle anterieur a la fenetre de reinject ?)" % a.get("type"))
        manquants = [c for c in CHAMPS_ETAT_ACTIVE if c not in st]
        if manquants:
            raise MesureImpossible(
                "`actives[].state` de l'ability %s ne porte pas %s -- offsets non resolus "
                "cote capteur (lire `abilityStateLayout` de la reponse)"
                % (a.get("type"), ",".join(manquants)))
        for cle in ("level", "multiplier"):
            if st.get(cle) is None:
                raise MesureImpossible(
                    "`actives[].state.%s` est null sur l'ability %s -- `get_AbilityState()` non "
                    "resolu" % (cle, a.get("type")))
        if st.get("usable") is None or st.get("disabled") is None:
            raise MesureImpossible(
                "`actives[].state` rend `usable`/`disabled` a null sur l'ability %s (PAS MESURE)"
                % a.get("type"))
        actives.append(ActiveAbilityState(
            ability_name=int(a["type"]), level=int(st["level"]),
            variable_multiplier_percentage=int(st["multiplier"]),
            can_still_be_used=bool(st["usable"]),
            remaining_cooldown_turns=st["cooldown"],
            is_disabled=bool(st["disabled"]),
            ammo_cost=st["ammoCost"],
            has_enough_ammo=bool(st["hasAmmo"])))
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


def recouper_avec_decision_view(u_ua: dict, u_dv: dict) -> list[str]:
    """RECOUPEMENT `unitAbilityStates.actives[].state` <-> `decisionView.units[].abilities[]`.

    CE QUE CE CONTROLE TESTE, ET CE QU'IL NE TESTE PAS. Les deux canaux appellent la MEME
    fonction de lecture (`readAbilityState`) : il ne verifie donc PAS la lecture des champs. Ce
    qu'il verifie, c'est que les deux chemins de RECUPERATION designent les memes objets --
    `GetActives()` d'un cote, le walk manuel de `Abilities@0x20` (`readInstList`) de l'autre. Si
    ce walk lisait une autre collection, ou decalait d'un element, ce recoupement rougirait alors
    que le flux, lui, resterait egal tant que les valeurs se ressemblent.

    Les abilities que `decisionView` NE publie PAS (l'attaque normale) sont hors de portee du
    recoupement par construction : c'est justement ce que #477-r15-r6 vient combler. Le nombre de
    NON RECOUPEES est rendu, jamais tu."""
    etats_dv = {int(a["id"]): a for a in ((u_dv or {}).get("abilities") or [])
                if a.get("id") is not None}
    ecarts: list[str] = []
    for a in (u_ua.get("actives") or []):
        st = a.get("state") or {}
        dv = etats_dv.get(int(a["type"]))
        if dv is None:
            continue                        # non recoupee (attaque normale, typiquement)
        for cle in ("usable", "cooldown", "disabled", "ammoCost", "hasAmmo"):
            if cle in dv and cle in st and dv[cle] != st[cle]:
                ecarts.append("ability %s : %s unitAbilityStates=%r decisionView=%r"
                              % (a["type"], cle, st[cle], dv[cle]))
    return ecarts


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
    ecarts_dv: list[str] = []
    non_recoupees = 0
    actives_recoupees = 0
    membres_degeneres = 0        # unites ou courant == maximum (le regime qui ne discrimine pas)
    membres_total = 0
    for u in sorted(adverses, key=lambda x: int(x["squadId"])):
        xy = (int(u["col"]), int(u["row"]))
        sid = int(u["squadId"])
        if sid not in par_cs or sid not in par_ua:
            raise MesureImpossible("substrat de ChangeStats/ChangeAbility absent pour "
                                   "l'entite %d (combatSnapshot=%s unitAbilityStates=%s)"
                                   % (sid, sid in par_cs, sid in par_ua))
        actives, triggered = abilities_unite(par_ua[sid], par_dv.get(sid, {}))
        ecarts_dv += recouper_avec_decision_view(par_ua[sid], par_dv.get(sid, {}))
        ids_dv = {int(a["id"]) for a in ((par_dv.get(sid) or {}).get("abilities") or [])
                  if a.get("id") is not None}
        for a in (par_ua[sid].get("actives") or []):
            if int(a["type"]) in ids_dv:
                actives_recoupees += 1
            else:
                non_recoupees += 1
        etat = etat_complet(par_cs[sid], u, par_ua[sid])
        membres_total += 1
        if etat.max_members == etat.init_alive_members:
            membres_degeneres += 1
        units.append(UnitSetup(entity_id=sid,
                               owner_id=int(u["playerId"]),
                               foot_tile_ids=[entite_de_tuile[xy]],
                               full_state=etat,
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
        # ⚠ LA BORNE A RETRECI DE TROIS ENTREES, ET CHACUNE A UN REMPLACANT NOMME. Une borne qui
        # maigrit sans que rien ne soit mesure serait un mensonge : `range` vient de
        # `stats.range` (`GetStat(.., StatType.Range, StatPart.Current)`), `MaxMembers` de
        # `numberOfMembersMax` (`StatPart.Maximum`), et les trois tags d'etat de l'attaque
        # normale de `unitAbilityStates.actives[].state` (`readAbilityState` sur l'instance).
        # Les trois canaux sont cites dans l'entete de ce fichier et dans `etat_complet` /
        # `abilities_unite`, avec le symbole natif dont ils sont le mirror.
        "Tag=UnitStats_{MaxHealth,MaxArmor} -- lus au champ BRUT `MaximumValue@0x14` "
        "(`observeBattle.hpMax`/`armorMax`) la ou le natif appelle "
        "`FillUpStatComponent$$get_CurrentMaximumValue()`. Les deux coincident au deploiement "
        "PAR CONSTRUCTION (modification `+0x28` et override `+0x38` nuls), pas par chance. Le "
        "capteur `combatSnapshot.healthMax` (`StatPart.Maximum`) existe DEJA pour la sante et "
        "fermerait la moitie de cette entree ; l'armure n'a aucun canal (son composant n'est "
        "atteignable ni par `GetStatComponent` ni par `GetStat`). Hors perimetre de "
        "#477-r15-r4/r5/r6 -- non traite, donc DECLARE",
        "Tag=UnitStats_TriggeredAbility_{AmmoCost,EnoughAmmo} -- NON CONFRONTES : `AmmoCost` est "
        "null sur toute unite reguliere (les munitions ne mordent que sur les Machines of War, "
        "qui passent par `AddMachineOperation`, hors de ce groupe)",
    ))
    return {"board": board, "rapport": rap, "tuiles": len(coords),
            "unites_emises": len(units), "addunit_natifs": attendus,
            "montage_coherent": len(units) == attendus,
            "ecarts_dv": ecarts_dv, "non_recoupees": non_recoupees,
            "actives_recoupees": actives_recoupees,
            "membres_degeneres": membres_degeneres, "membres_total": membres_total,
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
        # --- #477-r15-r6 : le RECOUPEMENT des deux chemins de recuperation d'instance, et son
        # TEMOIN. Un zero ne se lit comme un accord que si on dit combien de couples il a
        # compares -- sinon c'est le zero d'un balayage qui n'a rien visite.
        print("  RECOUPEMENT unitAbilityStates.state <-> decisionView : %d ecart(s) sur %d "
              "active(s) recoupee(s) ; %d non recoupee(s) (attaque normale : `GetActives()` la "
              "filtre -- c'est le trou que ce canal comble)"
              % (len(res["ecarts_dv"]), res["actives_recoupees"], res["non_recoupees"]))
        for e in res["ecarts_dv"]:
            print("      ROUGE RECOUPEMENT : %s" % e)
        if res["actives_recoupees"] == 0:
            print("      ! TEMOIN VIDE : aucune active recoupee -- ce zero ne prouve RIEN.")
        # --- #477-r15-r5 : le REGIME. La grandeur est MESUREE (plus copiee), mais l'egalite du
        # flux ne la DISCRIMINE pas tant que courant == maximum sur toutes les unites.
        print("  REGIME MEMBRES (#477-r15-r5) : %d/%d unite(s) ou courant == maximum -- sur "
              "celles-la, `MaxMembers` et `InitAliveMembers` NE SE DISTINGUENT PAS (les deux "
              "canaux sont distincts, le regime ne les separe pas). Discrimination :"
              " probe_477r15r5_membres_discrimine.py"
              % (res["membres_degeneres"], res["membres_total"]))
        if not res["montage_coherent"]:
            # ASCII PUR, sans `.replace` de rattrapage : la console Windows est en cp1252, et
            # cette ligne ne s'imprime QUE quand le montage est incoherent -- c'est-a-dire
            # exactement quand le probe a quelque chose a dire. Un `UnicodeEncodeError` y aurait
            # fait crasher le diagnostic au seul moment ou il compte. Le `.replace` qui etait la
            # ne couvrait que le premier des trois caracteres non-ASCII de la ligne.
            print("  ! MONTAGE : le filtre \"unites adverses\" ne predit pas le nombre d'AddUnit "
                  "du groupe natif -- les divergences d'AddUnit ci-dessous accusent le MONTAGE, "
                  "pas le port.")
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
    # #477-r15-r6 : deux chemins de recuperation d'instance qui divergent designent des objets
    # DIFFERENTS -- le flux peut rester egal et le canal etre faux. C'est donc un ROUGE a part
    # entiere, pas une note de bas de page.
    recoup_ko = [r["board"] for r in resultats if r["ecarts_dv"]]
    if recoup_ko:
        print("  ROUGE : `GetActives()` et le walk de `Abilities@0x20` ne s'accordent pas sur %s."
              % ",".join(recoup_ko))
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
