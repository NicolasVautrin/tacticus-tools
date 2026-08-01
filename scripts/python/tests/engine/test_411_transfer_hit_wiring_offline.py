"""#411 -- GARDE DE CABLAGE de `DealDamageInfo[+0x1D]` (le block GARANTI, 0 tirage).

Ce que verrouille ce fichier, et POURQUOI il est OFFLINE : les faits de RE qui rendent le residu
`+0x1D` de `case-407` §7 ACTIONNABLE se perissent en silence. Trois d'entre eux sont des DONNEES
(ids d'enum, porteurs, voie de montage) et le quatrieme est un INVARIANT DE PORT (si la mecanique
entre au registre, la route de garantie doit entrer avec elle).

RE (detail : `docs/rl/case-411-transfer-hit-guaranteed-block.md`) --

  L'ECRIVAIN de `+0x1D` est `IdunBattle.Operations.TransferHitOperation$$Execute`, qui remet a zero
  les 0x10 octets du `Nullable<IdunBattle.Core.AttackHit>` porte par le composant de l'unite CIBLE
  (`+0x98`). `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` a pose ce `PendingHit` juste
  avant d'emettre `EventTriggerType.PreAttackHit` (6) puis `PreAttackDamageHit` (7) ; il le RELIT
  apres, et sur `!HasValue` il met le degat a 0, arme le flag « never crit » du message (`+0x29`) et
  pose `DealDamageInfo[+0x1D] = 1`. `IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`
  route alors vers la surcharge `IdunBattle.Core.Services.DamageCalculations$$ApplyBlockDamage(
  blockChances, currentDamage)` (slot 4 d'`IDamageCalculations`, `currentDamage - blockChances[0]`
  puis `Math.Max(0, .)`) au lieu du couple `ApplyRandomEvasion` (slot 3) + `ApplyRandomBlockDamage`
  (slot 2) -- donc un block SANS AUCUN tirage, et `didBlock = 1` pose EN DUR.

  Les SEULS artefacts qui atteignent cet ecrivain sont les deux proprietaires DSL de
  `IdunBattleLogic.Entities.DSLBehaviors$$TransferHit` (xrefs entrantes, recoupees par
  `docs/rl/dsl-usage/dsl-usage-primitives.tsv` qui en compte EXACTEMENT 2) :
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DrawFireAbility` et
  `...PrimarchOfTheFirstLegionAbility`.

LE CRITERE QUE TIENT CE FICHIER, en une phrase --

  Tant que `DSLBehaviors$$TransferHit` est porte, la chaine d'EXECUTION qui va de la detection du
  porteur jusqu'a la route `ApplyBlockDamage` (slot 4) doit rester connectee de bout en bout : un
  coup transfere sort a 0 sur la cible ORIGINALE, pose `didBlock` en dur, ne consomme AUCUN tirage
  de block ni d'esquive, et le PORTEUR encaisse l'attaque relancee.

  La degradation qu'il interdit est SILENCIEUSE (aucune erreur, aucun crash) : un port qui roulerait
  quand meme le block d'un coup transfere consommerait des tirages que le natif ne consomme pas, et
  tout le flux RNG de l'attaque divergerait a partir de ce coup.

CE QUE CE FICHIER GARDAIT AVANT, ET POURQUOI C'ETAIT FAUX (#426, 2026-08-01) --

  Ecrit par `145c19c2` ALORS QUE LE PORT N'EXISTAIT PAS ENCORE, son invariant cherchait un
  `TRIGGERED_ABILITY_ID` valant 1109/1511 dans `ABILITY_TRIGGERS` / `CUSTOM_TRIGGERED_ABILITIES`,
  et skippait sinon. Le commit SUIVANT (`c24f226b`) a porte `DrawFire` -- mais par l'INTERCEPTEUR
  per-coup d'`ExecuteHit`, pas par le bus per-attaque, donc SANS jamais poser cet id dans ces
  registres. Le garde a continue de skipper, en VERT, sur un port bien vivant.

  Le vice n'est pas le mauvais registre : c'est qu'une empreinte de PRESENCE ne distingue pas
  « pas encore porte » de « porte et casse ». Ce fichier ne detecte donc plus par empreinte -- il
  EXECUTE le cablage (montage ECS reel, vrai `make_hit_interceptor`, vraie
  `AttackDamageOperation.execute`) et compare a un bras temoin. Le detecteur ne peut plus diverger
  du cablage, puisqu'il EST le cablage.

  Le skip reste possible, mais BRAS PAR BRAS : `1511 PrimarchOfTheFirstLegion` n'est pas porte
  (tache #418) et le dit tout seul, sans masquer le bras vivant.

Le PORT lui-meme (route slot 4, ordre transfert-avant-discard, comptage de tirages sur un
intercepteur factice) est garde par `test_411r1_transfer_port_offline.py`. Ce fichier-ci garde ce
que le factice ne peut pas voir : le MONTAGE et la DETECTION du porteur avec les vrais objets.
Confrontation live : `probe_411r1_transfer_port.py`.

ASCII only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PYDIR = Path(__file__).resolve().parents[2]
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

_SYMBOLS = Path(__file__).resolve().parents[4] / "data" / "symbols"


def _enums() -> dict:
    build = (_SYMBOLS / "CURRENT").read_text(encoding="utf-8").strip() if (
        _SYMBOLS / "CURRENT").exists() else None
    cand = [_SYMBOLS / build] if build else []
    cand += [p for p in sorted(_SYMBOLS.iterdir()) if p.is_dir()]
    for d in cand:
        f = d / "frida" / "enums.tsv"
        if f.exists():
            out = {}
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith("#") or "\t" not in line:
                    continue
                name, vals = line.split("\t", 1)
                out[name] = vals
            return out
    pytest.skip("table de symboles absente")


def _triggered_ability_ids() -> dict:
    vals = _enums().get("IdunBattle.Entities.Enum.TriggeredAbilityType")
    assert vals, "enum TriggeredAbilityType absente de enums.tsv"
    out = {}
    for kv in vals.split(","):
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        out[v] = int(k)
    return out


def test_les_deux_porteurs_dsl_de_transferhit_ont_leur_id_denum():
    """Les deux SEULS proprietaires de `DSLBehaviors$$TransferHit`, par leur `TriggeredAbilityType`.

    Ces ids sont ce qui relie le decompile au gameconfig et a `catalog_inject.graft_passive_ability`.
    Un renommage d'enum au prochain build casse ce test -- c'est exactement ce qu'on veut savoir."""
    ids = _triggered_ability_ids()
    assert ids.get("DrawFire") == 1109, ids.get("DrawFire")
    assert ids.get("PrimarchOfTheFirstLegion") == 1511, ids.get("PrimarchOfTheFirstLegion")


