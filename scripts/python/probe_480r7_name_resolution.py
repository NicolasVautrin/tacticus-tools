"""Probe #480-r7 -- LIRE les capteurs de resolution par NOM, cote session et cote host.

POURQUOI CE PROBE EXISTE
------------------------
#480-r7 a trouve trois capteurs qui portaient tous, en toutes lettres, « exporte pour
qu'une MAJ se VOIE » -- et aucun n'avait de lecteur :

  * `pinnedAddressRefusals()`      (`hooks/il2cpp/build-pin.ts`) : les adresses epinglees
    REFUSEES parce que le build charge n'est pas celui sur lequel la VA a ete mesuree ;
  * `EFFECT_TARGET_IDS_FIELD_NAME` (`hooks/game/effects.ts`) : le nom natif du champ
    retenu pour `targetIds`, resolu par OFFSET au chargement ;
  * `BOND_ENTITY_ID_FIELD_NAME`    (idem) : celui de `bondedEntityId`.

Un garde-fou qu'on croit arme et qui ne peut pas signaler ne garde rien. Ils sont
desormais exposes par le RPC `nameResolutionStatus`, et ce probe est ce qui les LIT --
sans lui, le canal neuf serait a son tour un RPC sans appelant (#480-r8).

Il lit aussi `GET /api/ai-trace/status` : son champ `store` porte le repertoire ABSOLU ou
le host ecrit les traces (`aiTraceStoreStatus()`, quatrieme capteur sans lecteur). C'est ce
qui remplace l'INFERENCE du chemin par une MESURE -- volet (c) de #273-r.

TRI-ETAT, SANS EXCEPTION
------------------------
Aucun chemin ne fabrique un zero ni un vert. Host injoignable, session absente, RPC absent
de la session injectee, champ absent de la reponse : tous rendent NON MESURE, avec la cause
NOMMEE, et un code de retour 2 qui n'est ni un succes ni un echec de contenu.

⚠ Un `HTTP 500` sur un RPC ne dit pas, PAR SON CODE, si le RPC manque ou si son corps a
leve : c'est le residu `#480-r3`. Mesure du 2026-08-05 sur la session 10, faite ici : le
CORPS de la reponse, lui, discrimine -- Frida rend litteralement
`unable to find method '<nom>'` quand `rpc.exports` ne porte pas la cle, la ou une
exception du handler remonte son propre message. Ce probe lit donc le corps et NOMME le
cas ; il ne le devine pas. Cela ne ferme pas `#480-r3` (rien n'ENUMERE encore ce que la
session expose), mais l'ecart entre « absent » et « en erreur » n'est pas aveugle.

Usage :
    python probe_480r7_name_resolution.py

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import sys

import requests

HOST = "http://127.0.0.1:8765"
NON_MESURE = 2


def _session_id() -> tuple[int | None, str]:
    try:
        r = requests.get("%s/api/admin/status" % HOST, timeout=10)
    except requests.RequestException as e:
        return None, "host injoignable (%s)" % type(e).__name__
    if r.status_code >= 400:
        return None, "/api/admin/status HTTP %d" % r.status_code
    s = (r.json() or {}).get("session")
    if not s or s.get("id") is None:
        return None, "aucune session Frida vivante"
    return int(s["id"]), ""


def volet_agent(sid: int) -> int:
    """Capteurs vivant dans le script INJECTE. Rend 0 / 1 / NON_MESURE."""
    try:
        r = requests.post("%s/api/scripts/%d/rpc" % (HOST, sid),
                          json={"method": "nameResolutionStatus", "args": [],
                                "timeout": 10000}, timeout=40)
    except requests.RequestException as e:
        print("[480r7] NON MESURE -- appel RPC impossible (%s)." % type(e).__name__)
        return NON_MESURE
    if r.status_code >= 400:
        absent = "unable to find method" in r.text
        print("[480r7] NON MESURE -- `nameResolutionStatus` HTTP %d : %s"
              % (r.status_code, r.text[:200]))
        if absent:
            print("        Le corps NOMME le cas : le RPC n'est pas dans `rpc.exports` de")
            print("        la session. Apres une modif de `frida/hooks/*`, il faut une")
            print("        RE-INJECTION pour qu'il existe (geste ORCHESTRATEUR).")
        else:
            print("        Le corps ne porte pas `unable to find method` : c'est donc le")
            print("        HANDLER qui a leve, pas le RPC qui manque.")
        return NON_MESURE

    res = (r.json() or {}).get("result")
    if not isinstance(res, dict):
        print("[480r7] NON MESURE -- reponse sans `result` exploitable : %s"
              % str(r.text)[:200])
        return NON_MESURE

    print("        build charge          : %s" % (res.get("build") or "NON MESURE"))
    if res.get("buildWhy"):
        print("        (pourquoi non mesure) : %s" % res["buildWhy"])
    refus = res.get("pinnedAddressRefusals")
    if refus is None:
        print("  ROUGE `pinnedAddressRefusals` absent de la reponse -- le contrat du RPC")
        print("        a change sans que ce lecteur suive.")
        return 1
    print("        refus d'adresses epinglees : %d" % len(refus))
    for m in refus:
        print("          - %s" % str(m)[:220])
    noms = res.get("fieldNames") or {}
    for cle, symbole in (("effectTargetIds", "EffectComponent.targetIds @0x48"),
                         ("bondEntityId", "BondComponent.BondedEntityId @0x10")):
        v = noms.get(cle, "<absent>")
        etat = "NON RESOLU (la lecture retombe sur l'offset RE)" if v is None else v
        print("        %-16s -> %s   [%s]" % (cle, etat, symbole))
    d = res.get("predictionLayoutDrift", "<absent>")
    print("        derive de layout      : %s"
          % ("aucune" if d is None else str(d)[:220]))
    return 0


def volet_host() -> int:
    """Capteur vivant dans le PROCESSUS HOST. Independant du volet agent : le host peut
    porter le correctif alors que la session tourne encore l'ancien bundle, et
    reciproquement. Les deux etats sont donc mesures separement, jamais l'un pour
    l'autre."""
    try:
        a = requests.get("%s/api/ai-trace/status" % HOST, timeout=15)
    except requests.RequestException as e:
        print("[480r7] store ai-trace : NON MESURE (%s)" % type(e).__name__)
        return NON_MESURE
    if a.status_code >= 400:
        print("[480r7] store ai-trace : NON MESURE (HTTP %d)" % a.status_code)
        return NON_MESURE
    body = a.json() or {}
    if "store" not in body:
        print("[480r7] store ai-trace : NON MESURE -- champ `store` absent de la reponse.")
        print("        Le host tourne du code anterieur a #480-r7 : il faut le")
        print("        redemarrer (geste ORCHESTRATEUR) pour que la route le porte.")
        return NON_MESURE
    store = body["store"] or {}
    print("        ai-trace store dir    : %s" % store.get("dir"))
    print("        writers ouverts       : %d" % len(store.get("sessions") or []))
    for w in (store.get("sessions") or []):
        print("          - s%s %s (%s lignes)"
              % (w.get("sessionId"), w.get("path"), w.get("lineCount")))
    return 0


