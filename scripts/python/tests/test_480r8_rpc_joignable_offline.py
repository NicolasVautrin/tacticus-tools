"""Cliquet #480-r8 -- tout RPC expose doit etre JOIGNABLE.

L'INVARIANT
-----------
Pour invoquer `{"method": "<nom>"}` il faut CONNAITRE le nom, donc l'avoir lu quelque part.
Un RPC dont le nom n'est ecrit nulle part hors de son fichier declarant n'est donc pas
« disponible au cas ou » : il est hors d'atteinte de fait. #480-r6 avait mesure que 155 des
321 RPC n'ont aucun appelant statique ; #480-r8 a ventile ces 155 et trouve que 83 d'entre eux
n'etaient mentionnes NI dans du code, NI dans une doc, NI dans un message de commit.

Le critere est DERIVE du corpus (tout fichier versionne, groupe deduit du chemin), jamais une
liste de noms -- il mord au 156e RPC comme au 1er.

CE QUE LE CLIQUET N'ACCEPTE PAS COMME PREUVE, ET POURQUOI
---------------------------------------------------------
  * **C5 (un frere du meme module est cable)** : mesure par mutation le 2026-08-05, un
    `ctx.rpc.<neuf>` ajoute dans `status.ts` laissait le cliquet VERT, parce que ses freres
    ont un appelant. C5 aurait donc cesse de mordre exactement sur le gisement vise -- notre
    propre cadence d'ajout. Il reste un canal de TRI, jamais une preuve.
  * **C0 (`hooks-legacy/`)** : le CLAUDE.md pose que rien de vivant n'en depend. Un nom qui
    n'existe QUE dans l'archive n'est pas joignable, il est archive.

ETAGE 2 -- pourquoi il existe
------------------------------
Un cliquet qui interroge un corpus VIDE rend vert sans rien avoir regarde. L'etage 2 exige donc
que le corpus DISCRIMINE : un RPC reellement documente doit y etre trouve, et un nom invente
doit y etre absent. Sans lui, le vert de l'etage 1 ne prouverait rien.

Offline pur : aucun runner, aucun RPC live, aucun reinject.
"""
from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ICI = Path(__file__).resolve()
SCRIPTS_PY = ICI.parents[1]
PROBE = SCRIPTS_PY / "probe_480r8_rpc_ventilation.py"

sys.path.insert(0, str(SCRIPTS_PY))


def test_etage1_tout_rpc_porte_un_canal_nominatif(capsys) -> None:
    """Aucun RPC declare ne doit etre injoignable (rc 0 du mode `--cliquet`).

    IN-PROCESS depuis #941-r2, et le sous-process qu'il remplace n'etait pas gratuit : ce fichier
    lisait le depot DEUX FOIS, une fois de chaque cote d'une frontiere de process qu'aucun memo
    ne traverse -- 51,6 s ici, 18,6 s a l'etage 2, mesures le 2026-08-11. Les trois lectures
    (`recenser_rpc`, `corpus_executable`, `corpus_doc`) sont desormais memoisees DANS le probe,
    ce qui ne vaut que si les deux etages partagent le process.

    CE QUI EST PERDU, ET CE QUI LE REMPLACE. Le sous-process exercait AUSSI l'entree script.
    `probe_480r8` n'est PAS une entree de `scripts/ratchets.ps1` (verifie) : ce fichier est le
    seul a la jouer, donc la laisser tomber en silence l'aurait rendue non couverte. Le test
    suivant la garde pour 0,3 s au lieu de 51.
    """
    assert PROBE.is_file(), "probe #480-r8 absent : %s" % PROBE
    import probe_480r8_rpc_ventilation as p

    rc = p.main(["--cliquet"])
    sortie = capsys.readouterr().out
    if rc == 2:
        pytest.fail("CAPTEUR casse (rc 2) -- ce n'est pas le depot qui est en cause :\n"
                    + sortie[-3000:])
    assert rc == 0, (
        "des RPC sont exposes sans etre joignables. Les cabler, ou les NOMMER dans une doc "
        "du depot (`--catalogue` produit le bloc pour `rpc-api.md`), ou les retirer.\n"
        + sortie[-4000:])


def test_le_probe_reste_LANCABLE_en_ligne_de_commande() -> None:
    """Ce que l'etage 1 n'exerce plus depuis qu'il tourne in-process : l'entree script.

    `--help` traverse le chemin complet -- imports au niveau module, `__name__ == "__main__"`,
    construction d'`argparse` -- sans payer un seul balayage du depot. Le CORPS de `main` est,
    lui, exerce par l'etage 1. C'est le partage exact : ici la coquille, la-bas le contenu.
    """
    r = subprocess.run([sys.executable, str(PROBE), "--help"],
                       cwd=str(SCRIPTS_PY), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    assert "--cliquet" in r.stdout, "le mode que l'etage 1 exerce n'est plus expose en CLI"


def test_etage2_le_corpus_discrimine() -> None:
    """Le vert de l'etage 1 doit venir d'un corpus qui VOIT, pas d'un corpus vide."""
    import probe_480r8_rpc_ventilation as p

    decl, _ = p.recenser_rpc()
    assert len(decl) >= p.PLANCHER_RPC, (
        "recensement sous le plancher (%d) : capteur casse" % p.PLANCHER_RPC)

    cexec = p.corpus_executable()
    cdoc = p.corpus_doc()
    assert len(cexec) >= p.PLANCHER_CORPUS, "corpus executable trop maigre : %d" % len(cexec)
    assert cdoc, "corpus doc VIDE -- le canal C3 ne verrait rien"

    doc_idx = p.index_inverse(cdoc, quote_seulement=False)
    exec_idx = p.index_inverse(cexec, quote_seulement=True)

    # Non-vide DIRIGE : un RPC reellement cable cote host doit se voir dans le corpus
    # executable, et un RPC de diagnostic reellement documente doit se voir dans la doc.
    assert exec_idx.get("autoBootExtraire"), (
        "le corpus executable ne voit pas `autoBootExtraire`, pourtant appele par le host")
    assert doc_idx.get("dumpComps"), (
        "le corpus doc ne voit pas `dumpComps`, pourtant nomme dans `rpc-api.md`")

    # Et il doit savoir dire NON : un nom qui n'existe pas ne doit etre trouve nulle part.
    # ⚠ Le temoin est TIRE AU HASARD, jamais ecrit en litteral : ce fichier est un `.py`
    # VERSIONNE, donc il appartient lui-meme au corpus qu'il interroge. Mesure du 2026-08-05 --
    # un temoin ecrit en dur passait au vert tant que le test n'etait pas commite, puis
    # ECHOUAIT des qu'il entrait dans `git ls-files`, en s'accusant lui-meme. Un controle qui
    # contamine son propre corpus finit par rougir sur son artefact, pas sur son sujet.
    invente = "rpcTemoinAbsent" + uuid.uuid4().hex
    assert invente not in doc_idx and invente not in exec_idx, (
        "le corpus rend un nom INVENTE : le capteur ne discrimine pas")
