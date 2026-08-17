"""#10015 -- `fire_on_death` mirrore `ITriggeredAbility.get_AllowForDeadOwner`, PAS un `IsAtomic`.

    python scripts/python/probe_10015_allow_for_dead_owner.py
    python scripts/python/probe_10015_allow_for_dead_owner.py --regenerer
    python scripts/python/probe_10015_allow_for_dead_owner.py --croiser
    python scripts/python/probe_10015_allow_for_dead_owner.py --inertie

CE QUE CE PROBE TRANCHE
-----------------------
Le gate de `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` qui dispense une
triggered-ability du test `UnitExtensions$$IsAlive(owner)` a ete cite dans TOUT le depot comme
`IsAtomic(ability)`. Ce nom est FAUX. Le pseudo-C rend `FUN_180002590(8, DAT_183389188, ability)`,
c'est-a-dire un appel au SLOT 8 d'une interface, et les deux se LISENT :

  * `DAT_183389188` = `IdunBattle.Entities.Abilities.ITriggeredAbility` -- c'est le type DECLARE du
    parametre (`frida/methods.tsv`), et TROIS concordances slot/arite le confirment dans
    `...$$EvaluateEffectTriggerEffectAbilities` : slot 2 = `ShouldTrigger` (2 args), slot 4 =
    `ExecuteBy` (3 args), slot 8 = `get_AllowForDeadOwner` (0 arg, booleen) ;
  * la table des slots vient du champ `slot` d'`Il2CppMethodDefinition` (`global-metadata.dat`),
    meme derivation que `data/symbols/<build>/metadata/interface_slots.tsv`.

Une propriete d'ATOMICITE existe bien, mais c'est une AUTRE : `ITriggerable` slot 0 =
`get_AllowInAtomicMode`, lue quelques instructions plus bas dans la MEME fonction, sous
`IMatchState slot 22 = get_InAtomicMode` et sous le parametre `onlyNonAtomic`. Les deux jeux de
declarants sont quasi disjoints. Confondre les deux, c'est lire la mauvaise propriete SANS QU'AUCUNE
ERREUR NE SOIT LEVEE -- exactement la panne silencieuse que la doctrine des enums decrit.

POURQUOI IL FAUT UN PROBE POUR CA
---------------------------------
`get_AllowForDeadOwner` a un corps TRIVIAL, donc DEDUPLIQUE par IL2CPP : sur les 44 types qui la
declarent, **zero** n'apparait dans `frida/methods.tsv` ni dans `ghidra/functions.tsv`. Les deux
tables sont indexees par ADRESSE ; << `<Classe>$$get_AllowForDeadOwner` n'y est pas >> ne prouve
donc RIEN. La RVA se resout par le TOKEN (`Il2CppCodeGenModule.methodPointers`, localisee par
INTERSECTION sur des couples (rid, VA) connus, puis RELUE sur tous), et le corps se lit :
`b0 01 c3` = `mov al,1 ; ret` = vrai, `32 c0 c3` = `xor al,al ; ret` = faux.

⚠ **SURCHARGER NE VEUT PAS DIRE VRAI, ET C'EST MESURE.** Sur les 43 surcharges, **4** rendent FAUX
(`DevastatingRefrain_AttackAbility`, `MalleusRocketLauncher_AttackAbility`,
`GazeOfMagnus_ApplyEngagementAbility`, `GazeOfMagnus_AttackAbility`). Un a priori
<< surcharge => vrai >> aurait ecrit 4 valeurs fausses. C'est la raison d'etre de l'etage 0 : on LIT
la valeur, on ne la deduit pas de la presence d'une surcharge.

⚠ **ET LA VALEUR D'UNE FEUILLE PEUT VENIR D'UN ANCETRE.** `PowerUpHealingAbility` ne declare rien et
herite le VRAI d'`APowerUpAbility` : sans remontee de chaine (`frida/classes.tsv`), la confrontation
rend TROIS faux desaccords. La chaine est donc remontee jusqu'au premier declarant.

LES QUATRE ETAGES
-----------------
0. DERIVATION / REGENERATION -- lit slots + valeurs dans le build. Tri-etat : jeu absent ou
   desynchronise => `PAS MESURE`, jamais un zero ni un vert.
1. CLIQUET D'ENTREE -- confronte l'entree VERSIONNEE `metadata/allow_for_dead_owner.tsv` a la
   re-derivation. C'est elle qui rend les etages 2-3 jouables dans un worktree sans le jeu.
2. CONFRONTATION DU PORT -- pour chaque classe du registre de triggers dont le NATIF est declare
   explicitement ici, `fire_on_death` doit valoir ce que le build dit. La DETTE mesuree est ecrite
   (`DESACCORDS_CONNUS`) : elle ne peut que retrecir ; un desaccord NEUF fait rougir.
3. INERTIE (`--inertie`) -- `fire_on_death` est-il vraiment illisible sur la face EFFET ? On ne le
   LIT pas, on le fait MORDRE : l'attribut est remplace par une property qui LEVE, et on rejoue un
   dispatch. Rien ne doit lever sur un `EffectTrigger` ; le meme montage sur un `TriggeredAbility`
   DOIT lever -- sans ce second bras, le controle serait vert par vacuite.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pin                                                        # noqa: E402
import il2cpp_metadata                                                  # noqa: E402

REPO = HERE.parent.parent

#: CLASSES CONCRETES qui ancrent la grille des types (cf. `il2cpp_metadata.locate_types`).
ANCRES_TYPES = (
    ("Core.Services", "OperationProcessor"),
    ("IdunBattle.Core.Services", "BattleQuery"),
    ("IdunBattle.Core.Services", "AttackQuery"),
    ("IdunBattle.Core.Services", "MovementQuery"),
    ("IdunBattle.Core.Services", "DamageCalculations"),
    ("IdunBattle.Core", "MatchState"),
)

#: Les DEUX proprietes, et c'est le fond du cas : les separer est le correctif.
METHODES = ("get_AllowForDeadOwner", "get_AllowInAtomicMode")

#: Les namespaces d'abilities balayes. Le perimetre est DERIVE de `ghidra/functions.tsv` (tout type
#: qui y porte au moins un symbole), jamais une liste ecrite d'avance.
PREFIXES = ("IdunBattleLogic.Entities.Abilities.", "IdunBattle.Entities.Abilities.")

#: Les deux corps triviaux, LUS. Tout autre corps sort tel quel -- jamais rabattu sur un booleen.
CORPS = {"b001c3": "TRUE", "32c0c3": "FALSE"}

TSV_REL = "metadata/allow_for_dead_owner.tsv"

#: LE PORT -> LE NATIF, declare A LA MAIN et seulement pour ce qui a ete LU au decompile.
#:
#: ⚠ **CE DICTIONNAIRE N'EST PLUS LA SOURCE DE L'ETAGE 2 -- IL EN EST LE TEMOIN (#10015-r3).**
#: L'appariement effectif est MECANIQUE (`apparier_mecaniquement`, plus bas) : nom court NORMALISE
#: et BIJECTIF DANS LES DEUX SENS. Ces neuf lignes restent parce qu'elles ont ete LUES au decompile
#: une par une : l'etage 2 exige que le critere mecanique les REPRODUISE toutes les neuf, a
#: l'identique. C'est ce controle -- et pas une intuition -- qui autorise a etendre la confrontation
#: de 9 classes a ~130.
#:
#: ⚠ **ET IL NE FAUT PAS LE CONFONDRE AVEC L'AUTRE APPARIEMENT AUTOMATIQUE, QUI RESTE REFUSE.**
#: `--croiser` apparie par le symbole CITE EN DOCSTRING ; mesure du 2026-08-15, il apparie
#: `FuelledByFuryReviveAbility` a `FuelledByFury_ExtraDamageAbility` et les TROIS classes Haywire du
#: port a la MEME native, donc il fabrique des desaccords qui n'en sont pas. Le critere du NOM, lui,
#: ECARTE ces cinq-la (aucune native ne porte leur nom -> ils sortent en `SANS NATIF`) au lieu de les
#: deviner : c'est la difference entre un appariement qui se tait et un qui invente.
NATIF_DU_PORT: dict[str, str] = {
    "SynapticLinchpinAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.SynapticLinchpinAbility",
    "AmbushSummonAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.Ambush_SummonAbility",
    "EnvAmbushResurrectAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvAmbushResurrectAbility",
    "FinalJusticeAbility":
        "IdunBattleLogic.Entities.Abilities.Active.Loki.FinalJusticeAbility",
    "ControlEdictAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility",
    "LightImUpAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility",
    "LordOfTempestsAddIceAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.LordOfTempests_AddIceAbility",
    "ReanimationProtocolsAbility":
        "IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationProtocolsAbility",
    "SplitAbility":
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.SplitAbility",
}
#: ATTENTION -- N'ENTRE ICI QUE CE QUI A ETE LU. `Bounce`, `DrawFire` et `ThrillSeekers` ont ete ECARTES de cet
#: appariement, chacun pour une raison DIFFERENTE et chacune fatale a un cliquet : les deux premiers
#: n'existent sous ce nom dans AUCUNE classe du registre (l'appariement serait perime des l'ecriture),
#: et `ThrillSeekersAbility` (natif) a DEUX contreparties portees
#: (`ThrillSeekersFullHealthTargetAbility`, `ThrillSeekersDamageTakenAbility`) dont la face n'a pas
#: ete relue -- les inscrire d'office fabriquerait deux desaccords non instruits. Ils entrent dans
#: le residu `#10015`, pas dans le cliquet.

#: LA DETTE. Chaque entree est un desaccord CONSTATE, avec la valeur du port ; le cliquet exige
#: qu'il soit TOUJOURS la et TOUJOURS dans ce sens. Il ne peut donc que retrecir -- et un desaccord
#: NEUF, lui, fait rougir.
#:
#: ⚠ **ELLE VALAIT 4 SUR NEUF CLASSES CONFRONTEES ; ELLE VAUT 1 SUR ~130 (#10015-r3).** Les trois
#: sorties (`ControlEdictAbility`, `LightImUpAbility`, `LordOfTempestsAddIceAbility`) sont PORTEES,
#: pas radiees. Et l'elargissement du perimetre en a fait apparaitre DEUX que personne n'avait
#: comptees -- `CursedPlagueBellAttackAbility` et `LifewardsAbility`, toutes deux natif VRAI / port
#: FAUX, toutes deux portees dans le meme commit : la fiche annoncait << au moins 4 abilities >>,
#: c'etait 6. Un cliquet qui ne confronte que ce qu'on lui a nomme ne peut pas montrer ce qu'on a
#: oublie de nommer.
DESACCORDS_CONNUS: dict[str, bool] = {
    #: `EnvAmbushResurrectAbility` : natif FAUX (herite de `BaseTriggeredAbility`), port VRAI.
    #: GARDE volontairement -- cf. la docstring de la classe (`triggers/genestealer.py`) : l'owner
    #: natif d'une `Env*Ability` n'est peut-etre pas une unite, auquel cas `IsUnit(owner)` est faux
    #: et les deux gates sont sautes. Residu `#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1`.
    "EnvAmbushResurrectAbility": True,
}


def build_dir() -> Path:
    return REPO / "data" / "symbols" / build_pin.versioned_build()


def tsv_path() -> Path:
    return build_dir() / TSV_REL


# ------------------------------------------------------------------ etage 0 : la derivation


def deriver() -> tuple[dict, str]:
    """`({type_plein: {methode: (slot, flags, va, valeur)}}, refus)`. `refus` non vide => PAS MESURE."""
    try:
        meta = build_pin.global_metadata()
        buf, image_base, secs, _idx = build_pin.load_dll()
    except Exception as exc:                                            # noqa: BLE001
        return {}, "PAS MESURE : %s" % exc
    methods_tsv = build_dir() / "frida" / "methods.tsv"
    fn_tsv = build_dir() / "ghidra" / "functions.tsv"
    if not methods_tsv.exists() or not fn_tsv.exists():
        return {}, "PAS MESURE : tables du build absentes sous %s" % build_dir().as_posix()

    reader = il2cpp_metadata.read(meta)
    reader.locate(il2cpp_metadata.class_method_order(methods_tsv, "%s.%s" % ANCRES_TYPES[0]))
    reader.locate_types([(ns, nm, il2cpp_metadata.class_method_order(methods_tsv,
                                                                    "%s.%s" % (ns, nm)))
                         for ns, nm in ANCRES_TYPES])

    def rid(m) -> int:
        tok = struct.unpack_from("<I", reader.blob, m.file_offset + reader.entry_size - 12)[0]
        if tok >> 24 != 0x06:
            raise il2cpp_metadata.MetadataRefused(
                "INCOHERENT : token 0x%08x hors de la table des methodes" % tok)
        return tok & 0x00FFFFFF

    # couples (rid, VA) CONNUS : methode au nom unique dans sa classe ET dans `methods.tsv`
    par_classe: dict[str, dict[str, list[int]]] = {}
    with methods_tsv.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("#!"):
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3:
                par_classe.setdefault(c[2], {}).setdefault(
                    c[1].rsplit(".", 1)[-1], []).append(int(c[0], 16))
    connus: list[tuple[int, int]] = []
    for ns, nm in ANCRES_TYPES:
        table = reader.type_methods(ns, nm)
        noms = [m.name for m in table]
        for m in table:
            if noms.count(m.name) != 1:
                continue
            v = par_classe.get("%s.%s" % (ns, nm), {}).get(m.name, [])
            if len(v) == 1:
                connus.append((rid(m), image_base + v[0]))
    if len(connus) < 50:
        return {}, "PAS MESURE : %d couple(s) (rid, VA) connus -- trop peu pour localiser" % len(connus)

    #: LOCALISATION PAR INTERSECTION -- aucun layout recopie. Une base unique, puis TOUS les
    #: couples connus sont RELUS : c'est le controle qui rend le resultat sur.
    bases: set[int] | None = None
    for rd, va in connus[:12]:
        pat, cands = struct.pack("<Q", va), set()
        pos = buf.find(pat)
        while pos >= 0:
            if pos - (rd - 1) * 8 >= 0:
                cands.add(pos - (rd - 1) * 8)
            pos = buf.find(pat, pos + 1)
        bases = cands if bases is None else (bases & cands)
        if bases is not None and len(bases) == 1:
            break
    if not bases or len(bases) != 1:
        return {}, ("PAS MESURE : %d base(s) candidates pour `methodPointers` -- on ne DEVINE pas"
                    % (0 if not bases else len(bases)))
    base = next(iter(bases))
    faux = sum(1 for rd, va in connus
               if struct.unpack_from("<Q", buf, base + (rd - 1) * 8)[0] != va)
    if faux:
        return {}, ("INCOHERENT : la base 0x%x ne reproduit que %d/%d couples connus"
                    % (base, len(connus) - faux, len(connus)))

    types: set[str] = set()
    with fn_tsv.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            c = line.rstrip("\n").split("\t")
            if len(c) < 2 or "$$" not in c[1]:
                continue
            p = c[1].split("$$", 1)[0]
            if p.startswith(PREFIXES) and "u003C" not in p:
                types.add(p)

    out: dict[str, dict] = {}
    for plein in sorted(types):
        ns, _, nm = plein.rpartition(".")
        try:
            table = reader.type_methods(ns, nm)
        except il2cpp_metadata.MetadataRefused:
            continue                                                    # nom non unique -> ecarte
        for m in table:
            if m.name not in METHODES:
                continue
            va = struct.unpack_from("<Q", buf, base + (rid(m) - 1) * 8)[0]
            off = build_pin.va_to_file_offset(image_base, secs, va)
            octets = buf[off:off + 3].hex() if off is not None else ""
            out.setdefault(plein, {})[m.name] = (
                m.slot, m.flags, va, CORPS.get(octets, "CORPS %s" % (octets or "HORS SECTION")))
    return out, ""


def ecrire_tsv(derive: dict) -> int:
    p = tsv_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lignes = [
        "# `ITriggeredAbility` slot 8 = `get_AllowForDeadOwner` et `ITriggerable` slot 0 =",
        "# `get_AllowInAtomicMode` -- les DEUX proprietes que le depot confondait sous le nom",
        "# `IsAtomic` jusqu'a #10015. `valeur` est le CORPS LU (corps trivial deduplique : la RVA",
        "# se resout par le token via `Il2CppCodeGenModule.methodPointers`, cf. le probe).",
        "# `origine` : BASE = declaration `NewSlot` (le defaut de `BaseTriggeredAbility`),",
        "# OVERRIDE = surcharge. Surcharger ne veut PAS dire vrai : 4 surcharges rendent FALSE.",
        "# Entree VERSIONNEE : c'est ce qui rend le cliquet jouable sans le jeu installe.",
        "# Regenerer : python scripts/python/probe_10015_allow_for_dead_owner.py --regenerer",
        "#type\tmethode\tslot\tvaleur\tva\torigine",
    ]
    n = 0
    for plein in sorted(derive):
        for meth in METHODES:
            if meth not in derive[plein]:
                continue
            slot, flags, va, val = derive[plein][meth]
            lignes.append("%s\t%s\t%d\t%s\t0x%x\t%s"
                          % (plein, meth, slot, val, va,
                             "BASE" if flags & 0x0100 else "OVERRIDE"))
            n += 1
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return n


def charger_tsv() -> dict:
    p = tsv_path()
    if not p.exists():
        return {}
    out: dict[str, dict] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        c = line.split("\t")
        if len(c) < 6:
            continue
        out.setdefault(c[0], {})[c[1]] = (int(c[2]), None, int(c[4], 16), c[3])
    return out


# ------------------------------------------------- etage 2 : la confrontation du port


def parents_du_build() -> dict[str, str]:
    """Parent de chaque type, LU dans `frida/classes.tsv` (entree VERSIONNEE)."""
    p = build_dir() / "frida" / "classes.tsv"
    out: dict[str, str] = {}
    if not p.exists():
        return out
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("#!"):
                continue
            c = line.rstrip("\n").split("\t")
            if len(c) >= 3 and c[2]:
                out[c[0]] = c[2]
    return out


def valeur_heritee(tsv: dict, parents: dict, plein: str, meth: str) -> tuple[str, str]:
    """Valeur de `meth` pour `plein`, en REMONTANT la chaine jusqu'au premier declarant."""
    vu, courant, chaine = set(), plein, []
    while courant and courant not in vu:
        vu.add(courant)
        chaine.append(courant.rsplit(".", 1)[-1])
        if courant in tsv and meth in tsv[courant]:
            return tsv[courant][meth][3], "->".join(chaine)
        courant = parents.get(courant)
    return "NON DECLARE DANS LA CHAINE", "->".join(chaine)


