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

CE QUI EST VOLATIL, ET CE QUI EST CONTRACTUEL (#473) -- LE PARTAGE PORTE TOUT
-----------------------------------------------------------------------------
Le volet B lit une source VIVANTE : c'est son objet, donc il ne peut pas etre rejoue sur capture
sans perdre ce qu'il garde. Reste a dire, epreuve par epreuve, QUI est accuse quand elle tombe.
Le critere est celui de #471 : << un depot PARFAIT, a cet instant, sur cette machine, aurait-il
produit ce meme echec ? >> OUI -> INDISPONIBLE (rc 99, BLOQUANT) | NON -> ROUGE.

VOLATIL -- bouge parce que la PLATEFORME bouge, n'accuse jamais le depot :
  * la JOIGNABILITE du host, appel par appel. Chaque `http_json` est un tirage INDEPENDANT : la
    capture peut reussir et une lecture ulterieure lacher, pour un budget client de 3 s
    (`Sources.http_json` : `min(timeout, 5.0)`). DEUX causes MESUREES, et la seconde interdit de
    reduire le defaut au pump : (a) `router.get("/api/admin/drain")` attend
    `rpcCall(sid, "listRunners", [], 5000)` sur le pump Frida, qu'un build de runner concurrent
    occupe -- c'est le cas rapporte par la PR #588 ; (b) le host lui-meme sature -- premiere passe
    de banque du 2026-08-04 apres ce correctif, a parallelisme 16, `/api/admin/status` a rendu
    `timed out` alors que ce handler ne touche PAS le pump (`findTacticusCandidates` +
    `activeMetaVersion`). Le volet a rendu 99, les 11 epreuves contractuelles restant VERTES.
  * les VALEURS rendues : `session` (objet ou null), `tacticus.running`, `drain.enabled`,
    `liveRunners` (entier OU null) et sa raison. Le volet juge la FORME, jamais la valeur.

CONTRACTUEL -- un fait sur le CODE, donc ROUGE :
  * dans une reponse OBTENUE et bien formee, la PRESENCE et le TYPE des cles que
    `mesurer_harnais` lit. Elles sont STRUCTURELLES cote host (`router.ts` rend toujours l'objet
    `tacticus` et `session|null` ; `enabled` vient de l'interface `DrainState`) : aucun etat de la
    plateforme ne peut les faire disparaitre, seul un changement de code le peut ;
  * que `mesurer_harnais` MESURE (pas `_ko`) sur une reponse OBTENUE ;
  * qu'il PROPAGE exactement la charge utile qu'on lui donne ;
  * qu'il n'interroge QUE les routes du contrat DERIVE -- une route lue mais non derivee rendrait
    le volet A aveugle dessus.

LA BORNE A NE PAS LAISSER GLISSER, c'est la meme qu'en #471 : une reponse qui ARRIVE bien formee
mais a laquelle il MANQUE un champ contractuel est un fait sur le code -> ROUGE. Ne jamais rabattre
<< le contrat est viole >> sur << l'etat a bouge sous ma lecture >>. Seule une panne de TRANSPORT --
un appel qui ne rend AUCUNE reponse -- est INDISPONIBLE. Sans cette borne, le cliquet finirait
toujours indisponible, donc ne garderait plus rien.

ET LES DEUX REGIMES D'IMPOSSIBILITE NE SE CONFONDENT PAS :
  * la CAPTURE echoue (host eteint, une route muette) -> le volet ne s'OUVRE PAS. Il ne pretend
    aucun jugement : NON MESURE + `PASS PARTIEL`, rc 0. Regime assume depuis l'origine -- le rendre
    bloquant ferait rougir la banque la moitie du temps, et un garde-fou qui rougit partout se fait
    desactiver (lecon ecrite dans `probe_439`, rappelee par #471) ;
  * le volet s'est OUVERT et ne peut plus CONCLURE (une lecture ulterieure lache) -> il ne peut ni
    dire PASS (il n'a pas tout juge) ni FAIL (le depot n'est pas en cause) : INDISPONIBLE, rc 99.

AUTO-EPREUVE INTEGREE (#439 : un cliquet qui ne peut pas rougir ne vaut rien), sur les DEUX volets
et, pour le volet B, sur les DEUX FACES du partage ci-dessus :
  * [A'] le host est copie dans un tmpdir, un champ y est SUPPRIME, le controle doit basculer au
    ROUGE ;
  * [B'] le JUGE du volet B est confronte a des sources FABRIQUEES -- une reponse amputee doit
    rendre ROUGE, un transport qui lache doit rendre INDISPONIBLE. Un chemin qui ne peut pas
    rendre les deux ne vaut rien, et VERT y est le resultat SUSPECT : chaque face verifie que sa
    mutation a MORDU. [B'] est 100 % deterministe -- il n'interroge aucun host.

Fabriquer une reponse est LEGITIME en auto-epreuve (on y eprouve le JUGE, comme [A'] mute une COPIE
du host) et PROSCRIT dans le volet B lui-meme, ou l'on ne juge que ce que le host a reellement
rendu -- c'est pourquoi `_Rejeu` LEVE sur une route non capturee.

Tmpdir SYSTEME (`mkdtemp()` sans `dir=`), jamais sous `scripts/python/` que la banque enumere en
parallele (#455). Ne lit que SON PROPRE checkout (#434) : les chemins sont ancres sur `REPO`,
sans aucun balayage remontant.

Sortie ASCII stricte (cp1252). Code de sortie : 0 = conforme (ou volet B non ouvert), N = nombre
d'epreuves fautives, 99 = INDISPONIBLE. Le ROUGE PRIME sur l'indisponible -- meme precedence que
`Get-CodeSortieBanque` dans `scripts/ratchets-verdict.ps1`.
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

#: << RIEN N'A PU ETRE CONCLU >>. La convention n'est pas inventee ici : elle est celle de
#: `scripts/ratchets-verdict.ps1` (`$EX_INDISPONIBLE = 99`, `Get-EtatCliquet` -> `INDISPO`), que la
#: banque dot-source. BLOQUANT -- reclasser un rouge en indisponible ne fait RIEN taire, ca change
#: l'ACCUSE (le harnais au lieu du code fusionne), pas le blocage.
EX_INDISPONIBLE = 99

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis.
#:
#: `frida/host/*.ts` est un glob de PROFONDEUR 1, et c'est la mesure : `volet_a` fait
#: `racine_host.glob("*.ts")`, il ne descend pas. La forme recursive est donnee EN PLUS parce
#: qu'un sous-repertoire neuf de `frida/host/` ferait changer le contrat sans changer ce glob.
DECLENCHEUR = {
    "chemins": ("frida/host/*.ts", "frida/host/**",
                "scripts/python/loop_status.py",
                "scripts/python/fleet_board.py",
                "scripts/python/host_inputs.py",
                "scripts/python/probe_467r4_contrat_host.py"),
    "build": False,
    "toujours": False,
    "raison": "Volet A confronte le CODE SOURCE de `frida/host/*.ts` a une liste de champs "
              "DERIVEE de `loop_status.mesurer_harnais` (donc les deux cotes sont dans le "
              "declencheur) ; volet B est opportuniste sur le host LIVE, qui n'est pas un "
              "chemin du depot -- host eteint, il sort en NON MESURE, jamais en vert muet.",
}

ECHECS: list[str] = []
NON_MESURE: list[str] = []
#: Le volet s'est OUVERT et n'a pas pu CONCLURE. Distinct de `NON_MESURE` (le volet ne s'est PAS
#: ouvert, regime assume a rc 0) : cf. << LES DEUX REGIMES D'IMPOSSIBILITE >> en tete de module.
INDISPONIBLE: list[str] = []


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


def indisponible(quoi: str) -> None:
    """Le volet a commence a juger et ne peut plus conclure. JAMAIS un vert, JAMAIS un rouge."""
    print("  INDISP " + _a(quoi))
    INDISPONIBLE.append(_a(quoi))


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
class _Rejeu:
    """Source qui REJOUE des reponses deja capturees, pour juger la PROPAGATION sans course.

    N'expose que `http_json` : c'est tout ce que `loop_status.mesurer_harnais` consomme d'une
    `Sources` (verifie au code, pas suppose). Une route absente leve, comme le ferait un host
    injoignable -- on ne fabrique jamais de reponse que le host n'a pas rendue."""

    def __init__(self, reponses: dict[str, dict]) -> None:
        self._r = dict(reponses)

    def http_json(self, route: str) -> dict:
        if route not in self._r:
            raise KeyError("route non capturee : %s" % route)
        return self._r[route]


class _Tracee:
    """Relaie `http_json` vers une source REELLE, en notant les routes VUES et les pannes de
    TRANSPORT.

    C'est ce qui separe les deux ACCUSES, et rien d'autre ne le peut : `mesurer_harnais` attrape
    `Exception` sans distinguer un appel qui n'a rendu AUCUNE reponse (la plateforme a bouge) d'une
    reponse obtenue mais inexploitable (le code ment). Il rend le MEME `_ko` dans les deux cas, et
    lire son message pour deviner laquelle serait une heuristique sur du texte -- c'est exactement
    la faute #467-r6 (trois pannes de `gh` derriere un seul `rc=127`), a l'envers.
    """

    def __init__(self, src) -> None:
        self._src = src
        self.vues: list[str] = []
        self.pannes: list[str] = []

    def http_json(self, route: str) -> dict:
        self.vues.append(route)
        try:
            return self._src.http_json(route)
        except Exception as e:                                # noqa: BLE001
            self.pannes.append(_a("%s : %s" % (route, str(e)[:70])))
            raise


def juger_forme(st: dict, dr: dict) -> list[tuple[bool, str]]:
    """Les epreuves CONTRACTUELLES, sur des reponses DEJA OBTENUES. Fonction PURE.

    Toutes portent sur la PRESENCE et le TYPE, jamais sur la VALEUR : `session` a null,
    `drain.enabled` a false, `liveRunners` a null accompagne de sa raison sont autant de reponses
    CONFORMES -- l'etat de la plateforme ne peut donc en faire tomber aucune. Ce qui les fait
    tomber, c'est un changement de `frida/host/*.ts`, et c'est un fait sur le depot -> ROUGE.

    Extraite pour que l'auto-epreuve [B'] la confronte a une reponse AMPUTEE sans aucun host.
    """
    lr = dr.get("liveRunners")
    return [
        ("session" in st, "/api/admin/status porte la cle `session` (SINGULIER)"),
        ("sessions" not in st, "/api/admin/status ne porte PAS `sessions` (le piege)"),
        (st.get("session") is None or isinstance(st.get("session"), dict),
         "`session` est un objet ou null, jamais autre chose"),
        (isinstance(st.get("tacticus"), dict) and "running" in st["tacticus"],
         "`tacticus.running` present"),
        (isinstance(dr.get("enabled"), bool), "`drain.enabled` est un booleen"),
        (lr is None or isinstance(lr, int),
         "`liveRunners` est un entier OU null -- jamais une chaine (%r)" % (lr,)),
        ("liveRunnersError" in dr, "`liveRunnersError` est present (tri-etat du host)"),
        (lr is not None or bool(dr.get("liveRunnersError")),
         "`liveRunners` null s'accompagne TOUJOURS de sa raison"),
    ]


def juger_relecture(contrat: dict[str, list[str]], src) -> tuple[list[str], list[tuple[bool, str]]]:
    """Relit le host par `mesurer_harnais` NON substitue, et VENTILE : (indisponibles, epreuves).

    CE QUE CETTE RELECTURE EST SEULE A VOIR, et qui justifie de la garder malgre son exposition :
    la vraie facade `Sources` consommee par `mesurer_harnais`, sur les routes que LUI choisit --
    la capture, elle, appelle les routes derivees par la regex du contrat. Une route lue ici mais
    absente du contrat rendrait le volet A aveugle dessus.

    LE PARTAGE (#473). Une panne de TRANSPORT -- un appel qui ne rend AUCUNE reponse -- est
    VOLATILE : un depot parfait l'aurait subie a cet instant, donc INDISPONIBLE. Une reponse
    OBTENUE dont `mesurer_harnais` ne tire pas une MESURE est CONTRACTUELLE : le depot est accuse,
    donc ROUGE. Ne jamais rabattre la seconde sur la premiere -- sans cette borne, il suffirait
    d'un host lent pour que le cliquet cesse de garder quoi que ce soit.
    """
    tr = _Tracee(src)
    ha = LS.mesurer_harnais(tr)
    # DETERMINISTE MEME SOUS PANNE : les routes sont VUES avant que le transport ne lache, et
    # `mesurer_harnais` les appelle dans deux `try` independants -- la premiere qui echoue
    # n'empeche pas la seconde. Cette epreuve reste donc jugee quand la suivante ne peut plus l'etre.
    vues = sorted(set(tr.vues))
    epreuves = [(vues == sorted(contrat),
                 "mesurer_harnais n'interroge QUE les routes du contrat derive (%s)"
                 % ", ".join(vues))]
    if tr.pannes:
        return (["relecture du host : %s" % p for p in tr.pannes], epreuves)
    epreuves.append((ha["session"].mesuree and ha["drain"].mesuree,
                     "loop_status.mesurer_harnais MESURE sur la reponse reelle"))
    return [], epreuves


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

    # Le volet juge NOMMEMENT deux routes, alors que le contrat, lui, est DERIVE. Si la derivation
    # en ratait une, le deballage ci-dessous levait un `KeyError` -- un traceback en rc=1, donc un
    # ROUGE ANONYME, la forme meme que #471 combat. Le verdict reste ROUGE (une derivation qui perd
    # une route est un fait sur le depot, pas un etat de plateforme), mais il porte son NOM.
    # Trouve par contre-epreuve adversariale de #473, pas par un incident.
    manquantes = [r for r in ("/api/admin/status", "/api/admin/drain") if r not in reponses]
    if manquantes:
        verifie(False, "le contrat DERIVE porte les routes que le volet B juge (manque %s)"
                       % ", ".join(manquantes))
        return
    st, dr = reponses["/api/admin/status"], reponses["/api/admin/drain"]
    lr = dr.get("liveRunners")
    for cond, quoi in juger_forme(st, dr):
        verifie(cond, quoi)

    # ⚠ LA PROPAGATION SE JUGE SUR LA REPONSE DEJA CAPTUREE, PAS SUR UNE SECONDE LECTURE.
    # `liveRunners` est VOLATIL par nature : les agents en vol creent et disposent des runners
    # en permanence. Confronter `mesurer_harnais(src)` -- qui RE-INTERROGE le host -- au `lr`
    # lu quelques millisecondes plus tot compare deux instants differents, pas deux modeles.
    # MESURE du 2026-08-04 : ce cliquet a rendu ROUGE `la valeur propagee est celle du host
    # (3 vs 4)` sur la banque de `afb3e209`, avec CINQ agents en vol -- un runner dispose entre
    # les deux appels. Aucun code juge n'avait bouge : ni `frida/host/*`, ni `loop_status.py`.
    # Un cliquet qui rougit au hasard des qu'on travaille n'accuse plus rien.
    #
    # Le REJEU rend l'epreuve deterministe ET STRICTEMENT PLUS FORTE : au lieu de constater une
    # coincidence entre deux lectures, il prouve que `mesurer_harnais` propage EXACTEMENT la
    # charge utile qu'on lui donne. Le volet LIVE ci-dessus garde, lui, ce qu'il est seul a
    # pouvoir garder : que le host repond et que `loop_status` MESURE dessus.
    rejeu = _Rejeu(reponses)
    hb = LS.mesurer_harnais(rejeu)
    verifie(hb["live_runners"].mesuree == isinstance(lr, int),
            "le tri-etat de `live_runners` SUIT la forme capturee (lr=%r, mesuree=%s)"
            % (lr, hb["live_runners"].mesuree))
    if isinstance(lr, int):
        verifie(hb["live_runners"].valeur == lr,
                "la valeur propagee est celle de la reponse capturee (%s vs %s)"
                % (hb["live_runners"].valeur, lr))

    # La boucle se ferme ici, et EN DERNIER : `loop_status` juge sur l'entree REELLE, non
    # substituee. C'est la seule epreuve du volet exposee a l'etat de la plateforme, donc la
    # placer apres tout le reste maximise ce qui reste JUGE quand elle ne peut plus conclure.
    indispos, epreuves = juger_relecture(contrat, src)
    for cond, quoi in epreuves:
        verifie(cond, quoi)
    for x in indispos:
        indisponible(x)


# =====================================================================================
#  AUTO-EPREUVE du volet B -- le partage VOLATIL / CONTRACTUEL doit MORDRE des DEUX cotes
# =====================================================================================
#: Reponses FABRIQUEES. Fabriquer est legitime ICI (on eprouve le JUGE, comme [A'] mute une COPIE
#: du host) et proscrit dans le volet B, qui ne juge que ce que le host a reellement rendu. Ces
#: litteraux n'ont pas a rester fideles au host : c'est [A'] qui garde le host, et la forme
#: exigee ici est celle de `juger_forme`, dont ils sont l'entree.
_CONFORME = {
    "/api/admin/status": {"tacticus": {"running": False, "launcherOnly": False},
                          "session": None, "version": None},
    "/api/admin/drain": {"ok": True, "enabled": False, "liveRunners": None,
                         "liveRunnersSource": None,
                         "liveRunnersError": "aucune session Frida vivante"},
}


class _SourceFixe:
    """Source FABRIQUEE dont le transport peut LACHER apres N appels reussis.

    `ok_avant_panne=1` reproduit la course exacte de la PR #588 : une lecture passe, la suivante
    non -- ce n'est pas un host eteint, c'est un host qui a bouge SOUS la lecture.
    """

    def __init__(self, reponses: dict, ok_avant_panne: int = 1 << 30) -> None:
        self._r = dict(reponses)
        self._reste = ok_avant_panne

    def http_json(self, route: str) -> dict:
        if self._reste <= 0:
            raise OSError("transport simule : le host ne repond plus")
        self._reste -= 1
        if route not in self._r:
            raise KeyError("route non fabriquee : %s" % route)
        return self._r[route]


def etape_auto_epreuve_b(contrat: dict[str, list[str]]) -> None:
    """100 % deterministe -- aucun host interroge. VERT est le resultat SUSPECT : chaque face
    verifie que sa mutation a MORDU, et chaque temoin sain rend les mutations discriminantes."""
    print("\n[B'] AUTO-EPREUVE du volet B : VOLATIL -> INDISPONIBLE, CONTRACTUEL -> ROUGE")
    st, dr = _CONFORME["/api/admin/status"], _CONFORME["/api/admin/drain"]

    # -- TEMOIN SAIN. Sans lui, un juge qui rendrait FAUX en toutes circonstances passerait
    #    toutes les mutations qui suivent.
    tombees = [q for c, q in juger_forme(st, dr) if not c]
    verifie(tombees == [], "temoin : une reponse CONFORME ne fait tomber aucune epreuve (%s)"
                           % tombees)

    # -- FACE ROUGE : un champ CONTRACTUEL retire d'une reponse BIEN FORMEE accuse le code.
    for cle, dans_status in (("session", True), ("tacticus", True),
                             ("enabled", False), ("liveRunnersError", False)):
        cible = st if dans_status else dr
        mute = {k: v for k, v in cible.items() if k != cle}
        tombees = [q for c, q in juger_forme(mute if dans_status else st,
                                             dr if dans_status else mute) if not c]
        verifie(tombees != [],
                "champ `%s` RETIRE d'une reponse bien formee -> ROUGE (%d epreuve(s) tombee(s))"
                % (cle, len(tombees)))

    # -- FACE INDISPONIBLE : le transport LACHE apres un appel reussi.
    ind, epr = juger_relecture(contrat, _SourceFixe(_CONFORME, ok_avant_panne=1))
    verifie(ind != [], "transport qui LACHE -> INDISPONIBLE (%d), et pas un rouge" % len(ind))
    verifie(not any("MESURE sur la reponse reelle" in q for _, q in epr),
            "sous panne de transport, l'epreuve de MESURE n'est PAS jugee (ni verte ni rouge)")

    # -- TEMOIN de cette face : transport SAIN -> l'epreuve est jugee, et VERTE.
    ind, epr = juger_relecture(contrat, _SourceFixe(_CONFORME))
    verifie(ind == [], "transport SAIN -> aucune indisponibilite (%s)" % ind)
    verifie(any(c and "MESURE sur la reponse reelle" in q for c, q in epr),
            "transport SAIN -> l'epreuve de MESURE est jugee, et VERTE")

    # -- LA BORNE A NE PAS LAISSER GLISSER (#471) : une reponse OBTENUE mais inexploitable est un
    #    fait sur le CODE -> ROUGE. Si elle basculait en INDISPONIBLE, il suffirait d'un host lent
    #    pour que le cliquet cesse de garder quoi que ce soit. `[]` est une reponse VALIDE au sens
    #    du transport (elle arrive), et `mesurer_harnais` n'en tire aucune mesure.
    ind, epr = juger_relecture(contrat, _SourceFixe(
        {"/api/admin/status": [], "/api/admin/drain": dr}))
    verifie(ind == [], "reponse OBTENUE mais inexploitable : AUCUNE indisponibilite (%s)" % ind)
    verifie(any((not c) and "MESURE sur la reponse reelle" in q for c, q in epr),
            "reponse OBTENUE mais inexploitable -> ROUGE (la borne #471 ne glisse pas)")

    # -- L'EPREUVE DES ROUTES doit MORDRE, sinon elle est DECORATIVE (#439). Son gisement : une
    #    route INTERROGEE par `mesurer_harnais` mais ABSENTE du contrat derive -- le volet A serait
    #    alors aveugle dessus. On ampute le CONTRAT, pas le lecteur : muter `mesurer_harnais`
    #    casserait `contrat_lu` en amont (il en lit le SOURCE), donc n'isolerait rien.
    _, epr = juger_relecture({"/api/admin/status": []}, _SourceFixe(_CONFORME))
    verifie(any((not c) and "routes du contrat derive" in q for c, q in epr),
            "une route INTERROGEE hors du contrat derive -> ROUGE")


def main() -> int:
    print("probe_467-r4 -- contrat host <-> loop_status, source NON substituee")
    contrat = contrat_lu()
    etape_a(contrat)
    etape_auto_epreuve(contrat)
    etape_auto_epreuve_b(contrat)
    etape_b(contrat)
    print("")
    if ECHECS:
        # RESERVE ASSUMEE, la meme que `Get-CodeSortieBanque` : 64 ou 99 epreuves fautives
        # rendraient un code ambigu avec les sentinelles. Le probe en compte une quarantaine au
        # total ; l'ambiguite est notee, pas contournee.
        print("VERDICT: FAIL -- %d epreuve(s) fautive(s) :" % len(ECHECS))
        for x in ECHECS:
            print("  - %s" % x)
        # Le ROUGE PRIME (il accuse le code fusionne, information plus actionnable), mais un
        # indisponible reste NOMME : sinon corriger le rouge rendrait le probe vert sur une
        # epreuve jamais jugee.
        for x in INDISPONIBLE:
            print("  (INDISPONIBLE, non juge) %s" % x)
    elif INDISPONIBLE:
        print("VERDICT: INDISPONIBLE -- le volet LIVE s'est OUVERT et n'a pas pu CONCLURE :")
        for x in INDISPONIBLE:
            print("  - %s" % x)
        print("  Le depot n'est PAS accuse : un depot PARFAIT aurait subi le meme echec a cet")
        print("  instant -- l'etat de la plateforme a bouge sous la lecture. Deux causes MESUREES :")
        print("  le host sature (banque a parallelisme 16 : `/api/admin/status` a depasse 3 s alors")
        print("  qu'il ne touche pas le pump), et le pump Frida occupe par un build de runner")
        print("  concurrent (`rpcCall listRunners`, 5 s, du handler `/api/admin/drain`).")
        print("  Conduite : rejouer CETTE entree seule ; si elle passe, le DIRE dans la PR, jamais")
        print("  la taire. Aucun rejeu automatique ici -- un rejeu qui passe ne prouve rien.")
        return EX_INDISPONIBLE
    elif NON_MESURE:
        # Ni vert ni rouge, et surtout pas silencieux : le volet offline a juge, le volet
        # live n'a pas pu. Un `PASS` ici se lirait « le contrat host est verifie », ce qui
        # serait faux -- et c'est exactement la confusion que ce probe existe pour interdire.
        print("VERDICT: PASS PARTIEL -- contrat SOURCE honore ; contrat LIVE **NON MESURE** :")
        for x in NON_MESURE:
            print("  - %s" % x)
        print("  (host eteint : rejouer avec le host allume pour juger la forme reelle)")
        # rc 0 et NON 99, et c'est DELIBERE : ici le volet LIVE ne s'est jamais OUVERT, donc il ne
        # pretend aucun jugement. Le host est eteint la moitie du temps ; rendre 99 bloquerait la
        # banque une passe sur deux, et un garde-fou qui rougit partout se fait desactiver. Le 99
        # est reserve au volet qui a COMMENCE a juger et n'a pas pu conclure.
    else:
        print("VERDICT: PASS -- le host produit ce que loop_status lit, source ET forme reelle.")
    return len(ECHECS)


if __name__ == "__main__":
    sys.exit(main())
