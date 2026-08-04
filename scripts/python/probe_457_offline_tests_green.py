"""#457 -- CLIQUET : TOUT fichier de test qui n'est pas `_live.py` doit etre VERT.

CE QU'IL EST SEUL A VOIR
------------------------
Un fichier de test 100 % OFFLINE, ROUGE EN PERMANENCE sur `master`, que rien ne signale.

Mesure du 2026-08-02, sur `master` propre : `tests/engine/runner/test_multihex_substrate.py`
rendait `3 failed, 15 passed` -- et le rouge datait du 2026-08-01. Trois raisons CUMULEES le
rendaient invisible, et aucune n'est un oubli individuel :

  1. `CLAUDE.md` PROSCRIT la suite complete -- a raison : 410 des 519 fichiers de test sont
     `_live.py`, la suite entiere sature la session Frida partagee. (Comptes RE-DERIVES le
     2026-08-02 apres #457-r5 ; les precedents -- 489 et 405 -- etaient eux-memes fausses par
     le glob corrige ci-dessous, qui masquait 23 fichiers.)
  2. Un agent ne rejoue que les tests de SA tranche, et ce fichier n'etait la tranche de personne.
  3. Les trois entrees pytest de la banque (`pytest_signatures`, `pytest_attestations`,
     `pytest_adjacency`) nomment leurs fichiers A LA MAIN. C'est une ALLOWLIST : un fichier n'y
     entre que si quelqu'un pense a l'y mettre. Personne n'y a pense pour celui-la.

C'est la forme deja trouvee par #435 et #455, et la correction durable a chaque fois ete d'entrer
le garde dans la banque. Ce cliquet la generalise : son perimetre se DERIVE (tout ce qui n'est pas
`_live.py`), donc un fichier offline neuf y entre TOUT SEUL, sans que personne ait a y penser.

Il voit aussi la SECONDE moitie du meme vice, plus couteuse : le VERT VACUEUX. Dans le fichier
mesure, un quatrieme test passait au vert avec zero assertion utile -- son anneau de voisins etait
vide, donc `set([centre]) == {centre} | set([])` etait trivialement vraie. Un fichier rouge se
repare ; un fichier vert-a-vide s'accumule.

CE QU'IL COUTE -- ET POURQUOI CE N'EST PLUS << presque rien >>
--------------------------------------------------------------
La proscription de la suite complete vise le cout des tests LIVE : les OFFLINE ne montent aucun
runner. Mais le cout a CHANGE D'ORDRE avec #457-r5, et l'ancienne redaction (<< 84 fichiers,
896 tests, 116 s d'un bloc ; 86 s pour le plus long des trois shards >>) mesurait un perimetre
AMPUTE de 23 fichiers.

Mesure du 2026-08-02, perimetre COMPLET, 109 fichiers / 1195 tests, trois shards joues en
parallele SOUS CHARGE (5 agents actifs) : **602 / 770 / 431 s**. Les 24 fichiers entrants pesent a
eux seuls plus de 600 s en serie -- ce sont pour l'essentiel des BALAYAGES (tables de symboles,
669 kits, arbre `scripts/**`), lourds mais legitimement offline.

Consequence assumee : a trois shards ce cliquet DEVIENT le mur de la banque, d'ou le passage a
HUIT dans `scripts/ratchets.ps1`.

ATTENTION -- NE PAS CONFONDRE LES DEUX CHIFFRES. La simulation sur les durees par fichier (mesurees SOUS
CHARGE) annoncait un mur de 629 s a 8 shards ; le mur REEL, mesure ISOLE le 2026-08-02
(`ratchets.ps1 -Only probe_439,probe_440,probe_457`), est **297,8 s** -- shard le plus long 295,7 s,
le plus court 48,3 s. La simulation surestime parce qu'elle additionne des durees deja gonflees par
la contention. Le mur d'une banque ne se SIMULE pas, il se MESURE isole (cf. les 4 releves du meme
jour, 126,6 / 136,2 / 159,1 / 319,8 s, sur des compositions quasi identiques).

Sharder plus ne rachete pas son cout : le md5 regroupe les lourds, et le plancher irreductible
reste le fichier le plus lourd, insecable (268 s en serie sous charge). Le vrai levier est
d'alleger les balayages eux-memes (residu #457-r6).

NE PAS << regler >> ce cout en retrecissant le perimetre : c'est exactement la faute que #457-r5
repare. Chiffres a RE-DERIVER, jamais a citer.

LE PERIMETRE, ET POURQUOI CE CRITERE-LA
---------------------------------------
Le critere retenu est `not name.endswith("_live.py")`. Un critere plus fin a ete essaye puis
REFUTE PAR MESURE : classer par la CLOTURE DE FIXTURES (`"host" not in item.fixturenames`) rendait
153 fichiers << offline >>, dont des DIZAINES de `*_live.py` -- ils montent leur runner a la main,
sans passer par les fixtures `host`/`live_session`/`build_runner`. Joue tel quel, ce critere partait
monter des runners et depassait 600 s. Le suffixe, lui, est DECLARATIF et tenu par le depot.

La cloture de fixtures reste utilisee, mais comme FILET et non comme critere : un item d'un fichier
non-`_live.py` qui reclame quand meme une fixture live est DESELECTIONNE et RAPPORTE (mesure :
1 item, `test_act_of_faith_crit_resets_both_paths.py`, fichier MIXTE). On ne rougit pas dessus --
ce cliquet garde << les tests offline sont verts >>, pas << le nommage est parfait >>.

PERIMETRE (#434) : la liste vient de `git ls-files` lance dans CE checkout, donc elle ne peut pas
lire l'arbre d'un autre agent. ECRITURE (#455) : aucune -- `-p no:cacheprovider` empeche pytest de
deposer `.pytest_cache` sous `scripts/python/`, que la banque enumere en parallele.

CE PROBE EXIGE SON CWD, ET LE VERIFIE (#464)
--------------------------------------------
Les chemins passes a `pytest.main` sont relatifs au ROOTDIR (`scripts/python/pytest.ini`). Lance
d'ailleurs, pytest ne trouve aucun de ses arguments et rend `rc=4` -- une erreur d'USAGE, pas un
verdict. Mesure du 2026-08-04, depuis la racine du depot : `--measure` chronometrait 127 fichiers a
**0,0 s**, ecrivait une empreinte a **0 fichier de test**, soit **632 lignes supprimees** du fichier
VERSIONNE `scripts/ratchets-457-footprints.json` -- et annoncait << poids ecrits, mais l'arbre est
ROUGE >>, c'est-a-dire un rc de gisement pour un echec de MONTAGE. C'est le patron << un echec RENDU
se lit comme une mesure >>, en pire : il PERSISTE, et une empreinte videe ne selectionne pas TROP
(ce que la peremption normale fait, cf. `_footprints_path`) mais TROP PEU -- `impacted_files`
interprete << absent de `par_test` >> comme << aucune dependance hors-.py >>, donc un FAUX VERT.

Deux verrous, dans cet ordre :
  1. `_exiger_cwd()` REFUSE avant de jouer quoi que ce soit (rc `EX_NON_MESURE`) ;
  2. `_ecrire_mesure()` est le FOYER UNIQUE d'ecriture et refuse encore si pytest a rendu un rc
     d'usage/interruption, ou si AUCUN fichier n'a produit de report -- le filet couvre ce que le
     CWD ne cause pas (un fichier disparu entre `git ls-files` et l'execution, un `-x` interrompu).

`EX_NON_MESURE = 99` est la convention deja tenue par `scripts/ratchets-bg.ps1` : << aucun verdict
sur le depot >>, a ne JAMAIS lire comme un rouge de gisement (ni comme un vert).

L'EMPREINTE NE DOIT RIEN AU `__pycache__` DE LA MACHINE (#464-r2)
-----------------------------------------------------------------
Le hook d'audit compte comme lecture GLOBALE tout `open` fait hors d'un test. Or, SANS bytecode,
l'import ouvre la SOURCE `.py` -- et la mesure devenait donc une fonction de l'etat du cache de la
machine. Mesure du 2026-08-04, MEME arbre, MEME probe :

| regime | `_globales` ecrites | dont `.py` | dont NON-`.py` |
| --- | --- | --- | --- |
| worktree FROID (0 `__pycache__`) | **552** | 549 | 3 |
| arbre CHAUD | **9** | 6 | 3 |

Les 3 NON-`.py` sont les MEMES des deux cotes (`data/seed-bc.json`, `data/symbols/CURRENT`,
`scripts/python/pytest.ini`) : le noyau utile etait stable, tout le reste etait du bytecode.

ATTENTION -- L'effet REEL de ce bruit n'est PAS celui qu'on croit, et la mesure le tranche : un `.py` du
domaine place dans `_globales` **n'a AUCUN effet quand LUI-MEME change** -- `impacted_files`
construit `hors_py = [c for c in changes if c not in mods]`, donc un module de `scripts/python`
n'est JAMAIS confronte a `_globales`. Son seul effet residuel passait par `dirs_glob` : un fichier
NON-`.py` du meme REPERTOIRE forcait le rejeu total. Un diff purement Python ne declenchait donc
jamais << TOUT rejoue >> par cette voie.

**RIEN N'EST FILTRE** -- la CAUSE est traitee. `--measure` PRECHAUFFE le bytecode
(`_prechauffer_bytecode`) avant d'installer le hook, et un GARDE DE REGIME refuse d'ecrire
l'empreinte si un module du domaine est quand meme lu en global (signe que le prechauffage n'a pas
pris). Mesure sur echantillon : **355** lectures brutes sans prechauffage, **2** avec, et
froid == chaud.

ATTENTION -- **La piste << filtrer les `.py` des globales >> a ete essayee, puis ECARTEE par mesure.** Elle
ferme `_globales` mais pas `par_test`, ou un import LAZY execute pendant un test attribue au test
une source `.py` (45 entrees a chaud contre 52 a froid). Et la, le filtre ne PEUT pas etre etendu :
`par_test` porte **420** couples (test, repertoire-de-code) meme a chaud, parce que ce depot est
plein de tests-BALAYAGE qui OUVRENT le code source pour l'analyser. Ces lectures ne sont couvertes
par aucun import, donc par aucune preuve -- les retirer serait le faux vert de #464.

Fermer la cause a tout de meme exige de fermer un trou du graphe, decouvert en cherchant la preuve
de couverture : cf. `_conftest_edges`.

MESURE INCREMENTALE (#463)
--------------------------
`--measure` rejoue TOUT le perimetre : mesure du 2026-08-04, **976,9 s pour 1471 tests**. Un fichier
de test offline NEUF n'a pas de poids, prend le poids MAXIMUM connu dans `bins_of`, et desequilibre
la partition -- ce qui faisait de cette passe complete le seul remede a une garde d'equilibrage,
soit ~12 min BLOQUANTES par PR pour une OPTIMISATION de mur.

`--measure-missing` ne chronometre que les fichiers SANS poids et FUSIONNE dans le JSON existant.
C'est le cas nominal (mediane 0-1 fichier offline neuf par PR) : quelques secondes au lieu de 12 min.

Il n'ecrit PAS l'empreinte, et c'est structurel : `_commit` horodate l'empreinte ENTIERE, donc le
rafraichir apres n'avoir joue que 2 fichiers pretendrait une fraicheur qu'elle n'a pas et
transformerait `impacted_files` en faux vert. L'asymetrie est celle que `_weights_path` et
`_footprints_path` documentent deja : des POIDS perimes coutent du MUR, une EMPREINTE perimee
ferait sauter des tests. Rafraichir l'empreinte reste le travail de `--measure` complet.

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import time
from pathlib import Path

import pytest

#: Fixture RACINE du monde live. La cloture calculee par pytest (`item.fixturenames`) est
#: TRANSITIVE : un item qui reclame `live_runner` -> `build_runner` -> `host` porte les trois.
#: Verifie le 2026-08-02 sur les 512 fichiers collectes -- `host` et `live_session` couvrent
#: EXACTEMENT les memes 359 fichiers, et `rpc`/`build_runner`/`live_runner` en sont des
#: sous-ensembles stricts (294 / 248 / 2). Une seule racine suffit donc a tous les reconnaitre.
LIVE_FIXTURE_ROOT = "host"

#: Repertoire des tests (`testpaths = tests` dans `pytest.ini`). C'est un PATHSPEC DE REPERTOIRE,
#: pas un glob : `git ls-files <dir>` descend recursivement, sans semantique `**` a deviner.
#:
#: ATTENTION #457-r5 : la forme precedente etait `scripts/python/tests/**/test_*.py`, et `**/` EXIGE un
#: niveau intermediaire -- les fichiers poses DIRECTEMENT dans `tests/` en etaient exclus.
#: Mesure du 2026-08-02 : 496 fichiers avec `**`, 519 sans, soit 23 invisibles, dont 21 que AUCUNE
#: entree de la banque ne jouait (les 2 autres etant nommes a la main par `pytest_signatures` et
#: `pytest_attestations`). C'est le vice de #458 (`Path.match` n'etend pas `**`) sur un autre outil.
TESTS_DIR = "scripts/python/tests"


def _is_test_file(name: str) -> bool:
    """Convention de collecte de pytest, laissee au DEFAUT par `pytest.ini` (pas de `python_files`).

    Les DEUX formes comptent. `*_test.py` n'existe pas dans le depot aujourd'hui, mais un perimetre
    DERIVE doit couvrir ce que pytest collecte, pas ce qui se trouve exister -- sinon le prochain
    fichier ainsi nomme rouvre exactement le trou qu'on vient de fermer."""
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))

