
import sqlite3

from database import DatabaseManager
from constants import DB_PATH

import flet as ft
import pandas as pd

from datatypes import Inventory, Item, Distributor

@ft.control
class HomePage(ft.Container):
    def __init__(self):
        super().__init__()

        self.content = ft.Text("Home Page")
