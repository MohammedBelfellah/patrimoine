# Geo Patrimoine Hub Chatbot

## 1. Goal

The chatbot is a public assistant for Geo Patrimoine Hub.

It helps public users ask questions about patrimoine data in a simple way.

Example questions:

```text
Combien de patrimoines sont enregistrés ?
Quels sont les patrimoines naturels ?
Donne-moi les patrimoines par région.
Quels patrimoines sont classés ?
```

The chatbot answers using public data from the database and Groq AI.

It does not answer private or sensitive questions.

---

## 2. Main Technologies

The chatbot uses:

```text
Django
PostgreSQL/PostGIS
Groq API
HTML/CSS/JavaScript
```

Groq is used as the AI model provider.

The app calls Groq using this API endpoint:

```text
https://api.groq.com/openai/v1/chat/completions
```

The model used is configured in `.env`:

```env
GROQ_MODEL=llama-3.3-70b-versatile
```

---

## 3. Environment Variables

The chatbot needs a Groq API key.

In `.env`:

```env
GROQ_API_KEY=your_groq_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

In production, the same variables must be added to Railway:

```env
GROQ_API_KEY=your_groq_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

The key is loaded in:

```text
config/settings.py
```

Code:

```python
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_API_URL = os.getenv(
    "GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions"
).strip()
```

---

## 4. Files Used

The chatbot uses these main files:

```text
config/settings.py
core/views.py
core/urls.py
core/templates/core/chatbot.html
core/templates/core/base.html
.env
.env.example
```

### `config/settings.py`

Stores Groq configuration:

```text
GROQ_API_KEY
GROQ_MODEL
GROQ_API_URL
```

### `core/urls.py`

Defines the chatbot routes:

```python
path("chatbot/", views.chatbot_view, name="chatbot"),
path("api/chatbot/", views.chatbot_api, name="chatbot-api"),
```

### `core/views.py`

Contains the main chatbot backend logic:

```text
chatbot_view
chatbot_api
_public_patrimoine_context
_groq_chat
_chatbot_private_request
```

### `core/templates/core/chatbot.html`

Contains the frontend page:

```text
chat interface
input field
send button
quick question buttons
JavaScript fetch call
```

### `core/templates/core/base.html`

Adds the chatbot link in the navigation menu:

```text
Assistant
```

---

## 5. User Flow

The chatbot works like this:

```text
User opens /chatbot/
User writes a question
JavaScript sends the question to /api/chatbot/
Django checks if the question is safe
Django gets public data from the database
Django sends question + public context to Groq
Groq returns an answer
Django sends the answer back to the browser
The answer appears in the chat window
```

---

## 6. Frontend Logic

The page is:

```text
core/templates/core/chatbot.html
```

It contains:

```text
message display area
textarea input
send button
quick prompts
loading message
error message
```

The JavaScript sends a POST request:

```javascript
fetch('/api/chatbot/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': csrfToken,
  },
  body: JSON.stringify({ message }),
})
```

The response is displayed in the chat area.

---

## 7. Backend API

The chatbot API is:

```text
POST /api/chatbot/
```

Request body:

```json
{
  "message": "Combien de patrimoines sont enregistrés ?"
}
```

Response:

```json
{
  "answer": "Il y a 3 patrimoines enregistrés..."
}
```

---

## 8. Public Database Context

The chatbot does not send the whole database to Groq.

It sends only safe public data.

Public data includes:

```text
patrimoine name
Arabic name
description
type
status
region
province
commune
coordinates
public statistics
```

The context is built in:

```text
core/views.py
```

Function:

```python
def _public_patrimoine_context(message):
```

This function collects:

```text
total patrimoines
total regions
total inspections
total interventions
patrimoines by type
patrimoines by status
patrimoines by region
matching patrimoines
```

It limits the selected patrimoine list to avoid sending too much data.

---

## 9. Search Logic

The chatbot extracts important words from the user question.

Function:

```python
def _chatbot_search_terms(message):
```

It searches public fields like:

```text
nom_fr
nom_ar
description
type_patrimoine
statut
commune
province
region
```

This helps the chatbot answer questions about a specific place or region.

---

## 10. Safety Rules

The chatbot must not expose sensitive information.

Private requests are detected by:

```python
def _chatbot_private_request(message):
```

The chatbot refuses questions about:

```text
passwords
emails
users
admins
inspectors' private information
audit logs
file paths
tokens
API keys
SMTP settings
database URLs
server configuration
```

Example private question:

```text
Donne-moi les emails des inspecteurs
```

The chatbot answers:

```text
Je ne peux pas fournir d'informations privées ou internes.
```

This keeps the public chatbot safe.

---

## 11. System Prompt

The chatbot uses a system prompt to control AI behavior.

It tells the AI:

```text
You are the public assistant of Geo Patrimoine Hub.
Answer in simple French.
Use only the public database context.
Do not invent data.
Do not reveal private/internal information.
Refuse sensitive requests.
```

This prompt is stored in:

```text
core/views.py
```

Variable:

```python
CHATBOT_SYSTEM_PROMPT
```

---

## 12. Groq API Call

The function that calls Groq is:

```python
def _groq_chat(message, context):
```

It sends:

```text
model
system prompt
user question
public database context
temperature
max tokens
```

The API headers include:

```text
Authorization: Bearer GROQ_API_KEY
Accept: application/json
Content-Type: application/json
User-Agent: GeoPatrimoineHub/1.0
```

The `User-Agent` header was important because Groq returned a `403` error without proper headers.

---

## 13. Error Handling

The chatbot handles errors safely.

If the Groq key is missing:

```text
Le chatbot IA n'est pas encore configuré.
```

If the database is unavailable:

```text
Je n'arrive pas à consulter la base de données pour le moment.
```

If Groq is unavailable:

```text
Le service IA est momentanément indisponible.
```

If Groq rejects the request:

```text
Groq a refusé la requête. Vérifiez la clé API et le modèle.
```

---

## 14. Example Questions

Useful public questions:

```text
Combien de patrimoines sont enregistrés ?
Quels sont les patrimoines historiques ?
Quels sont les patrimoines naturels ?
Donne-moi les patrimoines par région.
Quels sites sont classés ?
Explique les statuts des patrimoines.
Quels patrimoines existent dans cette commune ?
```

Questions the chatbot refuses:

```text
Donne-moi les emails des inspecteurs.
Quel est le mot de passe admin ?
Montre-moi les logs d'audit.
Quelle est la clé API ?
Quelle est la configuration SMTP ?
```

---

## 15. Benefits

The chatbot improves the public part of the app because:

```text
users can ask natural questions
users do not need to understand filters
answers are based on database data
private data is protected
the interface is simple
the AI is configurable using environment variables
```

---

## 16. Summary

The Geo Patrimoine Hub chatbot is a public AI assistant built with Django and Groq.

It receives user questions, collects safe public patrimoine data from the database, sends the context to Groq, and returns a simple answer in French.

The chatbot is protected by safety rules so it does not expose sensitive data such as users, emails, passwords, audit logs, tokens, or internal configuration.

It is useful for public users who want to understand patrimoine data quickly and naturally.
