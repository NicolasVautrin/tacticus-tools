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

CE QUE CETTE GARDE EST SEULE A VOIR : il n'existe aucun autre chemin vers ces trois-la.
`probe_273` garde les entrees GITIGNOREES lues depuis la racine, pas les sorties d'un outil ;
`probe_457` ne joue que `scripts/python/tests`, ou `loop_status` n'a aucun test. Tout le reste du
depot garde du CODE, dont la degradation produit un rouge -- alors que celle-ci ne produit rien.

COMMENT IL S'Y PREND. Toutes les entrees de `loop_status` passent par la facade `Sources`, qui est
SUBSTITUEE ici. Sans cette couture, garder le tri-etat exigerait d'eteindre le host, ce qu'aucune
garde ne peut faire -- et une garde qui depend de l'etat de la machine n'en est pas une.
Aucun appel reel a git, `gh` ou au host : ce probe est 100 % offline et deterministe.

Il ECRIT dans un tmpdir SYSTEME (`mkdtemp()` sans `dir=`), jamais sous `scripts/python/`, que
d'autres passes peuvent enumerer en parallele (#455).

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
                 prs: list | None = None, gh_ko: str | None = None,
                 http: dict | None = None, http_ko: str | None = None,
                 rows: list | None = None) -> None:
        super().__init__(repo=Path("/faux"), ttl_cache=0.0)
        self._status_v2, self._worktrees, self._mergees = status_v2, worktrees, mergees
        self._prs, self._gh_ko = prs, gh_ko
        self._http, self._http_ko = http or {}, http_ko
        self._rows = rows or []

    def git(self, *args: str) -> tuple[int, str]:
        if args[:1] == ("status",):
            return 0, self._status_v2
        if args[:2] == ("worktree", "list"):
            return 0, self._worktrees
        if args[:2] == ("for-each-ref", "--merged"):
            return 0, self._mergees
        if args[:1] == ("rev-list",):
            return 0, "0\n"
        raise AssertionError("git non scripte : %r" % (args,))

    def gh(self, *args: str) -> tuple[int, str, str]:
        # 3-uplet : `gh` rend AUSSI son stderr, seul texte qui nomme ses pannes (#467-r6).
        if self._gh_ko:
            raise RuntimeError(self._gh_ko)
        return 0, json.dumps(self._prs or []), ""

    def http_json(self, chemin: str) -> dict:
        if self._http_ko:
            raise RuntimeError(self._http_ko)
        return self._http.get(chemin, {})

    def flotte(self) -> list[dict]:
        return self._rows

    def lire_cache_gh(self):
        return None

    def ecrire_cache_gh(self, prs) -> None:
        pass


def _agent(nom: str, wt: str = "", depth: int = 1, parent: str = "") -> dict:
    #: `depth` 1 = tranche DISPATCHEE (compte au plafond) ; >= 2 = sous-agent lance par un
    #: solveur (n'y compte PAS). Le champ vient du meta ecrit par le harnais.
    return {"name": nom, "wt": wt, "state": "vif", "depth": depth, "parent": parent}


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


