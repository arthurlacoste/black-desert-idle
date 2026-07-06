# Notes de version

## 217 — Mobile responsive HUD

Date : 2026-07-06

### Mobile portrait

- Le cadre de jeu utilise maintenant 70% du viewport en portrait mobile.
- Le mode landscape garde le comportement desktop.
- Le canvas mobile adapte sa résolution interne pour éviter toute déformation du rendu.
- La caméra mobile est zoomée pour garder le héros lisible.

### Interface mobile

- Correction des overlaps entre HP/MP, potions, barre de cast, loot ticker, silver et bouton de mode farm.
- `#potStack` est aligné à droite en portrait mobile.
- `#farmModeBtn` est ancré à droite avec `right:8px` en portrait mobile.
- Le bouton skill/loot reste dans le viewport.

### Équipement

- Le paperdoll équipement passe en layout vertical sur mobile.
- Les slots d'équipement restent centrés et dans le viewport.

### Technique

- Ajout de `mobile.css` pour sortir les correctifs responsive du HTML.
- Ajout de `mobile-canvas.js` pour gérer le ratio et le zoom du canvas mobile.
