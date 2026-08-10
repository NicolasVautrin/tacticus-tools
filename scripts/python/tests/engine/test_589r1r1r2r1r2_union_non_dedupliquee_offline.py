"""`#589-r1-r1-r2-r1-r2` -- l'union du compteur ne dedoublonne PAS : le CLIQUET de reouverture.

Le natif, LU :

    // IdunBattle.Entities.Effects.Loki.AmuletOfTheVoidwyrm_CritDamageReductionEffect
    //   $$GetAdjacentFriendlySummonsAndDecoysCount
    Count( UnitsWithTrait(AdjacentFriends(Owner, unique: 1, selectionType: 3), 0x2   = Summon)
           op_Addition
           UnitsWithTrait(AdjacentFriends(Owner, unique: 1, selectionType: 3), 0x41d = Decoy) )

`IdunBattle.DSL.TargetsSelector$$op_Addition` construit un `CombinedSelector` de mode **1**, et
`IdunBattle.DSL.CombinedSelector$$SelectUnion` est litteralement
`new List(n1 + n2); AddRange(left); AddRange(right)` -- AUCUN dedoublonnage. Une unite portant a la
fois `Summon` ET `Decoy` compte donc **DEUX FOIS**. Le port mirrore ce quirk.

## CE QUE CE FICHIER CORRIGE DANS LA FICHE

`case-589-r1-r1-r2-r1` sec.9 conclut « le regime est **inatteignable**, donc le quirk est lu, non
confronte ». La premiere moitie est re-mesuree VRAIE sur le build courant (etage 1) ; **la seconde
est FAUSSE**. Le natif ne lit pas le gameconfig : `UnitsWithTrait` teste
`IdunBattle.Entities.UnitExtensions$$HasFlag(unit, trait)`, donc le substrat d'ENTITE
`BC.Units[].Traits` -> `BaseUnitComponent` (#264) -- exactement le champ que le montage du probe
ECRIT DEJA pour piloter `n` (`--unit-stat '<vid>:Traits=["Decoy"]'`). Poser les DEUX traits sur le
meme compagnon arme donc le regime, sans aucun porteur natif :

    python probe_589r1r1r2r1_amulet_crit_reduction_live.py --n 1 --level 3 --trait Summon,Decoy

et la reduction attendue est celle d'un bras `--n 2 --trait Decoy`. Le residu n'est donc PAS a
parquer : il est CONFRONTABLE par le montage deja ecrit.

ASCII only (console cp1252)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PY not in sys.path:
    sys.path.insert(0, _PY)

_DATA = Path(_PY).parent.parent / "data" / "symbols"


def _gameconfig_units() -> dict:
    """Les trois voies du catalogue (`lineup` / `npc` / `summons`), depuis le gameconfig VERSIONNE
    du build COURANT.

    Le build est LU dans `data/symbols/CURRENT`, jamais code en dur : une mesure faite contre le
    mauvais dump ne dit rien du build charge."""
    build = (_DATA / "CURRENT").read_text(encoding="utf-8").strip()
    path = _DATA / build / "gameconfig.json"
    gc = json.loads(path.read_text(encoding="utf-8"))["clientGameConfig"]["units"]
    out = {}
    for kind in ("lineup", "npc", "summons"):
        for uid, d in (gc.get(kind) or {}).items():
            out[uid] = (kind, list(d.get("traits") or []))
    return out


def test_etage1_aucun_porteur_des_deux_traits_au_gameconfig():
    """LE CLIQUET DE REOUVERTURE. Il rougit le jour ou un build ajoute une unite portant a la fois
    `Summon` et `Decoy` : le quirk devient alors observable SANS montage, et la ligne de la fiche
    (« regime inatteignable ») doit etre reecrite.

    Premisse ASSERTIONNEE : sans elle, un catalogue vide (chemin faux, cle renommee) rendrait un
    ensemble vide, donc un VERT qui ne mesure rien -- exactement la faute que le contre-controle
    d'ordinaux de #270-r1-r1-r3 a deja payee."""
    units = _gameconfig_units()
    assert len(units) > 300, "catalogue trop maigre (%d) : la mesure ne porte sur rien" % len(units)
    summon = {u for u, (_k, t) in units.items() if "Summon" in t}
    decoy = {u for u, (_k, t) in units.items() if "Decoy" in t}
    assert summon, "aucune unite `Summon` : le compteur n'a plus de substrat, RELIRE le natif"
    assert decoy, "aucune unite `Decoy` : idem"
    deux = sorted(summon & decoy)
    assert deux == [], (
        "REOUVERTURE de #589-r1-r1-r2-r1-r2 : %s porte(nt) a la fois Summon et Decoy. Le quirk de "
        "non-dedoublonnage de `CombinedSelector$$SelectUnion` devient OBSERVABLE sans montage." % deux)


def test_etage2_le_mirror_de_l_union_concatene_et_ne_dedoublonne_pas():
    """Le quirk PORTE. `engine.entities.selectors.units.Union` doit CONCATENER : une unite presente
    des deux cotes doit sortir DEUX FOIS.

    Contre-epreuve (vue rouge en remplacant le `+` du mirror par une union ensembliste) :
    `AssertionError: le mirror DEDOUBLONNE : 1 element pour 2 attendus`."""
    from engine.entities.selectors.units import Union, UnitSet
    u = {"id": 42, "alive": True}
    sel = Union(UnitSet([u]), UnitSet([u]))
    out = sel.select(None)
    assert len(out) == 2, "le mirror DEDOUBLONNE : %d element(s) pour 2 attendus" % len(out)
    assert [x["id"] for x in out] == [42, 42], out


def test_etage3_le_probe_sait_armer_le_bras_union():
    """Le montage qui CONFRONTE le quirk doit exister, sinon la conclusion « confrontable » n'est
    qu'une opinion. `--trait` accepte une LISTE et refuse tout trait que le natif ne compte pas."""
    import probe_589r1r1r2r1_amulet_crit_reduction_live as P
    assert P._traits_json("Summon,Decoy") == '"Summon","Decoy"'
    assert P._traits_json("Decoy") == '"Decoy"'
    for mauvais in ("Hero", "Summon,Hero", ""):
        try:
            P._traits_json(mauvais)
        except SystemExit:
            continue
        raise AssertionError("`--trait %s` accepte : un trait INERTE ferait tomber n a zero "
                             "sans qu'aucune assertion ne designe la cause" % mauvais)
