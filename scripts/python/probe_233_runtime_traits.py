"""#233 -- `combatSnapshot.units[].traits` publie-t-il les traits REELLEMENT portes en bataille ?

LE MANQUE : aucun RPC n'exposait les traits runtime. Le port les RECONSTRUISAIT depuis le substrat
(gameconfig + derivation d'alliance) et depuis son propre leaf `AddTrait` -- il ne pouvait donc
CONFRONTER aucun des 33 gates de traits recenses. Un trait accorde EN BATAILLE lui etait invisible.

SEMANTIQUE, lue au decompile de `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` :

    HasTrait(t) == !retires(+0x50).Contains(t)
                   && ( permanents(+0x40).Contains(t) || temporaires(+0x48).Contains(t) )

`AddTraitOperation$$Execute` ecrit +0x40 (isTemporary==0) ou +0x48 (sinon).
⚠ `RemoveTraitOperation$$RemoveTrait` NE remplit PAS +0x50 : il RETIRE de +0x40/+0x48 selon le
meme `isTemporary`. Le retrait est DESTRUCTIF sur les ensembles additifs, pas additif sur un
ensemble de veto -- l'ecrivain de +0x50 reste a identifier.

CE QUE MESURE CETTE SONDE :
  A. le canal REPOND : `traits` est une LISTE (pas `null`) pour toutes les unites vivantes ;
  B. il est DISCRIMINANT : au moins deux unites ont des ensembles differents (un canal qui rend
     la meme chose partout ne prouve rien) ;
  C. il ACCORDE avec le natif, un trait a la fois : pour un echantillon de (unite, trait), la
     presence dans `traits` == `HasTrait` invoque... ce qui serait circulaire. On confronte donc a
     une SECONDE SOURCE INDEPENDANTE : les traits de DEPART du gameconfig. Tout trait du
     gameconfig doit etre present ; l'inverse est faux (les ajouts de bataille sont EN PLUS), et
     c'est precisement l'ecart qu'on cherche a rendre visible.

Usage :  python scripts/python/probe_233_runtime_traits.py
"""
import json
import os
import subprocess
import sys
import urllib.request

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(PYDIR))
ETAT = os.path.join(RACINE, "logs", "_probe233_state.json")


