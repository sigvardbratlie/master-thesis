"""
Test Pipeline Manuscript - Sak TOSL-2024-103311
Eiendomskjøp med elektriske og bygningstekniske mangler - Granveien 15B, Oslo

Manuscript struktur:
- Session 0: Prosjekt-initialisering
- Session 1: Salgsoppgave og visning (mars 2023)
- Session 2: Budkonferanse og kjøpsavtale (august 2023)
- Session 3: Overtakelse og første problemer (november-desember 2023)
- Session 4: Ekspertutsendelse og reklamasjon (desember 2023 - februar 2024)
- Session 5: Forliksforhandlinger og stevning (mai-juni 2024)
- Session 6: Prosessskriv og forberedelser til rettssak (september 2024-januar 2025)
"""

anomymization_dict = {
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
    # SESSION 0: PROSJEKT-INITIALISERING
    # Advokaten får instrukser fra kjøperparet
    # ==============================================================================
    {
        "session": 0,
        "session_name": "Prosjekt-initialisering",
        "user_input": """
        Jeg er advokat og har fått instrukser fra Andreas Nilsen og Berit Johansen.
        De kjøpte en enebolig på Granveien 15B i Oslo i august 2023 for kr 15,5 millioner.
        
        Etter overtakelse 11. november 2023 har de oppdaget en rekke alvorlige 
        mangler ved eiendommen - elektriske feil, pipe-problemer, og mer.
        
        Vi er nå i januar 2024. De har allerede sendt én reklamasjon i desember 2023,
        og forsikringsselskapet har svart.
        
        Hva trenger jeg for å vurdere saken deres?
        """,
        "attachments": []
    },
    
    {
        "session": 0,
        "session_name": "Prosjekt-initialisering - Juridisk ramme",
        "user_input": """
        Dette er en eiendomskjøpssak der eiendommen ble solgt med boligselgerforsikring.
        Hvilke lovregler gjelder her? Hva er forskjellen på reklamasjon til selger
        vs. krav mot boligselgerforsikringen?
        """,
        "attachments": []
    },
    
    {
        "session": 0,
        "session_name": "Prosjekt-initialisering - Dokumentasjonsoversikt",
        "user_input": """
        Hvilke dokumenter bør jeg samle inn for å vurdere om vi har grunnlag for
        å kreve erstatning? Tenk på både dokumenter fra salget og dokumenter
        fra reklamasjonsprosessen.
        """,
        "attachments": []
    },

    # ==============================================================================
    # SESSION 1: SALGSOPPGAVE OG VISNING
    # Mars 2023 - Pre-avtale fase
    # ==============================================================================
    {
        "session": 1,
        "session_name": "Salgsoppgave - Første analyse",
        "user_input": """
        Her er salgsoppgaven fra 15. mars 2023. Eiendommen er en enebolig fra 1931
        som har vært oppgradert i perioden 2017-2022.
        
        Hva burde klientene mine ha vært obs på i denne fasen? Hvilke spørsmål
        burde de stilt megler?
        """,
        "attachments": [
            "01_fabricated/2023-03-15_00a_salgsoppgave_2023-03-15.txt"
        ]
    },
    
    {
        "session": 1,
        "session_name": "Visningsnotat",
        "user_input": """
        Her er notatet fra visningen 18. mars 2023. Klientene mine var på visning
        og fikk omvisning av megler og selger.
        
        Er det noe i visningsnotatet som burde vært undersøkt nærmere?
        """,
        "attachments": [
            "01_fabricated/2023-03-18_00b_visningsnotat_2023-03-18_21.txt"
        ]
    },
    
    {
        "session": 1,
        "session_name": "Tilstandsrapport - Gjennomgang",
        "user_input": """
        Tilstandsrapporten ble utarbeidet av ProTakst AS ved David Storvik 30. mars 2023.
        
        Les rapporten og gi meg en vurdering av:
        1. Hva er hovedfunnene?
        2. Hvilke advarsler gis?
        3. Er det noe rapporten IKKE dekker som kunne vært problematisk?
        """,
        "attachments": [
            "01_fabricated/2023-03-30_13_tilstandsrapport_ProTakst_2023-03-30.txt"
        ]
    },
    
    {
        "session": 1,
        "session_name": "Tilstandsrapport - Oppfølging",
        "user_input": """
        Tilstandsrapporten nevner flere oppgraderinger i 2017-2021:
        - Nordlandgulv og el-arbeider (2017)
        - Bad 2. etasje rehabilitert (2020/2021)
        - Ny taktekking (2021)
        
        Burde klientene mine krevd dokumentasjon på disse arbeidene før de kjøpte?
        Hva er risikoen ved å ikke gjøre det?
        """,
        "attachments": []
    },

    # ==============================================================================
    # SESSION 2: BUDKONFERANSE OG KJØPSAVTALE
    # August 2023
    # ==============================================================================
    {
        "session": 2,
        "session_name": "Budkonferanse",
        "user_input": """
        Her er notatet fra budkonferansen 22. mars 2023. Klientene mine la inn bud.
        
        Hva skjedde i budkonferansen? Var det andre interessenter?
        """,
        "attachments": [
            "01_fabricated/2023-03-22_00c_budkonferanse_2023-03-22.txt"
        ]
    },
    
    {
        "session": 2,
        "session_name": "Meglers oppfølging",
        "user_input": """
        Etter budkonferansen sendte megler denne oppfølgingseposten.
        
        Hva er meglers ansvar i denne fasen? Burde de ha gitt mer informasjon?
        """,
        "attachments": [
            "01_fabricated/2023-03-22_00d_meglers_oppfoelging_2023-03-22_08-25.txt"
        ]
    },
    
    {
        "session": 2,
        "session_name": "Egenerklæring fra selger",
        "user_input": """
        Før kontraktsinngåelse fikk klientene mine selgers egenerklæring datert 20. august 2023.
        
        Analyser denne - hva opplyser selger om? Er det noe som mangler?
        Spesielt interessant: Hva sier selger om elektriske installasjoner?
        """,
        "attachments": [
            "01_fabricated/2023-08-20_02_egenerklæring_selger_2023-08-20.txt"
        ]
    },
    
    {
        "session": 2,
        "session_name": "Dialog med selger",
        "user_input": """
        Det var noe epostutveksling mellom kjøper og selger 20-21. august.
        
        Les disse epostene - hva spurte klientene mine om, og hva svarte selger?
        """,
        "attachments": [
            "01_fabricated/2023-08-20_11_epost_kjoeper_til_selger_2023-08-20.txt",
            "01_fabricated/2023-08-21_12_epost_selger_til_kjoeper_2023-08-21.txt"
        ]
    },
    
    {
        "session": 2,
        "session_name": "Kjøpskontrakt - Analyse",
        "user_input": """
        Kjøpskontrakten ble signert 25. august 2023 med overtakelse 11. november 2023.
        
        Analyser kontrakten:
        1. Hva er kjøpesummen?
        2. Er det boligselgerforsikring?
        3. Hvilke dokumenter er vedlagt?
        4. Hva betyr det at eiendommen selges med boligselgerforsikring?
        """,
        "attachments": [
            "01_fabricated/2023-08-25_01_kjøpekontrakt_2023-08-25.txt"
        ]
    },

    # ==============================================================================
    # SESSION 3: OVERTAKELSE OG FØRSTE PROBLEMER
    # November-desember 2023
    # ==============================================================================
    {
        "session": 3,
        "session_name": "Overtakelse - SMS-utveksling",
        "user_input": """
        Rundt overtakelsen 11-15. november 2023 var det SMS-utveksling mellom
        partene. Hva snakket de om?
        """,
        "attachments": [
            "01_fabricated/2023-11-15_15_SMS_utveksling_2023-11-15.txt"
        ]
    },
    
    {
        "session": 3,
        "session_name": "Første reklamasjon - Elektrisk anlegg",
        "user_input": """
        11. desember 2023 sendte jeg første reklamasjon på vegne av klientene mine.
        Hovedproblemet er elektriske avvik som ble oppdaget av elektroingeniør.
        
        Les reklamasjonen - hva er hovedkravene? Hvilke mangler reklameres det på?
        """,
        "attachments": [
            "01_fabricated/2023-12-11_03_reklamasjon_1_2023-12-11.txt"
        ]
    },
    
    {
        "session": 3,
        "session_name": "Elektro-rapport",
        "user_input": """
        Sammen med reklamasjonen vedla vi rapport fra elektroingeniør Petter Iversen
        datert 28. desember 2023.
        
        Hva er de viktigste funnene i denne rapporten? Hvor alvorlige er avvikene?
        """,
        "attachments": [
            "01_fabricated/2023-12-28_09_rapport_Petter_Iversen_el_anlegg_2023-12-28.txt"
        ]
    },

    # ==============================================================================
    # SESSION 4: EKSPERTUTSENDELSE OG VIDERE REKLAMASJONER
    # Januar-februar 2024
    # ==============================================================================
    {
        "session": 4,
        "session_name": "Reklamasjonsrapport Tommy Eriksen",
        "user_input": """
        I januar 2024 engasjerte vi byggingeniør Tommy Eriksen fra Vest Takst AS
        til å vurdere manglene. Hans rapport kom 15. januar 2024.
        
        Hva er hovedfunnene i denne rapporten? Hva sier han om:
        - Pipen i 2. etasje?
        - Varmekabler?
        - Andre forhold?
        """,
        "attachments": [
            "01_fabricated/2024-01-15_10_rapport_Tommy_Eriksen_1_2024-01-15.txt"
        ]
    },
    
    {
        "session": 4,
        "session_name": "Pristilbud - Kostnadsestimering",
        "user_input": """
        Vi fikk inn pristilbud fra flere firma for å dokumentere utbedringskostnadene.
        
        Kan du oppsummere kostnadene basert på disse pristilbudene:
        - Nordby Elektro
        - Nordby Bad & Våtrom
        - Skogen Bygg
        """,
        "attachments": [
            "01_fabricated/2024-01-15_06_pristilbud_Nordby_Elektro_2024-01-15.txt",
            "01_fabricated/2024-01-20_07_pristilbud_Nordby_Bad_Vaatrom_2024-01-20.txt",
            "01_fabricated/2024-01-25_08_pristilbud_Skogen_Bygg_2024-01-25.txt"
        ]
    },
    
    {
        "session": 4,
        "session_name": "Forsikringsselskapets svar",
        "user_input": """
        15. januar 2024 kom forsikringsselskapets svar på vår første reklamasjon.
        
        Hva er deres standpunkt? Godtar de våre krav? Avviser de noe?
        """,
        "attachments": [
            "01_fabricated/2024-01-15_18_svar_forsikring_første_reklamasjon_2024-01-15.txt"
        ]
    },
    
    {
        "session": 4,
        "session_name": "Andre reklamasjon",
        "user_input": """
        Vi sendte en andre reklamasjon 14. januar 2024 med ytterligere krav.
        
        Hva er nytt i denne reklamasjonen sammenlignet med den første?
        """,
        "attachments": [
            "01_fabricated/2024-01-14_04_reklamasjon_2_2024-01-14.txt"
        ]
    },
    
    {
        "session": 4,
        "session_name": "Brann og redningsetaten",
        "user_input": """
        Oslo Brann- og redningsetat kom med et brev 15. februar 2024 om pipen.
        
        Hva sier de? Hvordan styrker dette vår sak?
        """,
        "attachments": [
            "01_fabricated/2024-02-15_02_brev_oslo_brann_2024-02-15.txt"
        ]
    },
    
    {
        "session": 4,
        "session_name": "Forsikringssvar - Reklamasjon 2 og 3",
        "user_input": """
        15. februar 2024 kom forsikringsselskapets svar på reklamasjon 2 og 3.
        
        Hva er deres standpunkt nå? Ser du en utvikling i deres svar?
        """,
        "attachments": [
            "01_fabricated/2024-02-15_19_svar_forsikring_reklamasjon_2_og_3_2024-02-15.txt"
        ]
    },
    
    {
        "session": 4,
        "session_name": "Ytterligere pristilbud",
        "user_input": """
        Vi fikk også pristilbud for varmekabler fra Nordby.
        
        Hva er kostnaden her? Hvordan bygger dette opp totalkravet?
        """,
        "attachments": [
            "01_fabricated/2024-02-19_10_pristilbud_nordby_varmekabler_2024-02-19.txt"
        ]
    },
    
    {
        "session": 4,
        "session_name": "Uleberg-rapport",
        "user_input": """
        23. februar 2024 fikk vi en rapport fra Uleberg.
        
        Hva omhandler denne rapporten? Hva er konklusjonene?
        """,
        "attachments": [
            "01_fabricated/2024-02-23_09_rapport_uleberg_2024-02-23.txt"
        ]
    },
    
    {
        "session": 4,
        "session_name": "Gulvproblematikk",
        "user_input": """
        I mars 2024 dukket det opp et nytt problem med gulvet (Nordlandgulv).
        Her er en epost fra Vindum & Pedersen AS.
        
        Hva er problemet? Er dette et nytt mangel vi må reklamere på?
        """,
        "attachments": [
            "01_fabricated/2024-03-08_03_epost_2024-03-08_vindum_pedersen_gulv.txt"
        ]
    },

    # ==============================================================================
    # SESSION 5: FORLIKSFORHANDLINGER OG STEVNING
    # April-juni 2024
    # ==============================================================================
    {
        "session": 5,
        "session_name": "Oppfølging - Manglende svar",
        "user_input": """
        15. april 2024 sendte jeg en oppfølgingsepost da vi ikke hadde fått tilfredsstillende
        svar fra motparten.
        
        Hva krever jeg i denne eposten? Hva er fristen?
        """,
        "attachments": [
            "01_fabricated/2024-04-15_20_epost_kjoeper_oppfoelging_manglende_svar_2024-04-15.txt"
        ]
    },
    
    {
        "session": 5,
        "session_name": "Forliksforslag",
        "user_input": """
        20. mai 2024 la jeg frem et forliksforslag med en minnelig løsning.
        
        Hva tilbyr vi? Hva er våre krav? Er dette et rimelig forslag?
        """,
        "attachments": [
            "01_fabricated/2024-05-20_22_forliksforslag_minnelig_loesning_2024-05-20.txt"
        ]
    },
    
    {
        "session": 5,
        "session_name": "Dialog mellom advokater",
        "user_input": """
        27. mai 2024 var det dialog mellom meg og motpartens advokat før stevning.
        
        Hva er tonen i dialogen? Hva er de uenige om?
        """,
        "attachments": [
            "01_fabricated/2024-05-27_21_epost_dialog_advokater_foer_stevning_2024-05-27.txt"
        ]
    },
    
    {
        "session": 5,
        "session_name": "Stevning - Utarbeidelse",
        "user_input": """
        29. juni 2024 tok ut stevning til Oslo Tingrett.
        
        Les stevningen:
        1. Hvem er saksøkt?
        2. Hva er påstanden?
        3. Hva er de viktigste rettsgrunnlagene?
        4. Hva er kravet i kroner?
        """,
        "attachments": [
            "01_fabricated/2024-06-29_01_stevning_kjøper_2024-06-29.txt"
        ]
    },

    # ==============================================================================
    # SESSION 6: PROSESSSKRIV OG RETTSSAK
    # September 2024 - mai 2025
    # ==============================================================================
    {
        "session": 6,
        "session_name": "Tilsvar fra saksøkte",
        "user_input": """
        15. august 2024 kom tilsvaret fra selger og forsikringsselskapet.
        
        Hva er deres forsvar? Hva bestrides? Hva innrømmes?
        """,
        "attachments": [
            "01_fabricated/2024-08-15_02_tilsvar_selger_forsikring_2024-08-15.txt"
        ]
    },
    
    {
        "session": 6,
        "session_name": "Prosesskriv - Forlikstilbud",
        "user_input": """
        12. september 2024 sendte vi et prosesskriv med forlikstilbud.
        
        Hva tilbyr vi nå? Har kravet endret seg siden stevningen?
        """,
        "attachments": [
            "01_fabricated/2024-09-12_06_prosesskriv_forlikstilbud_2024-09-12.txt"
        ]
    },
    
    {
        "session": 6,
        "session_name": "Stevning om kumulasjon",
        "user_input": """
        10. oktober 2024 tok ut en stevning om kumulasjon (sammenslåing av saker).
        
        Hva betyr dette? Hvorfor vil vi ha kumulasjon?
        """,
        "attachments": [
            "01_fabricated/2024-10-10_03_stevning_kumulasjon_2024-10-10.txt"
        ]
    },
    
    {
        "session": 6,
        "session_name": "Tredje reklamasjon",
        "user_input": """
        22. november 2024 sendte vi en tredje reklamasjon.
        
        Hva er nytt i denne reklamasjonen? Hvorfor kommer den så sent?
        """,
        "attachments": [
            "01_fabricated/2024-11-22_05_reklamasjon_3_2024-11-22.txt"
        ]
    },
    
    {
        "session": 6,
        "session_name": "Takrapport",
        "user_input": """
        11. november 2024 fikk vi en rapport fra Marius Holm om taket.
        
        Hva er funnene? Er dette et nytt mangel?
        """,
        "attachments": [
            "01_fabricated/2024-11-11_16_rapport_Marius_Holm_tak_2024-11-11.txt"
        ]
    },
    
    {
        "session": 6,
        "session_name": "Tilsvar fra takstmann",
        "user_input": """
        14. november 2024 kom tilsvar fra den opprinnelige takstmannen (ProTakst).
        
        Hvordan forsvarer takstmannen seg? Hva mener de om påstandene våre?
        """,
        "attachments": [
            "01_fabricated/2024-11-14_04_tilsvar_takstmann_tryg_2024-11-14.txt"
        ]
    },
    
    {
        "session": 6,
        "session_name": "Notat - AllFix samtale",
        "user_input": """
        15. november 2024 hadde vi en samtale med AllFix (som gjorde takarbeidet i 2021).
        
        Hva sa de? Hvordan kan dette brukes i saken?
        """,
        "attachments": [
            "01_fabricated/2024-11-15_17_notat_samtale_AllFix_2024-11-15.txt"
        ]
    },
    
    {
        "session": 6,
        "session_name": "Tilleggsrapport Eriksen",
        "user_input": """
        22. november 2024 kom en tilleggsrapport fra Tommy Eriksen.
        
        Hva er nytt i denne rapporten? Styrker den vår sak?
        """,
        "attachments": [
            "01_fabricated/2024-11-22_07_tilleggsrapport_eriksen_2024-11-22.txt"
        ]
    },
    
    {
        "session": 6,
        "session_name": "Helhetlig saksvurdering",
        "user_input": """
        Basert på alle dokumentene vi nå har samlet - fra salgsoppgaven i mars 2023
        til de siste rapportene i november 2024 - gi meg en helhetlig vurdering:
        
        1. Hva er de viktigste manglene ved eiendommen?
        2. Hvor sterke er våre rettskrav?
        3. Hva er svakhetene i vår sak?
        4. Hva er den totale erstatningen vi krever?
        5. Hva er prognosen for å vinne frem i retten?
        """,
        "attachments": [
            "01_fabricated/2023-03-30_13_tilstandsrapport_ProTakst_2023-03-30.txt",
            "01_fabricated/2024-01-15_10_rapport_Tommy_Eriksen_1_2024-01-15.txt",
            "01_fabricated/2023-12-28_09_rapport_Petter_Iversen_el_anlegg_2023-12-28.txt",
            "01_fabricated/2024-06-29_01_stevning_kjøper_2024-06-29.txt"
        ]
    },
    
    {
        "session": 6,
        "session_name": "Tilleggsrapport Arnesen",
        "user_input": """
        3. april 2025 kom en tilleggsrapport fra Arnesen.
        
        Hva omhandler denne? Hvordan påvirker den sakens styrke?
        """,
        "attachments": [
            "01_fabricated/2025-04-03_08_tilleggsrapport_arnesen_2025-04-03.txt"
        ]
    },
    
    {
        "session": 6,
        "session_name": "Prosesskriv - Oppsummering",
        "user_input": """
        Nå nærmer vi oss hovedforhandlingen. Basert på alle dokumentene,
        rapportene og prosessskriftene - hva er de 3-5 viktigste punktene
        jeg må få frem i retten?
        
        Hva er våre sterkeste argumenter?
        """,
        "attachments": []
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
  → Tester forståelse av boligselgerforsikring vs vanlig kjøp

Session 1: Salgsoppgave og visning (mars 2023) (4 queries)
  → Tester prediktiv analyse av salgsdokumentasjon
  → Tester kritisk lesning av tilstandsrapport
  → Tester identifikasjon av red flags

Session 2: Budkonferanse og kjøpsavtale (august 2023) (5 queries)
  → Tester forståelse av meglers ansvar
  → Tester analyse av egenerklæring
  → Tester vurdering av boligselgerforsikring

Session 3: Overtakelse og første problemer (november-desember 2023) (3 queries)
  → Tester reklamasjonsteknikk
  → Tester tolking av tekniske rapporter (elektrisk anlegg)
  → Tester prioritering av mangler

Session 4: Ekspertutsendelse og videre reklamasjoner (januar-mars 2024) (10 queries)
  → Tester håndtering av multiple rapporter
  → Tester kostnadsberegning fra pristilbud
  → Tester akkumulering av bevis
  → Tester vurdering av forsikringsselskapets svar
  → Tester identifikasjon av nye mangler (gulv)

Session 5: Forliksforhandlinger og stevning (april-juni 2024) (4 queries)
  → Tester forliksstrategi
  → Tester stevningsutarbeidelse
  → Tester juridisk argumentasjon

Session 6: Prosessskriv og rettssak (september 2024-mai 2025) (10 queries)
  → Tester prosessføring
  → Tester håndtering av motpartens tilsvar
  → Tester akkumulering av bevis over lang tid
  → Tester helhetlig saksvurdering
  → Tester strategisk prioritering før hovedforhandling


METRIKER TIL MÅLING:

1. Konsistens: Samme saksforhold konsistent beskrevet gjennom sessions?
2. Nøyaktighet: Juridisk korrekt tolking av avhendingsloven og forsikringsrett?
3. Hukommelse: Husk tidligere funn og innblikk fra tidligere queries?
4. Progresjon: Utvikler analysen seg når ny informasjon kommer?
5. Prioritering: Fokuserer på vesentlige juridiske spørsmål?
6. Naturlig dialog: Håndterer oppfølgingsspørsmål uten å miste kontekst?
7. Økonomisk forståelse: Kan estimere kostnader og sammenstille pristilbud?
8. Multiple mangler: Håndterer akkumulering av flere mangler over tid?
9. Forsikringsforståelse: Forstår forskjellen på krav mot selger vs forsikring?
"""

if __name__ == "__main__":
    print(f"Testmanuskript: TOSL-2024-103311")
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
