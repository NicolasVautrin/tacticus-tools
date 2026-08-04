"""Probe #467 -- la FIDELITE de `loop_status`. Un etat de boucle dont le verdict derive ne vaut rien.

LE GISEMENT
-----------
`loop_status.py` est le seul instrument du depot qui garde la BOUCLE et non le CODE. Sa
degradation n'a AUCUN symptome : il n'echoue pas, il se TAIT -- et un slot d'agent vide qu'on ne
signale plus se lit exactement comme un depot au repos. C'est la meme signature que le capteur
mort de #273 (`rl_ingest --all` ingerant zero batch depuis un worktree, sans erreur), sauf qu'ici
personne ne va relire la sortie : elle n'existe que quand il y a quelque chose a dire.

Trois facons, MESUREES, dont cet outil peut mourir sans bruit :

  1. UN ZERO A LA PLACE D'UN << PAS MESURE >>. Le host eteint, `gh` hors ligne : si `liveRunners`
     retombe a 0 au lieu de rester `None`, l'orchestrateur lance 4 tests sur un budget partage
     inconnu -- la faute deja commise (2 fichiers rendus en `timed out`). Meme forme pour
     << 0 PR ouverte >> quand `gh` n'a simplement pas repondu.
  2. LE RACCOURCI DE FLOTTE QUI DERIVE. Le decompte des agents en vol passe par le pre-filtre
     `only_alive` de `fleet_board` (54,8 s -> 0,2 s sur 870 transcripts). Si ce raccourci cesse
     d'etre EXACT, le compteur de slots ment -- et c'est precisement le chiffre pour lequel
     l'outil existe.
  3. LE DECLENCHEUR QUI SE TAIT (ou qui hurle). Un hook `Stop` qui ne parle jamais est un
     garde-fou mort ; un hook qui parle a chaque tour d'un depot au repos se fait desarmer par
     son proprietaire en une journee. Les deux directions se gardent.

CE QUE CE CLIQUET EST SEUL A VOIR : il n'existe aucun autre chemin vers ces trois-la. `probe_273`
garde les entrees GITIGNOREES lues depuis la racine, pas les sorties d'un outil ; `probe_457` ne
joue que `scripts/python/tests`, ou `loop_status` n'a aucun test ; et la banque entiere garde du
CODE, dont la degradation produit un rouge -- alors que celle-ci ne produit rien.

COMMENT IL S'Y PREND. Toutes les entrees de `loop_status` passent par la facade `Sources`, qui est
SUBSTITUEE ici. Sans cette couture, garder le tri-etat exigerait d'eteindre le host, ce qu'aucun
cliquet ne peut faire -- et un cliquet qui depend de l'etat de la machine n'est pas un cliquet.
Aucun appel reel a git, `gh` ou au host : ce probe est 100 % offline et deterministe.

Il ECRIT dans un tmpdir SYSTEME (`mkdtemp()` sans `dir=`), jamais sous `scripts/python/` que la
banque enumere en parallele (#455).

Sortie ASCII stricte (cp1252). Code de sortie = nombre d'epreuves fautives.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fleet_board                                                     # noqa: E402
import loop_status as LS                                               # noqa: E402

ECHECS: list[str] = []


def verifie(cond: bool, quoi: str) -> None:
    if cond:
        print("  OK    %s" % quoi)
    else:
        print("  ROUGE %s" % quoi)
        ECHECS.append(quoi)


# =====================================================================================
#  Sources SUBSTITUEES -- aucune entree reelle
# =====================================================================================
class FauxSources(LS.Sources):
    """Repond aux memes questions que `Sources`, depuis un scenario ecrit."""

    def __init__(self, *, status_v2: str = "", worktrees: str = "", mergees: str = "",
                 ancetre: bool = True, prs: list | None = None, gh_ko: str | None = None,
                 http: dict | None = None, http_ko: str | None = None,
                 rows: list | None = None, dossier: Path | None = None) -> None:
        super().__init__(repo=Path("/faux"), ttl_cache=0.0)
        self._status_v2, self._worktrees, self._mergees = status_v2, worktrees, mergees
        self._ancetre, self._prs, self._gh_ko = ancetre, prs, gh_ko
        self._http, self._http_ko = http or {}, http_ko
        self._rows, self._dossier = rows or [], dossier

    def git(self, *args: str) -> tuple[int, str]:
        if args[:1] == ("status",):
            return 0, self._status_v2
        if args[:2] == ("worktree", "list"):
            return 0, self._worktrees
        if args[:2] == ("for-each-ref", "--merged"):
            return 0, self._mergees
        if args[:1] == ("merge-base",):
            return (0 if self._ancetre else 1), ""
        if args[:1] == ("rev-list",):
            return 0, "0\n"
        raise AssertionError("git non scripte : %r" % (args,))

    def gh(self, *args: str) -> tuple[int, str]:
        if self._gh_ko:
            raise RuntimeError(self._gh_ko)
        return 0, json.dumps(self._prs or [])

    def http_json(self, chemin: str) -> dict:
        if self._http_ko:
            raise RuntimeError(self._http_ko)
        return self._http.get(chemin, {})

    def flotte(self) -> list[dict]:
        return self._rows

    def dossier_verdicts(self) -> Path | None:
        return self._dossier

    def lire_cache_gh(self):
        return None

    def ecrire_cache_gh(self, prs) -> None:
        pass


def _agent(nom: str, wt: str = "") -> dict:
    return {"name": nom, "wt": wt, "state": "vif"}


def _statut_v2(branche="master", upstream="origin/master", avance=0,
               suivis=(), non_suivis=()) -> str:
    L = ["# branch.oid " + "0" * 40, "# branch.head " + branche]
    if upstream:
        L.append("# branch.upstream " + upstream)
        L.append("# branch.ab +%d -0" % avance)
    for f in suivis:
        L.append("1 .M N... 100644 100644 100644 %s %s %s" % ("0" * 40, "0" * 40, f))
    for f in non_suivis:
        L.append("? " + f)
    return "\n".join(L) + "\n"


def _wt_porcelain(entrees: list[tuple[str, str]]) -> str:
    return "\n\n".join("worktree %s\nHEAD %s\nbranch refs/heads/%s" % (c, "0" * 40, b)
                       for c, b in entrees) + "\n"


def _verdict(dossier: Path, nom: str, *, sha: str, rc: int | None,
             etat: str, entete_cassee: bool = False) -> Path:
    p = dossier / nom
    if entete_cassee:
        # La forme REELLE des verdicts ecrits avant le correctif de precedence PowerShell du
        # 2026-08-04 : tout l'en-tete sur une ligne, et AUCUNE ligne `rc`.
        corps = ["commit  : %s sujet   : x quand   : y mur     : 1,0 s" % sha, "",
                 "[ratchets] BANQUE VERTE -- 37 cliquet(s), mur 1,0 s.",
                 "[ratchets-bg] %s -- commit %s, 1,0 s" % (etat, sha[:8])]
    else:
        corps = ["commit  : %s" % sha, "sujet   : x", "quand   : y", "mur     : 1,0 s",
                 "rc      : %s  (%s)" % (rc, etat), ""]
    p.write_text("\n".join(corps), encoding="utf-8")
    return p


# =====================================================================================
#  1. TRI-ETAT -- un zero ne remplace JAMAIS un << pas mesure >>
# =====================================================================================
def etape_1_tri_etat() -> None:
    print("\n[1] TRI-ETAT : host eteint, `gh` hors ligne")
    src = FauxSources(status_v2=_statut_v2(), worktrees="", mergees="",
                      gh_ko="gh absent du PATH", http_ko="connexion refusee",
                      rows=[], dossier=None)
    e = LS.etat(src, 5, {})
    ha, lv, bq = e["harnais"], e["livraison"], e["banque"]

    for cle in ("session", "drain", "live_runners"):
        m = ha[cle]
        verifie(not m.mesuree and m.valeur is None,
                "harnais.%s = PAS MESURE (et pas un zero)" % cle)
    verifie(not lv["pr_ouvertes"].mesuree,
            "livraison.pr_ouvertes = PAS MESURE quand `gh` ne repond pas")
    verifie(not bq["verdict"].mesuree,
            "banque.verdict = PAS MESURE quand logs/ratchets-bg est introuvable")

    # Le RENDU doit porter l'ignorance, pas la maquiller. C'est la moitie qui compte : une
    # mesure `None` correctement calculee mais imprimee `0` se lit comme un zero.
    sig, ctx = LS.signaux(e)
    texte = LS.rendu_complet(e, sig, ctx)
    verifie("liveRunners ?" in texte, "le rendu ecrit `liveRunners ?`, jamais `liveRunners 0`")
    verifie("liveRunners 0" not in texte, "aucun `liveRunners 0` dans un rendu non mesure")
    verifie("PR ouvertes : 0" not in texte, "aucune `PR ouvertes : 0` quand `gh` n'a pas repondu")

    # AUTO-EPREUVE du critere : sur un etat ou la mesure VAUT zero, les memes predicats doivent
    # basculer. Sans ca, ils passeraient aussi sur un outil qui rend systematiquement `None`.
    src2 = FauxSources(status_v2=_statut_v2(), prs=[],
                       http={"/api/admin/status": {"session": {"id": 1, "status": "running"},
                                                   "tacticus": {"running": True}},
                             "/api/admin/drain": {"enabled": False, "liveRunners": 0,
                                                  "liveRunnersSource": "hooks"}},
                       rows=[], dossier=None)
    e2 = LS.etat(src2, 5, {})
    s2, c2 = LS.signaux(e2)
    t2 = LS.rendu_complet(e2, s2, c2)
    verifie(e2["harnais"]["live_runners"].mesuree and e2["harnais"]["live_runners"].valeur == 0,
            "contre-epreuve : un VRAI zero reste un zero mesure")
    verifie("liveRunners 0" in t2 and "liveRunners ?" not in t2,
            "contre-epreuve : le rendu distingue le zero mesure de l'ignorance")


# =====================================================================================
#  2. LE RACCOURCI DE FLOTTE EST EXACT
# =====================================================================================
def etape_2_raccourci_flotte() -> None:
    print("\n[2] fleet_board.collect(only_alive) == les << vif >> du balayage COMPLET")
    tmp = Path(tempfile.mkdtemp(prefix="probe467-"))          # tmpdir SYSTEME (#455)
    try:
        racine = tmp / "projets"
        sub = racine / "sessionA" / "subagents"
        sub.mkdir(parents=True)
        wt_vivant = tmp / "wt-vivant"
        wt_vivant.mkdir()
        maintenant = time.time()

        def poser(aid: str, minutes: float, worktree: str) -> Path:
            """Un transcript dont l'horodatage INTERNE et le mtime sont a `minutes` du present."""
            quand = time.strftime("%Y-%m-%dT%H:%M:%S",
                                  time.gmtime(maintenant - minutes * 60.0)) + ".000Z"
            p = sub / ("agent-%s.jsonl" % aid)
            p.write_text("\n".join([
                json.dumps({"timestamp": quand,
                            "message": {"role": "user", "content": "brief %s" % aid}}),
                json.dumps({"timestamp": quand,
                            "message": {"role": "assistant",
                                        "usage": {"input_tokens": 10,
                                                  "cache_read_input_tokens": 50000},
                                        "content": [{"type": "text", "text": "t"}]}}),
            ]) + "\n", encoding="utf-8")
            (sub / ("agent-%s.meta.json" % aid)).write_text(
                json.dumps({"description": "agent " + aid, "worktreePath": worktree,
                            "agentType": "opus-solver", "worktreeBranch": "b-" + aid}),
                encoding="utf-8")
            os.utime(p, (maintenant - minutes * 60.0, maintenant - minutes * 60.0))
            return p

        poser("VIF", 1.0, str(wt_vivant))                     # ecrit a l'instant   -> vif
        poser("ATTENTE", 90.0, str(wt_vivant))                # silencieux + wt     -> attente
        poser("FINI", 90.0, str(tmp / "wt-disparu"))          # silencieux, wt mort -> fini
        poser("ORPHELIN", 90.0, "")                           # silencieux, sans wt -> fini

        vrai_project_dir = fleet_board.project_dir
        fleet_board.project_dir = lambda: racine               # noqa: E731
        try:
            complet = fleet_board.collect(include_done=False)
            rapide = fleet_board.collect(include_done=False, only_alive=True)
        finally:
            fleet_board.project_dir = vrai_project_dir

        vifs_complet = sorted(r["id"] for r in complet if r["state"] == "vif")
        vifs_rapide = sorted(r["id"] for r in rapide)
        verifie(vifs_complet == ["VIF"],
                "le balayage complet voit exactement un agent vif (%s)" % vifs_complet)
        verifie(vifs_rapide == vifs_complet,
                "only_alive rend EXACTEMENT les memes vifs (%s vs %s)" % (vifs_rapide, vifs_complet))
        verifie(all(r["state"] == "vif" for r in rapide),
                "only_alive ne rend QUE des vifs (contrat du mode rapide)")
        verifie(sorted(r["state"] for r in complet) == ["attente", "vif"],
                "le mode complet garde l'etat `attente`, que le rapide renonce a voir")

        # Le pre-filtre lui-meme : il ne doit ecarter QUE des transcripts trop vieux.
        tous = fleet_board.transcripts(racine, only_alive=False)
        gardes = fleet_board.transcripts(racine, only_alive=True)
        verifie(len(tous) == 4 and len(gardes) == 1,
                "le pre-filtre par mtime garde 1 transcript sur 4 (%d/%d)" % (len(gardes), len(tous)))
        verifie(set(gardes) <= set(tous), "le pre-filtre est un SOUS-ensemble du balayage")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =====================================================================================