def _http(chemin, methode="GET", corps=None, timeout=120):
    req = urllib.request.Request(
        HOST + chemin, method=methode,
        data=None if corps is None else json.dumps(corps).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def session_id():
    return int((_http("/api/admin/status").get("session") or {}).get("id"))


def rpc(sid, methode, args, timeout=180.0):
    return _http("/api/scripts/%d/rpc" % sid, "POST",
                 {"method": methode, "args": args, "timeout": int(timeout * 1000)},
                 timeout + 10).get("result")


def main():
    sid = session_id()
    if not sid:
        print("ECHEC: aucune session Frida vivante")
        return 2
    print("session=%d" % sid)

    noms = rpc(sid, "dumpEnum", [{"asm": "IdunSharedAssembly.dll",
                                 "ns": "IdunBattle.Entities.Enum",
                                 "cls": "UnitTrait"}], 60)
    par_valeur = {}
    for k, v in ((noms or {}).get("values") or {}).items():
        par_valeur.setdefault(int(v), []).append(k)
    print("UnitTrait: %d membres, %d valeurs distinctes"
          % (len(((noms or {}).get("values") or {})), len(par_valeur)))

    if os.path.exists(ETAT):
        os.remove(ETAT)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777",
         "--board", "MC1_67", "--state-file", ETAT],
        cwd=PYDIR, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not os.path.exists(ETAT):
        print("ECHEC build runner: %s" % ((p.stderr or p.stdout or "")[-400:]))
        return 3
    with open(ETAT, encoding="utf-8") as f:
        rid = json.load(f)["runnerId"]
    print("runner=%d" % rid)

    resultats = []
    try:
        snap = rpc(sid, "combatSnapshot", [{"runnerId": rid}], 240)
        unites = (snap or {}).get("units") or []
        print("combatSnapshot: %d unites" % len(unites))

        # A -- le canal repond
        sans = [u["entityId"] for u in unites if u.get("traits") is None]
        ok_a = bool(unites) and not sans
        resultats.append(("A canal renseigne", "OK" if ok_a else "ECHEC"))
        if sans:
            print("  unites a traits=null : %r" % sans[:10])

        # B -- il discrimine
        ensembles = {tuple(sorted(u.get("traits") or ())) for u in unites
                     if u.get("traits") is not None}
        ok_b = len(ensembles) > 1
        resultats.append(("B discriminant", "OK" if ok_b else "ECHEC"))
        print("  %d ensembles de traits DISTINCTS sur %d unites"
              % (len(ensembles), len(unites)))

        def vid_de(u):
            return (u.get("unitConfig") or {}).get("visualId")

        for u in unites[:8]:
            tr = u.get("traits")
            libelles = [par_valeur.get(t, [str(t)])[0] for t in (tr or [])]
            print("  u%-4s %-22s %d traits: %s"
                  % (u.get("entityId"), (vid_de(u) or "?")[:22],
                     len(tr or []), ", ".join(libelles[:8])))

        # C -- accord avec une SECONDE SOURCE INDEPENDANTE : les traits de DEPART du gameconfig,
        # nommes. Le canal les rend en ids d'enum -> on traduit par le nom de membre.
        # Le sens du test est asymetrique, et c'est voulu : tout trait du gameconfig DOIT etre
        # present ; l'inverse est FAUX -- le runtime en ajoute (grande alliance derivee,
        # AddTrait en bataille), et c'est precisement l'ecart que ce canal existe pour montrer.
        sys.path.insert(0, PYDIR)
        manquants, ecarts = [], []
        try:
            import gameconfig as gc
            par_nom = {}
            for k, v in ((noms or {}).get("values") or {}).items():
                par_nom[k] = int(v)
            for u in unites:
                vid, tr = vid_de(u), u.get("traits")
                if not vid or tr is None:
                    continue
                base = (gc.unit(vid) or {}).get("traits") or []
                attendus = [(n, par_nom[n]) for n in base if n in par_nom]
                absents = [n for (n, v) in attendus if v not in set(tr)]
                inconnus = [n for n in base if n not in par_nom]
                if absents or inconnus:
                    manquants.append((vid, absents, inconnus))
                extra = [par_valeur.get(t, [str(t)])[0] for t in tr
                         if t not in {v for (_n, v) in attendus}]
                if extra:
                    ecarts.append((vid, extra))
        except Exception as e:                       # noqa: BLE001
            print("  (source gameconfig non interrogee: %s)" % e)
            resultats.append(("C accord gameconfig", "NON MESURE"))
        else:
            ok_c = not manquants
            resultats.append(("C accord gameconfig", "OK" if ok_c else "ECHEC"))
            if manquants:
                print("  traits de DEPART absents du canal : %r" % manquants[:6])
            print("\n  ECART runtime - gameconfig (LA raison d'etre du canal) :")
            for vid, extra in ecarts[:8]:
                print("    %-22s +%s" % (vid, ", ".join(extra)))
            if not ecarts:
                print("    (aucun -- ce montage n'accorde aucun trait en bataille)")
    finally:
        try:
            rpc(sid, "disposeRunner", [{"runnerId": rid}], 20)
        except Exception:                            # noqa: BLE001
            pass
        if os.path.exists(ETAT):
            os.remove(ETAT)

    print("\n" + "=" * 70)
    for nom, v in resultats:
        print("  %-28s %s" % (nom, v))
    echecs = [n for n, v in resultats if v == "ECHEC"]
    return 0 if not echecs else 1


if __name__ == "__main__":
    sys.exit(main())
