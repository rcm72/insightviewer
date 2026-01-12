const el = id => document.getElementById(id);

// Elements
const step1 = el('step1');
const step2 = el('step2');
const step3 = el('step3');
const step4 = el('step4');
const labelSelect = el('labelSelect');
const btnLoadNodes = el('btnLoadNodes');
const nodeSelect = el('nodeSelect');
const numQuestions = el('numQuestions');
const btnStartQuiz = el('btnStartQuiz');
const progressText = el('progressText');
const questionNum = el('questionNum');
const questionText = el('questionText');
const contextText = el('contextText');
const answerEl = el('answer');
const btnSubmit = el('btnSubmit');
const btnSkip = el('btnSkip');
const btnNext = el('btnNext');
const resultArea = el('resultArea');
const scoreEl = el('score');
const feedbackText = el('feedbackText');
const idealAnswerArea = el('idealAnswerArea');
const idealAnswerText = el('idealAnswerText');
const finalResults = el('finalResults');
const btnRestart = el('btnRestart');

// State
let nodes = [];
let questions = [];
let currentIndex = 0;
let results = [];
let quizMetadata = {}; // Store quiz metadata for submission

// API base - use quiz-api service port
const API_BASE = 'http://192.168.1.16:8001/quiz';  // adjust IP to your host

