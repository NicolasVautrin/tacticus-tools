"""loop_status -- l'etat de la BOUCLE d'orchestration, DERIVE, jamais declare.

    python scripts/python/loop_status.py            # etat complet, ASCII
    python scripts/python/loop_status.py --json     # meme etat, machine
    python scripts/python/loop_status.py --hook     # lit le JSON du hook Stop sur stdin

POURQUOI CE FICHIER EXISTE (#467). Le depot est plein de gardes qui surveillent le CODE, et rien
ne surveille la BOUCLE. L'angle mort est structurel : une erreur de code produit un ROUGE, une
erreur de boucle ne produit RIEN -- un slot d'agent vide n'echoue pas, il COUTE. Le 2026-08-04 : un
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

ET UNE PANNE PORTE SON NOM (#467-r6). Un capteur qui ne sait pas nommer sa panne fait corriger la
MAUVAISE cause : l'incident du 2026-08-04 a ete diagnostique « `gh` absent du PATH » alors que le
PATH etait identique sous `pwsh` et sous le `powershell.exe -NoProfile` du hook, et que la cause
etait le BUDGET. Toutes les pannes retombaient sur la meme sentinelle `rc=127`. Elles sont
desormais distinctes A LA LECTURE, des deux cotes : `gh` (introuvable / delai depasse / erreur
systeme / non authentifie -- cf. `_cause_gh`) et git (`cause_git`). Et la sentinelle `RC_MUET`
subsiste comme SIGNAL comparable, jamais comme cause.

LA SEULE VALEUR ASSUMEE est le PLAFOND de dispatch : c'est un PARAMETRE d'orchestration, pas une
mesure. Il porte sa source en commentaire et s'ecrase par `--max-agents` / TACTICUS_DISPATCH_CAP.
"""
from __future__ import annotations

import argparse
import json
import os
import re
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
import livraison                                                       # noqa: E402
# LE FOYER DU RECENSEMENT OFFLINE (#463-r1). Le filtre du perimetre etait RECOPIE ici : trois
# derivations separees du meme critere (celle-ci, `probe_457.candidate_files`, le cliquet
# d'ecart), donc un ecart SILENCIEUX possible entre ce que ce capteur COMPTE et ce que
# `--measure-missing` JOUE. Le module est LEGER a dessein -- `ast`/`tokenize`/`argparse` y sont
# differes, et il n'importe NI `pytest` NI `repo_read` : mesure du 2026-08-07, l'import de
# `probe_457` coute 1,78 s, celui-ci ~0 une fois `json`/`subprocess` deja charges.
import probe_463r1_ecart_empreinte_offline as ecart_empreinte          # noqa: E402

REPO = Path(__file__).resolve().parents[2]

# Le motif des branches fabriquees par le harnais d'agents. Sert a BORNER le balayage des
# branches orphelines (cf. `_worktrees_et_livrees`) -- il est le meme que le perimetre par defaut
# de `nettoyer_livraison.PREFIXE_AGENT`, qui les supprime.
BRANCHE_AGENT_GLOB = livraison.BRANCHE_AGENT_GLOB

# PARAMETRE, pas mesure. Source : la conduite de campagne, elle-meme bornee par le partage du
# pump Frida. Rien dans le depot ne le DERIVE -- l'ecrire ici le rend au moins visible et
# surchargeable, au lieu de vivre dans la tete de l'orchestrateur.
#
# 5 -> 6 le 2026-08-06, puis 6 -> 5 le 2026-08-07, sur DECISION de l'utilisateur dans les deux
# sens. Les DEUX mouvements sont notes parce que ce chiffre n'a pas de derivation : son seul
# historique EST sa justification, et un lecteur qui n'y verrait qu'une valeur la croirait mesuree.
# ⚠ CE PLAFOND N'EST PAS CELUI DES RUNNERS, et les confondre est la faute a eviter : le budget
# des tests live est **4 workers pour une meme passe pytest** (rendement a 23 % des 6), il est
# PARTAGE entre tous les agents, et il ne borne PAS le nombre d'agents en vol -- une passe est
# sporadique, pas continue. Aucun des deux chiffres ne se derive de l'autre.
PLAFOND_DISPATCH = 5

# Le host tourne en local ; le littéral est celui de tous les probes du depot.
HOST_DEFAUT = "http://127.0.0.1:8765"

