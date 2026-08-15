"""#486-r1 -- LE CACHE DE VERDICT PAR FICHIER des cliquets a verdict LOCAL.

CE QUE CE MODULE EST, ET CE QU'IL N'EST PAS
-------------------------------------------
Il memoise LA CONTRIBUTION D'UN FICHIER a un cliquet, sous une cle qui contient le HASH DE SON
CONTENU. Il ne change AUCUN critere : ce qui est JUGE reste identique, seul ce qui est RECALCULE
diminue. Un cache absent, vide, corrompu ou en echec d'ecriture ne peut donc rendre qu'un verdict
IDENTIQUE, plus lentement -- jamais un verdict different.

LA REGLE QUI GOUVERNE L'ADMISSION -- ETABLIR LA LOCALITE AVANT DE CACHER
-----------------------------------------------------------------------
Un cache incremental sur un cliquet dont le verdict est GLOBAL fabrique des FAUX VERTS.

    LOCAL   le verdict d'un fichier ne depend QUE de son contenu, plus des entrees externes
            NOMMEES dans le contexte (source du cliquet, table de symboles du build). Cachable.
    GLOBAL  le verdict depend de la RELATION entre fichiers -- unicite d'un numero, bijection,
            comptage croise, cycle d'imports. NON cachable par fichier, et le dire est un
            RESULTAT.

Exemple vecu du cote GLOBAL : `probe_468` detecte qu'un numero est attribue DEUX FOIS. Un cache
par fichier ne verrait jamais une collision entre un fichier TOUCHE et un fichier NON TOUCHE --
c'est litteralement la collision `#477-r43` du 2026-08-05, verte sur chacune des deux PR prise
seule. Ce module ne doit JAMAIS etre cable a un cliquet de cette forme.

POURQUOI LE CACHE EST VERSIONNE, ET PAS DANS `logs/`
----------------------------------------------------
Tout agent de ce depot travaille dans un worktree FRAIS parti d'`origin/master`. Un cache sous
`logs/` (gitignore) y naitrait VIDE et mourrait avec le worktree : il ne rechaufferait que la
boucle locale de l'orchestrateur, jamais la validation d'une PR -- c'est-a-dire jamais le cas pour
lequel il existe. VERSIONNE, il part avec le depot et un worktree frais demarre CHAUD.

Il n'est pas non plus sous `data/`, reserve aux ENTREES du jeu (`CLAUDE.md` invariant 3, garde par
`probe_273 --only-scan` etape 0c). Il vit sous `scripts/cliquets-cache/`, dans la famille des
artefacts GENERES ET VERSIONNES du depot (`docs/rl/kit-coverage.md`) : un derive de l'arbre source,
pas une trace de run -- donc **jamais fusionne a la main, toujours REGENERE** en cas de conflit.

LES QUATRE DANGERS DU VERSIONNEMENT, ET CE QUI LES FERME
--------------------------------------------------------
1. UNE ATTESTATION QUI MENT. La cle est le sha256 du CONTENU (texte normalise, cf. `sha_texte`) :
   une entree perimee ne peut que MANQUER, donc faire recalculer. C'est structurel, pas
   disciplinaire.
   ⚠ CE QUI RESTE OUVERT, ET AUCUN CACHE NE LE FERME : une entree FALSIFIEE DE FACON COHERENTE --
   un verdict faux ecrit en face du hash JUSTE du contenu. Mesure : elle rend le cliquet VERT.
   La parade n'est pas dans la cle, elle est dans la RE-VERIFICATION : `verifier()` recalcule tout
   en ignorant le cache et confronte entree par entree. C'est ce que joue le test offline
   `tests/test_486_r1_cache_verdict_offline.py`, et c'est le seul controle qui puisse le voir.
2. LES CONFLITS DE MERGE. Format TSV, UNE LIGNE PAR (fichier, appel), triee par (fichier, appel).
   Deux agents qui touchent des fichiers differents ecrivent a des endroits differents du fichier ;
   quand un conflit survient quand meme, il se resout en REGENERANT (rejouer le cliquet), jamais
   en fusionnant a la main.
3. LE CHURN. Une ligne par fichier balaye et par appel, et SEULEMENT pour les fichiers dont le
   calcul est cher : le pre-filtre bon marche du cliquet (`"slot" not in texte`, `any(cls in
   texte)`) reste JOUE a chaque run et n'entre pas au cache. Un commit qui touche N fichiers du
   perimetre deplace donc au plus N lignes par appel.
4. LE CHANGEMENT DE BUILD. Le contexte (en-tete du fichier) porte le sha du SOURCE du cliquet ET
   celui des entrees externes qui gouvernent le calcul cache -- table de slots comprise. Un
   contexte different fait MANQUER toutes les entrees : cout plein, une fois, ce qui est le
   comportement voulu. Invalider trop est toujours sur ; invalider trop peu serait faux.

TRI-ETAT : ce module n'en rend aucun. Il ne mesure rien et ne juge rien -- toute panne de sa part
(fichier illisible, disque plein, en-tete inconnue) se degrade en « cache vide », donc en recalcul.
Le tri-etat des cliquets qui l'utilisent est inchange.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

#: `scripts/python/verdict_cache.py` -> `parents[2]` = racine du depot.
RACINE = Path(__file__).resolve().parents[2]
DOSSIER = RACINE / "scripts" / "cliquets-cache"

#: Version du FORMAT du fichier. Un fichier ecrit sous une autre version est ignore (cache vide),
#: jamais lu de travers.
FORMAT = 1

#: Sentinelle d'absence. `None` serait une valeur cachable legitime pour certains appelants.
MANQUE = object()

#: Echappatoire de diagnostic. Pose a `1`, aucun cliquet ne LIT ni n'ECRIT son cache -- c'est le
#: run A FROID du controle de fidelite, sans avoir a supprimer un fichier versionne.
ENV_SANS_CACHE = "TACTICUS_SANS_CACHE_CLIQUET"


def sha_texte(texte: str) -> str:
    """Le sha256 du CONTENU LOGIQUE d'un fichier -- celui que le cliquet consomme reellement.

    ⚠ SUR LE TEXTE, PAS SUR LES OCTETS. `core.autocrlf` vaut `true` dans ce depot : les memes
    octets versionnes se materialisent en CRLF sous Windows et en LF ailleurs. Un sha sur les
    octets bruts rendrait le cache VERSIONNE invalide d'une plateforme a l'autre -- toutes les
    entrees manqueraient, silencieusement, et le cache se lirait comme « toujours froid ».
    Le texte, lui, est ce que `Path.read_text()` rend aux cliquets, fins de ligne deja
    normalisees : la cle porte donc exactement sur ce qui a ete juge.
    """
    return hashlib.sha256(texte.encode("utf-8", "surrogatepass")).hexdigest()


def sha_fichiers(*chemins: Path) -> str:
    """Empreinte d'un jeu de fichiers SUR LES OCTETS. ⚠ NE PAS L'EMPLOYER POUR UN CONTEXTE.

    ⚠ ELLE N'EST PLUS QU'UN TEMOIN (#486-r17). C'est la variante NON PORTABLE : elle hache les
    octets, donc un `git rebase` sous `core.autocrlf=true` change son resultat sans qu'aucune
    source ait bouge (vice VECU le 2026-08-07 -- 119 s au lieu de 20 s), et sur une plateforme a
    LF un cache VERSIONNE clé par elle serait froid en permanence. `sha_fichiers_texte` est ce
    qu'un contexte doit appeler ; les 13 sites du depot le font, et un cliquet le garde.

    Elle SURVIT parce que le test qui etablit la difference entre les deux variantes a besoin
    des deux -- sans elle il comparerait deux fonctions identiques et serait VACANT sans le dire.
    C'est sa seule raison d'exister : la supprimer desarmerait ce controle.

    Un fichier absent entre dans l'empreinte comme tel : son absence est une donnee, pas un
    silence.
    """
    h = hashlib.sha256()
    for p in chemins:
        h.update(str(p.name).encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(hashlib.sha256(Path(p).read_bytes()).hexdigest().encode("ascii"))
        except OSError:
            h.update(b"ABSENT")
        h.update(b"\0")
    return h.hexdigest()


def sha_fichiers_texte(*chemins: Path) -> str:
    """`sha_fichiers`, mais sur le TEXTE -- la variante PORTABLE, pour un contexte de sources.

    ⚠ MESURE (#486-r11), et c'est un vice VECU, pas redoute : `sha_fichiers` hache les OCTETS,
    donc un simple `git rebase` suffit a changer le contexte d'un cliquet dont les sources
    passent de LF a CRLF (`core.autocrlf=true`). Constate le 2026-08-07 : le cache de
    `probe_270r4r2_import_en_premier` est reparti a ZERO apres un rebase qui n'avait touche
    AUCUNE de ses trois sources -- 119 s au lieu de 20 s. Sur une autre plateforme, un cache
    VERSIONNE serait ainsi froid en permanence, c'est-a-dire inutile la ou il existe.

    C'est exactement le piege que `sha_texte` documente pour la cle de LIGNE ; le contexte y
    echappait. Un fichier absent entre dans l'empreinte comme tel : son absence est une donnee.

    ⚠ CETTE LIGNE DISAIT L'INVERSE, ET ELLE ETAIT PERIMEE DE HUIT JOURS (#486-r17, re-mesure du
    2026-08-15). Elle annoncait « les trois cliquets de #486-r1 utilisent ENCORE `sha_fichiers` » ;
    la bascule a ete faite le 2026-08-07 par `d4b78353`, et le compte re-derive du code rend
    aujourd'hui **13 sites `sha_fichiers_texte` et 0 site `sha_fichiers`**. `sha_fichiers` n'a
    donc plus AUCUN appelant hors du test qui s'en sert comme TEMOIN
    (`test_486_r1_cache_verdict_offline::test_le_CONTEXTE_portable_ignore_les_fins_de_ligne...`,
    qui a besoin des deux moities pour ne pas comparer deux fonctions identiques).
    Le zero est desormais tenu par un CLIQUET, pas par cette phrase : cf.
    `test_le_contexte_d_un_cache_ne_passe_JAMAIS_par_la_variante_OCTETS`.
    """
    h = hashlib.sha256()
    for p in chemins:
        h.update(str(p.name).encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(sha_texte(Path(p).read_text(encoding="utf-8")).encode("ascii"))
        except (OSError, UnicodeDecodeError):
            h.update(b"ABSENT")
        h.update(b"\0")
    return h.hexdigest()


def sha_gros_fichiers(*chemins: Path) -> str | None:
    """Empreinte de fichiers VOLUMINEUX, lus par BLOCS. `None` si l'un manque -- jamais un sha.

    C'est la cle des entrees dont la source n'est PAS dans l'arbre : le `global-metadata.dat` du
    build installe (21,6 Mo) et la table `frida/methods.tsv` (22,9 Mo). Mesure : **0,05 s** pour
    hacher le metadata, contre ~14 s pour la derivation qu'il gouverne.

    ⚠ `None` EST LE TRI-ETAT. Un fichier absent veut dire « je ne peux pas mesurer », pas « le
    contenu est vide » : l'appelant doit alors REFUSER de servir une entree, sans quoi un depot
    sans le jeu installe se verrait attester une derivation qu'il n'a pas pu faire.
    """
    h = hashlib.sha256()
    for p in chemins:
        try:
            with open(p, "rb") as fh:
                for bloc in iter(lambda f=fh: f.read(1 << 20), b""):
                    h.update(bloc)
        except OSError:
            return None
        h.update(b"\0")
    return h.hexdigest()


class CacheCliquet:
    """Le cache d'UN cliquet. Cle de ligne : (fichier relatif, appel). Validation : sha du contenu.

    `contexte` est l'empreinte de tout ce qui gouverne le calcul HORS du fichier balaye -- le
    source du cliquet lui-meme en premier lieu. Un contexte different vide le cache.
    """

    def __init__(self, nom: str, contexte: str,
                 encoder: Callable[[Any, str], Any] | None = None,
                 decoder: Callable[[Any, str], Any] | None = None,
                 dossier: Path | None = None, actif: bool | None = None,
                 relire: bool = True, notes: tuple[str, ...] = ()):
        self.nom = nom
        self.contexte = contexte
        #: Lignes de commentaire PROPRES a ce cliquet, ecrites dans l'en-tete. L'en-tete
        #: generique dit « sha256 du CONTENU » ; un cliquet qui cle autrement (par SOUS-GRAPHE,
        #: #486-r11) doit pouvoir le DIRE dans son propre fichier -- un artefact versionne qui
        #: se decrit de travers fait ecrire des outils qui recalculent la mauvaise chose.
        self.notes = tuple(notes)
        #: ⚠ L'ENCODEUR RECOIT L'APPEL, et ce n'est pas un ornement : un meme cliquet cache des
        #: valeurs de FORMES DIFFERENTES selon l'appel (`probe_477r25` y met des citations ET un
        #: simple entier). Un encodeur qui ne connait que la valeur plantait sur la seconde forme
        #: -- faute reelle, attrapee par le controle de fidelite (le run SANS cache passait, celui
        #: AVEC cache levait `TypeError`), pas par un test.
        self._encoder = encoder or (lambda v, _appel: v)
        self._decoder = decoder or (lambda v, _appel: v)
        self.chemin = (dossier or DOSSIER) / ("%s.tsv" % nom)
        if actif is None:
            actif = os.environ.get(ENV_SANS_CACHE, "") not in ("1", "true", "TRUE")
        self.actif = actif
        #: MODE ESPION (`relire=False`) : le fichier est CHARGE mais jamais servi -- tout est
        #: recalcule, et `verifier` confronte le recalcul aux entrees du disque. C'est le seul
        #: chemin qui voie une entree FALSIFIEE de facon coherente.
        self.relire = relire
        #: {(rel, appel): (sha, valeur_json)} -- ce qui a ete LU du disque.
        self._sur_disque: dict[tuple[str, str], tuple[str, Any]] = {}
        #: {(rel, appel): (sha, valeur_json)} -- ce que ce run a VU (hit ou recalcul). C'est lui
        #: qui sera ecrit : une entree qui n'est plus visitee DISPARAIT (pas de derive).
        self._vues: dict[tuple[str, str], tuple[str, Any]] = {}
        self.hits = 0
        self.recalculs = 0
        #: ⚠ TRI-ETAT DE L'ECRITURE, et il commande le cran de fraicheur (#486-r22).
        #: `None` = `enregistrer()` n'a PAS ete appele -- rien n'a ete tente, donc il n'y a rien
        #: a conclure du fichier qui est sur le disque. `True` = le fichier a ete reecrit par ce
        #: run. `False` = `enregistrer()` a ete appele et n'a RIEN ecrit (cache desactive, aucune
        #: entree vue, ou panne d'ecriture), auquel cas `motif_non_ecrit` DIT laquelle des trois.
        #: Sans ce champ, `cache_a_commiter` comparait le fichier de la PASSE PRECEDENTE a
        #: l'index et concluait « a jour » -- un vert rendu sans avoir rien mesure.
        self.ecrit: bool | None = None
        self.motif_non_ecrit: str | None = None
        if self.actif:
            self._charger()

    # ------------------------------------------------------------------ disque

    def _charger(self) -> None:
        try:
            lignes = self.chemin.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            #: Un fichier absent OU illisible OU non-UTF-8 se degrade en cache VIDE, donc en
            #: recalcul. Une panne du cache ne rend jamais un verdict.
            return
        entete_ok = False
        for ln in lignes:
            if ln.startswith("#"):
                if ln.startswith("# format="):
                    champs = dict(x.split("=", 1) for x in ln[2:].split("\t") if "=" in x)
                    entete_ok = (champs.get("format") == str(FORMAT)
                                 and champs.get("contexte") == self.contexte)
                continue
            if not entete_ok:
                #: En-tete absente, d'un autre FORMAT, ou d'un autre CONTEXTE : on ne lit rien.
                #: Un cache mal apparie ne se devine pas, il se recalcule.
                self._sur_disque.clear()
                return
            parts = ln.split("\t")
            if len(parts) != 4:
                continue
            rel, appel, sha, brut = parts
            try:
                self._sur_disque[(rel, appel)] = (sha, json.loads(brut))
            except ValueError:
                continue

    def enregistrer(self) -> bool:
        """Reecrit le fichier avec EXACTEMENT les entrees vues par ce run. `False` si rien ecrit.

        La reecriture integrale est ce qui fait le menage : un fichier supprime du perimetre, un
        appel retire, une entree d'un ancien contexte -- tout cela disparait sans commande dediee.
        Une panne d'ecriture n'est pas un verdict : elle est avalee, le cliquet a deja rendu le
        sien. Elle est en revanche NOMMEE dans `motif_non_ecrit`, ce qui interdit au cran de
        fraicheur de lire le fichier de la passe precedente comme s'il venait d'etre produit.
        """
        if not self.actif:
            self.ecrit, self.motif_non_ecrit = False, "cache DESACTIVE (%s)" % ENV_SANS_CACHE
            return False
        if not self._vues:
            self.ecrit = False
            self.motif_non_ecrit = ("AUCUNE entree visitee par ce run -- le fichier sur le disque "
                                    "est celui d'une passe PRECEDENTE, il ne dit rien de ce run")
            return False
        lignes = ["# format=%d\tcontexte=%s\tcliquet=%s" % (FORMAT, self.contexte, self.nom),
                  "# CACHE DE VERDICT PAR FICHIER (#486-r1) -- artefact GENERE ET VERSIONNE.",
                  "# Cle de validation = sha256 du CONTENU : une entree perimee MANQUE, elle ne",
                  "# ment pas. En cas de conflit de merge : NE PAS FUSIONNER, REGENERER en",
                  "# rejouant le cliquet (python scripts/python/%s.py)." % self.nom]
        lignes.extend(self.notes)
        lignes.append("# rel\tappel\tsha256\tvaleur")
        for (rel, appel) in sorted(self._vues):
            sha, brut = self._vues[(rel, appel)]
            lignes.append("%s\t%s\t%s\t%s"
                          % (rel, appel, sha,
                             json.dumps(brut, ensure_ascii=True, sort_keys=True,
                                        separators=(",", ":"))))
        try:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            self.chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8", newline="\n")
        except OSError as ex:
            self.ecrit = False
            self.motif_non_ecrit = "PANNE d'ecriture : %s" % str(ex)[:90]
            return False
        self.ecrit, self.motif_non_ecrit = True, None
        return True

    # ------------------------------------------------------------------ usage

    def obtenir(self, rel: str, appel: str, sha: str) -> Any:
        """La valeur cachee pour ce contenu exact, ou `MANQUE`."""
        if not self.actif or not self.relire:
            return MANQUE
        vu = self._sur_disque.get((rel, appel))
        if vu is None or vu[0] != sha:
            return MANQUE
        self._vues[(rel, appel)] = vu
        self.hits += 1
        return self._decoder(vu[1], appel)

    def poser(self, rel: str, appel: str, sha: str, valeur: Any) -> None:
        self.recalculs += 1
        if self.actif:
            self._vues[(rel, appel)] = (sha, self._encoder(valeur, appel))

    def contribution(self, rel: str, appel: str, sha: str,
                     calcul: Callable[[], Any]) -> Any:
        """`obtenir` sinon `calcul()` puis `poser`. Le chemin unique des appelants."""
        v = self.obtenir(rel, appel, sha)
        if v is not MANQUE:
            return v
        v = calcul()
        self.poser(rel, appel, sha, v)
        return v

    def resume(self) -> str:
        return ("cache %s : %d entree(s) reutilisee(s), %d recalculee(s)"
                % ("CHAUD" if self.hits else ("FROID" if self.actif else "DESACTIVE"),
                   self.hits, self.recalculs))


#: Le rc d'un cliquet dont le cache VERSIONNE a bouge sans etre commite (#486-r22). Distinct de
#: `1` (gisement trouve) et des rc d'usage : ce n'est pas le DEPOT qui est fautif, c'est
#: l'ARTEFACT GENERE qui est en retard sur lui.
EX_CACHE_A_COMMITER = 6


def cache_a_commiter(cache: CacheCliquet, racine: Path | None = None):
    """Le cache versionne a-t-il ete REECRIT par ce run sans etre commite ? Tri-etat.

    Rend `(perime, detail)` : `perime is None` => PAS MESURE (git muet), jamais `False`.

    ------------------------------------------------------------------------------------
    POURQUOI CE CRAN, ET POURQUOI IL EST GRATUIT (#486-r22)
    ------------------------------------------------------------------------------------
    Rien ne DECLENCHAIT la regeneration d'un cache. Le regime normal recalcule une entree
    perimee, la REECRIT, et rend `rc=0` : la derive s'accumule donc sans jamais rougir, et seul
    `--verifier-cache` -- que rien ni personne ne lance -- la voit. Mesure du 2026-08-07 dans un
    worktree : `probe_313 --verifier-cache` rendait `rc=3` et **38** divergences (5 SHA PERIME,
    33 ENTREE ABSENTE) pendant que le regime normal rendait `rc=0` en 10 s.

    LES DEUX FORMES QU'IL FALLAIT EVITER, et pourquoi celle-ci n'en est aucune :

      * exiger `--verifier-cache` VERT a chaque passe deplacerait le cout sur tout le monde --
        c'est un recalcul integral en MODE ESPION, le mode le plus cher du cliquet ;
      * ne l'exiger jamais laisse la derive, c'est-a-dire l'etat mesure.

    Le cran retenu n'est ni l'un ni l'autre parce qu'il ne CALCULE RIEN DE PLUS : le run vient
    d'ecrire le fichier de toute facon (`enregistrer()` reecrit integralement). On lui demande
    juste si l'ecriture a CHANGE quelque chose. Cout : un `git status --porcelain` sur UN chemin
    (~20 ms). Il rougit donc exactement quand du code est entre sans que le cache suive, et se
    tait absolument le reste du temps -- y compris sur les passes ou l'arbre ne bouge pas.

    CE QU'IL NE FAIT PAS. Il ne voit pas une entree FALSIFIEE de facon coherente : cela reste le
    domaine de `verifier()` en mode espion (cf. son docstring). Les deux controles sont
    complementaires, pas redondants -- celui-ci garde la FRAICHEUR, l'autre la FIDELITE.

    ⚠ CE CRAN NE JUGE QUE CE QUE CE RUN A ECRIT (#486-r17). Sa premisse -- « le run vient
    d'ecrire le fichier de toute facon » -- N'EST PAS ETABLIE PAR L'APPEL : elle depend d'un
    `enregistrer()` que l'appelant peut n'avoir pas fait, avoir fait sans rien avoir visite, ou
    avoir vu echouer sur le disque. Dans ces trois cas le `git diff` ci-dessous compare le
    fichier de la passe PRECEDENTE a l'index et rend `0` -- ce qui se lisait « a jour », donc un
    VERT rendu sans avoir rien mesure. Le tri-etat de `CacheCliquet.ecrit` ferme la porte : tout
    ce qui n'est pas une reecriture EFFECTIVE sort en PAS MESURE, avec son motif.
    """
    racine = racine or RACINE
    if not cache.actif:
        return None, "cache DESACTIVE (%s) -- rien n'a ete ecrit, donc rien a conclure" % ENV_SANS_CACHE
    if cache.ecrit is None:
        return None, ("`enregistrer()` n'a pas ete appele sur %s -- le fichier du disque est "
                      "celui d'une passe precedente" % cache.chemin.name)
    if cache.ecrit is False:
        return None, ("%s n'a pas ete reecrit : %s"
                      % (cache.chemin.name, cache.motif_non_ecrit or "motif inconnu"))
    try:
        rel = cache.chemin.relative_to(racine).as_posix()
    except ValueError:
        return None, "cache hors du depot (%s)" % cache.chemin
    import subprocess
    # ⚠ LE FICHIER NON SUIVI EST LE QUATRIEME FAUX VERT, ET IL ETAIT LE PIRE (#486-r17).
    # `git diff --quiet -- <chemin>` IGNORE ce que git ne suit pas : un cache tout neuf, jamais
    # `git add`-e, rendait donc « est a jour (identique a l'index) ». Mesure du 2026-08-15, au
    # cablage du cache de `probe_485_imports_differes` -- le fichier etait `??` et le cran se
    # taisait. Consequence exacte : le cache VERSIONNE n'entre jamais dans le depot, donc tout
    # worktree frais repart FROID, c'est-a-dire precisement le regime pour lequel il existe.
    try:
        suivi = subprocess.run(["git", "-C", str(racine), "ls-files", "--error-unmatch", "--",
                                rel], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=15)
    except Exception as ex:                                       # noqa: BLE001
        return None, "git ls-files: %s" % str(ex)[:90]
    if suivi.returncode != 0:
        if not cache.chemin.is_file():
            return None, "%s n'existe pas sur le disque apres ecriture" % rel
        return True, "%s a ete ECRIT par ce run et n'est pas SUIVI par git" % rel
    # ⚠ LE CRITERE EST << DIFFERE DE L'INDEX >>, PAS << DIFFERE DE HEAD >>. Un fichier deja
    # INDEXE part dans le commit en preparation : il n'y a plus rien a signaler, et rougir
    # dessus rendrait le cran INEXTINGUIBLE tant que l'auteur n'a pas commite -- mesure faite,
    # `git status --porcelain` rendait encore `M ` apres `git add` et le cliquet restait rouge.
    # `git diff --quiet` compare exactement worktree vs index, et applique au passage la
    # normalisation `core.autocrlf` : un fichier ecrit en LF et indexe en LF n'y parait pas
    # modifie, alors qu'une comparaison d'octets le dirait.
    try:
        r = subprocess.run(["git", "-C", str(racine), "diff", "--quiet", "--", rel],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=15)
    except Exception as ex:                                       # noqa: BLE001
        return None, "git diff: %s" % str(ex)[:90]
    if r.returncode == 0:
        return False, "%s est a jour (identique a l'index)" % rel
    if r.returncode != 1:
        # rc 1 = differe ; tout autre rc est une PANNE, pas un constat.
        tete = next((l.strip() for l in (r.stderr or "").splitlines() if l.strip()), "")[:80]
        return None, "git diff: rc=%d%s" % (r.returncode, " -- " + tete if tete else "")
    return True, "%s a ete REECRIT par ce run et n'est pas indexe" % rel


def rendre_compte_du_cache(cache: CacheCliquet, rc: int, racine: Path | None = None) -> int:
    """Le rc final d'un cliquet, cache pris en compte. A appeler APRES `enregistrer()`.

    Un rc DEJA non nul est rendu tel quel : le gisement prime sur la fraicheur de l'artefact --
    on ne masque jamais un vrai rouge derriere un rouge d'intendance, ni l'inverse.
    """
    if rc != 0:
        return rc
    perime, detail = cache_a_commiter(cache, racine)
    if perime is None:
        print("[cache] fraicheur NON MESUREE : %s" % detail)
        print("[cache] rc INCHANGE -- une panne de capteur ne rend pas un verdict.")
        return rc
    if not perime:
        return rc
    print("")
    print("[cache] CACHE DE VERDICT PERIME : %s" % detail)
    print("[cache] Du code est entre depuis la derniere regeneration commitee. Le verdict du")
    print("[cache] cliquet est JUSTE (l'entree perimee a ete recalculee) -- c'est l'ARTEFACT")
    print("[cache] VERSIONNE qui est en retard, et il le resterait indefiniment sans ce cran.")
    print("[cache] REMEDE : git add %s" % detail.split(" ", 1)[0])
    print("[cache] rc=%d -- aucun verdict sur le depot." % EX_CACHE_A_COMMITER)
    return EX_CACHE_A_COMMITER


def verifier(cache: CacheCliquet) -> list[str]:
    """Confronte les entrees SUR DISQUE a ce que le run vient de RECALCULER. Rend les divergences.

    A n'appeler qu'apres un run en MODE ESPION (`relire=False`), ou tout a ete recalcule : le
    `_vues` est alors un calcul integral, jamais une relecture du disque.

    C'est le SEUL controle qui voie une entree FALSIFIEE DE FACON COHERENTE -- un verdict faux
    ecrit en face du hash JUSTE du contenu. La cle ne peut pas la voir, par construction : aucun
    cache ne le peut. Ce qui la ferme est la re-verification, pas la cle.
    """
    ecarts: list[str] = []
    for cle, (sha, brut) in sorted(cache._sur_disque.items()):
        vrai = cache._vues.get(cle)
        if vrai is None:
            ecarts.append("ENTREE ORPHELINE %s [%s] -- plus aucun calcul ne la produit"
                          % (cle[0], cle[1]))
        elif vrai[0] != sha:
            ecarts.append("SHA PERIME %s [%s]" % (cle[0], cle[1]))
        elif (json.dumps(vrai[1], sort_keys=True, ensure_ascii=True)
              != json.dumps(brut, sort_keys=True, ensure_ascii=True)):
            ecarts.append("VALEUR FALSIFIEE %s [%s] -- le cache atteste autre chose que le calcul"
                          % (cle[0], cle[1]))
    for cle in sorted(cache._vues):
        if cle not in cache._sur_disque:
            ecarts.append("ENTREE ABSENTE %s [%s] -- le cache versionne ne la porte pas"
                          % (cle[0], cle[1]))
    return ecarts
