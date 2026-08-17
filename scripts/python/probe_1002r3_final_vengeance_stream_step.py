#!/usr/bin/env python
"""probe #1002-r3 -- ce que poussent `FinalVengeance_UnitEffect$$ApplyInternal` / `$$RevertInternal`.

LA FICHE ACCUSAIT LE MAUVAIS CHAMP, ET C'EST CE QUI RENDAIT LE DICT ININTERPRETABLE.
Elle disait : << les deux poussent une **Operation** a `<processor>+0x70` avec un
`Dictionary{0x76: 0}` (apply) / `{0x76: 1}` (revert) [...] tant que le dict n'est pas identifie, on
ne peut PAS conclure "purement visuel" >>. Or `IdunBattle.Entities.Effects.BaseEffect$$Init` ecrit,
verbatim :

    *(this + 0x68) = operationProcessor
    *(this + 0x70) = events

`+0x70` n'est donc PAS le processeur d'Operations -- c'est le canal d'EVENEMENTS. Il n'y a aucune
Operation a porter : ce que les deux corps poussent est un STEP DE STREAM.

CE QUE CE PROBE ETABLIT, EN LISANT LE BINAIRE (aucune VA en dur -- bornes par SYMBOLE) :
  1. les deux corps posent la cle `0x76` avec la valeur `0` (apply) / `1` (revert) ;
  2. les deux appellent le SLOT 2 d'une interface, avec le step `0xc` ;
  3. c'est la MEME interface et le MEME slot qu'une Operation TEMOIN dont Ghidra NOMME le
     recepteur -- `IdunBattle.Operations.AddActiveAbilityOperation$$Execute` fait
     `<slot 2>(IdunBattle.Core.AOperation$$get_Events(this), 0xd, entityId, {...})`. C'est ce
     cran-la qui identifie `+0x70` comme un canal d'events, et non le nom du champ ;
  4. `0xc` nomme `ChangeStats` dans `IdunBattle.Streams.StepType` et `0x76` nomme
     `UnitStats_IsPlayDeathAnimationOnHit` dans `IdunBattle.Streams.TagKey` -- LUS dans
     `data/symbols/<build>/frida/enums.tsv`, jamais recopies ;
  5. le tag n'a AUCUN consommateur logique : les seuls symboles du build qui le portent sont
     `idun.Game.Board.AUnitView$$get_/set_/SetPlayDeathAnimationOnHit`, c.-a-d. la couche VUE.
     AUCUN sous `IdunBattle.` ni `IdunBattleLogic.`.

CE CINQUIEME CRAN EST LE SEUL QUI PUISSE SE PERIMER, et c'est pour lui que ce probe est versionne :
le jour ou un consommateur LOGIQUE de ce tag apparait, << purement visuel >> est a refaire.

VERDICT : rien a porter cote moteur. L'effet demande a la VUE de ne pas jouer l'animation de mort
sur le coup (`0`) tant qu'il est applique, et la lui rend (`1`) au retrait -- ce qu'il faut
exactement pour que le summon place sa derniere attaque (`FinalJustice`) AVANT de tomber.

Usage (offline, aucun runner, aucune session Frida) :
    python probe_1002r3_final_vengeance_stream_step.py

Codes de retour : 0 = tout tient ; 1 = un cran est tombe ; 99 = NON MESURE (binaire absent).

ASCII only (cp1252).
"""

from __future__ import annotations

import argparse

import probe_10018_effectsdatabase_registry as P10018

SYM_APPLY = ("IdunBattleLogic.Entities.Abilities.Triggered.Loki."
             "FinalVengeance_UnitEffect$$ApplyInternal")
SYM_REVERT = ("IdunBattleLogic.Entities.Abilities.Triggered.Loki."
              "FinalVengeance_UnitEffect$$RevertInternal")
#: TEMOIN : une Operation dont Ghidra NOMME le recepteur (`AOperation$$get_Events`). C'est elle qui
#: donne son sens au couple (interface, slot) qu'on relevera dans les deux corps ci-dessus.
SYM_TEMOIN = "IdunBattle.Operations.AddActiveAbilityOperation$$Execute"

ENUM_STEP = "IdunBattle.Streams.StepType"
ENUM_TAG = "IdunBattle.Streams.TagKey"

#: Ce que le port DOIT retrouver -- ecrit ici pour que le probe soit falsifiable, pas pour etre cru.
TAG_ATTENDU = 0x76
STEP_ATTENDU = 0xC
STEP_TEMOIN = 0xD
NOM_STEP_ATTENDU = "ChangeStats"
NOM_TAG_ATTENDU = "UnitStats_IsPlayDeathAnimationOnHit"
#: Le tag ne doit etre porte QUE par la couche vue. Prefixes de la couche LOGIQUE, qui doivent
#: rendre zero.
PREFIXES_LOGIQUE = ("IdunBattle.", "IdunBattleLogic.")
MOTIF_TAG = "PlayDeathAnimationOnHit"


