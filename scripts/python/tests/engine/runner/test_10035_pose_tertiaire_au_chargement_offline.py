"""#10035 -- la POSE des owner-effects d'une ability TERTIAIRE sur le chemin de CAPTURE.

CE QUE CE FICHIER GARDE, et pourquoi il existe. `IdunBattle.Operations.
InitializeActorAbilitiesOperation$$Execute` n'a qu'UNE boucle ABILITIES et elle enumere la
`Collection` du composant d'abilities (`+0x20`) -- l'ability TERTIAIRE y est au meme titre que les
autres, `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` l'y met par
`TriggeredAbilityComponent$$TryAdd(id, tertiaryAbilityState, 3)`. Il n'existe donc AUCUN ordre
natif ou l'owner-effect d'une relique ne serait pas pose.

Le port, lui, inversait l'ordre sur le chemin de CAPTURE : `snapshot._load_stats_and_effects`
porte le mirror de cette boucle (`spawn._seed_ability_owner_effects`), mais il tourne AVANT
`_load_tertiary_abilities`, SEUL ecrivain de `ctx.tertiary_ability`. La quatrieme source du seed
(#1005) y lisait donc toujours `None`, et AUCUN owner-effect de relique n'entrait dans l'etat par
la capture -- ce que trois residus decrivaient chacun comme un trou de registre distinct
(#589-r1-r1-r2-r1-r1, #908-r2, #922-r1), alors que c'est UNE cause d'ordre.

MESURE qui l'a etabli (`probe_922_intoxicating_elixir_live.py --n 0 --thrilled`, `emperKakophonist`
+ `IntoxicatingElixir`) : `instance_dans_by_unit` **0 -> 1** et l'ecart de degat par coup
`[462, 1600, 988] -> [0, 0, 0]`, les deux temoins du probe (`NOCHANNEL`, `CRITDMG_AVANT`) restant
ROUGES a `[6534, 4621, 5010]`.

⚠ CE FICHIER EST OFFLINE : il monte l'etat par `load_state` avec un payload `unitAbilityStates`
FABRIQUE, sans aucun runner. C'est voulu -- la cause est un ORDRE de passes, qui se mesure sans
bataille, et le montage LIVE vit dans les probes cites ci-dessus.
"""
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import inspect                                                              # noqa: E402
import pytest                                                              # noqa: E402

import hexgeo                                                              # noqa: E402
from engine.entities.effect_type import EffectType                         # noqa: E402
from engine.entities.effects import factory as F                           # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType    # noqa: E402
from engine.runner import snapshot as SNAP                                 # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/entities/effects_state.py",
        "scripts/python/engine/entities/unit_context.py",
        # Les mirrors d'enum dont les ordinaux sont FIGES au site par l'etage 0.
        "scripts/python/engine/entities/effect_type.py",
        "scripts/python/engine/entities/triggered_ability_type.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "L'etage 0 fige les ordinaux LUS au decompile (1462/1463/1464 cote "
              "`TriggeredAbilityType`, 1455/1456/1459/1460 cote `EffectType`) : un renumerotage du "
              "build les rendrait faux sans toucher aucun des chemins ci-dessus.",
}

COLS, ROWS = 8, 8
SPYDER, KELERMORPH, KAKOPHONIST, ENNEMI = 11, 12, 13, 21
HP = 90000

#: Les TROIS reliques dont la POSE etait le sujet des trois residus, avec leur porteur AUTORISE
#: (`catalog_inject.relic_carriers`) et les owner-effects que leur `CreateBehaviour` pose.
CAS = (
    (SPYDER, "necroSpyder", "NetherRealmCasket", 1462,
     ("NetherRealmCasket_CritDamageReduction", "NetherRealmCasket_LivingMetalBonus")),
    (KELERMORPH, "genesKelermorph", "AmuletOfTheVoidwyrm", 1464,
     ("AmuletOfTheVoidwyrm_CritDamageReduction",)),
    (KAKOPHONIST, "emperKakophonist", "IntoxicatingElixir", 1463,
     ("IntoxicatingElixir",)),
)

