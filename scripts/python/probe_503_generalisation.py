"""probe_503_generalisation -- ADVERSARIAL sur le port de `1141 OverwhelmingWrath` (#503).

`probe_503_overwhelming_wrath.py` mesure UN montage. Celui-ci cherche a le CASSER : chaque regime
ci-dessous est choisi pour qu'un port PLAUSIBLE-MAIS-FAUX y diverge, la ou le montage nominal
resterait vert.

  G1  ZERO ennemi adjacent      -- le selecteur `NormalUnits(AdjacentEnemies(Owner))` est VIDE. Un
                                   port qui rabattrait « pas de cible -> pose sur la cible du
                                   message » (ou qui ferait tomber la chaine `op_Addition` sur un
                                   `AddEffect` sans cible) poserait un taunt fantome, ou perdrait
                                   les DEUX effets suivants. Attendu : 1301 + 1300 sur le caster,
                                   AUCUN 27 nulle part.
                                   ⚠ CE REGIME EST NATIVEMENT INATTEIGNABLE, et c'est une MESURE :
                                   sans ennemi adjacent le natif REFUSE le cast, et il le refuse
                                   sur `AddCasterIfAtLeastOneTarget` (0x800) -- mesure
                                   `abilityReason(caster, 1141, caster)`. `isSelfCasting = 1` ne
                                   veut donc PAS dire « castable a vide » : le caster n'entre dans
                                   `fromHere` que s'il existe au moins une AUTRE cible legale.
                                   L'ecart de GATE qui en resulte cote port (0 au lieu de 0x800)
                                   est le residu ANTERIEUR #447 -- la branche `else` de
                                   `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason`
                                   appelle `TargetingQuery$$GetValidTargets`, qui n'est pas porte
                                   (cf. la docstring de `get_caster_not_added_reason`, qui NOMME
                                   deja cet ecart et le mesure sur 1226 Chronometron). G1 le
                                   re-mesure sur un DEUXIEME porteur, et verifie que l'ARBRE, lui,
                                   est correct sur un selecteur vide.
  G2  cast sur SOI-MEME         -- `isSelfCasting = 1` : `fromHere` contient le CASTER. L'arbre ne
                                   lit `Target()` NULLE PART (les trois feuilles visent `Caster` /
                                   `Owner`), donc l'empreinte doit etre STRICTEMENT la meme que sur
                                   un cast dirige vers un ennemi adjacent. Un port qui aurait
                                   glisse `Target()` quelque part diverge ICI et nulle part ailleurs.
  G3  ALLIE adjacent au caster  -- `AdjacentEnemies` prend sa reference d'equipe sur son PREMIER
                                   argument (`Owner`), pas sur un caster implicite. Un allie colle
                                   au caster ne doit PAS etre taunte.
  G4  crit ET block FORCES a 100 -- `--crit 100,700 --block-target 100,500 --block-player 100,500`.
                                   Les deux autres mecaniques annoncees par le kit (`crit`, `block`)
                                   sont-elles atteignables depuis ce behaviour ? Critere : le cast
                                   reste a ZERO degat ET le flux MT reste STRICTEMENT identique
                                   (un jet de crit ou de block CONSOMME un tirage). C'est une
                                   MESURE d'inatteignabilite, pas une supposition.
  G5  autre BOARD               -- « une amplitude ne s'estime pas depuis UN board ». Le montage
                                   nominal tourne sur MC1_67 ; on rejoue G-nominal ailleurs.
  G6  Steppable / Object        -- le filtre `IsNormalUnit` de `NormalUnits`. **OFFLINE PUR, et
                                   c'est DIT** : aucun porteur `Steppable`/`Object` n'est spawnable
                                   comme ENNEMI par `rl_duel build` (les 24 porteurs du gameconfig
                                   sont des `npc` LootObj/powup et deux summons, `genesSmnDecoy` et
                                   `astarSmnHaywireMine`, qui n'arrivent que par le cast de leur
                                   invocateur). On grefe donc le trait sur l'etat CHARGE et on
                                   verifie que l'arbre l'exclut -- sans oracle natif. NON CONFRONTE.

Sortie ASCII stricte (console cp1252). Ecrit sous `logs/`, jamais `data/` (#349).

Usage:
    python probe_503_generalisation.py
"""
from __future__ import annotations

import probe_503_overwhelming_wrath as P

OVERWHELMING_WRATH = P.OVERWHELMING_WRATH
TAUNTED = P.TAUNTED
OW_PENDING_ATTACK = P.OW_PENDING_ATTACK
OW_RANGE_DMG_REDUCTION = P.OW_RANGE_DMG_REDUCTION

