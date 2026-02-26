"""Bronze tier adapters - Web scraping sources (HTML/Firecrawl)."""

from src.adapters.bronze.cemit_galicia import CemitGaliciaAdapter
from src.adapters.bronze.cnt_agenda import CntAgendaAdapter
from src.adapters.bronze.defensor_pueblo import DefensorPuebloAdapter
from src.adapters.bronze.la_moncloa import LaMoncloaAdapter
from src.adapters.bronze.larioja_agenda import LaRiojaAgendaAdapter
from src.adapters.bronze.navarra import NavarraAdapter
from src.adapters.bronze.oviedo_digital import OviedoDigitalAdapter
from src.adapters.bronze.puntos_vuela import PuntosVuelaAdapter
from src.adapters.bronze.soledadnodeseada import SoledadNoDeseadaAdapter
from src.adapters.bronze.vacacionesseniors import VacacionesSeniorsAdapter
from src.adapters.bronze.visitnavarra import VisitNavarraAdapter

__all__ = [
    "CemitGaliciaAdapter",
    "CntAgendaAdapter",
    "DefensorPuebloAdapter",
    "LaMoncloaAdapter",
    "LaRiojaAgendaAdapter",
    "NavarraAdapter",
    "OviedoDigitalAdapter",
    "PuntosVuelaAdapter",
    "SoledadNoDeseadaAdapter",
    "VacacionesSeniorsAdapter",
    "VisitNavarraAdapter",
]