# Non-suivis ATTENDUS a la racine de l'arbre principal. Ils ne comptent pas comme « arbre sale ».
# Liste ASSUMEE et AFFICHEE (le rapport dit combien elle en a ecartes) : un filtre muet
# transformerait un vrai residu en silence.
UNTRACKED_CONNUS = (
    ".agent-alive",              # marqueur de vie d'un worktree d'agent (jamais versionne)
    "hs_err_pid",                # crash dumps JVM (ghidra headless)
    "logs/",                     # sorties de run
)
# ⚠ `frida/hooks/scratch/` FIGURAIT ici, decrit « modules de travail hors bundle » -- doublement
#   faux depuis #365 : le repertoire est VERSIONNE, et 66 de ses modules sont DANS le bundle.
#   L'entree ecartait donc silencieusement du rapport « arbre sale » exactement ce que la
#   doctrine demande de surveiller (« un fichier laisse non suivi n'est protege par RIEN » --
#   deux y ont deja survecu vides). Retiree par #480-r6, qui renomme le repertoire en
#   `frida/hooks/probes/`. Retirer une exclusion rend le rapport plus BAVARD, jamais moins.

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

    La garde de fidelite (`probe_467`) substitue cette classe pour jouer des etats que la
    machine ne presente pas a la demande -- host eteint, `gh` absent, git muet. Sans cette
    couture, garder le tri-etat exigerait d'eteindre le host, ce qu'aucune garde ne peut faire.
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
        # La CAUSE de la derniere panne de sous-process, par sous-commande. Ecrit depuis les
        # threads de `etat()`, mais chaque sous-commande n'est lancee qu'UNE fois par run et
        # ecrit donc SA propre cle : pas de course, et une affectation de dict est atomique.
        self._pannes: dict[str, str] = {}

    # -- processus
    #    RC_MUET : le process n'a pas repondu du tout. Ce n'est PAS un verdict -- chaque
    #    appelant le traite comme « pas mesure », jamais comme un zero. Mais ce n'est pas non
    #    plus une CAUSE : il en couvre plusieurs, et c'est exactement le vice de #467-r6 (trois
    #    pannes de `gh` derriere un `rc=127`). Le rc reste donc le SIGNAL (comparable), et la
    #    cause part en PARALLELE dans `_pannes`, d'ou `cause_git` la ressort pour l'humain.
    RC_MUET = 127

    def _run(self, argv: list[str], timeout: float | None = None,
             cle: str | None = None) -> tuple[int, str]:
        """Ne LEVE jamais. Un outil de fin de tour qui plante casse le tour."""
        budget = timeout or self.timeout
        try:
            p = subprocess.run(argv, cwd=str(self.repo), capture_output=True, text=True,
                               timeout=budget, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            # `%g` et non `%.0f` : un budget sous la seconde s'affichait << 0 s >>, ce qui se
            # lit comme un bug de l'outil plutot que comme le reglage qu'il est.
            self._note(cle, "delai depasse (%g s)" % budget)
            return self.RC_MUET, ""
        except (OSError, subprocess.SubprocessError) as ex:
            self._note(cle, "%s: %s" % (type(ex).__name__, str(ex)[:60]))
            return self.RC_MUET, ""
        return p.returncode, (p.stdout or "")

    def _note(self, cle: str | None, cause: str) -> None:
        if cle:
            self._pannes[cle] = cause

    def cause_git(self, rc: int, sous_commande: str) -> str:
        """Le NOM de la panne du dernier `git <sous_commande>`, jamais une sentinelle nue.

        Une cause ENREGISTREE veut dire que le process n'a produit AUCUN rc : elle est donc
        toute la verite, et elle prime. Sinon git a repondu, et `rc=<n>` est toute la verite.
        Aucun des deux chemins ne rend un code qui a l'air d'un verdict sans en etre un.

        La cle est la SOUS-COMMANDE, et c'est suffisant ICI : les trois seuls rc RENDUS a
        l'humain viennent de `status`, `rev-list` et `worktree`, tous distincts. `merge-base`
        est bien appele deux fois, mais son rc n'est jamais rendu -- il n'est lu que comme
        comparaison (`== 0`, `== 1`, `== RC_MUET`).
        """
        panne = self._pannes.get(sous_commande)
        if panne is not None:
            return panne
        # Reste le cas ou le rc VAUT la sentinelle sans qu'aucune cause n'ait ete enregistree :
        # une source SUBSTITUEE (les probes), ou -- theoriquement -- un vrai `git` sortant en
        # 127. On ne rend alors surtout pas `rc=127` tout nu, qui se lirait comme un verdict de
        # git : on dit l'absence de reponse ET l'absence de cause.
        return ("n'a pas repondu (rc=%d, cause non enregistree)" % rc
                if rc == self.RC_MUET else "rc=%d" % rc)

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
        return self._run(["git", "-C", str(self.repo), "--no-optional-locks", *args],
                         cle=args[0] if args else None)

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

    def gh(self, *args: str) -> tuple[int, str, str]:
        """Le SEUL poste RESEAU. Sa panne est NOMMEE, jamais reduite a un `rc=127`.

        Rend `(rc, stdout, STDERR)`. Le stderr n'est pas un supplement : c'est LE seul texte
        qui nomme la panne, et ce lecteur le JETAIT (`return p.returncode, p.stdout`). Mesure
        du 2026-08-05 sur l'exe installe (gh 2.88.1), qui tranche le sujet -- `rc=1` couvre a
        lui seul le token invalide, le depot inconnu et l'erreur d'usage :

            non authentifie   rc=4  << To get started with GitHub CLI, please run: gh auth login >>
            token invalide    rc=1  << HTTP 401: Bad credentials (https://api.github.com/graphql) >>
            depot inconnu     rc=1  << GraphQL: Could not resolve to a Repository ... >>
            commande inconnue rc=1

        LE RC NE SUFFIT DONC PAS A NOMMER LA PANNE. Une table rc -> libelle, ecrite de tete,
        aurait rendu << erreur >> pour ces trois-la : c'est le meme aveuglement qu'un `rc=127`
        partage, une couche plus haut. Cf. `_cause_gh`.

        Son budget est le SIEN (`timeout_gh`), pas le budget general : le plancher
        `max(self.timeout, 12.0)` reste proscrit (il ANNULAIT tout reglage a la baisse),
        mais un parametre distinct, lui, se regle dans les deux sens.

        POURQUOI (#467-r6), et c'est MESURE le 2026-08-04, pas suppose. Sous le
        `powershell.exe -NoProfile` qui execute le hook, `gh pr list` seul met **2,90 s**
        pour un budget de **3,00 s** ; dans le tour COMPLET, ou il court avec `git status`
        et la flotte, **5 tours sur 8** depassaient -- exactement la ligne PR
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
            # DEUX absences distinctes, et les confondre nomme la mauvaise cause : une
            # echappatoire posee sur un chemin mort n'a JAMAIS regarde le PATH, donc dire
            # « PATH + emplacements connus » serait faux -- exactement la faute de #467-r6.
            force = os.environ.get("TACTICUS_GH_EXE")
            raise RuntimeError("gh introuvable : TACTICUS_GH_EXE=%s n'existe pas" % force
                               if force else
                               "gh introuvable (PATH + emplacements connus)")
        try:
            p = subprocess.run([exe, *args], cwd=str(self.repo), capture_output=True,
                               text=True, timeout=self.timeout_gh, encoding="utf-8",
                               errors="replace")
        except subprocess.TimeoutExpired:
            raise RuntimeError("gh: delai depasse (%g s)" % self.timeout_gh) from None
        except (OSError, subprocess.SubprocessError) as ex:
            raise RuntimeError("gh: %s: %s" % (type(ex).__name__, str(ex)[:60])) from None
        return p.returncode, (p.stdout or ""), (p.stderr or "")

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
        """Agents qui TRAVAILLENT -- FILTRES par l'etat EXACT quand il est lisible.

        `fleet_board.collect(only_alive=True)` juge par le SILENCE du transcript de l'agent :
        c'est une BORNE SUPERIEURE a biais asymetrique (un agent qui vient de rendre reste compte
        « vif » jusqu'a `SILENCE_MORT_MIN`), donc `plafond - en_vol` annonce << 0 libre >> quand un
        slot l'est -- et BLOQUE le refill. Deux fois le 2026-08-10, corrige par l'utilisateur.

        On le CROISE donc avec `fleet_board.etat_par_le_transcript()`, qui lit le transcript de
        l'ORCHESTRATEUR (lancement `agentId:` contre `<task-id>` d'une `task-notification`) et rend
        l'etat SANS AUCUN SEUIL. Valide contre la verite terrain du harnais : 5/5 en vol, 9/9
        finis, 0 faux dans les deux sens, ~1 s.

        LE FILTRE VIT ICI, DANS LA SOURCE, ET PAS DANS `mesurer_flotte` -- ce n'est pas cosmetique :
        `probe_467` substitue les sources pour jouer des scenes fabriquees, et une seconde lecture
        disque cablee dans le calcul y ECHAPPERAIT. Mesure : la placer dans `mesurer_flotte` a fait
        rougir **10 epreuves** d'un coup, parce que le probe herite de cette classe et se retrouvait
        a lire la VRAIE flotte au lieu de la sienne. Le probe avait raison contre moi.

        Tri-etat : si l'etat exact n'est pas lisible, on rend `collect` tel quel -- degrade, jamais
        une certitude fabriquee.
        """
        rows = fleet_board.collect(include_done=False, only_alive=True)
        try:
            connus = {r.get("agent_id") or r.get("id") for r in rows}
            exact, _ = fleet_board.etat_par_le_transcript({c for c in connus if c})
        except Exception:                                    # noqa: BLE001
            exact = None
        if exact is None:
            return rows
        # Un agent ABSENT du transcript lu n'est PAS suppose fini : on le garde (sur-compter est
        # le defaut d'aujourd'hui, mais sous-compter ferait SUR-dispatcher, ce qui est pire).
        return [r for r in rows
                if (r.get("agent_id") or r.get("id")) in exact
                or (r.get("agent_id") or r.get("id")) is None]

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
    # LE PLAFOND PORTE SUR LES TRANCHES DISPATCHEES, PAS SUR LES AGENTS VIVANTS (correction de
    # l'utilisateur, 2026-08-06). Un solveur peut lancer ses propres sous-agents -- c'est meme
    # souhaitable, et un brief le demande parfois explicitement (`#419-r5` : « recense les accords
    # qui deviennent re-evaluables »). Les compter dans la flotte faisait afficher `6 / 6` pour
    # 5 tranches, donc RETENAIT un slot qui etait libre.
    #
    # Le discriminant est `spawnDepth`, LU dans le meta, jamais devine. Ne PAS le deriver de
    # l'absence de worktree : un agent de tete lance sans `isolation: worktree` n'en a pas non
    # plus, et serait pris pour un enfant.
    tranches = [r for r in rows if int(r.get("depth") or 1) <= 1]
    enfants = [r for r in rows if int(r.get("depth") or 1) > 1]
    n = len(tranches)
    # `src.flotte()` a DEJA croise le silence avec l'etat exact lu dans le transcript de
    # l'orchestrateur (cf. `Sources.flotte`) : ce qui arrive ici travaille vraiment.
    return {
        "en_vol": _ok(n, "fleet_board.collect(only_alive) x etat exact, spawnDepth <= 1"),
        "noms": _ok([r["name"] for r in tranches], "fleet_board"),
        "libres": _ok(max(0, plafond - n), "plafond - en_vol"),
        "plafond": plafond,
        # PUBLIE, jamais tu : un compte filtre dit ce qu'il filtre, sinon le total affiche se
        # met a diverger de ce que l'utilisateur voit dans son interface sans que rien ne
        # l'explique.
        "enfants": _ok([r["name"] for r in enfants], "spawnDepth > 1"),
        # sert a NE PAS proposer au nettoyage le worktree d'un agent qui travaille encore.
        # ⚠ Les ENFANTS y restent : un sous-agent qui aurait son propre worktree ne doit pas
        # voir celui-ci propose au nettoyage sous pretexte qu'il ne compte pas au plafond.
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


# Les codes de sortie de `gh` que l'on sait NOMMER. Table courte DELIBEREMENT : elle ne porte
# que ce qui a ete MESURE sur l'exe installe (gh 2.88.1, 2026-08-05), et la mesure dit surtout
# que `1` n'est PAS nommable -- il couvre le token invalide (HTTP 401), le depot inconnu
# (GraphQL) et l'erreur d'usage. Y ecrire « 1: erreur » donnerait un mot a la place d'une cause,
# ce qui est pire que rien : c'est ce genre d'etiquette qui a fait diagnostiquer #467-r6 a
# l'envers. Pour tous les autres codes, le NOM vient du stderr de `gh`, qui, lui, sait.
_GH_RC_NOMME = {2: "annule", 4: "non authentifie (gh auth login)"}


def _tete(texte: str) -> str:
    """La premiere ligne NON VIDE, bornee. C'est la que `gh` met son diagnostic."""
    return next((l.strip() for l in (texte or "").splitlines() if l.strip()), "")[:90]


def _cause_gh(rc: int, err: str) -> str:
    """Le NOM d'un echec de `gh`, jamais un code nu.

    Deux apports INDEPENDANTS, et il faut les deux : l'etiquette du rc quand elle existe
    (`4` = non authentifie -- mesure, pas doc recopiee), et la premiere ligne du stderr, qui
    est le seul discriminant des trois causes qui partagent `rc=1`.
    """
    nom = _GH_RC_NOMME.get(rc)
    base = "gh: %s [rc=%d]" % (nom, rc) if nom else "gh: rc=%d" % rc
    tete = _tete(err)
    return "%s -- %s" % (base, tete) if tete else base


