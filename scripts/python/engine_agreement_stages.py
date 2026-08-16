#!/usr/bin/env python
"""Étape 1 réconciliation live/offline — agreement DÉCOMPOSÉ PAR ÉTAGE (diagnostic pur).

Le % d'agreement d'`engine_validate` est OPAQUE : un miss peut venir de la PRÉDICTION
(le dégât estimé diverge), de l'UTILITÉ (formule/termes), de l'ÉNUMÉRATION (la paire
native n'est pas dans notre candidat-set = trou de feed), du GATE (playbook offline
refuse), ou du MOVE-SCORING. Ce module branche une SONDE (`probe` de `run_agreement`)
qui, à chaque pas comparé, classe le hit/miss par étage :

  ÉTAGE PRÉDICTION — confrontation par paire (ability, cible), MÊME TUILE (la courante) :
    natif  = RPC `aiPlaybookPredict` (= `<Ability>Playbook.MakeDamagePredictions`, l'oracle
             que le scorer de DÉCISION consomme réellement — PAS le preview `aiPredict`) ;
    offline = `playbook.make_damage_predictions(ctx, origin, …)` (port PV).
    Mismatch -> re-test avec un prédicteur REBUILDÉ FRAIS à ce pas :
      fresh == natif  -> «prediction-feed»  (staleness du prédicteur cold, trou de feed) ;
      fresh != natif  -> «prediction-logic» (gap de formule, ex. defender-modifiers #40).
    La confrontation tourne AUSSI sur les HITS -> métrique de fidélité prédiction globale.

  CONTREFACTUEL — pour un miss d'ability : on réévalue l'utilité offline des DEUX paires
  (native et moteur) avec les PRÉDICTIONS NATIVES injectées (damage_composite sur les
  events natifs). Si la paire native repasse devant -> le miss est «prediction»
  (entièrement expliqué par l'étage prédiction) ; sinon -> «utility-logic» (résiduel).

  ⚠ UN RÉSIDUEL N'EST UN VERDICT QUE SI LES DEUX CÔTÉS ONT ÉTÉ SCORÉS. Quand le choix du
  MOTEUR n'a pas d'utilité offline (`base_eng is None`), le contrefactuel n'a PAS eu lieu :
  «utility-logic» accuserait alors la formule d'utilité — l'étage qu'on mesure exact par
  ailleurs. Ces cas sortent NOMMÉS, jamais fondus dans le résiduel :
    le moteur caste une ability NonComparable (hors formule 4-familles) -> «eng-nc-pair»
      (`nc-pair` plus haut ne teste que le côté NATIF — ce cas y échappait) ;
    tout autre défaut de scoring du choix moteur                        -> «eng-unscored».
  Mesuré le 2026-08-16 (777+909) : les 2 «utility-logic» du lot étaient CE cas — u81, natif
  69 vs moteur 1129, avec `u_off_eng_choice = null` et `cf.eng = null`.

  ÉTAGE UTILITÉ (#45b') — confrontation par paire, MÊME TUILE, hits inclus :
    natif   = RPC `pairUtility` (= `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions` invoqué en direct — la valeur EXACTE que le bucket natif
              attribue à la paire, SANS le terme Tile(7) qui vit hors du scorer) ;
    offline = `_formula_pair_utility` : mirror 4-familles nourri des prédictions
              NATIVES (formule isolée — un mismatch est TOUJOURS «logic», la
              staleness/feed ayant déjà l'étage prédiction).
    Sous-produit sur un miss d'ability : si le scorer natif LUI-MÊME préfère la paire
    du MOTEUR (nat_u(native_pair) < nat_u(engine_pair)) -> «native-gate» : la décision
    native ne vient pas de l'utilité de paire (gate/éligibilité manqué offline —
    signature du cas 777 s15 stun, résolu par `battle_query.can_use_ability`) — au
    lieu du fourre-tout «utility-logic».

  ÉTAGE MOVE — pour un miss de move PUR (natif ET moteur ont bougé sans caster) :
    T_native pas dans nos tuiles légales -> «move-enumeration» (feed) ;
    u_off(T_native) == u_off(T_engine)   -> «move-tie-break» ;
    u_off(T_native) <  u_off(T_engine)   -> «move-formula» (breakdown Tile7/MinDist loggé) ;
    u_off(T_native) >  u_off(T_engine)   -> «move-selection-anomaly» (argmax incohérent).
    Un chunk COMPOSÉ (move+ability) dont l'ability DIVERGE a sa position en aval de ce
    choix -> «pos-downstream-of-ability» (pas de double-comptage).

  ⚠ « EN AVAL DU CHOIX D'ABILITY » EXIGE QUE L'ABILITY DIVERGE. Quand les deux côtés castent
  la MÊME paire (ability, cible) et que seule la TUILE diffère, rien en amont n'explique
  l'écart : le court-circuit classait un miss réel sous une étiquette signifiant « déjà
  expliqué ailleurs » (mesuré 777 s8 u79 : 69→93 identique, position à 2 hexes). Ce n'est pas
  non plus du move PUR — la tuile sort du sweep de position de la PAIRE, pas de
  Tile(7)+MinDist. Échelle dédiée, à la paire commune, ORDRE LOAD-BEARING (elle écarte les
  causes DÉJÀ MESURÉES avant d'oser nommer l'argmax). `own` = nos prédictions, `cf` = les
  prédictions NATIVES injectées :
    T_nat hors du candidat-set offline -> «pos-pair-enumeration» (feed, jamais énumérée) ;
    une des quatre valeurs absente     -> «pos-pair-unscored» (non mesuré, PAS un verdict) ;
    own(T_nat) >  own(T_eng)           -> «pos-pair-selection-anomaly» (argmax VRAI : notre
                                          propre score préférait déjà la native) ;
    cf(T_nat)  >  cf(T_eng)            -> «pos-pair-prediction» (choix cohérent avec NOS
                                          prédictions ; c'est la prédiction qui est fausse —
                                          déjà compté à l'étage prédiction) ;
    cf égaux (tolérance)               -> «pos-pair-tie-break» ;
    sinon                              -> «pos-pair-formula» (bien prédit, on sur-score la nôtre).

  ⚠ CE PIÈGE A ÉTÉ TENDU PAR CE MODULE MÊME. La v1 de cette échelle ne comparait QUE `cf` et
  a rendu «pos-pair-selection-anomaly» sur 777 s8 u79 (146.479 vs 138.155) — un argmax accusé
  à tort. Le record d'ability du MÊME pas portait la réponse : `pred.match = false`,
  `kill off=false / nat=true` à la tuile native. Notre moteur ne voyait pas le kill, donc son
  choix était COHÉRENT ; l'écart n'existait que sous prédictions natives injectées. D'où
  `_pair_own_at` et l'ordre ci-dessus.

  Cas non décomposés v1 (comptés tels quels) : «nc-pair» (utilité NonComparable =
  heuristique entière), «generator-overfire» (le moteur caste là où le natif bouge).
  #45 : les familles heal (healEvents, #34A) et repair (repairs, décodage v2 du
  Dictionary `MakeRepairPredictions`) sont désormais confrontées quand la paire n'a pas
  de DamageEvent (magnitude offline vs fill natif) et contrefactualisées (fills natifs
  × HealUtility/RepairedAmountUtility) — «non-attack-oracle» ne reste que pour les
  vieux hooks sans décodeur.

LIMITE v1 (assumée, documentée) : `aiPlaybookPredict` prédit depuis la tuile COURANTE ;
la confrontation prédiction est donc contrôlée à position égale (formule), les termes
position-dépendants relèvent de l'étage utilité/move.

Usage :
  python engine_agreement_stages.py --runner N [--steps K] [--json out.json]
  python engine_agreement_stages.py --build --seeds 777,909 [--steps K] [-- <args rl_duel build>]
      (mode batch : construit un runner ISOLÉ par seed via `rl_duel build` — state-file
       DÉDIÉ data/_stages_duel_state.json, --board MC1_67 par défaut — le walke, le DISPOSE.)
Pré-requis : session Frida warmee (+ hooks avec les champs shieldDmg/forceOverkill du
décodeur ProbableDamageEvent — rebuild + reinject si anciens hooks ; dégrade proprement sinon).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
import host_inputs  # noqa: E402  (#273 : entrees gitignorees, resolution tri-etat)
import hexgeo  # noqa: E402
from engine import weights  # noqa: E402
from engine.playbook import noncomparable as playbooks  # noqa: E402
from engine.playbook import scene as _scene  # noqa: E402
from engine.playbook import get_playbook_or_default, tile_utility  # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK  # noqa: E402
from engine.playbook.prediction._shared import defender_prediction_block_amount  # noqa: E402  (#54A)
from engine.predict import (heal_amount_config, heal_utility,  # noqa: E402  (#45 confrontation
                            heal_amount_weapon,                # #45c : branche ARME REELLE
                            predict_heal_effective,            # heal/repair : familles 2 et 4 de
                            predict_repair_effective,          # CalculateUtilityFromPredictions
                            repair_amount_config, repair_amount_weapon,  # #45d : branche ARME repair
                            repair_utility)  # IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions)
from engine.utilities import damage_composite, tile_composite  # noqa: E402
from engine.utilities.tile import (terrain_tile_effects,  # noqa: E402  (covers terrain TileEffects, case-37)
                                   apply_tile_attributes,  # noqa: E402  (isTerritory / effectType, #175)
                                   triggered_abilities_attack_utility)  # noqa: E402  (feuille 2 attack, #45-s18)
from engine.utilities.move import MIN_DIST_UTILITY  # noqa: E402
from engine.ai import context as _ai_ctx  # noqa: E402
from engine.ai.action_generators import tile_leaf_ctx  # noqa: E402  (feuille TriggeredAbilities(2), case-36)
import engine_validate as EV  # noqa: E402  (run_agreement = SOURCE UNIQUE du walk)

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
# State-file DÉDIÉ (jamais data/duel_state.json : replace scope = ownership record).
STATE = ROOT / "logs" / "runners" / "_stages_duel_state.json"

# ── Diag « terme manquant » move (docs/rl/agreement-stages.md lead 7 + case-36) ──
# Le breakdown `move_terms` est AUTO-RÉFÉRENTIEL : il ne montre que les feuilles qu'on CALCULE.
# Une feuille droppée à 0 (utilities/tile.py TILE_LEAVES = None) ne peut donc jamais apparaître
# comme coupable → un `move-formula` est ambigu (formule fausse VS terme absent). Deux leviers :
#
# LEVER 1 (précondition OFFLINE, coût zéro, aucune capture) — modèle CORRIGÉ case-36 : le terme move
# `TriggeredAbilities(2)` = Σ sur les abilities DÉCLENCHÉES DU MOVER des playbooks
# `AdjacentUnitPreferenceTriggeredAbilityPlaybook` (poids config `TriggeredAbilities[<NOM>_Adjacent*]`
# × #amis adjacents à la tuile candidate). Les types ENREGISTRÉS (`engine/playbook/
# adjacent_unit_preference.TRIGGERED_MOVE_PLAYBOOKS`) sont désormais CALCULÉS par la feuille portée ;
# le suspect restant = un passif du mover dont une clé config `<NOM>_Adjacent*` existe mais dont le
# playbook n'est PAS ENCORE porté (~24 concrets restants) — `_suspect_trigger` le nomme + chiffre.
# (L'ancien set {1191,1165,1202} « carriers adjacents » était un FAUX modèle — coïncidence géométrique
# 909 s4/s19 : les amis adjacents à ces tuiles étaient justement ces 3 porteurs. Cf. case-36 résolution.)

# LEVER 3 (diff L3 natif ↔ offline) : mots-clés des feuilles move qu'on DROP à 0 (TILE_LEAVES=None)
# ou qu'on ne couvre que PARTIELLEMENT (TriggeredAbilities : seuls les playbooks enregistrés comptent).
# Un score natif L3 non nul dont le NOM matche = terme MANQUANT/PARTIEL nommé automatiquement.
_DROPPED_LEAF_KEYWORDS = ("Triggered", "UnitSpecificBehaviour", "RangedAdjacentEnemy")
# #273 : les traces L3 sont ecrites par le HOST (`frida/host/ai-trace-store.ts`,
# cwd = `frida/`) dans SON arbre, et `frida/data/` est gitignore. Un `ROOT /
# "frida" / "data" / "ai-traces"` construit depuis un worktree resolvait donc
# dans le vide, et `Path.glob` y rendait une liste vide SANS lever : LEVER 3
# s'eteignait en silence. `host_inputs` resout l'arbre du host et distingue
# « repertoire introuvable » (leve) de « aucun fichier pour ce sid » ([]).
_TRACES = "frida/data/ai-traces"


def _tile_of(ct):
    """(col,row) d'un `caseTile` d'event L3 ({tile:{col,row}} ou {col,row}). None sinon."""
    if isinstance(ct, dict):
        v = ct.get("tile") if isinstance(ct.get("tile"), dict) else ct
        if isinstance(v, dict) and v.get("col") is not None:
            return (v.get("col"), v.get("row"))
    return None


def _r(sid: int, method: str, body: dict, t: float = 90) -> dict:
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


# ── Confrontation prédiction : lecture des events natifs -> champs composite ────────────

def _fields_from_native_event(ev: dict, block_amount: int = 0) -> dict:
    """Champs composite Damage depuis un event NATIF d'`aiPlaybookPredict` (mirror de
    `ProbableDamageEvent.composite_fields`). willKillDmg/mightKillDmg = struct+0x24/+0x28
    = les bornes RAW (non capées HP) ; healthDmg = AccurateHealthDamage (capé) ;
    shieldDmg/limitedByMinHp/forceOverkill = champs AJOUTÉS au décodeur (hooks récents) —
    absents (vieux hooks) -> 0/False, comparaison bouclier sautée par l'appelant."""
    hp = ev.get("hpBefore") or 0
    raw_min = ev.get("willKillDmg") or 0
    raw_max = ev.get("mightKillDmg") or 0
    # #54A : le décodeur n'expose PAS `list[0]@0x50` (scénario « tous coups bloqués ») — on le
    # RECALCULE depuis le kit du défenseur (`block_amount`, cf. defender_prediction_block_amount) :
    # per-hit uniforme = raw_min // hits ; bmin = raw_min − hits × min(per, amount). killSure
    # (WillBeKill IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill) et DefinitelyOverkill le consomment ; kill (rawMax) inchangé.
    bmin = None
    _hits = int(ev.get("appliedHits") or 0) or 1
    if block_amount and int(block_amount) > 0:
        per = raw_min // _hits
        bmin = raw_min - _hits * min(per, int(block_amount))
    return {"hpBefore": hp, "shieldBefore": ev.get("shieldBefore") or 0,
            "healthDmgMin": min(ev.get("healthDmgMin") or 0, hp),
            "healthDmgMax": min(ev.get("healthDmgMax") or 0, hp),
            "rawHealthDmgMin": raw_min, "rawHealthDmgMax": raw_max,
            "forceOverkill": bool(ev.get("forceOverkill")),
            # #R34 : `MightCrit` (event+0xb9 = `DamagePredictionResult.MightCrit@+0xb1`) — le 3e
            # argument `isCritical` de `MightBeOverkill`. Sans cette cle, la formule offline
            # nourrie des predictions NATIVES sous-comptait `PossibleOverkill` (15.0 EXACT, mesure
            # probe_r34) sur tout attaquant `CouldCrit` face a une cible letale-sous-le-seuil ->
            # un ecart d'etage UTILITE classe « logic » alors que le feed etait bon.
            "mightCrit": bool(ev.get("mightCrit")),
            # #195 : `PreventOverkill` (event+0xBB = `DamagePredictionResult.PreventOverkill@+0xb3`)
            # -- le 5e argument `isPreventOverkill`, passe par les DEUX bornes (a la difference
            # d'`isCritical`). Sans cette cle, la formule offline nourrie des predictions NATIVES
            # SUR-comptait `PossibleOverkill` (15.0 EXACT, mesure probe_195) sur toute cible portant
            # `UnitFlag.PreventOverkill` -- un ecart d'etage UTILITE classe « logic » alors que le
            # feed etait bon, exactement le pendant de #R34 dans l'autre sens.
            "preventOverkill": bool(ev.get("preventOverkill")),
            "shieldDmgMin": ev.get("shieldDmgMin") or 0,
            "shieldDmgMax": ev.get("shieldDmgMax") or 0,
            "limitedByMinHp": bool(ev.get("limitedByMinHp")),
            "appliedHits": ev.get("appliedHits") or 0,
            "blockRawMin": bmin,
            "kill": hp <= raw_max, "killSure": hp <= (bmin if bmin is not None else raw_min)}


