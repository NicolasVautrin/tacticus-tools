"""Probe #467-r4 -- le CONTRAT entre `loop_status` et le host, contre une source NON substituee.

LE TROU QU'IL FERME
-------------------
`probe_467_loop_status_fidelity.py` **et** `probe_467r4_scene_git_reelle.py` substituent tous
deux la facade `Sources` -- donc tous deux remplacent `http_json`. Un champ qui DISPARAITRAIT
cote host (`.session` renomme `.sessions`, `liveRunners` retire de `/api/admin/drain`) ne serait
vu par AUCUN des deux : ils resteraient VERTS en s'accordant parfaitement, et ils auraient tort
tous les deux. C'est le patron exact contre lequel le depot se garde ailleurs -- deux lecteurs
qui partagent la meme entree morte -- et le contrat host n'etait, lui, verifie par rien.

La degradation serait SILENCIEUSE et du pire genre : `dr.get("liveRunners")` sur une reponse qui
ne porte plus la cle rend `None`, donc `live_runners` bascule en PAS MESURE **pour toujours**.
L'outil n'echoue pas, il cesse simplement de dire le seul chiffre que personne ne peut deviner.

DEUX VOLETS, ET LE PREMIER EST CELUI QUI MORD
---------------------------------------------
VOLET A -- le contrat contre le CODE SOURCE du host (`frida/host/*.ts`). 100 % offline,
deterministe, et surtout **DERIVE DES DEUX COTES** : la liste des champs exiges n'est pas
recopiee ici, elle est extraite de `loop_status.mesurer_harnais` par lecture de son propre
source. Un champ qu'on ajouterait au lecteur devient donc automatiquement exige du producteur --
un cliquet dont la liste se recopie derive, et c'est precisement le vice qu'on corrige.

VOLET B -- la FORME REELLE de la reponse, quand le host repond. Il ne PEUT PAS conditionner le
vert : le host est eteint la moitie du temps, et un cliquet qui depend de l'etat de la machine
n'est pas un cliquet. Injoignable => **NON MESURE**, dit franchement, jamais un vert muet
(discipline `host_inputs.py`, #273). Il ne depend pas non plus d'une session Frida VIVANTE : il
juge la FORME (`liveRunners` est un entier OU `null` accompagne de `liveRunnersError`), pas la
valeur -- `null` sans session est une reponse conforme.

AUTO-EPREUVE INTEGREE (#439 : un cliquet qui ne peut pas rougir ne vaut rien). Le volet A se
prouve a CHAQUE execution : le host est copie dans un tmpdir, un champ y est SUPPRIME, et le
controle doit basculer au ROUGE. S'il reste vert sous mutation, c'est LUI qui rougit -- un
garde-fou aveugle est signale comme tel au lieu d'etre cru.

Tmpdir SYSTEME (`mkdtemp()` sans `dir=`), jamais sous `scripts/python/` que la banque enumere en
parallele (#455). Ne lit que SON PROPRE checkout (#434) : les chemins sont ancres sur `REPO`,
sans aucun balayage remontant.

Sortie ASCII stricte (cp1252). Code de sortie = nombre d'epreuves fautives.
"""
from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import loop_status as LS                                               # noqa: E402

REPO = Path(__file__).resolve().parents[2]
HOST = REPO / "frida" / "host"

ECHECS: list[str] = []
NON_MESURE: list[str] = []


def _a(s: str) -> str:
    """ASCII STRICT. Les messages d'erreur Windows sont LOCALISES -- un `urlopen error`
    rend « Aucune connexion n'a pu etre etablie » avec accents et apostrophe typographique,
    qui levent `UnicodeEncodeError` sur une console cp1252. Un cliquet qui plante en
    RAPPORTANT une non-mesure transformerait un tri-etat lisible en trace illisible."""
    return s.encode("ascii", "replace").decode("ascii")


def verifie(cond: bool, quoi: str) -> None:
    print(("  OK    " if cond else "  ROUGE ") + _a(quoi))
    if not cond:
        ECHECS.append(_a(quoi))


