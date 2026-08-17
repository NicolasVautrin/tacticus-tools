"""#429-r1-r1-r1 -- LE TRI, SITE PAR SITE, des call-sites d'`execute_ability_attack`.

#429-r1-r1 a pose le gate cadavre au FOYER de l'attaque NORMALE
(`AttackDamageOperation.execute`), parce que ses 11 call-sites empruntent TOUS, cote natif,
`IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviour$$Execute` ->
`Core.Services.OperationProcessor$$ActiveAbility` ->
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`, donc le MEME gate.

La famille ABILITY ne se comporte PAS ainsi, et c'est tout l'objet de cette tranche :
`AttackDamageOperation.execute_ability_attack` est appelee depuis des sites qui, cote natif,
sont de DEUX natures differentes. Poser le gate sur le foyer sur-refuserait.

LE CRITERE, ET IL EST MESURE (build `rnca9r7q6c`)
-------------------------------------------------
`IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility` a exactement
DEUX appelants CODE dans tout le binaire (xrefs) :
  * `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`
  * `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteForReplacedTarget`
et `ActiveAbilityOperation$$Execute` n'a lui-meme que deux appelants CODE
(`Core.Services.OperationProcessor$$ActiveAbility` + la re-entree ci-dessus), `ExecuteInternal`
un SEUL. Le gate est donc STRICTEMENT l'affaire de l'etage « execution d'ability active ».

L'etage des noeuds DSL d'attaque, lui, ne gate RIEN -- lu au decompile :
  `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
    -> `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget`
    -> `Core.Services.OperationProcessor$$AttackDamage`
    -> `IdunBattle.Operations.AttackDamageOperation$$Execute`   (ni IsAlive, ni IsDead, ni gate)
idem `IdunBattle.Entities.Behaviours.ChainLeftOverHitsAttackDamageBehaviour$$Execute` et
`IdunBattle.Operations.AbilityDamageOperation$$Execute` (leurs callees NOMMES ne contiennent
aucun test de mort).

=> UN SITE SE GATE SI ET SEULEMENT SI IL EMULE UN CAST D'ABILITY ACTIVE.
   Un site qui mirror un NOEUD DSL d'attaque interne a une behaviour ne se gate PAS : l'y gater
   serait un FORK du natif.

LA PREUVE QUE LE FORK COUTERAIT (et qu'elle n'est pas theorique)
---------------------------------------------------------------
`IdunBattleLogic.Entities.Abilities.Active.Loki.HazeCorruption_BonusHitAbility` a pour trigger
`OnPreDeath(1,0) & get_OwnerIsActor & IsDead(Target@0x178) & ...` : sa cible est MORTE PAR
CONSTRUCTION, et le natif la frappe quand meme (mesure case-209 : evenement de degat
`Amount 0` sur le cadavre, puis `LeftOverDamage` reportee sur le relais bonde). Un gate pose
sur le foyer supprimerait ce coup, donc le transfert. C'est ce que mesure le volet `live`.

VOLETS
------
  --volet tri    : scan AST des call-sites + CLIQUET de classification (offline)
  --volet gate   : les quatre bras offline + la contre-epreuve par mutation
  --volet live   : Haze -- natif vs port vs port MUTE (gate en bloc), chiffres

Re-deriver :
  python scripts/python/probe_429r1r1r1_ability_attack_dead_target.py --volet tri
  python scripts/python/probe_429r1r1r1_ability_attack_dead_target.py --volet gate
  python scripts/python/probe_429r1r1r1_ability_attack_dead_target.py --volet live
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ENGINE = Path(__file__).resolve().parent / "engine"

#: Le nom du predicat porte du gate -- ce que le scan cherche DANS le corps de chaque site.
GATE_NAME = "is_dead_unit_and_not_allowed_by_ability"

#: LE TRI. Cle = `(chemin relatif POSIX, qualname de la fonction englobante)`.
#: Valeur = `(gate_attendu, artefact natif, raison)`.
#: Ce n'est pas un commentaire : le volet `tri` CONFRONTE cette table au scan, dans les DEUX sens.
TRI = {
    ("runner/abilities/behaviours/combat.py", "AttackWithAttackDamage::execute"): (
        False, "IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage",
        "Feuille DSL. Etage natif `AttackBehaviour$$Execute` -> `AttackDamageBehaviour$$ExecuteTarget`"
        " -> `AttackDamageOperation$$Execute` : aucun gate cadavre sur le trajet."),
    ("runner/abilities/behaviours/combat.py", "ChainLeftOverHitsAttackDamage::execute"): (
        False, "IdunBattle.Entities.Behaviours.ChainLeftOverHitsAttackDamageBehaviour$$Execute",
        "Feuille DSL. Ses callees NOMMES ne comportent aucun test de mort."),
    ("runner/abilities/behaviours/combat.py", "AttackWithAbilityDamage::execute"): (
        False, "IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage",
        "Feuille DSL, famille ABILITY -> `IdunBattle.Operations.AbilityDamageOperation$$Execute` :"
        " teste `EntityExtensions$$IsUnit` (lecture de stat), jamais la mort."),
    ("runner/abilities/loki/splash.py", "_splash_ability_behaviour"): (
        False, "IdunBattleLogic.Entities.Abilities.Active.Loki.CrushingClawsAbility$$ExecuteBehaviour",
        "Volets MAIN + SPLASH d'une behaviour d'ability : noeuds INTERNES, cibles secondaires"
        " selectionnees DANS l'arbre. Plus aucun appelant production (oracle des tests DSL)."),
    ("runner/operations/summon_ai.py", "_apply_active_ability"): (
        True, "IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal",
        "SEUL site GATE : repli generique qui EMULE un cast d'ability active pour une ability sans"
        " port dedie. Cote natif un summon qui joue une ability traverse `ExecuteInternal`, dont"
        " `IsDeadUnitAndNotAllowedByAbility` est le PREMIER gate."),
    ("runner/operations/triggers/genestealer.py",
     "HypersensoryMoveAndSpawnDecoyAbility::_counter_attack"): (
        False, "IdunBattleLogic.Entities.Abilities.Triggered.Loki."
               "HypersensoryAbilitiesAbility_MoveAndSpawnDecoy$$CreateBehaviour",
        "Noeud DSL `AttackWithAttackDamage`. Le natif gate la vie de l'attaquant DANS L'ARBRE"
        " (`IsAlive(attaquant) & IsAlive(judh)`), et le port porte deja ce gate-la (`_counter_gate`)."
        " Y ajouter le gate d'ability serait un SECOND gate que le natif n'a pas."),
    ("runner/operations/triggers/loki/destroyer_hive.py",
     "DestroyerHiveAbility::execute_behaviour"): (
        False, "IdunBattleLogic.Entities.Abilities.Active.Loki.DestroyerHiveAbility$$CreateBehaviour",
        "Noeud DSL `AttackWithAttackDamage(caster, PickRandomly(GetValidTargets, 1), ...)`."
        " `GetValidTargets = Damageable(Enemies(AdjacentUnits(caster,1)))` : la cible est VIVANTE"
        " par construction du SELECTEUR, pas par un gate."),
    ("runner/operations/triggers/loki/hailstrike.py",
     "HailstrikeAttackAbility::execute_behaviour"): (
        False, "IdunBattleLogic.Entities.Abilities.Active.Loki.HailstrikeAttackAbility$$CreateBehaviour",
        "Noeud DSL `AttackWithAbilityDamage(...)` du `CreateBehaviour` d'une triggered ability :"
        " une triggered ability n'est PAS executee par `ActiveAbilityOperation`."),
    ("runner/operations/triggers/loki/haze_of_corruption.py",
     "HazeCorruptionBonusHitAbility::execute_behaviour"): (
        False, "IdunBattleLogic.Entities.Abilities.Active.Loki.HazeCorruption_BonusHitAbility"
               "$$CreateBehaviour",
        "Noeud DSL `AttackDamage(Owner@0x148, Target@0x178, ...)` dont le TRIGGER est"
        " `IsDead(Target@0x178)` : la cible est MORTE par construction et le natif la frappe"
        " quand meme, pour que le coup deborde en `LeftOverDamage`. LE site qui prouve qu'un"
        " gate en bloc sur-refuserait."),
}


def _rel(p: Path) -> str:
    return p.relative_to(ENGINE).as_posix()


class _Visiteur(ast.NodeVisitor):
    """Releve chaque appel `<X>.execute_ability_attack(...)` avec sa fonction englobante, et note
    si le corps de CETTE fonction appelle aussi le predicat du gate."""

    def __init__(self, rel: str):
        self.rel, self.pile, self.sites = rel, [], []

    def _porte(self, node) -> bool:
        return any(isinstance(n, ast.Name) and n.id == GATE_NAME
                   or isinstance(n, ast.Attribute) and n.attr == GATE_NAME
                   for n in ast.walk(node))

    def _fn(self, node):
        self.pile.append(node.name)
        self._corps = node
        self.generic_visit(node)
        self.pile.pop()

    visit_FunctionDef = _fn
    visit_AsyncFunctionDef = _fn

    def visit_ClassDef(self, node):
        self.pile.append(node.name)
        self.generic_visit(node)
        self.pile.pop()

    def visit_Call(self, node):
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr == "execute_ability_attack":
            self.sites.append({"fichier": self.rel, "ligne": node.lineno,
                               "fonction": "::".join(self.pile)})
        self.generic_visit(node)


def _fonctions_portant_le_gate(tree: ast.AST, rel: str) -> set:
    """`{qualname}` des fonctions dont le CORPS appelle le predicat du gate."""
    out, pile = set(), []

    def marche(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            pile.append(node.name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for n in ast.walk(node):
                    if isinstance(n, ast.Call):
                        f = n.func
                        nom = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
                        if nom == GATE_NAME:
                            out.add("::".join(pile))
            for ch in ast.iter_child_nodes(node):
                marche(ch)
            pile.pop()
        else:
            for ch in ast.iter_child_nodes(node):
                marche(ch)

    marche(tree)
    return out


def _scan() -> list:
    sites = []
    for f in sorted(ENGINE.rglob("*.py")):
        try:
            src = f.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = _rel(f)
        v = _Visiteur(rel)
        v.visit(tree)
        if not v.sites:
            continue
        gates = _fonctions_portant_le_gate(tree, rel)
        for s in v.sites:
            s["gate_pose"] = s["fonction"] in gates
            sites.append(s)
    return sites


def volet_tri() -> int:
    sites = _scan()
    vus = {(s["fichier"], s["fonction"]) for s in sites}
    attendus = set(TRI)

    print("--- CALL-SITES d'`AttackDamageOperation.execute_ability_attack` DANS engine/** ---")
    print("  %d appel(s), %d fichier(s), %d site(s) distinct(s)"
          % (len(sites), len({s["fichier"] for s in sites}), len(vus)))
    print("")
    for cle in sorted(attendus | vus):
        att = TRI.get(cle)
        lignes = sorted(s["ligne"] for s in sites if (s["fichier"], s["fonction"]) == cle)
        pose = {s["gate_pose"] for s in sites if (s["fichier"], s["fonction"]) == cle}
        etat = "GATE" if att and att[0] else ("NON GATE" if att else "?? INCONNU")
        print("  [%-8s] %s  %s" % (etat, cle[0], cle[1]))
        print("             lignes=%s  gate pose=%s"
              % (lignes or "ABSENT DU SCAN", (sorted(pose) if pose else "-")))
        if att:
            print("             natif : %s" % att[1])
            print("             %s" % att[2])
        print("")

    inconnus = sorted(vus - attendus)
    disparus = sorted(attendus - vus)
    # Le cliquet PROPREMENT DIT : le tri doit valoir pour l'arbre COURANT, pas pour celui du jour
    # ou il a ete ecrit. Trois facons de le casser, trois rouges.
    mal_poses = sorted(cle for cle in (vus & attendus)
                       if any(s["gate_pose"] != TRI[cle][0] for s in sites
                              if (s["fichier"], s["fonction"]) == cle))

    print("--- CLIQUET ---")
    print("  site(s) NON classe(s) (apparus depuis le tri) : %d %s"
          % (len(inconnus), inconnus or ""))
    print("  site(s) classe(s) mais DISPARUS du scan       : %d %s"
          % (len(disparus), disparus or ""))
    print("  site(s) dont la POSE contredit le tri         : %d %s"
          % (len(mal_poses), mal_poses or ""))
    if not sites:
        print("  ECHEC : le scan ne trouve RIEN -- son silence ne vaut rien.")
        return 1
    if inconnus or disparus or mal_poses:
        print("  ECHEC : le tri ne decrit plus l'arbre. Le RE-FAIRE site par site, au decompile.")
        return 1
    n_gate = sum(1 for v in TRI.values() if v[0])
    print("  OK : %d site(s) sur %d gate(s), et la pose du code correspond EXACTEMENT."
          % (n_gate, len(TRI)))
    return 0


# ---------------------------------------------------------------------------------- volet `gate`
#: Deux unites REELLES du catalogue -- il faut un `UnitContext` seede (`extra_pierce`, traits,
#: armure) pour que l'Operation de degat aille jusqu'au bout ; un ctx nu la fait lever.
_VIS_CASTER, _VIS_CIBLE = "ultraInceptorSgt", "tyranWingedPrime"


def _etat(hp_cible: int = 100000, caster_vis: str = None):
    """Deux unites adjacentes ; `2` est la cible. `rng` cale pour que les vecteurs tirent.
    PV eleves : on veut mesurer le DEGAT INFLIGE, pas une mort qui le tronquerait."""
    import gameconfig as GC
    from engine.entities.unit_context import UnitContext
    from engine.runner.state import Entity, State
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.components import (HealthComponent, OwnerComponent, PositionComponent,
                                          StatsComponent, UnitComponent)
    st = State()
    for uid, vis, team, col, row, hp in ((1, caster_vis or _VIS_CASTER, 1, 1, 1, 100000),
                                         (2, _VIS_CIBLE, 2, 2, 1, hp_cible)):
        e = Entity(uid)
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        e.add_component(OwnerComponent(team=team, player=team))
        e.add_component(PositionComponent(col=col, row=row))
        e.add_component(HealthComponent(hp=hp, hp_max=hp))
        cfg = GC.unit(vis) or {}
        ctx = UnitContext.from_snapshot(
            {"entityId": uid, "visualId": vis,
             "stats": {"attack": 1000, "health": int(hp), "fixedArmor": 0},
             "normalAttack": {"hits": 1}}, cfg)
        ctx.active_ability_level = 50
        ctx.passive_ability_level = 50
        ctx.ability_variables_multiplier = 100
        ctx.traits = list(cfg.get("traits") or [])
        e.add_component(StatsComponent(ctx=ctx))
        st.entities[uid] = e
    st.rng = IntBasedMersenneTwister(777)
    return st


def _tuer(st, uid: int):
    from engine.runner.components import HealthComponent, UnitComponent
    e = st.get_entity(uid)
    e.get_component(HealthComponent).hp = 0
    e.get_component(UnitComponent).alive = False


def _ability_hors_registre() -> tuple:
    """`(abilityId, visualId du porteur)` : une ability d'ATTAQUE active ABSENTE d'`ABILITY_CLASSES`
    -- donc qui atteint REELLEMENT le repli generique de `summon_ai` -- ET son porteur.

    DERIVE, jamais code en dur, pour deux raisons distinctes :
      * le registre GRANDIT a chaque tranche portee ; un id fige finirait par y entrer, la voie (1)
        le prendrait en charge et ce bras deviendrait MUET sans rougir ;
      * sans porteur reel, `ability_attack_params` rend des bornes NULLES et le bras vivant mesure
        `degat=0` des deux cotes -- un regime degenere qui ne discrimine rien.
    Porteur cherche parmi les SUMMONS d'abord (`summons` = la population meme de ce call-site),
    puis n'importe quel porteur si aucun summon ne convient."""
    import unit_map as UM
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.operations.summon_ai import _is_active_attack_ability
    from engine.entities.active_ability_type import ActiveAbilityType

    from engine.ai.state_bridge import _resolve_ability
    from engine.runner.abilities.base import ability_attack_params

    porteurs = {}
    for k in UM.all_kits():
        for nom in ((k.get("voies") or {}).get("active") or []):
            porteurs.setdefault(nom, []).append((k.get("id"), k.get("kind")))

    def bornes_non_nulles(aid: int, vis: str) -> bool:
        """Le 3e critere, et il ne s'infere PAS du catalogue : le repli lit `minDmg`/`maxDmg` par
        les cles PAR DEFAUT d'`ability_attack_params`. Une ability dont la config nomme sa variable
        autrement (`PrecisionShot` : `dmg`) rend des bornes NULLES -- le bras vivant mesurerait
        alors `degat=0` des deux cotes, un regime degenere sans pouvoir discriminant. On EXERCE
        donc le calcul reel plutot que de deviner."""
        try:
            nom, cfg = _resolve_ability(aid)
            prof = (cfg.get("constants") or {}).get("damageProfile")
            st = _etat(caster_vis=vis)
            _bmin, bmax, _p, hits = ability_attack_params(
                st, 1, nom, prof, ranged=(cfg.get("attackRangeType") == "Ranged"))
            return int(bmax) > 0 and int(hits) > 0
        except Exception:
            return False

    secours = None
    for a in ActiveAbilityType:
        aid = int(a)
        if aid in ABILITY_CLASSES:
            continue
        try:
            if not _is_active_attack_ability(aid):
                continue
        except Exception:
            continue
        for vis, kind in (porteurs.get(a.name) or []):
            if not bornes_non_nulles(aid, vis):
                continue
            if kind == "summons":
                return aid, vis
            if secours is None:
                secours = (aid, vis)
    return secours if secours is not None else (-1, None)


