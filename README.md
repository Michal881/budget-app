# Budget App 💸

Prosta aplikacja do zarządzania budżetem.

## Funkcje
- dodawanie wydatków
- usuwanie wydatków
- planowanie budżetu
- podsumowanie plan vs wykonanie

## Tech stack
- Backend: FastAPI (Python)
- Frontend: HTML + JavaScript
- Deployment: Render

## Demo
Frontend:
https://budget-app-1-ryba.onrender.com

Backend:
https://budget-app-olyq.onrender.com

## Konfiguracja API (lokalnie i produkcyjnie)
Frontend czyta adres backendu z `config.js` (`window.BUDGET_APP_CONFIG.apiBaseUrl`).

Domyślne zachowanie:
- jeśli frontend działa na `localhost` lub `127.0.0.1`, używa `http://127.0.0.1:8000`
- w innych przypadkach używa tego samego hosta co frontend

Dla produkcji (osobny URL backendu):
1. Otwórz `config.js`
2. Ustaw `apiBaseUrl`, np. `https://twoj-backend.onrender.com`
3. Zdeployuj frontend

Dzięki temu nie musisz trzymać adresu produkcyjnego backendu na stałe w `index.html`.