_PYDIR = Path(__file__).resolve().parent

#: rc << RIEN N'A ETE MESURE >>. Convention deja tenue par `scripts/ratchets-bg.ps1` (`rc=99` =
#: MONTAGE EN ECHEC, aucun verdict sur le depot). Un appelant DOIT le traiter comme
#: << non mesure >>, jamais comme un rouge de gisement -- ni comme un vert.
EX_NON_MESURE = 99

#: Codes pytest sous lesquels la mesure n'est PAS exploitable : 2 interrompu, 3 erreur interne,
#: 4 erreur d'USAGE, 5 aucun test collecte. `0` et `1` le sont -- des tests ROUGES n'invalident ni
#: les durees ni l'empreinte, les fichiers ont bien ete joues.
RC_PYTEST_SANS_MESURE = (2, 3, 4, 5)


def repo_root() -> Path:
    """Racine du checkout COURANT. Depuis un worktree, c'est le worktree -- jamais l'arbre
    principal (#434 : un cliquet ne balaie QUE son propre checkout)."""
    return _PYDIR.parents[1]


def _exiger_cwd() -> str:
    """`""` si le CWD permet de jouer, sinon le message de REFUS (#464).

    Les chemins passes a `pytest.main` sont relatifs au ROOTDIR, que `pytest.ini` fixe a
    `scripts/python`. Lance d'ailleurs, pytest rend `rc=4` (usage) et le probe ecrivait quand meme
    -- 632 lignes retirees d'un fichier VERSIONNE. On VERIFIE et on REFUSE plutot que de produire
    du garbage : c'est le geste que l'echec de montage exige, pas un repli silencieux.

    Pourquoi refuser au lieu de `chdir` : un `chdir` implicite masquerait un appelant mal cable
    (`ratchets.ps1` fait `Set-Location scripts\\python`, c'est SA responsabilite) et rendrait le
    diagnostic invisible la prochaine fois. `--list` n'invoque pas pytest et n'est donc pas garde.
    """
    ici = Path.cwd().resolve()
    if ici == _PYDIR:
        return ""
    return ("[457] REFUS : ce probe doit etre lance depuis `%s` (les chemins passes a pytest sont\n"
            "[457] relatifs au rootdir de `pytest.ini`). CWD courant : `%s`.\n"
            "[457] rc=%d -- RIEN n'a ete joue, RIEN n'a ete ecrit. Ce n'est PAS un verdict sur le "
            "depot." % (_PYDIR, ici, EX_NON_MESURE))