def types_natifs_du_build() -> set[str]:
    """Tout type d'ability du build, DERIVE des DEUX entrees VERSIONNEES.

    `ghidra/functions.tsv` seul ne suffit pas : il est indexe par ADRESSE, donc une classe dont
    TOUS les corps sont dedupliques n'y a aucun proprietaire (c'est le fait meme qui a rendu ce cas
    necessaire). `frida/classes.tsv` liste les TYPES, y compris ceux-la. L'union est donc le
    perimetre honnete -- et elle se lit sans le jeu installe, ce qui rend l'etage 2 jouable dans un
    worktree nu."""
    out: set[str] = set()
    fn = build_dir() / "ghidra" / "functions.tsv"
    if fn.exists():
        with fn.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                c = line.rstrip("\n").split("\t")
                if len(c) < 2 or "$$" not in c[1]:
                    continue
                p = c[1].split("$$", 1)[0]
                if p.startswith(PREFIXES) and "u003C" not in p:
                    out.add(p)
    cl = build_dir() / "frida" / "classes.tsv"
    if cl.exists():
        with cl.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("#!"):
                    continue
                c = line.rstrip("\n").split("\t")
                if c and c[0].startswith(PREFIXES) and "u003C" not in c[0]:
                    out.add(c[0])
    return out


