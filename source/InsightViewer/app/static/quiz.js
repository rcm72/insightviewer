// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2025 Robert Čmrlec

// Read questions from the hidden HTML bank
function loadQuestionsFromDOM() {
  const bank = document.getElementById('question-bank');
  const items = bank ? [...bank.querySelectorAll(':scope > li')] : [];
  return items.map(li => {
    const question = (li.querySelector('.q') && li.querySelector('.q').textContent) ? li.querySelector('.q').textContent.trim() : '';
    const answer = (li.dataset && li.dataset.answer) ? li.dataset.answer.trim() : '';
    const options = [...li.querySelectorAll('.opts > li')].map(li => li.textContent.trim());
    return { question, options, answer };
  });
}

const quizQuestions = loadQuestionsFromDOM();

// Elements
const qEl = document.getElementById('question');
const optsEl = document.getElementById('options');
const progressEl = document.getElementById('progress');
const scoreEl = document.getElementById('score');

let index = 0;
let score = 0;
const incorrectAnswers = []; // collect wrong answers

function normalizeText(s) {
  return (s || '').toLowerCase().trim().replace(/\s+/g, ' ');
}

function renderQuestion() {
  const q = quizQuestions[index];
  progressEl.textContent = `Vprašanje ${index + 1} / ${quizQuestions.length}`;
  qEl.textContent = q.question;

  // Clear and create input + submit UI
  optsEl.innerHTML = '';

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'quiz-input';
  input.placeholder = 'Vnesite odgovor...';
  input.autocomplete = 'off';
  input.spellcheck = false;
  input.style.minWidth = '60%';
  input.style.padding = '6px';
  input.style.marginRight = '8px';

  const submit = document.createElement('button');
  submit.className = 'btn';
  submit.textContent = 'Preveri';

  const feedback = document.createElement('div');
  feedback.className = 'quiz-feedback';
  feedback.style.marginTop = '8px';

  optsEl.appendChild(input);
  optsEl.appendChild(submit);
  optsEl.appendChild(feedback);

  input.focus();

  function finishAndAdvance(correct, userAnswer) {
    // disable controls
    input.disabled = true;
    submit.disabled = true;

    if (correct) {
      score++;
      feedback.textContent = 'Pravilno ✓';
      feedback.classList.remove('wrong');
      feedback.classList.add('correct');
    } else {
      const correctAnswer = quizQuestions[index].answer;
      feedback.textContent = `Napačno — pravilen odgovor: ${correctAnswer}`;
      feedback.classList.remove('correct');
      feedback.classList.add('wrong');

      // record incorrect
      incorrectAnswers.push({
        index: index,
        question: quizQuestions[index].question,
        userAnswer: userAnswer,
        correctAnswer: correctAnswer
      });
    }

    scoreEl.textContent = `Rezultat: ${score} / ${quizQuestions.length}`;

    setTimeout(() => {
      index++;
      if (index < quizQuestions.length) {
        renderQuestion();
      } else {
        endQuiz();
      }
    }, 900);
  }

  function submitAnswer() {
    const val = normalizeText(input.value);
    const correct = normalizeText(quizQuestions[index].answer);
    finishAndAdvance(val === correct, input.value);
  }

  submit.addEventListener('click', submitAnswer);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submitAnswer();
  });
}

function endQuiz() {
  qEl.textContent = 'Kviz končan!';
  optsEl.innerHTML = '';
  progressEl.textContent = '';
  scoreEl.textContent = `Vaš rezultat: ${score} od ${quizQuestions.length}`;

  if (incorrectAnswers.length > 0) {
    const heading = document.createElement('h4');
    heading.textContent = `Vprašanja na katera ste odgovorili napačno (${incorrectAnswers.length}):`;
    optsEl.appendChild(heading);

    const list = document.createElement('ol');
    incorrectAnswers.forEach(item => {
      const li = document.createElement('li');
      li.style.marginBottom = '8px';
      const qspan = document.createElement('div');
      qspan.textContent = item.question;
      qspan.style.fontWeight = '600';
      const user = document.createElement('div');
      user.textContent = `Vaš odgovor: ${item.userAnswer || '(brez odgovora)'}`;
      user.style.color = '#b33';
      const corr = document.createElement('div');
      corr.textContent = `Pravilen odgovor: ${item.correctAnswer}`;
      corr.style.color = '#2a7';
      li.appendChild(qspan);
      li.appendChild(user);
      li.appendChild(corr);
      list.appendChild(li);
    });
    optsEl.appendChild(list);
  } else {
    const msg = document.createElement('div');
    msg.textContent = 'Bravo — vsi odgovori so pravilni!';
    optsEl.appendChild(msg);
  }

  const repeat = document.createElement('button');
  repeat.className = 'btn';
  repeat.textContent = 'Reši znova';
  repeat.onclick = () => { index = 0; score = 0; incorrectAnswers.length = 0; scoreEl.textContent=''; renderQuestion(); };
  optsEl.appendChild(repeat);
}

// Init
if (quizQuestions.length > 0) {
  renderQuestion();
} else {
  if (qEl) qEl.textContent = 'Ni vprašanj.';
}