def _prs_du_json(out: str, err: str) -> list:
    """La liste de PR, ou une LEVEE NOMMEE. `rc=0` ne suffit pas a conclure « zero PR ».

    `json.loads(out or "[]")` fabriquait un zero : sortie vide + `rc=0` devenait une liste
    vide, donc `PR ouvertes : 0` RENDU COMME UNE MESURE. C'est le zero interdit -- il n'a
    meme pas besoin d'une panne pour apparaitre, une reponse tronquee suffit.
    """
    brut = (out or "").strip()
    if not brut:
        return _leve_gh("gh: sortie VIDE malgre rc=0", err)
    try:
        prs = json.loads(brut)
    except ValueError:
        return _leve_gh("gh: sortie ILLISIBLE malgre rc=0 (%d octets)" % len(brut), err)
    if not isinstance(prs, list):
        return _leve_gh("gh: sortie INATTENDUE (%s, pas une liste)" % type(prs).__name__, err)
    return prs


def _leve_gh(quoi: str, err: str) -> list:
    tete = _tete(err)
    raise RuntimeError("%s -- %s" % (quoi, tete) if tete else quoi)


def _gh_prs(src: Sources) -> tuple[Mesure, livraison.FenetrePR, float | None, str | None]:
    """(PR ouvertes, FENETRE des PR, age du cache en s, cause du repli).

    La FENETRE est l'objet de `livraison.py`, PARTAGE avec `nettoyer_livraison` : c'est ce qui
    empeche les deux outils de la meme etape du protocole de repondre l'inverse (`#479-r4`).
    Elle porte, en plus d'un simple ensemble de refs, LA SATURATION -- si `gh` a rendu autant de
    lignes que la limite demandee, une PR plus ancienne peut y etre invisible, donc l'ABSENCE
    d'une branche n'y prouve rien. C'est `#467-r2` transforme en etat NOMME.

    UN SEUL appel `gh`, et c'est mesure : deux appels (`--state open` puis `--state merged`)
    coutaient 2,71 s a eux seuls -- plus que tout le reste de l'outil reuni. `--state all` rend
    les deux en une requete, le tri se fait ici.

    Tri-etat sur les OUVERTES : `gh` absent ou hors ligne => PAS MESURE, jamais « 0 PR » --
    c'est la difference entre « plus rien a relire » et « je n'ai pas pu demander ». Le REPLI
    (#467-r6) n'entame pas cette regle : il ne peut que remplacer une IGNORANCE par une mesure
    horodatee PORTANT une PR ouverte. Aucun chemin de cette fonction ne fabrique un zero --
    y compris le chemin SANS PANNE : un `rc=0` a sortie vide ou tronquee ne devient pas une
    liste vide, il part en PAS MESURE avec sa cause (cf. `_prs_du_json`).
    """
    cache = src.lire_cache_gh()
    repli: str | None = None
    if cache is not None:
        prs, age = cache
    else:
        try:
            rc, out, err = src.gh("pr", "list", "--state", "all",
                                  "--limit", str(livraison.LIMITE_HOOK),
                                  "--json", "number,title,headRefName,isDraft,state")
            if rc != 0:
                raise RuntimeError(_cause_gh(rc, err))
            prs, age = _prs_du_json(out, err), 0.0
            src.ecrire_cache_gh(prs)
        except Exception as e:                               # noqa: BLE001
            # 140, pas 80 : la cause NOMMEE vaut au plus 42 (etiquette + rc) + 4 + 90 (tete du
            # stderr). Trancher a 80 amputait precisement le texte de `gh` qui nomme la panne,
            # c'est-a-dire ce que ce correctif ajoute.
            cause = str(e)[:140]
            try:
                vieux = src.lire_cache_gh_repli()
            except Exception:                                # noqa: BLE001
                vieux = None
            # Le repli n'est retenu QUE s'il porte une PR ouverte : cf. `lire_cache_gh_repli`.
            if vieux is None or not [p for p in vieux[0]
                                     if (p.get("state") or "").upper() == "OPEN"]:
                return (_ko("gh pr list", cause),
                        livraison.FenetrePR(cause=cause, limite=livraison.LIMITE_HOOK),
                        None, None)
            prs, age, repli = vieux[0], vieux[1], cause
    ouvertes = [p for p in prs if (p.get("state") or "").upper() == "OPEN"]
    source = "gh pr list --state all" + (" [cache, gh muet]" if repli else "")
    # Sous repli, les PR MERGEES sont ECARTEES (fenetre NON MESUREE) : le repli sert a
    # SIGNALER, jamais a autoriser un geste destructeur. Proposer le NETTOYAGE d'un worktree
    # sur un instantane perime, c'est proposer de supprimer le travail d'un agent dont la PR
    # n'est peut-etre plus mergee. Seule la voie ANCETRE (`--merged origin/master`, git local,
    # verifiable) continue alors d'alimenter les nettoyables.
    fenetre = (livraison.FenetrePR(cause="repli sur cache : " + repli,
                                   limite=livraison.LIMITE_HOOK)
               if repli else livraison.fenetre_des_prs(prs, livraison.LIMITE_HOOK))
    return _ok(ouvertes, source), fenetre, age, repli


def _worktrees_et_livrees(src: Sources) -> tuple[tuple[int, str], tuple[int, str],
                                                 tuple[int, str], tuple[int, str]]:
    """Les worktrees d'agents, LESQUELLES de LEURS branches sont livrees, et les ORPHELINES.

    Deux appels en SEQUENCE, et c'est le bon ordre : `git branch --merged origin/master`
    parcourt les 169 branches locales du depot, dont 131 sont des branches d'agents deja
    fusionnees et sans interet -- alors qu'on n'a besoin du verdict que pour les rares
    branches encore MONTEES dans un worktree. `for-each-ref` restreint le parcours a
    celles-la. Le second appel est meme ENTIEREMENT saute quand aucun worktree d'agent
    n'existe : au repos, l'outil ne le paie pas du tout.

    LE TROISIEME APPEL EXISTE PARCE QUE LES DEUX PREMIERS SONT AVEUGLES A UN GISEMENT ENTIER
    (#479-r3). Les deux ci-dessus partent des WORKTREES : une branche d'agent dont le worktree
    a deja ete retire n'est visitee par personne, donc elle ne peut RIEN faire dire a cet outil
    -- « un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas ». Mesure du
    2026-08-05 : **27** branches deja dans `origin/master` avaient survecu ainsi, sur 39
    branches locales, parce que le `git branch -D` d'apres-merge etait un geste manuel oublie.
    Ce troisieme appel part des REFS (glob `worktree-agent-*`, borne : 406 ms contre 998 ms
    pour un `--merged` complet) et rend celles qui ne sont montees NULLE PART.

    LE QUATRIEME EXISTE PARCE QUE LE TROISIEME PORTE `--merged`, DONC NE VOIT QUE LES ANCETRES.
    Une branche SQUASH-mergee n'est ancetre de rien : elle est invisible des trois premiers
    appels, et c'est le gisement entier de `#479-r4` (mesure du 2026-08-07 : 3 ancetres sur
    20 branches locales, les 16 autres livrees par PR). Il faut donc la liste COMPLETE des
    branches d'agents locales pour pouvoir leur appliquer la voie PR -- sans quoi le
    rattrapage n'aurait rien a rattraper.
    """
    rc_wt, out_wt = src.git("worktree", "list", "--porcelain")
    if rc_wt != 0:
        return (rc_wt, out_wt), (rc_wt, ""), (rc_wt, ""), (rc_wt, "")
    orph = src.git("for-each-ref", "--merged", "origin/master", "--format=%(refname:short)",
                   "refs/heads/" + BRANCHE_AGENT_GLOB)
    toutes = src.git("for-each-ref", "--format=%(refname:short)",
                     "refs/heads/" + BRANCHE_AGENT_GLOB)
    refs = ["refs/heads/" + w["branch"] for w in _porcelain_worktrees(out_wt)
            if w["branch"] and ".claude/worktrees/agent-" in w["path"].replace("\\", "/")]
    if not refs:
        return (rc_wt, out_wt), (0, ""), orph, toutes
    return (rc_wt, out_wt), src.git("for-each-ref", "--merged", "origin/master",
                                    "--format=%(refname:short)", *refs), orph, toutes


def _session_du_worktree(chemin: str) -> str | None:
    """La boucle qui a lance l'agent de ce worktree, ou None. Ne LEVE jamais.

    L'id de l'agent est deja dans le CHEMIN (`.claude/worktrees/agent-<id>`) -- mesure du
    #467-r8 : 1 agent sur 6 le recopie inutilement dans son marqueur. On le lit donc la, et on
    demande a `fleet_board` sous quelle session son transcript a ete ecrit.
    """
    base = Path(chemin).name
    if not base.startswith("agent-"):
        return None
    try:
        return fleet_board.session_de_l_agent(base[len("agent-"):])
    except Exception:                                            # noqa: BLE001
        return None


