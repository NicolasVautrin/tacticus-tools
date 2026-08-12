"""Board « sante du depot » : croisement PULL REQUESTS x TRANSCRIPTS x GIT, par jour.

Pendant de `fleet_board.py`, qui montre la flotte MAINTENANT. Celui-ci montre ce que la flotte a
PRODUIT, dans la duree : combien de PR, a quel cout en tokens, pour combien de lignes retenues.

TROIS SOURCES INDEPENDANTES, jointes sur la date locale :

  1. GitHub -- `gh pr list --state all`. Etat, dates, additions/deletions, branche, merge commit.
  2. Transcripts Claude Code -- `~/.claude/projects/<slug>/*.jsonl` (boucle principale) et
     `*/subagents/agent-*.jsonl` (agents). Tokens par jour, dedupes par uuid.
  3. Git -- `git log --numstat`. Commits et lignes par jour.

L'UNITE DE LIVRAISON EST LE MERGE D'UNE PR, PAS LE COMMIT. Les lignes d'une PR sont lues au DIFF
NET de son merge contre son premier parent (`git diff <merge>^1 <merge>`), et rattachees au jour du
MERGE. Une PR = une livraison atomique.

  - Insensible a la forme de l'historique de la branche : un `wip` puis son correctif comptent une
    fois. Mesure du 2026-08-01 : +427 449 lignes en net contre +430 816 en sommant les commits,
    soit 3 367 de churn interne (1 %).
  - Immunise contre les ALLERS-RETOURS DE REBASE. Quand l'orchestrateur renvoie une PR a son agent,
    elle revient sur un master qui a bouge, et deux PR mergees coup sur coup peuvent revendiquer
    les memes commits -- 831 revendications pour 816 commits distincts, 13 reclames deux ou trois
    fois. Au niveau du merge, la question ne se pose plus : `^1` est master AVANT le merge, donc
    le diff ne contient jamais ce qu'une PR precedente a deja fait entrer.
  - Marche uniformement sur les merges SQUASHES : `^1` existe toujours, le merge porte le diff.
    Necessaire ici -- seules 263 des 422 PR mergees ont produit un vrai merge a deux parents.

Le reste -- pushs directs sur master par l'orchestrateur : correctifs a chaud, docs, outillage --
est compte A PART et affiche, jamais melange au denominateur. Mesure du 2026-08-01, fenetre depuis
le 2026-07-10 : 1 290 commits de contenu, dont 819 arrives par une PR (63 %) et 471 pousses
directement.

LA JOINTURE PR <-> AGENT a DEUX voies, qui se corroborent :

  1. LA BRANCHE -- `worktreeBranch` du meta d'agent == `headRefName` de la PR. 381/422 PR mergees
     (90 %).
  2. LE MESSAGE DU MERGE -- un `agent-<id>` cite dans le corps, resolvable en
     `<session>/subagents/agent-<id>.jsonl`. 247/422 (59 %), dont 243 sur des commits
     « Merge pull request ».

La voie 2 est un SOUS-ENSEMBLE STRICT de la voie 1 : l'union reste 381, elle n'ajoute aucune PR.
Elle est gardee quand meme parce que, sur les 247 cas ou les deux repondent, elles sont d'accord
247 fois sur 247 -- validation croisee gratuite -- et parce qu'elle survit a un meta disparu.
VOIE ECARTEE -- le trailer `Claude-Session` : il nomme une SESSION API, or une conversation en
enchaine plusieurs. Mesure : 14 identifiants, dont 13 presents dans DEUX transcripts principaux ou
plus, et chacun present en outre dans 0 a 84 transcripts d'agent (l'agent herite du pied de page de
son parent). Il ne designe donc ni un transcript ni un agent -- et il ne figure que sur 16 des 263
commits « Merge pull request ».

Les 41 PR sans agent resolu portent une branche qui n'est celle d'aucun worktree
(`worktree-agent-350r3bc`, `agent/192-...`, `feat/113-votann-lot1`) -- ce sont des PR D'AGENT elles
aussi, avec un meta introuvable, pas des PR d'une autre provenance. Le denominateur les GARDE donc
par defaut ; les exclure amputait de 46 commits bien reels et basculait +39 791 lignes a tort du
cote « hors PR ». `--strict-agent` fournit la lecture etroite pour qui veut l'ecart.

CE QUE LES CHIFFRES NE DISENT PAS, et qu'il ne faut pas leur faire dire :

  - Les tokens d'un jour couvrent TOUTE l'activite du projet (RE, audits, conversation), pas
    seulement ce qui a fini en PR. Un `tokens / PR` est donc un indicateur de TENDANCE entre
    periodes, jamais un cout unitaire de production.
  - Les lignes de `git log --numstat` incluent le CHURN de scission de modules : un fichier eclate
    compte N ajouts + N suppressions pour zero code neuf. La croissance NETTE de l'arbre
    (`git diff base..HEAD`) est la mesure honnete, et elle est calculee a part. Elle couvre
    l'arbre ENTIER, PR et pushs directs confondus -- ce n'est pas le pendant net des colonnes.
  - `data/symbols` est exclu partout : c'est un artefact genere (table de symboles), pas du code
    ecrit. L'inclure gonflait les journees de re-dump de ~300 000 lignes.

Usage :
    python scripts/python/repo_board.py            # table console + logs/repo-board.html
    python scripts/python/repo_board.py --open      # ouvre la page
    python scripts/python/repo_board.py --since 2026-07-01
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import time
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Le corps d'un message de merge cite l'agent auteur sous cette forme -- c'est le NOM DE FICHIER
# de son transcript, `<session>/subagents/agent-<id>.jsonl`, donc un lien direct et non ambigu.
AGENT_RX = re.compile(r"agent-([0-9a-f]{8,})")
REC_SEP = "\x1e"

REPO = Path(__file__).resolve().parents[2]
# Le NOM DU FICHIER est l'identite de l'artefact publie : republier le meme chemin conserve
# l'URL, un chemin different en cree une neuve. Ne pas le renommer sans republier derriere.
OUT = REPO / "logs" / "repo-board.html"

# Artefact genere, versionne expres, mais ce n'est pas du code ecrit -- cf. docstring.
EXCLUDE = ":(exclude)data/symbols"

# ------------------------------------------------------------------ cache (VERSIONNE)
# Meme statut que `data/symbols/` : PRODUIT par un outil, versionne EXPRES. Ce que le board
# relit a chaque run est immuable par nature -- un jour revolu ne recoit plus d'enregistrement,
# et le diff d'une PR mergee ne bouge plus -- mais coute cher a re-deriver :
# 2,5 Go de transcripts (874 fichiers) et 2 appels git par PR, soit > 10 min de mur au
# 2026-08-03. Le cache ramene le run a ce qui a REELLEMENT change depuis la veille.
CACHE = REPO / "data" / "repo-board-cache.json"
CACHE_VERSION = 2

# Plafond de la liste des PR. Large A DESSEIN, et sature = erreur dure (cf. `load_prs`) :
# c'est le seul moyen d'apprendre qu'on a depasse la fenetre autrement qu'en voyant un jour
# revolu maigrir. 608 PR au 2026-08-04.
PR_LIMIT = 3000


def empty_cache() -> dict:
    return dict(version=CACHE_VERSION, days={}, agents={}, merges={}, files={})


def _first_uuid(fp: Path) -> str:
    """`uuid` de la PREMIERE ligne -- signature de conversation, lue en un seul read.

    Sert a reperer un FORK : une reprise de conversation RECOPIE le debut du parent dans un
    fichier neuf, donc les deux partagent leur premiere ligne. C'est le seul mecanisme qui
    produise des `uuid` en double entre fichiers (mesure du 2026-08-03 : 156 sur 277 109,
    tous entre transcripts PRINCIPAUX).
    """
    try:
        with fp.open("rb") as fh:
            ln = fh.readline(65536)
    except OSError:
        return ""
    try:
        return json.loads(ln.decode("utf-8", "replace")).get("uuid") or ""
    except Exception:
        return ""


def _read_tail(fp: Path, offset: int) -> tuple[list, int]:
    """Rend (lignes COMPLETES depuis `offset`, nouvel offset).

    Un transcript est APPEND-ONLY : un octet deja consomme ne changera plus, donc reprendre a
    l'offset est exact et evite de relire le fichier entier. On s'arrete au dernier saut de
    ligne -- une ligne partielle (ecriture en cours) est laissee pour le prochain run, sinon
    on parserait du JSON tronque et on perdrait l'enregistrement.
    """
    try:
        with fp.open("rb") as fh:
            fh.seek(offset)
            buf = fh.read()
    except OSError:
        return [], offset
    cut = buf.rfind(b"\n")
    if cut < 0:
        return [], offset
    usable = buf[:cut + 1]
    return usable.decode("utf-8", "replace").splitlines(), offset + len(usable)


def load_cache(use: bool = True) -> dict:
    """Cache disque, MIGRE vers la version courante -- jamais jete.

    ⛔ UN CHANGEMENT DE FORMAT NE DOIT JAMAIS PROVOQUER DE RELECTURE COMPLETE. Jeter le cache
    coute 2 616 Mo et 1 300 s (mesure du 2026-08-04), et cette relecture n'apporte RIEN : les
    agregats deja calcules portent sur des octets immuables. La v1 jetait, et l'a fait payer
    deux fois dans la meme heure.

    ⇒ TOUTE EVOLUTION DU FORMAT DOIT ETRE ADDITIVE : on ajoute des cles, on ne change pas le
    sens de `files[].offset` ni des agregats. C'est ce qui rend la migration triviale --
    on adopte l'existant et on estampille. Si un jour un champ devait changer de SENS, il
    faudrait le RECALCULER a partir du cache, pas des transcripts.

    Un cache illisible (absent, JSON casse) repart a vide : la, il n'y a rien a preserver.
    """
    if not use:
        return empty_cache()
    try:
        c = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty_cache()
    if not isinstance(c.get("days"), dict):
        return empty_cache()
    for k in ("days", "agents", "merges", "files"):
        c.setdefault(k, {})
    if c.get("version") != CACHE_VERSION:
        # Migration ADDITIVE : on garde jours/agents/merges/offsets tels quels. Les cles
        # devenues inutiles (`through`, `token` par agent) sont inertes -- personne ne les lit.
        c["version"] = CACHE_VERSION
    return c


# Le fichier se DECRIT LUI-MEME. Un lecteur qui le decouvre dans `git status` doit pouvoir
# trancher sans ouvrir ce script : le 2026-08-03, un autre agent travaillant dans le meme arbre
# l'a commite en le prenant pour « le cache du fleet-board, artefact de run dans data/ » -- soit
# exactement le motif qui aurait justifie de le SUPPRIMER. Un message de commit ne protege rien ;
# la provenance portee par le fichier, si.
_DOC = ("Cache du board de depot (scripts/python/repo_board.py). ENTREE versionnee, meme statut "
        "que data/symbols/ : memoise ce qui est IMMUABLE (jour revolu, diff d'une PR mergee) et "
        "couteux a re-deriver -- 408 s de recalcul complet contre 54 s. NE PAS SUPPRIMER : ce "
        "n'est pas une sortie de run. Le regenerer : repo_board.py --no-cache.")


def save_cache(c: dict) -> None:
    c["_doc"] = _DOC
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(c, ensure_ascii=False, sort_keys=True, indent=1),
                     encoding="utf-8")




def sh(args: list[str], cwd: Path = REPO) -> str:
    """Rend stdout, et REMONTE stderr en cas d'echec.

    Sans ca, un `gh` qui echoue rend une chaine vide et l'appelant ne peut qu'ACCUSER l'auth --
    diagnostic faux vu le 2026-07-28 sur un simple `HTTP 502: Bad Gateway` de l'API GitHub.
    """
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 and not r.stdout.strip():
        raise SystemExit("%s a echoue (rc=%d) : %s"
                         % (args[0], r.returncode, (r.stderr or "").strip()[:300]))
    return r.stdout


#: Pannes AMONT, qui se re-tentent : la requete est bonne, c'est le service qui a hoquete.
#: Mesure du 2026-08-12 -- la meme commande rend rc=1 (502) puis rc=0 en 68 s sans qu'on ait
#: touche a quoi que ce soit, et `--limit 1000` echoue la ou `--limit 3000` passe. Il n'y a
#: donc PAS de seuil de taille : c'est la PAGINATION qui expose. `gh pr list` decoupe en
#: pages de 100 ; a 982 PR ca fait ~10 appels GraphQL, et il suffit d'UN 502 pour tout perdre.
#: Le risque croit donc avec le depot -- ne pas re-tenter condamne l'outil a mesure qu'il grossit.
TRANSITOIRES = ("502", "503", "504", "bad gateway", "service unavailable",
                "gateway time-out", "gateway timeout", "timeout awaiting",
                "connection reset", "unexpected eof", "tls handshake",
                "temporary failure", "i/o timeout")

#: Pannes de NOTRE COTE : re-tenter n'y changerait rien et masquerait le diagnostic.
DEFINITIVES = ("authentication", "not logged", "requires authentication", "http 401",
               "http 403", "http 404", "could not resolve", "unknown flag",
               "no such host", "rate limit")


def _classe_panne(stderr: str) -> str:
    """`transitoire` / `definitive` / `inconnue` -- et le troisieme n'est PAS le premier.

    Une panne qu'on ne sait pas nommer ne doit pas etre re-tentee en boucle comme si on
    l'avait reconnue : on la re-tente UNE fois, puis on la remonte avec son texte. Rabattre
    l'inconnu sur << transitoire >> ferait tourner trois minutes sur une erreur d'usage."""
    s = (stderr or "").lower()
    if any(m in s for m in DEFINITIVES):
        return "definitive"
    if any(m in s for m in TRANSITOIRES):
        return "transitoire"
    return "inconnue"


def sh_retry(args: list[str], essais: int = 4, pause: float = 5.0,
             cwd: Path = REPO) -> str:
    """`sh`, mais qui re-tente les pannes AMONT -- et SEULEMENT celles-la.

    L'echec final NOMME sa classe et le nombre d'essais : un << gh a echoue >> nu avait deja
    fait accuser l'auth pour un 502 (cf. `sh`). Ici l'appelant apprend aussi qu'on a insiste."""
    dernier = ""
    for i in range(essais):
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode == 0 or r.stdout.strip():
            return r.stdout
        dernier = (r.stderr or "").strip()
        classe = _classe_panne(dernier)
        if classe == "definitive":
            raise SystemExit("%s a echoue (rc=%d, panne DEFINITIVE -- re-tenter n'y "
                             "changerait rien) : %s" % (args[0], r.returncode, dernier[:300]))
        reste = essais - i - 1
        if classe == "inconnue" and i >= 1:
            break                      # une seule insistance sur ce qu'on ne sait pas nommer
        if reste:
            print("  %s : panne %s, nouvel essai dans %.0fs (%d restant) -- %s"
                  % (args[0], classe, pause, reste, dernier[:120]))
            time.sleep(pause)
            pause *= 2
    raise SystemExit("%s a echoue apres insistance (panne %s) : %s"
                     % (args[0], _classe_panne(dernier), dernier[:300]))


