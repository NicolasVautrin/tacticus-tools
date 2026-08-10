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

import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

#: Chemin VERSIONNE, relatif a la racine du checkout. A cote de ses deux freres
#: (`ratchets-457-footprints.json`, `ratchets-462-live-attestations.json`), et pour la meme
#: raison : sous `logs/` il mourrait avec le worktree, ce qui est precisement le defaut repare.
CHEMIN = "scripts/ratchets-457-vert-offline.json"

#: VERSION DU FORMAT. Un format inconnu ne se devine pas : `lire` rend un ledger VIDE en le
#: DISANT, donc tout rejoue. C'est le seul traitement sur -- lire un format inconnu avec les
#: regles d'un autre produirait un faux vert, pas une sur-selection.
FORMAT = 1

#: PARTS DE LEDGER (#547-r7) -- l'ecriture MULTI-SHARD, qui etait REFUSEE.
#:
#: SOUS `logs/`, donc GITIGNORE et mortel avec le worktree, et c'est le point : une part est un
#: INTERMEDIAIRE de run, jamais un fait a partager. Le seul artefact partage reste le ledger
#: versionne, ecrit par UN SEUL processus -- celui qui consolide.
CHEMIN_PARTS = "logs/ratchets/457-ledger-parts"

#: Format des parts. Meme regle que `FORMAT` : un format inconnu est ECARTE en le disant, jamais
#: interprete avec les regles d'un autre.
FORMAT_PART = 1

#: La variable qui porte le JETON DE RUN. C'est l'identite d'une passe multi-shard : le lanceur en
#: tire un, l'exporte, et tous ses shards l'heritent. La consolidation n'accepte QUE ce jeton-la.
VAR_JETON = "TACTICUS_457_RUN"

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

    # ⚠ L'IMPACT SE JUGE PAR ANCRE, ET L'UNION ETAIT UN BUG (#547-r7). La version precedente
    # UNIONNAIT les impacts de toutes les ancres, puis appliquait cet ensemble a TOUS les
    # fichiers : un fichier atteste a une ancre RECENTE etait donc declare impacte parce qu'un
    # AUTRE fichier, atteste a une ancre ANCIENNE, l'etait. La contamination est mesuree
    # (2026-08-11, apres une passe `--jobs 8` qui venait d'attester 282 fichiers) :
    #
    #     ancre 15fc2a4c (282 entrees, fraiches) ->   9 impactes
    #     ancre 0d6283b6 ( 24 entrees, vieilles) -> 282 impactes
    #     union appliquee a tout               -> 282 rejoues, dont ~273 A TORT
    #
    # Autrement dit : 24 vieilles entrees suffisaient a peremer les 282 qu'on venait de gagner,
    # donc ATTESTER NE SERVAIT A RIEN -- meme forme que le defaut ferme par #547-r5, a un autre
    # etage. La correction RETRECIT la selection et ne peut pas produire de faux vert : elle
    # applique LITTERALEMENT la cle de validite de l'en-tete (<< le fichier ne doit pas etre
    # IMPACTE par le diff `_depuis..HEAD` >>) -- `_depuis` etant le SIEN, pas celui d'un voisin.
    impactes_par_ancre: dict = {}
    for sha in par_ancre:
        try:
            impactes_par_ancre[sha] = set(impactes_depuis(sha))
        except Exception as exc:                          # noqa: BLE001
            # PAS MESURE : on ne sait pas si ces fichiers sont impactes -> ils le sont TOUS,
            # mais SEULEMENT ceux de CETTE ancre. Le sens sur, et il est DIT -- jamais un vert
            # par defaut d'information.
            anomalies.append("impact depuis %s non mesurable (%s) -- ces fichiers rejouent"
                             % (sha[:8], exc))
            impactes_par_ancre[sha] = set(par_ancre[sha])

    rejeu, raisons = [], {}
    for rel in perimetre:
        ancre = ancres.get(rel)
        impacte = rel in impactes_par_ancre.get(ancre, ())
        motif = raison_de_rejeu(rel, entrees.get(rel), blobs.get(rel), ancre, impacte)
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