def _norm(nom: str) -> str:
    """Nom court CANONIQUE. Le seul ecart de forme mesure entre les deux cotes est le SOULIGNE que
    le natif place aux jointures (`LordOfTempests_AddIceAbility` / `LordOfTempestsAddIceAbility`,
    `Ambush_SummonAbility` / `AmbushSummonAbility`) ; la casse est normalisee par prudence, elle ne
    departage rien aujourd'hui."""
    return nom.replace("_", "").lower()


def apparier_mecaniquement(abilites: dict) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    """`(bijectifs, ambigus, sans_natif)` -- appariement port -> natif par NOM COURT NORMALISE.

    LE CRITERE, ET POURQUOI IL N'EST PAS UNE DEVINETTE. Un appariement n'est retenu que s'il est
    BIJECTIF DANS LES DEUX SENS : exactement UN type natif porte ce nom normalise, ET exactement une
    classe du port. Tout le reste sort en `ambigus` ou en `sans_natif` -- jamais rabattu sur un
    << plus probable >>. C'est la difference de nature avec `--croiser`, qui CHOISIT (`(pref or
    cands or [None])[0]`) et fabrique ainsi cinq faux appariements mesures.

    ⚠ **ET LE CRITERE EST LUI-MEME CONTROLE**, ce qui est la seule raison de lui faire confiance :
    l'etage 2 exige qu'il reproduise les NEUF appariements de `NATIF_DU_PORT`, lus au decompile un
    par un. Mesure du 2026-08-17 sur `t6dpr4k06g` : 9/9 reproduits, 0 ambiguite d'aucun cote,
    130 appariements retenus sur 196 classes de registre. Si un renommage futur casse un des neuf,
    l'etage 2 ROUGIT au lieu de se degrader en silence.

    ⚠ **CE QU'IL NE COUVRE PAS EST STRUCTUREL, PAS UN RESIDU A FINIR** : le port SCINDE souvent une
    native en plusieurs classes (les trois `HaywireMine*` du port viennent toutes de
    `HaywireMineSteppableAbility`, les sept `PowerUpSummonSpawn*` d'une seule fabrique). Aucun
    critere de NOM ne peut apparier ces cas-la -- il faut les LIRE. Ils sortent en `sans_natif`,
    comptes a chaque run."""
    natifs = types_natifs_du_build()
    par_natif: dict[str, list[str]] = {}
    for t in natifs:
        par_natif.setdefault(_norm(t.rsplit(".", 1)[-1]), []).append(t)
    par_port: dict[str, list[str]] = {}
    for nom in abilites:
        par_port.setdefault(_norm(nom), []).append(nom)

    bijectifs: dict[str, str] = {}
    ambigus: dict[str, list[str]] = {}
    sans_natif: list[str] = []
    for nom in sorted(abilites):
        cle = _norm(nom)
        cands = sorted(par_natif.get(cle, []))
        if len(par_port.get(cle, [])) > 1:
            ambigus[nom] = ["<%d classes du PORT portent ce nom>" % len(par_port[cle])] + cands
        elif not cands:
            sans_natif.append(nom)
        elif len(cands) > 1:
            ambigus[nom] = cands
        else:
            bijectifs[nom] = cands[0]
    return bijectifs, ambigus, sans_natif