def _capstone():
    import capstone

    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    return capstone, md


def _lire(dll, symbole):
    d, f = P10018.bornes_fonction(symbole)
    code, _base = P10018.lire_code(dll, d, f)
    _cs, md = _capstone()
    return list(md.disasm(code, d))


def _appel_interface(insns, cible_helper):
    """(slot, adresse du slot d'interface, step) du PREMIER appel a `cible_helper`.

    Le helper d'appel d'interface a la forme `f(slot, Il2CppClass*, this, arg1, ...)`, donc en x64 :
    `ecx` = slot, `rdx` = `[rip + X]` (le slot de classe de l'INTERFACE), `r9d` = arg1.
    """
    capstone, _md = _capstone()
    slot = iface = step = None
    for i, ins in enumerate(insns):
        if (ins.mnemonic == "call" and ins.operands
                and ins.operands[0].type == capstone.x86.X86_OP_IMM
                and ins.operands[0].imm == cible_helper):
            for k in range(i - 1, max(-1, i - 14), -1):
                q = insns[k]
                if slot is None and q.mnemonic == "mov" and q.op_str.startswith("ecx, "):
                    v = q.op_str.split(", ", 1)[1]
                    slot = int(v, 16) if v.startswith("0x") else int(v)
                if iface is None and q.mnemonic == "mov" and q.op_str.startswith("rdx, qword ptr ["):
                    for op in q.operands:
                        if (op.type == capstone.x86.X86_OP_MEM
                                and op.mem.base == capstone.x86.X86_REG_RIP):
                            iface = q.address + q.size + op.mem.disp
                if step is None and q.mnemonic == "mov" and q.op_str.startswith("r9d, "):
                    v = q.op_str.split(", ", 1)[1]
                    step = int(v, 16) if v.startswith("0x") else int(v)
            if slot is not None and iface is not None:
                return slot, iface, step
    return slot, iface, step


def _cle_valeur(insns):
    """(cle, valeur) poses sur la pile juste avant le `Dictionary.Add` -- LUS, pas postules.

    Motif : `lea r8, [rsp+A] ; lea rdx, [rsp+B] ; mov dword ptr [rsp+A], <valeur> ;
             mov dword ptr [rsp+B], <cle> ; call Add`. `rdx` = la CLE (2e argument), `r8` = la
    VALEUR (3e). Les deux emplacements sont derives des `lea`, jamais ecrits en dur.
    """
    slot_cle = slot_val = None
    for ins in insns:
        if ins.mnemonic == "lea" and ins.op_str.startswith("rdx, ["):
            slot_cle = ins.op_str[ins.op_str.index("[") + 1:ins.op_str.rindex("]")].strip()
        if ins.mnemonic == "lea" and ins.op_str.startswith("r8, ["):
            slot_val = ins.op_str[ins.op_str.index("[") + 1:ins.op_str.rindex("]")].strip()
    cle = valeur = None
    for ins in insns:
        if ins.mnemonic != "mov":
            continue
        for emplacement, nom in ((slot_cle, "cle"), (slot_val, "valeur")):
            if emplacement and ins.op_str.startswith("dword ptr [%s], " % emplacement):
                v = ins.op_str.split(", ", 1)[1]
                val = int(v, 16) if v.startswith("0x") else int(v)
                if nom == "cle":
                    cle = val
                else:
                    valeur = val
    return cle, valeur


def _membres(nom_enum):
    chemin = (P10018.RACINE / "data" / "symbols" / P10018.BUILD_ATTENDU / "frida" / "enums.tsv")
    with chemin.open("r", encoding="utf-8", errors="replace") as fh:
        for ligne in fh:
            p = ligne.rstrip("\n").split("\t")
            if len(p) >= 2 and p[0] == nom_enum:
                out = {}
                for morceau in p[1].split(","):
                    if "=" in morceau:
                        v, n = morceau.split("=", 1)
                        out[int(v)] = n
                return out
    return {}


