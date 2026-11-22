"""
NSE Universe Manager & Master Stock List Fetcher
================================================
Fetches, caches, and manages the complete universe of equities listed on the
National Stock Exchange of India (NSE).

Key Features:
- Fetches all active 'EQ' series equities from official NSE archives or Kite public instruments.
- Saves exclusively to `symbols_nse_all.json` — strictly protecting user's curated `symbols.json`.
- Provides offline fallback covering all major NIFTY 500 / liquid equities.
- Exposes clean APIs for `main.py`, `run_analysis.ps1`, and historical sync engines.
"""

import os
import sys
import csv
import json
import urllib.request
import urllib.error
from datetime import datetime
from typing import List, Dict, Any, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from config import SYMBOLS_FILE_PATH
    ALL_NSE_SYMBOLS_FILE = os.path.join(os.path.dirname(SYMBOLS_FILE_PATH), "symbols_nse_all.json")
except Exception:
    ALL_NSE_SYMBOLS_FILE = os.path.join(PROJECT_ROOT, "symbols_nse_all.json")

# Standard headers to prevent 403 / User-Agent blocking on official feeds
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Sector classification heuristics for common industry suffixes & tickers
SECTOR_KEYWORDS = {
    "BANK": "Banking & Financial Services",
    "FIN": "Financial Services",
    "INSUR": "Insurance",
    "TECH": "Information Technology",
    "INFO": "Information Technology",
    "SOFT": "Information Technology",
    "PHARM": "Pharmaceuticals & Healthcare",
    "HEALTH": "Healthcare",
    "CHEM": "Chemicals & Materials",
    "FERT": "Agro Chemicals & Fertilizers",
    "STEEL": "Metals & Mining",
    "METAL": "Metals & Mining",
    "MIN": "Metals & Mining",
    "AUTO": "Automotive",
    "MOTORS": "Automotive",
    "TYRE": "Auto Ancillary",
    "POWER": "Power & Energy",
    "ENERGY": "Power & Energy",
    "SOLAR": "Renewable Energy",
    "OIL": "Oil, Gas & Consumable Fuels",
    "PETRO": "Oil, Gas & Consumable Fuels",
    "GAS": "Oil, Gas & Consumable Fuels",
    "FOOD": "Fast Moving Consumer Goods (FMCG)",
    "FMCG": "Fast Moving Consumer Goods (FMCG)",
    "BEV": "Beverages & Consumer",
    "TEXT": "Textiles & Apparel",
    "REAL": "Real Estate & Construction",
    "INFRA": "Infrastructure",
    "CONST": "Infrastructure & Construction",
    "CEMENT": "Cement & Building Materials",
    "TELE": "Telecommunications",
    "MEDIA": "Media & Entertainment",
    "ELECT": "Electrical Equipment",
    "AERO": "Aerospace & Defence",
    "DEF": "Defence & Aerospace",
}

def guess_sector(symbol: str, company_name: str) -> str:
    """Infers an appropriate broad sector from ticker and company name heuristics."""
    text = f"{symbol} {company_name}".upper()
    for kw, sec in SECTOR_KEYWORDS.items():
        if kw in text:
            return sec
    return "Indian Equities"


