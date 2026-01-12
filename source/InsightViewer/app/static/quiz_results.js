// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2025 Robert Čmrlec

const el = id => document.getElementById(id);

// Elements
const studentFilter = el('studentFilter');
const limitSelect = el('limitSelect');
const btnFilter = el('btnFilter');
const btnRefresh = el('btnRefresh');
const resultsContainer = el('resultsContainer');

// API base
const API_BASE = 'http://192.168.1.16:8001/quiz';

// Format timestamp
function formatDate(isoString) {
  if (!isoString) return 'N/A';
  const date = new Date(isoString);
  return date.toLocaleString('sl-SI', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

// Load and display results
async function loadResults() {
  resultsContainer.innerHTML = '<div class="loading">Nalagam rezultate...</div>';
  
  try {
    const limit = limitSelect.value;
    const studentName = studentFilter.value.trim();
    
    let url = `${API_BASE}/results?limit=${limit}`;
    if (studentName) {
      url += `&student_name=${encodeURIComponent(studentName)}`;
    }
    
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    const data = await res.json();
    const sessions = data.results || [];
    
    if (sessions.length === 0) {
      resultsContainer.innerHTML = '<div class="empty">Ni rezultatov za prikaz.</div>';
      return;
    }
    
    // Render sessions
    resultsContainer.innerHTML = sessions.map((session, idx) => {
      const percentage = session.max_score > 0 
        ? Math.round((session.total_score / session.max_score) * 100)
        : 0;
      
      return `
        <div class="session-card" data-session-id="${session.session_id}">
          <div class="session-header">
            <div class="session-info">
              <h3>${session.node_name || 'Kviz'}</h3>
              <div class="session-meta">
                👤 ${session.student_name || 'Anonymous'} | 
                📅 ${formatDate(session.timestamp)} | 
                📝 ${session.total_questions} vprašanj
              </div>
            </div>
            <div class="session-score">
              <span class="score-big">${percentage}%</span>
              <span class="score-label">${session.total_score} / ${session.max_score} točk</span><br>
              <span class="score-label">Povprečje: ${session.average_score.toFixed(2)}</span>
            </div>
          </div>
          <button class="expand-btn" onclick="toggleDetails('${session.session_id}')">
            Prikaži podrobnosti ▼
          </button>
          <div class="session-details" id="details-${session.session_id}">
            ${renderQuestionResults(session.results)}
          </div>
        </div>
      `;
    }).join('');
    
  } catch (err) {
    resultsContainer.innerHTML = `<div class="empty">Napaka pri nalaganju rezultatov: ${err.message}</div>`;
  }
}

// Render question results
function renderQuestionResults(results) {
  if (!results || results.length === 0) {
    return '<p>Ni podrobnosti o vprašanjih.</p>';
  }
  
  // Sort by question number
  const sorted = results.sort((a, b) => (a.question_number || 0) - (b.question_number || 0));
  
  return sorted.map(r => {
    const score = r.score || 0;
    return `
      <div class="question-item score-${score}">
        <strong>Vprašanje ${r.question_number}:</strong> ${r.question || 'N/A'}<br>
        <em style="color: #666;">Odgovor študenta:</em> ${r.student_answer || 'N/A'}<br>
        <strong style="color: #667eea;">Ocena: ${score} / 5</strong><br>
        <em style="color: #555;">Povratna informacija:</em> ${r.feedback || 'N/A'}
        ${r.ideal_answer ? `
          <div class="ideal-answer-box">
            <strong style="color: #2e7d32;">💡 Idealen odgovor:</strong><br>
            ${r.ideal_answer}
          </div>
        ` : ''}
      </div>
    `;
  }).join('');
}

// Toggle session details
function toggleDetails(sessionId) {
  const details = document.getElementById(`details-${sessionId}`);
  const btn = details.previousElementSibling;
  
  if (details.classList.contains('visible')) {
    details.classList.remove('visible');
    btn.textContent = 'Prikaži podrobnosti ▼';
  } else {
    details.classList.add('visible');
    btn.textContent = 'Skrij podrobnosti ▲';
  }
}

// Make toggleDetails available globally
window.toggleDetails = toggleDetails;

// Event listeners
btnFilter.addEventListener('click', loadResults);
btnRefresh.addEventListener('click', loadResults);

// Load on enter in filter input
studentFilter.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') loadResults();
});

// Initial load
loadResults();