def _bras_foyer_nu(mutation: bool) -> int:
    """(c) Le FOYER `execute_ability_attack`, appele NU sur un cadavre. Rend le degat total."""
    from engine.runner.operations.damage import AttackDamageOperation
    st = _etat()
    _tuer(st, 2)
    r = AttackDamageOperation.execute_ability_attack(st, 1, 2, 40, 40, 0, 1,
                                                    damage_profile="DirectDamage", is_melee=True)
    return int((r or {}).get("total") or 0)


def _bras_summon(cible_morte: bool) -> tuple:
    """(a)/(b) Le repli generique de `summon_ai`, joue par le PORTEUR REEL de l'ability choisie,
    pour que les bornes de `ability_attack_params` soient non nulles.
    Rend `(routed, total DEMANDE, tirages RNG, abilityId)`.

    L'observable n'est PAS le delta de PV, et c'est structurel : sur un CADAVRE les PV valent deja
    0, donc `avant - apres` rend 0 que l'attaque parte ou non -- un bras muet qui se lirait comme
    un refus. On mesure donc ce que #429-r1-r1 mesurait : le total DEMANDE par l'Operation, et le
    nombre de tirages consommes (le natif, lui, n'en consomme AUCUN quand il refuse)."""
    from engine.runner.operations.summon_ai import _apply_active_ability
    aid, vis = _ability_hors_registre()
    st = _etat(caster_vis=vis)
    if cible_morte:
        _tuer(st, 2)
    n0 = int(st.rng.call_count)
    r = _apply_active_ability(st, 1, 2, aid)
    tirages = int(st.rng.call_count) - n0
    total = int(((r or {}).get("result") or {}).get("total") or 0)
    return (r.get("routed"), total, tirages, aid)


