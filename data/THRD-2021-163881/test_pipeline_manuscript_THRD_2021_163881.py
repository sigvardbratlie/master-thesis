
parts_map = {
    "parter": {
        "Nils Oscar Arnesen": "Anders Kristiansen",
        "Christine Helen Fosse": "Berit Kristiansen",
        "Sven Kåre Sture": "Carl Danielsen",
        "AmTrust International": "NordicGuard Insurance AS",
    },
    "advokater": {
        "Adele Munch Ditlefsen": "Emma Hansen",
        "Chriss Bjorøy": "Fredrik Larsen",
        "Amalie Skeide": "Fredrik Larsen",
        "Trond Baardseth": "Thor Berntsen",
    },
    "sakkyndige": {
        "Terje Haugan": "Tommy Hansen",
        "Trond Baardseth": "Thor Berntsen",
        "Trygve Berg": "Tore Bakke",
        "Magnus Sandvåg": "Martin Solberg",
        "Torstein Skutle": "Thomas Strand",
    },
    "eiendom": {
        "Langarinden 399A": "Fjellveien 42A",
        "Bergen": "Stavanger",
    },
}

MANUSCRIPT: list[dict] = [
    # ==============================================================================
    # SESSION 0: INITIALISERING
    # ==============================================================================
        {
            "session": 0,
            "date" : "2020-03-01",
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
            "attachments": ['./01_fabricated/2007-03-22_38_byggetillatelse_garasje_carport_2007-03-22.txt',
                        './01_fabricated/2019-07-28_04_epost_2019-07-28_utbedring_bekreftelse.txt',
                        './01_fabricated/2019-05-13_02_epost_2019-05-13_selgers_svar.txt',
                        './01_fabricated/2019-08-18_05_epost_2019-08-18_ny_lekkasje.txt',
                        './01_fabricated/2019-09-10_06a_skaderapport_2019-09-10_K2.txt',
                        './01_fabricated/2019-06-01_00_kjøpskontrakt_2019-06-01.txt',
                        './01_fabricated/2019-06-30_85_kvitteringer_flyttekostnader_2019-06-30.txt',
                        './01_fabricated/2019-05-15_00b_salgsoppgave_2019-05-15.txt',
                        './01_fabricated/2019-05-12_01_epost_2019-05-12_spoersmaal_om_eiendom.txt',
                        './01_fabricated/2019-08-15_33_kvitteringer_paakostninger_2019-08-15.txt',
                        './01_fabricated/2019-08-10_35_leieavtaler_dokumentasjon_2019-08-10.txt',
                        './01_fabricated/2019-07-25_03a_epost_2019-07-25_før_overtakelse.txt',
                        './01_fabricated/2019-07-15_03_epost_2019-07-15_varsling_lekkasje.txt',
                        './01_fabricated/2019-09-10_06_rapport_2019-09-10_skaderapport_takst.txt',
                        ".01/fabricated/2020_01-28_leieavtale_2020_tilbygg.txt",
                        ".01/fabricated/2020-03-12_07_rapport_2020-03-12_byggesoek_betongdekke.txt"],
            "solution" : ""
        },
    {
        "session": 0,
        "session_name": "Initialisering",
        "date" : "2020-03-13",
        "user_input": """
        Gi meg en kort og konsis oppsummering av sakens faktiske bakgrunn og utvikling så langt, basert på dokumentene jeg har lastet opp. 
        Fokuser på de viktigste hendelsene og problemstillingene. Hva er kjernen i saken?
        """,
        "attachments": [],
        "solution" : ""
    },
    {
        "session": 0,
        "session_name": "Initialisering",
        "date" : "2020-03-01",
        "user_input": """
        Dette er en eiendomskjøpssak. Hvilke lovbestemmelser er mest relevante 
        for denne typen tvister? Gi meg en oversikt over avhendingsloven sine 
        sentrale paragrafer for kjøpersaken.
        """,
        "attachments": [],
        "solution" : ""
    },
    {
        "session": 0,
        "session_name": "Initialisering",
        "date" : "2020-03-01",
        "user_input": """
        Er forholdene reklamert innenfor frister? Er det noen av punktene som er utenfor reklamasjonsfristen? Hva er konsekvensen av det i så fall?
        """,
        "attachments": [],
        "solution" : ""
    },
    {
        "session": 0,
        "session_name": "Initialisering",
        "date" : "2020-03-01",
        "user_input": """
        Har selger utelatt opplysninger eller gitt uriktig opplysbninger? 
        Har han evt også unnlatt å utbedre mangel innen fristen? 
        Er det noe han bør ha opplyst om som ikke er opplyst om? 
        """,
        "attachments": [],
        "solution" : ""
    },
    {
        "session": 0,
        "session_name": "Prosjekt-initialisering",
        "date" : "2020-03-01",
        "user_input": """
        Beskriver salgsoppgaven noen av de forhold som nå er problematiske?
        """,
        "attachments": [],
        "solution" : "",
    },

    # ==============================================================================
    # SESSION 1: Forbehold om heving
    # ==============================================================================
    {
        "session": 1,
        "session_name": "Heving",
        "date" : "2020-05-18",
        "user_input": """
        Saken har utviklet seg og vi har nå kommet til et punkt hvor vi skal heve kjøpet. Se vedlagt dokumenter frem til nå. 
        Lag meg utkast til forbehold om heving basert på de juridiske problemstillingene som er identifisert så langt.
        """,
        "attachments": [
                        './01_fabricated/2020-04-15_52_epost_2020-04-15_kommune_spoersmaal.txt',
                        './01_fabricated/2020-04-28_53_epost_2020-04-28_kommune_svar.txt',
                        './01_fabricated/2020-05-08_08_epost_2020-05-08_eiendomsgrense_problem.txt',
                        './01_fabricated/2020-05-18_55_sms_2020-05-18_kristiansen_hansen.txt',
                        './01_fabricated/2020-03-12_07_rapport_2020-03-12_byggesoek_betongdekke.txt',
                        './01_fabricated/2020-04-28_53_epost_2020-04-28_kommune_svar.txt',
                        './01_fabricated/2020-04-15_52_epost_2020-04-15_kommune_spoersmaal.txt',
                        './01_fabricated/2020-05-10_54_notat_2020-05-10_intern_strategi.txt'],
        "solution" : ""
    },
    {
        "session": 1,
        "session_name": "Heving",
        "date" : "2021-06-15",
        "user_input": """
        Se vedlagt nye rapporter, dokumenter og korrespondanse, samt vårt tidligere brev med forbehold om heving. 
        Lag et utkast til en formell hevingserklæring basert på dette.
        """,
        "attachments": [
                        
                        './01_fabricated/2020-05-19_09_brev_2020-05-19_forbehold_heving.txt',
                        './01_fabricated/2020-05-19_56_moetereferat_2020-05-19_klienter.txt',
                        './01_fabricated/2021-06-15_72_intern_mail_2021-06-15_forsikring.txt',
                        './01_fabricated/2021-01-29_10_rapport_2021-01-29_eiendomsgrenser_ERV.txt',
                        './01_fabricated/2021-06-11_12_pristilbud_2021-06-11_skandia_bygg.txt',
                        './01_fabricated/2020-05-10_54_notat_2020-05-10_intern_strategi.txt',
                        './01_fabricated/2021-06-16_73_epost_2021-06-16_forsikring_advokat.txt'],
        "solution" : ""
    },

    # ==============================================================================
    # SESSION 2: Stevning
    # ==============================================================================
    {
        "session": 2,
        "session_name": "Stevning",
        "date" : "2021-11-17",
        "user_input": """
        Se vedlagt nye rapporter, dokumenter og korrespondanse, samt vårt tidligere hevingserklæring.
        """,
        "attachments": ['./01_fabricated/2021-06-21_11_brev_2021-06-21_hevingserklaering.txt',
                        './01_fabricated/2021-01-15_40_rapport_berg_takstsenter_2021-01-15.txt',
                        './01_fabricated/2021-06-15_72_intern_mail_2021-06-15_forsikring.txt',
                        './01_fabricated/2021-01-29_10_rapport_2021-01-29_eiendomsgrenser_ERV.txt',
                        './01_fabricated/2021-06-11_12_pristilbud_2021-06-11_skandia_bygg.txt',
                        './01_fabricated/2021-10-21_41_rapport_target_consulting_skutle_2021-10-21.txt',
                        './01_fabricated/2021-06-16_73_epost_2021-06-16_forsikring_advokat.txt',
                        './01_fabricated/2021-10-21_13_rapport_2021-10-21_konsulentgruppen_dekke.txt'],
        "solution" : ""
    },
    {
        "session": 2,
        "session_name": "Stevning",
        "date" : "2021-11-17",
        "user_input": """
        Oppsummer sakens utvikling og status og gjør en kort summary av våre sterke og svake sider i saken. 
        
        """,
        "attachments": [], 
        "solution" : ""
    },
    {
        "session": 2,
        "session_name": "Stevning",
        "date" : "2021-11-17",
        "user_input": """
        Se vedlagt vår stevning og motpartens tilsvar. 
        Hva er de viktigste juridiske argumentene i hver av disse? Hvilke svakheter og styrker har de?
        
        """,
        "attachments": ['01_fabricated/2021-11-17_14_stevning_2021-11-17.txt',
                        '01_fabricated/2021-12-20_15_tilsvar_2021-12-20.txt'], 
        "solution" : ""
    },
    

    # ==============================================================================
    # SESSION 3: Rettsmekling og forliksavtale
    # ==============================================================================
    {
        "session": 3,
        "session_name": "Rettsmekling og forliksavtale",
        "date" : "2022-03-10",
        "user_input": """
        Vi skal nå i rettsmekling den 15. mars. Bistå meg i å forberede meg til dette. Se vedlagt nye dokumenter. 
        Hva er de viktigste punktene vi bør fokusere på i meklingen? Hva er våre forhandlingsmål, og hva er våre minimumsakseptable resultater?
        """,
        "attachments": [],
        "solution" : ""
    },
    {
        "session": 3,
        "session_name": "Rettsmekling og forliksavtale",
        "date" : "2022-03-10",
        "user_input": """
        Se vedlagt forliksavtale. Er det noen punkter som bør endres eller legges til for å sikre våre interesser?
        
        """,
        "attachments": ["01_fabricated/2022-03-30_17_forliksavtale_2022-03-30.txt"],
        "solution" : ""
    },
    {
        "session": 3,
        "session_name": "Rettsmekling og forliksavtale",
        "date" : "2023-04-18",
        "user_input": """
        Motparten har nå brutt forliksavtalen. Se vedlagt dokumenter. Hva er våre juridiske muligheter nå? Kan vi gå til sak igjen? Hva er risikoen ved det?
        Vi ønsker å heve avtalen, lag meg et utkast til en formell heving av forliksavtalen basert på dette.
        
        """,
        "attachments": ['./01_fabricated/2023-03-15_63_epost_2023-03-15_varsel_heving_forlik.txt',
                        './01_fabricated/2023-02-15_79_epost_2023-02-15_forsikring_alvorlig.txt',
                        './01_fabricated/2022-05-27_19_epost_2022-05-27_svar_oppfoelging.txt',
                        './01_fabricated/2022-09-05_60_epost_2022-09-05_manglende_fremdrift.txt',
                        './01_fabricated/2022-04-12_76_notat_2022-04-12_forsikring_oppfølging.txt',
                        './01_fabricated/2022-05-25_18_epost_2022-05-25_oppfoelging_forlik.txt',
                        './01_fabricated/2022-11-20_77_epost_2022-11-20_forsikring_bekymring.txt',
                        './01_fabricated/2022-12-14_93_epost_2022-12-14_svar_oppsigelse.txt',
                        './01_fabricated/2022-06-28_58_epost_2022-06-28_nabo_svar.txt',
                        './01_fabricated/2023-02-24_23_rapport_2023-02-24_betongteknikk.txt',
                        './01_fabricated/2022-04-05_20a_epost_2022-04-05_grendelag_makeskifte.txt',
                        './01_fabricated/2023-03-20_64_epost_2023-03-20_svar_heving.txt',
                        './01_fabricated/2022-09-12_21_epost_2022-09-12_ny_oppfoelging.txt',
                        './01_fabricated/2023-03-01_81_SMS_2023-03-01_kristiansen_interne.txt',
                        './01_fabricated/2022-09-19_22_epost_2022-09-19_svar_status.txt',
                        './01_fabricated/2022-11-22_78_epost_2022-11-22_advokat_svar_status.txt',
                        './01_fabricated/2022-07-05_59_epost_2022-07-05_kristiansen_nabo.txt',
                        './01_fabricated/2022-06-15_57_brev_2022-06-15_nabo_henvendelse.txt',
                        './01_fabricated/2023-02-28_62_notat_2023-02-28_hansen_intern.txt',
                        './01_fabricated/2023-01-15_36_epost_avslag_leietakere_2023-01-15.txt',
                        './01_fabricated/2023-02-17_80_epost_2023-02-17_carl_problemer.txt',
                        './01_fabricated/2022-10-12_61_epost_2022-10-12_fortsatt_ingen_søknad.txt'],
        "solution" : ""
    },
    {
        "session": 3,
        "session_name": "Rettsmekling og forliksavtale",
        "date" : "2023-04-18",
        "user_input": """
        Motpartens svar på heving ligger vedlagt. 
        Hva er vårt neste steg? 
        """,
        "attachments": ["01_fabricated/2023-05-02_24a_epost_2023-05-02_svar_heving.txt"],
        "solution" : ""
    },
    {
        "session": 3,
        "session_name": "Rettsmekling og forliksavtale",
        "date" : "2023-06-16",
        "user_input": """
        Vi ønsker å gjennomta saken. Lag meg utkast til begjæring om gjenopptakelse 
        """,
        "attachments": [ ],
        "solution" : ""
    },
    {
        "session": 3,
        "session_name": "Rettsmekling og forliksavtale",
        "date" : "2023-07-05",
        "user_input": """
        Se vedlagt svar fra tingretten.
        """,
        "attachments": ["01_fabricated/2023-07-05_66_kjennelse_2023-07-05_gjenopptagelse.txt"],
        "solution" : ""
    },
    #=============================================================================
    # SESSION 4: Rettsak
    #=============================================================================

     {
        "session": 4,
        "session_name": "Prosesskriv",
        "date" : "2025-06-01",
        "user_input": """
        Bistå meg i å utarbeide et prosesskriv for saken mot Selger. Se vedlagte nye dokumenter.
        Lag meg utkast og struktur for dette prosesskrivet basert på sakens dokumenter og utvikling så langt. 
        """,
        "attachments": ['./01_fabricated/2025-02-17_29_pristilbud_2025-02-17_vestkyst_mur.txt',
                        './01_fabricated/2024-11-07_71_epost_2024-11-07_saksøker_svar_passivitet.txt',
                        './01_fabricated/2023-09-25_27b_sms_2023-09-25_murer_utvidet.txt',
                        './01_fabricated/2025-05-25_88_beregning_tapte_husleieinntekter_detaljert_2025-05-25.txt',
                        './01_fabricated/2024-11-06_70_epost_2024-11-06_saksøkte_passivitet.txt',
                        './01_fabricated/2024-11-04_42_prosesskriv_saksøkte_2024-11-04.txt',
                        './01_fabricated/2024-03-15_30_prisanslag_2024-03-15_takstsenter.txt',
                        './01_fabricated/2023-09-25_68_epost_2023-09-25_hansen_svar_mur.txt',
                        './01_fabricated/2025-02-17_29a_pristilbud_2025-02-17_tertnes.txt',
                        './01_fabricated/2024-08-15_89_dokumentasjon_avviste_leietakere_2024-08-15.txt',
                        './01_fabricated/2024-09-09_28a_rapport_2024-09-09_BERAS_murer_komplett.txt',
                        './01_fabricated/2023-09-20_26_referat_2023-09-20_forhaandskonferanse.txt',
                        './01_fabricated/2023-09-22_67_epost_2023-09-22_mur_oppdagelse.txt',
                        './01_fabricated/2025-05-10_34_beregning_tapte_husleieinntekter_2025-05-10.txt',
                        './01_fabricated/2025-02-19_29b_pristilbud_2025-02-19_oygarden.txt',
                        './01_fabricated/2023-09-21_27a_epost_2023-09-21_murer_oppsummering.txt',
                        './01_fabricated/2023-09-25_27_sms_2023-09-25_murer.txt',
                        './01_fabricated/2024-09-09_28_rapport_2024-09-09_ERV_murer.txt',
                        './01_fabricated/2024-05-20_94_moetereferat_2024-05-20_forberedelse_hovedforhandling.txt',
                        './01_fabricated/2025-03-12_31_rapport_2025-03-12_verditap_parkering.txt',
                        './01_fabricated/2023-09-28_69_brev_2023-09-28_reklamasjon_murer.txt'],
        "solution" : ""
    },
    {
        "session": 4,
        "session_name": "Prosesskriv",
        "date" : "2025-06-06",
        "user_input": """
        Sluttinnlegg for hovedforhandling. Lag meg et utkast til dette basert på sakens dokumenter og utvikling så langt.
        """,
        "attachments": [],
        "solution" : ""
    },
    {
        "session": 4,
        "session_name": "Prosesskriv",
        "date" : "2025-06-06",
        "user_input": """
        Se vedlagt dom. 
        """,
        "attachments": ["01_fabricated/2025-07-16_132_Domisivilsak-fagdommer(e)_242348.txt"],
        "solution" : ""
    }, 
]
