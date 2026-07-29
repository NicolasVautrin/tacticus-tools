"""#263 -- un `applyAction` MAL CONSTRUIT doit echouer FORT, jamais rendre une mesure.

LE COUT MESURE (2026-07-29) : deux agents independants ont ecrit `{"kind":"attack", ...}`.
`applyOneAction` ne connait que move|ability|finish|endturn, et rendait `ok:false` dans une
enveloppe PAR AILLEURS NORMALE (`changes:[]`, `events:[]`, `eventCount:0`). Aucun des ~250
montages Python ne lit `ok`. Une attaque JAMAIS EMISE se lisait donc comme « une attaque qui
n'a rien fait » -- c'est-a-dire comme un RESULTAT. L'un a perdu 13 attaques, l'autre a
diagnostique « l'ennemi n'inflige aucun degat » alors que l'ennemi n'attaquait pas du tout.
Les deux ont d'abord accuse le jeu (armure ? immunite ? type de degat ?).

CE QUE MESURE CETTE SONDE, sur un runner reel :
  A. `{"kind":"attack"}`               -> doit lever (HTTP 500), et le message doit APPRENDRE
                                          le chemin propre (ability + NormalAttackType).
  B. `{"kind":"ability"}` sans caster  -> doit lever aussi : meme classe de faute.
  C. un `endturn` bien forme           -> doit passer : la levee ne mange pas le cas normal.
  D. la levee ne rend AUCUNE enveloppe plausible (pas de cle `actions`).

POURQUOI CETTE SONDE UTILISE UN `rpc()` QUI NE RATTRAPE PAS `HTTPError` : c'est EXACTEMENT
le motif des ~250 probes du depot. C'est cette voie-la qu'il fallait rendre bruyante, et
c'est donc elle qu'on mesure -- pas une voie de confort ecrite pour la circonstance.

PAS de kind `attack` ajoute, et c'est la decision : l'attaque normale EST une ability, dont
l'`ActiveAbilityType` est PER-UNIT (`NormalAttackType`, ex. 69 -- pas 17). Un kind dedie
ferait deux facons d'exprimer la meme chose et masquerait quelle ability a tire.

Usage :  python scripts/python/probe_263_apply_action_loud.py
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

HOST = "http://127.0.0.1:8765"
PYDIR = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(os.path.dirname(PYDIR))


def _http(chemin, methode="GET", corps=None, timeout=60):
    """VOLONTAIREMENT sans rattrapage de HTTPError -- cf. l'en-tete."""
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


def appelle(sid, action, rid):
    """-> ('leve', message) si HTTP 500 ; ('rend', resultat) sinon."""
    try:
        return "rend", rpc(sid, "applyAction",
                           [{"runnerId": rid, "action": action}], 60)
    except urllib.error.HTTPError as e:
        corps = e.read().decode("utf-8", "replace")
        try:
            return "leve", json.loads(corps).get("error", corps)
        except ValueError:
            return "leve", corps


def main():
    sid = session_id()
    if not sid:
        print("ECHEC: aucune session Frida vivante")
        return 2
    print("session=%d" % sid)

    etat = os.path.join(RACINE, "logs", "_probe263_state.json")
    if os.path.exists(etat):
        os.remove(etat)
    p = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "777",
         "--board", "MC1_67", "--state-file", etat],
        cwd=PYDIR, capture_output=True, text=True, encoding="utf-8",
        errors="replace")
    if not os.path.exists(etat):
        print("ECHEC build runner: %s" % ((p.stderr or p.stdout or "")[-400:]))
        return 3
    with open(etat, encoding="utf-8") as f:
        rid = json.load(f)["runnerId"]
    print("runner=%d" % rid)

    resultats = []
    try:
        cas = [
            ("A kind attack", {"kind": "attack", "casterId": 1, "targetId": 2}, True),
            ("B ability sans casterId", {"kind": "ability", "targetId": 2}, True),
            ("C endturn bien forme", {"kind": "endturn"}, False),
        ]
        for nom, action, doit_lever in cas:
            forme, charge = appelle(sid, action, rid)
            a_leve = (forme == "leve")
            verdict = "OK" if a_leve == doit_lever else "ECHEC"
            resultats.append((nom, verdict))
            print("\n[%s] %s" % (verdict, nom))
            print("     forme=%s" % forme)
            if a_leve:
                print("     message=%s" % str(charge)[:300])
            else:
                cles = sorted(charge.keys()) if isinstance(charge, dict) else type(charge)
                print("     cles=%s" % (cles,))
                if isinstance(charge, dict):
                    print("     ok=%r  actions=%d"
                          % (charge.get("ok"), len(charge.get("actions") or [])))

        # D -- la levee ne doit pas ressembler a une mesure.
        forme, charge = appelle(sid, {"kind": "attack"}, rid)
        pas_d_enveloppe = (forme == "leve")
        resultats.append(("D aucune enveloppe plausible",
                          "OK" if pas_d_enveloppe else "ECHEC"))
        print("\n[%s] D aucune enveloppe plausible (pas de cle `actions`)"
              % ("OK" if pas_d_enveloppe else "ECHEC"))

        # Le message doit APPRENDRE le chemin, pas seulement refuser.
        forme, msg = appelle(sid, {"kind": "attack"}, rid)
        instructif = forme == "leve" and "ability" in str(msg) \
            and "NormalAttackType" in str(msg)
        resultats.append(("E message instructif", "OK" if instructif else "ECHEC"))
        print("\n[%s] E le message enseigne le chemin propre"
              % ("OK" if instructif else "ECHEC"))
    finally:
        try:
            rpc(sid, "disposeRunner", [{"runnerId": rid}], 20)
        except Exception:
            pass
        if os.path.exists(etat):
            os.remove(etat)

    print("\n" + "=" * 70)
    for nom, v in resultats:
        print("  %-38s %s" % (nom, v))
    echecs = [n for n, v in resultats if v != "OK"]
    print("\n%d/%d OK" % (len(resultats) - len(echecs), len(resultats)))
    return 0 if not echecs else 1


if __name__ == "__main__":
    sys.exit(main())