#: Meme contrat de declencheur que le probe nominal (meme fermeture d'import).
DECLENCHEUR = dict(P.DECLENCHEUR,
                   raison="Contre-epreuves ADVERSARIALES du port de 1141 : regimes ou un port "
                          "plausible-mais-faux diverge (selecteur vide, cast sur soi, allie "
                          "adjacent, crit/block forces, autre board, trait Steppable).")


def _cast(sid, rid, caster_id, target_id):
    """Joue le MEME cast des deux cotes et rend `(off_delta, live_delta, hp_ok, rng_ok, diag)`.

    Le MT offline est CALE sur le MT live avant le replay (`seed_offline_rng`) : sans lui un
    `0 degat` offline serait le repli defensif de `damage_ops`, pas une mesure."""
    dec0 = P.decision(sid, rid)
    dump_pre = P.rng_dump(sid, rid)
    state, _ = P.load(sid, rid)
    P.seed_offline_rng(state, dump_pre)
    off_hp0, off_f0 = P.hp_off(state), P.footprint_off(state)
    rng0 = state.rng.call_count
    from engine.runner.operations.summon_ai import _apply_active_ability
    res = _apply_active_ability(state, caster_id, target_id, OVERWHELMING_WRATH) or {}
    off = P.delta(off_f0, P.footprint_off(state))
    off_hp1, rng1 = P.hp_off(state), state.rng.call_count

    live_f0, live_hp0 = P.footprint_live(dec0), P.hp_live(sid, rid)
    act = P.rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster_id, "abilityType": OVERWHELMING_WRATH,
        "targetId": target_id}}, 90) or {}
    act0 = (act.get("actions") or [{}])[0]
    live = P.delta(live_f0, P.footprint_live(P.decision(sid, rid)))
    live_hp1 = P.hp_live(sid, rid)
    rng_live = (P.rng_key(dump_pre), P.rng_key(P.rng_dump(sid, rid)))

    hp_ok = (all(off_hp1.get(k) == v for k, v in off_hp0.items())
             and all(live_hp1.get(k) == v for k, v in live_hp0.items()))
    rng_ok = (rng0 == rng1) and (rng_live[0] == rng_live[1])
    return off, live, hp_ok, rng_ok, {"ported": (res.get("diag") or {}).get("ported"),
                                      "error": act0.get("error"),
                                      "rng_off": (rng0, rng1), "rng_live": rng_live}


def _run(sid, nom, args, state_name, choix_cible, extra=None):
    """Monte un runner, resout les unites, joue le cast, rend le dict de mesure. `choix_cible` est
    une fonction `(dec, ids, fromHere) -> target_id` ; `extra` une lecture AVANT cast."""
    path = P.LOGS / ("%s.json" % state_name)
    rid = P.build(path, args)
    try:
        dec = P.decision(sid, rid)
        ids = {u.get("visualId"): int(u["id"]) for u in (dec.get("units") or [])}
        if "worldEightbound" not in ids:
            raise AssertionError("SCENARIO NON MONTE (%s) : Azkor absent -- unites=%s"
                                 % (nom, sorted(ids)))
        caster_id = ids["worldEightbound"]
        at = P.rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": caster_id,
                                           "abilityType": OVERWHELMING_WRATH}, 90) or {}
        row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster_id), None)
        ab = next((a for a in ((row or {}).get("abilities") or [])
                   if int(a.get("abilityId", -1)) == OVERWHELMING_WRATH), {})
        from_here = [int(t.get("targetId")) for t in (ab.get("fromHere") or [])]
        target_id = choix_cible(dec, ids, from_here)
        sup = extra(sid, rid, dec, ids) if extra is not None else {}
        off, live, hp_ok, rng_ok, diag = _cast(sid, rid, caster_id, target_id)
        return {"nom": nom, "rid": rid, "ids": ids, "caster": caster_id, "target": target_id,
                "from_here": from_here, "off": off, "live": live, "hp_ok": hp_ok,
                "rng_ok": rng_ok, "diag": diag, "extra": sup,
                "pos": {u.get("visualId"): (u["pos"]["col"], u["pos"]["row"])
                        for u in (dec.get("units") or []) if u.get("pos")}}
    finally:
        P.rpc(sid, "disposeRunner", {"runnerId": rid}, 20)   # MES runners, jamais ceux des autres


def _porteurs(f):
    return {int(k): sorted(int(x) for x in v) for k, v in f.items()}