def classes_du_registre():
    from engine.runner.operations.triggers.dispatch import registry as REG
    abilites, effets = {}, {}
    for d in (REG.TRAIT_TRIGGERS, REG.ABILITY_TRIGGERS, REG.ACTIVE_ABILITY_TRIGGERS,
              REG.PASSIVE_HELPER_ABILITY_TRIGGERS, REG.RELIC_ABILITY_TRIGGERS):
        for lot in d.values():
            for c in lot:
                abilites[c.__name__] = c
    for c in REG.GLOBAL_TRIGGERS:
        abilites[c.__name__] = c
    for lot in REG.EFFECT_TRIGGERS.values():
        for c in lot:
            effets[c.__name__] = c
    return abilites, effets


def confronter_port(tsv: dict) -> int:
    abilites, effets = classes_du_registre()
    parents = parents_du_build()
    print("registre : %d classes ABILITY, %d classes EFFET" % (len(abilites), len(effets)))
    if not tsv:
        print("  PAS MESURE : entree versionnee absente (%s)" % tsv_path().as_posix())
        return 99
    if not parents:
        print("  PAS MESURE : `frida/classes.tsv` absent -- la chaine d'heritage est illisible")
        return 99

    bijectifs, ambigus, sans_natif = apparier_mecaniquement(abilites)
    rc = 0

    # --- 2a : LE CRITERE EST-IL DIGNE DE CONFIANCE ? ------------------------------------------
    #: On ne le suppose pas, on le CONFRONTE au seul etalon qui existe : les appariements LUS au
    #: decompile. Ce controle precede la confrontation -- si le critere a derive, tout ce qu'il rend
    #: ensuite est suspect, et un desaccord de plus ne serait pas lisible.
    if not NATIF_DU_PORT:
        print("  PAS MESURE : le TEMOIN `NATIF_DU_PORT` est VIDE -- le controle 2a serait vacant")
        return 99
    ecarts_temoin = 0
    for nom, plein in sorted(NATIF_DU_PORT.items()):
        obtenu = bijectifs.get(nom)
        if obtenu is None:
            print("  TEMOIN PERDU : %-34s le critere du NOM ne l'apparie plus (%s)"
                  % (nom, "ambigu" if nom in ambigus else
                     ("sans natif" if nom in sans_natif else "absent du registre")))
            ecarts_temoin += 1
        elif obtenu != plein:
            print("  TEMOIN DIVERGENT : %-30s lu=%s / critere=%s" % (nom, plein, obtenu))
            ecarts_temoin += 1
    if ecarts_temoin:
        print("  ROUGE : %d/%d appariement(s) LU(S) au decompile non reproduit(s) par le critere du"
              " NOM -- l'etage 2b ne vaut plus rien tant que ce n'est pas relu"
              % (ecarts_temoin, len(NATIF_DU_PORT)))
        rc = 1
    else:
        print("  2a : le critere du NOM reproduit les %d appariement(s) LU(S) au decompile (%d/%d)"
              % (len(NATIF_DU_PORT), len(NATIF_DU_PORT), len(NATIF_DU_PORT)))

    # --- 2b : LA CONFRONTATION, sur TOUT ce que le critere apparie ----------------------------
    accord = 0
    for nom, plein in sorted(bijectifs.items()):
        cls = abilites[nom]
        port = bool(getattr(cls, "fire_on_death", False))
        val, chaine = valeur_heritee(tsv, parents, plein, "get_AllowForDeadOwner")
        if val not in ("TRUE", "FALSE"):
            print("  NON LU : %-34s %s [%s]" % (nom, val, chaine))
            rc = 1
            continue
        natif = (val == "TRUE")
        if natif == port:
            accord += 1
            if nom in DESACCORDS_CONNUS:
                print("  DETTE RESORBEE, RETIRE-LA DE `DESACCORDS_CONNUS` : %s" % nom)
                rc = 1
            continue
        attendu = DESACCORDS_CONNUS.get(nom)
        if attendu is None:
            print("  DESACCORD NEUF : %-28s port=%s natif=%s  (%s)" % (nom, port, natif, plein))
            rc = 1
        elif attendu != port:
            print("  DETTE DEPLACEE : %-29s port=%s, la dette disait %s" % (nom, port, attendu))
            rc = 1
    print("  2b : %d classe(s) confrontee(s) -- ACCORD %d, dette declaree %d"
          % (len(bijectifs), accord, len(DESACCORDS_CONNUS)))
    #: PORTEE -- ce que cet etage NE couvre PAS, imprime a chaque run : un cliquet qui tait son
    #: perimetre se lit comme une couverture totale. Les deux causes sont DISTINCTES et le restent.
    print("  NON COUVERT : %d sans natif de meme nom (le port SCINDE une native en N classes),"
          " %d nom(s) ambigu(s)" % (len(sans_natif), len(ambigus)))
    for nom in sorted(ambigus):
        print("      AMBIGU %-38s -> %s" % (nom, ambigus[nom]))
    return rc


