"""#262 / #259-b -- le MethodInfo d'une instance INFLATEE porte-t-il le CORPS PARTAGE ?

QUESTION, et elle est binaire : un hook peut-il resoudre AU RUNTIME une methode dont le
corps est un generique PLEINEMENT PARTAGE (`__Il2CppFullySharedGenericType`) ? Si oui, la
voie (c) de `docs/rl/case-259-couverture-gshared.md` est vivante et les adresses en dur de
`frida/hooks/features/scorer-damage-trace.ts` peuvent disparaitre au profit d'une resolution
qui survit a chaque build. Si non, seule la voie (a) -- la table Il2CppDumper -- tient.

CE QUI EST DEJA TRANCHE (ne pas le refaire) : la voie (b) est REFUTEE AU DECOMPILE. Le
`methodPointer` d'une DEFINITION generique
(`IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1$$Init`) est un THUNK D'INVOCATION : il
empile ses arguments puis saute a `MethodInfo.invoker_method`. La question ouverte porte sur
les instances INFLATEES, pas sur les definitions.

METHODE -- aller-retour, aucune adresse ecrite en dur :
  1. RPC `resolveMethodPtr` : remonte la chaine de parents d'une classe de playbook CONCRETE
     et rend, par niveau, le pointeur d'entree de la methode nommee.
  2. Chaque adresse rendue est traduite en `<symbole>+0x<offset>` par recherche dans
     `data/symbols/<build>/ghidra/functions.tsv` -- la meme table que celle retablie par
     #259-a. On ne COMPARE donc a aucune constante : on demande a la table qui habite la.

DISCRIMINANT SUPPLEMENTAIRE : on interroge PLUSIEURS playbooks concrets. Un corps PARTAGE
rend la MEME adresse pour tous ; du code par instanciation en rendrait une par classe.

Usage :  python scripts/python/probe_262_gshared_runtime.py
"""
import bisect
import json
import os
import sys
import urllib.error
import urllib.request