def sh_soft(args: list[str]) -> str:
    """Variante TOLERANTE : rend "" sur echec au lieu de lever.

    Indispensable pour `rev-list <sha>^1..<sha>` : un merge de PR SQUASHE n'a qu'un parent, donc
    `^2` n'existe pas et git sort en erreur. C'est un cas NORMAL, pas une panne -- l'appelant
    retombe alors sur le merge lui-meme.
    """
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def project_dir() -> Path:
    """`~/.claude/projects/<slug>` ou <slug> = chemin du repo, ':' et separateurs -> '-'."""
    root = Path.home() / ".claude" / "projects"
    slug = str(REPO).replace(":", "-").replace("\\", "-").replace("/", "-")
    cand = root / slug
    if cand.is_dir():
        return cand
    best = max(root.glob("*"), key=lambda p: len(list(p.glob("*/subagents/agent-*.jsonl"))),
               default=None)
    if best is None:
        raise SystemExit("aucun repertoire de projet Claude sous %s" % root)
    return best


def _ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------- 1. pull requests
def load_prs(limit: int = PR_LIMIT) -> list[dict]:
    """Toutes les PR du depot. Un plafond SATURE est une ERREUR, jamais une troncature muette.

    `gh pr list --limit N` rend les N PLUS RECENTES. Quand le depot en compte plus, la
    fenetre GLISSE : les plus anciennes tombent de la liste, et les journees revolues qui
    les portaient RETRECISSENT d'un run a l'autre -- alors qu'un jour revolu est cense etre
    immuable. Mesure du 2026-08-04 : plafond a 500 pour 608 PR reelles ; le 2026-07-26 est
    passe de 28 PR a 16 pendant que le 2026-08-04 en gagnait exactement 12, total fige a
    500. Un rapport qui retrecit en silence est pire qu'un rapport absent.
    """
    # `sh_retry` et pas `sh` : c'est le SEUL appel PAGINE du board (pages de 100), donc le
    # seul ou un hoquet amont fait perdre tout le run. Deux 502 consecutifs le 2026-08-12.
    raw = sh_retry(["gh", "pr", "list", "--state", "all", "--limit", str(limit), "--json",
                    "number,title,state,createdAt,mergedAt,closedAt,additions,deletions,"
                    "changedFiles,headRefName,mergeCommit"])
    if not raw.strip():
        raise SystemExit("gh n'a rien rendu -- `gh auth status` ?")
    data = json.loads(raw)
    if len(data) >= limit:
        raise SystemExit(
            "plafond de PR SATURE (%d rendues pour une limite de %d) : la fenetre glisse et "
            "les jours anciens rétrécissent. Relever PR_LIMIT." % (len(data), limit))
    out = []
    for p in data:
        created, merged = _ts(p["createdAt"]), _ts(p.get("mergedAt"))
        out.append(dict(
            num=p["number"], title=p["title"], state=p["state"], branch=p["headRefName"],
            created=created, merged=merged,
            merge_sha=(p.get("mergeCommit") or {}).get("oid") or "",
            day=created.astimezone().strftime("%Y-%m-%d") if created else "",
            merged_day=merged.astimezone().strftime("%Y-%m-%d") if merged else "",
            closed_day=(closed.astimezone().strftime("%Y-%m-%d")
                        if (closed := _ts(p.get("closedAt"))) else ""),
            # duree de vie : ouverture -> merge. Sur une campagne d'agents elle mesure la
            # latence d'INTEGRATION, pas le temps de travail (l'agent a deja fini).
            ttm=((merged - created).total_seconds() / 60.0) if (merged and created) else None,
            add=p["additions"], dele=p["deletions"], files=p["changedFiles"]))
    return out


