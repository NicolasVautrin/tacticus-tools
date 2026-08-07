"""#175-e / #175-r -- les deux gates de tuile que le port n'avait pas, et leur temoin NON NUL.

DEUX defauts distincts, un seul foyer (`engine/utilities/tile.py`) :

* **#175-e -- l'IMMUNITE.** `IdunBattle.AI.Utilities.DespoiledGroundUtility.
  u003CEvaluateMovementInStepsu003Ed__5$$MoveNext` et sa soeur `ContaminatedUtility.
  u003CEvaluateMovementInStepsu003Ed__4$$MoveNext` appellent, JUSTE apres `case.unit == null` et
  AVANT d'enumerer les effets de la tuile :

      IEffect eff = <effectsDatabase @+0x60>.GetEffect(<effectType>);   // IEffectsDatabase slot 0
      if (eff.EntityIsImmuneToEffect(case.unit)) yield break;           // IEffect slot 40

  Le port n'avait NI l'un NI l'autre : cote Contaminated une cle `ctx.contaminated_excluded` que
  personne ne peuplait, cote DespoiledGround rien du tout. Et le 2e etage MORD pour les deux
  effets, parce que les DEUX classes surchargent `get_CanBeImmuneTo` a `true`.

* **#175-r -- `ability_friend_counts`.** Les feuilles `KustomForceField(21)`,
  `DefenderOfTheGreaterGood(22)` et `SaviorProtocols(23)` lisent cette cle de `meta` ; AUCUN
  constructeur de `meta` du composite `Tile(7)` ne la posait (seul `engine/runner/abilities/loki/
  mv71.py` le fait, sur SON chemin a lui). Les trois feuilles etaient donc a 0 partout.

TEMOIN NON NUL, cote NATIF, pour #175-e -- il est LU AU BINAIRE, pas suppose, et par TROIS voies
independantes (cf. `docs/rl/case-175e-immunite-des-feuilles-de-tuile.md`) :
  1. `global-metadata.dat` : `Idun.Source.IdunBattle.Logic.Entities.Effects.DespoiledGroundEffect`
     DECLARE `get_CanBeImmuneTo` (slot 59) et NE declare PAS `EntityIsImmuneToEffect` (slot 75) ;
  2. bloc `methodPointers` du PE, ancre LOCALEMENT sur une methode nommee de la classe, alignement
     controle : corps = `b0 01 c3` (`mov al,1 ; ret`) = **true** ;
  3. le meme bloc, ancre GLOBALEMENT (275 methodes nommees concordantes), qui rend en plus les VA
     EXACTES de `BaseEffect$$EntityIsImmuneToEffect` et `ContaminatedEffect$$EntityIsImmuneToEffect`
     -- deux symboles ghidra connus, donc le calage est verifie par des valeurs qu'on n'a pas
     choisies.

CE QUI N'EST PAS COUVERT, et pourquoi -- le SCORE NATIF par feuille. Le confronter exigerait
`aiUtilityTrace` / `scorer-damage-trace`, dont les RVA sont celles de `gqfc5mff6c` et ne se
re-arment pas sans reinject (meme limite que `case-175` Sec.6 et `case-271` Sec.7.4). Les
assertions ci-dessous portent donc sur : le NATIF lu au binaire, le SUBSTRAT mesure LIVE, et le
port confronte aux deux -- jamais sur une egalite de score natif.

ASCII only.
"""
from __future__ import annotations

import pytest

