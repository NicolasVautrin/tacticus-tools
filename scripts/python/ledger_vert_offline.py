"""#486-r23 -- LE LEDGER VERSIONNE DU VERT OFFLINE. Foyer UNIQUE de sa validite.

CE QU'IL EST, ET POURQUOI IL N'EXISTAIT PAS
--------------------------------------------
Deux artefacts se partageaient l'information, et aucun des deux ne suffit :

| artefact                                  | sait                                  | ne sait pas          |
| ----------------------------------------- | ------------------------------------- | -------------------- |
| ledger LIVE `ratchets-462-live-attestations.json` | qu'il est passe, quand, a quel cout, avec quel bilan | de quoi le test DEPEND |
| empreinte OFFLINE `ratchets-457-footprints.json`  | de quoi le test depend (`dirs`, `temoins`)          | s'il est PASSE         |

Ce fichier porte la moitie manquante cote OFFLINE : la SIGNATURE du ledger live (`_at`, `_blob`,
`_commit`, `verdict`, `sec`, et le BILAN VENTILE de pytest), pour chaque fichier de test offline.
La cle de validite, elle, se COMPOSE avec l'empreinte -- cf. `raison_de_rejeu`.

IL EST VERSIONNE, ET C'EST TOUT L'ENJEU. `logs/` ne traverse pas les worktrees : un agent qui
arrive dans un worktree frais n'a AUCUN historique, donc rejoue tout. Mesure du 2026-08-07 : c'est
exactement le bug de `--measure-missing` (`logs/` gitignore => aucun poids => le critere
<< sans poids >> valait pour TOUT LE MONDE => 235/235 fichiers, ~16 min au lieu de 15 s).

⛔ LA SEMANTIQUE DU LEDGER LIVE NE SE RECOPIE PAS -- ELLE S'INVERSE
-------------------------------------------------------------------
`probe_462.verdict_effectif` rend **VERT TEL QUEL, sans aucune condition sur le commit** (son
<< trou B >>, ouvert et assume). C'est defendable LA-BAS parce que ce ledger sert a BLOQUER sur
les rouges : la peremption y touche le recit d'un non-vert.

ICI, un vert sert a **SAUTER un test**. Un vert perime n'y est donc pas conservateur : c'est
exactement le FAUX VERT que `#465` nomme comme le mode de defaillance a interdire. La regle est
donc l'inverse : **AUCUN vert n'est valable sans que sa cle de validite tienne**. Recopier
l'asymetrie de `probe_462` aurait produit un ledger permissif -- silencieusement.

LA CLE DE VALIDITE, ET POURQUOI CELLE-LA
-----------------------------------------
`#465` a mesure le defaut a ne pas refaire : la cle du ledger live est le BLOB DU FICHIER DE TEST
SEUL, donc elle repond a << ce CONTENU a-t-il ete atteste ? >> alors qu'un verdict depend du depot
ENTIER. Les trois rouges du ledger etaient PERIMES (2026-08-04).

La cle retenue couvre le test ET sa fermeture de dependances MESUREE, en composant les deux
artefacts (detail dans `raison_de_rejeu`) :

  1. le BLOB COURANT du fichier de test, pris dans le WORKTREE (`git hash-object`), pas dans
     l'index -- c'est le seul cran qui voit une edition NON COMMITEE, invisible de tout `git diff
     <ref> HEAD` ;
  2. le commit `_depuis` doit etre CONNU de git -- sinon la cle ne porte sur aucun arbre lisible ;
  3. le fichier ne doit pas etre IMPACTE par le diff `_depuis..HEAD`, au sens exact de
     `probe_457.impacted_files` -- c'est-a-dire empreinte (`dirs`/`temoins`), graphe d'imports,
     `DECLENCHEUR` declare et lectures globales, tous ensemble.

Le point 3 est la COMPOSITION : l'empreinte repond a << de quoi depend-il >>, le ledger a
<< quand etait-il vert >>. Ni l'un ni l'autre ne conclut seul.

DEUX ANCRES, ET C'EST LA MESURE QUI L'A IMPOSE
-----------------------------------------------
Une seule ancre ne peut pas etre a la fois PRECISE et SURVIVANTE, et prendre l'une ou l'autre
coute exactement ce que l'autre rapporte :

  * `_depuis` = **HEAD reel** -- PRECIS. C'est lui qui fait gagner : entre deux passes d'une meme
    tranche, le diff `HEAD_precedent..HEAD` ne porte que ce que l'agent vient de changer. Mais il
    MEURT au squash-merge, qui remplace la branche de l'agent par un commit neuf avant de la
    supprimer -- defaut exact que `#486-r15` a du reparer sur le `_commit` global de l'empreinte
    (`--since` rendait alors 220/220 sur chacune des 8 dernieres bases de PR, 3 jours durant).
  * `_base` = **`git merge-base HEAD origin/master`** -- SURVIVANTE, mais GROSSIERE.

MESURE DU 2026-08-07 qui tranche : avec `_base` SEULE, `--depuis-ledger` rend **exactement la meme
selection que `--since <base>`** -- 33 fichiers, 494 s dans les deux cas. C'est structurel, pas un
hasard : si toutes les attestations portent la base de la PR, la question posee au ledger EST
celle que `--since` pose deja. Le ledger n'aurait alors apporte que de la SURETE (il attrape les
rouges et les jamais-attestes), zero economie.

Donc les DEUX sont inscrites, et l'ancre effective est **la plus precise qui soit CONNUE de git**
(`ancre_effective`) : `_depuis` tant que la branche vit, `_base` apres le squash. La degradation
est SURE dans les deux sens -- une ancre plus ancienne ne fait que SUR-selectionner.

Et `_base` reste sure pour la meme raison qu'avant : si les changements de l'agent impactent le
fichier, il est de toute facon dans `impacted_files(base)` ; sinon, le vert observe sur
`base + changements` vaut aussi pour `base`.

`_commit` (HEAD au moment de l'ecriture) reste inscrit en CONTEXTE INFORMATIF -- jamais comme
critere ; c'est `_depuis` qui porte la meme valeur avec le statut de critere.

ASCII only (cp1252).
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

#: Chemin VERSIONNE, relatif a la racine du checkout. A cote de ses deux freres
#: (`ratchets-457-footprints.json`, `ratchets-462-live-attestations.json`), et pour la meme
#: raison : sous `logs/` il mourrait avec le worktree, ce qui est precisement le defaut repare.
CHEMIN = "scripts/ratchets-457-vert-offline.json"

#: VERSION DU FORMAT. Un format inconnu ne se devine pas : `lire` rend un ledger VIDE en le
#: DISANT, donc tout rejoue. C'est le seul traitement sur -- lire un format inconnu avec les
#: regles d'un autre produirait un faux vert, pas une sur-selection.
FORMAT = 1

#: Verdicts possibles. Repris de `probe_462` pour que les deux ledgers se lisent pareil.
VERT = "VERT"
ROUGE = "ROUGE"
SETUP = "SETUP"
VIDE = "VIDE"

#: Les seuls champs de BILAN. Ils ne sont PAS decoratifs : c'est le bilan ventile qui rend
#: possible le garde `#455` (`passed == 0 and skipped > 0` doit ROUGIR -- un fichier
#: integralement skippe est un vert qui ment). Un champ `verdict` seul ne saurait pas le voir.
CHAMPS_BILAN = ("passed", "failed", "error", "skipped", "xfailed")


def chemin(racine) -> Path:
    return Path(racine) / CHEMIN


# --------------------------------------------------------------------------------- VERDICT

def verdict_de_bilan(bilan: dict) -> str:
    """Le verdict DERIVE du bilan ventile -- jamais ecrit a la main.

    L'ORDRE des tests est le tout, et il reproduit celui de `probe_462` :
      * une ERREUR de setup/teardown n'est PAS un echec d'assertion (`SETUP`) -- confondre les
        deux fait accuser le depot pour une panne de montage ;
      * un echec d'assertion est `ROUGE` ;
      * `passed == 0` est `VIDE`, jamais `VERT`. C'est le garde `#455` : un fichier
        integralement skippe rendait `rc 0` sur `master` avec ZERO assertion evaluee, et rien ne
        le signalait. Un `VIDE` n'est pas valable comme attestation -- il rejoue.
    """
    if int(bilan.get("error", 0)) > 0:
        return SETUP
    if int(bilan.get("failed", 0)) > 0:
        return ROUGE
    if int(bilan.get("passed", 0)) <= 0:
        return VIDE
    return VERT


# ------------------------------------------------------------------------------- LECTURE

def lire(racine) -> tuple[dict, list]:
    """`(entrees, anomalies)`. TOLERANT PAR CONSTRUCTION, et jamais dans le sens permissif.

    Toute anomalie -- fichier absent, JSON illisible, format inconnu, entree non-dict -- rend
    l'entree ABSENTE, donc rejoue. C'est le tri-etat que ce depot tient partout : `null` = PAS
    MESURE, jamais un zero. Un ledger corrompu doit couter du MUR, jamais un faux vert.

    La tolerance a la LIGNE compte pour la concurrence : ce fichier est ecrit par plusieurs agents
    en parallele et peut arriver fusionne par git. Une entree abimee par une fusion est ecartee
    seule -- elle ne fait pas tomber les 235 autres.
    """
    p = chemin(racine)
    anomalies: list[str] = []
    if not p.exists():
        return {}, ["ledger ABSENT (%s) -- aucun vert atteste, tout rejoue" % CHEMIN]
    try:
        brut = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, ["ledger ILLISIBLE (%s) -- tout rejoue" % exc]
    if not isinstance(brut, dict):
        return {}, ["ledger de type %s -- tout rejoue" % type(brut).__name__]
    if brut.get("_format") != FORMAT:
        return {}, ["ledger au format %r (attendu %d) -- illisible sans risque, tout rejoue"
                    % (brut.get("_format"), FORMAT)]
    fichiers = brut.get("fichiers")
    if not isinstance(fichiers, dict):
        return {}, ["ledger sans section `fichiers` -- tout rejoue"]
    propres = {}
    for rel, entree in fichiers.items():
        if not isinstance(rel, str) or not isinstance(entree, dict):
            anomalies.append("entree ECARTEE (forme invalide) : %r" % (rel,))
            continue
        propres[rel] = entree
    return propres, anomalies


# ------------------------------------------------------------------------------- VALIDITE

def ancre_effective(entree, connus: dict) -> str | None:
    """LA plus PRECISE des deux ancres qui soit connue de git, ou `None`.

    `_depuis` (HEAD reel) d'abord : c'est lui qui fait gagner entre deux passes d'une meme
    tranche. `_base` (merge-base) ensuite : elle survit au squash-merge qui tue la premiere.
    `None` si aucune n'est lisible -- et `raison_de_rejeu` le traduit en rejeu, jamais en vert.

    Se degrader vers l'ancre la plus ANCIENNE ne peut que SUR-selectionner : le diff s'allonge,
    donc plus de fichiers sont juges impactes. La perte est du mur, jamais de la surete.
    """
    if not isinstance(entree, dict):
        return None
    for cle in ("_depuis", "_base"):
        sha = entree.get(cle)
        if sha and connus.get(sha):
            return sha
    return None


def raison_de_rejeu(rel: str, entree, blob_courant, ancre, impacte: bool) -> str | None:
    """LE FOYER UNIQUE de la validite. `None` = le vert tient, le fichier peut etre SAUTE.

    Tout autre retour est une CHAINE qui dit pourquoi il rejoue. Un seul foyer, parce qu'un
    garde-fou dont la validite DERIVE entre ses lecteurs ne vaut rien (lecon deja payee sur
    `host_inputs` et rappelee par `probe_462.verdict_effectif`).

    LES SIX CHEMINS, ET AUCUN AUTRE. Le test `test_486r23_ledger_vert_offline` balaie le produit
    CARTESIEN (verdict x commit connu/inconnu x blob egal/different x impacte/non) et exige que
    cette fonction rende `None` sur EXACTEMENT une combinaison : le vert non impacte, au blob
    courant, sur un commit connu. C'est la contre-epreuve de permissivite de `#465`, transposee.

    ⚠ `blob_courant is None` veut dire << git n'a pas su hacher ce fichier >>. C'est une panne de
    MESURE, pas un fait : elle rejoue. La rabattre sur << blob different >> serait juste ici, mais
    la rabattre sur << blob egal >> serait le faux vert -- on ne laisse pas le choix au lecteur.
    """
    if not isinstance(entree, dict):
        return "aucune attestation (jamais joue sous le ledger)"
    verdict = entree.get("verdict")
    if verdict != VERT:
        return "derniere attestation : %s" % (verdict or "?")
    if entree.get("_blob") is None:
        return "attestation sans `_blob` -- cle de validite incomplete"
    if blob_courant is None:
        return "blob COURANT non mesurable (git muet) -- PAS MESURE, donc rejoue"
    if entree.get("_blob") != blob_courant:
        return "le fichier de test a CHANGE depuis l'attestation (blob %s -> %s)" % (
            str(entree.get("_blob"))[:8], str(blob_courant)[:8])
    if not (entree.get("_depuis") or entree.get("_base")):
        return "attestation sans ancre (`_depuis`/`_base`) -- aucune fraicheur verifiable"
    if not ancre:
        return ("attestee depuis %s, INCONNU de ce depot (branche d'agent disparue, et pas de "
                "`_base` lisible) -- ne porte sur aucun arbre d'ici"
                % (str(entree.get("_depuis") or entree.get("_base"))[:8]))
    if impacte:
        return "une dependance MESUREE a change depuis %s" % str(ancre)[:8]
    return None


def a_rejouer(perimetre: list, racine, impactes_depuis) -> tuple[list, dict, list]:
    """`(a rejouer, {rel: raison}, anomalies)` -- LA composition empreinte x ledger.

    `impactes_depuis` est INJECTE (`ref -> set(rel impactes)`), et c'est delibere : ce module ne
    doit rien importer de `probe_457`, qui l'importe. L'arete reste a sens unique, donc pas de
    cycle -- meme arbitrage que `probe_463r1_ecart_empreinte_offline`.

    UN APPEL PAR COMMIT DISTINCT, pas par fichier. Les attestations d'une meme passe partagent
    leur `_depuis` : le nombre d'appels est donc de l'ordre du nombre de PR ayant contribue au
    ledger, pas des 236 fichiers. Le graphe d'imports, lui, est memoise chez l'appelant.
    """
    entrees, anomalies = lire(racine)
    blobs = blobs_courants(racine, list(perimetre))
    connus = commits_connus(racine, [s for e in entrees.values() if isinstance(e, dict)
                                     for s in (e.get("_depuis"), e.get("_base"))])
    ancres = {rel: ancre_effective(e, connus) for rel, e in entrees.items()}

    # Les fichiers dont l'attestation echoue AVANT meme la question du diff n'ont pas besoin que
    # l'on calcule leur impact : on ne paie le diff que pour les candidats reellement en lice.
    par_ancre: dict = {}
    for rel in perimetre:
        e = entrees.get(rel)
        if isinstance(e, dict) and e.get("verdict") == VERT and ancres.get(rel) \
                and e.get("_blob") and blobs.get(rel) == e.get("_blob"):
            par_ancre.setdefault(ancres[rel], []).append(rel)

    impactes: set = set()
    for sha in par_ancre:
        try:
            impactes |= set(impactes_depuis(sha))
        except Exception as exc:                          # noqa: BLE001
            # PAS MESURE : on ne sait pas si ces fichiers sont impactes -> ils le sont TOUS.
            # Le sens sur, et il est DIT -- jamais un vert par defaut d'information.
            anomalies.append("impact depuis %s non mesurable (%s) -- ces fichiers rejouent"
                             % (sha[:8], exc))
            impactes |= set(par_ancre[sha])

    rejeu, raisons = [], {}
    for rel in perimetre:
        motif = raison_de_rejeu(rel, entrees.get(rel), blobs.get(rel),
                                ancres.get(rel), rel in impactes)
        if motif is not None:
            rejeu.append(rel)
            raisons[rel] = motif
    return rejeu, raisons, anomalies


# ------------------------------------------------------------------------------ GIT / BLOBS

def _git(racine, args: list, tolere_rc: bool = False):
    r = subprocess.run(["git", "-C", str(racine), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 and not tolere_rc:
        return None
    return r


def blobs_courants(racine, rels: list, prefixe: str = "scripts/python/") -> dict:
    """`{rel: sha1 du blob DU WORKTREE}`, ou `None` par fichier que git n'a pas su hacher.

    `git hash-object` et non `git ls-files -s` : ce dernier lit l'INDEX, donc il est AVEUGLE a une
    edition non commitee -- exactement le cas d'un agent qui vient de modifier un test. Le blob du
    worktree est le seul qui reponde a << ce que pytest va REELLEMENT jouer >>.

    Par LOTS : 236 chemins tiennent sur une ligne de commande Windows, mais le perimetre grandit
    et un depassement se manifesterait par un rc non nul silencieux -- donc borne d'avance.
    """
    out: dict = {rel: None for rel in rels}
    lot = 80
    for i in range(0, len(rels), lot):
        tranche = rels[i:i + lot]
        r = _git(racine, ["hash-object", "--", *[prefixe + rel for rel in tranche]],
                 tolere_rc=True)
        if r is None or r.returncode != 0:
            continue                      # PAS MESURE pour ce lot -> None -> rejoue
        lignes = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
        if len(lignes) != len(tranche):
            continue                      # appariement douteux -> on ne devine pas
        for rel, sha in zip(tranche, lignes):
            out[rel] = sha
    return out


def commits_connus(racine, shas) -> dict:
    """`{sha: bool}` -- le commit existe-t-il dans CE depot ?

    `cat-file -e <sha>^{commit}` par sha, mais le nombre de shas DISTINCTS est petit (un par
    passe d'ecriture, donc ~un par PR ayant contribue au ledger), pas un par fichier.
    """
    out = {}
    for sha in {s for s in shas if s}:
        r = _git(racine, ["cat-file", "-e", "%s^{commit}" % sha], tolere_rc=True)
        out[sha] = bool(r is not None and r.returncode == 0)
    return out


def base_de_fraicheur(racine) -> tuple[str | None, str]:
    """`(sha, comment il a ete obtenu)` -- la valeur a inscrire dans `_depuis`.

    `merge-base HEAD origin/master` d'abord : c'est le seul point qui SURVIT au squash-merge de la
    branche d'agent. Repli sur `HEAD` si le depot n'a pas de `origin/master` (checkout detache,
    clone sans remote), et le DIRE : une attestation ancree sur HEAD mourra au merge, ce qui coute
    du mur au prochain agent, jamais un faux vert.
    """
    r = _git(racine, ["merge-base", "HEAD", "origin/master"], tolere_rc=True)
    if r is not None and r.returncode == 0 and (r.stdout or "").strip():
        return (r.stdout or "").strip(), "merge-base HEAD origin/master"
    r = _git(racine, ["rev-parse", "HEAD"], tolere_rc=True)
    if r is not None and r.returncode == 0 and (r.stdout or "").strip():
        return (r.stdout or "").strip(), ("HEAD (pas de `origin/master` -- l'attestation ne "
                                          "survivra pas a un squash-merge)")
    return None, "git muet -- aucune base, l'attestation ne sera pas ecrite"


# ------------------------------------------------------------------------------- ECRITURE

def entree_neuve(bilan: dict, sec: float, blob, depuis, head, messages=None,
                 base=None) -> dict:
    """Une entree, dans la signature du ledger live -- plus les DEUX ancres (cf. l'en-tete).

    `sec` n'est pas decoratif non plus : c'est le POIDS, mesure, et il est ici VERSIONNE. Le
    fichier de poids (`logs/ratchets/457-durations.json`) est gitignore, donc un worktree d'agent
    n'en a JAMAIS -- ce qui a produit le bug de `--measure-missing` (235/235 fichiers retenus).
    Un poids porte par le ledger traverse les worktrees, lui.
    """
    e = {
        "_at": int(time.time()),
        "_blob": blob,
        "_commit": head,
        "_depuis": depuis,
        "_base": base,
        "sec": round(float(sec), 3),
        "messages": list(messages or ()),
    }
    for k in CHAMPS_BILAN:
        e[k] = int(bilan.get(k, 0))
    e["verdict"] = verdict_de_bilan(e)
    return e


def fusionner(existantes: dict, neuves: dict, perimetre=None) -> dict:
    """Les neuves ECRASENT, le reste est CONSERVE -- puis RESTRICTION au perimetre.

    La restriction n'est pas cosmetique : un fichier de test supprime ou RENOMME en `_live.py`
    laisserait sinon une attestation FANTOME, que rien ne viendrait plus jamais rafraichir.
    """
    out = dict(existantes)
    out.update(neuves)
    if perimetre is not None:
        garde = set(perimetre)
        out = {k: v for k, v in out.items() if k in garde}
    return out


def ecrire(racine, entrees: dict) -> Path:
    """UNE LIGNE PAR ENTREE, triees. C'est la forme qui rend la fusion git EXPLOITABLE.

    Un JSON indente classique etale une entree sur ~12 lignes : deux agents attestant deux
    fichiers VOISINS produiraient des hunks qui se chevauchent, donc un conflit textuel sur des
    faits qui ne se contredisent pas. Une ligne par entree ramene le conflit a son grain
    semantique : deux agents ne se contredisent que sur le MEME fichier de test.
    """
    p = chemin(racine)
    p.parent.mkdir(parents=True, exist_ok=True)
    lignes = ['{',
              ' "_format": %d,' % FORMAT,
              ' "_ecrit_le": %d,' % int(time.time()),
              ' "fichiers": {']
    cles = sorted(entrees)
    for i, rel in enumerate(cles):
        virgule = "," if i < len(cles) - 1 else ""
        lignes.append('  %s: %s%s' % (json.dumps(rel),
                                      json.dumps(entrees[rel], sort_keys=True), virgule))
    lignes.append(' }')
    lignes.append('}')
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return p


# ------------------------------------------------------------------- CONCURRENCE / CONFLITS

#: Marqueurs de conflit git. Cherches en DEBUT DE LIGNE uniquement.
_DEBUT, _SEP, _FIN, _ANCETRE = "<<<<<<<", "=======", ">>>>>>>", "|||||||"


def resoudre_conflit(texte: str) -> tuple[dict, list]:
    """`(entrees retenues, cles ABANDONNEES)`. La regle : en conflit, on SUPPRIME l'entree.

    Il rend des ENTREES, pas du texte : la ponctuation JSON (virgule de fin de bloc) ne se
    rafistole pas ligne a ligne apres une suppression. L'appelant passe le resultat a `ecrire`,
    qui est le foyer unique de la mise en forme -- donc le fichier resolu est, octet pour octet,
    celui qu'une ecriture normale aurait produit.

    POURQUOI SUPPRIMER PLUTOT QUE CHOISIR -- et pourquoi ce n'est PAS la faute que la doctrine du
    depot interdit (<< un doc genere se REGENERE, il ne se fusionne pas >>).

    Deux agents qui attestent le meme fichier de test l'ont fait sur des arbres DIFFERENTS (chacun
    porte ses propres changements). Les deux attestations sont donc deux affirmations distinctes,
    et apres le merge NI L'UNE NI L'AUTRE ne porte sur l'arbre resultant. Choisir l'une serait
    arbitraire ET faux ; les garder toutes deux est impossible (une seule cle). Les SUPPRIMER rend
    l'entree ABSENTE, ce que `raison_de_rejeu` lit << jamais joue >> : le fichier REJOUE.

    C'est ce qui distingue ce ledger d'un doc genere : **toute perte y est SURE**. Un etat hybride
    ne peut pas produire un faux vert, seulement du mur -- parce que la validite est reverifiee A
    LA LECTURE, contre le depot, et jamais presumee du fait qu'une ligne existe.

    Une ligne survivante n'est PAS crue sur parole non plus : elle repasse par `lire` puis par
    `raison_de_rejeu`. La resolution ne fait donc que choisir ce qui vaut la peine d'etre RELU.
    """
    sortie: list[str] = []
    abandonnees: list[str] = []
    etat = "hors"           # hors | notre | ancetre | leur
    notre: list[str] = []
    leur: list[str] = []

    def _paire(ligne: str):
        """`(cle, entree)` si la ligne EST une entree, sinon `None`. Aucune devinette."""
        s = ligne.strip().rstrip(",")
        if not s.startswith('"') or ":" not in s:
            return None
        cle_txt, _, val_txt = s.partition(":")
        try:
            cle = json.loads(cle_txt.strip())
            val = json.loads(val_txt.strip())
        except ValueError:
            return None
        if not isinstance(cle, str) or not isinstance(val, dict):
            return None
        return cle, val

    def _cle(ligne: str):
        p = _paire(ligne)
        return p[0] if p else None

    for ligne in texte.splitlines():
        if ligne.startswith(_DEBUT):
            etat, notre, leur = "notre", [], []
            continue
        if ligne.startswith(_ANCETRE) and etat != "hors":
            etat = "ancetre"
            continue
        if ligne.startswith(_SEP) and etat != "hors":
            etat = "leur"
            continue
        if ligne.startswith(_FIN) and etat != "hors":
            # LES DEUX COTES SONT ABANDONNES -- y compris les cles presentes d'un seul cote, qui
            # n'ont pourtant rien de contradictoire. C'est assume : git ne dit pas QUELLES lignes
            # d'un hunk se contredisent, et sur-abandonner ne coute que du mur. Sous-abandonner
            # ferait survivre une entree que personne n'a ecrite telle quelle.
            for l in notre + leur:
                c = _cle(l)
                if c is not None:
                    abandonnees.append(c)
            etat = "hors"
            continue
        if etat == "notre":
            notre.append(ligne)
        elif etat == "leur":
            leur.append(ligne)
        elif etat == "ancetre":
            pass
        else:
            sortie.append(ligne)

    perdues = set(abandonnees)
    retenues = {}
    for ligne in sortie:
        p = _paire(ligne)
        if p is None:
            continue
        cle, val = p
        # Une cle abandonnee reste abandonnee MEME si elle survit hors conflit ailleurs dans le
        # fichier : deux occurrences de la meme cle signeraient une fusion qui a duplique le bloc.
        if cle not in perdues:
            retenues[cle] = val
    return retenues, sorted(perdues)