#: Les ids dont la ligne de backlog est un COMPTEUR ROULANT : elle est mise a jour a chaque
#: livraison partielle et RESTE ouverte. Une PR qui les nomme ne les ferme donc pas, et les
#: signaler serait un faux positif A CHAQUE PASSE (#526-r2 le nomme explicitement).
#:
#: ⚠ APPARIEMENT EXACT, JAMAIS PAR PREFIXE (#526-r4). L'ecriture d'origine etait
#: `rid.startswith(RESIDUS_ROULANTS)`, ce qui silencait tous les DESCENDANTS -- **31 residus
#: OUVERTS** sous `#419-r1` a la mesure du 2026-08-08 (`#419-r1-tr10-r2`, `#419-r1-tr14-r4`,
#: ...). Chacun a sa PROPRE ligne, son propre cycle de vie et se ferme pour de bon : le
#: caractere roulant du PARENT ne se transmet pas. Le prefixe etait inoffensif tant que la
#: grammaire d'extraction ne savait pas produire ces ids ; il devient un baillon des qu'elle
#: le sait (`_RE_ID_TITRE` ci-dessous).
#:
#: ⚠ RE-JUSTIFIES PAR LA MESURE, pas par l'inertie (#526-r4) -- ET LA FENETRE DE MESURE EST
#: ELLE-MEME UN PIEGE. Sur les **200** dernieres PR mergees, `#419-r1` est nomme EXACTEMENT
#: **0** fois et tronque **9** fois : sur cette fenetre, l'entree ne masque qu'une TRONCATURE,
#: et on conclurait qu'elle est de l'inertie. Sur l'historique COMPLET (**799** PR mergees,
#: 2026-08-08), elle masque **9** occurrences EXACTES (`#419-r1 tranche 14 : ...`, PR #541,
#: #523, #518, #514, #495, #493, #492, #487, #485) pour **28** troncatures : l'entree est
#: donc PLEINEMENT justifiee, et c'est la fenetre courte qui mentait. Un compte tire d'une
#: fenetre non saturee reste un compte SUR CETTE FENETRE -- le dire fait partie de la mesure.
#: `#217` : **0** exact et **0** tronque sur les deux fenetres (voir l'inertie ci-dessous).
#: Critere LU en complement : les deux lignes portent un compte RE-DERIVE a chaque livraison
#: partielle (`~~27~~ **20 au 2026-07-26**` ; `(etait 20 ; compte RE-DERIVE ... a la livraison
#: de #419-r1-tr14)`) et restent ouvertes par construction. Ce qui change, c'est qu'un ecart
#: n'est plus muet -- il est COMPTE dans la provenance, donc une entree qui ne masque rien se
#: voit (`probe_526r2 --etat` restitue les deux colonnes).
#:
#: ⚠ `#217` EST INERTE, ET C'EST DIT PLUTOT QUE TU -- c'est une RACINE NUE, que `_RE_ID_TITRE`
#: ne produit JAMAIS (l'exigence anti-numero-de-PR impose au moins un segment). Aucun titre ne
#: peut donc la faire tirer, dans aucun sens. Elle est CONSERVEE, parce qu'elle redeviendrait
#: effective si la grammaire admettait un jour les racines nues, et parce que la retirer
#: n'econnomise rien ; mais `probe_526r2` etape 5 la RECENSE et l'imprime a chaque passe
#: (`_roulants_inertes`), et exige qu'au moins une entree reste EFFECTIVE. Une entree inerte
#: n'est pas une faute -- la taire en est une, et c'est exactement l'angle mort ou `#419-r1` a
#: passe neuf tours a masquer une troncature en se faisant passer pour un compteur roulant.
RESIDUS_ROULANTS = ("#217", "#419-r1")

#: La 1re cellule du tableau, en POSITION DE DEFINITION. Grammaire ELARGIE (#526-r4) : un
#: segment d'id n'est PAS necessairement `r<chiffres>`. Mesure du 2026-08-08 sur la section
#: ouverte : **212 des 619** premieres cellules sont hors de l'ancienne grammaire
#: `#\d+(?:-r\d+)*` -- des FAMILLES entieres (`#419-r1-tr14-...`, `#462-r4b-...`, `#446-r3b`,
#: `#350-r3a`), plus les racines non numeriques (`#BF-chance`, `#PAI-c`, `#haze-ord`). Effet
#: MESURE de l'elargissement : residus ouverts VUS **191 -> 278**, et **+1 signal reel** que
#: personne ne pouvait voir (`#175-r`, livre par la PR #825 et toujours ouvert).
#: Le `~~` d'une ligne fermee ne matche pas -- c'est ce qui distingue ouvert de ferme.
_RE_ID_DEFINI = r"^\|\s*(#[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\s*\|"

#: L'id tel qu'un TITRE de PR le nomme. DEUX exigences, et chacune repare une faute mesuree :
#:
#: 1. LA BORNE DROITE `(?![-\w])`, ET SURTOUT LA LARGEUR (#526-r4). Sans elles,
#:    `#\d+(?:-r\d+)+` s'arretait au premier segment non-`r<chiffres>` et FABRIQUAIT un
#:    ANCETRE : sur `#462-r4b-r3-r1` le `+` s'arrete devant le `b` et rend `#462-r4`, un id qui
#:    EXISTE et qui est OUVERT. Mesure sur les **200** dernieres PR mergees : **24** extractions
#:    tronquees en 3 familles, soit **14 des 18** signaux emis qui etaient de purs faux
#:    positifs -- c'est la cause du `#462-r4 (PR #724)` remonte par le hook `Stop`. Sur
#:    l'historique COMPLET (**799** PR) : **88** troncatures, **10** familles.
#:    ⚠ LA BORNE SEULE NE REPARE PAS : sous la grammaire ELARGIE, `-r4b` est un segment
#:    ordinaire, donc c'est la LARGEUR qui dissout la troncature. Ce que la borne garde encore,
#:    c'est le suffixe COLLE hors classe (`#116-e_bis` ne doit pas rendre `#116-e`) -- les deux
#:    crans sont eprouves SEPAREMENT par `probe_526r2` etape 5 (a1) et (a2), justement pour que
#:    l'un ne passe pas pour la cause du vert de l'autre.
#: 2. AU MOINS UN SEGMENT (`+`, pas `*`), et c'est ce qui separe un id d'un NUMERO DE PR : un
#:    titre cite couramment `#832`, qui serait un id de racine parfaitement valide. Exiger le
#:    segment ecarte cette collision par construction. Une racine nue n'est donc jamais
#:    signalee -- borne assumee, nommee ici plutot que decouverte plus tard.
_RE_ID_TITRE = r"#[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+(?![-\w])"

#: Titre de la section du backlog qui porte les residus OUVERTS. Une ligne qui n'y est plus est
#: fermee, par construction.
#:
#: ⚠ AVEC SON ACCENT, et c'est une faute deja commise ici : ecrit `## Taches ouvertes`, il ne
#: matchait rien, et le poste rendait PAS MESURE en permanence -- un signal muet qu'on aurait
#: pu livrer sans le voir. C'est le tri-etat qui l'a montre (la cause `section introuvable`
#: etait NOMMEE) ; une liste vide l'aurait cache. La borne suivante est le TEMOIN NON NUL de
#: `probe_526r2` : le signal doit etre vu TIRER avant d'etre cru muet.
_SECTION_OUVERTE = "## Tâches ouvertes"


