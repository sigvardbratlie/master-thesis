"""
Fixture data for Summarizer tests.
Contains realistic mock data for testing Summarizer and ToolManager classes.
"""

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


# ============================================
#           MOCK CONTENT FOR SUMMARIZATION
# ============================================

def get_mock_long_content() -> str:
    """Returns mock long content for summarization testing - a legal document excerpt."""
    return """TILSTANDSRAPPORT

Oppdragsgiver: Daniel Erik Hansen og Camilla Marie Hansen
Adresse: Granveien 15B, 0375 Oslo
Oppdragsnummer: 2023-1542
Dato for befaring: 30. mars 2023
Rapportdato: 30. mars 2023

1. INNLEDNING
Denne tilstandsrapporten er utarbeidet på oppdrag fra eierne av eiendommen Granveien 15B i Oslo.
Rapporten beskriver teknisk tilstand på bygningen og eiendommen basert på visuell befaring.
Bygningen er en enebolig oppført i 1985 med senere tilbygg og ombygginger.

2. BYGNINGSBESKRIVELSE
Bygningstype: Enebolig
Byggeår: 1985
Antall etasjer: 2 + kjeller
Bruksareal (BRA): 245 kvm
Tomteareal: 812 kvm

3. VURDERING AV TILSTAND

3.1 Elektrisk anlegg
Tilstandsgrad: TG2
Beskrivelse: Det elektriske anlegget er delvis oppgradert. Hovedtavle og deler av anlegget
er fra byggåret (1985). Sikringsskapet har kombinasjon av gamle og nye kurser.
Anbefaling: Det anbefales gjennomgang av autorisert elektriker for vurdering av behov for
oppgradering til moderne standard.

3.2 Pipe og ildsted
Tilstandsgrad: TG2
Beskrivelse: Pipen er opprinnelig fra byggåret. Ved visuell inspeksjon observeres noe
forvitring av fuger i øvre del. Pipa er ikke feiet de siste 2 år ifølge eier.
Anbefaling: Det anbefales rehabilitering av pipeløp og feiing før bruk av ildsted.

3.3 Tak og taktekking
Tilstandsgrad: TG1
Beskrivelse: Taket ble lagt om i 2021 med nye takstein av typen Monier Zanda.
Takrenner og nedløp er i god stand.

3.4 Bad 2. etasje
Tilstandsgrad: TG1
Beskrivelse: Badet ble totalrenovert i 2020-2021 av Moderne Bygg AS.
Membran og flisarbeid fremstår fagmessig utført.

3.5 Kjeller
Tilstandsgrad: TG1
Beskrivelse: Kjelleren er tørr og godt ventilert. Ingen tegn til fuktproblemer.

4. KONKLUSJON
Eiendommen er generelt i god stand med noen merknader knyttet til det elektriske anlegget
og pipen som bør vurderes nærmere. Øvrige bygningsdeler har tilstandsgrad TG1.

5. ANSVARSFRASKRIVELSE
Denne rapporten er basert på visuell befaring uten inngrep i konstruksjoner.
Skjulte feil og mangler kan forekomme.

Takstmann: David Storvik
ProTakst AS
Autorisert takstmann NITO"""


def get_mock_short_content() -> str:
    """Returns mock short content for summarization testing."""
    return """E-post fra Daniel Hansen til Andreas Nilsen datert 21. august 2023.
Selger bekrefter at varmepumpene fungerer, ingen planlagte utbedringer gjenstår,
og at elektrikeren har sjekket alt."""


def get_mock_tool_result_content() -> str:
    """Returns mock tool result content for summarization."""
    return """{
    "query": "SELECT * FROM court_cases WHERE topic = 'avhendingslova'",
    "results": [
        {
            "case_id": "HR-2017-1073-A",
            "title": "Boligkjøper mot selger - skjulte mangler",
            "court": "Høyesterett",
            "date": "2017-06-01",
            "summary": "Saken gjaldt krav om prisavslag etter kjøp av bolig med fuktskader",
            "outcome": "Kjøper fikk medhold"
        },
        {
            "case_id": "HR-2010-997-A",
            "title": "Elektriske feil i bolig",
            "court": "Høyesterett",
            "date": "2010-06-10",
            "summary": "Spørsmål om selgers opplysningsplikt ved salg av bolig med eldre elektrisk anlegg",
            "outcome": "Selger ansvarlig for mangelfull opplysning"
        },
        {
            "case_id": "LB-2019-12345",
            "title": "Reklamasjon på pipe og ildsted",
            "court": "Borgarting lagmannsrett",
            "date": "2019-11-15",
            "summary": "Kjøper reklamerte på pipe som ikke tilfredsstilte krav til tetthet",
            "outcome": "Kjøper tilkjent prisavslag"
        }
    ],
    "total_matches": 3,
    "execution_time_ms": 145
}"""


# ============================================
#           MOCK LLM RESPONSES
# ============================================

def get_mock_summary_response() -> str:
    """Returns mock summary response from LLM."""
    return """Tilstandsrapporten fra ProTakst AS (30. mars 2023) for Granveien 15B viser:
- Elektrisk anlegg (TG2): Delvis fra 1985, anbefales gjennomgang av elektriker
- Pipe (TG2): Forvitring i fuger, anbefales rehabilitering
- Tak (TG1): Lagt om i 2021, god stand
- Bad 2. etasje (TG1): Renovert 2020-2021
- Kjeller (TG1): Tørr, ingen fuktproblemer
Konklusjon: Generelt god stand, men el-anlegg og pipe bør vurderes nærmere."""


