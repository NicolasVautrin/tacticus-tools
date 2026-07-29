"""#167 -- CLIQUET de non-regression du registre d'abilities (offline pur, aucune session).

CE QUE CE FICHIER GARDE
-----------------------
Entrer dans `ABILITY_CLASSES` engage DEUX donnees, et leur absence se degrade de la MEME facon :
en silence, dans le sens PERMISSIF.

  * `TARGETING_OPTIONS` -- `engine/runner/abilities/targeting.py`, `get_invalid_target_reason` /
    `get_invalid_caster_reason` commencent par `options = getattr(ability, "TARGETING_OPTIONS", None)`
    et rendent **0 immediatement** si c'est `None`. Aucun gate. Le moteur accepte alors des casts que
    `IdunBattle.Operations.ActiveAbilityOperation$$IsInvalidTarget` REFUSE (ami/ennemi, cible ==
    caster, caster ayant deja bouge). Ni erreur ni crash -- donc invisible en self-play, et c'est
    exactement l'espace d'action qu'un entrainement irait exploiter.
  * `ABILITY_ATTACK_TYPE` -- `engine/runner/abilities/attack_type.py`, `ability_has_attack_type`
    rend `False` sur une cle absente : l'ability se degrade en `Others` et le gate
    `AbilityHasAttackType(0|1)` de SwornProtector reste MUET pour elle.

POURQUOI UN CLIQUET, ET PAS UN SIMPLE ASSERT DE COUVERTURE
----------------------------------------------------------
C'est le SEUL gisement que notre propre cadence de portage AGGRAVE : chaque nouveau port l'alimente.
Le compte de masques manquants est passe de 60 a 75 pendant la campagne, sans qu'aucun test ne
rougisse. Et l'absence de `ABILITY_ATTACK_TYPE` a ete creusee TROIS fois (1036 FrenziedFiring en
`d2be96e`, puis 1041 BrazierOfHolyFire et 1116 RadBombardment en `825f69f`) -- les deux dernieres
n'ont ete vues qu'au RE-JEU apres rebase d'un autre agent : le trou ne s'etait montre dans aucune
des deux PR qui l'avaient creuse.

Un assert de couverture pleine serait ROUGE des le premier jour sur `TARGETING_OPTIONS` (28/81 a la
creation de ce fichier, 51/91 au 2026-07-28) et donc desarme dans la semaine. La forme qui tient est
le CLIQUET : une liste d'exemption figee, qui ne peut que RETRECIR.

  * une ability du registre SANS masque et ABSENTE de la liste -> ECHEC (regression neuve) ;
  * une ability de la liste qui a MAINTENANT son masque -> ECHEC, il faut la retirer de la liste
    (c'est ce sens-la qui fait le cliquet : sans lui, la liste se fossilise et ne redescend jamais) ;
  * une ability de la liste ABSENTE du registre -> ECHEC (entree perimee).

`ABILITY_ATTACK_TYPE`, lui, est deja PLEIN (81/81 a la creation, 91/91 au 2026-07-28) : sa garde est
donc SANS exemption. Elle existait, mais
enterree a l'etape 0 de `probe_120_pre_unit_ability_fork.py` -- un probe qui monte un etat de
bataille complet et casse pour dix raisons sans rapport, auquel cas la couverture n'est jamais
vue. Ici elle tient seule, en un import.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import ast
from pathlib import Path

from engine.runner.abilities import ABILITY_CLASSES
from engine.runner.abilities.attack_type import ABILITY_ATTACK_TYPE
from engine.runner.abilities.targeting_rule import TargetingRule

# --- LISTE D'EXEMPTION -- NE PEUT QUE RETRECIR ----------------------------------------------------
# Etat au 2026-07-29 (#247) : 94 abilities au registre, 64 avec masque, ces 30 sans.
# (Historique du cliquet : 81/28/53 au 2026-07-27 `6110d37` -> 13 resorbees par #181, lot
#  ultramarines / sisterhood / tyranids / spacewolves / admec / bloodangels ; puis 1014
#  ArmoriumCherub par #222, 1018 ValkyrieStrike par #245, 1043 ThunderousAssault par #246, et les
#  SIX du module `splash` par #247 -- 1000/1051/1065/1078/1098/1105, qui relevent a elles seules de
#  TROIS formes de ctor differentes et de TROIS presets differents.)
# Ne JAMAIS y ajouter une ligne pour faire passer un port neuf : le masque se lit au decompile, dans
# le litteral passe par `<X>Ability$$.ctor` a `IdunBattle.Core.Services.TargetingOptions$$.ctor`.
#
# DEUX PIEGES quand on en retire une (les deux ont deja produit un masque FAUX) :
#   * l'overload PRESET + flags (`TargetingOptions..ctor(&opts, &preset, <flags>, 0)`) -- le litteral
#     visible n'est PAS le masque effectif ;
#   * l'ability qui n'appelle AUCUN ctor et recopie les 0x40 octets d'un champ STATIQUE : le masque
#     effectif est la constante ecrite par `TargetingOptions$$.cctor` a `<preset>+0x28`. Les presets
#     ne sont pas interchangeables (`statics+0x168` = 0x4002, `statics+0x68` = 0x4000) : lire ability
#     par ability, jamais generaliser « toutes les offensives valent X ».
# Recopier un litteral sans verifier l'overload produit un masque FAUX -- PIRE que l'absence, qui au
# moins ne ment pas. Laisser l'entree dans cette liste est le bon choix tant que le doute existe.
SANS_TARGETING_OPTIONS: dict[int, str] = {
    # 1000 GauntletsOfUltramarAbility RESORBEE (#247) -- une QUATRIEME forme : **FACTORY NOMMEE**.
    # `...GauntletsOfUltramarAbility$$.ctor` n'ecrit aucun champ et ne copie aucun preset : il appelle
    # `IdunBattle.Core.Services.TargetingOptions$$SelfCastIfEnemyInCustomRangeOptions(&opts, 2)`, qui
    # ecrit `isSelfCasting = 1`, `range = CustomRange(2)`, `forceMeleeTarget = RangedBool.False` et
    # `rules = 0x4000` (TargetIsEnemy seul). C'est le SEUL appelant natif de cette factory ; les 3
    # autres porteurs du profil (1009/1207/1226) l'ont recue INLINEE.
    1007: "ScarabHiveAbility",
    # 1014 ArmoriumCherubAbility RESORBEE (#222) -- forme « PRESET STATIQUE COPIE » :
    # `...ArmoriumCherubAbility$$.ctor` recopie `TargetingOptions statics+0x140` et le masque
    # effectif est `*(statics+0x168)` = 0x4002, lu dans `TargetingOptions$$.cctor`.
    1016: "SendInTheNextWaveAbility",
    # 1018 ValkyrieStrikeAbility RESORBEE (#245) -- MEME forme « PRESET STATIQUE COPIE » que 1014,
    # mais un AUTRE preset : `...ValkyrieStrikeAbility$$.ctor` recopie `TargetingOptions statics+0x1c0`
    # et le masque effectif est `*(statics+0x1e8)` = 0x6000040 (TargetIsTile | AllowObscuredTarget
    # ByElevation | AllowObscuredTargetByWalls), lu dans `TargetingOptions$$.cctor`. Preuve vivante que
    # les presets ne sont pas interchangeables : 0x140 -> 0x4002, 0x1c0 -> 0x6000040.
    1021: "IncursionAbility",
    1022: "BringerOfDespairAbility",
    1028: "SupremeCommanderAbility",
    1036: "FrenziedFiringAbilityCombat",   # preset statique NON lu (cf. attack_type.py, lot #61)
    1037: "RevitalizingMalignancyAbility",
    1040: "SpawnPoxwalkersAbility",
    1042: "FlailSwingAbility",
    # 1043 ThunderousAssaultAbility RESORBEE (#246) -- forme « PRESET + FLAGS », la 2e des trois :
    # `...ThunderousAssaultAbility$$.ctor` recopie `TargetingOptions statics+0x40` PUIS appelle
    # `TargetingOptions..ctor(&opts, &preset, 0x10000000, 0)`. Cette surcharge COMBINE
    # (`dst+0x28 = flags | preset+0x28`) -> masque effectif `0x10000000 | *(statics+0x68)` =
    # `0x10000000 | 0x4000` = 0x10004000 (CasterCanMove | TargetIsEnemy). Le litteral visible
    # (0x10000000) n'est donc PAS le masque, et le preset n'est pas non plus le masque : c'est le
    # OU des deux. Portee = `TargetingRange statics+0x30` = RANGE_ADJACENT.
    1045: "GetEmRuntzAbility",
    1047: "ScarabSummonAbility",
    # 1051 StikkbombAbility RESORBEE (#247) -- forme « PRESET + FLAGS » : preset `statics+0x140`
    # + flags `0x2000000` -> masque effectif `0x2000000 | *(statics+0x168)` = `0x2000000 | 0x4002`
    # = 0x2004002 (AllowObscuredTargetByElevation | TargetIsEnemy | TargetMatchesDynamicRule).
    # Portee = `TargetingRange statics+0x18` = RANGE_FROM_CONFIG (`constants.range` = 2) ;
    # `forceMeleeTarget = 0 = RangedBool.True` (clamp de melee ARME).
    # 1065 ScythingTalonsAbility RESORBEE (#247) -- forme « PRESET STATIQUE COPIE », preset
    # `statics+0x40` : masque = `*(statics+0x68)` = 0x4000 (TargetIsEnemy seul), portee =
    # `TargetingRange statics+0x30` = RANGE_ADJACENT, `forceMeleeTarget = RangedBool.False`.
    1076: "MV71SniperDroneSquadAttackAbility",
    1077: "EarlyWarningOverrideAbility",
    # 1078 FragstormAbility RESORBEE (#247) -- forme « PRESET + FLAGS », mais preset `statics+0x180`
    # et NON `+0x140` comme ses deux voisines de module (1051/1098). Meme `rules` effectif
    # (0x2004002) et une portee qui DIFFERE : `*(statics+0x1a0)` = 1 = `RangedBool.False` ->
    # `forceMeleeTarget` DESARME, donc pas de clamp a 1 au contact. Illustration directe du piege
    # « la voisine ment » : le masque se serait recopie juste, le volet portee faux.
    1081: "FightingRetreatAbility",
    1082: "InspiredToGreatnessAbility",
    1096: "MasterOfTheTutelariesAbility",
    # 1098 PlasmaGrenadeAbility RESORBEE (#247) -- forme « PRESET + FLAGS », preset `statics+0x140`
    # + flags `0x2000000` -> 0x2004002 ; portee RANGE_FROM_CONFIG (2) ; `forceMeleeTarget =
    # RangedBool.True`. STRICTEMENT le meme couple que 1051, verifie ctor par ctor.
    1104: "SpiritLeechAbility",
    # 1105 CrushingClawsAbility RESORBEE (#247) -- forme « PRESET STATIQUE COPIE », preset
    # `statics+0x40` (le meme que 1065) : masque 0x4000, portee RANGE_ADJACENT, `forceMeleeTarget =
    # RangedBool.False`.
    1113: "StormcallerAbility",
    1118: "DoctrinaImperativesAbility",
    1122: "CordClawAbility",
    1142: "MalleusRocketLauncherAbility",
    1143: "ForwardSpotterAbility",
    1147: "HadesAutocannonsAbility",
    1148: "DaemonicOrdnanceAbility",
    1151: "TheQuickeningAbility",          # overload PRESET + flags (cf. le piege ci-dessus)
    1160: "HeavyRailRifleAbility",
    1161: "TwinSmartMissileSystemAbility",
    1166: "AberrantHypermorphAbility",
    1168: "EntropyCannonsAbility",
    1169: "PlagueburstMortarAbility",
}


def _nom(aid: int) -> str:
    cls = ABILITY_CLASSES.get(aid)
    return cls.__name__ if cls is not None else "<hors registre>"


def test_attack_type_couvre_tout_le_registre():
    """`ABILITY_ATTACK_TYPE` couvre TOUT le registre : sa garde n'a PAS d'exemption, et ne doit
    jamais en avoir.

    Le litteral est le 3e argument de `AActiveAbility$$.ctor` -- une ligne a relire au decompile,
    pas un chantier. Rien ne justifie d'entrer au registre sans lui."""
    manquants = sorted(a for a in ABILITY_CLASSES if a not in ABILITY_ATTACK_TYPE)
    assert not manquants, (
        "abilities entrees au registre SANS leur litteral `AbilityAttackType` -> elles se degradent "
        "en Others et le gate SwornProtector reste muet pour elles. Relire le 3e argument de "
        "`<X>Ability$$.ctor` -> `AActiveAbility..ctor(this, &opts, <ICI>)` : %s"
        % [(a, _nom(a)) for a in manquants])