def candidate_files() -> list[str]:
    """Les fichiers de test NON `_live.py`, en chemins relatifs a `scripts/python`.

    Passe par `git ls-files` : seul l'index de CE checkout est consulte, donc ni les worktrees
    voisins ni les fichiers non suivis n'y entrent. Tri stable -- le shard doit etre reproductible.

    Le REPERTOIRE est passe a git (qui descend seul), et la selection des fichiers se fait ICI, en
    Python : c'est ce qui rend le perimetre relisable et testable, au lieu de dependre de la
    semantique d'un glob (#457-r5)."""
    out = subprocess.run(["git", "ls-files", TESTS_DIR], capture_output=True, text=True,
                         cwd=str(repo_root()), check=True)
    prefix = "scripts/python/"
    rels = []
    for line in out.stdout.splitlines():
        rel = line.strip()
        if not rel or rel.endswith("_live.py") or not rel.startswith(prefix):
            continue
        if not _is_test_file(rel.rsplit("/", 1)[-1]):
            continue
        rels.append(rel[len(prefix):])
    return sorted(rels)


def shard_of(rel: str, total: int) -> int:
    """Shard STABLE d'un fichier : md5 du chemin relatif, modulo `total`.

    Stable = independant de l'ordre et du nombre de fichiers, donc l'ajout d'un fichier ne
    redistribue pas les autres (un modulo sur l'INDEX du tri, lui, decale tout le monde).

    C'est le REPLI, utilise quand aucun poids n'est disponible. Il repartit par NOMBRE, pas par
    COUT -- mesure du 2026-08-02 : il avait concentre 4 fichiers lourds dans le seul `s7`
    (106 s isole, contre 4,8 s pour `s3`), et ce shard-la faisait A LUI SEUL tout le mur de la
    banque (234,7 s sur 234,8). D'ou `bins_of` ci-dessous."""
    digest = hashlib.md5(rel.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % total


#: Poids MESURES (secondes par fichier), regeneres par `--measure`. VERSIONNE a dessein : sans
#: lui, un checkout frais retomberait sur le repli md5 et paierait le mur que #457-r6 corrige.
#:
#: Ces poids ne conditionnent QUE la repartition. Perimes, ils coutent du MUR -- jamais un faux
#: vert, jamais un trou : `bins_of` partitionne l'ENSEMBLE des fichiers quels que soient les
#: poids, et la garde `test_457_r5_perimetre_offline.py` verifie l'union stricte des bins.
#:
#: SOUS `logs/`, JAMAIS sous `scripts/python/` (#455). Premiere version de ce mode : les poids
#: etaient ecrits a cote du probe -- `probe_440` a ROUGI, a raison. La banque tourne en PARALLELE
#: et plusieurs cliquets ENUMERENT `scripts/python/**` : y creer un fichier le fait apparaitre
#: puis disparaitre sous les pieds d'un voisin. Le prix a payer est que `logs/` est gitignore,
#: donc un checkout frais (un worktree d'agent) retombe sur le repli md5 : mur sous-optimal,
#: verdict INCHANGE. C'est le bon arbitrage -- la correction prime sur le mur.
def _weights_path():
    return repo_root() / "logs" / "ratchets" / "457-durations.json"


def _weights() -> dict:
    """Les poids mesures, ou `{}` s'ils sont absents/illisibles (-> repli md5)."""
    path = _weights_path()
    if not path.exists():
        return {}
    try:
        import json
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in raw.items()}
    except Exception:
        return {}


def bins_of(files: list, total: int, weights: dict) -> list:
    """Partitionne `files` en `total` paquets EQUILIBRES PAR COUT (LPT).

    LPT (longest processing time first) : on place le plus lourd d'abord, toujours dans le paquet
    le moins charge. Heuristique classique, bornee a 4/3 de l'optimal -- amplement suffisant ici.

    DETERMINISTE : le tri porte sur `(-poids, chemin)`, donc deux shards du MEME run calculent
    exactement la meme partition. C'est ce qui interdit qu'un fichier tombe dans zero paquet --
    le mode de defaillance a eviter, puisqu'il serait SILENCIEUX (un fichier jamais joue, sous un
    verdict vert). Un fichier sans poids prend le poids MAXIMUM connu : on ignore son cout, on le
    suppose donc le pire (le choix sur, symetrique de l'ordonnancement de la banque)."""
    if total < 1:
        raise ValueError("total doit etre >= 1")
    defaut = max(weights.values()) if weights else 1.0
    charge = [0.0] * total
    paquets = [[] for _ in range(total)]
    for rel in sorted(files, key=lambda r: (-weights.get(r, defaut), r)):
        i = min(range(total), key=lambda j: (charge[j], j))
        paquets[i].append(rel)
        charge[i] += weights.get(rel, defaut)
    return [sorted(p) for p in paquets]


def equilibre_des_bins(files: list, total: int, weights: dict) -> dict:
    """Diagnostic de l'equilibre de la partition, SUR LES SEULS FICHIERS PESES (#463).

    Un fichier SANS poids prend le maximum connu dans `bins_of` (choix sur), donc il DEPLACE les
    vrais lourds et fait monter la charge maximale -- sans qu'aucun poids ne soit faux. Mesurer
    l'equilibre sur l'ensemble complet melangeait donc deux choses : la qualite de l'heuristique
    (ce qu'on veut garder) et l'absence de donnees (ce qu'on veut seulement RAPPORTER).

    `ratio = max(charges) / max(plancher, moyenne)` : le plancher est le fichier le PLUS LOURD,
    insecable -- on ne peut pas exiger mieux que lui.
    """
    peses = [rel for rel in files if rel in weights]
    inconnus = [rel for rel in files if rel not in weights]
    charges = [sum(weights[r] for r in b) for b in bins_of(peses, total, weights)] if peses else []
    plancher = max((weights[r] for r in peses), default=0.0)
    moyenne = (sum(charges) / len(charges)) if charges else 0.0
    reference = max(plancher, moyenne)
    return {
        "peses": peses,
        "inconnus": inconnus,
        "charges": charges,
        "plancher": plancher,
        "moyenne": moyenne,
        "ratio": (max(charges) / reference) if charges and reference > 0 else 0.0,
    }


class _DeselectLiveItems:
    """Retire les items dont la cloture de fixtures touche le monde live, et les RAPPORTE."""

    def __init__(self) -> None:
        self.kept = 0
        self.dropped_items = 0
        self.dropped_files: set[str] = set()

    def pytest_collection_modifyitems(self, session, config, items):   # noqa: D102
        keep = []
        for item in items:
            if LIVE_FIXTURE_ROOT in set(getattr(item, "fixturenames", ())):
                self.dropped_items += 1
                self.dropped_files.add(str(item.path))
            else:
                keep.append(item)
        self.kept = len(keep)
        items[:] = keep


class _TimePerFile:
    """Accumule setup+call+teardown PAR FICHIER, pour regenerer les poids en UN SEUL passage.

    Mesurer fichier par fichier couterait 110 demarrages de process (3,1 s piece, soit ~340 s de
    pur demarrage) et surestimerait chaque fichier de ce meme cout fixe -- deux fois faux."""

    def __init__(self) -> None:
        self.sec: dict = {}
        self.n: dict = {}

    def pytest_runtest_logreport(self, report):                       # noqa: D102
        # Le NODEID, pas `fspath` : mesure du 2026-08-02, `fspath` ne correspondait pas aux cles
        # pour 13 des 111 fichiers (sous-repertoires a conftest imbrique) -- ils ressortaient a
        # 0 s alors qu'ils collectaient et passaient leurs tests. Le nodeid, lui, commence
        # TOUJOURS par le chemin relatif au rootdir, separateurs `/`.
        nodeid = str(getattr(report, "nodeid", "") or "")
        rel = nodeid.split("::")[0].replace("\\", "/")
        if not rel:
            rel = str(getattr(report, "fspath", "")).replace("\\", "/")
        if rel:
            self.sec[rel] = self.sec.get(rel, 0.0) + float(getattr(report, "duration", 0.0) or 0.0)
            self.n[rel] = self.n.get(rel, 0) + 1


