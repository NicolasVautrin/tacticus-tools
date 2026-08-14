"""#1044 -- le MUR DES TRAITS : MONTAGE NOMME qui force le jeu de traits d'une unite.

    python scripts/python/probe_1044_levier_traits.py --cas hero-separant
    python scripts/python/probe_1044_levier_traits.py --cas levier-nu
    python scripts/python/probe_1044_levier_traits.py --offline        # etage 0 seul

CRITERE BINAIRE (enonce AVANT la methode) : peut-on FORCER le jeu de traits d'une unite au
MONTAGE, et le MESURER ? Reponse MESUREE : OUI pour 104 des 105 membres de l'enum par
`--unit-stat "<vis>:Traits=[...]"` ; NON pour `UnitTrait.Hero` par ce seul levier -- il faut
lui adjoindre un TRAIT PORTEUR (`NPC` ou `Summon`), pour la raison native ci-dessous.

LA VOIE, LUE AU DECOMPILE (jamais au nom) -- DEUX etages, et c'est le SECOND qui faisait mur :

 1. `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent(entity, config)` enumere
    `UnitConfiguration.Traits (+0xd0)` et remplit `BaseUnitComponent.<permanents @+0x40>`.
    `BC.Units[].Traits` est donc bien la source -- et c'est pourquoi le levier mord.
    (`IdunBattle.Entities.Factories.MachineFactory$$Build` appelle le MEME foyer : les Machines
    of War passent par la aussi.)

 2. `IdunBattle.Operations.AddUnitOperation$$AddUnitTypeTraits(unitComponent, unitOverrideType)`
    passe APRES et FORCE le triplet {Hero, NPC, Summon}, mutuellement exclusif :

        UnitOverrideType.Hero   (0) -> +Hero(0x10)  -NPC(0x7e6)  -Summon(0x2)
        UnitOverrideType.NPC    (1) -> -Hero        +NPC         -Summon
        UnitOverrideType.Summon (2) -> -Hero        -NPC         +Summon

    Son appelant `...AddUnitOperation$$AddUnitTypeTraits(unit, options, hasParent)` choisit :
      * si `options.<Nullable<UnitOverrideType>>` a une valeur -> elle decide ;
      * sinon `heroDeDroit = !hasParent && !Contains(NPC) && !Contains(Summon)` -- calcule sur
        les traits DEJA POSES par l'etage 1 ; si vrai -> `UnitOverrideType.Hero` ;
      * sinon -> RETOUR SEC, aucun des trois n'est touche.

    C'EST LA SORTIE : une unite dont `BC.Units[].Traits` porte DEJA `NPC` (ou `Summon`) n'est
    plus « hero de droit », la fonction retourne sans rien ecrire, et `Hero` reste ABSENT.

 3. La LECTURE, elle, est `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` :
        HasTrait(t) == !retires(+0x50).Contains(t)
                       && ( permanents(+0x40).Contains(t) || temporaires(+0x48).Contains(t) )
    `IdunBattle.Entities.UnitExtensions$$GetTraits` ne rend QUE `+0x40` : il est aveugle aux
    deux autres. Le canal publie (`combatSnapshot.units[].traits`, #233) ne l'utilise PAS -- il
    invoque `IdunBattle.Entities.UnitExtensions$$HasTrait` valeur par valeur, donc il rend
    l'ensemble EFFECTIF, veto compris. C'est la seule mesure qui vaille.

CE QUE CE PROBE MESURE, dans cet ordre :
  0. OFFLINE -- le mirror `engine/entities/traits/unit_trait.py` est en bijection avec
     `IdunBattle.Entities.Enum.UnitTrait` du build. Le canal publie des ORDINAUX : sans cet
     etage, une confusion d'enum serait SILENCIEUSE (c'est exactement ce qui a rendu un bras de
     `probe_1042_wisdom_of_the_ancients_live.py` faussement VERT, par comparaison de CHAINES).
  1. LIVE -- un runner en REGIME SEPARANT : des unites du MEME camp aux jeux de traits VOULUS
     DIFFERENTS. Un montage ou tout le monde porte le meme jeu ne prouve RIEN.
  2. VENTILATION par unite : seed BC -> demande -> mesure, en RETRAIT MORD / AJOUT MORD /
     RESISTANT (porte alors que la demande ne le portait pas -> ecrit par une AUTRE source).
  3. COUT DU LEVIER -- ce que le trait porteur change par ailleurs : position obtenue,
     activabilite (`decisionView.toActivate`), controle (`combatSnapshot.units[].ctrl`).

RC : 0 = mesure faite, conforme au cas ; 1 = mesure faite, NON conforme ; 2 = RIEN N'EST CONCLU
     (build echoue, montage incomplet, canal muet). Un `null` de canal n'est JAMAIS lu comme
     « aucun trait » : ce serait un vert qui ne mesure rien.

ASCII only. Dispose SON runner (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

BOARD = "MC1_67"                     # 7x9, entierement Grass : toute tuile est posable
SEED = 777

# Le TRAIT PORTEUR par defaut. `Summon` marche aussi (meme branche native), mais il coute
# BEAUCOUP plus cher : mesure du 2026-08-14 -- une p-unit `Summon` n'entre PAS dans
# `decisionView.toActivate` (le natif termine son tour, cf. #291) et le `--place` ne tient meme
# pas (position obtenue (3,4) au lieu de (2,1) demandee, donc `rl_duel build` refuse).
PORTEUR_DEFAUT = "NPC"

P_POS = {"adeptCanoness": (1, 1), "adeptRetributor": (2, 1), "adeptHospitaller": (3, 1),
         "astraBullgryn": (4, 1), "astraCreed": (5, 1)}
# >= 4 cibles : un coup qui en tue deux terminerait la bataille (`stage Finished`), et
# `decisionView` refuserait alors toute lecture.
A_UNITS = [("blackTerminator", (1, 7)), ("bloodDeathCompany", (2, 7)),
           ("bloodSanguinary", (3, 7)), ("tauCrisis", (4, 7)), ("ultraTitus", (5, 7))]

CASES: dict[str, dict] = {
    # LE MONTAGE UTILE : deux unites SANS `Hero`, une avec `Hero` FORCE malgre un
    # `BC.Units[].Traits` qui ne le porte pas (le CONTROLE du forcage), deux TEMOINS intacts.
    # C'est le regime que `UnitsWithTrait(., UnitTrait.Hero)` exige pour etre confrontable.
    "hero-separant": {
        "traits": {"adeptCanoness": ["NPC"],
                   "adeptRetributor": ["Psyker", "NPC"],
                   "astraBullgryn": ["Psyker"]},
        "attendu": {"adeptCanoness": {"NPC"},
                    "adeptRetributor": {"NPC", "Psyker"},
                    # CONTROLE : `Hero` n'est PAS demande et arrive quand meme -> c'est
                    # `AddUnitTypeTraits` qui l'ecrit, pas la config.
                    "astraBullgryn": {"Hero", "Psyker"}},
    },
    # LE LEVIER NU, sans trait porteur : etablit que 104 traits sur 105 obeissent et que
    # `Hero` seul resiste. C'est la CONTRE-EPREUVE du cas ci-dessus.
    "levier-nu": {
        "traits": {"adeptCanoness": [],
                   "adeptRetributor": ["Psyker"]},
        "attendu": {"adeptCanoness": {"Hero"},
                    "adeptRetributor": {"Hero", "Psyker"}},
    },
}


def _unwrap(x):
    return x["result"] if isinstance(x, dict) and "result" in x else x


def _lignes(dv: dict):
    return list(dv.get("units") or []) + list(dv.get("mows") or [])


def traits_du_seed() -> dict:
    """`{visualId: [Trait, ...]}` LU dans le seed BC versionne -- l'etat AVANT toute mutation."""
    bc = json.loads((RACINE / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    return {u.get("VisualId"): list(u.get("Traits") or []) for u in (bc.get("Units") or [])}


def sans_hero(traits_voulus, porteur: str = PORTEUR_DEFAUT) -> list:
    """Les traits a ECRIRE dans `BC.Units[].Traits` pour qu'une unite arrive SANS `UnitTrait.Hero`.

    C'est le geste que `--unit-stat "<vis>:Traits=[...]"` seul ne sait pas faire : il faut y
    joindre le trait PORTEUR qui fait echouer le `heroDeDroit` d'
    `IdunBattle.Operations.AddUnitOperation$$AddUnitTypeTraits` (cf. en-tete, etage 2)."""
    out = [t for t in traits_voulus if t != "Hero"]
    if porteur not in out:
        out.append(porteur)
    return out


def etage0_appariement(verbeux: bool = True) -> int:
    """Le mirror Python est-il apparie a l'enum que le canal publie ? (aucun live)"""
    echecs = 0
    build = (RACINE / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
    chemin = RACINE / "data" / "symbols" / build / "frida" / "enums.tsv"
    enums: dict = {}
    with chemin.open(encoding="utf-8") as fh:
        for ligne in fh:
            if ligne.startswith("#") or "\t" not in ligne:
                continue
            nom, membres = ligne.rstrip("\n").split("\t", 1)
            paires: dict = {}
            for morceau in membres.split(","):
                if "=" in morceau:
                    val, cle = morceau.split("=", 1)
                    try:
                        paires[cle] = int(val)
                    except ValueError:
                        pass
            if paires:
                enums[nom] = paires

    plein = "IdunBattle.Entities.Enum.UnitTrait"
    if verbeux:
        print("=== ETAGE 0 : appariement du mirror (build %s) ===" % build)
    if plein not in enums:
        print("ROUGE : %s absent de enums.tsv" % plein)
        return 1
    reference = enums[plein]
    homonymes = sorted(n for n in enums if n.rsplit(".", 1)[-1] in ("UnitTrait", "Trait"))

    from engine.entities.traits.unit_trait import UnitTrait  # noqa: PLC0415 (mirror, pas un cycle)
    porte = {m.name: int(m.value) for m in UnitTrait}
    manquants = sorted(set(reference) - set(porte))
    en_trop = sorted(set(porte) - set(reference))
    desaccords = sorted(k for k in set(porte) & set(reference) if porte[k] != reference[k])
    if verbeux:
        print("  %s : %d membres" % (plein, len(reference)))
        print("  homonymes du build (nom court) : %s" % homonymes)
    if manquants or en_trop or desaccords:
        print("ROUGE : mirror != build -- manquants=%s en_trop=%s desaccords=%s"
              % (manquants[:8], en_trop[:8], desaccords[:8]))
        echecs += 1
    elif verbeux:
        print("  mirror engine/entities/traits/unit_trait.py : BIJECTIF (%d membres)" % len(porte))

    # Le triplet que `AddUnitTypeTraits` FORCE doit exister sous ces noms-la : c'est par eux
    # que le montage passe. Un renommage de build les ferait disparaitre en silence.
    #
    # ⚠ CES TROIS ORDINAUX SONT DES LITTERAUX, ET C'EST LE POINT. Ils ne DESIGNENT rien ici --
    # ils sont la VALEUR LUE au decompile d'`IdunBattle.Operations.AddUnitOperation$$
    # AddUnitTypeTraits` (`Add(traits, 0x10)`, `Remove(traits, 0x7e6)`, `Add(traits, 2)`), figee
    # au site comme le cran que `test_270r1r1r3_role_enum_offline` etage 1 prescrit : passer par
    # `int(UnitTrait.Hero)` rendrait ce controle TAUTOLOGIQUE (il comparerait le mirror a
    # lui-meme) et il redeviendrait vert apres une renumerotation, alors que le decompile cite
    # dans toute la prose de ce fichier, lui, n'aurait pas bouge.
    for nom_trait, ordinal in (("Hero", 0x10), ("NPC", 0x7e6), ("Summon", 0x2)):
        if reference.get(nom_trait) != ordinal:
            print("ROUGE : %s vaut %s dans le build, %d au decompile d'AddUnitTypeTraits"
                  % (nom_trait, reference.get(nom_trait), ordinal))
            echecs += 1
    return echecs


def run(cas: str = "hero-separant", *, seed: int = SEED, board: str = BOARD,
        state_file: str | None = None, keep: bool = False,
        traits: dict | None = None) -> dict:
    """MONTE le regime demande et rend la MESURE. Dispose son runner (sauf `keep`).

    Rend `{"cas", "rid", "demande", "seed_traits", "mesure", "resistants", "separants",
           "activables", "positions", "ctrl", "conforme", "ecarts"}`.
    `mesure[visualId]` est un `set` de NOMS de traits, projete depuis les ORDINAUX du canal.
    """
    from engine.entities.traits.unit_trait import UnitTrait  # noqa: PLC0415

    spec = CASES[cas] if traits is None else {"traits": traits, "attendu": {}}
    demande = dict(spec["traits"])
    seedt = traits_du_seed()

    sf = state_file or str(RACINE / "logs" / ("probe1044_%s_s%d.json" % (cas, seed)))
    Path(sf).parent.mkdir(parents=True, exist_ok=True)
    argv = ["build", "--seed", str(seed), "--board", board,
            "--p-units", ",".join(P_POS),
            "--a-units", ",".join(v for v, _ in A_UNITS)]
    for vis, tr in sorted(demande.items()):
        argv += ["--unit-stat", "%s:Traits=%s" % (vis, json.dumps(tr))]
    for vis, pos in P_POS.items():
        argv += ["--place", "%s:%d,%d" % (vis, pos[0], pos[1])]
    for vis, pos in A_UNITS:
        argv += ["--a-place", "%s:%d,%d" % (vis, pos[0], pos[1])]
    argv += ["--state-file", sf]

    import rl_duel as R  # noqa: PLC0415
    rc = R.main(argv)
    if rc != 0:
        # ⚠ UN BUILD REFUSE PEUT AVOIR MONTE SON RUNNER : `rl_duel build` verifie les positions
        # APRES le deploiement, donc un `--place` non tenu laisse un runner VIVANT et un
        # `--state-file` ecrit. Lever sans disposer le rendrait ORPHELIN, sur un budget PARTAGE
        # entre tous les agents. Mesure : le premier essai de generalisation (board `C3_01`) en
        # a laisse un.
        try:
            orphelin = json.loads(Path(sf).read_text(encoding="utf-8")).get("runnerId")
        except Exception:                                  # noqa: BLE001
            orphelin = None
        if orphelin is not None and not keep:
            import rl_collect_batch as _B  # noqa: PLC0415
            try:
                _B._rpc(_B._resolve_session(), "disposeRunner",
                        [{"runnerId": orphelin}], timeout=30)
                print("[dispose] runner %s du build refuse" % orphelin)
            except Exception as exc:                       # noqa: BLE001
                print("[dispose] runner %s NON dispose : %s" % (orphelin, exc))
        # ⚠ NE PAS ATTRIBUER : `rl_duel build` refuse pour plusieurs raisons distinctes, et
        # deux ont ete VUES ici. (a) le trait porteur `Summon` -- la position obtenue n'est pas
        # la position demandee (mesure : (3,4) au lieu de (2,1)) ; (b) le BOARD -- les tuiles de
        # `P_POS`/`A_UNITS` sont celles de `MC1_67` (7x9, tout Grass), et un board plus petit ou
        # plus obstrue en refuse une (mesure sur `C3_01` : une a-unit manquante). Nommer une
        # seule cause dans le message ferait chercher au mauvais endroit.
        raise AssertionError(
            "#1044 : `rl_duel build` a refuse le montage %r sur le board %r -- RIEN N'EST"
            " CONCLU. Causes VUES, dans cet ordre de frequence : (a) tuile de `P_POS`/`A_UNITS`"
            " absente ou injouable sur CE board (elles sont dimensionnees pour `MC1_67`, 7x9 ;"
            " `python board.py --id <board>` les caracterise) ; (b) trait porteur `Summon`, dont"
            " le `--place` n'est pas tenu (cf. en-tete)." % (cas, board))
    rid = json.loads(Path(sf).read_text(encoding="utf-8")).get("runnerId")

    import rl_collect_batch as B  # noqa: PLC0415
    sid = B._resolve_session()

    def rpc(method, body=None, timeout=90):
        return _unwrap(B._rpc(sid, method, [body] if body is not None else [], timeout=timeout))

    try:
        dv = rpc("decisionView", {"runnerId": rid}, 120) or {}
        ids, positions = {}, {}
        for u in _lignes(dv):
            ids.setdefault(u.get("visualId"), u.get("id"))
            # `decisionView.units[].pos` est un OBJET {col,row}, pas une paire : `tuple(...)`
            # dessus rendait ('col','row') et l'etage 4 signalait un ECART sur TOUTES les
            # unites, y compris celles qui etaient a la bonne tuile.
            p = u.get("pos") or {}
            positions.setdefault(u.get("visualId"),
                                 (p.get("col"), p.get("row")) if isinstance(p, dict)
                                 else tuple(p))
        absents = [v for v in P_POS if ids.get(v) is None]
        if absents:
            raise AssertionError("#1044 : montage incomplet, unites absentes de `decisionView` :"
                                 " %s -- RIEN N'EST CONCLU" % absents)
        toact = set(dv.get("toActivate") or [])

        snap = rpc("combatSnapshot", {"runnerId": rid}, 90) or {}
        vus, ctrl = {}, {}
        for u in (snap.get("units") or []):
            vus[u.get("entityId")] = u.get("traits")
            ctrl[u.get("entityId")] = u.get("ctrl")

        nom = {int(m.value): m.name for m in UnitTrait}
        mesure: dict = {}
        for vis in P_POS:
            ordinaux = vus.get(ids[vis])
            if ordinaux is None:
                raise AssertionError(
                    "#1044 : `combatSnapshot.units[].traits` est NULL pour %s -- canal MUET,"
                    " RIEN N'EST CONCLU (un null n'est pas une unite sans trait)" % vis)
            mesure[vis] = {nom.get(int(t), "?%d" % int(t)) for t in ordinaux}

        resistants = {vis: sorted(mesure[vis] - set(demande[vis]))
                      for vis in demande if mesure[vis] - set(demande[vis])}
        paires = [(x, y) for i, x in enumerate(P_POS) for y in list(P_POS)[i + 1:]]
        separants = [(x, y) for x, y in paires if mesure[x] != mesure[y]]

        ecarts = {}
        for vis, att in (spec.get("attendu") or {}).items():
            if mesure[vis] != set(att):
                ecarts[vis] = {"attendu": sorted(att), "mesure": sorted(mesure[vis])}

        return {
            "cas": cas, "rid": rid, "demande": demande,
            "seed_traits": {v: seedt.get(v) for v in P_POS},
            "mesure": mesure, "resistants": resistants,
            "separants": separants, "paires": len(paires),
            "activables": {v: (ids[v] in toact) for v in P_POS},
            "positions": {v: positions.get(v) for v in P_POS},
            "demandees": dict(P_POS),
            "ctrl": {v: ctrl.get(ids[v]) for v in P_POS},
            "ids": {v: ids[v] for v in P_POS},
            "conforme": not ecarts, "ecarts": ecarts,
        }
    finally:
        if not keep and rid is not None:
            try:
                B._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            except Exception as exc:                       # noqa: BLE001
                print("[dispose] %s" % exc)


def main() -> int:
    ap = argparse.ArgumentParser(description="#1044 -- le levier de montage des TRAITS")
    ap.add_argument("--cas", choices=sorted(CASES), default="hero-separant")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--offline", action="store_true", help="s'arrete apres l'etage 0")
    ap.add_argument("--traits", action="append", default=None,
                    help="bras LIBRE : '<visualId>=<Trait>[,<Trait>]' (valeur vide = liste "
                         "VIDE), repetable. Remplace le cas nomme.")
    a = ap.parse_args()

    echecs = etage0_appariement()
    if a.offline:
        return 1 if echecs else 0
    if echecs:
        print("\nRIEN N'EST CONCLU : l'etage 0 est rouge, la lecture des ordinaux serait"
              " ininterpretable.")
        return 2

    libre = None
    if a.traits is not None:
        libre = {k: [t for t in v.split(",") if t]
                 for k, v in (x.split("=", 1) for x in a.traits)}

    print()
    print("=== ETAGE 1 : montage `%s` ===" % (a.cas if libre is None else "libre"))
    try:
        m = run(a.cas, seed=a.seed, board=a.board, state_file=a.state_file, keep=a.keep,
                traits=libre)
    except AssertionError as exc:
        print("  %s" % exc)
        return 2
    print("  runnerId=%s" % m["rid"])

    print()
    print("=== ETAGE 2 : ce que le NATIF porte, par unite (ordinaux -> membres) ===")
    for vis in P_POS:
        etat = ("DEMANDE %s" % m["demande"][vis]) if vis in m["demande"] else "TEMOIN (intact)"
        print("  %-20s %-46s %s" % (vis, sorted(m["mesure"][vis]), etat))

    print()
    print("=== ETAGE 3 : ventilation du levier ===")
    for vis in P_POS:
        avait, porte = set(m["seed_traits"].get(vis) or []), m["mesure"][vis]
        if vis not in m["demande"]:
            print("  %-20s TEMOIN : ecart seed<->mesure = %s" % (vis, sorted(porte ^ avait)))
            continue
        veut = set(m["demande"][vis])
        print("  %-20s RETRAIT MORD %s | AJOUT MORD %s | AJOUT RATE %s | RESISTANT %s"
              % (vis, sorted((avait - veut) - porte), sorted((veut - avait) & porte),
                 sorted(veut - porte), sorted(porte - veut)))

    print()
    print("=== ETAGE 4 : COUT du levier (ce que le trait porteur change par ailleurs) ===")
    for vis in P_POS:
        pos_ok = tuple(m["positions"][vis] or ()) == tuple(m["demandees"][vis])
        print("  %-20s pos=%-8s (demandee %-8s %s) activable=%-5s ctrl=%s"
              % (vis, m["positions"][vis], m["demandees"][vis], "OK" if pos_ok else "ECART",
                 m["activables"][vis], m["ctrl"][vis]))

    print()
    print("=== VERDICT ===")
    print("  paires d'unites du MEME camp aux traits DIFFERENTS : %d / %d"
          % (len(m["separants"]), m["paires"]))
    if m["resistants"]:
        print("  RESISTANTS (hors portee de `BC.Units[].Traits` seul) : %s" % m["resistants"])
    if not m["separants"]:
        print("  REGIME DEGENERE : toutes les unites portent le MEME jeu -- un gate y serait"
              " uniformement vrai, donc invalidable.")
        return 1
    if libre is not None:
        print("  bras LIBRE : aucune attente a confronter (mesure imprimee ci-dessus).")
        return 0
    if not m["conforme"]:
        print("  NON CONFORME au cas `%s` : %s" % (a.cas, m["ecarts"]))
        return 1
    print("  CONFORME au cas `%s` : le montage rend exactement les jeux attendus." % a.cas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
