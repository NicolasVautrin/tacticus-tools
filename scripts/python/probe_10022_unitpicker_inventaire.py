"""#10022 -- CLIQUET de l'inventaire `UnitPicker` (100 % OFFLINE, aucune session Frida).

Ce que ce probe garde, et POURQUOI il existe alors que rien n'est encore porte : l'inventaire de
`docs/rl/case-10022-unitpicker-inventaire.md` repose sur quatre faits qui se PERIMENT EN SILENCE au
changement de build ou de gameconfig, et dont aucun ne leve d'erreur quand il casse.

  1. Le namespace `IdunBattleLogic.AI.Utilities.UnitPicker.*` et ses DIX utilites. Un renommage
     ferait lire l'inventaire comme un inventaire d'autre chose.
  2. Les DIX ordinaux `UtilityType` du mirror Python vs le build. Le mirror a DEJA ete renumerote
     une fois (`gqfc5mff6c` -> `rnca9r7q6c`, insertion d'`AttackTile` en 8 : +1 sur 59 membres) --
     un decalage ici ferait nommer chaque bucket avec le libelle de son voisin.
  3. Le SUBSTRAT : `clientGameConfig.aiUtilities.Default.UnitOrder` est la SEULE entree de config
     des dix utilites, et `IdunBattle.AI.Utilities.BaseUtility$$GetUtilityValue` rend **0 en
     silence** (avec un simple warning journalise) sur une clef absente. Une clef renommee cote
     jeu rendrait donc `UnitOrderUtility$$Priority` muet sans qu'aucun test ne rougisse. C'est
     l'etage qui MORD.
  4. L'ordinal ECRIT AU SITE : `LastAbilitiesUtility$$.cctor` code en dur `0x496` = 1174 =
     `TriggeredAbilityType.RealityUnbound`, et `PreferSummonsAndObjectsUtility` code en dur les
     traits `2` / `13` = `Summon` / `Object`. Regenerer un mirror apres un renumerotage rendrait
     `probe_313` VERT alors que l'ordinal du site aurait change de sens.

Il ne prouve RIEN sur le comportement -- c'est un cliquet de FRAICHEUR, pas une validation de port.

    python scripts/python/probe_10022_unitpicker_inventaire.py

rc 0 = tout concorde ; rc 1 = au moins une divergence ; rc 2 = PAS MESURE (entrees manquantes --
jamais rabattu sur un vert, cf. la regle tri-etat du depot).
"""
from __future__ import annotations

import io
import json
import os
import sys

_ICI = os.path.dirname(os.path.abspath(__file__))
if _ICI not in sys.path:
    sys.path.insert(0, _ICI)

_RACINE = os.path.dirname(os.path.dirname(_ICI))
_SYMBOLES = os.path.join(_RACINE, "data", "symbols")


# --------------------------------------------------------------------------------------------- #
#  Ce que le decompile porte -- recopie du site, pas deduit du nom
# --------------------------------------------------------------------------------------------- #

# Les DIX classes du namespace, cf. case-10022 section 5.
UTILITES = (
    "LastAbilitiesUtility",
    "MinPossibleNormalAttackTargetUtility",
    "PreferAbilitiesUtility",
    "PreferFreshlySpawnedUtility",
    "PreferNonBossUtility",
    "PreferSummonsAndObjectsUtility",
    "RandomUtility",
    "RemainingUtility",
    "ShortestPathToEnemyUtility",
    "UnitOrderUtility",
)
_NS = "IdunBattleLogic.AI.Utilities.UnitPicker."

# Les HUIT buckets de `IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$.ctor`, DANS L'ORDRE,
# avec le litteral `UtilityType` LU au decompile. Le nom Python est celui du mirror
# `engine/utilities/utility_type.py` ; l'ordinal est celui ECRIT dans le ctor natif.
BUCKETS = (
    ("PreferSummons", 0x4B),
    ("PreferNonBoss", 0x45),
    ("PreferFreshlySpawned", 0x46),
    ("UnitOrder", 0x4D),
    ("LastAbilities", 0x4C),
    ("PreferAbilities", 0x4A),
    ("UnitWithShortestPathToEnemy", 0x48),
    ("Remaining", 0x49),
)
# Enregistrees dans `UtilitiesDatabase` mais demandees par AUCUN bucket (section 4) -- DEAD CODE.
HORS_BUCKET = (("MinPossibleNormalAttackTarget", 0x47), ("Random", 0x4E))

# Ordinaux ECRITS EN DUR dans un `.cctor` natif (section 4 du cas).
LAST_ABILITIES_CIBLE = ("RealityUnbound", 1174)          # LastAbilitiesUtility$$.cctor : arr[0] = 0x496
SUMMONS_ET_OBJETS = (("Summon", 2), ("Object", 13))      # PreferSummonsAndObjectsUtility : HasTrait(2)/(0xd)