# ---------------------------------------------------------------- 2. transcripts
def _ctx(u) -> int:
    """Tokens de CONTEXTE d'un tour = `input + cache_creation + cache_read`.

    C'est la taille du PROMPT envoye, ni plus ni moins : ce que le modele a du lire pour repondre.
    L'`output` en est exclu (c'est ce qu'il a ecrit, pas ce qu'il a lu), et aucune ponderation de
    facturation n'est appliquee (pas de cw*1.25 / cr*0.10) -- on compte des tokens, pas des euros.

    Somme sur une journee, ce total compte N FOIS le meme contexte relu d'un tour a l'autre. C'est
    voulu : c'est precisement la charge de lecture du jour. Ne pas le confondre avec l'occupation
    de fenetre du fleet-board, qui est le prompt d'UN SEUL tour (le dernier).
    """
    return (int(u.get("input_tokens") or 0)
            + int(u.get("cache_creation_input_tokens") or 0)
            + int(u.get("cache_read_input_tokens") or 0))


def load_tokens(pdir: Path, cache: dict) -> tuple[dict, dict]:
    """Rend (par_jour, par_agent_id). Streaming : on ne parse que les lignes portant `usage`.

    NE LIT QUE LES OCTETS NEUFS. Un transcript est APPEND-ONLY : on retient l'offset consomme
    par fichier et on reprend a la queue. Chaque octet n'entre donc qu'une fois dans les
    agregats, qui s'ACCUMULENT -- pas de recalcul, donc pas de risque de double compte.

    CE QUE LA VERSION PRECEDENTE FAISAIT, ET POURQUOI C'ETAIT INSUFFISANT. La v1 bornait la
    relecture par `mtime` : un fichier non modifie depuis le debut du jour J ne peut rien
    porter de J (append-only, horodate a l'ecriture). Exact, mais elle relisait ENTIEREMENT
    les fichiers touches. Mesure du 2026-08-04 : 654 Mo relus pour deux jours a recalculer,
    dont 542 Mo pour LE SEUL transcript de l'orchestrateur -- 83 % du volume, alors que sa
    part neuve tenait en quelques Mo. D'ou 298 s de mur.

    LE SEUL DANGER DE L'ACCUMULATION EST LE FORK. Un meme enregistrement peut figurer dans
    deux fichiers quand une conversation est REPRISE : le fichier neuf recopie le passe du
    parent. Mesure du 2026-08-03 : 156 uuid sur 277 109 (0,031 % du context), tous entre
    transcripts PRINCIPAUX, aucun n'impliquant un agent. La v1 les attrapait par un set
    `seen` global ; l'incremental ne le peut plus -- il ne relit pas le passe.
    Parade, sur le mecanisme et non sur le symptome : un fork PARTAGE SA PREMIERE LIGNE avec
    son parent. Un transcript principal inconnu dont le premier `uuid` est deja connu declenche
    donc une RECONSTRUCTION complete. Rare : 14 principaux en 25 jours.

    RESIDU ASSUME : un fork qui demarrerait au MILIEU du parent (premiere ligne differente)
    passerait la garde, et sa portion recopiee serait comptee deux fois. Jamais observe --
    les 156 doublons mesures viennent tous d'un fork depuis l'origine. `--no-cache` recalcule
    tout et repare, quoi qu'il arrive.
    """
    mains = sorted(pdir.glob("*.jsonl"))
    agents = sorted(pdir.glob("*/subagents/agent-*.jsonl"))
    fcache = cache["files"]

    # --- FORK ? ------------------------------------------------------------------------
    # Un transcript principal INCONNU qui partage sa premiere ligne avec un connu est une
    # REPRISE : il recopie le passe du parent, donc l'accumulation le compterait deux fois.
    # Seul remede exact : tout reconstruire. Rare (14 principaux en 25 jours, un seul fork).
    known_first = {v.get("first") for v in fcache.values() if v.get("first")}
    forked = next((fp.name for fp in mains
                   if fp.name not in fcache and _first_uuid(fp) in known_first), None)
    if forked:
        cache.update(days={}, agents={}, files={})
        fcache = cache["files"]

    by_day = defaultdict(lambda: defaultdict(int))
    for day, v in cache["days"].items():
        for k in ("ctx", "turns", "agent_ctx"):
            by_day[day][k] = int(v.get(k) or 0)

    by_agent = defaultdict(lambda: defaultdict(int))
    for aid, v in cache["agents"].items():
        a = by_agent[aid]
        a["ctx"] = int(v.get("ctx") or 0)
        a["turns"] = int(v.get("turns") or 0)
        a["first"] = _ts(v.get("first"))
        a["last"] = _ts(v.get("last"))

    seen = set()
    n_bytes = n_files = 0
    for fp in mains + agents:
        aid = fp.stem.replace("agent-", "") if "subagents" in fp.parts else None
        key = fp.name
        ent = fcache.get(key) or dict(offset=0, first=_first_uuid(fp))
        try:
            size = fp.stat().st_size
        except OSError:
            continue
        # Un fichier PLUS COURT que ce qu'on a consomme n'est plus le meme : il a ete
        # tronque ou remplace. On ne peut rien deduire de son offset -> on le relit entier,
        # et l'agregat qu'il portait est perdu (cas jamais observe ; `--no-cache` le repare).
        if size < ent["offset"]:
            ent["offset"] = 0
        if size == ent["offset"]:
            fcache[key] = ent
            continue
        lines, ent["offset"] = _read_tail(fp, ent["offset"])
        fcache[key] = ent
        n_files += 1
        for ln in lines:
            n_bytes += len(ln)
            if '"usage"' not in ln:
                continue
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            uid = rec.get("uuid")
            if uid:
                if uid in seen:
                    continue
                seen.add(uid)
            u = (rec.get("message") or {}).get("usage") or {}
            if not u:
                continue
            t = _ts(rec.get("timestamp"))
            if not t:
                continue
            ctx = _ctx(u)
            day = t.astimezone().strftime("%Y-%m-%d")
            # Accumulation PURE : chaque octet n'est consomme qu'une fois, donc plus besoin
            # de la borne `through` de la v1 -- aucun enregistrement ne peut etre recompte.
            by_day[day]["ctx"] += ctx
            by_day[day]["turns"] += 1
            if aid:
                by_day[day]["agent_ctx"] += ctx
                a = by_agent[aid]
                a["ctx"] += ctx
                a["turns"] += 1
                if not a.get("first") or t < a["first"]:
                    a["first"] = t
                if not a.get("last") or t > a["last"]:
                    a["last"] = t

    cache["days"] = {d: dict(ctx=v["ctx"], turns=v["turns"], agent_ctx=v.get("agent_ctx", 0))
                     for d, v in by_day.items()}
    cache["agents"] = {aid: dict(ctx=a["ctx"], turns=a["turns"],
                                 first=a["first"].isoformat() if a.get("first") else None,
                                 last=a["last"].isoformat() if a.get("last") else None)
                       for aid, a in by_agent.items()}
    cache["stat_tokens"] = dict(fichiers=n_files, total=len(mains) + len(agents),
                                mo=round(n_bytes / 1048576.0, 1), fork=forked or "")
    return by_day, by_agent