# =====================================================================================
#  1. TRI-ETAT -- un zero ne remplace JAMAIS un << pas mesure >>
# =====================================================================================
def etape_1_tri_etat() -> None:
    print("\n[1] TRI-ETAT : host eteint, `gh` hors ligne")
    src = FauxSources(status_v2=_statut_v2(), worktrees="", mergees="",
                      gh_ko="gh absent du PATH", http_ko="connexion refusee",
                      rows=[])
    e = LS.etat(src, 5)
    ha, lv = e["harnais"], e["livraison"]

    for cle in ("session", "drain", "live_runners"):
        m = ha[cle]
        verifie(not m.mesuree and m.valeur is None,
                "harnais.%s = PAS MESURE (et pas un zero)" % cle)
    verifie(not lv["pr_ouvertes"].mesuree,
            "livraison.pr_ouvertes = PAS MESURE quand `gh` ne repond pas")

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
                       rows=[])
    e2 = LS.etat(src2, 5)
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
        repos = FauxSources(
            status_v2=_statut_v2(avance=0), worktrees="", mergees="", prs=[],
            http={"/api/admin/status": {"session": {"id": 1, "status": "running", "pid": 9},
                                        "tacticus": {"running": True}},
                  "/api/admin/drain": {"enabled": False, "liveRunners": 0,
                                       "liveRunnersSource": "hooks"}},
            rows=[])
        sig, _ = LS.signaux(LS.etat(repos, 5))
        verifie(sig == [], "depot au REPOS (0 agent, 0 worktree, 0 PR, 0 commit) -> AUCUN signal")

        # Le meme etat, mais la campagne est en cours : les slots libres doivent se voir.
        actif = FauxSources(
            status_v2=_statut_v2(avance=0),
            worktrees=_wt_porcelain([(r"C:/r/.claude/worktrees/agent-1", "worktree-agent-1")]),
            mergees="", prs=[],
            http=repos._http, rows=[_agent("un", r"C:/r/.claude/worktrees/agent-1")],
            )
        cles = {s.cle for s in LS.signaux(LS.etat(actif, 5))[0]}
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
        s = FauxSources(status_v2=_statut_v2(avance=30, suivis=("engine/x.py",)),
                        worktrees=wts, mergees="worktree-agent-1\nworktree-agent-2\n",
                        prs=[], http=base_http,
                        rows=[_agent("solo", r"C:/r/.claude/worktrees/agent-9")])
        e = LS.etat(s, 5)
        cles = {x.cle for x in LS.signaux(e)[0]}
        for attendu in ("slots", "push", "sale", "nettoyage"):
            verifie(attendu in cles, "signal `%s` emis (%s)" % (attendu, sorted(cles)))
        verifie(len(e["livraison"]["nettoyables"].valeur) == 2,
                "les 2 worktrees d'agents livres sont proposes au nettoyage")

        # -- un agent EN VOL sur une branche deja mergee n'est JAMAIS propose au nettoyage
        s2 = FauxSources(status_v2=_statut_v2(), worktrees=wts,
                         mergees="worktree-agent-1\nworktree-agent-2\n", prs=[], http=base_http,
                         rows=[_agent("occupe", r"C:/r/.claude/worktrees/agent-1")])
        nett = LS.etat(s2, 5)["livraison"]["nettoyables"].valeur
        verifie([w["branche"] for w in nett] == ["worktree-agent-2"],
                "le worktree d'un agent EN VOL est retire des nettoyables (%s)"
                % [w["branche"] for w in nett])

        # -- drain arme, et session absente : deux pannes de harnais, deux signaux
        s3 = FauxSources(status_v2=_statut_v2(), worktrees="", mergees="", prs=[],
                         http={"/api/admin/status": {"session": None,
                                                     "tacticus": {"running": False}},
                               "/api/admin/drain": {"enabled": True, "liveRunners": 0,
                                                    "liveRunnersSource": "hooks"}},
                         rows=[])
        cles3 = {x.cle for x in LS.signaux(LS.etat(s3, 5))[0]}
        verifie("drain" in cles3, "mode DRAIN arme -> signal")
        verifie("session" in cles3, "aucune session Frida -> signal")

        # -- runners vivants sans aucun agent en vol : des orphelins
        s4 = FauxSources(status_v2=_statut_v2(), worktrees="", mergees="", prs=[],
                         http={"/api/admin/status": {"session": {"id": 1, "status": "running"},
                                                     "tacticus": {"running": True}},
                               "/api/admin/drain": {"enabled": False, "liveRunners": 3,
                                                    "liveRunnersSource": "hooks"}},
                         rows=[])
        verifie("orphelins" in {x.cle for x in LS.signaux(LS.etat(s4, 5))[0]},
                "3 runners vivants et 0 agent en vol -> signal orphelins")
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
                      rows=[_agent("a"), _agent("b")])
    for plafond, attendu in ((5, 3), (2, 0), (8, 6)):
        fl = LS.etat(src, plafond)["flotte"]
        verifie(fl["en_vol"].valeur == 2 and fl["libres"].valeur == attendu,
                "plafond %d -> %d libre(s) pour 2 en vol" % (plafond, attendu))
    # Le nombre EN VOL ne peut pas etre une saisie : il vient de la flotte.
    fl = LS.etat(FauxSources(status_v2=_statut_v2(), rows=[]), 5)["flotte"]
    verifie(fl["en_vol"].valeur == 0 and fl["libres"].valeur == 5,
            "flotte vide -> 0 en vol, 5 libres")


