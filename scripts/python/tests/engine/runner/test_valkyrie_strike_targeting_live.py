"""#245 -- GARDE du masque de ciblage de ValkyrieStrike (1018, `astraSmnVoxcaster`).

Le masque est celui du PRESET STATIQUE `TargetingOptions` +0x1c0 recopie par
`IdunBattleLogic.Entities.Abilities.Active.Loki.ValkyrieStrikeAbility$$.ctor` (la 3e forme de ctor :
aucun appel a `IdunBattle.Core.Services.TargetingOptions$$.ctor`). Sa valeur EFFECTIVE est la
constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` =
`*(statics+0x1e8)` = `0x6000040` = `TargetIsTile | AllowObscuredTargetByElevation |
AllowObscuredTargetByWalls`. Detail complet : `docs/rl/case-245-valkyrie-strike-targeting.md`.

CE QUE CE TEST VERROUILLE, et pourquoi il ECHOUE sans le masque : la seule regle du masque qui
MORD offline est `TargetIsTile` -- « tuile-cible NON MARCHABLE » -> le natif rend le litteral `1`
(`TargetingRule.ValidRequest`, qu'il REUTILISE pour ce refus). Sans `TARGETING_OPTIONS`,
`get_invalid_target_reason` rend 0 sur la premiere ligne (`options is None` => aucun gate) : le
moteur ACCEPTE un cast que `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE.
Le test mesure les trois versions sur le MEME etat fige -- natif (oracle), port APRES, port AVANT
(`TARGETING_OPTIONS = None`, l'etat de `master`) -- et exige l'accord natif/APRES sur toutes les
lignes PLUS au moins une ligne ou AVANT « refusait de refuser ».

Montage : le porteur est un SUMMON sans summoner de heros (ses seuls poseurs gameconfig sont 4
`EnvFactionSummons:Armageddon*`, cote ENVIRONNEMENT), mais il est DEJA au catalogue `BC.Units` du
seed BC -> spawnable via `initAndStart(playerUnits=...)`. Deux champs de son entree sont amenages
(`Health`, et le trait `Summon` retire, qui desarme `CanStillBeUsed` et ferait court-circuiter
l'oracle) ; la justification detaillee, appuyee sur le decompile, est dans l'en-tete du probe.

Le montage et les QUATRE lectures vivent dans `scripts/python/probe_245_valkyrie_targeting.py` (le
probe MESURE, ce test GARDE) -- une seule implementation, aucune divergence possible entre les deux.
Lit l'etat LIVE, aucune RVA ni tuile hardcodee, ASCII only.

QUI ACCUSE QUI (#462-r6). Une seule fonction de test, mais TROIS natures d'assertion. (1) l'accord
natif / port APRES a pour sujet le PORT REEL : son echec accuse le moteur. (0), (2), (3) et (4) ont
pour sujet une MUTATION fabriquee ici ou le REGIME du montage : ils passent par
`counterproof.assert_counterproof` / `assert_sample_confrontable` et echouent sous les types
`InertCounterproof` / `UnconfrontableSample`. C'est pour ca que le marqueur porte sur l'ASSERTION et
non sur le test -- un `pytest.mark` au niveau du test serait FAUX ici.

CE FICHIER EST L'AUTRE CAS D'ECOLE : son contrefactuel retirait `TargetIsTile` du masque et exigeait
un FAUX-ACCEPT. Or le bit 6 est AUSSI le bit de DOMAINE (tete de cascade) : depuis l'elargissement
#253 (`a644607e`, porte DEUX HEURES apres cette tranche), une tuile VIDE rompt `TargetIsUnit` en
unit-targeting. Le port refusait donc toujours -- par une autre porte -- et le contre-controle est
devenu MASQUE. Le contrefactuel de SUFFISANCE utilise desormais le DESARMEMENT NATIF de la branche
(`AllowUnwalkableTargetTile`, bit 43), qui eteint ce refus et rien d'autre ; celui de NECESSITE
garde ce que le retrait du bit prouve REELLEMENT : l'accord natif/port CASSE.
"""
from __future__ import annotations

import pytest

import probe_245_valkyrie_targeting as P
from counterproof import assert_counterproof, assert_sample_confrontable
from engine.entities.pathfinding.board import Board

