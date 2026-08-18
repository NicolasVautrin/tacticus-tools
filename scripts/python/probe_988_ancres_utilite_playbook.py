"""`#988` -- les ancres du capteur d'utilite sont-elles ATTEIGNABLES, et le bucket MENT-il ?

    python probe_988_ancres_utilite_playbook.py [--avec-runner] [--state-file <absolu>]

Deux etages, et ils ne mesurent PAS la meme chose. Le premier ne demande AUCUNE fenetre de
reinject ; le second monte un runner.

ETAGE 1 -- ATTEIGNABILITE DES ANCRES (aucune fenetre requise)
    Le risque numero un de la tranche est le piege du generique : sur une DEFINITION generique,
    `findMethod` rend le thunk d'invocation et non le corps partage, si bien qu'un hook se declare
    `enabled` et fire ZERO fois, sans erreur (c'est ce qui est arrive a `bucket-audit`).
    Ici on ne le suppose pas, on le MESURE : `interfaceSlotProbe` calibre la vtable de chaque
    playbook CONCRET et rend, pour chaque slot, l'adresse d'entree traduite en base Ghidra. On la
    confronte a l'adresse que `data/symbols/<build>/ghidra/functions.tsv` donne pour le MEME
    symbole. Egalite => le corps est PROPRE et adressable, le hook mordra.

    ⚠ Une methode NON virtuelle n'apparait dans AUCUNE vtable. Son absence ici ne prouve donc
    rien -- elle sort en `NON VIRTUELLE (hors vtable)`, jamais en echec. C'est exactement la regle
    « l'absence d'une methode dans les tables ne prouve RIEN », transposee a la vtable.

ETAGE 2 -- LE BUCKET MENT-IL ? (monte un runner)
    `IdunBattle.AI.Playbook.NonComparablePlaybook<T>$$GenerateBucketWithMultipleStrategies` ne
    passe QUE par `IdunBattle.AI.BucketSystem.Bucket<T>$$AddActionToBucket`, laquelle ecrit
    `sub.best` dans un sous-bucket de la `SortedList` -- le `best` de la racine reste nul PAR
    CONSTRUCTION. Un lecteur qui s'arrete a `best` rend donc « empty » sur un bucket PLEIN.

    Cet etage joue `ncEvaluate` sur `1043 ThunderousAssault` (porteur `templSwordBrother`) et
    DISCRIMINE tout seul le host qui le porte de celui qui ne le porte pas :
      * reponse SANS le champ `via`      -> host NON patche  = TEMOIN AVANT (on attend « empty ») ;
      * reponse AVEC le champ `via`      -> host patche      = on attend des utilites.
    Le meme probe sert donc avant et apres la fenetre, sans etre reecrit -- et il ne peut pas
    rendre un faux vert sur un host non patche, puisqu'il sait lequel il interroge.
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ROOT = PYDIR.parents[1]

import build_pin                                           # noqa: E402  (apres `sys.path`)


def _build_courant() -> str:
    """Le build qui FAIT FOI, jamais un hash ecrit ici (#10027).

    Ce probe confronte une adresse de capteur a celle que `ghidra/functions.tsv` donne pour le
    MEME symbole : les deux DOIVENT venir du build charge. Le hash etait en dur (`rnca9r7q6c`) et
    a survecu a deux mises a jour du jeu -- la confrontation lisait donc une table qui ne decrit
    plus le binaire, et son accord comme son desaccord ne voulaient plus rien dire."""
    try:
        return build_pin.versioned_build()
    except build_pin.BuildPinRefused:
        return "?"


def _ghidra_tsv():
    """`Path` de la table du build courant, ou `None` -- NON MESURE, jamais un chemin devine."""
    try:
        return build_pin.functions_tsv()
    except build_pin.BuildPinRefused:
        return None

#: Les quatre methodes d'utilite que le capteur sait ancrer, et ce qu'elles rendent.
ANCHOR_METHODS = (
    "EvaluateNonComparable",
    "CalculateCustomUtility",
    "GetTargetUtility",
    "CalculateCasterPositionUtility",
)

#: Echantillon d'ancres a confronter. Choisi pour couvrir les QUATRE methodes, pas pour flatter :
#: on y met les deux seuls porteurs de `GetTargetUtility`, ceux de `CalculateCasterPositionUtility`,
#: et des porteurs de chacune des deux methodes de masse.
SAMPLE = (
    ("IdunBattle.AI.Playbook.Loki", "HailstrikePlaybook"),
    ("IdunBattle.AI.Playbook.Loki", "StormcallerPlaybook"),
    ("IdunBattle.AI.Playbook.Loki", "MightFromBelowPlaybook"),
    ("IdunBattle.AI.Playbook.Loki", "BlackRagePlaybook"),
    ("IdunBattle.AI.Playbook.Loki", "ThunderousAssaultPlaybook"),
    ("IdunBattle.AI.Playbook.Loki", "OverwhelmingWrathPlaybook"),
    ("IdunBattle.AI.Playbook.Loki", "CrusadeOfWrathPlaybook"),
    ("IdunBattle.AI.Playbook.Loki", "MassDriverAcceleratorPlaybook"),
    ("IdunBattle.AI.Playbook", "ArcScourgePlaybook"),
)

#: Montage REPRIS de `#977` -- positions FORCEES par `--place` / `--a-place`. C'est le regime ou
#: le natif RETIENT effectivement l'ability : un montage a deux unites lachees au spawn ne la
#: proposait pas, et « non propose » se serait alors lu a tort comme « bucket vide ».
_FIXTURE_1043 = {
    "ability": 1043, "carrier": "templSwordBrother",
    "seed": 777, "board": "MC1_67", "rank": 5,
    "p_units": "worldJakhal,worldEightbound,genesPatriarch,templSwordBrother",
    "a_units": "necroWarden,necroDestroyer,tauCrisis,ultraTitus",
    "place": ["worldJakhal:3,4", "worldEightbound:2,5", "genesPatriarch:1,4",
              "templSwordBrother:4,3"],
    "a_place": ["necroWarden:3,5", "necroDestroyer:4,4", "tauCrisis:2,4", "ultraTitus:5,4"],
}


# --- table des symboles (offline) ------------------------------------------------------------

def ghidra_addresses() -> dict:
    """`symbole -> adresse` pour toutes les ancres du namespace Playbook. Derive de la table
    VERSIONNEE, jamais d'une constante recopiee."""
    out = {}
    tsv = _ghidra_tsv()
    if tsv is None or not tsv.exists():
        return out
    with io.open(str(tsv), "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 2:
                continue
            sym = p[1]
            if not sym.startswith("IdunBattle.AI.Playbook"):
                continue
            if "$$" not in sym:
                continue
            meth = sym.split("$$", 1)[1]
            if meth in ANCHOR_METHODS:
                out[sym] = p[0].lower()
    return out


#: Offsets des champs de `Bucket<T>`, LUS AU DECOMPILE (donc independants de l'API IL2CPP) :
#:   `ComparablePlaybook<T>$$EvaluateInternal`   -> `*(bucket + 0x20) = 0`  et  `+0x10`/`+0x18`
#:   `Bucket<T>$$AddActionToBucket`              -> `*(bucket + 0x28)`  (la SortedList)
#:   `Bucket<T>$$IsValidAction`                  -> `bucket + 0x10`     (le Nullable<Fix64>)
#: Ils servent de TEMOIN a l'etage 0 : ce ne sont pas des valeurs que le code utilise, ce sont
#: celles auxquelles on CONFRONTE ce que l'API resout.
OFFSETS_DECOMPILE = {"best": 0x20, "subBuckets": 0x28, "minUtility": 0x10}


def _rpc_mod():
    from rl_collect_batch import _resolve_session, _rpc          # noqa: E402
    return _resolve_session, _rpc


def _r(rpc, sid, m, b, t=90):
    return (rpc(sid, m, [b], timeout=t).get("result") or {})


# --- etage 0 ---------------------------------------------------------------------------------

def step0_layout(rpc, sid, verbose: bool = True) -> dict:
    """Le layout de `Bucket<T>` que le decodeur INJECTE a resolu, confronte au DECOMPILE.

    C'est le garde qui manquait, et son absence a coute une fenetre entiere : le decodeur resolvait
    ses offsets sur `findClassAnywhere("Bucket`1")`, c'est-a-dire la DEFINITION GENERIQUE, sur
    laquelle `il2cpp_field_get_offset` rend `0x0` pour TOUS les champs -- les offsets d'un generique
    dependent de `T`. Les NOMS, eux, se resolvaient parfaitement, donc le rapport de layout etait
    parfaitement rassurant pendant que le decodeur lisait `bucket+0x0`, le pointeur de classe.

    Un offset d'instance NUL n'est pas une valeur du domaine : `+0x0` est l'en-tete d'objet, jamais
    un champ. C'est donc un ROUGE, et il se voit AVANT tout montage de runner.
    """
    lst = _r(rpc, sid, "playbookUtilityTrace", {"action": "list"}, 300)
    if not lst.get("ok"):
        return {"ok": None, "skipped": "RPC `playbookUtilityTrace` indisponible (capteur absent "
                                       "du bundle injecte)"}
    lay = lst.get("bucketLayout") or {}
    out = {"resolved": lay.get("resolved"), "error": lay.get("error"),
           "pending": lay.get("pending"), "raw": lay.get("bucket")}
    champs = lay.get("bucket") or {}
    lus = {}
    for cle, champ in (("best", "best"), ("subBuckets", "subBuckets"),
                       ("minUtility", "minUtility")):
        v = champs.get(champ)
        if isinstance(v, str) and "@0x" in v:
            lus[cle] = int(v.split("@0x")[1], 16)
    out["offsets"] = {k: hex(v) for k, v in lus.items()}
    nuls = [k for k, v in lus.items() if v == 0]
    ecarts = {k: (hex(v), hex(OFFSETS_DECOMPILE[k]))
              for k, v in lus.items()
              if k in OFFSETS_DECOMPILE and v != OFFSETS_DECOMPILE[k]}
    out["nuls"] = nuls
    out["ecarts_vs_decompile"] = ecarts

    if lay.get("pending"):
        # Le layout ne se resout qu'a partir d'un objet reel : rien decode encore n'est PAS un
        # echec, et surtout pas un vert.
        out["ok"] = None
        out["note"] = "layout PAS ENCORE resolu (aucun bucket decode) -- ni vert ni rouge"
    elif not lus:
        out["ok"] = None
        out["note"] = "aucun offset publie par le capteur -- rien a confronter"
    elif nuls:
        out["ok"] = False
        out["note"] = ("offsets NULS sur %s : signature d'une DEFINITION GENERIQUE non inflatee. "
                       "Le decodeur lit l'en-tete d'objet a la place des champs." % ", ".join(nuls))
    elif ecarts:
        out["ok"] = False
        out["note"] = ("offsets resolus != decompile : %s (lu, attendu)" % ecarts)
    else:
        out["ok"] = True
        out["note"] = "offsets resolus CONCORDANTS avec le decompile"

    if verbose:
        print("\n[988/0] LAYOUT de `Bucket<T>` resolu par le decodeur INJECTE")
        print("   offsets lus : %s" % (out["offsets"] or "<aucun>"))
        print("   attendus (decompile) : %s"
              % {k: hex(v) for k, v in OFFSETS_DECOMPILE.items()})
        marque = {True: "OK", False: "ROUGE", None: "NON CONFRONTE"}[out["ok"]]
        print("   -> %s : %s" % (marque, out["note"]))
    return out


# --- etage 1 ---------------------------------------------------------------------------------

def step1_ancres(rpc, sid, verbose: bool = True) -> dict:
    table = ghidra_addresses()
    if not table:
        return {"ok": None, "skipped": "table ghidra/functions.tsv absente pour le build " + _build_courant()}
    # `interfaceSlotProbe` exige une interface ; on prend `IPlaybook`. Si la classe ne
    # l'implemente pas, `interfaceOffset` sort a `None` et les slots rendus sont ceux de la
    # vtable BRUTE -- ce qui est exactement ce qu'on veut balayer ici.
    r = _r(rpc, sid, "interfaceSlotProbe", {
        "iface": {"ns": "IdunBattle.AI.Playbook", "cls": "IPlaybook"},
        "impls": [{"ns": ns, "cls": cls} for ns, cls in SAMPLE],
        "slots": list(range(0, 96)),
    }, 120)
    if not r.get("ok"):
        return {"ok": None, "skipped": "interfaceSlotProbe indisponible : %r" % (r.get("error"),)}

    rows = []
    for impl in r.get("impls") or []:
        cls, ns = impl.get("cls"), impl.get("ns")
        if not impl.get("ok"):
            rows.append({"playbook": cls, "verdict": "CLASSE NON RESOLUE",
                         "error": impl.get("error")})
            continue
        seen = {}
        for slot in impl.get("slots") or []:
            nm = slot.get("implMethod")
            if nm in ANCHOR_METHODS and nm not in seen:
                seen[nm] = slot
        for meth in ANCHOR_METHODS:
            sym = "%s.%s$$%s" % (ns, cls, meth)
            expected = table.get(sym)
            if expected is None:
                continue          # ce playbook ne porte pas cette methode : rien a confronter
            slot = seen.get(meth)
            if slot is None:
                rows.append({"playbook": cls, "method": meth, "expected": expected,
                             "verdict": "NON VIRTUELLE (hors vtable)",
                             "note": "absente de la vtable : NE PROUVE RIEN sur l'atteignabilite "
                                     "-- le hook s'y attache par `findMethod`, pas par un slot"})
                continue
            got = (slot.get("ghidraVA") or "").lower().replace("0x", "")
            exp = expected.replace("0x", "")
            rows.append({"playbook": cls, "method": meth, "slot": slot.get("slot"),
                         "expected": exp, "got": got,
                         "verdict": "ADRESSABLE" if got == exp else "DIVERGENCE"})

    confirmed = [x for x in rows if x.get("verdict") == "ADRESSABLE"]
    diverged = [x for x in rows if x.get("verdict") == "DIVERGENCE"]
    nonvirt = [x for x in rows if x.get("verdict") == "NON VIRTUELLE (hors vtable)"]
    unresolved = [x for x in rows if x.get("verdict") == "CLASSE NON RESOLUE"]

    out = {"ok": bool(confirmed) and not diverged and not unresolved,
           "nConfirmed": len(confirmed), "nDiverged": len(diverged),
           "nNonVirtual": len(nonvirt), "nUnresolved": len(unresolved),
           "rows": rows}
    if verbose:
        print("\n[988/1] ATTEIGNABILITE DES ANCRES (aucune fenetre requise)")
        for x in rows:
            if x.get("verdict") == "ADRESSABLE":
                print("   OK    %-30s %-32s slot %-3s 0x%s"
                      % (x["playbook"], x["method"], x.get("slot"), x["got"]))
            elif x.get("verdict") == "DIVERGENCE":
                print("   DIVER %-30s %-32s attendu 0x%s, lu 0x%s"
                      % (x["playbook"], x["method"], x["expected"], x["got"]))
            elif x.get("verdict") == "NON VIRTUELLE (hors vtable)":
                print("   n/v   %-30s %-32s (hors vtable -- ne prouve rien)"
                      % (x["playbook"], x["method"]))
            else:
                print("   KO    %-30s %s" % (x["playbook"], x.get("error")))
        print("   -> %d adressable(s), %d divergence(s), %d non virtuelle(s), %d non resolue(s)"
              % (len(confirmed), len(diverged), len(nonvirt), len(unresolved)))
        # Un ensemble VIDE passerait pour un vert : on le dit.
        if not confirmed:
            print("   -> AUCUNE ancre confirmee : ce n'est PAS un vert, c'est une mesure vide")
    return out


# --- etage 2 ---------------------------------------------------------------------------------

def _build(state_file: Path, fx: dict) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(fx["seed"]),
           "--board", fx["board"], "--rank", str(fx["rank"]),
           "--state-file", str(state_file), "--no-ai",
           "--p-units", fx["p_units"], "--a-units", fx["a_units"]]
    for p in fx.get("place") or []:
        cmd += ["--place", p]
    for p in fx.get("a_place") or []:
        cmd += ["--a-place", p]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def step2_bucket(rpc, sid, state_file: Path, verbose: bool = True) -> dict:
    fx = _FIXTURE_1043
    try:
        rid = _build(state_file, fx)
    except Exception as e:                                          # noqa: BLE001
        return {"ok": None, "skipped": "montage impossible : %s" % e}

    try:
        # ⚠ L'identite d'unite qu'acceptent les RPC d'oracle est `squadId`, PAS `entityId` :
        # mesure #977, et `ncEvaluate` repond « unit N not found » sur un `entityId`. Le nom du
        # catalogue se lit dans `visualId`.
        units = _r(rpc, sid, "observeBattle", {"runnerId": rid}, 60).get("units") or []
        cid = None
        for u in units:
            if u.get("visualId") == fx["carrier"] and not u.get("isDead"):
                cid = u.get("squadId")
                break
        if cid is None:
            return {"ok": None,
                    "skipped": "porteur %s absent du runner (visualId vus : %s)"
                               % (fx["carrier"],
                                  sorted({str(u.get("visualId")) for u in units}))}
        # CONTRE-EPREUVE PAR DES CANAUX INDEPENDANTS -- deux, parce que le premier peut mentir.
        #
        # Canal A : `bucket-audit`, qui ancre `Bucket<T>$$AddActionToBucket` et publie chaque
        # action poussee avec son `weightBucket` et son utilite.
        # ⚠ On lit son DIAGNOSTIC avant de lui accorder la moindre valeur, et ce n'est pas une
        # precaution de style : sur un premier montage (deux unites lachees au spawn) il a rendu
        # 0 fire sur TOUS ses compteurs, ce qui se lit exactement comme le piege du gshared -- un
        # hook `enabled` qui ne fire jamais. C'etait FAUX : sur le montage a positions forcees il
        # fire. Le zero venait du MONTAGE (aucune action poussee), pas du hook. Un canal muet ne
        # prouve donc ni la vacuite ni sa propre mort ; `auditAlive` separe les deux.
        #
        # Canal B : `aiDryRunAllUnits`, qui demande au natif l'action qu'il RETIENDRAIT. Il ne
        # partage aucun code de lecture de bucket avec `ncEvaluate`. S'il propose l'ability alors
        # que `ncEvaluate` rend « empty » partout, la vacuite est REFUTEE.
        _r(rpc, sid, "bucketAuditReset", {}, 30)
        r = _r(rpc, sid, "ncEvaluate",
               {"runnerId": rid, "unitId": int(cid),
                "abilityType": fx["ability"], "sweep": True}, 240)
        dump = _r(rpc, sid, "bucketAuditDumpAdded", {"max": 400}, 60)
        audit_status = _r(rpc, sid, "bucketAuditStatus", {}, 30)
        dry = _r(rpc, sid, "aiDryRunAllUnits", {"runnerId": rid}, 240)
    finally:
        try:
            _r(rpc, sid, "disposeRunner", {"runnerId": rid}, 30)
        except Exception:                                           # noqa: BLE001
            pass

    positions = r.get("positions") or []
    # LE DISCRIMINANT : le champ `via` n'existe que sur un host portant le correctif #988.
    patched = any("via" in p for p in positions)

    entries = dump.get("entries") or dump.get("added") or []
    # Les pushes passes par `AddActionToBucket` -- ceux qui atterrissent dans un SOUS-bucket.
    to_sub = [e for e in entries if e.get("weightBucket") is not None]
    utils_sub = [e.get("utility") for e in to_sub
                 if isinstance(e.get("utility"), (int, float))]
    # Canal A vivant ? Un capteur a 0 fire sur TOUS ses compteurs est INERTE, pas temoin de vide.
    adiag = audit_status.get("diag") or {}
    audit_alive = any(isinstance(v, int) and v > 0 for v in adiag.values())
    # Canal B : le natif propose-t-il CETTE ability pour CE caster ?
    dry_txt = json.dumps(dry, ensure_ascii=True)
    dry_proposes = ('"abilityType": %d' % fx["ability"]) in dry_txt \
        or ('"ability": %d' % fx["ability"]) in dry_txt
    scored = [p for p in positions if isinstance(p.get("util"), (int, float))]
    empty = [p for p in positions if p.get("bucket") == "empty"]
    via_sub = [p for p in positions if p.get("via") == "subBuckets"]

    out = {"host_patched": patched, "nPositions": len(positions),
           "nScored": len(scored), "nEmpty": len(empty), "nViaSubBuckets": len(via_sub),
           "playbookClass": r.get("playbookClass"), "evalName": r.get("evalName"),
           "utils": [round(float(p["util"]), 4) for p in scored[:8]],
           "auditAdded": len(entries), "auditToSubBucket": len(to_sub),
           "auditUtils": [round(float(u), 4) for u in utils_sub[:8]]}
    if not positions:
        out["ok"] = None
        out["skipped"] = "aucune position rendue -- regime non atteint, PAS un echec de port"
    elif not patched:
        # TEMOIN AVANT : on ATTEND le faux negatif, et la CONTRE-EPREUVE doit le refuter.
        out["ok"] = None
        out["temoin"] = ("host NON patche : %d/%d positions rendues « empty ». C'est le FAUX "
                         "NEGATIF que #988 corrige -- pas un verdict sur le port."
                         % (len(empty), len(positions)))
        # Le verrou : la vacuite annoncee est-elle REFUTEE par un canal independant ?
        all_empty = len(empty) == len(positions)
        out["refute"] = all_empty and (bool(to_sub) or dry_proposes)
        if not audit_alive:
            out["auditNote"] = ("canal A MUET : `bucket-audit` est arme (%s listeners) mais rend "
                                "0 fire sur TOUS ses compteurs. Cela ne tranche PAS entre « hook "
                                "mort » et « ce montage ne pousse rien » -- ne rien conclure de "
                                "ce silence." % audit_status.get("listeners"))
        # LA PREDICTION QUE LA FENETRE DEVRA VERIFIER : le host patche doit rendre, pour au moins
        # une position, une utilite APPARTENANT aux utilites que le canal A a vu pousser.
        if utils_sub:
            out["attenduApresPatch"] = sorted({round(float(u), 4) for u in utils_sub})
    else:
        # HOST PATCHE : le bucket doit maintenant porter des utilites, et elles doivent
        # CONCORDER avec ce que le canal A a vu pousser -- pas seulement etre non vides.
        attendu = {round(float(u), 4) for u in utils_sub}
        obtenu = {round(float(p["util"]), 4) for p in scored}
        out["ok"] = bool(scored) and (not attendu or bool(attendu & obtenu))
        out["attendu"] = sorted(attendu)
        out["obtenu"] = sorted(obtenu)[:8]
        if not scored:
            out["echec"] = ("host patche mais AUCUNE position scoree : soit le decodeur ne lit "
                            "pas la SortedList, soit le bucket est reellement vide (regarder "
                            "`actionCount`).")
        elif attendu and not (attendu & obtenu):
            out["echec"] = ("host patche et positions scorees, mais AUCUNE utilite ne concorde "
                            "avec celles que `bucket-audit` a vu pousser (%s vs %s) : le "
                            "decodeur lit quelque chose, mais pas la bonne valeur."
                            % (sorted(attendu), sorted(obtenu)[:8]))
    if verbose:
        print("\n[988/2] LE BUCKET MENT-IL ? -- `ncEvaluate` sur %d %s (%s)"
              % (fx["ability"], "ThunderousAssault", fx["carrier"]))
        print("   host patche (#988) : %s" % ("OUI" if patched else "NON"))
        print("   playbook=%s eval=%s" % (out["playbookClass"], out["evalName"]))
        print("   positions=%d scorees=%d empty=%d via-subBuckets=%d"
              % (len(positions), len(scored), len(empty), len(via_sub)))
        print("   CANAL A (bucket-audit) : %d push(es) dont %d vers un SOUS-bucket ; vivant=%s"
              % (len(entries), len(to_sub), audit_alive))
        if utils_sub:
            print("      utilites poussees : %s" % out["auditUtils"])
        if out.get("auditNote"):
            print("      -> %s" % out["auditNote"])
        print("   CANAL B (aiDryRunAllUnits) : le natif propose-t-il %d ? %s"
              % (fx["ability"], "OUI" if dry_proposes else "non"))
        if out.get("refute"):
            print("      -> VACUITE REFUTEE : le bucket est PLEIN, seul le LECTEUR ne le "
                  "voyait pas.")
        if out.get("temoin"):
            print("   -> TEMOIN AVANT : %s" % out["temoin"])
        elif out.get("echec"):
            print("   -> ECHEC : %s" % out["echec"])
        elif out.get("skipped"):
            print("   -> NON CONFRONTE : %s" % out["skipped"])
        else:
            print("   -> OK, utilites : %s" % out["utils"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--avec-runner", action="store_true",
                    help="joue aussi l'etage 2 (monte un runner)")
    ap.add_argument("--state-file", default=str(ROOT / "logs" / "probe_988_state.json"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    res = {"build": _build_courant()}
    try:
        resolve_session, rpc = _rpc_mod()
        sid = resolve_session()
    except Exception as e:                                          # noqa: BLE001
        print("[988] NON CONFRONTE -- plateforme indisponible : %s" % e)
        return 0

    res["step0"] = step0_layout(rpc, sid, verbose=not a.json)
    res["step1"] = step1_ancres(rpc, sid, verbose=not a.json)
    if a.avec_runner:
        res["step2"] = step2_bucket(rpc, sid, Path(a.state_file), verbose=not a.json)

    if a.json:
        print(json.dumps(res, indent=2))
    # rc 1 UNIQUEMENT sur un `ok: False` franc. Un `None` est un NON CONFRONTE, pas un rouge.
    bad = [k for k, v in res.items()
           if isinstance(v, dict) and v.get("ok") is False]
    if bad:
        print("\n[988] ROUGE sur : %s" % ", ".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