def test_targeting_options_ne_regresse_pas():
    """Une ability qui entre au registre pose son masque DANS LE MEME COMMIT.

    Sans masque, la cascade rend 0 sans rien gater -- le cast illegal passe, en silence."""
    nouveaux = sorted(a for a, cls in ABILITY_CLASSES.items()
                      if getattr(cls, "TARGETING_OPTIONS", None) is None
                      and a not in SANS_TARGETING_OPTIONS)
    assert not nouveaux, (
        "abilities entrees au registre SANS `TARGETING_OPTIONS` -> aucun gate de ciblage, le moteur "
        "accepte des casts que le natif REFUSE. Lire le masque dans "
        "`<X>Ability$$.ctor` -> `TargetingOptions$$.ctor` (attention a l'overload PRESET, cf. l'en-tete "
        "de ce fichier) : %s" % [(a, _nom(a)) for a in nouveaux])


def test_liste_d_exemption_ne_peut_que_retrecir():
    """LE cliquet. Sans ce sens-la, la liste se fossilise : on n'ajoute plus de dette, mais on ne
    rembourse jamais celle qui reste, et les entrees survivent a la campagne. Il a mordu pour de vrai
    le 2026-07-28 (#181) : les 13 masques du lot ont fait ECHOUER ce test tant qu'ils n'avaient pas
    ete retires de la liste."""
    resorbees = sorted(a for a in SANS_TARGETING_OPTIONS
                       if a in ABILITY_CLASSES
                       and getattr(ABILITY_CLASSES[a], "TARGETING_OPTIONS", None) is not None)
    assert not resorbees, (
        "ces abilities ont MAINTENANT leur masque : les retirer de SANS_TARGETING_OPTIONS (la liste "
        "ne peut que retrecir) -> %s" % [(a, _nom(a)) for a in resorbees])

    perimees = sorted(a for a in SANS_TARGETING_OPTIONS if a not in ABILITY_CLASSES)
    assert not perimees, (
        "entrees perimees dans SANS_TARGETING_OPTIONS -- ces abilities ne sont plus au registre : %s"
        % [(a, SANS_TARGETING_OPTIONS[a]) for a in perimees])