# =====================================================================================
#  8. LE PLAFOND PORTE SUR LES TRANCHES, PAS SUR LES AGENTS VIVANTS (#467-r7)
# =====================================================================================
def etape_8_sous_agents() -> None:
    """Un sous-agent lance par un solveur ne consomme PAS un slot de dispatch.

    MESURE QUI L'A IMPOSE (2026-08-06) : la flotte affichait `6 / 6` -- donc « plafond atteint,
    0 slot libre » -- pour **5** tranches reellement dispatchees. Le sixieme etait un sous-agent
    (`spawnDepth = 2`, `parentAgentId` renseigne) lance par le solveur de `#419-r5`, a qui le
    brief demandait EXPLICITEMENT ce recensement. Un slot etait donc retenu sans raison, et
    l'orchestrateur s'est interdit un dispatch qui etait libre.

    ⚠ LE DISCRIMINANT EST LA PROFONDEUR, PAS L'ABSENCE DE WORKTREE. Un agent de TETE lance sans
    `isolation: worktree` n'a pas de worktree non plus ; le compter comme un enfant rendrait le
    plafond faux dans l'autre sens -- et silencieusement, puisque personne ne verifie a la main.
    C'est la meme faute que le `git worktree lock` du fleet-board, aveugle des la 1re reprise.

    ⚠ ET LE FILTRE DOIT SE DIRE. Un compte filtre qui ne publie pas ce qu'il ecarte fait diverger
    la sortie de ce que l'utilisateur voit dans son interface, sans rien pour l'expliquer.
    """
    print("\n[8] Les SOUS-AGENTS ne consomment pas de slot, et sont PUBLIES (#467-r7)")
    base = dict(status_v2=_statut_v2(), worktrees="", mergees="", prs=[],
                http={"/api/admin/status": {"session": {"id": 1, "status": "running"},
                                            "tacticus": {"running": True}},
                      "/api/admin/drain": {"enabled": False, "liveRunners": 0,
                                           "liveRunnersSource": "hooks"}})

    # la scene MESUREE : 5 tranches + 1 sous-agent, plafond 6 -> 5 en vol, 1 LIBRE
    rows = [_agent("tranche-%d" % i) for i in range(5)]
    rows.append(_agent("sous-agent", depth=2, parent="a08344cf9ecf7510f"))
    fl = LS.etat(FauxSources(rows=rows, **base), 6)["flotte"]
    verifie(fl["en_vol"].valeur == 5, "5 tranches + 1 sous-agent -> en vol = 5 (et non 6)")
    verifie(fl["libres"].valeur == 1, "le slot du sous-agent reste LIBRE")
    verifie("sous-agent" not in fl["noms"].valeur, "le sous-agent n'est pas dans les tranches")
    verifie(fl["enfants"].mesuree and fl["enfants"].valeur == ["sous-agent"],
            "le sous-agent est PUBLIE a part, jamais tu")

    # CONTRE-EPREUVE : sans le cran, ces memes donnees rendaient 6/6. Le mutant est la scene
    # elle-meme -- si le filtre disparait, la 1re assertion tombe. On verifie ici que le cran
    # a bien un DOMAINE : sans sous-agent, rien ne doit changer.
    fl2 = LS.etat(FauxSources(rows=[_agent("t%d" % i) for i in range(5)], **base), 6)["flotte"]
    verifie(fl2["en_vol"].valeur == 5 and fl2["libres"].valeur == 1,
            "sans sous-agent : 5 tranches -> 5 en vol, 1 libre (le cran est INERTE, et c'est bon)")
    verifie(not fl2["enfants"].valeur, "aucun enfant a publier quand il n'y en a pas")

    # profondeur ABSENTE (meta d'un vieil agent, ou harnais qui ne l'ecrit pas) -> compte comme
    # une TRANCHE. Le defaut prudent est de RETENIR un slot, pas d'en liberer un a tort.
    vieux = {"name": "sans-profondeur", "wt": "", "state": "vif"}
    fl3 = LS.etat(FauxSources(rows=[vieux], **base), 6)["flotte"]
    verifie(fl3["en_vol"].valeur == 1,
            "profondeur ABSENTE -> compte comme une tranche (defaut prudent)")


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

    def gh(self, *args: str) -> tuple[int, str, str]:
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
        txt = LS.rendu_complet(LS.etat(s, 5), *LS.signaux(LS.etat(s, 5)))
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
        s_ok.gh = lambda *a: (0, json.dumps(ouverte), "")        # type: ignore[assignment]
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
        def __init__(self, rc, out="", err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

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

        # Un rc NON NUL de `gh` doit remonter SON code ET SON NOM. Le repo est un tmpdir
        # VIERGE, et ce n'est pas un detail : sur un vrai checkout, `logs/loop-status-gh.json`
        # existe, le repli s'enclenche et l'epreuve devient verte sans rien avoir juge --
        # constate en jouant la contre-epreuve.
        #
        # LES TROIS CAS SONT MESURES sur l'exe installe (gh 2.88.1, 2026-08-05), pas supposes,
        # et c'est la mesure qui dicte la forme du garde : `rc=1` couvre A LUI SEUL le token
        # invalide, le depot inconnu et l'erreur d'usage. Le rc ne peut donc PAS nommer la
        # panne -- seul le stderr le fait, et c'est lui que le lecteur jetait.
        vierge = Path(tempfile.mkdtemp(prefix="probe467-rc-"))
        cas_rc = [
            (4, "To get started with GitHub CLI, please run:  gh auth login",
             ("non authentifie", "rc=4"),
             "un `gh` NON AUTHENTIFIE se nomme (rc=4 mesure), pas un code nu"),
            (1, "HTTP 401: Bad credentials (https://api.github.com/graphql)",
             ("rc=1", "Bad credentials"),
             "un TOKEN INVALIDE porte le diagnostic de `gh` (rc=1, indiscernable sans stderr)"),
            (1, "GraphQL: Could not resolve to a Repository with the name 'x/y'.",
             ("rc=1", "Could not resolve"),
             "un DEPOT INCONNU se distingue du token invalide -- meme rc=1, stderr different"),
        ]
        try:
            for rc, err, attendus, quoi in cas_rc:
                LS.subprocess.run = (                        # type: ignore[assignment]
                    lambda *a, _rc=rc, _e=err, **k: _Fini(_rc, "", _e))
                m, _, _, _, _ = LS._gh_prs(LS.Sources(repo=vierge, ttl_cache=0.0))
                msg = m.erreur or ""
                verifie(not m.mesuree and all(x in msg for x in attendus)
                        and "rc=127" not in msg, "%s (%r)" % (quoi, msg))

            # rc=0 A SORTIE VIDE : le zero le plus facile a fabriquer, et il n'a besoin
            # d'AUCUNE panne. `json.loads(out or "[]")` en faisait une liste vide, donc un
            # << PR ouvertes : 0 >> RENDU COMME UNE MESURE.
            LS.subprocess.run = lambda *a, **k: _Fini(0, "", "")   # type: ignore[assignment]
            m, _, _, _, _ = LS._gh_prs(LS.Sources(repo=vierge, ttl_cache=0.0))
            verifie(not m.mesuree and "VIDE" in (m.erreur or ""),
                    "rc=0 + sortie VIDE -> PAS MESURE, jamais << 0 PR >> (%r)" % m.erreur)

            LS.subprocess.run = (                                  # type: ignore[assignment]
                lambda *a, **k: _Fini(0, "{ tronque", ""))
            m, _, _, _, _ = LS._gh_prs(LS.Sources(repo=vierge, ttl_cache=0.0))
            verifie(not m.mesuree and "ILLISIBLE" in (m.erreur or ""),
                    "rc=0 + sortie TRONQUEE -> PAS MESURE (%r)" % m.erreur)

            # CONTRE-EPREUVE des quatre precedentes : une VRAIE liste vide reste une MESURE a
            # zero. Sans elle, un lecteur qui rendrait TOUJOURS PAS MESURE les passerait toutes.
            LS.subprocess.run = lambda *a, **k: _Fini(0, "[]", "")  # type: ignore[assignment]
            m, _, _, _, _ = LS._gh_prs(LS.Sources(repo=vierge, ttl_cache=0.0))
            verifie(m.mesuree and m.valeur == [],
                    "contre-epreuve : `[]` rendu par `gh` reste un ZERO MESURE")
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
        # ... et l'ABSENCE aussi a deux causes. Annoncer << PATH + emplacements connus >> quand
        # une echappatoire explicite pointe sur un chemin mort accuse le mauvais coupable : le
        # PATH n'a jamais ete consulte. C'est la faute de #467-r6 en miniature.
        try:
            LS.Sources(repo=LS.REPO).gh("pr", "list")
            msg = "(aucune levee)"
        except RuntimeError as e:
            msg = str(e)
        verifie("TACTICUS_GH_EXE" in msg,
                "gh introuvable VIA l'echappatoire le DIT, au lieu d'accuser le PATH (%r)" % msg)
    finally:
        if vrai is None:
            os.environ.pop("TACTICUS_GH_EXE", None)
        else:
            os.environ["TACTICUS_GH_EXE"] = vrai

    # -- LE BUDGET EST UN PARAMETRE, jusque dans le hook. Le wrapper `loop-status.ps1` ne passe
    #    QUE `--hook` : sans variable d'environnement, un budget ne se regle qu'en EDITANT le
    #    fichier -- c'est-a-dire qu'il redevient une constante magique, ce que #467-r6 reproche.
    vus2: dict = {}

    class Espion2(LS.Sources):
        def __init__(self, **kw):
            vus2.update(kw)
            super().__init__(**kw)

    anciens = {c: os.environ.get(c) for c in ("TACTICUS_LOOP_GH_TIMEOUT", "TACTICUS_LOOP_TIMEOUT")}
    LS.Sources = Espion2                                         # type: ignore[misc]
    vrai_stdin2 = sys.stdin
    sys.stdin = io.StringIO("")
    try:
        os.environ["TACTICUS_LOOP_GH_TIMEOUT"] = "17.5"
        os.environ["TACTICUS_LOOP_TIMEOUT"] = "6.25"
        LS.main(["--hook", "--repo", str(LS.REPO), "--no-gh", "--no-host"])
        verifie(vus2.get("timeout_gh") == 17.5 and vus2.get("timeout") == 6.25,
                "les deux budgets se surchargent par l'ENV (gh=%s, general=%s)"
                % (vus2.get("timeout_gh"), vus2.get("timeout")))
        # Une surcharge ILLISIBLE ne casse pas le tour : elle retombe sur le defaut mesure.
        vus2.clear()
        os.environ["TACTICUS_LOOP_GH_TIMEOUT"] = "pas-un-nombre"
        LS.main(["--hook", "--repo", str(LS.REPO), "--no-gh", "--no-host"])
        verifie(vus2.get("timeout_gh") == 10.0,
                "une surcharge illisible retombe sur le defaut (%s)" % vus2.get("timeout_gh"))
    finally:
        sys.stdin = vrai_stdin2
        LS.Sources = vrai_sources                                # type: ignore[misc]
        for c, v in anciens.items():
            if v is None:
                os.environ.pop(c, None)
            else:
                os.environ[c] = v

    # -- L'AUTRE CAPTEUR : git. `RC_MUET` y couvre encore le delai depasse ET l'erreur systeme,
    #    et c'est LUI qui court sous le budget serre du hook (3 s ; `git status` a deja ete
    #    mesure a 4,29 s sous charge). Rendre `rc=127` pour les deux, c'est le vice de #467-r6
    #    sur l'autre capteur. Exerce sur le VRAI `Sources._run`, jamais sur `git()` substitue.
    cas_git = [
        (_leve(LS.subprocess.TimeoutExpired("git", 3.0)), "delai depasse",
         "un `git status` qui DEPASSE SON BUDGET le dit (le poste le plus expose du hook)"),
        (_leve(OSError("git absent")), "OSError",
         "une panne systeme de git porte son type, pas la sentinelle 127"),
    ]
    try:
        for faux_run, attendu, quoi in cas_git:
            LS.subprocess.run = faux_run                         # type: ignore[assignment]
            s_git = LS.Sources(repo=LS.REPO, avec_gh=False, avec_host=False, ttl_cache=0.0)
            lv = LS.mesurer_livraison(s_git)
            msg = lv["branche"].erreur or ""
            verifie(not lv["branche"].mesuree and attendu in msg and "rc=127" not in msg,
                    "%s (%r)" % (quoi, msg))
        # CONTRE-EPREUVE : un rc REEL de git reste rendu comme un rc. Sans elle, un lecteur qui
        # nommerait TOUT << delai depasse >> passerait les deux epreuves ci-dessus.
        LS.subprocess.run = lambda *a, **k: _Fini(3)             # type: ignore[assignment]
        s_git = LS.Sources(repo=LS.REPO, avec_gh=False, avec_host=False, ttl_cache=0.0)
        lv = LS.mesurer_livraison(s_git)
        verifie((lv["branche"].erreur or "") == "rc=3",
                "contre-epreuve : un rc REEL de git reste `rc=<n>` (%r)" % lv["branche"].erreur)
    finally:
        LS.subprocess.run = vrai_run                             # type: ignore[assignment]

    # -- ET LA PANNE DOIT SE LIRE. Nommer la cause ne sert a rien si l'axe entier devient muet :
    #    un `git status` en echec emportait `push`, `sale` et `nettoyage` D'UN BLOC, sans un
    #    mot, exactement la signature << capteur mort = rien a signaler >>.
    s_ko = FauxSources(status_v2=_statut_v2(), worktrees="", mergees="", rows=[])
    s_ko.git = lambda *a: (LS.Sources.RC_MUET, "")               # type: ignore[assignment]
    cles = {x.cle for x in LS.signaux(LS.etat(s_ko, 5))[0]}
    verifie("livraison-inconnue" in cles,
            "un axe LIVRAISON non mesure est SIGNALE, pas avale en silence (%s)" % sorted(cles))
    # CONTRE-EPREUVE : sur un axe qui REPOND, ce signal n'existe pas -- sinon il hurlerait a
    # chaque tour et se ferait desarmer, ce qui reviendrait au meme silence.
    s_ok2 = FauxSources(status_v2=_statut_v2(), worktrees="", mergees="", rows=[])
    cles_ok = {x.cle for x in LS.signaux(LS.etat(s_ok2, 5))[0]}
    verifie("livraison-inconnue" not in cles_ok,
            "contre-epreuve : aucun signal de ce type quand la livraison est MESUREE (%s)"
            % sorted(cles_ok))


def _age_gh_de(lv: dict) -> str:
    return LS._age_gh(lv)


# =====================================================================================
#  Point d'entree
# =====================================================================================
def main() -> int:
    print("probe_467 -- fidelite de loop_status (100 % offline, sources substituees)")
    for etape in (etape_1_tri_etat, etape_2_raccourci_flotte, etape_3_silence,
                  etape_4_parole, etape_6_plafond, etape_7_gh_muet, etape_8_sous_agents):
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