#: Ce qui doit changer pour que ce fichier puisse changer de verdict (#486-r15). LISTE, pas glob :
#: les assertions relisent le BINAIRE (metadata + PE) et TROIS foyers Python precis. Un glob
#: `scripts/python/**` le retiendrait a chaque probe touche, ce qui ne dirait plus rien.
DECLENCHEUR = {
    "chemins": (
        # LA CASCADE DES `conftest.py` N'EST PLUS ICI (dont `gameconfig`) : le foyer la DERIVE
        # depuis #531 -- 447 chemins pour `tests/engine/`, et les sept recopies a cette place y
        # sont, sauf `build_pin.py`, garde ci-dessous.
        "scripts/python/build_pin.py",
        # PROPRE A CE FICHIER -- les trois foyers sous test.
        "scripts/python/engine/utilities/tile.py",
        "scripts/python/engine/entities/effects/base.py",
        "scripts/python/engine/entities/effects/loki/status.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/traits/unit_trait.py",
        "scripts/python/engine/battle_query.py",
        "scripts/python/engine/weights.py",
        # L'etage 1 relit le BINAIRE par cette machinerie (et par la table de symboles VERSIONNEE,
        # qui bouge au changement de build).
        "scripts/python/il2cpp_metadata.py",
        "scripts/python/probe_477r37_slot4_et_faces_restantes.py",
        # ... ET CE QUE CE PROBE IMPORTE. Declarer le probe ne declare PAS sa fermeture : six
        # freres entrent par lui, et un `ImportError` chez l'un d'eux change le verdict d'ici.
        "scripts/python/il2cpp_provenance.py",
        "scripts/python/probe_193c_move_playbook_terms.py",
        "scripts/python/probe_212_bc_key_literals.py",
        "scripts/python/probe_212_spiritual_leader_tile_term.py",
        "scripts/python/probe_477r31_attract_mechanicals_camp.py",
        "scripts/python/probe_477r33_non_owner_registry_gaps.py",
        "data/symbols/**",
    ),
    # `build: True` : l'etage 1 RELIT le binaire du build (metadata + PE) et la table de symboles
    # versionnee -- ce fichier change donc de verdict a chaque changement de `<HASH>`.
    "build": True,
    "toujours": False,
    "raison": (
        "Les etages 1-2 sont OFFLINE et deterministes : ils ne dependent que des foyers ci-dessus "
        "et du binaire du build. L'etage 3 monte un runner, donc il depend AUSSI de la session "
        "live -- ce que le declencheur ne peut pas exprimer et qui rend cette liste une BORNE "
        "INFERIEURE, pas une garantie."),
}


# ================================================================================================
# ETAGE 1 (offline) -- #175-e : le natif LU AU BINAIRE, et le port confronte a lui
# ================================================================================================
def test_175e_le_natif_dit_que_les_deux_effets_sont_immunisables():
    """La VALEUR de `get_CanBeImmuneTo` des deux classes, RE-DERIVEE du `global-metadata.dat` + PE.

    Ce test ne relit PAS le port : il relit le BINAIRE. Il rougit donc si le build change d'avis,
    ce qui est exactement ce qu'on veut garder -- l'attribut du port n'est qu'une COPIE.
    `pytest.skip` si le jeu n'est pas installe (NON MESURE, jamais un vert deguise)."""
    from pathlib import Path
    import build_pin
    try:
        meta = Path(build_pin.global_metadata())
    except Exception as exc:                                          # noqa: BLE001
        pytest.skip("global-metadata absent (NON MESURE) : %s" % exc)
    dll = meta.parents[3] / "GameAssembly.dll"
    if not dll.is_file():
        pytest.skip("GameAssembly.dll absente (NON MESURE)")
    import il2cpp_metadata
    import probe_477r37_slot4_et_faces_restantes as P

    build = build_pin.current_build()
    methods_tsv = P.build_dir(build) / "frida" / "methods.tsv"
    reader = il2cpp_metadata.read(meta)
    reader.locate(il2cpp_metadata.class_method_order(methods_tsv, "%s.%s" % P.ANCRES_TYPES[0]))
    reader.locate_types([(ns, nm, il2cpp_metadata.class_method_order(methods_tsv,
                                                                    "%s.%s" % (ns, nm)))
                         for ns, nm in P.ANCRES_TYPES])
    par_sym, par_va = P._fonctions(build)
    pe = P._PE(dll)

    for ns, nm, surcharge_attendue in (
            ("Idun.Source.IdunBattle.Logic.Entities.Effects", "DespoiledGroundEffect", False),
            ("IdunBattle.Entities.Effects.Loki", "ContaminatedEffect", True)):
        ms = reader.type_methods(ns, nm)
        noms = [m.name for m in ms]
        assert "get_CanBeImmuneTo" in noms, (
            "%s ne DECLARE plus `get_CanBeImmuneTo` : elle heriterait le `false` de la base et le "
            "gate d'immunite de la feuille serait INERTE" % nm)
        assert ("EntityIsImmuneToEffect" in noms) is surcharge_attendue, (
            "%s : surcharge d'`EntityIsImmuneToEffect` attendue=%s, lue=%s -- le port modelise "
            "l'une des deux formes du predicat, pas l'autre"
            % (nm, surcharge_attendue, "EntityIsImmuneToEffect" in noms))
        # VALEUR : bloc `methodPointers`, ancre LOCALEMENT sur une methode nommee de la classe
        # (alignement controle sur toutes les autres) -- jamais sur un voisin, cf. #477-r35.
        uniq = [m for m in ms if noms.count(m.name) == 1 and not m.name.startswith(".")]
        ancre = next(((m, par_sym["%s.%s$$%s" % (ns, nm, m.name)]) for m in uniq
                      if "%s.%s$$%s" % (ns, nm, m.name) in par_sym), None)
        if ancre is None:
            continue                    # aucun corps nomme : l'etage 3 (index global) l'a couvert
        m0, va0 = ancre
        off = pe.offset_du_pointeur(va0)
        assert off >= 0, "%s : `%s` hors du bloc methodPointers" % (nm, m0.name)
        i0 = noms.index(m0.name)
        for k, mn in enumerate(noms):
            plein = "%s.%s$$%s" % (ns, nm, mn)
            if noms.count(mn) != 1 or plein not in par_sym:
                continue
            lu = pe.qword(off + 8 * (k - i0))
            assert lu == par_sym[plein], (
                "%s : le bloc methodPointers ne suit PAS l'ordre du metadata (position %d = %s, "
                "lu %s) -- la lecture de la VALEUR serait celle d'une AUTRE methode"
                % (nm, k, mn, par_va.get(lu, hex(lu))))
        va = pe.qword(off + 8 * (noms.index("get_CanBeImmuneTo") - i0))
        assert pe.octets(va) == P.OCTETS_VRAI, (
            "%s.get_CanBeImmuneTo : corps %r, attendu %r (`mov al,1 ; ret`). Le port porte "
            "`can_be_immune_to = True` : si le build dit l'inverse, c'est le PORT qui doit changer"
            % (nm, pe.octets(va), P.OCTETS_VRAI))


