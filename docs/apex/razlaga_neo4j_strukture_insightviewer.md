# Razlaga Neo4j strukture za InsightViewer (Forms → APEX migracija)

## Namen

Ta dokument razlaga predlagano Neo4j strukturo za InsightViewer, ki podpira:

- migracijo Oracle Forms → APEX
- dokumentiranje sistema
- onboarding novih sodelavcev
- kasnejše vzdrževanje
- full-text search
- GraphRAG / AI layer

Poudarek je na tem, **kaj posamezni node-i in relacije pomenijo v praksi**.

---

## 1. Glavna ideja modela

Model loči tri vrste realnosti:

### 1. Legacy sistem
To je stari svet Oracle Forms.

Sem sodijo:
- `LegacyApplication`
- `OraForm`
- `OraBlock`
- `ORATable`
- `OracleProcedure`
- `OraclePackage`

### 2. Target sistem
To je nova APEX implementacija.

Sem sodijo:
- `APEXApp`
- `APEXPage`
- `APEXRegion`
- `APEXButton`
- `APEXDynamicAction`
- `APEXDynamicActionStep`

### 3. Migracijski in dokumentacijski kontekst
To je plast, ki opisuje, kako se je prehod iz legacy sveta v APEX zgodil.

Sem sodijo:
- `MigrationCase`
- `DocumentationHTML`
- `DocumentationMD`
- `Section`
- `Chunk`

To ločevanje je pomembno, ker:

- `OraForm` ni isto kot `MigrationCase`
- `APEXPage` ni isto kot dokumentacija
- dokumentacija ni isto kot tehnična struktura
- AI potrebuje povezave med vsemi temi plastmi

---

## 2. Obvezni tehnični fieldi

Vsak node naj ima:

```text
id_rc
projectName
created_on
updated_on
```

### `id_rc`
To je tehnični identifikator tvoje aplikacije InsightViewer.

- generira se z `randomUUID()`
- je stabilen za UI in API
- ni vezan na pomen objekta
- je glavni tehnični ključ v tvoji aplikaciji

### `projectName`
To je logična oznaka projekta.

Pri tvojem primeru:

```text
projectName = 'APEX'
```

S tem lahko v isti bazi hraniš več projektov in jih ločuješ.

### `created_on`, `updated_on`
Uporabna za:
- sledenje spremembam
- audit
- debugging
- poznejše dashboarde

---

## 3. Kaj je `key`

`key` je **logični identifikator**.

Ni isto kot `id_rc`.

### `id_rc`
- tehnični UUID
- primeren za aplikacijo

### `key`
- človeško razumljiv
- determinističen
- primeren za `MERGE`
- uporaben pri importih

### Pomembno
Pri ročno ustvarjenih node-ih je lahko `key` sprva prazen.

Pri tehničnih/importiranih node-ih je priporočljivo, da obstaja.

---

## 4. Pravilo za `key`

Za tehnične node-e naj velja:

```text
key = <Label>:<identity parts>
```

Primeri:

```text
ORATable:REI_DB:RCM72:SIF_STATUS
APEXPage:100:45
APEXRegion:100:45:20
APEXButton:100:45:RUN_PROC
OracleProcedure:REI_DB:RCM72:PKG_REI.PROCESS_VM
OraForm:Vmesniki_pozavarovanja
OraBlock:Vmesniki_pozavarovanja:BLK_VM_POZ
```

To je dobro, ker:
- ni potrebna konverzija tipa `OraTable → Table`
- key sledi labeli
- deluje enotno skozi sistem

---

## 5. LegacyApplication

Predstavlja širšo staro aplikacijo ali domeno, npr.:

- Reinsurance
- Provizije

### Namen
To je višji organizacijski nivo, ki pove, v kateri poslovni ali aplikacijski domeni se nahajajo forme.

### Tipične relacije

```text
(LegacyApplication)-[:HAS_FORM]->(OraForm)
(LegacyApplication)-[:USES_TABLE]->(ORATable)
```

### Uporaba v praksi
Omogoča vprašanja:

- katere forme spadajo v Reinsurance?
- katere aplikacije uporabljajo isti šifrant?
- koliko migracijskih primerov pripada isti domeni?

---

## 6. OraForm

Predstavlja eno Oracle Forms formo.

To je dejanski objekt starega sistema.

### Pomembno
`OraForm` ni migracija.  
Je **izvorni artefakt**.

### Tipične relacije

```text
(LegacyApplication)-[:HAS_FORM]->(OraForm)
(OraForm)-[:HAS_BLOCK]->(OraBlock)
(OraForm)-[:USES_TABLE]->(ORATable)
(OraForm)-[:CALLS]->(OracleProcedure)
(OraForm)-[:MIGRATED_TO]->(APEXPage)
```

### Uporaba v praksi
Omogoča:
- sledljivost starega sistema
- povezavo z dokumentacijo
- mapiranje na APEX

---

## 7. OraBlock