# ------------------------------------------------------- etage 3 : la morsure (inertie)


def morsure() -> int:
    """`fire_on_death` est-il LU sur la face EFFET ? On le fait MORDRE, on ne le lit pas."""
    from engine.runner.operations.triggers.base import TriggeredAbility, EffectTrigger

    class Mordu(Exception):
        pass

    class _Piege:
        def __get__(self, obj, cls=None):
            raise Mordu("fire_on_death LU sur %s" % (cls.__name__ if cls else "?"))

    abilites, effets = classes_du_registre()
    #: ATTENTION -- LE PERIMETRE SE DERIVE, IL NE SE CITE PAS -- et la fiche du residu se trompait de NOMS.
    #: `#462-r4b-r1-r1-r1-r1-c-r3-r3` enumere << PhoenixGemReviveAbility,
    #: PhoenixGemRemoveMarkerOnRevive, PhoenixGemRemoveMarkerOnResurrect, RitesOfMorkaiReviveTrigger >>.
    #: Mesure du 2026-08-15 : le compte (4) est juste, la MEMBRANCE a derive -- deux de ces noms ne
    #: portent plus l'attribut, et deux AUTRES classes le portent. Le critere retenu est l'attribut
    #: EFFECTIF (`getattr`), pas la declaration : une sous-classe qui l'herite est concernee autant
    #: que celle qui l'ecrit.
    porteuses = sorted({c.__name__ for c in effets.values()
                        if getattr(c, "fire_on_death", False)})
    print("classes EFFET a `fire_on_death` VRAI : %d -> %s" % (len(porteuses), porteuses))
    if not porteuses:
        print("  PAS MESURE : aucune classe EFFET ne porte l'attribut -- le controle serait VIDE")
        return 99

    from engine.runner.operations.triggers.dispatch import core as CORE
    rc = 0
    # bras A -- la face EFFET ne doit RIEN lire
    for c in effets.values():
        if not getattr(c, "fire_on_death", False):
            continue
        setattr(c, "fire_on_death", _Piege())
        try:
            applique = CORE._owner_gate_applies(c(0))
            if applique:
                print("  ROUGE : `_owner_gate_applies` rend VRAI sur %s (face EFFET gatee)"
                      % c.__name__)
                rc = 1
        except Mordu as exc:
            print("  ROUGE : %s" % exc)
            rc = 1
        finally:
            delattr(c, "fire_on_death")
    # bras B -- CONTRE-EPREUVE : sur une ability, le MEME montage DOIT mordre. Sans ce bras, un
    # `_owner_gate_applies` casse en `return False` rendrait le bras A vert par vacuite.
    cible = next((c for c in abilites.values() if not getattr(c, "owner_is_global", False)), None)
    if cible is None:
        print("  PAS MESURE : aucune classe ABILITY non-globale au registre")
        return 99
    from engine.runner.state import State
    from engine.runner.components import UnitComponent
    #: LE REGIME OU L'ATTRIBUT EST LU, et il est ETROIT : owner PRESENT, portant un
    #: `UnitComponent`, et NON VIVANT. Un owner absent tombe sur le `continue` du porteur
    #: introuvable AVANT toute lecture -- le montage naif ne mord donc pas, et se lirait comme
    #: une preuve d'inertie alors qu'il ne prouve que le surplus de
    #: `#462-r4b-r1-r1-r1-r1-c-r3-r2`.
    st = State()
    ent = st.add_entity(4242)
    ent.add_component(UnitComponent(visual_id=None, alive=False))
    inst = cible(4242)
    #: On SUBSTITUE le collecteur : `collect_triggered_abilities` n'inscrit que ce qui porte un
    #: `StatsComponent`, et fabriquer un porteur complet ferait dependre la contre-epreuve du
    #: substrat de stats plutot que du GATE qu'elle teste. La fonction sous test reste la VRAIE
    #: (`evaluate_trigger_operation`), avec son vrai bloc de gate.
    vrai_collect, vrais_globaux = CORE.collect_triggered_abilities, CORE.collect_global_triggers
    CORE.collect_triggered_abilities = lambda s: [inst]
    CORE.collect_global_triggers = lambda: []
    setattr(cible, "fire_on_death", _Piege())
    mordu = False
    try:
        CORE.evaluate_trigger_operation(st, _ev_bidon(inst))
    except Mordu:
        mordu = True
    except Exception:                                                   # noqa: BLE001
        pass
    finally:
        delattr(cible, "fire_on_death")
        CORE.collect_triggered_abilities = vrai_collect
        CORE.collect_global_triggers = vrais_globaux
    if not mordu:
        print("  ROUGE : le montage NE MORD PAS sur %s -- le bras A serait vert par vacuite"
              % cible.__name__)
        rc = 1
    else:
        print("  contre-epreuve OK : le montage MORD sur %s (owner PRESENT, mort)" % cible.__name__)
    return rc


