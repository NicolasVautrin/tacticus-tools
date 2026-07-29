"""#264 -- `load_state` CONSOMME-T-IL `combatSnapshot.units[].traits` ?

LE MANQUE (avant #264). Le hook publie depuis `0231573` (#233) l'ensemble EFFECTIF des traits que le
natif considere poses -- l'invoke de `IdunBattle.Entities.UnitExtensions$$HasTrait(unit, trait)` par
valeur d'enum, donc la resultante de
`IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` :

    HasTrait(t) == !retires(+0x50).Contains(t)
                   && ( permanents(+0x40).Contains(t) || temporaires(+0x48).Contains(t) )

`load_state` ne le consommait pas : il RECONSTRUISAIT le substrat depuis `gameconfig.unit(vis).traits`
plus une derivation d'alliance (`GrandAlliance$$GetTrait`). Or le natif ne lit pas le gameconfig : les
traits de depart viennent de `BattleConfiguration.Units[].Traits`, resolus PAR PROGRESSION.

CE QUE MESURE CETTE SONDE (le critere, binaire) : apres `load_state`, l'ensemble de traits que rend
le port (`entity_trait_names`, plus les deux lecteurs qui l'adaptent) est-il EGAL a celui que publie
`combatSnapshot`, sur DEUX montages de rosters differents ?

  0. COUVERTURE D'ENUM -- `dumpEnum(UnitTrait)` live vs le mirror `engine.entities.traits.UnitTrait`.
     C'est la garde de `trait_names_from_ids` : un id publie par le natif et absent du mirror LEVE.
  1. MONTAGE A -- roster ALEATOIRE seede (777 / MC1_67). Egalite pour chaque ligne.
  2. MONTAGE B -- roster EXPLICITE + MoW `ultraDreadnought`, puis cast `DutyEternal` (1158) qui
     SPAWNE `ultraSmnDreadnought` avec un `AddTrait(Stationary)` on-appearance. Egalite + les DEUX
     regimes discriminants dans le meme etat :
       * `necroOverlord` porte `Resilient` au GAMECONFIG et PAS en bataille -> la reconstruction en
         ajoutait un EN TROP (degradation PERMISSIVE : le cap `ApplyResilientTraitDamageLimit`
         rendait l'unite impossible a tuer offline) ;
       * le summon porte `Stationary` accorde EN BATAILLE -> la reconstruction le RATAIT
         (degradation RESTRICTIVE).
  3. NON-VACUITE -- le MEME etat recharge avec le canal EFFACE (`traits: null`, l'etat d'avant #264)
     doit DIVERGER. Sans ce controle, 1 et 2 passeraient a vide.
  4. TRI-ETAT -- `null` n'est PAS `[]`. Canal efface => le port garde sa RECONSTRUCTION intacte
     (`traits_measured` faux) ; `[]` => mesure, le port ecrit un ensemble VIDE.

Usage :  python scripts/python/probe_264_load_state_traits.py
"""
import json
import os
import subprocess
import sys
import urllib.request

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(PYDIR))
LOGS = os.path.join(RACINE, "logs")
sys.path.insert(0, PYDIR)

DUTY_ETERNAL = 1158          # `ultraDreadnought` : Spawn(ultraSmnDreadnought) + AddTrait(Stationary)


