"""#10022-r1 -- CLIQUET de l'offset `RandomizeAiInput` (100 % OFFLINE, aucune session Frida).

Ce que ce probe garde, et POURQUOI. `BattleConfiguration` porte NEUF booleens CONSECUTIFS a
partir de `+0xE0`. Le capteur `frida/hooks/features/battle-config.ts` en lisait un de trop court
(`+0xE7` = `DisableRandomness`) sous le nom `randomizeAiInput` -- et l'erreur etait INVISIBLE :
au seed, les deux valent `false`, donc lecture juste par accident. Un accord en regime degenere.
En ECRITURE, elle etait pire que muette : `bcPatch({randomizeAi:true})` figeait le seed de la
bataille (`idun.IdunMainView$$ShowBattle` gate `DateTime.Now.Ticks` sur `+0xE7`) au lieu de
randomiser l'ordre d'activation IA.

Quatre etages, et le 4e est celui qui empeche la faute de revenir :

  1. l'offset ECRIT dans `battle-config.ts` vaut `0xE8`, et surtout **PAS `0xE7`** -- la valeur
     fautive est nommee EXPLICITEMENT, pas seulement la bonne exigee. Une garde qui dirait
     seulement « == 0xE8 » ne dirait pas au lecteur POURQUOI elle existe ;
  2. la table des neuf booleens est presente et COMPLETE dans le commentaire de tete du meme
     fichier, dans l'ordre. Sans elle, l'octet voisin reste a portee de faute ;
  3. `data/seed-bc.json` porte `RandomizeAiInput == false`. C'est ce qui etablit que l'etage
     `UnitPicker` MORD sur le regime confrontable (`AiControl.<+0x70> == 0` =>
     `IdunBattle.Core.Services.AiControl$$GetAi` rend `DefaultPlayerStrategy`). Si le seed change,
     le verdict doit etre RE-EXAMINE, pas herite ;
  4. **l'ORDRE des neuf cles booleennes dans le seed BC**, qui est la serialisation Newtonsoft de
     l'ordre de DECLARATION, donc l'image de l'ordre des offsets. C'est le seul etage qui voit un
     booleen INSERE cote jeu -- lequel decalerait `RandomizeAiInput` d'un octet sans qu'aucun des
     trois autres ne bronche. Ancre du haut : `+0xE0 UseGroupForAddUnit`, fixe par
     `IdunBattle.Core.Services.BattleQuery$$get_UseGroupForAddUnit` ; ancre du bas :
     `+0xE8 RandomizeAiInput`, fixe par le parametre `configurationRandomizeAiInput` de
     `IdunBattle.Core.Services.AiControl$$Init`.

Un 5e etage garde la FRAICHEUR des deux ancres nommees dans le build courant.

    python scripts/python/probe_10022r1_randomize_ai_input.py

rc 0 = tout concorde ; rc 1 = au moins une divergence ; rc 2 = PAS MESURE (entrees manquantes --
jamais rabattu sur un vert, cf. la regle tri-etat du depot).
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

_ICI = os.path.dirname(os.path.abspath(__file__))
_RACINE = os.path.dirname(os.path.dirname(_ICI))
_SYMBOLES = os.path.join(_RACINE, "data", "symbols")

_CAPTEUR = os.path.join(_RACINE, "frida", "hooks", "features", "battle-config.ts")
_SEED_BC = os.path.join(_RACINE, "data", "seed-bc.json")
_HOOKS = os.path.join(_RACINE, "frida", "hooks")


# --------------------------------------------------------------------------------------------- #
#  Ce que le decompile porte -- recopie du site, pas deduit du nom
# --------------------------------------------------------------------------------------------- #

# Les NEUF booleens de `BattleConfiguration`, consecutifs depuis +0xE0, DANS L'ORDRE.
# Cet ordre est celui de la declaration C#, donc celui de la serialisation Newtonsoft.
BOOLEENS = (
    (0xE0, "UseGroupForAddUnit"),
    (0xE1, "NoAutomaticUnitTurns"),
    (0xE2, "EnableIdunAbilities"),
    (0xE3, "IsTestBattle"),
    (0xE4, "DisableTimeouts"),
    (0xE5, "DisableAnimatorRecovery"),
    (0xE6, "DisableActiveAbilitiesOnAI"),
    (0xE7, "DisableRandomness"),
    (0xE8, "RandomizeAiInput"),
)

OFFSET_ATTENDU = 0xE8
OFFSET_FAUTIF = 0xE7          # la valeur qui vivait dans le capteur avant #10022-r1

# Les deux getters natifs qui ANCRENT le haut de la table. Ils ne se deduisent de rien :
# ils lisent `this.<+0xa0>` (la BattleConfiguration) a `+0xe0` / `+0xe1`.
ANCRES_NOMMEES = (
    "IdunBattle.Core.Services.BattleQuery$$get_UseGroupForAddUnit",
    "IdunBattle.Core.Services.BattleQuery$$get_NoAutomaticUnitTurns",
)

# Le SEUL ecrivain legitime de la cle dans le depot -- un wrapper de vague RL qui la force a
# `True` EXPLICITEMENT (il le dit dans son entete). Il vit hors de `frida/hooks/**`.
ECRIVAIN_LEGITIME = os.path.join("scripts", "python", "_wave_build.py")


def _build_courant():
    chemin = os.path.join(_SYMBOLES, "CURRENT")
    if not os.path.isfile(chemin):
        return None
    val = io.open(chemin, encoding="utf-8").read().strip()
    return val or None


def _fonctions_du_build(build):
    chemin = os.path.join(_SYMBOLES, build, "ghidra", "functions.tsv")
    noms = set()
    if not os.path.isfile(chemin):
        return noms
    for ligne in io.open(chemin, encoding="utf-8", errors="replace"):
        champs = ligne.rstrip("\n").split("\t")
        if len(champs) >= 2:
            noms.add(champs[1])
    return noms


def main():
    rouges = []
    print("[10022-r1] cliquet offset RandomizeAiInput")

    # --- entrees ------------------------------------------------------------------------------ #
    if not os.path.isfile(_CAPTEUR):
        print("[10022-r1] NON MESURE : %s absent -- rc 2 (jamais un vert)"
              % os.path.relpath(_CAPTEUR, _RACINE))
        return 2
    if not os.path.isfile(_SEED_BC):
        print("[10022-r1] NON MESURE : data/seed-bc.json absent -- rc 2")
        return 2
    source = io.open(_CAPTEUR, encoding="utf-8", errors="replace").read()

    # --- etage 1 : l'offset ECRIT, et l'interdit explicite sur le fautif ----------------------- #
    m = re.search(r"const\s+BC_OFF_RANDOMIZE_AI\s*=\s*(0[xX][0-9a-fA-F]+|\d+)\s*;", source)
    if m is None:
        rouges.append("etage 1 : `BC_OFF_RANDOMIZE_AI` INTROUVABLE dans battle-config.ts "
                      "(renomme ? le capteur n'est plus garde)")
    else:
        val = int(m.group(1), 0)
        if val == OFFSET_FAUTIF:
            rouges.append(
                "etage 1 : BC_OFF_RANDOMIZE_AI = 0x%X -- c'est `DisableRandomness`, PAS "
                "`RandomizeAiInput` (#10022-r1). En lecture le champ ment en silence (les deux "
                "valent false au seed) ; en ECRITURE il fige le seed de la bataille au lieu de "
                "randomiser l'ordre IA. Attendu 0x%X." % (val, OFFSET_ATTENDU))
        elif val != OFFSET_ATTENDU:
            rouges.append("etage 1 : BC_OFF_RANDOMIZE_AI = 0x%X, attendu 0x%X"
                          % (val, OFFSET_ATTENDU))
        else:
            print("[10022-r1] etage 1 OK : BC_OFF_RANDOMIZE_AI = 0x%X" % val)

    # --- etage 2 : la table des neuf booleens vit dans le commentaire de tete ------------------ #
    absents = []
    for off, nom in BOOLEENS:
        if not re.search(r"\+0x%X\s+%s\b" % (off, re.escape(nom)), source, re.IGNORECASE):
            absents.append("+0x%X %s" % (off, nom))
    if absents:
        rouges.append("etage 2 : table des booleens incomplete dans battle-config.ts, manquent : %s"
                      % ", ".join(absents))
    else:
        print("[10022-r1] etage 2 OK : les %d booleens sont documentes avec leur offset"
              % len(BOOLEENS))

    # --- etage 3 : le seed BC porte false ------------------------------------------------------ #
    try:
        bc = json.load(io.open(_SEED_BC, encoding="utf-8"))
    except Exception as exc:                                     # noqa: BLE001
        print("[10022-r1] NON MESURE : seed-bc.json illisible (%s) -- rc 2" % exc)
        return 2
    if "RandomizeAiInput" not in bc:
        rouges.append("etage 3 : la cle `RandomizeAiInput` a DISPARU du seed BC -- le verdict "
                      "« l'etage UnitPicker est actif » n'a plus de substrat, re-mesurer")
    elif bc["RandomizeAiInput"] is not False:
        rouges.append(
            "etage 3 : seed-bc.json porte RandomizeAiInput = %r. Le verdict #10022-r1 "
            "(`AiControl.<+0x70> == 0` => DefaultPlayerStrategy => les 8 buckets) est ETABLI SUR "
            "`false` : avec `true` c'est `RandomGroupOperation` (tirage uniforme) qui decide et "
            "tout le chantier #10022-r2..r5 est inerte. RE-EXAMINER, ne pas heriter."
            % (bc["RandomizeAiInput"],))
    else:
        print("[10022-r1] etage 3 OK : seed-bc.json RandomizeAiInput = false "
              "(=> l'etage UnitPicker MORD sur le regime confrontable)")

    # --- etage 4 : l'ORDRE des neuf cles dans le seed BC ---------------------------------------- #
    # C'est l'image de l'ordre de declaration, donc de l'ordre des offsets. Le SEUL etage qui
    # voit un booleen INSERE cote jeu.
    attendus = [nom for _off, nom in BOOLEENS]
    presentes = [c for c in bc.keys() if c in set(attendus)]
    if len(presentes) != len(attendus):
        rouges.append("etage 4 : le seed BC ne porte que %d des %d booleens (%s) -- l'ordre ne "
                      "peut plus servir d'image des offsets"
                      % (len(presentes), len(attendus),
                         ", ".join(sorted(set(attendus) - set(presentes))) or "?"))
    elif presentes != attendus:
        rouges.append("etage 4 : ORDRE des booleens du seed BC = %s, attendu %s. L'ordre de "
                      "serialisation Newtonsoft est celui de la DECLARATION, donc celui des "
                      "offsets : un ecart ici decale `RandomizeAiInput`. RE-DERIVER la table."
                      % (presentes, attendus))
    else:
        # Contre-controle du controle : sans lui, un seed BC qui aurait perdu les neuf cles
        # rendrait deux listes VIDES donc EGALES, et l'etage passerait pour vert.
        assert presentes, "etage 4 vacant : aucune cle booleenne lue"
        print("[10022-r1] etage 4 OK : les %d cles sont dans l'ordre de declaration "
              "(%s ... %s)" % (len(presentes), presentes[0], presentes[-1]))

    # --- etage 5 : les deux ancres nommees existent dans le build courant ----------------------- #
    build = _build_courant()
    if build is None:
        rouges.append("etage 5 : NON MESURE -- data/symbols/CURRENT absent")
    else:
        fonctions = _fonctions_du_build(build)
        if not fonctions:
            rouges.append("etage 5 : NON MESURE -- ghidra/functions.tsv du build %s absente"
                          % build)
        else:
            perdues = [a for a in ANCRES_NOMMEES if a not in fonctions]
            if perdues:
                rouges.append("etage 5 : ancre(s) NOMMEE(S) disparue(s) du build %s : %s -- la "
                              "table des offsets n'est plus ancree, la RE-DERIVER"
                              % (build, ", ".join(perdues)))
            else:
                print("[10022-r1] etage 5 OK : les %d ancres nommees vivent dans le build %s"
                      % (len(ANCRES_NOMMEES), build))

    # --- etage 6 : personne d'autre n'ecrit la cle sous frida/hooks ----------------------------- #
    ecrivains = []
    for base, _dirs, fichiers in os.walk(_HOOKS):
        for f in fichiers:
            if not f.endswith((".ts", ".js")):
                continue
            chemin = os.path.join(base, f)
            txt = io.open(chemin, encoding="utf-8", errors="replace").read()
            if re.search(r"[\"']RandomizeAiInput[\"']\s*\]?\s*=", txt):
                ecrivains.append(os.path.relpath(chemin, _RACINE))
    if ecrivains:
        rouges.append("etage 6 : %s ecrit la cle `RandomizeAiInput` dans frida/hooks -- le "
                      "pipeline du runner ne doit PAS la reecrire (seul %s le fait, et il le dit)"
                      % (", ".join(ecrivains), ECRIVAIN_LEGITIME))
    else:
        print("[10022-r1] etage 6 OK : aucun ecrivain de la cle sous frida/hooks")

    print("")
    if rouges:
        for r in rouges:
            print("[10022-r1] ROUGE : %s" % r)
        return 1
    print("[10022-r1] VERT : %d etages" % 6)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
