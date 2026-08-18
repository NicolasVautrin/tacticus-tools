"""#1022 -- MESURE LIVE de la face COMBAT d'`AetherStride` (1208) : natif vs port.

CRITERE : « quand le natif execute 1208, RETIRE-T-IL la machine et POSE-T-IL une unite a 3 pieds
portant `Stationary` -- et l'arbre porte rend-il la MEME aire, le MEME summon, le MEME trait ? »

PORTEUR ET MONTAGE. Le seul porteur du build est `thousNpcMowDaemonPrince` (npc, ABSENT de
`BC.Units` du seed -- verifie). La confrontation passe donc par la GREFFE (case-92 §5bis) :
`BC.Units["ultraDreadnought"].ActiveAbilities = [1208]` dans une COPIE du seed BC. La condition de
greffe est VERIFIEE au decompile, pas supposee :
  * le natif charge le playbook PAR ABILITY (`PlaybookDatabase.LoadPlaybook(abilityType)`) ;
  * `IdunBattleLogic.Entities.Abilities.Active.Loki.AetherStrideAbility$$ExecuteBehaviour` ne lit
    du caster NI stat NI trait -- seulement `Caster@DSLSelectors+0x48` (`RemoveMachine` + owner du
    spawn) et `Owner@DSLSelectors+0x30` (predicat `ActorHasTriggeredAbility`) ;
  * le porteur de greffe `ultraDreadnought` est une MoW du POOL et le porteur natif de
    `DutyEternal` (1158), dont le `.ctor` produit un masque de ciblage IDENTIQUE OCTET POUR OCTET
    (`...AetherStrideAbility$$.ctor` et `...DutyEternalAbility$$.ctor` compares cote a cote) --
    la greffe ne deplace donc AUCUN gate.
Le summon vise, `thousSmnDaemonPrince`, est deja dans `BC.Units` du seed (verifie).

LEVIERS : `MachineOfWarAmmo` (le seed part a 0 -> aucune MoW ne caste, meme levier que probe_129) ;
1208 a `munitionsCost = 1` et `initialCooldownTurns = 1` (gameconfig).

CANAUX -- tous EXISTANTS, aucun hook neuf :
  * `decisionView.mows[]`               -> la MoW deployee, son `casterId`, l'etat de son ability ;
  * `abilityReason`                     -> `GetInvalidTargetReason` natif, tuile par tuile ;
  * `applyAction.actions[].events[]`    -> tags `Unit_Foot_Tile_Id_1..3` du spawn ;
  * `observeBattle.units[]`             -> UNE LIGNE PAR PIED (`squadId` = l'unite) ;
  * `boardGraph.tiles[].occupantUnitId` -> l'occupation native.

Usage : python probe_1022_aether_stride.py [--board MC1_67] [--seed 777]
ASCII only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

import catalog_inject as CI
import gameconfig as GC
import hexgeo
import oracle_targeting as O
from engine.entities.pathfinding.board import Board
from engine.services import spawn_tile_shape as STS
from rl_collect_batch import _load_seed_bc, _rpc, _resolve_session, bind_ambient_rpc

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
MOW = "ultraDreadnought"                 # porteur de GREFFE (MoW du pool)
AETHER_STRIDE = 1208
SUMMON = "thousSmnDaemonPrince"          # `constants.unitId` de 1208, lu au gameconfig
STATIONARY = 1048                        # `UnitTrait.Stationary` = le `0x418` d'`AddTrait`
#: Nombre de tuiles interrogees pour confronter la REGLE DYNAMIQUE. Le board entier serait 1 RPC
#: par tuile ; l'echantillon en tete d'ordre de balayage porte les DEUX verdicts, ce que le probe
#: VERIFIE au lieu de le supposer.
DYNAMIC_RULE_SAMPLE = 24


def rpc(sid, method, args, timeout=120):
    r = _rpc(sid, method, [args], timeout=timeout)
    return r.get("result", r) if isinstance(r, dict) else r


def graft_seed_bc(ammo: int = 9) -> Path:
    """LE MONTAGE, nomme et reutilisable : seed BC + munitions de MoW + greffe de 1208 sur `MOW`.

    ⚠ LA GREFFE EST **DEUX** ECRITURES, ET LA SECONDE ECHOUE EN SILENCE SI ON L'OUBLIE -- c'est
    pourquoi elle passe par `catalog_inject.graft_active_ability` et JAMAIS par un
    `u["ActiveAbilities"] = [aid]` a la main :
      1. `BC.Units[<greffon>].ActiveAbilities` <- l'`ActiveAbilityType` ;
      2. `BC.Abilities.ActiveAbilities["AetherStride"]` <- la CONFIG (variables/constantes).
    MESURE du 2026-08-13 : `_load_seed_bc` re-synthetise bien `BC.Abilities`, mais SEULEMENT pour
    les abilities DEJA presentes -- `AetherStride` n'y figure pas (131 cles, clé absente), la
    capture ne portant aucune unite qui la possede. Sans l'ecriture 2, la greffe passe TOUS les
    gates (`casterReason` et `targetReason` valent `0x0`, `decisionView` la dit `usable`) et le cast
    rend **« system error » en CONSOMMANT le tour** (`actionConsumed: true`, `spawned: 0`,
    `UnitStats_ActionsAvailable: 0`) : verrou #226. Ce symptome est INDISCERNABLE du bug qu'on
    cherche -- « l'IA choisit, le moteur n'execute rien » -- et l'aurait donc CONFIRME a tort.

    Ecrit sous `logs/` -- JAMAIS sous `data/`, qui ne porte que des ENTREES versionnees."""
    bc = _load_seed_bc(None)
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(p, dict) and p.get("PlayerType") != 2:        # Environment exclu
            p["MachineOfWarAmmo"] = ammo
    rap = CI.graft_active_ability(bc, MOW, "AetherStride", replace=True)
    print("[1022] greffe : %s" % json.dumps(rap)[:300])
    out = ROOT / "logs" / "runners" / ("bc-1022-%s.json" % uuid.uuid4().hex[:8])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")
    return out


def build(seed: str, board: str, bc: Path, p_units: str = "ultraTigurius,ultraCalgar"):
    state = ROOT / "logs" / "runners" / ("st-1022-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", seed, "--board", board,
         "--seed-bc", str(bc), "--state-file", str(state), "--no-ai",
         "--p-units", p_units, "--a-units", "necroWarden,necroSpyder",
         "--p-mow", MOW],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:", (p.stderr or p.stdout or "")[-900:])
        return None, state
    return json.loads(state.read_text())["runnerId"], state


def occupants(sid, rid) -> set:
    g = rpc(sid, "boardGraph", {"runnerId": rid})
    return {(t["col"], t["row"]) for t in g["tiles"] if t.get("occupantUnitId") is not None}


def feet_from_events(actions, board) -> list:
    """L'ORDRE natif des pieds : tags `Unit_Foot_Tile_Id_1..N` de l'event de spawn -- reconnu par
    ses TAGS, jamais par un ordinal de `IdunBattle.Streams.StepType` (qui a deja glisse d'un cran
    entre deux builds)."""
    for a in actions:
        for ev in (a.get("events") or []):
            try:
                tags = json.loads(ev.get("tags") or "{}")
            except ValueError:
                continue
            ids = [tags[k] for k in sorted(tags) if k.startswith("Unit_Foot_Tile_Id_")]
            if ids:
                return [board.coord(int(i)) for i in ids]
    return []


def native_feet(sid, rid, squad_id) -> list:
    rows = [(u.get("entityId") or 0, (u["col"], u["row"]))
            for u in (rpc(sid, "observeBattle", {"runnerId": rid}).get("units") or [])
            if u.get("squadId") == squad_id and u.get("col") is not None]
    return [t for _e, t in sorted(rows, key=lambda x: x[0])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--psyker", choices=("on", "off"), default="on",
                    help="`off` = CONTRE-EPREUVE : meme montage sans deplacer d'allie Psyker au "
                         "contact de l'empreinte -> le terme `PerformAIAttack` doit rester INERTE")
    ap.add_argument("--p-units", default="ultraTigurius,ultraCalgar")
    a = ap.parse_args()

    sid = _resolve_session()
    # #1074 -- CE PROBE GREFFE (`graft_seed_bc` -> `CI.graft_active_ability`), donc son
    # `load_state` de l'etage C DOIT alimenter `unitAbilityStates`. Sans ce transport,
    # `collect_triggered_abilities` retombe sur `gameconfig.unit(<greffon>)`, qui ne porte PAS
    # `AetherStride` : le port ne monterait AUCUNE classe greffee et l'etage C mesurerait un
    # NEANT en VERT (mesure #448-r3-r1 : 0 echec en CLI contre 3 sous pytest, MEME code).
    bind_ambient_rpc(sid)
    bc = graft_seed_bc()
    print("[1022] seed BC greffe : %s (%s.ActiveAbilities = [%d])" % (bc.name, MOW, AETHER_STRIDE))
    rid, _state = build(a.seed, a.board, bc, a.p_units)
    if rid is None:
        return 2
    print("[build] runner=%s board=%s" % (rid, a.board))
    try:
        view = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        mows = [m for m in (view.get("mows") or []) if m.get("visualId") == MOW]
        if not mows:
            print("PAS MESURE : %s absente de decisionView.mows" % MOW)
            return 2
        caster, owner = mows[0]["casterId"], mows[0].get("owner")
        ids = [x.get("id") for x in (mows[0].get("abilities") or [])]
        print("[greffe] casterId=%s abilities exposees par le natif = %s" % (caster, ids))
        if AETHER_STRIDE not in ids:
            print("PAS MESURE : la greffe n'a pas pris -- le natif n'expose pas 1208 sur la MoW")
            return 2

        board = Board(rpc(sid, "boardGraph", {"runnerId": rid})["tiles"])

        # Attendre que 1208 soit castable ET que ce soit le tour du proprietaire.
        # `for ... else` OBLIGATOIRE : sans lui, une boucle qui EXPIRE laisserait la mesure partir
        # a travers un oracle court-circuite.
        ab = None
        for _ in range(16):
            v = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
            ab = next((x for x in (v["mows"][0].get("abilities") or [])
                       if x.get("id") == AETHER_STRIDE), None)
            ready = (ab and ab.get("usable") and ab.get("hasAmmo", True)
                     and not (ab.get("cooldown") or 0))
            if ready and (owner is None or v.get("currentPlayer") == owner):
                break
            rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}})
        else:
            print("PAS MESURE : 1208 jamais castable en 16 fins de tour (dernier etat : %s)"
                  % json.dumps(ab))
            return 2

        # LE CRAN D'ORACLE (#287-r9) : `decisionView.usable` n'est PAS l'oracle. Seul `casterReason`
        # dit si la cascade ATTEINT la regle dynamique, et il est INDEPENDANT de la cible.
        def _rpc3(method, body, timeout=90000):
            return rpc(sid, method, body, timeout=max(30, int(timeout) // 1000))

        empeche = O.debloquer_oracle(_rpc3, rid, caster, AETHER_STRIDE, jouer_adverse=False)
        if empeche:
            print("PAS MESURE (oracle court-circuite en AMONT) : %s" % empeche)
            return 2

        # --- ETAGE A : `GetDynamicInvalidTargetReason` natif vs `spawn_tile_shape.get_area` -------
        occ = occupants(sid, rid)
        rows, desac = [], 0
        for tid in sorted(board.by_id)[:DYNAMIC_RULE_SAMPLE]:
            pos = board.coord(tid)
            predit = len(STS.get_area(board, occ, pos)) == 3
            # ⚠ LES CLES SONT `casterId`/`abilityType`, ET LE VERDICT EST DANS `targetReason`, PAS
            # A LA RACINE (meme piege que #287-r9 sur probe_91 : lu a cote, le canal « accepte »
            # TOUTE tuile et l'accord ne prouve rien). `O._hex_de` rend le masque effectif.
            r = rpc(sid, "abilityReason", {"runnerId": rid, "casterId": caster,
                                           "abilityType": AETHER_STRIDE, "targetId": tid})
            tr = (r or {}).get("targetReason") or {}
            masque = O._hex_de(tr)
            natif = masque == 0
            noms = ",".join(str(x) for x in (tr.get("reasons") or [])) or "-"
            rows.append((tid, pos, predit, natif, "%s %s" % (hex(masque), noms)))
            desac += int(predit != natif)
        ok_a = sum(1 for _t, _p, pr, na, _r in rows if pr and na)
        ko_a = sum(1 for _t, _p, pr, na, _r in rows if (not pr) and (not na))
        print("[A] regle dynamique : %d tuile(s) | accord=%d | DESACCORD=%d"
              % (len(rows), len(rows) - desac, desac))
        print("    ventilation : aire valide ET acceptee=%d ; aire absente ET refusee=%d" % (ok_a, ko_a))
        if ok_a == 0 or ko_a == 0:
            print("    ATTENTION REGIME DEGENERE : un seul verdict present dans l'echantillon "
                  "-> l'accord ne prouve rien. Elargir DYNAMIC_RULE_SAMPLE.")
        for t, pos, pr, na, raw in rows:
            if pr != na:
                print("    ECART tuile %s %s : port=%s natif=%s reason=%s" % (t, pos, pr, na, raw))

        # --- ETAGE B : le CAST -------------------------------------------------------------------
        cible = next((t for t, _p, pr, na, _r in rows if pr and na), None)
        if cible is None:
            print("PAS MESURE : aucune tuile acceptee par les DEUX cotes -- rien a caster")
            return 2

        # --- ETAGE D (amont) : CRAFTER l'adjacence PSYKER ----------------------------------------
        # Le terme `If(Count(UnitsWithTrait(AdjacentFriends(ActiveTarget,1,3), Psyker, 3)) > 0,
        # PerformAIAttack(ActiveTarget))` est le SEUL etage qui separe 1208 de son voisin de forme
        # 1158. Sans allie Psyker au contact de l'empreinte, il est INERTE et l'accord natif/port
        # ne prouverait rien de lui. On DEPLACE donc une unite plutot que de subir la geometrie de
        # spawn. `--psyker off` sert de CONTRE-EPREUVE (meme montage, rail retire).
        def _voisines(aire):
            """Les tuiles a distance 1 de l'empreinte, empreinte exclue. `Board.neighbours` prend
            un ID de tuile, pas un `(col,row)`."""
            out = set()
            for f in aire:
                fid = board.id_at(f[0], f[1])
                for nid in (board.neighbours(fid) if fid is not None else ()):
                    out.add(board.coord(nid))
            return out - set(aire)

        psyker_pose = None
        if a.psyker != "off":
            # Les traits ne sont PAS publies par `decisionView.units[]` (verifie : le champ est
            # absent) -> on les lit au GAMECONFIG par `visualId`, ce qui est de toute facon la
            # source que le natif lit lui-meme pour la config d'unite.
            mine = [u for u in (rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
                                .get("units") or [])
                    if u.get("ctrl") and u.get("alive") and u.get("pos")
                    and "Psyker" in set((GC.unit(u.get("visualId")) or {}).get("traits") or [])]
            mv = rpc(sid, "aiMovableTiles", {"runnerId": rid}) or {}
            atteignables = {e.get("unitId"): {(t["col"], t["row"]) for t in (e.get("tiles") or [])}
                            for e in (mv.get("units") or [])}
            print("[D] psykers CONTROLES : %s"
                  % [(u["id"], u.get("visualId"), len(atteignables.get(u["id"]) or ()))
                     for u in mine])
            # LA CIBLE SE CHOISIT POUR LE SCENARIO, pas l'inverse : on balaie TOUTES les tuiles
            # acceptees et on retient celle dont l'empreinte a une voisine ATTEIGNABLE par un
            # psyker. « bloque par la geometrie de spawn » n'est pas une conclusion recevable.
            # PREFERENCE FORTE : une empreinte qui touche AUSSI un ennemi -- sans cible a portee,
            # `PerformAIAttack` s'execute mais n'attaque personne, et l'accord natif/port a 0 degat
            # serait un accord en REGIME DEGENERE.
            ennemis = {(u["col"], u["row"]) for u in (rpc(sid, "observeBattle", {"runnerId": rid})
                                                     .get("units") or [])
                       if u.get("col") is not None and u.get("team") is not None
                       and u.get("team") != (mine[0].get("team") if mine else None)}
            couples = []
            for tid in sorted(board.by_id):
                ar = STS.get_area(board, occ, board.coord(tid))
                if len(ar) != 3:
                    continue
                vs = _voisines(ar) - occ
                proche = any(hexgeo.distance(f, e) <= 1 for f in ar for e in ennemis)
                for u in mine:
                    cand = sorted((atteignables.get(u["id"]) or set()) & vs)
                    if cand:
                        couples.append((0 if proche else 1, tid, u, cand[0]))
            for _rang, tid, u, dest in sorted(couples, key=lambda x: (x[0], x[1])):
                r = rpc(sid, "applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": u["id"],
                    "to": {"col": dest[0], "row": dest[1]}}})
                if r.get("ok"):
                    psyker_pose = (u["id"], u.get("visualId"), dest, "ennemi au contact"
                                   if _rang == 0 else "aucun ennemi au contact")
                    cible, occ = tid, occupants(sid, rid)
                    break
        aire = STS.get_area(board, occ, board.coord(cible))
        print("[D] adjacence Psyker CRAFTEE : %s -> cible retenue %s %s (aire=%s)"
              % (psyker_pose, cible, board.coord(cible), aire))

        # --- ETAGE E (amont) : AMENER UN ENNEMI AU CONTACT DE L'EMPREINTE (#1022-r3) --------------
        # Sans cible a portee, `PerformAIAbilityUnitBehaviour$$Execute` s'execute mais ne frappe
        # personne : natif et port rendent 0 degat et l'accord est en REGIME DEGENERE -- il ne dit
        # rien du choix de cible ni de la magnitude. C'est le residu #1022-r3.
        #
        # ⚠ SA PREMISSE ETAIT FAUSSE, et elle est REFUTEE PAR LE HARNAIS LUI-MEME. La fiche disait
        # « l'equipe adverse n'est pas pilotable sous `--no-ai` », donc « il faut un board ou les
        # trois contraintes coexistent ». Or `tests/engine/runner/_charge_regime.py::place` porte,
        # ecrit noir sur blanc : « `applyAction` ne verifie NI propriete NI portee : les DEUX camps
        # sont pilotables ». Ce probe DEPLACE deja un allie par ce meme canal -- rien ne distingue
        # une unite adverse. Aucun board a chercher : on POSE l'ennemi.
        #
        # ⚠ ET AUCUN BOARD NE L'AURAIT DONNE. C'est structurel, pas une malchance de `MC1_67` :
        # les spawns des deux equipes sont aux deux bouts (`C1_74` : team 1 en row 0, team 2 en
        # rows 5-8, `(2,0)->(5,4) = 5 hex`), et l'ancre du cast doit etre a portee du CASTER, donc
        # dans son camp. Au tour 0, aucune empreinte atteignable ne touche un ennemi, sur aucun
        # board.
        #
        # Un `place` est un `MoveUnitOperation` NATIF COMPLET (il appelle `UpdateCharging`, peut
        # declencher overwatch et charges) : on le joue AVANT le cast et on RELIT la position, un
        # pas refuse ne devant jamais passer pour un pas fait.
        # ⚠ LE CANAL DES ADVERSES EST `decisionView`, PAS `observeBattle` -- et les confondre rend un
        # ensemble VIDE en silence, donc un « aucun ennemi posable » qui n'a rien mesure. Le
        # discriminant lu ici est `ctrl` (l'unite est-elle du camp qu'on pilote), le meme champ que
        # la selection des psykers plus haut ; `observeBattle.units[]`, lui, ne porte pas de `team`
        # comparable a `owner` (qui est un PLAYER).
        ennemi_pose = None
        refus = []
        vs_libres = sorted(_voisines(aire) - occupants(sid, rid))
        dv_e = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}).get("units") or []
        adverses = [u for u in dv_e
                    if u.get("alive") and u.get("pos") and not u.get("ctrl")]
        print("[E] adverses VIVANTS lus dans decisionView : %s"
              % [(u["id"], u.get("visualId"), (u["pos"]["col"], u["pos"]["row"]))
                 for u in adverses][:8])
        deja = any(hexgeo.distance((u["pos"]["col"], u["pos"]["row"]), f) <= 1
                   for u in adverses for f in aire)
        if deja:
            ennemi_pose = ("DEJA", "un ennemi touche deja l'empreinte -- rien a poser")
        else:
            for e in adverses:
                for dest in vs_libres:
                    r = rpc(sid, "applyAction", {"runnerId": rid, "action": {
                        "kind": "move", "unitId": e["id"],
                        "to": {"col": dest[0], "row": dest[1]}}})
                    dv2 = (rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
                           .get("units") or [])
                    now = next((x for x in dv2 if x.get("id") == e["id"]), None)
                    p = (now or {}).get("pos") or {}
                    if (p.get("col"), p.get("row")) == dest:
                        ennemi_pose = (e["id"], e.get("visualId"), dest)
                        occ = occupants(sid, rid)
                        break
                    # ON LEVE L'ECHEC : un `applyAction` refuse rend `ok`/`mutated` et parfois un
                    # `error` -- s'en tenir a « la position n'a pas change » ferait conclure
                    # « geometrie impossible » sur un simple refus de propriete.
                    refus.append((e["id"], dest, r.get("ok"), r.get("mutated"),
                                  str(r.get("error") or r.get("reason") or "")[:90]))
                if ennemi_pose:
                    break
        print("[E] ennemi au contact de l'empreinte : %s (voisines libres=%s)"
              % (ennemi_pose, vs_libres[:6]))
        if refus:
            print("[E] refus d'applyAction (les 4 premiers) : %s" % (refus[:4],))
        if ennemi_pose is None:
            print("    ATTENTION REGIME DEGENERE (#1022-r3) : aucun ennemi n'a pu etre pose au "
                  "contact -- `PerformAIAttack` frappera dans le vide et l'accord a 0 degat ne "
                  "prouvera RIEN. Ne pas lire le verdict de l'etage D comme une confrontation "
                  "de l'ATTAQUE.")
        pre_dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        pre_ob = rpc(sid, "observeBattle", {"runnerId": rid})
        # Dump du Mersenne Twister PRIS AVANT LE CAST : c'est ce qui rend le rejeu offline
        # comparable au live des que le summon frappe pour de bon (cf. l'etage C).
        pre_rng = rpc(sid, "dumpRng", {"runnerId": rid})
        avant = {u.get("squadId") for u in (pre_ob.get("units") or [])}
        pred_area = STS.get_area(board, occ, board.coord(cible))
        anc = board.coord(cible)
        dv = rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        m0 = next((m for m in (dv.get("mows") or []) if m.get("casterId") == caster), None)
        print("    ETAT AVANT CAST : currentPlayer=%s owner=%s mow=%s"
              % (dv.get("currentPlayer"), owner, json.dumps((m0 or {}).get("abilities") or [])[:300]))
        cr = rpc(sid, "abilityReason", {"runnerId": rid, "casterId": caster,
                                        "abilityType": AETHER_STRIDE, "targetId": cible})
        print("    casterReason=%s / targetReason=%s"
              % (json.dumps(cr.get("casterReason"))[:200], json.dumps(cr.get("targetReason"))[:200]))
        # ⚠ Un cast de MoW TILE-TARGET se pose par `casterId`/`abilityType`/`to`, PAS par
        # `unitId`/`abilityId`/`targetId` : avec les mauvaises cles le RPC rend `ok` sans rien
        # muter -- un NO-OP qui se lit comme « le natif n'a rien fait » (mesure du 2026-08-13).
        res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster, "abilityType": AETHER_STRIDE,
            "to": {"col": anc[0], "row": anc[1]}}})
        actions = res.get("actions") or []
        print("    reponse applyAction : ok=%s mutated=%s spawned=%s"
              % (res.get("ok"), actions[0].get("mutated") if actions else None,
                 actions[0].get("spawned") if actions else None))
        if not res.get("ok"):
            print("    REFUS BRUT : %s" % json.dumps(res)[:600])
        pieds = feet_from_events(actions, board)
        obs = rpc(sid, "observeBattle", {"runnerId": rid}).get("units") or []
        neufs = [u for u in obs if u.get("squadId") not in avant]
        squads = sorted({u.get("squadId") for u in neufs})
        print("[B] cast 1208 sur la tuile %s %s" % (cible, board.coord(cible)))
        print("    aire PREDITE par le port          : %s" % (pred_area,))
        print("    pieds NATIFS (tags Unit_Foot_...) : %s" % (pieds,))
        print("    squads neufs : %s" % (squads,))
        for s in squads:
            f = native_feet(sid, rid, s)
            vid = next((u.get("visualId") for u in neufs if u.get("squadId") == s), None)
            traits = next((u.get("traits") for u in neufs if u.get("squadId") == s), None)
            print("      squad %s visualId=%s pieds=%s traits=%s" % (s, vid, f, traits))
        mows2 = [m for m in (rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
                             .get("mows") or []) if m.get("visualId") == MOW]
        print("    MoW encore dans decisionView.mows apres le cast : %s" % bool(mows2))

        # --- ETAGE C : le PORT rejoue le MEME cast sur l'etat PRE-cast -------------------------
        from engine.runner.abilities.thousandsons import AetherStrideAbility
        from engine.entities.traits.unit_trait import UnitTrait, has_trait
        from engine.runner.components import MachineComponent, StatsComponent
        from engine.runner.snapshot import load_state
        from engine.services import movement_query as MQ
        st = load_state(pre_dv, pre_ob, board=board)
        # ⚠ LE MT DOIT ETRE CALE DES QUE LE SUMMON PEUT FRAPPER (#1022-r3). Tant qu'aucun ennemi
        # n'etait au contact, `PerformAIAttack` n'atteignait jamais `AttackDamageOperation` et
        # `state.rng is None` passait inapercu ; avec l'ennemi pose, le rejeu tire pour de bon et
        # `damage_ops/normal.py` REFUSE (`state.rng non cale`) -- un refus explicite, pas un
        # degat invente. On repose le twister sur le dump pris JUSTE AVANT le cast live, donc le
        # port consomme le MEME flux que le natif. Meme patron que `_charge_regime::offline_state`.
        if isinstance(pre_rng, dict) and pre_rng.get("mt"):
            from engine.runner.prng import IntBasedMersenneTwister
            _mt = IntBasedMersenneTwister()
            _mt.mt, _mt.mti = list(pre_rng["mt"]), pre_rng["mti"]
            st.rng = _mt
        print("[C] MT cale sur le dump pre-cast : %s (mti=%s)"
              % (bool(getattr(st, "rng", None)), (pre_rng or {}).get("mti")))
        diag = AetherStrideAbility().execute_behaviour(st, caster, cible)
        print("[C] port : tile=%s spawned=%s removed_machine=%s traits=%s carried=%s"
              % (diag.get("tile"), diag.get("spawned"), diag.get("removed_machine"),
                 diag.get("traits"), diag.get("carried")))
        pieds_port = list(diag.get("feet") or [])
        if diag.get("spawned"):
            sid0 = diag["spawned"][0]
            sc = st.get_entity(sid0).get_component(StatsComponent)
            stat = has_trait(sc.ctx.traits, UnitTrait.Stationary) if sc is not None else None
            mv = MQ.get_movable_positions_for(board, st, sid0, [board.coord(cible)])
            print("    pieds PORTES = %s | Stationary=%s | positions mobiles=%s"
                  % (pieds_port, stat, mv))
        mc = st.get_entity(caster).get_component(MachineComponent) if st.get_entity(caster) else None
        print("    MachineComponent.removed cote port = %s" % (getattr(mc, "removed", None),))
        accord_c = (sorted(pieds_port) == sorted(pieds)) and bool(pieds)
        print("[C] VERDICT empreinte natif vs port : %s" % ("ACCORD" if accord_c else "DESACCORD"))

        # --- ETAGE D (aval) : le terme PSYKER a-t-il MORDU ? --------------------------------------
        # Cote PORT : `ai_attacks` non vide <=> `Count(psykers adjacents) > 0`. Cote NATIF : une
        # attaque du summon apparait dans les `changes` du cast (PV d'une unite ADVERSE qui bougent).
        pv_avant = {u.get("squadId"): u.get("hp") for u in (pre_ob.get("units") or [])}
        pv_apres = {u.get("squadId"): u.get("hp") for u in obs}
        touches = sorted(s for s in pv_avant
                         if s in pv_apres and pv_apres[s] is not None and pv_avant[s] is not None
                         and pv_apres[s] < pv_avant[s])
        # ⚠ `observeBattle.units[]` NE PUBLIE PAS les traits -> les lire au GAMECONFIG par
        # `visualId`. Un `u.get("traits") or []` rend `[]` pour TOUTE unite et fait conclure
        # « aucun psyker adjacent » meme quand il y en a un (mesure du 2026-08-13).
        adj_psy = [u for u in (pre_ob.get("units") or [])
                   if u.get("col") is not None
                   and "Psyker" in set((GC.unit(u.get("visualId")) or {}).get("traits") or [])
                   and any(hexgeo.distance((u["col"], u["row"]), f) == 1 for f in pieds)]
        print("[D] psykers a distance 1 d'un pied (canal observeBattle) : %s"
              % [(u.get("squadId"), u.get("visualId")) for u in adj_psy])
        print("[D] port : ai_attacks=%s" % json.dumps(diag.get("ai_attacks"))[:400])
        print("[D] natif : unites ayant PERDU des PV pendant le cast = %s" % (touches,))

        # --- ETAGE F : L'ATTAQUE ELLE-MEME, cible ET magnitude (#1022-r3) -------------------------
        # C'est l'etage que le residu declarait NON CONFRONTE : sans ennemi a portee, `attacks`
        # etait vide DES DEUX COTES et l'accord a 0 degat ne disait rien. L'etage E l'a leve.
        # ⚠ ON ASSERTIONNE LE NON-NUL AVANT DE COMPARER : un accord `[] == []` (ou `0 == 0`) est
        # exactement le regime degenere qu'on vient de supprimer -- s'il revient, il doit se voir.
        att = [x for a_ in (diag.get("ai_attacks") or []) for x in (a_.get("attacks") or [])]
        cibles_port = sorted({int(x["target"]) for x in att if x.get("target") is not None})
        degat_port = sum(int(x.get("total") or 0) for x in att)
        degats_natifs = {s: int(pv_avant[s]) - int(pv_apres[s]) for s in touches}
        degat_natif = sum(degats_natifs.values())
        print("[F] ATTAQUE du summon -- cible(s) port=%s natif=%s | degat port=%s natif=%s (%s)"
              % (cibles_port, touches, degat_port, degat_natif, degats_natifs))
        if not att or degat_natif == 0:
            print("    REGIME DEGENERE : `attacks` vide cote port (%s) ou 0 degat cote natif (%s) "
                  "-- l'etage F ne conclut RIEN. #1022-r3 reste ouvert." % (bool(att), degat_natif))
        else:
            print("[F] VERDICT CIBLE : %s"
                  % ("ACCORD" if cibles_port == touches else
                     "DESACCORD port=%s natif=%s" % (cibles_port, touches)))
            print("[F] VERDICT MAGNITUDE : %s (ecart=%s)"
                  % ("ACCORD" if degat_port == degat_natif else "DESACCORD",
                     degat_port - degat_natif))

            # --- ETAGE G : DECOMPOSER l'ecart de magnitude, jamais le fitter -------------------
            # On ne cherche pas un facteur : on met COTE A COTE ce qui alimente le degat du
            # summon des deux cotes -- son `AbilityState` (niveau / multiplicateur) et ses stats
            # d'attaque. Le premier etage ou natif != port est la cause ; tout le reste en aval.
            from engine.runner.components import StatsComponent as _SC
            sid_port = (diag.get("spawned") or [None])[0]
            ctx_port = None
            if sid_port is not None:
                _e = st.get_entity(sid_port)
                _sc = _e.get_component(_SC) if _e is not None else None
                ctx_port = getattr(_sc, "ctx", None)
            snap_n = rpc(sid, "combatSnapshot", {"runnerId": rid}) or {}
            ligne_n = next((u for u in (snap_n.get("units") or [])
                            if u.get("entityId") in set(squads)), None)
            stats_n = (ligne_n or {}).get("stats") or {}
            print("[G] summon PORT  : id=%s visual=%s attack=%s dmg=%s level=%s mult=%s hp=%s"
                  % (sid_port, getattr(ctx_port, "visual_id", None),
                     getattr(ctx_port, "attack", None), getattr(ctx_port, "damage", None),
                     getattr(ctx_port, "active_ability_level", None),
                     getattr(ctx_port, "ability_variables_multiplier", None),
                     getattr(ctx_port, "health", None)))
            print("[G] summon NATIF : entityId=%s visual=%s unitConfig=%s stats(extrait)=%s"
                  % ((ligne_n or {}).get("entityId"), (ligne_n or {}).get("visualId"),
                     json.dumps((ligne_n or {}).get("unitConfig") or {})[:220],
                     json.dumps({k: v for k, v in list(stats_n.items())[:10]})[:300]))
        print("PROBE OK")
        return 0
    finally:
        if rid and not a.keep:
            try:
                rpc(sid, "disposeRunner", {"runnerId": rid}, timeout=30)
                print("[1022] runner %s dispose" % rid)
            except Exception as exc:                                # noqa: BLE001
                print("[1022] dispose KO : %s" % exc)


if __name__ == "__main__":
    sys.exit(main())