class _FilesPerTest:
    """EMPREINTE MESUREE : quels fichiers du depot chaque fichier de test ouvre REELLEMENT.

    C'est la piece qui permet une selection par diff SANS table ecrite a la main. Le graphe
    d'imports ne voit que les dependances `import` ; un test qui lit `data/...` ou `docs/...` en
    est invisible, et c'est exactement la ou une selection naive produirait un FAUX VERT.

    Deux seaux, et la distinction est ce qui rend l'empreinte SURE :
      * `par_test`  -- lectures faites PENDANT un test (on sait a qui les attribuer) ;
      * `globales`  -- lectures faites hors de tout test (collecte, import de module, conftest).
        Elles ne sont attribuables a personne, donc tout changement les touchant impacte TOUS les
        fichiers. Conservateur par construction -- jamais l'inverse.
    """

    def __init__(self, root) -> None:
        self.root = str(root).replace("\\", "/").rstrip("/") + "/"
        self._prefixe = self.root.lower()
        self._n = len(self.root)
        self.par_test: dict = {}
        self.globales: set = set()
        self.courant = None
        sys.addaudithook(self._hook)

    def _hook(self, event, args):
        # Chemin CHAUD : appele a chaque `open` du process. Sortir au plus vite.
        if event != "open":
            return
        p = args[0]
        if type(p) is not str or len(p) <= self._n:
            return
        q = p.replace("\\", "/")
        if not q.lower().startswith(self._prefixe):
            return
        rel = q[self._n:]
        if self.courant is None:
            self.globales.add(rel)
        else:
            self.par_test.setdefault(self.courant, set()).add(rel)

    def pytest_runtest_logstart(self, nodeid, location):               # noqa: D102
        self.courant = str(nodeid).split("::")[0].replace("\\", "/")

    def pytest_runtest_logfinish(self, nodeid, location):              # noqa: D102
        self.courant = None


