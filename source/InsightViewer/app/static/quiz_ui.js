document.addEventListener('DOMContentLoaded', () => {
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

  // Nova spremenljivka za vnaprej pripravljena vprašanja in odgovore
  const preparedQA = [

    { q:"[DodatniListi.2] Primerjaj rastlinsko in živalsko celico po zgradbi",
      chap:"2.0",
      srcSid:"2.0",
      a:`
      <table>
        <thead>
          <tr>
        <th>Lastnost</th>
        <th>Rastlinska celica</th>
        <th>Živalska celica</th>
          </tr>
        </thead>
        <tbody>
          <tr>
        <td>Celična stena</td>
        <td>Prisotna (iz celuloze)</td>
        <td>Ni prisotna</td>
          </tr>
          <tr>
        <td>Kloroplasti</td>
        <td>Prisotni</td>
        <td>Ni prisotnih</td>
          </tr>
          <tr>
        <td>Vakuole</td>
        <td>Velike in osrednje</td>
        <td>Majhne ali jih ni</td>
          </tr>
          <tr>
        <td>Lizosomi</td>
        <td>Običajno ni prisotnih</td>
        <td>Prisotni</td>
          </tr>
          <tr>
        <td>Centriole</td>
        <td>Običajno ni prisotnih</td>
        <td>Prisotne</td>
          </tr>
          <tr>
        </tbody>
      </table>
      <br>
      Skupne struktur prisotne v obeh so <br>
      - Celična membrana, <br>
      - jedro, <br>
      - mitohondriji, <br>
      - endoplazemski retikel, <br>
      - Golgijev aparat, <br>
      - ribosomi          
      ` },

  { q:"[DodatniListi.2] Primerjaj lastnosti Arheje, Bakterije in Evkarionte",
      chap:"2.0",
      srcSid:"2.0",
      a:`- <img src="/static/images/bookBiologija1/slike/DodatniListi/bio_dodatno_pog2_01_01.jpg"
             alt="Evglena (Razvojno drevo)"
             style="max-width: 100%; height: auto; cursor: zoom-in;">` 
             },

  { q:"[DodatniListi.2] Vakuola",
      chap:"2.0",
      srcSid:"2.0",
      a:`v starejših rastlinskih celicah je zelo velika in zavzema skoraj celoten  volumen celice<br>
      vsebuje celični sok, ki je raztopina vode, dpadnih snovi, barvil ... <br>
      <b>tonoplast</b> je membrana, ki obdaja vakuolo <br>
      <b>turgor</b> je tlak v vakuoli, ki daje rastlinski celici oporo in čvrstost <br>
      `},	  

  { q:"[DodatniListi.2] Kloroplast",
      chap:"2.0",
      srcSid:"2.0",
      a:`Kloroplast vsebujejo samo rastlinske celice <br>
      v kloroplastu poteka fotosinteza<br>
      ima nagubano notranjost<br>
      ima zunanjo membrano<br>
      v kloroplastu poteka fotosinteza<br>
      nagubana notranjost so tilakoidi<br>
      vsebuje klorofil za potek svetlobnih reakcij in nastanek ATP<br>
      stroma je tekočina znotraj kloroplasta, v kateri potekajo temeljne reakcije fotosinteze, pri katerih nastane glukoza <br>
      lastna DNA in ribosomi omogočajo sintezo nekaterih beljakovin kloroplasta <br>
      kloroplasti so nastali po endosimbiontski teoriji iz prokariontskih cianobakterij<br>
      `},

  { q:"[DodatniListi.2] Kaj so plastidi]",
      chap:"2.0",
      srcSid:"2.0",
      a:`Plastidi so organeli, ki jih imajo rastlinske celice <br>
      - kloroplasti (zeleno barvilo klorofil, fotosinteza)<br>
      - kromoplasti (rdeča, oranžna, rumena - so zaloga barvil v cvetovih, plodovih, podzemnih delih rastlin)<br>
      - aminoplasti so brezbarvni in služijo skladiščenju škroba)<br>
      `},

  
  { q:"[DodatniListi.0] Golgijev aparat",
      chap:"2.0",
      srcSid:"2.0",
      a:`Golgijev apart dokončno obdela in sortira snovi (beljakovine) ter jih pakira v mehurčke (glikoproteine, lipide) za izvoz iz celice (eksciotoza - izločanje) ali za uporabo znotraj celice.<br>
      glikoproteini so beljakovine z vezanimi ogljikovimi hidrati <br>
      lipidi so maščobne snovi <br>
      eksocitoza je proces izločanja snovi iz celice preko celične membrane <br>
      `},	        

  { q:"[DodatniListi.0] Lizosom",
      chap:"2.0",
      srcSid:"2.0",
      a:`je značilen organel živalskih celic <br>
      primarni lizosom nastane iz Golgijevega aparata in vsebuje prebavne encime za znotrajcelično prebavo <br>
      sekundarni lizosom ali prebavna vakuola nastane z združitvijo primarnega lizosoma in enodicitnega vezikla<br>
      enocitni vezikel nastane z endocitozo (vključevanje snovi v celico preko celične membrane) <br>
      `},	        

  { q:"[DodatniListi.0] Robosomi",
      chap:"2.0",
      srcSid:"2.0",
      a:`Vsebujejo jih vse celice <br>
      Ribosom ni membranski organel, ne vsebuje fosfolipidov, ampak je sestavljen iz RNA in beljakovin <br>
      RNA je iz nuleotidov, beljakovine pa iz aminokislin <br>
      na ribosomih poteka sinteza beljakovin (prevajanje dedne informacije iz mRNA v zaporedje aminokislin v beljakovini) <br>
      na prostih ribosomih nastajajo citosolni proteini <br>
      na ribosomih, vezanih na GER, nastajajo membranski in sekrecijski proteini <br>
      `},

  { q:"[DodatniListi.0] Motohondrij",
      chap:"2.0",
      srcSid:"2.0",
      a:`Vsebujejo jih živalske, rastlinske celice in glivne celice <br>
      ima zunanja in notranja membrana <br>
      notranja membrana je nagubana in tvori kriste <br>
      mitohondirj ima lastno DNA in ribosome <br>
      nastane je po endosimbiontski teoriji iz prokariontskih celičnih dihalcev <br>
      v mitohondriju poteka celično dihanje, pri katerem se sprošča energija iz glukoze v obliki ATP <br>
      
      `},      

  { q:"[DodatniListi.0] Celična stena",
      chap:"2.0",
      srcSid:"2.0",
      a:`je trda in toga plast, ki daje oporo, zaščito in obliko <br>
      je nepropustna za večino snovi <br>
      pri rastlinah je zgrajena iz celuloze, pri glivah je zgrajena iz hitina, živalska celica nima stene <br>
      leži zunaj celične membrane <br>
      najprej nastane primarna celična stena, ki je tanka in prožna, kasneje pa se lahko tvori sekundarna celična stena, ki je debelejša in trša <br>  
      med dvema rastlinskima celicama je osrednja lamela, ki ju drži skupaj <br>
      rastlinsko celico brez celične stene imenujemo protoplast <br>
      celična stena je na nekaterih mestih prekinjena s plazmodesmami, ki omogočajo izmenjavo snovi in informacij med sosednjimi celicami <br>            
      `},      

  { q:"[DodatniListi.0] Gladki AER",
      chap:"2.0",
      srcSid:"2.0",
      a:`je preplet cevk membran, ki nima ribosomov <br>
      v njem poteka sinteza lipidov (fosfolipidi) ali lipidov, ki jih celica izloči - sekrecijski lipidi npr. stroidi <
      `},      

  { q:"[DodatniListi.0] Endoplazemski retikulum (ER)",
      chap:"2.0",
      srcSid:"2.0",
      a:`je membranski celični organel<br>
      znrati GER ima sploščene cisterne membran, na katerih so ribosomi <br>
      na ribosomih GER poteka sinteza membranskih in sekrecijskih proteinov, ki dozorevajo in potujejo v notranjosti cistern <br>
      `},      

  { q:"[DodatniListi.0] Jedro ali nukleus",
      chap:"2.0",
      srcSid:"2.0",
      a:`nadzoruje delovanje celice in shranjuje dedno informacijo <br>
      v njem je shranjena DNA, v obliki kromatina  ovitega okrog histonov<br>
      vsebuje jedrce, kjer je jedrna DNA bolj skoncentrirana in nosi navodila za izgradnjo rRNA <br>
      dvojna jedrna membrana ima pore in se nadaljuje v membrane zrnatega ER <br>
      `},

  { q:"[DodatniListi.0] Bički, migetalke ",
      chap:"2.0",
      srcSid:"2.0",
      a:`obadni so z membrano<br>
      vsebujejo gibljive beljakovinske niti, ki omogočajo gibanje celice <br>
      mikrotubuli so zgrajeni iz beljakovine tubulina, razporejeni so (9X2+2) <br>
      za gibanje celice se uporabljajo bički in migetalke <br>
      `},      

  { q:"[DodatniListi.0] Bazalno telo",
      chap:"2.0",
      srcSid:"2.0",
      a:`iz bazalnega telesa izhaja biček ali migetalka <br>
      zgrajeno je iz mikrotubulov, razporejenih v (9X3) <br>
      `},      

  { q:"[DodatniListi.0] Centrosom / centriol",
      chap:"2.0",
      srcSid:"2.0",
      a:`centrosom je območje v bližini jedra živalske celice, kjer se nahajata dve centrioli <br>
      centrioli so zgrajene iz mikrotubulov, razporejenih v (9X3) <br>
      centrioli sodelujejo pri organizaciji delitvenega vretena med mitozo in mejozo <br>
      tovrijo niti delitvenega vretena, na katere se pripnejo kromosomi <br>
      `},

  { q:"[DodatniListi.0] Citoskelet",
      chap:"2.0",
      srcSid:"2.0",
      a:`nudi oporo celici, ji daje obliko in obliko <br>
      mikrotubuli gradijo bičke in migetalke ter niti delitvenega vretena <br>
      veliki so približno 25 nm <br>
      intermedijarni filamenti so veliki približno 10 nm, celici dajejo odpornost na pritiske in raztezke, vzdržujejo obliko celice: keratin (koža, nohti, lasje) <br>
      mikrofilamenti so veliki približno 7 nm, zgrajeni iz aktina, omogočajo gibanje celice in spremembo oblike celice in jih najdemo v mišičnih vlaknih <br>
      `},

  { q:"[DodatniListi.0] Celična membrana ali plazmalema",
      chap:"2.0",
      srcSid:"2.0",
      a:`obdaja celico in ločuje notranjost celice od zunanjega okolja <br>
      imajo jo vse celice <br>
      izbirno prepušča snovi v celico in iz celice <br>
      lipidni dvosloj - model tekočega mozaika <br>
      iz fosfolipidov, beljakovin in ogljikovih hidratov <br>
      pri živalskih celicah je v membrano vgrajen holesterol, ki uravnava fluidnost membrane <br>
      `},      

  { q:"[DodatniListi.0] Citosol",
      chap:"2.0",
      srcSid:"2.0",
      a:`je raztopina vode, soli in proteinov, ogljikovih hidratov, maščob <br>
      v njem potekajo številne biokemijske reakcije <br>
      `},

  { q:"[DodatniListi.0] Dokazi za endosimbiontsko teorijo",
      chap:"2.0",
      srcSid:"2.0",
      a:`dvojna membrana mitohondrijev in kloroplastov <br>
      lastna DNA, ki se samostojno podvaja in ni obdana z ovojnico<br>
      vsebuje lastne ribosome, podobne bakterijskim ribosomom<br>
      je velikosti bakterijske celice<br>
      `},      

  { q:"[DodatniListi.0] Vrste celic",
      chap:"2.0",
      srcSid:"2.0",
      a:`prokariontske celice: nimajo jedra in membranskih organelov (bakterije, arheje) <br>
      evkariontske celice: imajo jedro in membranske organele (rastlinske, živalske, glivne celice in protisti (enoceličarji)) <br>
      velikost celic: prokariontske celice so manjše (1-10 µm), evkariontske celice so večje (10-100 µm) <br>
      `},      

  { q:"[DodatniListi.0] Celična teorija",
      chap:"2.0",
      srcSid:"2.0",
      a:`Vsa živa bitja so zgrajena iz celic.<br>
      Vse celice imajo podobno kemijsko sestavo.<br>
      celice vsebujejo gene z navodili za delovanje celice, rast. Geni se pri delitvi prenašajo na potomke.<br>
      nove celice nastajajo z delitvijo obstoječih celic.<br>
      v celici potekajo življensko pomembne kemijske reakcije (presnova).<br>
      skupne značilnosti celic kažejo na skupen izvor življenja na Zemlji.<br>
      Skupne značilnosti so celična membrana, DNA, ribosomi, osnovne presnovne poti (npr. glikoliza), citoplazma, citosol.<br>
      Celica nastane z delitvijo, raste, se stara in odmre.<br>             
      `},      

      
  { q:"[DodatniListi.0] Zgodovina odrivanja celice ",
      chap:"2.0",
      srcSid:"2.0",
      a:`1662 Robert Hooke izumi mikrosop in uvede izraz celica<br>
      1680 A. Von Leeuwenhoek je izdeloval proproste mikroskope in opica enoceličarje, bakterije, eritrocite, praživali <br>
      1839 Schleiden in Schwann oblikujeta celično teorijo. Ugotovila sta, da so vse živali in vse rastline iz celic<br> 
      1855 R. Virchow dopolni celično teorijo z ugotovitvijo, da vse celice nastanejo iz obstoječih celic<br>
      1879 - W. Flemming opiše delitev celic in jo poimenuje mitoza<br>
      `},      

  { q:"[DodatniListi.0] Katere so oblike bakterijskih celic",
      chap:"2.0",
      srcSid:"2.0",
      a:`Bakterijske celice so lahko različnih oblik:<br>
      - kroglične (kok, pneumokok, streptokoki, stafilokoki), <br>
      - paličaste (bacil), <br>
      - vijugaste (spiril, spirohete), <br>
      - vijačaste (spiroheta). <br>      
      `},

  { q:"[DodatniListi.0] Opazovanje bakterij",
      chap:"2.0",
      srcSid:"2.0",
      a:`Pri 1000-2000-kratni povečavi z optičnim mikroskopom <br>  
      Za boljši kontrast pri opazovanju bakterij uporabljamo različne barvne tehnike, npr. Gramovo barvanje
      Po Gramovem barvanju ločimo bakterije na Gram-pozitivne (modro-vijolične) in Gram-negativne (rdeče-roza). <br>
      `},      
  
  { q:"[DodatniListi.0] Krožni kromosom",
      chap:"2.0",
      srcSid:"2.0",
      a:`Krožni kromosom nosi genski zapis za osnovne lastnosti Plazmid <br>
      Izvenkromosomksa manjša ciklična DNA nosi zapis za posebne lastnosti (npr. odpornost na antibiotike) <br>      
      `},

  { q:"[DodatniListi.0] Ribosomi ",
      chap:"2.0",
      srcSid:"2.0",
      a:`N njih poteka sinteza beljakovin (večaj podenota 50S in manjša 30S) <br>`},	                    

  { q:"[DodatniListi.0] Pili ali fimbrije ",
      chap:"2.0",
      srcSid:"2.0",
      a:`To so lasasti izrastki na površini bakterijske celice, zgrajeni iz beljakovine pilina <br>
      S pili se bakterije vežejo na površine in med seboj (konjug`},

  { q:"[DodatniListi.0] Bički",
      chap:"2.0",
      srcSid:"2.0",
      a:`Bički sodelujejo pri gibanju bakterijske celice `},	        

  { q:"[DodatniListi.0] Celična membrana",
      chap:"2.0",
      srcSid:"2.0",
      a:`Selektivno prepušča snovi v celico in iz celice <br>`},      

  { q:"[DodatniListi.0] Mezosom",
      chap:"2.0",
      srcSid:"2.0",
      a:`To so uvihki celične membrane.<br>
      vsebujejo encime za celično dihanje <br>
      sodelujejo pri cepitvi celice <br>
      `},

  { q:"[DodatniListi.0] Celična stena",
      chap:"2.0",
      srcSid:"2.0",
      a:`Sestavljena je iz peptidoglikana (mureina) <br>
      daje oporo in obliko<br>`}, 

  { q:"[DodatniListi.0] Kapsula",
      chap:"2.0",
      srcSid:"2.0",
      a:`Ščiti bakterijsko celico pred vplivi okolja<br>`},      

  { q:"[DodatniListi.0] Citoplazma",
      chap:"2.0",
      srcSid:"2.0",
      a:`Je vodna raztopina, ki zapolnjuje celico, v njej poteka presnova<br>`},

  { q:"[DodatniListi.0] Katera dva načina transportov snovi preko celične membrane poznamo",
      chap:"2.0",
      srcSid:"2.0",
      a:`Pasivni transport (difuzija, olajšana difuzija, osmoza) in aktivni transport (črpalke, endocitoza, eksocitoza)<br>
      Aktivni transport potrebuje energijo v obliki ATP<br>`},

  { q:"[DodatniListi.0] Opiši pasivni transport preko celične membrane",
      chap:"2.0",
      srcSid:"2.0",
      a:`Pri pasivnem transportu celica na porablja dodatne energije (ATP)<br>
      delci potujejo zaradi razlike v koncentraciji delcev. Potujejo iz območja z višjo koncentracijo proti območju z nižjo koncentracijo<br>
      `},

  { q:"[DodatniListi.0] Opiši aktivni transport preko celične membrane",
      chap:"2.0",
      srcSid:"2.0",
      a:`Pri tem transportu celica porablja dodatno energijo (ATP)<br>
      delci potujejo v smeri naraščujoče koncentracije delcev<br>
      `},

  { q:"[DodatniListi.0] Difuzija",
      chap:"2.0",
      srcSid:"2.0",
      a:`Difuzija je temeljni način pasivnega transporta snovi preko celične membrane<br>
      Delci se premikajo zaradi koncentracijskega gradienta iz območja z višjo koncentracijo proti območju z nižjo koncentracijo, pri tem dobijo delci kinetično energijo<br>
      Difuzija poteka, dokler se koncentracija delcev na obeh straneh membrane ne izenači<br>
      `},

  { q:"[DodatniListi.0] Kako lahko poteka pasivni transport",
      chap:"2.0",
      srcSid:"2.0",
      a:`Poteka lahko:
      - neposredno skozi lipidni dvosloj (majhni nepolanrni delci, npr. O2, CO2, H2O) <br>
      - skozi posebne pore<br>
      - z pomočjo transportnih beljakovin (olajšana difuzija)<br
      Difuzija vode preko polprepustne membrane se imenuje osmoza<br>
      `
    },      

  { q:"[DodatniListi.0] Kaj je osmoza",
      chap:"2.0",
      srcSid:"2.0",
      a:`Je difuzija vode preko polprepustne membrane iz območja z nižjo koncentracijo raztopljenih snovi proti območju z višjo koncentracijo raztopljenih snovi<br>
    voda prehaja v smeri večje koncentracije raztopljenih snovi<br>
    sometski potencial reztopine je merilo za sposobnost raztopine, da pridobiva vodo z osmozo<br>
    osmotski tlaj je merilo za težnjo vode, da z osmozo vstopa v raztopino, se veča ali manjša<br>
      `},
          

  { q:"[DodatniListi.0] ",
      chap:"2.0",
      srcSid:"2.0",
      a:``},    

  ];

  // Funkcija za nalaganje vnaprej pripravljenih vprašanj
  function loadPreparedQuestions() {
    questions = preparedQA.map(item => ({
      question: item.q || 'Ni vprašanja.', // Ensure a default question if `q` is empty
      context: `Poglavje: ${item.chap}, Vir: ${item.srcSid}`,
      ideal_answer: item.a || 'Ni idealnega odgovora.' // Ensure a default answer if `a` is empty
    }));
    results = [];
    currentIndex = 0;
    step3.classList.remove('hidden');
    showQuestion(); // Ensure this is called to display the first question
  }

  // Function to load questions from the "ollama" source
  async function loadOllamaQuestions() {
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
    
  }

  // Example function where questionText is updated
  function updateQuestionText(question) {
    const questionTextElement = document.getElementById('questionText');
    
    // Debugging: Check if the element is selected
    if (!questionTextElement) {
        console.error('Element with id "questionText" not found.');
        return;
    }

    // Debugging: Log the question data
    console.log('Updating questionText with:', question);

    // Update the question text
    questionTextElement.innerHTML = question || '⚠️ Question text is empty or unavailable.';

    // Debugging: Verify the update
    console.log('Updated questionText content:', questionTextElement.textContent);
  }

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
  btnStartQuiz.addEventListener('click', () => {
    const selectedSource = document.querySelector('input[name="questionSource"]:checked').value;
    if (selectedSource === 'prepared') {
      loadPreparedQuestions();
    } else if (selectedSource === 'ollama') {
      loadOllamaQuestions();
    } else {
      console.error('Unknown question source selected.');
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
    updateQuestionText(q.question);
    contextText.innerHTML = q.context;
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
      feedbackText.innerHTML = feedback;
      
      // Show ideal answer
      idealAnswerArea.classList.remove('hidden');
      idealAnswerText.innerHTML = q.ideal_answer;
      
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
});
