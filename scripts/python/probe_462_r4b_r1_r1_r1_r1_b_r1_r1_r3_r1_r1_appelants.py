"""#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r1 (+ -r2) -- CE QUE LE PORT SAIT D'UNE UNITE MORTE :
l'ENUMERATION des appelants du substrat `unit_state`, et le REGISTRE des triggered-abilities.

Deux residus, un seul substrat -- << une entite chargee MORTE >> (dite CADAVRE-AU-CHARGEMENT :
presente dans `decisionView.units[]`, `alive == False`, SANS `StatsComponent` parce que
`combatSnapshot` n'enumere que les `IsAlive`).

  * `-r1` : les DEUX sites `INDECIDABLE` de la ventilation `#462-...-r3-r1`
    (`runner/components.py::UnitEffectStateView.__init__` et `playbook/scene.py::Scene.unit_state`)
    lisent `ctx.traits` BRUT. Le seul driver enumere (`refresh_stat_modifier_effects`) sort sur
    `us is None`, mais les AUTRES appelants n'avaient PAS ete enumeres. Ce probe les enumere -- par
    AST, jamais par grep -- et les VENTILE.
  * `-r2` : `triggers/dispatch/core.py::collect_triggered_abilities` fait `if sc is None: continue`,
    donc un cadavre-au-chargement est HORS du registre. La question natif etait ouverte ; elle est
    tranchee ici (`--step registre`).

CE QUE LA MESURE A CHANGE PAR RAPPORT A L'ENONCE DES DEUX RESIDUS :

  1. La degradation permissive a UN SEUL consommateur, et il se MESURE (`--step consommateur`).
     `-r1` dit << cle `traits` absente ⇒ une condition de TRAIT rend VRAI (#208) >>, ce qui est
     exact -- mais une seule `is_active` de tout `engine/` lit cette cle. Un site n'est donc un
     gisement que si son sujet peut etre un cadavre ET que le consommateur aval lit CET effet-la.
  2. La question de `-r2` ne se tranche PAS sur `AbilityAndEffectCache` : elle se tranche un cran
     plus bas, sur `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger`
     (`--step registre`).

100 % OFFLINE. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
if str(ICI) not in sys.path:
    sys.path.insert(0, str(ICI))

ENGINE = ICI / "engine"


# ================================================================================================
# INVENTAIRE -- AST, jamais grep
# ================================================================================================
def _proprio(tree: ast.AST) -> dict:
    """{ligne: nom de la fonction/classe la PLUS INTERIEURE qui la couvre}."""
    owner: dict = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for i in range(n.lineno, (n.end_lineno or n.lineno) + 1):
                prev = owner.get(i)
                owner[i] = (n.name, n.lineno) if prev is None or n.lineno > prev[1] else prev
    return owner


def _fichiers():
    for dirpath, _d, files in os.walk(ENGINE):
        for fn in sorted(files):
            if fn.endswith(".py"):
                p = Path(dirpath) / fn
                yield os.path.relpath(p, ENGINE).replace("\\", "/"), p


# Les DEUX faces du meme substrat. La cle de ventilation est `(fichier, fonction, methode)` : elle
# survit a un deplacement de lignes, ce qu'un couple `(fichier, ligne)` ne fait pas.
_METHODES = {
    "active_effects": "COMBAT",       # `EffectsState.active_effects(uid, unit_state)`
    "unit_state": "DECISION",         # `Scene.unit_state(uid)` -- le substrat lui-meme
}


def sites() -> list:
    """Tous les appels `<x>.active_effects(...)` et `<x>.unit_state(...)` sous `engine/`.

    Rend `(fichier, fonction, methode, face, ligne, arg0)`. Le foyer `EffectsState.active_effects`
    et `Scene.unit_state` (les DEFINITIONS) sont exclus : ce sont les substrats, pas des appelants.
    """
    out = []
    for rel, p in _fichiers():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        owner = _proprio(tree)
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
                continue
            face = _METHODES.get(n.func.attr)
            if face is None:
                continue
            fn = owner.get(n.lineno, ("<module>", 0))[0]
            if (rel, fn) in (("entities/effects_state.py", "active_effects"),
                             ("playbook/scene.py", "unit_state")):
                continue                              # la DEFINITION, pas un appelant
            arg0 = ast.unparse(n.args[0]) if n.args else "<aucun>"
            out.append((rel, fn, n.func.attr, face, n.lineno, arg0))
    return out


def cle(s) -> tuple:
    return (s[0], s[1], s[2])


# ================================================================================================
# VENTILATION -- un verdict PAR CLE, avec son MOTIF
# ================================================================================================
# Verdicts (memes noms que `probe_462_..._r3_r1_substrat_traits.py`, pour qu'un lecteur qui connait
# l'un lise l'autre) :
#   INERTE-VIVANT  le sujet est un COMBATTANT du coup en cours (attaquant / defenseur / caster /
#                  cible) : il est vivant par construction du vecteur qui appelle
#   INERTE-AMONT   un gate ANTERIEUR (dans la meme fonction) refuse le cadavre avant la lecture
#   INERTE-AVAL    la lecture est atteinte, mais le CONSOMMATEUR ne lit aucun effet degrade
#   ATTEIGNABLE    le sujet PEUT etre un cadavre-au-chargement, et rien dans la fonction ne l'ecarte
#   NON-VENTILE    face DECISION -- enumere, pas trie (residu, cf. l'en-tete de `step_ventilation`)
VENTILATION = {
    # ---- face COMBAT : les sujets qui sont des COMBATTANTS ------------------------------------
    ("runner/damage_model.py", "attacker_modifiers", "active_effects"):
        ("INERTE-VIVANT", "`unit_id` = l'ATTAQUANT du coup en cours"),
    ("runner/damage_model.py", "defender_modifiers", "active_effects"):
        ("INERTE-VIVANT", "DEUX appels dans cette fonction, et ils ne sont pas de meme nature : "
                          "le PREMIER porte sur `unit_id` = le DEFENDEUR du coup (vivant par "
                          "construction -- le ciblage natif ne rend pas un mort cible legale) ; le "
                          "SECOND balaie les porteurs d'aura et porte son propre gate `hp <= 0`, "
                          "cf. la note de `_apply_ally_attack_damage_auras`"),
    ("runner/damage_model.py", "apply_trench_reduction", "active_effects"):
        ("INERTE-VIVANT", "`target_id` = la CIBLE du coup"),
    ("runner/damage_model.py", "_has_no_elev", "active_effects"):
        ("INERTE-VIVANT", "appele sur `attacker_id` PUIS `target_id` -- les deux combattants"),
    ("runner/abilities/base.py", "ability_pierce_effect_bonus", "active_effects"):
        ("INERTE-VIVANT", "`caster_id` = le CASTER : un mort ne caste pas"),
    ("runner/operations/repair.py", "_repair_modifier", "active_effects"):
        ("INERTE-VIVANT", "`target_id` d'un REPAIR ; `IdunBattle.Core.Services.AttackQuery$$"
                          "EntityCanBeRepaired` gate la cible en amont du vecteur"),
    ("runner/operations/damage_ops/ability.py", "execute_ability_attack", "active_effects"):
        ("INERTE-VIVANT", "`target_id` de l'attaque d'ability en cours"),
    ("runner/components.py", "unit_prevents_overkill", "active_effects"):
        ("INERTE-VIVANT", "`unit_id` = l'unite dont on decide l'OVERKILL, donc celle qu'on est en "
                          "train de tuer : elle est vivante a l'instant du test"),
    ("runner/operations/triggers/loki/reactivate_overwatch.py", "matches", "active_effects"):
        ("INERTE-AMONT", "`self.owner_id` -- le gate d'owner de `evaluate_trigger_operation` "
                         "(`CanGetAbilityTrigger`, `uc.alive` sauf `fire_on_death`) precede tout "
                         "`matches`, et cette classe ne porte PAS `fire_on_death`"),

    # ---- face COMBAT : les BALAYAGES d'entites -- c'est la que le gisement se joue -------------
    ("runner/damage_model.py", "normal_attack_per_hit_range", "active_effects"):
        ("INERTE-AMONT", "`if sc is None: return None` SIX lignes plus haut -- un "
                         "cadavre-au-chargement n'atteint jamais la lecture"),
    ("runner/damage_model.py", "_apply_ally_attack_damage_auras", "active_effects"):
        ("INERTE-AMONT", "balayage de `state.entities`, gate `hc.hp <= 0 -> continue` juste "
                         "au-dessus. ⚠ Le gate est sur les PV, pas sur `uc.alive` : il tient parce "
                         "que `snapshot._hp_by_id` lit `observe.units[].hp`, qui vaut 0 pour un "
                         "mort. Une capture sans `hp` (cle absente -> `HealthComponent` non pose) "
                         "le rendrait inerte"),
    ("runner/damage_model.py", "build_hits_board", "active_effects"):
        ("INERTE-AMONT", "balayage de `state.entities` sous le gate `#57m` "
                         "(`uid != tgt_id and not _uc.alive -> continue`) : le board natif est une "
                         "OCCUPATION DE TUILE, un mort n'y est plus"),
    ("runner/operations/damage.py", "_crit_carriers", "active_effects"):
        ("INERTE-AMONT", "meme balayage, meme gate `#57m` que `build_hits_board`"),
    ("runner/operations/additional_hits.py", "collect_additional_hit_groups", "active_effects"):
        ("INERTE-AMONT", "balayage de `state.entities`, gate `not uc.alive -> continue`"),
    ("runner/damage_model.py", "defender_fixed_armor", "active_effects"):
        ("ATTEIGNABLE", "LE SEUL des six balayages qui n'avait AUCUN gate de vivacite : ses filtres "
                        "etaient `OwnerComponent`, `PositionComponent` et l'egalite d'equipe. Un "
                        "cadavre-au-chargement de l'equipe du defenseur, s'il a une position, ETAIT "
                        "visite -- et `decisionView.units[]` conserve les morts, donc "
                        "`snapshot._load_stats_and_effects` les seede dans `EffectsState`. "
                        "TRAITE PAR CETTE TRANCHE (gate `uc.alive`, cf. `--step gates`) ; ce que le "
                        "gate ferme et ce qu'il ne ferme PAS : `--step gisement`"),

    # ---- face DECISION : le pendant du substrat ------------------------------------------------
    ("playbook/scene.py", "effects", "unit_state"):
        ("NON-VENTILE", "`Scene.effects(uid)` -- le PORTAIL de la face DECISION : ~30 appelants "
                        "sous `playbook/`, non tries par cette tranche (residu "
                        "`#462-...-r3-r1-r1-r1`). Ce qui EST mesure ici : la `Scene` porte bien "
                        "des morts (`build_scene_ctx` construit `pos_by_id`/`team_by_id`/`hp_by_id`"
                        " et le `EffectsState` depuis TOUT `dv.units`), alors que `ctx_by_id` vient"
                        " du `predictor`, donc de `combatSnapshot`, donc des VIVANTS seuls"),
    ("playbook/savior_protocols.py", "_target_has_active_markerlight", "unit_state"):
        ("INERTE-VIVANT", "`target_uid` est un VOISIN du mover, resolu par le selecteur "
                          "`AdjacentFriends` de `SaviorProtocols` -- meme argument `#57m` que "
                          "`build_hits_board` : le board est une occupation de tuile"),
    # Les DEUX fonctions ci-dessus appellent `unit_state` PUIS `active_effects` : elles portent donc
    # une cle par METHODE, et c'est voulu -- ce sont deux lectures distinctes du meme substrat.
    ("playbook/savior_protocols.py", "_target_has_active_markerlight", "active_effects"):
        ("INERTE-VIVANT", "meme sujet que la ligne `unit_state` ci-dessus, meme motif"),
    ("playbook/scene.py", "effects", "active_effects"):
        ("NON-VENTILE", "meme sujet que la ligne `unit_state` ci-dessus, meme residu"),
}

VERDICTS_A_TRAITER = ("ATTEIGNABLE",)


# ================================================================================================
# CONSOMMATEUR -- qui LIT la cle `traits` du `unit_state` ? (le rayon de souffle, mesure)
# ================================================================================================
def consommateurs_cle_traits() -> list:
    """Toute lecture `<x>.get("traits")` sous `engine/entities/effects/` dont le `<x>` est le
    parametre `unit_state` d'une methode `is_active`.

    C'est le RAYON DE SOUFFLE de la degradation permissive : une cle `traits` absente ne peut
    changer un verdict que la ou une `is_active` la lit. Le mesurer evite de traiter les 16 autres
    sites comme s'ils portaient tous le meme risque."""
    out = []
    for rel, p in _fichiers():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == "is_active"):
                continue
            noms = {a.arg for a in n.args.args}
            for c in ast.walk(n):
                if (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                        and c.func.attr == "get" and len(c.args) >= 1
                        and isinstance(c.args[0], ast.Constant) and c.args[0].value == "traits"):
                    # le receveur remonte-t-il au parametre `unit_state` ?
                    cur = c.func.value
                    while isinstance(cur, (ast.BoolOp, ast.Call)):
                        cur = (cur.values[0] if isinstance(cur, ast.BoolOp) else cur.func)
                    src = ast.unparse(c.func.value)
                    if any(nm in src for nm in noms):
                        out.append((rel, n.name, c.lineno, src))
    return out