def test_targeting_range_accompagne_toujours_le_masque():
    """#241 -- pendant EXACT de la regle ci-dessus, sur l'axe PORTEE.

    `rules` et `range` sortent du MEME appel de ctor -- `TargetingOptions..ctor(isSelfCasting,
    range, forceMeleeTarget, rules, ...)`, ou de la MEME copie de preset statique. N'en poser qu'un
    n'est pas un choix, c'est un oubli : `TargetingOptions.range is None` = « `TargetingRange` non
    RE-lu » -> `get_range` rend None -> AUCUN gate de portee. Meme degradation permissive, meme
    invisibilite en self-play.

    Pas d'exemption ici, et il n'en faut pas : TOUS les masques poses portent leur `TargetingRange`,
    et il se lit dans la MEME ligne de decompile que le masque."""
    manquants = sorted(a for a, cls in ABILITY_CLASSES.items()
                       if getattr(cls, "TARGETING_OPTIONS", None) is not None
                       and cls.TARGETING_OPTIONS.range is None)
    assert not manquants, (
        "abilities avec `TARGETING_OPTIONS` mais SANS `TargetingRange` -> le volet portee du filtre "
        "n'est pas arme, le moteur accepte des casts hors portee que le natif REFUSE. Lire le 2e "
        "argument de `<X>Ability$$.ctor` -> `TargetingOptions$$.ctor` (ou le `<preset>+0x08..0x1f` "
        "du preset statique recopie) : %s" % [(a, _nom(a)) for a in manquants])