def agents_on_disk(pdir: Path) -> set:
    return {p.stem.replace("agent-", "") for p in pdir.glob("*/subagents/agent-*.jsonl")}


def merge_msg_agents(known: set) -> dict:
    """SHA de merge -> id d'agent CITE dans son message, filtre sur les transcripts existants.

    Deuxieme voie de jointure, corroborante (cf. docstring du module) : elle couvre moins que la
    branche mais n'est jamais en desaccord avec elle, et elle survit a un meta disparu. Le filtre
    par `known` est ce qui empeche de fabriquer un lien : un id sans transcript n'est pas retenu.
    """
    raw = sh(["git", "log", "--format=%H\x1f%B" + REC_SEP])
    out = {}
    for blk in raw.split(REC_SEP):
        f = blk.strip("\n").split("\x1f")
        if len(f) < 2:
            continue
        ids = [i for i in AGENT_RX.findall(f[1]) if i in known]
        if ids:
            out[f[0]] = ids[0]
    return out


def load_metas(pdir: Path, cache: dict) -> dict:
    """branche -> {id, name}. Double indexation : le meta, et l'id lu DANS le nom de branche.

    Certaines PR portent une branche `worktree-agent-<id>` dont le meta est absent (transcript
    dans un autre repertoire de projet, ou meta jamais ecrit). Reconstruire l'id depuis le nom
    rattrape ces cas sans inventer de correspondance : l'id EST dans la chaine.

    MEMOISE PAR FICHIER : un meta est ecrit au lancement de l'agent et n'est plus jamais touche
    -- il n'a ni suite ni revision. Les relire tous coutait 7,0 s par run pour 894 fichiers
    (mesure du 2026-08-04), soit le deuxieme poste du board une fois les transcripts rendus
    incrementaux. On ne lit donc que les meta INCONNUS du cache.
    """
    known = cache.setdefault("metas", {})
    n_new = 0
    for p in pdir.glob("*/subagents/agent-*.meta.json"):
        aid = p.name.replace("agent-", "").replace(".meta.json", "")
        if aid in known:
            continue
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        known[aid] = dict(branch=(m.get("worktreeBranch") or "").strip(),
                          name=m.get("description") or aid, type=m.get("agentType") or "")
        n_new += 1
    cache["stat_metas"] = dict(lus=n_new, reutilises=len(known) - n_new)

    by_branch = {}
    for aid, m in known.items():
        rec = dict(id=aid, name=m["name"], type=m.get("type") or "")
        if m.get("branch"):
            by_branch[m["branch"]] = rec
        by_branch.setdefault("worktree-agent-%s" % aid, rec)
    return by_branch


