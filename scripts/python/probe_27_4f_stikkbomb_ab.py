"""probe #27-4f -- A/B causal LIVE de Stikkbomb (1051) : la PENALITE DE TIR AMI de
`IdunBattle.AI.Playbook.Loki.StikkbombPlaybook$$CalculateCustomUtility`.

Le terme natif vaut `- Somme( CalculateUtilityFromDamageEvent(p) )` sur les predictions generees
pour chaque AMI du caster adjacent a la CIBLE. Comme le 4e argument passe a
`...ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions` est la CIBLE PRINCIPALE (et non
l'ami itere -- lu au decompile puis a l'assembleur, cf. `prediction.make_stikkbomb_splash_event`),
chaque ami produit le MEME event : `custom = -n x U(1 coup = nrOfHits_2 sur la cible)`.

MONTAGE (board MC1_67, seed 909, stats naturelles) :
  caster en (3,4) ; DEUX cibles a distance 2, distantes de 4 l'une de l'autre :
    T_high = la cible dont `pairUtility(1051)` NATIVE est la plus FORTE -- elle recoit les amis
    T_low  = l'autre, laissee intacte
  appats AMIS : (2,6) et (4,6) -- voisins de T_high, a distance 3 du caster et 5 de T_low : ils ne
  changent l'adjacence d'AUCUNE autre entite du montage, et ils sont AMIS donc n'ajoutent AUCUN
  event de prediction (seuls les ENNEMIS adjacents en ajoutent, cf. `StikkbombPlaybook$$MakeDamage-
  Predictions`). Consequence VERIFIEE dans le probe : les 4 `pairUtility` natives sont
  BIT-IDENTIQUES entre n=0, n=1 et n=2 -> confond de prediction MESURE et NUL.

  L'ecart natif `pair(1051,T_high) - pair(1051,T_low)` doit tomber dans (U1, 2xU1) :
    n=0 ami -> le natif cible T_high
    n=1 ami -> -U1 ne suffit pas -> le natif cible ENCORE T_high
    n=2 amis-> -2xU1 suffit       -> le natif bascule sur T_low
  => la FORME LINEAIRE est mesuree : un terme BOOLEEN (« au moins un ami adjacent ») donnerait le
  MEME resultat a n=1 et n=2, donc ne basculerait JAMAIS ici.

CONTROLES :
  - `ally-far`  : les deux amis reviennent LOIN -> retour a T_high (le terme est bien positionnel).
  - `foe`       : un ENNEMI prend la place d'un ami adjacent a T_high. Il ne compte PAS dans le
                  custom (`IsFriend` faux) mais il AJOUTE un event de prediction -> `pairUtility`
                  (1051, T_high) doit AUGMENTER. C'est l'autre moitie du meme artefact natif.
  - custom force a 0 -> le moteur doit DIVERGER du natif au bras n=2.
  - playbook RETIRE du registre -> le moteur doit DIVERGER du natif au bras n=2.

PORTEUR : les deux seuls porteurs de 1051 sont `orksOrkBoys` (SUMMON de `Waaagh`/orksWarboss) et
`orksNpc2OrkBoy` (npc). Le summon EST amenable en bataille par son summoner -- MESURE (runner 189,
tours 1 a 3) : il apparait bien dans l'equipe avec `Stikkbomb(1051) [pret]`, mais il **n'entre
jamais dans la liste « A ACTIVER »** du harnais arene et `aiDryRunAllUnits` ne rend pour lui que
`FinishUnitTurnMessage` (puis l'IA adverse le tue au premier tour). Pas de verite de reference par
cette voie -> GREFFE de l'ability sur une unite DU POOL (recette `case-92` §5bis) : `orksRuntherd`
(Orks, arme MELEE `Physical` -- voir le commentaire de `GRAFT_HOST` pour pourquoi le greffon doit
etre melee ET l'armure des cibles relevee).
Ce que la greffe ne couvre pas est nomme dans `case-27` §Non couvert.

Usage :
    python probe_27_4f_stikkbomb_ab.py --build [--engine]
    python probe_27_4f_stikkbomb_ab.py --engine       # re-joue sur le runner du state-file
ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import probe_27_3_live as L

HERE = Path(__file__).resolve().parent
LOGS = HERE.parents[1] / "logs"
SEED_BC = LOGS / "bc_stikkbomb_graft.json"
STATE = LOGS / "rs_stikk_ab.json"
BOARD = "MC1_67"
SEED = 909
ABILITY = 1051
# Greffon MELEE a arme `Physical` (PiercingRatio 1) : a distance 2 son attaque normale n'est pas
# disponible sans se deplacer, et l'armure des cibles (`--armor-target`) l'ecrase — la ou Stikkbomb
# est `Blast` (PiercingRatio 15). Sans ce reglage le natif joue TOUJOURS la normale et le probe ne
# mesure RIEN (mesure du 2026-07-30 avec `orksKillaKan`, arme Projectile r3 : pair69 = 59.94 contre
# pair1051 = 28.88 sur la meme cible, ability 1051 jamais emise).
GRAFT_HOST = "orksRuntherd"
ARMOR_TARGET = 3000

# ids stables du montage. ⚠ le runner numerote la team ADVERSE d'abord (verifie live :
# 77/79/81 = a-units, 83/85/87/89 = p-units) — l'ordre `p-units puis a-units` de la ligne de
# commande n'est PAS l'ordre des ids.
E1 = 77              # astraOrdnance
E2 = 79              # necroWarden
E3 = 81              # ultraCalgar  (spare, reste loin ; sert au bras `foe`)
CASTER = 83          # <GRAFT_HOST>  (greffe : ActiveAbilities = [1051])
ALLY1 = 85           # orksNob
ALLY2 = 87           # orksKillaKan
ALLY3 = 89           # orksBigMek

POS_CASTER = "3,4"
POS_T1, POS_T2 = "3,6", "3,2"          # les deux cibles a distance 2 du caster (d(T1,T2) = 4)
# Tuiles d'appat, par CIBLE. Voisins de (3,6) : d(caster)=3, d(3,2)=5. Voisins de (3,2) retenus :
# d(caster)=3, d(3,6)=5. Aucune ne change l'adjacence d'une autre entite du montage.
ADJ_OF = {POS_T1: ("2,6", "4,6"), POS_T2: ("2,1", "4,1")}
FAR = ("0,0", "1,0", "0,1", "6,0")     # tuiles de parking, loin de tout


def _run(args) -> None:
    subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(HERE),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _runner_id() -> int:
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def _move(rid: int, unit: int, to: str) -> None:
    _run(["act", "move", "--unit", str(unit), "--to", to,
          "--state-file", str(STATE), "--runner", str(rid)])


def write_graft() -> None:
    """GREFFE (`case-92` §5bis) : dans une COPIE du seed BC, l'entree `BC.Units` du greffon ne porte
    plus que l'ability visee. Le natif charge le playbook PAR ABILITY
    (`PlaybookDatabase.LoadPlaybook(abilityType)`) : le code exerce est donc bien
    `StikkbombPlaybook`, ce que le natif PROUVE en emettant `ActiveAbilityMessage(1051)`."""
    import rl_collect_batch as R
    bc = R._load_seed_bc(None)
    hit = 0
    for u in bc.get("Units") or []:
        if u.get("Id") == GRAFT_HOST:
            u["ActiveAbilities"] = [ABILITY]
            hit += 1
    if hit != 1:
        raise SystemExit("greffe impossible : %d entree(s) '%s' dans le seed BC" % (hit, GRAFT_HOST))
    LOGS.mkdir(parents=True, exist_ok=True)
    SEED_BC.write_text(json.dumps(bc), encoding="utf-8")


def _positions(rid: int) -> dict:
    dv = L._rpc("decisionView", [{"runnerId": rid, "allAbilities": True}])
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("id")] = (p.get("col"), p.get("row"))
    return out


def _assert_placed(rid: int, want) -> None:
    """Un `act move` REFUSE (tuile occupee/injouable) ne leve rien : le montage se degraderait
    SILENCIEUSEMENT en trois bras identiques, ou l'accord natif<->moteur est trivialement vrai."""
    pos = _positions(rid)
    bad = [(u, to, pos.get(u)) for u, to in want
           if pos.get(u) != tuple(int(x) for x in to.split(","))]
    if bad:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %s"
                         % ["u%s voulu=%s obtenu=%s" % (u, to, got) for u, to, got in bad])


