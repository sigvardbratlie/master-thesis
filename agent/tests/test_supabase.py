import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Legg til src-mappen i path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import SupabaseManager

# Mock data fra Supabase
MOCK_PROJECT_DATA = {'data': {'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
  'created_at': '2026-02-05T12:12:19.666087+00:00',
  'updated_at': '2026-02-05T13:12:19.560601+00:00',
  'updated_query_id': '0c22552d-8bee-4c24-a099-335c80db5573',
  'updated_session_id': '8fbac4e4-c2ff-4f58-95ba-7836f207a89d',
  'background': 'Eiendomskjøp på Fjellveien 42A i Stavanger kommune med problemer som har dukket opp etter kjøpet.',
  'title': 'Eiendomskjøpssak - Problemer med eiendommen',
  'user_id': '53d63d18-cfa1-416e-96e8-770c8f66507b',
  'project_attachments': [{'path': '53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/fc545f59-ac93-4cda-8b41-83eed0d04ee3.txt',
    'size': 4944,
    'file_id': 'fc545f59-ac93-4cda-8b41-83eed0d04ee3',
    'category': 'agreement',
    'filename': '2019-08-10_35_leieavtaler_dokumentasjon_2019-08-10.txt',
    'file_date': '2019-08-10T00:00:00+00:00',
    'file_type': 'text/plain',
    'created_at': '2026-02-05T12:12:19.851307+00:00',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Lease agreements for properties at Fjellveien 42A, Stavanger, detailing tenant agreements, rental amounts, and termination notices.',
    'party_roles': ['plaintiff', 'tenant'],
    'significance': 'high',
    'key_provisions': ['Monthly rent for extension unit: Kr 8,000, later increased to Kr 9,000',
     'Deposit: Kr 24,000 for extension unit, Kr 27,000 for interior unit',
     'Lease period: Indefinite with 3 months notice',
     'Termination notice received on 5 October 2022, last rental day on 31 December 2022',
     'New interior unit lease starting on 1 February 2023']},
   {'path': '53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/9a7722d6-804b-42bf-b3af-8b2860dc207b.txt',
    'size': 654,
    'file_id': '9a7722d6-804b-42bf-b3af-8b2860dc207b',
    'category': 'other',
    'filename': '2019-06-30_85_kvitteringer_flyttekostnader_2019-06-30.txt',
    'file_date': '2023-01-15T00:00:00+00:00',
    'file_type': 'text/plain',
    'created_at': '2026-02-05T12:12:19.851307+00:00',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Dokumentasjon av flyttekostnader for eiendom på Fjellveien 42A.',
    'party_roles': ['plaintiff'],
    'significance': 'medium',
    'key_provisions': ['Flyttebyrå - Innflytting 2019: NOK 33,400',
     'Rengjøring ved innflytting: NOK 12,500',
     'Flytting av møbler (internt) - 2023: NOK 8,900',
     'Estimert utflytting: NOK 45,000 - 55,000']},
   {'path': '53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/ec93234f-2d18-4ace-83a9-8fba789aff44.txt',
    'size': 568,
    'file_id': 'ec93234f-2d18-4ace-83a9-8fba789aff44',
    'category': 'correspondence',
    'filename': '2019-07-15_03_epost_2019-07-15_varsling_lekkasje.txt',
    'file_date': '2019-07-15T00:00:00+00:00',
    'file_type': 'text/plain',
    'created_at': '2026-02-05T12:12:19.851307+00:00',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'E-mail notification about a leak discovered in the rental part of the property purchased by the plaintiffs, detailing the issue, the actions being taken, and the responsibility to remedy the situation before the handover.',
    'party_roles': ['plaintiff', 'defendant'],
    'significance': 'high',
    'key_provisions': None},
   {'path': '53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/d21d4947-c2b9-40c7-a12b-03e9b57f8ffa.txt',
    'size': 877,
    'file_id': 'd21d4947-c2b9-40c7-a12b-03e9b57f8ffa',
    'category': 'correspondence',
    'filename': '2019-07-25_03a_epost_2019-07-25_før_overtakelse.txt',
    'file_date': '2019-07-25T00:00:00+00:00',
    'file_type': 'text/plain',
    'created_at': '2026-02-05T12:12:19.851307+00:00',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'E-mail correspondence regarding renovations and issues prior to property takeover at Fjellveien 42A.',
    'party_roles': ['plaintiff', 'defendant'],
    'significance': 'medium',
    'key_provisions': ['Renovation work details before takeover',
     'Leak repair performed in rental unit',
     'Confirmation of cleanliness of rental unit before takeover']},
   {'path': '53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/4ec72cdf-dc46-4e25-8c40-b161798e6b7d.txt',
    'size': 395,
    'file_id': '4ec72cdf-dc46-4e25-8c40-b161798e6b7d',
    'category': 'correspondence',
    'filename': '2019-07-28_04_epost_2019-07-28_utbedring_bekreftelse.txt',
    'file_date': '2019-07-28T00:00:00+00:00',
    'file_type': 'text/plain',
    'created_at': '2026-02-05T12:12:19.851307+00:00',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Email from Carl Danielsen informing Anders Kristiansen that the leak has been repaired and confirming that everything is ready for takeover on August 1.',
    'party_roles': ['plaintiff'],
    'significance': 'medium',
    'key_provisions': None},
   {'path': '53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/bd1a0c50-6fbb-4653-bb37-70728eadf446.txt',
    'size': 2303,
    'file_id': 'bd1a0c50-6fbb-4653-bb37-70728eadf446',
    'category': 'other',
    'filename': '2019-08-15_33_kvitteringer_paakostninger_2019-08-15.txt',
    'file_date': '2024-01-01T00:00:00+00:00',
    'file_type': 'text/plain',
    'created_at': '2026-02-05T12:12:19.851307+00:00',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Documentation of expenses related to property improvements and upgrades following the purchase of a home at Fjellveien 42A, Stavanger. Includes receipts for appliances and installations, totaling documented costs of 74,598 NOK.',
    'party_roles': ['plaintiff'],
    'significance': 'medium',
    'key_provisions': ['Total documented expenses: 74,598 NOK',
     'Claimed in the case (estimated): 49,287 NOK']},
   {'path': '53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/385152cb-182e-4551-89f6-3091528b9f55.txt',
    'size': 406,
    'file_id': '385152cb-182e-4551-89f6-3091528b9f55',
    'category': 'correspondence',
    'filename': '2019-08-18_05_epost_2019-08-18_ny_lekkasje.txt',
    'file_date': '2019-08-18T00:00:00+00:00',
    'file_type': 'text/plain',
    'created_at': '2026-02-05T12:12:19.851307+00:00',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Email from Anders Kristiansen to Carl Danielsen regarding a water leak in a rental unit at Fjellveien 42A, signaling ongoing issues after a property purchase.',
    'party_roles': ['plaintiff'],
    'significance': 'medium',
    'key_provisions': None},
   {'path': '53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/ceedaf8c-94a0-432a-9eef-a084796b21eb.txt',
    'size': 1260,
    'file_id': 'ceedaf8c-94a0-432a-9eef-a084796b21eb',
    'category': 'expert_report',
    'filename': '2019-09-10_06_rapport_2019-09-10_skaderapport_takst.txt',
    'file_date': '2019-09-10T00:00:00+00:00',
    'file_type': 'text/plain',
    'created_at': '2026-02-05T12:12:19.851307+00:00',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Skaderapport for eiendom på Fjellveien 42A, som beskriver problemer med lekkasje, observert skader, årsak til skaden, og anbefalinger for utbedring.',
    'party_roles': ['plaintiff'],
    'significance': 'high',
    'key_provisions': ['Konstatert lekkasje via betongdekket',
     'Visibly observed damages',
     'Recommendation for further technical assessment']},
   {'path': '53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/ebd3677f-5d90-446d-b224-00581dd925ea.txt',
    'size': 1966,
    'file_id': 'ebd3677f-5d90-446d-b224-00581dd925ea',
    'category': 'expert_report',
    'filename': '2019-09-10_06a_skaderapport_2019-09-10_K2.txt',
    'file_date': '2019-09-10T00:00:00+00:00',
    'file_type': 'text/plain',
    'created_at': '2026-02-05T12:12:19.851307+00:00',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Skaderapport regarding water leakage issues at the property located at Fjellveien 42A, Stavanger. The report details observations from an inspection, causes of the damage, and recommendations for repairs and further investigation.',
    'party_roles': ['plaintiff'],
    'significance': 'high',
    'key_provisions': ['Befaring date: September 5, 2019',
     'Report date: September 10, 2019',
     'Identified leakage points and observations of water damage.',
     'Recommendations for further examination and repairs.']},
   {'path': '53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/0d73bcbd-ef86-402e-b9ae-89303140ed81.txt',
    'size': 345,
    'file_id': '0d73bcbd-ef86-402e-b9ae-89303140ed81',
    'category': 'agreement',
    'filename': '2020_90_leieavtale_2020_tilbygg.txt',
    'file_date': '2020-01-28T00:00:00+00:00',
    'file_type': 'text/plain',
    'created_at': '2026-02-05T12:12:19.851307+00:00',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Lease agreement for a rental unit located at Fjellveien 42A, Stavanger, between landlords Anders and Berit Kristiansen and tenant Ole Martin Pedersen.',
    'party_roles': ['landlord', 'tenant'],
    'significance': 'high',
    'key_provisions': ['Rental object: Hybel, Fjellveien 42A, 4020 Stavanger',
     'Lease period: From February 1, 2020',
     'Monthly rent: NOK 8,500 (including utilities)',
     'Deposit: NOK 25,500']},
   {'path': '53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/6d7490fd-cf3a-4d8a-b1c3-f62c7f95e4e4.txt',
    'size': 1608,
    'file_id': '6d7490fd-cf3a-4d8a-b1c3-f62c7f95e4e4',
    'category': 'expert_report',
    'filename': '2020-03-12_07_rapport_2020-03-12_byggesoek_betongdekke.txt',
    'file_date': '2020-03-12T00:00:00+00:00',
    'file_type': 'text/plain',
    'created_at': '2026-02-05T12:12:19.851307+00:00',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Teknisk rapport avdekkende problemer med betongdekke i eiendom på Fjellveien 42A, inkludert manglende bærebjelker, avvik i materialtykkelser, og manglende dokumentasjon.',
    'party_roles': ['plaintiff'],
    'significance': 'high',
    'key_provisions': ['Undersøkelse av betongdekke',
     'Ingen bærebjelker funnet',
     'Oppbygging er tynnere enn godkjent',
     'Avvik i materialtykkelser',
     'Manglende dokumentasjon for brukte produkter']}],
  'project_events': [{'file_id': '9a7722d6-804b-42bf-b3af-8b2860dc207b',
    'parties': ['plaintiff'],
    'category': 'payment_made',
    'disputed': False,
    'event_id': 'dcec892b-75f1-41cc-86ac-d24420f6111b',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2019-07-30T00:00:00+00:00',
    'event_name': 'Flyttebyrå - Innflytting',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Kvittering fra Viking Flyttebyrå AS for innflytting.',
    'significance': 'medium'},
   {'file_id': '9a7722d6-804b-42bf-b3af-8b2860dc207b',
    'parties': ['plaintiff'],
    'category': 'payment_made',
    'disputed': False,
    'event_id': '6596a207-de5e-4045-b46b-7bd58fc713eb',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2019-07-29T00:00:00+00:00',
    'event_name': 'Rengjøring ved innflytting',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Kvittering fra Renhold Vest AS for rengjøring ved innflytting.',
    'significance': 'medium'},
   {'file_id': '9a7722d6-804b-42bf-b3af-8b2860dc207b',
    'parties': ['plaintiff'],
    'category': 'payment_made',
    'disputed': False,
    'event_id': '795775f8-32a8-486b-ab2a-7349d1f854d5',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2023-01-15T00:00:00+00:00',
    'event_name': 'Flytting av møbler (internt)',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Kvittering fra Småjobber AS for internt flytt.',
    'significance': 'medium'},
   {'file_id': '9a7722d6-804b-42bf-b3af-8b2860dc207b',
    'parties': ['plaintiff'],
    'category': 'other',
    'disputed': False,
    'event_id': '0529cdf9-9862-4008-8069-54819e59af08',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2023-01-15T00:00:00+00:00',
    'event_name': 'Estimert utflytting',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Estimat for fremtidige flyttekostnader basert på tilbud fra tre flyttebyråer.',
    'significance': 'medium'},
   {'file_id': 'ec93234f-2d18-4ace-83a9-8fba789aff44',
    'parties': ['plaintiff', 'other'],
    'category': 'notice_sent',
    'disputed': False,
    'event_id': '560fa25e-6057-4140-83c1-936752a9d450',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2019-07-15T16:48:00+00:00',
    'event_name': 'notice_sent',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Notice sent to Anders Kristiansen regarding the discovery of a leak in the property before handover.',
    'significance': 'high'},
   {'file_id': 'd21d4947-c2b9-40c7-a12b-03e9b57f8ffa',
    'parties': ['plaintiff', 'defendant'],
    'category': 'other',
    'disputed': False,
    'event_id': '6b5f593a-c59d-44c2-8009-fecb4f4d1b96',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2019-07-25T00:00:00+00:00',
    'event_name': 'Renovation Issues Addressed',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Notification regarding the completion of repairs and other renovation details prior to property takeover.',
    'significance': 'medium'},
   {'file_id': 'd21d4947-c2b9-40c7-a12b-03e9b57f8ffa',
    'parties': ['plaintiff', 'defendant'],
    'category': 'other',
    'disputed': False,
    'event_id': '8682faca-e050-4474-842c-fde1c80137b6',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2019-08-01T00:00:00+00:00',
    'event_name': 'Property Takeover Scheduled',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Scheduled date for the takeover of the property.',
    'significance': 'high'},
   {'file_id': '4ec72cdf-dc46-4e25-8c40-b161798e6b7d',
    'parties': ['plaintiff'],
    'category': 'notice_sent',
    'disputed': False,
    'event_id': 'b2ac987c-400a-4f6e-8397-7d6e28d7f79b',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2019-07-28T14:22:00+00:00',
    'event_name': 'notice_sent',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Email sent to Anders Kristiansen regarding repairs and readiness for takeover.',
    'significance': 'medium'},
   {'file_id': 'fc545f59-ac93-4cda-8b41-83eed0d04ee3',
    'parties': ['plaintiff', 'tenant'],
    'category': 'contract_signed',
    'disputed': False,
    'event_id': 'dcf84394-a909-47c2-bbad-8f1533d80695',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2019-08-10T00:00:00+00:00',
    'event_name': 'Lease Signed for Extension Unit',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Lease agreement signed between Anders Kristiansen, Berit Kristiansen, and Martine Olsen for extension unit at Fjellveien 42A.',
    'significance': 'high'},
   {'file_id': 'fc545f59-ac93-4cda-8b41-83eed0d04ee3',
    'parties': ['plaintiff', 'tenant'],
    'category': 'other',
    'disputed': False,
    'event_id': 'd8825500-72fa-43c5-b672-e2e26b552957',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2020-08-01T00:00:00+00:00',
    'event_name': 'Lease Increased for Extension Unit',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Monthly rent increased from Kr 8,000 to Kr 9,000 for the extension unit.',
    'significance': 'medium'},
   {'file_id': 'fc545f59-ac93-4cda-8b41-83eed0d04ee3',
    'parties': ['plaintiff', 'tenant'],
    'category': 'termination',
    'disputed': False,
    'event_id': 'e3e3c8ab-0dbc-42c4-b3f5-b24f1a11aae9',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2022-10-05T00:00:00+00:00',
    'event_name': 'Termination Notice Received for Extension Unit',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Termination notice received from Martine Olsen for the extension unit, effective 31 December 2022.',
    'significance': 'high'},
   {'file_id': 'fc545f59-ac93-4cda-8b41-83eed0d04ee3',
    'parties': ['plaintiff', 'tenant'],
    'category': 'contract_signed',
    'disputed': False,
    'event_id': '1884447b-936d-4f3b-bb97-3fd6700cf0f5',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2023-01-15T00:00:00+00:00',
    'event_name': 'Lease Signed for Interior Unit',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'New lease agreement signed between Anders Kristiansen, Berit Kristiansen, and Jonas Pettersen for an interior unit at Fjellveien 42A.',
    'significance': 'high'},
   {'file_id': 'fc545f59-ac93-4cda-8b41-83eed0d04ee3',
    'parties': ['plaintiff'],
    'category': 'other',
    'disputed': False,
    'event_id': 'e1f75aab-be3f-410f-98ef-dc20bf356583',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2023-01-20T00:00:00+00:00',
    'event_name': 'Notice from Landlord',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Anders Kristiansen discusses the leasing situation concerning the interior unit being rented out and the challenges faced by the family.',
    'significance': 'medium'},
   {'file_id': 'bd1a0c50-6fbb-4653-bb37-70728eadf446',
    'parties': ['plaintiff'],
    'category': 'payment_made',
    'disputed': False,
    'event_id': '148cf9b6-2ef1-4e99-a9b6-81798783c15d',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2019-08-15T00:00:00+00:00',
    'event_name': 'Receipt for Appliances',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Purchase of kitchen appliances including a dishwasher, oven, refrigerator, and associated costs.',
    'significance': 'medium'},
   {'file_id': 'bd1a0c50-6fbb-4653-bb37-70728eadf446',
    'parties': ['plaintiff'],
    'category': 'payment_made',
    'disputed': False,
    'event_id': 'f9ffea2d-a44c-434b-a068-1b3633f9ccba',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2024-04-12T00:00:00+00:00',
    'event_name': 'Invoice for Digital Lock',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Installation of a digital lock for security purposes, paid on 15.04.2024.',
    'significance': 'medium'},
   {'file_id': 'bd1a0c50-6fbb-4653-bb37-70728eadf446',
    'parties': ['plaintiff'],
    'category': 'payment_made',
    'disputed': False,
    'event_id': '94c01c43-2942-44a3-9788-ae24bb7c4174',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2023-09-05T00:00:00+00:00',
    'event_name': 'Installation of Electric Vehicle Charger',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Installation of an electric vehicle charger, completed and paid in cash.',
    'significance': 'medium'},
   {'file_id': 'bd1a0c50-6fbb-4653-bb37-70728eadf446',
    'parties': ['plaintiff'],
    'category': 'payment_made',
    'disputed': False,
    'event_id': 'ee25fdea-ba08-4e11-afcc-67543f14f60d',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2024-03-23T00:00:00+00:00',
    'event_name': 'Minor Improvements',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Installation of new lamps in the rental unit.',
    'significance': 'medium'},
   {'file_id': 'bd1a0c50-6fbb-4653-bb37-70728eadf446',
    'parties': ['plaintiff'],
    'category': 'payment_made',
    'disputed': False,
    'event_id': '294170cf-f61b-45b0-affa-b575d093fee5',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2024-01-01T00:00:00+00:00',
    'event_name': 'Painting Work',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Self-done painting work with purchased materials.',
    'significance': 'medium'},
   {'file_id': 'bd1a0c50-6fbb-4653-bb37-70728eadf446',
    'parties': ['plaintiff'],
    'category': 'payment_made',
    'disputed': False,
    'event_id': 'e9a22db0-09cb-4ae6-a038-221704dbbcdb',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2024-01-01T00:00:00+00:00',
    'event_name': 'Purchase of Garden Tools',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Acquisition of garden tools such as rakes.',
    'significance': 'medium'},
   {'file_id': 'bd1a0c50-6fbb-4653-bb37-70728eadf446',
    'parties': ['plaintiff'],
    'category': 'payment_made',
    'disputed': False,
    'event_id': '570e8461-37f7-4054-be8b-238cf01ad9ef',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2024-01-01T00:00:00+00:00',
    'event_name': 'Purchase of Outdoor Furniture',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Purchase of outdoor furniture for the terrace.',
    'significance': 'medium'},
   {'file_id': '385152cb-182e-4551-89f6-3091528b9f55',
    'parties': ['plaintiff', 'other'],
    'category': 'notice_sent',
    'disputed': False,
    'event_id': 'd9f630e0-2900-422b-9e30-cf2cf3c77f00',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2019-08-18T20:15:00+00:00',
    'event_name': 'notice_sent',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Anders Kristiansen notifies Carl Danielsen of a recurring water leak issue in the rental part of the property.',
    'significance': 'high'},
   {'file_id': 'ceedaf8c-94a0-432a-9eef-a084796b21eb',
    'parties': ['plaintiff'],
    'category': 'other',
    'disputed': False,
    'event_id': '14581453-c919-4400-9f29-bd27159f0543',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2019-09-03T00:00:00+00:00',
    'event_name': 'Property Inspection',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Inspeksjon av eiendom Fjellveien 42A for å vurdere skader.',
    'significance': 'high'},
   {'file_id': 'ceedaf8c-94a0-432a-9eef-a084796b21eb',
    'parties': ['plaintiff'],
    'category': 'other',
    'disputed': False,
    'event_id': '16094d10-c1f3-4086-a615-28f82f461c11',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2019-09-10T00:00:00+00:00',
    'event_name': 'Report Completed',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Skaderapport for eiendom på Fjellveien 42A ble utarbeidet.',
    'significance': 'high'},
   {'file_id': 'ebd3677f-5d90-446d-b224-00581dd925ea',
    'parties': ['plaintiff'],
    'category': 'other',
    'disputed': False,
    'event_id': '398a6f71-9e63-4a98-b940-6de442e1b6de',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2019-09-10T00:00:00+00:00',
    'event_name': 'inspection_report_completed',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Completion of the inspection report by K2 Taksering AS regarding the leakage issues at Fjellveien 42A.',
    'significance': 'high'},
   {'file_id': 'ebd3677f-5d90-446d-b224-00581dd925ea',
    'parties': ['plaintiff'],
    'category': 'meeting',
    'disputed': False,
    'event_id': '6f459b42-1928-4e1e-9992-096416d6e8aa',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2019-09-05T00:00:00+00:00',
    'event_name': 'construction_inspection',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Inspection of the property at Fjellveien 42A for leakage issues.',
    'significance': 'medium'},
   {'file_id': '0d73bcbd-ef86-402e-b9ae-89303140ed81',
    'parties': ['landlord', 'tenant'],
    'category': 'contract_signed',
    'disputed': False,
    'event_id': 'd7d15607-6963-4fda-b06c-1434b2392285',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2020-01-28T00:00:00+00:00',
    'event_name': 'contract_signed',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Lease agreement signed between Anders and Berit Kristiansen (landlords) and Ole Martin Pedersen (tenant).',
    'significance': 'high'},
   {'file_id': '6d7490fd-cf3a-4d8a-b1c3-f62c7f95e4e4',
    'parties': ['plaintiff'],
    'category': 'other',
    'disputed': False,
    'event_id': '9408152b-3748-41d7-bb8e-e349236da1b8',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2020-03-12T00:00:00+00:00',
    'event_name': 'report_created',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Teknisk rapport utarbeidet av Kari Berg om betongdekke på Fjellveien 42A.',
    'significance': 'high'},
   {'file_id': '6d7490fd-cf3a-4d8a-b1c3-f62c7f95e4e4',
    'parties': ['plaintiff'],
    'category': 'meeting',
    'disputed': False,
    'event_id': '9502329c-7f1c-4aa0-8973-d7bbd8871d8a',
    'created_at': '2026-02-05T12:12:20.15631+00:00',
    'event_date': '2020-03-10T00:00:00+00:00',
    'event_name': 'inspection_date',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'description': 'Befaring gjennomført for å undersøke betongdekke på eiendom.',
    'significance': 'medium'}],
  'project_parties': [{'role': 'plaintiff',
    'party_id': '125ad5b1-5dac-4711-b387-82453f1487f4',
    'created_at': '2026-02-05T12:12:20.062707+00:00',
    'legal_name': 'Anders Kristiansen',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'entity_type': 'individual',
    'key_contact': None},
   {'role': 'plaintiff',
    'party_id': 'f1e79376-8ffb-480a-904c-7b9bb8beeb2e',
    'created_at': '2026-02-05T12:12:20.062707+00:00',
    'legal_name': 'Berit Kristiansen',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'entity_type': 'individual',
    'key_contact': None}],
  'project_deadlines': [{'file_id': 'ec93234f-2d18-4ace-83a9-8fba789aff44',
    'created_at': '2026-02-05T12:12:20.265036+00:00',
    'party_role': None,
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'deadline_id': 'ae0d1d84-e706-4a7b-990a-4ff7db135544',
    'description': 'Deadline for repairs to be completed before handover.',
    'deadline_date': '2019-08-01T00:00:00+00:00'},
   {'file_id': '4ec72cdf-dc46-4e25-8c40-b161798e6b7d',
    'created_at': '2026-02-05T12:12:20.265036+00:00',
    'party_role': None,
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'deadline_id': '7f1471a6-8e9d-4eb3-a2f1-81e100310095',
    'description': 'Takeover of the property',
    'deadline_date': '2019-08-01T00:00:00+00:00'},
   {'file_id': 'fc545f59-ac93-4cda-8b41-83eed0d04ee3',
    'created_at': '2026-02-05T12:12:20.265036+00:00',
    'party_role': None,
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'deadline_id': '6f37ef48-65a4-4702-babb-cc8c67827681',
    'description': "Last rental day according to tenant's termination notice",
    'deadline_date': '2022-12-31T00:00:00+00:00'}],
  'project_damages': [{'basis': 'Dokumenterte flyttekostnader',
    'amount': 54800,
    'file_id': '9a7722d6-804b-42bf-b3af-8b2860dc207b',
    'category': 'direct_losses',
    'damage_id': '20148f6b-3de1-4198-9ba9-3edeae4defd5',
    'created_at': '2026-02-05T12:12:20.35751+00:00',
    'party_role': None,
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'supporting_evidence': ['file1', 'file2', 'file3']},
   {'basis': 'Estimert fremtidige flyttekostnader',
    'amount': 50000,
    'file_id': '9a7722d6-804b-42bf-b3af-8b2860dc207b',
    'category': 'consequential',
    'damage_id': '932c4d44-53f1-49f9-856e-af2adad301aa',
    'created_at': '2026-02-05T12:12:20.35751+00:00',
    'party_role': None,
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'supporting_evidence': ['file4']},
   {'basis': 'Lekkasje i betongdekk',
    'amount': None,
    'file_id': 'ceedaf8c-94a0-432a-9eef-a084796b21eb',
    'category': 'direct_losses',
    'damage_id': 'a26f8bd2-8d4d-4851-bab7-7f6d86b30c0f',
    'created_at': '2026-02-05T12:12:20.35751+00:00',
    'party_role': 'plaintiff',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'supporting_evidence': ['Skaderapport']}],
  'project_claims': [{'defense': None,
    'file_id': 'ceedaf8c-94a0-432a-9eef-a084796b21eb',
    'claim_id': '75e79a5f-f461-4ba8-be31-9e2f3114c3da',
    'created_at': '2026-02-05T12:12:20.453262+00:00',
    'party_role': 'plaintiff',
    'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
    'legal_basis': 'N/A',
    'factual_basis': 'Lekkasjen forårsaker betydelig skade på eiendommen.',
    'relief_sought': 'Utbedringer og erstatning for skader',
    'strength_assessment': 'strong'}],
  'project_custom': {'created_at': '2026-02-05T12:12:19.965227+00:00',
   'project_id': 'ce119cd7-2c72-4400-8133-a08888b747ff',
   'governing_law': {'key_areas': ['contract law',
     'property law',
     'lease agreements',
     'notice procedures',
     'contract signing'],
    'procedural_law': 'tvisteloven',
    'primary_jurisdiction': 'Norwegian law',
    'international_elements': None},
   'disputed_facts': [],
   'undisputed_facts': ['Eiendomskjøp på Fjellveien 42A i Stavanger kommune med problemer som har dukket opp etter kjøpet.',
    'Kvittering fra Viking Flyttebyrå AS for innflytting, datert 30. juli 2019.',
    'Kvittering fra Renhold Vest AS for rengjøring ved innflytting, datert 29. juli 2019.',
    'Kvittering fra Småjobber AS for internt flytt, datert 15. januar 2023.',
    'Estimat for fremtidige flyttekostnader basert på tilbud fra tre flyttebyråer, datert 15. januar 2023.',
    'Notice sent to Anders Kristiansen regarding the discovery of a leak in the property before handover, datert 15. juli 2019.',
    'Notification regarding the completion of repairs and other renovation details prior to property takeover, datert 25. juli 2019.',
    'Scheduled date for the takeover of the property, datert 1. august 2019.',
    'Email sent to Anders Kristiansen regarding repairs and readiness for takeover, datert 28. juli 2019.',
    'Lease agreement signed between Anders Kristiansen, Berit Kristiansen, and Martine Olsen for extension unit at Fjellveien 42A, datert 10. august 2019.',
    'Monthly rent increased from Kr 8,000 to Kr 9,000 for the extension unit, datert 1. august 2020.',
    'Termination notice received from Martine Olsen for the extension unit, effective 31 December 2022, datert 5. oktober 2022.',
    'New lease agreement signed between Anders Kristiansen, Berit Kristiansen, and Jonas Pettersen for an interior unit at Fjellveien 42A, datert 15. januar 2023.',
    'Anders Kristiansen discusses the leasing situation concerning the interior unit being rented out and the challenges faced by the family, datert 20. januar 2023.',
    'Purchase of kitchen appliances including a dishwasher, oven, refrigerator, and associated costs, datert 15. august 2019.',
    'Installation of a digital lock for security purposes, paid on 15.04.2024, datert 12. april 2024.',
    'Installation of an electric vehicle charger, completed and paid in cash, datert 5. september 2023.',
    'Installation of new lamps in the rental unit, datert 23. mars 2024.',
    'Self-done painting work with purchased materials, datert 1. januar 2024.',
    'Acquisition of garden tools such as rakes, datert 1. januar 2024.',
    'Purchase of outdoor furniture for the terrace, datert 1. januar 2024.',
    'Anders Kristiansen notifies Carl Danielsen of a recurring water leak issue in the rental part of the property, datert 18. august 2019.',
    'Inspection of property Fjellveien 42A for damage, datert 3. september 2019.',
    'Damage report for property at Fjellveien 42A was prepared, datert 10. september 2019.',
    'Completion of the inspection report by K2 Taksering AS regarding the leakage issues at Fjellveien 42A, datert 10. september 2019.',
    'Inspection of the property at Fjellveien 42A for leakage issues, datert 5. september 2019.',
    'Lease agreement signed between Anders and Berit Kristiansen (landlords) and Ole Martin Pedersen (tenant), datert 28. januar 2020.',
    'Technical report created by Kari Berg about concrete slab at Fjellveien 42A, datert 12. mars 2020.',
    'Inspection was conducted to examine the concrete slab on the property, datert 10. mars 2020.']}},
 'count': None}