Predstavlja block znotraj forme.

To je pomembno, ker se v Forms logika pogosto skriva po blockih.

### Tipične relacije

```text
(OraForm)-[:HAS_BLOCK]->(OraBlock)
(OraBlock)-[:MIGRATED_TO]->(APEXRegion)
```

### Uporaba v praksi
Omogoča:
- mapiranje block → region
- bolj natančno dokumentiranje
- boljši impact analysis

---

## 8. ORATable

Predstavlja tabelo v bazi.

Lahko je:
- navadna transakcijska tabela
- master data tabela
- šifrant / codebook
- staging tabela

### Tipične relacije

```text
(OraForm)-[:USES_TABLE]->(ORATable)
(MigrationCase)-[:USES_TABLE]->(ORATable)
(APEXRegion)-[:USES_TABLE]->(ORATable)
(LegacyApplication)-[:USES_TABLE]->(ORATable)
```

---

### `isCodebook`
Pomeni:

> Ali je tabela šifrant / lookup / referenčna tabela?

Primer:
- statusi
- države
- valute
- tipi dokumentov

### `sharedAcrossApps`
Pomeni:

> Ali to tabelo uporablja več aplikacij?

Ta dva property-ja nista ista stvar.

#### Primeri

```text
isCodebook = true
sharedAcrossApps = false
```
Šifrant, ki ga uporablja samo ena aplikacija.

```text
isCodebook = true
sharedAcrossApps = true
```
Skupni šifrant, ki ga uporablja več aplikacij.

```text
isCodebook = false
sharedAcrossApps = true
```
Skupna tabela, ki ni klasičen šifrant.

---

## 9. OracleProcedure in OraclePackage

Predstavljata PL/SQL backend.

### Zakaj sta pomembna
Migracija Forms → APEX ni samo UI migracija.  
Velik del poslovne logike ostane v PL/SQL.

### Tipične relacije

```text
(OraForm)-[:CALLS]->(OracleProcedure)
(MigrationCase)-[:CALLS]->(OracleProcedure)
(APEXButton)-[:CALLS_PROCEDURE]->(OracleProcedure)
(OraclePackage)-[:HAS_PROCEDURE]->(OracleProcedure)
```

### Uporaba v praksi
To omogoča vprašanja:
- kateri gumb kliče to proceduro?
- katere migracije uporabljajo ta package?
- katera logika je shared?

---

## 10. APEXApp

Predstavlja APEX aplikacijo kot celoto.

### Tipične relacije

```text
(APEXApp)-[:HAS_PAGE]->(APEXPage)
```

To je vstopna točka v target svet.

---

## 11. APEXPage

Predstavlja eno stran v APEX-u.

To je glavni target artefakt migracije.

### Tipične relacije

```text
(APEXApp)-[:HAS_PAGE]->(APEXPage)
(OraForm)-[:MIGRATED_TO]->(APEXPage)
(MigrationCase)-[:TARGETS]->(APEXPage)
(APEXPage)-[:HAS_REGION]->(APEXRegion)
(APEXPage)-[:HAS_BUTTON]->(APEXButton)
```

### Razlika med `MIGRATED_TO` in `TARGETS`

#### `OraForm -[:MIGRATED_TO]-> APEXPage`
To je **trajna mapirna relacija legacy → target**.

#### `MigrationCase -[:TARGETS]-> APEXPage`
To je **kontekst migracijskega dela**.

Obe sta koristni in ne pomenita istega.

---

## 12. APEXRegion

Predstavlja region na strani, npr.:
- Interactive Grid
- Report
- Form region
- Static region

### Tipične relacije

```text
(APEXPage)-[:HAS_REGION]->(APEXRegion)
(OraBlock)-[:MIGRATED_TO]->(APEXRegion)
(APEXRegion)-[:USES_TABLE]->(ORATable)
(MigrationCase)-[:TARGETS]->(APEXRegion)
```

### Uporaba v praksi
Pomaga razumeti:
- kateri region predstavlja kateri block
- kateri region dela nad katero tabelo
- kje je logika prikaza podatkov

---

## 13. APEXButton

Predstavlja gumb na APEX strani.

### Tipične relacije

```text
(APEXPage)-[:HAS_BUTTON]->(APEXButton)
(APEXButton)-[:CALLS_PROCEDURE]->(OracleProcedure)
(APEXButton)-[:TRIGGERS_DA]->(APEXDynamicAction)
```

### Uporaba v praksi
Omogoča razumevanje flowa:
- kateri gumb sproži proces
- kateri gumb kliče proceduro
- kateri gumb je samo UI trigger

---

## 14. APEXDynamicAction in APEXDynamicActionStep

Predstavljata APEX client/AJAX vedenje.

### Tipične relacije

```text
(APEXButton)-[:TRIGGERS_DA]->(APEXDynamicAction)
(APEXDynamicAction)-[:HAS_ACTION]->(APEXDynamicActionStep)
```

