"""GARDE du contrat d'enum : largeur reelle + keyage par NOM.

CE QUE CA MESURE
----------------
`scripts/frida/dump-il2cpp-full.js` lisait la valeur de chaque literal d'enum avec
`readS32()`, INCONDITIONNELLEMENT, et rangeait le resultat dans un dictionnaire keye
PAR VALEUR. Sur un enum adosse a `long` — les enums de FLAGS un peu fournis — tout
membre au-dessus du bit 31 a ses 32 bits de poids faible NULS : il tronquait vers 0, et
les membres hauts s'ecrasaient donc les uns les autres.

Mesure sur `IdunBattle.Core.Services.TargetingRule` (build gqfc5mff6c) : sur les douze
membres au-dessus du bit 31, UN SEUL survivait — `TargetIsCasterOrEnemy`, range sous la
cle "0" parce qu'il etait le dernier ecrit. C'est ce qui a oblige a renommer a la main,
au decompile, les bits des masques de ciblage.

Le fix a deux volets, et ce probe garde les deux :
  1. lecture a la LARGEUR reelle (type sous-jacent, porte par le champ `value__`) ;
  2. keyage par NOM cote dump — les noms sont uniques en C#, les valeurs non (alias,
     composites de flags). Le TSV, lui, garde sa forme historique `valeur=nom` : son
     diff inter-build est un rapport de changement, qu'un changement de format rendrait
     illisible une fois.

L'enum d'entree est SYNTHETIQUE : le probe teste le contrat de bout en bout (emission
TSV -> relecture -> generateur Java) sans exiger de session live ni de re-dump.

Sortie ASCII only (console Windows cp1252).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gen_battle_config_java as g

# Reproduit exactement le cas mesure : deux membres au-dessus du bit 31 (tous deux
# tronques vers 0 avant le fix, donc s'ecrasant), un negatif au bit 31, un composite,
# et un alias de valeur.
EVALS = {
    "ValidRequest": "1",
    "TargetIsEnemy": "16384",
    "CasterHasCompletedOneTurn": "-2147483648",     # bit 31, signe
    "TargetIsInRange": "134217728",
    "AllowObscuredTarget": "100663296",             # composite 0x2000000|0x4000000
    "TargetIsCasterOrEnemy": "144115188075855872",  # bit 57 -- perdu avant le fix
    "HasSteppableUnit": "2251799813685248",         # bit 51 -- perdu avant le fix
    "AliasOfValidRequest": "1",                     # meme valeur qu'un autre membre
}


def check_tsv_emission() -> str:
    """Mirror de l'emission de `preprocess_il2cpp_dump.py` : nom -> valeur devient
    `valeur=nom`, SANS perdre de membre."""
    v_str = ",".join(f"{v}={n}" for n, v in EVALS.items())
    assert "144115188075855872=TargetIsCasterOrEnemy" in v_str, v_str
    assert "2251799813685248=HasSteppableUnit" in v_str, v_str
    assert "1=AliasOfValidRequest" in v_str, "l'alias doit SURVIVRE (keye par nom en amont)"
    assert v_str.count("=") == len(EVALS)
    print("OK tsv: %d membres emis, dont les 2 au-dessus du bit 31 et l'alias" % len(EVALS))
    return v_str


def check_readback(v_str: str) -> None:
    """Mirror du parseur de `catalog_inject.enum_map` : `valeur=nom` -> {nom: valeur}."""
    back = {}
    for kv in v_str.split(","):
        k, v = kv.split("=", 1)
        back[v] = int(k)
    assert back["TargetIsCasterOrEnemy"] == 1 << 57
    assert back["HasSteppableUnit"] == 1 << 51
    assert back["CasterHasCompletedOneTurn"] == -(1 << 31)
    assert len(back) == len(EVALS)
    print("OK relecture: %d membres, bit57=%d bit51=%d" % (len(back), 1 << 57, 1 << 51))


def check_java_backing() -> None:
    """Un enum 64 bits deborde `int` : le backing Java doit suivre la largeur reelle."""
    g.ENUM_STRING_SERIALIZED = set()

    src = g.emit_enum("IdunBattle.Core.Services.TargetingRule", EVALS)
    assert "private final long value;" in src, src[:400]
    assert "TargetIsCasterOrEnemy(144115188075855872L)" in src, src
    assert "n.longValue()" in src
    assert "@JsonValue public long value()" in src
    print("OK java 64 bits: backing long, litteral suffixe L")

    narrow = {"None": "0", "A": "1", "B": "2"}
    src32 = g.emit_enum("Some.Narrow", narrow)
    assert "private final int value;" in src32
    assert "A(1)," in src32 and "A(1L)" not in src32
    assert "n.intValue()" in src32
    print("OK java 32 bits: backing int inchange")


def main() -> int:
    check_readback(check_tsv_emission())
    check_java_backing()
    print("TOUT OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
