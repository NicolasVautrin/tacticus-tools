"""livraison -- LE critere de livraison d'une branche, partage par les outils de nettoyage.

POURQUOI CE MODULE EXISTE. Trois residus (`#479-r4`, `#467-r2`, `#479-r1`) sont le MEME fait
vu sous trois angles, et un quatrieme (`#467-r8`) est ce qui arrive quand deux outils de la
meme etape repondent l'inverse :

    LE SQUASH-MERGE EST NOTRE SEUL MODE DE MERGE, ET IL DETRUIT L'ANCESTRALITE.

Un squash recopie l'ARBRE, pas les commits : le tip d'une branche mergee n'est donc JAMAIS un
ancetre d'`origin/master`. Tout critere fonde sur `--merged` / `merge-base --is-ancestor` est
par consequent aveugle a nos propres livraisons -- et il l'est du cote MUET, donc il se lit
comme << rien a faire >>.

Mesure du 2026-08-07 (re-deriver, ne jamais citer) : sur **20** branches `worktree-agent-*`
locales, **3** sont ancetres et **16** ont une PR MERGEE que l'ancestralite ne voit pas ;
cote distant, **431** branches, **0** ancetre et **418** PR mergees. Le critere d'ancestralite
seul voit donc 15 % du gisement local et 0 % du distant.

LES TROIS ETATS, ET POURQUOI IL EN FAUT TROIS

    LIVREE        une voie POSITIVE a repondu oui (ancetre, ou PR mergee sur cette head)
    NON LIVREE    les DEUX voies ont repondu, et toutes deux disent non
    NON TRANCHEE  au moins une voie n'a pas pu conclure -- ON NE SUPPRIME RIEN, ET ON LE DIT

`NON TRANCHEE` n'est pas une commodite : c'est le tri-etat de `host_inputs` (#273) applique a
un outil qui SUPPRIME. Un `gh` muet ne rend pas << 0 PR mergee >>, il rend << je n'ai pas pu
demander >>. Aucun chemin de ce module ne fabrique un zero.

LA FENETRE SATUREE EST LE CRAN QUI FERME `#467-r2`. `gh pr list --limit N` rend au plus N
lignes ; si le rendu VAUT N, la fenetre est SATUREE et peut cacher n'importe quelle PR plus
ancienne. Une fenetre saturee ne peut donc conclure QUE positivement -- l'absence d'une branche
n'y prouve rien. C'est exactement le trou de `#467-r2` (<< au-dela de 120 PR, un worktree
squash-merge n'est pas propose >>), sauf qu'il devient un etat NOMME au lieu d'un faux negatif
silencieux. Mesure du 2026-08-07 : `--limit 120` rend 120 (SATUREE) ; `--limit 2000` rend
822 pour 822 PR reelles (NON saturee), en 4,5 s -- un outil manuel peut donc s'offrir
l'exhaustivite, un hook de 3 s non.

CE QUE CE MODULE NE DECIDE PAS. << Livree >> n'est pas << a retirer >>. Le protocole exige un
SECOND terme -- << je n'ai plus rien a demander a l'agent >> -- qui ne se derive d'aucun etat
git (`#467-r8`). Il vit dans `garde_marquee()` : une marque DEPOSEE dans le worktree, lue ici,
jamais devinee.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

#: Les branches fabriquees par le harnais d'agents.
PREFIXE_AGENT = "worktree-agent-"
BRANCHE_AGENT_GLOB = PREFIXE_AGENT + "*"

#: Limite `gh pr list` d'un outil MANUEL : assez haute pour que la fenetre ne sature pas, donc
#: pour que le verdict NEGATIF soit atteignable. Mesure du 2026-08-07 : 822 PR au total, 4,5 s.
#: Ce n'est pas une constante magique -- si le depot depasse ce chiffre, la fenetre saturera et
#: l'outil le DIRA (il ne conclura simplement plus au negatif), ce qui est le bon sens de
#: l'erreur pour un outil qui supprime.
LIMITE_MANUELLE = 2000

#: Limite d'un HOOK (budget de 3 s). La fenetre y sature, et c'est assume : sous hook on ne
#: cherche que des positifs (proposer un nettoyage), jamais a prouver qu'une branche n'est pas
#: livree. Mesure : couvre 16 des 20 branches locales, la seule non tranchee etant un agent
#: EN VOL -- c'est-a-dire precisement celle qu'il ne faut pas toucher.
LIMITE_HOOK = 120

#: Le fichier qu'un orchestrateur depose dans un worktree pour dire << je vais reprendre cet
#: agent >>. Son CONTENU est la raison, rendue telle quelle. Cf. `garde_marquee`.
MARQUE_GARDE = ".keep-agent"

ETAT_LIVREE = "LIVREE"
ETAT_NON_LIVREE = "NON LIVREE"
ETAT_NON_TRANCHEE = "NON TRANCHEE"


@dataclass(frozen=True)
class Verdict:
    """Le verdict de livraison d'UNE branche. `voie` dit ce qui a tranche, `cause` pourquoi non.

    Les deux champs sont exclusifs par construction : un verdict positif porte sa voie, un
    verdict non tranche porte sa cause. Un `NON LIVREE` porte les deux voies qui ont dit non,
    parce qu'un negatif se justifie autant qu'un positif.
    """

    branche: str
    etat: str
    voie: str | None = None
    cause: str | None = None

    @property
    def livree(self) -> bool:
        return self.etat == ETAT_LIVREE

    @property
    def tranchee(self) -> bool:
        return self.etat != ETAT_NON_TRANCHEE

    def txt(self) -> str:
        if self.etat == ETAT_LIVREE:
            return "%s (%s)" % (ETAT_LIVREE, self.voie or "?")
        if self.etat == ETAT_NON_LIVREE:
            return "%s (%s)" % (ETAT_NON_LIVREE, self.cause or "les deux voies disent non")
        return "%s -- %s" % (ETAT_NON_TRANCHEE, self.cause or "cause non enregistree")


@dataclass(frozen=True)
class FenetrePR:
    """Ce qu'un `gh pr list` a REELLEMENT rendu, et ce qu'il ne peut PAS dire.

    `mergees is None` => PAS MESUREE (gh muet, sortie illisible, ...). Ce n'est pas un
    ensemble vide : un ensemble vide affirmerait << aucune PR mergee >>, ce qu'un capteur
    muet ne peut pas affirmer. Meme distinction que `Mesure` de `loop_status`.
    """

    mergees: dict[str, int] | None = None
    ouvertes: dict[str, int] | None = None
    saturee: bool = False
    limite: int | None = None
    rendus: int | None = None
    cause: str | None = None
    source: str = "gh pr list"
    #: Les lignes BRUTES rendues par `gh`, telles quelles. Ce module n'en consomme aucune -- il
    #: ne lit que `number/headRefName/state`. Elles sont la pour les lecteurs qui ont besoin
    #: d'un champ de plus (`loop_status._titres_mergees` veut le TITRE, #526-r2) SANS relancer
    #: `gh` : ce lecteur-la court sous un budget de 3 s. Un champ absent rend simplement une
    #: liste vide chez l'appelant -- le signal se tait, il ne se trompe pas.
    brutes: tuple = ()

    @property
    def mesuree(self) -> bool:
        return self.mergees is not None

    @property
    def conclut_au_negatif(self) -> bool:
        """La SEULE condition sous laquelle l'absence d'une branche prouve quelque chose."""
        return self.mesuree and not self.saturee

    def portee(self) -> str:
        """Ce que cette fenetre couvre -- imprime a cote de tout compte qui en derive."""
        if not self.mesuree:
            return "PR : PAS MESUREES (%s)" % (self.cause or "cause non enregistree")
        base = "PR : %d mergee(s), %d ouverte(s) sur %s rendu(s) (limite %s)" % (
            len(self.mergees), len(self.ouvertes or {}), self.rendus, self.limite)
        if self.saturee:
            return (base + " -- FENETRE SATUREE : l'ABSENCE d'une branche n'y prouve RIEN "
                           "(une PR plus ancienne y serait invisible)")
        return base + " -- fenetre NON saturee : l'absence vaut donc constat"


def lire_fenetre_pr(gh, limite: int = LIMITE_MANUELLE) -> FenetrePR:
    """`gh pr list --state all` -> `FenetrePR`. Ne LEVE jamais : la panne part dans `cause`.

    `gh` est un callable `(*args) -> (rc, stdout, stderr)` -- la signature de
    `loop_status.Sources.gh`, pour que les deux outils partagent aussi la resolution de l'exe
    et la NOMINATION des pannes (#467-r6 : `rc=1` couvre token invalide / depot inconnu /
    erreur d'usage, seul le stderr les separe).

    UN SEUL appel, `--state all` : le tri ouvertes/mergees se fait ici. Deux appels coutaient
    2,71 s a eux seuls (mesure #467).
    """
    try:
        # `title` n'est consomme par AUCUN critere d'ici -- il est demande pour que `brutes`
        # porte le meme jeu de champs que la fenetre du hook (`loop_status`, qui demande
        # `number,title,headRefName,isDraft,state`). Sans lui, `_residus_livres` rendait
        # `[]` par cette voie et `probe_526r2 --etat` l'imprimait << aucun -- mesure, pas
        # suppose >> alors que le critere (le TITRE) n'avait tout simplement pas ete lu :
        # 0 par la voie manuelle contre 4 par la voie du hook, le meme jour (#526-r4).
        rc, out, err = gh("pr", "list", "--state", "all", "--limit", str(limite),
                          "--json", "number,title,headRefName,state")
    except Exception as ex:                                       # noqa: BLE001
        return FenetrePR(cause=str(ex)[:140], limite=limite)
    if rc != 0:
        return FenetrePR(cause=_cause_gh(rc, err), limite=limite)
    brut = (out or "").strip()
    if not brut:
        # `json.loads(out or "[]")` fabriquerait ici un zero : sortie vide + rc=0 deviendrait
        # << aucune PR >>, RENDU COMME UNE MESURE. C'est le zero interdit (cf. #467-r6).
        return FenetrePR(cause="gh: sortie VIDE malgre rc=0", limite=limite)
    try:
        prs = json.loads(brut)
    except ValueError:
        return FenetrePR(cause="gh: sortie ILLISIBLE malgre rc=0 (%d octets)" % len(brut),
                         limite=limite)
    if not isinstance(prs, list):
        return FenetrePR(cause="gh: sortie INATTENDUE (%s, pas une liste)" % type(prs).__name__,
                         limite=limite)
    return fenetre_des_prs(prs, limite)


def fenetre_des_prs(prs: list, limite: int) -> FenetrePR:
    """Construit la fenetre a partir de lignes DEJA obtenues (cache de `loop_status`).

    Extrait pour que le cache `gh` de `loop_status` alimente exactement le meme critere que
    l'appel direct -- sinon les deux outils divergeraient a nouveau, par un autre chemin.
    """
    mergees, ouvertes = {}, {}
    for p in prs:
        etat = (p.get("state") or "").upper()
        head = p.get("headRefName") or ""
        num = p.get("number")
        if not head:
            continue
        if etat == "MERGED":
            mergees.setdefault(head, num)
        elif etat == "OPEN":
            ouvertes.setdefault(head, num)
    return FenetrePR(mergees=mergees, ouvertes=ouvertes,
                     saturee=len(prs) >= limite, limite=limite, rendus=len(prs),
                     source="gh pr list --state all --limit %d" % limite,
                     brutes=tuple(prs))


_GH_RC_NOMME = {2: "annule", 4: "non authentifie (gh auth login)"}


def _cause_gh(rc: int, err: str) -> str:
    """Le NOM d'un echec de `gh`, jamais un code nu. Copie du critere de `loop_status`.

    Table courte DELIBEREMENT : `1` n'est PAS nommable (token invalide, depot inconnu, erreur
    d'usage le partagent), donc c'est le stderr qui nomme.
    """
    tete = next((l.strip() for l in (err or "").splitlines() if l.strip()), "")[:90]
    nom = _GH_RC_NOMME.get(rc)
    base = "gh: %s [rc=%d]" % (nom, rc) if nom else "gh: rc=%d" % rc
    return "%s -- %s" % (base, tete) if tete else base


def classer(branches, ancetres: set[str] | None, fenetre: FenetrePR,
            cause_ancetres: str | None = None) -> dict[str, Verdict]:
    """Le critere, en un seul endroit. `ancetres is None` => voie ancestralite PAS MESUREE.

    Ordre des voies : l'ANCESTRALITE d'abord, parce qu'elle est LOCALE et verifiable a la main
    (`git merge-base --is-ancestor`), donc elle ne depend d'aucun reseau ni d'aucun cache. La
    PR ne sert qu'a rattraper ce que le squash lui cache.

    LE NEGATIF EXIGE LES DEUX VOIES. Une seule voie muette suffit a faire `NON TRANCHEE` :
    c'est ce qui distingue << je sais qu'elle n'est pas livree >> de << je n'ai pas pu
    savoir >>, et c'est toute la difference entre un outil qui supprime a bon escient et un
    outil qui supprime le travail d'un agent en vol.
    """
    out: dict[str, Verdict] = {}
    for b in branches:
        if ancetres is not None and b in ancetres:
            out[b] = Verdict(b, ETAT_LIVREE, voie="ancetre d'origin/master")
            continue
        if fenetre.mesuree and b in fenetre.mergees:
            out[b] = Verdict(b, ETAT_LIVREE,
                             voie="PR #%s mergee" % fenetre.mergees[b])
            continue
        if ancetres is None:
            out[b] = Verdict(b, ETAT_NON_TRANCHEE,
                             cause="ancestralite PAS MESUREE (%s)"
                                   % (cause_ancetres or "cause non enregistree"))
            continue
        if not fenetre.mesuree:
            out[b] = Verdict(b, ETAT_NON_TRANCHEE,
                             cause="pas ancetre, et %s" % (fenetre.cause or "PR pas mesurees"))
            continue
        if fenetre.saturee:
            out[b] = Verdict(b, ETAT_NON_TRANCHEE,
                             cause="pas ancetre, et fenetre PR SATUREE (%d rendus pour une "
                                   "limite de %d) : une PR plus ancienne y serait invisible"
                                   % (fenetre.rendus or 0, fenetre.limite or 0))
            continue
        out[b] = Verdict(b, ETAT_NON_LIVREE,
                         cause="ni ancetre d'origin/master, ni PR mergee parmi les %d PR lues"
                               % (fenetre.rendus or 0))
    return out


def trancher_par_pr_ciblee(gh, branche: str) -> Verdict:
    """`gh pr list --state merged --head <branche>` -- la voie qui IGNORE la fenetre.

    C'est le rattrapage exact de `#467-r2` : la requete est CIBLEE, donc elle ne peut pas
    saturer, donc son absence de resultat vaut constat. Cout mesure : 1,4 s par branche --
    a reserver aux petits lots (les branches montees dans un worktree d'agent, typiquement
    moins de 10), jamais a un balayage de 400 branches distantes.
    """
    try:
        rc, out, err = gh("pr", "list", "--state", "merged", "--head", branche,
                          "--limit", "5", "--json", "number,state")
    except Exception as ex:                                       # noqa: BLE001
        return Verdict(branche, ETAT_NON_TRANCHEE, cause="cible: %s" % str(ex)[:120])
    if rc != 0:
        return Verdict(branche, ETAT_NON_TRANCHEE, cause="cible: " + _cause_gh(rc, err))
    brut = (out or "").strip()
    if not brut:
        return Verdict(branche, ETAT_NON_TRANCHEE, cause="cible: sortie VIDE malgre rc=0")
    try:
        prs = json.loads(brut)
    except ValueError:
        return Verdict(branche, ETAT_NON_TRANCHEE, cause="cible: sortie ILLISIBLE")
    if not isinstance(prs, list):
        return Verdict(branche, ETAT_NON_TRANCHEE, cause="cible: sortie INATTENDUE")
    if prs:
        return Verdict(branche, ETAT_LIVREE, voie="PR #%s mergee (requete ciblee)"
                                                  % prs[0].get("number"))
    return Verdict(branche, ETAT_NON_LIVREE,
                   cause="aucune PR mergee sur cette head (requete ciblee, sans fenetre)")


def branches_protegees_par_worktree(sortie_porcelain: str) -> set[str]:
    """Les branches qu'un worktree PROTEGE -- a exclure de toute suppression, locale ou distante.

    DEUX voies, et la seconde n'est pas un supplement de confort. Elle vit deja dans
    `probe_479.branches_a_worktree` ; elle est hissee ici parce que `nettoyer_livraison` et
    `loop_status` ne l'avaient PAS, et que c'est le meme fait qui les mordait tous les deux.

    1. la ligne `branch refs/heads/<x>` de `git worktree list --porcelain` ;
    2. la CONVENTION DE NOM du repertoire : `.claude/worktrees/agent-<id>` protege
       `worktree-agent-<id>`, que le worktree expose cette branche ou non.

    POURQUOI LA SECONDE -- deux mesures, un an d'ecart de forme, la meme cause :

    - 2026-08-05 : `worktree-agent-a403b7d0c9170ac76` est apparu ORPHELIN alors que son
      worktree existait, etait `locked` et que son agent commitait. Un worktree en HEAD
      DETACHE n'emet aucune ligne `branch` -- et c'est exactement son etat PENDANT `git
      rebase`, que la doctrine impose a chaque agent avant d'ouvrir sa PR.
    - 2026-08-07 : `worktree-agent-a209ad485d64a730e` a ete propose au gisement B (tip
      `22fdb030`, un ancien `master`, 0 commit d'avance, donc ANCETRE, donc « livree »)
      alors que son agent TRAVAILLAIT -- il avait simplement RENOMME sa branche en
      `agent/486r24-bypass-declare`. L'outil voyait les deux faces du meme agent
      (`agent/486r24-...` figurait dans sa liste INTACT) SANS LES RELIER.

    Le discriminant sur n'est donc PAS le nom de la branche, c'est le WORKTREE -- et le nom
    du REPERTOIRE est ce qui survit aussi bien au detachement de HEAD qu'au renommage de la
    branche. La voie 2 sur-protege legerement (elle garde `worktree-agent-<id>` meme si
    l'agent est parti ailleurs pour de bon) : c'est le bon sens de l'erreur, on ne supprime
    jamais par defaut d'information.
    """
    noms: set[str] = set()
    for ligne in (sortie_porcelain or "").splitlines():
        if ligne.startswith("branch refs/heads/"):
            noms.add(ligne[len("branch refs/heads/"):].strip())
        elif ligne.startswith("worktree "):
            base = ligne[len("worktree "):].strip().replace("\\", "/").rstrip("/")
            base = base.rsplit("/", 1)[-1]
            if base.startswith("agent-"):
                noms.add("worktree-" + base)
    return noms


#: Le repertoire ou le harnais d'agents monte les worktrees, relatif a la racine du depot.
RACINE_WORKTREES = ".claude/worktrees"

ETAT_WT_ENREGISTRE = "ENREGISTRE"
ETAT_WT_ORPHELIN = "ORPHELIN"
ETAT_WT_DANGLING = "DANGLING"


@dataclass(frozen=True)
class EtatWorktrees:
    """Ce que `git worktree list` dit -- et ce que le DISQUE dit -- des worktrees d'agents.

    `mesure is False` => le porcelain n'a pas pu etre lu. Les trois listes sont alors VIDES et
    ne valent pas constat : meme tri-etat que `FenetrePR`. Aucun chemin ne fabrique un zero.
    """

    enregistres: list[str]
    orphelins: list[str]
    dangling: list[str]
    mesure: bool = True
    cause: str | None = None
    declares: frozenset[str] = frozenset()

    def etat_de(self, chemin: str) -> str | None:
        """L'etat d'UN repertoire quelconque, ou None si la mesure n'a pas eu lieu.

        Le discriminant est la liste des chemins DECLARES par git, jamais l'enumeration d'un
        repertoire : `fleet_board` juge des chemins lus dans des `meta.json`, qui designent
        l'arbre PRINCIPAL alors que la mesure peut tourner depuis un worktree. Comparer a ce
        qu'on a su ENUMERER rendait `None` pour tout le monde -- donc le repli, donc rien.

        Un chemin ni declare ni present sur disque rend None : il a disparu proprement, il n'y
        a aucune decision a prendre dessus (ce n'est pas un orphelin).
        """
        if not self.mesure:
            return None
        c = _norme(chemin)
        if c in self.declares:
            return ETAT_WT_ENREGISTRE
        # ⚠ HORS DU GISEMENT, ON NE CONCLUT RIEN. Un chemin qui n'est pas un
        # `.claude/worktrees/agent-*` n'est pas un worktree d'agent de CE depot : ce peut etre
        # un montage de test, un checkout tiers, un chemin d'une autre machine. Le declarer
        # ORPHELIN parce que git ne le connait pas serait une conclusion tiree d'un perimetre
        # qu'on n'a jamais mesure -- faute commise ici : `probe_467` est devenu ROUGE (ses
        # scenes synthetiques pointent sous `%TEMP%`) et le mode complet perdait l'etat
        # `attente` qu'il garde precisement pour ne pas oublier un agent reprenable.
        if "/.claude/worktrees/agent-" not in c:
            return None
        try:
            existe = Path(chemin).is_dir()
        except OSError:
            return None
        return ETAT_WT_ORPHELIN if existe else None

    def portee(self) -> str:
        if not self.mesure:
            return "WORKTREES : PAS MESURES (%s)" % (self.cause or "cause non enregistree")
        return ("WORKTREES : %d enregistre(s), %d ORPHELIN(s) (repertoire sans entree admin), "
                "%d DANGLING (entree admin sans repertoire)"
                % (len(self.enregistres), len(self.orphelins), len(self.dangling)))


def _norme(p: str) -> str:
    return str(p).replace("\\", "/").rstrip("/").lower()


def chemins_enregistres(sortie_porcelain: str) -> list[str]:
    """Les chemins que `git worktree list --porcelain` declare, dans l'ordre rendu."""
    return [l[len("worktree "):].strip()
            for l in (sortie_porcelain or "").splitlines() if l.startswith("worktree ")]


def racine_principale(sortie_porcelain: str) -> str | None:
    """L'arbre PRINCIPAL, derive du porcelain : git le rend toujours en PREMIER.

    Necessaire parce que la mesure tourne couramment DEPUIS un worktree (`fleet_board` importe
    par un agent), alors que le gisement -- `.claude/worktrees/agent-*` -- ne vit que dans
    l'arbre principal. Le deriver evite d'exiger de l'appelant une racine qu'il n'a pas.
    """
    chemins = chemins_enregistres(sortie_porcelain)
    return chemins[0] if chemins else None


def etat_des_worktrees(racine, sortie_porcelain: str | None,
                       cause: str | None = None) -> EtatWorktrees:
    """Croise l'entree ADMIN et le DISQUE -- les deux peuvent survivre l'un sans l'autre (#480-r11).

    LES DEUX PORTES, mesurees le 2026-08-07, et elles s'ouvrent en sens INVERSE :

      ORPHELIN   le repertoire existe, l'entree admin NON. C'est ce que laisse un
                 `git worktree remove` qui echoue en `Filename too long` : git retire l'entree
                 AVANT d'echouer sur les fichiers, donc `git worktree list` dit << supprime >>
                 pendant que des dizaines de Mo restent sur disque, `.git` compris. Un tel
                 repertoire n'est PLUS reprenable : son `.git/worktrees/<id>` n'existe plus.
      DANGLING   l'entree admin existe, le repertoire NON. C'est ce que laisse un test qui monte
                 un worktree et se fait TUER (Ctrl+C, timeout, worker xdist) : son `finally`
                 couvre une exception, pas un kill. `git worktree prune` la ramasse -- et n'est
                 joue nulle part.

    POURQUOI CE CRITERE PLUTOT QUE L'EXISTENCE DU REPERTOIRE. `fleet_board` derivait son etat
    << EN ATTENTE -- reprenable par SendMessage >> de `Path(worktreePath).exists()` seul, donc il
    annoncait comme reprenables des agents dont l'entree admin avait disparu. La presence du
    repertoire prouve qu'il RESTE quelque chose, jamais que git le connait encore.

    Le perimetre est `<racine>/.claude/worktrees/agent-*` : les worktrees de TEST (montes sous
    `%TEMP%` par `test_431_build_pin_offline` et `probe_273`) sont enregistres ailleurs et
    n'entrent donc jamais dans le compte de la flotte -- c'est deja vrai, on ne le change pas.
    """
    if sortie_porcelain is None:
        return EtatWorktrees([], [], [], mesure=False,
                             cause=cause or "git worktree list: cause non enregistree")
    declares = chemins_enregistres(sortie_porcelain)
    par_norme = {_norme(c) for c in declares}

    # La racine est DERIVEE quand l'appelant n'en donne pas, ou en donne une qui n'heberge pas
    # le gisement (cas normal : la mesure tourne depuis un worktree d'agent).
    base = Path(racine) / ".claude" / "worktrees" if racine else None
    if base is None or not base.is_dir():
        principale = racine_principale(sortie_porcelain)
        base = Path(principale) / ".claude" / "worktrees" if principale else base

    sur_disque: list[str] = []
    try:
        if base is not None and base.is_dir():
            sur_disque = [str(d) for d in sorted(base.iterdir())
                          if d.is_dir() and d.name.startswith("agent-")]
    except OSError as ex:
        return EtatWorktrees([], [], [], mesure=False,
                             cause="lecture de %s: %s" % (base, ex))

    enregistres = [d for d in sur_disque if _norme(d) in par_norme]
    orphelins = [d for d in sur_disque if _norme(d) not in par_norme]
    # DANGLING : borne au perimetre de la FLOTTE. Une entree pointant sous `%TEMP%` appartient a
    # un test, pas a un agent -- la ramasser ici melangerait deux gisements.
    dangling = [c for c in declares
                if "/.claude/worktrees/agent-" in _norme(c) and not Path(c).is_dir()]
    return EtatWorktrees(enregistres, orphelins, dangling, declares=frozenset(par_norme))


def garde_marquee(chemin_worktree: str) -> str | None:
    """La RAISON pour laquelle ce worktree doit RESTER, ou None. Lue, jamais devinee (#467-r8).

    << Livree >> n'est pas << a retirer >>. Le protocole (`tacticus-orchestration`, section
    boucle de MERGE) garde le worktree d'un agent qu'on compte reprendre -- et ce second terme
    n'est derivable d'AUCUN etat git : il vit dans la tete de l'orchestrateur. Mesure du
    2026-08-07 : le worktree de `#527-r1` a ete signale 3 tours de suite et garde 3 fois pour
    la meme raison, faute de pouvoir inscrire la decision quelque part.

    D'ou une marque DEPOSEE : un fichier `.keep-agent` a la racine du worktree, dont le
    contenu est la raison. Ni compteur d'avertissements ni `--quiet` -- ceux-la supprimeraient
    le signal au lieu de le rendre juste.
    """
    try:
        p = Path(chemin_worktree) / MARQUE_GARDE
        if not p.is_file():
            return None
        raison = p.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return raison.splitlines()[0][:120] if raison else "marque posee, sans raison ecrite"