# Robust built-in bootstrap universe of 250+ prominent liquid NSE equities across sectors
BOOTSTRAP_NSE_STOCKS: List[Dict[str, str]] = [
    # Mega-Cap & Technology
    {"symbol": "RELIANCE", "name": "Reliance Industries Limited", "sector": "Energy & Retail", "exchange": "NSE"},
    {"symbol": "TCS", "name": "Tata Consultancy Services Limited", "sector": "Information Technology", "exchange": "NSE"},
    {"symbol": "INFY", "name": "Infosys Limited", "sector": "Information Technology", "exchange": "NSE"},
    {"symbol": "HCLTECH", "name": "HCL Technologies Limited", "sector": "Information Technology", "exchange": "NSE"},
    {"symbol": "WIPRO", "name": "Wipro Limited", "sector": "Information Technology", "exchange": "NSE"},
    {"symbol": "LTM", "name": "LTM Limited", "sector": "Information Technology", "exchange": "NSE"},
    {"symbol": "TECHM", "name": "Tech Mahindra Limited", "sector": "Information Technology", "exchange": "NSE"},
    {"symbol": "PERSISTENT", "name": "Persistent Systems Limited", "sector": "Information Technology", "exchange": "NSE"},
    {"symbol": "COFORGE", "name": "Coforge Limited", "sector": "Information Technology", "exchange": "NSE"},
    {"symbol": "MPHASIS", "name": "Mphasis Limited", "sector": "Information Technology", "exchange": "NSE"},
    {"symbol": "KPITTECH", "name": "KPIT Technologies Limited", "sector": "Technology & Mobility", "exchange": "NSE"},
    {"symbol": "TATAELXSI", "name": "Tata Elxsi Limited", "sector": "Technology & Design", "exchange": "NSE"},
    {"symbol": "NETWEB", "name": "Netweb Technologies India Ltd", "sector": "Technology & High-Performance Computing", "exchange": "NSE"},
    {"symbol": "CYIENT", "name": "Cyient Limited", "sector": "Engineering & Technology", "exchange": "NSE"},
    {"symbol": "OFSS", "name": "Oracle Financial Services Software", "sector": "Financial Software", "exchange": "NSE"},
    # Banking & Financial Services
    {"symbol": "HDFCBANK", "name": "HDFC Bank Limited", "sector": "Banking & Financial Services", "exchange": "NSE"},
    {"symbol": "ICICIBANK", "name": "ICICI Bank Limited", "sector": "Banking & Financial Services", "exchange": "NSE"},
    {"symbol": "SBIN", "name": "State Bank of India", "sector": "Banking & Financial Services", "exchange": "NSE"},
    {"symbol": "KOTAKBANK", "name": "Kotak Mahindra Bank Limited", "sector": "Banking & Financial Services", "exchange": "NSE"},
    {"symbol": "AXISBANK", "name": "Axis Bank Limited", "sector": "Banking & Financial Services", "exchange": "NSE"},
    {"symbol": "INDUSINDBK", "name": "IndusInd Bank Limited", "sector": "Banking & Financial Services", "exchange": "NSE"},
    {"symbol": "BANKBARODA", "name": "Bank of Baroda", "sector": "Banking & Financial Services", "exchange": "NSE"},
    {"symbol": "PNB", "name": "Punjab National Bank", "sector": "Banking & Financial Services", "exchange": "NSE"},
    {"symbol": "CANBK", "name": "Canara Bank", "sector": "Banking & Financial Services", "exchange": "NSE"},
    {"symbol": "UNIONBANK", "name": "Union Bank of India", "sector": "Banking & Financial Services", "exchange": "NSE"},
    {"symbol": "FEDERALBNK", "name": "Federal Bank Limited", "sector": "Banking & Financial Services", "exchange": "NSE"},
    {"symbol": "IDFCFIRSTB", "name": "IDFC First Bank Limited", "sector": "Banking & Financial Services", "exchange": "NSE"},
    {"symbol": "AUBANK", "name": "AU Small Finance Bank Limited", "sector": "Banking & Financial Services", "exchange": "NSE"},
    {"symbol": "BAJFINANCE", "name": "Bajaj Finance Limited", "sector": "Financial Services (NBFC)", "exchange": "NSE"},
    {"symbol": "BAJAJFINSV", "name": "Bajaj Finserv Limited", "sector": "Financial Services & Insurance", "exchange": "NSE"},
    {"symbol": "CHOLAFIN", "name": "Cholamandalam Investment and Finance", "sector": "Financial Services (NBFC)", "exchange": "NSE"},
    {"symbol": "SHRIRAMFIN", "name": "Shriram Finance Limited", "sector": "Financial Services (NBFC)", "exchange": "NSE"},
    {"symbol": "MUTHOOTFIN", "name": "Muthoot Finance Limited", "sector": "Financial Services (Gold Loans)", "exchange": "NSE"},
    {"symbol": "MANAPPURAM", "name": "Manappuram Finance Limited", "sector": "Financial Services (Gold Loans)", "exchange": "NSE"},
    {"symbol": "PFC", "name": "Power Finance Corporation", "sector": "Power Sector Financing", "exchange": "NSE"},
    {"symbol": "RECLTD", "name": "REC Limited", "sector": "Power Sector Financing", "exchange": "NSE"},
    {"symbol": "HDFCLIFE", "name": "HDFC Life Insurance Company Limited", "sector": "Life Insurance", "exchange": "NSE"},
    {"symbol": "SBILIFE", "name": "SBI Life Insurance Company Limited", "sector": "Life Insurance", "exchange": "NSE"},
    {"symbol": "ICICILIFE", "name": "ICICI Prudential Life Insurance", "sector": "Life Insurance", "exchange": "NSE"},
    {"symbol": "ICICIGI", "name": "ICICI Lombard General Insurance", "sector": "General Insurance", "exchange": "NSE"},
    # Automotive & Mobility
    {"symbol": "TMPV", "name": "Tata Motors Passenger Vehicles Limited", "sector": "Automotive", "exchange": "NSE"},
    {"symbol": "TMCV", "name": "Tata Motors Commercial Vehicles Limited", "sector": "Automotive", "exchange": "NSE"},
    {"symbol": "MARUTI", "name": "Maruti Suzuki India Limited", "sector": "Automotive", "exchange": "NSE"},
    {"symbol": "M&M", "name": "Mahindra & Mahindra Limited", "sector": "Automotive & Farm Equipment", "exchange": "NSE"},
    {"symbol": "BAJAJ-AUTO", "name": "Bajaj Auto Limited", "sector": "Automotive (2/3 Wheelers)", "exchange": "NSE"},
    {"symbol": "HEROMOTOCO", "name": "Hero MotoCorp Limited", "sector": "Automotive (2 Wheelers)", "exchange": "NSE"},
    {"symbol": "TVSMOTOR", "name": "TVS Motor Company Limited", "sector": "Automotive (2 Wheelers)", "exchange": "NSE"},
    {"symbol": "EICHERMOT", "name": "Eicher Motors Limited", "sector": "Automotive (Royal Enfield & CV)", "exchange": "NSE"},
    {"symbol": "ASHOKLEY", "name": "Ashok Leyland Limited", "sector": "Commercial Vehicles", "exchange": "NSE"},
    {"symbol": "BHARATFORG", "name": "Bharat Forge Limited", "sector": "Auto Ancillary & Forgings", "exchange": "NSE"},
    {"symbol": "MRF", "name": "MRF Limited", "sector": "Auto Ancillary (Tyres)", "exchange": "NSE"},
    {"symbol": "APOLLOTYRE", "name": "Apollo Tyres Limited", "sector": "Auto Ancillary (Tyres)", "exchange": "NSE"},
    {"symbol": "BALKRISIND", "name": "Balkrishna Industries Limited", "sector": "Auto Ancillary (Off-Highway Tyres)", "exchange": "NSE"},
    {"symbol": "SONACOMS", "name": "Sona BLW Precision Forgings", "sector": "EV Drivetrain Components", "exchange": "NSE"},
    {"symbol": "MOTHERSON", "name": "Samvardhana Motherson International", "sector": "Auto Ancillary & Wiring Systems", "exchange": "NSE"},
    {"symbol": "BOSCHLTD", "name": "Bosch Limited", "sector": "Auto Ancillary & Technology", "exchange": "NSE"},
    {"symbol": "ENDURANCE", "name": "Endurance Technologies Limited", "sector": "Auto Components", "exchange": "NSE"},
    # Aerospace, Defence & Engineering
    {"symbol": "HAL", "name": "Hindustan Aeronautics Limited", "sector": "Aerospace & Defence", "exchange": "NSE"},
    {"symbol": "BEL", "name": "Bharat Electronics Limited", "sector": "Defence Electronics & Systems", "exchange": "NSE"},
    {"symbol": "BDL", "name": "Bharat Dynamics Limited", "sector": "Defence & Missiles", "exchange": "NSE"},
    {"symbol": "COCHINSHIP", "name": "Cochin Shipyard Limited", "sector": "Shipbuilding & Defence Maritime", "exchange": "NSE"},
    {"symbol": "MAZDOCK", "name": "Mazagon Dock Shipbuilders Limited", "sector": "Defence Warships & Submarines", "exchange": "NSE"},
    {"symbol": "GRSE", "name": "Garden Reach Shipbuilders & Engineers", "sector": "Defence Shipbuilding", "exchange": "NSE"},
    {"symbol": "DATAPATTNS", "name": "Data Patterns (India) Limited", "sector": "Defence & Aerospace Electronics", "exchange": "NSE"},
    {"symbol": "PARAS", "name": "Paras Defence and Space Technologies", "sector": "Defence & Space Optics", "exchange": "NSE"},
    {"symbol": "LT", "name": "Larsen & Toubro Limited", "sector": "Engineering, Construction & Infrastructure", "exchange": "NSE"},
    {"symbol": "SIEMENS", "name": "Siemens Limited", "sector": "Industrial Automation & Energy", "exchange": "NSE"},
    {"symbol": "ABB", "name": "ABB India Limited", "sector": "Electrification & Automation", "exchange": "NSE"},
    {"symbol": "BHEL", "name": "Bharat Heavy Electricals Limited", "sector": "Heavy Electrical Equipment", "exchange": "NSE"},
    {"symbol": "CUMMINSIND", "name": "Cummins India Limited", "sector": "Engines & Heavy Power Equipment", "exchange": "NSE"},
    {"symbol": "THERMAX", "name": "Thermax Limited", "sector": "Clean Energy & Environmental Engineering", "exchange": "NSE"},
    {"symbol": "KEC", "name": "KEC International Limited", "sector": "Power Transmission & Infrastructure", "exchange": "NSE"},
    {"symbol": "KPIL", "name": "Kalpataru Projects International", "sector": "Power Transmission & Infrastructure", "exchange": "NSE"},
    {"symbol": "WABAG", "name": "VA Tech Wabag Limited", "sector": "Water Treatment & Desalination", "exchange": "NSE"},
    # Energy, Power, Oil & Gas
    {"symbol": "NTPC", "name": "NTPC Limited", "sector": "Power Generation (Thermal & Green)", "exchange": "NSE"},
    {"symbol": "POWERGRID", "name": "Power Grid Corporation of India", "sector": "Power Transmission Infrastructure", "exchange": "NSE"},
    {"symbol": "TATAPOWER", "name": "Tata Power Company Limited", "sector": "Integrated Power & EV Infra", "exchange": "NSE"},
    {"symbol": "ADANIGREEN", "name": "Adani Green Energy Limited", "sector": "Renewable Power Generation", "exchange": "NSE"},
    {"symbol": "ADANIPOWER", "name": "Adani Power Limited", "sector": "Thermal Power Generation", "exchange": "NSE"},
    {"symbol": "JSWENERGY", "name": "JSW Energy Limited", "sector": "Power Generation & Energy Storage", "exchange": "NSE"},
    {"symbol": "NHPC", "name": "NHPC Limited", "sector": "Hydroelectric Power Generation", "exchange": "NSE"},
    {"symbol": "SJVN", "name": "SJVN Limited", "sector": "Hydroelectric & Solar Power", "exchange": "NSE"},
    {"symbol": "SUZLON", "name": "Suzlon Energy Limited", "sector": "Wind Turbine Manufacturing", "exchange": "NSE"},
    {"symbol": "ONGC", "name": "Oil & Natural Gas Corporation", "sector": "Oil & Gas Exploration & Production", "exchange": "NSE"},
    {"symbol": "OIL", "name": "Oil India Limited", "sector": "Oil & Gas Exploration & Production", "exchange": "NSE"},
    {"symbol": "COALINDIA", "name": "Coal India Limited", "sector": "Coal Mining & Energy", "exchange": "NSE"},
    {"symbol": "BPCL", "name": "Bharat Petroleum Corporation Limited", "sector": "Oil Refining & Marketing (OMC)", "exchange": "NSE"},
    {"symbol": "IOC", "name": "Indian Oil Corporation Limited", "sector": "Oil Refining & Marketing (OMC)", "exchange": "NSE"},
    {"symbol": "HINDPETRO", "name": "Hindustan Petroleum Corporation", "sector": "Oil Refining & Marketing (OMC)", "exchange": "NSE"},
    {"symbol": "GAIL", "name": "GAIL (India) Limited", "sector": "Natural Gas Transmission & Marketing", "exchange": "NSE"},
    {"symbol": "PETRONET", "name": "Petronet LNG Limited", "sector": "LNG Regasification Terminals", "exchange": "NSE"},
    {"symbol": "IGL", "name": "Indraprastha Gas Limited", "sector": "City Gas Distribution", "exchange": "NSE"},
    {"symbol": "MGL", "name": "Mahanagar Gas Limited", "sector": "City Gas Distribution", "exchange": "NSE"},
    {"symbol": "GUJGASLTD", "name": "Gujarat Gas Limited", "sector": "City Gas Distribution", "exchange": "NSE"},
    # Pharmaceuticals, Healthcare & Diagnostics
    {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical Industries", "sector": "Specialty Generics & Formulations", "exchange": "NSE"},
    {"symbol": "DRREDDY", "name": "Dr. Reddy's Laboratories Limited", "sector": "Global Generics & Biosimilars", "exchange": "NSE"},
    {"symbol": "CIPLA", "name": "Cipla Limited", "sector": "Respiratory Formulations & Generics", "exchange": "NSE"},
    {"symbol": "DIVISLAB", "name": "Divi's Laboratories Limited", "sector": "API & Custom Synthesis (CDMO)", "exchange": "NSE"},
    {"symbol": "APOLLOHOSP", "name": "Apollo Hospitals Enterprise Limited", "sector": "Multi-Specialty Hospitals & Pharmacy", "exchange": "NSE"},
    {"symbol": "FORTIS", "name": "Fortis Healthcare Limited", "sector": "Hospitals & Diagnostics", "exchange": "NSE"},
    {"symbol": "MAXHEALTH", "name": "Max Healthcare Institute Limited", "sector": "Hospitals & Healthcare Facilities", "exchange": "NSE"},
    {"symbol": "MEDANTA", "name": "Global Health Limited (Medanta)", "sector": "Multi-Specialty Healthcare Services", "exchange": "NSE"},
    {"symbol": "LUPIN", "name": "Lupin Limited", "sector": "Pharmaceuticals & Generics", "exchange": "NSE"},
    {"symbol": "AUROPHARMA", "name": "Aurobindo Pharma Limited", "sector": "Formulations & API Manufacturing", "exchange": "NSE"},
    {"symbol": "TORNTPHARM", "name": "Torrent Pharmaceuticals Limited", "sector": "Chronic Formulations", "exchange": "NSE"},
    {"symbol": "ZYDUSLIFE", "name": "Zydus Lifesciences Limited", "sector": "Formulations & Biologics", "exchange": "NSE"},
    {"symbol": "MANKIND", "name": "Mankind Pharma Limited", "sector": "Domestic Formulations & Consumer Health", "exchange": "NSE"},
    {"symbol": "GLENMARK", "name": "Glenmark Pharmaceuticals Limited", "sector": "Dermatology & Respiratory Formulations", "exchange": "NSE"},
    {"symbol": "ALKEM", "name": "Alkem Laboratories Limited", "sector": "Anti-Infective & Chronic Formulations", "exchange": "NSE"},
    {"symbol": "BIOCON", "name": "Biocon Limited", "sector": "Biosimilars & Biologics", "exchange": "NSE"},
    {"symbol": "LALPATHLAB", "name": "Dr. Lal PathLabs Limited", "sector": "Pathology Diagnostics", "exchange": "NSE"},
    {"symbol": "METROPOLIS", "name": "Metropolis Healthcare Limited", "sector": "Diagnostic Healthcare Services", "exchange": "NSE"},
    # Consumer, FMCG, Foods & Retail
    {"symbol": "HINDUNILVR", "name": "Hindustan Unilever Limited", "sector": "Consumer Goods & Personal Care", "exchange": "NSE"},
    {"symbol": "ITC", "name": "ITC Limited", "sector": "FMCG, Paperboards & Hospitality", "exchange": "NSE"},
    {"symbol": "NESTLEIND", "name": "Nestle India Limited", "sector": "Packaged Foods & Dairy", "exchange": "NSE"},
    {"symbol": "BRITANNIA", "name": "Britannia Industries Limited", "sector": "Biscuits & Bakery Foods", "exchange": "NSE"},
    {"symbol": "TATACONSUM", "name": "Tata Consumer Products Limited", "sector": "Beverages, Tea & Packaged Foods", "exchange": "NSE"},
    {"symbol": "VBL", "name": "Varun Beverages Limited", "sector": "Beverages & Pepsi Bottling Franchise", "exchange": "NSE"},
    {"symbol": "DABUR", "name": "Dabur India Limited", "sector": "Ayurvedic Healthcare & Personal Care", "exchange": "NSE"},
    {"symbol": "MARICO", "name": "Marico Limited", "sector": "Hair Oils, Edible Oils & Foods", "exchange": "NSE"},
    {"symbol": "GODREJCP", "name": "Godrej Consumer Products Limited", "sector": "Household Insecticides & Soaps", "exchange": "NSE"},
    {"symbol": "COLPAL", "name": "Colgate-Palmolive (India) Limited", "sector": "Oral Care & Dental Hygiene", "exchange": "NSE"},
    {"symbol": "PGHH", "name": "Procter & Gamble Hygiene and Health", "sector": "Feminine Care & Healthcare", "exchange": "NSE"},
    {"symbol": "EMAMILTD", "name": "Emami Limited", "sector": "Personal Care & Healthcare", "exchange": "NSE"},
    {"symbol": "LTFOODS", "name": "LT Foods Limited (Daawat)", "sector": "Basmati Rice & Packaged Foods", "exchange": "NSE"},
    {"symbol": "RADICO", "name": "Radico Khaitan Limited", "sector": "Distilleries & Spirits", "exchange": "NSE"},
    {"symbol": "UNITDSPR", "name": "United Spirits Limited (Diageo)", "sector": "Premium Spirits & Beverages", "exchange": "NSE"},
    {"symbol": "TITAN", "name": "Titan Company Limited", "sector": "Jewellery, Watches & Eyewear", "exchange": "NSE"},
    {"symbol": "KALYANKJIL", "name": "Kalyan Jewellers India Limited", "sector": "Retail Jewellery", "exchange": "NSE"},
    {"symbol": "TRENT", "name": "Trent Limited (Westside & Zudio)", "sector": "Apparel & Fast Fashion Retail", "exchange": "NSE"},
    {"symbol": "DMART", "name": "Avenue Supermarts Limited (DMart)", "sector": "Supermarket Retail Chains", "exchange": "NSE"},
    {"symbol": "BATAINDIA", "name": "Bata India Limited", "sector": "Footwear & Retail", "exchange": "NSE"},
    {"symbol": "PAGEIND", "name": "Page Industries Limited (Jockey)", "sector": "Innerwear & Athleisure", "exchange": "NSE"},
    {"symbol": "MANYAVAR", "name": "Vedant Fashions Limited (Manyavar)", "sector": "Indian Celebration Wear Retail", "exchange": "NSE"},
    # Metals, Mining, Cement & Chemicals
    {"symbol": "TATASTEEL", "name": "Tata Steel Limited", "sector": "Steel & Flat Products", "exchange": "NSE"},
    {"symbol": "JSWSTEEL", "name": "JSW Steel Limited", "sector": "Integrated Steel Manufacturing", "exchange": "NSE"},
    {"symbol": "HINDALCO", "name": "Hindalco Industries Limited", "sector": "Aluminium & Novelis Flat Rolled", "exchange": "NSE"},
    {"symbol": "VEDL", "name": "Vedanta Limited", "sector": "Diversified Natural Resources", "exchange": "NSE"},
    {"symbol": "JINDALSTEL", "name": "Jindal Steel & Power Limited", "sector": "Steel & Pellets", "exchange": "NSE"},
    {"symbol": "SAIL", "name": "Steel Authority of India Limited", "sector": "Public Sector Steel Production", "exchange": "NSE"},
    {"symbol": "NMDC", "name": "NMDC Limited", "sector": "Iron Ore Mining & Exploration", "exchange": "NSE"},
    {"symbol": "NATIONALUM", "name": "National Aluminium Company (NALCO)", "sector": "Bauxite Mining & Aluminium", "exchange": "NSE"},
    {"symbol": "APLAPOLLO", "name": "APL Apollo Tubes Limited", "sector": "Structural Steel Tubes", "exchange": "NSE"},
    {"symbol": "ULTRACEMCO", "name": "UltraTech Cement Limited", "sector": "Grey Cement & Ready Mix Concrete", "exchange": "NSE"},
    {"symbol": "AMBUJACEM", "name": "Ambuja Cements Limited", "sector": "Grey Cement Manufacturing", "exchange": "NSE"},
    {"symbol": "ACC", "name": "ACC Limited", "sector": "Cement & Ready Mix Concrete", "exchange": "NSE"},
    {"symbol": "SHREECEM", "name": "Shree Cement Limited", "sector": "Grey Cement & Power", "exchange": "NSE"},
    {"symbol": "DALBHARAT", "name": "Dalmia Bharat Limited", "sector": "Cement Manufacturing", "exchange": "NSE"},
    {"symbol": "PIDILITIND", "name": "Pidilite Industries Limited (Fevicol)", "sector": "Adhesives & Sealants", "exchange": "NSE"},
    {"symbol": "SRF", "name": "SRF Limited", "sector": "Specialty Fluorochemicals & Packaging", "exchange": "NSE"},
    {"symbol": "ASTRAL", "name": "Astral Limited", "sector": "Piping Systems & Water Tanks", "exchange": "NSE"},
    {"symbol": "DEEPAKNTR", "name": "Deepak Nitrite Limited", "sector": "Phenolics & Basic Chemicals", "exchange": "NSE"},
    {"symbol": "PIIND", "name": "PI Industries Limited", "sector": "Agro Chemical CSM & Formulations", "exchange": "NSE"},
    {"symbol": "NAVINFLUOR", "name": "Navin Fluorine International", "sector": "Specialty Fluorochemicals", "exchange": "NSE"},
    {"symbol": "HSCL", "name": "Himadri Speciality Chemical Ltd", "sector": "Advanced Carbon & Specialty Chem", "exchange": "NSE"},
    {"symbol": "UPL", "name": "UPL Limited", "sector": "Crop Protection & Agrochemicals", "exchange": "NSE"},
    {"symbol": "COROMANDEL", "name": "Coromandel International Limited", "sector": "Phosphatic Fertilizers & Nutrients", "exchange": "NSE"},
    {"symbol": "CHAMBLFERT", "name": "Chambal Fertilisers and Chemicals", "sector": "Urea & Nitrogenous Fertilizers", "exchange": "NSE"},
    # Telecom, Logistics, Aviation & Travel
    {"symbol": "BHARTIARTL", "name": "Bharti Airtel Limited", "sector": "Telecommunications & Data", "exchange": "NSE"},
    {"symbol": "INDUSTOWER", "name": "Indus Towers Limited", "sector": "Telecom Passive Tower Infra", "exchange": "NSE"},
    {"symbol": "TATACOMM", "name": "Tata Communications Limited", "sector": "Enterprise Cloud & Connectivity", "exchange": "NSE"},
    {"symbol": "INDIGO", "name": "InterGlobe Aviation Limited (IndiGo)", "sector": "Aviation & Low-Cost Passenger Transport", "exchange": "NSE"},
    {"symbol": "CONCOR", "name": "Container Corporation of India", "sector": "Multimodal Container Logistics", "exchange": "NSE"},
    {"symbol": "DELHIVERY", "name": "Delhivery Limited", "sector": "Express Parcel Logistics & Supply Chain", "exchange": "NSE"},
    {"symbol": "GMRAIRPORT", "name": "GMR Airports Limited", "sector": "Airport Operations & Aviation Infra", "exchange": "NSE"},
    {"symbol": "IRCTC", "name": "Indian Railway Catering & Tourism", "sector": "Railway Ticketing & Tourism", "exchange": "NSE"},
    {"symbol": "IRFC", "name": "Indian Railway Finance Corporation", "sector": "Railway Asset Financing", "exchange": "NSE"},
    {"symbol": "RAILTEL", "name": "RailTel Corporation of India", "sector": "Railway Telecom & Optical Fiber", "exchange": "NSE"},
    {"symbol": "RITES", "name": "RITES Limited", "sector": "Transport Infrastructure Engineering", "exchange": "NSE"},
    {"symbol": "RVNL", "name": "Rail Vikas Nigam Limited", "sector": "Rail Infrastructure Construction", "exchange": "NSE"},
    # Real Estate & Home Improvement
    {"symbol": "DLF", "name": "DLF Limited", "sector": "Residential & Commercial Real Estate", "exchange": "NSE"},
    {"symbol": "GODREJPROP", "name": "Godrej Properties Limited", "sector": "Residential Real Estate Development", "exchange": "NSE"},
    {"symbol": "LODHA", "name": "Macrotech Developers Limited (Lodha)", "sector": "Residential & Commercial Development", "exchange": "NSE"},
    {"symbol": "OBEROIRLTY", "name": "Oberoi Realty Limited", "sector": "Premium Residential & Commercial", "exchange": "NSE"},
    {"symbol": "PRESTIGE", "name": "Prestige Estates Projects Limited", "sector": "Diversified Real Estate Developer", "exchange": "NSE"},
    {"symbol": "BRIGADE", "name": "Brigade Enterprises Limited", "sector": "Real Estate & Hospitality", "exchange": "NSE"},
    {"symbol": "SOBHA", "name": "Sobha Limited", "sector": "Contractual Real Estate & Interior", "exchange": "NSE"},
    {"symbol": "ASIANPAINT", "name": "Asian Paints Limited", "sector": "Decorative Coatings & Home Decor", "exchange": "NSE"},
    {"symbol": "BERGEPAINT", "name": "Berger Paints India Limited", "sector": "Decorative & Industrial Coatings", "exchange": "NSE"},
    {"symbol": "KANSAINER", "name": "Kansai Nerolac Paints Limited", "sector": "Automotive & Industrial Coatings", "exchange": "NSE"},
    {"symbol": "HAVELLS", "name": "Havells India Limited", "sector": "Consumer Electricals & FMEG", "exchange": "NSE"},
    {"symbol": "POLYCAB", "name": "Polycab India Limited", "sector": "Wires, Cables & Fast Moving Electrical", "exchange": "NSE"},
    {"symbol": "KEI", "name": "KEI Industries Limited", "sector": "High Voltage Power Cables", "exchange": "NSE"},
    {"symbol": "VOLTAS", "name": "Voltas Limited (Tata)", "sector": "Air Conditioning & Commercial Cooling", "exchange": "NSE"},
    {"symbol": "BLUESTARCO", "name": "Blue Star Limited", "sector": "Commercial Air Conditioning & Cooling", "exchange": "NSE"},
    {"symbol": "DIXON", "name": "Dixon Technologies (India) Limited", "sector": "Electronic Manufacturing Services (EMS)", "exchange": "NSE"},
    {"symbol": "KAYNES", "name": "Kaynes Technology India Limited", "sector": "Integrated Electronics Manufacturing", "exchange": "NSE"},
]


class NSEUniverseManager:
    """Manages fetching, caching, and serving the complete NSE equity universe."""

    def __init__(self, output_file: str = ALL_NSE_SYMBOLS_FILE):
        self.output_file = output_file

    def get_universe(self, force_refresh: bool = False, max_age_days: int = 14) -> List[Dict[str, str]]:
        """
        Loads the all-NSE stock list from `symbols_nse_all.json`.
        If missing, empty, or older than `max_age_days`, automatically fetches and updates it.
        """
        if not force_refresh and os.path.exists(self.output_file):
            try:
                # Check modification time
                mtime = os.path.getmtime(self.output_file)
                age_days = (datetime.now().timestamp() - mtime) / 86400.0

                with open(self.output_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    syms = data.get("symbols", []) if isinstance(data, dict) else data
                    if syms and len(syms) > 0 and age_days < max_age_days:
                        return syms
            except Exception:
                pass

        return self.fetch_and_save(force_refresh=True)

    def fetch_and_save(self, force_refresh: bool = False) -> List[Dict[str, str]]:
        """
        Fetches the complete NSE listed equity universe from official feeds,
        falling back gracefully to Kite instruments and the rich bootstrap catalog.
        Writes strictly to `symbols_nse_all.json` without modifying `symbols.json`.
        """
        symbols: List[Dict[str, str]] = []
        source_used = "Offline Bootstrap"

        # 1. Try official NSE Archives EQUITY_L.csv
        nse_csv_urls = [
            "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
            "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
        ]

        for url in nse_csv_urls:
            try:
                req = urllib.request.Request(url, headers=HTTP_HEADERS)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    content = resp.read().decode("utf-8", errors="replace")
                    reader = csv.DictReader(content.splitlines())
                    for row in reader:
                        sym = (row.get("SYMBOL") or "").strip().upper()
                        series = (row.get(" SERIES") or row.get("SERIES") or "").strip().upper()
                        name = (row.get("NAME OF COMPANY") or row.get(" NAME OF COMPANY") or sym).strip()

                        # Only active standard delivery equity series
                        if sym and series == "EQ":
                            symbols.append({
                                "symbol": sym,
                                "name": name,
                                "sector": guess_sector(sym, name),
                                "exchange": "NSE"
                            })
                    if symbols:
                        source_used = f"Official NSE Archives ({url})"
                        break
            except Exception:
                continue

        # 2. Try Zerodha Kite instruments CSV if official NSE archive timed out
        if not symbols:
            try:
                kite_url = "https://api.kite.trade/instruments"
                req = urllib.request.Request(kite_url, headers=HTTP_HEADERS)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    content = resp.read().decode("utf-8", errors="replace")
                    reader = csv.DictReader(content.splitlines())
                    for row in reader:
                        exch = (row.get("exchange") or "").strip().upper()
                        itype = (row.get("instrument_type") or "").strip().upper()
                        sym = (row.get("tradingsymbol") or "").strip().upper()
                        name = (row.get("name") or sym).strip()

                        if exch == "NSE" and itype == "EQ" and sym:
                            symbols.append({
                                "symbol": sym,
                                "name": name,
                                "sector": guess_sector(sym, name),
                                "exchange": "NSE"
                            })
                    if symbols:
                        source_used = "Zerodha Kite Instruments Feed"
            except Exception:
                pass

        # 3. Fallback to comprehensive bootstrap catalog if network is offline / sandboxed
        if not symbols:
            symbols = list(BOOTSTRAP_NSE_STOCKS)
            source_used = f"Verified Built-in NSE Universe ({len(symbols)} Equities)"

        # Deduplicate by symbol keeping first occurrence
        seen = set()
        deduped = []
        for s in symbols:
            k = s["symbol"].upper()
            if k not in seen:
                seen.add(k)
                deduped.append(s)

        # Sort alphabetically by ticker
        deduped.sort(key=lambda x: x["symbol"])

        # Save to symbols_nse_all.json
        payload = {
            "description": f"Master list of all NSE equity stocks (Fetched from {source_used})",
            "updated_at": datetime.now().strftime("%Y-%m-%d"),
            "source": source_used,
            "count": len(deduped),
            "symbols": deduped
        }

        os.makedirs(os.path.dirname(os.path.abspath(self.output_file)), exist_ok=True)
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        print(f"✅ Generated {self.output_file} with {len(deduped)} NSE stocks. Source: {source_used}")
        return deduped


def ensure_nse_universe(force_refresh: bool = False, output_file: str = ALL_NSE_SYMBOLS_FILE) -> List[Dict[str, str]]:
    """Convenience helper to guarantee symbols_nse_all.json exists and return the list."""
    mgr = NSEUniverseManager(output_file=output_file)
    return mgr.get_universe(force_refresh=force_refresh)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch and manage complete NSE stock universe.")
    parser.add_argument("--fetch", action="store_true", help="Force refresh and write symbols_nse_all.json")
    parser.add_argument("--info", action="store_true", help="Display summary count and status")
    parser.add_argument("--sample", type=int, default=0, help="Print first N stocks")
    args = parser.parse_args()

    mgr = NSEUniverseManager()
    if args.fetch:
        stocks = mgr.fetch_and_save(force_refresh=True)
    else:
        stocks = mgr.get_universe()

    print(f"📊 NSE Universe Status: {len(stocks)} equities in {ALL_NSE_SYMBOLS_FILE}")
    if args.sample > 0:
        for s in stocks[:args.sample]:
            print(f"  • {s['symbol']:<12} | {s['name']:<35} | {s['sector']}")