def _http(chemin, methode="GET", corps=None, timeout=300):
    req = urllib.request.Request(
        HOST + chemin, method=methode,
        data=None if corps is None else json.dumps(corps).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def rpc(sid, methode, args, timeout=240.0):
    return _http("/api/scripts/%d/rpc" % sid, "POST",
                 {"method": methode, "args": args, "timeout": int(timeout * 1000)},
                 timeout + 20).get("result")


def build(nom, extra):
    """Construit un runner isole ; rend (runnerId, chemin du state-file) ou (None, msg)."""
    etat = os.path.join(LOGS, "_probe264_%s.json" % nom)
    if os.path.exists(etat):
        os.remove(etat)
    os.makedirs(LOGS, exist_ok=True)
    p = subprocess.run([sys.executable, "rl_duel.py", "build", "--state-file", etat, *extra],
                       cwd=PYDIR, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if not os.path.exists(etat):
        return None, (p.stderr or p.stdout or "")[-500:]
    with open(etat, encoding="utf-8") as f:
        return json.load(f)["runnerId"], etat


def capture(sid, rid):
    from engine.runner.snapshot import decision_view_seed_body
    return (rpc(sid, "decisionView", [decision_view_seed_body(rid, allAbilities=True)]),
            rpc(sid, "observeBattle", [{"runnerId": rid}]),
            rpc(sid, "combatSnapshot", [{"runnerId": rid}]))


def confronter(dec, obs, snap, titre):
    """Compare, ligne a ligne, la MESURE au substrat du port charge -- via les TROIS lecteurs.

    Rend `(nb_lignes, ecarts, rate_par_la_reconstruction)`. `ecarts` liste les divergences du port
    SEEDE (doit etre vide) ; `rate_par_la_reconstruction` compte les unites que l'etat d'AVANT #264
    (canal efface) manquait -- c'est la garde de non-vacuite du montage."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent, UnitComponent
    from engine.entities.traits.unit_trait import entity_trait_names, trait_names_from_ids
    from engine.runner.abilities.targeting import _unit_traits
    from engine.runner.abilities.behaviours.context import _unit_dict

    st = load_state(dec, obs, snap)
    snap_efface = {**snap, "units": [{**u, "traits": None} for u in (snap.get("units") or [])]}
    st_avant = load_state(dec, obs, snap_efface)

    ecarts, rates, n = [], 0, 0
    print("\n== %s" % titre)
    for su in (snap.get("units") or []):
        eid = su.get("entityId")
        if eid is None or not isinstance(su.get("traits"), list):
            continue
        n += 1
        mes = trait_names_from_ids(su["traits"])
        ent = st.get_entity(eid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        uc = ent.get_component(UnitComponent) if ent is not None else None
        vis = uc.visual_id if uc is not None else None
        lus = {
            "entity_trait_names": frozenset(entity_trait_names(sc.ctx if sc is not None else None,
                                                               vis)),
            "targeting._unit_traits": frozenset(_unit_traits(st, eid)),
            "behaviours._unit_dict": frozenset((_unit_dict(st, eid) or {}).get("_traits") or ()),
        }
        for nom, val in lus.items():
            if val != mes:
                ecarts.append((eid, vis, nom, sorted(mes - val), sorted(val - mes)))
        ent0 = st_avant.get_entity(eid)
        sc0 = ent0.get_component(StatsComponent) if ent0 is not None else None
        avant = frozenset(entity_trait_names(sc0.ctx if sc0 is not None else None, vis))
        if avant != mes:
            rates += 1
        print("  u%-4s et=%s %-24s mes=%2d  seede=%s  reconstruction_ecart=%r"
              % (eid, su.get("entityType"), str(vis)[:24], len(mes),
                 "OK" if all(v == mes for v in lus.values()) else "DIV",
                 sorted(mes ^ avant)))
    for eid, vis, nom, manque, trop in ecarts:
        print("    ECART u%s %s via %s : MANQUE=%r EN_TROP=%r" % (eid, vis, nom, manque, trop))
    return n, ecarts, rates


def etape_tri_etat(dec, obs, snap):
    """`null` n'est PAS `[]` : canal efface => reconstruction INTACTE ; `[]` => ensemble VIDE."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent, UnitComponent
    from engine.entities.traits.unit_trait import entity_trait_names, unit_trait_names

    cible = next((u.get("entityId") for u in (snap.get("units") or [])
                  if isinstance(u.get("traits"), list) and u.get("traits")), None)
    if cible is None:
        return "NON MESURE"

    def _lire(mut):
        s = {**snap, "units": [({**u, **mut} if u.get("entityId") == cible else u)
                               for u in (snap.get("units") or [])]}
        st = load_state(dec, obs, s)
        e = st.get_entity(cible)
        sc = e.get_component(StatsComponent) if e is not None else None
        uc = e.get_component(UnitComponent) if e is not None else None
        vis = uc.visual_id if uc is not None else None
        return (frozenset(entity_trait_names(sc.ctx if sc is not None else None, vis)),
                bool(getattr(sc.ctx, "traits_measured", False)) if sc is not None else False,
                frozenset(unit_trait_names(vis)))

    nul, m_nul, reconstruit = _lire({"traits": None})
    vide, m_vide, _ = _lire({"traits": []})
    print("  u%s : canal null -> %d traits (mesure=%s, reconstruction=%d) ; canal [] -> %d traits "
          "(mesure=%s)" % (cible, len(nul), m_nul, len(reconstruit), len(vide), m_vide))
    ok = (nul == reconstruit) and (not m_nul) and (vide == frozenset()) and m_vide
    return "OK" if ok else "ECHEC"


def main():
    sid = int((_http("/api/admin/status").get("session") or {}).get("id"))
    print("session=%d" % sid)
    resultats = []

    # --- 0. couverture d'enum ------------------------------------------------------------------
    from engine.entities.traits.unit_trait import UnitTrait
    brut = ((rpc(sid, "dumpEnum", [{"asm": "IdunSharedAssembly.dll",
                                    "ns": "IdunBattle.Entities.Enum",
                                    "cls": "UnitTrait"}], 60) or {}).get("values") or {})
    natif = {}
    for k, v in brut.items():
        natif.setdefault(int(v), []).append(k)
    mirror = {int(t): t.name for t in UnitTrait}
    absents = sorted(v for v in natif if v not in mirror)
    desaccords = [(v, natif[v][0], mirror[v]) for v in sorted(natif)
                  if v in mirror and natif[v][0] not in (mirror[v],) and mirror[v] not in natif[v]]
    print("UnitTrait natif=%d valeurs, mirror=%d ; absentes du mirror=%r ; desaccords de nom=%r"
          % (len(natif), len(mirror), absents, desaccords[:6]))
    resultats.append(("0 couverture enum UnitTrait",
                      "OK" if (natif and not absents and not desaccords) else "ECHEC"))

    runners = []
    try:
        # --- 1. montage A : roster ALEATOIRE seede ---------------------------------------------
        rid, etat = build("a", ["--seed", "777", "--board", "MC1_67"])
        if rid is None:
            print("ECHEC build A: %s" % etat)
            return 3
        runners.append((rid, etat))
        dec, obs, snap = capture(sid, rid)
        n, ecarts, rates = confronter(dec, obs, snap, "MONTAGE A -- seed 777 / MC1_67 (aleatoire)")
        resultats.append(("1 A egalite port == mesure (%d lignes)" % n,
                          "OK" if (n and not ecarts) else "ECHEC"))
        tri = etape_tri_etat(dec, obs, snap)
        resultats.append(("4 tri-etat null != []", tri))

        # --- 2. montage B : roster EXPLICITE + MoW, puis AddTrait en bataille -------------------
        rid_b, etat_b = build("b", ["--seed", "31337", "--board", "MC1_67",
                                    "--p-units", "ultraTitus,ultraApothecary",
                                    "--a-units", "necroOverlord,orksWarboss",
                                    "--p-mow", "ultraDreadnought"])
        if rid_b is None:
            print("ECHEC build B: %s" % etat_b)
            return 3
        runners.append((rid_b, etat_b))
        dec, obs, snap = capture(sid, rid_b)
        n_b0, ec_b0, rates_b0 = confronter(
            dec, obs, snap, "MONTAGE B t0 -- roster explicite + MoW ultraDreadnought")

        # cast DutyEternal : le dreadnought invoque prend `Stationary` a l'apparition. On prend les
        # cibles LEGALES du canal natif (`abilityTargets`), pas une tuile devinee.
        mow = next((m for m in (dec.get("mows") or [])
                    if m.get("visualId") == "ultraDreadnought"), None)
        spawned = None
        if mow is not None:
            at = rpc(sid, "abilityTargets", [{"runnerId": rid_b,
                                              "unitId": int(mow["casterId"]),
                                              "abilityType": DUTY_ETERNAL}], 90) or {}
            # `units[].abilities[].{fromHere,targets}[]`, chaque entree `{kind, tile:{col,row}}`
            hexes = [(int(t["tile"]["col"]), int(t["tile"]["row"]))
                     for u in (at.get("units") or [])
                     for ab in (u.get("abilities") or [])
                     for cle in ("fromHere", "targets")
                     for t in (ab.get(cle) or [])
                     if isinstance(t.get("tile"), dict) and t["tile"].get("col") is not None]
            for col, row in hexes[:6]:
                rpc(sid, "applyAction", [{"runnerId": rid_b, "action": {
                    "kind": "ability", "casterId": int(mow["casterId"]),
                    "abilityType": DUTY_ETERNAL, "to": {"col": col, "row": row}}}], 90)
                dv = rpc(sid, "decisionView", [{"runnerId": rid_b}]) or {}
                nouveau = next((u.get("id") for u in (dv.get("units") or [])
                                if u.get("visualId") == "ultraSmnDreadnought"), None)
                if nouveau is not None:
                    spawned = nouveau
                    break
        dec, obs, snap = capture(sid, rid_b)
        n_b, ec_b, rates_b = confronter(
            dec, obs, snap, "MONTAGE B apres cast DutyEternal (summon spawne = u%s)" % spawned)
        resultats.append(("2 B egalite port == mesure (%d lignes)" % n_b,
                          "OK" if (n_b and not ec_b) else "ECHEC"))
        resultats.append(("3 B non-vacuite (%d unites ratees par la reconstruction)" % rates_b,
                          "OK" if rates_b >= 2 else "ECHEC"))
        print("\n  (B t0 : %d lignes, %d ecarts, %d ratees par la reconstruction)"
              % (n_b0, len(ec_b0), rates_b0))

        # --- 5. montage C : la POLARITE INVERSE sur les traits de DEPART ------------------------
        # `custoAtlacoya` porte `SistersSilence` et `astraDreir` `DeathKorpsKrieg` dans le BC, NI
        # l'un ni l'autre au gameconfig -> la reconstruction les RATAIT, sans aucun AddTrait en jeu.
        rid_c, etat_c = build("c", ["--seed", "909", "--board", "MC1_67",
                                    "--p-units", "custoAtlacoya,astraDreir",
                                    "--a-units", "necroWarden,orksNob"])
        if rid_c is None:
            print("ECHEC build C: %s" % etat_c)
            return 3
        runners.append((rid_c, etat_c))
        dec, obs, snap = capture(sid, rid_c)
        n_c, ec_c, rates_c = confronter(
            dec, obs, snap, "MONTAGE C -- traits de DEPART portes par le seul BC")
        resultats.append(("5 C egalite port == mesure (%d lignes)" % n_c,
                          "OK" if (n_c and not ec_c) else "ECHEC"))
        resultats.append(("6 C non-vacuite (%d unites ratees par la reconstruction)" % rates_c,
                          "OK" if rates_c >= 2 else "ECHEC"))
    finally:
        for rid, etat in runners:
            try:
                rpc(sid, "disposeRunner", [{"runnerId": rid}], 20)
            except Exception:                                        # noqa: BLE001
                pass
            if etat and os.path.exists(etat):
                os.remove(etat)

    print("\n" + "=" * 78)
    for nom, v in resultats:
        print("  %-52s %s" % (nom, v))
    return 0 if not [n for n, v in resultats if v == "ECHEC"] else 1


if __name__ == "__main__":
    sys.exit(main())