def _residus_livres(src: Sources, fenetre) -> "Mesure":
    """Les residus qu'une PR MERGEE nomme dans son TITRE et dont la ligne est TOUJOURS ouverte.

    ------------------------------------------------------------------------------------
    POURQUOI ICI, ET PAS DANS UN CLIQUET (#526-r2)
    ------------------------------------------------------------------------------------
    La fraicheur d'un residu n'est pas derivable, et la cause est en AMONT : une PR qui ferme
    un residu ne retire pas sa ligne du backlog, et rien ne l'y oblige. Mesure du 2026-08-07 :
    10 PERIME-CANDIDAT sur 278 ; re-mesure le 2026-08-08 : **19 sur 285**. La derive a donc
    DOUBLE en un jour -- notre cadence de livraison l'alimente plus vite qu'on ne la resorbe.

    UN CLIQUET NE PEUT PAS FERMER CE GISEMENT, et ce n'est pas un arbitrage de cout : pour
    partir de zero il faudrait NETTOYER les 19 lignes d'un coup, c'est-a-dire une modification
    de MASSE de `docs/rl/backlog.md` -- que `CLAUDE.md` interdit, mesure a l'appui (36 des 40
    dernieres PR mergees y touchent ; une passe qui reecrit des lignes de tableau partout ferait
    conflit avec chaque PR en vol). Et un cliquet a SEUIL se degraderait en silence.

    D'ou un signal RESTITUE plutot qu'un verdict : `loop_status` tourne au hook `Stop`, donc
    JUSTE APRES un merge -- au moment ou il reste UNE ligne a retirer, pas dix-neuf. C'est le
    << au fil de l'eau, jamais en masse >> que la doctrine prescrit deja pour ce fichier,
    applique a la fraicheur. Cout : ZERO appel supplementaire, la fenetre PR est deja lue.

    LE CRITERE EST LE TITRE, jamais le corps ni le message de commit -- mesure #526 : `git log`
    corps compris rend 187/278 et ne discrimine RIEN, parce qu'un residu est cite par le commit
    qui l'OUVRE. Le titre d'une PR mergee, lui, nomme ce qu'elle a LIVRE (10/278, dont 6
    invisibles de tout autre signal).

    LA GRAMMAIRE DE L'ID EST LE POINT FAIBLE, ET ELLE A DEJA MENTI (#526-r4) -- voir
    `_RE_ID_TITRE` / `_RE_ID_DEFINI` : sans borne droite, elle FABRIQUAIT l'ancetre d'un id
    (14 des 18 signaux emis etaient ce faux positif) ; trop etroite, elle ne voyait pas
    87 residus ouverts sur 278. Les deux sont mesurees et corrigees la-haut.
    """
    m = _residus_nommes(src, fenetre)
    if not m.mesuree:
        return m
    retenus, ecartes = m.valeur["retenus"], m.valeur["ecartes_roulants"]
    # UN ECART NE DOIT PAS ETRE MUET : une entree de `RESIDUS_ROULANTS` qui ne masque RIEN est
    # de l'inertie, et c'est exactement ce que #526-r4 a trouve. Le compte part dans la
    # provenance, donc il se lit meme quand la liste retenue est vide.
    src_txt = "titres de PR mergees x backlog `%s`" % _SECTION_OUVERTE
    if ecartes:
        src_txt += " -- %d ecarte(s) par RESIDUS_ROULANTS (%s)" % (
            len(ecartes), ", ".join(sorted({t["residu"] for t in ecartes})))
    return _ok(retenus, src_txt)


def _residus_nommes(src: Sources, fenetre) -> "Mesure":
    """Ventile les ids nommes par un titre de PR mergee : `{retenus, ecartes_roulants}`.

    SEPARE de `_residus_livres` pour que le cran << les COMPTEURS ROULANTS sont ecartes >>
    soit OBSERVABLE : tant que le filtre etait interne, aucune epreuve ne pouvait distinguer
    << l'entree a masque un id >> de << aucun id ne correspondait >>, et c'est precisement
    dans cet angle mort que `#419-r1` a passe neuf tours a masquer une TRONCATURE (#526-r4).
    """
    if not fenetre.mesuree:
        return _ko("residus livres", fenetre.cause or "PR pas mesurees")
    definis = _residus_ouverts(src)
    if not definis.mesuree:
        return definis
    titres = _titres_mergees(src, fenetre)
    if not titres.mesuree:
        return titres
    trouves, ecartes = [], []
    for titre, num in titres.valeur:
        for rid in sorted(set(re.findall(_RE_ID_TITRE, titre))):
            if rid not in definis.valeur:
                continue
            item = {"residu": rid, "pr": num, "titre": titre[:70]}
            (ecartes if rid in RESIDUS_ROULANTS else trouves).append(item)
    vus, uniq = set(), []
    for t in trouves:
        if t["residu"] not in vus:
            vus.add(t["residu"])
            uniq.append(t)
    return _ok({"retenus": uniq, "ecartes_roulants": ecartes},
               "titres de PR mergees x backlog `%s`" % _SECTION_OUVERTE)


def _residus_ouverts(src: Sources) -> "Mesure":
    """Les ids DEFINIS dans la section ouverte du backlog. FOYER UNIQUE de cette grammaire.

    Elle vivait en DOUBLE -- ici et dans `probe_526r2_fraicheur_backlog.py::_residus_ouverts`,
    recopiee -- donc le probe pouvait rester vert sur une grammaire que le lecteur n'employait
    plus, ou l'inverse. Un cran qui juge une regle qu'il a lui-meme recopiee ne juge rien.
    """
    chemin = src.repo / "docs" / "rl" / "backlog.md"
    try:
        texte = chemin.read_text(encoding="utf-8")
    except OSError as ex:
        return _ko("residus ouverts", "backlog.md illisible : %s" % str(ex)[:70])
    tete = texte.split(_SECTION_OUVERTE, 1)
    if len(tete) != 2:
        # La section n'existe pas sous ce nom : on ne DEVINE pas un perimetre, on le dit.
        return _ko("residus ouverts", "section %r introuvable dans backlog.md" % _SECTION_OUVERTE)
    #: En POSITION DE DEFINITION (1re cellule du tableau) -- jamais une simple mention, qui
    #: rougirait sur presque tous les renvois croises (critere de `probe_468`).
    return _ok(set(re.findall(_RE_ID_DEFINI, tete[1], re.MULTILINE)),
               "1res cellules de `%s`" % _SECTION_OUVERTE)


