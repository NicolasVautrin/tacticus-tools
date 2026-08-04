"""loop_status -- l'etat de la BOUCLE d'orchestration, DERIVE, jamais declare.

    python scripts/python/loop_status.py            # etat complet, ASCII
    python scripts/python/loop_status.py --json     # meme etat, machine
    python scripts/python/loop_status.py --hook     # lit le JSON du hook Stop sur stdin

POURQUOI CE FICHIER EXISTE (#467). Le depot porte 37 cliquets qui gardent le CODE et AUCUN qui
garde la BOUCLE. L'angle mort est structurel : une erreur de code produit un ROUGE, une erreur de
boucle ne produit RIEN -- un slot d'agent vide n'echoue pas, il COUTE. Mesure du 2026-08-04 : un
tour termine a 1 agent sur un plafond de 5 apres que quatre solveurs avaient rendu, avec 30 commits
d'avance non pousses et 4 worktrees livres non nettoyes. Rien ne l'a signale.

CE QUE CET OUTIL N'EST PAS : un tableau de bord. Il se TAIT quand il n'y a rien a faire. Sa valeur
est dans le DECLENCHEMENT automatique (hook `Stop`) et dans le fait que chaque chiffre soit
DERIVE d'une source nommee -- jamais d'une saisie, jamais d'un souvenir.

TRI-ETAT, partout ou la mesure peut ne pas avoir lieu (lecon de `host_inputs.py`, #273) :

    valeur  = mesure                (un nombre, une liste)
    None    = PAS MESURE            (host eteint, `gh` absent, RPC en echec)

`None` ne se rend JAMAIS comme un zero. « je n'ai pas pu compter » et « il n'y a rien » sont deux
etats differents, et les confondre est exactement ce qui fait qu'un capteur mort se lit comme
« rien a signaler ».

MEME REGLE SUR L'AXE DU TEMPS -- A QUOI un verdict de banque s'applique (#472). Un chiffre juste
sur un commit qui n'est plus la pointe est un chiffre FAUX sur la pointe. MESURE le 2026-08-04,
trois tours consecutifs : le hook a repete `verdict de banque afb3e209 rc=1 [ROUGE (1)]` alors que
`HEAD` valait successivement `4b62a914` puis `c94efb11`, aucun verdict n'existant pour ceux-la --
et le rouge d'`afb3e209` etait DEJA corrige par un commit plus recent que lui. Re-mesure a la
reprise du dossier : dernier verdict `6979f712`, pointe `5efc6a69`, **48 commits d'ecart**, rendus
comme l'etat courant. Trois tours d'alarme sur un fait perime -- et le jour ou la pointe sera
VRAIMENT rouge, cette ligne aura EXACTEMENT la meme apparence.

La ventilation est donc a TROIS etats, comme partout ailleurs ici :

    JUGEE      -- un verdict porte SUR la pointe : il est rendu tel quel, vert ou rouge ;
    EN COURS   -- aucun verdict pour la pointe, mais un run VIVANT la juge (fait, cf. `_runs_vivants`) ;
    NON JUGEE  -- aucun verdict pour la pointe, et rien n'indique qu'un run la juge.

et, orthogonale, la FRAICHEUR du verdict retenu (`pointe` / `ancetre` / `hors-lignee` /
`inconnue`). Un verdict PERIME reste AFFICHE -- c'est une information utile (« la banque a juge,
mais pas ceci ») -- il change seulement d'ACCUSE : il passe des SIGNAUX au CONTEXTE. Il n'est
rabattu ni sur un vert ni sur un rouge.

LA SEULE VALEUR ASSUMEE est le PLAFOND de dispatch : c'est un PARAMETRE d'orchestration, pas une
mesure. Il porte sa source en commentaire et s'ecrase par `--max-agents` / TACTICUS_DISPATCH_CAP.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# `urllib.request` (137 ms), `concurrent.futures` (50 ms) et `shutil` sont importes
# PARESSEUSEMENT. Ce module est le point d'entree d'un hook `Stop` GLOBAL : il demarre a
# CHAQUE fin de tour de CHAQUE projet de la machine, y compris ceux ou il n'a rien a dire et
# ou il sort avant d'avoir ouvert la moindre socket. Les payer a l'import, c'est les facturer
# aux autres projets.

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fleet_board                                                     # noqa: E402
import host_inputs                                                     # noqa: E402

REPO = Path(__file__).resolve().parents[2]

# PARAMETRE, pas mesure. Source : la conduite de campagne (« Profondeur de dispatch : 5 agents »,
# elle-meme bornee par le partage du pump Frida). Rien dans le depot ne le DERIVE -- l'ecrire ici
# le rend au moins visible et surchargeable, au lieu de vivre dans la tete de l'orchestrateur.
PLAFOND_DISPATCH = 5

# Le host tourne en local ; le littéral est celui de tous les probes du depot.
HOST_DEFAUT = "http://127.0.0.1:8765"

# Non-suivis ATTENDUS a la racine de l'arbre principal. Ils ne comptent pas comme « arbre sale ».
# Liste ASSUMEE et AFFICHEE (le rapport dit combien elle en a ecartes) : un filtre muet
# transformerait un vrai residu en silence.
UNTRACKED_CONNUS = (
    ".agent-alive",              # marqueur de vie d'un worktree d'agent (jamais versionne)
    "hs_err_pid",                # crash dumps JVM (ghidra headless)
    "frida/hooks/scratch/",      # modules de travail hors bundle
    "logs/",                     # sorties de run
)

_VERDICTS_REL = "logs/ratchets-bg"


# ------------------------------------------------------------------ tri-etat
@dataclass(frozen=True)
class Mesure:
    """`erreur is None` => MESURE. Sinon PAS MESURE, et `valeur` vaut None."""

    valeur: object | None
    source: str
    erreur: str | None = None

    @property
    def mesuree(self) -> bool:
        return self.erreur is None

    def txt(self, fmt: str = "%s") -> str:
        return (fmt % (self.valeur,)) if self.mesuree else "? (%s)" % self.erreur


def _ok(valeur, source: str) -> Mesure:
    return Mesure(valeur=valeur, source=source, erreur=None)


def _ko(source: str, erreur: str) -> Mesure:
    return Mesure(valeur=None, source=source, erreur=erreur)


# ------------------------------------------------------------------ sources
class Sources:
    """Toutes les entrees, derriere une facade INJECTABLE.

    Le cliquet de fidelite (`probe_467`) substitue cette classe pour jouer des etats que la
    machine ne presente pas a la demande -- host eteint, `gh` absent, verdict rouge. Sans cette
    couture, garder le tri-etat exigerait d'eteindre le host, ce qu'aucun cliquet ne peut faire.
    """

    # Le REPLI ne sert la derniere mesure que si elle est plus jeune que ceci. Au-dela,
    # PAS MESURE : une PR relue et mergee il y a une heure n'a plus rien a dire.
    AGE_MAX_REPLI = 1800.0

    def __init__(self, repo: Path = REPO, host: str = HOST_DEFAUT,
                 timeout: float = 8.0, avec_gh: bool = True, avec_host: bool = True,
                 ttl_cache: float = 90.0, timeout_gh: float | None = None) -> None:
        self.repo = repo
        self.host = host
        self.timeout = timeout
        self.avec_gh = avec_gh
        self.avec_host = avec_host
        self.ttl_cache = ttl_cache
        # Budget PROPRE de `gh`. Ce n'est PAS le plancher `max(self.timeout, 12.0)` qui
        # avait ete retire : c'est un parametre distinct, donc un reglage explicite a la
        # baisse reste honore. La politique de defaut vit dans `main`.
        self.timeout_gh = timeout if timeout_gh is None else timeout_gh

    # -- processus
    #    RC_MUET : le process n'a pas repondu (timeout, binaire absent). Ce n'est PAS un
    #    verdict -- chaque appelant le traite comme « pas mesure », jamais comme un zero.
    RC_MUET = 127

    def _run(self, argv: list[str], timeout: float | None = None) -> tuple[int, str]:
        """Ne LEVE jamais. Un outil de fin de tour qui plante casse le tour."""
        try:
            p = subprocess.run(argv, cwd=str(self.repo), capture_output=True, text=True,
                               timeout=timeout or self.timeout, encoding="utf-8",
                               errors="replace")
        except (OSError, subprocess.SubprocessError):
            return self.RC_MUET, ""
        return p.returncode, (p.stdout or "")

    def git(self, *args: str) -> tuple[int, str]:
        """`--no-optional-locks` est pose au FOYER, jamais au site d'appel (#474).

        Ce lecteur vise l'ARBRE PRINCIPAL, depuis le hook `Stop`, sous un budget de 3 s --
        et `subprocess.run(timeout=)` TUE par `TerminateProcess` au depassement. Or
        `git status` tient `.git/index.lock` a **0 octet pendant ~toute sa duree** (1,2 s
        sur cet arbre) : un git tue dans cette fenetre laisse un lock ORPHELIN que plus
        aucun process ne tient, et c'est le `git merge` SUIVANT de l'arbre principal qui
        meurt dessus. On supprime la FENETRE, on ne court pas apres le residu.

        Mesure sur depot jetable (#474) : kill pendant la fenetre = **15/15** residus sans
        l'option, **0/15** avec, et la sortie de `status --porcelain` est IDENTIQUE.

        Au foyer parce qu'un `src.git("status", ...)` ajoute demain serait couvert d'office
        -- meme raison que le foyer `_git` de `probe_457`. Sans effet sur les commandes qui
        ne prennent pas de lock optionnel (mesure : seuls `status` et `describe --dirty`
        en prennent un ; `diff`, `ls-files`, `rev-parse`, `worktree list` n'en prennent pas).
        """
        return self._run(["git", "-C", str(self.repo), "--no-optional-locks", *args])

    # Emplacements d'installation connus de `gh` sous Windows, essayes APRES le PATH.
    _GH_CONNUS = (
        r"%ProgramFiles%\GitHub CLI\gh.exe",
        r"%ProgramFiles(x86)%\GitHub CLI\gh.exe",
        r"%LOCALAPPDATA%\Programs\GitHub CLI\gh.exe",
        r"%LOCALAPPDATA%\Microsoft\WinGet\Links\gh.exe",
    )

    def exe_gh(self) -> str | None:
        """`gh` par CHEMIN ABSOLU -- comme `loop-status.ps1` resout `$repo` et son script.

        `TACTICUS_GH_EXE` d'abord (echappatoire explicite, meme patron que
        `TACTICUS_HOST_DATA_ROOT`), puis le PATH, puis les emplacements connus.

        Le PATH n'etait PAS la cause de #467-r6 -- MESURE le 2026-08-04, il est IDENTIQUE
        (39 entrees, `GitHub CLI` present) sous `pwsh` et sous le `powershell.exe
        -NoProfile` qui execute reellement le hook. C'est une cause ELIMINABLE a cout nul,
        pas la cause constatee ; celle-la etait le BUDGET (cf. `gh`).
        """
        import shutil
        force = os.environ.get("TACTICUS_GH_EXE")
        if force:
            return force if Path(force).exists() else None
        trouve = shutil.which("gh")
        if trouve:
            return trouve
        for motif in self._GH_CONNUS:
            p = os.path.expandvars(motif)
            if "%" not in p and Path(p).exists():        # `%VAR%` non resolu => on passe
                return p
        return None

    def gh(self, *args: str) -> tuple[int, str]:
        """Le SEUL poste RESEAU. Sa panne est NOMMEE, jamais reduite a un `rc=127`.

        Son budget est le SIEN (`timeout_gh`), pas le budget general : le plancher
        `max(self.timeout, 12.0)` reste proscrit (il ANNULAIT tout reglage a la baisse),
        mais un parametre distinct, lui, se regle dans les deux sens.

        POURQUOI (#467-r6), et c'est MESURE le 2026-08-04, pas suppose. Sous le
        `powershell.exe -NoProfile` qui execute le hook, `gh pr list` seul met **2,90 s**
        pour un budget de **3,00 s** ; dans le tour COMPLET, ou il court avec `git status`,
        la flotte et la banque, **5 tours sur 8** depassaient -- exactement la ligne PR
        aveugle rapportee. Au repos, 20 tirages : mediane 1,60 s, max 1,99 s, **0** au-dessus
        de 3 s. C'est donc bien la CONCURRENCE qui fait franchir la borne, et un budget
        propre est le correctif de la cause.

        LES TROIS PANNES RENDAIENT LE MEME `rc=127` (la sentinelle `RC_MUET`) : binaire
        absent, delai depasse, `OSError`. Un incident devenait indiagnosticable -- c'est ce
        qui a fait lire << gh absent du PATH >> un DEPASSEMENT DE DELAI. Chaque cause porte
        desormais son nom, sinon le prochain incident se rediagnostiquera aussi mal.
        """
        if not self.avec_gh:
            raise RuntimeError("gh desactive")
        exe = self.exe_gh()
        if exe is None:
            raise RuntimeError("gh introuvable (PATH + emplacements connus)")
        try:
            p = subprocess.run([exe, *args], cwd=str(self.repo), capture_output=True,
                               text=True, timeout=self.timeout_gh, encoding="utf-8",
                               errors="replace")
        except subprocess.TimeoutExpired:
            raise RuntimeError("gh: delai depasse (%.0f s)" % self.timeout_gh) from None
        except (OSError, subprocess.SubprocessError) as ex:
            raise RuntimeError("gh: %s" % type(ex).__name__) from None
        return p.returncode, (p.stdout or "")

    # -- http
    def http_json(self, chemin: str) -> dict:
        import urllib.request
        if not self.avec_host:
            raise RuntimeError("host desactive")
        url = self.host.rstrip("/") + chemin
        with urllib.request.urlopen(url, timeout=min(self.timeout, 5.0)) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    # -- cache GitHub. Le SEUL poste reseau de l'outil, et le plus cher (1,35 s). Le cacher
    #    quelques dizaines de secondes rend le hook quasi gratuit sur des tours rapprochés.
    #    Ce n'est PAS une valeur declaree : c'est une mesure HORODATEE, et son age est RENDU a
    #    cote des chiffres qui en derivent (un cache muet, lui, serait une valeur inventee).
    def _cache_gh(self) -> Path:
        return self.repo / "logs" / "loop-status-gh.json"

    def _lire_cache_brut(self) -> tuple[list, float] | None:
        """(prs, age en s) du dernier `gh` REUSSI, sans borne d'age. None = pas de cache."""
        p = self._cache_gh()
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            age = self.maintenant() - float(d["quand"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return (d["prs"], age) if age >= 0 else None

    def lire_cache_gh(self) -> tuple[list, float] | None:
        brut = self._lire_cache_brut() if self.ttl_cache > 0 else None
        return brut if brut is not None and brut[1] < self.ttl_cache else None

    def lire_cache_gh_repli(self) -> tuple[list, float] | None:
        """Le cache PERIME, servi UNIQUEMENT quand `gh` vient d'echouer.

        Il ne remplace pas le tri-etat, il l'ALIMENTE : servi, l'etat reste une MESURE --
        horodatee, et son age est RENDU a cote du chiffre. Non servi, on retombe sur
        PAS MESURE. Ce qui n'arrive jamais, c'est un zero fabrique.

        L'ASYMETRIE est la propriete qui compte, et elle est deliberee : l'appelant ne
        retient ce repli QUE s'il porte au moins une PR ouverte. Un cache disant << 0 PR >>
        ne peut RIEN prouver quand `gh` est muet -- une PR ouverte il y a deux minutes y
        serait absente, et l'outil se tairait en ayant l'air d'avoir mesure. Le repli peut
        donc SIGNALER, jamais RASSURER : son faux positif (une PR mergee entre-temps) coute
        un rappel de trop, son faux negatif couterait l'oubli que ce hook existe pour eviter.
        """
        brut = self._lire_cache_brut()
        return brut if brut is not None and brut[1] < self.AGE_MAX_REPLI else None

    def ecrire_cache_gh(self, prs: list) -> None:
        p = self._cache_gh()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"quand": self.maintenant(), "prs": prs}),
                         encoding="utf-8")
        except OSError:
            pass

    # -- flotte
    def flotte(self) -> list[dict]:
        """Agents qui TRAVAILLENT. `only_alive` : cf. la preuve dans `fleet_board`."""
        return fleet_board.collect(include_done=False, only_alive=True)

    # -- verdicts de banque
    def dossier_verdicts(self) -> Path | None:
        """`logs/ratchets-bg` -- l'arbre JUGE d'abord, `host_inputs` en repli. None = PAS MESURE.

        L'ordre compte, et il a ete pris a l'envers : `host_inputs.resolve` part de SA propre
        racine (`parents[2]` de son fichier), pas de l'arbre qu'on nous a demande de juger. Un
        `--repo` explicite lisait donc les verdicts d'un AUTRE arbre -- trouve en rejouant la
        scene sur un depot jetable, ou l'outil rapportait un verdict VERT etranger alors que le
        depot juge en portait un ROUGE.

        Le repli garde son sens : ce repertoire est GITIGNORE, donc vide par construction dans
        un worktree d'agent, et un `glob` y rendrait zero sans lever. `host_inputs` remonte a
        l'arbre principal (ou le `ratchets-bg` tourne) et rend None quand aucun candidat
        n'existe -- ce qui se lit « je n'ai pas regarde », pas « aucune banque n'a tourne ».
        """
        local = self.repo / "logs" / "ratchets-bg"
        if local.is_dir():
            return local
        return host_inputs.resolve(_VERDICTS_REL).path

    def dossier_runs(self) -> Path | None:
        """`logs/ratchets-bg/runs` -- les VERROUS de run. None = PAS MESURE.

        Volontairement ADOSSE au dossier des verdicts, et pas au tmpdir systeme ou vit le
        worktree de `ratchets-bg`. Deux raisons, et la premiere suffit : `Path` cote Python et
        `[System.IO.Path]::GetTempPath()` cote .NET ne lisent pas les memes variables dans le
        meme ordre (`TMP` avant `TEMP` pour l'un, l'inverse pour l'autre) -- un desaccord y
        serait SILENCIEUX, exactement la panne qu'on ferme. Ici la localisation est deja
        resolue, par le meme chemin que les verdicts, avec le meme repli `host_inputs`.
        """
        d = self.dossier_verdicts()
        return None if d is None else (d / "runs")

    def maintenant(self) -> float:
        return time.time()


# ------------------------------------------------------------------ FLOTTE
def mesurer_flotte(src: Sources, plafond: int) -> dict:
    try:
        rows = src.flotte()
    except Exception as e:                                   # noqa: BLE001
        return {"en_vol": _ko("fleet_board", str(e)[:120]),
                "noms": _ko("fleet_board", str(e)[:120]),
                "libres": _ko("fleet_board", str(e)[:120]),
                "plafond": plafond, "chemins": set()}
    n = len(rows)
    return {
        "en_vol": _ok(n, "fleet_board.collect(only_alive)"),
        "noms": _ok([r["name"] for r in rows], "fleet_board"),
        "libres": _ok(max(0, plafond - n), "plafond - en_vol"),
        "plafond": plafond,
        # sert a NE PAS proposer au nettoyage le worktree d'un agent qui travaille encore
        "chemins": {str(Path(r["wt"]).resolve()).lower() for r in rows if r.get("wt")},
    }


# ------------------------------------------------------------------ LIVRAISON
def _porcelain_worktrees(sortie: str) -> list[dict]:
    """`git worktree list --porcelain` -> [{path, branch}]."""
    out, cur = [], {}
    for ln in sortie.splitlines():
        if not ln.strip():
            if cur:
                out.append(cur)
            cur = {}
            continue
        if ln.startswith("worktree "):
            cur = {"path": ln[len("worktree "):].strip(), "branch": None}
        elif ln.startswith("branch "):
            ref = ln[len("branch "):].strip()
            cur["branch"] = ref.rsplit("/", 1)[-1] if ref.startswith("refs/heads/") else ref
    if cur:
        out.append(cur)
    return out


def _gh_prs(src: Sources) -> tuple[Mesure, set[str], bool, float | None, str | None]:
    """(PR ouvertes, refs des PR mergees, mergees_mesuree, age du cache en s, cause du repli).

    UN SEUL appel `gh`, et c'est mesure : deux appels (`--state open` puis `--state merged`)
    coutaient 2,71 s a eux seuls -- plus que tout le reste de l'outil reuni. `--state all` rend
    les deux en une requete, le tri se fait ici.

    Tri-etat sur les OUVERTES : `gh` absent ou hors ligne => PAS MESURE, jamais « 0 PR » --
    c'est la difference entre « plus rien a relire » et « je n'ai pas pu demander ». Le REPLI
    (#467-r6) n'entame pas cette regle : il ne peut que remplacer une IGNORANCE par une mesure
    horodatee PORTANT une PR ouverte. Aucun chemin de cette fonction ne fabrique un zero.
    """
    cache = src.lire_cache_gh()
    repli: str | None = None
    if cache is not None:
        prs, age = cache
    else:
        try:
            rc, out = src.gh("pr", "list", "--state", "all", "--limit", "120",
                             "--json", "number,title,headRefName,isDraft,state")
            if rc != 0:
                raise RuntimeError("gh: rc=%d" % rc)
            prs, age = json.loads(out or "[]"), 0.0
            src.ecrire_cache_gh(prs)
        except Exception as e:                               # noqa: BLE001
            cause = str(e)[:80]
            try:
                vieux = src.lire_cache_gh_repli()
            except Exception:                                # noqa: BLE001
                vieux = None
            # Le repli n'est retenu QUE s'il porte une PR ouverte : cf. `lire_cache_gh_repli`.
            if vieux is None or not [p for p in vieux[0]
                                     if (p.get("state") or "").upper() == "OPEN"]:
                return _ko("gh pr list", cause), set(), False, None, None
            prs, age, repli = vieux[0], vieux[1], cause
    ouvertes = [p for p in prs if (p.get("state") or "").upper() == "OPEN"]
    mergees = {p.get("headRefName", "") for p in prs
               if (p.get("state") or "").upper() == "MERGED"}
    source = "gh pr list --state all" + (" [cache, gh muet]" if repli else "")
    # Sous repli, les PR MERGEES sont ECARTEES (set vide + `mergees_mesuree` faux) : le repli
    # sert a SIGNALER, jamais a autoriser un geste destructeur. Proposer le NETTOYAGE d'un
    # worktree sur un instantane perime, c'est proposer de supprimer le travail d'un agent
    # dont la PR n'est peut-etre plus mergee. Seule la voie ANCETRE (`--merged origin/master`,
    # git local, verifiable) continue alors d'alimenter les nettoyables.
    return _ok(ouvertes, source), (set() if repli else mergees), repli is None, age, repli


def _worktrees_et_livrees(src: Sources) -> tuple[tuple[int, str], tuple[int, str]]:
    """Les worktrees d'agents, puis LESQUELLES de LEURS branches sont deja livrees.

    Deux appels en SEQUENCE, et c'est le bon ordre : `git branch --merged origin/master`
    parcourt les 169 branches locales du depot, dont 131 sont des branches d'agents deja
    fusionnees et sans interet -- alors qu'on n'a besoin du verdict que pour les rares
    branches encore MONTEES dans un worktree. `for-each-ref` restreint le parcours a
    celles-la. Le second appel est meme ENTIEREMENT saute quand aucun worktree d'agent
    n'existe : au repos, l'outil ne le paie pas du tout.
    """
    rc_wt, out_wt = src.git("worktree", "list", "--porcelain")
    if rc_wt != 0:
        return (rc_wt, out_wt), (rc_wt, "")
    refs = ["refs/heads/" + w["branch"] for w in _porcelain_worktrees(out_wt)
            if w["branch"] and ".claude/worktrees/agent-" in w["path"].replace("\\", "/")]
    if not refs:
        return (rc_wt, out_wt), (0, "")
    return (rc_wt, out_wt), src.git("for-each-ref", "--merged", "origin/master",
                                    "--format=%(refname:short)", *refs)


def mesurer_livraison(src: Sources) -> dict:
    """Toutes les entrees de la livraison, en PARALLELE.

    Les deux postes lourds -- `git status` (1,2 s sur cet arbre) et `gh pr list` (1,2 s de
    reseau) -- sont independants : joues en serie ils faisaient a eux seuls 3,6 s de mur, soit
    plus que le budget entier d'un hook. Le pool les recouvre.
    """
    d: dict = {}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        # UN SEUL `git status --porcelain=v2 --branch` porte la branche, l'avance sur l'upstream
        # ET l'etat de l'arbre. Chaque process git coute ~0,2 s de demarrage sous Windows, et
        # ils se genent entre eux : trois appels fondus en un, c'est ~0,4 s de mur en moins.
        f_status = ex.submit(src.git, "status", "--porcelain=v2", "--branch")
        f_wt_mg = ex.submit(_worktrees_et_livrees, src)
        f_gh = ex.submit(_gh_prs, src)
        rc, out = f_status.result()
        (rc_wt, out_wt), (rc_mg, out_mg) = f_wt_mg.result()
        pr_ouvertes, pr_mergees_refs, pr_mergees_ok, age_gh, gh_repli = f_gh.result()
    d["gh_age_s"] = age_gh
    d["gh_repli"] = gh_repli

    if rc != 0:
        for k in ("branche", "avance", "suivis_sales", "non_suivis", "non_suivis_inconnus"):
            d[k] = _ko("git status --porcelain=v2", "rc=%d" % rc)
    else:
        entetes, suivis, inconnus, connus = {}, [], [], 0
        for ln in out.splitlines():
            if not ln.strip():
                continue
            if ln.startswith("# "):
                k, _, v = ln[2:].partition(" ")
                entetes[k] = v.strip()
                continue
            if ln.startswith("? "):
                chemin = ln[2:].strip().strip('"')
                if any(m in chemin for m in UNTRACKED_CONNUS):
                    connus += 1
                else:
                    inconnus.append(chemin)
            elif ln[:2] in ("1 ", "2 ", "u "):
                # v2 : le chemin est le DERNIER champ ; un renommage (`2 `) porte
                # `<nouveau><TAB><ancien>`, dont seul le nouveau nous interesse.
                d_ = ln.split(" ", 8)
                suivis.append(d_[-1].split("\t")[0].strip().strip('"'))
        d["branche"] = _ok(entetes.get("branch.head", "?"), "git status v2 # branch.head")
        d["suivis_sales"] = _ok(suivis, "git status --porcelain=v2")
        d["non_suivis"] = _ok(connus + len(inconnus), "git status --porcelain=v2")
        d["non_suivis_inconnus"] = _ok(inconnus, "git status v2 (hors UNTRACKED_CONNUS)")
        # `branch.ab` compte contre l'UPSTREAM de HEAD, pas contre origin/master : on ne s'en
        # sert QUE s'ils coincident (le cas nominal, l'arbre principal sur master -- exactement
        # la ou le hook tourne). Sinon un `rev-list` explicite, qui garde la question posee :
        # « combien de MES commits ne sont pas dans origin/master ».
        # On ne fetch pas : la ref de suivi est locale, la reponse est « ce que je n'ai pas
        # pousse », jamais « de combien je suis en retard ».
        ab = entetes.get("branch.ab", "")
        if entetes.get("branch.upstream") == "origin/master" and ab.startswith("+"):
            d["avance"] = _ok(int(ab.split()[0][1:]), "git status v2 # branch.ab")
        else:
            rc2, out2 = src.git("rev-list", "--count", "origin/master..HEAD")
            d["avance"] = (_ok(int(out2.strip() or 0), "git rev-list origin/master..HEAD")
                           if rc2 == 0 else _ko("git rev-list", "rc=%d" % rc2))

    # -- worktrees d'agents, et lesquels sont NETTOYABLES
    if rc_wt != 0:
        d["worktrees"] = _ko("git worktree list", "rc=%d" % rc_wt)
        d["nettoyables"] = _ko("git worktree list", "rc=%d" % rc_wt)
        branches_agents: dict[str, str] = {}
    else:
        wts = [w for w in _porcelain_worktrees(out_wt)
               if ".claude/worktrees/agent-" in w["path"].replace("\\", "/")]
        d["worktrees"] = _ok([w["path"] for w in wts], "git worktree list --porcelain")
        branches_agents = {w["branch"]: w["path"] for w in wts if w["branch"]}

    # `--merged origin/master` = le tip de la branche est ANCETRE. C'est le cote SUR : un
    # squash-merge n'y apparait pas (faux negatif), donc on ne proposera jamais de nettoyer une
    # branche non livree. Les squash sont rattrapes par `gh pr list --state merged`.
    mergees = {b.strip() for b in out_mg.splitlines() if b.strip()} if rc_mg == 0 else set()

    d["pr_ouvertes"] = pr_ouvertes
    if d["worktrees"].mesuree and (rc_mg == 0 or pr_mergees_ok):
        nett = []
        for br, chemin in sorted(branches_agents.items()):
            if br not in mergees and br not in pr_mergees_refs:
                continue
            nett.append({"branche": br, "chemin": chemin,
                         "voie": "ancetre" if br in mergees else "PR mergee"})
        d["nettoyables"] = _ok(nett, "git branch --merged + gh pr list --state merged")
    else:
        d["nettoyables"] = _ko("nettoyables", "ni --merged ni gh n'ont repondu")
    return d


# ------------------------------------------------------------------ HARNAIS
def mesurer_harnais(src: Sources) -> dict:
    d: dict = {}
    try:
        st = src.http_json("/api/admin/status")
        # `.session` SINGULIER -- `.sessions` n'existe pas, et l'avoir cru a deja coute.
        d["session"] = _ok(st.get("session"), "GET /api/admin/status .session")
        d["jeu"] = _ok(bool((st.get("tacticus") or {}).get("running")), "status .tacticus.running")
    except Exception as e:                                   # noqa: BLE001
        d["session"] = _ko("GET /api/admin/status", str(e)[:80])
        d["jeu"] = _ko("GET /api/admin/status", str(e)[:80])
    try:
        dr = src.http_json("/api/admin/drain")
        d["drain"] = _ok(bool(dr.get("enabled")), "GET /api/admin/drain .enabled")
        # Le host rend DEJA `liveRunners` en tri-etat (null = pas mesure cote hooks). On le
        # PROPAGE : le rabattre sur 0 autoriserait a lancer 4 tests sur un budget inconnu.
        lr, err = dr.get("liveRunners"), dr.get("liveRunnersError")
        d["live_runners"] = (_ok(int(lr), "GET /api/admin/drain .liveRunners (hooks)")
                             if isinstance(lr, int)
                             else _ko("GET /api/admin/drain .liveRunners", str(err or "null")[:80]))
    except Exception as e:                                   # noqa: BLE001
        d["drain"] = _ko("GET /api/admin/drain", str(e)[:80])
        d["live_runners"] = _ko("GET /api/admin/drain", str(e)[:80])
    return d


# ------------------------------------------------------------------ BANQUE
def _lire_verdict(p: Path) -> tuple[str, int | None, str]:
    """(sha, rc, etiquette) d'un verdict `ratchets-bg`. DEUX voies, et il en faut deux.

    Voie 1, l'en-tete `rc      : <n>  (<etat>)`. Voie 2, la ligne de bilan du corps,
    `[ratchets-bg] <etat> -- commit <court>, <n> s`.

    La voie 2 n'est pas une ceinture de securite theorique : les verdicts ecrits AVANT le
    correctif de precedence de `ratchets-bg.ps1` (2026-08-04) n'ont PAS de ligne `rc` du tout --
    leur en-tete entier tient sur une ligne. Les lire par la seule voie 1 rendait « rc inconnu »
    sur les 3 verdicts presents, c'est-a-dire un capteur muet sur son unique gisement.
    """
    sha, rc, etiq = "", None, "?"
    try:
        texte = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return sha, rc, etiq
    # `lstrip` du BOM : PowerShell 5.1 ecrit `utf8` AVEC BOM (PS7 sans). Un BOM devant `commit`
    # ferait echouer le `startswith` et rendrait le sha VIDE -- donc « fraicheur inconnue » a vie.
    lignes = texte.lstrip("﻿").splitlines()
    for ln in lignes[:8]:
        if ln.startswith("commit") and ":" in ln:
            mot = ln.split(":", 1)[1].split()
            if mot:
                sha = mot[0]
        elif ln.startswith("rc") and ":" in ln:
            reste = ln.split(":", 1)[1].strip()
            try:
                rc = int(reste.split()[0])
            except (ValueError, IndexError):
                rc = None
            if "(" in reste:
                # UN SEUL `)` retire, pas `rstrip(")")` : l'etiquette d'un ROUGE porte ses
                # PROPRES parentheses (`rc      : 2  (ROUGE (2))`), et un rstrip gourmand les
                # mangeait toutes -- la ligne rendue etait `rc=2 [ROUGE (2]`, desequilibree
                # exactement sur le seul regime ou elle compte.
                etiq = reste.split("(", 1)[1].strip()
                etiq = etiq[:-1] if etiq.endswith(")") else etiq
    if rc is None:
        for ln in reversed(lignes):
            if ln.startswith("[ratchets-bg] ") and " -- commit " in ln:
                etiq = ln[len("[ratchets-bg] "):].split(" -- commit ")[0].strip()
                # Meme table que `ratchets-bg.ps1` : VERTE=0, USAGE=64, MONTAGE=99, sinon
                # le nombre de cliquets rouges, que l'etiquette porte entre parentheses.
                rc = (0 if etiq.startswith("VERTE")
                      else 64 if etiq.startswith("USAGE")
                      else 99 if etiq.startswith("MONTAGE")
                      else int(etiq.split("(")[1].rstrip(")")) if "(" in etiq else None)
                break
    return sha, rc, etiq


def _sha_entete(p: Path) -> str:
    """Le commit JUGE, lu dans les premiers octets. Balayage bon marche.

    `_lire_verdict` lit le fichier ENTIER (il lui faut le corps pour la voie 2 du rc) ; ici on
    ne cherche que le sha, qui est toujours en tete -- y compris dans la forme d'en-tete CASSEE
    (tout sur une ligne), ou `commit  : <sha> sujet   : ...` commence pareil. 512 octets pour
    50 utiles : la marge est la pour ne pas dependre de la mise en forme.
    """
    try:
        with p.open("rb") as f:
            tete = f.read(512).decode("utf-8", "replace")
    except OSError:
        return ""
    for ln in tete.lstrip("﻿").splitlines():
        if ln.startswith("commit") and ":" in ln:
            mot = ln.split(":", 1)[1].split()
            if mot:
                return mot[0]
    return ""


def _meme_commit(a: str, b: str) -> bool:
    """Deux sha designent-ils le meme commit ? Tolerant aux formes abregees (>= 7)."""
    if not a or not b or min(len(a), len(b)) < 7:
        return False
    n = min(len(a), len(b))
    return a[:n].lower() == b[:n].lower()


def _fraicheur(src: Sources, sha: str, pointe: str) -> str:
    """`pointe` | `ancetre` | `hors-lignee` | `inconnue` -- A QUOI ce verdict s'applique.

    `inconnue` couvre DEUX ignorances qu'on ne fabrique pas : la pointe non mesuree, et un
    `merge-base` qui ne repond pas (git muet) ou qui ne connait pas le commit (`rc=128`, verdict
    d'un arbre etranger). Aucune ne se rabat sur `pointe` -- ce serait exactement le glissement
    que #472 ferme : rendre pour l'etat COURANT ce qui n'a pas ete confronte a la pointe.
    """
    if not sha or not pointe:
        return "inconnue"
    if _meme_commit(sha, pointe):
        return "pointe"
    code, _ = src.git("merge-base", "--is-ancestor", sha, "HEAD")
    if code == 0:
        return "ancetre"
    return "hors-lignee" if code == 1 else "inconnue"


def _verrou_tenu(p: Path) -> bool:
    """Ce verrou est-il TENU par un processus VIVANT ? Un FAIT de l'OS, pas une heuristique.

    `ratchets-bg.ps1` ouvre son verrou en partage LECTURE SEULE (`FileShare.Read`) et garde le
    handle pendant tout le run : tant qu'il vit, aucun autre processus ne peut ouvrir le fichier
    en ECRITURE. Le tester ainsi ne suppose rien -- ni PID (recyclable), ni age (une banque lente
    est un run lent, pas un run mort), ni bonne foi du producteur.

    Le pendant est ce qui rend le mecanisme honnete dans l'autre sens : un run TUE (kill, reboot,
    fenetre fermee) laisse son fichier, mais l'OS libere toujours le handle -- le verrou devient
    ouvrable, donc un RESIDU, et il ne peut plus fabriquer un « EN COURS » perpetuel. C'est le
    defaut de conception qu'un simple fichier-temoin aurait introduit.

    Le test est WINDOWS (partage de fichiers). Ailleurs il rend `False` sur un verrou pourtant
    tenu : `EN COURS` se degrade alors en `NON JUGEE`, qui reste VRAI (la pointe n'est
    effectivement pas jugee) -- on perd le raffinement, jamais la justesse. `ratchets-bg.ps1`
    etant du PowerShell, il n'y a de toute facon pas de verrou a lire hors Windows.
    """
    try:
        with p.open("r+b"):
            return False                    # ouvrable en ECRITURE => plus personne ne le tient
    except PermissionError:
        return True                         # ERROR_SHARING_VIOLATION : un run le tient
    except OSError:
        return False


def _lire_verrou(p: Path) -> dict:
    """`{commit, pid, debut, repo}` d'un verrou de run. Champs absents = chaine vide."""
    d = {"commit": "", "pid": "", "debut": "", "repo": ""}
    try:
        texte = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return d
    for ln in texte.lstrip("﻿").splitlines():
        cle, _, val = ln.partition(":")
        cle = cle.strip().lower()
        if cle in d:
            d[cle] = val.strip()
    return d


def _runs_vivants(dossier: Path) -> tuple[list[dict], int]:
    """(runs VIVANTS, nombre de residus). Le repertoire peut ne pas exister : 0 verrou pose."""
    vivants, residus = [], 0
    try:
        fichiers = sorted(dossier.glob("*.lock"))
    except OSError:
        return vivants, residus
    for p in fichiers:
        if _verrou_tenu(p):
            info = _lire_verrou(p)
            info["fichier"] = str(p)
            vivants.append(info)
        else:
            residus += 1
    return vivants, residus


def _etat_pointe(fraicheur: str, m_pointe: Mesure, m_runs: Mesure, pointe: str) -> Mesure:
    """`JUGEE` | `EN COURS` | `NON JUGEE`, ou PAS MESURE. La table, en UN seul endroit.

    `NON JUGEE` n'affirme PAS « personne ne tourne » -- il dit « aucun verdict ne porte sur la
    pointe », ce qui est vrai dans tous les cas. `EN COURS` est ce meme etat PLUS une raison
    connue de patienter, et cette raison est un fait. Aucun chemin n'invente le cas rassurant.
    """
    if fraicheur == "pointe":
        return _ok("JUGEE", "sha du verdict == git rev-parse HEAD")
    if not m_pointe.mesuree:
        return _ko("git rev-parse HEAD", m_pointe.erreur or "pointe inconnue")
    if not m_runs.mesuree:
        return _ko("logs/ratchets-bg/runs", m_runs.erreur or "verrous non lus")
    if any(_meme_commit(r.get("commit", ""), pointe) for r in m_runs.valeur):
        return _ok("EN COURS", "verrou de run TENU sur la pointe")
    return _ok("NON JUGEE", "aucun verdict ni run pour la pointe")


def mesurer_banque(src: Sources, journal: dict) -> dict:
    rc_p, out_p = src.git("rev-parse", "HEAD")
    pointe = out_p.strip().splitlines()[0].strip() if (rc_p == 0 and out_p.strip()) else ""
    m_pointe = (_ok(pointe, "git rev-parse HEAD") if pointe
                else _ko("git rev-parse HEAD",
                         "rc=%d" % rc_p if rc_p != 0 else "sortie vide"))

    dossier = src.dossier_verdicts()
    d_runs = src.dossier_runs()
    if d_runs is None:
        m_runs: Mesure = _ko("logs/ratchets-bg/runs", "repertoire introuvable (gitignore)")
        residus = 0
    else:
        vivants, residus = _runs_vivants(d_runs)
        m_runs = _ok(vivants, "logs/ratchets-bg/runs (verrous TENUS)")

    if dossier is None:
        return {"verdict": _ko("logs/ratchets-bg", "repertoire introuvable (gitignore)"),
                "pointe": m_pointe, "runs": m_runs, "residus": residus,
                "etat": _etat_pointe("inconnue", m_pointe, m_runs, pointe)}
    fichiers = sorted(dossier.glob("*.txt"), key=lambda p: p.stat().st_mtime)
    if not fichiers:
        return {"verdict": _ok(None, "logs/ratchets-bg (vide)"),
                "pointe": m_pointe, "runs": m_runs, "residus": residus,
                "etat": _etat_pointe("aucun", m_pointe, m_runs, pointe)}

    # Le verdict RETENU est celui de la POINTE s'il en existe un -- pas le dernier ecrit. Les
    # deux different des qu'un run juge autre chose que la pointe (bisect, `-Commit <ancien>`,
    # PR d'un agent) : prendre le dernier par mtime rendrait alors un verdict etranger pour
    # l'etat courant. A defaut, le plus recent, et il portera sa FRAICHEUR.
    retenu = None
    if pointe:
        for p in reversed(fichiers):
            if _meme_commit(_sha_entete(p), pointe):
                retenu = p
                break
    choisi = retenu if retenu is not None else fichiers[-1]

    sha, rc, etiq = _lire_verdict(choisi)
    livre = None
    if sha:
        code, _ = src.git("merge-base", "--is-ancestor", sha, "origin/master")
        # `RC_MUET` = git n'a pas repondu. `livre` reste None -- et le signal « vert non encore
        # livre » teste `is False`, donc un echec de mesure ne fabrique aucun faux signal.
        livre = None if code == src.RC_MUET else (code == 0)
    fraicheur = "pointe" if retenu is not None else _fraicheur(src, sha, pointe)
    v = {
        "fichier": str(choisi), "commit": sha[:8], "rc": rc, "etat": etiq,
        "age_min": (src.maintenant() - choisi.stat().st_mtime) / 60.0,
        "livre": livre,
        "deja_signale": journal.get("verdict_vu") == choisi.name,
        "fraicheur": fraicheur,
        "pointe": pointe[:8],
    }
    return {"verdict": _ok(v, "logs/ratchets-bg (%s)"
                           % ("verdict de la pointe" if retenu is not None else "dernier ecrit")),
            "pointe": m_pointe, "runs": m_runs, "residus": residus,
            "etat": _etat_pointe(fraicheur, m_pointe, m_runs, pointe)}


# ------------------------------------------------------------------ etat complet
def etat(src: Sources, plafond: int, journal: dict | None = None) -> dict:
    """Toutes les mesures, en parallele. Aucune ne peut faire echouer les autres."""
    journal = journal or {}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_flotte = ex.submit(mesurer_flotte, src, plafond)
        f_livr = ex.submit(mesurer_livraison, src)
        f_harnais = ex.submit(mesurer_harnais, src)
        f_banque = ex.submit(mesurer_banque, src, journal)
        flotte, livr = f_flotte.result(), f_livr.result()
        harnais, banque = f_harnais.result(), f_banque.result()

    # JONCTION, apres coup pour que les quatre mesures restent independantes : un agent qui
    # TRAVAILLE garde son worktree meme si sa branche est deja mergee (il peut encore
    # committer). Le proposer au nettoyage, c'est proposer de le tuer.
    if livr["nettoyables"].mesuree and flotte["chemins"]:
        garde = [w for w in livr["nettoyables"].valeur
                 if str(Path(w["chemin"]).resolve()).lower() not in flotte["chemins"]]
        livr["nettoyables"] = _ok(garde, livr["nettoyables"].source + " - agents en vol")
    return {"flotte": flotte, "livraison": livr, "harnais": harnais, "banque": banque,
            "repo": str(src.repo)}


# ------------------------------------------------------------------ signaux
@dataclass
class Signal:
    cle: str
    ligne: str


_FRAICHEUR_TXT = {
    "ancetre": "PERIME (juge %s, la pointe est %s)",
    "hors-lignee": "PERIME (juge %s, HORS de la lignee de la pointe %s)",
    "inconnue": "fraicheur INCONNUE (juge %s, pointe %s)",
}


def _txt_fraicheur(v: dict) -> str:
    return _FRAICHEUR_TXT.get(v["fraicheur"], "juge %s, pointe %s") % (
        v["commit"] or "?", v["pointe"] or "?")


def _ctx_banque(bq: dict, v: dict | None) -> str:
    """La ligne de CONTEXTE quand la pointe n'est pas jugee. Elle AFFICHE, elle n'alarme pas.

    C'est la borne anti-glissement de #472 : un verdict perime ne devient pas silencieux -- on
    continue de dire qu'il existe, ce qu'il vaut et SUR QUOI il porte. Ce qui change est
    l'ACCUSE : il quitte les signaux (« l'etat courant est ROUGE ») pour le contexte (« la
    banque a juge, mais pas ceci »).
    """
    etatm = bq.get("etat")
    pointe8 = bq["pointe"].valeur[:8] if bq["pointe"].mesuree else "?"
    if etatm is None:
        quoi = "?"
    elif not etatm.mesuree:
        quoi = "etat NON MESURE (%s)" % etatm.erreur
    else:
        quoi = etatm.valeur
    if v is None:
        detail = "" if bq["verdict"].mesuree else " ; %s" % bq["verdict"].txt()
    else:
        detail = " ; dernier verdict rc=%s [%s] %s, il y a %.0f min" % (
            v["rc"], v["etat"], _txt_fraicheur(v), v["age_min"])
    return "banque : pointe %s %s%s" % (pointe8, quoi, detail)


def signaux(e: dict) -> tuple[list[Signal], list[str]]:
    """Rend (ce qui APPELLE UNE ACTION, ce qui est du CONTEXTE).

    Un signal est ACTIONNABLE : il nomme un geste que l'orchestrateur peut poser tout de suite.
    Le contexte accompagne les signaux quand il y en a, et ne parle jamais seul -- c'est ce qui
    fait que l'outil se TAIT quand tout va bien.
    """
    sig: list[Signal] = []
    ctx: list[str] = []
    fl, lv, ha, bq = e["flotte"], e["livraison"], e["harnais"], e["banque"]

    # -- La campagne est-elle EN COURS ? Derive, jamais declare. Hors campagne, des slots vides
    #    sont l'etat NORMAL d'un depot au repos : les signaler serait du bruit a chaque tour.
    en_vol = fl["en_vol"].valeur if fl["en_vol"].mesuree else 0
    wts = len(lv["worktrees"].valeur) if lv["worktrees"].mesuree else 0
    prs = len(lv["pr_ouvertes"].valeur) if lv["pr_ouvertes"].mesuree else 0
    avance = lv["avance"].valeur if lv["avance"].mesuree else 0
    campagne = bool(en_vol or wts or prs or avance)

    if campagne and fl["libres"].mesuree and fl["libres"].valeur > 0:
        sig.append(Signal("slots", "%d SLOT(S) d'agent LIBRE(S) -- %d/%d en vol"
                          % (fl["libres"].valeur, en_vol, fl["plafond"])))
    if not fl["en_vol"].mesuree:
        sig.append(Signal("flotte-inconnue", "flotte NON MESUREE (%s)" % fl["en_vol"].erreur))

    if avance:
        sig.append(Signal("push", "%d commit(s) non pousse(s) sur origin/master (branche %s)"
                          % (avance, lv["branche"].txt())))
    if lv["suivis_sales"].mesuree and lv["suivis_sales"].valeur:
        n = len(lv["suivis_sales"].valeur)
        sig.append(Signal("sale", "%d fichier(s) SUIVI(S) modifie(s) non commis : %s"
                          % (n, ", ".join(lv["suivis_sales"].valeur[:4])
                             + (" ..." if n > 4 else ""))))
    if lv["nettoyables"].mesuree and lv["nettoyables"].valeur:
        noms = ", ".join(w["branche"][-12:] for w in lv["nettoyables"].valeur[:5])
        sig.append(Signal("nettoyage", "%d worktree(s) d'agent NETTOYABLE(S) (branche livree) : %s"
                          % (len(lv["nettoyables"].valeur), noms)))
    if lv["pr_ouvertes"].mesuree and lv["pr_ouvertes"].valeur:
        ctx.append("PR ouvertes : %d%s (%s)"
                   % (len(lv["pr_ouvertes"].valeur), _age_gh(lv),
                      ", ".join("#%s" % p.get("number") for p in lv["pr_ouvertes"].valeur[:8])))
    elif not lv["pr_ouvertes"].mesuree:
        ctx.append("PR : %s" % lv["pr_ouvertes"].txt())

    # LE VERDICT DE BANQUE -- et A QUOI il s'applique (#472).
    #
    # Un verdict n'accuse l'etat COURANT que s'il porte SUR LA POINTE. Les regimes :
    #   rc is None    -> le fichier existe mais son rc est ILLISIBLE : un capteur muet, jamais
    #                    « rien a signaler ». Il accuse l'OUTIL D'ECRITURE, pas le commit juge --
    #                    donc il est signale QUELLE QUE SOIT la fraicheur (c'est le bug d'en-tete
    #                    trouve le 2026-08-04 sur les 3 verdicts presents) ;
    #   sur la pointe, rc != 0  -> un VERDICT defavorable : signale a CHAQUE tour, il ne
    #                    s'acquitte pas, il se CORRIGE ;
    #   sur la pointe, rc == 0  -> signale UNE FOIS, et seulement s'il porte sur du travail PAS
    #                    ENCORE dans origin/master. Un vert deja livre n'appelle aucun geste ;
    #   PERIME        -> AUCUN signal. Il reste AFFICHE en contexte -- utile a savoir, jamais a
    #                    alarmer -- et n'est rabattu ni sur un vert ni sur un rouge.
    bqv = bq["verdict"]
    v = bqv.valeur if (bqv.mesuree and isinstance(bqv.valeur, dict)) else None
    sur_pointe = v is not None and v["fraicheur"] == "pointe"
    if v is not None and v["rc"] is None:
        sig.append(Signal("banque-illisible",
                          "verdict de banque %s ILLISIBLE (pas de rc) -- %s"
                          % (v["commit"] or "?", Path(v["fichier"]).name)))
    elif sur_pointe and v["rc"] != 0:
        # `%s` entre crochets : l'etiquette de `ratchets-bg` porte deja ses propres
        # parentheses (`ROUGE (2)`), et l'imbriquer rendait une ligne desequilibree.
        sig.append(Signal("banque", "verdict de banque %s rc=%s [%s] SUR LA POINTE, il y a "
                                    "%.0f min" % (v["commit"], v["rc"], v["etat"], v["age_min"])))
    elif sur_pointe and v["livre"] is False and not v["deja_signale"]:
        sig.append(Signal("banque", "verdict de banque %s VERTE (il y a %.0f min) -- son "
                                    "commit n'est PAS ENCORE dans origin/master"
                                    % (v["commit"], v["age_min"])))

    if not sur_pointe:
        ctx.append(_ctx_banque(bq, v))

    if ha["drain"].mesuree and ha["drain"].valeur:
        sig.append(Signal("drain", "mode DRAIN ARME -- la creation de runner est refusee"))
    if not ha["session"].mesuree:
        ctx.append("harnais : %s" % ha["session"].erreur)
    elif ha["session"].valeur is None:
        sig.append(Signal("session", "AUCUNE session Frida -- tout RPC/runner echouera"))
    else:
        s = ha["session"].valeur
        ctx.append("session %s %s (pid %s)" % (s.get("id"), s.get("status"), s.get("pid")))

    lr = ha["live_runners"]
    if lr.mesuree and lr.valeur and not en_vol:
        sig.append(Signal("orphelins", "%d runner(s) VIVANT(S) sans aucun agent en vol -- "
                                       "candidats orphelins" % lr.valeur))
    ctx.append("liveRunners %s (budget partage des 4-en-parallele)" % lr.txt())
    return sig, ctx


# ------------------------------------------------------------------ journal
def _chemin_journal(src: Sources) -> Path | None:
    d = src.dossier_verdicts()
    return (d.parent / "loop-status-seen.json") if d is not None else None


def lire_journal(src: Sources) -> dict:
    p = _chemin_journal(src)
    if p is None or not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ecrire_journal(src: Sources, e: dict) -> None:
    """Acquitte le dernier verdict VERT. Un ROUGE ne s'acquitte pas : il se CORRIGE."""
    p = _chemin_journal(src)
    v = e["banque"]["verdict"]
    if p is None or not v.mesuree or not isinstance(v.valeur, dict):
        return
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"verdict_vu": Path(v.valeur["fichier"]).name,
                                 "quand": time.strftime("%Y-%m-%dT%H:%M:%S")}),
                     encoding="utf-8")
    except OSError:
        pass


