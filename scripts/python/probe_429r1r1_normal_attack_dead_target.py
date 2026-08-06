"""#429-r1-r1 -- L'ATTAQUE NORMALE SUR UN CADAVRE : quelles PORTES, et que refuse le natif.

LA QUESTION PREALABLE, ET POURQUOI ELLE PASSE AVANT LE PORT
-----------------------------------------------------------
#429-r1 a pose le gate `IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility`
sur la seule voie d'ABILITY (`AbilityHandler.visit_ActiveAbilityMessage`), et a nomme le residu :
l'attaque NORMALE n'est pas gatee. Elle a AUSSI nomme ce qu'il fallait etablir AVANT de porter :

    les attaques DECLENCHEES (overwatch, riposte) empruntent-elles `visit_AttackUnitMessage` ?

Si oui, un gate pose la les gaterait elles aussi -- et il faudrait montrer que le natif les gate de
la meme facon, sans quoi le correctif creerait une divergence la ou il n'y en avait pas.

CE QUE CE PROBE MESURE
----------------------
  volet `portes`  -- OFFLINE PUR (balayage AST d'`engine/**`, aucun runner) : qui CONSTRUIT un
                     `AttackUnitMessage`, et qui appelle `AttackDamageOperation.execute`. C'est la
                     REPONSE, derivee du code et non de la prose : les deux ensembles sont
                     DISJOINTS. Contre-epreuve integree (`--check`) : le scan doit retrouver les
                     sites CONNUS, sinon son silence ne vaut rien.
  volet `gate`    -- OFFLINE PUR : sur un `State` synthetique, le gate refuse-t-il l'attaque
                     normale sur un cadavre, aux TROIS portes du port ?
  volet `live`    -- CONFRONTATION : `spaceWulfen` tue `tyranWingedPrime`, puis `ultraInceptorSgt`
                     porte son ATTAQUE NORMALE sur le cadavre. Natif vs port, avec contre-epreuve
                     (gate debranche). Reutilise le montage ECRIT de
                     `probe_429r1_dead_target_gate` (positions forcees, DEUX ennemis).

⚠ CE QUE LE LIVE NE PEUT PAS DISCRIMINER (identique a #429-r1) : le gate cible-morte et
`IsInvalidTarget` sortent tous deux avant `On(0x2a)`, avant tout degat et avant les flags de tour.
Leur observable depuis le runner est IDENTIQUE. Le live etablit « le natif no-oppe » ; que ce soit
CE gate-la est etabli au decompile.

USAGE (ASCII only)
------------------
    python scripts/python/probe_429r1r1_normal_attack_dead_target.py --volet portes
    python scripts/python/probe_429r1r1_normal_attack_dead_target.py --volet portes --check
    python scripts/python/probe_429r1r1_normal_attack_dead_target.py --volet gate
    python scripts/python/probe_429r1r1_normal_attack_dead_target.py --volet live --state-file <ABSOLU>
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ENGINE = Path(__file__).resolve().parent / "engine"

# Sites CONNUS que le scan DOIT retrouver -- la contre-epreuve du volet `portes`. Sans elle, un
# scan qui rendrait zero partout se lirait comme « aucune porte », exactement le faux negatif que
# #429-r1 reproche a `search_code`.
ATTENDUS_EXECUTE = (
    "runner/operations/damage.py",                     # le visiteur de l'attaque normale
    "runner/operations/triggers/effect_triggers.py",   # OverwatchAutoAttack
    "runner/abilities/behaviours/combat.py",           # la feuille DSL UseActiveAbility
)


def _rel(p: Path) -> str:
    return p.relative_to(ENGINE).as_posix()


def _scan() -> dict:
    """Balaye `engine/**` en AST. Rend `{constructeurs, appels_execute}`.

    `constructeurs` = tout `AttackUnitMessage(...)` CONSTRUIT (le seul moyen d'atteindre
    `DamageHandler.visit_AttackUnitMessage`, le visiteur etant appele par `Message.accept`).
    `appels_execute` = tout `<X>.execute(...)` dont le receveur nomme `AttackDamageOperation`."""
    ctors, calls = [], []
    for f in sorted(ENGINE.rglob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id == "AttackUnitMessage":
                ctors.append((_rel(f), node.lineno))
            elif isinstance(fn, ast.Attribute) and fn.attr == "execute":
                recv = fn.value
                nom = recv.id if isinstance(recv, ast.Name) else getattr(recv, "attr", None)
                if nom == "AttackDamageOperation":
                    calls.append((_rel(f), node.lineno))
    return {"constructeurs": ctors, "appels_execute": calls}


def volet_portes(check: bool) -> int:
    r = _scan()
    ctors, calls = r["constructeurs"], r["appels_execute"]
    fichiers = sorted({f for f, _ in calls})

    print("--- QUI CONSTRUIT `AttackUnitMessage` DANS engine/** ---")
    print("  %d site(s)" % len(ctors))
    for f, ln in ctors:
        print("     %s:%d" % (f, ln))
    print("  -> le visiteur `DamageHandler.visit_AttackUnitMessage` n'est donc atteint QUE")
    print("     depuis le HARNAIS (tests, probes, pilotage RL), jamais depuis engine/.")
    print("")
    print("--- QUI APPELLE `AttackDamageOperation.execute` (le FOYER de l'attaque normale) ---")
    print("  %d appel(s), %d fichier(s)" % (len(calls), len(fichiers)))
    for f, ln in calls:
        print("     %s:%d" % (f, ln))
    print("")
    print("REPONSE A LA QUESTION PREALABLE : les deux ensembles sont DISJOINTS.")
    print("  Les attaques DECLENCHEES n'empruntent PAS `visit_AttackUnitMessage` -- elles")
    print("  appellent l'operation directement. Un gate pose au rang du MESSAGE ne les aurait")
    print("  donc ni gatees ni sur-refusees : il n'aurait ferme qu'UNE porte sur %d." % len(fichiers))

    if not check:
        return 0
    print("")
    print("--- CONTRE-EPREUVE : le scan retrouve-t-il les sites CONNUS ? ---")
    manquants = [a for a in ATTENDUS_EXECUTE if a not in fichiers]
    for a in ATTENDUS_EXECUTE:
        print("     %-52s %s" % (a, "TROUVE" if a in fichiers else "MANQUANT"))
    if manquants or not calls:
        print("  ECHEC : le scan ne retrouve pas ce qui EXISTE -> son silence ne vaut rien.")
        return 1
    print("  OK : le scan mord sur les trois formes (visiteur, trigger d'effet, feuille DSL).")
    return 0


# ------------------------------------------------------------------------------------------
def _state_synthetique():
    """Un `State` MINIMAL a deux unites adjacentes -- assez pour exercer les gates, sans runner."""
    from engine.runner.state import Entity, State
    from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                          UnitComponent)
    st = State()
    for uid, team, col, row in ((1, 1, 1, 1), (2, 2, 2, 1)):
        e = Entity(uid)
        e.add_component(UnitComponent(visual_id="u%d" % uid, alive=True))
        e.add_component(OwnerComponent(team=team, player=team))
        e.add_component(PositionComponent(col=col, row=row))
        e.add_component(HealthComponent(hp=100, hp_max=100))
        st.entities[uid] = e
    return st


def volet_gate() -> int:
    """OFFLINE PUR : le gate refuse-t-il l'attaque normale sur un cadavre ?

    Balaye les DEUX etats (cible vivante / cible morte) sur le predicat porte. Une cible VIVANTE
    doit passer : un gate qui refuserait tout passerait la moitie « morte » sans rien prouver."""
    from engine.runner.components import HealthComponent, UnitComponent
    from engine.runner.operations.active_ability import is_dead_unit_and_not_allowed_by_ability

    st = _state_synthetique()
    vivante = is_dead_unit_and_not_allowed_by_ability(st, None, 2)
    ce = st.get_entity(2)
    ce.get_component(HealthComponent).hp = 0
    ce.get_component(UnitComponent).alive = False
    morte = is_dead_unit_and_not_allowed_by_ability(st, None, 2)
    # Une cible qui n'est PAS une unite (id inconnu) : le natif rend false (`!IsUnit -> false`).
    non_unite = is_dead_unit_and_not_allowed_by_ability(st, None, 999)

    print("is_dead_unit_and_not_allowed_by_ability(ability_class=None) :")
    print("   cible VIVANTE   -> %s   (attendu False)" % vivante)
    print("   cible MORTE     -> %s   (attendu True)" % morte)
    print("   cible NON-UNITE -> %s   (attendu False)" % non_unite)
    ok = (vivante is False) and (morte is True) and (non_unite is False)
    print("   verdict : %s" % ("OK" if ok else "ECHEC"))
    return 0 if ok else 1


# ------------------------------------------------------------------------------------------
def scenario_live(state_file: str, seed: str = "777", board: str = "MC1_67",
                  verbose: bool = True, killer: str = "spaceWulfen",
                  attacker: str = "ultraInceptorSgt") -> dict:
    """MONTAGE ECRIT, REUTILISE de `probe_429r1_dead_target_gate` (positions forcees, DEUX ennemis
    -- avec un seul, le tuer TERMINE la bataille et les vues cessent de publier le cadavre).

    Difference avec le scenario parent : ce qui est joue sur le cadavre n'est pas un CAST mais
    l'ATTAQUE NORMALE (`abilityType` = l'ability `kind == "normal"` du DV cote natif ;
    `AttackUnitMessage` cote port -- ce message n'existe PAS en natif).

    Renvoie un dict de mesures ; `why` non vide = montage NON INSTALLE (jamais un skip vert)."""
    import json
    import subprocess

    from probe_429r1_dead_target_gate import (A_UNITS, P_UNITS, _ids, _normal_id, rpc, sid)
    from sibling_script import sibling_script

    from engine.runner.snapshot import load_state
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.entities.pathfinding.board import Board

    out = subprocess.run([sys.executable, sibling_script("rl_duel.py"), "build",
                          "--seed", seed, "--board", board, "--state-file", state_file,
                          "--p-units", P_UNITS, "--a-units", A_UNITS, "--hp-target", "1",
                          "--place", "spaceWulfen:3,3", "--place", "ultraInceptorSgt:1,3",
                          "--a-place", "tyranWingedPrime:2,3",
                          "--a-place", "tauDarkstrider:6,6"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return {"why": "BUILD rc=%d : %s" % (out.returncode, (out.stderr or out.stdout)[-500:])}
    st_json = json.loads(Path(state_file).read_text(encoding="utf-8"))
    s, rid = sid(), int(st_json["runnerId"])
    res = {"rid": rid}
    try:
        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ids = _ids(dv)
        tueur, att, prime = ids.get(killer), ids.get(attacker), ids.get("tyranWingedPrime")
        if None in (tueur, att, prime):
            return {"why": "roster incomplet : %s" % sorted(ids)}
        nid_tueur = _normal_id(dv, tueur)
        nid_att = _normal_id(dv, att)
        if nid_tueur is None or nid_att is None:
            return {"why": "attaque normale introuvable (tueur=%s attaquant=%s)"
                           % (nid_tueur, nid_att)}
        res["normal_ability_id"] = nid_att
        # --- 0. CONTRE-EPREUVE « CIBLE VIVANTE », prise AVANT le kill -------------------------
        # Un gate qui refuserait TOUT passerait toutes les assertions « cadavre ». On mesure donc
        # d'abord, sur le MEME porteur et la MEME attaque normale, que le port EXECUTE quand la
        # cible est VIVANTE. Etat de replay pur (aucun RPC mutant) : l'attaque n'est jouee QUE cote
        # port, le runner natif n'en sait rien.
        ob_v = rpc(s, "observeBattle", {"runnerId": rid}, 40)
        snap_v = rpc(s, "combatSnapshot", {"runnerId": rid}, 40)
        bg_v = rpc(s, "boardGraph", {"runnerId": rid}, 60)
        rng_v = rpc(s, "dumpRng", {"runnerId": rid}, 30)
        st_v = load_state(dv, ob_v, snap_v)
        if isinstance(bg_v, dict) and "tiles" in bg_v:
            st_v.board = Board(bg_v["tiles"], adjacency="native_sym")
        if isinstance(rng_v, dict) and rng_v.get("mt"):
            _r = IntBasedMersenneTwister()
            _r.mt = list(rng_v["mt"])
            _r.mti = rng_v["mti"]
            st_v.rng = _r
        _m0 = getattr(st_v.rng, "mti", None)
        _ce_v = st_v.get_entity(prime)
        from engine.runner.components import UnitComponent as _UCv
        res["vivante_cible_alive"] = None if _ce_v is None else getattr(
            _ce_v.get_component(_UCv), "alive", None)
        _rv = Runner(st_v).install_default_handlers(20)
        _rv.apply(AttackUnitMessage(tueur, prime))
        _lv = _rv.damage_handler.last
        res["vivante_port_total"] = None if not isinstance(_lv, dict) else _lv.get("total")
        res["vivante_port_draws"] = (None if _m0 is None else
                                     (st_v.rng.mti - _m0 + (624 if st_v.rng.mti < _m0 else 0)))
        # --- 1. TUER la cible ---------------------------------------------------------------
        rpc(s, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": tueur, "targetId": prime, "abilityType": nid_tueur}}, 40)
        ob0 = rpc(s, "observeBattle", {"runnerId": rid}, 40)
        dv = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        cible = next((u for u in (dv.get("units") or []) if u.get("id") == prime), {})
        res["cible_dv_alive"] = cible.get("alive")
        res["cible_dv_hp"] = cible.get("hp")
        res["cible_ob_dead"] = next((u.get("isDead") for u in (ob0.get("units") or [])
                                     if u.get("id") == prime), None)
        if cible.get("alive") or res["cible_ob_dead"] is False:
            return {"why": "la cible n'est pas morte -- montage non installe", **res}
        # --- 2. ATTAQUE NORMALE sur le CADAVRE : mesure NATIVE -------------------------------
        snap = rpc(s, "combatSnapshot", {"runnerId": rid}, 40)
        bg = rpc(s, "boardGraph", {"runnerId": rid}, 60)
        st = load_state(dv, ob0, snap)
        if isinstance(bg, dict) and "tiles" in bg:
            st.board = Board(bg["tiles"], adjacency="native_sym")
        s0 = rpc(s, "dumpRng", {"runnerId": rid}, 30)
        r = rpc(s, "applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": att, "targetId": prime, "abilityType": nid_att}}, 40)
        s1 = rpc(s, "dumpRng", {"runnerId": rid}, 30)
        res["live_ok"] = bool(isinstance(r, dict) and r.get("ok"))
        res["live_action_consumed"] = (r or {}).get("actionConsumed")
        if isinstance(s0, dict) and isinstance(s1, dict):
            a, b = s0.get("mti"), s1.get("mti")
            res["live_draws"] = (b - a + (624 if b < a else 0)) if None not in (a, b) else None
        dv2 = rpc(s, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        res["live_att_has_action"] = next(
            (u.get("hasAction") for u in (dv2.get("units") or []) if u.get("id") == att), None)
        # --- 3. le MEME coup cote PORT --------------------------------------------------------
        from engine.runner.components import PositionComponent, UnitComponent as _UC
        ce = st.get_entity(prime)
        res["port_cible_presente"] = ce is not None
        res["port_cible_alive"] = None if ce is None else getattr(
            ce.get_component(_UC), "alive", None)
        res["port_cible_pos"] = None if ce is None else (
            None if ce.get_component(PositionComponent) is None else
            (ce.get_component(PositionComponent).col, ce.get_component(PositionComponent).row))

        def _cale(state):
            if isinstance(s0, dict) and s0.get("mt"):
                rng = IntBasedMersenneTwister()
                rng.mt = list(s0["mt"])
                rng.mti = s0["mti"]
                state.rng = rng
            return getattr(state.rng, "mti", None)

        mti0 = _cale(st)
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(att, prime))
        res["port_last"] = runner.damage_handler.last if hasattr(runner, "damage_handler") else None
        res["port_draws"] = (None if mti0 is None else
                             (st.rng.mti - mti0 + (624 if st.rng.mti < mti0 else 0)))
        # --- 3bis. LA PORTE DECLENCHEE : l'operation appelee DIRECTEMENT ----------------------
        # C'est ce qui separe les deux etages possibles. Les ~11 call-sites declenches (overwatch,
        # riposte, drone commande, summon) n'empruntent AUCUN visiteur : ils appellent
        # `AttackDamageOperation.execute` tel quel. Un gate pose au rang du MESSAGE les laisserait
        # tous ouverts. On mesure donc l'operation NUE sur le cadavre, sur un etat frais.
        from engine.runner.operations.damage import AttackDamageOperation
        st3 = load_state(dv, ob0, snap)
        if isinstance(bg, dict) and "tiles" in bg:
            st3.board = Board(bg["tiles"], adjacency="native_sym")
        mti3 = _cale(st3)
        _op = AttackDamageOperation.execute(st3, att, prime)
        res["port_op_directe"] = _op
        res["port_op_directe_draws"] = (None if mti3 is None else
                                        (st3.rng.mti - mti3 + (624 if st3.rng.mti < mti3 else 0)))
        # --- 3ter. LE GATE DE MESSAGE SEUL, DEBRANCHE (#429-r1-r3-r1) --------------------------
        # DEPUIS #429-r1-r3-r1, la voie du MESSAGE porte DEUX gates : celui du `Visit` natif
        # (`IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled`) puis celui de l'OPERATION
        # (`IsDeadUnitAndNotAllowedByAbility`). Sur un CADAVRE ils CONVERGENT -- et c'est
        # exactement ce qu'il faut MESURER, pas supposer : neutraliser le seul gate de message ne
        # doit RIEN changer, sinon le gate d'operation ne mordrait plus sur cette porte et
        # l'etape 4 ci-dessous ne prouverait plus rien de LUI.
        import engine.runner.components as C                        # noqa: PLC0415
        st5 = load_state(dv, ob0, snap)
        if isinstance(bg, dict) and "tiles" in bg:
            st5.board = Board(bg["tiles"], adjacency="native_sym")
        _cale(st5)
        from counterproof import substituer_partout                 # noqa: PLC0415
        with substituer_partout(C, "is_alive_and_not_fled", lambda *_a, **_k: True):
            r5 = Runner(st5).install_default_handlers(20)
            r5.apply(AttackUnitMessage(att, prime))
            res["port_sans_gate_message_last"] = (r5.damage_handler.last
                                                  if hasattr(r5, "damage_handler") else None)
        # --- 4. CONTRE-EPREUVE : le MEME coup, LES DEUX gates DEBRANCHES ------------------------
        # Un vert de l'etape 3 ne prouve rien tant qu'on n'a pas montre que SANS gate le port
        # EXECUTAIT sur le cadavre.
        # ⚠ #419-r6-r1 : ce commentaire disait << les deux gates sont importes en LAZY dans leurs
        # porteurs, donc substituer l'attribut de module les neutralise a TOUTES leurs poses >>.
        # La premisse est FAUSSE depuis `492c722f` (hissage de 624 imports differes) : les deux
        # consommateurs (`operations/damage.py`, `abilities/handler.py`) lient le nom A L'IMPORT,
        # donc la mutation posee sur le module SOURCE ne les atteignait plus -- le probe rendait
        # `port_sans_gate_draws = 0` et le test disait << la mutation n'a pas mordu >>. C'est le
        # gisement de #484, cote LIVE (que sa tranche avait explicitement laisse non couvert).
        # `substituer_partout` substitue le foyer ET tous ses consommateurs, DERIVES de
        # `sys.modules` -- pas une liste ecrite a la main, qui se perimerait au prochain.
        # #429-r1-r3-r1 : il faut desormais retirer LES DEUX -- retirer le seul gate d'operation
        # laisse le gate de message refuser (cf. 3ter), et la contre-epreuve rendrait `None`. Ce
        # n'est PAS un affaiblissement : la garantie du gate d'OPERATION sur cette porte est
        # RE-ASSERTEE a son etage par l'etape 3ter, et sur la porte DECLENCHEE (qui n'a jamais eu
        # de gate de message) par `port_op_directe_sans_gate_total` ci-dessous.
        st2 = load_state(dv, ob0, snap)
        if isinstance(bg, dict) and "tiles" in bg:
            st2.board = Board(bg["tiles"], adjacency="native_sym")
        mti1 = _cale(st2)
        import engine.runner.operations.active_ability as OA        # noqa: PLC0415
        with substituer_partout(OA, "is_dead_unit_and_not_allowed_by_ability",
                                lambda *_a, **_k: False), \
             substituer_partout(C, "is_alive_and_not_fled", lambda *_a, **_k: True):
            r2 = Runner(st2).install_default_handlers(20)
            r2.apply(AttackUnitMessage(att, prime))
            last2 = r2.damage_handler.last if hasattr(r2, "damage_handler") else None
            res["port_sans_gate_last"] = last2
            res["port_sans_gate_total"] = None if not isinstance(last2, dict) else last2.get("total")
            res["port_sans_gate_draws"] = (None if mti1 is None else
                                           (st2.rng.mti - mti1 + (624 if st2.rng.mti < mti1 else 0)))
            # meme contre-epreuve pour la porte DECLENCHEE : sans le gate, l'operation NUE frappait
            # aussi le cadavre -- c'est la mesure du trou que le rang MESSAGE aurait laisse ouvert.
            # Elle est INSENSIBLE au gate de message (elle n'emprunte aucun visiteur) : c'est ce
            # qui la garde probante pour le gate d'OPERATION, tout seul.
            st4 = load_state(dv, ob0, snap)
            if isinstance(bg, dict) and "tiles" in bg:
                st4.board = Board(bg["tiles"], adjacency="native_sym")
            _cale(st4)
            _op2 = AttackDamageOperation.execute(st4, att, prime)
            res["port_op_directe_sans_gate_total"] = (None if not isinstance(_op2, dict)
                                                      else _op2.get("total"))
        res["why"] = ""
    finally:
        try:
            rpc(s, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:                                          # noqa: BLE001
            pass
    if verbose:
        for k in sorted(res):
            print("  %-26s %s" % (k, res[k]))
    return res


def volet_live(state_file: str, seed: str, board: str) -> int:
    r = scenario_live(state_file, seed, board)
    if r.get("why"):
        print("MONTAGE NON INSTALLE : %s" % r["why"])
        return 2
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--volet", choices=("portes", "gate", "live"), default="portes")
    ap.add_argument("--check", action="store_true", help="volet `portes` : contre-epreuve")
    ap.add_argument("--state-file", default=None, help="chemin ABSOLU, hors data/")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args()
    if a.volet == "portes":
        return volet_portes(a.check)
    if a.volet == "gate":
        return volet_gate()
    if not a.state_file:
        print("--state-file (ABSOLU) requis pour ce volet")
        return 2
    return volet_live(a.state_file, a.seed, a.board)


if __name__ == "__main__":
    raise SystemExit(main())
