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
    """Empreinte d'un jeu de fichiers -- pour le CONTEXTE (source du cliquet, table de symboles).

    Un fichier absent entre dans l'empreinte comme tel : son absence est une donnee du contexte,
    pas un silence.
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


class CacheCliquet:
    """Le cache d'UN cliquet. Cle de ligne : (fichier relatif, appel). Validation : sha du contenu.

    `contexte` est l'empreinte de tout ce qui gouverne le calcul HORS du fichier balaye -- le
    source du cliquet lui-meme en premier lieu. Un contexte different vide le cache.
    """

    def __init__(self, nom: str, contexte: str,
                 encoder: Callable[[Any, str], Any] | None = None,
                 decoder: Callable[[Any, str], Any] | None = None,
                 dossier: Path | None = None, actif: bool | None = None,
                 relire: bool = True):
        self.nom = nom
        self.contexte = contexte
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
        sien.
        """
        if not self.actif or not self._vues:
            return False
        lignes = ["# format=%d\tcontexte=%s\tcliquet=%s" % (FORMAT, self.contexte, self.nom),
                  "# CACHE DE VERDICT PAR FICHIER (#486-r1) -- artefact GENERE ET VERSIONNE.",
                  "# Cle de validation = sha256 du CONTENU : une entree perimee MANQUE, elle ne",
                  "# ment pas. En cas de conflit de merge : NE PAS FUSIONNER, REGENERER en",
                  "# rejouant le cliquet (python scripts/python/%s.py)." % self.nom,
                  "# rel\tappel\tsha256\tvaleur"]
        for (rel, appel) in sorted(self._vues):
            sha, brut = self._vues[(rel, appel)]
            lignes.append("%s\t%s\t%s\t%s"
                          % (rel, appel, sha,
                             json.dumps(brut, ensure_ascii=True, sort_keys=True,
                                        separators=(",", ":"))))
        try:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            self.chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8", newline="\n")
        except OSError:
            return False
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
