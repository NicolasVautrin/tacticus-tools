"""GENERE `engine/runner/abilities/targeting_rule.py` depuis la table de symboles.

Mirror 1:1 de `IdunBattle.Core.Services.TargetingRule` (enum de FLAGS 64 bits), lu dans
`data/symbols/<build>/frida/enums.tsv`.

POURQUOI GENERER PLUTOT QU'ECRIRE
---------------------------------
Les masques du registre etaient des litteraux hexadecimaux (`rules=0x200240000400`) : illisibles,
donc non relisibles en revue -- un bit faux y passe sans laisser de trace. Les nommer suppose une
table nom<->bit, et cette table doit venir de la SOURCE, pas d'une transcription : c'est
exactement la faute que le dumper 32 bits avait rendue inevitable (il perdait les 27 membres
au-dessus du bit 31, ce qui a force a nommer des bits a la main, dont un a l'envers).

Regenerer apres chaque re-dump :
    python scripts/python/gen_targeting_rule.py

`probe_targeting_rule_bits.py` garde la coherence module <-> dump et ECHOUE si elle se rompt.

Sortie ASCII only (console Windows cp1252).
"""
import keyword
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENUM = "IdunBattle.Core.Services.TargetingRule"
OUT = REPO / "scripts" / "python" / "engine" / "runner" / "abilities" / "targeting_rule.py"

ENTETE = '''"""Mirror 1:1 de `IdunBattle.Core.Services.TargetingRule` -- GENERE, ne pas editer a la main.

Les regles de ciblage natives sont un enum de FLAGS **64 bits**, lu a `TargetingOptions+0x28` et
consomme par `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (cascade 7-args).
Chaque membre est un bit ; quelques-uns sont des COMPOSITES (plusieurs bits), conserves tels quels
parce que le natif les declare.

Produit par `scripts/python/gen_targeting_rule.py` depuis
`data/symbols/{build}/frida/enums.tsv`. Regenerer apres chaque re-dump ; la coherence
module <-> dump est gardee par `scripts/python/probe_targeting_rule_bits.py`.

`IntFlag` et non `IntEnum` : un masque est une COMBINAISON, et `rules & TargetingRule.TargetIsEnemy`
doit rester un test d'entier -- les consommateurs existants comparent des ints, rien a changer chez
eux.
"""
from __future__ import annotations

from enum import IntFlag


class TargetingRule(IntFlag):
'''


def build_hash() -> str:
    """Le build QUI FAIT FOI (`data/symbols/CURRENT`), via `symbols_layout`.

    ⚠ Cette fonction lisait `sorted(glob("*/BUILD"))[0]`, c'est-a-dire le PREMIER build par
    ordre ALPHABETIQUE -- donc un build ARCHIVE des qu'un hash trie avant le courant. Mesure du
    2026-08-01 : `CURRENT` = `rnca9r7q6c`, et cette fonction rendait `gqfc5mff6c`. Les deux
    dumps declaraient le meme enum, donc le mirror etait juste PAR CHANCE et rien ne le
    signalait -- et `probe_targeting_rule_bits.py`, qui devait garder la coherence, lisait LE
    MEME mauvais build : deux lecteurs qui partagent une entree perimee s'accordent toujours.
    Garde depuis #429 : `tests/engine/runner/test_targeting_rule_inventory.py::
    test_mirror_couvre_le_dump_du_build_courant` (mirror <-> dump du build courant)."""
    import symbols_layout
    return symbols_layout.current_build()


def _identifiant(nom: str) -> str:
    """Nom C# -> identifiant Python. Le natif declare un membre `None`, qui est un MOT-CLE
    Python : sans cette conversion le module genere ne s'importe meme pas. On suffixe d'un `_`
    plutot que de renommer, et la ligne generee garde le nom natif en commentaire -- le grep
    code <-> table doit rester immediat."""
    return nom + "_" if keyword.iskeyword(nom) or not nom.isidentifier() else nom


def membres(build: str) -> list:
    """[(nom, valeur)] dans l'ordre du dump, valeurs exactes."""
    p = REPO / "data" / "symbols" / build / "frida" / "enums.tsv"
    for ln in p.open(encoding="utf-8"):
        if ln.startswith(ENUM + "\t"):
            out = []
            for kv in ln.rstrip("\n").split("\t", 1)[1].split(","):
                raw, nom = kv.split("=", 1)
                out.append((nom, int(raw)))
            return out
    raise RuntimeError(f"{ENUM} absent de {p}")


def main() -> int:
    build = build_hash()
    ms = membres(build)
    # Ordre de valeur : un lecteur cherche un bit, pas un nom de declaration.
    ms.sort(key=lambda nv: (nv[1] < 0, abs(nv[1])))

    lignes = [ENTETE.format(build=build)]
    for nom, val in ms:
        py = _identifiant(nom)
        if val > 0 and not (val & (val - 1)):
            corps = "    %-42s = 1 << %d" % (py, val.bit_length() - 1)
        else:
            # composite (plusieurs bits), zero, ou negatif : valeur brute
            corps = "    %-42s = %#x" % (py, val)
        if py != nom:
            corps += "   # natif : %s" % nom
        lignes.append(corps.rstrip() + "\n")

    OUT.write_text("".join(lignes), encoding="utf-8")
    simples = sum(1 for _n, v in ms if v > 0 and not (v & (v - 1)))
    print("ecrit %s" % OUT.relative_to(REPO))
    print("  build=%s  %d membres dont %d bits simples" % (build, len(ms), simples))
    return 0


if __name__ == "__main__":
    sys.exit(main())