### Uporaba v praksi
Pomaga razumeti:
- kaj se zgodi na klik
- ali se izvaja JavaScript
- ali se dela AJAX call
- ali se osveži region

---

## 15. MigrationCase

To je eden najpomembnejših node-ov.

Predstavlja **migracijsko enoto**.

Najpogosteje:
- ena forma = en MigrationCase

Ampak model tega ne zaklene, ker lahko kasneje pride do:
- več faz
- redesigna
- združevanja več form

### Pomembno
`MigrationCase` ni del produkcijske aplikacije.  
Je **kontekst dela, dokumentacije in odvisnosti**.

### Tipične relacije

```text
(MigrationCase)-[:BELONGS_TO_APP]->(LegacyApplication)
(MigrationCase)-[:SOURCE_FORM]->(OraForm)
(MigrationCase)-[:TARGETS]->(APEXPage)
(MigrationCase)-[:TARGETS]->(APEXRegion)
(MigrationCase)-[:USES_TABLE]->(ORATable)
(MigrationCase)-[:CALLS]->(OracleProcedure)
(MigrationCase)-[:HAS_HTML_DOC]->(DocumentationHTML)
(MigrationCase)-[:HAS_MD_DOC]->(DocumentationMD)
```

### Uporaba v praksi
To je najboljši “entry point” za:
- onboarding
- vprašanja o migraciji
- status
- dokumentacijo
- AI retrieval

---

## 16. DocumentationHTML

To je dokumentacija za človeka.

### Zakaj jo imeti
Ker je HTML:
- bolj pregleden
- bolj prijazen za onboarding
- primeren za zložljive sekcije, poudarke, kartice

### Tipične relacije

```text
(MigrationCase)-[:HAS_HTML_DOC]->(DocumentationHTML)
```

To je “human-facing” dokumentacija.

---

## 17. DocumentationMD

To je dokumentacija za sistem in AI.

### Zakaj je pomembna
Markdown je boljši za:
- verzioniranje
- chunking
- embeddinge
- full-text search
- GraphRAG

### Tipične relacije

```text
(MigrationCase)-[:HAS_MD_DOC]->(DocumentationMD)
(DocumentationMD)-[:HAS_SECTION]->(Section)
```

To je semantična osnova za AI sloj.

---

## 18. Section

Predstavlja logično sekcijo v MD dokumentu.

Primeri:
- Purpose
- Legacy Forms behavior
- APEX implementation
- Processes
- Business rules

### Tipične relacije

```text
(DocumentationMD)-[:HAS_SECTION]->(Section)
(Section)-[:HAS_CHUNK]->(Chunk)
```

### Uporaba v praksi
To omogoča, da AI ne dela nad celim dokumentom, ampak nad smiselno strukturiranimi deli.

---

## 19. Chunk

To je najmanjša AI retrieval enota.

Chunk je del besedila, ki ga:
- indeksiraš,
- embeddaš,
- uporabljaš za GraphRAG.

### Tipične relacije

```text
(Section)-[:HAS_CHUNK]->(Chunk)
(Chunk)-[:REFERS_TO]->(OraForm)
(Chunk)-[:REFERS_TO]->(OraBlock)
(Chunk)-[:DESCRIBES]->(APEXPage)
(Chunk)-[:DESCRIBES]->(APEXRegion)
(Chunk)-[:DESCRIBES]->(APEXButton)
(Chunk)-[:DESCRIBES]->(OracleProcedure)
```

### Uporaba v praksi
To omogoča:
- AI odgovore
- semantično iskanje
- odpiranje natančnega konteksta

---

## 20. Zakaj je model dober

Ta struktura omogoča odgovore na vprašanja:

- katera APEX stran nadomešča to formo?
- kateri region ustreza temu blocku?
- katera migracija je povezana s to stranjo?
- katera dokumentacija velja za to implementacijo?
- kateri shared šifrant uporabljata Reinsurance in Provizije?
- kateri gumb kliče to proceduro?
- kaj se bo verjetno pokvarilo, če spremenim ta šifrant?

To pomeni, da model ni uporaben samo za dokumentacijo,
ampak tudi za:
- impact analysis
- onboarding
- maintenance
- AI copilot scenarije

---

## 21. Zaključek

Predlagana Neo4j struktura ima naslednje glavne prednosti:

- jasno loči legacy, target in migracijski kontekst
- podpira ročni vnos in kasnejše bogatenje podatkov
- je skladna z InsightViewer zahtevami (`id_rc`, `projectName`)
- omogoča stabilen import z uporabo `key`
- podpira dokumentacijo za ljudi in AI
- je dobra osnova za GraphRAG

Najpomembnejši praktični koncepti so:

- `id_rc` kot glavni tehnični ID
- `projectName = 'APEX'`
- `key` kot logični identifikator tam, kjer ga znaš določiti
- `MigrationCase` kot osrednji kontekst migracije
- `DocumentationMD -> Section -> Chunk` kot AI plast
