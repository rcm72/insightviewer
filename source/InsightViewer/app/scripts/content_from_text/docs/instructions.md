# hal9000 C:\work\sola\instructions

1. **Slikaj strani knjige in s pomočjo chatGpt pripravi ocr text po posameznih streneh.** Navodilo za chatGpt:
   > Naredi ocr dokumenta in pri tem uporabi svoj notranji program ne python. Rezultat spravi v datoteko in pri tem uporabi številko strani v imenu po naslednjem formatu bio1+stran.txt

2. **Pripravi html za učenje**

   2.1 Združi ocr datoteke v eno datoteko z imenom `bio1_poglavje2.txt` (format: bio + letnik + poglavje). Opremi vse naslove z `< >`.

   2.2 **Generiranje vsebine lahko narediš na dva načina:**

      2.2.1 Uporabi program `generate_content.py` za generiranje vsebine:
      
         ```bash
         python build_cypher_from_text.py bio1_poglavje2.txt \
           --project Biologija \
           --out outBiologija1_ch2.cypher \
           --out-json payloadBiologija1_ch2.json
         ```

      2.2.2 Navodila za chatGpt:
      
         - V datoteki `structure_Vsebina.html` je primer strukture HTML.
         - Na podlagi vsebine iz datoteke `data.txt`, ustvari nov HTML dokument, ki uporablja to strukturo.
         - Čeprav so poglavja označeni kot `<Chapter>`, ne vključuj teh označilcev v generiranem HTML-u.

   2.3 **Pripravi flip kartice na dva načina:**

      2.3.1 Uporabi program `generate_flipcards_rules.py`.

      2.3.2 Navodila za chatGpt:
      
         - V prilogi je datoteka `structure_flipCard.html` v kateri je primer formata vprašanj qa.
             ```javascript
             const qa = [ { q:"Kaj je vreme in zakaj se lahko hitro spreminja?",
                     a: "Vreme je stanje ozračja v določenem času in kraju. Odvisno je od temperature zraka, od vlažnosti in od zračnega tlaka. Spreminja se lahko iz ure v uro in od kraja do kraja." },
             ];
             ```
         - Na podlagi datoteke `data.txt`, ustvari HTML stran imenovano `flipCard.html`.
         - Vrni vsako vprašanje z informacijo o poglavju, iz katerega je nastalo.
         - Ustvari mehanizem za filtriranje vprašanj po številki poglavja.
         - Odstrani označilce `< >` pred in po vprašanjih in odgovorih.

To so osnovni koraki za delo s slikami knjige, OCR z ChatGPT, ustvarjanje HTML datotek za učenje ter generiranje flip kartic.