# ------------------------------------------------- 2bis. livraison par squash manuel
def squash_delivered(prs: list[dict], cache: dict) -> None:
    """Marque les PR FERMEES SANS `mergedAt` qui ont pourtant LIVRE, et pose `delivered_day`.

    ⛔ `mergedAt` N'EST PAS LE CRITERE DE LIVRAISON DANS CE DEPOT. Quand une branche est
    squashee A LA MAIN sur `master` puis la PR fermee, le sha de la branche n'est jamais
    ancetre de `master` : GitHub la classe `CLOSED`, `mergedAt` reste nul. La PR a livre.

    MESURE DU 2026-08-11, qui a motive cette fonction : la journee affichait **15 PR** alors
    que **42** avaient ete livrees. Les 27 manquantes etaient toutes des squashes manuels --
    confrontees au CONTENU, **27/27 retrouvees dans `master`** (26 a 100 % de leurs fichiers,
    1 a 85 %), **0 reellement abandonnee**. Le board les comptait en « fermees sans merge »,
    c'est-a-dire en ABANDONS, et affichait un taux de merge de 93 % qui n'existait pas.

    LE CRITERE EST LE CONTENU, PAS LE MESSAGE. Une premiere tentative cherchait le numero de
    PR dans les sujets de commit de `master` : elle rendait 23 faux « sans trace », parce que
    les messages citent le numero de RESIDU (`merge(#926)`) et non celui de la PR. On regarde
    donc si les FICHIERS que la PR touche existent dans `origin/master`. Seuil a 80 % : une
    PR livree peut voir un fichier renomme ou resupprime derriere elle.

    MEMOISE : une PR fermee ne rouvre pas, donc son verdict est definitif. Sans cela, chaque
    run refait un `gh pr view` par PR fermee (60 appels reseau au 2026-08-11).
    """
    dcache = cache.setdefault("delivered", {})
    n_new = n_fail = 0
    for p in prs:
        p["via_squash"] = False
        p["delivered_day"] = p["merged_day"]
        if p["merged"] or p["state"] != "CLOSED" or not p["closed_day"]:
            continue
        key = str(p["num"])
        hit = dcache.get(key)
        if hit is None:
            # UN ECHEC RESEAU N'EST PAS UN VERDICT. `gh` rend des 502/504 par rafales ; avec 60
            # PR fermees a interroger, en faire une SystemExit tuait tout le run, et cacher le
            # resultat vide aurait fige un « non livree » DEFINITIF sur une PR livree. On
            # reessaie, puis on laisse la PR NON MESUREE (rien en cache, elle repassera).
            raw = ""
            for _ in range(3):
                raw = sh_soft(["gh", "pr", "view", key, "--json", "files"])
                if raw.strip():
                    break
            if not raw.strip():
                n_fail += 1
                continue
            files = [f["path"] for f in (json.loads(raw).get("files") or [])]
            present = sum(1 for f in files
                          if subprocess.run(["git", "cat-file", "-e", "origin/master:" + f],
                                            cwd=REPO, capture_output=True).returncode == 0)
            # `part` est conserve tel quel : un verdict borderline doit rester RELISIBLE plus
            # tard sans refaire l'appel reseau.
            hit = dict(n=len(files), present=present,
                       part=(present / len(files)) if files else 0.0)
            dcache[key] = hit
            n_new += 1
        if hit["n"] and hit["part"] >= 0.80:
            p["via_squash"] = True
            p["delivered_day"] = p["closed_day"]
            # LIGNES : base de mesure DIFFERENTE, et il faut le savoir. Une PR mergee est
            # mesuree au diff NET de son merge contre master-avant ; une PR squashee n'a pas
            # de merge, donc on prend le diff que GITHUB calcule pour la branche (`additions`).
            # Les deux ne coincident pas exactement (le net absorbe ce qu'un rebase a deja fait
            # entrer), mais l'alternative etait ZERO ligne : le 2026-08-11 affichait 20 994
            # lignes pour 42 PR et un ctx/ligne de 317 k, quatre fois la normale de la fenetre.
            p["net_add"], p["net_del"] = p["add"], p["dele"]
            p["n_commits"] = 1
    # `non_mesurees` est un TRI-ETAT, pas un zero : ces PR n'ont pas de verdict, et le board doit
    # le DIRE plutot que les ranger en abandons par defaut.
    cache["stat_delivered"] = dict(interroges=n_new, reutilises=len(dcache) - n_new,
                                   non_mesurees=n_fail)


