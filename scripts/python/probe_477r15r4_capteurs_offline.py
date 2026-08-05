#!/usr/bin/env python3
"""#477-r15-r4/r5/r6/r7 -- LE CLIQUET OFFLINE des capteurs, jouable SANS session Frida.

    python probe_477r15r4_capteurs_offline.py

CE QU'IL GARDE, ET POURQUOI OFFLINE
-----------------------------------
Les grandeurs que l'emetteur de flux COPIAIT de l'oracle sont desormais LUES. Des capteurs les
portent, et chacun repose sur un ENTIER ou un NOM qui peut glisser AU PROCHAIN BUILD, en silence :

  r4  `COMBAT_STAT_IDS.range = 2`   -- si `IdunBattle.Entities.Enum.StatType` renumerote,
                                       le hook lira un AUTRE stat et publiera une valeur
                                       parfaitement plausible ;
  r5  `numberOfMembersMax`          -- `StatPart.Maximum` vaut 2 ; meme risque, et le hook
                                       ecrit ce littéral en clair (`partBufMax`) ;
  r6  `actives[].state`             -- le sous-objet doit EXISTER, et le probe live doit le
                                       CONSOMMER au lieu de retomber sur un defaut ;
  r7  `armorMax` / `healthMax`      -- les deux maximums, pris jusqu'ici au champ BRUT
                                       `MaximumValue@0x14` d'`observeBattle`. Le capteur
                                       d'armure repose sur `StatType.Armor` = 4, et sur le fait
                                       que cette cle vive dans `STAT_IDS_MAX_SEUL` et NON dans
                                       `COMBAT_STAT_IDS` : cette derniere est publiee sous
                                       `statTypes` et `engine/entities/stats.py::seed_unit_stats`
                                       l'itere pour materialiser un `StatComponent` par entree --
                                       or `StatType.Armor` est un `FillUpStatComponent`. L'y
                                       ajouter ne casserait AUCUN test : c'est exactement le
                                       genre de derive qu'un cliquet doit tenir.

Rien de tout cela n'exige le jeu : les tables du build sont VERSIONNEES
(`data/symbols/<build>/frida/enums.tsv`) et les sources sont dans l'arbre. Ce probe se joue donc
AVANT la fenetre de reinject -- c'est ce qui permet de livrer un capteur deja garde.

⚠ UN BALAYAGE QUI NE VISITE RIEN REND ZERO. Chaque etape imprime son TEMOIN (combien de cles
comparees, combien de motifs cherches) et rougit si le temoin est VIDE : un `enums.tsv` illisible
ou un fichier renomme doit se voir comme une PANNE, jamais comme un accord.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

ROOT = HERE.parents[1]
HOOK = ROOT / "frida" / "hooks" / "features" / "ai-step" / "rpc-snapshot.ts"
INTERNALS = ROOT / "frida" / "hooks" / "features" / "ai-step" / "internals.ts"
PROBE_LIVE = HERE / "probe_477r15a_stream_conformance.py"

from engine.entities.stats import StatPart, StatType  # noqa: E402
from engine.streams.tag_key import TagKey  # noqa: E402


class Panne(RuntimeError):
    """Le probe n'a pas pu MESURER -- distinct d'un desaccord."""


def build_courant() -> str:
    """Le build qui FAIT FOI -- delegue au foyer unique `symbols_layout.current_build()`.

    ⚠ NE PAS RE-DERIVER ICI. Une premiere version choisissait « le premier repertoire dont le
    fichier `BUILD` se nomme lui-meme » : elle a rendu `gqfc5mff6c`, une ARCHIVE, et compare la
    table du hook a un enum PERIME. Deux builds versionnes coexistent exprès (leur diff est le
    rapport de changement du jeu) ; seul `data/symbols/CURRENT` les departage."""
    from symbols_layout import LayoutError, current_build
    try:
        return current_build()
    except LayoutError as e:
        raise Panne(str(e)) from e


def enum_du_build(build: str, nom_plein: str) -> dict:
    """`{membre: ordinal}` d'un enum, LU dans la table versionnee du build."""
    tsv = ROOT / "data" / "symbols" / build / "frida" / "enums.tsv"
    for ligne in tsv.read_text(encoding="utf-8", errors="replace").split("\n"):
        nom, _, corps = ligne.partition("\t")
        if nom.strip() != nom_plein:
            continue
        out = {}
        for entree in corps.strip().split(","):
            val, _, membre = entree.partition("=")
            try:
                out[membre] = int(val)
            except ValueError:
                continue
        return out
    raise Panne("enum `%s` absent de %s" % (nom_plein, tsv))


