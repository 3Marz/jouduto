
from database import DatabaseManager
import constants

with DatabaseManager(constants.DB_PATH) as db:
    db.execute_script(constants.INITIAL_DB_SCHEME)
    print("Database initialized")