def main() -> int:
    sid, pourquoi = _session_id()
    if sid is None:
        print("[480r7] NON MESURE -- %s." % pourquoi)
        print("        Ce n'est ni un vert ni un rouge : rien n'a ete lu.")
        return NON_MESURE

    print("[480r7] session Frida %d" % sid)
    print("--- volet AGENT (script injecte) ---")
    a = volet_agent(sid)
    print("--- volet HOST (processus Node) ---")
    h = volet_host()

    print()
    if a == 1 or h == 1:
        print("[480r7] ROUGE -- un contrat a change sans que ce lecteur suive.")
        return 1
    if a == NON_MESURE or h == NON_MESURE:
        etat = {0: "LU", 1: "ROUGE", NON_MESURE: "NON MESURE"}
        print("[480r7] NON MESURE (agent=%s, host=%s) -- ni vert ni rouge. Les capteurs"
              % (etat[a], etat[h]))
        print("        existent dans l'arbre ; ils ne sont pas encore CHARGES par le")
        print("        processus vise.")
        return NON_MESURE
    print("[480r7] OK -- les quatre capteurs sont LUS. Leur contenu est un CONSTAT, pas un")
    print("        verdict : une liste de refus VIDE est le cas nominal, et un nom de")
    print("        champ `null` dit que la resolution par offset n'a pas abouti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
