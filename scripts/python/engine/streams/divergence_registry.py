"""Le REGISTRE des divergences CONNUES entre le flux natif et le flux emis par le port.

POURQUOI CE FICHIER EXISTE. Un comparateur de flux entier serait rouge presque partout : le
port ne couvre pas toutes les mecaniques du jeu, donc son flux est structurellement plus pauvre.
Un pass/fail serait donc inutilisable des le premier jour. `case-477r15` § 6 tranche : TROIS
etats, et un seul rougit.

    conforme          les deux flux sont egaux sur le perimetre compare
    divergent CONNU   la divergence est INSCRITE ici, avec sa cause NOMMEE
    divergent NOUVEAU le seul etat qui rougit

LA CLE. Une divergence se nomme par sa FORME et par le symbole qui la porte :

    "MANQUANT Action=ChangeStats"   le natif ecrit cette ligne, le port ne l'ecrit pas
    "EN_TROP  Action=X"             le port ecrit une ligne que le natif n'ecrit pas
    "VALEUR   Tag=X"                meme symbole, meme position, valeur differente

Le symbole est TOUJOURS un membre de `GroupType` / `StepType` / `TagKey` (ou `Finish_Group`),
jamais un extrait de texte : c'est ce qui rend le registre re-derivable au changement de build.

LES DEUX EXIGENCES, chacune tiree d'une faute deja mesuree dans ce depot :

1. LE REGISTRE SE PURGE TOUT SEUL. Une entree qui cesse d'etre exercee rougit comme PERIMEE.
   Sans cela le registre ne fait que grossir et finit par tout couvrir -- c'est la lecon de
   `probe_181`, qui a rendu `0` inconditionnellement pendant des semaines : un inventaire
   deguise en garde-fou. La reponse a une entree perimee est de la SUPPRIMER, jamais de
   l'elargir.
   ⚠ La purge s'evalue sur le CORPUS COMPLET d'une passe (l'union des cles exercees par tous
   les scenarios joues), jamais sur un scenario isole -- sinon jouer un seul board rendrait
   perimees toutes les entrees des autres.

2. CE QUI N'EST PAS COMPARE EST PUBLIE. Une entree d'ici dit ce qu'on SAIT diverger ; elle ne
   dit rien de ce qu'on ne regarde pas. Les bornes du comparateur (membres d'enum non exerces,
   omissions structurelles du flux, entrees prises du natif) sont IMPRIMEES par
   `conformance.rapport`. NON COMPARE != EGAL.
"""
from __future__ import annotations

#: `cle -> cause NOMMEE`. Une cause doit dire POURQUOI, pas re-decrire la cle.
KNOWN_DIVERGENCES: dict[str, str] = {
    # --- Tranche D : les tags d'ETAT COMPLET d'une unite.
    # Le producteur est NOMME, et ce n'est PAS celui qu'annoncait `case-477r15` : les trois
    # surcharges de `IdunBattle.Entities.UnitExtensions$$GetFullStateUpdateTags`, et non un
    # `IdunBattle.Core.Services.StreamHelper$$Get*Tags`. Le portage est donc possible ; ce qui
    # manque au port, ce sont les ENTREES (stats resolues, etats d'ability), pas la RE.
    "MANQUANT Action=ChangeStats":
        "les 16 tags de stats initiales viennent de "
        "`IdunBattle.Entities.UnitExtensions$$GetFullStateUpdateTags(unit)` (garde d'entree : "
        "`EntityType.Unit`, sinon dictionnaire VIDE). Non porte -- tranche D. Le port ne les "
        "invente pas.",
    "MANQUANT Action=ChangeAbility":
        "une ligne par ability montee, ACTIVES d'abord puis DECLENCHEES : surcharges "
        "`GetFullStateUpdateTags(activeAbility)` (6 tags, +2 conditionnels si l'ability a un "
        "cout en munitions) et `GetFullStateUpdateTags(component, triggeredAbility)` (3 tags). "
        "Non porte -- tranche D.",
}
