document.addEventListener('DOMContentLoaded', async () => {
  const el = id => document.getElementById(id);

  // Elements
  const questionEl = el('question');
  const btnAsk = el('btnAsk');
  const responseArea = el('responseArea');
  const responseText = el('responseText');
  const modelInfo = el('modelInfo'); // Add an element in HTML to display the model

  // API base - Ollama API endpoint
  const API_BASE = 'http://192.168.1.16:5001/proxy/ollama'; // Adjust to your Ollama API

  // Fetch model info from the server
  try {
    const res = await fetch('/api/ollama/model'); // Create an endpoint to return the model
    if (res.ok) {
      const data = await res.json();
      modelInfo.textContent = `Uporabljen model: ${data.model}`;
    } else {
      modelInfo.textContent = 'Napaka pri pridobivanju modela.';
    }
  } catch (err) {
    console.error('Error fetching model info:', err);
    modelInfo.textContent = 'Napaka pri pridobivanju modela.';
  }

  // Ask question
  btnAsk.addEventListener('click', async () => {
    const question = questionEl.value.trim();
    if (!question) {
      alert('Vnesi vprašanje.');
      return;
    }

    // Disable button during request
    btnAsk.disabled = true;

    try {
      const payload = { question };
      const res = await fetch(`${API_BASE}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errorDetails = await res.text();
        console.error(`Error response: ${errorDetails}`);
        throw new Error(`Napaka: HTTP ${res.status}`);
      }
      const data = await res.json();

      // Show response
      responseText.innerHTML = data.answer || 'Ni odgovora.';
      responseArea.classList.remove('hidden');
    } catch (err) {
      console.error('Error fetching response:', err);
      console.error('Full error details:', err);
      alert('Napaka pri pridobivanju odgovora: ' + err.message);
    } finally {
      btnAsk.disabled = false;
    }
  });
});