#  3. LE DECLENCHEUR SE TAIT quand il le doit
# =====================================================================================
def etape_3_silence() -> None:
    print("\n[3] SILENCE : depot au repos, chaine deja relancee, autre projet")
    tmp = Path(tempfile.mkdtemp(prefix="probe467-"))
    try:
        _verdict(tmp, "aaaaaaaa-1.txt", sha="a" * 40, rc=0, etat="VERTE")
        repos = FauxSources(
            status_v2=_statut_v2(avance=0), worktrees="", mergees="", ancetre=True, prs=[],
            http={"/api/admin/status": {"session": {"id": 1, "status": "running", "pid": 9},
                                        "tacticus": {"running": True}},
                  "/api/admin/drain": {"enabled": False, "liveRunners": 0,
                                       "liveRunnersSource": "hooks"}},
            rows=[], dossier=tmp)
        sig, _ = LS.signaux(LS.etat(repos, 5, {}))
        verifie(sig == [], "depot au REPOS (0 agent, 0 worktree, 0 PR, 0 commit) -> AUCUN signal")

        # Le meme etat, mais la campagne est en cours : les slots libres doivent se voir.
        actif = FauxSources(
            status_v2=_statut_v2(avance=0),
            worktrees=_wt_porcelain([(r"C:/r/.claude/worktrees/agent-1", "worktree-agent-1")]),
            mergees="", ancetre=True, prs=[],
            http=repos._http, rows=[_agent("un", r"C:/r/.claude/worktrees/agent-1")],
            dossier=tmp)
        cles = {s.cle for s in LS.signaux(LS.etat(actif, 5, {}))[0]}
        verifie("slots" in cles,
                "campagne EN COURS + 1/5 en vol -> les 4 slots libres se voient (%s)" % sorted(cles))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Les gardes du mode hook, joues par `main()` -- le vrai point d'entree.
    charge_relance = json.dumps({"cwd": str(LS.REPO), "stop_hook_active": True})
    charge_autre = json.dumps({"cwd": str(Path(tempfile.gettempdir()) / "un-autre-projet"),
                               "stop_hook_active": False})
    cas = [
        ("stop_hook_active -> silence (anti-boucle)", charge_relance),
        ("cwd hors du depot -> silence (le hook Stop peut etre GLOBAL)", charge_autre),
        # GISEMENT MESURE : PowerShell 5.1 prefixe d'un BOM tout ce qu'il pipe vers un natif.
        # Le BOM faisait lever `json.loads`, la charge retombait a vide, et le hook parlait
        # MALGRE `stop_hook_active` -- la boucle meme qu'il doit eviter.
        ("charge prefixee d'un BOM UTF-8 -> lue quand meme (garde anti-boucle intact)",
         "﻿" + charge_relance),
        # Une charge ILLISIBLE ne doit pas se rabattre sur << pas de garde >> : on se tait.
        ("charge JSON illisible -> silence (defaut SUR)", "{ceci n'est pas du json"),
    ]
    for nom, charge in cas:
        vrai_stdin, vrai_stdout = sys.stdin, sys.stdout
        buf = io.StringIO()
        sys.stdin, sys.stdout = io.StringIO(charge), buf
        try:
            rc = LS.main(["--hook", "--repo", str(LS.REPO)])
        finally:
            sys.stdin, sys.stdout = vrai_stdin, vrai_stdout
        verifie(rc == 0 and buf.getvalue().strip() == "", nom)


