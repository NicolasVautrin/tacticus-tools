"""GARDE #242 (OFFLINE PUR) -- le cap `vtbl+0x228` de `FabricatorClawArrayPlaybook` AU BINAIRE.

CE QU'ELLE PROTEGE, ET POURQUOI ELLE EXISTE. La constante `MAX_ADJACENT_FRIENDS = 1` du port ne
repose pas sur un fit : elle mirror un getter dont le corps est `mov eax,1 ; ret`. Ce corps est
TRIVIAL, donc FONDU par l'ICF avec des milliers d'autres -- il n'a **aucun symbole propre** et
`search_symbols_by_name` ne peut pas le montrer (le faux negatif que documente le CLAUDE.md,
« l'ABSENCE d'une methode dans les tables ne prouve RIEN »). La seule lecture possible est le bloc
`methodPointers` du PE, ou les methodes d'un type sont CONTIGUES dans l'ordre des slots.

Cette garde rejoue cette lecture a chaque passe, et elle est **build-agnostique** : elle part de
`data/symbols/CURRENT`, resout les symboles par la table VERSIONNEE de ce build, et lit le PE du
build correspondant. Aucune VA n'est ecrite ici. Si un futur build reorganise ce bloc -- ou si le
getter cesse de rendre 1 -- elle rougit, au lieu de laisser la constante devenir une fausse verite
invalidable (le port continuerait a rendre 30 sans que rien ne signale l'ecart).

CE QU'ELLE NE COUVRE PAS. La position dans le bloc ne distingue pas a elle seule `vtbl+0x228` (cap
AMIS) de `vtbl+0x238` (cap ENNEMIS) : c'est la mesure live de `case-242` par.5.1 (`X_nat` PLAT a 30
pour `nRep` = 1, 2, 3) qui l'a tranche, plus le fait que la face ennemis n'est pas surchargee (le
`<ret 0>` du slot precedent) et rendrait donc 0. Cette garde verifie la STRUCTURE, pas la semantique
du slot.

Complement live : `test_fabricator_claw_cap_live.py` (loi du port sur une bataille reelle).
ASCII only.
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

ROOT = Path(__file__).resolve().parents[4]
GAMES = Path(r"C:\Users\nicolasv\AppData\Local\tacticus\games")

# Les deux corps que l'ICF a fondus, tels qu'ils sont ecrits dans le PE.
RET_0 = bytes.fromhex("33c0c3")            # xor eax,eax ; ret
RET_1 = bytes.fromhex("b801000000c3")      # mov eax,1   ; ret

# Le groupe attendu, dans l'ordre des slots : `.ctor`, `GetAdjacentFriendUtility` (vtbl+0x208),
# la face ENNEMIS non surchargee (vtbl+0x218 -> ret 0), le CAP (vtbl+0x228 -> ret 1), puis
# `FilterAdjacentFriends` (vtbl+0x248). Les DEUX seules classes du module qui surchargent aussi le
# filtre portent ce groupe -- c'est la correlation, pas une lecture isolee, qui identifie le slot.
CLASSES = ["IdunBattle.AI.Playbook.Loki.FabricatorClawArrayPlaybook",
           "IdunBattle.AI.Playbook.Loki.SpiritualLeaderPlaybook"]
MEMBERS = [".ctor", "GetAdjacentFriendUtility", "FilterAdjacentFriends"]


def _build_hash() -> str:
    p = ROOT / "data" / "symbols" / "CURRENT"
    if not p.exists():
        pytest.skip("data/symbols/CURRENT absent")
    return p.read_text(encoding="utf-8").strip()


def _symbols(build: str) -> dict:
    """`<symbole>` -> VA, depuis la table VERSIONNEE du build (aucune VA en dur ici)."""
    tsv = ROOT / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    if not tsv.exists():
        pytest.skip("table de symboles absente pour le build %s" % build)
    wanted = {"%s$$%s" % (c, m) for c in CLASSES for m in MEMBERS}
    out = {}
    for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1] in wanted:
            out[parts[1]] = int(parts[0], 16)
    return out


def _pe(build: str):
    """(buffer, image_base, [(rva, size, file_off)]) du `GameAssembly.dll` de CE build."""
    dll = GAMES / build / "GameAssembly.dll"
    if not dll.exists():
        pytest.skip("GameAssembly.dll absent pour le build %s" % build)
    buf = dll.read_bytes()
    pe = struct.unpack_from("<I", buf, 0x3C)[0]
    nsec = struct.unpack_from("<H", buf, pe + 6)[0]
    opt_size = struct.unpack_from("<H", buf, pe + 20)[0]
    opt = pe + 24
    assert struct.unpack_from("<H", buf, opt)[0] == 0x20B, "PE32+ attendu"
    image_base = struct.unpack_from("<Q", buf, opt + 24)[0]
    secs = []
    for i in range(nsec):
        s = opt + opt_size + i * 40
        vsize, vaddr, rawsize, rawoff = struct.unpack_from("<IIII", buf, s + 8)
        secs.append((vaddr, max(vsize, rawsize), rawoff))
    return buf, image_base, secs


def _va_to_off(va: int, image_base: int, secs) -> int:
    rva = va - image_base
    for vaddr, size, rawoff in secs:
        if vaddr <= rva < vaddr + size:
            return rawoff + (rva - vaddr)
    raise AssertionError("VA %#x hors des sections du PE" % va)


def _ptr_offsets(buf: bytes, va: int) -> list:
    """Offsets FICHIER (alignes 8) ou le qword `va` apparait -- la table `methodPointers` l'est."""
    pat = struct.pack("<Q", va)
    out, i = [], buf.find(pat)
    while i != -1:
        if i % 8 == 0:
            out.append(i)
        i = buf.find(pat, i + 1)
    return out


