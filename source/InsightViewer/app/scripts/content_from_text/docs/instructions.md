# hal9000 C:\work\sola\instructions

1. **Slikaj strani knjige in s pomočjo chatGpt pripravi ocr text po posameznih streneh.** Navodilo za chatGpt:
   > Naredi ocr dokumenta in pri tem uporabi svoj notranji program ne python. Rezultat spravi v datoteko in pri tem uporabi številko strani v imenu po naslednjem formatu bio1+stran.txt

2. **Pripravi html za učenje**

   2.1 Združi ocr datoteke v eno datoteko z imenom `bio1_poglavje2.txt` (format: bio + letnik + poglavje). Opremi vse naslove z `< >`.

   2.2 ** Uporabi program `generate_content.py` za generiranje vsebine:   
         ```
            python3 generate_content.py \
            --template structure_Vsebina.html \
            --data /home/robert/insightViewer/source/InsightViewer/app/scripts/content_from_text/ocr/zgo_grki_d3.txt \
            --out /home/robert/insightViewer/source/InsightViewer/app/scripts/content_from_text/ocr/zgo_grki_d3.html
         ```

   2.3 ** Uporabi program `importCypherpy.py` za uvoz v neo4j:
         ```
            python3 src/generate_cypher.py ocr/zgo_grki_skupaj_flip.txt \	
               --project Zgodovina \
               --out-json output/zgo_grki_skupaj_flip.json \
               --out output/zgo_grki_skupaj_flip.cypher             
         ```

   2.4 ** Uporabi program `importCypherpy.py` za uvoz v neo4j:
         ```bash
            python src/importCypherpy.py \
            --cypher output/zgo_grki_skupaj_flip.cypher \
            --json output/zgo_grki_skupaj_flip.json	
         ```



   2.5 **Pripravi flip kartice na dva načina:**

      2.5.1 Uporabi program `generate_flipcards_rules.py`.

      2.5.2 Navodila za chatGpt:
      
         - V prilogi je datoteka `zgo_grki_skupaj_flip.txt`. Na podlagi te datoteke in spodnjega primera vprašanj qa pripravi vprašanja in odgovore ter pripravi datoteko zgoGrkiflipCard.json
             ```javascript
             const qa = [ { q:"Kaj je vreme in zakaj se lahko hitro spreminja?",
                     a: "Vreme je stanje ozračja v določenem času in kraju. Odvisno je od temperature zraka, od vlažnosti in od zračnega tlaka. Spreminja se lahko iz ure v uro in od kraja do kraja." },
             ];
             ```
         - Vrni vsako vprašanje z informacijo o poglavju, iz katerega je nastalo.         
         - Odstrani označilce `<< >>` pred in po vprašanjih in odgovorih.

To so osnovni koraki za delo s slikami knjige, OCR z ChatGPT, ustvarjanje HTML datotek za učenje ter generiranje flip kartic.
