"""#999-r3-r1-r1 -- CONFRONTATION LIVE : une MACHINE OF WAR porteuse d'un effet-AURA est-elle
publiee par le jeu, et le PORT la retient-il comme PORTEUR, sur les DEUX faces ?

POURQUOI CE PROBE EXISTE. La reparation de `#999-r3-r1-r1` est offline par nature (elle enleve un
filtre du port). Un test offline peut montrer qu'un etat SYNTHETIQUE traverse ; il ne peut pas
montrer que le JEU publie bien la matiere -- que `decisionView.mows[].effects` porte reellement
l'aura, et que `combatSnapshot` materialise la MoW en entite sans position. C'est cette moitie-la
que ce probe mesure, et c'est la seule qui puisse REFUTER le port.

⚠ CE N'EST PAS UNE MESURE DE NOMBRE, et il ne faut pas le lire comme tel. AUCUN des six effets
d'aura de MoW (1442, 1443, 1445, 1449, 1494, 1548) n'est porte cote Python : il n'existe donc
aucune magnitude a confronter. Ce qui est confronte ici est le CANAL -- la chaine
`jeu -> decisionView/combatSnapshot -> EffectsState -> univers de porteurs`. Le jour ou l'un des
six sera porte, SA magnitude devra etre confrontee separement, en regime SEPARANT.

MONTAGE (`deathCrawler` / `BlightedLand` 1447 -> effet 1442) : c'est le seul couple qui tienne les
trois contraintes -- porteur MoW **au seed** (`catalog_inject --list-mythics` : `au-seed=
['deathCrawler']`), aura POSEE A L'INIT (owner-effect, donc presente au tour 0 sans avoir a jouer
quoi que ce soit), et effet dont le `$$CreateTargetSelector` ne lit AUCUNE position -- ce qui est
justement la classe d'effets que la reparation rend atteignable.

CE QU'IL MESURE, ETAGE PAR ETAGE :
  1. `decisionView.mows[]` porte la MoW, et `mows[].effects` porte 1442  (le CAPTEUR)
  2. `combatSnapshot` -> `load_state` : la MoW est une ENTITE, SANS `PositionComponent`, et
     `state.effects` porte son aura                                       (la face COMBAT, entree)
  3. les deux agregateurs COMBAT la RETIENNENT comme porteur              (la face COMBAT, sortie)
  4. `step_context` la seede, et `Scene.effect_carrier_ids` la contient   (la face DECISION)
  5. ⚠ CONTRE-EPREUVE : elle n'a AUCUNE position sur aucune des deux faces. Sans cet etage, une
     << reparation >> qui fabriquerait une tuile pour la MoW passerait pour un succes -- alors
     qu'elle rendrait evaluable une aura POSITIONNELLE qui doit se taire.

Discipline runner : `--state-file` ABSOLU sous `logs/` du checkout, `--board` EXPLICITE, runner
DISPOSE en sortie sauf `--keep`. ASCII only (cp1252).

Usage :
    python probe_999r3r1r1_porteur_mow_live.py
    python probe_999r3r1r1_porteur_mow_live.py --mow ultraDreadnought --mythic WisdomOfTheAncients
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import rl_duel as R  # noqa: E402

#: Board EXPLICITE (jamais le defaut implicite) -- `runner.md` l'exige.
BOARD = "MC1_67"
SEED = 777
#: MoW porteuse AU SEED d'une mythique dont l'effet est une AURA posee a l'init.
MOW = "deathCrawler"
MYTHIC = "BlightedLand"
#: `EffectType` 0x5a2 = 1442 -- l'owner-effect que `BlightedLand` pose sur sa MoW.
EFFET_AURA = "BlightedLand_ExtraDamagePct"
#: Palier de la mythique (1..4). Sans consequence sur ce probe (aucune magnitude mesuree), mais
#: `TertiaryAbilityLevel >= 1` est un VERROU du montage (cf. `case-237`).
NIVEAU = 4


def _unwrap(x):
    return x.get("result") if isinstance(x, dict) and "result" in x else x


def _effect_names(row) -> list:
    return [e.get("name") for e in (row.get("effects") or []) if e.get("name")]


def run(mow: str = MOW, mythic: str = MYTHIC, effet: str = EFFET_AURA, seed: int = SEED,
        board: str = BOARD, niveau: int = NIVEAU, keep: bool = False, verbose: bool = False) -> dict:
    """Monte le runner, mesure les cinq etages, DISPOSE. Rend un dict de faits MESURES.

    LEVE `RuntimeError` si le montage ne s'installe pas (MoW absente du roster, aura absente) --
    un montage qui echoue ne doit JAMAIS se degrader en verdict, sinon la garde qui le consomme
    rend un VERT VIDE."""
    from engine.runner.snapshot import load_state                              # noqa: PLC0415
    from engine.runner.components import PositionComponent                     # noqa: PLC0415
    from engine.runner import damage_model as DM                               # noqa: PLC0415
    from engine.runner.damage_model import unit_state_for_effects              # noqa: PLC0415
    from engine.playbook.scene import Scene, step_context                      # noqa: PLC0415

    import json                                                                # noqa: PLC0415
    import rl_collect_batch as B                                               # noqa: PLC0415

    sf = Path(__file__).resolve().parents[2] / "logs" / "probe_999r3r1r1_mow.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    # ⚠ MEME VOIE DE BUILD que `probe_999r3_regime_separant_rarete` : la CLI par `R.main(argv)`,
    # pas un `Namespace` fabrique a la main -- un jeu de defauts recopie se perime en silence des
    # qu'une option est ajoutee a `rl_duel build`.
    argv = ["build", "--seed", str(int(seed)), "--board", str(board), "--p-mow", str(mow),
            "--equip-mythic", "%s:%s:%d" % (mow, mythic, int(niveau)),
            "--state-file", str(sf)]
    if verbose:
        print("[999-r3-r1-r1] build %s" % " ".join(argv))
    if R.main(argv) != 0:
        raise RuntimeError("build ECHOUE : %s" % " ".join(argv))
    rid = json.loads(sf.read_text(encoding="utf-8")).get("runnerId")
    if rid is None:
        raise RuntimeError("build sans runnerId (montage non installe) : %s" % sf)
    sid = B._resolve_session()
    # #1074 -- CE MONTAGE GREFFE (`--equip-mythic` -> `catalog_inject.equip_mythic`, qui ecrit
    # `BC.Units[].TertiaryAbility`), donc le `load_state` de l'etage 2 DOIT alimenter le canal
    # `unitAbilityStates` : c'est la SEULE voie par laquelle le port voit la mythique montee. Sans
    # lui, `collect_triggered_abilities` retombe sur `gameconfig.unit(<greffon>)` et le porteur
    # arrive SANS son owner-effect -- le probe mesurerait un NEANT en VERT (#448-r3-r1).
    B.bind_ambient_rpc(sid)

    def _rpc(method, body, timeout=90):
        return _unwrap(B._rpc(sid, method, [body], timeout=timeout)) or {}

    faits: dict = {"runnerId": rid, "mow": mow, "mythic": mythic, "effet": effet}
    try:
        dv = _rpc("decisionView", {"runnerId": rid, "includeInactive": True})
        snap = _rpc("combatSnapshot", {"runnerId": rid})
        obs = _rpc("observeBattle", {"runnerId": rid}, 40)

        # --- etage 1 : le CAPTEUR ------------------------------------------------------------
        mows = dv.get("mows") or []
        ligne = next((m for m in mows if m.get("visualId") == mow), None)
        if ligne is None:
            raise RuntimeError("la MoW %r n'est pas dans decisionView.mows (%d ligne(s) : %r)"
                               % (mow, len(mows), [m.get("visualId") for m in mows]))
        mid = ligne.get("casterId")
        noms = _effect_names(ligne)
        faits["mow_id"] = mid
        faits["mow_effets_publies"] = noms
        faits["aura_publiee"] = effet in noms
        if not faits["aura_publiee"]:
            raise RuntimeError("montage DEGENERE : la MoW ne porte pas %r (publie : %r) -- la "
                               "mythique n'est pas montee, ou son owner-effect n'est pas pose"
                               % (effet, noms))
        faits["mow_pos_publiee"] = ligne.get("pos")

        # --- etage 2 : la face COMBAT, ENTREE ------------------------------------------------
        st = load_state(dv, obs, snap)
        ent = st.get_entity(mid)
        faits["mow_entite_combat"] = ent is not None
        faits["mow_sans_position_combat"] = (ent is not None
                                             and ent.get_component(PositionComponent) is None)
        portes = [getattr(e, "name", None)
                  for e in st.effects.active_effects(mid, unit_state_for_effects(st, mid))]
        faits["mow_aura_active_combat"] = effet in portes

        # --- etage 3 : la face COMBAT, SORTIE (interception du foyer REEL) -------------------
        # ⚠ On INTERCEPTE l'agregateur, on ne recopie PAS sa boucle : un mirror mesurerait le code
        # du probe. FORME B : `damage_model` lie ces symboles au niveau module, donc remplacer
        # l'attribut du module MORD (remplacer `engine.entities.effects.<nom>` ne mordrait pas).
        allie = next((u["id"] for u in (dv.get("units") or [])
                      if u.get("team") == ligne.get("team") and (u.get("hp") or 0) > 0), None)
        ennemi = next((u["id"] for u in (dv.get("units") or [])
                       if u.get("team") != ligne.get("team") and (u.get("hp") or 0) > 0), None)
        faits["allie"], faits["ennemi"] = allie, ennemi
        if allie is None or ennemi is None:
            raise RuntimeError("montage DEGENERE : pas de couple (allie, ennemi) vivant")
        faits["porteurs_aura_attaque"] = _porteurs(
            DM, "aura_attack_damage_bonus_from_allies",
            lambda: DM.attacker_modifiers(st, allie, 5000, is_ranged=False, target_id=ennemi))
        faits["porteurs_aura_defense"] = _porteurs(
            DM, "aura_defense_damage_malus_from_units",
            lambda: DM.defender_modifiers(st, ennemi, 5000, is_melee=True, attacker_id=allie))
        faits["mow_porteur_attaque"] = mid in (faits["porteurs_aura_attaque"] or [])
        faits["mow_porteur_defense"] = mid in (faits["porteurs_aura_defense"] or [])

        # --- etage 4 : la face DECISION ------------------------------------------------------
        predictor = {"mult_by_id": {}, "ablvl_by_id": {}, "ctx_by_id": {}}
        sctx = step_context(predictor, dv)
        sc = Scene(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                   vis_by_id={}, units=sctx.get("units") or [],
                   hp_by_id=sctx.get("hp_by_id") or {}, pos_by_id=sctx.get("pos_by_id") or {},
                   team_by_id=sctx.get("team_by_id") or {}, eff_state=sctx["eff_state"])
        faits["mow_seedee_decision"] = mid in (sctx["eff_state"].by_unit or {})
        faits["mow_dans_univers_porteurs"] = mid in sc.effect_carrier_ids()
        # --- etage 5 : CONTRE-EPREUVE -- aucune position, nulle part -------------------------
        faits["mow_sans_position_decision"] = mid not in (sctx.get("pos_by_id") or {})
    finally:
        if not keep:
            try:
                B._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
            except Exception:                  # un teardown qui leve masquerait le verdict
                pass
    if verbose:
        _print(faits)
    return faits


def _porteurs(DM, nom_agregateur: str, appel):
    """Ids des porteurs que le foyer REEL a retenus, captes par INTERCEPTION. `None` = l'agregateur
    n'a PAS ete appele (aucun porteur du tout) -- un `[]` s'y confondrait avec << appele, MoW
    absente >>."""
    vus = []
    reel = getattr(DM, nom_agregateur)

    def _spy(carriers, ctx):
        vus.append([c[0] for c in (carriers or [])])
        return reel(carriers, ctx)

    setattr(DM, nom_agregateur, _spy)
    try:
        appel()
    finally:
        setattr(DM, nom_agregateur, reel)
    return vus[0] if vus else None


def _print(f: dict) -> None:
    print("=== #999-r3-r1-r1 LIVE : %s / %s -> %s ===" % (f["mow"], f["mythic"], f["effet"]))
    print("-- etage 1 : le CAPTEUR (decisionView.mows[])")
    print("   MoW publiee (casterId)                   : %s" % f.get("mow_id"))
    print("   effets publies sur la MoW                : %s" % (f.get("mow_effets_publies"),))
    print("   l'AURA y est                             : %s" % f.get("aura_publiee"))
    print("   position publiee (doit etre None)        : %s" % (f.get("mow_pos_publiee"),))
    print("-- etage 2 : face COMBAT, ENTREE (load_state)")
    print("   MoW materialisee comme entite            : %s" % f.get("mow_entite_combat"))
    print("   SANS PositionComponent                   : %s" % f.get("mow_sans_position_combat"))
    print("   aura ACTIVE dans state.effects           : %s" % f.get("mow_aura_active_combat"))
    print("-- etage 3 : face COMBAT, SORTIE (foyer REEL intercepte)")
    print("   porteurs retenus (aura ATTAQUE)          : %s" % (f.get("porteurs_aura_attaque"),))
    print("   MoW retenue                              : %s" % f.get("mow_porteur_attaque"))
    print("   porteurs retenus (aura DEFENSE)          : %s" % (f.get("porteurs_aura_defense"),))
    print("   MoW retenue                              : %s" % f.get("mow_porteur_defense"))
    print("-- etage 4 : face DECISION (step_context / Scene)")
    print("   aura SEEDEE dans EffectsState            : %s" % f.get("mow_seedee_decision"))
    print("   MoW dans l'univers des porteurs          : %s" % f.get("mow_dans_univers_porteurs"))
    print("-- etage 5 : CONTRE-EPREUVE (aucune position fabriquee)")
    print("   absente de pos_by_id (face DECISION)     : %s" % f.get("mow_sans_position_decision"))


def verdict(f: dict) -> bool:
    return bool(f.get("aura_publiee") and f.get("mow_entite_combat")
                and f.get("mow_sans_position_combat") and f.get("mow_aura_active_combat")
                and f.get("porteurs_aura_attaque") is not None
                and f.get("porteurs_aura_defense") is not None
                and f.get("mow_porteur_attaque") and f.get("mow_porteur_defense")
                and f.get("mow_seedee_decision") and f.get("mow_dans_univers_porteurs")
                and f.get("mow_sans_position_decision"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mow", default=MOW)
    ap.add_argument("--mythic", default=MYTHIC)
    ap.add_argument("--effet", default=EFFET_AURA)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--niveau", type=int, default=NIVEAU)
    ap.add_argument("--keep", action="store_true", help="ne PAS disposer le runner")
    a = ap.parse_args()
    f = run(mow=a.mow, mythic=a.mythic, effet=a.effet, seed=a.seed, board=a.board,
            niveau=a.niveau, keep=a.keep, verbose=True)
    print()
    if verdict(f):
        print("VERDICT: le canal TRAVERSE de bout en bout, sur les DEUX faces, et AUCUNE position")
        print("         n'a ete fabriquee pour la MoW. La reparation #999-r3-r1-r1 tient LIVE.")
        return 0
    print("VERDICT: le canal NE traverse PAS -- un etage est muet (re-lire la ventilation ci-dessus).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
