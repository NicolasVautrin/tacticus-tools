"""#475 -- le cliquet `probe_475` MORD-il encore ?

Un cliquet dont le detecteur a cesse de mordre rend VERT sur un depot fautif (`probe_181`
avant #430). Ce test lui oppose, DURABLEMENT, les formes EXACTES retirees de
`bucket-audit.ts` et `modifier-observe.ts`, et les formes legitimes que la banque n'a PAS
le droit de faire rougir -- celles que le `CLAUDE.md` et la tache #475 nomment (masques de
bits, base ghidra d'affichage, codes d'exception, `POISON_OFFSET`, arithmetique 64 bits),
plus les DEUX que le premier passage du cliquet a fait rougir a tort (`r.base.add(offset)`
d'un `Memory.scan` et `lib.base.add(lib.size)` d'un test d'appartenance).

Il ne mute RIEN sur le disque : la banque tourne en parallele, et muter `frida/hooks/**`
serait #455 dans l'autre sens (un voisin lirait l'arbre pendant la mutation). Les detecteurs
sont des fonctions pures sur `(rel, source)` -- c'est ce qui rend ce test possible.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict
#: (#486-r15). Meme contrat que les cliquets de la banque (`declencheur_cliquet.py`).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a TOUT fichier de test : la cascade des deux `conftest.py` et sa
        # fermeture. Aucun test ne les IMPORTE -- c'est de la semantique pytest -- et ils
        # portent le `green_skip_guard` de #455 plus trois fixtures `autouse`, dont le
        # verdict de CHAQUE test depend. Liste EXPLICITE et non `scripts/python/*.py` : le
        # glob large retiendrait ce test a chaque modification d'un probe quelconque.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/enum_maps.py",
        "scripts/python/host_inputs.py", "scripts/python/rl_collect_batch.py",
        "scripts/python/stream_events.py", "scripts/python/symbols_layout.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER :
        "scripts/python/probe_475_pinned_addresses.py", "frida/hooks/**",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le probe sous test et les hooks TypeScript qu'il BALAIE a la recherche d'adresses "
              "epinglees. Une adresse en dur ajoutee dans `frida/hooks/**` doit rejouer ce test "
              ": c'est exactement le gisement qu'il garde.",
}

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[1]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_475_pinned_addresses as P  # noqa: E402


def _r1(src: str):
    code, nocom = P.blanchir(src)
    pins, incomplets = P.extraire_pins("<t>", src, nocom)
    return P.sites_r1("<t>", code, src, pins), incomplets


# Les formes EXACTES retirees par #475 -- si le cliquet cesse de les voir, il est mort.
RETIREES = [
    # modifier-observe : la SEULE des six qui etait encore armee.
    "const DISPATCH_HELPER_RVA = 0x1800267c0 - 0x180000000;\n"
    "const helper = il2cppBase.add(DISPATCH_HELPER_RVA);\n"
    "Interceptor.attach(helper, {});\n",
    # bucket-audit : les quatre constantes, dans leur forme ARMEE.
    "const RVA = { addAction: 0x13fbcc0, isValidAction: 0x13fc660 };\n"
    "Interceptor.attach(il2cppBase.add(RVA.addAction), {});\n",
    # modifier-observe : la constante morte, si quelqu'un la re-arme.
    "const CRIT_CTOR_RVA = 0x180fff850 - 0x180000000;\n"
    "Interceptor.attach(il2cppBase.add(CRIT_CTOR_RVA), {});\n",
    # scorer-damage-trace : la forme `rva(<VA>)` + `.add`.
    "const RVA_LEAF = 0x181212b60 - 0x180000000;\n"
    "const p = il2cppBase.add(RVA_LEAF);\n",
    # le deguisement par la RVA nue sur une autre base.
    "const p = mod.base.add(0x14eff60);\n",
    # re-deriver la base d'image a la main.
    'const b = Module.findBaseAddress("GameAssembly.dll");\n',
]

# Ce sur quoi le cliquet se ferait DESACTIVER s'il rougissait. Le critere central de #475.
LEGITIMES = [
    "const RULES = { ObscuredTerrainBrokenTargetingRule: 0x1000000 };",
    "const ghidra = 0x180000000 + m.ptr.sub(il2cppBase).toInt32();",
    'const GHIDRA_BASE = ptr("0x180000000");',
    "const fatal = (code === 0xC00000FD || code === 0xC0000005);",
    "const msvcCxx = (code === 0xE06D7363);",
    "const POISON_OFFSET = 0x40000000;",
    "return Number(BigInt(raw.toString())) / 4294967296;",
    "const off = bt[i].sub(il2cppBase);",
    "const base = r.base.add(offset);",
    "if (addr.compare(lib.base.add(lib.size)) < 0) { return 1; }",
    "const util = d8.add(0x20).readPointer();",
    "const func = klass.add(0x4d8).readPointer();",
    "// AddAction @1813fbcc0 -- mesure sur le build precedent",
    'log("hooked @ 0x181212640");',
]


def test_les_formes_retirees_rougissent():
    for src in RETIREES:
        sites, inc = _r1(src)
        assert sites or inc, "forme fautive NON vue par probe_475 :\n%s" % src


def test_les_formes_legitimes_ne_rougissent_pas():
    for src in LEGITIMES:
        sites, inc = _r1(src + "\n")
        assert not sites and not inc, "forme LEGITIME vue comme fautive : %r -> %s" % (src, sites)


def test_un_pin_declare_exempte_sa_VA():
    src = ('const P = { va: 0x181212640, build: "x", symbol: "A$$B", what: "c" };\n')
    sites, inc = _r1(src)
    assert not sites and not inc, sites or inc


def test_un_pin_incomplet_rougit():
    for src in ('const P = { va: 0x181212640, symbol: "A$$B" };\n',
                'const P = { va: 0x181212640, build: "x" };\n'):
        sites, inc = _r1(src)
        assert inc, "pin incomplet accepte : %s" % src


def test_la_confrontation_a_la_table_tranche_dans_les_deux_sens():
    class T:
        exact = {0x181212640: "Vrai$$Symbole", 0x181212000: "Autre$$Fn"}
        addrs = [0x181212000, 0x181212640]
        names = ["Autre$$Fn", "Vrai$$Symbole"]
        derniere = 0x181212640
        englobant = P.Table.englobant

    t = T()
    juste = P.Pin("<t>", 1, 0x181212640, "b", "Vrai$$Symbole", "code", (0, 0))
    assert P.confronter(juste, t) is None
    faux = P.Pin("<t>", 1, 0x181212640, "b", "Faux$$Symbole", "code", (0, 0))
    assert P.confronter(faux, t) is not None
    # Point INTERNE : le symbole doit se trouver a `va - offset`, pas a `va`.
    interne = P.Pin("<t>", 1, 0x181212648, "b", "Vrai$$Symbole+0x8", "code", (0, 0))
    assert P.confronter(interne, t) is None
    interne_faux = P.Pin("<t>", 1, 0x181212648, "b", "Vrai$$Symbole+0x9", "code", (0, 0))
    assert P.confronter(interne_faux, t) is not None
    # DONNEE : le symbole doit etre DAT_<va>, et la VA doit tomber HORS de la zone des fonctions.
    data_ok = P.Pin("<t>", 1, 0x183340000, "b", "DAT_183340000", "data", (0, 0))
    assert P.confronter(data_ok, t) is None
    data_dans_le_code = P.Pin("<t>", 1, 0x181212640, "b", "DAT_181212640", "data", (0, 0))
    assert P.confronter(data_dans_le_code, t) is not None


def test_l_auto_epreuve_du_probe_est_verte():
    assert P.self_test(verbose=False) == []


def test_le_perimetre_n_est_pas_vide():
    """Un balayage qui rend zero se lit comme 'rien a signaler' (#434/#440)."""
    rels = P.fichiers()
    assert len(rels) > 50, "perimetre suspect : %d fichier(s)" % len(rels)
    assert P.FOYER in rels, "le foyer est absent du depot -- R1 n'a plus de sens"

