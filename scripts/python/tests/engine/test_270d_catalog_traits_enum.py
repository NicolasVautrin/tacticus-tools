"""#270-d -- GARDE : une entree injectee au catalogue ne peut porter QUE des membres de `UnitTrait`.

CE QUE CETTE GARDE TIENT. `IdunBattle.Configuration.UnitConfiguration.Traits` est TYPE
`List<IdunBattle.Entities.Enum.UnitTrait>` :

  * `Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` recopie
    `UnitProperties+0x18` dans `UnitConfiguration+0xd0` ;
  * `IdunMetaLogic.UserProgress.Model.UnitPropertiesExtensions$$GetPlayerFacingTraits` lit ce MEME
    `UnitProperties+0x18` et sa signature rend `List<IdunBattle.Entities.Enum.UnitTrait>`.

Un nom hors enum est donc INEXPRIMABLE dans ce champ, et le BC entier devient indeserialisable :
`initAndStart` step=deserialize BC -> `Newtonsoft.Json.Converters.StringEnumConverter$$ReadJson`
-> `Newtonsoft.Json.Utilities.EnumUtils$$ParseEnum` -> `$$MatchName`/`$$FindIndexByName` rendent un
`Nullable` vide -> `System.ArgumentException` LEVEE -> Frida rend « system error ». La degradation
n'est ni permissive ni localisee : elle emporte TOUT le montage, y compris les autres unites.

POURQUOI UNE GARDE ET PAS UN CONSTAT. Le gisement est reouvert par le JEU, pas par nous : le
gameconfig VIVANT est livre EN AVANCE sur le binaire. Mesure du 2026-07-31 (`rnca9r7q6c`) --
`astarLysander` (releaseStatus 2026-08-26) apporte `Subfaction: ImperialFists` quand `UnitTrait`
s'arrete a quatre sous-factions (9000..9003). Chaque livraison de contenu peut en apporter un autre,
et le symptome (« initAndStart: system error ») ne nomme jamais le coupable.

⚠ ET LE FILTRE EST DESORMAIS CONFRONTE A LA FABRIQUE, PLUS SEULEMENT AU TYPE (#10039). Le
raisonnement ci-dessus est un raisonnement de TYPAGE : le champ est un `List<UnitTrait>`, donc un
nom hors enum y est inexprimable. Depuis que `data/seed-bc.json` est FORGE par
`Idun.Source.IdunBattle.View.BattleConfigBuilder` (et non plus la capture d'une bataille ou
`astarLysander` etait absent), on peut confronter le filtre a ce que la fabrique NATIVE ecrit
pour ce porteur meme -- et elle ecarte `ImperialFists` exactement comme lui. Le filtre n'est donc
plus « une consequence du type » : c'est un comportement OBSERVE du jeu.

Ces tests sont 100 % OFFLINE (gameconfig + table d'enums versionnee) : aucun runner, aucune session.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import catalog_inject as CI  # noqa: E402
import gameconfig as G  # noqa: E402

# Le porteur de #270-d : le montage NOMME du cas, jamais un id inline ailleurs.
LYSANDER = "astarLysander"

# NOM de l'enum, lu par `enum_map` -- l'API qui existait DEJA avant le correctif. La garde doit
# rougir sur la SUBSTANCE (un nom hors vocabulaire), pas sur un helper absent.
UNIT_TRAIT_ENUM = "IdunBattle.Entities.Enum.UnitTrait"


def _members() -> frozenset:
    return frozenset(CI.enum_map(UNIT_TRAIT_ENUM))


def _all_gameconfig_units() -> list:
    idx = G._index()
    return [(kind, uid, gc)
            for kind in ("lineup", "npc", "summons")
            for uid, gc in idx[kind].items()]


def test_synthese_ne_produit_que_des_membres_de_unit_trait():
    """AUCUNE des unites du gameconfig ne doit sortir du vocabulaire de l'enum.

    ROUGE avant le fix -- verbatim mesure le 2026-07-31 sur `rnca9r7q6c` :
        AssertionError: ces entrees porteraient un nom hors
        IdunBattle.Entities.Enum.UnitTrait -> le BC ENTIER devient indeserialisable
        (initAndStart: system error) : {'astarLysander': ['ImperialFists']}
    """
    members = _members()
    hors = {uid: [t for t in CI._traits(gc) if t not in members]
            for _kind, uid, gc in _all_gameconfig_units()}
    hors = {k: v for k, v in hors.items() if v}
    assert hors == {}, (
        "ces entrees porteraient un nom hors %s -> "
        "le BC ENTIER devient indeserialisable (initAndStart: system error) : %r"
        % (UNIT_TRAIT_ENUM, hors))


def test_lysander_est_deployable_et_ce_qui_est_ecarte_est_dit():
    """Le porteur de #270-d passe la gate, et ce qui a ete retire est NOMME (jamais silencieux)."""
    gc = G.unit(LYSANDER)
    assert gc is not None, "%s absent du gameconfig" % LYSANDER
    members = CI.unit_trait_members()
    garde = CI._traits(gc)
    ecarte = CI.dropped_traits(gc)
    assert set(garde) <= members
    assert set(ecarte).isdisjoint(members)
    # partition stricte : rien n'est invente, rien ne disparait sans etre compte
    assert sorted(garde + ecarte) == sorted(CI._traits_raw(gc))
    # le kit de combat proprement dit survit -- seule la sous-faction inconnue tombe
    for t in ("Hero", "TeleportStrike", "TerminatorArmour", "Resilient", "CrushingStrike"):
        assert t in garde, "%s a perdu %s" % (LYSANDER, t)