# ================================================================================================
# REGISTRE (-r2) -- ce que le natif fait d'un cadavre, et ou la question se tranche
# ================================================================================================
def porteurs_fire_on_death() -> list:
    """Toute classe de `engine/runner/operations/triggers/**` qui pose `fire_on_death = True`,
    avec l'evenement qu'elle ecoute.

    POURQUOI CETTE LISTE EST LE BON RECENSEMENT. Le residu `-r2` demandait si
    `IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache` retire l'entite a la mort. La
    reponse se lit un cran PLUS BAS, et elle est STRUCTURELLE :
    `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` teste
    `IdunBattle.Entities.UnitExtensions$$IsAlive(owner)` A LA LECTURE, sous une exemption
    `IsAtomic(ability)` :

        if (!IsAtomic(ability)) { if (IsUnit(owner) && !IsAlive(owner))  return 0; }
        if (IsUnit(owner) && IsTriggersDisabled(owner))                 return 0;

    Si le cache retirait les morts, CE gate et SON exemption seraient tous deux INATTEIGNABLES --
    la branche atomique n'existe QUE pour laisser passer un owner MORT. Le cache CONSERVE donc les
    entites mortes, et c'est `CanGetAbilityTrigger` qui trie.

    ⇒ le `if sc is None: continue` du port et le gate natif rendent le MEME verdict pour toute
    ability NON atomique. Ils ne divergent que sur les ATOMIQUES -- que le port nomme
    `fire_on_death`. D'ou ce recensement : un porteur ne peut diverger que si son EVENEMENT peut
    encore se produire APRES sa propre mort."""
    base = ENGINE / "runner" / "operations" / "triggers"
    out = []
    for p in sorted(base.rglob("*.py")):
        rel = os.path.relpath(p, ENGINE).replace("\\", "/")
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not isinstance(n, ast.ClassDef):
                continue
            champs = {}
            for st in n.body:
                if (isinstance(st, ast.Assign) and len(st.targets) == 1
                        and isinstance(st.targets[0], ast.Name)):
                    champs[st.targets[0].id] = ast.unparse(st.value)
            if champs.get("fire_on_death") == "True":
                out.append((rel, n.name, champs.get("event_id"), champs.get("event_ids"),
                            _face_de(rel, n.name)))
    return out