BOARD = "C3_26"     # 31 tuiles NON marchables sur 63 -> le regime refuse est largement exerce
SEED = 31337
TILES = 6           # echantillon par categorie (marchable / non marchable)


def _rpc(sid, method, body, timeout=90):
    return P._r(sid, method, body, timeout)


def test_valkyrie_strike_targeting_mask_matches_native(host, live_session):
    """Le gate de cible porte de 1018 == `AttackQuery.GetInvalidTargetReason` natif, et il REFUSE
    des tuiles que `master` (sans masque) acceptait."""
    sid = live_session
    rid, _added, _ab, state_file = P._build(sid, SEED, BOARD)
    try:
        dv, vox = P._to_my_turn(sid, rid)
        assert vox is not None, "Voxcaster absent du decisionView -- spawn KO"
        cid = int(vox["id"])
        assert P._ability_usable(sid, rid, cid), (
            "1018 non utilisable -> `GetInvalidTargetReason` court-circuite sur "
            "`ActiveAbility.CanCurrentlyBeUsed` et rend 0x1 pour la MAUVAISE raison : rien de "
            "mesurable (cf. l'en-tete du probe)")

        ob = _rpc(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = _rpc(sid, "boardGraph", {"runnerId": rid}, 90)
        assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indisponible"
        board = Board(bg["tiles"], adjacency="native_sym")

        allw = [t for t in bg["tiles"] if t.get("walkable")]
        allnw = [t for t in bg["tiles"] if not t.get("walkable")]
        assert_sample_confrontable(
            bool(allnw),
            mutation="board %s, choisi pour ses tuiles NON MARCHABLES" % BOARD,
            doit_casser="le regime REFUSE (`TargetIsTile` sur tuile non marchable) doit etre exerce",
            observe="0 tuile non marchable sur ce board",
            remede="changer de board : sans regime refuse le test ne garde RIEN -- pas un verdict.")
        walk = allw[::max(1, len(allw) // TILES)][:TILES]
        nowalk = allnw[::max(1, len(allnw) // TILES)][:TILES]

        cases = [("unit:%s" % u.get("visualId"), int(u["id"])) for u in (dv.get("units") or [])]
        cases += [("walk:%d,%d" % (t["col"], t["row"]), int(t["id"])) for t in walk]
        cases += [("nowalk:%d,%d" % (t["col"], t["row"]), int(t["id"])) for t in nowalk]

        rows = []
        for label, tid in cases:
            nat = _rpc(sid, "abilityReason",
                       {"runnerId": rid, "casterId": cid, "targetId": tid,
                        "abilityType": P.VALKYRIE_STRIKE}, 60)
            tr = (nat or {}).get("targetReason") or {}
            hexv = tr.get("hex")
            natv = int(hexv, 16) if isinstance(hexv, str) else (
                0 if tr.get("ruleClass") == "NoBrokenTargetingRule" else None)
            rows.append((label, tid, natv,
                         P._port_reason(dv, ob, snap, board, cid, tid, "apres"),
                         P._port_reason(dv, ob, snap, board, cid, tid, "avant")))

        print("\n[1018 targeting] caster=u%d board=%s seed=%d" % (cid, BOARD, SEED))
        for label, tid, natv, apres, avant in rows:
            print("  %-22s id=%-4d natif=%-6s apres=%-6s avant=%s"
                  % (label, tid, "-" if natv is None else hex(natv), hex(apres), hex(avant)))

        # 0) la garde anti-confusion du code 0x1 : au moins une tuile MARCHABLE est ACCEPTEE, donc
        #    le court-circuit d'ability ne mord pas et les 0x1 mesures viennent de `TargetIsTile`.
        assert_sample_confrontable(
            any(natv == 0 for label, _t, natv, *_ in rows if label.startswith("walk:")),
            mutation="echantillon de tuiles MARCHABLES interroge sur le meme etat fige",
            doit_casser="au moins une doit etre ACCEPTEE (0x0) par le natif",
            observe="aucune tuile marchable acceptee",
            remede="le court-circuit d'ability mord (`CanCurrentlyBeUsed` faux) : les 0x1 mesures "
                   "ne viennent PAS de `TargetIsTile` et ne prouvent rien. Re-monter le caster.")

        # 1) ASSERTION DE FOND -- accord natif / port APRES sur TOUTES les lignes. C'EST ELLE qui
        #    tombe quand `TARGETING_OPTIONS` disparait : le port rend 0 la ou le natif rend 0x1.
        #    Son echec accuse le PORT ; les trois autres accusent le SCENARIO.
        desaccords = [(label, hex(natv or 0), hex(apres))
                      for label, _t, natv, apres, _a in rows if natv != apres]
        assert not desaccords, "PORT : desaccord natif/port : %s" % desaccords

        # 2) CONTRE-CONTROLE -- le masque SERT : au moins une ligne ou le natif REFUSE et ou
        #    `master` (sans masque) rendait 0.
        gains = [label for label, _t, natv, _ap, avant in rows
                 if natv not in (None, 0) and avant == 0]
        assert_counterproof(
            bool(gains),
            mutation="variante AVANT = la MEME classe avec `TARGETING_OPTIONS = None` (l'etat de "
                     "`master` avant #245) -> aucun gate, `get_invalid_target_reason` rend 0",
            doit_casser="au moins une ligne ou le natif REFUSE doit etre faux-acceptee par AVANT",
            observe="0 ligne ou le masque change le verdict",
            remede="ce test passerait AUSSI sans `TARGETING_OPTIONS` : il ne garde rien. Re-crafter "
                   "l'echantillon (board avec tuiles non marchables atteignables) -- pas un verdict.")

        # 3) CONTREFACTUEL DE SUFFISANCE -- le DESARMEMENT NATIF de la branche etudiee : masque
        #    PLUS `AllowUnwalkableTargetTile` (bit 43), le gate meme du refus. Il eteint EXACTEMENT
        #    ce refus et rien d'autre -> faux-accept sur toutes les lignes refusees. Place APRES
        #    les assertions de fond, pour qu'un masque absent tombe sur (1), son vrai motif.
        faux_accepts = [label for label, tid, natv, _ap, _av in rows
                        if natv not in (None, 0)
                        and P._port_reason(dv, ob, snap, board, cid, tid, "desarme") == 0]
        assert_counterproof(
            len(faux_accepts) == len(gains),
            mutation="variante DESARME = masque | `AllowUnwalkableTargetTile` (bit 43), le gate "
                     "que le filtre statique lit dans la MEME branche que `TargetIsTile`",
            doit_casser="le refus : desarme, le port doit rendre 0 sur les lignes refusees",
            observe="%d faux-accept pour %d lignes refusees" % (len(faux_accepts), len(gains)),
            remede="si (1) passe, le port est sain et c'est une AUTRE porte de la cascade qui "
                   "refuse desormais ces lignes : le contrefactuel est MASQUE, le re-crafter sur "
                   "la porte reelle. Si (1) tombe, reclasser en rouge de PORT.")

        # 4) CONTREFACTUEL DE NECESSITE -- masque PRIVE de `TargetIsTile`. Il ne PEUT PAS servir a
        #    prouver le faux-accept : le bit 6 est aussi le bit de DOMAINE (tete de cascade), donc
        #    le retirer bascule l'ability en unit-targeting, ou une tuile VIDE rompt `TargetIsUnit`
        #    (elargissement #253, porte DEUX HEURES apres cette tranche -- c'est ce qui a rendu ce
        #    contre-controle inerte, mesure #462-r6). Ce qu'il garde reste juste : sans le bit,
        #    l'accord natif/port CASSE.
        accords_sans_tile = [label for label, tid, natv, _ap, _av in rows
                             if natv not in (None, 0)
                             and P._port_reason(dv, ob, snap, board, cid, tid, "sansTile") == natv]
        assert_counterproof(
            not accords_sans_tile,
            mutation="variante sansTile = masque & ~`TargetIsTile` (bit 6)",
            doit_casser="l'ACCORD natif/port : sans le bit, le port ne doit plus rendre le verdict "
                        "natif sur les lignes refusees",
            observe="%d ligne(s) ou sansTile rend ENCORE le verdict natif : %s"
                    % (len(accords_sans_tile), accords_sans_tile),
            remede="le bit 6 n'est plus necessaire au verdict -- une autre regle du masque rend le "
                   "meme code : re-crafter le contrefactuel sur la regle qui porte reellement, ou "
                   "reclasser si (1) tombe aussi.")
    finally:
        try:
            P._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
        finally:
            state_file.unlink(missing_ok=True)