def _build_courant() -> "str | None":
    chemin = os.path.join(_SYMBOLES, "CURRENT")
    if not os.path.isfile(chemin):
        return None
    val = io.open(chemin, encoding="utf-8").read().strip()
    return val or None


def _enums_du_build(build: str) -> "dict[str, dict[str, int]]":
    """`frida/enums.tsv` : `<nom plein>\\t<k=v,k=v,...>`. Rend {nom plein: {membre: ordinal}}."""
    chemin = os.path.join(_SYMBOLES, build, "frida", "enums.tsv")
    out: "dict[str, dict[str, int]]" = {}
    if not os.path.isfile(chemin):
        return out
    for ligne in io.open(chemin, encoding="utf-8", errors="replace"):
        champs = ligne.rstrip("\n").split("\t")
        if len(champs) < 2:
            continue
        membres: "dict[str, int]" = {}
        for paire in champs[1].split(","):
            if "=" not in paire:
                continue
            cle, _, val = paire.partition("=")
            try:
                membres[val] = int(cle)
            except ValueError:
                continue
        if membres:
            out[champs[0]] = membres
    return out


def _fonctions_du_build(build: str) -> "set[str]":
    chemin = os.path.join(_SYMBOLES, build, "ghidra", "functions.tsv")
    noms: "set[str]" = set()
    if not os.path.isfile(chemin):
        return noms
    for ligne in io.open(chemin, encoding="utf-8", errors="replace"):
        champs = ligne.rstrip("\n").split("\t")
        if len(champs) >= 2:
            noms.add(champs[1])
    return noms


def _gameconfig(build: str):
    chemin = os.path.join(_SYMBOLES, build, "gameconfig.json")
    if not os.path.isfile(chemin):
        return None
    return json.load(io.open(chemin, encoding="utf-8"))


def _mirror_utility_type():
    from engine.utilities.utility_type import UtilityType
    return UtilityType


