"""#910-r1 -- LES DEUX CANAUX `EffectBonus` ACCUSES PAR LA FICHE, RE-MESURES UN PAR UN.

La fiche annonce que la face DECISION ignore les DEUX canaux (percage et crit-degat). Re-mesure au
decompile du build courant : **UN SEUL des deux est un ecart**. L'autre est une PROPRIETE DU NATIF,
et le porter ferait mordre le canal PLUS LARGE que le jeu.

## AXE CRIT -- REFUTE

`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` est le SEUL corps de prediction
(`PredictAttack` -> lui ; `DamagePredictionQuery$$GetAttackPrediction` ne fait que monter
l'`AttackPredictionRequest` puis appeler le slot 5). Son decompile INTEGRAL (2782 lignes) ne
contient AUCUN appel a `GetCritChance`, `GetCritDamage` ni `CalculateCriticalDamage` -- les trois
seuls corps qui consomment `GetCritChanceBonusFromEffects` / `GetCritDamageBonusFromEffects` :

    GetCritChance(attacker, defender, hitIndex, ability)
        = clamp(0, 100, GetStat(attacker, 9) + GetCritChanceBonusFromEffects(...))   <- xref: RollCritical
    GetCritDamage(attacker, defender, ability)
        = Max(0, GetStat(attacker, 10) + GetCritDamageBonusFromEffects(...))         <- xref: CalculateCriticalDamage

`RollCritical` = slot 10 d'`IDamagePrediction`, `CalculateCriticalDamage` = slot 11 : les DEUX sont
la face EXECUTION. Le seul canal crit qu'ecrit la prediction est
`MightCrit@+0xB1 = DamageCalculations$$CouldCrit(attacker)`, et `CouldCrit` lit les stats **NUES** :

    CouldCrit(attacker) : if (GetStat(attacker, 9) < 1) return false;
                          return GetStat(attacker, 10) > 0;

=> la face DECISION native ne voit ni le +crit-chance ni le +crit-degat d'AUCUN effet. Le port, qui
ne les passe pas non plus (`services/damage_prediction.attacker_could_crit`), est FIDELE.

## AXE PERCAGE -- CONFIRME, avec sa PORTEE et sa CAUSE

Le natif applique bien le percage d'effet en PREDICTION, mais pas par un argument separe : il le
verse dans les `DamageModifiers`. Chaine LUE :

    CalculateAttackerModifiersForPrediction(state, entities, activeEffects)
        invoque les slots 0x16 / 0x17 / **0x18 = 24 `PiercingBonusForAttack`**  -> DamageModifiers@+0x20
    CalculateDefenderModifiersForPrediction(...)
        invoque les slots 0x1a / 0x1b / **0x19 = 25 `PiercingMalusForDefense`** -> DamageModifiers@+0x20
    CalculateBaseDamageWithAllModifiers(base, att, def, profile, attMods, defMods, isCrit, isMelee)
        additionalPiercing = attMods.HasValue ? attMods.Value.<+0x20> : Fix64.Zero
        defenderPiercing   = defMods.HasValue ? defMods.Value.<+0x20> : Fix64.Zero
        -> GetBaseDamageWithFixedPiercedArmor(..., additionalPiercing, defenderPiercing, ...)
           dont le corps INLINE celui de `GetAttackPiercingDamageRatio` :
               if (damageProfile == null) return 0;                                  <- LA PORTE
               Min(100, Max(base > 0, GetStat(0x1a) + GetStat(isMelee ? 0x15 : 0x16)
                                      + (int)additionalPiercing + (int)defenderPiercing + base))

PORTEE, qui n'etait pas ecrite : la garde `damageProfile == null` ferme le canal sur TOUT le chemin
`SortUnitsByDamageUtilitySelector` (qui passe `damageProfile: null`). L'ecart ne mord donc que la ou
la prediction porte un PROFIL -- l'attaque normale du PLAYBOOK.

CAUSE cote port : le slot 24 a **DEUX** mirrors, et un seul est cable au foyer partage.
  * `BaseEffect.create_piercing_bonus_for_attack(damage_profile, is_melee, attacker_ctx)` -> rend un
    `EffectBonus`, agrege par `build_defender_modifiers_from_effects` (variante `OwnerIsTarget`) ;
  * `BaseEffect.create_effect_piercing_bonus_for_attack(ctx)` -> rend un ENTIER, agrege par
    `piercing_bonus_from_effects`, et pousse a la main dans `select_weapon_pierce(effect_bonus=...)`
    par les seuls call-sites COMBAT.
La boucle attaquant PARTAGEE (`_attacker_effect_bonuses`) n'appelle NI l'un NI l'autre : cote
DECISION, l'axe percage de l'attaquant n'a donc aucun chemin vers `DamageModifiers.extra_pierce`.

Ce probe FIGE ces deux verdicts par balayage AST du port. Il rougit (rc 1) si l'un des deux bascule.

ASCII only.
"""
from __future__ import annotations

import ast
import pathlib
import sys

PYDIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))
ENGINE = PYDIR / "engine"

#: Le ctx COMPLET que la face COMBAT monte pour le canal percage
#: (`runner/abilities/base.py::ability_pierce_effect_bonus`). C'est l'etalon : tout ce qui manque
#: cote DECISION est un gate d'effet qui se TAIT.
CLES_CTX_COMBAT = {"owner_id", "att_id", "ability_type", "target_traits", "owner_ctx",
                   "is_ranged", "is_overwatch", "unit_ctx_of"}