# =====================================================================================
#  Ce que `loop_status` LIT -- extrait de son propre source, jamais recopie
# =====================================================================================
def contrat_lu() -> dict[str, list[str]]:
    """{route: [cles lues]} derive de `loop_status.mesurer_harnais`.

    Le decoupage suit les appels `src.http_json("<route>")` : tout ce qui est lu par
    `.get("<cle>")` APRES un appel, et avant le suivant, appartient a cette route.
    """
    src = inspect.getsource(LS.mesurer_harnais)
    morceaux = re.split(r'src\.http_json\(\s*"([^"]+)"\s*\)', src)
    contrat: dict[str, list[str]] = {}
    # morceaux = [avant, route1, corps1, route2, corps2, ...]
    for i in range(1, len(morceaux) - 1, 2):
        route, corps = morceaux[i], morceaux[i + 1]
        cles = []
        for c in re.findall(r'\.get\(\s*"([A-Za-z_][A-Za-z0-9_]*)"', corps):
            if c not in cles:
                cles.append(c)
        contrat[route] = cles
    return contrat


# =====================================================================================
#  VOLET A -- le contrat contre le CODE SOURCE du host
# =====================================================================================
def _bloc_handler(source_router: str, route: str) -> str | None:
    """Le corps du `router.get("<route>", ...)`, jusqu'au handler suivant."""
    debut = source_router.find('router.get("%s"' % route)
    if debut < 0:
        return None
    suite = source_router.find("\n    router.", debut + 1)
    return source_router[debut:suite if suite > 0 else len(source_router)]


def _argument_res_json(bloc: str) -> str:
    """L'argument de `res.json(...)` -- ce qui est REELLEMENT rendu, et rien d'autre.

    Chercher la cle dans tout le handler est un FAUX VERT, et l'auto-epreuve l'a attrape
    des le premier passage : `let liveRunners: number | null = null;` est une DECLARATION
    locale, que n'importe quel motif `<cle>\\s*:` prend pour une propriete de reponse. Le
    champ retire de `res.json`, le controle restait vert.
    """
    i = bloc.find("res.json(")
    if i < 0:
        return ""
    i += len("res.json(")
    prof, j = 1, i
    while j < len(bloc) and prof > 0:
        if bloc[j] in "({[":
            prof += 1
        elif bloc[j] in ")}]":
            prof -= 1
        j += 1
    return bloc[i:j - 1]


def _corps_types(txt: str) -> str:
    """Les blocs `interface`/`type` d'un module -- la forme DECLAREE, pas les affectations.

    Pour une cle qui entre par un spread (`...getDrainState()`), le module entier serait
    trop laxiste : `state.enabled = false` y passerait pour une propriete rendue.
    """
    zones = []
    for m in re.finditer(r"(?:export\s+)?(?:interface|type)\s+\w+[^{]*\{", txt):
        prof, j = 1, m.end()
        while j < len(txt) and prof > 0:
            if txt[j] == "{":
                prof += 1
            elif txt[j] == "}":
                prof -= 1
            j += 1
        zones.append(txt[m.end():j - 1])
    return "\n".join(zones)


def _zone_de_recherche(bloc: str, sources: dict[str, str]) -> str:
    """Ce que le handler REND, etendu aux TYPES des modules qu'il etale.

    `enabled` n'apparait pas en clair dans le handler `/api/admin/drain` : il entre par le
    spread de `getDrainState()`, dont le type vit dans `drain.ts`. Chercher la cle dans le
    seul littéral rendu produirait donc un ROUGE mensonger.
    """
    rendu = _argument_res_json(bloc)
    zone = rendu
    for fn in set(re.findall(r"\.\.\.(\w+)\(\)", rendu)):
        for txt in sources.values():
            if re.search(r"export function %s\b" % re.escape(fn), txt):
                zone += "\n" + _corps_types(txt)
    return zone


def _produit(zone: str, cle: str) -> bool:
    """La cle est-elle PRODUITE ? Propriete (`cle:`), shorthand (`cle,`) ou champ de type.

    Le suffixe est DISCRIMINANT : `liveRunnersSource:` ne doit pas valider `liveRunners`.
    """
    return bool(re.search(r"(^|[\s{,])%s\s*[?]?\s*[:,]" % re.escape(cle), zone, re.M)
                or re.search(r"(^|[\s{,])%s\s*$" % re.escape(cle), zone, re.M))


