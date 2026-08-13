"""#547 -- CLIQUET : le LEDGER VERSIONNE du vert offline ne porte AUCUN verdict non-VERT.

CE QU'IL EST SEUL A VOIR
------------------------
Un rouge offline **MESURE, ECRIT, COMMITE et LIVRE**.

Ce n'est pas une hypothese. Mesure du 2026-08-08, sur `origin/master` :
`scripts/ratchets-457-vert-offline.json` portait **8 entrees `ROUGE`**, toutes horodatees du
2026-08-08 02:13, toutes ecrites par le commit `bfa97ce8` d'un worktree d'agent, et arrivees sur
`master` par le squash-merge `785855e2` (PR #835). Les fichiers nommes etaient exacts --
`test_337_dsl_triggers_attestation_offline.py`,
`test_433_r4_r2_r1_r2_r2_r1_r1_r1_r4_caster_reason_offline.py`,
`test_433r4r1r4r2r1r1_derivation_morte_offline.py` et cinq autres. Deux d'entre eux etaient
encore rouges 24 h plus tard.

⚠ LA MESURE EXISTAIT DONC, ET RIEN NE LA LISAIT. C'est ce qui distingue ce gisement de tous ses
voisins : `#455` garde un fichier integralement skippe, `#455-r3` un fichier dont les tests ont
disparu, `#486-r15` un DECLENCHEUR trop etroit -- les trois gardent une passe qui A EU LIEU. Ici la
passe a eu lieu, a rendu le bon verdict, l'a inscrit dans un fichier VERSIONNE, et personne n'a
regarde. Aucun cliquet ne lisait le ledger ; `probe_457` l'ECRIT et le consomme pour SELECTIONNER,
jamais pour JUGER.

⚠ UNE ATTESTATION N'EST PAS UN ETAT : ELLE PORTE SUR UN ARBRE, ET IL FAUT LE DIRE (#547-r2)
--------------------------------------------------------------------------------------------
Ce cliquet a d'abord lu le VERDICT ECRIT et rien d'autre. C'etait un compte FAUX PAR
CONSTRUCTION, et le foyer savait deja pourquoi : `ledger_vert_offline.raison_de_rejeu` -- LA
fonction dont `probe_457` derive ses rejeux -- refuse un vert des que le blob du test a change, que
son ancre est inconnue, ou qu'**une dependance MESUREE a change depuis**. C'est ce dernier chemin
qui compte ici, et il est le seul que le blob ne voit pas.

MESURE qui l'etablit (2026-08-10, sur le perimetre de 290 fichiers) : **0 attestation sur 290 etait
VALABLE sur l'arbre courant** -- 272 invalidees par un changement de dependance depuis leur ancre,
11 sans attestation, 4 au blob change, 3 non-VERT. Le cliquet, lui, imprimait
`entrees NON-VERT : 0, dont 0 NON DECLAREES` et concluait `PASS`. Les TROIS rouges de `master`
trouves le meme jour (`test_477r24r1_slots_interface_offline`,
`test_421_effect_active_gate_offline`, `test_camo_seed_inventory_offline`) sont exactement de ce
type : des tests dont le PERIMETRE est l'ARBRE (couverture d'un registre), donc qui rougissent sans
que leur propre blob ait bouge. Leur attestation restait verte, et rien ne demandait si elle valait
encore.

⇒ CE CLIQUET NE RABAT PLUS UN VERT PERIME SUR UN VERT. Il classe chaque fichier du perimetre en
TROIS etats -- VALABLE ICI / non-VERT / **PAS MESURE ICI** -- et le compte de tete porte desormais
son denominateur. C'est le tri-etat de `host_inputs` (`null` = pas mesure, jamais un zero),
transpose au ledger.
⚠ La staleness ne fait PAS rougir, et c'est un choix DIT : toute PR change une dependance de
presque tous les tests, donc un rouge sur ce critere serait permanent et donc muet. Ce qui est
exigible, c'est que le chiffre soit LU -- pas qu'il soit nul.
⚠ Et le marquage des tests << a perimetre ARBRE >> a ete ECARTE PAR LA MESURE : il aurait ete
redondant. Le foyer voyait deja ces trois fichiers comme invalides (`une dependance MESUREE a
change depuis a55d7539`, verbatim). Ce qui manquait n'etait pas un capteur, c'etait un LECTEUR.

CE QU'IL NE VOIT PAS -- et il l'IMPRIME, parce qu'un vert muet se lirait << tout l'offline est
vert >> :
  * un fichier du perimetre offline SANS AUCUNE entree -- jamais joue, donc jamais atteste ;
  * une entree dont l'attestation est PERIMEE (le blob du fichier de test a change depuis) ;
  * les `*_live.py`, hors du perimetre de `probe_457` PAR CHOIX. Un test purement offline
    HEBERGE dans un fichier `_live.py` est donc invisible des deux cotes -- c'est le cas de
    `test_pre_unit_ability_fork_live::test_port_reproduces_replaced_target_offline`, rouge sur
    `master` le meme jour sans qu'aucun des deux gardes puisse le voir.

POLARITE : LISTE BLANCHE D'UN SEUL ELEMENT, ET ELLE EST DERIVEE
---------------------------------------------------------------
Le critere n'est pas << pas de `ROUGE` >> mais << rien d'autre que `VERT` >>, et `VERT` est LU
dans le foyer (`ledger_vert_offline.VERT`). `SETUP` (panne de montage) et `VIDE` (zero test passe,
le garde `#455`) rougissent donc aussi, et un verdict NEUF introduit demain rougira sans qu'on ait
rien a ajouter ici. Une liste blanche de rouges connus ne peut pas montrer le verdict qu'elle a
oublie -- c'est le vice que ce depot a deja paye sur son recenseur d'enums.

CONTRE-EPREUVE INTEGREE (idiome #421) : `--mutants` fabrique en MEMOIRE les ledgers que le cliquet
doit refuser, et exige qu'il les refuse. Un cliquet dont on n'a pas montre qu'il MORD est un vert
qui ne prouve rien.

100 % OFFLINE, aucune ecriture. ASCII only.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import ledger_vert_offline as ledger              # noqa: E402

ROOT = PYDIR.parent.parent
PREFIXE = "scripts/python/"

EX_NON_MESURE = 99                                # convention `ratchets-bg.ps1` : aucun verdict

#: LES NON-VERT DECLARES -- `{chemin: raison}`. Un gisement OUVERT, dont la reparation est nommee
#: et ne tient pas dans la tranche courante, n'est pas la meme chose qu'un rouge livre en silence :
#: le premier est un ETAT CONNU, le second est ce que ce cliquet interdit.
#:
#: ⚠ DEUX CRANS, et le SECOND est ce qui empeche cette liste de pourrir en allowlist molle :
#:   1. une entree non-VERT HORS de cette liste fait ROUGIR (le cliquet) ;
#:   2. une entree de cette liste qui est redevenue VERTE fait ROUGIR AUSSI -- la declaration est
#:      PERIMEE et doit sortir. C'est l'idiome de l'etape 5 de
#:      `probe_433r4r1r4r2_neigh_channel_wired` (<< la SUSPENSION d'un natif lu est-elle encore
#:      justifiee ? >>). Sans lui, une ligne oubliee ici masquerait un rouge futur du meme fichier.
#: Chaque ligne porte le numero du residu qui la ferme. Pas de numero => pas de ligne.
NON_VERTS_DECLARES: dict[str, str] = {
    # LES CINQ ROUGES QUE LA PASSE COMPLETE A MIS AU JOUR -- residu #547-r6. Ils ne sont PAS le
    # fait de cette tranche : les CINQ ont ete rejoues dans un worktree TEMOIN a `origin/master`
    # PUR (`ea55462c`) et y rendent `rc=1` a l'identique. Ils n'etaient pas VISIBLES avant parce
    # que le ledger ne portait AUCUNE attestation a jour : c'est la passe `--measure` de cette
    # tranche (290 fichiers, 4047 passed / 8 failed en 2220 s) qui les a inscrits. Chacun porte
    # son assertion, pas une paraphrase.
    # DEUX ROUGES DE `master` MIS AU JOUR PAR LE REJEU DE #547-r7 -- residu #547-r10. Ils ne sont
    # PAS le fait de cette tranche, et leur provenance est MESUREE (`git log -S`), pas supposee :
    # l'un date d'avant son lancement, l'autre est arrive PAR LE REBASE. Ils n'etaient pas
    # visibles parce que le ledger ne portait aucune attestation a jour sur ces fichiers.
    # ⚠ DEUX LIGNES SONT SORTIES D'ICI PAR LE CRAN 2 (#962), et les DEUX causes sont differentes --
    # c'est exactement ce que ce cran existe pour distinguer :
    #   * `tests/test_337_dsl_triggers_attestation_offline.py` -- REPARE par #962. Sa ligne
    #     accusait `AttackUsedAttackDamage` (deja reparee par `56250b3d`) alors que le rouge
    #     COURANT portait sur TROIS autres primitives (`IsHero`, `IsPlayerDefeated`, `OnDeath`) :
    #     la declaration etait donc a la fois PERIMEE et VRAIE, le pire des deux etats -- elle
    #     aurait absous n'importe quel rouge futur de ce fichier.
    #   * `tests/test_480r8_rpc_joignable_offline.py` -- REDEVENU VERT sur `master` (3 passed,
    #     mesure du 2026-08-12). Personne n'avait retire sa ligne.
    "tests/engine/test_477r24r1_slots_interface_offline.py":
        "REPARE par #962-r1 -- le fichier rend 59 passed / 0 failed (mesure du 2026-08-13). Cette "
        "ligne ne subsiste que parce que l'ATTESTATION du ledger, elle, date d'avant : elle porte "
        "encore `ROUGE {'passed': 57, 'failed': 2}`, et le CRAN 1 rougirait sans elle. Elle DOIT "
        "sortir au premier `probe_457` qui rejoue ce fichier -- c'est le CRAN 2 qui l'y forcera. "
        "CE QUI A ETE REPARE : la phrase de "
        "`scripts/python/tests/engine/test_953r2_preattack_place_live.py` nommait `IBattleQuery` "
        "pour les trois slots du groupe atomique ; ce sont ceux de `Core.Services.IMatchState` "
        "(10 `TryDequeueBattleEvent`, 20 `IncreaseAtomicModeCounter`, 21 "
        "`DecreaseAtomicModeCounter`), LUS dans "
        "`data/symbols/rnca9r7q6c/metadata/interface_slots.tsv`. Aucun nom devine : le triplet "
        "tombe sur la MEME interface et sa semantique concorde avec le decompile. Residu #962-r1.",
    # ⚠ TROIS LIGNES SONT SORTIES D'ICI PAR LE CRAN 2, ET C'EST LA PREMIERE FOIS QU'ELLES SORTENT
    # SUR UNE MESURE FRAICHE (#547-r5). Elles y etaient toutes les trois parce que le ledger ne se
    # rejouait pas -- l'une le DISAIT explicitement (<< elle sortira a la prochaine passe
    # ordinaire >>). La passe ordinaire a eu lieu : 299 entrees, 295 VERT, 4 non-VERT.
    #   * `test_270r4_role_enum_offline.py` -- REPARE sur `master`, l'entree ROUGE etait un
    #     RESIDU D'ARBRE ANTERIEUR ;
    #   * `test_463r1_ecart_empreinte_offline.py` -- le FANTOME est PURGE, et sa cause
    #     structurelle est fermee : `_empreinte_fusionnee` restreint desormais au perimetre, donc
    #     `--measure-missing` purge un fichier supprime ou renomme (avant, seul `--measure` le
    #     faisait -- 2 220 s pour effacer la trace d'un renommage a 1 s) ;
    #   * `test_host_inputs_offline.py` -- REPARE, et son DIAGNOSTIC ETAIT FAUX. La ligne accusait
    #     le regime worktree (<< etage 3, `frida/data/_absent_273 : INTROUVABLE (pas mesure)` >>),
    #     qui est la sortie ATTENDUE d'un controle qui PASSE. La cause reelle etait a l'ETAPE 0 :
    #     `probe_448r1r1r2r2r1_gates_amont.py` ecrivait son state-file sous `scripts/python/logs/`,
    #     ce que #455 interdit et que `probe_273` sort en `[FAIL]`.
    # VIDE POUR LE RESTE, et c'est un ETAT MESURE. Les TROIS lignes qui vivaient ici
    # (#270-r4-r2-r2 seuil des differes, #448-r1 stormboyz, #462-r4b-r1-r1 producteurs d'additif)
    # ont ete FERMEES par #547-r2, chacune par sa cause propre -- pas retirees pour faire taire :
    #   * le seuil a ete RE-MESURE (partition exhaustive + debit par commit) apres remise a ZERO
    #     des differes GRATUITS, en FORME B ;
    #   * le stub de tri de stormboyz etait en retard d'un argument sur une signature CONFIRMEE au
    #     decompile (deux surcharges de `IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtility`) ;
    #   * le 4e producteur d'additif defenseur a ete CONFRONTE en combat (bras `herald`).
    # Le CRAN 2 exige qu'une ligne sorte des que son fichier redevient vert : ce dict a donc
    # vocation a etre vide la plupart du temps.
}

# ⚠ CE QUI A DEJA ETE RETIRE D'ICI, ET CE QUE CA MESURE. `test_486r15_empreinte_par_entree_offline
# .py` (`test_la_DETTE_ne_peut_pas_absoudre_ce_qui_declare_deja`, 1 failed / 26 passed) y a figure
# QUELQUES HEURES : il a ete repare sur `master` par `dd85e821` (<< retirer de la dette un fichier
# qui DECLARE -- signale trois fois, jamais repare >>) pendant que cette tranche etait en vol, et
# le CRAN 2 l'a fait sortir au rebase suivant. C'est exactement le cycle de vie qu'une ligne d'ici
# doit avoir : entrer parce qu'un rouge est MESURE, sortir des qu'il ne l'est plus -- et le cliquet
# qui l'exige est ce qui empeche la liste de devenir une allowlist.
#
# ⚠ DEUXIEME SORTIE, meme cycle : `tests/engine/runner/test_421_effect_active_gate_offline.py`
# (`test_the_probe_rail_covers_the_whole_registry`, 1 failed / 12 passed) est retire par **#549**,
# qui l'a DIAGNOSTIQUE en jouant le garde : `HeraldOfTheApocalypseExtraDamageRemove` etait inscrit
# dans `EFFECT_TRIGGERS` sans rail declare dans `probe_229.RAIL` (#BL-1020r). Rail LU --
# `IdunBattle.Entities.Effects.Loki.HeraldOfTheApocalypse_ExtraDamageEffect$$
# CreateRemoveEffectTrigger` existe dans `frida/methods.tsv`, et la classe n'a AUCUN
# `CreateTargetTrigger` -> ARRAYSET. Le fichier est VERT ; la ligne devait donc sortir, sans quoi
# elle aurait masque son prochain rouge.
# ⚠ ET ELLE N'ETAIT PAS SORTIE : ce paragraphe a ete ecrit par #549, l'entree du dict est RESTEE.
# `probe_547` la nommait `[DECLARATION PERIMEE]` sur `edfdda38` -- le CRAN 2 faisait donc rougir
# `master` sur une reparation REUSSIE, ce qui est exactement le vice symetrique de celui que le
# CRAN 1 garde. Retirer POUR DE BON fait partie de la fermeture. Re-mesure du 2026-08-08 : le
# fichier rend 13 passed. Ligne effectivement retiree par #547-r4.
#
# ⚠ TROISIEME SORTIE, meme cycle : `tests/engine/test_498r4_face_decision_is_displaceable_offline
# .py` (`test_le_recenseur_ne_credite_pas_une_condition_seulement_CITEE`, 1 failed / 9 passed) a
# ete repare sur `master` par `627a62ac` -- un SEUIL HAUT (`== 2`) qu'un port legitime a fait
# CROITRE, converti en borne BASSE apres MESURE des trois sites, jamais bumpe a 3. Re-mesure du
# 2026-08-08 : 10 passed. Ligne retiree par #547-r4, qui repare trois autres fichiers de la MEME
# famille : une assertion qui epingle une population que `ABILITY_CLASSES` deplace.


class MontageImpossible(RuntimeError):
    """Panne d'OUTIL (git muet, ...) -- rend `EX_NON_MESURE`, jamais un rouge de gisement.

    Meme discipline que `probe_457._git` : un cliquet qui rougit sans avoir rien mesure fait
    corriger la mauvaise cause (#471)."""


def _git(args: list, tolere_rc: bool = False) -> str:
    try:
        p = subprocess.run(["git"] + args, cwd=str(ROOT), capture_output=True, text=True,
                           errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise MontageImpossible("git injouable (%s) : %s" % (type(exc).__name__, exc))
    if p.returncode != 0 and not tolere_rc:
        raise MontageImpossible("git %s -> rc=%d : %s"
                                % (" ".join(args[:2]), p.returncode, (p.stderr or "").strip()[:200]))
    return p.stdout


def perimetre_offline() -> list:
    """Les fichiers de test NON-`_live.py`, DERIVES de `git ls-files` -- jamais une allowlist.

    Meme critere que `probe_457` : le suffixe est DECLARATIF et tenu par le depot, la cloture de
    fixtures a ete refutee par mesure (elle classait des dizaines de `*_live.py` en offline)."""
    out = _git(["ls-files", PREFIXE + "tests"])
    rels = []
    for ligne in out.splitlines():
        rel = ligne.strip()
        if not rel.startswith(PREFIXE) or not rel.endswith(".py"):
            continue
        nom = rel.rsplit("/", 1)[-1]
        if not nom.startswith("test_") or nom.endswith("_live.py"):
            continue
        rels.append(rel[len(PREFIXE):])
    if not rels:
        raise MontageImpossible("perimetre offline VIDE -- `git ls-files` n'a rien rendu")
    return sorted(rels)


def non_verts(entrees: dict) -> list:
    """`[(rel, verdict, bilan)]` -- toute entree dont le verdict n'est pas `VERT`.

    Le verdict est RE-DERIVE du bilan ventile quand celui-ci est present : une entree qui
    porterait `verdict: VERT` avec `failed: 3` serait sinon acceptee sur sa propre etiquette."""
    out = []
    for rel, e in sorted(entrees.items()):
        bilan = {c: e.get(c) for c in ledger.CHAMPS_BILAN}
        derive = (ledger.verdict_de_bilan({k: v for k, v in bilan.items() if v is not None})
                  if any(v is not None for v in bilan.values()) else None)
        ecrit = e.get("verdict")
        v = derive if derive is not None else ecrit
        if v != ledger.VERT or (ecrit is not None and ecrit != v):
            out.append((rel, ecrit, v, bilan))
    return out


def crans(mauvais: list, declares: dict) -> tuple[list, list]:
    """`(non-VERT NON DECLARES, declarations PERIMEES)` -- les deux seules causes de rouge.

    Fonction PURE, pour que la contre-epreuve puisse l'exercer sans ledger ni git."""
    non_declares = [m for m in mauvais if m[0] not in declares]
    encore = {m[0] for m in mauvais}
    perimees = sorted(r for r in declares if r not in encore)
    return non_declares, perimees


def validite(rels: list) -> tuple[dict, list]:
    """`({rel: raison|None}, anomalies)` -- L'ATTESTATION DE CHAQUE FICHIER PORTE-T-ELLE SUR CET
    ARBRE ? `None` = oui. Toute autre valeur est la raison, LUE DU FOYER.

    ⚠ LE FOYER EST CELUI DE `probe_457`, PAS UNE SECONDE DERIVATION. `ledger.a_rejouer` compose
    `raison_de_rejeu` (les six chemins de validite) avec la fonction d'impact de
    `probe_457.impacted_files` -- celle-la meme qui decide un rejeu. Redonner ici un critere a nous
    aurait fabrique le vice que ce depot a deja paye sur `host_inputs` : deux lecteurs d'une meme
    verite qui divergent. Le prix est le graphe d'imports (~1 min) ; il est paye, parce que le
    chemin << une dependance MESUREE a change >> est le SEUL qui voie un test dont le PERIMETRE est
    l'arbre, et c'est precisement le type des rouges que ce cliquet a laisse passer.

    Une panne de la mesure d'impact n'est JAMAIS un vert : `a_rejouer` range alors les fichiers
    concernes en rejeu et le DIT par une anomalie (contrat du foyer)."""
    import probe_457_offline_tests_green as p457     # forme B -- module, pas symbole (CLAUDE.md)
    garde = set(rels)
    try:
        _rejeu, raisons, anomalies = ledger.a_rejouer(
            rels, ROOT,
            lambda sha: [r for r in p457.impacted_files(p457.candidate_files(), sha)[0]
                         if r in garde])
    except Exception as exc:                     # noqa: BLE001 -- panne d'OUTIL, pas un gisement
        raise MontageImpossible("validite des attestations non mesurable : %s: %s"
                                % (type(exc).__name__, exc))
    return {r: raisons.get(r) for r in rels}, anomalies


def classer(rels: list, raisons: dict, non_vert_rels: set) -> tuple[list, list, dict]:
    """`(VALABLES ICI, PAS MESURE ICI, causes)` -- la partition du perimetre sur l'axe VALIDITE.

    Fonction PURE : la contre-epreuve l'exerce sans git ni ledger. Un fichier deja compte comme
    non-VERT n'entre pas dans `PAS MESURE` -- il a un verdict, et c'est lui qui prime ; sans quoi
    un rouge disparaitrait dans le tas des perimes."""
    valables = [r for r in rels if raisons.get(r) is None]
    pas_mesure = [r for r in rels if raisons.get(r) is not None and r not in non_vert_rels]
    causes: dict = {}
    for r in pas_mesure:
        cle = str(raisons[r]).split(" (")[0].split(" --")[0]
        causes[cle] = causes.get(cle, 0) + 1
    return valables, pas_mesure, causes


def portee(entrees: dict, rels: list) -> dict:
    """CE QUE LE VERT DE CE CLIQUET NE COUVRE PAS. Mesure, jamais rougi -- mais IMPRIME."""
    sans = [r for r in rels if r not in entrees]
    try:
        blobs = ledger.blobs_courants(ROOT, [r for r in rels if r in entrees], PREFIXE)
    except Exception as exc:                      # noqa: BLE001 -- panne d'outil, pas un gisement
        raise MontageImpossible("`git hash-object` injouable : %s" % exc)
    perimees = [r for r in rels
                if r in entrees and blobs.get(r) is not None
                and entrees[r].get("_blob") != blobs.get(r)]
    return {"sans_entree": sans, "attestation_perimee": perimees,
            "hors_perimetre_live": len([1 for l in _git(["ls-files", PREFIXE + "tests"]).splitlines()
                                        if l.strip().endswith("_live.py")])}


def mesurer() -> tuple[int, dict]:
    entrees, anomalies = ledger.lire(ROOT)
    rels = perimetre_offline()
    if not entrees:
        # Ledger absent/illisible : AUCUN verdict sur le depot. Ce n'est ni un vert ni un rouge.
        return EX_NON_MESURE, {"anomalies": anomalies, "entrees": 0, "perimetre": len(rels)}
    mauvais = non_verts(entrees)
    p = portee(entrees, rels)
    # TRI-ETAT (#547-r2) : l'attestation de chaque fichier porte-t-elle sur CET arbre ? Un vert qui
    # n'y porte pas est `PAS MESURE ICI`, jamais un vert.
    raisons, anomalies_v = validite(rels)
    anomalies = list(anomalies) + list(anomalies_v)
    valables, pas_mesure, causes = classer(rels, raisons, {m[0] for m in mauvais})
    # CRAN 1 : non-VERT hors declaration. CRAN 2 : declaration PERIMEE (le fichier est redevenu
    # vert, ou a disparu du ledger) -- elle doit sortir, sinon elle masquerait un rouge futur.
    non_declares, perimees = crans(mauvais, NON_VERTS_DECLARES)
    return (1 if (non_declares or perimees) else 0), {
        "anomalies": anomalies, "entrees": len(entrees), "perimetre": len(rels),
        "non_verts": mauvais, "non_declares": non_declares, "declarations_perimees": perimees,
        "valables": valables, "pas_mesure_ici": pas_mesure, "causes_pas_mesure": causes,
        "portee": p}


# ------------------------------------------------------------------------------- CONTRE-EPREUVE

#: Chaque mutant est un ledger FABRIQUE que le cliquet DOIT refuser. `sain=True` = il doit
#: l'accepter (un mutant sain qui rougit dirait que le critere est trop large).
def mutants() -> list:
    base = {"_at": 1, "_base": "0" * 40, "_blob": "0" * 40, "_commit": "0" * 40,
            "_depuis": "0" * 40, "passed": 3, "failed": 0, "error": 0, "skipped": 0, "xfailed": 0,
            "verdict": ledger.VERT}

    def av(**kw):
        e = dict(base)
        e.update(kw)
        return {"tests/x.py": e}

    return [
        ("M1 verdict ROUGE ecrit", av(verdict=ledger.ROUGE, failed=2, passed=1), False),
        ("M2 verdict SETUP (panne de montage)", av(verdict=ledger.SETUP, error=1, passed=0), False),
        ("M3 verdict VIDE (garde #455)", av(verdict=ledger.VIDE, passed=0, skipped=8), False),
        ("M4 etiquette VERT mais bilan ROUGE", av(verdict=ledger.VERT, failed=3), False),
        ("M5 verdict INCONNU (vocabulaire elargi demain)", av(verdict="TIEDE"), False),
        ("M6 SAIN -- vert franc", av(), True),
        ("M7 SAIN -- vert avec des skips (mais du passed)", av(passed=2, skipped=5), True),
    ]


#: Mutants des DEUX CRANS. `(nom, mauvais, declares, doit_rougir)`.
def mutants_crans() -> list:
    m = [("tests/a.py", "ROUGE", "ROUGE", {})]
    return [
        ("C1 non-VERT NON declare", m, {}, True),
        ("C2 non-VERT declare -- tolere", m, {"tests/a.py": "residu #x"}, False),
        ("C3 declaration PERIMEE (le fichier est redevenu vert)", [], {"tests/a.py": "residu #x"},
         True),
        ("C4 declare + un AUTRE non declare", m + [("tests/b.py", "VIDE", "VIDE", {})],
         {"tests/a.py": "residu #x"}, True),
        ("C5 SAIN -- rien de non-VERT, rien de declare", [], {}, False),
    ]


#: Mutants de l'axe VALIDITE (#547-r2). `(nom, rels, raisons, non_vert, valables, pas_mesure)`.
#: Ils exercent la SEULE chose qui manquait au cliquet : un vert qui ne porte pas sur cet arbre
#: doit sortir en `PAS MESURE`, jamais grossir le tas des attestations.
def mutants_validite() -> list:
    rels = ["tests/a.py", "tests/b.py", "tests/c.py"]
    return [
        ("V1 vert VALABLE -- compte comme atteste",
         rels[:1], {"tests/a.py": None}, set(), 1, 0),
        ("V2 vert INVALIDE par une dependance changee -- PAS MESURE, pas un vert",
         rels[:1], {"tests/a.py": "une dependance MESUREE a change depuis abcd1234"}, set(), 0, 1),
        ("V3 non-VERT invalide -- reste un ROUGE, ne disparait pas dans les perimes",
         rels[:1], {"tests/a.py": "derniere attestation : ROUGE"}, {"tests/a.py"}, 0, 0),
        ("V4 melange -- un valable, un perime, un rouge",
         rels, {"tests/a.py": None, "tests/b.py": "blob change", "tests/c.py": "ROUGE"},
         {"tests/c.py"}, 1, 1),
    ]


def jouer_mutants() -> int:
    rate = []
    for nom, entrees, sain in mutants():
        mauvais = non_verts(entrees)
        detecte = bool(mauvais)
        if detecte == (not sain):
            print("   [%s] %s" % ("OK" if sain else "DETECTE", nom))
        else:
            print("   [*** RATE ***] %s -- %s" % (nom, "non detecte" if not sain else "faux rouge"))
            rate.append(nom)
    for nom, mauvais, declares, doit in mutants_crans():
        nd, per = crans(mauvais, declares)
        rougit = bool(nd or per)
        if rougit == doit:
            print("   [%s] %s" % ("DETECTE" if doit else "OK", nom))
        else:
            print("   [*** RATE ***] %s -- %s" % (nom, "non detecte" if doit else "faux rouge"))
            rate.append(nom)
    for nom, rels, raisons, non_vert, n_val, n_pas in mutants_validite():
        val, pas, _c = classer(rels, raisons, non_vert)
        if (len(val), len(pas)) == (n_val, n_pas):
            print("   [OK] %s" % nom)
        else:
            print("   [*** RATE ***] %s -- valables %d (attendu %d), pas-mesure %d (attendu %d)"
                  % (nom, len(val), n_val, len(pas), n_pas))
            rate.append(nom)
    total = len(mutants()) + len(mutants_crans()) + len(mutants_validite())
    print("   mutants : %d/%d conformes" % (total - len(rate), total))
    return 1 if rate else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mutants", action="store_true",
                    help="ne joue QUE la contre-epreuve (le cliquet mord-il ?)")
    args = ap.parse_args(argv)

    print("== #547 -- le ledger versionne du vert offline ne porte que des VERT")
    print("-- contre-epreuve : le cliquet MORD-il ?")
    rc_mut = jouer_mutants()
    if args.mutants:
        print("VERDICT: %s" % ("PASS" if rc_mut == 0 else "FAIL"))
        return rc_mut

    try:
        rc, info = mesurer()
    except MontageImpossible as exc:
        print("INDISPONIBLE (montage, pas gisement) : %s" % exc)
        print("VERDICT: NON MESURE")
        return EX_NON_MESURE
    for a in info.get("anomalies", []):
        print("   anomalie de lecture : %s" % a)
    if rc == EX_NON_MESURE:
        print("   ledger sans aucune entree exploitable -> AUCUN VERDICT")
        print("VERDICT: NON MESURE")
        return EX_NON_MESURE

    print("-- etat du ledger")
    print("   entrees attestees : %d | perimetre offline derive : %d"
          % (info["entrees"], info["perimetre"]))
    # LE DENOMINATEUR D'ABORD (#547-r2) : sans lui, `entrees NON-VERT : 0` se lit << tout est vert >>
    # alors qu'il peut ne porter sur RIEN. Mesure du 2026-08-10 : 0 attestation VALABLE sur 290.
    print("   attestations VALABLES sur CET arbre : %d / %d   (foyer `ledger.raison_de_rejeu`)"
          % (len(info["valables"]), info["perimetre"]))
    print("   PAS MESURE ICI (vert d'un AUTRE arbre) : %d -- ni vert ni rouge, un TROU"
          % len(info["pas_mesure_ici"]))
    for cle, n in sorted(info["causes_pas_mesure"].items(), key=lambda kv: -kv[1]):
        print("      %-72s %d" % (cle[:72], n))
    mauvais = info["non_verts"]
    print("   entrees NON-VERT  : %d, dont %d NON DECLAREES (attendu 0)"
          % (len(mauvais), len(info["non_declares"])))
    for rel, ecrit, derive, bilan in mauvais:
        print("      [%s] %-78s ecrit=%s derive=%s %s"
              % ("declare" if rel in NON_VERTS_DECLARES else "NON DECLARE", rel, ecrit, derive,
                 {k: v for k, v in bilan.items() if v}))
    for rel in info["declarations_perimees"]:
        print("      [DECLARATION PERIMEE] %s -- ce fichier n'est plus non-VERT : retire sa ligne "
              "de `NON_VERTS_DECLARES`, sinon elle masquera son prochain rouge" % rel)
    p = info["portee"]
    print("-- PORTEE DE LA MESURE (ce que ce vert ne couvre PAS)")
    print("   fichiers offline SANS entree (jamais joues)     : %d" % len(p["sans_entree"]))
    for r in p["sans_entree"][:10]:
        print("      %s" % r)
    if len(p["sans_entree"]) > 10:
        print("      ... (%d de plus)" % (len(p["sans_entree"]) - 10))
    print("   attestations PERIMEES (blob du test change)     : %d" % len(p["attestation_perimee"]))
    for r in p["attestation_perimee"][:10]:
        print("      %s" % r)
    if len(p["attestation_perimee"]) > 10:
        print("      ... (%d de plus)" % (len(p["attestation_perimee"]) - 10))
    print("   fichiers `*_live.py`, HORS perimetre par choix  : %d" % p["hors_perimetre_live"])
    print("      (un test offline heberge dans un `_live.py` est invisible des DEUX gardes)")

    rc = rc or rc_mut
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
