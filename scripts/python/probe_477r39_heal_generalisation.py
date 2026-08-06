#!/usr/bin/env python3
"""#477-r39 -- la GENERALISATION du foyer `IdunBattle.Operations.HealUnitOperation$$Execute`.

    python probe_477r39_heal_generalisation.py [--session N] [--tours 2]

POURQUOI CE PROBE EXISTE, ET CE QU'IL CORRIGE
----------------------------------------------
`probe_477r22_turn_phase.py` confronte le foyer sur TOUT le flux de ses quatre scenarios -- mais
un seul d'entre eux porte une `Action=HealInfo`, et il n'en porte que DEUX, produites par la
MEME ability (`MedicusMinistorum`) sur la MEME cible. Un vert obtenu la-dessus ne dit rien de
trois choses :

  * les AUTRES porteurs : le trait `Healer` est porte par QUATRE unites du pool
    (`adeptHospitaller`, `bloodSanguinary`, `deathRotbone`, `genesBiophagus`) et leurs abilities
    de soin sont distinctes. Si l'une passait par un producteur different, le foyer se tairait ;
  * l'AUTO-SOIN : sur le corpus herite, `Tag=Caster_Id` differe TOUJOURS de l'entite de
    l'action, donc la contre-epreuve `heal_entite` mord toujours. Un montage ou le soigneur se
    soigne lui-meme la rend HORS DOMAINE -- et c'est exactement le regime ou un port qui aurait
    interverti les deux entites resterait VERT ;
  * les deux valeurs des cles d'ETAT. `UnitStats_RemovedNegativeUnitEffects` vaut `0` sur
    2 / 2 du corpus herite et `UnitStats_WasWoundedBeforeHeal` vaut `1` sur 2 / 2 : le regime a
    une seule valeur ne separe pas ces cles par l'egalite brute.

Le probe monte donc N rosters, applique le MEME foyer, et publie la VENTILATION DES REGIMES --
le compte de chacun, pas seulement le total. Un regime qu'aucun roster n'atteint est PUBLIE
comme non exerce, jamais tu.

DISCIPLINE : un runner a la fois, dispose dans le `finally`, state-files sous `logs/`, board
explicite. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import probe_477r15a_stream_conformance as R15A  # noqa: E402
import probe_477r19_process_removals as R19  # noqa: E402
import probe_477r21_activation_tree as R21  # noqa: E402
import probe_477r22_turn_phase as R22  # noqa: E402
from engine.streams import StepType, TagKey  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "logs"

MesureImpossible = R15A.MesureImpossible

#: LES ROSTERS, ET LE REGIME QUE CHACUN VISE. Le board est le MEME que celui du corpus herite
#: (`MC1_67`), et pour une raison LUE : c'est son effet de tuile
#: (`EnvDespoiledGroundTileDamage`) qui blesse une unite au debut du tour, donc qui declenche le
#: soin. Changer de board ferait disparaitre la blessure, et avec elle l'emission -- la GATE 2 de
#: `HealUnitOperation$$Execute` retourne sans rien ecrire quand la cible n'etait pas blessee,
#: qu'aucun point n'a ete rendu et qu'aucun effet n'a ete retire.
#:
#: ⚠ LE 1v1 EST LE MONTAGE DE L'AUTO-SOIN, ET IL EST DERIVE, PAS ESPERE : avec une seule unite
#: dans l'equipe, la seule cible possible du soin EST le soigneur. S'il ne se soigne pas, le
#: probe le DIT (regime `auto` a zero) au lieu de compter un vert.
#:
#: ⚠ LE NOMBRE DE TOURS EST UNE VARIABLE DE LA MESURE, ET IL A ETE MESURE. A DEUX tours, un seul
#: de ces rosters produit un soin (`MedicusMinistorum`, le passif d'`adeptHospitaller`) : le
#: corpus reste alors a UN producteur, et la forme n'est confrontee que sous cette ability-la. A
#: QUATRE, `SanguinaryPriest` (le passif de `bloodSanguinary`) entre a son tour -- **2**
#: producteurs distincts, **3** actions. C'est pourquoi le defaut est 4 et non 2.
PLANS = (
    ("hospitaller-2v2", "MC1_67", "adeptHospitaller,astraBullgryn",
     "blackTerminator,worldJakhal"),
    ("sanguinary-2v2", "MC1_67", "bloodSanguinary,astraBullgryn",
     "blackTerminator,worldJakhal"),
    ("rotbone-2v2", "MC1_67", "deathRotbone,astraBullgryn", "blackTerminator,worldJakhal"),
    ("biophagus-2v2", "MC1_67", "genesBiophagus,astraBullgryn", "blackTerminator,worldJakhal"),
    ("hospitaller-1v1", "MC1_67", "adeptHospitaller", "blackTerminator"),
)


def regimes(actions) -> Dict[str, int]:
    """LA VENTILATION DES REGIMES, DERIVEE DES DONNEES -- jamais declaree.

    Chaque cle nomme une CONFIGURATION que le port traite differemment, ou dont la contre-epreuve
    depend. Un compte a zero est un regime NON EXERCE, et il est publie tel quel."""
    out = {"auto-soin": 0, "hetero-soin": 0,
           "effets retires > 0": 0, "effets retires = 0": 0,
           "cible blessee": 0, "cible NON blessee": 0,
           "membres > 1": 0}
    for _i, _t, act in actions:
        d = dict(act.tags)
        out["auto-soin" if d.get(TagKey.Caster_Id.name) == act.entity
            else "hetero-soin"] += 1
        retires = d.get(TagKey.UnitStats_RemovedNegativeUnitEffects.name, 0)
        out["effets retires > 0" if retires > 0 else "effets retires = 0"] += 1
        blesse = d.get(TagKey.UnitStats_WasWoundedBeforeHeal.name, 0)
        out["cible blessee" if blesse else "cible NON blessee"] += 1
        if d.get(TagKey.UnitStats_NumberOfMembers.name, 0) > 1:
            out["membres > 1"] += 1
    return out


def scenario(session: int, etiquette: str, board: str, p_units: str, a_units: str,
             tours: int) -> dict:
    state = OUT / ("state-477r39-gen-%s.json" % etiquette)
    state.parent.mkdir(parents=True, exist_ok=True)
    rid = R19.build(board, state, p_units, a_units)
    try:
        joues = 0
        for _ in range(tours):
            q = subprocess.run([sys.executable, "rl_duel.py", "aiturn",
                                "--state-file", str(state)],
                               cwd=str(HERE), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900)
            if q.returncode != 0:
                break
            joues += 1
        flux = (R15A.rpc(session, "replayOutputStream",
                         {"runnerId": rid, "maxChars": 8000000}).get("outputStream") or "")
    finally:
        R15A.dispose(state)
    if not flux:
        raise MesureImpossible("`replayOutputStream` rend un flux VIDE")
    actions = R22._actions_heal(flux)
    # LES SOURCES DES `Group=Ability_Power` QUI ENVELOPPENT CHAQUE SOIN -- c'est ce qui dit si un
    # AUTRE producteur que `MedicusMinistorum` est exerce. Derive du flux, jamais liste.
    lignes = [l for l in flux.split("\n") if l != ""]
    sources: Dict[str, int] = {}
    for i, _t, _a in actions:
        for k in range(i - 1, -1, -1):
            m = R22.CONF.RE_GROUP.match(lignes[k])
            if m and R22.profondeur(lignes[k]) < R22.profondeur(lignes[i]):
                sources[m.group("source") or "<vide>"] = \
                    sources.get(m.group("source") or "<vide>", 0) + 1
                break
    return {"etiquette": etiquette, "tours": joues, "lignes_flux": flux.count("\n"),
            "foyer": R22.conformite_du_foyer_heal(flux), "regimes": regimes(actions),
            "sources": sources}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--tours", type=int, default=4)
    ap.add_argument("--plans", default="")
    args = ap.parse_args()

    try:
        session = args.session if args.session is not None else R15A.session_courante()
    except MesureImpossible as e:
        print("[477-r39-gen] MESURE IMPOSSIBLE : %s" % e)
        return 2

    choisis = [p for p in PLANS
               if not args.plans or p[0] in args.plans.split(",")]
    print("[477-r39-gen] session=%d  scenarios=%s"
          % (session, ",".join(p[0] for p in choisis)))

    resultats: List[dict] = []
    for etiquette, board, pu, au in choisis:
        print("")
        print("=== %s (board %s, %s vs %s) ===" % (etiquette, board, pu, au))
        try:
            res = scenario(session, etiquette, board, pu, au, args.tours)
        except MesureImpossible as e:
            print("  MESURE IMPOSSIBLE : %s" % e)
            return 2
        resultats.append(res)
        foy = res["foyer"]
        print("  flux %d lignes, %d tour(s) ; `Action=%s` : %d / %d reproduite(s) (%d lignes)"
              % (res["lignes_flux"], res["tours"], StepType.HealInfo.name,
                 foy["egales"], foy["actions"], foy["lignes"]))
        for d in foy["divergences"][:6]:
            print("      ROUGE %s" % d)
        print("  producteur(s) enveloppant(s) : %s"
              % (", ".join("%s x%d" % (k, v) for k, v in sorted(res["sources"].items()))
                 or "AUCUN"))
        print("  regimes exerces : %s"
              % (", ".join("%s=%d" % (k, v) for k, v in res["regimes"].items())))
        for nom, mordus, muets, rouges, hd in foy["contre_epreuve"]:
            etat = ("HORS DOMAINE" if mordus + muets == 0
                    else "OK" if (muets == 0 and rouges == mordus) else "ROUGE")
            print("      %-24s domaine=%-3d mord=%-3d INERTE=%-2d rougit=%d/%-3d %s"
                  % (nom, mordus + muets, mordus, muets, rouges, mordus, etat))

    print("")
    print("=== VERDICT (corpus = %d roster(s)) ===" % len(resultats))
    rc = 0
    total = sum(r["foyer"]["actions"] for r in resultats)
    egales = sum(r["foyer"]["egales"] for r in resultats)
    print("  %d / %d `Action=%s` reproduite(s) a l'EGALITE BRUTE, donnees fournies."
          % (egales, total, StepType.HealInfo.name))
    ko = [(r["etiquette"], len(r["foyer"]["divergences"])) for r in resultats
          if r["foyer"]["divergences"]]
    if ko:
        print("  ROUGE : %d divergence(s) : %s"
              % (sum(n for _b, n in ko), ", ".join("%s:%d" % (b, n) for b, n in ko)))
        rc = 1
    muettes = [(r["etiquette"], nom) for r in resultats
               for nom, _m, muets, _ro, _hd in r["foyer"]["contre_epreuve"] if muets > 0]
    if muettes:
        print("  ROUGE : %d mutation(s) INERTES PAR CONSTRUCTION : %s"
              % (len(muettes), ", ".join("%s/%s" % (b, n) for b, n in muettes)))
        rc = 1
    ce_ko = [(r["etiquette"], nom) for r in resultats
             for nom, mordus, _mu, rouges, _hd in r["foyer"]["contre_epreuve"]
             if mordus > 0 and rouges != mordus]
    if ce_ko:
        print("  ROUGE : %d mutation(s) ONT MORDU SANS ROUGIR : %s"
              % (len(ce_ko), ", ".join("%s/%s" % (b, n) for b, n in ce_ko)))
        rc = 1
    # ⚠ UN CORPUS DE GENERALISATION QUI N'ATTEINT AUCUN SOIN NE GENERALISE RIEN -- et le dire est
    # tout l'objet de ce probe. C'est un ROUGE, pas une attention : il signale que le MONTAGE ne
    # tient plus (roster hors pool, board sans degat de tuile, gate amont fermee), pas que le
    # port serait faux.
    if total == 0:
        print("  ROUGE : AUCUNE `Action=%s` sur AUCUN roster -- le montage n'atteint plus le "
              "pipeline de soin, donc rien n'est generalise." % StepType.HealInfo.name)
        return 1
    cumul: Dict[str, int] = {}
    for r in resultats:
        for k, v in r["regimes"].items():
            cumul[k] = cumul.get(k, 0) + v
    print("  REGIMES CUMULES : %s"
          % ", ".join("%s=%d" % (k, cumul[k]) for k in sorted(cumul)))
    morts = [k for k, v in cumul.items() if v == 0]
    if morts:
        print("  ATTENTION : %d regime(s) qu'AUCUN roster n'exerce -- le vert ne dit rien sur "
              "eux : %s" % (len(morts), ", ".join(sorted(morts))))
    prod = sorted({s for r in resultats for s in r["sources"]})
    print("  PRODUCTEURS ENVELOPPANTS DISTINCTS : %d -- %s" % (len(prod), ", ".join(prod)))
    if len(prod) < 2:
        print("  ATTENTION : un SEUL producteur enveloppant sur tout le corpus -- la forme "
              "`Action=%s` n'est donc confrontee que sous cette ability-la."
              % StepType.HealInfo.name)
    if rc == 0:
        print("  VERT : le foyer `HealUnitOperation$$Execute` reproduit %d / %d action(s) sur "
              "%d roster(s), et les %d contre-epreuves rougissent partout ou elles mordent."
              % (egales, total, len(resultats), len(R21.MUTATIONS_HEAL)))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