def volet_a(contrat: dict[str, list[str]], racine_host: Path, bavard: bool = True) -> list[str]:
    """Rend la liste des manques. Vide == contrat honore."""
    sources: dict[str, str] = {}
    for p in sorted(racine_host.glob("*.ts")):
        try:
            sources[p.name] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    manques: list[str] = []
    router = sources.get("router.ts")
    if router is None:
        return ["frida/host/router.ts INTROUVABLE sous %s" % racine_host]
    for route, cles in contrat.items():
        bloc = _bloc_handler(router, route)
        if bloc is None:
            manques.append("route %s absente de router.ts" % route)
            continue
        zone = _zone_de_recherche(bloc, sources)
        for cle in cles:
            if not _produit(zone, cle):
                manques.append("%s : le host ne produit plus `%s`" % (route, cle))
            elif bavard:
                print("  OK    %s produit `%s`" % (route, cle))
    return manques


def etape_a(contrat: dict[str, list[str]]) -> None:
    print("\n[A] CONTRAT : chaque champ lu par loop_status est PRODUIT par frida/host/*.ts")
    for route, cles in contrat.items():
        print("      %s <- %s" % (route, ", ".join(cles)))
    verifie(bool(contrat), "le contrat se DERIVE de mesurer_harnais (%d route(s))" % len(contrat))
    # `.session` est SINGULIER, et l'avoir cru pluriel a deja coute : on l'exige nommement,
    # en plus de la derivation, parce que c'est le piege que le contrat porte le plus.
    verifie("session" in contrat.get("/api/admin/status", []),
            "le contrat porte bien `.session` SINGULIER (jamais `.sessions`)")
    for cle in ("enabled", "liveRunners"):
        verifie(cle in contrat.get("/api/admin/drain", []),
                "le contrat porte `%s` sur /api/admin/drain" % cle)

    manques = volet_a(contrat, HOST)
    for m in manques:
        verifie(False, m)
    if not manques:
        print("  ---   contrat host HONORE : aucun champ manquant")