def _bras_haze() -> int:
    """(d) `HazeCorruptionBonusHitAbility.execute_behaviour` sur un cadavre : l'attaque part-elle ?
    Rend le total du coup bonus (0 = le site a ete refuse)."""
    from engine.runner.operations.triggers.loki.haze_of_corruption import (
        HazeCorruptionBonusHitAbility)
    from engine.runner.operations.damage import AttackDamageOperation
    st = _etat()
    _tuer(st, 2)
    vu = {"total": 0}
    orig = AttackDamageOperation.execute_ability_attack

    def espion(state, att, tgt, *a, **k):
        r = orig(state, att, tgt, *a, **k)
        vu["total"] = int((r or {}).get("total") or 0)
        return r
    # `ability_attack_params` a besoin d'un `ctx` que l'etat synthetique n'a pas -> on court-circuite
    # la RESOLUTION de config (hors sujet) et on garde ce qui est mesure ici : l'appel PART-IL ?
    import engine.runner.abilities.base as B
    orig_params = B.ability_attack_params
    try:
        AttackDamageOperation.execute_ability_attack = staticmethod(espion)
        B.ability_attack_params = lambda *a, **k: (40, 40, 0, 1)

        class _Ev:
            dying_id, killer_id, player_id = 2, 1, 1
        HazeCorruptionBonusHitAbility(owner_id=1).execute_behaviour(st, _Ev())
    finally:
        AttackDamageOperation.execute_ability_attack = orig
        B.ability_attack_params = orig_params
    return vu["total"]