NIVEAU_TERTIAIRE, MULT_TERTIAIRE = 3, 100
NIVEAU_PASSIF, MULT_PASSIF = 50, 180


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _board():
    from engine.entities.pathfinding.board import Board
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


def _triggered(aid: int, hierarchie: int = 3, level: int = NIVEAU_TERTIAIRE,
               mult: int = MULT_TERTIAIRE) -> dict:
    """Une ligne du canal `unitAbilityStates` : `raw` = 12 x int32 depuis `+0x10`, donc
    `raw[0]` = `AbilityName` et `raw[10]` = la HIERARCHIE (3 = tertiaire, cf.
    `_load_tertiary_abilities`)."""
    raw = [0] * 12
    raw[0] = int(aid)
    raw[10] = int(hierarchie)
    return {"raw": raw, "level": int(level), "mult": int(mult)}


def _montage(*, relique=True, deep_strike=False, niveau=NIVEAU_TERTIAIRE, effets_captes=()):
    """`decisionView` + `observeBattle` + `combatSnapshot` + `unitAbilityStates` FABRIQUES.

    `effets_captes` : noms d'owner-effet a publier dans `decisionView` comme s'ils avaient ete
    CAPTES actifs -- c'est ce qui permet de distinguer « le seed a pose » de « le canal avait
    deja publie » (le seed est idempotent, donc un montage qui publie tout serait un VERT VIDE)."""
    unites, ab_units, snap_units, ob_units, dv_effects = [], [], [], [], []
    for i, (uid, vid, _relic, aid, _noms) in enumerate(CAS):
        effs = []
        for nom in effets_captes:
            if nom in _noms:
                e = {"id": 9000 + len(dv_effects), "name": nom,
                     "effectType": int(EffectType[nom]), "source": uid, "active": True}
                effs.append(e)
                dv_effects.append(dict(e, ownerId=uid, targetIds=[]))
        if deep_strike:
            e = {"id": 9500 + i, "name": EffectType.TeleportStrike_TeleportingIn.name,
                 "effectType": int(EffectType.TeleportStrike_TeleportingIn),
                 "source": uid, "active": True}
            effs.append(e)
            dv_effects.append(dict(e, ownerId=uid, targetIds=[]))
        unites.append({"id": uid, "visualId": vid, "alive": True, "team": 1, "owner": 1,
                       "pos": {"col": 1, "row": i}, "effects": effs})
        snap_units.append({"entityId": uid, "visualId": vid, "entityType": 1,
                           "unitConfig": {"abilityVariablesMultiplier": MULT_PASSIF,
                                          "passiveAbilityLevel": NIVEAU_PASSIF,
                                          "activeAbilityLevel": NIVEAU_PASSIF}})
        ob_units.append({"squadId": uid, "hp": HP, "hpMax": HP})
        if relique:
            ab_units.append({"entityId": uid, "triggered": [_triggered(aid, level=niveau)]})
        else:
            ab_units.append({"entityId": uid, "triggered": []})
    unites.append({"id": ENNEMI, "visualId": "orksRuntherd", "alive": True, "team": 2, "owner": 2,
                   "pos": {"col": 6, "row": 6}, "effects": []})
    snap_units.append({"entityId": ENNEMI, "visualId": "orksRuntherd", "entityType": 1})
    ob_units.append({"squadId": ENNEMI, "hp": HP, "hpMax": HP})
    dv = {"currentPlayer": 1, "units": unites, "effects": dv_effects}
    return (dv, {"units": ob_units}, {"units": snap_units}, {"units": ab_units})


def _charger(**kw):
    dv, ob, snap, ab = _montage(**kw)
    return load_state(dv, ob, snap, board=_board(), ability_states=ab)


def _noms(state, uid):
    return sorted(e.name for e in (state.effects.by_unit.get(int(uid)) or ()))


def _inst(state, uid, nom):
    for e in (state.effects.by_unit.get(int(uid)) or ()):
        if e.name == nom:
            return e
    return None


# --------------------------------------------------------------------------------------------
# Etage 0 -- les ordinaux et les entrees de registre, LUS au decompile
# --------------------------------------------------------------------------------------------