def build() -> int:
    write_graft()
    _run(["build", "--seed", str(SEED), "--board", BOARD, "--seed-bc", str(SEED_BC),
          "--p-units", "%s,orksNob,orksKillaKan,orksBigMek" % GRAFT_HOST,
          "--a-units", "astraOrdnance,necroWarden,ultraCalgar",
          "--armor-target", str(ARMOR_TARGET),
          "--state-file", str(STATE)])
    rid = _runner_id()
    want = ((CASTER, POS_CASTER), (E1, POS_T1), (E2, POS_T2),
            (ALLY1, FAR[0]), (ALLY2, FAR[1]), (ALLY3, FAR[2]), (E3, FAR[3]))
    # Un `act move` vers une tuile encore OCCUPEE est refuse silencieusement : on repasse la liste
    # jusqu'a ce que les occupations se resorbent (3 passes suffisent, `_assert_placed` tranche).
    for _ in range(3):
        for unit, to in want:
            _move(rid, unit, to)
    _assert_placed(rid, want)
    return rid


def _native(rid: int, t_high: int, t_low: int) -> tuple[dict, tuple, list]:
    pairs = {}
    # E3 est mesure AUSSI : au bras `foe` il devient le VOISIN de T_high, et c'est en comparant
    # l'utilite AJOUTEE a `pair(1051, T_high)/2` plutot qu'a `pair(1051, E3)/2` qu'on tranche
    # « l'event splash porte sur la CIBLE, pas sur le voisin ».
    for tgt in (t_low, t_high, E3):
        for ab in (69, ABILITY):
            r = L._rpc("pairUtility", [{"runnerId": rid, "unitId": CASTER,
                                        "targetId": tgt, "abilityType": ab}])
            pairs[(ab, tgt)] = r.get("utility")
    dr = L._rpc("aiDryRunAllUnits", [{"runnerId": rid}])
    chosen, msgs = (None, None), []
    for u in (dr.get("units") or []):
        if u.get("unitId") != CASTER:
            continue
        msgs = u.get("proposed") or []
        for m in msgs:
            if m.get("cls") == "ActiveAbilityMessage":
                chosen = (m.get("abilityType"), m.get("targetId"))
    return pairs, chosen, msgs