def _src(rel: str) -> str:
    return (ENGINE / rel).read_text(encoding="utf-8")


def _appelle_avec(mod_src: str, fonc: str, appelee: str) -> "tuple[bool, set]":
    """Dans la fonction `fonc` du source, l'appel a `appelee` existe-t-il, et avec quels mots-cles ?"""
    tree = ast.parse(mod_src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fonc:
            for c in ast.walk(node):
                if isinstance(c, ast.Call):
                    f = c.func
                    nom = getattr(f, "id", None) or getattr(f, "attr", None)
                    if nom == appelee:
                        return True, {k.arg for k in c.keywords if k.arg}
    return False, set()


def etage_crit() -> int:
    print("ETAGE 1 -- AXE CRIT : le port ne doit PAS ouvrir le canal cote DECISION")
    src = _src("services/damage_prediction.py")
    ok, _ = _appelle_avec(src, "attacker_could_crit", "could_crit")
    print("  attacker_could_crit -> could_crit(stats nues) : %s" % ok)
    mauvais = []
    for appel in ("crit_chance_bonus_from_effects", "crit_damage_bonus_from_effects"):
        if appel in src:
            mauvais.append("services/damage_prediction.py:%s" % appel)
    for rel in ("playbook/prediction/_shared.py", "playbook/prediction/normal_attack.py",
                "playbook/prediction/abilities.py", "runner/operations/attack_prediction.py",
                "runner/operations/damage_utility.py"):
        s = _src(rel)
        for appel in ("crit_chance_bonus_from_effects", "crit_damage_bonus_from_effects"):
            # une MENTION en commentaire ne compte pas -- on cherche un APPEL
            for node in ast.walk(ast.parse(s)):
                if isinstance(node, ast.Call):
                    nom = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                    if nom == appel:
                        mauvais.append("%s:%s" % (rel, appel))
    if not ok:
        print("  ROUGE : attacker_could_crit ne passe plus par `could_crit`")
        return 1
    if mauvais:
        print("  ROUGE : la face DECISION appelle un canal crit-from-effects que le natif")
        print("          n'y traverse PAS (PredictAttackRaw n'appelle ni GetCritChance ni")
        print("          GetCritDamage ni CalculateCriticalDamage) -> %s" % mauvais)
        return 1
    print("  OK : aucun canal crit-from-effects sur la face DECISION -- conforme au decompile")
    return 0


def etage_percage() -> int:
    print()
    print("ETAGE 2 -- AXE PERCAGE : le canal est-il toujours INERTE cote DECISION ?")
    shared = _src("playbook/prediction/_shared.py")
    trouve, kw = _appelle_avec(shared, "_weapon_pierce", "select_weapon_pierce")
    print("  _shared._weapon_pierce -> select_weapon_pierce trouve=%s kwargs=%s"
          % (trouve, sorted(kw)))
    if not trouve:
        print("  INDETERMINE : le site a bouge -- relire `_weapon_pierce`")
        return 1
    inerte = "effect_bonus" not in kw
    print("  canal `effect_bonus` cote DECISION : %s" % ("INERTE (ecart)" if inerte else "ARME"))

    # Le ctx que la face DECISION monte DEJA pour `piercing_bonus_from_effects` (#1052) : il est
    # APPAUVRI, et c'est ce qui rend le cablage non trivial -- passer la valeur ne suffit pas.
    manquantes = set()
    tree = ast.parse(shared)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            nom = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if nom == "piercing_bonus_from_effects" and len(node.args) >= 2:
                d = node.args[1]
                if isinstance(d, ast.Dict):
                    posees = {k.value for k in d.keys
                              if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                    manquantes = CLES_CTX_COMBAT - posees
    print("  ctx DECISION de `piercing_bonus_from_effects` -- cles ABSENTES vs le ctx COMBAT :")
    print("    %s" % (sorted(manquantes) if manquantes else "(aucune)"))

    # La boucle ATTAQUANT partagee appelle-t-elle l'un des deux mirrors du slot 24 ?
    eff = _src("entities/effects/__init__.py")
    a1, _ = _appelle_avec(eff, "_attacker_effect_bonuses", "create_piercing_bonus_for_attack")
    a2, _ = _appelle_avec(eff, "_attacker_effect_bonuses", "create_effect_piercing_bonus_for_attack")
    d1, _ = _appelle_avec(eff, "build_defender_modifiers_from_effects",
                          "create_piercing_bonus_for_attack")
    print("  boucle ATTAQUANT partagee -> slot 24 : create_piercing=%s create_effect_piercing=%s"
          % (a1, a2))
    print("  boucle DEFENSEUR         -> slot 24 : create_piercing=%s (variante OwnerIsTarget)" % d1)
    if not inerte and (a1 or a2):
        print("  ROUGE : les DEUX chemins sont armes -> DOUBLE COMPTAGE du percage d'effet")
        return 1
    if inerte and not (a1 or a2):
        print("  CONSTAT : l'ecart #910-r1 (axe PERCAGE) est TOUJOURS OUVERT, et son foyer est")
        print("            `playbook/prediction/_shared.py::_weapon_pierce` + l'enrichissement du")
        print("            ctx ci-dessus. Portee : seulement la ou `damageProfile != null`.")
        return 0
    print("  CONSTAT : le canal percage a ete cable cote DECISION -- relire la fiche #910-r1")
    return 0


def main() -> int:
    rc = etage_crit()
    rc |= etage_percage()
    print()
    print("rc=%d" % rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
