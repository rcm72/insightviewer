# SPDX-License-Interier: AGPL-3.0-or-later
# Copyright (c) 2025 Robert Čmrlec

# app/routes/__init__.py
from flask import Blueprint

# Create blueprints for different route groups
nodes_bp = Blueprint("nodes", __name__)
people_bp = Blueprint("people", __name__)
people_bp = Blueprint("createNodeTypes", __name__)

# Import route files to register blueprints
from . import nodes, people, createNodeTypes