def test_les_ordinaux_des_deux_enums_sont_figes_au_site():
    """Les trois reliques et leurs quatre owner-effects. `TriggeredAbilityType` et `EffectType`
    partagent des ordinaux a la pelle : c'est le NOM qui discrimine, jamais la valeur."""
    assert int(TriggeredAbilityType.NetherRealmCasket) == 1462
    assert int(TriggeredAbilityType.IntoxicatingElixir) == 1463
    assert int(TriggeredAbilityType.AmuletOfTheVoidwyrm) == 1464
    assert int(EffectType.NetherRealmCasket_CritDamageReduction) == 1455
    assert int(EffectType.NetherRealmCasket_LivingMetalBonus) == 1456
    assert int(EffectType.IntoxicatingElixir) == 1459
    assert int(EffectType.AmuletOfTheVoidwyrm_CritDamageReduction) == 1460
    for _uid, _vid, relic, aid, _noms in CAS:
        assert int(TriggeredAbilityType[relic]) == aid


def test_le_meme_ordinal_1459_nomme_AUTRE_CHOSE_dans_l_autre_enum():
    """TEMOIN de non-degenerescence de l'etage 0 : si les deux enums nommaient pareil a ces
    ordinaux, confondre `EffectType` et `TriggeredAbilityType` serait indetectable et figer les
    valeurs ne dirait rien."""
    croises = 0
    for nom_effet in ("IntoxicatingElixir", "AmuletOfTheVoidwyrm_CritDamageReduction",
                      "NetherRealmCasket_CritDamageReduction"):
        ordinal = int(EffectType[nom_effet])
        try:
            autre = TriggeredAbilityType(ordinal).name
        except ValueError:
            continue
        croises += 1
        assert autre != nom_effet, (
            f"TEMOIN DEGENERE : l'ordinal {ordinal} nomme `{nom_effet}` dans les DEUX enums")
    assert croises > 0, ("TEMOIN VIDE : aucun des trois ordinaux n'existe dans "
                         "`TriggeredAbilityType` -- l'assertion ci-dessus n'a rien evalue")


def test_les_trois_reliques_ont_leur_entree_de_registre():
    """`factory.ABILITY_INIT_OWNER_EFFECTS` est keye par le nom d'ABILITY, l'effet porte un AUTRE
    nom (`AmuletOfTheVoidwyrm` -> `AmuletOfTheVoidwyrm_CritDamageReduction`). Sans cette entree,
    la passe de pose n'aurait rien a poser -- c'est la premiere moitie du mecanisme."""
    for _uid, _vid, relic, _aid, noms in CAS:
        assert tuple(F.ABILITY_INIT_OWNER_EFFECTS.get(relic) or ()) == noms, relic


# --------------------------------------------------------------------------------------------
# Etage 1 -- LE RANG DE LA PASSE : apres l'ecrivain de `tertiary_ability`, avant le re-bake
# --------------------------------------------------------------------------------------------

def test_la_passe_est_APRES_l_ecrivain_de_la_tertiaire_et_AVANT_le_rebake():
    """C'est la CAUSE RACINE elle-meme, figee : la boucle ABILITIES de `_load_stats_and_effects`
    tourne AVANT `_load_tertiary_abilities`, donc sa quatrieme source y est structurellement
    muette. Remonter la pose au-dessus de l'ecrivain la rendrait muette a nouveau -- sans erreur,
    sans crash, et sans qu'aucun test de valeur ne le voie sur un montage sans relique."""
    src = inspect.getsource(SNAP.load_state)
    i_stats = src.index("_load_stats_and_effects(state,")
    i_tert = src.index("_load_tertiary_abilities(state, payload)")
    i_seed = src.index("_seed_tertiary_owner_effects(state)")
    i_rebake = src.index("_rebake_tertiary_owner_effects(state)")
    assert i_stats < i_tert, "`_load_stats_and_effects` doit rester AVANT le seed de la tertiaire"
    assert i_tert < i_seed, (
        "la pose des owner-effects tertiaires est REMONTEE au-dessus de son ecrivain "
        "(`_load_tertiary_abilities`) : elle relirait `tertiary_ability = None` sur toute unite")
    assert i_seed < i_rebake, (
        "le re-bake doit rester l'ECRIVAIN FINAL du couple, donc APRES la pose")