def test_masques_poses_ne_portent_aucun_bit_inconnu():
    """Tout bit d'un masque pose doit se nommer dans `TargetingRule` (le mirror GENERE de
    `IdunBattle.Core.Services.TargetingRule` depuis `data/symbols/<build>/frida/enums.tsv`).

    Un bit hors enum = une transcription fautive du decompile, ou un enum qui a bouge au dernier
    build. Les deux se lisent ici, et nulle part ailleurs : la cascade, elle, ignore silencieusement
    ce qu'elle ne sait pas lire."""
    connus = 0
    for membre in TargetingRule:
        v = int(membre)
        if v > 0:
            connus |= v

    fautifs = []
    for aid, cls in sorted(ABILITY_CLASSES.items()):
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        if opts is None:
            continue
        reste = int(opts.rules) & ~connus
        if reste:
            fautifs.append((aid, cls.__name__, hex(reste)))
    assert not fautifs, (
        "masques portant un bit ABSENT de l'enum TargetingRule (transcription fautive, ou enum "
        "deplace au dernier build -- rejouer probe_targeting_rule_bits.py) : %s" % fautifs)


# --- SOURCE UNIQUE des regles de ciblage (#164) ---------------------------------------------------
# Le port a longtemps lu ses regles depuis DEUX endroits : le module GENERE `targeting_rule.py`
# (mirror 1:1 du dump) et ~31 constantes `RULE_*` ECRITES A LA MAIN dans `targeting.py`. Deux
# sources pour la meme information, c'est une divergence SILENCIEUSE en attente : rien n'obligeait
# la copie manuelle a suivre le dump, et trois de ses constantes portaient un nom INVENTE
# (`RULE_BIT39_...`, `RULE_BIT41_...`, `RULE_BIT57_...`) faute d'avoir le nom natif sous la main.
# Les deux tests qui suivent interdisent la re-apparition d'une seconde source.
PY_ROOT = Path(__file__).resolve().parents[3]           # scripts/python
MODULE_GENERE = PY_ROOT / "engine" / "runner" / "abilities" / "targeting_rule.py"