# ---------------------------------------------------------------- 3. git
def pr_commits(prs: list[dict], strict: bool, cache: dict) -> dict:
    """SHA -> numero de PR, pour chaque commit AMENE par une PR mergee.

    `rev-list <merge>^1..<merge>` = ce que le merge a fait entrer, et rien d'autre : le premier
    parent est master avant le merge, le second la tete de la branche. Un merge SQUASHE n'a qu'un
    parent -- `^2` echoue, et c'est le merge lui-meme qui PORTE le contenu : on le compte pour un.
    `strict` restreint aux PR dont l'agent est identifie par sa branche (cf. docstring du module).

    UN COMMIT N'EST COMPTE QU'UNE FOIS, ET POUR LA PREMIERE PR QUI L'A FAIT ENTRER. Quand
    l'orchestrateur renvoie une PR a son agent pour rebase, la branche repart d'un master qui a
    bouge : deux PR mergees coup sur coup peuvent alors revendiquer les memes commits.
    Mesure du 2026-08-01 : 831 revendications pour 816 commits distincts -- 13 commits reclames
    par deux ou trois PR (grappe #378-#386). D'ou le parcours par date de MERGE croissante :
    `setdefault` attribue au premier arrive, qui est celui qui a reellement fait entrer le code.
    Ce que ces allers-retours coutent VRAIMENT est en tokens, dans le transcript de l'agent
    repris -- pas en commits. Verifie par ailleurs : 0 branche porte plusieurs PR, 0 groupe de
    `git patch-id` partage (aucun contenu reapplique sous un autre SHA), et 0 des 31 PR fermees
    sans merge n'a vu sa tache remergee sous un autre numero.
    """
    mcache = cache["merges"]
    owner = {}
    n_git = 0
    for p in sorted(prs, key=lambda q: q["merged"] or datetime.max.replace(tzinfo=timezone.utc)):
        if not p["merge_sha"] or (strict and not p.get("agent_id")):
            continue
        sha = p["merge_sha"]
        # MEMOISE PAR SHA DE MERGE : `<merge>^1..<merge>` et son diff ne dependent que de l'objet
        # git, immuable une fois la PR mergee. C'est ce qui evite 2 appels git par PR a chaque run.
        hit = mcache.get(sha)
        if hit is None:
            # --no-merges : une branche d'agent qui a merge master en cours de route amene ses
            # propres merges, qui n'apportent aucune ligne. Les compter gonflait le perimetre de
            # 174 sur 993 (mesure du 2026-08-01) pour zero contenu.
            shas = [s for s in sh_soft(["git", "rev-list", "--no-merges",
                                        "%s^1..%s" % (sha, sha)]).split() if s]
            add = dele = 0
            # LA LIVRAISON : diff NET du merge contre master-avant-merge. C'est cette mesure-la
            # qui alimente les colonnes, pas la somme des commits (gardee pour le compte seul).
            for ln in sh_soft(["git", "diff", "--numstat", "%s^1" % sha, sha,
                               "--", ".", EXCLUDE]).splitlines():
                f = ln.split("\t")
                if len(f) == 3 and f[0] != "-":
                    add += int(f[0])
                    dele += int(f[1])
            hit = dict(commits=shas or [sha], add=add, dele=dele)
            mcache[sha] = hit
            n_git += 1
        # La DEDUPLICATION reste calculee a chaque run, jamais memoisee : elle depend de l'ORDRE
        # de merge de TOUTES les PR, donc une PR mergee ensuite peut la changer.
        n = 0
        for s in hit["commits"]:
            if s not in owner:
                owner[s] = p["num"]
                n += 1
        p["n_commits"] = n
        p["net_add"] = hit["add"]
        p["net_del"] = hit["dele"]
    cache["stat_merges"] = dict(interroges=n_git, reutilises=len(mcache) - n_git)
    return owner


def load_git(since: str, keep: set) -> tuple[dict, dict]:
    """Agrege par jour. `commits`/`add` = PR SEULEMENT ; `direct_*` = les pushs hors PR.

    Les deux sont retenus : un board qui n'afficherait que le perimetre PR laisserait croire que
    le depot n'a pas d'autre activite, alors que les pushs directs de l'orchestrateur en portent
    plus du tiers.
    """
    # %P donne les parents SUR LA LIGNE : deux parents = merge. Le demander a `git log` evite un
    # `rev-parse` par commit -- 1 459 sous-processus sous Windows, plusieurs minutes pour rien.
    raw = sh(["git", "log", "--pretty=format:C|%H|%aI|%P", "--numstat",
              "--since", since, "--", ".", EXCLUDE])
    by_day = defaultdict(lambda: defaultdict(int))
    day = None
    pfx = "direct_"
    for ln in raw.splitlines():
        if ln.startswith("C|"):
            _, sha, iso, parents = ln.split("|", 3)
            day = _ts(iso).astimezone().strftime("%Y-%m-%d")
            # Un merge ne tombe dans AUCUN des deux seaux, et le test passe AVANT `keep` : une
            # branche d'agent qui a merge master en cours de route amene ses propres merges, que
            # `rev-list` rapporte donc comme commits de la PR. Les compter gonflait le perimetre
            # PR de 174 sur 993 (mesure du 2026-08-01) pour zero ligne -- --numstat ignore leur
            # diff. La partition doit rester : PR + direct + merges = tous les commits.
            merge = len(parents.split()) > 1
            pfx = None if merge else ("" if sha in keep else "direct_")
            if pfx is not None:
                by_day[day][pfx + "commits"] += 1
            continue
        parts = ln.split("\t")
        if len(parts) != 3 or day is None or parts[0] == "-" or pfx is None:
            continue
        by_day[day][pfx + "add"] += int(parts[0])
        by_day[day][pfx + "del"] += int(parts[1])
    # croissance NETTE de l'arbre sur la fenetre -- annule le churn de scission de modules
    base = sh(["git", "rev-list", "-1", "--before", "%s 00:00" % since, "HEAD"]).strip()
    net = {}
    if base:
        stat = sh(["git", "diff", "--shortstat", base, "HEAD", "--", ".", EXCLUDE]).strip()
        net["shortstat"] = stat
    return by_day, net