def g6_offline(sid) -> dict:
    """G6 -- le filtre `IsNormalUnit` de `NormalUnits`, OFFLINE PUR (aucun oracle natif : cf.
    l'en-tete). On charge un etat REEL (deux ennemis adjacents), on GREFFE le trait `Steppable` sur
    l'un des deux via le canal `ctx.has_trait` du port -- le MEME que lit `UnitsWithoutTrait` --,
    puis on rejoue l'arbre : l'unite greffee doit DISPARAITRE des cibles du taunt."""
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.runner.operations.summon_ai import _apply_active_ability
    path = P.LOGS / ("probe_503_g6.json")
    rid = P.build(path, [
        "--seed", "777", "--board", P.BOARD,
        "--p-units", "worldEightbound,worldExecutions",
        "--a-units", "orksNob,orksRuntherd,bloodMephiston",
        "--place", "worldEightbound:3,4", "--place", "worldExecutions:4,5",
        "--a-place", "orksNob:3,5", "--a-place", "orksRuntherd:2,4",
        "--a-place", "bloodMephiston:1,4"])
    try:
        dec = P.decision(sid, rid)
        ids = {u.get("visualId"): int(u["id"]) for u in (dec.get("units") or [])}
        caster_id, greffe = ids["worldEightbound"], ids["orksNob"]
        out = {}
        for etiquette, trait in (("temoin (aucun trait)", None),
                                 ("Steppable", UnitTrait.Steppable),
                                 ("Object", UnitTrait.Object)):
            state, _ = P.load(sid, rid)
            P.seed_offline_rng(state, P.rng_dump(sid, rid))
            if trait is not None:
                # Le trait est greffe sur le SUBSTRAT que lisent les selecteurs de trait du port
                # (`ctx.has_trait`, cf. `UnitsWithoutTrait` / `NormalUnits`).
                from engine.runner.components import StatsComponent
                ent = state.get_entity(greffe)
                ctx = ent.get_component(StatsComponent).ctx
                ctx.traits = list(getattr(ctx, "traits", None) or []) + [trait.name]
            f0 = P.footprint_off(state)
            _apply_active_ability(state, caster_id, ids["orksRuntherd"], OVERWHELMING_WRATH)
            d = P.delta(f0, P.footprint_off(state))
            out[etiquette] = sorted(int(u) for u, effs in d.items() if TAUNTED in effs)
        return out
    finally:
        P.rpc(sid, "disposeRunner", {"runnerId": rid}, 20)


NOMINAL = ["--seed", "777",
           "--p-units", "worldEightbound,worldExecutions",
           "--a-units", "orksNob,orksRuntherd,bloodMephiston",
           "--place", "worldEightbound:3,4", "--place", "worldExecutions:4,5",
           "--a-place", "orksNob:3,5", "--a-place", "orksRuntherd:2,4",
           "--a-place", "bloodMephiston:1,4"]