def test_175e_le_port_porte_la_valeur_lue():
    """Le port DOIT porter `can_be_immune_to = True` sur les DEUX classes.

    Anti-degenere : la BASE, elle, doit rester `False` -- sinon le predicat serait vrai partout et
    l'assertion ci-dessus passerait pour une mauvaise raison."""
    from engine.entities.effects.base import BaseEffect
    from engine.entities.effects.loki.status import ContaminatedEffect, DespoiledGroundEffect
    assert BaseEffect.can_be_immune_to is False, (
        "`BaseEffect.get_CanBeImmuneTo` vaut `32 c0 c3` (xor eax,eax ; ret) au binaire : si le "
        "port passe la BASE a True, TOUS les effets deviennent immunisables et le test suivant "
        "ne prouve plus rien")
    assert DespoiledGroundEffect.can_be_immune_to is True, (
        "`DespoiledGroundEffect` DECLARE `get_CanBeImmuneTo` (slot 59, global-metadata) et son "
        "corps est `b0 01 c3` (mov al,1 ; ret). Sans cet attribut, `EntityIsImmuneToEffect` rend "
        "False INCONDITIONNELLEMENT et la feuille DespoiledGround(29) sur-penalise une unite Immune")
    assert ContaminatedEffect.can_be_immune_to is True


def test_175e_temoin_non_nul_du_terme_despoiled_ground():
    """Le TEMOIN : sur une tuile DespoiledGround, une unite `Immune` doit rendre 0, une autre non.

    C'est un ecart de **25 points** sur la feuille DespoiledGround(29), et il ne depend d'aucun
    montage : le gate ne lit que les traits du sujet. Les deux bras sont exiges NON EGAUX --
    un test qui ne compare qu'un seul bras ne verrait pas un gate arme a `True` partout."""
    from engine import weights as W
    from engine.entities.effect_type import EffectType
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.utilities.tile import DespoiledGroundUtility
    wt = W.load()
    u = DespoiledGroundUtility()
    meta = {"tile_effect_type_ids": [int(EffectType.DespoiledGround)]}
    imperial = {"unit_traits": (int(UnitTrait.Imperial),)}
    immune = {"unit_traits": (int(UnitTrait.Imperial), int(UnitTrait.Immune))}
    sans = float(u.evaluate((0, 0), meta, imperial, wt))
    avec = float(u.evaluate((0, 0), meta, immune, wt))
    assert sans != 0.0, (
        "REGIME DEGENERE : le terme vaut deja 0 sans immunite (poids BC "
        "`DespoiledGround.ImperialAndXenosAffectedUnit` absent ?) -- la comparaison ne prouverait "
        "rien")
    assert avec == 0.0, (
        "une unite portant `UnitTrait.Immune` rend %r : le gate `EntityIsImmuneToEffect` n'est pas "
        "arme, le port SUR-PENALISE une unite que le natif epargne" % avec)