# ---------------------------------------------------------------- assemblage
def build(since: str, strict: bool = False, use_cache: bool = True,
          pr_rows: int = 120) -> dict:
    pdir = project_dir()
    cache = load_cache(use_cache)
    prs = load_prs()
    tok_day, tok_agent = load_tokens(pdir, cache)
    metas = load_metas(pdir, cache)

    known = agents_on_disk(pdir)
    by_msg = merge_msg_agents(known)

    joined = via_msg = agree = 0
    clashes = []
    for pr in prs:
        m = metas.get(pr["branch"])
        cited = by_msg.get(pr["merge_sha"]) if pr["merge_sha"] else None
        if m and cited:
            # Confrontation des deux voies. Un desaccord est RARE et doit etre NOMME, pas
            # compte : un « 1 desaccord » anonyme oblige a re-ecrire a la main la sonde qui
            # dit LAQUELLE -- fait le 2026-08-05, et la cause etait instructive.
            #
            # CE QU'UN DESACCORD SIGNIFIE, mesure : la voie MESSAGE se fait piéger quand le
            # corps du merge CITE un `agent-<id>` comme SUJET au lieu de l'avoir pour auteur.
            # Cas reel, PR #659 (menage de branches) : le message cite la branche gardee
            # `worktree-agent-a884d253a85a3b0c5`, et `AGENT_RX` y voit l'auteur. La voie
            # BRANCHE, elle, disait juste -- c'est elle qui prime, donc l'ATTRIBUTION reste
            # correcte ; seul le compteur s'en emeut. Un desaccord n'est donc PAS
            # automatiquement une erreur d'attribution : c'est un appel a regarder.
            if m["id"] == cited:
                agree += 1
            else:
                clashes.append((pr["num"], m["id"], m["name"], cited))
        # La BRANCHE prime : voie la plus couvrante. Le message la RELAIE quand le meta manque.
        pr["agent_id"] = m["id"] if m else (cited or "")
        pr["agent"] = m["name"] if m else (("agent %s" % cited[:8]) if cited else "")
        pr["via"] = "branche" if m else ("message" if cited else "")
        a = tok_agent.get(pr["agent_id"]) if pr["agent_id"] else None
        pr["agent_ctx"] = a["ctx"] if a else 0
        pr["agent_mins"] = ((a["last"] - a["first"]).total_seconds() / 60.0
                            if a and a.get("first") and a.get("last") else 0.0)
        pr["n_commits"] = 0
        pr["net_add"] = pr["net_del"] = 0
        joined += bool(pr["agent_id"])
        via_msg += pr["via"] == "message"

    squash_delivered(prs, cache)

    # L'enumeration des commits de PR vient APRES la jointure d'agent : `--strict-agent` en depend.
    owner = pr_commits(prs, strict, cache)
    git_day, git_net = load_git(since, set(owner))
    # Le cache est valide dans LES DEUX modes : les tokens ignorent `strict`, et le cache de
    # merges est de la donnee git BRUTE par sha (`strict` change seulement QUELLES PR on
    # interroge, pas ce que git repond pour l'une d'elles).
    save_cache(cache)

    days = sorted({d for d in set(tok_day) | set(git_day) | {p["day"] for p in prs if p["day"]}
                   if d >= since})
    rows = []
    for d in days:
        g, t = git_day.get(d, {}), tok_day.get(d, {})
        opened = [p for p in prs if p["day"] == d]
        # LIVREE, pas « mergee » : une PR squashee A LA MAIN puis fermee n'a pas de `mergedAt`
        # (le sha de sa branche n'est jamais ancetre de master) alors qu'elle a bel et bien
        # livre. Les compter comme des abandons faisait tomber la livraison du 2026-08-11 de
        # 42 a 15 -- cf. `squash_delivered`.
        merged = [p for p in prs if p["delivered_day"] == d]
        # Les colonnes sont portees par les PR LIVREES ce jour-la, au diff net de leur merge.
        # `commits` reste le compte des commits qu'elles ont fait entrer : c'est une INDICATION
        # de granularite, jamais le denominateur des lignes.
        ctx = t.get("ctx", 0)
        commits = sum(p["n_commits"] for p in merged)
        add = sum(p["net_add"] for p in merged)
        rows.append(dict(
            day=d, opened=len(opened), merged=len(merged),
            squash=len([p for p in merged if p["via_squash"]]),
            closed=len([p for p in opened if p["state"] == "CLOSED"]),
            commits=commits, add=add, dele=sum(p["net_del"] for p in merged),
            direct_commits=g.get("direct_commits", 0), direct_add=g.get("direct_add", 0),
            ctx=ctx, turns=t.get("turns", 0), agent_ctx=t.get("agent_ctx", 0),
            # Les deux ratios demandes. Denominateur nul -> 0, jamais une division qui explose ni
            # un « infini » qui polluerait les echelles de barres.
            ctx_per_pr=(ctx / len(merged)) if merged else 0,
            ctx_per_commit=(ctx / commits) if commits else 0,
            ctx_per_line=(ctx / add) if add else 0))
    return dict(days=rows, prs=prs, joined=joined, net=git_net, since=since, strict=strict,
                agents=tok_agent, project_dir=str(pdir), n_pr_commits=len(owner),
                via_msg=via_msg, agree=agree, clash=len(clashes), clashes=clashes,
                pr_rows=pr_rows,
                cache=dict(tokens=cache.get("stat_tokens", {}),
                           merges=cache.get("stat_merges", {}),
                           metas=cache.get("stat_metas", {}),
                           delivered=cache.get("stat_delivered", {})))