// Step 1: Load nodes by label
btnLoadNodes.addEventListener('click', async () => {
  const label = labelSelect.value;
  try {
    const res = await fetch(`${API_BASE}/nodes?label=${encodeURIComponent(label)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    nodes = data.nodes || [];
    if (nodes.length === 0) {
      alert('Ni najdenih vozlišč za izbrani tip.');
      return;
    }
    // Populate select
    nodeSelect.innerHTML = '';
    nodes.forEach((n, i) => {
      const opt = document.createElement('option');
      opt.value = i;
      opt.textContent = n.name || n.id_rc;
      nodeSelect.appendChild(opt);
    });
    step2.classList.remove('hidden');
  } catch (err) {
    alert('Napaka pri nalaganju vozlišč: ' + err.message);
  }
});

// Step 2: Start quiz
btnStartQuiz.addEventListener('click', async () => {
  const idx = parseInt(nodeSelect.value);
  if (isNaN(idx) || idx < 0 || idx >= nodes.length) {
    alert('Izberi vozlišče.');
    return;
  }
  const node = nodes[idx];
  const num = parseInt(numQuestions.value) || 5;
  
  // Store metadata for later submission
  quizMetadata = {
    node_id_rc: node.id_rc,
    node_name: node.name,
    student_name: 'Anonymous' // Can be made configurable later
  };
  
  try {
    const res = await fetch(`${API_BASE}/start?id_rc=${encodeURIComponent(node.id_rc)}&num_questions=${num}`);
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`HTTP ${res.status}: ${text}`);
    }
    const data = await res.json();
    questions = data.questions || [];
    if (questions.length === 0) {
      alert('Ni bilo mogoče generirati vprašanj.');
      return;
    }
    results = [];
    currentIndex = 0;
    step1.classList.add('hidden');
    step2.classList.add('hidden');
    step3.classList.remove('hidden');
    showQuestion();
  } catch (err) {
    alert('Napaka pri začetku kviza: ' + err.message);
  }
});

// Show current question
function showQuestion() {
  if (currentIndex >= questions.length) {
    showResults();
    return;
  }
  const q = questions[currentIndex];
  questionNum.textContent = `${currentIndex + 1} / ${questions.length}`;
  progressText.textContent = `Napredek: ${currentIndex} / ${questions.length} odgovorjenih`;
  questionText.textContent = q.question;
  contextText.textContent = q.context;
  answerEl.value = '';
  resultArea.classList.add('hidden');
  idealAnswerArea.classList.add('hidden');
  
  // Re-enable controls
  answerEl.disabled = false;
  btnSubmit.disabled = false;
  btnSkip.disabled = false;
}

// Submit answer
btnSubmit.addEventListener('click', async () => {
  const q = questions[currentIndex];
  const studentAnswer = answerEl.value.trim();
  if (!studentAnswer) {
    alert('Vnesi odgovor.');
    return;
  }
  
  // Disable controls during grading
  answerEl.disabled = true;
  btnSubmit.disabled = true;
  btnSkip.disabled = true;
  
  try {
    const payload = {
      context: q.context,
      question: q.question,
      ideal_answer: q.ideal_answer,
      student_answer: studentAnswer
    };
    const res = await fetch(`${API_BASE}/grade`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const score = data.score || 0;
    const feedback = data.feedback || '';
    
    // Show feedback
    resultArea.classList.remove('hidden');
    scoreEl.textContent = score;
    feedbackText.textContent = feedback;
    
    // Show ideal answer
    idealAnswerArea.classList.remove('hidden');
    idealAnswerText.textContent = q.ideal_answer;
    
    // Save result
    results.push({ question: q.question, answer: studentAnswer, score, feedback, ideal_answer: q.ideal_answer });
    
  } catch (err) {
    alert('Napaka pri ocenjevanju: ' + err.message);
    // Re-enable controls on error
    answerEl.disabled = false;
    btnSubmit.disabled = false;
    btnSkip.disabled = false;
  }
});

// Next question button
btnNext.addEventListener('click', () => {
  currentIndex++;
  showQuestion();
});

// Skip question
btnSkip.addEventListener('click', () => {
  results.push({ 
    question: questions[currentIndex].question, 
    answer: '(preskočeno)', 
    score: 0, 
    feedback: 'Vprašanje preskočeno',
    ideal_answer: questions[currentIndex].ideal_answer
  });
  currentIndex++;
  showQuestion();
});

// Show final results
async function showResults() {
  step3.classList.add('hidden');
  step4.classList.remove('hidden');
  const totalScore = results.reduce((sum, r) => sum + r.score, 0);
  const maxScore = results.length * 5;
  const avg = results.length > 0 ? (totalScore / results.length).toFixed(2) : 0;
  
  // Submit results to backend
  try {
    const payload = {
      node_id_rc: quizMetadata.node_id_rc,
      node_name: quizMetadata.node_name,
      student_name: quizMetadata.student_name,
      quiz_type: 'llm',
      results: results
    };
    
    const res = await fetch(`${API_BASE}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    if (res.ok) {
      const data = await res.json();
      console.log('Results saved:', data);
      finalResults.innerHTML = `
        <p style="color: #27ae60; font-weight: 600;">✓ Rezultati shranjeni! (Session ID: ${data.session_id.substring(0, 8)}...)</p>
        <p><strong>Skupaj točk:</strong> ${totalScore} / ${maxScore}</p>
        <p><strong>Povprečje:</strong> ${avg} / 5</p>
        <h4>Podrobnosti:</h4>
        <ul>
          ${results.map((r, i) => `
            <li>
              <strong>Vprašanje ${i+1}:</strong> ${r.question}<br>
              <em>Tvoj odgovor:</em> ${r.answer}<br>
              <strong>Ocena:</strong> ${r.score} / 5<br>
              <em>Povratna informacija:</em> ${r.feedback}<br>
              <div style="margin-top:8px; padding:8px; background:#e8f5e9; border-left:3px solid #4caf50; border-radius:4px;">
                <strong style="color:#2e7d32;">💡 Idealen odgovor:</strong> ${r.ideal_answer}
              </div>
            </li>
          `).join('')}
        </ul>
      `;
    } else {
      throw new Error('Failed to save results');
    }
  } catch (err) {
    console.error('Error saving results:', err);
    // Show results even if saving failed
    finalResults.innerHTML = `
      <p style="color: #e67e22;">⚠ Rezultati niso bili shranjeni na strežnik.</p>
      <p><strong>Skupaj točk:</strong> ${totalScore} / ${maxScore}</p>
      <p><strong>Povprečje:</strong> ${avg} / 5</p>
      <h4>Podrobnosti:</h4>
      <ul>
        ${results.map((r, i) => `
          <li>
            <strong>Vprašanje ${i+1}:</strong> ${r.question}<br>
            <em>Tvoj odgovor:</em> ${r.answer}<br>
            <strong>Ocena:</strong> ${r.score} / 5<br>
            <em>Povratna informacija:</em> ${r.feedback}<br>
            <div style="margin-top:8px; padding:8px; background:#e8f5e9; border-left:3px solid #4caf50; border-radius:4px;">
              <strong style="color:#2e7d32;">💡 Idealen odgovor:</strong> ${r.ideal_answer}
            </div>
          </li>
        `).join('')}
      </ul>
    `;
  }
}

// Restart
btnRestart.addEventListener('click', () => {
  step1.classList.remove('hidden');
  step2.classList.add('hidden');
  step3.classList.add('hidden');
  step4.classList.add('hidden');
  nodes = [];
  questions = [];
  results = [];
  currentIndex = 0;
});
