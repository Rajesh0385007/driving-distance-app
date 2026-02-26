from flask import Flask, request, render_template_string
import requests
import urllib.parse
import pandas as pd
import json

app = Flask(__name__)

# =========================
# CONFIG
# =========================
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB upload limit
REQUEST_TIMEOUT = 10  # seconds

# =========================
# LOAD DESTINATIONS FROM JSON
# =========================
with open("destinations.json", "r") as f:
    data = json.load(f)

DESTINATIONS = [d["postcode"] for d in data["destinations"]]
AGENCY_MAP = {d["postcode"]: d["agency"] for d in data["destinations"]}
CITY_MAP = {d["postcode"]: d["city"] for d in data["destinations"]}

# =========================
# HELPER FUNCTIONS
# =========================
def geocode(postcode):
    """Get latitude and longitude of a postcode."""
    try:
        url = f"https://api.postcodes.io/postcodes/{urllib.parse.quote(postcode)}"
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != 200:
            return None
        return data["result"]["latitude"], data["result"]["longitude"]
    except Exception as e:
        print(f"Geocode error for {postcode}: {e}")
        return None

def get_route(lat1, lon1, lat2, lon2):
    """Get driving distance (km) and duration (min) between two coordinates."""
    try:
        url = f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if not data.get("routes"):
            return None
        route = data["routes"][0]
        return route["distance"] / 1000, route["duration"] / 60
    except Exception as e:
        print(f"Route error: {e}")
        return None

# =========================
# PRE-CACHE DESTINATION COORDINATES
# =========================
DEST_COORDS = {}
for dest in DESTINATIONS:
    coords = geocode(dest)
    if coords:
        DEST_COORDS[dest] = coords

print("Cached destination coordinates:", len(DEST_COORDS))

# =========================
# HTML TEMPLATE
# =========================
PAGE = """
<!doctype html>
<html>
  <body>
    <h2>Driving Distance Calculator</h2>

    <h3>Upload Excel File (Multiple Origins)</h3>
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="file"><br><br>
      <input type="submit" value="Upload & Calculate">
    </form>

    <br><hr><br>

    <h3>OR Enter Single Origin Postcode</h3>
    <form method="post">
      <label>Origin Postcode:</label><br>
      <input name="Origin" placeholder="Enter Origin Postcode"><br><br>
      <input type="submit" value="Calculate">
    </form>

    {% if error %}
      <p style="color:red;">{{ error }}</p>
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
# MAIN ROUTE
# =========================
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            rows = []

            # ---------------- FILE UPLOAD ----------------
            file = request.files.get("file")
            if file and file.filename != "":
                try:
                    df = pd.read_excel(file, engine="openpyxl")
                except Exception as e:
                    return render_template_string(PAGE, error=f"Excel read error: {e}")

                if "origin" not in df.columns:
                    return render_template_string(PAGE, error="Excel must contain column named 'origin'")

                for origin_pc in df["origin"].dropna():
                    origin_pc = str(origin_pc).strip()
                    origin_coords = geocode(origin_pc)
                    if not origin_coords:
                        print(f"Skipping invalid origin: {origin_pc}")
                        continue

                    for dest_pc, dest_coords in DEST_COORDS.items():
                        route = get_route(origin_coords[0], origin_coords[1], dest_coords[0], dest_coords[1])
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

                if not rows:
                    return render_template_string(PAGE, error="No valid routes found.")
                return render_template_string(PAGE, rows=rows)

            # ---------------- SINGLE ORIGIN ----------------
            origin_pc = request.form.get("Origin", "").strip()
            if not origin_pc:
                return render_template_string(PAGE, error="Please enter an origin postcode or upload a file.")

            origin_coords = geocode(origin_pc)
            if not origin_coords:
                return render_template_string(PAGE, error="Invalid origin postcode.")

            for dest_pc, dest_coords in DEST_COORDS.items():
                route = get_route(origin_coords[0], origin_coords[1], dest_coords[0], dest_coords[1])
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

            if not rows:
                return render_template_string(PAGE, error="No valid routes found.")
            return render_template_string(PAGE, rows=rows)

        except Exception as e:
            return render_template_string(PAGE, error=f"Server Error: {e}")

    return render_template_string(PAGE)

# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    app.run(debug=True)