# ------------------------------------------------------------------ rendu
def _duree(s: float) -> str:
    return "%.0f s" % s if s < 120.0 else "%.0f min" % (s / 60.0)


def _age_gh(lv: dict) -> str:
    """L'age du cache GitHub, RENDU a cote de tout chiffre qui en derive.

    Sous REPLI (#467-r6), la panne de `gh` est NOMMEE dans la meme ligne : sans cela le
    chiffre servi se lirait comme une mesure fraiche, et la panne serait masquee par le
    correctif meme qui la contourne.
    """
    a = lv.get("gh_age_s")
    if lv.get("gh_repli"):
        return " [cache %s, gh muet: %s]" % (_duree(a or 0.0), lv["gh_repli"])
    return "" if not a or a < 1.0 else " [cache %s]" % _duree(a)


def rendu_complet(e: dict, sig: list[Signal], ctx: list[str]) -> str:
    fl, lv, ha, bq = e["flotte"], e["livraison"], e["harnais"], e["banque"]
    L = ["[boucle] %s  (%s)" % (e["repo"], lv["branche"].txt())]
    L.append("")
    L.append("FLOTTE     en vol %s / %d -> %s libre(s)"
             % (fl["en_vol"].txt(), fl["plafond"], fl["libres"].txt()))
    if fl["noms"].mesuree:
        for n in fl["noms"].valeur:
            L.append("             . %s" % n[:64])
    L.append("LIVRAISON  %s commit(s) non pousse(s) sur origin/master" % lv["avance"].txt())
    if lv["suivis_sales"].mesuree:
        L.append("           arbre : %d suivi(s) modifie(s), %s non suivi(s) dont %d inconnu(s)"
                 % (len(lv["suivis_sales"].valeur), lv["non_suivis"].txt(),
                    len(lv["non_suivis_inconnus"].valeur)))
    else:
        L.append("           arbre : %s" % lv["suivis_sales"].txt())
    if lv["pr_ouvertes"].mesuree:
        L.append("           PR ouvertes : %d%s%s"
                 % (len(lv["pr_ouvertes"].valeur), _age_gh(lv),
                    ("  " + ", ".join("#%s %s" % (p.get("number"), (p.get("title") or "")[:38])
                                      for p in lv["pr_ouvertes"].valeur[:6]))
                    if lv["pr_ouvertes"].valeur else ""))
    else:
        L.append("           PR ouvertes : %s" % lv["pr_ouvertes"].txt())
    if lv["worktrees"].mesuree:
        n_net = len(lv["nettoyables"].valeur) if lv["nettoyables"].mesuree else None
        L.append("           worktrees d'agents : %d ; nettoyables : %s"
                 % (len(lv["worktrees"].valeur),
                    n_net if n_net is not None else lv["nettoyables"].txt()))
        if lv["nettoyables"].mesuree:
            for w in lv["nettoyables"].valeur:
                L.append("             . %s  [%s]" % (w["branche"], w["voie"]))
    L.append("HARNAIS    session %s ; drain %s ; liveRunners %s"
             % (("aucune" if ha["session"].valeur is None else
                 "%s %s" % (ha["session"].valeur.get("id"), ha["session"].valeur.get("status")))
                if ha["session"].mesuree else ha["session"].txt(),
                ("ARME" if ha["drain"].valeur else "off") if ha["drain"].mesuree
                else ha["drain"].txt(),
                ha["live_runners"].txt()))
    # La POINTE d'abord, et TOUJOURS : c'est elle que la ligne pretend decrire. Un verdict sans
    # son commit de reference est ce qui a fait lire trois tours de suite un rouge deja corrige.
    L.append("BANQUE     pointe %s : %s" % (bq["pointe"].txt("%.8s"), bq["etat"].txt()))
    if bq["verdict"].mesuree and isinstance(bq["verdict"].valeur, dict):
        v = bq["verdict"].valeur
        L.append("           verdict %s rc=%s (%s) il y a %.0f min ; fraicheur=%s ; livre=%s ; "
                 "deja signale=%s" % (v["commit"], v["rc"], v["etat"], v["age_min"],
                                      v["fraicheur"], v["livre"], v["deja_signale"]))
    else:
        L.append("           verdict %s" % bq["verdict"].txt())
    if bq.get("runs") is not None:
        L.append("           runs vivants : %s%s"
                 % (len(bq["runs"].valeur) if bq["runs"].mesuree else bq["runs"].txt(),
                    " ; %d verrou(s) RESIDUEL(S)" % bq["residus"] if bq.get("residus") else ""))
        if bq["runs"].mesuree:
            for r in bq["runs"].valeur:
                L.append("             . %s (pid %s, depuis %s)"
                         % ((r.get("commit") or "?")[:8], r.get("pid") or "?",
                            r.get("debut") or "?"))
    L.append("")
    if sig:
        L.append("A FAIRE :")
        for s in sig:
            L.append("  - %s" % s.ligne)
    else:
        L.append("RIEN A SIGNALER.")
    if ctx:
        L.append("contexte : " + " ; ".join(ctx))
    return "\n".join(L)


