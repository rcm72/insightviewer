// ...existing code...
document.addEventListener("DOMContentLoaded", function() {
  const qEl = document.getElementById("question");
  const btn = document.getElementById("ask");
  const results = document.getElementById("results");
  const status = document.getElementById("status");
  const topK = document.getElementById("top_k");
  async function doSearch() {
    const question = qEl.value.trim();
    if (!question) {
      status.textContent = "Enter a question first.";
      return;
    }
    status.textContent = "Computing embedding and searching...";
    results.innerHTML = "";
    try {
      const resp = await fetch("/api/quiz/search", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({question, top_k: parseInt(topK.value || "6", 10)})
      });
      const j = await resp.json();
      if (!j.success) {
        status.textContent = "Error: " + (j.error || JSON.stringify(j));
        return;
      }
      status.textContent = `Found ${j.rows.length} matches`;
      j.rows.forEach((r, idx) => {
        const el = document.createElement("div");
        el.className = "result";
        el.innerHTML = `<div><strong>#${idx+1}</strong> <span class="score">score: ${Number(r.score).toFixed(4)}</span></div>
                        <div class="chunk">${escapeHtml(r.text || "")}</div>
                        <div style="margin-top:.5rem;color:#555">id: ${r.id}</div>`;
        results.appendChild(el);
      });
    } catch (e) {
      status.textContent = "Request failed: " + e;
    }
  }
  function escapeHtml(s) {
    return (s||"").replace(/[&<>\"']/g, function(m) { return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}[m]); });
  }
  btn.addEventListener("click", doSearch);
  qEl.addEventListener("keydown", function(e){
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) doSearch();
  });
});
// ...existing code...
