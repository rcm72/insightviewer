// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2025 Robert Čmrlec

// Flashcards – minimal, robust, brez odvisnosti
// Vedênje: izpiše VSA vprašanja (front). Klik/Enter/Space flipne posamezno kartico.
// Optionals: Reset in Reveal gumbi.

(function(){
  // --- Zajem podatkov ---
  function fromHtmlBank(){
    const bank = document.getElementById('fc-bank');
    if(!bank) return null;
    const items = [...bank.querySelectorAll('li')];
    if(!items.length) return null;
    return items.map(li => ({
      q: (li.textContent || '').trim(),
      a: (li.getAttribute('data-answer') || '').trim()
    })).filter(x => x.q && x.a);
  }

  const bootFromWindow = Array.isArray(window.FC_BOOT_DATA) ? window.FC_BOOT_DATA : null;
  const data = bootFromWindow && bootFromWindow.length ? bootFromWindow
             : (fromHtmlBank() );

  // --- Gradnja DOM ---
  const host = document.getElementById('flashcards') || (() => {
    const d = document.createElement('div'); d.id = 'flashcards';
    document.body.appendChild(d); return d;
  })();

  function createCard(item, idx){
    const wrap = document.createElement('div');
    wrap.className = 'fc-card';
    wrap.dataset.index = String(idx);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute('aria-pressed','false');
    btn.setAttribute('aria-label','Preklopi odgovor');

    const inner = document.createElement('div');
    inner.className = 'fc-inner';

    const front = document.createElement('div');
    front.className = 'fc-face fc-front';
    front.innerHTML = '<div class="fc-q"></div>';
    front.querySelector('.fc-q').textContent = item.q;

    const back = document.createElement('div');
    back.className = 'fc-face fc-back';
    back.innerHTML = '<div class="fc-a"></div>';
    back.querySelector('.fc-a').textContent = item.a;

    inner.appendChild(front); inner.appendChild(back);
    btn.appendChild(inner); wrap.appendChild(btn);
    return wrap;
  }

  // Render
  host.innerHTML = '';
  data.forEach((it,i) => host.appendChild(createCard(it,i)));

  // --- Interakcija ---
  function flip(card, forceState){
    const isFlipped = card.classList.contains('flipped');
    const next = (typeof forceState === 'boolean') ? forceState : !isFlipped;
    card.classList.toggle('flipped', next);
    const btn = card.querySelector('button');
    if(btn) btn.setAttribute('aria-pressed', String(next));
  }

  host.addEventListener('click', (e) => {
    const card = e.target.closest('.fc-card');
    if(!card || !host.contains(card)) return;
    flip(card);
  });

  host.addEventListener('keydown', (e) => {
    const card = e.target.closest('.fc-card');
    if(!card) return;
    if(e.key === 'Enter' || e.key === ' '){
      e.preventDefault(); flip(card);
    }else if(e.key === 'Escape'){
      flip(card, false);
    }
  });

  // Fokus naj gre na kartico (gumb znotraj)
  host.querySelectorAll('.fc-card button').forEach(b => b.tabIndex = 0);

  // --- Kontrolni gumbi ---
  const btnReset = document.getElementById('fc-reset');
  if(btnReset){
    btnReset.addEventListener('click', () => {
      host.querySelectorAll('.fc-card').forEach(c => flip(c,false));
    });
  }
  const btnReveal = document.getElementById('fc-reveal');
  if(btnReveal){
    btnReveal.addEventListener('click', () => {
      host.querySelectorAll('.fc-card').forEach(c => flip(c,true));
    });
  }
})();