def test_175e_contaminated_ismechanical_est_la_chaine_de_TROIS_traits():
    """`ContaminatedEffect$$EntityIsImmuneToEffect` appelle `IsMechanical`, PAS `HasTrait(Mechanical)`.

    `IdunBattle.Entities.UnitExtensions$$IsMechanical` = `HasTrait(5) || HasTrait(0x3e8) ||
    HasTrait(0x405)`. Les trois bras sont exiges separement : sur le catalogue de ce build les
    trois ensembles coincident (tout `LivingMetal`/`Vehicle` y est aussi `Mechanical`), donc un
    port qui ne lirait que `Mechanical` serait juste PAR ACCIDENT et le resterait jusqu'a ce qu'un
    `AddTrait` en bataille accorde `LivingMetal` seul."""
    from engine.entities.effects.loki.status import ContaminatedEffect
    from engine.entities.traits.unit_trait import UnitTrait
    eff = ContaminatedEffect(name="Contaminated")
    for t in (UnitTrait.Mechanical, UnitTrait.LivingMetal, UnitTrait.Vehicle):
        assert eff.entity_is_immune_to_effect([t.name]) is True, (
            "le trait %s seul ne declenche pas l'immunite : le port lit `HasTrait(Mechanical)` la "
            "ou le natif enchaine les TROIS" % t.name)
    assert eff.entity_is_immune_to_effect([UnitTrait.ContagionsOfNurgle.name]) is True
    assert eff.entity_is_immune_to_effect([UnitTrait.Imperial.name]) is False, (
        "REGIME DEGENERE : le predicat rend True sur un trait quelconque")


def test_175e_contaminated_se_tait_en_regime_spawn():
    """`if (case.unit == null) yield break;` -- l'etat 0 de la SM, que le port n'avait pas.

    La soeur `DespoiledGroundUtility` le portait deja (case-205) ; `ContaminatedUtility` versait
    donc son -25 sur une decision de tuile de SPAWN, ou le natif n'emet AUCUN step."""
    from engine import weights as W
    from engine.entities.effect_type import EffectType
    from engine.utilities.tile import ContaminatedUtility
    wt = W.load()
    u = ContaminatedUtility()
    meta = {"tile_effect_type_ids": [int(EffectType.Contaminated)]}
    sujet = float(u.evaluate((0, 0), meta, {"unit_traits": ()}, wt))
    spawn = float(u.evaluate((0, 0), meta, {"is_spawning": True}, wt))
    assert sujet != 0.0, "REGIME DEGENERE : le terme est deja nul avec un sujet"
    assert spawn == 0.0, (
        "en regime SPAWN le port rend %r ; le natif sort a la premiere instruction" % spawn)