def main() -> int:
    build = _build_courant()
    if build is None:
        print("[10022] NON MESURE : data/symbols/CURRENT absent -- rc 2 (jamais un vert)")
        return 2
    print("[10022] build = %s" % build)

    fonctions = _fonctions_du_build(build)
    enums = _enums_du_build(build)
    cfg = _gameconfig(build)
    if not fonctions or not enums or cfg is None:
        print("[10022] NON MESURE : tables du build incompletes "
              "(functions=%d, enums=%d, gameconfig=%s) -- rc 2"
              % (len(fonctions), len(enums), "oui" if cfg else "non"))
        return 2

    rouges: "list[str]" = []

    # --- etage 1 : les DIX utilites, et leur CORPS d'iterateur ------------------------------- #
    # Le corps reel d'`EvaluateUnitInSteps` est dans le `MoveNext` de la classe generee : sa
    # presence est ce qui rend l'inventaire lisible. On accepte `d__0` comme `d__1` (le suffixe
    # depend du nombre de lambdas de la classe, il n'est pas stable par construction).
    manquantes, sans_corps = [], []
    for nom in UTILITES:
        if (_NS + nom + "$$EvaluateUnitInSteps") not in fonctions:
            manquantes.append(nom)
            continue
        prefixe = _NS + nom + ".u003CEvaluateUnitInStepsu003Ed__"
        if not any(f.startswith(prefixe) and f.endswith("$$MoveNext") for f in fonctions):
            sans_corps.append(nom)
    print("[10022] etage 1 -- namespace UnitPicker : %d/%d utilites, %d sans corps d'iterateur"
          % (len(UTILITES) - len(manquantes), len(UTILITES), len(sans_corps)))
    if manquantes:
        rouges.append("etage 1 : utilites ABSENTES du build -> %s" % ", ".join(manquantes))
    if sans_corps:
        rouges.append("etage 1 : pas de <EvaluateUnitInSteps>d__N.MoveNext -> %s"
                      % ", ".join(sans_corps))
    # Temoin de non-vacuite : un etage qui ne visite rien ne peut pas rendre zero.
    assert len(UTILITES) == 10, "le recensement lui-meme a ete ampute"

    # --- etage 2 : les ordinaux des buckets, mirror <-> build --------------------------------- #
    UtilityType = _mirror_utility_type()
    natif = enums.get("IdunBattle.Configuration.UtilityType") or {}
    if not natif:
        rouges.append("etage 2 : IdunBattle.Configuration.UtilityType absent de enums.tsv")
    ecarts = []
    for nom, ordinal in BUCKETS + HORS_BUCKET:
        m = UtilityType.__members__.get(nom)
        if m is None:
            ecarts.append("%s: absent du mirror" % nom)
            continue
        if int(m) != ordinal:
            ecarts.append("%s: mirror=%d SITE=%d" % (nom, int(m), ordinal))
        n = natif.get(nom)
        if n is None:
            ecarts.append("%s: absent du build" % nom)
        elif n != ordinal:
            ecarts.append("%s: build=%d SITE=%d" % (nom, n, ordinal))
    print("[10022] etage 2 -- ordinaux UtilityType (8 buckets + 2 hors-bucket) : %d ecart(s)"
          % len(ecarts))
    for e in ecarts:
        print("           %s" % e)
    if ecarts:
        rouges.append("etage 2 : %d ordinal(aux) divergent(s)" % len(ecarts))

    # --- etage 3 : le SUBSTRAT est bien reduit a `UnitOrder` ---------------------------------- #
    ai = ((cfg.get("clientGameConfig") or {}).get("aiUtilities") or {})
    defaut = ai.get("Default") or {}
    if not defaut:
        rouges.append("etage 3 : aiUtilities.Default vide ou absent")
    presentes = [nom for nom, _ in BUCKETS + HORS_BUCKET if nom in defaut]
    print("[10022] etage 3 -- substrat : collections=%s, Default=%d entrees, "
          "utilites du picker configurees=%s"
          % (sorted(ai.keys()), len(defaut), presentes))
    if presentes != ["UnitOrder"]:
        rouges.append("etage 3 : le substrat du picker a change -- attendu ['UnitOrder'], lu %s"
                      % presentes)

    # --- etage 4 : les clefs d'`UnitOrder` se RESOLVENT (le cran qui mord) -------------------- #
    # `GetUtilityValue` rend 0 en silence sur une clef absente ; symetriquement, une clef du
    # gameconfig qui ne nomme plus rien cote enums est un poids que le natif n'appliquera JAMAIS.
    # Les trois voies sont celles de `UnitOrderUtility$$Priority` : ActiveAbilityType (a),
    # TriggeredAbilityType (b), UnitTrait (c) -- plus l'unitId sans rarete, qui n'a aucune clef ici.
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.entities.traits.unit_trait import UnitTrait
    try:
        from engine.entities.triggered_ability_type import TriggeredAbilityType
    except ImportError:
        TriggeredAbilityType = None

    unit_order = defaut.get("UnitOrder") or {}
    assert unit_order, "etage 4 : temoin VIDE -- un etage sans clef ne peut pas rendre zero"
    non_resolues, voies = [], {"active": 0, "triggered": 0, "trait": 0}
    for clef in unit_order:
        vu = False
        if clef in ActiveAbilityType.__members__:
            voies["active"] += 1
            vu = True
        if TriggeredAbilityType is not None and clef in TriggeredAbilityType.__members__:
            voies["triggered"] += 1
            vu = True
        if clef in UnitTrait.__members__:
            voies["trait"] += 1
            vu = True
        if not vu:
            non_resolues.append(clef)
    print("[10022] etage 4 -- UnitOrder : %d clefs, voies actif=%d declenche=%d trait=%d, "
          "NON RESOLUES=%d"
          % (len(unit_order), voies["active"], voies["triggered"], voies["trait"],
             len(non_resolues)))
    if non_resolues:
        print("           %s" % ", ".join(sorted(non_resolues)))
        rouges.append("etage 4 : %d clef(s) d'UnitOrder ne nomment plus rien -> poids MUET"
                      % len(non_resolues))

    # --- etage 5 : les ordinaux ECRITS EN DUR dans les `.cctor` ------------------------------- #
    nom_ta, ord_ta = LAST_ABILITIES_CIBLE
    natif_trig = enums.get("IdunBattle.Entities.Enum.TriggeredAbilityType") or {}
    if not natif_trig:
        for cle in enums:
            if cle.endswith("TriggeredAbilityType"):
                natif_trig = enums[cle]
                break
    if natif_trig.get(nom_ta) != ord_ta:
        rouges.append("etage 5 : LastAbilitiesUtility cible 0x496=%d, que le build nomme %r "
                      "(attendu %s)" % (ord_ta,
                                        [k for k, v in natif_trig.items() if v == ord_ta] or None,
                                        nom_ta))
    natif_trait = enums.get("IdunBattle.Entities.Enum.UnitTrait") or {}
    ecarts_traits = [(n, o) for n, o in SUMMONS_ET_OBJETS if natif_trait.get(n) != o]
    if ecarts_traits:
        rouges.append("etage 5 : traits en dur de PreferSummonsAndObjectsUtility divergents -> %s"
                      % ecarts_traits)
    print("[10022] etage 5 -- ordinaux en dur : LastAbilities->%s(%d), traits %s : %s"
          % (nom_ta, ord_ta, [n for n, _ in SUMMONS_ET_OBJETS],
             "OK" if natif_trig.get(nom_ta) == ord_ta and not ecarts_traits else "DIVERGENT"))

    print("")
    if rouges:
        print("[10022] ROUGE -- %d divergence(s) :" % len(rouges))
        for r in rouges:
            print("   - %s" % r)
        return 1
    print("[10022] VERT -- l'inventaire de docs/rl/case-10022-unitpicker-inventaire.md concorde "
          "avec le build %s" % build)
    print("[10022] PORTEE : cliquet de FRAICHEUR. Il ne dit RIEN du comportement du picker, et "
          "rien n'est encore porte (aucun consommateur Python).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
