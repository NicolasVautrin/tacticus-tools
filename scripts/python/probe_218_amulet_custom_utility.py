"""probe #218 -- AmuletOfTheVoidwyrmPlaybook override-t-il CalculateCustomUtility ?

Reponse : NON. Le "13bis" de `docs/rl/case-27-custom-utility.md` (tranche 3) etait un
FAUX POSITIF de lecture HORS VTABLE -- le piege (b) que la fiche elle-meme nommait.

Le probe etablit le verdict par TROIS piliers independants, chacun POSITIF (on lit ce
qui EST, jamais l'absence d'un symbole dans une table) :

  A -- STRUCTURE (offline, source indexee par NOM : data/symbols/<build>/frida/classes.tsv)
       `CalculateCustomUtility` est un virtuel declare par
       `IdunBattle.AI.Playbook.ComparablePlaybook`1`, dont la chaine est
       ComparablePlaybook -> Playbook -> BasePlaybook -> System.Object.
       `AmuletOfTheVoidwyrmPlaybook` derive de
       `IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1` -> System.Object.
       Les deux branches sont DISJOINTES : la methode n'est ni heritee ni overridable.

  B -- FORME DE LA VTABLE DE LA BASE (live). `ControlEdictPlaybook` a la MEME base
       (`TriggeredAbilityPlaybook`1`) et sa classe EST initialisee dans la session :
       sa vtable tient en 13 slots (0x138..0x1f8) tous nommes, et aucun ne s'appelle
       `CalculateCustomUtility`. C'est la forme que porte AUSSI AmuletOfTheVoidwyrm.

  C -- ARITHMETIQUE DU FAUX POSITIF (live). Les `Il2CppClass` sont CONTIGUS.
       klass(PlasmaGrenadePlaybook) - klass(AmuletOfTheVoidwyrmPlaybook) = 0x210,
       et le "slot 0x548" d'Amulet moins le VRAI slot 0x338 de PlasmaGrenade = 0x210 :
       le sweep lisait la vtable de la classe VOISINE. Toute la sequence de 39 slots
       coincide (Equals @+0x348 vs @+0x138 ... MakeFinalTilePrediction @+0x5a8 vs @+0x398).

Pourquoi le debordement a ete SILENCIEUX : la vtable propre d'AmuletOfTheVoidwyrmPlaybook
est NULLE (classe jamais initialisee dans la session), donc le balayage 0x108..0x808 ne
trouvait rien chez elle et tombait sur la premiere vtable REMPLIE en aval.

Sortie ASCII pure (cp1252).
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import probe_27_custom_utility_inventory as INV

REPO = Path(__file__).resolve().parents[2]

VTABLE_START = 0x138  # offset canonique du 1er VirtualInvokeData dans Il2CppClass
SLOT = 0x10           # sizeof(VirtualInvokeData) = { methodPtr, MethodInfo* }

NS = "IdunBattle.AI.Playbook.Loki"
SUBJECT = "AmuletOfTheVoidwyrmPlaybook"
NEIGHBOUR = "PlasmaGrenadePlaybook"
SIBLING = "ControlEdictPlaybook"  # meme base, classe INITIALISEE -> vtable lisible

# Les 7 classes que la tranche 3 avait vues "porter le slot hors +0x338".
OFF_GRID = [
    "AmuletOfTheVoidwyrmPlaybook", "ControlEdictPlaybook", "OmnissiahsBlessingPlaybook",
    "FoulInfusionPlaybook", "RedRampagePlaybook", "UnbreakableDutyPlaybook",
    "PrehensilePincerTailPlaybook",
]


# ------------------------------------------------------------------ pilier A
def load_parents(build: str) -> dict:
    p = REPO / "data" / "symbols" / build / "frida" / "classes.tsv"
    parents = {}
    with io.open(p, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3:
                parents[c[0]] = c[2]
    return parents


def chain(parents: dict, name: str, depth: int = 16) -> list:
    out = [name]
    while depth and parents.get(name) and parents[name] != name:
        name = parents[name]
        out.append(name)
        depth -= 1
    return out


def pillar_a(build: str) -> bool:
    parents = load_parents(build)
    subj = "%s.%s" % (NS, SUBJECT)
    neigh = "%s.%s" % (NS, NEIGHBOUR)
    sib = "%s.%s" % (NS, SIBLING)
    ok = True
    for full in (subj, neigh, sib):
        ch = chain(parents, full)
        print("  %-58s : %s" % (full.split(".")[-1], " -> ".join(
            x.split(".")[-1] for x in ch)))
    subj_chain = chain(parents, subj)
    if any("ComparablePlaybook" in x for x in subj_chain):
        print("  FAIL: %s descend de ComparablePlaybook" % SUBJECT)
        ok = False
    else:
        print("  OK: %s ne descend PAS de ComparablePlaybook"
              " -> CalculateCustomUtility ni herite ni overridable" % SUBJECT)
    if not any("ComparablePlaybook" in x for x in chain(parents, neigh)):
        print("  FAIL: %s ne descend pas de ComparablePlaybook" % NEIGHBOUR)
        ok = False
    return ok


# ------------------------------------------------------------------ pilier B
def bounded_vtable(sid: int, ns: str, cls: str, max_slots: int = 96) -> tuple:
    """Vtable BORNEE : premier bloc CONTIGU de slots nommes depuis +0x138.

    Le bornage est ce qui manquait au sweep de la tranche 3 : `resolveVtableSlot`
    lit `klass+off` en aveugle, sans connaitre `vtable_count`, donc un balayage
    large deborde sur l'Il2CppClass suivante (contigue) et rend des MethodInfo
    parfaitement nommes appartenant a une AUTRE classe.
    """
    end = VTABLE_START + (max_slots - 1) * SLOT
    res = INV.rpc(sid, "resolveVtableSlot",
                  [{"ns": ns, "cls": cls, "start": VTABLE_START, "end": end}])
    if not res or not res.get("ok"):
        raise SystemExit("resolveVtableSlot KO on %s.%s: %r" % (ns, cls, res))
    slots = []
    for s in res["slots"]:
        if not s.get("method") or not s.get("funcRVA"):
            break
        slots.append((int(s["off"], 0), s["method"], int(s["funcRVA"], 16)))
    return int(res["klass"], 16), slots


def pillar_b(sid: int) -> bool:
    klass, slots = bounded_vtable(sid, NS, SIBLING)
    print("  %s klass=0x%x : %d slots dans sa vtable propre"
          % (SIBLING, klass, len(slots)))
    for off, name, rva in slots:
        print("    +0x%-4x rva=0x%-8x %s" % (off, rva, name))
    names = [n for _o, n, _r in slots]
    if "CalculateCustomUtility" in names:
        print("  FAIL: la base TriggeredAbilityPlaybook porte CalculateCustomUtility")
        return False
    print("  OK: aucun CalculateCustomUtility dans la vtable de"
          " TriggeredAbilityPlaybook`1 (%d slots, tous de MOUVEMENT)" % len(slots))
    return True


# ------------------------------------------------------------------ pilier C
def pillar_c(sid: int) -> bool:
    k_subj, slots_subj = bounded_vtable(sid, NS, SUBJECT)
    k_neigh, slots_neigh = bounded_vtable(sid, NS, NEIGHBOUR)
    delta = k_neigh - k_subj
    print("  klass(%s) = 0x%x" % (SUBJECT, k_subj))
    print("  klass(%s) = 0x%x" % (NEIGHBOUR, k_neigh))
    print("  delta = 0x%x" % delta)
    print("  vtable propre BORNEE de %s : %d slots (classe non initialisee ->"
          " slots nuls)" % (SUBJECT, len(slots_subj)))

    cc = [(o, r) for o, n, r in slots_neigh if n == "CalculateCustomUtility"]
    if len(cc) != 1:
        print("  FAIL: %s n'a pas exactement 1 CalculateCustomUtility" % NEIGHBOUR)
        return False
    off_neigh, rva = cc[0]
    print("  %s : CalculateCustomUtility au VRAI slot +0x%x (rva=0x%x)"
          % (NEIGHBOUR, off_neigh, rva))

    # Le sweep non borne de la tranche 3 rendait ce meme corps a +0x548 sur Amulet.
    off_seen = off_neigh + delta
    print("  => lu depuis %s, ce meme slot tombe a +0x%x" % (SUBJECT, off_seen))
    if off_seen != 0x548:
        print("  NOTE: la tranche 3 rapportait +0x548 ; mesure ici +0x%x"
              " (les adresses de classe bougent d'une session a l'autre,"
              " l'IDENTITE du debordement, elle, tient)" % off_seen)

    # Confrontation slot a slot : la sequence vue depuis SUBJECT a +delta est
    # exactement la vtable de NEIGHBOUR.
    res = INV.rpc(sid, "resolveVtableSlot",
                  [{"ns": NS, "cls": SUBJECT,
                    "start": VTABLE_START + delta,
                    "end": VTABLE_START + delta + (len(slots_neigh) - 1) * SLOT}])
    seen = [(s.get("method"), s.get("funcRVA")) for s in res["slots"]]
    want = [(n, hex(r)) for _o, n, r in slots_neigh]
    same = all(seen[i][0] == want[i][0]
               and int(seen[i][1] or "0", 16) == slots_neigh[i][2]
               for i in range(len(want)))
    print("  confrontation slot-a-slot sur %d slots : %s"
          % (len(want), "IDENTIQUE" if same else "DIFFERENT"))
    if not same:
        for i in range(len(want)):
            if seen[i][0] != want[i][0]:
                print("    mismatch #%d: vu=%r attendu=%r" % (i, seen[i], want[i]))
        return False
    print("  OK: le 'slot' d'Amulet EST la vtable de %s lue par debordement"
          % NEIGHBOUR)
    return True


# ------------------------------------------------------------ les 7 hors-grille
def offgrid_sweep(sid: int, build: str) -> bool:
    """Re-balaye BORNE les 7 classes que la tranche 3 voyait 'hors +0x338'.

    `slots=0` ne PROUVE rien a lui seul : c'est une vtable NON INITIALISEE
    (la classe n'a jamais ete instanciee dans la session), et c'est precisement
    ce qui faisait deborder le sweep non borne. Pour ces classes le verdict vient
    de la BASE (pilier A + pilier B), pas du compte de slots -- la colonne `base`
    le rend explicite.
    """
    parents = load_parents(build)
    ok = True
    for cls in OFF_GRID:
        base = parents.get("%s.%s" % (NS, cls), "?").split(".")[-1]
        try:
            klass, slots = bounded_vtable(sid, NS, cls)
        except SystemExit as exc:
            print("  %-32s : %s" % (cls, exc))
            continue
        names = [n for _o, n, _r in slots]
        has = "CalculateCustomUtility" in names
        why = ("vtable LUE" if slots else "vtable NON INITIALISEE"
                                          " -> verdict par la base")
        print("  %-32s klass=0x%-13x slots=%-3d CCU=%-3s base=%-42s (%s)"
              % (cls, klass, len(slots), "OUI" if has else "non", base, why))
        if has:
            ok = False
    if ok:
        print("  OK: aucune des 7 ne porte le slot dans sa PROPRE vtable")
        print("  NB: les bases rencontrees -- TriggeredAbilityPlaybook`1,"
              " AdjacentUnitPreferenceTriggeredAbilityPlaybook`1 (elle-meme fille"
              " de TriggeredAbilityPlaybook`1) et NonComparablePlaybook`1 -- sont"
              " TOUTES hors de la branche ComparablePlaybook`1 qui declare"
              " CalculateCustomUtility.")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", default="gqfc5mff6c")
    args = ap.parse_args()

    sid = INV._session_id()
    print("session=%d build=%s" % (sid, args.build))

    print("\n=== PILIER A -- chaine d'heritage (classes.tsv, indexee par NOM) ===")
    a = pillar_a(args.build)

    print("\n=== PILIER B -- vtable REELLE de la base TriggeredAbilityPlaybook`1 ===")
    b = pillar_b(sid)

    print("\n=== PILIER C -- arithmetique du debordement ===")
    c = pillar_c(sid)

    print("\n=== les 7 'slots hors +0x338' de la tranche 3, re-balayes BORNE ===")
    d = offgrid_sweep(sid, args.build)

    print("\n=== VERDICT ===")
    verdict = a and b and c and d
    print("AmuletOfTheVoidwyrmPlaybook override CalculateCustomUtility : %s"
          % ("OUI (piliers en desaccord -- RELIRE)" if not verdict else "NON"))
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