def _ecrire_mesure(perimetre: list, joues: list, horloge, empreinte, rc: int,
                   elapsed: float, poids_connus: dict) -> int:
    """FOYER UNIQUE d'ecriture de ce probe (#464). DECIDE d'abord, ecrit ensuite -- jamais l'inverse.

    Le vice repare : `--measure` ecrivait, PUIS annoncait << poids ecrits, mais l'arbre est ROUGE >>
    sur un `pytest rc=4` qui n'est pas un rouge du tout mais une erreur d'USAGE. Un echec de montage
    RENDU se lit comme une mesure ; ici il se PERSISTAIT, dans un fichier versionne.

    Le critere du refus est le NOMBRE DE REPORTS, jamais la duree : un fichier offline pur peut
    passer ses 4 tests en moins de 5 ms (mesure du 2026-08-02 -- l'arrondi a 2 decimales rendait 13
    puis 15 fichiers << sans mesure >>, signature d'un seuil, pas d'un fichier muet). Ce qui ne peut
    PAS arriver en regime normal, c'est que le perimetre ENTIER soit muet.

    `empreinte is None` = mesure incrementale : on ne touche pas au fichier versionne, cf. `main`.
    """
    import json

    mesures = [rel for rel in joues if horloge.n.get(rel, 0) > 0]
    if rc in RC_PYTEST_SANS_MESURE or not mesures:
        cause = ("pytest rc=%d (%s)" % (rc, {2: "interrompu", 3: "erreur interne",
                                             4: "erreur d'USAGE -- rien n'a ete joue",
                                             5: "aucun test collecte"}.get(rc, "non exploitable"))
                 if rc in RC_PYTEST_SANS_MESURE
                 else "aucun des %d fichier(s) joue(s) n'a produit le moindre report" % len(joues))
        print("[457] REFUS D'ECRIRE : %s." % cause)
        print("[457] Les poids ET l'empreinte sont INCHANGES -- une mesure vide ecrite serait pire")
        print("[457] que pas de mesure : une empreinte a zero fichier fait SAUTER des tests sous")
        print("[457] `--since` (absent de `par_test` = << aucune dependance hors-.py >>).")
        print("[457] Cause la plus frequente : lancement hors `%s`." % _PYDIR)
        print("[457] rc=%d -- aucun verdict sur le depot." % EX_NON_MESURE)
        return EX_NON_MESURE

    # FUSION (mode incremental) puis RESTRICTION au perimetre : un fichier de test supprime ne
    # doit pas laisser son poids derriere lui -- il gonflerait le `defaut` de `bins_of` pour rien.
    poids = {rel: poids_connus[rel] for rel in perimetre if rel in poids_connus}
    poids.update({rel: round(horloge.sec.get(rel, 0.0), 3) for rel in joues})
    manquants = [rel for rel in joues if horloge.n.get(rel, 0) == 0]

    path = _weights_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(poids, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    empreinte_refusee = False
    if empreinte is not None:
        # Empreinte MESUREE -- VERSIONNEE, avec le commit qui l'horodate (cf. `_footprints_path`).
        # Sans `_commit`, la selection ne peut pas mesurer son age et refuse de s'appliquer.
        import subprocess as _sp
        tete = _sp.run(["git", "-C", str(repo_root()), "rev-parse", "HEAD"],
                       capture_output=True, text=True)

        def _versionnable(r: str) -> bool:
            # Bruit MACHINE, jamais dans un diff : bytecode et sorties de run. Les garder gonflerait
            # un fichier versionne de 521 lignes illisibles (mesure) sans rien apporter -- ils sont
            # deja ignores a la lecture.
            return not (r.endswith(".pyc") or "__pycache__" in r or r.startswith("logs/"))

        def _dossiers(chemins) -> list:
            # On stocke les REPERTOIRES, pas les fichiers -- c'est exactement la granularite a
            # laquelle `impacted_files` compare (un test qui lit `docs/rl/x.md` doit rejouer si
            # `docs/rl/y.md` change, sinon un fichier NEUF passerait entre les mailles). Stocker
            # chaque fichier ne rendrait AUCUNE precision, et pesait 961 Ko versionnes.
            return sorted({c.rsplit("/", 1)[0] for c in chemins if _versionnable(c) and "/" in c})

        # GARDE DE REGIME (#464-r2). Un module du domaine lu GLOBALEMENT signe un bytecode qui
        # n'etait pas a jour : `import` a ouvert la SOURCE. L'empreinte decrirait alors le
        # `__pycache__` de la machine (mesure : 552 globales a froid contre 3 a chaud) -- et elle
        # est VERSIONNEE, donc le defaut serait propage. On REFUSE de l'ecrire.
        modules = _modules_du_graphe()
        brutes = [g for g in empreinte.globales if _versionnable(g)]
        modules_globaux = sorted(g for g in brutes if _est_module_du_domaine(g, modules))
        if modules_globaux and not _echappatoire_regime():
            print("[457] REFUS D'ECRIRE L'EMPREINTE : %d module(s) du domaine lu(s) en GLOBAL, "
                  "donc le bytecode n'etait pas a jour au moment de la mesure."
                  % len(modules_globaux))
            for rel in modules_globaux[:5]:
                print("        %s" % rel)
            print("[457] Une empreinte mesuree dans ce regime decrit le __pycache__ de la machine,")
            print("[457] pas le depot -- et elle est VERSIONNEE. Les POIDS, eux, sont ecrits.")
            print("[457] Causes usuelles : PYTHONDONTWRITEBYTECODE=1, `logs/` non ecrivable, ou un")
            print("[457] module non compilable. Remede : relancer `--measure` (le prechauffage a")
            print("[457] deja tourne). Echappatoire CONSCIENTE si la lecture est APPLICATIVE")
            print("[457] (un conftest qui lit un .py comme DONNEE) : %s=1" % _ENV_ECHAPPATOIRE)
            empreinte_refusee = True
        else:
            emp_path = _footprints_path()
            emp = {
                "_commit": (tete.stdout or "").strip() or None,
                "_regime": REGIME_MESURE,
                "_globales": sorted(brutes),
                "par_test": {rel: d for rel, d in
                             ((r, _dossiers(v)) for r, v in sorted(empreinte.par_test.items()))
                             if d},
            }
            emp_path.write_text(json.dumps(emp, indent=1, sort_keys=True) + "\n",
                                encoding="utf-8")

            hors_py = sorted({r for r in emp["_globales"] if not r.endswith(".py")})
            hors_py_test = sorted({r for v in empreinte.par_test.values() for r in v
                                   if not r.endswith(".py")})
            print("[457] empreinte -> %s : %d fichier(s) de test, %d lecture(s) GLOBALE(s) "
                  "(non attribuables -> impactent TOUT), dont %d hors .py ; %d fichier(s) hors .py "
                  "lus pendant les tests"
                  % (emp_path, len(emp["par_test"]), len(emp["_globales"]), len(hors_py),
                     len(hors_py_test)))
    else:
        print("[457] empreinte NON REECRITE (mesure incrementale) : `_commit` horodate l'empreinte")
        print("[457] ENTIERE -- la rafraichir apres n'avoir joue que %d fichier(s) pretendrait une"
              % len(joues))
        print("[457] fraicheur qu'elle n'a pas. `--measure` complet reste la voie pour l'empreinte.")

    joue = sum(round(horloge.sec.get(rel, 0.0), 3) for rel in joues)
    print("[457] %d fichier(s) joue(s), %.1f s de tests mesures en %.1f s de mur ; %d poids -> %s"
          % (len(joues), joue, elapsed, len(poids), path))
    for rel in sorted(joues, key=lambda r: -horloge.sec.get(r, 0.0))[:5]:
        print("    %7.1f s  %s" % (horloge.sec.get(rel, 0.0), rel))
    if manquants:
        # Un fichier a 0 s n'est pas anodin : il n'a produit AUCUN report (collecte vide, items
        # tous deselectionnes). Le dire -- il garde un poids nul, jamais le maximum.
        print("[457] %d fichier(s) sans mesure (0 report) : %s"
              % (len(manquants), ", ".join(manquants[:5])))
    if rc != 0:
        print("[457] pytest rc=%d -- poids ecrits (les fichiers ONT ete joues), mais l'arbre est "
              "ROUGE" % rc)
        return 1
    if empreinte_refusee:
        # Le GISEMENT est vert, mais le LIVRABLE << empreinte >> n'a pas ete produit. Ne pas rendre
        # 0 : un `--measure` qui n'ecrit pas l'empreinte et se tait passerait pour une maintenance
        # faite. `EX_NON_MESURE` est deja la convention << ce run n'a pas produit sa mesure >>.
        print("[457] rc=%d -- l'arbre est VERT, mais l'EMPREINTE n'a pas ete produite (cf. ci-dessus)"
              % EX_NON_MESURE)
        return EX_NON_MESURE
    return 0


def _pycache_prefix():
    """Ou le bytecode de la MESURE est ecrit -- surtout PAS `scripts/python/**/__pycache__`.

    `sys.pycache_prefix` (CPython >= 3.8) redirige tout le bytecode vers une arborescence miroir.
    Deux raisons, dans cet ordre :

      1. #455 -- un cliquet n'ECRIT JAMAIS dans `scripts/python` : la banque tourne en parallele et
         plusieurs cliquets ENUMERENT cet arbre. Faire apparaitre des dizaines de `__pycache__`
         pendant qu'un voisin le parcourt est exactement la course mesuree entre `probe_455` et
         `probe_391`.
      2. #464-r2 -- le prechauffage doit etre REPRODUCTIBLE. Sous `logs/` (gitignore, deja le foyer
         des poids), il survit d'une mesure a l'autre sans jamais entrer dans un diff.
    """
    return repo_root() / "logs" / "ratchets" / "457-pycache"


def _prechauffer_bytecode() -> tuple:
    """Compile `scripts/python/**` AVANT de poser le hook. `(compiles, secondes)`.

    LA CAUSE de #464-r2, traitee a sa racine. Sans bytecode a jour, `import` ouvre la SOURCE `.py`
    -- et le hook d'audit `open` compte cette ouverture comme une lecture du depot. Mesure du
    2026-08-04, MEME arbre MEME probe : `_globales` = 552 a froid contre 3 a chaud, et `par_test`
    = 52 entrees contre 47. L'empreinte decrivait donc l'etat du `__pycache__` de la machine.

    Le prechauffage RETIRE la cause au lieu de filtrer le symptome -- il ne fait disparaitre AUCUNE
    information : une lecture applicative de `.py` (un test-BALAYAGE qui ouvre le code source pour
    l'analyser -- ils sont nombreux ici) reste un `open` bien reel, vu et attribue. C'est ce qui
    interdisait de simplement retirer les `.py` de `par_test` : ces lectures-la ne sont couvertes
    par AUCUN import, donc par aucune preuve.

    Best-effort assume : un echec de compilation n'interrompt pas la mesure -- c'est le GARDE DE
    REGIME de `_ecrire_mesure` qui la sanctionne, en refusant d'ecrire une empreinte qui decrirait
    le `__pycache__` plutot que le depot. Ce partage est deliberatif : ici on AGIT, la-bas on
    VERIFIE le resultat, jamais l'inverse.
    """
    import compileall
    import os

    prefixe = str(_pycache_prefix())
    sys.pycache_prefix = prefixe
    # `PYTHONPYCACHEPREFIX` EN PLUS, et c'est INDISPENSABLE : `workers != 1` fait compiler
    # `compile_dir` dans des SOUS-PROCESS, qui n'heritent PAS d'une affectation a
    # `sys.pycache_prefix` -- elle ne vit que dans l'interpreteur courant. Mesure du 2026-08-04 avec
    # `workers=0` seul : **1691** `.pyc` deposes dans `scripts/python/**/__pycache__` (violation
    # #455) contre 1030 dans le prefixe, et le GARDE DE REGIME a refuse l'empreinte sur **548**
    # modules lus en source. La variable d'environnement, elle, traverse le fork.
    os.environ["PYTHONPYCACHEPREFIX"] = prefixe

    avant = _pyc_dans_l_arbre()
    started = time.time()
    try:
        compileall.compile_dir(str(_PYDIR), quiet=2, workers=0, force=False)
    except Exception as exc:                                   # pragma: no cover - best effort
        print("[457] prechauffage bytecode INTERROMPU (%s) -- le garde de regime tranchera"
              % type(exc).__name__)
    fuite = _pyc_dans_l_arbre() - avant
    if fuite > 0:
        # Le DIRE tout de suite : sans cela, la cause ne se lit qu'a la fin, apres ~20 min.
        print("[457] ATTENTION -- %d fichier(s) .pyc ecrit(s) DANS scripts/python malgre le "
              "prefixe : le redirection n'a pas pris (#455 + #464-r2)" % fuite)
    return prefixe, time.time() - started


def _pyc_dans_l_arbre() -> int:
    """Combien de `.pyc` vivent sous `scripts/python` -- le temoin DIRECT que le prefixe a pris."""
    return sum(1 for _ in _PYDIR.rglob("*.pyc"))


def _measure(perimetre: list, seulement_manquants: bool = False) -> int:
    """Chronometre le perimetre (ou ses seuls fichiers SANS poids) et reecrit les poids. ASCII only."""
    if not perimetre:
        # Un perimetre vide n'est pas une mesure a zero : c'est un effondrement de perimetre
        # (`git ls-files` muet, checkout partiel). Le DIRE, et n'ecrire RIEN.
        print("[457] --measure : perimetre VIDE, rien a mesurer")
        print("[457] rc=%d -- aucun verdict sur le depot." % EX_NON_MESURE)
        return EX_NON_MESURE

    poids_connus = _weights() if seulement_manquants else {}
    if seulement_manquants:
        joues = [rel for rel in perimetre if rel not in poids_connus]
        if not joues:
            print("[457] --measure-missing : les %d fichier(s) du perimetre ont deja un poids, "
                  "rien a mesurer" % len(perimetre))
            return 0
        print("[457] --measure-missing : %d fichier(s) SANS poids sur %d ; les %d autres gardent "
              "leur mesure" % (len(joues), len(perimetre), len(perimetre) - len(joues)))
    else:
        joues = list(perimetre)

    horloge = _TimePerFile()
    filet = _DeselectLiveItems()
    # AVANT le hook : le bytecode a jour, sinon `import` ouvre les SOURCES et l'empreinte mesure le
    # `__pycache__` de la machine (#464-r2). Inutile en incremental -- il n'ecrit pas d'empreinte.
    if not seulement_manquants:
        ou, secs = _prechauffer_bytecode()
        print("[457] bytecode prechauffe en %.1f s -> %s (hors scripts/python, cf. #455)"
              % (secs, ou))
    # L'empreinte pose un audit hook GLOBAL et IRREVERSIBLE sur `open` : on ne l'installe que
    # lorsqu'on va reellement la reecrire, c'est-a-dire en mesure COMPLETE.
    empreinte = None if seulement_manquants else _FilesPerTest(repo_root())
    plugins = [horloge, filet] + ([empreinte] if empreinte is not None else [])
    started = time.time()
    rc = pytest.main(["-q", "-p", "no:cacheprovider", *joues], plugins=plugins)
    elapsed = time.time() - started

    return _ecrire_mesure(perimetre, joues, horloge, empreinte, int(rc), elapsed, poids_connus)


#: ---------------------------------------------------------------------------------------------
#: SELECTION PAR DIFF (`--since`). DEUX mecanismes COMPLEMENTAIRES, et le partage des roles est
#: STRICT : le graphe d'imports couvre l'axe `import` (tout `.py` du domaine), l'empreinte couvre
#: ce qu'aucun import ne revele -- un test qui lit `data/symbols/...`, `docs/...` ou
#: `frida/hooks/*.ts`.
#:
#: Le hook d'audit, lui, voyait AUSSI ce que la MACHINE fait faire a l'import : des `.pyc` quand le
#: cache est chaud, les SOURCES `.py` quand il est froid. Ni l'un ni l'autre n'est une information
#: sur le DEPOT -- d'ou le prechauffage et son garde de regime (#464-r2), qui suppriment la cause
#: au lieu de filtrer la trace.
#:
#: TOUT CE QUI N'EST PAS PROUVE IMPACTE. Un test sans empreinte, un module illisible, un import
#: dynamique, une empreinte absente : impacte. La selection ne peut que RETIRER des tests dont on
#: a montre l'independance -- jamais en retirer par defaut. C'est ce qui la separe d'une table
#: ecrite a la main, qui est le vice recurrent de ce depot (5 occurrences).
#: ---------------------------------------------------------------------------------------------

def _module_name(rel: str) -> str:
    nom = rel[len(TESTS_DIR.rsplit("/", 1)[0]) + 1:-3].replace("/", ".")
    return nom[:-len(".__init__")] if nom.endswith(".__init__") else nom


#: Ce que l'empreinte ATTESTE d'elle-meme, en clair dans le fichier versionne : elle a ete mesuree
#: bytecode a jour, donc aucune de ses lectures ne vient de la compilation d'un import. Chaine
#: CONSTANTE -- identique a froid et a chaud, donc aucun bruit de diff (#464-r2).
REGIME_MESURE = ("bytecode PRECHAUFFE avant la mesure -- aucune lecture GLOBALE ne provient d'un "
                 "import (garde de regime #464-r2)")

#: Echappatoire CONSCIENTE au garde de regime, sur le patron de `TACTICUS_ALLOW_GREEN_SKIP` (#455).
#: A n'employer que si la lecture globale d'un module est APPLICATIVE (un `conftest.py` qui ouvre
#: un `.py` comme DONNEE) -- pas pour faire taire un prechauffage en echec.
_ENV_ECHAPPATOIRE = "TACTICUS_457_ACCEPTE_PY_GLOBAUX"


def _echappatoire_regime() -> bool:
    import os
    return bool(os.environ.get(_ENV_ECHAPPATOIRE))


def _modules_du_graphe(racine=None) -> dict:
    """`{chemin relatif au depot -> nom de module}` pour tout `.py` VERSIONNE de `scripts/python`.

    FOYER UNIQUE du domaine (#464-r2). C'est A LA FOIS le domaine sur lequel `_import_graph`
    resout les imports, et l'ensemble que le filtre de `_couverte_par_le_graphe` consulte pour
    decider qu'une lecture globale est deja couverte. Les deriver separement -- une fois a
    l'ecriture de l'empreinte, une fois a sa lecture -- ouvrirait un ecart SILENCIEUX : une
    lecture retiree d'un cote sans etre couverte de l'autre est exactement le faux vert de #464.
    """
    import subprocess
    racine = racine or repo_root()
    r = subprocess.run(["git", "-C", str(racine), "ls-files", "scripts/python"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {l.strip(): _module_name(l.strip())
            for l in r.stdout.splitlines() if l.strip().endswith(".py")}


def _est_module_du_domaine(rel: str, modules) -> bool:
    """`True` si `rel` est un module du domaine du graphe (`_modules_du_graphe`).

    Sert au GARDE DE REGIME, PAS a filtrer (#464-r2). La nuance est le coeur de l'arbitrage :

    Un module du domaine lu PENDANT un import est couvert par le graphe -- mais le hook d'audit ne
    sait pas dire d'ou vient un `open`. Ce depot est plein de tests-BALAYAGE qui OUVRENT le code
    source pour l'analyser, et un `conftest.py` pourrait faire de meme A LA COLLECTE : cette
    lecture-la n'est couverte par AUCUN import, donc par aucune preuve. Retirer les modules des
    globales << parce qu'ils sont bruyants >> retirerait donc, un jour, un vrai signal -- exactement
    le faux vert de #464.

    D'ou le choix : on ne FILTRE pas, on traite la CAUSE (`_prechauffer_bytecode`) et on VERIFIE
    qu'elle a bien ete traitee. En regime nominal ce predicat ne designe plus rien.
    """
    return rel in modules


def _conftest_edges(mods: dict) -> dict:
    """Aretes de la semantique PYTEST, qu'aucune instruction `import` ne rend visibles.

    Un `conftest.py` s'applique a TOUT fichier de test de son repertoire et de ses
    sous-repertoires -- fixtures, hooks, `autouse`. Aucun test ne l'IMPORTE, donc le graphe
    purement syntaxique s'arretait sur lui, et tout ce qu'il importe lui-meme s'arretait la aussi.

    Mesure du 2026-08-04 sur `origin/master`, AVANT cette arete : changer n'importe lequel des 4
    `conftest.py` ne retenait que **2 fichiers de test sur 132** -- alors que
    `scripts/python/tests/conftest.py` porte `green_skip_guard` (le garde de #455),
    `pytest_runtest_makereport` et trois fixtures `autouse`. Le meme trou frappait donc, par
    transitivite, tout module importe par un conftest.

    Ce trou est INDEPENDANT du regime chaud/froid (un `conftest.py` est dans `mods`, donc il n'a
    jamais ete confronte a `_globales`). Il est ferme ICI parce que la couverture par le graphe
    est ce sur quoi #464-r2 s'appuie pour cesser de compter les modules : la preuve devait etre
    VRAIE, pas postulee.
    """
    conftests = [rel for rel in mods if rel.rsplit("/", 1)[-1] == "conftest.py"]
    tests = [rel for rel in mods if _is_test_file(rel.rsplit("/", 1)[-1])]
    aretes = {}
    for c in conftests:
        base = c.rsplit("/", 1)[0] + "/"
        cibles = {t for t in tests if t.startswith(base)}
        if cibles:
            aretes[c] = cibles
    return aretes


def _import_graph(mods: dict) -> tuple:
    """(qui-importe-qui inverse, modules a resolution INCERTAINE). Purement statique."""
    import ast as _ast
    from collections import defaultdict

    par_nom = defaultdict(set)
    for rel, m in mods.items():
        par_nom[m].add(rel)

    inverse = defaultdict(set)
    incertains = set()
    racine = repo_root()
    for rel in mods:
        try:
            arbre = _ast.parse((racine / rel).read_bytes())
        except (OSError, SyntaxError, ValueError):
            incertains.add(rel)          # illisible : on ne PRETEND pas savoir
            continue
        noms, dyn = set(), False
        for n in _ast.walk(arbre):
            if isinstance(n, _ast.Import):
                noms.update(a.name for a in n.names)
            elif isinstance(n, _ast.ImportFrom):
                if n.level:
                    dyn = True           # import relatif : non resolu ici
                if n.module:
                    noms.add(n.module)
                    noms.update(n.module + "." + a.name for a in n.names)
            elif isinstance(n, _ast.Call):
                f = n.func
                if (getattr(f, "attr", None) or getattr(f, "id", None)) in (
                        "import_module", "__import__", "load_module", "exec_module"):
                    dyn = True
        if dyn:
            incertains.add(rel)
        for nom in noms:
            morceaux = nom.split(".")
            for i in range(len(morceaux), 0, -1):
                cle = ".".join(morceaux[:i])
                if cle in par_nom:
                    for cible in par_nom[cle]:
                        inverse[cible].add(rel)
                    break

    # La semantique pytest, que l'AST ne peut PAS voir (aucun test n'importe son conftest).
    for conf, cibles in _conftest_edges(mods).items():
        inverse[conf].update(cibles)
    return inverse, incertains


#: L'empreinte est VERSIONNEE, contrairement aux poids -- et l'asymetrie est le point.
#: Des POIDS perimes coutent du MUR, jamais un faux vert : ils ne font que deplacer des fichiers
#: entre shards. Une EMPREINTE perimee, elle, ferait SAUTER des tests. La versionner telle quelle
#: convertirait donc un defaut local en faux vert PARTAGE.
#: Ce qui la rend versionnable : elle porte le commit ou elle a ete mesuree, et `impacted_files`
#: unit le diff de la PR avec TOUT ce qui a change depuis. Perimee, elle selectionne TROP -- et
#: retombe continument sur le rejeu total a mesure qu'elle vieillit. Meme classe de surete que les
#: poids, sans en partager la fragilite.
#: Placee sous `scripts/`, PAS sous `scripts/python/` (#455 : la banque y enumere en parallele) et
#: PAS sous `data/`, qui est reserve aux ENTREES du jeu et dont un cliquet garde la composition.
def _footprints_path():
    return repo_root() / "scripts" / "ratchets-457-footprints.json"


def _footprints() -> dict:
    import json
    for p in (_footprints_path(), _weights_path().parent / "457-footprints.json"):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {}
    return {}


def _changed(ref: str) -> list:
    import subprocess
    r = subprocess.run(["git", "-C", str(repo_root()), "diff", "--name-only", ref, "HEAD"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None
    return sorted({l.strip() for l in r.stdout.splitlines() if l.strip()})


def impacted_files(perimetre: list, ref: str) -> tuple:
    """(sous-ensemble du perimetre a rejouer, raison). Retourne le perimetre ENTIER si un doute
    subsiste -- et la raison le DIT, pour qu'un rejeu total ne se lise jamais comme une mesure."""
    changes = _changed(ref)
    if changes is None:
        return perimetre, "ref `%s` inconnue de git -- TOUT rejoue" % ref
    if not changes:
        return [], "aucun fichier change entre %s et HEAD" % ref

    emp = _footprints()
    if not emp:
        return perimetre, "AUCUNE empreinte mesuree (`--measure`) -- TOUT rejoue"

    # INVALIDATION PAR L'AGE. L'empreinte decrit l'arbre tel qu'il etait au commit `_commit` ; tout
    # ce qui a bouge depuis peut l'avoir invalidee. On UNIT donc ce diff-la a celui de la PR. Sans
    # cela, versionner l'empreinte transformerait sa peremption en FAUX VERT partage.
    mesure_a = emp.get("_commit")
    if not mesure_a:
        return perimetre, "empreinte SANS commit de mesure -- age inverifiable, TOUT rejoue"
    depuis = _changed(mesure_a)
    if depuis is None:
        return perimetre, ("commit de mesure `%s` inconnu de git -- empreinte inverifiable, "
                           "TOUT rejoue" % mesure_a[:8])
    if depuis:
        changes = sorted(set(changes) | set(depuis))

    racine = repo_root()
    mods = _modules_du_graphe(racine)

    inverse, incertains = _import_graph(mods)

    # Cloture arriere du graphe d'imports sur les .py changes.
    touches, pile = set(), [c for c in changes if c in mods]
    while pile:
        x = pile.pop()
        if x in touches:
            continue
        touches.add(x)
        pile.extend(inverse.get(x, ()))

    # Les GLOBALES ne sont attribuables a personne -> tout changement les touchant impacte TOUT.
    # `.pyc` exclus : bytecode non versionne, jamais dans un diff.
    #
    # ATTENTION -- AUCUN autre retrait ici (#464-r2). Filtrer les modules du domaine a la LECTURE a ete
    # essaye puis ECARTE : rien ne distingue, dans une empreinte deja ecrite, la lecture d'IMPORT
    # (couverte par le graphe) de la lecture APPLICATIVE d'un `.py` par un conftest-balayage (qui
    # n'est couverte par rien). Le regime est garanti a l'ECRITURE, ou l'information existe encore.
    # Une empreinte ANCIENNE, mesuree avant ce correctif, garde donc ses `.py` : elle SUR-selectionne
    # -- le sens sur, et elle se regenere.
    globales = {g for g in emp.get("_globales", ()) if not g.endswith(".pyc")}
    dirs_glob = {g.rsplit("/", 1)[0] for g in globales if "/" in g}
    hors_py = [c for c in changes if c not in mods]
    for c in hors_py:
        d = c.rsplit("/", 1)[0] if "/" in c else ""
        if c in globales or d in dirs_glob:
            return perimetre, "changement dans une lecture GLOBALE (%s) -- TOUT rejoue" % c

    # Un fichier hors-.py impacte les tests dont l'empreinte lit son REPERTOIRE (granularite
    # repertoire : un test qui lit `docs/rl/x.md` doit rejouer si `docs/rl/y.md` change).
    # `par_test` stocke des REPERTOIRES (cf. `_dossiers` a l'ecriture). On tolere une empreinte
    # ancienne qui contiendrait encore des fichiers : en prendre le repertoire est idempotent.
    par_test = emp.get("par_test", {})
    dirs_par_test = {t: {x.rsplit("/", 1)[0] if "." in x.rsplit("/", 1)[-1] else x
                         for x in lus} | set(lus)
                     for t, lus in par_test.items()}

    dirs_changes = {c.rsplit("/", 1)[0] for c in hors_py if "/" in c} | set(hors_py)

    # NORMALISATION : `perimetre` et les cles de `par_test` sont relatifs a `scripts/python`
    # (nodeid pytest), `changes`/`touches`/`mods` sont relatifs au DEPOT. Comparer les deux formes
    # sans les ramener l'une a l'autre ne matcherait JAMAIS -- selection vide, donc faux vert.
    prefixe = "scripts/python/"
    changes_s = set(changes)

    retenus = []
    for rel in perimetre:
        abs_rel = prefixe + rel
        if abs_rel in changes_s or abs_rel in touches or abs_rel in incertains:
            retenus.append(rel)
        elif rel not in par_test:
            # Aucune empreinte pour ce fichier : il n'a ouvert AUCUN fichier du depot pendant ses
            # tests. Ses dependances sont donc d'import pur, deja couvertes par le graphe.
            continue
        elif dirs_par_test[rel] & dirs_changes:
            retenus.append(rel)
    raison = ("%d/%d fichier(s) impactes par %d changement(s) depuis %s"
              % (len(retenus), len(perimetre), len(changes), ref))
    return retenus, raison


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", default=None,
                    help="Ne joue que les fichiers IMPACTES par le diff <ref>..HEAD (empreinte "
                         "mesuree + graphe d'imports). Tout doute rejoue TOUT, et le dit.")
    ap.add_argument("--shard", default="0/1",
                    help="k/N -- ne joue que le shard k parmi N (defaut 0/1 = tout).")
    ap.add_argument("--list", action="store_true",
                    help="Imprime les fichiers du shard et sort, sans rien jouer.")
    ap.add_argument("--measure", action="store_true",
                    help="Joue TOUT le perimetre d'un bloc en chronometrant chaque fichier, puis "
                         "reecrit les poids ET l'empreinte versionnee. Rejeu COMPLET (mesure du "
                         "2026-08-04 : 976,9 s / 1471 tests) -- de la maintenance, pas une etape "
                         "de PR. A rejouer quand le mur derive ou que l'empreinte vieillit.")
    ap.add_argument("--measure-missing", action="store_true", dest="measure_missing",
                    help="Ne chronometre que les fichiers SANS poids et FUSIONNE dans les poids "
                         "existants (cas nominal : mediane 0-1 fichier offline neuf par PR). "
                         "N'ecrit PAS l'empreinte -- son `_commit` horodate l'empreinte ENTIERE.")
    args = ap.parse_args(argv)

    if args.measure and args.measure_missing:
        print("[457] --measure et --measure-missing s'excluent : le premier rejoue TOUT, le "
              "second complete.")
        return 2

    # GARDE DE CWD (#464), en tete : il couvre TOUT mode qui invoque pytest -- la mesure comme le
    # shard. `--list` n'invoque rien (l'enumeration passe par `git -C <racine>`, donc elle est
    # CWD-independante) et reste jouable de partout.
    # Sans lui, le shard lance hors `scripts/python` rendait `VERDICT: FAIL` sur un `rc=4` d'usage
    # (residu #457-r7), et `--measure` ecrivait du garbage PERSISTANT (#464).
    if not args.list:
        refus = _exiger_cwd()
        if refus:
            print(refus)
            return EX_NON_MESURE

    if args.measure or args.measure_missing:
        return _measure(candidate_files(), seulement_manquants=args.measure_missing)

    try:
        k_txt, n_txt = args.shard.split("/", 1)
        k, n = int(k_txt), int(n_txt)
    except ValueError:
        print("[457] --shard attend la forme k/N (ex. 0/3)")
        return 2
    if n < 1 or not (0 <= k < n):
        print("[457] --shard hors bornes : %s" % args.shard)
        return 2

    every = candidate_files()
    if args.since:
        # La selection s'applique AVANT le partitionnement : les shards se repartissent alors les
        # seuls fichiers impactes, donc N shards restent equilibres sur un perimetre reduit.
        every, raison = impacted_files(every, args.since)
        print("[457] --since %s : %s" % (args.since, raison))
        if not every:
            print("[457] aucun fichier impacte -- rien a jouer, VERDICT: PASS")
            return 0
    poids = _weights()
    if poids:
        mine = bins_of(every, n, poids)[k]
        mode = "cout mesure"
        charge = sum(poids.get(rel, 0.0) for rel in mine)
        # Un fichier de test offline NEUF n'a pas de poids : `bins_of` lui donne le MAXIMUM connu
        # (choix sur), donc il deplace les vrais lourds et degrade le mur -- sans qu'aucun poids ne
        # soit faux et sans le moindre risque de faux vert. Le DIRE ici, et nommer le remede a
        # quelques secondes ; c'est ce rapport qui remplace la passe complete de 976,9 s que la
        # garde d'equilibrage exigeait (#463).
        sans = [rel for rel in every if rel not in poids]
        if sans:
            print("[457] %d fichier(s) SANS poids (mur sous-optimal, verdict INCHANGE) : %s"
                  % (len(sans), ", ".join(sans[:3])))
            print("[457] les mesurer : cd scripts/python ; python %s --measure-missing"
                  % Path(__file__).name)
    else:
        # Repli : aucun poids disponible (checkout partiel, fichier supprime). Le cliquet reste
        # CORRECT -- il est seulement moins bien equilibre. Le dire, plutot que le taire.
        mine = [rel for rel in every if shard_of(rel, n) == k]
        mode = "REPLI md5 (poids absents -> mur sous-optimal)"
        charge = 0.0
    print("[457] %d fichier(s) de test non-`_live.py` ; shard %d/%d -> %d fichier(s) [%s%s]"
          % (len(every), k, n, len(mine), mode,
             ("", " ~%.0f s" % charge)[bool(charge)]))

    if args.list:
        for rel in mine:
            print("   ", rel)
        return 0

    if not mine and args.since:
        # SOUS `--since` un shard vide est LEGITIME : la selection a reduit le perimetre en dessous
        # du nombre de shards (mesure : un diff docs-only retient 4 fichiers pour 8 shards). Le
        # garde anti-effondrement reste ARME pour le cas normal ci-dessous -- le desarmer pour tout
        # le monde rouvrirait exactement le trou que la section 3 de la case-doc a ferme.
        print("[457] shard vide SOUS SELECTION (%d fichier(s) retenus pour %d shards) -- rien a "
              "jouer ici, ce n'est PAS un effondrement de perimetre" % (len(every), n))
        return 0

    if not mine:
        # Un shard vide n'est pas un succes : c'est le signe que le perimetre s'est effondre
        # (glob devenu faux, `git ls-files` muet). Le dire, plutot que rendre un vert.
        print("[457] FAIL shard VIDE -- le perimetre ne designe aucun fichier")
        return 1

    plugin = _DeselectLiveItems()
    started = time.time()
    # `-p no:cacheprovider` : aucune ecriture sous `scripts/python/` (#455 -- la banque enumere
    # cet arbre en parallele). `--import-mode=importlib` est deja dans `pytest.ini` ; on ne le
    # repete pas, pour que ce cliquet joue EXACTEMENT la configuration de production.
    rc = pytest.main(["-q", "-p", "no:cacheprovider", *mine], plugins=[plugin])
    elapsed = time.time() - started

    print("[457] %d test(s) joue(s) en %.1f s -- pytest rc=%d" % (plugin.kept, elapsed, int(rc)))
    if plugin.dropped_items:
        print("[457] %d item(s) DESELECTIONNE(S) (fixture live dans un fichier non-`_live.py`) :"
              % plugin.dropped_items)
        for path in sorted(plugin.dropped_files):
            try:
                shown = str(Path(path).relative_to(_PYDIR))
            except ValueError:
                shown = path
            print("    ", shown.replace("\\", "/"))
        print("[457] (rapporte, non bloquant : ce cliquet garde le VERT des offline, pas le nommage)")

    # #457-r7 : un rc d'USAGE / d'interruption ne dit RIEN sur le depot. Le traduire en
    # `VERDICT: FAIL` faisait lire << un test offline est rouge >> la ou RIEN n'avait tourne. Le
    # garde de CWD ci-dessus en couvre la cause de loin la plus frequente ; ceci est le filet
    # (fichier disparu entre `git ls-files` et l'execution, `-x` interrompu, erreur interne).
    # `rc=5` (aucun test collecte) reste un ROUGE : le shard a des fichiers, n'en collecter aucun
    # est anormal -- c'est le gisement de `probe_455` r3.
    if int(rc) in (2, 3, 4):
        print("[457] pytest rc=%d -- erreur d'USAGE ou interruption, AUCUN verdict sur le depot."
              % int(rc))
        print("[457] rc=%d : ne PAS le lire comme un rouge de gisement (ni comme un vert)."
              % EX_NON_MESURE)
        return EX_NON_MESURE
    if int(rc) != 0:
        print("[457] VERDICT: FAIL -- au moins un test offline est ROUGE (pytest rc=%d)" % int(rc))
        return 1
    print("[457] VERDICT: PASS -- tous les tests offline du shard sont verts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