def _titres_mergees(src: Sources, fenetre) -> "Mesure":
    """`[(titre, numero)]` des PR MERGEES de la fenetre. NON MESURE si le titre n'a pas ete lu.

    On ne relance PAS `gh` pour le titre -- ce lecteur court sous un budget de 3 s (#467-r6,
    ou 2,90 s pour 3,00 s rendait 5 tours sur 8 aveugles). Le titre est pris dans le cache que
    `Sources` tient deja.

    ⚠ SON ABSENCE EST UNE PANNE, PAS UN CONSTAT (#526-r4). Ce lecteur rendait une liste VIDE
    en s'expliquant << le signal se tait, il ne se trompe pas >> -- or il se trompait : une
    fenetre sans champ `title` remontait jusqu'a `probe_526r2 --etat`, qui imprimait
    << 0 residu(s) ... (aucun -- mesure, pas suppose) >>. MESURE le 2026-08-08 : la voie
    manuelle rendait **0** et la voie du hook **4**, le meme jour, sur le meme depot. Un
    capteur qui se tait DOIT dire qu'il se tait ; un silence rendu comme une liste vide est
    lu comme une mesure des qu'il traverse un appelant de plus.
    """
    brutes = [p for p in (getattr(fenetre, "brutes", None) or [])
              if (p.get("state") or "").upper() == "MERGED"]
    if brutes and not any("title" in p for p in brutes):
        return _ko("titres de PR mergees",
                   "le champ `title` n'a pas ete demande a `gh` (%d PR mergees dans la "
                   "fenetre, aucune ne le porte)" % len(brutes))
    return _ok([(p.get("title") or "", p.get("number")) for p in brutes], "cache gh")


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
        (rc_wt, out_wt), (rc_mg, out_mg), (rc_or, out_or), (rc_to, out_to) = f_wt_mg.result()
        pr_ouvertes, fenetre_pr, age_gh, gh_repli = f_gh.result()
    d["gh_age_s"] = age_gh
    d["gh_repli"] = gh_repli

    if rc != 0:
        # `cause_git` et non `rc=%d` : sous `--hook`, ce poste dispose de 3 s et il a deja ete
        # mesure a 4,29 s sous charge (#467). Le lecteur doit pouvoir distinguer « budget
        # depasse » de « git absent » -- c'est la lecon de #467-r6, sur l'autre capteur.
        for k in ("branche", "avance", "retard", "suivis_sales", "non_suivis",
                  "non_suivis_inconnus"):
            d[k] = _ko("git status --porcelain=v2", src.cause_git(rc, "status"))
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
                           if rc2 == 0
                           else _ko("git rev-list", src.cause_git(rc2, "rev-list")))

        # -- et le sens INVERSE, qui manquait (#467-r7). L'AVANCE seule est rassurante a tort :
        # mesure le 2026-08-14, l'arbre principal etait **56 commits EN RETARD** et cette
        # section affichait `0 commit(s) non pousse(s)`, donc rien. Cout constate : un audit
        # GENERE lu a un compte perime (`171/3` contre `172/2`), `probe_313` rendu `rc=6` alors
        # qu'il est VERT, et un brief d'agent entier demandant de construire un canal deja livre.
        # Le retard se lit sans AUCUN fetch -- c'est la meme ref locale `origin/master` que
        # ci-dessus, prise dans l'autre sens ; le commentaire du dessus n'a jamais interdit que
        # ca, il disait seulement qu'on ne rafraichit pas la ref.
        # ⚠ C'est donc un PLANCHER, jamais un inventaire : sans fetch, `origin/master` peut
        # elle-meme dater. `0` ne prouve pas « a jour », il prouve « rien de connu en retard ».
        if entetes.get("branch.upstream") == "origin/master" and " -" in ab:
            d["retard"] = _ok(int(ab.split()[1][1:]), "git status v2 # branch.ab")
        else:
            rc3, out3 = src.git("rev-list", "--count", "HEAD..origin/master")
            d["retard"] = (_ok(int(out3.strip() or 0), "git rev-list HEAD..origin/master")
                           if rc3 == 0
                           else _ko("git rev-list", src.cause_git(rc3, "rev-list")))

    # -- worktrees d'agents, et lesquels sont NETTOYABLES
    if rc_wt != 0:
        d["worktrees"] = _ko("git worktree list", src.cause_git(rc_wt, "worktree"))
        d["nettoyables"] = _ko("git worktree list", src.cause_git(rc_wt, "worktree"))
        branches_agents: dict[str, str] = {}
    else:
        wts = [w for w in _porcelain_worktrees(out_wt)
               if ".claude/worktrees/agent-" in w["path"].replace("\\", "/")]
        d["worktrees"] = _ok([w["path"] for w in wts], "git worktree list --porcelain")
        branches_agents = {w["branch"]: w["path"] for w in wts if w["branch"]}

    # `--merged origin/master` = le tip de la branche est ANCETRE. Voie LOCALE et verifiable,
    # mais AVEUGLE au squash-merge -- qui est notre SEUL mode de merge. Le rattrapage par la PR
    # vit dans `livraison.classer`, PARTAGE avec `nettoyer_livraison` (#479-r4).
    ancetres = ({b.strip() for b in out_mg.splitlines() if b.strip()} if rc_mg == 0
                else None)
    cause_anc = src.cause_git(rc_mg, "for-each-ref") if rc_mg != 0 else ""

    d["pr_ouvertes"] = pr_ouvertes
    d["portee_pr"] = fenetre_pr.portee()
    d["residus_livres"] = _residus_livres(src, fenetre_pr)
    if d["worktrees"].mesuree:
        verdicts = livraison.classer(sorted(branches_agents), ancetres, fenetre_pr,
                                     cause_ancetres=cause_anc)
        nett, gardes = [], []
        for br, chemin in sorted(branches_agents.items()):
            if not verdicts[br].livree:
                continue
            # << Livree >> n'est pas << a retirer >> : le second terme du protocole n'est
            # derivable d'aucun etat git (#467-r8). Une marque DEPOSEE dans le worktree le
            # porte -- et le worktree garde reste DIT, jamais efface du rapport.
            raison = livraison.garde_marquee(chemin)
            (gardes if raison is not None else nett).append(
                {"branche": br, "chemin": chemin, "voie": verdicts[br].voie,
                 # LA BOUCLE qui a lance cet agent, DERIVEE (#467-r8). Publiee, jamais
                 # transformee en verdict : ce lecteur ne connait pas SA propre session, donc
                 # il ne peut pas dire << la mienne >> -- et inventer cette attribution est
                 # exactement la faute que le residu a mesuree (un worktree defendu quatre
                 # tours sur une propriete supposee, qui s'est revelee FAUSSE).
                 "session": _session_du_worktree(chemin),
                 **({"raison": raison} if raison is not None else {})})
        if not nett and not gardes and ancetres is None and not fenetre_pr.mesuree:
            # AUCUNE des deux voies n'a repondu : une liste vide se lirait « rien a nettoyer ».
            d["nettoyables"] = _ko("nettoyables", "ni --merged ni gh n'ont repondu")
            d["gardes"] = _ko("gardes", "ni --merged ni gh n'ont repondu")
        else:
            d["nettoyables"] = _ok(nett, "livraison.classer (ancetre + PR mergee)")
            d["gardes"] = _ok(gardes, "livraison.garde_marquee (%s)" % livraison.MARQUE_GARDE)
    else:
        d["nettoyables"] = _ko("nettoyables", "worktrees non mesures")
        d["gardes"] = _ko("gardes", "worktrees non mesures")

    # -- branches d'agents LIVREES et montees NULLE PART (#479-r3). Le poste ci-dessus ne peut
    #    pas les voir : il part des worktrees. Ce sont elles qui s'accumulaient en silence.
    #    ⚠ DEUX corrections ici, l'une et l'autre mesurees le 2026-08-07 :
    #    (a) le critere passe par `livraison.classer`, donc une branche SQUASH-mergee y entre
    #        enfin -- l'ancestralite seule en voyait 3 sur 20 ;
    #    (b) la protection ne se lit plus sur la seule ligne `branch` du porcelain, mais aussi
    #        sur la CONVENTION DE NOM du repertoire (`livraison.branches_protegees_par_worktree`) :
    #        un agent qui RENOMME sa branche laisse `worktree-agent-<id>` non montee alors qu'il
    #        travaille encore, et l'ancienne voie l'aurait declaree orpheline.
    if not d["worktrees"].mesuree:
        d["branches_orphelines"] = _ko("branches orphelines", "worktrees non mesures")
    else:
        protegees = livraison.branches_protegees_par_worktree(out_wt)
        # Le glob `--merged` ne rend QUE des ancetres. Le periMETRE est donc la liste COMPLETE
        # des branches d'agents locales (4e appel) -- une branche squash-mergee n'apparait dans
        # aucune des deux autres sources, et un recenseur ne peut pas rendre zero sur ce qu'il
        # ne visite pas.
        vues = {b.strip() for b in out_or.splitlines() if b.strip()} if rc_or == 0 else set()
        if rc_to != 0:
            d["branches_orphelines"] = _ko("git for-each-ref (toutes)",
                                           src.cause_git(rc_to, "for-each-ref"))
        else:
            cand = sorted({b.strip() for b in out_to.splitlines() if b.strip()} - protegees)
            verd = livraison.classer(cand, vues if rc_or == 0 else None, fenetre_pr,
                                     cause_ancetres=src.cause_git(rc_or, "for-each-ref"))
            d["branches_orphelines"] = _ok(
                [b for b in cand if verd[b].livree],
                "livraison.classer (ancetre + PR mergee) sur " + BRANCHE_AGENT_GLOB)
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


# ------------------------------------------------------------------ EMPREINTE (#486-r15)
#: Le format attendu de `scripts/ratchets-457-footprints.json`. RECOPIE et non importe : tirer
#: `probe_457` ici traine `pytest` et `repo_read` dans un outil qui court sous 3 s. Le prix de la
#: recopie est borne -- une divergence ne peut que faire SIGNALER a tort (sur-alerte), jamais
#: taire ; et `test_486r15_empreinte_par_entree_offline` la confronte a la constante source.
FORMAT_EMPREINTE_ATTENDU = 2