def _engine(rid: int, t_high: int, t_low: int) -> dict:
    """Decision MOTEUR : (a) telle quelle, (b) custom 1051 FORCE a 0, (c) playbook RETIRE du
    registre. (b) et (c) sont les deux contre-epreuves de NECESSITE."""
    import engine_validate as EV
    import engine.playbook as PB
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX

    sid = L.INV._session_id()
    rpc = lambda m, b, t: EV._r(sid, m, b, t)          # noqa: E731
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)

    ctx = AICTX.build(rpc, rid, dv, mov_by_unit, CASTER, wt, predictor)
    mp = (ctx.me or {}).get("pos") or {}
    here = (mp.get("col"), mp.get("row"))
    pb = PB.REGISTRY.get(ABILITY)
    customs = {t: pb.calculate_custom_utility(ctx, here, t, ABILITY) for t in (t_low, t_high)}
    counts = {t: pb._splash_count(ctx, t, friends=True) for t in (t_low, t_high)}
    foes = {t: pb._splash_count(ctx, t, friends=False) for t in (t_low, t_high)}

    a = EV.engine_decide(sid, rid, dv, mov_by_unit, CASTER, wt, predictor)
    orig = type(pb).calculate_custom_utility
    type(pb).calculate_custom_utility = (lambda self, ctx, tile, target, ability_id: 0.0)
    try:
        b = EV.engine_decide(sid, rid, dv, mov_by_unit, CASTER, wt, predictor)
    finally:
        type(pb).calculate_custom_utility = orig
    saved = PB.REGISTRY.pop(ABILITY, None)
    try:
        c = EV.engine_decide(sid, rid, dv, mov_by_unit, CASTER, wt, predictor)
    finally:
        if saved is not None:
            PB.REGISTRY[ABILITY] = saved
    return {"engine": (a.get("ability"), a.get("target")),
            "engine_c0": (b.get("ability"), b.get("target")),
            "engine_noreg": (c.get("ability"), c.get("target")),
            "customs": customs, "counts": counts, "foes": foes}