@patch('database.database_modules.create_client')  # ← HER SETTES MOCKEN!
def test_load_project(mock_create_client):  # ← mock_create_client ER create_client nå
    """
    SLIK FUNGERER @patch:
    
    @patch('database.database_modules.create_client') gjør at:
    - create_client funksjonen i database_modules.py blir ERSTATTET med en mock
    - mock_create_client parameteren ER den erstattede funksjonen
    - Alle kall til create_client() går nå til mocken, ikke ekte Supabase
    
    FLYT:
    1. @patch erstatter create_client → mock_create_client
    2. mock_create_client.return_value = mock_supabase → setter hva mocken returnerer
    3. SupabaseManager() kjører __init__() som kaller create_client()
    4. Men create_client() er nå mock_create_client, så den returnerer mock_supabase
    5. self.supabase = mock_supabase (ikke ekte Supabase!)
    """
    # Sett opp hva mock_create_client skal returnere når den kalles
    mock_supabase = MagicMock()
    mock_create_client.return_value = mock_supabase  # ← NÅR create_client() kalles, returner dette
    
    # Konfigurer mock response chain
    mock_response = Mock()
    mock_response.data = MOCK_PROJECT_DATA['data'].copy()
    
    # Bygg opp chain: table().select().eq().single().execute()
    # Dette er hva SupabaseManager.load_project() kaller på self.supabase
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_response
    
    # Initialiser SupabaseManager
    # Internt kjører dette: self.supabase = create_client(url, key)
    # Men create_client er nå mocket, så self.supabase blir mock_supabase
    manager = SupabaseManager()
    
    # Kall load_project
    project_id = 'ce119cd7-2c72-4400-8133-a08888b747ff'
    result = manager.load_project(project_id)
    
    # Verifiser at create_client ble kalt (fra __init__)
    mock_create_client.assert_called_once()
    
    # Verifiser at riktig metoder ble kalt på mock_supabase
    mock_supabase.table.assert_called_once_with("projects")
    
    # Verifiser resultatet
    assert result is not None
    assert "factsheet" in result
    assert "attachments" in result
    
    # Sjekk factsheet innhold
    factsheet = result["factsheet"]
    assert factsheet.project_id == project_id
    assert factsheet.title == 'Eiendomskjøpssak - Problemer med eiendommen'
    assert len(factsheet.parties) == 2  # Anders og Berit
    
    # Sjekk attachments
    attachments = result["attachments"]
    assert len(attachments) == 11 # Fra mock data


