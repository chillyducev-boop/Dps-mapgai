#!/bin/bash
python bot.py & gunicorn webapp:app --bind 0.0.0.0:$PORT --workers 1