def test_les_porteurs_dunites_sont_ceux_mesures():
    """Les porteurs, derives du gameconfig (pas d'une liste ecrite a la main).

    MESURE (`unit_map find --ability`, build `rnca9r7q6c`) : `DrawFire` -> `blackNpc2Terminator`
    (npc) + `blackSmnTerminator` (SUMMON) ; `PrimarchOfTheFirstLegion` -> `darkaBossLion` (npc).
    Aucun HERO, aucune MoW, aucune relique : les trois etats de la gate relique ne s'appliquent pas,
    et la seule voie de confrontation est la GREFFE du passif (`case-92` §5bis volet passif) --
    ce que le test suivant verrouille."""
    import gameconfig as GC
    units = GC._index()
    carriers = {}
    for bucket in ("lineup", "npc", "summons"):
        for uid, u in (units.get(bucket) or {}).items():
            for ab in ((u or {}).get("passiveAbilities") or []) + (
                    (u or {}).get("activeAbilities") or []):
                carriers.setdefault(ab, set()).add(uid)
    assert carriers.get("DrawFire") == {"blackNpc2Terminator", "blackSmnTerminator"}, \
        sorted(carriers.get("DrawFire") or [])
    assert carriers.get("PrimarchOfTheFirstLegion") == {"darkaBossLion"}, \
        sorted(carriers.get("PrimarchOfTheFirstLegion") or [])


