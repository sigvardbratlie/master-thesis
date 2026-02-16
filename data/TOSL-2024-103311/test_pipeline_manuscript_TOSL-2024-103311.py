parts_map = {
    "parter": {
        "Stian Kristensen": "Andreas Nilsen",
        "Ellen Gunderson": "Berit Johansen",
        "Rebekka Nacera Bournane Nordgård": "Camilla Marie Hansen",
        "Rune Andre Nordgård": "Daniel Erik Hansen",
    },
    "selskaper": {
        "HDI Global Specialty SE": "Nordic Insurance Group SE",
        "SCOR Europe SE": "Euro Risk Solutions SE",
        "Newline Europe Versicherung AG": "Continental Cover AG",
        "Claims Link AS": "Insurance Partners AS",
        "Boinspect AS": "ProTakst AS",
        "Snare Boligvurdering AS": "ProTakst AS",
        "Tryg Forsikring": "Norsk Forsikring",
        "Advokatfirmaet SGB AS": "Advokatfirmaet Hansen & Co",
    },
    "advokater": {
        "Ketil Krohn Venås": "Erik Martinsen",
        "Linn Strand Bruvik": "Lisa Andreassen",
        "Bjørnar Solberg Brandtzæg": "Bjørn Svendsen",
        "Håvard Skallerud": "Henrik Sørensen",
    },
    "sakkyndige": {
        "Daniel Snare": "David Storvik",
        "Per Iver Strand": "Petter Iversen",
        "Truls Erik Stokker": "Tommy Eriksen",
        "Anders Ugland": "Anders Uleberg",
        "Magnus Hem": "Marius Holm",
        "Vidar Aarnes": "Viktor Arnesen",
        "Terje Karlsen": "Tor Kristoffersen",
        "Fredrik Evensen": "Frank Eliassen",
        "Halvor Pettersen": "Harald Pedersen",
    },
    "firmaer": {
        "Eiendomstakst 1": "Eiendomskontroll Nord",
        "Asker Takstforum AS": "Vest Takst AS",
        "Stand": "Takst & Vurdering",
        "Follo Boligtakst AS": "Sør Boligkontroll AS",
        "Aarnes Eiendom AS": "Arnesen Takst AS",
        "Vinderen Elektro": "Nordby Elektro",
        "Vinderen Bad og Våtrom": "Nordby Bad og VVS",
        "Fjellhamar Bygg": "Skogen Bygg",
        "Renova Design AS": "Moderne Bygg AS",
        "Multi-Fix": "AllFix",
        "Eriksen og Jensen AS": "Hansen og Olsen AS",
        "Elektro 365": "Elektro Komplett",
        "Viftrup og Pettersen": "Vindum og Pedersen",
    },
    "eiendom": {
        "Skjoldveien 2B": "Granveien 15B",
        "0881 OSLO": "0654 OSLO",
        "Ãs, Akershus": "Bærum, Akershus",
    },
    "andre_personer": {
        "Rui": "Roger"
}
}
MANUSCRIPT: list[dict] = [
    
    # ==============================================================================
    # SESSION 0: INITIALISERING
    # Februar 2024 - Advokaten mottar saken
    # ==============================================================================
    {
        "session": 0,
        "date": "2024-02-01",
        "session_name": "Prosjekt-initialisering",
        "user_input": """
        Jeg er advokat og har fått instrukser fra Andreas Nilsen og Berit Johansen.
        
        De kjøpte en enebolig på Granveien 15B i Oslo fra Camilla Marie Hansen og 
        Daniel Erik Hansen i august 2023 for kr 15,5 millioner. 
        Overtakelse var 11. november 2023.
        
        Eiendommen ble solgt med boligselgerforsikring gjennom Nordic Insurance Group SE.
        
        Etter overtakelse har de oppdaget en rekke alvorlige mangler: elektriske feil, 
        pipeproblemer, varmekabler, gulvproblemer, og mer.
        
        Jeg vedlegger alle relevante dokumenter fra salgsprosessen, overtakelsen, 
        første reklamasjoner og ekspertrapporter.
        
        Kan du hjelpe meg å strukturere denne saken og vurdere våre rettigheter?
        """,
        "attachments": ['./01_fabricated/2023-03-15_00a_salgsoppgave_2023-03-15.txt',
                        './01_fabricated/2023-03-22_00c_budkonferanse_2023-03-22.txt',
                        './01_fabricated/2023-12-28_09_rapport_Petter_Iversen_el_anlegg_2023-12-28.txt',
                        './01_fabricated/2023-03-30_13_tilstandsrapport_ProTakst_2023-03-30.txt',
                        './01_fabricated/2024-01-15_10_rapport_Tommy_Eriksen_1_2024-01-15.txt',
                        './01_fabricated/2024-01-15_18_svar_forsikring_første_reklamasjon_2024-01-15.txt',
                        './01_fabricated/2023-03-18_00b_visningsnotat_2023-03-18_21.txt',
                        './01_fabricated/2024-01-20_07_pristilbud_Nordby_Bad_Vaatrom_2024-01-20.txt',
                        './01_fabricated/2023-08-25_01_kjøpekontrakt_2023-08-25.txt',
                        './01_fabricated/2023-08-20_02_egenerklæring_selger_2023-08-20.txt',
                        './01_fabricated/2024-01-14_04_reklamasjon_2_2024-01-14.txt',
                        './01_fabricated/2023-03-20_00e_oppdragsbrev_takstmann_2023-03-20.txt',
                        './01_fabricated/2023-11-15_15_SMS_utveksling_2023-11-15.txt',
                        './01_fabricated/2023-12-11_03_reklamasjon_1_2023-12-11.txt',
                        './01_fabricated/2023-03-22_00d_meglers_oppfoelging_2023-03-22_08-25.txt'],
        "solution": ""
    },
    {
        "session": 0,
        "date": "2024-02-01",
        "session_name": "Initialisering",
        "user_input": """
        Gi meg en kort og konsis oppsummering av sakens faktiske bakgrunn og utvikling 
        så langt, basert på dokumentene jeg har lastet opp. 
        
        Fokuser på de viktigste hendelsene og problemstillingene. Hva er kjernen i saken?
        """,
        "attachments": [],
        "solution": ""
    },
    {
        "session": 0,
        "date": "2024-02-01",
        "session_name": "Initialisering",
        "user_input": """
        Dette er en eiendomskjøpssak med boligselgerforsikring. 
        
        Hvilke lovbestemmelser er mest relevante? Hva er forskjellen på å reklamere 
        til selger versus å fremme krav mot boligselgerforsikringen?
        """,
        "attachments": [],
        "solution": ""
    },
    {
        "session": 0,
        "date": "2024-02-01",
        "session_name": "Initialisering",
        "user_input": """
        Har selger gitt uriktige eller ufullstendige opplysninger? 
        Hva burde selger ha opplyst om som ikke er opplyst om?
        
        Er det noen forhold som burde vært undersøkt nærmere før kjøpet?
        """,
        "attachments": [],
        "solution": ""
    },
    {
        "session": 0,
        "date": "2024-02-01",
        "session_name": "Initialisering",
        "user_input": """
        Er manglene reklamert innenfor frister? 
        
        Hva er konsekvensen hvis noen av forholdene er reklamert for sent?
        """,
        "attachments": [],
        "solution": ""
    },

    # ==============================================================================
    # SESSION 1: REKLAMASJONER OG EKSPERTRAPPORTER
    # Februar-mars 2024
    # ==============================================================================
    {
        "session": 1,
        "date": "2024-02-20",
        "session_name": "Reklamasjoner og ekspertrapporter",
        "user_input": """
        Saken har utviklet seg. Se vedlagte nye rapporter, pristilbud, og svar 
        fra forsikringsselskapet.
        
        Vi har nå dokumentasjon på utbedringskostnadene og flere ekspertuttalelser.
        
        Hva er hovedfunnene i de nye rapportene? Hvor sterkt står vi nå?
        """,
        "attachments": [
            './01_fabricated/2024-01-15_06_pristilbud_Nordby_Elektro_2024-01-15.txt',
            './01_fabricated/2024-01-20_07_pristilbud_Nordby_Bad_Vaatrom_2024-01-20.txt',
            './01_fabricated/2024-01-25_08_pristilbud_Skogen_Bygg_2024-01-25.txt',
            './01_fabricated/2024-02-15_02_brev_oslo_brann_2024-02-15.txt',
            './01_fabricated/2024-02-15_19_svar_forsikring_reklamasjon_2_og_3_2024-02-15.txt',
            './01_fabricated/2024-02-19_10_pristilbud_nordby_varmekabler_2024-02-19.txt',
            './01_fabricated/2024-02-23_09_rapport_uleberg_2024-02-23.txt'
        ],
        "solution": ""
    },
    {
        "session": 1,
        "date": "2024-02-20",
        "session_name": "Reklamasjoner og ekspertrapporter",
        "user_input": """
        Oppsummer de totale utbedringskostnadene basert på pristilbudene vi har fått.
        
        Hva er hovedpostene? Hva er totalsummen?
        """,
        "attachments": [],
        "solution": ""
    },
    {
        "session": 1,
        "date": "2024-03-08",
        "session_name": "Reklamasjoner og ekspertrapporter",
        "user_input": """
        Det har dukket opp et nytt problem med gulvet. Se vedlagt epost fra 
        Vindum & Pedersen AS.
        
        Hva er problemet? Er dette en ny mangel vi må reklamere på?
        """,
        "attachments": [
            './01_fabricated/2024-03-08_03_epost_2024-03-08_vindum_pedersen_gulv.eml'
        ],
        "solution": ""
    },
    {
        "session": 1,
        "date": "2024-03-15",
        "session_name": "Reklamasjoner og ekspertrapporter",
        "user_input": """
        Hva er forsikringsselskapets standpunkt basert på svarene de har gitt så langt?
        
        Godtar de våre krav? Hva avviser de? Hva er begrunnelsen?
        """,
        "attachments": [],
        "solution": ""
    },

    # ==============================================================================
    # SESSION 2: FORLIKSFORHANDLINGER OG STEVNING
    # April-juni 2024
    # ==============================================================================
    {
        "session": 2,
        "date": "2024-05-01",
        "session_name": "Forliksforhandlinger og stevning",
        "user_input": """
        Vi har forsøkt å få til en minnelig løsning, men uten hell. 
        Se vedlagt korrespondanse.
        
        Hva er situasjonen nå? Bør vi stevne?
        """,
        "attachments": [
            './01_fabricated/2024-04-15_20_epost_kjoeper_oppfoelging_manglende_svar_2024-04-15.eml',
            './01_fabricated/2024-05-20_22_forliksforslag_minnelig_loesning_2024-05-20.txt',
            './01_fabricated/2024-05-27_21_epost_dialog_advokater_foer_stevning_2024-05-27.eml'
        ],
        "solution": ""
    },
    {
        "session": 2,
        "date": "2024-05-20",
        "session_name": "Forliksforhandlinger og stevning",
        "user_input": """
        Hva er et realistisk forlikskrav i denne saken? 
        
        Hva bør vi tilby i forlik, og hva er vår minsteakseptable løsning?
        """,
        "attachments": [],
        "solution": ""
    },
    {
        "session": 2,
        "date": "2024-06-20",
        "session_name": "Forliksforhandlinger og stevning",
        "user_input": """
        Forhandlingene har strandet. Vi må stevne.
        
        Lag meg et utkast til stevning basert på sakens dokumenter og utvikling. 
        
        Hvem skal stevnes? Hva skal påstanden være? Hva er kravet?
        """,
        "attachments": [],
        "solution": ""
    },
    {
        "session": 2,
        "date": "2024-06-29",
        "session_name": "Forliksforhandlinger og stevning",
        "user_input": """
        Se vedlagt stevningen som ble tatt ut 29. juni 2024.
        
        Er det noe som bør justeres eller legges til?
        """,
        "attachments": [
            './01_fabricated/2024-06-29_01_stevning_kjøper_2024-06-29.txt'
        ],
        "solution": ""
    },

    # ==============================================================================
    # SESSION 3: PROSESSFØRING
    # August-november 2024
    # ==============================================================================
    {
        "session": 3,
        "date": "2024-08-20",
        "session_name": "Prosessføring",
        "user_input": """
        Se vedlagt tilsvar fra selger og forsikringsselskapet.
        
        Hva er deres forsvar? Hva bestrides? Hva innrømmes?
        
        Hva er de viktigste svakhetene i deres argumentasjon?
        """,
        "attachments": [
            './01_fabricated/2024-08-15_02_tilsvar_selger_forsikring_2024-08-15.txt'
        ],
        "solution": ""
    },
    {
        "session": 3,
        "date": "2024-09-10",
        "session_name": "Prosessføring",
        "user_input": """
        Vi skal sende et prosesskriv med forlikstilbud før saken går videre.
        
        Lag meg et utkast til dette basert på motpartens tilsvar og vår stevning.
        """,
        "attachments": [],
        "solution": ""
    },
    {
        "session": 3,
        "date": "2024-09-12",
        "session_name": "Prosessføring",
        "user_input": """
        Se vedlagt prosesskrivet som ble sendt.
        
        Er argumentasjonen god nok? Er det noe som bør styrkes?
        """,
        "attachments": [
            './01_fabricated/2024-09-12_06_prosesskriv_forlikstilbud_2024-09-12.txt'
        ],
        "solution": ""
    },
    {
        "session": 3,
        "date": "2024-11-01",
        "session_name": "Prosessføring",
        "user_input": """
        Saken har utviklet seg videre. Se vedlagte nye dokumenter om kumulasjon, 
        takrapport, tilsvar fra takstmann, og tredje reklamasjon.
        
        Hva er status nå? Hvordan påvirker dette vår sak?
        """,
        "attachments": [
            './01_fabricated/2024-10-10_03_stevning_kumulasjon_2024-10-10.txt',
            './01_fabricated/2024-11-11_16_rapport_Marius_Holm_tak_2024-11-11.txt',
            './01_fabricated/2024-11-14_04_tilsvar_takstmann_tryg_2024-11-14.txt',
            './01_fabricated/2024-11-15_17_notat_samtale_AllFix_2024-11-15.txt',
            './01_fabricated/2024-11-22_05_reklamasjon_3_2024-11-22.txt',
            './01_fabricated/2024-11-22_07_tilleggsrapport_eriksen_2024-11-22.txt'
        ],
        "solution": ""
    },
    {
        "session": 3,
        "date": "2024-11-25",
        "session_name": "Prosessføring",
        "user_input": """
        Hva er de viktigste nye funnene i Marius Holm sin takrapport og 
        Tommy Eriksen sin tilleggsrapport?
        
        Styrker dette vår sak?
        """,
        "attachments": [],
        "solution": ""
    },
    {
        "session": 3,
        "date": "2024-11-30",
        "session_name": "Prosessføring",
        "user_input": """
        Basert på tilsvaret fra takstmannen - hvordan bør vi imøtegå deres argumenter?
        
        Hva er de svakeste punktene i deres forsvar?
        """,
        "attachments": [],
        "solution": ""
    },

    # ==============================================================================
    # SESSION 4: HOVEDFORHANDLING OG DOM
    # April-mai 2025
    # ==============================================================================
    {
        "session": 4,
        "date": "2025-04-01",
        "session_name": "Hovedforhandling og dom",
        "user_input": """
        Hovedforhandlingen nærmer seg. Se vedlagt tilleggsrapport fra Arnesen.
        
        Hva er konklusjonen i denne rapporten? Hvordan påvirker den sakens styrke?
        """,
        "attachments": [
            './01_fabricated/2025-04-03_08_tilleggsrapport_arnesen_2025-04-03.txt'
        ],
        "solution": ""
    },
    {
        "session": 4,
        "date": "2025-04-05",
        "session_name": "Hovedforhandling og dom",
        "user_input": """
        Basert på alle dokumentene fra salgsprosessen til nå - hva er de 3-5 viktigste 
        punktene jeg må få frem i hovedforhandlingen?
        
        Hva er våre sterkeste argumenter? Hva er våre svakeste punkter?
        """,
        "attachments": [],
        "solution": ""
    },
    {
        "session": 4,
        "date": "2025-04-07",
        "session_name": "Hovedforhandling og dom",
        "user_input": """
        Lag meg utkast til sluttinnlegg for hovedforhandlingen.
        
        Strukturer det slik at det dekker alle våre påstander og bevis på en 
        overbevisende måte.
        """,
        "attachments": [],
        "solution": ""
    },
    {
        "session": 4,
        "date": "2025-04-25",
        "session_name": "Hovedforhandling og dom",
        "user_input": """
        Hovedforhandlingen er gjennomført. Se vedlagte dokumenter fra rettssaken.
        
        Hva skjedde under hovedforhandlingen?
        """,
        "attachments": [
            './01_fabricated/2025-04-09_05_sluttinnlegg_kjoper_2025-04-09.txt',
            './01_fabricated/2025-04-23_05_rettsbok_utdrag_2025-04-23_25.txt',
            './01_fabricated/2025-04-24_01_befaringsprotokoll_2025-04-24.txt'
        ],
        "solution": ""
    },
    {
        "session": 4,
        "date": "2025-05-14",
        "session_name": "Hovedforhandling og dom",
        "user_input": """
        Se vedlagt dom fra Oslo Tingrett datert 14. mai 2025.
        
        Hva ble utfallet? Vant vi frem? Hva var begrunnelsen?
        """,
        "attachments": [
            './01_fabricated/2025-05-14_04_dom_2025-05-14.txt'
        ],
        "solution": ""
    },
]
