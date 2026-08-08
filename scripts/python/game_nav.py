#!/usr/bin/env python3
"""Se balader dans Tacticus : VOIR l'ecran, CLIQUER, et PROUVER que le clic a porte.

POURQUOI CE MODULE
------------------
Les primitives existaient deja et etaient INJOIGNABLES. `frida/hooks/features/ui-nav.ts`
publie `uiList`, `uiListAll` et `uiClick` depuis toujours ; elles sont dans le bundle vivant.
Mais aucune route host ne les expose et aucun client ne les appelle -- c'est pour ca qu'un
recensement les classait << RPC sans appelant >>. Elles ne sont pas mortes : personne ne
pouvait leur parler. Le passe-plat generique `POST /api/scripts/<id>/rpc` suffit.

LE POINT QUI GOUVERNE TOUT LE MODULE
------------------------------------
LE RETOUR DE `uiClick` NE DIT RIEN, DANS LES DEUX SENS. Mesure du 2026-08-08, session 3 :

  * `ok:true` sur un clic AVALE -- documente depuis #332. `interactable == true` precede la
    fin de l'animation du popup, et le clic emis dans cette fenetre est PERDU.
  * `ok:false` (<< onClick.Invoke threw: system error >>) sur un clic qui A PORTE -- mesure
    2 sur 2 sur les onglets `Idun_UI_Tabs` : l'ecran a bel et bien change a chaque fois.

Donc on ne LIT jamais `ok`. On prend une EMPREINTE de l'ecran avant, on clique, on attend un
CHANGEMENT d'empreinte, et c'est ce changement -- lui seul -- qui vaut succes. Un clic dont
l'empreinte ne bouge pas est un ECHEC, quel que soit son `ok`.

TRI-ETAT. `None` = PAS MESURE (host injoignable, session morte). Jamais un ecran vide rendu
comme << il n'y a rien a l'ecran >>.

⚠ LA SESSION EST PARTAGEE. Naviguer DEPLACE le jeu sous les pieds de tout ce qui tourne.
`exiger_calme()` refuse d'agir tant qu'un runner est vivant -- une lecture reste permise.

⚠ NE JAMAIS cliquer ce qui DEPENSE : `PlusButton` (achat de monnaie), boutiques, offres.
`DANGEREUX` les nomme et `cliquer()` refuse, sauf `force=True` explicite.

Usage:
    python game_nav.py ou                 # l'ecran courant + les boutons
    python game_nav.py boutons --tout     # inclut les inactifs
    python game_nav.py clic <fragment>    # clic valide PAR L'EFFET
    python game_nav.py maison             # retour a l'ecran d'accueil

ASCII strict en sortie (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request

HOTE = "http://127.0.0.1:8765"
ATTENTE_EFFET_S = 6.0
PAS_S = 0.35

#: Ce qu'on ne clique pas sans `--force` : tout ce qui engage une depense.
#: ⚠ LE GARDE PORTE SUR LA FEUILLE, PAS SUR LE CHEMIN. Premiere version : un simple
#: `"/Shop" in chemin` -- il a bloque `ShopPopup(Clone)/CloseArea`, c'est-a-dire LA SORTIE
#: DE SECOURS du popup qu'il pretendait proteger. Un garde qui interdit de sortir d'un ecran
#: dangereux y ENFERME au lieu d'en proteger. On regarde donc le dernier segment.
DANGEREUX = ("PlusButton", "ResourceButton", "ShopButton", "Purchase", "Buy",
             "button_special_BattlePass")
#: Prefixes de feuille qui designent une depense meme sans nom exact.
DANGEREUX_PREFIXES = ("template_offer", "offer_")
#: Toujours autorise : ce qui FERME. Une echappatoire ne se gate jamais.
SORTIES = ("CloseArea", "Blocker", "CloseButton", "Close", "button_close", "BackButton")

#: L'ecran se NOMME par les prefabs presents dans l'arbre, jamais par un compte de boutons.
RE_ECRAN = re.compile(r"Idun_UI_(\w+?Screen)\(Clone\)")
RE_POPUP = re.compile(r"([A-Za-z_]*Popup)\(Clone\)")


def _http(chemin: str, corps=None, timeout=70):
    donnees = None if corps is None else json.dumps(corps).encode("utf-8")
    req = urllib.request.Request(
        HOTE + chemin, data=donnees, method="POST" if donnees else "GET",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def session() -> int | None:
    """Id de la session Frida VIVANTE, ou None si PAS MESURE."""
    try:
        s = _http("/api/admin/status", timeout=8).get("session")
    except Exception:                                                # noqa: BLE001
        return None
    if not s or s.get("status") != "running":
        return None
    return s.get("id")


def rpc(sid: int, methode: str, args=None, timeout_ms=25000):
    r = _http("/api/scripts/%d/rpc" % sid,
              {"method": methode, "args": args or [], "timeout": timeout_ms})
    return r.get("result")


def exiger_calme() -> str | None:
    """Rend un motif de REFUS si un runner est vivant, sinon None. Tri-etat : une panne
    de capteur REFUSE aussi -- on ne navigue pas sur un budget inconnu."""
    try:
        d = _http("/api/admin/drain", timeout=8)
    except Exception as ex:                                          # noqa: BLE001
        return "budget de runners NON MESURE (%s) -- on ne bouge pas le jeu a l'aveugle" \
               % str(ex)[:70]
    n = d.get("liveRunners")
    if n is None:
        return "liveRunners NON MESURE -- on ne bouge pas le jeu a l'aveugle"
    if n:
        return "%d runner(s) vivant(s) : naviguer les casserait" % n
    return None


def boutons(sid: int, tout: bool = False) -> list[dict] | None:
    r = rpc(sid, "uiListAll" if tout else "uiList")
    if not r or not r.get("ok"):
        return None
    return r.get("buttons") or []


def empreinte(bs: list[dict]) -> tuple:
    """Ce qui IDENTIFIE un ecran. Le compte de boutons seul ne suffit pas : il bouge quand
    un widget finit de charger, sans que l'ecran ait change (mesure : 38 -> 57 sur le meme
    `HomeScreen`). On hache donc l'ENSEMBLE des chemins, plus les prefabs d'ecran."""
    chemins = frozenset(b.get("path", "") for b in bs)
    return (frozenset(ecrans(bs)), frozenset(popups(bs)), hash(chemins))


def ecrans(bs: list[dict]) -> set[str]:
    out = set()
    for b in bs:
        out.update(RE_ECRAN.findall(b.get("path", "")))
    return out


def popups(bs: list[dict]) -> set[str]:
    out = set()
    for b in bs:
        out.update(RE_POPUP.findall(b.get("path", "")))
    return out


def ou(sid: int) -> dict | None:
    bs = boutons(sid)
    if bs is None:
        return None
    return {"ecrans": sorted(ecrans(bs)), "popups": sorted(popups(bs)),
            "n_boutons": len(bs), "boutons": bs}


def est_dangereux(chemin: str) -> str | None:
    """Le verdict porte sur la FEUILLE. Une sortie n'est jamais gatee -- cf. DANGEREUX."""
    feuille = chemin.rstrip("/").split("/")[-1]
    if any(s.lower() in feuille.lower() for s in SORTIES):
        return None
    if feuille in DANGEREUX:
        return feuille
    for p in DANGEREUX_PREFIXES:
        if feuille.startswith(p):
            return p
    return None