def test_la_passe_est_TRACEE_dans_ability_states_seed():
    """Un seed qui ne dit pas combien il a pose ne se distingue pas d'un seed qui n'a rien vu."""
    st = _charger()
    assert st.ability_states_seed.get("seededTertiaryOwnerEffects") == len(CAS)
    st0 = _charger(relique=False)
    assert st0.ability_states_seed.get("seededTertiaryOwnerEffects") == 0


# --------------------------------------------------------------------------------------------
# Etage 2 -- LA POSE, de bout en bout par `load_state`, avec sa contre-epreuve
# --------------------------------------------------------------------------------------------

def test_le_montage_ne_publie_PAS_les_owner_effets_de_relique():
    """TEMOIN DE NON-DEGENERESCENCE, joue AVANT les assertions de pose. `_materialize_owner_effect`
    est idempotent (gate `has_effect`) : si `decisionView.effects` publiait deja ces effets, la
    passe serait un no-op et l'etage 2 serait VERT SANS RIEN MESURER."""
    dv, _ob, _snap, _ab = _montage()
    publies = {e.get("name") for e in (dv.get("effects") or ())}
    attendus = {n for _u, _v, _r, _a, noms in CAS for n in noms}
    assert not (publies & attendus), (
        f"le montage publie deja {sorted(publies & attendus)} : la pose ne serait pas mesuree")


@pytest.mark.parametrize("uid,vid,relic,aid,noms", CAS,
                         ids=[c[2] for c in CAS])
def test_la_relique_equipee_POSE_ses_owner_effets(uid, vid, relic, aid, noms):
    st = _charger()
    presents = _noms(st, uid)
    for nom in noms:
        assert nom in presents, (
            f"{relic} sur {vid} : `{nom}` ABSENT de l'etat charge -- la boucle ABILITIES de "
            f"`InitializeActorAbilitiesOperation$$Execute` n'a pas vu l'ability tertiaire "
            f"(presents : {presents})")


@pytest.mark.parametrize("uid,vid,relic,aid,noms", CAS,
                         ids=[c[2] for c in CAS])
def test_CONTRE_EPREUVE_sans_relique_equipee_aucun_owner_effet(uid, vid, relic, aid, noms):
    """Le canal `unitAbilityStates` ne porte AUCUNE ligne de hierarchie 3 -> `tertiary_ability`
    reste `None` -> rien ne doit etre pose. Sans ce bras, une passe qui poserait
    INCONDITIONNELLEMENT (depuis le kit gameconfig, par exemple) passerait le bras positif."""
    st = _charger(relique=False)
    presents = _noms(st, uid)
    for nom in noms:
        assert nom not in presents, (
            f"{nom} pose SANS relique equipee sur {vid} -- la pose ne lit pas "
            f"`ctx.tertiary_ability` (presents : {presents})")


@pytest.mark.parametrize("uid,vid,relic,aid,noms", CAS,
                         ids=[c[2] for c in CAS])
def test_CONTRE_EPREUVE_la_passe_NEUTRALISEE_perd_la_pose(monkeypatch, uid, vid, relic, aid, noms):
    """La MUTATION qui doit MORDRE : on desarme la passe et on exige que l'etat reperde
    exactement ce qu'elle apporte. C'est ce qui distingue « la passe pose » de « quelqu'un
    d'autre posait deja ».

    ⚠ FORME B : on substitue l'attribut du MODULE `engine.runner.snapshot`, celui que `load_state`
    resout a l'appel -- une liaison `from ... import` gelee ne mordrait pas."""
    monkeypatch.setattr(SNAP, "_seed_tertiary_owner_effects", lambda state: 0)
    st = _charger()
    presents = _noms(st, uid)
    for nom in noms:
        assert nom not in presents, (
            f"{nom} est present alors que la passe est DESARMEE : le test ne mesure pas la passe "
            f"mais un autre chemin (presents : {presents})")


# --------------------------------------------------------------------------------------------
# Etage 3 -- le COUPLE baké, et les deux gates
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("uid,vid,relic,aid,noms", CAS,
                         ids=[c[2] for c in CAS])