# =====================================================================================
#  AUTO-EPREUVE du volet A -- il doit ROUGIR quand un champ disparait (#439)
# =====================================================================================
def etape_auto_epreuve(contrat: dict[str, list[str]]) -> None:
    print("\n[A'] AUTO-EPREUVE : un champ SUPPRIME du host doit faire basculer le volet A")
    tmp = Path(tempfile.mkdtemp(prefix="probe467r4-"))            # tmpdir SYSTEME (#455)
    try:
        faux = tmp / "host"
        shutil.copytree(HOST, faux)
        temoin = volet_a(contrat, faux, bavard=False)
        verifie(temoin == [],
                "avant mutation, la copie du host honore le contrat (%s)" % temoin)

        # Mutation 1 -- `liveRunners` retire de la reponse du handler drain.
        r = faux / "router.ts"
        txt = r.read_text(encoding="utf-8")
        mute = txt.replace("            liveRunners,\n", "", 1)
        verifie(mute != txt, "la mutation `liveRunners` a bien MORDU le fichier")
        r.write_text(mute, encoding="utf-8")
        m1 = volet_a(contrat, faux, bavard=False)
        verifie(any("liveRunners" in x for x in m1),
                "champ `liveRunners` retire -> le volet A ROUGIT (%s)" % m1)
        r.write_text(txt, encoding="utf-8")

        # Mutation 2 -- `.session` renomme `.sessions` : le piege nomme du contrat.
        mute2 = txt.replace("                session: session ? {",
                            "                sessions: session ? {", 1)
        verifie(mute2 != txt, "la mutation `session`->`sessions` a bien MORDU le fichier")
        r.write_text(mute2, encoding="utf-8")
        m2 = volet_a(contrat, faux, bavard=False)
        verifie(any("session" in x for x in m2),
                "`.session` renomme `.sessions` -> le volet A ROUGIT (%s)" % m2)
        r.write_text(txt, encoding="utf-8")

        # Mutation 3 -- `enabled` disparait de DrainState : il entre par un SPREAD, donc
        # cette mutation prouve aussi que la zone de recherche suit bien les spreads.
        d = faux / "drain.ts"
        td = d.read_text(encoding="utf-8")
        muted = td.replace("enabled", "actif")
        verifie(muted != td, "la mutation `enabled` a bien MORDU drain.ts")
        d.write_text(muted, encoding="utf-8")
        m3 = volet_a(contrat, faux, bavard=False)
        verifie(any("enabled" in x for x in m3),
                "`enabled` disparu de DrainState -> le volet A ROUGIT (%s)" % m3)
        d.write_text(td, encoding="utf-8")

        verifie(volet_a(contrat, faux, bavard=False) == [],
                "apres restauration, le volet A redevient vert (pas d'etat resident)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =====================================================================================
#  VOLET B -- la FORME REELLE, quand le host repond
# =====================================================================================
def etape_b(contrat: dict[str, list[str]]) -> None:
    print("\n[B] FORME REELLE de la reponse du host (NON MESURE si injoignable)")
    hote = os.environ.get("TACTICUS_HOST_URL", LS.HOST_DEFAUT)
    src = LS.Sources(repo=REPO, host=hote, timeout=3.0, avec_gh=False)
    reponses: dict[str, dict] = {}
    for route in contrat:
        try:
            reponses[route] = src.http_json(route)
        except Exception as e:                                # noqa: BLE001
            NON_MESURE.append(_a("%s : %s" % (route, str(e)[:70])))
    if len(reponses) != len(contrat):
        for x in NON_MESURE:
            print("  NON MESURE  %s" % x)
        print("  ---   host injoignable : le contrat LIVE n'est pas juge (et ce n'est PAS un vert)")
        return

    st, dr = reponses["/api/admin/status"], reponses["/api/admin/drain"]
    verifie("session" in st, "/api/admin/status porte la cle `session` (SINGULIER)")
    verifie("sessions" not in st, "/api/admin/status ne porte PAS `sessions` (le piege)")
    verifie(st.get("session") is None or isinstance(st.get("session"), dict),
            "`session` est un objet ou null, jamais autre chose")
    verifie(isinstance(st.get("tacticus"), dict) and "running" in st["tacticus"],
            "`tacticus.running` present")
    verifie(isinstance(dr.get("enabled"), bool), "`drain.enabled` est un booleen")
    lr = dr.get("liveRunners")
    verifie(lr is None or isinstance(lr, int),
            "`liveRunners` est un entier OU null -- jamais une chaine (%r)" % (lr,))
    verifie("liveRunnersError" in dr, "`liveRunnersError` est present (tri-etat du host)")
    verifie(lr is not None or dr.get("liveRunnersError"),
            "`liveRunners` null s'accompagne TOUJOURS de sa raison")

    # La boucle se ferme ici : `loop_status` juge sur l'entree REELLE, non substituee.
    ha = LS.mesurer_harnais(src)
    verifie(ha["session"].mesuree and ha["drain"].mesuree,
            "loop_status.mesurer_harnais MESURE sur la reponse reelle")
    verifie(ha["live_runners"].mesuree == isinstance(lr, int),
            "le tri-etat de `live_runners` SUIT la forme reelle (host lr=%r, mesuree=%s)"
            % (lr, ha["live_runners"].mesuree))
    if isinstance(lr, int):
        verifie(ha["live_runners"].valeur == lr,
                "la valeur propagee est celle du host (%s vs %s)"
                % (ha["live_runners"].valeur, lr))


def main() -> int:
    print("probe_467-r4 -- contrat host <-> loop_status, source NON substituee")
    contrat = contrat_lu()
    etape_a(contrat)
    etape_auto_epreuve(contrat)
    etape_b(contrat)
    print("")
    if ECHECS:
        print("VERDICT: FAIL -- %d epreuve(s) fautive(s) :" % len(ECHECS))
        for x in ECHECS:
            print("  - %s" % x)
    elif NON_MESURE:
        # Ni vert ni rouge, et surtout pas silencieux : le volet offline a juge, le volet
        # live n'a pas pu. Un `PASS` ici se lirait « le contrat host est verifie », ce qui
        # serait faux -- et c'est exactement la confusion que ce probe existe pour interdire.
        print("VERDICT: PASS PARTIEL -- contrat SOURCE honore ; contrat LIVE **NON MESURE** :")
        for x in NON_MESURE:
            print("  - %s" % x)
        print("  (host eteint : rejouer avec le host allume pour juger la forme reelle)")
    else:
        print("VERDICT: PASS -- le host produit ce que loop_status lit, source ET forme reelle.")
    return len(ECHECS)


if __name__ == "__main__":
    sys.exit(main())