@pytest.fixture(scope="module")
def blocks():
    """{classe: [qword, ...]} -- les 5 entrees du groupe `methodPointers`, par classe."""
    build = _build_hash()
    syms = _symbols(build)
    buf, image_base, secs = _pe(build)
    out = {"_pe": (buf, image_base, secs), "_build": build}
    for cls in CLASSES:
        ctor = syms.get("%s$$.ctor" % cls)
        assert ctor is not None, (
            "`%s$$.ctor` absent de la table du build %s -- la classe a-t-elle disparu, ou la table "
            "est-elle a regenerer ?" % (cls, build))
        offs = _ptr_offsets(buf, ctor)
        assert len(offs) == 1, (
            "`%s$$.ctor` apparait %d fois dans le PE (attendu 1) : le bloc `methodPointers` n'est "
            "plus identifiable sans ambiguite" % (cls, len(offs)))
        base = offs[0]
        out[cls] = {"base": base,
                    "qwords": [struct.unpack_from("<Q", buf, base + k * 8)[0] for k in range(5)],
                    "syms": syms}
    return out


@pytest.mark.parametrize("cls", CLASSES)
def test_group_layout_is_the_expected_five_slots(blocks, cls):
    """Le groupe commence par `.ctor`, puis `GetAdjacentFriendUtility`, et finit par le FILTRE.

    Ce sont les trois seules entrees NOMMEES : elles bornent le groupe. Les deux du milieu (+0x10 et
    +0x18) sont les corps fondus, verifies par le test suivant."""
    q = blocks[cls]["qwords"]
    syms = blocks[cls]["syms"]
    assert q[0] == syms["%s$$.ctor" % cls], "slot +0x00 != .ctor"
    assert q[1] == syms["%s$$GetAdjacentFriendUtility" % cls], (
        "slot +0x08 != GetAdjacentFriendUtility (vtbl+0x208) -- l'ordre du bloc a change")
    assert q[4] == syms["%s$$FilterAdjacentFriends" % cls], (
        "slot +0x20 != FilterAdjacentFriends (vtbl+0x248) -- deux entrees seulement devraient "
        "s'intercaler entre l'accesseur de poids et le filtre ; bloc lu = %r" % [hex(x) for x in q])


@pytest.mark.parametrize("cls", CLASSES)
def test_the_intercalated_bodies_are_ret0_then_ret1(blocks, cls):
    """LE COEUR DE LA GARDE : entre l'accesseur de poids et le filtre, `<ret 0>` PUIS `<ret 1>`.

    `<ret 1>` est le getter du cap (`vtbl+0x228`) : c'est LUI qui justifie
    `MAX_ADJACENT_FRIENDS = 1`. S'il devenait `<ret 0>` -- ou disparaissait -- le port sommerait a
    tort (30 x n) ou rendrait 0."""
    buf, image_base, secs = blocks["_pe"]
    q = blocks[cls]["qwords"]
    b0 = buf[_va_to_off(q[2], image_base, secs):][:len(RET_0)]
    b1 = buf[_va_to_off(q[3], image_base, secs):][:len(RET_1)]
    assert b0 == RET_0, (
        "slot +0x10 de %s : corps %s, attendu %s (`xor eax,eax ; ret` -- la face ENNEMIS non "
        "surchargee)" % (cls, b0.hex(), RET_0.hex()))
    assert b1 == RET_1, (
        "slot +0x18 de %s : corps %s, attendu %s (`mov eax,1 ; ret` = le CAP `vtbl+0x228` a 1). "
        "Si ce corps a change, `MAX_ADJACENT_FRIENDS` du port n'a plus de source -- RE-LIRE le bloc "
        "avant de toucher a la constante." % (cls, b1.hex(), RET_1.hex()))


def test_both_carriers_share_the_very_same_folded_bodies(blocks):
    """CORROBORATION CROISEE : les deux classes pointent sur les MEMES adresses de corps fondus.

    C'est ce qui rend la lecture non-accidentelle -- `SpiritualLeaderPlaybook` a son cap MESURE live
    (`case-212` par.6 : `X_nat` plat a 30 pour 1, 2 ET 3 decoys). Partager le corps a l'octet ET a
    l'adresse pres, a la meme position relative, est ce qui transporte cette mesure sur 1006."""
    a = blocks[CLASSES[0]]["qwords"]
    b = blocks[CLASSES[1]]["qwords"]
    assert (a[2], a[3]) == (b[2], b[3]), (
        "les deux playbooks n'intercalent plus les MEMES corps fondus : %r vs %r -- la "
        "correlation qui identifie le slot du cap est rompue"
        % ([hex(x) for x in a[2:4]], [hex(x) for x in b[2:4]]))