def volet_gate() -> int:
    from engine.runner.operations.damage_ops import ability as A

    aid, vis = _ability_hors_registre()
    print("ability d'attaque active HORS `ABILITY_CLASSES` (derivee) : %s, portee par %s"
          % (aid, vis))
    if aid < 0:
        print("ECHEC : plus aucune ability n'atteint le repli generique -- le bras est MUET.")
        return 1
    print("")

    # ---- TEMOIN : l'arbre tel qu'il est livre -------------------------------------------------
    r_morte = _bras_summon(True)
    r_vive = _bras_summon(False)
    foyer = _bras_foyer_nu(False)
    haze = _bras_haze()
    print("--- TEMOIN (arbre livre) ---")
    print("  (a) summon_ai, cible MORTE    -> routed=%-26s total=%-6d tirages=%d"
          % (r_morte[0], r_morte[1], r_morte[2]))
    print("  (b) summon_ai, cible VIVANTE  -> routed=%-26s total=%-6d tirages=%d"
          % (r_vive[0], r_vive[1], r_vive[2]))
    print("  (c) FOYER `execute_ability_attack` nu, cadavre        -> total=%d" % foyer)
    print("  (d) HazeCorruption_BonusHit sur cadavre              -> total=%d" % haze)
    ok_a = r_morte[0] == "dead_target_not_allowed" and r_morte[1] == 0 and r_morte[2] == 0
    ok_b = r_vive[0] != "dead_target_not_allowed" and r_vive[1] > 0
    ok_c = foyer > 0
    ok_d = haze > 0
    print("  attendus : (a) refus/0 -> %s ; (b) PAS refuse -> %s ; (c) passe -> %s ; (d) passe -> %s"
          % (ok_a, ok_b, ok_c, ok_d))

    # ---- CONTRE-EPREUVE 1 : le gate DEBRANCHE -- (a) doit se remettre a frapper le cadavre ----
    # Sans elle, `degat=0` sur (a) serait indiscernable d'un montage inerte (bornes nulles, cible
    # hors portee, ability non resolue...) : c'est le chiffre du bras DEBRANCHE qui etablit qu'il y
    # avait bien un degat A REFUSER.
    # (le port importe le predicat DANS le corps de `_apply_active_ability` -> le lookup se fait a
    #  chaque appel sur le module, donc substituer l'attribut du module MORD bien.)
    import engine.runner.operations.active_ability as AA
    _orig_gate = AA.is_dead_unit_and_not_allowed_by_ability
    try:
        AA.is_dead_unit_and_not_allowed_by_ability = lambda *a, **k: False
        d_morte = _bras_summon(True)
    finally:
        AA.is_dead_unit_and_not_allowed_by_ability = _orig_gate
    print("")
    print("--- CONTRE-EPREUVE 1 : gate DEBRANCHE (le predicat rend toujours False) ---")
    print("  (a) summon_ai, cible MORTE  -> routed=%-22s total=%-6d tirages=%d"
          "  (temoin total=%d tirages=%d)"
          % (d_morte[0], d_morte[1], d_morte[2], r_morte[1], r_morte[2]))
    mord_a = (d_morte[1] > 0 and d_morte[2] > 0 and d_morte[0] != "dead_target_not_allowed")
    print("  le gate MORD (il y avait bien une attaque a refuser) : %s" % mord_a)
    if not mord_a:
        print("  ECHEC : gate debranche et TOUJOURS 0 -> le refus de (a) n'est pas attribuable")
        print("          au gate, mais a un montage inerte.")
        return 1

    # ---- CONTRE-EPREUVE 2 : et si on gatait le FOYER, comme le brief le redoutait ? ------------
    # On pose le gate en TETE d'`execute_ability_attack` -- exactement le « gate en bloc ». (c) et
    # (d) DOIVENT basculer, sinon la mutation n'a pas mordu et le temoin ne prouve rien.
    from engine.runner.operations.active_ability import is_dead_unit_and_not_allowed_by_ability
    orig = A._AbilityAttack.execute_ability_attack

    def gate_en_bloc(state, attacker_id, target_id, *a, **k):
        if is_dead_unit_and_not_allowed_by_ability(state, None, target_id):
            return None
        return orig(state, attacker_id, target_id, *a, **k)

    from engine.runner.operations.damage import AttackDamageOperation
    orig_pub = AttackDamageOperation.execute_ability_attack
    try:
        A._AbilityAttack.execute_ability_attack = staticmethod(gate_en_bloc)
        AttackDamageOperation.execute_ability_attack = staticmethod(gate_en_bloc)
        m_foyer = _bras_foyer_nu(True)
        m_haze = _bras_haze()
    finally:
        A._AbilityAttack.execute_ability_attack = orig
        AttackDamageOperation.execute_ability_attack = orig_pub

    print("")
    print("--- CONTRE-EPREUVE 2 : gate pose EN BLOC sur le foyer ---")
    print("  (c) FOYER nu, cadavre                 -> total=%d  (temoin %d)" % (m_foyer, foyer))
    print("  (d) HazeCorruption_BonusHit, cadavre  -> total=%d  (temoin %d)" % (m_haze, haze))
    mord = (m_foyer == 0 and m_haze == 0)
    print("  la mutation MORD et DIFFERE du temoin : %s" % mord)
    if not mord:
        print("  ECHEC : mutation sans effet -> le VERT du temoin ne prouve rien.")
        return 1

    # L'arbre livre doit avoir ete RESTAURE (sinon la mesure suivante heriterait de la mutation).
    if _bras_haze() != haze:
        print("  ECHEC : restauration incomplete apres mutation.")
        return 1

    ok = ok_a and ok_b and ok_c and ok_d
    print("")
    print("VERDICT : %s" % ("OK -- le gate mord SUR LA SEULE porte triee GATE, et les sites"
                            " NON gates passent encore." if ok else "ECHEC"))
    return 0 if ok else 1