def cliquer(sid: int, chemin: str, force: bool = False,
            attente: float = ATTENTE_EFFET_S) -> dict:
    """Clique, puis ATTEND un changement d'empreinte. Le verdict vient de l'EFFET.

    Rend `{porte, avant, apres, retour_brut, secondes}`. `retour_brut` est conserve pour
    la trace, jamais pour decider : mesure du 2026-08-08, il vaut `ok:false` sur des clics
    qui ont porte 2 fois sur 2.
    """
    danger = est_dangereux(chemin)
    if danger and not force:
        return {"porte": False, "refus": "chemin DANGEREUX (contient %r) -- depense "
                                         "possible. `--force` pour passer outre." % danger}
    avant_b = boutons(sid, tout=True)
    if avant_b is None:
        return {"porte": None, "refus": "ecran NON MESURE avant le clic"}
    avant = empreinte(avant_b)

    brut = rpc(sid, "uiClick", [chemin])

    t0 = time.time()
    apres_b, apres = avant_b, avant
    while time.time() - t0 < attente:
        time.sleep(PAS_S)
        b = boutons(sid, tout=True)
        if b is None:
            continue
        e = empreinte(b)
        if e != avant:
            apres_b, apres = b, e
            break
    return {
        "porte": apres != avant,
        "avant": {"ecrans": sorted(ecrans(avant_b)), "n": len(avant_b)},
        "apres": {"ecrans": sorted(ecrans(apres_b)), "n": len(apres_b)},
        "retour_brut": brut,
        "secondes": round(time.time() - t0, 1),
    }


