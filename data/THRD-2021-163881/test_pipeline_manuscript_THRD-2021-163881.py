"""
Test Pipeline Manuscript - Sak THRD-2021-163881
Eiendomskjøp med lekkasjeproblemer - Fjellveien 42A, Stavanger

Manuscript struktur:
- Session 0: Prosjekt-initialisering
- Session 1: Initial interessekunngjøring (mai 2019)
- Session 2: Kjøpsavtale signert (juni 2019)  
- Session 3: Overtakelse og første problemer (juli-august 2019)
- Session 4: Problem eskalering (september 2019)
- Session 5: Advokat engasjeres & teknisk utredning (mars 2020)
"""

MANUSCRIPT: list[dict] = [
    # ==============================================================================
    # SESSION 0: PROSJEKT-INITIALISERING
    # Advokaten får instrukser fra kjøper om å følge saken
    # ==============================================================================
    {
        "session": 0,
        "session_name": "Prosjekt-initialisering",
        "user_input": """
        Jeg er advokat og representerer kjøperparet Anders og Berit Kristiansen i en 
        eiendomskjøpssak. De kjøpte en eiendom på Fjellveien 42A i Stavanger kommune 
        den 1. august 2019. 
        
        Vi er nå i mars 2020 og det har dukket opp flere problemer med eiendommen. 
        Jeg trenger din hjelp til å organisere saksinnholdet, identifisere de juridiske 
        problemstillingene, og vurdere mulige tiltak.
        
        Kan du hjelpe meg med å strukturere denne saken?
        """,
        "attachments": []
    },
    
    {
        "session": 0,
        "session_name": "Prosjekt-initialisering - Oppfølging",
        "user_input": """
        Hvilken informasjon trenger du fra klientene mine for å kunne gi dem god 
        rådgivning? Kan du lage en liste over dokumenter jeg bør samle inn?
        """,
        "attachments": []
    },
    
    {
        "session": 0,
        "session_name": "Prosjekt-initialisering - Juridisk ramme",
        "user_input": """
        Dette er en eiendomskjøpssak. Hvilke lovbestemmelser er mest relevante 
        for denne typen tvister? Gi meg en oversikt over avhendingsloven sine 
        sentrale paragrafer for kjøpersaken.
        """,
        "attachments": []
    },

    # ==============================================================================
    # SESSION 1: INITIAL INTERESSEKUNNGJØRING
    # Kjøper kontakter selger med spørsmål før kjøpsavtale undertegnes
    # ==============================================================================
    {
        "session": 1,
        "session_name": "Pre-avtale fase - Interessespørsmål",
        "user_input": """
        Her er den første eposten min med spørsmål som jeg stilte til selgeren 
        Carl Danielsen før vi undertegnet kjøpsavtalen. 
        
        Hvilke av disse spørsmålene bør jeg ha stilt oppfølging på hvis jeg hadde vært 
        advokaten allerede på dette stadiet?
        """,
        "attachments": [
            "fabricated/2019-05-12_01_epost_2019-05-12_spoersmaal_om_eiendom.txt"
        ]
    },
    
    {
        "session": 1,
        "session_name": "Pre-avtale fase - Selgers svar",
        "user_input": """
        Selger Carl sendte meg svar på spørsmålene mine. Les svaret hans - 
        er det noe som bør undersøkes nærmere? Er det noe han har unnlatt å svare på?
        """,
        "attachments": [
            "fabricated/2019-05-13_02_epost_2019-05-13_selgers_svar.txt"
        ]
    },

    {
        "session": 1,
        "session_name": "Pre-avtale fase - Salgsoppgave",
        "user_input": """
        Dette er salgsoppgaven som ble utarbeidet av eiendomsmegler 15. mai 2019. 
        
        Hva burde vi ha vært obs på her, spesielt knyttet til utleiedelen 
        og eventuell tidligere fukt- og lekkasjehistorikk?
        """,
        "attachments": [
            "fabricated/2019-05-15_00b_salgsoppgave_2019-05-15.txt"
        ]
    },
    
    {
        "session": 1,
        "session_name": "Pre-avtale fase - Analyse av utleiedel",
        "user_input": """
        Jeg ser at salgsoppgaven beskriver en utleiedel på ca. 40 kvm. 
        Hvilken dokumentasjon burde jeg kreve for å verifisere at denne er 
        lovlig utleid og godkjent?
        """,
        "attachments": []
    },

    {
        "session": 1,
        "session_name": "Pre-avtale fase - Kjøpskontrakt signering",
        "user_input": """
        Her er kjøpskontrakten som vi undertegnet 1. juni 2019. 
        
        Analyser betingelsene som gjelder mangelsansvar, 'som-den-er'-klausulen 
        og reklamasjonsfristene. Hva er vår juridiske posisjon basert på denne kontrakten?
        """,
        "attachments": [
            "fabricated/2019-06-01_00_kjøpskontrakt_2019-06-01.txt"
        ]
    },
    
    {
        "session": 1,
        "session_name": "Pre-avtale fase - Risikovurdering",
        "user_input": """
        Når jeg leser kontrakten ser jeg at det står 'som den er' salg i § 1. 
        Betyr det at vi ikke har noe mangelsansvar i det hele tatt? 
        Hva er rekkevidden av en slik klausul?
        """,
        "attachments": []
    },

    # ==============================================================================
    # SESSION 2: OVERTAKELSE OG FØRSTE PROBLEMER
    # Lekkasjen oppdages like før overtakelse
    # ==============================================================================
    {
        "session": 2,
        "session_name": "Overtakelse og første lekkasje",
        "user_input": """
        Like før overtakelse 1. august 2019 oppdaget selgeren en lekkasje i taket 
        over utleiedelen. Han sendte denne eposten den 15. juli 2019. 
        
        Hva burde jeg ha gjort juridisk på dette tidspunkt? Var det noe jeg burde 
        ha krevd før overtakelse?
        """,
        "attachments": [
            "fabricated/2019-07-15_03_epost_2019-07-15_varsling_lekkasje.txt"
        ]
    },
    
    {
        "session": 2,
        "session_name": "Overtakelse - Rettslige konsekvenser",
        "user_input": """
        Hvis selgeren kjente til denne lekkasjen før salget - men først oppdaget 
        den og meldte fra om den kort tid før overtakelse - hvilken betydning 
        har det for mangelsansvaret?
        """,
        "attachments": []
    },

    {
        "session": 2,
        "session_name": "Utbedring bekreftelse før overtakelse",
        "user_input": """
        Selgeren bekreftet 28. juli 2019 at lekkasjen var utbedret. 
        
        Hva burde jeg ha krevd av dokumentasjon eller inspeksjon før 
        overtakelsen ble godtatt?
        """,
        "attachments": [
            "fabricated/2019-07-28_04_epost_2019-07-28_utbedring_bekreftelse.txt"
        ]
    },
    
    {
        "session": 2,
        "session_name": "Overtakelse - Utsettelse?",
        "user_input": """
        Burde vi ha utsatt overtakelsen til etter at vi fikk dokumentert at 
        lekkasjen var ordentlig utbedret? Hva er risikoen ved å overta 
        eiendommen basert på selgers muntlige forsikring?
        """,
        "attachments": []
    },

    # ==============================================================================
    # SESSION 3: LEKKASJEN RECIDIVERS
    # Lekkasjen kommer tilbake kort etter overtakelse
    # ==============================================================================
    {
        "session": 3,
        "session_name": "Problem realiseres - Lekkasjen kommer tilbake",
        "user_input": """
        Bare 18 dager etter overtakelsen (1. august), den 18. august 2019, 
        oppdaget vi at lekkasjen var tilbake! 
        
        Her er eposten jeg sendte til selgeren. 
        
        Hva er vår juridiske stilling nå? Hvilke rettsmidler har vi? 
        Hva burde jeg ha gjort umiddelbart?
        """,
        "attachments": [
            "fabricated/2019-08-18_05_epost_2019-08-18_ny_lekkasje.txt"
        ]
    },
    
    {
        "session": 3,
        "session_name": "Reklamasjon - Formkrav",
        "user_input": """
        Må jeg sende en formell reklamasjon til selgeren nå, eller holder det 
        med eposten jeg allerede sendte? Hvilke formkrav gjelder for reklamasjon 
        ved eiendomskjøp?
        """,
        "attachments": []
    },
    
    {
        "session": 3,
        "session_name": "Reklamasjon - Bevaring av rettigheter",
        "user_input": """
        Jeg har sett at selgeren har flyttekostnader han vil kreve dekket. 
        Har vi her dokumentasjon på disse? Og hvis lekkasjen viser seg å være 
        mangel - kan vi kreve disse dekket?
        """,
        "attachments": [
            "fabricated/2019-06-30_85_kvitteringer_flyttekostnader_2019-06-30.txt"
        ]
    },
    
    {
        "session": 3,
        "session_name": "Reklamasjon - Tidslinje",
        "user_input": """
        Oppsummer tidslinjen så langt: Når ble lekkasjen først oppdaget? 
        Når ble den meldt utbedret? Når kom den tilbake? Dette er viktig 
        for å vurdere om selgeren har oppfylt sin utbedringplikt.
        """,
        "attachments": []
    },

    # ==============================================================================
    # SESSION 4: EKSPERTUTSENDELSE OG SKADEOMFANG
    # September 2019 - Uavhengig sakkyndig kartlegger omfattende skader
    # ==============================================================================
    {
        "session": 4,
        "session_name": "Ekspertutsendelse og skademål",
        "user_input": """
        Vi tok kontakt med en uavhengig takstmann og fikk utarbeidet en 
        skaderapport datert 10. september 2019. Denne avdekket at problemet 
        var LANGT mer alvorlig enn vi trodde.
        
        Analyser denne rapporten: Hva er de juridiske implikasjonene av disse funnene?
        Hva betyr det at problemet stammer fra mangler i selve betongdekkets konstruksjon?
        """,
        "attachments": [
            "fabricated/2019-09-10_06_rapport_2019-09-10_skaderapport_takst.txt"
        ]
    },
    
    {
        "session": 4,
        "session_name": "Ekspertvurdering - K2 rapport",
        "user_input": """
        I tillegg til hovedrapporten fikk vi en mer detaljert K2-rapport samme dag.
        Kan du lese denne og se om den gir ytterligere informasjon om problemets omfang?
        """,
        "attachments": [
            "fabricated/2019-09-10_06a_skaderapport_2019-09-10_K2.txt"
        ]
    },
    
    {
        "session": 4,
        "session_name": "Skjult vs åpenbar mangel",
        "user_input": """
        Basert på skaderapportene - var dette en skjult mangel? Kunne vi som 
        kjøpere ha oppdaget dette ved en vanlig befaring? Dette er vel viktig 
        for å vurdere om 'som-den-er'-klausulen beskytter selgeren?
        """,
        "attachments": []
    },
    
    {
        "session": 4,
        "session_name": "Årsakssammenheng",
        "user_input": """
        Rapporten nevner at søyleskoene har punktert membranen. Er dette noe 
        som oppstår over tid, eller er dette en feil som var der da bygget ble 
        oppført? Hvorfor er dette viktig juridisk?
        """,
        "attachments": []
    },
    
    {
        "session": 4,
        "session_name": "Estimert utbedringskostnad",
        "user_input": """
        Basert på rapporten - hva vil det koste å utbedre dette? Kan du gi 
        en grov estimering? Og hvordan påvirker kostnaden valget mellom 
        prisavslag, utbedring eller heving?
        """,
        "attachments": []
    },

    # ==============================================================================
    # SESSION 5: TEKNISK UTREDNING OG JURIDISK STRATEGI
    # Mars 2020 - Uavhengig byggingeniør kartlegger konstruksjonsmangel
    # ==============================================================================
    {
        "session": 5,
        "session_name": "Eiendomsgrense problem",
        "user_input": """
        Vi har nå (mai 2020) oppdaget at deler av tilbygget faktisk ligger 
        UTENFOR vår eiendomsgrense! Her er eposten der vi oppdaget dette.
        
        Hva betyr dette juridisk? Er dette en mangel? Kan vi kreve at 
        selgeren ordner dette?
        """,
        "attachments": [
            "fabricated/2020-05-08_08_epost_2020-05-08_eiendomsgrense_problem.txt"
        ]
    },
    
    {
        "session": 5,
        "session_name": "Dypdykk i teknisk problemstilling",
        "user_input": """
        Tilbake til mars 2020: Vi fikk utarbeidet en detaljert 
        teknisk rapport fra byggingeniør som bore inn i betongdekket og kartla 
        oppbyggingen.
        
        Her er rapporten fra 12. mars 2020. De fant at:
        - Det er INGEN bærebjelker i dekket (det skulle vært noen)
        - Dekket er tynnere enn godkjent standard
        - Materialtykkelsene er feil
        - Det finnes ikke dokumentasjon på utføring
        
        Hva betyr dette juridisk? Er dette et mangel vi kan fremsette krav om?
        Hva er våre handlingsalternativ nå?
        """,
        "attachments": [
            "fabricated/2020-03-12_07_rapport_2020-03-12_byggesoek_betongdekke.txt"
        ]
    },
    
    {
        "session": 5,
        "session_name": "Mangler - Sammenstilling",
        "user_input": """
        Så nå har vi altså:
        1. Lekkasje i betongdekket
        2. Betongdekket mangler bærebjelker og er feilkonstruert
        3. Deler av tilbygget ligger utenfor eiendomsgrensen
        
        Dette er jo FLERE mangler. Må vi vurdere disse hver for seg, eller 
        kan vi se dem samlet? Hva er prognosen for å heve hele kjøpet nå?
        """,
        "attachments": []
    },
    
    {
        "session": 5,
        "session_name": "Forbehold om heving",
        "user_input": """
        Vi sendte et formelt brev med forbehold om heving 19. mai 2020.
        Les dette brevet - er det juridisk korrekt utformet? Mangler vi noe?
        """,
        "attachments": [
            "fabricated/2020-05-19_09_brev_2020-05-19_forbehold_heving.txt"
        ]
    },
    
    {
        "session": 5,
        "session_name": "Kommunikasjon med motpart",
        "user_input": """
        Vi har vært i korrespondanse med kommunen om byggesøknaden for dekket.
        Her er spørsmålet vårt og deres svar. Hva forteller dette oss?
        """,
        "attachments": [
            "fabricated/2020-04-15_52_epost_2020-04-15_kommune_spoersmaal.txt",
            "fabricated/2020-04-28_53_epost_2020-04-28_kommune_svar.txt"
        ]
    },
    
    {
        "session": 5,
        "session_name": "Intern strategi",
        "user_input": """
        Vi hadde et internt strategimøte. Les notatet fra møtet - 
        er strategien vi har lagt fornuftig? Hva er risikoene?
        """,
        "attachments": [
            "fabricated/2020-05-10_54_notat_2020-05-10_intern_strategi.txt"
        ]
    },

    {
        "session": 5,
        "session_name": "Juridisk vurdering og strategi",
        "user_input": """
        Basert på alle dokumentene som nå er samlet - kontrakten, epostene, 
        og de tekniske rapportene fra september 2019 og mars 2020 - 
        gjør nå en helhetlig vurdering av:
        
        1. Hva er manglene ved eiendommen?
        2. Var disse manglene kjente eller burde kjennes av selgeren ved overtakelse?
        3. Hva er våre juridiske rettsmidler under avhendingsloven?
        4. Hva er prognosen for heving vs. prisavslag?
        5. Hva er estimert erstatningsomfang?
        
        Gi en strategivurdering for hvordan vi skal proceed.
        """,
        "attachments": [
            "fabricated/2019-06-01_00_kjøpskontrakt_2019-06-01.txt",
            "fabricated/2019-07-15_03_epost_2019-07-15_varsling_lekkasje.txt",
            "fabricated/2019-09-10_06_rapport_2019-09-10_skaderapport_takst.txt",
            "fabricated/2020-03-12_07_rapport_2020-03-12_byggesoek_betongdekke.txt"
        ]
    },
    
    {
        "session": 5,
        "session_name": "Påkostninger og tap",
        "user_input": """
        Klientene mine har hatt betydelige påkostninger på eiendommen etter kjøpet.
        Her er dokumentasjonen. Kan vi kreve disse dekket hvis vi hever kjøpet?
        """,
        "attachments": [
            "fabricated/2019-08-15_33_kvitteringer_paakostninger_2019-08-15.txt"
        ]
    },
    
    {
        "session": 5,
        "session_name": "Leieinntekter - Dokumentasjon",
        "user_input": """
        Vi har leid ut deler av eiendommen. Her er leieavtalene. 
        Hvordan påvirker dette en eventuell heving? Må vi tilbakebetale 
        leieinntektene hvis kjøpet heves?
        """,
        "attachments": [
            "fabricated/2019-08-10_35_leieavtaler_dokumentasjon_2019-08-10.txt"
        ]
    },
]