# ---------------------------------------------------------------------------------- volet `live`
def volet_live(hp: str, seed: str) -> int:
    """Le bras qui compte : un site NON gate passe-t-il ENCORE, cote natif comme cote port ?

    Montage = celui de case-209 (`probe_209_haze_damage_transfer`), regime `hp` ou la cible meurt
    AVANT le dernier coup : le coup BONUS de `HazeCorruption_BonusHitAbility` tombe alors sur le
    CADAVRE, et sa `LeftOverDamage` est reportee sur le relais bonde. Trois bras :
      1. NATIF   : ce que le relais encaisse reellement (evenements de degat) ;
      2. PORT    : ce que le rejeu offline lui inflige, arbre LIVRE ;
      3. PORT MUTE : le meme rejeu avec le gate pose EN BLOC sur le foyer.
    Si (3) == (2), la distinction gate/non-gate n'est pas observable et le tri n'est pas
    attribuable."""
    import importlib
    P = importlib.import_module("probe_209_haze_damage_transfer")

    class _A:
        armor, k, dump_events = 0, 1, False

    def relais(r):
        live = sum(int(td["tags"]["Amount"]) for td in r["events"]
                   if "Amount" in td["tags"] and td["tags"].get("Target_Id") == r["relay"])
        port = None
        for e in r["off_entities"]:
            if e.get("id") == r["relay"] and e.get("hp") is not None:
                port = int(r["hp"]) - int(e["hp"])
        return live, port

    rpc = P._mkrpc()
    r = P._run(rpc, seed, int(hp), _A())
    if r is None:
        print("MONTAGE KO (seed %s hp %s) -- rien mesure, aucun verdict rendu." % (seed, hp))
        return 2
    live, port = relais(r)
    print("--- HAZE OF CORRUPTION -- seed %s, PV cible %s, board de case-207 ---" % (seed, hp))
    print("  coup BONUS evalue/fire (rejeu port) : %s" % r["trace"])
    print("  relais %s : NATIF %s  |  PORT (arbre livre) %s" % (r["relay"], live, port))

    from engine.runner.operations.damage_ops import ability as A
    from engine.runner.operations.damage import AttackDamageOperation
    from engine.runner.operations.active_ability import is_dead_unit_and_not_allowed_by_ability
    orig, orig_pub = A._AbilityAttack.execute_ability_attack, \
        AttackDamageOperation.execute_ability_attack

    def gate_en_bloc(state, attacker_id, target_id, *a, **k):
        if is_dead_unit_and_not_allowed_by_ability(state, None, target_id):
            return None
        return orig(state, attacker_id, target_id, *a, **k)

    try:
        A._AbilityAttack.execute_ability_attack = staticmethod(gate_en_bloc)
        AttackDamageOperation.execute_ability_attack = staticmethod(gate_en_bloc)
        r2 = P._run(rpc, seed, int(hp), _A())
    finally:
        A._AbilityAttack.execute_ability_attack = orig
        AttackDamageOperation.execute_ability_attack = orig_pub
    if r2 is None:
        print("MONTAGE KO au bras MUTE -- contre-epreuve non rendue.")
        return 2
    live2, port2 = relais(r2)
    print("  relais %s : NATIF %s  |  PORT (gate EN BLOC) %s" % (r2["relay"], live2, port2))
    print("")
    accord = (live == port)
    discrimine = (port2 != port)
    print("  accord natif/port sur l'arbre LIVRE       : %s" % accord)
    print("  le gate EN BLOC CHANGE le resultat        : %s" % discrimine)
    if not discrimine:
        print("  ECHEC : la mutation ne discrimine pas -> ce montage ne prouve rien sur le tri.")
        return 1
    if not accord:
        print("  ECHEC : le port livre ne reproduit deja pas le natif sur ce montage.")
        return 1
    print("  OK : le natif frappe le cadavre par la voie DSL, le port livre aussi, et un gate")
    print("       pose en bloc le lui interdirait -> le tri est ATTRIBUABLE.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volet", choices=("tri", "gate", "live"), required=True)
    ap.add_argument("--hp", default="5000", help="PV de la cible (volet live)")
    ap.add_argument("--seed", default="777")
    a = ap.parse_args()
    if a.volet == "tri":
        return volet_tri()
    if a.volet == "gate":
        return volet_gate()
    return volet_live(a.hp, a.seed)


if __name__ == "__main__":
    raise SystemExit(main())