def test_le_summon_drawfire_na_pas_dinvocateur_dunite():
    """`blackSmnTerminator` est declare par `EnvFactionSummons:BlackLegion`, une ability
    d'ENVIRONNEMENT que PORTE aucune unite du catalogue.

    C'est le point qui interdit la voie « spawner l'invocateur » de la gate de confrontabilite
    (`case-92` §5bis recours 1 et 2) et impose le recours 3 (GREFFE). Le balayage est fait ici, pas
    suppose : on cherche l'ability qui declare ce summon, PUIS qui la porte."""
    import gameconfig as GC
    units = GC._index()
    decl = [name for name, ab in (units.get("abilities") or {}).items()
            if ((ab or {}).get("constants") or {}).get("unitId") == "blackSmnTerminator"]
    assert decl == ["EnvFactionSummons:BlackLegion"], decl
    holders = [uid for bucket in ("lineup", "npc", "summons")
               for uid, u in (units.get(bucket) or {}).items()
               if decl[0] in (((u or {}).get("passiveAbilities") or [])
                              + ((u or {}).get("activeAbilities") or []))]
    assert holders == [], holders


def test_le_montage_de_greffe_ecrit_bien_les_deux_entrees(tmp_path):
    """La voie de confrontation MESUREE par `probe_411_transfer_hit_guaranteed_block.py`.

    `catalog_inject.graft_passive_ability` doit poser LES DEUX ecritures -- `BC.Units[].
    PassiveAbilities = [1109]` (ce que monte `IdunBattle.Entities.Factories.UnitFactory$$
    AddConfiguredAbilities`) ET `BC.Abilities.PassiveAbilities['DrawFire']` (sans quoi la
    construction de l'arbre DSL du passif LEVE au deploiement). Le test verrouille le montage
    lui-meme : c'est lui qui a produit 6597/0 -> 3153/3488 en live."""
    import catalog_inject as CI
    out = tmp_path / "drawfire-grafted-bc.json"
    path, reports = CI.write_grafted_seed_bc(str(out), ["astraCreed:DrawFire"])
    assert reports[0]["abilityId"] == 1109, reports
    assert reports[0]["passiveAbilitiesAfter"] == [1109], reports
    bc = json.loads(Path(path).read_text(encoding="utf-8"))
    assert "DrawFire" in ((bc.get("Abilities") or {}).get("PassiveAbilities") or {})
    hit = [u for u in bc["Units"] if u["Id"] == "astraCreed"]
    assert hit and hit[0]["PassiveAbilities"] == [1109], hit[:1]


# =============================================================================================
# LE DETECTEUR -- les DEUX bouts du cablage, cherches SEPAREMENT
# =============================================================================================

def _draw_fire_wiring() -> dict:
    """Les deux bouts du cablage de `1109 DrawFire`, cherches INDEPENDAMMENT l'un de l'autre.

      * `relance`  -- l'artefact de port de l'ability : `DrawFireTransfer`, le mirror de
        `DSLBehaviors$$TransferHit` + `TransferHitOperation$$Execute` (detection du porteur par les
        cinq gates de `CreateTrigger`, puis re-entree dans `AttackDamageOperation`) ;
      * `accroche` -- le point ou `ExecuteHit` le CONSOMME : `should_transfer` sur l'intercepteur
        per-coup, appele par `operations/damage_hits.py`.

    Pourquoi SEPAREMENT : c'est ce qui rend le verdict a trois etats au lieu de deux.
      - les DEUX absents  -> le port n'existe pas (ou a ete retire en entier) : skip LEGITIME ;
      - UN SEUL present   -> le cablage est ROMPU : le fichier ROUGIT (c'est exactement le cas que
        l'ancien detecteur rendait indistinguable du precedent, et en VERT) ;
      - les DEUX presents -> on EXECUTE la chaine et on l'eprouve contre un bras temoin.

    On ne lit AUCUN registre : `DrawFire` se declenche PAR COUP et n'entre donc dans aucun des deux
    dictionnaires de `triggers/dispatch/registry.py` -- c'est precisement la voie que #366-r1 a
    ouverte pour le `discard` d'`HarlequinsPanoply`."""
    out = {}
    try:
        from engine.runner.operations.triggers.loki.draw_fire import DrawFireTransfer
        out["relance"] = DrawFireTransfer
    except ImportError:
        pass
    try:
        from engine.runner.operations.triggers.loki.harlequins_panoply import (
            HarlequinsPanoplyHitInterceptor)
        if hasattr(HarlequinsPanoplyHitInterceptor, "should_transfer"):
            out["accroche"] = HarlequinsPanoplyHitInterceptor.should_transfer
    except ImportError:
        pass
    return out