def _face_de(rel: str, nom: str) -> str:
    """La FACE de la classe -- `EffectTrigger` ou `TriggeredAbility` -- resolue par la vraie MRO.

    ⚠ PAS par le nom de sa base a l'AST : `RitesOfMorkaiReviveTrigger(ReviveEffectTrigger)` derive
    d'`EffectTrigger` par un INTERMEDIAIRE, et un test de nom de base le rendait << NON TRIE >>.
    C'est la meme faute de forme que << l'absence dans une table ne prouve rien >> : un critere
    superficiel rend un faux verdict, pas une mesure. Le probe est offline, l'import ne coute rien."""
    import importlib
    mod = importlib.import_module("engine." + rel[:-3].replace("/", "."))
    cls = getattr(mod, nom, None)
    if cls is None:                                   # classe PRIVEE renommee/absente du module
        return "INCONNUE"
    from engine.runner.operations.triggers.base import EffectTrigger
    return "EFFET" if issubclass(cls, EffectTrigger) else "ABILITY"


# Un porteur `fire_on_death` DIVERGE (port vs natif) sur un cadavre-au-chargement seulement si son
# evenement peut se produire APRES sa mort. Tous ceux dont l'evenement EST leur propre mort sont
# structurellement inertes : l'evenement a deja eu lieu avant la capture, il ne se reproduira pas.
_EVENTS_DE_SA_PROPRE_MORT = (
    "EventTriggerType.PreUnitDeath", "EventTriggerType.PreUnitDeath_2",
    "EventTriggerType.UnitDeath", "EventTriggerType.UnitDefeated",
    "EventTriggerType.PendingDeathAdded",
)