def _table_ts(nom: str) -> dict:
    """Une table `Record<string, number>` LUE dans la source du hook -- pas recopiee ici.

    La recopier ferait de ce probe un miroir de lui-meme : il rougirait si le hook change, ce
    qui est l'inverse du but. On veut confronter le hook au BUILD."""
    src = HOOK.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"const %s: Record<string, number> = \{(.*?)\n\};" % re.escape(nom), src, re.S)
    if not m:
        raise Panne("`%s` introuvable dans %s" % (nom, HOOK))
    corps = re.sub(r"//[^\n]*", "", m.group(1))          # les commentaires portent des chiffres
    return {k: int(v) for k, v in re.findall(r"(\w+)\s*:\s*(\d+)", corps)}


def table_du_hook() -> dict:
    """`COMBAT_STAT_IDS` -- la table publiee sous `statTypes`, donc ITEREE par `seed_unit_stats`."""
    return _table_ts("COMBAT_STAT_IDS")


def table_max_seul_du_hook() -> dict:
    """`STAT_IDS_MAX_SEUL` (#477-r15-r7) -- les `StatType` lus UNIQUEMENT en `StatPart.Maximum`.

    Elle est SEPAREE de `COMBAT_STAT_IDS` pour une raison fonctionnelle, pas cosmetique : la
    premiere sort du RPC sous `statTypes`, la seconde jamais."""
    return _table_ts("STAT_IDS_MAX_SEUL")


#: `{cle du hook: (membre natif, membre du mirror Python)}`. Les TROIS noms different, et la
#: table les ecrit tous les trois EXPRES : le hook nomme en camelCase, le natif en PascalCase, le
#: mirror en UPPER_SNAKE -- et l'appariement n'est PAS mecanique. Une derivation automatique
#: (`CriticalChance` -> `CRITICAL_CHANCE`) a ete essayee : elle rate `CRIT_CHANCE` / `CRIT_DAMAGE`
#: et accuse le mirror d'un trou qui n'existe pas. L'appariement est une CONVENTION du depot,
#: pas une donnee du build ; toute cle absente de cette table est SIGNALEE, jamais ignoree.
CLE_HOOK_VERS_STATTYPE = {
    "attack": ("Attack", "ATTACK"), "movement": ("Movement", "MOVEMENT"),
    "range": ("Range", "RANGE"), "defense": ("Defense", "DEFENSE"),
    "health": ("Health", "HEALTH"), "blockChance": ("BlockChance", "BLOCK_CHANCE"),
    "blockDamage": ("BlockDamage", "BLOCK_DAMAGE"),
    "critChance": ("CriticalChance", "CRIT_CHANCE"),
    "critDamage": ("CriticalDamage", "CRIT_DAMAGE"),
    "turnsStarted": ("TurnsStarted", "TURNS_STARTED"),
    "fixedArmor": ("FixedArmor", "FIXED_ARMOR"), "extraHits": ("ExtraHits", "EXTRA_HITS"),
    "activeAbilityLevel": ("ActiveAbilityLevel", "ACTIVE_ABILITY_LEVEL"),
    "numberOfMembers": ("NumberOfMembers", "NUMBER_OF_MEMBERS"),
    "extraPierceMelee": ("ExtraPierceMelee", "EXTRA_PIERCE_MELEE"),
    "extraPierceRanged": ("ExtraPierceRanged", "EXTRA_PIERCE_RANGED"),
    "extraHitsMelee": ("ExtraHitsMelee", "EXTRA_HITS_MELEE"),
    "extraRange": ("ExtraRange", "EXTRA_RANGE"),
    "extraMaxDamage": ("ExtraMaxDamage", "EXTRA_MAX_DAMAGE"),
    "extraPierce": ("ExtraPierce", "EXTRA_PIERCE"),
    # #477-r15-r7 -- vit dans `STAT_IDS_MAX_SEUL`, mais s'apparie par la MEME table : l'etape 1
    # confronte les DEUX tables du hook au meme enum, sans quoi la cle neuve serait comparee a
    # rien et le zero d'ecarts ne dirait rien d'elle.
    "armor": ("Armor", "ARMOR"),
}


