"""GARDE #218 -- `AmuletOfTheVoidwyrmPlaybook` n'override PAS `CalculateCustomUtility`.

CE QUE CETTE GARDE PROTEGE. La tranche 3 de `case-27` avait conclu que
`IdunBattle.AI.Playbook.Loki.AmuletOfTheVoidwyrmPlaybook` overridait
`CalculateCustomUtility` en PARTAGEANT le corps de
`IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$CalculateCustomUtility` (dedup IL2CPP),
et l'avait inscrit comme 28e classe overridante / 10e residu a porter. **C'etait un FAUX
POSITIF de lecture HORS VTABLE.** `resolveVtableSlot` lit `klass+off` en aveugle -- il n'a
pas acces a `vtable_count` -- et le balayage large (0x108..0x808) de la tranche 3 debordait
sur l'`Il2CppClass` SUIVANTE, contigue en memoire.

Deux gardes INDEPENDANTES, l'une offline (structure), l'autre live (contre-epreuve du fix) :

1. STRUCTURE (offline, `data/symbols/<build>/frida/classes.tsv`, indexee par NOM).
   `CalculateCustomUtility` est un virtuel de `IdunBattle.AI.Playbook.ComparablePlaybook`1`.
   `AmuletOfTheVoidwyrmPlaybook` derive de `IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1`,
   fille directe de `System.Object` : branche DISJOINTE, la methode n'est ni heritee ni
   overridable. C'est une preuve POSITIVE de structure, pas une absence dans une table.

2. BORNAGE DU SWEEP (live). `probe_27_custom_utility_inventory.sweep_vtable` borne desormais
   le balayage a la vtable PROPRE. La contre-epreuve exerce les DEUX regimes sur la meme
   classe : le balayage non borne (celui de la tranche 3) trouve un `CalculateCustomUtility`,
   le balayage borne n'en trouve aucun.

ASCII only.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "scripts" / "python"))

NS = "IdunBattle.AI.Playbook.Loki"
SUBJECT = "AmuletOfTheVoidwyrmPlaybook"
NEIGHBOUR = "PlasmaGrenadePlaybook"
DECLARING = "IdunBattle.AI.Playbook.ComparablePlaybook`1"


def _classes_tsv() -> Path:
    """Table de classes du build QUI FAIT FOI -- designe par `data/symbols/CURRENT`.

    #254 : exiger un repertoire UNIQUE sous `data/symbols/` cassait des qu'une MAJ laisse l'ancien
    build a cote du neuf, alors qu'on le conserve EXPRES (son diff est le rapport de changement du
    jeu). Meme correction que `catalog_inject._build_hash` : passer par `symbols_layout`."""
    from symbols_layout import current_build
    p = REPO / "data" / "symbols" / current_build() / "frida" / "classes.tsv"
    assert p.exists(), "table de classes absente pour le build courant : %s" % p
    return p


def _parents() -> dict:
    out = {}
    with io.open(_classes_tsv(), encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3:
                out[c[0]] = c[2]
    return out


def _chain(parents: dict, name: str, depth: int = 16) -> list:
    out = [name]
    while depth and parents.get(name) and parents[name] != name:
        name = parents[name]
        out.append(name)
        depth -= 1
    return out


def test_amulet_playbook_is_outside_the_comparable_branch():
    """Pilier structurel : la methode ne peut pas etre overridee depuis cette branche."""
    parents = _parents()
    subj = "%s.%s" % (NS, SUBJECT)
    neigh = "%s.%s" % (NS, NEIGHBOUR)
    assert subj in parents, "%s absente de classes.tsv" % subj
    subj_chain = _chain(parents, subj)
    neigh_chain = _chain(parents, neigh)

    # Le VOISIN, lui, est bien un ComparablePlaybook -- c'est ce qui rend son corps
    # `CalculateCustomUtility` legitime, et le debordement credible.
    assert DECLARING in neigh_chain, (
        "%s devrait deriver de %s ; chaine=%r" % (NEIGHBOUR, DECLARING, neigh_chain))

    assert DECLARING not in subj_chain, (
        "%s descend de %s -- si c'est VRAI, le verdict #218 (pas d'override) tombe et il "
        "faut re-derouler le RE ; chaine=%r" % (SUBJECT, DECLARING, subj_chain))
    assert subj_chain[1] == "IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1", (
        "base de %s changee : %r" % (SUBJECT, subj_chain))


def _session_or_skip():
    try:
        import probe_27_custom_utility_inventory as INV
    except Exception as exc:  # noqa: BLE001
        pytest.skip("inventaire #27 non importable: %s" % exc)
    try:
        sid = INV._session_id()
    except Exception as exc:  # noqa: BLE001
        pytest.skip("pas de session Frida: %s" % exc)
    return INV, sid


@pytest.mark.skipif(os.environ.get("TACTICUS_NO_LIVE") == "1", reason="live desactive")
def test_bounded_sweep_rejects_the_neighbour_class():
    """Contre-epreuve du fix : non borne -> faux positif ; borne -> aucun hit."""
    INV, sid = _session_or_skip()

    # --- regime BORNE (le fix) : la vtable PROPRE de la classe.
    rows = INV.sweep_vtable(sid, [(NS, SUBJECT)])
    _ns, _cls, rva, off, status = rows[0]
    assert status in ("no-slot", "vtable-uninit"), (
        "sweep BORNE rend un slot CalculateCustomUtility sur %s (off=%s rva=%r) -- "
        "le verdict #218 tombe" % (SUBJECT, off, rva))

    # --- regime NON BORNE (celui de la tranche 3) : reproduit tel quel.
    res = INV.rpc(sid, "resolveVtableSlot",
                  [{"ns": NS, "cls": SUBJECT, "start": 0x108, "end": 0x808}])
    assert res and res.get("ok"), "resolveVtableSlot KO: %r" % (res,)
    hits = [s for s in res["slots"] if s.get("method") == "CalculateCustomUtility"]
    if not hits:
        pytest.skip(
            "le balayage NON BORNE ne deborde plus sur une vtable porteuse (agencement "
            "memoire different de la session de mesure) -- le fix reste juste, la "
            "contre-epreuve n'est simplement plus exercable ici")

    # Le hit du regime non borne est le VRAI slot du VOISIN, decale du delta d'adresse
    # entre les deux Il2CppClass.
    k_subj = int(res["klass"], 16)
    res_n = INV.rpc(sid, "resolveVtableSlot",
                    [{"ns": NS, "cls": NEIGHBOUR, "start": 0x108, "end": 0x808}])
    k_neigh = int(res_n["klass"], 16)
    own = []
    for s in res_n["slots"]:
        if int(s["off"], 0) < 0x138:
            continue
        if not s.get("method") or not s.get("funcRVA"):
            break
        own.append(s)
    neigh_hit = [s for s in own if s.get("method") == "CalculateCustomUtility"]
    assert len(neigh_hit) == 1, "%s devrait porter 1 CalculateCustomUtility" % NEIGHBOUR

    delta = k_neigh - k_subj
    off_seen = int(hits[0]["off"], 0)
    off_real = int(neigh_hit[0]["off"], 0)
    assert off_seen - off_real == delta, (
        "le hit non borne (+0x%x) n'est pas le slot +0x%x du voisin decale de 0x%x : "
        "le debordement n'est PAS l'explication, re-ouvrir le RE"
        % (off_seen, off_real, delta))
    assert int(hits[0]["funcRVA"], 16) == int(neigh_hit[0]["funcRVA"], 16)