def test_le_JEU_ecarte_LUI_MEME_ce_que_le_filtre_ecarte():
    """LA CONFRONTATION DIRECTE, que la capture ne permettait pas (#10039).

    CE QUE CE TEST GARDAIT AVANT, ET POURQUOI IL A CHANGE DE FORME. Il verifiait que le filtre
    « n'a AUCUN effet sur la cohorte que le jeu a reellement construite » -- une garde par
    l'ABSENCE de cas : `astarLysander`, le seul porteur de #270-d, n'etait pas dans la capture
    (175 entrees), donc le filtre ne pouvait rien y toucher. Cette forme etait la meilleure
    disponible, mais elle ne disait rien de ce que le jeu fait quand le cas SE PRESENTE.

    Le catalogue est desormais FORGE par `Idun.Source.IdunBattle.View.BattleConfigBuilder`, et il
    porte `astarLysander`. On peut donc confronter le filtre a la fabrique NATIVE au lieu de
    l'eviter -- et le verdict est le meilleur possible : le jeu ecarte EXACTEMENT ce que le filtre
    ecarte. Mesure verbatim :

        gameconfig  : ['Imperial', 'ImperialFists', 'Hero', 'TeleportStrike', 'TerminatorArmour',
                       'Resilient', 'CrushingStrike']
        _traits()   : ['Imperial', 'Hero', 'TeleportStrike', 'TerminatorArmour', 'Resilient',
                       'CrushingStrike']
        BC forgee   : ['Imperial', 'Hero', 'TeleportStrike', 'TerminatorArmour', 'Resilient',
                       'CrushingStrike']

    Ce n'est plus « le filtre ne touche rien » : c'est « le filtre reproduit la fabrique ».
    """
    if not CI.SEED_BC.exists():
        pytest.skip("seed BC absent (%s) -- regenere: python dump_boards.py" % CI.SEED_BC)
    bc = json.loads(CI.SEED_BC.read_text(encoding="utf-8"))
    members = _members()
    hors = {u["Id"]: [t for t in (u.get("Traits") or []) if t not in members] for u in bc["Units"]}
    hors = {k: v for k, v in hors.items() if v}
    assert hors == {}, (
        "le catalogue lui-meme porte des traits hors enum -- le build a change sous nos "
        "pieds : %r" % hors)

    # Les entrees sur lesquelles le filtre MORD, DERIVEES du catalogue (jamais nommees a la main).
    mordues = {}
    for u in bc["Units"]:
        gc = G.unit(u["Id"].split(":")[0])
        if gc is None:
            continue
        drop = CI.dropped_traits(gc)
        if drop:
            mordues[u["Id"]] = drop
    assert mordues, (
        "le filtre ne mord sur AUCUNE entree du catalogue : la confrontation est VIDE et ce test "
        "ne prouve rien. Si le gameconfig n'est plus en avance sur le binaire, le dire -- ne pas "
        "laisser un vert vacueux.")

    # ... et sur CHACUNE, ce que la fabrique native a ecrit == ce que le filtre rend.
    ecarts = {}
    for uid in mordues:
        gc = G.unit(uid.split(":")[0])
        reel = [t for t in ((next(u for u in bc["Units"] if u["Id"] == uid).get("Traits")) or [])]
        if reel != CI._traits(gc):
            ecarts[uid] = {"forge": reel, "filtre": CI._traits(gc), "ecarte": mordues[uid]}
    assert ecarts == {}, (
        "le filtre ne reproduit PAS ce que la fabrique native a ecrit -- il change le catalogue "
        "au lieu de le mirrorer : %r" % ecarts)
    print("\n[270d] filtre confronte a la fabrique native sur %d entree(s) : %r"
          % (len(mordues), mordues))