def etape_1_stat_ids(build: str) -> list[str]:
    """Chaque cle de `COMBAT_STAT_IDS` == l'ordinal du build ET du mirror Python."""
    natif = enum_du_build(build, "IdunBattle.Entities.Enum.StatType")
    hook = table_du_hook()
    max_seul = table_max_seul_du_hook()
    if not hook or not natif or not max_seul:
        raise Panne("table vide (COMBAT_STAT_IDS=%d, STAT_IDS_MAX_SEUL=%d, build=%d) -- rien "
                    "n'a ete compare" % (len(hook), len(max_seul), len(natif)))
    ecarts, compares = [], 0
    # ⚠ LES DEUX TABLES SONT CONFRONTEES AU MEME ENUM. Les separer dans le hook est un choix de
    # PUBLICATION, pas de fidelite : un ordinal faux est aussi grave dans l'une que dans l'autre.
    doublons = sorted(set(hook) & set(max_seul))
    if doublons:
        ecarts.append("cle(s) presentes dans les DEUX tables du hook : %s -- `STAT_IDS_MAX_SEUL` "
                      "n'existe que pour ce qui NE doit PAS sortir sous `statTypes`" % doublons)
    for cle, ordinal in sorted({**hook, **max_seul}.items()):
        paire = CLE_HOOK_VERS_STATTYPE.get(cle)
        if paire is None:
            ecarts.append("cle `%s` du hook n'est appariee a AUCUN membre de StatType "
                          "(completer CLE_HOOK_VERS_STATTYPE)" % cle)
            continue
        membre, membre_py = paire
        if membre not in natif:
            ecarts.append("membre `StatType.%s` absent du build %s" % (membre, build))
            continue
        compares += 1
        if natif[membre] != ordinal:
            ecarts.append("hook `%s` = %d mais `StatType.%s` du build = %d"
                          % (cle, ordinal, membre, natif[membre]))
        # ... et le mirror Python, troisieme source INDEPENDANTE.
        py = getattr(StatType, membre_py, None)
        if py is None:
            ecarts.append("mirror Python `StatType` ne porte pas `%s`" % membre_py)
        elif int(py) != natif[membre]:
            ecarts.append("mirror Python `StatType.%s` = %d mais build = %d"
                          % (membre_py, int(py), natif[membre]))
    print("  [1] {COMBAT_STAT_IDS + STAT_IDS_MAX_SEUL} x StatType(build) x StatType(mirror) : "
          "%d cle(s) comparee(s), %d ecart(s)" % (compares, len(ecarts)))
    if compares == 0:
        raise Panne("TEMOIN VIDE : aucune cle comparee -- ce zero ne prouve rien")
    # Le coeur de #477-r15-r4 : la cle DOIT etre la, sinon le hook ne publie pas `range`.
    if "range" not in hook:
        ecarts.append("`range` ABSENT de COMBAT_STAT_IDS -- #477-r15-r4 rouvert : le probe "
                      "live repasserait `UnitStats_Range` en copie de l'oracle")
    # #477-r15-r7 : `armor` doit etre la, ET du BON cote. Les deux fautes sont silencieuses --
    # absente, le capteur disparait ; dans `COMBAT_STAT_IDS`, elle fait materialiser un
    # `StatComponent` de la mauvaise famille dans tout `UnitContext` reconstruit d'une capture.
    if "armor" not in max_seul:
        ecarts.append("`armor` ABSENT de STAT_IDS_MAX_SEUL -- #477-r15-r7 rouvert : le probe "
                      "live repasserait `UnitStats_MaxArmor` en copie de l'oracle")
    if "armor" in hook:
        ecarts.append("`armor` present dans COMBAT_STAT_IDS -- cette table est publiee sous "
                      "`statTypes` et `seed_unit_stats` l'itere pour seeder un `StatComponent` "
                      "par entree ; `StatType.Armor` est un `FillUpStatComponent`")
    return ecarts