# =====================================================================================
#  4. LE DECLENCHEUR PARLE quand il le doit
# =====================================================================================
def etape_4_parole() -> None:
    print("\n[4] PAROLE : chaque gisement produit SON signal")
    tmp = Path(tempfile.mkdtemp(prefix="probe467-"))
    try:
        base_http = {"/api/admin/status": {"session": {"id": 1, "status": "running", "pid": 9},
                                           "tacticus": {"running": True}},
                     "/api/admin/drain": {"enabled": False, "liveRunners": 0,
                                          "liveRunnersSource": "hooks"}}
        wts = _wt_porcelain([(r"C:/r/.claude/worktrees/agent-1", "worktree-agent-1"),
                             (r"C:/r/.claude/worktrees/agent-2", "worktree-agent-2")])

        # -- la scene du 2026-08-04 : 1 agent sur 5, 30 commits d'avance, worktrees livres
        _verdict(tmp, "bbbbbbbb-1.txt", sha="b" * 40, rc=2, etat="ROUGE (2)")
        s = FauxSources(status_v2=_statut_v2(avance=30, suivis=("engine/x.py",)),
                        worktrees=wts, mergees="worktree-agent-1\nworktree-agent-2\n",
                        ancetre=True, prs=[], http=base_http,
                        rows=[_agent("solo", r"C:/r/.claude/worktrees/agent-9")], dossier=tmp)
        e = LS.etat(s, 5, {})
        cles = {x.cle for x in LS.signaux(e)[0]}
        for attendu in ("slots", "push", "sale", "nettoyage", "banque"):
            verifie(attendu in cles, "signal `%s` emis (%s)" % (attendu, sorted(cles)))
        verifie(len(e["livraison"]["nettoyables"].valeur) == 2,
                "les 2 worktrees d'agents livres sont proposes au nettoyage")

        # -- un agent EN VOL sur une branche deja mergee n'est JAMAIS propose au nettoyage
        s2 = FauxSources(status_v2=_statut_v2(), worktrees=wts,
                         mergees="worktree-agent-1\nworktree-agent-2\n", prs=[], http=base_http,
                         rows=[_agent("occupe", r"C:/r/.claude/worktrees/agent-1")], dossier=tmp)
        nett = LS.etat(s2, 5, {})["livraison"]["nettoyables"].valeur
        verifie([w["branche"] for w in nett] == ["worktree-agent-2"],
                "le worktree d'un agent EN VOL est retire des nettoyables (%s)"
                % [w["branche"] for w in nett])

        # -- drain arme, et session absente : deux pannes de harnais, deux signaux
        s3 = FauxSources(status_v2=_statut_v2(), worktrees="", mergees="", prs=[],
                         http={"/api/admin/status": {"session": None,
                                                     "tacticus": {"running": False}},
                               "/api/admin/drain": {"enabled": True, "liveRunners": 0,
                                                    "liveRunnersSource": "hooks"}},
                         rows=[], dossier=tmp)
        cles3 = {x.cle for x in LS.signaux(LS.etat(s3, 5, {}))[0]}
        verifie("drain" in cles3, "mode DRAIN arme -> signal")
        verifie("session" in cles3, "aucune session Frida -> signal")

        # -- runners vivants sans aucun agent en vol : des orphelins
        s4 = FauxSources(status_v2=_statut_v2(), worktrees="", mergees="", prs=[],
                         http={"/api/admin/status": {"session": {"id": 1, "status": "running"},
                                                     "tacticus": {"running": True}},
                               "/api/admin/drain": {"enabled": False, "liveRunners": 3,
                                                    "liveRunnersSource": "hooks"}},
                         rows=[], dossier=tmp)
        verifie("orphelins" in {x.cle for x in LS.signaux(LS.etat(s4, 5, {}))[0]},
                "3 runners vivants et 0 agent en vol -> signal orphelins")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =====================================================================================
