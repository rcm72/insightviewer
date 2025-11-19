# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2025 Robert Čmrlec

from dotenv import load_dotenv
import os

load_dotenv()  # Load variables from .env file

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