def etape_2_statpart_maximum(build: str) -> list[str]:
    """`partBufMax` du hook == `StatPart.Maximum` du build et du mirror."""
    natif = enum_du_build(build, "IdunBattle.Entities.Enum.StatPart")
    src = HOOK.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"const partBufMax = Memory\.alloc\(4\); partBufMax\.writeS32\((\d+)\)", src)
    if not m:
        raise Panne("`partBufMax` introuvable dans le hook -- #477-r15-r5 ne peut pas etre garde")
    ecrit = int(m.group(1))
    ecarts = []
    if natif.get("Maximum") != ecrit:
        ecarts.append("hook `partBufMax` = %d mais `StatPart.Maximum` du build = %s"
                      % (ecrit, natif.get("Maximum")))
    if int(StatPart.MAXIMUM) != natif.get("Maximum"):
        ecarts.append("mirror Python `StatPart.MAXIMUM` = %d mais build = %s"
                      % (int(StatPart.MAXIMUM), natif.get("Maximum")))
    print("  [2] partBufMax=%d x StatPart.Maximum(build)=%s x mirror=%d : %d ecart(s)"
          % (ecrit, natif.get("Maximum"), int(StatPart.MAXIMUM), len(ecarts)))
    return ecarts


#: Les motifs que les trois capteurs DOIVENT laisser dans la source. Ce n'est pas un controle
#: de style : chacun est le seul point ou la grandeur cesse d'etre copiee de l'oracle. Le
#: fichier est nomme pour que la disparition d'un motif accuse le bon endroit.
MOTIFS_CAPTEUR = (
    (HOOK, r'getStatP\(e, "numberOfMembers", partBufMax\)',
     "r5 : le canal `StatPart.Maximum` des membres"),
    (HOOK, r"\bnumberOfMembersMax\b",
     "r5 : le champ publie au niveau unite"),
    (HOOK, r"state: readAbilityState\(inst\)",
     "r6 : l'etat castable lu sur L'INSTANCE de `Abilities@0x20`"),
    (HOOK, r"abilityStateLayout: abilityStateLayout\(\)",
     "r6 : la disposition publiee, pour que `non resolu` se dise"),
    (INTERNALS, r"export function readAbilityState",
     "r6 : la fonction dont le capteur depend"),
    (HOOK, r'getStatP\(e, "armor", partBufMax\)',
     "r7 : le canal `StatPart.Maximum` de l'ARMURE"),
    (HOOK, r"\barmorMax\b",
     "r7 : le champ publie au niveau unite"),
    (HOOK, r'getStatP\(e, "health", partBufMax\)',
     "r7 : le canal `StatPart.Maximum` de la SANTE (capteur #45b', que r7 fait enfin consommer)"),
)

#: Ce que le probe LIVE doit FAIRE -- le pendant positif des motifs interdits. Un motif interdit
#: seul ne prouve pas que la copie a ete REMPLACEE : il prouve qu'elle a disparu. Le port pourrait
#: avoir cesse de lire `hpMax` sans lire `healthMax` pour autant (une constante, un defaut). Ces
#: motifs-la exigent que le canal soit CONSOMME.
MOTIFS_REQUIS_LIVE = (
    (r'_champ_unite\(u_cs, "healthMax"', "r7 : `UnitStats_MaxHealth` lit bien `combatSnapshot`"),
    (r'_champ_unite\(u_cs, "armorMax"', "r7 : `UnitStats_MaxArmor` lit bien `combatSnapshot`"),
    (r'_champ_unite\(u_cs, "numberOfMembersMax"', "r5 : `UnitStats_MaxMembers` idem"),
)