# ==============================================================================
# METADATA OG BRUK
# ==============================================================================

"""
BRUK AV MANUSKRIPTET:

For hver query i listen:
1. Les user_input
2. Last inn alle filer spesifisert i attachments
3. Send user_input + vedlegg til modellen
4. Registrer:
   - Input tokens
   - Output tokens  
   - Responstid
   - Faktorskettens nøyaktighet (hvis aktuelt)
   - Konsistens med tidligere svar

SESSIONS FORKLART:

Session 0: Baseline - Advokaten får instrukser (3 queries)
  → Tester modellens evne til å organisere kompleks informasjon
  → Tester kjennskap til juridisk ramme

Session 1: Pre-avtalefasen (mai-juni 2019) (6 queries)
  → Tester prediktiv analyse: Hva burde vært gjort?
  → Tester due diligence-vurdering
  → Tester forståelse av 'som-den-er'-salg

Session 2: Overtakelse og første problemer (juli 2019) (4 queries)
  → Tester respons på tidspress og umiddelbare juridiske vurderinger
  → Tester risikovurdering ved overtakelse
  → Tester oppfølgingsspørsmål og naturlig dialog

Session 3: Problemrealisering (august 2019) (4 queries)
  → Tester eskalering og identifikasjon av nye juridiske muligheter
  → Tester forståelse av reklamasjonsfrister og formkrav
  → Tester kronologisk hukommelse (tidslinje)

Session 4: Ekspertutsendelse (september 2019) (5 queries)
  → Tester tolking av teknisk dokumentasjon
  → Tester link mellom teknisk og juridisk analyse
  → Tester skjult vs åpenbar mangel-vurdering
  → Tester økonomisk estimering

Session 5: Dypdykk og strategi (mars-mai 2020) (9 queries)
  → Tester helhetlig saksanalyse
  → Tester strategibeskrivelse
  → Tester prognoseestimering
  → Tester multippel mangelvurdering (flere mangler samtidig)
  → Tester økonomisk tap-beregning


METRIKER TIL MÅLING:

1. Konsistens: Samme saksforhold konsistent beskrevet gjennom sessions?
2. Nøyaktighet: Juridisk korrekt tolking av avhendingsloven?
3. Hukommelse: Husk tidligere funn og innblikk fra tidligere queries?
4. Progresjon: Utvikler analysen seg når ny informasjon kommer?
5. Prioritering: Fokuserer på vesentlige juridiske spørsmål?
6. Naturlig dialog: Håndterer oppfølgingsspørsmål uten å miste kontekst?
7. Økonomisk forståelse: Kan estimere kostnader og økonomisk tap?
"""

if __name__ == "__main__":
    print(f"Testmanuskript: THRD-2021-163881")
    print(f"Totalt antall queries: {len(MANUSCRIPT)}")
    print(f"Sessions: {len(set(q['session'] for q in MANUSCRIPT))}")
    print()
    
    # Print session oversikt
    sessions = {}
    for query in MANUSCRIPT:
        session = query['session']
        if session not in sessions:
            sessions[session] = []
        sessions[session].append(query)
    
    for session_num in sorted(sessions.keys()):
        queries_in_session = sessions[session_num]
        print(f"Session {session_num}: {queries_in_session[0]['session_name'].split(' - ')[0]}")
        print(f"  Totalt {len(queries_in_session)} queries")
        
        total_attachments = sum(len(q['attachments']) for q in queries_in_session)
        unique_attachments = len(set(att for q in queries_in_session for att in q['attachments']))
        print(f"  Totalt {total_attachments} vedlegg ({unique_attachments} unike)")
        
        for i, query in enumerate(queries_in_session, 1):
            print(f"    {i}. {query['session_name']}")
            if query['attachments']:
                for att in query['attachments']:
                    print(f"       - {att}")
        print()