# ---------------------------------------------------------------- console
def n(x) -> str:
    return f"{int(x):,}".replace(",", " ")


def console(data: dict) -> None:
    # L'UNITE DE LA LIGNE EST LA PR MERGEE ce jour-la. Le compte de commits reste affiche, mais
    # en colonne SECONDAIRE : c'est une granularite (combien de commits une PR a fait entrer),
    # jamais le denominateur. Une PR = une livraison, quel que soit le nombre de commits dedans.
    hdr = "%-12s%6s%7s%16s%10s%14s%12s%9s%9s%8s"
    print("unite = la PR LIVREE%s : lignes au diff net de son merge, au jour de la livraison."
          % (" (agent identifie)" if data["strict"] else ""))
    print("`squash` = livrees a la MAIN puis fermees (pas de mergedAt) -- livrees quand meme.")
    print("`direct` = commits pousses sur master hors PR.")
    print(hdr % ("jour", "PR", "squash", "context", "+lignes",
                 "ctx/PR", "ctx/ligne", "ouvertes", "commits", "direct"))
    tot = defaultdict(int)
    for r in data["days"]:
        for k in ("opened", "merged", "squash", "commits", "add", "dele", "ctx",
                  "direct_commits", "direct_add"):
            tot[k] += r[k]
        print(hdr % (r["day"], r["merged"] or "-", r["squash"] or "-", n(r["ctx"]), n(r["add"]),
                     n(r["ctx_per_pr"]) if r["merged"] else "-",
                     n(r["ctx_per_line"]) if r["add"] else "-",
                     r["opened"] or "-", r["commits"] or "-", r["direct_commits"] or "-"))
    print(hdr % ("TOTAL", tot["merged"], tot["squash"], n(tot["ctx"]), n(tot["add"]),
                 n(tot["ctx"] / tot["merged"]) if tot["merged"] else "-",
                 n(tot["ctx"] / tot["add"]) if tot["add"] else "-",
                 tot["opened"], tot["commits"], tot["direct_commits"]))
    prs = data["prs"]
    # LIVREE = mergee par GitHub OU squashee a la main (cf. `squash_delivered`). Compter les
    # secondes en abandons donnait un taux de merge de 93 % qui n'existait pas.
    merged = [p for p in prs if p["state"] == "MERGED" or p["via_squash"]]
    squash = [p for p in prs if p["via_squash"]]
    ttm = sorted(p["ttm"] for p in merged if p["ttm"] is not None)
    print()
    print("PR            : %d ouvertes, %d livrees (%.0f%%) dont %d par squash manuel,"
          " %d abandonnees"
          % (len(prs), len(merged), 100 * len(merged) / max(1, len(prs)), len(squash),
             len(prs) - len(merged)))
    print("jointure agent: %d/%d (%.0f%%) -- dont %d par le message de merge seul"
          % (data["joined"], len(prs), 100 * data["joined"] / max(1, len(prs)),
             data["via_msg"]))
    print("  confrontation des deux voies : %d accords, %d desaccords%s"
          % (data["agree"], data["clash"], "" if not data["clash"] else "  <-- A TRANCHER"))
    for num, bid, bname, cited in data.get("clashes", []):
        # L'attribution RETENUE est celle de la branche ; on la nomme pour qu'un lecteur
        # puisse trancher sans re-outiller.
        print("     PR #%s : branche -> %s (%s) | message -> %s  [retenu : branche]"
              % (num, bid[:12], bname[:44], cited[:12]))
    tot_c = tot["commits"] + tot["direct_commits"]
    print("commits       : %d par PR (%.0f%%), %d pousses directement sur master"
          % (tot["commits"], 100 * tot["commits"] / max(1, tot_c), tot["direct_commits"]))
    print("lignes        : +%s par PR, +%s hors PR" % (n(tot["add"]), n(tot["direct_add"])))
    if ttm:
        print("latence merge : mediane %.0f min, p90 %.0f min"
              % (ttm[len(ttm) // 2], ttm[int(len(ttm) * 0.9)]))
    if data["net"].get("shortstat"):
        print("croissance nette de l'arbre depuis %s : %s" % (data["since"], data["net"]["shortstat"]))
    c, tk = data["cache"], data["cache"]["tokens"]
    print("cache         : %.1f Mo lus (queue de %d fichiers sur %d), merges %d/%d,"
          " metas %d/%d neufs%s"
          % (tk.get("mo", 0), tk.get("fichiers", 0), tk.get("total", 0),
             c["merges"].get("interroges", 0),
             c["merges"].get("interroges", 0) + c["merges"].get("reutilises", 0),
             c["metas"].get("lus", 0),
             c["metas"].get("lus", 0) + c["metas"].get("reutilises", 0),
             "  [FORK %s -> reconstruction]" % tk["fork"] if tk.get("fork") else ""))


# ---------------------------------------------------------------- rendu HTML
def esc(s) -> str:
    return html.escape(str(s), quote=True)


def render(data: dict) -> str:
    from repo_board_render import page          # noqa: E402  (rendu isole, cf. module)
    return page(data)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default="2026-07-10", help="date de debut (defaut 2026-07-10)")
    ap.add_argument("-o", "--out", default=str(OUT))
    ap.add_argument("--open", action="store_true", help="ouvre la page dans le navigateur")
    ap.add_argument("--json", action="store_true", help="sortie machine")
    ap.add_argument("--strict-agent", action="store_true",
                    help="ne garder que les PR dont l'agent est identifie par sa branche")
    ap.add_argument("--no-cache", action="store_true",
                    help="tout recalculer et REECRIRE le cache (long : cf. docstring de CACHE)")
    ap.add_argument("--pr-rows", type=int, default=120,
                    help="PR les plus recentes listees dans la page (defaut 120 ; les agregats,"
                         " eux, portent toujours sur la totalite)")
    args = ap.parse_args()

    data = build(args.since, args.strict_agent, use_cache=not args.no_cache,
                 pr_rows=args.pr_rows)
    if args.json:
        def enc(o):
            return o.isoformat() if isinstance(o, datetime) else str(o)
        print(json.dumps(data, default=enc, ensure_ascii=False))
        return

    console(data)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print("\n-> %s" % out)
    if args.open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