def main() -> int:
    argparse.ArgumentParser().parse_args()
    try:
        build, dll = P10018.chemin_build()
    except SystemExit as exc:
        print("NON MESURE : %s" % exc)
        return 99
    print("BUILD %s" % build)

    apply_i = _lire(dll, SYM_APPLY)
    revert_i = _lire(dll, SYM_REVERT)
    temoin_i = _lire(dll, SYM_TEMOIN)

    # Le helper d'appel d'interface se DERIVE : c'est la seule cible d'appel commune aux trois
    # corps qui soit precedee d'un `mov ecx, <petit immediat>` (le slot).
    capstone, _md = _capstone()

    def cibles(insns):
        out = set()
        for i, ins in enumerate(insns):
            if (ins.mnemonic == "call" and ins.operands
                    and ins.operands[0].type == capstone.x86.X86_OP_IMM):
                for k in range(i - 1, max(-1, i - 14), -1):
                    q = insns[k]
                    if q.mnemonic == "mov" and q.op_str.startswith("ecx, ") \
                            and not q.op_str.split(", ")[1].startswith(("r", "e")):
                        out.add(ins.operands[0].imm)
                        break
        return out

    communs = cibles(apply_i) & cibles(revert_i) & cibles(temoin_i)
    ok_helper = len(communs) == 1
    print("CRAN 0 -- helper d'appel d'interface DERIVE (commun aux 3 corps) : %s (%d candidat(s))"
          % ("OK" if ok_helper else "ECHEC", len(communs)))
    if not ok_helper:
        print("REFUS DE CONCLURE : le helper n'est pas identifiable.")
        return 1
    helper = next(iter(communs))

    sa, ia, st_a = _appel_interface(apply_i, helper)
    sr, ir, st_r = _appel_interface(revert_i, helper)
    st_, it_, st_t = _appel_interface(temoin_i, helper)
    ca, va = _cle_valeur(apply_i)
    cr, vr = _cle_valeur(revert_i)

    print("  apply  : slot=%s iface=%s step=%s ; dict {%s: %s}"
          % (sa, ("0x%x" % ia) if ia else None, ("0x%x" % st_a) if st_a is not None else None,
             ("0x%x" % ca) if ca is not None else None, va))
    print("  revert : slot=%s iface=%s step=%s ; dict {%s: %s}"
          % (sr, ("0x%x" % ir) if ir else None, ("0x%x" % st_r) if st_r is not None else None,
             ("0x%x" % cr) if cr is not None else None, vr))
    print("  temoin : slot=%s iface=%s step=%s   (%s)"
          % (st_, ("0x%x" % it_) if it_ else None,
             ("0x%x" % st_t) if st_t is not None else None, SYM_TEMOIN))

    crans = {}
    crans["1_cle_et_valeurs"] = (ca == TAG_ATTENDU and cr == TAG_ATTENDU and va == 0 and vr == 1)
    crans["2_step_0xc"] = (st_a == STEP_ATTENDU and st_r == STEP_ATTENDU)
    # CRAN 3 -- c'est LUI qui dit que `+0x70` est un canal d'EVENTS : meme interface, meme slot
    # qu'une Operation dont le recepteur est nomme `AOperation$$get_Events`. Le temoin doit par
    # ailleurs porter un step DIFFERENT, sinon la comparaison serait vacante.
    crans["3_meme_canal_que_le_temoin"] = (sa == sr == st_ and ia == ir == it_
                                           and st_t == STEP_TEMOIN)

    steps = _membres(ENUM_STEP)
    tags = _membres(ENUM_TAG)
    crans["4_les_ordinaux_nomment_bien_ca"] = (steps.get(STEP_ATTENDU) == NOM_STEP_ATTENDU
                                               and tags.get(TAG_ATTENDU) == NOM_TAG_ATTENDU)
    print("  StepType(0x%x) = %s ; TagKey(0x%x) = %s"
          % (STEP_ATTENDU, steps.get(STEP_ATTENDU), TAG_ATTENDU, tags.get(TAG_ATTENDU)))

    # CRAN 5 -- aucun consommateur LOGIQUE du tag.
    porteurs = [nom for _va, nom in P10018.symboles_tries() if MOTIF_TAG in nom]
    logiques = [n for n in porteurs if n.startswith(PREFIXES_LOGIQUE)]
    print("  symboles portant `%s` : %d -> %s" % (MOTIF_TAG, len(porteurs), porteurs))
    # le non-vide est ASSERTIONNE : une liste vide ferait passer `logiques == []` pour un vert
    # alors qu'elle ne mesurerait rien (motif introuvable = table changee).
    crans["5_tag_lu_par_la_VUE_seulement"] = (len(porteurs) > 0 and not logiques)

    print("")
    for k in sorted(crans):
        print("  [%s] %s" % ("PASS" if crans[k] else "FAIL", k))
    if all(crans.values()):
        print("")
        print("VERDICT : `+0x70` est le canal d'EVENTS (pas le processeur d'Operations), le step est")
        print("`StepType.%s` et la cle `TagKey.%s`" % (NOM_STEP_ATTENDU, NOM_TAG_ATTENDU))
        print("(apply -> 0 = ne joue PAS l'animation de mort sur le coup ; revert -> 1 = la rend).")
        print("Aucun consommateur logique : RIEN A PORTER cote moteur.")
    return 0 if all(crans.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