#: Ce que le probe LIVE ne doit PLUS faire. Chaque motif est une COPIE de l'oracle qui a ete
#: retiree ; sa reapparition rouvrirait le residu sans qu'aucun test ne tombe.
#:
#: ⚠ LES MOTIFS DE BORNE VISENT LE LIBELLE, PAS LE NUMERO. Une premiere version cherchait
#: `#477-r15-r4)` : elle a rougi sur le COMMENTAIRE qui explique pourquoi la borne a retreci --
#: c'est-a-dire sur le texte meme qui prouve que le residu est ferme. Un motif de
#: non-regression doit designer l'ARTEFACT, jamais sa mention.
MOTIFS_INTERDITS_LIVE = (
    (r"range\s*=\s*0\b", "r4 : `UnitStats_Range` re-pose a 0 en dur"),
    (r'dv\.get\("usable", True\)', "r6 : defaut silencieux sur `CanStillBeUsed`"),
    (r'dv\.get\("disabled", False\)', "r6 : defaut silencieux sur `IsDisabled`"),
    (r'"Tag=UnitStats_Range -- ', "r4 : l'entree de borne (c) est revenue"),
    (r'"Tag=UnitStats_MaxMembers -- ', "r5 : l'entree de borne (c) est revenue"),
    (r'"Tag=UnitStats_ActiveAbility_\{CanStillBeUsed',
     "r6 : l'entree de borne (c) est revenue"),
    (r'max_health=int\(u_obs\[', "r7 : `UnitStats_MaxHealth` re-copie du champ brut d'observeBattle"),
    (r'max_armor=int\(u_obs\[', "r7 : `UnitStats_MaxArmor` re-copie du champ brut d'observeBattle"),
    (r'"Tag=UnitStats_\{MaxHealth,MaxArmor\} -- ', "r7 : l'entree de borne (c) est revenue"),
)


def etape_3_motifs() -> list[str]:
    ecarts, cherches = [], 0
    for fichier, motif, quoi in MOTIFS_CAPTEUR:
        src = fichier.read_text(encoding="utf-8", errors="replace")
        cherches += 1
        if not re.search(motif, src):
            ecarts.append("capteur MANQUANT dans %s -- %s" % (fichier.name, quoi))
    live = PROBE_LIVE.read_text(encoding="utf-8", errors="replace")
    for motif, quoi in MOTIFS_INTERDITS_LIVE:
        cherches += 1
        if re.search(motif, live):
            ecarts.append("COPIE REVENUE dans %s -- %s" % (PROBE_LIVE.name, quoi))
    for motif, quoi in MOTIFS_REQUIS_LIVE:
        cherches += 1
        if not re.search(motif, live):
            ecarts.append("CANAL NON CONSOMME dans %s -- %s" % (PROBE_LIVE.name, quoi))
    print("  [3] motifs de capteur, de consommation et de non-regression : %d cherche(s), "
          "%d ecart(s)" % (cherches, len(ecarts)))
    if cherches == 0:
        raise Panne("TEMOIN VIDE : aucun motif cherche")
    return ecarts


def etape_4_contre_epreuve() -> list[str]:
    """LE BRAS QUI PROUVE QUE L'ETAPE 3 MORD. Un balayage par motif rend vert des que le motif
    est trop laxiste ; on lui soumet donc un texte ou le capteur est ABSENT et on exige qu'il
    rougisse. Sans ce bras, `0 ecart` pourrait vouloir dire `la regex ne matche jamais rien`."""
    faux = "const rien = 1;\n"
    rate = [quoi for _, motif, quoi in MOTIFS_CAPTEUR if re.search(motif, faux)]
    #: Un TEMOIN qui porte TOUTES les copies -- l'etat exact du probe live AVANT ces tranches.
    #: Il doit toutes les attraper ; s'il en attrape moins, un motif est mort et l'etape 3
    #: rendrait un vert qui ne peut pas rougir.
    faux_live = ('range=0,\n'
                 'can_still_be_used=bool(dv.get("usable", True)),\n'
                 'is_disabled=bool(dv.get("disabled", False)),\n'
                 '        "Tag=UnitStats_Range -- `StatType.Range` (2) absent de ...",\n'
                 '        "Tag=UnitStats_MaxMembers -- pris de `stats.numberOfMembers` ...",\n'
                 '        "Tag=UnitStats_ActiveAbility_{CanStillBeUsed,...} de la ...",\n'
                 '        max_health=int(u_obs["hpMax"]), max_armor=int(u_obs["armorMax"]),\n'
                 '        "Tag=UnitStats_{MaxHealth,MaxArmor} -- lus au champ BRUT ...",\n')
    attrape = [quoi for motif, quoi in MOTIFS_INTERDITS_LIVE if re.search(motif, faux_live)]
    attendus = len(MOTIFS_INTERDITS_LIVE)
    ecarts = []
    if rate:
        ecarts.append("un motif de capteur matche un texte VIDE (trop laxiste) : %s" % rate)
    if len(attrape) < attendus:
        manques = [q for _, q in MOTIFS_INTERDITS_LIVE if q not in attrape]
        ecarts.append("les motifs interdits n'attrapent que %d/%d copies sur un temoin qui les "
                      "porte TOUTES -- l'etape 3 ne mordrait pas sur : %s"
                      % (len(attrape), attendus, manques))
    # ... et le PENDANT du bras positif : les motifs REQUIS doivent tomber sur ce meme temoin,
    # qui ne consomme AUCUN canal. Un motif requis trop laxiste (qui matcherait n'importe quoi)
    # rendrait l'etape 3 verte sur un port qui a cesse de lire.
    requis_laxistes = [quoi for motif, quoi in MOTIFS_REQUIS_LIVE if re.search(motif, faux_live)]
    if requis_laxistes:
        ecarts.append("motif(s) REQUIS satisfait(s) par un temoin qui ne consomme rien : %s"
                      % requis_laxistes)
    # ... et le TEMOIN INVERSE : le probe live REEL ne doit rien declencher (deja verifie par
    # l'etape 3), mais on s'assure ici qu'un motif ne matche pas n'importe quel texte.
    innocent = "rien de tout cela\n"
    faux_positifs = [q for motif, q in MOTIFS_INTERDITS_LIVE if re.search(motif, innocent)]
    if faux_positifs:
        ecarts.append("motif(s) interdit(s) matchant un texte INNOCENT : %s" % faux_positifs)
    print("  [4] contre-epreuve : motifs laxistes=%d, copies attrapees sur temoin=%d/%d, "
          "requis laxistes=%d, faux positifs=%d, %d ecart(s)"
          % (len(rate), len(attrape), attendus, len(requis_laxistes), len(faux_positifs),
             len(ecarts)))
    return ecarts


