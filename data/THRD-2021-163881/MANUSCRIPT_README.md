# Test Pipeline Manuscript - THRD-2021-163881

## Oversikt

Dette manuskriptet fungerer som en test pipeline for oppgaven din. Det inneholder 10 queries som skal sendes til språkmodellen, organisert i 6 naturlige sessions som følger saken kronologisk.

**Saken**: Eiendomskjøp med alvorlige lekkasje- og konstruksjonsmangel på Fjellveien 42A, Stavanger.

**Tidsperiode**: Mai 2019 - Mars 2020 (fra første henvendelse til advokaten til teknisk utredning er avsluttet)

## Sessions

### Session 0: Prosjekt-initialisering
- **Når**: Mars 2020
- **Kontekst**: Advokaten får instrukser fra kjøperparet
- **Hensikt**: Test av kontekstorganisering og baseline forståelse
- **Queries**: 1

### Session 1: Pre-avtale fase (mai-juni 2019)
- **Hendelse**: Spørsmål til selger, salgsoppgave, kjøpsavtale signering
- **Hensikt**: Test av due diligence-analyse og prediktiv evaluering
- **Queries**: 3

### Session 2: Overtakelse og første problemer (juli 2019)
- **Hendelse**: Lekkasje oppdages før overtakelse, utbedring bekreftelse
- **Hensikt**: Test av respons på tidspress og juridiske rettsmidler
- **Queries**: 2

### Session 3: Problemrealisering (august 2019)
- **Hendelse**: Lekkasjen kommer tilbake kort etter overtakelse
- **Hensikt**: Test av eskalering og nye juridiske muligheter
- **Queries**: 1

### Session 4: Ekspertutsendelse (september 2019)
- **Hendelse**: Sakkyndig takstmann avdekker omfattende skader
- **Hensikt**: Test av tolking av teknisk dokumentasjon
- **Queries**: 1

### Session 5: Dypdykk og strategi (mars 2020)
- **Hendelse**: Byggingeniør bore inn i dekket, dypere analyse av problemet
- **Hensikt**: Test av helhetlig saksanalyse og strategibeskrivelse
- **Queries**: 2

## Struktur av queries

Hver query er en dictionary med:
```python
{
    "session": int,                    # Sesjonsnummer (0-5)
    "session_name": str,               # Navn på fasen
    "user_input": str,                 # Spørsmål/instruksjon til modellen
    "attachments": list[str]           # Filstier til dokumenter (relative paths)
}
```

## Bruk av manuskriptet

### 1. Last inn data
```python
from test_pipeline_manuscript_THRD_2021_163881 import MANUSCRIPT

for query in MANUSCRIPT:
    session = query['session']
    user_input = query['user_input']
    attachments = query['attachments']
    
    # Din test-logikk her
```

### 2. For hver query, gjør:
1. Les `user_input`
2. Last inn alle filer fra `attachments` (gjør relative paths absolutte)
3. Send til modellen med kontekst fra tidligere queries i samme session
4. Registrer respons

### 3. Metriker å måle

- **Konsistens**: Samme saksforhold konsistent beskrevet gjennom sessions?
- **Nøyaktighet**: Juridisk korrekt tolking av avhendingsloven § 3-9, § 4-13 etc.?
- **Hukommelse**: Husk tidligere funn når nye dokumenter presenteres?
- **Progresjon**: Utvikler analysen seg når ny informasjon kommer (tidsserier)?
- **Prioritering**: Fokuserer på vesentlige juridiske spørsmål?
- **Erstatning**: Kan den estimere skadeerstatning basert på funn?

## Kritiske juridiske konsepter i saken

- **Avhendingsloven § 3-9**: "Som-den-er"-salg
- **Avhendingsloven § 4-13**: Heving av kjøp
- **Avhendingsloven § 4-19**: Reklamasjonsfrist
- **Mangelbegrepet**: Hva regnes som mangel etter norsk rett?
- **Skjult mangel**: Lekkasjen var ikke åpenbar ved overtakelse

## Dokumenter brukt

Alle dokumenter er lokalisert i:
```
/Users/sigvardbratlie/Documents/Projects/master-thesis/data/THRD-2021-163881/fabricated/
```

Totalt 8 unike dokumenter:
1. Spørsmål til selger (12.mai 2019)
2. Salgsoppgave (15.mai 2019)
3. Kjøpskontrakt (1.juni 2019)
4. Lekkasje melding (15.juli 2019)
5. Utbedring bekreftelse (28.juli 2019)
6. Lekkasje recidiver (18.august 2019)
7. Takst-/skaderapport (10.september 2019)
8. Teknisk rapport betongdekke (12.mars 2020)

## Forventet bruk i oppgaven

Dette manuskriptet skal brukes til å:

1. **Teste FactSheet-modellen**: Opprettholder modellen konsistent forståelse av saksforholdet gjennom 10 queries?
2. **Måle kontekstbevaring**: Faller nøyaktigheten når mer informasjon akkumuleres?
3. **Sammenligne modeller**: GPT-4 vs Claude vs Gemini
4. **EvaluereRAG vs FactSheet**: Er eksplisitt state management bedre enn standard RAG?

## Teknisk struktur

Filen er en vanlig Python-fil som kan importeres eller kjøres direkte.

```bash
python3 test_pipeline_manuscript_THRD_2021_163881.py
```

Gir output:
```
Testmanuskript: THRD-2021-163881
Totalt antall queries: 10
Sessions: 6
[detaljert listing av hver session]
```