# -------------------------------------------------------------- PARTS / MULTI-SHARD (#547-r7)

def chemin_parts(racine) -> Path:
    return Path(racine) / CHEMIN_PARTS


def jeton_courant() -> str | None:
    """Le jeton de run herite de l'environnement, ou `None`. Jamais fabrique ici.

    Un jeton fabrique par le shard lui-meme ne servirait a RIEN : chaque shard en aurait un
    different, donc la consolidation ne pourrait plus reconnaitre les siens. C'est le LANCEUR
    qui en tire un et l'exporte -- lui seul sait ce qu'est << ce run >>.
    """
    v = (os.environ.get(VAR_JETON) or "").strip()
    return v or None


def nouveau_jeton() -> str:
    """Un jeton de run. `uuid4` : deux lanceurs simultanes au MEME `HEAD` ne se confondent pas."""
    return uuid.uuid4().hex


def sha_perimetre(perimetre) -> str:
    """Empreinte du PERIMETRE COMPLET tel que la passe l'a vu -- ordre COMPRIS.

    Ce n'est pas un ornement : `fusionner(perimetre=...)` RESTREINT, donc consolider avec un
    perimetre different de celui qu'ont vu les shards effacerait des attestations qu'aucun d'eux
    n'a remises en cause. Deux shards d'un meme run derivent le meme `git ls-files` ; s'ils
    divergent, l'arbre a bouge SOUS le run et la consolidation doit REFUSER, pas arbitrer.
    """
    h = hashlib.sha1()
    for rel in perimetre:
        h.update(rel.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def ecrire_part(racine, jeton: str, head: str, perimetre_sha: str, k: int, n: int,
                entrees: dict, rc: int) -> Path:
    """Depose la part du shard `k/n`. UN FICHIER PAR SHARD -- donc AUCUN read-modify-write.

    C'est tout le mecanisme, et c'est pour cela qu'il est sur : le refus de `_ecrire_ledger`
    portait sur la CONCURRENCE D'ECRITURE (8 processus sur un meme JSON versionne, dernier
    arrive gagnant). Ecrire des fichiers DISJOINTS -- un nom par `(jeton, n, k)` -- supprime la
    course au lieu de la serialiser : pas de verrou, donc rien a laisser orphelin si un shard
    meurt.

    `entrees` VIDE est ecrit quand meme, et c'est deliberement informatif : sans cela, la
    consolidation ne saurait pas distinguer << ce shard a joue et n'a produit aucun report >> de
    << ce shard n'a jamais rendu la main >>. Le tri-etat vaut aussi entre processus.
    """
    d = chemin_parts(racine)
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("part-%s-%02dsur%02d.json" % (jeton, k, n))
    charge = {
        "_format": FORMAT_PART,
        "_jeton": jeton,
        "_head": head,
        "_perimetre_sha": perimetre_sha,
        "_k": int(k),
        "_n": int(n),
        "_rc": int(rc),
        "_at": int(time.time()),
        "fichiers": entrees,
    }
    p.write_text(json.dumps(charge, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return p


def lire_parts(racine) -> tuple[list, list]:
    """`(parts, anomalies)`. Une part illisible est ECARTEE seule, jamais devinee.

    Meme tolerance que `lire`, et pour la meme raison : une part abimee doit couter du MUR (ses
    fichiers rejoueront) et jamais un faux vert.
    """
    d = chemin_parts(racine)
    anomalies: list[str] = []
    if not d.is_dir():
        return [], []
    parts = []
    for p in sorted(d.glob("part-*.json")):
        try:
            brut = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            anomalies.append("part ILLISIBLE %s (%s) -- ecartee" % (p.name, exc))
            continue
        if not isinstance(brut, dict) or brut.get("_format") != FORMAT_PART:
            anomalies.append("part %s au format %r (attendu %d) -- ecartee"
                             % (p.name, (brut or {}).get("_format")
                                if isinstance(brut, dict) else None, FORMAT_PART))
            continue
        if not isinstance(brut.get("fichiers"), dict):
            anomalies.append("part %s sans section `fichiers` -- ecartee" % p.name)
            continue
        brut["_chemin"] = str(p)
        parts.append(brut)
    return parts, anomalies


def parts_retenues(parts: list, jeton: str, head: str, perimetre_sha: str) -> tuple[list, list]:
    """FOYER UNIQUE DU REFUS. `(retenues, [(part, raison) ecartees])`.

    ⚠ LE MODE DE DEFAILLANCE A INTERDIRE EST NOMME, et c'est un FAUX VERT : une part oubliee d'un
    run PRECEDENT porte des verts observes sur un AUTRE arbre. Les fusionner inscrirait au ledger
    versionne une attestation que personne n'a gagnee sur l'arbre courant -- exactement ce que
    `#465` interdit, et ce que le refus historique de `_ecrire_ledger` protegeait.

    TROIS CRITERES, ET AUCUN N'EST REDONDANT :

      1. le JETON -- l'identite du run. Il est le seul a distinguer deux passes lancees au MEME
         `HEAD` sur le MEME arbre (rejeu apres interruption, deux lanceurs simultanes).
      2. le `HEAD` -- il attrape un jeton recycle a la main, et il dit ce que le jeton ne dit
         pas : sur quel commit la part a ete gagnee.
      3. le SHA DU PERIMETRE -- il attrape l'arbre qui BOUGE pendant le run (un fichier de test
         ajoute ou supprime entre deux shards). Consolider avec un perimetre different de celui
         qu'ont vu les shards ferait effacer par `fusionner` des attestations qu'aucun d'eux n'a
         remises en cause.

    Un critere manquant ne se remplace pas par la prudence de l'appelant : c'est ici, et nulle
    part ailleurs, que la question << cette part porte-t-elle sur CET arbre ? >> se tranche.
    """
    gardees, ecartees = [], []
    for part in parts:
        if part.get("_jeton") != jeton:
            ecartees.append((part, "jeton %s (run courant : %s) -- part d'un AUTRE run"
                             % (str(part.get("_jeton"))[:8], str(jeton)[:8])))
            continue
        if part.get("_head") != head:
            ecartees.append((part, "HEAD %s (courant : %s) -- gagnee sur un AUTRE commit"
                             % (str(part.get("_head"))[:8], str(head)[:8])))
            continue
        if part.get("_perimetre_sha") != perimetre_sha:
            ecartees.append((part, "perimetre %s (courant : %s) -- l'arbre a bouge pendant le run"
                             % (str(part.get("_perimetre_sha"))[:8], str(perimetre_sha)[:8])))
            continue
        gardees.append(part)
    return gardees, ecartees


def consolider(racine, jeton: str, head: str, perimetre: list) -> dict:
    """Fusionne les parts DU RUN COURANT dans le ledger versionne. Rend un compte-rendu.

    DECIDE D'ABORD, ECRIT ENSUITE -- meme discipline que partout ailleurs dans cette machinerie :
    tout est trie et compte avant qu'une seule ligne du fichier versionne ne bouge.

    Le compte-rendu porte `manquants` : les shards dont AUCUNE part n'a ete retenue. Ce n'est pas
    une erreur -- un shard peut avoir refuse d'attester (rc d'usage, aucun report) -- mais c'est
    un fait a DIRE : ces fichiers-la n'ont pas d'attestation neuve, donc ils rejoueront. Le taire
    ferait lire une consolidation partielle comme une passe complete.
    """
    perimetre_sha = sha_perimetre(perimetre)
    parts, anomalies = lire_parts(racine)
    gardees, ecartees = parts_retenues(parts, jeton, head, perimetre_sha)

    neuves: dict = {}
    doublons: list = []
    n_declares = {int(p.get("_n") or 0) for p in gardees}
    for part in sorted(gardees, key=lambda p: int(p.get("_k") or 0)):
        for rel, entree in (part.get("fichiers") or {}).items():
            if not isinstance(rel, str) or not isinstance(entree, dict):
                anomalies.append("entree ECARTEE (forme invalide) dans %s : %r"
                                 % (Path(part["_chemin"]).name, (rel,)))
                continue
            if rel in neuves:
                # Deux shards ont atteste le MEME fichier : la partition est censee etre
                # disjointe, donc c'est un fait anormal. On ECARTE les deux (l'entree ne
                # survit pas), meme regle que `resoudre_conflit` -- le fichier rejouera.
                doublons.append(rel)
                continue
            neuves[rel] = entree
    for rel in set(doublons):
        neuves.pop(rel, None)
        anomalies.append("fichier atteste par PLUSIEURS shards, entree ABANDONNEE : %s" % rel)

    couverts = {int(p.get("_k") or 0) for p in gardees}
    total = max(n_declares) if n_declares else 0
    manquants = sorted(set(range(total)) - couverts) if total else []

    anciennes, anomalies_ledger = lire(racine)
    fusion = fusionner(anciennes, neuves, perimetre=perimetre)
    return {
        "fusion": fusion,
        "neuves": neuves,
        "gardees": gardees,
        "ecartees": ecartees,
        "manquants": manquants,
        "n_shards": total,
        "anomalies": list(anomalies) + list(anomalies_ledger),
        "perimetre_sha": perimetre_sha,
    }


def purger_parts(racine, parts: list) -> int:
    """Supprime les parts nommees. Une part CONSOMMEE ne doit pas pouvoir l'etre deux fois.

    C'est le second cran contre la part orpheline : le premier (`parts_retenues`) l'ECARTE a la
    lecture, celui-ci l'empeche d'exister. Une suppression qui echoue n'est pas une panne du
    mecanisme -- la part reste, et le jeton du run suivant la rejettera.
    """
    n = 0
    for part in parts:
        chemin_ = part.get("_chemin")
        if not chemin_:
            continue
        try:
            Path(chemin_).unlink()
            n += 1
        except OSError:
            continue
    return n


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


def main(argv=None) -> int:
    """`--resoudre` : le point d'entree que le mecanisme n'avait pas.

    Sans lui, `resoudre_conflit` etait une fonction que personne en situation de conflit ne
    pouvait appeler -- et la reaction par defaut aurait ete de resoudre le JSON A LA MAIN, ce qui
    est precisement la faute que la regle << on regenere, on ne fusionne pas >> vise.
    """
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--resoudre", action="store_true",
                    help="Resout un ledger laisse EN CONFLIT par git : abandonne les entrees "
                         "disputees (elles rejoueront) et reecrit le fichier par le foyer "
                         "d'ecriture, donc a l'octet pres comme une passe normale l'aurait ecrit.")
    ap.add_argument("--racine", default=None,
                    help="Racine du checkout (defaut : deduite de l'emplacement de ce fichier).")
    args = ap.parse_args(argv)

    racine = Path(args.racine) if args.racine else Path(__file__).resolve().parents[2]
    if not args.resoudre:
        entrees, anomalies = lire(racine)
        for a in anomalies:
            print("[ledger] %s" % a)
        verts = sum(1 for e in entrees.values() if e.get("verdict") == VERT)
        print("[ledger] %s : %d entree(s), %d VERT" % (CHEMIN, len(entrees), verts))
        return 0

    p = chemin(racine)
    if not p.exists():
        print("[ledger] %s absent -- rien a resoudre." % CHEMIN)
        return 1
    texte = p.read_text(encoding="utf-8")
    if _DEBUT not in texte:
        print("[ledger] %s ne porte AUCUN marqueur de conflit -- rien a resoudre." % CHEMIN)
        return 0
    retenues, abandonnees = resoudre_conflit(texte)
    ecrire(racine, retenues)
    print("[ledger] resolu : %d entree(s) retenue(s), %d ABANDONNEE(S) (elles rejoueront) :"
          % (len(retenues), len(abandonnees)))
    for cle in abandonnees[:10]:
        print("    %s" % cle)
    print("[ledger] une entree abandonnee coute un REJEU, jamais un faux vert -- la validite est")
    print("[ledger] reverifiee a la lecture, contre le depot.")
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main())