def rendu_hook(sig: list[Signal], ctx: list[str]) -> str:
    L = ["[boucle] etat DERIVE de la boucle d'orchestration -- rien de ceci n'est declare :"]
    for s in sig:
        L.append("  - %s" % s.ligne)
    if ctx:
        L.append("  (contexte : " + " ; ".join(ctx) + ")")
    L.append("Traite ce qui s'applique, puis termine ton tour. Ce rappel ne se repetera pas "
             "dans cette meme chaine.")
    return "\n".join(L)


# ------------------------------------------------------------------ CLI
def _sous(chemin: str, racine: str) -> bool:
    """`chemin` est-il la racine ou sous elle ? (comparaison de chemins, pas de chaines)."""
    try:
        a, b = Path(chemin).resolve(), Path(racine).resolve()
    except OSError:
        return False
    return a == b or b in a.parents


def _sortie_ascii(s: str) -> str:
    """La console est en cp1252 : tout non-ASCII y leve UnicodeEncodeError."""
    return s.encode("ascii", "replace").decode("ascii")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hook", action="store_true",
                    help="mode hook Stop : lit le JSON du hook sur stdin, emet un JSON de decision")
    ap.add_argument("--json", action="store_true", help="etat brut, machine")
    ap.add_argument("--max-agents", type=int, default=None, help="plafond de dispatch")
    ap.add_argument("--host", default=os.environ.get("TACTICUS_HOST_URL", HOST_DEFAUT))
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--no-gh", action="store_true", help="ne pas interroger GitHub")
    ap.add_argument("--no-host", action="store_true", help="ne pas interroger le host Frida")
    # Defauts RESOLUS plus bas : sous `--hook` on serre le timeout et on allonge le cache --
    # un hook synchrone ne doit jamais immobiliser un tour pour une reponse GitHub lente.
    ap.add_argument("--timeout", type=float, default=None)
    ap.add_argument("--timeout-gh", type=float, default=None,
                    help="budget PROPRE de `gh`, en secondes (defaut : 10 sous --hook, 12 sinon)")
    ap.add_argument("--ttl-cache", type=float, default=None,
                    help="duree de vie du cache GitHub, en secondes (0 = pas de cache)")
    ap.add_argument("--ack", action="store_true",
                    help="acquitte le dernier verdict de banque (implicite sous --hook)")
    a = ap.parse_args(argv)

    if a.hook and os.environ.get("TACTICUS_LOOP_STATUS_HOOK", "1") == "0":
        return 0

    if a.hook:
        # Le `lstrip` du BOM n'est PAS decoratif : PowerShell 5.1 prefixe d'un `﻿` tout ce
        # qu'il pipe vers un executable natif. `json.loads` levait donc, la charge retombait a
        # `{}`, et le hook parlait MALGRE `stop_hook_active` -- exactement la boucle qu'il est
        # cense eviter. MESURE le 2026-08-04 sur le wrapper de ce depot.
        brut = sys.stdin.read().lstrip("﻿ \t\r\n")
        if brut:
            try:
                charge = json.loads(brut)
            except ValueError:
                return 0      # charge illisible : on ne sait plus dans quelle chaine on est
        else:
            charge = {}       # stdin vide : appel manuel, legitime
        # Anti-boucle : Claude continue DEJA a cause d'un stop hook. Re-bloquer ici le ferait
        # tourner indefiniment.
        if charge.get("stop_hook_active"):
            return 0
        # Le hook `Stop` est GLOBAL (`~/.claude/settings.json`) : il se declenche pour TOUS les
        # projets de la machine. On ne parle que du notre.
        # La comparaison porte sur `--repo`, PAS sur `REPO` (la racine deduite de `__file__`) :
        # depuis un worktree d'agent, `REPO` vaut le worktree, et le hook se taisait alors pour
        # l'arbre principal -- c'est-a-dire pour le seul cas qui compte.
        cwd = str(charge.get("cwd") or "")
        if cwd and not _sous(cwd, a.repo):
            return 0

    plafond = (a.max_agents if a.max_agents is not None
               else int(os.environ.get("TACTICUS_DISPATCH_CAP", PLAFOND_DISPATCH)))
    timeout = a.timeout if a.timeout is not None else (3.0 if a.hook else 8.0)
    ttl = a.ttl_cache if a.ttl_cache is not None else (300.0 if a.hook else 90.0)
    # `gh` a son propre budget, et il est LARGE la ou le budget general est SERRE. Les deux
    # repondent a des risques opposes : le budget general borne des sous-process LOCAUX (git,
    # dont une lenteur signale un probleme), `timeout_gh` borne un aller-retour RESEAU dont la
    # duree normale est deja de l'ordre de la seconde. Sous `--hook`, 3 s pour `gh` etaient
    # SOUS son cout mesure en concurrence -- 5 tours sur 8 aveugles (#467-r6).
    # Le mur reste tenu de deux cotes : le hook `Stop` dispose de 20 s cote Claude Code
    # (`.claude/settings.json`), et le cache de 300 s fait que `gh` n'est appele qu'une fois
    # par tranche de 5 minutes.
    timeout_gh = a.timeout_gh if a.timeout_gh is not None else (10.0 if a.hook else 12.0)
    src = Sources(repo=Path(a.repo), host=a.host, timeout=timeout,
                  avec_gh=not a.no_gh, avec_host=not a.no_host, ttl_cache=ttl,
                  timeout_gh=timeout_gh)
    if a.hook:
        # Un hook de fin de tour ne casse JAMAIS le tour. Toute panne imprevue se rabat sur le
        # silence : c'est un garde-fou, pas un maillon du chemin critique.
        try:
            journal = lire_journal(src)
            e = etat(src, plafond, journal)
            sig, ctx = signaux(e)
            if not sig:
                return 0
            ecrire_journal(src, e)
            print(json.dumps({"decision": "block",
                              "reason": _sortie_ascii(rendu_hook(sig, ctx))}))
        except Exception:                                    # noqa: BLE001
            return 0
        return 0

    journal = lire_journal(src)
    e = etat(src, plafond, journal)
    sig, ctx = signaux(e)

    if a.ack:
        ecrire_journal(src, e)
    if a.json:
        def _plat(m):
            return ({"valeur": m.valeur, "source": m.source, "erreur": m.erreur}
                    if isinstance(m, Mesure) else m)
        brut = {k: ({kk: _plat(vv) for kk, vv in v.items()} if isinstance(v, dict) else v)
                for k, v in e.items()}
        brut["flotte"].pop("chemins", None)
        brut["signaux"] = [s.cle for s in sig]
        print(_sortie_ascii(json.dumps(brut, indent=2, default=str)))
        return 0
    print(_sortie_ascii(rendu_complet(e, sig, ctx)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