# Les porteurs qui ecoutent AUTRE CHOSE, nommes un par un avec leur consequence mesuree.
REGISTRE_HORS_MORT = {
    "EnvAmbushResurrectAbility":
        ("DIVERGENT-DOUBLE-GATE",
         "`On(TurnStart_Actions = 22)` : l'evenement se reproduit a CHAQUE tour, donc le natif "
         "evalue bien ce trigger pour un cadavre-au-chargement porteur du trait Ambush, la ou le "
         "port ne l'inscrit meme pas. AUCUNE consequence observable, et c'est un DOUBLE gate qui "
         "l'assure : (1) le behaviour est GLOBAL (il enumere TOUS les eligibles), donc toute autre "
         "instance inscrite produit le meme effet ; (2) `_eligible_for_resurrect` exige "
         "`turn_defeated is not None`, que rien ne seede au chargement. Ce qui reste OUVERT est le "
         "cas ou le SEUL porteur Ambush du plateau est un cadavre-au-chargement -- residu "
         "`#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1`"),
}


def _est_effect_trigger(face: str) -> bool:
    return face == "EFFET"


# ================================================================================================
# GATES DE VIVACITE -- les SIX balayages d'entites, et la preuve qu'ils portent tous leur gate
# ================================================================================================
# Un balayage de `state.entities` qui appelle `active_effects` sur CHAQUE entite visitee doit
# ecarter les morts : le board natif est une OCCUPATION DE TUILE (`#57m`). Le criteres est LU au
# source (AST) : une lecture de l'attribut `alive`, ou une comparaison sur `hp`.
BALAYAGES = {
    ("runner/damage_model.py", "defender_fixed_armor"):
        "aura FixedArmor de `ProtectorImperative` (gate pose par cette tranche)",
    ("runner/damage_model.py", "_apply_ally_attack_damage_auras"):
        "auras +degat alliees (Conqueror / BeaconOfRage)",
    ("runner/damage_model.py", "defender_modifiers"):
        "porteurs de malus de defense",
    ("runner/damage_model.py", "build_hits_board"):
        "board des COUPS (`#57m`)",
    ("runner/operations/damage.py", "_crit_carriers"):
        "univers des deux canaux CRIT (`#57m`)",
    ("runner/operations/additional_hits.py", "collect_additional_hit_groups"):
        "groupes de coups additionnels",
}