HOST = "http://127.0.0.1:8765"
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Sous-classes CONCRETES dont classes.tsv donne le parent `ComparablePlaybook`1`.
# Plusieurs, et c'est le point : un corps partage rend la meme adresse pour toutes.
CIBLES = [
    ("IdunBattle.AI.Playbook", "MurderousSwingPlaybook"),
    ("IdunBattle.AI.Playbook", "BlightGrenadesPlaybook"),
    ("IdunBattle.AI.Playbook", "EntropyCannonsPlaybook"),
    ("IdunBattle.AI.Playbook", "LightOfSanguiniusPlaybook"),
]
METHODES = ["CalculateActionUtility", "CalculateUtilityFromTilePrediction"]

# Le marqueur du mecanisme, pas d'un namespace (cf. axe 5 de symbols_sync.py).
MARQUEUR = "__Il2CppFullySharedGeneric"


def _http(chemin, methode="GET", corps=None, timeout=60):
    req = urllib.request.Request(
        HOST + chemin, method=methode,
        data=None if corps is None else json.dumps(corps).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def session_id():
    st = _http("/api/admin/status")
    return int((st.get("session") or {}).get("id"))


def rpc(sid, methode, args, timeout=90.0):
    out = _http("/api/scripts/%d/rpc" % sid, "POST",
                {"method": methode, "args": args, "timeout": int(timeout * 1000)},
                timeout + 10)
    return out.get("result")


def build_courant():
    with open(os.path.join(RACINE, "data", "symbols", "CURRENT"), encoding="utf-8") as f:
        return f.read().strip()


def charge_table(build):
    """-> (liste triee d'adresses, liste parallele de symboles)."""
    chemin = os.path.join(RACINE, "data", "symbols", build, "ghidra", "functions.tsv")
    adresses, symboles = [], []
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            if ligne.startswith("#"):
                continue
            morceaux = ligne.rstrip("\n").split("\t")
            if len(morceaux) < 2:
                continue
            try:
                adresses.append(int(morceaux[0], 16))
            except ValueError:
                continue
            symboles.append(morceaux[1])
    ordre = sorted(range(len(adresses)), key=lambda i: adresses[i])
    return [adresses[i] for i in ordre], [symboles[i] for i in ordre]


def whereis(adresses, symboles, va):
    """VA -> '<symbole>+0x<offset>' (la fonction qui CONTIENT va), ou None."""
    if va == 0:
        return None
    i = bisect.bisect_right(adresses, va) - 1
    if i < 0:
        return None
    delta = va - adresses[i]
    return symboles[i] if delta == 0 else "%s+0x%x" % (symboles[i], delta)


def main():
    build = build_courant()
    adresses, symboles = charge_table(build)
    print("build=%s  table=%d fonctions" % (build, len(adresses)))

    sid = session_id()
    if not sid:
        print("ECHEC: aucune session Frida vivante")
        return 2
    print("session=%d" % sid)

    targets = [{"ns": ns, "cls": cls, "method": m}
               for (ns, cls) in CIBLES for m in METHODES]
    res = rpc(sid, "resolveMethodPtr", [{"targets": targets, "maxDepth": 6}], 90)
    if not res or not res.get("ok"):
        print("ECHEC RPC: %r" % (res,))
        return 3

    # adresse d'entree -> ensemble des classes concretes qui y menent
    partage = {}
    verdicts = []
    for t in res["targets"]:
        etiquette = "%s.%s::%s" % (t["ns"], t["cls"], t["method"])
        if not t.get("ok"):
            print("\n%s\n  INTROUVABLE: %s" % (etiquette, t.get("error")))
            verdicts.append((etiquette, "CLASSE INTROUVABLE"))
            continue
        print("\n%s" % etiquette)
        trouve = None
        for niveau in t["levels"]:
            if not niveau["methods"]:
                print("  [%d] %-62s (pas de methode de ce nom)"
                      % (niveau["depth"], niveau["name"]))
                continue
            for m in niveau["methods"]:
                entree = int(m["entry"]["ghidraVA"], 16)
                brut = int(m["raw"]["ghidraVA"], 16)
                invoker = int(m["invoker"]["ghidraVA"], 16)
                sym_e = whereis(adresses, symboles, entree)
                print("  [%d] %s  params=%s"
                      % (niveau["depth"], niveau["name"], m["paramCount"]))
                print("       entry   -> %s" % (sym_e or "(nul / hors table)"))
                if brut != entree:
                    print("       raw     -> %s"
                          % (whereis(adresses, symboles, brut) or "(nul)"))
                print("       invoker -> %s"
                      % (whereis(adresses, symboles, invoker) or "(nul)"))
                if sym_e and MARQUEUR in sym_e and trouve is None:
                    trouve = (niveau["depth"], niveau["name"], sym_e, entree)
        if trouve:
            profondeur, nom, sym, va = trouve
            exact = "+0x" not in sym
            verdicts.append((etiquette,
                             "CORPS PARTAGE a la profondeur %d%s"
                             % (profondeur, "" if exact else " (PAS au debut !)")))
            partage.setdefault((t["method"], va), []).append(t["cls"])
        else:
            verdicts.append((etiquette, "AUCUN corps partage dans la chaine"))

    print("\n" + "=" * 78)
    print("VERDICT PAR CIBLE")
    for etiquette, v in verdicts:
        print("  %-58s %s" % (etiquette, v))

    print("\nADRESSES PARTAGEES ENTRE CLASSES CONCRETES")
    if not partage:
        print("  (aucune)")
    for (methode, va), classes in sorted(partage.items()):
        print("  %-34s @%x  <- %d classe(s): %s"
              % (methode, va, len(classes), ", ".join(sorted(classes))))

    ok = all(v.startswith("CORPS PARTAGE") for _, v in verdicts) and verdicts
    une_seule = all(len(c) == len(CIBLES) for c in partage.values())
    print("\nREPONSE A #259-b :")
    if ok and une_seule:
        print("  VOIE (c) VIVANTE -- le MethodInfo d'une instance inflatee porte bien le")
        print("  corps PARTAGE, identique pour toutes les classes concretes. Un hook peut")
        print("  resoudre sa cible au runtime ; les adresses en dur peuvent tomber.")
        return 0
    if ok and not une_seule:
        print("  MITIGE -- un corps est resolu, mais PAS le meme pour toutes les classes.")
        print("  A relire cible par cible avant d'en tirer une regle.")
        return 1
    print("  VOIE (c) MORTE -- la resolution runtime ne rend pas le corps partage.")
    print("  La table Il2CppDumper (voie (a), livree par #259-a) reste la seule source.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
