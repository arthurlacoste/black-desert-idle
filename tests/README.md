# tests/

Suite de tests de régression.

- `tests.js` : `assert()` + des centaines de tests couvrant équilibrage, formules de stat,
  migrations rétroactives, UI, patch notes. Charge en tout dernier, car il a besoin de tout le reste.
- `regression.spec.js` : wrapper Playwright. Ouvre `index.dev.html`, attend `window.runRegressionTests()`, puis échoue si la suite retourne une erreur ou si la page lève une exception.

Commandes :

```bash
npm test
npm run test:headed
npm run test:ui
```

Préparation locale :

```bash
npm install
npx playwright install chromium
```

Convention : après toute extraction de code entre fichiers, relancer la suite complète et vérifier au moins un comportement réel en direct, pas seulement l'absence d'erreur au chargement. Voir `CLAUDE.md` à la racine.