def _fonction_ast(fichier: str, fonction: str):
    tree = ast.parse((ENGINE / fichier).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fonction:
            return n
    return None


def etat_gates() -> list:
    """Pour chaque balayage : `(cle, lit_alive, compare_hp, motif)`.

    Un balayage passe s'il porte l'UN des deux (les deux formes existent dans l'arbre et sont
    toutes deux fideles : `uc.alive` est le mirror direct, `hp <= 0` la derivation par les PV)."""
    out = []
    for cle_, motif in sorted(BALAYAGES.items()):
        fn = _fonction_ast(*cle_)
        lit_alive = compare_hp = False
        if fn is not None:
            lit_alive = any(isinstance(n, ast.Attribute) and n.attr == "alive"
                            for n in ast.walk(fn))
            compare_hp = any(isinstance(n, ast.Compare)
                             and isinstance(n.left, ast.Attribute) and n.left.attr == "hp"
                             for n in ast.walk(fn))
        out.append((cle_, lit_alive, compare_hp, motif))
    return out


# ================================================================================================
# STEPS
# ================================================================================================
def step_inventaire() -> int:
    lst = sites()
    print("INVENTAIRE -- appelants du substrat `unit_state` sous `engine/` (AST, jamais grep)")
    print("")
    par_face = {}
    for s in lst:
        par_face.setdefault(s[3], []).append(s)
    for face in sorted(par_face):
        rows = sorted(par_face[face], key=lambda r: (r[0], r[4]))
        print("  face %s : %d appel(s)" % (face, len(rows)))
        for r in rows:
            print("      %-52s %5d  %-34s uid=%s" % (r[0], r[4], r[1], r[5]))
        print("")
    print("appels TOTAL : %d  --  cles DISTINCTES : %d" % (len(lst), len({cle(s) for s in lst})))
    return 0


def step_ventilation() -> int:
    lst = sites()
    trouves = {cle(s) for s in lst}
    print("VENTILATION -- le sujet de chaque appelant peut-il etre un CADAVRE-AU-CHARGEMENT ?")
    print("")
    par_verdict = {}
    for c in sorted(trouves):
        v, motif = VENTILATION.get(c, ("NON-VENTILE", "site NEUF : a ventiler"))
        par_verdict.setdefault(v, []).append((c, motif))
    for v in sorted(par_verdict):
        print("  %-14s %d" % (v, len(par_verdict[v])))
        for c, motif in par_verdict[v]:
            print("      %s::%s  (%s)" % (c[0], c[1], c[2]))
            for i in range(0, len(motif), 96):
                print("          %s" % motif[i:i + 96])
        print("")
    manquantes = sorted(trouves - set(VENTILATION))
    orphelines = sorted(set(VENTILATION) - trouves)
    print("cles TOTAL : %d  --  non ventilees : %d  --  orphelines : %d"
          % (len(trouves), len(manquantes), len(orphelines)))
    if manquantes:
        print("  NON VENTILEES : %r" % (manquantes,))
    if orphelines:
        print("  ORPHELINES    : %r" % (orphelines,))
    return 1 if (manquantes or orphelines) else 0


def step_consommateur() -> int:
    cons = consommateurs_cle_traits()
    print("RAYON DE SOUFFLE -- qui LIT la cle `traits` du `unit_state` dans une `is_active` ?")
    print("")
    for rel, fn, ln, src in cons:
        print("  %-52s %5d  %s.get(\"traits\")" % (rel, ln, src))
    print("")
    print("consommateurs : %d" % len(cons))
    print("")
    print("LECTURE. La degradation << cle absente ⇒ condition de TRAIT VRAIE >> ne peut changer un")
    print("verdict QUE la. Un appelant ATTEIGNABLE dont le consommateur aval ne lit pas cet effet-la")
    print("ne porte donc AUCUN ecart par ce canal -- ce qui ne veut pas dire qu'il n'en porte pas")
    print("d'autre (cf. `--step gisement`).")
    return 0 if cons else 1        # un recensement VIDE serait un faux vert : on l'assertionne


def step_gisement() -> int:
    """Ce que le SEUL site ATTEIGNABLE produit -- et pourquoi ce n'est PAS le defaut `traits`."""
    print("LE SEUL SITE ATTEIGNABLE -- `damage_model.py::defender_fixed_armor`")
    print("")
    print("Son balayage retient un porteur d'aura sur trois criteres : `OwnerComponent`,")
    print("`PositionComponent`, meme equipe que le defenseur. AUCUN gate de vivacite, la ou ses")
    print("CINQ freres en portent un (`build_hits_board` et `_crit_carriers` par `#57m`,")
    print("`collect_additional_hit_groups` par `uc.alive`, `_apply_ally_attack_damage_auras` et le")
    print("second appel de `defender_modifiers` par `hp <= 0`).")
    print("")
    print("DEUX ECARTS DISTINCTS s'y superposent, et les confondre ferait corriger le mauvais :")
    print("")
    print("  A. LA CLE `traits` (le defaut nomme par le residu) -- SANS CONSEQUENCE ICI.")
    print("     Le seul consommateur de cette cle est `PinnedEffect.is_active`")
    print("     (`PinnedEffect$$CreateActiveCondition` = `Not(HasTrait(Self, 0x40f =")
    print("     TerminatorArmour))`), un effet de REDUCTION DE DEGAT. `defender_fixed_armor` ne lit")
    print("     que l'aura `FixedArmor` de `ProtectorImperative` : le `Pinned` d'un cadavre y est")
    print("     invisible, actif ou non.")
    print("")
    print("  B. LE GATE DE VIVACITE ABSENT -- c'est LUI, l'ecart, et il est PLUS LARGE.")
    print("     Un cadavre-au-chargement projette son aura `FixedArmor`. Le natif ne le peut pas :")
    print("     `IdunBattle.Operations.KillUnitOperation$$Execute` appelle TROIS fois")
    print("     `RemoveEffects(killed, <step>)`, donc une unite morte EN BATAILLE n'a plus d'effet")
    print("     a projeter -- et c'est aussi pourquoi l'ecart est INERTE EN FAIT aujourd'hui :")
    print("     `decisionView.units[].effects` est VIDE pour un mort, donc `active_effects` rend")
    print("     `[]` et le `if not effs: continue` qui suit l'ecarte. INERTE PAR UNE PROPRIETE DU")
    print("     CAPTEUR, PAS PAR UN GATE DU PORT : rien ne garde cette propriete, et un etat")
    print("     construit hors capture (montage, greffe, seed synthetique) la viole sans erreur.")
    print("")
    print("Le gate `uc.alive` pose par cette tranche ferme B et aligne le site sur ses cinq freres.")
    return 0


def step_registre() -> int:
    lst = porteurs_fire_on_death()
    print("REGISTRE (-r2) -- un cadavre-au-chargement porte-t-il ses triggered-abilities ?")
    print("")
    print("REPONSE NATIVE, et elle ne se lit PAS sur `AbilityAndEffectCache` :")
    for ligne in (porteurs_fire_on_death.__doc__ or "").split("\n")[2:]:
        s = ligne.strip()
        if s:
            print("  %s" % s)
    print("")
    print("PORTEURS `fire_on_death` du port (= mirror d'`IsAtomic`), et leur evenement :")
    print("")
    rc = 0
    for rel, nom, evid, evids, face in lst:
        ev = evid or evids or "<aucun au niveau classe>"
        if _est_effect_trigger(face):
            etat = "INERTE-FACE  (EffectTrigger : `_owner_gate_applies` est FAUX, aucun gate)"
        elif any(k in (ev or "") for k in _EVENTS_DE_SA_PROPRE_MORT):
            etat = "INERTE-EVENT (l'evenement EST sa propre mort : deja eu lieu avant la capture)"
        elif nom in REGISTRE_HORS_MORT:
            etat = "%s" % REGISTRE_HORS_MORT[nom][0]
        else:
            etat = "NON TRIE  <-- ROUGE : evenement hors mort, non instruit"
            rc = 1
        print("  %-34s %-46s %s" % (nom, ev, etat))
        print("        %s" % rel)
    print("")
    for nom, (_e, motif) in sorted(REGISTRE_HORS_MORT.items()):
        print("  %s :" % nom)
        for i in range(0, len(motif), 96):
            print("      %s" % motif[i:i + 96])
    print("")
    print("porteurs : %d" % len(lst))
    return rc


_STEPS = {"inventaire": step_inventaire, "ventilation": step_ventilation,
          "consommateur": step_consommateur, "gisement": step_gisement,
          "registre": step_registre}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", choices=sorted(_STEPS), default="ventilation")
    a = ap.parse_args()
    return _STEPS[a.step]()


if __name__ == "__main__":
    raise SystemExit(main())