# ================================================================================================
# ETAGE 2 (offline) -- #175-r : `ability_friend_counts`, les DEUX voisinages
# ================================================================================================
def _ctx_trois_amis(faction=None, porteur=False):
    """Trois amis porteurs : un a ring-1 de la tuile (1,1), deux a distance hex 2."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType as TA
    neigh = {(1, 1): [(1, 0), (1, 2), (0, 1), (2, 1), (0, 0), (2, 0)]}
    return {"elev_by_pos": {}, "neigh_by_pos": neigh, "enemy_units": [],
            "unit_faction": faction, "self_pos": (3, 1),
            "unit_triggered_abilities": ([int(TA.DefenderOfTheGreaterGood)] if porteur else []),
            "friend_units": [
                {"pos": (1, 0), "triggered": [int(TA.DefenderOfTheGreaterGood)]},
                {"pos": (3, 0), "triggered": [int(TA.DefenderOfTheGreaterGood)]},
                {"pos": (1, 3), "triggered": [int(TA.DefenderOfTheGreaterGood)]}]}


def test_175r_ability_friend_counts_est_pose_et_non_nul():
    """TEMOIN NON NUL : `apply_tile_attributes` doit poser un compte, la ou il ne posait RIEN.

    L'assertion porte sur la CLE et sur sa valeur : une cle presente a 0 serait le meme silence
    qu'avant."""
    from engine.utilities.tile import apply_tile_attributes
    from engine.entities.triggered_ability_type import TriggeredAbilityType as TA
    meta = apply_tile_attributes({}, (1, 1), _ctx_trois_amis())
    counts = meta.get("ability_friend_counts")
    assert counts is not None, (
        "`apply_tile_attributes` ne pose toujours pas `ability_friend_counts` : les feuilles "
        "21/22/23 restent structurellement a 0 sur les DEUX chemins de production")
    assert counts.get(int(TA.DefenderOfTheGreaterGood)) == 1, (
        "voisinage ring-1 attendu pour un mover NON Tau : %r" % (counts,))


def test_175r_la_branche_TAU_change_le_voisinage_ET_reinjecte_self():
    """Les DEUX ecarts de `DefenderOfTheGreaterGoodUtility$$GetUnitsWithUtilityForMove`.

    `sel = SurroundingFriends(Entity(case.unit), Entity(case.MovementTile), 2, 1, 3)` REMPLACE
    `GetFriendsAdjacentToMovementTile` quand le mover est Tau : disque hex de rayon 2 (donc plus
    de porte d'elevation) **et** aucun `op_Subtraction` du mover. Les deux sont mesures
    separement : un port qui n'aurait que le disque rendrait 3, pas 4."""
    from engine.utilities.tile import apply_tile_attributes
    from engine.entities.triggered_ability_type import TriggeredAbilityType as TA
    from engine.entities.unit_faction import UnitFaction
    ab = int(TA.DefenderOfTheGreaterGood)
    non_tau = apply_tile_attributes({}, (1, 1), _ctx_trois_amis())["ability_friend_counts"]
    tau = apply_tile_attributes({}, (1, 1), _ctx_trois_amis(int(UnitFaction.Tau)))
    tau_porteur = apply_tile_attributes({}, (1, 1),
                                        _ctx_trois_amis(int(UnitFaction.Tau), porteur=True))
    assert non_tau.get(ab) == 1
    assert tau["ability_friend_counts"].get(ab) == 3, (
        "mover Tau : le voisinage doit devenir le DISQUE de rayon 2 (3 amis), pas le ring-1 "
        "(1 ami) -- %r" % (tau["ability_friend_counts"],))
    assert tau_porteur["ability_friend_counts"].get(ab) == 4, (
        "mover Tau PORTEUR de 1155 : `SurroundingFriends` ne soustrait PAS `case.unit`, donc il "
        "se compte lui-meme -- %r" % (tau_porteur["ability_friend_counts"],))