def test_l_instance_posee_porte_le_couple_TERTIAIRE_pas_celui_des_passifs(uid, vid, relic, aid,
                                                                          noms):
    """`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultEffectBuilder(id, abilityState)`
    BAKE l'`AbilityStateReference` de l'ability QUI POSE. Pour une relique c'est l'etat TERTIAIRE
    (`level 1..10 / mult 100`, fabrique depuis `config+0xc0` / `config+0x78`), jamais celui des
    passifs (`50 / 180` en runner normalise) -- passer le couple passif lirait le dernier palier
    apres clamp (`Idun.Shared.Level$$ToZeroBasedIndex` clampe `idx >= len`)."""
    st = _charger()
    for nom in noms:
        inst = _inst(st, uid, nom)
        assert inst is not None, nom
        assert inst.ability_level == NIVEAU_TERTIAIRE, (
            f"{nom} : niveau {inst.ability_level} au lieu du TERTIAIRE {NIVEAU_TERTIAIRE}")
        assert inst.ability_variables_multiplier == MULT_TERTIAIRE, (
            f"{nom} : multiplicateur {inst.ability_variables_multiplier} au lieu du TERTIAIRE "
            f"{MULT_TERTIAIRE}")
    assert NIVEAU_TERTIAIRE != NIVEAU_PASSIF and MULT_TERTIAIRE != MULT_PASSIF, (
        "TEMOIN DEGENERE : les deux couples sont egaux, l'assertion ne discrimine rien")


@pytest.mark.parametrize("uid,vid,relic,aid,noms", CAS,
                         ids=[c[2] for c in CAS])
def test_GATE_niveau_verrouille_la_relique_n_est_PAS_montee(uid, vid, relic, aid, noms):
    """`0` = « verrouille / non debloque » (`Idun.Shared.Level$$CreateValidOrLockedLevel`), et
    `Idun.Shared.Level$$ToZeroBasedIndex` LEVE sur `<= 0`. Le gate vit deja dans
    `_load_tertiary_abilities` (qui refuse d'ingerer la ligne) : ce bras verifie que la pose n'a
    pas ouvert une seconde porte a cote."""
    st = _charger(niveau=0)
    presents = _noms(st, uid)
    for nom in noms:
        assert nom not in presents, f"{nom} pose sur une relique VERROUILLEE (niveau 0)"


@pytest.mark.parametrize("uid,vid,relic,aid,noms", CAS,
                         ids=[c[2] for c in CAS])
def test_GATE_deep_strike_les_passives_restent_DIFFEREES(uid, vid, relic, aid, noms):
    """`TeleportStrike_TeleportingIn` (1035) : une unite qui descend du ciel n'a pas ses passives
    initialisees -- elles sont differees a l'atterrissage
    (`spawn.initialize_deferred_actor_abilities`). C'est le MEME gate que la boucle de
    `_load_stats_and_effects` ; l'omettre poserait la relique un tour trop tot."""
    st = _charger(deep_strike=True)
    presents = _noms(st, uid)
    assert EffectType.TeleportStrike_TeleportingIn.name in presents, (
        "TEMOIN DEGENERE : le montage deep-strike n'a pas pose 1035, le gate n'est pas exerce")
    for nom in noms:
        assert nom not in presents, f"{nom} pose alors que {vid} est encore en deep-strike"


# --------------------------------------------------------------------------------------------
# Etage 4 -- IDEMPOTENCE : ce que le canal a deja capte n'est jamais double
# --------------------------------------------------------------------------------------------

def test_un_effet_DEJA_CAPTE_n_est_pas_double():
    """Le regime NOMINAL d'une relique dont la condition est VRAIE a la capture : l'effet arrive
    par `decisionView.effects` et la passe doit etre un NO-OP exact. Une pose non gardee
    creerait DEUX instances du meme owner-effect -- et un canal qui somme les verserait deux fois."""
    nom = "AmuletOfTheVoidwyrm_CritDamageReduction"
    st = _charger(effets_captes=(nom,))
    instances = [e for e in (st.effects.by_unit.get(KELERMORPH) or ()) if e.name == nom]
    assert len(instances) == 1, (
        f"{len(instances)} instances de {nom} -- la pose a double un effet deja capte")