def _prediction_from_native_fields(f: dict):
    """#438 -- REMATERIALISE la struct `DamagePredictionResult` que le case natif porte
    (`IdunBattle.AI.Utilities.UtilityAttackCase$$ForDamagePrediction`, 4e argument, recopiee a
    `case@+0x28` sur 0xa8 octets), depuis les champs decodes de l'event natif.

    Seuls les TROIS champs que lisent les deux accesseurs du case sont peuplés -- `get_MightBeKill`
    (`CurrentHealth@0x00 <= rawMax@0x20`) et `get_WillBeKill` (gate `CannotBeGuaranteedKilled@0x89`
    puis `CurrentHealth <= BlockScenarios[0]`, sinon `rawMin@0x1c`). Le reste de la struct n'est lu
    par aucun playbook attack de ce build : le remplir a partir d'un decodeur partiel inventerait
    des valeurs.

    ⚠ `cannot_be_guaranteed_killed` reste a `False` : le decodeur `aiPlaybookPredict` ne publie pas
    ce flag, exactement comme `killSure` de `_fields_from_native_event` qui l'ignore aussi. Les deux
    voies partagent donc la MEME borne inferieure assumee (#372), pas deux verdicts differents."""
    from engine.services.damage_prediction import DamagePredictionResult
    from engine.services.min_max_damage import MinMaxDamage
    return DamagePredictionResult(
        current_health=int(f.get("hpBefore") or 0),
        raw_health_damage=MinMaxDamage(min=int(f.get("rawHealthDmgMin") or 0),
                                       max=int(f.get("rawHealthDmgMax") or 0)),
        block_raw_min=f.get("blockRawMin"))