def get_mock_title_response() -> str:
    """Returns mock title response from LLM."""
    return "Eiendomstvist Granveien 15B"


# ============================================
#           MOCK CHAT MESSAGES
# ============================================

def get_mock_messages_for_title() -> list:
    """Returns mock messages for title generation."""
    return [
        HumanMessage(content="Jeg har en eiendomssak angående mangler funnet etter kjøp av Granveien 15B."),
        AIMessage(content="Jeg forstår. Kan du fortelle mer om hvilke mangler som ble oppdaget?"),
        HumanMessage(content="Det var elektriske feil og problemer med pipa som ikke var opplyst om."),
        AIMessage(content="Basert på det du beskriver kan dette være brudd på selgers opplysningsplikt etter avhendingslova.")
    ]


def get_mock_messages_for_summary() -> list:
    """Returns mock messages for conversation summarization."""
    return [
        HumanMessage(content="Hei, jeg trenger hjelp med en eiendomssak."),
        AIMessage(content="Hei! Jeg hjelper gjerne. Hva handler saken om?"),
        HumanMessage(content="Vi kjøpte en bolig i august 2023 og oppdaget mangler etter overtakelsen."),
        AIMessage(content="Forstår. Hvilke mangler ble oppdaget, og når oppdaget dere dem?"),
        HumanMessage(content="Elektriske feil i sikringsskapet og problemer med pipa. Vi oppdaget det i desember."),
        AIMessage(content="""Dette høres ut som en sak der avhendingslova kan komme til anvendelse.
Etter § 3-9 har eiendommen mangel hvis den ikke samsvarer med opplysninger selger har gitt.
Dere bør dokumentere manglene og sende skriftlig reklamasjon til selger."""),
        HumanMessage(content="Selgeren sa før kjøpet at elektrikeren hadde sjekket alt og at alt var i orden."),
        AIMessage(content="""Dette er viktig informasjon. Hvis selger ga uriktige opplysninger om det elektriske
anleggets tilstand, kan dette utgjøre en mangel etter avhendingslova § 3-8.
Dere kan ha krav på prisavslag eller erstatning.""")
    ]


# ============================================
#           MOCK LLM RETURN OBJECTS
# ============================================

class MockLLMResponse:
    """Mock LLM response object with content attribute."""
    def __init__(self, content: str):
        self.content = content


def get_mock_llm_summary_response() -> MockLLMResponse:
    """Returns mock LLM response object for summarization."""
    return MockLLMResponse(content=get_mock_summary_response())


def get_mock_llm_title_response() -> MockLLMResponse:
    """Returns mock LLM response object for title generation."""
    return MockLLMResponse(content=get_mock_title_response())


# ============================================
#           ADDITIONAL MOCK DATA
# ============================================

def get_mock_conversation_history() -> list:
    """Returns a longer conversation history for testing truncation."""
    messages = []
    topics = [
        ("Hva er fristen for reklamasjon?", "Etter avhendingslova må reklamasjon fremsettes innen rimelig tid."),
        ("Hva menes med rimelig tid?", "Vanligvis 2-3 måneder fra mangelen ble eller burde vært oppdaget."),
        ("Kan vi kreve heving av kjøpet?", "Heving krever vesentlig kontraktbrudd. Prisavslag er mer vanlig."),
        ("Hvor mye kan vi kreve i prisavslag?", "Prisavslaget beregnes ut fra utbedringskostnadene."),
        ("Trenger vi advokat?", "For større saker anbefales juridisk bistand."),
        ("Hva koster det å gå til sak?", "Saksomkostninger avhenger av sakens kompleksitet."),
        ("Kan vi bruke rettshjelpsforsikring?", "Ja, sjekk innboforsikringen din for rettshjelpsdekning."),
        ("Hvordan dokumenterer vi manglene?", "Innhent takstrapport og dokumenter alt skriftlig.")
    ]

    for question, answer in topics:
        messages.append(HumanMessage(content=question))
        messages.append(AIMessage(content=answer))

    return messages


def get_mock_legal_document_content() -> str:
    """Returns mock legal document content for testing."""
    return """STEVNING

Til Oslo tingrett

Saksøker: Andreas Nilsen og Berit Johansen
v/advokat Erik Olsen
Advokatfirmaet Olsen & Co

Saksøkt: Daniel Erik Hansen og Camilla Marie Hansen
Adresse: Granveien 15B, 0375 Oslo

PÅSTAND:
1. De saksøkte dømmes til å betale saksøkerne prisavslag med kr 225.000,-
2. De saksøkte dømmes til å betale sakskostnader

SAKSFREMSTILLING:
Saksøkerne kjøpte eiendommen Granveien 15B den 25. august 2023 for kr 15.500.000,-.
Overtakelse skjedde 11. november 2023.

Etter overtakelsen ble det avdekket følgende mangler:
1. Elektrisk anlegg med alvorlige feil som krever full utskifting (kr 150.000,-)
2. Pipe med behov for rehabilitering (kr 75.000,-)

RETTSLIG GRUNNLAG:
Avhendingslova § 3-8 og § 3-9
Selger ga uriktige opplysninger om eiendommens tilstand.

Oslo, 15. januar 2024

_____________________
Advokat Erik Olsen"""
