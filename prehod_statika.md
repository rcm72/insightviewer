### 1. **Razlogi za prehod na statično obliko**
- **Ločitev odgovornosti**: Statične datoteke (HTML, CSS, JS) skrbijo za prikaz uporabniškega vmesnika, medtem ko backend zagotavlja API-je za obdelavo podatkov.
- **Preprosto vzdrževanje**: Spremembe v frontendu ne vplivajo na backend in obratno.
- **Prilagodljivost**: Backend lahko enostavno zamenjaš (npr. prehod na FastAPI), ne da bi spremenil frontend.
- **Izboljšana zmogljivost**: Statične datoteke se lahko predpomnijo v brskalniku, kar zmanjša obremenitev strežnika.

---

### 2. **Nova struktura projekta**
Organiziraj projekt tako, da ločiš statične datoteke od API-jev:

```
project/
├── app.py                # Glavna Flask aplikacija
├── static/               # Mapa za statične datoteke
│   ├── js/
│   │   ├── app.js        # JavaScript za frontend
│   ├── css/
│   │   ├── styles.css    # CSS za frontend
│   ├── zgo_grki.html     # Statični HTML
├── templates/            # (opcijsko, če uporabljaš Jinja2)
└── requirements.txt      # Odvisnosti
```

---

### 3. **Priprava statičnih datotek**

#### a) **HTML (`static/zgo_grki.html`)**
Ustvari statično HTML datoteko, ki bo prikazovala vsebino in omogočala interakcijo z API-ji prek JavaScript-a:

```html
<!DOCTYPE html>
<html lang="sl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Zgodovina Grki</title>
    <link rel="stylesheet" href="/static/css/styles.css">
    <script src="/static/js/app.js" defer></script>
</head>
<body>
    <div class="container">
        <h1>Zgodovina Grki</h1>
        <p>Troja je bila pomembno kulturno središče grške bronaste dobe.</p>
        <button id="ask-question-btn">Ask a Question</button>
        <div id="response"></div>
    </div>
</body>
</html>
```

---

#### b) **CSS (`static/css/styles.css`)**
Dodaj preprosto oblikovanje za boljšo predstavitev:

```css
body {
    font-family: Arial, sans-serif;
    line-height: 1.6;
    margin: 20px;
}

.container {
    max-width: 800px;
    margin: 0 auto;
}

button {
    background-color: #007BFF;
    color: white;
    border: none;
    padding: 10px 20px;
    cursor: pointer;
    border-radius: 5px;
}

button:hover {
    background-color: #0056b3;
}

#response {
    margin-top: 20px;
    padding: 10px;
    border: 1px solid #ccc;
    background-color: #f9f9f9;
}
```

---

#### c) **JavaScript (`static/js/app.js`)**
Implementiraj logiko za pošiljanje zahtev na API-je:

```javascript
document.addEventListener("DOMContentLoaded", () => {
    const askQuestionBtn = document.getElementById("ask-question-btn");
    const responseDiv = document.getElementById("response");

    askQuestionBtn.addEventListener("click", async () => {
        const context = "Troja je bila pomembno kulturno središče grške bronaste dobe.";
        const question = prompt("Vnesite vprašanje:");

        if (!question) {
            alert("Vprašanje je obvezno!");
            return;
        }

        try {
            // Pošlji zahtevo na /ask-question
            const res = await fetch("/ask-question", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ question, context }),
            });

            const data = await res.json();
            if (data.success) {
                responseDiv.innerHTML = `<p>Odgovor: ${data.answer}</p>`;
            } else {
                responseDiv.innerHTML = `<p>Napaka: ${data.error}</p>`;
            }
        } catch (error) {
            console.error("Napaka pri pošiljanju zahteve:", error);
            responseDiv.innerHTML = `<p>Napaka pri pošiljanju zahteve.</p>`;
        }
    });
});
```

---

### 4. **Prilagoditev Flask aplikacije**

#### a) **API za `/ask-question`**
V app.py ohrani API za obdelavo vprašanj:

```python
from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route('/ask-question', methods=['POST'])
def ask_question():
    """
    Sprejme vprašanje in kontekst ter vrne odgovor.
    """
    data = request.json
    question = data.get("question", "").strip()
    context = data.get("context", "").strip()

    if not question or not context:
        return jsonify({"success": False, "error": "Manjka 'question' ali 'context'"}), 400

    # Simulacija odgovora (tu bi bil klic OpenAI API)
    answer = f"Odgovor na vprašanje '{question}' v kontekstu '{context}'."
    return jsonify({"success": True, "answer": answer})
```

#### b) **Strežba statičnih datotek**
Dodaj pot za strežbo statičnih datotek:

```python
@app.route('/zgo-grki', methods=['GET'])
def serve_static_html():
    return app.send_static_file('zgo_grki.html')
```

---

### 5. **Zagon aplikacije**
Zaženi aplikacijo z naslednjim ukazom:
```bash
python app.py
```

Aplikacija bo na voljo na naslovu:
```
http://localhost:5000/zgo-grki
```

---

### 6. **Prednosti nove strukture**
- **Ločitev frontend-a in backend-a**: Statične datoteke so ločene od API-jev.
- **Preprosto vzdrževanje**: Spremembe v frontendu ne vplivajo na backend.
- **Prilagodljivost**: Backend lahko enostavno zamenjaš (npr. prehod na FastAPI).

---

### 7. **Razširitev**
- Dodaj nove API-je za obdelavo podatkov.
- Razširi JavaScript za bolj interaktivno uporabniško izkušnjo.
- Uporabi knjižnice, kot so **vis.js** ali **D3.js**, za vizualizacijo podatkov.

S tem pristopom bo tvoja aplikacija bolj modularna, prilagodljiva in enostavna za vzdrževanje.