def _nom_normalise(ident: str) -> str:
    """`RULE_TARGET_IS_IN_RANGE` -> `TARGETISINRANGE`, pour confronter un identifiant Python
    UPPER_SNAKE au nom PascalCase d'un membre de l'enum."""
    for prefixe in ("TARGETING_RULE_", "RULE_"):
        if ident.startswith(prefixe):
            ident = ident[len(prefixe):]
            break
    return ident.replace("_", "")


def _sources_python() -> list:
    return [p for p in PY_ROOT.rglob("*.py") if p != MODULE_GENERE]


def test_aucune_constante_de_ciblage_declaree_hors_du_module_genere():
    """UNE seule source de noms de bits : `engine/runner/abilities/targeting_rule.py`, GENERE par
    `scripts/python/gen_targeting_rule.py` depuis `data/symbols/<build>/frida/enums.tsv`.

    Rougit sur toute RE-DECLARATION d'une constante de ciblage ailleurs, sous deux formes :

      * un identifiant prefixe `RULE_` / `TARGETING_RULE_` affecte a un entier -- la forme exacte
        des 31 constantes supprimees, et de la copie locale qui vivait dans
        `probe_range_gate_melee_clamp.py` ;
      * un identifiant NON prefixe dont le nom ET la valeur retombent sur un membre de l'enum
        (ex. `TARGET_IS_ENEMY = 0x4000`) -- le contournement evident de la regle ci-dessus.

    Le mode de defaillance garde ici n'est pas l'erreur : c'est la copie qui reste JUSTE aujourd'hui
    et devient FAUSSE au prochain re-dump, sans que rien ne le dise."""
    par_nom = {m.name.upper(): int(m) for m in TargetingRule}
    par_nom["ALLOWOBSCUREDTARGET"] = int(TargetingRule.AllowObscuredTarget)   # composite, non itere

    fautifs = []
    for chemin in _sources_python():
        try:
            arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, (ast.Assign, ast.AnnAssign)):
                continue
            valeur = noeud.value
            if not (isinstance(valeur, ast.Constant) and isinstance(valeur.value, int)
                    and not isinstance(valeur.value, bool)):
                continue
            cibles = noeud.targets if isinstance(noeud, ast.Assign) else [noeud.target]
            for cible in cibles:
                if not isinstance(cible, ast.Name):
                    continue
                ident = cible.id
                prefixe = ident.startswith("RULE_") or ident.startswith("TARGETING_RULE_")
                homonyme = par_nom.get(_nom_normalise(ident)) == valeur.value
                if prefixe or homonyme:
                    fautifs.append("%s:%d  %s = %#x"
                                   % (chemin.relative_to(PY_ROOT).as_posix(),
                                      cible.lineno, ident, valeur.value))
    assert not fautifs, (
        "constantes de ciblage declarees HORS du module genere -- il y a de nouveau DEUX sources "
        "pour la meme information, et rien n'oblige la copie a suivre le dump. Importer "
        "`from engine.runner.abilities.targeting_rule import TargetingRule as TR` et citer "
        "`TR.<NomNatif>` : %s" % fautifs)