_CMP_KEYS = ("healthDmgMin", "healthDmgMax", "rawHealthDmgMin", "rawHealthDmgMax",
             "kill", "killSure")
_CMP_SHIELD = ("shieldDmgMin", "shieldDmgMax")


def _pred_delta(off_f: dict, nat_f: dict, shield_ok: bool) -> dict:
    """Diff champ-à-champ des deux prédictions (main target). {} = MATCH."""
    keys = _CMP_KEYS + (_CMP_SHIELD if shield_ok else ())
    return {k: {"off": off_f.get(k), "nat": nat_f.get(k)}
            for k in keys if off_f.get(k) != nat_f.get(k)}


class StageProbe:
    """Sonde par-étage branchée sur `run_agreement(probe=...)` — accumule `self.records`."""

    def __init__(self, sid: int, rid: int, wt):
        self.sid = sid
        self.rid = rid
        self.wt = wt
        self.rpc = lambda m, b, t: _r(sid, m, b, t)
        self.records: list = []
        self._nat_events_cache: dict = {}   # {(step, uid, ab, tgt): events|None} — 1 RPC/paire/pas
        self._pu_cache: dict = {}           # {(step, uid, ab, tgt, tile): resp|None} — pairUtility (#45b')
        # LEVER 3 (opt-in --l3) : fenêtre seq de CE pas (events L3 émis par l'aiStepDryRun) + trace.
        self.l3 = False
        self._prev_seq = None
        self._seq_win = None
        self._trace_path = None

    # ---- côté natif : events décision (MakeDamagePredictions) ----
    def _native_resp(self, step: int, uid: int, ab: int, tgt: int, tile=None) -> dict | None:
        """Réponse BRUTE d'`aiPlaybookPredict` pour la paire, prédite DEPUIS `tile`
        (cachée) — porte les 4 familles du scorer (`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`) : events (damage) + healEvents + effectEvents + repairs (#45)."""
        key = (step, uid, ab, tgt, tile)
        if key in self._nat_events_cache:
            return self._nat_events_cache[key]
        body = {"runnerId": self.rid, "unitId": uid, "targetId": tgt, "abilityType": ab}
        if tile is not None:
            body["col"], body["row"] = int(tile[0]), int(tile[1])
        resp = self.rpc("aiPlaybookPredict", body, 60)
        resp = resp if resp.get("ok") else None
        self._nat_events_cache[key] = resp
        return resp

    def _native_events(self, step: int, uid: int, ab: int, tgt: int, tile=None):
        """Events DAMAGE natifs de la paire, prédits DEPUIS `tile` (UnitPosition à la
        tuile candidate, `GetUnitPositionAtTile` — ce que le sweep de décision natif
        évalue). tile None = tuile courante. Sans col/row, un chunk composé move+attack
        rendrait un faux 0 « hors de portée depuis la tuile courante » (piège seed 777)."""
        resp = self._native_resp(step, uid, ab, tgt, tile)
        return (resp.get("events") or []) if resp is not None else None

    # ---- côté offline : meilleur (u_full, tuile) d'une paire via le sweep du générateur ----
    def _pair_best_offline(self, ctx, ab: int, tgt: int):
        """Mirror du sweep par-paire de `ComparableAbilityGenerator._best_attack`.
        Renvoie {u_full, u, tile, pred} | "gated" (évals présentes, toutes tuiles refusées)
        | None (paire absente des evals = non énumérée offline)."""
        plan = ctx.plans.get(ctx.uid) or {}
        ev = next((e for e in (plan.get("evals") or [])
                   if e.get("abilityId") == ab and e.get("targetId") == tgt
                   and e.get("rankCount")), None)
        if ev is None:
            return None
        pb = NORMAL_ATTACK_PLAYBOOK if ab in ctx.normal_ids else get_playbook_or_default(ab)
        best = None
        for rk in (ev.get("ranked") or []):
            tile = (rk.get("col"), rk.get("row"))
            if tile[0] is None:
                continue
            cand = pb.calculate_action_utility(ctx, tile, tgt, ab)
            if cand is None:
                continue
            if best is None or cand["u_full"] > best["u_full"]:
                best = {"u_full": cand["u_full"], "u": cand["u"], "tile": tile,
                        "pred": cand["pred"]}
        return best if best is not None else "gated"

    # ---- utilité de la paire à UNE tuile, avec NOS PROPRES prédictions ----
    def _pair_own_at(self, ctx, ab: int, tgt: int, tile):
        """`u_full` de la paire à `tile` avec les prédictions du MOTEUR — le scoring qu'il a
        réellement appliqué au moment de décider. C'est le PENDANT de
        `_counterfactual_utility`, qui injecte les prédictions NATIVES : seul l'écart entre
        les deux distingue un argmax INCOHÉRENT (notre propre score préférait déjà la tuile
        native) d'un simple gap de PRÉDICTION (notre choix était cohérent avec ce qu'on
        prédisait, et c'est la prédiction qui est fausse)."""
        if tile is None or playbooks.is_noncomp(ab):
            return None
        pb = NORMAL_ATTACK_PLAYBOOK if ab in ctx.normal_ids else get_playbook_or_default(ab)
        cand = pb.calculate_action_utility(ctx, tile, tgt, ab)
        return None if cand is None else cand["u_full"]

    # ---- tuiles ÉNUMÉRÉES offline pour une paire (candidat-set du sweep) ----
    def _pair_ranked_tiles(self, ctx, ab: int, tgt: int):
        """Tuiles que le sweep offline a EFFECTIVEMENT énumérées pour la paire (`ranked` de
        l'eval attackPlans). `None` = paire absente des evals. Sans ce contrôle, une tuile
        jamais énumérée se lit comme un défaut d'argmax alors que c'est un trou de FEED."""
        plan = ctx.plans.get(ctx.uid) or {}
        ev = next((e for e in (plan.get("evals") or [])
                   if e.get("abilityId") == ab and e.get("targetId") == tgt
                   and e.get("rankCount")), None)
        if ev is None:
            return None
        return {(rk.get("col"), rk.get("row")) for rk in (ev.get("ranked") or [])
                if rk.get("col") is not None}

    # ---- confrontation prédiction (MÊME tuile des deux côtés = la tuile d'attaque) ----
    def _confront_prediction(self, ctx, dv, mov_by_unit, step: int, uid: int,
                             ab: int, tgt: int, tile) -> dict:
        """Confronte la prédiction offline à l'oracle décision natif (`aiPlaybookPredict`)
        DEPUIS LA MÊME TUILE `tile` (= la tuile d'attaque du chunk natif : move-to si
        composé, sinon la courante). Mismatch -> feed-vs-logic via prédicteur FRAIS."""
        if playbooks.is_noncomp(ab):
            return {"skipped": "nc-pair"}
        tile = tile if tile is not None else ctx.origin
        nat_evs = self._native_events(step, uid, ab, tgt, tile)
        if not nat_evs:
            fam = self._confront_nonattack(ctx, step, uid, ab, tgt, tile)
            if fam is not None:
                return fam                           # #45 : famille heal/repair confrontée
            return {"skipped": "no-native-events"}   # non-attaque non décodée ou RPC KO
        nat_main = next((e for e in nat_evs if e.get("targetId") == tgt), nat_evs[0])
        shield_ok = "shieldDmgMin" in nat_main       # champs récents du décodeur
        pb = NORMAL_ATTACK_PLAYBOOK if ab in ctx.normal_ids else get_playbook_or_default(ab)
        off_evs = pb.make_damage_predictions(ctx, tile, tgt, ab) or []
        off_main = next((e for e in off_evs if e.target == tgt), off_evs[0] if off_evs else None)
        if off_main is None:
            return {"match": False, "off": "empty", "nat_n": len(nat_evs),
                    "feed": None, "delta": None, "tile": tile}
        # #54A : killSure natif recompute avec le block du défenseur (le décodeur n'expose pas list[0])
        _blk = (defender_prediction_block_amount(ctx.scene, tgt)
                if getattr(ctx, "scene", None) is not None else 0)
        nat_f = _fields_from_native_event(nat_main, block_amount=_blk)
        delta = _pred_delta(off_main.composite_fields(), nat_f, shield_ok)
        out = {"match": not delta, "delta": delta or None, "tile": tile,
               "aoe": {"off": len(off_evs), "nat": len(nat_evs)}, "shield_ok": shield_ok}
        if delta:
            # feed vs logic : la MÊME formule offline, nourrie d'un prédicteur REBUILDÉ à ce pas.
            fresh = _scene.build_predictor(self.rpc, self.rid)
            if fresh is not None:
                ctx_f = _ai_ctx.build(self.rpc, self.rid, dv, mov_by_unit, uid, self.wt, fresh)
                f_evs = pb.make_damage_predictions(ctx_f, tile, tgt, ab) or []
                f_main = next((e for e in f_evs if e.target == tgt),
                              f_evs[0] if f_evs else None)
                f_delta = (_pred_delta(f_main.composite_fields(), nat_f, shield_ok)
                           if f_main is not None else {"off": "empty"})
                out["feed"] = not f_delta        # True = fresh matche -> staleness (feed)
                out["fresh_delta"] = f_delta or None
            else:
                out["feed"] = None               # combatSnapshot KO — inclassable
        return out

    # ---- #45 : confrontation des familles NON-damage (heal famille 2, repair famille 4) ----
    def _confront_nonattack(self, ctx, step: int, uid: int, ab: int, tgt: int,
                            tile) -> dict | None:
        """Confronte la MAGNITUDE offline (mirrors `IdunBattle.Core.Services.DamagePrediction$$PredictHeal` /
        `IdunBattle.Core.Services.DamagePrediction$$PredictRepair`) au fill NATIF décodé (`healEvents` #34A /
        `repairs` #45 v2) quand la paire n'a aucun DamageEvent — les familles 2 et 4
        du scorer `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`. None = famille absente
        (vieux hooks sans décodeur, ou paire réellement vide) -> l'appelant garde le
        skip v1 `no-native-events`. Mismatch = logic (feed=False) : la magnitude ne lit
        que l'état DU PAS (obs fraîche) + la config — pas de canal cold."""
        resp = self._native_resp(step, uid, ab, tgt, tile)
        if resp is None:
            return None
        hevs = resp.get("healEvents") or []
        reps = resp.get("repairs") or []
        ob = next((u for u in ctx.obs_units if u.get("squadId") == tgt), None)
        hp_max = int((ob or {}).get("hpMax") or 0)
        hp_cur = int((ob or {}).get("hp") or 0)
        hc = ctx.heal_config(ctx.uid)
        if hevs:
            nat = next((e for e in hevs if e.get("targetId") == tgt), hevs[0])
            amt = heal_amount_config(ctx.ab_name_by_id.get(ab), hc["active"],
                                     hc["passive"], hc["multiplier"])
            # #45c : pas de `hpToHeal` -> branche ARME REELLE (stat Damage du caster x
            # Max(WeaponHighestHits,1) — #55 : Hospitaller Heal(18) 3-hit = 2008x3=6024),
            # mirror du generateur heal (action_generators). Saturation = dernier filet.
            if amt is None and getattr(ctx, "scene", None) is not None:
                actx = ctx.scene.ctx(ctx.uid)
                if actx is not None:
                    amt = heal_amount_weapon(actx.attack, actx.normal_weapon_hits)
            missing = max(0, hp_max - hp_cur)
            off = missing if amt is None else predict_heal_effective(amt, hp_cur, hp_max)
            delta = ({} if int(off) == int(nat.get("healAmount") or 0) else
                     {"healAmount": {"off": int(off), "nat": nat.get("healAmount")}})
            return {"match": not delta, "delta": delta or None, "tile": tile,
                    "family": "heal", "feed": (False if delta else None)}
        if reps:
            nat = next((r for r in reps if r.get("targetId") == tgt), reps[0])
            vid = next((u.get("visualId") for u in ctx.obs_units
                        if u.get("squadId") == uid), None)
            amt = repair_amount_config(vid, hc["active"], hc["multiplier"])
            # #45d : pas de `hpToRepair` Comparable -> branche ARME REELLE de `RepairAbility$$
            # RepairAmount` (`Multiply(StatAmount(weapon), Max(WeaponHighestHits,1))`), le cas de
            # TOUS les porteurs du trait `Mechanic`. Mirror du generateur repair. Saturation =
            # dernier filet (Scene absente).
            if amt is None and getattr(ctx, "scene", None) is not None:
                actx = ctx.scene.ctx(ctx.uid)
                if actx is not None:
                    amt = repair_amount_weapon(actx.attack, actx.normal_weapon_hits)
            if amt is None:
                off_hp = max(0, hp_max - hp_cur)
            else:
                off_hp = predict_repair_effective(amt, hp_cur, hp_max).fill_hp
            delta = {}
            # ⚠ #276-r1 : le decodeur hooks de `RepairPredictionResult` lit 16 octets d'une struct
            # qui n'en fait que 8 (`ForRepairPrediction` stocke la valeur ENTIERE dans le
            # pointer-size ecrit a `case+0xdc`, et `PredictRepair` rend `CONCAT44(fill,
            # currentHealth)`). Seuls `+0x00`/`+0x04` sont dans la struct ; `hpFill`(+0x08) et
            # `armorFill`(+0x0c) sont HORS. `armorFill` n'est donc plus compare (le natif n'a
            # AUCUN volet Armor) ; `hpFill` reste confronte mais son cote NATIF est suspect tant
            # que le decodeur n'est pas corrige (tache #276-r1, exige un reinject).
            if int(off_hp) != int(nat.get("hpFill") or 0):
                delta["hpFill"] = {"off": int(off_hp), "nat": nat.get("hpFill")}
            return {"match": not delta, "delta": delta or None, "tile": tile,
                    "family": "repair", "feed": (False if delta else None)}
        return None

    # ---- #45b' : mirror OFFLINE du scorer de paire (4 familles, prédictions NATIVES) ----
    def _formula_pair_utility(self, ctx, step: int, uid: int, ab: int, tgt: int,
                              tile) -> float | None:
        """Mirror de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
        nourri des prédictions NATIVES (`aiPlaybookPredict`, MÊME tuile) — la formule
        ISOLÉE (tout écart au scorer natif = logic, jamais feed) :
          Σ damage (+0x358 : prob1×prob2 × ±damage_composite, friendly NÉGÉ,
                    `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent`)
        + Σ heal   (+0x368 : prob × HealUtility, `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromHealEvent`)
        + Σ repair (+0x388 : RepairedAmountUtility(fills), SANS facteur prob — mirror natif)
        SANS le terme Tile(7) (hors scorer : il vit dans le sweep de position) et SANS la
        famille effet (+0x378) : seul override du build = SpiritLeech, poids
        AddedTileEffects=0 -> contribution 0 des deux côtés (cf. probable_damage_event.py).
        Écart documenté : le CustomUtility TwistedScience (+100/+200) n'est pas modélisé.
        None = RPC KO ou paire sans aucune famille décodée (vieux hooks)."""
        resp = self._native_resp(step, uid, ab, tgt, tile)
        if resp is None:
            return None
        me = next((u for u in ctx.units if u.get("id") == uid), None)
        my_team = (me or {}).get("team")
        team_by_id = {u.get("id"): u.get("team") for u in ctx.units}
        u = None
        for ev in (resp.get("events") or []):
            t_id = ev.get("targetId")
            sign = -1.0 if (t_id is not None and team_by_id.get(t_id) == my_team) else 1.0
            prob = (ev.get("probability") or 1.0) * (ev.get("probMult") or 1.0)
            # #45-s18 : + feuille TriggeredAbilities(2) face ATTACK (splash Psyker) — le natif
            # l'évalue DANS ForDamagePrediction par event -> même prob x signe que le composite.
            _blk = (defender_prediction_block_amount(ctx.scene, t_id)
                    if getattr(ctx, "scene", None) is not None else 0)   # #54A block défenseur
            _f = _fields_from_native_event(ev, block_amount=_blk)
            # #438 : le case natif de CET event porte sa `DamagePrediction` -> on la rematerialise
            # depuis les champs decodes, sinon `BarbedOvipositorPlaybook` lirait `HasValue == false`
            # et rendrait 0 -- un ecart d'etage UTILITE classe « logic » alors que le feed est bon.
            u = (u or 0.0) + sign * prob * (
                damage_composite(_f, ctx.hpmax_by_id.get(t_id), ctx.wt)
                + triggered_abilities_attack_utility(
                    ctx, uid, ab, t_id, tile, prediction=_prediction_from_native_fields(_f)))
        for ev in (resp.get("healEvents") or []):
            t_id = ev.get("targetId")
            u = (u or 0.0) + (ev.get("probability") or 1.0) * heal_utility(
                int(ev.get("healAmount") or 0), int(ctx.hpmax_by_id.get(t_id) or 0),
                is_friend=(t_id is not None and team_by_id.get(t_id) == my_team),
                is_boss=False)
        for rp in (resp.get("repairs") or []):
            t_id = rp.get("targetId")
            ob = next((o for o in ctx.obs_units if o.get("squadId") == t_id), None) or {}
            # UN SEUL terme (#45d) : `RepairedAmountUtility` ne lit que `W[0]=100` sur le `fillUp`
            # de la struct 8 octets. `armorFill` du decodeur est HORS struct (#276-r1) -> ignore.
            u = (u or 0.0) + repair_utility(
                int(rp.get("hpFill") or 0), int(ob.get("hpMax") or 0), is_boss=False)
        return u

    # ---- contrefactuel : utilité offline avec prédictions NATIVES injectées ----
    def _counterfactual_utility(self, ctx, step: int, uid: int, ab: int, tgt: int,
                                tile) -> float | None:
        """L'utilité que NOTRE formule donnerait à la paire si notre prédiction était
        EXACTE (la native, même tuile) + Tile(7)@tile — la forme des candidats du
        générateur. Délègue le scorer de paire à `_formula_pair_utility` (#45b' :
        source UNIQUE, le même mirror sert à l'étage UTILITÉ — plus de drift possible
        entre contrefactuel et confrontation)."""
        u = self._formula_pair_utility(ctx, step, uid, ab, tgt,
                                       tile if tile is not None else ctx.origin)
        if u is None:
            return None
        return u + (tile_utility(ctx, tile) if tile is not None else 0.0)

    # ---- #45b' : ÉTAGE UTILITÉ — scorer natif invoqué vs formule offline, même tuile ----
    def _confront_utility(self, ctx, step: int, uid: int, ab: int, tgt: int,
                          tile) -> dict:
        """Confronte `_formula_pair_utility` (formule offline, prédictions natives) au
        scorer NATIF invoqué (RPC `pairUtility` = `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions` en direct, MÊME tuile). Prédictions natives des deux côtés ⇒ un
        mismatch chiffre un gap de FORMULE par famille (jamais un gap de feed).
        Tolérance : |delta| <= max(0.01, 0.1% de |natif|) (Fix64 Q32.32 + arrondis)."""
        if playbooks.is_noncomp(ab):
            return {"skipped": "nc-pair"}
        tile = tile if tile is not None else ctx.origin
        key = (step, uid, ab, tgt, tile)
        if key not in self._pu_cache:
            r = self.rpc("pairUtility",
                         {"runnerId": self.rid, "unitId": uid, "targetId": tgt,
                          "abilityType": ab, "col": int(tile[0]), "row": int(tile[1])}, 60)
            self._pu_cache[key] = r if r.get("ok") else {"error": r.get("error")}
        nat = self._pu_cache[key]
        if nat.get("utility") is None:
            return {"skipped": "rpc-ko", "error": nat.get("error")}
        off = self._formula_pair_utility(ctx, step, uid, ab, tgt, tile)
        if off is None:
            return {"skipped": "no-native-events", "nat": round(nat["utility"], 4)}
        delta = off - nat["utility"]
        resp = self._native_resp(step, uid, ab, tgt, tile) or {}
        fams = [f for f, k in (("damage", "events"), ("heal", "healEvents"),
                               ("effect", "effectEvents"), ("repair", "repairs"))
                if resp.get(k)]
        out = {"match": abs(delta) <= max(0.01, 0.001 * abs(nat["utility"])),
               "off": round(off, 4), "nat": round(nat["utility"], 4),
               "delta": round(delta, 4), "families": fams, "tile": tile}
        if nat.get("mutated"):
            out["mutated"] = True   # scorer censé être read-only — à investiguer si vu
        return out

    # ---- scoring move par-tuile (mirror best_move_faithful, tuiles ciblées) ----
    def _move_utils(self, ctx, tiles: list) -> dict:
        # Elevation(8) : min/max sur le BOARD ENTIER (LoadRelevantTileElevations, case-37), pas les candidats.
        board_elevs = [e for e in ctx.elev_by_pos.values() if e is not None]
        emax, emin = (max(board_elevs), min(board_elevs)) if board_elevs else (None, None)
        leaf_ctx = tile_leaf_ctx(ctx)   # TriggeredAbilities(2) : kit passif mover + fpos (case-36)
        out = {}
        for c in tiles:
            e = ctx.elev_by_pos.get(c)
            meta: dict = {"elevation": e, "elevation_max": emax, "elevation_min": emin} \
                if e is not None else {}
            if c in ctx.is_temporary_by_pos:
                meta["is_temporary"] = ctx.is_temporary_by_pos[c]
            # TileEffects(10) : effets DYNAMIQUES (tileMeta, Loop1) + covers HÉBERGÉS par le terrain
            # (Loop2 : DryBush->LightCover, case-37).
            _effs = list(ctx.effects_by_pos.get(c) or [])
            _effs += terrain_tile_effects(ctx.terrain_by_pos.get(c), _effs)   # #155 : canal dyn. passé
            if _effs:
                meta["effects"] = _effs
            # isTerritory / effects[].effectType (#175) — MEME complement que `engine.move` et
            # `playbook.base.tile_utility` : sans lui ce mirror de mesure divergerait du moteur.
            apply_tile_attributes(meta, c, leaf_ctx)
            tile_u = tile_composite(c, meta, leaf_ctx, ctx.wt)
            # `case=` : les 4 gates d'entree de la feuille (#236). Ce mirror de mesure DOIT le
            # passer, sinon il rendrait un terme la ou le moteur (et le natif) rend 0.
            mind_u = MIN_DIST_UTILITY.evaluate_movement(c, ctx.tgt_epos or ctx.epos, ctx.wt,
                                                        ctx.pathdist_by_pos, case=ctx.mindist_case)
            out[c] = {"tile": round(tile_u, 3), "mindist": round(mind_u, 3),
                      "u": round(tile_u + mind_u, 3),
                      "pathdist": ctx.pathdist_by_pos.get(c)}
        return out

    # ---- classification dimension ABILITY ----
    def _probe_ability(self, ctx, dv, mov_by_unit, step: int, uid: int, nat: dict,
                       eng: dict) -> dict:
        na = nat["ability"]
        ab, tgt = na["ability"], na["target"]
        eng_is_ab = eng.get("kind") == "ability"
        hit = (eng_is_ab and eng.get("ability") == ab
               and (eng.get("target") == tgt or playbooks.is_summon(ab)))
        rec = {"step": step, "uid": uid, "dim": "ability", "hit": hit,
               "native": {"ability": ab, "target": tgt},
               "engine": {"kind": eng.get("kind"), "ability": eng.get("ability"),
                          "target": eng.get("target")}}
        # Tuile d'attaque du chunk NATIF : move-to si composé, sinon la tuile courante —
        # la confrontation prédiction se fait à CETTE tuile, des deux côtés (à-position-égale).
        nat_tile = (nat["move"] or {}).get("to") or ctx.origin
        # Confrontation prédiction SYSTÉMATIQUE (hits inclus) -> fidélité prédiction globale.
        rec["pred"] = self._confront_prediction(ctx, dv, mov_by_unit, step, uid, ab, tgt,
                                                nat_tile)
        # #45b' : confrontation UTILITÉ systématique (hits inclus) -> fidélité formule globale.
        rec["util"] = self._confront_utility(ctx, step, uid, ab, tgt, nat_tile)
        if hit:
            rec["stage"] = "hit"
            return rec
        if playbooks.is_noncomp(ab):
            rec["stage"] = "nc-pair"
            return rec
        if rec["pred"].get("skipped") == "no-native-events":
            rec["stage"] = "non-attack-oracle"   # famille non décodée (vieux hooks sans #45 v2)
            return rec
        nat_pair = self._pair_best_offline(ctx, ab, tgt)
        if nat_pair is None:
            rec["stage"] = "enumeration"         # paire native absente des evals offline (feed)
            return rec
        if nat_pair == "gated":
            rec["stage"] = "gate"                # playbook offline refuse toutes les tuiles
            return rec
        rec["u_off_nat_pair"] = round(nat_pair["u_full"], 3)
        # Utilité offline du CHOIX du moteur : sweep par-paire pour une attaque Comparable ;
        # pour un choix heal/repair/bespoke (paire hors attackPlans), reconstruction depuis
        # l'action émise (full = util(pred) + Tile(7)@to — la forme des candidats du générateur).
        u_eng = None
        eng_ab, eng_tgt = eng.get("ability"), eng.get("target")
        if eng_is_ab and eng_ab is not None and not playbooks.is_noncomp(eng_ab):
            eng_pair = self._pair_best_offline(ctx, eng_ab, eng_tgt)
            if isinstance(eng_pair, dict):
                u_eng = eng_pair["u_full"]
            elif isinstance(eng.get("util"), (int, float)):
                to = eng.get("to") or ctx.origin
                u_eng = eng["util"] + (tile_utility(ctx, to) if to is not None else 0.0)
                rec["u_off_eng_src"] = "util+tile"
        rec["u_off_eng_choice"] = None if u_eng is None else round(u_eng, 3)
        if u_eng is not None and nat_pair["u_full"] > u_eng:
            rec["stage"] = "selection-anomaly"   # offline préférait la paire native — sweep incohérent
            return rec
        # CONTREFACTUEL : les deux paires re-scorées avec les prédictions NATIVES injectées
        # (chacune à SA tuile d'attaque : la native au move-to du chunk, celle du moteur à son to).
        cf_nat = self._counterfactual_utility(ctx, step, uid, ab, tgt, nat_tile)
        cf_eng = None
        if eng_is_ab and eng_ab is not None and eng_tgt is not None \
                and not playbooks.is_noncomp(eng_ab):
            cf_eng = self._counterfactual_utility(ctx, step, uid, eng_ab, eng_tgt,
                                                  eng.get("to"))
        base_eng = cf_eng if cf_eng is not None else u_eng
        rec["cf"] = {"nat": None if cf_nat is None else round(cf_nat, 3),
                     "eng": None if base_eng is None else round(base_eng, 3)}
        if cf_nat is not None and base_eng is not None and cf_nat > base_eng:
            rec["stage"] = "prediction"          # injecter la prédiction native suffit à flipper
            pc = rec["pred"]
            rec["pred_kind"] = ("feed" if pc.get("feed") else
                                "logic" if pc.get("feed") is False else "unknown")
            return rec
        # #45b' : le scorer NATIF départage le résiduel — s'il préfère LUI-MÊME la paire
        # du moteur, la décision native ne vient pas de l'utilité de paire -> gate/
        # éligibilité manqué offline (signature 777 s15 stun), pas un gap de formule.
        if eng_is_ab and eng_ab is not None and eng_tgt is not None \
                and not playbooks.is_noncomp(eng_ab):
            rec["util_eng"] = self._confront_utility(ctx, step, uid, eng_ab, eng_tgt,
                                                     eng.get("to") or ctx.origin)
        nu_nat = (rec.get("util") or {}).get("nat")
        nu_eng = (rec.get("util_eng") or {}).get("nat")
        if nu_nat is not None and nu_eng is not None and nu_nat < nu_eng:
            rec["stage"] = "native-gate"
            return rec
        # RÉSIDUEL — mais un résiduel n'est un VERDICT que si les DEUX côtés ont été scorés.
        # `base_eng is None` ⇒ le choix du MOTEUR n'a jamais pu être scoré offline, donc le
        # contrefactuel n'a PAS eu lieu : le classer «utility-logic» accuse la formule
        # d'utilité — précisément l'étage qu'on mesure EXACT par ailleurs (19/19, delta -0.0
        # sur 777+909 le 2026-08-16). On NOMME l'absence de mesure au lieu de la déguiser en
        # cause. Cas dominant mesuré : le moteur caste une ability NonComparable (utilité =
        # heuristique entière, hors formule 4-familles) là où le natif en caste une
        # Comparable — `nc-pair` ci-dessus ne teste que le côté NATIF, donc ce cas tombait
        # dans le fourre-tout. (777 s10/s18 u81 : natif 69, moteur 1129.)
        if base_eng is None:
            rec["stage"] = ("eng-nc-pair" if (eng_is_ab and eng_ab is not None
                                              and playbooks.is_noncomp(eng_ab))
                            else "eng-unscored")
            return rec
        # Deux côtés scorés, et aucune des portes ci-dessus ne l'explique : gap de formule.
        rec["stage"] = "utility-logic"
        return rec

    # ---- LEVER 1 : précondition offline « terme TriggeredAbilities suspect » (sans capture) ----
    def _suspect_trigger(self, ctx, uid: int, nat_to, eng_to) -> dict | None:
        """Modèle CORRIGÉ case-36 : le terme move TriggeredAbilities(2) appartient au MOVER (Σ de SES
        playbooks AdjacentUnitPreference × amis adjacents à la tuile). Les types portés
        (TRIGGERED_MOVE_PLAYBOOKS) sont calculés par la feuille → plus suspects. Reste suspect : un
        passif du mover dont une clé config `TriggeredAbilities[<NOM>_Adjacent*]` existe mais dont le
        playbook n'est pas porté → est_delta = Σ poids × (amis adj nat − eng)."""
        if eng_to is None or nat_to is None:
            return None
        me = next((u for u in ctx.units if u.get("id") == uid), None)
        if me is None:
            return None
        from engine.playbook.adjacent_unit_preference import TRIGGERED_MOVE_PLAYBOOKS
        from engine.entities.triggered_ability_type import TriggeredAbilityType
        import gameconfig as GC
        ta = ctx.wt.category("TriggeredAbilities")
        unported = []          # [(passif, clé config, poids)]
        for a in (GC.unit_abilities(me.get("visualId") or "").get("passive") or []):
            nm = a.get("name") or ""
            m = TriggeredAbilityType.__members__.get(nm)
            if m is not None and int(m) in TRIGGERED_MOVE_PLAYBOOKS:
                continue       # porté → calculé par la feuille TriggeredAbilitiesUtility
            for k, v in ta.items():
                if v and k.split("_")[0].lower() == nm.lower() and "adjacent" in k.lower():
                    unported.append((nm, k, v))
        if not unported:
            return None
        team = me.get("team")

        def friends_adjacent(tile):
            n = 0
            for u in ctx.units:
                if (not u.get("alive")) or u.get("team") != team or u.get("id") == uid:
                    continue
                p = u.get("pos") or {}
                pc = (p.get("col"), p.get("row"))
                if pc[0] is not None and hexgeo.distance(pc, tile) == 1:
                    n += 1
            return n

        d = friends_adjacent(nat_to) - friends_adjacent(eng_to)
        if d > 0:
            return {"term": "TriggeredAbilities:AdjacentUnitPreference(unported)",
                    "mover_passives": [f"{nm}:{k}={v}" for (nm, k, v) in unported],
                    "est_delta": sum(v for (_, _, v) in unported) * d}
        return None

    # ---- LEVER 3 : diff L3 natif ↔ offline (feuilles move par-tuile, fenêtre seq de ce pas) ----
    _traces_warned = False        # le message d'indisponibilité, une seule fois

    def _trace_file(self):
        """Fichier NDJSON L3 le plus récent de cette session (glob `<sid>-*.jsonl`).

        `None` recouvre DEUX cas que #273 sépare, parce que LEVER 3 est un diagnostic
        auxiliaire (le faire lever tuerait tout le run d'agreement) :
          * répertoire de traces INTROUVABLE -> `HostInputUnavailable`, message NOMMANT
            les chemins essayés, imprimé UNE fois — c'est « pas mesuré » ;
          * répertoire présent, aucun `<sid>-*.jsonl` -> vrai négatif (L3 pas activée
            pour cette session), silencieux comme avant.
        """
        if self._trace_path is None:
            try:
                files = sorted(host_inputs.find(_TRACES, f"{self.sid}-*.jsonl"),
                               key=lambda p: p.stat().st_mtime)
                self._trace_path = files[-1] if files else None
            except host_inputs.HostInputUnavailable as e:
                if not StageProbe._traces_warned:
                    StageProbe._traces_warned = True
                    print("[stages] LEVER 3 (diff L3 natif) INDISPONIBLE -- pas "
                          "mesure, pas 'aucun ecart' :\n" + str(e))
                self._trace_path = None
            except OSError:
                self._trace_path = None
        return self._trace_path

    def _l3_native_terms(self, actor_vis, tiles: list) -> dict:
        """Scores natifs par-feuille (events `utility_score`) pour `tiles`, filtrés sur la
        fenêtre seq de CE pas (émis par l'aiStepDryRun). Renvoie {tile: {utility: score}} ({}
        si pas de trace/fenêtre). Le champ `unit` de la trace = {name: visualId} → on filtre par
        NOM (== visualId de l'acteur) quand connu (une seule unité agit/pas ; robustesse fenêtre)."""
        win = self._seq_win
        tf = self._trace_file()
        if win is None or tf is None:
            return {}
        lo, hi = win
        tset = {tuple(t) for t in tiles if t}
        out: dict = {}
        try:
            with open(tf, encoding="utf-8") as f:
                for line in f:
                    if '"utility_score"' not in line:
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    if e.get("evt") != "utility_score":
                        continue
                    sq = e.get("seq")
                    if sq is None or (hi is not None and sq > hi) or (lo is not None and sq <= lo):
                        continue
                    eu = e.get("unit")
                    eun = eu.get("name") if isinstance(eu, dict) else eu
                    if actor_vis is not None and eun is not None and eun != actor_vis:
                        continue
                    t = _tile_of(e.get("caseTile"))
                    if t not in tset:
                        continue
                    out.setdefault(t, {})[str(e.get("utility") or "")] = e.get("score")
        except OSError:
            return {}
        return out

    @staticmethod
    def _missing_terms(native_terms: dict) -> list:
        """Feuilles natives non nulles dont le NOM matche une feuille qu'on DROP à 0 = manquantes."""
        miss = []
        for tile, leaves in native_terms.items():
            for name, score in leaves.items():
                if score and any(k in name for k in _DROPPED_LEAF_KEYWORDS):
                    miss.append({"tile": list(tile), "term": name, "native_score": score})
        return miss

    # ---- classification dimension MOVE ----
    def _probe_move(self, ctx, step: int, uid: int, nat: dict, eng: dict) -> dict:
        nat_to = nat["move"]["to"]
        eng_to = eng.get("to")
        d = hexgeo.distance(eng_to, nat_to) if (eng_to and nat_to) else None
        rec = {"step": step, "uid": uid, "dim": "move", "hit": d == 0,
               "native": nat_to, "engine": {"kind": eng.get("kind"), "to": eng_to},
               "dist": d}
        if d == 0:
            rec["stage"] = "hit"
            return rec
        na = nat["ability"]
        eng_is_ab = eng.get("kind") == "ability"
        # « En aval du choix d'ability » n'a de sens que si l'ability DIVERGE. Quand les deux
        # côtés castent la MÊME paire, rien en amont n'explique l'écart de tuile : court-circuiter
        # là revient à classer un miss réel sous une étiquette qui dit « déjà expliqué ailleurs ».
        # (Mesuré 777 s8 u79 : ability 69→93 IDENTIQUE des deux côtés, position à 2 hexes.)
        same_pair = bool(na) and eng_is_ab and eng.get("ability") == na["ability"] \
            and (eng.get("target") == na["target"] or playbooks.is_summon(na["ability"]))
        if (na or eng_is_ab) and not same_pair:
            # Chunk composé (ou moteur qui caste) : la position découle du choix d'ability.
            rec["stage"] = ("generator-overfire" if (not na and eng_is_ab)
                            else "pos-downstream-of-ability")
            return rec
        if same_pair:
            # Même paire des deux côtés, tuile différente. Ce n'est PAS du move pur (la tuile
            # sort du sweep de position de la PAIRE, pas de Tile(7)+MinDist) et ce n'est PAS en
            # aval d'un choix d'ability. Échelle dédiée — ORDRE LOAD-BEARING : elle écarte les
            # causes DÉJÀ MESURÉES avant d'oser nommer un argmax incohérent.
            ab_, tgt_ = na["ability"], na["target"]
            ranked = self._pair_ranked_tiles(ctx, ab_, tgt_)
            u_own_nat = self._pair_own_at(ctx, ab_, tgt_, nat_to)
            u_own_eng = self._pair_own_at(ctx, ab_, tgt_, eng_to)
            u_cf_nat = self._counterfactual_utility(ctx, step, uid, ab_, tgt_, nat_to)
            u_cf_eng = (self._counterfactual_utility(ctx, step, uid, ab_, tgt_, eng_to)
                        if eng_to is not None else None)
            _r3 = lambda v: None if v is None else round(v, 3)          # noqa: E731
            rec["pair_pos_u"] = {"own": {"nat": _r3(u_own_nat), "eng": _r3(u_own_eng)},
                                 "cf": {"nat": _r3(u_cf_nat), "eng": _r3(u_cf_eng)}}
            if ranked is not None and nat_to not in ranked:
                rec["stage"] = "pos-pair-enumeration"     # tuile native jamais énumérée (feed)
                return rec
            if None in (u_own_nat, u_own_eng, u_cf_nat, u_cf_eng):
                rec["stage"] = "pos-pair-unscored"        # non mesuré, PAS un verdict
                return rec
            if u_own_nat > u_own_eng:
                # NOS PROPRES prédictions préféraient déjà la tuile native, et on a pris l'autre :
                # incohérence d'argmax VRAIE, indépendante de toute divergence de prédiction.
                rec["stage"] = "pos-pair-selection-anomaly"
            elif u_cf_nat > u_cf_eng:
                # Notre choix était COHÉRENT avec ce qu'on prédisait ; injecter les prédictions
                # NATIVES suffit à faire repasser la tuile native devant -> le miss est porté par
                # l'étage PRÉDICTION, où il est déjà compté. Ne pas le compter deux fois, et
                # surtout ne pas l'imputer à l'argmax.
                rec["stage"] = "pos-pair-prediction"
            elif abs(u_cf_nat - u_cf_eng) <= max(0.01, 0.001 * abs(u_cf_nat)):
                rec["stage"] = "pos-pair-tie-break"
            else:
                rec["stage"] = "pos-pair-formula"         # même bien prédit, on sur-score la nôtre
            return rec
        # Move PUR des deux côtés -> décomposition Tile7 + MinDist.
        legal = {(t["col"], t["row"]) for t in ctx.move_tiles}
        if nat_to not in legal:
            rec["stage"] = "move-enumeration"    # tuile native hors de notre set légal (feed)
            return rec
        mu = self._move_utils(ctx, [nat_to] + ([eng_to] if eng_to else []))
        rec["move_terms"] = {str(k): v for k, v in mu.items()}
        u_nat = mu.get(nat_to, {}).get("u")
        u_eng = mu.get(eng_to, {}).get("u") if eng_to else None
        if u_nat is None or u_eng is None:
            rec["stage"] = "move-unscored"
        elif u_nat == u_eng:
            rec["stage"] = "move-tie-break"
        elif u_nat < u_eng:
            rec["stage"] = "move-formula"
        else:
            rec["stage"] = "move-selection-anomaly"
        # Nommer un TERME MANQUANT (feuille droppée à 0) au lieu du fourre-tout move-formula :
        #   LEVER 1 (offline) — précondition « ami TriggeredAbilities adjacent » (sans capture) ;
        #   LEVER 3 (--l3)    — breakdown natif par-feuille (diff L3) + feuilles manquantes nommées.
        suspect = self._suspect_trigger(ctx, uid, nat_to, eng_to)
        if suspect:
            rec["suspect"] = suspect
        if self.l3:
            _me = next((u for u in ctx.units if u.get("id") == uid), None)
            nt = self._l3_native_terms(_me.get("visualId") if _me else None, [nat_to, eng_to])
            if nt:
                rec["native_terms"] = {str(k): v for k, v in nt.items()}
                miss = self._missing_terms(nt)
                if miss:
                    rec["missing_terms"] = miss
        return rec

    # ---- entrée sonde (signature `probe` de run_agreement) ----
    def __call__(self, step: int, uid: int, dv: dict, mov_by_unit: dict, nat: dict,
                 eng: dict, predictor) -> None:
        # LEVER 3 : borne HAUTE de la fenêtre seq = seq AVANT tout RPC de sonde (les events L3
        # de CE pas ont été émis par l'aiStepDryRun de run_agreement ; les RPC intermédiaires
        # decisionView/movable/engine_decide n'émettent PAS d'utility_score → fenêtre propre).
        if self.l3:
            st = _rpc(self.sid, "aiTraceStatus", [], timeout=20).get("result") or {}
            seq_now = st.get("seq")
            self._seq_win = (self._prev_seq, seq_now)
            self._prev_seq = seq_now
        # ctx REBUILDÉ avec les MÊMES entrées qu'engine_decide (même predictor partagé,
        # boucliers déjà refreshés par run_agreement) -> l'offline sondé == l'offline décidé.
        ctx = _ai_ctx.build(self.rpc, self.rid, dv, mov_by_unit, uid, self.wt, predictor)
        if nat["ability"]:
            self.records.append(self._probe_ability(ctx, dv, mov_by_unit, step, uid,
                                                    nat, eng))
        if nat["move"]:
            self.records.append(self._probe_move(ctx, step, uid, nat, eng))