#  5. LE VERDICT DE BANQUE SE LIT SOUS SES DEUX FORMES
# =====================================================================================
def etape_5_verdict() -> None:
    print("\n[5] VERDICT de banque : en-tete normal ET en-tete cassee (gisement mesure)")
    tmp = Path(tempfile.mkdtemp(prefix="probe467-"))
    try:
        p = _verdict(tmp, "cccccccc-1.txt", sha="c" * 40, rc=0, etat="VERTE")
        sha, rc, etiq = LS._lire_verdict(p)
        verifie((sha, rc) == ("c" * 40, 0) and etiq == "VERTE",
                "en-tete normale : commit + rc + etiquette lus (%s, %s)" % (rc, etiq))

        p2 = _verdict(tmp, "dddddddd-1.txt", sha="d" * 40, rc=None, etat="VERTE",
                      entete_cassee=True)
        sha2, rc2, etiq2 = LS._lire_verdict(p2)
        verifie(rc2 == 0 and sha2 == "d" * 40,
                "en-tete CASSEE (sans ligne rc) : le rc se retrouve dans le corps (rc=%s)" % rc2)

        # L'etiquette d'un ROUGE porte ses PROPRES parentheses -- un `rstrip(')')` gourmand les
        # mangeait toutes et rendait `rc=2 [ROUGE (2]`, desequilibre sur le seul regime qui compte.
        p2b = _verdict(tmp, "dd2-1.txt", sha="2" * 40, rc=2, etat="ROUGE (2)")
        _, rc2b, etiq2b = LS._lire_verdict(p2b)
        verifie((rc2b, etiq2b) == (2, "ROUGE (2)"),
                "etiquette d'un ROUGE lue ENTIERE, parentheses imbriquees comprises (%r)" % etiq2b)

        # Un verdict dont le rc reste introuvable est un CAPTEUR MUET, pas un vert.
        p3 = tmp / "eeeeeeee-1.txt"
        p3.write_text("commit  : %s\nsujet   : x\n" % ("e" * 40), encoding="utf-8")
        _, rc3, _ = LS._lire_verdict(p3)
        verifie(rc3 is None, "verdict sans aucun rc lisible -> None (jamais 0)")

        src = FauxSources(status_v2=_statut_v2(), worktrees="", mergees="", prs=[],
                          http={"/api/admin/status": {"session": {"id": 1, "status": "running"},
                                                      "tacticus": {"running": True}},
                                "/api/admin/drain": {"enabled": False, "liveRunners": 0,
                                                     "liveRunnersSource": "hooks"}},
                          rows=[], dossier=tmp)
        cles = {x.cle for x in LS.signaux(LS.etat(src, 5, {}))[0]}
        verifie("banque-illisible" in cles,
                "un verdict au rc illisible est SIGNALE, pas avale (%s)" % sorted(cles))

        # Un vert DEJA livre (son commit est dans origin/master) n'appelle aucun geste.
        for f in tmp.glob("*.txt"):
            f.unlink()
        _verdict(tmp, "ffffffff-1.txt", sha="f" * 40, rc=0, etat="VERTE")
        src_livre = FauxSources(status_v2=_statut_v2(), worktrees="", mergees="", prs=[],
                                ancetre=True, http=src._http, rows=[], dossier=tmp)
        verifie(LS.signaux(LS.etat(src_livre, 5, {}))[0] == [],
                "verdict VERT deja dans origin/master -> silence")
        src_non_livre = FauxSources(status_v2=_statut_v2(), worktrees="", mergees="", prs=[],
                                    ancetre=False, http=src._http, rows=[], dossier=tmp)
        verifie("banque" in {x.cle for x in LS.signaux(LS.etat(src_non_livre, 5, {}))[0]},
                "verdict VERT dont le commit n'est PAS dans origin/master -> signale une fois")

        # L'ARBRE JUGE d'abord. `host_inputs.resolve` part de SA racine, pas de celle qu'on
        # demande : pris dans cet ordre, un `--repo` explicite lisait les verdicts d'un AUTRE
        # arbre -- et rapportait donc un vert etranger sur un depot qui portait un rouge.
        faux_repo = Path(tempfile.mkdtemp(prefix="probe467-repo-"))
        try:
            (faux_repo / "logs" / "ratchets-bg").mkdir(parents=True)
            reel = LS.Sources(repo=faux_repo, avec_gh=False, avec_host=False)
            verifie(reel.dossier_verdicts() == faux_repo / "logs" / "ratchets-bg",
                    "dossier_verdicts respecte `--repo` quand l'arbre juge a bien le repertoire")
            vide = LS.Sources(repo=faux_repo / "sans-logs", avec_gh=False, avec_host=False)
            d = vide.dossier_verdicts()
            verifie(d is None or d != faux_repo / "logs" / "ratchets-bg",
                    "sans repertoire local, le repli host_inputs prend le relais (ou None)")
        finally:
            shutil.rmtree(faux_repo, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =====================================================================================
#  6. LE PLAFOND EST UN PARAMETRE VISIBLE, le nombre EN VOL une MESURE
# =====================================================================================
def etape_6_plafond() -> None:
    print("\n[6] PLAFOND parametrable, EN VOL derive")
    src = FauxSources(status_v2=_statut_v2(avance=1), worktrees="", mergees="", prs=[],
                      http={"/api/admin/status": {"session": {"id": 1, "status": "running"},
                                                  "tacticus": {"running": True}},
                            "/api/admin/drain": {"enabled": False, "liveRunners": 0,
                                                 "liveRunnersSource": "hooks"}},
                      rows=[_agent("a"), _agent("b")], dossier=None)
    for plafond, attendu in ((5, 3), (2, 0), (8, 6)):
        fl = LS.etat(src, plafond, {})["flotte"]
        verifie(fl["en_vol"].valeur == 2 and fl["libres"].valeur == attendu,
                "plafond %d -> %d libre(s) pour 2 en vol" % (plafond, attendu))
    # Le nombre EN VOL ne peut pas etre une saisie : il vient de la flotte.
    fl = LS.etat(FauxSources(status_v2=_statut_v2(), rows=[], dossier=None), 5, {})["flotte"]
    verifie(fl["en_vol"].valeur == 0 and fl["libres"].valeur == 5,
            "flotte vide -> 0 en vol, 5 libres")


# =====================================================================================
#  7. `gh` MUET -- le repli peut SIGNALER, jamais RASSURER (#467-r6)
# =====================================================================================
def _pose_cache(repo: Path, prs: list, age_s: float) -> None:
    p = repo / "logs" / "loop-status-gh.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"quand": time.time() - age_s, "prs": prs}), encoding="utf-8")


class GhMuet(LS.Sources):
    """Tout est REEL sauf `gh`, qui echoue -- le gisement mesure de #467-r6."""

    def __init__(self, repo: Path, cause: str) -> None:
        super().__init__(repo=repo, avec_host=False, ttl_cache=0.0)
        self._cause = cause

    def gh(self, *args: str) -> tuple[int, str]:
        raise RuntimeError(self._cause)

    def git(self, *args: str) -> tuple[int, str]:
        if args[:1] == ("status",):
            return 0, _statut_v2()
        if args[:2] == ("worktree", "list"):
            return 0, ""
        return 0, ""

    def flotte(self) -> list[dict]:
        return []

    def dossier_verdicts(self) -> Path | None:
        return None


def etape_7_gh_muet() -> None:
    print("\n[7] `gh` MUET : le repli SIGNALE, il ne RASSURE jamais (#467-r6)")
    tmp = Path(tempfile.mkdtemp(prefix="probe467-gh-"))          # tmpdir SYSTEME (#455)
    try:
        ouverte = [{"number": 999, "title": "t", "headRefName": "b", "state": "OPEN"}]

        # -- (a) AUCUN cache : PAS MESURE. C'est l'exigence dure -- jamais un zero.
        s = GhMuet(tmp, "gh: delai depasse (10 s)")
        lv = LS.mesurer_livraison(s)
        verifie(not lv["pr_ouvertes"].mesuree, "gh muet sans cache -> PAS MESURE")
        txt = LS.rendu_complet(LS.etat(s, 5, {}), *LS.signaux(LS.etat(s, 5, {})))
        verifie("PR ouvertes : 0" not in txt, "gh muet sans cache -> jamais `PR ouvertes : 0`")
        verifie("delai depasse" in txt,
                "la CAUSE est nommee dans le rendu, pas reduite a un `rc=127`")

        # -- (b) cache RECENT portant une PR ouverte : servi, AVEC son age et la panne.
        _pose_cache(tmp, ouverte, 480.0)
        lv = LS.mesurer_livraison(GhMuet(tmp, "gh: delai depasse (10 s)"))
        verifie(lv["pr_ouvertes"].mesuree and len(lv["pr_ouvertes"].valeur) == 1,
                "cache recent portant 1 PR ouverte -> servi en repli")
        verifie(lv.get("gh_repli") and "8 min" in _age_gh_de(lv),
                "l'age du repli est RENDU (%s)" % _age_gh_de(lv))
        verifie("gh muet" in _age_gh_de(lv),
                "la panne de `gh` est RENDUE a cote du chiffre servi (%s)" % _age_gh_de(lv))
        verifie(not lv["nettoyables"].mesuree or lv["nettoyables"].valeur == [],
                "sous repli, AUCUN nettoyage de worktree n'est propose (instantane perime)")

        # -- (c) L'ASYMETRIE, le coeur du correctif : un cache qui dit << 0 PR >> ne prouve
        #    RIEN quand `gh` est muet. Le rabattre en mesure ferait taire l'outil sur une PR
        #    ouverte depuis, exactement l'oubli que le hook existe pour attraper.
        _pose_cache(tmp, [{"number": 1, "headRefName": "x", "state": "MERGED"}], 60.0)
        lv = LS.mesurer_livraison(GhMuet(tmp, "gh introuvable (PATH + emplacements connus)"))
        verifie(not lv["pr_ouvertes"].mesuree,
                "cache SANS PR ouverte + gh muet -> PAS MESURE (jamais un zero rassurant)")

        # -- (d) cache TROP VIEUX : hors borne, on retombe sur PAS MESURE.
        _pose_cache(tmp, ouverte, LS.Sources.AGE_MAX_REPLI + 60.0)
        lv = LS.mesurer_livraison(GhMuet(tmp, "gh: delai depasse (10 s)"))
        verifie(not lv["pr_ouvertes"].mesuree,
                "cache plus vieux que AGE_MAX_REPLI -> PAS MESURE")

        # -- (e) CONTRE-EPREUVE du repli lui-meme : `gh` qui REPOND doit rendre une mesure
        #    FRAICHE, sans mention de panne. Sans elle, (b) passerait aussi sur un outil qui
        #    servirait TOUJOURS le cache.
        _pose_cache(tmp, ouverte, 480.0)
        s_ok = GhMuet(tmp, "x")
        s_ok.gh = lambda *a: (0, json.dumps(ouverte))            # type: ignore[assignment]
        lv_ok = LS.mesurer_livraison(s_ok)
        verifie(lv_ok["pr_ouvertes"].mesuree and not lv_ok.get("gh_repli"),
                "gh qui REPOND -> mesure fraiche, aucune mention de repli")
        verifie("gh muet" not in _age_gh_de(lv_ok),
                "aucune panne annoncee quand il n'y en a pas (%r)" % _age_gh_de(lv_ok))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # -- LES CAUSES, exercees sur le VRAI `Sources.gh` (et non sur une substitution).
    #    CE BLOC EXISTE PARCE QUE LA CONTRE-EPREUVE A TROUVE UN GARDE AVEUGLE : l'epreuve
    #    << la cause est nommee >> ci-dessus lit le rendu d'un `GhMuet` qui leve SA PROPRE
    #    cause -- elle reste donc verte meme si `Sources.gh` refond tout en `rc=127`. Un
    #    garde qui substitue precisement le code qu'il pretend juger ne juge rien : c'est le
    #    meme vice que #467-r4 (deux lecteurs, une entree morte), a l'echelle d'une methode.
    #    On substitue donc `subprocess.run`, d'un cran EN DESSOUS, pour que le corps de `gh`
    #    soit reellement traverse.
    vrai_run = LS.subprocess.run
    vrai_exe = os.environ.get("TACTICUS_GH_EXE")
    os.environ["TACTICUS_GH_EXE"] = sys.executable          # un exe qui EXISTE : la garde passe

    def _leve(ex):
        def _f(*a, **k):
            raise ex
        return _f

    class _Fini:
        def __init__(self, rc):
            self.returncode, self.stdout = rc, ""

    try:
        src_reel = LS.Sources(repo=LS.REPO, timeout_gh=7.0)
        cas_gh = [
            (_leve(LS.subprocess.TimeoutExpired("gh", 7.0)), "delai depasse",
             "un DEPASSEMENT DE DELAI se nomme (c'etait la cause reelle de #467-r6)"),
            # `OSError(2, ...)` s'instancie en `FileNotFoundError` (Python mappe l'errno) :
            # on leve un OSError NU pour que l'epreuve porte sur le type RENDU, pas sur la
            # table errno de l'interpreteur.
            (_leve(OSError("panne")), "OSError",
             "une panne systeme porte son type, pas un code muet"),
        ]
        for faux_run, attendu, quoi in cas_gh:
            LS.subprocess.run = faux_run                     # type: ignore[assignment]
            try:
                src_reel.gh("pr", "list")
                msg = "(aucune levee)"
            except RuntimeError as e:
                msg = str(e)
            verifie(attendu in msg and "rc=127" not in msg, "%s (%r)" % (quoi, msg))

        # Un rc NON NUL de `gh` (non authentifie, depot inconnu) doit remonter SON code.
        # Le repo est un tmpdir VIERGE, et ce n'est pas un detail : sur un vrai checkout,
        # `logs/loop-status-gh.json` existe, le repli s'enclenche et l'epreuve devient verte
        # sans rien avoir juge -- constate en jouant la contre-epreuve.
        vierge = Path(tempfile.mkdtemp(prefix="probe467-rc-"))
        try:
            LS.subprocess.run = lambda *a, **k: _Fini(4)      # type: ignore[assignment]
            m, _, _, _, _ = LS._gh_prs(LS.Sources(repo=vierge, ttl_cache=0.0))
            verifie(not m.mesuree and "rc=4" in (m.erreur or ""),
                    "un rc non nul de `gh` remonte SON code, pas la sentinelle 127 (%r)"
                    % m.erreur)
        finally:
            shutil.rmtree(vierge, ignore_errors=True)
    finally:
        LS.subprocess.run = vrai_run                          # type: ignore[assignment]
        if vrai_exe is None:
            os.environ.pop("TACTICUS_GH_EXE", None)
        else:
            os.environ["TACTICUS_GH_EXE"] = vrai_exe

    # -- LE BUDGET, cause MESUREE de #467-r6. Sous `--hook`, `gh` doit disposer d'un budget
    #    STRICTEMENT plus large que le budget general : a 3 s (l'ancien reglage, partage avec
    #    les sous-process git), `gh` seul mettait deja 2,90 s et 5 tours sur 8 rendaient la
    #    ligne PR aveugle. Sans cette epreuve, un retour au budget commun passerait inapercu --
    #    il ne casse rien, il rend juste l'outil muet sur ce poste.
    vus: dict = {}
    vrai_sources = LS.Sources

    class Espion(LS.Sources):
        def __init__(self, **kw):
            vus.update(kw)
            super().__init__(**kw)

    LS.Sources = Espion                                          # type: ignore[misc]
    vrai_stdin = sys.stdin
    sys.stdin = io.StringIO("")
    try:
        LS.main(["--hook", "--repo", str(LS.REPO), "--no-gh", "--no-host"])
    finally:
        sys.stdin = vrai_stdin
        LS.Sources = vrai_sources                                # type: ignore[misc]
    verifie(vus.get("timeout_gh", 0.0) > vus.get("timeout", 1e9),
            "sous --hook, le budget de `gh` (%s s) depasse le budget general (%s s)"
            % (vus.get("timeout_gh"), vus.get("timeout")))

    # La resolution de `gh` par chemin absolu : `TACTICUS_GH_EXE` est EXCLUSIF -- pose sur un
    # chemin inexistant, il ne doit pas retomber en silence sur le PATH (meme discipline que
    # `TACTICUS_HOST_DATA_ROOT`, #273), sinon l'echappatoire mentirait sur ce qu'elle lance.
    vrai = os.environ.get("TACTICUS_GH_EXE")
    try:
        os.environ["TACTICUS_GH_EXE"] = str(Path(tempfile.gettempdir()) / "gh-qui-nexiste-pas.exe")
        verifie(LS.Sources(repo=LS.REPO).exe_gh() is None,
                "TACTICUS_GH_EXE inexistant -> gh introuvable (pas de repli muet sur le PATH)")
    finally:
        if vrai is None:
            os.environ.pop("TACTICUS_GH_EXE", None)
        else:
            os.environ["TACTICUS_GH_EXE"] = vrai


def _age_gh_de(lv: dict) -> str:
    return LS._age_gh(lv)


def main() -> int:
    print("probe_467 -- fidelite de loop_status (100 % offline, sources substituees)")
    for etape in (etape_1_tri_etat, etape_2_raccourci_flotte, etape_3_silence,
                  etape_4_parole, etape_5_verdict, etape_6_plafond, etape_7_gh_muet):
        etape()
    print("")
    if ECHECS:
        print("VERDICT: FAIL -- %d epreuve(s) fautive(s) :" % len(ECHECS))
        for x in ECHECS:
            print("  - %s" % x)
    else:
        print("VERDICT: PASS -- loop_status derive ce qu'il rend, et se tait quand il le doit.")
    return len(ECHECS)


if __name__ == "__main__":
    sys.exit(main())