def _ev_bidon(inst):
    from engine.runner.operations.triggers.base import TriggerEvent
    return TriggerEvent(inst.event_id, 1, 2, ranged=False, profile=None)


# ------------------------------------------------------------------------------- pilotage


def main() -> int:
    ap = argparse.ArgumentParser(description="#10015 -- get_AllowForDeadOwner")
    ap.add_argument("--regenerer", action="store_true",
                    help="reecrit l'entree versionnee depuis le build")
    ap.add_argument("--croiser", action="store_true",
                    help="appariement HEURISTIQUE par le symbole cite en docstring (JAMAIS bloquant)")
    ap.add_argument("--inertie", action="store_true", help="etage 3 seul (morsure)")
    a = ap.parse_args()

    print("=== #10015 -- `fire_on_death` = `ITriggeredAbility` slot 8 `get_AllowForDeadOwner` ===")
    if a.inertie:
        return morsure()

    tsv = charger_tsv()
    rc = 0

    if a.regenerer:
        derive, refus = deriver()
        if refus:
            print("etage 0 : %s" % refus)
            return 99
        n = ecrire_tsv(derive)
        print("etage 0 : entree versionnee reecrite (%d type(s), %d ligne(s)) -> %s"
              % (len(derive), n, tsv_path().as_posix()))
        tsv = charger_tsv()
    else:
        derive, refus = deriver()
        if refus:
            print("etage 1 : %s -- l'entree versionnee tient lieu de mesure" % refus)
        else:
            ecarts = []
            for plein in sorted(set(derive) | set(tsv)):
                for meth in METHODES:
                    d = derive.get(plein, {}).get(meth)
                    t = tsv.get(plein, {}).get(meth)
                    if (d is None) != (t is None):
                        ecarts.append("%s::%s %s" % (plein, meth,
                                                     "absent du TSV" if t is None else "absent du build"))
                    elif d is not None and (d[0], d[3]) != (t[0], t[3]):
                        ecarts.append("%s::%s slot/valeur %s vs %s"
                                      % (plein, meth, (d[0], d[3]), (t[0], t[3])))
            if ecarts:
                print("etage 1 : ROUGE -- %d ecart(s) entree versionnee <-> build" % len(ecarts))
                for e in ecarts[:20]:
                    print("    %s" % e)
                print("    REGENERER : python scripts/python/probe_10015_allow_for_dead_owner.py --regenerer")
                rc = 1
            else:
                print("etage 1 : entree versionnee CONCORDANTE avec le build (%d types)" % len(derive))

    nb = {m: sum(1 for v in tsv.values() if m in v) for m in METHODES}
    vals = {}
    for v in tsv.values():
        for m in METHODES:
            if m in v:
                vals.setdefault(m, {}).setdefault(v[m][3], 0)
                vals[m][v[m][3]] += 1
    for m in METHODES:
        print("  %-24s %3d declarant(s) %s" % (m, nb.get(m, 0), vals.get(m, {})))

    print("")
    print("etage 2 -- confrontation du port")
    rc = confronter_port(tsv) or rc

    if a.croiser:
        print("")
        print("etage 2bis -- appariement HEURISTIQUE (inventaire, jamais bloquant)")
        croiser_heuristique(tsv)
    print("")
    print("VERDICT : rc=%d" % rc)
    return rc


