from flask import Flask, request, render_template_string
import requests
import urllib.parse
import pandas as pd
import json

app = Flask(__name__)

# =========================
# LOAD STATIC DATA FROM JSON
# =========================
with open("destinations.json", "r") as f:
    data = json.load(f)

DESTINATIONS = [d["postcode"] for d in data["destinations"]]

AGENCY_MAP = {
    d["postcode"]: d["agency"] for d in data["destinations"]
}

CITY_MAP = {
    d["postcode"]: d["city"] for d in data["destinations"]
}

# =========================
# HTML PAGE
# =========================
PAGE = """
<!doctype html>
<html>
  <body>
    <h2>Driving Distance Calculator</h2>

    <h3>Upload Excel File (Multiple Origins)</h3>
    <form method="post" action="/" enctype="multipart/form-data">
      <input type="file" name="file"><br><br>
      <input type="submit" value="Upload & Calculate">
    </form>

    <br><hr><br>

    <h3>OR Enter Single Origin Postcode</h3>
    <form method="post" action="/">
      <label>Origin Postcode:</label><br>
      <input name="Origin" placeholder="Enter Origin Postcode"><br><br>
      <input type="submit" value="Calculate">
    </form>

    {% if error %}
      <p style="color: red;">{{ error }}</p>
    {% endif %}

    {% if rows %}
      <h3>Results:</h3>
      <table border="1" cellpadding="6" cellspacing="0">
        <tr>
          <th>Origin</th>
          <th>Destination</th>
          <th>Smart Safe Name</th>
          <th>City</th>
          <th>Distance (KM)</th>
          <th>Time (MIN)</th>
        </tr>
        {% for row in rows %}
        <tr>
          <td>{{ row.origin }}</td>
          <td>{{ row.dest }}</td>
          <td>{{ row.agency }}</td>
          <td>{{ row.city }}</td>
          <td>{{ row.dist }}</td>
          <td>{{ row.time }}</td>
        </tr>
        {% endfor %}
      </table>
    {% endif %}
  </body>
</html>
"""

# =========================
# HELPERS
# =========================
def geocode(postcode):
    url = f"https://api.postcodes.io/postcodes/{urllib.parse.quote(postcode)}"
    r = requests.get(url).json()
    if r.get("status") != 200:
        return None
    return r["result"]["latitude"], r["result"]["longitude"]

def get_route(lat1, lon1, lat2, lon2):
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{lon1},{lat1};{lon2},{lat2}?overview=false"
    )
    r = requests.get(url).json()
    if not r.get("routes"):
        return None
    route = r["routes"][0]
    return route["distance"] / 1000, route["duration"] / 60

# =========================
# ROUTE
# =========================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":

        # ===== FILE UPLOAD =====
        file = request.files.get("file")
        if file:
            try:
                df = pd.read_excel(file)
            except Exception:
                return render_template_string(PAGE, error="Invalid Excel file.")

            if "origin" not in df.columns:
                return render_template_string(PAGE, error="Excel must contain 'origin' column.")

            rows = []

            for origin_pc in df["origin"].dropna():
                origin_pc = str(origin_pc).strip()
                origin_coords = geocode(origin_pc)
                if not origin_coords:
                    continue

                for dest_pc in DESTINATIONS:
                    dest_coords = geocode(dest_pc)
                    if not dest_coords:
                        continue

                    route = get_route(
                        origin_coords[0], origin_coords[1],
                        dest_coords[0], dest_coords[1]
                    )

                    if route:
                        dist_km, time_min = route
                        rows.append({
                            "origin": origin_pc,
                            "dest": dest_pc,
                            "agency": AGENCY_MAP.get(dest_pc, "Unknown"),
                            "city": CITY_MAP.get(dest_pc, "Unknown"),
                            "dist": f"{dist_km:.1f}",
                            "time": f"{time_min:.1f}"
                        })

            return render_template_string(PAGE, rows=rows)

        # ===== SINGLE ORIGIN =====
        origin_pc = request.form.get("Origin", "").strip()
        if not origin_pc:
            return render_template_string(PAGE, error="Enter an origin or upload a file.")

        origin_coords = geocode(origin_pc)
        if not origin_coords:
            return render_template_string(PAGE, error="Invalid origin postcode.")

        rows = []
        for dest_pc in DESTINATIONS:
            dest_coords = geocode(dest_pc)
            if not dest_coords:
                continue

            route = get_route(
                origin_coords[0], origin_coords[1],
                dest_coords[0], dest_coords[1]
            )

            if route:
                dist_km, time_min = route
                rows.append({
                    "origin": origin_pc,
                    "dest": dest_pc,
                    "agency": AGENCY_MAP.get(dest_pc, "Unknown"),
                    "city": CITY_MAP.get(dest_pc, "Unknown"),
                    "dist": f"{dist_km:.1f}",
                    "time": f"{time_min:.1f}"
                })

        return render_template_string(PAGE, rows=rows)

    return render_template_string(PAGE)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)