# ── Orchestration : un runner -> walk + sonde ; batch = N seeds ────────────────────────

def run_stages(sid: int, rid: int, steps: int, wt, l3: bool = False) -> dict:
    probe = StageProbe(sid, rid, wt)
    probe.l3 = l3
    if l3:
        _rpc(sid, "aiTraceEnable", ["L3"], timeout=20)   # RUNTIME, sans reinject
    try:
        res = EV.run_agreement(sid, rid, steps, wt, probe=probe)
    finally:
        if l3:
            _rpc(sid, "aiTraceDisable", ["L3"], timeout=20)
    return {"agreement": {"pos": res["pos"], "ability": res["ability"]},
            "stage_records": probe.records}


def _build_runner(seed: str, extra: list) -> int | None:
    """`rl_duel build` sur le state-file DÉDIÉ (mirror du fixture pytest build_runner)."""
    board_args = [] if any(x in ("--board", "--board-pool") for x in extra) \
        else ["--board", "MC1_67"]
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(STATE), *board_args, *extra],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[stages] build seed={seed} KO: {(proc.stderr or proc.stdout or '')[-300:]}",
              file=sys.stderr)
        return None
    return json.loads(STATE.read_text())["runnerId"]


def summarize(all_records: list) -> None:
    """Tableau des misses PAR ÉTAGE + fidélité prédiction globale (ASCII only)."""
    ab_recs = [r for r in all_records if r["dim"] == "ability"]
    mv_recs = [r for r in all_records if r["dim"] == "move"]
    print()
    print("=== ETAGE PREDICTION (paires natives confrontees, hits inclus) ===")
    preds = [r["pred"] for r in ab_recs if isinstance(r.get("pred"), dict)
             and "match" in r["pred"]]
    n = len(preds)
    if n:
        n_match = sum(1 for p in preds if p["match"])
        n_feed = sum(1 for p in preds if not p["match"] and p.get("feed") is True)
        n_logic = sum(1 for p in preds if not p["match"] and p.get("feed") is False)
        n_unk = n - n_match - n_feed - n_logic
        print(f"  confrontations: {n}  match={n_match} ({100 * n_match // n}%)  "
              f"mismatch-feed(staleness)={n_feed}  mismatch-logic(formule)={n_logic}  "
              f"inclassable={n_unk}")
    else:
        print("  aucune paire confrontable")
    print()
    print("=== ETAGE UTILITE (#45b' : formule offline vs scorer natif pairUtility) ===")
    urecs = [(r, r["util"]) for r in ab_recs
             if isinstance(r.get("util"), dict) and "match" in r["util"]]
    nu = len(urecs)
    if nu:
        n_match = sum(1 for _, u in urecs if u["match"])
        n_skip = sum(1 for r in ab_recs if isinstance(r.get("util"), dict)
                     and r["util"].get("skipped") not in (None, "nc-pair"))
        print(f"  confrontations: {nu}  match={n_match} ({100 * n_match // nu}%)  "
              f"mismatch={nu - n_match}  skipped(rpc/no-events)={n_skip}")
        mism = [(r, u) for r, u in urecs if not u["match"]]
        fam_cnt: Counter = Counter("+".join(u.get("families") or ["?"]) for _, u in mism)
        for fam, k in fam_cnt.most_common():
            ds = [abs(u["delta"]) for _, u in mism
                  if "+".join(u.get("families") or ["?"]) == fam]
            print(f"    {fam:<20} {k}  |delta| moy={sum(ds) / len(ds):.3f} "
                  f"max={max(ds):.3f}")
        for r, u in sorted(mism, key=lambda x: -abs(x[1]["delta"]))[:3]:
            na = r.get("native") or {}
            print(f"    worst: step={r['step']} u{r['uid']} "
                  f"ab={na.get('ability')}->t{na.get('target')} "
                  f"off={u['off']} nat={u['nat']} delta={u['delta']} "
                  f"fam={'+'.join(u.get('families') or [])}")
    else:
        print("  aucune paire confrontable")
    print()
    print("=== MISSES PAR ETAGE ===")
    for name, recs in (("ability", ab_recs), ("move", mv_recs)):
        cnt = Counter(r["stage"] for r in recs)
        total = len(recs)
        hits = cnt.pop("hit", 0)
        print(f"  [{name}] compares={total} hits={hits}"
              + (f" ({100 * hits // total}%)" if total else ""))
        for stage, k in cnt.most_common():
            print(f"    {stage:<28} {k}")
    print()
    # LEVER 1/3 : « termes manquants » NOMMÉS sur les misses move (au lieu du fourre-tout
    # move-formula) — suspect offline (précondition) + missing L3 (feuille native non nulle qu'on drop).
    sus: Counter = Counter()
    miss_l3: Counter = Counter()
    for r in mv_recs:
        if r.get("suspect"):
            sus[r["suspect"]["term"]] += 1
        for m in (r.get("missing_terms") or []):
            miss_l3[m["term"]] += 1
    if sus or miss_l3:
        print("=== TERMES MANQUANTS MOVE (leviers 1/3) ===")
        for term, k in sus.most_common():
            print(f"    suspect(offline)   {term:<40} {k}")
        for term, k in miss_l3.most_common():
            print(f"    missing(L3-natif)  {term:<40} {k}")
        print()
    # Détail des misses de prédiction (les leviers) : champ(s) divergents les plus frequents.
    field_cnt: Counter = Counter()
    for p in preds:
        for k in (p.get("delta") or {}):
            field_cnt[k] += 1
    if field_cnt:
        print("=== CHAMPS DIVERGENTS (prediction main-target) ===")
        for k, v in field_cnt.most_common():
            print(f"    {k:<20} {v}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--build", action="store_true",
                    help="batch : construit/walke/dispose un runner isole par seed")
    ap.add_argument("--seeds", type=str, default="777",
                    help="seeds du mode --build, separes par des virgules")
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--json", type=str, default=None,
                    help="dump JSON des stage_records (defaut data/stages_agreement.json)")
    ap.add_argument("--l3", action="store_true",
                    help="LEVER 3 : capture ai-trace L3 (RUNTIME, sans reinject) + diff natif par-feuille "
                         "sur les misses move (native_terms/missing_terms). Plus lent (1 RPC seq/pas). "
                         "L3 est SESSION-GLOBALE -> lancer SOLO (cf. --l3-force).")
    ap.add_argument("--l3-force", action="store_true",
                    help="passer outre le garde-fou --l3 malgre des runners preexistants (danger : "
                         "crash IL2CPP si un autre agent walke l'IA en parallele).")
    ap.add_argument("--state-file", type=str, default=None,
                    help="state-file DEDIE du mode --build (defaut data/_stages_duel_state.json, "
                         "PARTAGE). En passer un PROPRE (chemin absolu) permet de lancer N "
                         "invocations --build EN PARALLELE (une par seed) sans collision de "
                         "scoped-replace — discipline runner par-state-file inchangee.")
    args, extra = ap.parse_known_args(argv)
    if args.state_file:
        globals()["STATE"] = Path(args.state_file)
    if extra and extra[0] == "--":
        extra = extra[1:]
    sid = _resolve_session()
    wt = weights.load()
    all_records: list = []
    runs: list = []

    # GARDE-FOU --l3 : L3 est SESSION-GLOBALE (hooks sur 41 *Utility.MoveNext du hot-path IA). Si un
    # AUTRE agent walke l'IA en parallele, ses aiStepDryRun declenchent AUSSI ces hooks -> double
    # charge hot-path = crash IL2CPP (VECU 2026-07-19 : session perdue). En mode --build, tout runner
    # preexistant est ETRANGER -> refuser --l3 sauf --l3-force.
    if args.build and args.l3 and not getattr(args, "l3_force", False):
        pre = _rpc(sid, "listRunners", [], timeout=10).get("result") or []
        if pre:
            ids = [(r.get("runnerId") if isinstance(r, dict) else r) for r in pre]
            print(f"[stages] REFUS --l3 : {len(pre)} runner(s) preexistant(s) {ids} — L3 est "
                  f"SESSION-GLOBALE ; un autre agent qui walke l'IA en parallele => crash IL2CPP. "
                  f"Relance en SOLO (aucun autre runner), ou --l3-force si tu es certain d'etre seul.",
                  file=sys.stderr)
            return 2

    if args.build:
        for seed in [s.strip() for s in args.seeds.split(",") if s.strip()]:
            rid = _build_runner(seed, extra)
            if rid is None:
                continue
            print(f"[stages] seed={seed} runner={rid} steps={args.steps}"
                  + (" +L3" if args.l3 else ""))
            try:
                out = run_stages(sid, rid, args.steps, wt, l3=args.l3)
                runs.append({"seed": seed, "rid": rid, **out})
                all_records += out["stage_records"]
            finally:
                _r(sid, "disposeRunner", {"runnerId": rid}, 20)
    else:
        rid = args.runner
        if rid is None:
            rl = _rpc(sid, "listRunners", [], timeout=10).get("result") or []
            first = rl[0] if rl else None
            rid = first.get("runnerId") if isinstance(first, dict) else first
        if rid is None:
            print("[stages] aucun runner — --runner N ou --build", file=sys.stderr)
            return 2
        print(f"[stages] session={sid} runner={rid} steps={args.steps}"
              + (" +L3" if args.l3 else ""))
        out = run_stages(sid, rid, args.steps, wt, l3=args.l3)
        runs.append({"rid": rid, **out})
        all_records += out["stage_records"]

    summarize(all_records)
    dump = Path(args.json) if args.json else (ROOT / "logs" / "runners" / "stages_agreement.json")
    dump.parent.mkdir(parents=True, exist_ok=True)
    with open(dump, "w", encoding="utf-8") as f:
        json.dump({"runs": runs}, f, ensure_ascii=False, indent=1, default=str)
    print(f"[stages] dump JSON -> {dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