def main() -> int:
    sid = P._session()
    verdicts = {}

    # ---- G1 : ZERO ennemi adjacent (les trois ennemis loin du caster) --------------------
    g1 = _run(sid, "G1 selecteur VIDE",
              ["--board", P.BOARD, "--seed", "777",
               "--p-units", "worldEightbound,worldExecutions",
               "--a-units", "orksNob,orksRuntherd,bloodMephiston",
               "--place", "worldEightbound:6,0", "--place", "worldExecutions:6,1",
               "--a-place", "orksNob:0,7", "--a-place", "orksRuntherd:0,6",
               "--a-place", "bloodMephiston:1,7"],
              "probe_503_g1", lambda dec, ids, fh: ids["worldEightbound"],
              extra=lambda sid_, rid_, dec_, ids_: {
                  "reason_self": P.reason_live(sid_, rid_, ids_["worldEightbound"],
                                               ids_["worldEightbound"], OVERWHELMING_WRATH)})
    print("\n[G1] ZERO ennemi adjacent -- le selecteur du taunt est VIDE")
    print("     fromHere=%s  (VIDE : `isSelfCasting` n'ajoute le caster que s'il existe une AUTRE "
          "cible)" % g1["from_here"])
    print("     natif : abilityReason(caster -> caster) = 0x%x  (0x800 = "
          "AddCasterIfAtLeastOneTarget attendu)" % g1["extra"]["reason_self"])
    print("     port  = %s" % g1["off"])
    print("     natif = %s   (le cast est REFUSE : aucun effet)" % g1["live"])
    attendu_g1 = {g1["caster"]: [OW_PENDING_ATTACK, OW_RANGE_DMG_REDUCTION]}
    # (a) le NATIF refuse, et sur la regle attendue ; (b) l'ARBRE du port, joue quand meme, ne
    # fabrique AUCUN taunt fantome et ne perd AUCUNE des deux poses self.
    ok_g1_natif = (g1["extra"]["reason_self"] == 0x800 and g1["live"] == {})
    ok_g1_arbre = (_porteurs(g1["off"]) == attendu_g1 and g1["hp_ok"] and g1["rng_ok"]
                   and g1["diag"]["ported"] is True)
    ok_g1 = ok_g1_natif and ok_g1_arbre
    print("     -> natif refuse sur 0x800 : %s | arbre port sur selecteur VIDE : %s (attendu %s, "
          "aucun 27 nulle part)" % ("OK" if ok_g1_natif else "KO",
                                    "OK" if ok_g1_arbre else "KO", attendu_g1))
    print("     ECART NOMME (residu ANTERIEUR #447, PAS de cette tranche) : le port rend 0 la ou le "
          "natif rend 0x800 -- la branche `else` de `GetCasterNotAddedReason` appelle "
          "`TargetingQuery$$GetValidTargets`, non porte. Degradation PERMISSIVE.")
    verdicts["G1 selecteur vide"] = ok_g1

    # ---- G2 : cast sur SOI vs cast sur un ENNEMI adjacent, memes montages ----------------
    g2a = _run(sid, "G2a cible = ennemi", ["--board", P.BOARD] + NOMINAL, "probe_503_g2a",
               lambda dec, ids, fh: ids["orksNob"])
    g2b = _run(sid, "G2b cible = SOI", ["--board", P.BOARD] + NOMINAL, "probe_503_g2b",
               lambda dec, ids, fh: ids["worldEightbound"])
    print("\n[G2] L'arbre ne lit PAS `Target()` -- cast sur un ENNEMI vs cast sur SOI")
    print("     cible=ennemi : port=%s natif=%s" % (g2a["off"], g2a["live"]))
    print("     cible=SOI    : port=%s natif=%s" % (g2b["off"], g2b["live"]))
    ok_g2 = (g2a["off"] == g2a["live"] and g2b["off"] == g2b["live"]
             and g2a["off"] == g2b["off"] and g2a["live"] == g2b["live"]
             and len(_porteurs(g2a["off"])) == 3)      # anti-degenerescence : 3 porteurs
    print("     -> %s (les DEUX empreintes doivent etre IDENTIQUES, et non vides)"
          % ("OK" if ok_g2 else "KO"))
    verdicts["G2 cible non lue"] = ok_g2

    # ---- G3 : ALLIE adjacent au caster ---------------------------------------------------
    g3 = _run(sid, "G3 allie adjacent",
              ["--board", P.BOARD, "--seed", "777",
               "--p-units", "worldEightbound,worldExecutions",
               "--a-units", "orksNob,orksRuntherd,bloodMephiston",
               # `worldExecutions` en (4,4) : ADJACENT au caster (3,4) -- et il ne doit PAS etre
               # taunte. `orksNob` (3,5) reste le temoin non-nul.
               "--place", "worldEightbound:3,4", "--place", "worldExecutions:4,4",
               "--a-place", "orksNob:3,5", "--a-place", "orksRuntherd:2,4",
               "--a-place", "bloodMephiston:1,4"],
              "probe_503_g3", lambda dec, ids, fh: ids["orksNob"])
    print("\n[G3] ALLIE ADJACENT -- `AdjacentEnemies` prend sa reference d'equipe sur son 1er "
          "argument")
    print("     port  = %s" % g3["off"])
    print("     natif = %s" % g3["live"])
    tauntes = sorted(int(u) for u, e in g3["off"].items() if TAUNTED in e)
    attendu_g3 = sorted([g3["ids"]["orksNob"], g3["ids"]["orksRuntherd"]])
    ok_g3 = (g3["off"] == g3["live"] and tauntes == attendu_g3
             and g3["ids"]["worldExecutions"] not in tauntes)
    print("     tauntes=%s attendu=%s (l'allie u%d ADJACENT doit etre EPARGNE) -> %s"
          % (tauntes, attendu_g3, g3["ids"]["worldExecutions"], "OK" if ok_g3 else "KO"))
    verdicts["G3 allie epargne"] = ok_g3

    # ---- G4 : crit et block FORCES a 100 -------------------------------------------------
    g4 = _run(sid, "G4 crit+block forces",
              ["--board", P.BOARD] + NOMINAL
              + ["--crit", "100,700", "--crit-target", "100,700",
                 "--block-target", "100,500", "--block-player", "100,500"],
              "probe_503_g4", lambda dec, ids, fh: ids["orksNob"])
    print("\n[G4] CRIT ET BLOCK FORCES A 100 -- les deux autres mecaniques du kit sont-elles "
          "atteignables ?")
    print("     port  = %s" % g4["off"])
    print("     natif = %s" % g4["live"])
    print("     HP inchanges = %s | MT inchange = %s (off %s, live %s)"
          % (g4["hp_ok"], g4["rng_ok"], g4["diag"]["rng_off"], g4["diag"]["rng_live"]))
    ok_g4 = g4["off"] == g4["live"] and g4["hp_ok"] and g4["rng_ok"]
    print("     -> %s : `crit` et `block` sont STRUCTURELLEMENT INATTEIGNABLES depuis "
          "`ExecuteBehaviour` (0 coup, 0 tirage), et c'est MESURE" % ("OK" if ok_g4 else "KO"))
    verdicts["G4 crit/block inatteignables"] = ok_g4

    # ---- G5 : autre BOARD ----------------------------------------------------------------
    # Les coordonnees du montage nominal ne sont pas jouables sur TOUS les boards (eau, blocs,
    # elevation). On essaie une liste DETERMINISTE et on retient le PREMIER board ou les cinq
    # unites atterrissent sur les tuiles demandees ET ou les deux ennemis sont adjacents : c'est
    # « driver la configuration », pas la subir. Un echec sur TOUS = regime NON MONTE, et on le dit.
    g5, autre_board = None, None
    for cand in ("C1_02", "C1_14", "C1_21", "C1_25", "C1_35", "C1_38", "C5_19", "C1_74"):
        try:
            essai = _run(sid, "G5 autre board", ["--board", cand] + NOMINAL, "probe_503_g5",
                         lambda dec, ids, fh: ids["orksNob"])
        except AssertionError:
            continue
        tauntes = sorted(int(u) for u, e in essai["off"].items() if TAUNTED in e)
        if len(tauntes) == 2:
            g5, autre_board = essai, cand
            break
    print("\n[G5] AUTRE BOARD -- une amplitude ne s'estime pas depuis UN board")
    if g5 is None:
        print("     REGIME NON MONTE : aucun board candidat ne place les 5 unites avec DEUX "
              "ennemis adjacents. On ne conclut RIEN.")
        ok_g5 = None
    else:
        print("     board=%s positions=%s" % (autre_board, g5["pos"]))
        print("     port  = %s" % g5["off"])
        print("     natif = %s" % g5["live"])
        ok_g5 = (g5["off"] == g5["live"] and len(_porteurs(g5["off"])) == 3
                 and g5["diag"]["ported"] is True and not g5["diag"]["error"])
        print("     -> %s" % ("OK" if ok_g5 else "KO"))
    verdicts["G5 autre board"] = ok_g5

    # ---- G6 : Steppable / Object (OFFLINE PUR, sans oracle natif) ------------------------
    g6 = g6_offline(sid)
    print("\n[G6] FILTRE `IsNormalUnit` de `NormalUnits` -- OFFLINE PUR, AUCUN ORACLE NATIF")
    for k, v in g6.items():
        print("     %-22s -> tauntes = %s" % (k, v))
    temoin = g6["temoin (aucun trait)"]
    ok_g6 = (len(temoin) == 2
             and len(g6["Steppable"]) == 1 and len(g6["Object"]) == 1
             and set(g6["Steppable"]) < set(temoin) and set(g6["Object"]) < set(temoin))
    print("     -> %s (le porteur greffe DOIT sortir du set ; NON CONFRONTE au natif -- aucun "
          "porteur Steppable/Object n'est spawnable comme ennemi)" % ("OK" if ok_g6 else "KO"))
    verdicts["G6 Steppable/Object (offline)"] = ok_g6

    rouges = [k for k, v in verdicts.items() if v is False]
    muets = [k for k, v in verdicts.items() if v is None]
    print("\nVERDICTS : %s" % {k: ("OK" if v else ("NON MESURE" if v is None else "KO"))
                               for k, v in verdicts.items()})
    if muets:
        print("NON MESURE : %s" % ", ".join(muets))
    print("NON COUVERT : G6 n'a AUCUN oracle natif (offline pur, cf. l'en-tete) ; le regime "
          "« cast LEGAL avec taunt VIDE » est NATIVEMENT INATTEIGNABLE (cf. G1).")
    print("PROBE OK" if not rouges else "PROBE KO -- %s" % ", ".join(rouges))
    return 0 if not rouges else 1


if __name__ == "__main__":
    raise SystemExit(main())