@pytest.fixture
def mock_supabase_client():
    """
    Pytest fixture som kan brukes i flere tester.
    
    Eksempel bruk:
    def test_something(mock_supabase_client):
        # mock_supabase_client er allerede konfigurert
        pass
    """
    with patch('database.database_modules.create_client') as mock_create:
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        yield mock_client


def test_load_project_with_fixture(mock_supabase_client):
    """
    Alternativ test som bruker fixture i stedet for @patch.
    Dette er mer ryddig hvis du har mange tester som trenger samme mock.
    """
    # Konfigurer mock response
    mock_response = Mock()
    mock_response.data = MOCK_PROJECT_DATA['data'].copy()
    mock_supabase_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_response
    
    # Initialiser og test
    manager = SupabaseManager()
    result = manager.load_project('ce119cd7-2c72-4400-8133-a08888b747ff')
    
    assert result is not None
    assert result["factsheet"].title == 'Eiendomskjøpssak - Problemer med eiendommen'


"""
================================================================================
FORKLARING AV HVORDAN @patch FUNGERER
================================================================================

Uten @patch (normal kode):
------------------------
# I database_modules.py:
from supabase import create_client  # ← Importerer ekte funksjon

class SupabaseManager:
    def __init__(self):
        self.supabase = create_client(url, key)  # ← Kaller EKTE create_client
        
# Denne kobler til ekte Supabase!


Med @patch (i test):
--------------------
@patch('database.database_modules.create_client')  # ← Erstatter create_client
def test_something(mock_create_client):             # ← mock_create_client ER nå create_client
    
    # Sett opp hva mocken skal returnere
    fake_supabase = MagicMock()
    mock_create_client.return_value = fake_supabase  # ← Når create_client() kalles, returner fake_supabase
    
    # Nå kjører vi koden:
    manager = SupabaseManager()
    # Internt kjører __init__():
    #   self.supabase = create_client(url, key)
    #                   ↑
    #                   Dette er NÅ mock_create_client (ikke ekte!)
    #                   Så self.supabase = fake_supabase
    
    # Alle kall til self.supabase går til fake_supabase, ikke ekte Supabase!


Steg-for-steg:
--------------
1. @patch('database.database_modules.create_client') 
   → Finner create_client i database_modules.py
   → Erstatter den midlertidig med en Mock
   
2. def test_something(mock_create_client):
   → mock_create_client er den erstattede funksjonen
   
3. mock_create_client.return_value = fake_supabase
   → Sier "når mock_create_client() kalles, returner fake_supabase"
   
4. manager = SupabaseManager()
   → Kjører __init__() som kaller create_client()
   → Men create_client er nå mocken!
   → Så mock_create_client() kalles
   → Den returnerer fake_supabase
   → self.supabase = fake_supabase
   
5. Ingen ekte Supabase-kall skjer!
"""

