"""Bronze tier adapters - Web scraping sources (HTML/Firecrawl)."""

from src.adapters.bronze.barcelona_activa import BarcelonaActivaAdapter
from src.adapters.bronze.cemit_galicia import CemitGaliciaAdapter
from src.adapters.bronze.cnt_agenda import CntAgendaAdapter
from src.adapters.bronze.nferias import NFeriasAdapter
from src.adapters.bronze.defensor_pueblo import DefensorPuebloAdapter
from src.adapters.bronze.horizonte_europa import HorizonteEuropaAdapter
from src.adapters.bronze.jgpa import JgpaAdapter
from src.adapters.bronze.la_moncloa import LaMoncloaAdapter
from src.adapters.bronze.larioja_agenda import LaRiojaAgendaAdapter
from src.adapters.bronze.navarra import NavarraAdapter
from src.adapters.bronze.oviedo_digital import OviedoDigitalAdapter
from src.adapters.bronze.puntos_vuela import PuntosVuelaAdapter
from src.adapters.bronze.segib import SegibAdapter
from src.adapters.bronze.soledadnodeseada import SoledadNoDeseadaAdapter
from src.adapters.bronze.tourdelempleo import TourDelEmpleoAdapter
from src.adapters.bronze.vacacionesseniors import VacacionesSeniorsAdapter
from src.adapters.bronze.visitnavarra import VisitNavarraAdapter

__all__ = [
    "BarcelonaActivaAdapter",
    "CemitGaliciaAdapter",
    "CntAgendaAdapter",
    "NFeriasAdapter",
    "DefensorPuebloAdapter",
    "HorizonteEuropaAdapter",
    "JgpaAdapter",
    "LaMoncloaAdapter",
    "LaRiojaAgendaAdapter",
    "NavarraAdapter",
    "OviedoDigitalAdapter",
    "PuntosVuelaAdapter",
    "SegibAdapter",
    "SoledadNoDeseadaAdapter",
    "TourDelEmpleoAdapter",
    "VacacionesSeniorsAdapter",
    "VisitNavarraAdapter",
]