def croiser_heuristique(tsv: dict) -> None:
    import re
    citation = re.compile(r"\b((?:IdunBattle|IdunBattleLogic|idun)[\w.]*?\.(\w+))\$\$")
    abilites, _e = classes_du_registre()
    parents = parents_du_build()
    accord = desaccord = nonmappe = 0
    lignes = []
    for nom, cls in sorted(abilites.items()):
        if nom in NATIF_DU_PORT:
            continue
        port = bool(getattr(cls, "fire_on_death", False))
        src = (cls.__doc__ or "") + "\n" + (sys.modules[cls.__module__].__doc__ or "")
        cands = [m.group(1) for m in citation.finditer(src)
                 if m.group(2).endswith(("Ability", "Trigger"))]
        pref = [c for c in cands if c.rsplit(".", 1)[-1] == nom]
        plein = (pref or cands or [None])[0]
        if plein is None:
            nonmappe += 1
            continue
        val, chaine = valeur_heritee(tsv, parents, plein, "get_AllowForDeadOwner")
        if val not in ("TRUE", "FALSE"):
            nonmappe += 1
            continue
        if (val == "TRUE") == port:
            accord += 1
        else:
            desaccord += 1
            lignes.append("    port=%-5s natif=%-5s %-40s <- %s" % (port, val, nom, plein))
    print("    ACCORD %d / DESACCORD %d / NON APPARIE %d (hors appariement explicite)"
          % (accord, desaccord, nonmappe))
    for l in lignes:
        print(l)
    print("    ATTENTION : un DESACCORD ici peut n'etre qu'un mauvais APPARIEMENT -- a lire un par un.")


if __name__ == "__main__":
    raise SystemExit(main())