def _require_draw_fire_wiring() -> dict:
    """Le gate des tests d'execution ci-dessous. Skip UNIQUEMENT sur l'absence TOTALE, et le message
    ne nomme QUE 1109 -- il ne dit RIEN de 1511, qui a son propre bras."""
    w = _draw_fire_wiring()
    if not w:
        pytest.skip("1109 DrawFire NON PORTE -- aucun des deux bouts du cablage n'existe "
                    "(ni DrawFireTransfer, ni should_transfer). Le bras 1511 est independant.")
    assert set(w) == {"relance", "accroche"}, (
        "CABLAGE ROMPU de 1109 DrawFire : seul %s est present. Un coup transfere ne prendrait "
        "plus la route ApplyBlockDamage (slot 4) et roulerait son block -- desynchronisant tout "
        "le flux RNG de l'attaque a partir de ce coup." % sorted(w))
    return w


# =============================================================================================
# LE MONTAGE -- un `State` ECS reel, pas un intercepteur factice
# =============================================================================================

_ATTACKER_VID = "necroWarden"
_CARRIER_VID = "blackNpc2Terminator"       # porteur MESURE de DrawFire (cf. le test des porteurs)
_HITS = 6                                  # index impairs 1, 3, 5 -> `AmountIsOdd(CurrentHitIndex)`
_HP = 10 ** 7                              # aucune mort : le compte de tirages reste structurel
_COLS = _ROWS = 7
_DEFENDER_POS = (2, 3)
_ADJACENT_POS = (2, 2)                     # voisin hex evenq de `_DEFENDER_POS`
_FARAWAY_POS = (6, 6)