def mesurer_empreinte(src: Sources) -> dict:
    """La COUVERTURE de l'empreinte de `probe_457` -- le capteur qui manquait.

    LE GISEMENT. `probe_457 --since` ne peut retirer un test du perimetre que s'il a une entree
    d'empreinte : sans elle, le test est << jamais mesure >> et se rejoue. La selection se DEGRADE
    donc continument, et cette degradation etait MUETTE -- l'outil imprimait bien sa raison, mais
    dans une ligne noyee dans sa sortie, que personne n'a lue pendant 3 jours et ~40 commits
    pendant que `--since` rendait 220/220. Un capteur muet est un garde-fou mort (#467).

    BON MARCHE : deux `git ls-files` et une lecture JSON. Aucun graphe, aucun `ast.parse` -- le
    hook `Stop` court sous 3 s.

    TRI-ETAT : git muet ou empreinte illisible rendent PAS MESURE, jamais un zero. Un << 0 fichier
    couvert >> fabrique se lirait comme une alarme fausse, et un << tout va bien >> fabrique
    ferait taire l'outil sur exactement le defaut qu'il existe pour voir.
    """
    d: dict = {}
    rc, out = src.git("ls-files", ecart_empreinte.TESTS_DIR)
    if rc != 0:
        d["couverture"] = _ko("git ls-files " + ecart_empreinte.TESTS_DIR,
                              src.cause_git(rc, "ls-files"))
        return d
    # #463-r1 : le FILTRE vient du foyer, l'APPEL a git reste ici (cache TTL + tri-etat propres a
    # cet outil). C'est ce partage-la qui supprime la recopie sans imposer une facon d'appeler git.
    perimetre = ecart_empreinte.perimetre_offline(out)
    if not perimetre:
        # Un depot SANS fichier de test offline ne dit RIEN sur l'empreinte : il n'y a pas de
        # couverture a mesurer. PAS MESURE, donc du CONTEXTE -- surtout pas un signal.
        # Le PERIMETRE EFFONDRE, lui, reste garde la ou il a un sens : `probe_457` rend
        # `FAIL shard VIDE`. Le dupliquer ici ferait parler cet outil dans tout depot de
        # travail jetable, et un outil qui alarme a tort se fait desarmer.
        d["couverture"] = _ko("git ls-files " + ecart_empreinte.TESTS_DIR,
                              "aucun fichier de test offline dans ce checkout")
        return d
    try:
        emp = json.loads((src.repo / ecart_empreinte.EMPREINTE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        d["couverture"] = _ko(ecart_empreinte.EMPREINTE,
                              "%s: %s" % (type(ex).__name__, str(ex)[:50]))
        return d
    # #463-r1 : la VENTILATION remplace le compte d'INTERSECTION. `couverts` ne voyait qu'un sens
    # -- une empreinte portant des entrees FANTOMES (fichier supprime, ou RENOMME en `_live.py`)
    # affichait `N/N` et se taisait, parce qu'une intersection ne montre jamais ce qui deborde.
    # `couverts` reste RENDU pour le libelle, mais il est DERIVE des manquants, plus recompte.
    ecart = ecart_empreinte.ventiler(perimetre, emp.get("par_test") or {})
    d["couverture"] = _ok({"format": emp.get("_format"),
                           "couverts": len(perimetre) - len(ecart["manquants"]),
                           "perimetre": len(perimetre),
                           "manquants": ecart["manquants"],
                           "fantomes": ecart["fantomes"]},
                          ecart_empreinte.EMPREINTE + " vs git ls-files")
    return d


# ------------------------------------------------------------------ etat complet
def etat(src: Sources, plafond: int) -> dict:
    """Toutes les mesures, en parallele. Aucune ne peut faire echouer les autres."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        f_flotte = ex.submit(mesurer_flotte, src, plafond)
        f_livr = ex.submit(mesurer_livraison, src)
        f_harnais = ex.submit(mesurer_harnais, src)
        f_emp = ex.submit(mesurer_empreinte, src)
        flotte, livr, harnais = f_flotte.result(), f_livr.result(), f_harnais.result()
        empreinte = f_emp.result()

    # JONCTION, apres coup pour que les trois mesures restent independantes : un agent qui
    # TRAVAILLE garde son worktree meme si sa branche est deja mergee (il peut encore
    # committer). Le proposer au nettoyage, c'est proposer de le tuer.
    if livr["nettoyables"].mesuree and flotte["chemins"]:
        garde = [w for w in livr["nettoyables"].valeur
                 if str(Path(w["chemin"]).resolve()).lower() not in flotte["chemins"]]
        livr["nettoyables"] = _ok(garde, livr["nettoyables"].source + " - agents en vol")
    return {"flotte": flotte, "livraison": livr, "harnais": harnais,
            "empreinte": empreinte, "repo": str(src.repo)}


# ------------------------------------------------------------------ signaux
@dataclass
class Signal:
    cle: str
    ligne: str


def signaux(e: dict) -> tuple[list[Signal], list[str]]:
    """Rend (ce qui APPELLE UNE ACTION, ce qui est du CONTEXTE).

    Un signal est ACTIONNABLE : il nomme un geste que l'orchestrateur peut poser tout de suite.
    Le contexte accompagne les signaux quand il y en a, et ne parle jamais seul -- c'est ce qui
    fait que l'outil se TAIT quand tout va bien.
    """
    sig: list[Signal] = []
    ctx: list[str] = []
    fl, lv, ha = e["flotte"], e["livraison"], e["harnais"]

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

    # UN CAPTEUR MORT NE DOIT PAS SE LIRE << rien a signaler >>. La flotte avait ce garde
    # (juste au-dessus), la LIVRAISON ne l'avait pas : un `git status` qui depasse les 3 s du
    # hook rendait `push`, `sale` et `nettoyage` muets D'UN BLOC, sans un mot. C'est #467-r6
    # sur l'autre capteur -- la panne existait, elle est meme NOMMEE depuis, mais personne ne
    # la lisait.
    #
    # POURQUOI ICI ET PAS POUR `gh` : le critere n'est pas le capteur, c'est CE QU'IL PORTE.
    # L'axe git porte trois SIGNAUX (des gestes a poser) ; `gh` ne porte que du CONTEXTE (la
    # ligne PR), dont l'ignorance s'affiche deja a cote des chiffres et n'appelle aucun geste.
    # Alarmer sur une panne reseau a chaque tour ferait desarmer le hook -- exactement ce que
    # ce fichier evite depuis le debut.
    morts = [(c, lv[c].erreur) for c in ("avance", "retard", "suivis_sales", "worktrees")
             if not lv[c].mesuree]
    if morts:
        sig.append(Signal("livraison-inconnue", "livraison NON MESUREE : %s"
                          % ", ".join("%s (%s)" % (c, e) for c, e in morts)))

    if avance:
        sig.append(Signal("push", "%d commit(s) non pousse(s) sur origin/master (branche %s)"
                          % (avance, lv["branche"].txt())))
    retard = lv["retard"].valeur if lv["retard"].mesuree else 0
    if retard:
        sig.append(Signal(
            "retard",
            "arbre EN RETARD de %d commit(s) sur origin/master -- toute mesure prise ici "
            "(audit genere, cliquet, brief d'agent) porte sur un arbre PERIME. "
            "`git merge --ff-only origin/master` AVANT de conclure quoi que ce soit."
            % retard))
    if lv["suivis_sales"].mesuree and lv["suivis_sales"].valeur:
        n = len(lv["suivis_sales"].valeur)
        sig.append(Signal("sale", "%d fichier(s) SUIVI(S) modifie(s) non commis : %s"
                          % (n, ", ".join(lv["suivis_sales"].valeur[:4])
                             + (" ..." if n > 4 else ""))))
    if lv["nettoyables"].mesuree and lv["nettoyables"].valeur:
        noms = ", ".join(w["branche"][-12:] for w in lv["nettoyables"].valeur[:5])
        sig.append(Signal("nettoyage", "%d worktree(s) d'agent NETTOYABLE(S) (branche livree) : %s"
                          % (len(lv["nettoyables"].valeur), noms)))
    orph = lv.get("branches_orphelines")
    if orph is not None and orph.mesuree and orph.valeur:
        sig.append(Signal(
            "branches-orphelines",
            "%d branche(s) d'agent LIVREE(S) et montee(s) nulle part : %s -- "
            "`python scripts/python/nettoyer_livraison.py` (DRY-RUN par defaut)"
            % (len(orph.valeur), ", ".join(b[-12:] for b in orph.valeur[:5]))))
    rl = lv.get("residus_livres")
    if rl is not None and rl.mesuree and rl.valeur:
        # AU FIL DE L'EAU : ce signal arrive juste apres le merge, quand il reste UNE ligne a
        # retirer. C'est ce qui evite la passe de masse sur `backlog.md` (#526-r2).
        sig.append(Signal(
            "backlog",
            "%d residu(s) nomme(s) par une PR MERGEE et TOUJOURS ouverts dans backlog.md : %s"
            % (len(rl.valeur),
               ", ".join("%s (PR #%s)" % (t["residu"], t["pr"]) for t in rl.valeur[:5]))))
    if lv["pr_ouvertes"].mesuree and lv["pr_ouvertes"].valeur:
        ctx.append("PR ouvertes : %d%s (%s)"
                   % (len(lv["pr_ouvertes"].valeur), _age_gh(lv),
                      ", ".join("#%s" % p.get("number") for p in lv["pr_ouvertes"].valeur[:8])))
    elif not lv["pr_ouvertes"].mesuree:
        ctx.append("PR : %s" % lv["pr_ouvertes"].txt())

    if ha["drain"].mesuree and ha["drain"].valeur:
        sig.append(Signal("drain", "mode DRAIN ARME -- la creation de runner est refusee"))
    if not ha["session"].mesuree:
        ctx.append("harnais : %s" % ha["session"].erreur)
    elif ha["session"].valeur is None:
        sig.append(Signal("session", "AUCUNE session Frida -- tout RPC/runner echouera"))
    else:
        s = ha["session"].valeur
        ctx.append("session %s %s (pid %s)" % (s.get("id"), s.get("status"), s.get("pid")))

    # -- EMPREINTE de `probe_457` (#486-r15, ventilee par #463-r1). ACTIONNABLE, et la
    #    degradation est INVISIBLE autrement -- elle ne se lit que dans une ligne de sortie du
    #    probe, que personne n'a lue pendant 3 jours et ~40 commits.
    #    HORS campagne aussi : c'est un fait sur le DEPOT, pas sur la boucle, et le silence
    #    reste tenu par le fait qu'un depot sain ne produit AUCUNE de ces lignes.
    #
    #    ⚠ IL NOMME LES FICHIERS ET NE TRANCHE PAS (#463-r1). Ce signal disait « regenerer :
    #    --measure-missing », c'est-a-dire qu'il CHOISISSAIT la mesure. Le contre-cas est mesure
    #    et date du 2026-08-07 (`40917cd0`) : le meme ecart `N-1/N` appelait la reponse INVERSE
    #    -- un test LIVE mal nomme, a RENOMMER. L'avoir mesure aurait grave une empreinte derivee
    #    d'un run live, donc un FAUX VERT durable. Le discriminant « ce fichier est-il offline ? »
    #    porte sur l'INTENTION : il n'est pas mecanisable, et un capteur qui le tranche a la place
    #    de l'humain fabrique exactement le defaut qu'il surveille.
    emp = e.get("empreinte") or {}
    cov = emp.get("couverture")
    if cov is not None and not cov.mesuree:
        ctx.append("empreinte 457 : %s" % cov.txt())
    elif cov is not None:
        v = cov.valeur
        if v["format"] != FORMAT_EMPREINTE_ATTENDU:
            sig.append(Signal(
                "empreinte-format",
                "empreinte 457 au format %s (attendu %d) -- `--since` refuse de s'en servir et "
                "rejoue TOUT ; regenerer : cd scripts/python ; $env:TACTICUS_ALLOW_RATCHETS=1 ; "
                "python probe_457_offline_tests_green.py --measure"
                % (v["format"], FORMAT_EMPREINTE_ATTENDU)))
        else:
            if v["manquants"]:
                sig.append(Signal(
                    "empreinte",
                    "empreinte 457 : %d fichier(s) offline NON MESURE(S) -- ils se rejouent "
                    "TOUJOURS sous `--since` : %s%s. DEUX issues, a TRANCHER par un humain : "
                    "(a) reellement offline -> le mesurer (`--measure-missing`) ; (b) il reclame "
                    "une fixture live -> le RENOMMER en `*_live.py`. L'indice, LU dans les "
                    "signatures : python probe_463r1_ecart_empreinte_offline.py"
                    % (len(v["manquants"]), ", ".join(v["manquants"][:3]),
                       "" if len(v["manquants"]) <= 3 else " (+%d)" % (len(v["manquants"]) - 3))))
            if v["fantomes"]:
                sig.append(Signal(
                    "empreinte-fantome",
                    "empreinte 457 : %d entree(s) FANTOME(S) -- mesurees, mais ABSENTES du "
                    "perimetre offline (fichier supprime, ou RENOMME en `_live.py`) : %s%s. "
                    "`--measure-missing` ne les purge PAS ; seul `--measure` le fait."
                    % (len(v["fantomes"]), ", ".join(v["fantomes"][:3]),
                       "" if len(v["fantomes"]) <= 3 else " (+%d)" % (len(v["fantomes"]) - 3))))

    lr = ha["live_runners"]
    if lr.mesuree and lr.valeur and not en_vol:
        sig.append(Signal("orphelins", "%d runner(s) VIVANT(S) sans aucun agent en vol -- "
                                       "candidats orphelins" % lr.valeur))
    ctx.append("liveRunners %s (budget partage des 4-en-parallele)" % lr.txt())
    return sig, ctx


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
    fl, lv, ha = e["flotte"], e["livraison"], e["harnais"]
    L = ["[boucle] %s  (%s)" % (e["repo"], lv["branche"].txt())]
    L.append("")
    L.append("FLOTTE     en vol %s / %d -> %s libre(s)"
             % (fl["en_vol"].txt(), fl["plafond"], fl["libres"].txt()))
    if fl["noms"].mesuree:
        for n in fl["noms"].valeur:
            L.append("             . %s" % n[:64])
    # Les sous-agents sont AFFICHES et NE COMPTENT PAS -- publier ce qu'on filtre est ce qui
    # empeche l'ecart avec l'interface de passer pour un bug de comptage.
    if fl.get("enfants") is not None and fl["enfants"].mesuree and fl["enfants"].valeur:
        L.append("           + %d sous-agent(s), HORS plafond :" % len(fl["enfants"].valeur))
        for n in fl["enfants"].valeur:
            L.append("             . %s" % n[:64])
    L.append("LIVRAISON  %s commit(s) non pousse(s) sur origin/master" % lv["avance"].txt())
    if not lv["retard"].mesuree or lv["retard"].valeur:
        L.append("           EN RETARD de %s commit(s) sur origin/master (plancher : ref locale,"
                 " pas de fetch)" % lv["retard"].txt())
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
                L.append("             . %s  [%s]%s"
                         % (w["branche"], w["voie"],
                            "  boucle %s" % w["session"][:8] if w.get("session") else ""))
        # LES GARDES RESTENT DITS. Un worktree retire du compte SANS etre affiche serait un
        # signal qu'on a fait taire -- exactement ce que `#467-r8` refuse (« ni compteur
        # d'avertissements ni `--quiet` : ca supprime le signal au lieu de le rendre juste »).
        grd = lv.get("gardes")
        if grd is not None and grd.mesuree and grd.valeur:
            L.append("           GARDE(S) sur marque `%s` : %d"
                     % (livraison.MARQUE_GARDE, len(grd.valeur)))
            for w in grd.valeur:
                L.append("             . %s  %s" % (w["branche"], w.get("raison") or ""))
    orph = lv.get("branches_orphelines")
    if orph is not None and (not orph.mesuree or orph.valeur):
        L.append("           branches d'agent livrees sans worktree : %s"
                 % (len(orph.valeur) if orph.mesuree else orph.txt()))
    cov = (e.get("empreinte") or {}).get("couverture")
    if cov is not None:
        L.append("EMPREINTE  457 : %s"
                 % (("format %s, %d/%d fichier(s) offline mesure(s), %d fantome(s)"
                     % (cov.valeur["format"], cov.valeur["couverts"], cov.valeur["perimetre"],
                        len(cov.valeur["fantomes"])))
                    if cov.mesuree else cov.txt()))
    L.append("HARNAIS    session %s ; drain %s ; liveRunners %s"
             % (("aucune" if ha["session"].valeur is None else
                 "%s %s" % (ha["session"].valeur.get("id"), ha["session"].valeur.get("status")))
                if ha["session"].mesuree else ha["session"].txt(),
                ("ARME" if ha["drain"].valeur else "off") if ha["drain"].mesuree
                else ha["drain"].txt(),
                ha["live_runners"].txt()))
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


def _budget(arg: float | None, env: str, defaut: float) -> float:
    """Un budget est un PARAMETRE : drapeau, puis variable d'environnement, puis defaut mesure.

    L'ENV n'est pas du confort. Le seul chemin qui compte est le hook, et son wrapper
    (`scripts/hooks/loop-status.ps1`) ne passe QUE `--hook` : sans variable, un budget ne se
    regle qu'en EDITANT ce fichier. C'est le meme patron que `TACTICUS_DISPATCH_CAP`, pour la
    meme raison -- la valeur reste visible et surchargeable au lieu de vivre en dur.

    Une surcharge ILLISIBLE retombe sur le defaut : ce module est un garde-fou de fin de tour,
    il ne casse pas un tour pour une faute de frappe dans une variable.
    """
    if arg is not None:
        return arg
    brut = os.environ.get(env)
    if brut:
        try:
            return float(brut)
        except ValueError:
            pass
    return defaut


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
    ap.add_argument("--timeout", type=float, default=None,
                    help="budget des sous-process locaux (env TACTICUS_LOOP_TIMEOUT)")
    ap.add_argument("--timeout-gh", type=float, default=None,
                    help="budget PROPRE de `gh`, en secondes (defaut : 10 sous --hook, 12 "
                         "sinon ; env TACTICUS_LOOP_GH_TIMEOUT)")
    ap.add_argument("--ttl-cache", type=float, default=None,
                    help="duree de vie du cache GitHub, en secondes (0 = pas de cache)")
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
    timeout = _budget(a.timeout, "TACTICUS_LOOP_TIMEOUT", 3.0 if a.hook else 8.0)
    ttl = a.ttl_cache if a.ttl_cache is not None else (300.0 if a.hook else 90.0)
    # `gh` a son propre budget, et il est LARGE la ou le budget general est SERRE. Les deux
    # repondent a des risques opposes : le budget general borne des sous-process LOCAUX (git,
    # dont une lenteur signale un probleme), `timeout_gh` borne un aller-retour RESEAU dont la
    # duree normale est deja de l'ordre de la seconde. Sous `--hook`, 3 s pour `gh` etaient
    # SOUS son cout mesure en concurrence -- 5 tours sur 8 aveugles (#467-r6).
    # Le mur reste tenu de deux cotes : le hook `Stop` dispose de 20 s cote Claude Code
    # (`.claude/settings.json`), et le cache de 300 s fait que `gh` n'est appele qu'une fois
    # par tranche de 5 minutes.
    timeout_gh = _budget(a.timeout_gh, "TACTICUS_LOOP_GH_TIMEOUT", 10.0 if a.hook else 12.0)
    src = Sources(repo=Path(a.repo), host=a.host, timeout=timeout,
                  avec_gh=not a.no_gh, avec_host=not a.no_host, ttl_cache=ttl,
                  timeout_gh=timeout_gh)
    if a.hook:
        # Un hook de fin de tour ne casse JAMAIS le tour. Toute panne imprevue se rabat sur le
        # silence : c'est un garde-fou, pas un maillon du chemin critique.
        try:
            e = etat(src, plafond)
            sig, ctx = signaux(e)
            if not sig:
                return 0
            print(json.dumps({"decision": "block",
                              "reason": _sortie_ascii(rendu_hook(sig, ctx))}))
        except Exception:                                    # noqa: BLE001
            return 0
        return 0

    e = etat(src, plafond)
    sig, ctx = signaux(e)

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