def measure(rid: int, label: str, t_high: int, t_low: int, engine: bool) -> dict:
    pos = _positions(rid)
    pairs, chosen, msgs = _native(rid, t_high, t_low)
    print("  --- %s ---" % label)
    print("      positions : caster=%s T_high=%s T_low=%s a1=%s a2=%s a3=%s e3=%s"
          % (pos.get(CASTER), pos.get(t_high), pos.get(t_low), pos.get(ALLY1),
             pos.get(ALLY2), pos.get(ALLY3), pos.get(E3)))
    for tgt, nm in ((t_low, "T_low "), (t_high, "T_high")):
        print("      %s  pair69=%-22r pair%d=%-22r" % (nm, pairs[(69, tgt)], ABILITY,
                                                       pairs[(ABILITY, tgt)]))
    print("      ecart natif pair%d(T_high) - pair%d(T_low) = %.6f"
          % (ABILITY, ABILITY, pairs[(ABILITY, t_high)] - pairs[(ABILITY, t_low)]))
    print("      natif  : ability=%s target=%s  (messages=%s)"
          % (chosen[0], chosen[1], [m.get("cls") for m in msgs]))
    row = {"pairs": pairs, "native": chosen, "pos": pos}
    if engine:
        e = _engine(rid, t_high, t_low)
        print("      moteur : ability=%s target=%s | n_amis(T_high)=%s n_amis(T_low)=%s"
              " n_ennemis(T_high)=%s" % (e["engine"][0], e["engine"][1],
                                          e["counts"][t_high], e["counts"][t_low],
                                          e["foes"][t_high]))
        print("      custom : T_high=%.6f T_low=%.6f" % (e["customs"][t_high], e["customs"][t_low]))
        print("      contre-epreuves : [custom=0] ability=%s target=%s | [hors registre] ability=%s target=%s"
              % (e["engine_c0"][0], e["engine_c0"][1], e["engine_noreg"][0], e["engine_noreg"][1]))
        row.update(e)
    return row