def etape_5_tags(build: str) -> list[str]:
    """Les trois `TagKey` en cause, contre l'enum du build -- le mirror ne se garde pas seul."""
    natif = enum_du_build(build, "IdunBattle.Streams.TagKey")
    ecarts, compares = [], 0
    for membre in ("UnitStats_Range", "UnitStats_MaxMembers", "UnitStats_InitAliveMembers",
                   "UnitStats_ActiveAbility_CanStillBeUsed",
                   "UnitStats_ActiveAbility_RemainingCooldownTurns",
                   "UnitStats_ActiveAbility_IsDisabled",
                   # #477-r15-r7 : les deux maximums ET les deux bruts qui leur font face. Les
                   # QUATRE ensemble, parce que c'est leur APPARIEMENT qui porte le sens -- le
                   # couple (9, 2) pour la sante, (13, 3) pour l'armure.
                   "UnitStats_MaxHealth", "UnitStats_MaxArmor",
                   "UnitStats_InitRemainingHealth", "UnitStats_InitRemainingArmor"):
        py = getattr(TagKey, membre, None)
        if py is None:
            ecarts.append("mirror `TagKey` ne porte pas `%s`" % membre)
            continue
        if membre not in natif:
            ecarts.append("`TagKey.%s` absent du build %s" % (membre, build))
            continue
        compares += 1
        if int(py) != natif[membre]:
            ecarts.append("`TagKey.%s` mirror=%d build=%d" % (membre, int(py), natif[membre]))
    print("  [5] TagKey des trois grandeurs : %d compare(s), %d ecart(s)"
          % (compares, len(ecarts)))
    if compares == 0:
        raise Panne("TEMOIN VIDE : aucun TagKey compare")
    return ecarts


def main() -> int:
    try:
        build = build_courant()
    except Panne as e:
        print("[477-r15-r4/r5/r6/r7 offline] PANNE : %s" % e)
        return 2
    print("[477-r15-r4/r5/r6/r7 offline] build = %s" % build)
    ecarts: list[str] = []
    try:
        for etape in (lambda: etape_1_stat_ids(build), lambda: etape_2_statpart_maximum(build),
                      etape_3_motifs, etape_4_contre_epreuve, lambda: etape_5_tags(build)):
            ecarts += etape()
    except Panne as e:
        print("  PANNE : %s" % e)
        return 2
    print("")
    if ecarts:
        print("=== ROUGE : %d ecart(s) ===" % len(ecarts))
        for e in ecarts:
            print("  - %s" % e)
        return 1
    print("=== VERT : les capteurs sont en place, CONSOMMES par le probe live, et leurs ordinaux "
          "concordent sur les TROIS sources (hook, table du build, mirror Python). ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