def resoudre(bs: list[dict], fragment: str) -> list[str]:
    """Les chemins dont le SUFFIXE contient le fragment (insensible a la casse)."""
    f = fragment.lower()
    return [b["path"] for b in bs if f in b.get("path", "").lower()]


def maison(sid: int) -> dict:
    """Retour a l'ecran d'accueil par l'onglet Home. C'est la voie de secours."""
    bs = boutons(sid, tout=True) or []
    cands = [p for p in resoudre(bs, "Buttons/HomeButton")]
    if not cands:
        return {"porte": False, "refus": "aucun onglet Home dans l'arbre courant"}
    return cliquer(sid, cands[0], force=True)


def _imprimer_ou(o: dict) -> None:
    print("ECRAN   : %s" % (", ".join(o["ecrans"]) or "(aucun prefab d'ecran -- "
                                                     "transition en cours)"))
    if o["popups"]:
        print("POPUP   : %s" % ", ".join(o["popups"]))
    print("BOUTONS : %d actifs" % o["n_boutons"])
    feuilles = {}
    for b in o["boutons"]:
        feuilles.setdefault(b["path"].split("/")[-1], 0)
        feuilles[b["path"].split("/")[-1]] += 1
    for nom, n in sorted(feuilles.items(), key=lambda kv: (-kv[1], kv[0]))[:20]:
        print("    %3d  %s" % (n, nom))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("commande", choices=["ou", "boutons", "clic", "maison"])
    ap.add_argument("fragment", nargs="?", default="")
    ap.add_argument("--tout", action="store_true", help="inclure les boutons inactifs")
    ap.add_argument("--force", action="store_true", help="passer outre le garde de depense")
    a = ap.parse_args()

    sid = session()
    if sid is None:
        print("session Frida NON MESUREE (host injoignable ou session morte).")
        print("Rien n'est conclu sur l'etat du jeu.")
        return 2

    if a.commande in ("clic", "maison"):
        refus = exiger_calme()
        if refus:
            print("REFUS : %s" % refus)
            return 3

    if a.commande == "ou":
        o = ou(sid)
        if o is None:
            print("ecran NON MESURE.")
            return 2
        _imprimer_ou(o)
        return 0

    if a.commande == "boutons":
        bs = boutons(sid, tout=a.tout)
        if bs is None:
            print("ecran NON MESURE.")
            return 2
        for b in sorted(bs, key=lambda x: x.get("path", "")):
            print(b.get("path", ""))
        print("-- %d bouton(s)%s" % (len(bs), " (inactifs compris)" if a.tout else ""))
        return 0

    if a.commande == "maison":
        r = maison(sid)
        print(json.dumps(r, ensure_ascii=True, indent=2))
        return 0 if r.get("porte") else 1

    # clic
    bs = boutons(sid, tout=True)
    if bs is None:
        print("ecran NON MESURE.")
        return 2
    cands = resoudre(bs, a.fragment)
    if not cands:
        print("aucun bouton ne contient %r. `boutons --tout` pour voir l'arbre." % a.fragment)
        return 1
    if len(cands) > 1:
        print("AMBIGU : %d boutons contiennent %r -- precise." % (len(cands), a.fragment))
        for c in cands[:12]:
            print("   " + c)
        return 1
    r = cliquer(sid, cands[0], force=a.force)
    print("cible : %s" % cands[0])
    print(json.dumps(r, ensure_ascii=True, indent=2))
    return 0 if r.get("porte") else 1


if __name__ == "__main__":
    raise SystemExit(main())
