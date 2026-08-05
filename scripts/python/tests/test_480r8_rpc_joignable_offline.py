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
from pathlib import Path

import pytest

ICI = Path(__file__).resolve()
SCRIPTS_PY = ICI.parents[1]
PROBE = SCRIPTS_PY / "probe_480r8_rpc_ventilation.py"

sys.path.insert(0, str(SCRIPTS_PY))


def test_etage1_tout_rpc_porte_un_canal_nominatif() -> None:
    """Aucun RPC declare ne doit etre injoignable (rc 0 du mode `--cliquet`)."""
    assert PROBE.is_file(), "probe #480-r8 absent : %s" % PROBE
    r = subprocess.run([sys.executable, str(PROBE), "--cliquet"],
                       cwd=str(SCRIPTS_PY), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode == 2:
        pytest.fail("CAPTEUR casse (rc 2) -- ce n'est pas le depot qui est en cause :\n"
                    + r.stdout[-3000:])
    assert r.returncode == 0, (
        "des RPC sont exposes sans etre joignables. Les cabler, ou les NOMMER dans une doc "
        "du depot (`--catalogue` produit le bloc pour `rpc-api.md`), ou les retirer.\n"
        + r.stdout[-4000:])


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
    assert exec_idx.get("warmupGameSingletons"), (
        "le corpus executable ne voit pas `warmupGameSingletons`, pourtant appele par le host")
    assert doc_idx.get("dumpComps"), (
        "le corpus doc ne voit pas `dumpComps`, pourtant nomme dans `rpc-api.md`")

    # Et il doit savoir dire NON : un nom qui n'existe pas ne doit etre trouve nulle part.
    invente = "qqNomQuiNExistePas9f3a"
    assert invente not in doc_idx and invente not in exec_idx, (
        "le corpus rend un nom INVENTE : le capteur ne discrimine pas")