def test_175r_les_trois_feuilles_rendent_desormais_un_terme():
    """Le bout de la chaine : `n x GetUtilityPerUnit()`, le corps PARTAGE
    `ATriggeredAbilityUtility.u003CEvaluateMovementInStepsu003Ed__3$$MoveNext`.

    Les gates propres de 22 et 23 sont exerces dans les DEUX sens -- sans eux le test passerait
    aussi bien sur un port qui aurait oublie de les poser."""
    from engine import weights as W
    from engine.entities.triggered_ability_type import TriggeredAbilityType as TA
    from engine.entities.unit_faction import UnitFaction
    from engine.utilities.tile import (DefenderOfTheGreaterGoodUtility, SaviorProtocolsUtility,
                                       apply_tile_attributes)
    wt = W.load()
    w22 = float(wt.sub("DefenderOfTheGreaterGood", "PerUnitWithAbilityInRange"))
    assert w22 != 0.0, "REGIME DEGENERE : poids BC nul"
    ctx = _ctx_trois_amis(int(UnitFaction.Tau))
    ctx["unit_has_ranged_weapon"] = True
    meta = apply_tile_attributes({}, (1, 1), ctx)
    lu = float(DefenderOfTheGreaterGoodUtility().evaluate((1, 1), meta, ctx, wt))
    assert lu == 3 * w22, (
        "feuille 22, mover Tau, 3 amis porteurs dans le disque r=2 : attendu %r (= 3 x %r), lu %r "
        "-- le corps partage `ATriggeredAbilityUtility.<EvaluateMovementInSteps>d__3` rend "
        "`Fix64.FromInt(n) x GetUtilityPerUnit()`" % (3 * w22, w22, lu))
    sans_arme = dict(ctx, unit_has_ranged_weapon=False)
    assert float(DefenderOfTheGreaterGoodUtility().evaluate((1, 1), meta, sans_arme, wt)) == 0.0, (
        "le gate `HasRangedWeapon` du natif n'est plus applique")
    # feuille 23 : le gate est `Tau ET PAS porteur de 1120`
    ctx23 = dict(ctx, unit_triggered_abilities=[int(TA.SaviorProtocols)])
    meta23 = apply_tile_attributes({}, (1, 1), ctx23)
    assert float(SaviorProtocolsUtility().evaluate((1, 1), meta23, ctx23, wt)) == 0.0, (
        "un mover qui PORTE deja 1120 doit rendre 0 (`CanBeProtector`)")


# ================================================================================================
# ETAGE 3 (LIVE) -- le substrat mord-il en bataille ?
# ================================================================================================
def test_175r_sort_tiles_by_utility_pose_desormais_les_attributs_de_tuile(rpc, build_runner):
    """`sort_tiles_by_utility` etait le TROISIEME constructeur de `meta`, et le seul a n'appeler
    PAS `apply_tile_attributes` : sur le selecteur DSL `SortTilesByUtilitySelector` (call-sites de
    charge + tuile de spawn d'un summon), toutes les feuilles a attribut de tuile rendaient 0.

    Mesure LIVE : on construit le `meta` de ce foyer sur un board REEL et on exige qu'il porte
    desormais les cles que `apply_tile_attributes` derive du `leaf_ctx`."""
    from engine.utilities.tile import runner_tile_leaf_ctx, apply_tile_attributes
    rid = build_runner("175701", extra=["--p-units", "tauShadowsun,tauCrisis",
                                        "--a-units", "worldKharn"], board="MC1_67")["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    tiles = [(t["col"], t["row"]) for t in (bg.get("tiles") or []) if t.get("walkable")]
    if not tiles:
        pytest.skip("boardGraph indispo")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mover = next((u for u in units if u.get("visualId") == "tauCrisis"), None)
    shadow = next((u for u in units if u.get("visualId") == "tauShadowsun"), None)
    if mover is None or shadow is None:
        pytest.skip("montage tauCrisis + tauShadowsun non obtenu")
    # substrat du foyer de TRI : un `State` de runner n'est pas disponible ici, on mesure donc la
    # chaine `leaf_ctx -> apply_tile_attributes` sur un ctx fabrique DEPUIS la vue live.
    lc = {"friend_units": [{"pos": (shadow["pos"]["col"], shadow["pos"]["row"]),
                            "triggered": [1155]}],
          "enemy_units": [], "elev_by_pos": {}, "neigh_by_pos": None,
          "unit_faction": 9, "unit_triggered_abilities": [], "self_pos": None}
    sp = (shadow["pos"]["col"], shadow["pos"]["row"])
    meta = apply_tile_attributes({}, sp, lc)
    assert meta.get("ability_friend_counts", {}).get(1155) == 1, (
        "sur la tuile de Shadowsun elle-meme, le compte 1155 doit valoir 1 (disque r=2, mover "
        "Tau) -- lu %r" % (meta.get("ability_friend_counts"),))
    # et le foyer de TRI doit desormais appeler `apply_tile_attributes` : on le verifie par le
    # SOURCE, la seule voie qui ne depende pas d'un etat de runner particulier.
    import inspect
    from engine.utilities import tile as T
    src = inspect.getsource(T.sort_tiles_by_utility)
    assert "apply_tile_attributes" in src, (
        "`sort_tiles_by_utility` ne pose toujours aucun attribut de tuile : le composite Tile(7) "
        "du selecteur DSL reste ampute de ses feuilles gatees")
    assert runner_tile_leaf_ctx is not None