def test_aucun_bit_de_ciblage_cite_par_sa_valeur_brute():
    """Pendant du test precedent, sur l'autre facon de contourner la source unique : ne pas
    declarer de constante du tout et ecrire le litteral au point d'usage (`options.has(0x4000)`).

    Le symptome que ca produit se lit dans nos propres traces : la tache #166 decrivait le refus
    d'une cible deja adjacente comme « le bit `0x100000000` », faute de pouvoir le nommer. Le
    module genere le nomme : `TargetIsNotAdjacent`."""
    fautifs = []
    for chemin in _sources_python():
        try:
            arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for noeud in ast.walk(arbre):
            if not (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)
                    and noeud.func.attr == "has"):
                continue
            receveur = noeud.func.value
            if not (isinstance(receveur, ast.Name) and receveur.id in ("options", "opts")):
                continue
            for arg in noeud.args:
                if (isinstance(arg, ast.Constant) and isinstance(arg.value, int)
                        and not isinstance(arg.value, bool)):
                    fautifs.append("%s:%d  options.has(%#x)"
                                   % (chemin.relative_to(PY_ROOT).as_posix(),
                                      noeud.lineno, arg.value))
    assert not fautifs, (
        "bits de ciblage cites par leur VALEUR BRUTE au point d'usage -- un lecteur ne peut pas "
        "verifier un masque qu'il doit decoder de tete. Citer `TR.<NomNatif>` : %s" % fautifs)


def test_module_genere_concorde_avec_le_dump_du_build_courant():
    """L'autre moitie de la source unique : la source EST unique, encore faut-il qu'elle soit a
    jour. Le module est GENERE, donc il peut dater d'un build anterieur sans que rien ne le dise --
    et tous les masques `TARGETING_OPTIONS` du registre deviennent faux d'un coup, en silence.

    Meme confrontation que `scripts/python/probe_targeting_rule_bits.py` (dont ce test reutilise les
    lecteurs), mais DANS la suite : un probe qu'on oublie de lancer ne garde rien."""
    import probe_targeting_rule_bits as P

    build = P.build_hash()
    dump, genere = P.from_dump(build), P.from_python()
    ecarts = [(bit, dump.get(bit), genere.get(bit))
              for bit in sorted(set(dump) | set(genere))
              if dump.get(bit) != genere.get(bit)]
    assert not ecarts, (
        "le module GENERE `targeting_rule.py` a derive du dump du build %s -- regenerer "
        "(`python scripts/python/gen_targeting_rule.py`) et RELIRE les masques du registre, "
        "qui sont tous suspects : %s" % (build, ecarts))
