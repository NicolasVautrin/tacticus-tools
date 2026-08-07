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
        rc, out, err = gh("pr", "list", "--state", "all", "--limit", str(limite),
                          "--json", "number,headRefName,state")
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
                     source="gh pr list --state all --limit %d" % limite)


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