def _board():
    """⚠ INDISPENSABLE, et c'est un piege MESURE : `IsAdjacent(Owner, Target)` passe par
    `_is_adjacent_units`, qui rend `False` des que `state.board is None`. Un montage sans board
    rendrait le transfert MUET -- et ce fichier reproduirait, en vert, le defaut qu'il corrige."""
    import hexgeo
    from engine.entities.pathfinding.board import Board
    tiles = []
    for col in range(_COLS):
        for row in range(_ROWS):
            nb = [c * _ROWS + r + 1 for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < _COLS and 0 <= r < _ROWS]
            tiles.append({"id": col * _ROWS + row + 1, "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tiles, adjacency="evenq")


def _scene(carrier_pos=_ADJACENT_POS, carrier_vid=_CARRIER_VID, block_chance: int = 0):
    """`(state, attaquant, defenseur, porteur)`.

    L'attaquant est ENNEMI du defenseur (`AreEnemies(Caster, Target)`), le porteur est son ALLIE
    (`AreFriends`) et n'est pas lui-meme (`!AreEqual`). `carrier_pos` pilote le dernier gate,
    `IsAdjacent` -- c'est le levier des bras temoins.

    `carrier_vid` porte la detection : `_carries_draw_fire` derive les passives du gameconfig par
    `visualId` quand le canal live n'a pas parle, donc le VRAI porteur mesure suffit -- aucune
    greffe, aucun champ force.

    `block_chance` arme le defenseur d'une source de block, ce qui rend la ROUTE observable au
    compteur du MT (chemin ordinaire : 1 chaine de tirages par coup ; route garantie : aucune)."""
    from engine.entities.effects_state import EffectsState
    from engine.entities.stats import StatType, UnitStats
    from engine.entities.unit_context import UnitContext
    from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                          StatsComponent, UnitComponent)
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.state import State

    st = State()
    st.effects = EffectsState.seed({})
    st.rng = IntBasedMersenneTwister(777)
    st.board = _board()

    def _unit(vid, pos, team, attack, hits, blk=0):
        e = st.add_entity()
        e.add_component(UnitComponent(visual_id=vid, alive=True))
        e.add_component(OwnerComponent(team=team, player=(3 if team == 1 else 4)))
        e.add_component(PositionComponent(col=pos[0], row=pos[1]))
        e.add_component(HealthComponent(hp=_HP, hp_max=_HP))
        stats = UnitStats()
        stats.ensure_seeded(StatType.ATTACK, int(attack))
        stats.ensure_seeded(StatType.EXTRA_HITS, int(hits) - 1)
        stats.ensure_seeded(StatType.BLOCK_CHANCE, int(blk))
        stats.ensure_seeded(StatType.BLOCK_DAMAGE, 10 if blk else 0)
        for s in (StatType.FIXED_ARMOR, StatType.CRIT_CHANCE, StatType.CRIT_DAMAGE):
            stats.ensure_seeded(s, 0)
        e.add_component(StatsComponent(ctx=UnitContext(
            entity_id=e.id, visual_id=vid, active_ability_level=50, passive_ability_level=50,
            ability_variables_multiplier=100, stats=stats)))
        return e.id

    att = _unit(_ATTACKER_VID, (1, 3), 2, 1000, _HITS)
    dfd = _unit(_ATTACKER_VID, _DEFENDER_POS, 1, 10, 1, blk=block_chance)
    car = _unit(carrier_vid, carrier_pos, 1, 10, 1)
    return st, att, dfd, car


def _hp(state, uid: int) -> int:
    from engine.runner.components import HealthComponent
    return int(state.get_entity(int(uid)).get_component(HealthComponent).hp)


def _attack(carrier_pos=_ADJACENT_POS, carrier_vid=_CARRIER_VID, block_chance: int = 0) -> dict:
    """Joue UNE attaque normale complete et rend ce qui est observable de la route."""
    from engine.runner.operations.damage import AttackDamageOperation
    st, att, dfd, car = _scene(carrier_pos, carrier_vid, block_chance)
    draws0, hp_def0, hp_car0 = st.rng.call_count, _hp(st, dfd), _hp(st, car)
    r = AttackDamageOperation.execute(st, att, dfd)
    assert r is not None, "montage incomplet : l'attaque n'a pas tourne"
    assert int(r.get("hits") or 0) == _HITS, (
        "le montage doit produire %d coups (index impairs) -- lu %s" % (_HITS, r.get("hits")))
    return {"per_hit": list(r.get("per_hit") or []), "did_block": bool(r.get("did_block")),
            "draws": st.rng.call_count - draws0,
            "degat_defenseur": hp_def0 - _hp(st, dfd),
            "degat_porteur": hp_car0 - _hp(st, car)}


# =============================================================================================
# BRAS 1109 -- le cablage EXECUTE
# =============================================================================================

def test_1109_le_montage_arme_bien_les_cinq_gates_de_CreateTrigger():
    """Garde du MONTAGE lui-meme, avant toute conclusion. Un bras temoin qui echouerait pour une
    RAISON DE MONTAGE (porteur non reconnu, board absent, teams inversees) rendrait tous les tests
    suivants verts pour rien -- c'est le mode d'echec exact que ce fichier corrige."""
    _require_draw_fire_wiring()
    from engine.runner.operations.triggers.base import _is_adjacent_units
    from engine.runner.operations.triggers.loki.draw_fire import (_carries_draw_fire,
                                                                  find_transfer_carrier)
    from engine.runner.components import OwnerComponent
    st, att, dfd, car = _scene()
    assert _carries_draw_fire(st, car) is True, "le porteur n'est pas reconnu par le gameconfig"
    assert _carries_draw_fire(st, dfd) is False, "le defenseur ne doit PAS porter le passif"
    assert _is_adjacent_units(st, car, dfd) is True, "IsAdjacent(Owner, Target) : montage faux"
    t = lambda u: st.get_entity(u).get_component(OwnerComponent).team
    assert t(car) == t(dfd) != t(att), "AreFriends(Owner, Target) & AreEnemies(Caster, Target)"
    assert find_transfer_carrier(st, att, dfd) == car


def test_1109_lintercepteur_REEL_repond_sur_la_parite_du_coup():
    """Le maillon que l'intercepteur FACTICE de `test_411r1_transfer_port_offline.py` ne peut pas
    voir : `make_hit_interceptor` -> `HarlequinsPanoplyHitInterceptor.__init__` monte le
    `DrawFireTransfer` INCONDITIONNELLEMENT (le porteur est un ALLIE du defenseur, pas le
    defenseur), et `should_transfer` lui delegue.

    `AmountIsOdd(CurrentHitIndex)`, 0-based : impair OUI, pair NON."""
    _require_draw_fire_wiring()
    from engine.runner.operations.triggers.loki.harlequins_panoply import make_hit_interceptor
    st, att, dfd, _ = _scene()
    icept = make_hit_interceptor(st, att, dfd)
    assert icept is not None, "aucun intercepteur monte : `_run_hits` n'aurait rien a consulter"
    assert icept.should_transfer(1) is True, "index IMPAIR : le transfert doit avoir lieu"
    assert icept.should_transfer(0) is False, "index PAIR : `AmountIsOdd` interdit le transfert"
    # bras temoin sur le MEME maillon : sans porteur adjacent, le meme appel doit se taire.
    st2, att2, dfd2, _ = _scene(carrier_pos=_FARAWAY_POS)
    assert make_hit_interceptor(st2, att2, dfd2).should_transfer(1) is False


def test_1109_le_cablage_est_CONNECTE_de_bout_en_bout():
    """LA garde. Attaque complete, vrais objets, aucun test-double : les coups d'index IMPAIR
    sortent a 0 sur la cible ORIGINALE (relecture `!HasValue` -> degat 0) et le PORTEUR encaisse
    l'attaque relancee par `TransferHitOperation$$Execute`.

    Rompre N'IMPORTE LEQUEL des maillons -- montage du `DrawFireTransfer`, delegation de
    `should_transfer`, appel depuis `damage_hits._transferred` -- fait tomber ce test."""
    _require_draw_fire_wiring()
    r = _attack()
    zeros = [i for i, v in enumerate(r["per_hit"]) if v == 0]
    assert zeros == [1, 3, 5], (
        "coups transferes attendus aux index impairs, lus %s (per_hit=%s)" % (zeros, r["per_hit"]))
    assert all(r["per_hit"][i] > 0 for i in (0, 2, 4)), r["per_hit"]
    assert r["degat_porteur"] > 0, (
        "le porteur n'a RIEN encaisse : la relance de `TransferHitOperation$$Execute` est morte")


def test_1109_les_bras_temoins_reprennent_le_chemin_ORDINAIRE():
    """DISCRIMINANCE -- sans elle, un port colle a « transfere toujours » passerait le test
    precedent. Les deux gates qu'on relache un par un :
      * `IsAdjacent(Owner, Target)` : le meme porteur, deplace hors de portee ;
      * la detection du passif : une unite adjacente qui ne porte PAS `DrawFire`.
    Dans les deux cas : aucun coup a 0, aucun degat sur le tiers, et le total encaisse par le
    defenseur DOIT etre superieur (il prend les six coups au lieu de trois)."""
    _require_draw_fire_wiring()
    plein = _attack()
    for label, kw in (("porteur HORS de portee", {"carrier_pos": _FARAWAY_POS}),
                      ("voisin NON porteur", {"carrier_vid": _ATTACKER_VID})):
        r = _attack(**kw)
        assert all(v > 0 for v in r["per_hit"]), "%s : un coup est sorti a 0 -- %s" % (
            label, r["per_hit"])
        assert r["degat_porteur"] == 0, "%s : le tiers a encaisse %d" % (label, r["degat_porteur"])
        assert r["did_block"] is False, "%s : `didBlock` pose sans source de block" % label
        assert r["degat_defenseur"] > plein["degat_defenseur"], (
            "%s : le defenseur devrait prendre PLUS que sous transfert (%d vs %d)"
            % (label, r["degat_defenseur"], plein["degat_defenseur"]))


def test_1109_un_coup_transfere_pose_didBlock_SANS_aucune_source_de_block():
    """`didBlock = 1` est pose EN DUR par la branche `damageInfo[+0x1D] != 0`. Le montage n'arme
    AUCUNE source de block : sur le chemin ordinaire `did_block` ne peut donc pas etre vrai. Le
    voir vrai ici, et faux au temoin, prouve que la route slot 4 est bien celle qui a ete prise."""
    _require_draw_fire_wiring()
    assert _attack(block_chance=0)["did_block"] is True
    assert _attack(carrier_pos=_FARAWAY_POS, block_chance=0)["did_block"] is False


def test_1109_les_coups_transferes_ne_consomment_AUCUN_tirage_de_block():
    """LA propriete de CONSOMMATION -- celle dont la violation serait invisible autrement.

    On mesure ce que COUTE l'armement d'une source de block, sur chacun des deux bras :
      * bras TEMOIN   : les 6 coups roulent leur block  -> surcout = 6 chaines ;
      * bras TRANSFERT: seuls les 3 coups PAIRS roulent -> surcout = 3 chaines, soit la MOITIE.
    Le rapport est mesure, pas suppose : on ne code en dur ni le cout d'une chaine ni un total.

    Si les coups transferes roulaient leur block (slots 2/3) au lieu de prendre `ApplyBlockDamage`
    (slot 4), les deux surcouts seraient EGAUX -- et le flux RNG de l'attaque divergerait du natif
    a partir du premier coup transfere."""
    _require_draw_fire_wiring()
    surcout_temoin = (_attack(carrier_pos=_FARAWAY_POS, block_chance=100)["draws"]
                      - _attack(carrier_pos=_FARAWAY_POS)["draws"])
    surcout_transfert = (_attack(block_chance=100)["draws"] - _attack()["draws"])
    assert surcout_temoin > 0, "regime NON discriminant : armer le block ne coute rien"
    assert surcout_transfert * 2 == surcout_temoin, (
        "coups transferes : surcout de block %d, attendu %d (la moitie des %d du temoin) ; "
        "l'egalite signifierait qu'ils roulent leur block comme les autres"
        % (surcout_transfert, surcout_temoin // 2, surcout_temoin))


# =============================================================================================
# BRAS 1511 -- non porte, et il le dit TOUT SEUL
# =============================================================================================

def test_1511_reste_NON_PORTE_et_le_dit_sans_masquer_le_bras_1109():
    """Le SECOND proprietaire de `DSLBehaviors$$TransferHit`. Son `transferTarget` sort d'un
    `AdjacentFriends -> UnitsFromFaction(0xa) -> Randomize -> SortByFormula -> First` : le
    `Randomize` CONSOMME du RNG et l'ordre du pool n'est pas lu, donc le porter serait SPECULATIF.
    Il a sa propre tache (#418).

    Ce bras est SEPARE a dessein : c'etait le defaut de structure du garde d'origine, qui fondait
    les deux ids dans un `pytest.skip` unique -- si bien que le residu 1511 masquait le port 1109
    bien vivant. Ici, le skip ne nomme QUE 1511 et n'empeche RIEN au-dessus.

    Le jour ou 1511 entre, ce test ROUGIT et demande son bras d'EXECUTION (pas une empreinte)."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    assert int(TriggeredAbilityType.PrimarchOfTheFirstLegion) == 1511
    from engine.runner.operations.triggers.dispatch.registry import (ABILITY_TRIGGERS,
                                                                     CUSTOM_TRIGGERED_ABILITIES)
    import engine.runner.operations.triggers.loki.draw_fire as DF
    trouve = [getattr(cls, "__name__", str(cls))
              for classes in list(ABILITY_TRIGGERS.values()) + list(CUSTOM_TRIGGERED_ABILITIES.values())
              for cls in classes if getattr(cls, "TRIGGERED_ABILITY_ID", None) == 1511]
    trouve += [n for n in ("PrimarchOfTheFirstLegionTransfer",) if hasattr(DF, n)]
    assert not trouve, (
        "1511 PrimarchOfTheFirstLegion est desormais porte (%s) : ce bras doit passer du skip a "
        "un test d'EXECUTION -- meme forme que les tests 1109 ci-dessus, avec le pool de son "
        "`Randomize`. Ne PAS se contenter de retirer le skip." % trouve)
    pytest.skip("1511 PrimarchOfTheFirstLegion NON PORTE (tache #418) -- `Randomize` non lu. "
                "Le bras 1109 ci-dessus, lui, est EXECUTE : ce skip ne le masque pas.")
