import os
import json
from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def index():
    points = []
    if os.path.exists("points.json"):
        with open("points.json", "r") as f:
            points = json.load(f)
    return render_template("index.html", points=points)

if name == "__main__":
    app.run(host="0.0.0.0", port=5000)