def run_ab(rid: int, engine: bool) -> dict:
    """Les SEPT bras. `t_high`/`t_low` sont DESIGNES par la mesure native, jamais supposes."""
    p0, _, _ = _native(rid, E1, E2)
    t_high, t_low = (E1, E2) if p0[(ABILITY, E1)] >= p0[(ABILITY, E2)] else (E2, E1)
    print("designation : T_high=u%d (pair=%r) T_low=u%d (pair=%r)"
          % (t_high, p0[(ABILITY, t_high)], t_low, p0[(ABILITY, t_low)]))
    hi, lo = (POS_T1, POS_T2) if t_high == E1 else (POS_T2, POS_T1)
    adj_high, adj_high2 = ADJ_OF[hi]
    adj_low = ADJ_OF[lo][0]

    rows = {"_t": (t_high, t_low)}
    rows["n=0"] = measure(rid, "n=0 ami adjacent a T_high", t_high, t_low, engine)
    _move(rid, ALLY1, adj_high)
    rows["n=1"] = measure(rid, "n=1 ami adjacent a T_high", t_high, t_low, engine)
    _move(rid, ALLY2, adj_high2)
    rows["n=2"] = measure(rid, "n=2 amis adjacents a T_high", t_high, t_low, engine)
    # BRAS DESEQUILIBRES -- c'est EUX qui separent LINEAIRE de BOOLEEN, sans rien recalibrer :
    #   `bal1` = 1 ami sur CHAQUE cible  -> les deux modeles disent T_high (controle) ;
    #   `bal2` = 2 amis sur T_high, 1 sur T_low -> LINEAIRE dit T_low (16.04-2xU1 ~ 0 contre
    #            12.26-U1_low ~ 6.13), BOOLEEN dit T_high (16.04-U1 ~ 8.02 contre 6.13).
    _move(rid, ALLY2, FAR[1])
    _move(rid, ALLY3, adj_low)
    rows["bal1"] = measure(rid, "bal1 : 1 ami sur T_high, 1 ami sur T_low", t_high, t_low, engine)
    _move(rid, ALLY2, adj_high2)
    rows["bal2"] = measure(rid, "bal2 : 2 amis sur T_high, 1 ami sur T_low", t_high, t_low, engine)
    # CONTROLE 1 : tous les amis repartent LOIN -> le natif doit revenir sur T_high.
    _move(rid, ALLY1, FAR[0])
    _move(rid, ALLY2, FAR[1])
    _move(rid, ALLY3, FAR[2])
    rows["ally-far"] = measure(rid, "controle : les 3 amis repartent loin", t_high, t_low, engine)
    # CONTROLE 2 : un ENNEMI prend une tuile adjacente a T_high. Il ne compte PAS dans le custom
    # (`IsFriend` faux) mais il ajoute un event de prediction -> pair(1051, T_high) doit MONTER.
    _move(rid, E3, adj_high)
    rows["foe"] = measure(rid, "controle : 1 ENNEMI adjacent a T_high (pas un ami)",
                          t_high, t_low, engine)
    return rows


def main() -> int:
    argv = sys.argv[1:]
    engine = "--engine" in argv
    rid = build() if "--build" in argv else _runner_id()
    print("runner=%d board=%s seed=%d greffon=%s armor-target=%d"
          % (rid, BOARD, SEED, GRAFT_HOST, ARMOR_TARGET))
    rows = run_ab(rid, engine)
    t_high, t_low = rows["_t"]
    rows = {k: v for k, v in rows.items() if k != "_t"}

    print("\n=== SYNTHESE ===")
    ok = True
    exercised = any(r["native"][0] == ABILITY for r in rows.values())
    for k, want in (("n=0", t_high), ("n=1", t_low), ("n=2", t_low), ("bal1", t_high),
                    ("bal2", t_low), ("ally-far", t_high), ("foe", t_high)):
        got_ab, got_tgt = rows[k]["native"]
        good = (got_tgt == want)
        ok = ok and good
        print("  %-9s : natif -> ability=%s target=%s (attendu target=u%s) %s"
              % (k, got_ab, got_tgt, want, "OK" if good else "MISMATCH"))
        if engine:
            e_ab, e_tgt = rows[k]["engine"]
            agree = (e_ab == got_ab and e_tgt == got_tgt)
            ok = ok and agree
            print("              moteur -> ability=%s target=%s %s"
                  % (e_ab, e_tgt, "MATCH" if agree else "DIVERGE"))
    # EXERCICE : sans un seul bras ou le natif joue REELLEMENT 1051, ce probe ne mesure rien.
    print("  ability 1051 REELLEMENT jouee par le natif dans au moins un bras : %s"
          % ("OUI" if exercised else "NON -- PROBE NON EXERCE"))
    ok = ok and exercised
    # CONFOND DE PREDICTION : les paires natives doivent etre bit-identiques sur n=0/1/2.
    ref = rows["n=0"]["pairs"]
    frozen = all(rows[k]["pairs"] == ref for k in ("n=1", "n=2", "bal1", "bal2", "ally-far"))
    print("  pairUtility natives BIT-IDENTIQUES sur tous les bras AMIS : %s"
          % ("OUI -- confond de prediction NUL" if frozen else "NON -- confond present"))
    ok = ok and frozen
    # LINEARITE : les bras DESEQUILIBRES tranchent. `bal1` (1 ami de chaque cote) doit rester sur
    # T_high pour les DEUX modeles -- c'est le controle qui prouve que `bal2` ne bascule pas pour
    # une raison etrangere. `bal2` (2 amis sur T_high, 1 sur T_low) separe : LINEAIRE -> T_low,
    # BOOLEEN -> T_high.
    lin = (rows["bal1"]["native"][1] == t_high and rows["bal2"]["native"][1] == t_low)
    print("  linearite (bal1 reste T_high, bal2 bascule sur T_low) : %s"
          % ("PROUVEE -- un terme booleen est exclu" if lin else "NON ETABLIE"))
    ok = ok and lin
    # ENCADREMENT de U1(T_high), sans fitting : `n=1` a bascule -> U1 > l'ecart de paire ; `bal1`
    # n'a PAS bascule -> U1(T_high) - U1(T_low) < le meme ecart.
    gap = ref[(ABILITY, t_high)] - ref[(ABILITY, t_low)]
    print("  encadrement (forme -n x U1) : U1(T_high) > %.4f (n=1 bascule)"
          " et U1(T_high) - U1(T_low) < %.4f (bal1 ne bascule pas)" % (gap, gap))
    # Le bras `foe` doit FAIRE MONTER la prediction native (l'autre moitie de l'artefact) — et le
    # SUPPLEMENT tranche sur QUI recoit l'event splash : la CIBLE (`pair(T_high)/2`, nrOfHits_2=1
    # coup contre nrOfHits=2) ou le VOISIN (`pair(E3)/2`). Les deux valeurs sont mesurees.
    up = rows["foe"]["pairs"][(ABILITY, t_high)] > ref[(ABILITY, t_high)]
    add = rows["foe"]["pairs"][(ABILITY, t_high)] - ref[(ABILITY, t_high)]
    half_tgt = ref[(ABILITY, t_high)] / 2.0
    half_foe = ref[(ABILITY, E3)] / 2.0
    print("  bras `foe` : pair%d(T_high) %r -> %r (%s)"
          % (ABILITY, ref[(ABILITY, t_high)], rows["foe"]["pairs"][(ABILITY, t_high)],
             "MONTE -- events splash natifs confirmes" if up else "INCHANGE"))
    print("      supplement = %.4f | moitie de pair(T_high) = %.4f | moitie de pair(voisin u%d) = %.4f"
          % (add, half_tgt, E3, half_foe))
    if up:
        verdict = ("la CIBLE" if abs(add - half_tgt) < abs(add - half_foe) else "le VOISIN")
        print("      => l'event splash porte sur %s" % verdict)
        ok = ok and (verdict == "la CIBLE")
    if engine:
        c0 = rows["n=2"]["engine_c0"][1] == rows["n=2"]["native"][1]
        nr = rows["n=2"]["engine_noreg"][1] == rows["n=2"]["native"][1]
        print("  contre-epreuve [custom force a 0] au bras n=2 : %s"
              % ("DIVERGE du natif -- terme NECESSAIRE" if not c0 else
                 "suit encore le natif -- terme NON demontre necessaire"))
        print("  contre-epreuve [playbook hors registre] au bras n=2 : %s"
              % ("DIVERGE du natif -- port NECESSAIRE" if not nr else
                 "suit encore le natif -- port NON demontre necessaire"))
        ok = ok and (not c0) and (not nr)
    print("(pense a disposer le runner : rl_duel.py dispose --state-file %s)" % STATE)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
